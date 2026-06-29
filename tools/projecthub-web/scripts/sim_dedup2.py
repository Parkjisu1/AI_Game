import sys
sys.path.insert(0, "/home/aimed/.hermes/watcher")
if "zone_pipeline" in sys.modules: del sys.modules["zone_pipeline"]
if "field_complete_levels" in sys.modules: del sys.modules["field_complete_levels"]
import zone_pipeline as zp
import field_complete_levels as fc

print("=== zone_pipeline 직접 호출 다양성 (lv=50 헤링본 nc=3) ===")
for so in range(5):
    g, pal = zp.generate_field_from_metaphor(rows=20, cols=20, num_colors=3,
                                              metaphor="헤링본", level=50, seed_offset=so)
    from collections import Counter
    cnts = Counter(v for row in g for v in row if v != 0)
    print(f"  seed_offset={so}: palette={pal} cells={dict(sorted(cnts.items()))}")

print()
print("=== complete_one_row multi-seed (lv=50 헤링본 nc=3) ===")
csv_row = {
    "level_number": 50,
    "pkg": 3, "pos": 10, "chapter": 3,
    "purpose_type": "노말",
    "field_rows": 20, "field_columns": 20,
    "total_cells": 400, "num_colors": 3,
    "rail_capacity": 80, "queue_columns": 3, "queue_rows": 8,
    "bl_metaphor": "헤링본",
    "designer_note": "[Metaphor]\n헤링본",
    "gimmick_hidden": 0, "gimmick_chain": 0, "gimmick_pinata": 0, "gimmick_glass_pipe": 0,
    "gimmick_pin": 0, "gimmick_lock_key": 0, "gimmick_surprise": 0, "gimmick_wall": 0,
    "gimmick_spawner_o": 0, "gimmick_spawner_t": 0, "gimmick_pinata_box": 0,
    "gimmick_ice": 0, "gimmick_frozen_dart": 0, "gimmick_curtain": 0,
}

r5 = fc.complete_one_row(csv_row, n_candidates=5, allow_escalation=False, keep_all_candidates=True)
print(f"best source: {r5.get('field_map_source')}")
for i, c in enumerate(r5.get("all_candidates", [])):
    fa = c.get("field_analysis") or {}
    cd = fa.get("cluster_dist") or {}
    pal = c.get("zone_pipeline_palette") or "?"
    print(f"  seed {i}: palette={pal} score={c.get('score',0):.3f} cluster_count={cd.get('cluster_count')} max={cd.get('max_cluster_size')}")
