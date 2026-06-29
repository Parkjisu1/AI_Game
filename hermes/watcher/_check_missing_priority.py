"""우선순위 필드 누락된 태스크 찾기."""
import os
from pymongo import MongoClient

db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
n_missing = db.pixelforge_tasks.count_documents({"priority": {"$exists": False}})
n_total = db.pixelforge_tasks.count_documents({})
print(f"missing priority: {n_missing}/{n_total}")
for t in db.pixelforge_tasks.find(
    {"priority": {"$exists": False}}, {"title": 1, "_id": 1}
).limit(10):
    tid = str(t["_id"])
    title = t.get("title", "")[:60]
    print(f"  {tid} {title}")
