"""IMAP read wrapper for Mail Plug (imap.mailplug.co.kr:993 SSL).

Provides folder listing, mailbox listing/searching, and per-message fetching
with attachment metadata. Designed to return plain dict / list output ready
for direct serialization back to MCP tool callers.
"""
from __future__ import annotations

import email
import imaplib
import re
import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parsedate_to_datetime
from typing import Any

from .auth import get_app_password
from .config import Config


class IMAPError(RuntimeError):
    """Raised when an IMAP operation fails."""


# ── Connection ─────────────────────────────────────────────────────────────


@contextmanager
def imap_session(config: Config) -> Iterator[imaplib.IMAP4_SSL]:
    """Yield an authenticated IMAP4_SSL connection. Logs out on exit."""
    password = get_app_password(config.email)
    context = ssl.create_default_context()
    try:
        conn = imaplib.IMAP4_SSL(config.imap_host, config.imap_port, ssl_context=context, timeout=30)
    except OSError as exc:
        raise IMAPError(f"Could not connect to {config.imap_host}:{config.imap_port}: {exc}") from exc

    try:
        conn.login(config.email, password)
    except imaplib.IMAP4.error as exc:
        raise IMAPError(
            f"IMAP login failed for {config.email}: {exc}. "
            "Mail Plug → 환경설정 → IMAP에서 사용 ON 및 앱 비밀번호 발급 여부를 확인하세요."
        ) from exc

    try:
        yield conn
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001 - best-effort close
            pass


# ── Helpers ────────────────────────────────────────────────────────────────


def _decode(s: str | bytes | None) -> str:
    """Decode RFC 2047 encoded-word headers (=?utf-8?B?...?=)."""
    if s is None:
        return ""
    if isinstance(s, bytes):
        try:
            s = s.decode("utf-8", errors="replace")
        except Exception:
            return s.decode("latin-1", errors="replace")
    try:
        return str(make_header(decode_header(s)))
    except Exception:
        return s


_FOLDER_LINE = re.compile(rb'\((?P<flags>[^)]*)\) "(?P<delim>[^"]+)" (?P<name>.+)')


def _parse_folder_line(line: bytes) -> dict[str, Any] | None:
    m = _FOLDER_LINE.search(line)
    if not m:
        return None
    name = m.group("name").decode("utf-8", errors="replace").strip()
    if name.startswith('"') and name.endswith('"'):
        name = name[1:-1]
    # IMAP UTF-7 (RFC 3501) → unicode for Korean folder names
    try:
        decoded = name.encode("latin-1", errors="ignore").decode("utf-7", errors="ignore") or name
    except Exception:
        decoded = name
    return {
        "raw": name,
        "name": decoded,
        "delimiter": m.group("delim").decode("utf-8", errors="replace"),
        "flags": m.group("flags").decode("utf-8", errors="replace"),
    }


def _select_folder(conn: imaplib.IMAP4_SSL, folder: str) -> int:
    typ, data = conn.select(f'"{folder}"', readonly=True)
    if typ != "OK":
        raise IMAPError(f"Could not SELECT folder {folder!r}: {data!r}")
    return int(data[0])


def _parse_envelope(uid: bytes, msg: Message) -> dict[str, Any]:
    raw_date = msg.get("Date", "")
    iso_date: str | None = None
    if raw_date:
        try:
            dt = parsedate_to_datetime(raw_date)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            iso_date = dt.astimezone().isoformat()
        except (TypeError, ValueError):
            iso_date = None
    return {
        "uid": uid.decode() if isinstance(uid, bytes) else str(uid),
        "subject": _decode(msg.get("Subject")),
        "from": _decode(msg.get("From")),
        "to": _decode(msg.get("To")),
        "cc": _decode(msg.get("Cc")),
        "date": iso_date or raw_date,
        "message_id": (msg.get("Message-ID") or "").strip(),
    }


def _extract_bodies(msg: Message) -> tuple[str, str]:
    """Return (plain_text, html) bodies. Empty string if absent."""
    plain_parts: list[str] = []
    html_parts: list[str] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            ctype = part.get_content_type()
            disp = (part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            charset = part.get_content_charset() or "utf-8"
            try:
                payload = part.get_payload(decode=True) or b""
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/plain":
                plain_parts.append(text)
            elif ctype == "text/html":
                html_parts.append(text)
    else:
        ctype = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        payload = msg.get_payload(decode=True) or b""
        try:
            text = payload.decode(charset, errors="replace")
        except Exception:
            text = ""
        if ctype == "text/html":
            html_parts.append(text)
        else:
            plain_parts.append(text)
    return "\n".join(plain_parts).strip(), "\n".join(html_parts).strip()


def _extract_attachments(msg: Message) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not msg.is_multipart():
        return out
    for idx, part in enumerate(msg.walk()):
        disp = (part.get("Content-Disposition") or "").lower()
        if "attachment" not in disp and not part.get_filename():
            continue
        filename = _decode(part.get_filename() or f"attachment_{idx}")
        payload = part.get_payload(decode=True) or b""
        out.append({
            "index": idx,
            "filename": filename,
            "content_type": part.get_content_type(),
            "size_bytes": len(payload),
        })
    return out


# ── Public operations ──────────────────────────────────────────────────────


def list_folders(config: Config) -> list[dict[str, Any]]:
    with imap_session(config) as conn:
        typ, data = conn.list()
        if typ != "OK":
            raise IMAPError(f"LIST failed: {data!r}")
        out: list[dict[str, Any]] = []
        for line in data:
            if not line:
                continue
            parsed = _parse_folder_line(line if isinstance(line, bytes) else line.encode())
            if parsed:
                out.append(parsed)
        return out


def list_inbox(
    config: Config,
    *,
    folder: str = "INBOX",
    limit: int = 20,
    since: str | None = None,
) -> list[dict[str, Any]]:
    """Return the most-recent ``limit`` envelopes in ``folder``.

    If ``since`` is provided (ISO date YYYY-MM-DD), only messages on or after
    that date are returned.
    """
    if limit <= 0 or limit > 200:
        raise IMAPError("limit must be between 1 and 200")

    with imap_session(config) as conn:
        _select_folder(conn, folder)

        criteria: list[bytes] = [b"ALL"]
        if since:
            try:
                dt = datetime.fromisoformat(since)
            except ValueError as exc:
                raise IMAPError(f"Invalid `since` date: {since!r} (expected YYYY-MM-DD)") from exc
            imap_date = dt.strftime("%d-%b-%Y").encode()
            criteria = [b"SINCE", imap_date]

        typ, data = conn.uid("SEARCH", None, *criteria)  # type: ignore[arg-type]
        if typ != "OK":
            raise IMAPError(f"SEARCH failed: {data!r}")
        uids = data[0].split()
        # Newest first; UIDs are monotonically increasing.
        uids = uids[-limit:][::-1]

        envelopes: list[dict[str, Any]] = []
        for uid in uids:
            typ, fetch = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO CC DATE MESSAGE-ID)])")
            if typ != "OK" or not fetch or not isinstance(fetch[0], tuple):
                continue
            header_bytes = fetch[0][1]
            msg = email.message_from_bytes(header_bytes)
            envelopes.append(_parse_envelope(uid, msg))
        return envelopes


def search_email(
    config: Config,
    *,
    query: str,
    folder: str = "INBOX",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Full-text search across SUBJECT, FROM, TO, BODY using IMAP TEXT search.

    Mail Plug supports IMAP TEXT search; results are sorted newest-first.
    """
    if not query or not query.strip():
        raise IMAPError("query cannot be empty")
    if limit <= 0 or limit > 200:
        raise IMAPError("limit must be between 1 and 200")

    with imap_session(config) as conn:
        _select_folder(conn, folder)
        encoded_query = query.encode("utf-8")
        # IMAP literal syntax is required for non-ASCII queries.
        typ, data = conn.uid("SEARCH", "CHARSET", "UTF-8", "TEXT", encoded_query)  # type: ignore[arg-type]
        if typ != "OK":
            raise IMAPError(f"SEARCH failed: {data!r}")
        uids = data[0].split()[-limit:][::-1]

        envelopes: list[dict[str, Any]] = []
        for uid in uids:
            typ, fetch = conn.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM TO CC DATE MESSAGE-ID)])")
            if typ != "OK" or not fetch or not isinstance(fetch[0], tuple):
                continue
            msg = email.message_from_bytes(fetch[0][1])
            envelopes.append(_parse_envelope(uid, msg))
        return envelopes


def get_email(
    config: Config,
    *,
    uid: str,
    folder: str = "INBOX",
) -> dict[str, Any]:
    """Fetch one full message: envelope + plain body + html body + attachment metadata."""
    with imap_session(config) as conn:
        _select_folder(conn, folder)
        typ, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            raise IMAPError(f"FETCH failed for UID {uid}: {data!r}")
        raw = data[0][1]
        msg = email.message_from_bytes(raw)
        envelope = _parse_envelope(uid.encode(), msg)
        plain, html = _extract_bodies(msg)
        return {
            **envelope,
            "body_plain": plain,
            "body_html": html,
            "attachments": _extract_attachments(msg),
        }


def download_attachment(
    config: Config,
    *,
    uid: str,
    attachment_index: int,
    save_to: str,
    folder: str = "INBOX",
) -> dict[str, Any]:
    """Save the attachment at ``attachment_index`` (from get_email) to ``save_to`` path."""
    from pathlib import Path as _Path
    target = _Path(save_to).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    with imap_session(config) as conn:
        _select_folder(conn, folder)
        typ, data = conn.uid("FETCH", uid, "(BODY.PEEK[])")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            raise IMAPError(f"FETCH failed for UID {uid}: {data!r}")
        msg = email.message_from_bytes(data[0][1])

    parts = list(msg.walk()) if msg.is_multipart() else [msg]
    if attachment_index < 0 or attachment_index >= len(parts):
        raise IMAPError(f"attachment_index {attachment_index} out of range (have {len(parts)} parts)")
    part = parts[attachment_index]
    payload = part.get_payload(decode=True) or b""
    if not payload:
        raise IMAPError(f"Part {attachment_index} has no decodable payload")

    target.write_bytes(payload)
    return {
        "saved_to": str(target),
        "filename": _decode(part.get_filename() or target.name),
        "size_bytes": len(payload),
        "content_type": part.get_content_type(),
    }
