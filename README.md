# mailplug-mcp

Mail Plug 메일을 Claude에서 **잘 쓰고, 깨지지 않게 보내고, 받은 편지함을 검색·읽는** MCP 서버.

핵심 가치 한 줄: 회사가 직원의 메일 비밀번호를 보관하지 않고도, 각 직원이 자기 PC의 키체인에 자기 앱 비밀번호만 두면 Claude가 그 사람 명의로 한국어 비즈니스 메일 서식을 흐트러뜨리지 않고 발송하고, 받은 메일을 읽고 검색할 수 있습니다.

---

## 1. 왜 이게 필요한가

- 새 Outlook for Mac은 Mail Plug IMAP과 호환성 문제가 있어 계정 추가가 실패합니다(Microsoft Cloud 검증 단계에서 실패).
- 그렇다고 Apple Mail 같은 일반 메일 클라이언트에 등록해 두면 Claude가 그 메일에 접근하지 못합니다.
- Microsoft 365 커넥터로 우회해도 회사 메일을 Microsoft Cloud로 동기화해야 하고, 발신은 you@example.com 명의로 못 보냅니다.

이 MCP는 그 사이를 정확히 이어줍니다 — Claude는 Mail Plug에 직접 SMTP로 발송하고 IMAP으로 수신을 봅니다. 중간 클라우드 없음, 외부 서비스 없음, 비밀번호 서버 보관 없음.

---

## 2. 도구 목록

| 도구 | 설명 |
|------|------|
| `draft_email` | 마크다운 본문을 인라인 CSS HTML로 렌더링하고 미리보기를 반환. **발송하지 않음.** |
| `send_draft` | `draft_id`로 만든 초안을 실제로 발송. `confirmed=True` 필수. |
| `discard_draft` | 발송하지 않고 초안 폐기. |
| `list_drafts` | 발송 대기 중인 초안 목록. |
| `list_inbox` | 받은편지함의 envelope 목록 (최신순). |
| `search_email` | 키워드 검색 (한글 가능). |
| `get_email` | 단일 메일 본문(plain+html) + 첨부 메타데이터. |
| `download_attachment` | 첨부 파일 로컬 저장. |
| `list_folders` | IMAP 폴더 목록 (사용자 폴더명 확인용). |

발신은 **반드시 두 단계**(draft → 사용자 확인 → send)로만 가능합니다. Claude가 혼자 발송할 수 없도록 구조적으로 막아 두었습니다.

---

## 3. 시스템 요구사항

- macOS 12+ / Windows 10+ / Linux (keyring 백엔드가 있는 모든 OS)
- Python 3.10 이상
- Mail Plug 계정 + 앱 비밀번호 (Mail Plug 웹메일 → 환경설정 → 로그인 보안 설정 → 앱 비밀번호)
- Mail Plug 측 IMAP/SMTP 사용 ON (환경설정 → 메일 → IMAP 탭)

---

## 4. 설치

### (a) `uv` 사용 — 권장

```bash
# repo clone + 의존성 설치 + 가상환경 한 방
git clone https://github.com/YOUR-USERNAME/mailplug-mcp.git
cd mailplug-mcp
uv venv
uv pip install -e ".[dev]"
```

### (b) `pip` 사용

```bash
git clone https://github.com/YOUR-USERNAME/mailplug-mcp.git
cd mailplug-mcp
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

설치가 끝나면 두 개의 명령어가 PATH에 등록됩니다:

- `mailplug-mcp` — MCP 서버 본체 (Claude가 호출)
- `mailplug-mcp-setup` — 키체인 저장 / 서명 임포트 등 1회성 설정

---

## 5. 1회 셋업

### 5.1 환경 변수

`.env.example`을 `.env`로 복사하고 본인 정보로 채우세요. **비밀번호는 절대 .env에 적지 마세요.**

```bash
cp .env.example .env
```

수정할 항목 (필수만):

```env
MAILPLUG_EMAIL=you@example.com
MAILPLUG_DISPLAY_NAME=홍길동
MAILPLUG_SIGNATURE_MODE=auto
MAILPLUG_SIGNATURE_NAME=홍길동
MAILPLUG_SIGNATURE_TITLE=직책
MAILPLUG_SIGNATURE_COMPANY=회사명
MAILPLUG_SIGNATURE_PHONE=010-0000-0000
MAILPLUG_SIGNATURE_WEBSITE=example.com
```

### 5.2 앱 비밀번호 키체인 저장

```bash
mailplug-mcp-setup
# Mail Plug 이메일 주소 [you@example.com]: ↵
# 앱 비밀번호: (입력 시 표시되지 않음)
# ✓ you@example.com 의 앱 비밀번호가 키체인에 저장되었습니다.
```

저장 위치:

- macOS: Keychain Access → "mailplug-mcp" 항목
- Windows: 자격증명 관리자 → "mailplug-mcp" 항목
- Linux: Secret Service (GNOME Keyring / KWallet)

비밀번호 변경: 같은 명령 다시 실행 → 덮어쓰기.
삭제: `mailplug-mcp-setup --reset --email you@example.com`.

### 5.3 (선택) Mail Plug 서명 가져오기

`MAILPLUG_SIGNATURE_MODE=mailplug` 또는 `auto`로 운영하려면, 본인이 Mail Plug에 등록해 둔 서명 HTML을 한 번 임포트해 두면 됩니다.

1. Mail Plug 웹메일 → 환경설정 → 메일 → 서명 → 본인 서명 편집기에서 "HTML 보기" 클릭 → 표시된 HTML 전체를 파일(`signature.html`)로 저장.
2. 다음 명령으로 캐시 등록:

```bash
mailplug-mcp-setup --import-signature signature.html
```

캐시 위치: `~/.mailplug-mcp/signature_cache.json`

이후 `signature_mode=auto`로 두면 우선 이 캐시를 쓰고, 없으면 `.env`의 `MAILPLUG_SIGNATURE_*` 값으로 자동 생성된 템플릿 서명을 씁니다.

---

## 6. Claude Desktop / Claude Code에 등록

### 6.1 Claude Desktop (`claude_desktop_config.json`)

macOS 위치: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "mailplug": {
      "command": "/절대경로/mailplug-mcp/.venv/bin/mailplug-mcp",
      "env": {
        "MAILPLUG_EMAIL": "you@example.com",
        "MAILPLUG_DISPLAY_NAME": "홍길동",
        "MAILPLUG_SIGNATURE_MODE": "auto",
        "MAILPLUG_SIGNATURE_NAME": "홍길동",
        "MAILPLUG_SIGNATURE_TITLE": "직책",
        "MAILPLUG_SIGNATURE_COMPANY": "회사명",
        "MAILPLUG_SIGNATURE_PHONE": "010-0000-0000",
        "MAILPLUG_SIGNATURE_WEBSITE": "example.com"
      }
    }
  }
}
```

`command` 경로는 `which mailplug-mcp`로 확인하세요. 가상환경의 절대 경로를 그대로 적습니다.

### 6.2 Claude Code

워크스페이스 루트의 `.mcp.json` 또는 사용자 글로벌 `~/.claude/mcp.json`에 동일한 블록을 추가하면 됩니다.

### 6.3 Cowork 모드

Cowork는 Claude Desktop 위에서 동작하므로 6.1과 동일.

설정 후 Claude를 재시작하면 도구 목록에 9개의 `mp_*` 도구가 등장합니다.

---

## 7. 사용 예

### 7.1 발신

> 사용자: "you@example.com 발신으로 boss@example.com 한테 '주간 보고 첨부 드립니다' 라는 메일 써줘. 본문은 이번 주 핵심 3가지 정리해서 한 줄씩, 마지막에 다음 주 일정 두 줄."

Claude가 `draft_email`을 호출 → 미리보기 표시 → 사용자께 "이대로 보낼까요?" 확인 → 명시 승인 → `send_draft(confirmed=True)` 호출 → 실제 발송.

### 7.2 수신·검색

> 사용자: "이번 주에 김태영 님한테 받은 메일 찾아줘"

Claude가 `search_email(query="김태영", limit=20)` → 결과 envelope 5건 → 사용자가 그중 하나 선택 → `get_email(uid=...)` 로 본문 펼치기.

### 7.3 첨부 다운로드

> 사용자: "방금 그 메일에 붙어 있던 PDF, 데스크탑에 저장해줘"

`download_attachment(uid=..., attachment_index=2, save_to="~/Desktop/report.pdf")`.

---

## 8. 보안 모델

- 앱 비밀번호는 OS 키체인에만 저장. 코드·git·설정 파일에는 절대 들어가지 않음.
- 회사가 직원의 비밀번호를 보관하지 않음(각자 키체인).
- 발신은 `confirmed=True` 명시 플래그 없이는 SMTP가 호출되지 않음(자동 발송 사고 방지).
- 받은 메일 본문은 Claude 컨텍스트에 들어오지만 외부 학습 데이터로 쓰이지 않음(Anthropic 정책).
- Bcc 주소는 헤더에 포함되지 않고 SMTP envelope에만 들어감 (RFC 5321 / 5322 표준).
- TLS는 SMTP_SSL(465) / IMAP_SSL(993) 모두 SSLContext.create_default_context() 기본값을 사용 — 인증서 검증 활성, 약한 cipher 차단.

---

## 9. 트러블슈팅

| 증상 | 원인 / 조치 |
|------|------------|
| `RuntimeError: MAILPLUG_EMAIL is not set` | `.env` 작성 후 Claude 재시작. Claude Desktop의 env 블록 직접 사용도 OK. |
| `CredentialError: No app password found in keyring` | `mailplug-mcp-setup` 실행. 이미 했다면 `--email` 인자 일치 여부 확인. |
| SMTP `Authentication failed` | (1) Mail Plug → 환경설정 → IMAP에서 사용 ON 확인, (2) 앱 비밀번호 재발급 후 setup 재실행. |
| IMAP `login failed` | 위와 동일. SMTP는 되는데 IMAP만 실패하면 일반 비밀번호를 잘못 쓴 경우가 많음. |
| HTML이 받는 쪽에서 깨짐 | `tests/test_renderer.py`로 출력 확인, 보고 부탁. premailer 인라인 누락이 의심되면 issue. |

---

## 10. 개발

```bash
pytest                    # 테스트 실행
ruff check src tests      # 정적 분석
ruff format src tests     # 포맷
```

---

## 11. 라이선스

MIT — `LICENSE` 참조.
