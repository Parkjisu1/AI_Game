"""P3b — E:\\BalloonFlow 문서를 design_base에 청크 임베딩 (project=BalloonFlow). 멱등(designId upsert)."""
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
EMBED_MODEL = "text-embedding-3-small"  # hermes_atlas_retrieval와 동일


def chunk_md(text, target=2200):
    """## 섹션 경계 우선, 그 안에서 target 길이로 누적 분할."""
    parts = re.split(r"(?=\n#{1,3}\s)", text)  # 헤더 앞에서 분리
    chunks, buf = [], ""
    for p in parts:
        if len(buf) + len(p) > target and buf:
            chunks.append(buf.strip())
            buf = ""
        buf += p
        while len(buf) > target * 1.6:  # 헤더 없는 초대형 블록 강제 분할
            chunks.append(buf[:target].strip())
            buf = buf[target:]
    if buf.strip():
        chunks.append(buf.strip())
    return [c for c in chunks if len(c) >= 80]


# 1) 모든 문서 청크 수집
items = []  # (designId, fname, idx, text)
for path in sorted(glob.glob("/tmp/bf_docs/*.md")):
    fname = os.path.basename(path)
    txt = open(path, encoding="utf-8", errors="ignore").read()
    for i, ch in enumerate(chunk_md(txt)):
        items.append((f"bf_doc_{re.sub(r'[^a-zA-Z0-9]', '_', fname)[:40]}_{i}", fname, i, ch))
print(f"문서 {len(set(x[1] for x in items))}개 → 청크 {len(items)}개")

# 2) 배치 임베딩 + upsert
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
            "text": ch, "content": ch, "title": fname,
            "embedding": e.embedding,
        }}, upsert=True)
        done += 1
    print(f"  {done}/{len(items)}")

print("완료. design_base 총:", col.estimated_document_count(),
      "| BalloonFlow spec_doc:", col.count_documents({"data_type": "spec_doc"}))
