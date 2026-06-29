"""Inspect a pipeline session — find anchor/category from CSV vs effective metaphors used in art."""
import os
import json
from pymongo import MongoClient
from bson import ObjectId
import sys

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ.get("MONGODB_DB", "aigame")]

session_id = sys.argv[1] if len(sys.argv) > 1 else "6a16606f09dcf35aa8d3d787"

sess = db["pixelforge_pipeline_sessions"].find_one({"_id": ObjectId(session_id)})
if not sess:
    print(f"Session {session_id} not found")
    sys.exit(1)

print(f"=== Session {session_id} ===")
print(f"  label    = {sess.get('label')}")
print(f"  stage    = {sess.get('stage')}")
print(f"  targets  = {sess.get('target_levels')[:10]}... ({len(sess.get('target_levels') or [])} lv)")
print(f"  preset   = {sess.get('gimmick_preset')}")
art = sess.get("art_job") or {}
print(f"  art job  = {art.get('job_id')} ({art.get('status')})")

# v43 job → out_dir → evaluation.json
v43 = db["pixelforge_v43_jobs"].find_one({"_id": ObjectId(art["job_id"])}) if art.get("job_id") else None
if not v43:
    print("No v43 job doc")
    sys.exit(1)
print(f"\n=== v43 job ===")
print(f"  status   = {v43.get('status')}")
print(f"  out_dir  = {v43.get('out_dir')}")
print(f"  csv_path = {v43.get('csv_path')}")
print(f"  pipeline_version = {v43.get('pipeline_version')}")

eval_path = v43.get("eval_path") or os.path.join(v43.get("out_dir", ""), "evaluation.json")
print(f"  eval_path = {eval_path}")

if os.path.exists(eval_path):
    with open(eval_path, "r", encoding="utf-8") as f:
        results = json.load(f)
    print(f"\n=== evaluation.json — {len(results)} levels ===")
    print(f"{'Lv':>4} | {'Anchor (CSV)':<20} | {'Category':<12} | {'Motif List':<50} | A meta -> B meta")
    print("-" * 160)
    for r in results[:20]:
        lv = r.get("level")
        anchor = r.get("metaphor") or ""
        cat = r.get("category") or ""
        ml = r.get("motif_list") or []
        ml_str = ", ".join(ml[:6])
        finals = r.get("final_candidates") or []
        a_meta = finals[0].get("effective_metaphor") if finals else ""
        b_meta = finals[1].get("effective_metaphor") if len(finals) > 1 else ""
        print(f"{lv:>4} | {anchor[:20]:<20} | {cat[:12]:<12} | {ml_str[:50]:<50} | {a_meta[:15]} -> {b_meta[:15]}")
    print(f"\n... (total {len(results)} levels)")
else:
    print(f"  evaluation.json missing at {eval_path}")
