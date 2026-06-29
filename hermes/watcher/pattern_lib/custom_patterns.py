import math
from collections import Counter

# ─────────────────────────────────────────────────────────────
# 공통 유틸
# ─────────────────────────────────────────────────────────────
def _sym4(grid, W, H):
    """상하+좌우 대칭 강제 적용"""
    for gy in range(H):
        for gx in range(W):
            mirror_x = grid[gy][W-1-gx]
            mirror_y = grid[H-1-gy][gx]
            mirror_xy = grid[H-1-gy][W-1-gx]
            # 좌상단 기준으로 나머지 3사분면 덮어씌우기
            if gy < H//2 and gx < W//2:
                v = grid[gy][gx]
                grid[gy][W-1-gx]     = v
                grid[H-1-gy][gx]     = v
                grid[H-1-gy][W-1-gx] = v
    return grid

def _sym_radial(grid, W, H, n):
    """n방향 방사 대칭"""
    cx, cy = (W-1)/2.0, (H-1)/2.0
    result = [row[:] for row in grid]
    for gy in range(H):
        for gx in range(W):
            dx, dy = gx-cx, gy-cy
            ang = math.atan2(dy, dx)
            r = math.sqrt(dx**2+dy**2)
            # 첫 번째 섹터로 접기
            seg = (2*math.pi/n)
            ang_fold = ang % seg
            sx = int(cx + r*math.cos(ang_fold) + 0.5)
            sy = int(cy + r*math.sin(ang_fold) + 0.5)
            if 0<=sx<W and 0<=sy<H:
                result[gy][gx] = grid[sy][sx]
    return result

# ─────────────────────────────────────────────────────────────
# Lv1: 수직 2색 분할 + 다트 음각
# ─────────────────────────────────────────────────────────────
def pattern_dart_silhouette(W, H, n):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            # 다트 실루엣: 위 뾰족 + 아래 날개
            dx, dy = gx-cx, gy-cy
            norm_y = dy/cy if cy else 0
            dart_w = abs(norm_y) * (W*0.35) + 1  # 위아래로 좁아지는 다트
            in_dart = abs(dx) < dart_w and norm_y < 0.6
            if in_dart:
                row.append(0)  # 다트 음각 (배경색)
            else:
                row.append(1 if gx < W//2 else (min(2, n-1)))
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv3: 대각선 스트라이프 + 우하단 삼각형
# ─────────────────────────────────────────────────────────────
def pattern_stripe_triangle(W, H, n):
    grid = []
    stripe_w = max(3, W//6)
    for gy in range(H):
        row = []
        for gx in range(W):
            # 우하단 삼각형 영역: gx/W + gy/H > 1.3
            if gx/W + gy/H > 1.35:
                row.append(min(n-1, 2))
            else:
                row.append(((gx+gy)//stripe_w) % max(2, n-1))
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv4: 모래시계 (위아래 삼각형)
# ─────────────────────────────────────────────────────────────
def pattern_hourglass(W, H, n):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            dx, dy = abs(gx-cx)/cx, abs(gy-cy)/cy if cy else 0
            # 모래시계 내부: |dx| < |dy| (중심에서 수직축에 가까울수록 내부)
            in_glass = dx < (1-dy)*0.9
            if in_glass:
                # 위/아래 절반으로 색상 구분
                half = 0 if gy < H//2 else 1
                # 중심에서 거리로 내부 음영
                dist = math.sqrt((gx-cx)**2+(gy-cy)**2)
                band = int(dist / (min(W,H)*0.15)) % max(2, n//2)
                row.append((half * (n//2) + band) % n)
            else:
                row.append(min(n-1, 3))
        grid.append(row)
    return _sym4(grid, W, H)

# ─────────────────────────────────────────────────────────────
# Lv7: 테두리 프레임 + 내부 패턴
# ─────────────────────────────────────────────────────────────
def pattern_border_frame(W, H, n):
    frame_w = max(2, min(W, H)//8)
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            # 거리 기반 레이어
            dist_border = min(gx, W-1-gx, gy, H-1-gy)
            layer = dist_border // frame_w
            row.append(layer % n)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv14: 다트판 (동심원 링)
# ─────────────────────────────────────────────────────────────
def pattern_dartboard(W, H, n):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    max_r = math.sqrt(cx**2+cy**2)
    ring_w = max_r / n
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            r = math.sqrt((gx-cx)**2+(gy-cy)**2)
            ring = int(r/ring_w) % n
            row.append(ring)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv21: 코너에서 시작하는 L자 스트라이프
# ─────────────────────────────────────────────────────────────
def pattern_corner_L(W, H, n):
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            # 좌상단 코너 기준 체비쇼프 거리
            d = max(gx, gy)
            row.append(d % n)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv23: 다이아몬드 파셋 (잘린 면)
# ─────────────────────────────────────────────────────────────
def pattern_diamond_facet(W, H, n):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            dx, dy = (gx-cx)/cx, (gy-cy)/(cy if cy else 1)
            # 다이아몬드 외곽 (|dx|+|dy| <= 1)
            in_diamond = abs(dx)+abs(dy) <= 0.92
            if in_diamond:
                # 파셋: 각도를 n등분
                ang = (math.degrees(math.atan2(dy, dx)) + 360) % 360
                facet = int(ang / 360 * n) % n
                row.append(facet)
            else:
                row.append(0)  # 배경
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv25: 삼각형 테셀레이션
# ─────────────────────────────────────────────────────────────
def pattern_triangle_tessellation(W, H, n):
    tile = max(4, min(W, H)//6)
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            tx, ty = gx // tile, gy // tile
            lx, ly = gx % tile, gy % tile
            # 타일 내 대각선으로 삼각형 2개
            upper = ly < lx * tile // tile  # 상삼각 vs 하삼각
            tri_id = (tx + ty * 2 + (1 if lx+ly >= tile else 0)) % n
            row.append(tri_id)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv41: 지그재그 (chevron)
# ─────────────────────────────────────────────────────────────
def pattern_chevron(W, H, n):
    band = max(3, H//8)
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            # V자 형태: |gx - W/2| + gy % band
            v = (abs(gx*2 - W) // 2 + gy) % (band * n)
            row.append(v // band % n)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv50: 직조 패턴 (woven)
# ─────────────────────────────────────────────────────────────
def pattern_woven(W, H, n):
    stripe = max(2, min(W, H)//10)
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            h_band = (gx // stripe) % n
            v_band = (gy // stripe) % n
            # 교차점: 수직 밴드가 수평 밴드 위에 오게 (짝수줄)
            if (gy // stripe) % 2 == 0:
                row.append(h_band)
            else:
                row.append(v_band)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv51: 원형 나선 (동심원 + 회전 오프셋)
# ─────────────────────────────────────────────────────────────
def pattern_spiral(W, H, n):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    max_r = math.sqrt(cx**2+cy**2)
    ring_w = max_r / (n * 2)
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            dx, dy = gx-cx, gy-cy
            r = math.sqrt(dx**2+dy**2)
            ang = (math.degrees(math.atan2(dy, dx)) + 360) % 360
            # 나선: 반지름 + 각도 결합
            spiral_val = int(r/ring_w + ang/360*2) % n
            row.append(spiral_val)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv59: 마름모 격자 (diamond lattice)
# ─────────────────────────────────────────────────────────────
def pattern_diamond_lattice(W, H, n):
    size = max(4, min(W, H)//8)
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            u = (gx+gy) // size
            v = (gx-gy+H) // size
            row.append((u+v) % n)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv65: 웨이브 패턴
# ─────────────────────────────────────────────────────────────
def pattern_wave(W, H, n):
    amp = H // (n * 2)
    freq = 2 * math.pi / W * 2
    band_h = max(2, H // (n * 2))
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            wave_offset = int(amp * math.sin(freq * gx))
            adjusted_y = gy + wave_offset
            row.append((adjusted_y // band_h) % n)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv76: 매듭/켈트 (과감한 교차 링)
# ─────────────────────────────────────────────────────────────
def pattern_knot(W, H, n):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    grid = []
    loop_r = min(cx, cy) * 0.45
    centers = [
        (cx - loop_r*0.8, cy - loop_r*0.5),
        (cx + loop_r*0.8, cy - loop_r*0.5),
        (cx,              cy + loop_r),
    ]
    thick = max(2, min(W,H)//10)
    for gy in range(H):
        row = []
        for gx in range(W):
            # 각 루프까지의 거리 계산 → 가장 가까운 루프 색상
            dists = []
            for i, (lx, ly) in enumerate(centers):
                dx, dy = gx-lx, gy-ly
                r = math.sqrt(dx**2+dy**2)
                # 루프: ring_r ± thick
                ring_dist = abs(r - loop_r*1.1)
                dists.append((ring_dist, i))
            dists.sort()
            min_d, closest = dists[0]
            if min_d < thick:
                row.append(closest % n)
            else:
                # 배경: 만다라 방사 패턴
                dx2, dy2 = gx-cx, gy-cy
                ang = (math.degrees(math.atan2(dy2, dx2))+360)%360
                row.append(int(ang/(360/n)) % n)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv78: 만다라 (다중 방사)
# ─────────────────────────────────────────────────────────────
def pattern_mandala(W, H, n, arms=8):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    max_r = math.sqrt(cx**2+cy**2)
    ring_w = max_r / n
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            dx, dy = gx-cx, gy-cy
            r = math.sqrt(dx**2+dy**2)
            ang = (math.degrees(math.atan2(dy, dx))+360) % 360
            # 방사 섹터 + 동심원 결합
            sector = int(ang / (360/arms)) % 2
            ring = int(r/ring_w) % n
            row.append((ring + sector) % n)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv81: 꽃형 만다라 (페탈 형태)
# ─────────────────────────────────────────────────────────────
def pattern_flower_mandala(W, H, n, petals=6):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    max_r = math.sqrt(cx**2+cy**2)
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            dx, dy = gx-cx, gy-cy
            r = math.sqrt(dx**2+dy**2)
            ang = math.atan2(dy, dx)
            # 꽃잎 경계: r < petal_r(ang)
            petal_r = max_r * 0.45 * (1 + 0.6*math.cos(petals*ang))
            if r < petal_r * 0.35:
                row.append(0)  # 중심
            elif r < petal_r:
                ring = int(r / (max_r*0.12)) % (n-1) + 1
                row.append(ring % n)
            else:
                # 외곽 배경 패턴
                ring_out = int(r / (max_r*0.15)) % n
                row.append(ring_out)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv85: 도트 격자
# ─────────────────────────────────────────────────────────────
def pattern_dot_grid(W, H, n):
    spacing = max(4, min(W,H)//8)
    dot_r = max(1, spacing//3)
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            # 가장 가까운 격자점
            nx = round(gx/spacing)*spacing
            ny = round(gy/spacing)*spacing
            dist = math.sqrt((gx-nx)**2+(gy-ny)**2)
            dot_id = ((nx//spacing) + (ny//spacing)*3) % (n-1)
            if dist <= dot_r:
                row.append(dot_id + 1)  # 도트 색
            else:
                row.append(0)           # 배경
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# Lv88: 기하 모자이크 (voronoi-like)
# ─────────────────────────────────────────────────────────────
def pattern_mosaic(W, H, n, seed=88):
    import random
    rng = random.Random(seed)
    k = n * 3  # 씨앗 수
    seeds = [(rng.randint(0,W-1), rng.randint(0,H-1), i%n) for i in range(k)]
    grid = []
    for gy in range(H):
        row = []
        for gx in range(W):
            best_d, best_c = float('inf'), 0
            for sx, sy, sc in seeds:
                d = abs(gx-sx)+abs(gy-sy)  # 맨해튼 거리
                if d < best_d:
                    best_d, best_c = d, sc
            row.append(best_c)
        grid.append(row)
    return grid

# ─────────────────────────────────────────────────────────────
# 레벨별 디스패치 테이블
# ─────────────────────────────────────────────────────────────
LEVEL_CUSTOM = {
    1:  lambda W,H,n: pattern_dart_silhouette(W,H,n),
    3:  lambda W,H,n: pattern_stripe_triangle(W,H,n),
    4:  lambda W,H,n: pattern_hourglass(W,H,n),
    7:  lambda W,H,n: pattern_border_frame(W,H,n),
    14: lambda W,H,n: pattern_dartboard(W,H,n),
    21: lambda W,H,n: pattern_corner_L(W,H,n),
    # 23: pattern_diamond_facet 제거 → diamond_check (seed 변주)로 폴백 (원본이 찌그러짐)
    25: lambda W,H,n: pattern_triangle_tessellation(W,H,n),
    41: lambda W,H,n: pattern_chevron(W,H,n),
    50: lambda W,H,n: pattern_woven(W,H,n),
    51: lambda W,H,n: pattern_spiral(W,H,n),
    59: lambda W,H,n: pattern_diamond_lattice(W,H,n),
    65: lambda W,H,n: pattern_wave(W,H,n),
    76: lambda W,H,n: pattern_knot(W,H,n),
    78: lambda W,H,n: pattern_mandala(W,H,n, arms=8),
    81: lambda W,H,n: pattern_flower_mandala(W,H,n, petals=6),
    85: lambda W,H,n: pattern_dot_grid(W,H,n),
    88: lambda W,H,n: pattern_mosaic(W,H,n, seed=88),
}
