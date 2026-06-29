"""batch 결과 빠른 확인."""
import os, sys
from pymongo import MongoClient

mood = sys.argv[1] if len(sys.argv) > 1 else "warm"
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
n = db.pixelforge_grid_levels.count_documents({"mood": mood})
print(f"{mood}: {n} docs")
docs = list(db.pixelforge_grid_levels.find({"mood": mood}).sort("created_at", -1).limit(10))
for d in docs:
    sc = d.get("validation", {}).get("score", {})
    name = d.get("name", "")[:40]
    pat = (d.get("pattern_chosen") or "")[:30]
    is10 = sc.get("is_10_mult")
    sym = float(sc.get("sym_best", 0))
    scat = sc.get("scatter", 0)
    comp = float(sc.get("composite", 0))
    print(f"  {str(d['_id'])[-8:]} {name:40s} {pat:30s} 10x={is10} sym={sym:.2f} scat={scat:3d} comp={comp:.0f}")
