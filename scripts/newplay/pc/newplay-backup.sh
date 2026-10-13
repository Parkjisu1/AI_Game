#!/bin/bash
# newplay-backup.sh — newteam DB 전 컬렉션을 BSON 으로 덤프해 Windows 쪽(C:\newplay\backups)에 날짜별로 보관. 14일 보존.
set -e
OUT=/mnt/c/newplay/backups/$(date +%Y%m%d)
mkdir -p "$OUT"
/home/newplay/.hermes-newteam/watcher/venv/bin/python - "$OUT" <<'EOP'
import sys, os, bson
from pymongo import MongoClient
db = MongoClient("mongodb://127.0.0.1:27018/?directConnection=true")["newteam"]
out = sys.argv[1]
for name in sorted(db.list_collection_names()):
    with open(os.path.join(out, name + ".bson"), "wb") as f:
        for d in db[name].find():
            f.write(bson.encode(d))
EOP
git -C /home/newplay/projecthub-newteam bundle create -q "$OUT/web.bundle" --all
git -C /home/newplay/.hermes-newteam/watcher bundle create -q "$OUT/watcher.bundle" --all
find /mnt/c/newplay/backups -maxdepth 1 -mindepth 1 -type d -mtime +14 -exec rm -rf {} +
echo "backup ok $OUT $(du -sh "$OUT" | cut -f1)"
