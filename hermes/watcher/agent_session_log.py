"""
Agent Session Log — 에이전트 호출 기록 + 재작업 시 과거 맥락 조회

MongoDB 컬렉션 `hermes_agent_sessions`에 invoke_agent 호출마다 한 레코드 저장.
- record_invocation: 호출 완료 후 저장
- find_for_task: 특정 task_id의 최근 호출들 반환 (재작업 시 Lead 프롬프트에 주입)

장기적으로 Hermes CLI의 FTS5로 이전하면 이 모듈의 인터페이스만 유지하면 된다.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("agent-session-log")

MONGO_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("MONGODB_DB", "aigame")
COLLECTION = "hermes_agent_sessions"
_MAX_PREVIEW_CHARS = 2000  # 저장할 prompt/output 앞부분 크기

_client = None
_indexes_ensured = False


def _get_collection():
    """MongoDB 컬렉션 핸들. 최초 호출 시 인덱스 보장."""
    global _client, _indexes_ensured
    if not MONGO_URI:
        return None
    if _client is None:
        try:
            from pymongo import MongoClient
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        except Exception:
            log.exception("MongoClient init failed")
            return None
    try:
        coll = _client[DB_NAME][COLLECTION]
        if not _indexes_ensured:
            try:
                coll.create_index([("task_id", 1), ("created_at", -1)])
                _indexes_ensured = True
            except Exception:
                log.debug("index ensure failed (non-fatal)", exc_info=True)
        return coll
    except Exception:
        log.exception("get_collection failed")
        return None


def record_invocation(
    task_id: Optional[str],
    task_title: str,
    role: str,
    model: str,
    prompt: str,
    output: str,
    structured: Optional[dict[str, Any]],
    duration_sec: float,
    success: bool,
    error: Optional[str],
) -> None:
    """에이전트 호출 1회를 기록. 실패해도 조용히 무시."""
    if not task_id:
        return  # 세션 로깅은 task 맥락에서만 의미
    coll = _get_collection()
    if coll is None:
        return
    try:
        doc = {
            "task_id": str(task_id),
            "task_title": (task_title or "")[:200],
            "role": role,
            "model": model,
            "prompt_preview": (prompt or "")[:_MAX_PREVIEW_CHARS],
            "prompt_len": len(prompt or ""),
            "output_preview": (output or "")[:_MAX_PREVIEW_CHARS],
            "output_len": len(output or ""),
            "structured": structured if isinstance(structured, dict) else None,
            "duration_sec": float(duration_sec or 0.0),
            "success": bool(success),
            "error": error,
            "created_at": datetime.now(timezone.utc),
        }
        coll.insert_one(doc)
    except Exception:
        log.exception("record_invocation failed (non-fatal)")

    # 벡터 임베딩 — Sub PC Qdrant에 기록 (fire-and-forget)
    try:
        from hermes_embedding_client import record_session_embedding
        record_session_embedding(
            task_id=str(task_id),
            task_title=task_title or "",
            role=role or "",
            model=model or "",
            content=(output or "")[:_MAX_PREVIEW_CHARS],
            success=bool(success),
        )
    except Exception:
        log.debug("session embedding skipped", exc_info=True)


def find_for_task(task_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """이 task_id로 기록된 과거 세션들 — 최신 순. 없으면 빈 리스트."""
    if not task_id:
        return []
    coll = _get_collection()
    if coll is None:
        return []
    try:
        cursor = (
            coll.find({"task_id": str(task_id)})
            .sort("created_at", -1)
            .limit(limit)
        )
        return list(cursor)
    except Exception:
        log.exception("find_for_task failed")
        return []


def format_rework_context(task_id: str, max_entries: int = 8, max_chars: int = 5000) -> str:
    """
    재작업 시 Lead 프롬프트에 주입할 '이전 시도 로그' 섹션 문자열.
    직전부터 최대 max_entries개 세션을, max_chars 안에 들어가게 조립.
    """
    sessions = find_for_task(task_id, limit=max_entries)
    if not sessions:
        return ""
    # 오래된 것 → 최신 순으로 보여주는 게 시간 흐름 이해에 좋음
    sessions = list(reversed(sessions))
    lines = ["\n## 📒 이전 Hermes 시도 로그 (참고용 — 같은 실수 반복 금지)\n"]
    used = 0
    for s in sessions:
        header = (
            f"### [{s.get('role', '?')}/{s.get('model', '?')}] "
            f"{'✓' if s.get('success') else '✗'} "
            f"({s.get('duration_sec', 0):.1f}s, {s.get('output_len', 0)}자)"
        )
        body_parts = []
        if s.get("error"):
            body_parts.append(f"  - error: {str(s['error'])[:300]}")
        output_preview = (s.get("output_preview") or "").strip()
        if output_preview:
            snippet = output_preview[:600]
            body_parts.append(f"  - output: {snippet}")
        struct = s.get("structured")
        if isinstance(struct, dict):
            summary = struct.get("summary")
            files = struct.get("files_modified")
            if summary:
                body_parts.append(f"  - summary: {str(summary)[:300]}")
            if isinstance(files, list) and files:
                body_parts.append(f"  - files_modified: {files[:10]}")
        block = header + "\n" + "\n".join(body_parts) + "\n"
        if used + len(block) > max_chars:
            lines.append("...(이전 로그 생략)")
            break
        lines.append(block)
        used += len(block)
    return "\n".join(lines)
