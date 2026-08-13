"""
DNA 1-hop 그라운딩 — balloonflow-graph.json(실제 코드 추출)에서 관련 클래스의
1-hop 서브그래프(의존/피의존 이웃) + 노출 메서드를 coder/lead 프롬프트에 주입.
정적·존재만 보장(의미검증 아님). 실패 시 항상 '' 반환(비치명). HERMES_GROUNDING on 일 때만 호출.
join 키 = code_base.fileId ↔ graph node.cls (P-1 CONFIRM-C: 95% 커버리지).

2026-07-20 개편 — 회귀(기존 코드 삭제) 방지를 목표로 두 가지를 고침:

  (1) 앵커 소스 확대.
      이전에는 앵커를 **task 제목/본문의 클래스명 정규식 매칭**으로만 잡았다.
      그래서 "레벨 클리어가 안 됨" 처럼 클래스명이 안 적힌 현상 기반 task는
      그라운딩을 **한 줄도 못 받았다**(anchors 비면 '' 반환).
      → RAG 벡터검색이 이미 찾아둔 유사 코드(code_base)의 클래스를 extra_anchors 로 받는다.
        이게 "곧 수정될 파일"에 대한 가장 좋은 사전 신호다.

  (2) 노출 메서드 주입.
      graph.json 에 클래스별 methods[] 가 이미 추출돼 있는데(전체 3,399개) 쓰지 않았다.
      이웃 클래스 '이름'만 알려주는 것으로는 "기존 메서드를 지워버리는" 사고를 막지 못한다.
      → 앵커 클래스의 노출 메서드와 피의존 파일을 함께 주고, 보존 지시를 명시한다.

한계(정직): 정적 추출이라 동적 디스패치는 누락될 수 있고, 메서드 단위 호출자까지는
알 수 없다(엣지는 클래스 단위). 따라서 '삭제 금지 근거'로는 충분하나 '안전 증명'은 아니다.

2026-08-13 수정 — **프로젝트 오주입 차단**:
      그래프는 프로젝트마다 하나씩 생성되는데(balloonflow/crewflowrotation/nextpr)
      이 모듈은 BalloonFlow 경로 **하나만** 읽고 있었다. 세 프로젝트가 같은 Unity
      템플릿 파생이라 클래스명이 대량으로 겹쳐(NextPR 109/174, CrewFlow 179/191)
      앵커가 거의 항상 걸렸고, 그 결과 NextPR 코더가 **BalloonFlow 의 메서드 목록**을
      "실제 코드 구조 · 하나도 없애지 마세요" 라는 문구와 함께 받았다.
      실측: GameManager 는 BF 19메서드 / NextPR 7메서드이고 BF 쪽 19개는 NextPR 에 하나도 없다.
      → task.project 로 그래프를 고른다. 해당 그래프가 없으면 **침묵**한다('').
        잘못된 그라운딩은 없느니만 못하다 — 앵커 기준선(0.65) 때와 같은 원칙.
"""
from __future__ import annotations
import json
import logging
import os
import re

log = logging.getLogger("bf-graph-context")
#: 경로별 캐시 — 프로젝트가 여럿이므로 단일 슬롯이면 서로 밀어낸다. {path: {mtime, graph}}
_CACHE: dict = {}
#: 그래프 산출 디렉터리. bf_graph_refresh.py(graph_projects.PUBLIC_DIR)가 여기에 쓴다.
GRAPH_DIR = os.environ.get("NEWPLAY_GRAPH_PUBLIC", "/home/aimed/projecthub-web/public")
#: project 를 못 받은 레거시 task 용 기본 그래프. hermes_executor 의 DEFAULT_REPO(BalloonFlow)와
#: 짝이 맞아야 한다 — 코드가 실제로 수정되는 레포와 그라운딩이 같은 곳을 가리켜야 하기 때문.
GRAPH_PATH = os.environ.get("HERMES_GRAPH_PATH", os.path.join(GRAPH_DIR, "balloonflow-graph.json"))

MAX_CHARS = int(os.environ.get("HERMES_GRAPH_CTX_CHARS", "4200"))


def _graph_path(project: "str | None") -> "str | None":
    """task.project → 그래프 파일 경로. 없으면 None(=그라운딩 생략)."""
    slug = (project or "").strip().lower()
    if not slug:
        # 레거시 경로: project 미지정 task 는 DEFAULT_REPO(BalloonFlow)로 라우팅되므로
        # 기본 그래프가 곧 그 task 가 손댈 코드다.
        return GRAPH_PATH if os.path.exists(GRAPH_PATH) else None
    p = os.path.join(GRAPH_DIR, f"{slug}-graph.json")
    if os.path.exists(p):
        return p
    log.info("graph grounding skipped — project=%s 그래프 없음 (%s)", slug, p)
    return None


def _load(path: "str | None" = None):
    path = path or GRAPH_PATH
    try:
        st = os.stat(path)
        hit = _CACHE.get(path)
        if hit and hit["mtime"] == st.st_mtime:
            return hit["graph"]
        with open(path, encoding="utf-8") as f:
            g = json.load(f)
        _CACHE[path] = {"mtime": st.st_mtime, "graph": g}
        return g
    except Exception:
        return None


def build_graph_context(
    title: str,
    description: str,
    extra_anchors: "list[str] | None" = None,
    max_anchors: int = 3,
    max_neighbors: int = 8,
    max_methods: int = 14,
    project: "str | None" = None,
) -> str:
    """task 텍스트 + RAG 후보 클래스를 앵커로 1-hop 서브그래프 + 노출 메서드 블록 반환.

    extra_anchors: code_base 벡터검색이 뽑은 클래스명(=fileId). 텍스트 매칭보다 우선한다.
    project: task.project 슬러그. 이 프로젝트의 그래프만 읽는다(오주입 차단).
             그래프가 없으면 '' — 다른 프로젝트 구조를 대신 주지 않는다.
    """
    try:
        path = _graph_path(project)
        if not path:
            return ""
        g = _load(path)
        if not g or not g.get("nodes"):
            return ""
        nodes = g["nodes"]
        edges = g.get("edges", [])
        by_cls = {n["cls"]: n for n in nodes if n.get("cls")}

        # ── 앵커 수집: RAG 후보 우선 → 텍스트 매칭 보충 ──────────────────────
        picked: list[dict] = []
        seen: set = set()
        for c in (extra_anchors or []):
            n = by_cls.get(c)
            if n and n["cls"] not in seen:
                seen.add(n["cls"]); picked.append(n)

        text = f"{title} {description or ''}".lower()
        text_hits = [n for n in nodes
                     if n.get("cls") and len(n["cls"]) >= 4 and n["cls"] not in seen
                     and re.search(r"\b" + re.escape(n["cls"].lower()) + r"\b", text)]
        text_hits.sort(key=lambda n: n.get("refsIn", 0), reverse=True)
        for n in text_hits:
            seen.add(n["cls"]); picked.append(n)

        anchors = picked[:max_anchors]
        if not anchors:
            return ""

        by_id = {n["id"]: n for n in nodes}
        # 어느 프로젝트의 구조인지 본문에 박아 둔다 — 클래스명이 프로젝트 간에 대량으로
        # 겹치므로(GameManager/TitleController…), 출처가 안 보이면 오주입을 눈으로도 못 잡는다.
        src = os.path.basename(path).replace("-graph.json", "")
        lines = [
            "",
            f"## 🧬 DNA 1-hop — 실제 코드 구조 · `{src}` (정적 추출·존재만 보장, 의미/런타임 검증 아님)",
            f"아래는 이번 작업과 관련된 **`{src}` 프로젝트 실존 클래스의 연결과 노출 메서드**입니다. "
            "다른 프로젝트의 동명 클래스가 아닙니다.",
            "**보존 규칙**: 작업 지시에 '삭제/제거'가 명시되지 않았다면 아래 메서드를 하나도 없애지 마세요. "
            "시그니처를 바꿔야 하면 `피의존←`에 적힌 파일의 호출처를 **전부 같이** 수정하세요.",
        ]
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
            methods = [m for m in (a.get("methods") or []) if m][:max_methods]
            n_all = len(a.get("methods") or [])

            lines.append(f"- **{a['cls']}** [{a.get('system', '')}] "
                         f"(`{a.get('file', '')}`, 피참조 {a.get('refsIn', 0)})")
            if methods:
                more = f" …외 {n_all - len(methods)}개" if n_all > len(methods) else ""
                lines.append(f"  - 노출 메서드: {', '.join(methods)}{more}")
            if ins:
                lines.append(f"  - 피의존←(이 클래스를 쓰는 쪽): {', '.join(ins)}")
            if outs:
                lines.append(f"  - 의존→(이 클래스가 쓰는 쪽): {', '.join(outs)}")

        return ("\n".join(lines))[:MAX_CHARS] + "\n"
    except Exception:
        log.debug("build_graph_context failed", exc_info=True)
        return ""
