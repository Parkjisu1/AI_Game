#!/usr/bin/env python3
"""reembed_kb.py — 지식베이스를 로컬 임베딩(Ollama bge-m3, 1024차원)으로 다시 색인한다.

두 가지 입력을 받는다:
  (a) --from-collection newplay_code      기존 Qdrant 컬렉션의 payload.text 를 그대로 재임베딩 (이전용, 레포 불필요)
  (b) --from-jsonl chunks.jsonl           chunk-repo.js 가 만든 청크 파일 (레포가 바뀌었을 때 재색인)

출력: Qdrant 컬렉션 --to (기본 newplay_code_m3). 같은 id 는 덮어쓴다(upsert) → 반복 실행 안전.
OpenAI 가 필요 없다. 이 PC 안에서 끝난다.

Usage (WSL, newplay):
  cd ~/.hermes-newteam/watcher
  venv/bin/python reembed_kb.py --from-collection newplay_code              # 최초 이전
  venv/bin/python reembed_kb.py --from-jsonl /mnt/c/newplay/chunks.jsonl    # 레포 갱신 후
옵션: --to <collection> --qdrant http://127.0.0.1:6343 --ollama http://127.0.0.1:11434 --model bge-m3 --batch 16 --limit N
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import uuid

import requests


def _retry(fn, what: str, tries: int = 5):
    """Ollama/Qdrant 가 잠깐 끊겨도(WSL 시계 점프·재기동) 작업 전체가 죽지 않게 — 지수 백오프 재시도."""
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                raise
            wait = 3 * (2 ** i)
            print(f"  {what} 실패({type(e).__name__}) — {wait}s 뒤 재시도 {i+1}/{tries-1}", flush=True)
            time.sleep(wait)


#: 청크 하나당 임베딩에 넣는 최대 글자 수. bge-m3 의 Ollama 컨텍스트(4096 토큰)를 코드가 넘기면 400 이 나고,
#: 실측(2026-09-14, ollama 0.34)에서는 그 직후 서버가 재시작돼 연결이 끊겼다. 2,000자면 코드도 4096 토큰 안이다.
MAX_CHARS = 2000


def embed(ollama: str, model: str, texts: list[str]) -> list[list[float]]:
    def go():
        r = requests.post(f"{ollama}/api/embed",
                          json={"model": model, "input": [t[:MAX_CHARS] for t in texts], "keep_alive": "30m"},
                          timeout=600)
        if r.status_code == 400 and len(texts) > 1:
            # 어느 하나가 너무 길다 — 반으로 나눠 범인을 고립시키고 나머지는 살린다
            mid = len(texts) // 2
            return embed(ollama, model, texts[:mid]) + embed(ollama, model, texts[mid:])
        if r.status_code == 400:
            return embed(ollama, model, [texts[0][: max(200, len(texts[0]) // 2)]])
        r.raise_for_status()
        return r.json()["embeddings"]
    return _retry(go, "임베딩")


def ensure_collection(qdrant: str, name: str, dim: int) -> None:
    r = requests.get(f"{qdrant}/collections/{name}", timeout=10)
    if r.status_code == 200:
        got = r.json()["result"]["config"]["params"]["vectors"]["size"]
        if got != dim:
            sys.exit(f"컬렉션 {name} 차원 {got} ≠ {dim}. 다른 이름을 쓰거나 삭제 후 재실행.")
        return
    requests.put(f"{qdrant}/collections/{name}",
                 json={"vectors": {"size": dim, "distance": "Cosine"}}, timeout=30).raise_for_status()
    for key, schema in (("area", "keyword"), ("kind", "keyword"), ("path", "keyword"), ("project", "keyword")):
        requests.put(f"{qdrant}/collections/{name}/index",
                     json={"field_name": key, "field_schema": schema}, timeout=30)


def iter_from_collection(qdrant: str, name: str, limit: int):
    offset = None
    n = 0
    while True:
        body = {"limit": 256, "with_payload": True, "with_vector": False}
        if offset is not None:
            body["offset"] = offset
        r = requests.post(f"{qdrant}/collections/{name}/points/scroll", json=body, timeout=60)
        r.raise_for_status()
        res = r.json()["result"]
        for p in res["points"]:
            yield p["id"], p["payload"]
            n += 1
            if limit and n >= limit:
                return
        offset = res.get("next_page_offset")
        if offset is None:
            return


def iter_from_jsonl(path: str, limit: int):
    n = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            # chunk-repo.js 의 id 규칙과 무관하게, 경로+시작줄+sha 로 안정적인 uuid 를 만든다
            key = f"{row.get('project','')}|{row.get('path','')}|{row.get('startLine','')}|{row.get('sha','')}"
            pid = str(uuid.UUID(hashlib.md5(key.encode()).hexdigest()))
            payload = {k: row.get(k) for k in ("area", "endLine", "kind", "lang", "path", "project", "sha", "startLine", "symbols", "text")}
            yield pid, payload
            n += 1
            if limit and n >= limit:
                return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-collection")
    ap.add_argument("--from-jsonl")
    ap.add_argument("--to", default="newplay_code_m3")
    ap.add_argument("--qdrant", default="http://127.0.0.1:6343")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="bge-m3")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not a.from_collection and not a.from_jsonl:
        ap.error("--from-collection 또는 --from-jsonl 이 필요합니다")

    dim = len(embed(a.ollama, a.model, ["dim probe"])[0])
    ensure_collection(a.qdrant, a.to, dim)
    src = iter_from_collection(a.qdrant, a.from_collection, a.limit) if a.from_collection \
        else iter_from_jsonl(a.from_jsonl, a.limit)

    t0 = time.time()
    total = 0
    buf: list[tuple[str, dict]] = []

    def flush() -> None:
        nonlocal total
        if not buf:
            return
        vecs = embed(a.ollama, a.model, [str(p.get("text") or "") for _, p in buf])
        pts = [{"id": pid, "vector": v, "payload": p} for (pid, p), v in zip(buf, vecs)]
        _retry(lambda: requests.put(f"{a.qdrant}/collections/{a.to}/points?wait=true",
                                    json={"points": pts}, timeout=120).raise_for_status(), "업서트")
        total += len(buf)
        buf.clear()
        if total % (a.batch * 10) == 0:
            rate = total / max(1, time.time() - t0)
            print(f"  {total} 개 … {rate:.1f}/s", flush=True)

    for pid, payload in src:
        buf.append((pid, payload))
        if len(buf) >= a.batch:
            flush()
    flush()
    cnt = requests.get(f"{a.qdrant}/collections/{a.to}", timeout=10).json()["result"]["points_count"]
    print(f"완료: {total} 개 재임베딩, 컬렉션 {a.to} = {cnt} 포인트 ({dim}차원), {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
