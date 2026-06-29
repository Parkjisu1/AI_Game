"""
자연 10-mult 우선 파이프라인.

기존 `variant_pipeline.py`와 달리 — `balance_to_x10` 사후 보정을 **마지막 수단**으로만 사용.
변형(_A~_H)과 확장 seed(최대 300개)를 돌면서:
  1. 생성된 grid 자체가 이미 10-mult인 seed가 있으면 그것 우선 채택
  2. 빈칸 전략 적용만으로 10-mult 달성되면 그것 다음 우선
  3. 두 방법 다 실패할 때만 balance_to_x10 적용
  4. 그래도 실패한 레벨은 리포트에 "10-mult 불가" 로 표시

결과 저장: output_natural/
"""
import json
import random
from pathlib import Path
from collections import Counter

from pixel_pattern_api import (
    generate_pattern, _hex_to_rgb, balance_to_x10
)
from blank_engine import (
    classify_pattern, strategies_for, replace_cells
)
from variant_pipeline import (
    gen_variant, gen_origin_grid, _grid_to_rgb, score_grid,
    save_grid_as_png,
)


def count_fills(grid, bg):
    cnt = Counter(c for row in grid for c in row)
    return {c: n for c, n in cnt.items() if c != bg}


def is_10_mult(grid, bg):
    f = count_fills(grid, bg)
    return bool(f) and all(n % 10 == 0 for n in f.values())


def try_variant_natural(vid, pattern, W, H, n, colors, seed, palette_rgb,
                         extra_seed: int = 0):
    """변형 하나 시도 — balance 없이 10-mult 되는지 + 빈칸 적용해서 되는지 확인.
    반환: dict with 'grid', 'score', 'tier' in {'natural', 'blank', 'balanced'}"""
    try:
        v_seed = seed + extra_seed
        grid = gen_variant(vid, pattern, W, H, n, colors, v_seed)
        if grid is None:
            return None
        rgb_grid = _grid_to_rgb(grid, palette_rgb)
        bg = (255, 255, 255)

        # TIER 1: 원본 grid가 이미 10-mult?
        if is_10_mult(rgb_grid, bg):
            sc = score_grid(rgb_grid, W, H, n_requested=n)
            return {'variant': vid, 'grid': rgb_grid, 'score': sc, 'tier': 'natural'}

        # TIER 2: 빈칸 전략만으로 10-mult?
        ptype = classify_pattern(pattern)
        best_blank = None
        for name, cells in strategies_for(ptype, W, H, bg):
            if not cells:
                continue
            g = replace_cells(rgb_grid, cells, bg)
            if is_10_mult(g, bg):
                sc = score_grid(g, W, H, n_requested=n)
                if best_blank is None or sc['composite'] > best_blank['score']['composite']:
                    best_blank = {'variant': vid, 'grid': g, 'score': sc, 'tier': 'blank'}
        if best_blank is not None:
            return best_blank

        # TIER 3: balance_to_x10까지 적용해야 함 (마지막 수단)
        ptype = classify_pattern(pattern)
        candidates = [rgb_grid] + [
            replace_cells(rgb_grid, cells, bg)
            for name, cells in strategies_for(ptype, W, H, bg) if cells
        ]
        best_bal = None
        for cand in candidates:
            balanced = balance_to_x10(cand, W, H, bg_marker=bg)
            sc = score_grid(balanced, W, H, n_requested=n)
            priority = (0 if sc['is_10_mult'] else 1, -sc['composite'])
            if best_bal is None or priority < best_bal['_pri']:
                best_bal = {
                    'variant': vid, 'grid': balanced, 'score': sc,
                    'tier': 'balanced', '_pri': priority,
                }
        if best_bal:
            best_bal.pop('_pri', None)
        return best_bal
    except Exception:
        return None


def process_level_natural(entry, extended_seeds=300):
    """자연 10-mult 우선 채택."""
    lv = entry['_meta']['level']
    pattern = entry['pattern']
    W, H = entry['width'], entry['height']
    colors = entry['colors']
    n = len(colors)
    seed = entry.get('seed', lv)
    palette_rgb = [_hex_to_rgb(c) for c in colors]

    natural_hits = []     # tier='natural' 후보
    blank_hits = []       # tier='blank' 후보
    balanced_hits = []    # tier='balanced' fallback

    def feed(c):
        if not c: return
        if c['tier'] == 'natural':
            natural_hits.append(c)
        elif c['tier'] == 'blank':
            blank_hits.append(c)
        else:
            balanced_hits.append(c)

    # 1) 기본 A~H
    for vid in 'ABCDEFGH':
        feed(try_variant_natural(vid, pattern, W, H, n, colors, seed, palette_rgb))

    # 2) natural 못 찾았으면 extended seed 탐색
    if not natural_hits:
        for extra in range(1, extended_seeds + 1):
            for vid in ('A', 'B', 'C', 'D', 'E', 'F', 'G', 'H'):
                feed(try_variant_natural(
                    vid, pattern, W, H, n, colors, seed, palette_rgb,
                    extra_seed=extra * 73
                ))
            if natural_hits:  # 찾으면 탐색 멈춤
                break

    # 채택 우선순위: natural > blank > balanced
    pool = natural_hits or blank_hits or balanced_hits
    if not pool:
        return None
    best = max(pool, key=lambda c: c['score']['composite'])
    return {
        'level': lv,
        'chosen_variant': best['variant'],
        'chosen_grid': best['grid'],
        'chosen_score': best['score'],
        'tier': best['tier'],
        'n_natural': len(natural_hits),
        'n_blank': len(blank_hits),
        'n_balanced': len(balanced_hits),
    }


def main():
    cfg = json.load(open('batch_config_levels.json', encoding='utf-8'))
    out_dir = Path('output_natural')
    out_dir.mkdir(exist_ok=True)

    print(f"자연 10-mult 우선 파이프라인 (balance 최소화)")
    print(f"{'Lv':>4} {'패턴':18s} {'채택':>4} {'방식':>9} {'대칭':>5} {'종합':>6} {'색수':>4}")
    print('-' * 70)

    tier_counts = Counter()
    results = {}
    failed = []

    for e in sorted(cfg['patterns'], key=lambda e: e['_meta']['level']):
        lv = e['_meta']['level']
        r = process_level_natural(e)
        if r is None:
            failed.append(lv)
            continue
        s = r['chosen_score']
        tier = r['tier']
        tier_counts[tier] += 1
        pass10 = s['is_10_mult']
        n_col = len(e['colors'])
        pass_mark = 'OK' if pass10 else '--'
        print(f'{lv:>4} {e["pattern"]:18s} _{r["chosen_variant"]:<3} '
              f'{tier:>9s} {pass_mark:>2s} {s["sym_best"]*100:>4.0f}% '
              f'{s["composite"]:>5.1f} {s["n_used"]}/{n_col:d}')
        # 저장
        path = out_dir / f'level_{lv:03d}.png'
        save_grid_as_png(r['chosen_grid'], e['width'], e['height'],
                         path, overwrite=True)
        results[lv] = {
            'variant': r['chosen_variant'],
            'tier': tier,
            'is_10_mult': pass10,
            'sym_best': round(s['sym_best']*100, 1),
            'composite': round(s['composite'], 1),
            'n_natural_hits': r['n_natural'],
            'n_blank_hits': r['n_blank'],
            'n_balanced_hits': r['n_balanced'],
        }

    print()
    print('채택 방식 분포:')
    for t, c in tier_counts.most_common():
        print(f'  {t:>9s}: {c}개')

    # 10-mult 미달 레벨 보고
    not_10 = [lv for lv, r in results.items() if not r['is_10_mult']]
    if not_10:
        print(f'\n⚠ 10-mult 미달 레벨 ({len(not_10)}개): {not_10}')
    else:
        print(f'\n✅ 전체 10-mult 달성')

    if failed:
        print(f'\n❌ 생성 실패 레벨: {failed}')

    # JSON 저장
    json.dump(results, open('natural_results.json', 'w', encoding='utf-8'),
              ensure_ascii=False, indent=2)
    print(f'\n📋 결과: natural_results.json')
    print(f'📂 PNG: {out_dir.absolute()}')


if __name__ == '__main__':
    main()
