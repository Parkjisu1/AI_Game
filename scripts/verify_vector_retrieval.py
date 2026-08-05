#!/usr/bin/env python
"""
Verify vector retrieval works against BalloonFlow embeddings on Atlas.
Tests 3 indexed collections: code_base, pixelforge_tasks, hermes_team_scores.
For non-indexed collections (design_base, art_assets, etc.), demonstrate keyword + cosine in-memory fallback.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

for p in ["/home/aimed/.hermes/watcher/.env", "/home/aimed/projecthub-web/.env.production"]:
    if Path(p).exists():
        load_dotenv(p, override=False)

from openai import OpenAI
from pymongo import MongoClient

oa = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
mongo_uri = os.environ.get("MONGODB_URI") or os.environ["MONGO_URI"]
db = MongoClient(mongo_uri)["aigame"]


def vector_search(coll: str, query: str, limit: int = 4):
    qv = oa.embeddings.create(model="text-embedding-3-small", input=[query]).data[0].embedding
    pipe = [
        {"$vectorSearch": {
            "index": "vector_index",
            "path": "embedding",
            "queryVector": qv,
            "limit": limit,
            "numCandidates": 80,
        }},
        {"$project": {
            "_id": 0,
            "project": 1,
            "className": 1,
            "title": 1,
            "role": 1,
            "verdict": 1,
            "team": 1,
            "designId": 1,
            "system": 1,
            "score": {"$meta": "vectorSearchScore"},
        }},
    ]
    return list(db[coll].aggregate(pipe))


def keyword_only(coll: str, terms: list[str], limit: int = 4):
    # Fallback for non-indexed collections — case-insensitive substring on summary/content/system/tags
    or_filters = []
    for t in terms:
        or_filters.append({"summary": {"$regex": t, "$options": "i"}})
        or_filters.append({"content": {"$regex": t, "$options": "i"}})
        or_filters.append({"system": {"$regex": t, "$options": "i"}})
        or_filters.append({"tags": t.lower()})
    return list(db[coll].find({"project": "BalloonFlow", "$or": or_filters}, {"_id": 0, "designId": 1, "system": 1, "domain": 1, "tags": 1, "summary": 1}).limit(limit))


def main():
    print("===== Vector search (indexed collections) =====\n")

    tests = [
        ("code_base", "BalloonFlow의 풍선 발사 큐 관리하는 매니저"),
        ("code_base", "ObjectPool로 다트 객체 풀링하는 클래스"),
        ("code_base", "레일에서 풍선이 초과되어 게임오버 처리"),
        ("pixelforge_tasks", "BalloonFlow 시즌 패스 보상 테이블 디자인"),
        ("hermes_team_scores", "BalloonFlow 컨텐츠 작업 거부 사유"),
    ]
    for coll, q in tests:
        print(f"[{coll}] q={q!r}")
        results = vector_search(coll, q)
        for r in results:
            label = r.get("className") or r.get("title") or r.get("role") or r.get("designId") or "unknown"
            proj = r.get("project") or r.get("team") or "?"
            print(f"  {r['score']:.3f}  {proj:<22}  {str(label)[:60]}")
        print()

    print("\n===== Keyword fallback (non-indexed collections) =====\n")
    fb = [
        ("design_base", ["queue", "큐", "생성기"]),
        ("design_base", ["gimmick", "기믹", "기믹명세"]),
        ("design_base", ["beat", "비트", "PKG"]),
        ("art_assets", ["balloon"]),
    ]
    for coll, terms in fb:
        print(f"[{coll}] terms={terms}")
        results = keyword_only(coll, terms)
        for r in results:
            label = r.get("designId") or r.get("system") or "?"
            print(f"  - {label} (domain={r.get('domain')})  tags={(r.get('tags') or [])[:5]}")
        print()


if __name__ == "__main__":
    main()
