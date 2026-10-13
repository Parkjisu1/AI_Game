#!/bin/bash
# sync-src.sh — 빌드 컨텍스트(src/web, src/watcher)를 git 저장소에서 채운다. 이미 있으면 ff 갱신.
#   WEB_SRC / WATCHER_SRC: 원본 git 경로 또는 bundle 파일 (기본: 현재 PC 의 WSL 경로)
set -e
cd "$(dirname "$0")"
WEB_SRC=${WEB_SRC:-$HOME/projecthub-newteam}
WATCHER_SRC=${WATCHER_SRC:-$HOME/.hermes-newteam/watcher}
mkdir -p src
sync() { # name src
  local name=$1 src=$2 dst=src/$1
  if [ ! -d "$dst/.git" ]; then git clone -q "$src" "$dst"; echo "cloned $name: $(git -C $dst log --oneline -1 | cut -c1-70)"
  else
    git -C "$dst" fetch -q "$src" HEAD:refs/remotes/src/head
    if git -C "$dst" merge -q --ff-only refs/remotes/src/head 2>/dev/null; then echo "updated $name: $(git -C $dst log --oneline -1 | cut -c1-70)"
    elif [ "${SYNC_FORCE:-0}" = "1" ]; then git -C "$dst" reset -q --hard refs/remotes/src/head && echo "reset $name → $(git -C $dst log --oneline -1 | cut -c1-70)"
    else echo "$name: 갈라짐(compose 쪽에 배포 커밋이 있음). 원본이 진실이면 SYNC_FORCE=1 로 다시 실행"; exit 1; fi
  fi
}
sync web "$WEB_SRC"
sync watcher "$WATCHER_SRC"
# 비밀은 복사하지 않는다 — .env 는 deploy/.env.web / .env.watcher 로 따로.
cp src/watcher/requirements.lock ./requirements.lock 2>/dev/null || true
# 웹 의존성 + 빌드 (호스트에 node 가 있으면 여기서, 없으면 컨테이너에서 `docker compose run --rm web npm ci && npm run build`)
if command -v node >/dev/null; then
  # next build 는 페이지 데이터 수집 중 mongodb 모듈을 평가하므로 MONGODB_URI 가 있어야 한다(값은 아무거나). 나머지는 .env.web 에서.
  ( cd src/web && set -a && [ -f ../../.env.web ] && . ../../.env.web; set +a; export MONGODB_URI=${MONGODB_URI:-mongodb://mongo:27017/newteam?directConnection=true} NEXT_PUBLIC_APP_THEME=clean \
    && npm ci --no-audit --no-fund >/dev/null 2>&1 && npm run build >/tmp/newplay-web-build.log 2>&1 && echo "web build OK" ) || { echo "web build FAILED (see /tmp/newplay-web-build.log)"; exit 1; }
else
  echo "node 없음 — 컨테이너에서 빌드: docker compose run --rm web sh -c 'npm ci && npm run build'"
fi
echo SYNC_OK
