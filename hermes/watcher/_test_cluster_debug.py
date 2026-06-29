"""각 패턴의 모든 candidates의 cluster 분포 출력 — multi-cluster에 갇혔는지 확인."""
import sys
sys.path.insert(0, 'E:/AI/hermes/watcher')
sys.path.insert(0, 'E:/AI/hermes/watcher/pattern_lib')

from variant_pipeline import process_level

PATTERNS_BAD = ['chevron', 'kaleidoscope', 'diamond_check', 'i_tetromino', 'wave', 'brick']
PALETTE = ['#FC6AAF', '#50E8F6', '#8950F8', '#FED555', '#73FE66']

for i, pat in enumerate(PATTERNS_BAD):
    entry = {
        '_meta': {'level': i + 1},
        'pattern': pat,
        'width': 25, 'height': 25,
        'colors': PALETTE[:4],
        'seed': 100 + i,
    }
    r = process_level(entry, save_all_variants=False, extended_seeds=5)
    if r is None:
        print(f'{pat}: FAILED'); continue
    print(f'\n=== {pat} (chosen={r["chosen_variant"]} clusters={r["chosen_score"].get("bg_clusters")}) ===')
    for c in r['all_candidates']:
        s = c['score']
        marker = '★' if c['variant'] == r['chosen_variant'] else ' '
        print(f'  {marker} {c["variant"]:>2} 10x={int(s["is_10_mult"])} '
              f'clusters={s.get("bg_clusters",0):>2} sym={s["sym_best"]:.2f} '
              f'scatter={s.get("scatter",0):>2} edge={s.get("full_bg_edge",0)} '
              f'comp={s["composite"]:>7.1f}')
