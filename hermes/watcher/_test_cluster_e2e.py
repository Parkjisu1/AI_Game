"""실제 process_level 호출해서 변화 확인. bg cluster 분포 비교."""
import sys
from collections import Counter
sys.path.insert(0, 'E:/AI/hermes/watcher')
sys.path.insert(0, 'E:/AI/hermes/watcher/pattern_lib')

from variant_pipeline import process_level

# 사용자가 본 패턴 풀 — batch_generate_levels.py COWORK_PATTERNS 13개
PATTERNS = [
    'hex_tile', 'maze', 'brick',
    'rect_grid', 'stripe', 'truchet',
    'argyle', 'wave', 'concentric_sq', 'checkerboard',
    'x_motif', 't_motif', 'plus_motif',
]

PALETTE = ['#FC6AAF', '#50E8F6', '#8950F8', '#FED555', '#73FE66']

results = []
for i, pat in enumerate(PATTERNS):
    entry = {
        '_meta': {'level': i + 1},
        'pattern': pat,
        'width': 25, 'height': 25,
        'colors': PALETTE[:4],
        'seed': 100 + i,
    }
    r = process_level(entry, save_all_variants=False, extended_seeds=5)
    if r is None:
        print(f'{pat:18s} REJECTED (10x+single-cluster 못 찾음)', flush=True)
        continue
    s = r['chosen_score']
    bg_clusters = s.get('bg_clusters', '?')
    is_10 = s['is_10_mult']
    variant = r['chosen_variant']
    results.append((pat, variant, bg_clusters, is_10, s['composite']))
    print(f'{pat:18s} variant={variant} clusters={bg_clusters} 10x={is_10} composite={s["composite"]:.1f}')

print()
print(f'Total: {len(results)} levels')
cluster_dist = Counter(r[2] for r in results)
print(f'Cluster distribution: {dict(sorted(cluster_dist.items()))}')
single_pct = 100 * cluster_dist.get(1, 0) / len(results) if results else 0
zero_pct = 100 * cluster_dist.get(0, 0) / len(results) if results else 0
print(f'  single-cluster (1): {cluster_dist.get(1, 0)} ({single_pct:.0f}%)')
print(f'  no-bg (0):          {cluster_dist.get(0, 0)} ({zero_pct:.0f}%)')
print(f'  multi-cluster (≥2): {sum(v for k, v in cluster_dist.items() if k >= 2)}')
