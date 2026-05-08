"""Signature resolution.

Three modes:
  - "mailplug" : pull the signature HTML the user has registered in Mail Plug.
  - "template" : generate a Korean-business-style signature from config fields.
  - "auto"     : try mailplug → fallback to template.

The Mail Plug signature is fetched at runtime via an authenticated session
against the Mail Plug web API. To avoid coupling to that internal API (which
can change without notice), we cache the last successfully fetched signature
in a sidecar file so the MCP keeps working when the API is unreachable.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .config import Config, SignatureConfig


# Matches a paragraph that contains only whitespace and/or <br> tags
# (and arbitrary attributes on the <p> tag itself). Mail Plug's webmail
# editor inserts these as visual padding when users press Enter — when
# embedded as a signature in our renderer's mp-signature div, they create
# unwanted vertical gaps. We trim them off the leading edge.
_LEADING_EMPTY_P = re.compile(
    r'^\s*(?:<p[^>]*>\s*(?:<br\s*/?>\s*)*</p>\s*)+',
    re.IGNORECASE,
)


def trim_leading_empty_paragraphs(html: str) -> str:
    """Strip leading empty <p>...</p> blocks (e.g. <p><br></p>) from a signature.

    Returns the input unchanged if no leading empties are present.
    """
    if not html:
        return html
    return _LEADING_EMPTY_P.sub("", html, count=1)


CACHE_DIR = Path.home() / ".mailplug-mcp"
CACHE_FILE = CACHE_DIR / "signature_cache.json"


def render_template_signature(sig: SignatureConfig) -> str:
    """Build a clean inline-HTML signature from user-supplied fields.

    Lines are emitted only for non-empty fields. The output is plain HTML
    (no <html>/<body> wrapper) intended to be inserted inside the
    ``mp-signature`` div by ``renderer.render_markdown_to_html``.
    """
    rows: list[str] = []
    name_line = sig.name
    if sig.title:
        name_line = f"{sig.name} · {sig.title}" if sig.name else sig.title
    if name_line:
        rows.append(f'<div style="font-weight:600; color:#222;">{_escape(name_line)}</div>')
    if sig.company:
        rows.append(f'<div>{_escape(sig.company)}</div>')

    contact_bits: list[str] = []
    if sig.phone:
        contact_bits.append(f'☎ {_escape(sig.phone)}')
    if sig.website:
        href = sig.website if sig.website.startswith(("http://", "https://")) else f"https://{sig.website}"
        contact_bits.append(f'<a href="{_escape(href)}" style="color:#2563eb;">{_escape(sig.website)}</a>')
    if contact_bits:
        rows.append(f'<div style="margin-top:4px;">{" &nbsp;|&nbsp; ".join(contact_bits)}</div>')

    return "\n".join(rows)


def _escape(s: str) -> str:
    """Minimal HTML-attribute-safe escaping."""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


# ── Mail Plug fetch (best-effort, cached) ──────────────────────────────────


def _read_cache(email: str) -> str | None:
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    entry = data.get(email)
    if isinstance(entry, dict):
        return entry.get("html")
    return None


def _write_cache(email: str, html: str) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
    data[email] = {"html": html}
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_mailplug_signature(config: Config) -> str | None:
    """Best-effort: try to retrieve the registered Mail Plug signature.

    The Mail Plug web API requires session-cookie auth (web SSO), which the
    MCP does not have. We therefore use a *cache-only* strategy here: if a
    previous run (or a manual ``mailplug-mcp-setup --import-signature``
    invocation) populated the cache, we return that. Otherwise None.

    See README → "Mail Plug 서명 가져오기" for the manual import procedure.
    """
    return _read_cache(config.email)


def store_mailplug_signature(email: str, html: str) -> None:
    """Persist a signature HTML blob to the cache (used by the setup CLI)."""
    _write_cache(email, html)


# ── Public resolver ────────────────────────────────────────────────────────


def resolve_signature(config: Config) -> str:
    """Return the signature HTML to embed, based on the configured mode.

    Mail Plug-imported signatures pass through ``trim_leading_empty_paragraphs``
    before being returned so that visual whitespace the user added in Mail Plug's
    editor for spacing doesn't compound with our renderer's own ``mp-signature``
    margin.
    """
    mode = (config.signature_mode or "auto").lower()

    if mode == "mailplug":
        html = fetch_mailplug_signature(config)
        return trim_leading_empty_paragraphs(html or "")

    if mode == "template":
        return render_template_signature(config.signature)

    # "auto": mailplug first, fallback to template, fallback to empty.
    html = fetch_mailplug_signature(config)
    if html:
        return trim_leading_empty_paragraphs(html)
    return render_template_signature(config.signature)
