"""최근 4팀 결과의 10배수 정규화 검증."""
import os, sys
from pymongo import MongoClient
from bson import ObjectId

ids = sys.argv[1:]
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]

print(f"{'team':16s} {'pattern':20s} {'counts':50s} {'all_10x':>8s}")
print("-" * 100)
for lid in ids:
    d = db.pixelforge_grid_levels.find_one({"_id": ObjectId(lid)})
    if not d:
        print(f"{lid}: NOT FOUND")
        continue
    pcc = d.get("validation", {}).get("color_counts") or {}
    counts_str = ", ".join(f"c{k}={v}" for k, v in sorted(pcc.items(), key=lambda kv: int(kv[0])))
    all_10x = all(int(v) % 10 == 0 for v in pcc.values())
    mark = "✓" if all_10x else "✗"
    print(f"{d.get('team_id', '?'):16s} {d.get('pattern_chosen', '?'):20s} {counts_str:50s} {mark:>8s}")
