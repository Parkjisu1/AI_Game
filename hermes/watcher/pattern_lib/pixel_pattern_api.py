"""
pixel_pattern_api.py
====================
기하학적 픽셀아트 패턴 생성 API

사용법:
    from pixel_pattern_api import generate_pattern
    img = generate_pattern("kaleidoscope", width=32, height=40, colors=["#FC6AAF", ...])
    img.save("out.png")

지원 패턴:
    kaleidoscope  - 8방향 대칭 만화경
    hex_tile      - 벌집형 헥사곤 타일
    maze          - DFS 백트래킹 미로
    brick         - 오프셋 벽돌 패턴
    i_tetromino   - I형 테트로미노 반복
    rect_grid     - 정사각형+직사각형 분할 패턴
    diamond_check - 다이아몬드 체커보드
    stripe        - 대각선 스트라이프
"""

import math
import random
from PIL import Image
from collections import Counter
from typing import List, Tuple, Optional


# ── 기본 팔레트 (c1~c28) ──────────────────────────────────────────────────
DEFAULT_PALETTE: List[str] = [
    "#FC6AAF","#50E8F6","#8950F8","#FED555","#73FE66","#FDA14C",
    "#FFFFFF","#414141","#6EA8FA","#39AE2E","#FC5E5E","#326BF8",
    "#3AA58B","#E7A7FA","#B7C7FB","#6A4A30","#FEE3A9","#FDB7C1",
    "#9E3D5E","#A7DD94","#592E7E","#DC7881","#D9D9E7","#6F727F",
    "#FC38A5","#FDB458","#890A08","#6FAFB1",
]

def _hex_to_rgb(h: str) -> Tuple[int,int,int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i+2],16) for i in (0,2,4))

def balance_to_x10(grid: list, W: int, H: int, bg_marker: str = "K") -> list:
    """
    각 색 셀 개수를 10배수로 맞춤. **색 치환** 방식 — 빈칸 0개, 대칭 유지, 내부 셀 우선.

    알고리즘:
      1) 각 색 목표 개수 계산 (10배수 + 합계 보존 + 4-호환성)
      2) 타겟 달성 위한 swap 실행 (source color의 orbit → target color)
      3) 내부 셀 orbit 우선 선택 (경계 셀 피해서 쥐파먹음 방지)
    """
    from collections import Counter
    new_grid = [row[:] for row in grid]

    # 모든 orbit 후보 열거 (크기 4/2/1)
    # 우선순위 (심미성):
    #   1) 4-orbit (LR+TB 완전 대칭)
    #   2) 180° 회전 2-orbit (좌상↔우하 diagonal pair, 더 디자인적)
    #   3) LR 2-orbit / TB 2-orbit (축 대칭 pair)
    #   4) 1-orbit (중앙 셀, parity 조정용)
    orbits_4 = []
    orbits_2_rot = []  # 180° rotational pair (diagonal)
    orbits_2_lr = []   # LR mirror pair
    orbits_2_tb = []   # TB mirror pair
    orbits_1 = []

    # 4-orbit 열거 (좌상 사분면)
    seen4 = set()
    for y in range((H+1)//2):
        for x in range((W+1)//2):
            sib4 = tuple(sorted({(y, x), (y, W-1-x), (H-1-y, x), (H-1-y, W-1-x)}))
            if sib4 in seen4: continue
            seen4.add(sib4)
            if len(sib4) == 4: orbits_4.append(list(sib4))
            elif len(sib4) == 2:
                (a, b) = sib4
                if a[0] == b[0]: orbits_2_lr.append([a, b])
                else: orbits_2_tb.append([a, b])
            elif len(sib4) == 1:
                orbits_1.append([sib4[0]])

    # 180° 회전 2-orbit: (y, x) ↔ (H-1-y, W-1-x)
    rot_seen = set()
    for y in range(H):
        for x in range(W):
            mate = (H-1-y, W-1-x)
            if (y, x) == mate: continue
            pair = tuple(sorted([(y, x), mate]))
            if pair in rot_seen: continue
            rot_seen.add(pair)
            orbits_2_rot.append(list(pair))

    # 추가 LR pair / TB pair (모든 쌍)
    for y in range(H):
        for x in range(W//2):
            mate = (y, W-1-x)
            if (y, x) == mate: continue
            orbits_2_lr.append([(y, x), mate])
    for y in range(H//2):
        for x in range(W):
            mate = (H-1-y, x)
            if (y, x) == mate: continue
            orbits_2_tb.append([(y, x), mate])

    # 모든 셀 1-orbit (중앙 가까운 것부터)
    all_cells = [(y, x) for y in range(H) for x in range(W)]
    cy, cx = (H-1)/2.0, (W-1)/2.0
    all_cells.sort(key=lambda c: (c[0]-cy)**2 + (c[1]-cx)**2)
    for c in all_cells:
        orbits_1.append([c])

    # ㄱ/ㄴ 코너 L-shape 180° 회전 orbit (예: 6셀 = ㄱ3개 + ㄴ3개)
    # Lv123처럼 특정 색을 6, 10, 14개 단위로 줄일 때 코너에 "디자인 브래킷" 형태로 제거
    orbits_corner_L = []
    for L in [2, 3, 4, 5]:
        if 2*L >= min(W, H): break
        # 우상 ㄱ + 좌하 ㄴ
        tr = set()
        for x in range(L): tr.add((0, W-1-x))
        for y in range(L): tr.add((y, W-1))
        bl = {(H-1-y, W-1-x) for (y, x) in tr}
        orbits_corner_L.append(list(tr | bl))
        # 좌상 ㄴ + 우하 ㄱ (반대 대각)
        tl = set()
        for x in range(L): tl.add((0, x))
        for y in range(L): tl.add((y, 0))
        br = {(H-1-y, W-1-x) for (y, x) in tl}
        orbits_corner_L.append(list(tl | br))

    # 우선순위: 큰 4-orbit > 180°회전 2-orbit > 코너 L-orbit > LR/TB 2-orbit
    # 1-orbit은 pool에서 제외 (1픽셀 이물질 = "쥐파먹음" 방지)
    # fallback 필요 시 orbits_1 따로 시도
    orbits = orbits_4 + orbits_2_rot + orbits_corner_L + orbits_2_lr + orbits_2_tb

    def interior_score(orbit, src_color):
        """블록 내부 깊이: 각 orbit 셀에서 **다른 색 셀 or 그리드 경계**까지 Chebyshev 거리.
        깊을수록 블록의 진짜 중앙 → 높은 점수.
        예: 다이아몬드 한가운데 셀 = depth 4, 엣지 셀 = depth 1.
        orbit 내 최소 depth를 반환 (worst case; 모든 orbit 셀이 깊은 것만 고르려고)."""
        max_r = max(W, H)
        min_depth = max_r
        for y, x in orbit:
            d = 0
            for r in range(1, max_r + 1):
                found_diff = False
                for dy in range(-r, r+1):
                    for dx in range(-r, r+1):
                        if max(abs(dy), abs(dx)) != r: continue
                        ny, nx = y + dy, x + dx
                        if not (0 <= ny < H and 0 <= nx < W):
                            found_diff = True; break
                        if new_grid[ny][nx] != src_color:
                            found_diff = True; break
                    if found_diff: break
                if found_diff:
                    d = r - 1
                    break
            else:
                d = max_r
            if d < min_depth:
                min_depth = d
        return min_depth

    def compute_targets(counts):
        """각 색의 10배수 타겟. bg가 잉여 차이를 흡수 (bg는 10배수 필요 없음).
        sum(targets) ≤ total 이어야 함 (나머지는 bg)."""
        colors = list(counts.keys())
        total = sum(counts.values())
        # 각 색을 가장 가까운 10-배수로
        targets = {c: round(counts[c] / 10) * 10 for c in colors}
        # sum(targets) > total 이면 감소 필요 (bg가 음수 불가)
        for _ in range(400):
            diff = sum(targets.values()) - total
            if diff <= 0: return targets  # bg가 |diff| 만큼 흡수
            # 감소만 허용 (무한 루프 방지)
            best_c = None
            best_cost = None
            for c in colors:
                new_t = targets[c] - 10
                if new_t < 0: continue
                cost = abs(new_t - counts[c]) - abs(targets[c] - counts[c])
                if best_cost is None or cost < best_cost:
                    best_cost = cost; best_c = c
            if best_c is None: return None
            targets[best_c] -= 10
        return None

    full_counts = Counter(c for row in new_grid for c in row)
    counts = {c: n for c, n in full_counts.items() if c != bg_marker}
    if not counts: return new_grid
    if all(n % 10 == 0 for n in counts.values()): return new_grid

    # 임계값: 총합이 10배수 아니고 + 개별 색 excess 미미하면 skip (빈칸 도입 방지)
    total = sum(counts.values())
    max_delta = max((min(n % 10, 10 - (n % 10)) for n in counts.values() if n % 10 != 0), default=0)
    original_bg = full_counts.get(bg_marker, 0)
    if total % 10 != 0 and max_delta < 4 and original_bg == 0:
        return new_grid  # 미미한 불균형 → 원본 유지

    targets = compute_targets(dict(counts))
    if targets is None:
        return new_grid

    # bg를 "무한 deficit" 타겟으로 취급 — surplus가 deficit 없을 때 bg로 흘려보냄
    total_cells = sum(full_counts.values())
    total_fill_target = sum(targets.values())
    bg_target = total_cells - total_fill_target  # bg가 되어야 할 셀 수

    current = dict(counts)
    current_bg = full_counts.get(bg_marker, 0)

    for _ in range(500):
        deltas = {c: targets[c] - current[c] for c in current}
        if all(d == 0 for d in deltas.values()) and current_bg == bg_target: break
        surplus = [c for c, d in deltas.items() if d <= -1]
        deficit_list = [c for c, d in deltas.items() if d >= 1]
        # bg도 deficit으로 추가 가능
        bg_deficit = bg_target - current_bg
        deficit = deficit_list[:]
        if bg_deficit >= 1:
            deficit.append(bg_marker)
        if not surplus or not deficit: break

        # Pre-compute base symmetry scores for delta calculation
        def count_sym_changes(orbit, tgt):
            """Compute symmetry preservation change if orbit → tgt.
            Returns (lr_delta, tb_delta, rot_delta) — positive = more symmetric after swap."""
            # For each cell (y, x) in orbit:
            # - mirror_lr at (y, W-1-x)
            # - mirror_tb at (H-1-y, x)
            # - mirror_rot at (H-1-y, W-1-x)
            # Check: before swap, was cell == mirror? After swap (tgt), will cell == mirror?
            orbit_set = set(orbit)
            lr_d = tb_d = rot_d = 0
            for y, x in orbit:
                # LR mirror
                my, mx = y, W - 1 - x
                if (my, mx) == (y, x): continue  # self-mirror, no change
                mv_now = tgt if (my, mx) in orbit_set else new_grid[my][mx]
                src_v = new_grid[y][x]
                # before: src_v == new_grid[my][mx]; after: tgt == mv_now
                was_match = src_v == new_grid[my][mx]
                now_match = tgt == mv_now
                lr_d += (1 if now_match else 0) - (1 if was_match else 0)
            for y, x in orbit:
                my, mx = H - 1 - y, x
                if (my, mx) == (y, x): continue
                mv_now = tgt if (my, mx) in orbit_set else new_grid[my][mx]
                src_v = new_grid[y][x]
                was_match = src_v == new_grid[my][mx]
                now_match = tgt == mv_now
                tb_d += (1 if now_match else 0) - (1 if was_match else 0)
            for y, x in orbit:
                my, mx = H - 1 - y, W - 1 - x
                if (my, mx) == (y, x): continue
                mv_now = tgt if (my, mx) in orbit_set else new_grid[my][mx]
                src_v = new_grid[y][x]
                was_match = src_v == new_grid[my][mx]
                now_match = tgt == mv_now
                rot_d += (1 if now_match else 0) - (1 if was_match else 0)
            return lr_d, tb_d, rot_d

        def neighbor_stats(orbit, tgt):
            """orbit 셀들의 8-이웃 분석.
            min_tgt_neighbors: orbit 각 셀이 가진 tgt 색 이웃 수 중 **최솟값**
                               (== orbit 중 가장 외로운 셀의 tgt 이웃 수)
            이 값 ≥ 3 이어야 "기존 tgt 영역을 자연스럽게 확장" 으로 간주.
            낮으면 고립된 섬을 만드는 셈 = 쥐파먹음."""
            orbit_set = set(orbit)
            min_match = 99
            total_ratio_sum = 0
            for y, x in orbit:
                matched = 0
                valid = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0: continue
                        ny, nx = y+dy, x+dx
                        if not (0 <= ny < H and 0 <= nx < W): continue
                        if (ny, nx) in orbit_set: continue
                        valid += 1
                        if new_grid[ny][nx] == tgt:
                            matched += 1
                if matched < min_match:
                    min_match = matched
                total_ratio_sum += (matched / valid) if valid else 0
            avg_ratio = total_ratio_sum / len(orbit) if orbit else 0
            return min_match, avg_ratio

        # (src orbit, tgt) 최적 조합 찾기
        # 우선순위 (rat-eaten 방지 강화):
        #   1) 각 orbit 셀이 tgt 이웃을 3개 이상 가지는지 (고립 방지 하드 게이트)
        #   2) 큰 orbit (대칭 보존)
        #   3) 평균 neighbor_match 비율 (부드럽게 확장)
        #   4) swap 후 대칭 점수 유지
        def orbit_key(orbit, src, tgt):
            size = len(orbit)
            lr_d, tb_d, rot_d = count_sym_changes(orbit, tgt)
            best_sym_delta = max(lr_d, tb_d, rot_d)
            min_match, avg_ratio = neighbor_stats(orbit, tgt)
            # min_match < 3 이면 모든 orbit 셀이 외로운 섬 → 강한 패널티
            isolated_penalty = 1 if min_match < 3 else 0
            return (isolated_penalty, -size, -avg_ratio, -best_sym_delta)

        def tgt_capacity(t):
            """target 용량: bg면 무한 가까이, 아니면 delta 체크."""
            if t == bg_marker:
                return bg_target - current_bg
            return deltas.get(t, 0)

        best = None
        # 1단계: 같은 색 orbit (순수 swap)
        for orbit in orbits:
            size = len(orbit)
            src_set = {new_grid[y][x] for y, x in orbit}
            if len(src_set) != 1: continue
            src = next(iter(src_set))
            if src not in surplus: continue
            if deltas[src] > -size: continue
            for tgt in deficit:
                if tgt_capacity(tgt) < size: continue
                key = orbit_key(orbit, src, tgt)
                cand = (key, orbit, src, tgt, None)  # src가 지정됨 = 순수
                if best is None or cand[0] < best[0]:
                    best = cand
        # 2단계: 혼합 색 4-orbit (대칭 보존 최우선, 여러 색 1씩 감소)
        # 1-orbit 같은 대칭 깨는 옵션 쓰기 전에 시도
        if best is None:
            for orbit in orbits:
                size = len(orbit)
                if size < 4: continue  # 4-orbit만 허용
                src_cells = [new_grid[y][x] for y, x in orbit]
                # 각 src 색이 모두 surplus여야 함 + 감소 가능해야 함
                src_count_in_orbit = Counter(src_cells)
                if bg_marker in src_count_in_orbit: continue  # bg 셀 있으면 건너뜀
                all_ok = True
                for sc, cnt in src_count_in_orbit.items():
                    if sc not in deltas or deltas[sc] > -cnt:
                        all_ok = False; break
                if not all_ok: continue
                for tgt in deficit:
                    if tgt_capacity(tgt) < size: continue
                    if tgt in src_count_in_orbit: continue  # 혼합 중 타겟색 있으면 non-swap
                    # key: 크기 큰 것, 평균 interior score 높은 것
                    key = (-size, 0)  # 심미 점수는 일단 단순
                    cand = (key, orbit, None, tgt, src_count_in_orbit)
                    if best is None or cand[0] < best[0]:
                        best = cand
        # 3단계: fallback (순수 2-orbit)
        if best is None:
            for orbit in orbits:
                size = len(orbit)
                src_set = {new_grid[y][x] for y, x in orbit}
                if len(src_set) != 1: continue
                src = next(iter(src_set))
                if src not in surplus: continue
                for tgt in deficit:
                    key = orbit_key(orbit, src, tgt)
                    cand = (key, orbit, src, tgt, None)
                    if best is None or cand[0] < best[0]:
                        best = cand
        # 4단계: 마지막 수단으로 1-orbit (10배수 위해 홀수 parity 보정 필요할 때만)
        if best is None:
            for orbit in orbits_1:
                src_set = {new_grid[y][x] for y, x in orbit}
                if len(src_set) != 1: continue
                src = next(iter(src_set))
                if src not in surplus: continue
                for tgt in deficit:
                    if tgt_capacity(tgt) < 1: continue
                    key = orbit_key(orbit, src, tgt)
                    cand = (key, orbit, src, tgt, None)
                    if best is None or cand[0] < best[0]:
                        best = cand
        if best is None: break

        _, orbit, src_info, tgt, mix_counter = best
        size = len(orbit)
        for y, x in orbit:
            new_grid[y][x] = tgt
        if mix_counter is not None:
            # 혼합 색: 각 src 색에서 개별 감소
            for sc, cnt in mix_counter.items():
                current[sc] -= cnt
        else:
            current[src_info] -= size
        if tgt == bg_marker:
            current_bg += size
        else:
            current[tgt] = current.get(tgt, 0) + size

    return new_grid


def _make_image(grid: list, palette: list, W: int, H: int, block: int, transparent_bg=False):
    """그리드를 PNG image로 렌더. transparent_bg=True면 RGBA 모드, bg('K' or 'T') = alpha 0."""
    mode = "RGBA" if transparent_bg else "RGB"
    img = Image.new(mode, (W*block, H*block), (0,0,0,0) if transparent_bg else (255,255,255))
    px = img.load()
    for gy in range(H):
        for gx in range(W):
            c = grid[gy][gx]
            is_bg = c in ("T", "K")
            col = _hex_to_rgb(palette[c]) if isinstance(c,int) and 0<=c<len(palette) else \
                  (0,0,0,0) if is_bg else \
                  _hex_to_rgb(c) if isinstance(c,str) and c.startswith("#") else (255,255,255)
            if mode == "RGBA":
                col = col + (0 if is_bg else 255,)
            for py in range(block):
                for ppx in range(block):
                    px[gx*block+ppx, gy*block+py] = col
    return img


# ══════════════════════════════════════════════════════════════════════════
# 1. 만화경 (8방향 대칭) — seed로 band 폭 + 색 순열 변주
# ══════════════════════════════════════════════════════════════════════════
def _kaleidoscope(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    style = rng.randrange(4)   # 0=rings, 1=petals, 2=starburst, 3=spiral
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    cx, cy = (W-1)/2.0, (H-1)/2.0

    if style == 0:  # 기존: 동심원 링 + 2섹션
        band = rng.choice([3.0, 3.5, 4.0, 4.5, 5.0])
        def _assign(gx, gy):
            dx, dy = abs(gx-cx), abs(gy-cy)
            if dx < dy: dx, dy = dy, dx
            d = dx + dy
            ring = int(d/band) % max(1, n_colors//2)
            a = math.atan2(dy, dx+1e-9)
            sec = 0 if a < math.pi/8 else 1
            return perm[(ring*2 + sec + rot) % n_colors]
    elif style == 1:  # 꽃잎 (n-fold petals)
        petals = rng.choice([5, 6, 8])
        band = rng.choice([3.0, 4.0, 5.0])
        def _assign(gx, gy):
            dx, dy = gx-cx, gy-cy
            r = math.sqrt(dx*dx + dy*dy)
            a = math.atan2(dy, dx)
            ring = int(r/band)
            petal = int((a + math.pi) / (2*math.pi) * petals)
            return perm[(ring + petal + rot) % n_colors]
    elif style == 2:  # 스타버스트: 방사 빛살
        rays = rng.choice([8, 12, 16])
        band = rng.choice([2.0, 3.0, 4.0])
        def _assign(gx, gy):
            dx, dy = gx-cx, gy-cy
            r = math.sqrt(dx*dx + dy*dy)
            a = math.atan2(dy, dx)
            ray = int((a + math.pi) / (2*math.pi) * rays)
            band_idx = int(r / band)
            # 빛살 중간은 색A, 틈은 색B
            return perm[((ray % 2) * band_idx + rot) % n_colors] \
                   if (ray % 2 == 0) else perm[(band_idx + rot + 1) % n_colors]
    else:  # 스파이럴
        arms = rng.choice([2, 3, 4])
        tightness = rng.choice([0.25, 0.35, 0.5])
        def _assign(gx, gy):
            dx, dy = gx-cx, gy-cy
            r = math.sqrt(dx*dx + dy*dy)
            a = math.atan2(dy, dx)
            # 나선 방정식: angle + tightness*r
            spiral = a * arms / (2*math.pi) + tightness * r
            idx = int(spiral * n_colors) % n_colors
            return perm[(idx + rot) % n_colors]

    return [[_assign(gx, gy) for gx in range(W)] for gy in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 2. 헥사곤 타일 — seed로 radius + 색 순열 변주
# ══════════════════════════════════════════════════════════════════════════
def _hex_tile(W:int, H:int, n_colors:int, radius:float=None,
              outline_color:Optional[int]=None, seed:int=0) -> list:
    rng = random.Random(seed)
    if radius is None: radius = rng.choice([4.5, 5.0, 5.5, 6.0, 6.5])
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    cx0,cy0 = (W-1)/2.0,(H-1)/2.0
    def axial_round(q,r):
        s=-q-r; rq,rr,rs=round(q),round(r),round(s)
        dq,dr,ds=abs(rq-q),abs(rr-r),abs(rs-s)
        if dq>dr and dq>ds: rq=-rr-rs
        elif dr>ds: rr=-rq-rs
        return rq,rr
    def p2h(x,y,R):
        q=(math.sqrt(3)/3*x-1/3*y)/R; r=(2/3*y)/R
        return axial_round(q,r)
    hmap=[[p2h(gx-cx0,gy-cy0,radius) for gx in range(W)] for gy in range(H)]
    OC = outline_color if outline_color is not None else (n_colors % 28)
    FILL_N = n_colors-1 if outline_color is not None else n_colors
    grid=[]
    for gy in range(H):
        row=[]
        for gx in range(W):
            hq,hr=hmap[gy][gx]
            is_out=any(0<=gx+dx<W and 0<=gy+dy<H and hmap[gy+dy][gx+dx]!=(hq,hr)
                       for dy,dx in [(-1,0),(1,0),(0,-1),(0,1)])
            if is_out: row.append(OC)
            else:
                base = ((hq*2+hr*3)%FILL_N+FILL_N)%FILL_N
                row.append(perm[(base+rot) % n_colors] if FILL_N == n_colors
                           else (base + rot) % FILL_N)
        grid.append(row)
    return grid


# ══════════════════════════════════════════════════════════════════════════
# 3. 미로 (DFS 백트래킹, 벽 거리 기반 다색)
# ══════════════════════════════════════════════════════════════════════════
def _maze(W:int, H:int, n_colors:int, seed:int=42) -> list:
    # W,H는 홀수여야 단일 외곽선 보장. 원본 크기 기억해서 끝에 padding.
    orig_W, orig_H = W, H
    if W%2==0: W-=1
    if H%2==0: H-=1
    MW,MH = W//2, H//2
    import sys; sys.setrecursionlimit(10000)
    passages=[[set() for _ in range(MW)] for _ in range(MH)]
    visited=[[False]*MW for _ in range(MH)]
    rng=random.Random(seed)
    # 벽 색 순열
    wall_perm = list(range(max(1, n_colors-1))); rng.shuffle(wall_perm)
    stack=[(0,0)]; visited[0][0]=True
    while stack:
        mx,my=stack[-1]
        dirs=[(1,0,'E','W'),(-1,0,'W','E'),(0,1,'S','N'),(0,-1,'N','S')]
        rng.shuffle(dirs)
        nbrs=[(mx+dx,my+dy,fw,bk) for dx,dy,fw,bk in dirs
              if 0<=mx+dx<MW and 0<=my+dy<MH and not visited[my+dy][mx+dx]]
        if nbrs:
            nx,ny,fw,bk=nbrs[0]
            passages[my][mx].add(fw); passages[ny][nx].add(bk)
            visited[ny][nx]=True; stack.append((nx,ny))
        else: stack.pop()
    grid=[['K']*W for _ in range(H)]
    for my in range(MH):
        for mx in range(MW):
            gx,gy=1+mx*2,1+my*2
            grid[gy][gx]='P'
            if 'E' in passages[my][mx] and mx+1<MW: grid[gy][gx+1]='P'
            if 'S' in passages[my][mx] and my+1<MH: grid[gy+1][gx]='P'
    grid[0][W//2]='P'; grid[H-1][W//2]='P'

    # 스타일 선택 (seed로): 0=radial, 1=quadrant, 2=heart_outline, 3=bands, 4=diamond_outline
    style = rng.randrange(5)
    cx_g, cy_g = (W-1)/2.0, (H-1)/2.0
    wall_n = max(1, n_colors - 1)

    # 최외곽 1~2칸은 강조용 '테두리' (마지막 색으로 칠함)
    border_thick = 1 if min(W, H) < 24 else 2
    def is_border(gx, gy):
        return gx < border_thick or gx >= W - border_thick \
            or gy < border_thick or gy >= H - border_thick

    def wall_color(gx, gy):
        """각 스타일별 벽 색 인덱스 계산."""
        # 모든 스타일 공통: 최외곽 테두리는 벽 색 중 마지막(진한) 색
        if is_border(gx, gy) and style != 0:
            return wall_n - 1

        if style == 0:  # 동심원 반지름
            d = math.sqrt((gx-cx_g)**2 + (gy-cy_g)**2) / math.sqrt(cx_g**2+cy_g**2)
            return int(d * (wall_n - 0.01)) % wall_n
        if style == 1:  # 4분면 + 중앙 원
            # 중앙 원 반지름
            r_center = min(W, H) * 0.2
            d_c = math.sqrt((gx-cx_g)**2 + (gy-cy_g)**2)
            if d_c < r_center:
                return wall_n - 2 if wall_n >= 3 else 0   # 중앙 강조색
            q = (0 if gx < cx_g else 1) + (0 if gy < cy_g else 2)
            return q % max(1, wall_n - 1)   # 테두리용 마지막 색 남김
        if style == 2:  # 하트 윤곽 (하트 안/밖)
            X = (gx - cx_g) / (W * 0.35)
            Y = (gy - cy_g - H*0.12) / (H * 0.35)
            inside_heart = (X*X + Y*Y - 1)**3 - X*X * ((-Y)**3) <= 0
            d = math.sqrt((gx-cx_g)**2 + (gy-cy_g)**2)
            ring = int(d / 3) % wall_n
            return ring if inside_heart else (wall_n - 1)
        if style == 3:  # 4분면 색 + 중앙 원 (변종: 테두리 없이 깔끔)
            r_center = min(W, H) * 0.22
            d_c = math.sqrt((gx-cx_g)**2 + (gy-cy_g)**2)
            if d_c < r_center:
                return wall_n - 1
            q = (0 if gx < cx_g else 1) + (0 if gy < cy_g else 2)
            return q % max(1, wall_n)
        # style 4: 마름모(체비셰프 링)
        dmax = max(abs(gx - cx_g), abs(gy - cy_g))
        scale = max(cx_g, cy_g)
        return int((dmax / scale) * (wall_n - 0.01)) % wall_n

    for gy in range(H):
        for gx in range(W):
            if grid[gy][gx] == 'K':
                grid[gy][gx] = wall_perm[wall_color(gx, gy) % wall_n]
    # 통로를 마지막 색으로
    for gy in range(H):
        for gx in range(W):
            if grid[gy][gx] == 'P':
                grid[gy][gx] = n_colors - 1
    # 원본 크기로 padding (끝 행/열에 'K' 추가)
    while len(grid) < orig_H:
        grid.append(['K'] * W)
    if W < orig_W:
        for row in grid:
            row.extend(['K'] * (orig_W - W))
    return grid


# ══════════════════════════════════════════════════════════════════════════
# 4. 벽돌 패턴 — seed로 brick 크기와 색 순열 변주
# ══════════════════════════════════════════════════════════════════════════
def _brick(W:int, H:int, n_colors:int,
           brick_w:int=None, brick_h:int=None, seed:int=0) -> list:
    rng = random.Random(seed)
    if brick_w is None:
        pool = [4,5,6] if W < 28 else ([5,6,7,8] if W < 36 else [7,8,9,10])
        brick_w = rng.choice(pool)
    if brick_h is None:
        pool = [3,4] if H < 28 else ([4,5] if H < 36 else [5,6])
        brick_h = rng.choice(pool)
    # 줄눈 색 인덱스는 n_colors 사용(팔레트 n_colors번째는 기본 팔레트에서 래핑됨)
    # 벽돌 본체 색만 섞음
    body_n = max(1, n_colors)
    perm = list(range(body_n)); rng.shuffle(perm)
    rot  = rng.randrange(body_n)
    def classify(gx,gy):
        ly=gy%brick_h
        if ly==brick_h-1: return n_colors  # 줄눈
        row=gy//brick_h; off=(brick_w//2) if row%2==1 else 0
        lx=(gx+off)%brick_w
        if lx==brick_w-1: return n_colors
        col=(gx+off)//brick_w
        return perm[(col+row+rot) % body_n]
    grid=[[classify(gx,gy) for gx in range(W)] for gy in range(H)]
    return grid


# ══════════════════════════════════════════════════════════════════════════
# 5. I형 테트로미노 반복 — seed로 타일 크기 + 색 순열 변주
# ══════════════════════════════════════════════════════════════════════════
def _i_tetromino(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    m = min(W, H)
    pool = [6, 8] if m < 28 else ([8, 10] if m < 36 else [10, 12])
    T = rng.choice(pool)               # 타일 크기 (짝수)
    Q = T // 4                          # 블록 경계
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    def get_color(gx,gy):
        tx=gx//T; ty=gy//T
        lx=gx%T; ly=gy%T
        parity=(tx+ty)%2; off=(tx*2+ty)%3
        if ly < 2*Q:  role = 0 if lx < 2*Q else 1
        elif ly < 3*Q:
            if   lx < Q:    role = 2
            elif lx >= 3*Q: role = 3
            else:            role = 4
        else:         role = 5 if lx < 2*Q else 0
        return perm[(role+off*2+parity*3+rot) % n_colors]
    return [[get_color(gx,gy) for gx in range(W)] for gy in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 6. 정사각형+직사각형 분할 (상하좌우 대칭)
#    seed로 타일 크기와 색 회전·순열을 변주 (같은 W/H/n이어도 다른 결과)
# ══════════════════════════════════════════════════════════════════════════
def _rect_grid(W:int, H:int, n_colors:int,
               tile_w:int=None, tile_h:int=None, seed:int=0) -> list:
    rng = random.Random(seed)
    if tile_w is None:
        pool = [4,5,6,7] if W < 28 else ([6,7,8,9] if W < 36 else [8,9,10,11])
        tile_w = rng.choice(pool)
    if tile_h is None:
        pool = [5,6,7,8] if H < 30 else ([7,8,9,10] if H < 40 else [9,10,11,12])
        tile_h = rng.choice(pool)
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    # 이미 mirror 보장: tx_s, ty_s가 중심 거리 기반 (concentric-plaid)
    def get_zone(lx,ly):
        if (ly<=1 or ly>=tile_h-2) and lx!=tile_w//2: return 0
        if (ly<=1 or ly>=tile_h-2) and lx==tile_w//2: return 1
        if 2<=ly<=tile_h-3 and lx!=tile_w//2: return 2
        return 3
    def get_color(gx,gy):
        lx=gx%tile_w; ly=gy%tile_h
        tx=gx//tile_w; ty=gy//tile_h
        tx_s=min(tx, (W//tile_w)-1-tx) if W//tile_w>1 else 0
        ty_s=min(ty, (H//tile_h)-1-ty) if H//tile_h>1 else 0
        z=get_zone(lx,ly)
        return perm[(z+tx_s+ty_s*2+rot)%n_colors]
    return [[get_color(gx,gy) for gx in range(W)] for gy in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 7. 다이아몬드 체커보드
# ══════════════════════════════════════════════════════════════════════════
def _diamond_check(W:int, H:int, n_colors:int, size:int=None, seed:int=0) -> list:
    rng = random.Random(seed)
    if size is None:
        m = min(W, H)
        pool = [5,6,7,8] if m < 24 else ([7,8,9,10] if m < 32 else [9,10,11,12,13])
        size = rng.choice(pool)
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    def get_color(gx,gy):
        u=(gx+gy)//size; v=(gx-gy)//size
        return perm[(u+v+rot)%n_colors]
    return [[get_color(gx,gy) for gx in range(W)] for gy in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 8. 스트라이프 (direction 미지정 시 seed로 방향 선택)
# ══════════════════════════════════════════════════════════════════════════
def _balance_color_swap_only(grid, W: int, H: int, n_colors: int,
                                targets: list, bg_marker='K') -> list:
    """색 cells을 swap해서 색별 카운트를 targets에 맞춤. bg 위치는 고정.
    180° pair / 4-orbit 단위 swap으로 대칭 보존.
    sum(현재 색 cells) == sum(targets)이어야 가능."""
    from collections import Counter
    new_grid = [row[:] for row in grid]
    cnt = Counter(c for row in new_grid for c in row if isinstance(c, int))
    excess = {c: cnt.get(c, 0) - targets[c] for c in range(n_colors)}

    if all(e == 0 for e in excess.values()):
        return new_grid

    seen_pairs = set()
    orbits = []  # (size, [(x, y), ...], color)

    # 4-orbit 우선 (LR+TB 대칭)
    for y in range((H + 1) // 2):
        for x in range((W + 1) // 2):
            sib4 = tuple(sorted({(x, y), (W - 1 - x, y),
                                  (x, H - 1 - y), (W - 1 - x, H - 1 - y)}))
            if sib4 in seen_pairs: continue
            seen_pairs.add(sib4)
            if not all(new_grid[py][px] != bg_marker for (px, py) in sib4):
                continue
            colors = set(new_grid[py][px] for (px, py) in sib4)
            if len(colors) == 1:
                c = next(iter(colors))
                if isinstance(c, int):
                    orbits.append((len(sib4), list(sib4), c))

    # 180° rotation pair (자기-pair 제외)
    for y in range(H):
        for x in range(W):
            mate = (W - 1 - x, H - 1 - y)
            if (x, y) == mate: continue
            pair = tuple(sorted([(x, y), mate]))
            if pair in seen_pairs: continue
            seen_pairs.add(pair)
            if not all(new_grid[py][px] != bg_marker for (px, py) in pair):
                continue
            colors = set(new_grid[py][px] for (px, py) in pair)
            if len(colors) == 1:
                c = next(iter(colors))
                if isinstance(c, int):
                    orbits.append((2, list(pair), c))

    # 1-orbit (중앙 single cell, 홀수 grid)
    if W % 2 == 1 and H % 2 == 1:
        cx, cy = W // 2, H // 2
        c = new_grid[cy][cx]
        if c != bg_marker and isinstance(c, int):
            orbits.append((1, [(cx, cy)], c))

    # excess > 0 색 orbit을 deficit 색으로 swap
    # 큰 orbit 우선 (한 번에 많이 보정)
    orbits.sort(key=lambda o: -o[0])
    for size, cells, c in orbits:
        if all(e == 0 for e in excess.values()):
            break
        if excess.get(c, 0) < size:
            continue
        # deficit 색 찾기 (size 만큼 받을 수 있는)
        for d in range(n_colors):
            if d == c: continue
            if excess.get(d, 0) + size <= 0:
                for (px, py) in cells:
                    new_grid[py][px] = d
                excess[c] -= size
                excess[d] += size
                break
    return new_grid


def _fill_motif_natural(motif_fn, W: int, H: int, n_colors: int,
                            bg_layout: set, targets: list, seed: int = 0,
                            seed_offsets=(0, 1000, 2000, 3000, 7919, 13127)) -> list:
    """자연 motif/lattice 패턴 생성 후 bg_layout 위치를 'K' overlay.
    여러 seed offset 시도 → 색별 카운트가 targets와 일치하면 해당 grid 반환.
    어떤 seed도 매치 안 되면 None."""
    from collections import Counter
    bg_set = set(bg_layout)
    for sd_off in seed_offsets:
        try:
            grid_color = motif_fn(W, H, n_colors, seed=seed + sd_off)
        except TypeError:
            try:
                grid_color = motif_fn(W, H, n_colors, seed + sd_off)
            except Exception:
                continue
        except Exception:
            continue
        grid = [list(row) for row in grid_color]
        for x, y in bg_set:
            if 0 <= y < H and 0 <= x < W:
                grid[y][x] = 'K'
        cnt = Counter(c for row in grid for c in row if isinstance(c, int))
        if all(cnt.get(c, 0) == targets[c] for c in range(n_colors)):
            return grid
    return None


def _fill_chevron(W: int, H: int, n_colors: int,
                    bg_layout: set, targets: list,
                    band: int = 5, seed: int = 0) -> list:
    """bg_layout cells을 'K'로 두고 V자 chevron 색 채움.
    color = ((y + |x-cx|) // band + rot) % n. band/rot은 best target match 자동."""
    grid = [['K' for _ in range(W)] for _ in range(H)]
    bg_set = set(bg_layout)
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)
    cx = W // 2

    def color_at(x, y, b, rot):
        return perm[(((y + abs(x - cx)) // b) + rot) % n_colors]

    best_b, best_rot, best_diff = band, 0, None
    candidate_bands = list(range(max(2, band) + 2, 1, -1)) + [2, 1]
    for b in candidate_bands:
        if b < 1: continue
        for rot in range(n_colors):
            cnt = {c: 0 for c in range(n_colors)}
            for y in range(H):
                for x in range(W):
                    if (x, y) in bg_set: continue
                    cnt[color_at(x, y, b, rot)] += 1
            diff = sum(abs(cnt[c] - targets[c]) for c in range(n_colors))
            if best_diff is None or diff < best_diff:
                best_diff = diff; best_b = b; best_rot = rot
        if best_diff == 0: break

    for y in range(H):
        for x in range(W):
            if (x, y) in bg_set:
                grid[y][x] = 'K'
            else:
                grid[y][x] = color_at(x, y, best_b, best_rot)
    return grid


def _fill_brick(W: int, H: int, n_colors: int,
                  bg_layout: set, targets: list,
                  brick_w: int, brick_h: int, seed: int = 0) -> list:
    """bg_layout cells을 'K'로 두고, 나머지 brick 패턴 채움.
    row-shifted: 홀수 row는 brick_w//2 offset. 색 cycle (row + col + rot) % n."""
    grid = [['K' for _ in range(W)] for _ in range(H)]
    bg_set = set(bg_layout)
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    def color_at(x, y, rot):
        row_idx = y // brick_h
        off = brick_w // 2 if row_idx % 2 == 1 else 0
        col_idx = (x + off) // brick_w
        return perm[(row_idx + col_idx + rot) % n_colors]

    best_rot = 0
    best_diff = None
    for rot in range(n_colors):
        cnt = {c: 0 for c in range(n_colors)}
        for y in range(H):
            for x in range(W):
                if (x, y) in bg_set: continue
                cnt[color_at(x, y, rot)] += 1
        diff = sum(abs(cnt[c] - targets[c]) for c in range(n_colors))
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_rot = rot

    for y in range(H):
        for x in range(W):
            if (x, y) in bg_set:
                grid[y][x] = 'K'
            else:
                grid[y][x] = color_at(x, y, best_rot)
    return grid


def _fill_diamond_check(W: int, H: int, n_colors: int,
                          bg_layout: set, targets: list,
                          size: int = 5, seed: int = 0) -> list:
    """bg_layout cells을 'K'로 두고 다이아몬드 체커 색 채움.
    n≤4: Manhattan distance ring concentric. n>4: tilted checker."""
    grid = [['K' for _ in range(W)] for _ in range(H)]
    bg_set = set(bg_layout)
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    use_concentric = n_colors <= 4

    def color_at(x, y, s, rot):
        if use_concentric:
            return perm[(int((abs(x - cx) + abs(y - cy)) // s) + rot) % n_colors]
        return perm[(((x + y) // s) + ((x - y) // s) + rot) % n_colors]

    best_s, best_rot, best_diff = size, 0, None
    candidate_sizes = list(range(max(2, size), 1, -1)) + [2, 1]
    for s in candidate_sizes:
        for rot in range(n_colors):
            cnt = {c: 0 for c in range(n_colors)}
            for y in range(H):
                for x in range(W):
                    if (x, y) in bg_set: continue
                    cnt[color_at(x, y, s, rot)] += 1
            diff = sum(abs(cnt[c] - targets[c]) for c in range(n_colors))
            if best_diff is None or diff < best_diff:
                best_diff = diff; best_s = s; best_rot = rot
        if best_diff == 0: break

    for y in range(H):
        for x in range(W):
            if (x, y) in bg_set:
                grid[y][x] = 'K'
            else:
                grid[y][x] = color_at(x, y, best_s, best_rot)
    return grid


def _fill_rect_grid(W: int, H: int, n_colors: int,
                       bg_layout: set, targets: list,
                       tile_w: int, tile_h: int, seed: int = 0) -> list:
    """bg_layout cells을 'K'로 두고, 나머지 영역에 tile_w × tile_h 격자 패턴.
    color = ((x // tile_w) + (y // tile_h) + rot) % n cycle. rot은 best target match 자동 선택."""
    grid = [['K' for _ in range(W)] for _ in range(H)]
    bg_set = set(bg_layout)
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    best_rot = 0
    best_diff = None
    for rot in range(n_colors):
        cnt = {c: 0 for c in range(n_colors)}
        for y in range(H):
            for x in range(W):
                if (x, y) in bg_set: continue
                c = perm[(((x // tile_w) + (y // tile_h)) + rot) % n_colors]
                cnt[c] += 1
        diff = sum(abs(cnt[c] - targets[c]) for c in range(n_colors))
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_rot = rot

    for y in range(H):
        for x in range(W):
            if (x, y) in bg_set:
                grid[y][x] = 'K'
            else:
                c = perm[(((x // tile_w) + (y // tile_h)) + best_rot) % n_colors]
                grid[y][x] = c
    return grid


def _fill_concentric_sq(W: int, H: int, n_colors: int,
                           bg_layout: set, targets: list, seed: int = 0) -> list:
    """bg_layout cells을 'K'로 두고, 나머지 cells에 concentric square ring 색.
    ring_idx (Chebyshev d) cycle %n. rot은 best target match 자동 선택."""
    grid = [['K' for _ in range(W)] for _ in range(H)]
    bg_set = set(bg_layout)
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    best_rot = 0
    best_diff = None
    for rot in range(n_colors):
        cnt = {c: 0 for c in range(n_colors)}
        for y in range(H):
            for x in range(W):
                if (x, y) in bg_set: continue
                d = int(max(abs(x - cx), abs(y - cy)))
                c = perm[(d + rot) % n_colors]
                cnt[c] += 1
        diff = sum(abs(cnt[c] - targets[c]) for c in range(n_colors))
        if best_diff is None or diff < best_diff:
            best_diff = diff
            best_rot = rot

    for y in range(H):
        for x in range(W):
            if (x, y) in bg_set:
                grid[y][x] = 'K'
            else:
                d = int(max(abs(x - cx), abs(y - cy)))
                c = perm[(d + best_rot) % n_colors]
                grid[y][x] = c
    return grid


def _fill_checkerboard(W: int, H: int, n_colors: int,
                          bg_layout: set, targets: list,
                          tile_size: int, seed: int = 0) -> list:
    """bg_layout cells을 'K'로 두고, 나머지 영역에 tile_size 큰 체커 패턴.
    각 색 셀 수 = targets[c]. tile은 (x // tile_size + y // tile_size + rot) % n cycle."""
    grid = [['K' for _ in range(W)] for _ in range(H)]
    bg_set = set(bg_layout)
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    # 각 색별 cell 수 카운트하면서 채움
    color_count = {c: 0 for c in range(n_colors)}
    # rot 후보 시도 (best matching targets)
    best_rot = None
    best_total_diff = None
    for rot in range(n_colors):
        cnt = {c: 0 for c in range(n_colors)}
        for y in range(H):
            for x in range(W):
                if (x, y) in bg_set:
                    continue
                c = perm[(((x // tile_size) + (y // tile_size)) + rot) % n_colors]
                cnt[c] += 1
        diff = sum(abs(cnt[c] - targets[c]) for c in range(n_colors))
        if best_total_diff is None or diff < best_total_diff:
            best_total_diff = diff
            best_rot = rot
    rot = best_rot if best_rot is not None else 0

    for y in range(H):
        for x in range(W):
            if (x, y) in bg_set:
                grid[y][x] = 'K'
            else:
                c = perm[(((x // tile_size) + (y // tile_size)) + rot) % n_colors]
                grid[y][x] = c

    # 색별 카운트 검증 — targets와 차이 있으면 약간 swap (small adjustment)
    from collections import Counter
    cnt = Counter(c for row in grid for c in row if isinstance(c, int))
    if all(cnt.get(c, 0) == targets[c] for c in range(n_colors)):
        return grid
    # mismatch — return grid anyway, BFS removal/balance가 후처리 (caller 책임)
    return grid


def _fill_stripe(W: int, H: int, n_colors: int,
                  bg_layout: set, targets: list, seed: int = 0) -> list:
    """bg_layout (cells set)을 'K'로 두고, 나머지 cells에 stripe 색 채움.
    bg_layout이 column-major면 vertical stripe, row-major면 horizontal stripe.
    각 색 정확히 targets[c] cells (10x 보장 for 외부 plan_counts).
    실패 시 None 반환."""
    grid = [['K' for _ in range(W)] for _ in range(H)]
    for x, y in bg_layout:
        grid[y][x] = 'K'

    # bg layout 분석
    bg_cols = set()
    for x in range(W):
        if all((x, y) in bg_layout for y in range(H)):
            bg_cols.add(x)
    bg_rows = set()
    for y in range(H):
        if all((x, y) in bg_layout for x in range(W)):
            bg_rows.add(y)

    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    # column-major bg → vertical stripe (stripe-단위 색 그룹화)
    if bg_cols and len(bg_cols) * H == len(bg_layout):
        # color stripe groups (연속된 non-bg cols)
        color_groups = []
        cur = []
        for x in range(W):
            if x in bg_cols:
                if cur: color_groups.append(cur); cur = []
            else:
                cur.append(x)
        if cur: color_groups.append(cur)
        # n_colors개 group + 각 group cells × H == target 매칭
        if len(color_groups) == n_colors:
            # group 면적별로 target에 매칭 (target 정렬 순서 사용)
            sorted_groups = sorted(range(n_colors), key=lambda i: -len(color_groups[i]))
            sorted_targets = sorted(range(n_colors), key=lambda i: -targets[i])
            ok = all(len(color_groups[sorted_groups[i]]) * H == targets[sorted_targets[i]]
                     for i in range(n_colors))
            if ok:
                for gi, ti in zip(sorted_groups, sorted_targets):
                    c = perm[ti]
                    for x in color_groups[gi]:
                        for y in range(H):
                            grid[y][x] = c
                return grid
        return None  # 그룹 mismatch → reject

    # row-major bg → horizontal stripe (stripe-단위 색 그룹화)
    if bg_rows and len(bg_rows) * W == len(bg_layout):
        color_groups = []
        cur = []
        for y in range(H):
            if y in bg_rows:
                if cur: color_groups.append(cur); cur = []
            else:
                cur.append(y)
        if cur: color_groups.append(cur)
        if len(color_groups) == n_colors:
            sorted_groups = sorted(range(n_colors), key=lambda i: -len(color_groups[i]))
            sorted_targets = sorted(range(n_colors), key=lambda i: -targets[i])
            ok = all(len(color_groups[sorted_groups[i]]) * W == targets[sorted_targets[i]]
                     for i in range(n_colors))
            if ok:
                for gi, ti in zip(sorted_groups, sorted_targets):
                    c = perm[ti]
                    for y in color_groups[gi]:
                        for x in range(W):
                            grid[y][x] = c
                return grid
        return None

    # bg가 square cluster: 가능하면 vertical stripe 위주로 채움
    # 색 cells을 col-major로 grouping 후 stripe-like 분배
    bg_set = set(bg_layout)
    color_positions = [(x, y) for y in range(H) for x in range(W)
                       if (x, y) not in bg_set]
    if len(color_positions) != sum(targets):
        return None
    # 각 col에 색 채우되 bg cell은 건너뜀
    # 단순화: x순 → y순으로 색 분배 (각 색은 연속 column-y cells)
    cursor = 0
    color_quota = list(targets)  # 색별 남은 quota
    perm_idx = 0
    for x in range(W):
        for y in range(H):
            if (x, y) in bg_set:
                continue
            # 현재 perm 색 quota 남으면 그 색 사용
            while color_quota[perm[perm_idx]] == 0 and perm_idx < n_colors - 1:
                perm_idx += 1
            c = perm[perm_idx]
            if color_quota[c] == 0:
                return None
            grid[y][x] = c
            color_quota[c] -= 1
    return grid


def _stripe_to_targets(W: int, H: int, n_colors: int,
                        stripe_width: int, bg_cols_total: int,
                        seed: int = 0) -> list:
    """plan_counts에서 나온 stripe_width 사용. 세로 스트라이프 배치:
    [color0][bg gap][color1][bg gap]...[colorN-1] — bg는 stripe 사이에만, 외곽은 항상 색.
    결과: 각 색 count = stripe_width × H (정확히 10-mult 보장).
    n_colors=1이면 bg를 색 양 옆이 아닌 가능한 안쪽으로 (외곽은 색 1열 보장)."""
    import random
    rng = random.Random(seed)
    grid = [['K']*W for _ in range(H)]
    perm = list(range(n_colors))
    rng.shuffle(perm)

    if n_colors >= 2:
        # bg를 stripe 사이 (n_colors-1) gap에 균등 분산. 외곽은 색.
        n_gaps = n_colors - 1
        base = bg_cols_total // n_gaps
        extra = bg_cols_total % n_gaps
        gaps = [base + (1 if i < extra else 0) for i in range(n_gaps)]
        cursor = 0
        for i, c in enumerate(perm):
            for dx in range(stripe_width):
                x = cursor + dx
                if 0 <= x < W:
                    for y in range(H):
                        grid[y][x] = c
            cursor += stripe_width
            if i < n_gaps:
                cursor += gaps[i]
    else:
        # n_colors == 1: 외곽 색 1열씩 보장, 나머지 색 + bg 안쪽
        c = perm[0]
        if W >= 2 and stripe_width >= 2:
            # 첫 col, 마지막 col은 색 (외곽 보장)
            for y in range(H): grid[y][0] = c
            for y in range(H): grid[y][W-1] = c
            inner_color_cols = stripe_width - 2
            inner_w = W - 2
            inner_bg = inner_w - inner_color_cols
            # 가운데 색, 양 옆 bg
            color_start = 1 + inner_bg // 2
            for dx in range(inner_color_cols):
                x = color_start + dx
                if 1 <= x <= W - 2:
                    for y in range(H): grid[y][x] = c
        else:
            for x in range(min(stripe_width, W)):
                for y in range(H): grid[y][x] = c
    return grid


def _stripe(W:int, H:int, n_colors:int,
            stripe_width:int=None, direction:str=None, seed:int=0) -> list:
    rng = random.Random(seed)
    if stripe_width is None:
        m = min(W, H)
        pool = [3,4,5] if m < 24 else ([4,5,6,7] if m < 32 else [5,6,7,8,9])
        stripe_width = rng.choice(pool)
    if direction is None:
        direction = rng.choice(["diagonal", "vertical", "horizontal", "anti_diagonal"])
    width = stripe_width
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    def get_color(gx,gy):
        if direction=="diagonal":       idx = (gx+gy)//width
        elif direction=="anti_diagonal":idx = (gx-gy+H)//width  # +H로 음수 방지
        elif direction=="vertical":     idx = gx//width
        else:                            idx = gy//width  # horizontal
        return perm[(idx+rot)%n_colors]
    return [[get_color(gx,gy) for gx in range(W)] for gy in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 9. XOR 프랙탈  color = ((|x-cx|) XOR (|y-cy|) // scale + rot) % n
#    중심 기준 좌표 XOR → 자연발생 시에르핀스키 삼각형 + LR/TB/대각 대칭
# ══════════════════════════════════════════════════════════════════════════
def _xor_fractal(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    scale = rng.choice([1, 2, 3, 4])
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    cx, cy = W // 2, H // 2
    def get_color(x, y):
        dx = abs(x - cx)
        dy = abs(y - cy)
        v = (dx ^ dy) // scale
        return perm[(v + rot) % n_colors]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 10. 시에르핀스키 카펫 (3^k 재귀 분할, 정확히 8/9 채움)
#     p4m 대칭군 완벽 일치
# ══════════════════════════════════════════════════════════════════════════
def _sierpinski_carpet(W:int, H:int, n_colors:int, seed:int=0) -> list:
    """
    9×9 시에르핀스키 카펫을 **타일처럼 반복**. 깔끔한 자기유사 모티프 반복.
    - 필드: 한 색 / 중앙 큰 구멍: 다른 색 / 작은 8구멍: 또 다른 색
    - 최대 3색만 활용 (노이즈 없음)
    """
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    S = 9  # 3^2 고정 — 시각적 명료성 우선
    def carpet_level(lx, ly):
        if (lx // 3) % 3 == 1 and (ly // 3) % 3 == 1: return 0  # 큰 중앙 구멍
        if lx % 3 == 1 and ly % 3 == 1:               return 1  # 작은 구멍
        return 2                                                # 채움
    def get_color(x, y):
        lvl = carpet_level(x % S, y % S)
        return perm[(lvl + rot) % n_colors]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 16. X 모티프 (각 타일에 X자 반복, 4-fold 대칭)
# ══════════════════════════════════════════════════════════════════════════
def _best_tile(rng, W, H, pool):
    """W, H를 가장 덜 남기는 타일 크기를 seed로 pick (top-2 중 랜덤)."""
    scored = sorted(pool, key=lambda t: (W % t) + (H % t))
    return rng.choice(scored[:2])


def _x_motif(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    tile = _best_tile(rng, W, H, [5, 7, 9])
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    thickness = 1 if tile == 5 else 2
    ox = (W % tile) // 2
    oy = (H % tile) // 2
    def get_color(x, y):
        lx = (x - ox) % tile
        ly = (y - oy) % tile
        tx = (x - ox) // tile
        ty = (y - oy) // tile
        on_main = abs(lx - ly) < thickness
        on_anti = abs(lx + ly - (tile - 1)) < thickness
        if on_main or on_anti:
            return perm[(tx + ty + rot) % n_colors]
        return perm[((tx + ty + rot + n_colors // 2) % n_colors)]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 17. T 모티프 (각 타일에 T자; LR 대칭)
# ══════════════════════════════════════════════════════════════════════════
def _t_motif(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    tile = _best_tile(rng, W, H, [5, 6, 7, 8])
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    # 방향: 0=T(위에 바), 1=⊥(아래에 바), 2=⊢(왼쪽에 바), 3=⊣(오른쪽에 바)
    orient = rng.randrange(4)
    # 교차 방향 (tx+ty 짝수/홀수로 뒤집기) → 체커보드식 방향 번갈아
    alternating = rng.choice([False, True])
    bar_h  = max(1, tile // 3)
    stem_w = max(1, tile // 3)
    mid = tile // 2
    ox = (W % tile) // 2
    oy = (H % tile) // 2
    def shape_hit(lx, ly, o):
        if o == 0:
            return ly < bar_h or abs(lx - mid) < stem_w - (1 if stem_w > 1 else 0)
        if o == 1:
            return ly >= tile - bar_h or abs(lx - mid) < stem_w - (1 if stem_w > 1 else 0)
        if o == 2:
            return lx < bar_h or abs(ly - mid) < stem_w - (1 if stem_w > 1 else 0)
        return lx >= tile - bar_h or abs(ly - mid) < stem_w - (1 if stem_w > 1 else 0)
    def get_color(x, y):
        lx = (x - ox) % tile
        ly = (y - oy) % tile
        tx = (x - ox) // tile
        ty = (y - oy) // tile
        o = orient
        if alternating and (tx + ty) % 2 == 1:
            o = (orient + 2) % 4
        if shape_hit(lx, ly, o):
            return perm[(tx + ty + rot) % n_colors]
        return perm[((tx + ty + rot + 1) % n_colors)]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 18. + 모티프 (각 타일에 +자; 4-fold 대칭)
# ══════════════════════════════════════════════════════════════════════════
def _plus_motif(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    tile = _best_tile(rng, W, H, [5, 7, 9])
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    arm_w = 1 if tile == 5 else 2
    mid = tile // 2
    ox = (W % tile) // 2
    oy = (H % tile) // 2
    def get_color(x, y):
        lx = (x - ox) % tile
        ly = (y - oy) % tile
        tx = (x - ox) // tile
        ty = (y - oy) // tile
        is_h_arm = abs(ly - mid) < arm_w
        is_v_arm = abs(lx - mid) < arm_w
        if is_h_arm or is_v_arm:
            return perm[(tx + ty + rot) % n_colors]
        return perm[((tx + ty + rot + 1) % n_colors)]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 11. Truchet tiles (쿼터 원호, 사분면 미러 대칭)
#     arc 네트워크로 유기적 곡선 패턴
# ══════════════════════════════════════════════════════════════════════════
def _truchet(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    T = rng.choice([4, 5, 6, 7])
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))

    nx = (W + T - 1) // T
    ny = (H + T - 1) // T
    qx = (nx + 1) // 2
    qy = (ny + 1) // 2
    # 사분면 타일 방향 (0=NW-SE arcs, 1=NE-SW arcs)
    quad = [[rng.randrange(2) for _ in range(max(1, qx))] for _ in range(max(1, qy))]

    def tile_orient(tx, ty):
        # 좌상 사분면으로 접기
        ix = tx if tx < qx else nx - 1 - tx
        iy = ty if ty < qy else ny - 1 - ty
        ix = max(0, min(ix, qx - 1))
        iy = max(0, min(iy, qy - 1))
        base = quad[iy][ix]
        # 반전된 사분면은 방향도 뒤집어서 arc 연속성 유지
        if (tx >= qx) ^ (ty >= qy):
            base = 1 - base
        return base

    half_sq = ((T - 1) / 2.0) ** 2
    def get_color(x, y):
        tx = x // T; ty = y // T
        lx = x % T;  ly = y % T
        ori = tile_orient(tx, ty)
        if ori == 0:
            # arc 중심: (0,0), (T-1, T-1)
            d1 = lx * lx + ly * ly
            d2 = (T - 1 - lx) ** 2 + (T - 1 - ly) ** 2
        else:
            # arc 중심: (T-1, 0), (0, T-1)
            d1 = (T - 1 - lx) ** 2 + ly * ly
            d2 = lx * lx + (T - 1 - ly) ** 2
        inside = (d1 < half_sq) or (d2 < half_sq)
        idx = (tx + ty + (0 if inside else 1))
        return perm[(idx + rot) % n_colors]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 12. Chevron (V 띠 반복, 가운데가 꼭짓점) — LR 대칭 보장
# ══════════════════════════════════════════════════════════════════════════
def _chevron(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    m = min(W, H)
    pool = [3,4,5] if m < 24 else ([4,5,6] if m < 32 else [5,6,7,8])
    band = rng.choice(pool)
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    cx = W // 2
    def get_color(x, y):
        dx = abs(x - cx)
        idx = (y + dx) // band
        return perm[(idx + rot) % n_colors]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 13. Argyle (다이아몬드 + 대각선 X 라인 오버레이)
# ══════════════════════════════════════════════════════════════════════════
def _argyle(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    m = min(W, H)
    pool = [5,6,7] if m < 24 else ([7,8,9] if m < 32 else [9,10,11])
    size = rng.choice(pool)
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    line_color = (n_colors - 1) if n_colors >= 3 else 0
    def get_color(x, y):
        u = (x+y)//size; v = (x-y)//size
        # 얇은 X 라인
        if ((x+y) % size) in (0,) or ((x-y) % size) in (0,):
            return perm[line_color]
        base = (u + v) % n_colors
        return perm[(base + rot) % n_colors]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 14. Wave (사인 기반 세로 물결 띠)
# ══════════════════════════════════════════════════════════════════════════
def _wave(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    amplitude = rng.choice([2, 3, 4])
    period    = rng.choice([W//3, W//4, W//5]) or 4
    band      = rng.choice([3, 4, 5])
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    def get_color(x, y):
        offset = int(amplitude * math.sin(2 * math.pi * x / period))
        idx = (y + offset) // band
        return perm[(idx + rot) % n_colors]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 15a. Checkerboard (정통 체스보드 — 정사각 2색+ 격자)
#      완벽한 LR/TB/180° 대칭 + 2·size 주기
# ══════════════════════════════════════════════════════════════════════════
def _checkerboard(W:int, H:int, n_colors:int, size:int=None, seed:int=0) -> list:
    rng = random.Random(seed)
    if size is None:
        m = min(W, H)
        pool = [3,4,5] if m < 24 else ([4,5,6,7] if m < 32 else [6,7,8,9])
        size = rng.choice(pool)
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    def get_color(x, y):
        return perm[((x // size) + (y // size) + rot) % n_colors]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


def _apply_180_bfs_removal(grid: list, excess: dict, W: int, H: int,
                            n_colors: int, seed: int, targets: list = None,
                            max_cluster: int = 2):
    """주어진 grid에서 excess 만큼 180° orbit 페어를 chunk-based 분산 BFS로 제거.
    cluster당 max_cluster orbit (= TL측 셀 수) 제한. 실제 제거 셀수는 2 × max_cluster.
    max_cluster를 타일 면적(brick/rect 큰 타일)에 맞추면 whole-tile 제거 가능.

    targets가 주어지면 제거 후 실제 count가 targets와 일치하는지 검증,
    불일치 시 None 반환 → 호출 측이 다른 변형으로 대체 가능."""
    from collections import deque
    rng = random.Random(seed + 7919)

    removed = [[False]*W for _ in range(H)]

    def try_remove(x: int, y: int) -> bool:
        if removed[y][x]: return False
        x2, y2 = W-1-x, H-1-y
        if removed[y2][x2]: return False
        if (x, y) == (x2, y2):
            c = grid[y][x]
            if isinstance(c, int) and excess.get(c, 0) >= 1:
                grid[y][x] = 'K'; removed[y][x] = True
                excess[c] -= 1; return True
            return False
        a, b = grid[y][x], grid[y2][x2]
        if not (isinstance(a, int) and isinstance(b, int)): return False
        if a == b:
            if excess.get(a, 0) >= 2:
                grid[y][x] = 'K'; grid[y2][x2] = 'K'
                removed[y][x] = True; removed[y2][x2] = True
                excess[a] -= 2; return True
        else:
            if excess.get(a, 0) > 0 and excess.get(b, 0) > 0:
                grid[y][x] = 'K'; grid[y2][x2] = 'K'
                removed[y][x] = True; removed[y2][x2] = True
                excess[a] -= 1; excess[b] -= 1; return True
        return False

    def all_done() -> bool:
        return all(e <= 0 for e in excess.values())

    if not all_done():
        visited = [[False]*W for _ in range(H)]
        # interior seed 우선 (외곽 행/열 통째 bg 방지)
        interior_seeds = []
        edge_seeds = []
        for y in range(H):
            for x in range(W):
                x2, y2 = W-1-x, H-1-y
                if (y, x) <= (y2, x2):
                    if y == 0 or y == H-1 or x == 0 or x == W-1:
                        edge_seeds.append((x, y))
                    else:
                        interior_seeds.append((x, y))
        rng.shuffle(interior_seeds)
        rng.shuffle(edge_seeds)
        seed_candidates = interior_seeds + edge_seeds

        for sx, sy in seed_candidates:
            if all_done(): break
            if visited[sy][sx]: continue
            queue = deque([(sx, sy)])
            visited[sy][sx] = True
            cluster_orbits = 0
            # max_cluster가 타일 면적이면 cluster_orbits도 면적 단위 (TL측 셀 수)
            while queue and cluster_orbits < max_cluster and not all_done():
                x, y = queue.popleft()
                if try_remove(x, y):
                    cluster_orbits += 1
                for dx, dy in [(1, 0), (0, 1), (-1, 0), (0, -1)]:
                    nx, ny = x+dx, y+dy
                    if 0 <= nx < W and 0 <= ny < H and not visited[ny][nx]:
                        visited[ny][nx] = True
                        queue.append((nx, ny))

    for c in range(n_colors):
        while excess[c] > 0:
            found = False
            for y in range(H):
                for x in range(W):
                    if grid[y][x] == c:
                        grid[y][x] = 'K'
                        excess[c] -= 1; found = True; break
                if found: break
            if not found: break

    if targets is not None:
        from collections import Counter
        final = Counter(c for row in grid for c in row)
        for c in range(n_colors):
            if final.get(c, 0) != targets[c]:
                return None  # target 미달성 → 호출 측이 다른 변형 선택
    return grid


def _tile_grid_to_targets(W: int, H: int, n_colors: int,
                           targets: list, bg_count: int,
                           tile_w: int, tile_h: int,
                           seed: int = 0,
                           max_cluster: int = None,
                           expand_search: bool = True) -> list:
    """Tiled grid 공통 helper. natural (x//tw + y//th + rot)%n 생성 후 BFS 제거.
    expand_search=True: 힌트보다 큰 타일도 탐색 (rect_grid).
    expand_search=False: 힌트에서 작게만 축소 (checker — 힌트 그대로 유지 선호).
    max_cluster=None이면 tile_area 기반 자동 (큰 타일 whole-tile 제거).
    max_cluster를 명시적으로 작게(2)하면 분산 scatter 유지."""
    from collections import Counter
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    def make_grid_fn(tw: int, th: int, rot: int) -> list:
        return [[perm[((x // tw) + (y // th) + rot) % n_colors]
                 for x in range(W)] for y in range(H)]

    tw0 = max(1, tile_w); th0 = max(1, tile_h)
    candidates = []
    seen = set()
    if expand_search:
        # 힌트 ±2 범위 탐색, 큰 타일 우선
        for tw in range(tw0 + 2, 0, -1):
            for th in range(th0 + 2, 0, -1):
                tw_c = max(1, tw); th_c = max(1, th)
                if (tw_c, th_c) not in seen:
                    seen.add((tw_c, th_c)); candidates.append((tw_c, th_c))
        candidates.sort(key=lambda t: (-t[0]*t[1], -(t[0]+t[1])))
    else:
        # 힌트 크기부터 축소만 — checker 스타일 유지
        for dec in range(max(tw0, th0)):
            ctw = max(1, tw0 - dec); cth = max(1, th0 - dec)
            if (ctw, cth) not in seen:
                seen.add((ctw, cth)); candidates.append((ctw, cth))
        for extra in [(2, 2), (1, 1)]:
            if extra not in seen:
                seen.add(extra); candidates.append(extra)

    best_rot = None; best_total = None; best_tw = tw0; best_th = th0
    for ctw, cth in candidates:
        for rot in range(n_colors):
            g = make_grid_fn(ctw, cth, rot)
            cnt = Counter(c for row in g for c in row)
            if all(cnt.get(c, 0) >= targets[c] for c in range(n_colors)):
                tot = sum(cnt.get(c, 0) - targets[c] for c in range(n_colors))
                if best_total is None or tot < best_total:
                    best_total = tot; best_rot = rot
                    best_tw, best_th = ctw, cth
        if best_rot is not None:
            break  # 첫 feasible (가장 큰 타일)에서 멈춤

    if best_rot is None:
        best_rot = rng.randrange(max(1, n_colors))
        best_tw, best_th = 1, 1

    grid = make_grid_fn(best_tw, best_th, best_rot)
    counts = Counter(c for row in grid for c in row)
    excess = {c: counts.get(c, 0) - targets[c] for c in range(n_colors)}
    tile_area = best_tw * best_th
    mc = max_cluster if max_cluster is not None else max(2, tile_area)
    return _apply_180_bfs_removal(grid, excess, W, H, n_colors, seed,
                                   targets=targets, max_cluster=mc)


def _checker_to_targets(W: int, H: int, n_colors: int,
                         targets: list, bg_count: int,
                         tile_size: int = 1,
                         seed: int = 0) -> list:
    """plan_counts targets/bg_count 맞춰 checkerboard 생성 (정사각 타일).
    max_cluster=2 — Lv123 스타일 작은 분산 클러스터."""
    return _tile_grid_to_targets(W, H, n_colors, targets, bg_count,
                                  tile_size, tile_size, seed,
                                  max_cluster=2, expand_search=False)


def _rect_grid_to_targets(W: int, H: int, n_colors: int,
                           targets: list, bg_count: int,
                           tile_w: int = 4, tile_h: int = 4,
                           seed: int = 0) -> list:
    """plan_counts targets/bg_count 맞춰 rect_grid 생성 (tile_w × tile_h 직사각 타일).
    원본 `_rect_grid` (concentric-plaid zones)과는 다른, 단순 tiled 버전 — 10-mult 보장 우선."""
    return _tile_grid_to_targets(W, H, n_colors, targets, bg_count,
                                  tile_w, tile_h, seed)


def _brick_to_targets(W: int, H: int, n_colors: int,
                       targets: list, bg_count: int,
                       brick_w: int = 5, brick_h: int = 4,
                       seed: int = 0):
    """plan_counts targets/bg_count 맞춰 brick 생성.
    줄눈(mortar) 없음. row-shifted tile: row%2==1이면 brick_w//2 offset.
    큰 브릭에서 내부 쥐파먹음 회피 위해 excess가 brick_area 배수인 크기 우선 선택,
    BFS 클러스터 크기도 brick_area로 맞춰 whole-brick 단위 제거."""
    from collections import Counter
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    def make_grid_fn(bw: int, bh: int, rot: int) -> list:
        g = []
        for y in range(H):
            row_idx = y // bh
            off = bw // 2 if row_idx % 2 == 1 else 0
            g.append([perm[(row_idx + ((x + off) // bw) + rot) % n_colors]
                      for x in range(W)])
        return g

    # 후보 크기: 기본값부터 아래로 + 흔한 작은 크기들
    size_candidates = []
    for bw in [brick_w, brick_w-1, 5, 4, 3]:
        for bh in [brick_h, brick_h-1, 4, 3, 2]:
            bw2 = max(2, bw); bh2 = max(2, bh)
            if (bw2, bh2) not in size_candidates:
                size_candidates.append((bw2, bh2))

    # target relax loop — 자연이 안 맞으면 per_color 단계 하향
    total = W * H
    original_per = targets[0] if targets else 0
    per_candidates = []
    p = original_per
    while p > 0:
        bg = total - p * n_colors
        if bg / total > 0.15:
            break
        per_candidates.append(p)
        p -= 10
    if not per_candidates and original_per > 0:
        per_candidates.append(original_per)

    for try_per in per_candidates:
        try_targets = [try_per] * n_colors
        # 최적 선택: (align_score, -brick_area, total_excess)
        best = None
        for bw, bh in size_candidates:
            ba = bw * bh
            for rot in range(n_colors):
                g = make_grid_fn(bw, bh, rot)
                cnt = Counter(c for row in g for c in row)
                if not all(cnt.get(c, 0) >= try_targets[c] for c in range(n_colors)):
                    continue
                excess_list = [cnt[c] - try_targets[c] for c in range(n_colors)]
                align_score = max(e % ba for e in excess_list)
                score = (align_score, -ba, sum(excess_list))
                if best is None or score < best[0]:
                    best = (score, bw, bh, rot, ba)
        if best is None:
            continue
        _, bw, bh, rot, ba = best
        grid = make_grid_fn(bw, bh, rot)
        counts = Counter(c for row in grid for c in row)
        excess = {c: counts.get(c, 0) - try_targets[c] for c in range(n_colors)}
        out = _apply_180_bfs_removal(grid, excess, W, H, n_colors, seed,
                                       targets=try_targets, max_cluster=ba)
        if out is not None:
            return out
    return None


def _natural_to_targets(pattern_fn, W: int, H: int, n_colors: int,
                          targets: list, bg_count: int,
                          seed: int = 0, max_attempts: int = 20,
                          max_cluster: int = 2,
                          max_bg_ratio: float = 0.15):
    """Generic target-aware: 기존 패턴 함수로 natural grid 생성 후 BFS 제거.
    pattern_fn(W, H, n_colors, seed) → int color index grid.
    여러 seed 시도해서 natural >= target 하나 찾으면 BFS 제거 적용.
    원래 target 불가 시 target 단계적 하향 (bg_ratio max_bg_ratio 까지).
    여전히 불가하면 None."""
    from collections import Counter
    total = W * H
    original_per = targets[0] if targets else 0

    # 원래 target부터 시작해서 10씩 낮추며 시도
    per_candidates = []
    per = original_per
    while per > 0:
        bg = total - per * n_colors
        if bg / total > max_bg_ratio:
            break
        per_candidates.append(per)
        per -= 10
    # 첫 후보가 없을 만큼 큰 bg면 최소 1 시도
    if not per_candidates and original_per > 0:
        per_candidates.append(original_per)

    # 시그니처가 (W, H, n_colors, seed)이 아닌 함수도 있음 (hex_tile, brick 등).
    # 'seed' 파라미터가 있으면 kwarg로 전달.
    import inspect
    fn_params = inspect.signature(pattern_fn).parameters
    seed_kwarg = {'seed': None}  # 호출 시 갱신

    for try_per in per_candidates:
        try_targets = [try_per] * n_colors
        for attempt in range(max_attempts):
            try_seed = seed + attempt * 7919
            try:
                if 'seed' in fn_params:
                    grid = pattern_fn(W, H, n_colors, seed=try_seed)
                else:
                    grid = pattern_fn(W, H, n_colors)
            except Exception:
                continue
            cnt = Counter(c for row in grid for c in row if isinstance(c, int))
            if all(cnt.get(c, 0) >= try_targets[c] for c in range(n_colors)):
                excess = {c: cnt.get(c, 0) - try_targets[c] for c in range(n_colors)}
                grid_copy = [row[:] for row in grid]
                return _apply_180_bfs_removal(grid_copy, excess, W, H, n_colors,
                                                try_seed, targets=try_targets,
                                                max_cluster=max_cluster)
    return None


def _partition_into_uniform_groups(rings: list, n_groups: int, target: int,
                                       time_budget_ms: int) -> list:
    """각 그룹 합이 정확히 target. cap=target로 strict pruning. 가장 빠름.
    반환: assignment[ring_idx -> group_idx] or None."""
    import time
    R = len(rings)
    if sum(rings) != n_groups * target:
        return None
    if R < n_groups:
        return None
    deadline = time.monotonic() + time_budget_ms / 1000.0
    order = sorted(range(R), key=lambda i: -rings[i])
    sorted_rings = [rings[i] for i in order]

    sums = [0] * n_groups
    sorted_assignment = [0] * R

    def search(pos):
        if time.monotonic() > deadline:
            return False
        if pos == R:
            return all(s == target for s in sums)
        ring = sorted_rings[pos]
        used_max = max((sorted_assignment[i] for i in range(pos)), default=-1)
        max_g = min(n_groups - 1, used_max + 1)
        # 작은 sum 그룹 먼저 (균형)
        cands = sorted(range(max_g + 1), key=lambda g: sums[g])
        for g in cands:
            if sums[g] + ring > target:
                continue
            sums[g] += ring
            sorted_assignment[pos] = g
            if search(pos + 1):
                return True
            sums[g] -= ring
        return False

    if not search(0):
        return None
    orig_assignment = [0] * R
    for sorted_idx, g in enumerate(sorted_assignment):
        orig_assignment[order[sorted_idx]] = g
    return orig_assignment


def _partition_into_groups(rings: list, n_groups: int, color_cap: int,
                              time_budget_ms: int) -> list:
    """Rings를 n_groups 그룹으로 분할, 각 그룹 sum이 10x이고 cap 이하.
    label-symmetry break + 큰 ring부터. score: spread 최소화.
    반환: 가장 균형잡힌 partition (group_index per ring) 또는 None."""
    import time
    R = len(rings)
    if R < n_groups:
        return None
    # 큰 ring 먼저 배치
    order = sorted(range(R), key=lambda i: -rings[i])
    sorted_rings = [rings[i] for i in order]
    suffix_sum = [0] * (R + 1)
    for i in range(R - 1, -1, -1):
        suffix_sum[i] = suffix_sum[i + 1] + sorted_rings[i]

    best = [None]  # (spread, assignment_sorted_order)
    deadline = time.monotonic() + time_budget_ms / 1000.0

    def backtrack(pos, sums, assignment):
        if time.monotonic() > deadline:
            return
        if best[0] is not None:
            cur_spread_lb = max(sums) - min(sums)
            if cur_spread_lb >= best[0][0]:
                return
        if pos == R:
            if all(s > 0 and s % 10 == 0 for s in sums):
                spread = max(sums) - min(sums)
                if best[0] is None or spread < best[0][0]:
                    best[0] = (spread, assignment[:])
            return
        # remaining rings 잔량 < 미사용 그룹 × 10이면 무효
        used_groups = sum(1 for s in sums if s > 0)
        unused_groups = n_groups - used_groups
        if suffix_sum[pos] < unused_groups * 10:
            return
        ring = sorted_rings[pos]
        # 대칭 break: 사용된 그룹 + 처음 사용 그룹 1개만
        used_max = max((g for g in assignment), default=-1)
        max_g = min(n_groups - 1, used_max + 1)
        # 작은 sum 그룹부터 시도 (균형 heuristic)
        cands = sorted(range(max_g + 1), key=lambda g: sums[g])
        for g in cands:
            new = sums[g] + ring
            if new > color_cap:
                continue
            sums[g] = new
            assignment.append(g)
            backtrack(pos + 1, sums, assignment)
            sums[g] -= ring
            assignment.pop()

    backtrack(0, [0] * n_groups, [])
    if best[0] is None:
        return None
    _, sorted_assignment = best[0]
    orig_assignment = [0] * R
    for sorted_idx, g in enumerate(sorted_assignment):
        orig_assignment[order[sorted_idx]] = g
    return orig_assignment


def _subset_sum_indices(rings: list, target: int) -> list:
    """rings 중에서 합이 정확히 target인 부분집합의 인덱스 리스트. 없으면 None.
    DP backtrace."""
    if target == 0:
        return []
    R = len(rings)
    # DP: reachable[v] = list of last-ring-idx-that-led-to-v (for backtrace)
    parent = {0: (-1, -1)}  # value -> (prev_value, ring_idx)
    reachable = {0}
    for i, r in enumerate(rings):
        if r > target:
            continue
        new_reach = []
        for v in list(reachable):
            nv = v + r
            if nv == target:
                # backtrace
                indices = [i]
                cur = v
                while cur > 0:
                    pv, pi = parent[cur]
                    indices.append(pi)
                    cur = pv
                return sorted(indices)
            if nv < target and nv not in reachable:
                parent[nv] = (v, i)
                new_reach.append(nv)
        reachable.update(new_reach)
    return None


def _concentric_ring_partition(ring_areas: list, n_colors: int,
                                 max_bg_ratio: float = 0.15,
                                 max_color_ratio: float = 1.4,
                                 time_budget_ms: int = 3000) -> tuple:
    """2-stage subset-sum 분할:
       (1) bg를 0부터 증가시키며 ring subset으로 정확히 매칭
       (2) 남은 ring을 n_colors 그룹으로 분할 (각 10x, balanced)
    bg 후보: total mod 10 = bg mod 10 (각 색 10x이므로 bg residue도 결정됨).
    반환: (assignment_list[ring_idx -> color or -1], bg_total) or None."""
    import time
    R = len(ring_areas)
    total = sum(ring_areas)
    bg_max = int(total * max_bg_ratio)
    target_residue = total % 10
    avg_per_color = (total - 0) / n_colors  # bg=0 가정 시 avg
    color_cap = int(avg_per_color * max_color_ratio // 10) * 10 + 10

    deadline = time.monotonic() + time_budget_ms / 1000.0

    # bg 후보: residue 호환 + 0 ≤ bg ≤ bg_max
    bg_candidates = [v for v in range(0, bg_max + 1)
                     if v % 10 == target_residue]
    # bg 작은 것부터 시도

    best_result = None  # (score=(bg, spread), assignment)
    for bg in bg_candidates:
        if time.monotonic() > deadline:
            break
        if best_result is not None and bg > best_result[0][0]:
            break  # bg 큰 후보로 가도 더 좋아질 수 없음
        # bg subset 찾기
        if bg == 0:
            bg_indices = []
        else:
            bg_indices = _subset_sum_indices(ring_areas, bg)
            if bg_indices is None:
                continue
        # 남은 ring index 및 area
        remaining_idx = [i for i in range(R) if i not in set(bg_indices)]
        remaining_areas = [ring_areas[i] for i in remaining_idx]
        # n_colors 그룹 분할
        remaining_total = sum(remaining_areas)
        new_avg = remaining_total / n_colors
        new_cap = int(new_avg * max_color_ratio // 10) * 10 + 10
        # 남은 시간 budget
        remain_ms = int((deadline - time.monotonic()) * 1000)
        if remain_ms < 100: break
        sub_budget = min(remain_ms, 3000)
        # (a) Uniform 분할 우선 (strict cap=target → 빠른 pruning)
        partition = None
        if remaining_total % n_colors == 0:
            uniform_target = remaining_total // n_colors
            if uniform_target % 10 == 0 and uniform_target > 0:
                partition = _partition_into_uniform_groups(
                    remaining_areas, n_colors, uniform_target,
                    sub_budget // 2)
        # (b) Uniform 실패 시 비균일 (cap 안에서 각 그룹 10x)
        if partition is None:
            remain_ms2 = int((deadline - time.monotonic()) * 1000)
            if remain_ms2 < 100: break
            partition = _partition_into_groups(remaining_areas, n_colors,
                                                  new_cap,
                                                  min(remain_ms2, 3000))
        if partition is None:
            partition = _partition_into_groups(remaining_areas, n_colors,
                                                  remaining_total, sub_budget)
        if partition is None:
            continue
        # 색 sum 계산 → spread
        color_sums = [0] * n_colors
        for i, g in enumerate(partition):
            color_sums[g] += remaining_areas[i]
        spread = max(color_sums) - min(color_sums)
        score = (bg, spread)
        if best_result is None or score < best_result[0]:
            assignment = [0] * R
            for i in bg_indices:
                assignment[i] = -1
            for i, g in enumerate(partition):
                assignment[remaining_idx[i]] = g
            best_result = (score, assignment)

    if best_result is None:
        return None
    score, assignment = best_result
    return assignment, score[0]


def _concentric_sq_to_targets(W: int, H: int, n_colors: int,
                                 targets: list, bg_count: int,
                                 ring: int = 2,
                                 seed: int = 0):
    """concentric_sq target-aware. 우선순위:
       (1) Subset-sum partition: 각 Chebyshev frame을 한 색에 통째 할당
           → 모든 색 10x, bg 최소. 가장 깔끔한 동심 모양.
       (2) 실패 시 자연 cycling + BFS removal (기존 fallback).
    """
    from collections import Counter
    rng = random.Random(seed)
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0

    # ── (1) Subset-sum: ring 별 cell 그룹화 (Chebyshev distance index) ──
    from collections import defaultdict
    ring_cells = defaultdict(list)
    for y in range(H):
        for x in range(W):
            d = int(max(abs(x - cx), abs(y - cy)))
            ring_cells[d].append((x, y))
    ring_indices = sorted(ring_cells.keys())
    ring_areas = [len(ring_cells[d]) for d in ring_indices]

    # 큰 grid (ring 많음 + 색 많음)는 시간 더 부여
    R = len(ring_areas)
    budget_ms = 1500 if R * n_colors < 100 else (15000 if R * n_colors < 250 else 25000)
    result = _concentric_ring_partition(ring_areas, n_colors,
                                          max_bg_ratio=0.15,
                                          time_budget_ms=budget_ms)
    if result is not None:
        assignment, bg_total = result
        # 색 라벨 셔플 (시드 기반, 시각적 다양성)
        perm = list(range(n_colors)); rng.shuffle(perm)
        grid = [['K'] * W for _ in range(H)]
        for ridx, d in enumerate(ring_indices):
            c = assignment[ridx]
            cell_color = perm[c] if c >= 0 else 'K'
            for (x, y) in ring_cells[d]:
                grid[y][x] = cell_color
        return grid

    # ── (2) Fallback: 자연 cycling + BFS removal ──
    perm = list(range(n_colors)); rng.shuffle(perm)
    def make_grid_fn(r: int, rot: int) -> list:
        return [[perm[(int(max(abs(x - cx), abs(y - cy)) // r) + rot) % n_colors]
                 for x in range(W)] for y in range(H)]

    candidates = []
    seen = set()
    for r in range(max(2, ring) + 2, 1, -1):
        if r not in seen:
            seen.add(r); candidates.append(r)
    if 2 not in seen: candidates.append(2)
    if 1 not in seen: candidates.append(1)

    # target-relax loop (natural_to_targets 스타일)
    total = W * H
    original_per = targets[0] if targets else 0
    per_candidates = []
    p = original_per
    while p > 0:
        bg = total - p * n_colors
        if bg / total > 0.15:
            break
        per_candidates.append(p)
        p -= 10
    if not per_candidates and original_per > 0:
        per_candidates.append(original_per)

    for try_per in per_candidates:
        try_targets = [try_per] * n_colors
        for r in candidates:
            for rot in range(n_colors):
                g = make_grid_fn(r, rot)
                cnt = Counter(c for row in g for c in row)
                if all(cnt.get(c, 0) >= try_targets[c] for c in range(n_colors)):
                    excess = {c: cnt.get(c, 0) - try_targets[c]
                              for c in range(n_colors)}
                    out = _apply_180_bfs_removal(g, excess, W, H, n_colors,
                                                  seed, targets=try_targets)
                    if out is not None:
                        return out
    return None


def _argyle_to_targets(W: int, H: int, n_colors: int,
                          targets: list, bg_count: int,
                          seed: int = 0):
    """Argyle target-aware. 라인 없이 lattice 기반 색칠. 여러 lattice 시도:
       (a) 대각 다이아몬드: (x+y)//s + (x-y)//s
       (b) 사각 격자:       x//s + y//s
       (c) 단방향 대각:     (x+y)//s
       각 formula × size × rot 조합 시도하여 자연 분포가 target 만족하면 BFS 제거."""
    from collections import Counter
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    sizes = list(range(max(3, min(W, H) // 3), 2, -1))
    if not sizes: sizes = [3]

    def grid_diamond(s, rot):
        return [[perm[(((x + y) // s) + ((x - y) // s) + rot) % n_colors]
                 for x in range(W)] for y in range(H)]
    def grid_rect(s, rot):
        return [[perm[((x // s) + (y // s) + rot) % n_colors]
                 for x in range(W)] for y in range(H)]
    def grid_stripe_diag(s, rot):
        return [[perm[(((x + y) // s) + rot) % n_colors]
                 for x in range(W)] for y in range(H)]

    formulas = [grid_diamond, grid_rect, grid_stripe_diag]

    total = W * H
    original_per = targets[0] if targets else 0
    per_candidates = []
    p = original_per
    while p > 0:
        bg = total - p * n_colors
        if bg / total > 0.15:
            break
        per_candidates.append(p)
        p -= 10
    if not per_candidates and original_per > 0:
        per_candidates.append(original_per)

    for try_per in per_candidates:
        try_targets = [try_per] * n_colors
        for fn in formulas:
            for s in sizes:
                for rot in range(n_colors):
                    grid = fn(s, rot)
                    cnt = Counter(c for row in grid for c in row)
                    if all(cnt.get(c, 0) >= try_targets[c] for c in range(n_colors)):
                        excess = {c: cnt.get(c, 0) - try_targets[c]
                                  for c in range(n_colors)}
                        out = _apply_180_bfs_removal(grid, excess, W, H,
                                                      n_colors, seed,
                                                      targets=try_targets)
                        if out is not None:
                            return out
    return None


def _maze_to_targets(W: int, H: int, n_colors: int,
                        targets: list, bg_count: int,
                        seed: int = 0):
    """Maze target-aware. 자연 DFS 분포가 imbalanced하므로 lattice 기반.
    여러 T (tile size) × formula × rot 조합 시도."""
    from collections import Counter
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    Ts = list(range(max(2, min(W, H) // 6), max(2, min(W, H) // 2) + 1))

    def grid_rect(T, rot):
        return [[perm[((x // T) + (y // T) + rot) % n_colors]
                 for x in range(W)] for y in range(H)]
    def grid_diamond(T, rot):
        return [[perm[(((x + y) // T) + ((x - y) // T) + rot) % n_colors]
                 for x in range(W)] for y in range(H)]
    formulas = [grid_rect, grid_diamond]

    total = W * H
    original_per = targets[0] if targets else 0
    per_candidates = []
    p = original_per
    while p > 0:
        bg = total - p * n_colors
        if bg / total > 0.15:
            break
        per_candidates.append(p)
        p -= 10
    if not per_candidates and original_per > 0:
        per_candidates.append(original_per)

    for try_per in per_candidates:
        try_targets = [try_per] * n_colors
        for fn in formulas:
            for T in Ts:
                for rot in range(n_colors):
                    grid = fn(T, rot)
                    cnt = Counter(c for row in grid for c in row)
                    if all(cnt.get(c, 0) >= try_targets[c] for c in range(n_colors)):
                        excess = {c: cnt.get(c, 0) - try_targets[c]
                                  for c in range(n_colors)}
                        out = _apply_180_bfs_removal(grid, excess, W, H,
                                                      n_colors, seed,
                                                      targets=try_targets)
                        if out is not None:
                            return out
    return None


def _i_tetromino_to_targets(W: int, H: int, n_colors: int,
                                targets: list, bg_count: int,
                                seed: int = 0):
    """I-tetromino target-aware. 자연 role-based 분포가 imbalanced하므로
    tile-grid 기반 lattice (tx+ty)%n으로 대체. 여러 T(tile size) 시도."""
    from collections import Counter
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    Ts = [4, 5, 6, 8, 10, 12, 3]

    def grid_rect(T, rot):
        return [[perm[((x // T) + (y // T) + rot) % n_colors]
                 for x in range(W)] for y in range(H)]
    def grid_diamond(T, rot):
        return [[perm[(((x + y) // T) + ((x - y) // T) + rot) % n_colors]
                 for x in range(W)] for y in range(H)]

    formulas = [grid_rect, grid_diamond]

    total = W * H
    original_per = targets[0] if targets else 0
    per_candidates = []
    p = original_per
    while p > 0:
        bg = total - p * n_colors
        if bg / total > 0.15:
            break
        per_candidates.append(p)
        p -= 10
    if not per_candidates and original_per > 0:
        per_candidates.append(original_per)

    for try_per in per_candidates:
        try_targets = [try_per] * n_colors
        for fn in formulas:
            for T in Ts:
                for rot in range(n_colors):
                    grid = fn(T, rot)
                    cnt = Counter(c for row in grid for c in row)
                    if all(cnt.get(c, 0) >= try_targets[c] for c in range(n_colors)):
                        excess = {c: cnt.get(c, 0) - try_targets[c]
                                  for c in range(n_colors)}
                        out = _apply_180_bfs_removal(grid, excess, W, H,
                                                      n_colors, seed,
                                                      targets=try_targets)
                        if out is not None:
                            return out
    return None


def _hex_tile_to_targets(W: int, H: int, n_colors: int,
                            targets: list, bg_count: int,
                            seed: int = 0):
    """Hex_tile target-aware. outline 없이 hex 내부만 색칠.
    (a) 자연 (2q+3r)%n cycling으로 target 만족하면 BFS 제거.
    (b) 실패 시 hex 별 subset-sum partition (각 hex을 한 색에 통째 할당)."""
    from collections import Counter, defaultdict
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)
    cx0, cy0 = (W - 1) / 2.0, (H - 1) / 2.0

    def axial_round(q, r):
        s = -q - r
        rq, rr, rs = round(q), round(r), round(s)
        dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
        if dq > dr and dq > ds: rq = -rr - rs
        elif dr > ds: rr = -rq - rs
        return rq, rr

    def hex_map(radius):
        """Return dict (hq, hr) -> list of (x, y)."""
        cells = defaultdict(list)
        for gy in range(H):
            for gx in range(W):
                xx, yy = gx - cx0, gy - cy0
                q = (math.sqrt(3) / 3 * xx - 1 / 3 * yy) / radius
                r = (2 / 3 * yy) / radius
                hq, hr = axial_round(q, r)
                cells[(hq, hr)].append((gx, gy))
        return cells

    radii = [3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0]

    # ── (a) 자연 cycling 시도 ──
    total = W * H
    original_per = targets[0] if targets else 0
    per_candidates = []
    p = original_per
    while p > 0:
        bg = total - p * n_colors
        if bg / total > 0.15:
            break
        per_candidates.append(p)
        p -= 10
    if not per_candidates and original_per > 0:
        per_candidates.append(original_per)

    for try_per in per_candidates:
        try_targets = [try_per] * n_colors
        for radius in radii:
            cells = hex_map(radius)
            for rot in range(n_colors):
                grid = [[0] * W for _ in range(H)]
                for (hq, hr), cell_list in cells.items():
                    base = ((hq * 2 + hr * 3) % n_colors + n_colors) % n_colors
                    color = perm[(base + rot) % n_colors]
                    for (x, y) in cell_list:
                        grid[y][x] = color
                cnt = Counter(c for row in grid for c in row)
                if all(cnt.get(c, 0) >= try_targets[c] for c in range(n_colors)):
                    excess = {c: cnt.get(c, 0) - try_targets[c]
                              for c in range(n_colors)}
                    out = _apply_180_bfs_removal(grid, excess, W, H, n_colors,
                                                  seed, targets=try_targets)
                    if out is not None:
                        return out

    # ── (b) Subset-sum: 각 hex을 한 색에 통째 할당 ──
    for radius in radii:
        cells = hex_map(radius)
        hex_keys = list(cells.keys())
        hex_areas = [len(cells[k]) for k in hex_keys]
        if len(hex_areas) < n_colors:
            continue
        budget_ms = 5000 if len(hex_areas) * n_colors < 100 else 12000
        result = _concentric_ring_partition(hex_areas, n_colors,
                                              max_bg_ratio=0.15,
                                              time_budget_ms=budget_ms)
        if result is None:
            continue
        assignment, bg_total = result
        perm2 = list(range(n_colors)); rng.shuffle(perm2)
        grid = [['K'] * W for _ in range(H)]
        for hidx, k in enumerate(hex_keys):
            c = assignment[hidx]
            cell_color = perm2[c] if c >= 0 else 'K'
            for (x, y) in cells[k]:
                grid[y][x] = cell_color
        return grid
    return None


def _chevron_to_targets(W: int, H: int, n_colors: int,
                          targets: list, bg_count: int,
                          band: int = 5,
                          seed: int = 0):
    """plan_counts targets/bg_count 맞춰 chevron 생성.
    V자 밴드: color=((y + |x-cx|) // band + rot) % n. band 자동 축소."""
    from collections import Counter
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)
    cx = W // 2

    def make_grid_fn(bd: int, rot: int) -> list:
        return [[perm[(((y + abs(x - cx)) // bd) + rot) % n_colors]
                 for x in range(W)] for y in range(H)]

    candidates = []
    seen = set()
    for bd in range(max(2, band) + 2, 1, -1):
        if bd not in seen:
            seen.add(bd); candidates.append(bd)
    if 2 not in seen: candidates.append(2)
    if 1 not in seen: candidates.append(1)

    best_rot = None; best_total = None; best_band = band
    for bd in candidates:
        for rot in range(n_colors):
            g = make_grid_fn(bd, rot)
            cnt = Counter(c for row in g for c in row)
            if all(cnt.get(c, 0) >= targets[c] for c in range(n_colors)):
                tot = sum(cnt.get(c, 0) - targets[c] for c in range(n_colors))
                if best_total is None or tot < best_total:
                    best_total = tot; best_rot = rot; best_band = bd
        if best_rot is not None:
            break
    if best_rot is None:
        best_rot = rng.randrange(max(1, n_colors))
        best_band = 1

    grid = make_grid_fn(best_band, best_rot)
    counts = Counter(c for row in grid for c in row)
    excess = {c: counts.get(c, 0) - targets[c] for c in range(n_colors)}
    return _apply_180_bfs_removal(grid, excess, W, H, n_colors, seed, targets=targets)


def _diamond_check_to_targets(W: int, H: int, n_colors: int,
                                targets: list, bg_count: int,
                                size: int = 5,
                                seed: int = 0) -> list:
    """plan_counts targets/bg_count 맞춰 diamond pattern 생성.
    n≤4: 중심 기반 Manhattan 거리 concentric diamond rings (실제 마름모 모양).
    n>4: 45° 회전 체커 (기존 수식)."""
    from collections import Counter
    rng = random.Random(seed)
    perm = list(range(n_colors)); rng.shuffle(perm)

    use_concentric = n_colors <= 4
    cx, cy = (W - 1) / 2.0, (H - 1) / 2.0

    def make_grid_fn(s: int, rot: int) -> list:
        if use_concentric:
            # Manhattan distance ring → diamond 모양 concentric
            return [[perm[(int((abs(x - cx) + abs(y - cy)) // s) + rot) % n_colors]
                     for x in range(W)] for y in range(H)]
        else:
            return [[perm[(((x + y) // s) + ((x - y) // s) + rot) % n_colors]
                     for x in range(W)] for y in range(H)]

    candidates = []
    seen = set()
    for cs in range(max(2, size), 1, -1):
        if cs not in seen:
            seen.add(cs); candidates.append(cs)
    if 2 not in seen: candidates.append(2)
    if 1 not in seen: candidates.append(1)

    best_rot = None; best_total = None; best_size = size
    for cs in candidates:
        for rot in range(n_colors):
            g = make_grid_fn(cs, rot)
            cnt = Counter(c for row in g for c in row)
            if all(cnt.get(c, 0) >= targets[c] for c in range(n_colors)):
                tot = sum(cnt.get(c, 0) - targets[c] for c in range(n_colors))
                if best_total is None or tot < best_total:
                    best_total = tot; best_rot = rot; best_size = cs
        if best_rot is not None:
            break

    if best_rot is None:
        best_rot = rng.randrange(max(1, n_colors))
        best_size = 1

    grid = make_grid_fn(best_size, best_rot)
    counts = Counter(c for row in grid for c in row)
    excess = {c: counts.get(c, 0) - targets[c] for c in range(n_colors)}
    return _apply_180_bfs_removal(grid, excess, W, H, n_colors, seed, targets=targets)


def _checkerboard_B(W:int, H:int, n_colors:int, size:int=None, seed:int=0) -> list:
    """_B 변형: 그리드 중심 기준 동심 사각형 (항상 대칭)."""
    rng = random.Random(seed)
    if size is None:
        m = min(W, H)
        pool = [3,4,5] if m < 24 else ([4,5,6,7] if m < 32 else [6,7,8,9])
        size = rng.choice(pool)
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    cx, cy = (W-1)/2.0, (H-1)/2.0
    def get_color(x, y):
        bx = int(abs(x - cx) // size)
        by = int(abs(y - cy) // size)
        return perm[(bx + by + rot) % n_colors]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 15. Concentric Squares (중앙 기준 동심 사각형 반지 = 링)
#     완벽한 4-fold 대칭 + LR/TB 미러
# ══════════════════════════════════════════════════════════════════════════
def _concentric_sq(W:int, H:int, n_colors:int, seed:int=0) -> list:
    rng = random.Random(seed)
    ring = rng.choice([2, 3])   # 링 두께
    perm = list(range(n_colors)); rng.shuffle(perm)
    rot  = rng.randrange(max(1, n_colors))
    cx, cy = (W-1)/2.0, (H-1)/2.0
    def get_color(x, y):
        # 체비셰프 거리 (정사각 링)
        d = max(abs(x - cx), abs(y - cy))
        idx = int(d // ring)
        return perm[(idx + rot) % n_colors]
    return [[get_color(x, y) for x in range(W)] for y in range(H)]


# ══════════════════════════════════════════════════════════════════════════
# 메인 API
# ══════════════════════════════════════════════════════════════════════════
PATTERN_FUNCS = {
    "kaleidoscope":      _kaleidoscope,
    "hex_tile":          _hex_tile,
    "maze":              _maze,
    "brick":             _brick,
    "i_tetromino":       _i_tetromino,
    "rect_grid":         _rect_grid,
    "diamond_check":     _diamond_check,
    "stripe":            _stripe,
    "xor_fractal":       _xor_fractal,
    "sierpinski_carpet": _sierpinski_carpet,
    "truchet":           _truchet,
    "chevron":           _chevron,
    "argyle":            _argyle,
    "wave":              _wave,
    "concentric_sq":     _concentric_sq,
    "checkerboard":      _checkerboard,
    "x_motif":           _x_motif,
    "t_motif":           _t_motif,
    "plus_motif":        _plus_motif,
}

def generate_pattern(
    pattern: str,
    width: int = 32,
    height: int = 40,
    block_size: int = 30,
    colors: Optional[List[str]] = None,
    transparent_bg: bool = False,
    seed: int = 42,
    **kwargs
) -> Image.Image:
    """
    기하학적 픽셀아트 패턴 생성

    Parameters
    ----------
    pattern      : 패턴 종류 (kaleidoscope/hex_tile/maze/brick/
                              i_tetromino/rect_grid/diamond_check/stripe)
    width        : 그리드 가로 칸 수 (최대 40)
    height       : 그리드 세로 칸 수 (최대 50)
    block_size   : 한 칸의 픽셀 크기 (기본 30)
    colors       : 사용할 HEX 색상 리스트. None이면 기본 팔레트 사용
    transparent_bg: True이면 RGBA 투명 배경 PNG
    seed         : 미로 등 랜덤 요소에 사용할 시드
    **kwargs     : 패턴별 추가 옵션 (아래 참고)

    패턴별 kwargs
    -------------
    hex_tile     : radius(float=5.5)
    brick        : brick_w(int=5), brick_h(int=4)
    i_tetromino  : (없음)
    rect_grid    : tile_w(int=5), tile_h(int=6)
    diamond_check: size(int=8)
    stripe       : stripe_width(int=4), direction(str="diagonal"|"vertical"|"horizontal")

    Returns
    -------
    PIL.Image.Image
    """
    assert 1 <= width <= 40,  f"width는 1~40 (입력값: {width})"
    assert 1 <= height <= 50, f"height는 1~50 (입력값: {height})"
    assert pattern in PATTERN_FUNCS, \
        f"지원 패턴: {list(PATTERN_FUNCS.keys())}"

    palette = resolve_colors(colors) if colors else DEFAULT_PALETTE
    n = len(palette)

    func = PATTERN_FUNCS[pattern]
    # seed가 필요한 함수만 전달
    import inspect
    sig = inspect.signature(func)
    params = sig.parameters
    call_kwargs = {k:v for k,v in {**kwargs, "seed":seed}.items() if k in params}
    grid = func(width, height, n, **call_kwargs)

    # 10배수 보정: 각 색 셀 수를 10의 배수로 맞춤 (모서리 대칭 깎기)
    grid = balance_to_x10(grid, width, height, bg_marker="K")

    return _make_image(grid, palette, width, height, block_size, transparent_bg)


def list_patterns() -> List[str]:
    """사용 가능한 패턴 목록 반환"""
    return list(PATTERN_FUNCS.keys())


# ── 직접 실행 시 데모 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    demo_colors_6 = ["#FC6AAF","#50E8F6","#8950F8","#FED555","#73FE66","#FDA14C"]
    demo_colors_5 = ["#FC6AAF","#50E8F6","#FED555","#73FE66","#FDA14C"]

    demos = [
        ("kaleidoscope",  32, 40, demo_colors_6, {}),
        ("hex_tile",      32, 32, demo_colors_6, {"radius": 5.5}),
        ("maze",          31, 39, demo_colors_5, {}),
        ("brick",         30, 40, demo_colors_6, {}),
        ("i_tetromino",   36, 40, demo_colors_6, {}),
        ("rect_grid",     25, 30, demo_colors_5, {}),
        ("diamond_check", 32, 40, demo_colors_6, {"size": 8}),
        ("stripe",        32, 40, demo_colors_6, {"stripe_width": 4, "direction": "diagonal"}),
    ]

    for name, w, h, cols, kw in demos:
        img = generate_pattern(name, width=w, height=h, colors=cols, **kw)
        img.save(f"/mnt/user-data/outputs/demo_{name}.png")
        print(f"  ✓ {name} ({w}×{h})")

    print("\n모든 데모 생성 완료!")
    print(f"지원 패턴: {list_patterns()}")


# ══════════════════════════════════════════════════════════════════════════
# c-notation 헬퍼 (c1~c28 → HEX 자동 변환)
# ══════════════════════════════════════════════════════════════════════════
def resolve_colors(colors: List[str]) -> List[str]:
    """
    c1~c28 표기를 HEX로 변환. HEX("#RRGGBB") 그대로도 통과.
    혼용 가능: ["c1", "#50E8F6", "c21"]

    Examples
    --------
    resolve_colors(["c1","c3","c4"])  → ["#FC6AAF","#8950F8","#FED555"]
    resolve_colors(["c1~c6"])         → c1,c2,c3,c4,c5,c6 6색 전체
    resolve_colors(["c1~c21"])        → c1~c21 21색 전체 (레벨100 이하)
    """
    expanded = []
    for c in colors:
        c = str(c).strip()
        # 범위 표기: "c1~c6"
        if '~' in c and c.count('~') == 1:
            a, b = c.split('~')
            a_n = int(a.strip()[1:])
            b_n = int(b.strip()[1:])
            expanded += [f"c{i}" for i in range(a_n, b_n+1)]
        else:
            expanded.append(c)

    resolved = []
    for c in expanded:
        if c.lower().startswith('c') and c[1:].isdigit():
            idx = int(c[1:]) - 1
            if 0 <= idx < len(DEFAULT_PALETTE):
                resolved.append(DEFAULT_PALETTE[idx])
            else:
                raise ValueError(f"'{c}' 범위 초과 (c1~c{len(DEFAULT_PALETTE)})")
        else:
            resolved.append(c)
    return resolved
