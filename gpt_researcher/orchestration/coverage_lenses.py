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


# Complementary narrative-chain coverage used to prevent "flat" reports that
# mention many points but fail to connect macro context to execution.
COVERAGE_CHAIN_STEPS: list[dict[str, Any]] = [
    {
        "id": "macro_context",
        "label": "Macro context and external trajectory",
        "keywords": [
            "macro", "industry", "trend", "market context", "external trajectory", "baseline trend",
            "宏观", "行业", "趋势", "外部环境",
        ],
    },
    {
        "id": "focal_positioning",
        "label": "Focal target positioning and baseline",
        "keywords": [
            "focal", "target entity", "positioning", "brand baseline", "current portfolio", "as-is",
            "目标对象", "品牌基线", "定位", "现有组合",
        ],
    },
    {
        "id": "demand_pull",
        "label": "Demand and stakeholder pull",
        "keywords": [
            "demand", "stakeholder", "user signal", "buyer requirement", "consumer preference",
            "需求", "利益相关方", "用户信号", "采购要求", "消费者偏好",
        ],
    },
    {
        "id": "supply_constraints",
        "label": "Supply/input constraints and enabling infrastructure",
        "keywords": [
            "supply chain", "raw material", "capacity", "manufacturing readiness", "infrastructure", "upstream",
            "供应链", "原材料", "产能", "制造准备度", "基础设施", "上游",
        ],
    },
    {
        "id": "constraints_risk",
        "label": "Regulatory/climate/risk constraints",
        "keywords": [
            "regulation", "policy", "compliance", "climate", "risk", "uncertainty",
            "监管", "政策", "合规", "气候", "风险", "不确定性",
        ],
    },
    {
        "id": "options_tradeoffs",
        "label": "Options and tradeoffs",
        "keywords": [
            "option", "alternative", "tradeoff", "compare", "scenario",
            "方案", "替代", "权衡", "对比", "情景",
        ],
    },
    {
        "id": "execution_plan",
        "label": "Execution roadmap and decision actions",
        "keywords": [
            "roadmap", "milestone", "pilot", "implementation", "decision gate", "next action",
            "路线图", "里程碑", "试点", "落地", "决策门", "下一步",
        ],
    },
]


def coverage_lens_prompt_block() -> str:
    lines = []
    for idx, lens in enumerate(COVERAGE_LENSES, start=1):
        lines.append(f"{idx}. {lens['label']}")
    return "\n".join(lines)


def coverage_chain_prompt_block() -> str:
    lines = []
    for idx, step in enumerate(COVERAGE_CHAIN_STEPS, start=1):
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


def assess_chain_coverage(text_items: list[str]) -> dict[str, Any]:
    normalized_items = [str(item).lower() for item in (text_items or []) if str(item).strip()]
    covered_ids: list[str] = []
    covered_labels: list[str] = []
    missing_ids: list[str] = []
    missing_labels: list[str] = []

    for step in COVERAGE_CHAIN_STEPS:
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

    total = len(COVERAGE_CHAIN_STEPS)
    ratio = round((len(covered_ids) / total) if total else 0.0, 4)
    return {
        "covered_ids": covered_ids,
        "covered_labels": covered_labels,
        "missing_ids": missing_ids,
        "missing_labels": missing_labels,
        "ratio": ratio,
        "total": total,
    }
