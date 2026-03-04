from gpt_researcher.retrievers.tavily.tavily_search import TavilySearch


def test_tavily_search_retry_with_minimal_payload(monkeypatch):
    calls: list[dict] = []

    def fake_search(self, query, **kwargs):
        calls.append({"query": query, **kwargs})
        if len(calls) == 1:
            raise RuntimeError("400 bad request")
        return {
            "results": [
                {
                    "url": "https://www.vfc.com/investors",
                    "content": "VF investor update",
                    "raw_content": "",
                    "title": "Investor Relations",
                }
            ]
        }

    monkeypatch.setattr(TavilySearch, "_search", fake_search, raising=True)

    retriever = TavilySearch(
        query="VF " * 500,  # deliberately long query
        headers={"tavily_api_key": "test-key"},
        query_domains=["example.com"],
    )
    results = retriever.search(max_results=3)

    assert len(retriever.query) <= 700
    assert results
    assert results[0]["href"] == "https://www.vfc.com/investors"
    assert len(calls) == 2
    assert calls[1]["include_domains"] is None
    assert calls[1]["search_depth"] == "basic"
    assert calls[1]["include_raw_content"] is False
