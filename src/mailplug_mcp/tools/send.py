"""Send-side MCP tools: draft_email + send_draft.

Two-step flow is intentional. The MCP NEVER auto-sends:
  1. ``draft_email`` renders + persists a draft and returns a preview.
  2. ``send_draft(draft_id, confirmed=True)`` is the only path that calls SMTP.

Drafts are persisted to ~/.mailplug-mcp/drafts/<id>.json so the assistant
can reference a draft across separate tool calls.
"""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config import Config
from ..renderer import html_to_text, render_markdown_to_html
from ..signature import resolve_signature
from ..smtp_client import SMTPSendError, build_message, send


DRAFT_DIR = Path.home() / ".mailplug-mcp" / "drafts"


def _draft_path(draft_id: str) -> Path:
    return DRAFT_DIR / f"{draft_id}.json"


def _new_draft_id() -> str:
    return secrets.token_urlsafe(9)


def _truncate(text: str, n: int = 240) -> str:
    text = text.strip()
    return text if len(text) <= n else text[: n - 1] + "…"


# ── Public tool implementations ─────────────────────────────────────────────


def draft_email(
    config: Config,
    *,
    to: list[str],
    subject: str,
    body_md: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    attachments: list[str] | None = None,
    signature_mode: str | None = None,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """Render a draft and return a preview. Does NOT send.

    Returns:
        dict with keys:
          - draft_id: opaque token to pass to ``send_draft``
          - preview_html: rendered, inlined HTML body
          - preview_text: plain-text fallback
          - summary: short human-readable summary
          - to / cc / bcc / subject / attachments: echoed for confirmation UX
    """
    if not to:
        raise ValueError("`to` cannot be empty")
    if not subject or not subject.strip():
        raise ValueError("`subject` cannot be empty")

    cc = cc or []
    bcc = bcc or []
    attachments = attachments or []

    # Allow per-call override of signature mode without mutating config.
    if signature_mode:
        local_config = Config(
            **{**config.__dict__, "signature_mode": signature_mode}
        )
    else:
        local_config = config

    sig_html = resolve_signature(local_config)
    html_body = render_markdown_to_html(body_md, signature_html=sig_html)
    text_body = html_to_text(html_body)

    draft_id = _new_draft_id()
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    draft = {
        "draft_id": draft_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "subject": subject,
        "body_md": body_md,
        "body_html": html_body,
        "body_text": text_body,
        "attachments": [str(Path(a).expanduser().resolve()) for a in attachments],
        "reply_to": reply_to,
        "signature_mode": signature_mode or config.signature_mode,
    }
    _draft_path(draft_id).write_text(
        json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "draft_id": draft_id,
        "preview_html": html_body,
        "preview_text": text_body,
        "summary": (
            f"받는사람: {', '.join(to)}"
            + (f" / 참조: {', '.join(cc)}" if cc else "")
            + (f" / 숨은참조: {', '.join(bcc)}" if bcc else "")
            + f"\n제목: {subject}"
            + (f"\n첨부: {len(attachments)}개" if attachments else "")
            + f"\n본문 미리보기: {_truncate(text_body)}"
        ),
        "to": to,
        "cc": cc,
        "bcc": bcc,
        "subject": subject,
        "attachments": attachments,
    }


def send_draft(
    config: Config,
    *,
    draft_id: str,
    confirmed: bool = False,
) -> dict[str, Any]:
    """Send a previously drafted email. ``confirmed`` MUST be True.

    The ``confirmed`` flag is a structural guard: the MCP server will not
    invoke SMTP unless the assistant explicitly passes ``confirmed=True``,
    which the assistant should only do after the user gives explicit consent
    in chat.
    """
    if not confirmed:
        raise ValueError(
            "`confirmed` must be True. The user must explicitly approve sending "
            "before this tool is called."
        )

    path = _draft_path(draft_id)
    if not path.exists():
        raise FileNotFoundError(f"No draft found with id {draft_id!r}")

    draft = json.loads(path.read_text(encoding="utf-8"))

    msg = build_message(
        config=config,
        to=draft["to"],
        subject=draft["subject"],
        plain_text=draft["body_text"],
        html_body=draft["body_html"],
        cc=draft.get("cc", []),
        bcc=draft.get("bcc", []),
        attachments=draft.get("attachments", []),
        reply_to=draft.get("reply_to"),
    )

    envelope_to = list(draft["to"]) + list(draft.get("cc", [])) + list(draft.get("bcc", []))

    try:
        meta = send(config=config, msg=msg, envelope_to=envelope_to)
    except SMTPSendError:
        # Keep the draft file so the user can inspect / retry / delete manually.
        raise

    # On success, archive the draft into a "sent" subdirectory for record.
    sent_dir = DRAFT_DIR.parent / "sent"
    sent_dir.mkdir(parents=True, exist_ok=True)
    archive_path = sent_dir / f"{draft_id}.json"
    draft["sent_at"] = datetime.now(timezone.utc).isoformat()
    draft["smtp_meta"] = meta
    archive_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    path.unlink(missing_ok=True)

    return {
        "status": "sent",
        "draft_id": draft_id,
        "sent_at": draft["sent_at"],
        **meta,
    }


def discard_draft(draft_id: str) -> dict[str, Any]:
    """Delete a draft without sending."""
    path = _draft_path(draft_id)
    if path.exists():
        path.unlink()
        return {"status": "discarded", "draft_id": draft_id}
    return {"status": "not_found", "draft_id": draft_id}


def list_drafts() -> list[dict[str, Any]]:
    """List currently pending drafts (not yet sent)."""
    if not DRAFT_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(DRAFT_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        out.append({
            "draft_id": d.get("draft_id"),
            "created_at": d.get("created_at"),
            "to": d.get("to"),
            "subject": d.get("subject"),
        })
    return out
