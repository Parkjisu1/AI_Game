"""
DNA 1-hop 그라운딩 — balloonflow-graph.json(실제 코드 추출)에서 task가 언급한 클래스의
1-hop 서브그래프(의존/피의존 이웃)를 coder/lead 프롬프트에 주입.
정적·존재만 보장(의미검증 아님). 실패 시 항상 '' 반환(비치명). HERMES_GROUNDING on 일 때만 호출.
join 키 = code_base.fileId ↔ graph node.cls (P-1 CONFIRM-C: 95% 커버리지).
"""
from __future__ import annotations
import json
import logging
import os
import re

log = logging.getLogger("bf-graph-context")
_CACHE: dict = {"mtime": 0.0, "graph": None}
GRAPH_PATH = os.environ.get("HERMES_GRAPH_PATH", "/home/aimed/projecthub-web/public/balloonflow-graph.json")


def _load():
    try:
        st = os.stat(GRAPH_PATH)
        if _CACHE["graph"] is not None and _CACHE["mtime"] == st.st_mtime:
            return _CACHE["graph"]
        with open(GRAPH_PATH, encoding="utf-8") as f:
            g = json.load(f)
        _CACHE.update(mtime=st.st_mtime, graph=g)
        return g
    except Exception:
        return None


def build_graph_context(title: str, description: str, max_anchors: int = 3, max_neighbors: int = 8) -> str:
    """task 텍스트에 등장하는 클래스를 앵커로 1-hop 서브그래프 마크다운 블록 반환(~1.8KB cap)."""
    try:
        g = _load()
        if not g or not g.get("nodes"):
            return ""
        nodes = g["nodes"]
        edges = g.get("edges", [])
        text = f"{title} {description}".lower()
        cand = [n for n in nodes if n.get("cls") and len(n["cls"]) >= 4
                and re.search(r"\b" + re.escape(n["cls"].lower()) + r"\b", text)]
        cand.sort(key=lambda n: n.get("refsIn", 0), reverse=True)
        anchors = cand[:max_anchors]
        if not anchors:
            return ""
        by_id = {n["id"]: n for n in nodes}
        lines = ["", "## 🧬 DNA 1-hop (실제 코드 구조 — 정적·존재만 보장, 의미·런타임 검증 아님)"]
        for a in anchors:
            aid = a["id"]
            outs: list[str] = []
            ins: list[str] = []
            for e in edges:
                if e.get("from") == aid and by_id.get(e.get("to")):
                    outs.append(by_id[e["to"]]["cls"])
                elif e.get("to") == aid and by_id.get(e.get("from")):
                    ins.append(by_id[e["from"]]["cls"])
            outs = list(dict.fromkeys(outs))[:max_neighbors]
            ins = list(dict.fromkeys(ins))[:max_neighbors]
            lines.append(f"- **{a['cls']}** [{a.get('system', '')}] (피참조 {a.get('refsIn', 0)})")
            if outs:
                lines.append(f"  - 의존→: {', '.join(outs)}")
            if ins:
                lines.append(f"  - 피의존←: {', '.join(ins)}")
        return ("\n".join(lines))[:1800] + "\n"
    except Exception:
        log.debug("build_graph_context failed", exc_info=True)
        return ""
