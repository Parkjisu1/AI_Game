"""
Truth Gate — 자기개선 학습을 '객관적 수용(objective acceptance)'에 묶는 진실성 게이트.

문제: 기존 학습(시니어 원칙 / RAG good / 프롬프트 패치 승격)이 리뷰 시점의
LLM 점수만으로 일어남 = "LLM이 LLM을 채점". 검증 안 된 성공을 학습 → 환각 강화.

해결: 리뷰 시점엔 학습을 '보류(pending)'만 하고, 작업이 게이트를 통과해 실제
ship(next_status=done)된 '객관적 수용' 시점에만 학습을 확정(grounded reflect +
candidate 패치 승격). 사람이 나중에 거부하면(on_falsified) 파생 학습을 회수.

데이터 흐름:
  review  → defer_learning()        → hermes_learning_pending {status:pending}
  done    → on_objective_acceptance → reflect(grounded) + promote candidate patches
  reject  → on_falsified            → 원칙/RAG-good 회수 + pending 취소

모든 함수는 방어적(절대 raise 안 함) — 학습 게이트 실패가 작업 흐름을 막지 않게.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

log = logging.getLogger("truth-gate")

PENDING = "hermes_learning_pending"
PRINCIPLES = "hermes_domain_principles"
TASKS = "pixelforge_tasks"


def _get_db():
    try:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            return None
        return MongoClient(uri, serverSelectionTimeoutMS=2000)[os.environ.get("MONGODB_DB", "aigame")]
    except Exception:
        log.exception("truth_gate._get_db failed")
        return None


def _oid(task_id):
    try:
        from bson import ObjectId
        return ObjectId(str(task_id))
    except Exception:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def defer_learning(*, task_id, team, sub_team, reviewer_role, coder_role,
                   score, verdict, summary, files_changed, diff_summary,
                   title, description) -> None:
    """리뷰 시점: 학습을 즉시 하지 않고 근거(diff 등)와 함께 pending 적재. 수용 시 확정."""
    db = _get_db()
    if db is None:
        return
    try:
        db[PENDING].update_one(
            {"task_id": str(task_id), "reviewer_role": reviewer_role or ""},
            {"$set": {
                "task_id": str(task_id),
                "team": team or "",
                "sub_team": sub_team or "general",
                "reviewer_role": reviewer_role or "",
                "coder_role": coder_role or "",
                "score": int(score),
                "verdict": (verdict or "")[:32],
                "summary": (summary or "")[:800],
                "files_changed": (files_changed or [])[:30],
                "diff_summary": (diff_summary or "")[:4000],
                "title": (title or "")[:200],
                "description": (description or "")[:1500],
                "status": "pending",
                "updated_at": _now(),
            }},
            upsert=True,
        )
    except Exception:
        log.exception("defer_learning failed")


def on_objective_acceptance(task_id) -> None:
    """task가 done으로 ship됨 = 객관적 수용. pending 학습을 grounded로 확정 + 패치 승격."""
    db = _get_db()
    if db is None:
        return
    try:
        pendings = list(db[PENDING].find({"task_id": str(task_id), "status": "pending"}))
    except Exception:
        log.exception("on_objective_acceptance: fetch pending failed")
        return

    for pend in pendings:
        # 1) grounded senior reflection (점수<70은 reflect_on_task가 자체 스킵)
        try:
            from senior_reflection import reflect_on_task
            saved = reflect_on_task(
                task_id=str(task_id),
                title=pend.get("title") or "(task)",
                description=pend.get("description") or "",
                team=pend.get("team") or "?",
                sub_team=pend.get("sub_team") or "general",
                verdict=pend.get("verdict") or "",
                score=pend.get("score"),
                files_changed=pend.get("files_changed") or [],
                diff_summary=pend.get("diff_summary") or "",
                reviewer_notes=pend.get("summary") or "",
            )
            if saved:
                log.info("🎓 [truth-gate] %d grounded principles saved on acceptance task=%s",
                         saved, task_id)
        except Exception:
            log.exception("on_objective_acceptance: reflect failed")

        # 2) candidate 패치 승격 — 수용된 작업에서만 표본 인정(coder/reviewer 양쪽)
        try:
            from prompt_self_improvement import promote_candidates_on_acceptance
            for r in {pend.get("coder_role"), pend.get("reviewer_role")}:
                if r:
                    promote_candidates_on_acceptance(role=r, score=int(pend.get("score") or 0))
        except Exception:
            log.exception("on_objective_acceptance: promote failed")

        try:
            db[PENDING].update_one({"_id": pend["_id"]},
                                   {"$set": {"status": "promoted", "promoted_at": _now()}})
        except Exception:
            pass

    # 작업에 학습검증 마크 (조회/감사용)
    oid = _oid(task_id)
    if oid is not None:
        try:
            db[TASKS].update_one({"_id": oid}, {"$set": {"learning_verified": True}})
        except Exception:
            pass


def on_falsified(task_id, reason: str = "user_rejected") -> None:
    """사람이 거부 = 직전 학습이 거짓. 파생 원칙 회수 + RAG-good 강등 + pending 취소."""
    db = _get_db()
    if db is None:
        return
    tid = str(task_id)
    try:
        db[PENDING].update_many({"task_id": tid, "status": "pending"},
                                {"$set": {"status": "cancelled", "cancel_reason": reason}})
    except Exception:
        log.exception("on_falsified: cancel pending failed")

    # 이 task에서 파생된 원칙 회수 (reinforced_count 차감, 0이면 삭제)
    try:
        for pr in db[PRINCIPLES].find({"task_ids": tid}):
            rc = int(pr.get("reinforced_count") or 1) - 1
            if rc <= 0:
                db[PRINCIPLES].delete_one({"_id": pr["_id"]})
            else:
                db[PRINCIPLES].update_one(
                    {"_id": pr["_id"]},
                    {"$pull": {"task_ids": tid}, "$set": {"reinforced_count": rc}},
                )
    except Exception:
        log.exception("on_falsified: evict principles failed")

    # RAG '우수예시' 강등 — best_score를 임계 아래로 낮춰 ≥80 필터에서 제외
    oid = _oid(task_id)
    if oid is not None:
        try:
            db[TASKS].update_one(
                {"_id": oid},
                {"$set": {"best_score": 0, "learning_verified": False, "falsified": True}},
            )
        except Exception:
            pass
    log.info("🧹 [truth-gate] falsified learning evicted for task=%s (%s)", tid, reason)
