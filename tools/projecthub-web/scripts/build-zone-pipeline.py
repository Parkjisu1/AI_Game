#!/usr/bin/env python3
"""Adapt gen_43_hybrid_pipeline.py → zone_pipeline.py for Mother watcher.

Removes:
- PIL import + make_image() (rendering, watcher does not need)
- __main__ block (CSV-driven; watcher invokes as library)

Appends entry function `generate_field_from_metaphor(...)` returning BL field_map shape.
"""
import re
from pathlib import Path

SRC = Path(r"C:/Users/user/Downloads/v43_hybrid_delivery/gen_43_hybrid_pipeline.py")
DST = Path(r"E:/AI/tools/projecthub-web/scripts/zone_pipeline.py")

assert SRC.exists(), f"source missing: {SRC}"

text = SRC.read_text(encoding="utf-8")

# 1) drop PIL import
text = re.sub(r"^from PIL import Image\s*$", "# PIL removed for watcher (no rendering needed)", text, count=1, flags=re.MULTILINE)

# 2) drop make_image function (until next blank-line + def or comment-block boundary)
m = re.search(r"^def make_image\([^)]*\)[^:]*:", text, re.MULTILINE)
if m:
    start = m.start()
    # find next "^def " or "^# ══════" or "^if __name__" at column 0
    rest = text[start + len(m.group(0)):]
    next_top = re.search(r"^(def |# ══|if __name__)", rest, re.MULTILINE)
    if next_top:
        end = start + len(m.group(0)) + next_top.start()
    else:
        end = len(text)
    text = text[:start] + "# make_image() removed for watcher (no rendering)\n\n" + text[end:]

# 3) drop __main__ block
text = re.sub(r"^if __name__ == \"__main__\":[\s\S]*$", "# __main__ block removed for watcher (library use only)\n", text, count=1, flags=re.MULTILINE)

# 4) Append entry function
ENTRY = '''

# ══════════════════════════════════════════════════════════
# Watcher 진입점 (field_complete_levels.STEP 2 통합용)
# ══════════════════════════════════════════════════════════

def generate_field_from_metaphor(
    rows: int,
    cols: int,
    num_colors: int,
    metaphor: str,
    level: int,
    seed_offset: int = 0,
    has_life_gimmick: bool = False,
):
    """메타포 텍스트 → 41 종 ZoneMap → 색상 배정 → BL field_map (rows×cols 정수 그리드).

    Returns (grid, palette_ids):
        grid: list[list[int]], grid[y][x] = BL palette ID (1..28) 또는 0(=empty/T)
        palette_ids: list[int], 사용 색상의 BL palette ID (1-based, num_colors 개)

    호출 측: field_complete_levels._complete_one_seed STEP 2 fallback.
    designer_note 에 [FieldMap] 없을 때 메타포로부터 field_map 자동 생성.
    """
    # generate_zone_seeds 는 항상 seed_id 0..n-1 사용. seed_offset 별 다른 ZoneMap 가져오려면
    # 마지막 seed 만 픽 (또는 seed_start 도입). 단순화 → n_seeds = seed_offset + 1, 마지막 픽.
    try:
        n = max(1, seed_offset + 1)
        seeds = generate_zone_seeds(cols, rows, num_colors, metaphor or "", level, n_seeds=n)
        if not seeds:
            return [], []
        seed = seeds[-1]
    except Exception as e:
        # 메타포 미인식 등 — 호출 측에서 fallback (generate_default_layout) 으로 진행
        return [], []

    grid_local = seed["grid"]
    colors_hex = seed["colors"]
    n_colors = seed.get("num_colors", num_colors)

    # hex → BL palette ID (1-based)
    palette_ids = []
    for hx in colors_hex:
        try:
            palette_ids.append(PALETTE.index(hx) + 1)
        except ValueError:
            # 알 수 없는 색 (방어적) — 가장 가까운 PALETTE 인덱스로 대체
            palette_ids.append(1)

    # T → 0, 0..n-1 → palette_ids[c]
    out = []
    H = len(grid_local)
    for y in range(H):
        row_out = []
        W_local = len(grid_local[y])
        for x in range(W_local):
            v = grid_local[y][x]
            if v == T_VALUE:
                row_out.append(0)
            elif isinstance(v, int) and 0 <= v < len(palette_ids):
                row_out.append(palette_ids[v])
            else:
                row_out.append(0)
        out.append(row_out)
    return out, palette_ids


def is_metaphor_recognized(metaphor: str) -> bool:
    """메타포가 METAPHOR_ZONE_MAP 에 매핑되어 있는지 (퍼지 매칭 포함)."""
    if not metaphor:
        return False
    if metaphor in METAPHOR_ZONE_MAP:
        return True
    for key in METAPHOR_ZONE_MAP:
        if key in metaphor or metaphor in key:
            return True
    return False
'''

text = text.rstrip() + ENTRY

DST.parent.mkdir(parents=True, exist_ok=True)
DST.write_text(text, encoding="utf-8")
print(f"wrote {DST}  ({len(text.splitlines())} lines)")
