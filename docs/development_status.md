# 개발 현황과 남은 작업

## PR 2 review correction

The task-list classifier now accepts complete negative rerun/resume qualifiers while holding mixed-effect requests for clarification. `tests/test_workflow_dispatch.py` covers classification, unchanged tasks/approvals, owner/conversation selection fences and synthetic Discord intake without model submission. This is a source correction; live connector acceptance and operating deployment remain separate. The dated review below is historical evidence, not the current PR validation result.

Ordinary Codex review identified four additional corrections: destination-scoped automatic reminders/receipts, preserved Discord task-list aliases and admin checks, bounded agent-limit detection that leaves technical timeout questions as work, and safe blocked outcomes for unavailable upload workspaces. Focused regressions cover periodic and completion notices, parent/child origin inheritance, cross-channel/connector/owner separation, alias permissions, model intake and upload confirmation without effects. These are source contracts and synthetic test evidence, not an installed-service security certification.

A follow-up review also identified that generic “all/remove” wording could cancel an unrelated saved task selection. Cancellation now requires a complete task/previous-list target; file targets, mixed clauses and interrogative shortcuts cannot mutate the selection. Regression tests retain a valid queued selection before the non-task request and verify unchanged tasks/approvals through the service and authenticated API.

## Public review guidance

The reviewed root `AGENTS.md` now supplies contributor instructions and three scoped code-review rules; `SECURITY.md` supplies the threat model, security invariants, finding criteria and reporting policy. The Git release check permits only the explicitly approved root guide; nested/override instructions remain blocked, and npm/source-install checks still exclude all AGENTS files. `SECURITY.md` is included as public distribution policy. These files do not enable automatic reviews, private vulnerability reporting or a security scanner, and do not establish operational deployment or a completed security scan.

## Dashboard installation follow-up

Normal CLI setup and the Bash/PowerShell installers now provision a private dashboard token before service admission, preserving configured credentials on reruns. Authentication and Host/Origin checks remain unchanged. [Token provisioning](installation_and_distribution.md#dashboard-token-provisioning) describes behavior and recovery. Regression coverage is in `tests/test_dashboard_token_setup.py` and the source-installer integration test; Windows CI additionally exercises the native ACL and PowerShell installer. A source fix and automated checks do not establish operational installation or live Discord acceptance.

검토일: 2026-09-21. 작업 ID: REVIEW-20260921.
기준: `main` / `bb8774b7b929bf565f353adf800d1797f1ce44e9`.
목적은 4차까지 공개한 소스의 구현 범위와 현재 검증을 대조하는 것이다.
기준 검토는 가이드 정리와 공개 문서의 패키지 목록 보완이다.
2026-09-22의 개발/운영 환경 분리 후속 결과는 아래 별도 절에 기록한다.

## 완료 수준의 해석

**4개 차수의 소스 통합·공개는 완료되었다. 첫 안정 버전의 운영 수용은 아직 완료로
판정할 수 없다.** 차수는 커밋을 검토하기 위해 나눈 단위이며 기능 완성률의 분모가 아니다.
제품 전체의 백분율은 산정하지 않는다. 구현, 자동 검증, 실제 운영 수용을 구분한다.

| 차수 | 범위 / 마지막 커밋 | 확인된 개발 결과 | 남은 경계 |
|---|---|---|---|
| 1차 | 개인정보 경계·분석·설계 / `6fc1df3` | 공개/비공개 정책, 실행 계약과 아키텍처 문서 | 오래된 현재형 설명은 이번 검토로 갱신; 정책이 모든 실행 경로의 구현 완료를 뜻하지 않음 |
| 2차 | 저장소·실행·승인·복구 / `7aaeb80` | schema v4, OperationSpec, 별도 worker, 병렬 claim, 파일안 승인·journal, 중단 보류 | 전달 보장, 외부 세션 지속, 단일 요청의 다중 에이전트 분해, 아래 결함 보완 |
| 3차 | 터미널·연결 경로·대시보드 / `4542986` | 일반 terminal/Discord/API 공통 operation 경로, workspace 확인, 인증 제어 | 메모리·세션 연결, 모든 진입 경로의 통계, 중간 진행 전송과 Telegram 명령 동등성 |
| 4차 | 설치·배포·검사·문서 / `3ea23b7` | Node CLI/Python 런타임 분리, 상태 보존·백업, 공개 파일 manifest와 CI | 실제 설치/복구 수용, 미검증 플랫폼, 별도 npm/Release/Wiki 게시 |

4차까지 `52a1bb5..3ea23b7`은 **89개 파일, +10,394 / -991줄**, 총 5커밋이다.
2차에 린트 설정 보정 커밋이 별도로 들어갔다. 이후 main에 통합되었고
`74830f3`, `bb8774b`에서 설치 의존성의 Git/privacy 경계를 보완했다.
현재 기준 `52a1bb5..bb8774b`는 **89개 파일, +10,531 / -991줄**이다.
차수별 파일 수는 중복 파일을 포함하므로 단순 합산하지 않는다.

2026-09-21 조회에서 당시 GitHub main과 로컬 HEAD가 일치했고 CI는 성공이었다.
문서의 커밋 ID는 2026-09-22 개인정보 이력 정리 후의 대응 ID로 갱신했다.
당시 Actions 기록은 개인정보 정리 과정에서 비공개 백업 후 제거했으므로,
이전 실행 링크를 현재 검증 증거로 사용하지 않는다. 최신 검증은 해당 변경의
로컬 검사와 새 커밋의 CI 결과를 별도로 확인한다.
Wiki 기능은 활성화되어 있으나 페이지 내용은 이번 검토에서 확인하지 않았다.
GitHub Release 목록은 비어 있었다. npm 게시 버전은 이번에 조회하지 않았다.

## 개발/운영 환경 분리 — SPLIT-20260922

기존 작업 폴더는 운영 설치·사용에 유지하고, 하위 `source`를 독립된 개발 Git
루트로 분리했다. 기존 Git 이력·브랜치·미커밋 변경과 과거 검증 worktree를 보존했으며,
개발 Python 가상환경과 Node 의존성을 별도로 설치했다. 운영 코드와 서비스 경로는 유지한다.

`scripts/dev.py`는 개발 상태를 `.dev-state`에 두고 운영 NyaNya 설정과 지정된
인증 환경변수의 상속을 제거한다. 서비스 설치/관리 명령은 제공하지 않는다.
개발 상태는 Git, 패키지, 배포 파일 복사에서 제외한다. 이 도구는 OS sandbox가 아니며
외부 CLI의 사용자 홈 인증 파일 접근까지 격리하지 않는다.

- 자동 검사: 기존 318개와 신규 개발 격리 9개, 총 **327개 통과**.
- Ruff, TypeScript typecheck/build, JavaScript 구문 검사와 전체 release gate 통과.
  패키지 164개 파일에 AGENTS·개발 상태·운영 데이터·설치 의존성은 포함되지 않았다.
  문서 13개의 로컬 링크 317개도 대상 파일 존재를 확인했다.
- 실제 개발 대시보드: 별도 loopback 포트에서 HTTP 200과 독립 SQLite 무결성을 확인한 뒤 종료했다.
- 운영 대시보드: 같은 검사 중 HTTP 200을 유지했다. 운영 서비스 재시작이나 모델 요청은 하지 않았다.
- Git/패키지의 현재 파일 검사와 과거 이력 검사는 별도다. 현재 파일이 통과해도
  과거 커밋의 개인정보 제거를 보장하지 않으며, 이력 변경은 별도 검토·승인이 필요하다.

분리는 제품 기능 배포나 Discord/복구 수용 완료를 뜻하지 않는다. 아래 REV-01–03과
전달·문맥 기능의 미완료 상태는 유지된다. 운영 업데이트는 검증한 산출물의 별도 설치 절차로 진행한다.
구체적인 개발 명령과 배포 경계는 [설치·배포 안내](installation_and_distribution.md#development-install)를 따른다.

## 요구사항별 판정

| 요구사항 | 판정 | 근거와 한계 |
|---|---|---|
| Discord 연결·사용자 workspace 경계 | 구현·자동 검증 | `test_workspace_intake.py`; 실제 사용자 요청의 모델 완료는 새 수용 증거 필요 |
| Flash 최초 판단과 모델 선택 | 구현·자동 검증 | 점수·선택 기록; 현재 설치 모델 접근 권한이나 최신 모델 여부는 재검증하지 않음 |
| 여러 요청 병렬 처리 | 구현·자동 검증 | 기본 2개, 설정 1–4개; 같은 workspace의 apply는 조정 |
| 한 요청을 여러 agy/Codex 에이전트에 분배 | 미구현 | 작업 분해, 의존성 DAG, 결과 병합은 별도 설계 필요 |
| 신규 파일 생성·기존 파일 승인 | 구현·자동 검증 | POSIX UTF-8 일반 파일 한정; 정확한 plan hash/owner/만료/원본 확인 |
| 중단 보류·상기·why/resume/reconcile | 구현·자동 검증, 보완 필요 | 자동 재실행 없음; 아래 재시도 대기 결함과 실제 운영 복구 검증 필요 |
| 실행 상태 단일 원장 | 일반 operation 구현 | legacy envelope·memory·project 전체 이관은 미완료 |
| 결과 보존과 재전달 | 부분 구현 | 저장 결과 조회 가능; inbox/outbox/receipt 기반 재전달은 미구현 |
| 메모리와 대화 연속성 | 부분 구현 | 일반 Discord 요청은 이전 대화·승인 메모리를 주입하지 않음; REPL만 제한된 프로세스 내 대화 포함 |
| 대시보드 | 로컬 관리·조회 구현 | 5초 인증 polling; Requests 통계와 memory 원본은 envelope 없는 operation을 누락 |

구현 근거는 [실행 경로](local_control_plane_implementation.md),
[P0 계약](p0_execution_20260912.md), [테스트 안내](test_catalog_ko.md)를 함께 확인한다.
기존 운영 기록의 서비스/Gateway 확인과 복구 안내 수신은 새 요청의 모델 응답 완료를
대신하지 않는다. 2026-09-21 기준 검토에서는 서비스, 운영 DB, 실제 Discord나 모델을 호출하지 않았다.

## 이번에 확인한 구체적 보완점

다음 항목은 수정 완료가 아니라 **수정 대기**다. 기존 테스트 통과가 이 결함을 배제하지 않는다.

| ID | 현상 / 확인 수준 | 필요한 검증 |
|---|---|---|
| REV-01 | 이전 시도 결과가 남아 있고 새 시도가 결과 저장 전 blocked가 되면 `OperationService.wait`가 timeout까지 기다리고 cancel을 호출할 수 있음. 실제 함수의 메모리 내 재현으로 확인 | 현재 시도 결과 여부로 판단하고, 보류 상태 대기가 취소로 바뀌지 않는 회귀 테스트 |
| REV-02 | Codex final-message 파일의 전체 읽기에 별도 크기 상한이 없음. stdout/stderr 제한과 다른 경로이며 소스로 확인 | 작은 stream + 큰 결과 파일을 만드는 가짜 CLI로 제한 검증 |
| REV-03 | provider snapshot에서 `AGENTS.md`, `AGENTS.override.md`가 이름 기준으로 제외되지 않음. 메모리 내 수집 재현으로 확인 | 루트/중첩 로컬 지침 제외와 제공 문맥 정책 정합성 검증 |

소스 위치: [wait](../src/nyanya_agent/operation_service.py),
[모델 출력](../src/nyanya_agent/model_routing.py),
[snapshot](../src/nyanya_agent/reviewed_changes.py).
REV-03은 Git/패키지 제외와 별개인 **모델 입력 경계**다. 실제 비공개 파일을 외부 모델에
보내는 테스트는 하지 않았으며, 이번 검토로 실제 유출이 발생했다고 판정하지 않는다.

## 다음 순서

1. REV-01–03을 제한된 수정과 회귀 테스트로 보완한다.
2. 등록된 테스트 workspace에서 실제 Discord 결과, 파일 승인, 두 요청 병렬 처리,
   중단 보류·why·상기·안전한 재개를 수용 검증한다.
3. DELIVERY-01: 메시지 중복 접수 방지, 전달 목적지, outbox 재시도, receipt와 진행 순서를 구현한다.
4. CONTEXT-01: owner/project/session 문맥과 승인 메모리를 operation에 연결하고
   전체 ingress의 request 통계·memory 원본을 원장 기준으로 전환한다.
5. 단일 요청의 다중 에이전트 작업 분해, 자원 기반 스케줄링, 추가 connector는 이후 진행한다.

외부 대시보드 접속과 서버·DB·호스팅 구성은 사용자 결정으로 보류한다.
Wiki/Release Notes는 수용 결과와 대상 버전을 확정한 뒤 별도 게시 작업으로 진행한다.

## 기준 검토의 검증과 문서 인계 — 2026-09-21

- 기준 소스: 28개 테스트 파일, 178개 테스트 함수, **318개 실행 케이스 통과**.
- Ruff, TypeScript typecheck, dashboard JavaScript 구문 검사 통과.
- 문서/manifest 변경 후 배포·패키지·공개 경계 관련 99개 회귀 케이스도 통과했다.
  이는 318개 중 관련 부분의 재실행이며 별도 신규 테스트 수가 아니다.
- 기준 소스의 패키지/privacy 검사 통과. 작업 중 신규 문서 링크 미포함을 검출했고
  문서를 npm 공개 파일 목록에 명시적으로 추가했다. CLI build를 포함한 최종
  release gate도 통과하여 패키지 링크·개인정보·비밀 패턴·버전 일치를 재검증했다.
- 현재 Git 추적 목록에 AGENTS, node_modules, private/runtime 파일은 없었다.
  최종 npm dry-run은 162개 항목이며 신규 공개 가이드를 포함하고 비공개 항목은 없었다.
  이는 과거의 모든 Git 객체나 모든 비밀 패턴을 완전히 검사했다는 뜻은 아니다.
- dependency 취약점 재감사, live 모델·Discord 수용, 운영 재시작, DB migration,
  외부 접속 설정, commit/push/publish는 이번 범위에 포함하지 않았다.
- 공개 문서는 재사용 가능한 동작·제한·검증만 기록한다. AGENTS와 에이전트별
  실행 기록·토큰 계측 여부·상세 조사 자료는 로컬 비공개 자료로 유지한다.

기준 검토의 문서 변경은 데이터 형식이나 운영 상태를 바꾸지 않는다. 문서 검토만 되돌릴
때는 해당 문서와 package manifest 차이를 검토하며 기존 로컬 변경이나 운영 데이터를 건드리지 않는다.
후속 폴더 분리의 복구에는 보존된 Git 메타데이터·worktree 경로·개발 전용 파일의
복원을 함께 검토해야 하며, 실행 중인 운영 DB를 이전 백업으로 덮어쓰지 않는다.
