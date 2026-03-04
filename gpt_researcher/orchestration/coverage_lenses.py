"""Reusable coverage-lens heuristics for adaptive deep research."""

from __future__ import annotations

from typing import Any


COVERAGE_LENSES: list[dict[str, Any]] = [
    {
        "id": "scope_constraints",
        "label": "Problem framing and constraints",
        "keywords": [
            "scope", "boundary", "constraint", "assumption", "framing",
            "范围", "边界", "约束", "假设", "问题框定",
        ],
    },
    {
        "id": "current_baseline",
        "label": "Current state and baseline evidence",
        "keywords": [
            "current state", "baseline", "status quo", "existing", "as-is",
            "现状", "基线", "存量", "当前",
        ],
    },
    {
        "id": "option_space",
        "label": "Option space and comparative paths",
        "keywords": [
            "option", "path", "route", "alternative", "compare", "comparison", "tradeoff",
            "方案", "路径", "路线", "替代", "对比", "权衡",
        ],
    },
    {
        "id": "stakeholders_demand",
        "label": "Stakeholders and demand signals",
        "keywords": [
            "stakeholder", "user", "customer", "buyer", "demand", "persona",
            "利益相关方", "用户", "客户", "买手", "需求", "人群",
        ],
    },
    {
        "id": "economics_feasibility",
        "label": "Economics and operational feasibility",
        "keywords": [
            "cost", "budget", "roi", "economics", "capex", "opex", "timeline", "capacity", "feasibility",
            "成本", "预算", "回报", "经济性", "投入", "排期", "产能", "可行性",
        ],
    },
    {
        "id": "risk_regulatory",
        "label": "Risk, compliance, and uncertainty",
        "keywords": [
            "risk", "compliance", "regulation", "uncertainty", "legal", "governance", "conflict",
            "风险", "合规", "监管", "不确定性", "法律", "治理", "冲突",
        ],
    },
    {
        "id": "competition_benchmark",
        "label": "Competition, substitutes, and benchmarks",
        "keywords": [
            "competition", "competitor", "benchmark", "substitute", "alternative provider", "peer",
            "竞争", "竞品", "基准", "替代", "对手", "同业",
        ],
    },
    {
        "id": "roadmap_actions",
        "label": "Roadmap, priorities, and actions",
        "keywords": [
            "roadmap", "milestone", "priority", "action", "implementation", "next step", "execution",
            "路线图", "里程碑", "优先级", "行动", "落地", "下一步", "执行",
        ],
    },
]


# Chain profiles are explicit "industry -> brand -> demand -> material -> technology -> execution".
CHAIN_PROFILES: dict[str, list[dict[str, Any]]] = {
    "generic": [
        {
            "id": "industry_context",
            "label": "Industry context and external trajectory",
            "keywords": [
                "industry", "macro", "market context", "trend", "category trajectory",
                "行业", "宏观", "市场环境", "趋势", "赛道",
            ],
        },
        {
            "id": "brand_positioning",
            "label": "Brand/entity positioning and baseline",
            "keywords": [
                "brand strategy", "entity baseline", "current portfolio", "positioning", "operating model",
                "品牌战略", "品牌基线", "产品组合", "定位", "经营模式",
            ],
        },
        {
            "id": "demand_signals",
            "label": "Demand and stakeholder signals",
            "keywords": [
                "demand", "stakeholder", "consumer", "buyer requirement", "user signal",
                "需求", "利益相关方", "消费者", "采购要求", "用户信号",
            ],
        },
        {
            "id": "material_constraints",
            "label": "Materials/inputs and upstream constraints",
            "keywords": [
                "material", "raw material", "upstream", "input constraint", "supply chain",
                "材料", "原材料", "上游", "输入约束", "供应链",
            ],
        },
        {
            "id": "technology_path",
            "label": "Technology/process pathways",
            "keywords": [
                "technology", "process", "manufacturing method", "technical route", "engineering",
                "技术", "工艺", "制造方法", "技术路径", "工程",
            ],
        },
        {
            "id": "execution_rollout",
            "label": "Execution rollout and decision actions",
            "keywords": [
                "roadmap", "rollout", "milestone", "pilot", "implementation", "decision gate",
                "路线图", "落地", "里程碑", "试点", "实施", "决策门",
            ],
        },
    ],
    "apparel_supply_chain": [
        {
            "id": "industry_context",
            "label": "Apparel industry context and external trajectory",
            "keywords": [
                "apparel industry", "fashion retail", "garment market", "textile trend", "industry outlook",
                "服装行业", "时尚零售", "成衣市场", "纺织趋势", "行业展望",
            ],
        },
        {
            "id": "brand_positioning",
            "label": "Brand/group strategy and product baseline",
            "keywords": [
                "brand strategy", "group strategy", "product baseline", "core assortment", "lifecycle",
                "品牌战略", "集团战略", "产品基线", "核心品类", "商品结构",
            ],
        },
        {
            "id": "demand_signals",
            "label": "Consumer scenarios and demand signals",
            "keywords": [
                "consumer demand", "wearing scenario", "comfort demand", "buyer signal", "merchandising requirement",
                "消费需求", "穿着场景", "舒适需求", "买手信号", "商品企划要求",
            ],
        },
        {
            "id": "material_constraints",
            "label": "Fiber/material inputs and upstream constraints",
            "keywords": [
                "fiber", "yarn", "raw material", "dyeing", "finishing", "upstream capacity",
                "纤维", "纱线", "原材料", "染整", "后整理", "上游产能",
            ],
        },
        {
            "id": "technology_path",
            "label": "Fabric/process technology pathways",
            "keywords": [
                "fabric technology", "weaving", "knitting", "process route", "functional finishing",
                "面料技术", "机织", "针织", "工艺路线", "功能整理",
            ],
        },
        {
            "id": "execution_rollout",
            "label": "Scale-up rollout and commercial landing",
            "keywords": [
                "scale-up", "pilot", "line trial", "mass production", "commercial rollout", "go-no-go",
                "放量", "试产", "产线验证", "量产", "商业落地", "放行决策",
            ],
        },
    ],
}

# Backward-compatible alias used by existing imports/tests.
COVERAGE_CHAIN_STEPS: list[dict[str, Any]] = CHAIN_PROFILES["generic"]


def coverage_lens_prompt_block() -> str:
    lines = []
    for idx, lens in enumerate(COVERAGE_LENSES, start=1):
        lines.append(f"{idx}. {lens['label']}")
    return "\n".join(lines)


def infer_chain_industry_profile(query: str) -> str:
    text = str(query or "").lower()
    apparel_markers = (
        "apparel", "garment", "fashion", "textile", "fabric", "fiber", "shirt", "clothing",
        "服装", "纺织", "面料", "纤维", "衬衫", "成衣",
    )
    if any(marker in text for marker in apparel_markers):
        return "apparel_supply_chain"
    return "generic"


def resolve_chain_steps(
    *,
    profile_mode: str = "generic",
    industry_profile: str = "auto",
    query: str = "",
) -> list[dict[str, Any]]:
    mode = str(profile_mode or "generic").strip().lower()
    profile = str(industry_profile or "auto").strip().lower()
    if profile not in CHAIN_PROFILES and profile != "auto":
        profile = "generic"

    if mode == "dual":
        chosen = infer_chain_industry_profile(query) if profile == "auto" else profile
        return CHAIN_PROFILES.get(chosen, CHAIN_PROFILES["generic"])
    return CHAIN_PROFILES["generic"]


def coverage_chain_prompt_block(chain_steps: list[dict[str, Any]] | None = None) -> str:
    steps = chain_steps or COVERAGE_CHAIN_STEPS
    lines = []
    for idx, step in enumerate(steps, start=1):
        lines.append(f"{idx}. {step['label']}")
    return "\n".join(lines)


def assess_text_coverage(text_items: list[str]) -> dict[str, Any]:
    normalized_items = [str(item).lower() for item in (text_items or []) if str(item).strip()]
    covered_ids: list[str] = []
    covered_labels: list[str] = []
    missing_ids: list[str] = []
    missing_labels: list[str] = []

    for lens in COVERAGE_LENSES:
        keywords = [str(k).lower() for k in (lens.get("keywords") or []) if str(k).strip()]
        hit = False
        for text in normalized_items:
            if any(keyword in text for keyword in keywords):
                hit = True
                break
        if hit:
            covered_ids.append(str(lens["id"]))
            covered_labels.append(str(lens["label"]))
        else:
            missing_ids.append(str(lens["id"]))
            missing_labels.append(str(lens["label"]))

    total = len(COVERAGE_LENSES)
    ratio = round((len(covered_ids) / total) if total else 0.0, 4)
    return {
        "covered_ids": covered_ids,
        "covered_labels": covered_labels,
        "missing_ids": missing_ids,
        "missing_labels": missing_labels,
        "ratio": ratio,
        "total": total,
    }


def assess_chain_coverage(
    text_items: list[str],
    chain_steps: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    steps = chain_steps or COVERAGE_CHAIN_STEPS
    normalized_items = [str(item).lower() for item in (text_items or []) if str(item).strip()]
    covered_ids: list[str] = []
    covered_labels: list[str] = []
    missing_ids: list[str] = []
    missing_labels: list[str] = []

    for step in steps:
        keywords = [str(k).lower() for k in (step.get("keywords") or []) if str(k).strip()]
        hit = False
        for text in normalized_items:
            if any(keyword in text for keyword in keywords):
                hit = True
                break
        if hit:
            covered_ids.append(str(step["id"]))
            covered_labels.append(str(step["label"]))
        else:
            missing_ids.append(str(step["id"]))
            missing_labels.append(str(step["label"]))

    total = len(steps)
    ratio = round((len(covered_ids) / total) if total else 0.0, 4)
    return {
        "covered_ids": covered_ids,
        "covered_labels": covered_labels,
        "missing_ids": missing_ids,
        "missing_labels": missing_labels,
        "ratio": ratio,
        "total": total,
    }
