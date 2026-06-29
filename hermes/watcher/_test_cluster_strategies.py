import sys
sys.path.insert(0, 'E:/AI/hermes/watcher/pattern_lib')
from blank_engine import strategies_for, classify_pattern, _cluster_strategies

print("=== Cluster strategies for 25x25 ===")
for n, cells in _cluster_strategies(25, 25):
    print(f"  {n}: {len(cells)} cells")

print()
print("=== strategies_for() per pattern type ===")
for pat in ['stripe', 'kaleidoscope', 'rect_grid', 'maze', 'plus_motif', 'wave']:
    pt = classify_pattern(pat)
    strats = strategies_for(pt, 25, 25, 'bg')
    is_single_corner = lambda n: any(c in n for c in ('_TL_', '_TR_', '_BL_', '_BR_'))
    cluster = [n for n, _ in strats if is_single_corner(n)]
    print(f'{pat:15s} ({pt:18s}): total={len(strats)} single-corner={len(cluster)}')
    print(f'  first 4: {[n for n,_ in strats[:4]]}')
