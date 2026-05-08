"""SMTP send wrapper for Mail Plug (smtp.mailplug.co.kr:465 SSL).

Builds RFC 5322 multipart messages (text + HTML + attachments) and dispatches
via SMTP_SSL with auth from the OS keyring.
"""
from __future__ import annotations

import mimetypes
import smtplib
import ssl
from collections.abc import Iterable
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any

from .auth import get_app_password
from .config import Config


class SMTPSendError(RuntimeError):
    """Raised when SMTP delivery fails. Message preserves server response detail."""


def build_message(
    *,
    config: Config,
    to: Iterable[str],
    subject: str,
    plain_text: str,
    html_body: str,
    cc: Iterable[str] = (),
    bcc: Iterable[str] = (),
    attachments: Iterable[str | Path] = (),
    reply_to: str | None = None,
) -> EmailMessage:
    """Build a multipart EmailMessage with text + html alternative and attachments.

    The plain text part exists so that mail clients without HTML rendering still
    show readable content (this is required by RFC 2046 best practice and by
    several spam filters).
    """
    msg = EmailMessage()
    msg["From"] = config.from_header
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    # Bcc is intentionally NOT added as a header — it's only an envelope recipient.
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=config.email.split("@", 1)[-1] or "localhost")
    if reply_to:
        msg["Reply-To"] = reply_to

    # alternative: plain + html
    msg.set_content(plain_text or "(본문 없음)", subtype="plain", charset="utf-8")
    msg.add_alternative(html_body, subtype="html", charset="utf-8")

    for raw in attachments:
        path = Path(raw).expanduser().resolve()
        if not path.is_file():
            raise SMTPSendError(f"Attachment not found: {path}")
        ctype, encoding = mimetypes.guess_type(str(path))
        if ctype is None or encoding is not None:
            ctype = "application/octet-stream"
        maintype, _, subtype = ctype.partition("/")
        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )

    return msg


def send(
    *,
    config: Config,
    msg: EmailMessage,
    envelope_to: Iterable[str],
) -> dict[str, Any]:
    """Send ``msg`` via SMTP_SSL. Returns metadata for logging/inspection."""
    password = get_app_password(config.email)
    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, context=context, timeout=30) as s:
            s.login(config.email, password)
            s.send_message(msg, from_addr=config.email, to_addrs=list(envelope_to))
    except smtplib.SMTPAuthenticationError as exc:
        raise SMTPSendError(
            f"SMTP authentication failed for {config.email}: {exc}. "
            "Verify the app password (mailplug-mcp-setup) and that "
            "Mail Plug → 환경설정 → IMAP에서 IMAP/SMTP 사용이 ON 인지 확인하세요."
        ) from exc
    except smtplib.SMTPException as exc:
        raise SMTPSendError(f"SMTP error: {exc}") from exc

    return {
        "message_id": msg["Message-ID"],
        "from": msg["From"],
        "to": msg["To"],
        "cc": msg.get("Cc", ""),
        "subject": msg["Subject"],
        "date": msg["Date"],
    }
