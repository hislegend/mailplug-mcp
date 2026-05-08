"""Sanity tests for the markdown → email-HTML pipeline.

Note: these don't try to verify pixel-perfect rendering; they verify that
sanitization, inlining, and the plain-text fallback do not silently lose
critical structure.
"""
from __future__ import annotations

import re

from mailplug_mcp.renderer import html_to_text, render_markdown_to_html


def test_basic_paragraph_renders_with_inline_styles():
    html = render_markdown_to_html("안녕하세요. 첫 단락입니다.")
    # Body wrapped in mp-wrapper div with inlined styles
    assert 'class="mp-wrapper"' in html or "mp-wrapper" in html
    # Paragraph tag survives
    assert "<p" in html
    assert "안녕하세요. 첫 단락입니다." in html
    # Inline style attribute should appear somewhere on body content
    assert 'style="' in html


def test_lists_and_emphasis_preserved():
    md = """
**중요:** 다음 항목 확인 부탁드립니다.

- 첨부 1
- 첨부 2
- 첨부 3
"""
    html = render_markdown_to_html(md)
    assert "<strong" in html
    assert "<ul" in html
    assert html.count("<li") == 3


def test_dangerous_tags_are_stripped():
    """Verify no executable script/iframe tags survive — text content may remain
    as escaped/visible characters (which is harmless, just visible text)."""
    md = '<script>alert(1)</script>\n\n본문 텍스트'
    html = render_markdown_to_html(md)
    # The script tag itself must be gone (this is the security-critical part).
    assert "<script" not in html.lower()
    assert "</script>" not in html.lower()
    # Body text should still render normally.
    assert "본문 텍스트" in html


def test_javascript_urls_are_neutralized():
    """Anchor tags with javascript: protocol must have href stripped or rewritten."""
    md = '[클릭](javascript:alert(1))'
    html = render_markdown_to_html(md)
    # bleach removes disallowed-protocol hrefs; the link text may remain.
    assert 'href="javascript:' not in html.lower()


def test_iframe_is_stripped():
    md = '<iframe src="https://evil.example/"></iframe>\n\n본문'
    html = render_markdown_to_html(md)
    assert "<iframe" not in html.lower()


def test_signature_block_is_appended():
    sig = '<div>홍길동 · 책임</div>'
    html = render_markdown_to_html("안녕하세요.", signature_html=sig)
    assert "홍길동" in html
    assert "mp-signature" in html


def test_html_to_text_collapses_blocks():
    html = "<div><p>줄1</p><p>줄2</p><ul><li>항목1</li><li>항목2</li></ul></div>"
    text = html_to_text(html)
    assert "줄1" in text
    assert "줄2" in text
    assert "항목1" in text
    # Blank-line separation between paragraphs
    assert re.search(r"줄1\s*\n\s*줄2", text)


def test_table_renders_cells():
    md = """
| 이름 | 직책 |
|------|------|
| 홍길동 | 책임 |
| 김철수 | 매니저 |
"""
    html = render_markdown_to_html(md)
    assert "<table" in html
    assert "홍길동" in html
    assert "김철수" in html
    assert html.count("<tr") >= 3  # header + 2 rows


def test_links_get_href_preserved():
    html = render_markdown_to_html("[홈페이지](https://crabs.ai)")
    assert 'href="https://crabs.ai"' in html
