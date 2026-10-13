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
        # 3000ms는 Atlas 콜드 커넥션에 짧다 — 프로세스 기동 후 첫 호출이 server selection
        # 타임아웃으로 실패하면 _vector_search 가 경고만 남기고 []를 반환해
        # **해당 task는 RAG 컨텍스트를 통째로 못 받는다**(조용한 품질 저하).
        # lru_cache 로 클라이언트는 프로세스당 1회만 만들어지므로 여유를 줘도 상시 비용은 없다.
        _sel_ms = int(os.environ.get("HERMES_MONGO_SELECT_TIMEOUT_MS", "10000"))
        return MongoClient(uri, serverSelectionTimeoutMS=_sel_ms)[os.environ.get("MONGODB_DB", "aigame")]
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

# 그래프 앵커 전용 기준선 — 일반 RAG(CODE_SIM_FLOOR)보다 높게 잡는다.
# 앵커는 "네가 지금 건드릴 코드다"라고 코더에게 선언하는 것이라 오탐 비용이 크다.
# 2026-07-20 실측: 0.75/0.73 = 명백히 관련, 0.68 = 경계, 0.64 이하 = 무관
#   ("레일이 꽉 찼는데 발사가 안 됨" → 최고 0.636 → PopupLoadingSpinner/LocalizedImage 등 전부 무관).
# 기준선 미달이면 앵커 0개 = 그라운딩 침묵. 잘못된 그라운딩보다 없는 편이 낫다.
GRAPH_ANCHOR_FLOOR = float(os.environ.get("HERMES_GRAPH_ANCHOR_FLOOR", "0.65"))


def code_anchor_classes(title: str, description: str, k: int = 2) -> list[str]:
    """벡터검색이 뽑은 유사 코드의 클래스명 목록 — 그래프 그라운딩 앵커용.

    build_code_context 와 같은 검색을 쓰되 문자열이 아닌 식별자를 돌려준다.
    bf_graph_context 가 "곧 수정될 파일"을 추정하는 신호로 쓴다
    (task 텍스트에 클래스명이 없으면 그라운딩이 0이 되던 문제 보완).
    graph node.cls 와 join 되도록 className > fileId 순으로 고른다.
    """
    try:
        query = f"{title}\n{description or ''}".strip()[:2000]
        # 검색은 아래 _ec.search_similar_code(Qdrant)가 자체 임베딩으로 수행한다.
        # 예전엔 여기서 OpenAI _embed 로 가드했는데, 키가 죽자 401 → 조기 return 이 되어
        # 멀쩡한 Qdrant 검색까지 함께 막혔다. 가드를 제거한다.
        import os as _os
        import hermes_embedding_client as _ec
        hits = _ec.search_similar_code(query, limit=k + 6)
        out: list[str] = []
        for h in hits:
            path = h.get("file") or ""
            stem = _os.path.splitext(_os.path.basename(path))[0]
            if stem and stem not in out:
                out.append(stem)
            if len(out) >= k:
                break
        return out
    except Exception:
        log.debug("code_anchor_classes failed", exc_info=True)
        return []


def build_code_context(title: str, description: str, k: int = 4, project: str | None = None) -> str:
    """유사 검증 코드(code_base) 블록 — Main Coder/Lead 프롬프트용. project 가 있으면 같은 프로젝트 우선."""
    query = f"{title}\n{description or ''}".strip()[:2000]
    # Qdrant(gf_code_chunks, nomic 768d) 기반 — Atlas $vectorSearch 는 로컬 mongo 에서 죽음.
    try:
        import hermes_embedding_client as _ec
        hits = _ec.search_similar_code(query, limit=k, project=project)
    except Exception:
        hits = []
    if not hits:
        return ""
    lines = []
    for h in hits:
        path = h.get("file") or "?"
        proj = h.get("project") or "?"
        prev = " ".join((h.get("preview") or "").split())[:200]
        _same = (project and str(proj).lower() == str(project).lower())
        _tag = "같은 프로젝트 — 그대로 재사용" if _same else ("타 프로젝트 — 패턴 참고만, 경로·네임스페이스 복사 금지" if project else "")
        lines.append(
            f"- `{path}` [{h.get('score',0):.2f}] (project={proj}, lang={h.get('lang','?')}{', ' + _tag if _tag else ''})\n"
            f"  - {prev}"
        )
    return (
        "\n## 🔎 유사 검증 코드 (Qdrant gf_code_chunks)\n"
        "이 task와 유사한 **이미 검증된 실제 코드**입니다. 새로 짜기 전에 이 패턴을 우선 재사용하고, "
        "동일 시스템이면 기존 클래스를 수정하세요(중복 생성 금지).\n"
        + "\n".join(lines) + "\n"
    )


# ─────────────────────────── pixelforge_tasks (유사 세션, Qdrant 대체) ───────────────────────────

def build_similar_tasks_block(title: str, description: str, k: int = 4, exclude_id: str = "") -> str:
    """유사 과거 task(pixelforge_tasks) 블록 — 기존 Qdrant format_similar_sessions_section 대체."""
    query = f"{title}\n{description or ''}".strip()[:2000]
    # 위와 같은 이유로 OpenAI _embed 가드를 제거한다 — 검색은 Qdrant 가 수행한다.
    try:
        import hermes_embedding_client as _ec
        _sess = _ec.search_similar_sessions(query, limit=k + 12)
    except Exception:
        _sess = []
    # Qdrant hermes_text_memory 기반(과거 세션). Atlas $vectorSearch(pixelforge_tasks) 죽음 대체.
    rows = [{"_id": x.get("task_id"), "_score": x.get("score", 0) * 100.0,
             "title": x.get("task_title"), "status": ("done" if x.get("success") else "review"),
             "best_score": 100.0 if x.get("success") else 0.0,
             "comments": [{"author": "user", "text": x.get("preview") or ""}] if x.get("preview") else []}
            for x in _sess]
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
    BalloonFlow 기준 444건(과거 주석의 "<100" 은 낡음, 2026-07-20 실측) 전체 fetch 후
    in-Python 랭킹. text 포함 총 ~730KB 로 task 당 1회 호출에는 충분히 가볍다.

    2026-07-20 — 랭킹/출력 대상 필드 확대.
      444건 중 395건이 title+text 형태의 청크 문서이고 system/summary/tags/headings 가 없다.
      이전 구현은 이 필드들만 haystack 으로 써서 395건(89%)이 domain 단일 토큰으로만
      랭킹됐고, 설령 뽑혀도 출력이 `**?**` 로 렌더돼 사실상 쓸모가 없었다.
      → haystack 과 출력 모두 title/text 폴백을 추가한다.
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
            {"system": 1, "domain": 1, "summary": 1, "tags": 1, "document_role": 1,
             "headings": 1, "title": 1, "text": 1, "doc_file": 1},
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
            str(d.get("title", "")), str(d.get("text", ""))[:2000],
            " ".join(d.get("tags", []) or []),
            " ".join(h.get("title", "") for h in (d.get("headings") or []) if isinstance(h, dict)),
        ])
        overlap = len(q_tokens & _tokenize(hay))
        if overlap > 0:
            scored.append((overlap, d))
    if not scored:
        return ""
    scored.sort(key=lambda x: x[0], reverse=True)

    # 같은 원본 문서의 여러 청크가 k칸을 잠식하지 않도록 출처 단위로 중복 제거.
    deduped, seen_src = [], set()
    for ov, d in scored:
        src = d.get("doc_file") or d.get("system") or d.get("title") or id(d)
        if src in seen_src:
            continue
        seen_src.add(src)
        deduped.append((ov, d))
        if len(deduped) >= k:
            break

    lines = []
    for ov, d in deduped:
        # 청크 문서는 system/summary 가 없다 — title/doc_file, text 로 폴백.
        label = d.get("system") or d.get("title") or d.get("doc_file") or "?"
        body = ((d.get("summary") or d.get("text") or "")
                .strip().replace("\n", " ")[:MAX_SUMMARY_CHARS])
        lines.append(
            f"- **{label}** (domain={d.get('domain','?')}, match={ov})"
            + (f"\n  - {body}" if body else "")
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
