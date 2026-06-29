"""
Batch level generator — mood × N levels 일괄 생성.

각 iteration:
  1. mood pool에서 결정성 random palette 샘플링 (n_colors개)
  2. pattern pool에서 결정성 random pick
  3. cowork process_level 호출 → 9 변형 + score_grid + rank → best 자동 채택
  4. PNG 렌더 + pixelforge_grid_levels 저장 (mood 필드 포함)

사용:
  python batch_generate_levels.py --mood warm --count 500
  python batch_generate_levels.py --mood pastel --count 50 --width 30 --height 30
  python batch_generate_levels.py --mood all  # 4 mood × count 모두 (warm/cool/pastel/vivid)

LLM 안 씀. designer LLM 비용 0. 결정성 — 같은 mood/i면 같은 결과.
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

log = logging.getLogger("batch-levels")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _load_dotenv(env_path: str = "") -> None:
    """
    .env 파일을 직접 파싱해 os.environ에 주입. xargs/shell 변수 expansion 우회.
    MongoDB URI의 `&`/`?` 같은 shell-special 문자 안전하게 처리.
    """
    if not env_path:
        env_path = str(Path(__file__).resolve().parent / ".env")
    p = Path(env_path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        # 따옴표 stripping (선택적)
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1]
        os.environ.setdefault(k, v)


# 항상 .env 자동 로드 (이미 환경변수에 있으면 setdefault라 덮어쓰지 않음)
_load_dotenv()

# BalloonFlow 24색을 4 mood로 분류
MOOD_PALETTES: dict[str, list[int]] = {
    "warm":   [0, 3, 5, 10, 15, 16, 17, 18, 21],   # HotPink, Yellow, Orange, Red, Brown, Cream, Pink, Wine, Rose
    "cool":   [1, 2, 8, 9, 11, 12, 13, 14, 20],    # Cyan, Purple, SkyBlue, Forest, Blue, Teal, Lavender, Periwinkle, Indigo
    "pastel": [0, 6, 8, 13, 14, 16, 17, 19, 22],   # HotPink, White, SkyBlue, Lavender, Periwinkle, Cream, Pink, Mint, Silver
    "vivid":  [0, 1, 2, 3, 4, 5, 10, 11],          # HotPink, Cyan, Purple, Yellow, Green, Orange, Red, Blue
}

# 패턴 풀 — cowork 13개 (process_level 거침)
# 제외(2026-04-29): chevron, kaleidoscope, diamond_check, i_tetromino
#   → 항상 빈칸 cluster≥13 ("쥐파먹은" 모양) 발생, blank_engine으로 cluster≤1 달성 불가.
#   variant_pipeline의 차단 로직이 REJECT하므로 batch에서 시간 낭비만 됨.
COWORK_PATTERNS = [
    "hex_tile", "maze", "brick",
    "rect_grid", "stripe", "truchet",
    "argyle", "wave", "concentric_sq", "checkerboard", "x_motif",
    "t_motif", "plus_motif",
    # 노이즈 패턴은 mood batch에서 제외 (xor_fractal, sierpinski_carpet)
]

# 4 구조 스타일별 패턴 풀 (cowork 패턴 안에서 분류)
STYLE_PATTERNS: dict[str, list[str]] = {
    "kaleidoscope": [
        "concentric_sq", "x_motif", "plus_motif",
    ],
    "tile": [
        "hex_tile", "brick", "checkerboard", "truchet", "argyle", "stripe",
    ],
    "organic": [
        "maze", "wave",  # voronoi는 별도 backend (skip)
    ],
    "motif": [
        "t_motif", "rect_grid",
    ],
}

# Size presets — 가로×세로 변주
SIZE_PRESETS: dict[str, list[tuple[int, int]]] = {
    "small":  [(20, 20)],
    "medium": [(25, 25)],
    "large":  [(30, 30)],
    "tall":   [(20, 30)],
    "wide":   [(30, 20)],
    "mixed":  [(20, 20), (25, 25), (30, 30), (20, 30), (30, 20), (25, 30), (30, 25)],
}


def _pick_size(size: str, idx: int) -> tuple[int, int]:
    """size preset에서 W×H 결정성 pick. 단일 사이즈면 그대로, mixed면 idx 기반 random."""
    pool = SIZE_PRESETS.get(size, [(25, 25)])
    if len(pool) == 1:
        return pool[0]
    rng = random.Random(f"size-{size}-{idx}")
    return rng.choice(pool)


# 결정성 mood pick — style/idx 조합으로 mood 4개 중 1개 선택
def _pick_mood(style: str, idx: int) -> str:
    rng = random.Random(f"{style}-mood-{idx}")
    return rng.choice(["warm", "cool", "pastel", "vivid"])


# ─────────────────────────────────────────────────────
# CSV input 지원 — PixelForge 포맷과 호환
# ─────────────────────────────────────────────────────
# Motif/Shape 키워드 → cowork pattern 매칭 LUT
# 매칭 안 되면 'kaleidoscope' fallback.
MOTIF_KEYWORDS: list[tuple[str, str]] = [
    # (keyword substring, pattern name) — 첫 매칭 우선
    ("kaleidoscope", "kaleidoscope"),
    ("mandala",      "kaleidoscope"),
    ("ring",         "concentric_sq"),
    ("circle",       "concentric_sq"),
    ("concentric",   "concentric_sq"),
    ("dart",         "x_motif"),
    ("x-shape",      "x_motif"),
    ("x_motif",      "x_motif"),
    ("plus",         "plus_motif"),
    ("t-shape",      "t_motif"),
    ("t_motif",      "t_motif"),
    ("hex",          "hex_tile"),
    ("brick",        "brick"),
    ("wall",         "brick"),
    ("maze",         "maze"),
    ("labyrinth",    "maze"),
    ("wave",         "wave"),
    ("ripple",       "wave"),
    ("diamond",      "diamond_check"),
    ("rhomb",        "diamond_check"),
    ("chevron",      "chevron"),
    ("zigzag",       "chevron"),
    ("argyle",       "argyle"),
    ("truchet",      "truchet"),
    ("stripe",       "stripe"),
    ("line",         "stripe"),
    ("checker",      "checkerboard"),
    ("grid",         "rect_grid"),
    ("rectang",      "rect_grid"),
    ("tetro",        "i_tetromino"),
    ("L-shape",      "i_tetromino"),
    ("tile",         "hex_tile"),  # 일반 'tile' fallback
]



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


def _pattern_from_motif(designer_note: str, fallback: str = "kaleidoscope") -> str:
    """designer_note에서 [Motif]/[Shape] 키워드 추출 후 cowork pattern 매칭.
    매칭 못하면 fallback (default kaleidoscope)."""
    if not designer_note:
        return fallback
    note = designer_note.lower()
    # [Motif]: ... 또는 [Shape]: ... 안의 텍스트 우선 검사
    import re
    motif_match = re.search(r"\[motif\][^:\[]*:?\s*([^\[\n]+)", note)
    shape_match = re.search(r"\[shape\][^:\[]*:?\s*([^\[\n]+)", note)
    haystack_parts: list[str] = []
    if motif_match:
        haystack_parts.append(motif_match.group(1))
    if shape_match:
        haystack_parts.append(shape_match.group(1))
    haystack = " ".join(haystack_parts) if haystack_parts else note
    for kw, pat in MOTIF_KEYWORDS:
        if kw in haystack:
            return pat
    return fallback


def _palette_from_color_dist(color_dist: str, n_colors: int = 4) -> list[int]:
    """PixelForge 'c1,c2,c3,c4' → BalloonFlow 인덱스 0~23 변환.
    c1=0, c2=1, ..., c24=23, c25~=wrap mod 24.
    n_colors가 dist 길이보다 크면 추가로 wrap pad."""
    import re
    if not color_dist:
        return list(range(min(n_colors, 24)))
    raw = re.findall(r"c(\d+)", color_dist.lower())
    indices = [(int(x) - 1) % 24 for x in raw]
    # dedupe 유지하며 우선순위 보존
    seen: set[int] = set()
    out: list[int] = []
    for i in indices:
        if i not in seen:
            out.append(i)
            seen.add(i)
        if len(out) >= n_colors:
            break
    # 부족하면 미사용 인덱스로 채움
    if len(out) < n_colors:
        for i in range(24):
            if i not in seen and len(out) < n_colors:
                out.append(i)
                seen.add(i)
    return out[:n_colors]


def _sample_palette(mood: str, n_colors: int, idx: int) -> list[int]:
    """mood pool에서 n_colors개 결정성 sampling. (mood, idx) 같으면 같은 결과."""
    pool = MOOD_PALETTES.get(mood, [])
    if not pool:
        return [0, 2, 13, 17][:n_colors]
    rng = random.Random(f"{mood}-palette-{idx}")
    n = min(n_colors, len(pool))
    return rng.sample(pool, n)


def _pick_pattern(mood: str, idx: int, style: str = "") -> str:
    """pattern pool에서 결정성 pick. style 지정 시 그 스타일 패턴 풀로 한정."""
    pool = STYLE_PATTERNS.get(style, COWORK_PATTERNS) if style else COWORK_PATTERNS
    rng = random.Random(f"{mood}-{style}-pattern-{idx}")
    return rng.choice(pool)


def generate_one(
    *, mood: str, idx: int, width: int, height: int, n_colors: int,
    base_email: str = "batch@aimed.xyz", style: str = "", size: str = "",
    allow_duplicate: bool = False,
) -> dict[str, Any]:
    """1 레벨 생성 + 저장. 결과 metadata dict 반환.
    size가 주어지면 SIZE_PRESETS에서 결정성 pick (width/height arg 무시).
    """
    import pattern_lib  # noqa: F401  -- sys.path 등록
    from variant_pipeline import process_level  # type: ignore
    from pixel_pattern_api import _hex_to_rgb  # type: ignore
    from level_png_renderer import render_grid_to_png
    from level_storage import save_level, compute_structure_hash, structure_exists
    from design_teams import bf_index_to_hex

    if size:
        width, height = _pick_size(size, idx)

    palette = _sample_palette(mood, n_colors, idx)
    pattern = _pick_pattern(mood, idx, style=style)
    seed = idx * 13

    colors_hex = [bf_index_to_hex(c) for c in palette]
    entry = {
        "_meta": {"level": idx},
        "pattern": pattern,
        "width": width,
        "height": height,
        "colors": colors_hex,
        "seed": seed,
    }

    t0 = time.monotonic()
    try:
        result = process_level(entry, save_all_variants=False, extended_seeds=10)
    except Exception:
        log.exception("[batch %s/%d] process_level failed", mood, idx)
        return {"ok": False, "error": "process_level exception"}
    if result is None:
        return {"ok": False, "error": "no candidate"}

    rgb_grid = result["chosen_grid"]
    chosen_variant = result["chosen_variant"]
    sc = result["chosen_score"]
    duration = time.monotonic() - t0

    # RGBA → BalloonFlow 인덱스 변환
    rgb_to_bf: dict[tuple, int] = {}
    for i, hexstr in enumerate(colors_hex):
        rgb3 = _hex_to_rgb(hexstr)
        rgb_to_bf[(rgb3[0], rgb3[1], rgb3[2], 255)] = palette[i]

    cells: list[list[int]] = []
    counts: dict[int, int] = {}
    for r in range(height):
        row_out: list[int] = []
        for c in range(width):
            v = rgb_grid[r][c] if r < len(rgb_grid) and c < len(rgb_grid[r]) else None
            if isinstance(v, tuple):
                if len(v) >= 4 and v[3] == 0:
                    row_out.append(-1)
                    continue
                bf = rgb_to_bf.get(v)
                if bf is None and len(v) >= 3:
                    bf = rgb_to_bf.get((v[0], v[1], v[2], 255))
                if bf is None:
                    row_out.append(-1)
                else:
                    row_out.append(bf)
                    counts[bf] = counts.get(bf, 0) + 1
            else:
                row_out.append(-1)
        cells.append(row_out)

    # 색상만 다른 중복 차단 — structure_hash로 이미 저장된 것 있으면 skip (allow_duplicate=True이면 우회)
    structure_hash = compute_structure_hash(cells)
    if structure_exists(structure_hash) and not allow_duplicate:
        return {"ok": False, "skipped": True, "error": "duplicate_structure",
                "structure_hash": structure_hash, "pattern": pattern, "mood": mood}

    if style:
        name = f"{style}-{mood}-{pattern}-{idx:04d}"
        title = f"{style} · {mood} · {pattern} · _{chosen_variant}"
    else:
        name = f"{mood}-{pattern}-{idx:04d}"
        title = f"{mood} · {pattern} · _{chosen_variant}"
    try:
        png_bytes = render_grid_to_png(cells, cell_size_px=20, title=title)
    except Exception as e:
        log.exception("[batch %s/%d] render failed", mood, idx)
        return {"ok": False, "error": f"render: {e}"}

    try:
        saved = save_level(
            spec={
                "width": width, "height": height,
                "symmetry": "none",
                "palette": palette,
                "per_color_count": counts,
                "seed": seed,
                "pattern": pattern,
            },
            cells=cells, png_bytes=png_bytes,
            validation={
                "ok": bool(sc.get("is_10_mult", False)),
                "errors": [],
                "color_counts": {str(k): v for k, v in counts.items()},
                "filled_cells": sum(counts.values()),
                "empty_cells": width * height - sum(counts.values()),
                "lenient": True,
                "score": {
                    "is_10_mult":  bool(sc.get("is_10_mult", False)),
                    "sym_best":    float(sc.get("sym_best", 0)),
                    "scatter":     int(sc.get("scatter", 0)),
                    "bg_ratio":    float(sc.get("bg_ratio", 0)),
                    "composite":   float(sc.get("composite", 0)),
                },
            },
            task_id=None,
            task_title=f"[batch][{mood}] {name}",
            created_by_email=base_email,
            name=name,
            team_id=f"batch_{style}_{mood}" if style else f"batch_{mood}",
            pattern_chosen=f"{pattern} _{chosen_variant}",
            mood=mood,
            extra_meta={
                "batch_idx": idx,
                "style": style or None,
                "duration_sec": round(duration, 2),
                "score": {k: float(sc.get(k, 0)) if not isinstance(sc.get(k), bool) else bool(sc.get(k))
                          for k in ("is_10_mult", "sym_best", "scatter", "bg_ratio", "composite")},
            },
        )
        return {
            "ok": True, "id": saved["id"], "mood": mood, "style": style or None,
            "pattern": pattern,
            "variant": chosen_variant, "duration": round(duration, 2),
            "composite": round(float(sc.get("composite", 0)), 1),
            "scatter": int(sc.get("scatter", 0)),
        }
    except Exception as e:
        log.exception("[batch %s/%d] save failed", mood, idx)
        return {"ok": False, "error": f"save: {e}"}


def generate_one_from_csv(
    *, row: dict[str, Any], idx: int,
    base_email: str = "batch@aimed.xyz",
    csv_source: str = "csv",
    allow_duplicate: bool = False,
) -> dict[str, Any]:
    """CSV 한 row를 받아 1 레벨 생성. 명시적 W/H/palette/pattern 사용.
    row 키 (alias 처리는 client에서 정규화 후 전달):
      level_number  : int
      width         : int (field_columns)
      height        : int (field_rows)
      n_colors      : int (num_colors)
      palette       : int[] (BF index 변환된 결과; 없으면 color_distribution에서 변환)
      color_dist    : str  (raw 'c1,c2' — palette 없을 때 변환용)
      pattern       : str  (cowork pattern; 없으면 designer_note에서 추론)
      designer_note : str
      purpose       : str (선택)
    """
    import pattern_lib  # noqa: F401
    from variant_pipeline import process_level  # type: ignore
    from pixel_pattern_api import _hex_to_rgb  # type: ignore
    from level_png_renderer import render_grid_to_png
    from level_storage import save_level, compute_structure_hash, structure_exists
    from design_teams import bf_index_to_hex

    width = int(row.get("width") or 25)
    height = int(row.get("height") or 25)
    n_colors = max(2, min(8, int(row.get("n_colors") or 4)))

    palette: list[int] = list(row.get("palette") or [])
    if not palette:
        palette = _palette_from_color_dist(str(row.get("color_dist") or ""), n_colors=n_colors)
    if len(palette) < n_colors:
        for i in range(24):
            if i not in palette and len(palette) < n_colors:
                palette.append(i)

    pattern = str(row.get("pattern") or "").strip()
    if not pattern:
        # v2026-05-22: bl_metaphor (한글) 우선 → designer_note (영문) 보조.
        # 이전엔 designer_note 만 봐서 한글 메타포가 fallback 으로 빠짐 (kaleidoscope 75%+ 편향).
        bl_meta = str(row.get("bl_metaphor") or "")
        pattern = _pattern_from_bl_metaphor(bl_meta) or _pattern_from_motif(str(row.get("designer_note") or ""))

    level_no = int(row.get("level_number") or idx)
    seed = level_no * 13 + 7

    colors_hex = [bf_index_to_hex(c) for c in palette]
    entry = {
        "_meta": {"level": level_no},
        "pattern": pattern,
        "width": width,
        "height": height,
        "colors": colors_hex,
        "seed": seed,
    }

    t0 = time.monotonic()
    try:
        result = process_level(entry, save_all_variants=False, extended_seeds=10)
    except Exception:
        log.exception("[csv #%d lv=%d] process_level failed", idx, level_no)
        return {"ok": False, "error": "process_level exception"}
    if result is None:
        return {"ok": False, "error": "no candidate"}

    rgb_grid = result["chosen_grid"]
    chosen_variant = result["chosen_variant"]
    sc = result["chosen_score"]
    duration = time.monotonic() - t0

    rgb_to_bf: dict[tuple, int] = {}
    for i, hexstr in enumerate(colors_hex):
        rgb3 = _hex_to_rgb(hexstr)
        rgb_to_bf[(rgb3[0], rgb3[1], rgb3[2], 255)] = palette[i]

    cells: list[list[int]] = []
    counts: dict[int, int] = {}
    for r in range(height):
        row_out: list[int] = []
        for c in range(width):
            v = rgb_grid[r][c] if r < len(rgb_grid) and c < len(rgb_grid[r]) else None
            if isinstance(v, tuple):
                if len(v) >= 4 and v[3] == 0:
                    row_out.append(-1)
                    continue
                bf = rgb_to_bf.get(v)
                if bf is None and len(v) >= 3:
                    bf = rgb_to_bf.get((v[0], v[1], v[2], 255))
                if bf is None:
                    row_out.append(-1)
                else:
                    row_out.append(bf)
                    counts[bf] = counts.get(bf, 0) + 1
            else:
                row_out.append(-1)
        cells.append(row_out)

    structure_hash = compute_structure_hash(cells)
    if structure_exists(structure_hash) and not allow_duplicate:
        return {"ok": False, "skipped": True, "error": "duplicate_structure",
                "structure_hash": structure_hash, "pattern": pattern,
                "level_number": level_no}

    name = f"csv-lv{level_no:04d}-{pattern}"
    title = f"CSV · lv{level_no} · {pattern} · _{chosen_variant}"
    try:
        png_bytes = render_grid_to_png(cells, cell_size_px=20, title=title)
    except Exception as e:
        log.exception("[csv #%d lv=%d] render failed", idx, level_no)
        return {"ok": False, "error": f"render: {e}"}

    try:
        saved = save_level(
            spec={
                "width": width, "height": height,
                "symmetry": "none",
                "palette": palette,
                "per_color_count": counts,
                "seed": seed,
                "pattern": pattern,
            },
            cells=cells, png_bytes=png_bytes,
            validation={
                "ok": bool(sc.get("is_10_mult", False)),
                "errors": [],
                "color_counts": {str(k): v for k, v in counts.items()},
                "filled_cells": sum(counts.values()),
                "empty_cells": width * height - sum(counts.values()),
                "lenient": True,
                "score": {
                    "is_10_mult":  bool(sc.get("is_10_mult", False)),
                    "sym_best":    float(sc.get("sym_best", 0)),
                    "scatter":     int(sc.get("scatter", 0)),
                    "bg_ratio":    float(sc.get("bg_ratio", 0)),
                    "composite":   float(sc.get("composite", 0)),
                },
            },
            task_id=None,
            task_title=f"[csv][{csv_source}] {name}",
            created_by_email=base_email,
            name=name,
            team_id="batch_csv",
            pattern_chosen=f"{pattern} _{chosen_variant}",
            mood=None,
            extra_meta={
                "csv_source": csv_source,
                "level_number": level_no,
                "designer_note": str(row.get("designer_note") or "")[:500],
                "purpose": str(row.get("purpose") or "")[:80],
                "duration_sec": round(duration, 2),
                "score": {k: float(sc.get(k, 0)) if not isinstance(sc.get(k), bool) else bool(sc.get(k))
                          for k in ("is_10_mult", "sym_best", "scatter", "bg_ratio", "composite")},
            },
        )
        return {
            "ok": True, "id": saved["id"], "level_number": level_no,
            "pattern": pattern, "variant": chosen_variant,
            "duration": round(duration, 2),
            "composite": round(float(sc.get("composite", 0)), 1),
            "scatter": int(sc.get("scatter", 0)),
            "width": width, "height": height,
        }
    except Exception as e:
        log.exception("[csv #%d lv=%d] save failed", idx, level_no)
        return {"ok": False, "error": f"save: {e}"}


def run_csv_batch(*, csv_rows: list[dict[str, Any]],
                  email: str = "batch@aimed.xyz",
                  csv_source: str = "csv",
                  allow_duplicate: bool = False) -> dict[str, Any]:
    """CSV row 리스트로 batch 처리."""
    print(f"\n=== csv batch start: rows={len(csv_rows)} source={csv_source} ===")
    t_start = time.monotonic()
    n_ok = n_fail = n_skip = 0
    fails: list[str] = []
    for i, row in enumerate(csv_rows):
        r = generate_one_from_csv(row=row, idx=i, base_email=email, csv_source=csv_source, allow_duplicate=allow_duplicate)
        if r.get("ok"):
            n_ok += 1
            if (i + 1) % 10 == 0 or (i + 1 == len(csv_rows)):
                elapsed = time.monotonic() - t_start
                eta = elapsed / (i + 1) * (len(csv_rows) - (i + 1)) if (i + 1) > 0 else 0
                print(f"  [{i+1:4d}/{len(csv_rows)}] lv{r.get('level_number'):04d} · "
                      f"{r.get('width')}×{r.get('height')} · {r.get('pattern'):16s} · "
                      f"_{r.get('variant')} · {r.get('duration')}s · eta={eta:.0f}s")
        elif r.get("skipped"):
            n_skip += 1
        else:
            n_fail += 1
            fails.append(f"#{i} lv={row.get('level_number')}: {r.get('error')}")
    total = time.monotonic() - t_start
    print(f"=== csv done: ok={n_ok} dedup_skip={n_skip} fail={n_fail} total={total:.0f}s ===")
    if fails[:5]:
        print(f"  failures (first 5):")
        for f in fails[:5]:
            print(f"    {f}")
    return {"label": f"csv:{csv_source}", "ok": n_ok, "fail": n_fail,
            "dedup_skip": n_skip, "duration_sec": total}


def run_batch(*, mood: str, count: int, width: int, height: int, n_colors: int,
              start_idx: int = 0, email: str = "batch@aimed.xyz",
              style: str = "", size: str = "", allow_duplicate: bool = False) -> dict[str, Any]:
    """1 (style+mood) × count batch. mood가 'random'이면 each item별로 결정성 random pick.
    size가 주어지면 SIZE_PRESETS pick (width/height 무시), 'mixed'면 item별 random.
    """
    label = f"{style}/" if style else ""
    size_label = size or f"{width}×{height}"
    print(f"\n=== batch start: {label}mood={mood} size={size_label} count={count} n_colors={n_colors} ===")
    t_start = time.monotonic()
    n_ok = 0
    n_fail = 0
    n_skip = 0
    fails: list[str] = []
    for i in range(start_idx, start_idx + count):
        # mood='random'이면 item별로 4 mood 중 결정성 random
        item_mood = _pick_mood(style or "any", i) if mood == "random" else mood
        r = generate_one(
            mood=item_mood, idx=i, width=width, height=height,
            n_colors=n_colors, base_email=email, style=style, size=size,
            allow_duplicate=allow_duplicate,
        )
        if r.get("ok"):
            n_ok += 1
            if (i + 1) % 25 == 0 or (i + 1 == start_idx + count):
                elapsed = time.monotonic() - t_start
                eta = elapsed / (i + 1 - start_idx) * (count - (i + 1 - start_idx)) if (i + 1 - start_idx) > 0 else 0
                print(f"  [{i + 1 - start_idx:4d}/{count}] {label}{r.get('mood', mood)} · {r.get('pattern'):16s} · "
                      f"_{r.get('variant')} · scatter={r.get('scatter')} · "
                      f"comp={r.get('composite'):.0f} · "
                      f"{r.get('duration')}s · elapsed={elapsed:.0f}s eta={eta:.0f}s")
        elif r.get("skipped"):
            n_skip += 1
        else:
            n_fail += 1
            fails.append(f"#{i}: {r.get('error')}")
    total = time.monotonic() - t_start
    print(f"=== {label}mood={mood} done: ok={n_ok} dedup_skip={n_skip} fail={n_fail} total={total:.0f}s ===")
    if fails[:5]:
        print(f"  failures (first 5):")
        for f in fails[:5]:
            print(f"    {f}")
    return {"label": f"{style}/{mood}" if style else mood,
            "ok": n_ok, "fail": n_fail, "dedup_skip": n_skip,
            "duration_sec": total}


REQUESTS_COLLECTION = "pixelforge_batch_requests"


def _pull_request(req_id: str) -> dict[str, Any]:
    """batch_requests 컬렉션에서 doc fetch + status='running' 마킹."""
    from pymongo import MongoClient
    from bson import ObjectId
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    db_name = os.environ.get("MONGODB_DB", "aigame")
    db = MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    doc = db[REQUESTS_COLLECTION].find_one({"_id": ObjectId(req_id)})
    if not doc:
        raise RuntimeError(f"batch_request {req_id} not found")
    db[REQUESTS_COLLECTION].update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": "running",
                  "started_at": _iso_now()}},
    )
    return doc


def _finalize_request(req_id: str, *, summary: list[dict[str, Any]],
                      error: str = "") -> None:
    """batch_requests doc에 결과 기록."""
    from pymongo import MongoClient
    from bson import ObjectId
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        return
    db_name = os.environ.get("MONGODB_DB", "aigame")
    db = MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    totals = {
        "ok": sum(s["ok"] for s in summary),
        "fail": sum(s["fail"] for s in summary),
        "dedup_skip": sum(s.get("dedup_skip", 0) for s in summary),
        "duration_sec": sum(s["duration_sec"] for s in summary),
    }
    update = {
        "status": "failed" if error else "done",
        "finished_at": _iso_now(),
        "result_summary": summary,
        "totals": totals,
    }
    if error:
        update["error"] = error
    db[REQUESTS_COLLECTION].update_one({"_id": ObjectId(req_id)}, {"$set": update})


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mood",
                    choices=["warm", "cool", "pastel", "vivid", "all", "random"],
                    default="random",
                    help="mood. 'all'=4개 순차, 'random'=item별 결정성 random pick (style batch에 추천)")
    ap.add_argument("--style",
                    choices=["kaleidoscope", "tile", "organic", "motif", "all", ""],
                    default="",
                    help="구조 스타일. 'all'이면 4 스타일 순차 실행. 빈 값이면 mood batch (모든 cowork 패턴).")
    ap.add_argument("--count", type=int, default=500,
                    help="(style 또는 mood) 당 생성 개수")
    ap.add_argument("--width", type=int, default=25)
    ap.add_argument("--height", type=int, default=25)
    ap.add_argument("--size",
                    choices=["", "small", "medium", "large", "tall", "wide", "mixed"],
                    default="",
                    help="size preset. 'mixed'면 item별 결정성 random. 빈 값이면 --width/--height 사용.")
    ap.add_argument("--n_colors", type=int, default=4)
    ap.add_argument("--start_idx", type=int, default=0,
                    help="시작 인덱스. default 0")
    ap.add_argument("--email", default="batch@aimed.xyz")
    ap.add_argument("--request",
                    help="pixelforge_batch_requests _id; DB에서 params 읽고 status update")
    args = ap.parse_args()

    # --request 모드: DB doc에서 params 읽기
    request_id = args.request
    csv_rows: list[dict[str, Any]] = []
    csv_source = "csv"
    if request_id:
        try:
            doc = _pull_request(request_id)
        except Exception as e:
            log.error("failed to pull request %s: %s", request_id, e)
            return 2
        args.mood     = doc.get("mood",     args.mood)
        args.style    = doc.get("style",    args.style)
        args.count    = int(doc.get("count", args.count))
        args.size     = doc.get("size",     args.size)
        args.n_colors = int(doc.get("n_colors", args.n_colors))
        args.start_idx = int(doc.get("start_idx", args.start_idx))
        args.email    = doc.get("created_by_email") or args.email
        if not args.size:
            args.width  = int(doc.get("width",  args.width))
            args.height = int(doc.get("height", args.height))
        csv_rows = list(doc.get("csv_rows") or [])
        csv_source = doc.get("csv_source") or "csv"
        args_allow_dup = bool(doc.get("allow_duplicate", False))
        if csv_rows:
            print(f"[request {request_id}] csv_rows={len(csv_rows)} source={csv_source}")
        else:
            print(f"[request {request_id}] mood={args.mood} style={args.style} "
                  f"size={args.size or f'{args.width}×{args.height}'} count={args.count}")

    if not request_id:
        args_allow_dup = False
    summary: list[dict[str, Any]] = []
    error_str = ""
    try:
        if csv_rows:
            # CSV 모드: row별로 처리. mood/style/size 무시.
            s = run_csv_batch(csv_rows=csv_rows, email=args.email, csv_source=csv_source, allow_duplicate=args_allow_dup)
            summary.append(s)
        elif args.style:
            styles = ["kaleidoscope", "tile", "organic", "motif"] if args.style == "all" else [args.style]
            for st in styles:
                s = run_batch(
                    mood=args.mood, count=args.count,
                    width=args.width, height=args.height, n_colors=args.n_colors,
                    start_idx=args.start_idx, email=args.email, style=st, size=args.size,
                    allow_duplicate=args_allow_dup,
                )
                summary.append(s)
        else:
            moods = ["warm", "cool", "pastel", "vivid"] if args.mood == "all" else [args.mood]
            for m in moods:
                s = run_batch(
                    mood=m, count=args.count,
                    width=args.width, height=args.height, n_colors=args.n_colors,
                    start_idx=args.start_idx, email=args.email, size=args.size,
                    allow_duplicate=args_allow_dup,
                )
                summary.append(s)
    except Exception as e:
        error_str = f"{type(e).__name__}: {e}"
        log.exception("batch failed")

    print("\n=== ALL DONE ===")
    for s in summary:
        print(f"  {s['label']:24s}: ok={s['ok']:4d} dedup={s.get('dedup_skip', 0):3d} "
              f"fail={s['fail']:3d} ({s['duration_sec']:.0f}s)")
    total_ok = sum(s["ok"] for s in summary)
    total_skip = sum(s.get("dedup_skip", 0) for s in summary)
    total_dur = sum(s["duration_sec"] for s in summary)
    print(f"  TOTAL   : ok={total_ok:4d} dedup={total_skip} ({total_dur:.0f}s = {total_dur/60:.1f}min)")

    if request_id:
        try:
            _finalize_request(request_id, summary=summary, error=error_str)
        except Exception:
            log.exception("failed to finalize batch_request %s", request_id)

    return 0 if not error_str else 1


if __name__ == "__main__":
    sys.exit(main())
