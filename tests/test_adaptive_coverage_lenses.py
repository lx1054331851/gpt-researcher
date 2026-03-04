from gpt_researcher.orchestration.outline_schema import ResearchOutline
from gpt_researcher.orchestration.coverage_lenses import assess_chain_coverage
from gpt_researcher.skills.research_planner import assess_outline_coverage


def _build_outline(sections, workstreams):
    return ResearchOutline.from_dict(
        {
            "outline_id": "coverage-test",
            "query": "generic strategy decision",
            "objective": "Deliver a decision-ready strategy.",
            "scope": "Define scope, constraints, and baseline context.",
            "constraints": ["Boundaries and assumptions must be explicit."],
            "sections": sections,
            "workstreams": workstreams,
        }
    )


def test_assess_outline_coverage_sufficient():
    outline = _build_outline(
        sections=[
            {
                "id": "foundation-1",
                "title": "Scope and Baseline",
                "intent": "Frame constraints and current baseline evidence.",
                "key_questions": ["What are scope constraints and baseline metrics?"],
                "stage": "foundation",
                "priority": 0.9,
                "required": True,
            },
            {
                "id": "evidence-1",
                "title": "Options, Economics, Risk, and Benchmarks",
                "intent": "Compare options, economics feasibility, risk/compliance, and competitor benchmarks.",
                "key_questions": ["Which option has better tradeoffs under risk and cost constraints?"],
                "stage": "evidence",
                "priority": 0.8,
                "required": True,
            },
            {
                "id": "judgement-1",
                "title": "Roadmap and Actions",
                "intent": "Define roadmap, priorities, stakeholder demand, and concrete next actions.",
                "key_questions": ["What should stakeholders do next?"],
                "stage": "judgement",
                "priority": 0.7,
                "required": True,
            },
        ],
        workstreams=[
            {
                "id": "ws-1",
                "title": "Stakeholder demand mapping",
                "intent": "Capture user and buyer demand signals.",
                "deliverable": "Demand matrix and personas",
            }
        ],
    )
    coverage = assess_outline_coverage(outline)
    assert coverage["ratio"] >= 0.75
    assert len(coverage["missing_ids"]) <= 2


def test_assess_outline_coverage_insufficient():
    outline = _build_outline(
        sections=[
            {
                "id": "foundation-1",
                "title": "Technical stack overview",
                "intent": "Describe technical architecture only.",
                "key_questions": ["Which model architecture is modern?"],
                "stage": "foundation",
                "priority": 0.9,
                "required": True,
            },
            {
                "id": "evidence-1",
                "title": "Technical benchmark details",
                "intent": "Collect technical benchmark numbers.",
                "key_questions": ["How fast is model inference?"],
                "stage": "evidence",
                "priority": 0.8,
                "required": True,
            },
            {
                "id": "judgement-1",
                "title": "Technical recommendation",
                "intent": "Recommend technical implementation only.",
                "key_questions": ["Which technical option should we choose?"],
                "stage": "judgement",
                "priority": 0.7,
                "required": True,
            },
        ],
        workstreams=[
            {
                "id": "ws-1",
                "title": "Architecture review",
                "intent": "Review architecture decisions",
                "deliverable": "Architecture memo",
            }
        ],
    )
    coverage = assess_outline_coverage(outline)
    assert coverage["ratio"] < 0.75
    assert len(coverage["missing_ids"]) >= 3


def test_assess_outline_coverage_repeated_dimension_stays_low():
    outline = _build_outline(
        sections=[
            {
                "id": "foundation-1",
                "title": "Benchmark benchmark benchmark",
                "intent": "Benchmark competitors and benchmark peers.",
                "key_questions": ["How do competitor benchmarks compare?"],
                "stage": "foundation",
                "priority": 0.9,
                "required": True,
            },
            {
                "id": "evidence-1",
                "title": "Benchmark expansion",
                "intent": "Continue benchmark analysis.",
                "key_questions": ["More benchmark evidence?"],
                "stage": "evidence",
                "priority": 0.8,
                "required": True,
            },
            {
                "id": "judgement-1",
                "title": "Benchmark decision",
                "intent": "Decision based on benchmark only.",
                "key_questions": ["What benchmark wins?"],
                "stage": "judgement",
                "priority": 0.7,
                "required": True,
            },
        ],
        workstreams=[],
    )
    coverage = assess_outline_coverage(outline)
    assert coverage["ratio"] < 0.5
    assert "Roadmap, priorities, and actions" in coverage["missing_labels"]


def test_assess_chain_coverage_detects_macro_to_execution_flow():
    text_items = [
        "Industry macro trend and market context are changing quickly.",
        "Brand baseline and current portfolio show a gap.",
        "Customer demand and buyer requirements emphasize comfort and compliance.",
        "Supply chain capacity and raw material constraints remain tight.",
        "Regulatory and climate risk are increasing.",
        "Option tradeoff analysis compares route A and route B.",
        "Roadmap includes pilot milestones and go/no-go decision gates.",
    ]
    chain = assess_chain_coverage(text_items)
    assert chain["ratio"] >= 0.85
    assert len(chain["missing_ids"]) <= 1
