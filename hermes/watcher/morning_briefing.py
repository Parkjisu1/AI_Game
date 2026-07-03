"""
Morning Briefing — 매일 아침 Slack DM 브리핑 (cron 엔트리)

cron 예 (Mother, KST 08:00 = UTC 23:00 전날):
  0 23 * * * ~/.hermes/watcher/venv/bin/python ~/.hermes/watcher/morning_briefing.py >> ~/.hermes/logs/briefing.log 2>&1

수신자: HERMES_BRIEFING_RECIPIENTS (콤마 구분 이메일). 미설정 시 박지수만.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
from pathlib import Path

try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

from pymongo import MongoClient

from hermes_briefing import build_briefing_text

logging.basicConfig(level="INFO", format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("morning-briefing")

MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("MONGODB_DB", "aigame")
DEFAULT_RECIPIENTS = "jisu.park@gameberry.co.kr"


def _slack_settings():
    db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)[DB_NAME]
    doc = db.projecthub_settings.find_one({"key": "current"}) or {}
    return (doc.get("settings") or {})


def _dm(bot_token: str, user_id: str, text: str) -> bool:
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps({"channel": user_id, "text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {bot_token}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        return bool(body.get("ok"))


def main() -> int:
    settings = _slack_settings()
    bot_token = settings.get("slack_bot_token", "")
    webhooks = settings.get("slack_assignee_webhooks", []) or []
    if not bot_token:
        log.error("slack_bot_token 없음 — 브리핑 발송 불가")
        return 1

    recipients = [
        e.strip().lower()
        for e in os.environ.get("HERMES_BRIEFING_RECIPIENTS", DEFAULT_RECIPIENTS).split(",")
        if e.strip()
    ]
    text = build_briefing_text(hours=24)
    sent = 0
    for email in recipients:
        match = next((w for w in webhooks
                      if (w.get("email") or "").strip().lower() == email
                      and w.get("slack_user_id")), None)
        if not match:
            log.warning("수신자 %s — slack_user_id 매핑 없음, 스킵", email)
            continue
        try:
            if _dm(bot_token, match["slack_user_id"], text):
                sent += 1
                log.info("브리핑 발송: %s", email)
        except Exception:
            log.exception("브리핑 발송 실패: %s", email)
    log.info("완료 — %d/%d 발송", sent, len(recipients))
    return 0 if sent else 1


if __name__ == "__main__":
    raise SystemExit(main())
