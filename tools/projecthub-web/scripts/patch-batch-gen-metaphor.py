#!/usr/bin/env python3
"""batch_generate_levels.py 에 bl_metaphor → cowork pattern 매핑 추가.

기존: _pattern_from_motif(designer_note) 만 — 한글 메타포 미매핑 → fallback kaleidoscope 75%+
신규: csv_row.bl_metaphor 우선 → 한글 매핑 → 매칭 안 되면 designer_note → 기존 키워드 매칭.
"""
import sys
PATH = "/home/aimed/.hermes/watcher/batch_generate_levels.py"

# Add KO_METAPHOR_TO_PATTERN map + _pattern_from_bl_metaphor helper before existing _pattern_from_motif
KO_MAP_AND_FUNC = '''
# v2026-05-22: bl_metaphor (BL 한글 메타포) → cowork pattern 매핑.
# 기존 _pattern_from_motif 는 designer_note 영문 키워드만 봤음.
# CSV bl_metaphor "나선/헤링본/체크/..." 를 cowork 19종에 매핑.
KO_METAPHOR_TO_PATTERN: list[tuple[str, str]] = [
    # 가장 명확한 매핑 우선 — 부분 매칭 (substring)
    ("나선",        "wave"),
    ("헤링본",      "chevron"),
    ("추상 라인",   "stripe"),
    ("도형 조합",   "x_motif"),
    ("물방울",      "wave"),
    ("동심 사각",   "concentric_sq"),
    ("그라데이션 사각", "concentric_sq"),
    ("추상 그라데", "wave"),
    ("구름 그라데", "wave"),
    ("색조 분할",   "stripe"),
    ("색상 띠",     "stripe"),
    ("방사 패턴",   "kaleidoscope"),
    ("빛 산란",     "kaleidoscope"),
    ("빛의 분산",   "kaleidoscope"),
    ("빛 입자",     "kaleidoscope"),
    ("추상 형상",   "xor_fractal"),
    ("도트 패턴",   "rect_grid"),
    ("체크 패턴",   "checkerboard"),
    ("외곽 체크",   "checkerboard"),
    ("다이아몬드",  "diamond_check"),
    ("광선 다발",   "kaleidoscope"),
    ("광선 패턴",   "kaleidoscope"),
    ("픽셀 그리드", "rect_grid"),
    ("컬러 블록",   "rect_grid"),
    ("컬러 픽셀",   "rect_grid"),
    ("불꽃",        "x_motif"),
    ("컬러 휠",     "kaleidoscope"),
    ("미궁",        "maze"),
    ("미로",        "maze"),
    ("줄무늬",      "stripe"),
    ("꽃 만다라",   "kaleidoscope"),
    ("눈송이 만다라","kaleidoscope"),
    ("만다라",      "kaleidoscope"),
    ("6각형",       "hex_tile"),
    ("육각",        "hex_tile"),
    ("우주 성운",   "wave"),
    ("성운",        "wave"),
    ("삼각 패턴",   "i_tetromino"),
    ("삼각",        "truchet"),
    ("브릭",        "brick"),
    ("벽돌",        "brick"),
    ("아가일",      "argyle"),
    ("프랙탈",      "xor_fractal"),
    ("시에르핀",    "sierpinski_carpet"),
    ("플러스",      "plus_motif"),
    ("십자",        "plus_motif"),
    ("X",           "x_motif"),
    ("T",           "t_motif"),
]


def _pattern_from_bl_metaphor(bl_metaphor: str) -> str | None:
    """bl_metaphor (한글) → cowork pattern. 매칭 못하면 None."""
    if not bl_metaphor:
        return None
    text = str(bl_metaphor).strip()
    if not text:
        return None
    for kw, pat in KO_METAPHOR_TO_PATTERN:
        if kw in text:
            return pat
    return None


'''

# Insert before existing _pattern_from_motif def
MARKER = "def _pattern_from_motif(designer_note: str, fallback: str = \"kaleidoscope\") -> str:"

# Update _make_csv_row_level to prefer bl_metaphor
OLD_CALL = '''    pattern = str(row.get("pattern") or "").strip()
    if not pattern:
        pattern = _pattern_from_motif(str(row.get("designer_note") or ""))'''

NEW_CALL = '''    pattern = str(row.get("pattern") or "").strip()
    if not pattern:
        # v2026-05-22: bl_metaphor (한글) 우선 → designer_note (영문) 보조.
        # 이전엔 designer_note 만 봐서 한글 메타포가 fallback 으로 빠짐 (kaleidoscope 75%+ 편향).
        bl_meta = str(row.get("bl_metaphor") or "")
        pattern = _pattern_from_bl_metaphor(bl_meta) or _pattern_from_motif(str(row.get("designer_note") or ""))'''


def main():
    with open(PATH, encoding="utf-8") as f:
        src = f.read()
    if "KO_METAPHOR_TO_PATTERN" in src:
        print("already patched. abort.")
        sys.exit(0)
    if MARKER not in src:
        print("ABORT: marker not found", file=sys.stderr); sys.exit(1)
    if OLD_CALL not in src:
        print("ABORT: call site not found", file=sys.stderr); sys.exit(1)
    # Insert helper before _pattern_from_motif
    src = src.replace(MARKER, KO_MAP_AND_FUNC + MARKER, 1)
    # Replace call site
    src = src.replace(OLD_CALL, NEW_CALL, 1)
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("patched ok")


if __name__ == "__main__":
    main()
