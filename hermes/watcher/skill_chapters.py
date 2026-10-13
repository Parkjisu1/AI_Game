"""
Skill Chapters — 팀 표준 문서를 '챕터' 단위로 쪼개, 작업에 관련된 것만 프롬프트에 싣는다.

왜 필요한가
  지금까지는 스코프 메모리 파일 전체를 이어붙여 최대 50,000자를 통째로 주입했다.
  문제는 두 가지다:
    1) 비용 — 대부분의 작업은 그중 한두 절만 쓴다.
    2) **희석** — 진짜 지시(작업 요청)가 수만 자의 배경 문서에 묻힌다.
       NewPlay 에서 "티켓 본문이 컨텍스트를 지배한다"고 지적받은 것과 같은 뿌리다.

무엇을 하는가
  - 문서를 헤딩(md) / 최상위 키(yaml) 기준으로 챕터로 나눈다.
  - **목차는 전부 싣는다** — 무엇이 존재하는지는 알아야 인용도 하고 더 열어보기도 한다.
  - **본문은 관련된 것만** 예산 안에서 싣는다. 관련도는 작업 제목·설명과의 어휘 겹침.
  - 안 실린 항목은 목차에 `[ ]`로 남고, 파일 경로를 함께 준다(도구 있는 역할은 직접 열면 된다).

의도적으로 하지 않은 것
  - 임베딩 검색 — 여기선 결정적(deterministic)인 편이 낫다. 같은 입력이면 같은 결과여야
    회귀를 판정할 수 있고, 표준 문서 수십 개 규모에선 어휘 겹침으로 충분하다.
  - 요약 — 표준은 원문 그대로 인용돼야 한다. 요약하면 인용이 거짓이 된다.

끄기:  HERMES_SKILL_CHAPTERS=off  → 호출부가 기존 통째 주입으로 되돌아간다.
예산:  HERMES_STANDARDS_BUDGET (기본 18000자)
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

log = logging.getLogger("skill-chapters")

DEFAULT_BUDGET = int(os.environ.get("HERMES_STANDARDS_BUDGET", "18000"))

#: 고정 주입(pin) 예산. 아래 PIN_PATTERNS 에 해당하는 파일은 관련도와 무관하게 싣는다.
#:
#: 왜 필요한가 — 실측(2026-08-11, puzzle/design 스코프):
#:   스코프 메모리 34개 파일 405KB 중, 기존 50,000자 컷은 **앞 5개만** 남기고 있었다.
#:   로드 순서가 global → _shared → _shared/design(340KB!) → team → roles → projects → MEMORY
#:   라서, 정작 "이 팀이 어떻게 일하는가"를 담은 team.md·conventions.md·roles/*.md·
#:   projects/*.md·MEMORY.md 는 **한 번도 주입된 적이 없었다.** 잘린 게 아니라 도달조차 못 했다.
#:   관련도 선별만 하면 이 파일들은 여전히 밀린다(작업 어휘와 안 겹치니까) — 그래서 따로 고정한다.
PIN_BUDGET = int(os.environ.get("HERMES_STANDARDS_PIN_BUDGET", "12000"))

#: 고정 대상: 정체성·규약 문서. 작업 주제와 무관하게 항상 유효하다.
PIN_PATTERNS = (
    "MEMORY.md",
    "/team.md",
    "/conventions.md",
    "/roles/",
    "/projects/",
    "global/",
)

#: 이보다 작은 챕터는 앞 챕터에 합친다 — 목차만 길어지고 정보는 없는 조각 방지.
MIN_CHAPTER_CHARS = 200
#: 목차는 **파일 단위로 묶는다**. 항목 570개를 한 줄씩 늘어놓으면 목차만 13KB가 되어
#: (실측) 정작 본문보다 자리를 많이 먹는다. 파일당 대표 항목 몇 개만 보인다.
MAX_INDEX_FILES = 60
TITLES_PER_FILE = 6
#: 관련도는 높은데 예산에 밀려 못 실은 항목 — 이건 개별로 보여줘야 찾아볼 수 있다.
MAX_NEARMISS = 12

_MD_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_YAML_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_\-]*)\s*:")
#: 한글/영문/숫자 토큰. 2자 미만은 버린다.
_TOKEN = re.compile(r"[0-9a-z]+|[가-힣]+")

#: 어디에나 나와 점수를 무의미하게 만드는 말들.
_STOPWORDS = {
    "그리고", "하지만", "그래서", "때문에", "위해", "관련", "대한", "있는", "없는", "하는",
    "해줘", "해주세요", "부탁", "확인", "작업", "내용", "부분", "경우", "정도", "다음",
    "the", "and", "for", "with", "that", "this", "from", "into", "task", "please",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if len(t) >= 2 and t not in _STOPWORDS]


# ──────────────────────────────────────────────
# 분할
# ──────────────────────────────────────────────
def _split_by(lines: list[str], is_heading) -> list[tuple[str, list[str]]]:
    """(제목, 줄들) 목록으로 자른다. 첫 헤딩 앞의 내용은 '(머리말)'."""
    out: list[tuple[str, list[str]]] = []
    title, buf = "(머리말)", []
    for line in lines:
        h = is_heading(line)
        if h is not None:
            if buf and "".join(buf).strip():
                out.append((title, buf))
            title, buf = h, [line]
        else:
            buf.append(line)
    if buf and "".join(buf).strip():
        out.append((title, buf))
    return out


def chapters_of(path: str, content: str) -> list[dict[str, Any]]:
    """파일 하나를 챕터 목록으로. 나눌 근거가 없으면 파일 전체가 1개 챕터."""
    lines = content.splitlines(keepends=True)
    lower = path.lower()

    if lower.endswith((".yaml", ".yml")):
        def _h(line: str):
            if line[:1].isspace() or line.lstrip().startswith("#"):
                return None
            m = _YAML_KEY.match(line)
            return m.group(1) if m else None
    else:
        def _h(line: str):
            m = _MD_HEADING.match(line.rstrip("\n"))
            return m.group(2) if m else None

    raw = _split_by(lines, _h)
    if not raw:
        return []

    # 너무 작은 챕터는 앞에 병합 — 원문 순서는 그대로 유지된다.
    merged: list[tuple[str, list[str]]] = []
    for title, buf in raw:
        size = sum(len(x) for x in buf)
        if merged and size < MIN_CHAPTER_CHARS:
            merged[-1][1].extend(buf)
        else:
            merged.append((title, list(buf)))

    result: list[dict[str, Any]] = []
    for i, (title, buf) in enumerate(merged):
        text = "".join(buf).rstrip()
        if not text.strip():
            continue
        result.append({
            "path": path,
            "title": title.strip()[:120],
            "text": text,
            "chars": len(text),
            "order": i,
        })
    return result


def chapters_of_files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """load_scoped_memory 결과 → 전체 챕터 목록 (파일 순서 보존)."""
    out: list[dict[str, Any]] = []
    for fi, f in enumerate(files):
        try:
            for ch in chapters_of(str(f.get("path") or ""), str(f.get("content") or "")):
                ch["file_order"] = fi
                out.append(ch)
        except Exception:
            log.debug("chapter split failed: %s", f.get("path"), exc_info=True)
            # 쪼개기 실패한 파일은 통째로 한 챕터 — 내용이 사라지는 게 최악이다.
            out.append({
                "path": str(f.get("path") or ""), "title": "(전체)",
                "text": str(f.get("content") or ""), "chars": len(str(f.get("content") or "")),
                "order": 0, "file_order": fi,
            })
    return out


# ──────────────────────────────────────────────
# 선별
# ──────────────────────────────────────────────
def score_chapter(ch: dict[str, Any], query_tokens: set[str]) -> int:
    """제목 일치는 3배. 본문은 **서로 다른** 토큰이 몇 개 등장했는지로 센다
    (같은 단어 반복으로 긴 챕터가 이기는 것을 막는다)."""
    if not query_tokens:
        return 0
    title_hits = len(query_tokens & set(_tokens(ch["title"] + " " + ch["path"])))
    body_hits = len(query_tokens & set(_tokens(ch["text"])))
    return title_hits * 3 + body_hits


def is_pinned(path: str) -> bool:
    """정체성·규약 문서인가 — 작업 주제와 무관하게 항상 싣는다."""
    p = path.replace("\\", "/")
    return any(pat in p or p.startswith(pat) for pat in PIN_PATTERNS)


def select(
    chapters: list[dict[str, Any]], query: str, budget_chars: int,
    pin_budget: int = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(실을 것, 안 실을 것).

    두 예산이 따로 돈다:
      - 고정분(pin) — 정체성·규약 문서. 작은 파일부터 채운다(개수를 최대화).
      - 관련분      — 점수 desc, 동점은 원문 순서.
    """
    pin_b = PIN_BUDGET if pin_budget is None else pin_budget
    pinned = [c for c in chapters if is_pinned(c["path"])]
    rest = [c for c in chapters if not is_pinned(c["path"])]

    pin_taken: list[dict[str, Any]] = []
    used_pin = 0
    for ch in sorted(pinned, key=lambda c: (c["chars"], c["file_order"], c["order"])):
        cost = ch["chars"] + 80
        if used_pin + cost > pin_b:
            continue
        ch["pinned"] = True
        pin_taken.append(ch)
        used_pin += cost

    chapters = rest
    qt = set(_tokens(query))
    scored = [(score_chapter(ch, qt), ch) for ch in chapters]

    # 아무것도 안 걸리면(질의가 비었거나 겹치는 어휘가 없음) 원문 순서대로 채운다.
    # 빈 표준을 주는 것보다 앞부분이라도 주는 편이 낫다.
    if not any(s > 0 for s, _ in scored):
        ranked = list(chapters)
    else:
        ranked = [ch for _, ch in sorted(
            scored, key=lambda p: (-p[0], p[1]["file_order"], p[1]["order"]))]

    taken: list[dict[str, Any]] = []
    used = 0
    for ch in ranked:
        # 헤더 오버헤드까지 감안 — 못 넣는 챕터는 건너뛰고 더 작은 걸 계속 본다.
        cost = ch["chars"] + 80
        if used + cost > budget_chars:
            continue
        taken.append(ch)
        used += cost

    taken = pin_taken + taken
    taken_ids = {id(ch) for ch in taken}
    dropped = [ch for ch in (pinned + rest) if id(ch) not in taken_ids]
    taken.sort(key=lambda c: (c["file_order"], c["order"]))
    dropped.sort(key=lambda c: (c["file_order"], c["order"]))
    return taken, dropped


# ──────────────────────────────────────────────
# 프롬프트 블록
# ──────────────────────────────────────────────
def _human(n: int) -> str:
    return f"{n/1000:.1f}k" if n >= 1000 else str(n)


def build_block(
    files: list[dict[str, Any]],
    query: str,
    *,
    budget_chars: int = None,
    memory_root: str = "",
    index_only: bool = False,
) -> str:
    """
    표준 주입 블록을 만든다.

    index_only=True  → 목차만 (Lead 계획용, 저비용)
    index_only=False → 목차 + 관련 챕터 본문
    """
    budget = budget_chars if budget_chars is not None else DEFAULT_BUDGET
    chapters = chapters_of_files(files)
    if not chapters:
        return ""

    total_chars = sum(c["chars"] for c in chapters)

    if index_only:
        taken, dropped = [], chapters
    else:
        taken, dropped = select(chapters, query, budget)
    taken_ids = {id(c) for c in taken}

    # ── 목차: 파일 단위로 묶는다 ──────────────────────────────
    by_file: dict[str, list[dict[str, Any]]] = {}
    for ch in chapters:
        by_file.setdefault(ch["path"], []).append(ch)

    lines: list[str] = [
        f"\n\n## 📚 팀 표준/디렉션 — 목차 "
        f"(파일 {len(by_file)}개 · 항목 {len(chapters)}개 · 전체 {_human(total_chars)}자)",
    ]
    if memory_root:
        lines.append(f"경로는 `{memory_root}` 기준.")

    for path in list(by_file)[:MAX_INDEX_FILES]:
        chs = by_file[path]
        size = _human(sum(c["chars"] for c in chs))
        got = [c for c in chs if id(c) in taken_ids]
        if index_only:
            names = ", ".join(c["title"] for c in chs[:TITLES_PER_FILE])
            more = f" 외 {len(chs) - TITLES_PER_FILE}개" if len(chs) > TITLES_PER_FILE else ""
            lines.append(f"- {path} ({len(chs)}항목 · {size}) — {names}{more}")
        elif got:
            names = ", ".join(c["title"] for c in got[:TITLES_PER_FILE])
            more = f" 외 {len(got) - TITLES_PER_FILE}개" if len(got) > TITLES_PER_FILE else ""
            mark = "📌" if is_pinned(path) else "✅"
            lines.append(f"- {mark} {path} ({len(got)}/{len(chs)}항목 실림) — {names}{more}")
        else:
            lines.append(f"- ⬜ {path} ({len(chs)}항목 · {size}) — 미수록")

    if len(by_file) > MAX_INDEX_FILES:
        lines.append(f"- … 외 파일 {len(by_file) - MAX_INDEX_FILES}개 (목차 표시 상한)")

    if index_only:
        lines.append("\n※ 본문은 집필 담당 에이전트에게 주입된다. 계획 단계에선 목차만 본다.")
        return "\n".join(lines)

    # ── 관련도는 높은데 예산에 밀린 것 — 이건 개별로 알려줘야 찾아본다 ──
    qt = set(_tokens(query))
    near = sorted(
        ((score_chapter(c, qt), c) for c in dropped),
        key=lambda p: (-p[0], p[1]["file_order"], p[1]["order"]),
    )
    near = [c for s, c in near if s > 0][:MAX_NEARMISS]
    if near:
        lines.append("\n관련은 있으나 예산에 밀려 본문을 싣지 못한 항목:")
        for c in near:
            lines.append(f"- {c['path']} § {c['title']} ({_human(c['chars'])})")

    root_hint = f" (루트: `{memory_root}`)" if memory_root else ""
    lines.append(
        f"\n필요한데 본문이 없으면 **추측하지 말고** 해당 파일을 직접 열어라{root_hint}. "
        f"열 수 없으면 `확인 필요: <경로> § <항목>` 이라고 적는다."
    )

    if taken:
        lines.append("\n## 📚 실린 표준 본문 (적극 인용 — `경로 § 항목` 으로 출처 명시)")
        for ch in taken:
            lines.append(f"\n### [표준] {ch['path']} § {ch['title']}\n{ch['text']}")

    if dropped:
        lines.append(
            f"\n※ 관련도·예산 기준으로 {len(dropped)}개 항목"
            f"({_human(sum(c['chars'] for c in dropped))}자)은 본문을 싣지 않았다."
        )
    return "\n".join(lines)


def stats(files: list[dict[str, Any]], query: str, budget_chars: int = None) -> dict[str, Any]:
    """측정용 — 실제 주입 전후 크기 비교."""
    budget = budget_chars if budget_chars is not None else DEFAULT_BUDGET
    chapters = chapters_of_files(files)
    taken, dropped = select(chapters, query, budget)
    pin = [c for c in taken if c.get("pinned")]
    return {
        "files": len(files),
        "chapters": len(chapters),
        "total_chars": sum(c["chars"] for c in chapters),
        "taken": len(taken),
        "taken_chars": sum(c["chars"] for c in taken),
        "pinned": len(pin),
        "pinned_chars": sum(c["chars"] for c in pin),
        "dropped": len(dropped),
    }
