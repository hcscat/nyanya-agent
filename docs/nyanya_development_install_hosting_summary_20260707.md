# NyaNya Agent 개발 목록, 설치/배포 계획, 외부 접속 호스팅 조사

작성일: 2026-07-07 KST

## 1. 요약 결론

NyaNya Agent를 단기간에 완성형 멀티에이전트 플랫폼으로 만드는 것은 현실적이지 않다. 우선순위를 나누면 다음 순서가 가장 안전하다.

1. 설치/배포 개선
2. 에이전트 프로필 시스템
3. 여러 Discord/Telegram connector 관리
4. 중앙 task/orchestrator
5. dashboard 관리 UI 확장
6. 파일 변경 승인 시스템
7. agent별 memory/policy 학습
8. 외부 접속 구조

외부 접속은 처음부터 모든 것을 클라우드로 옮기기보다, 현재 Mac mini에서 NyaNya를 계속 실행하고 `Cloudflare Tunnel + Cloudflare Access`로 dashboard/API만 안전하게 노출하는 방식이 가장 현실적이다. Discord bot처럼 계속 연결되어야 하는 런타임은 무료 serverless hosting과 잘 맞지 않는다.

## 2. 개발해야 하는 목록

| 순서 | 개발 항목 | 핵심 산출물 | 이유 |
|---:|---|---|---|
| 1 | 설치/배포 개선 | `nyanya init`, `nyanya doctor`, npm, Homebrew, pipx/PyPI 계획 | 사용자가 쉽게 설치/업데이트/복구할 수 있어야 함 |
| 2 | 에이전트 프로필 | agent별 이름, 역할, prompt, memory, token reference, workspace, 권한 | A/B/C 서브 에이전트를 분리 운영하기 위함 |
| 3 | 다중 SNS connector | profile별 Discord/Telegram token, prefix, channel allowlist | 여러 봇을 각각 다른 token으로 연결하기 위함 |
| 4 | 중앙 관리 runtime | 모든 agent start/stop/status/restart 관리 | NyaNya가 control plane 역할을 해야 함 |
| 5 | task/orchestrator | planner/reviewer/worker 순서 제어, turn limit, timeout | agent끼리 무한 대화하지 않고 목적 있게 협업해야 함 |
| 6 | dashboard 관리 UI | Agents, Connectors, Tasks, Approvals, Projects, Memory 화면 | 현재 어떤 에이전트와 작업이 돌고 있는지 확인해야 함 |
| 7 | 결과 보고 aggregator | sub-agent 결과 수집, 요약, 최종 보고 | 최종 책임자는 중앙 NyaNya여야 함 |
| 8 | 파일 변경 승인 시스템 | plan 제출, risk scoring, diff 검토, 승인/거절 | sub-agent가 임의로 파일을 바꾸지 못하게 해야 함 |
| 9 | memory/policy 학습 | agent별 memory namespace, 승인/거절 사례 저장 | 반복 작업에서 판단 품질을 개선하기 위함 |
| 10 | 외부 접속 | Cloudflare Tunnel, Access, HTTPS, 인증, 배포 문서 | 집 밖에서도 dashboard/API 접근 가능하게 하기 위함 |
| 11 | 테스트/보안 | token leak check, package whitelist, loop guard, audit log | 공개 배포와 멀티 agent 운영 안정성 확보 |
| 12 | 배포 자동화 | GitHub Actions, release tag, npm publish, Homebrew formula update | 반복 가능한 release 절차 필요 |

## 3. 설치/배포 개선을 먼저 해야 하는 이유

설치/배포가 먼저 안정화되어야 이후 기능 개발의 기준점이 생긴다. 현재 NyaNya는 로컬에서 동작하지만, 설치 절차가 수동에 가깝고 다음 문제가 남아 있다.

- Python 가상환경 생성과 dependency 설치가 사용자의 책임이다.
- npm wrapper는 있지만 Python dependency bootstrap을 완전히 해결하지 않는다.
- Homebrew formula/tap이 없다.
- `doctor`, `init`, `upgrade`, `uninstall`, `repair` 같은 사용자 친화적 명령이 부족하다.
- `.env`, `data`, `logs`, `docs/private` 같은 민감/개인 파일이 package에 들어가지 않는지 release 전에 검증해야 한다.

## 4. 설치/배포 개선 기준

설치 기능을 설계할 때 기준은 다음과 같다.

| 기준 | 설명 | 확인 방법 |
|---|---|---|
| 쉬운 설치 | 사용자가 1~3개 명령으로 설치 가능 | fresh macOS에서 설치 테스트 |
| 안전한 설정 | token, `.env`, DB, 로그가 package/repo에 포함되지 않음 | `npm pack --dry-run`, 보안 grep |
| 복구 가능성 | 서비스 재시작, health check, repair 가능 | `nyanyactl doctor`, `nyanyactl repair` |
| 업데이트 가능성 | npm/brew/pipx 업데이트 경로 존재 | release tag 기준 upgrade test |
| macOS 친화성 | LaunchAgent 자동 실행 지원 | reboot 후 status 확인 |
| Python 의존성 관리 | venv 또는 pipx로 dependencies 격리 | 전역 Python 오염 없음 |
| 문서화 | 설치/설정/토큰/권한/문제 해결 문서 | README와 install guide |
| 배포 재현성 | GitHub release, checksum, package whitelist | CI에서 release artifact 검증 |

## 5. 설치/배포에 필요한 기능

### 5.1 CLI 명령

```bash
nyanya init
nyanya doctor
nyanya config validate
nyanya bootstrap
nyanya update
nyanya uninstall
nyanya version
```

`nyanyactl`에는 운영 명령을 강화한다.

```bash
nyanyactl install
nyanyactl start-all
nyanyactl stop-all
nyanyactl restart-all
nyanyactl status-all
nyanyactl repair
nyanyactl logs
nyanyactl dashboard-open
```

### 5.2 `init`에서 해야 할 일

1. Python 버전 확인
2. `.venv` 생성 여부 확인
3. 필요한 dependency 설치
4. `.env.example`에서 `.env` 생성
5. workspace root 설정
6. dashboard port 충돌 확인
7. Discord/Telegram token 입력은 직접 입력 또는 keychain reference 방식 제공
8. LaunchAgent 설치 여부 질문
9. `doctor` 자동 실행

### 5.3 `doctor`에서 확인할 일

| 검사 | 예시 |
|---|---|
| Python | `python >= 3.11` |
| package import | `nyanya_agent.core` import 가능 |
| optional deps | `discord.py`, `fastapi`, `uvicorn` |
| env | token 존재 여부는 true/false만 표시 |
| workspace | allowed/trusted root 유효성 |
| dashboard | port 사용 가능 또는 현재 응답 |
| LaunchAgent | loaded/running/last exit code |
| Codex | CLI 존재 여부, app server 상태 |
| Discord | bot token API check, channel permission check |
| 보안 | `.env`, DB, logs package 포함 여부 |

## 6. 설치/배포 기술 스택

| 경로 | 역할 | 장점 | 단점 | 우선순위 |
|---|---|---|---|---|
| npm | 가장 쉬운 global CLI 진입점 | Node 사용자는 익숙함, wrapper 이미 존재 | Python dependency bootstrap 필요 | P0 |
| Homebrew | macOS 사용자용 정석 설치 | LaunchAgent와 잘 맞음, update 쉬움 | formula/tap/release checksum 필요 | P0 |
| pipx/PyPI | Python CLI 정석 | Python dependency 격리 우수 | 비개발자에게는 pipx 설치가 장벽 | P1 |
| GitHub Releases | brew formula와 수동 설치 기준 | tag/tarball/checksum 명확 | release 자동화 필요 | P0 |
| GitHub Actions | 빌드/검증/배포 자동화 | release 품질 안정화 | secrets 관리 필요 | P1 |

## 7. npm 배포 계획

npm 공식 문서는 scoped public package를 공개할 때 `npm publish --access public`을 사용한다고 설명한다. 또한 package 공개 전 민감정보, private key, password, PII를 제거하라고 안내한다.

출처: [npm scoped public packages](https://docs.npmjs.com/creating-and-publishing-scoped-public-packages/)

현재 `package.json`에는 이미 `@hcscat/nyanya-agent`와 `bin/*.js` wrapper가 존재한다. 우선 개발할 것은 wrapper의 완성도다.

필요 작업:

1. `npm pack --dry-run` 검증 추가
2. package `files` whitelist 재검토
3. `.env`, `data`, `logs`, `docs/private`, `.venv` 제외 검증
4. `nyanya-agent init` 구현
5. 첫 실행 시 `.venv` 생성 또는 pipx 설치 방식 결정
6. `npm run check`에 py_compile/test/security scan 포함
7. GitHub Actions에서 npm package artifact 생성

권장 설치 UX:

```bash
npm install -g @hcscat/nyanya-agent
nyanya-agent init
nyanya-agent doctor
nyanyactl install
nyanyactl start-all
```

## 8. Homebrew 배포 계획

Homebrew 공식 문서는 tap 저장소 이름을 `homebrew-` prefix로 만드는 것을 권장한다. Python formula는 application과 library를 구분하고, application dependency는 resource stanza로 고정할 수 있다.

출처:

- [Homebrew Tap](https://docs.brew.sh/How-to-Create-and-Maintain-a-Tap)
- [Homebrew Formula Cookbook](https://docs.brew.sh/Formula-Cookbook)
- [Homebrew Python for Formula Authors](https://docs.brew.sh/Python-for-Formula-Authors)

필요 작업:

1. `hcscat/homebrew-nyanya` 저장소 생성
2. `Formula/nyanya-agent.rb` 작성
3. GitHub release tarball URL과 `sha256` 고정
4. Python dependencies resource stanza 생성
5. `brew test nyanya-agent` 추가
6. 설치 후 `nyanya`, `nyanyactl` 실행 확인
7. LaunchAgent plist 생성은 사용자가 명시적으로 `nyanyactl install` 실행할 때만 수행

권장 설치 UX:

```bash
brew tap hcscat/nyanya
brew install nyanya-agent
nyanya init
nyanya doctor
nyanyactl install
nyanyactl start-all
```

## 9. 외부 접속 가능한 에이전트 시스템 선택지

외부 접속에는 두 종류가 있다.

1. dashboard/API를 외부에서 보는 것
2. 에이전트 런타임 자체를 클라우드에서 계속 실행하는 것

두 요구는 다르다. dashboard/API는 무료 serverless나 tunnel로 가능하다. 그러나 Discord bot gateway, memory worker, Codex 연동처럼 계속 살아 있어야 하는 런타임은 무료 serverless와 잘 맞지 않는다.

## 10. 외부 접속 권장안

### 10.1 1순위: Mac mini runtime + Cloudflare Tunnel

가장 현실적인 방식이다.

```text
사용자 브라우저
  -> Cloudflare Access 인증
  -> Cloudflare Tunnel
  -> Mac mini의 NyaNya dashboard/API
```

장점:

- NyaNya가 현재처럼 로컬 파일과 Codex를 사용할 수 있다.
- Discord token과 workspace를 클라우드로 옮기지 않아도 된다.
- 공유기 port forwarding이 필요 없다.
- Cloudflare Access 무료 플랜을 이용할 수 있다.

Cloudflare Tunnel 공식 문서는 private network/application access와 public application publishing에 사용하는 connector로 설명한다. Cloudflare Zero Trust pricing은 Free Plan을 제공한다.

출처:

- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)
- [Cloudflare Zero Trust Pricing](https://www.cloudflare.com/plans/zero-trust-services/)

주의:

- dashboard 인증은 반드시 필요하다.
- public URL에 dashboard를 인증 없이 열면 안 된다.
- 파일 수정/삭제 API는 외부에서 직접 호출하지 못하게 해야 한다.

### 10.2 2순위: Cloudflare Pages + Workers + D1/KV

dashboard frontend는 Cloudflare Pages, 간단한 API는 Workers, 상태 저장은 D1/KV로 처리하는 방식이다.

Cloudflare Workers Free plan은 일일 요청 제한이 있고, Free plan CPU time은 짧다. Pages는 무료 플랜에서 static site에 강하다.

출처:

- [Cloudflare Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [Cloudflare Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/)
- [Cloudflare Pages](https://pages.cloudflare.com/)

적합:

- dashboard frontend
- 간단한 상태 API
- webhook receiver
- agent command relay

부적합:

- 장시간 실행되는 Discord bot runtime
- 무거운 Python/Codex 작업
- 지속 WebSocket gateway client

### 10.3 3순위: Oracle Cloud Always Free VM

진짜 클라우드에서 계속 켜져 있는 agent runtime을 원하면 Always Free VM이 후보가 될 수 있다.

Oracle Cloud는 Always Free 서비스를 무기한 제공하고, Free Trial에는 30일 또는 크레딧 소진 시점까지 사용할 수 있는 크레딧을 제공한다고 설명한다.

출처:

- [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/)
- [OCI Free Tier documentation](https://docs.oracle.com/iaas/Content/FreeTier/freetier.htm)

장점:

- 항상 켜진 VM 구조가 가능하다.
- Discord bot, FastAPI, memory worker를 직접 띄울 수 있다.

단점:

- 서버 운영 부담이 크다.
- 보안 패치, SSH, firewall, backup, secret 관리가 필요하다.
- Codex Desktop/Mac local workspace 연동과는 맞지 않는다.

## 11. 무료/조건부 무료 서비스 비교

| 서비스 | 무료/조건부 무료 내용 | NyaNya에 적합한 용도 | 주의점 |
|---|---|---|---|
| Cloudflare Tunnel/Access | Zero Trust Free Plan 제공 | Mac mini dashboard/API 외부 접속 | 인증 필수, 공개 API 최소화 |
| Cloudflare Pages | 무료 static hosting, 500 builds/month 등 | dashboard frontend | backend runtime 아님 |
| Cloudflare Workers | Free plan 일일 요청 제한, 짧은 CPU time | relay/webhook/light API | long-running agent 부적합 |
| Firebase Hosting | Spark plan no-cost hosting 가능 | static dashboard frontend | App Hosting/Functions는 Blaze 필요 가능 |
| Firebase App Hosting | Blaze 필요, no-cost quota 존재 | Next.js류 app hosting | billing account 필요, 초과 과금 주의 |
| Vercel Hobby | free personal projects | frontend/serverless dashboard prototype | persistent bot runtime 부적합 |
| Netlify Free | free deploy, functions 포함 | frontend/static dashboard | long-running agent 부적합 |
| Supabase Free | DB/Auth/storage free project | remote metadata DB/Auth | project inactivity pause, agent runtime 아님 |
| Neon Free | serverless Postgres free tier | remote DB | storage/compute limit |
| Render Free | free web service 가능 | demo API | 15분 idle spin down, Discord bot 부적합 |
| Railway Free | trial/credit 중심 | short prototype | 항상 무료 runtime으로 보기 어려움 |
| Koyeb Free Instance | 1개 free instance, 제한된 CPU/RAM | 소형 demo backend | production 비권장, resource 작음 |
| Oracle Always Free | Always Free VM 제공 | always-on cloud runtime | 서버 운영 부담 큼 |

관련 출처:

- [Firebase Pricing](https://firebase.google.com/pricing)
- [Firebase App Hosting costs](https://firebase.google.com/docs/app-hosting/costs)
- [Vercel Hobby Plan](https://vercel.com/docs/plans/hobby)
- [Netlify Pricing](https://www.netlify.com/pricing/)
- [Supabase Pricing](https://supabase.com/pricing)
- [Neon Pricing](https://neon.com/pricing)
- [Render Free](https://render.com/docs/free)
- [Railway Pricing](https://railway.com/pricing)
- [Koyeb Instances](https://www.koyeb.com/docs/reference/instances)
- [Fly.io cost management](https://fly.io/docs/about/cost-management/)

## 12. 외부 접속 방식별 추천

| 목표 | 추천 방식 | 이유 |
|---|---|---|
| 집 밖에서 dashboard 보기 | Mac mini + Cloudflare Tunnel + Access | 무료/안전/현재 구조 유지 |
| 정적 소개 페이지 공유 | Cloudflare Pages 또는 Firebase Hosting | 무료 static hosting에 적합 |
| 간단한 remote command relay | Cloudflare Workers | 가벼운 API에 적합 |
| DB/Auth를 클라우드에 두기 | Supabase 또는 Neon | 무료 DB/Auth prototype 가능 |
| 완전 클라우드 agent runtime | Oracle Always Free VM 또는 저가 VPS | persistent process 필요 |
| 빠른 demo backend | Koyeb/Render/Railway | prototype은 가능하나 안정 운영에는 한계 |

## 13. 권장 단계별 실행 계획

### Phase 1: 설치/배포 MVP

목표:

- `nyanya init`
- `nyanya doctor`
- npm package 검증
- Homebrew formula 초안
- README install guide 정리

완료 기준:

```bash
npm pack --dry-run
npm install -g ./package.tgz
nyanya init
nyanya doctor
nyanyactl start-all
```

### Phase 2: 외부 접속 MVP

목표:

- local dashboard 인증 강화
- Cloudflare Tunnel guide 작성
- Access 정책 설정 guide 작성
- dashboard 외부 접속 smoke test

완료 기준:

```text
외부 URL 접속
-> Cloudflare Access 인증
-> NyaNya dashboard 표시
-> health endpoint 정상
-> 파일 변경 API는 외부에서 직접 실행 불가
```

### Phase 3: 배포 자동화

목표:

- GitHub Actions로 test/package 검증
- GitHub Release 생성
- npm publish dry-run
- Homebrew formula checksum 자동 갱신

### Phase 4: 멀티에이전트 기반

목표:

- `agent_profiles` table
- `nyanyactl agent create/list/start/stop`
- profile별 Discord token reference
- dashboard Agents 화면

### Phase 5: 오케스트레이션/승인

목표:

- planner/reviewer/worker workflow
- agent-to-agent event log
- approval queue
- 승인/거절 memory 저장

## 14. 최종 권고

가장 먼저 개발할 것은 설치/배포 개선이다. 이 작업은 이후 멀티에이전트, 외부 접속, 대시보드 확장을 안정적으로 검증하는 기반이 된다.

외부 접속은 다음 결론을 따른다.

1. NyaNya runtime은 당분간 Mac mini에서 유지한다.
2. dashboard/API만 Cloudflare Tunnel로 외부 접속시킨다.
3. static 문서나 소개 페이지는 Cloudflare Pages 또는 Firebase Hosting을 쓴다.
4. cloud DB가 필요해지면 Supabase 또는 Neon을 검토한다.
5. 완전 cloud runtime이 필요할 때만 Oracle Always Free VM 또는 저가 VPS를 검토한다.

무료 hosting은 많지만, "항상 실행되는 agent"에는 대부분 맞지 않는다. NyaNya의 핵심은 로컬 workspace, Codex, Discord bridge, memory worker이므로 처음에는 로컬 runtime + 안전한 외부 tunnel이 가장 효율적이다.
