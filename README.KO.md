# NyaNya Agent

NyaNya Agent는 Python 중심의 가벼운 로컬 에이전트 래퍼다. Discord, Telegram, Codex 위임, 로컬 운영 대시보드를 선택적으로 함께 사용할 수 있다.

주요 목적:

- 터미널에서 LLM backend 실행,
- Discord 또는 Telegram 요청 접수,
- 허용된 workspace 안에서만 파일 작업 수행,
- 복잡한 코드/파일 작업을 Codex로 위임,
- SQLite 기반 로컬 운영 대시보드 제공,
- macOS LaunchAgent 기반 자동 실행,
- 공개 가능한 소스와 비공개 운영 데이터를 명확히 분리.

English guide: [README.md](README.md)

## 프로젝트 상태

이 저장소는 독립적인 경량 프로젝트다. 공식 Hermes Agent가 아니며, 다른 agent 프로젝트의 소스 트리를 포함하거나 복사하지 않는다.

주요 구현 파일:

```text
src/nyanya_agent/core.py              # CLI와 backend provider
src/nyanya_agent/bridge_common.py     # bridge helper 호환 export
src/nyanya_agent/bridge_constants.py  # 명령어와 routing keyword
src/nyanya_agent/bridge_policy.py     # workspace, command, safety policy helper
src/nyanya_agent/bridge_runtime.py    # Codex 위임과 runtime helper
src/nyanya_agent/bridge_store.py      # 대화 저장소와 사용자별 task queue
src/nyanya_agent/dashboard_store.py   # SQLite dashboard/event store
src/nyanya_agent/dashboard_api.py     # FastAPI dashboard server
src/nyanya_agent/discord_bridge.py    # Discord bridge
src/nyanya_agent/telegram_bridge.py   # Telegram bridge
```

## 설치

저장소를 clone하고 패키지를 설치한다.

```bash
git clone https://github.com/hcscat/nyanya-agent.git
cd nyanya-agent
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[bots,dashboard]"
cp .env.example .env
```

개발과 테스트까지 설치하려면:

```bash
python -m pip install -e ".[bots,dashboard,dev]"
```

`.env`를 열어 필요한 값만 설정한다. `.env`는 절대 커밋하지 않는다.

## 최소 설정

주요 환경 변수:

```text
NYANYA_PROVIDER=gemini_cli
NYANYA_GEMINI_CLI=gemini
NYANYA_WORKSPACE_ROOTS=/absolute/workspace/path
NYANYA_SYSTEM_PROMPT_PATH=prompts/system.md
NYANYA_DISCORD_BOT_TOKEN=
NYANYA_DISCORD_PREFIX=!nyanya
NYANYA_DISCORD_RESPOND_IN_ALLOWED_CHANNELS=false
NYANYA_DISCORD_ALLOWED_CHANNEL_IDS=
NYANYA_DISCORD_ALLOWED_USER_IDS=
NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS=
NYANYA_CODEX_ENABLED=false
NYANYA_CODEX_WRITE_ENABLED=false
NYANYA_DASHBOARD_RECORDING_ENABLED=true
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
NYANYA_DASHBOARD_DB_PATH=data/nyanya_dashboard.db
```

workspace root는 필요한 범위만 좁게 지정한다. NyaNya Agent는 sandbox가 아니라 routing과 policy layer다.

## 터미널 실행

backend 설정 확인:

```bash
./scripts/check_backend.sh
```

대화형 CLI:

```bash
./scripts/run_nyanya.sh
```

한 번만 prompt 실행:

```bash
./scripts/run_nyanya.sh --prompt "현재 runtime 설정을 요약해줘."
```

## Discord Bridge

Discord bridge 직접 실행:

```bash
./scripts/run_discord_bridge.sh
```

기본적으로 prefix 또는 mention으로 호출된 메시지에 응답한다.

```text
!nyanya status
@nyanya status
```

`NYANYA_DISCORD_RESPOND_IN_ALLOWED_CHANNELS=true`는 허용 채널의 모든 메시지를 agent 요청으로 처리해야 할 때만 사용한다.

주요 Discord 명령:

| 명령 | 목적 |
|---|---|
| `!nyanya status` | bridge runtime 상태 확인 |
| `!nyanya config` | 비밀값을 제외한 runtime 설정 확인 |
| `!nyanya reset` | 현재 사용자/채널 대화 context 초기화 |
| `!nyanya save` | session 저장이 켜져 있을 때 현재 대화 저장 |
| `!nyanya resources` | 로컬 시스템 리소스 정보 확인 |
| `!nyanya upload <file_path>` | 로컬 workspace 파일을 현재 Discord 채널에 업로드 |
| `!nyanya gemini <prompt>` | 설정된 Google/Gemini 계열 backend에 직접 질의 |
| `!nyanya codex <prompt>` | 검토 또는 조사 작업을 Codex에 위임 |
| `!nyanya codex-work <prompt>` | 쓰기 위임이 켜져 있을 때 코드/파일 변경 작업을 Codex에 위임 |
| `!nyanya cancel` | 현재 사용자의 대기/실행 작업 취소 |

파일 업로드 처리 순서:

1. 요청된 파일 경로를 사용자 workspace 기준으로 해석한다.
2. 경로가 허용된 workspace root 내부인지 확인한다.
3. 대상이 존재하고 파일인지 확인한다.
4. Discord attachment로 업로드한다.
5. dashboard recording이 켜져 있으면 요청 원장에 기록한다.

## Telegram Bridge

Telegram bridge 직접 실행:

```bash
./scripts/run_telegram_bridge.sh
```

사용 전에 `.env`에 Telegram token과 허용 chat/user 값을 설정한다.

## Dashboard

Dashboard 직접 실행:

```bash
./scripts/run_dashboard.sh
```

기본 URL:

```text
http://127.0.0.1:8765
```

대시보드는 세 화면으로 나뉜다.

| 화면 | 목적 | 주요 내용 |
|---|---|---|
| 메인 | 현재 운영 상태 확인 | 전체 요청, 오늘 요청, 실행 중 요청, 실패, 확인 필요 단계 |
| 프로젝트 | 프로젝트와 단계 운영 | 프로젝트 생성, 목표 입력, 단계 카드, 단계 체크 |
| 통계 | 과거 이력 분석 | 사용량 추이, 요청 원장, 감사 로그 |

기본 DB:

```text
data/nyanya_dashboard.db
```

dashboard DB, WAL/SHM 파일, 실제 요청 로그, private export는 커밋하지 않는다.

## 프로젝트와 단계 추적

Dashboard에서 프로젝트를 만들면 다음 API가 호출된다.

```text
POST /v1/projects
```

store는 다음을 수행한다.

1. project row 생성,
2. status를 `active`로 설정,
3. health를 `green`으로 설정,
4. current phase를 `planning`으로 설정,
5. `planning`, `design`, `implementation`, `test` 네 단계 생성,
6. `planning`을 `running`으로 설정,
7. 나머지 단계를 `waiting`으로 설정,
8. audit log 기록.

단계 체크 API:

```text
POST /v1/projects/{project_id}/phases/{phase_key}/check
```

단계에 `next_action`이 있으면 결과가 `needs_confirmation`이 되고 Discord 확인 메시지 후보가 생성된다. 다음 작업이 없으면 결과는 `ok`다.

## macOS 서비스 관리

NyaNya는 macOS LaunchAgent 관리 명령을 제공한다.

설치와 시작:

```bash
./scripts/nyanya_ctl.sh install
./scripts/nyanya_ctl.sh dashboard-install
./scripts/nyanya_ctl.sh start-all
```

재시작:

```bash
./scripts/nyanya_ctl.sh restart-all
```

상태 확인:

```bash
./scripts/nyanya_ctl.sh status-all
```

health와 smoke check:

```bash
./scripts/nyanya_ctl.sh health
./scripts/nyanya_ctl.sh dashboard-health
./scripts/nyanya_ctl.sh deep-health
./scripts/nyanya_ctl.sh smoke
```

Codex 정책:

- Discord bridge가 messenger 요청의 runtime entrypoint다.
- Dashboard는 별도 로컬 관측 프로세스다.
- Codex는 별도 복구/위임 채널이다.
- `start-all`, `restart-all`, `health`, `repair`는 Codex를 agent 프로세스에 포함하거나 관리하지 않는다.
- Codex 앱 lifecycle은 `codex-status`, `codex-start`, `codex-install`, `codex-uninstall`로 확인한다.

## NPM Wrapper

이 프로젝트는 Python 기반이지만 공유 편의를 위해 npm wrapper를 제공한다.

```bash
npm install -g @hcscat/nyanya-agent
nyanya-agent --help
```

npm package는 `python3`와 bundled `src/` package를 실행한다. Python을 대체하지 않는다.

## 보안 모델

NyaNya Agent는 sandbox가 아니다. routing, policy, operations layer다.

핵심 guardrail:

- allowed workspace roots,
- protected delete paths,
- per-user task queue,
- SQLite request/audit ledger,
- local `.env` secrets,
- optional Codex sandbox settings.

절대 공개하지 않을 것:

- `.env`와 실제 환경 변수 값,
- Discord/Telegram bot token,
- OAuth token, API key, browser cookie, credential cache,
- 실제 Discord guild/channel/user ID,
- `config/user_workspaces.json`,
- `data/`, `logs/`, `downloads/`, `sessions/`, `run/`,
- private prompt, transcript, attachment,
- 실제 요청 데이터가 들어간 dashboard DB/export.

## Dashboard 외부 접근

안전한 기본값은 로컬 전용이다.

```text
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
```

원격 접근 권장 순서:

1. 가능하면 로컬 전용 유지.
2. 개인 장치 접근은 Tailscale Serve 사용.
3. 공개 hostname이 필요하면 Cloudflare Tunnel + Access 사용.
4. 공유기 포트포워딩은 TLS, 인증, reverse proxy가 있을 때만 최후 수단으로 사용.

FastAPI dashboard를 인증 없이 공인 인터넷에 직접 노출하지 않는다.

## 테스트

단위 테스트:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q
```

Dashboard 관련 focused lint:

```bash
PYTHONPATH=src .venv/bin/python -m ruff check \
  src/nyanya_agent/dashboard_api.py \
  src/nyanya_agent/dashboard_store.py \
  tests/test_dashboard_store.py \
  tests/test_bridge_dashboard_recording.py
```

Dashboard JavaScript 문법 확인:

```bash
node --check src/nyanya_agent/dashboard_static/app.js
```

Python compile:

```bash
.venv/bin/python -m compileall -q src
```

현재 참고 사항: 전체 저장소 Ruff는 bridge compatibility module의 기존 wildcard import로 인해 실패할 수 있다. 이는 별도 cleanup 작업으로 분리한다.

## 문서

- [Copyright review](docs/copyright_review.md)
- [Public and private source policy](docs/source_publication_policy.md)
- [Discord bot rename guide](docs/discord_bot_rename_guide.md)
- [Operations guide](docs/operations_guide.md)
- [External dashboard access guide](docs/external_dashboard_access.md)
- [Why many agents use TypeScript](docs/typescript_agent_ecosystem.html)
- [CLI session agent development cycle](docs/cli_session_agent_development_cycle.html)

## License

MIT
