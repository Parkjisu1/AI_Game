#!/bin/bash
# migrate-data.sh — 현재(systemd) 스택의 데이터를 compose 볼륨(DATA_ROOT)으로 옮긴다. 원본은 건드리지 않는다.
#   Mongo: pymongo BSON 덤프 → 컨테이너 mongo 에 복원   Qdrant: 스토리지 복사   git store·mirror·tokens·logs 복사
set -e
cd "$(dirname "$0")"
DATA_ROOT=${DATA_ROOT:-/data/newplay}
SRC_MONGO=${SRC_MONGO:-mongodb://127.0.0.1:27018/newteam?directConnection=true}
# pymongo 가 있는 파이썬 (현재 PC 는 워처 venv). 없으면 pip install pymongo 한 python3
PY=${PY:-$( [ -x $HOME/.hermes-newteam/watcher/venv/bin/python ] && echo $HOME/.hermes-newteam/watcher/venv/bin/python || echo python3 )}
sudo mkdir -p $DATA_ROOT/{mongo,qdrant,ollama,git,mirror,tokens,transcripts,logs,backups,preview}
sudo chown -R $(id -u):$(id -g) $DATA_ROOT
echo "== git store"; rsync -a --delete $HOME/work/ $DATA_ROOT/git/ 2>/dev/null || cp -a $HOME/work/. $DATA_ROOT/git/
echo "== mirror (윈도우 미러 → 리눅스 복사, ro 마운트용)"; [ -d /mnt/c/newplay/repos ] && rsync -a --delete /mnt/c/newplay/repos/ $DATA_ROOT/mirror/ || true
echo "== tokens"; cp -a $HOME/.hermes-newteam/claude-tokens/. $DATA_ROOT/tokens/ 2>/dev/null || true; chmod 700 $DATA_ROOT/tokens
if [ -d "$HOME/newplay-preview/webstore/.git" ]; then
  echo "== preview (전용 체크아웃·산출물)"
  rsync -a --exclude preview-build.sh "$HOME/newplay-preview/" "$DATA_ROOT/preview/"
fi
echo "== qdrant storage (컨테이너 정지 상태에서 복사)"; docker compose stop qdrant >/dev/null 2>&1 || true
sudo rsync -a --delete /var/lib/qdrant/storage/ $DATA_ROOT/qdrant/ && sudo chown -R 1000:1000 $DATA_ROOT/qdrant || true
docker compose start qdrant >/dev/null 2>&1 || true
echo "== mongo (BSON dump → restore)"
TMP=$(mktemp -d)
$PY - "$SRC_MONGO" "$TMP" <<'EOP'
import sys, os, bson
from pymongo import MongoClient
uri, out = sys.argv[1], sys.argv[2]
db = MongoClient(uri)["newteam"]
for name in sorted(db.list_collection_names()):
    with open(os.path.join(out, name + ".bson"), "wb") as f:
        n = 0
        for d in db[name].find():
            f.write(bson.encode(d)); n += 1
    print(f"  dump {name}: {n}")
EOP
MPORT=$(grep -E '^MONGO_PORT=' .env.compose 2>/dev/null | cut -d= -f2); MPORT=${MPORT:-27018}
$PY - "mongodb://127.0.0.1:$MPORT/newteam?directConnection=true" "$TMP" <<'EOP'
import sys, os, glob, bson
from pymongo import MongoClient
uri, src = sys.argv[1], sys.argv[2]
db = MongoClient(uri)["newteam"]
for p in sorted(glob.glob(os.path.join(src, "*.bson"))):
    name = os.path.basename(p)[:-5]
    docs = list(bson.decode_file_iter(open(p, "rb")))
    db[name].drop()
    if docs: db[name].insert_many(docs)
    print(f"  restore {name}: {len(docs)}")
EOP
rm -rf "$TMP"
echo MIGRATE_OK
