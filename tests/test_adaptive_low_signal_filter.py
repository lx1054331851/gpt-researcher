from types import SimpleNamespace

from gpt_researcher.skills.adaptive_deep_research import AdaptiveDeepResearchSkill


def _researcher_with_filter_cfg():
    cfg = SimpleNamespace(
        deep_research_breadth=3,
        deep_research_concurrency=2,
        adaptive_source_quality_filter_enabled=True,
        adaptive_max_sources_per_query=5,
        adaptive_max_sources_per_domain=2,
        adaptive_min_source_quality_score=-10.0,
        adaptive_require_high_quality_source_quota=False,
        adaptive_high_quality_domains=[],
        adaptive_low_quality_domains=[],
        adaptive_domain_hard_blocklist=["plecoforums.com"],
        adaptive_low_signal_url_patterns=[r"wordfreq", r"dictionary", r"wordlist"],
        adaptive_low_signal_title_patterns=[r"词频", r"frequency list", r"lexicon"],
    )
    return SimpleNamespace(
        cfg=cfg,
        websocket=None,
        headers={},
        query_domains=[],
        retrievers=[],
        query="low signal filtering",
        visited_urls=set(),
        research_sources=[],
        scraper_manager=None,
        add_research_sources=lambda sources: None,
        context="",
        research_trace={},
    )


def test_low_signal_sources_are_hard_filtered():
    skill = AdaptiveDeepResearchSkill(_researcher_with_filter_cfg())
    results = [
        {
            "href": "https://plecoforums.com/download/technology_wordfreq-release_utf-8-txt.2599/",
            "title": "word frequency list",
            "body": "dictionary resource",
        },
        {
            "href": "https://example.com/glossary/dictionary-of-textiles",
            "title": "Textile dictionary",
            "body": "terminology list",
        },
        {
            "href": "https://www.fastretailing.com/eng/ir/library/pdf/ar2024_en.pdf",
            "title": "Integrated report 2024",
            "body": "materials and supply chain strategy",
        },
    ]
    selected = skill._rank_and_filter_search_results(results)
    selected_urls = [str(item.get("href") or item.get("url") or "") for item in selected]
    assert len(selected_urls) == 1
    assert "fastretailing.com" in selected_urls[0]
    assert skill.diagnostics["low_signal_dropped_count"] >= 2
