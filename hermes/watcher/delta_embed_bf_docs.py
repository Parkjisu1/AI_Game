#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
delta_embed_bf_docs.py — E:\\BalloonFlow\\BalloonFlow_Doc 의 신규 .md 기획서 델타 임베딩 → design_base.
- 2026-06-17. "중복없이": 이미 임베딩된 doc_file + 정규화 파일명(폴더/'(N)' 무시) 중복 제거.
- 폴더 우선순위: Recent > 2026-05-28 > balloonflow_260522 > 루트 (같은 문서면 최신 폴더만).
- p3b와 동일 청크/모델(text-embedding-3-small). docx/xlsx는 제외(변환 필요·레벨데이터 정책).
- 사전: BalloonFlow_Doc 를 /tmp/bf_docs2/ 에 scp.
"""
import glob
import os
import re
from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient

load_dotenv("/home/aimed/.hermes/watcher/.env")
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
col = db.design_base
cli = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
EMBED_MODEL = "text-embedding-3-small"

PRIORITY = ["/Recent/", "/2026-05-28/", "/balloonflow_260522/", "/"]


def norm(fn):
    """파일명 정규화: '(1)'/공백 꼬리 제거 → 같은 문서 판별 키."""
    b = os.path.basename(fn)
    b = re.sub(r"\s*\(\d+\)(?=\.md$)", "", b)
    return b.strip().lower()


def chunk_md(text, target=2200):
    parts = re.split(r"(?=\n#{1,3}\s)", text)
    chunks, buf = [], ""
    for p in parts:
        if len(buf) + len(p) > target and buf:
            chunks.append(buf.strip()); buf = ""
        buf += p
        while len(buf) > target * 1.6:
            chunks.append(buf[:target].strip()); buf = buf[target:]
    if buf.strip():
        chunks.append(buf.strip())
    return [c for c in chunks if len(c) >= 80]


# 이미 임베딩된 doc_file (정규화)
embedded = set(norm(x["doc_file"]) for x in
               col.find({"project": "BalloonFlow", "doc_file": {"$exists": True}}, {"doc_file": 1})
               if x.get("doc_file"))
print("already embedded (normalized):", len(embedded))

# 폴더 우선순위로 후보 정렬 → 같은 정규화 이름은 1번만
def prio(path):
    for i, p in enumerate(PRIORITY):
        if p in path.replace("\\", "/"):
            return i
    return len(PRIORITY)

all_md = sorted(glob.glob("/tmp/bf_docs2/**/*.md", recursive=True), key=prio)
seen, new_files = set(), []
for path in all_md:
    n = norm(path)
    if n in embedded or n in seen:
        continue
    seen.add(n)
    new_files.append(path)

print(f"NEW md docs (delta): {len(new_files)}")
for p in new_files:
    print("  +", os.path.basename(p))

# 청크 수집
items = []
for path in new_files:
    fname = os.path.basename(path)
    txt = open(path, encoding="utf-8", errors="ignore").read()
    for i, ch in enumerate(chunk_md(txt)):
        did = f"bf_doc_{re.sub(r'[^a-zA-Z0-9]', '_', fname)[:40]}_{i}"
        items.append((did, fname, i, ch))
print(f"→ chunks: {len(items)}")

BATCH = 96
done = 0
for s in range(0, len(items), BATCH):
    batch = items[s:s + BATCH]
    resp = cli.embeddings.create(model=EMBED_MODEL, input=[b[3][:8000] for b in batch])
    for (did, fname, idx, ch), e in zip(batch, resp.data):
        col.update_one({"designId": did}, {"$set": {
            "designId": did, "project": "BalloonFlow", "genre": "puzzle",
            "source": "internal_produced", "data_type": "spec_doc", "domain": "content",
            "doc_file": fname, "chunk_index": idx,
            "text": ch, "content": ch, "title": fname, "embedding": e.embedding,
        }}, upsert=True)
        done += 1
    print(f"  embedded {done}/{len(items)}")

print("DONE. design_base BalloonFlow spec_doc:",
      col.count_documents({"project": "BalloonFlow", "data_type": "spec_doc"}))
