"""
H1 Resilience — retry + circuit breaker + fallback chain.

3가지 핵심 컴포넌트:

1. categorize_error(exc) → "transient" | "permanent" | "quota" | "unknown"
   raised exception을 판별 — retry 할지, 영구 실패인지, rate limit인지.

2. with_retry(policy)  decorator
   transient/quota만 retry. 지수 백오프. timeout_total 예산 강제.

3. CircuitBreaker(key)
   per-model 실패율 추적. failure_threshold 도달 시 open → 일정 시간 reject.
   open_duration 후 half-open → 1회 시험 → success면 close, 실패면 다시 open.

4. FallbackChain([models])
   Primary model 실패면 다음 모델 시도. circuit-open 인 모델은 skip.

설계 원칙:
- in-process state (multi-process 시 각자 own state — v1)
- 모든 call이 thread-safe
- 결정성 — 같은 에러는 같은 카테고리로 분류
- 보수적 — 애매하면 transient (retry 한다) 분류
"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypeVar

log = logging.getLogger("harness.resilience")

T = TypeVar("T")


# ──────────────────────────────────────────────
# Custom exceptions
# ──────────────────────────────────────────────
class HarnessError(Exception):
    """Base for all harness-raised errors."""


class TransientError(HarnessError):
    """일시적 실패 — retry 가치 있음. (5xx, 네트워크, timeout)"""


class PermanentError(HarnessError):
    """영구 실패 — retry 무의미. (4xx auth, malformed request)"""


class QuotaError(HarnessError):
    """rate limit / 토큰 한도 — 별도 처리 (대기 후 retry, 또는 fallback)"""


class CircuitOpenError(HarnessError):
    """Circuit이 열려있어 호출 거부됨."""


class FallbackExhaustedError(HarnessError):
    """모든 fallback 모델이 실패."""


# ──────────────────────────────────────────────
# Error categorization
# ──────────────────────────────────────────────

# regex/substring 패턴 — 에러 메시지 기반 분류
_TRANSIENT_HINTS = [
    "connection", "timeout", "timed out", "broken pipe", "reset by peer",
    "temporary", "service unavailable", "bad gateway", "gateway timeout",
    "502", "503", "504", "internal server error", "500",
    "EOF occurred", "ssl",
    # Claude CLI specific
    "exceeded the quota for tokens (try again later)",
    "request_id",  # transient request_id mentions in errors usually retriable
    # Subprocess/SSH transient
    "Connection refused", "no route to host",
]

_PERMANENT_HINTS = [
    "401", "403", "unauthorized", "authentication", "invalid api key",
    "permission denied", "forbidden",
    "404", "not found",
    "400", "bad request", "invalid",
    "model not found", "model_not_found",
    # Claude CLI
    "Invalid model",
]

_QUOTA_HINTS = [
    "429", "rate limit", "rate-limit", "too many requests",
    "quota", "usage limit",
    "credit balance",  # OpenAI billing
    # Anthropic specific
    "anthropic-ratelimit",
]


def categorize_error(exc: BaseException) -> str:
    """
    에러를 4 카테고리 중 하나로 분류.

    Returns: "transient" | "permanent" | "quota" | "unknown"
    """
    # 우선 우리 custom exception 직접 분류
    if isinstance(exc, TransientError):
        return "transient"
    if isinstance(exc, PermanentError):
        return "permanent"
    if isinstance(exc, QuotaError):
        return "quota"
    if isinstance(exc, CircuitOpenError):
        return "transient"  # circuit open은 시간 지나면 재시도 가능

    msg = str(exc).lower()

    # quota 우선 체크 (transient/permanent보다 더 specific)
    for hint in _QUOTA_HINTS:
        if hint.lower() in msg:
            return "quota"

    # transient 체크
    for hint in _TRANSIENT_HINTS:
        if hint.lower() in msg:
            return "transient"

    # permanent 체크
    for hint in _PERMANENT_HINTS:
        if hint.lower() in msg:
            return "permanent"

    # Python 내장 exception 분류
    exc_name = type(exc).__name__.lower()
    if any(k in exc_name for k in ("timeout", "connection", "ssl", "network")):
        return "transient"
    if any(k in exc_name for k in ("notimplemented", "value", "type", "key", "attribute")):
        # 프로그래밍 에러 — 영구
        return "permanent"

    # subprocess returncode != 0 + stderr 짧은 경우 — 보수적으로 transient
    return "unknown"


def is_retryable(category: str) -> bool:
    """Retry 가능 카테고리?"""
    return category in {"transient", "quota"}


# ──────────────────────────────────────────────
# Retry policy + decorator
# ──────────────────────────────────────────────
@dataclass
class RetryPolicy:
    max_retries: int = 3            # 첫 시도 제외 추가 시도 횟수
    base_delay: float = 1.0          # 첫 retry 대기 (초)
    max_delay: float = 30.0          # 최대 대기
    timeout_total: float = 600.0     # 모든 retry 합쳐서 deadline (초)
    jitter: float = 0.3              # ±jitter*delay 랜덤

    def compute_delay(self, attempt: int) -> float:
        """attempt: 1 = 첫 retry, 2 = 두번째 retry…"""
        d = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
        if self.jitter > 0:
            d *= 1 + random.uniform(-self.jitter, self.jitter)
        return max(0.1, d)


DEFAULT_POLICY = RetryPolicy()
QUOTA_POLICY = RetryPolicy(max_retries=2, base_delay=10.0, max_delay=60.0)


def with_retry(
    policy: Optional[RetryPolicy] = None,
    *, on_retry: Optional[Callable[[int, str, BaseException], None]] = None,
):
    """
    Decorator: transient/quota 에러 시 자동 재시도.

    permanent 에러는 즉시 raise (retry 안 함).
    timeout_total 초과 시 마지막 에러 raise.
    """
    pol = policy or DEFAULT_POLICY

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T:
            start = time.monotonic()
            last_exc: Optional[BaseException] = None
            for attempt in range(pol.max_retries + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as e:
                    last_exc = e
                    cat = categorize_error(e)
                    if not is_retryable(cat):
                        log.info("[retry] %s — permanent (%s) — no retry", type(e).__name__, cat)
                        raise
                    elapsed = time.monotonic() - start
                    if elapsed >= pol.timeout_total:
                        log.warning("[retry] timeout_total %.0fs reached after attempt %d", pol.timeout_total, attempt + 1)
                        raise
                    if attempt >= pol.max_retries:
                        log.warning("[retry] max_retries %d reached", pol.max_retries)
                        raise
                    delay = pol.compute_delay(attempt + 1)
                    if cat == "quota":
                        # quota는 더 길게 대기
                        delay = max(delay, QUOTA_POLICY.compute_delay(attempt + 1))
                    log.info("[retry %d/%d] %s (%s) — sleep %.1fs",
                             attempt + 1, pol.max_retries, type(e).__name__, cat, delay)
                    if on_retry:
                        try:
                            on_retry(attempt + 1, cat, e)
                        except Exception:
                            log.exception("on_retry callback failed")
                    time.sleep(delay)
            # unreachable but keep mypy happy
            assert last_exc is not None
            raise last_exc
        wrapper.__wrapped__ = fn  # type: ignore
        return wrapper
    return decorator


# ──────────────────────────────────────────────
# Circuit Breaker (per-model in-process state)
# ──────────────────────────────────────────────
@dataclass
class _CircuitState:
    state: str = "closed"        # "closed" | "open" | "half_open"
    failures: int = 0
    successes: int = 0
    last_failure_at: float = 0.0
    opened_at: float = 0.0


class CircuitBreaker:
    """
    Per-key circuit. failure_threshold 연속 실패 시 open → reject_for 동안 거부.
    그 이후 half-open → 첫 호출만 통과 → 성공이면 close, 실패면 다시 open.

    Usage:
        cb = CircuitBreaker("model:claude-opus-4-7")
        with cb.call():
            ... # 실패 시 cb가 자동 record
    """

    # class-level state (process 전역 — 모든 인스턴스 공유)
    _states: dict[str, _CircuitState] = {}
    _lock = threading.Lock()

    def __init__(
        self,
        key: str,
        *,
        failure_threshold: int = 5,
        reject_for: float = 60.0,         # open → half_open 전환까지 (초)
        success_threshold: int = 2,        # half_open에서 close 까지 필요한 연속 성공
    ):
        self.key = key
        self.failure_threshold = failure_threshold
        self.reject_for = reject_for
        self.success_threshold = success_threshold

    def _get(self) -> _CircuitState:
        with self._lock:
            if self.key not in self._states:
                self._states[self.key] = _CircuitState()
            return self._states[self.key]

    def is_open(self) -> bool:
        """open 또는 half_open이면 true. half_open은 1회만 시도 허용."""
        s = self._get()
        if s.state == "closed":
            return False
        if s.state == "open":
            # reject_for 초 지나면 half_open으로 자동 전환
            if time.monotonic() - s.opened_at > self.reject_for:
                with self._lock:
                    s.state = "half_open"
                    s.successes = 0
                log.info("[cb:%s] open → half_open", self.key)
                return False  # 이번 호출 통과
            return True
        # half_open — 통과 (다음 record가 결정)
        return False

    def record_success(self) -> None:
        s = self._get()
        with self._lock:
            if s.state == "half_open":
                s.successes += 1
                if s.successes >= self.success_threshold:
                    s.state = "closed"
                    s.failures = 0
                    log.info("[cb:%s] half_open → closed", self.key)
            elif s.state == "closed":
                # 연속 성공이면 failure 카운터 리셋
                s.failures = 0

    def record_failure(self, error_category: str = "unknown") -> None:
        s = self._get()
        with self._lock:
            s.failures += 1
            s.last_failure_at = time.monotonic()
            # quota는 circuit open 안 함 (외부 요인)
            if error_category == "quota":
                return
            if s.state == "half_open":
                s.state = "open"
                s.opened_at = time.monotonic()
                log.warning("[cb:%s] half_open → open (재실패)", self.key)
            elif s.state == "closed" and s.failures >= self.failure_threshold:
                s.state = "open"
                s.opened_at = time.monotonic()
                log.warning("[cb:%s] closed → open (failures=%d)", self.key, s.failures)

    @classmethod
    def reset(cls, key: Optional[str] = None) -> None:
        """수동 reset — 테스트/관리용."""
        with cls._lock:
            if key is None:
                cls._states.clear()
            else:
                cls._states.pop(key, None)

    @classmethod
    def snapshot(cls) -> dict[str, dict[str, Any]]:
        """모든 circuit 상태 — observability."""
        with cls._lock:
            out: dict[str, dict[str, Any]] = {}
            for k, s in cls._states.items():
                out[k] = {
                    "state": s.state,
                    "failures": s.failures,
                    "successes": s.successes,
                    "opened_for_sec": (
                        time.monotonic() - s.opened_at if s.state == "open" else 0
                    ),
                }
            return out

    def call(self):
        """Context manager. 실패 시 자동 record. 성공 시 자동 record."""
        return _CircuitGuard(self)


class _CircuitGuard:
    def __init__(self, cb: CircuitBreaker):
        self.cb = cb

    def __enter__(self):
        if self.cb.is_open():
            raise CircuitOpenError(f"circuit open: {self.cb.key}")
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc is None:
            self.cb.record_success()
            return False
        cat = categorize_error(exc)
        self.cb.record_failure(cat)
        return False  # re-raise


# ──────────────────────────────────────────────
# Fallback chain
# ──────────────────────────────────────────────
class FallbackChain:
    """
    Primary 모델 실패 시 다음 모델 시도. circuit-open 모델은 skip.

    Usage:
        chain = FallbackChain(["claude-opus-4-7", "gpt-4o", "gpt-4o-mini"])
        result = chain.execute(lambda model: call_llm(model, prompt))
    """

    def __init__(self, models: list[str]):
        if not models:
            raise ValueError("FallbackChain requires at least 1 model")
        self.models = models

    def execute(
        self, fn: Callable[[str], T],
        *, retry_policy: Optional[RetryPolicy] = None,
    ) -> T:
        """
        각 모델에 대해 retry 적용 후 실패하면 다음 모델로.
        permanent 에러는 즉시 raise (다음 모델로 안 넘어감 — auth 같은 건 다른 모델도 같은 키 쓰면 같은 결과).
        """
        last_exc: Optional[BaseException] = None
        attempted: list[str] = []
        for model in self.models:
            cb = CircuitBreaker(f"model:{model}")
            if cb.is_open():
                log.info("[fallback] skip %s (circuit open)", model)
                continue
            attempted.append(model)
            try:
                wrapped = with_retry(retry_policy)(lambda m=model: self._guarded_call(fn, m, cb))
                return wrapped()
            except CircuitOpenError as e:
                last_exc = e
                continue
            except Exception as e:
                cat = categorize_error(e)
                last_exc = e
                if cat == "permanent":
                    log.warning("[fallback] permanent error on %s — abort chain: %s", model, e)
                    raise
                log.warning("[fallback] %s failed (%s) — try next", model, cat)
                continue
        raise FallbackExhaustedError(
            f"all fallbacks exhausted: tried {attempted} of {self.models}"
        ) from last_exc

    @staticmethod
    def _guarded_call(fn: Callable[[str], T], model: str, cb: CircuitBreaker) -> T:
        with cb.call():
            return fn(model)


# ──────────────────────────────────────────────
# Self-test
# ──────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # 1. categorize_error
    cases = [
        (ConnectionError("connection refused"), "transient"),
        (TimeoutError("timed out"), "transient"),
        (RuntimeError("HTTP 502 Bad Gateway"), "transient"),
        (RuntimeError("401 Unauthorized"), "permanent"),
        (RuntimeError("429 Too Many Requests"), "quota"),
        (RuntimeError("rate limit exceeded"), "quota"),
        (ValueError("invalid"), "permanent"),
        (RuntimeError("something weird"), "unknown"),
    ]
    print("\n[categorize_error]")
    for exc, expected in cases:
        actual = categorize_error(exc)
        ok = "✓" if actual == expected else "✗"
        print(f"  {ok} {type(exc).__name__:20s} → {actual:10s} (expected {expected})")

    # 2. retry decorator
    print("\n[with_retry]")
    attempt_count = {"n": 0}

    @with_retry(RetryPolicy(max_retries=3, base_delay=0.1, max_delay=0.3, jitter=0))
    def flaky():
        attempt_count["n"] += 1
        if attempt_count["n"] < 3:
            raise ConnectionError("transient")
        return "ok"

    result = flaky()
    print(f"  ✓ flaky() succeeded after {attempt_count['n']} attempts → {result}")

    # 3. CircuitBreaker
    print("\n[CircuitBreaker]")
    CircuitBreaker.reset()
    cb = CircuitBreaker("test:demo", failure_threshold=3, reject_for=0.5)

    # 3 failures → open
    for i in range(3):
        try:
            with cb.call():
                raise ConnectionError("fail")
        except ConnectionError:
            pass
    snap = CircuitBreaker.snapshot()
    print(f"  after 3 failures: {snap.get('test:demo')}")
    assert snap["test:demo"]["state"] == "open"

    # circuit-open rejects immediately
    try:
        with cb.call():
            pass
        print("  ✗ should have raised CircuitOpenError")
    except CircuitOpenError:
        print(f"  ✓ open circuit rejected next call")

    # wait for half_open + success → closed
    time.sleep(0.6)
    for _ in range(2):
        with cb.call():
            pass
    snap = CircuitBreaker.snapshot()
    print(f"  after 2 successes: {snap.get('test:demo')}")
    assert snap["test:demo"]["state"] == "closed"

    # 4. FallbackChain
    print("\n[FallbackChain]")
    CircuitBreaker.reset()
    call_log: list[str] = []

    def call_model(m: str) -> str:
        call_log.append(m)
        if m == "primary":
            raise ConnectionError("primary down")
        return f"got:{m}"

    chain = FallbackChain(["primary", "secondary"])
    result = chain.execute(call_model, retry_policy=RetryPolicy(max_retries=1, base_delay=0.05))
    print(f"  ✓ chain result: {result} (calls: {call_log})")
    assert result == "got:secondary"

    # permanent error aborts chain
    CircuitBreaker.reset()
    call_log.clear()

    def call_perm(m: str) -> str:
        call_log.append(m)
        raise ValueError("invalid request")

    try:
        FallbackChain(["a", "b"]).execute(call_perm, retry_policy=RetryPolicy(max_retries=0, base_delay=0.05))
        print("  ✗ should have raised")
    except ValueError:
        print(f"  ✓ permanent error aborts chain (calls: {call_log})")
    assert call_log == ["a"]

    print("\n✅ all H1 self-tests passed")
