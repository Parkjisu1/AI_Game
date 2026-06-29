"""
패턴 타입별 빈칸 배치 엔진.

"쥐파먹은" 스캐터 방지 — 각 패턴의 수학적 특성(주기/대칭)에 맞춰 빈칸 배치.

핵심 아이디어:
  - 패턴 분류 → 그 패턴에 자연스러운 전략들만 후보로
  - 각 전략 적용 → 가장 10배수에 근접 + 심미적인 것 선택
  - balance_to_x10 orbit 스캐터 방식과 별개/위에서 동작
"""
from collections import Counter


# ─────────────────────────────────────────────────────
# 패턴 분류
# ─────────────────────────────────────────────────────
PATTERN_CLASS = {
    # 1D 주기 (가로 or 세로 반복 밴드)
    'stripe': 'periodic_1d',
    'chevron': 'periodic_1d',

    # 파동 (수평 밴드, zigzag 리듬)
    'wave': 'wave',

    # 2D 주기 (타일 반복)
    'rect_grid': 'periodic_2d',
    'brick': 'periodic_2d',
    'i_tetromino': 'periodic_2d',
    'checkerboard': 'periodic_2d',

    # 모티프 (각 타일에 도형)
    'plus_motif': 'motif_tile',
    't_motif': 'motif_tile',
    'x_motif': 'motif_tile',
    'argyle': 'motif_tile',
    'diamond_check': 'motif_tile',

    # 중심 대칭 (radial)
    'concentric_sq': 'symmetric_center',
    'kaleidoscope': 'symmetric_center',
    'hex_tile': 'symmetric_center',

    # 유기/랜덤
    'maze': 'maze',
    'truchet': 'maze',

    # 프랙탈 (자기유사)
    'xor_fractal': 'fractal',
    'sierpinski_carpet': 'fractal',
}


def classify_pattern(pattern_name: str) -> str:
    return PATTERN_CLASS.get(pattern_name, 'generic')


# ─────────────────────────────────────────────────────
# 기본 조작 함수
# ─────────────────────────────────────────────────────
def replace_cells(grid, cells, bg):
    new_grid = [row[:] for row in grid]
    for (y, x) in cells:
        if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
            new_grid[y][x] = bg
    return new_grid


def cells_row(W, y):
    return [(y, x) for x in range(W)]


def cells_col(H, x):
    return [(y, x) for y in range(H)]


def cells_corner_block(W, H, size, corners='4'):
    """corners: '4' (all 4), 'diag' (TL+BR), 'antidiag' (TR+BL)."""
    cells = []
    if corners == '4':
        origins = [(0, 0), (0, W-size), (H-size, 0), (H-size, W-size)]
    elif corners == 'diag':
        origins = [(0, 0), (H-size, W-size)]
    elif corners == 'antidiag':
        origins = [(0, W-size), (H-size, 0)]
    else:
        origins = []
    for (cy, cx) in origins:
        for dy in range(size):
            for dx in range(size):
                y, x = cy+dy, cx+dx
                if 0 <= y < H and 0 <= x < W:
                    cells.append((y, x))
    return cells


def cells_center_axis_h(W, H, thickness=1):
    """수평 중앙축 (thickness줄)."""
    cells = []
    mid = H // 2
    for d in range(-(thickness//2), thickness - thickness//2):
        y = mid + d
        if 0 <= y < H:
            cells.extend(cells_row(W, y))
    return cells


def cells_center_axis_v(W, H, thickness=1):
    """수직 중앙축."""
    cells = []
    mid = W // 2
    for d in range(-(thickness//2), thickness - thickness//2):
        x = mid + d
        if 0 <= x < W:
            cells.extend(cells_col(H, x))
    return cells


def cells_stripe_lines(W, H, direction, count, offset_frac=0.5):
    """direction='horizontal' or 'vertical'. count개 줄 빼기 (균등 배치)."""
    cells = []
    if direction == 'horizontal':
        # count개 행을 H 공간에 균등 배치
        for i in range(count):
            y = int(H * (i + 1) / (count + 1))
            cells.extend(cells_row(W, y))
    else:
        for i in range(count):
            x = int(W * (i + 1) / (count + 1))
            cells.extend(cells_col(H, x))
    return cells


def _band_lines(W, H, direction, thickness):
    """thickness개 **인접한** 줄 (중앙 밴드). 1줄 2줄 스트라이프가 아니라 두꺼운 한 덩어리."""
    cells = []
    if direction == 'horizontal':
        mid = H // 2
        start = mid - thickness // 2
        for d in range(thickness):
            y = start + d
            if 0 <= y < H:
                cells.extend(cells_row(W, y))
    else:
        mid = W // 2
        start = mid - thickness // 2
        for d in range(thickness):
            x = start + d
            if 0 <= x < W:
                cells.extend(cells_col(H, x))
    return cells


def cells_tile_pattern(W, H, tile_size, positions):
    """각 타일(tile_size × tile_size) 내 특정 상대 위치 셀만 빼기.
    positions = [(rel_y, rel_x), ...] — 타일 내 상대 좌표 리스트."""
    cells = []
    bx_max = W // tile_size
    by_max = H // tile_size
    for by in range(by_max):
        for bx in range(bx_max):
            for (ry, rx) in positions:
                y = by*tile_size + ry
                x = bx*tile_size + rx
                if 0 <= y < H and 0 <= x < W:
                    cells.append((y, x))
    return cells


# ─────────────────────────────────────────────────────
# 전략 세트 (패턴 타입별)
# ─────────────────────────────────────────────────────
def strategies_for(pattern_type, W, H, bg):
    """각 전략 = (이름, [셀 좌표 리스트])."""
    out = []

    if pattern_type == 'periodic_1d':
        # 스트라이프/chevron은 내부 관통/코너 블록 전부 금지 — 오직 프레임 엣지만
        # 전체 상하 프레임 (2줄)
        out.append(('frame_tb_2', cells_row(W, 0) + cells_row(W, 1)
                                 + cells_row(W, H-2) + cells_row(W, H-1)))
        # 전체 좌우 프레임 (2줄)
        out.append(('frame_lr_2', cells_col(H, 0) + cells_col(H, 1)
                                 + cells_col(H, W-2) + cells_col(H, W-1)))
        # 전체 4방향 프레임 1줄 (얇은 테두리)
        out.append(('frame_all_1',
                    cells_row(W, 0) + cells_row(W, H-1)
                    + cells_col(H, 0)[1:-1] + cells_col(H, W-1)[1:-1]))

    elif pattern_type == 'wave':
        # wave도 프레임만 (상하단만 — 수평 파동이라)
        out.append(('frame_tb_1', cells_row(W, 0) + cells_row(W, H-1)))
        out.append(('frame_tb_2', cells_row(W, 0) + cells_row(W, 1)
                                 + cells_row(W, H-2) + cells_row(W, H-1)))

    elif pattern_type == 'periodic_2d':
        # 타일 단위 빈 (타일 추정 3~7)
        for tile in [3, 4, 5, 6, 7]:
            if 2*tile >= min(W, H): continue
            # 4코너 타일 빼기
            out.append((f'tile_4corner_s{tile}', cells_corner_block(W, H, tile, '4')))
            # 대각 2코너만
            out.append((f'tile_diag_s{tile}', cells_corner_block(W, H, tile, 'diag')))
            out.append((f'tile_antidiag_s{tile}', cells_corner_block(W, H, tile, 'antidiag')))

    elif pattern_type == 'symmetric_center':
        # 2×2 이상만 (1×1 코너 블록은 쥐파먹은 점처럼 보임)
        for s in [2, 3]:
            if 2*s >= min(W, H): continue
            out.append((f'diag_s{s}', cells_corner_block(W, H, s, 'diag')))
            out.append((f'antidiag_s{s}', cells_corner_block(W, H, s, 'antidiag')))
            out.append((f'4corner_s{s}', cells_corner_block(W, H, s, '4')))

    elif pattern_type == 'motif_tile':
        # 타일 단위 - 1셀 전략 제거 (tile_center/tile_corner 1셀) → 2×2 이상만
        for tile in [4, 5, 6, 7]:
            if 2*tile >= min(W, H): continue
            # 타일 중심 2×2 블록
            c = tile//2
            if c >= 1:
                positions_2x2 = [(c-1, c-1), (c-1, c), (c, c-1), (c, c)]
                out.append((f'tile_center2_s{tile}',
                            cells_tile_pattern(W, H, tile, positions_2x2)))
        # 4-fold 코너 블록 (2×2 이상)
        for s in [2, 3]:
            if 2*s >= min(W, H): continue
            out.append((f'4corner_s{s}', cells_corner_block(W, H, s, '4')))

    elif pattern_type == 'maze':
        # 4코너 블록 - 2×2 이상만
        for s in [2, 3]:
            if 2*s >= min(W, H): continue
            out.append((f'4corner_s{s}', cells_corner_block(W, H, s, '4')))
            out.append((f'diag_s{s}', cells_corner_block(W, H, s, 'diag')))

    elif pattern_type == 'fractal':
        # 중앙 점 대신 2×2 이상 블록만 (1픽셀 이물질 방지)
        for s in [2, 3]:
            if 2*s >= min(W, H): continue
            out.append((f'4corner_s{s}', cells_corner_block(W, H, s, '4')))

    else:  # generic — 2×2 이상만
        for s in [2, 3]:
            if 2*s >= min(W, H): continue
            out.append((f'4corner_s{s}', cells_corner_block(W, H, s, '4')))

    # 빈칸 없는 베이스 케이스도 포함 (패턴이 이미 완벽하면)
    out.insert(0, ('no_blank', []))
    return out


# ─────────────────────────────────────────────────────
# 평가 & 선택
# ─────────────────────────────────────────────────────
def evaluate_blank_candidate(grid, W, H, bg):
    """반환: (is_10_mult, total_excess, bg_count, colors_used)"""
    cnt = Counter(c for row in grid for c in row)
    bg_count = cnt.get(bg, 0)
    fills = {c: n for c, n in cnt.items() if c != bg}
    if not fills:
        return False, 0, bg_count, 0
    excesses = [n % 10 for n in fills.values()]
    is_10_mult = all(e == 0 for e in excesses)
    return is_10_mult, sum(excesses), bg_count, len(fills)


def pattern_aware_blank(grid, W, H, pattern_name, bg=(255, 255, 255)):
    """패턴 타입에 맞는 빈칸 전략 중 최적 선택.
    반환: (best_grid, strategy_name, (is_10mult, excess, bg_count))"""
    pattern_type = classify_pattern(pattern_name)
    candidates = strategies_for(pattern_type, W, H, bg)

    best_grid = grid
    best_meta = evaluate_blank_candidate(grid, W, H, bg)
    best_name = 'no_blank'

    for name, cells in candidates:
        if not cells:
            # no_blank: 평가만 (이미 grid)
            continue
        g = replace_cells(grid, cells, bg)
        meta = evaluate_blank_candidate(g, W, H, bg)
        # 우선순위: 10배수 True > total_excess 작음 > bg 적음 > 색 많이 사용
        is_10, excess, bgc, ncolors = meta
        best_is_10, best_excess, best_bgc, best_ncolors = best_meta
        # 비교 키 (작을수록 좋음)
        key_new = (not is_10, excess, bgc, -ncolors)
        key_best = (not best_is_10, best_excess, best_bgc, -best_ncolors)
        if key_new < key_best:
            best_grid = g
            best_meta = meta
            best_name = name

    return best_grid, best_name, best_meta
