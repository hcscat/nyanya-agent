# NyaNya Agent

NyaNya Agent는 작업공간을 원격으로 요청·관리하기 위한 Python 중심의
**Local Control Plane**이다. 터미널과 Discord 요청은 설정된 provider 또는
Codex를 호출하기 전에 SQLite durable task/execution 원장에 기록된다.
대시보드는 지시보다 모니터링·관리 중심이다.

주요 목적:

- 터미널에서 LLM backend 실행,
- Discord 또는 Telegram 요청 접수,
- 허용된 workspace 안에서만 파일 작업 수행,
- 복잡한 코드/파일 작업을 Codex로 위임,
- SQLite 기반 durable task/execution 원장과 로컬 운영 대시보드 제공,
- macOS LaunchAgent 기반 자동 실행,
- 공개 가능한 소스와 비공개 운영 데이터를 명확히 분리.

English guide: [README.md](README.md)

보안 경계·취약점 제보 안내는 [SECURITY.md](SECURITY.md), 개발·Codex 리뷰 지침은 공개 루트 `AGENTS.md`를 참고한다. 개인 로컬 지침은 Git에서 제외하며 모든 AGENTS 파일은 실행용 패키지에서 제외한다.

## P0 실행 구조 갱신 (2026-09-12)

현재 완료 범위·남은 작업·검증 결과는 [개발 현황](docs/development_status.md)을 참고한다.

운영 설치본과 개발 저장소를 분리한 환경에서는 `source` checkout 안에서 Git과
개발 검사를 실행한다. [개발 환경 분리 안내](docs/installation_and_distribution.md#separate-an-operational-workspace-from-development)를 참고한다.

Terminal/Discord 요청은 직렬화된 작업 명세와 별도 worker를 통해 제한된 수로 병렬 처리합니다.
Gemini Flash가 요청을 판단하고 Flash/Luna/Astra를 선택합니다. 기존 파일은 구체적인 변경안과
정확한 승인 hash를 확인한 후에만 수정합니다. 중단된 요청은 보류하고 원인을 조회할 수 있습니다.
[구현·명령어·검증 안내](docs/p0_execution_20260912.md)에서 지원 범위와 남은 제약을 확인하세요.
이 설명은 소스 구현 기준이며 운영 Discord 서비스에 배포되었다는 뜻은 아닙니다.

## 프로젝트 상태

이 저장소는 독립적인 경량 프로젝트다. 공식 Hermes Agent가 아니며, 다른 agent 프로젝트의 소스 트리를 포함하거나 복사하지 않는다.

현재 소스 버전은 `0.3.0`이다. npm에 공개된 버전은 `npm view @hcscat-dev/nyanya-agent version`으로 확인할 수 있다.

주요 구현 파일:

```text
src/nyanya_agent/core.py              # CLI와 backend provider
src/nyanya_agent/bridge_common.py     # bridge helper 호환 export
src/nyanya_agent/bridge_constants.py  # 명령어와 routing keyword
src/nyanya_agent/bridge_policy.py     # workspace, command, safety policy helper
src/nyanya_agent/bridge_runtime.py    # Codex 위임과 runtime helper
src/nyanya_agent/bridge_store.py      # 대화 컨텍스트와 durable task service 연동
src/nyanya_agent/task_service.py      # 호환용 callback task service
src/nyanya_agent/operation_service.py # 일반 요청·제어용 직렬화 operation facade
src/nyanya_agent/operation_worker.py  # 별도 worker와 제한된 동시 실행
src/nyanya_agent/reviewed_changes.py  # 불변 파일안·승인 적용·journal
src/nyanya_agent/dashboard_store.py   # SQLite dashboard/event store
src/nyanya_agent/execution_store.py   # versioned task/execution/approval ledger
src/nyanya_agent/execution_adapters.py # subprocess, tmux, Codex, Antigravity adapter
src/nyanya_agent/execution_runtime.py # adapter lifecycle, recovery, writer lease coordinator
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
NYANYA_CODEX_PROFILE=nyanya-readonly
NYANYA_CODEX_WRITE_PROFILE=nyanya-approved-write
NYANYA_ANTIGRAVITY_SANDBOX=true
NYANYA_DASHBOARD_RECORDING_ENABLED=true
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
NYANYA_DASHBOARD_DB_PATH=data/nyanya_dashboard.db
NYANYA_DASHBOARD_CONTROL_TOKEN_FILE=data/dashboard_control.token
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
| `!nyanya reset` | 호환용 대화 context 초기화; 일반 operation에는 아직 연결되지 않음 |
| `!nyanya save` | 설정 시 호환용 context 저장; 실제 Codex 세션 지속 기능은 아님 |
| `!nyanya resources` | 로컬 시스템 리소스 정보 확인 |
| `!nyanya tasks` | 현재 사용자의 펜딩/진행/대기 작업 목록 확인 |
| `!nyanya tasks all` | 전체 사용자의 작업 목록 확인, 관리자 전용 |
| `!nyanya upload <file_path>` | 로컬 workspace 파일 업로드. 설정된 파일공유 채널 밖에서 실행하면 `NYANYA_DISCORD_FILE_SHARE_CHANNEL_IDS` 채널로 전송 |
| `!nyanya gemini <prompt>` | Flash 판단 후 Flash profile로 실행 |
| `!nyanya codex <prompt>` | Flash 판단 후 Luna/Codex profile로 실행 |
| `!nyanya codex-work <prompt>` | Luna/Codex로 파일 변경안 작성; 기존 파일 적용은 정확한 변경안 승인 필요 |
| `!nyanya cancel` | 현재 사용자의 대기/실행 작업 취소 |

장시간 작업 가시성:

- 접수 시 task ID와 예정 단계를 반환하고 watcher가 저장 결과 전송을 시도한다.
- `tasks`, `why 작업ID`, `recovery`, `result 작업ID`로 상태와 결과를 조회한다.
- 일반 operation의 중간 heartbeat 전달과 접수 안내·결과의 전송 순서는 보장하지 않는다.
  기존 progress/delay 설정은 호환 경로에만 적용된다.
- 재시작 후 자동 결과 재전달과 receipt/outbox는 후속 작업이다.

중요 작업 정책:

- 등록된 workspace의 제한된 임시 snapshot으로 요청을 분석한다.
- 신규 UTF-8 파일은 작업 폴더 안에 기존 파일을 덮어쓰지 않고 생성할 수 있다.
- 기존 파일 수정·삭제는 `plan`, 필요 시 `plan-file`로 검토한 뒤
  `approve 변경안ID plan_hash`로 승인한다. 승인 단어만으로 권한을 부여하지 않는다.
- 임의 shell, 설치·배포·권한 변경과 디렉터리 이동은 일반 파일안 경로의 지원 작업이 아니다.
- 외부 내용은 신뢰하지 않는다. snapshot 필터와 CLI sandbox 옵션은 완전한
  비밀정보 검출이나 호스트 보안 격리를 보장하지 않는다.

파일 업로드 처리 순서:

1. 명시한 파일을 원 요청자의 등록 workspace 안에서 no-follow로 열고 single-link 일반 파일인지 확인합니다. 인증·세션·키 경로는 차단하며 일반 reports/data/private 폴더 이름만으로는 막지 않습니다.
2. 설정한 목적지와 SDK의 guild 파일 크기 정보를 확인합니다. 조회 실패 시 다른 채널로 보내지 않으며, 실제 상한은 SDK 한도와 8 MiB 중 작은 값입니다.
3. 고정한 원본 bytes 전체를 로컬에서 검사합니다. UTF-8·BOM UTF-16·CP949 텍스트와 제한된 text-only DOCX/XLSX/PPTX를 지원합니다. PDF·이미지·암호화·미지원/불완전 추출 문서는 보류합니다. 모델 호출·OCR·파서 다운로드는 하지 않습니다.
4. 인증정보는 확인으로 우회할 수 없습니다. 개인정보 패턴은 종류·개수만 표시하고 원 요청자가 원 채널에서 upload-approve <id> <sha256>로 확인해야 합니다. upload-reject/upload-cancel로 닫을 수 있습니다. 확인은 300초 동안 한 파일·목적지·한 번의 전송에만 유효합니다.
5. 전송 직전에 사용자·대화·workspace·상대경로·파일 identity·SHA256·목적지를 재검사합니다. 변경·잘못된 hash·거절·사전 취소·만료·재사용은 전송을 승인하지 않습니다. 검사한 bytes 그대로 전송합니다.
6. 전송 시작 뒤 취소/오류는 전달 여부가 불확실할 수 있으므로 자동 재전송하지 않습니다. 패턴 무검출은 개인정보가 없다는 보장이 아닙니다.

자세한 검사 범위와 한계는 [업로드 보안 계약](docs/security_and_reliability.md#upload-file-boundary)을 참고하세요. 이 경로는 파일 공유이며 모델의 PDF/이미지 이해 기능을 추가하지 않습니다.

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

대시보드는 다섯 화면으로 나뉜다.

| 화면 | 목적 | 주요 내용 |
|---|---|---|
| 메인 | 현재 운영 상태 확인 | 전체 요청, 오늘 요청, 실행 중 요청, 실패, 확인 필요 단계 |
| 에이전트실 | 실행 제어면 관찰 | Host, Agent, Task, Execution, Approval, 2D 상태 구역, 인증된 5초 주기 조회 |
| 프로젝트 | 프로젝트와 단계 운영 | 프로젝트 생성, 목표 입력, 단계 카드, 단계 체크 |
| 메모리 | 장기기억 검토 | pending/approved 기억 후보, memory graph, technology graph |
| 통계 | 과거 이력 분석 | 사용량 추이, 요청 원장, 감사 로그 |

기본 DB:

```text
data/nyanya_dashboard.db
```

dashboard DB, WAL/SHM 파일, 실제 요청 로그, private export는 커밋하지 않는다.

### 실행 원장과 제어 API

`0.3.0`부터 기존 `agent_requests`를 유지하면서 versioned migration으로 다음 원장을 추가한다.

- `hosts`, `agent_profiles`, `agent_tasks`, `executions`
- `execution_projects`, project별 `codex_sessions`
- `runtime_sessions`, append-only `execution_events`
- `approvals`, `artifacts`, `writer_leases`

일반 터미널/Discord 요청은 `operation_service.py`와 별도 worker를 통해 저장된
OperationSpec을 실행한다. 업로드 callback은 호환용 `task_service.py` 경로를 유지한다.
대시보드는 모니터링과 인증된 관리가 우선이다.

루프백 읽기를 포함한 모든 `/v1/` 데이터·상태 변경 API는 `NYANYA_DASHBOARD_CONTROL_TOKEN` 또는 owner-only token file 인증이 필요하다. 정확한 Host/Origin 검사도 적용한다. token은 URL, HTML, 로그, Git에 기록하지 않는다. 정적 화면과 health는 인증 없이 열리지만 운영 기록을 제공하지 않는다.

주요 API:

```text
GET  /v1/hosts
GET  /v1/agents
GET  /v1/tasks
GET  /v1/execution-projects
GET  /v1/execution-projects/{id}/codex-sessions
GET  /v1/executions
GET  /v1/approvals
GET  /v1/events
GET  /v1/events/stream
POST /v1/operations
POST /v1/operations/control
POST /v1/approvals/{approval_id}/decision
POST /v1/executions/{execution_id}/cancel
POST /v1/recovery/reconcile
```

POSIX UTF-8 일반 파일의 파일별 승인·적용 경로는 구현되어 있다. 승인에는 owner,
불변 plan hash와 만료를 결합하고 적용 시 원본 hash와 worker 소유권을 재검사한다.
중단된 파일 효과는 reconcile이 필요하다. `POST /v1/tasks`는 draft이며 실제 실행
접수는 `/v1/operations`다. 상세 제한은 [P0 계약](docs/p0_execution_20260912.md)을 참조한다.

실행 adapter는 managed subprocess, tmux, Codex, Antigravity를 지원한다.
Orca는 현재 기본 adapter registry와 제품 방향에서 제외한다.

SQLite 온라인 백업과 복구:

```bash
./scripts/backup_state.sh
NYANYA_RESTORE_CONFIRM=YES ./scripts/restore_state.sh data/backups/<stamp>/nyanya_dashboard.db
```

복구는 NyaNya 서비스를 모두 중지한 뒤 수행한다. 상세 구조와 상태 전이는 [실행 제어면 운영 문서](docs/execution_control_plane.md)를 참고한다.

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

호환용 메모리 하위 시스템에는 두 계층이 있다. 일반 Discord operation에는 아직
이 기억이나 이전 대화가 주입되지 않는다. 터미널 REPL은 제한된 프로세스 내 대화를
프롬프트에 포함하지만 재시작 후 지속되는 외부 모델 세션은 아니다.

| 계층 | 목적 | 저장 위치 |
|---|---|---|
| 기본 기억 | 시스템 프롬프트에 들어가는 압축된 운영 사실 | `prompts/agent_memory.md` |
| 동적 기억 | 요청 기록에서 추출하고 검토할 수 있는 기억 후보 | SQLite `memory_items` |

동적 기억 흐름:

1. legacy connector envelope가 있는 요청을 request read model에서 조회한다.
2. memory worker가 완료 envelope를 스캔한다. envelope가 없는 terminal/dashboard/
   Telegram operation은 이 추출 원본에 포함되지 않는다.
3. 규칙 기반 추출로 `pending` 기억 후보를 만든다.
4. 민감 내용은 redaction하거나 skip한다.
5. 필요한 경우에만 LLM refinement를 켤 수 있다.
6. dashboard에서 후보를 승인 또는 거절한다.
7. 호환용 검색 함수는 owner 범위의 승인된 비민감 기억만 사용한다.
   일반 operation과의 연결은 후속 작업이다.

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

현재 설치/배포 구조는 [설치와 배포](docs/installation_and_distribution.md)에
정리되어 있다. Python runtime과 TypeScript CLI는 서로 분리된 계층으로 유지한다.

## 보안 모델

NyaNya Agent는 sandbox가 아니다. routing, policy, operations layer다.

핵심 guardrail:

- allowed workspace roots,
- trusted workspace roots,
- protected delete paths,
- per-user task queue,
- 고위험 작업의 계획 우선 승인,
- SQLite request/audit ledger,
- 호환용 검색 함수에서 owner 범위의 approved memory만 사용,
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

2026-09-21 기준 외부 접속과 서버·DB·호스팅 구성은 보류한다.
아래 내용은 추후 별도로 진행할 때의 참고 자료다.

안전한 기본값은 로컬 전용이다.

```text
NYANYA_DASHBOARD_HOST=127.0.0.1
NYANYA_DASHBOARD_PORT=8765
```

원격 접근 권장 순서:

1. 가능하면 로컬 전용 유지.
2. 개인 장치 접근은 Tailscale Serve 사용.
3. 공개 hostname이 필요하면 Cloudflare Tunnel + Access 사용.
4. 공유기 직접 포트포워딩은 승인된 배포 방식이 아니다.

FastAPI dashboard를 인증 없이 공인 인터넷에 직접 노출하지 않는다.

## 테스트

단위 테스트:

```bash
PYTHONPATH=src .venv/bin/python -m pytest -q tests
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

- [문서 인덱스](docs/README.md)
- [아키텍처와 로드맵](docs/architecture_and_roadmap.md)
- [실행 제어면](docs/execution_control_plane.md)
- [Canonical 운영 정책](prompts/policy.md)
- [설치와 배포](docs/installation_and_distribution.md)
- [운영 가이드](docs/operations_guide.md)
- [Dashboard 외부 접근](docs/external_dashboard_access.md)
- [사용자 수용 테스트](docs/user_acceptance_tests_ko.md)
- [Copyright review](docs/copyright_review.md)
- [Public and private source policy](docs/source_publication_policy.md)

## License

MIT
