"""newplay_kb.py — webstore 코드 지식베이스 검색 (qdrant-newteam :6343).

에이전트가 추측 대신 실제 코드를 보고 답하게 하는 그라운딩 경로다.
게임팀은 Atlas $vectorSearch 를 쓰지만 NewPlay 의 Mongo 는 로컬 커뮤니티 서버라
$vectorSearch 가 없어 Qdrant 가 유일한 선택지다.

컬렉션과 임베딩 제공자는 env 로 고른다 (질의 임베딩은 **색인 때 쓴 것과 같은 모델**이어야 한다):
    NEWPLAY_EMBED_PROVIDER=ollama   NEWPLAY_EMBED_MODEL=bge-m3   NEWPLAY_OLLAMA_URL=http://127.0.0.1:11434
        → 컬렉션 newplay_code_m3 (1024차원). 외부 API 없음. 이 PC 안에서 끝난다.  ← 기본
    NEWPLAY_EMBED_PROVIDER=openai   NEWPLAY_EMBED_MODEL=text-embedding-3-small
        → 컬렉션 newplay_code (1536차원). OPENAI_API_KEY 필요. 예전 방식.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import requests

log = logging.getLogger("newplay-kb")

QDRANT_URL = os.environ.get("NEWPLAY_QDRANT_URL", "http://127.0.0.1:6343")
EMBED_PROVIDER = os.environ.get("NEWPLAY_EMBED_PROVIDER", "ollama").lower()
EMBED_MODEL = os.environ.get("NEWPLAY_EMBED_MODEL",
                             "bge-m3" if EMBED_PROVIDER == "ollama" else "text-embedding-3-small")
OLLAMA_URL = os.environ.get("NEWPLAY_OLLAMA_URL", "http://127.0.0.1:11434")
COLLECTION = os.environ.get("NEWPLAY_KB_COLLECTION",
                            "newplay_code_m3" if EMBED_PROVIDER == "ollama" else "newplay_code")


def _embed(text: str) -> Optional[list[float]]:
    try:
        if EMBED_PROVIDER == "ollama":
            # 2,000자 상한 — 컨텍스트(4096 토큰) 초과 시 400 + 서버 재시작(실측). 질의는 어차피 짧다.
            r = requests.post(f"{OLLAMA_URL}/api/embeddings",
                              json={"model": EMBED_MODEL, "prompt": text[:2000]}, timeout=60)
            r.raise_for_status()
            return r.json().get("embedding") or None
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            log.warning("OPENAI_API_KEY 없음 — KB 검색 불가")
            return None
        r = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": EMBED_MODEL, "input": text[:8000]},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except Exception as e:  # noqa: BLE001
        log.warning("임베딩 실패(%s/%s): %s: %s", EMBED_PROVIDER, EMBED_MODEL, type(e).__name__, e)
        return None


def search(query: str, top: int = 6, area: str = "", kind: str = "") -> list[dict[str, Any]]:
    """의미 검색. 실패하면 빈 리스트 — 그라운딩이 없다고 태스크를 죽이지는 않는다."""
    vec = _embed(query)
    if not vec:
        return []
    must = []
    if area:
        must.append({"key": "area", "match": {"value": area}})
    if kind:
        must.append({"key": "kind", "match": {"value": kind}})
    body: dict[str, Any] = {"vector": vec, "limit": top, "with_payload": True}
    if must:
        body["filter"] = {"must": must}
    try:
        r = requests.post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/search",
            json=body, timeout=30,
        )
        r.raise_for_status()
        return r.json().get("result", []) or []
    except Exception as e:  # noqa: BLE001
        log.warning("KB 검색 실패: %s: %s", type(e).__name__, e)
        return []


def paths(query: str, top: int = 6, area: str = "", kind: str = "") -> list[str]:
    """검색 결과의 파일 경로만 중복 없이 돌려준다.

    미러 표면 조회가 "무엇이 검색됐나"를 알아야 해서 만든 얇은 래퍼다.
    as_prompt_block 은 프롬프트 문자열만 주므로 경로를 되뽑을 수 없다.
    """
    seen: list[str] = []
    try:
        for h in search(query, top=top, area=area, kind=kind):
            p = (h.get("payload") or {}).get("path")
            if p and p not in seen:
                seen.append(str(p))
    except Exception:  # noqa: BLE001
        return []
    return seen


def as_prompt_block(query: str, top: int = 6, area: str = "", kind: str = "") -> str:
    """검색 결과를 프롬프트에 넣을 수 있는 형태로. 결과가 없으면 빈 문자열."""
    hits = search(query, top=top, area=area, kind=kind)
    if not hits:
        return ""
    lines = ["## 관련 코드 (webstore 지식베이스에서 검색된 실제 코드)",
             "아래는 추측이 아니라 레포에 실재하는 코드다. 답할 때 이것을 근거로 삼고,",
             "여기에 없는 동작을 있다고 단정하지 마라.", ""]
    for h in hits:
        p = h.get("payload") or {}
        lines.append(f"### {p.get('path')}:{p.get('startLine')}-{p.get('endLine')}  ({p.get('kind')}/{p.get('area')}, score {h.get('score', 0):.3f})")
        body = str(p.get("text") or "")
        # text 앞 2줄은 우리가 붙인 헤더라 본문만 남긴다
        parts = body.split("\n", 2)
        lines.append("```" + str(p.get("lang") or ""))
        lines.append((parts[2] if len(parts) > 2 else body)[:1800])
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def health() -> dict[str, Any]:
    try:
        r = requests.get(f"{QDRANT_URL}/collections/{COLLECTION}", timeout=10)
        r.raise_for_status()
        res = r.json()["result"]
        return {"ok": True, "points": res.get("points_count"),
                "dim": res["config"]["params"]["vectors"]["size"]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
