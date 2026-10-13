from dotenv import load_dotenv
load_dotenv("/home/aimed/.hermes/watcher/.env")
import os
from pymongo import MongoClient

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ["MONGODB_DB"]]
doc = db.projecthub_settings.find_one({"key": "current"})

if not doc:
    print("ProjectHub settings 없음")
else:
    s = doc.get("settings", {})
    print("=== ProjectHub Slack 설정 ===")
    print("default_webhook_url:", "설정됨" if s.get("slack_webhook_url") else "없음")
    print("bot_token:", "설정됨" if s.get("slack_bot_token") else "없음")
    print("notify_on_create:", s.get("slack_notify_on_create", True))
    print("notify_on_status_change:", s.get("slack_notify_on_status_change", True))
    print()
    assigns = s.get("slack_assignee_webhooks") or []
    print(f"assignee 개별 매핑 {len(assigns)}개:")
    for a in assigns:
        name = a.get("assignee", "?")
        has_dm = bool(a.get("slack_user_id"))
        has_wh = bool(a.get("webhook_url"))
        dm_val = a.get("slack_user_id", "")
        wh_val = (a.get("webhook_url") or "")[:40]
        print(f"  - {name:10} | DM={has_dm} ({dm_val[:15]}) | webhook={has_wh} ({wh_val})")
