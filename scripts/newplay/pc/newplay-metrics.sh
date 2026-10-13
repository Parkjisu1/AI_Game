#!/bin/bash
# newplay-metrics.sh — 최근 N일(기본 30) 플랫폼 지표: 프로젝트·사람별 채택률, 겹침·충돌, 재작업, 학습 건수, 계정별 호출.
DAYS=${1:-30}
~/.hermes-newteam/watcher/venv/bin/python - "$DAYS" <<'EOP'
import sys
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
days = int(sys.argv[1]); since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
db = MongoClient("mongodb://127.0.0.1:27018/?directConnection=true")["newteam"]
T = db["pixelforge_tasks"]; S = db["hermes_agent_sessions"]
print(f"== 최근 {days}일")
rows = list(T.find({"updated_at": {"$gte": since}, "branch": {"$exists": True}},
                   {"project": 1, "created_by_email": 1, "selection": 1, "overlaps": 1, "merge_hold": 1, "rework_round": 1, "learned_at": 1, "checks": 1}))
print(f"작업장 작업: {len(rows)}")
by = {}
for r in rows:
    k = (r.get("project") or "-", r.get("created_by_email") or "-")
    d = by.setdefault(k, {"n": 0, "accept": 0, "hold": 0, "reject": 0, "overlap": 0, "conflict": 0, "rework": 0, "learned": 0, "checks_fail": 0})
    d["n"] += 1
    dec = (r.get("selection") or {}).get("decision")
    if dec in d: d[dec] += 1
    if r.get("overlaps"): d["overlap"] += 1
    if r.get("merge_hold"): d["conflict"] += 1
    d["rework"] += int(r.get("rework_round") or 0)
    if r.get("learned_at"): d["learned"] += 1
    if any(not c.get("ok") for c in (r.get("checks") or [])): d["checks_fail"] += 1
print(f"{'프로젝트':<10} {'사람':<26} {'작업':>4} {'채택':>4} {'보류':>4} {'반려':>4} {'겹침':>4} {'충돌':>4} {'재작업':>5} {'학습':>4} {'검사실패':>6}")
for (p, u), d in sorted(by.items()):
    print(f"{p:<10} {u:<26} {d['n']:>4} {d['accept']:>4} {d['hold']:>4} {d['reject']:>4} {d['overlap']:>4} {d['conflict']:>4} {d['rework']:>5} {d['learned']:>4} {d['checks_fail']:>6}")
print("== 계정별 Claude 호출")
for d in S.aggregate([{"$match": {"created_at": {"$gte": datetime.now(timezone.utc) - timedelta(days=days)}, "tool": {"$in": ["claude", "claude-agent"]}}},
                      {"$group": {"_id": "$account", "n": {"$sum": 1}, "fail": {"$sum": {"$cond": ["$success", 0, 1]}}, "sec": {"$sum": "$duration_sec"}}}, {"$sort": {"n": -1}}]):
    print(f"  {(d['_id'] or '(cli-login)'):<30} 호출 {d['n']:>4}  실패 {d['fail']:>3}  총 {int(d['sec'])}s")
EOP
