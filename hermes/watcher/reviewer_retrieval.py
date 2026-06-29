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
        overturned = S.count_documents({"role": reviewer_role, "verdict": "user_rejected_after_approval"})
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
