"""Receive-side MCP tools: list_inbox, search_email, get_email, list_folders.

Thin wrappers over imap_client that shape arguments + handle defaults.
"""
from __future__ import annotations

from typing import Any

from .. import imap_client
from ..config import Config


def list_folders(config: Config) -> list[dict[str, Any]]:
    return imap_client.list_folders(config)


def list_inbox(
    config: Config,
    *,
    folder: str = "INBOX",
    limit: int = 20,
    since: str | None = None,
) -> list[dict[str, Any]]:
    return imap_client.list_inbox(config, folder=folder, limit=limit, since=since)


def search_email(
    config: Config,
    *,
    query: str,
    folder: str = "INBOX",
    limit: int = 20,
) -> list[dict[str, Any]]:
    return imap_client.search_email(config, query=query, folder=folder, limit=limit)


def get_email(
    config: Config,
    *,
    uid: str,
    folder: str = "INBOX",
) -> dict[str, Any]:
    return imap_client.get_email(config, uid=uid, folder=folder)
