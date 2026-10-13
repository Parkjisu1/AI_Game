#!/bin/bash
# wsl-restore.sh — aimed-sub 에서 추출한 NewPlay 를 WSL(newplay 사용자)에 복원한다.
#   소스 2 트리(git bundle) · Mongo 19 컬렉션(BSON) · Qdrant 스냅샷 · 유닛 2개 · env 골격
set -e
. ~/.nvm/nvm.sh
EX=/mnt/c/newplay/export
cd ~

# ── 1) 소스
if [ ! -d ~/projecthub-newteam/.git ]; then git clone -q $EX/web.bundle ~/projecthub-newteam; fi
mkdir -p ~/.hermes-newteam/logs
if [ ! -d ~/.hermes-newteam/watcher/.git ]; then git clone -q $EX/watcher.bundle ~/.hermes-newteam/watcher; fi
echo "web=$(git -C ~/projecthub-newteam log --oneline -1) | watcher=$(git -C ~/.hermes-newteam/watcher log --oneline -1)"

# ── 2) 파이썬 venv (워처)
cd ~/.hermes-newteam/watcher
if [ ! -x venv/bin/python ]; then python3 -m venv venv; fi
venv/bin/pip install -q -r requirements.lock
echo "venv=$(venv/bin/python -c 'import pymongo,qdrant_client;print(pymongo.version)' 2>/dev/null || venv/bin/python -c 'import pymongo;print(pymongo.version)')"

# ── 3) Mongo 복원 (BSON → newteam)
venv/bin/python - <<'EOP'
import os, glob, bson
from pymongo import MongoClient
db = MongoClient("mongodb://127.0.0.1:27018/?directConnection=true")["newteam"]
for path in sorted(glob.glob("/mnt/c/newplay/export/mongo-bson/*.bson")):
    name = os.path.basename(path)[:-5]
    docs = []
    with open(path, "rb") as f:
        docs = list(bson.decode_file_iter(f))
    db[name].drop()
    if docs:
        db[name].insert_many(docs, ordered=True)
    print(f"  {name}: {len(docs)}")
EOP

# ── 4) Qdrant 스냅샷 복원
if ! curl -s http://127.0.0.1:6343/collections/newplay_code | jq -e '.result.points_count > 0' >/dev/null 2>&1; then
  curl -s -X POST "http://127.0.0.1:6343/collections/newplay_code/snapshots/upload?priority=snapshot" \
    -H "Content-Type: multipart/form-data" -F "snapshot=@$EX/newplay_code.snapshot" | jq -c .
fi
echo "qdrant points=$(curl -s http://127.0.0.1:6343/collections/newplay_code | jq .result.points_count)"

# ── 5) env 골격 (값은 비움 — 비밀은 별도 주입)
if [ ! -f ~/.hermes-newteam/watcher/.env ]; then
cat > ~/.hermes-newteam/watcher/.env <<'EOC'
MONGODB_URI=mongodb://127.0.0.1:27018/newteam?directConnection=true
MONGODB_DB=newteam
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
NEWPLAY_QDRANT_URL=http://127.0.0.1:6343
NEWPLAY_KB_COLLECTION=newplay_code
NEWPLAY_DEFAULT_PROJECT=webstore
HERMES_WORKER_SLOTS=2
HERMES_LEASE_MINUTES=30
EOC
chmod 600 ~/.hermes-newteam/watcher/.env
fi
if [ ! -f ~/projecthub-newteam/.env.production ]; then
cat > ~/projecthub-newteam/.env.production <<EOC
AUTH_URL=https://newplay.tailf6f809.ts.net
AUTH_TRUST_HOST=true
AUTH_SECRET=$(openssl rand -base64 32)
MONGODB_URI=mongodb://127.0.0.1:27018/newteam?directConnection=true
MONGODB_DB=newteam
ALLOWED_EMAILS=
ADMIN_EMAILS=
PORT=3000
HERMES_INTERNAL_API_KEY=$(openssl rand -hex 24)
SLACK_SIGNING_SECRET=
AUTH_GOOGLE_ID=
AUTH_GOOGLE_SECRET=
OPENAI_API_KEY=
NEXT_PUBLIC_APP_THEME=clean
BQ_PROJECT_ID=
BQ_SA_KEY_JSON=
EOC
chmod 600 ~/projecthub-newteam/.env.production
fi

# ── 6) 웹 의존성 + 빌드
cd ~/projecthub-newteam
npm ci --no-audit --no-fund >/dev/null 2>&1 || npm install --no-audit --no-fund >/dev/null
npm run build > /tmp/web-build.log 2>&1 && echo "web build OK" || { echo "web build FAILED"; tail -20 /tmp/web-build.log; exit 1; }

# ── 7) 사용자 서비스 유닛 (경로만 이 홈으로)
mkdir -p ~/.config/systemd/user
NODE_BIN=$(dirname "$(nvm which 20)")
sed -e "s#/home/aimed#/home/newplay#g" -e "s#/home/newplay/.nvm/versions/node/v[0-9.]*/bin#$NODE_BIN#g" \
  $EX/units/projecthub-newteam.service > ~/.config/systemd/user/projecthub-newteam.service
sed -e "s#/home/aimed#/home/newplay#g" -e "s#/home/newplay/.nvm/versions/node/v[0-9.]*/bin#$NODE_BIN#g" \
  $EX/units/hermes-newteam.service > ~/.config/systemd/user/hermes-newteam.service
systemctl --user daemon-reload
echo "units: $(grep -c newplay ~/.config/systemd/user/projecthub-newteam.service) $(grep -c newplay ~/.config/systemd/user/hermes-newteam.service)"
echo RESTORE_OK
