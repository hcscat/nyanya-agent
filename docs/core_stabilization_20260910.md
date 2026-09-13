# CORE-STAB-01 — 구조 안정화 및 전체 소스 검토

2026-09-12 follow-up: [P0 execution contracts and verification](p0_execution_20260912.md)
supersede earlier callback-only execution, general-file write-hold and legacy mirroring
statements for normal terminal/Discord operations. Retain historical verification
and remaining delivery/session/platform limitations; source changes are not deployment.


작성: 2026-09-10. 상태: 로컬 기반 보강 구현, 검증 및 후속 인계. 안정 버전 출시 아님.

## 목표와 범위

단일 운영자의 Discord 요청을 등록된 워크스페이스에서 처리하는 Local Control Plane을 우선한다.
Python은 실행·정책·저장소·커넥터·FastAPI를, TypeScript는 설치·설정·진단·서비스 CLI를 소유한다.
SQLite를 단일 제어 호스트의 운영 원장으로 유지한다. 현재 패키지 선언은 Python 3.11 이상,
Node 18 이상이며 discord.py, FastAPI/Pydantic, TypeScript를 선택 의존성 또는 빌드 의존성으로 사용한다.
선언된 최소 버전과 모든 플랫폼의 실제 지원 검증은 구분한다.

이번 세션은 분석·구현·테스트 역할을 함께 수행했다. 별도 모델 세션 생성 또는 전환은 하지 않았다.
기준 커밋은 2182510, 브랜치는 main이다. 시작부터 다수의 수정 파일과 미추적 구현·문서가 있었으며
이를 보존했다. 이번 변경도 커밋되지 않았다. 원격 저장소와의 소스 일치, 배포 상태는 확인하지 않았다.
라이브 DB, 자격 증명, 서비스 설정은 변경하지 않았고 서비스 재시작·게시·실제 모델 작업은 수행하지 않았다.

운영자가 제시한 첫 안정 버전 방향:

- Discord 작업 분석 후 agy/Codex 및 모델을 선택하고, 필요한 경우 여러 에이전트에 분배한다.
- 등록된 사용자 워크스페이스 내부에 작업 종류·날짜 기반 폴더를 만든다.
- 새 파일 생성은 허용하되 기존 파일 수정·삭제는 대상, 이유, 변경 방향을 제시하고 피드백을 받는다.
- 중단 작업은 남겨 두고 복구 후 알린다. 사용자 판단 없이 재실행하지 않는다.
- 다중 사용자 SaaS보다 단일 운영자 사용성을 우선한다.

이 방향은 제품 목표다. 이번 코드가 이 전체 동작을 보장하는 것은 아니다.

## 검토 방식과 유지·보류 판단

공개 소스 전체를 목록화하여 Python 구문/인터페이스, TypeScript 진입점과 명령,
배포 JS, shell/PowerShell 설치·제거 경로, 정적 UI, 설정 예제, 프롬프트, CI와 테스트를 검토했다.
큐·승인·실행·경로·저장·백업·배포 경계는 구현과 테스트를 상세 추적했다.
전체 기능의 실제 동작 또는 모든 줄에 대한 독립 보안 감사를 완료했다는 의미는 아니다.
비공개 설정·데이터와 설치된 모델의 동작은 검토 입력에서 제외했다.

| 영역 | 판단 | 이번 처리 또는 후속 조건 |
|---|---|---|
| core, bridge policy/runtime/store, Discord | 유지·집중 개선 | 결과 타입, 작업 경계, 쓰기 보류, 복구 통지와 결과 조회 |
| execution store, task service, adapters, coordinator | 유지·집중 개선 | 원자적 claim/결과, heartbeat, 오래된 완료 거부; 실행 경로 통합은 다음 단계 |
| dashboard API/store/static | 기존 기능 유지, 확장 보류 | 작동하지 않는 retry 차단, 취소 상태 구분; 원격 읽기 인증·원장 read model 이관 필요 |
| memory worker/store/prompts | 기본 기능 유지, 확장 보류 | 운영자 범위 검색, 자동 호스트 정보 주입 제거; 프로젝트 격리·보존/삭제 정책 필요 |
| TypeScript CLI/runtime, dist, bin | 유지 | dist는 생성물, bin은 호환 진입점; DB 백업과 소스 배포 안전성 보강 |
| manager, shell, launchd | 유지·정리 예정 | 기존 서비스 제어 보존; 수명주기 소유자 통합 및 Codex 제어 명령 분리 필요 |
| Telegram | 호환 코드 보존, 신규 기능 보류 | Discord 완료 후 별도 승인·전달·재시작 수용시험 |
| Orca adapter | 제품 범위 제외, 삭제 이관 목록 | 참조·테스트·설정 호환성 검토 후 제거; 새로운 의존 기능 개발 금지 |
| project/session, Agent Office UI | 기본 조회 보존 | 실제 외부 세션 재개, DAG, 자원 스케줄링을 구현 완료로 표현하지 않음 |
| local LLM, OAuth/API, agy/Codex routing | 연결 기반 유지 | 명시적 capability/model profile 및 실측 기반 선택은 후속 |
| PowerShell/Homebrew/배포 CI | 정적 검토, 자격화 보류 | Windows 실제 설치/제거·최소 버전·패키지 clean install 매트릭스 필요 |
| remote host, 새 커넥터, npm 자동 게시 | 보류 | 로컬 복구·승인·전달 증거 이후 독립 작업 |

## 구현한 계약

1. 스키마 v3는 task_claims와 task_results를 추가한다. v1/v2 정의는 변경하지 않는다.
   SQLite 트랜잭션 안에서 task claim, 실행 생성, 현재 실행 지정, 이벤트를 기록한다.
   worker ID·만료시간을 검사하고 heartbeat를 갱신한다. 같은 owner의 미해제 claim은 중복 실행을 막는다.
   만료 claim은 자동 인계하지 않는다. writer lease와 task ownership은 별도다.
2. 큐는 최근 500개 이력을 경유하지 않고 전체 미완료 행에서 선택한다.
   저장된 작업에 현재 프로세스의 runner가 없으면 보류하며 자동 복원·재생하지 않는다.
   이것은 전용 독립 worker가 아니다. runner/responder는 여전히 프로세스 메모리에 있다.
3. 성공·실패·시간초과·취소·승인대기·차단을 TaskOutcome으로 전달한다.
   응답 문구의 접두사로 성공 여부를 판단하지 않는다. 상태와 결과를 한 트랜잭션으로 기록하며
   오래된 실행/만료 worker의 완료를 거부한다. 취소 요청과 실제 종료 확인을 구분한다.
4. 결과를 전송 전에 저장한다. 전송 성공 여부는 별도로 기록하며 전송 오류의 내용 대신 오류 타입을 남긴다.
   Discord에서 result/결과 뒤에 task ID를 주면 owner 범위의 저장 결과를 조회한다.
   전송 영수증·아티팩트까지 포함하는 durable outbox와 자동 결과 재전송은 아직 없다.
5. recovery/복구 명령과 연결 후 60초 주기의 복구 점검은 과거 작업을 보고한다.
   현재 허용된 목적지와 등록 workspace를 확인한다. claim 만료 전에는 통지가 다음 점검까지 늦어질 수 있다.
   통지 성공 기록은 프로세스 메모리이므로 재시작 중복 통지가 가능하다.
   legacy 요청의 목적지 연결이 없는 행은 자동 전달할 수 없고 로컬 원장 검토가 필요하다.
6. 승인 단어는 권한이 아니다. 직접 쓰기 요청은 검토 대기하며 Codex 조회는 read-only를 강제한다.
   feedback.review 승인은 작업 보류 기록이며 CLI 쓰기 권한이 아니다.
   별도 coordinator는 actor·task·명령/cwd/환경/시간제한·resource hash·만료를 확인하고 승인을 한 번만 소비한다.
   파일별 diff/hash 검토 및 적용은 구현되지 않았다. 자연어 위험 분류와 agy sandbox만으로
   임의 에이전트의 파일별 쓰기 금지를 보장할 수 없다.
7. 기본 HOME 허용을 없애고 등록되지 않은 bridge 사용자는 실행하지 않는다.
   Discord 파일 입출력을 해당 owner workspace로 제한한다. 첨부는 작업 종류/날짜/고유 ID 폴더에
   배타적으로 생성하여 덮어쓰기를 막는다. 일반 모델의 모든 생성물을 이 경로로 중재하는 기능은 후속이다.
8. 메모리 검색의 암묵적 전역 공유와 provider prompt의 자동 경로/프로세스 목록 주입을 제거했다.
   기존 전역 memory 행은 삭제하지 않는다. 프로젝트별 분리 및 개인정보 보존 정책은 미완료다.
9. TypeScript 상태 백업은 SQLite backup API를 사용하여 WAL의 커밋된 내용을 포함하고 무결성을 검사한다.
   symlink/special file, 자기 디렉토리 내부 백업, 기존 대상 덮어쓰기를 거부한다.
   파일 집합 전체의 원자적 스냅샷은 아니며 실패한 백업 폴더가 남을 수 있다.
10. 소스 설치는 package manifest의 공개 파일만 복사한다. runtime data·비밀 파일·외부 symlink를 거부한다.
    shell launcher 경로 인용과 설치 대상 경계 검사를 보강했다.
    과거 shell backup/restore 명령의 별도 경로와 Windows 실행 자격화는 후속이다.

## 남은 구조적 작업과 다음 수용 조건

| 순서 / 작업 ID | 다음 작업 | 완료 판단 |
|---|---|---|
| P0 / EXEC-02 | 직렬화 OperationSpec, 단일 application 경로, 독립 worker | 모든 ingress의 동일 정책; 작업/시도/heartbeat/취소; 실행 전후 crash 시 자동 중복 부작용 없음 |
| P0 / APPLY-01 | 생성과 변경 분리, 파일별 계획·승인·적용 | 기존 파일 hash, 새 파일 배타 생성, symlink 재검증, 승인 actor/scope/revision/expiry/revocation; 계획 변경 시 재승인 |
| P0 / RECOVERY-02 | 보류·취소·재개 선택과 외부 흔적 조정 | 실행 종료 증거 없는 취소를 완료 처리하지 않음; 미해제 claim 해소를 감사 이벤트와 함께 수행 |
| P0 / LEDGER-02 | legacy 쓰기와 순환 store 의존 제거 | upgrade fixture의 task/event/project/memory 참조 보존; 원장 단독 쓰기 및 백업 복원 |
| P1 / DELIVERY-01 | inbox dedup, durable 목적지/outbox/receipt | 수신 중복, 전송 직후 crash, 재연결과 첨부 실패에서 실행과 전달 상태 분리 |
| P1 / ROUTING-01 | 명시적 agy/Codex model profile, planner와 bounded fan-out | 작업 종류·복잡도·중요도·위험·예산을 분리; 선택 이유 기록; 변경 계획은 단일 승인/적용 경로로 모음 |
| P1 / SESSION-01 | Project/Workspace/NyaNya Session/외부 Session 구분 | 등록/선택/조회, 실제 CLI 지속성 확인; 논리 session을 외부 resume로 표현하지 않음 |
| P1 / OPS-02 | 서비스 소유자 통합, 설정 오류, 종료/preflight | 잘못된/손상된 config 보존, 독립 Codex lifecycle, 실제 launch context 권한 오류 분류 |
| P1 / MEMORY-02 | 프로젝트 격리와 데이터 수명 | provider 공개 범위, 로그/결과/첨부/백업 보존·삭제·audit 충돌의 명시적 정책 |
| P2 / DIST-02 | 배포 자격화 | Python/Node 최소 버전, macOS/Linux/Windows 설치·업데이트·제거, disk-full/권한/복원, dependency audit |
| P2 / UI-02 | dashboard 축소 및 원격 read 인증 | 동작하는 제어만 노출; private remote read의 인증/소유권 시험 |
| P2 / HOST-01 | 원격 host 및 자원 최적화 | 로컬 보장 후 인증 worker API; SQLite 파일 공유와 credential 동기화 금지 |

멀티 에이전트 분배는 필요한 제품 기능으로 남긴다. 첫 구현은 제한된 병렬 분석/새 결과물 생성,
단일 변경계획 취합·승인·적용으로 나누는 것이 제안이다. 구체적 예산/모델 우선순위는 아직 결정하지 않았다.
새 커넥터·Orca·공개 대시보드·멀티테넌시·무제한 autonomous write는 현재 개발 대상이 아니다.

## 검증과 한계

이번 회귀시험은 tests/conftest.py에서 NYANYA 설정을 임시 상태로 격리하여 실제 .env와 DB를 로드하지 않는다.
별도 프로세스의 동시 claim, 600행 이력, 만료 lease, 오래된 완료, 재시작 보류, typed outcome,
불확실 전송의 결과 보존, 승인 task/actor/scope/expiry/재사용, 경로 traversal/symlink, memory owner,
WAL 백업·손상 DB·덮어쓰기, 공개 파일 설치와 비밀/외부 링크 거부를 검사한다.
실제 subprocess/tmux 시험과 임시 디렉토리의 bash clean install (--skip-deps)을 포함한다.
설치 시험은 패키지 다운로드·인증·서비스 등록·실제 모델 실행을 포함하지 않는다.

최종 검증 기록:

- Python 전체 회귀시험: 111 passed (5.29초).
- Ruff: All checks passed. TypeScript build 및 typecheck 통과.
- dashboard JS, 전체 dist/bin JS, shell syntax, Python AST 검사 통과.
- release verification: npm pack dry-run, 공개 worktree의 추적·미추적 파일 privacy scan, 버전 일치 검사 통과.
- 변경 Markdown의 상대 링크 검사 및 git diff --check 통과.
- 중간 회귀시험에서 같은 초의 작업 순서가 임의 ID에 좌우되는 결함을 발견하여 삽입 순서 tie-break와 재현 시험을 추가했다.
- dependency audit, 실제 Discord/모델, Windows와 최소 버전 매트릭스는 미실행.

 통과한 단위/통합시험은 Discord 실운영 증거가 아니다.
실제 Discord 요청→모델→작업별 새 폴더→변경안 피드백→중단→재연결 통지는 별도 운영자 수용시험이다.
OS 팝업/권한 준비 작업 OPS-PERM-01도 별도이며 보안 설정을 변경하지 않았다.

## 업그레이드·복원과 다음 역할 인계

실행 시 스키마가 자동으로 v3로 올라가므로 배포 전 서비스를 정지하고 올바른 상태 DB를 지정한
검증된 백업을 확보한다. 이번에는 실제 DB migration을 실행하지 않았다.
구버전 코드로 v3 DB에 쓰게 하는 rollback은 지원하지 않는다. 새 상태를 보존한 뒤 사전 백업과
대응 코드를 함께 복원하고 무결성·참조를 확인한다. 기존 queued/running 기록은 임의 삭제·재실행하지 않는다.

다음 역할은 같은 CORE-STAB-01 인계와 최신 worktree에서 시작하여 EXEC-02/APPLY-01의 계약을 구체화한다.
먼저 owner queue를 막는 미해제 claim의 사용자 조정 절차와 파일별 승인 실행의 threat/acceptance model을 확정한다.
운영자의 현재 추가 조작은 필요 없다. 실서비스 배포와 실제 모델 수용시험은 별도 실행 범위로 남긴다.

## 검토 대상 파일 목록

다음 목록은 공개 소스·운영/배포 스크립트·설정 예제·시험의 검토 범위다. dist의 JavaScript는 TypeScript 빌드로 재생성·검증한다. 비공개 runtime 파일은 포함하지 않는다.

### src (30)

- src/nyanya_agent/__init__.py
- src/nyanya_agent/adapter_runner.py
- src/nyanya_agent/approval_contract.py
- src/nyanya_agent/bridge_common.py
- src/nyanya_agent/bridge_constants.py
- src/nyanya_agent/bridge_policy.py
- src/nyanya_agent/bridge_runtime.py
- src/nyanya_agent/bridge_store.py
- src/nyanya_agent/codex_cli.py
- src/nyanya_agent/core.py
- src/nyanya_agent/dashboard_api.py
- src/nyanya_agent/dashboard_static/app.js
- src/nyanya_agent/dashboard_static/index.html
- src/nyanya_agent/dashboard_static/styles.css
- src/nyanya_agent/dashboard_store.py
- src/nyanya_agent/discord_bridge.py
- src/nyanya_agent/distribution_copy.py
- src/nyanya_agent/execution_adapters.py
- src/nyanya_agent/execution_runtime.py
- src/nyanya_agent/execution_store.py
- src/nyanya_agent/manager.py
- src/nyanya_agent/memory_worker.py
- src/nyanya_agent/policy_documents.py
- src/nyanya_agent/runtime_paths.py
- src/nyanya_agent/state_backup.py
- src/nyanya_agent/task_outcomes.py
- src/nyanya_agent/task_service.py
- src/nyanya_agent/telegram_bridge.py
- src/nyanya_agent/work_queue.py
- src/nyanya_agent/workspace_paths.py

### cli (18)

- cli/src/bin/nyanya-agent.ts
- cli/src/bin/nyanya-dashboard.ts
- cli/src/bin/nyanya-discord.ts
- cli/src/bin/nyanya-memory-worker.ts
- cli/src/bin/nyanya-telegram.ts
- cli/src/bin/nyanya.ts
- cli/src/bin/nyanyactl.ts
- cli/src/bin/python-module.ts
- cli/src/commands/config.ts
- cli/src/commands/doctor.ts
- cli/src/commands/service.ts
- cli/src/commands/setup.ts
- cli/src/commands/state.ts
- cli/src/runtime/env-file.ts
- cli/src/runtime/process.ts
- cli/src/runtime/project.ts
- cli/src/runtime/prompt.ts
- cli/src/runtime/python.ts

### bin (7)

- bin/nyanya-agent.js
- bin/nyanya-dashboard.js
- bin/nyanya-discord.js
- bin/nyanya-memory-worker.js
- bin/nyanya-telegram.js
- bin/nyanya.js
- bin/nyanyactl.js

### scripts (14)

- scripts/backup_state.sh
- scripts/check_backend.sh
- scripts/install_discord_launch_agent.sh
- scripts/mark_dist_executable.js
- scripts/nyanya_ctl.sh
- scripts/restore_state.sh
- scripts/run_dashboard.sh
- scripts/run_discord_bridge.sh
- scripts/run_memory_worker.sh
- scripts/run_nyanya.sh
- scripts/run_telegram_bridge.sh
- scripts/runtime_env.sh
- scripts/status_launch_agents.sh
- scripts/uninstall_discord_launch_agent.sh

### packaging (13)

- packaging/README.md
- packaging/homebrew/Formula/nyanya-agent.rb.template
- packaging/install/install.ps1
- packaging/install/install.sh
- packaging/install/uninstall.ps1
- packaging/install/uninstall.sh
- packaging/launchd/com.hcs.nyanya.agent.plist.template
- packaging/launchd/com.hcs.nyanya.dashboard.plist.template
- packaging/launchd/com.hcs.nyanya.memory-worker.plist.template
- packaging/release/generate_checksums.sh
- packaging/release/package-allowlist.txt
- packaging/release/package-denylist.txt
- packaging/release/verify_release.sh

### config (2)

- config/nyanya.json
- config/user_workspaces.example.json

### prompts (5)

- prompts/agent_memory.md
- prompts/policy.md
- prompts/policy_governance.md
- prompts/policy_technical.md
- prompts/system.md

### tests (22)

- tests/conftest.py
- tests/test_agent_memory.py
- tests/test_bridge_dashboard_recording.py
- tests/test_bridge_policy.py
- tests/test_cli_distribution.py
- tests/test_cli_safety_profiles.py
- tests/test_codex_cli_resolution.py
- tests/test_dashboard_execution_api.py
- tests/test_dashboard_store.py
- tests/test_distribution_safety.py
- tests/test_execution_adapters.py
- tests/test_execution_runtime.py
- tests/test_execution_store.py
- tests/test_manager_launchd.py
- tests/test_memory_store.py
- tests/test_memory_worker.py
- tests/test_policy_documents.py
- tests/test_runtime_paths.py
- tests/test_safety_boundaries.py
- tests/test_task_service.py
- tests/test_terminal_durable_path.py
- tests/test_work_queue.py

### .github (1)

- .github/workflows/ci.yml

## 현재 worktree 인계 목록

아래 목록에는 세션 시작 전부터 있던 수정도 포함한다. 이번 변경만의 diff로 해석하지 않는다. 미추적 파일도 다음 역할에 반드시 전달한다. 원격 push/commit은 하지 않았다.

- README.KO.md (M)
- README.md (M)
- cli/src/commands/state.ts (M)
- cli/src/runtime/process.ts (M)
- dist/commands/state.js (M)
- dist/runtime/process.js (M)
- docs/README.md (M)
- docs/architecture_and_roadmap.md (M)
- docs/execution_control_plane.md (M)
- docs/installation_and_distribution.md (M)
- docs/operations_guide.md (M)
- package.json (M)
- packaging/install/install.ps1 (M)
- packaging/install/install.sh (M)
- packaging/release/verify_release.sh (M)
- prompts/agent_memory.md (M)
- prompts/system.md (M)
- src/nyanya_agent/bridge_policy.py (M)
- src/nyanya_agent/bridge_runtime.py (M)
- src/nyanya_agent/bridge_store.py (M)
- src/nyanya_agent/core.py (M)
- src/nyanya_agent/dashboard_api.py (M)
- src/nyanya_agent/dashboard_store.py (M)
- src/nyanya_agent/discord_bridge.py (M)
- src/nyanya_agent/execution_adapters.py (M)
- src/nyanya_agent/execution_runtime.py (M)
- src/nyanya_agent/execution_store.py (M)
- src/nyanya_agent/manager.py (M)
- src/nyanya_agent/memory_worker.py (M)
- tests/test_agent_memory.py (M)
- tests/test_bridge_dashboard_recording.py (M)
- tests/test_bridge_policy.py (M)
- tests/test_cli_distribution.py (M)
- tests/test_cli_safety_profiles.py (M)
- tests/test_dashboard_execution_api.py (M)
- tests/test_execution_adapters.py (M)
- tests/test_execution_runtime.py (M)
- tests/test_execution_store.py (M)
- AGENTS.md (??)
- docs/architecture_diagnostic_20260826.md (??)
- docs/core_stabilization_20260910.md (??)
- docs/local_control_plane_implementation.md (??)
- docs/npm_release_resumption_guide.md (??)
- prompts/policy.md (??)
- prompts/policy_governance.md (??)
- prompts/policy_technical.md (??)
- src/nyanya_agent/approval_contract.py (??)
- src/nyanya_agent/codex_cli.py (??)
- src/nyanya_agent/distribution_copy.py (??)
- src/nyanya_agent/policy_documents.py (??)
- src/nyanya_agent/state_backup.py (??)
- src/nyanya_agent/task_outcomes.py (??)
- src/nyanya_agent/task_service.py (??)
- src/nyanya_agent/work_queue.py (??)
- src/nyanya_agent/workspace_paths.py (??)
- tests/conftest.py (??)
- tests/test_codex_cli_resolution.py (??)
- tests/test_distribution_safety.py (??)
- tests/test_policy_documents.py (??)
- tests/test_safety_boundaries.py (??)
- tests/test_task_service.py (??)
- tests/test_terminal_durable_path.py (??)
- tests/test_work_queue.py (??)
