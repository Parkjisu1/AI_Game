"""
BalloonFlow Zone-Based Pattern Pipeline v42
============================================
존 기반 통합 프로세스: 구조(존) → 색상 배정(×10) → T 배치(대칭)

핵심 차이 (vs v41):
- 패턴 구조(존 맵)와 색상 배정을 분리
- ×10은 색상 배정 단계에서 처음부터 만족
- 리컬러링 0개 — 패턴 구조 100% 보존
- T 셀은 존 경계의 대칭 위치에만 배치
"""
import math, random, os, csv, json, copy
from PIL import Image
from collections import Counter, defaultdict
from typing import List, Tuple, Dict, Optional, Set

# ══════════════════════════════════════════════════════════
# 팔레트 (v41에서 그대로 가져옴)
# ══════════════════════════════════════════════════════════
PALETTE = [
    "#FC6AAF","#50E8F6","#8950F8","#FED555","#73FE66","#FDA14C",
    "#FFFFFF","#414141","#6EA8FA","#39AE2E","#FC5E5E","#326BF8",
    "#3AA58B","#E7A7FA","#B7C7FB","#6A4A30","#FEE3A9","#FDB7C1",
    "#9E3D5E","#A7DD94","#592E7E","#DC7881","#D9D9E7","#6F727F",
    "#FC38A5","#FDB458","#890A08","#6FAFB1",
]

T_VALUE = "T"

def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def color_distance(hex1, hex2):
    r1, g1, b1 = hex2rgb(hex1)
    r2, g2, b2 = hex2rgb(hex2)
    return ((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2) ** 0.5

def pick_colors(n, level, start_offset=0):
    if level <= 100: pool = PALETTE[:21]
    elif level <= 249: pool = PALETTE[:24]
    else: pool = PALETTE[:28]
    if n <= 1:
        return [pool[start_offset % len(pool)]]
    start_idx = start_offset % len(pool)
    selected = [start_idx]
    remaining = [i for i in range(len(pool)) if i != start_idx]
    for _ in range(n - 1):
        if not remaining: break
        best_idx = None
        best_min_dist = -1
        for ri in remaining:
            min_d = min(color_distance(pool[ri], pool[si]) for si in selected)
            if min_d > best_min_dist:
                best_min_dist = min_d
                best_idx = ri
        if best_idx is not None:
            selected.append(best_idx)
            remaining.remove(best_idx)
    return [pool[i] for i in selected]


# ══════════════════════════════════════════════════════════
# 핵심 자료구조: ZoneMap
# ══════════════════════════════════════════════════════════

class ZoneMap:
    """
    W×H 그리드의 각 셀이 어떤 존에 속하는지 정의.
    존은 정수 ID (0, 1, 2, ...).

    핵심 속성:
    - zones[y][x] = zone_id (정수)
    - zone_cells[zone_id] = [(y, x), ...] — 해당 존의 셀 목록
    - 존 경계는 패턴의 시각적 구조를 정의
    """
    def __init__(self, W, H):
        self.W = W
        self.H = H
        self.zones = [[0]*W for _ in range(H)]
        self._zone_cells = None  # lazy cache

    def set(self, y, x, zone_id):
        self.zones[y][x] = zone_id
        self._zone_cells = None  # invalidate cache

    def get(self, y, x):
        return self.zones[y][x]

    @property
    def zone_cells(self):
        if self._zone_cells is None:
            self._zone_cells = defaultdict(list)
            for y in range(self.H):
                for x in range(self.W):
                    self._zone_cells[self.zones[y][x]].append((y, x))
        return self._zone_cells

    @property
    def num_zones(self):
        return len(self.zone_cells)

    def zone_sizes(self):
        """각 존의 셀 수 반환: {zone_id: count}"""
        return {zid: len(cells) for zid, cells in self.zone_cells.items()}

    def total_cells(self):
        return self.W * self.H


# ══════════════════════════════════════════════════════════
# 대칭 유틸리티
# ══════════════════════════════════════════════════════════

def get_sym_group(y, x, H, W, sym_type="quad_mirror"):
    """(y,x)의 대칭 좌표 그룹 반환 (중복 제거)"""
    pts = set()
    pts.add((y, x))
    if sym_type == "quad_mirror":
        my, mx = H - 1 - y, W - 1 - x
        pts.add((y, mx))
        pts.add((my, x))
        pts.add((my, mx))
    elif sym_type == "bilateral_lr":
        pts.add((y, W - 1 - x))
    elif sym_type == "bilateral_tb":
        pts.add((H - 1 - y, x))
    elif sym_type == "rotational":
        cx, cy = (W-1)/2, (H-1)/2
        dx, dy = x - cx, y - cy
        for _ in range(3):
            dx, dy = -dy, dx
            nx, ny = int(round(cx + dx)), int(round(cy + dy))
            if 0 <= ny < H and 0 <= nx < W:
                pts.add((ny, nx))
    return list(pts)


def make_symmetric_zone_map(W, H, zone_func, sym_type="quad_mirror"):
    """
    존 생성 함수를 좌상단 1/4(또는 적절한 영역)에만 적용하고
    대칭으로 나머지를 채움 → 존 자체가 완벽 대칭
    """
    zm = ZoneMap(W, H)

    if sym_type == "quad_mirror":
        # 좌상단 1/4만 계산, 나머지는 미러
        half_h = (H + 1) // 2
        half_w = (W + 1) // 2
        for y in range(half_h):
            for x in range(half_w):
                zid = zone_func(y, x, W, H)
                for sy, sx in get_sym_group(y, x, H, W, sym_type):
                    zm.set(sy, sx, zid)
    elif sym_type == "bilateral_lr":
        half_w = (W + 1) // 2
        for y in range(H):
            for x in range(half_w):
                zid = zone_func(y, x, W, H)
                for sy, sx in get_sym_group(y, x, H, W, sym_type):
                    zm.set(sy, sx, zid)
    else:
        # rotational 등: 전체 계산 후 대칭 강제
        for y in range(H):
            for x in range(W):
                zid = zone_func(y, x, W, H)
                zm.set(y, x, zid)
        # 대칭 그룹별로 최소 zone_id로 통일
        visited = [[False]*W for _ in range(H)]
        for y in range(H):
            for x in range(W):
                if visited[y][x]: continue
                grp = get_sym_group(y, x, H, W, sym_type)
                min_zid = min(zm.get(sy, sx) for sy, sx in grp)
                for sy, sx in grp:
                    zm.set(sy, sx, min_zid)
                    visited[sy][sx] = True

    return zm


def coat_border_zone(zm, W, H, thickness=1):
    """
    외곽 thickness줄을 하나의 존으로 통합한다.
    PixelFlow 스타일: 외곽을 단일 색상으로 감싸서 플레이 순서를 강제.
    새로운 존 ID = 현재 최대 존 ID + 1.
    """
    max_zone = 0
    for y in range(H):
        for x in range(W):
            z = zm.get(y, x)
            if z > max_zone:
                max_zone = z
    border_zone_id = max_zone + 1

    for y in range(H):
        for x in range(W):
            if x < thickness or x >= W - thickness or y < thickness or y >= H - thickness:
                zm.set(y, x, border_zone_id)

    zm._zone_cells = None  # cache invalidate
    return zm


def split_disconnected_zones(zm, W, H):
    """같은 zone ID라도 공간적으로 연결되지 않은 조각은 별도 zone으로 분리.
    zone_pixel_grid, zone_flower_mandala 등이 동일 ID를 여러 곳에 배정하는 문제 해결.
    이래야 graph coloring이 인접하지 않은 조각에 서로 다른 색을 줄 수 있음."""
    next_zone = 0
    new_zm = ZoneMap(W, H)
    visited = [[False]*W for _ in range(H)]

    for y in range(H):
        for x in range(W):
            if visited[y][x]:
                continue
            orig_zid = zm.get(y, x)
            # BFS: 같은 zone ID의 연결된 셀들
            queue = [(y, x)]
            visited[y][x] = True
            cells = []
            while queue:
                cy, cx = queue.pop(0)
                cells.append((cy, cx))
                for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                    ny, nx = cy+dy, cx+dx
                    if 0 <= ny < H and 0 <= nx < W and not visited[ny][nx] and zm.get(ny, nx) == orig_zid:
                        visited[ny][nx] = True
                        queue.append((ny, nx))
            for cy, cx in cells:
                new_zm.set(cy, cx, next_zone)
            next_zone += 1

    new_zm._zone_cells = None
    return new_zm


def subdivide_zones_if_needed(zm, min_zones, sym_type="quad_mirror"):
    """
    존 수가 min_zones보다 적으면 분할 + 존 크기가 불균등하면 큰 존을 추가 분할.
    대칭을 유지하면서 분할하여, n_colors개 색상이 골고루 쓰일 수 있는 존 구조를 보장.

    분할 조건:
    1) 존 수 < min_zones → 무조건 분할
    2) 존 수 >= min_zones이지만 가장 큰 존이 평균의 2.5배 이상 → 균등화 분할
    """
    W, H = zm.W, zm.H
    cx, cy = (W-1)/2.0, (H-1)/2.0
    total_cells = W * H

    for iteration in range(30):  # 안전 장치
        # 현재 존 수 체크
        unique = set()
        zone_cells = {}
        for y in range(H):
            for x in range(W):
                z = zm.get(y, x)
                unique.add(z)
                if z not in zone_cells:
                    zone_cells[z] = []
                zone_cells[z].append((y, x))

        n_zones = len(unique)

        # 조건 1: 존 수 부족
        need_more_zones = n_zones < min_zones

        # 조건 2: 존 크기 불균등 — 가장 큰 존이 평균의 2.5배 이상이면 분할
        avg_size = total_cells / max(n_zones, 1)
        biggest_zone = max(zone_cells.keys(), key=lambda z: len(zone_cells[z]))
        biggest_size = len(zone_cells[biggest_zone])
        # 분할해도 최소 20셀은 돼야 의미 있음
        need_balance = (biggest_size > avg_size * 2.5 and biggest_size >= 40)

        if not need_more_zones and not need_balance:
            break

        cells = zone_cells[biggest_zone]
        new_zone_id = max(unique) + 1

        # 중심 거리 기준으로 셀을 2등분
        dists = []
        for y, x in cells:
            d = math.sqrt((x - cx)**2 + (y - cy)**2)
            dists.append(d)
        median_d = sorted(dists)[len(dists) // 2]

        # 중심에서 먼 쪽을 새 존으로
        changed = 0
        for y, x in cells:
            d = math.sqrt((x - cx)**2 + (y - cy)**2)
            if d > median_d:
                # 대칭 그룹 전체를 같이 변경
                for sy, sx in get_sym_group(y, x, H, W, sym_type):
                    if zm.get(sy, sx) == biggest_zone:
                        zm.set(sy, sx, new_zone_id)
                        changed += 1

        # 분할이 안 됐으면 (모든 셀이 같은 거리) 무한루프 방지
        if changed == 0:
            break

    return zm


# ══════════════════════════════════════════════════════════
# 존 생성기들 — 메타포별 구조 정의
# ══════════════════════════════════════════════════════════

def zone_concentric_rect(y, x, W, H, num_rings=None):
    """동심 사각형: 체비셰프 거리 기반 링"""
    cx, cy = (W-1)/2, (H-1)/2
    d = max(abs(x - cx), abs(y - cy))
    max_d = max(cx, cy)
    if num_rings is None:
        num_rings = max(3, int(max_d / 3))
    ring = int(d / max(1, max_d / num_rings))
    return min(ring, num_rings - 1)


def zone_spiral(y, x, W, H, arms=2, band_width=None):
    """나선: 각도 + 거리 기반"""
    cx, cy = W/2, H/2
    dx, dy = x - cx, y - cy
    angle = math.atan2(dy, dx)
    dist = math.sqrt(dx*dx + dy*dy)
    if band_width is None:
        band_width = max(W, H) / 6
    v = (angle / (2*math.pi) * arms + dist / band_width)
    return int(v) % max(arms * 2, 4)


def zone_herringbone(y, x, W, H, block_size=4):
    """헤링본: 지그재그 블록"""
    bs = max(2, block_size)
    block_y = y // bs
    block_x = x // bs
    local_y = y % bs
    local_x = x % bs
    if block_y % 2 == 0:
        diag = (local_x + local_y) // 2
    else:
        diag = (local_x + (bs - 1 - local_y)) // 2
    return (diag + block_x + block_y) % max(4, bs)


def zone_radial(y, x, W, H, num_sectors=8, num_rings=4):
    """방사형: 섹터 × 링"""
    cx, cy = (W-1)/2, (H-1)/2
    dx, dy = x - cx, y - cy
    angle = math.atan2(dy, dx) + math.pi
    sector = int(angle / (2 * math.pi) * num_sectors) % num_sectors
    dist = max(abs(dx), abs(dy))
    max_d = max(cx, cy)
    ring = int(dist / max(1, max_d / num_rings))
    ring = min(ring, num_rings - 1)
    return ring * num_sectors + sector


def zone_dot_grid(y, x, W, H, spacing=5, dot_r=2):
    """도트 패턴: 배경(0) + 도트 위치별 존"""
    cx_dot = round(x / spacing) * spacing
    cy_dot = round(y / spacing) * spacing
    dist = math.sqrt((x - cx_dot)**2 + (y - cy_dot)**2)
    if dist <= dot_r:
        dot_idx = (cx_dot // spacing + cy_dot // spacing)
        return 1 + (dot_idx % 8)  # 도트별 다른 존
    return 0  # 배경


def zone_check(y, x, W, H, size=4):
    """체크(바둑판): 블록 단위 체크 — 색상 다양성을 위해 위치별 구분"""
    bx = x // size
    by = y // size
    # 체크 패턴: (bx+by)%2 로 흑백 구분 + 위치별 존 다양화
    check = (bx + by) % 2
    # 동일 체크 내에서도 거리별 존 분화 (더 많은 색상 사용)
    cx, cy = (W-1)/2, (H-1)/2
    dist = max(abs(x - cx), abs(y - cy))
    ring = int(dist / max(1, max(cx, cy) / 4))
    return check * 4 + min(ring, 3)


def zone_stripe_h(y, x, W, H, width=4):
    """수평 줄무늬"""
    return (y // width)


def zone_stripe_grid(y, x, W, H, stripe_w=4):
    """줄무늬 그리드: 수평선 + 수직선이 교차하는 격자"""
    on_h_line = (y % stripe_w) < max(1, stripe_w // 3)  # 수평 줄무늬
    on_v_line = (x % stripe_w) < max(1, stripe_w // 3)  # 수직 줄무늬
    if on_h_line and on_v_line:
        return 0  # 교차점
    elif on_h_line:
        return 1  # 수평선
    elif on_v_line:
        return 2  # 수직선
    else:
        # 빈 영역: 위치별 색상 분화
        bx = x // stripe_w
        by = y // stripe_w
        return 3 + (bx + by) % 3  # 배경 셀


def zone_hex_grid(y, x, W, H, radius=5):
    """6각형 격자: hex 좌표 → 존"""
    cx0, cy0 = (W-1)/2.0, (H-1)/2.0
    q = (math.sqrt(3)/3*(x-cx0) - 1/3*(y-cy0)) / radius
    r = (2/3*(y-cy0)) / radius
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq-q), abs(rr-r), abs(rs-s)
    if dq > dr and dq > ds: rq = -rr - rs
    elif dr > ds: rr = -rq - rs
    # 경계 vs 내부
    is_edge = False
    for dy2, dx2 in [(-1,0),(1,0),(0,-1),(0,1)]:
        nx2, ny2 = x+dx2, y+dy2
        if 0 <= nx2 < W and 0 <= ny2 < H:
            q2 = (math.sqrt(3)/3*(nx2-cx0) - 1/3*(ny2-cy0)) / radius
            r2 = (2/3*(ny2-cy0)) / radius
            s2 = -q2 - r2
            rq2, rr2 = round(q2), round(r2)
            rs2 = round(s2)
            dq2, dr2, ds2 = abs(rq2-q2), abs(rr2-r2), abs(rs2-s2)
            if dq2 > dr2 and dq2 > ds2: rq2 = -rr2 - rs2
            elif dr2 > ds2: rr2 = -rq2 - rs2
            if (rq2, rr2) != (rq, rr):
                is_edge = True; break
    if is_edge:
        return 0  # 격자선 존
    return 1 + ((rq * 7 + rr * 13) % 6 + 6) % 6  # 내부 셀별 존


def zone_diamond_check(y, x, W, H, size=5):
    """다이아몬드 격자: 45도 회전 체크 + 거리 세분화"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    check = ((x + y) // size + (x - y + 1000*size) // size) % 2
    # 중심 거리 기반 링 추가
    d = max(abs(x - cx), abs(y - cy))
    ring = int(d / max(1, max(cx, cy) / 3))
    ring = min(ring, 2)
    return check * 3 + ring


def zone_kaleidoscope(y, x, W, H, n_sectors=8):
    """만화경: 접기(fold) 기반 방사 대칭 (큰 존 유지)"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = abs(x - cx), abs(y - cy)
    if dx < dy: dx, dy = dy, dx
    d = dx + dy
    # 더 넓은 밴드 → 더 큰 존 → 프래그 방지
    band = max(5.0, (W + H) / 8)
    ring = int(d / band)
    ring = min(ring, 3)
    a = math.atan2(dy, dx + 1e-9)
    sec = int(a / (math.pi / 4)) % 2  # 2섹터로 단순화
    return ring * 2 + sec


def zone_snowflake(y, x, W, H, fold=6, branch_width=2):
    """눈송이 만다라: fold 대칭 + 가지 구조 (깔끔한 대형 존)"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    dist = math.sqrt(dx*dx + dy*dy)
    angle = math.atan2(dy, dx) + math.pi
    fold_angle = 2 * math.pi / fold
    sector_angle = angle % fold_angle
    if sector_angle > fold_angle / 2:
        sector_angle = fold_angle - sector_angle
    # 넓은 가지 → 깨끗한 경계
    branch_thresh = fold_angle / (fold * 0.8)
    on_branch = sector_angle < branch_thresh
    max_r = min(cx, cy)
    ring = int(dist / max(1, max_r / 3))
    ring = min(ring, 2)
    if on_branch and dist > max_r * 0.15:
        return 6 + ring  # 가지 존
    return ring  # 배경 링


def zone_flower_mandala(y, x, W, H, petals=5, layers=4):
    """꽃 만다라: 꽃잎 구조 + 동심 레이어"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    dist = math.sqrt(dx*dx + dy*dy)
    angle = math.atan2(dy, dx) + math.pi
    max_r = min(cx, cy)
    # 꽃잎 변조
    petal_wave = math.cos(angle * petals) * max_r * 0.25
    effective_dist = dist - petal_wave
    # 레이어
    layer = int(effective_dist / max(1, max_r / layers))
    layer = max(0, min(layer, layers - 1))
    return layer


def zone_flame(y, x, W, H, taper=0.7):
    """불꽃: 아래 넓고 위로 좁아지는 삼각 + 내부 레이어 + 높이 구분"""
    cx = (W-1)/2
    frac_y = y / max(1, H - 1)  # 0=top, 1=bottom
    half_width = (cx * frac_y * taper + 1)
    dx = abs(x - cx)
    if dx > half_width:
        return 0  # 배경
    # 내부: 수평 위치(좌우 깊이) + 수직 높이 조합
    layer_frac = 1.0 - dx / max(half_width, 1)
    h_layer = int(layer_frac * 3)
    h_layer = min(h_layer, 2)
    v_layer = int(frac_y * 3)
    v_layer = min(v_layer, 2)
    return 1 + v_layer * 3 + h_layer


def zone_maze(y, x, W, H, seed=42, wall_frac=0.35):
    """미궁: DFS 미로 생성 → 벽/통로를 존으로"""
    # 미로는 셀 단위로 생성 후 확대
    cell_w = max(2, W // 8)
    cell_h = max(2, H // 8)
    maze_w = W // cell_w
    maze_h = H // cell_h

    # DFS 미로 생성
    rng = random.Random(seed)
    visited = [[False]*maze_w for _ in range(maze_h)]
    walls_h = [[True]*(maze_w) for _ in range(maze_h + 1)]  # 수평 벽
    walls_v = [[True]*(maze_w + 1) for _ in range(maze_h)]   # 수직 벽

    stack = [(0, 0)]
    visited[0][0] = True
    while stack:
        cy2, cx2 = stack[-1]
        neighbors = []
        for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
            ny, nx = cy2+dy, cx2+dx
            if 0 <= ny < maze_h and 0 <= nx < maze_w and not visited[ny][nx]:
                neighbors.append((ny, nx, dy, dx))
        if neighbors:
            ny, nx, dy, dx = rng.choice(neighbors)
            if dy == -1: walls_h[cy2][cx2] = False
            elif dy == 1: walls_h[cy2+1][cx2] = False
            elif dx == -1: walls_v[cy2][cx2] = False
            elif dx == 1: walls_v[cy2][cx2+1] = False
            visited[ny][nx] = True
            stack.append((ny, nx))
        else:
            stack.pop()

    # 셀 좌표
    my, mx = y // cell_h, x // cell_w
    my = min(my, maze_h - 1)
    mx = min(mx, maze_w - 1)
    ly, lx = y % cell_h, x % cell_w

    # 벽 판정
    is_wall = False
    wall_px_h = max(1, int(cell_h * wall_frac))
    wall_px_w = max(1, int(cell_w * wall_frac))

    if ly < wall_px_h and my < maze_h and walls_h[my][mx]:
        is_wall = True
    if ly >= cell_h - wall_px_h and my + 1 <= maze_h and walls_h[min(my+1, maze_h)][mx]:
        is_wall = True
    if lx < wall_px_w and mx < maze_w and walls_v[my][mx]:
        is_wall = True
    if lx >= cell_w - wall_px_w and mx + 1 <= maze_w and walls_v[my][min(mx+1, maze_w)]:
        is_wall = True

    if is_wall:
        return 0  # 벽
    # 통로: 거리 기반 색상 존
    center_dist = abs(my - maze_h//2) + abs(mx - maze_w//2)
    max_dist = maze_h//2 + maze_w//2
    layer = int(center_dist / max(1, max_dist / 5))
    return 1 + min(layer, 4)


def zone_color_wheel(y, x, W, H, n_sectors=None):
    """컬러 휠: 원형 섹터"""
    cx, cy = (W-1)/2, (H-1)/2
    dx, dy = x - cx, y - cy
    dist = math.sqrt(dx*dx + dy*dy)
    max_r = min(cx, cy)
    if dist > max_r * 0.95:
        return 0  # 배경
    angle = math.atan2(dy, dx) + math.pi
    if n_sectors is None:
        n_sectors = 6
    sector = int(angle / (2 * math.pi) * n_sectors) % n_sectors
    return 1 + sector


def zone_mosaic(y, x, W, H, tile=4, seed=42):
    """모자이크: 타일별 다른 존 (대칭 적용)"""
    tw = (W + tile - 1) // tile
    th = (H + tile - 1) // tile
    tx, ty = min(x // tile, tw-1), min(y // tile, th-1)
    # 대칭: 좌우 + 상하 접기
    sx = min(tx, tw - 1 - tx)
    sy = min(ty, th - 1 - ty)
    rng = random.Random(seed * 1000 + sy * 100 + sx)
    return rng.randint(0, 7)


def zone_triangle(y, x, W, H, tile_h=8):
    """삼각 패턴: 개별 삼각형이 독립 존 — 5색+ 대응"""
    tile_w = tile_h
    tx = x // tile_w
    ty = y // tile_h
    local_x = x % tile_w
    local_y = y % tile_h
    # 대각선 기준: 위삼각 vs 아래삼각
    is_lower = local_y > local_x
    # 각 삼각형 타일에 고유 존 부여 (행/열/방향 조합)
    # 행 내 색상 순환: 인접한 삼각형이 다른 존을 갖도록
    # 5색 이상을 위해 (tx, ty, is_lower) 조합으로 충분한 다양성 확보
    n_cols = max(W // tile_w, 1)
    tri_id = ty * n_cols * 2 + tx * 2 + (1 if is_lower else 0)
    return tri_id


def zone_gradient(y, x, W, H, direction="radial"):
    """그라데이션: 연속 존 (중심~외곽 또는 상~하)"""
    if direction == "radial":
        cx, cy = (W-1)/2, (H-1)/2
        d = math.sqrt((x-cx)**2 + (y-cy)**2)
        max_d = math.sqrt(cx*cx + cy*cy)
        frac = d / max(max_d, 1)
        return min(int(frac * 8), 7)
    else:  # linear
        frac = y / max(H-1, 1)
        return min(int(frac * 8), 7)


def zone_quadrant_cross(y, x, W, H, cross_w=None, border=3):
    """사분면 + 십자: 외곽 테두리 + 십자선 + 4사분면 내부 링"""
    cx, cy = W // 2, H // 2
    if cross_w is None:
        cross_w = max(2, W // 12)
    if x < border or x >= W-border or y < border or y >= H-border:
        return 0  # 외곽 테두리
    if abs(x - cx) < cross_w or abs(y - cy) < cross_w:
        return 1  # 십자
    qx = 0 if x < cx else 1
    qy = 0 if y < cy else 1
    quadrant = qy * 2 + qx
    # 사분면 내부 거리 기반 링 (존 수 확대)
    qdx = abs(x - cx) - cross_w
    qdy = abs(y - cy) - cross_w
    qd = max(qdx, qdy)
    max_qd = max(cx - cross_w - border, cy - cross_w - border)
    ring = int(qd / max(1, max_qd / 3))
    ring = min(ring, 2)
    return 2 + quadrant * 3 + ring  # 2~13 (4사분면 × 3링)


def zone_concentric_check(y, x, W, H, layers=5, check_size=3):
    """동심사각 + 각도 세분화"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    d = max(abs(dx), abs(dy))
    max_d = max(cx, cy)
    ring = int(d / max(1, max_d / layers))
    ring = min(ring, layers - 1)
    # 체크 대신 사분면 구분 → 더 깨끗한 패턴
    angle = math.atan2(dy, dx) + math.pi
    sec = int(angle / (math.pi / 2)) % 4
    return ring * 4 + sec


def zone_ray(y, x, W, H, num_rays=12):
    """광선: 방사 섹터 + 거리 링 (깊이감)"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    angle = math.atan2(dy, dx) + math.pi
    sector = int(angle / (2 * math.pi) * num_rays) % num_rays
    # 거리 기반 링 추가
    dist = math.sqrt(dx*dx + dy*dy)
    max_r = min(cx, cy)
    ring = int(dist / max(1, max_r / 3))
    ring = min(ring, 2)
    return sector * 3 + ring


def zone_abstract_line(y, x, W, H, diag_width=5, horiz_width=6):
    """추상 라인: 대각선 + 수평 교차"""
    v1 = (x + y) // diag_width
    v2 = y // horiz_width
    return (v1 + v2) % 6


def zone_color_band(y, x, W, H, width=7):
    """색상 띠: 수평 밴드"""
    return y // width


def zone_droplet(y, x, W, H, wave_freq=3, wave_amp=2.0, band_width=4.0):
    """물방울: 원형 파동 (각도 변조)"""
    cx, cy = W/2, H/2
    dx, dy = x - cx, y - cy
    dist = math.sqrt(dx*dx + dy*dy)
    angle = math.atan2(dy, dx)
    r = dist + wave_amp * math.sin(angle * wave_freq)
    return int(r / band_width) % 8


def zone_nebula(y, x, W, H, wave_freq=4, band_width=3.0):
    """성운: 방사형 파동"""
    cx, cy = (W-1)/2, (H-1)/2
    dx, dy = x - cx, y - cy
    dist = math.sqrt(dx*dx + dy*dy)
    angle = math.atan2(dy, dx)
    v = dist / band_width + math.sin(angle * wave_freq) * 2
    return int(abs(v)) % 6


def zone_pixel_grid(y, x, W, H, tile=5, seed=42):
    """픽셀 그리드: 맨해튼 거리 링 + 각도 (대형 연결 존)"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    d = abs(dx) + abs(dy)
    max_d = cx + cy
    ring = int(d / max(1, max_d / 4))
    ring = min(ring, 3)
    angle = math.atan2(dy, dx) + math.pi
    sec = int(angle / (math.pi / 2)) % 4
    return ring * 4 + sec


def zone_light_scatter(y, x, W, H, band_width=5):
    """빛 산란: 접기(fold) + 원형"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = abs(x - cx), abs(y - cy)
    if dx < dy: dx, dy = dy, dx
    d = math.sqrt(dx*dx + dy*dy)
    a = math.atan2(dy, dx + 1e-9)
    ring = int(d / band_width)
    sec = int(a / (math.pi/4) * 2) % 3
    return ring * 3 + sec


def zone_abstract_form(y, x, W, H, block_size=4):
    """추상 형상: 동심 다이아몬드 + 방사 세분화"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    # 맨해튼 거리 → 다이아몬드 링
    d = abs(dx) + abs(dy)
    max_d = cx + cy
    ring = int(d / max(1, max_d / 5))
    ring = min(ring, 4)
    # 각도 기반 세분화
    angle = math.atan2(dy, dx) + math.pi
    sec = int(angle / (math.pi / 2)) % 4
    return ring * 4 + sec


def zone_gradient_square(y, x, W, H, tile=8):
    """그라데이션 사각: 타일 내부 동심"""
    tx, ty = x // tile, y // tile
    lx, ly = x % tile, y % tile
    cd = max(abs(lx - tile//2), abs(ly - tile//2))
    base = (tx + ty) % 3
    inner = min(cd, 2)
    return base * 3 + inner


def zone_diamond_dot(y, x, W, H, d_size=6):
    """다이아몬드 격자 + 도트"""
    # 다이아몬드 격자
    d1 = (x + y) // d_size
    d2 = (x - y + 1000 * d_size) // d_size
    cell = (d1 + d2) % 2
    # 격자 교차점에 도트
    dx = (x + y) % d_size
    dy = (x - y + 1000 * d_size) % d_size
    is_vertex = (dx <= 1 or dx >= d_size - 1) and (dy <= 1 or dy >= d_size - 1)
    if is_vertex:
        return 2  # 도트
    return cell


def zone_ray_bundle(y, x, W, H, beam_mult=4, dist_width=5):
    """광선 다발: 방사 섹터 × 거리 링 (독립 조합)"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    angle = math.atan2(dy, dx) + math.pi
    dist = math.sqrt(dx*dx + dy*dy)
    max_r = min(cx, cy)
    sector = int(angle / (2*math.pi) * beam_mult * 2) % (beam_mult * 2)
    ring = int(dist / max(1, max_r / 3))
    ring = min(ring, 2)
    return sector * 3 + ring


def zone_color_block(y, x, W, H, bw=6, bh=5, seed=99):
    """컬러 블록: 동심 사각 링 × 각도 세분화 (대형 연결 존)"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    d = max(abs(dx), abs(dy))
    max_d = max(cx, cy)
    ring = int(d / max(1, max_d / 4))
    ring = min(ring, 3)
    # 각도 기반 세분화
    angle = math.atan2(dy, dx) + math.pi
    sec = int(angle / (math.pi / 2)) % 4
    return ring * 4 + sec


def zone_concentric_holder(y, x, W, H, center_size=3):
    """동심사각 + 중앙 홀더: 링×사분면 조합"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    d = max(abs(dx), abs(dy))
    if d <= center_size:
        qx = 0 if x <= cx else 1
        qy = 0 if y <= cy else 1
        return 10 + qx + qy * 2  # 중앙 4분할
    max_d = max(cx, cy)
    ring = int((d - center_size) / max(1, (max_d - center_size) / 4))
    ring = min(ring, 3)
    # 사분면별 구분 추가 → 더 다양한 존
    qx = 0 if dx <= 0 else 1
    qy = 0 if dy <= 0 else 1
    quadrant = qx + qy * 2
    return ring * 4 + quadrant


def zone_concentric_gradient(y, x, W, H):
    """동심 그라데이션: 중심~외곽"""
    cx, cy = (W-1)/2, (H-1)/2
    d = max(abs(x - cx), abs(y - cy))
    max_d = max(cx, cy)
    frac = d / max_d
    return min(int(frac * 6), 5)


def zone_stripe_diag(y, x, W, H, width=5):
    """대각 줄무늬"""
    return ((x + y) // width) % 4


def zone_vortex(y, x, W, H, arms=3, twist=2.5):
    """소용돌이: 나선형으로 꼬이는 팔 — 빛 입자/추상 소용돌이용"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    d = math.sqrt(dx*dx + dy*dy)
    a = math.atan2(dy, dx)
    max_d = math.sqrt(cx*cx + cy*cy)
    # 거리에 따라 각도를 비틀어서 소용돌이 효과
    twisted = a + twist * (d / max(max_d, 1)) * math.pi
    sector = int((twisted % (2*math.pi)) / (2*math.pi) * arms) % arms
    ring = int(d / max(max_d/4, 1))
    return sector * 5 + min(ring, 4)


def zone_basket_weave(y, x, W, H, tile=6):
    """바스켓 위브(직조): 수평/수직 밴드가 번갈아 교차 — 추상 모자이크용"""
    t = max(3, tile)
    bx = x // t
    by = y // t
    lx = x % t
    ly = y % t
    # 짝수 블록은 수평, 홀수 블록은 수직 방향 스트라이프
    if (bx + by) % 2 == 0:
        # 수평 밴드
        stripe = ly * 3 // t
        return stripe
    else:
        # 수직 밴드
        stripe = lx * 3 // t
        return 3 + stripe
    # 6개 존: 수평0,1,2 / 수직3,4,5 — 직조 느낌


def zone_diamond_cutout(y, x, W, H, layers=5):
    """다이아몬드 + 컷아웃: 동심 다이아몬드 + 모서리 삼각 잘라냄 — 추상 그라데용"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = abs(x - cx), abs(y - cy)
    # 다이아몬드 거리
    d_diamond = dx + dy
    max_d = cx + cy
    ring = int(d_diamond / max(max_d / layers, 1))
    ring = min(ring, layers - 1)
    # 컷아웃: 4 모서리에서 대각 방향 판별
    quadrant = 0
    if x < cx and y < cy: quadrant = 0  # top-left
    elif x >= cx and y < cy: quadrant = 1  # top-right
    elif x < cx and y >= cy: quadrant = 2  # bottom-left
    else: quadrant = 3  # bottom-right
    # 외곽 링에서만 사분면 구분
    if ring >= layers - 2:
        return layers + quadrant
    return ring


def zone_oriental_frame(y, x, W, H, frame_w=3, inner_rings=4):
    """오리엔탈 프레임: 두꺼운 장식 테두리 + 내부 동심원 — 구름 그라데용"""
    # 외곽 프레임 영역
    dist_edge = min(x, y, W-1-x, H-1-y)
    if dist_edge < frame_w:
        # 프레임 내 장식: 모서리 vs 변
        is_corner = (x < frame_w and y < frame_w) or \
                    (x >= W-frame_w and y < frame_w) or \
                    (x < frame_w and y >= H-frame_w) or \
                    (x >= W-frame_w and y >= H-frame_w)
        if is_corner:
            return 0  # 코너 장식
        elif x < frame_w or x >= W-frame_w:
            return 1  # 좌우 변
        else:
            return 2  # 상하 변
    # 내부: 동심 원
    cx, cy = (W-1)/2.0, (H-1)/2.0
    d = math.sqrt((x-cx)**2 + (y-cy)**2)
    inner_max = min(cx - frame_w, cy - frame_w)
    ring = int(d / max(inner_max / inner_rings, 1))
    return 3 + min(ring, inner_rings - 1)


def zone_ancient_pattern(y, x, W, H, cell=5, wall=1):
    """고대문양/미로: 반복 셀 + 벽 라인 — 빛 산란(블루 미로)용"""
    c = max(3, cell)
    w = max(1, wall)
    lx = x % c
    ly = y % c
    bx = x // c
    by = y // c
    # 벽 판별
    on_h_wall = ly < w
    on_v_wall = lx < w
    if on_h_wall and on_v_wall:
        return 0  # 교차점
    elif on_h_wall:
        return 1  # 수평 벽
    elif on_v_wall:
        return 2  # 수직 벽
    else:
        # 내부 셀: 위치에 따라 다른 존
        return 3 + (bx + by * 2) % 5  # 8종 셀 중 5종 반복


def zone_jigsaw(y, x, W, H, tile=7):
    """직소 퍼즐: 돌기/홈이 있는 타일 — 빛의 분산(직소 퍼즐)용"""
    t = max(5, tile)
    bx = x // t
    by = y // t
    lx = x % t
    ly = y % t
    cx_t, cy_t = t // 2, t // 2
    # 타일 내부 vs 돌기/홈 영역 판별
    # 각 변의 중앙에 돌기(볼록) 또는 홈(오목)
    bump_r = t // 4
    # 상단 돌기
    if ly <= bump_r and abs(lx - cx_t) <= bump_r:
        return (bx + by) % 4  # 위쪽 커넥터
    # 하단 돌기
    if ly >= t - 1 - bump_r and abs(lx - cx_t) <= bump_r:
        return 4 + (bx + by) % 4  # 아래쪽 커넥터
    # 좌측 돌기
    if lx <= bump_r and abs(ly - cy_t) <= bump_r:
        return (bx + by + 1) % 4  # 왼쪽 커넥터
    # 우측 돌기
    if lx >= t - 1 - bump_r and abs(ly - cy_t) <= bump_r:
        return 4 + (bx + by + 1) % 4  # 오른쪽 커넥터
    # 타일 본체
    return 8 + (bx + by) % 3


# ── v47 개선 존 함수 ──────────────────────────────────────

def zone_abstract_mosaic(y, x, W, H, tile_base=5, seed=65):
    """추상 모자이크(v47): 바스켓위브 + 동심 레이어 혼합.
    레퍼런스: 가로/세로 직조 바가 교차하되, 중심~외곽으로 색상 톤 변화.
    바 폭은 타일 크기의 1/2~1/3로 넓게, 색상 대비 선명하게.
    """
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = abs(x - cx), abs(y - cy)
    # 동심 레이어 (외곽 프레임 구분)
    max_d = max(cx, cy)
    layer = int(max(dx, dy) / max(1, max_d / 4))
    layer = min(layer, 3)
    # 바스켓 위브: 바 폭을 넓게 (타일의 절반씩 2개 바)
    t = max(4, tile_base)
    bx = int(dx) // t
    by = int(dy) // t
    lx = int(dx) % t
    ly = int(dy) % t
    if (bx + by) % 2 == 0:
        # 수평 바: 2분할 (위/아래)
        stripe = 0 if ly < t // 2 else 1
    else:
        # 수직 바: 2분할 (왼/오)
        stripe = 2 if lx < t // 2 else 3
    # 레이어별로 4가지 바 색이 달라짐
    return layer * 4 + stripe


def zone_mosaic_v2(y, x, W, H, tile=4, seed=70):
    """모자이크(v47): 그라우트 라인으로 구분된 컬러 타일.
    레퍼런스: 보라색 라인으로 구분된 정사각 타일 + 각 타일 고유 색.
    """
    t = max(3, tile)
    # 그라우트 라인 (1px 폭)
    if x % t == 0 or y % t == 0:
        return 0  # 그라우트 존
    # 대칭 접기
    cx, cy = (W-1)/2.0, (H-1)/2.0
    fx, fy = abs(x - cx), abs(y - cy)
    tx = int(fx) // t
    ty = int(fy) // t
    # 타일별 고유 존 (시드 기반)
    tile_rng = random.Random(seed * 100 + ty * 20 + tx)
    return 1 + tile_rng.randint(0, 6)  # 7가지 타일 색


def zone_gradient_rings(y, x, W, H, n_rings=6):
    """그라데이션 사각: 동심 사각 링이 점진적으로 색상 변화.
    각 링 내부에서 꼭짓점/변 방향에 따라 미세 존 변화."""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = abs(x - cx), abs(y - cy)
    # 체비셰프 거리 → 사각 링
    d = max(dx, dy)
    max_d = max(cx, cy)
    ring = int(d / max(1, max_d / n_rings))
    ring = min(ring, n_rings - 1)
    # 링 내에서 위치 구분: 모서리 vs 변
    is_corner = abs(dx - dy) < max(1, max_d / n_rings * 0.3)
    if is_corner:
        return ring * 2 + 1  # 모서리 톤
    return ring * 2  # 변 톤


def zone_hex_honeycomb(y, x, W, H, radius=4):
    """육각형 벌집(v47): 뚜렷한 육각형 셀 + 1px 경계선.
    레퍼런스: 각 셀이 뚜렷하고 경계가 깨끗한 허니컴."""
    cx0, cy0 = (W-1)/2.0, (H-1)/2.0
    r = max(3, radius)
    # 육각형 좌표 변환
    q_f = (math.sqrt(3)/3*(x-cx0) - 1/3*(y-cy0)) / r
    r_f = (2/3*(y-cy0)) / r
    s_f = -q_f - r_f
    rq, rr, rs = round(q_f), round(r_f), round(s_f)
    dq, dr, ds = abs(rq-q_f), abs(rr-r_f), abs(rs-s_f)
    if dq > dr and dq > ds: rq = -rr - rs
    elif dr > ds: rr = -rq - rs
    # 셀 중심까지 거리 → 경계 판별 (더 두꺼운 경계)
    frac_q = abs(q_f - rq)
    frac_r = abs(r_f - rr)
    frac_s = abs(s_f - (-rq - rr))
    max_frac = max(frac_q, frac_r, frac_s)
    if max_frac > 0.38:  # 경계 영역
        return 0  # 경계 존
    # 셀별 고유 존: 동심 링으로 색상 배치
    hex_dist = max(abs(rq), abs(rr), abs(rq + rr))
    cell_color = hex_dist % 5
    return 1 + cell_color


def zone_dot_blob(y, x, W, H, spacing=6, blob_r=2.5):
    """도트/블롭 패턴(v47): 둥근 큰 블롭이 규칙적으로 배열.
    레퍼런스: 배경 위에 큰 원형 요소들이 격자 배치."""
    # 대칭 접기
    cx, cy = (W-1)/2.0, (H-1)/2.0
    fx, fy = abs(x - cx), abs(y - cy)
    s = max(4, spacing)
    r = max(1.5, blob_r)
    # 가장 가까운 그리드 포인트
    gx = round(fx / s) * s
    gy = round(fy / s) * s
    dist = math.sqrt((fx - gx)**2 + (fy - gy)**2)
    if dist <= r:
        # 블롭 내부: 그리드 위치별 존
        blob_id = int(gx / s) * 10 + int(gy / s)
        return 1 + (blob_id % 6)  # 6가지 블롭 색
    elif dist <= r + 1:
        return 7  # 블롭 경계
    # 배경: 체비셰프 거리 기반 구역
    max_d = max(cx, cy)
    bg_zone = int(max(fx, fy) / max(1, max_d / 3))
    return 8 + min(bg_zone, 2)  # 3가지 배경 톤


def zone_checker_in_shape(y, x, W, H, check_size=3, shape="diamond"):
    """형태 안 체커(v47): 다이아몬드/타원 경계 안에만 체커 패턴.
    레퍼런스: 형태 바깥은 솔리드, 안쪽만 체크."""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = abs(x - cx), abs(y - cy)
    max_x, max_y = cx * 0.85, cy * 0.85
    if max_x > 0 and max_y > 0:
        ellipse_d = (dx/max_x)**2 + (dy/max_y)**2
    else:
        ellipse_d = 2.0
    if ellipse_d > 1.0:
        frame_d = max(dx, dy)
        frame_ring = int(frame_d / max(1, max(cx, cy) / 3))
        return 8 + min(frame_ring, 2)
    cs = max(2, check_size)
    check = ((int(dx) // cs) + (int(dy) // cs)) % 2
    inner_d = math.sqrt(dx*dx + dy*dy)
    inner_ring = int(inner_d / max(1, min(max_x, max_y) / 3))
    inner_ring = min(inner_ring, 3)
    return check * 4 + inner_ring


def zone_mandala_checker(y, x, W, H, n_rings=5, check_size=3):
    """만다라+체커(v47): 동심 사각 링마다 체커/솔리드가 번갈아 나오는 복합 만다라.
    레퍼런스: 외곽 솔리드 → 체커 → 솔리드 → 체커... 뚜렷한 색상 대비."""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = abs(x - cx), abs(y - cy)
    # 체비셰프 거리 → 사각 링 (원형 대신 사각형 동심)
    d = max(dx, dy)
    max_d = max(cx, cy)
    ring = int(d / max(1, max_d / n_rings))
    ring = min(ring, n_rings - 1)
    cs = max(2, check_size)
    # 짝수 링: 체커 패턴, 홀수 링: 솔리드 (뚜렷한 대비)
    if ring % 2 == 0:
        # 체커: 각 체커 셀이 다른 존
        check = ((int(dx) // cs) + (int(dy) // cs)) % 2
        return ring * 2 + check
    else:
        # 솔리드: 축 방향 분할 (4방향 색상 대비)
        if dx > dy:
            return ring * 2 + 0
        else:
            return ring * 2 + 1


def zone_tile_with_dots(y, x, W, H, tile_size=6, dot_r=1):
    """타일+도트(v47): 큰 컬러 타일 격자 + 각 타일 중앙에 작은 도트.
    레퍼런스: 오렌지/시안/그레이 큰 타일, 중앙에 흰/초록 작은 점."""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    t = max(4, tile_size)
    # 대칭 접기
    fx, fy = abs(x - cx), abs(y - cy)
    tx = int(fx) // t
    ty = int(fy) // t
    lx = int(fx) % t
    ly = int(fy) % t
    # 타일 중심 도트
    tile_cx, tile_cy = t // 2, t // 2
    dot_dist = max(abs(lx - tile_cx), abs(ly - tile_cy))
    dr = max(1, dot_r)
    if dot_dist <= dr:
        # 도트: 타일 체커 위치에 따라 색
        return 6 + ((tx + ty) % 2)  # 2종 도트 색
    # 타일 배경: 체커 배치 + 거리 톤
    check = (tx + ty) % 2
    dist_ring = int(max(fx, fy) / max(1, max(cx, cy) / 3))
    dist_ring = min(dist_ring, 2)
    return check * 3 + dist_ring


def zone_blob_field(y, x, W, H, spacing=5, blob_r=2.2):
    """블롭 필드(v47): 큰 둥근 블롭이 규칙 배열 + 사이에 작은 악센트.
    레퍼런스: 노란 큰 블롭 그리드, 사이에 파란/갈색 작은 요소."""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    fx, fy = abs(x - cx), abs(y - cy)
    s = max(4, spacing)
    r = max(1.5, blob_r)
    # 메인 블롭 그리드
    gx = round(fx / s) * s
    gy = round(fy / s) * s
    dist = math.sqrt((fx - gx)**2 + (fy - gy)**2)
    if dist <= r:
        # 블롭 내부: 동심 거리로 톤
        inner = 0 if dist <= r * 0.5 else 1
        return inner  # 2종 블롭 톤
    # 블롭 사이 공간: 대각선 악센트
    # 반격자 포인트 (블롭 사이 중앙)
    hgx = round((fx - s/2) / s) * s + s/2
    hgy = round((fy - s/2) / s) * s + s/2
    h_dist = math.sqrt((fx - hgx)**2 + (fy - hgy)**2)
    if h_dist <= r * 0.6:
        return 2  # 악센트 블롭
    # 배경
    bg_d = max(fx, fy)
    max_d = max(cx, cy)
    bg_ring = int(bg_d / max(1, max_d / 3))
    return 3 + min(bg_ring, 2)  # 3종 배경


def zone_hourglass(y, x, W, H, neck_ratio=0.25, n_layers=5):
    """아워글래스/터널(v47): 원근감 있는 모래시계형 동심 구조.
    레퍼런스: 위아래가 넓고 중앙이 좁은 대칭 프레임."""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = abs(x - cx), abs(y - cy)
    # 수직 위치에 따라 수평 폭 변화 (모래시계)
    # 중앙(dy=0)에서 가장 좁고, 위아래(dy=cy)에서 가장 넓음
    t = dy / max(cy, 1)  # 0~1: 중앙~끝
    # 모래시계 곡선: 중앙에서 neck_ratio만큼 좁아짐
    width_at_y = neck_ratio + (1.0 - neck_ratio) * (t ** 0.8)
    # 정규화된 수평 거리
    norm_dx = dx / max(cx * width_at_y, 0.5)
    # 정규화된 수직 거리
    norm_dy = dy / max(cy, 1)
    # 동심 레이어
    d = max(norm_dx, norm_dy)
    layer = int(d * n_layers)
    layer = min(layer, n_layers - 1)
    # 레이어 내 위치 구분: 상하 vs 좌우
    is_vertical = norm_dy > norm_dx
    return layer * 2 + (1 if is_vertical else 0)


def zone_light_burst(y, x, W, H, n_rays=8, n_rings=4):
    """빛 산란(개선): 방사형 광선이 동심원과 교차.
    광선 위 / 광선 사이를 구분해 빛의 산란 느낌."""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = x - cx, y - cy
    dist = math.sqrt(dx*dx + dy*dy)
    angle = math.atan2(dy, dx) + math.pi
    max_r = math.sqrt(cx*cx + cy*cy)
    ring = int(dist / max(1, max_r / n_rings))
    ring = min(ring, n_rings - 1)
    # 광선 판별: 각도가 광선 방향에 가까운지
    ray_angle = 2 * math.pi / n_rays
    nearest_ray = round(angle / ray_angle) * ray_angle
    angle_diff = abs(angle - nearest_ray)
    on_ray = angle_diff < ray_angle * 0.2
    if on_ray:
        return n_rings + ring  # 광선 위 (밝은 톤)
    return ring  # 광선 사이 (어두운 톤)


def zone_light_disperse(y, x, W, H, band_width=5):
    """빛의 분산(개선): 프리즘을 통과한 빛이 각도별로 분산.
    대각선 방향으로 색상이 분리되는 스펙트럼 효과."""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    dx, dy = abs(x - cx), abs(y - cy)
    # 대각선 방향 성분
    diag1 = (dx + dy) / 2.0
    diag2 = abs(dx - dy) / 2.0
    # 대각선 기준 밴드
    band1 = int(diag1 / band_width)
    band2 = int(diag2 / max(1, band_width * 0.7))
    band1 = min(band1, 4)
    band2 = min(band2, 2)
    # 중심부는 별도 존
    dist = max(dx, dy)
    if dist < band_width:
        return 15  # 중심 프리즘
    return band1 * 3 + band2


# ══════════════════════════════════════════════════════════
# v41 패턴 함수들 (하이브리드 브릿지용)
# ══════════════════════════════════════════════════════════

def pat_spiral(W, H, n, freq=6.0, start_angle=0.0, **_):
    cx, cy = W/2, H/2
    grid = [[0]*W for _ in range(H)]
    offset = start_angle * math.pi / 180
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            angle = math.atan2(dy, dx) + offset
            dist = math.sqrt(dx*dx + dy*dy)
            v = (angle / (2*math.pi) + dist / freq) * n
            grid[y][x] = int(v) % n
    return grid

def pat_herringbone(W, H, n, block_size=4, **_):
    grid = [[0]*W for _ in range(H)]
    bs = max(2, block_size)
    for y in range(H):
        for x in range(W):
            block_y = y // bs
            block_x = x // bs
            local_y = y % bs
            local_x = x % bs
            if block_y % 2 == 0:
                diag = (local_x + local_y) // 2
            else:
                diag = (local_x + (bs - 1 - local_y)) // 2
            grid[y][x] = (diag + block_x + block_y) % n
    return grid

def pat_concentric_rect(W, H, n, **_):
    cx, cy = (W-1)/2, (H-1)/2
    grid = [[0]*W for _ in range(H)]
    max_d = max(cx, cy)
    for y in range(H):
        for x in range(W):
            d = max(abs(x - cx), abs(y - cy))
            ring = int(d / max(1, max_d / n))
            grid[y][x] = min(ring, n-1)
    return grid

def pat_abstract_line(W, H, n, diag_width=5, horiz_width=6, **_):
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            v1 = (x + y) // diag_width
            v2 = y // horiz_width
            grid[y][x] = (v1 + v2) % n
    return grid

def pat_shape_combo(W, H, n, tile=8, **_):
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            tx, ty = x % tile, y % tile
            cx2, cy2 = tile/2, tile/2
            dist = math.sqrt((tx-cx2)**2 + (ty-cy2)**2)
            block_idx = (x // tile + y // tile)
            if dist < tile * 0.3:
                grid[y][x] = block_idx % n
            else:
                grid[y][x] = (block_idx + 1 + int(dist/2)) % n
    return grid

def pat_droplet(W, H, n, wave_freq=3, wave_amp=2.0, band_width=4.0, **_):
    cx, cy = W/2, H/2
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx*dx + dy*dy)
            angle = math.atan2(dy, dx)
            r = dist + wave_amp * math.sin(angle * wave_freq)
            grid[y][x] = int(r / band_width) % n
    return grid

def pat_radial(W, H, n, ring_width=4, sector_mult=2, **_):
    cx, cy = (W-1)/2, (H-1)/2
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            angle = math.atan2(dy, dx)
            sector = int((angle + math.pi) / (2 * math.pi) * n * sector_mult)
            dist = max(abs(dx), abs(dy))
            ring = int(dist / ring_width)
            grid[y][x] = (sector + ring) % n
    return grid

def pat_kaleidoscope(W, H, n, **_):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            dx, dy = abs(x - cx), abs(y - cy)
            if dx < dy: dx, dy = dy, dx
            d = dx + dy
            band = max(3.0, (W + H) / (n * 2))
            ring = int(d / band) % max(1, n // 2)
            a = math.atan2(dy, dx + 1e-9)
            sec = 0 if a < math.pi / 8 else 1
            grid[y][x] = (ring * 2 + sec) % n
    return grid

def pat_light_scatter(W, H, n, band_width=5, **_):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            dx, dy = abs(x - cx), abs(y - cy)
            if dx < dy: dx, dy = dy, dx
            d = math.sqrt(dx*dx + dy*dy)
            a = math.atan2(dy, dx + 1e-9)
            ring = int(d / band_width) % n
            sec = int(a / (math.pi/4) * 2) % 3
            grid[y][x] = (ring + sec) % n
    return grid

def pat_stripe_diag(W, H, n, width=4, **_):
    return [[((x + y) // width) % n for x in range(W)] for y in range(H)]

def pat_abstract_form(W, H, n, block_size=4, **_):
    bs = max(2, block_size)
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            h_band = (y // bs) % n
            v_band = (x // bs) % n
            if (y // bs + x // bs) % 2 == 0:
                grid[y][x] = h_band
            else:
                grid[y][x] = v_band
    return grid

def pat_concentric_gradient(W, H, n, **_):
    cx, cy = (W-1)/2, (H-1)/2
    grid = [[0]*W for _ in range(H)]
    max_d = max(cx, cy)
    for y in range(H):
        for x in range(W):
            d = max(abs(x - cx), abs(y - cy))
            frac = d / max_d
            c = int(frac * (n - 1))
            grid[y][x] = min(c, n-1)
    mid_x, mid_y = W//2, H//2
    for dy in range(-1, 2):
        for dx in range(-1, 2):
            ny, nx = mid_y+dy, mid_x+dx
            if 0 <= ny < H and 0 <= nx < W:
                grid[ny][nx] = n-1
    return grid

def pat_concentric_hidden(W, H, n, layers=5, check_size=3, **_):
    cx, cy = (W-1)/2, (H-1)/2
    grid = [[0]*W for _ in range(H)]
    max_d = max(cx, cy)
    for y in range(H):
        for x in range(W):
            d = max(abs(x - cx), abs(y - cy))
            ring = int(d / (max_d / layers))
            ring = min(ring, layers - 1)
            check = (x // check_size + y // check_size) % 2
            grid[y][x] = (ring + check) % n
    return grid

def pat_mosaic(W, H, n, tile=4, seed=42, **_):
    rng = random.Random(seed)
    grid = [[0]*W for _ in range(H)]
    tw = (W + tile - 1) // tile
    th = (H + tile - 1) // tile
    tile_colors = [[rng.randint(0, n-1) for _ in range(tw)] for _ in range(th)]
    for ty in range(th):
        for tx in range(tw):
            sx = min(tx, tw-1-tx)
            sy = min(ty, th-1-ty)
            tile_colors[ty][tx] = tile_colors[sy][sx]
    for y in range(H):
        for x in range(W):
            tx2, ty2 = x // tile, y // tile
            if tx2 < tw and ty2 < th:
                grid[y][x] = tile_colors[ty2][tx2]
    return grid

def pat_diamond_check(W, H, n, size=6, **_):
    return [[((x+y)//size + (x-y)//size) % n for x in range(W)] for y in range(H)]

def pat_hex_grid(W, H, n, radius=5, **_):
    cx0, cy0 = (W-1)/2.0, (H-1)/2.0
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            q = (math.sqrt(3)/3*(x-cx0) - 1/3*(y-cy0)) / radius
            r = (2/3*(y-cy0)) / radius
            s = -q - r
            rq, rr, rs = round(q), round(r), round(s)
            dq, dr, ds = abs(rq-q), abs(rr-r), abs(rs-s)
            if dq > dr and dq > ds: rq = -rr - rs
            elif dr > ds: rr = -rq - rs
            is_edge = False
            for dy2, dx2 in [(-1,0),(1,0),(0,-1),(0,1)]:
                nx2, ny2 = x+dx2, y+dy2
                if 0 <= nx2 < W and 0 <= ny2 < H:
                    q2 = (math.sqrt(3)/3*(nx2-cx0) - 1/3*(ny2-cy0)) / radius
                    r2 = (2/3*(ny2-cy0)) / radius
                    s2 = -q2 - r2
                    rq2, rr2, rs2 = round(q2), round(r2), round(s2)
                    dq2, dr2, ds2 = abs(rq2-q2), abs(rr2-r2), abs(rs2-s2)
                    if dq2 > dr2 and dq2 > ds2: rq2 = -rr2 - rs2
                    elif dr2 > ds2: rr2 = -rq2 - rs2
                    if (rq2, rr2) != (rq, rr):
                        is_edge = True; break
            if is_edge:
                grid[y][x] = n - 1
            else:
                grid[y][x] = ((rq * 2 + rr * 3) % (n-1) + (n-1)) % (n-1)
    return grid

def pat_color_band(W, H, n, width=6, **_):
    return [[(y // width) % n for _ in range(W)] for y in range(H)]

def pat_nebula(W, H, n, wave_freq=4, band_width=3.0, **_):
    cx, cy = (W-1)/2, (H-1)/2
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx*dx + dy*dy)
            angle = math.atan2(dy, dx)
            v = dist / band_width + math.sin(angle * wave_freq) * 2
            grid[y][x] = int(abs(v)) % n
    return grid

def pat_triangle(W, H, n, tile_h=6, **_):
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            ty = y // tile_h
            ly = y % tile_h
            half = (x + ty * 3) % (tile_h * 2)
            if ly <= half % tile_h:
                c = (ty + x // tile_h) % n
            else:
                c = (ty + x // tile_h + 1) % n
            grid[y][x] = c
    return grid

def pat_color_block(W, H, n, bw=6, bh=5, seed=99, **_):
    rng = random.Random(seed)
    tw = (W + bw - 1) // bw
    th = (H + bh - 1) // bh
    block_c = [[0]*tw for _ in range(th)]
    for ty in range(th):
        for tx in range(tw):
            sx = min(tx, tw - 1 - tx)
            sy = min(ty, th - 1 - ty)
            if ty == sy and tx == sx:
                block_c[ty][tx] = rng.randint(0, n-1)
            else:
                block_c[ty][tx] = block_c[sy][sx]
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            tx2, ty2 = min(x // bw, tw-1), min(y // bh, th-1)
            grid[y][x] = block_c[ty2][tx2]
    return grid

def pat_cloud_gradient(W, H, n, **_):
    cx, cy = (W-1)/2, (H-1)/2
    max_r = math.sqrt(cx*cx + cy*cy)
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            d = math.sqrt(dx*dx + dy*dy)
            frac = d / max_r
            c = int(frac * (n - 0.01))
            grid[y][x] = min(c, n-1)
    return grid

def pat_snowflake_mandala(W, H, n, fold=6, band_width=5, **_):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    grid = [[0]*W for _ in range(H)]
    fold_angle = 2 * math.pi / fold
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx*dx + dy*dy)
            angle = math.atan2(dy, dx) + math.pi
            sector_angle = angle % fold_angle
            if sector_angle > fold_angle / 2:
                sector_angle = fold_angle - sector_angle
            r = dist
            band = int(r / band_width) % n
            spike = 1 if sector_angle < fold_angle / 12 and r > 3 else 0
            grid[y][x] = (band + spike) % n
    return grid

def pat_quadrant_cross(W, H, n, cross_w=None, border=3, **_):
    cx, cy = W // 2, H // 2
    if cross_w is None:
        cross_w = max(2, W // 12)
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            if x < border or x >= W-border or y < border or y >= H-border:
                grid[y][x] = ((x + y) // 2) % min(3, n)
            elif abs(x - cx) < cross_w or abs(y - cy) < cross_w:
                grid[y][x] = n // 2
            else:
                qx = 0 if x < cx else 1
                qy = 0 if y < cy else 1
                quad = qy * 2 + qx
                dist = max(abs(x - cx), abs(y - cy))
                grid[y][x] = (quad + int(dist / 5)) % n
    return grid

def pat_ray(W, H, n, ray_mult=3, **_):
    cx, cy = (W-1)/2, (H-1)/2
    grid = [[0]*W for _ in range(H)]
    num_rays = n * ray_mult
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            angle = math.atan2(dy, dx) + math.pi
            sector = int(angle / (2 * math.pi) * num_rays)
            grid[y][x] = sector % n
    return grid

def pat_dot(W, H, n, spacing=5, dot_r=2, **_):
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            cx_dot = round(x / spacing) * spacing
            cy_dot = round(y / spacing) * spacing
            dist = math.sqrt((x - cx_dot)**2 + (y - cy_dot)**2)
            if dist <= dot_r:
                dot_idx = (cx_dot // spacing + cy_dot // spacing)
                grid[y][x] = (dot_idx % (n - 1)) + 1
            else:
                grid[y][x] = 0
    return grid

def pat_check(W, H, n, size=5, **_):
    return [[((x // size + y // size)) % n for x in range(W)] for y in range(H)]

def pat_gradient_square(W, H, n, tile=8, **_):
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            tx, ty = x // tile, y // tile
            lx, ly = x % tile, y % tile
            cd = max(abs(lx - tile//2), abs(ly - tile//2))
            base = (tx + ty) % n
            grid[y][x] = (base + cd // 2) % n
    return grid

def pat_concentric_check(W, H, n, border=3, layers=5, **_):
    cx, cy = (W-1)/2, (H-1)/2
    grid = [[0]*W for _ in range(H)]
    max_d = max(cx, cy)
    for y in range(H):
        for x in range(W):
            if x < border or x >= W-border or y < border or y >= H-border:
                grid[y][x] = ((x + y) // 2) % min(3, n)
            else:
                d = max(abs(x - cx), abs(y - cy))
                ring = int(d / ((max_d - border) / layers))
                grid[y][x] = min(ring, n-1)
    return grid

def pat_diamond_dot(W, H, n, d_size=6, **_):
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            u = (x + y) // d_size
            v = (x - y) // d_size
            base = (u + v) % (n - 1)
            if (x + y) % d_size == 0 and (x - y) % d_size == 0:
                grid[y][x] = n - 1
            else:
                grid[y][x] = base
    return grid

def pat_ray_bundle(W, H, n, beam_mult=4, dist_width=6, **_):
    cx, cy = (W-1)/2, (H-1)/2
    grid = [[0]*W for _ in range(H)]
    num_beams = n * beam_mult
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            angle = math.atan2(dy, dx) + math.pi
            beam = int(angle / (2*math.pi) * num_beams)
            dist = math.sqrt(dx*dx + dy*dy)
            intensity = int(dist / dist_width)
            grid[y][x] = (beam + intensity) % n
    return grid

def pat_pixel_grid(W, H, n, tile=5, seed=77, **_):
    rng = random.Random(seed)
    tw = (W + tile - 1) // tile
    th = (H + tile - 1) // tile
    tc = [[0]*tw for _ in range(th)]
    for ty in range(th):
        for tx in range(tw):
            sx = min(tx, tw-1-tx)
            sy = min(ty, th-1-ty)
            if ty == sy and tx == sx:
                tc[ty][tx] = rng.randint(0, n-1)
            else:
                tc[ty][tx] = tc[sy][sx]
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            tx2 = min(x // tile, tw-1)
            ty2 = min(y // tile, th-1)
            grid[y][x] = tc[ty2][tx2]
    return grid

def pat_flame(W, H, n, taper=0.7, **_):
    cx = (W-1)/2
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            dx = abs(x - cx)
            progress = (H - 1 - y) / H
            width_at_y = (W/2) * (1 - progress * taper)
            if dx < width_at_y:
                intensity = int(progress * (n - 1))
                lateral = int(dx / max(1, width_at_y) * 2)
                grid[y][x] = (intensity + lateral) % n
            else:
                grid[y][x] = 0
    return grid

def pat_color_wheel(W, H, n, **_):
    cx, cy = (W-1)/2, (H-1)/2
    max_r = min(cx, cy)
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx*dx + dy*dy)
            if dist <= max_r:
                angle = math.atan2(dy, dx) + math.pi
                sector = int(angle / (2 * math.pi) * n)
                grid[y][x] = sector % n
            else:
                grid[y][x] = 0
    return grid

def pat_maze(W, H, n, seed=42, **_):
    mW = W - 1 if W % 2 == 0 else W
    mH = H - 1 if H % 2 == 0 else H
    MW, MH = mW // 2, mH // 2
    passages = [[set() for _ in range(MW)] for _ in range(MH)]
    visited = [[False]*MW for _ in range(MH)]
    rng = random.Random(seed)
    stack = [(0, 0)]
    visited[0][0] = True
    while stack:
        mx, my = stack[-1]
        dirs = [(1,0,'E','W'),(-1,0,'W','E'),(0,1,'S','N'),(0,-1,'N','S')]
        rng.shuffle(dirs)
        nbrs = [(mx+ddx, my+ddy, fw, bk) for ddx, ddy, fw, bk in dirs
                if 0 <= mx+ddx < MW and 0 <= my+ddy < MH and not visited[my+ddy][mx+ddx]]
        if nbrs:
            nx2, ny2, fw, bk = nbrs[0]
            passages[my][mx].add(fw)
            passages[ny2][nx2].add(bk)
            visited[ny2][nx2] = True
            stack.append((nx2, ny2))
        else:
            stack.pop()
    maze_grid = [['K']*mW for _ in range(mH)]
    for my in range(MH):
        for mx in range(MW):
            gx2, gy2 = 1+mx*2, 1+my*2
            maze_grid[gy2][gx2] = 'P'
            if 'E' in passages[my][mx] and mx+1 < MW:
                maze_grid[gy2][gx2+1] = 'P'
            if 'S' in passages[my][mx] and my+1 < MH:
                maze_grid[gy2+1][gx2] = 'P'
    cx_g, cy_g = (mW-1)/2.0, (mH-1)/2.0
    max_d = math.sqrt(cx_g**2 + cy_g**2)
    wall_n = n - 1
    for gy in range(mH):
        for gx in range(mW):
            if maze_grid[gy][gx] == 'K':
                d = math.sqrt((gx-cx_g)**2 + (gy-cy_g)**2) / max_d
                maze_grid[gy][gx] = int(d * (wall_n - 0.01)) % wall_n
            elif maze_grid[gy][gx] == 'P':
                maze_grid[gy][gx] = n - 1
    grid = [[0]*W for _ in range(H)]
    for y in range(min(mH, H)):
        for x in range(min(mW, W)):
            grid[y][x] = maze_grid[y][x]
    for y in range(mH, H):
        for x in range(W):
            grid[y][x] = grid[mH-1][min(x, mW-1)]
    for y in range(H):
        for x in range(mW, W):
            grid[y][x] = grid[min(y, mH-1)][mW-1]
    return grid

def pat_stripe_grid(W, H, n, stripe_w=4, **_):
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            h_stripe = (y // stripe_w) % n
            v_stripe = (x // stripe_w) % n
            grid[y][x] = (h_stripe + v_stripe) % n
    return grid

def pat_flower_mandala(W, H, n, petals=4, band_width=4, **_):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            dist = math.sqrt(dx*dx + dy*dy)
            angle = math.atan2(dy, dx) + math.pi
            petal = math.cos(angle * petals) * 3
            r = dist - petal
            band = int(abs(r) / band_width) % n
            grid[y][x] = band
    return grid

def pat_concentric_holder(W, H, n, center_size=3, **_):
    cx, cy = (W-1)/2, (H-1)/2
    grid = [[0]*W for _ in range(H)]
    max_d = max(cx, cy)
    for y in range(H):
        for x in range(W):
            d = max(abs(x - cx), abs(y - cy))
            if d <= center_size:
                qx = 0 if x <= cx else 1
                qy = 0 if y <= cy else 1
                grid[y][x] = (qx + qy * 2) % n
            else:
                ring = int((d - center_size) / max(1, (max_d - center_size) / max(1, n - 2)))
                grid[y][x] = min(ring + 2, n-1) % n
    return grid


# ══════════════════════════════════════════════════════════
# 대칭 매핑 + 파라미터 범위
# ══════════════════════════════════════════════════════════

SYMMETRY_MAP = {
    "나선":         "rotational",
    "헤링본":       "bilateral_lr",
    "동심사각":     "quad_mirror",
    "추상 라인":    "bilateral_lr",
    "도형 조합":    "translational",
    "물방울 무늬":  "rotational",
    "방사 패턴":    "radial",
    "빛 산란":      "radial",
    "빛의 분산":    "radial",
    "빛 입자":      "quad_mirror",
    "추상 형상":    "bilateral_lr",
    "그라데":       "radial",
    "색조 분할":    "bilateral_lr",
    "동심 히든":    "quad_mirror",
    "모자이크":     "quad_mirror",
    "6각형 격자":   "radial",
    "색상 띠":      "bilateral_tb",
    "우주 성운":    "rotational",
    "삼각 패턴":    "translational",
    "컬러 블록":    "quad_mirror",
    "구름 그라데":  "radial",
    "눈송이 만다라":"hexagonal",
    "사분면 십자":  "quad_mirror",
    "광선 패턴":    "radial",
    "도트 패턴":    "translational",
    "체크 패턴":    "quad_mirror",
    "그라데이션 사각":"translational",
    "동심 체크":    "quad_mirror",
    "다이아몬드":   "quad_mirror",
    "광선 다발":    "radial",
    "픽셀 그리드":  "quad_mirror",
    "불꽃":         "bilateral_lr",
    "컬러 휠":      "radial",
    "미로":         "bilateral_lr",
    "줄무늬 그리드":"quad_mirror",
    "꽃 만다라":    "radial",
    "동심 홀더":    "quad_mirror",
}


# v41 파라미터 범위 (시드별 랜덤화용)
V41_PARAM_RANGES = {
    "pat_spiral":      {"freq": (4.0, 9.0), "start_angle": (0, 359)},
    "pat_herringbone": {"block_size": (3, 6)},
    "pat_abstract_line": {"diag_width": (3, 7), "horiz_width": (4, 8)},
    "pat_shape_combo": {"tile": (6, 12)},
    "pat_droplet":     {"wave_freq": (2, 5), "wave_amp": (1.0, 4.0), "band_width": (3.0, 6.0)},
    "pat_radial":      {"ring_width": (3, 6), "sector_mult": (1, 3)},
    "pat_light_scatter": {"band_width": (3, 7)},
    "pat_stripe_diag": {"width": (3, 7)},
    "pat_abstract_form": {"block_size": (3, 6)},
    "pat_concentric_hidden": {"layers": (4, 7), "check_size": (2, 5)},
    "pat_mosaic":      {"tile": (3, 6)},
    "pat_diamond_check": {"size": (4, 8)},
    "pat_hex_grid":    {"radius": (4, 7)},
    "pat_color_band":  {"width": (4, 9)},
    "pat_nebula":      {"wave_freq": (3, 6), "band_width": (2.0, 5.0)},
    "pat_triangle":    {"tile_h": (4, 8)},
    "pat_color_block": {"bw": (4, 8), "bh": (4, 7)},
    "pat_snowflake_mandala": {"fold": (5, 8), "band_width": (3, 7)},
    "pat_quadrant_cross": {"border": (2, 5)},
    "pat_ray":         {"ray_mult": (2, 5)},
    "pat_dot":         {"spacing": (4, 7), "dot_r": (1, 3)},
    "pat_check":       {"size": (3, 7)},
    "pat_gradient_square": {"tile": (6, 12)},
    "pat_concentric_check": {"border": (2, 5), "layers": (4, 7)},
    "pat_diamond_dot": {"d_size": (4, 8)},
    "pat_ray_bundle":  {"beam_mult": (3, 6), "dist_width": (4, 8)},
    "pat_pixel_grid":  {"tile": (4, 7)},
    "pat_flame":       {"taper": (0.5, 0.9)},
    "pat_stripe_grid": {"stripe_w": (3, 6)},
    "pat_flower_mandala": {"petals": (3, 6), "band_width": (3, 6)},
    "pat_concentric_holder": {"center_size": (2, 5)},
    "pat_maze":        {},
}


def randomize_v41_params(pat_func_name, rng):
    """v41 패턴 함수의 파라미터를 시드 기반으로 랜덤화"""
    ranges = V41_PARAM_RANGES.get(pat_func_name, {})
    params = {}
    for key, (lo, hi) in ranges.items():
        if isinstance(lo, float):
            params[key] = lo + rng.random() * (hi - lo)
        else:
            params[key] = rng.randint(lo, hi)
    return params


# ══════════════════════════════════════════════════════════
# v41 → v42 브릿지: 패턴 그리드 → ZoneMap (연결 요소 분석)
# ══════════════════════════════════════════════════════════

def make_zone_map_from_v41(pat_func, W, H, n_colors, seed_id=0, rng=None, **kwargs):
    """
    v41 패턴 함수 출력 → 연결 요소(connected component) → ZoneMap.

    v41의 풍부한 시각 패턴을 존 구조로 변환하여
    v42의 graph_color + ×10 밸런싱을 적용할 수 있게 함.
    """
    # v41 패턴 생성 — 고해상도에서 생성 후 블록 다운샘플링
    # 패턴 함수를 2~3배 큰 해상도로 실행하고, 블록 다수결로 축소
    # → 존 경계가 블록 단위로 정렬되어 프래그멘테이션 완전 제거
    SUPERSAMPLE = 3  # 3×3 블록 → 1 셀
    big_W, big_H = W * SUPERSAMPLE, H * SUPERSAMPLE
    big_grid = pat_func(big_W, big_H, n_colors, **kwargs)

    # 블록 다운샘플링: 각 SUPERSAMPLE×SUPERSAMPLE 블록에서 최다 색 선택
    raw_grid = [[0]*W for _ in range(H)]
    for by in range(H):
        for bx in range(W):
            counts = {}
            for dy in range(SUPERSAMPLE):
                for dx in range(SUPERSAMPLE):
                    c = big_grid[by * SUPERSAMPLE + dy][bx * SUPERSAMPLE + dx]
                    counts[c] = counts.get(c, 0) + 1
            raw_grid[by][bx] = max(counts, key=counts.get)

    # 연결 요소 분석 → ZoneMap
    zm = ZoneMap(W, H)
    zone_id = 0
    visited = [[False]*W for _ in range(H)]

    for y in range(H):
        for x in range(W):
            if visited[y][x]:
                continue
            color = raw_grid[y][x]
            # BFS로 같은 색의 연결 영역 찾기
            queue = [(y, x)]
            visited[y][x] = True
            cells = []
            while queue:
                cy, cx = queue.pop(0)
                cells.append((cy, cx))
                for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                    ny, nx = cy+dy, cx+dx
                    if 0 <= ny < H and 0 <= nx < W and not visited[ny][nx] and raw_grid[ny][nx] == color:
                        visited[ny][nx] = True
                        queue.append((ny, nx))
            for cy, cx in cells:
                zm.set(cy, cx, zone_id)
            zone_id += 1

    # ── 작은 존 병합: min_zone_size 미만인 존을 인접한 가장 큰 존에 흡수 ──
    # 작은 파편 존을 제거하여 깨끗한 구조 보장 (스무딩 후 남은 잔여물)
    min_zone_size = max(12, (W * H) // (n_colors * 4))
    for merge_pass in range(12):
        zs = zm.zone_sizes()
        small_zones = [(sz, zid) for zid, sz in zs.items() if sz < min_zone_size]
        if not small_zones:
            break
        small_zones.sort()  # 가장 작은 것부터 병합
        adj = build_zone_adjacency(zm)
        merged_any = False
        for sz, zid in small_zones:
            # 이미 병합돼서 없어졌을 수 있음
            cur_sizes = zm.zone_sizes()
            if zid not in cur_sizes or cur_sizes[zid] >= min_zone_size:
                continue
            # 인접 존 중 가장 큰 존에 병합
            neighbors = adj.get(zid, set())
            if not neighbors:
                continue
            best_neighbor = max(neighbors, key=lambda nz: cur_sizes.get(nz, 0))
            for cy in range(H):
                for cx in range(W):
                    if zm.get(cy, cx) == zid:
                        zm.set(cy, cx, best_neighbor)
            merged_any = True
        if not merged_any:
            break

    return zm


# ══════════════════════════════════════════════════════════
# 메타포 → 존 생성기 매핑 (하이브리드: v41 브릿지 우선)
# ══════════════════════════════════════════════════════════
# 포맷: (sym_type, ("v41_bridge", pat_func, func_name, default_kwargs))
#   또는 (sym_type, zone_func)  — 기존 v42 네이티브

def _make_zone_map_entry(nc):
    """n_colors에 맞게 파라미터를 조정한 METAPHOR_ZONE_MAP 생성.
    존 함수의 ring/layer/sector 수를 n_colors 이상으로 보장하여
    subdivide의 인위적 분할을 최소화."""
    # 링/레이어 수 = n_colors 이상 확보
    rings = max(4, nc + 1)
    sectors = max(6, nc)
    layers = max(4, nc)
    d_size = max(3, 14 // nc)  # 색 많으면 작은 다이아몬드
    tile = max(3, 10 // nc)
    bw = max(3, 12 // nc)
    return {
        "나선":         ("rotational",   lambda y,x,W,H,r=rings: zone_spiral(y,x,W,H,band_width=max(2,min(W,H)//(r*2)))),
        "헤링본":       ("bilateral_lr", lambda y,x,W,H: zone_herringbone(y,x,W,H)),
        "추상 라인":    ("bilateral_lr", lambda y,x,W,H: zone_abstract_line(y,x,W,H)),
        "도형 조합":    ("quad_mirror",  lambda y,x,W,H,s=max(3,8//nc): zone_check(y,x,W,H,size=s)),
        "물방울 무늬":  ("quad_mirror",  lambda y,x,W,H,s=max(4,10//nc),r=max(2,4//max(1,nc//3)): zone_blob_field(y,x,W,H,spacing=s,blob_r=r)),
        "4단 동심 사각 (주황-녹-보라-주황)": ("quad_mirror", lambda y,x,W,H,r=rings: zone_concentric_rect(y,x,W,H,num_rings=r)),
        "6색 동심 사각": ("quad_mirror",  lambda y,x,W,H,r=rings: zone_concentric_rect(y,x,W,H,num_rings=r)),
        "추상 그라데":  ("quad_mirror",  lambda y,x,W,H: zone_gradient(y,x,W,H,direction="radial")),
        "색조 분할":    ("bilateral_lr", lambda y,x,W,H,w=max(3,10//nc): zone_stripe_diag(y,x,W,H,width=w)),
        "방사 패턴":    ("quad_mirror",  lambda y,x,W,H,s=sectors,r=rings: zone_radial(y,x,W,H,num_sectors=s,num_rings=r)),
        "빛 산란":      ("quad_mirror",  lambda y,x,W,H,nr=max(6,nc): zone_light_burst(y,x,W,H,n_rays=nr,n_rings=max(3,nc//2))),
        "빛의 분산":    ("quad_mirror",  lambda y,x,W,H,bw=max(3,8//nc): zone_light_disperse(y,x,W,H,band_width=bw)),
        "빛 입자":      ("quad_mirror",  lambda y,x,W,H,s=sectors: zone_kaleidoscope(y,x,W,H,n_sectors=s)),
        "추상 형상":    ("quad_mirror",  lambda y,x,W,H,bs=max(3,8//nc): zone_abstract_form(y,x,W,H,block_size=bs)),
        "3색 그라데 직사각형 + 가운데 빈 픽셀": ("quad_mirror", lambda y,x,W,H: zone_concentric_gradient(y,x,W,H)),
        "5단 동심 사각 + ? 도배 (Hidden Balloon)": ("quad_mirror", lambda y,x,W,H,r=max(5,nc),cs=max(2,6//nc): zone_mandala_checker(y,x,W,H,n_rings=r,check_size=cs)),
        "픽셀 모자이크": ("quad_mirror",  lambda y,x,W,H,t=max(4,10//nc): zone_tile_with_dots(y,x,W,H,tile_size=t)),
        "추상 모자이크": ("quad_mirror",  lambda y,x,W,H,t=max(4,10//nc): zone_abstract_mosaic(y,x,W,H,tile_base=t,seed=65)),
        "모자이크":     ("quad_mirror",  lambda y,x,W,H,t=max(3,8//nc): zone_mosaic_v2(y,x,W,H,tile=t,seed=70)),
        "다단 동심 사각 + 중앙 4 holder (의자형)": ("quad_mirror", lambda y,x,W,H: zone_concentric_holder(y,x,W,H)),
        "6각형 격자":   ("quad_mirror",  lambda y,x,W,H,r=max(3,8//nc): zone_hex_honeycomb(y,x,W,H,radius=r)),
        "색상 띠":      ("bilateral_lr", lambda y,x,W,H,w=max(4,12//nc): zone_color_band(y,x,W,H,width=w)),
        "우주 성운":    ("quad_mirror",  lambda y,x,W,H,bw=max(2,6//nc): zone_nebula(y,x,W,H,band_width=bw)),
        "삼각 패턴":    ("bilateral_lr", lambda y,x,W,H,th=max(4,10//nc): zone_triangle(y,x,W,H,tile_h=th)),
        "컬러 블록 패턴": ("quad_mirror",  lambda y,x,W,H,bw=bw: zone_color_block(y,x,W,H,bw=bw,bh=bw)),
        "구름 그라데":  ("quad_mirror",  lambda y,x,W,H: zone_gradient(y,x,W,H,direction="radial")),
        "눈송이 만다라": ("quad_mirror",  lambda y,x,W,H,f=max(4,nc): zone_snowflake(y,x,W,H,fold=f,branch_width=max(1,3//nc))),
        "4사분면 얼음 + 십자 우드보드 + 외곽 체크": ("quad_mirror", lambda y,x,W,H: zone_quadrant_cross(y,x,W,H)),
        "광선 패턴":    ("quad_mirror",  lambda y,x,W,H,s=max(8,nc*2): zone_ray(y,x,W,H,num_rays=s)),
        "도트 패턴":    ("quad_mirror",  lambda y,x,W,H,sp=max(4,8//nc),r=max(2,3//max(1,nc//4)): zone_dot_blob(y,x,W,H,spacing=sp,blob_r=r)),
        "체크 패턴":    ("quad_mirror",  lambda y,x,W,H,s=max(3,8//nc): zone_check(y,x,W,H,size=s)),
        "그라데이션 사각": ("quad_mirror", lambda y,x,W,H,r=max(4,nc): zone_gradient_rings(y,x,W,H,n_rings=r)),
        "5단 다채 동심 사각 + 외곽 체크": ("quad_mirror", lambda y,x,W,H,cs=max(2,6//nc): zone_checker_in_shape(y,x,W,H,check_size=cs)),
        "흰 점 박힌 다이아몬드 격자 + 우상단 체크": ("quad_mirror", lambda y,x,W,H,d=d_size: zone_diamond_dot(y,x,W,H,d_size=d)),
        "광선 다발":    ("quad_mirror",  lambda y,x,W,H,bm=max(3,nc): zone_ray_bundle(y,x,W,H,beam_mult=bm)),
        "컬러 픽셀 그리드": ("quad_mirror", lambda y,x,W,H,t=tile: zone_pixel_grid(y,x,W,H,tile=t)),
        "불꽃만 (해골 제거)": ("bilateral_lr", lambda y,x,W,H: zone_flame(y,x,W,H)),
        "컬러 휠":      ("quad_mirror",  lambda y,x,W,H,s=max(nc,6): zone_color_wheel(y,x,W,H,n_sectors=s)),
        "사분면 ㄱ자 회오리 미궁": ("quad_mirror", lambda y,x,W,H: zone_maze(y,x,W,H,seed=271)),
        "줄무늬 그리드": ("quad_mirror",  lambda y,x,W,H,sw=max(3,8//nc): zone_stripe_grid(y,x,W,H,stripe_w=sw)),
        "꽃 만다라 (Snake 가드)": ("quad_mirror", lambda y,x,W,H,l=layers: zone_flower_mandala(y,x,W,H,layers=l)),
    }


def resolve_zone_metaphor(bl_meta, n_colors=6):
    """메타포 문자열 → (sym_type, zone_func) 퍼지 매칭
    n_colors에 맞게 존 파라미터를 자동 조정하여
    subdivide 없이도 충분한 존이 생성되도록 함.
    """
    entry_map = _make_zone_map_entry(n_colors)
    if bl_meta in entry_map:
        return entry_map[bl_meta]
    for key in entry_map:
        if key in bl_meta or bl_meta in key:
            return entry_map[key]
    # ── [2026-06-18] 영어 프롬프트(새 CSV 형식) 지원 ─────────────────────────────
    # 문제: CSV 메타포가 영어("Checkerboard","blue wave"...)인데 entry_map 키는 한글뿐
    #       → 한 개도 매칭 안 돼 전부 fallback(동심사각)으로 수렴 → 결과물이 다 비슷.
    # 해결: 영어 키워드 → 한글 존 개념 substring 매핑 (결정론적, LLM 번역 불필요).
    # 원복(ROLLBACK): 아래 EN 매칭 + 해시 fallback 블록을 지우고 원래 코드로 되돌리면 됨:
    #   rings = max(4, n_colors + 1)
    #   return ("quad_mirror", lambda y,x,W,H,r=rings: zone_concentric_rect(y,x,W,H,num_rings=r))
    _EN_TO_CONCEPT = [
        ("checker", "체크"), ("argyle", "다이아몬드"), ("diamond", "다이아몬드"),
        ("herringbone", "헤링본"), ("chevron", "헤링본"),
        ("wave", "색상 띠"), ("stripe", "줄무늬"), ("weav", "줄무늬"),
        ("concentric", "동심 사각"), ("target", "동심 사각"), ("ring", "동심 사각"),
        ("windmill", "나선"), ("pinwheel", "나선"), ("spiral", "나선"), ("vortex", "회오리"),
        ("radial", "방사"), ("star", "방사"), ("burst", "광선"), ("light", "빛"),
        ("scale", "물방울"), ("fish", "물방울"), ("dot", "도트"), ("polka", "도트"),
        ("hexagon", "6각형"), ("honeycomb", "6각형"),
        ("mosaic", "모자이크"), ("pixel", "픽셀 그리드"), ("grid", "픽셀 그리드"),
        ("triangle", "삼각"), ("flag", "삼각"), ("garland", "삼각"),
        ("snowflake", "눈송이"), ("mandala", "만다라"), ("kaleido", "방사"),
        ("nebula", "성운"), ("galaxy", "성운"), ("cloud", "구름"),
        ("gradient", "그라데"), ("rainbow", "그라데"), ("wheel", "컬러 휠"),
        ("heart", "도형 조합"), ("shield", "도형 조합"), ("cross", "도형 조합"), ("frame", "도형 조합"),
        ("face", "추상 형상"), ("puppy", "추상 형상"), ("animal", "추상 형상"), ("flower", "만다라"),
    ]
    lo = str(bl_meta).lower()
    for en, concept in _EN_TO_CONCEPT:
        if en in lo:
            for key in entry_map:
                if concept in key:
                    return entry_map[key]
    # 미매칭 fallback: "동심사각 하나"로 몰면 전부 동일해지므로,
    # 메타포 문자열 해시로 entry_map 안에서 결정론적 분산(다양성 보장).
    keys = list(entry_map.keys())
    idx = (sum(ord(c) for c in str(bl_meta)) + int(n_colors)) % len(keys)
    return entry_map[keys[idx]]


# ══════════════════════════════════════════════════════════
# STAGE 1: 존 맵 생성 (멀티시드)
# ══════════════════════════════════════════════════════════

def generate_zone_seeds(W, H, num_colors, bl_meta, level, n_seeds=10):
    """메타포에서 존 맵 + 색상 배정을 n_seeds개 생성 (하이브리드 v41+v42)"""
    sym_type, zone_info = resolve_zone_metaphor(bl_meta, num_colors)
    seeds = []

    # v41 브릿지 여부 판별
    is_v41 = isinstance(zone_info, tuple) and len(zone_info) >= 1 and zone_info[0] == "v41_bridge"

    for seed_id in range(n_seeds):
        rng = random.Random(level * 1000 + seed_id)

        # 색상 수는 CSV 원본 그대로 사용
        nc = num_colors

        if is_v41:
            # ── v41 하이브리드 경로 ──
            _, pat_func, func_name, default_kwargs = zone_info

            # 시드별 파라미터 랜덤화
            rand_params = randomize_v41_params(func_name, rng)
            kwargs = {**default_kwargs, **rand_params}

            # 특수 파라미터: seed가 있는 함수 (mosaic, color_block, pixel_grid, maze)
            if func_name in ("pat_mosaic", "pat_color_block", "pat_pixel_grid", "pat_maze"):
                kwargs["seed"] = level * 100 + seed_id

            # v41 패턴 → 연결 요소 → ZoneMap
            zm = make_zone_map_from_v41(pat_func, W, H, nc, seed_id=seed_id, rng=rng, **kwargs)
        else:
            # ── v42 네이티브 경로 ──
            zone_func = zone_info
            zm = make_symmetric_zone_map(W, H, zone_func, sym_type)
            # 참고: 같은 zone ID가 여러 곳에 반복되는 건 의도된 패턴 구조.
            # 분리하면 graph coloring이 각각 다른 색을 줘서 패턴이 깨짐.

        # 존 수가 색상 수보다 적으면 자동 세분화
        zm = subdivide_zones_if_needed(zm, nc, sym_type)

        # 외곽 단일색 코팅: PixelFlow 스타일 (전체의 ~23%에 적용)
        # 시드별 결정 — 약 30% 확률로 외곽 코팅 적용
        apply_border = rng.random() < 0.30
        if apply_border:
            zm = coat_border_zone(zm, W, H, thickness=1)

        # 존 ID 정규화 (0부터 연속)
        unique_zones = sorted(set(zm.zones[y][x] for y in range(H) for x in range(W)))
        zone_remap = {old: new for new, old in enumerate(unique_zones)}
        for y in range(H):
            for x in range(W):
                zm.zones[y][x] = zone_remap[zm.zones[y][x]]
        zm._zone_cells = None  # cache invalidate

        # 색상 선택
        colors = pick_colors(nc, level, start_offset=seed_id)

        # 색상 배정: 존 → 색상 (×10 제약 만족)
        grid, t_count = assign_colors_x10(zm, nc, rng, seed_id, level_num=level)

        # v46: 대칭 강제 후처리
        enforce_symmetry(grid, W, H, sym_type)
        t_count = fix_x10_after_symmetry(grid, W, H, nc, sym_type, rng)

        seeds.append({
            'seed_id': seed_id,
            'zone_map': zm,
            'has_border_coat': apply_border,
            'grid': grid,
            'colors': colors,
            'num_colors': nc,
            'symmetry': sym_type,
            't_count': t_count,
        })

    return seeds


# ══════════════════════════════════════════════════════════
# v46: 대칭 강제 후처리
# ══════════════════════════════════════════════════════════

def enforce_symmetry(grid, W, H, sym_type):
    """대칭 강제.
    Q(quad_mirror): 좌상단 1/4 → 나머지 3/4에 미러
    B(bilateral_lr): 왼쪽 1/2 → 오른쪽 1/2에 미러
    R(rotational): 좌상단 1/4 → 90°/180°/270° 회전 복사
    """
    if sym_type in ("quad_mirror", "Q"):
        cy, cx = H // 2, W // 2
        for y in range(cy):
            for x in range(cx):
                c = grid[y][x]
                grid[y][W - 1 - x] = c
                grid[H - 1 - y][x] = c
                grid[H - 1 - y][W - 1 - x] = c
        if H % 2 == 1:
            for x in range(cx):
                grid[cy][W - 1 - x] = grid[cy][x]
        if W % 2 == 1:
            for y in range(cy):
                grid[H - 1 - y][cx] = grid[y][cx]
    elif sym_type in ("bilateral_lr", "B"):
        cx = W // 2
        for y in range(H):
            for x in range(cx):
                grid[y][W - 1 - x] = grid[y][x]
    elif sym_type in ("rotational", "R"):
        # 90° 회전 대칭 (정사각형 전용, W==H)
        # 좌상단 1/4을 마스터로, 90°씩 회전 복사
        # 미러가 아니라 회전이므로 나선 구조 보존
        cy, cx = H // 2, W // 2
        for y in range(cy):
            for x in range(cx):
                c = grid[y][x]
                # 90° 시계: (y,x) → (x, H-1-y)
                grid[x][H - 1 - y] = c
                # 180°: (y,x) → (H-1-y, W-1-x)
                grid[H - 1 - y][W - 1 - x] = c
                # 270°: (y,x) → (W-1-x, y)
                grid[W - 1 - x][y] = c
        # 홀수: 중앙 행/열도 회전 적용
        if H % 2 == 1:
            for x in range(cx):
                c = grid[cy][x]
                grid[x][H - 1 - cy] = c
                grid[cy][W - 1 - x] = c
                grid[W - 1 - x][cy] = c
    return grid


def fix_x10_after_symmetry(grid, W, H, n_colors, sym_type, rng):
    """대칭 유지하면서 ×10 보정 — target_unit(20 or 10) 배수로 맞춤."""
    def sym_group(y, x):
        if sym_type in ("quad_mirror", "Q"):
            return list(set([(y, x), (y, W-1-x), (H-1-y, x), (H-1-y, W-1-x)]))
        elif sym_type in ("bilateral_lr", "B"):
            return list(set([(y, x), (y, W-1-x)]))
        elif sym_type in ("rotational", "R"):
            # 90° 회전 대칭 그룹 (나선용)
            cx, cy = (W-1)/2, (H-1)/2
            pts = set()
            dx, dy = x - cx, y - cy
            for _ in range(4):
                nx, ny = int(round(cx + dx)), int(round(cy + dy))
                if 0 <= ny < H and 0 <= nx < W:
                    pts.add((ny, nx))
                dx, dy = -dy, dx  # 90° 회전
            return list(pts)
        return [(y, x)]

    def get_counts():
        counts = Counter()
        for y in range(H):
            for x in range(W):
                if grid[y][x] != T_VALUE:
                    counts[grid[y][x]] += 1
        return counts

    # 대칭 그룹의 최소 크기 결정
    # 짝수×짝수 Q대칭: 모든 그룹 크기 4 → 색상 카운트는 4의 배수
    # ×10 되려면 20의 배수 필요 (LCM(4,10)=20)
    all_even_Q = (W % 2 == 0 and H % 2 == 0) and sym_type in ("quad_mirror", "Q")
    target_unit = 20 if all_even_Q else 10

    counts = get_counts()

    # Phase 1: 각 색상의 목표 = 현재 카운트를 target_unit으로 내림
    targets = {}
    for c in range(n_colors):
        cnt = counts.get(c, 0)
        t = (cnt // target_unit) * target_unit
        if t < target_unit and cnt >= target_unit:
            t = target_unit
        elif t < 10:
            t = 0  # 너무 적으면 포기 (나중에 복구)
        targets[c] = t

    # 총 타겟 확인 — W*H 초과하면 축소
    while sum(targets.values()) > W * H:
        max_c = max(targets, key=lambda c: targets[c])
        targets[max_c] -= target_unit

    # Phase 2: 각 색상의 초과분을 T로 변환 (경계 돌출 그룹 우선)
    # 홀수 그리드: 중앙 줄의 작은 그룹(크기2,1)을 미세 조정에 활용
    for c in range(n_colors):
        excess = counts.get(c, 0) - targets[c]
        if excess <= 0:
            continue

        # 이 색상의 대칭 그룹 수집 (크기별 분류)
        color_groups_small = []  # 크기 1,2 (중앙 줄 — 미세 조정용)
        color_groups_big = []    # 크기 4 (일반 그룹)
        visited_c = set()
        for y in range(H):
            for x in range(W):
                if (y, x) in visited_c:
                    continue
                grp = sym_group(y, x)
                for gy, gx in grp:
                    visited_c.add((gy, gx))
                if grid[y][x] != c:
                    continue
                if not all(grid[gy][gx] == c for gy, gx in grp):
                    continue
                # 돌출도 (낮을수록 경계)
                same = sum(1 for gy, gx in grp
                           for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]
                           if 0 <= gy+dy < H and 0 <= gx+dx < W and grid[gy+dy][gx+dx] == c)
                if len(grp) <= 2:
                    color_groups_small.append((same, grp))
                else:
                    color_groups_big.append((same, grp))

        color_groups_big.sort()    # 돌출 셀 우선
        color_groups_small.sort()

        # 큰 그룹 먼저 제거, 남은 잔여분은 작은 그룹으로 미세 조정
        remaining = excess
        for _, grp in color_groups_big:
            if remaining <= 0:
                break
            if len(grp) <= remaining:
                for gy, gx in grp:
                    grid[gy][gx] = T_VALUE
                remaining -= len(grp)
        for _, grp in color_groups_small:
            if remaining <= 0:
                break
            if len(grp) <= remaining:
                for gy, gx in grp:
                    grid[gy][gx] = T_VALUE
                remaining -= len(grp)

    # Phase 3: 카운트 0인 색상 복구 — 큰 색상에서 대칭 그룹 빌려옴
    counts = get_counts()
    for c in range(n_colors):
        if counts.get(c, 0) >= 10:
            continue
        # T셀 중 대칭 그룹을 이 색상으로 변환
        needed = target_unit - counts.get(c, 0)
        visited_t = set()
        for y in range(H):
            if needed <= 0:
                break
            for x in range(W):
                if needed <= 0:
                    break
                if (y, x) in visited_t:
                    continue
                grp = sym_group(y, x)
                for gy, gx in grp:
                    visited_t.add((gy, gx))
                if grid[y][x] != T_VALUE:
                    continue
                if not all(grid[gy][gx] == T_VALUE for gy, gx in grp):
                    continue
                for gy, gx in grp:
                    grid[gy][gx] = c
                needed -= len(grp)

        if needed > 0:
            # T가 부족 → 가장 큰 색상에서 빌림
            counts2 = get_counts()
            donor = max(range(n_colors), key=lambda cc: counts2.get(cc, 0) if cc != c else 0)
            visited_d = set()
            for y in range(H):
                if needed <= 0:
                    break
                for x in range(W):
                    if needed <= 0:
                        break
                    if (y, x) in visited_d:
                        continue
                    grp = sym_group(y, x)
                    for gy, gx in grp:
                        visited_d.add((gy, gx))
                    if grid[y][x] != donor:
                        continue
                    gs = len(grp)
                    if counts2.get(donor, 0) - gs < target_unit:
                        continue
                    if not all(grid[gy][gx] == donor for gy, gx in grp):
                        continue
                    for gy, gx in grp:
                        grid[gy][gx] = c
                    counts2[donor] -= gs
                    counts2[c] = counts2.get(c, 0) + gs
                    needed -= gs

    # 누락 색 복구
    counts = get_counts()
    missing = [c for c in range(n_colors) if counts.get(c, 0) == 0]
    if missing:
        # 가장 많은 색에서 대칭 그룹을 빌려옴
        for mc in missing:
            counts = get_counts()
            donor = max(range(n_colors), key=lambda c: counts.get(c, 0))
            if counts.get(donor, 0) < 20:
                continue
            visited = set()
            for y in range(H):
                for x in range(W):
                    if (y, x) in visited:
                        continue
                    grp = sym_group(y, x)
                    for gy, gx in grp:
                        visited.add((gy, gx))
                    if grid[y][x] != donor:
                        continue
                    gs = len(grp)
                    if counts.get(donor, 0) - gs < 10:
                        continue
                    for gy, gx in grp:
                        grid[gy][gx] = mc
                    counts[donor] -= gs
                    counts[mc] = counts.get(mc, 0) + gs
                    if counts.get(mc, 0) >= 10:
                        break

    t_count = sum(1 for y in range(H) for x in range(W) if grid[y][x] == T_VALUE)
    return t_count


# ══════════════════════════════════════════════════════════
# 핵심: 색상 배정 알고리즘 (×10 제약 내 최적화)
# ══════════════════════════════════════════════════════════

def build_zone_adjacency(zm: ZoneMap):
    """존 간 인접 관계 그래프 생성: {zone_id: set of neighbor zone_ids}"""
    W, H = zm.W, zm.H
    adj = defaultdict(set)
    for y in range(H):
        for x in range(W):
            z = zm.get(y, x)
            for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                ny, nx = y+dy, x+dx
                if 0 <= ny < H and 0 <= nx < W:
                    nz = zm.get(ny, nx)
                    if nz != z:
                        adj[z].add(nz)
                        adj[nz].add(z)
    return adj


def graph_color_zones(zone_ids, adj, n_colors, zone_sizes, rng, strategy="greedy"):
    """
    그래프 컬러링으로 인접 존에 다른 색상 배정.
    존이 n_colors보다 많으면 재사용하되, 인접하지 않은 존끼리만 같은 색.
    모든 색상이 최소 1번은 사용되도록 보장.
    """
    zone_color = {}

    if strategy == "greedy":
        # 큰 존부터 배정 (constrained → 선택지 적어지기 전에 처리)
        order = sorted(zone_ids, key=lambda z: -zone_sizes.get(z, 0))
        for zid in order:
            used_by_neighbors = set()
            for nz in adj.get(zid, set()):
                if nz in zone_color:
                    used_by_neighbors.add(zone_color[nz])
            # 사용 안 된 색상 중 가장 적게 사용된 색 우선
            color_counts = Counter(zone_color.values())
            candidates = [c for c in range(n_colors) if c not in used_by_neighbors]
            if not candidates:
                # 모든 색이 이웃에 사용됨 → 가장 적은 색 선택
                candidates = list(range(n_colors))
            # 가장 적게 사용된 색 (균형)
            candidates.sort(key=lambda c: color_counts.get(c, 0))
            zone_color[zid] = candidates[0]

    elif strategy == "sequential":
        # 존 ID 순서대로 순환
        for i, zid in enumerate(sorted(zone_ids)):
            used_by_neighbors = set()
            for nz in adj.get(zid, set()):
                if nz in zone_color:
                    used_by_neighbors.add(zone_color[nz])
            c = i % n_colors
            if c in used_by_neighbors:
                for alt in range(n_colors):
                    if alt not in used_by_neighbors:
                        c = alt
                        break
            zone_color[zid] = c

    elif strategy == "random":
        order = list(zone_ids)
        rng.shuffle(order)
        for zid in order:
            used_by_neighbors = set()
            for nz in adj.get(zid, set()):
                if nz in zone_color:
                    used_by_neighbors.add(zone_color[nz])
            candidates = [c for c in range(n_colors) if c not in used_by_neighbors]
            if not candidates:
                candidates = list(range(n_colors))
            zone_color[zid] = rng.choice(candidates)

    # 모든 색상이 최소 1번 사용되고, 충분한 셀 수를 갖도록 보정
    total_cells = sum(zone_sizes.get(z, 0) for z in zone_ids)
    min_fair = max(20, total_cells // n_colors // 3)  # 최소 공정 배분의 1/3

    used_colors = set(zone_color.values())
    missing = [c for c in range(n_colors) if c not in used_colors]
    if missing:
        color_zones = defaultdict(list)
        for zid, c in zone_color.items():
            color_zones[c].append(zid)
        for mc in missing:
            # 가장 많은 셀을 가진 색에서 → 중간 크기 존을 빌려옴
            most_used = max(color_zones.keys(),
                key=lambda c: sum(zone_sizes.get(z,0) for z in color_zones[c]))
            zones_of_most = sorted(color_zones[most_used],
                key=lambda z: zone_sizes.get(z, 0), reverse=True)
            # most_used에 최소 2존 남기고, 가장 큰 존(인접 허용 시) 이전
            picked = None
            for zid in zones_of_most:
                if len(color_zones[most_used]) <= 1:
                    break
                # 인접 존에 mc가 없는지 확인 (그래프 컬러링 위반 방지)
                neighbor_colors = set(zone_color.get(nz) for nz in adj.get(zid, set()) if nz in zone_color)
                if mc not in neighbor_colors:
                    picked = zid
                    break
            if picked is None and zones_of_most:
                # 인접 무시하고 가장 작은 것이라도
                picked = zones_of_most[-1]
            if picked:
                zone_color[picked] = mc
                color_zones[most_used].remove(picked)
                color_zones[mc].append(picked)

    return zone_color


def optimize_x10_coloring(zone_color, zone_ids, adj, n_colors, zone_sizes, rng, max_iter=200):
    """
    그래프 컬러링 결과를 받아서, 인접 제약을 유지하면서
    각 색상의 총 셀 수가 ×10에 최대한 가까워지도록 존 색상을 최적화.

    Local search: 각 존을 순회하며, 유효한 다른 색으로 바꿨을 때
    총 ×10 나머지가 줄어들면 수락.
    """
    def total_remainder(zc):
        counts = Counter()
        for zid in zone_ids:
            counts[zc[zid]] += zone_sizes.get(zid, 0)
        return sum(c % 10 for c in counts.values())

    def color_counts(zc):
        counts = Counter()
        for zid in zone_ids:
            counts[zc[zid]] += zone_sizes.get(zid, 0)
        return counts

    best = dict(zone_color)
    best_rem = total_remainder(best)

    for iteration in range(max_iter):
        if best_rem == 0:
            break

        improved = False
        order = list(zone_ids)
        rng.shuffle(order)

        for zid in order:
            if best_rem == 0:
                break

            cur_color = best[zid]
            neighbor_colors = set()
            for nz in adj.get(zid, set()):
                neighbor_colors.add(best[nz])

            # 유효한 대안 색상 (이웃과 다른 색)
            candidates = [c for c in range(n_colors) if c != cur_color and c not in neighbor_colors]
            if not candidates:
                continue

            # 각 대안의 나머지 변화량 빠르게 계산
            counts = color_counts(best)
            zs = zone_sizes.get(zid, 0)
            cur_rem = best_rem

            best_cand = None
            best_cand_rem = cur_rem

            for new_c in candidates:
                # old color loses zs, new color gains zs
                old_c_new = counts[cur_color] - zs
                new_c_new = counts[new_c] + zs
                # 나머지 변화
                new_rem = cur_rem - (counts[cur_color] % 10) - (counts[new_c] % 10) + (old_c_new % 10) + (new_c_new % 10)

                # 색상 균형 보호:
                # - 소멸 금지 (0셀)
                # - 극소량 금지 (공정 배분의 15% 미만)
                total = sum(counts.values())
                min_acceptable = max(10, total // n_colors // 7)
                if old_c_new == 0:
                    continue
                if 0 < old_c_new < min_acceptable:
                    continue

                if new_rem < best_cand_rem:
                    best_cand_rem = new_rem
                    best_cand = new_c

            if best_cand is not None and best_cand_rem < cur_rem:
                best[zid] = best_cand
                best_rem = best_cand_rem
                improved = True

        if not improved:
            break

    return best


def assign_colors_x10(zm: ZoneMap, n_colors: int, rng: random.Random, seed_id: int = 0, level_num: int = 100):
    """
    존 맵의 각 존에 색상을 배정하되, 모든 색상의 총 셀 수가 ×10이 되도록 한다.

    알고리즘:
    1. 존 인접 그래프 구축
    2. 그래프 컬러링으로 인접 존에 다른 색상 배정 (누락색엔 큰 존 배정)
    3. ×10 최적화 — 인접 제약 유지 + 색 소멸 금지
    4. 남은 나머지 → T 셀 (경계 우선, 대칭 그룹 우선)
    """
    W, H = zm.W, zm.H
    zone_sizes = zm.zone_sizes()
    zone_ids = sorted(zone_sizes.keys())

    # Step 1: 인접 그래프 + 그래프 컬러링
    adj = build_zone_adjacency(zm)
    strategies = ["greedy", "sequential", "random"]
    strategy = strategies[seed_id % len(strategies)]
    zone_color = graph_color_zones(zone_ids, adj, n_colors, zone_sizes, rng, strategy)

    # Step 2: ×10 최적화 — 색 소멸 금지
    zone_color = optimize_x10_coloring(zone_color, zone_ids, adj, n_colors, zone_sizes, rng)

    # Step 3: 그리드 생성
    grid = [[0]*W for _ in range(H)]
    for y in range(H):
        for x in range(W):
            grid[y][x] = zone_color[zm.get(y, x)]

    # Step 4~6: 반복 루프 — 색상 복구 + ×10 보정을 모두 만족할 때까지
    for repair_round in range(5):
        # ×10 보정
        t_count = fix_x10_zone_based(grid, zm, n_colors, W, H, rng)

        # 누락 색 확인
        counts = Counter()
        for y in range(H):
            for x in range(W):
                if grid[y][x] != T_VALUE:
                    counts[grid[y][x]] += 1
        missing = [c for c in range(n_colors) if counts.get(c, 0) == 0]

        if not missing:
            if all(counts.get(c, 0) % 10 == 0 for c in range(n_colors) if counts.get(c, 0) > 0):
                break

        # 누락 색 복구 — 존 단위 우선
        t_count = restore_missing_colors_zone_based(grid, zm, n_colors, W, H, rng)

        # 존 단위로도 안 되면 기존 방식 fallback (개별 셀, 최소 보장)
        counts2 = Counter()
        for y in range(H):
            for x in range(W):
                if grid[y][x] != T_VALUE:
                    counts2[grid[y][x]] += 1
        still_missing = [c for c in range(n_colors) if counts2.get(c, 0) == 0]
        if still_missing:
            t_count = restore_missing_colors(grid, n_colors, W, H, rng)

    # Step 5: ×10-aware 스무딩 — ×10 유지하면서 삐뚤빼뚤 경계만 정리
    counts_final = Counter()
    for y in range(H):
        for x in range(W):
            if grid[y][x] != T_VALUE:
                counts_final[grid[y][x]] += 1

    for _sp in range(5):
        changes = 0
        snap = [row[:] for row in grid]
        for y in range(H):
            for x in range(W):
                c = snap[y][x]
                if c == T_VALUE:
                    continue
                nbrs = []
                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and snap[ny][nx] != T_VALUE:
                        nbrs.append(snap[ny][nx])
                if not nbrs:
                    continue
                same = sum(1 for n in nbrs if n == c)
                if same >= 2:
                    continue  # 돌출 아님
                # 고립(0) 또는 돌출(1)
                mc, mcnt = Counter(nbrs).most_common(1)[0]
                if mc == c:
                    continue
                if same == 1 and mcnt < 2:
                    continue
                # ×10 영향 체크: 악화하지 않을 때만 변경
                old_rem = (counts_final.get(c, 0) % 10) + (counts_final.get(mc, 0) % 10)
                new_rem = ((counts_final.get(c, 0) - 1) % 10) + ((counts_final.get(mc, 0) + 1) % 10)
                if new_rem <= old_rem:
                    grid[y][x] = mc
                    counts_final[c] -= 1
                    counts_final[mc] = counts_final.get(mc, 0) + 1
                    changes += 1
        if changes == 0:
            break

    # 최종 T 카운트
    t_count = sum(1 for y in range(H) for x in range(W) if grid[y][x] == T_VALUE)

    return grid, t_count


def restore_missing_colors_zone_based(grid, zm, n_colors, W, H, rng):
    """
    누락 색상 복구 — 존 단위로 통째 재배정.
    10셀 짜잘이 대신, 의미 있는 크기의 존을 빌려와서 색 배정.
    """
    zone_sizes = zm.zone_sizes()
    zone_ids = sorted(zone_sizes.keys())

    for iteration in range(n_colors):
        counts = Counter()
        for y in range(H):
            for x in range(W):
                c = grid[y][x]
                if c != T_VALUE:
                    counts[c] += 1

        missing = [c for c in range(n_colors) if counts.get(c, 0) == 0]
        if not missing:
            break

        target_color = missing[0]

        # 가장 많은 색에서 → 중간 크기 존을 통째로 재배정
        donor_color = max(counts.keys(), key=lambda c: counts.get(c, 0))
        if counts.get(donor_color, 0) < 40:
            break  # 빌릴 여유 없음

        # donor 색의 존들 — 존 내 donor_color 셀 수 기준 (T 부분 제외)
        donor_zones = []
        for zid in zone_ids:
            cells = zm.zone_cells[zid]
            donor_count = sum(1 for cy, cx in cells if grid[cy][cx] == donor_color)
            if donor_count >= 10:  # 의미 있는 양만
                donor_zones.append((donor_count, zid))
        donor_zones.sort(reverse=True)

        if not donor_zones:
            break

        # 존 크기가 10의 배수인 것 우선 (×10 유지)
        # 없으면 가장 큰 것 선택
        total_donor = counts[donor_color]
        target_size = max(20, total_donor // 4)

        # ×10 유지하는 존 우선
        x10_zones = [(sz, zid) for sz, zid in donor_zones if sz % 10 == 0 and sz >= 20]
        if x10_zones:
            best_zone = min(x10_zones, key=lambda x: abs(x[0] - target_size))
        else:
            best_zone = min(donor_zones, key=lambda x: abs(x[0] - target_size))
        _, picked_zid = best_zone

        # 존 내 donor_color 셀만 target_color로 변환 (T는 유지)
        for cy, cx in zm.zone_cells[picked_zid]:
            if grid[cy][cx] == donor_color:
                grid[cy][cx] = target_color

    return sum(1 for y in range(H) for x in range(W) if grid[y][x] == T_VALUE)


def restore_missing_colors(grid, n_colors, W, H, rng):
    """
    ×10 밸런싱 후 누락된 색상을 복구.
    가장 많은 색에서 10셀을 빼서 누락 색에 배정 (×10 유지).
    대칭 그룹 단위로 변환하여 대칭 유지.
    """
    sym_type = "quad_mirror"

    # 대칭 그룹 사전 계산
    visited = [[False]*W for _ in range(H)]
    sym_groups = []
    for y in range(H):
        for x in range(W):
            if visited[y][x]: continue
            grp = get_sym_group(y, x, H, W, sym_type)
            grp = [(gy, gx) for gy, gx in grp if 0 <= gy < H and 0 <= gx < W]
            grp = list(set(grp))
            for gy, gx in grp:
                visited[gy][gx] = True
            sym_groups.append(grp)

    def _boundary_score(y, x):
        c = grid[y][x]
        diff = 0
        for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
            ny, nx = y+dy, x+dx
            if 0 <= ny < H and 0 <= nx < W:
                nc = grid[ny][nx]
                if nc != c and nc != T_VALUE:
                    diff += 1
            else:
                diff += 1
        return diff

    for iteration in range(n_colors):
        counts = Counter()
        for y in range(H):
            for x in range(W):
                c = grid[y][x]
                if c != T_VALUE:
                    counts[c] += 1

        missing = [c for c in range(n_colors) if counts.get(c, 0) == 0]
        if not missing:
            break

        # 가장 많은 색 (최소 20 이상이어야 10을 뺄 수 있음)
        donor_candidates = [(cnt, c) for c, cnt in counts.items() if cnt >= 20 and c != T_VALUE]
        if not donor_candidates:
            break
        donor_candidates.sort(reverse=True)
        donor_color = donor_candidates[0][1]

        target_color = missing[0]

        # donor 색상 셀을 경계 우선으로 정렬, 대칭 쌍 단위로 변환
        donor_cells = []
        for y in range(H):
            for x in range(W):
                if grid[y][x] == donor_color:
                    bs = _boundary_score(y, x)
                    ed = min(y, H-1-y, x, W-1-x)
                    donor_cells.append((-bs, ed, rng.random(), y, x))
        donor_cells.sort()

        converted = 0
        for _, _, _, y, x in donor_cells:
            if converted >= 10:
                break
            if grid[y][x] != donor_color:
                continue
            # 대칭 위치도 함께 변환 (가능하면)
            mirrors = get_sym_group(y, x, H, W, sym_type)
            mirrors = [(my, mx) for my, mx in mirrors if 0 <= my < H and 0 <= mx < W and grid[my][mx] == donor_color]
            mirrors = list(set(mirrors))
            if converted + len(mirrors) <= 10:
                for my, mx in mirrors:
                    grid[my][mx] = target_color
                converted += len(mirrors)
            else:
                grid[y][x] = target_color
                converted += 1

    # T 재계산
    return sum(1 for y in range(H) for x in range(W) if grid[y][x] == T_VALUE)


def smooth_jagged_boundaries(grid, W, H, max_passes=5):
    """
    경계 스무딩: 삐죽삐죽 돌출된 셀을 이웃 다수결로 정리.

    규칙:
    - 고립 셀(같은 색 이웃 0개): 다수결 색으로 변경
    - 돌출 셀(같은 색 이웃 1개, 다른 색 이웃 2+개가 동일): 그 색으로 변경
    - T셀은 건드리지 않음

    Returns: 총 변경 셀 수
    """
    total_changes = 0
    for _ in range(max_passes):
        changes = 0
        snap = [row[:] for row in grid]
        for y in range(H):
            for x in range(W):
                c = snap[y][x]
                if c == T_VALUE:
                    continue
                nbrs = []
                for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx < W and snap[ny][nx] != T_VALUE:
                        nbrs.append(snap[ny][nx])
                if not nbrs:
                    continue
                same = sum(1 for n in nbrs if n == c)
                if same == 0:
                    # 완전 고립 → 다수결
                    grid[y][x] = Counter(nbrs).most_common(1)[0][0]
                    changes += 1
                elif same == 1 and len(nbrs) >= 3:
                    # 돌출 — 나머지 이웃 중 2개 이상 동일하면 흡수
                    others = [n for n in nbrs if n != c]
                    mc, mcnt = Counter(others).most_common(1)[0]
                    if mcnt >= 2:
                        grid[y][x] = mc
                        changes += 1
        total_changes += changes
        if changes == 0:
            break
    return total_changes


def fix_x10_zone_based(grid, zm, n_colors, W, H, rng):
    """
    ×10 보정: 존 경계의 대칭 셀을 T로 변환하여 나머지 흡수.

    방법:
    1. per-color 카운트 계산
    2. 나머지 있는 색상의 색상 경계 셀을 대칭 그룹 단위로 T 변환
    3. T도 대칭 보장

    T 배치 우선순위: 색상 경계(인접 셀과 색이 다른 곳) > 외곽
    → T가 색상 간 자연스러운 구분선 역할
    """
    sym_type = "quad_mirror"  # 기본

    def get_counts():
        counts = Counter()
        for y in range(H):
            for x in range(W):
                if grid[y][x] != T_VALUE:
                    counts[grid[y][x]] += 1
        return counts

    def total_remainder(counts):
        return sum(c % 10 for c in counts.values())

    # 색상 경계 점수: 4방향 이웃 중 자신과 다른 색(T 제외)이 몇 개인지
    def boundary_score(y, x):
        """0=내부(이웃 모두 같은 색), 1~4=경계(높을수록 강한 경계)"""
        c = grid[y][x]
        diff = 0
        for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
            ny, nx = y+dy, x+dx
            if 0 <= ny < H and 0 <= nx < W:
                nc = grid[ny][nx]
                if nc != c and nc != T_VALUE:
                    diff += 1
            else:
                diff += 1  # 그리드 외부도 경계로 취급
        return diff

    # 대칭 그룹 사전 계산
    visited = [[False]*W for _ in range(H)]
    groups = []
    for y in range(H):
        for x in range(W):
            if visited[y][x]: continue
            grp = get_sym_group(y, x, H, W, sym_type)
            grp = [(gy, gx) for gy, gx in grp if 0 <= gy < H and 0 <= gx < W]
            grp = list(set(grp))
            for gy, gx in grp:
                visited[gy][gx] = True
            groups.append(grp)

    min_gs = min(len(g) for g in groups)

    # 외곽 거리
    def edge_dist(y, x):
        return min(y, H-1-y, x, W-1-x)

    # Phase 1: 존 간 색상 재배정으로 ×10 근접 시도
    for _ in range(20):
        counts = get_counts()
        if total_remainder(counts) == 0:
            break

        # 나머지가 큰 색 → 나머지가 작은 색으로 존 재배정
        color_rem = {c: counts.get(c, 0) % 10 for c in range(n_colors)}
        colors_with_rem = [c for c in range(n_colors) if color_rem[c] > 0]
        if not colors_with_rem:
            break

        improved = False
        # 가장 작은 존부터 색상 변경 시도
        zone_sizes = zm.zone_sizes()
        small_zones = sorted(zone_sizes.keys(), key=lambda z: zone_sizes[z])

        for zid in small_zones:
            zsize = zone_sizes[zid]
            if zsize > 40:  # 너무 큰 존은 건드리지 않음
                continue
            # 이 존의 현재 색상
            cells = zm.zone_cells[zid]
            cur_color = grid[cells[0][0]][cells[0][1]]
            if cur_color == T_VALUE:
                continue

            cur_rem = counts.get(cur_color, 0) % 10
            if cur_rem == 0:
                continue

            # 다른 색상으로 바꿨을 때 총 나머지 감소하는지 확인
            best_new_color = None
            best_reduction = 0

            for new_c in range(n_colors):
                if new_c == cur_color:
                    continue
                # 변경 시뮬레이션
                old_c_cnt = counts.get(cur_color, 0) - zsize
                new_c_cnt = counts.get(new_c, 0) + zsize
                old_rem = cur_rem + (counts.get(new_c, 0) % 10)
                new_rem = (old_c_cnt % 10) + (new_c_cnt % 10)
                reduction = old_rem - new_rem
                if reduction > best_reduction:
                    best_reduction = reduction
                    best_new_color = new_c

            if best_new_color is not None and best_reduction > 0:
                # 색상 소멸 방지: 변경 후 cur_color가 0이면 절대 스킵
                remaining = counts.get(cur_color, 0) - zsize
                if remaining == 0:
                    continue
                if remaining > 0 and remaining < 10:
                    continue
                # 존 전체 색상 변경
                for cy, cx in cells:
                    grid[cy][cx] = best_new_color
                counts[cur_color] -= zsize
                counts[best_new_color] = counts.get(best_new_color, 0) + zsize
                improved = True
                break

        if not improved:
            break

    # Phase 2: 남은 나머지 처리 — T셀 전략
    # 원칙:
    #   mod10==0 → T=0 강제 (존 경계 미세조정으로 해결)
    #   mod10≠0 → 최소 T만 외곽 코너에서 연속 블록으로 배치
    total_cells = W * H
    min_t = total_cells % 10  # 물리적 최소 T

    counts = get_counts()
    cur_remainder = total_remainder(counts)

    if cur_remainder == 0:
        # 이미 완벽 — T 필요 없음
        t_count = sum(1 for y in range(H) for x in range(W) if grid[y][x] == T_VALUE)
        return t_count

    # Phase 2a: 셀 단위 미세조정 — 비활성화!
    # 셀 swap은 패턴 프래그멘테이션의 주범. 나머지는 T셀로 처리.
    for micro_round in range(0):  # DISABLED
        counts = get_counts()
        if total_remainder(counts) == 0:
            break

        # 나머지 있는 색상 찾기
        color_rem = {c: counts.get(c, 0) % 10 for c in range(n_colors) if counts.get(c, 0) > 0}
        colors_with_rem = [(rem, c) for c, rem in color_rem.items() if rem > 0]
        if not colors_with_rem:
            break
        colors_with_rem.sort(reverse=True)  # 나머지 큰 것 먼저

        improved = False
        for _, src_color in colors_with_rem:
            src_rem = counts.get(src_color, 0) % 10
            if src_rem == 0:
                continue

            # src_color의 경계 셀 수집 (인접 셀이 다른 색인 곳)
            boundary_cells = []
            for y in range(H):
                for x in range(W):
                    if grid[y][x] != src_color:
                        continue
                    for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                        ny, nx = y+dy, x+dx
                        if 0 <= ny < H and 0 <= nx < W:
                            nc = grid[ny][nx]
                            if nc != src_color and nc != T_VALUE:
                                boundary_cells.append((y, x, ny, nx, nc))

            rng.shuffle(boundary_cells)

            for y, x, ny, nx, dst_color in boundary_cells:
                if grid[y][x] != src_color or grid[ny][nx] != dst_color:
                    continue
                # 이 셀을 src → dst로 변경하면 나머지가 줄어드는지?
                src_cnt = counts.get(src_color, 0)
                dst_cnt = counts.get(dst_color, 0)
                old_rem = (src_cnt % 10) + (dst_cnt % 10)
                new_rem = ((src_cnt - 1) % 10) + ((dst_cnt + 1) % 10)

                if new_rem < old_rem:
                    # 색상 소멸 방지
                    if src_cnt - 1 < 10:
                        continue
                    grid[y][x] = dst_color
                    counts[src_color] -= 1
                    counts[dst_color] += 1
                    improved = True
                    break  # 한 번에 1셀씩만

            if improved:
                break

        if not improved:
            break

    # Phase 2b: 아직 나머지가 남아있다면 — 최소 T를 외곽 코너에 연속 배치
    counts = get_counts()
    cur_remainder = total_remainder(counts)

    if cur_remainder > 0 and min_t > 0:
        # 외곽 코너에서 연속 블록으로 T 배치
        need_t = min_t

        # 4코너에서 가까운 셀 순서
        corners = [(0, 0), (W-1, 0), (0, H-1), (W-1, H-1)]
        corner_cells = []
        for cy, cx in corners:
            for y in range(H):
                for x in range(W):
                    d = abs(x - cx) + abs(y - cy)
                    corner_cells.append((d, y, x))
        corner_cells.sort()

        # 나머지 있는 색상에서 코너에 가까운 셀부터 T로
        removed = 0
        for _, y, x in corner_cells:
            if removed >= need_t:
                break
            c = grid[y][x]
            if c == T_VALUE:
                continue
            rem = counts.get(c, 0) % 10
            if rem == 0:
                continue
            grid[y][x] = T_VALUE
            counts[c] -= 1
            removed += 1

    elif cur_remainder > 0 and min_t == 0:
        # mod10==0인데 아직 나머지가 남아있음 → Phase 2a가 부족했음
        # 전략: 각 색상의 remainder를 0으로 만들어야 함
        # 셀 1개를 src→dst로 이동하면 src -1, dst +1
        # 전체 remainder 변화 = 새remainder합 - 이전remainder합
        prev_tr = 9999
        stall_count = 0
        for swap_round in range(500):  # 2000→500 + 조기탈출
            counts = get_counts()
            tr = total_remainder(counts)
            if tr == 0:
                break
            # 정체 감지: 50라운드 동안 개선 없으면 T셀 전환
            if tr >= prev_tr:
                stall_count += 1
            else:
                stall_count = 0
            prev_tr = tr
            if stall_count >= 50:
                break  # Phase 2c에서 T로 처리

            # 모든 가능한 (src, dst) 방향에 대해 전체 remainder 감소량 계산
            best_improvement = 0
            best_src = -1
            best_dst = -1
            for src in range(n_colors):
                src_cnt = counts.get(src, 0)
                if src_cnt <= 10:
                    continue
                src_rem = src_cnt % 10
                if src_rem == 0:
                    # src에서 빼면 remainder 증가 — 하지만 dst 쪽이 더 줄면 net 개선 가능
                    pass
                for dst in range(n_colors):
                    if dst == src:
                        continue
                    dst_cnt = counts.get(dst, 0)
                    old_pair = (src_cnt % 10) + (dst_cnt % 10)
                    new_pair = ((src_cnt - 1) % 10) + ((dst_cnt + 1) % 10)
                    improvement = old_pair - new_pair
                    if improvement > best_improvement:
                        best_improvement = improvement
                        best_src = src
                        best_dst = dst

            if best_improvement <= 0:
                # 직접 개선 불가 → 2셀 동시 교환(swap) 시도
                # A에서 B로 1개, B에서 C로 1개 → 체인 이동
                found_chain = False
                for c1 in range(n_colors):
                    cnt1 = counts.get(c1, 0)
                    if cnt1 <= 10:
                        continue
                    for c2 in range(n_colors):
                        if c2 == c1:
                            continue
                        cnt2 = counts.get(c2, 0)
                        if cnt2 <= 10:
                            continue
                        # swap: c1 셀 1개를 c2에 인접한 셀의 색으로, c2 셀 1개를 c1에 인접한 셀의 색으로
                        # 실질적으로 c1과 c2의 경계 셀 1개 교환
                        old_pair = (cnt1 % 10) + (cnt2 % 10)
                        new_pair = ((cnt1 - 1) % 10) + ((cnt2 + 1) % 10)
                        # swap은 양방향이므로: c1-1,c2+1 vs c1+1,c2-1 중 하나라도 개선이면 OK
                        # 하지만 이건 위에서 체크한 것. 정체 상태라면 random perturbation
                        pass

                # Smooth-aware perturbation: 돌출 셀 우선 이동 (경계 스무딩 효과)
                all_boundary = []
                for y in range(H):
                    for x in range(W):
                        c = grid[y][x]
                        if c == T_VALUE:
                            continue
                        dst_colors = []
                        same_count = 0
                        for dy2, dx2 in [(-1,0),(1,0),(0,-1),(0,1)]:
                            ny, nx = y+dy2, x+dx2
                            if 0 <= ny < H and 0 <= nx < W:
                                nc = grid[ny][nx]
                                if nc == c:
                                    same_count += 1
                                elif nc != T_VALUE and counts.get(c, 0) > 10:
                                    dst_colors.append(nc)
                        if dst_colors:
                            # 돌출도 = same_count (낮을수록 돌출)
                            # 목표색 = 이웃 중 다수결
                            best_dst_c = Counter(dst_colors).most_common(1)[0][0]
                            all_boundary.append((same_count, y, x, c, best_dst_c))
                if not all_boundary:
                    break
                all_boundary.sort()  # 돌출 셀 우선 (same_count 낮은 순)
                _, by, bx, bsrc, bdst = all_boundary[0]
                grid[by][bx] = bdst
                counts[bsrc] -= 1
                counts[bdst] = counts.get(bdst, 0) + 1
                continue

            # 최적 src→dst 방향 찾음, 경계 셀 이동
            moved = False
            candidates = []
            for y in range(H):
                for x in range(W):
                    if grid[y][x] != best_src:
                        continue
                    for dy2, dx2 in [(-1,0),(1,0),(0,-1),(0,1)]:
                        ny, nx = y+dy2, x+dx2
                        if 0 <= ny < H and 0 <= nx < W and grid[ny][nx] == best_dst:
                            candidates.append((y, x))
                            break
            if candidates:
                # 돌출 셀 우선 선택 (같은 색 이웃 적은 것 = 더 돌출)
                def _protrusion_score(pos):
                    py, px = pos
                    return sum(1 for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]
                               if 0 <= py+dy < H and 0 <= px+dx < W and grid[py+dy][px+dx] == best_src)
                candidates.sort(key=_protrusion_score)
                cy, cx = candidates[0]
                grid[cy][cx] = best_dst
                counts[best_src] -= 1
                counts[best_dst] += 1
            else:
                # src와 dst가 인접하지 않음 → 체인 경유
                # src에 인접한 다른 색 mid를 찾아 src→mid, 그 후 mid→dst 시도
                bridged = False
                for y in range(H):
                    if bridged:
                        break
                    for x in range(W):
                        if bridged:
                            break
                        if grid[y][x] != best_src:
                            continue
                        for dy2, dx2 in [(-1,0),(1,0),(0,-1),(0,1)]:
                            ny, nx = y+dy2, x+dx2
                            if 0 <= ny < H and 0 <= nx < W:
                                mid = grid[ny][nx]
                                if mid != best_src and mid != T_VALUE and counts.get(best_src, 0) > 10:
                                    grid[y][x] = mid
                                    counts[best_src] -= 1
                                    counts[mid] = counts.get(mid, 0) + 1
                                    bridged = True
                                    break
                if not bridged:
                    break

    # Phase 2c: 정체 후 남은 remainder → T셀로 흡수 (돌출 셀 우선)
    counts = get_counts()
    if total_remainder(counts) > 0:
        for t_fallback in range(W * H):
            counts = get_counts()
            if total_remainder(counts) == 0:
                break
            # 나머지 있는 색상의 돌출 셀 찾기
            best = None
            for y in range(H):
                for x in range(W):
                    c = grid[y][x]
                    if c == T_VALUE:
                        continue
                    if counts.get(c, 0) % 10 == 0:
                        continue
                    if counts.get(c, 0) <= 10:
                        continue  # 색 소멸 방지
                    same = sum(1 for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]
                               if 0 <= y+dy < H and 0 <= x+dx < W and grid[y+dy][x+dx] == c)
                    ed = min(y, H-1-y, x, W-1-x)
                    if best is None or same < best[0] or (same == best[0] and ed < best[1]):
                        best = (same, ed, y, x, c)
            if best is None:
                break
            _, _, by, bx, bc = best
            grid[by][bx] = T_VALUE
            counts[bc] -= 1

    # Phase 3: T셀 위치 재배치 — 중앙에 있는 T를 코너로 이동
    # T셀과 유색 셀의 위치를 교환 (색상 카운트 불변, 위치만 변경)
    t_positions = [(y, x) for y in range(H) for x in range(W) if grid[y][x] == T_VALUE]
    if t_positions:
        def corner_dist(y, x):
            return min(abs(x) + abs(y),
                       abs(x - (W-1)) + abs(y),
                       abs(x) + abs(y - (H-1)),
                       abs(x - (W-1)) + abs(y - (H-1)))

        for _ in range(len(t_positions) * 5):  # 여러 라운드 시도
            t_positions = [(y, x) for y in range(H) for x in range(W) if grid[y][x] == T_VALUE]
            if not t_positions:
                break

            # 가장 중앙에 가까운 T셀 (코너에서 가장 먼 T)
            t_by_dist = sorted(t_positions, key=lambda p: -corner_dist(p[0], p[1]))
            ty, tx = t_by_dist[0]
            t_cdist = corner_dist(ty, tx)

            if t_cdist <= 2:
                break  # 모든 T가 이미 코너 근처

            # 이 T셀과 교환할 유색 셀 찾기: 코너에 더 가까운 유색 셀
            # 같은 색상이면 교환해도 카운트 불변 → 아무 유색 셀이나 교환 가능
            best_swap = None
            best_swap_dist = t_cdist
            for y in range(H):
                for x in range(W):
                    c = grid[y][x]
                    if c == T_VALUE:
                        continue
                    cd = corner_dist(y, x)
                    if cd < best_swap_dist:
                        best_swap = (y, x, c)
                        best_swap_dist = cd

            if best_swap is None or best_swap_dist >= t_cdist:
                break  # 개선 불가

            sy, sx, sc = best_swap
            # 교환: T↔유색
            grid[ty][tx] = sc
            grid[sy][sx] = T_VALUE
            # 색상 카운트는 변하지 않음 (같은 색이 같은 수만큼 존재)

    # T 카운트
    t_count = sum(1 for y in range(H) for x in range(W) if grid[y][x] == T_VALUE)
    return t_count


# ══════════════════════════════════════════════════════════
# STAGE 2: 선별 (10 → 5)
# ══════════════════════════════════════════════════════════

def select_top5(seeds, W, H, has_life_gimmick):
    """×10 친화도 + T 최소화로 5개 선별"""
    scored = []
    for s in seeds:
        grid = s['grid']
        nc = s['num_colors']
        counts = Counter()
        for y in range(H):
            for x in range(W):
                v = grid[y][x]
                if v != T_VALUE:
                    counts[v] += 1

        x10_pass = all(counts.get(c, 0) % 10 == 0 for c in range(nc))
        t_cells = s['t_count']
        remainder = sum(counts.get(c, 0) % 10 for c in range(nc))

        score = 0
        if x10_pass: score += 1000
        score -= remainder * 50
        score -= t_cells * 2

        scored.append((score, s))

    scored.sort(key=lambda x: -x[0])
    return [s for _, s in scored[:5]]


# ══════════════════════════════════════════════════════════
# STAGE 3: 평가
# ══════════════════════════════════════════════════════════

def evaluate_candidate(seed_info, grid, W, H, has_life_gimmick):
    """종합 평가 스코어"""
    n_colors = seed_info['num_colors']
    sym_type = seed_info.get('symmetry', 'quad_mirror')

    # ×10 체크
    counts = Counter()
    for y in range(H):
        for x in range(W):
            if grid[y][x] != T_VALUE:
                counts[grid[y][x]] += 1
    x10_pass = all(counts.get(c, 0) % 10 == 0 for c in range(n_colors))

    # T셀 수
    t_cells = sum(1 for y in range(H) for x in range(W) if grid[y][x] == T_VALUE)
    max_t = max((W * H) % 10, 10)
    t_score = 1.0 - min(t_cells / max(max_t * 5, 1), 1.0)

    # T 대칭도
    t_sym_score = 1.0
    if t_cells > 0:
        visited_t = [[False]*W for _ in range(H)]
        t_grps_total = 0
        t_grps_sym = 0
        for ty in range(H):
            for tx in range(W):
                if visited_t[ty][tx] or grid[ty][tx] != T_VALUE:
                    continue
                grp = get_sym_group(ty, tx, H, W, sym_type)
                for sy, sx in grp:
                    if 0 <= sy < H and 0 <= sx < W:
                        visited_t[sy][sx] = True
                t_grps_total += 1
                if all(0 <= sy < H and 0 <= sx < W and grid[sy][sx] == T_VALUE for sy, sx in grp):
                    t_grps_sym += 1
        t_sym_score = t_grps_sym / max(t_grps_total, 1)

    # 시각 품질: 고립 픽셀 체크
    noise = 0
    total_checked = 0
    for y in range(H):
        for x in range(W):
            c = grid[y][x]
            if c == T_VALUE: continue
            total_checked += 1
            same = 0
            total_n = 0
            for dy, dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                ny, nx = y+dy, x+dx
                if 0 <= ny < H and 0 <= nx < W:
                    total_n += 1
                    if grid[ny][nx] == c:
                        same += 1
            if total_n > 0 and same == 0:
                noise += 1
    # PixelFlow 기준: ~12%가 고립/소그룹이므로 15%까지 허용 (이전: 5%)
    noise_score = 1.0 - min(noise / max(total_checked * 0.15, 1), 1.0)

    # 색상 분포 균형
    if counts:
        vals = list(counts.values())
        avg = sum(vals) / len(vals)
        variance = sum((v - avg)**2 for v in vals) / len(vals)
        balance_score = 1.0 / (1.0 + variance / max(avg**2, 1))
    else:
        balance_score = 0.0

    # 색상 대비
    colors = seed_info.get('colors', [])
    if len(colors) >= 2:
        min_dist = float('inf')
        for i in range(len(colors)):
            for j in range(i+1, len(colors)):
                d = color_distance(colors[i], colors[j])
                if d < min_dist:
                    min_dist = d
        contrast_score = min(min_dist / 200.0, 1.0)
    else:
        contrast_score = 1.0

    visual_quality = noise_score * 0.4 + balance_score * 0.3 + contrast_score * 0.3

    total_score = (
        0.25 * visual_quality +
        0.10 * t_score +
        0.25 * t_sym_score +
        0.40 * (1.0 if x10_pass else 0.0)
    )

    # 클러스터 분포 분석 (PixelFlow 비교용)
    from collections import deque as _dq
    _visited = [[False]*W for _ in range(H)]
    _cluster_sizes = []
    for _y in range(H):
        for _x in range(W):
            if _visited[_y][_x] or grid[_y][_x] == T_VALUE:
                continue
            _c = grid[_y][_x]
            _q = _dq([(_y, _x)])
            _visited[_y][_x] = True
            _sz = 0
            while _q:
                _cy, _cx = _q.popleft()
                _sz += 1
                for _dy, _dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                    _ny, _nx = _cy+_dy, _cx+_dx
                    if 0 <= _ny < H and 0 <= _nx < W and not _visited[_ny][_nx] and grid[_ny][_nx] == _c:
                        _visited[_ny][_nx] = True
                        _q.append((_ny, _nx))
            _cluster_sizes.append(_sz)

    _tc = sum(_cluster_sizes) if _cluster_sizes else 1
    _le3 = sum(s for s in _cluster_sizes if s <= 3) * 100 / _tc if _tc else 0
    cluster_dist = {
        'le3_pct': round(_le3, 1),
        'f4to10_pct': round(sum(s for s in _cluster_sizes if 4 <= s <= 10) * 100 / _tc, 1) if _tc else 0,
        'f11to30_pct': round(sum(s for s in _cluster_sizes if 11 <= s <= 30) * 100 / _tc, 1) if _tc else 0,
        'gt30_pct': round(sum(s for s in _cluster_sizes if s > 30) * 100 / _tc, 1) if _tc else 0,
    }

    return {
        'seed_idx': seed_info['seed_id'],
        'x10_pass': x10_pass,
        'grid': grid,
        'colors': seed_info['colors'],
        'num_colors': n_colors,
        'has_border_coat': seed_info.get('has_border_coat', False),
        't_cells': t_cells,
        't_sym_score': round(t_sym_score, 3),
        'noise_score': round(noise_score, 3),
        'visual_quality': round(visual_quality, 3),
        'total_score': round(total_score, 3),
        'cluster_dist': cluster_dist,
    }


# ══════════════════════════════════════════════════════════
# 렌더링
# ══════════════════════════════════════════════════════════

def make_image(grid, palette_hex, W, H, block=20):
    img = Image.new("RGBA", (W*block, H*block), (0, 0, 0, 0))
    px = img.load()
    for gy in range(H):
        for gx in range(W):
            c = grid[gy][gx]
            if c == T_VALUE:
                col = (0, 0, 0, 0)
            elif isinstance(c, int) and 0 <= c < len(palette_hex):
                col = hex2rgb(palette_hex[c]) + (255,)
            else:
                col = (0, 0, 0, 0)
            for py in range(block):
                for ppx in range(block):
                    px[gx*block+ppx, gy*block+py] = col
    return img


# ══════════════════════════════════════════════════════════
# 기믹 관련
# ══════════════════════════════════════════════════════════
LIFE_ADJUSTABLE_GIMMICKS = {'gimmick_pinata', 'gimmick_pin', 'gimmick_pinata_box'}


# ══════════════════════════════════════════════════════════
# 메인 파이프라인
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    CSV_PATH = "/sessions/ecstatic-intelligent-bell/mnt/uploads/00_BalloonFlow_LevelDesign - Level Design (12)-4e267e24.csv"
    # v45: 경계 스무딩 추가 — ×10 보정 후 돌출 셀 제거 + 반복 수렴
    TARGET_LEVELS_ALL = {1,3,4,5,7,14,18,20,21,23,25,27,37,50,51,59,64,65,70,72,76,78,81,88,115,123,137,139,144,156,163,167,203,209,231,248,262,263,271,274,292}
    TARGET_LEVELS = {1}  # Lv1 rotational 나선 테스트

    OUT_DIR = "/sessions/ecstatic-intelligent-bell/mnt/balloonflow/2026-05-21_v47_motif"
    os.makedirs(OUT_DIR, exist_ok=True)
    BLOCK = 1
    N_SEEDS = 20
    N_FINAL = 2

    # CSV 파싱
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    header = reader[2] if len(reader) > 2 else []
    gimmick_col_indices = {}
    for i, col_name in enumerate(header):
        cn = col_name.strip().lower()
        if cn.startswith('gimmick_'):
            gimmick_col_indices[cn] = i

    levels = []
    for row in reader[3:]:
        if not row or not row[0].strip():
            continue
        try:
            lv = int(row[0].strip())
        except:
            continue
        if lv in TARGET_LEVELS:
            W = int(row[11].strip())
            H = int(row[12].strip())
            n_colors = int(row[8].strip())
            bl_meta = row[50].strip() if len(row) > 50 else ""
            has_life_gimmick = False
            for gname in LIFE_ADJUSTABLE_GIMMICKS:
                idx = gimmick_col_indices.get(gname)
                if idx and idx < len(row):
                    try:
                        if int(row[idx].strip()) > 0:
                            has_life_gimmick = True
                            break
                    except:
                        pass
            levels.append((lv, W, H, n_colors, bl_meta, has_life_gimmick))

    print(f"{'Lv':>4} | {'Size':>7} | {'C':>2} | {'M':>1} | {'BL Metaphor':<35} | Best Seeds")
    print("=" * 110)

    all_results = []

    for lv, W, H, n_colors, bl_meta, has_life_gimmick in sorted(levels, key=lambda x: x[0]):
        try:
            # STAGE 1: 존 기반 시드 생성
            seeds = generate_zone_seeds(W, H, n_colors, bl_meta, lv, N_SEEDS)

            # STAGE 2: 선별
            top5 = select_top5(seeds, W, H, has_life_gimmick)

            # STAGE 3: 평가
            candidates = []
            for s in top5:
                eval_result = evaluate_candidate(s, s['grid'], W, H, has_life_gimmick)
                candidates.append(eval_result)

            # 최종 2개 선택
            candidates.sort(key=lambda c: -c['total_score'])
            final = candidates[:N_FINAL]

            # 렌더링
            labels = ['A', 'B']
            safe_meta = bl_meta.replace("/", "_").replace(" ", "_")[:25]
            for i, c in enumerate(final):
                img = make_image(c['grid'], c['colors'], W, H, BLOCK)
                fname = f"level_{lv:03d}_{safe_meta}_{labels[i]}.png"
                img.save(os.path.join(OUT_DIR, fname))

            # 결과 기록
            result = {
                'level': lv,
                'metaphor': bl_meta,
                'board_size': [W, H],
                'num_colors': n_colors,
                'has_life_gimmick': has_life_gimmick,
                'final_candidates': final,
            }
            all_results.append(result)

            status = "✓" if all(c['x10_pass'] for c in final) else "✗"
            cands_str = " | ".join(
                f"s{c['seed_idx']}={c['total_score']:.2f}{status}(T={c['t_cells']})"
                for c in final
            )
            sym = resolve_zone_metaphor(bl_meta, n_colors)[0][0].upper()  # first char of sym_type
            print(f"{lv:>4} | {W:>2}×{H:<3} | {n_colors:>2} | {sym} | {bl_meta:<35} | {cands_str}")

        except Exception as e:
            print(f"{lv:>4} | ERROR: {e}")
            import traceback
            traceback.print_exc()

    # evaluation.json 저장
    eval_path = os.path.join(OUT_DIR, "evaluation.json")
    with open(eval_path, "w", encoding="utf-8") as f:
        # grid는 직렬화에서 제외 (큼)
        save_data = []
        for r in all_results:
            rd = dict(r)
            rd['final_candidates'] = []
            for c in r['final_candidates']:
                cd = {k: v for k, v in c.items() if k != 'grid'}
                rd['final_candidates'].append(cd)
            save_data.append(rd)
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    print("=" * 110)
    print(f"완료: {len(levels)} 레벨, 각 {N_FINAL}개 후보 → {OUT_DIR}")
    print(f"평가 결과: {eval_path}")
