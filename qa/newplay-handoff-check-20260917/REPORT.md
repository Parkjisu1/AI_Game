# NewPlay 현재 상태 및 전달 파일 검수

확인일: 2026-09-17 KST. 서버 관찰 시각: 12:06. 대상: 지정 ZIP, `handoff/ssyoung` 폴더, 기존 제작물 318개, NewPlay 전용 PC의 현재 WSL 서버.

**판정: 현재 ZIP은 참고 자료로 전달할 수 있지만, 전체 개발·운영 권한 이양용 완성본으로 바로 사용하게 하면 안 된다.** 실행 도구의 작업 유실, 문서와 실제 운영의 불일치, 전체 소스·실행 구성 누락을 확인했다. Ubuntu와 Docker 설치는 사용자가 진행하며, 이번 작업에서는 제품 코드·기존 문서·기존 ZIP·서버 설정·토큰을 변경하지 않았다.

## 현재 서버

| 확인 항목 | 실측 결과 | 인수에 미치는 영향 |
|---|---|---|
| Docker | 8개 running, 재시작 횟수 모두 0. web·mongo health는 healthy | 컨테이너 기동 확인. 모든 사용자 기능의 정상 판정은 아님 |
| 기존 서비스 | systemd 웹·워처와 일일 백업 타이머도 active | 기존 서비스와 Docker 서비스가 함께 존재 |
| 팀 공개 주소 | HTTPS 프록시는 `127.0.0.1:3000`으로 연결 | 공개 서비스는 기존 systemd 경로. Docker 웹 `3100`과 다름 |
| 데이터 | 공개 작업 목록 지문은 3000과 같고 3100과 다름 | 운영 기준 DB를 하나로 정한 뒤 인수해야 함 |
| DB 차이 | Mongo 27018 / 27019의 작업 수는 각각 26, 활성 Hub API 토큰 수는 각각 2 / 4 | 작업 수가 같다고 DB가 같은 것은 아님. 원장·토큰 상태도 다름 |
| 터미널 | 공개 `/gateway/term` GET은 404. Docker 설정은 `ws://127.0.0.1:3101` | 기존 설정으로 원격 사용자의 공개 터미널 완료를 주장할 수 없음. 이번에 로그인 WebSocket 접속은 수행하지 않음 |
| AI 인증·학습 | 확인한 개인 Claude 토큰 디렉터리는 양쪽 모두 파일 0, 공용 credentials 없음. 두 DB의 개인 프로필·작업 세션 각각 0 | 실제 팀원 계정의 AI 작업 및 프로필 축적을 완료했다고 판단할 근거 없음 |
| 지식 검색 | Qdrant green, 7,176 points. Ollama에 `bge-m3:latest` 존재 | 검색 기반 데이터·모델 존재 확인 |
| 미리보기 | 확인 대상 제품 원본 `.git`, 프런트엔드 의존성, 미리보기 `index.html` 없음 | 미리보기·제품 적용 경로의 기존 미완료 상태 지속 |
| 백업 | 9/17 04:30:49 작업 성공, 23개 파일 중 21개 비어 있지 않음 | 이번 확인은 생성 상태. 전체 Docker 복구를 시험한 결과가 아님 |

서버 웹 HEAD는 양쪽 모두 `ec9a83b2c9744b93c938b6a17ad6dc3a0705bf62`다. 워처 HEAD는 systemd `c82a5f0fa6c1d1491e5d8007a16968c4aa918096`, Docker `6f06ac733038987e80c014f48eeb50c0aaaf146c`다. 모두 9/16 재감사와 같고, 네 저장소 모두 미커밋 변경이 없다. 서로 다른 워처 커밋의 Python 내용 일치는 9/16에 확인한 결과다.

근거: [서버 요약](server-summary.json), [프록시 설정](tailscale-routing.json), `server-*.sh.stdout` 원본 관찰 기록. `server-data.sh.stdout`의 레거시 필드 `revoked_today`는 실제로 **2026-09-16 이후** 조건이다. 요약에서는 `revoked_since_20260916`으로 바로 표기했다. 이번 검사 중 토큰을 폐기하거나 발급하지 않았다.

## 전달 ZIP과 파일 판정

`E:\AI\scripts\newplay\handoff\newplay-hub-ssyoung.zip`

- 크기: 166,756 bytes. 파일 33개. ZIP CRC 검사 통과.
- SHA256: `31dd2350282aaff753ba7458c8319992c676d6a63259406dbbd2b767865bbe24`.
- 9/16 재감사 대상 ZIP과 동일하다. 기존 제작물 318개도 내용 변경·누락이 없다.
- ZIP과 `handoff/ssyoung` 폴더는 `FIXES-20260916.md` 한 파일이 다르다. ZIP에는 “서버에는 아직 적용하지 않았다”, 폴더에는 그 뒤의 적용 기록이 추가돼 있다.

### 1. `newplay-hub.ps1`: 일상 배포용 전달 보류

최신 ZIP의 스크립트를 실제 PowerShell 및 임시 Git 저장소, localhost 가짜 API로 실행했다. **6개 중 5개 통과, 1개 실패**했다.

재현 순서: 기존 파일 수정 → 배포 요청 전송 → 응답 대기 중 같은 파일을 추가 수정 → 배포 완료. 마지막 추가 수정이 사라지고 서버에 먼저 전송한 내용만 남는다. 새 미추적 파일은 이 재현에서 보존됐다. 모든 파일을 무조건 삭제한다는 뜻은 아니다.

원인: 배포 성공 후 `-AfterDeploy` 분기가 `git reset --hard refs/remotes/server/head`를 실행한다. 근거는 [ZIP 코드 152행](handoff/newplay-hub.ps1:152), [재현 검사](test_cli_handoff.py:82), [검사 결과](cli-results.xml)다. 기존 상위 폴더의 CLI는 다른 버전이므로 임의로 대신 쓰는 것도 검증된 해결책이 아니다.

### 2. `setup.ps1`: Windows 개발자용, 주소 변경 대응 부족

이 파일은 개발자 PC에서 Hub 토큰을 저장하고 두 저장소를 받는다. Ubuntu 서버 설치 파일이 아니며 일반 사용자는 실행할 필요가 없다. PowerShell 구문과 UTF-8 BOM은 정상이다.

`setup.ps1`에는 `-BaseUrl` 매개변수가 없고 하위 CLI의 기존 팀 주소를 그대로 쓴다. Ubuntu 전환 후 주소가 달라지면 이 파일에 새 주소를 전달할 수 없다. CLI 자체는 `-BaseUrl`을 받는다. 현재 주소를 유지하면 이 주소 문제는 발생하지 않지만, 위 CLI 결함은 별개로 남는다.

근거: [setup 매개변수](handoff/setup.ps1:17), [하위 호출](handoff/setup.ps1:64), [CLI 기본 주소](handoff/newplay-hub.ps1:35), [구문 검사](powershell-syntax.json). 실제 setup 실행은 토큰 저장을 수반하므로 실행하지 않았다.

### 3. 전체 소스·Docker 구성: 현재 ZIP만으로는 부족

ZIP의 `fixes/`는 패치와 변경 파일 묶음이다. 원래 안내에도 신규 설치 꾸러미가 아니라고 적혀 있다. 그러므로 단순 보조 패키지로는 이해할 수 있지만, 전체 플랫폼 이양 자료로는 완전하지 않다.

웹·워처 전체 Git 저장소가 없고, Compose가 참조하는 `src/web`, `src/watcher`, `Dockerfile.watcher`, `Dockerfile.workbench`, `gateway/Dockerfile`, `gateway/package.json` 등이 없다. `.env.*.example`, `sync-src.sh`도 빠져 있다. 이 파일들은 로컬 `E:\AI\scripts\newplay\deploy`에는 존재한다. 그 로컬 폴더를 그대로 최신 운영본이라고 단정하지 말고 최종 서버 커밋과 대조해 묶어야 한다.

Docker 서비스는 호스트의 소스와 데이터를 바인드 마운트한다. 이미지 파일만 전달하면 호스트 소스, Mongo 데이터, Git 작업공간, 개인 홈, 기록 등이 포함되지 않는다. 일반 개발자용 소스 배포와 운영 인수자용 데이터·비밀 설정 인계는 전달 대상을 구분한다.

근거: [구성 파일](handoff/fixes/deploy/docker-compose.yml), [누락 경로 검사](package-checks.json), [현재 컨테이너 마운트](server-state.sh.stdout).

### 4. 인수 문서: 일부 수정 권한 안내와 전체 권한 이양이 혼재

- `HANDOFF-newplay-hub.md`는 “지수님만 할 수 있는 일”, SSH·의존성 변경 금지 등을 전제로 한다. 전체 운영·개발 권한을 넘기려는 현재 목적과 다르다.
- `README-AI-AGENT.md`는 특정 수신자 계정과 기존 주소, 제한된 수정·배포 흐름을 전제로 한다. 코드 구조 참고는 가능하지만 새 소유자의 유일한 작업 지침으로 쓰기 어렵다.
- `SERVER-RUNBOOK.md`는 기존 Windows·WSL·systemd 구성이 포함된 운영 기록이다. Ubuntu 전환 이후 운영 명령과 최종 경로를 별도로 확정해야 한다.
- `OWNERSHIP-TRANSFER.md`는 이전 서버·임베딩 구성과 현재 전용 PC 설명이 섞여 있다. `V2-ARCHITECTURE.md`와 함께 설계·역사 참고로 보관한다.
- `FIXES-20260916.md`, `MANIFEST.md`에는 미적용 표기가 남고, MANIFEST의 16개 파일 목록은 현재 33개와 다르다. 반면 감사 부록은 서버 적용 완료를 주장한다. 최신 기준 문서가 하나로 정리되지 않았다.

### 5. QA 파일: 과거 통과 기록과 재실행 가능성을 구분

ZIP의 `fixes/verification/test_regressions.py`는 ZIP에 없는 `scripts/newplay/deploy/src/watcher/platform_deploy.py`를 찾는다. ZIP을 별도 위치에 풀어 `pytest --collect-only`를 실행했더니 `FileNotFoundError`로 검사 수집부터 실패했다. `test_cli.py`와 `test_web.cjs`도 같은 외부 폴더 구조를 전제한다.

따라서 동봉된 이전 통과 JSON을 “수신자가 이 ZIP만으로 같은 검사를 재실행할 수 있다”는 증거로 쓰면 안 된다. 이번 CLI 6개 검사는 감사용 경로를 별도로 지정해 **ZIP 안의 실제 CLI**를 실행한 결과다.

`qa/qa-run.sh`에는 호스트 경로의 `git worktree prune`이 남아 있다. 기존 RA-14 재현에서 컨테이너 경로로 등록된 다른 오래된 작업의 메타데이터가 삭제될 수 있었다. 이번에는 운영 서버에서 전체 QA를 재실행하지 않았다. `qa/claude-mock`은 가짜 검사용 CLI이지 실제 AI 실행 도구가 아니다.

근거: [수집 실패 기록](portable-tests.stdout), [호스트 정리 코드](handoff/qa/qa-run.sh:202), [9/16 전체 재감사](../newplay-reaudit-20260916/REPORT.md).

## 무엇을 전달해야 하나

일반 사용자는 최종 URL·본인 로그인 안내만 있으면 된다. 플랫폼 개발자는 전체 웹·워처·게이트웨이·배포 구성 소스와 Git 이력, 개발 안내, 개인별 권한이 필요하다. 운영을 넘겨받는 사람은 여기에 서버 관리권, 외부 서비스 소유권, 최종 Compose 설정, 데이터 백업·복원 절차까지 받아야 한다.

현재 제한된 CLI 토큰만 주는 것으로는 의존성·인증·배포 장치·인프라까지 스스로 수정할 수 없다. 전체 권한 이양과 일부 기능 수정 권한을 구분해야 한다.

수신자에게 전달할 설명과 구체적인 목록은 [수신자 안내](../../scripts/newplay/handoff/recipient-review-20260917/START-HERE.md)에 정리했다. ZIP 33개 파일의 개별 판정은 같은 폴더의 `FILE-VERDICTS.csv`에 있다. 이 두 파일은 이번 검수 문서이며 실행 제품을 새로 패키징한 것은 아니다.

## 검사 범위와 남은 확인

이번에 새로 수행한 검사는 ZIP·폴더 해시 대조, 서버 읽기 전용 상태·라우팅·데이터 집계 조회, CLI 행동 검사 6개, ZIP 검사 도구의 수집 가능 여부, PowerShell 구문 검사다. 서버에 배포·재기동·실제 AI 호출·DB 변경을 수행하지 않았다.

9/16 전체 재감사 RA-01~RA-16의 모든 재현을 이번에 반복한 것은 아니다. 관련 ZIP과 소스 버전이 그대로이므로 그 문제들이 해결됐다는 새 근거도 없다. 이전 보고서의 43/44를 이번 실행 결과로 합산하지 않는다.

최종 전달 전 필요한 확인은 최종 운영 주소·DB 일치, CLI 추가 수정 보존, 실제 계정 작업 1건·개인 터미널·미리보기, 새 운영자의 배포·복구 수행이다. 이는 Ubuntu/Docker 설치와 별개다. 이번 작업 결과만으로 “전수 정상, 남은 결함 0”이라고 안내하면 안 된다.
