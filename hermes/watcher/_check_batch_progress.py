"""batch 진행 상황 확인 — DB에 저장된 mood doc 수."""
import os
from pathlib import Path
from pymongo import MongoClient


def load_env():
    p = Path("/home/aimed/.hermes/watcher/.env")
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


load_env()
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
moods = ["warm", "cool", "pastel", "vivid"]
total = 0
for m in moods:
    n = db.pixelforge_grid_levels.count_documents({"mood": m})
    total += n
    print(f"  {m:8s}: {n:4d}")
print(f"  TOTAL   : {total:4d} / 2000")

recent = list(db.pixelforge_grid_levels.find(
    {"mood": {"$in": moods}}, {"mood": 1, "name": 1}
).sort("created_at", -1).limit(3))
print(f"\n  recent:")
for d in recent:
    name = d.get("name", "")
    mood = d.get("mood", "?")
    print(f"    {mood:8s} {name}")
