"""P3a — 완료 task에 best_score 태깅 (hermes_team_scores reviewer max). good-result RAG의 전제."""
import os

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/aimed/.hermes/watcher/.env")
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]

best = {}  # task_id(str) -> max reviewer score
for s in db.hermes_team_scores.find({"role": {"$regex": "reviewer$"}}, {"task_id": 1, "score": 1}):
    tid = s.get("task_id")
    sc = s.get("score")
    if tid and sc is not None:
        best[str(tid)] = max(best.get(str(tid), 0), float(sc))

tagged = good = 0
for tid, sc in best.items():
    try:
        oid = ObjectId(tid)
    except Exception:
        continue
    r = db.pixelforge_tasks.update_one({"_id": oid}, {"$set": {"best_score": sc}})
    if r.matched_count:
        tagged += 1
        if sc >= 80:
            good += 1
print(f"best_score 태깅: {tagged}개 | good(≥80): {good}개")
print("good 임베딩 보유:", db.pixelforge_tasks.count_documents({"best_score": {"$gte": 80}, "embedding": {"$exists": True}}))
