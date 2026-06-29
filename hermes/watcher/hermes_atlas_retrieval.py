"""
hermes_atlas_retrieval.py — 생성(Generation) 단계 RAG.

검증된 코드(code_base) + 프로젝트 기획 디렉션(design_base) + 유사 과거 task(pixelforge_tasks)를
Atlas Vector Search 로 검색해 **Lead / Main Coder / Designer / Writer 프롬프트에 주입**한다.

배경:
  - 기존엔 code_base / design_base 임베딩을 생성 단계에서 아무도 안 썼다 (휴면 자산).
  - 유사 세션/유사 코드 RAG 는 Qdrant(hermes_embedding_client) 기반이었으나 Qdrant 미가동 → 사실상 죽음.
  - 모든 임베딩이 Atlas 에 있으므로 **단일 저장소(Atlas)로 통일**하고 생성에 연결한다.

검색 대상 / 방식:
  - code_base       : Atlas $vectorSearch (index=vector_index, READY)        → 유사 검증 코드
  - pixelforge_tasks: Atlas $vectorSearch (index=vector_index, READY)        → 유사 과거 task (Qdrant 세션 대체)
  - design_base     : 벡터 인덱스 없음(M0 한도) → 토큰 오버랩 키워드 랭킹     → 관련 기획 디렉션

장애 대응: OpenAI/Atlas 실패 시 모든 함수가 빈 문자열/빈 리스트 반환 → 프롬프트 영향 0 (non-fatal).
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from typing import Any

log = logging.getLogger("atlas-retrieval")

EMBED_MODEL = "text-embedding-3-small"
CODE_SIM_FLOOR = 0.50
TASK_SIM_FLOOR = 0.62
MAX_SUMMARY_CHARS = 240

# 한/영 불용어 — 디자인 키워드 랭킹 노이즈 제거
_STOP = {
    "the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "수정", "추가", "변경",
    "구현", "적용", "작업", "관련", "기능", "처리", "확인", "버그", "fix", "unity", "balloonflow",
    "레벨", "기획", "디렉션", "명세", "task", "그리고", "해야", "하기", "되도록",
}


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


def _vector_search(coll_name: str, qvec: list[float], k: int) -> list[dict]:
    db = _mongo_db()
    if db is None:
        return []
    pipe = [
        {"$vectorSearch": {
            "index": "vector_index", "path": "embedding",
            "queryVector": qvec, "numCandidates": k * 10, "limit": k,
        }},
        {"$addFields": {"_score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"embedding": 0}},  # 1536-d 배열 회수 방지
    ]
    try:
        return list(db[coll_name].aggregate(pipe))
    except Exception as e:
        log.warning("%s vector search failed: %s", coll_name, e)
        return []


# ─────────────────────────── code_base ───────────────────────────

def build_code_context(title: str, description: str, k: int = 4) -> str:
    """유사 검증 코드(code_base) 블록 — Main Coder/Lead 프롬프트용."""
    query = f"{title}\n{description or ''}".strip()[:2000]
    qvec = _embed(query)
    if qvec is None:
        return ""
    rows = [r for r in _vector_search("code_base", qvec, k + 4) if r.get("_score", 0) >= CODE_SIM_FLOOR][:k]
    if not rows:
        return ""

    lines = []
    for r in rows:
        classes = r.get("classes") or []
        cls = (classes[0].get("className") if classes and isinstance(classes[0], dict) else "") or r.get("fileId") or "?"
        base = classes[0].get("baseClass") if classes and isinstance(classes[0], dict) else ""
        provides = ", ".join((r.get("provides") or [])[:6])[:400]
        uses = ", ".join((r.get("uses") or [])[:8])[:240]
        lines.append(
            f"- **{cls}**{f' : {base}' if base else ''} [{r.get('_score',0):.2f}] "
            f"(layer={r.get('layer','?')} / role={r.get('role','?')} / system={r.get('system','?')})\n"
            f"  - file: `{r.get('filePath', r.get('fileId',''))}`"
            + (f"\n  - provides: {provides}" if provides else "")
            + (f"\n  - uses: {uses}" if uses else "")
        )

    return (
        "\n## 🔎 유사 검증 코드 (code_base Vector Search)\n"
        "이 task와 유사한 **이미 검증된 BalloonFlow 코드**입니다. 새로 짜기 전에 이 패턴/계약을 우선 재사용하고, "
        "동일 시스템이면 기존 클래스를 수정하세요(중복 생성 금지). 환각 방지: 아래 file 경로가 실제 존재하는지 전제로 참조.\n"
        + "\n".join(lines) + "\n"
    )


# ─────────────────────────── pixelforge_tasks (유사 세션, Qdrant 대체) ───────────────────────────

def build_similar_tasks_block(title: str, description: str, k: int = 4, exclude_id: str = "") -> str:
    """유사 과거 task(pixelforge_tasks) 블록 — 기존 Qdrant format_similar_sessions_section 대체."""
    query = f"{title}\n{description or ''}".strip()[:2000]
    qvec = _embed(query)
    if qvec is None:
        return ""
    rows = _vector_search("pixelforge_tasks", qvec, k + 12)  # good 필터 보정 위해 넓게
    # 결과가 좋았던 작업만 참조 (best_score = reviewer max). 검증된 우수 사례만 RAG 주입.
    GOOD = 80.0
    rows = [r for r in rows
            if str(r.get("_id")) != exclude_id
            and r.get("_score", 0) >= TASK_SIM_FLOOR
            and float(r.get("best_score") or 0) >= GOOD][:k]
    if not rows:
        return ""

    lines = []
    for r in rows:
        comments = r.get("comments") or []
        user = [c for c in comments if isinstance(c, dict) and c.get("author") != "hermes"]
        last_user = ""
        if user:
            t = user[-1].get("text") or user[-1].get("content") or user[-1].get("body") or ""
            last_user = " ".join(t.split())[:180]
        line = f"- [{r.get('_score',0):.2f}] {(r.get('title') or '').strip()} (status={r.get('status','?')})"
        if last_user:
            line += f"\n  - 🗣️ 사용자 지적: \"{last_user}\""
        lines.append(line)

    return (
        "\n## 📚 유사 과거 task (Atlas Vector Search)\n"
        "과거 유사 작업과 사용자가 남긴 지적입니다. 같은 함정을 피하도록 계획에 반영하세요.\n"
        + "\n".join(lines) + "\n"
    )


# ─────────────────────────── design_base (키워드 랭킹, 인덱스 없음) ───────────────────────────

def _tokenize(s: str) -> set[str]:
    toks = re.findall(r"[A-Za-z0-9]+|[가-힣]{2,}", (s or "").lower())
    return {t for t in toks if len(t) >= 2 and t not in _STOP}


def build_design_context(title: str, description: str, k: int = 3, project: str = "BalloonFlow") -> str:
    """관련 기획 디렉션(design_base) 블록 — Designer/Writer/Lead 프롬프트용.

    design_base 는 벡터 인덱스가 없어(M0 한도) 토큰 오버랩으로 랭킹한다.
    프로젝트 design_base 가 작아(<100) 전체 fetch 후 in-Python 랭킹이 충분히 빠르다.
    """
    db = _mongo_db()
    if db is None:
        return ""
    q_tokens = _tokenize(f"{title} {description or ''}")
    if not q_tokens:
        return ""
    try:
        docs = list(db.design_base.find(
            {"project": project},
            {"system": 1, "domain": 1, "summary": 1, "tags": 1, "document_role": 1, "headings": 1},
        ))
    except Exception as e:
        log.warning("design_base fetch failed: %s", e)
        return ""
    if not docs:
        return ""

    scored = []
    for d in docs:
        hay = " ".join([
            str(d.get("system", "")), str(d.get("domain", "")), str(d.get("summary", "")),
            " ".join(d.get("tags", []) or []),
            " ".join(h.get("title", "") for h in (d.get("headings") or []) if isinstance(h, dict)),
        ])
        overlap = len(q_tokens & _tokenize(hay))
        if overlap > 0:
            scored.append((overlap, d))
    if not scored:
        return ""
    scored.sort(key=lambda x: x[0], reverse=True)

    lines = []
    for ov, d in scored[:k]:
        summary = (d.get("summary") or "").strip()[:MAX_SUMMARY_CHARS]
        lines.append(
            f"- **{d.get('system','?')}** (domain={d.get('domain','?')}, match={ov})"
            + (f"\n  - {summary}" if summary else "")
        )

    return (
        "\n## 📐 관련 기획 디렉션 (design_base)\n"
        "이 task와 관련된 **프로젝트 기획 디렉션/명세**입니다. 수치·정책·의도는 이 문서를 우선 근거로 삼으세요.\n"
        + "\n".join(lines) + "\n"
    )


# ─────────────────────────── 조합 블록 ───────────────────────────

def build_dev_block(title: str, description: str, exclude_id: str = "") -> str:
    """dev(Unity) 생성용: 유사 코드 + 관련 기획 + 유사 task."""
    parts = [
        build_code_context(title, description),
        build_design_context(title, description),
        build_similar_tasks_block(title, description, exclude_id=exclude_id),
    ]
    return "".join(p for p in parts if p)


def build_design_block(title: str, description: str) -> str:
    """design/content 생성용: 관련 기획 디렉션 + 유사 task."""
    parts = [
        build_design_context(title, description, k=4),
        build_similar_tasks_block(title, description, k=3),
    ]
    return "".join(p for p in parts if p)


# ── 셀프 테스트 ──
if __name__ == "__main__":
    import sys
    t = sys.argv[1] if len(sys.argv) > 1 else "[unity] 상점 상품 단계별 노출 적용"
    d = sys.argv[2] if len(sys.argv) > 2 else "UIShop 에서 상품을 단계별로 노출하도록 수정"
    print("===== DEV BLOCK =====")
    print(build_dev_block(t, d) or "(empty)")
    print("\n===== DESIGN BLOCK =====")
    print(build_design_block(t, d) or "(empty)")
