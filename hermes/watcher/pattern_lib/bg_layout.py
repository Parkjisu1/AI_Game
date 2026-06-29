"""
bg_layout.py
============
패턴별 빈칸(bg) 위치를 결정하는 봇.

두 단계 워크플로우:
  1. propose_layouts(pattern, W, H, n_bg, hints) → bg cells set 후보 N개
  2. score_layout(layout, W, H, pattern, hints) → 사전 점수 (대칭/콤팩트/외곽-안전/패턴-적합)

generator는 이 봇이 결정한 bg 위치를 받아 그 외 영역에 색만 채움.
"""
from typing import List, Set, Tuple, Dict


CellSet = Set[Tuple[int, int]]


def _is_180_symmetric(cells: CellSet, W: int, H: int) -> bool:
    return all((W - 1 - x, H - 1 - y) in cells for (x, y) in cells)


def _is_lr_symmetric(cells: CellSet, W: int) -> bool:
    return all((W - 1 - x, y) in cells for (x, y) in cells)


def _is_tb_symmetric(cells: CellSet, H: int) -> bool:
    return all((x, H - 1 - y) in cells for (x, y) in cells)


def _violates_edge(cells: CellSet, W: int, H: int) -> bool:
    """외곽 행/열 통째 bg 위반 여부."""
    if not cells:
        return False
    if all((x, 0) in cells for x in range(W)): return True
    if H > 1 and all((x, H - 1) in cells for x in range(W)): return True
    if all((0, y) in cells for y in range(H)): return True
    if W > 1 and all((W - 1, y) in cells for y in range(H)): return True
    return False


def score_layout(layout: CellSet, W: int, H: int,
                   pattern: str = "", hints: dict = None) -> float:
    """layout 자체 점수 (높을수록 좋음).
    +대칭 (180°/LR/TB)
    +콤팩트 (cells 간 평균 거리 작을수록)
    +패턴 적합도 (handler가 align 잘 됐는지)
    -외곽 위반 (감점)
    """
    if not layout:
        return 0.0
    n = len(layout)
    score = 0.0

    # 1. 대칭
    if _is_180_symmetric(layout, W, H):
        score += 30
    elif _is_lr_symmetric(layout, W):
        score += 15
    elif _is_tb_symmetric(layout, H):
        score += 15

    # 2. 콤팩트 (cells의 bbox 면적 대비 cells 수)
    xs = [x for x, y in layout]
    ys = [y for x, y in layout]
    bbox_w = max(xs) - min(xs) + 1
    bbox_h = max(ys) - min(ys) + 1
    bbox_area = bbox_w * bbox_h
    fill_ratio = n / bbox_area  # 1.0이면 완전 사각
    score += 25 * fill_ratio

    # 3. 외곽 위반
    if _violates_edge(layout, W, H):
        score -= 100

    # 4. 가운데 가까움 (cell들의 무게중심이 grid 중심에 가까울수록)
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    avg_x = sum(xs) / n
    avg_y = sum(ys) / n
    dist_from_center = ((avg_x - cx) ** 2 + (avg_y - cy) ** 2) ** 0.5
    max_dist = ((W / 2) ** 2 + (H / 2) ** 2) ** 0.5
    score += 15 * (1 - dist_from_center / max(max_dist, 1))

    return score


# ─────────────────────────────────────────────────────
# Pattern-specific handlers
# ─────────────────────────────────────────────────────
def _stripe_layouts(W: int, H: int, n_bg: int, hints: dict) -> List[CellSet]:
    """Stripe bg layout 후보:
       (a) 인터리브: color stripes 사이에 bg gap (외곽 = 색 stripe, 가장 깔끔)
       (b) 중앙 통째 column(s)
       (c) 중앙 통째 row(s)
       (d) 정사각 cluster (n_bg가 col/row 단위로 안 떨어질 때)
    """
    candidates = []
    if n_bg <= 0:
        return [set()]
    n_colors = hints.get('n_colors', 0)
    stripe_width = hints.get('stripe_width', 0)

    # 후보 (a): 인터리브 — [color stripe][bg gap][color stripe][bg gap]...[color stripe]
    if n_colors >= 2 and stripe_width > 0 and n_bg % H == 0:
        bg_cols = n_bg // H
        n_color_cols = stripe_width * n_colors
        if n_color_cols + bg_cols == W and bg_cols > 0:
            n_gaps = n_colors - 1
            if n_gaps > 0:
                gap_widths = [bg_cols // n_gaps +
                              (1 if i < bg_cols % n_gaps else 0)
                              for i in range(n_gaps)]
                # 외곽은 색 stripe
                cells = set()
                cursor = stripe_width
                for gap_w in gap_widths:
                    for dx in range(gap_w):
                        x = cursor + dx
                        if 0 <= x < W:
                            for y in range(H):
                                cells.add((x, y))
                    cursor += gap_w + stripe_width
                if len(cells) == n_bg and not _violates_edge(cells, W, H):
                    candidates.append(cells)
        # 가로 방향 인터리브 (rows)
        if n_bg % W == 0:
            bg_rows = n_bg // W
            if stripe_width * n_colors + bg_rows == H and bg_rows > 0:
                n_gaps = n_colors - 1
                if n_gaps > 0:
                    gap_widths = [bg_rows // n_gaps +
                                  (1 if i < bg_rows % n_gaps else 0)
                                  for i in range(n_gaps)]
                    cells = set()
                    cursor = stripe_width
                    for gap_w in gap_widths:
                        for dy in range(gap_w):
                            y = cursor + dy
                            if 0 <= y < H:
                                for x in range(W):
                                    cells.add((x, y))
                        cursor += gap_w + stripe_width
                    if len(cells) == n_bg and not _violates_edge(cells, W, H):
                        candidates.append(cells)

    # 후보 (b): 중앙 통째 column(s)
    if n_bg % H == 0:
        k_cols = n_bg // H
        if 1 <= k_cols <= W - 2:
            start = (W - k_cols) // 2
            cells = {(start + dx, y) for dx in range(k_cols) for y in range(H)}
            if not _violates_edge(cells, W, H):
                if cells not in candidates:
                    candidates.append(cells)

    # 후보 (c): 중앙 통째 row(s)
    if n_bg % W == 0:
        k_rows = n_bg // W
        if 1 <= k_rows <= H - 2:
            start = (H - k_rows) // 2
            cells = {(x, start + dy) for dy in range(k_rows) for x in range(W)}
            if not _violates_edge(cells, W, H):
                if cells not in candidates:
                    candidates.append(cells)

    # 후보 (d): 정사각 cluster fallback
    if not candidates:
        cells = _square_cluster(W, H, n_bg)
        if cells:
            candidates.append(cells)

    return candidates


def _checker_layouts(W: int, H: int, n_bg: int, hints: dict) -> List[CellSet]:
    """Checkerboard bg layout 후보:
       (a) tile_size 단위 임의 a×b 직사각 cluster (n_tiles = a*b)
       (b) 외곽 안 침범, 중앙 정렬
    """
    candidates = []
    if n_bg <= 0:
        return [set()]

    tile_size = hints.get('tile_size', 4) if hints else 4
    if tile_size < 1:
        tile_size = 1
    tile_area = tile_size * tile_size

    if n_bg % tile_area == 0:
        n_tiles = n_bg // tile_area
        tx_max = W // tile_size
        ty_max = H // tile_size
        # 임의 a×b 직사각 cluster (a ≤ b, |a-b| 작은 것 우선)
        ab_pairs = []
        for a in range(1, int(n_tiles ** 0.5) + 2):
            if n_tiles % a == 0:
                b = n_tiles // a
                ab_pairs.append((a, b))
                if a != b:
                    ab_pairs.append((b, a))
        # |a-b| 작은 순 (정사각 우선)
        ab_pairs.sort(key=lambda ab: abs(ab[0] - ab[1]))
        for a, b in ab_pairs:
            # a rows × b cols of tiles, 외곽 안 침범 (각 1 tile margin)
            if a + 2 > ty_max or b + 2 > tx_max:
                continue
            txc = (tx_max - b) // 2
            tyc = (ty_max - a) // 2
            if txc < 1 or tyc < 1:
                continue
            if txc + b > tx_max - 1 or tyc + a > ty_max - 1:
                continue
            cells = set()
            for ty_off in range(a):
                for tx_off in range(b):
                    for dx in range(tile_size):
                        for dy in range(tile_size):
                            cells.add(((txc + tx_off) * tile_size + dx,
                                       (tyc + ty_off) * tile_size + dy))
            if not _violates_edge(cells, W, H):
                candidates.append(cells)

    # fallback: 정사각 cluster (cell-단위)
    if not candidates:
        cells = _square_cluster(W, H, n_bg)
        if cells:
            candidates.append(cells)

    return candidates


def _rect_grid_layouts(W: int, H: int, n_bg: int, hints: dict) -> List[CellSet]:
    """Rect_grid bg layout 후보:
       (a) tile_w × tile_h 단위 임의 a×b 직사각 cluster
       (b) 좌우/상하 대칭 분산 (n_tiles 짝수)
       (c) cell-단위 정사각 cluster (fallback)
    """
    candidates = []
    if n_bg <= 0:
        return [set()]

    tile_w = hints.get('tile_w', 5) if hints else 5
    tile_h = hints.get('tile_h', 5) if hints else 5
    if tile_w < 1: tile_w = 1
    if tile_h < 1: tile_h = 1
    tile_area = tile_w * tile_h

    if n_bg % tile_area == 0:
        n_tiles = n_bg // tile_area
        tx_max = W // tile_w
        ty_max = H // tile_h

        # 임의 a×b 직사각 cluster
        ab_pairs = []
        for a in range(1, int(n_tiles ** 0.5) + 2):
            if n_tiles % a == 0:
                b = n_tiles // a
                ab_pairs.append((a, b))
                if a != b:
                    ab_pairs.append((b, a))
        ab_pairs.sort(key=lambda ab: abs(ab[0] - ab[1]))
        for a, b in ab_pairs:
            if a + 2 > ty_max or b + 2 > tx_max:
                continue
            txc = (tx_max - b) // 2
            tyc = (ty_max - a) // 2
            if txc < 1 or tyc < 1:
                continue
            cells = set()
            for ty_off in range(a):
                for tx_off in range(b):
                    for dx in range(tile_w):
                        for dy in range(tile_h):
                            cells.add(((txc + tx_off) * tile_w + dx,
                                       (tyc + ty_off) * tile_h + dy))
            if not _violates_edge(cells, W, H):
                candidates.append(cells)

        # 좌우 대칭 분산 (각 끝 1 tile씩, n_tiles=2일 때)
        if n_tiles == 2 and tx_max >= 4 and ty_max >= 3:
            tyc = (ty_max - 1) // 2
            txc1 = 1
            txc2 = tx_max - 2
            if txc1 < txc2:
                cells = set()
                for tx in [txc1, txc2]:
                    for dx in range(tile_w):
                        for dy in range(tile_h):
                            cells.add((tx * tile_w + dx, tyc * tile_h + dy))
                if not _violates_edge(cells, W, H):
                    if cells not in candidates:
                        candidates.append(cells)

    if not candidates:
        cells = _square_cluster(W, H, n_bg)
        if cells:
            candidates.append(cells)

    return candidates


def _brick_layouts(W: int, H: int, n_bg: int, hints: dict) -> List[CellSet]:
    """Brick bg layout 후보:
       (a) brick_w × brick_h tile 단위 직사각 cluster
       (b) row-shift 고려: 짝수 row는 offset 0, 홀수 row는 brick_w//2 offset
    """
    candidates = []
    if n_bg <= 0:
        return [set()]
    bw = hints.get('brick_w', 5) if hints else 5
    bh = hints.get('brick_h', 4) if hints else 4
    if bw < 1: bw = 1
    if bh < 1: bh = 1
    ba = bw * bh

    if n_bg % ba == 0:
        n_tiles = n_bg // ba
        # brick은 row-shift 있으므로 단순 a×b cluster이 정확 안 들어맞음
        # 대신 한 row of n_tiles bricks 또는 직사각 cluster 시도
        ab_pairs = []
        for a in range(1, int(n_tiles ** 0.5) + 2):
            if n_tiles % a == 0:
                b = n_tiles // a
                ab_pairs.append((a, b))
                if a != b:
                    ab_pairs.append((b, a))
        ab_pairs.sort(key=lambda ab: abs(ab[0] - ab[1]))
        # 각 (a, b)에 대해 중앙 cluster 위치
        rows_n = H // bh
        cols_n = W // bw
        for a, b in ab_pairs:
            if a + 2 > rows_n or b + 2 > cols_n:
                continue
            tyc = (rows_n - a) // 2
            txc = (cols_n - b) // 2
            if tyc < 1 or txc < 1:
                continue
            cells = set()
            for ty_off in range(a):
                for tx_off in range(b):
                    row_idx = tyc + ty_off
                    off = bw // 2 if row_idx % 2 == 1 else 0
                    for dy in range(bh):
                        for dx in range(bw):
                            x = (txc + tx_off) * bw + dx - off
                            y = row_idx * bh + dy
                            if 0 <= x < W and 0 <= y < H:
                                cells.add((x, y))
            if not _violates_edge(cells, W, H) and len(cells) > 0:
                candidates.append(cells)

    if not candidates:
        cells = _square_cluster(W, H, n_bg)
        if cells:
            candidates.append(cells)

    return candidates


def _chevron_layouts(W: int, H: int, n_bg: int, hints: dict) -> List[CellSet]:
    """Chevron bg layout 후보:
       (a) V-band 통째 — (y + |x-cx|) // band 가 같은 cells region
       (b) 중앙 정사각/직사각 cluster
       (c) 가로 row-stripe (V 형태 흩뿌림 회피)
    """
    candidates = []
    if n_bg <= 0:
        return [set()]
    band = hints.get('band', 5) if hints else 5
    if band < 1: band = 1
    cx = W // 2

    # V band별 cell 수집
    bands = {}
    for y in range(H):
        for x in range(W):
            b_idx = (y + abs(x - cx)) // band
            bands.setdefault(b_idx, set()).add((x, y))

    # 한 V band 통째 (외곽 침범 X)
    max_b = max(bands.keys())
    for b_idx, cells in sorted(bands.items()):
        if len(cells) == n_bg:
            if not _violates_edge(cells, W, H):
                candidates.append(set(cells))

    # 인접 V band 합 (n_bg 매칭 시도)
    sorted_b = sorted(bands.keys())
    for start_idx in range(len(sorted_b)):
        cum = set()
        for end_idx in range(start_idx, len(sorted_b)):
            cum |= bands[sorted_b[end_idx]]
            if len(cum) == n_bg:
                if not _violates_edge(cum, W, H):
                    candidates.append(set(cum))
                break
            if len(cum) > n_bg:
                break

    # 중앙 정사각 cluster fallback
    sq = _square_cluster(W, H, n_bg)
    if sq and sq not in candidates:
        candidates.append(sq)
    return candidates


def _diamond_layouts(W: int, H: int, n_bg: int, hints: dict) -> List[CellSet]:
    """Diamond_check bg layout:
       (a) Manhattan ring (다이아 ring 통째)
       (b) 중앙 다이아 cluster
       (c) 정사각 cluster
    """
    candidates = []
    if n_bg <= 0:
        return [set()]
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0

    # Manhattan 거리 ring별 cell 수집
    rings = {}
    for y in range(H):
        for x in range(W):
            d = int(abs(x - cx) + abs(y - cy))
            rings.setdefault(d, set()).add((x, y))

    # 한 ring 통째 (외곽 ring 제외)
    max_d = max(rings.keys())
    for d, ring in sorted(rings.items()):
        if d == max_d:
            continue
        if len(ring) == n_bg:
            candidates.append(set(ring))

    # 중앙 다이아 cluster (Manhattan distance 0..k)
    cum = []
    cum_total = 0
    for d in sorted(rings.keys()):
        cum_total += len(rings[d])
        cum.append((d, cum_total))
    for d, total in cum:
        if total == n_bg:
            cells = set()
            for d2 in range(d + 1):
                cells.update(rings[d2])
            if not _violates_edge(cells, W, H):
                candidates.append(cells)

    # 정사각 cluster fallback
    sq = _square_cluster(W, H, n_bg)
    if sq and sq not in candidates:
        candidates.append(sq)

    return candidates


def _concentric_layouts(W: int, H: int, n_bg: int, hints: dict) -> List[CellSet]:
    """Concentric_sq bg layout 후보:
       (a) 한 ring 통째 (가운데 ring 우선, 외곽 ring은 외곽 위반이라 제외)
       (b) 중앙 정사각 cluster
    """
    candidates = []
    if n_bg <= 0:
        return [set()]

    # ring별 cell 집계
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    rings = {}
    for y in range(H):
        for x in range(W):
            d = int(max(abs(x - cx), abs(y - cy)))
            rings.setdefault(d, set()).add((x, y))

    # ring 면적 = n_bg와 일치하는 ring 찾기 (외곽 ring 제외 — 외곽 위반)
    max_d = max(rings.keys())
    for d in sorted(rings.keys()):
        if d == max_d:
            continue  # 외곽 ring 제외
        if len(rings[d]) == n_bg:
            candidates.append(set(rings[d]))

    # 중앙 정사각 cluster
    sq = _square_cluster(W, H, n_bg)
    if sq and sq not in candidates:
        candidates.append(sq)

    return candidates


def _square_cluster(W: int, H: int, n_bg: int) -> CellSet:
    """n_bg cells을 중앙 정사각/직사각 모양으로 배치.
    정사각 우선 → 직사각 → 1×n 폴백. 외곽 안 침범 (a+2 ≤ H, b+2 ≤ W)."""
    if n_bg <= 0:
        return set()

    # (a, b) 후보 enumerate — n_bg ≤ a*b ≤ n_bg+5, a ≤ b
    candidates_ab = []
    for a in range(1, int(n_bg ** 0.5) + 3):
        for b in range(a, n_bg + 1):
            if a * b < n_bg:
                continue
            if a * b > n_bg + 5:
                break
            if a + 2 > H or b + 2 > W:
                continue
            excess = a * b - n_bg
            shape_penalty = abs(a - b)  # 정사각 0
            candidates_ab.append((excess, shape_penalty, a, b))

    if candidates_ab:
        candidates_ab.sort()
        excess, _, a, b = candidates_ab[0]
        x0 = (W - b) // 2
        y0 = (H - a) // 2
        cells = {(x0 + dx, y0 + dy) for dx in range(b) for dy in range(a)}
        # excess > 0이면 정확히 n_bg cells로 자르기 (중앙 가까운 순)
        if len(cells) > n_bg:
            cx_, cy_ = (W - 1) / 2.0, (H - 1) / 2.0
            cells_list = sorted(cells, key=lambda p: (p[0] - cx_) ** 2 + (p[1] - cy_) ** 2)
            cells = set(cells_list[:n_bg])
        return cells

    # fallback: 1×n cells (중앙 row, 외곽 안 침범)
    if n_bg <= W - 2 and H >= 3:
        x0 = (W - n_bg) // 2
        y0 = H // 2
        return {(x0 + dx, y0) for dx in range(n_bg)}
    return set()


def _generic_layouts(W: int, H: int, n_bg: int, hints: dict) -> List[CellSet]:
    """기본 fallback: 중앙 정사각 cluster."""
    if n_bg <= 0:
        return [set()]
    cells = _square_cluster(W, H, n_bg)
    return [cells] if cells else []


def _motif_layouts(W: int, H: int, n_bg: int, hints: dict) -> List[CellSet]:
    """Motif/lattice 패턴 (plus/x/t/argyle/kaleidoscope/etc):
       (a) 중앙 정사각/직사각 cluster
       (b) 다이아 cluster
    """
    candidates = []
    if n_bg <= 0:
        return [set()]
    sq = _square_cluster(W, H, n_bg)
    if sq:
        candidates.append(sq)
    return candidates


LAYOUT_HANDLERS: Dict[str, callable] = {
    'stripe': _stripe_layouts,
    'checkerboard': _checker_layouts,
    'rect_grid': _rect_grid_layouts,
    'concentric_sq': _concentric_layouts,
    'brick': _brick_layouts,
    'diamond_check': _diamond_layouts,
    'chevron': _chevron_layouts,
    'plus_motif': _motif_layouts,
    'x_motif': _motif_layouts,
    't_motif': _motif_layouts,
    'argyle': _motif_layouts,
    'kaleidoscope': _motif_layouts,
    'wave': _motif_layouts,
    'hex_tile': _motif_layouts,
    'maze': _motif_layouts,
    'i_tetromino': _motif_layouts,
    'truchet': _motif_layouts,
    'xor_fractal': _motif_layouts,
    'sierpinski_carpet': _motif_layouts,
}


def propose_layouts(pattern: str, W: int, H: int, n_bg: int,
                       hints: dict = None) -> List[CellSet]:
    """패턴별 bg layout 후보 N개 반환. 점수순으로 정렬.
    빈 set만 반환되면 후보 없음."""
    hints = hints or {}
    handler = LAYOUT_HANDLERS.get(pattern, _generic_layouts)
    candidates = handler(W, H, n_bg, hints)
    # 점수순 정렬 (높은 점수 우선)
    candidates.sort(key=lambda L: -score_layout(L, W, H, pattern, hints))
    return candidates


def best_layout(pattern: str, W: int, H: int, n_bg: int,
                  hints: dict = None) -> CellSet:
    """가장 높은 점수의 layout 1개 반환. 후보 없으면 None."""
    layouts = propose_layouts(pattern, W, H, n_bg, hints)
    return layouts[0] if layouts else None
