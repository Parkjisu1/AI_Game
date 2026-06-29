"""pixelforge_levels 컬렉션 점검 — 302건의 정체 파악."""
import os
from pymongo import MongoClient

db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
coll = db.pixelforge_levels

total = coll.count_documents({})
print(f"total docs: {total}")
print()

# 첫 5건 샘플 — 실제 fields 확인
print("--- first 5 docs (sample fields) ---")
for d in coll.find().limit(5):
    keys = sorted(d.keys())
    print(f"\n_id={d['_id']}")
    print(f"  keys: {keys}")
    print(f"  name:    {d.get('name')!r}")
    print(f"  width:   {d.get('width')!r}")
    print(f"  height:  {d.get('height')!r}")
    print(f"  symmetry:{d.get('symmetry')!r}")
    print(f"  palette: {d.get('palette')!r}")
    print(f"  png_filename: {d.get('png_filename')!r}")
    print(f"  created_at:   {d.get('created_at')!r}")

print()
print("--- field presence stats ---")
for f in ["name", "width", "height", "symmetry", "palette", "png_filename", "cells", "validation", "created_at"]:
    n = coll.count_documents({f: {"$exists": True}})
    print(f"  {f:18}: {n}/{total}")

# 우리가 만든 테스트 doc들만 분리
print()
print("--- our test docs (created_by_email contains aimed.xyz/gameberry) ---")
n_ours = coll.count_documents({"created_by_email": {"$in": [
    "hermes-self-test@aimed.xyz",
    "jisu.park@gameberry.co.kr",
]}})
print(f"  count: {n_ours}")

# 옛날 무관한 데이터?
print()
print("--- distinct created_by_email ---")
for e in coll.distinct("created_by_email"):
    cnt = coll.count_documents({"created_by_email": e})
    print(f"  {e!r}: {cnt}")
