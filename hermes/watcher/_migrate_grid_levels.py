"""우리가 만든 grid level doc만 pixelforge_grid_levels로 이동.

판별 기준: `cells` 필드가 있고 `chapter` 필드가 없음 (BalloonFlow 게임 레벨은
chapter 가짐 / 우리 grid level은 cells 가짐).
"""
import os
from pymongo import MongoClient

db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
src = db.pixelforge_levels
dst = db.pixelforge_grid_levels

filt = {"cells": {"$exists": True}, "chapter": {"$exists": False}}

n_match = src.count_documents(filt)
print(f"matching docs to migrate: {n_match}")

migrated = 0
for d in src.find(filt):
    # upsert into dst by _id (idempotent)
    dst.replace_one({"_id": d["_id"]}, d, upsert=True)
    src.delete_one({"_id": d["_id"]})
    migrated += 1
    print(f"  moved {d['_id']} ({d.get('name')!r})")

print(f"\ndone. migrated={migrated}")
print(f"pixelforge_levels       remaining: {src.count_documents({})}")
print(f"pixelforge_grid_levels  total:     {dst.count_documents({})}")
