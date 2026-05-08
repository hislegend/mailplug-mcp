"""Attachment download tool."""
from __future__ import annotations

from typing import Any

from .. import imap_client
from ..config import Config


def download_attachment(
    config: Config,
    *,
    uid: str,
    attachment_index: int,
    save_to: str,
    folder: str = "INBOX",
) -> dict[str, Any]:
    return imap_client.download_attachment(
        config,
        uid=uid,
        attachment_index=attachment_index,
        save_to=save_to,
        folder=folder,
    )
