"""Markdown → email-safe HTML pipeline.

Goal: produce HTML that renders consistently across Outlook, Gmail, Naver Mail,
Daum Mail, mobile mail apps, and the Mail Plug webmail.

Pipeline:
  1. markdown-it-py converts markdown to HTML.
  2. bleach sanitizes — drops scripts/styles/iframes; allows a conservative tag whitelist.
  3. premailer inlines all CSS into ``style="..."`` attributes (most webmail
     clients strip <style>).
  4. We wrap the result in a Korean-business-email base template that fixes
     fonts, line-height, and width.
  5. ``html_to_text`` produces a plain-text fallback for the multipart message.
"""
from __future__ import annotations

import re
from html import unescape

import bleach
from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from premailer import transform


# Tags safe enough for email rendering. Anything else is stripped.
ALLOWED_TAGS = [
    "a", "b", "blockquote", "br", "code", "div", "em", "h1", "h2", "h3", "h4",
    "hr", "i", "img", "li", "ol", "p", "pre", "span", "strong", "table",
    "tbody", "td", "th", "thead", "tr", "u", "ul",
]
# NOTE: ``style`` is intentionally NOT in the allowed attribute list. Inline
# styles are produced by premailer AFTER bleach has run, against the trusted
# <style> block in our template. Markdown body content goes through markdown-it
# with html=false, so any raw style="..." attributes from user input would
# already have been escaped before reaching bleach.
ALLOWED_ATTRS = {
    "*": ["class", "id", "align", "valign"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "title", "width", "height"],
    "td": ["colspan", "rowspan", "width", "height"],
    "th": ["colspan", "rowspan", "width", "height"],
    "table": ["cellpadding", "cellspacing", "border", "width"],
}


# Base CSS — kept conservative. premailer will inline these onto matching tags.
# Korean font fallback chain prioritized for Mac → Windows → fallback sans-serif.
BASE_CSS = """
body, table, td {
    font-family: 'Apple SD Gothic Neo', 'Malgun Gothic', '맑은 고딕', '나눔고딕',
                 -apple-system, BlinkMacSystemFont, sans-serif;
    color: #222222;
    font-size: 14px;
    line-height: 1.7;
}
.mp-wrapper {
    max-width: 680px;
    margin: 0;
    padding: 8px 4px;
    word-break: break-word;
}
p { margin: 0 0 12px 0; }
h1 { font-size: 22px; font-weight: 700; margin: 24px 0 12px 0; color: #111; }
h2 { font-size: 18px; font-weight: 700; margin: 20px 0 10px 0; color: #111; }
h3 { font-size: 16px; font-weight: 700; margin: 16px 0 8px 0; color: #111; }
ul, ol { margin: 0 0 12px 24px; padding: 0; }
li { margin: 0 0 4px 0; }
a { color: #2563eb; text-decoration: underline; }
blockquote {
    border-left: 3px solid #d1d5db;
    margin: 12px 0;
    padding: 4px 0 4px 12px;
    color: #555;
}
hr { border: none; border-top: 1px solid #e5e7eb; margin: 20px 0; }
code {
    font-family: 'SF Mono', Menlo, Consolas, monospace;
    background: #f3f4f6;
    padding: 2px 5px;
    border-radius: 3px;
    font-size: 13px;
}
pre {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
    padding: 10px 12px;
    overflow-x: auto;
    font-size: 13px;
}
pre code { background: transparent; padding: 0; }
table {
    border-collapse: collapse;
    margin: 12px 0;
}
th, td { border: 1px solid #e5e7eb; padding: 6px 10px; text-align: left; }
th { background: #f9fafb; font-weight: 600; }
.mp-signature {
    margin-top: 12px;
    color: #555;
    font-size: 13px;
}
"""


def _build_markdown() -> MarkdownIt:
    return (
        MarkdownIt("commonmark", {"breaks": True, "linkify": True, "html": False})
        .enable("table")
        .enable("strikethrough")
    )


_MD = _build_markdown()


def render_markdown_to_html(body_md: str, *, signature_html: str = "") -> str:
    """Render Korean business email markdown to inline-styled HTML.

    The ``signature_html`` is appended verbatim inside a <div class="mp-signature">
    block so that it survives the sanitization step (already-trusted HTML).
    """
    body_md = body_md or ""
    raw_html = _MD.render(body_md)
    sanitized = bleach.clean(
        raw_html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=["http", "https", "mailto"],
        strip=True,
        strip_comments=True,
    )

    sig_block = ""
    if signature_html and signature_html.strip():
        sig_block = f'<div class="mp-signature">{signature_html}</div>'

    full_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<style>{BASE_CSS}</style>
</head>
<body>
<div class="mp-wrapper">
{sanitized}
{sig_block}
</div>
</body>
</html>
"""

    inlined = transform(
        full_html,
        keep_style_tags=False,
        remove_classes=False,
        cssutils_logging_level="CRITICAL",
        disable_validation=True,
    )
    return inlined


def html_to_text(html: str) -> str:
    """Convert rendered HTML back to a readable plain-text fallback.

    Not meant to be lossless — just to provide a sensible body for clients
    that don't display HTML, and as defense in depth against text-only spam
    filters.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")

    # Replace <br> with newline; <p>/<div> get blank-line separation.
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for block in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "li", "tr"]):
        block.append("\n")

    text = soup.get_text("")
    text = unescape(text)
    # Collapse 3+ newlines to 2; trim trailing whitespace per line.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
