#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""임베딩컴 Qdrant 점검 도구 (2026-10-12). 쓰기 없음.

  python3 ~/kb_qdrant.py counts <project> [<project> ...]
      → gf_code_chunks_m3 / art_vectors 의 project 별 포인트 수·고유 path 수
  python3 ~/kb_qdrant.py paths <collection> <project>
      → 그 project 의 고유 path 를 한 줄씩 출력 (워크스테이션 manifest_todo.js 입력)
  python3 ~/kb_qdrant.py art <image-name> [<project>]
      → art_vectors 에서 이름이 같은 이미지의 벡터로 유사 이미지 6개 (project 주면 그 안에서)
  python3 ~/kb_qdrant.py code "<한국어 질의>" [<project>]
      → bge-m3 로 질의 임베딩 후 gf_code_chunks_m3 상위 5개 (project 주면 그 안에서)
"""
import json, sys, urllib.request, collections
QD = "http://127.0.0.1:6333"; OL = "http://127.0.0.1:11434/api/embed"
CODE = "gf_code_chunks_m3"; ART = "art_vectors"


def h(m, u, d=None):
    r = urllib.request.Request(u, data=(json.dumps(d).encode() if d is not None else None),
                               headers={"Content-Type": "application/json"}, method=m)
    with urllib.request.urlopen(r, timeout=300) as resp:
        return json.loads(resp.read().decode())


def pfilter(project):
    return {"must": [{"key": "project", "match": {"value": project}}]} if project else None


def scroll_paths(coll, project):
    paths = collections.Counter(); off = None
    while True:
        body = {"limit": 2000, "with_payload": ["path"], "with_vector": False, "filter": pfilter(project)}
        if off: body["offset"] = off
        res = h("POST", f"{QD}/collections/{coll}/points/scroll", body)["result"]
        for p in res["points"]: paths[p["payload"].get("path")] += 1
        off = res.get("next_page_offset")
        if not off: return paths


cmd = sys.argv[1] if len(sys.argv) > 1 else ""
if cmd == "counts":
    for coll in (CODE, ART):
        tot = h("GET", f"{QD}/collections/{coll}")["result"]["points_count"]
        print(f"[{coll}] total points={tot}")
        for pr in sys.argv[2:]:
            ps = scroll_paths(coll, pr)
            print(f"  {pr}: points={sum(ps.values())} paths={len(ps)}")
elif cmd == "paths":
    for p in sorted(scroll_paths(sys.argv[2], sys.argv[3])): print(p)
elif cmd == "gaps":
    # gf_code_chunks_m3 조각 누락 탐지: path 별 (chunkIndex, pieceIndex) 가 0..max 로 이어지는지,
    # 마지막 조각 길이가 정확히 6000 인데 다음 조각이 없는지(꼬리 누락 의심)
    want = set(sys.argv[2:])
    seen = collections.defaultdict(dict); off = None
    while True:
        body = {"limit": 2000, "with_payload": ["project", "path", "chunkIndex", "pieceIndex", "content"], "with_vector": False}
        if off: body["offset"] = off
        res = h("POST", f"{QD}/collections/{CODE}/points/scroll", body)["result"]
        for p in res["points"]:
            pl = p["payload"]; pr = pl.get("project")
            if want and pr not in want: continue
            seen[(pr, pl.get("path"))][(pl.get("chunkIndex", 0), pl.get("pieceIndex", 0))] = len(pl.get("content") or "")
        off = res.get("next_page_offset")
        if not off: break
    per = collections.Counter(); files = collections.Counter(); detail = []
    for (pr, path), ck in seen.items():
        files[pr] += 0
        holes = []
        chunks = sorted({c for c, _ in ck})
        for c in range(0, max(chunks) + 1):
            pcs = sorted(p for cc, p in ck if cc == c)
            if not pcs: holes.append(f"c{c}:all"); continue
            for j in range(0, max(pcs) + 1):
                if j not in pcs: holes.append(f"c{c}p{j}")
            # 청크 24000자 = 조각 최대 4개(p0..p3). p3 가 6000 이면 정상 꽉 찬 청크
            if max(pcs) < 3 and ck[(c, max(pcs))] == 6000: holes.append(f"c{c}p{max(pcs)+1}?")
        if holes:
            per[pr] += len(holes); files[pr] += 1; detail.append((pr, path, holes))
    for pr in sorted({k[0] for k in seen}):
        print(f"  {pr}: files_with_gaps={files[pr]} missing_pieces={per[pr]}")
    for pr, path, holes in sorted(detail): print(f"    {pr} | {path} | {' '.join(holes)}")
elif cmd == "art":
    name = sys.argv[2]; pr = sys.argv[3] if len(sys.argv) > 3 else None
    must = [{"key": "name", "match": {"value": name}}] + (pfilter(pr)["must"] if pr else [])
    res = h("POST", f"{QD}/collections/{ART}/points/scroll", {"limit": 1, "with_vector": True, "with_payload": True, "filter": {"must": must}})["result"]["points"]
    if not res: sys.exit(f"기준 이미지 없음: {name}")
    print("기준:", res[0]["payload"]["project"], res[0]["payload"]["path"])
    body = {"query": res[0]["vector"], "limit": 6, "with_payload": True}
    if pr: body["filter"] = pfilter(pr)
    for s in h("POST", f"{QD}/collections/{ART}/points/query", body)["result"]["points"]:
        print(f"  {s['score']:.3f} {s['payload']['name']} | {s['payload']['project']} | {s['payload']['path']}")
elif cmd == "code":
    q = sys.argv[2]; pr = sys.argv[3] if len(sys.argv) > 3 else None
    v = h("POST", OL, {"model": "bge-m3", "input": q})["embeddings"][0]
    body = {"query": v, "limit": 5, "with_payload": ["project", "path", "category", "indexed_at"]}
    if pr: body["filter"] = pfilter(pr)
    print(f"[{q}] project={pr or '*'}")
    for s in h("POST", f"{QD}/collections/{CODE}/points/query", body)["result"]["points"]:
        p = s["payload"]; print(f"  {s['score']:.3f} {p.get('project')} {p.get('path')} [{p.get('category')}] {p.get('indexed_at')}")
else:
    print(__doc__); sys.exit(2)
