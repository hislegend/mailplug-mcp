"""MCP server entrypoint.

Registers all Mail Plug tools with the FastMCP framework and exposes them
over the stdio transport (the standard transport used by Claude Desktop and
Claude Code MCP integration).

Run:
    mailplug-mcp
"""
from __future__ import annotations

import logging
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from .config import Config, load_config
from .tools import attachments as attachments_tools
from .tools import receive as receive_tools
from .tools import send as send_tools

logger = logging.getLogger("mailplug_mcp")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")


# We load config at import time so any missing-env errors surface immediately
# when the MCP server starts (rather than on first tool call).
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


mcp = FastMCP("mailplug-mcp")


# ── Send tools ──────────────────────────────────────────────────────────────


@mcp.tool(
    name="draft_email",
    description=(
        "Mail Plug 발신용 메일 초안을 생성하고 인라인 CSS HTML 미리보기를 반환합니다. "
        "이 도구는 절대 메일을 발송하지 않습니다. 사용자에게 미리보기를 보여주고 명시적 "
        "승인을 받은 뒤 send_draft(draft_id, confirmed=True)로 발송하세요. "
        "본문은 마크다운으로 작성합니다 — 표·목록·인용·링크 모두 사용 가능합니다."
    ),
)
def draft_email(
    to: Annotated[list[str], Field(description="받는사람 이메일 주소 리스트", min_length=1)],
    subject: Annotated[str, Field(description="메일 제목")],
    body_md: Annotated[str, Field(description="메일 본문 (Markdown). 인사말 / 본문 / 맺음말 순서 권장.")],
    cc: Annotated[list[str] | None, Field(description="참조 이메일 리스트 (선택)")] = None,
    bcc: Annotated[list[str] | None, Field(description="숨은참조 이메일 리스트 (선택)")] = None,
    attachments: Annotated[
        list[str] | None,
        Field(description="첨부 파일의 절대 로컬 경로 리스트 (선택)"),
    ] = None,
    signature_mode: Annotated[
        str | None,
        Field(description='서명 정책 임시 변경: "mailplug" | "template" | "auto" | "none"'),
    ] = None,
    reply_to: Annotated[str | None, Field(description="회신주소 (선택)")] = None,
) -> dict[str, Any]:
    if signature_mode == "none":
        # Override: render with empty signature.
        from .config import Config as _Cfg
        cfg = get_config()
        cfg = _Cfg(**{**cfg.__dict__, "signature_mode": "template"})
        cfg.signature.name = ""
        cfg.signature.title = ""
        cfg.signature.company = ""
        cfg.signature.phone = ""
        cfg.signature.website = ""
        return send_tools.draft_email(
            cfg, to=to, subject=subject, body_md=body_md,
            cc=cc, bcc=bcc, attachments=attachments, reply_to=reply_to,
        )
    return send_tools.draft_email(
        get_config(),
        to=to, subject=subject, body_md=body_md,
        cc=cc, bcc=bcc, attachments=attachments,
        signature_mode=signature_mode, reply_to=reply_to,
    )


@mcp.tool(
    name="send_draft",
    description=(
        "draft_email로 만든 초안을 실제로 발송합니다. confirmed=True 가 반드시 있어야 하며, "
        "사용자가 채팅에서 명시적으로 발송 승인을 한 뒤에만 호출하세요. "
        "발송 성공 시 message_id와 발송 시각을 반환합니다."
    ),
)
def send_draft(
    draft_id: Annotated[str, Field(description="draft_email에서 받은 draft_id")],
    confirmed: Annotated[
        bool,
        Field(description="사용자가 명시적으로 발송 승인했는지 여부. 반드시 True여야 발송됨."),
    ] = False,
) -> dict[str, Any]:
    return send_tools.send_draft(get_config(), draft_id=draft_id, confirmed=confirmed)


@mcp.tool(
    name="discard_draft",
    description="발송하지 않고 초안을 폐기합니다.",
)
def discard_draft(
    draft_id: Annotated[str, Field(description="폐기할 draft_id")],
) -> dict[str, Any]:
    return send_tools.discard_draft(draft_id)


@mcp.tool(
    name="list_drafts",
    description="아직 발송되지 않은 초안 목록을 반환합니다.",
)
def list_drafts() -> list[dict[str, Any]]:
    return send_tools.list_drafts()


# ── Receive tools ───────────────────────────────────────────────────────────


@mcp.tool(
    name="list_inbox",
    description=(
        "받은편지함의 최근 메일 목록(envelope)을 반환합니다. since는 YYYY-MM-DD 형식. "
        "본문이 필요하면 get_email(uid)을 별도로 호출하세요."
    ),
)
def list_inbox(
    folder: Annotated[str, Field(description='IMAP 폴더 이름. 기본 "INBOX".')] = "INBOX",
    limit: Annotated[int, Field(description="최대 개수 (1~200). 기본 20.", ge=1, le=200)] = 20,
    since: Annotated[
        str | None,
        Field(description="이 날짜 이후 메일만 반환. YYYY-MM-DD."),
    ] = None,
) -> list[dict[str, Any]]:
    return receive_tools.list_inbox(get_config(), folder=folder, limit=limit, since=since)


@mcp.tool(
    name="search_email",
    description=(
        "IMAP TEXT 검색으로 제목·본문·발신자 등을 가로질러 키워드 검색합니다. "
        "결과는 최신순. 한글 키워드 지원."
    ),
)
def search_email(
    query: Annotated[str, Field(description="검색어 (한글 가능)", min_length=1)],
    folder: Annotated[str, Field(description="대상 폴더. 기본 INBOX.")] = "INBOX",
    limit: Annotated[int, Field(description="최대 개수 (1~200). 기본 20.", ge=1, le=200)] = 20,
) -> list[dict[str, Any]]:
    return receive_tools.search_email(get_config(), query=query, folder=folder, limit=limit)


@mcp.tool(
    name="get_email",
    description="단일 메일의 헤더·본문(plain+html)·첨부 메타데이터를 반환합니다.",
)
def get_email(
    uid: Annotated[str, Field(description="list_inbox 또는 search_email에서 받은 UID")],
    folder: Annotated[str, Field(description="해당 폴더. 기본 INBOX.")] = "INBOX",
) -> dict[str, Any]:
    return receive_tools.get_email(get_config(), uid=uid, folder=folder)


@mcp.tool(
    name="list_folders",
    description="IMAP 폴더 목록을 반환합니다. 사용자 정의 폴더 이름을 알아낼 때 사용하세요.",
)
def list_folders() -> list[dict[str, Any]]:
    return receive_tools.list_folders(get_config())


# ── Attachments ─────────────────────────────────────────────────────────────


@mcp.tool(
    name="download_attachment",
    description=(
        "메일의 특정 첨부 파일을 로컬에 저장합니다. attachment_index는 get_email 응답의 "
        "attachments[*].index 값을 사용하세요. save_to는 절대 경로 권장."
    ),
)
def download_attachment(
    uid: Annotated[str, Field(description="대상 메일 UID")],
    attachment_index: Annotated[int, Field(description="get_email().attachments[*].index 값", ge=0)],
    save_to: Annotated[str, Field(description="저장할 로컬 파일 경로")],
    folder: Annotated[str, Field(description="해당 폴더. 기본 INBOX.")] = "INBOX",
) -> dict[str, Any]:
    return attachments_tools.download_attachment(
        get_config(),
        uid=uid,
        attachment_index=attachment_index,
        save_to=save_to,
        folder=folder,
    )


# ── Entrypoint ──────────────────────────────────────────────────────────────


def main() -> None:
    """Run the MCP server over stdio."""
    # Triggers eager config load so missing-env errors surface in the parent's stderr,
    # which Claude Desktop then surfaces in its MCP log panel.
    try:
        get_config()
    except Exception as exc:
        logger.error("Configuration error: %s", exc)
        raise
    mcp.run()


if __name__ == "__main__":
    main()
