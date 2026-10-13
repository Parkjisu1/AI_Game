# NewPlay 재감사 — 아키텍처·구조·실효성

검사일: 2026-09-16 KST. 대상: 현재 전달 ZIP, 실제 WSL 서버의 두 실행 스택, 운영 설정, 로컬 NewPlay 제작물.

**판정: 아직 v2 전체 기능 및 독립 운영의 이양 완료를 승인할 수 없다.** 정상 작동하는 기반과 수정 반영은 확인했지만, 공개 서비스 연결·작업 보존·배포 원자성·권한 회수·복구 범위에 미해결 문제가 있다. 이번 기록은 QA이며 제품 코드·전달 ZIP·운영 설정·데이터를 수정하지 않았다. 이전 제 수정에서 남아 있던 경계와 이후 전달본 변경의 회귀를 함께 기록한다.

## 검사 기준과 결과

- ZIP: `newplay-hub-ssyoung.zip`, 166,756 bytes, SHA256 `31dd2350282aaff753ba7458c8319992c676d6a63259406dbbd2b767865bbe24`.
- 서버 웹 HEAD: `ec9a83b2c9744b93c938b6a17ad6dc3a0705bf62`.
- Compose watcher HEAD: `6f06ac733038987e80c014f48eeb50c0aaaf146c`; systemd watcher HEAD: `c82a5f0fa6c1d1491e5d8007a16968c4aa918096`. 커밋 이력은 다르지만 Python 22개 내용은 같다.
- 기존 44개 회귀 조건을 현재 서버 코드/설정 및 최신 ZIP CLI 기준으로 재검사: **43 통과, 1 실패**. Python 29, 웹/게이트웨이 9 통과; CLI 5 통과·1 실패. 문서·보조 스크립트 관련 일부 Python 조건은 현재 로컬 파일도 참조한다. 이것을 로그인 브라우저 및 실제 계정의 종단간 44개 검증으로 해석하면 안 된다.
- 새 행동 재현 12개: Python 9, 웹 권한 2, 호스트 worktree prune 1. 모두 해당 실패 조건을 재현했다. 재현 스크립트의 `PASS`는 **결함이 재현됐다는 뜻**인 항목도 있으므로 정상 기능 검사 통과와 합산하지 않았다.
- 정적 확인: 서버 Python 44개 AST 검사(두 스택 각 22개), 현재 웹 TypeScript `tsc --noEmit --incremental false`, 게이트웨이 `node --check`, ZIP PowerShell 2개 구문 검사 통과.
- 확인 사항 **16건: P1 9건, P2 7건**. 코드 재현, 현 운영 설정, 조건부 잠재 문제를 아래에서 구분한다. P1은 이양 전에 우선 해결할 사항이며 모두 현재 진행 중 장애라는 뜻은 아니다.

## 실제 아키텍처

```mermaid
flowchart TB
  User[팀 사용자 / PowerShell] --> Funnel[공개 HTTPS :443]
  Funnel --> OldWeb[systemd 웹 :3000]
  OldWeb --> OldDB[(Mongo :27018)]
  OldWorker[systemd watcher] --> OldDB
  OldWorker --> OldKB[(Qdrant :6343 / Ollama :11434)]
  OldWeb -. 터미널 경로 없음 .-> Missing[/gateway/term 404]
  QA[qa-run.sh auto] --> NewWeb[Compose 웹 :3100]
  NewWeb --> NewDB[(Compose Mongo :27019)]
  NewWeb --> Ops[ops / 배포 저장소 / Docker socket]
  Watcher[watcher + learner] --> NewDB
  Watcher --> NewKB[(Compose Qdrant / Ollama)]
  Gateway[gateway :3101] --> Workbench[개인 workbench / 별도 네트워크]
  Gateway --> NewDB
  Backup[일일 백업] --> OldDB
  Backup --> OldSources[systemd 소스 bundle]
```

v2의 웹·실행기·학습기·배포기·터미널 게이트웨이 분리는 역할상 타당하다. 개인 작업대의 별도 네트워크, UID 정합성, 개인 홈/토큰 분리, ops 인증 및 워처/학습기 동시 재기동도 이전보다 개선됐다.

그러나 공개 진입점과 QA 스택이 다르고 데이터베이스도 갈라져 있다. 같은 소스 버전이어도 같은 서비스 상태가 아니다. 배포는 공유 작업 트리를 여러 요청이 동시에 바꾸고, 학습은 UI에서 수정 가능한 작업 메타데이터를 신뢰하며, 실패 작업의 격리가 없다. 이 세 경계가 구조적으로 약하다. 컨테이너가 모두 running이고 HTTP가 200이어도 사용자 결과물 보존·학습 진행·복구 가능성은 별도로 확인해야 한다.

## 확인 사항 목록

| ID | 우선순위 | 검증 성격 | 내용 |
|---|---|---|---|
| RA-01 | P1 | 운영 실측 | 공개 서비스와 v2 QA 대상이 서로 다른 스택·DB다 |
| RA-02 | P1 | 운영 실측 | 현재 공개 주소에서 개인 터미널에 도달할 경로가 없다 |
| RA-03 | P1 | 격리 재현 | 최신 ZIP CLI가 배포 대기 중 추가 수정한 파일을 지운다 |
| RA-04 | P1 | 격리 재현 | 한 배포의 실패 복구가 동시에 성공한 다른 배포를 없앤다 |
| RA-05 | P1 | 격리 재현 | 제품 코드 적용 경로에는 삭제 파일 범위 검사 우회가 남아 있다 |
| RA-06 | P1 | 격리 재현 | 일반 사용자가 작업의 실행 메타데이터를 위조하고 학습 대상 경로를 바꿀 수 있다 |
| RA-07 | P1 | 운영 실측·구성 대조 | 미리보기와 제품 적용에 필요한 원본 트리가 준비돼 있지 않다 |
| RA-08 | P1 | 운영 실측 | 백업 성공은 v2 전체 복구를 보장하지 않는다 |
| RA-09 | P2 | 격리 재현 | 재작업 결과 패치가 이전 차수의 변경을 누락한다 |
| RA-10 | P2 | 격리 재현 | 아무 일 없이 재접속해도 이전 개인 커밋을 다시 학습한다 |
| RA-11 | P2 | 격리 재현 | 앞의 실패 작업 세 개가 뒤의 학습을 계속 막는다 |
| RA-12 | P2 | 조건부 격리 재현 | 프로젝트 간 학습 데이터 분리 경계가 두 경로에서 깨진다 |
| RA-13 | P2 | 조건부 격리 재현 | 개인 토큰이 없을 때 공용 CLI 로그인으로 내려가는 경로가 남아 있다 |
| RA-14 | P2 | 조건부 격리 재현 | QA 정리의 호스트 worktree prune이 다른 작업 메타데이터를 제거할 수 있다 |
| RA-15 | P1 | 격리 재현 | 허용 사용자 삭제가 기존 API 토큰 권한을 회수하지 않는다 |
| RA-16 | P2 | 전달물·문서 대조 | 최신 전달 코드와 이전 검사 증거·운영 설명이 일치하지 않는다 |

## RA-01 · 공개 서비스와 v2 QA 대상이 서로 다른 스택·DB다

**P1 · 운영 실측**

관찰: Tailscale 공개 입구는 127.0.0.1:3000(systemd)으로 간다. v2 Compose 웹은 3100, Mongo는 27019다. 공개 API 작업 목록의 ID·갱신시각 지문은 3000과 같고 3100과 다르다. QA auto는 Compose를 선택하고, 공개 주소 검사는 /login 응답만 확인한다.

영향: Compose에서 터미널·프로필·배포가 통과해도 사용자가 접속하는 서비스의 통과를 증명하지 못한다. 두 DB의 원장과 토큰 폐기 상태도 다르다. 병행 검증 구성 자체는 문서에 명시돼 있으나, v2 이양 완료 근거로 쓰면 안 된다.

검증: SSH 읽기 전용 설정 조회 및 내부 키를 출력하지 않는 GET 비교. 두 watcher의 커밋은 다르지만 Python 22개 내용은 동일했다. 코드 미적용 문제와 실행 환경 차이를 구분했다.

완료 판정 기준: 최종 운영 스택과 데이터 기준을 하나로 지정하고, 실제 공개 주소에서 같은 DB·원장·터미널을 사용함을 검증해야 한다. 전환 시 데이터 차이를 처리한 기록이 필요하다.

근거: [tailscale-routing.json:11](E:/AI/qa/newplay-reaudit-20260916/tailscale-routing.json:11) · [server-functional-read.sh.stdout:7](E:/AI/qa/newplay-reaudit-20260916/server-functional-read.sh.stdout:7) · [server-config/server-qa-run.sh:45](E:/AI/qa/newplay-reaudit-20260916/server-config/server-qa-run.sh:45)

## RA-02 · 현재 공개 주소에서 개인 터미널에 도달할 경로가 없다

**P1 · 운영 실측**

관찰: 공개 systemd 웹에는 GATEWAY_PUBLIC_WS 설정이 없다. TerminalView는 /gateway/term으로 연결하지만 공개 프록시에 해당 경로 전달 규칙이 없고 인증 우회 키를 사용한 읽기 요청도 404다. Compose 웹 설정은 ws://127.0.0.1:3101이다.

영향: 공개 HTTPS 사이트의 원격 사용자는 개인 터미널을 사용할 수 없다. Compose 주소도 사용자 PC의 loopback을 가리키고 평문 WebSocket이므로 공개 전환만으로 해결되지 않는다.

검증: 서버 환경의 관련 키만 조회, 프록시 설정 확인, 세 주소의 /gateway/term 응답 및 클라이언트 URL 생성 코드 대조. 실제 사용자 WebSocket 접속은 수행하지 않았다.

완료 판정 기준: 실제 팀 주소의 wss 경로를 게이트웨이로 전달하고, 로그인한 원격 브라우저에서 연결·재접속·일회용 티켓 거절을 확인해야 한다.

근거: [server-web/src/components/TerminalView.tsx:14](E:/AI/qa/newplay-reaudit-20260916/server-web/src/components/TerminalView.tsx:14) · [server-functional-read.sh.stdout:9](E:/AI/qa/newplay-reaudit-20260916/server-functional-read.sh.stdout:9) · [server-state.sh.stdout:49](E:/AI/qa/newplay-reaudit-20260916/server-state.sh.stdout:49)

## RA-03 · 최신 ZIP CLI가 배포 대기 중 추가 수정한 파일을 지운다

**P1 · 격리 재현**

관찰: 새 -AfterDeploy 분기가 서버 bundle을 받은 뒤 git reset --hard refs/remotes/server/head를 수행한다. 배포 제출 후 같은 추적 파일을 더 수정하면 배포 완료 시 그 추가 수정이 사라진다.

영향: 배포가 성공해도 사용자 작업이 유실된다. 기존 충돌 문제를 없애면서 NP-09의 수정 보존 조건이 다시 깨졌다. 신규 미추적 파일이 남는 것만으로 추적 파일 보존을 보장하지 못한다.

검증: 최신 ZIP의 PowerShell을 실제 실행하고 임시 Git·localhost 모의 API로 제출 후 편집을 삽입했다. 6개 검사 중 해당 1개 실패, 5개 통과. 운영 배포는 하지 않았다.

완료 판정 기준: 제출 시점과 그 이후 변경을 구분해 보존하고, 서버 변경과 충돌하면 사용자 수정이 복구 가능한 형태로 남아야 한다. 현재 실패한 회귀 검사가 통과해야 한다.

근거: [handoff/newplay-hub.ps1:152](E:/AI/qa/newplay-reaudit-20260916/handoff/newplay-hub.ps1:152) · [cli-results.txt:3](E:/AI/qa/newplay-reaudit-20260916/cli-results.txt:3) · [test_cli_handoff.py:62](E:/AI/qa/newplay-reaudit-20260916/test_cli_handoff.py:62)

## RA-04 · 한 배포의 실패 복구가 동시에 성공한 다른 배포를 없앤다

**P1 · 격리 재현**

관찰: 동일 저장소에 대한 배포 전체의 잠금이 없다. A 배포가 커밋 후 빌드 대기하는 동안 B 배포가 성공하면, 뒤늦게 실패한 A의 _restore가 A 시작 전 SHA로 reset --hard한다.

영향: B는 원장에 deployed로 남지만 실제 B 변경은 사라진다. 빌드 산출물 백업 경로도 공유돼 복구와 현재 상태가 어긋날 수 있다.

검증: 실제 platform_deploy 코드를 두 스레드와 임시 Git에서 실행했다. 빌드·서비스 재기동·원장만 모의 처리했다. B 성공 응답 후 B=1이 B=0으로 돌아가고 HEAD가 최초 SHA가 됨을 확인했다.

완료 판정 기준: 같은 대상의 검사·커밋·빌드·재기동·복구를 프로세스 간 직렬화해야 한다. 동시 요청과 실패를 섞어도 성공 건의 커밋·원장·산출물이 일치해야 한다.

근거: [server-watcher/platform_deploy.py:423](E:/AI/qa/newplay-reaudit-20260916/server-watcher/platform_deploy.py:423) · [server-watcher/platform_deploy.py:370](E:/AI/qa/newplay-reaudit-20260916/server-watcher/platform_deploy.py:370) · [behavior-results.json:16](E:/AI/qa/newplay-reaudit-20260916/behavior-results.json:16)

## RA-05 · 제품 코드 적용 경로에는 삭제 파일 범위 검사 우회가 남아 있다

**P1 · 격리 재현**

관찰: platform_deploy는 이전 경로까지 검사하도록 수정됐지만 제품용 change_ledger.patch_files는 +++ b/...만 읽는다. 허용된 front-end 파일 수정과 금지 영역 infra 파일 삭제를 섞으면 dry_run이 ok=true를 반환한다.

영향: 제품 적용 도구의 허용 디렉터리 경계가 삭제 패치에는 강제되지 않는다. 적용 시 허용 범위 밖 작업 파일을 삭제할 수 있고, 파일 목록·커밋 관리에서도 삭제가 빠진다.

검증: 임시 제품 저장소에서 infra/protected.txt 삭제와 front-end/view.txt 수정을 만든 뒤 실제 dry_run 실행. 검사 결과 files에는 front-end만 있었고 out_of_scope는 비어 있었다.

완료 판정 기준: 제품 경로에도 삭제·이름 변경·바이너리 패치의 양쪽 경로 검사를 적용하고, 허용된 삭제는 실제 커밋 및 되돌리기까지 확인해야 한다.

근거: [server-watcher/change_ledger.py:63](E:/AI/qa/newplay-reaudit-20260916/server-watcher/change_ledger.py:63) · [behavior-results.json:3](E:/AI/qa/newplay-reaudit-20260916/behavior-results.json:3)

## RA-06 · 일반 사용자가 작업의 실행 메타데이터를 위조하고 학습 대상 경로를 바꿀 수 있다

**P1 · 격리 재현**

관찰: tasks PATCH는 selection·소유자와 일부 상태 필드를 보호하지만 worktree, touched_files, proposed_patch, run_id는 일반 로그인 사용자가 다른 사람 작업에도 기록할 수 있다. 학습기의 reindex_files는 worktree와 파일명을 결합한 뒤 경로 이탈 검사 없이 읽는다.

영향: 검수용 패치 변조와 지식베이스 오염이 가능하다. 채택·학습이 실행되는 조건에서는 학습기 권한으로 읽을 수 있는 작업 폴더 밖 파일도 색인될 수 있다. 실제 비밀 유출이 발생했다는 뜻은 아니다.

검증: 실제 TypeScript 핸들러를 모의 DB에서 실행해 무관한 사용자 PATCH가 200 및 DB 기록으로 이어짐을 확인했다. 별도 Python 재현에서 ../outside.txt의 합성 표식이 색인 payload에 들어갔다. 실서버 파일·토큰은 읽지 않았다.

완료 판정 기준: 클라이언트 수정 필드를 명시하고 워커 전용 메타데이터는 신뢰된 경로에서만 기록해야 한다. 색인은 승인된 worktree 내부의 정규화된 파일만 읽고 ..·절대경로·심볼릭 링크 이탈을 거부해야 한다.

근거: [server-web/src/app/api/tasks/route.ts:129](E:/AI/qa/newplay-reaudit-20260916/server-web/src/app/api/tasks/route.ts:129) · [server-watcher/learning.py:161](E:/AI/qa/newplay-reaudit-20260916/server-watcher/learning.py:161) · [web-results.json:48](E:/AI/qa/newplay-reaudit-20260916/web-results.json:48) · [behavior-results.json:51](E:/AI/qa/newplay-reaudit-20260916/behavior-results.json:51)

## RA-07 · 미리보기와 제품 적용에 필요한 원본 트리가 준비돼 있지 않다

**P1 · 운영 실측·구성 대조**

관찰: 두 스택의 기본 미리보기 위치에서 webstore/.git 및 serve/index.html이 없다. Compose 미리보기에는 전용 script가 마운트됐지만 제품 checkout·Yarn 파일·node_modules는 없다. ops에는 제품 적용용 저장소/미리보기 볼륨도 없다.

영향: 스크립트 존재·python/flock 설치·비로그인 401만으로는 미리보기 빌드나 제품 적용을 완주할 수 없다. change_ledger 기본 SOURCE_REPO 역시 없는 홈 미리보기 경로를 참조한다.

검증: 실제 경로 존재 여부와 Compose 마운트, preview-build.sh 시작 경로 및 change_ledger 기본값을 읽기 전용으로 대조했다. 운영 파일을 만드는 preview/apply 명령은 실행하지 않았다.

완료 판정 기준: 운영 스택에 제품 원본·의존성·적용 작업 트리를 명시적으로 준비하고, 합성 패치의 검사→제품 적용→미리보기 렌더링→되돌리기까지 별도 검증해야 한다.

근거: [server-routing.sh.stdout:40](E:/AI/qa/newplay-reaudit-20260916/server-routing.sh.stdout:40) · [server-config/preview-build.sh:40](E:/AI/qa/newplay-reaudit-20260916/server-config/preview-build.sh:40) · [server-config/docker-compose.yml:119](E:/AI/qa/newplay-reaudit-20260916/server-config/docker-compose.yml:119) · [server-watcher/change_ledger.py:38](E:/AI/qa/newplay-reaudit-20260916/server-watcher/change_ledger.py:38)

## RA-08 · 백업 성공은 v2 전체 복구를 보장하지 않는다

**P1 · 운영 실측**

관찰: 실행 중인 백업 스크립트는 Mongo 27018과 systemd 웹·워처 bundle만 저장한다. Compose Mongo 27019, /data/newplay/git 및 개인 홈, Qdrant 상태, 운영 설정을 모두 복원하는 구성이 아니다.

영향: v2로 사용한 작업·프로필·원장 및 개인 작업을 현재 백업만으로 복구할 수 없다. BSON을 임시 DB에 읽어 넣는 검증은 해당 덤프의 가독성을 보여주지만 서비스 전체 복원 증거는 아니다.

검증: 백업 service 성공, 최신 파일 존재, 실제 백업 script 내용과 v2 볼륨 목록 대조. 기존 공개 systemd DB의 백업 자체가 실패했다는 뜻은 아니다. 전체 복원 훈련은 미실시다.

완료 판정 기준: 최종 운영 스택의 데이터·소스·설정·개인 작업을 포괄하는 백업 명세를 만들고, 격리 서버에서 복원 후 로그인·작업·색인·터미널까지 확인해야 한다.

근거: [server-functional-read.sh.stdout:40](E:/AI/qa/newplay-reaudit-20260916/server-functional-read.sh.stdout:40) · [server-data.sh.stdout:288](E:/AI/qa/newplay-reaudit-20260916/server-data.sh.stdout:288) · [server-config/docker-compose.yml:14](E:/AI/qa/newplay-reaudit-20260916/server-config/docker-compose.yml:14)

## RA-09 · 재작업 결과 패치가 이전 차수의 변경을 누락한다

**P2 · 격리 재현**

관찰: worktree를 재사용하고 매 차수 커밋하지만 stage_and_diff는 현재 HEAD 이후 staged 변경만 반환한다. 실행기는 이 diff로 카드의 proposed_patch와 touched_files를 덮어쓴다.

영향: 1차 A 파일, 2차 B 파일을 고치면 브랜치에는 A+B가 있으나 최종 전달 패치에는 B만 남는다. 채택·제품 적용·학습이 전체 결과와 달라질 수 있다.

검증: 실제 workspace 함수와 임시 Git로 두 차수를 구성. branch_changes=[a.py,b.py], latest_card_files=[b.py] 확인. 실행기의 저장 경로와 연결 검토했다.

완료 판정 기준: 원래 기준 커밋에서 최종 상태까지의 누적 패치를 전달해야 한다. 수정 차수 사이에 되돌림·삭제·기준 브랜치 변경을 섞어도 최종 결과와 같아야 한다.

근거: [server-watcher/workspace.py:127](E:/AI/qa/newplay-reaudit-20260916/server-watcher/workspace.py:127) · [server-watcher/hermes_executor.py:670](E:/AI/qa/newplay-reaudit-20260916/server-watcher/hermes_executor.py:670) · [behavior-results.json:27](E:/AI/qa/newplay-reaudit-20260916/behavior-results.json:27)

## RA-10 · 아무 일 없이 재접속해도 이전 개인 커밋을 다시 학습한다

**P2 · 격리 재현**

관찰: 개인 브랜치는 계속 재사용되지만 gateway 세션에 접속 시점 base_rev가 없다. 학습기는 main과의 merge-base부터 HEAD까지 전체 커밋을 매 세션 집계한다.

영향: 두 번째 빈 세션도 첫 세션의 파일을 다시 담당 영역으로 반영한다. 작업량·담당 영역 가중치가 재접속 횟수에 따라 부풀어 오른다. 다른 사람 최근 커밋을 배제한 F-06 수정만으로는 해결되지 않는다.

검증: 과거 커밋 하나가 있는 개인 브랜치에서 실제 process_session을 두 번 실행했다. 두 번째는 신규 전사·커밋이 없어도 같은 src/one.py가 추출됐다.

완료 판정 기준: 접속 시점 또는 직전 처리 지점의 커밋·전사 범위를 기록해 동일 활동을 중복 집계하지 않아야 한다. 빈 재접속으로 프로필 값이 증가하지 않아야 한다.

근거: [server-config/gateway-server.js:170](E:/AI/qa/newplay-reaudit-20260916/server-config/gateway-server.js:170) · [server-watcher/learning.py:244](E:/AI/qa/newplay-reaudit-20260916/server-watcher/learning.py:244) · [behavior-results.json:41](E:/AI/qa/newplay-reaudit-20260916/behavior-results.json:41)

## RA-11 · 앞의 실패 작업 세 개가 뒤의 학습을 계속 막는다

**P2 · 격리 재현**

관찰: learning_loop는 learned_at이 없는 채택 작업에서 매번 limit(3)만 가져온다. 실패한 작업에는 learn_error만 기록하고 재시도 시각·횟수·격리 상태를 적용하지 않는다.

영향: 앞 세 작업이 계정·파일·네트워크 문제로 계속 실패하면 뒤의 정상 작업이 무기한 미처리로 남을 수 있다. 컨테이너 health는 정상이어도 학습 실효성은 멈춘다.

검증: 실제 루프에 모의 작업 5개를 주고 앞 3개 실패를 고정했다. 두 순환의 시도 순서는 0,1,2,0,1,2였고 3,4는 실행되지 않았다. 실서버 현재 대기열은 비어 있었다.

완료 판정 기준: 실패 작업의 재시도 간격·상한 또는 별도 실패 상태를 두고 정상 작업의 처리 기회를 보장해야 한다.

근거: [server-watcher/learning.py:278](E:/AI/qa/newplay-reaudit-20260916/server-watcher/learning.py:278) · [behavior-results.json:70](E:/AI/qa/newplay-reaudit-20260916/behavior-results.json:70)

## RA-12 · 프로젝트 간 학습 데이터 분리 경계가 두 경로에서 깨진다

**P2 · 조건부 격리 재현**

관찰: 전사 폴더 매칭에서 web_store와 web-store가 같은 이름으로 정규화되고 실제 JSON cwd를 다시 검증하지 않는다. 색인 교체의 삭제 필터는 path만 사용하고 project는 제외한다.

영향: 해당 이름 조합을 사용하면 다른 프로젝트 전사가 선택된다. 여러 프로젝트가 같은 지식 컬렉션을 쓰면 동일 파일 경로의 다른 프로젝트 청크를 삭제할 수 있다. 현재 활성 프로젝트 하나에서 실제 혼입이 발생했다는 주장은 아니다.

검증: web-store cwd 전사를 web_store로 조회해 선택됨을 확인했다. 실제 reindex_files가 만든 Qdrant 삭제 요청에 project 조건이 없음을 모의 HTTP로 확인했다.

완료 판정 기준: 정확한 프로젝트/작업 경로 기준으로 전사를 선택하고, 색인 삭제·조회·갱신 모두 같은 프로젝트 범위를 적용해야 한다.

근거: [server-watcher/profiles.py:88](E:/AI/qa/newplay-reaudit-20260916/server-watcher/profiles.py:88) · [server-watcher/learning.py:159](E:/AI/qa/newplay-reaudit-20260916/server-watcher/learning.py:159) · [behavior-results.json:92](E:/AI/qa/newplay-reaudit-20260916/behavior-results.json:92) · [behavior-results.json:56](E:/AI/qa/newplay-reaudit-20260916/behavior-results.json:56)

## RA-13 · 개인 토큰이 없을 때 공용 CLI 로그인으로 내려가는 경로가 남아 있다

**P2 · 조건부 격리 재현**

관찰: NEWPLAY_CLAUDE_SHARE=0, DEFAULT=0이어도 candidates 끝에 ("", None)을 무조건 붙인다. 실행기는 이 후보에서 개인 OAuth 지정 없이 CLI를 호출하며 공유 HOME/환경 인증이 사용될 여지가 있다.

영향: 나중에 운영자가 공용 HOME에 로그인하거나 공용 API 키를 넣으면 개인 토큰 없는 사용자의 요청이 그 계정으로 실행될 수 있다. 문서의 1인 1계정 보장과 다르다.

검증: 개인·공용 토큰 없는 모의 환경에서도 기본 인증 후보가 반환됨을 확인했다. 현재 조사한 서버의 공용 credential 및 watcher API/OAuth 환경 인증은 없었고 실제 타 계정 호출은 확인되지 않았다.

완료 판정 기준: 개인 인증이 없으면 명시적으로 실패하고, 공용 인증은 별도 허용된 운영 모드에서만 선택해야 한다. 실제 계정 호출 없이 후보 선택 검사로 회귀를 감시할 수 있다.

근거: [server-watcher/claude_pool.py:129](E:/AI/qa/newplay-reaudit-20260916/server-watcher/claude_pool.py:129) · [server-watcher/agent_team.py:143](E:/AI/qa/newplay-reaudit-20260916/server-watcher/agent_team.py:143) · [behavior-results.json:86](E:/AI/qa/newplay-reaudit-20260916/behavior-results.json:86)

## RA-14 · QA 정리의 호스트 worktree prune이 다른 작업 메타데이터를 제거할 수 있다

**P2 · 조건부 격리 재현**

관찰: 개별 worktree 제거는 컨테이너 경로로 수정됐지만, 바로 뒤의 worktree prune은 여전히 호스트에서 실행된다. 다른 worktree의 gitdir에도 컨테이너 절대 경로가 기록돼 호스트에서는 없는 폴더로 보인다.

영향: 기본 정리 유예 기간보다 오래된 항목은 실제 작업 파일이 살아 있어도 메타데이터가 제거될 수 있다. QA 계정 한 개의 정리가 오래된 팀원 작업에 영향을 주는 조건부 결함이다.

검증: 임시 Git worktree를 만들고 gitdir만 컨테이너 전용 경로로 기록한 뒤 100일 전 시각을 설정했다. 실제 git worktree prune 실행 후 다른 작업 파일은 남고 해당 메타데이터는 제거됐다. 운영 prune은 실행하지 않았다.

완료 판정 기준: 정리는 같은 경로 공간을 보는 컨테이너 안에서 수행하거나 이번 QA가 만든 정확한 메타데이터만 다뤄야 한다. 오래된 다른 사용자 worktree가 보존되는 검사가 필요하다.

근거: [server-config/server-qa-run.sh:202](E:/AI/qa/newplay-reaudit-20260916/server-config/server-qa-run.sh:202) · [source-checks.json:889](E:/AI/qa/newplay-reaudit-20260916/source-checks.json:889)

## RA-15 · 허용 사용자 삭제가 기존 API 토큰 권한을 회수하지 않는다

**P1 · 격리 재현**

관찰: 관리 API DELETE는 allowed_users에서 이메일만 지운다. 배포 API는 활성 토큰의 이메일을 찾은 뒤 현재 허용 목록을 다시 검사하지 않는다. JWT 세션도 로그인 시점의 허용 판정에 의존한다.

영향: DB 허용 목록에서 제거한 사용자가 기존 토큰으로 제품 API를 계속 사용할 수 있다. 소유권 이양·퇴사·권한 회수에서 기대한 차단이 이루어지지 않는다. 관리자 권한까지 새로 얻는 문제는 아니다.

검증: 실제 DELETE 및 apply GET 핸들러를 모의 DB/ops에서 연결했다. 허용 목록 삭제 성공 후에도 같은 사용자의 토큰으로 제품 이력 요청이 200이고 ops까지 도달했다. JWT 지속은 코드 검토 근거다.

완료 판정 기준: 사용자 비활성화 시 토큰·세션을 함께 회수하거나 매 요청 현재 접근 권한을 검증해야 한다. 허용 목록에서 삭제한 뒤 기존 토큰과 세션이 모두 거절되는지 확인해야 한다.

근거: [server-web/src/app/api/admin/allowed-users/route.ts:82](E:/AI/qa/newplay-reaudit-20260916/server-web/src/app/api/admin/allowed-users/route.ts:82) · [server-web/src/app/api/platform/apply/route.ts:100](E:/AI/qa/newplay-reaudit-20260916/server-web/src/app/api/platform/apply/route.ts:100) · [server-web/src/auth.ts:81](E:/AI/qa/newplay-reaudit-20260916/server-web/src/auth.ts:81) · [web-results.json:53](E:/AI/qa/newplay-reaudit-20260916/web-results.json:53)

## RA-16 · 최신 전달 코드와 이전 검사 증거·운영 설명이 일치하지 않는다

**P2 · 전달물·문서 대조**

관찰: 루트 scripts/newplay/newplay-hub.ps1과 ZIP CLI는 다르다. 이전 회귀 검사 경로는 루트 CLI를 가리키므로 최신 ZIP의 -AfterDeploy 회귀를 검사하지 않는다. 전달 문서에는 이전 aimed-sub·공용 계정·OpenAI 임베딩 설명과 PC 이관·개인 계정·Ollama 설명이 함께 남아 있다.

영향: 인수자가 어느 소스·DB·스택·인증 방식을 기준으로 운영해야 하는지 잘못 판단할 수 있다. 과거 44개 통과 기록은 수정된 ZIP의 보존 동작까지 검증한 증거가 아니다.

검증: ZIP SHA256을 고정해 별도 추출하고 그 CLI로 재검사했다. 운영 환경은 PC WSL/Ollama/newplay_code_m3인데 문서 구성표에는 이전 서버/컬렉션/계정 의존이 남아 있음을 대조했다.

완료 판정 기준: 전달 ZIP·소스 commit·대상 스택·검사 도구 경로·실행 결과를 하나의 manifest로 묶어야 한다. 현재 운영 절차와 역사 기록을 구분하고 오래된 안내는 현재 명령으로 오인되지 않게 해야 한다.

근거: [handoff/OWNERSHIP-TRANSFER.md:25](E:/AI/qa/newplay-reaudit-20260916/handoff/OWNERSHIP-TRANSFER.md:25) · [handoff/newplay-hub.ps1:41](E:/AI/qa/newplay-reaudit-20260916/handoff/newplay-hub.ps1:41) · [handoff/fixes/verification/test_cli.py:54](E:/AI/qa/newplay-reaudit-20260916/handoff/fixes/verification/test_cli.py:54)

## 정상으로 재확인한 범위

- 원본 서버에 NP 수정 커밋이 적용돼 있고 두 watcher 코드가 일치한다. 실행 중 Compose 8개와 기존 systemd 웹/워처를 확인했다.
- 일반 사용자의 채택 필드·소유자 위조와 무관한 사용자의 검수 결정을 막는 기존 수정은 동작한다. 다만 RA-06의 워커 필드 경계는 별개다.
- 개인 식별자의 구두점/도메인 충돌 방지, 토큰 변경 시 작업대 재생성, 작업대의 별도 네트워크 지정, 웹→ops 인증 키 전달은 현 서버 소스로 재확인했다. 현재 살아 있는 개인 workbench는 0개이므로 실제 컨테이너 네트워크 차단 시험을 이번에 반복한 것은 아니다.
- 공개 API 비로그인 GET 8개가 401, 루트 화면이 로그인으로 307을 반환했다. 존재하지 않는 API 경로도 인증에 먼저 걸릴 수 있으므로 401 자체로 기능 존재를 판정하지 않았다.
- Compose Qdrant의 newplay_code_m3는 green, 7,176 points이고 Ollama에는 bge-m3:latest가 있다. 이 값이 현재 소스와 완전히 동기화되었거나 답변 품질이 충분하다는 증거는 아니다.
- 최근 백업 service 성공과 파일 존재를 확인했다. 현재 두 DB에 미처리 채택 학습·종료 세션 대기열은 없었다.

## 실효성과 이양 준비도

| 사용자 흐름 | 이번 판정 |
|---|---|
| 비로그인 접근 차단 | 읽기 요청에서 확인 |
| 로그인 후 작업 보드·회의장·프로필 화면 | 사용자 OAuth 세션으로 렌더링 미검증 |
| 개인 터미널 | 현재 공개 경로 장애 조건 확인(RA-02) |
| AI에 맡기기/대리하기 → 실제 결과 완주 | 실제 팀 계정 미등록 상태라 미검증 |
| 반복 수정 → 전체 결과 패치 | 누락 재현(RA-09) |
| 채택 → 지식/개인 프로필 갱신 | 경로 신뢰·중복 집계·대기열 문제가 남음 |
| 플랫폼/워처 CLI 배포·되돌리기 | 기존 기본 경로 검사는 통과하나 로컬 변경 보존·동시 배포 실패 |
| 제품 패치 적용·미리보기 | 저장소 준비 및 배포 경계가 부족함 |
| 운영자 없이 장애 복구 | 전체 복원 미검증, v2 백업 범위 누락 |
| 계정/권한 완전 이양 | 사용자 제거의 토큰 회수 경계와 외부 자원 명의 이전 확인 필요 |

실측한 두 개인 토큰 디렉터리의 `*.token`은 각각 0개였고, 조사한 공유 CLI credential 및 Compose watcher API/OAuth 환경 인증도 없었다. 유료 모델 호출은 하지 않았다. 따라서 “실제 AI 작업이 현 팀원 계정으로 끝까지 된다”는 판정을 내리지 않는다. 이는 Claude 쪽에서도 남겼던 실계정 검증 공백과 일치한다.

Claude가 보고한 기존 API 토큰 4개 폐기는 systemd DB의 당일 revoked 4개와 부합한다. Compose DB의 당일 폐기 수는 0이다. 기존 토큰 재발급·추가 폐기·로그인은 이번 QA에서 수행하지 않았다. 필요 시 어느 DB의 어느 토큰을 처리하는지부터 고정해야 한다. 토큰 평문은 수집하거나 보고서에 남기지 않았다.

권한 이양은 코드 ZIP만으로 끝나지 않는다. PC/OS 관리자, Tailscale 공개 입구, Google OAuth 프로젝트, GitHub 저장소/배포 키, 팀원의 모델 계정, 백업 보관 위치의 소유·복구 담당이 실제 인수자에게 넘어갔는지는 별도 확인이 필요하다. 이는 이번에 외부 서비스의 명의를 바꾸라는 요청으로 해석하지 않았다.

## 검사의 한계와 재실행

이번 범위는 NewPlay의 운영 구조와 핵심 사용자 흐름 전체를 대상으로 한 재감사다. 웹 소스 176파일과 API 70개를 목록화했으나, 남아 있는 게임팀 BQ·이미지·음성·게임 API의 모든 동작과 모든 브라우저 조합까지 완전 검증한 것은 아니다. 관련 없는 서비스를 새로 개발하거나 기능을 확대하지 않았다.

원격에서는 설정/프로세스/컨테이너 정보, Git archive, DB 조회, GET만 수행했다. 상태를 생성·정리하는 서버 qa-run.sh, 실제 배포/재기동, 모델 실행, 토큰 발급·폐기, 복원 명령은 실행하지 않았다. 따라서 기존 “서버 QA 40 통과”는 전달받은 주장으로 보존하고, 이번 측정과 섞지 않는다.

현재 소스에서 검사한 결과는 `coverage.json`, 원격 근거는 `server-*.sh.stdout` 및 `tailscale-routing.json`, 상세 코드 재현은 아래 파일에 있다. 서버 snapshot은 로컬 재현에만 사용한다.

```powershell
python -B -m pytest -q -p no:cacheprovider qa/newplay-reaudit-20260916/test_server_regressions.py
python -B -m pytest -q -p no:cacheprovider qa/newplay-reaudit-20260916/test_cli_handoff.py
python -B qa/newplay-reaudit-20260916/behavior_probes.py
node qa/newplay-reaudit-20260916/test_web_server.cjs
```

이 스크립트들은 현 작업 환경의 Python/Node 의존성 및 기존 QA 보조 코드에 의존한다. 독립 실행용 새 인수 패키지로 포장한 것은 아니다. CLI 재현은 현재 코드에서 실패하는 것이 정상이며, 웹/행동 재현의 일부 PASS는 위에 명시한 결함 재현 성공이다.

원본 무결성: QA 시작 시 해시를 저장한 318개 파일을 다시 대조했다. 변경 0개, 누락 0개. 결과는 [integrity.json](integrity.json)에 있다. 이번에 추가한 것은 이 재감사 디렉터리의 보고서·증거·재현 코드뿐이다.
