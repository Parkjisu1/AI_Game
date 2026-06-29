"""
H3 Observability — distributed tracing for Hermes pipelines.

핵심 컨셉:
- **trace**: task 단위 전체 작업 (예: "[level] task" 1건의 전체 파이프라인)
- **span**: trace 안의 1개 operation (LLM 호출 1건, 파이프라인 단계 1개 등)
- **trace_id**: trace 식별자 (모든 자식 span이 공유)
- **parent_span_id**: span 트리 구조 (디버깅에 핵심)
- **contextvar 전파**: thread-safe + async-safe하게 자동 전파

사용:
    with tracing.trace_context(task_id="abc123") as trace_id:
        with tracing.span("design_pipeline", task_id="abc123"):
            with tracing.span("invoke_agent", role="designer", model="claude-opus-4-7") as sp:
                sp.set_attr("prompt_length", len(prompt))
                output = call_llm()
                sp.set_attr("output_length", len(output))
            # span 자동 finish, MongoDB에 저장

Storage: hermes_traces 컬렉션
  _id: span_id (uuid hex 16)
  trace_id: str
  parent_span_id: str | None
  span_name: str
  task_id: str | None
  team / sub_team / role / model: 검색용
  status: "ok" | "error" | "in_progress"
  error: str | None
  start_time / end_time: ISO
  duration_ms: int
  attributes: dict (자유 metadata)

쿼리 예:
  - 한 task의 모든 span:    { trace_id: "..." }
  - 에러난 trace:           { status: "error" }
  - 특정 모델 P95 latency:  { "model": "claude-opus-4-7" } + sort by duration_ms

설계 원칙:
- 동기 flush (간단). 다음 H3.5에서 background queue로 변환 가능.
- pymongo 미설치/MongoDB 다운 시 silent fail (트레이싱이 본 작업 막지 않게).
"""

from __future__ import annotations

import contextvars
import logging
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Optional

log = logging.getLogger("harness.tracing")

# Context vars for trace_id / span_id propagation (thread-safe + async-safe)
_current_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_trace_id", default=None
)
_current_span_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_span_id", default=None
)


# ──────────────────────────────────────────────
# Identifier helpers
# ──────────────────────────────────────────────
def new_id() -> str:
    """Fresh ID — 16-char hex (uuid4)."""
    return uuid.uuid4().hex[:16]


def get_trace_id() -> Optional[str]:
    """현재 trace_id 가져오기. trace_context 밖이면 None."""
    return _current_trace_id.get()


def get_span_id() -> Optional[str]:
    """현재 span_id 가져오기."""
    return _current_span_id.get()


# ──────────────────────────────────────────────
# trace_context — task 단위 trace 시작
# ──────────────────────────────────────────────
@contextmanager
def trace_context(
    task_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Iterator[str]:
    """
    Trace 스코프 진입. 모든 자식 span이 이 trace_id 공유.

    task_id가 주어지면 trace_id를 task_id 기반으로 결정성 생성 (디버깅 편의).
    """
    if trace_id is None:
        trace_id = (task_id[-16:] if task_id and len(task_id) >= 8 else new_id())
    token = _current_trace_id.set(trace_id)
    try:
        yield trace_id
    finally:
        _current_trace_id.reset(token)


# ──────────────────────────────────────────────
# Span class
# ──────────────────────────────────────────────
class Span:
    """1개 operation을 나타내는 span. context manager로 사용."""

    def __init__(
        self, name: str, *,
        trace_id: str,
        parent_span_id: Optional[str] = None,
        task_id: Optional[str] = None,
        **attrs: Any,
    ):
        self.span_id = new_id()
        self.name = name
        self.trace_id = trace_id
        self.parent_span_id = parent_span_id
        self.task_id = task_id
        self.start_time = datetime.now(timezone.utc)
        self.end_time: Optional[datetime] = None
        self.status: str = "in_progress"
        self.error: Optional[str] = None
        self.attributes: dict[str, Any] = dict(attrs)

    def set_attr(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def update(self, **kwargs: Any) -> None:
        self.attributes.update(kwargs)

    def finish(self, error: Optional[BaseException] = None) -> None:
        if self.end_time is not None:
            return  # 이미 종료
        self.end_time = datetime.now(timezone.utc)
        if error is not None:
            self.status = "error"
            self.error = f"{type(error).__name__}: {error}"[:500]
        elif self.status == "in_progress":
            self.status = "ok"
        _flush(self)


# ──────────────────────────────────────────────
# MongoDB flush (silent fail safe)
# ──────────────────────────────────────────────
_db_cache: list[Any] = []  # mutable cache for connection (None or db handle)


def _get_db() -> Optional[Any]:
    if _db_cache:
        return _db_cache[0]
    try:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            _db_cache.append(None)
            return None
        db_name = os.environ.get("MONGODB_DB", "aigame")
        db = MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
        _db_cache.append(db)
        return db
    except Exception:
        _db_cache.append(None)
        return None


def _flush(span: Span) -> None:
    """span을 hermes_traces에 저장. 실패해도 본 작업 영향 X.
    H5: PII가 attributes에 들어있을 가능성 — flush 직전 redact.
    """
    db = _get_db()
    if db is None:
        return
    duration_ms = None
    if span.end_time:
        duration_ms = int((span.end_time - span.start_time).total_seconds() * 1000)

    # H5: attributes 안의 PII 마스킹 (재귀)
    safe_attrs = span.attributes
    try:
        from harness.safety import redact_pii_recursive
        safe_attrs = redact_pii_recursive(span.attributes)
    except Exception:
        pass  # safety 미설치 시 raw 그대로

    doc: dict[str, Any] = {
        "_id": span.span_id,
        "trace_id": span.trace_id,
        "parent_span_id": span.parent_span_id,
        "span_name": span.name,
        "task_id": span.task_id,
        "status": span.status,
        "error": span.error,
        "start_time": span.start_time.isoformat(),
        "end_time": span.end_time.isoformat() if span.end_time else None,
        "duration_ms": duration_ms,
    }
    # attributes에서 검색 자주 쓰는 필드 top-level로 promote (redact 후)
    for key in ("team", "sub_team", "role", "model", "team_id", "mood", "style"):
        if key in safe_attrs:
            doc[key] = safe_attrs[key]
    doc["attributes"] = safe_attrs
    try:
        db["hermes_traces"].insert_one(doc)
    except Exception:
        log.debug("trace flush failed", exc_info=True)


# ──────────────────────────────────────────────
# span() — main API
# ──────────────────────────────────────────────
@contextmanager
def span(name: str, **attrs: Any) -> Iterator[Span]:
    """
    새 span 생성. context manager 종료 시 자동 finish.

    예외 발생 시 status='error', error msg 기록 후 re-raise.

    attrs:
      task_id / role / model / team / sub_team 같은 검색 친화 필드는 자동 top-level promote.
      나머지는 attributes dict에 저장.
    """
    trace_id = _current_trace_id.get()
    auto_trace = False
    if trace_id is None:
        # trace_context 밖에서 span() 호출 → 임시 trace_id 자동 생성
        trace_id = new_id()
        trace_token = _current_trace_id.set(trace_id)
        auto_trace = True
    else:
        trace_token = None

    parent_id = _current_span_id.get()
    sp = Span(
        name=name, trace_id=trace_id,
        parent_span_id=parent_id,
        task_id=attrs.pop("task_id", None),
        **attrs,
    )
    span_token = _current_span_id.set(sp.span_id)
    try:
        yield sp
        sp.finish()
    except BaseException as e:  # KeyboardInterrupt도 포함
        sp.finish(error=e)
        raise
    finally:
        _current_span_id.reset(span_token)
        if auto_trace and trace_token:
            _current_trace_id.reset(trace_token)


def current_context() -> dict[str, Optional[str]]:
    """현재 trace context 정보 반환 (디버깅용)."""
    return {
        "trace_id": _current_trace_id.get(),
        "span_id": _current_span_id.get(),
    }


# ──────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    print("[basic span]")
    with trace_context(task_id="test_task_001") as tid:
        print(f"  trace_id={tid}")
        with span("outer", role="lead", model="claude-opus-4-7") as sp1:
            sp1.set_attr("prompt_length", 1234)
            with span("inner_a", role="coder", model="gpt-4o") as sp2:
                sp2.set_attr("output_length", 567)
            with span("inner_b", role="reviewer") as sp3:
                pass
        ctx = current_context()
        print(f"  outer parent_id={sp1.parent_span_id}")
        print(f"  inner_a parent_id={sp2.parent_span_id} (= outer span_id?)")
        assert sp2.parent_span_id == sp1.span_id
        assert sp3.parent_span_id == sp1.span_id

    print("\n[error span]")
    try:
        with span("failing_op", role="reviewer") as sp:
            raise RuntimeError("simulated error")
    except RuntimeError:
        print(f"  span status={sp.status} error={sp.error}")
        assert sp.status == "error"

    print("\n[no trace_context]")
    with span("orphan_span") as sp:
        print(f"  auto trace_id={sp.trace_id} (no outer)")

    print("\n✅ all H3 self-tests passed")
