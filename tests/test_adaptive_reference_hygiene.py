from gpt_researcher.actions.report_generation import _sanitize_reference_hygiene


def test_reference_hygiene_rebuilds_markdown_links_and_removes_placeholders():
    report = """
## Findings
Evidence notes mention domain-only sources (uniqlo.com) and (theecologist.org).
Another source is linked directly ([S1](https://example.com/s1)).

## 参考文献
- 链接
- 来源
- uniqlo.com
- theecologist.org
- [S1](https://example.com/s1)
"""
    cleaned, meta = _sanitize_reference_hygiene(report, language="chinese")
    lowered = cleaned.lower()
    assert "## 参考文献" in cleaned
    assert "链接" not in cleaned
    assert "来源" not in cleaned
    assert "[uniqlo.com](https://uniqlo.com)" in lowered
    assert "[theecologist.org](https://theecologist.org)" in lowered
    assert "[example.com](https://example.com/s1)" in lowered
    assert meta["reference_url_count"] >= 3
    assert meta["reference_hygiene_changed"] is True


def test_reference_hygiene_deduplicates_urls():
    report = """
## Evidence
Repeated citations ([A](https://example.com/a)) and ([B](https://example.com/a)).

## References
- [A](https://example.com/a)
- [B](https://example.com/a)
"""
    cleaned, meta = _sanitize_reference_hygiene(report, language="english")
    assert cleaned.lower().count("https://example.com/a") == 1
    assert meta["reference_url_count"] == 1


def test_reference_hygiene_uses_context_urls_when_report_has_no_links():
    report = """
## Findings
This section cites named sources only.

## References
- OEKO-TEX 2026/2027 rules
- UNIQLO Masterpiece
"""
    context = """
Evidence Log:
- Rule update ([source](https://www.oeko-tex.com/en/))
- Product detail ([source](https://www.uniqlo.com/us/en/contents/masterpiece/))
"""
    cleaned, meta = _sanitize_reference_hygiene(report, language="english", extra_context=context)
    lowered = cleaned.lower()
    assert "[www.oeko-tex.com](https://www.oeko-tex.com/en/)" in lowered
    assert "[www.uniqlo.com](https://www.uniqlo.com/us/en/contents/masterpiece/)" in lowered
    assert meta["reference_url_count"] >= 2
