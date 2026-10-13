**NewPlay 인수인계 QA — 2026-09-16**

**판정: 현 자료를 근거로 “QA 완료·독립 운영 및 소유권 이양 준비 완료”라고 승인할 수 없다.** 제품 수정은 수행하지 않았다. 아래에는 원본 함수에서 재현한 결함, 전달된 배포 구성의 결함, 아직 검증하지 못한 인수 조건을 구분했다. 운영 DB 쓰기·배포·롤백·서비스 재기동·Claude 유료 호출은 하지 않았다.

소프트웨어·QA·배포 지적은 **19건: P1 11건, P2 8건**이다. P1은 이양 전 우선 해소할 권한·데이터·핵심 동작 문제, P2는 조건부 기능 결함과 운영·설치 재현성 문제다. 실제 운영에서 사고가 발생했다는 뜻은 아니다.

**대상과 기준**

| 대상 | 확인 범위 |
|---|---|
| 지정 ZIP | 14개 항목 전부 확인. 풀어둔 ssyoung 폴더와 14/14 바이트 일치. SHA-256 `66335a2cc0e30006640fd0b45d132e5dbcc9a0f25f1d28a73ebe00969c8c0ac4` |
| E:/AI/scripts/newplay | 99개 파일 목록·해시 확보. 웹 오버레이, 워처, PC 운영 스크립트, compose, gateway, 회귀·QA, 이양 문서 포함 |
| 운영 서버가 제공한 웹 git bundle | 176개 추적 파일. HEAD `487abdf7c7114c6774fddb72f54f619645ea852c` |
| 운영 서버가 제공한 워처 git bundle | 24개 추적 파일. HEAD `c7f63781fc1fe089843bfb138d3dba1b99d869ac` |
| 관련 기존 코드 | tools/projecthub-web의 clean 분기, hermes/watcher의 연계 참조, scripts/qa-feature-check.mjs. scripts/tools/hermes/History/docs/platform/webapp/.claude 및 루트 문서에서 NewPlay 언급 파일 104개 확인 |

서버 자료는 이 PC에 이미 등록된 NEWPLAY_TOKEN으로 **GET history·bundle만** 호출해 확보했다. 토큰 값은 보고서·로그에 기록하지 않았다. git bundle의 커밋 소스를 검사한 것이며 서버 작업 트리에 미커밋 변경이 있는지, 실제 컨테이너의 env·네트워크·마운트가 같은지는 확인하지 않았다. 로컬 task_router.py와 서버본의 차이는 인수 검수 주석 1줄이다. 로컬 웹 오버레이만으로는 terminal/profiles/workspace 등 최신 기능을 대표할 수 없어 서버본으로 검사를 확장했다.

파일 목록·구문·빌드 범위는 전수로 수집했고, 동작 검사는 권한·배포·계정·학습·인수 경로를 중심으로 수행했다. 모든 화면·업무 시나리오를 실제 계정으로 완주했다는 의미의 “전 기능 QA 완료”는 아니다. 관련성이 없는 게임 추출물·모델·대용량 데이터는 기능 QA 범위에 넣지 않았다.

**통과한 검사와 한계**

| 검사 | 결과 | 해석 |
|---|---|---|
| ZIP 대조 | 14/14 일치 | 전달 ZIP과 검토 폴더가 같음 |
| ZIP 자격증명 패턴 검사 | 실제 토큰/개인키 형태 탐지 0건 | nph_, sk-, GitHub 토큰, PEM 개인키에 대한 휴리스틱. 비밀 부재의 완전한 증명은 아님 |
| 구문 검사 | Python 48개, JavaScript 9개, Bash 19개, PowerShell 6개 통과 | 중복 사본 포함. TypeScript는 웹 전체 빌드에서 검사 |
| 워처 모듈 import | 22/22 통과 | Python 3.13.5, 외부 연결·스레드 기동 차단. Linux 서비스 실기동 검사는 아님 |
| 웹 npm ci | 종료 코드 0, 436 패키지 설치 | 격리된 소스 사본에서 --ignore-scripts 사용 |
| 웹 production build | 컴파일·TypeScript·Next build 종료 코드 0 | Windows / Node 24.12.0. compose의 Linux / Node 20 실행 검증과는 구분 |
| 공개 HTTP GET | 로그인 200, 보호 화면 5개 307, API·SSE 7개 401 | 로그인 전 보호 경로 13개 확인. 로그인 후 기능 검사가 아님 |
| 인증된 배포 관리 읽기 | platform·watcher history 200, bundle 200 | 읽기 접근 정상. 배포·롤백 쓰기는 미실행 |
| 원본 보존 | 기준 파일 321개 해시 변경 0개 | 추가 자료는 qa/newplay-audit-20260916에만 생성 |

빌드 중 실제 운영 DB 접근을 막기 위해 의도적으로 127.0.0.1:9를 사용했다. build.log의 Mongo 연결 거부는 이 격리 설정에서 발생한 것이며 운영 장애로 세지 않았다. workspace-root/NFT tracing 경고가 있었고, 빌드 종료 후 로그를 콘솔에 출력하는 보조 Python 코드에 CP949 인코딩 오류가 발생했지만 npm build 자체는 exit 0이었다.

**결함 목록**

| ID | 등급 | 지적 |
|---|---|---|
| NP-01 | P1 | 일반 작업 수정 API로 채택 권한과 요청자 정보를 우회 |
| NP-02 | P1 | 배포 범위 검사에서 삭제 파일이 빠져 보호 파일 삭제가 허용됨 |
| NP-03 | P1 | 서로 다른 이메일이 같은 개인 컨테이너·홈으로 매핑됨 |
| NP-04 | P1 | 개인 터미널에서 도달 가능한 내부망에 무인증 배포 실행기와 DB가 있음 |
| NP-05 | P1 | 학습되는 검사 명령의 개행으로 추가 셸 명령이 통과 |
| NP-06 | P1 | 빌드 시간 초과 시 자동 복구·결과 원장이 실행되지 않음 |
| NP-07 | P1 | 전달된 QA 정리 단계가 실제 팀원의 작업대·홈도 삭제 대상으로 잡음 |
| NP-08 | P1 | compose 학습기에 개인 홈이 연결되지 않아 터미널 전사를 읽지 못함 |
| NP-09 | P1 | CLI가 스테이징된 변경을 누락하고 성공 후 강제 동기화함 |
| NP-10 | P1 | 문서의 공개 터미널 주소를 그대로 설정하면 /term이 두 번 붙음 |
| NP-11 | P2 | 신규 설치 문서의 workbench 빌드 대상·프로필이 실제 compose에 없음 |
| NP-12 | P1 | 기존 QA가 컨테이너 0개를 정상으로 판정 |
| NP-13 | P2 | 프로필을 꺼도 채택 작업으로 영역·예시가 계속 학습됨 |
| NP-14 | P2 | Claude 토큰 교체·삭제가 기존 개인 컨테이너에 반영되지 않음 |
| NP-15 | P2 | 워처 배포 성공 후 learner는 이전 Python 코드를 계속 실행 |
| NP-16 | P2 | 롤백 헬스체크 실패도 reverted로 기록되고 CLI가 성공으로 표시 |
| NP-17 | P2 | 프로젝트명이 부분 일치하면 다른 프로젝트의 전사가 섞임 |
| NP-18 | P2 | 대리 대상 본인이 결과를 확인·채택할 기본 권한이 없음 |
| NP-19 | P2 | compose 구성에 기존 제품 미리보기 실행 환경이 전달되지 않음 |

**NP-01 · P1 · 일반 작업 수정 API로 채택 권한과 요청자 정보를 우회**

검증: 서버 제공 웹 커밋 · 원본 함수 모의 실행. 작업 작성자·검수자·관리자가 아닌 계정은 /api/workspace POST에서 403을 받는다. 같은 계정이 /api/tasks PATCH로 selection={decision:accept,by:원래작성자}, status=done, created_by_email을 보내면 200이며 값이 그대로 저장된다. 실제 DB 대신 메모리 저장소로 두 API를 비교했다.

영향: 남의 작업을 채택하거나 채택자를 위조할 수 있다. selection을 신뢰하는 학습 루프와 created_by_email을 사용하는 계정 선택에도 영향을 준다. 외부 비로그인 접근이 아니라 로그인된 일반 사용자 사이의 권한 문제다.

근거: [route.ts:126](E:/AI/qa/newplay-audit-20260916/server-platform/src/app/api/tasks/route.ts:126), [route.ts:158](E:/AI/qa/newplay-audit-20260916/server-platform/src/app/api/tasks/route.ts:158), [route.ts:69](E:/AI/qa/newplay-audit-20260916/server-platform/src/app/api/workspace/route.ts:69). 재현 항목: `task_patch_bypasses_workspace_decision_authorization`.

**NP-02 · P1 · 배포 범위 검사에서 삭제 파일이 빠져 보호 파일 삭제가 허용됨**

검증: 서버 제공 워처 커밋 · 임시 Git 저장소 재현. patch_files는 +++ b/ 행만 수집한다. 삭제 패치의 +++ /dev/null은 목록에 없다. token_mint.py 삭제와 worker.py 수정을 함께 보내면 files에는 worker.py만 남고 deploy가 성공한다. 임시 저장소에서 보호 파일이 실제로 사라졌음을 확인했다. 빌드·서비스 재기동은 모의 처리했다.

영향: 문서가 보장하는 “배포 장치 파일은 변경 불가”가 삭제 경로에서는 성립하지 않는다. 삭제가 커밋에도 포함되지 않아 작업 트리·이력·배포 결과가 달라진다.

근거: [platform_deploy.py:145](E:/AI/qa/newplay-audit-20260916/server-watcher/platform_deploy.py:145), [platform_deploy.py:419](E:/AI/qa/newplay-audit-20260916/server-watcher/platform_deploy.py:419). 재현 항목: `protected_file_deletion_bypasses_scope_guard`.

**NP-03 · P1 · 서로 다른 이메일이 같은 개인 컨테이너·홈으로 매핑됨**

검증: 로컬 gateway 소스 · 원본 함수 실행. qa.first@example.test와 qa-first@example.test가 모두 wb-qa-first-example-test로 변환된다. 길이가 40 이하인 이름에는 해시를 붙이지 않아 마침표·하이픈 등 구분자가 충돌한다.

영향: 두 사람이 같은 홈·tmux·작업 폴더를 공유한다. 먼저 만들어진 컨테이너의 Claude 토큰도 그대로 사용될 수 있어 “1인 1계정” 보장이 깨진다.

근거: [server.js:35](E:/AI/scripts/newplay/deploy/gateway/server.js:35), [server.js:61](E:/AI/scripts/newplay/deploy/gateway/server.js:61). 재현 항목: `distinct_emails_share_workbench`.

**NP-04 · P1 · 개인 터미널에서 도달 가능한 내부망에 무인증 배포 실행기와 DB가 있음**

검증: 전달된 compose 구성 정적 대조 + 서버 ops 원본의 localhost 모의 실행. workbench는 newplay_default에 연결되고 compose의 mongo·ops도 같은 기본 네트워크다. ops /run은 인증 없이 CLI 인자를 실행한다. Authorization 없는 요청이 로컬 모의 서버에서 200으로 전달됐다. mongo 실행 인자에도 인증 설정이 없다. ops에는 Docker 소켓이 마운트된다.

영향: 이 compose 그대로 배포하면 터미널 사용자가 웹의 관리자 검사를 거치지 않고 배포 실행기·DB에 접근할 수 있다. 호스트의 127.0.0.1 포트 바인딩은 컨테이너 사이의 접근을 막지 않는다. 실제 운영 네트워크·방화벽에서 공격을 시도하지 않았으며, 운영 적용 여부는 별도 확인 대상이다.

근거: [server.js:70](E:/AI/scripts/newplay/deploy/gateway/server.js:70), [docker-compose.yml:133](E:/AI/scripts/newplay/deploy/docker-compose.yml:133), [ops_server.py:65](E:/AI/qa/newplay-audit-20260916/server-watcher/ops_server.py:65). 재현 항목: `workbench_shares_backend_network; ops_accepts_command_without_auth`.

**NP-05 · P1 · 학습되는 검사 명령의 개행으로 추가 셸 명령이 통과**

검증: 서버 제공 워처 커밋 · 정규식 실제 실행. CHECK_RE가 npm run test\nprintf QA_UNEXPECTED_COMMAND라는 두 줄 문자열을 허용한다. 금지 문자 목록에 개행이 없고, workspace.run_checks는 해당 문자열을 bash -lc로 실행한다. 재현에서는 허용 판정만 확인하고 추가 명령은 실행하지 않았다.

영향: 전사에서 얻은 “검사 습관”에 검사 이외의 명령이 들어가 이후 대리 작업에서 실행될 수 있다. 기존 C2는 &&와 deploy만 시험해 이 경우를 놓친다.

근거: [profiles.py:36](E:/AI/qa/newplay-audit-20260916/server-watcher/profiles.py:36), [workspace.py:191](E:/AI/qa/newplay-audit-20260916/server-watcher/workspace.py:191). 재현 항목: `profile_allows_newline_second_command`.

**NP-06 · P1 · 빌드 시간 초과 시 자동 복구·결과 원장이 실행되지 않음**

검증: 서버 제공 워처 커밋 · 임시 Git 저장소 재현. 패치 적용·커밋 후 _build에서 TimeoutExpired를 발생시키면 예외가 deploy 밖으로 전파된다. 임시 저장소에서 HEAD가 새 커밋으로 남고 파일도 새 내용이며 원장 기록은 0건이었다.

영향: “실패하면 자동으로 이전 상태 복구”라는 인수인계 설명에 예외가 있다. 실제 빌드가 .next를 일부 덮은 시점이라면 서비스 장애와 CLI 결과 대기가 함께 발생할 수 있다.

근거: [platform_deploy.py:136](E:/AI/qa/newplay-audit-20260916/server-watcher/platform_deploy.py:136), [platform_deploy.py:433](E:/AI/qa/newplay-audit-20260916/server-watcher/platform_deploy.py:433). 재현 항목: `build_timeout_leaves_new_commit_without_rollback`.

**NP-07 · P1 · 전달된 QA 정리 단계가 실제 팀원의 작업대·홈도 삭제 대상으로 잡음**

검증: ZIP과 동일한 QA 스크립트 · 패턴 대조, 삭제 미실행. cleanup_qa는 wb-qa-* 컨테이너, wt/*qa-* 작업 폴더, home/*qa-* 홈을 삭제한다. 실제 업무 계정 예시 qa-engineer@example.com의 정상 작업대·홈도 전부 매칭된다. 이 정리 함수는 --only A로 실행해도 호출된다.

영향: “가짜 newplay.test 계정만 건드린다”는 안내와 다르다. 검사 실행만으로 정상 계정의 작업 디렉터리·설정·전사를 지울 수 있으므로 현재 QA 스크립트의 운영 실행을 안전하다고 판정할 수 없다.

근거: [qa-run.sh:169](E:/AI/scripts/newplay/handoff/ssyoung/qa/qa-run.sh:169), [qa-run.sh:180](E:/AI/scripts/newplay/handoff/ssyoung/qa/qa-run.sh:180). 재현 항목: `qa_cleanup_matches_real_user`.

**NP-08 · P1 · compose 학습기에 개인 홈이 연결되지 않아 터미널 전사를 읽지 못함**

검증: 전달된 compose와 서버 학습기 소스 대조. gateway는 DATA_ROOT/home을 사람별 /home/app에 연결한다. learner에는 git·tokens·transcripts만 마운트하고 home 마운트와 NEWPLAY_HOME_ROOT가 없다. learning.py는 /data/newplay/home을 찾는다. 기존 qa-learn.py는 /tmp/qa-home을 따로 만들어 환경변수를 덮어써서 이 배포 문제를 검사하지 않는다.

영향: compose 그대로 설치하면 실제 직접 모드의 명령·대화 전사가 프로필로 들어오지 않는다. 파일 변경은 git에서 일부 얻을 수 있어 학습이 완전히 작동하는 것으로 오인하기 쉽다.

근거: [docker-compose.yml:87](E:/AI/scripts/newplay/deploy/docker-compose.yml:87), [learning.py:207](E:/AI/qa/newplay-audit-20260916/server-watcher/learning.py:207), [qa-learn.py:28](E:/AI/scripts/newplay/handoff/ssyoung/qa/qa-learn.py:28). 재현 항목: `learner_has_no_home_mount`.

**NP-09 · P1 · CLI가 스테이징된 변경을 누락하고 성공 후 강제 동기화함**

검증: ZIP과 동일한 CLI · 임시 Git 저장소에서 실제 check 실행. git add로 스테이징한 수정이 있는 임시 저장소에 check를 실행하면 “git diff가 비어 있음”으로 종료 코드 0을 반환했다. Get-LocalPatch는 git diff만 사용한다. deploy 성공 후에는 git reset --hard와 git clean -fdq를 실행한다.

영향: 일반적인 에디터의 스테이징 작업이 배포에 포함되지 않는다. 스테이징된 변경과 별도의 미스테이징 변경이 섞인 경우, 보내지 않은 변경도 성공 후 강제 동기화에서 잃을 수 있다. 누락은 직접 재현했고 혼합 변경의 소실 경로는 코드로 확인했다.

근거: [newplay-hub.ps1:84](E:/AI/scripts/newplay/newplay-hub.ps1:84), [newplay-hub.ps1:184](E:/AI/scripts/newplay/newplay-hub.ps1:184). 재현 항목: `cli_misses_staged_changes`.

**NP-10 · P1 · 문서의 공개 터미널 주소를 그대로 설정하면 /term이 두 번 붙음**

검증: 서버 웹 원본 함수 실행 + 로컬 gateway·배포 문서 대조. README는 GATEWAY_PUBLIC_WS=wss://도메인/term을 지시한다. TerminalView는 설정값 뒤에 다시 /term?ticket=...를 붙여 /term/term으로 접속한다. gateway의 수신 경로는 /term이다.

영향: 안내대로 이전·설치한 공개 터미널은 연결되지 않는다. 기존 QA는 gateway 내부 ws://127.0.0.1:포트/term에 직접 접속하여 브라우저 URL 조립을 검사하지 않는다.

근거: [README.md:43](E:/AI/scripts/newplay/deploy/README.md:43), [TerminalView.tsx:48](E:/AI/qa/newplay-audit-20260916/server-platform/src/components/TerminalView.tsx:48), [server.js:142](E:/AI/scripts/newplay/deploy/gateway/server.js:142). 재현 항목: `documented_terminal_url_gets_duplicate_term`.

**NP-11 · P2 · 신규 설치 문서의 workbench 빌드 대상·프로필이 실제 compose에 없음**

검증: 배포 문서·YAML 파싱 대조. 문서 명령은 --profile build build workbench다. 실제 서비스 이름은 workbench-image, 프로필은 build-only다. 최초 up에서 해당 이미지는 기본 빌드 대상도 아니다.

영향: 문서 순서대로 새 서버를 설치하면 개인 작업대 이미지 준비가 완료되지 않는다. 이 PC에는 Docker 실행 파일이 없어 compose 명령 자체 실행은 하지 않았고 서비스 키·프로필을 파싱해 확인했다.

근거: [README.md:29](E:/AI/scripts/newplay/deploy/README.md:29), [docker-compose.yml:160](E:/AI/scripts/newplay/deploy/docker-compose.yml:160). 재현 항목: `documented_build_target_missing`.

**NP-12 · P1 · 기존 QA가 컨테이너 0개를 정상으로 판정**

검증: ZIP과 동일한 qa-run.sh · 외부 명령을 모두 모의 처리해 실행. docker compose ps가 빈 결과를 내도록 하고 웹 응답만 정상으로 제공하면 A1은 “컨테이너 전부 running (0개)” PASS, 최종 PASS 9 / FAIL 0 / SKIP 1 / exit 0이다. 서비스 수·필수 서비스·명령 성공 여부를 확인하지 않는다.

영향: 기존 “40개 통과”는 이양 완료의 근거로 충분하지 않다. C 그룹도 프로세스 종료 코드를 확인하지 않고 PASS/FAIL 문자열을 세며, E4는 백업 파일의 최신 날짜·복원 가능 여부 대신 목록 존재만 검사한다. 이번에 직접 재현한 것은 A1의 거짓 통과다.

근거: [qa-run.sh:54](E:/AI/scripts/newplay/handoff/ssyoung/qa/qa-run.sh:54), [qa-run.sh:128](E:/AI/scripts/newplay/handoff/ssyoung/qa/qa-run.sh:128), [qa-run.sh:201](E:/AI/scripts/newplay/handoff/ssyoung/qa/qa-run.sh:201). 재현 항목: `qa_passes_with_zero_containers`.

**NP-13 · P2 · 프로필을 꺼도 채택 작업으로 영역·예시가 계속 학습됨**

검증: 서버 워처 원본 함수 · 메모리 저장소 재현. enabled=false 프로필에 update_from_accepted를 호출하면 areas에 src/payment.ts:2가 추가되고 exemplars에도 작업이 들어간다. update_from_session의 비활성 검사와 달리 채택 경로에는 검사가 없다.

영향: 문서·화면의 “끄면 수집 중단”과 실제 동작이 다르다. 기존 C4는 세션 경로만 검사한다.

근거: [profiles.py:166](E:/AI/qa/newplay-audit-20260916/server-watcher/profiles.py:166), [learning.py:288](E:/AI/qa/newplay-audit-20260916/server-watcher/learning.py:288). 재현 항목: `disabled_profile_still_learns_accepted_task`.

**NP-14 · P2 · Claude 토큰 교체·삭제가 기존 개인 컨테이너에 반영되지 않음**

검증: gateway 원본 함수 · Docker 명령 모의 기록. ensureContainer는 새 컨테이너를 만들 때만 토큰을 환경변수로 넣는다. 기존 컨테이너는 docker start만 호출한다. 토큰 파일을 교체한 상황을 모의해도 inspect/start 외 명령이 없었다.

영향: 관리자가 토큰을 갱신해도 개인 터미널은 오래된 토큰을 계속 쓴다. 파일을 삭제해도 이미 주입된 자격이 컨테이너에 남는다. 사용자는 “토큰 있음” 표시와 실제 인증 결과가 다른 상태를 겪을 수 있다.

근거: [server.js:63](E:/AI/scripts/newplay/deploy/gateway/server.js:63), [server.js:79](E:/AI/scripts/newplay/deploy/gateway/server.js:79). 재현 항목: `existing_workbench_does_not_refresh_token`.

**NP-15 · P2 · 워처 배포 성공 후 learner는 이전 Python 코드를 계속 실행**

검증: 서버 배포 함수 모의 실행 + compose 구조 대조. learning.py·profiles.py는 watcher 편집 허용 범위이며 독립 learner도 import한다. _restart(WATCHER)가 실행한 명령은 docker restart newplay-watcher-1 하나였다.

영향: 학습 로직 변경을 정상 배포해도 learner 프로세스에는 반영되지 않아 웹·워처·학습기의 동작 버전이 달라진다.

근거: [platform_deploy.py:356](E:/AI/qa/newplay-audit-20260916/server-watcher/platform_deploy.py:356), [learner_main.py:14](E:/AI/qa/newplay-audit-20260916/server-watcher/learner_main.py:14), [docker-compose.yml:87](E:/AI/scripts/newplay/deploy/docker-compose.yml:87). 재현 항목: `watcher_deploy_does_not_restart_learner`.

**NP-16 · P2 · 롤백 헬스체크 실패도 reverted로 기록되고 CLI가 성공으로 표시**

검증: 서버 롤백 함수 모의 실행 + CLI 분기 대조. rollback_to의 헬스체크를 실패시켜도 원장 status는 reverted, healthy=false다. platform CLI는 reverted와 커밋·시각만 확인하고 healthy를 검사하지 않은 채 “되돌림”으로 출력한다. 빌드 실패 롤백에는 .next 백업 복원도 없다.

영향: 운영자가 복구 성공으로 오인할 수 있다. 첫 항목은 함수 재현, CLI의 성공 표시는 분기 코드 대조 결과이며 운영 롤백은 실행하지 않았다.

근거: [platform_deploy.py:491](E:/AI/qa/newplay-audit-20260916/server-watcher/platform_deploy.py:491), [newplay-hub.ps1:256](E:/AI/scripts/newplay/newplay-hub.ps1:256). 재현 항목: `failed_rollback_health_still_records_reverted`.

**NP-17 · P2 · 프로젝트명이 부분 일치하면 다른 프로젝트의 전사가 섞임**

검증: 서버 프로필 원본 함수 · 임시 전사 파일 재현. find_transcripts(project="web")가 -data-git-webstore-wt-... 아래의 전사 파일도 반환했다. 프로젝트 식별자를 폴더명의 부분 문자열로 검사한다.

영향: web/webstore처럼 겹치는 프로젝트 이름을 쓰면 담당 영역·검사 습관·지시 내용이 다른 프로젝트 프로필에 누적될 수 있다.

근거: [profiles.py:102](E:/AI/qa/newplay-audit-20260916/server-watcher/profiles.py:102). 재현 항목: `transcript_project_substring_collision`.

**NP-18 · P2 · 대리 대상 본인이 결과를 확인·채택할 기본 권한이 없음**

검증: 서버 웹 원본 API 함수 · 모의 요청. act_as=developer인 작업에서 developer가 작성자·지정 검수자·관리자가 아니면 채택 API는 403이다. 권한 검사 조회 필드에 act_as가 없다.

영향: 문서의 “담당자 본인이 채택해야 본인 예시로 학습”을 일반 팀원 권한에서 이행하기 어렵다. 전원 관리자 환경에서는 드러나지 않으며, 지정 검수자로 별도 등록하면 통과하는 조건부 문제다.

근거: [route.ts:65](E:/AI/qa/newplay-audit-20260916/server-platform/src/app/api/workspace/route.ts:65), [profiles.py:187](E:/AI/qa/newplay-audit-20260916/server-watcher/profiles.py:187). 재현 항목: `proxy_profile_owner_cannot_approve_by_default`.

**NP-19 · P2 · compose 구성에 기존 제품 미리보기 실행 환경이 전달되지 않음**

검증: 서버 웹 소스·Dockerfile·마운트 대조. /api/platform/preview는 HOME/newplay-preview/preview-build.sh를 로컬 실행한다. 전달된 web 이미지는 런타임만 설치하고 /srv/web만 마운트하며, 해당 스크립트·제품 체크아웃·미리보기 산출물 마운트가 없다. /api/platform/overview도 기본 Qdrant 주소·컬렉션이 기존 systemd 값이며 web의 compose 설정에서 새 값을 주지 않는다.

영향: 전달된 compose와 env 예시만으로 이전하면 기존 “수정안 미리보기”와 일부 플랫폼 상태 표시를 재현할 수 없다. 운영 서버에 수동 보완이 있을 가능성은 남아 있으며 실제 기능 호출은 수행하지 않았다.

근거: [route.ts:22](E:/AI/qa/newplay-audit-20260916/server-platform/src/app/api/platform/preview/route.ts:22), [Dockerfile.web:3](E:/AI/scripts/newplay/deploy/Dockerfile.web:3), [docker-compose.yml:37](E:/AI/scripts/newplay/deploy/docker-compose.yml:37), [route.ts:16](E:/AI/qa/newplay-audit-20260916/server-platform/src/app/api/platform/overview/route.ts:16). 재현 항목: `정적 구성 대조`.

**소유권 이양 판정 — 코드 결함과 별도로 확인할 것**

지정 ZIP은 편집권 전달용 문서·다운로더·QA 묶음이다. 그 자체에 웹·워처 전체 소스, 제품 저장소, DB, 지식베이스, 운영 비밀, 서버 자격이 들어 있는 완전한 독립 운영 패키지는 아니다. 이는 MANIFEST에도 별도 전달 대상으로 명시되어 있으므로 “ZIP 누락 사고”로 단정하지 않는다. 다만 이번 요청의 목표인 완전한 권한 이양에는 다음 증빙이 필요하다.

| 인수 항목 | 이번에 확인한 상태 | 완료를 입증할 자료/실행 |
|---|---|---|
| 플랫폼·워처 전체 소스와 의존성 | 서버 bundle 다운로드·웹 빌드 확인. 감사 사본에 보관 | 수신자가 자기 환경에서 두 bundle을 복제하고 같은 기준 커밋으로 실행 |
| 서버·Docker·관리자 접근 | 문서에 Windows User/WSL 및 Ubuntu compose 경로가 혼재. 실제 권한 인계 여부 미확인 | 실제 인계 대상 서버와 런타임 확정, 팀 관리자 계정으로 재기동·복구 실증 |
| Tailscale/도메인·Google OAuth 소유 | RUNBOOK에 기존 소유자 의존이 남는다고 명시 | 팀 소유 관리자·복구 권한, OAuth 클라이언트, 도메인·망 관리 권한 확인 |
| GitHub 제품 저장소·push/PR | 문서에는 deploy key 미등록 상태가 남아 있음. 실제 등록 여부 미확인 | 팀 저장소 접근 및 허용 브랜치 push/PR 실증 |
| Claude 개인 계정 | 토큰을 쓰는 경로는 검토. 실제 Claude 호출은 미실행 | 수신자 계정으로 직접·맡기기·대리 작업 각각 완료, 계정 귀속 확인 |
| 데이터·지식베이스·학습·개인 홈 백업 | 기존 백업은 BSON+소스 bundle 위주. compose용 전체 백업은 설명 수준이며 복원 결과 없음 | Mongo 컬렉션·인덱스, Qdrant, 프로젝트 git, 개인 홈/전사, 역할·설정·원장·필요 비밀의 복원 실증 |
| 구 소유자 의존 제거 | 문서상 구 SSH 키, env 관리자/허용 목록, OAuth·tailnet 의존 항목 존재 | 수신자 관리 접근을 검증한 뒤 구 계정·토큰·키의 실제 정리 여부 확인 |
| 인수 QA 원본 결과 | ZIP에는 40개 통과라는 설명이 있고 원본 last-run.txt는 없음 | 실행 시간·소스 커밋·설정·전체 출력·수신자 검수 기록과 연결 |

이 세션에서는 수신자를 대신해 계정 소유권을 이전하거나 권한을 변경하지 않았다. 서류의 “완료” 표시는 이번 QA의 완료 판정으로 전용하지 않았다.

**미실행 범위**

로그인 후 실제 브라우저 조작, Google OAuth 로그인 완료, 실제 Claude 토큰/한도/모델 호출, Linux Docker 스택 기동과 재부팅, 실서비스 배포·롤백·장애 복구, 백업에서 빈 서버 복원, 수신자의 GitHub 반출과 계정 소유권은 미검증이다. 현재 PC에는 Docker CLI가 없고, 운영 서비스 쓰기를 하지 않는 범위에서 진행했다. 특히 NP-07 때문에 전달된 qa-run.sh를 운영에서 그대로 재실행하지 않았다.

**검사 산출물**

- [findings.csv](E:/AI/qa/newplay-audit-20260916/findings.csv): 필터링 가능한 19개 지적 목록.
- [behavior-results.json](E:/AI/qa/newplay-audit-20260916/behavior-results.json), [web-behavior-results.json](E:/AI/qa/newplay-audit-20260916/web-behavior-results.json): 재현 결과. `observed=true`는 해당 결함/조건이 관찰되었다는 뜻이며 제품 정상 통과를 뜻하지 않는다. `syntax` 항목만 구문 정상 여부다.
- [run_audit.py](E:/AI/qa/newplay-audit-20260916/run_audit.py), [probe_web.cjs](E:/AI/qa/newplay-audit-20260916/probe_web.cjs): 임시 저장소·모의 DB·모의 명령으로 실행한 검사 코드.
- [qa-zero-containers-probe.txt](E:/AI/qa/newplay-audit-20260916/qa-zero-containers-probe.txt): 기존 QA의 0개 컨테이너 거짓 통과 원본 출력.
- [build.log](E:/AI/qa/newplay-audit-20260916/build.log), [build-status.json](E:/AI/qa/newplay-audit-20260916/build-status.json): 빌드 원본 출력과 해석.
- [public-http-results.json](E:/AI/qa/newplay-audit-20260916/public-http-results.json), [server-source-status.json](E:/AI/qa/newplay-audit-20260916/server-source-status.json): 운영 읽기 검사.
- [source-integrity.json](E:/AI/qa/newplay-audit-20260916/source-integrity.json), [zip-inventory.json](E:/AI/qa/newplay-audit-20260916/zip-inventory.json), [scope-counts.json](E:/AI/qa/newplay-audit-20260916/scope-counts.json): 원본 보존·ZIP·범위 증빙.
- local_newplay-inventory.json, server_web-inventory.json, server_watcher-inventory.json, related-files.txt: 파일별 목록·해시와 연계 참조 목록.
- platform.bundle / watcher.bundle 및 server-platform / server-watcher: GET으로 확보한 감사 기준 소스. 수신자 인수 패키지를 새로 완성하거나 기존 ZIP을 교체한 것은 아니다.
