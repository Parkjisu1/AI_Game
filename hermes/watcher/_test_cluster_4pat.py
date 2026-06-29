"""문제 패턴 4개만 빠르게 검증 — extended_seeds 점진 증가."""
import sys, time
sys.path.insert(0, 'E:/AI/hermes/watcher')
sys.path.insert(0, 'E:/AI/hermes/watcher/pattern_lib')

from variant_pipeline import process_level

PATTERNS = ['chevron', 'kaleidoscope', 'diamond_check', 'i_tetromino']
PALETTE = ['#FC6AAF', '#50E8F6', '#8950F8', '#FED555']

for seeds in [10, 30]:
    print(f'\n=== extended_seeds={seeds} ===', flush=True)
    for i, pat in enumerate(PATTERNS):
        entry = {'_meta': {'level': i+1}, 'pattern': pat, 'width': 25, 'height': 25,
                 'colors': PALETTE, 'seed': 100 + i}
        t0 = time.monotonic()
        r = process_level(entry, save_all_variants=False, extended_seeds=seeds)
        dt = time.monotonic() - t0
        if r is None:
            print(f'  {pat:18s} REJECTED  ({dt:.1f}s)', flush=True)
        else:
            s = r['chosen_score']
            print(f'  {pat:18s} variant={r["chosen_variant"]} clusters={s.get("bg_clusters")} '
                  f'10x={s["is_10_mult"]} comp={s["composite"]:.1f}  ({dt:.1f}s)', flush=True)
