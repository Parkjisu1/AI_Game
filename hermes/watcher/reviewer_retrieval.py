"""
Reviewer Retrieval — 유사 과거 task의 cycle history + user 거부 사유를 Reviewer 프롬프트에 주입.

전략 (2-stage):
  1) Qdrant `reviewer_tasks_m3`(bge-m3 1024d) 유사도 검색 → 유사 task top-k
  2) 각 task의 hermes_team_scores 조회 → cycle 길이, user_reject 횟수, AI summary chain
  3) 사용자가 무엇을 요청/거부했는지 + AI가 무엇을 놓쳤는지 정리

목적: user_rejected_after_approval 29건 같은 패턴 — AI Reviewer가 OK 줬지만 사용자가
거부한 영역 — 의 구체적 사유를 다음 review에 컨텍스트로 제공.

2026-10-13 — Mongo `$vectorSearch`(pixelforge_tasks, OpenAI 1536d) → Qdrant 이전.
  Mother 의 MONGODB_URI 는 Atlas 가 아니라 임베딩컴 로컬 mongod 라 `$vectorSearch` 가 항상 실패했고,
  OpenAI 키도 401 이라 그 앞의 질의 임베딩부터 죽어 **조용히 빈 문자열**을 반환하고 있었다.
  → 임베딩은 hermes_embedding_client(Ollama bge-m3, 한국어 판별 가능)를 쓰고,
    검색 대상은 "리뷰 점수 기록(hermes_team_scores)이 있는 task" 만 별도 컬렉션에 증분 색인한다.
    (기존 hermes_text_memory_m3 는 점수 있는 task 135건 중 30건만 담고 있어 대체 불가 — 실측)
  색인은 build_retrieval_block 호출 시 SYNC_INTERVAL_SEC 마다 델타만 갱신한다(제목+설명 해시 비교).

장애 대응: 실패해도 빈 문자열 반환(비치명) — 대신 WARNING 로그(사유별 WARN_INTERVAL_SEC 당 1회) +
  hermes_retrieval_health 컬렉션에 ok/empty/fail 카운터와 마지막 사유를 남긴다(조용한 사망 방지).
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
import uuid
from functools import lru_cache
from typing import Any

log = logging.getLogger("reviewer-retrieval")

# bge-m3 코사인 기준. 2026-10-13 실측으로 보정(본문 test 참조) — env 로 조정 가능.
TASK_SIMILARITY_FLOOR = float(os.environ.get("HERMES_REVIEWER_SIM_FLOOR", "0.55"))
TASK_COLLECTION = os.environ.get("HERMES_REVIEWER_TASK_COLLECTION", "reviewer_tasks_m3")
SYNC_INTERVAL_SEC = int(os.environ.get("HERMES_REVIEWER_SYNC_INTERVAL_SEC", "600"))
SYNC_MAX_EMBED = int(os.environ.get("HERMES_REVIEWER_SYNC_MAX_EMBED", "40"))
WARN_INTERVAL_SEC = int(os.environ.get("HERMES_RETRIEVAL_WARN_INTERVAL_SEC", "600"))
_POINT_NS = uuid.UUID("5b0c7a8e-1f0e-4b7e-9d1a-7e6a2f3c9b10")
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


# ─────────────────────────── 관측 (조용한 사망 방지) ───────────────────────────

RETRIEVAL_STATS: dict[str, Any] = {"ok": 0, "empty": 0, "fail": 0, "last_status": "", "last_reason": ""}
_last_warn: dict[str, float] = {}
_stats_lock = threading.Lock()


def _note(status: str, stage: str = "", reason: str = "") -> None:
    """검색 결과를 카운트하고 hermes_retrieval_health 에 남긴다. fail 이면 사유별 주기당 1회 WARNING."""
    with _stats_lock:
        RETRIEVAL_STATS[status] = RETRIEVAL_STATS.get(status, 0) + 1
        RETRIEVAL_STATS["last_status"] = status
        RETRIEVAL_STATS["last_reason"] = f"{stage}: {reason}" if stage else reason
        warn = False
        if status == "fail":
            now = time.monotonic()
            if now - _last_warn.get(stage, -1e9) >= WARN_INTERVAL_SEC:
                _last_warn[stage] = now
                warn = True
    if warn:
        log.warning("reviewer retrieval FAILED at %s — %s (빈 컨텍스트로 진행; 누적 fail=%d, %ds 동안 같은 사유 경고 생략)",
                    stage, reason, RETRIEVAL_STATS["fail"], WARN_INTERVAL_SEC)
    elif status == "fail":
        log.debug("reviewer retrieval failed at %s — %s", stage, reason)
    db = _mongo_db()
    if db is None:
        return
    try:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        st = {"last_status": status, "last_reason": RETRIEVAL_STATS["last_reason"][:300], "updated_at": now_iso}
        if status == "ok":
            st["last_ok_at"] = now_iso
        elif status == "fail":
            st["last_fail_at"] = now_iso
        db.hermes_retrieval_health.update_one(
            {"_id": "reviewer_retrieval"},
            {"$inc": {status: 1}, "$set": st},
            upsert=True)
    except Exception:
        log.debug("retrieval health upsert failed", exc_info=True)


def retrieval_health() -> dict:
    """프로세스 내 카운터 스냅샷 (ok/empty/fail/last_*)."""
    with _stats_lock:
        return dict(RETRIEVAL_STATS)


# ─────────────────────────── Qdrant 색인/검색 ───────────────────────────

def _ec():
    import hermes_embedding_client as ec
    return ec


def _task_text(doc: dict) -> str:
    # build_retrieval_block 의 질의와 같은 형태(제목\n설명)로 색인한다.
    return f"{doc.get('title') or ''}\n{doc.get('description') or ''}".strip()[:2000]


_sync_lock = threading.Lock()
_last_sync = 0.0


def sync_task_index(force: bool = False, max_embed: int | None = None) -> dict:
    """점수 기록이 있는 pixelforge_tasks 를 Qdrant TASK_COLLECTION 에 델타 색인.

    - 대상: hermes_team_scores.distinct(task_id) ∩ pixelforge_tasks (리뷰 이력이 있어야 블록에 쓸모가 있다)
    - 제목+설명 sha1 이 payload.h 와 같으면 스킵, 다르거나 없으면 bge-m3 임베딩 후 upsert
    - SYNC_INTERVAL_SEC 마다 1회(force 면 즉시). 실패는 예외로 올리고 호출측이 _note 한다.
    반환: {"candidates", "indexed", "embedded", "skipped"}
    """
    global _last_sync
    if not force and time.monotonic() - _last_sync < SYNC_INTERVAL_SEC:
        return {"skipped": True}
    if not _sync_lock.acquire(blocking=False):
        return {"skipped": True}
    try:
        _last_sync = time.monotonic()
        db = _mongo_db()
        if db is None:
            raise RuntimeError("mongo unavailable (MONGODB_URI 없음)")
        ec = _ec()
        client = ec._get_qdrant()
        if client is None:
            raise RuntimeError("qdrant client init failed")
        from qdrant_client.http.models import Distance, PointStruct, VectorParams
        if not client.collection_exists(TASK_COLLECTION):
            client.create_collection(TASK_COLLECTION,
                                     vectors_config=VectorParams(size=ec.EMBEDDING_DIM, distance=Distance.COSINE))
            log.info("created qdrant collection %s", TASK_COLLECTION)

        from bson import ObjectId
        ids = []
        for t in db.hermes_team_scores.distinct("task_id"):
            try:
                ids.append(ObjectId(str(t)))
            except Exception:
                continue
        docs = list(db.pixelforge_tasks.find(
            {"_id": {"$in": ids}}, {"title": 1, "description": 1, "team": 1, "sub_team": 1}))

        have: dict[str, str] = {}
        offset = None
        while True:
            pts, offset = client.scroll(TASK_COLLECTION, limit=512, offset=offset,
                                        with_payload=["task_id", "h"], with_vectors=False)
            for p in pts:
                pl = p.payload or {}
                have[str(pl.get("task_id"))] = str(pl.get("h") or "")
            if offset is None:
                break

        cap = SYNC_MAX_EMBED if max_embed is None else max_embed
        embedded = 0
        batch: list = []
        for d in docs:
            if embedded >= cap:
                break
            tid = str(d["_id"])
            text = _task_text(d)
            if len(text) < 5:
                continue
            h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
            if have.get(tid) == h:
                continue
            vec = ec._embed(text)
            if vec is None:
                raise RuntimeError(f"embed failed ({ec.EMBEDDING_MODEL} @ {ec.OLLAMA_URL})")
            batch.append(PointStruct(
                id=str(uuid.uuid5(_POINT_NS, tid)), vector=vec,
                payload={"task_id": tid, "title": (d.get("title") or "")[:200], "h": h,
                         "team": d.get("team"), "sub_team": d.get("sub_team")}))
            embedded += 1
            if len(batch) >= 32:
                client.upsert(TASK_COLLECTION, points=batch)
                batch = []
        if batch:
            client.upsert(TASK_COLLECTION, points=batch)
        if embedded:
            log.info("reviewer task index: +%d embedded (candidates=%d, %s)", embedded, len(docs), TASK_COLLECTION)
        return {"candidates": len(docs), "indexed": len(have), "embedded": embedded}
    finally:
        _sync_lock.release()


def _qdrant_task_search(query: str, k: int, exclude_id: str = "") -> list[dict]:
    """Qdrant 유사 task 검색 → pixelforge_tasks 문서(+_score). 예전 _vector_task_search 와 같은 행 모양.
    실패는 예외로 올린다(호출측이 사유를 기록)."""
    ec = _ec()
    qvec = ec._embed(query)
    if qvec is None:
        raise RuntimeError(f"query embed failed ({ec.EMBEDDING_MODEL} @ {ec.OLLAMA_URL})")
    client = ec._get_qdrant()
    if client is None:
        raise RuntimeError("qdrant client init failed")
    res = client.query_points(collection_name=TASK_COLLECTION, query=qvec, limit=k + 5, with_payload=True)
    hits = [(str((h.payload or {}).get("task_id")), float(h.score)) for h in res.points]
    hits = [(tid, s) for tid, s in hits if tid and tid != exclude_id]
    if not hits:
        return []
    db = _mongo_db()
    if db is None:
        raise RuntimeError("mongo unavailable (MONGODB_URI 없음)")
    from bson import ObjectId
    oids = []
    for tid, _ in hits:
        try:
            oids.append(ObjectId(tid))
        except Exception:
            pass
    by_id = {str(d["_id"]): d for d in db.pixelforge_tasks.find(
        {"_id": {"$in": oids}},
        {"title": 1, "team": 1, "sub_team": 1, "status": 1, "comments": 1})}
    rows = []
    for tid, s in hits:
        d = by_id.get(tid)
        if d is None:  # 삭제/아카이브된 task
            continue
        d["_score"] = s
        rows.append(d)
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
    if len(query) < 5:
        return ""
    try:
        sync_task_index()
    except Exception as e:  # 색인 갱신 실패는 기존 색인으로 검색은 계속한다
        _note("fail", "index_sync", f"{type(e).__name__}: {e}")
    try:
        tasks = _qdrant_task_search(query, k=4, exclude_id=current_task_id)
    except Exception as e:
        _note("fail", "search", f"{type(e).__name__}: {e}")
        return ""
    tasks = [t for t in tasks if t.get("_score", 0) >= TASK_SIMILARITY_FLOOR]
    if not tasks:
        _note("empty", "search", f"no hit >= {TASK_SIMILARITY_FLOOR}")
        return ""
    _note("ok", "search", f"{len(tasks)} hits")

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

    header = "## 📚 유사 과거 task 검토 (Qdrant retrieval)\n"
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
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "--sync":  # 초기 백필: python reviewer_retrieval.py --sync
        print(sync_task_index(force=True, max_embed=100000))
        sys.exit(0)
    title = sys.argv[1] if len(sys.argv) > 1 else "[unity] UIShop ShopListItem 리소스 교체"
    desc = sys.argv[2] if len(sys.argv) > 2 else "ShopListItem prefab 이미지 리소스 교체"
    print(build_retrieval_block(title, desc) or "(empty)")
    print(retrieval_health())
