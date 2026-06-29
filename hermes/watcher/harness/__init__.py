"""
harness — Hermes 모든 LLM 호출을 둘러싸는 5-layer 엔지니어링.

H1 Resilience    — retry, circuit breaker, fallback chain
H2 Validation    — pydantic schema, re-prompt on malformed (예정)
H3 Observability — distributed tracing, trace_id propagation (예정)
H4 Evaluation    — golden test set, regression detect (예정)
H5 Safety        — refusal detect, PII redact, injection guard (예정)

3 surface 적용:
- ProjectHub AI    : invoke_agent in agent_team.py
- Mother LLM       : _invoke_via_litellm HTTP wrapper
- Embedding LLM    : hermes_embedding_client
"""

from harness.resilience import (
    TransientError,
    PermanentError,
    QuotaError,
    CircuitOpenError,
    FallbackExhaustedError,
    RetryPolicy,
    CircuitBreaker,
    FallbackChain,
    categorize_error,
    with_retry,
)

from harness.validation import (
    ValidationResult,
    ROLE_SCHEMAS,
    extract_json,
    validate_role_output,
    build_repair_prompt,
    with_validation,
)

from harness.tracing import (
    Span,
    new_id,
    get_trace_id,
    get_span_id,
    trace_context,
    span,
    current_context,
)

from harness.eval import (
    GoldenCase,
    EvalResult,
    extract_golden_from_levels,
    save_golden_cases,
    load_golden_cases,
    compare_level_specs,
    run_eval_case,
    run_all_eval,
    save_eval_results,
)

from harness.safety import (
    detect_refusal,
    redact_pii,
    redact_pii_recursive,
    detect_injection,
    REFUSAL_PATTERNS,
    PII_PATTERNS,
    INJECTION_PATTERNS,
)

__all__ = [
    # H1
    "TransientError", "PermanentError", "QuotaError",
    "CircuitOpenError", "FallbackExhaustedError",
    "RetryPolicy", "CircuitBreaker", "FallbackChain",
    "categorize_error", "with_retry",
    # H2
    "ValidationResult", "ROLE_SCHEMAS",
    "extract_json", "validate_role_output", "build_repair_prompt",
    "with_validation",
    # H3
    "Span", "new_id", "get_trace_id", "get_span_id",
    "trace_context", "span", "current_context",
]
