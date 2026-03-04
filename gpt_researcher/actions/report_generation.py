import asyncio
import re
from urllib.parse import urlparse
from typing import List, Dict, Any, Callable
from ..config.config import Config
from ..orchestration.coverage_lenses import (
    assess_chain_coverage,
    assess_text_coverage,
    coverage_chain_prompt_block,
    coverage_lens_prompt_block,
    resolve_chain_steps,
)
from ..utils.llm import create_chat_completion
from ..utils.logger import get_formatted_logger
from ..prompts import PromptFamily, get_prompt_by_report_type
from ..utils.enum import Tone

logger = get_formatted_logger()

REPORT_COMPLETE_MARKER = "<!-- REPORT_COMPLETE -->"
DEFAULT_MAX_OUTLINE_CONTEXT_CHARS = 24000
CONCLUSION_SECTION_PATTERN = re.compile(
    r"^#{1,6}\s*(conclusion|conclusions|summary|final thoughts|结论|总结|结语)(\s|:|：|$)",
    flags=re.IGNORECASE | re.MULTILINE,
)
REFERENCE_SECTION_PATTERN = re.compile(
    r"^#{1,6}\s*(references|reference|sources|bibliography|works cited|参考文献|参考资料|资料来源|来源)(\s|:|：|$)",
    flags=re.IGNORECASE | re.MULTILINE,
)
TRAILING_HEADER_PATTERN = re.compile(r"^#{1,6}\s+.+$")
MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((https?://[^\s)]+)\)")
URL_PATTERN = re.compile(r"https?://[^\s)]+")
DOMAIN_TOKEN_PATTERN = re.compile(
    r"(?<![@/])\b(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[a-z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?",
    flags=re.IGNORECASE,
)
PLACEHOLDER_REFERENCE_PATTERN = re.compile(
    r"^(?:链接|來源|来源|source|sources|reference|references|ref|n/?a|none|待补充|tbd)$",
    flags=re.IGNORECASE,
)
COVERAGE_CHECK_PATTERN = re.compile(r"(coverage check|gap notes|覆盖检查|缺口说明|缺口)", flags=re.IGNORECASE)
DECISION_SHEET_PATTERN = re.compile(
    r"\|\s*(?:option|方案)\s*\|\s*(?:expected value|预期价值)\s*\|\s*(?:feasibility|可行性)\s*\|",
    flags=re.IGNORECASE,
)

EXPLICIT_CHAIN_SECTION_RULES: list[dict[str, Any]] = [
    {
        "id": "industry",
        "label": "Industry",
        "keywords": ["industry", "macro", "sector", "行业", "宏观", "赛道"],
    },
    {
        "id": "brand",
        "label": "Brand",
        "keywords": ["brand", "entity", "group strategy", "品牌", "集团", "对象"],
    },
    {
        "id": "demand",
        "label": "Demand",
        "keywords": ["demand", "stakeholder", "consumer", "需求", "消费者", "利益相关方"],
    },
    {
        "id": "material",
        "label": "Material",
        "keywords": ["material", "raw material", "fiber", "input", "材料", "原材料", "纤维"],
    },
    {
        "id": "technology",
        "label": "Technology",
        "keywords": ["technology", "process", "pathway", "技术", "工艺", "技术路径"],
    },
    {
        "id": "execution",
        "label": "Execution",
        "keywords": ["execution", "rollout", "roadmap", "implementation", "落地", "执行", "路线图"],
    },
]


def evaluate_report_completeness(
    report: str,
    *,
    require_sections: bool,
    require_marker: bool,
) -> tuple[bool, list[str]]:
    """Return (is_complete, missing_requirements) for generated markdown report."""
    missing: list[str] = []
    report = (report or "").strip()

    lines = [line.rstrip() for line in report.splitlines()]
    non_empty_lines = [line for line in lines if line.strip()]
    if not non_empty_lines:
        missing.append("empty_report")
    else:
        last_non_empty = non_empty_lines[-1].strip()
        if TRAILING_HEADER_PATTERN.match(last_non_empty):
            missing.append("trailing_header_without_content")

    if require_sections and not CONCLUSION_SECTION_PATTERN.search(report):
        missing.append("missing_conclusion_section")
    if require_sections and not REFERENCE_SECTION_PATTERN.search(report):
        missing.append("missing_references_section")
    if require_marker and REPORT_COMPLETE_MARKER not in report:
        missing.append("missing_completion_marker")

    return len(missing) == 0, missing


def _strip_completion_marker(report: str) -> str:
    return report.replace(REPORT_COMPLETE_MARKER, "").strip()


def _truncate_text(value: str, max_chars: int) -> str:
    if max_chars <= 0:
        return value
    return value[:max_chars]


def _domain_from_url(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _is_transport_error(exc: Exception) -> bool:
    text = str(exc or "").lower()
    return any(
        token in text
        for token in (
            "incomplete chunked read",
            "connection",
            "peer closed",
            "eof",
            "transport",
            "timed out",
            "timeout",
        )
    )


def _reference_heading(language: str) -> str:
    lang = (language or "").lower()
    return "## 参考文献" if ("chinese" in lang or lang.startswith("zh")) else "## References"


def _conclusion_heading(language: str) -> str:
    lang = (language or "").lower()
    return "## 结论" if ("chinese" in lang or lang.startswith("zh")) else "## Conclusion"


def _build_reference_section_from_report(report: str, language: str, max_items: int = 20) -> str:
    heading = _reference_heading(language)
    lines: list[str] = []
    seen_urls: set[str] = set()
    for match in MARKDOWN_LINK_PATTERN.finditer(report or ""):
        title = (match.group(1) or "").strip() or "Source"
        url = (match.group(2) or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        lines.append(f"- [{title}]({url})")
        if len(lines) >= max_items:
            break
    if not lines:
        fallback_line = "- 未提取到可用外部链接。" if heading == "## 参考文献" else "- No external links were extracted."
        lines = [fallback_line]
    return f"{heading}\n" + "\n".join(lines)


def _normalize_url_candidate(raw_value: str) -> str:
    value = str(raw_value or "").strip().strip("()[]{}<>,.;")
    if not value:
        return ""
    if PLACEHOLDER_REFERENCE_PATTERN.match(value):
        return ""
    if value.lower().startswith(("http://", "https://")):
        normalized = value
    else:
        normalized = f"https://{value}"
    try:
        parsed = re.sub(r"\s+", "", normalized)
        if not parsed:
            return ""
        parts = urlparse(parsed)
        if not parts.netloc or "." not in parts.netloc:
            return ""
        return f"{parts.scheme}://{parts.netloc}{parts.path or ''}{('?' + parts.query) if parts.query else ''}"
    except Exception:
        return ""


def _extract_reference_urls(report: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def _append(candidate: str) -> None:
        normalized = _normalize_url_candidate(candidate)
        if not normalized:
            return
        key = normalized.lower()
        if key in seen:
            return
        seen.add(key)
        urls.append(normalized)

    for match in MARKDOWN_LINK_PATTERN.finditer(report or ""):
        _append(match.group(2))

    for match in URL_PATTERN.finditer(report or ""):
        _append(match.group(0))

    section_match = REFERENCE_SECTION_PATTERN.search(report or "")
    if section_match:
        ref_section = (report or "")[section_match.start():]
        for line in ref_section.splitlines():
            cleaned = line.strip().lstrip("-*").strip()
            if not cleaned:
                continue
            if PLACEHOLDER_REFERENCE_PATTERN.match(cleaned):
                continue
            for domain_token in DOMAIN_TOKEN_PATTERN.findall(cleaned):
                _append(domain_token)

    return urls


def _build_reference_section_from_urls(urls: list[str], language: str, max_items: int = 20) -> str:
    heading = _reference_heading(language)
    lines: list[str] = []
    for url in (urls or [])[:max_items]:
        domain = _domain_from_url(url) or "source"
        lines.append(f"- [{domain}]({url})")
    if not lines:
        fallback_line = "- 未提取到可用外部链接。" if heading == "## 参考文献" else "- No external links were extracted."
        lines = [fallback_line]
    return f"{heading}\n" + "\n".join(lines)


def _split_report_references(report: str) -> tuple[str, str]:
    match = REFERENCE_SECTION_PATTERN.search(report or "")
    if not match:
        return (report or "").rstrip(), ""
    return (report or "")[: match.start()].rstrip(), (report or "")[match.start():].strip()


def _sanitize_reference_hygiene(
    report: str,
    language: str,
    extra_context: str = "",
) -> tuple[str, dict[str, Any]]:
    body, existing_reference_section = _split_report_references(report or "")
    merged_source_text = "\n".join([str(report or ""), str(extra_context or "")]).strip()
    urls = _extract_reference_urls(merged_source_text)
    rebuilt_reference_section = _build_reference_section_from_urls(urls, language=language)
    existing_clean = existing_reference_section.strip()
    changed = existing_clean != rebuilt_reference_section.strip()
    sanitized = f"{body.rstrip()}\n\n{rebuilt_reference_section}".strip()
    metadata = {
        "reference_url_count": len(urls),
        "reference_hygiene_changed": changed,
        "reference_had_existing_section": bool(existing_clean),
    }
    return sanitized, metadata


def _apply_emergency_completion(
    report: str,
    missing_requirements: list[str],
    language: str,
    require_marker: bool,
) -> str:
    patched = (report or "").rstrip()
    missing = set(missing_requirements or [])

    if "trailing_header_without_content" in missing:
        filler = "- 待补充的段落在后续版本补全。" if ("chinese" in (language or "").lower() or str(language).lower().startswith("zh")) else "- Additional details are pending a follow-up update."
        patched = f"{patched}\n\n{filler}"

    if "missing_conclusion_section" in missing:
        heading = _conclusion_heading(language)
        text = (
            "- 基于当前可核验证据，核心结论已形成；其余未证实点已在正文标记为待验证。"
            if heading == "## 结论"
            else "- Based on currently verifiable evidence, core conclusions are established and unresolved items remain marked for validation."
        )
        patched = f"{patched}\n\n{heading}\n{text}"

    if "missing_references_section" in missing:
        patched = f"{patched}\n\n{_build_reference_section_from_report(patched, language)}"

    missing_blueprint_sections = [
        item.split(":", 1)[1].strip()
        for item in missing
        if item.startswith("missing_blueprint_section:")
    ]
    for title in missing_blueprint_sections:
        if not title:
            continue
        placeholder = (
            f"## {title}\n- 本节为结构占位，待补充经验证据与结论。"
            if ("chinese" in (language or "").lower() or str(language).lower().startswith("zh"))
            else f"## {title}\n- Placeholder section added to preserve required report structure."
        )
        if f"## {title}" not in patched:
            patched = f"{patched}\n\n{placeholder}"

    if require_marker and REPORT_COMPLETE_MARKER not in patched:
        patched = f"{patched}\n\n{REPORT_COMPLETE_MARKER}"

    return patched


def extract_section_titles_from_outline(outline_markdown: str, max_sections: int = 6) -> list[str]:
    """Extract ordered H2 section titles from markdown outline."""
    titles: list[str] = []
    seen: set[str] = set()
    for raw_line in (outline_markdown or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        title = ""
        if line.startswith("## "):
            title = line[3:].strip()
        elif line.startswith("- ## "):
            title = line[5:].strip()
        elif re.match(r"^\d+[\.\)]\s+.+", line):
            title = re.sub(r"^\d+[\.\)]\s+", "", line).strip()

        title = re.sub(r"[*_`#]", "", title).strip()
        title = re.sub(r"\s{2,}", " ", title)
        if not title:
            continue

        normalized = title.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        titles.append(title)
        if len(titles) >= max_sections:
            break

    return titles


def default_section_titles(language: str) -> list[str]:
    lang = (language or "").lower()
    if "chinese" in lang or lang.startswith("zh"):
        return [
            "执行摘要",
            "关键发现与证据",
            "风险与不确定性",
            "结论与行动建议",
        ]
    return [
        "Executive Summary",
        "Key Findings and Evidence",
        "Risks and Uncertainties",
        "Conclusion and Recommendations",
    ]


def _extract_h2_titles(markdown_text: str) -> list[str]:
    titles: list[str] = []
    for line in (markdown_text or "").splitlines():
        line = line.strip()
        if line.startswith("## "):
            titles.append(line[3:].strip())
    return titles


def _check_explicit_chain_sections(report: str) -> dict[str, Any]:
    headings = _extract_h2_titles(report or "")
    matched_positions: dict[str, int] = {}
    matched_titles: dict[str, str] = {}

    for idx, heading in enumerate(headings):
        normalized = heading.lower().strip()
        for rule in EXPLICIT_CHAIN_SECTION_RULES:
            rid = str(rule["id"])
            if rid in matched_positions:
                continue
            keywords = [str(k).lower() for k in (rule.get("keywords") or []) if str(k).strip()]
            if any(keyword in normalized for keyword in keywords):
                matched_positions[rid] = idx
                matched_titles[rid] = heading

    expected_ids = [str(rule["id"]) for rule in EXPLICIT_CHAIN_SECTION_RULES]
    missing_ids = [rid for rid in expected_ids if rid not in matched_positions]
    explicit_ok = len(missing_ids) == 0
    ordered_positions = [matched_positions[rid] for rid in expected_ids if rid in matched_positions]
    order_ok = explicit_ok and ordered_positions == sorted(ordered_positions)
    return {
        "explicit_ok": explicit_ok,
        "order_ok": order_ok,
        "missing_ids": missing_ids,
        "matched_titles": matched_titles,
    }


def _calculate_reference_url_ratio(report: str) -> float:
    _body, reference_section = _split_report_references(report or "")
    if not reference_section.strip():
        return 0.0
    lines = [
        line.strip()
        for line in reference_section.splitlines()
        if line.strip().startswith("-")
    ]
    if not lines:
        return 0.0
    with_url = 0
    for line in lines:
        if MARKDOWN_LINK_PATTERN.search(line) or URL_PATTERN.search(line):
            with_url += 1
    return round(with_url / max(1, len(lines)), 4)


def _extract_query_focus_tokens(query: str) -> list[str]:
    raw = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}", str(query or ""))
    stopwords = {
        "what", "when", "where", "which", "who", "why", "how", "the", "and", "for", "with",
        "from", "this", "that", "about", "report", "research", "analysis", "deep", "adaptive",
        "什么", "如何", "哪些", "关于", "研究", "报告", "分析",
    }
    deduped: list[str] = []
    seen: set[str] = set()
    for token in raw:
        key = token.lower().strip()
        if not key or key in stopwords:
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(token.strip())
    return deduped[:10]


def _extract_conclusion_block(report: str) -> str:
    if not report:
        return ""
    lines = (report or "").splitlines()
    start_idx = -1
    for idx, line in enumerate(lines):
        if CONCLUSION_SECTION_PATTERN.match(line.strip()):
            start_idx = idx
            break
    if start_idx < 0:
        return report
    collected: list[str] = []
    for idx in range(start_idx, len(lines)):
        line = lines[idx]
        if idx > start_idx and re.match(r"^#{1,6}\s+\S+", line.strip()):
            break
        collected.append(line)
    return "\n".join(collected).strip()


def evaluate_goal_alignment(report: str, query: str) -> tuple[bool, list[str]]:
    """
    Basic alignment checks for adaptive_deep quality KPI:
    - conclusion should mention core query focus
    - if query includes explicit time tokens, conclusion should address them
    - avoid methodology-only output without factual signals
    """
    issues: list[str] = []
    normalized_report = (report or "").lower()
    conclusion = _extract_conclusion_block(report).lower()

    focus_tokens = _extract_query_focus_tokens(query)
    if focus_tokens:
        token_hits = sum(
            1 for token in focus_tokens[:4]
            if token.lower() in conclusion or token.lower() in normalized_report
        )
        if token_hits == 0:
            issues.append("missing_query_focus_in_conclusion")

    query_time_tokens = re.findall(r"(?:19|20)\d{2}|(?:19|20)\d{2}年", str(query or ""))
    if query_time_tokens:
        has_time_in_conclusion = any(token in conclusion for token in [str(t).lower() for t in query_time_tokens])
        if not has_time_in_conclusion:
            issues.append("missing_timepoint_in_conclusion")

    methodology_markers = (
        "methodology", "framework", "future work", "generic approach", "high-level process",
        "方法论", "框架", "后续研究", "通用流程", "高层方法",
    )
    method_hits = sum(1 for token in methodology_markers if token in normalized_report)
    factual_signal = bool(MARKDOWN_LINK_PATTERN.search(report or "")) or bool(re.search(r"\b\d{2,}\b", report or ""))
    if method_hits >= 3 and not factual_signal:
        issues.append("methodology_only_without_facts")

    # Detect broad single-dimension bias in longer multi-section outputs.
    h2_count = len(_extract_h2_titles(report))
    if h2_count >= 3:
        coverage = assess_text_coverage([report or ""])
        if coverage.get("ratio", 0.0) < 0.35 and len(coverage.get("covered_ids") or []) <= 2:
            issues.append("single_dimension_bias")

    return len(issues) == 0, issues


def _validate_blueprint_section_coverage(report: str, report_blueprint: dict[str, Any]) -> tuple[bool, list[str]]:
    rendered_titles = {title.strip().lower() for title in _extract_h2_titles(report)}
    missing: list[str] = []
    specs = report_blueprint.get("section_specs") or []
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        title = str(spec.get("title") or "").strip()
        if not title:
            continue
        if title.lower() not in rendered_titles:
            missing.append(title)
    return len(missing) == 0, missing


def _evaluate_coverage_lens_report(report: str) -> dict[str, Any]:
    return assess_text_coverage([report or ""])


def _evaluate_chain_coverage_report(
    report: str,
    chain_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return assess_chain_coverage([report or ""], chain_steps=chain_steps)


async def _patch_coverage_gaps_once(
    *,
    report: str,
    query: str,
    context: str,
    missing_lenses: list[str],
    missing_chain_steps: list[str] | None,
    chain_steps: list[dict[str, Any]] | None,
    language: str,
    tone: Tone,
    source_policy: str,
    adaptive_style_instruction: str,
    cfg,
    agent_role_prompt: str,
    websocket,
    cost_callback: callable,
    finish_reason_callback: Callable[[str | None], None] | None = None,
    **kwargs,
) -> tuple[str, bool]:
    missing_text = ", ".join(missing_lenses or [])
    missing_chain_text = ", ".join(missing_chain_steps or [])
    prompt = f"""
COVERAGE_GAP_PATCH_TASK
The report below is missing analysis coverage in these lenses:
{missing_text}

The report also has potential narrative-chain gaps in:
{missing_chain_text or "none"}

Coverage lenses reference:
{coverage_lens_prompt_block()}

Coverage chain reference:
{coverage_chain_prompt_block(chain_steps)}

Task:
- Append concise markdown subsections to close missing lenses.
- Close chain gaps so the report reads from macro context to executable actions.
- Include explicit "Gap Notes" with reason + follow-up evidence action for any lens still unresolved.
- Keep existing report unchanged; append only incremental content.
- Keep recommendations decision-oriented and consistent with source policy `{source_policy}`.
- Add citations with markdown links where possible.
- Write in {language}; tone: {tone.value}.
- {adaptive_style_instruction}

Research query:
{query}

Context:
{context}

Current report:
{report}
"""
    patch = await _generate_report_once(
        cfg=cfg,
        agent_role_prompt=agent_role_prompt,
        messages=[
            {"role": "system", "content": f"{agent_role_prompt}"},
            {"role": "user", "content": prompt},
        ],
        websocket=websocket,
        cost_callback=cost_callback,
        finish_reason_callback=finish_reason_callback,
        **kwargs,
    )
    if not patch.strip():
        return report, False
    return f"{report.rstrip()}\n\n{patch.lstrip()}", True


async def _patch_adaptive_artifacts_once(
    *,
    report: str,
    query: str,
    context: str,
    language: str,
    tone: Tone,
    source_policy: str,
    adaptive_style_instruction: str,
    missing_chain_sections: list[str] | None,
    chain_order_issue: bool,
    cfg,
    agent_role_prompt: str,
    websocket,
    cost_callback: callable,
    finish_reason_callback: Callable[[str | None], None] | None = None,
    **kwargs,
) -> tuple[str, bool]:
    prompt = f"""
ADAPTIVE_ARTIFACT_PATCH_TASK
The report below is missing one or more required adaptive artifacts.

Add concise markdown-only content to ensure:
1) Explicit "Coverage Check" and/or "Gap Notes" subsection:
   - list covered analysis lenses,
   - list missing lenses/chain steps (if any),
   - give reason + follow-up evidence action.
2) A compact "Decision Sheet" table with columns:
   Option | Expected Value | Feasibility | Main Risk | First Experiment | Go/No-Go Signal
3) Explicit chain sections exist and follow this order:
   Industry -> Brand -> Demand -> Material -> Technology -> Execution
   Also include this mapping line exactly once:
   Chain Map: 行业→品牌→需求→材料→技术→落地

Rules:
- Append only incremental content; do not rewrite existing sections.
- Keep output decision-oriented and aligned to source policy `{source_policy}`.
- Use markdown links for citations where possible.
- Write in {language}; tone: {tone.value}.
- {adaptive_style_instruction}

Missing explicit chain sections:
{", ".join(missing_chain_sections or []) if missing_chain_sections else "none"}
Chain section order issue: {"yes" if chain_order_issue else "no"}

Research query:
{query}

Context:
{context}

Current report:
{report}
"""
    patch = await _generate_report_once(
        cfg=cfg,
        agent_role_prompt=agent_role_prompt,
        messages=[
            {"role": "system", "content": f"{agent_role_prompt}"},
            {"role": "user", "content": prompt},
        ],
        websocket=websocket,
        cost_callback=cost_callback,
        finish_reason_callback=finish_reason_callback,
        **kwargs,
    )
    if not patch.strip():
        return report, False
    return f"{report.rstrip()}\n\n{patch.lstrip()}", True


def _adaptive_style_instruction(report_style: str | None) -> str:
    style = (report_style or "strategic_report").strip().lower()
    if style == "consulting_brief":
        return (
            "Writing style: consulting brief. Keep sections crisp and executive-friendly, "
            "prefer concise bullets, include comparison tables for tradeoffs, and avoid long narrative detours."
        )
    return (
        "Writing style: strategic report. Build a coherent narrative from context to evidence to judgement, "
        "with explicit transitions and synthesis."
    )


def _extract_must_answer_questions(
    query: str,
    research_outline: dict[str, Any] | None,
    user_requirements: str | None,
) -> list[str]:
    questions: list[str] = []
    if isinstance(research_outline, dict):
        raw_items = research_outline.get("must_answer_questions") or []
        if isinstance(raw_items, list):
            for item in raw_items:
                text = str(item).strip()
                if text:
                    questions.append(text)
    if not questions and query.strip():
        questions.append(f"What are the most practical recommendations for: {query.strip()}?")
    requirements = (user_requirements or "").strip()
    if requirements:
        questions.append(f"How does the final recommendation satisfy this requirement: {requirements}?")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in questions:
        normalized = item.lower().strip()
        if normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(item)
    return deduped[:8]


async def _generate_blueprint_report(
    *,
    query: str,
    context: str,
    report_blueprint: dict[str, Any],
    user_requirements: str | None,
    report_type: str,
    report_style: str,
    source_policy: str,
    must_answer_questions: list[str] | None,
    report_format: str,
    tone: Tone,
    language: str,
    cfg,
    agent_role_prompt: str,
    websocket,
    cost_callback: callable,
    prompt_family: type[PromptFamily] | PromptFamily,
    finish_reason_callback: Callable[[str | None], None] | None = None,
    **kwargs,
) -> tuple[str, dict[str, Any]]:
    section_order = [str(item).strip() for item in (report_blueprint.get("section_order") or []) if str(item).strip()]
    section_specs = report_blueprint.get("section_specs") or []
    spec_map: dict[str, dict[str, Any]] = {}
    for spec in section_specs:
        if not isinstance(spec, dict):
            continue
        sid = str(spec.get("id") or "").strip()
        if sid:
            spec_map[sid] = spec

    if not section_order and spec_map:
        section_order = list(spec_map.keys())

    if not section_order:
        # Delegate to existing sectional fallback behavior when blueprint is empty.
        return await _generate_sectional_report(
            query=query,
            context=context,
            report_type=report_type,
            report_source="web",
            report_format=report_format,
            tone=tone,
            language=language,
            cfg=cfg,
            agent_role_prompt=agent_role_prompt,
            websocket=websocket,
            cost_callback=cost_callback,
            prompt_family=prompt_family,
            report_blueprint=report_blueprint,
            must_answer_questions=must_answer_questions,
            report_style=report_style,
            max_sections=6,
            context_char_limit=DEFAULT_MAX_OUTLINE_CONTEXT_CHARS,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )

    trimmed_context = _truncate_text(str(context), DEFAULT_MAX_OUTLINE_CONTEXT_CHARS)
    user_req = (user_requirements or "").strip()
    style_instruction = _adaptive_style_instruction(report_style)
    must_answer_questions = must_answer_questions or []
    must_answer_block = ""
    if must_answer_questions:
        must_answer_block = "\n".join([f"- {item}" for item in must_answer_questions if str(item).strip()])
    must_answer_context_block = (
        f"Must-answer questions:\n{must_answer_block}"
        if must_answer_block and report_type == "adaptive_deep"
        else ""
    )
    rendered_sections: list[str] = []
    rendered_ids: list[str] = []

    for idx, section_id in enumerate(section_order, start=1):
        spec = spec_map.get(section_id) or {}
        title = str(spec.get("title") or section_id).strip() or f"Section {idx}"
        purpose = str(spec.get("purpose") or spec.get("intent") or title).strip()
        required_evidence = [str(item).strip() for item in (spec.get("required_evidence_types") or []) if str(item).strip()]
        min_citations = max(0, int(spec.get("min_citations", 1) or 1))
        must_include = [str(item).strip() for item in (spec.get("must_include") or []) if str(item).strip()]

        section_prompt = f"""
BLUEPRINT_SECTION_TASK
Write ONE markdown section according to the blueprint constraints.

Topic: {query}
Section ID: {section_id}
Section Index: {idx}/{len(section_order)}
Section Title: {title}
Section Purpose: {purpose}
Required Evidence Types: {required_evidence or ["cross_source"]}
Minimum Citations: {min_citations}
Must Include Elements: {must_include or ["none"]}
User Requirements: {user_req or "none"}
Source Policy: {source_policy}
Report Type: {report_type}

Requirements:
- Start with exactly: ## {title}
- Keep analysis grounded in provided context.
- Add explicit citations using markdown links.
- If evidence is conflicting or incomplete, state uncertainty explicitly.
- Write in {language}, tone: {tone.value}.
- Avoid repeating content from other sections.
- {style_instruction}
{"- If this is a judgement section, explicitly answer all must-answer questions listed below." if report_type == "adaptive_deep" else ""}

Context:
{trimmed_context}
{must_answer_context_block}
"""
        section_md = await _generate_report_once(
            cfg=cfg,
            agent_role_prompt=agent_role_prompt,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {"role": "user", "content": section_prompt},
            ],
            websocket=websocket,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )
        if section_md.strip():
            rendered_sections.append(section_md.strip())
            rendered_ids.append(section_id)

    report = "\n\n".join(rendered_sections).strip()
    if not report.strip():
        return "", {"rendered_sections": 0, "section_order": section_order, "rendered_ids": []}

    if not CONCLUSION_SECTION_PATTERN.search(report):
        conclusion_extra = ""
        if report_type == "adaptive_deep" and must_answer_block:
            conclusion_extra = f"\n\nYou MUST explicitly answer these questions in the conclusion:\n{must_answer_block}\n"
        conclusion_text = await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {
                    "role": "user",
                    "content": prompt_family.generate_report_conclusion(
                        query=query,
                        report_content=report,
                        language=language,
                        report_format=report_format,
                    ) + conclusion_extra,
                },
            ],
            temperature=0.25,
            llm_provider=cfg.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=cfg.smart_token_limit,
            llm_kwargs=cfg.llm_kwargs,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )
        if conclusion_text.strip():
            report = f"{report.rstrip()}\n\n{conclusion_text.strip()}"

    if not REFERENCE_SECTION_PATTERN.search(report):
        report = f"{report.rstrip()}\n\n{_build_reference_section_from_report(report, language)}"

    coverage_ok, missing_sections = _validate_blueprint_section_coverage(report, report_blueprint)
    meta = {
        "rendered_sections": len(rendered_sections),
        "section_order": section_order,
        "rendered_ids": rendered_ids,
        "coverage_ok": coverage_ok,
        "missing_sections": missing_sections,
    }
    return report, meta


async def _generate_report_once(
    *,
    cfg,
    agent_role_prompt: str,
    messages: list[dict[str, str]],
    websocket,
    cost_callback: callable,
    finish_reason_callback: Callable[[str | None], None] | None = None,
    **kwargs
) -> str:
    try:
        return await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=messages,
            temperature=0.35,
            llm_provider=cfg.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=cfg.smart_token_limit,
            llm_kwargs=cfg.llm_kwargs,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs
        )
    except Exception:
        # Fallback path with single-message prompt for strict providers.
        fallback_content = "\n\n".join(message.get("content", "") for message in messages)
        return await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=[{"role": "user", "content": f"{agent_role_prompt}\n\n{fallback_content}"}],
            temperature=0.35,
            llm_provider=cfg.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=cfg.smart_token_limit,
            llm_kwargs=cfg.llm_kwargs,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs
        )


async def _generate_sectional_report(
    *,
    query: str,
    context: str,
    report_type: str,
    report_source: str,
    report_format: str,
    tone: Tone,
    language: str,
    cfg,
    agent_role_prompt: str,
    websocket,
    cost_callback: callable,
    prompt_family: type[PromptFamily] | PromptFamily,
    report_blueprint: dict[str, Any] | None,
    must_answer_questions: list[str] | None,
    report_style: str,
    max_sections: int,
    context_char_limit: int,
    finish_reason_callback: Callable[[str | None], None] | None = None,
    **kwargs,
) -> tuple[str, dict[str, Any]]:
    """
    Fallback strategy: generate outline then write section-by-section.
    Used only when full-report generation remains incomplete.
    """
    trimmed_context = _truncate_text(str(context), context_char_limit)
    style_instruction = _adaptive_style_instruction(report_style)
    must_answer_questions = must_answer_questions or []
    must_answer_block = "\n".join([f"- {item}" for item in must_answer_questions if str(item).strip()])
    must_answer_context_block = (
        f"Must-answer questions:\n{must_answer_block}"
        if must_answer_block and report_type == "adaptive_deep"
        else ""
    )
    outline_prompt = f"""
SECTIONAL_OUTLINE_TASK
Using the context below, produce a concise markdown outline with H2 headings only.
Return only headings in order, one per line, e.g.:
## Heading 1
## Heading 2

Topic: {query}
Context:
{trimmed_context}
Report Type: {report_type}
{style_instruction}
"""

    outline_markdown = await _generate_report_once(
        cfg=cfg,
        agent_role_prompt=agent_role_prompt,
        messages=[
            {"role": "system", "content": f"{agent_role_prompt}"},
            {"role": "user", "content": outline_prompt},
        ],
        websocket=websocket,
        cost_callback=cost_callback,
        finish_reason_callback=finish_reason_callback,
        **kwargs,
    )

    section_titles = extract_section_titles_from_outline(outline_markdown, max_sections=max_sections)
    if report_type == "adaptive_deep" and isinstance(report_blueprint, dict):
        blueprint_titles = [
            str(spec.get("title") or "").strip()
            for spec in (report_blueprint.get("section_specs") or [])
            if isinstance(spec, dict) and str(spec.get("title") or "").strip()
        ]
        if blueprint_titles:
            section_titles = blueprint_titles[:max_sections]
    if not section_titles:
        section_titles = default_section_titles(language)[:max_sections]

    sections: list[str] = []
    for idx, section_title in enumerate(section_titles, start=1):
        section_prompt = f"""
SECTIONAL_SECTION_TASK
Write ONLY one markdown section for this report.

Section Title: {section_title}
Section Index: {idx}/{len(section_titles)}
Topic: {query}

Requirements:
- Start with '## {section_title}'
- Use concise, evidence-backed analysis with in-text citations in markdown links.
- Do NOT include a references section unless this section itself is explicitly references.
- Keep this section self-contained and non-duplicative.
- Write in {language}.
- Use {tone.value} tone.
- {style_instruction}
{"- Explicitly connect each section to evidence quality and uncertainty." if report_type == "adaptive_deep" else ""}
{"- If this section is judgement/recommendation oriented, answer must-answer questions when relevant." if report_type == "adaptive_deep" else ""}

Context:
{trimmed_context}
{must_answer_context_block}
"""

        section_md = await _generate_report_once(
            cfg=cfg,
            agent_role_prompt=agent_role_prompt,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {"role": "user", "content": section_prompt},
            ],
            websocket=websocket,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )

        if section_md.strip():
            sections.append(section_md.strip())

    report = "\n\n".join(sections).strip()

    # Ensure conclusion exists.
    has_conclusion, _missing = evaluate_report_completeness(
        report,
        require_sections=True,
        require_marker=False,
    )
    if not CONCLUSION_SECTION_PATTERN.search(report):
        conclusion_extra = ""
        if report_type == "adaptive_deep" and must_answer_block:
            conclusion_extra = f"\n\nYou MUST explicitly answer these questions in the conclusion:\n{must_answer_block}\n"
        conclusion_text = await create_chat_completion(
            model=cfg.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {
                    "role": "user",
                    "content": prompt_family.generate_report_conclusion(
                        query=query,
                        report_content=report,
                        language=language,
                        report_format=report_format,
                    ) + conclusion_extra,
                },
            ],
            temperature=0.25,
            llm_provider=cfg.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=cfg.smart_token_limit,
            llm_kwargs=cfg.llm_kwargs,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )
        if conclusion_text.strip():
            report = f"{report.rstrip()}\n\n{conclusion_text.strip()}"

    # Ensure references exist.
    if not REFERENCE_SECTION_PATTERN.search(report):
        references_prompt = f"""
SECTIONAL_REFERENCES_TASK
Based on the draft report below, produce a deduplicated references section in markdown.

Requirements:
- Start with '## 参考文献' for Chinese, or '## References' otherwise.
- Include only sources actually referenced in the report.
- Each reference must contain one markdown hyperlink.
- Return only this references section.

Language: {language}
Draft report:
{report}
"""
        references_md = await _generate_report_once(
            cfg=cfg,
            agent_role_prompt=agent_role_prompt,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {"role": "user", "content": references_prompt},
            ],
            websocket=websocket,
            cost_callback=cost_callback,
            finish_reason_callback=finish_reason_callback,
            **kwargs,
        )
        if references_md.strip():
            report = f"{report.rstrip()}\n\n{references_md.strip()}"

    meta = {
        "outline_raw_length": len(outline_markdown or ""),
        "section_count": len(section_titles),
        "section_titles": section_titles,
        "assembled_sections": len(sections),
        "completion_check_hint": has_conclusion,
    }
    return report, meta


async def write_report_introduction(
    query: str,
    context: str,
    agent_role_prompt: str,
    config: Config,
    websocket=None,
    cost_callback: callable = None,
    prompt_family: type[PromptFamily] | PromptFamily = PromptFamily,
    **kwargs
) -> str:
    """
    Generate an introduction for the report.

    Args:
        query (str): The research query.
        context (str): Context for the report.
        role (str): The role of the agent.
        config (Config): Configuration object.
        websocket: WebSocket connection for streaming output.
        cost_callback (callable, optional): Callback for calculating LLM costs.
        prompt_family: Family of prompts

    Returns:
        str: The generated introduction.
    """
    try:
        introduction = await create_chat_completion(
            model=config.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {"role": "user", "content": prompt_family.generate_report_introduction(
                    question=query,
                    research_summary=context,
                    language=config.language
                )},
            ],
            temperature=0.25,
            llm_provider=config.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=config.smart_token_limit,
            llm_kwargs=config.llm_kwargs,
            cost_callback=cost_callback,
            **kwargs
        )
        return introduction
    except Exception as e:
        logger.error(f"Error in generating report introduction: {e}")
    return ""


async def write_conclusion(
    query: str,
    context: str,
    agent_role_prompt: str,
    config: Config,
    websocket=None,
    cost_callback: callable = None,
    prompt_family: type[PromptFamily] | PromptFamily = PromptFamily,
    **kwargs
) -> str:
    """
    Write a conclusion for the report.

    Args:
        query (str): The research query.
        context (str): Context for the report.
        role (str): The role of the agent.
        config (Config): Configuration object.
        websocket: WebSocket connection for streaming output.
        cost_callback (callable, optional): Callback for calculating LLM costs.
        prompt_family: Family of prompts

    Returns:
        str: The generated conclusion.
    """
    try:
        conclusion = await create_chat_completion(
            model=config.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{agent_role_prompt}"},
                {
                    "role": "user",
                    "content": prompt_family.generate_report_conclusion(query=query,
                                                                        report_content=context,
                                                                        language=config.language),
                },
            ],
            temperature=0.25,
            llm_provider=config.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=config.smart_token_limit,
            llm_kwargs=config.llm_kwargs,
            cost_callback=cost_callback,
            **kwargs
        )
        return conclusion
    except Exception as e:
        logger.error(f"Error in writing conclusion: {e}")
    return ""


async def summarize_url(
    url: str,
    content: str,
    role: str,
    config: Config,
    websocket=None,
    cost_callback: callable = None,
    **kwargs
) -> str:
    """
    Summarize the content of a URL.

    Args:
        url (str): The URL to summarize.
        content (str): The content of the URL.
        role (str): The role of the agent.
        config (Config): Configuration object.
        websocket: WebSocket connection for streaming output.
        cost_callback (callable, optional): Callback for calculating LLM costs.

    Returns:
        str: The summarized content.
    """
    try:
        summary = await create_chat_completion(
            model=config.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{role}"},
                {"role": "user", "content": f"Summarize the following content from {url}:\n\n{content}"},
            ],
            temperature=0.25,
            llm_provider=config.smart_llm_provider,
            stream=True,
            websocket=websocket,
            max_tokens=config.smart_token_limit,
            llm_kwargs=config.llm_kwargs,
            cost_callback=cost_callback,
            **kwargs
        )
        return summary
    except Exception as e:
        logger.error(f"Error in summarizing URL: {e}")
    return ""


async def generate_draft_section_titles(
    query: str,
    current_subtopic: str,
    context: str,
    role: str,
    config: Config,
    websocket=None,
    cost_callback: callable = None,
    prompt_family: type[PromptFamily] | PromptFamily = PromptFamily,
    **kwargs
) -> List[str]:
    """
    Generate draft section titles for the report.

    Args:
        query (str): The research query.
        context (str): Context for the report.
        role (str): The role of the agent.
        config (Config): Configuration object.
        websocket: WebSocket connection for streaming output.
        cost_callback (callable, optional): Callback for calculating LLM costs.
        prompt_family: Family of prompts

    Returns:
        List[str]: A list of generated section titles.
    """
    try:
        section_titles = await create_chat_completion(
            model=config.smart_llm_model,
            messages=[
                {"role": "system", "content": f"{role}"},
                {"role": "user", "content": prompt_family.generate_draft_titles_prompt(
                    current_subtopic, query, context)},
            ],
            temperature=0.25,
            llm_provider=config.smart_llm_provider,
            stream=True,
            websocket=None,
            max_tokens=config.smart_token_limit,
            llm_kwargs=config.llm_kwargs,
            cost_callback=cost_callback,
            **kwargs
        )
        return section_titles.split("\n")
    except Exception as e:
        logger.error(f"Error in generating draft section titles: {e}")
    return []


async def generate_report(
    query: str,
    context,
    agent_role_prompt: str,
    report_type: str,
    tone: Tone,
    report_source: str,
    websocket,
    cfg,
    main_topic: str = "",
    existing_headers: list = [],
    relevant_written_contents: list = [],
    cost_callback: callable = None,
    custom_prompt: str = "", # This can be any prompt the user chooses with the context
    headers=None,
    prompt_family: type[PromptFamily] | PromptFamily = PromptFamily,
    available_images: list = None,
    report_blueprint: dict | None = None,
    research_outline: dict | None = None,
    user_requirements: str | None = None,
    report_style: str = "strategic_report",
    source_policy: str = "medium_tier",
    generation_metadata_callback: Callable[[dict], None] | None = None,
    **kwargs
):
    """
    generates the final report
    Args:
        query:
        context:
        agent_role_prompt:
        report_type:
        websocket:
        tone:
        cfg:
        main_topic:
        existing_headers:
        relevant_written_contents:
        cost_callback:
        prompt_family: Family of prompts
        available_images: Pre-generated images to embed in the report

    Returns:
        report:

    """
    available_images = available_images or []
    generate_prompt = get_prompt_by_report_type(report_type, prompt_family)
    report = ""
    adaptive_mode = report_type == "adaptive_deep"
    must_answer_questions = _extract_must_answer_questions(
        query=query,
        research_outline=research_outline,
        user_requirements=user_requirements,
    )
    adaptive_style_instruction = _adaptive_style_instruction(report_style)

    if report_type == "subtopic_report":
        content = f"{generate_prompt(query, existing_headers, relevant_written_contents, main_topic, context, report_format=cfg.report_format, tone=tone, total_words=cfg.total_words, language=cfg.language)}"
    elif custom_prompt:
        content = f"{custom_prompt}\n\nContext: {context}"
    else:
        if adaptive_mode:
            content = f"{generate_prompt(query, context, report_source, report_format=cfg.report_format, tone=tone, total_words=cfg.total_words, language=cfg.language, report_style=report_style, must_answer_questions=must_answer_questions, source_policy=source_policy)}"
        else:
            content = f"{generate_prompt(query, context, report_source, report_format=cfg.report_format, tone=tone, total_words=cfg.total_words, language=cfg.language)}"
    
    guard_enabled = bool(getattr(cfg, "report_completion_guard_enabled", True))
    guard_max_attempts = max(0, int(getattr(cfg, "report_completion_max_attempts", 2)))
    guard_require_marker = bool(getattr(cfg, "report_completion_require_marker", True))
    sectional_fallback_enabled = bool(getattr(cfg, "report_sectional_fallback_enabled", True))
    sectional_max_sections = max(2, int(getattr(cfg, "report_sectional_max_sections", 6)))
    sectional_context_chars = max(5000, int(getattr(cfg, "report_sectional_context_chars", DEFAULT_MAX_OUTLINE_CONTEXT_CHARS)))
    sectional_preflight_enabled = bool(getattr(cfg, "report_sectional_preflight_enabled", True))
    sectional_preflight_min_context_chars = max(2000, int(getattr(cfg, "report_sectional_preflight_min_context_chars", 14000)))
    sectional_timeout_seconds = max(20, int(getattr(cfg, "report_sectional_timeout_seconds", 120)))
    sectional_fallback_reduced_max_sections = max(2, int(getattr(cfg, "report_sectional_fallback_reduced_max_sections", 4)))
    sectional_fallback_reduced_context_chars = max(5000, int(getattr(cfg, "report_sectional_fallback_reduced_context_chars", 12000)))
    coverage_enhancer_enabled = bool(getattr(cfg, "adaptive_coverage_enhancer_enabled", False))
    coverage_min_ratio = max(0.0, min(1.0, float(getattr(cfg, "adaptive_coverage_min_ratio", 0.75))))
    coverage_profile = str(getattr(cfg, "adaptive_coverage_profile", "balanced") or "balanced").strip().lower()
    chain_enforcer_enabled = bool(getattr(cfg, "adaptive_chain_enforcer_enabled", True))
    chain_min_ratio = max(0.0, min(1.0, float(getattr(cfg, "adaptive_chain_min_ratio", 0.90))))
    chain_require_explicit_sections = bool(getattr(cfg, "adaptive_chain_require_explicit_sections", True))
    chain_patch_max_rounds = max(1, int(getattr(cfg, "adaptive_chain_patch_max_rounds", 1)))
    chain_profile_mode = str(getattr(cfg, "adaptive_chain_profile_mode", "dual") or "dual").strip().lower()
    chain_industry_profile = str(getattr(cfg, "adaptive_chain_industry_profile", "auto") or "auto").strip().lower()
    chain_steps = resolve_chain_steps(
        profile_mode=chain_profile_mode,
        industry_profile=chain_industry_profile,
        query=str(query or ""),
    )
    reference_url_min_ratio = max(0.0, min(1.0, float(getattr(cfg, "adaptive_reference_url_min_ratio", 0.80))))
    require_sections = report_type != "subtopic_report"
    context_text = str(context)

    preflight_condition = (
        sectional_fallback_enabled
        and sectional_preflight_enabled
        and require_sections
        and (
            report_type in {"deep", "adaptive_deep"}
            or len(context_text) >= sectional_preflight_min_context_chars
        )
    )

    # Add available images instruction if images were pre-generated
    if available_images:
        images_info = "\n".join([
            f"- Image {i+1}: ![{img.get('title', img.get('alt_text', 'Illustration'))}]({img['url']}) - {img.get('section_hint', 'General')}"
            for i, img in enumerate(available_images)
        ])
        content += f"""

AVAILABLE IMAGES:
You have the following pre-generated images available. Embed them in relevant sections of your report using the exact markdown syntax provided:

{images_info}

Place each image on its own line after the relevant section header or paragraph. Use all available images where they add value to the content."""
    if guard_enabled:
        content += f"""

OUTPUT COMPLETION RULES:
- You MUST include a clear conclusion section.
- You MUST include a references/sources section.
- End the full report with the exact marker: {REPORT_COMPLETE_MARKER}
"""
    if adaptive_mode:
        must_answer_block = "\n".join([f"- {item}" for item in must_answer_questions if str(item).strip()])
        must_answer_constraint_block = f"Must-answer questions:\n{must_answer_block}" if must_answer_block else ""
        content += f"""

ADAPTIVE_DEEP_WRITING_CONSTRAINTS:
- Use adaptive evidence flow: foundation -> evidence -> judgement.
- Explicitly state conflicts, uncertainty, and unresolved verification items where applicable.
- Avoid generic methodology-only output that does not answer the research objective.
- Maintain broad lens coverage (scope, baseline, options, demand/stakeholders, economics, risk/compliance, benchmark, actions).
- Preserve a coherent chain: macro context -> focal baseline -> demand -> supply/input constraints -> options -> execution.
- Use explicit chain sections (or clear synonyms) for:
  Industry -> Brand -> Demand -> Material -> Technology -> Execution.
- Include one explicit mapping line in the report:
  Chain Map: 行业→品牌→需求→材料→技术→落地
- Add embedded "Coverage Check" / "Gap Notes" when some lenses are weakly covered.
- Include one compact decision table: Option | Expected Value | Feasibility | Main Risk | First Experiment | Go/No-Go Signal.
- {adaptive_style_instruction}
- Source policy is `{source_policy}`. Critical conclusions should prioritize higher-trust citations.
- Reference hygiene: avoid placeholders like "链接/来源/source"; references must be valid markdown links.
{must_answer_constraint_block}
"""

    finish_reasons: list[str] = []

    def _capture_finish_reason(reason: str | None) -> None:
        if reason:
            finish_reasons.append(str(reason))

    sectional_meta: dict[str, Any] = {}
    blueprint_meta: dict[str, Any] = {}
    used_blueprint_mode = False
    used_sectional_fallback = False
    used_sectional_preflight = False
    preflight_transport_failed = False
    preflight_error = ""
    fallback_max_sections = sectional_max_sections
    fallback_context_chars = sectional_context_chars
    emergency_completion_applied = False

    if preflight_condition:
        try:
            sectional_report, sectional_meta = await asyncio.wait_for(
                _generate_sectional_report(
                    query=query,
                    context=context_text,
                    report_type=report_type,
                    report_source=report_source,
                    report_format=cfg.report_format,
                    tone=tone,
                    language=cfg.language,
                    cfg=cfg,
                    agent_role_prompt=agent_role_prompt,
                    websocket=websocket,
                    cost_callback=cost_callback,
                    prompt_family=prompt_family,
                    report_blueprint=report_blueprint,
                    must_answer_questions=must_answer_questions,
                    report_style=report_style,
                    max_sections=sectional_max_sections,
                    context_char_limit=sectional_context_chars,
                    finish_reason_callback=_capture_finish_reason,
                    **kwargs,
                ),
                timeout=sectional_timeout_seconds,
            )
            if sectional_report.strip():
                report = sectional_report.strip()
                used_sectional_preflight = True
                if guard_require_marker and REPORT_COMPLETE_MARKER not in report:
                    report = f"{report}\n\n{REPORT_COMPLETE_MARKER}"
        except Exception as e:
            preflight_error = str(e)
            preflight_transport_failed = isinstance(e, asyncio.TimeoutError) or _is_transport_error(e)
            if preflight_transport_failed:
                fallback_max_sections = min(sectional_max_sections, sectional_fallback_reduced_max_sections)
                fallback_context_chars = min(sectional_context_chars, sectional_fallback_reduced_context_chars)
            logger.error(f"Error in sectional preflight generation: {e}")

    if report_blueprint and not report.strip():
        try:
            blueprint_report, blueprint_meta = await _generate_blueprint_report(
                query=query,
                context=context_text,
                report_blueprint=report_blueprint,
                user_requirements=user_requirements,
                report_type=report_type,
                report_style=report_style,
                source_policy=source_policy,
                must_answer_questions=must_answer_questions,
                report_format=cfg.report_format,
                tone=tone,
                language=cfg.language,
                cfg=cfg,
                agent_role_prompt=agent_role_prompt,
                websocket=websocket,
                cost_callback=cost_callback,
                prompt_family=prompt_family,
                finish_reason_callback=_capture_finish_reason,
                **kwargs,
            )
            if blueprint_report.strip():
                report = blueprint_report.strip()
                used_blueprint_mode = True
                if guard_require_marker and REPORT_COMPLETE_MARKER not in report:
                    report = f"{report}\n\n{REPORT_COMPLETE_MARKER}"
        except Exception as e:
            logger.error(f"Error in blueprint-driven generation: {e}")

    continuation_attempts = 0
    initial_complete = False
    missing_requirements: list[str] = []

    if not report.strip():
        messages = [
            {"role": "system", "content": f"{agent_role_prompt}"},
            {"role": "user", "content": content},
        ]

        try:
            report = await _generate_report_once(
                cfg=cfg,
                agent_role_prompt=agent_role_prompt,
                messages=messages,
                websocket=websocket,
                cost_callback=cost_callback,
                finish_reason_callback=_capture_finish_reason,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Error in generate_report initial call: {e}")
            report = ""

    initial_complete, missing_requirements = evaluate_report_completeness(
        report,
        require_sections=require_sections,
        require_marker=guard_require_marker and guard_enabled,
    )

    if guard_enabled and not initial_complete:
        for attempt in range(1, guard_max_attempts + 1):
            continuation_attempts = attempt
            missing_text = ", ".join(missing_requirements) if missing_requirements else "none"
            adaptive_continuation_rules = ""
            if adaptive_mode:
                must_answer_block = "\n".join([f"- {item}" for item in must_answer_questions if str(item).strip()])
                must_answer_completion_rule = (
                    f"- Explicitly answer these must-answer questions in the completion:\n{must_answer_block}"
                    if must_answer_block
                    else ""
                )
                adaptive_continuation_rules = f"""
- Maintain adaptive structure: foundation evidence, evidence synthesis, judgement and recommendations.
- Keep evidence quality explicit; do not rely solely on low-tier claims for key conclusions.
- Preserve narrative chain from macro context to execution actions.
- Keep references clean: no placeholder entries, use valid markdown links.
- {adaptive_style_instruction}
{must_answer_completion_rule}
"""
            continuation_prompt = f"""
The prior report appears incomplete or truncated.
Continue the existing report without repeating already written content.

Missing requirements to satisfy: {missing_text}

Current partial report:
{report}

Rules:
- Continue from the unfinished point.
- Preserve original markdown style and headings.
- Add the missing sections if absent.
- End your continuation with the exact marker: {REPORT_COMPLETE_MARKER}
- Return ONLY markdown continuation text to append.
{adaptive_continuation_rules}
"""
            try:
                continuation = await _generate_report_once(
                    cfg=cfg,
                    agent_role_prompt=agent_role_prompt,
                    messages=[
                        {"role": "system", "content": f"{agent_role_prompt}"},
                        {"role": "user", "content": continuation_prompt},
                    ],
                    websocket=websocket,
                    cost_callback=cost_callback,
                    finish_reason_callback=_capture_finish_reason,
                    **kwargs,
                )
            except Exception as e:
                logger.error(f"Error in generate_report continuation attempt {attempt}: {e}")
                continuation = ""

            if continuation.strip():
                report = f"{report.rstrip()}\n\n{continuation.lstrip()}"

            completed, missing_requirements = evaluate_report_completeness(
                report,
                require_sections=require_sections,
                require_marker=guard_require_marker and guard_enabled,
            )
            if completed:
                break

    final_complete, final_missing = evaluate_report_completeness(
        report,
        require_sections=require_sections,
        require_marker=guard_require_marker and guard_enabled,
    )
    if report_blueprint:
        coverage_ok, missing_sections = _validate_blueprint_section_coverage(report, report_blueprint)
        if not coverage_ok:
            final_complete = False
            final_missing.extend([f"missing_blueprint_section:{title}" for title in missing_sections])
    allow_sectional_fallback = sectional_fallback_enabled and not preflight_transport_failed
    if guard_enabled and require_sections and not final_complete and allow_sectional_fallback:
        try:
            sectional_report, sectional_meta = await asyncio.wait_for(
                _generate_sectional_report(
                    query=query,
                    context=context_text,
                    report_type=report_type,
                    report_source=report_source,
                    report_format=cfg.report_format,
                    tone=tone,
                    language=cfg.language,
                    cfg=cfg,
                    agent_role_prompt=agent_role_prompt,
                    websocket=websocket,
                    cost_callback=cost_callback,
                    prompt_family=prompt_family,
                    report_blueprint=report_blueprint,
                    must_answer_questions=must_answer_questions,
                    report_style=report_style,
                    max_sections=fallback_max_sections,
                    context_char_limit=fallback_context_chars,
                    finish_reason_callback=_capture_finish_reason,
                    **kwargs,
                ),
                timeout=sectional_timeout_seconds,
            )
            if sectional_report.strip():
                report = sectional_report.strip()
                used_sectional_fallback = True
                if guard_require_marker and REPORT_COMPLETE_MARKER not in report:
                    report = f"{report}\n\n{REPORT_COMPLETE_MARKER}"
                final_complete, final_missing = evaluate_report_completeness(
                    report,
                    require_sections=require_sections,
                    require_marker=guard_require_marker and guard_enabled,
                )
        except Exception as e:
            logger.error(f"Error in sectional fallback generation: {e}")

    if guard_enabled and not final_complete:
        report = _apply_emergency_completion(
            report=report,
            missing_requirements=final_missing,
            language=cfg.language,
            require_marker=guard_require_marker and guard_enabled,
        )
        emergency_completion_applied = True
        final_complete, final_missing = evaluate_report_completeness(
            report,
            require_sections=require_sections,
            require_marker=guard_require_marker and guard_enabled,
        )

    marker_present = REPORT_COMPLETE_MARKER in report
    report = _strip_completion_marker(report)
    coverage_patch_applied = False
    chain_patch_applied = False
    adaptive_artifact_patch_applied = False
    coverage_report = _evaluate_coverage_lens_report(report) if adaptive_mode else {"ratio": 1.0, "missing_labels": []}
    chain_report = (
        _evaluate_chain_coverage_report(report, chain_steps=chain_steps)
        if adaptive_mode else {"ratio": 1.0, "missing_labels": []}
    )
    chain_patch_reason = "none"
    if adaptive_mode and (coverage_enhancer_enabled or chain_enforcer_enabled) and (
        coverage_report.get("ratio", 0.0) < coverage_min_ratio
        or chain_report.get("ratio", 0.0) < chain_min_ratio
        or bool(chain_report.get("missing_ids"))
    ):
        report, coverage_patch_applied = await _patch_coverage_gaps_once(
            report=report,
            query=query,
            context=context_text,
            missing_lenses=list(coverage_report.get("missing_labels") or []),
            missing_chain_steps=list(chain_report.get("missing_labels") or []),
            chain_steps=chain_steps,
            language=cfg.language,
            tone=tone,
            source_policy=source_policy,
            adaptive_style_instruction=adaptive_style_instruction,
            cfg=cfg,
            agent_role_prompt=agent_role_prompt,
            websocket=websocket,
            cost_callback=cost_callback,
            finish_reason_callback=_capture_finish_reason,
            **kwargs,
        )
        coverage_report = _evaluate_coverage_lens_report(report)
        chain_report = _evaluate_chain_coverage_report(report, chain_steps=chain_steps)
        chain_patch_applied = True
        chain_patch_reason = "coverage_or_chain_gap"

    chain_section_status = _check_explicit_chain_sections(report)
    missing_coverage_check = not bool(COVERAGE_CHECK_PATTERN.search(report or ""))
    missing_decision_sheet = not bool(DECISION_SHEET_PATTERN.search(report or ""))
    artifact_patch_round = 0
    while adaptive_mode and artifact_patch_round < chain_patch_max_rounds:
        needs_artifact_patch = bool(missing_coverage_check or missing_decision_sheet)
        if chain_require_explicit_sections:
            needs_artifact_patch = needs_artifact_patch or not bool(
                chain_section_status.get("explicit_ok") and chain_section_status.get("order_ok")
            )
        if not needs_artifact_patch:
            break

        report, adaptive_artifact_patch_applied = await _patch_adaptive_artifacts_once(
            report=report,
            query=query,
            context=context_text,
            language=cfg.language,
            tone=tone,
            source_policy=source_policy,
            adaptive_style_instruction=adaptive_style_instruction,
            missing_chain_sections=list(chain_section_status.get("missing_ids") or []),
            chain_order_issue=not bool(chain_section_status.get("order_ok")),
            cfg=cfg,
            agent_role_prompt=agent_role_prompt,
            websocket=websocket,
            cost_callback=cost_callback,
            finish_reason_callback=_capture_finish_reason,
            **kwargs,
        )
        artifact_patch_round += 1
        missing_coverage_check = not bool(COVERAGE_CHECK_PATTERN.search(report or ""))
        missing_decision_sheet = not bool(DECISION_SHEET_PATTERN.search(report or ""))
        coverage_report = _evaluate_coverage_lens_report(report)
        chain_report = _evaluate_chain_coverage_report(report, chain_steps=chain_steps)
        chain_section_status = _check_explicit_chain_sections(report)
        chain_patch_reason = "missing_artifacts_or_explicit_chain_sections"

    coverage_ratio = float(coverage_report.get("ratio", 0.0))
    coverage_missing_lenses = list(coverage_report.get("missing_labels") or [])
    coverage_ok = coverage_ratio >= coverage_min_ratio if (adaptive_mode and coverage_enhancer_enabled) else True
    chain_coverage_ratio = float(chain_report.get("ratio", 0.0)) if adaptive_mode else 1.0
    chain_missing_steps = list(chain_report.get("missing_labels") or []) if adaptive_mode else []
    chain_coverage_ok = (
        chain_coverage_ratio >= chain_min_ratio and not bool(chain_report.get("missing_ids"))
        if (adaptive_mode and chain_enforcer_enabled) else True
    )

    reference_hygiene_meta = {
        "reference_url_count": 0,
        "reference_hygiene_changed": False,
        "reference_had_existing_section": False,
        "reference_url_ratio": 0.0,
        "reference_url_ratio_ok": True,
    }
    report_source_normalized = str(report_source or "").strip().lower()
    if "web" in report_source_normalized:
        report, reference_hygiene_meta = _sanitize_reference_hygiene(
            report,
            cfg.language,
            extra_context=context_text,
        )
        reference_ratio = _calculate_reference_url_ratio(report)
        reference_hygiene_meta["reference_url_ratio"] = reference_ratio
        reference_hygiene_meta["reference_url_ratio_ok"] = reference_ratio >= reference_url_min_ratio
    else:
        reference_ratio = 1.0

    explicit_chain_sections_ok = bool(chain_section_status.get("explicit_ok"))
    chain_section_order_ok = bool(chain_section_status.get("order_ok"))

    goal_alignment_ok = True
    goal_alignment_issues: list[str] = []
    if adaptive_mode:
        goal_alignment_ok, goal_alignment_issues = evaluate_goal_alignment(report, query)
    blueprint_coverage_ok = True
    blueprint_missing_sections: list[str] = []
    if report_blueprint:
        blueprint_coverage_ok, blueprint_missing_sections = _validate_blueprint_section_coverage(report, report_blueprint)

    if generation_metadata_callback:
        generation_metadata_callback(
            {
                "guard_enabled": guard_enabled,
                "initial_complete": initial_complete,
                "final_complete": final_complete,
                "continuation_attempts": continuation_attempts,
                "missing_requirements": final_missing,
                "marker_present": marker_present,
                "finish_reasons": finish_reasons,
                "used_sectional_fallback": used_sectional_fallback,
                "used_sectional_preflight": used_sectional_preflight,
                "sectional_preflight_condition": preflight_condition,
                "sectional_preflight_transport_failed": preflight_transport_failed,
                "sectional_preflight_error": preflight_error,
                "emergency_completion_applied": emergency_completion_applied,
                "sectional_fallback": sectional_meta,
                "used_blueprint_mode": used_blueprint_mode,
                "blueprint_generation": blueprint_meta,
                "blueprint_coverage_ok": blueprint_coverage_ok,
                "blueprint_missing_sections": blueprint_missing_sections,
                "goal_alignment_ok": goal_alignment_ok,
                "goal_alignment_issues": goal_alignment_issues,
                "coverage_enhancer_enabled": coverage_enhancer_enabled,
                "coverage_profile": coverage_profile,
                "coverage_min_ratio": coverage_min_ratio,
                "coverage_ratio": coverage_ratio,
                "coverage_ok": coverage_ok,
                "coverage_missing_lenses": coverage_missing_lenses,
                "coverage_patch_applied": coverage_patch_applied,
                "chain_min_ratio": chain_min_ratio,
                "chain_coverage_ratio": chain_coverage_ratio,
                "chain_coverage_ok": chain_coverage_ok,
                "chain_missing_steps": chain_missing_steps,
                "chain_patch_applied": chain_patch_applied,
                "chain_patch_reason": chain_patch_reason,
                "explicit_chain_sections_ok": explicit_chain_sections_ok,
                "chain_section_order_ok": chain_section_order_ok,
                "adaptive_artifact_patch_applied": adaptive_artifact_patch_applied,
                "missing_coverage_check": missing_coverage_check,
                "missing_decision_sheet": missing_decision_sheet,
                "report_style": report_style,
                "source_policy": source_policy,
                "reference_hygiene": reference_hygiene_meta,
                "reference_url_ratio": reference_ratio,
            }
        )

    return report
