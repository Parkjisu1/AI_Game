"""
Hermes Node Journal — 실행 노드의 실시간 in-flight 상태 + task별 변경파일 기록.

Phase 1 노드엔진 연결 (1)+(4):
  - mark_start/mark_finish: invoke_agent(=노드 실행)의 running→done/failed 상태.
    → ProjectHub /balloonflow G1 라이브 뷰가 '지금 실행 중'을 정밀 표시.
  - record_files: dev 파이프라인의 changed_files를 기록. → G1 실행 노드 ↔ G2 코드그래프 연결
    (어느 작업이 어떤 실제 코드 파일을 건드렸는지).

컬렉션: hermes_node_runs
  run 문서:  {task_id, role, model, status: running|done|failed, started_at, ended_at}
  files 문서: {task_id, kind:"files", files:[...], created_at}

모든 함수는 graceful — 실패해도 본 실행을 절대 방해하지 않는다(조용히 무시).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("node-journal")

_client = None


def _coll():
    global _client
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        return None
    try:
        if _client is None:
            from pymongo import MongoClient
            _client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        c = _client[os.environ.get("MONGODB_DB", "aigame")]["hermes_node_runs"]
        return c
    except Exception:
        log.debug("node_runs coll failed", exc_info=True)
        return None


def mark_start(task_id: Optional[str], role: str, model: str = "") -> Optional[Any]:
    """노드 실행 시작 — running 문서 삽입. _id 반환(mark_finish에 전달)."""
    if not task_id:
        return None
    c = _coll()
    if c is None:
        return None
    try:
        r = c.insert_one({
            "task_id": str(task_id),
            "role": role,
            "model": model,
            "status": "running",
            "started_at": datetime.now(timezone.utc),
        })
        return r.inserted_id
    except Exception:
        log.debug("mark_start failed", exc_info=True)
        return None


def mark_finish(run_id: Optional[Any], success: bool) -> None:
    """노드 실행 완료 — running 문서를 done/failed로 갱신."""
    if run_id is None:
        return
    c = _coll()
    if c is None:
        return
    try:
        c.update_one(
            {"_id": run_id},
            {"$set": {"status": "done" if success else "failed", "ended_at": datetime.now(timezone.utc)}},
        )
    except Exception:
        log.debug("mark_finish failed", exc_info=True)


def record_files(task_id: Optional[str], files: list[str]) -> None:
    """dev 파이프라인 changed_files 기록 — G1↔G2 연결용."""
    if not task_id or not files:
        return
    c = _coll()
    if c is None:
        return
    try:
        c.insert_one({
            "task_id": str(task_id),
            "kind": "files",
            "files": [str(f) for f in files][:60],
            "created_at": datetime.now(timezone.utc),
        })
    except Exception:
        log.debug("record_files failed", exc_info=True)
