"""
ProjectHub Writer — pixelforge_tasks 컬렉션 업데이트 래퍼

ProjectHub의 API route(POST/PATCH /api/tasks)와 동등한 연산을 MongoDB로 직접 수행.
Hermes가 작업 처리 결과를 반영할 때 사용.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from pymongo.collection import Collection

log = logging.getLogger("projecthub-writer")


def _utc_now_iso() -> str:
    """ProjectHub 규칙과 맞추기 위해 ISO 8601 문자열로 저장"""
    return datetime.now(timezone.utc).isoformat()


class ProjectHubWriter:
    """pixelforge_tasks 컬렉션에 업데이트를 반영"""

    def __init__(self, collection: Collection) -> None:
        self.coll = collection

    # ──────────────────────────────────────────
    # 상태 변경
    # ──────────────────────────────────────────
    def update_status(self, task_id: str, new_status: str) -> bool:
        """
        status를 변경. 허용값: todo | in_progress | review | done

        주의: ProjectHub의 PATCH API가 자동으로 Slack 알림을 쏘지만,
        여기선 MongoDB 직접 업데이트라 Slack 알림 스킵됨. Phase 1은 알림 불필요.
        """
        if new_status not in {"todo", "in_progress", "review", "done"}:
            log.warning("Invalid status: %s", new_status)
            return False

        try:
            result = self.coll.update_one(
                {"_id": ObjectId(task_id)},
                {"$set": {
                    "status": new_status,
                    "updated_at": _utc_now_iso(),
                }},
            )
            return result.modified_count > 0
        except Exception:
            log.exception("update_status failed for %s", task_id)
            return False

    # ──────────────────────────────────────────
    # 댓글 추가
    # ──────────────────────────────────────────
    def add_comment(
        self,
        task_id: str,
        text: str,
        author: str = "hermes",
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[str]:
        """
        comments 배열에 추가. ProjectHub의 PATCH { add_comment } 구조와 일치.

        반환: comment_id (string) 또는 None (실패 시)
        """
        comment_id = str(ObjectId())
        comment = {
            "id": comment_id,
            "text": text,
            "author": author,
            "created_at": _utc_now_iso(),
        }
        if metadata:
            # ProjectHub UI가 모르는 필드지만 MongoDB는 허용
            comment["_hermes_meta"] = metadata

        try:
            result = self.coll.update_one(
                {"_id": ObjectId(task_id)},
                {
                    "$push": {"comments": comment},
                    "$set": {"updated_at": _utc_now_iso()},
                },
            )
            if result.modified_count > 0:
                return comment_id
            return None
        except Exception:
            log.exception("add_comment failed for %s", task_id)
            return None

    # ──────────────────────────────────────────
    # 여러 필드 한 번에 패치
    # ──────────────────────────────────────────
    def patch(self, task_id: str, updates: dict[str, Any]) -> bool:
        """
        title, description, priority, related_levels 등 기타 필드 업데이트용.
        status / comments 같은 특수 필드는 전용 메서드 사용 권장.
        """
        updates["updated_at"] = _utc_now_iso()
        try:
            result = self.coll.update_one(
                {"_id": ObjectId(task_id)},
                {"$set": updates},
            )
            return result.modified_count > 0
        except Exception:
            log.exception("patch failed for %s", task_id)
            return False

    # ──────────────────────────────────────────
    # 조회
    # ──────────────────────────────────────────
    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        """단일 task 조회 (다른 모듈이 필요할 때)"""
        try:
            return self.coll.find_one({"_id": ObjectId(task_id)})
        except Exception:
            log.exception("get_task failed for %s", task_id)
            return None

    # ──────────────────────────────────────────
    # Hermes 세션 링크 (projecthub_settings 컬렉션 활용)
    # ──────────────────────────────────────────
    def link_hermes_session(
        self,
        task_id: str,
        session_id: str,
        scope: dict[str, Any],
    ) -> bool:
        """
        task ↔ hermes_session_id 매핑을 projecthub_settings에 저장.
        (pixelforge_tasks 스키마는 건드리지 않음 — 경로 A 원칙)
        """
        try:
            db = self.coll.database
            settings_coll = db["projecthub_settings"]
            settings_coll.update_one(
                {"key": "hermes_sessions"},
                {
                    "$set": {
                        f"mapping.{task_id}": {
                            "session_id": session_id,
                            "scope": scope,
                            "last_activity": _utc_now_iso(),
                        }
                    }
                },
                upsert=True,
            )
            return True
        except Exception:
            log.exception("link_hermes_session failed")
            return False

    def get_linked_session(self, task_id: str) -> Optional[dict[str, Any]]:
        """이전에 이 task에서 시작된 Hermes 세션 정보 조회"""
        try:
            db = self.coll.database
            doc = db["projecthub_settings"].find_one({"key": "hermes_sessions"})
            if not doc:
                return None
            mapping = doc.get("mapping", {})
            return mapping.get(task_id)
        except Exception:
            log.exception("get_linked_session failed")
            return None
