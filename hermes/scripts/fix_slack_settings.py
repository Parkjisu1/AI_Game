"""
ProjectHub Slack 설정 수정:
1. default_webhook 비활성화 (공용방 알림 중단)
2. hermes assignee → 박지수 DM 매핑 추가 (개인 모니터링)
"""
from dotenv import load_dotenv
load_dotenv("/home/aimed/.hermes/watcher/.env")
import os
from datetime import datetime, timezone
from pymongo import MongoClient

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ["MONGODB_DB"]]

doc = db.projecthub_settings.find_one({"key": "current"})
if not doc:
    print("settings 없음 — 중단")
    raise SystemExit(1)

s = doc.get("settings", {})

# 백업 (추후 복구 가능)
backup = {
    "slack_webhook_url": s.get("slack_webhook_url"),
    "slack_assignee_webhooks": s.get("slack_assignee_webhooks"),
    "backed_up_at": datetime.now(timezone.utc).isoformat(),
}
db.projecthub_settings.update_one(
    {"key": "current"},
    {"$set": {"slack_backup": backup}},
)
print("✓ 기존 설정 slack_backup 필드에 백업")

# 1. default_webhook 제거
s["slack_webhook_url"] = ""  # 빈 문자열 (resolveAssigneeRoute는 this를 "none" 취급)

# 2. hermes → 박지수 DM
assigns = s.get("slack_assignee_webhooks") or []
# 박지수의 slack_user_id 재사용
park_user_id = None
for a in assigns:
    if a.get("assignee", "").strip() == "박지수":
        park_user_id = a.get("slack_user_id")
        break

if not park_user_id:
    print("⚠️ 박지수 매핑 못 찾음. 수동 설정 필요.")
    raise SystemExit(1)

# 중복 방지
assigns = [a for a in assigns if a.get("assignee", "").strip().lower() not in {"hermes", "hermes-bot", "헤르메스"}]
for name in ["hermes", "Hermes", "헤르메스"]:
    assigns.append({
        "assignee": name,
        "slack_user_id": park_user_id,
    })

s["slack_assignee_webhooks"] = assigns

# 저장
db.projecthub_settings.update_one(
    {"key": "current"},
    {"$set": {"settings": s, "updated_at": datetime.now(timezone.utc).isoformat()}},
)
print("✓ default_webhook 제거 + hermes/Hermes/헤르메스 3개 alias 모두 박지수 DM으로 라우팅")
print()
print("결과:")
print(f"  default_webhook: {'설정' if s.get('slack_webhook_url') else '없음 (공용방 알림 중단)'}")
print(f"  hermes → 박지수 DM ({park_user_id})")
print()
print("복구 방법 (필요 시):")
print("  mongosh에서: db.projecthub_settings.updateOne(")
print("    {key:'current'},")
print("    {$set:{settings:{slack_webhook_url: '<backup url>', slack_assignee_webhooks: <backup array>}}}")
print("  )")
