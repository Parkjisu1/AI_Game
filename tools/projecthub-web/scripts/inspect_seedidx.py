import json
d = json.load(open("/home/aimed/.hermes/v43_out/6a167beee63453fc3198f7c3/evaluation.json"))
print("=== seed_idx, effective_metaphor of final_candidates ===")
for r in d[:6]:
    print(f"Lv {r['level']} (anchor={r['metaphor']}):")
    for i, c in enumerate(r.get('final_candidates', [])):
        si = c.get('seed_idx')
        em = c.get('effective_metaphor')
        sc = c.get('total_score')
        print(f"  [{i}] seed_idx={si} meta={em!r} score={sc}")
