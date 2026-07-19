# NyaNya Agent 사용자 수용 테스트

이 문서는 소스 전체를 읽지 않고도 핵심 기능이 실제로 동작하는지 확인하기 위한 체크리스트다. 테스트 메시지에는 비밀번호, 토큰, 개인 경로 또는 계정 식별자를 넣지 않는다.

## 공통 판정

- `통과`: 기대 결과가 모두 보이고 오류 메시지가 없다.
- `부분 통과`: 핵심 결과는 보이지만 진행 상태 또는 대시보드 기록이 빠진다.
- `실패`: 응답이 없거나 권한·인증·파일 전송 오류가 발생한다.

## TC-01 로컬 서비스와 대시보드

터미널에서 다음을 실행한다.

```bash
./scripts/nyanya_ctl.sh status-all
./scripts/nyanya_ctl.sh dashboard-health
```

브라우저에서 `http://127.0.0.1:8765/#office`를 연다.

기대 결과:

- Discord bridge, dashboard, memory worker가 `running` 또는 `active`다.
- dashboard health가 `status=ok`다.
- Agent Office 화면과 접근 가능한 상태 목록이 표시된다.

## TC-02 Discord 제어 명령

허용된 Discord 채널에서 차례로 보낸다.

```text
!nyanya status
!nyanya tasks
```

기대 결과:

- `status`가 bridge와 backend 구성을 요약한다.
- `tasks`가 현재 사용자의 대기·진행·완료 작업을 보여준다.
- 다른 사용자의 작업이나 비밀 설정값은 노출되지 않는다.

## TC-03 LLM 기본 응답

허용된 Discord 채널에서 다음과 같이 보낸다.

```text
!nyanya 현재 NyaNya Agent가 제공하는 기능을 다섯 줄로 요약해줘.
```

기대 결과:

- 접수 메시지가 먼저 표시된다.
- 오래 걸리면 계획 또는 진행 상태가 중간에 표시된다.
- 마지막에 한국어 결과가 한 번만 표시된다.
- 대시보드의 Tasks 또는 Executions에서 같은 요청을 찾을 수 있다.

## TC-04 Codex 읽기 전용 작업과 진행 조회

허용된 Discord 채널에서 다음과 같이 보낸다.

```text
!nyanya codex README.md와 README.KO.md만 읽고 문서 구조의 차이를 다섯 가지로 정리해줘.
```

작업 중에 다음을 보낸다.

```text
!nyanya tasks
```

기대 결과:

- Codex 작업이 읽기 전용 profile로 시작된다.
- `tasks`에서 대기 또는 진행 상태를 확인할 수 있다.
- 작업 완료 후 요약이 표시되고 저장소 파일은 변경되지 않는다.

## TC-05 일반 채널 요청 파일을 자료공유로 전송

관리자가 준비한 테스트 파일을 일반 채널에서 업로드 요청한다.

```text
!nyanya upload docs/private/nyanya_uat_sample.txt
```

기대 결과:

- 일반 채널에는 업로드 결과만 간단히 표시된다.
- 설정된 `자료공유` 채널에 테스트 파일이 정확히 한 번 첨부된다.
- 토큰, 절대 홈 경로 또는 내부 채널 식별자가 메시지에 나타나지 않는다.

## 기록할 결과

| 테스트 | 결과 | 확인 시각 | 메모 |
|---|---|---|---|
| TC-01 | 대기 |  |  |
| TC-02 | 대기 |  |  |
| TC-03 | 대기 |  |  |
| TC-04 | 대기 |  |  |
| TC-05 | 대기 |  |  |
