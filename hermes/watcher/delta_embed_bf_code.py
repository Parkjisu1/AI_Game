#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
delta_embed_bf_code.py — E:\\BalloonFlow 1.Scripts C# 코드 델타 임베딩 → code_base.
- 2026-06-17. "중복없이": 기존 code_base(project~balloonflow) fileId에 없는 파일만 임베딩.
- text-embedding-3-small (p3b/hermes_atlas_retrieval와 동일, 1536dim). 멱등(fileId+project upsert).
- 보안: *.local.cs (SdkConfig.local 등 시크릿) 제외.
- 사전 준비: 1.Scripts 폴더를 /tmp/bf_code/ 에 scp 해둘 것.
"""
import glob
import os
from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient

load_dotenv("/home/aimed/.hermes/watcher/.env")
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
col = db.code_base
cli = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
EMBED_MODEL = "text-embedding-3-small"

# 폴더 → Layer (CLAUDE.md 분류 체계)
LAYER_BY_FOLDER = {
    "Core": "Core", "Data": "Game", "InGame": "Domain", "Manager": "Domain",
    "UI": "Game", "Popup": "Game", "UX": "Game", "Controller": "Domain",
    "Analytics": "Domain", "UA": "Game", "Debug": "Game",
}
ROLE_SUFFIX = [("Manager", "Manager"), ("Controller", "Controller"), ("Calculator", "Calculator"),
               ("Processor", "Processor"), ("Handler", "Handler"), ("Listener", "Listener"),
               ("Provider", "Provider"), ("Factory", "Factory"), ("Service", "Service"),
               ("Validator", "Validator"), ("Builder", "Builder"), ("Pool", "Pool"),
               ("Effect", "UX"), ("Tweener", "UX"), ("Config", "Config"), ("Helper", "Helper")]


def role_of(name):
    for suf, role in ROLE_SUFFIX:
        if name.endswith(suf):
            return role
    return "Component"


existing = set(x.get("fileId") for x in
               col.find({"project": {"$regex": "balloonflow", "$options": "i"}}, {"fileId": 1}))
print("existing BalloonFlow fileIds:", len(existing))

items = []  # (className, folder, text)
skipped_dup = skipped_secret = 0
for path in glob.glob("/tmp/bf_code/**/*.cs", recursive=True):
    base = os.path.basename(path)
    if base.endswith(".local.cs"):
        skipped_secret += 1
        continue
    cls = base[:-3]
    if cls in existing:
        skipped_dup += 1
        continue
    folder = os.path.basename(os.path.dirname(path))
    txt = open(path, encoding="utf-8", errors="ignore").read()
    if len(txt.strip()) < 40:
        continue
    items.append((cls, folder, txt))

print(f"scan: dup-skip={skipped_dup} secret-skip={skipped_secret} | NEW(delta)={len(items)}")
print("new files:", sorted(i[0] for i in items))

BATCH = 64
done = 0
for s in range(0, len(items), BATCH):
    batch = items[s:s + BATCH]
    resp = cli.embeddings.create(model=EMBED_MODEL, input=[b[2][:8000] for b in batch])
    for (cls, folder, txt), e in zip(batch, resp.data):
        col.update_one({"fileId": cls, "project": "BalloonFlow"}, {"$set": {
            "fileId": cls, "project": "BalloonFlow", "genre": "puzzle",
            "layer": LAYER_BY_FOLDER.get(folder, "Game"), "role": role_of(cls),
            "system": folder, "source": "internal_produced", "score": 0.4,
            "className": cls, "text": txt[:12000], "content": txt[:12000],
            "embedding": e.embedding, "embed_model": EMBED_MODEL,
        }}, upsert=True)
        done += 1
    print(f"  embedded {done}/{len(items)}")

print("DONE. code_base BalloonFlow total:",
      col.count_documents({"project": {"$regex": "balloonflow", "$options": "i"}}))
