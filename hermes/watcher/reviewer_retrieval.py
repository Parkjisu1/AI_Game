"""
Reviewer Retrieval — 유사 과거 task의 cycle history + user 거부 사유를 Reviewer 프롬프트에 주입.

전략 (2-stage):
  1) pixelforge_tasks vector search → 유사 task top-k (사용자 코멘트 포함 임베딩)
  2) 각 task의 hermes_team_scores 조회 → cycle 길이, user_reject 횟수, AI summary chain
  3) 사용자가 무엇을 요청/거부했는지 + AI가 무엇을 놓쳤는지 정리

목적: user_rejected_after_approval 29건 같은 패턴 — AI Reviewer가 OK 줬지만 사용자가
거부한 영역 — 의 구체적 사유를 다음 review에 컨텍스트로 제공.

장애 대응: OpenAI/Atlas 실패 시 빈 문자열 반환 → Reviewer 프롬프트에 영향 0.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

log = logging.getLogger("reviewer-retrieval")

EMBED_MODEL = "text-embedding-3-small"
TASK_SIMILARITY_FLOOR = 0.62
MAX_USER_COMMENT_CHARS = 220
MAX_AI_SUMMARY_CHARS = 180

# 리뷰어 캘리브레이션: APPROVED 표본이 이 이상이고 오승인율이 이 이상이면 경고 주입
CALIB_MIN_SAMPLES = int(os.environ.get("HERMES_CALIB_MIN_SAMPLES", "8"))
CALIB_WARN_RATE = float(os.environ.get("HERMES_CALIB_WARN_RATE", "0.40"))


@lru_cache(maxsize=1)
def _openai_client():
    try:
        from openai import OpenAI
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            return None
        return OpenAI(api_key=key)
    except Exception:
        log.exception("OpenAI client init failed")
        return None


@lru_cache(maxsize=1)
def _mongo_db():
    try:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI")
        if not uri:
            try:
                from dotenv import load_dotenv as _ld
                _ld("/home/aimed/.hermes/watcher/.env")
                uri = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI")
            except Exception:
                uri = None
        if not uri:
            return None
        return MongoClient(uri, serverSelectionTimeoutMS=3000)[os.environ.get("MONGODB_DB", "aigame")]
    except Exception:
        log.exception("Mongo client init failed")
        return None


def _embed(text: str) -> list[float] | None:
    if not text or len(text) < 5:
        return None
    cli = _openai_client()
    if cli is None:
        return None
    try:
        resp = cli.embeddings.create(model=EMBED_MODEL, input=[text[:8000]])
        return resp.data[0].embedding
    except Exception as e:
        log.warning("embed call failed: %s", e)
        return None


def _vector_task_search(qvec: list[float], k: int, exclude_id: str = "") -> list[dict]:
    db = _mongo_db()
    if db is None:
        return []
    pipe = [
        {"$vectorSearch": {
            "index": "vector_index", "path": "embedding",
            "queryVector": qvec, "numCandidates": k * 8, "limit": k + 5,
        }},
        {"$project": {"title": 1, "team": 1, "sub_team": 1, "status": 1, "comments": 1,
                      "_score": {"$meta": "vectorSearchScore"}}},
    ]
    try:
        rows = list(db.pixelforge_tasks.aggregate(pipe))
    except Exception as e:
        log.warning("task vector search failed: %s", e)
        return []
    rows = [r for r in rows if str(r.get("_id")) != exclude_id]
    return rows[:k]


def _scores_for_task(task_id: str) -> list[dict]:
    db = _mongo_db()
    if db is None:
        return []
    try:
        return list(db.hermes_team_scores.find(
            {"task_id": task_id},
            {"verdict": 1, "score": 1, "summary": 1, "role": 1, "created_at": 1},
        ).sort("created_at", 1))
    except Exception:
        return []


def _last_user_comment(task_doc: dict) -> str:
    """가장 최근 사용자(non-hermes) 코멘트 텍스트."""
    comments = task_doc.get("comments") or []
    user = [c for c in comments if isinstance(c, dict) and c.get("author") != "hermes"]
    if not user:
        return ""
    txt = (user[-1].get("text") or user[-1].get("content") or user[-1].get("body") or "")
    return " ".join(txt.split())[:MAX_USER_COMMENT_CHARS]


REJECT_CLASSIFY_MODEL = os.environ.get("HERMES_REJECT_CLASSIFY_MODEL", "gpt-4o-mini")


def classify_reject_type(task_title: str, user_comment: str) -> str:
    """review 상태에서 사용자가 남긴 코멘트가 (직전 APPROVED 산출물에 대한) 진짜 결함 지적인지,
    아니면 새 범위/후속 요청(iteration)인지 분류.

    반환: 'defect' | 'new_scope' | 'unclear'
      - defect    : 승인된 결과물이 틀렸다/안 된다/빠졌다/반대다 등 → 리뷰어 오승인 (페널티 대상)
      - new_scope : "이것도 해줘/추가로/그 다음엔" 등 새 작업 지시 → 리뷰어 책임 아님
      - unclear   : 실패/불명확 (페널티 제외 — 과승인 지표 재오염 방지)
    """
    cmt = (user_comment or "").strip()
    if not cmt:
        return "unclear"
    cli = _openai_client()
    if cli is None:
        return "unclear"
    try:
        import json as _json
        r = cli.chat.completions.create(
            model=REJECT_CLASSIFY_MODEL,
            messages=[
                {"role": "system", "content": (
                    "리뷰가 APPROVED된 작업의 'review' 상태에서 사용자가 남긴 코멘트를 분류한다. "
                    "JSON만 반환: {\"t\":\"defect|new_scope|unclear\"}. "
                    "defect=승인된 결과물이 잘못됐다는 지적(안 됨/틀림/누락/반대/다시/버그/깨짐/왜 안). "
                    "new_scope=승인물은 괜찮고 추가·후속 작업을 새로 지시(이것도/추가로/그 다음/또 하나/새 리소스 매핑). "
                    "불명확하면 unclear."
                )},
                {"role": "user", "content": f"작업: {task_title[:150]}\n코멘트: {cmt[:500]}"},
            ],
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=20,
        )
        t = (_json.loads(r.choices[0].message.content or "{}").get("t") or "").strip()
        return t if t in ("defect", "new_scope", "unclear") else "unclear"
    except Exception as e:
        log.warning("classify_reject_type failed: %s", e)
        return "unclear"


def get_calibration(reviewer_role: str) -> "dict | None":
    """hermes_reviewer_calibration에서 해당 리뷰어 신뢰도 doc 조회 (merge-gate 연동용)."""
    db = _mongo_db()
    if db is None or not reviewer_role:
        return None
    try:
        return db.hermes_reviewer_calibration.find_one({"role": reviewer_role})
    except Exception:
        return None


def build_calibration_block(reviewer_role: str) -> str:
    """리뷰어 자기 캘리브레이션 — 과거 'APPROVED 후 사용자가 뒤집은'(user_rejected_after_approval)
    비율을 산출해 hermes_reviewer_calibration에 적재(관측) + 오승인율이 높으면 리뷰어 프롬프트에
    '더 보수적으로' 경고를 주입(자기교정 루프). 데이터/표본 부족·실패 시 빈 문자열."""
    db = _mongo_db()
    if db is None or not reviewer_role:
        return ""
    try:
        S = db.hermes_team_scores
        approved = S.count_documents({"role": reviewer_role, "verdict": "APPROVED"})
        # 오승인은 '진짜 결함(defect)'만 카운트 — 반복개선(new_scope)/불명확(unclear)은 리뷰어 책임이 아니므로 제외.
        # (지표 정확화: 과거엔 review 상태의 모든 사용자 코멘트를 오승인으로 집계해 false_approve_rate가 부풀려짐)
        overturned = S.count_documents({"role": reviewer_role, "verdict": "user_rejected_after_approval", "reject_type": "defect"})
    except Exception:
        log.exception("calibration count failed")
        return ""
    if approved <= 0:
        return ""
    rate = overturned / approved
    reliability = max(0.0, 1.0 - rate)
    try:
        from datetime import datetime, timezone
        db.hermes_reviewer_calibration.update_one(
            {"role": reviewer_role},
            {"$set": {"role": reviewer_role, "approved": approved, "overturned": overturned,
                      "false_approve_rate": round(rate, 3), "reliability": round(reliability, 3),
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True)
    except Exception:
        log.exception("calibration upsert failed")
    # 표본 충분 + 오승인율 높을 때만 경고 주입
    if approved < CALIB_MIN_SAMPLES or rate < CALIB_WARN_RATE:
        return ""
    return (
        "\n\n## ⚖️ 리뷰어 캘리브레이션 경고 (자기인식)\n"
        f"당신({reviewer_role})의 과거 APPROVED 중 **{overturned}/{approved} ({rate * 100:.0f}%)**가 "
        "이후 사용자에게 거부됐습니다(user_rejected_after_approval) — **과승인 경향**이 큽니다.\n"
        "→ 이번 리뷰는 **더 보수적으로**: 기획 의도 부합·회귀·계약 일치가 조금이라도 불확실하면 "
        "APPROVED 대신 **REQUEST_CHANGES**. 컴파일/문법 통과만으로 승인하지 말 것."
    )


FAILPAT_MODEL = os.environ.get("HERMES_FAILPAT_MODEL", "gpt-4o-mini")


def _related_role(base: str, other_role: str) -> bool:
    """같은 도메인 계열 리뷰어인지 (dev_ingame_fx ↔ dev_ingame* 처럼 sub_team 토큰 공유)."""
    stop = {"dev", "art", "design", "reviewer", "general"}
    a = {t for t in base.split("_") if t and t not in stop}
    b = {t for t in other_role.replace("_reviewer", "").split("_") if t and t not in stop}
    return bool(a & b)


def _gather_defect_comments(db, reviewer_role: str) -> list[str]:
    """해당 리뷰어의 '진짜 결함(defect)' 거부 사유 수집. thin이면 같은 도메인 계열로 broaden."""
    def _pull(role):
        out = []
        for r in db.hermes_team_scores.find(
            {"role": role, "verdict": "user_rejected_after_approval", "reject_type": "defect"},
            {"reject_comment": 1},
        ):
            c = (r.get("reject_comment") or "").strip()
            if c:
                out.append(c)
        return out
    comments: list[str] = []
    for c in _pull(reviewer_role):
        if c not in comments:
            comments.append(c)
    if len(comments) < 3:
        base = reviewer_role.replace("_reviewer", "")
        for r in db.hermes_team_scores.find(
            {"verdict": "user_rejected_after_approval", "reject_type": "defect", "role": {"$regex": "reviewer$"}},
            {"reject_comment": 1, "role": 1},
        ):
            rr = r.get("role", "")
            if rr == reviewer_role or not _related_role(base, rr):
                continue
            c = (r.get("reject_comment") or "").strip()
            if c and c not in comments:
                comments.append(c)
    return comments[:12]


def _distill_patterns(reviewer_role: str, comments: list[str]) -> list[str]:
    cli = _openai_client()
    if cli is None or not comments:
        return []
    try:
        import json as _json
        joined = "\n".join(f"- {c[:220]}" for c in comments)
        r = cli.chat.completions.create(
            model=FAILPAT_MODEL,
            messages=[
                {"role": "system", "content": (
                    "아래는 리뷰가 APPROVED된 뒤 사용자가 실제로 거부한 결함 사유들이다. "
                    "미래 리뷰어가 변경 내용과 하나씩 대조할 수 있는 **구체적·검증가능한 체크 항목** 3~6개로 유형화하라. "
                    "각 항목은 '어떤 조건/시점/대상을 확인'하는 형태(예: '사운드/BGM 재생·정지 시점이 지정된 트리거와 정확히 일치하는가'). "
                    "JSON만: {\"p\":[\"...\",\"...\"]}"
                )},
                {"role": "user", "content": f"리뷰어: {reviewer_role}\n거부 사유:\n{joined}"},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
            max_tokens=400,
        )
        arr = _json.loads(r.choices[0].message.content or "{}").get("p") or []
        return [str(x).strip() for x in arr if str(x).strip()][:6]
    except Exception as e:
        log.warning("distill_patterns failed: %s", e)
        return []


def get_failure_patterns(reviewer_role: str) -> list[str]:
    """리뷰어 도메인의 '실제 결함(defect) 거부 사유'를 유형화한 체크 리스트 반환.
    캐시(hermes_reviewer_failure_patterns), 표본 수 변동 시에만 LLM 재증류. 리뷰어/코더 공용."""
    db = _mongo_db()
    if db is None or not reviewer_role:
        return []
    try:
        comments = _gather_defect_comments(db, reviewer_role)
        if not comments:
            return []
        sig = len(comments)
        cache = db.hermes_reviewer_failure_patterns.find_one({"role": reviewer_role})
        if cache and cache.get("sig") == sig and cache.get("patterns"):
            return cache["patterns"]
        patterns = _distill_patterns(reviewer_role, comments)
        if patterns:
            from datetime import datetime, timezone
            db.hermes_reviewer_failure_patterns.update_one(
                {"role": reviewer_role},
                {"$set": {"role": reviewer_role, "sig": sig, "patterns": patterns,
                          "updated_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True)
        return patterns
    except Exception:
        log.exception("get_failure_patterns failed")
        return []


def build_failure_pattern_block(reviewer_role: str) -> str:
    """리뷰어용: 과거 거부된 결함 유형을 대조 체크로 주입."""
    patterns = get_failure_patterns(reviewer_role)
    if not patterns:
        return ""
    lines = [
        "\n\n## 🎯 이 도메인에서 실제로 반려된 실패 패턴 (과거 사용자 거부 근거)",
        "리뷰 통과 후 사용자가 실제 거부한 사유를 유형화한 것이다. **이번 변경이 같은 함정에 빠지지 않는지 하나씩 대조**하고, 하나라도 불확실하면 APPROVED 대신 REQUEST_CHANGES.",
    ]
    for i, p in enumerate(patterns, 1):
        lines.append(f"{i}. {p}")
    return "\n".join(lines)


def _coder_to_reviewer_role(coder_role: str) -> str:
    """코더 역할 → 대응 리뷰어 역할 (도메인 실패패턴 조회용)."""
    r = (coder_role or "").strip()
    if not r or r in ("main_coder", "sub_coder", "optimizer", "lead"):
        return "reviewer"
    if r.endswith("_coder"):
        return r[:-6] + "_reviewer"
    if r.endswith("_lead"):
        return r[:-5] + "_reviewer"
    return "reviewer"


def build_coder_guardrails_block(coder_role: str) -> str:
    """코더용: 이 도메인 과거 결함 유형을 '구현 전 회피' 가드레일로 선주입 → 첫 시도 정확성 ↑."""
    patterns = get_failure_patterns(_coder_to_reviewer_role(coder_role))
    if not patterns:
        return ""
    lines = [
        "\n\n## ⚠️ 이 도메인 과거 반려 함정 — 구현 전 필수 회피",
        "아래는 이 영역에서 과거 리뷰 통과 후에도 사용자가 실제 거부한 유형이다. **처음부터 이 조건들을 만족시켜 구현**하라(재작업 방지):",
    ]
    for i, p in enumerate(patterns, 1):
        lines.append(f"{i}. {p}")
    return "\n".join(lines)


def build_retrieval_block(task_title: str, task_description: str, current_task_id: str = "") -> str:
    """Reviewer 프롬프트에 끼울 컨텍스트 블록 (markdown)."""
    query = f"{task_title}\n{task_description or ''}".strip()[:2000]
    qvec = _embed(query)
    if qvec is None:
        return ""

    tasks = _vector_task_search(qvec, k=4, exclude_id=current_task_id)
    tasks = [t for t in tasks if t.get("_score", 0) >= TASK_SIMILARITY_FLOOR]
    if not tasks:
        return ""

    sections: list[str] = []
    high_risk: list[str] = []  # cycle≥5 이거나 user_reject가 있는 task

    for t in tasks:
        tid = str(t.get("_id"))
        sim = t.get("_score", 0)
        title = (t.get("title") or "").strip()
        scores = _scores_for_task(tid)

        if not scores:
            sections.append(f"- [{sim:.2f}] {title} *(점수 기록 없음)*")
            continue

        cycles = len(scores)
        n_user_rej = sum(1 for s in scores if (s.get("verdict") or "") == "user_rejected_after_approval")
        n_request_changes = sum(1 for s in scores if (s.get("verdict") or "").upper() == "REQUEST_CHANGES")
        last_summary = (scores[-1].get("summary") or "")[:MAX_AI_SUMMARY_CHARS]
        user_comment = _last_user_comment(t)

        is_risky = cycles >= 5 or n_user_rej >= 2
        risk_tag = "🚨 HIGH-RISK" if is_risky else "ℹ️"

        block = (
            f"\n#### {risk_tag} [{sim:.2f}] {title}\n"
            f"- cycles: {cycles} | user_rejected: {n_user_rej} | request_changes: {n_request_changes}\n"
            f"- last AI verdict: {scores[-1].get('verdict','?')} ({scores[-1].get('score','?')}/100) — {last_summary}\n"
        )
        if user_comment:
            block += f"- 🗣️ 사용자 마지막 요청/지적: \"{user_comment}\"\n"
        sections.append(block)
        if is_risky:
            high_risk.append(title)

    header = "## 📚 유사 과거 task 검토 (Vector Search retrieval)\n"
    header += (
        "이 task와 유사했던 과거 사례입니다. **HIGH-RISK 표시는 5+ cycle 또는 사용자 거부 2회 이상** 발생한 영역입니다 — "
        "같은 함정에 빠지지 않도록 변경 내용에서 동일 패턴을 점검하세요.\n"
    )
    if high_risk:
        header += f"\n⚠️ HIGH-RISK 영역 ({len(high_risk)}건): {', '.join(high_risk[:3])}\n"
    body = "\n".join(sections)
    footer = (
        "\n\n**검토 지시**: 위 사용자 지적/요청과 **이번 변경 내용을 직접 매칭**하여, "
        "사용자가 같은 사유로 또 거부할 가능성이 있다면 verdict를 REQUEST_CHANGES로, "
        "concerns 항목에 구체적으로 명시하세요."
    )
    return header + body + footer


# ── 셀프 테스트 ──
if __name__ == "__main__":
    import sys
    title = sys.argv[1] if len(sys.argv) > 1 else "[unity] UIShop ShopListItem 리소스 교체"
    desc = sys.argv[2] if len(sys.argv) > 2 else "ShopListItem prefab 이미지 리소스 교체"
    print(build_retrieval_block(title, desc) or "(empty)")
