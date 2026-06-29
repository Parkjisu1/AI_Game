"""chevron 1개만 — seed 단계별 시간 측정으로 병목 찾기."""
import sys, time
sys.path.insert(0, 'E:/AI/hermes/watcher')
sys.path.insert(0, 'E:/AI/hermes/watcher/pattern_lib')

from variant_pipeline import process_level

PALETTE = ['#FC6AAF', '#50E8F6', '#8950F8', '#FED555']

for seeds in [0, 1, 3, 5]:
    entry = {'_meta': {'level': 1}, 'pattern': 'chevron', 'width': 25, 'height': 25,
             'colors': PALETTE, 'seed': 100}
    t0 = time.monotonic()
    r = process_level(entry, save_all_variants=False, extended_seeds=seeds)
    dt = time.monotonic() - t0
    if r is None:
        print(f'  seeds={seeds:>2}: REJECTED  ({dt:.1f}s)', flush=True)
    else:
        s = r['chosen_score']
        print(f'  seeds={seeds:>2}: variant={r["chosen_variant"]} '
              f'clusters={s.get("bg_clusters")} 10x={s["is_10_mult"]} '
              f'comp={s["composite"]:.1f} candidates={len(r["all_candidates"])}  ({dt:.1f}s)',
              flush=True)
