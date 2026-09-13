# Python 테스트 안내서 — 311개 케이스

OPS-DEPLOY-01 후속 갱신, 2026-09-13.

## 테스트 수의 의미

정확한 폴더 이름은 tests다. 현재 테스트 파일 28개, 테스트 함수 176개이며
파라미터별 반복을 포함한 pytest 케이스는 311개다. conftest.py를 포함하면 Python 파일은 29개다.
2026-09-12의 22개 파일/132개 함수/150개 케이스에 종료 14개 함수/24개 케이스,
배포 안전성 16개 함수/36개 케이스, 패키지 7개 함수/11개 케이스와 표준입력 격리 1개 함수/2개 케이스를 추가했다.
함수와 매개변수 조합 수는 Python AST로 정적 확인했다. 테스트 모듈을 import하거나 pytest를 실행하지 않았다.
현재 호스트 전체 실행 결과는 **311 passed, upstream Starlette deprecation warning 1건**이다.
이 문서 작업의 재실행 결과가 아니며, 합계는 기존 150 + 종료 24 + 배포 36 + 패키지 11 + 표준입력 2 + 접수 차단 10 + 공개 경계 78 = 311이다.
이전의 111개는 2026-09-10 기준이고, P0 테스트 파일의 32개 함수/39개 케이스가 추가되었다.
기존 일부 케이스는 callback/legacy 동기화 대신 새 worker/원장 계약을 검증하도록 바뀌었다.

223은 제품 기능 수나 코드 커버리지 비율이 아니다. 실제 모델 호출은 pytest 밖에서
별도 임시 환경으로 확인했다. [P0 검증 문서](p0_execution_20260912.md)를 함께 본다.
원래 TC-001–111 식별자는 유지하고 신규 P0 케이스는 별도 표에 입력별로 정리했다.

## 실행 방식과 환경

- 임시 DB/파일: 실제 SQLite나 파일시스템을 쓰지만 운영 데이터 대신 pytest의 임시 경로를 사용한다.
- 가짜 응답: monkeypatch로 외부 호출을 고정 응답 또는 오류로 바꾼다. 성공·실패 조건을 재현하기 위한 장치다.
- 실제 subprocess: 테스트용 Python/shell/Node/tmux를 실행한다. 실제 Codex/agy 모델 호출과는 다르다.
- API 내부 호출: FastAPI TestClient가 앱 내부로 요청한다. 인터넷이나 실제 서버 포트에 연결하지 않는다.
- assert: 기대 결과를 코드로 확인하는 조건이다. 조건 하나라도 맞지 않으면 해당 케이스가 실패한다.

공통 설정은 [conftest.py](../tests/conftest.py)다. pytest 시작 시 NYANYA 환경변수를 보관·제거하고,
임시 상태 경로·없는 env 경로·임시 DB·시험용 workspace를 지정하며 기본 메모리 검색을 끈다.
종료 시 환경을 되돌리고 공통 임시 상태를 정리한다. 개별 시험은 필요한 설정을 다시 지정한다.
이 설정은 운영 상태 혼입을 줄이는 장치이며 전체 프로세스의 OS sandbox나 모든 환경변수 격리는 아니다.

## 파일별 요약

| 파일 | 함수 | 케이스 | 주된 검증 대상 |
|---|---:|---:|---|
| [test_agent_memory.py](../tests/test_agent_memory.py) | 3 | 3 | 시스템·장기 메모리 문맥 |
| [test_bridge_dashboard_recording.py](../tests/test_bridge_dashboard_recording.py) | 4 | 4 | bridge 작업 기록·상태 안내 |
| [test_bridge_policy.py](../tests/test_bridge_policy.py) | 5 | 5 | 요청 위험·승인 분류 |
| [test_cli_distribution.py](../tests/test_cli_distribution.py) | 6 | 6 | Node CLI·상태 배포 |
| [test_cli_safety_profiles.py](../tests/test_cli_safety_profiles.py) | 4 | 4 | backend URL·CLI 안전 옵션 |
| [test_codex_cli_resolution.py](../tests/test_codex_cli_resolution.py) | 9 | 14 | Codex 실행 파일·OS 오류 |
| [test_dashboard_execution_api.py](../tests/test_dashboard_execution_api.py) | 3 | 3 | FastAPI 작업·승인·조회 |
| [test_dashboard_store.py](../tests/test_dashboard_store.py) | 3 | 3 | 요청·프로젝트 집계 |
| [test_distribution_safety.py](../tests/test_distribution_safety.py) | 3 | 3 | 공개 파일 복사·설치 |
| [test_execution_adapters.py](../tests/test_execution_adapters.py) | 10 | 10 | 실행 adapter·산출물 |
| [test_execution_runtime.py](../tests/test_execution_runtime.py) | 3 | 3 | 실행 조정·승인·취소 |
| [test_execution_store.py](../tests/test_execution_store.py) | 8 | 8 | 원장·schema·lease |
| [test_manager_launchd.py](../tests/test_manager_launchd.py) | 2 | 2 | launchd 재시도 |
| [test_memory_store.py](../tests/test_memory_store.py) | 4 | 4 | 메모리 추출·검색·그래프 |
| [test_memory_worker.py](../tests/test_memory_worker.py) | 1 | 1 | 메모리 worker 1회 실행 |
| [test_p0_operations.py](../tests/test_p0_operations.py) | 32 | 39 | 직렬화·병렬 워커·파일 승인·복구·migration |
| [test_policy_documents.py](../tests/test_policy_documents.py) | 1 | 1 | 정책 Markdown 결합 |
| [test_runtime_paths.py](../tests/test_runtime_paths.py) | 5 | 5 | 코드·상태 경로 분리 |
| [test_safety_boundaries.py](../tests/test_safety_boundaries.py) | 11 | 13 | 권한·경로·백업·메모리 격리 |
| [test_task_service.py](../tests/test_task_service.py) | 2 | 2 | owner별 실행·취소 |
| [test_terminal_durable_path.py](../tests/test_terminal_durable_path.py) | 1 | 1 | terminal의 원장 경유 |
| [test_work_queue.py](../tests/test_work_queue.py) | 12 | 16 | claim·중단 보류·결과 저장 |
| [test_operation_shutdown.py](../tests/test_operation_shutdown.py) | 14 | 24 | worker·bridge 종료, 부모 소실, 부분 적용 보류 |
| [test_deployment_safety.py](../tests/test_deployment_safety.py) | 16 | 36 | legacy 보류·취소 소유권·파일 변경 직전 재검증 |
| [test_package_followup.py](../tests/test_package_followup.py) | 7 | 11 | 명시적 신뢰·개인정보 스캔·배포 파일과 링크 |
| [test_model_stdin.py](../tests/test_model_stdin.py) | 1 | 2 | 열린 부모 파이프와 모델 표준입력 격리 |
| [test_workspace_intake.py](../tests/test_workspace_intake.py) | 2 | 10 | 등록 누락·접수 실패 상태와 민감정보 차단 |
| [test_publication_privacy.py](../tests/test_publication_privacy.py) | 4 | 78 | 비공개 파일의 설치·패키지 포함 차단과 공개 필수 파일 유지 |
| **합계** | **176** | **311** | 공통 설정 파일 제외 |

## test_agent_memory.py — 3개

임시 파일·SQLite를 실제 사용한다. 모델 API는 호출하지 않는다. 검색 결과의 의미적 품질 평가는 아니다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-001 | 기본 시스템 문구와 임시 메모리 파일을 함께 제공 → 시스템 메시지에 메모리 제목과 본문 포함 | 단일 사례 | [test_build_messages_includes_agent_memory](../tests/test_agent_memory.py#L7) |
| TC-002 | 메모리 파일이 없는 경로 제공 → 오류 없이 기본 시스템 메시지만 생성 | 단일 사례 | [test_build_messages_allows_missing_agent_memory](../tests/test_agent_memory.py#L26) |
| TC-003 | 요청에서 추출한 메모리를 승인하고 검색 활성화 → 해당 owner의 관련 메모리가 모델 문맥에 포함 | 단일 사례 | [test_dynamic_memory_context_includes_approved_memory](../tests/test_agent_memory.py#L40) |

## test_bridge_dashboard_recording.py — 4개

실제 store/스레드/SQLite와 가짜 작업 응답을 결합한다. Discord 메시지 수신·업로드·Gateway 통신은 실행하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-004 | 가짜 작업 응답을 done으로 지정하고 비동기 제출 → 접수 안내·목표·일정 표시, 완료 응답, 원장 완료·저장 결과·legacy read view 반영 | 단일 사례 | [test_bridge_submit_records_async_completion](../tests/test_bridge_dashboard_recording.py#L34) |
| TC-005 | 첫 가짜 작업을 대기시킨 채 둘째 제출 → 첫 작업 실행 중, 둘째 대기열이라는 안내와 두 작업 제목 표시 | 단일 사례 | [test_bridge_task_status_lists_running_and_queued](../tests/test_bridge_dashboard_recording.py#L89) |
| TC-006 | 업로드 대신 uploaded를 반환하는 callback 제출 → task ID 발급, task 완료와 execution 성공 기록 | 단일 사례 | [test_bridge_custom_external_operation_is_durable](../tests/test_bridge_dashboard_recording.py#L112) |
| TC-007 | 미승인 README 수정 요청 → 실행 대신 계획 및 승인 필요 안내 반환 | 단일 사례 | [test_bridge_answer_returns_plan_for_unapproved_file_mutation](../tests/test_bridge_dashboard_recording.py#L137) |

## test_bridge_policy.py — 5개

함수의 위험 분류와 출력 문구 검사다. 모든 자연어 우회나 모델의 실제 지시 준수를 검증하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-008 | 허용되지만 trusted 목록 밖인 폴더에서 수정 요청 → extended·high 위험, 승인 필요, 미승인 | 단일 사례 | [test_extended_workspace_write_requires_approval](../tests/test_bridge_policy.py#L8) |
| TC-009 | trusted 폴더에서 수정 요청 → trusted·medium 위험이어도 승인 필요 | 단일 사례 | [test_trusted_file_mutation_still_gets_plan_gate](../tests/test_bridge_policy.py#L25) |
| TC-010 | 승인이라는 단어가 포함된 수정 요청 → 승인 필요 상태 유지, 실행 권한 부여 안 함 | 단일 사례 | [test_approval_words_are_not_execution_authorization](../tests/test_bridge_policy.py#L38) |
| TC-011 | 운영 프로토콜 문자열 생성 → 목표·범위·일정·절차·검증·중단·계획 재검토 문구 존재 | 단일 사례 | [test_task_operating_protocol_preserves_objective_and_requires_replanning](../tests/test_bridge_policy.py#L48) |
| TC-012 | 숨겨진 HTML에 이전 지시 무시 문구를 넣은 웹 요약 요청 → blocked 위험과 중단·프롬프트 관련 안내 | 단일 사례 | [test_external_hidden_prompt_injection_stops](../tests/test_bridge_policy.py#L59) |

## test_cli_distribution.py — 6개

Node와 빌드된 CLI를 실제 실행한다. CLI 파일이 없으면 manifest 검사를 제외한 5건은 skip. manifest 검사는 npm pack 결과 검사가 아니며 update 시험은 안내 출력만 확인한다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-013 | npm manifest 및 정적 UI 파일 검사 → dashboard asset 패턴과 HTML/CSS/JS 실제 파일 존재 | 단일 사례 | [test_npm_manifest_includes_dashboard_assets](../tests/test_cli_distribution.py#L16) |
| TC-014 | 임시 상태 경로에서 Node CLI config show 실행 → 별도 상태 경로와 user 모드 표시, owner 전용 설정 파일 생성, venv 미생성 | 단일 사례 | [test_config_show_creates_separate_state](../tests/test_cli_distribution.py#L40) |
| TC-015 | 포트를 99999로 설정하고 config validate 실행 → 종료 코드 1, 포트 오류와 검증 실패 출력 | 단일 사례 | [test_config_validate_rejects_invalid_port](../tests/test_cli_distribution.py#L54) |
| TC-016 | Node CLI update 실행 → npm 갱신 명령과 사용자 상태 보존 안내 출력; 실제 패키지 갱신은 안 함 | 단일 사례 | [test_update_command_preserves_user_state_policy](../tests/test_cli_distribution.py#L67) |
| TC-017 | 임시 설정·SQLite·로그를 준비하고 state backup 실행 → 설정과 DB는 복사, 로그 제외 | 단일 사례 | [test_state_backup_copies_only_durable_items](../tests/test_cli_distribution.py#L76) |
| TC-018 | legacy 설정·SQLite·PID·venv를 준비하고 state migrate 실행 → 설정과 DB는 이동 대상에 복사, run·venv 제외 | 단일 사례 | [test_state_migrate_excludes_venv_and_run](../tests/test_cli_distribution.py#L97) |

## test_cli_safety_profiles.py — 4개

네트워크와 CLI 실행을 대체한다. 옵션 전달을 확인하며 실제 agy/Codex sandbox 차단 효과는 확인하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-019 | file 스킴의 URL을 backend 요청에 전달 → HTTP/HTTPS만 허용한다는 ValueError | 단일 사례 | [test_backend_request_rejects_non_http_scheme](../tests/test_cli_safety_profiles.py#L12) |
| TC-020 | HTTPS URL과 가짜 JSON 응답 → JSON 객체 해석 성공; 실제 HTTPS 접속은 안 함 | 단일 사례 | [test_backend_request_accepts_https](../tests/test_cli_safety_profiles.py#L17) |
| TC-021 | agy 실행 함수를 가짜 함수로 교체 → 생성된 명령에 sandbox 옵션 포함하고 가짜 결과 반환 | 단일 사례 | [test_antigravity_uses_sandbox_by_default](../tests/test_cli_safety_profiles.py#L33) |
| TC-022 | Codex 실행·위험 판단을 대체하고 임시 결과 파일 생성 → read-only 옵션과 nyanya-readonly profile 전달 | 단일 사례 | [test_codex_read_only_invocation_uses_nyanya_profile](../tests/test_cli_safety_profiles.py#L50) |

## test_codex_cli_resolution.py — 14개

임시 파일·symlink·권한을 실제 다루며 1건은 임시 shell을 실제 실행한다. 나머지 OS 오류·preflight 의존 동작은 대체한다. 진짜 Codex 모델 호출은 없다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-023 | 임시 실행 파일만 PATH에 배치하고 override 제거 → 해당 실행 파일 발견 | 단일 사례 | [test_path_discovery](../tests/test_codex_cli_resolution.py#L17) |
| TC-024 | PATH에는 정상 파일, override에는 없는 파일 지정 → 다른 설치본으로 대체하지 않고 None | 단일 사례 | [test_broken_override_does_not_fallback](../tests/test_codex_cli_resolution.py#L23) |
| TC-025 | 실행 비트 없는 파일, 이어서 디렉토리를 override에 지정 → 두 경우 모두 거부 | 단일 사례 | [test_non_executable_and_directory_rejected](../tests/test_codex_cli_resolution.py#L29) |
| TC-026 | 대상이 없는 symlink를 override로 지정 → 거부 | 단일 사례 | [test_broken_symlink_rejected](../tests/test_codex_cli_resolution.py#L37) |
| TC-027 | 임시 shell 실행 파일을 resolver로 찾고 실제 subprocess 실행 → 종료 코드 0, stdout ok, 빈 stderr | 단일 사례 | [test_resolved_binary_starts](../tests/test_codex_cli_resolution.py#L44) |
| TC-028 | resolver가 실행 파일을 찾지 못하도록 대체 → 프로세스 시작 전 설정 관련 RuntimeError | 단일 사례 | [test_missing_binary_fails_before_spawn](../tests/test_codex_cli_resolution.py#L51) |
| TC-029 | 시작 함수에서 지정 OS 오류 발생 → errno는 안내하지만 예외의 비공개 경로와 상세문구는 제외 | ENOENT: 파일 없음 | [test_spawn_error_is_sanitized](../tests/test_codex_cli_resolution.py#L59) |
| TC-030 | 시작 함수에서 지정 OS 오류 발생 → errno는 안내하지만 예외의 비공개 경로와 상세문구는 제외 | EACCES: 접근 거부 | [test_spawn_error_is_sanitized](../tests/test_codex_cli_resolution.py#L59) |
| TC-031 | 시작 함수에서 지정 OS 오류 발생 → errno는 안내하지만 예외의 비공개 경로와 상세문구는 제외 | EPERM: 작업 권한 없음 | [test_spawn_error_is_sanitized](../tests/test_codex_cli_resolution.py#L59) |
| TC-032 | 시작 함수에서 지정 OS 오류 발생 → errno는 안내하지만 예외의 비공개 경로와 상세문구는 제외 | ENOEXEC: 실행 형식 오류 | [test_spawn_error_is_sanitized](../tests/test_codex_cli_resolution.py#L59) |
| TC-033 | 시작 함수에서 지정 OS 오류 발생 → errno는 안내하지만 예외의 비공개 경로와 상세문구는 제외 | EMFILE: 열린 파일 한도 초과 | [test_spawn_error_is_sanitized](../tests/test_codex_cli_resolution.py#L59) |
| TC-034 | manager와 bridge resolver에 동일 override 적용 → 같은 결과; 없는 경로로 바꾸면 manager도 거부 | 단일 사례 | [test_manager_uses_same_resolution](../tests/test_codex_cli_resolution.py#L79) |
| TC-035 | Codex 실행 파일이 없는 환경의 preflight → Codex 활성 여부에 맞는 종료 코드 | 활성: 오류 코드 1 | [test_preflight_checks_enabled_codex](../tests/test_codex_cli_resolution.py#L89) |
| TC-036 | Codex 실행 파일이 없는 환경의 preflight → Codex 활성 여부에 맞는 종료 코드 | 비활성: 정상 코드 0 | [test_preflight_checks_enabled_codex](../tests/test_codex_cli_resolution.py#L89) |

## test_dashboard_execution_api.py — 3개

FastAPI TestClient와 임시 DB를 사용한다. TCP 서버/브라우저/원격 사용자 환경을 실행하지 않는다. 조회 API는 무인증 성공을 검사하며 원격 읽기 인증을 보장하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-037 | FastAPI TestClient로 task 생성·조회·취소·retry·health 호출 → 무인증 생성 401, 인증 생성 201, 취소 완료, retry 409와 취소 상태 유지, schema 4 | 단일 사례 | [test_execution_read_api_and_authenticated_control_actions](../tests/test_dashboard_execution_api.py#L9) |
| TC-038 | 인증하여 프로젝트·논리 Codex session·task 생성 → 연결 ID 보존, API key 필드 마스킹, 프로젝트 필터 및 session 조회 성공 | 단일 사례 | [test_execution_project_codex_session_and_task_filters](../tests/test_dashboard_execution_api.py#L52) |
| TC-039 | 인증된 승인 결정과 event cursor 조회 → approved 응답, cursor 이후 seq의 이벤트 반환 | 단일 사례 | [test_approval_decision_and_cursor_event_read](../tests/test_dashboard_execution_api.py#L96) |

## test_dashboard_store.py — 3개

임시 SQLite에서 실제 저장·집계를 실행한다. 생성된 Discord 확인 문구를 실제 전송하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-040 | 요청 생성 후 running·completed 전이 → 소요시간·수신 이벤트·요약 집계·일별 완료 집계 기록 | 단일 사례 | [test_agent_request_lifecycle_and_usage](../tests/test_dashboard_store.py#L6) |
| TC-041 | 프로젝트 planning 단계에 다음 행동 등록 → 확인 필요 상태와 사용자 확인 메시지 생성 | 단일 사례 | [test_project_phase_check_requires_confirmation_when_next_action_exists](../tests/test_dashboard_store.py#L40) |
| TC-042 | 단계 확인을 같은 시간 구간에 두 번 호출 → 첫 호출만 확인 항목 반환 | 단일 사례 | [test_due_phase_checks_respects_interval](../tests/test_dashboard_store.py#L59) |

## test_distribution_safety.py — 3개

실제 파일 복사와 bash 설치를 임시 디렉토리에서 수행한다. bash 설치 1건은 Windows에서 skip. 의존성 다운로드·서비스 등록·npm 게시·Windows 설치 검증은 없다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-043 | 공개 파일만 manifest에 넣고 비공개 fixture를 함께 배치 → 공개 파일과 package manifest만 설치 대상에 복사 | 단일 사례 | [test_source_copy_uses_public_manifest_not_entire_checkout](../tests/test_distribution_safety.py#L11) |
| TC-044 | manifest에 비공개 설정 파일 또는 이를 가리키는 symlink 지정 → ValueError; 첫 실패에서 대상 폴더 미생성 | 단일 사례 | [test_source_copy_rejects_private_manifest_and_symlinks](../tests/test_distribution_safety.py#L24) |
| TC-045 | 공백 포함 임시 경로에서 bash installer를 의존성 설치 없이 실행 → 성공, 비공개 파일 제외, 상태 설정 생성, 생성 launcher의 help 성공 | 단일 사례 | [test_clean_source_install_without_network_or_services](../tests/test_distribution_safety.py#L39) |

## test_execution_adapters.py — 10개

subprocess와 tmux는 실제 실행한다. tmux가 없으면 관련 2건 skip. Orca는 가짜 shell/marker를 사용한다. 테스트용 workspace 검증을 대체하는 항목이 있어 이 파일만으로 경로 정책을 보장하지 않는다. 모든 하위 프로세스 종료를 개별 확인하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-046 | 실제 Python subprocess가 adapter-ok 출력 → succeeded·종료 코드 0·출력과 완료 marker 파일 확인 | 단일 사례 | [test_managed_subprocess_persists_completion_marker](../tests/test_execution_adapters.py#L55) |
| TC-047 | 실제 대기 subprocess를 시작하고 취소 → cancelled 및 running false 관측 | 단일 사례 | [test_managed_subprocess_can_cancel_process_group](../tests/test_execution_adapters.py#L74) |
| TC-048 | 실제 tmux session에서 짧은 Python 명령 실행 → succeeded·종료 코드 0·출력 확인 | 단일 사례 | [test_tmux_adapter_discovers_and_completes_session](../tests/test_execution_adapters.py#L92) |
| TC-049 | Codex 읽기/쓰기 및 agy AdapterRequest 생성 → 각각 요구된 profile·sandbox 옵션 포함; CLI 실행은 안 함 | 단일 사례 | [test_cli_adapters_build_explicit_safety_commands](../tests/test_execution_adapters.py#L110) |
| TC-050 | Orca 역할의 임시 shell이 정해진 JSON 반환 → runtime ready, terminal handle, running 및 cancel 상태 매핑 | 단일 사례 | [test_orca_adapter_maps_terminal_and_reports_runtime_state](../tests/test_execution_adapters.py#L125) |
| TC-051 | 완료 marker 파일과 Orca handle만 준비 → 실행 파일 없이 marker에서 succeeded 판정 | 단일 사례 | [test_orca_adapter_uses_completion_marker](../tests/test_execution_adapters.py#L165) |
| TC-052 | 가짜 Orca가 offline 반환 → 실제 tmux fallback으로 Python 명령 실행, 성공 출력과 fallback 근거 확인 | 단일 사례 | [test_orca_adapter_falls_back_to_tmux_when_runtime_is_offline](../tests/test_execution_adapters.py#L190) |
| TC-053 | workspace 내부 6바이트 파일과 외부 파일 검사 → 내부 파일 크기·64자리 hash 정보, 외부 파일 PermissionError | 단일 사례 | [test_artifact_collector_rejects_escape_and_records_hash](../tests/test_execution_adapters.py#L222) |
| TC-054 | 저장 PID가 살아 있다고 가정하되 소유한 process 객체 없음 → signal 호출 없이 lost, running true | 단일 사례 | [test_restarted_adapter_does_not_signal_unowned_pid](../tests/test_execution_adapters.py#L240) |
| TC-055 | 가짜 process가 계속 살아 있고 signal 권한 오류 발생 → cancelled 대신 lost, running true | 단일 사례 | [test_permission_denied_is_not_reported_as_cancelled](../tests/test_execution_adapters.py#L250) |

## test_execution_runtime.py — 3개

실제 Python subprocess와 SQLite를 사용하되 workspace 허용 검사는 대체한다. 복구는 동일 테스트 안에서 객체를 다시 만드는 방식이며 OS/service 강제 종료 시험이 아니다. 쓰기 승인 시험의 실제 명령은 print이므로 파일 수정 승인·적용 시험이 아니다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-056 | 실제 짧은 Python 실행 후 coordinator/adapter 객체를 새로 생성 → 저장 handle·marker로 성공 복구, task 완료와 session stopped | 단일 사례 | [test_coordinator_recovers_from_persisted_handle_and_marker](../tests/test_execution_runtime.py#L14) |
| TC-057 | 쓰기 resource를 지정한 실행을 승인 없이 시도 후 정확한 scope 승인으로 다시 시도 → 최초 거부, 승인 후 print 명령 성공, writer lease 재획득 가능 | 단일 사례 | [test_write_execution_requires_matching_persisted_approval](../tests/test_execution_runtime.py#L41) |
| TC-058 | 실제 대기 Python 실행을 coordinator로 취소 → execution과 task 모두 cancelled | 단일 사례 | [test_coordinator_cancels_active_execution](../tests/test_execution_runtime.py#L89) |

## test_execution_store.py — 8개

실제 SQLite와 스레드를 사용한다. host/profile 이름은 fixture다. heartbeat 시험은 offline만 직접 assert하며 stale 분기·원시 status 불변성은 별도 assert하지 않는다. append-only 시험은 UPDATE만 확인한다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-059 | schema 초기화를 두 번 수행하고 event UPDATE 시도 → 동일 schema v4 기록 유지, append-only 오류로 이벤트 수정 거부 | 단일 사례 | [test_versioned_migration_is_idempotent_and_events_are_append_only](../tests/test_execution_store.py#L13) |
| TC-060 | 6개 스레드에서 schema 초기화 12회 경합 → 전부 v4, 최종 schema v4 | 단일 사례 | [test_concurrent_schema_bootstrap_is_serialized](../tests/test_execution_store.py#L32) |
| TC-061 | host/profile/task/execution 생성 후 running→succeeded → 종료시각과 task completed 반영; 완료 후 running 역전 거부 | 단일 사례 | [test_task_execution_lifecycle_and_status_projection](../tests/test_execution_store.py#L42) |
| TC-062 | project·논리 Codex session·task 연결 → 연결/집계와 민감 metadata 마스킹, 다른 프로젝트 session 결합 거부 | 단일 사례 | [test_projects_and_codex_sessions_are_linked_to_tasks](../tests/test_execution_store.py#L65) |
| TC-063 | 민감 fixture가 들어간 task·승인·사유 생성 후 승인 → 상태 승인, password·사유·event에서 fixture 값 숨김 | 단일 사례 | [test_approval_and_audit_metadata_are_redacted](../tests/test_execution_store.py#L105) |
| TC-064 | worker A가 writer lease 확보 후 B 경합 → 최초 fence 1, B 거부, A 갱신·해제 성공 | 단일 사례 | [test_writer_lease_uses_fencing_and_owner_checks](../tests/test_execution_store.py#L129) |
| TC-065 | host와 runtime session heartbeat를 400초 전으로 조작 → 조회상 offline 판정 | 단일 사례 | [test_heartbeat_reports_stale_and_offline_without_destroying_raw_status](../tests/test_execution_store.py#L151) |
| TC-066 | legacy 요청 일회 import 후 legacy 상태 변경 → 기존 task 상태를 다시 덮어쓰지 않음 | 단일 사례 | [test_legacy_import_is_one_way_and_never_overwrites_current_ledger](../tests/test_execution_store.py#L169) |

## test_manager_launchd.py — 2개

launchctl과 sleep을 대체한다. 운영 macOS 서비스의 실제 복구·권한·등록을 확인하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-067 | 가짜 bootstrap 결과를 오류 5 다음 성공으로 지정 → 0.25초 대기 요청 1회 후 두 번째 호출 성공 | 단일 사례 | [test_bootstrap_with_retry_recovers_launchd_transition](../tests/test_manager_launchd.py#L9) |
| TC-068 | 가짜 bootstrap이 오류 78 반환 → 재시도·대기 없이 그대로 오류 반환 | 단일 사례 | [test_bootstrap_with_retry_does_not_retry_other_errors](../tests/test_manager_launchd.py#L33) |

## test_memory_store.py — 4개

규칙 기반 추출·검색·그래프 데이터의 SQLite 검사다. 실제 LLM 요약 품질이나 그래프 화면 렌더링 검사는 아니다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-069 | 완료 요청에서 보고 형식 메모리 추출 → 후보 1개·pending·중요도 기준, 그래프 노드·짧은 label·contains 간선 | 단일 사례 | [test_extract_memory_candidates_and_graph](../tests/test_memory_store.py#L6) |
| TC-070 | 생성 후보의 상태와 중요도를 변경 → approved 및 중요도 90 저장 | 단일 사례 | [test_update_memory_status](../tests/test_memory_store.py#L42) |
| TC-071 | 동일 문구로 승인 전후 검색 → pending은 검색 제외, approved는 검색 및 문맥 포맷에 포함 | 단일 사례 | [test_search_approved_memories_returns_only_approved](../tests/test_memory_store.py#L55) |
| TC-072 | 기술명 포함 요청 추출 → FastAPI·SQLite·Cytoscape.js 그래프 노드와 기술 수 확인 | 단일 사례 | [test_tech_stack_graph_extracts_known_technologies](../tests/test_memory_store.py#L74) |

## test_memory_worker.py — 1개

worker 함수를 한 번 호출한다. 장기 상주·주기 실행·LLM refinement는 시험하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-073 | 완료 요청을 준비하고 LLM refinement를 끈 채 worker 1회 실행 → pending·normal 후보 1개, refinement skipped 1 | 단일 사례 | [test_memory_worker_run_once_creates_pending_candidate](../tests/test_memory_worker.py#L7) |

## test_policy_documents.py — 1개

파일 집합과 특정 문구의 포함을 검사한다. 정책 내용의 타당성이나 실행 시 강제를 증명하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-074 | 정책 Markdown 로드 및 운영 프로토콜 구성 → 지정 파일 집합과 원장·Tailscale·검토 gate 문구 포함 | 단일 사례 | [test_markdown_policy_set_is_loaded_into_operating_protocol](../tests/test_policy_documents.py#L7) |

## test_runtime_paths.py — 5개

경로 계산과 임시 plist 생성을 검사한다. launchd 서비스는 등록하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-075 | macOS와 임시 home을 인자로 지정 → Library/Application Support 아래 앱 상태 경로 계산 | 단일 사례 | [test_default_user_state_root_uses_macos_application_support](../tests/test_runtime_paths.py#L10) |
| TC-076 | 코드 폴더에 legacy 설정이 있고 명시적 상태 override 없음 → 코드 폴더를 legacy 상태 경로로 유지 | 단일 사례 | [test_resolve_state_root_preserves_legacy_source_env](../tests/test_runtime_paths.py#L16) |
| TC-077 | legacy 설정과 별도 상태 override를 함께 제공 → 명시한 상태 경로 우선 | 단일 사례 | [test_resolve_state_root_honors_explicit_home](../tests/test_runtime_paths.py#L24) |
| TC-078 | 상대 DB 경로와 임시 상태 root 제공 → 상태 root 기준 절대 경로 계산 | 단일 사례 | [test_dashboard_relative_db_path_uses_state_root](../tests/test_runtime_paths.py#L34) |
| TC-079 | 임시 code/state/LaunchAgents 경로로 plist 생성 → Python 명령·code/state 환경값·로그 경로 분리; 실제 서비스 등록 없음 | 단일 사례 | [test_launchagent_uses_separate_code_and_state_paths](../tests/test_runtime_paths.py#L47) |

## test_safety_boundaries.py — 13개

임시 DB/파일과 가짜 backend를 사용한다. 대표 승인 문구 3개 및 특정 경로 사례를 검사한다. 승인 취소·파일 변경 직전 경쟁·전체 CLI artifact 중재는 미검증이다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-080 | workspace 설정 제거 → 허용 root 없음, HOME 접근 거부, 기본 작업 경로 선택 오류 | 단일 사례 | [test_unconfigured_roots_do_not_grant_home](../tests/test_safety_boundaries.py#L15) |
| TC-081 | 허용 root는 있지만 사용자 등록 파일이 없음 → 해당 사용자 실행 workspace 선택 blocked | 단일 사례 | [test_unassigned_user_cannot_fallback_to_an_allowed_root](../tests/test_safety_boundaries.py#L24) |
| TC-082 | 상위 이동·외부 symlink·외부 절대 경로 → 거부; 내부 새 파일 경로 허용, 작업 폴더 두 개는 서로 다름, 잘못된 종류 거부 | 단일 사례 | [test_paths_reject_traversal_and_symlink_escape](../tests/test_safety_boundaries.py#L35) |
| TC-083 | 승인 관련 단어를 포함한 수정/삭제 요청 → backend 호출 없이 awaiting_approval | 승인: README.md 파일을 수정해 | [test_terminal_write_gate_cannot_be_bypassed_by_words](../tests/test_safety_boundaries.py#L51) |
| TC-084 | 승인 관련 단어를 포함한 수정/삭제 요청 → backend 호출 없이 awaiting_approval | 승인하지 않았지만 README.md 수정 | [test_terminal_write_gate_cannot_be_bypassed_by_words](../tests/test_safety_boundaries.py#L51) |
| TC-085 | 승인 관련 단어를 포함한 수정/삭제 요청 → backend 호출 없이 awaiting_approval | approved delete file.txt | [test_terminal_write_gate_cannot_be_bypassed_by_words](../tests/test_safety_boundaries.py#L51) |
| TC-086 | 호스트 inventory 수집 함수를 호출 시 실패하도록 바꾼 뒤 문맥 구성 → 수집 없이 사용자 메시지 포함 | 단일 사례 | [test_model_context_does_not_collect_process_or_directory_inventory](../tests/test_safety_boundaries.py#L59) |
| TC-087 | 정확한 승인·변경 scope·다른 task·소비 후 재사용 순으로 검사 → 최초 허용, 불일치 거부, 1회 소비 후 거부 | 단일 사례 | [test_approval_checks_scope_actor_expiry_and_single_use](../tests/test_safety_boundaries.py#L74) |
| TC-088 | 이미 approved인 승인의 만료시간을 과거로 조작 → 실행 승인 검증 거부 | 단일 사례 | [test_expired_approved_command_is_rejected](../tests/test_safety_boundaries.py#L87) |
| TC-089 | 다른 actor 승인 및 만료 승인 결정 시도 → 각각 거부, 만료 상태는 DB에 expired로 보존 | 단일 사례 | [test_approval_wrong_decider_and_expiry_persist](../tests/test_safety_boundaries.py#L95) |
| TC-090 | WAL 모드 DB의 커밋된 행을 연결 열린 상태에서 백업 → 행 보존; 동일 대상 재백업은 거부 | 단일 사례 | [test_backup_includes_committed_wal_and_refuses_overwrite](../tests/test_safety_boundaries.py#L109) |
| TC-091 | DB가 아닌 바이트 파일을 백업 → DatabaseError, 원본 그대로, 실패 대상 제거 | 단일 사례 | [test_corrupt_database_backup_fails_without_touching_source](../tests/test_safety_boundaries.py#L126) |
| TC-092 | 사용자 one의 요청에서 메모리를 추출·승인 → one 검색 성공, two 검색 결과 없음 | 단일 사례 | [test_memory_is_not_globally_promoted_or_retrieved](../tests/test_safety_boundaries.py#L135) |

## test_task_service.py — 2개

실제 스레드/SQLite에 가짜 runner/responder를 연결한다. 재시작 가능한 독립 worker나 모델 프로세스 종료의 증거는 아니다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-093 | 같은 owner의 첫 runner를 대기시킨 채 두 번째 제출 → 둘째 queued·프로젝트 연결, 첫 해제 후 두 응답과 성공 상태 | 단일 사례 | [test_service_persists_queue_and_runs_one_task_per_owner](../tests/test_task_service.py#L21) |
| TC-094 | 실행 중 runner와 queued 작업을 각각 취소 → queued 취소, runner에 cancel event 전달 후 cancelled, 실행 응답 1회 | 단일 사례 | [test_service_cancellation_reaches_running_handler_and_queued_task](../tests/test_task_service.py#L69) |

## test_terminal_durable_path.py — 1개

실제 terminal 함수·worker thread·SQLite를 사용하고 모델은 가짜다. 실제 외부 모델 접속은 없다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-095 | 가짜 모델 worker로 terminal 단일 요청 실행 → 응답 출력·종료 코드 0, operator 소유의 operation/task 완료 | 단일 사례 | [test_terminal_single_prompt_uses_durable_execution_path](../tests/test_terminal_durable_path.py#L4) |

## test_work_queue.py — 16개

실제 SQLite, 스레드, 별도 프로세스 경합을 포함한다. 만료·오래된 실행·v2 자료는 시험 안에서 구성한다. 실제 프로세스 crash 위치별 fault injection 및 Discord 전달은 없다. 원자성 이름의 시험은 상태·결과 일치 검사이며 commit 도중 강제 종료는 하지 않는다.

| ID | 준비·행동 → 기대 결과 | 입력 변형 | 원문 함수 |
|---|---|---|---|
| TC-096 | 3개 별도 프로세스에서 동일 task에 6번 claim 경합 → 성공 claim 1개, execution 1개 | 단일 사례 | [test_separate_processes_claim_once](../tests/test_work_queue.py#L18) |
| TC-097 | 오래된 queued 행 뒤에 완료 이력 600개 추가 → owner의 대기 조회에서 오래된 작업 유지 | 단일 사례 | [test_pending_queue_not_limited_by_history](../tests/test_work_queue.py#L27) |
| TC-098 | claim 만료를 과거로 조작 → 갱신·완료 저장·재claim 거부, 복구 목록에 남고 running 원상태 유지 | 단일 사례 | [test_expired_worker_cannot_renew_commit_or_be_replayed](../tests/test_work_queue.py#L37) |
| TC-099 | 응답 본문에 실패처럼 보이는 문구를 넣고 typed 결과 저장 → 문구와 무관한 상태 매핑, 다른 owner 결과 조회 거부; 승인대기는 feedback.review 생성 | awaiting_approval-awaiting_approval | [test_typed_outcomes_are_saved_atomically](../tests/test_work_queue.py#L53) |
| TC-100 | 응답 본문에 실패처럼 보이는 문구를 넣고 typed 결과 저장 → 문구와 무관한 상태 매핑, 다른 owner 결과 조회 거부; 승인대기는 feedback.review 생성 | blocked-blocked | [test_typed_outcomes_are_saved_atomically](../tests/test_work_queue.py#L53) |
| TC-101 | 응답 본문에 실패처럼 보이는 문구를 넣고 typed 결과 저장 → 문구와 무관한 상태 매핑, 다른 owner 결과 조회 거부; 승인대기는 feedback.review 생성 | timed_out-failed | [test_typed_outcomes_are_saved_atomically](../tests/test_work_queue.py#L53) |
| TC-102 | 응답 본문에 실패처럼 보이는 문구를 넣고 typed 결과 저장 → 문구와 무관한 상태 매핑, 다른 owner 결과 조회 거부; 승인대기는 feedback.review 생성 | failed-failed | [test_typed_outcomes_are_saved_atomically](../tests/test_work_queue.py#L53) |
| TC-103 | 응답 본문에 실패처럼 보이는 문구를 넣고 typed 결과 저장 → 문구와 무관한 상태 매핑, 다른 owner 결과 조회 거부; 승인대기는 feedback.review 생성 | succeeded-completed | [test_typed_outcomes_are_saved_atomically](../tests/test_work_queue.py#L53) |
| TC-104 | 취소 요청 상태에서 runner가 성공 반환 → 취소 완료로 간주하지 않고 task blocked | 단일 사례 | [test_cancellation_request_does_not_prove_termination](../tests/test_work_queue.py#L65) |
| TC-105 | runner 성공 후 responder 예외 → 완료 결과 보존, 전달 uncertain, 민감 상세 대신 오류 타입 저장 | 단일 사례 | [test_delivery_failure_preserves_completed_result](../tests/test_work_queue.py#L74) |
| TC-106 | 기존 queued 행을 두고 새 service와 새 callback 제출 → 0.6초 동안 새 callback 미실행, 기존 작업 복구 목록 포함 | 단일 사례 | [test_restarted_service_does_not_run_old_callbacks](../tests/test_work_queue.py#L92) |
| TC-107 | 동일 task에 새 execution을 만든 뒤 옛 execution을 force 성공 처리 → Stale 오류, current execution 유지 | 단일 사례 | [test_old_attempt_cannot_override_new_attempt_even_with_force](../tests/test_work_queue.py#L104) |
| TC-108 | writer lease 해제·재획득 후 만료 조작 → fence 증가, 만료 lease 갱신 거부 | 단일 사례 | [test_lease_fence_survives_release_and_expired_renewal_fails](../tests/test_work_queue.py#L114) |
| TC-109 | 현재 migration 목록을 v2까지만 적용하여 queued 행 생성 후 v4 적용 → schema 4, queued 상태와 복구 조회 유지 | 단일 사례 | [test_schema_two_upgrades_preserving_queued_work](../tests/test_work_queue.py#L126) |
| TC-110 | 다른 owner 이름으로 task claim → 실패하고 queued 상태 유지 | 단일 사례 | [test_claim_cannot_change_task_owner](../tests/test_work_queue.py#L137) |
| TC-111 | 동일 생성시각에 z-old 다음 a-new 삽입 → ID 가나다순과 무관하게 삽입 순서대로 조회 | 단일 사례 | [test_equal_timestamp_queue_preserves_insertion_order](../tests/test_work_queue.py#L144) |

## 테스트를 지원하는 코드

이 함수들은 별도 케이스로 집계되지 않는다.

| 보조 함수 | 역할 |
|---|---|
| [conftest.py: pytest_configure](../tests/conftest.py#L8) | 공통 임시 환경 준비 |
| [conftest.py: pytest_unconfigure](../tests/conftest.py#L23) | 공통 환경 복원·정리 |
| [test_bridge_dashboard_recording.py: registered_workspace](../tests/test_bridge_dashboard_recording.py#L16) | bridge 시험마다 임시 사용자 workspace 등록 fixture |
| [test_cli_distribution.py: run_cli](../tests/test_cli_distribution.py#L24) | 임시 상태 환경으로 빌드된 Node CLI 실행 |
| [test_codex_cli_resolution.py: executable](../tests/test_codex_cli_resolution.py#L10) | Codex 역할의 임시 shell 실행 파일 fixture |
| [test_execution_adapters.py: wait_for_terminal](../tests/test_execution_adapters.py#L14) | adapter 종료 상태까지 제한시간 내 polling |
| [test_safety_boundaries.py: approved_command](../tests/test_safety_boundaries.py#L64) | 정확한 scope와 actor가 결합된 승인 fixture 생성 |
| [test_task_service.py: wait_for](../tests/test_task_service.py#L11) | 비동기 상태가 기대 조건에 도달할 때까지 제한시간 내 확인 |
| [test_work_queue.py: competing_claim](../tests/test_work_queue.py#L13) | 별도 프로세스에서 동일 작업 선점 시도 |

## 이 테스트가 아직 보장하지 않는 것

| 제품 기대 | 현재 증거 | 남은 검증 |
|---|---|---|
| Discord로 실제 작업 완료 | bridge callback·DB 통합 | Gateway 수신→실제 모델→메시지/첨부 전달 전체 흐름 |
| 중단 후 남은 작업 알림 | queued 보존·복구 조회·가짜 responder 실패 | 실제 bridge/worker 강제 종료, 재연결 통지, 중복 수신·전송 영수증 장애 |
| 기존 파일은 승인 후만 수정 | 대표 문구 차단·명령 scope 승인 | 파일별 diff/hash·승인 취소·변경 직전 경쟁·실제 적용 경로 |
| Codex/agy 안전 실행 | 명령 옵션·가짜 실행 파일·OS 오류 | 실제 설치본 sandbox, 모델 응답, 인증·OS 권한 문제 |
| 작업별 새 폴더와 결과물 | 경로 helper·고유 폴더·산출물 정보 | 모델이 생성하는 모든 파일의 경로 중재와 실제 Discord 첨부 흐름 |
| 실행 취소 | 테스트 자식 프로세스와 callback 취소 | 손자 프로세스·분리된 프로세스·provider 취소·서비스 재시작 뒤 종료 확인 |
| 데이터 업그레이드·복원 | v2→v4 queued fixture, v3→v4 task/execution/approval/event backup·restore, SQLite WAL 백업 | 실제 legacy/v1 전체 참조 fixture, 복원·rollback, 디스크 부족·동시 변경 |
| 개인 정보 보호 | 특정 metadata 마스킹·owner 검색 | 전체 로그·artifact·backup 보존/삭제, project 격리·동시 사용자 격리 |
| 안정적인 배포 | 임시 bash 설치·Node 상태 명령 | Windows/최소 버전 매트릭스, 의존성 감사, 실제 설치·업데이트·제거 |
| 멀티 에이전트·모델 선택 | 직접 검증하는 테스트 없음 | planner, capability, 분배, 비용·병렬 수 제한, 결과 통합 |

특히 이름에 atomic·restart·recover·sandbox가 있어도 실제 assert 범위를 넘어 보장한다고 읽으면 안 된다.
Orca 관련 시험 3개는 남아 있는 호환 코드의 회귀 검사다. Orca를 제품 방향에 다시 포함한다는 뜻이 아니다.
별도 수동 수용 시나리오는 [운영자 수용시험](user_acceptance_tests_ko.md)에 있다.

## 실행·수집 방법

프로젝트 루트에서 저장소 가상환경을 사용한다. 아래 명령은 예시이며 이 설명 작업에서 전체 실행을 다시 수행하지 않았다.

```bash
# 케이스 수집만 수행: 실제 테스트 본문은 실행하지 않음
PYTHONPATH=src .venv/bin/python -m pytest --collect-only -q

# 전체 실행
PYTHONPATH=src .venv/bin/python -m pytest -q

# 중요한 큐·안전 경계만 실행
PYTHONPATH=src .venv/bin/python -m pytest -v tests/test_work_queue.py tests/test_safety_boundaries.py

# 특정 테스트 함수만 실행
PYTHONPATH=src .venv/bin/python -m pytest -v tests/test_work_queue.py::test_separate_processes_claim_once

# skip 사유까지 표시
PYTHONPATH=src .venv/bin/python -m pytest -q -rs
```

Node CLI 시험 전에 build 결과가 필요하다. 누락된 CLI 때문에 5건이 skip되면 통과로 해석하지 않는다.
tmux가 없으면 2건, Windows에서는 bash 설치 1건이 skip 대상이다. 다른 의존성 부족은 skip이 아니라
수집 오류 또는 실행 실패가 될 수 있다. 결과 보고에는 passed/failed/skipped를 구분한다.

Ruff, TypeScript typecheck/build, JavaScript 구문 검사, release/privacy 검사와 문서 링크 검사는
별도의 검증 명령이다. 233개 pytest 케이스에 포함되지 않는다.

## 문서 작업 인계 — 2026-09-12 이력

2026-09-12 / CORE-STAB-01 P0 후속. main, 기준 commit 2182510.
기존 미커밋 변경을 보존하고 runtime·tests 변경에 맞춰 이 안내서를 갱신했다.
당시 22개 테스트 파일/132개 함수/150개 수집 항목을 안내했다. 원래 111개 안내의
문서 전용 작업은 2026-09-10 기록이며 이번 구현 작업과 구분한다.
소스·검증·rollback·운영 미적용 범위는 [P0 handoff](p0_execution_20260912.md)가 기준이다.

## P0 추가 케이스 — 39개

공통 setup은 임시 workspace/DB와 가짜 모델 Worker다. 아래 실제 모델 표시가 없는 시험은 모델 계정에 접속하지 않는다. 실제 모델 확인은 P0 handoff의 별도 evidence다.

| ID | 입력과 기대 결과 | 파라미터 | 소스 |
|---|---|---|---|
| TC-112 | 명세 JSON 왕복 일치; shell 필드와 미지원 version 거절 | 단일 사례 | [test_operation_roundtrip_and_unknown_executable_fields](../tests/test_p0_operations.py#L38) |
| TC-113 | 제출자 callback 없이 명세만으로 실행·결과·라우팅 event 저장 | 단일 사례 | [test_data_only_operation_runs_without_submitter_callback](../tests/test_p0_operations.py#L48) |
| TC-114 | 동일 소유자 요청 3개 경쟁 → 서로 다른 2개만 claim, 나머지 queued | 단일 사례 | [test_same_owner_parallelism_and_global_capacity](../tests/test_p0_operations.py#L57) |
| TC-115 | 종료된 worker의 요청은 보류; 새 작업 완료 응답에 미완료 상기; 타인 조회 거절 | 단일 사례 | [test_dead_worker_queue_is_held_but_other_tasks_can_complete](../tests/test_p0_operations.py#L67) |
| TC-116 | 과거 worker 완료 거절; 명시적 resume 후 새 worker가 새 시도 실행 | 단일 사례 | [test_recovery_rejects_old_worker_result_and_requires_explicit_resume](../tests/test_p0_operations.py#L88) |
| TC-117 | 중요도/영향도/복잡도 점수별 profile과 Luna xhigh/Astra low 매핑 확인 | 1-1-1-flash | [test_routing_axes](../tests/test_p0_operations.py#L107) |
| TC-118 | 중요도/영향도/복잡도 점수별 profile과 Luna xhigh/Astra low 매핑 확인 | 2-2-3-luna | [test_routing_axes](../tests/test_p0_operations.py#L107) |
| TC-119 | 중요도/영향도/복잡도 점수별 profile과 Luna xhigh/Astra low 매핑 확인 | 4-1-2-astra | [test_routing_axes](../tests/test_p0_operations.py#L107) |
| TC-120 | 중요도/영향도/복잡도 점수별 profile과 Luna xhigh/Astra low 매핑 확인 | 1-4-1-astra | [test_routing_axes](../tests/test_p0_operations.py#L107) |
| TC-121 | 중요도/영향도/복잡도 점수별 profile과 Luna xhigh/Astra low 매핑 확인 | 1-1-5-astra | [test_routing_axes](../tests/test_p0_operations.py#L107) |
| TC-122 | 잘못된 boolean 점수 → 보류 및 구체적 원인 저장, 모델 대체 없음 | 단일 사례 | [test_bad_model_assessment_fails_without_fallback](../tests/test_p0_operations.py#L118) |
| TC-123 | 승인 전 원본 보존; 잘못된 owner/hash 거절; 승인 후 적용·journal 백업·재사용 거절 | 단일 사례 | [test_review_preview_approval_and_exact_apply](../tests/test_p0_operations.py#L142) |
| TC-124 | 새 파일을 분류된 document/date 경로에 생성; 기존 파일 보존 | 단일 사례 | [test_create_is_exclusive_and_under_dated_task_directory](../tests/test_p0_operations.py#L165) |
| TC-125 | 파일 변경·만료·철회·symlink 각 조건에서 승인 후에도 적용 거절 | edited | [test_approval_revalidation_before_apply](../tests/test_p0_operations.py#L185) |
| TC-126 | 파일 변경·만료·철회·symlink 각 조건에서 승인 후에도 적용 거절 | expired | [test_approval_revalidation_before_apply](../tests/test_p0_operations.py#L185) |
| TC-127 | 파일 변경·만료·철회·symlink 각 조건에서 승인 후에도 적용 거절 | revoked | [test_approval_revalidation_before_apply](../tests/test_p0_operations.py#L185) |
| TC-128 | 파일 변경·만료·철회·symlink 각 조건에서 승인 후에도 적용 거절 | symlink | [test_approval_revalidation_before_apply](../tests/test_p0_operations.py#L185) |
| TC-129 | 삭제도 승인 전 보존하고 승인 후 지정 파일만 제거 | 단일 사례 | [test_delete_needs_approval](../tests/test_p0_operations.py#L206) |
| TC-130 | 두 파일 중 두 번째 replace 실패 → 첫 결과/이전 내용/journal 보존, 재적용 거절 | 단일 사례 | [test_partial_apply_failure_has_journal_and_no_automatic_replay](../tests/test_p0_operations.py#L217) |
| TC-131 | 모델 수정안 → awaiting_approval → 사람의 정확한 승인 → apply와 원래 task 완료 | 단일 사례 | [test_worker_executes_generated_plan_but_waits_for_modification_approval](../tests/test_p0_operations.py#L250) |
| TC-132 | 접수 뒤 workspace 등록 제거 → 실행 시 다시 검사하여 파일 작업 실패 | 단일 사례 | [test_workspace_registration_revalidated_in_worker](../tests/test_p0_operations.py#L281) |
| TC-133 | env·workspace mapping·symlink는 snapshot 제외, 공개 파일만 포함 | 단일 사례 | [test_snapshot_does_not_include_private_state_or_symlinks](../tests/test_p0_operations.py#L292) |
| TC-134 | barrier로 두 thread가 모델 단계에 실제 동시 진입함을 확인 | 단일 사례 | [test_two_real_worker_threads_run_simultaneously](../tests/test_p0_operations.py#L302) |
| TC-135 | 실제 별도 Python worker와 가짜 CLI 실행 → 저장된 명세 처리·결과 회수·process 종료 | 단일 사례 | [test_dedicated_worker_process_executes_spec_with_fake_cli](../tests/test_p0_operations.py#L336) |
| TC-136 | 실제 worker를 정지·강제 종료 → queued 요청 보존, 보류·원인 조회 | 단일 사례 | [test_real_worker_death_preserves_queued_request](../tests/test_p0_operations.py#L364) |
| TC-137 | 실패 후 resume 직후에는 옛 결과 반환·전달 금지; 새 시도 결과만 수신 | 단일 사례 | [test_resume_wait_and_delivery_never_return_previous_attempt](../tests/test_p0_operations.py#L387) |
| TC-138 | 유효한 worker 없는 resume 거절; 총 3회 이후 재시도 거절 | 단일 사례 | [test_explicit_retries_are_bounded_and_require_live_generation](../tests/test_p0_operations.py#L408) |
| TC-139 | 타인 resolve 거절; 관측 후 변경되면 hash 거절; 확인 처리 시 파일 재작성 없음 | 단일 사례 | [test_interrupted_apply_resolution_binds_owner_and_observed_files](../tests/test_p0_operations.py#L423) |
| TC-140 | 외부 편집 후에도 저장된 원본/변경 diff를 유지하고 변경된 상태 경고 | 단일 사례 | [test_preview_preserves_original_review_even_after_external_change](../tests/test_p0_operations.py#L451) |
| TC-141 | 인증 없는 접수 거절; 인증된 API 요청은 worker로 처리; 전달 안 한 결과는 pending | 단일 사례 | [test_api_operation_submission_uses_worker_and_preserves_undelivered_result](../tests/test_p0_operations.py#L469) |
| TC-142 | 별도 process 4개의 동시 claim → 고유 작업 2개만 허용 | 단일 사례 | [test_separate_process_claims_share_atomic_capacity](../tests/test_p0_operations.py#L494) |
| TC-143 | worker heartbeat가 살아 있어도 만료 claim은 보류; stale 완료 거절 | 단일 사례 | [test_expired_claim_is_held_even_with_live_worker_heartbeat](../tests/test_p0_operations.py#L507) |
| TC-144 | 파일 생성 뒤 결과 유실 상태 → request resume로 파일 생성 반복 금지 | 단일 사례 | [test_creation_side_effects_cannot_be_replayed_after_result_loss](../tests/test_p0_operations.py#L519) |
| TC-145 | 원래 요청 취소 후에는 승인된 파일안도 적용 거절 | 단일 사례 | [test_cancelled_original_task_cannot_apply_approved_plan](../tests/test_p0_operations.py#L541) |
| TC-146 | worker 시작 오류 → 원래 요청과 시작 실패 근거 저장; 즉시 보류 결과 조회 | 단일 사례 | [test_worker_start_failure_retains_request_and_reason](../tests/test_p0_operations.py#L560) |
| TC-147 | 원격/forwarded 조회에 token 필요; loopback과 health 경계 확인 | 단일 사례 | [test_remote_and_forwarded_reads_require_authentication](../tests/test_p0_operations.py#L575) |
| TC-148 | v3 task/execution/approval/event 백업 → v4 upgrade 및 v3 restore 후 무결성·참조 보존 | 단일 사례 | [test_schema_three_backup_upgrade_and_restore_preserve_work](../tests/test_p0_operations.py#L591) |
| TC-149 | 실제 테스트 process 취소 회수; 5 MB 출력은 제한 초과로 보류 | 단일 사례 | [test_owned_process_cancellation_and_output_limit](../tests/test_p0_operations.py#L619) |
| TC-150 | 실제 apply process가 파일 replace·fsync 직후 종료 → 파일은 after, journal은 prepared; 재적용 거절 및 관측 hash 확인으로 완료 처리 | POSIX 실제 process 강제 종료 | [test_real_apply_crash_after_file_commit_is_reconciled_without_replay](../tests/test_p0_operations.py#L652) |

## OPS-DEPLOY-01 추가 케이스 — 71개

2026-09-13 정적 대조: 신규 37개 함수의 매개변수 조합은 71개다. 아래 한 행은 함수 하나이며,
여러 TC 번호를 묶은 행은 입력 열의 조합 수만큼 케이스를 뜻한다. 함수 내부 반복은 별도 pytest 케이스로 세지 않는다.
기존 TC-001–150과 111/150 시점의 설명은 이력으로 보존한다. 위의 과거 검증 한계 표는
당시 범위이며, 종료·파일 적용·신뢰·패키지의 추가 증거는 아래 표에서 구분한다.

### test_operation_shutdown.py — 종료 처리

임시 SQLite·workspace와 실제 스레드/OS pipe를 사용한다. 시작 실패는 가짜 프로세스·시계, Discord는 FakeClient, Telegram은 설정·실행 대체로 검사한다. signal 4건과 controller 소실 1건은 실제 임시 Python 프로세스를 실행하되 모델은 모의 함수다. 부분 apply 1건과 이 프로세스 5건은 POSIX가 아니면 skip이다. 운영 서비스 종료, 실제 Discord Gateway·Telegram 통신, Codex/agy 모델 호출이나 분리된 모든 자손 프로세스 종료를 입증하지 않는다.

| ID | 입력·변형 | 기대 assertion | 원문 함수 |
|---|---|---|---|
| TC-151–154 | once=False/True × explicit_cancel=False/True, 4조합 | 상주/run_once 종료 시 실행·대기 작업은 blocked, 명시적으로 취소한 실행만 cancelled. 이미 취소한 대기 작업과 완료 결과는 보존. 원요청·단계·사용자 취소 아님 안내를 확인하고 worker closed, claim 전부 해제, 이벤트 정리, 새 worker 자동 claim 없음 확인 | [test_shutdown_holds_work_but_preserves_explicit_cancel_and_completion](../tests/test_operation_shutdown.py#L56) |
| TC-155 | 단일 사례 | 모의 실행 중 명시적 취소 후 종료 확인 응답 → task cancelled, worker 자체 stop은 설정되지 않음 | [test_explicit_cancel_without_worker_shutdown](../tests/test_operation_shutdown.py#L102) |
| TC-156 | 단일 사례 | perform이 stop을 설정하면서 성공 반환 → 완료 task를 blocked로 바꾸지 않고 worker·claim·이벤트 정리 | [test_completed_result_during_shutdown_is_not_relabelled](../tests/test_operation_shutdown.py#L117) |
| TC-157 | 단일 사례 | run_once 전에 stop 설정 → 실행하지 않고 False, task blocked, attempts=0, worker 정리 | [test_run_once_already_stopped_does_not_claim](../tests/test_operation_shutdown.py#L131) |
| TC-158 | 단일 사례 | perform에서 KeyboardInterrupt 주입 → 예외 재전파, task blocked, worker closed·미해제 claim 없음·이벤트 정리 | [test_run_once_base_exception_stops_monitor_and_recovers](../tests/test_operation_shutdown.py#L142) |
| TC-159 | 단일 사례; POSIX 전용 | 두 파일 중 첫 replace 직후 종료 → 첫 파일만 after, 둘째 before, apply task blocked·plan uncertain. 새 worker에서 부모와 apply의 resume는 reconciliation 오류, 자동 claim 없음, 기존 worker 정리 | [test_shutdown_during_partial_apply_keeps_reconciliation_gate](../tests/test_operation_shutdown.py#L157) |
| TC-160–161 | cannot_reap=False/True, 2조합 | 시작 시간 초과를 가짜 시계·프로세스로 재현 → terminate→wait(5)→kill→wait(3), 회수 실패 때도 요청 blocked와 시작 실패 사유 보존. stdin 닫힘·generation 미설정·부모 PID 인자와 PIPE 전달 확인 | [test_startup_timeout_bounds_terminate_kill_reap_and_retains_request](../tests/test_operation_shutdown.py#L222) |
| TC-162 | 단일 사례; 시작 시도 2회 | Popen에 OSError 주입 → 매번 예외, generation 미설정, 두 번 모두 실제 시작 함수 호출을 시도하여 준비 완료로 캐시하지 않음 | [test_failed_spawn_is_not_cached_as_ready](../tests/test_operation_shutdown.py#L246) |
| TC-163 | 단일 사례; 정상 부모 pipe EOF, 잘못된 부모 값 | 실제 OS pipe를 열어 둔 동안 stop 없음, 쓰기 끝 닫으면 stop. 잘못된 부모 식별값으로 감시 시작해도 즉시 stop | [test_parent_pipe_loss_stops_worker_and_wrong_parent_fails_closed](../tests/test_operation_shutdown.py#L262) |
| TC-164–167 | SIGTERM/SIGINT × once=False/True, 4조합; POSIX 전용 | 실제 임시 Python worker가 RUNNING 출력 후 signal 수신 → worker closed 1개, 실행·대기 task blocked 2개, CLOSED_AND_HELD 출력, 종료 코드 0·stderr 없음. 모델 함수는 모의 | [test_standalone_worker_main_signals_close_and_hold](../tests/test_operation_shutdown.py#L283) |
| TC-168 | 단일 사례; POSIX 전용 | 직접 만든 임시 controller 프로세스를 kill → 상속 pipe를 감시하는 자식 worker가 실행·대기 작업을 blocked로 보류하고 CLOSED_AND_HELD 출력, stderr 없음. 모델은 모의이고 임의의 운영 PID를 찾지 않음 | [test_real_controller_death_closes_orphan_worker_without_replay](../tests/test_operation_shutdown.py#L331) |
| TC-169–171 | termination=sigterm/cancel/failure, 3조합 | 가짜 Discord client에 반복 SIGTERM, asyncio 취소, 시작 오류 주입 → client를 먼저 닫고 store close는 이벤트 루프 밖 스레드에서 1회 수행, 루프 진행 유지. 이전 SIGTERM handler 복원, SIGINT 등록 없음. 취소·실패는 해당 예외 재전파 | [test_discord_orderly_close_is_off_loop_and_restores_signal](../tests/test_operation_shutdown.py#L396) |
| TC-172 | 단일 사례; 보조 스레드 | 가짜 Discord client를 보조 스레드 이벤트 루프에서 종료 → 스레드 종료, signal 등록 없이 close만 1회 | [test_discord_does_not_register_signals_off_main_thread](../tests/test_operation_shutdown.py#L447) |
| TC-173–174 | main_thread=False/True, 2조합 | Telegram 설정·store·run을 모의 처리 → 주 스레드에서는 SIGTERM 처리 후 이전 handler 복원·정상 반환, 보조 스레드에서는 signal 등록 없음·스레드 종료. 양쪽 모두 store close 1회 | [test_telegram_sigterm_cleanup_and_thread_guard](../tests/test_operation_shutdown.py#L466) |

### test_deployment_safety.py — 배포 안전성

실제 임시 SQLite·파일시스템과 monkeypatch 장애 주입을 사용한다. API 6건은 FastAPI TestClient의 앱 내부 호출로 실제 네트워크 서버를 열지 않는다. legacy writer 정지·백업 확인은 fixture 전제와 인자일 뿐 운영 프로세스 정지·백업·라이브 migration 검증이 아니다. 취소 확인은 저장된 typed 결과로 모사하고, 모델·Discord·실제 서비스 배포는 수행하지 않는다. 파일 적용 결과는 candidate host 환경의 증거이며 Windows 지원을 보장하지 않는다.

| ID | 입력·변형 | 기대 assertion | 원문 함수 |
|---|---|---|---|
| TC-175–176 | version=2/3, 2조합 | 임시 legacy DB를 현 schema로 올려도 일반 recover는 기존 running을 보류하지 않음. writers_stopped=False는 거부, True로 명시 보류 시 2개 task blocked·모든 기존 시도 lost·claim 해제. 재호출은 0, 원요청·사유·시도 수 2/0 보존, event 2개·외래키 무결성 확인. 새 operation/자동 claim 없음, resume 거부, 명시 취소 가능 | [test_quiesced_legacy_upgrade_holds_all_attempts_without_replay](../tests/test_deployment_safety.py#L43) |
| TC-177–178 | attempts=0/2, 2조합 | execution 행 1개와 별도로 operation 시도 수 지정 → incomplete와 explain 모두 행 개수 대신 지정한 attempts 사용 | [test_incomplete_preserves_operation_attempts_over_execution_count](../tests/test_deployment_safety.py#L91) |
| TC-179 | 단일 사례 | legacy 보류 감사 event 기록에 오류 주입 → 예외 발생, task/execution running과 미해제 claim을 원자적으로 유지 | [test_upgrade_audit_failure_rolls_back_task_execution_and_claim](../tests/test_deployment_safety.py#L100) |
| TC-180–181 | claim_state=expired/released, 2조합 | 만료 또는 해제된 claim의 task 취소 → 무기한 cancelling 대신 task blocked·execution lost·claim released·eligible=0, 늦은 성공 finish는 Stale 오류 | [test_cancellation_without_usable_claim_does_not_wait_forever](../tests/test_deployment_safety.py#L122) |
| TC-182 | 단일 사례 | 유효 claim의 task 취소 → task/execution cancelling 유지, worker의 cancelled 결과를 finish한 뒤 task cancelled | [test_active_cancel_still_requires_worker_acknowledgement](../tests/test_deployment_safety.py#L140) |
| TC-183 | 단일 사례 | 취소 접수 후 확인 전에 worker를 closed 처리 → recover 1개, task blocked·execution lost | [test_cancel_remains_recoverable_if_worker_dies_before_acknowledgement](../tests/test_deployment_safety.py#L150) |
| TC-184 | 단일 사례 | 현재 실행과 다른 expected_execution_id로 취소 → no longer current 오류, 현재 execution running 유지 | [test_old_execution_cancellation_cannot_cancel_a_new_attempt](../tests/test_deployment_safety.py#L160) |
| TC-185–188 | endpoint=tasks/executions × approved=False/True, 4조합 | 승인 대기 부모를 API 취소 → 무인증 401, 인증 200·cancelled. pending/approved 양쪽 계획 모두 후속 승인·apply 거부, 원본 before 유지 | [test_dashboard_cancel_waiting_parent_prevents_approval_and_apply](../tests/test_deployment_safety.py#L170) |
| TC-189–190 | endpoint=tasks/executions, 2조합 | 다른 owner의 task에 요청 본문 actor를 맞춰 위조하고 인증 취소 → 403, 실행 running 유지 | [test_dashboard_cancel_does_not_trust_payload_owner](../tests/test_deployment_safety.py#L197) |
| TC-191–198 | loss=eligible/released/expired/current/worker/execution/parent/missing_record, 8조합 | 실행 자격 제거, claim 해제·만료, 현재 실행 연결 제거, worker 종료, execution cancelling, 부모 취소, record 누락 각각 주입 → apply 거부, journal 0개, 원본 before와 원본 파일만 유지 | [test_stale_apply_rejected_before_journal](../tests/test_deployment_safety.py#L217) |
| TC-199–201 | action=create/modify/delete, 3조합 | journal 생성 뒤 첫 workspace 변경 전에 eligible 제거 → ownership 오류·plan uncertain, 파일 바이트 목록 전후 동일. create에서는 폴더도 생성하지 않음 | [test_eligibility_lost_after_journal_before_any_workspace_mutation](../tests/test_deployment_safety.py#L246) |
| TC-202 | 단일 사례 | 임시 파일 fsync 트랜잭션 직후 eligible 제거 → ownership 오류, 원본 before 유지, after 내용의 임시 파일 1개 보존, plan uncertain. replace와 임시 파일 삭제를 추가 수행하지 않음 | [test_eligibility_loss_after_temp_write_prevents_replace_and_cleanup](../tests/test_deployment_safety.py#L277) |
| TC-203–207 | (create,mkdir), (create,open), (modify,open), (modify,fchmod), (modify,replace), 5조합 | 지정 파일 변경 직후 DB 트랜잭션 경계에서 eligible 제거 → ownership 오류·plan uncertain. 상실 시점에 관측한 경로·권한·파일 바이트 목록과 종료 후 목록이 동일하여 이후 추가 변경 없음 | [test_no_further_mutations_after_ownership_loss_at_each_boundary](../tests/test_deployment_safety.py#L313) |
| TC-208 | 단일 사례 | 정상 승인과 현재 product 실행 record로 apply·finish → 원본 after, 부모 task completed | [test_valid_product_record_applies_and_completes_parent](../tests/test_deployment_safety.py#L359) |
| TC-209 | 단일 사례 | 정상 product record로 파일 생성 뒤 결과 유실을 blocked 결과로 모사 → resume는 File side effects 오류. reconcile 관측 hash로 resolve 후 task completed, 생성 파일은 1개 | [test_product_creation_result_loss_still_requires_reconciliation](../tests/test_deployment_safety.py#L368) |
| TC-210 | 단일 사례; 한 번도 claim하지 않은 계획 helper | 격리 fixture에서 실행 이력이 없는 새 파일 계획을 record 없이 apply → 계획이 지정한 경로에 new 내용 생성. 실행 중 product record 검증의 우회 허용을 뜻하지 않음 | [test_never_started_isolated_plan_helper_contract](../tests/test_deployment_safety.py#L385) |

### test_package_followup.py — 패키지·신뢰 정책

환경변수는 monkeypatch로 격리하고 신뢰 경계·symlink·스캔·복사를 임시 경로에서 확인한다. package_checks의 함수와 공개 배포 복사를 사용하며 개인정보는 합성 fixture다. 마지막 항목은 실제 로컬 복사지만 npm pack, 설치·빌드·게시 또는 네트워크 검증이 아니다. 실제 비밀 자료 전체에 대한 완전한 탐지 보장도 아니다.

| ID | 입력·변형 | 기대 assertion | 원문 함수 |
|---|---|---|---|
| TC-211–215 | configured=None, 빈 문자열, 공백 2개, 쉼표·공백만, 루트 슬래시, 5조합 | trusted roots 미설정/빈 값/루트 값 → 신뢰 목록 비어 있음·프로젝트 root 자동 신뢰 없음. 명시 등록 workspace는 정상 해석하되 수정 요청은 extended·승인 필요·미승인 | [test_no_implicit_trust_preserves_registered_workspace_and_approval](../tests/test_package_followup.py#L18) |
| TC-216 | 단일 사례; 중복 등록 root·미등록 root·루트 슬래시·외부 symlink | 명시 신뢰 목록은 중복·루트 슬래시 제거. 등록 root만 trusted, 미등록 root와 이를 가리키는 내부 symlink는 blocked·경로 해석 거부 | [test_explicit_trust_never_grants_unregistered_access](../tests/test_package_followup.py#L34) |
| TC-217 | 단일 사례 | workspace 등록 설정 두 종류를 제거하고 trusted만 지정 → blocked, 기본 workspace 선택은 explicit workspace root 오류 | [test_trust_alone_cannot_replace_workspace_registration](../tests/test_package_followup.py#L52) |
| TC-218 | 단일 케이스 내부 검사: 탐지 예시 6개·허용 예시 6개 | Path.home 계열 기본 개인 폴더 2종, 홈 축약 문서 1종, set_home 상대 개인 폴더 예시 3종 → personal 탐지. 저자·저작권 이름, 명시 신뢰 경로 placeholder, set_home 경로 placeholder 2종, 표준 Library 경로 → 탐지 없음. 이름 전체를 금지하지 않음 | [test_privacy_scan_detects_defaults_without_blacklisting_author_names](../tests/test_package_followup.py#L61) |
| TC-219 | 단일 사례; 텍스트·NUL 포함 바이너리 | 동일 가짜 개인 경로를 텍스트와 바이너리에 넣어 보고서 생성 → personal 보고서는 해당 텍스트 파일명 한 줄만 포함, secret 보고서는 비어 있음. 일치한 실제 문자열·바이너리 파일명은 출력하지 않음 | [test_privacy_reports_keep_matching_values_out_of_output](../tests/test_package_followup.py#L85) |
| TC-220 | 단일 사례; 링크 대상 미포함/포함, 필수 파일 누락·비공개 파일 포함 | checkout에 상대 링크 대상이 존재해도 manifest에 없으면 unpackaged relative link 오류. 대상 포함 시 오류 없음; 웹 링크·문서 내부 anchor는 허용. 빌드 helper 누락과 sessions 경로 포함은 각각 오류 | [test_manifest_requires_packaged_link_targets_even_if_they_exist_in_checkout](../tests/test_package_followup.py#L96) |
| TC-221 | 단일 사례; 실제 임시 배포 복사 | 공개 manifest로 임시 배포를 복사 → package_errors 없음, 빌드 helper·이 카탈로그·conftest 포함. package.json의 files에는 docs 전체를 포괄하는 세 가지 패턴 없음 | [test_public_distribution_has_build_helper_and_resolvable_documentation](../tests/test_package_followup.py#L113) |

### OPS-DEPLOY-01 문서 작업 인계

요청 역할은 테스트 카탈로그 갱신, 요청 모델/effort는 GPT 6 Astra medium이다.
이번 작업은 이 문서만 수정했으며 소스·테스트·운영 상태를 변경하지 않았다.
정적 확인은 신규 14/16/7개 함수와 24/36/11개 조합, 추가 표준입력 1개 함수/2개 조합을 포함해 접수 차단 2개 함수/10개 조합을 추가한 전체 27개 테스트 파일/172개 함수다.
233 passed와 Starlette 경고 1건은 부모 세션의 authoritative candidate host 결과를 인용했다.
테스트 실행·수집, Git, 네트워크·서비스 작업은 수행하지 않아 현재 branch/commit과 live 상태는 재확인하지 않았다.
기존 TC 행을 보존하고 새 37개 함수의 표 누락·중복 및 수치 일치를 정적으로 점검했다.
최종 패키지 포함 여부·문서 링크·개인정보 스캔은 부모 세션이 수행한다. 실제 Discord/모델 수용 검증은
이 71개 자동화 케이스의 범위 밖이며, 이 문서 갱신에 필요한 사용자 전용 단계는 없다.
되돌림이 필요하면 이번 머리말·요약 갱신과 OPS-DEPLOY-01 추가 부분만 복원하고 기존 이력은 유지한다.

### test_model_stdin.py — 실제 모델 검증에서 발견한 표준입력 대기

| 케이스 | 입력 | 검증 내용 | 함수 |
|---|---|---|---|
| TC-222–223 | 부모 파이프 writer를 닫지 않은 채 빈 데이터 또는 controller-liveness 바이트를 넣음 | 실제 Python 자식이 stdin EOF를 즉시 받고 정상 종료한다. 인자로 전달한 prompt는 유지되고 원래 부모 파이프 바이트는 소비되지 않는다. 수정 전에는 2초 제한으로 실패했고 DEVNULL 적용 후 통과했다. 실제 Codex 모델 호출은 이 테스트에 포함하지 않는다 | [test_model_stdin_eof_preserves_open_controller_pipe](../tests/test_model_stdin.py#L16) |

### test_workspace_intake.py — 실제 Discord 수용에서 발견한 접수 차단 기록

| 식별자 | 입력·조건 | 기대 결과 | 구현 |
|---|---|---|---|
| TC-224–227 | auto/gemini/codex/codex_write의 실제 요청자 등록 누락; 다른 계정 등록과 허용 root만 존재 | 요청 기록 blocked 및 prerequisite_failed 사유 저장, operation·execution·worker 생성 0 | [test_missing_owner_workspace_records_block_without_submission](../tests/test_workspace_intake.py#L62) |
| TC-228–233 | workspace/submission 단계 × ValueError/OSError/RuntimeError | 안전한 예외 유형만 응답·저장, 내부 상세는 응답·기록·출력에 없음 | [test_generic_prerequisite_failure_records_only_safe_diagnostic](../tests/test_workspace_intake.py#L81) |

접수 후속 변경을 통합한 실제 호스트 전체 실행은 233 passed, upstream 경고 1건이었다.

### test_publication_privacy.py — 공개 배포 경계

| 식별자 | 입력·조건 | 기대 결과 | 구현 |
|---|---|---|---|
| TC-234–271 | PRIVATE_PATHS의 중첩 AGENTS, env 변형, 비공개 설정, 키, DB 백업, 보고서 등 38종 | 명시적으로 manifest에 넣어도 대상 폴더 생성 전 설치 복사 거부 | [test_private_manifest_rejected_before_any_copy](../tests/test_publication_privacy.py#L44) |
| TC-272–309 | 같은 비공개 경로 38종을 패키지 파일 목록에 삽입 | 파일 내용을 읽지 않고 경로만으로 패키지 오류 반환 | [test_package_audit_rejects_same_private_paths_without_reading_them](../tests/test_publication_privacy.py#L55) |
| TC-310 | 공개 env 예제, 일반 설정, launchd 템플릿, 제품 dashboard HTML, 소스와 설계 문서 | 공개 필수 파일은 설치 복사 및 패키지 검사 통과 | [test_required_public_templates_copy_and_pass_package_audit](../tests/test_publication_privacy.py#L64) |
| TC-311 | Python isolated mode, PYTHONPATH 없이 패키지 검사 실행 | 독립 검사 도구 정상 실행 및 빈 검사 결과 파일 생성 | [test_package_checker_runs_standalone_without_pythonpath](../tests/test_publication_privacy.py#L76) |

최신 공개 경계 후속 검증: 전체 311 passed, upstream 경고 1건. 위 233개 검증
기록은 이전 단계이며, 이번 변경에서 78개 경로·설치·패키지 회귀 사례를 추가했다.
