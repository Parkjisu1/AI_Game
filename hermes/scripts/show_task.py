from dotenv import load_dotenv
load_dotenv("/home/aimed/.hermes/watcher/.env")
import os, sys
from pymongo import MongoClient
from bson import ObjectId

task_id = sys.argv[1] if len(sys.argv) > 1 else "69e9812af825851947d10ad7"
c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ["MONGODB_DB"]]
t = db.pixelforge_tasks.find_one({"_id": ObjectId(task_id)})
if not t:
    print("태스크 없음")
    raise SystemExit(1)
print("=== 원본 ===")
print("title:", t.get("title"))
print("description:", repr(t.get("description")))
print("priority:", t.get("priority"))
print("related_levels:", t.get("related_levels"))
print("status:", t.get("status"))
print("image_base64:", "있음" if t.get("image_base64") else "없음")
print()
print("=== 코멘트 ===")
for c_ in t.get("comments") or []:
    print(f"[{c_.get('author')}]:", (c_.get("text") or "")[:200])
    print("---")
