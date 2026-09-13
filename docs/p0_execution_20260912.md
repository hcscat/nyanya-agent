# CORE-STAB-01 / P0 실행·파일 승인·복구·원장 구현

2026-09-12. 작업 ID: EXEC-02 / APPLY-01 / RECOVERY-02 / LEDGER-02.
역할: 설계 검토·구현·테스트를 이번 작업에서 함께 수행했다. 개발 세션 모델을
전환하지 않았다. 운영 배포, 서비스 재시작, 운영 DB migration, 공개 배포는 포함하지 않는다.

## 목표와 판단

단일 사용자의 Discord/terminal 요청을 보존하고, 여러 요청을 병렬 처리하되
기존 파일은 구체적인 변경안에 대한 사람의 승인 이후에만 바꾼다.
중단된 요청은 자동 재실행하지 않고, 다른 요청 완료 시 상기시키며 근거를 조회한다.
전체 제품을 폐기하지 않고 실행 경로를 새로 구현했다. 배포 CLI, connector,
설정·백업·호환 reader는 보존했다.

사용자의 병렬 처리 방향은 타당하다. 직렬화와 직렬 실행은 다른 개념이다.
OperationSpec의 직렬화는 실행할 일을 함수/callback 대신 다음과 같은 데이터로
저장한다는 뜻이다. 여러 명세를 여러 worker thread가 동시에 처리할 수 있다.

```json
{
  "version": 1,
  "kind": "request",
  "prompt": "요청 내용을 분석해 주세요",
  "workspace": "/absolute/workspace/path",
  "profile": "auto",
  "timeout_seconds": 600,
  "plan_id": ""
}
```

명세에는 임의 shell, Python 객체, credential, 직렬화된 callback을 넣지 않는다.
지원 종류는 request와 apply이며, apply는 저장된 변경안 ID를 참조한다.
미지원 version/field/profile은 실행하지 않는다. JSON 복원 가능성과 외부 모델
대화 세션 재개는 별개다. 중단 후 resume는 사용자가 승인한 **새 시도**다.

## 구현 경로

```text
terminal / Discord / authenticated operations API
  → OperationService → SQLite task + OperationSpec
  → dedicated operation_worker process
  → atomic claim + bounded thread pool
  → Flash assessment → selected executor → summary / file plan
  → new-file exclusive creation OR owner approval → reviewed apply
  → atomic execution/task/result/event commit → connector delivery
```

| 작업 | 구현 | 중요 제한 |
|---|---|---|
| EXEC-02 | 데이터 명세, 별도 process, worker ID/heartbeat, atomic claim, 병렬 작업, lease 검증, bounded retry, typed outcome | 임의 shell/브라우저 작업 및 하나의 요청을 자동 분해하는 DAG scheduler는 미포함 |
| APPLY-01 | 불변 파일안, 이전 내용/hash, diff, actor/plan/hash/expiry 승인, 실행 시 경로 재검사, journal, workspace lock | UTF-8 일반 파일만; 디렉터리 삭제·이동·binary 편집은 미지원 |
| RECOVERY-02 | 중단 보류, 원래 요청·단계·근거·시도 수, 완료 응답에 미완료 목록, 명시적 resume와 reconcile/resolve | full delivery outbox는 별도 작업; 자동 원인 추측이나 자동 재실행 없음 |
| LEDGER-02 | 공유 DB 모듈로 순환 의존 제거, schema v4, 실행 상태 단일 원장, legacy 일회 import와 read view | legacy 요청 envelope/메모리/project 테이블은 호환 보존; 전체 도메인 migration 완료를 뜻하지 않음 |

일반 모델 요청은 기존 프로세스 내부 runner를 사용하지 않는다. Discord 파일 업로드
전달 기능은 기존 callback 경로를 보존했다. 이것을 durable delivery라고 부르지 않는다.
기존 dashboard `/v1/tasks`는 실행 명세 없는 draft 기록이며 자동 실행하지 않는다.
실제 실행 접수는 인증된 `POST /v1/operations`를 사용한다. dashboard UI는 monitoring 우선이다.

## 모델 정책

2026-09-12 로컬 CLI 지원 목록 및 아래 공식 문서를 확인했다.

| 별칭 | 런타임 | 모델 ID | effort | 선택 기준 |
|---|---|---|---|---|
| flash | agy | gemini-3.8-flash-medium | medium | 모든 요청의 최초 판단; 낮은 복잡도의 실행 |
| luna | Codex | gpt-5.6-luna | xhigh | 복잡도 3–4이며 상위 중요도/영향도 조건에 해당하지 않을 때 |
| astra | Codex | gpt-6-astra | low | 중요도 또는 영향도 ≥4, 또는 복잡도 5 |

점수는 각각 1–5이고 reason을 함께 저장한다. 형식이 틀리거나 모델 접근·인증이
실패하면 보류한다. 다른 모델로 조용히 대체하지 않는다. 명시적 flash/luna/astra
profile도 최초 Flash 판단을 생략하지 않으며 실제 선택을 별도 event로 기록한다.

사용자의 Astra Light는 공식 effort인 low로 해석했다. Flash medium은 설치된 agy의
실제 variant ID다. 최신 모델이라는 표현을 영구 alias로 사용하지 않는다.
업데이트 시 지원 ID/권한과 실제 응답을 재검증한다. 모델 강도는 쓰기 권한을 바꾸지 않는다.
기존 provider/model 설정과 CLI override는 backend `--check`에 보존하며,
일반 실행에 해당 override를 전달하면 명시적으로 거절한다.

공식 근거: [Gemini 3.8 Flash](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash),
[GPT 5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna),
[GPT 6 Astra](https://developers.openai.com/api/docs/models/gpt-6-astra).

## 실행과 병렬성

기본 동시 실행은 2개, NYANYA_WORKER_CONCURRENCY로 1–4개까지 설정한다.
동일 DB의 operation claim 수를 transaction 안에서 검사하여 중복·과다 claim을 막는다.
일반 분석은 같은 workspace에서도 병렬 실행한다. 별도 apply 작업은 같은 workspace의
다른 operation과 겹치지 않으며 실제 파일 쓰기는 추가 POSIX lock으로 직렬화한다.
서로 다른 controller는 동시 실행 한도를 동일하게 설정해야 한다.

각 작업은 claim 후 Flash가 판단하므로 점수 기반 모델 선택은 구현되어 있지만
아직 평가하지 않은 요청 전체를 미리 평가해 최적 순서로 재배열하거나 실행 중인
작업을 선점하지 않는다. worker는 우선순위/접수 순서를 사용하고 판단 점수를 기록한다.
작업 분해 DAG, 자동 재할당, 자원 예측·비용 최적화는 후속 작업이다.

Worker heartbeat/claim은 30초 유효하며 claim 갱신은 실행 중에 이루어진다.
lease 만료나 worker 종료를 발견하면 보류하고 이전 시도의 완료 보고를 거절한다.
새 worker가 과거 작업을 자동 인계하지 않는다. 정상적인 독립 새 요청은 계속 처리한다.
worker 시작 실패도 가능한 경우 작업/명세와 원인을 보존한다. workspace가 등록되지 않은
요청은 실행 가능한 작업으로 접수하지 않는다.

취소·timeout은 소유한 subprocess group 종료와 parent 회수를 시도한다. 종료 권한 오류나
확인 실패를 취소 성공으로 표시하지 않는다. detached descendant 전체의 종료 보장은
별도 운영 검증이 필요하다. 출력은 stream당 4 MB, CLI 입력은 100 KB 이내다.

## 파일 계약

- 사용자 등록 workspace를 접수와 실행 시 다시 확인한다. 암묵적인 HOME 접근은 없다.
- 모델 입력은 최대 80개/총 50 KB의 UTF-8 snapshot, 탐색 최대 200개 디렉터리다.
  알려진 private/runtime/credential 경로와 symlink를 제외하고 임시 폴더에 복사한다.
  이 목록은 모든 비밀을 알아내는 DLP가 아니다. provider에 줄 자료는 workspace에서 관리한다.
- 모델은 분석 또는 파일안 JSON만 반환한다. agy plan/sandbox, Codex read-only로 호출한다.
  임시 snapshot과 CLI 옵션은 OS 전체에 대한 완전한 보안 격리를 주장하는 근거가 아니다.
- 신규 파일은 `nyanya-tasks/task_kind/YYYYMMDD-HHMMSS-plan_id/` 아래에 배치한다.
  작업 종류는 analysis/code/document/data/work 중에서 판단하며, 누락 시 work를 사용한다. UTC 시각과 고유 ID를 사용한다. 기존 파일과 충돌하면 쓰지 않는다.
- 기존 파일 수정/삭제는 snapshot의 내용 hash가 현재와 같아야 변경안을 만들 수 있다.
  파일 경로, 작업 종류, 이유, 이전/이후 내용과 plan hash를 저장한다.
- diff가 길면 일부 표시임을 알리고 plan-file로 전체 내용을 조회한다.
  승인은 동일 owner의 정확한 plan ID/hash, 1시간 유효기간에 묶인다.
  승인 단어·feedback.review 행·강한 모델 선택은 쓰기를 허용하지 않는다.
- 적용 시 등록 경로, 승인 상태, 만료, 불변 내용 hash, 이전 파일 hash를 재검사한다.
  단일 링크 일반 파일만 허용하고 dir-fd/O_NOFOLLOW로 symlink 순회를 거부한다.
  원래 작업을 취소한 뒤에는 승인된 변경안도 적용하지 않는다.
- 쓰기 전 journal에 이전 bytes/hash를 저장한다. 신규 생성은 O_EXCL, 수정은 fsync한
  임시 파일의 replace, 삭제는 승인된 파일만 unlink한다. 여러 파일은 단일 filesystem
  transaction이 아니므로 일부 적용 상태를 숨기지 않는다.
- 적용 중단 시 applying/uncertain 상태가 남고 같은 workspace의 다음 apply를 막는다.
  reconcile로 실제 상태를 관측한 뒤 resolve에 관측 hash를 제공하여 확인 처리한다.
  resolve는 파일을 다시 쓰거나 rollback하지 않는다. 일부만 적용되었다면 현재 파일을
  기준으로 새 요청/변경안을 받아야 한다. 파일 효과가 있는 기존 요청의 resume도 거절한다.

다른 편집기가 검사와 replace 사이에 파일을 바꾸는 경쟁까지 완전히 차단하지는 않는다.
적용 중 같은 파일을 다른 도구로 수정하지 않는 운영 조건이 필요하다.
Windows에서는 no-follow 파일 적용을 지원하지 않아 보류한다. 파일 내용 rollback은
journal/pre-upgrade backup과 사람의 별도 검토를 거친다.

## 사용자 명령

Discord에서는 기존 prefix 뒤에 아래 명령을 넣는다. Terminal에서는 prompt로 전달하거나
REPL에 입력한다. dashboard control API는 operator 소유권으로 실행한다.
Discord actor는 실제 발신자에서 결정하며 임의 문자열로 바꾸지 않는다.

| 명령 | 동작 |
|---|---|
| recovery / 복구 | 내 미완료 작업 요약 |
| why 작업ID | 원래 요청, 상태, 기록된 단계/근거, 시도 수 |
| plan 변경안ID | 구체적인 변경 방향과 파일별 diff |
| plan-file 변경안ID 상대경로 | 해당 파일안 전체 내용 |
| approve 변경안ID plan_hash | 검토한 변경안 승인 및 apply 접수 |
| revoke 변경안ID | 아직 소비되지 않은 변경안 거절/철회 |
| resume 작업ID | 안전한 request의 명시적 새 시도; 최대 총 3회 |
| cancel 작업ID | 개별 취소 요청; 실행 중이면 종료 확인 대기 |
| reconcile 변경안ID | 현재 파일을 before/after/diverged로 관측하고 hash 반환 |
| resolve 변경안ID 관측hash | 동일한 관측 상태를 확인 처리; 파일 재실행 없음 |
| result 작업ID (Discord) | 전달 실패를 포함한 저장 결과 확인 |

성공한 작업 응답에는 다른 미완료 작업 개수와 최대 5개 ID/요약을 덧붙인다.
새 분석의 현재 작업이나 방금 적용 완료한 원래 요청은 상기 목록에서 제외한다.
실패도 미완료 목록에 포함한다. 원인 근거가 부족하면 확정할 수 없다고 표시한다.
기존 reconnect 알림과 병행하며 receipt/outbox의 정확히 한 번 전달은 보장하지 않는다.

API: `POST /v1/operations`에 prompt/workspace/profile을 보내고,
`POST /v1/operations/control`에 command를 보낸다. API는 비동기 접수하며
실제 전달 없이 delivered로 기록하지 않는다. 원격 또는 forwarded API 읽기도 token이
필요하다. dashboard는 token을 GET/POST header에 전송하고 5초 주기로 갱신한다.
제어 활성 버튼은 인증 확인만 하며 복구 상태를 변경하지 않는다. health와 정적 화면을 공개 실행 제어 권한으로 해석하지 않는다.

## 원장과 migration / rollback

schema v4는 worker/spec/plan/journal과 request_read_model을 추가한다.
database는 provider나 dashboard를 import하지 않는다. dashboard_store와
execution_store 사이의 순환 초기화를 제거했다. 이미 import한 legacy 행은 재동기화하지 않는다.
새 operation의 상태/result/event/claim 해제/재실행 가능 여부는 한 transaction으로 commit한다.
승인된 apply 완료와 원래 요청 완료 event도 같은 transaction에 묶는다.
실행 이력과 이전 결과는 보존하고 오래된 시도로 최신 task 상태를 덮어쓰지 않는다.

agent_requests는 connector envelope와 호환 데이터로 남는다. 현재 상태/결과는 원장
read view로 조회한다. legacy 메모리 추출·project 화면의 전체 전환, schema 이전 시대의
모든 데이터 형태 지원과 호환 테이블 제거는 별도 migration/검토 후 수행한다.
호환 reader는 최소 다음 배포의 upgrade/restore 검증 완료까지 유지한다.

배포 전에 현재 DB를 SQLite backup으로 백업하고 integrity/FK 검사를 수행한다.
운영 적용 시 모든 관련 구버전 process를 중단한 후 v4로 올려야 한다.
v4 DB를 구버전 코드로 계속 쓰는 방식으로 rollback하지 않는다. 중단 상태에서
배포 전 backup을 별도 경로에 복원하고 코드/상태를 함께 되돌린다.
이번 작업에서는 임시 fixture만 migration/backup/restore했고 운영 DB에는 적용하지 않았다.

## 검증과 후속 작업

아래 결과는 이 문서 작성 작업의 검증이다. 기존 111개는 2026-09-10 기준이며
현재 테스트 수와 범위를 동일시하지 않는다. 상세 케이스는 테스트 안내서와
[test_p0_operations.py](../tests/test_p0_operations.py)를 함께 본다.

- 전체 Python 테스트: 150개 통과. 이 중 P0 추가 파일은 32개 함수/39개 케이스다.
- 단위/통합: 명세 검증, 모델 점수·선택, 병렬 claim, stale 완료 거부, owner/path 확인,
  승인 hash/만료/철회, symlink, 전후 hash 변경, 삭제, 부분 적용, 관측 hash 확인,
  retry 제한, 이전 결과 재전달 방지, API auth/실행 접수, 작업 시작 실패 보존.
- 실제 OS/SQLite: 서로 다른 process의 claim 경쟁, 별도 worker + 가짜 CLI,
  실제 worker 강제 종료, 두 thread 동시 모델 작업, 파일 journal/backup,
  v3→v4 upgrade 및 v3 backup restore, 취소/출력 제한. 실제 파일 replace+fsync 직후
  process를 강제 종료하여 journal이 prepared인 상태도 관측·확인 처리했다.
- 실제 모델: 세 profile 모두 임시 폴더의 최소 JSON 응답 성공. 실제 모델이 임시 note.txt
  변경안을 생성 → awaiting_approval → 원본 유지 → 명시적 승인 → apply 성공 확인.
  실제 Discord 네트워크 경유나 운영 계정 작업 완료 검증은 아니다.

남은 우선 작업: DELIVERY-01 inbox/outbox/receipt·재전달, session/project context와
external session continuation, legacy 메모리 source와 read model 전환, 사용자 의도에
맞춘 snapshot 선택, 요청 하나의 multi-agent DAG 분해, 자원 기반 scheduling.
Telegram 확장·Orca·원격 host·public dashboard·npm 발행은 진행하지 않았다.

다음 운영 검증: 백업 후 승인된 배포에서 Discord 실제 접수/동시 요청/파일 승인/중단
알림/why/reconcile 흐름을 확인한다. 운영 서비스 변경과 배포는 별도 권한 범위다.
기능 테스트 통과를 운영 배포 완료나 모든 OS/플랫폼 호환 증거로 보고하지 않는다.

## 최종 handoff

- Branch: main. 기준 commit: 2182510. 기존 미커밋 변경을 보존했고 이번 변경도 미커밋이다.
- 신규 주요 소스: database, operation_schema/spec/service/store/worker, model_routing,
  process_runner, reviewed_changes. 공통 work_queue 결과 transaction과 ingress를 갱신했다.
- 변경 ingress/호환 영역: core, bridge_store/policy, discord_bridge, telegram_bridge,
  dashboard_api/store/static app.js, execution_store, task_outcomes; 관련 tests, prompts, README, AGENTS.
- 문서: 이 문서 및 docs/README.md, test_catalog_ko.md, 기존 계약 문서에 후속 링크를 추가했다.
- 검증 명령/결과: PYTHONPATH=src .venv/bin/python -m pytest -q — 150 passed.
  .venv/bin/ruff check src/nyanya_agent tests, npm run typecheck --if-present,
  npm run build, node --check src/nyanya_agent/dashboard_static/app.js 통과.
  packaging/release/verify_release.sh의 Python/shell 구문, npm pack/public manifest,
  개인정보·비밀정보, version 일치 gate 통과. git diff --check 및 Markdown 링크 검사 통과.
  Node 실행으로 dashboard GET/POST 인증 header 병합과 token URL 미사용을 확인했다.
- 환경: repository Python virtualenv, POSIX/macOS, Node/TypeScript, 테스트 의존성.
  pytest는 임시 NYANYA_HOME/env/DB를 사용하고 실제 모델 호출을 금지한다.
  실모델 smoke와 synthetic file acceptance는 별도의 임시 경로에서 수행했다.
- 미실행: 운영 DB migration, 서비스 재시작, 실제 Discord 수신·전달, 운영 사용자 파일 변경,
  권한 변경, remote host drill, Windows acceptance, commit/push/publish.
