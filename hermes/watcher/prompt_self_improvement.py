"""
Prompt Self-Improvement — 실패 케이스 reflection으로 role별 프롬프트 패치 자동 생성

failure_learning은 카테고리별 하드코딩 템플릿만 사용 → 진짜 자기 개선이 아님.
이 모듈은:
  1. 실패 발생 시 동일 role+category 누적 임계값 도달하면
  2. LLM(reflection)에게 실패 케이스 + 현재 페르소나/프롬프트 보여주고
  3. "어떤 짧은 추가 지시(patch)가 이 실패를 막을 수 있겠나?" 물어봐
  4. 응답을 hermes_prompt_patches 컬렉션에 저장 → invoke_agent 호출 시 자동 주입
  5. 패치 적용 후 점수 변동 추적, 분명히 악화되면 자동 revert

데이터 흐름:
  failure → reflect_and_propose → patches[role=X, status=active]
  next call → load_active_patches_text(X) → 프롬프트 상단 주입
  reviewer 점수 수집 → update_patch_score → 악화 시 revert
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

log = logging.getLogger("prompt-self-improve")

PATCHES_COLLECTION = "hermes_prompt_patches"
ACTIVITY_COLLECTION = "activity_logs"
SCORES_COLLECTION = "hermes_team_scores"

# 동일 role+category가 이만큼 누적되면 reflection 트리거
REFLECTION_THRESHOLD = int(os.environ.get("HERMES_REFLECTION_THRESHOLD", "2"))
# reflection 시 최근 몇 시간 내 실패만 본다
REFLECTION_LOOKBACK_HOURS = int(os.environ.get("HERMES_REFLECTION_LOOKBACK_HOURS", "168"))  # 7일
# 패치 적용 후 이만큼 점수 표본이 쌓이면 효과 평가
PATCH_EVAL_MIN_SAMPLES = int(os.environ.get("HERMES_PATCH_EVAL_SAMPLES", "5"))
# 패치 적용 후 평균 점수가 이 값 이상 떨어지면 자동 revert
PATCH_REVERT_THRESHOLD = float(os.environ.get("HERMES_PATCH_REVERT_THRESHOLD", "5.0"))
# 같은 role에 active 패치는 최대 N개까지만 (프롬프트 비대화 방지)
MAX_ACTIVE_PATCHES_PER_ROLE = int(os.environ.get("HERMES_MAX_PATCHES_PER_ROLE", "3"))
# 진실성 게이트(D): 신규 패치는 'candidate'로 들어가 적용·측정되되, '객관적으로 수용된'
# 작업을 이만큼 통과해야(+골든 통과 시) 'active'로 승격. 검증 안 된 패치 영구화 방지.
PATCH_PROBATION_SAMPLES = int(os.environ.get("HERMES_PATCH_PROBATION_SAMPLES", "3"))


# ──────────────────────────────────────────────────────────
# DB 헬퍼
# ──────────────────────────────────────────────────────────
def _get_db():
    """MongoDB DB 핸들 — agent_team / executor 어디서 호출하든 동작"""
    try:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            return None
        db_name = os.environ.get("MONGODB_DB", "aigame")
        return MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    except Exception:
        log.exception("_get_db failed")
        return None


# ──────────────────────────────────────────────────────────
# 패치 로드 — 프롬프트 주입용
# ──────────────────────────────────────────────────────────
def load_active_patches_text(role: str) -> str:
    """
    해당 role의 active 패치들을 한 덩어리 텍스트로 반환.
    invoke_agent의 페르소나 주입 다음에 호출.
    """
    db = _get_db()
    if db is None:
        return ""
    try:
        # active + candidate 모두 주입(candidate도 적용·측정 대상 — 단 영구화는 수용 게이트 후)
        rows = list(
            db[PATCHES_COLLECTION]
            .find({"role": role, "status": {"$in": ["active", "candidate"]}})
            .sort("created_at", 1)
            .limit(MAX_ACTIVE_PATCHES_PER_ROLE)
        )
    except Exception:
        log.exception("load_active_patches_text failed for role=%s", role)
        return ""
    if not rows:
        return ""
    header = (
        "# ⚙️ AUTO-LEARNED PATCHES (이전 실패에서 학습한 추가 지시)\n"
        "다음은 같은 실수 반복을 막기 위해 자동 적용된 가이드입니다.\n\n"
    )
    bullets = "\n".join(
        f"- {(r.get('patch_text') or '').strip()}"
        for r in rows
        if (r.get("patch_text") or "").strip()
    )
    if not bullets:
        return ""
    return header + bullets + "\n\n---\n\n"


# ──────────────────────────────────────────────────────────
# Reflection — LLM에게 패치 제안 요청
# ──────────────────────────────────────────────────────────
_REFLECT_PROMPT = """You are a prompt engineer reviewing failures of an AI agent role
in the aimed-puzzle (mobile casual puzzle game) team.

Agent role: {role}
Role persona summary:
{persona_excerpt}

Recent failures of this role ({fail_count} total in last {hours}h):
{failure_summaries}

Recent successes of the same role (for contrast, if any):
{success_summaries}

Active prompt patches already applied to this role (do NOT propose duplicates):
{existing_patches}

🚫 BAD CASES — 사용자가 "방향 자체가 어긋남" 또는 "결과 불일치"로 영구 차단한 패치들.
이런 방향은 절대 다시 제안하면 안 됨. 키워드만 살짝 바꾼 변형도 금지:
{bad_cases}

Your task: propose 1~2 SHORT prompt addenda that, if injected at the top of this role's
system prompt, would have prevented these failures. Each patch must:
- Be ≤ 240 characters
- Be specific and actionable (NOT generic advice)
- Address the failure pattern, not the symptom
- NOT duplicate existing active patches
- NOT match the direction of any BAD CASE listed above

If you cannot propose anything useful (failures look unrelated, or all reasonable
directions are already covered by BAD CASES), return empty patches list.

Output JSON ONLY:
```json
{{
  "patches": [
    {{
      "patch_text": "한국어 또는 영문 짧은 지시 (≤240자)",
      "rationale": "왜 이 패치가 도움이 되는지 1줄"
    }}
  ]
}}
```
"""


def _summarize_failures(samples: list[dict[str, Any]]) -> str:
    if not samples:
        return "(없음)"
    parts = []
    for s in samples[:5]:
        ts = s.get("timestamp")
        ts_str = ts.isoformat()[:19] if ts else "?"
        cat = s.get("category", "?")
        det = (s.get("details") or "")[:200]
        parts.append(f"- [{ts_str}] cat={cat}: {det}")
    return "\n".join(parts)


def _summarize_successes(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "(없음)"
    parts = []
    for r in rows[:3]:
        ts = r.get("created_at", "?")[:19]
        score = r.get("score", "?")
        sm = (r.get("summary") or "")[:150]
        parts.append(f"- [{ts}] score={score}: {sm}")
    return "\n".join(parts)


def reflect_and_propose(
    role: str,
    failure_category: str,
) -> int:
    """
    동일 role+category 누적이 임계값 넘으면 reflection 호출 → 패치 저장.
    반환값: 저장된 패치 수 (0이면 거른 것).

    호출 시점: _log_and_maybe_learn 내부에서, 같은 role의 같은 카테고리 실패가
    REFLECTION_THRESHOLD 이상일 때.
    """
    db = _get_db()
    if db is None:
        return 0

    # 1. 최근 실패 샘플
    since = datetime.now(timezone.utc) - timedelta(hours=REFLECTION_LOOKBACK_HOURS)
    try:
        fails = list(
            db[ACTIVITY_COLLECTION]
            .find({
                "type": "failure",
                "category": failure_category,
                "agent_role": role,
                "timestamp": {"$gte": since},
            })
            .sort("timestamp", -1)
            .limit(5)
        )
    except Exception:
        log.exception("reflect: failure fetch failed")
        return 0

    if len(fails) < REFLECTION_THRESHOLD:
        return 0

    # 2. 같은 role의 최근 성공 점수 (컨트라스트용)
    try:
        successes = list(
            db[SCORES_COLLECTION]
            .find({"role": role, "score": {"$gte": 80}})
            .sort("created_at", -1)
            .limit(3)
        )
    except Exception:
        successes = []

    # 3. 같은 role에 이미 적용된 active 패치 (중복 방지)
    try:
        existing = list(
            db[PATCHES_COLLECTION].find({"role": role, "status": "active"})
        )
    except Exception:
        existing = []

    if len(existing) >= MAX_ACTIVE_PATCHES_PER_ROLE:
        log.info("[reflect] role=%s already has max patches — skip", role)
        return 0

    # 3-b. Bad Case 패치 — 사용자가 "방향 자체가 잘못됨/결과 불일치"로 명시적 차단한 것
    # → 절대 다시 제안하면 안 됨 (anti-pattern으로 LLM에 강하게 전달)
    try:
        bad_cases = list(
            db[PATCHES_COLLECTION]
            .find({"role": role, "status": "bad_case"})
            .sort("marked_bad_at", -1)
            .limit(10)
        )
    except Exception:
        bad_cases = []

    # 4. 페르소나 발췌 (앞 400자) — reflection LLM 컨텍스트
    persona_excerpt = ""
    try:
        from agent_team import _load_agent_roles
        roles = _load_agent_roles()
        if role in roles:
            persona_excerpt = (roles[role].get("persona") or "")[:400]
    except Exception:
        pass

    existing_text = "\n".join(
        f"- {(p.get('patch_text') or '')[:200]}" for p in existing
    ) or "(없음)"

    bad_cases_text = "\n".join(
        f"- \"{(p.get('patch_text') or '')[:200]}\" "
        f"(사유: {p.get('bad_case_reason') or '명시 안 됨'} — {(p.get('bad_case_note') or '')[:120]})"
        for p in bad_cases
    ) or "(없음 — 첫 reflection이거나 아직 사용자 차단 없음)"

    prompt = _REFLECT_PROMPT.format(
        role=role,
        persona_excerpt=persona_excerpt or "(페르소나 등록 안 됨)",
        fail_count=len(fails),
        hours=REFLECTION_LOOKBACK_HOURS,
        failure_summaries=_summarize_failures(fails),
        success_summaries=_summarize_successes(successes),
        existing_patches=existing_text,
        bad_cases=bad_cases_text,
    )

    # 5. Reflection LLM 호출 — 저비용 모델로 충분
    try:
        from agent_team import ExecutionEnv, invoke_agent
        from pathlib import Path
        env = ExecutionEnv(
            mode="local", cwd=str(Path.home()), timeout_sec=60,
            task_id=None, task_title=f"reflect:{role}",
        )
        # 새 가상 역할 'reflector' — DB에 없으면 sub-coder-agent로 폴백
        resp = invoke_agent("reflector", prompt, env)
        if not resp.success:
            # reflector 역할이 없으면 sub-coder-agent 직접 호출 (더 단순한 이름)
            log.info("[reflect] reflector role missing, retry as sub-coder-agent")
            resp = invoke_agent("sub_coder", prompt, env)
            if not resp.success:
                log.warning("[reflect] both calls failed: %s", resp.error)
                return 0
    except Exception:
        log.exception("[reflect] invoke_agent failed")
        return 0

    out = resp.structured or {}
    patches = out.get("patches") or []
    if not isinstance(patches, list):
        return 0

    # 6. 패치 저장
    saved = 0
    now = datetime.now(timezone.utc)
    fail_ids = [str(f.get("task_id", "")) for f in fails]
    for p in patches[: MAX_ACTIVE_PATCHES_PER_ROLE - len(existing)]:
        if not isinstance(p, dict):
            continue
        text = (p.get("patch_text") or "").strip()
        rationale = (p.get("rationale") or "").strip()
        if not text or len(text) > 240:
            continue
        # 동일 텍스트 중복 방지
        if db[PATCHES_COLLECTION].find_one({"role": role, "patch_text": text}):
            continue

        # score_before — 패치 적용 직전의 같은 role 평균 점수
        try:
            agg = list(
                db[SCORES_COLLECTION].aggregate([
                    {"$match": {"role": role}},
                    {"$group": {"_id": None, "avg": {"$avg": "$score"}, "count": {"$sum": 1}}},
                ])
            )
            score_before = float(agg[0]["avg"]) if agg else None
        except Exception:
            score_before = None

        db[PATCHES_COLLECTION].insert_one({
            "role": role,
            "patch_text": text,
            "rationale": rationale,
            # 진실성 게이트(D): candidate로 시작 — 적용·측정되되 수용 게이트 통과 전엔 영구화 안 됨
            "status": "candidate",
            "addresses_failures": fail_ids[:5],
            "addresses_category": failure_category,
            "created_at": now.isoformat(),
            "activated_at": now.isoformat(),
            "score_before": score_before,
            "score_after": None,
            "samples_after": 0,
            "accepted_samples": 0,   # 객관적으로 수용된 작업 통과 횟수 (promote 기준)
            "reverted_at": None,
            "revert_reason": None,
        })
        saved += 1
        log.info("[reflect] new patch for role=%s: %s", role, text[:80])

    return saved


# ──────────────────────────────────────────────────────────
# 패치 효과 트래킹 — 점수 들어올 때마다 호출
# ──────────────────────────────────────────────────────────
def track_score_for_patches(role: str, score: int) -> None:
    """
    Reviewer가 점수 매긴 직후 호출. 해당 role의 active 패치들이 있으면
    score_after 평균 갱신, 표본 충분히 쌓이고 명백히 악화면 자동 revert.
    """
    db = _get_db()
    if db is None:
        return
    try:
        # active + candidate 모두 효과 추적(악화 시 자동 revert — candidate도 즉시 폐기 가능)
        active = list(db[PATCHES_COLLECTION].find(
            {"role": role, "status": {"$in": ["active", "candidate"]}}))
    except Exception:
        log.exception("track_score: fetch active failed")
        return

    now = datetime.now(timezone.utc).isoformat()
    for p in active:
        n = int(p.get("samples_after") or 0)
        prev_avg = float(p.get("score_after") or 0.0)
        # incremental average
        new_n = n + 1
        new_avg = (prev_avg * n + score) / new_n
        update = {"samples_after": new_n, "score_after": round(new_avg, 2)}

        # 자동 revert 검토
        if new_n >= PATCH_EVAL_MIN_SAMPLES:
            sb = p.get("score_before")
            if isinstance(sb, (int, float)) and (sb - new_avg) >= PATCH_REVERT_THRESHOLD:
                update["status"] = "reverted"
                update["reverted_at"] = now
                update["revert_reason"] = (
                    f"score dropped: before={sb:.1f}, after={new_avg:.1f} "
                    f"(n={new_n}, threshold={PATCH_REVERT_THRESHOLD})"
                )
                log.info("[reflect] AUTO-REVERT patch role=%s — %s",
                         role, update["revert_reason"])

        try:
            db[PATCHES_COLLECTION].update_one({"_id": p["_id"]}, {"$set": update})
        except Exception:
            log.exception("track_score: update failed")


# ──────────────────────────────────────────────────────────
# 진실성 게이트(D) — 객관적 수용 시 candidate 패치 승격
# ──────────────────────────────────────────────────────────
def _golden_ok(role: str) -> bool:
    """골든 회귀 테스트 게이트. 지원 역할이면 통과해야 True.
    하네스 미가용/미지원 역할은 fail-open(True) — 표본 프로베이션만 적용.
    (golden 커버리지 확대는 후속: 현재 design_level_designer만 지원)"""
    try:
        from harness import eval as _ev  # noqa: N813
    except Exception:
        return True
    try:
        supported = getattr(_ev, "SUPPORTED_ROLES", {"design_level_designer"})
        if role not in supported:
            return True
        runner = getattr(_ev, "run_eval", None)
        if runner is None:
            return True
        res = runner(role=role)
        return bool(res and float(res.get("pass_rate", 0) or 0) >= 0.7)
    except Exception:
        log.exception("_golden_ok failed (fail-open)")
        return True


def promote_candidates_on_acceptance(role: str, score: int) -> None:
    """객관적으로 수용된 작업(done으로 ship)에서만 호출.
    해당 role의 candidate 패치 accepted 표본을 +1, 충분히 검증되고(+골든 통과 시)
    악화가 없으면 active로 승격. 검증 안 된 패치가 영구 반영되는 걸 막는다."""
    db = _get_db()
    if db is None:
        return
    try:
        cands = list(db[PATCHES_COLLECTION].find({"role": role, "status": "candidate"}))
    except Exception:
        log.exception("promote_candidates: fetch failed")
        return
    now = datetime.now(timezone.utc).isoformat()
    for p in cands:
        n = int(p.get("accepted_samples") or 0) + 1
        update: dict[str, Any] = {"accepted_samples": n}
        # 악화하지 않았는지(track_score_for_patches가 이미 score_after 갱신) + 표본 충분 + 골든 통과
        sb = p.get("score_before")
        sa = p.get("score_after")
        regressed = (
            isinstance(sb, (int, float)) and isinstance(sa, (int, float))
            and (sb - sa) >= PATCH_REVERT_THRESHOLD
        )
        if n >= PATCH_PROBATION_SAMPLES and not regressed and _golden_ok(role):
            update["status"] = "active"
            update["promoted_at"] = now
            log.info("[reflect] PROMOTE candidate→active role=%s (accepted=%d): %s",
                     role, n, (p.get("patch_text") or "")[:60])
        try:
            db[PATCHES_COLLECTION].update_one({"_id": p["_id"]}, {"$set": update})
        except Exception:
            log.exception("promote_candidates: update failed")


# ──────────────────────────────────────────────────────────
# 외부에서 직접 패치 revert (admin 운영용)
# ──────────────────────────────────────────────────────────
def revert_patch(patch_id: str, reason: str = "manual revert") -> bool:
    """단순 비활성화 — LLM이 다시 비슷한 방향 제안할 수도 있음 (잡음/일시적 노이즈용)"""
    db = _get_db()
    if db is None:
        return False
    try:
        from bson import ObjectId
        res = db[PATCHES_COLLECTION].update_one(
            {"_id": ObjectId(patch_id), "status": "active"},
            {"$set": {
                "status": "reverted",
                "reverted_at": datetime.now(timezone.utc).isoformat(),
                "revert_reason": reason[:500],
            }},
        )
        return res.modified_count > 0
    except Exception:
        log.exception("revert_patch failed")
        return False


# Bad Case 분류 — 사용자가 명시적으로 "방향 자체가 어긋남/결과 불일치" 판정한 경우.
# reflect_and_propose가 매번 LLM에 "이 방향 다시 제안 금지"로 강하게 전달.
BAD_CASE_REASONS = {"off_direction", "wrong_result", "other"}


def mark_bad_case(patch_id: str, reason: str = "off_direction", note: str = "") -> bool:
    """
    패치를 영구 anti-pattern으로 등록.
    reason: off_direction(방향 어긋남) | wrong_result(결과 불일치) | other
    note:   추가 설명 (선택)

    이미 reverted 상태인 패치도 bad_case로 승격 가능.
    """
    db = _get_db()
    if db is None:
        return False
    if reason not in BAD_CASE_REASONS:
        reason = "other"
    try:
        from bson import ObjectId
        res = db[PATCHES_COLLECTION].update_one(
            {"_id": ObjectId(patch_id), "status": {"$in": ["active", "reverted"]}},
            {"$set": {
                "status": "bad_case",
                "bad_case_reason": reason,
                "bad_case_note": note[:500],
                "marked_bad_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return res.modified_count > 0
    except Exception:
        log.exception("mark_bad_case failed")
        return False
