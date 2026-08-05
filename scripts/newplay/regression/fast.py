#!/usr/bin/env python3
"""fast.py — 라우팅 회귀만 빠르게 잰다. 워처를 거치지 않는다.

왜 직접 호출인가:
    워커 슬롯이 2개인데 태스크 하나가 클레임되면 코더·검수까지 다 돌고서야 슬롯이 빈다.
    9케이스를 큐에 넣으면 줄을 서서 수십 분이 걸리고, 실제로 대기 15건이 쌓여 전부 시간초과가 났다.
    라우팅만 재는 데 그 비용을 낼 이유가 없다.
    Translator 와 PM 만 직접 부르면 케이스당 3~5초다. 태스크도 만들지 않아 보드가 깨끗하다.

재는 것:
    team / sub_team 정확도, 되묻기 여부(needs_input).
    파일 recall·검수 점수는 실제 작업이 필요하므로 full 모드(run.js --full)에서만 잰다.

Usage:
    python3 fast.py                     # 전체
    python3 fast.py --only game-key     # 일부
    python3 fast.py --compare           # 최근 2회 비교
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/home/aimed/.hermes-newteam/watcher")
os.chdir("/home/aimed/.hermes-newteam/watcher")

from dotenv import load_dotenv  # noqa: E402

load_dotenv("/home/aimed/.hermes-newteam/watcher/.env")

import logging  # noqa: E402

logging.disable(logging.WARNING)

from bson import ObjectId  # noqa: E402
from pymongo import MongoClient  # noqa: E402

import hermes_executor as HE  # noqa: E402

CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases.json")
MONGO = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27018/?directConnection=true")
DB = os.environ.get("MONGODB_DB", "newteam")

args = sys.argv[1:]
ONLY = []
if "--only" in args:
    ONLY = [x.strip() for x in args[args.index("--only") + 1].split(",") if x.strip()]
COMPARE = "--compare" in args


class _NullWriter:
    """PM 이 코멘트를 남기려 하지만 회귀에서는 남길 태스크가 없다."""

    def add_comment(self, *a, **k):
        return True

    def patch(self, *a, **k):
        return True


def run_case(c: dict) -> dict:
    task = {
        "_id": ObjectId(),
        "title": c["title"],
        "description": c["description"],
        "comments": [],
    }
    ctx = {"comments": [], "kb_health": {"ok": True}}

    t0 = time.time()
    tr = HE._translate(task, ctx)
    if not tr.get("ok"):
        return {"id": c["id"], "error": tr.get("error", "translator 실패"), "sec": round(time.time() - t0, 1)}

    team = tr["team"]
    asked = tr["clarity"] == "needs_input" and bool(tr.get("questions"))
    sub = ""
    # 팀이 정해지고 되묻지 않을 때만 PM 을 부른다 — 실제 흐름과 같게.
    if not asked and team in HE.PM_ROLE:
        sub = HE._pick_sub_team(task, team, _NullWriter(), str(task["_id"]))

    exp = c.get("expect", {})
    return {
        "id": c["id"],
        "team": team,
        "sub_team": sub,
        "team_ok": (not exp.get("team")) or team == exp["team"],
        "sub_ok": (not exp.get("sub_team")) or sub == exp["sub_team"],
        "asked": asked,
        "ask_ok": True if exp.get("no_ask") is None else (not asked if exp["no_ask"] else True),
        "questions": tr.get("questions", [])[:3],
        "reason": (tr.get("reason") or "")[:120],
        "sec": round(time.time() - t0, 1),
    }


def main() -> None:
    cli = MongoClient(MONGO, serverSelectionTimeoutMS=10000)
    runs = cli[DB]["newplay_regression_runs"]

    if COMPARE:
        last = list(runs.find({"mode": "fast"}).sort("started_at", -1).limit(2))
        if len(last) < 2:
            print("비교할 fast 실행이 2회 미만입니다.")
            return
        now, prev = last[0], last[1]
        print(f"비교: {prev['started_at']}  →  {now['started_at']}\n")
        pm = {r["id"]: r for r in prev["results"]}
        for r in now["results"]:
            p = pm.get(r["id"])
            if not p:
                print(f"  {r['id']:<16} (신규)")
                continue
            bits = []
            if p.get("team") != r.get("team"):
                bits.append(f"팀 {p.get('team')}→{r.get('team')}")
            if p.get("sub_team") != r.get("sub_team"):
                bits.append(f"분과 {p.get('sub_team') or '-'}→{r.get('sub_team') or '-'}")
            if p.get("asked") != r.get("asked"):
                bits.append(f"되묻기 {'Y' if p.get('asked') else 'N'}→{'Y' if r.get('asked') else 'N'}")
            print(f"  {r['id']:<16} {' · '.join(bits) if bits else '변화 없음'}")
        return

    cases = json.load(open(CASES_PATH, encoding="utf-8"))["cases"]
    if ONLY:
        cases = [c for c in cases if c["id"] in ONLY]

    started = datetime.now(timezone.utc).isoformat()
    print(f"fast 회귀 · 케이스 {len(cases)}건 (워처 미경유, 라우팅만)")
    results = []
    for c in cases:
        r = run_case(c)
        results.append(r)
        if "error" in r:
            print(f"  {r['id']:<16} 오류: {r['error'][:60]}")
            continue
        mark = lambda ok: "O" if ok else "X"  # noqa: E731
        print(f"  {r['id']:<16} {mark(r['team_ok'])} {r['team']:<7} "
              f"{mark(r['sub_ok'])} {(r['sub_team'] or '-'):<9} "
              f"되묻기 {'Y' if r['asked'] else 'N'}{'' if r['ask_ok'] else '!'}  {r['sec']}s")

    ok = [r for r in results if "error" not in r]
    summary = {
        "cases": len(results),
        "team_ok": sum(1 for r in ok if r["team_ok"]),
        "sub_ok": sum(1 for r in ok if r["sub_ok"]),
        "ask_ok": sum(1 for r in ok if r["ask_ok"]),
        "errors": len(results) - len(ok),
        "sec_total": round(sum(r.get("sec", 0) for r in results), 1),
    }
    run_id = "fast_" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    runs.insert_one({
        "run_id": run_id, "mode": "fast", "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary, "results": results,
    })
    print("\n요약:", json.dumps(summary, ensure_ascii=False))
    print(f"저장됨 → {DB}.newplay_regression_runs ({run_id})")


if __name__ == "__main__":
    main()
