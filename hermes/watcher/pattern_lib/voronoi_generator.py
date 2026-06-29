"""
voronoi_generator.py
====================
보로노이 패턴 생성 + 정제 파이프라인

사용법:
    python3 voronoi_generator.py                      # 기본 실행
    python3 voronoi_generator.py --level 88           # 특정 레벨
    python3 voronoi_generator.py --seed 274 --n 30    # 파라미터 지정

출력:
    level_088_voronoi.png
"""

import math, random, argparse
from PIL import Image
from collections import Counter, defaultdict, deque
from pathlib import Path

# ── 기본 설정 ──────────────────────────────────────────────────────
DEFAULT_PALETTE = {
    'a': (252,106,175),  # c1 핫핑크
    'b': (80, 232,246),  # c2 시안
    'c': (137, 80,248),  # c3 바이올렛
    'd': (254,213, 85),  # c4 옐로
    'e': (115,254,102),  # c5 그린
    'K': (255,255,255),  # 경계선 흰색
}
FILL = list('abcde')


# ══════════════════════════════════════════════════════════════════
# Step 1: 보로노이 셀 생성
# ══════════════════════════════════════════════════════════════════
def generate_voronoi(W, H, n_seeds=30, min_dist=4, seed_val=274):
    rng = random.Random(seed_val)
    seeds = []
    attempts = 0
    while len(seeds) < n_seeds and attempts < 5000:
        sx, sy = rng.randint(0,W-1), rng.randint(0,H-1)
        if not any(math.sqrt((sx-px)**2+(sy-py)**2) < min_dist
                   for px,py in seeds):
            seeds.append((sx, sy))
        attempts += 1
    print(f"  씨앗: {len(seeds)}개 (seed={seed_val})")

    # 유클리드 보로노이
    cell_id = [[0]*W for _ in range(H)]
    for gy in range(H):
        for gx in range(W):
            bd, bi = float('inf'), 0
            for i,(sx,sy) in enumerate(seeds):
                d = (gx-sx)**2+(gy-sy)**2
                if d < bd: bd,bi = d,i
            cell_id[gy][gx] = bi
    return cell_id, seeds


# ══════════════════════════════════════════════════════════════════
# Step 2: 경계선 + 그래프 컬러링
# ══════════════════════════════════════════════════════════════════
def apply_coloring(cell_id, seeds, W, H):
    # 4방향 경계
    is_border = [[False]*W for _ in range(H)]
    for gy in range(H):
        for gx in range(W):
            c = cell_id[gy][gx]
            for dy,dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                ny,nx = gy+dy,gx+dx
                if 0<=nx<W and 0<=ny<H and cell_id[ny][nx]!=c:
                    is_border[gy][gx] = True; break

    # 그래프 컬러링 (인접 셀 다른 색)
    adj = defaultdict(set)
    for gy in range(H):
        for gx in range(W):
            for dy,dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                ny,nx=gy+dy,gx+dx
                if 0<=nx<W and 0<=ny<H:
                    a2,b2=cell_id[gy][gx],cell_id[ny][nx]
                    if a2!=b2: adj[a2].add(b2); adj[b2].add(a2)

    color_assign={}; color_use=Counter()
    for node in sorted(range(len(seeds)), key=lambda n:-len(adj[n])):
        used = {color_assign[nb] for nb in adj[node] if nb in color_assign}
        avail = [c for c in sorted(FILL, key=lambda c:color_use[c])
                 if c not in used]
        chosen = avail[0] if avail else min(
            FILL, key=lambda c:sum(1 for nb in adj[node]
                                   if color_assign.get(nb)==c))
        color_assign[node]=chosen; color_use[chosen]+=1

    grid = [['K' if is_border[gy][gx]
              else color_assign.get(cell_id[gy][gx], FILL[0])
              for gx in range(W)] for gy in range(H)]
    return grid


# ══════════════════════════════════════════════════════════════════
# Step 3: 정제 (반복 적용)
# ══════════════════════════════════════════════════════════════════
def refine(grid, W, H, verbose=True):

    def nbrs4(gx, gy):
        return [grid[gy+dy][gx+dx]
                for dy,dx in [(-1,0),(1,0),(0,-1),(0,1)]
                if 0<=gx+dx<W and 0<=gy+dy<H]

    # 3-1. 작은 고립 섬 제거 (3칸 이하)
    visited=[[False]*W for _ in range(H)]; island=0
    for sy in range(H):
        for sx in range(W):
            if visited[sy][sx] or grid[sy][sx]=='K': continue
            color=grid[sy][sx]
            q=deque([(sx,sy)]); visited[sy][sx]=True; region=[(sx,sy)]
            while q:
                cx,cy=q.popleft()
                for dy,dx in [(-1,0),(1,0),(0,-1),(0,1)]:
                    ny,nx=cy+dy,cx+dx
                    if 0<=nx<W and 0<=ny<H and not visited[ny][nx] and grid[ny][nx]==color:
                        visited[ny][nx]=True; q.append((nx,ny)); region.append((nx,ny))
            if len(region)<=3:
                adj=Counter(c for rx,ry in region for c in nbrs4(rx,ry)
                            if c!='K' and c!=color)
                if adj:
                    best=adj.most_common(1)[0][0]
                    for rx,ry in region: grid[ry][rx]=best
                    island+=len(region)
    if verbose: print(f"  고립 섬 제거: {island}칸")

    # 3-2. 볼록 코너 제거
    CORNER_DIRS=[
        ((-1,0),(0,1),(-1,1)),((-1,0),(0,-1),(-1,-1)),
        ((1,0),(0,1),(1,1)),  ((1,0),(0,-1),(1,-1)),
    ]
    corner=0; changed=True
    while changed:
        changed=False
        for gy in range(H):
            for gx in range(W):
                if grid[gy][gx]=='K': continue
                c=grid[gy][gx]
                for (dy1,dx1),(dy2,dx2),(dyd,dxd) in CORNER_DIRS:
                    ny1,nx1=gy+dy1,gx+dx1; ny2,nx2=gy+dy2,gx+dx2
                    nyd,nxd=gy+dyd,gx+dxd
                    if not(0<=nx1<W and 0<=ny1<H and 0<=nx2<W
                           and 0<=ny2<H and 0<=nxd<W and 0<=nyd<H): continue
                    if (grid[ny1][nx1]=='K' and grid[ny2][nx2]=='K'
                            and grid[nyd][nxd]!='K' and grid[nyd][nxd]!=c):
                        grid[gy][gx]='K'; corner+=1; changed=True; break
    if verbose: print(f"  볼록 코너: {corner}개")

    # 3-3. 완전 고립 K (4면 모두 같은 색) → 채우기
    dent=0
    for gy in range(H):
        for gx in range(W):
            if grid[gy][gx]!='K': continue
            nb=nbrs4(gx,gy)
            non_K=[n for n in nb if n!='K']
            if len(non_K)==4 and len(set(non_K))==1:
                grid[gy][gx]=non_K[0]; dent+=1
    if verbose: print(f"  고립 K 채우기: {dent}개")

    # 3-4. 대각 침범 수정
    diag=0; changed=True
    while changed:
        changed=False
        for gy in range(H-1):
            for gx in range(W-1):
                tl,tr=grid[gy][gx],grid[gy][gx+1]
                bl,br=grid[gy+1][gx],grid[gy+1][gx+1]
                if tl!='K' and br!='K' and tl!=br and tr!='K' and bl!='K':
                    grid[gy][gx+1]='K'; diag+=1; changed=True
                if tr!='K' and bl!='K' and tr!=bl and tl!='K' and br!='K':
                    grid[gy+1][gx]='K'; diag+=1; changed=True
    if verbose: print(f"  대각 수정: {diag}개")

    return grid


# ══════════════════════════════════════════════════════════════════
# Step 4: ×10 밸런싱
# ══════════════════════════════════════════════════════════════════
def balance_x10(grid, W, H, verbose=True):
    cx, cy = (W-1)/2.0, (H-1)/2.0
    cur = Counter(c for row in grid for c in row if c!='K')
    targets = {k:(v//10)*10 for k,v in cur.items()}

    def bK(x, y):
        return sum(1 for dy,dx in [(-1,0),(1,0),(0,-1),(0,1)]
                   if 0<=x+dx<W and 0<=y+dy<H and grid[y+dy][x+dx]=='K')

    for color in FILL:
        while cur.get(color,0) > targets.get(color,0):
            cands = sorted(
                [(math.sqrt((x-cx)**2+(y-cy)**2), -bK(x,y), x, y)
                 for y in range(H) for x in range(W) if grid[y][x]==color],
                reverse=True)
            if not cands: break
            _,_,bx,by = cands[0]
            grid[by][bx]='K'; cur[color]-=1

    fc = Counter(c for row in grid for c in row if c!='K')
    K_n = W*H - sum(fc.values())
    ok = all(v%10==0 for v in fc.values())
    if verbose:
        print(f"  K: {K_n}칸 | ×10: {'✓' if ok else '✗'}")
        for k,v in sorted(fc.items()):
            name={'a':'핫핑크','b':'시안','c':'바이올렛',
                  'd':'옐로','e':'그린'}[k]
            print(f"    {name}: {v}칸 {'✓' if v%10==0 else '✗'}")
    return grid, fc


# ══════════════════════════════════════════════════════════════════
# 렌더링
# ══════════════════════════════════════════════════════════════════
def render(grid, W, H, block=30, palette=None, out_path='output.png'):
    if palette is None: palette = DEFAULT_PALETTE
    img = Image.new('RGB', (W*block, H*block))
    px = img.load()
    for gy in range(H):
        for gx in range(W):
            col = palette[grid[gy][gx]]
            for py in range(block):
                for ppx in range(block):
                    px[gx*block+ppx, gy*block+py] = col
    img.save(out_path)
    print(f"  저장: {out_path}")


# ══════════════════════════════════════════════════════════════════
# 검증 리포트
# ══════════════════════════════════════════════════════════════════
def validate(grid, W, H, fc):
    print("\n=== 검증 ===")
    # 대각 침범
    diag = sum(
        1 for gy in range(H-1) for gx in range(W-1)
        for (ay,ax),(by2,bx) in [((gy,gx),(gy+1,gx+1)),((gy+1,gx),(gy,gx+1))]
        if grid[ay][ax]!='K' and grid[by2][bx]!='K'
        and grid[ay][ax]!=grid[by2][bx]
    )
    print(f"  대각 침범: {diag}쌍 {'✓' if diag==0 else '✗'}")

    # 직접 인접 (다른 색 K없이)
    direct = sum(
        1 for gy in range(H) for gx in range(W)
        if grid[gy][gx]!='K'
        for dy,dx in [(-1,0),(0,-1)]
        if 0<=gx+dx<W and 0<=gy+dy<H
        and grid[gy+dy][gx+dx]!='K'
        and grid[gy+dy][gx+dx]!=grid[gy][gx]
    )
    print(f"  직접 인접: {direct}쌍 {'✓' if direct==0 else '✗'}")

    # ×10
    ok = all(v%10==0 for v in fc.values())
    print(f"  ×10: {'✓' if ok else '✗'}")
    return diag==0 and direct==0 and ok


# ══════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--level',  type=int, default=88)
    parser.add_argument('--width',  type=int, default=32)
    parser.add_argument('--height', type=int, default=40)
    parser.add_argument('--block',  type=int, default=30)
    parser.add_argument('--seed',   type=int, default=274)
    parser.add_argument('--n',      type=int, default=30,
                        help='씨앗 수')
    parser.add_argument('--out',    type=str, default='./output_patterns')
    args = parser.parse_args()

    W, H = args.width, args.height
    out_dir = Path(args.out); out_dir.mkdir(parents=True, exist_ok=True)
    out_path = str(out_dir / f"level_{args.level:03d}.png")

    print(f"\n{'='*50}")
    print(f"Lv{args.level} 보로노이 생성: {W}x{H} seed={args.seed} n={args.n}")
    print(f"{'='*50}")

    print("\n[1] 보로노이 생성")
    cell_id, seeds = generate_voronoi(W, H, n_seeds=args.n,
                                      seed_val=args.seed)

    print("\n[2] 컬러링")
    grid = apply_coloring(cell_id, seeds, W, H)

    print("\n[3] 정제")
    grid = refine(grid, W, H)

    print("\n[4] ×10 밸런싱")
    grid, fc = balance_x10(grid, W, H)

    print("\n[5] 렌더링")
    render(grid, W, H, block=args.block, out_path=out_path)

    validate(grid, W, H, fc)
    print(f"\n완료: {out_path}\n")


if __name__ == '__main__':
    main()
