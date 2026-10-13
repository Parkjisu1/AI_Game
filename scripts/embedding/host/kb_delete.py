#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Qdrant 포인트 삭제 (사람이 승인한 목록만, 2026-10-12, 2026-10-13 백업 규칙 수정). 업서트 스크립트와 분리된 별도 도구.

  python3 ~/kb_delete.py <collection> <project> <paths_file> [--apply [--backup=<file.jsonl>]]

- paths_file: 한 줄에 path 하나 (워크스테이션 manifest_todo.js --stale-out / qdrant_delta.py --missing-out 출력)
- project 필터 + path 일치로 포인트 id 를 찾고, payload 의 project/path 를 다시 확인한 id 만 대상으로 삼는다.
- --apply 없으면 조회만 하고 **아무 파일도 쓰지 않는다**.
- --apply: 대상 포인트를 {id, vector, payload} JSONL 로 백업(덮어쓰기 금지: 있으면 중단. 생략 시
  ~/kb_delta/deleted/<collection>_<project>_<시각>.jsonl) → 백업 성공 후 id 목록으로만 삭제.
  복구: python3 ~/artload_file.py <backup> (art_vectors) 또는 같은 형식 PUT points.
"""
import json, sys, os, datetime, urllib.request

QD = "http://127.0.0.1:6333"
args = [a for a in sys.argv[1:] if not a.startswith("--")]
if len(args) != 3: print(__doc__); sys.exit(2)
COLL, PROJECT, PATHS = args
APPLY = "--apply" in sys.argv
BACKUP = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--backup=")), None)


def h(m, u, d=None):
    r = urllib.request.Request(u, data=(json.dumps(d).encode() if d is not None else None),
                               headers={"Content-Type": "application/json"}, method=m)
    with urllib.request.urlopen(r, timeout=300) as resp:
        return json.loads(resp.read().decode())


paths = [l.rstrip("\r\n") for l in open(PATHS, encoding="utf-8") if l.strip()]
want = set(paths)
found = []  # point dicts with vector
for i in range(0, len(paths), 100):
    chunk = paths[i:i + 100]; off = None
    while True:
        body = {"limit": 1000, "with_payload": True, "with_vector": True,
                "filter": {"must": [{"key": "project", "match": {"value": PROJECT}},
                                    {"key": "path", "match": {"any": chunk}}]}}
        if off: body["offset"] = off
        res = h("POST", f"{QD}/collections/{COLL}/points/scroll", body)["result"]
        for p in res["points"]:
            pl = p["payload"]
            if pl.get("project") == PROJECT and pl.get("path") in want:
                found.append(p)
        off = res.get("next_page_offset")
        if not off: break
before = h("GET", f"{QD}/collections/{COLL}")["result"]["points_count"]
matched_paths = {p["payload"]["path"] for p in found}
print(f"[{COLL}] project={PROJECT} paths_in_file={len(paths)} points_found={len(found)} paths_matched={len(matched_paths)} unmatched_paths={len(want - matched_paths)} | collection points={before}")
if not APPLY:
    print("dry-run: 아무것도 쓰지 않음 (삭제하려면 --apply)"); sys.exit(0)
if not found:
    print("삭제할 포인트 없음"); sys.exit(0)
if not BACKUP:
    d = os.path.expanduser("~/kb_delta/deleted"); os.makedirs(d, exist_ok=True)
    BACKUP = os.path.join(d, f"{COLL}_{PROJECT}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
try:
    with open(BACKUP, "x", encoding="utf-8") as f:
        for p in found: f.write(json.dumps({"id": p["id"], "vector": p["vector"], "payload": p["payload"]}, ensure_ascii=False) + "\n")
except FileExistsError:
    sys.exit(f"백업 파일이 이미 있음 — 덮어쓰지 않고 중단: {BACKUP}")
print("backup ->", BACKUP, len(found))
ids = [p["id"] for p in found]
for k in range(0, len(ids), 500):
    h("POST", f"{QD}/collections/{COLL}/points/delete?wait=true", {"points": ids[k:k + 500]})
after = h("GET", f"{QD}/collections/{COLL}")["result"]["points_count"]
print(f"deleted {len(ids)} ids | collection points {before} -> {after}")
