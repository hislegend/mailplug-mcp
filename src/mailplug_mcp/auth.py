"""Credential storage via OS keyring (macOS Keychain / Windows Credential Manager / Linux Secret Service).

Why a separate module:
- Centralizes the keyring service name so it stays consistent across CLI setup,
  the running MCP server, and any tests.
- Provides a fallback to MAILPLUG_APP_PASSWORD env var for local debugging
  without ever encouraging plain-text storage in dotfiles.
"""
from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError

# Single canonical service name. Do NOT change without a migration story —
# users have credentials stored under this exact name.
SERVICE_NAME = "mailplug-mcp"


class CredentialError(RuntimeError):
    """Raised when no credential could be located for the given account."""


def get_app_password(email: str) -> str:
    """Return the Mail Plug app password for ``email``.

    Resolution order:
      1. ``MAILPLUG_APP_PASSWORD`` environment variable (debug only).
      2. OS keyring entry under service "mailplug-mcp" / username == email.
    """
    env_pw = os.environ.get("MAILPLUG_APP_PASSWORD")
    if env_pw:
        return env_pw

    try:
        password = keyring.get_password(SERVICE_NAME, email)
    except KeyringError as exc:
        raise CredentialError(
            f"Failed to read keyring entry for {email!r}: {exc}. "
            "Run `mailplug-mcp-setup` to (re)configure."
        ) from exc

    if not password:
        raise CredentialError(
            f"No app password found in keyring for {email!r}. "
            "Run `mailplug-mcp-setup` to store it."
        )
    return password


def set_app_password(email: str, password: str) -> None:
    """Store the Mail Plug app password in the OS keyring."""
    keyring.set_password(SERVICE_NAME, email, password)


def delete_app_password(email: str) -> None:
    """Remove the keyring entry. Idempotent — does not error if absent."""
    try:
        keyring.delete_password(SERVICE_NAME, email)
    except keyring.errors.PasswordDeleteError:
        pass
