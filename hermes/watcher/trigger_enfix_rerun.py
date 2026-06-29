#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trigger_enfix_rerun.py — pipeline/route.ts POST 흐름을 그대로 재현해 재생성 트리거.
- session + v43_job 생성 + latest CSV로 input.csv 작성 → v43_runner --job-id 가 읽어감.
- 패치된 gen_43(영어 메타포 매핑)으로 다양하게 재생성됨. UI /agents/batches Pipeline에 노출.
- 원래 job(6a338488)의 동일 target_levels/params 그대로.
"""
import os, datetime, sys
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/home/aimed/.hermes/watcher/.env")
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
EMAIL = "jisu.park@gameberry.co.kr"
TARGET = [4,5,7,14,18,20,21,23,27,30,48,50,51,52,59,65,70,72,76,78,81,88,92,100,
          123,137,156,163,178,200,203,222,262,263]

csv = db.pixelforge_csv_versions.find_one({"is_latest": True})
if not csv or not csv.get("csv_text"):
    print("ERROR: latest CSV (csv_text) 없음", file=sys.stderr); sys.exit(1)

sess = db.pixelforge_pipeline_sessions.insert_one({
    "created_at": now, "updated_at": now, "created_by_email": EMAIL,
    "label": "[EN-fix 재생성] geometric 4-300, 34개", "target_levels": TARGET,
    "art_mode": "v47", "auto_advance": False, "gimmick_preset": "pf_grounded",
    "n_seeds": 10, "n_final": 2, "csv_version_id": str(csv["_id"]),
    "csv_version_label": f'{csv.get("version")} {csv.get("label")}',
    "stage": "art_running",
    "stage_history": [{"stage": "art_running", "at": now, "by": EMAIL}],
})
sid = str(sess.inserted_id)

job = db.pixelforge_v43_jobs.insert_one({
    "created_at": now, "created_by_email": EMAIL, "status": "pending",
    "label": f"[Pipeline {sid[-6:]}] geometric 4-300, 34개 (EN-fix)",
    "source_pipeline": sid, "target_levels": TARGET, "n_seeds": 10, "n_final": 2,
    "pipeline_version": "v47 (gen_43 EN-metaphor fix 2026-06-18)",
})
jid = str(job.inserted_id)
outdir = f"/home/aimed/.hermes/v43_out/{jid}"
os.makedirs(outdir, exist_ok=True)
open(outdir + "/input.csv", "w", encoding="utf-8").write(csv["csv_text"])
db.pixelforge_v43_jobs.update_one({"_id": job.inserted_id},
    {"$set": {"csv_path": outdir + "/input.csv", "out_dir": outdir}})
db.pixelforge_pipeline_sessions.update_one({"_id": sess.inserted_id},
    {"$set": {"art_job": {"type": "v47", "job_id": jid, "status": "running", "started_at": now}}})

print(f"SESSION={sid}")
print(f"JOB={jid}")
print(f"OUTDIR={outdir}")
