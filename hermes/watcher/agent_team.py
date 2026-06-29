"""
Agent Team — 역할 기반 멀티 에이전트 오케스트레이션

현재: 모든 역할이 Claude Code로 라우팅 (OpenAI 키 대기 중)
OpenAI 키 도착 후: AGENT_ROLES 테이블만 업데이트하면 역할별 다른 모델 사용

사용자 차별화 비전:
- 단일 Claude 호출로 끝나면 "로컬 Claude와 뭐가 다름?" 질문 답변 약함
- 역할 기반 분할 + 검증 게이트 + 병렬 처리가 핵심 차별점
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("agent-team")


# ──────────────────────────────────────────────
# 역할 → 모델 매핑
# ProjectHub UI(/agents)에서 편집하면 hermes_agent_roles 컬렉션에 반영.
# 매 invoke_agent 호출마다 _load_agent_roles()가 DB 조회 → DB 비어있으면 DEFAULT.
# ──────────────────────────────────────────────
DEFAULT_AGENT_ROLES: dict[str, dict[str, str]] = {
    "translator": {
        "tool": "litellm",
        "model": "sub-coder-agent",  # 빠른 저가 모델로 충분 — 자연어 해석 + 코드 탐색
        "description": "자연어 태스크 → 기술 요구사항 변환. 정보 부족 시 질문 생성 후 Slack DM으로 생성자에게 확인",
    },
    "lead": {
        "tool": "claude",
        "model": "claude-opus-4-7",
        "description": "태스크 분해, 영향 분석, 작업 계획 수립",
    },
    "main_coder": {
        "tool": "claude",
        "model": "claude-opus-4-7",
        "description": "핵심 아키텍처/복잡 로직 구현",
    },
    "sub_coder": {
        # OpenAI 키 활성화 — gpt-4o-mini via LiteLLM (비용 절감)
        "tool": "litellm",
        "model": "sub-coder-agent",  # LiteLLM alias → openai/gpt-4o-mini
        "description": "병렬 구현 — OpenAI 백엔드로 부하 분산",
    },
    "validator": {
        "tool": "litellm",
        "model": "validator-agent",
        "description": "계약 교차 검증 — OpenAI로 저가 대량 처리",
    },
    "reviewer": {
        "tool": "claude",
        "model": "claude-opus-4-7",
        "description": "최종 품질 게이트 — Claude Max 프리미엄 채널",
    },
    "optimizer": {
        "tool": "claude",
        "model": "claude-opus-4-7",
        "description": "성능 최적화 — GC alloc, 매 프레임 연산, Unity 안티패턴 제거 (기능 변경 금지)",
    },
    "optimization_reviewer": {
        "tool": "litellm",
        "model": "validator-agent",  # 검증 유형이라 저가 모델로 충분
        "description": "최적화가 정확성 깨뜨리지 않고 실제 개선인지 검증",
    },
}

# 하위 호환성: 외부 모듈이 AGENT_ROLES를 참조하면 DEFAULT 값을 노출
AGENT_ROLES = DEFAULT_AGENT_ROLES


_roles_cache: dict[str, dict[str, str]] | None = None
_roles_cache_ts: float = 0.0
_ROLES_CACHE_TTL_SEC = 10.0  # UI 수정 후 최대 10초 반영 지연


# ── Phase 3 보상 체계: 모델 자동 승격 ────────────────────────────────
# 분과의 최근 평균 품질점수가 임계값 미만이면 다음 호출 모델을 한 단계 위로.
# PM/Translator는 분류 역할이라 승격 대상에서 제외 (저비용 유지).
_MODEL_PROMOTION_LADDER = {
    # LiteLLM alias (gpt-4o-mini) → gpt-4o → claude-opus-4-7
    "sub-coder-agent": "gpt-4o",
    "validator-agent": "gpt-4o",
    "gpt-4o-mini":     "gpt-4o",
    "gpt-4o":          "claude-opus-4-7",
}
_PROMOTION_THRESHOLD = 65.0          # 평균 점수 < 65 → 승격
_PROMOTION_MIN_SAMPLES = 5            # 표본 5건 이상에서만 평가
_PROMOTION_LOOKBACK_DAYS = 14         # 최근 2주 점수만 본다
_promoted_log_cache: set[str] = set() # 승격 로그 1회만 출력
_score_cache: dict[tuple[str, str], tuple[float, float, int]] = {}  # (team,sub) -> (ts, avg, count)
_SCORE_CACHE_TTL_SEC = 60.0


def _get_team_score(team: str, sub_team: str) -> Optional[tuple[float, int]]:
    """(평균, 개수) 또는 None. 60초 캐싱."""
    import time as _t
    key = (team or "", sub_team or "general")
    now = _t.monotonic()
    cached = _score_cache.get(key)
    if cached and (now - cached[0]) < _SCORE_CACHE_TTL_SEC:
        return (cached[1], cached[2])
    try:
        from pymongo import MongoClient
        from datetime import datetime, timedelta
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            return None
        db_name = os.environ.get("MONGODB_DB", "aigame")
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        cutoff = (datetime.utcnow() - timedelta(days=_PROMOTION_LOOKBACK_DAYS)).isoformat()
        agg = list(client[db_name]["hermes_team_scores"].aggregate([
            {"$match": {"team": key[0], "sub_team": key[1], "created_at": {"$gte": cutoff}}},
            {"$group": {"_id": None, "avg": {"$avg": "$score"}, "count": {"$sum": 1}}},
        ]))
        if not agg:
            _score_cache[key] = (now, 0.0, 0)
            return (0.0, 0)
        avg = float(agg[0].get("avg", 0))
        cnt = int(agg[0].get("count", 0))
        _score_cache[key] = (now, avg, cnt)
        return (avg, cnt)
    except Exception:
        log.exception("_get_team_score failed")
        return None


def _get_promoted_model(role: str, base_model: str, env: "ExecutionEnv") -> str:
    """team/sub_team 점수가 낮으면 한 단계 위 모델 반환."""
    if role.endswith("_pm") or role == "translator":
        return base_model
    team = env.team or ""
    sub_team = env.sub_team or "general"
    if not team:
        return base_model
    res = _get_team_score(team, sub_team)
    if res is None:
        return base_model
    avg, cnt = res
    if cnt < _PROMOTION_MIN_SAMPLES or avg >= _PROMOTION_THRESHOLD:
        return base_model
    promoted = _MODEL_PROMOTION_LADDER.get(base_model, base_model)
    if promoted != base_model:
        key = f"{team}/{sub_team}/{role}"
        if key not in _promoted_log_cache:
            log.info("[promotion] %s avg=%.1f cnt=%d — %s upgraded %s → %s",
                     key, avg, cnt, role, base_model, promoted)
            _promoted_log_cache.add(key)
    return promoted


def _load_agent_roles() -> dict[str, dict[str, str]]:
    """DB에서 현재 역할 매핑을 읽어 반환. 실패/빈 결과면 DEFAULT."""
    global _roles_cache, _roles_cache_ts
    import time as _time

    now = _time.monotonic()
    if _roles_cache is not None and (now - _roles_cache_ts) < _ROLES_CACHE_TTL_SEC:
        return _roles_cache

    # DEFAULT로 시작해서 DB 값이 있으면 덮어쓴다 (병합 방식).
    # 이렇게 하면 새 역할을 DEFAULT_AGENT_ROLES에 추가하면 DB 시드 없이도 바로 사용 가능.
    mapping: dict[str, dict[str, str]] = {k: dict(v) for k, v in DEFAULT_AGENT_ROLES.items()}
    try:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        db_name = os.environ.get("MONGODB_DB", "aigame")
        if uri:
            client = MongoClient(uri, serverSelectionTimeoutMS=3000)
            for d in client[db_name]["hermes_agent_roles"].find({}):
                role = d.get("role")
                if not role:
                    continue
                mapping[role] = {
                    "tool": str(d.get("tool") or "claude"),
                    "model": str(d.get("model") or "claude-opus-4-7"),
                    "description": str(d.get("description") or ""),
                    # Phase 2에서 분과별 파이프라인 라우팅에 사용 (Phase 1: 메타만 보존)
                    "team": str(d.get("team") or "dev"),
                    "sub_team": str(d.get("sub_team") or "general"),
                    # Phase 4: 직무 기술서 (JD) — invoke_agent에서 프롬프트 상단에 주입
                    "persona": str(d.get("persona") or ""),
                }
    except Exception:
        log.exception("_load_agent_roles DB read failed — DEFAULT만 사용")

    _roles_cache = mapping
    _roles_cache_ts = now
    return mapping


# ──────────────────────────────────────────────
# 에이전트 응답 구조
# ──────────────────────────────────────────────
@dataclass
class AgentResponse:
    role: str
    model: str
    success: bool
    output: str  # 에이전트 발언 전체
    structured: Optional[dict[str, Any]] = None  # JSON 파싱 가능하면 여기
    duration_sec: float = 0.0
    error: Optional[str] = None
    # 토큰 사용량 — 가능한 백엔드에서만 채워진다 (Claude --output-format json, LiteLLM usage 필드).
    # {"input_tokens": int, "output_tokens": int, "cache_read": int, "cache_create": int}
    usage: Optional[dict[str, int]] = None


# ──────────────────────────────────────────────
# 실행 환경 (원격/로컬 추상화)
# ──────────────────────────────────────────────
@dataclass
class ExecutionEnv:
    """어디서 에이전트를 실행할지"""
    mode: str = "remote_ssh"  # "remote_ssh" | "local"
    ssh_host: Optional[str] = None  # e.g. "user@100.92.43.9"
    cwd: str = "."  # 작업 디렉토리
    timeout_sec: int = 600
    image_path: Optional[str] = None  # Claude --image로 전달할 이미지 경로 (원격 기준)
    task_id: Optional[str] = None     # 세션 로그 연결용 — 설정되면 호출마다 기록
    task_title: str = ""              # 검색 편의용 짧은 라벨
    # 보상 체계: 모델 승격에 사용 — 호출 시 (team, sub_team) 평균 점수 < 임계값이면
    # 모델을 한 단계 강한 것으로 자동 교체
    team: Optional[str] = None
    sub_team: Optional[str] = None


# ──────────────────────────────────────────────
# 모델별 가격 (백만 토큰당 USD) — 비용 대시보드용
# 갱신은 여기서. 맞춤 모델 추가 시 prefix 매칭으로 fallback.
# ──────────────────────────────────────────────
MODEL_PRICES_PER_MTOK: dict[str, dict[str, float]] = {
    # Claude (Anthropic)
    "claude-opus-4-7":      {"in": 15.00, "out": 75.00},
    "claude-opus-4-6":      {"in": 15.00, "out": 75.00},
    "claude-sonnet-4-6":    {"in":  3.00, "out": 15.00},
    "claude-sonnet-4-5":    {"in":  3.00, "out": 15.00},
    "claude-haiku-4-5":     {"in":  0.80, "out":  4.00},
    "claude-3-5-sonnet":    {"in":  3.00, "out": 15.00},
    # OpenAI
    "gpt-4o":               {"in":  2.50, "out": 10.00},
    "gpt-4o-mini":          {"in":  0.15, "out":  0.60},
    "gpt-4.1":              {"in":  2.00, "out":  8.00},
    "gpt-4.1-mini":         {"in":  0.40, "out":  1.60},
    "o1":                   {"in": 15.00, "out": 60.00},
    "o1-mini":              {"in":  1.10, "out":  4.40},
    # Image generation은 토큰 단위가 아님 — 비용 대시보드 별도 처리 (현재 미수집)
}


def _lookup_model_price(model: str) -> dict[str, float]:
    """model_id에 해당하는 가격 dict 반환. 정확 매칭 → prefix 매칭 → 0 폴백."""
    if model in MODEL_PRICES_PER_MTOK:
        return MODEL_PRICES_PER_MTOK[model]
    # prefix 매칭 (claude-opus-4-7-some-suffix 같은 변형 대응)
    for k, v in MODEL_PRICES_PER_MTOK.items():
        if model.startswith(k):
            return v
    return {"in": 0.0, "out": 0.0}


def _record_token_usage(
    *, role: str, model: str,
    team: Optional[str], sub_team: Optional[str],
    task_id: Optional[str],
    usage: dict[str, int], duration_sec: float,
) -> None:
    """
    호출 1건의 토큰/비용을 hermes_token_usage 컬렉션에 누적 기록.
    스키마: {role, model, team, sub_team, task_id,
            input_tokens, output_tokens, cache_read, cache_create,
            cost_usd, duration_sec, created_at}
    """
    try:
        from datetime import datetime
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            return
        db_name = os.environ.get("MONGODB_DB", "aigame")
        db = MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    except Exception:
        return

    in_tok    = int(usage.get("input_tokens", 0) or 0)
    out_tok   = int(usage.get("output_tokens", 0) or 0)
    cache_r   = int(usage.get("cache_read", 0) or 0)
    cache_c   = int(usage.get("cache_create", 0) or 0)
    price     = _lookup_model_price(model)
    # Anthropic 캐시 가격: read = 0.1x input, create = 1.25x input.
    # OpenAI는 cache_read만 (0.5x), cache_create=0.
    cost_usd = (
        (in_tok    * price["in"]  / 1_000_000) +
        (out_tok   * price["out"] / 1_000_000) +
        (cache_r   * price["in"]  * 0.10 / 1_000_000) +
        (cache_c   * price["in"]  * 1.25 / 1_000_000)
    )

    try:
        db["hermes_token_usage"].insert_one({
            "role": role,
            "model": model,
            "team": team,
            "sub_team": sub_team,
            "task_id": task_id,
            "input_tokens":  in_tok,
            "output_tokens": out_tok,
            "cache_read":    cache_r,
            "cache_create":  cache_c,
            "cost_usd": round(cost_usd, 6),
            "duration_sec": round(duration_sec, 2),
            "created_at": datetime.utcnow().isoformat(),
        })
    except Exception:
        log.exception("hermes_token_usage insert failed")


# ──────────────────────────────────────────────
# 핵심 호출 함수 — 역할 추상화
# ──────────────────────────────────────────────
def invoke_agent(
    role: str,
    prompt: str,
    env: ExecutionEnv,
    extra_args: Optional[list[str]] = None,
) -> AgentResponse:
    """
    지정한 역할의 에이전트 호출.

    OpenAI 키 도착 시:
      - AGENT_ROLES[role]["tool"] = "openai" 또는 "litellm"으로 변경
      - _invoke_via_litellm() 경로 호출
    지금은 모두 Claude Code로 라우팅.

    학습된 스킬(failure_learning)이 있으면 프롬프트 상단에 자동 주입.
    """
    import time

    roles = _load_agent_roles()
    if role not in roles:
        return AgentResponse(
            role=role, model="unknown", success=False,
            output="", error=f"Unknown role: {role}",
        )

    config = roles[role]
    tool = config["tool"]
    model = config["model"]
    # Phase 3: 분과 평균 점수 기반 모델 자동 승격 (env에 team/sub_team 있을 때만)
    promoted = _get_promoted_model(role, model, env)
    if promoted != model:
        log.info("[%s] model auto-promoted %s → %s (low team score)", role, model, promoted)
        model = promoted
    start = time.monotonic()

    # 노드 저널: 실시간 in-flight(running) 기록 — 완료 시 done/failed로 갱신 (G1 라이브 뷰).
    _jrun = None
    try:
        from hermes_node_journal import mark_start
        _jrun = mark_start(getattr(env, "task_id", None), role, model)
    except Exception:
        pass

    # 학습된 스킬을 프롬프트 상단에 주입 (Hermes 자가 강화 핵심)
    # 단, content/art 등 비-코드 파이프라인엔 코드 관련 스킬 자동 차단 (토큰 절약 + 노이즈 제거).
    try:
        _team = getattr(env, "team", "") or ""
        _sub = getattr(env, "sub_team", "") or ""
        is_non_code_pipeline = (
            role.startswith("design_content_")
            or role.startswith("art_")
            or _team in {"art"}
            or _sub in {"content"}
        )
        if not is_non_code_pipeline:
            from failure_learning import load_learned_skills_text
            learned = load_learned_skills_text()
            if learned:
                prompt = learned + prompt
                log.debug("[%s] injected %d chars of learned skills", role, len(learned))
        else:
            log.debug("[%s] skipped learned skills (non-code pipeline)", role)
    except Exception:
        pass  # failure_learning 없어도 기본 동작

    # Phase 4 (직무 페르소나): 역할에 JD가 등록돼 있으면 프롬프트 최상단에 주입
    persona = (config.get("persona") or "").strip()
    if persona:
        prompt = (
            f"# 직무 기술서 ({role})\n"
            f"{persona}\n\n"
            f"---\n\n"
            + prompt
        )
        log.debug("[%s] injected persona (%d chars)", role, len(persona))

    # Phase 5 (프롬프트 자기 개선): 같은 role의 active 패치가 있으면 페르소나 다음에 주입
    try:
        from prompt_self_improvement import load_active_patches_text
        patches_text = load_active_patches_text(role)
        if patches_text:
            prompt = patches_text + prompt
            log.debug("[%s] injected %d chars of auto-learned patches", role, len(patches_text))
    except Exception:
        pass  # 모듈 없거나 DB 다운이어도 기본 동작 유지

    log.info("[%s/%s] invoking (mode=%s)", role, model, env.mode)

    # H1 Resilience: retry + circuit breaker로 _invoke_* 호출을 감쌈.
    # H2 Validation: schema 정의된 역할은 잘못된 응답에 1회 repair 재시도.
    # H3 Observability: span으로 1 호출 단위 trace.
    # 호출 순서: span (H3) → with_retry (H1) → with_validation (H2) → 실제 LLM
    try:
        from harness.resilience import (
            with_retry, RetryPolicy, CircuitBreaker, CircuitOpenError,
            categorize_error,
        )
        from harness.validation import with_validation
        from harness.tracing import span as _trace_span
        _retry_policy = RetryPolicy(max_retries=2, base_delay=2.0, max_delay=20.0,
                                    timeout_total=env.timeout_sec)
        _cb = CircuitBreaker(f"model:{model}")

        # 내층: validation (malformed 시 repair 1회)
        def _raw_call(p: str) -> tuple[str, Optional[dict[str, int]]]:
            with _cb.call():
                if tool == "claude":
                    return _invoke_claude_code(model, p, env, extra_args)
                if tool in {"openai", "litellm", "anthropic"}:
                    return _invoke_via_litellm(model, p, env)
                raise ValueError(f"Unknown tool: {tool}")

        _validated_call = with_validation(role, max_repair=1)(_raw_call)

        # 외층: retry + span
        @with_retry(_retry_policy)
        def _resilient_call() -> tuple[str, Optional[dict[str, int]]]:
            return _validated_call(prompt)

        with _trace_span(
            "invoke_agent",
            role=role, model=model, tool=tool,
            team=env.team, sub_team=env.sub_team,
            task_id=env.task_id,
            prompt_length=len(prompt),
        ) as _span:
            output, usage = _resilient_call()
            _span.set_attr("output_length", len(output))
            if usage:
                _span.set_attr("usage", usage)
            # H5 Safety: 거부응답 감지 (성공 호출이지만 LLM이 협조 거부한 케이스)
            try:
                from harness.safety import detect_refusal
                is_refusal, snippet = detect_refusal(output)
                if is_refusal:
                    _span.set_attr("is_refusal", True)
                    _span.set_attr("refusal_snippet", snippet)
                    log.warning("[%s] refusal detected: %s", role, snippet)
            except Exception:
                pass  # safety check 실패는 본 호출 방해 X
    except CircuitOpenError as e:
        # circuit open — error로 처리
        duration = time.monotonic() - start
        log.warning("[%s] circuit open: %s", role, e)
        err_msg = f"CircuitOpen: {e}"
        try:
            from agent_session_log import record_invocation
            record_invocation(
                task_id=env.task_id, task_title=env.task_title,
                role=role, model=model,
                prompt=prompt, output="", structured=None,
                duration_sec=duration, success=False, error=err_msg,
            )
        except Exception:
            pass
        try:
            from hermes_node_journal import mark_finish
            mark_finish(_jrun, False)
        except Exception:
            pass
        return AgentResponse(
            role=role, model=model, success=False,
            output="", duration_sec=duration, error=err_msg,
        )
    except Exception as e:
        duration = time.monotonic() - start
        log.exception("[%s] failed after %.1fs", role, duration)
        err_msg = f"{type(e).__name__}: {e}"
        try:
            from agent_session_log import record_invocation
            record_invocation(
                task_id=env.task_id, task_title=env.task_title,
                role=role, model=model,
                prompt=prompt, output="", structured=None,
                duration_sec=duration, success=False, error=err_msg,
            )
        except Exception:
            pass
        try:
            from hermes_node_journal import mark_finish
            mark_finish(_jrun, False)
        except Exception:
            pass
        return AgentResponse(
            role=role, model=model, success=False,
            output="", duration_sec=duration,
            error=err_msg,
        )

    duration = time.monotonic() - start
    log.info("[%s] completed in %.1fs (%d chars, tok=%s)",
             role, duration, len(output),
             f"{usage.get('input_tokens', '?')}/{usage.get('output_tokens', '?')}" if usage else "?")

    # 구조화된 응답 시도 (JSON 파싱)
    structured = _try_parse_json(output)

    try:
        from agent_session_log import record_invocation
        record_invocation(
            task_id=env.task_id, task_title=env.task_title,
            role=role, model=model,
            prompt=prompt, output=output, structured=structured,
            duration_sec=duration, success=True, error=None,
        )
    except Exception:
        pass

    # 토큰 사용량 누적 — hermes_token_usage (비용 대시보드용)
    if usage and (usage.get("input_tokens") or usage.get("output_tokens")):
        try:
            _record_token_usage(
                role=role, model=model,
                team=env.team, sub_team=env.sub_team,
                task_id=env.task_id,
                usage=usage, duration_sec=duration,
            )
        except Exception:
            log.exception("_record_token_usage failed")

    try:
        from hermes_node_journal import mark_finish
        mark_finish(_jrun, True)
    except Exception:
        pass

    return AgentResponse(
        role=role, model=model, success=True,
        output=output, structured=structured,
        duration_sec=duration, usage=usage,
    )


# ──────────────────────────────────────────────
# Claude Code 호출 (SSH 경유 또는 로컬)
# ──────────────────────────────────────────────
def _invoke_claude_code(
    model: str,
    prompt: str,
    env: ExecutionEnv,
    extra_args: Optional[list[str]] = None,
) -> tuple[str, Optional[dict[str, int]]]:
    """
    Claude Code CLI를 비대화 모드로 호출.

    --output-format json 으로 토큰 사용량 포함 응답을 받아 (text, usage) 튜플 반환.
    파싱 실패 시 stdout 원문 + usage=None 폴백.

    중요: --permission-mode acceptEdits로 파일 수정 자동 승인.
    BalloonFlow 레포는 feature 브랜치에 작업하므로 안전.
    """
    permission_args = [
        "--dangerously-skip-permissions",
        "--tools", "default",
        "--output-format", "json",
    ]
    if env.image_path:
        prompt = (
            f"[REFERENCE IMAGE ATTACHED]\n"
            f"An image is attached at: {env.image_path}\n"
            f"Use the Read tool to view it if visual context helps with this task.\n\n"
            f"---\n\n"
            + prompt
        )

    if env.mode == "local":
        cmd = ["claude", "-p", prompt, "--model", model, *permission_args]
        if extra_args:
            cmd.extend(extra_args)
        # stdin=DEVNULL 필수: 프롬프트는 -p 인자로 전달됨. stdin을 닫지 않으면 부모 stdin을
        # 상속 → cron/수동/배치 컨텍스트에서 claude CLI가 "no stdin data received in 3s" 후
        # exit 1. systemd(watcher)는 stdin=/dev/null이라 우연히 동작했을 뿐. 컨텍스트 독립 보장.
        proc = subprocess.run(
            cmd, cwd=env.cwd, capture_output=True, text=True,
            stdin=subprocess.DEVNULL,
            timeout=env.timeout_sec, check=False,
        )
    elif env.mode == "remote_ssh":
        if not env.ssh_host:
            raise ValueError("remote_ssh mode requires ssh_host")
        perm_flag = " ".join(permission_args)
        extra = (" " + " ".join(extra_args)) if extra_args else ""
        remote_cmd = (
            f'cd "{env.cwd}" && '
            f'claude -p --model {model} {perm_flag}{extra}'
        )
        proc = subprocess.run(
            ["ssh", env.ssh_host, remote_cmd],
            input=prompt, capture_output=True, text=True,
            timeout=env.timeout_sec, check=False,
        )
    else:
        raise ValueError(f"Unknown env.mode: {env.mode}")

    if proc.returncode != 0:
        raise RuntimeError(
            f"Claude Code failed (exit={proc.returncode}): {proc.stderr[:500]}"
        )

    # --output-format json: 단일 JSON 객체 (또는 stream-json 줄별)
    raw = proc.stdout.strip()
    text = raw
    usage: Optional[dict[str, int]] = None
    try:
        envelope = json.loads(raw)
        if isinstance(envelope, dict):
            text = envelope.get("result") or envelope.get("text") or raw
            u = envelope.get("usage") or {}
            if isinstance(u, dict):
                usage = {
                    "input_tokens":  int(u.get("input_tokens", 0) or 0),
                    "output_tokens": int(u.get("output_tokens", 0) or 0),
                    "cache_read":    int(u.get("cache_read_input_tokens", 0) or 0),
                    "cache_create":  int(u.get("cache_creation_input_tokens", 0) or 0),
                }
    except (json.JSONDecodeError, ValueError):
        # JSON 파싱 실패 시 원문 그대로 — usage는 미수집
        pass

    return text, usage


# ──────────────────────────────────────────────
# LiteLLM 경유 호출 (OpenAI, Anthropic API 등)
# ──────────────────────────────────────────────
def _invoke_via_litellm(
    model: str, prompt: str, env: ExecutionEnv,
) -> tuple[str, Optional[dict[str, int]]]:
    """
    LiteLLM 프록시(Mother:4000) 경유 호출.
    응답의 usage 필드를 추출해 (text, usage) 반환.
    """
    import requests

    litellm_url = os.environ.get("LITELLM_URL", "http://localhost:4000")
    master_key = os.environ.get("LITELLM_MASTER_KEY", "")

    resp = requests.post(
        f"{litellm_url}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {master_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 4096,
        },
        timeout=env.timeout_sec,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"]
    usage: Optional[dict[str, int]] = None
    u = data.get("usage") or {}
    if isinstance(u, dict):
        usage = {
            "input_tokens":  int(u.get("prompt_tokens", 0) or 0),
            "output_tokens": int(u.get("completion_tokens", 0) or 0),
            "cache_read":    int(u.get("cache_read_input_tokens", 0) or 0),
            "cache_create":  int(u.get("cache_creation_input_tokens", 0) or 0),
        }
    return text, usage


# ──────────────────────────────────────────────
# 병렬 에이전트 실행
# ──────────────────────────────────────────────
def run_parallel_agents(
    agents: list[tuple[str, str]],  # [(role, prompt), ...]
    env: ExecutionEnv,
    max_workers: int = 3,
) -> list[AgentResponse]:
    """
    여러 에이전트를 병렬 실행 (Sub Coder ×2 같은 케이스).
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = [
            pool.submit(invoke_agent, role, prompt, env)
            for role, prompt in agents
        ]
        return [f.result() for f in futures]


# ──────────────────────────────────────────────
# 응답 JSON 파싱 헬퍼
# ──────────────────────────────────────────────
def _try_parse_json(text: str) -> Optional[dict[str, Any]]:
    """
    응답 안에 JSON 블록 있으면 파싱.
    (```json ... ``` 형식 또는 { ... } 전체 형식 감지)
    """
    # 코드 블록 추출
    import re
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = match.group(1) if match else text.strip()

    if not candidate.startswith("{"):
        return None

    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None


# ──────────────────────────────────────────────
# 프롬프트 템플릿 (역할별)
# ──────────────────────────────────────────────
TRANSLATOR_PROMPT_TEMPLATE = """You are the Translator / Requirements Analyst for the aimed-puzzle team.
Your job: take a terse, informal task written in natural language (often by non-engineers)
and decide whether there is enough information to start coding, or whether we need to ask
the author a follow-up question first.

Task from ProjectHub:
Title: {title}
Description: {description}

Existing comments:
{comments}

## ⚠️ 사용자 보충 답변 처리 (중요)
- Description에 `## 사용자 보충 답변` 섹션이 있으면, 이는 **이전 hermes 질문에 대한 사용자의 직접 답변**이다.
- 이 답변을 **description의 핵심 정보로 합쳐서** 판단하라. 비어 있던 description이라도 답변에서 색상/난이도/모티프/모양/장애물 등이 명시됐다면 **충분한 정보**로 간주.
- **같은 needs_input 질문을 반복하지 말 것**. 답변이 일부만 채워졌다면 *남은 부분만* 다시 묻거나, 합리적 default로 채워 clarity=clear 처리.
- 답변이 색상/난이도/주제 같은 키워드를 포함하면 `clarity=clear`로 진행하고 `enriched_description`에 답변 내용을 통합 기재.

## 수행 단계
1. 태스크의 핵심 개념 단어를 추출해 영문/한글/snake_case/camelCase 변형으로 Grep한다
   (Assets/Scripts/**, *.asset, *.prefab 등)
2. 개념이 코드베이스에 **이미 존재**하면, 현재 값을 찾아 제시하고 "변경하려는 값"을
   구체적으로 명세할 수 있는지 판단
3. 애매한 부분(예: "얼마나?", "어느 레벨?", "모든 플랫폼?")이 있으면 **질문으로 뽑아내기**

## 판정 규칙
- **clear**: 변경할 대상/값이 구체적으로 하나의 해석으로 수렴하면 clear
  · 예: "다트 spacing 1.0 -> 1.25" — 대상·값 둘 다 명확
- **needs_input**: 대상은 알겠으나 값이 빠졌거나, 영향 범위가 모호하면 needs_input
  · 예: "다트 좀 띄워줘" — 몇 배? 전 레벨? 특정 레벨?
- **cancel**: 사용자가 **작업 취소/중단/건너뛰기** 또는 **"코드 변경 필요 없음"**
  의도를 표현하면 cancel
  · 명시적 취소: "그대로 둬", "작업하지마", "완료로 넘겨", "skip", "pass",
    "필요 없어", "취소", "하지 말자", "나중에 할게", "안 해도 돼", "그만", "done"
  · **현상 유지 답변도 cancel로 처리** (중요):
    "현재 값 유지", "기본값 유지", "현재 색상 유지", "지금 상태 그대로",
    "변경 없음", "no changes needed", "keep as is", "default 유지",
    "난이도 상관없이 현재대로" 같이 **결과적으로 코드 수정이 없어야 하는 답변**
  · 이유: clear로 넘기면 Main Coder가 `files_modified=[]` 반환 → no_changes_made
    실패로 잡혀 사용자가 혼란스러워함. 시작부터 cancel로 닫는 게 깔끔.
  · 재작업 comments에서 이런 표현이 마지막 사용자 답변에 있으면 주저 없이 cancel
  · cancel_reason에 사용자 원문(또는 요약)을 적는다

- **재시도 케이스** (clarity=clear로 처리):
  · 이전 코멘트에 "❌ 작업 실패" 같은 실패 안내가 있고 사용자 답변이
    "재시도", "retry", "다시", "네", "다시 해봐", "ok" 같은 단답이면:
    → `clarity=clear`, `enriched_description`에 원본 의도 + "(이전 시도 실패 후 재시도 요청)" 추가
    → Lead가 이전 실패 맥락(session log에 이미 있음)을 보고 다른 접근을 시도할 것

- **rollback**: 이전에 **이미 commit/push/PR이 만들어진 작업**을 **되돌리는** 요청
  · 키워드: "롤백", "revert", "되돌려", "이전으로", "취소해줘", "되돌리자",
    "없던 일로", "PR 닫아", "merge 전으로"
  · 단서: 이전 Hermes 코멘트에 `✅ 작업 완료` 또는 `PR: https://...` 가 있음
  · clarity="rollback", rollback_reason에 이유 적음
  · 주의: 단순히 "작업 취소"(cancel)과는 다름 — cancel은 시작 전 중단,
    rollback은 **이미 만들어진 것 제거**. PR/merge 상태에 따라 close 또는 revert

## 질문 작성 원칙 (needs_input일 때)
- 최대 3개, 간결하게
- 가능하면 선택지(①②③) 제공 — 사용자가 한 단어로 답할 수 있게
- 현재 코드의 기본값을 괄호로 함께 제시

## 팀 분류 (team 필드) — 어느 파이프라인으로 보낼지 결정
- **dev** (기본): Unity 코드 수정, .cs/.prefab/.asset 편집, 버그 픽스, 최적화, 리팩토링
  · 키워드: 수정, manager, prefab, .cs, 버그, 최적화, patch, fix, sync
  · `[unity]`, `[code]`, `[patch]`, `[fix]`, `[optimize]` 태그
- **art**: **이미지/스프라이트/일러스트 생성 또는 편집 요청**
  · 키워드: 이미지 생성, 이미지 만들어, 일러스트, 스프라이트, concept art, 아트웍,
    배경 이미지, 캐릭터 아트, 디자인 참조 만들어, "그려줘", "이미지로"
  · `[art]`, `[아트]`, `[image]`, `[sprite]`, `[illustration]` 태그
  · 이 경우 art 파이프라인으로 라우팅 → art_prompter → image_generator → art_reviewer
- **design**: 기획·격자 레벨 디자인 (활성: design/level, 미연결: design/content)
  · level 키워드: 만화경, kaleidoscope, 격자/grid 패턴, 25x25 셀, 타일맵, 스테이지 레이아웃,
    "대칭 패턴 만들어", "퍼즐 보드 레이아웃 짜줘", color palette 배치
  · content 키워드: 시나리오, 보상 시스템, 레벨 기획(난이도 기획), 스펙 문서, PDR, 튜토리얼 카피
  · `[design]`, `[기획]`, `[level]`, `[레벨]`, `[balance]`, `[spec]`, `[plan]` 태그
  · 이 경우 design 파이프라인으로 라우팅 → design_pm이 level/content 분류 → 각 분과 처리
- **chat**: 위 셋 모두 아닌 일반 문의/대화 (예: "지금 상태 설명해줘", "이 태스크 뭐야")

**중요**: team_override가 true(사용자가 수동 재배정)인 태스크는 이 분류를 무시하고
사용자가 지정한 팀을 그대로 사용해야 한다 (executor가 처리).

## 요구 출력 JSON (반드시 이 형식만 반환)
```json
{{
  "clarity": "clear" | "needs_input" | "cancel" | "rollback",
  "team": "dev" | "art" | "design" | "chat",
  "concept_keywords": ["핵심 단어1", "변형1", ...],
  "files_examined": ["Assets/.../FileA.cs", ...],
  "current_state": "현재 코드에서 파악한 기본값/구조 1~2줄 요약",
  "enriched_description": "clarity=clear일 때만 채움 — Lead/Main이 보기 좋게 정제된 요구사항",
  "questions": [
    "clarity=needs_input일 때만 — 사용자에게 물을 질문 (최대 3개)"
  ],
  "question_preamble": "질문에 앞서 사용자에게 표시할 1~2줄 현황 설명",
  "cancel_reason": "clarity=cancel일 때만 — 사용자 원문 또는 요약 한 줄",
  "rollback_reason": "clarity=rollback일 때만 — 이유 한 줄"
}}
```
"""


LEAD_PROMPT_TEMPLATE = """You are the Lead Agent for the aimed-puzzle team (Balloonflow project).

Task from ProjectHub:
Title: {title}
Description: {description}

Previous comments:
{comments}

## ⚠️ 파일 탐색은 반드시 다음 순서로 — 한 파일만 보고 판단하지 말 것

1. **개념 단어 추출**: 태스크 제목/설명에서 핵심 개념 단어(예: "다트 간격", "spacing",
   "delay", "speed")를 뽑아 한글/영문/snake_case/camelCase/UPPER_SNAKE 변형을 모두 만든다.
   예: "다트 spacing" → `dart`, `Dart`, `DART`, `spacing`, `Spacing`, `SPACING`, `interval`, `space`, `multiplier`

2. **전역 grep 필수** — 아래 세 가지를 모두 수행하고 결과를 확인:
   - Grep tool로 각 변형을 Unity 소스(Assets/Scripts/**)에 대해 검색
   - Grep으로 ScriptableObject/Config/Settings 파일(*.asset, *.json, *SO.cs)도 검색
   - Glob으로 관련 이름 패턴 파일 나열(예: **/*Dart*, **/*Spacing*, **/*Layout*, **/*Spawner*)

3. **영향 파일 후보를 '하나'가 아닌 '전체 리스트'로 제출**:
   - Controller/Manager 외에 실제 로직이 있는 Spawner/Layout/Config/ScriptableObject/
     SerializeField/Prefab value까지 포함
   - GameManager 같은 상위 오케스트레이션 파일이 값을 **위임**하고 있으면, 실제
     값이 살고 있는 파일이 주 수정 대상 — GameManager는 부수 수정일 수 있음

4. **동일 개념이 여러 곳에 분산** 되어 있으면 그 사실을 impact_analysis에 명시하고,
   main_coder에게 "모든 후보 파일을 읽은 뒤 어느 쪽을 고쳐야 실제 동작이 바뀌는지
   판단하라"고 지시한다.

## 큰 작업 자동 분할 (Phase Plan) — 시니어 PM 능력
**한 사이클(600초)에 끝낼 수 없을 거라 판단되는 큰 작업**은 즉시 구현 시작 대신
phase_plan을 반환하라. 각 phase는 독립적으로 commit + Reviewer 검증이 가능해야 한다.

분할이 필요한 케이스:
- 영향 파일 수 ≥ 6개
- 변경 라인 수 ≥ 300줄
- 다단 의존성 리팩토링 (스키마 변경 → 호출처 N곳 수정)
- 새 시스템 도입 (구조 추가 + 기능 + UI 연결 + 테스트)

분할 안 해도 되는 케이스:
- 단일 파일 수정
- 명확한 함수 추가/제거
- 단순 버그 픽스 (1~3 파일)
- 변수·상수 값 변경

응답 형식 — 둘 중 **하나** 선택:

[A] 단일 사이클 작업 (기본):
```json
{{
  "summary": "...",
  "impact_analysis": "...",
  "search_queries_used": [...],
  "main_coder_task": "...",
  "sub_tasks": [...],
  "likely_files": [...],
  "validation_focus": "..."
}}
```

[B] Phase 분할 필요:
```json
{{
  "phase_plan": [
    {{"n": 1, "name": "Schema 변경", "files": ["Foo.cs"], "estimated_lines": 50, "rationale": "Schema부터 안 바꾸면 후속 phase 진행 불가"}},
    {{"n": 2, "name": "Manager 리팩토링", "files": ["Bar.cs", "Baz.cs"], "estimated_lines": 200, "rationale": "..."}}
  ],
  "summary": "왜 분할이 필요한지 1~2줄"
}}
```

분할 시 각 phase가 커밋·리뷰 단위로 독립 실행됨. 첫 phase부터 자동 진행됨.

## 요구 출력 JSON (단일 사이클일 때)
```json
{{
  "summary": "one-line summary of what needs to be done",
  "impact_analysis": "does this change affect existing contracts/architecture? 관련 개념이 여러 파일에 분산돼 있는가?",
  "search_queries_used": ["grep query 1", "grep query 2", ...],
  "main_coder_task": "Main Coder는 모든 후보 파일을 Read한 후 실제 값이 사는 곳을 찾아 수정하라 (GameManager가 값을 위임만 한다면 실제 값 소유자를 고쳐야 함). 구체 지시: ...",
  "sub_tasks": [
    "sub-task 1 for Sub Coder A",
    "sub-task 2 for Sub Coder B"
  ],
  "likely_files": ["file1.cs", "file2.cs", "...(후보 전체)"],
  "validation_focus": "Validator가 실제로 런타임 값이 바뀌는지 확인할 포인트"
}}
```
"""

MAIN_CODER_PROMPT_TEMPLATE = """You are the Main Coder for the aimed-puzzle team. You have FILE EDITING TOOLS — use them.

Lead's plan:
{lead_plan}

Focus on the MAIN task: {main_task}

ACTIONS YOU MUST TAKE (not describe — DO):
1. Use the Glob/Read tools to explore the project structure (look inside BalloonFlow/Assets/Scripts or similar).
2. Use Edit or Write to MODIFY the actual files — do not just describe changes.
3. Follow existing coding conventions (namespaces, SingletonManagers, etc.)
4. Do NOT modify _CONTRACTS.yaml, _ARCHITECTURE.md, _ASSET_MANIFEST.yaml (GameForge-owned).

## 🛡️ 회귀 방지 — 외과적 최소 수정 (절대 규칙, 위반 시 Reviewer 거부)
최우선 원칙: **기존 기능을 절대 망가뜨리거나 붕괴·롤백하지 않는다. 기존 코드를 이해해 필요한 부분만 완벽히 구현한다.**
1. **먼저 이해**: 수정 전 해당 파일+주변 코드를 Read해 기존 코드 스타일·네이밍·구조·패턴을 파악하고 **그대로 따른다**(새 스타일 강요 금지).
2. **필요한 코드만**: 과제가 요구하는 라인만 변경. **수정 대상 외 코드는 절대 건드리지 않는다** — 포맷팅 변경·리네임·임의 리팩토링·import 정리·주석 삭제 금지.
3. **삭제/시그니처 변경 금지**: 기존 public 메서드/필드/프로퍼티/[SerializeField]/이벤트/using을 삭제하거나 시그니처 바꾸지 않는다. 에러를 "그 코드 삭제·주석처리·우회 null체크"로 회피 금지. 정말 불가피하면 호출처 전부 동시 수정 + summary에 사유 명시.
4. **파일 통째 재작성 금지**: 기존 파일은 Write로 덮어쓰지 말고 **Edit로 최소 hunk만**. (Write는 신규 파일 한정)
5. **diff 최소화**: 과제와 직접 관련된 변경만. "겸사겸사" 정리/개선 금지. 변경량이 과제 규모를 크게 넘으면 과도수정 — 되돌려 좁힌다.
6. **무에러·완벽**: 변경 후 컴파일·기존 동작이 깨지지 않아야 한다. 불확실하면 추측하지 말고 기존 패턴을 따른다.

## ⚠️ GameManager는 신뢰하지 말 것 (Balloonflow 프로젝트 특수 규칙)

Balloonflow의 GameManager에는 런타임에 실제로 읽히지 않는 **dead 필드/메서드가 다수** 존재한다.
GameManager만 수정하고 끝내면 git diff는 통과해도 **실제 동작이 바뀌지 않아 재작업**으로 이어진 사례가 많다.

**반드시 수행**:
- (a) 바꾸려는 값의 이름을 `grep`으로 전역 검색 → 실제로 **읽는** 코드가 어디 있는지 확인
  (GameManager 내부에서만 자기 참조되는 필드는 dead code 가능성 높음)
- (b) Spawner/Controller/Layout/Config/ScriptableObject/SerializeField 중에서 실제 값 소유자를 찾는다
- (c) GameManager는 오케스트레이션 레이어 — 마지막 후보로 두고 실제 값이 사는 파일을 먼저 수정
- (d) Inspector 값(`.prefab`, `.asset` 파일)에 하드코딩된 값이 있으면 C# 소스 수정만으로 안 바뀔 수 있음 — 해당 파일도 Grep해서 확인
- (e) summary 필드에 "값이 실제 런타임에 읽히는 경로"를 문장으로 명시 (예: "DartSpawner.spawnInterval ← DartLayoutConfig.asset ← Editor Inspector")

After you have ACTUALLY edited files, respond with:
```json
{{
  "files_modified": ["BalloonFlow/Assets/Scripts/BalloonManager.cs", ...],
  "summary": "what you changed and why",
  "tests_needed": "manual/automated test checklist"
}}
```

If you did not modify any files, respond with `"files_modified": []` and explain why in summary.
"""

SUB_CODER_PROMPT_TEMPLATE = """You are a Sub Coder for the aimed-puzzle team. You have FILE EDITING TOOLS — use them.

Lead's plan:
{lead_plan}

Your sub-task: {sub_task}

ACTIONS YOU MUST TAKE:
1. Use Glob/Read to find the right files
2. Use Edit or Write to ACTUALLY modify files — do not just describe
3. Keep changes focused and small — only the sub-task scope
4. Follow existing conventions

After actually editing files, respond:
```json
{{
  "files_modified": [...],
  "summary": "..."
}}
```

If no files were modified, set "files_modified": [] and explain.
"""

VALIDATOR_PROMPT_TEMPLATE = """You are the Validator for the aimed-puzzle team.

Changes made:
{changes_summary}

Your job:
1. Run `git diff HEAD~1` to see the actual changes
2. Verify the changes follow team conventions (namespaces, naming, singleton patterns)
3. Check if any contracts are implicitly violated
4. Check if tests exist or are needed

Respond with:
```json
{{
  "passed": true/false,
  "issues": ["issue 1", "issue 2"],
  "recommendations": ["..."],
  "needs_rework": true/false
}}
```
"""

REVIEWER_PROMPT_TEMPLATE = """You are the Reviewer — final quality gate for the aimed-puzzle team.

Changes summary:
{changes_summary}

Validator's verdict:
{validator_verdict}

Your job: Final quality review.
1. Assess code quality and maintainability
2. Check naming and documentation
3. Decide whether to APPROVE or REQUEST_CHANGES
4. Assign a quality score (0-100)

## 🛡️ 회귀/과도수정 게이트 (먼저 검사 — 위반 시 무조건 REQUEST_CHANGES)
`git diff HEAD~1`(또는 changes_summary)을 보고 다음을 검사. 하나라도 해당되면 점수와 무관하게 REQUEST_CHANGES:
- **기능 삭제/롤백**: 기존 public 메서드/필드/[SerializeField]/이벤트/클래스가 과제와 무관하게 삭제되거나 시그니처가 바뀜
- **과도수정**: 과제와 무관한 파일/라인 변경(포맷팅·리네임·임의 리팩토링·import 정리·주석 삭제), 또는 파일 통째 재작성(Write로 기존 파일 덮어쓰기)
- **범위 이탈**: 변경 파일이 과제(Lead 계획/likely_files) 범위를 크게 벗어남
- **에러 우회**: 로직 우회형 null 체크(`if(x==null) return;`로 필수 로직 스킵)나 코드 주석처리로 에러 회피
→ required_changes에 "과제 범위로 되돌리고 삭제된 X 복구" 식으로 구체 지시.

Score rubric:
- 90-100: Excellent — clean, idiomatic, well-tested, no concerns
- 75-89:  Good — solid implementation, minor nits at most
- 60-74:  Acceptable — works but has notable concerns or rough edges
- 40-59:  Marginal — significant issues, REQUEST_CHANGES
- 0-39:   Poor — major problems, REQUEST_CHANGES

Respond with:
```json
{{
  "verdict": "APPROVED" | "REQUEST_CHANGES",
  "quality_score": 0-100,
  "strengths": ["..."],
  "concerns": ["..."],
  "required_changes": ["..."] // empty if APPROVED
}}
```
"""


# ════════════════════════════════════════════════════════════════
# 🎨 아트팀 프롬프트 (art_prompter / art_reviewer)
# ════════════════════════════════════════════════════════════════

ART_PROMPTER_TEMPLATE = """You are the Art Prompter for the aimed-puzzle team.
Your job: take a user's art request (often terse, Korean, informal) and produce a
detailed English prompt for GPT Image 2 that yields a high-quality game asset.

Task:
Title: {title}
Description: {description}
Comments history:
{comments}

## 고려사항
1. **게임 컨텍스트** — 이 프로젝트는 Balloonflow라는 **퍼즐/캐주얼 모바일 게임**이다.
   - 톤앤매너: 친근함, 선명한 색감, 명확한 실루엣, 단순·귀여운 스타일
   - 타겟: 캐주얼 유저 (라이트한 비주얼 선호)
2. **명세할 요소** (사용자가 말하지 않았어도 기본값 제공)
   - 스타일: 2D illustration / flat design / semi-realistic 중 어느 쪽?
   - 배경: 투명 PNG로 분리할지, 배경 포함할지
   - 색상 팔레트: 밝은 톤 / 파스텔 / 대비 강한지
   - 구도: 정면/사이드/3/4 뷰 · 중앙 정렬
   - 해상도: 1024×1024 (정사각 기본), 1024×1536 (세로 배너), 1536×1024 (가로 배너)
3. **금지 사항** — 저작권 있는 캐릭터/브랜드 명시 금지, 사람 얼굴은 단순화

## 요구 출력 JSON
```json
{{
  "image_prompt": "GPT Image 2에 그대로 들어갈 영문 프롬프트 (상세·구체적)",
  "size": "1024x1024" | "1024x1536" | "1536x1024" | "auto",
  "n": 1-4,
  "quality": "auto" | "high" | "medium" | "low",
  "tags": ["aimed-puzzle", "balloonflow", "ui", "character", ...],
  "rationale": "왜 이 프롬프트·크기·수량을 선택했는지 1~2줄"
}}
```
"""


# ════════════════════════════════════════════════════════════════
# 🧭 PM 에이전트 — Translator 다음 단계, sub_team 배당 결정
# ════════════════════════════════════════════════════════════════

PM_PROMPT_TEMPLATE = """You are the {team_label} team PM (Project Manager).
Translator has classified this task as the **{team}** team's responsibility.
Your job: pick which **sub_team** (분과) should own this work.

Task:
Title: {title}
Description: {description}

Available sub_teams:
{sub_team_options}

Decision rules:
{decision_rules}

If the task is genuinely cross-cutting or not specific to any sub_team, choose `general`.

Output JSON ONLY:
```json
{{
  "sub_team": "<one of: {sub_team_csv}>",
  "reason": "한 줄 — 핵심 근거 (예: 'Canvas Prefab 수정이라 UI')"
}}
```
"""

_DEV_PM_RULES = """가장 구체적인 분과를 고르세요. 세부가 애매하면 거친 분과(ui/server/ingame/outgame).
[UI] ui_hud(HUD·체력·재화·점수·타이머·오버레이) / ui_popup(팝업·모달·결과·설정·확인·일시정지) / ui_lobby(로비·메인메뉴·타이틀·연출) / ui_shop(상점·구매버튼·가격·IAP UI·광고제거) / ui_inventory(보관함·슬롯·장착) / ui(그 외 일반 UI)
[SERVER] server_auth(인증·로그인·세션·토큰) / server_iap(결제·영수증검증·지급) / server_data(세이브·동기화·마이그레이션) / server_liveops(이벤트·시즌·원격설정·푸시) / server_leaderboard(랭킹·점수제출) / server(그 외 백엔드)
[INGAME] ingame_core(코어메카닉·룰·보드·승패) / ingame_gimmick(기믹·장애물) / ingame_input(입력·터치·조준·발사) / ingame_fx(연출·이펙트·파티클·효과음·BGM) / ingame(그 외 인게임)
[OUTGAME] outgame_progression(성장·해금·튜토리얼·진행도) / outgame_reward(보상·재화·일일보상·시즌패스) / outgame_meta(업적·도감·프로필·스트릭) / outgame(그 외 메타)
- general: 인프라/공용/위 어디에도 안 맞음"""

_ART_PM_RULES = """가장 구체적인 분과를 고르세요.
- art_ui_icon: UI 아이콘·버튼 그래픽·재화/기능 아이콘
- art_ui_panel: UI 패널·창·바·프레임(9-slice)
- art_bg: 배경·환경·스테이지 비주얼
- art_character: 캐릭터·단일 피사체·일러스트(중앙·전신)
- art_fx: 이펙트·파티클 스프라이트·연출 프레임
- ui/background/illustration/general: 위 세부에 안 맞는 거친 분과 fallback"""

_DESIGN_PM_RULES = """**생성 분과(격자/이미지 산출)와 문서 분과(기획 문서)를 구분하세요.**
[생성]
- level: **선형 격자 패턴** — chevron/kaleidoscope/rings/대칭/기하 (키워드: 패턴·대칭·기하학·격자·타일)
- motif: **비선형 모티프** — 동물·캐릭터·일러스트·특정 그림 (PixelLab 호출)
[문서 기획]
- content_level: 레벨 디자인 문서(난이도곡선·기믹배치·비트차트·큐 명세)
- content_balance: 밸런스/경제(성장·전투·확률·재화 곡선·공식)
- content_liveops: 라이브옵스(이벤트·시즌·운영·KPI)
- content_bm: BM/수익화(결제·패키지·LTV·광고)
- content_narrative: 내러티브/UX텍스트(시나리오·튜토리얼·팝업 문구·텍스트정합)
- content/general: 위 외 일반 기획"""


def _discover_sub_teams(team: str) -> list[str]:
    """DB에 등록된 (team) 안의 모든 sub_team을 자동 발견 — UI에서 새로 추가된 분과도 PM이 알게 됨."""
    try:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            return []
        db_name = os.environ.get("MONGODB_DB", "aigame")
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        rows = client[db_name]["hermes_agent_roles"].distinct("sub_team", {"team": team})
        return [str(s) for s in rows if isinstance(s, str) and s.strip()]
    except Exception:
        return []


def build_pm_prompt(team: str, title: str, description: str) -> Optional[tuple[str, list[str]]]:
    """
    (prompt, available_sub_teams) 반환. team이 PM 대상 아니면 None.
    DEFAULT + DB 동적 발견을 합친 sub_team 카탈로그 사용 — UI에서 새 분과 추가 시 자동 반영.
    """
    if team == "dev":
        defaults = ["ui", "server", "ingame", "outgame", "general"]
        rules = _DEV_PM_RULES
        label = "개발"
    elif team == "art":
        defaults = ["ui", "background", "illustration", "general"]
        rules = _ART_PM_RULES
        label = "아트"
    elif team == "design":
        defaults = ["content", "level", "motif", "general"]
        rules = _DESIGN_PM_RULES
        label = "기획"
    else:
        return None
    # DB-발견 sub_team을 합쳐서 옵션 확장 (순서: DEFAULT 먼저, 신규 발견 뒤)
    discovered = _discover_sub_teams(team)
    opts: list[str] = []
    seen: set[str] = set()
    for s in [*defaults, *discovered]:
        if s and s not in seen:
            seen.add(s)
            opts.append(s)
    options_text = "\n".join(f"  - {o}" for o in opts)
    prompt = PM_PROMPT_TEMPLATE.format(
        team_label=label, team=team,
        title=title, description=description or "(설명 없음)",
        sub_team_options=options_text,
        decision_rules=rules,
        sub_team_csv=" | ".join(opts),
    )
    return prompt, opts


def format_best_practices_section(team: str, sub_team: str, limit: int = 2) -> str:
    """
    같은 (team, sub_team) 분과의 점수≥85 최근 작업의 plan_summary를
    Lead 프롬프트에 주입해 best-practice 학습 효과를 노린다.
    데이터 없으면 빈 문자열.
    """
    try:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            return ""
        db_name = os.environ.get("MONGODB_DB", "aigame")
        client = MongoClient(uri, serverSelectionTimeoutMS=2000)
        rows = list(client[db_name]["hermes_team_scores"].find(
            {"team": team, "sub_team": sub_team or "general", "score": {"$gte": 85}},
            {"task_id": 1, "score": 1, "summary": 1, "verdict": 1, "created_at": 1},
        ).sort("created_at", -1).limit(limit))
        if not rows:
            return ""
        lines = [f"\n\n## 🏆 같은 분과의 best-practice ({team}/{sub_team or 'general'}, score≥85)"]
        lines.append("이전에 좋은 평가를 받은 작업의 요약입니다. 패턴을 참고하세요.")
        for r in rows:
            sm = (r.get("summary") or "")[:300]
            sc = r.get("score", 0)
            tid = str(r.get("task_id", ""))[-8:]
            lines.append(f"- [{tid}] (score={sc}) {sm}")
        return "\n".join(lines)
    except Exception:
        log.exception("format_best_practices_section failed")
        return ""


def resolve_role(team: str, sub_team: str, kind: str) -> str:
    """
    sub_team-aware role 이름 결정. 우선순위:
      1. {team}_{sub_team}_{kind}   (예: dev_ui_lead)
      2. {team}_{kind}                (예: dev_lead — 거의 안 쓰임)
      3. {kind}                       (예: lead, main_coder)

    호출 시점에 DB와 DEFAULT를 합친 role 매핑에서 존재하는 첫 후보를 반환.
    """
    roles = _load_agent_roles()
    candidates = [
        f"{team}_{sub_team}_{kind}" if sub_team and sub_team != "general" else None,
        f"{team}_{kind}",
        kind,
    ]
    for c in candidates:
        if c and c in roles:
            return c
    # 폴백: kind 그대로 (없으면 invoke_agent에서 unknown role 에러)
    return kind


# ════════════════════════════════════════════════════════════════
# 🎨 아트팀 프롬프트 (계속)
# ════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════
# 🧩 9-Slice 모드 — Unity Sprite Border용 UI 이미지 가이드
# ════════════════════════════════════════════════════════════════
_9SLICE_KEYWORDS = (
    "9slice", "9-slice", "9 slice",
    "나인슬라이스", "나인 슬라이스", "9분할", "9 분할",
    "ninepatch", "nine-patch", "nine patch", "sprite border",
)


def is_9slice_request(*texts: str) -> bool:
    """task title/description/comment 어디든 9-slice 키워드가 있으면 True"""
    blob = " ".join(t for t in texts if t).lower()
    return any(k in blob for k in _9SLICE_KEYWORDS)


def parse_border_px(text: str, default: int = 96) -> int:
    """본문에서 'border 96px', 'slice 48' 같은 패턴이 있으면 그 px 반환, 없으면 default"""
    import re as _re
    if not text:
        return default
    # "border 96", "slice 48px", "9slice 64" 등 모두 매칭
    m = _re.search(r"(?:border|slice|9-?slice|보더|보더값)\s*[:=]?\s*(\d{2,3})\s*(?:px|픽셀)?", text, _re.IGNORECASE)
    if m:
        v = int(m.group(1))
        if 8 <= v <= 256:
            return v
    return default


def get_9slice_guidance(border_px: int = 96, output_size: str = "1024x1024") -> str:
    """art_prompter 프롬프트 끝에 주입할 9-slice 전용 가이드"""
    return f"""

## 🧩 9-SLICE MODE — Critical generation rules

이 요청은 Unity Sprite Border (9-slice scalable) 용 UI 이미지입니다.
다음 규칙을 image_prompt에 영문으로 **명시적으로** 반영해야 stretch 시 자글거리지 않습니다:

- "FLAT solid color fills only. NO noise, NO grain, NO subtle gradients, NO film texture."
- "Uniform interior: center region must be a single flat color so it tiles cleanly when stretched."
- "Decorative detail (shadow, bevel, ornament) is confined to the outer {border_px}px border on each side. Inside is plain."
- "Pixel-aligned sharp edges, minimal anti-aliasing on outline. No fuzzy or blurred edges."
- "Corners are distinctive (rounded/beveled/etc.). Top·bottom·left·right edges are uniform along their length."
- "Designed to be imported as Unity Sprite with 9-slice border = {border_px}px on all 4 sides."
- "Output size: {output_size}, square layout, 1:1 aspect."

권장 size 출력: "{output_size}", n=1, quality="high".
tags 에 반드시 ["9slice", "tileable", "ui_panel"] 포함.
"""


ART_REVIEWER_TEMPLATE = """You are the Art Reviewer for the aimed-puzzle team. **Your primary job is VISUAL inspection of the generated image.**

Task:
Title: {title}
Description: {description}

Generated image prompt: {gpt_prompt}
Image count generated: {n}
Image path on this machine: {image_path}

## ⚠️ FIRST: 이미지를 직접 본다
**가장 먼저 Read 도구로 위 image_path를 열어 실제 이미지를 본다.** 이미지를 보지 않고 점수를 매기지 마라 — 그건 무의미하다.
이미지가 보이지 않거나 path가 비어있으면 verdict="cannot_review", quality_score=null로 응답.

## 시각 검수 기준 (이 순서로 직접 확인)
1. **요청 일치도** — 사용자 원래 요청의 핵심 요소(주제·구도·키 컬러·스타일)가 이미지에 실제로 반영됐는가? 누락/오인된 요소를 구체적으로 적는다.
2. **텍스트 무결성** — 이미지에 글자가 있다면 깨지거나 오타·외계어가 있는가? (gpt-image-2는 한글/긴 문장 글자를 자주 깬다)
3. **구도/해상도** — 가장자리 잘림, 어색한 여백, 흐림, 비대칭, 의도하지 않은 객체 추가가 있는가?
4. **톤앤매너** — 퍼즐/캐주얼 게임 톤에 맞는가? 의도치 않은 sci-fi/공포/성인 톤이 섞이지 않았는가?
5. **기술 적합성** — 9-slice/UI 자산이라면 가장자리가 깨끗한가? 캐릭터/일러라면 배경 처리(투명/단색/풍경)가 의도대로인가?

## 요구 출력 JSON
```json
{{
  "verdict": "ok" | "revise" | "regenerate" | "cannot_review",
  "quality_score": 0-100,
  "visual_observations": ["이미지에서 직접 본 사실 3-5개 — 짧게"],
  "issues_found": ["발견한 문제 0-N개 — 텍스트 깨짐/요소 누락 등"],
  "notes": "전반 검수 의견 2~3줄",
  "suggested_prompt_adjustments": "verdict=revise/regenerate일 때만 — 다음 시도용 프롬프트 수정안"
}}
```

품질 점수 기준 (시각적 결과 기준 — 프롬프트 좋아도 결과가 나쁘면 점수 낮춤):
- 90-100: 의도 100% 반영, 결과물 우수, 즉시 사용 가능
- 75-89:  의도 대체로 반영, 사소한 보정만 필요
- 60-74:  의도 부분 반영, 한두 요소 누락 또는 가벼운 결함
- 40-59:  의도 일부만 반영 또는 두드러진 결함, revise 권장
- 0-39:   의도 거의 미반영 또는 텍스트 깨짐/큰 결함, regenerate 권장
"""


# ════════════════════════════════════════════════════════════════
# 🎓 Senior Reflection — 작업 완료 후 추상화된 도메인 원칙 추출
# ════════════════════════════════════════════════════════════════

SENIOR_REFLECTION_TEMPLATE = """You are a senior tech lead reflecting on a just-completed task in the
aimed-puzzle (Balloonflow) team. Your goal: extract **abstract, reusable principles**
that future similar tasks can benefit from. Not failure-specific tips (those are handled
by failure_learning) but higher-level wisdom — patterns, idioms, gotchas, design tradeoffs.

Completed task:
- Title: {title}
- Team / sub_team: {team} / {sub_team}
- Description: {description}
- Reviewer verdict: {verdict}
- Quality score: {score}/100
- Files changed: {files}
- Diff summary: {diff_summary}
- Reviewer concerns / strengths: {reviewer_notes}

Extract 1~3 principles. Each principle:
- General enough to apply to future similar work in the same {team}/{sub_team}
- Specific enough to be actionable (not "write good code")
- Includes WHY (what problem it solves)
- ≤ 200 chars per principle

For each principle, also indicate whether it transfers to **other sub_teams of the same team**
(cross-team propagation). Example: "Singleton Manager 정리 코드" 같은 원칙은 ingame/outgame 양쪽에 적용 가능
하지만, "Tilemap collider 캐시" 같은 ingame-specific 원칙은 그렇지 않다.

Examples of good principles:
- "Singleton Manager change: 항상 Awake/OnDestroy의 정리 코드 동시 수정 — 메모리 누수 방지"
- "UI Canvas anchor 변경 시 children prefab 회귀 체크 필수 — 자식 anchor가 깨질 수 있음"
- "ScriptableObject 값 변경: 런타임 캐싱 매니저(GameConfig 등)도 같이 보강 필요"

Examples of bad principles (too generic):
- "Write clean code"
- "Test your changes"
- "Follow conventions"

If the task wasn't substantive enough to extract anything (trivial fix, no new insight),
return empty principles list.

Output JSON ONLY:
```json
{{
  "principles": [
    {{
      "principle": "한국어 또는 영문 (≤200자)",
      "applies_to": "domain hint — 예: 'Singleton Manager 수정', 'UI anchor 변경'",
      "applies_to_teams": ["ingame", "outgame"],
      "why": "이 원칙이 해결하는 문제 1줄"
    }}
  ]
}}
```

`applies_to_teams` 작성 가이드:
- 같은 {team} 안에서 이 원칙이 유효한 sub_team들을 나열. 본인 sub_team({sub_team})은 포함하지 않아도 됨 (자동 포함됨).
- 정말 sub_team-specific이면 빈 배열 [] 또는 생략.
- "all"을 넣으면 같은 {team} 모든 sub_team에 적용된다는 뜻.
"""
