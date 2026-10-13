#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gf_code_chunks_m3 델타 갱신 (임베딩컴에서 실행).

입력: <chunks.jsonl> (워크스테이션 scripts/embedding/chunks.js 출력, 한 project 분량)
사용: python3 ~/qdrant_delta.py <chunks.jsonl> [--dry-run] [--delete-missing] [--missing-out=<file>]
(repo 사본: E:/AI/scripts/embedding/host/qdrant_delta.py, 2026-10-12 승격. 이전엔 indexed_at 이 2026-10-08 고정이었음)
기준: Qdrant 의 같은 project 포인트 (path → fileSha, category)
동작:
  - fileSha 가 같고 조각 (chunkIndex, pieceIndex) 집합도 디스크 기대값과 같은 path → 건너뜀
  - 새 path / fileSha 바뀐 path / 조각이 빠진 path(incomplete) → 파일 단위로 bge-m3 임베딩.
    한 조각이라도 임베딩에 실패하면 그 파일은 **아무것도 쓰지 않는다**(기존 포인트 유지 → 다음 실행에서 다시 대상).
    전부 성공한 파일만 기존 포인트 삭제 후 업서트. 실패 파일이 있으면 목록을 찍고 종료코드 3.
    (2026-10-13 수정: 예전엔 실패 조각만 빠진 채 fileSha 가 기록돼 영영 "unchanged" 로 남았다 — Mod10*.cs 등)
  - Qdrant 에만 있고 디스크(JSONL)에 없는 path → --delete-missing 일 때만 삭제. 삭제 전 해당 포인트(벡터 포함)를
    ~/kb_delta/deleted/<project>_missing_<시각>.jsonl 로 백업(덮어쓰지 않음)
ID 규약은 embed_qdrant.py 와 동일: uuid5(NS, "project|path|chunkIndex|pieceIndex"), 조각 6000자.
"""
import json, sys, uuid, urllib.request, collections, os, re, datetime

QD = "http://127.0.0.1:6333"; OLLAMA = "http://127.0.0.1:11434/api/embed"
COLL = os.environ.get("COLL", "gf_code_chunks_m3"); MODEL = "bge-m3"; DIM = 1024
PIECE = 6000; BATCH = 16
NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
if not ARGS: sys.exit("usage: qdrant_delta.py <chunks.jsonl> [--dry-run] [--delete-missing] [--missing-out=<file>]")
JSONL = os.path.expanduser(ARGS[0])
MISSING_OUT = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--missing-out=")), None)
TODAY = datetime.date.today().isoformat()
DELETE_MISSING = "--delete-missing" in sys.argv
DRY = "--dry-run" in sys.argv


def http(m, u, d=None):
    r = urllib.request.Request(u, data=(json.dumps(d).encode() if d is not None else None),
                               headers={"Content-Type": "application/json"}, method=m)
    with urllib.request.urlopen(r, timeout=300) as resp:
        return json.loads(resp.read().decode())


def embed(texts):
    try:
        return http("POST", OLLAMA, {"model": MODEL, "input": texts})["embeddings"]
    except Exception as e:
        out = []
        for t in texts:
            try: out.append(http("POST", OLLAMA, {"model": MODEL, "input": [t if t.strip() else " "]})["embeddings"][0])
            except Exception as e2: print("  embed skip:", str(e2)[:80]); out.append(None)
        return out


# 갈래 규칙 (kb_category_labels 메모리의 우선순위: popup > liveops > core > ui, 확신 없으면 미분류)
def categorize(path):
    p = path.lower(); name = os.path.basename(p)
    if re.search(r"(^|/)(editor|plugins|sdk|analytics|ua|debug|tools|util|data)/", p) or name.startswith("sdk"):
        return "기타"
    if "popup" in p or "dialog" in name or "modal" in name: return "popup"
    if re.search(r"(^|/)(liveops|shop|event|mission)/", p) or re.search(r"(dailyreward|pass|shop|mission|offer|\brv\b|reward)", name): return "liveops"
    if name.startswith("ui"): return "ui"
    if re.search(r"(^|/)(ingame|gameplay|battle|buddy|voxel)/", p) or re.search(r"(dart|rail|balloon|tile|board|holder|cube|gem)", name): return "core"
    if re.search(r"(^|/)ui/", p): return "ui"
    return "미분류"


rows = [json.loads(l) for l in open(JSONL, encoding="utf-8")]
project = rows[0]["project"]
disk = collections.defaultdict(list)
for r in rows: disk[r["path"]].append(r)


def split(c):
    return [c[i:i + PIECE] for i in range(0, max(1, len(c)), PIECE)] or [""]


expected = {p: {(r["chunkIndex"], j) for r in rs for j in range(len(split(r["content"])))} for p, rs in disk.items()}

# 기존 상태
existing = {}  # path -> {"shas": set, "category": c, "keys": set((chunk, piece)), "n": count}
off = None
while True:
    body = {"limit": 1000, "with_payload": ["path", "fileSha", "category", "chunkIndex", "pieceIndex"], "with_vector": False,
            "filter": {"must": [{"key": "project", "match": {"value": project}}]}}
    if off: body["offset"] = off
    res = http("POST", f"{QD}/collections/{COLL}/points/scroll", body)["result"]
    for p in res["points"]:
        pl = p["payload"]
        e = existing.setdefault(pl["path"], {"shas": set(), "category": pl.get("category"), "keys": set(), "n": 0})
        e["shas"].add(pl.get("fileSha")); e["keys"].add((pl.get("chunkIndex", 0), pl.get("pieceIndex", 0))); e["n"] += 1
    off = res.get("next_page_offset")
    if not off: break

same_sha = lambda p: existing[p]["shas"] == {disk[p][0]["fileSha"]}
unchanged = [p for p in disk if p in existing and same_sha(p) and existing[p]["keys"] == expected[p]]
incomplete = [p for p in disk if p in existing and same_sha(p) and existing[p]["keys"] != expected[p]]
changed = [p for p in disk if p in existing and not same_sha(p)]
new = [p for p in disk if p not in existing]
missing = [p for p in existing if p not in disk]
print(f"[{COLL}] {project}: qdrant files={len(existing)} disk files={len(disk)} | unchanged={len(unchanged)} changed={len(changed)} incomplete={len(incomplete)} new={len(new)} missing_on_disk={len(missing)}")
if incomplete:
    print("incomplete (조각 누락/초과):", [(p, sorted(expected[p] - existing[p]["keys"])[:6]) for p in incomplete[:50]])
if missing:
    print("missing_on_disk (Qdrant 에만 있음, --delete-missing 없으면 유지):", missing[:200])
if MISSING_OUT:
    open(MISSING_OUT, "w", encoding="utf-8").write("".join(p + "\n" for p in missing))
if DRY:
    print("changed:", changed[:50]); print("new:", new[:50]); sys.exit(0)


def path_filter(paths):
    return {"must": [{"key": "project", "match": {"value": project}}, {"key": "path", "match": {"any": paths}}]}


def delete_paths(paths):
    for i in range(0, len(paths), 50):
        http("POST", f"{QD}/collections/{COLL}/points/delete?wait=true", {"filter": path_filter(paths[i:i + 50])})


if DELETE_MISSING and missing:
    bdir = os.path.expanduser("~/kb_delta/deleted"); os.makedirs(bdir, exist_ok=True)
    bfile = os.path.join(bdir, f"{project}_missing_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl")
    if os.path.exists(bfile): sys.exit(f"backup exists, refusing to overwrite: {bfile}")
    with open(bfile, "x", encoding="utf-8") as f:
        for i in range(0, len(missing), 50):
            off = None
            while True:
                b = {"limit": 1000, "with_payload": True, "with_vector": True, "filter": path_filter(missing[i:i + 50])}
                if off: b["offset"] = off
                res = http("POST", f"{QD}/collections/{COLL}/points/scroll", b)["result"]
                for p in res["points"]: f.write(json.dumps({"id": p["id"], "vector": p["vector"], "payload": p["payload"]}, ensure_ascii=False) + "\n")
                off = res.get("next_page_offset")
                if not off: break
    print("backup of missing paths ->", bfile)
    delete_paths(missing); print("deleted missing paths:", len(missing))

todo = changed + incomplete + new
total_pieces = sum(len(expected[p]) for p in todo)
print("files to embed:", len(todo), "pieces:", total_pieces)
n = 0; failed = []
for k, path in enumerate(todo):
    cat = existing.get(path, {}).get("category") or categorize(path)
    cat_src = "kept_from_previous" if path in existing and existing[path].get("category") else "path_rule_20261008_delta"
    pieces = []
    for r in disk[path]:
        for j, s in enumerate(split(r["content"])):
            pid = str(uuid.uuid5(NS, f"{r['project']}|{r['path']}|{r['chunkIndex']}|{j}"))
            payload = {"project": r["project"], "path": r["path"], "lang": r["lang"], "fileSha": r["fileSha"],
                       "chunkIndex": r["chunkIndex"], "pieceIndex": j, "content": s,
                       "category": cat, "category_src": cat_src, "indexed_at": TODAY}
            pieces.append((pid, payload, s if s.strip() else " "))
    vecs = []
    for i in range(0, len(pieces), BATCH):
        vecs += embed([x[2][:PIECE] for x in pieces[i:i + BATCH]])
    bad = [pl["chunkIndex"] * 100 + pl["pieceIndex"] for (_, pl, _), v in zip(pieces, vecs) if v is None or len(v) != DIM]
    if bad:
        failed.append((path, bad)); print(f"  FAILED {path}: {len(bad)}/{len(pieces)} pieces — 이 파일은 쓰지 않음(기존 포인트 유지)", flush=True)
        continue
    if path in existing: delete_paths([path])
    pts = [{"id": pid, "vector": v, "payload": pl} for (pid, pl, _), v in zip(pieces, vecs)]
    for i in range(0, len(pts), 64):
        http("PUT", f"{QD}/collections/{COLL}/points?wait=true", {"points": pts[i:i + 64]})
    n += len(pts)
    if k % 20 == 0: print(f"  {n}/{total_pieces}", flush=True)
info = http("GET", f"{QD}/collections/{COLL}")["result"]
print(f"=== done: upserted {n} points; failed files {len(failed)}; collection points_count={info['points_count']} ===")
if failed:
    print("FAILED_FILES:", failed); sys.exit(3)
