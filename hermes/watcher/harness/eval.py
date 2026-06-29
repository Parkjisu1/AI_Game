"""
H4 Evaluation — golden test set + 회귀 감지.

핵심 컴포넌트:

1. GoldenCase — 1개 정답 케이스 (input prompt + expected output + metadata)
2. extract_golden_*() — 기존 데이터에서 정답 추출
   - extract_golden_from_levels: 별점 ≥4 grid level의 designer spec → golden
   - extract_golden_from_tasks: (확장 여지) task별 best output

3. compare_specs / compare_levels — 필드 레벨 유사도 (0..1)
4. run_eval_case — golden case를 재실행, 비교, 결과 반환
5. run_all_eval — DB의 모든 golden 실행, 결과 hermes_eval_runs에 누적

저장:
  hermes_eval_golden  — 추출된 golden cases
    {_id, role, source_id, source_score, input, expected, created_at}
  hermes_eval_runs    — eval 실행 기록
    {_id, case_id, role, run_at, pass, score, diff_summary, duration_ms}

실행:
  python harness/eval.py extract --role design_level_designer --min_score 4
  python harness/eval.py run --role design_level_designer
  python harness/eval.py run --all      # 모든 role 회귀
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("harness.eval")

GOLDEN_COLLECTION = "hermes_eval_golden"
RUNS_COLLECTION = "hermes_eval_runs"

# Pass threshold for regression detection
DEFAULT_PASS_THRESHOLD = 0.7


# ──────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────
@dataclass
class GoldenCase:
    """1개 정답 케이스."""
    case_id: str            # 고유 ID
    role: str               # agent role (e.g. design_level_designer)
    source_id: str          # 원본 데이터 ID (level_id, task_id)
    source_score: float     # 원본 별점/점수
    input: dict[str, Any]   # input prompt context (재실행용)
    expected: dict[str, Any]  # 정답 spec/output
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvalResult:
    """1번 eval 실행 결과."""
    case_id: str
    role: str
    passed: bool
    score: float            # 0..1 유사도
    diff_summary: str
    duration_ms: int
    actual: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    run_at: str = ""


# ──────────────────────────────────────────────
# DB helper
# ──────────────────────────────────────────────
def _get_db():
    try:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            return None
        db_name = os.environ.get("MONGODB_DB", "aigame")
        return MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    except Exception:
        return None


# ──────────────────────────────────────────────
# Golden 추출 (level designer)
# ──────────────────────────────────────────────
def extract_golden_from_levels(
    *, min_score: int = 4, max_cases: int = 100,
) -> list[GoldenCase]:
    """
    pixelforge_grid_levels에서 user_score >= min_score 인 doc → golden case.

    각 case:
      input  = {prompt: <natural language regenerated from spec>, original_spec_keywords: ...}
      expected = {width, height, symmetry, palette, per_color_count, pattern, mood, ...}
    """
    db = _get_db()
    if db is None:
        return []

    cases: list[GoldenCase] = []
    cursor = db["pixelforge_grid_levels"].find(
        {"user_score": {"$gte": min_score}},
    ).sort("user_score", -1).limit(max_cases)
    for doc in cursor:
        spec = {
            "width": doc.get("width"),
            "height": doc.get("height"),
            "symmetry": doc.get("symmetry"),
            "palette": doc.get("palette") or [],
            "pattern": doc.get("pattern"),
            "mood": doc.get("mood"),
            "per_color_count": doc.get("per_color_count") or {},
        }
        # input: 별점 매겨진 task의 원본 prompt 재구성 (mood 기반 자연어)
        # 가장 자연스러운 형태: "[level] {mood} 풍 25x25 {pattern} 4색"
        mood = spec.get("mood") or "kaleidoscope"
        pattern = spec.get("pattern") or "kaleidoscope"
        prompt = (
            f"[level] {spec['width']}x{spec['height']} {mood} 풍 {pattern} 4색 패턴, "
            f"BalloonFlow 레벨용"
        )
        case = GoldenCase(
            case_id=f"level_{str(doc['_id'])}",
            role="design_level_designer",
            source_id=str(doc["_id"]),
            source_score=float(doc.get("user_score") or 0),
            input={"prompt": prompt, "title": f"[level] {mood} {pattern}", "description": ""},
            expected=spec,
            metadata={
                "team_id": doc.get("team_id"),
                "name": doc.get("name"),
                "created_at": doc.get("created_at"),
            },
        )
        cases.append(case)
    return cases


def save_golden_cases(cases: list[GoldenCase]) -> int:
    """golden cases를 hermes_eval_golden에 upsert. 이미 있으면 skip (case_id unique)."""
    db = _get_db()
    if db is None:
        return 0
    coll = db[GOLDEN_COLLECTION]
    saved = 0
    now = datetime.now(timezone.utc).isoformat()
    for case in cases:
        doc = asdict(case)
        doc["_id"] = case.case_id
        doc["created_at"] = now
        try:
            coll.replace_one({"_id": case.case_id}, doc, upsert=True)
            saved += 1
        except Exception:
            log.exception("save golden case failed: %s", case.case_id)
    return saved


def load_golden_cases(role: Optional[str] = None) -> list[GoldenCase]:
    db = _get_db()
    if db is None:
        return []
    flt = {"role": role} if role else {}
    out: list[GoldenCase] = []
    for doc in db[GOLDEN_COLLECTION].find(flt):
        out.append(GoldenCase(
            case_id=doc["_id"],
            role=doc["role"],
            source_id=doc.get("source_id", ""),
            source_score=float(doc.get("source_score") or 0),
            input=doc.get("input") or {},
            expected=doc.get("expected") or {},
            metadata=doc.get("metadata") or {},
        ))
    return out


# ──────────────────────────────────────────────
# Comparison — field-level similarity
# ──────────────────────────────────────────────
def _jaccard(a: list[Any], b: list[Any]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _normalized_distance(a: float, b: float, scale: float = 100.0) -> float:
    """0..1 — 1이 같음. scale은 max-min 추정값."""
    return max(0.0, 1.0 - abs(a - b) / max(scale, 1.0))


def compare_level_specs(actual: dict, expected: dict) -> tuple[float, dict[str, float]]:
    """
    design_level_designer 출력 비교. 각 필드별 0..1 점수 + 가중 평균.

    가중치:
      symmetry / pattern / mood:  exact match 0/1, 무거움 (0.20 each)
      palette:                    Jaccard (0.20)
      width / height:             exact (0.05 each)
      per_color_count:            10배수 만족 + Jaccard of color keys (0.10)
    """
    scores: dict[str, float] = {}

    # categorical exact match
    scores["symmetry"] = 1.0 if actual.get("symmetry") == expected.get("symmetry") else 0.0
    scores["pattern"]  = 1.0 if actual.get("pattern")  == expected.get("pattern")  else 0.0
    scores["mood"]     = 1.0 if actual.get("mood")     == expected.get("mood")     else 0.0

    # palette 유사도 (Jaccard)
    scores["palette"] = _jaccard(actual.get("palette") or [], expected.get("palette") or [])

    # width / height exact
    scores["width"]  = 1.0 if actual.get("width")  == expected.get("width")  else 0.0
    scores["height"] = 1.0 if actual.get("height") == expected.get("height") else 0.0

    # per_color_count: 색 키만 Jaccard (count 정확 매칭은 너무 strict)
    a_keys = list(actual.get("per_color_count", {}).keys())
    e_keys = list(expected.get("per_color_count", {}).keys())
    scores["per_color_count_keys"] = _jaccard(a_keys, e_keys)

    weights = {
        "symmetry": 0.20, "pattern": 0.20, "mood": 0.20,
        "palette": 0.20, "per_color_count_keys": 0.10,
        "width": 0.05, "height": 0.05,
    }
    total = sum(scores[k] * weights[k] for k in weights if k in scores)
    return total, scores


# ──────────────────────────────────────────────
# Run eval — re-invoke agent + compare
# ──────────────────────────────────────────────
def run_eval_case(case: GoldenCase, *, threshold: float = DEFAULT_PASS_THRESHOLD) -> EvalResult:
    """
    1 case 재실행 + 비교. 실패해도 EvalResult 반환 (error 필드).
    """
    t0 = time.monotonic()
    now = datetime.now(timezone.utc).isoformat()

    if case.role != "design_level_designer":
        return EvalResult(
            case_id=case.case_id, role=case.role,
            passed=False, score=0, diff_summary=f"unsupported role: {case.role}",
            duration_ms=0, run_at=now,
        )

    try:
        from agent_team import ExecutionEnv, invoke_agent
        env = ExecutionEnv(
            mode="local", cwd=str(Path.home()), timeout_sec=120,
            task_id=f"eval_{case.case_id}",
            task_title=f"[eval] {case.case_id}",
            team="design", sub_team="level",
        )
        prompt = case.input.get("prompt") or ""
        resp = invoke_agent("design_level_designer", prompt, env)
        if not resp.success:
            return EvalResult(
                case_id=case.case_id, role=case.role,
                passed=False, score=0,
                diff_summary=f"invoke_agent failed: {resp.error}",
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=resp.error or "unknown",
                run_at=now,
            )
        actual = resp.structured or {}
    except Exception as e:
        log.exception("[eval %s] error", case.case_id)
        return EvalResult(
            case_id=case.case_id, role=case.role,
            passed=False, score=0,
            diff_summary=f"exception: {type(e).__name__}: {e}",
            duration_ms=int((time.monotonic() - t0) * 1000),
            error=str(e), run_at=now,
        )

    score, field_scores = compare_level_specs(actual, case.expected)
    duration = int((time.monotonic() - t0) * 1000)
    diff = ", ".join(f"{k}={v:.2f}" for k, v in sorted(field_scores.items()))
    return EvalResult(
        case_id=case.case_id, role=case.role,
        passed=score >= threshold,
        score=round(score, 3),
        diff_summary=diff,
        duration_ms=duration,
        actual={k: v for k, v in actual.items()
                if k in {"width", "height", "symmetry", "pattern", "mood", "palette", "per_color_count"}},
        run_at=now,
    )


def save_eval_results(results: list[EvalResult]) -> int:
    db = _get_db()
    if db is None:
        return 0
    coll = db[RUNS_COLLECTION]
    saved = 0
    now = datetime.now(timezone.utc).isoformat()
    batch_id = f"batch_{now[:19]}"
    for r in results:
        doc = asdict(r)
        doc["batch_id"] = batch_id
        doc["created_at"] = now
        try:
            coll.insert_one(doc)
            saved += 1
        except Exception:
            log.exception("save eval result failed: %s", r.case_id)
    return saved


def run_all_eval(role: Optional[str] = None, *, max_cases: Optional[int] = None) -> dict:
    """golden 모두 (또는 role 한정) 실행. 결과 저장 + 요약."""
    cases = load_golden_cases(role=role)
    if max_cases:
        cases = cases[:max_cases]
    if not cases:
        return {"total": 0, "passed": 0, "failed": 0, "avg_score": 0.0, "results": []}

    print(f"\n=== eval start: role={role or 'all'} cases={len(cases)} ===")
    t0 = time.monotonic()
    results: list[EvalResult] = []
    for i, case in enumerate(cases, 1):
        r = run_eval_case(case)
        results.append(r)
        mark = "✓" if r.passed else "✗"
        print(f"  [{i:3d}/{len(cases)}] {mark} {case.case_id[:30]:30s} "
              f"score={r.score:.2f} ({r.duration_ms}ms)")
    save_eval_results(results)

    passed = sum(1 for r in results if r.passed)
    avg = sum(r.score for r in results) / max(1, len(results))
    print(f"\n=== eval done: {passed}/{len(results)} passed, avg score {avg:.3f} "
          f"({time.monotonic() - t0:.1f}s) ===")
    return {
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "avg_score": round(avg, 3),
        "duration_sec": round(time.monotonic() - t0, 1),
        "results": [asdict(r) for r in results],
    }


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────
def _cli_extract(args) -> int:
    if args.role == "design_level_designer":
        cases = extract_golden_from_levels(min_score=args.min_score, max_cases=args.max)
    else:
        print(f"unsupported role for extract: {args.role}")
        return 1
    n = save_golden_cases(cases)
    print(f"extracted + saved {n} golden cases for {args.role}")
    return 0


def _cli_run(args) -> int:
    role = None if args.all else args.role
    summary = run_all_eval(role=role, max_cases=args.max)
    print(json.dumps({"summary": {k: v for k, v in summary.items() if k != "results"}},
                     ensure_ascii=False, indent=2))
    return 0 if summary.get("failed", 0) == 0 else 2


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    extract = sub.add_parser("extract", help="golden 추출 후 DB 저장")
    extract.add_argument("--role", default="design_level_designer")
    extract.add_argument("--min_score", type=int, default=4)
    extract.add_argument("--max", type=int, default=100)

    run = sub.add_parser("run", help="회귀 eval 실행")
    run.add_argument("--role", default="design_level_designer")
    run.add_argument("--all", action="store_true", help="모든 role")
    run.add_argument("--max", type=int, default=None)

    args = ap.parse_args()
    if args.cmd == "extract":
        return _cli_extract(args)
    if args.cmd == "run":
        return _cli_run(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
