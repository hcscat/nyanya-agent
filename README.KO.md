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

현재 패키지 릴리스는 `0.2.0`이다. npm에 공개된 버전은 `npm view @hcscat-dev/nyanya-agent version`으로 확인할 수 있다.

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
src/nyanya_agent/memory_worker.py     # 장기기억 후보를 정리하는 background worker
src/nyanya_agent/discord_bridge.py    # Discord bridge
src/nyanya_agent/telegram_bridge.py   # Telegram bridge
```

## npm 설치

일반 사용자는 npm으로 CLI를 설치한 뒤 `setup`을 먼저 실행한다. `doctor`는 setup 이후에 실행한다.

```bash
npm install -g @hcscat-dev/nyanya-agent
nyanya setup --all
nyanya doctor
```

`npm install`은 Node/TypeScript CLI만 설치한다. Python 가상환경과 `discord.py`, `fastapi`, `uvicorn` 같은 Python 의존성은 `nyanya setup`에서 생성/설치한다. 대화형 터미널에서는 LLM provider와 Discord/Telegram 연결 설정을 바로 선택할 수 있다. 자동 설치 환경에서는 `nyanya setup --all --non-interactive`를 사용한다.

`--all`은 macOS에서 dashboard, Discord bridge, memory worker LaunchAgent를 함께 구성한다. Discord token이 없으면 Discord bridge만 안전하게 건너뛰고 dashboard와 memory worker를 시작한다. `postinstall`은 Python 부재와 설치 side effect 문제 때문에 사용하지 않는다.

npm 패키지 코드와 사용자 상태는 분리된다. 기본 상태 경로:

| OS | `NYANYA_HOME` 기본값 |
|---|---|
| macOS | `~/Library/Application Support/NyaNya Agent` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/nyanya-agent` |
| Windows | `%LOCALAPPDATA%\NyaNya Agent` |

`.env`, `.venv`, SQLite DB, logs, sessions는 `NYANYA_HOME` 아래에 유지되므로 npm 업데이트로 삭제되지 않는다. 기존 소스 checkout에 `.env`가 있으면 호환을 위해 해당 소스 폴더를 상태 경로로 계속 사용한다.

설정과 상태 확인:

```bash
nyanya config             # LLM과 SNS 대화형 설정
nyanya config show        # 비밀값을 제외한 설정 상태
nyanya config validate    # 설정 변경 시 사용하는 내장 검증
nyanya auth               # LLM provider 설정만 변경
nyanya paths              # code/state/env/dashboard 경로 확인
nyanya state backup       # 설정, DB, session 백업
```

Discord, Telegram token을 설정하지 않으면 해당 bridge는 비활성 상태다. Slack connector는 아직 포함되지 않는다.

서비스 제어:

```bash
nyanya service start
nyanya service status
nyanya service stop
nyanya service uninstall
nyanya update
```

`nyanya service stop`은 NyaNya Agent가 관리하는 Discord bridge, dashboard, memory worker 서비스를 함께 중지한다. 격리 테스트에서는 `NYANYA_SERVICE_LABEL_PREFIX`를 별도로 지정해 운영 서비스가 아닌 테스트 서비스만 제어한다.

업데이트는 `npm update -g @hcscat-dev/nyanya-agent` 후 `nyanya setup --non-interactive`를 실행한다. 삭제할 때는 먼저 `nyanya service uninstall`을 실행하고 `npm uninstall -g @hcscat-dev/nyanya-agent`를 실행한다. npm package를 삭제해도 `NYANYA_HOME` 데이터는 자동 삭제하지 않는다.

`0.1.x` 설치본에서 package directory 안에 실제 `.env`나 DB를 만든 경우에는 `0.2.0`으로 업데이트하기 전에 해당 파일을 별도 경로에 백업해야 한다. `0.2.0` 이후에는 `nyanya state backup`과 `nyanya state migrate`를 사용한다. 현재 소스 checkout 운영은 legacy state 자동 감지로 기존 경로를 유지한다.

## 소스 설치

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
NYANYA_TRUSTED_WORKSPACE_ROOTS=/absolute/trusted/path
NYANYA_SYSTEM_PROMPT_PATH=prompts/system.md
NYANYA_AGENT_MEMORY_PATH=prompts/agent_memory.md
NYANYA_DISCORD_BOT_TOKEN=
NYANYA_DISCORD_PREFIX=!nyanya
NYANYA_DISCORD_RESPOND_IN_ALLOWED_CHANNELS=false
NYANYA_DISCORD_ALLOWED_CHANNEL_IDS=
NYANYA_DISCORD_ALLOWED_USER_IDS=
NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS=
NYANYA_DISCORD_FILE_SHARE_CHANNEL_NAMES=
NYANYA_CODEX_ENABLED=false
NYANYA_CODEX_WRITE_ENABLED=false
NYANYA_DASHBOARD_RECORDING_ENABLED=true
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
NYANYA_DASHBOARD_DB_PATH=data/nyanya_dashboard.db
NYANYA_MEMORY_RETRIEVAL_ENABLED=true
NYANYA_MEMORY_WORKER_INTERVAL_SECONDS=1800
NYANYA_MEMORY_WORKER_LLM_REFINEMENT=false
```

`NYANYA_HOME`은 `.env`를 찾기 전에 결정해야 하므로 shell 또는 LaunchAgent 환경에서 설정한다. `.env` 안의 상대 경로는 mutable data의 경우 `NYANYA_HOME`, system prompt 같은 package asset은 code root 기준으로 해석한다.

workspace root는 필요한 범위만 좁게 지정한다. NyaNya Agent는 sandbox가 아니라 routing과 policy layer다.

workspace tier:

- `NYANYA_WORKSPACE_ROOTS`는 bridge가 접근 가능한 경로다.
- `NYANYA_TRUSTED_WORKSPACE_ROOTS`는 일상 작업이 예상되는 더 안전한 하위 범위다.
- allowed root 안이지만 trusted root 밖인 경로는 더 엄격한 위험도 기준을 적용한다.

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
| `!nyanya tasks` | 현재 사용자의 펜딩/진행/대기 작업 목록 확인 |
| `!nyanya tasks all` | 전체 사용자의 작업 목록 확인, 관리자 전용 |
| `!nyanya upload <file_path>` | 로컬 workspace 파일 업로드. 설정된 파일공유 채널 밖에서 실행하면 `NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS` 채널로 전송 |
| `!nyanya gemini <prompt>` | 설정된 Google/Gemini 계열 backend에 직접 질의 |
| `!nyanya codex <prompt>` | 검토 또는 조사 작업을 Codex에 위임 |
| `!nyanya codex-work <prompt>` | 쓰기 위임이 켜져 있을 때 코드/파일 변경 작업을 Codex에 위임 |
| `!nyanya cancel` | 현재 사용자의 대기/실행 작업 취소 |

장시간 작업 가시성:

- 첫 응답은 작업 계획과 현재 queue 상태를 먼저 반환한다.
- worker 시작, routing, backend/Codex 위임 단계는 진행 메시지로 별도 전송한다.
- `NYANYA_TASK_PROGRESS_INTERVAL_SECONDS` 값으로 backend 또는 Codex 응답 대기 중 heartbeat 주기를 조정한다.
- `NYANYA_TASK_START_DELAY_SECONDS` 값으로 worker 실행을 아주 짧게 지연해 계획 응답이 채팅에 먼저 표시되도록 한다.

중요 작업 정책:

- 파일 생성, 수정, 삭제, 이동, 권한 변경, 시스템 설정, 네트워크 설정, 설치, 배포, 외부 side effect가 있는 작업은 고위험 작업으로 본다.
- 고위험 요청은 바로 실행하지 않고 계획을 먼저 반환한 뒤 명시 승인을 요구한다.
- trusted root 밖이지만 allowed root 안인 작업은 더 엄격하게 점수화한다.
- 웹 또는 타인 자료에 숨은 프롬프트형 지시가 의심되면 해당 지시를 따르지 않고 보고한다.

파일 업로드 처리 순서:

1. 요청된 파일 경로를 사용자 workspace 기준으로 해석한다.
2. 경로가 허용된 workspace root 내부인지 확인한다.
3. 대상이 존재하고 파일인지 확인한다.
4. 설정된 파일공유 채널 안에서 실행한 경우 현재 채널에 Discord attachment로 업로드한다.
5. 일반 허용 채널에서 실행한 경우 첫 번째 `NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS` 채널로 업로드하고 요청 채널에는 완료 확인만 반환한다.
6. dashboard recording이 켜져 있으면 요청 원장에 기록한다.

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

대시보드는 네 화면으로 나뉜다.

| 화면 | 목적 | 주요 내용 |
|---|---|---|
| 메인 | 현재 운영 상태 확인 | 전체 요청, 오늘 요청, 실행 중 요청, 실패, 확인 필요 단계 |
| 프로젝트 | 프로젝트와 단계 운영 | 프로젝트 생성, 목표 입력, 단계 카드, 단계 체크 |
| 메모리 | 장기기억 검토 | pending/approved 기억 후보, memory graph, technology graph |
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

## 장기기억

NyaNya는 두 가지 기억 계층을 사용한다.

| 계층 | 목적 | 저장 위치 |
|---|---|---|
| 기본 기억 | 시스템 프롬프트에 들어가는 압축된 운영 사실 | `prompts/agent_memory.md` |
| 동적 기억 | 요청 기록에서 추출하고 검토할 수 있는 기억 후보 | SQLite `memory_items` |

동적 기억 흐름:

1. Discord, Telegram, CLI, dashboard 요청을 SQLite에 기록한다.
2. memory worker가 완료 상태 요청을 스캔한다.
3. 규칙 기반 추출로 `pending` 기억 후보를 만든다.
4. 민감 내용은 redaction하거나 skip한다.
5. 필요한 경우에만 LLM refinement를 켤 수 있다.
6. dashboard에서 후보를 승인 또는 거절한다.
7. `approved`이면서 민감하지 않은 기억만 이후 프롬프트에 검색 주입된다.

worker 1회 실행:

```bash
./scripts/nyanya_ctl.sh memory-worker-once
```

background worker 관리:

```bash
./scripts/nyanya_ctl.sh memory-worker-start
./scripts/nyanya_ctl.sh memory-worker-status
./scripts/nyanya_ctl.sh memory-worker-restart
```

## macOS 서비스 관리

NyaNya는 macOS LaunchAgent 관리 명령을 제공한다.

설치와 시작:

```bash
./scripts/nyanya_ctl.sh install
./scripts/nyanya_ctl.sh dashboard-install
./scripts/nyanya_ctl.sh memory-worker-install
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
- Memory worker는 별도 저비용 유지보수 프로세스다.
- Codex는 별도 복구/위임 채널이다.
- `start-all`, `restart-all`, `health`, `repair`는 Codex를 agent 프로세스에 포함하거나 관리하지 않는다.
- Codex 앱 lifecycle은 `codex-status`, `codex-start`, `codex-install`, `codex-uninstall`로 확인한다.

## NPM Wrapper

이 프로젝트는 Python 기반이지만 공유 편의를 위해 npm wrapper를 제공한다.

```bash
npm install -g @hcscat-dev/nyanya-agent
nyanya setup --all
nyanya doctor
```

npm package는 TypeScript로 개발한 CLI를 JavaScript로 빌드해서 배포한다. Python을 대체하지 않고, `nyanya setup`에서 Python runtime과 dependency를 준비한다.

설치/배포 개선의 최신 권장안은 [NyaNya Agent 설치/배포 최종 권장안](docs/nyanya_install_distribution_final_plan_20260707.md)에 정리되어 있다. 핵심 방향은 npm CLI 계층은 TypeScript로 전환하고, Python dependency, dashboard, Discord bridge, memory worker, LaunchAgent 설정은 `nyanya setup`에서 한 번에 처리하는 것이다.

## 보안 모델

NyaNya Agent는 sandbox가 아니다. routing, policy, operations layer다.

핵심 guardrail:

- allowed workspace roots,
- trusted workspace roots,
- protected delete paths,
- per-user task queue,
- 고위험 작업의 계획 우선 승인,
- SQLite request/audit ledger,
- approved memory만 검색 주입,
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

전체 lint:

```bash
.venv/bin/ruff check src/nyanya_agent tests
```

Dashboard JavaScript 문법 확인:

```bash
node --check src/nyanya_agent/dashboard_static/app.js
```

Python compile:

```bash
PYTHONPATH=src .venv/bin/python -m py_compile \
  src/nyanya_agent/core.py \
  src/nyanya_agent/bridge_policy.py \
  src/nyanya_agent/bridge_runtime.py \
  src/nyanya_agent/bridge_store.py \
  src/nyanya_agent/dashboard_store.py \
  src/nyanya_agent/memory_worker.py \
  src/nyanya_agent/manager.py \
  src/nyanya_agent/telegram_bridge.py
```

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
