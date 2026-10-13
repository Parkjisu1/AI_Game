#!/usr/bin/env python3
# art_vectors 업로더(범용): JSONL {id,vector,payload} → Qdrant art_vectors upsert. (임베딩컴 100.87.87.59 에서 실행)
# 사용: python3 ~/artload_file.py <jsonl>      (repo 사본: E:/AI/scripts/embedding/host/artload_file.py, 2026-10-12 승격)
# 같은 id(uuid5 "project|path")는 덮어쓴다 → 바뀐 이미지 재업서트 안전. 삭제는 하지 않는다.
import json, sys, urllib.request, collections
Q = "http://localhost:6333"; C = "art_vectors"
def h(m, u, d=None):
    r = urllib.request.Request(u, data=(json.dumps(d).encode() if d is not None else None), headers={"Content-Type": "application/json"}, method=m)
    return json.loads(urllib.request.urlopen(r, timeout=300).read())
buf = []; n = 0; proj = collections.Counter()
def flush():
    global n
    if buf: h("PUT", f"{Q}/collections/{C}/points?wait=true", {"points": buf}); n += len(buf); buf.clear()
for l in open(sys.argv[1], encoding="utf-8"):
    if not l.strip(): continue
    o = json.loads(l); proj[o["payload"]["project"]] += 1
    buf.append({"id": o["id"], "vector": o["vector"], "payload": o["payload"]})
    if len(buf) >= 500: flush()
flush()
info = h("GET", f"{Q}/collections/{C}")["result"]
print("upserted", n, dict(proj), "| collection points:", info["points_count"])
