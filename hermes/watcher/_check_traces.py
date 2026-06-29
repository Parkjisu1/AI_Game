"""H3 trace 검증 — 가장 최근 trace 1건의 span 트리 출력."""
import os
from pathlib import Path
from pymongo import MongoClient


def load_env():
    p = Path("/home/aimed/.hermes/watcher/.env")
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


load_env()
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]

# 가장 최근 trace_id 찾기
latest = db.hermes_traces.find_one({}, sort=[("start_time", -1)])
if not latest:
    print("no traces yet")
    raise SystemExit(0)

trace_id = latest["trace_id"]
print(f"latest trace_id: {trace_id}")
print()

spans = list(db.hermes_traces.find({"trace_id": trace_id}).sort("start_time", 1))
print(f"  total spans: {len(spans)}")
print()

# trace 트리 출력
by_id = {s["_id"]: s for s in spans}
children: dict[str, list] = {}
roots: list = []
for s in spans:
    p = s.get("parent_span_id")
    if p:
        children.setdefault(p, []).append(s)
    else:
        roots.append(s)


def print_tree(s, depth=0):
    indent = "  " * depth
    name = s["span_name"]
    role = s.get("role") or ""
    model = s.get("model") or ""
    dur = s.get("duration_ms") or 0
    status = s.get("status")
    info = []
    if role:
        info.append(f"role={role}")
    if model:
        info.append(f"model={model}")
    info.append(f"{dur}ms")
    if status != "ok":
        info.append(f"⚠️{status}")
    print(f"{indent}├─ {name:25s} ({', '.join(info)})")
    for c in sorted(children.get(s["_id"], []), key=lambda x: x["start_time"]):
        print_tree(c, depth + 1)


for r in roots:
    print_tree(r)

# 통계
print()
total = db.hermes_traces.count_documents({})
distinct_traces = len(db.hermes_traces.distinct("trace_id"))
print(f"전체: {total} spans across {distinct_traces} traces")
