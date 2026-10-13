# NewPlay Hub — compose 배포 (v2 단계 A~D)

한 줄: `sync-src.sh` 로 소스를 채우고, `.env.*` 를 채우고, `docker compose up -d --build`. 데이터는 `DATA_ROOT`(기본 `/data/newplay`) 아래 볼륨.

```
deploy/
├── docker-compose.yml        mongo · qdrant · ollama · web · watcher · learner · ops · gateway (8) — 개인 작업대(workbench)는 gateway 가 사람마다 동적으로 띄운다
├── gateway/                  터미널 게이트웨이 (티켓 검증 → 개인 컨테이너 `wb-<사람>` → tmux, 유휴 정지, 세션 기록)
├── Dockerfile.workbench      개인 작업대 이미지 (Claude Code CLI + tmux + 개발 도구, HOME 은 사람별 볼륨)
├── Dockerfile.web            node 20 런타임 (소스는 볼륨 /srv/web)
├── Dockerfile.watcher        python 3.12 + node 20 + Claude Code CLI + git + docker CLI (watcher/learner/ops 공용)
├── sync-src.sh               src/web, src/watcher 를 git 에서 채우고 웹 빌드
├── migrate-data.sh           현재(systemd) 스택 데이터 → DATA_ROOT (mongo BSON, qdrant, git store, mirror, tokens)
├── .env.compose.example      포트·DATA_ROOT (검증 시 3100/27019/6353/11435, 운영 시 기본)
├── .env.web.example          웹 비밀 (AUTH_*, ADMIN_EMAILS …)
└── .env.watcher.example      워처 비밀·설정
```

## 처음 띄우기 (사무실 Ubuntu 22.04+, Docker Engine + compose 플러그인)

```bash
git clone <이 폴더가 든 저장소> && cd deploy
cp .env.compose.example .env.compose && cp .env.web.example .env.web && cp .env.watcher.example .env.watcher   # 값 채우기
WEB_SRC=<웹 git 또는 bundle> WATCHER_SRC=<워처 git 또는 bundle> ./sync-src.sh
sudo mkdir -p /data/newplay && sudo chown $USER /data/newplay
docker compose --env-file .env.compose up -d --build
docker compose --env-file .env.compose exec ollama ollama pull bge-m3
./migrate-data.sh            # 이전 서버 데이터가 있으면. 없으면 생략(빈 상태로 시작)
docker compose --env-file .env.compose --profile build-only build workbench-image   # 개인 작업대 이미지
docker compose --env-file .env.compose ps            # 8개 running
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:${WEB_PORT:-3000}/login   # 200
```

## 배포 도구(newplay-hub.ps1)와의 관계
웹의 `/api/platform/apply` 는 `NEWPLAY_OPS_URL` 이 있으면 **ops 컨테이너**에 HTTP 로 넘긴다. 웹과 ops는 `.env.web`의 `HERMES_INTERNAL_API_KEY`로 인증한다. ops 는 소스 볼륨에 `git apply` → web 컨테이너 안에서 `npm run build` → 재기동 → 헬스체크 → 실패 시 자동 복구. 워처 배포는 watcher와 learner를 함께 재기동한다.

## 공개 입구
운영: Caddy(또는 팀 리버스 프록시)가 `web:3000` 을 팀 도메인으로. 검증(WSL2): 기존 Funnel 이 127.0.0.1:3000 을 가리키므로 compose 웹은 3100 으로 띄워 공존 → 검증 끝나면 포트를 바꿔 교체.

## 개인 터미널·프로필·대리 모드 (단계 B~D)

> **꼭 지킬 두 가지.** ① 작업대 컨테이너는 호스트 사용자 uid 로 떠야 한다(`WORKBENCH_USER`, 기본 `HOST_UID:HOST_GID`). root 로 뜨면 공유 저장소의 `.git` 이 root 소유가 되어 워처가 작업 폴더를 못 만들고 맡기기·대리 모드가 전부 멈춘다. ② `gateway/server.js` 를 고쳤으면 `docker compose build gateway` 로 **이미지를 다시 만들어야** 반영된다(`up -d` 만으로는 옛 코드가 돈다).
> 공개로 쓸 때는 `GATEWAY_PUBLIC_WS` 를 **`wss://<도메인>/term`** 으로 두고 리버스 프록시가 게이트웨이로 넘긴다. 검증용 `ws://127.0.0.1:3101` 은 서버 본체에서만 열리고, 암호화도 없어 접속 티켓이 평문으로 지나간다.
- `/terminal` → 웹이 짧은 수명의 서명 티켓을 발급 → gateway 가 검증하고 그 사람의 컨테이너를 띄운다. 컨테이너 안 HOME 은 `DATA_ROOT/home/<사람>` 이라 로그인·설정·전사가 사람마다 분리된다.
- 유휴 `WORKBENCH_IDLE_MIN` 분(결정값 10)이 지나면 컨테이너만 멈춘다. tmux 세션과 작업 내용은 볼륨에 남아 재접속 시 이어진다.
- 세션이 끝나면 learner 가 전사를 읽어 `person_profiles` 를 채운다(영역·검사 명령). `NEWPLAY_HOME_ROOT` 가 전사 위치다(컨테이너 기본 `/data/newplay/home`).
- 대리 모드는 그 프로필을 프롬프트에 넣고 실행한다. 담당자 본인이 채택할 때만 그 사람의 예시로 쌓인다.
- Claude 계정은 1인 1계정이다. 공용 토큰(`_default`)은 기본으로 무시하며, 쓰려면 워처 환경에 `NEWPLAY_CLAUDE_DEFAULT=1` 이 필요하다.

2026-09-16 재감사 수정: 개인 작업대는 `newplay_workbench` 네트워크만 사용하며 DB·ops의 기본 네트워크에 붙이지 않는다. 토큰 교체·삭제는 다음 터미널 접속 때 컨테이너 재생성으로 반영된다. 개인 식별자는 `정규화 이메일 앞 27자-SHA256 앞 12자`로 gateway와 learner가 동일하게 계산한다. 충돌할 수 있는 옛 이름의 홈·작업 폴더는 자동 삭제·재사용하지 않는다. 기존 설치에서 적용할 때는 옛 작업대의 접속을 종료하고 컨테이너를 정지한 뒤, 소유자를 확인한 데이터만 새 홈·작업 폴더로 옮긴다. 충돌한 홈은 소유자 확인 없이 합치지 않는다.

## 기존 제품 미리보기 이전

API·정적 서빙·빌드 스크립트는 모두 `NEWPLAY_PREVIEW_ROOT=/data/preview`를 사용한다. compose는 `DATA_ROOT/preview`와 `../preview-build.sh`를 연결하며 웹 이미지에 Python과 flock을 포함한다. `migrate-data.sh`는 기존 `~/newplay-preview`의 전용 체크아웃과 산출물도 복사한다.

새 서버라면 **미리보기 전용** 제품 저장소를 `DATA_ROOT/preview/webstore`에 clone하고, 해당 체크아웃의 `front-end`에서 저장소에 포함된 Yarn으로 의존성을 설치한다. 업무용 작업 폴더를 여기에 연결하지 않는다(미리보기 빌드가 이 전용 트리의 패치를 되돌리기 때문).

```bash
docker compose --env-file .env.compose exec -w /data/preview/webstore/front-end web node .yarn/releases/yarn-4.17.0.cjs install --immutable
docker compose --env-file .env.compose exec web bash /data/preview/preview-build.sh
```

## 재부팅
모든 서비스 `restart: unless-stopped`. Docker 가 부팅 시 자동 시작되면 전부 복귀한다. Windows 업데이트 문제는 호스트가 Ubuntu 이면 없다.

## 백업
`DATA_ROOT` 아래를 통째로(야간 cron: mongo dump + qdrant snapshot + git bundle → 다른 디스크/S3). 예시는 `pc/newplay-backup.sh` 를 컨테이너 경로로 바꿔 쓴다.
