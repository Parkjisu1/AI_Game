# R3 로컬 회귀 시험 준비와 실행

아래는 이번에 사용한 **Windows + WSL Ubuntu** 시험 절차입니다. 운영 Ubuntu의 컨테이너 관통 QA를 대신하지 않습니다. 실제 계정·운영 DB·토큰을 넣지 마세요.

## 시험 폴더 준비

ZIP의 `qa` 폴더를 시험 루트로 사용합니다. 이 폴더 안에 다음이 있어야 합니다.

```text
qa/
  deploy/                  전체 소스의 별도 시험 사본
    gateway/
    src/web/               전체 웹 소스와 node_modules
    src/watcher/           전체 워처 소스
  test-tools/              임시 Mongo 실행 도구
  build_qa.py
  start-qa-mongo.cjs
  qa-fixture.cjs
  run_checks.py
  ...나머지 시험 파일
```

**`changes/deploy`는 24개 변경 파일만 있으므로 전체 소스를 대체하지 않습니다.** 원래 기준본 `newplay-ubuntu-migration-20260918/handoff/deploy`의 전체 소스를 별도 시험 사본 `qa/deploy`에 준비하고, 루트 `verify_update.py --deploy-dir <시험 사본>`이 통과한 다음 `changes/deploy`의 파일을 같은 상대 경로로 반영합니다. 운영 폴더 위에서 시험하지 마세요.

필요한 도구는 Windows Node/npm·Git·Python, WSL 배포판 `Ubuntu`의 Python3·Git, Python 패키지 `pymongo`, `requests`, `python-dotenv`, `playwright`, Playwright Chromium입니다. 웹 의존성은 `qa/deploy/src/web`에서 `npm ci`, 임시 Mongo 도구는 `qa/test-tools`에서 `npm ci`로 설치합니다. Python 의존성이 없으면 시험용 가상환경에서 `python -m pip install pymongo requests python-dotenv playwright`, `python -m playwright install chromium`으로 준비합니다. 임시 Mongo 최초 실행은 테스트 바이너리를 내려받을 수 있습니다.

이번 검증은 Windows Python 3.13, Node 24.12.0, WSL Ubuntu Python 3.12 환경에서 수행했습니다. 모듈 버전은 제공된 잠금 파일을 사용합니다. 환경이 다르면 결과를 별도 기록하세요.

## 실행 순서

각 PowerShell 창에서 같은 `qa` 폴더로 이동합니다. 로컬 포트 27999, 13010, 13011, 13012가 비어 있어야 합니다.

1. 창 A: `node start-qa-mongo.cjs` → `QA_MONGO_READY` 확인.
2. 창 B: `python build_qa.py` → `Build exit: 0` 확인. 합성 설정만 사용하는 production 빌드입니다.
3. 창 B: `node qa-fixture.cjs` → `QA_FIXTURE_READY` 확인. 창을 열어 둡니다.
4. 창 C: `python run_checks.py` → 10개 항목 모두 `PASS` 확인.
5. `checks-results.json`, `profile-races-results.json`, `browser-results.json`, `browser-git-live-results.json`, 각 로그를 확인합니다. 브라우저 오류 목록은 비어 있어야 합니다.
6. 창 B와 A에서 Ctrl+C로 시험 서비스를 종료합니다. 로컬 시험 포트가 닫혔는지 확인합니다.

`test_profile_races.cjs`를 따로 실행하려면 `QA_PYTHON` 환경변수에 시험용 Python 실행 파일을 지정하거나 `python`이 PATH에서 동작해야 합니다. 통합 실행기는 현재 Python 경로를 자동으로 전달합니다.

임시 Mongo는 127.0.0.1:27999에만 연결합니다. 경쟁 시험은 고정된 합성 DB `newplay_profile_regression`만 초기화하고 종료 시 삭제합니다. 브라우저 시험은 합성 `newplay_qa` 데이터를 사용합니다. 시험 쿠키와 런타임 로그는 실행 중 생성되지만 전달 ZIP에는 포함하지 않습니다.

## 실제 서버에서 별도로 확인할 것

적용 전 소스·DB 백업, 현재 작업 유무, 프로필 중복 및 인덱스 생성 권한을 확인합니다. 적용 후 실제 Docker에서 파일 비교·저장 충돌·새 파일 표시·터미널·세션 학습·개발 대리 실행을 확인해야 합니다. 계정 연결과 실제 업무 완주는 해당 사용자 본인이 진행합니다.

신규 `test_git_live.py`는 Linux 임시 Git 원격에서 실행합니다. `browser_git_live.py`는 QA 작업 폴더의 `.git/qa-remote.git`과 `.git/qa-author`에 합성 원격·작성자를 만들며, 원격 자동 갱신까지 약 60초 기다립니다. 반복 실행 시 `qa-fixture.cjs`를 재시작하여 새 임시 저장소를 준비하세요. 운영 Git 원격이나 자격 증명을 넣지 마세요.
