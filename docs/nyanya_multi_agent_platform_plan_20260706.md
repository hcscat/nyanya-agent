# NyaNya Agent 설치/멀티에이전트 플랫폼 개발 계획

작성일: 2026-07-06 KST

## 1. 결론 요약

현재 NyaNya Agent는 `Discord bridge + 로컬 LLM/Codex 위임 + 작업 큐 + SQLite 대시보드 + memory worker` 구조를 이미 갖고 있다. 그러나 사용자가 요구한 "중앙 NyaNya Agent가 여러 서브 에이전트를 생성, 관리, 승인, 보고하는 플랫폼"으로 가려면 단순히 Discord bridge를 복제하는 수준으로는 부족하다.

권장 방향은 다음과 같다.

1. 설치는 `npm`과 `Homebrew tap`을 우선 지원한다.
2. Python CLI로서의 정식 배포 경로는 `pipx/PyPI`도 준비한다.
3. 여러 Discord/Telegram 봇은 "각각 별도 토큰을 가진 agent profile"로 관리한다.
4. Discord는 에이전트 간 대화의 화면/로그 채널로 사용하되, 실제 제어는 중앙 orchestrator와 DB/event bus가 담당한다.
5. 파일 추가/수정/삭제는 서브 에이전트가 직접 실행하지 않고, 계획 제출 -> 중앙 NyaNya 검토 -> 사용자 승인 또는 정책 승인 -> 실행 위임 구조로 처리한다.
6. 반복 학습은 모델 자체 학습이 아니라 승인/거절 사례, 작업 성공/실패, 프로젝트 규칙, 선호 도구를 memory/policy store에 축적하는 방식으로 구현한다.

최종 목표는 `NyaNya Control Plane`이다. 즉, NyaNya는 하나의 봇이 아니라 여러 SNS connector, 여러 sub-agent, 작업 큐, 승인 정책, 기억, 대시보드를 통합 관리하는 로컬 운영 플랫폼이 된다.

## 2. 현재 NyaNya Agent 상태

현재 저장소 기준으로 확인한 구성은 다음과 같다.

| 영역 | 현재 상태 | 보강 필요 |
|---|---|---|
| CLI | `nyanya`, `nyanyactl`, `nyanya-discord`, `nyanya-dashboard`, `nyanya-memory-worker` entry point 존재 | 설치 후 bootstrap 명령과 프로파일 생성 명령 필요 |
| npm | `@hcscat/nyanya-agent` package wrapper 존재 | Python venv bootstrap, 서비스 설치, postinstall 안내, release workflow 필요 |
| Homebrew | formula/tap 없음 | `homebrew-nyanya` tap과 Python formula 필요 |
| Discord | 단일 bot token 기반 bridge | agent profile별 token/설정/권한 분리 필요 |
| Telegram | bridge 구현 존재 | multi-profile 실행 관리 필요 |
| Dashboard | FastAPI + SQLite 기반 로컬 대시보드 존재 | agent 목록, connector 상태, 승인 큐, 실행 그래프, 프로젝트별 작업 현황 추가 필요 |
| Memory | baseline memory와 SQLite dynamic memory 존재 | agent별 memory namespace, 승인/거절 사례 기반 policy memory 필요 |
| 작업 큐 | 사용자별 queue와 progress heartbeat 존재 | agent 간 task graph, central scheduler, task ownership, cancellation propagation 필요 |
| 승인 정책 | 위험 작업 plan/approval 개념 존재 | sub-agent 계획 검토, diff 검토, 승인 이력 학습 필요 |

현재 코드에서 Discord bridge는 봇 메시지를 무시한다. 이는 무한 응답 루프 방지를 위한 안전한 기본값이다. 따라서 A/B/C 에이전트가 서로 대화하려면 "허용된 peer bot 메시지만, 전용 채널에서, 명시적 mention/prefix 또는 orchestrator가 부여한 turn token이 있을 때만 처리"하도록 수정해야 한다.

## 3. 공식 문서 조사 요약

### 3.1 npm 배포

npm 공식 문서는 scoped public package를 npm registry에 공개할 수 있고, scoped package는 기본적으로 private visibility이므로 공개하려면 `npm publish --access public`을 사용해야 한다고 설명한다. 또한 publish 전에 민감정보, private key, password, PII 등을 제거하라고 권고한다.

출처: [npm: Creating and publishing scoped public packages](https://docs.npmjs.com/creating-and-publishing-scoped-public-packages/)

NyaNya에는 이미 `package.json`과 `bin/*.js` wrapper가 있다. 따라서 npm은 가장 빠른 설치 UX를 만들 수 있다.

권장 사용자 경험:

```bash
npm install -g @hcscat/nyanya-agent
nyanya-agent doctor
nyanya-agent init
nyanyactl install
nyanyactl start-all
```

단, NyaNya의 본체는 Python이므로 npm package는 다음 중 하나를 선택해야 한다.

| 방식 | 장점 | 단점 | 권장 |
|---|---|---|---|
| 현재처럼 source 포함 + `PYTHONPATH` 실행 | 빠름, 단순 | Python 의존성 설치가 사용자 책임 | 단기 가능 |
| npm wrapper가 첫 실행 시 `.venv` 생성 | 설치 UX 좋음 | postinstall/first-run 실패 처리 필요 | 1차 목표 |
| npm wrapper가 PyPI package를 `pipx`로 설치 | Python CLI와 npm wrapper 분리 가능 | `pipx` 의존 | 2차 목표 |

### 3.2 Homebrew 배포

Homebrew 공식 문서는 tap을 외부 formula/cask 저장소로 설명하며, GitHub에 둘 경우 repository 이름을 `homebrew-`로 시작하는 것을 권장한다. Python formula 작성에서는 Python application과 library를 구분하고, Python application dependency는 resource stanza로 고정할 수 있으며 `brew update-python-resources` 자동화가 가능하다.

출처:

- [Homebrew: How to Create and Maintain a Tap](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
- [Homebrew: Formula Cookbook](https://docs.brew.sh/Formula-Cookbook)
- [Homebrew: Python for Formula Authors](https://docs.brew.sh/Python-for-Formula-Authors)

권장 사용자 경험:

```bash
brew tap hcscat/nyanya
brew install nyanya-agent
nyanyactl doctor
nyanyactl init
nyanyactl install
nyanyactl start-all
```

Homebrew formula는 macOS 사용자를 위한 가장 자연스러운 설치 경로다. 특히 LaunchAgent 설치와 잘 맞는다. 단, formula는 release tarball URL과 `sha256`을 요구하므로 GitHub release/tag 프로세스가 먼저 안정화되어야 한다.

### 3.3 멀티에이전트 패턴

LangChain 문서는 multi-agent가 복잡한 workflow를 처리하기 위해 specialized component를 조정한다고 설명한다. 주요 이유는 context 관리, 기능별 독립 개발, 병렬화이며, 단일 agent에 tool이 너무 많아져 선택 품질이 떨어지거나 domain-specific context가 클 때 유용하다고 설명한다.

출처: [LangChain: Multi-agent](https://docs.langchain.com/oss/python/langchain/multi-agent)

LangGraph는 agent orchestration runtime으로 durable execution, streaming, human-in-the-loop, persistence에 초점을 둔다. persistence 문서는 checkpointer가 thread의 graph state를 저장하고, store가 long-term memory를 저장한다고 설명한다.

출처:

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangChain human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)

OpenAI Agents SDK는 agent loop, agents-as-tools/handoffs, guardrails, function tools, MCP integration, sessions, human-in-the-loop, tracing을 제공한다.

출처: [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)

AutoGen은 conversational single/multi-agent application을 위한 framework와 event-driven core를 제공한다. 특히 Core는 business process workflow, multi-agent collaboration research, distributed agents에 초점을 둔다.

출처: [Microsoft AutoGen](https://microsoft.github.io/autogen/stable/index.html)

### 3.4 Discord 제약

Discord 공식 문서는 message content가 privileged intent이며, message object의 `content`, `embeds`, `attachments`, `components` 등에 접근하려면 Message Content Intent가 필요하다고 설명한다. 또 Discord 권한은 guild-level role과 channel overwrite로 부여/제한된다.

출처:

- [Discord: Privileged Intents](https://support-dev.discord.com/hc/en-us/articles/6207308062871-What-are-Privileged-Intents)
- [Discord: Gateway](https://docs.discord.com/developers/events/gateway)
- [Discord: Permissions](https://docs.discord.com/developers/topics/permissions)

따라서 여러 에이전트 봇을 Discord에 붙일 때는 각 bot application에 필요한 intent를 켜고, 전용 채널의 view/send/read history/attach files 권한을 명시적으로 부여해야 한다.

## 4. 목표 아키텍처

권장 구조는 Discord bot 여러 개를 단순히 켜는 구조가 아니다. 중앙 NyaNya가 control plane이 되고, 서브 에이전트는 profile/runtime으로 관리되어야 한다.

```text
User
  |
  | Discord / Telegram / Dashboard / CLI
  v
NyaNya Control Plane
  |
  +-- Agent Registry
  |     +-- Agent A: planner, token A, memory A, tools A
  |     +-- Agent B: reviewer, token B, memory B, tools B
  |     +-- Agent C: worker, token C, memory C, tools C
  |
  +-- Connector Manager
  |     +-- Discord client A
  |     +-- Discord client B
  |     +-- Discord client C
  |     +-- Telegram clients
  |
  +-- Orchestrator / Scheduler
  |     +-- task graph
  |     +-- turn control
  |     +-- loop guard
  |     +-- timeout/cost limit
  |
  +-- Approval Engine
  |     +-- sub-agent plan review
  |     +-- risk scoring
  |     +-- user approval queue
  |     +-- learned approval examples
  |
  +-- Memory / Policy Store
  |     +-- agent-specific memory
  |     +-- project memory
  |     +-- approval/rejection memory
  |
  +-- Dashboard API/UI
        +-- running agents
        +-- current projects
        +-- pending approvals
        +-- task results
        +-- audit log
```

핵심 원칙:

1. Discord는 transport이자 관찰 화면이다.
2. agent 간 실제 상태 전달은 DB/event bus를 통해 한다.
3. 중앙 orchestrator가 다음 발화권과 작업 권한을 결정한다.
4. 서브 에이전트는 직접 side effect를 실행하지 않고 계획/패치를 제출한다.
5. 중앙 NyaNya와 사용자가 승인해야 파일 변경이 실행된다.

## 5. 요구사항별 구현 계획

| 요구사항 | 구현 방식 | 우선순위 |
|---|---|---|
| 1. 쉬운 설치 | npm global install, Homebrew tap, pipx/PyPI 준비 | P0 |
| 2. 여러 서브 에이전트 + SNS token | `agent_profiles` 테이블과 profile별 env/token/connector 설정 | P0 |
| 3. Discord A/B/C 의사소통 | 전용 channel + peer bot allowlist + orchestrator turn token | P1 |
| 4. 중앙 관리 | `NyaNya Control Plane` 프로세스와 dashboard 관리 API | P0 |
| 5. 대시보드/관리 플랫폼 | 현재 FastAPI dashboard 확장 | P0 |
| 6. NyaNya를 통한 sub-agent 생성 | `nyanyactl agent create`, dashboard create form | P1 |
| 7. 중앙/서브 에이전트별 작업 요청 | `nyanya task create --agent`, Discord mention routing | P1 |
| 8. 결과는 NyaNya가 보고 | 모든 sub-agent result를 중앙 report aggregator가 요약/보고 | P1 |
| 9. 파일 변경 승인 | sub-agent plan/diff -> central review -> approval -> execution | P0 |
| 10. 승인 가능 작업 학습 | approval/rejection 사례를 policy memory로 저장, 승인 추천만 자동화 | P2 |
| 11. 기술 스택 정리 | 아래 section 6 참고 | P0 |
| 12. MD/HTML 보고서와 Discord 공유 | 본 문서와 HTML 산출물 생성 후 자료공유 업로드 | 완료 대상 |

## 6. 권장 기술 스택

### 6.1 유지할 현재 기술

| 기술 | 역할 | 판단 |
|---|---|---|
| Python 3.11+ | core runtime | 유지 |
| discord.py | Discord connector | 유지 |
| FastAPI | dashboard/API | 유지 |
| SQLite | 개인/로컬 운영 DB | 유지, 추후 Postgres 선택 가능 |
| LaunchAgent | macOS 자동실행 | 유지 |
| Codex CLI 위임 | 코드/파일 작업 | 유지 |
| pytest/ruff | 품질 검증 | 강화 |

### 6.2 추가할 핵심 기술

| 기술 | 사용 목적 | 도입 시점 |
|---|---|---|
| Pydantic model | agent profile, task, approval schema | 즉시 |
| APScheduler 또는 system scheduler | 주기 작업이 NyaNya 내부 관리 대상이 될 때 | 선택 |
| asyncio task supervisor | 여러 connector와 sub-agent runtime 관리 | 즉시 |
| SQLite migration 도구 | schema 변경 추적 | P0 |
| Server-Sent Events 또는 WebSocket | dashboard 실시간 상태 | P1 |
| LangGraph | durable workflow, human-in-the-loop, graph state | P1/P2 |
| OpenAI Agents SDK | OpenAI 기반 agent/handoff/guardrail 실험 | 선택 |
| AutoGen | conversational multi-agent prototype 비교 | 선택 |
| pipx/PyPI | Python CLI 표준 설치 | P1 |
| GitHub Actions | npm/brew/PyPI release 자동화 | P1 |

### 6.3 LangGraph 도입 판단

NyaNya가 단순 bridge라면 LangGraph는 과하다. 하지만 다음 요구사항을 보면 도입 가치가 있다.

- 여러 agent가 순차/병렬로 작업
- 중간에 사용자 승인으로 멈췄다가 재개
- 작업 상태가 재시작 후에도 유지
- agent별 기억과 thread 상태를 분리
- dashboard에서 task graph를 보여줌

따라서 P1까지는 자체 SQLite task graph로 구현하고, P2에서 LangGraph를 도입 또는 비교하는 방식이 현실적이다. 처음부터 LangGraph로 전면 재작성하면 현재 동작 중인 Discord/Codex 운영 흐름을 깨뜨릴 위험이 있다.

## 7. 데이터 모델 초안

### 7.1 Agent Profile

```text
agent_profiles
- id
- name
- role
- status
- connector_type
- connector_token_ref
- discord_application_id
- discord_bot_user_id
- allowed_channel_ids
- prefix
- system_prompt_path
- memory_namespace
- workspace_roots
- tool_permissions
- created_at
- updated_at
```

### 7.2 Task

```text
agent_tasks
- id
- parent_task_id
- project_id
- requested_by
- assigned_agent_id
- status
- mode
- prompt
- plan
- result_summary
- requires_approval
- approval_id
- created_at
- started_at
- completed_at
```

### 7.3 Agent Message / Event

```text
agent_events
- id
- task_id
- source_agent_id
- target_agent_id
- channel
- event_type
- payload_json
- discord_message_id
- created_at
```

### 7.4 Approval

```text
approvals
- id
- task_id
- agent_id
- action_type
- risk_level
- plan_text
- diff_summary
- requested_paths
- decision
- decided_by
- feedback
- created_at
- decided_at
```

### 7.5 Policy Memory

```text
policy_memories
- id
- scope
- agent_id
- project_id
- pattern
- decision
- rationale
- confidence
- status
- created_from_approval_id
- created_at
```

## 8. 서브 에이전트 생성 UX

### CLI

```bash
nyanyactl agent create planner \
  --role planner \
  --connector discord \
  --prefix '!planner' \
  --token-ref keychain:nyanya/planner-discord-token \
  --memory prompts/agents/planner_memory.md

nyanyactl agent start planner
nyanyactl agent status planner
nyanyactl agent stop planner
```

### Dashboard

필수 화면:

1. Agents
   - agent 생성/수정/중지/재시작
   - token 설정 상태 확인
   - Discord 연결 상태 확인

2. Connectors
   - Discord/Telegram token reference
   - channel allowlist
   - message content intent 필요 여부
   - permission check

3. Tasks
   - 중앙 NyaNya 작업
   - sub-agent 작업
   - pending/running/queued/completed/failed

4. Approvals
   - 파일 변경 계획
   - diff
   - 위험도
   - 승인/거절/수정 요청

5. Memory
   - agent별 기억
   - 프로젝트별 기억
   - 승인 정책 기억

## 9. A/B/C Discord 에이전트 대화 설계

### 나쁜 방식

```text
A 봇이 메시지 작성
B 봇이 그 메시지에 자동 반응
C 봇이 B 메시지에 자동 반응
A 봇이 C 메시지에 자동 반응
...
```

이 방식은 무한 루프, 비용 폭증, Discord rate limit, 같은 작업 중복 실행이 발생한다.

### 권장 방식

```text
사용자: "이 프로젝트 분석해줘"
NyaNya Control Plane:
  1. task 생성
  2. Planner A에게 계획 요청
  3. Reviewer B에게 계획 검토 요청
  4. Worker C에게 실행 요청
  5. Reviewer B에게 결과 검토 요청
  6. NyaNya가 사용자에게 최종 보고

Discord #agent-lab:
  - 각 단계 로그 표시
  - agent 간 의견 표시
  - approval 요청 표시
```

agent 간 메시지에는 반드시 metadata가 필요하다.

```text
conversation_id
task_id
turn_id
source_agent
target_agent
allowed_next_agents
max_turns
expires_at
requires_human_approval
```

## 10. 파일 변경 승인 구조

서브 에이전트가 파일을 수정해야 할 때는 다음 절차를 따른다.

1. 서브 에이전트가 plan 제출
2. 중앙 NyaNya가 risk classifier 실행
3. 수정 대상 path가 allowed/trusted root 안인지 확인
4. 필요하면 Codex에게 read-only review 위임
5. dashboard approval queue에 등록
6. 사용자가 승인/거절/수정 요청
7. 승인 시에만 Codex write 또는 제한된 tool executor 실행
8. 실행 결과와 diff를 중앙 NyaNya가 최종 보고

자동 승인은 처음에는 금지한다. 반복 사례가 쌓이면 다음처럼 낮은 위험 작업만 추천 자동 승인으로 바꿀 수 있다.

| 작업 | 초기 정책 | 학습 후 가능 정책 |
|---|---|---|
| 문서 초안 생성 | 승인 필요 | 프로젝트 내부 docs에 한해 자동 승인 가능 |
| README 문구 수정 | 승인 필요 | 작은 diff일 때 추천 승인 |
| 테스트 실행 | 자동 허용 | 유지 |
| 소스 코드 수정 | 승인 필요 | 유지 |
| 파일 삭제 | 강한 승인 필요 | 유지 |
| 환경변수/토큰 파일 수정 | 금지 또는 강한 승인 | 유지 |
| 시스템 설정 변경 | 강한 승인 | 유지 |

## 11. 설치 배포 구현 로드맵

### Phase 0: 현재 npm wrapper 정리

목표:

- `npm pack --dry-run`으로 배포 파일 검증
- `.npmignore` 또는 `files` whitelist 검증
- `.env`, `data`, `logs`, `docs/private` 제외 확인
- `nyanya-agent doctor` 명령 추가

완료 기준:

```bash
npm pack --dry-run
npm install -g ./hcscat-nyanya-agent-0.1.0.tgz
nyanya-agent --check
nyanyactl status-all
```

### Phase 1: npm 설치 UX 완성

목표:

- first-run bootstrap 구현
- Python venv 자동 생성
- optional dependency 설치: `bots`, `dashboard`
- `nyanya-agent init`으로 `.env` scaffold
- token은 절대 npm package에 포함하지 않음

권장 명령:

```bash
npm install -g @hcscat/nyanya-agent
nyanya-agent init
nyanya-agent doctor
nyanyactl install
nyanyactl start-all
```

### Phase 2: Homebrew tap

목표:

- `hcscat/homebrew-nyanya` 저장소 생성
- `Formula/nyanya-agent.rb` 작성
- GitHub release tarball 기반 URL/SHA256 고정
- Python dependencies는 Homebrew resource stanza로 고정
- `brew test nyanya-agent`에서 `nyanya --check` 또는 `nyanyactl --help` 실행

권장 명령:

```bash
brew tap hcscat/nyanya
brew install nyanya-agent
nyanyactl doctor
```

### Phase 3: PyPI/pipx

목표:

- `pyproject.toml` metadata 보강
- `python -m build`
- `twine check`
- PyPI publish
- `pipx install 'nyanya-agent[bots,dashboard]'` 지원

이 경로는 Python 사용자에게 가장 자연스럽고, Homebrew formula dependency 관리에도 도움이 된다.

## 12. 멀티에이전트 구현 로드맵

### Phase A: Agent Profile Registry

- `agent_profiles` SQLite table 추가
- profile별 prompt/memory/workspace/tool permission 저장
- token은 DB에 저장하지 않고 keychain/env reference만 저장
- `nyanyactl agent create/list/show/delete` 추가

### Phase B: Multi Connector Runtime

- `ConnectorManager` 추가
- 하나의 process에서 여러 Discord client를 띄울지, profile별 process로 분리할지 결정
- 초기에는 profile별 process가 안전하다.
- label 예시:
  - `com.hcs.nyanya.agent.planner`
  - `com.hcs.nyanya.agent.reviewer`
  - `com.hcs.nyanya.agent.worker`

### Phase C: Peer Bot Allowlist

- 현재 `message.author.bot` 무조건 ignore 로직을 수정
- 허용 조건:
  - 자기 자신 메시지는 ignore
  - `NYANYA_DISCORD_PEER_BOT_IDS`에 포함
  - 전용 agent channel
  - mention/prefix/turn token 중 하나 존재
  - max turn 초과 아님

### Phase D: Central Orchestrator

- task graph table 추가
- planner/reviewer/worker 역할 정의
- agent 간 메시지는 Discord message만이 아니라 DB event로 기록
- Discord에는 visibility log를 출력

### Phase E: Approval Engine

- sub-agent가 side effect plan 제출
- 중앙 NyaNya가 risk classifier와 path policy 적용
- dashboard approval queue에 표시
- 승인 시 실행
- 거절/수정 요청은 sub-agent memory에 feedback으로 축적

### Phase F: Memory/Policy Learning

- agent별 memory namespace
- approval/rejection examples
- project-specific rules
- retrieval query에 role, project, task type을 포함
- 자동 승인은 낮은 위험 작업부터 단계적으로 적용

## 13. 보안/운영 주의사항

1. token은 Git, npm package, Homebrew formula, HTML 보고서에 포함하지 않는다.
2. Discord bot token은 profile별로 분리한다.
3. 같은 bot token으로 여러 process를 띄우지 않는다.
4. peer bot message 처리는 allowlist 기반으로만 허용한다.
5. 파일 변경은 sub-agent가 직접 실행하지 않는다.
6. 삭제/이동/권한 변경/환경파일 수정은 강한 승인 대상으로 유지한다.
7. dashboard를 외부 공개하려면 인증과 HTTPS reverse proxy가 필요하다.
8. agent-to-agent 대화는 반드시 max turns, timeout, budget을 가져야 한다.
9. Codex write delegation은 workspace root와 sandbox 정책을 확인해야 한다.
10. 모든 승인은 audit log로 남긴다.

## 14. 우선 구현 순서

현실적인 우선순위는 다음이다.

1. `nyanyactl doctor/init` 추가
2. npm package 배포 파일 검증과 first-run bootstrap
3. Homebrew tap/release 준비
4. `agent_profiles` schema와 CLI 추가
5. profile별 Discord bridge 실행
6. dashboard에 Agents/Connectors/Tasks/Approvals 화면 추가
7. peer bot allowlist와 agent lab channel 구현
8. 중앙 orchestrator task graph 구현
9. sub-agent plan approval flow 구현
10. agent별 memory namespace와 approval learning 구현
11. LangGraph/OpenAI Agents SDK/AutoGen 비교 prototype
12. 안정화 후 배포 자동화

## 15. 권장 MVP 범위

첫 MVP는 다음까지만 잡는 것이 적절하다.

```text
설치:
- npm global install
- Homebrew tap 초안
- nyanyactl doctor/init/start-all

멀티에이전트:
- agent profile 3개 생성
- profile별 Discord token 연결
- 전용 Discord 채널에서 중앙 orchestrator가 A/B/C에게 순서대로 작업 요청
- agent 간 메시지는 DB에 기록하고 Discord에 표시
- 파일 변경은 approval queue에 등록만 하고 자동 실행 금지

대시보드:
- agent 상태
- connector 상태
- 현재 task
- approval queue
- 결과 보고서
```

이 MVP가 완료되면 사용자는 "NyaNya에게 sub-agent를 만들고, Discord에 붙이고, 각 agent에게 역할별 작업을 맡기고, 중앙 NyaNya가 결과를 보고하는 구조"를 실제로 확인할 수 있다.

## 16. 최종 판단

이 기능은 가능하다. 다만 핵심은 "Discord 봇끼리 그냥 대화하게 만들기"가 아니라 "중앙 NyaNya가 agent runtime과 승인 정책을 통제하는 구조"를 만드는 것이다.

설치 배포는 npm이 가장 빠른 진입점이고, macOS 운영 안정성은 Homebrew + LaunchAgent가 좋다. Python 프로젝트로서의 정석 배포는 PyPI/pipx까지 준비하는 것이 장기적으로 맞다.

멀티에이전트 구현은 자체 SQLite orchestrator로 시작하고, human-in-the-loop와 durable workflow가 복잡해지는 시점에 LangGraph를 도입하는 접근이 가장 안전하다.
