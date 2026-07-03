"""
Hermes Briefing — 상태 요약/브리핑 텍스트 생성 (공용 모듈)

사용처:
  - morning_briefing.py (cron, 매일 아침 Slack DM)
  - slack_inbound.py ("상태" / "브리핑" 명령 응답)
  - (향후) projecthub-web /api/assistant

모든 함수는 읽기 전용 — DB 상태를 절대 변경하지 않는다.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass

from pymongo import MongoClient

MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("MONGODB_DB", "aigame")

TASK_URL = "https://aimed.tailf6f809.ts.net/tasks"


def _db():
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return client[DB_NAME]


def _since_filter(field: str, since: datetime) -> dict[str, Any]:
    """created_at/updated_at이 datetime 또는 ISO 문자열 혼재 — 둘 다 매칭."""
    return {"$or": [
        {field: {"$gte": since}},
        {field: {"$gte": since.isoformat()}},
    ]}


def _short_id(task: dict[str, Any]) -> str:
    return str(task.get("_id"))[-8:]


def build_status_text() -> str:
    """현재 상태 스냅샷 — '상태' 질의 응답용 (가볍고 빠름)."""
    db = _db()
    tasks = db.pixelforge_tasks
    now = datetime.now(timezone.utc)

    counts = {s: tasks.count_documents({"status": s}) for s in ("todo", "in_progress", "review")}
    lines = [
        "📊 *Hermes 현재 상태*",
        f"• 대기(todo) {counts['todo']} · 진행중 {counts['in_progress']} · 리뷰 대기 {counts['review']}",
    ]

    # 진행중 작업 (최대 5)
    inprog = list(tasks.find({"status": "in_progress"},
                             {"title": 1, "hermes_claimed_by": 1}).limit(5))
    if inprog:
        lines.append("\n*🏃 진행중:*")
        for t in inprog:
            worker = t.get("hermes_claimed_by") or ""
            lines.append(f"• `#{_short_id(t)}` {(t.get('title') or '')[:50]}"
                         + (f" _({worker})_" if worker else ""))

    # 리뷰 대기 중 오래된 것부터 3건
    old_reviews = list(tasks.find(
        {"status": "review"}, {"title": 1, "updated_at": 1}
    ).sort("updated_at", 1).limit(3))
    if old_reviews:
        lines.append("\n*👀 리뷰 대기 (오래된 순):*")
        for t in old_reviews:
            lines.append(f"• `#{_short_id(t)}` {(t.get('title') or '')[:50]}")

    # 워커 플릿 (worker pool 배포 후 heartbeat)
    try:
        cutoff = now - timedelta(minutes=3)
        workers = list(db.hermes_workers.find({"ts": {"$gte": cutoff}}))
        if workers:
            lines.append("\n*⚙️ 워커:*")
            for w in workers:
                active = w.get("active") or []
                lines.append(f"• {w.get('worker_id')} — 슬롯 {len(active)}/{w.get('slots', '?')} 사용중")
    except Exception:
        pass

    lines.append(f"\n→ {TASK_URL}")
    return "\n".join(lines)


def build_briefing_text(hours: int = 24) -> str:
    """지난 N시간 브리핑 — 모닝 브리핑 / '브리핑' 명령용."""
    db = _db()
    tasks = db.pixelforge_tasks
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    lines = [f"☀️ *Hermes 브리핑* — 지난 {hours}시간 (KST {_kst(now)})"]

    # 1) 처리 요약
    created = tasks.count_documents(_since_filter("created_at", since))
    done = list(tasks.find(
        {"status": "done", **_since_filter("updated_at", since)},
        {"title": 1}).limit(10))
    review = list(tasks.find(
        {"status": "review", **_since_filter("updated_at", since)},
        {"title": 1}).limit(10))
    lines.append(f"\n*📦 작업:* 신규 {created} · 완료 {len(done)} · 리뷰 도착 {len(review)}")
    if done:
        lines.append("*✅ 완료:*")
        lines += [f"• `#{_short_id(t)}` {(t.get('title') or '')[:55]}" for t in done[:5]]
    if review:
        lines.append("*👀 리뷰해주세요:*")
        lines += [f"• `#{_short_id(t)}` {(t.get('title') or '')[:55]}" for t in review[:5]]

    # 2) 게이트/차단
    try:
        gate_rows = list(db.hermes_gate_events.aggregate([
            {"$match": {"ts": {"$gte": since}}},
            {"$group": {"_id": {"gate": "$gate", "result": "$result"}, "n": {"$sum": 1}}},
        ]))
        if gate_rows:
            parts = [f"{r['_id']['gate']}:{r['_id']['result']}×{r['n']}" for r in gate_rows]
            lines.append(f"\n*🚧 게이트:* {' · '.join(parts)}")
        blocked = list(tasks.find({"hermes_merge_state": "blocked"}, {"title": 1}).limit(5))
        if blocked:
            lines.append("*⛔ 배포 차단 (사람 확인 필요):*")
            lines += [f"• `#{_short_id(t)}` {(t.get('title') or '')[:55]}" for t in blocked]
    except Exception:
        pass

    # 3) 시뮬레이션
    try:
        sim_n = db.bf_sim_results.count_documents(_since_filter("created_at", since))
        if sim_n:
            lines.append(f"\n*🎯 시뮬레이션:* 결과 {sim_n}건 적재")
    except Exception:
        pass

    # 4) 에이전트 세션
    try:
        sess = db.hermes_agent_sessions.count_documents({"created_at": {"$gte": since}})
        lines.append(f"*🤖 에이전트 세션:* {sess}건")
    except Exception:
        pass

    # 5) 오래 방치된 리뷰 (3일+) — 매일 리마인드
    old_cut = now - timedelta(days=3)
    old_reviews = tasks.count_documents({
        "status": "review",
        "$nor": [_since_filter("updated_at", old_cut)],
    })
    if old_reviews:
        lines.append(f"\n*🕰️ 3일+ 방치된 리뷰:* {old_reviews}건 — 확인 부탁드려요")

    lines.append(f"\n→ {TASK_URL}")
    lines.append("_명령: `상태` `브리핑` `승인` `재시도` `중단 #id` `재개 #id` `작업생성: 제목 | 설명`_")
    return "\n".join(lines)


def _kst(dt: datetime) -> str:
    return (dt + timedelta(hours=9)).strftime("%m/%d %H:%M")
