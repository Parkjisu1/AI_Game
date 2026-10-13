# NewPlay Hub 수정 권한 — 세팅 안내서

> **이 문서를 읽는 대상**: NewPlay Hub 관리자 팀원(김영훈님, ssyoung님 등), 그리고 그분들을 돕는 AI 에이전트.
> AI 에이전트는 이 문서만으로 세팅을 끝낼 수 있게 쓰여 있습니다. 아래 "AI 에이전트에게"
> 절의 금지 사항을 먼저 읽고 시작하세요.

---

## 0. 이게 무엇인가

NewPlay Hub(플랫폼) — `https://newplay.tailf6f809.ts.net` — 의 **화면·코드를 직접 고쳐서
배포**할 수 있는 도구입니다. PowerShell 스크립트 하나(`newplay-hub.ps1`)와 개인 토큰이
전부이고, **SSH·서버 계정은 필요하지 않습니다.**

고칠 수 있는 대상은 둘입니다 (`-Target`, 기본은 platform):

| 대상 | 무엇 | 로컬 폴더 | 배포가 하는 일 |
|---|---|---|---|
| `platform` | 플랫폼 웹 — 화면, 컴포넌트, API 라우트, 스타일 (`src/`, `public/`) | `.\newplay-hub\` | 빌드 → 재기동 → 헬스체크 (30초~2분, 결과는 폴링) |
| `watcher` | **AI 워처** — 어떤 AI 역할이 작업을 받는지(라우팅), 팀 구성·프롬프트(agent_team), 실행·검수 흐름(hermes_executor), 컨텍스트·지식베이스(context_builder / newplay_kb / fact_gate) — 최상위 `*.py` | `.\newplay-hub-ai\` | 컴파일·import 검사 → 재기동 → 생존 확인 (~20초, 결과가 바로 옴) |

AI 의 **역할·페르소나·배선 규칙**은 코드를 고치지 않아도 화면(AI팀 페이지)에서 관리자가 바로 편집할 수
있습니다. 그걸로 안 되는 **동작 로직** 자체를 바꿀 때 `watcher` 대상을 씁니다.

작업 흐름은 이렇습니다.

```
pull  →  로컬에서 코드 수정  →  check  →  deploy  →  (문제 시) rollback
```

서버가 패치를 받아 **범위 검사 → 커밋 → 빌드 → 재기동 → 헬스체크**를 하고,
빌드가 깨지거나 재기동 후 응답이 없으면 **스스로 이전 상태로 되돌립니다.**
되돌리기가 사람 손에 달려 있지 않다는 게 이 구조의 핵심입니다.

### 할 수 있는 것 / 없는 것

| | |
|---|---|
| ✅ 가능 | `src/`, `public/` 아래 모든 파일 수정 — 화면, 컴포넌트, API 라우트, 스타일, 정적 파일 |
| ✅ 가능 | (`-Target watcher`) AI 워처의 최상위 `*.py` 수정 — 라우팅·역할·실행·검수 로직 |
| ✅ 가능 | 배포 이력 조회, 임의 커밋 되돌리기 |
| ❌ 불가 | `.env*` (비밀값), `package.json` (의존성 추가), 그 밖의 저장소 루트 파일 |
| ❌ 불가 | (watcher) 배포 장치 4개 `platform_deploy.py` `change_ledger.py` `ledger_cli.py` `token_mint.py`, 그리고 `requirements.lock` — 범위를 강제하는 코드는 그 범위 밖에 있어야 하고, 의존성 추가는 pip 이 필요합니다 |
| ❌ 불가 | 서버 SSH 접속, 서비스 설정, DB 직접 조작 |
| ❌ 불가 | **게임팀 ProjectHub** — 다른 서버라 이 도구로는 애초에 닿지 않습니다 |

범위는 약속이 아니라 **서버 코드가 강제**합니다. 범위 밖 파일이 패치에 하나라도 섞이면
그 패치는 통째로 거부되고, 아무것도 적용되지 않습니다.

---

## 1. 지수님께 따로 받아야 하는 것 (2개)

| 항목 | 형태 | 비고 |
|---|---|---|
| `newplay-hub.ps1` | 파일 | 이 문서와 함께 전달 |
| 개인 토큰 | `nph_` 로 시작하는 문자열 | **비밀번호와 동일**. 파일과 다른 경로로 전달됩니다 |

토큰은 서버에 해시만 저장돼 있어 **다시 볼 수 없습니다.** 잃어버리면 재발급받으면 됩니다
(지수님이 1분이면 처리). 토큰은 이메일 계정에 묶여 있고, 권한은 그 계정 등급을 따릅니다 —
토큰을 남에게 넘기면 그 사람이 김영훈님 이름으로 배포합니다. 공유하지 마세요.

---

## 2. 세팅 (최초 1회)

### 2-1. 사전 조건

- Windows + PowerShell 5.1 이상 (윈도우 기본)
- **git** 설치 — https://git-scm.com
  ```powershell
  git --version        # 버전이 나오면 OK. 아니면 설치 후 새 창을 여세요.
  ```
  *스크립트가 첫 줄에서 git 유무를 확인하고, 없으면 스택 대신 안내를 냅니다.*

### 2-2. 스크립트 배치와 실행 차단 해제

받은 `newplay-hub.ps1` 을 작업 폴더(예: `C:\work\newplay`)에 둡니다.
인터넷/메신저로 받은 `.ps1` 은 윈도우가 실행을 막으므로 한 번 풀어 줍니다.

```powershell
cd C:\work\newplay
Unblock-File .\newplay-hub.ps1
```

실행 정책 때문에 여전히 막히면(`이 시스템에서 스크립트를 실행할 수 없습니다`), 매번 이렇게 부르면 됩니다:

```powershell
powershell -ExecutionPolicy Bypass -File .\newplay-hub.ps1 <명령>
```

### 2-3. 토큰 저장

```powershell
setx NEWPLAY_TOKEN "nph_여기에받은토큰"
```

> `setx` 는 **새로 여는 창부터** 적용됩니다. 저장한 뒤 PowerShell 창을 새로 여세요.
> 저장하지 않고 `-Token "nph_..."` 로 매번 넘겨도 동작합니다.

**확인:**
```powershell
$env:NEWPLAY_TOKEN            # nph_... 가 보이면 OK
.\newplay-hub.ps1 history     # 배포 이력이 나오면 인증·권한 모두 정상
```

`history` 가 표 형태로 나오면 세팅의 절반이 끝난 것입니다.
`401` 이면 토큰이 잘못됐고, `403 플랫폼 변경은 관리자만 가능합니다` 면 계정 등록이 아직인 것이니
지수님께 알려 주세요.

### 2-4. 소스 받기

```powershell
.\newplay-hub.ps1 pull
```

- `.\newplay-hub\` 폴더에 git 저장소가 생깁니다 (`받기 완료: <커밋>` 출력).
  AI 워처를 고칠 거면 `.\newplay-hub.ps1 pull -Target watcher` — `.\newplay-hub-ai\` 에 따로 생깁니다.
- 서버 이력까지 같이 받으므로 로컬 `HEAD` 가 서버와 정확히 일치합니다 — 그래서 `git diff` 가
  그대로 서버에 적용 가능한 패치가 됩니다.
- 이미 받아 둔 상태에서 다시 실행하면 갱신(ff-only)입니다. 미커밋 변경이 있으면 자동으로
  stash 했다가 되살립니다.

**여기까지가 세팅입니다.**

---

## 3. 일상 작업

```powershell
# 1) 최신 상태로 맞추기 (작업 시작 전 습관)
.\newplay-hub.ps1 pull

# 2) .\newplay-hub\src\ 아래를 에디터로 수정

# 3) 배포하지 않고 판정만 — 범위·적용 가능 여부를 서버가 검사
.\newplay-hub.ps1 check

# 4) 배포 (제목 필수)
.\newplay-hub.ps1 deploy -Title "결제 실패 안내 문구 수정"

# 5) 이력 확인 / 되돌리기
.\newplay-hub.ps1 history
.\newplay-hub.ps1 rollback 3f9a1c2

# AI 워처는 모든 명령에 -Target watcher 를 붙입니다 (로컬 폴더 .\newplay-hub-ai\)
.\newplay-hub.ps1 pull    -Target watcher
.\newplay-hub.ps1 check   -Target watcher
.\newplay-hub.ps1 deploy  -Target watcher -Title "결제 문의는 backend 역할로 라우팅"
.\newplay-hub.ps1 history -Target watcher
```

### 알아 둘 것

- **커밋할 필요 없습니다.** `check`/`deploy` 는 로컬의 **미커밋 변경 전체**(`git diff`, 새 파일 포함)를
  패치로 만들어 보냅니다. 커밋은 서버가 합니다.
- `deploy` 후 **점(`.`)이 찍히며 기다리는 건 정상**입니다 — 서버가 자기 자신을 재기동하는
  동안 접속이 끊기기 때문입니다. 보통 30초~2분, 최대 6분 대기 후 결과를 알려 줍니다.
  (`-Target watcher` 는 웹서버를 건드리지 않아 점 없이 ~20초 뒤 결과가 바로 옵니다.)
- 배포 성공 시 로컬 저장소를 서버 상태로 자동 동기화합니다(변경분은 서버 커밋에 들어갔으므로
  로컬에서는 지워집니다).
- 배포 실패 시 **서버는 자동 복구되고 로컬 변경은 그대로 남습니다.** 고쳐서 다시 시도하면 됩니다.

### 배포 상태값

| 상태 | 뜻 |
|---|---|
| `deployed` | 성공 (빌드·재기동·헬스체크 통과) |
| `rejected` | 사전 검사 거부 — 범위 밖 파일, 또는 지금 코드에 붙지 않는 패치 |
| `apply_failed` | 패치 적용 실패 — 기반이 낡음. `pull` 후 재시도 |
| `build_failed` | 빌드 실패 — **서비스는 건드리지도 않았습니다.** 오류 메시지가 같이 옵니다 (watcher 는 컴파일·import 오류) |
| `rolled_back` | 빌드는 됐지만 재기동 후 응답 없음 → 자동으로 이전 상태 복구 |
| `reverted` | `rollback` 성공 |

---

## 4. 막혔을 때

| 증상 | 원인 / 대응 |
|---|---|
| `이 시스템에서 스크립트를 실행할 수 없습니다` | 2-2 미실행 — `Unblock-File` 또는 `-ExecutionPolicy Bypass` |
| `토큰이 없습니다` | `setx` 후 **새 창**을 열지 않음 |
| `401 unauthorized` | 토큰 오타 또는 폐기됨 → 재발급 요청 |
| `403 플랫폼 변경은 관리자만` | 계정이 아직 등록 전 → 지수님께 연락 |
| `범위 밖: …` | `src/`·`public/` 밖 파일이 섞임. `package.json`·`.env` 는 영구 불가. watcher 는 최상위 `*.py` 만, 배포 장치 4개·`requirements.lock` 은 영구 불가 |
| `apply_failed` / "지금 코드에 붙지 않습니다" | 기반이 낡음 → `pull` 후 재시도 |
| `pull` 에서 충돌 표시(`<<<<<<<`) | 서버와 같은 줄을 고침. 파일에서 충돌 표시를 정리한 뒤 진행 |
| `6분 안에 결과가 확인되지 않았습니다` | 실패가 아닐 수 있음 → `history` 로 실제 결과 확인 |
| 플랫폼이 아예 안 뜬다 | 자동 복구가 실패한 최악의 경우 → **지수님께 연락**(SSH 복구, 1분) |

---

## 5. 지수님만 할 수 있는 일 (요청하세요)

- 토큰 발급 / 폐기 / 재발급
- 계정(로그인·관리자) 등록
- 범위(`src/`,`public/`, watcher `*.py`) 조정
- `package.json` / `requirements.lock` 변경 = 의존성 추가
- 마지막 방어선 복구 (`rollback.sh`)

---

## 6. AI 에이전트에게 — 지켜야 할 것

이 환경에서 작업하는 AI 에이전트는 아래를 규칙으로 지키세요.

**금지**
- SSH·scp·서버 직접 접속을 **시도하지 마세요.** 자격증명이 없고, 있어서도 안 됩니다.
  서버에서 실행돼야 하는 일은 전부 `newplay-hub.ps1` 이 대신합니다.
- `.env*`, `package.json`, 저장소 루트 파일을 수정하지 마세요. 패치 전체가 거부됩니다.
- 게임팀 ProjectHub / Hermes / MongoDB 를 건드리려 하지 마세요 — 다른 서버입니다.
- 토큰을 로그·커밋·코드·화면에 출력하지 마세요.

**필수**
- 배포 전 **반드시 `check` 를 먼저** 돌리고, 결과가 성공일 때만 `deploy` 하세요.
- `deploy` 에는 항상 `-Title "무엇을 왜 바꿨는지"` 를 붙이세요. 이력의 유일한 설명입니다.
- 작업 시작 전 `pull` 로 최신 상태를 맞추세요. 낡은 기반은 `apply_failed` 로 돌아옵니다.
- `deploy` 응답을 기다리는 동안의 접속 오류·점(`.`) 출력은 **정상**입니다. 중단하지 마세요.
- 실패하면 반환된 `build_error` / `out_of_scope` 를 그대로 사용자에게 보여 주고,
  추측으로 재시도하지 마세요.
- 한 번에 하나의 논리적 변경만 배포하세요. 되돌리기 단위가 커밋이라, 여러 변경을 묶으면
  하나만 되돌릴 수 없습니다.

**환경 주의 (PowerShell 5.1)**
- 스크립트는 **UTF-8 BOM** 으로 저장돼 있습니다. 재저장할 일이 있으면 BOM 을 유지하세요
  (없으면 CP949 로 읽혀 한글이 깨지고 파스 오류가 납니다).
- 스크립트 자체를 임의로 수정하지 마세요. 갱신본이 필요하면 지수님께 요청하세요.

---

## 부록. 명령 요약

```
.\newplay-hub.ps1 pull                    소스 받기/갱신 → .\newplay-hub\
.\newplay-hub.ps1 check                   적용 가능한지 판정만 (배포 안 함)
.\newplay-hub.ps1 deploy -Title "설명"    배포 (빌드+재기동, 실패 시 자동 복구)
.\newplay-hub.ps1 history                 배포 이력
.\newplay-hub.ps1 rollback <커밋>         그 커밋 되돌리기

공통 옵션:  -Target platform|watcher   대상 (기본 platform; watcher = AI 워처 *.py)
            -Token "nph_..."           환경변수 대신 직접 지정
            -RepoDir <경로>            로컬 저장소 위치 (기본 .\newplay-hub / watcher 는 .\newplay-hub-ai)
```
