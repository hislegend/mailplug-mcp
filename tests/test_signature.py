"""Signature module tests."""
from __future__ import annotations

from mailplug_mcp.config import Config, SignatureConfig
from mailplug_mcp.signature import (
    render_template_signature,
    resolve_signature,
    trim_leading_empty_paragraphs,
)


def test_trim_strips_leading_empty_paragraphs():
    sig = (
        '<p style="line-height:1.5"><br></p>'
        '<p style="line-height:1.5"><br></p>'
        '<p style="line-height:1.5">--</p>'
        '<p>Real content</p>'
    )
    out = trim_leading_empty_paragraphs(sig)
    assert out.startswith('<p style="line-height:1.5">--</p>')
    assert "Real content" in out


def test_trim_handles_no_empty_paragraphs():
    sig = '<p>Already clean</p>'
    assert trim_leading_empty_paragraphs(sig) == sig


def test_trim_handles_empty_input():
    assert trim_leading_empty_paragraphs("") == ""
    assert trim_leading_empty_paragraphs(None) is None  # type: ignore[arg-type]


def test_trim_only_removes_leading_not_internal_breaks():
    sig = '<p><br></p><p>Hello</p><p><br></p><p>World</p>'
    out = trim_leading_empty_paragraphs(sig)
    # Leading empty stripped
    assert out.startswith('<p>Hello</p>')
    # Internal empty between Hello and World is preserved
    assert '<p><br></p><p>World</p>' in out


def _cfg(**overrides) -> Config:
    base = {
        "email": "test@example.com",
        "signature_mode": "template",
        "signature": SignatureConfig(),
    }
    base.update(overrides)
    return Config(**base)  # type: ignore[arg-type]


def test_template_signature_with_full_fields():
    sig = SignatureConfig(
        name="홍길동",
        title="책임 매니저",
        company="주식회사 크랩스",
        phone="010-1234-5678",
        website="crabs.ai",
    )
    html = render_template_signature(sig)
    assert "홍길동" in html
    assert "책임 매니저" in html
    assert "주식회사 크랩스" in html
    assert "010-1234-5678" in html
    assert 'href="https://crabs.ai"' in html


def test_template_signature_skips_empty_fields():
    sig = SignatureConfig(name="홍길동")
    html = render_template_signature(sig)
    assert "홍길동" in html
    # No empty contact line
    assert "☎" not in html


def test_resolve_template_mode():
    cfg = _cfg(signature=SignatureConfig(name="홍길동"))
    out = resolve_signature(cfg)
    assert "홍길동" in out


def test_resolve_auto_falls_back_to_template_when_no_cache(tmp_path, monkeypatch):
    # Redirect cache file to an empty tmp dir so fetch returns None.
    from mailplug_mcp import signature as sig_mod
    monkeypatch.setattr(sig_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sig_mod, "CACHE_FILE", tmp_path / "cache.json")
    cfg = _cfg(signature_mode="auto", signature=SignatureConfig(name="홍길동"))
    out = resolve_signature(cfg)
    assert "홍길동" in out


def test_resolve_mailplug_mode_returns_empty_when_no_cache(tmp_path, monkeypatch):
    from mailplug_mcp import signature as sig_mod
    monkeypatch.setattr(sig_mod, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(sig_mod, "CACHE_FILE", tmp_path / "cache.json")
    cfg = _cfg(signature_mode="mailplug")
    assert resolve_signature(cfg) == ""
