"""
BalloonFlow 기믹 배치 — generator 순수함수 (프로토타입 추출)
==========================================================

출처: `_bl_lv34_v222_wooden_4variants.py` (Lv34·Wooden 하드코딩 프로토타입)을
완성보드 포맷을 입력받는 **범용 순수함수**로 추출한 것.

핵심 공개 API (pixelforge-web API가 래핑하는 코어):
  - generate_variants(board, gimmick_type) -> [4 variants]   # 4안 큐레이션
  - apply_variant(board, variant, gimmick_type) -> new_board # 택1 → 병합(기믹 배치)
  - validate_color_darts(grid, instances) -> {color_darts,total,violations}

board 포맷 (= pixelforge_field_complete_jobs.results[] 완성보드):
  {
    "field_rows": H, "field_columns": W,
    "balloons": [{"row": r, "col": c, "color": 1-28, "life": 1}, ...],
    "gimmicks": [ ... ]   # (선택) 기존 배치된 기믹. apply_variant가 여기에 누적
  }

좌표계: balloons/instances 모두 grid-index (col=x, row=y). 0-indexed.
color_darts 규칙(필드완성 §1.1): color_darts[c] = (덮이지 않은 색 c 표준풍선 수)
  + (색 c로 배치된 기믹 hp 합). 각 표준풍선 = 1 dart. 10의 배수 필수.

이 모듈은 **stdlib만** 의존 (json, collections). pymongo/Pillow 불필요.
"""
from __future__ import annotations

from collections import Counter, deque
from typing import Any


# ──────────────────────────────────────────────────────────
# 기믹별 설정 (프로토타입 PF_WOODEN_DIST / WOODEN_HP_BY_SIZE 추출)
# ──────────────────────────────────────────────────────────
# Wooden Board — PF Hard Pixel 사이즈 빈출 분포
WOODEN_SIZE_DIST = {
    (2, 2): 0.19, (4, 1): 0.15, (2, 4): 0.15, (3, 1): 0.10, (4, 4): 0.09,
    (1, 3): 0.08, (3, 3): 0.07, (1, 1): 0.006, (1, 2): 0.04, (2, 1): 0.04,
    (1, 4): 0.04, (3, 4): 0.03, (4, 3): 0.03, (5, 5): 0.01, (6, 6): 0.01,
    (5, 1): 0.005, (1, 5): 0.005, (6, 1): 0.005, (1, 6): 0.005,
}
# Wooden 사이즈(cells)별 HP 분포 (cap 100, cell당 비선형). 결정론적 = mode 선택.
WOODEN_HP_BY_SIZE = {
    1:  [(5, 0.30), (6, 0.25), (7, 0.20), (10, 0.25)],
    3:  [(10, 0.30), (12, 0.30), (15, 0.25), (18, 0.15)],
    4:  [(15, 0.30), (18, 0.30), (21, 0.25), (24, 0.15)],
    5:  [(15, 0.30), (18, 0.30), (20, 0.25), (25, 0.15)],
    6:  [(18, 0.30), (20, 0.30), (24, 0.25), (30, 0.15)],
    8:  [(20, 0.30), (24, 0.30), (28, 0.20), (32, 0.20)],
    9:  [(25, 0.30), (30, 0.30), (35, 0.25), (40, 0.15)],
    12: [(30, 0.25), (35, 0.30), (40, 0.25), (50, 0.20)],
    16: [(40, 0.30), (50, 0.30), (60, 0.25), (70, 0.15)],
    25: [(50, 0.30), (60, 0.30), (70, 0.25), (80, 0.15)],
    36: [(50, 0.30), (70, 0.30), (100, 0.40)],
}

# 기믹별 설정 레지스트리. Wooden만 완전 구현, 나머지는 후속 (STEP 5-C 큐레이션 패턴).
GIMMICK_CONFIG: dict[str, dict[str, Any]] = {
    "Wooden": {
        "size_dist": WOODEN_SIZE_DIST,
        "hp_by_size": WOODEN_HP_BY_SIZE,
        "hp_cap": 100,
        # STEP 5-C: Wooden 4안 (intent, target 선택자)
        "strategies": [
            {"name": "1안.큰단일",   "intent": "cover_area",       "target": "primary"},
            {"name": "2안.가로막대", "intent": "block_horizontal", "target": "horizontal"},
            {"name": "3안.세로막대", "intent": "block_vertical",   "target": "vertical"},
            {"name": "4안.큰+중간",  "intent": "mixed_focus",      "target": "primary"},
        ],
    },
    # Hidden Balloon (서프라이즈 풍선) — 1×1 다수. 표준풍선을 같은색 Hidden으로 대체.
    # color_darts 순변화 0 (−1 표준 +1 기믹, 동색) → 항상 10배수 유지. STEP 5-C.2.
    "Hidden": {
        "hp": 1,
        "out_kind": "balloon",       # balloons[] gimmickType="Hidden" (boardGimmicks 아님)
        "darts_neutral": True,        # 10배수 무관 (대체)
        "density": 0.10,              # 모티프 대비 산재 비율
        "strategies": [
            {"name": "1안.모티프산재",  "intent": "distribute_inside_motif", "target": "motif"},
            {"name": "2안.영역집중",   "intent": "concentrate_region",     "target": "primary"},
            {"name": "3안.외곽띠",     "intent": "distribute_edge",        "target": "motif"},
            {"name": "4안.패턴정렬",   "intent": "distribute_pattern",     "target": "motif"},
        ],
    },
    # Iron Wall (벽) — 오버레이, darts 중립(색·HP 없음), walls[] 출력. STEP 5-C.2 + 6-B.
    "IronWall": {
        "removes": False, "darts_mode": "none", "out_kind": "wall",
        "strategies": [
            {"name": "1안.외곽라인",  "intent": "wall_outline",     "target": "motif"},
            {"name": "2안.정사각외곽", "intent": "wall_squares_edge", "target": "motif"},
            {"name": "3안.상단편중",  "intent": "wall_top_band",     "target": "frame"},
            {"name": "4안.혼합",     "intent": "wall_mixed",        "target": "motif"},
        ],
    },
    # Ice (얼음) — 오버레이, darts 중립, pixelIceBlocks[] 출력. BlockSize 2~5.
    "Ice": {
        "removes": False, "darts_mode": "none", "out_kind": "ice", "health": 600,
        "strategies": [
            {"name": "1안.큰영역",   "intent": "ice_single_large", "target": "primary"},
            {"name": "2안.중간N개",  "intent": "ice_multi_medium", "target": "primary"},
            {"name": "3안.작은분산",  "intent": "ice_multi_small",  "target": "motif"},
            {"name": "4안.혼합",     "intent": "ice_mixed",        "target": "primary"},
        ],
    },
    # Barricade (핀) — 오버레이(풍선 가림), +Count darts(Material), gates[] 출력. 일직선만.
    "Barricade": {
        "removes": False, "darts_mode": "count", "out_kind": "gate", "hp_cap": 240,
        "default_count": 50,
        "strategies": [
            {"name": "1안.가로한줄",  "intent": "barricade_horizontal", "target": "primary"},
            {"name": "2안.세로한줄",  "intent": "barricade_vertical",   "target": "primary"},
            {"name": "3안.L자",      "intent": "barricade_L",          "target": "primary"},
            {"name": "4안.액자",     "intent": "barricade_frame",      "target": "primary"},
        ],
    },
    # Target Box (피냐타 박스) — 오버레이, +egg Count darts, eggBoxes[] 출력. 박스+알.
    "TargetBox": {
        "removes": False, "darts_mode": "count", "out_kind": "eggBox", "hp_cap": 40,
        "default_count": 20,
        "strategies": [
            {"name": "1안.큰박스단일", "intent": "box_single_large", "target": "primary"},
            {"name": "2안.중간박스N",  "intent": "box_line",         "target": "primary"},
            {"name": "3안.다양분산",   "intent": "box_multiple",     "target": "primary"},
            {"name": "4안.큰+작은",    "intent": "box_mixed",        "target": "primary"},
        ],
    },
    # TODO(후속): "Snake" (곡선 기하 — 명세 intent만, 알고리즘 미제공)
}

SUPPORTED_GIMMICKS = [g for g, c in GIMMICK_CONFIG.items() if c.get("strategies")]


# ──────────────────────────────────────────────────────────
# board → grid / 영역(region) 인식
# ──────────────────────────────────────────────────────────
def board_to_grid(board: dict) -> tuple[dict[tuple[int, int], int], int, int, int]:
    """완성보드 → grid[(col,row)]=color, W, H, bg(최빈색)."""
    W = int(board["field_columns"])
    H = int(board["field_rows"])
    grid: dict[tuple[int, int], int] = {}
    for b in board["balloons"]:
        grid[(int(b["col"]), int(b["row"]))] = int(b["color"])
    bg = Counter(grid.values()).most_common(1)[0][0] if grid else 0
    return grid, W, H, bg


def board_life_map(board: dict) -> dict:
    """{(col,row): life} — 표준풍선 dart 가중치(=life). field_complete 정합(다트=life 합)."""
    return {(int(b["col"]), int(b["row"])): int(b.get("life", 1)) for b in board.get("balloons", [])}


def _bfs_components(cells: set[tuple[int, int]]) -> list[set[tuple[int, int]]]:
    """4-이웃 연결 컴포넌트 분해."""
    cells = set(cells)
    comps: list[set[tuple[int, int]]] = []
    while cells:
        s = next(iter(cells))
        comp: set[tuple[int, int]] = set()
        q = deque([s])
        while q:
            c = q.popleft()
            if c in comp:
                continue
            comp.add(c)
            x, y = c
            for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if nb in cells and nb not in comp:
                    q.append(nb)
        cells -= comp
        comps.append(comp)
    return comps


def _region_of(cells: set[tuple[int, int]], color: int) -> dict:
    xs = [c[0] for c in cells]
    ys = [c[1] for c in cells]
    return {
        "cells": cells,
        "color": color,
        "size": len(cells),
        "bbox": (min(xs), min(ys), max(xs), max(ys)),
        "bbox_w": max(xs) - min(xs) + 1,
        "bbox_h": max(ys) - min(ys) + 1,
        "center": (sum(xs) / len(xs), sum(ys) / len(ys)),
    }


def detect_regions(grid: dict, bg: int, min_size: int = 6) -> list[dict]:
    """
    배경(bg)을 제외한 단색 컴포넌트들을 영역 후보로 추출 (size >= min_size).
    프로토타입의 하드코딩(노랑 c3 몸통 / 하늘 c8 상단)을 일반화한 것.
    """
    by_color: dict[int, set] = {}
    for cell, col in grid.items():
        if col == bg:
            continue
        by_color.setdefault(col, set()).add(cell)
    regions: list[dict] = []
    for col, cells in by_color.items():
        for comp in _bfs_components(cells):
            if len(comp) >= min_size:
                regions.append(_region_of(comp, col))
    regions.sort(key=lambda r: -r["size"])
    return regions


def _pick_target(regions: list[dict], kind: str) -> dict | None:
    """
    전략별 target 영역 선택자. vision 라벨(motif_body 등)이 있으면 의미 우선,
    없으면 휴리스틱(면적·bbox). is_empty(frame) 영역은 채워진 영역 우선 후 fallback.
    """
    if not regions:
        return None
    filled = [r for r in regions if not r.get("is_empty")]
    pool = filled or regions
    labeled = {r.get("label"): r for r in pool if r.get("label")}
    if kind == "primary":
        for lab in ("motif_body", "motif_head"):  # vision: 몸통/머리 우선
            if lab in labeled:
                return labeled[lab]
        # 휴리스틱: 면적 × compactness (납작 밴드 회피)
        return max(pool, key=lambda r: r["size"] * (min(r["bbox_w"], r["bbox_h"]) / max(r["bbox_w"], r["bbox_h"])))
    if kind == "horizontal":   # 가로 막대 = 너비 우선
        return max(pool, key=lambda r: (r["bbox_w"], r["size"]))
    if kind == "vertical":     # 세로 막대 = 높이 우선
        return max(pool, key=lambda r: (r["bbox_h"], r["size"]))
    return pool[0]


# ──────────────────────────────────────────────────────────
# 사이즈 / HP 결정 (프로토타입 select_size / pick_hp 추출)
# ──────────────────────────────────────────────────────────
def select_size(intent: str, region: dict, W: int, H: int, size_dist: dict) -> list[dict]:
    """STEP 4-C.4 컨텍스트 의존 사이즈 결정. 점수 내림차순 후보 리스트."""
    rw, rh = region["bbox_w"], region["bbox_h"]
    cands: list[dict] = []
    for (sw, sh), pf in size_dist.items():
        if sw > rw or sh > rh:
            continue
        intent_s = 0.0
        if intent == "block_horizontal":
            intent_s = 1.0 if (W % sw == 0 and sh <= 2) else 0.3
        elif intent == "block_vertical":
            intent_s = 1.0 if (H % sh == 0 and sw <= 2) else 0.3
        elif intent in ("cover_area", "mixed_focus"):
            fit = 1.0 - abs(sw * sh - rw * rh * 0.5) / max(rw * rh, 1)
            intent_s = max(0.0, fit)
        ratio = 0.0
        if sw / sh >= 2 and rw / rh >= 2:
            ratio = 0.5
        elif sw / sh <= 0.5 and rw / rh <= 0.5:
            ratio = 0.5
        elif sw == sh and abs(rw - rh) <= 2:
            ratio = 0.5
        if intent in ("cover_area", "mixed_focus"):
            score = 0.1 * pf + 0.7 * intent_s + 0.2 * ratio
        elif intent in ("block_horizontal", "block_vertical"):
            score = 0.2 * pf + 0.6 * intent_s + 0.2 * ratio
        else:
            score = 0.3 * pf + 0.5 * intent_s + 0.2 * ratio
        cands.append({"size": (sw, sh), "score": score, "pf": pf, "intent": intent_s, "ratio": ratio})
    cands.sort(key=lambda c: -c["score"])
    return cands


def pick_hp(size_cells: int, hp_by_size: dict, cap: int) -> int:
    """사이즈(cells)별 HP 결정 — 결정론적(mode). cap 강제."""
    if size_cells in hp_by_size:
        dist = hp_by_size[size_cells]
        return min(cap, max(dist, key=lambda x: x[1])[0])
    nearest = min(hp_by_size.keys(), key=lambda k: abs(k - size_cells))
    dist = hp_by_size[nearest]
    avg = sum(v * w for v, w in dist)
    return min(cap, int(avg * (size_cells / nearest) ** 0.5))


# ──────────────────────────────────────────────────────────
# 검증 (프로토타입 validate 추출) — color_darts 10배수
# ──────────────────────────────────────────────────────────
def _covered_cells(instances: list[dict]) -> set[tuple[int, int]]:
    covered: set[tuple[int, int]] = set()
    for inst in instances:
        sw, sh = inst["size"]
        ax, ay = inst["pos"]
        for dx in range(sw):
            for dy in range(sh):
                covered.add((ax + dx, ay + dy))
    return covered


def _gimmick_rules(gimmick_type: str | None) -> tuple[bool, str]:
    """(removes, darts_mode) — 기믹별 풍선 제거/darts 규칙.
    removes: 덮은 셀의 표준풍선 제거(대체) 여부. False=오버레이(풍선 그대로).
    darts_mode: 'hp'(Wooden/Hidden) | 'count'(Barricade/TargetBox/Snake) | 'none'(IronWall/Ice).
    """
    cfg = GIMMICK_CONFIG.get(gimmick_type or "Wooden", {})
    return cfg.get("removes", True), cfg.get("darts_mode", "hp")


def validate_color_darts(grid: dict, instances: list[dict],
                         removes: bool = True, darts_mode: str = "hp",
                         life_map: dict | None = None) -> dict:
    """
    color_darts[c] = (덮이지 않은 색 c 표준풍선 dart) + (색 c 기믹 darts).
    - 표준풍선 dart = life (life_map 제공 시), 없으면 1 (life=1 보드/골든).
    - removes=True(Wooden/Hidden): 덮은 셀 표준풍선 제거. False(오버레이): 풍선 그대로.
    - darts_mode 'hp'/'count': inst.hp 를 색 darts에 가산. 'none'(IronWall/Ice): 가산 안 함(중립).
    위반 = 10의 배수가 아닌 색.
    """
    covered = _covered_cells(instances) if removes else set()
    bcount: Counter = Counter()
    for cell, col in grid.items():
        if cell in covered:
            continue
        bcount[col] += (life_map.get(cell, 1) if life_map else 1)
    glife: Counter = Counter()
    if darts_mode in ("hp", "count"):
        for inst in instances:
            if inst.get("color") is not None:
                glife[inst["color"]] += inst.get("hp", 0)
    color_darts: dict[int, int] = {}
    for c in set(bcount) | set(glife):
        color_darts[c] = bcount.get(c, 0) + glife.get(c, 0)
    total = sum(color_darts.values())
    violations = [[c, n, n % 10] for c, n in sorted(color_darts.items()) if n % 10 != 0]
    return {
        "color_darts": dict(sorted(color_darts.items())),
        "total": total,
        "violations": violations,
    }


# ──────────────────────────────────────────────────────────
# 공개 API ①: 4안 생성
# ──────────────────────────────────────────────────────────
def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _motif_cells(grid: dict, bg: int) -> list:
    return [c for c, col in grid.items() if col != bg]


def _sample_even(cells: list, n: int) -> list:
    """공간적으로 고르게 n개 샘플 (정렬 후 등간격 인덱스)."""
    cells = sorted(cells)
    if n <= 0:
        return []
    if n >= len(cells):
        return cells
    step = len(cells) / n
    return [cells[int(i * step)] for i in range(n)]


def _edge_cells(grid: dict, bg: int) -> list:
    """모티프 셀 중 배경/보드밖과 인접한 외곽 셀."""
    motif = set(c for c, col in grid.items() if col != bg)
    edge = []
    for (x, y) in motif:
        for nb in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if grid.get(nb, bg) == bg:
                edge.append((x, y))
                break
    return edge


def _hidden_instances(cells: list, grid: dict, life_map: dict | None = None) -> list[dict]:
    """1×1 Hidden — color=하부 셀 색, hp=하부 life (대체 → darts 완전 중립)."""
    return [{"size": (1, 1), "pos": (x, y),
             "hp": (life_map.get((x, y), 1) if life_map else 1), "color": grid[(x, y)]}
            for (x, y) in cells]


def _build_instances(strategy: dict, regions: list[dict], grid: dict, W: int, H: int,
                     cfg: dict, bg: int = 0, life_map: dict | None = None) -> list[dict]:
    intent = strategy["intent"]

    # ── Hidden Balloon (1×1 산재, 표준풍선 대체) ──────────────
    if intent == "distribute_inside_motif":
        motif = _motif_cells(grid, bg)
        n = max(3, int(len(motif) * cfg.get("density", 0.10)))
        return _hidden_instances(_sample_even(motif, n), grid, life_map)
    if intent == "concentrate_region":
        region = _pick_target(regions, strategy["target"])
        if region is None:
            return []
        n = max(3, int(len(region["cells"]) * 0.30))
        return _hidden_instances(_sample_even(list(region["cells"]), n), grid, life_map)
    if intent == "distribute_edge":
        edge = _edge_cells(grid, bg)
        n = max(3, int(len(edge) * 0.40))
        return _hidden_instances(_sample_even(edge, n), grid, life_map)
    if intent == "distribute_pattern":
        motif = set(_motif_cells(grid, bg))
        cells = sorted(c for c in motif if (c[0] + c[1]) % 3 == 0)  # 대각 격자
        return _hidden_instances(cells, grid, life_map)

    # ── Iron Wall (오버레이, darts 중립, color/hp 없음) ───────
    if intent.startswith("wall_"):
        if intent == "wall_outline":
            edge = _sample_even(_edge_cells(grid, bg), 60)
            return [{"size": (1, 1), "pos": (x, y), "hp": 0, "color": None} for (x, y) in edge]
        if intent == "wall_top_band":
            ymax = max((y for (_x, y) in grid), default=H - 1)
            band = [(x, y) for (x, y) in grid if y >= ymax - max(1, int(H * 0.3))]
            cells = _sample_even(band, 8)
            return [{"size": (2, 2), "pos": (_clamp(x, 0, W - 2), _clamp(y, 0, H - 2)), "hp": 0, "color": None} for (x, y) in cells]
        sq = [{"size": (2, 2), "pos": (_clamp(x, 0, W - 2), _clamp(y, 0, H - 2)), "hp": 0, "color": None}
              for (x, y) in _sample_even(_edge_cells(grid, bg), 12)]
        if intent == "wall_mixed":
            outline = [{"size": (1, 1), "pos": (x, y), "hp": 0, "color": None}
                       for (x, y) in _sample_even(_edge_cells(grid, bg), 30)]
            return outline + sq
        return sq  # wall_squares_edge

    # ── Ice (오버레이, darts 중립) ────────────────────────────
    if intent.startswith("ice_"):
        region = _pick_target(regions, strategy["target"]) or (regions[0] if regions else None)
        health = cfg.get("health", 600)
        if intent == "ice_single_large":
            if not region:
                return []
            cx, cy = region["center"]
            b = 5
            return [{"size": (b, b), "pos": (_clamp(int(cx - b / 2), 0, W - b), _clamp(int(cy - b / 2), 0, H - b)), "hp": health, "color": None}]
        if intent == "ice_multi_medium":
            b = 3
            return [{"size": (b, b), "pos": (_clamp(x, 0, W - b), _clamp(y, 0, H - b)), "hp": health, "color": None}
                    for (x, y) in _sample_even(_motif_cells(grid, bg), 4)]
        if intent == "ice_multi_small":
            b = 2
            return [{"size": (b, b), "pos": (_clamp(x, 0, W - b), _clamp(y, 0, H - b)), "hp": health, "color": None}
                    for (x, y) in _sample_even(_motif_cells(grid, bg), 9)]
        big = []
        if region:
            cx, cy = region["center"]
            big = [{"size": (4, 4), "pos": (_clamp(int(cx - 2), 0, W - 4), _clamp(int(cy - 2), 0, H - 4)), "hp": health, "color": None}]
        small = [{"size": (2, 2), "pos": (_clamp(x, 0, W - 2), _clamp(y, 0, H - 2)), "hp": health, "color": None}
                 for (x, y) in _sample_even(_motif_cells(grid, bg), 3)]
        return big + small  # ice_mixed

    # ── Barricade (오버레이, +Count darts, 일직선) ────────────
    if intent.startswith("barricade_"):
        region = _pick_target(regions, strategy["target"])
        if region is None:
            return []
        bx0, by0, bx1, by1 = region["bbox"]
        rw, rh = bx1 - bx0 + 1, by1 - by0 + 1
        cx, cy = int(region["center"][0]), int(region["center"][1])
        cnt = cfg.get("default_count", 50)
        color = region["color"]
        if intent == "barricade_horizontal":
            return [{"size": (rw, 1), "pos": (bx0, cy), "hp": cnt, "color": color}]
        if intent == "barricade_vertical":
            return [{"size": (1, rh), "pos": (cx, by0), "hp": cnt, "color": color}]
        if intent == "barricade_L":
            return [{"size": (rw, 1), "pos": (bx0, by0), "hp": max(1, cnt // 2), "color": color},
                    {"size": (1, rh), "pos": (bx0, by0), "hp": max(1, cnt // 2), "color": color}]
        q = max(1, cnt // 4)
        return [{"size": (rw, 1), "pos": (bx0, by1), "hp": q, "color": color},
                {"size": (rw, 1), "pos": (bx0, by0), "hp": q, "color": color},
                {"size": (1, rh), "pos": (bx0, by0), "hp": q, "color": color},
                {"size": (1, rh), "pos": (_clamp(bx1, 0, W - 1), by0), "hp": q, "color": color}]  # barricade_frame

    # ── Target Box (오버레이, +egg Count darts) ──────────────
    if intent.startswith("box_"):
        region = _pick_target(regions, strategy["target"])
        if region is None:
            return []
        bx0, by0, bx1, by1 = region["bbox"]
        cx, cy = int(region["center"][0]), int(region["center"][1])
        cnt = cfg.get("default_count", 20)
        color = region["color"]
        if intent == "box_single_large":
            b = 5
            return [{"size": (b, b), "pos": (_clamp(cx - b // 2, 0, W - b), _clamp(cy - b // 2, 0, H - b)), "hp": cnt, "color": color}]
        if intent == "box_line":
            b = 3
            xs = _sample_even([bx0 + i * b for i in range(max(1, (bx1 - bx0 + 1) // b))], 3)
            return [{"size": (b, b), "pos": (_clamp(x, 0, W - b), _clamp(cy - b // 2, 0, H - b)), "hp": cnt, "color": color} for x in xs]
        if intent == "box_multiple":
            cells = _sample_even(list(region["cells"]), 3)
            return [{"size": (s, s), "pos": (_clamp(x, 0, W - s), _clamp(y, 0, H - s)), "hp": cnt, "color": color}
                    for (s, (x, y)) in zip([4, 3, 2], cells)]
        return [{"size": (5, 5), "pos": (_clamp(cx - 2, 0, W - 5), _clamp(cy - 2, 0, H - 5)), "hp": cnt, "color": color},
                {"size": (2, 2), "pos": (_clamp(bx1 - 2, 0, W - 2), _clamp(by1 - 2, 0, H - 2)), "hp": max(1, cnt // 2), "color": color}]  # box_mixed

    # ── 영역 기반 기믹 (Wooden 등) ───────────────────────────
    region = _pick_target(regions, strategy["target"])
    if region is None:
        return []
    size_dist = cfg["size_dist"]
    hp_by_size = cfg["hp_by_size"]
    cap = cfg["hp_cap"]
    color = region["color"]
    bx0, by0, bx1, by1 = region["bbox"]

    if intent == "cover_area":
        cands = select_size("cover_area", region, W, H, size_dist)
        if not cands:
            return []
        sw, sh = cands[0]["size"]
        cx, cy = region["center"]
        ax = _clamp(int(cx - sw / 2), bx0, bx1 - sw + 1)
        ay = _clamp(int(cy - sh / 2), by0, by1 - sh + 1)
        hp = pick_hp(sw * sh, hp_by_size, cap)
        return [{"size": (sw, sh), "pos": (ax, ay), "hp": hp, "color": color}]

    if intent == "block_horizontal":
        cands = select_size("block_horizontal", region, W, H, size_dist)
        if not cands:
            return []
        sw, sh = cands[0]["size"]
        count = max(1, W // sw)
        # densest row 스냅 — region 색이 가장 꽉 찬 행에 막대를 깔아 collateral(타색 제거) 최소화.
        # 단색 영역 전폭 행이면 auto-fix 없이도 10배수 정합 (골든 2안 = pure-c8 행 정합).
        rows_count = Counter(y for (_x, y) in region["cells"])
        best_row = max(rows_count, key=lambda r: rows_count[r])
        ay = _clamp(best_row, 0, H - sh)
        hp = pick_hp(sw * sh, hp_by_size, cap)
        return [{"size": (sw, sh), "pos": (i * sw, ay), "hp": hp, "color": color} for i in range(count)]

    if intent == "block_vertical":
        cands = select_size("block_vertical", region, W, H, size_dist)
        if not cands:
            return []
        sw, sh = cands[0]["size"]
        rh = by1 - by0 + 1
        count = max(1, rh // sh)
        # densest col 스냅
        cols_count = Counter(x for (x, _y) in region["cells"])
        best_col = max(cols_count, key=lambda cc: cols_count[cc])
        ax = _clamp(best_col, bx0, bx1 - sw + 1)
        hp = pick_hp(sw * sh, hp_by_size, cap)
        return [{"size": (sw, sh), "pos": (ax, by0 + i * sh), "hp": hp, "color": color} for i in range(count)]

    if intent == "mixed_focus":
        cands = select_size("cover_area", region, W, H, size_dist)
        if not cands:
            return []
        big = cands[0]["size"]
        mid = (3, 3) if (region["bbox_w"] >= 3 and region["bbox_h"] >= 3) else (2, 2)
        cx, cy = region["center"]
        big_pos = (_clamp(int(cx - big[0] / 2), bx0, bx1 - big[0] + 1),
                   _clamp(int(cy - big[1] / 2), by0, by1 - big[1] + 1))
        mid_pos = (_clamp(bx1 - mid[0] + 1, bx0, bx1 - mid[0] + 1),
                   _clamp(by1 - mid[1] + 1, by0, by1 - mid[1] + 1))
        return [
            {"size": big, "pos": big_pos, "hp": pick_hp(big[0] * big[1], hp_by_size, cap), "color": color},
            {"size": mid, "pos": mid_pos, "hp": pick_hp(mid[0] * mid[1], hp_by_size, cap), "color": color},
        ]
    return []


def generate_variants(board: dict, gimmick_type: str = "Wooden", options: dict | None = None,
                      regions: list[dict] | None = None) -> list[dict]:
    """
    완성보드 + 기믹 타입 → 4안 큐레이션.
    각 variant = {name, instances:[{size,pos,hp,color}], validation:{color_darts,total,violations}}

    regions: vision으로 미리 해석한 의미 영역(라벨 포함)을 넘기면 그걸 사용.
             None이면 휴리스틱 detect_regions (= 골든 회귀 경로, 변동 없음).
    """
    if gimmick_type not in GIMMICK_CONFIG or not GIMMICK_CONFIG[gimmick_type].get("strategies"):
        raise ValueError(f"unsupported gimmick_type: {gimmick_type} (지원: {SUPPORTED_GIMMICKS})")
    cfg = GIMMICK_CONFIG[gimmick_type]
    grid, W, H, bg = board_to_grid(board)
    min_size = (options or {}).get("min_region_size", 6)
    if not regions:
        regions = detect_regions(grid, bg, min_size=min_size)

    removes, darts_mode = _gimmick_rules(gimmick_type)
    lm = board_life_map(board)
    variants: list[dict] = []
    for strat in cfg["strategies"]:
        instances = _build_instances(strat, regions, grid, W, H, cfg, bg, lm)
        variant = {"name": strat["name"], "gimmick_type": gimmick_type, "instances": instances}
        if instances:
            variant["validation"] = validate_color_darts(grid, instances, removes, darts_mode, lm)
        else:
            variant["validation"] = None
            variant["note"] = "N/A: 적용 가능한 영역 없음"
        variants.append(variant)
    return variants


# ──────────────────────────────────────────────────────────
# 공개 API ②: 10배수 auto-fix (부록 E Algorithm L1.1 추출)
# ──────────────────────────────────────────────────────────
def auto_fix_variant(grid: dict, variant: dict, gimmick_type: str | None = None,
                     hp_cap: int | None = None, life_map: dict | None = None) -> dict:
    """
    부록 E Algorithm L1.1 — color_darts 10배수 위반 자동 조정.

    조정 우선순위(원본 L11):
      1) 기믹색 위반 → 해당 색 기믹 중 **최소 hp** 1개를 round-up(+ (10-residual)).
         cap 초과 시 round-down(- residual) fallback. (덜 침습적, 아트 불변)
      2) 비기믹색 위반(덮인 셀의 collateral) → **designer_needed** 플래그
         (풍선 수 조정 = 아트 변경이라 자동화 안 함)
      3) total 위반 → 색별 조정 후 자동 정합 (별도 처리 불필요)

    주의: hp cap은 README v2.2 §3의 **per-instance 통합 cap**(Wooden 100)을 사용.
          (원본 L11의 per-cell 50과 다름 — 신버전 핸드오프/generator와 정합)

    반환: {variant(조정본, 원본 불변), adjustments[], designer_needed[], clean, validation}
    """
    gt = gimmick_type or variant.get("gimmick_type") or "Wooden"
    cap = hp_cap if hp_cap is not None else GIMMICK_CONFIG.get(gt, {}).get("hp_cap", 100)
    removes, darts_mode = _gimmick_rules(gt)
    insts = [dict(i) for i in variant.get("instances", [])]

    adjustments: list[dict] = []
    designer_needed: list[dict] = []

    val = validate_color_darts(grid, insts, removes, darts_mode, life_map)
    for c, n, residual in val["violations"]:
        if c == "total":
            continue
        color_insts = [i for i in insts if i["color"] == c]
        fixed = False
        if color_insts:
            g = min(color_insts, key=lambda i: i["hp"])
            up = 10 - residual
            if g["hp"] + up <= cap:                       # 1차: round-up
                old = g["hp"]; g["hp"] = old + up
                adjustments.append({"type": "gimmick_hp_increase", "color": c,
                                    "old_hp": old, "new_hp": g["hp"], "delta": up})
                fixed = True
            elif g["hp"] - residual >= 1:                  # fallback: round-down
                old = g["hp"]; g["hp"] = old - residual
                adjustments.append({"type": "gimmick_hp_decrease", "color": c,
                                    "old_hp": old, "new_hp": g["hp"], "delta": -residual})
                fixed = True
        if not fixed:                                      # 2차: designer (아트 변경)
            if residual <= 5:
                designer_needed.append({"color": c, "action": "add_balloons", "count": 10 - residual,
                                        "note": f"색 c{c}에 1×1 풍선 {10 - residual}개 추가 필요"})
            else:
                designer_needed.append({"color": c, "action": "remove_balloons", "count": residual,
                                        "note": f"색 c{c}에서 1×1 풍선 {residual}개 제거 필요"})

    final_val = validate_color_darts(grid, insts, removes, darts_mode, life_map)
    fixed_variant = dict(variant)
    fixed_variant["instances"] = insts
    fixed_variant["validation"] = final_val
    return {
        "variant": fixed_variant,
        "adjustments": adjustments,
        "designer_needed": designer_needed,
        "clean": len(final_val["violations"]) == 0,
        "validation": final_val,
    }


# ──────────────────────────────────────────────────────────
# 공개 API ③: 택1 → 병합 (기믹 배치)
# ──────────────────────────────────────────────────────────
def _inst_cells(inst: dict) -> list:
    sw, sh = inst["size"]
    ax, ay = inst["pos"]
    return [(ax + dx, ay + dy) for dx in range(sw) for dy in range(sh)]


def _board_detail_entry(gt: str, inst: dict):
    """instance → boardGimmicks.details 엔트리 (STEP 6-B 스키마). Wooden/Hidden은 None(balloons)."""
    sw, sh = inst["size"]
    cells = _inst_cells(inst)
    color = inst.get("color")
    hp = inst.get("hp", 0) or 0
    mat = (color + 1) if color is not None else 0  # BL 0-27 → PF 1-28
    if gt == "Barricade":
        return "gates", {"GridPoints": cells, "Direction": 0 if sw >= sh else 1,
                         "Length": max(sw, sh), "Material": mat, "Count": hp}
    if gt == "IronWall":
        return "walls", {"GridPoints": cells, "size": f"{sw}x{sh}",
                         "mode": "outline" if (sw == 1 or sh == 1) else "sqr"}
    if gt == "Ice":
        return "pixelIceBlocks", {"GridPoints": cells, "BlockSize": max(sw, sh), "Health": hp}
    if gt == "TargetBox":
        return "eggBoxes", {"GridPoints": cells, "EggArea": [sw, sh], "Eggs": [{"Material": mat, "Count": hp}]}
    return None


def apply_variant(board: dict, variant: dict, gimmick_type: str | None = None) -> dict:
    """
    선택된 variant를 완성보드에 병합 (기믹별 규칙).
      - removes=True(Wooden/Hidden): 덮은 셀 표준풍선 제거. False(오버레이): 풍선 유지.
      - gimmicks[](평면) + boardGimmicks.details(STEP 6-B 스키마) 동시 기록.
      - color_darts 재검증을 board["validation"]에 기록. 원본 불변(새 dict).
    """
    gt = gimmick_type or variant.get("gimmick_type") or "Wooden"
    removes, darts_mode = _gimmick_rules(gt)
    grid, W, H, _bg = board_to_grid(board)
    instances = variant.get("instances", [])
    covered = _covered_cells(instances) if removes else set()

    new_balloons = [b for b in board["balloons"] if (int(b["col"]), int(b["row"])) not in covered]
    new_gimmicks = list(board.get("gimmicks", []))
    details = {k: list(v) for k, v in (board.get("boardGimmicks", {}).get("details", {}) or {}).items()}
    for inst in instances:
        ax, ay = inst["pos"]
        sw, sh = inst["size"]
        new_gimmicks.append({"type": gt, "col": ax, "row": ay, "sizeW": sw, "sizeH": sh,
                             "hp": inst.get("hp"), "color": inst.get("color")})
        de = _board_detail_entry(gt, inst)
        if de:
            key, entry = de
            details.setdefault(key, []).append(entry)

    out = dict(board)
    out["balloons"] = new_balloons
    out["gimmicks"] = new_gimmicks
    if details:
        out["boardGimmicks"] = {"details": details}
    out["validation"] = validate_color_darts(grid, instances, removes, darts_mode, board_life_map(board))
    out["applied_variant"] = variant.get("name")
    return out


# ──────────────────────────────────────────────────────────
# 공개 API ④: 4안 PNG 미리보기 렌더 (프로토타입 render 추출)
# ──────────────────────────────────────────────────────────
# PF Material 팔레트 (1~28). BL 색은 -1 시프트 (BL c = PF c+1).
PF_PALETTE = {
    1: (252, 106, 175), 2: (80, 232, 246), 3: (137, 80, 248), 4: (254, 213, 85),
    5: (115, 254, 102), 6: (253, 161, 76), 7: (255, 255, 255), 8: (65, 65, 65),
    9: (110, 168, 250), 10: (57, 174, 46), 11: (252, 94, 94), 12: (50, 107, 248),
    13: (58, 165, 139), 14: (231, 167, 250), 15: (183, 199, 251), 16: (106, 74, 48),
    17: (254, 227, 169), 18: (253, 183, 193), 19: (158, 61, 94), 20: (167, 221, 148),
    21: (89, 46, 126), 22: (220, 120, 129), 23: (217, 217, 231), 24: (111, 114, 127),
    25: (252, 56, 165), 26: (253, 180, 88), 27: (137, 10, 8), 28: (111, 175, 177),
}


def _palette_for(indexing: str) -> dict:
    """indexing='bl' → BL c0~c27 (=PF c+1) / 'pf' → PF c1~c28."""
    if indexing == "pf":
        return dict(PF_PALETTE)
    return {i: PF_PALETTE[i + 1] for i in range(28)}  # bl


def render_variant_png(board: dict, variant: dict, cell: int = 11, flip_y: bool = True,
                       indexing: str = "bl", palette: dict | None = None) -> str:
    """
    완성보드 + variant → 미리보기 PNG(base64). 디자이너가 4안을 눈으로 보고 택1하기 위한 시각화.
      - 표준풍선: 색 팔레트, 기믹 점유 셀은 비움
      - 기믹: 갈색 박스 + hp 텍스트
      - 헤더: 안 이름 + 10배수 OK/X
    indexing: 보드 color 인덱싱 ('bl' c0~27 / 'pf' c1~28). flip_y: row 0을 하단에 둘지.
    """
    from PIL import Image, ImageDraw  # lazy

    grid, W, H, _bg = board_to_grid(board)
    pal = palette or _palette_for(indexing)
    covered = _covered_cells(variant.get("instances", []))

    img = Image.new("RGB", (W * cell, H * cell), (40, 40, 40))
    draw = ImageDraw.Draw(img)

    def py_of(y: int, span: int = 1) -> int:
        return ((H - (y + span)) if flip_y else y) * cell

    for (x, y), col in grid.items():
        if (x, y) in covered:
            continue
        rgb = pal.get(col, (128, 128, 128))
        px, py = x * cell, py_of(y)
        draw.rectangle([px, py, px + cell - 1, py + cell - 1], fill=rgb)

    for inst in variant.get("instances", []):
        sw, sh = inst["size"]
        ax, ay = inst["pos"]
        px, py = ax * cell, py_of(ay, sh)
        draw.rectangle([px + 1, py + 1, px + sw * cell - 2, py + sh * cell - 2],
                       fill=(160, 90, 50), outline=(101, 50, 20), width=2)
        draw.text((px + 3, py + 1), str(inst.get("hp", "")), fill=(255, 255, 0))

    val = variant.get("validation")
    ok = bool(val) and not val["violations"]
    draw.rectangle([0, 0, 190, 18], fill=(0, 0, 0))
    draw.text((4, 2), str(variant.get("name", "")), fill=(255, 255, 0))
    draw.text((150, 2), "10x" + ("OK" if ok else "X"),
              fill=(0, 255, 0) if ok else (255, 80, 80))

    import base64
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def render_variants_grid_png(board: dict, variants: list[dict], cell: int = 11,
                             flip_y: bool = True, indexing: str = "bl") -> str:
    """4안을 2×2 한 장으로 합쳐 base64 PNG 반환 (골든 PNG와 동일 레이아웃)."""
    from PIL import Image  # lazy
    import base64
    import io

    _grid, W, H, _bg = board_to_grid(board)
    pad = 10
    panel_w, panel_h = W * cell, H * cell
    combined = Image.new("RGB", (panel_w * 2 + pad, panel_h * 2 + pad), (20, 20, 20))
    for i, v in enumerate(variants[:4]):
        b64 = render_variant_png(board, v, cell=cell, flip_y=flip_y, indexing=indexing)
        panel = Image.open(io.BytesIO(base64.b64decode(b64)))
        combined.paste(panel, ((i % 2) * (panel_w + pad), (i // 2) * (panel_h + pad)))
    buf = io.BytesIO()
    combined.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ──────────────────────────────────────────────────────────
# 어댑터: BL 빌드 JSON(level_NN.json, world gridPosition) → board 포맷
# ──────────────────────────────────────────────────────────
def level_json_to_board(level_json: dict) -> dict:
    """
    BL 빌드 포맷(balloons[].gridPosition world좌표) → 완성보드 포맷({row,col,color,life}).
    grid-index = 고유 x/y 값 정렬 순위. (골든샘플 회귀테스트 입력 변환용)
    """
    balloons = level_json["balloons"]
    xs = sorted(set(b["gridPosition"]["x"] for b in balloons))
    ys = sorted(set(b["gridPosition"]["y"] for b in balloons))
    x_to_col = {x: i for i, x in enumerate(xs)}
    y_to_row = {y: i for i, y in enumerate(ys)}
    out_balloons = [{
        "row": y_to_row[b["gridPosition"]["y"]],
        "col": x_to_col[b["gridPosition"]["x"]],
        "color": b["color"],
        "life": 1,  # 표준풍선 = 1 dart (필드완성 정합)
    } for b in balloons]
    return {
        "field_columns": len(xs),
        "field_rows": len(ys),
        "balloons": out_balloons,
        "gimmicks": [],
    }
