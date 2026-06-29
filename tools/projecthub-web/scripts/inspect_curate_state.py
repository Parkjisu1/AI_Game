"""Check whether B curation actually works for latest session."""
import os
import json
import sys
from pymongo import MongoClient
from bson import ObjectId

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ.get("MONGODB_DB", "aigame")]

# 최근 v43 job
job = list(db["pixelforge_v43_jobs"].find({}).sort([("created_at", -1)]).limit(3))
for j in job:
    print(f"--- Job {j['_id']} status={j.get('status')} ---")
    print(f"  out_dir = {j.get('out_dir')}")
    print(f"  curated = {j.get('curated_at') is not None}")
    if j.get("curations"):
        print(f"  curations = {j.get('curations')}")
    if j.get("curation_results"):
        print(f"  curation_results [first 5]:")
        for r in j["curation_results"][:5]:
            print(f"    Lv {r.get('level')} label={r.get('label')} ok={r.get('ok')} err={r.get('error','')}")
    print()

# 최근 pipeline_sessions
print("=== Recent pipeline sessions ===")
for s in db["pixelforge_pipeline_sessions"].find({}).sort([("created_at", -1)]).limit(5):
    art = s.get("art_job", {})
    print(f"  {s['_id']} stage={s.get('stage')} curations={list((s.get('curations') or {}).items())[:5]}")
