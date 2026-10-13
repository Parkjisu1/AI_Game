# -*- coding: utf-8 -*-
"""updatedAt 없는 옛 스키마 code_base 문서(24건) 재임베딩 보조 (2026-10-13, 사용자 승인 건).

  python scripts/embedding/legacy_reembed_20261013.py backup <log.jsonl>   # _id·project·fileId·embedding_model·embedded_at·옛 벡터 저장
  python scripts/embedding/legacy_reembed_20261013.py unset  <log.jsonl>   # 로그에 있는 _id 에서만 embedding 3필드 제거
  (그다음 scripts/embed_collection.py code_base)
  python scripts/embedding/legacy_reembed_20261013.py verify <log.jsonl>   # 새 embedded_at·옛/새 코사인
키 값은 출력하지 않는다.
"""
import os, sys, json, math
from bson import ObjectId
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".env"))
from pymongo import MongoClient
col = MongoClient(os.getenv("MONGO_URI"))["aigame"]["code_base"]
cmd, log = sys.argv[1], sys.argv[2]
Q = {"embedding": {"$exists": True}, "updatedAt": {"$exists": False}, "updated_at": {"$exists": False}}


def oid(s):
    try: return ObjectId(s)
    except Exception: return s


if cmd == "backup":
    docs = list(col.find(Q, {"project": 1, "fileId": 1, "embedding_model": 1, "embedded_at": 1, "embedding": 1}))
    with open(log, "x", encoding="utf-8") as f:   # 덮어쓰기 금지(2026-10-13): 이미 있으면 FileExistsError
        for d in docs:
            f.write(json.dumps({"_id": str(d["_id"]), "project": d.get("project"), "fileId": d.get("fileId"),
                                "embedding_model": d.get("embedding_model"), "embedded_at": str(d.get("embedded_at")),
                                "old_embedding": d["embedding"]}) + "\n")
    by = {}
    for d in docs: by[d.get("project")] = by.get(d.get("project"), 0) + 1
    print("backed up", len(docs), by, "->", log)
elif cmd == "unset":
    ids = [oid(json.loads(l)["_id"]) for l in open(log, encoding="utf-8") if l.strip()]
    r = col.update_many({"_id": {"$in": ids}}, {"$unset": {"embedding": "", "embedding_model": "", "embedded_at": ""}})
    print("ids", len(ids), "unset", r.modified_count)
elif cmd == "verify":
    rows = [json.loads(l) for l in open(log, encoding="utf-8") if l.strip()]
    cos = lambda a, b: sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    fresh = 0; changed = []; missing = 0; sims = []
    for r in rows:
        d = col.find_one({"_id": oid(r["_id"])}, {"embedding": 1, "embedded_at": 1, "fileId": 1})
        if not d or "embedding" not in d: missing += 1; continue
        if str(d.get("embedded_at", "")) > r["embedded_at"]: fresh += 1
        s = cos(r["old_embedding"], d["embedding"]); sims.append(s)
        if s < 0.99: changed.append((round(s, 4), r["project"], r["fileId"]))
    print(f"docs {len(rows)} missing {missing} fresh_embedded_at {fresh} cos_min {min(sims):.4f} cos_max {max(sims):.4f} below_0.99 {len(changed)}")
    for c in sorted(changed): print("  ", c)
