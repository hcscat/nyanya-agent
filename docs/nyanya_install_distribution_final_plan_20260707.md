# NyaNya Agent 설치/배포 최종 권장안

작성일: 2026-07-07 KST

이 문서는 NyaNya Agent를 npm 중심으로 배포하기 위한 현재 기준의 최종 권장안이다. Homebrew 배포는 npm 설치/배포 안정화 이후 별도 단계로 진행한다.

## 1. 결론

권장 방향은 다음과 같다.

1. 에이전트 본체는 Python으로 유지한다.
2. npm으로 배포되는 설치/실행 CLI 계층은 TypeScript로 전환한다.
3. npm install 자체는 가볍게 유지하고, 실제 초기 구성은 `nyanya setup`에서 수행한다.
4. `nyanya setup`은 Python runtime, dependency, dashboard, Discord bridge, memory worker, LaunchAgent, health check를 한 번에 처리한다.
5. Python, Node.js, Git 같은 system prerequisite는 무단 자동 설치하지 않고 명확히 감지한 뒤 설치 안내를 제공한다.
6. Python dependency는 독립 runtime 환경에 설치한다. npm/curl 설치에서는 `.venv`, 향후 Homebrew에서는 Homebrew virtualenv, PyPI/pipx에서는 pipx 격리를 사용한다.
7. npm 계정과 organization 생성은 사용자가 직접 수행한다. 계정 비밀번호, OTP, token은 repo, 문서, 로그에 기록하지 않는다.

## 2. Python 의존성 자동 설치 계획

현재 npm wrapper는 Node.js에서 `python3 -m nyanya_agent...`를 호출하는 구조다. 이 구조만으로는 `discord.py`, `fastapi`, `uvicorn` 같은 Python optional dependency가 자동 설치되지 않는다.

권장 구현은 다음과 같다.

```text
npm install -g @scope/nyanya-agent
  -> TypeScript로 빌드된 JS CLI 설치

nyanya setup
  -> Python 3.11+ 확인
  -> .venv 생성
  -> pip upgrade
  -> pip install -e ".[bots,dashboard]"
  -> .env 또는 config 생성
  -> dashboard, Discord bridge, memory worker 설정
  -> macOS LaunchAgent 등록 선택
  -> health check 실행
```

`postinstall`에서 전부 처리하지 않는 것이 좋다. 이유는 다음과 같다.

- npm install 도중 사용자 입력을 요구하면 설치 실패 원인을 파악하기 어렵다.
- Discord token, LLM OAuth, API key, workspace 설정은 사용자의 명시적 입력이 필요하다.
- npm의 install script는 보안 정책상 제한되거나 사용자가 비활성화할 수 있다.
- 실패 시 `nyanya setup`, `nyanya doctor`, `nyanya repair`처럼 재실행 가능한 명령이 더 관리하기 쉽다.

따라서 npm package에는 다음 기능을 넣는다.

```text
nyanya
  최초 실행 시 setup 상태 확인
  setup 미완료면 "nyanya setup" 안내

nyanya setup
  전체 초기 설치/설정 수행

nyanya doctor
  설치 상태, dependency, 서비스, SNS bridge 권한 점검

nyanya repair
  누락된 dependency, 깨진 .venv, LaunchAgent 문제 복구

nyanya service status
nyanya service start
nyanya service stop
nyanya service restart
  agent, dashboard, Discord bridge, memory worker 제어
```

## 3. 설치 시 함께 구성해야 하는 범위

`nyanya setup`이 한 번에 처리해야 하는 범위는 다음이다.

| 단계 | 처리 내용 | 자동화 수준 |
|---|---|---|
| 사전 점검 | OS, Python, Node.js, Git, port, write permission 확인 | 자동 |
| Python runtime | `.venv` 생성, pip upgrade, dependency 설치 | 자동 |
| 기본 디렉터리 | config, data, logs, run, downloads 생성 | 자동 |
| 보안 권한 | `.env`, DB, private config에 `0600` 또는 owner-only 권한 적용 | 자동 |
| Dashboard | FastAPI/uvicorn dependency 확인, local URL 출력 | 자동 |
| Discord bridge | token 입력, channel allowlist, upload channel, permission check | 반자동 |
| Telegram/Slack | 구조만 확장 가능하게 두고 초기 우선순위는 Discord | 선택 |
| LLM backend | Codex CLI, Claude Code, Antigravity/Gemini CLI, OpenAI API key 방식 선택 | 반자동 |
| LaunchAgent | macOS 자동 시작 등록 여부 선택 | 선택 |
| Health check | process, import, DB, dashboard, Discord 권한 확인 | 자동 |

## 4. Python, Node.js, Git이 없는 경우

권장 정책은 "무단 자동 설치 금지, 명확한 감지와 안내"다.

### 4.1 Node.js가 없는 경우

npm 배포 방식에서는 Node.js와 npm이 이미 전제 조건이다. 따라서 npm 설치 경로에서는 Node.js가 없을 수 없다. curl 설치 경로에서는 Node.js가 없어도 Python 기반 설치는 가능하게 만들 수 있다.

권장 처리:

```text
npm 설치 경로:
  Node.js/npm 존재를 전제로 함

curl 설치 경로:
  Node.js가 없으면 npm wrapper 기능은 비활성
  Python agent와 LaunchAgent 설치는 계속 가능
  Node.js 설치 안내만 출력
```

### 4.2 Python이 없는 경우

Python은 에이전트 본체 실행에 필수다. 설치 스크립트가 Python 자체를 몰래 설치하면 권한, 경로, Homebrew 의존성, 기업 보안 정책 문제가 생길 수 있다.

권장 처리:

```text
Python 3.11+ 없음:
  설치 중단
  macOS: brew install python@3.12 안내
  Windows: winget 또는 python.org 설치 안내
  Linux: distro별 apt/dnf/pacman 안내
  설치 완료 후 nyanya setup 재실행 안내
```

Homebrew 배포 단계에서는 formula가 `python@3.12`를 dependency로 선언할 수 있으므로 Homebrew가 Python 설치를 담당한다.

### 4.3 Git이 없는 경우

Git은 설치 경로에 따라 필수 여부가 다르다.

```text
npm registry 설치:
  Git 불필요

GitHub URL npm 설치:
  Git 필요할 수 있음

curl installer:
  Git clone 방식이면 Git 필요
  GitHub tarball download 방식이면 Git 불필요
```

권장 개선:

1. curl installer는 Git이 있으면 `git clone`을 사용한다.
2. Git이 없으면 GitHub tarball을 `curl`로 다운로드하는 fallback을 제공한다.
3. Git 자체는 자동 설치하지 않고 설치 안내만 제공한다.

## 5. `.venv` 사용은 필수인가?

개념적으로 반드시 `.venv`여야 하는 것은 아니다. 그러나 npm/curl 설치에서는 Python dependency 격리를 위해 독립 runtime 환경이 사실상 필수다.

선택지는 다음과 같다.

| 설치 방식 | 권장 Python 격리 방식 | 이유 |
|---|---|---|
| npm | package-managed `.venv` | Node wrapper가 예측 가능한 Python을 호출해야 함 |
| curl | install dir 내부 `.venv` | 사용자의 global Python 오염 방지 |
| Homebrew | Homebrew `virtualenv_install_with_resources` | Homebrew Python formula 관례 |
| pipx/PyPI | pipx venv | Python CLI 배포 관례 |
| 개발 checkout | repo-local `.venv` | 개발/테스트 편의 |

따라서 답은 다음이다.

```text
반드시 이름이 .venv일 필요는 없다.
하지만 격리된 Python runtime은 필수로 보는 것이 맞다.
```

## 6. JavaScript CLI와 TypeScript CLI의 의미

Node.js는 기본적으로 JavaScript를 실행한다. TypeScript는 배포 전에 JavaScript로 compile해야 한다.

따라서 "TypeScript CLI"의 실제 의미는 다음이다.

```text
개발 소스:
  TypeScript

npm에 포함되는 실행 파일:
  compiled JavaScript

사용자 실행:
  node dist/bin/nyanya.js
```

즉, 사용자는 JS CLI를 실행하지만, 우리는 TypeScript로 CLI를 개발한다. 관리 관점에서는 TypeScript CLI라고 부를 수 있으나, npm package 안의 bin entry는 최종적으로 `.js` 파일이어야 가장 호환성이 좋다.

권장 구조:

```text
package/
  src/
    bin/
      nyanya.ts
    runtime/
      python.ts
      venv.ts
      process.ts
      platform.ts
    setup/
      setup.ts
      doctor.ts
      repair.ts
      service.ts
  dist/
    bin/
      nyanya.js
    runtime/
    setup/

bin/
  nyanya.js
  nyanya-agent.js
  nyanya-discord.js
```

`bin/*.js`는 `dist`를 호출하는 얇은 compatibility wrapper로 두거나, `package.json`의 `bin`을 직접 `dist/bin/*.js`로 연결한다.

## 7. TypeScript 전환 계획

단계별 전환안은 다음이다.

### 7.1 1단계: 공통 Node runner 도입

현재 `bin/*.js`가 중복된 Python 실행 코드를 갖고 있다. 먼저 공통 runner를 만든다.

```text
bin/lib/run-python.js
bin/nyanya.js
bin/nyanya-agent.js
bin/nyanya-discord.js
```

### 7.2 2단계: TypeScript build 체계 추가

```text
package.json
  devDependencies:
    typescript
    @types/node

  scripts:
    build
    typecheck
    prepack
    check

tsconfig.json
```

### 7.3 3단계: setup/doctor/repair 구현

TypeScript에서 설치 상태 모델을 명시적으로 관리한다.

```ts
type PythonStatus = {
  found: boolean;
  version?: string;
  path?: string;
  satisfies: boolean;
};

type RuntimeStatus = {
  projectRoot: string;
  venvPath: string;
  python: PythonStatus;
  dependenciesInstalled: boolean;
  dashboardConfigured: boolean;
  discordConfigured: boolean;
};
```

### 7.4 4단계: 기존 Python CLI와 역할 분리

```text
TypeScript:
  설치, setup, doctor, service wrapper, cross-platform UX

Python:
  agent core, bridge, dashboard, memory worker, task queue
```

## 8. npm 계정과 organization 생성 계획

제공된 목표 기준:

```text
npm username: hcscat
npm organization: hcscat-dev
```

비밀번호와 email은 repo, 문서, 로그, CI 설정에 저장하지 않는다. 계정 생성, email verification, 2FA 설정은 사용자가 npm 웹사이트에서 직접 수행한다.

중요한 이름 차이가 있다.

```text
@hcscat/nyanya-agent
  npm user scope 또는 hcscat organization scope

@hcscat-dev/nyanya-agent
  hcscat-dev organization scope
```

현재 `package.json`은 사용자 scope 배포 기준에 맞춰 아래 이름을 사용한다.

```json
{
  "name": "@hcscat/nyanya-agent"
}
```

최신 선택:

```text
현재 npm 배포:
  @hcscat/nyanya-agent

나중에 organization 권한/2FA 정책을 정리한 뒤 검토:
  @hcscat-dev/nyanya-agent
```

이번 배포는 organization scope가 아니라 사용자 scope인 `@hcscat/nyanya-agent`로 진행한다.

### 8.1 사용자가 직접 해야 하는 작업

1. npm 계정 생성 또는 로그인
2. email verification
3. 2FA 설정
4. `hcscat-dev` organization 생성
5. 필요한 경우 automation token 또는 granular access token 생성
6. CI publish를 쓸 경우 GitHub Actions secret에 token 등록

### 8.2 Codex가 도울 수 있는 작업

1. `package.json` package name 변경
2. publish 전 `npm pack --dry-run` 검증
3. 민감정보 포함 여부 검사
4. GitHub Actions publish workflow 작성
5. `npm publish --dry-run` 실행
6. 사용자가 npm login을 마친 뒤 publish 명령 실행 보조

### 8.3 npm publish 절차

공식 npm 문서 기준으로 scoped public package 최초 공개 배포는 다음 명령을 사용한다.

```bash
npm publish --access public
```

direct publishing에는 2FA가 활성화된 계정 또는 2FA bypass가 허용된 granular access token이 필요하다.

참고:

- https://docs.npmjs.com/creating-an-organization/
- https://docs.npmjs.com/about-organization-scopes-and-packages/
- https://docs.npmjs.com/creating-and-publishing-scoped-public-packages/
- https://docs.npmjs.com/creating-and-publishing-an-organization-scoped-package/

## 9. Homebrew는 나중에 진행

현재 단계에서는 Homebrew를 보류한다.

이유:

1. npm CLI와 Python bootstrap 설계가 먼저 확정되어야 한다.
2. Homebrew formula는 release tarball, checksum, Python resources 고정이 필요하다.
3. Homebrew에서 service를 `brew services`로 관리할지 자체 LaunchAgent로 관리할지 결정이 필요하다.

나중에 진행할 때는 전용 tap repository를 만든다.

```text
github.com/hcscat/homebrew-tap
  Formula/
    nyanya-agent.rb
```

사용자 설치 UX:

```bash
brew install hcscat/tap/nyanya-agent
nyanya setup
```

참고:

- https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap
- https://docs.brew.sh/Formula-Cookbook
- https://docs.brew.sh/Homebrew-and-Python

## 10. 최종 구현 순서

권장 작업 순서는 다음이다.

1. npm package name을 `@hcscat/nyanya-agent`로 확정
2. 기존 `bin/*.js` 중복 제거
3. TypeScript build 체계 추가
4. TypeScript 기반 `nyanya setup` skeleton 구현
5. Python version/dependency check 구현
6. `.venv` 생성과 `pip install -e ".[bots,dashboard]"` 구현
7. `nyanya doctor` 구현
8. Dashboard health check 구현
9. Discord bridge 설정/권한 check 구현
10. LaunchAgent 등록/해제/상태 확인을 `nyanya service ...`로 통합
11. `npm pack --dry-run`과 release secret scan을 CI에 연결
12. npm organization publish 준비
13. npm publish dry-run
14. npm public publish
15. Homebrew tap은 이후 별도 phase로 진행

## 11. 보안 기준

설치/배포 코드에서 절대 하지 말아야 할 것:

- npm password 저장
- Discord bot token 출력
- `.env` raw dump
- `config/user_workspaces.json` package 포함
- `data/`, `logs/`, `docs/private/` package 포함
- token 값을 health check 결과에 표시
- CI log에 API key, OAuth token, npm token 출력

권장 출력 방식:

```text
Discord token: configured
Discord file-share channel: configured
Dashboard DB: present
Python dependencies: installed
```

값 자체가 아니라 설정 여부와 검증 결과만 출력한다.

## 12. 최종 권장안

현재 시점의 최종 권장안은 다음이다.

```text
배포 우선순위:
  1. npm
  2. curl installer
  3. Homebrew

CLI 구현:
  TypeScript source -> compiled JavaScript bin

Python dependency:
  setup 단계에서 격리 runtime에 자동 설치

초기 설정:
  nyanya setup 하나로 agent, dashboard, Discord bridge, memory worker까지 구성

사전 조건:
  Python/Node/Git은 무단 설치하지 않음
  감지 후 명확한 설치 안내
  curl installer는 Git 없는 경우 tarball fallback 제공

npm scope:
  현재 배포는 @hcscat/nyanya-agent 사용

Homebrew:
  npm 안정화 후 전용 tap repository로 진행
```
