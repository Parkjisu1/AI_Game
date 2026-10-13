#!/usr/bin/env python3
"""
Pipeline Stale Cleaner — 중간 사멸한 파이프라인 행 자동 복구 (cron 30분)

대상 (전부 결정론적·안전 전이만):
  1. pixelforge_batch_requests: pending 24h+ → failed (spawn 실패 영구잔류 방지)
  2. pixelforge_levels 등 파이프라인 행: field_running/queue_running 3h+
     → 직전 done 상태로 롤백 (UI 재실행 가능해짐. 거짓 done 마킹은 절대 안 함)
  3. art_running 3h+: 상태머신상 안전한 롤백 대상이 불명 → 변경하지 않고 Slack 경고만

updated_at/created_at이 ISO 문자열/Date 혼재 → 둘 다 매칭.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    _env = Path(__file__).parent / ".env"
    if _env.exists():
        load_dotenv(_env)
except ImportError:
    pass

from pymongo import MongoClient

logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("stale-cleaner")

MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("MONGODB_DB", "aigame")

ROLLBACK = {  # 스턱 running → 직전 안정 상태 (재실행 가능)
    "field_running": "art_done",
    "queue_running": "field_done",
}


def _old_filter(hours: int) -> dict:
    cut = datetime.now(timezone.utc) - timedelta(hours=hours)
    return {"$or": [
        {"updated_at": {"$lt": cut}}, {"updated_at": {"$lt": cut.isoformat()}},
        {"updated_at": {"$exists": False}, "created_at": {"$lt": cut.isoformat()}},
        {"updated_at": {"$exists": False}, "created_at": {"$lt": cut}},
    ]}


def _slack(db, text: str) -> None:
    try:
        s = (db.projecthub_settings.find_one({"key": "current"}) or {}).get("settings", {})
        m = next((w for w in s.get("slack_assignee_webhooks", [])
                  if (w.get("email") or "").lower() == "jisu.park@gameberry.co.kr"), None)
        if not m or not s.get("slack_bot_token"):
            return
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=json.dumps({"channel": m["slack_user_id"], "text": text}).encode(),
            headers={"Content-Type": "application/json; charset=utf-8",
                     "Authorization": f"Bearer {s['slack_bot_token']}"}, method="POST")
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        log.exception("slack notify failed")


def main() -> None:
    db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=8000)[DB_NAME]
    now = datetime.now(timezone.utc).isoformat()

    # 1. batch_requests pending 24h+ → failed
    r = db.pixelforge_batch_requests.update_many(
        {"status": "pending", **_old_filter(24)},
        {"$set": {"status": "failed", "updated_at": now,
                  "fail_reason": "stale pending 24h+ (auto-cleaned)"}})
    if r.modified_count:
        log.info("batch_requests pending→failed: %d", r.modified_count)

    # 2. 파이프라인 행 스턱 롤백 (여러 컬렉션에 같은 상태머신이 있을 수 있어 공통 적용)
    for coll_name in ("pixelforge_levels", "pixelforge_v43_jobs", "field_complete_jobs"):
        coll = db[coll_name]
        for stuck, back in ROLLBACK.items():
            r = coll.update_many(
                {"status": stuck, **_old_filter(3)},
                {"$set": {"status": back, "updated_at": now,
                          "stale_note": f"{stuck} 3h+ 스턱 → {back} 롤백 (auto)"}})
            if r.modified_count:
                log.info("%s: %s→%s %d건", coll_name, stuck, back, r.modified_count)
                _slack(db, f"🧹 파이프라인 스턱 자동 복구: `{coll_name}` {stuck}→{back} {r.modified_count}건 (재실행 가능)")

        # 3. art_running 스턱은 경고만 (안전 롤백 상태 불명)
        n = coll.count_documents({"status": "art_running", **_old_filter(3)})
        if n:
            log.warning("%s: art_running 3h+ 스턱 %d건 — 수동 확인 필요", coll_name, n)
            _slack(db, f"⚠️ `{coll_name}` art_running 3h+ 스턱 {n}건 — 자동 복구 불가, 수동 확인 필요")

    # pixelforge_tasks watchdog: fail-loud detect of stopped/review-parked hermes tasks.
    # Audit found 107 review/stopped tasks up to 131d old because nothing watched this table.
    # Read-only + Slack alert only (no writes) - safe.
    try:
        from collections import Counter
        WD_H = int(os.environ.get("HERMES_TASK_WATCHDOG_H", "12"))
        cut = datetime.now(timezone.utc) - timedelta(hours=WD_H)
        def _lt(field):
            return [{field: {"$lt": cut}}, {field: {"$lt": cut.isoformat()}}]
        base = {"assignee": {"$in": ["hermes", "Hermes", "\ud5e4\ub974\uba54\uc2a4"]}}
        stopped_q = {**base, "hermes_stopped": True, "$or": _lt("updated_at")}
        review_q = {**base, "status": "review", "$or": _lt("updated_at")}
        n_stop = db.pixelforge_tasks.count_documents(stopped_q)
        n_rev = db.pixelforge_tasks.count_documents(review_q)
        if n_stop or n_rev:
            who = Counter()
            for t in db.pixelforge_tasks.find({"$or": [stopped_q, review_q]}, {"created_by_email": 1}).limit(200):
                who[(t.get("created_by_email") or "?")] += 1
            top = ", ".join("%s:%d" % (e, c) for e, c in who.most_common(4))
            # 2026-09-11: 30분 주기로 같은 수치를 다시 보내 순수 스팸이 됐다(147회 연속 stopped=7/review=28).
            # 파킹된 태스크는 대부분 의도적으로 세워 둔 것이라 "변하지 않는 사실"을 반복 통지할 이유가 없다.
            # 기본을 미발송으로 바꾸고 로그에는 계속 남긴다 — 감사 흔적은 유지하되 알림만 끈다.
            # 다시 켜려면 크론에 HERMES_TASK_WATCHDOG_SLACK=1 을 준다.
            if os.environ.get("HERMES_TASK_WATCHDOG_SLACK", "0") == "1":
                _slack(db, ":eyes: hermes tasks parked >%dh - stopped %d / review %d. requesters: %s" % (WD_H, n_stop, n_rev, top))
            log.info("task watchdog: stopped=%d review=%d (>%dh)", n_stop, n_rev, WD_H)
    except Exception:
        log.exception("task watchdog failed")

    log.info("done")


if __name__ == "__main__":
    main()
