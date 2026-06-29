"""priority 필드 누락된 태스크에 'medium' 기본값 채움."""
import os
from datetime import datetime
from pymongo import MongoClient

db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
res = db.pixelforge_tasks.update_many(
    {"priority": {"$exists": False}},
    {"$set": {"priority": "medium", "updated_at": datetime.utcnow().isoformat()}},
)
print(f"matched={res.matched_count} modified={res.modified_count}")
