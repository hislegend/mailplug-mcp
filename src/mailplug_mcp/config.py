"""Configuration loading.

Resolution order for each setting:
  1. Environment variable (MAILPLUG_*)
  2. .env file in current directory (if python-dotenv available)
  3. Built-in default

The Mail Plug app password is *never* loaded from config — it must come from
the OS keychain. See `auth.py`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


# Default Mail Plug servers (verified against gw.mailplug.com IMAP settings page).
DEFAULT_IMAP_HOST = "imap.mailplug.co.kr"
DEFAULT_IMAP_PORT = 993
DEFAULT_SMTP_HOST = "smtp.mailplug.co.kr"
DEFAULT_SMTP_PORT = 465


@dataclass
class SignatureConfig:
    """User-supplied fields for the template-mode signature."""

    name: str = ""
    title: str = ""
    company: str = ""
    phone: str = ""
    website: str = ""


@dataclass
class Config:
    email: str
    imap_host: str = DEFAULT_IMAP_HOST
    imap_port: int = DEFAULT_IMAP_PORT
    smtp_host: str = DEFAULT_SMTP_HOST
    smtp_port: int = DEFAULT_SMTP_PORT
    display_name: str = ""
    signature_mode: str = "auto"  # "mailplug" | "template" | "auto"
    signature: SignatureConfig = field(default_factory=SignatureConfig)

    @property
    def from_header(self) -> str:
        """RFC 5322 From header value (display name + email)."""
        if self.display_name:
            return f'"{self.display_name}" <{self.email}>'
        return self.email


def _load_dotenv_if_present() -> None:
    """Best-effort .env loading without requiring python-dotenv."""
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # Don't override values that the parent process already set.
        os.environ.setdefault(key, value)


def load_config() -> Config:
    """Load Config from environment variables (with .env fallback)."""
    _load_dotenv_if_present()

    email = os.environ.get("MAILPLUG_EMAIL", "").strip()
    if not email:
        raise RuntimeError(
            "MAILPLUG_EMAIL is not set. Run `mailplug-mcp-setup` or set it in .env / environment."
        )

    return Config(
        email=email,
        imap_host=os.environ.get("MAILPLUG_IMAP_HOST", "").strip() or DEFAULT_IMAP_HOST,
        imap_port=int(os.environ.get("MAILPLUG_IMAP_PORT", DEFAULT_IMAP_PORT)),
        smtp_host=os.environ.get("MAILPLUG_SMTP_HOST", "").strip() or DEFAULT_SMTP_HOST,
        smtp_port=int(os.environ.get("MAILPLUG_SMTP_PORT", DEFAULT_SMTP_PORT)),
        display_name=os.environ.get("MAILPLUG_DISPLAY_NAME", "").strip(),
        signature_mode=os.environ.get("MAILPLUG_SIGNATURE_MODE", "auto").strip() or "auto",
        signature=SignatureConfig(
            name=os.environ.get("MAILPLUG_SIGNATURE_NAME", "").strip(),
            title=os.environ.get("MAILPLUG_SIGNATURE_TITLE", "").strip(),
            company=os.environ.get("MAILPLUG_SIGNATURE_COMPANY", "").strip(),
            phone=os.environ.get("MAILPLUG_SIGNATURE_PHONE", "").strip(),
            website=os.environ.get("MAILPLUG_SIGNATURE_WEBSITE", "").strip(),
        ),
    )
