"""CLI entrypoint: ``mailplug-mcp-setup``.

Stores the Mail Plug app password in the OS keyring under service
"mailplug-mcp" / username == email. Optionally imports a Mail Plug-side
signature into the local cache.

Usage:
    mailplug-mcp-setup
    mailplug-mcp-setup --email valla@crabs.ai
    mailplug-mcp-setup --import-signature path/to/signature.html
    mailplug-mcp-setup --reset
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from .auth import delete_app_password, get_app_password, set_app_password
from .signature import store_mailplug_signature


def _prompt_email(default: str) -> str:
    msg = "Mail Plug 이메일 주소"
    if default:
        msg += f" [{default}]"
    msg += ": "
    while True:
        val = input(msg).strip() or default
        if "@" in val and "." in val.split("@", 1)[-1]:
            return val
        print("올바른 이메일 형식이 아닙니다. 다시 입력해 주세요.")


def cmd_setup(email: str | None) -> int:
    import os
    default_email = email or os.environ.get("MAILPLUG_EMAIL", "").strip()
    final_email = email or _prompt_email(default_email)

    print(
        "\nMail Plug 앱 비밀번호를 입력하세요.\n"
        "  • 입력값은 화면에 표시되지 않습니다.\n"
        "  • 일반 로그인 비밀번호가 아니라 Mail Plug → 환경설정 → 로그인 보안 설정 →\n"
        "    앱 비밀번호 페이지에서 발급받은 값입니다.\n"
    )
    pw = getpass.getpass("앱 비밀번호: ")
    if not pw.strip():
        print("빈 비밀번호는 저장할 수 없습니다.", file=sys.stderr)
        return 2

    try:
        set_app_password(final_email, pw.strip())
    except Exception as exc:  # noqa: BLE001
        print(f"키체인 저장 실패: {exc}", file=sys.stderr)
        return 3

    # Round-trip verify so we surface keyring backend issues immediately.
    try:
        readback = get_app_password(final_email)
    except Exception as exc:  # noqa: BLE001
        print(f"저장은 성공했으나 즉시 읽기 실패: {exc}", file=sys.stderr)
        return 4
    if readback != pw.strip():
        print("저장은 성공했으나 읽기 결과가 일치하지 않습니다.", file=sys.stderr)
        return 4

    print(f"\n✓ {final_email} 의 앱 비밀번호가 키체인에 저장되었습니다.")
    print("  서비스 이름: mailplug-mcp")
    print("  변경: 같은 명령을 다시 실행하면 덮어쓰기 됩니다.")
    print(f"  삭제: mailplug-mcp-setup --reset --email {final_email}")
    print("\n다음 단계:")
    print("  1) .env에 MAILPLUG_EMAIL 등 변수를 설정하세요 (.env.example 참조).")
    print("  2) Claude Desktop / Claude Code에 MCP 서버를 등록하세요 (README 참조).")
    return 0


def cmd_reset(email: str | None) -> int:
    if not email:
        print("--email <주소> 가 필요합니다.", file=sys.stderr)
        return 2
    delete_app_password(email)
    print(f"✓ {email} 의 키체인 항목을 삭제했습니다.")
    return 0


def cmd_import_signature(email: str | None, path: str) -> int:
    import os
    final_email = email or os.environ.get("MAILPLUG_EMAIL", "").strip()
    if not final_email:
        print("--email <주소> 또는 환경변수 MAILPLUG_EMAIL 이 필요합니다.", file=sys.stderr)
        return 2
    p = Path(path).expanduser().resolve()
    if not p.is_file():
        print(f"파일을 찾을 수 없습니다: {p}", file=sys.stderr)
        return 2
    html = p.read_text(encoding="utf-8")
    store_mailplug_signature(final_email, html)
    print(f"✓ 서명 HTML({len(html)} bytes)을 {final_email} 캐시에 저장했습니다.")
    print(f"  캐시 위치: {Path.home() / '.mailplug-mcp' / 'signature_cache.json'}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mailplug-mcp-setup",
        description="Store the Mail Plug app password in the OS keyring and (optionally) import a signature.",
    )
    p.add_argument("--email", help="Mail Plug 메일 주소. 생략하면 대화형 입력.")
    p.add_argument("--reset", action="store_true", help="키체인에서 해당 이메일 항목을 삭제.")
    p.add_argument(
        "--import-signature",
        metavar="PATH",
        help="Mail Plug에 등록된 서명 HTML 파일을 캐시에 저장.",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()

    if args.reset:
        return cmd_reset(args.email)
    if args.import_signature:
        return cmd_import_signature(args.email, args.import_signature)
    return cmd_setup(args.email)


if __name__ == "__main__":
    sys.exit(main())
