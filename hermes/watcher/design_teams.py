"""
Design Teams — 4팀 경쟁 격자 레벨 생성.

각 팀은 패턴 번들 + 페르소나를 가지며, 같은 task에 대해 1 level을 생성.
사용자가 1~5 별점으로 평가 → hermes_design_team_scores에 누적 → 약팀 자동 개선.

팀 구성:
  hermes_native — 결정성 정렬 (level_grid_generator 그대로 활용)
  geometric    — pixel_pattern_api 기하 (kaleidoscope, concentric_sq, diamond_check, x_motif, plus_motif, t_motif)
  organic      — pixel_pattern_api 유기 (voronoi, maze, wave, stripe)
  tile         — pixel_pattern_api 타일 (hex_tile, brick, checkerboard, truchet, argyle, chevron, i_tetromino)

API:
  TEAMS: dict[team_id, TeamSpec]
  run_team(team_id, request) -> TeamResult
"""

from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("design-teams")

# ──────────────────────────────────────────────
# Density mask — backend가 만든 grid의 밀도/형태를 spec에 맞게 조정
# ──────────────────────────────────────────────
MASK_SHAPES = {"uniform", "radial", "ring", "corners"}


# ──────────────────────────────────────────────
# Task type 분류 + pattern whitelist
# 사용자 요청 키워드로 task의 시각적 의도를 5유형 중 하나로 추정.
# 각 유형마다 허용 패턴 풀이 다름 — sierpinski/xor/argyle 같은 부적합 패턴 자동 차단.
# ──────────────────────────────────────────────

TASK_TYPES = {"kaleidoscope", "tile", "organic", "motif", "fractal", "any"}

TASK_TYPE_KEYWORDS: dict[str, list[str]] = {
    "kaleidoscope": [
        "만화경", "kaleidoscope", "방사", "별", "sunburst", "동심", "ring", "concentric",
        "그라데이션", "회오리", "spiral", "만다라", "mandala", "halo", "도넛",
    ],
    "tile": [
        "타일", "tile", "모자이크", "mosaic", "체크", "checker", "벽돌", "brick",
        "육각", "hex", "honeycomb", "픽셀아트", "pixel art", "픽셀 아트",
    ],
    "organic": [
        "유기", "organic", "voronoi", "보로노이", "미로", "maze", "통로",
        "파동", "wave", "물결", "줄무늬", "stripe", "자연", "natural",
    ],
    "motif": [
        "모티프", "motif", "엑스", "다이아", "diamond", "마름모", "플러스", "plus",
        "십자", "심볼", "symbol", "i형", "tetris", "테트리스", "사각 격자",
    ],
    "fractal": [
        "프랙탈", "fractal", "sierpinski", "시에르핀", "xor",
    ],
}

# Task 유형별 허용 패턴 (각 팀 내부에서 추가 필터링)
TASK_TYPE_PATTERN_WHITELIST: dict[str, set[str]] = {
    "kaleidoscope": {
        "rings", "rays", "spiral", "diamond",
        "kaleidoscope", "concentric_sq", "diamond_check",
        "voronoi", "wave",
        "hex_tile",
        # BalloonFlow custom — kaleidoscope 적합
        "bf_dartboard", "bf_mandala", "bf_flower_mandala", "bf_spiral",
        "bf_diamond_lattice", "bf_dot_grid", "bf_wave", "bf_knot",
    },
    "tile": {
        "blocks", "diamond",
        "diamond_check", "rect_grid",
        "stripe",
        "hex_tile", "brick", "checkerboard", "truchet", "argyle", "chevron",
        # BalloonFlow custom — tile 적합
        "bf_chevron", "bf_woven", "bf_triangle_tess", "bf_mosaic",
        "bf_dot_grid", "bf_diamond_lattice", "bf_corner_L",
    },
    "organic": {
        "rings", "spiral", "blocks",
        "voronoi", "maze", "wave", "stripe",
        "hex_tile",
        # BalloonFlow custom — organic 적합
        "bf_wave", "bf_spiral", "bf_knot", "bf_woven",
    },
    "motif": {
        "rings", "diamond", "blocks",
        "x_motif", "plus_motif", "t_motif", "i_tetromino", "diamond_check", "rect_grid",
        "stripe",
        "checkerboard", "argyle",
        # BalloonFlow custom — motif 적합
        "bf_dart_silhouette", "bf_hourglass", "bf_border_frame", "bf_corner_L",
        "bf_dartboard", "bf_dot_grid", "bf_diamond_lattice",
    },
    "fractal": {
        # 명시적 fractal 요청에서만 노이즈 패턴 풀림
        "xor_fractal", "sierpinski_carpet", "truchet",
        "rings", "spiral",
    },
    "any": {
        "rings", "rays", "spiral", "diamond", "blocks",
        "kaleidoscope", "concentric_sq", "diamond_check", "x_motif", "plus_motif",
        "t_motif", "i_tetromino", "rect_grid",
        "voronoi", "maze", "wave", "stripe",
        "hex_tile", "brick", "checkerboard", "truchet", "argyle", "chevron",
        "xor_fractal", "sierpinski_carpet",
        # BalloonFlow custom — 모두 허용 (hand-crafted, 노이즈 없음)
        "bf_dart_silhouette", "bf_stripe_triangle", "bf_hourglass",
        "bf_border_frame", "bf_dartboard", "bf_corner_L",
        "bf_triangle_tess", "bf_chevron", "bf_woven",
        "bf_spiral", "bf_diamond_lattice", "bf_wave",
        "bf_knot", "bf_mandala", "bf_flower_mandala",
        "bf_dot_grid", "bf_mosaic",
    },
}


def classify_task_type(user_prompt: str) -> str:
    """user_prompt 키워드로 task 유형 추정. 매칭 없으면 'kaleidoscope' 폴백 (인게임 가장 흔한 의도)."""
    text = (user_prompt or "").lower()
    if not text:
        return "kaleidoscope"
    scores: dict[str, int] = {}
    for ttype, kws in TASK_TYPE_KEYWORDS.items():
        s = sum(1 for kw in kws if kw in text)
        if s:
            scores[ttype] = s
    if not scores:
        return "kaleidoscope"
    # fractal은 explicit 키워드 1+로 충분 (덮어쓰기 방지)
    if "fractal" in scores and scores["fractal"] >= 1:
        return "fractal"
    return max(scores.items(), key=lambda kv: kv[1])[0]


def filter_team_patterns(team_patterns: list[str], task_type: str) -> list[str]:
    """팀 패턴 풀에서 task 유형에 부적합한 것 제거. 모두 잘리면 원본 반환 (안전)."""
    whitelist = TASK_TYPE_PATTERN_WHITELIST.get(task_type, TASK_TYPE_PATTERN_WHITELIST["any"])
    filtered = [p for p in team_patterns if p in whitelist]
    return filtered if filtered else team_patterns


def apply_density_mask(
    cells: list[list[int]], *,
    density_target: float, mask_shape: str = "uniform", seed: int = 0,
) -> tuple[list[list[int]], int]:
    """
    grid의 채워진 셀 비율을 density_target에 맞춤. 초과분은 mask_shape에 따라
    선호 위치를 빈칸(-1)으로 변환.

    mask_shape:
      - "uniform"  : 균등 무작위 산포 — 노이즈/스캐터 만화경
      - "radial"   : 외곽 우선 제거 (중심에 focal 응집) ★ 인게임 puzzle 기본 추천
      - "ring"     : 중심 우선 제거 (도넛/halo 형태)
      - "corners"  : 모서리 우선 제거 (가운데 +자/마름모 응집)

    Returns (cells, removed_count).
    """
    if mask_shape not in MASK_SHAPES:
        mask_shape = "uniform"
    h = len(cells)
    w = len(cells[0]) if h else 0
    total = h * w
    if total == 0:
        return cells, 0

    filled: list[tuple[int, int]] = [
        (r, c) for r in range(h) for c in range(w) if cells[r][c] != -1
    ]
    target_filled = max(0, int(round(total * density_target)))
    excess = len(filled) - target_filled
    if excess <= 0:
        return cells, 0

    cy = (h - 1) / 2.0
    cx = (w - 1) / 2.0
    rng = random.Random(f"{seed}-{mask_shape}")
    eps = 0.001  # 결정성 tiebreak — 같은 score 내에서도 결정성 순서

    def dist_sq(p: tuple[int, int]) -> float:
        return (p[0] - cy) ** 2 + (p[1] - cx) ** 2

    def cheby(p: tuple[int, int]) -> float:
        # max(|r-cy|, |c-cx|) — 모서리/edge 거리. corners 마스크용.
        return max(abs(p[0] - cy), abs(p[1] - cx))

    # 각 셀의 "제거 우선도" score. 높을수록 먼저 제거.
    scored: list[tuple[float, tuple[int, int]]]
    if mask_shape == "uniform":
        scored = [(rng.random(), p) for p in filled]
    elif mask_shape == "radial":
        # 거리 클수록(=외곽일수록) 먼저 제거 → 중심 응집
        scored = [(dist_sq(p) + rng.random() * eps, p) for p in filled]
    elif mask_shape == "ring":
        # 거리 작을수록(=중심일수록) 먼저 제거 → 도넛
        scored = [(-dist_sq(p) + rng.random() * eps, p) for p in filled]
    elif mask_shape == "corners":
        # chebyshev 거리 클수록(=모서리에 가까울수록) 먼저 제거 → +자/마름모 가운데 보존
        scored = [(cheby(p) + rng.random() * eps, p) for p in filled]
    else:
        scored = [(rng.random(), p) for p in filled]

    scored.sort(key=lambda kv: kv[0], reverse=True)
    removed = 0
    for _, (r, c) in scored[:excess]:
        cells[r][c] = -1
        removed += 1
    return cells, removed


def normalize_color_counts_to_10(
    cells: list[list[int]], *, seed: int = 0,
) -> tuple[list[list[int]], dict[int, int], dict[int, int]]:
    """
    각 색상의 셀 카운트를 **10의 배수**로 내림 정규화.
    초과 셀은 결정성 시드로 선택해 빈칸(-1)으로 변경.

    Returns:
      (cells, final_counts, trimmed_counts)
      - cells:          후처리된 grid (in-place 변경됨)
      - final_counts:   {color: count} — 모든 값이 10의 배수
      - trimmed_counts: {color: trimmed_n} — 색상별 빈칸으로 바뀐 셀 수 (0이면 키 없음)

    동작:
      - 각 색상의 셀 위치들을 결정성 셔플 (seed + color 기반)
      - 초과분(count % 10)만큼 앞에서 빈칸으로 demote
      - 색상 카운트가 < 10이면 그 색은 전부 사라짐 (count → 0)
    """
    from collections import defaultdict

    h = len(cells)
    w = len(cells[0]) if h else 0
    color_positions: dict[int, list[tuple[int, int]]] = defaultdict(list)
    for r in range(h):
        for c in range(w):
            v = cells[r][c]
            if v != -1 and v is not None:
                color_positions[int(v)].append((r, c))

    trimmed: dict[int, int] = {}
    final: dict[int, int] = {}
    for color, positions in color_positions.items():
        n = len(positions)
        excess = n % 10
        if excess == 0:
            final[color] = n
            continue
        # 결정성 셔플 (color도 시드에 섞어 색마다 다른 패턴)
        rng = random.Random(seed + color * 1009)
        order = list(positions)
        rng.shuffle(order)
        # 앞에서 excess개를 빈칸으로
        for (r, c) in order[:excess]:
            cells[r][c] = -1
        trimmed[color] = excess
        new_n = n - excess
        if new_n > 0:
            final[color] = new_n
        # else: 색이 사라짐, final dict에서 제외

    return cells, final, trimmed


# BalloonFlow 24색 RGB (level_png_renderer에서 그대로) → hex 변환용
BALLOONFLOW_COLORS_RGB: list[tuple[int, int, int]] = [
    (252, 106, 175), ( 80, 232, 246), (137,  80, 248), (254, 213,  85),
    (115, 254, 102), (253, 161,  76), (255, 255, 255), ( 65,  65,  65),
    (110, 168, 250), ( 57, 174,  46), (252,  94,  94), ( 50, 107, 248),
    ( 58, 165, 139), (231, 167, 250), (183, 199, 251), (106,  74,  48),
    (254, 227, 169), (253, 183, 193), (158,  61,  94), (167, 221, 148),
    ( 89,  46, 126), (220, 120, 129), (217, 217, 231), (111, 114, 127),
]


def bf_index_to_hex(idx: int) -> str:
    """BalloonFlow 색상 인덱스 (0..23) → '#RRGGBB' hex 문자열."""
    r, g, b = BALLOONFLOW_COLORS_RGB[max(0, min(23, idx))]
    return f"#{r:02X}{g:02X}{b:02X}"


@dataclass
class TeamSpec:
    """팀 정의 — 패턴 번들 + 페르소나 메타데이터."""
    team_id: str
    label: str
    philosophy: str          # 사용자 표시용 짧은 설명
    patterns: list[str]      # 패턴 이름 풀
    backend: str             # "hermes_native" | "pattern_api" | "voronoi"
    color: str               # UI 표시용 색
    icon: str


@dataclass
class TeamRequest:
    """팀에 전달할 요청 spec."""
    width: int
    height: int
    palette: list[int]       # BalloonFlow 색상 인덱스
    per_color_count: dict[int, int]   # 각 색의 총 셀 수 (10의 배수, 정보용)
    seed: int
    user_prompt: str = ""    # 사용자 원본 요청 (팀이 패턴 선택에 참조)
    # 모양 제어 — density 1.0 = full board (BalloonFlow 인게임 정책 default).
    # 실제 사용 안 됨 — cowork gen_planned이 plan_counts로 자체 빈칸 비율 결정.
    density: float = 1.0
    mask_shape: str = "uniform"


@dataclass
class TeamResult:
    """팀이 만든 결과 — 격자 + spec 메타."""
    team_id: str
    cells: list[list[int]]                    # height × width, -1=empty, 0..23=BalloonFlow color
    width: int
    height: int
    palette: list[int]                        # 실제 사용된 BalloonFlow 인덱스
    per_color_count: dict[int, int]           # 결과의 색별 카운트 (10의 배수 정규화 후)
    pattern_chosen: str                       # 팀이 고른 패턴 이름
    backend: str
    seed: int
    notes: list[str] = field(default_factory=list)
    trimmed_counts: dict[int, int] = field(default_factory=dict)  # 10배수 맞추려고 빈칸으로 내린 셀 수


# ──────────────────────────────────────────────
# 팀 정의 (4팀)
# ──────────────────────────────────────────────
TEAMS: dict[str, TeamSpec] = {
    "hermes_native": TeamSpec(
        team_id="hermes_native",
        label="Hermes Native",
        philosophy="결정성 정렬 — fundamental domain을 거리/각도/회오리로 정렬해 의미 있는 형태",
        patterns=["rings", "rays", "spiral", "diamond", "blocks"],
        backend="hermes_native",
        color="#6366F1",  # indigo
        icon="🌀",
    ),
    "geometric": TeamSpec(
        team_id="geometric",
        label="Geometric",
        philosophy="정확한 기하학 — 만화경, 동심사각, 다이아 체크, 모티프형",
        patterns=["kaleidoscope", "concentric_sq", "diamond_check", "x_motif", "plus_motif", "t_motif", "i_tetromino", "rect_grid"],
        backend="pattern_api",
        color="#10B981",  # emerald
        icon="🔷",
    ),
    "organic": TeamSpec(
        team_id="organic",
        label="Organic",
        philosophy="유기적 분포 — Voronoi 영역 + 미로 + 파동 + 스트라이프",
        patterns=["voronoi", "maze", "wave", "stripe"],
        backend="pattern_api",  # voronoi는 별도 backend로 분기
        color="#F59E0B",  # amber
        icon="🌊",
    ),
    "tile": TeamSpec(
        team_id="tile",
        label="Tile / Pixel-Art",
        philosophy="반복 타일 — 육각/벽돌/체크/Truchet/아가일/쉐브론",
        patterns=["hex_tile", "brick", "checkerboard", "truchet", "argyle", "chevron", "xor_fractal", "sierpinski_carpet"],
        backend="pattern_api",
        color="#EC4899",  # pink
        icon="🧱",
    ),
    "balloonflow": TeamSpec(
        team_id="balloonflow",
        label="BalloonFlow Custom",
        philosophy="BalloonFlow 디자이너 손작업 패턴 — dart/hourglass/dartboard/mandala/knot 등 게임 의도 반영",
        patterns=[
            "bf_dart_silhouette", "bf_stripe_triangle", "bf_hourglass",
            "bf_border_frame", "bf_dartboard", "bf_corner_L",
            "bf_triangle_tess", "bf_chevron", "bf_woven",
            "bf_spiral", "bf_diamond_lattice", "bf_wave",
            "bf_knot", "bf_mandala", "bf_flower_mandala",
            "bf_dot_grid", "bf_mosaic",
        ],
        backend="custom_patterns",
        color="#06B6D4",  # cyan
        icon="🎯",
    ),
}


# BalloonFlow custom_patterns 함수 매핑 (vendored)
def _bf_patterns_map() -> dict[str, Any]:
    """name → callable. lazy import (모듈 로드 비용 회피)."""
    from pattern_lib import custom_patterns as cp
    return {
        "bf_dart_silhouette":   cp.pattern_dart_silhouette,
        "bf_stripe_triangle":   cp.pattern_stripe_triangle,
        "bf_hourglass":         cp.pattern_hourglass,
        "bf_border_frame":      cp.pattern_border_frame,
        "bf_dartboard":         cp.pattern_dartboard,
        "bf_corner_L":          cp.pattern_corner_L,
        "bf_triangle_tess":     cp.pattern_triangle_tessellation,
        "bf_chevron":           cp.pattern_chevron,
        "bf_woven":             cp.pattern_woven,
        "bf_spiral":            cp.pattern_spiral,
        "bf_diamond_lattice":   cp.pattern_diamond_lattice,
        "bf_wave":              cp.pattern_wave,
        "bf_knot":              cp.pattern_knot,
        "bf_mandala":           cp.pattern_mandala,
        "bf_flower_mandala":    cp.pattern_flower_mandala,
        "bf_dot_grid":          cp.pattern_dot_grid,
        "bf_mosaic":            cp.pattern_mosaic,
    }


def _run_custom_patterns(req: TeamRequest, pattern_choice: str) -> TeamResult:
    """BalloonFlow 디자이너 hand-crafted 패턴 실행."""
    funcs = _bf_patterns_map()
    if pattern_choice not in funcs:
        raise ValueError(f"unknown bf pattern: {pattern_choice}")
    func = funcs[pattern_choice]
    n = len(req.palette)

    # 일부 패턴은 seed/arms/petals 같은 추가 kwargs를 가짐 — inspect로 시그니처 확인
    import inspect
    sig = inspect.signature(func)
    call_kwargs: dict[str, Any] = {}
    if "seed" in sig.parameters:
        call_kwargs["seed"] = req.seed

    grid = func(req.width, req.height, n, **call_kwargs)

    # 결과 grid는 0..n-1 정수 (custom_patterns는 'K' 사용 안 함, 모두 채워짐)
    cells: list[list[int]] = []
    counts: dict[int, int] = {}
    for r in range(req.height):
        row_out: list[int] = []
        for c in range(req.width):
            v = grid[r][c]
            if v is None or v == "K" or v == -1:
                row_out.append(-1)
                continue
            try:
                iv = int(v)
            except (TypeError, ValueError):
                row_out.append(-1)
                continue
            bf = req.palette[iv % n]
            row_out.append(bf)
            counts[bf] = counts.get(bf, 0) + 1
        cells.append(row_out)

    return TeamResult(
        team_id="balloonflow",
        cells=cells,
        width=req.width, height=req.height,
        palette=req.palette,
        per_color_count=counts,
        pattern_chosen=pattern_choice,
        backend="custom_patterns",
        seed=req.seed,
    )


# ──────────────────────────────────────────────
# Backend: hermes_native — 기존 level_grid_generator 사용
# ──────────────────────────────────────────────
def _run_hermes_native(req: TeamRequest, pattern_choice: Optional[str] = None) -> TeamResult:
    from level_grid_generator import GridSpec, generate_grid, EXPANSION as EXP

    pattern = pattern_choice or "rings"
    # symmetry 기본 — 4-fold-rot이 만화경 느낌. width==height 면 회전 가능
    symmetry = "4-fold-rot" if req.width == req.height else "4-fold"
    # per_color_count 보정 — symmetry expansion에 호환되는 10배수 단위로 라운드
    # rules: 10의 배수 + expansion의 배수 → unit = lcm(10, expansion)
    expansion = EXP.get(symmetry, 1)
    unit = (10 * expansion) // math.gcd(10, expansion)
    pcc: dict[int, int] = {}
    for c, n in req.per_color_count.items():
        pcc[c] = max(0, (n // unit) * unit)
    # 모든 색이 0이면 최소 1색 fallback
    if sum(pcc.values()) == 0 and req.palette:
        pcc = {req.palette[0]: unit}

    spec = GridSpec(
        width=req.width, height=req.height,
        symmetry=symmetry, palette=req.palette,
        per_color_count=pcc, seed=req.seed,
        name=f"hermes_native_{pattern}",
        pattern=pattern,
    )
    result = generate_grid(spec)
    cells = result.cells
    counts: dict[int, int] = {}
    for row in cells:
        for v in row:
            if v != -1:
                counts[v] = counts.get(v, 0) + 1
    return TeamResult(
        team_id="hermes_native",
        cells=cells,
        width=req.width, height=req.height,
        palette=req.palette,
        per_color_count=counts,
        pattern_chosen=pattern,
        backend="hermes_native",
        seed=req.seed,
        notes=[f"symmetry={symmetry}"] + result.notes,
    )


# ──────────────────────────────────────────────
# Backend: pattern_api — generate_pattern → grid
# ──────────────────────────────────────────────
def _run_pattern_api(req: TeamRequest, pattern_choice: str) -> TeamResult:
    """
    cowork의 **production process_level** 그대로 호출:
      9개 변형 (P, A, B, C, D, E, F, G, H) 생성 → score_grid 채점 →
      rank_key로 best 선택 (우선순위: is_10_mult > edge_violation X >
      _P clean (sym 99%+, scatter 0) > bg_zero > composite).

    이 워크플로우가 cowork goodcase 수준 출력의 핵심:
      - scatter penalty: 흩어진 단일 셀 빈칸은 후순위
      - bg_zero 우선: 빈칸 0개 변형이 있으면 그거 채택 (구멍 X)
      - sym 99% + scatter 0의 깨끗한 _P 우선
    """
    import pattern_lib  # noqa: F401  --  sys.path 등록
    from variant_pipeline import process_level  # type: ignore
    from pixel_pattern_api import _hex_to_rgb  # type: ignore

    n = len(req.palette)
    colors_hex = [bf_index_to_hex(c) for c in req.palette]

    # cowork process_level entry 형식
    entry = {
        "_meta": {"level": req.seed},  # 라벨용
        "pattern": pattern_choice,
        "width": req.width,
        "height": req.height,
        "colors": colors_hex,
        "seed": req.seed,
    }

    notes: list[str] = []
    rgb_grid: list[list[Any]] = []
    chosen_variant = "?"
    try:
        result = process_level(entry, save_all_variants=False, extended_seeds=10)
        if result is not None:
            rgb_grid = result["chosen_grid"]
            chosen_variant = result["chosen_variant"]
            sc = result["chosen_score"]
            notes.append(
                f"채택: _{chosen_variant} · 10x={sc.get('is_10_mult')} · "
                f"sym={sc.get('sym_best', 0):.0%} · scatter={sc.get('scatter', 0)} · "
                f"bg={sc.get('bg_ratio', 0):.0%} · composite={sc.get('composite', 0):.0f}"
            )
    except Exception as e:
        log.exception("[process_level %s] failed: %s", pattern_choice, e)

    # process_level 실패 시 gen_planned 폴백
    if not rgb_grid:
        from variant_pipeline import gen_planned, _grid_to_rgb  # type: ignore
        try:
            int_grid = gen_planned(pattern_choice, req.width, req.height, n, colors_hex, req.seed)
            palette_rgb_full = [(*_hex_to_rgb(h), 255) for h in colors_hex]
            rgb_grid = _grid_to_rgb(int_grid, palette_rgb_full)
            notes.append("폴백: gen_planned 직접 호출 (process_level 실패)")
            chosen_variant = "P-fallback"
        except Exception:
            log.exception("[fallback %s] failed", pattern_choice)
            return TeamResult(
                team_id="",
                cells=[[-1] * req.width for _ in range(req.height)],
                width=req.width, height=req.height,
                palette=req.palette, per_color_count={},
                pattern_chosen=pattern_choice, backend="pattern_api",
                seed=req.seed,
                notes=[f"❌ 모두 실패: {pattern_choice}"],
            )

    # RGBA 튜플 → BalloonFlow 인덱스 변환
    # palette_rgb[i] (alpha=255) ↔ req.palette[i] BalloonFlow index
    rgb_to_bf: dict[tuple, int] = {}
    for i, hexstr in enumerate(colors_hex):
        rgb3 = _hex_to_rgb(hexstr)
        rgba = (rgb3[0], rgb3[1], rgb3[2], 255)
        rgb_to_bf[rgba] = req.palette[i]

    cells: list[list[int]] = []
    counts: dict[int, int] = {}
    for r in range(req.height):
        row_out: list[int] = []
        for c in range(req.width):
            v = rgb_grid[r][c] if r < len(rgb_grid) and c < len(rgb_grid[r]) else None
            if v is None:
                row_out.append(-1)
                continue
            if isinstance(v, tuple):
                # 배경 (alpha=0) → -1
                if len(v) >= 4 and v[3] == 0:
                    row_out.append(-1)
                    continue
                bf = rgb_to_bf.get(v)
                if bf is None and len(v) >= 3:
                    # alpha 무시하고 RGB만 매칭
                    rgba_lookup = (v[0], v[1], v[2], 255)
                    bf = rgb_to_bf.get(rgba_lookup)
                if bf is None:
                    row_out.append(-1)
                else:
                    row_out.append(bf)
                    counts[bf] = counts.get(bf, 0) + 1
            elif v == "K" or v == -1:
                row_out.append(-1)
            else:
                try:
                    iv = int(v)
                    bf = req.palette[iv % n]
                    row_out.append(bf)
                    counts[bf] = counts.get(bf, 0) + 1
                except (TypeError, ValueError):
                    row_out.append(-1)
        cells.append(row_out)

    return TeamResult(
        team_id="",  # 호출자가 채움
        cells=cells,
        width=req.width, height=req.height,
        palette=req.palette,
        per_color_count=counts,
        pattern_chosen=f"{pattern_choice} _{chosen_variant}",
        backend="pattern_api",
        seed=req.seed,
        notes=notes,
    )


# ──────────────────────────────────────────────
# Backend: voronoi — 별도 워크플로
# ──────────────────────────────────────────────
def _run_voronoi(req: TeamRequest) -> TeamResult:
    from pattern_lib.voronoi_generator import (
        generate_voronoi, apply_coloring, refine, balance_x10 as voronoi_balance,
        FILL as VORONOI_FILL,
    )

    # 색 수에 비례한 seed 개수
    n_seeds = max(8, len(req.palette) * 5)
    cell_id, seeds = generate_voronoi(
        req.width, req.height, n_seeds=n_seeds,
        min_dist=2, seed_val=req.seed,
    )
    grid = apply_coloring(cell_id, seeds, req.width, req.height)
    grid = refine(grid, req.width, req.height, verbose=False)
    grid = voronoi_balance(grid, req.width, req.height, verbose=False)

    # voronoi grid 셀 값은 'a'/'b'/'c'/'d'/'e' 같은 char (FILL=['a','b','c','d','e']) + 'K'(blank).
    # 이걸 req.palette[VORONOI_FILL.index(ch)] 로 BalloonFlow 인덱스 매핑.
    palette_n = len(req.palette)
    char_to_bf: dict[str, int] = {}
    for i, ch in enumerate(VORONOI_FILL):
        char_to_bf[ch] = req.palette[i % palette_n]

    cells: list[list[int]] = []
    counts: dict[int, int] = {}
    for r in range(req.height):
        row_out: list[int] = []
        for c in range(req.width):
            v = grid[r][c]
            if v == "K" or v == -1 or v is None:
                row_out.append(-1)
                continue
            if isinstance(v, str) and v in char_to_bf:
                bf = char_to_bf[v]
                row_out.append(bf)
                counts[bf] = counts.get(bf, 0) + 1
            elif isinstance(v, int) and 0 <= v < palette_n:
                bf = req.palette[v]
                row_out.append(bf)
                counts[bf] = counts.get(bf, 0) + 1
            else:
                row_out.append(-1)
        cells.append(row_out)

    return TeamResult(
        team_id="organic",
        cells=cells,
        width=req.width, height=req.height,
        palette=req.palette,
        per_color_count=counts,
        pattern_chosen="voronoi",
        backend="voronoi",
        seed=req.seed,
    )


# ──────────────────────────────────────────────
# Pattern selection — 팀이 자기 번들에서 best 고르기
# ──────────────────────────────────────────────
def _select_pattern_for_team(team: TeamSpec, req: TeamRequest) -> str:
    """
    팀 내 패턴 선택 — 우선순위:
      1. user_prompt keyword 매칭 (강한 신호)
      2. 누적 별점 가중치 (Bayesian-smoothed mean) — 약한 패턴은 후순위
      3. 시드 기반 결정성 폴백
    """
    text = (req.user_prompt or "").lower()

    # Q-B: task 유형으로 패턴 풀 필터링 (sierpinski/xor 등 부적합 패턴 차단)
    task_type = classify_task_type(text)
    allowed_patterns = filter_team_patterns(team.patterns, task_type)
    log.info("[team:%s] task_type=%s, allowed=%s",
             team.team_id, task_type, allowed_patterns)

    keyword_map: dict[str, list[str]] = {
        # hermes_native
        "rings":         ["동심", "원형", "그라데이션", "ring", "concentric"],
        "rays":          ["방사", "별", "ray", "sunburst", "만화경"],
        "spiral":        ["회오리", "spiral", "회전 흐름"],
        "diamond":       ["마름모", "diamond"],
        "blocks":        ["블록", "block 모자이크"],
        # geometric
        "kaleidoscope":  ["만화경", "kaleidoscope"],
        "concentric_sq": ["동심사각", "concentric square", "사각 동심"],
        "diamond_check": ["다이아 체크", "diamond check"],
        "x_motif":       ["엑스", "x", "교차"],
        "plus_motif":    ["플러스", "plus", "십자"],
        "t_motif":       ["t자", "t motif"],
        "i_tetromino":   ["i형", "tetris", "테트리스"],
        "rect_grid":     ["사각 격자", "rect grid"],
        # organic
        "voronoi":       ["voronoi", "보로노이", "셀 영역", "유기적 영역"],
        "maze":          ["미로", "maze", "통로"],
        "wave":          ["파동", "wave", "물결"],
        "stripe":        ["줄무늬", "스트라이프", "stripe"],
        # tile
        "hex_tile":      ["육각", "hex", "honeycomb"],
        "brick":         ["벽돌", "brick"],
        "checkerboard":  ["체크판", "checkerboard"],
        "truchet":       ["truchet"],
        "argyle":        ["아가일", "argyle"],
        "chevron":       ["쉐브론", "chevron", "지그재그"],
        "xor_fractal":   ["xor", "fractal", "프랙탈"],
        "sierpinski_carpet": ["시에르핀", "sierpinski", "카페트"],
    }

    # 1단계: 키워드 매칭 (필터링된 풀 안에서)
    kw_scores: dict[str, int] = {}
    for p in allowed_patterns:
        kws = keyword_map.get(p, [])
        s = sum(1 for kw in kws if kw in text)
        if s:
            kw_scores[p] = s
    if kw_scores:
        return max(kw_scores.items(), key=lambda kv: kv[1])[0]

    # 2단계: 누적 별점 가중치 — Bayesian smoothing (필터링된 풀 안에서)
    perf = _load_pattern_performance(team.team_id, allowed_patterns)
    if perf:
        rng = random.Random(f"{req.seed}-{team.team_id}-perf")
        ranked = sorted(
            allowed_patterns,
            key=lambda p: (perf.get(p, 3.0), rng.random()),
            reverse=True,
        )
        top_half = ranked[: max(1, len(ranked) // 2)]
        return rng.choice(top_half)

    # 3단계: 시드 폴백 (필터링된 풀 안에서)
    rng = random.Random(f"{req.seed}-{team.team_id}")
    return rng.choice(allowed_patterns)


def _load_pattern_performance(
    team_id: str, patterns: list[str], min_samples: int = 2,
) -> dict[str, float]:
    """
    hermes_design_team_scores에서 (team_id, pattern) 별 평균 별점 (1~5)을 반환.
    Bayesian prior = 3.0, prior 표본 2개 (작은 표본일 때 평균이 극단으로 가지 않도록).
    표본이 0건이거나 DB 미가용이면 빈 dict.
    """
    try:
        import os
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            return {}
        db_name = os.environ.get("MONGODB_DB", "aigame")
        db = MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    except Exception:
        return {}

    out: dict[str, float] = {}
    try:
        agg = db["hermes_design_team_scores"].aggregate([
            {"$match": {"team_id": team_id, "pattern_chosen": {"$in": patterns}}},
            {"$group": {
                "_id": "$pattern_chosen",
                "avg": {"$avg": "$score"},
                "n": {"$sum": 1},
            }},
        ])
        prior, prior_n = 3.0, 2.0
        for row in agg:
            pname = row.get("_id")
            n = float(row.get("n") or 0)
            avg = float(row.get("avg") or 3.0)
            if n < 1:
                continue
            # smoothed = (prior*prior_n + avg*n) / (prior_n + n)
            smoothed = (prior * prior_n + avg * n) / (prior_n + n)
            out[pname] = smoothed
    except Exception:
        log.exception("_load_pattern_performance failed")
        return {}
    return out


# ──────────────────────────────────────────────
# 통일 엔트리포인트
# ──────────────────────────────────────────────
def run_team(team_id: str, req: TeamRequest) -> TeamResult:
    """
    한 팀이 한 번 작업 — 자기 번들에서 패턴 선택 + 격자 생성.
    실패 시 RuntimeError. 호출자가 catch하고 다른 팀에 영향 없게 처리.
    """
    if team_id not in TEAMS:
        raise ValueError(f"unknown team_id: {team_id}")
    team = TEAMS[team_id]
    pattern = _select_pattern_for_team(team, req)
    log.info("[team:%s] selected pattern=%s", team_id, pattern)

    if team.backend == "hermes_native":
        result = _run_hermes_native(req, pattern_choice=pattern)
    elif team.backend == "voronoi":
        result = _run_voronoi(req)
    elif team.backend == "pattern_api":
        # organic 팀의 voronoi는 voronoi backend로 분기
        if pattern == "voronoi":
            result = _run_voronoi(req)
        else:
            result = _run_pattern_api(req, pattern_choice=pattern)
    elif team.backend == "custom_patterns":
        result = _run_custom_patterns(req, pattern_choice=pattern)
    else:
        raise ValueError(f"unknown backend: {team.backend}")

    result.team_id = team_id

    # cowork 본 파이프라인 (gen_planned, custom_patterns)은 자체적으로 10-mult 사전계획
    # + 봇 워크플로우로 품질 보장. 우리쪽 후처리 mask/balance 추가하면 오히려 품질 저하.
    # → 후처리 안 함. trimmed_counts는 빈 dict.
    # 단, 색상 카운트가 10배수가 아닌 경미한 잔여분만 cleanup (cowork 내부에서 거의 떨어짐).
    counts: dict[int, int] = {}
    for row in result.cells:
        for v in row:
            if v != -1 and v is not None:
                counts[int(v)] = counts.get(int(v), 0) + 1
    # 10배수에서 살짝 어긋난 색은 nearest 10으로 trim (cowork이 거의 다 처리하므로 여기는 거의 동작 안함)
    has_misalign = any(n % 10 != 0 for n in counts.values())
    if has_misalign:
        result.cells, result.per_color_count, result.trimmed_counts = normalize_color_counts_to_10(
            result.cells, seed=req.seed,
        )
        if result.trimmed_counts:
            trim_str = ", ".join(f"c{k}:{v}" for k, v in sorted(result.trimmed_counts.items()))
            result.notes.append(f"잔여 10배수 trim: [{trim_str}]")
    else:
        result.per_color_count = counts

    return result


# ──────────────────────────────────────────────
# self-test
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import os, sys
    from pathlib import Path

    out_dir = Path(os.environ.get("TEAMS_TEST_OUT", "/tmp/teams_test"))
    out_dir.mkdir(parents=True, exist_ok=True)

    req = TeamRequest(
        width=25, height=25,
        palette=[0, 2, 13, 17, 21],  # 분홍·보라 톤 5색
        per_color_count={0: 40, 2: 40, 13: 60, 17: 40, 21: 20},
        seed=42,
        user_prompt="만화경 25x25 분홍 보라 톤",
    )

    from level_png_renderer import render_grid_to_png

    for tid in TEAMS.keys():
        try:
            res = run_team(tid, req)
            png = render_grid_to_png(
                res.cells, cell_size_px=22,
                title=f"{tid} · {res.pattern_chosen} · seed={res.seed}",
            )
            path = out_dir / f"team_{tid}.png"
            path.write_bytes(png)
            counts_str = ", ".join(f"c{k}={v}" for k, v in sorted(res.per_color_count.items()))
            print(f"✓ {tid:14s} pattern={res.pattern_chosen:18s} counts={counts_str}")
        except Exception as e:
            print(f"✗ {tid:14s} FAILED: {type(e).__name__}: {e}")

    print(f"\n✅ outputs in {out_dir}")
