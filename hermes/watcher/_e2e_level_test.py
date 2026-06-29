"""E2E 테스트: [level] 태스크 생성 → 파이프라인 처리 결과 확인."""
import os
import sys
import time
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import MongoClient

db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]

# 테스트 태스크 생성 — 만화경 4-fold-rot, 분홍·보라 톤
task_doc = {
    "_id": ObjectId(),
    "title": "[level] E2E 테스트 — 25x25 만화경 4-fold-rot 분홍 보라 톤",
    "description": (
        "L1-L5 통합 검증용. 25x25 격자에 4-fold rotation 만화경 패턴, "
        "BalloonFlow 색상 중 분홍·보라 계열(0=HotPink, 2=Purple, 13=Lavender, 17=Pink) "
        "위주로 5색 이내 사용. 색상별 셀 카운트 모두 10의 배수. "
        "전체적으로 부드럽고 가독성 높게."
    ),
    "status": "todo",
    "assignee": "hermes",
    "tags": ["level", "기획", "test"],
    "team": "design",          # team override → design 파이프라인 즉시 진입
    "team_override": True,
    "sub_team": "level",
    "sub_team_override": True,  # design_pm 스킵 (어차피 level)
    "comments": [],
    "created_by_email": "jisu.park@gameberry.co.kr",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "updated_at": datetime.now(timezone.utc).isoformat(),
}

db.pixelforge_tasks.insert_one(task_doc)
task_id = str(task_doc["_id"])
print(f"✓ created task {task_id}")
print(f"  title: {task_doc['title']}")
print()

# 워처가 폴링·처리할 때까지 대기 (최대 5분)
print("⏳ waiting for watcher to process (up to 5 min)...")
deadline = time.time() + 300
last_comment_count = 0
last_status = "todo"

while time.time() < deadline:
    cur = db.pixelforge_tasks.find_one({"_id": task_doc["_id"]})
    if not cur:
        print("✗ task vanished")
        sys.exit(1)
    status = cur.get("status", "?")
    comments = cur.get("comments") or []
    if len(comments) > last_comment_count:
        # 새 코멘트만 출력
        for c in comments[last_comment_count:]:
            text = (c.get("text") or "")[:200]
            ts = (c.get("created_at") or "")[11:19]
            print(f"  [{ts}] {c.get('author', '?')}: {text}")
        last_comment_count = len(comments)
    if status != last_status:
        print(f"  → status: {last_status} → {status}")
        last_status = status
    if status in {"done", "review"}:
        # 처리 완료 — 잠시 더 기다려서 마지막 코멘트들 확보
        time.sleep(3)
        cur = db.pixelforge_tasks.find_one({"_id": task_doc["_id"]})
        comments = cur.get("comments") or []
        for c in comments[last_comment_count:]:
            text = (c.get("text") or "")[:200]
            ts = (c.get("created_at") or "")[11:19]
            print(f"  [{ts}] {c.get('author', '?')}: {text}")
        break
    time.sleep(5)
else:
    print("⏱ timeout — task still processing")

# 결과 확인
print()
print("=" * 60)
final = db.pixelforge_tasks.find_one({"_id": task_doc["_id"]})
print(f"final status: {final.get('status')}")
print(f"comments: {len(final.get('comments') or [])}")
print(f"generated_level_ids: {final.get('generated_level_ids') or 'none'}")

level_ids = final.get("generated_level_ids") or []
if level_ids:
    for lid in level_ids:
        doc = db.pixelforge_levels.find_one({"_id": ObjectId(lid)})
        if doc:
            print()
            print(f"📐 Level {lid}:")
            print(f"  name:           {doc.get('name')}")
            print(f"  size:           {doc['width']}x{doc['height']}")
            print(f"  symmetry:       {doc.get('symmetry')}")
            print(f"  palette:        {doc.get('palette')}")
            print(f"  per_color_count:{doc.get('per_color_count')}")
            print(f"  seed:           {doc.get('seed')}")
            print(f"  png:            {doc.get('png_filename')}")
            v = doc.get("validation") or {}
            print(f"  validation.ok:  {v.get('ok')}")
            print(f"  filled/empty:   {v.get('filled_cells')}/{v.get('empty_cells')}")
else:
    print("⚠ no level was generated")

# reviewer 점수
score = db.hermes_team_scores.find_one(
    {"task_id": task_id, "team": "design"},
    sort=[("created_at", -1)],
)
if score:
    print()
    print(f"🏆 reviewer score:")
    print(f"  role:    {score.get('role')}")
    print(f"  score:   {score.get('score')}/100")
    print(f"  verdict: {score.get('verdict')}")

print()
print(f"태스크 보기: /tasks?id={task_id}")
if level_ids:
    print(f"레벨 보기:    /levels#level={level_ids[0]}")
