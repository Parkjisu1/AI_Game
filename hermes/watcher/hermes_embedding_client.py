"""
Hermes 임베딩 + 벡터 검색 클라이언트.

아키텍처:
  Sub PC (100.87.87.59)
    ├── Ollama :11434 — nomic-embed-text (768차원)
    └── Qdrant :6333 — SSH 터널로 Mother의 127.0.0.1:6333으로 포워딩됨

컬렉션:
  - hermes_text_memory  : agent_session_log 기록 시 자동 임베딩
  - hermes_code_index   : Balloonflow C# 코드 청크 (별도 인덱서로 채움)

용도:
  1. record_session_embedding(...) — 에이전트 호출마다 벡터 저장
  2. search_similar_sessions(...) — 과거 유사 태스크 검색 (Lead 프롬프트에 주입)
  3. search_similar_code(...)    — Main Coder에게 유사 코드 참조 제공

장애 대응: Ollama/Qdrant 접근 실패는 조용히 skip (파이프라인 영향 0).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional
from uuid import uuid4

log = logging.getLogger("hermes-embedding")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.87.87.59:11434")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
# nomic-embed-text 는 한국어를 판별하지 못한다.
# 2026-09-09 실측: 무관한 한국어 문장쌍 cos 0.996 / 유사한 쌍 0.997 — 격차 0.001.
# Hermes 의 태스크 설명과 검색 쿼리는 전부 한국어라, 어떤 질의를 넣어도
# 같은 결과가 나오는 상태였다(검색이 사실상 무작위).
# bge-m3 는 같은 실측에서 격차 0.264. 차원이 768 -> 1024 이므로 컬렉션도 함께 옮긴다.
EMBEDDING_MODEL = os.environ.get("HERMES_EMBED_MODEL", "bge-m3")
EMBEDDING_DIM = 1024

COLL_TEXT = os.environ.get("HERMES_TEXT_COLLECTION", "hermes_text_memory_m3")  # 464 pts, 1024d bge-m3
COLL_CODE = "hermes_code_index"  # legacy (empty)
COLL_CODE_CHUNKS = os.environ.get("HERMES_CODE_COLLECTION", "gf_code_chunks_m3")  # 7,778 pts, 1024d bge-m3

# 한 텍스트당 Ollama에 보낼 최대 문자 수 (너무 길면 품질↓ + latency↑)
MAX_EMBED_INPUT_CHARS = 8000


def _embed(text: str) -> Optional[list[float]]:
    """
    텍스트 → 768차원 벡터. 실패 시 None.

    H1 Resilience:
      - retry: 2회 재시도 (transient 에러만)
      - circuit breaker: 5회 연속 실패 시 60초간 immediate-None (Sub PC 다운 시)
    """
    if not text:
        return None
    text = text[:MAX_EMBED_INPUT_CHARS]

    # H1 + H3 wrapping
    try:
        from harness.resilience import (
            with_retry, RetryPolicy, CircuitBreaker, CircuitOpenError,
        )
        from harness.tracing import span as _trace_span
    except ImportError:
        # harness 미설치 시 (테스트/로컬) 폴백
        return _embed_raw(text)

    cb = CircuitBreaker("embedding:ollama", failure_threshold=5, reject_for=60.0)
    if cb.is_open():
        log.debug("[embed] circuit open — return None")
        return None
    policy = RetryPolicy(max_retries=2, base_delay=1.0, max_delay=5.0, timeout_total=30.0)

    @with_retry(policy)
    def _call() -> Optional[list[float]]:
        with cb.call():
            return _embed_raw(text)

    try:
        with _trace_span("embed_text", model=EMBEDDING_MODEL, input_chars=len(text)) as sp:
            vec = _call()
            sp.set_attr("dim", len(vec) if vec else 0)
            return vec
    except CircuitOpenError:
        return None
    except Exception:
        log.debug("[embed] failed after retries", exc_info=True)
        return None


def _embed_raw(text: str) -> Optional[list[float]]:
    """raw 호출 — 재시도/circuit 없는 단발."""
    import httpx
    r = httpx.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBEDDING_MODEL, "input": text},
        timeout=15.0,
    )
    r.raise_for_status()
    data = r.json()
    embeddings = data.get("embeddings") or []
    if not embeddings:
        return None
    vec = embeddings[0] if isinstance(embeddings[0], list) else embeddings
    if len(vec) != EMBEDDING_DIM:
        log.warning("Unexpected embedding dim: %d (expected %d)", len(vec), EMBEDDING_DIM)
        return None
    return list(map(float, vec))


def _get_qdrant():
    try:
        from qdrant_client import QdrantClient
        return QdrantClient(url=QDRANT_URL, timeout=5.0, check_compatibility=False)
    except Exception:
        log.debug("qdrant client init failed", exc_info=True)
        return None


def record_session_embedding(
    task_id: str,
    task_title: str,
    role: str,
    model: str,
    content: str,
    success: bool,
) -> None:
    """
    세션 로그 한 건을 임베딩해 hermes_text_memory에 저장.
    agent_team.invoke_agent 완료 시점에 호출됨 (fire-and-forget).
    """
    if not task_id or not content:
        return
    vec = _embed(f"{task_title}\n\n[{role}] {content}")
    if vec is None:
        return
    client = _get_qdrant()
    if client is None:
        return
    try:
        from qdrant_client.http.models import PointStruct
        client.upsert(
            collection_name=COLL_TEXT,
            points=[
                PointStruct(
                    id=str(uuid4()),
                    vector=vec,
                    payload={
                        "task_id": task_id,
                        "task_title": task_title[:200],
                        "role": role,
                        "model": model,
                        "success": bool(success),
                        "content_preview": content[:500],
                    },
                )
            ],
        )
    except Exception:
        log.debug("qdrant upsert failed", exc_info=True)


def search_similar_sessions(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    쿼리와 의미상 유사한 과거 세션 반환.
    Lead 프롬프트에 '이전 유사 태스크' 섹션 주입용.
    """
    if not query:
        return []
    vec = _embed(query)
    if vec is None:
        return []
    client = _get_qdrant()
    if client is None:
        return []
    try:
        res = client.query_points(
            collection_name=COLL_TEXT,
            query=vec,
            limit=limit,
            with_payload=True,
        )
        return [
            {
                "score": float(h.score),
                "task_id": h.payload.get("task_id"),
                "task_title": h.payload.get("task_title"),
                "role": h.payload.get("role"),
                "success": h.payload.get("success"),
                "preview": h.payload.get("content_preview"),
            }
            for h in res.points
        ]
    except Exception:
        log.debug("qdrant search failed", exc_info=True)
        return []


def search_similar_code(query: str, limit: int = 5, project: Optional[str] = None) -> list[dict[str, Any]]:
    """쿼리와 유사한 코드 청크 검색. hermes_code_index에서.

    project 가 주어지면 그 프로젝트 청크를 먼저 채우고, 모자라면 전체에서 보충한다
    (2026-09-14: 필터가 없어 러너 요청에 타 게임 코드가 "검증된 유사 코드"로 주입되던 것 수정).
    """
    if not query:
        return []
    vec = _embed(query)
    if vec is None:
        return []
    client = _get_qdrant()
    if client is None:
        return []
    try:
        points = []
        if project:
            try:
                from qdrant_client.http.models import Filter, FieldCondition, MatchValue
                _f = Filter(must=[FieldCondition(key="project", match=MatchValue(value=project))])
                points = list(client.query_points(
                    collection_name=COLL_CODE_CHUNKS, query=vec, limit=limit,
                    with_payload=True, query_filter=_f,
                ).points)
            except Exception:
                log.debug("project-filtered code search failed — falling back to global", exc_info=True)
                points = []
        if len(points) < limit:
            _seen = {p.id for p in points}
            res = client.query_points(
                collection_name=COLL_CODE_CHUNKS,
                query=vec,
                limit=limit,
                with_payload=True,
            )
            points += [p for p in res.points if p.id not in _seen][: limit - len(points)]
        out = []
        for h in points:
            p = h.payload or {}
            content = p.get("content") or p.get("content_preview") or ""
            out.append({
                "score": float(h.score),
                "file": p.get("path") or p.get("file"),
                "project": p.get("project"),
                "lang": p.get("lang"),
                "symbol": p.get("symbol"),
                "preview": content[:1200],
            })
        return out
    except Exception:
        log.debug("qdrant search failed", exc_info=True)
        return []


def format_similar_sessions_section(query: str, limit: int = 5) -> str:
    """Lead 프롬프트에 붙일 '과거 유사 태스크' 마크다운 섹션. 결과 없으면 빈 문자열."""
    hits = search_similar_sessions(query, limit=limit)
    if not hits:
        return ""
    lines = ["\n## 🔎 과거 유사 태스크 (벡터 검색)\n"]
    for h in hits:
        marker = "✓" if h.get("success") else "✗"
        lines.append(
            f"- {marker} [{h.get('role')}] **{h.get('task_title')}** "
            f"(score={h.get('score'):.2f})"
        )
        preview = (h.get("preview") or "").strip().replace("\n", " ")[:200]
        if preview:
            lines.append(f"  > {preview}")
    return "\n".join(lines) + "\n"
