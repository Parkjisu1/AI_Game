"""
패턴별 색상 count 배분 계획.

사후 보정(balance_to_x10) 대신 **사전 계획**으로 10-mult 100% 자연 달성.

핵심 아이디어:
  - 보드사이즈(W×H) + 색상 수(n) + 모티프(pattern)를 모두 본다
  - 각 색에 정확히 몇 셀씩 줄지 **미리** 결정 (모두 10-mult)
  - 제너레이터는 이 목표 count에 맞춰 생성 (target-aware)

함수 시그니처:
  plan_counts(W, H, n, pattern) → {
    'targets': [c1, c2, ..., cn],   # 각 색 목표 셀 수 (10-mult)
    'bg_count': N,                   # 빈칸(배경) 셀 수
    'feasible': bool,                # 이 패턴으로 달성 가능?
    'generator_hints': {...},        # 제너레이터 파라미터 힌트
  }
"""


def plan_counts(W: int, H: int, n: int, pattern: str) -> dict:
    total = W * H
    result = {
        'targets': None, 'bg_count': 0, 'feasible': False,
        'generator_hints': {}, 'notes': '',
    }

    if pattern == 'stripe':
        return _plan_stripe(W, H, n)
    if pattern in ('checkerboard', 'diamond_check'):
        return _plan_checker(W, H, n)
    if pattern == 'rect_grid':
        return _plan_rect_grid(W, H, n)
    if pattern == 'concentric_sq':
        return _plan_concentric_sq(W, H, n)

    # 기타 패턴: 단순 균등 분배 (feasibility 보장 안 함, 힌트만)
    per = (total // (n * 10)) * 10
    targets = [per] * n
    result['targets'] = targets
    result['bg_count'] = total - sum(targets)
    result['feasible'] = per > 0
    result['notes'] = f'generic even split (not pattern-aware)'
    return result


def _plan_stripe(W: int, H: int, n: int) -> dict:
    """vertical stripes. each color = stripe_width × H.
    목표: 각 색 count가 10-mult, 스트라이프 너비 합 ≤ W (나머지는 bg 프레임).

    전략: H가 고정이므로 stripe_width × H ≡ 0 mod 10 이려면
      stripe_width × H mod 10 == 0
    이걸 만족하는 너비 찾고, 색마다 stripe_width 동일하게 n개 배치.
    """
    total = W * H
    # 10 / gcd(H, 10) = 필요한 width_multiple
    from math import gcd
    g = gcd(H, 10)
    width_unit = 10 // g  # stripe_width가 이것의 배수여야 count가 10-mult
    # 모든 색 동일 width로 n개 배치: total width = n × stripe_width ≤ W
    # 최대 stripe_width = W // n  (이것이 width_unit의 배수여야)
    max_per = W // n
    stripe_width = (max_per // width_unit) * width_unit
    if stripe_width < width_unit:
        # 색 수가 많아서 균등 배치 불가
        return {
            'targets': None, 'bg_count': 0, 'feasible': False,
            'generator_hints': {}, 'notes': f'stripe_width<{width_unit} infeasible',
        }
    per_color = stripe_width * H
    bg_cols = W - n * stripe_width
    bg_count = bg_cols * H
    targets = [per_color] * n
    return {
        'targets': targets,
        'bg_count': bg_count,
        'feasible': True,
        'generator_hints': {
            'stripe_width': stripe_width,
            'bg_cols_total': bg_cols,
            'bg_side': 'split',   # 양끝 균등
        },
        'notes': f'width={stripe_width} × {n}색 + bg {bg_cols}cols',
    }


def _plan_checker(W: int, H: int, n: int) -> dict:
    """checkerboard: tile-aligned bg 보장.
    조건:
      - tile_size | W AND tile_size | H (정사각 tile)
      - per_color = k × tile_area, 10x
      - bg_count = bg_tiles × tile_area
    Best: 큰 tile + 작은 bg_tiles."""
    total = W * H
    if total < n * 10:
        return {'targets': None, 'bg_count': 0, 'feasible': False,
                'generator_hints': {}, 'notes': 'per_color=0 infeasible'}

    def divisors(d):
        return [i for i in range(1, d + 1) if d % i == 0]

    from math import gcd
    def lcm(a, b):
        return a * b // gcd(a, b)

    best = None
    common_div = sorted(set(divisors(W)) & set(divisors(H)),
                         reverse=True)
    for ts in common_div:
        ta = ts * ts
        unit = lcm(10, ta)
        if unit > total // n:
            continue
        max_per = (total // n // unit) * unit
        if max_per <= 0:
            continue
        per = max_per
        bg = total - per * n
        if bg < 0 or bg % ta != 0:
            continue
        bg_tiles = bg // ta
        tiles_per_color = per // ta
        # k=1이면 색별 1 tile (단조), k≥2 권장
        if tiles_per_color < 2:
            continue
        sweet_dist = abs(ta - 16)  # 4×4 sweet spot
        score = (sweet_dist, -min(tiles_per_color, 8), bg_tiles)
        if best is None or score < best[0]:
            best = (score, {
                'targets': [per] * n,
                'bg_count': bg,
                'feasible': True,
                'generator_hints': {
                    'tile_size': ts,
                    'bg_distribution': 'cluster' if bg > 0 else None,
                },
                'notes': f'checker per={per}, tile={ts}×{ts}, k={tiles_per_color}, bg_tiles={bg_tiles}',
            })

    if best is None:
        per = (total // (n * 10)) * 10
        if per == 0:
            return {'targets': None, 'bg_count': 0, 'feasible': False,
                    'generator_hints': {}, 'notes': 'per_color=0 infeasible'}
        return {
            'targets': [per] * n,
            'bg_count': total - per * n,
            'feasible': True,
            'generator_hints': {'tile_size': 2, 'bg_distribution': 'corners'},
            'notes': f'checker per={per}, tile=fallback',
        }
    return best[1]


def _plan_rect_grid(W: int, H: int, n: int) -> dict:
    """rect_grid: 색별 직사각 타일. tile-aligned bg 보장.
    조건:
      - tile_w | W AND tile_h | H (격자 정확 align)
      - per_color = k × tile_area (각 색이 정확히 k tiles)
      - per_color = 10 배수 (10x rule)
      → per_color = lcm(10, tile_area) × m, n × per ≤ total
      - bg_count = total - n × per = bg_tiles × tile_area (tile-단위 bg cluster 가능)
    Best: bg_tiles 작고 tile 크고 정사각에 가깝게."""
    total = W * H
    if total < n * 10:
        return {'targets': None, 'bg_count': 0, 'feasible': False,
                'generator_hints': {}, 'notes': 'infeasible (total too small)'}

    def divisors(d):
        return [i for i in range(2, d + 1) if d % i == 0]

    from math import gcd
    def lcm(a, b):
        return a * b // gcd(a, b)

    best = None  # (score_tuple, plan_dict)
    for tw in divisors(W):
        for th in divisors(H):
            ta = tw * th
            unit = lcm(10, ta)
            if unit > total // n:
                continue
            max_per = (total // n // unit) * unit
            if max_per <= 0:
                continue
            per = max_per
            bg = total - per * n
            if bg < 0 or bg % ta != 0:
                continue
            bg_tiles = bg // ta
            tiles_per_color = per // ta
            # 사용자 선호: 색별 ≥ 2 tile (k=1이면 stripe-like, 단조)
            # tile 크기 너무 작아도 (≤4 cells) 노이즈 느낌
            if tiles_per_color < 2:
                continue
            if ta < 4:
                continue
            # 비율 제약: 정사각 ~ 2:1 만 허용 (가는 띠 X)
            ratio = max(tw, th) / max(1, min(tw, th))
            if ratio > 2.0:
                continue
            # score: 정사각 우선 → 적당한 크기 → k≥4 → 작은 bg
            sweet_dist = abs(ta - 25)  # 5x5 sweet
            score = (abs(tw - th), sweet_dist, -min(tiles_per_color, 8), bg_tiles)
            if best is None or score < best[0]:
                best = (score, {
                    'targets': [per] * n,
                    'bg_count': bg,
                    'feasible': True,
                    'generator_hints': {'tile_w': tw, 'tile_h': th},
                    'notes': f'rect_grid per={per}, tile={tw}×{th}, k={tiles_per_color}, bg_tiles={bg_tiles}',
                })

    if best is None:
        # fallback: 옛 방식 (tile-misaligned, 봇이 cell-cluster fallback)
        per = (total // (n * 10)) * 10
        if per == 0:
            return {'targets': None, 'bg_count': 0, 'feasible': False,
                    'generator_hints': {}, 'notes': 'infeasible'}
        return {
            'targets': [per] * n,
            'bg_count': total - per * n,
            'feasible': True,
            'generator_hints': {'tile_w': 4, 'tile_h': 4},
            'notes': f'rect_grid per={per}, tile=fallback (no perfect align)',
        }
    return best[1]


def _plan_concentric_sq(W: int, H: int, n: int) -> dict:
    """concentric_sq: Chebyshev 링. 단순 균등 target=floor10(total/n)으로
    제너레이터에 위임 (BFS로 excess 제거). 기존 ring-rotation 검색은 일부 색이
    0이 되는 쏠림 발생 → 균등 분배 후 사후 보정 방식이 더 안정적."""
    total = W * H
    per = (total // (n * 10)) * 10
    if per == 0:
        return {'targets': None, 'bg_count': 0, 'feasible': False,
                'generator_hints': {}, 'notes': 'per_color=0 infeasible'}
    targets = [per] * n
    bg_count = total - per * n
    # ring 두께 힌트: 그리드 크기에 비례
    mind = min(W, H)
    ring_hint = 3 if mind >= 24 else 2
    return {
        'targets': targets,
        'bg_count': bg_count,
        'feasible': True,
        'generator_hints': {'ring': ring_hint},
        'notes': f'concentric per_color={per}, ring_hint={ring_hint}',
    }


if __name__ == '__main__':
    # 테스트
    import json
    tests = [
        (24, 24, 3, 'stripe'),
        (17, 17, 2, 'stripe'),
        (24, 24, 3, 'checkerboard'),
        (20, 20, 4, 'concentric_sq'),
        (28, 32, 8, 'concentric_sq'),
    ]
    for W, H, n, p in tests:
        r = plan_counts(W, H, n, p)
        print(f'{p:15s} {W}x{H} n={n}:')
        print(f'  feasible={r["feasible"]}, targets={r["targets"]}, bg={r["bg_count"]}')
        print(f'  {r["notes"]}')
        print()
