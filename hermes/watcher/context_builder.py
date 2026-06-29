"""
Context Builder — Task + 스코프 기반으로 Hermes에게 전달할 컨텍스트 번들 조립

단계:
  1. 작성자/팀/롤/프로젝트 추론 (user_name_resolver)
  2. 스코프 메모리 로드 (scoped_memory_loader)
  3. MongoDB 관련 문서 프리패치 (code_expert, design_expert 등)
  4. 이전 Hermes 세션 링크 조회 (동일 task 재호출 시)
  5. 모든 걸 번들로 묶어 반환

반환 타입:
  {
    "task": dict,                 # 원본 task
    "scope": dict,                # team/role/project/user
    "memory_files": list[dict],   # 로드된 MD 파일들
    "related_docs": list[dict],   # MongoDB 관련 문서
    "session_link": dict | None,  # 이전 Hermes 세션 정보
    "token_estimate": int,        # 대략적 토큰 수
  }
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pymongo import MongoClient

from user_name_resolver import resolve_scope_from_task
from scoped_memory_loader import load_scoped_memory, estimate_total_tokens

log = logging.getLogger("context-builder")


MONGO_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("MONGODB_DB", "aigame")


# ──────────────────────────────────────────────
# MongoDB 연결 (재사용)
# ──────────────────────────────────────────────
_client: MongoClient | None = None


def _get_db():
    global _client
    if _client is None:
        if not MONGO_URI:
            log.warning("MONGODB_URI not set — related_docs prefetch disabled")
            return None
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client[DB_NAME]


# ──────────────────────────────────────────────
# 관련 문서 프리패치
# ──────────────────────────────────────────────
def _prefetch_related_docs(task: dict[str, Any], scope: dict[str, Any]) -> list[dict[str, Any]]:
    """
    task title/description에서 키워드 추출 → MongoDB에서 관련 문서 조회.

    규칙:
      - "balance" 또는 "밸런스" 포함 → design_expert에서 balance 관련
      - "code" 또는 "구현" 포함 → code_expert에서 해당 장르
      - "설계" 포함 → design_expert 최근 10개
      - 프로젝트명 포함 → 그 프로젝트 관련 Expert 문서

    경량 조회만 수행 — 많이 가져오지 않음 (LLM 컨텍스트 경제).
    """
    db = _get_db()
    if db is None:
        return []

    text = f"{task.get('title', '')} {task.get('description', '')}".lower()
    genre = scope.get("genre")
    project = scope.get("project")
    docs: list[dict[str, Any]] = []

    try:
        # 1. 밸런스 관련
        if any(kw in text for kw in ["balance", "밸런스", "난이도", "클리어율"]):
            for d in db.design_expert.find(
                {"docId": {"$regex": "balance|difficulty", "$options": "i"}},
                projection={"_id": 0, "docId": 1, "summary": 1, "score": 1},
            ).limit(3):
                docs.append({"source": "design_expert", "doc": d})

        # 2. 코드 관련
        if any(kw in text for kw in ["code", "구현", "manager", "system"]):
            query: dict[str, Any] = {"score": {"$gte": 0.6}}
            if genre:
                query["genre"] = genre
            for d in db.code_expert.find(
                query,
                projection={"_id": 0, "fileId": 1, "role": 1, "system": 1, "score": 1, "provides": 1, "requires": 1},
            ).sort("score", -1).limit(5):
                docs.append({"source": "code_expert", "doc": d})

        # 3. 프로젝트 관련
        if project:
            for d in db.design_expert.find(
                {"$or": [
                    {"project": project},
                    {"docId": {"$regex": project, "$options": "i"}},
                ]},
                projection={"_id": 0, "docId": 1, "summary": 1, "score": 1},
            ).limit(3):
                docs.append({"source": "design_expert", "doc": d})

        # 4. 규칙(rules) 해당 장르
        if genre:
            for d in db.rules.find(
                {"genre": genre},
                projection={"_id": 0, "rule": 1, "pattern": 1},
            ).limit(5):
                docs.append({"source": "rules", "doc": d})

    except Exception:
        log.exception("Failed to prefetch related docs (continuing anyway)")

    log.debug("Prefetched %d related docs", len(docs))
    return docs


# ──────────────────────────────────────────────
# 메인: 컨텍스트 빌드
# ──────────────────────────────────────────────
def _detect_pipeline_hint(task: dict[str, Any]) -> str | None:
    """
    task의 태그/키워드에서 파이프라인 종류를 감지.
    감지 시 _shared/<pipeline_hint>/ 디렉토리의 표준이 메모리에 추가 로드됨.

    현재 지원:
      - 'design': 기획/플랜/콘텐츠/레벨/LiveOps 관련 키워드
      - 'dev':    Unity/코드/스크립트/프리팹/씬 관련 키워드
      - 'art':    스프라이트/애니메이션/머티리얼/아트 관련 키워드
    """
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()
    DESIGN_TRIGGERS = (
        "[기획]", "[design]", "[plan]", "[content]", "[level]", "[liveops]", "[live_ops]",
        "기획서", "기획 문서", "design doc", "design document",
        "beat chart", "beat_chart", "비트차트",
        "기믹 명세", "gimmick spec",
        "레벨 디자인", "level design",
        "balance sheet", "밸런스 시트",
        "시즌 패스", "season pass",
        "이벤트 기획", "event design",
    )
    DEV_TRIGGERS = (
        "[dev]", "[unity]", "[code]", "[prefab]", "[scene]", "[script]",
        "unity 수정", "prefab", "scriptableobject", "monobehaviour",
        "코드 수정", "스크립트 수정", "버그 수정", "refactor",
        "objectpool", "serializefield",
    )
    ART_TRIGGERS = (
        "[art]", "[sprite]", "[animation]", "[atlas]", "[material]",
        "스프라이트", "애니메이션", "머티리얼", "아틀라스",
        "아트 작업", "art asset", "리소스 교체",
    )
    if any(t in text for t in DESIGN_TRIGGERS):
        return 'design'
    if any(t in text for t in DEV_TRIGGERS):
        return 'dev'
    if any(t in text for t in ART_TRIGGERS):
        return 'art'
    return None


def build_context(task: dict[str, Any]) -> dict[str, Any]:
    """
    Task에서 출발하여 Hermes에게 전달할 완전한 컨텍스트 번들 조립.
    """
    # 1. 스코프 추론
    scope = resolve_scope_from_task(task)

    # 1b. 파이프라인 힌트 (design 등) — _shared/<hint>/ 표준 추가 로드용
    pipeline_hint = _detect_pipeline_hint(task)

    # 2. 메모리 로드
    memory_files = load_scoped_memory(
        team=scope.get("team"),
        genre=scope.get("genre"),
        role=scope.get("role"),
        project=scope.get("project"),
        slack_id=(scope.get("user") or {}).get("slack_id") if scope.get("user") else None,
        include_user_private=False,  # ProjectHub는 공용 채널이라 개인 메모리 제외
        pipeline_hint=pipeline_hint,
    )

    # 3. 관련 문서 프리패치
    related_docs = _prefetch_related_docs(task, scope)

    # 4. 세션 링크 조회 (같은 task 재호출이면 이전 세션 이어받기)
    session_link = _get_session_link(str(task.get("_id")))

    # 5. 토큰 추정
    token_estimate = estimate_total_tokens(memory_files)
    # 관련 문서도 대략 포함 (각 문서 200 토큰 가정)
    token_estimate += len(related_docs) * 200

    bundle = {
        "task": task,
        "scope": scope,
        "memory_files": memory_files,
        "related_docs": related_docs,
        "session_link": session_link,
        "token_estimate": token_estimate,
    }

    log.info(
        "Context built: scope=%s, memory=%d files, related=%d docs, ~%d tokens",
        {k: v for k, v in scope.items() if k != "user"},
        len(memory_files),
        len(related_docs),
        token_estimate,
    )
    return bundle


# ──────────────────────────────────────────────
# Session link (projecthub_settings 활용)
# ──────────────────────────────────────────────
def _get_session_link(task_id: str) -> dict[str, Any] | None:
    """
    이전에 이 task를 Hermes가 처리했다면 session_id를 이어받음.
    (ProjectHub 스키마 무수정 — projecthub_settings 컬렉션 사용)
    """
    db = _get_db()
    if db is None:
        return None
    try:
        doc = db["projecthub_settings"].find_one({"key": "hermes_sessions"})
        if not doc:
            return None
        mapping = doc.get("mapping", {})
        return mapping.get(task_id)
    except Exception:
        log.exception("Failed to get session link")
        return None
