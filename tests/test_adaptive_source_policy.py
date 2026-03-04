from types import SimpleNamespace

from gpt_researcher.skills.adaptive_deep_research import AdaptiveDeepResearchSkill


def _make_skill(source_policy: str = "medium_tier") -> AdaptiveDeepResearchSkill:
    researcher = SimpleNamespace(
        cfg=SimpleNamespace(),
        websocket=None,
        headers={},
        query_domains=[],
        retrievers=[],
        query="source policy test",
        visited_urls=set(),
        research_sources=[],
        scraper_manager=None,
        add_research_sources=lambda sources: None,
        context="",
        research_trace={},
        source_policy=source_policy,
    )
    return AdaptiveDeepResearchSkill(researcher)


def test_medium_tier_flags_core_claim_without_t1_t2_anchor():
    skill = _make_skill("medium_tier")
    skill.claim_to_anchors = {
        "Claim A": [
            {"url": "https://random-blog.example/post", "source_tier": "T3", "node_id": "judgement_1"},
        ]
    }

    ledger = skill._build_claim_ledger()
    skill.claim_ledger = ledger
    coverage = skill._compute_citation_coverage()

    assert ledger[0]["is_core_conclusion"] is True
    assert ledger[0]["policy_pass"] is False
    assert ledger[0]["policy_reason"] == "medium_tier_requires_t1_or_t2_anchor"
    assert coverage["core_conclusion_policy_failed"] == 1


def test_medium_tier_allows_t3_but_not_as_sole_support():
    skill = _make_skill("medium_tier")
    skill.claim_to_anchors = {
        "Claim B": [
            {"url": "https://random-blog.example/post", "source_tier": "T3", "node_id": "judgement_1"},
            {"url": "https://www.reuters.com/example", "source_tier": "T2", "node_id": "judgement_1"},
        ]
    }

    ledger = skill._build_claim_ledger()
    skill.claim_ledger = ledger
    coverage = skill._compute_citation_coverage()

    assert ledger[0]["policy_pass"] is True
    assert ledger[0]["tier_counts"]["T3"] == 1
    assert ledger[0]["tier_counts"]["T2"] == 1
    assert coverage["core_conclusion_policy_failed"] == 0
