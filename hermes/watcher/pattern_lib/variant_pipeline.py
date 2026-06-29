"""
변형 양산 → 평가 → 최적 채택 파이프라인.

각 레벨당 6~8개 변형 생성 후, 평가 점수 높은 것을 채택.
원본 balance_to_x10 사후 수정 방식 대체.

변형 전략:
  _A: 현재 기본 (seed 그대로)
  _B: 동심 대칭 (그리드 중심 기준 concentric coloring)
  _C: 다른 seed (+100)
  _D: 다른 seed (+200)
  _E: 다른 seed (+500)
  _F: 타일 크기 강제 (grid 나눠떨어지는 값)
  _G: 방향 변경 (stripe/chevron 방향 회전)
  _H: 다른 패턴군 (대체 후보)

평가 항목:
  1. 10배수 완벽 달성 (binary)
  2. 대칭 점수 (LR/TB/180° 최대값)
  3. 주기성 점수
  4. 노이즈 페널티 (빈칸 비율)
"""
import json
import math
import random
from pathlib import Path
from collections import Counter
from PIL import Image

from pixel_pattern_api import (
    generate_pattern, _make_image, balance_to_x10, DEFAULT_PALETTE,
    PATTERN_FUNCS,
)
from blank_engine import pattern_aware_blank, classify_pattern


# ─────────────────────────────────────────────────────
# 변형 생성 전략
# ─────────────────────────────────────────────────────
def _bot_workflow(pattern: str, W: int, H: int, n_colors: int,
                    n_bg: int, targets: list, fill_fn,
                    hints: dict, seed: int,
                    K: int = 5, seed_offsets=(0, 100, 200, 500),
                    layout_idx: int = 0) -> list:
    """통일 워크플로우.
    layout_idx: 어느 layout 시도할지 (0=top, 1=2nd, ...). 다른 변형 위해 사용.
    fail시 layout_idx+1, +2 ... 순회 fallback."""
    from bg_layout import propose_layouts, score_layout
    from collections import Counter
    layout_hints = {**(hints or {}), 'n_colors': n_colors}
    layouts = propose_layouts(pattern, W, H, n_bg, layout_hints)
    scored = [(score_layout(L, W, H, pattern, layout_hints), L) for L in layouts]
    scored.sort(reverse=True, key=lambda x: x[0])
    top_K = [L for s, L in scored[:K]]
    if not top_K:
        return None
    from pixel_pattern_api import _balance_color_swap_only

    # layout_idx부터 시작해서 fallback 순회
    rotated = top_K[layout_idx % len(top_K):] + top_K[:layout_idx % len(top_K)]
    for layout in rotated:
        for off in seed_offsets:
            g = fill_fn(W, H, n_colors, layout, targets, seed + off)
            if g is None:
                continue
            cnt = Counter(c for row in g for c in row if isinstance(c, int))
            if all(cnt.get(c, 0) == targets[c] for c in range(n_colors)):
                return g
            if sum(cnt.values()) == sum(targets):
                g_bal = _balance_color_swap_only(g, W, H, n_colors, targets,
                                                    bg_marker='K')
                cnt2 = Counter(c for row in g_bal for c in row if isinstance(c, int))
                if all(cnt2.get(c, 0) == targets[c] for c in range(n_colors)):
                    return g_bal
    return None


def gen_planned(pattern: str, W: int, H: int, n_colors: int,
                colors: list, seed: int, layout_idx: int = 0) -> list:
    """plan_counts 결과에 따라 10-mult 자연 달성하는 grid 생성.
    모든 패턴 + plan_infeasible 케이스 모두 통일 봇 워크플로우 거침.
    봇 실패 시 기존 _natural_to_targets / 패턴별 fallback."""
    from plan_counts import plan_counts
    plan = plan_counts(W, H, n_colors, pattern)
    total = W * H

    if plan['feasible']:
        targets = plan['targets']
        n_bg = plan['bg_count']
        hints = plan['generator_hints']
    else:
        # plan_infeasible: targets 자동 하향 (uniform 10x), bg ≤ 15%까지
        per = (total // (n_colors * 10)) * 10
        while per > 0 and (total - per * n_colors) > total * 0.15:
            per -= 10
        if per <= 0:
            per = 10
        targets = [per] * n_colors
        n_bg = total - per * n_colors
        hints = {}

    # plan_infeasible 케이스도 hints는 비어 있지만 봇은 실행 가능
    # ─── 통일 봇 워크플로우 dispatch ───
    if pattern == 'stripe':
        from pixel_pattern_api import _fill_stripe, _stripe_to_targets
        g = _bot_workflow(
            'stripe', W, H, n_colors, n_bg, targets,
            fill_fn=_fill_stripe, hints=hints, seed=seed, layout_idx=layout_idx,
        )
        if g is not None:
            return g
        if plan['feasible']:
            return _stripe_to_targets(
                W, H, n_colors,
                stripe_width=hints['stripe_width'],
                bg_cols_total=hints['bg_cols_total'],
                seed=seed,
            )
    if pattern == 'checkerboard':
        from pixel_pattern_api import _checker_to_targets, _fill_checkerboard
        tile_size = hints.get('tile_size', 1) or 4
        fill_with_tile = lambda W, H, n, lay, tg, sd: _fill_checkerboard(
            W, H, n, lay, tg, tile_size, sd)
        g = _bot_workflow(
            'checkerboard', W, H, n_colors, n_bg, targets,
            fill_fn=fill_with_tile,
            hints={**hints, 'tile_size': tile_size}, seed=seed, layout_idx=layout_idx,
        )
        if g is not None:
            return g
        if plan['feasible']:
            return _checker_to_targets(
                W, H, n_colors,
                targets=targets, bg_count=n_bg,
                tile_size=tile_size, seed=seed,
            )
    if pattern == 'rect_grid':
        from pixel_pattern_api import _rect_grid_to_targets, _fill_rect_grid
        tile_w = hints.get('tile_w', 4) or 4
        tile_h = hints.get('tile_h', 4) or 4
        fill_with_tile = lambda W, H, n, lay, tg, sd: _fill_rect_grid(
            W, H, n, lay, tg, tile_w, tile_h, sd)
        g = _bot_workflow(
            'rect_grid', W, H, n_colors, n_bg, targets,
            fill_fn=fill_with_tile,
            hints={**hints, 'tile_w': tile_w, 'tile_h': tile_h}, seed=seed, layout_idx=layout_idx,
        )
        if g is not None:
            return g
        if plan['feasible']:
            return _rect_grid_to_targets(
                W, H, n_colors,
                targets=targets, bg_count=n_bg,
                tile_w=tile_w, tile_h=tile_h, seed=seed,
            )
    if pattern == 'diamond_check':
        # 봇 통합 미완 — 옛 _diamond_check_to_targets 사용 (사용자 검증된 결과)
        from pixel_pattern_api import _diamond_check_to_targets
        mind = min(W, H)
        if n_colors <= 3:
            default_size = 6 if mind >= 24 else 4
        elif n_colors == 4:
            default_size = 7 if mind >= 24 else 5
        else:
            default_size = 5 if mind >= 20 else 3
        if plan['feasible']:
            return _diamond_check_to_targets(
                W, H, n_colors,
                targets=targets, bg_count=n_bg,
                size=hints.get('tile_size', default_size), seed=seed,
            )
    if pattern == 'brick':
        # 봇 통합 미완 — 옛 _brick_to_targets 사용 (Lv139 보존)
        from pixel_pattern_api import _brick_to_targets
        if plan['feasible']:
            return _brick_to_targets(
                W, H, n_colors,
                targets=targets, bg_count=n_bg,
                brick_w=hints.get('brick_w', 5),
                brick_h=hints.get('brick_h', 4), seed=seed,
            )
    if pattern == 'chevron':
        from pixel_pattern_api import _chevron_to_targets, _fill_chevron
        mind = min(W, H)
        default_band = 6 if mind >= 24 else 4
        band = hints.get('band', default_band)
        fill_with_band = lambda W, H, n, lay, tg, sd: _fill_chevron(
            W, H, n, lay, tg, band, sd)
        g = _bot_workflow(
            'chevron', W, H, n_colors, n_bg, targets,
            fill_fn=fill_with_band,
            hints={**hints, 'band': band}, seed=seed, layout_idx=layout_idx,
        )
        if g is not None:
            return g
        if plan['feasible']:
            return _chevron_to_targets(
                W, H, n_colors,
                targets=targets, bg_count=n_bg,
                band=band, seed=seed,
            )
    if pattern == 'concentric_sq':
        from pixel_pattern_api import _concentric_sq_to_targets, _fill_concentric_sq
        g = _bot_workflow(
            'concentric_sq', W, H, n_colors, n_bg, targets,
            fill_fn=_fill_concentric_sq, hints=hints, seed=seed, layout_idx=layout_idx,
        )
        if g is not None:
            return g
        if plan['feasible']:
            return _concentric_sq_to_targets(
                W, H, n_colors,
                targets=targets, bg_count=n_bg,
                ring=hints.get('ring', 3), seed=seed,
            )
    # 미통합 패턴: 봇 워크플로우 시도 → 옛 _to_targets fallback
    from pixel_pattern_api import _fill_motif_natural, PATTERN_FUNCS
    if pattern == 'argyle':
        from pixel_pattern_api import _argyle_to_targets, _argyle
        fill_fn = lambda W, H, n, lay, tg, sd: _fill_motif_natural(
            _argyle, W, H, n, lay, tg, sd)
        g = _bot_workflow('argyle', W, H, n_colors, n_bg, targets,
                            fill_fn=fill_fn, hints=hints, seed=seed)
        if g is not None: return g
        return _argyle_to_targets(W, H, n_colors,
                                    targets=targets, bg_count=n_bg, seed=seed)
    if pattern == 'hex_tile':
        from pixel_pattern_api import _hex_tile_to_targets, _hex_tile
        fill_fn = lambda W, H, n, lay, tg, sd: _fill_motif_natural(
            _hex_tile, W, H, n, lay, tg, sd)
        g = _bot_workflow('hex_tile', W, H, n_colors, n_bg, targets,
                            fill_fn=fill_fn, hints=hints, seed=seed)
        if g is not None: return g
        return _hex_tile_to_targets(W, H, n_colors,
                                       targets=targets, bg_count=n_bg, seed=seed)
    if pattern == 'i_tetromino':
        from pixel_pattern_api import _i_tetromino_to_targets, _i_tetromino
        fill_fn = lambda W, H, n, lay, tg, sd: _fill_motif_natural(
            _i_tetromino, W, H, n, lay, tg, sd)
        g = _bot_workflow('i_tetromino', W, H, n_colors, n_bg, targets,
                            fill_fn=fill_fn, hints=hints, seed=seed)
        if g is not None: return g
        return _i_tetromino_to_targets(W, H, n_colors,
                                         targets=targets, bg_count=n_bg,
                                         seed=seed)
    if pattern == 'maze':
        from pixel_pattern_api import _maze_to_targets, _maze
        fill_fn = lambda W, H, n, lay, tg, sd: _fill_motif_natural(
            _maze, W, H, n, lay, tg, sd)
        g = _bot_workflow('maze', W, H, n_colors, n_bg, targets,
                            fill_fn=fill_fn, hints=hints, seed=seed)
        if g is not None: return g
        return _maze_to_targets(W, H, n_colors,
                                  targets=targets, bg_count=n_bg, seed=seed)

    # 모든 다른 패턴: 봇 워크플로우 → _natural_to_targets fallback
    from pixel_pattern_api import _natural_to_targets
    if pattern in PATTERN_FUNCS:
        pattern_fn = PATTERN_FUNCS[pattern]
        fill_fn = lambda W, H, n, lay, tg, sd: _fill_motif_natural(
            pattern_fn, W, H, n, lay, tg, sd)
        g = _bot_workflow(pattern, W, H, n_colors, n_bg, targets,
                            fill_fn=fill_fn, hints=hints, seed=seed)
        if g is not None: return g
        return _natural_to_targets(pattern_fn, W, H, n_colors,
                                     targets=targets, bg_count=n_bg, seed=seed)
    return None


def gen_variant(variant_id: str, pattern: str, W: int, H: int,
                n_colors: int, colors: list, seed: int, **kwargs) -> list:
    """특정 변형 ID에 맞는 grid 생성."""

    # 'P' = planned (target-aware). plan_counts + target generator로 10-mult 자연 달성.
    # _P만 봇 워크플로우. _A~_H는 자연 generator (사용자 좋아한 모양 보존)
    if variant_id == 'P':
        g = gen_planned(pattern, W, H, n_colors, colors, seed)
        return g

    if variant_id == 'A':
        img = generate_pattern(pattern, W, H, block_size=30,
                               colors=colors, seed=seed,
                               transparent_bg=True, **kwargs)
        return _img_to_grid(img, W, H)
    if variant_id == 'B':
        img = generate_pattern(pattern, W, H, block_size=30,
                               colors=colors, seed=seed + 1000,
                               transparent_bg=True, **kwargs)
        return _img_to_grid(img, W, H)
    if variant_id == 'C':
        img = generate_pattern(pattern, W, H, block_size=30,
                               colors=colors, seed=seed + 100,
                               transparent_bg=True, **kwargs)
        return _img_to_grid(img, W, H)
    if variant_id == 'D':
        img = generate_pattern(pattern, W, H, block_size=30,
                               colors=colors, seed=seed + 200,
                               transparent_bg=True, **kwargs)
        return _img_to_grid(img, W, H)
    if variant_id == 'E':
        img = generate_pattern(pattern, W, H, block_size=30,
                               colors=colors, seed=seed + 500,
                               transparent_bg=True, **kwargs)
        return _img_to_grid(img, W, H)
    if variant_id == 'F':
        divisors_w = [d for d in range(3, 12) if W % d == 0]
        divisors_h = [d for d in range(3, 12) if H % d == 0]
        tw = divisors_w[0] if divisors_w else 5
        th = divisors_h[0] if divisors_h else 5
        kw = dict(kwargs)
        if pattern == 'rect_grid':
            kw['tile_w'] = tw; kw['tile_h'] = th
        elif pattern in ('brick',):
            kw['brick_w'] = tw; kw['brick_h'] = th
        elif pattern in ('checkerboard', 'diamond_check', 'stripe'):
            kw['size' if pattern != 'stripe' else 'stripe_width'] = min(tw, th)
        img = generate_pattern(pattern, W, H, block_size=30,
                               colors=colors, seed=seed,
                               transparent_bg=True, **kw)
        return _img_to_grid(img, W, H)
    if variant_id == 'G':
        rng = random.Random(seed + 13)
        shuffled = list(colors); rng.shuffle(shuffled)
        img = generate_pattern(pattern, W, H, block_size=30,
                               colors=shuffled, seed=seed,
                               transparent_bg=True, **kwargs)
        return _img_to_grid(img, W, H)
    if variant_id == 'H':
        alt_map = {
            'rect_grid': 'checkerboard', 'checkerboard': 'rect_grid',
            'plus_motif': 't_motif', 't_motif': 'plus_motif',
            'x_motif': 'plus_motif', 'stripe': 'chevron',
            'chevron': 'stripe', 'argyle': 'diamond_check',
            'diamond_check': 'argyle', 'hex_tile': 'concentric_sq',
            'kaleidoscope': 'concentric_sq',
        }
        alt = alt_map.get(pattern, pattern)
        img = generate_pattern(alt, W, H, block_size=30,
                               colors=colors, seed=seed,
                               transparent_bg=True)
        return _img_to_grid(img, W, H)
    return None


def gen_concentric(W: int, H: int, n: int, colors: list, seed: int) -> list:
    """_B: 동심 사각 링 (Chebyshev 거리). 격자비에 상관없이 깔끔한 사각 링.
    LR/TB/180° 완벽 대칭."""
    rng = random.Random(seed)
    max_useful_size = max(2, min(W, H) // (2 * max(n-1, 1)))
    size_pool = list(range(2, max_useful_size + 1))
    if not size_pool: size_pool = [2]
    size = rng.choice(size_pool)
    perm = list(range(n)); rng.shuffle(perm)
    rot = rng.randrange(max(1, n))
    cx, cy = (W-1)/2.0, (H-1)/2.0
    def get_color(x, y):
        bx = int(abs(x - cx) // size)
        by = int(abs(y - cy) // size)
        # Chebyshev: 사각 링 (이전: bx + by = 다이아몬드)
        r = max(bx, by)
        return perm[(r + rot) % n]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


def gen_concentric_xor(W: int, H: int, n: int, colors: list, seed: int) -> list:
    """_G: XOR 동심 (bx XOR by). Sierpinski-like 자기유사 패턴. 대칭 완벽."""
    rng = random.Random(seed)
    max_useful_size = max(2, min(W, H) // (2 * max(n-1, 1)))
    size_pool = list(range(2, max_useful_size + 1))
    if not size_pool: size_pool = [2]
    size = rng.choice(size_pool)
    perm = list(range(n)); rng.shuffle(perm)
    rot = rng.randrange(max(1, n))
    cx, cy = (W-1)/2.0, (H-1)/2.0
    def get_color(x, y):
        bx = int(abs(x - cx) // size)
        by = int(abs(y - cy) // size)
        return perm[((bx ^ by) + rot) % n]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


def _img_to_grid(img: Image.Image, W: int, H: int) -> list:
    """PIL Image를 grid (RGBA 4-tuple 리스트) 로 변환. RGB는 alpha=255로 보강."""
    img = img.convert('RGBA')
    px = img.load()
    return [[px[gx*30+15, gy*30+15] for gx in range(W)] for gy in range(H)]


# ─────────────────────────────────────────────────────
# 평가 함수
# ─────────────────────────────────────────────────────
def _swap_edge_bg(grid, W, H, bg=(255, 255, 255, 0)):
    """외곽 행/열이 통째로 bg면 interior color cell과 swap (180° 대칭 보존,
    색별 카운트 보존). 위반당 swap 1쌍씩 (외곽 1셀 + 180° pair = 색이 됨)."""
    edge_specs = [
        ('top', [(x, 0) for x in range(W)]),
        ('bottom', [(x, H-1) for x in range(W)]),
        ('left', [(0, y) for y in range(H)]),
        ('right', [(W-1, y) for y in range(H)]),
    ]
    grid = [row[:] for row in grid]
    changed = False
    for name, cells in edge_specs:
        if not all(grid[y][x] == bg for x, y in cells):
            continue
        # 위반: 외곽 중앙 셀 + 180° pair을 swap with 가까운 interior color cell pair
        cx_e, cy_e = cells[len(cells)//2]
        pair_x, pair_y = W-1-cx_e, H-1-cy_e
        # interior color cell 찾기 (interior + 180° pair도 색)
        # 중앙에서 가까운 순으로 탐색
        cx, cy = (W-1)/2.0, (H-1)/2.0
        candidates = []
        for iy in range(1, H-1):
            for ix in range(1, W-1):
                if grid[iy][ix] != bg and grid[H-1-iy][W-1-ix] != bg:
                    d = (ix - cx) ** 2 + (iy - cy) ** 2
                    candidates.append((d, ix, iy))
        candidates.sort()
        for _, ix, iy in candidates:
            iy2, ix2 = H-1-iy, W-1-ix
            if (ix, iy) == (cx_e, cy_e) or (ix2, iy2) == (cx_e, cy_e):
                continue
            a = grid[iy][ix]
            b = grid[iy2][ix2]
            grid[cy_e][cx_e] = a
            grid[pair_y][pair_x] = b
            grid[iy][ix] = bg
            grid[iy2][ix2] = bg
            changed = True
            break
    return grid if changed else grid


def _design_central_cluster(n: int, W: int, H: int) -> set:
    """n개 cells을 중앙에 180°-symmetric 배치. center pair부터 채워 가장 콤팩트한 형태.
    가능: 정중앙 self-pair (홀×홀 grid n=1) + 180° pair들. 우선순위는 중심 거리.
    반환: positions set or None (구성 불가)."""
    if n <= 0:
        return set()
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    pairs = []
    seen = set()
    for y in range(H):
        for x in range(W):
            mx, my = W - 1 - x, H - 1 - y
            key = tuple(sorted([(x, y), (mx, my)]))
            if key in seen:
                continue
            seen.add(key)
            if (x, y) == (mx, my):
                cells = [(x, y)]
                count = 1
            else:
                cells = [(x, y), (mx, my)]
                count = 2
            d = (x - cx) ** 2 + (y - cy) ** 2
            pairs.append((d, count, cells))
    pairs.sort()
    chosen = set()
    for d, count, cells in pairs:
        if len(chosen) + count > n:
            continue
        for c in cells:
            chosen.add(c)
        if len(chosen) == n:
            return chosen
    if len(chosen) == n:
        return chosen
    return None


def _consolidate_bg_to_center(grid, W, H, bg=(255, 255, 255, 0)):
    """grid의 bg 셀들을 중앙 cluster로 모음. 색별 카운트 + 180° 대칭 보존.
    원본이 180° 대칭일 때만 작동. 비대칭이면 원본 반환."""
    bg_now = {(x, y) for y in range(H) for x in range(W) if grid[y][x] == bg}
    n = len(bg_now)
    if n == 0:
        return grid
    # 원본 180° 대칭 확인
    for (x, y) in bg_now:
        if (W - 1 - x, H - 1 - y) not in bg_now:
            return grid
    # 중앙 cluster 위치
    target = _design_central_cluster(n, W, H)
    if target is None or len(target) != n or target == bg_now:
        return grid
    # to_color: bg_now − target (색이 되어야)
    # to_bg: target − bg_now (bg가 되어야)
    to_color = bg_now - target
    to_bg = target - bg_now
    if len(to_color) != len(to_bg):
        return grid
    # to_bg 위치의 색 cells을 to_color 위치로 이동 (180° pair 보존)
    new_grid = [row[:] for row in grid]
    # canonical 순서 (sorted) 매핑 — 양쪽 다 180°-symmetric면 자연 페어 매칭
    tc = sorted(to_color)
    tb = sorted(to_bg)
    for (cx_, cy_), (bx, by) in zip(tc, tb):
        new_grid[cy_][cx_] = grid[by][bx]
        new_grid[by][bx] = bg
    # 검증: bg count 보존
    new_bg = sum(1 for row in new_grid for c in row if c == bg)
    if new_bg != n:
        return grid
    return new_grid


def _full_bg_edge(grid, W, H, bg=(255, 255, 255, 0)) -> int:
    """외곽(첫/끝) 행 또는 열 중 전체가 bg인 개수. 0이면 OK, ≥1이면 규칙 위반.
    "외곽이 통째로 빈칸인 행/열은 금지" 규칙."""
    cnt = 0
    if all(grid[0][x] == bg for x in range(W)): cnt += 1
    if H > 1 and all(grid[H-1][x] == bg for x in range(W)): cnt += 1
    if all(grid[y][0] == bg for y in range(H)): cnt += 1
    if W > 1 and all(grid[y][W-1] == bg for y in range(H)): cnt += 1
    return cnt


def _scatter_count(grid, W, H, bg=(255, 255, 255, 0)) -> int:
    """고립된 1셀 빈칸 (주변 8방향 모두 비-bg) 개수. "쥐파먹음" 지표."""
    cnt = 0
    for y in range(H):
        for x in range(W):
            if grid[y][x] != bg: continue
            surrounded = True
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0: continue
                    ny, nx = y+dy, x+dx
                    if 0 <= ny < H and 0 <= nx < W and grid[ny][nx] == bg:
                        surrounded = False; break
                if not surrounded: break
            if surrounded: cnt += 1
    return cnt


def _largest_color_component(grid, W, H, bg):
    """가장 큰 단일색 connected component 크기 / total. 단조 패턴 감지."""
    from collections import deque
    visited = [[False]*W for _ in range(H)]
    max_size = 0
    for y in range(H):
        for x in range(W):
            if visited[y][x]: continue
            color = grid[y][x]
            if color == bg:
                visited[y][x] = True; continue
            size = 0
            q = deque([(x, y)])
            visited[y][x] = True
            while q:
                cx, cy = q.popleft()
                size += 1
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = cx + dx, cy + dy
                    if 0 <= nx < W and 0 <= ny < H and not visited[ny][nx] and grid[ny][nx] == color:
                        visited[ny][nx] = True
                        q.append((nx, ny))
            if size > max_size: max_size = size
    return max_size / (W * H) if W * H > 0 else 0


def _bg_cluster_count(grid, W, H, bg) -> int:
    """bg cells의 connected component 수. 1이 가장 좋음 (단일 cluster)."""
    visited = [[False]*W for _ in range(H)]
    count = 0
    from collections import deque
    for y in range(H):
        for x in range(W):
            if visited[y][x] or grid[y][x] != bg:
                continue
            count += 1
            q = deque([(x, y)])
            visited[y][x] = True
            while q:
                cx, cy = q.popleft()
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, ny = cx+dx, cy+dy
                    if 0 <= nx < W and 0 <= ny < H and not visited[ny][nx] and grid[ny][nx] == bg:
                        visited[ny][nx] = True
                        q.append((nx, ny))
    return count


def score_grid(grid: list, W: int, H: int, n_requested: int = 0, bg=(255, 255, 255, 0)) -> dict:
    """변형 grid 평가. 높을수록 좋음."""
    cnt = Counter(c for row in grid for c in row)
    bg_count = cnt.get(bg, 0)
    fills = {c: n for c, n in cnt.items() if c != bg}
    n_used = len(fills)

    # 색 수 매칭 (요청한 n_colors 다 썼는지)
    color_match = n_used / n_requested if n_requested > 0 else 1
    color_match = min(color_match, 1.0)

    # 1. 10배수 달성
    is_10_mult = all(n % 10 == 0 for n in fills.values())

    # 2. 대칭 점수 (최대축)
    def sym_lr():
        d = H * (W // 2)
        return (sum(1 for y in range(H) for x in range(W//2)
                    if grid[y][x] == grid[y][W-1-x]) / d) if d else 1
    def sym_tb():
        d = (H // 2) * W
        return (sum(1 for y in range(H//2) for x in range(W)
                    if grid[y][x] == grid[H-1-y][x]) / d) if d else 1
    def sym_180():
        return sum(1 for y in range(H) for x in range(W)
                   if grid[y][x] == grid[H-1-y][W-1-x]) / (W*H)

    lr, tb, r = sym_lr(), sym_tb(), sym_180()
    sym_best = max(lr, tb, r)

    # 3. 주기성 (간단): 가로 + 세로 주기 최대
    def periodicity():
        best = 0
        for P in range(2, min(W, H)//2 + 1):
            if W - P > 0:
                d = H * (W-P)
                m = sum(1 for y in range(H) for x in range(W-P)
                        if grid[y][x] == grid[y][x+P])
                best = max(best, m/d if d else 0)
            if H - P > 0:
                d = (H-P) * W
                m = sum(1 for y in range(H-P) for x in range(W)
                        if grid[y][x] == grid[y+P][x])
                best = max(best, m/d if d else 0)
        return best
    peri = periodicity()

    # 4. 노이즈 페널티: bg 비율 (완화 — 과도하지 않게)
    bg_ratio = bg_count / (W * H)
    noise_penalty = max(0, bg_ratio - 0.10) * 20  # 10% 초과분만 페널티

    # 5. 스캐터 페널티: 고립된 빈칸 = "쥐파먹은" 지표 (비율 기반)
    scatter = _scatter_count(grid, W, H, bg)
    scatter_ratio = scatter / (W * H)
    scatter_penalty = scatter_ratio * 200   # 강화 (사용자 별로 평가 강함)

    # 6. 외곽 행/열 통째 bg 위반
    full_bg_edge = _full_bg_edge(grid, W, H, bg)

    # 7. bg cluster 수: 1개가 best (사용자 선호: 모아진 빈칸)
    #   강화 (2026-04-29): 10→25. 산발 빈칸을 더 강하게 페널티.
    bg_clusters = _bg_cluster_count(grid, W, H, bg) if bg_count > 0 else 0
    cluster_penalty = max(0, bg_clusters - 1) * 25

    # 8. 색 dominance: 한 색이 너무 크면 페널티 (균형)
    if fills and n_used > 0:
        max_color_ratio = max(fills.values()) / sum(fills.values())
        ideal_ratio = 1.0 / n_used
        dominance_excess = max(0, max_color_ratio - ideal_ratio * 1.3)  # 30% 초과
        dominance_penalty = dominance_excess * 25
    else:
        dominance_penalty = 0

    # 9. 가장 큰 단일색 region (균형: 너무 큰 영역만 페널티)
    largest_comp = _largest_color_component(grid, W, H, bg)
    expected_comp = 1.0 / max(n_used, 1)
    comp_excess = max(0, largest_comp - expected_comp * 1.5)  # 50% 초과만
    component_penalty = comp_excess * 30

    # 종합 점수:
    #   대칭 + 주기성이 최상위 심미 요소 (클린한 링/스트라이프)
    composite = (
        color_match * 40
        + (30 if is_10_mult else 0)
        + sym_best * 15
        + peri * 25
        - noise_penalty * 5
        - scatter_penalty
        - cluster_penalty          # bg cluster 다수만 페널티 (5점)
        # dominance, component 페널티 제거 — kaleidoscope 등 사용자 좋다 패턴 보존
    )

    return {
        'composite': composite,
        'is_10_mult': is_10_mult,
        'sym_lr': lr, 'sym_tb': tb, 'sym_180': r, 'sym_best': sym_best,
        'periodicity': peri,
        'bg_ratio': bg_ratio,
        'n_used': n_used,
        'color_match': color_match,
        'scatter': scatter,
        'full_bg_edge': full_bg_edge,
        'bg_clusters': bg_clusters,
        'dominance_penalty': dominance_penalty,
        'largest_component': largest_comp,
        'component_penalty': component_penalty,
    }


# ─────────────────────────────────────────────────────
# 메인: 변형 양산 + 채택
# ─────────────────────────────────────────────────────
def _grid_to_rgb(grid, palette_rgb, bg_rgb=(255, 255, 255, 0)):
    """Grid (int index 또는 'K' 또는 RGBA tuple)를 모두 RGBA tuple grid로 통일.
    bg_rgb는 alpha=0 (투명). 팔레트 색은 alpha=255 (불투명)."""
    def _opaque(c):
        if len(c) == 4:
            return c
        return (c[0], c[1], c[2], 255)

    result = []
    for row in grid:
        new_row = []
        for c in row:
            if c == 'K':
                new_row.append(bg_rgb)
            elif isinstance(c, int):
                if 0 <= c < len(palette_rgb):
                    new_row.append(_opaque(palette_rgb[c]))
                else:
                    new_row.append(bg_rgb)
            elif isinstance(c, tuple):
                if len(c) == 3:
                    new_row.append((c[0], c[1], c[2], 255))
                else:
                    new_row.append(c)
            else:
                new_row.append(bg_rgb)
        result.append(new_row)
    return result


def gen_origin_grid(entry: dict) -> list:
    """원본 모티프 = run_all.py가 생성하는 이미지와 동일 (generate_pattern 사용).
    RGBA 4-tuple 그리드 반환 (bg는 alpha 0)."""
    from pixel_pattern_api import generate_pattern
    W, H = entry['width'], entry['height']
    colors = entry['colors']
    pattern = entry['pattern']
    seed = entry.get('seed', entry['_meta']['level'])
    img = generate_pattern(pattern, W, H, block_size=30, colors=colors, seed=seed,
                           transparent_bg=True)
    img = img.convert('RGBA')
    px = img.load()
    return [[px[gx*30+15, gy*30+15] for gx in range(W)] for gy in range(H)]


def process_level(entry: dict, save_all_variants: bool = False,
                  variants_to_try=('P', 'A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'),
                  extended_seeds: int = 30) -> dict:
    lv = entry['_meta']['level']
    pattern = entry['pattern']
    W, H = entry['width'], entry['height']
    colors = entry['colors']
    n = len(colors)
    seed = entry.get('seed', lv)
    from pixel_pattern_api import _hex_to_rgb
    palette_rgb = [_hex_to_rgb(c) for c in colors]

    def try_variant(vid, extra_seed=0):
        try:
            v_seed = seed + extra_seed
            grid = gen_variant(vid, pattern, W, H, n, colors, v_seed)
            if grid is None: return None
            rgb_grid = _grid_to_rgb(grid, palette_rgb)
            bg = (255, 255, 255, 0)

            # 'P' 변형은 plan_counts 기반 = 이미 10-mult 자연 달성, balance 스킵
            if vid == 'P':
                rgb_grid = _swap_edge_bg(rgb_grid, W, H, bg)
                sc = score_grid(rgb_grid, W, H, n_requested=n)
                return {'variant': vid, 'grid': rgb_grid, 'score': sc}

            from blank_engine import strategies_for, replace_cells, classify_pattern
            ptype = classify_pattern(pattern)
            candidates_blanked = [rgb_grid]
            for name, cells in strategies_for(ptype, W, H, bg):
                if cells:
                    candidates_blanked.append(replace_cells(rgb_grid, cells, bg))
            best_result = None
            for cand_grid in candidates_blanked:
                balanced = balance_to_x10(cand_grid, W, H, bg_marker=bg)
                balanced = _swap_edge_bg(balanced, W, H, bg)
                sc = score_grid(balanced, W, H, n_requested=n)
                priority = (
                    0 if sc['is_10_mult'] else 1,
                    1 if sc.get('full_bg_edge', 0) > 0 else 0,
                    -sc['composite'],
                )
                if best_result is None or priority < best_result[0]:
                    best_result = (priority, balanced, sc)
            if best_result is None: return None
            _, grid_balanced, score = best_result
            return {'variant': vid, 'grid': grid_balanced, 'score': score}
        except Exception:
            return None

    # 1단계: 기본 변형 7개
    candidates = []
    for vid in variants_to_try:
        c = try_variant(vid)
        if c: candidates.append(c)

    # 2단계: 10배수 통과한 것만 필터
    pass10 = [c for c in candidates if c['score']['is_10_mult']]

    # 2.5단계: 10x + 단일cluster (cluster≤1) 후보가 있는지 확인
    #   chevron 등은 P가 cluster=21로 10x만 통과 → "쥐파먹은" 모양 채택 방지
    pass10_clean = [c for c in pass10 if c['score'].get('bg_clusters', 99) <= 1]

    # 3단계: 깨끗한 10x 후보 없으면 추가 seed로 확장 탐색
    #   목표: 10x ✓ + cluster ≤ 1 동시 만족.
    #   못 찾아도 cluster ≤ 8 (chevron 21 같은 극단치만 차단)이면 채택.
    if not pass10_clean:
        for extra in range(1, extended_seeds + 1):
            for vid in ('B', 'C', 'D', 'E'):
                c = try_variant(vid, extra_seed=extra * 73)
                if c and c['score']['is_10_mult']:
                    candidates.append(c)
                    pass10.append(c)
                    if c['score'].get('bg_clusters', 99) <= 1:
                        pass10_clean.append(c)
            if pass10_clean:  # 깨끗한 거 하나라도 찾으면 그만
                break

    if not candidates:
        return None

    # 차단 로직: 모든 10x 후보의 cluster가 극단(>8)이면 그 레벨 거부.
    #   사용자 결정: 10배수 깨진 채로 저장하지 않음. 빈칸이 산발이면 차라리 실패.
    CLUSTER_HARD_LIMIT = 8
    if pass10:
        min_cluster_in_10x = min(c['score'].get('bg_clusters', 99) for c in pass10)
        if min_cluster_in_10x > CLUSTER_HARD_LIMIT:
            # 10x 통과한 모든 후보가 cluster > 8 — 빈칸 너무 산발 → 거부
            return None

    # 4단계: 10배수 통과한 것 중 최고 선택. 없으면 전체 중 최고 (fallback)
    #   우선순위: is_10_mult > _P(planned) AND bg=0 여부 > composite
    #   _P bg=0은 쥐파먹음 0 보장 + 사용자 검증 = 최우선.
    #   _P bg>0은 composite 경쟁 — bg shape 따라 호불호 갈림.
    pool = pass10 if pass10 else candidates
    def _rank_key(c):
        s = c['score']
        is_planned = (c['variant'] == 'P')
        bg_zero = is_planned and s.get('bg_ratio', 1.0) == 0
        edge_violation = s.get('full_bg_edge', 0) > 0
        bg_clusters = s.get('bg_clusters', 0)
        # _P 깨끗한 봇-layout: 100% 대칭 + 외곽 위반 X + 10x + 단일 cluster → 우선 채택
        # bg_ratio 무관 (인터리브 layout은 bg 비율 큰 경우도 깔끔)
        p_clean = (is_planned and s['is_10_mult']
                   and s['sym_best'] >= 0.99
                   and not edge_violation
                   and s.get('scatter', 0) == 0
                   and bg_clusters <= 1)
        return (
            0 if s['is_10_mult'] else 1,
            1 if edge_violation else 0,
            0 if p_clean else 1,           # _P clean (대칭+외곽X+스캐터X+단일cluster) 우선
            0 if bg_zero else 1,
            min(bg_clusters, 4),           # cluster 1,2,3,4까지 변별, 5+는 동률 (composite로 결정)
            -s['composite'],
        )
    best = min(pool, key=_rank_key)
    return {
        'level': lv,
        'chosen_variant': best['variant'],
        'chosen_grid': best['grid'],
        'chosen_score': best['score'],
        'all_candidates': candidates,
        'passed_10mult': len(pass10),
    }


def save_grid_as_png(grid: list, W: int, H: int, path: Path, block: int = 30,
                     overwrite: bool = False):
    """RGBA tuple grid를 PNG로 저장 (bg = alpha 0, 팔레트 색 = alpha 255).
    grid 셀은 (R,G,B,A) 4-tuple 또는 (R,G,B) 3-tuple 둘 다 허용."""
    if not overwrite and path.exists():
        return False  # 스킵됨
    img = Image.new('RGBA', (W*block, H*block), (0, 0, 0, 0))
    px = img.load()
    for gy in range(H):
        for gx in range(W):
            c = grid[gy][gx]
            if isinstance(c, tuple):
                col = c if len(c) == 4 else (c[0], c[1], c[2], 255)
            else:
                col = (0, 0, 0, 0)
            for py in range(block):
                for ppx in range(block):
                    px[gx*block+ppx, gy*block+py] = col
    img.save(path)
    return True


def main(save_all: bool = False, overwrite: bool = False):
    cfg = json.load(open('batch_config_levels.json', encoding='utf-8'))
    out_dir = Path('output_patterns')
    out_dir.mkdir(exist_ok=True)

    print(f"변형 양산 + 필수조건(10배수) 필터링 + 최적 채택")
    print(f"조건: (1) W×H 일치 (2) 색상 일치 (3) 배경 제외 10배수\n")
    print(f"{'Lv':>4} {'패턴':18s} {'채택':>4} {'10배수':>5} {'대칭':>5} {'색수':>4} {'종합':>6}")
    print('-' * 70)

    variant_counts = Counter()
    failed_10mult = []
    generated = 0
    chosen_report = {}  # lv → {variant, score}

    for e in cfg['patterns']:
        lv = e['_meta']['level']
        # 변형 파일들 경로
        origin_path = out_dir / f'level_{lv:03d}_origin.png'
        variant_paths = {v: out_dir / f'level_{lv:03d}_{v}.png'
                          for v in 'PABCDEFGH'}

        # 이미 생성된 파일이 있는지 확인
        all_files_exist = origin_path.exists() and all(p.exists() for p in variant_paths.values())

        if all_files_exist and not overwrite:
            # 기존 파일 사용 - 재생성 안 함, 평가만
            from PIL import Image
            def load_grid(path):
                img = Image.open(path).convert('RGBA')
                W = img.size[0]//30; H = img.size[1]//30
                px = img.load()
                return [[px[gx*30+15, gy*30+15] for gx in range(W)] for gy in range(H)]
            candidates = []
            for v, p in variant_paths.items():
                try:
                    grid = load_grid(p)
                    score = score_grid(grid, e['width'], e['height'], n_requested=len(e['colors']))
                    candidates.append({'variant': v, 'grid': grid, 'score': score})
                except: pass
            pass10 = [c for c in candidates if c['score']['is_10_mult']]
            pool = pass10 if pass10 else candidates
            if not pool: continue
            def _rk(c):
                s = c['score']
                is_planned = (c['variant'] == 'P')
                bg_zero = is_planned and s.get('bg_ratio', 1.0) == 0
                edge_violation = s.get('full_bg_edge', 0) > 0
                bg_clusters = s.get('bg_clusters', 0)
                p_clean = (is_planned and s['is_10_mult']
                           and s['sym_best'] >= 0.99
                           and not edge_violation
                           and s.get('scatter', 0) == 0
                           and bg_clusters <= 1)
                return (0 if s['is_10_mult'] else 1,
                        1 if edge_violation else 0,
                        0 if p_clean else 1,
                        0 if bg_zero else 1,
                        min(bg_clusters, 4),
                        -s['composite'])
            best = min(pool, key=_rk)
        else:
            # 신규 생성
            result = process_level(e, save_all_variants=save_all)
            if result is None: continue
            # origin 저장 (덮어쓰지 않음)
            try:
                if not origin_path.exists() or overwrite:
                    origin_grid = gen_origin_grid(e)
                    save_grid_as_png(origin_grid, e['width'], e['height'],
                                     origin_path, overwrite=overwrite)
            except Exception: pass
            # 변형 파일들 저장 (덮어쓰지 않음)
            for cand in result['all_candidates']:
                vp = variant_paths[cand['variant']]
                save_grid_as_png(cand['grid'], e['width'], e['height'],
                                 vp, overwrite=overwrite)
            def _rk(c):
                s = c['score']
                is_planned = (c['variant'] == 'P')
                bg_zero = is_planned and s.get('bg_ratio', 1.0) == 0
                edge_violation = s.get('full_bg_edge', 0) > 0
                bg_clusters = s.get('bg_clusters', 0)
                p_clean = (is_planned and s['is_10_mult']
                           and s['sym_best'] >= 0.99
                           and not edge_violation
                           and s.get('scatter', 0) == 0
                           and bg_clusters <= 1)
                return (0 if s['is_10_mult'] else 1,
                        1 if edge_violation else 0,
                        0 if p_clean else 1,
                        0 if bg_zero else 1,
                        min(bg_clusters, 4),
                        -s['composite'])
            pool_c = [c for c in result['all_candidates'] if c['score']['is_10_mult']] \
                     or result['all_candidates']
            best = min(pool_c, key=_rk)
            generated += 1

        chosen = best['variant']
        s = best['score']
        variant_counts[chosen] += 1
        if not s['is_10_mult']:
            failed_10mult.append(lv)
        chosen_report[lv] = {
            'chosen': chosen,
            'is_10_mult': s['is_10_mult'],
            'sym_best': round(s['sym_best']*100, 1),
            'n_used': s['n_used'],
            'composite': round(s['composite'], 1),
        }
        print(f'{lv:>4} {e["pattern"]:18s} _{chosen:<3} '
              f'{"✅" if s["is_10_mult"] else "❌":>3} '
              f'{s["sym_best"]*100:>4.0f}% {s["n_used"]}/{len(e["colors"])} '
              f'{s["composite"]:>5.1f}')

    # 채택 결과 JSON 저장
    json.dump(chosen_report, open('chosen_variants.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)

    print()
    print(f'변형 채택 분포:')
    for v, c in sorted(variant_counts.items()):
        print(f'  _{v}: {c}개')
    print(f'\n💾 신규 생성: {generated}개 | 기존 유지: {len(cfg["patterns"]) - generated}개')
    print(f'📋 채택 리포트: chosen_variants.json')
    if failed_10mult:
        print(f'\n⚠ 10배수 미달: {failed_10mult}')
    else:
        print(f'\n✅ 전체 10배수 달성')


if __name__ == '__main__':
    import sys
    save_all = '--no-save-all' not in sys.argv
    overwrite = '--regenerate' in sys.argv
    main(save_all=save_all, overwrite=overwrite)
