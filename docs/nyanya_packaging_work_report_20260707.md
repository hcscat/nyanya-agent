# NyaNya Agent 설치/배포 패키징 작업 리포트

작성일: 2026-07-07 14:20:54 KST

## 1. 작업 목적

이번 작업의 목적은 NyaNya Agent를 앞으로 더 쉽게 설치하고 배포할 수 있도록 `packaging/` 폴더를 만들고, 설치/삭제/검증/배포 준비 파일을 실제로 추가하는 것이다.

쉽게 말하면, 기존에는 개발자가 저장소를 직접 열어 `python`, `pip`, `scripts/`를 알아서 실행해야 했다. 이번 작업은 앞으로 사용자가 다음과 같은 방식으로 설치할 수 있는 기반을 만든 것이다.

```bash
curl -fsSL https://example.com/nyanya/install.sh | bash
```

또는:

```bash
brew install nyanya-agent
```

또는:

```bash
npm install -g @hcscat/nyanya-agent
```

아직 완성된 공식 배포는 아니지만, 설치/배포 개발을 시작할 수 있는 기본 골격을 저장소에 추가했다.

## 2. 전체 변경 요약

| 구분 | 변경 내용 |
|---|---|
| 새 폴더 | `packaging/` 추가 |
| 설치 스크립트 | macOS/Linux용 `install.sh`, Windows PowerShell용 `install.ps1` 추가 |
| 삭제 스크립트 | `uninstall.sh`, `uninstall.ps1` 추가 |
| Homebrew 준비 | `nyanya-agent.rb.template` 추가 |
| macOS 자동실행 준비 | LaunchAgent plist template 3개 추가 |
| 배포 검증 | release allowlist/denylist, checksum 생성, release 검증 스크립트 추가 |
| npm 명령 | `nyanya` 명령 wrapper 추가 |
| package.json | npm package에 `nyanya`와 packaging 파일 포함 |

## 3. 추가한 폴더 구조

```text
packaging/
  README.md
  install/
    install.sh
    install.ps1
    uninstall.sh
    uninstall.ps1
  homebrew/
    Formula/
      nyanya-agent.rb.template
  launchd/
    com.hcs.nyanya.agent.plist.template
    com.hcs.nyanya.dashboard.plist.template
    com.hcs.nyanya.memory-worker.plist.template
  release/
    generate_checksums.sh
    package-allowlist.txt
    package-denylist.txt
    verify_release.sh
```

## 4. 왜 `packaging/` 폴더를 따로 만들었는가

설치/배포 관련 파일을 루트에 바로 만들면 처음에는 단순하지만, 시간이 지나면 저장소가 복잡해진다.

예를 들어 설치 스크립트, 삭제 스크립트, Homebrew formula, npm 검증 파일, LaunchAgent template, release 검증 스크립트가 모두 루트에 있으면 실제 앱 코드와 배포 코드가 섞인다.

이번에는 다음 기준으로 분리했다.

| 위치 | 역할 |
|---|---|
| `src/` | NyaNya Agent 실제 Python 코드 |
| `bin/` | npm/CLI wrapper |
| `scripts/` | 현재 로컬 실행용 스크립트 |
| `packaging/` | 설치, 삭제, 배포, 검증, Homebrew, LaunchAgent 준비 |

이 구조는 나중에 Homebrew tap이나 별도 installer repository로 분리하기도 쉽다.

## 5. 설치 스크립트

### 5.1 `packaging/install/install.sh`

macOS, Linux, WSL 계열에서 사용할 설치 스크립트다.

주요 동작:

1. 설치 위치를 결정한다.
2. local checkout 또는 GitHub repository에서 source를 가져온다.
3. `.git`, `.venv`, `data`, `logs`, `.env`, `docs/private` 같은 로컬/민감 파일을 제외하고 복사한다.
4. `.env.example`을 기반으로 `.env`를 생성한다.
5. `.env` 권한을 `0600`으로 설정한다.
6. Python virtual environment를 만든다.
7. `pip install -e ".[bots,dashboard]"`로 필요한 dependency를 설치한다.
8. `~/.local/bin`에 실행 명령을 생성한다.

생성되는 명령:

```text
nyanya
nyanya-agent
nyanyactl
nyanya-discord
nyanya-telegram
nyanya-dashboard
nyanya-memory-worker
```

기본 설치 위치:

```text
~/.local/share/nyanya-agent
```

기본 명령 위치:

```text
~/.local/bin
```

### 5.2 `packaging/install/install.ps1`

Windows PowerShell용 설치 스크립트다.

현재는 macOS/Linux installer와 같은 방향으로 구성했다.

기본 설치 위치:

```text
%LOCALAPPDATA%\nyanya-agent
```

기본 명령 위치:

```text
%USERPROFILE%\.local\bin
```

PowerShell launcher는 `.ps1` 파일로 생성된다.

## 6. 삭제 스크립트

### 6.1 `uninstall.sh`

macOS/Linux용 삭제 스크립트다.

기본 동작:

- `nyanya`, `nyanya-agent`, `nyanyactl` 같은 launcher만 삭제한다.
- 설치 디렉터리는 보존한다.

완전 삭제:

```bash
packaging/install/uninstall.sh --purge-data
```

`--purge-data`를 붙이면 설치 디렉터리까지 삭제한다.

### 6.2 `uninstall.ps1`

Windows PowerShell용 삭제 스크립트다.

기본 동작은 `uninstall.sh`와 동일하다. 완전 삭제는 다음처럼 한다.

```powershell
.\uninstall.ps1 -PurgeData
```

## 7. Homebrew 준비

추가 파일:

```text
packaging/homebrew/Formula/nyanya-agent.rb.template
```

이 파일은 실제 Homebrew formula가 아니라 template이다. 이유는 아직 GitHub release tag와 tarball checksum이 정해지지 않았기 때문이다.

나중에 release를 만들면 다음 값을 채워야 한다.

```text
{{VERSION}}
{{SHA256}}
```

예상 사용자 설치 방식:

```bash
brew tap hcscat/nyanya
brew install nyanya-agent
```

Homebrew formula는 Python virtualenv 방식으로 설치하는 형태를 준비했다.

## 8. LaunchAgent template

macOS에서 재부팅 후 자동 실행하려면 LaunchAgent plist가 필요하다.

이번에 추가한 template:

```text
com.hcs.nyanya.agent.plist.template
com.hcs.nyanya.dashboard.plist.template
com.hcs.nyanya.memory-worker.plist.template
```

각각의 역할:

| 파일 | 역할 |
|---|---|
| `agent` | Discord bridge 실행 |
| `dashboard` | FastAPI dashboard 실행 |
| `memory-worker` | 장기기억 후보 추출 worker 실행 |

현재는 template만 추가했다. 실제 설치 시에는 `{{INSTALL_DIR}}` 값을 설치 경로로 바꾼 뒤 `~/Library/LaunchAgents`에 배치해야 한다.

## 9. 배포 검증 도구

추가 파일:

```text
packaging/release/verify_release.sh
packaging/release/generate_checksums.sh
packaging/release/package-allowlist.txt
packaging/release/package-denylist.txt
```

### 9.1 `verify_release.sh`

배포 전에 실행하는 검증 스크립트다.

검사 항목:

1. 필수 파일이 존재하는지 확인
2. 민감하거나 생성된 파일이 Git에 추적되지 않는지 확인
3. Python 파일이 컴파일되는지 확인
4. shell script 문법이 맞는지 확인
5. `npm pack --dry-run` 결과에 민감 파일이 들어가지 않는지 확인
6. release 대상 경로에 token/API key 패턴이 없는지 확인

실행 결과:

```text
Release verification passed.
```

### 9.2 `generate_checksums.sh`

release tarball 또는 설치 파일의 SHA-256 checksum을 생성한다.

예:

```bash
packaging/release/generate_checksums.sh dist/nyanya-agent.tar.gz
```

Homebrew formula를 만들 때 `sha256` 값이 필요하므로 이 스크립트를 사용한다.

## 10. npm package 변경

기존 npm package에는 `nyanya-agent` 명령만 있었다. 이번 작업에서 `nyanya` 명령을 추가했다.

추가 파일:

```text
bin/nyanya.js
```

변경된 `package.json`:

```json
"bin": {
  "nyanya": "bin/nyanya.js",
  "nyanya-agent": "bin/nyanya-agent.js"
}
```

이렇게 한 이유는 앞으로 사용자가 `nyanya` 하나로 진입하도록 만들기 위해서다.

또한 npm package에 `packaging/` 파일들이 포함되도록 `package.json`의 `files` 항목을 업데이트했다.

## 11. 검증 결과

실행한 검증:

```bash
packaging/release/verify_release.sh
node --check bin/nyanya.js
node --check bin/nyanya-agent.js
npm run check
packaging/install/install.sh --help
packaging/install/uninstall.sh --help
```

결과:

| 검증 | 결과 |
|---|---|
| release 필수 파일 확인 | 통과 |
| denylist Git 추적 확인 | 통과 |
| Python compile | 통과 |
| shell script 문법 | 통과 |
| npm pack dry-run | 통과 |
| 민감정보/token 패턴 검사 | 통과 |
| Node wrapper 문법 검사 | 통과 |
| npm check | 통과 |
| install/uninstall help 출력 | 통과 |

`npm pack --dry-run` 결과에서 `.env`, `data/`, `logs/`, `run/`, `downloads/`, `docs/private/`는 포함되지 않았다.

## 12. 현재 한계

이번 작업은 "설치/배포 패키징 개발 기반"을 만든 것이다. 아직 완성된 공식 배포는 아니다.

남은 작업:

1. `nyanya init` 구현
2. `nyanya doctor` 확장
3. `nyanya service ...`로 `nyanyactl` 기능 통합
4. 설치 스크립트에서 TUI onboarding 연결
5. macOS LaunchAgent template 자동 적용 기능
6. Homebrew tap repository 생성
7. GitHub release 자동화
8. npm publish workflow 추가
9. Windows PowerShell 설치 실제 환경 테스트
10. 설치 후 Discord/Telegram/LLM 인증 wizard 구현

## 13. 비전공자용 설명

이번 작업은 NyaNya Agent를 "압축 파일만 던져놓는 프로그램"에서 "설치 프로그램을 만들 수 있는 프로그램"으로 한 단계 정리한 작업이다.

비유하면 다음과 같다.

| 기존 상태 | 이번 작업 이후 |
|---|---|
| 부품이 상자에 들어 있음 | 조립 설명서와 기본 공구를 넣음 |
| 개발자가 직접 실행 방법을 알아야 함 | 설치 스크립트가 기본 작업을 대신함 |
| 배포 전에 무엇이 들어가는지 확인하기 어려움 | 검증 스크립트가 위험 파일 포함 여부를 확인함 |
| macOS 자동 실행 설정이 코드 안에 흩어짐 | LaunchAgent template으로 정리됨 |
| Homebrew 배포 준비가 없음 | formula template이 생김 |

즉, 아직 완성된 installer는 아니지만 installer를 만들기 위한 뼈대가 생겼다.

## 14. 다음 추천 작업

다음 단계는 `nyanya init`과 `nyanya doctor`다.

이유:

1. installer가 있어도 초기 설정이 어렵다면 사용자는 설치에 실패한다.
2. Discord token, Telegram token, LLM model 설정은 반드시 guided wizard가 필요하다.
3. 설치 후 문제가 생겼을 때 `doctor`가 원인을 알려줘야 한다.

추천 순서:

```text
1. nyanya init
2. nyanya doctor
3. nyanya service status/start/stop/restart
4. LaunchAgent 자동 적용
5. Homebrew tap
6. GitHub release + npm publish
```

## 15. 결론

`packaging/` 폴더를 추가했고, 설치/삭제/배포 검증/Homebrew/LaunchAgent 준비 파일을 구현했다.

현재 결과물은 공식 배포 직전 단계가 아니라, 공식 배포를 만들기 위한 기반이다. 그러나 중요한 기준인 "무엇을 포함하고 무엇을 제외해야 하는지", "어떻게 설치 파일을 만들지", "배포 전 무엇을 검사할지"는 이번 작업으로 정리되었다.
