"""
Goal Chain — [goal] 목표 분해 태스크의 의존성 체인 실행

모델:
  - 목표(부모) task: [goal] 태그 → hermes_executor._handle_goal_decompose가
    하위 task들을 status='draft'로 생성 (goal_parent, goal_index, goal_depends_on 필드)
  - 승인(on_goal_approved): 의존성 없는 draft 하위 task → todo (watcher가 픽업)
  - 하위 task 완료(on_task_done): 의존성 충족된 draft 하위 task → todo,
    전부 done이면 부모 done + 완료 알림

상태 규칙:
  - 'draft'는 watcher._is_active_status 밖 → 승인 전/의존성 미충족 시 절대 실행 안 됨
  - todo 전환은 change stream이 감지해 자연스럽게 실행됨 (별도 디스패치 불필요)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import MongoClient

log = logging.getLogger("goal-chain")

MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("MONGODB_DB", "aigame")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coll():
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)[DB_NAME]["pixelforge_tasks"]


def _comment(coll, task_id: ObjectId, text: str) -> None:
    coll.update_one(
        {"_id": task_id},
        {"$push": {"comments": {
            "id": str(ObjectId()), "text": text, "author": "hermes",
            "created_at": _now_iso(),
        }},
         "$set": {"updated_at": _now_iso()}},
    )


def _release_ready(coll, parent_id: ObjectId) -> list[str]:
    """의존성이 모두 done인 draft 하위 task를 todo로 전환. 전환된 제목 목록 반환."""
    children = list(coll.find(
        {"goal_parent": str(parent_id)},
        {"title": 1, "status": 1, "goal_index": 1, "goal_depends_on": 1},
    ))
    done_idx = {c.get("goal_index") for c in children if c.get("status") == "done"}
    released: list[str] = []
    for c in children:
        if c.get("status") != "draft":
            continue
        deps = c.get("goal_depends_on") or []
        if all(d in done_idx for d in deps):
            # 원자 전환 — draft일 때만 (중복 방지)
            res = coll.update_one(
                {"_id": c["_id"], "status": "draft"},
                {"$set": {"status": "todo", "updated_at": _now_iso()}},
            )
            if res.modified_count:
                released.append(c.get("title") or str(c["_id"]))
                log.info("goal: released subtask → todo: %s", c.get("title"))
    return released


def is_goal_parent(task: dict[str, Any]) -> bool:
    return bool(task.get("goal_children"))


def on_goal_approved(task: dict[str, Any]) -> bool:
    """
    목표 부모 task가 승인됨 → 의존성 없는 하위 task 실행 시작.
    반환: 실제로 뭔가 시작했으면 True.
    """
    coll = _coll()
    parent_id = task["_id"] if isinstance(task.get("_id"), ObjectId) else ObjectId(str(task["_id"]))
    released = _release_ready(coll, parent_id)
    if released:
        coll.update_one(
            {"_id": parent_id},
            {"$set": {"status": "in_progress", "goal_approved_at": _now_iso(),
                      "updated_at": _now_iso()}},
        )
        _comment(coll, parent_id,
                 "🚀 **목표 승인됨** — 하위 작업 실행 시작:\n"
                 + "\n".join(f"• {t}" for t in released))
        return True
    log.info("goal approved but no ready subtasks: %s", parent_id)
    return False


def on_task_done(task: dict[str, Any]) -> None:
    """
    task가 done이 됨. 목표 하위 task라면:
      1) 의존성 충족된 형제 draft → todo
      2) 전부 done이면 부모 완료 처리
    목표와 무관한 task면 no-op.
    """
    parent_ref = task.get("goal_parent")
    if not parent_ref:
        return
    try:
        coll = _coll()
        parent_id = ObjectId(str(parent_ref))
        released = _release_ready(coll, parent_id)
        if released:
            _comment(coll, parent_id,
                     f"▶️ `{(task.get('title') or '')[:40]}` 완료 → 다음 작업 시작:\n"
                     + "\n".join(f"• {t}" for t in released))

        # 전부 완료?
        remaining = coll.count_documents(
            {"goal_parent": str(parent_id), "status": {"$ne": "done"}})
        if remaining == 0:
            parent = coll.find_one({"_id": parent_id})
            if parent and parent.get("status") != "done":
                coll.update_one(
                    {"_id": parent_id},
                    {"$set": {"status": "done", "updated_at": _now_iso()}},
                )
                _comment(coll, parent_id, "🎯 **목표 완료** — 모든 하위 작업이 done 처리되었습니다.")
                _notify_goal_complete(parent)
    except Exception:
        log.exception("goal_chain.on_task_done failed (non-fatal)")


def _notify_goal_complete(parent: dict[str, Any]) -> None:
    """목표 완료 Slack DM (best-effort)."""
    try:
        from hermes_executor import _send_slack_notice
        _send_slack_notice(
            parent.get("created_by_email") or "",
            f"🎯 *목표 완료* — `{(parent.get('title') or '')[:60]}`\n"
            f"모든 하위 작업이 완료되었습니다. → https://aimed.tailf6f809.ts.net/tasks",
            fallback_assignee=(parent.get("assignee") or ""),
        )
    except Exception:
        log.debug("goal complete Slack notify failed", exc_info=True)
