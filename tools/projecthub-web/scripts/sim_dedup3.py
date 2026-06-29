import sys
sys.path.insert(0, "/home/aimed/.hermes/watcher")
if "zone_pipeline" in sys.modules: del sys.modules["zone_pipeline"]
if "field_complete_levels" in sys.modules: del sys.modules["field_complete_levels"]
import field_complete_levels as fc

csv_row = {
    "level_number": 50, "pkg": 3, "pos": 10, "chapter": 3,
    "purpose_type": "노말", "field_rows": 20, "field_columns": 20,
    "total_cells": 400, "num_colors": 3,
    "rail_capacity": 80, "queue_columns": 3, "queue_rows": 8,
    "bl_metaphor": "헤링본",
    "designer_note": "[Metaphor]\n헤링본",
}
for k in ["gimmick_hidden","gimmick_chain","gimmick_pinata","gimmick_glass_pipe",
          "gimmick_pin","gimmick_lock_key","gimmick_surprise","gimmick_wall",
          "gimmick_spawner_o","gimmick_spawner_t","gimmick_pinata_box",
          "gimmick_ice","gimmick_frozen_dart","gimmick_curtain"]:
    csv_row[k] = 0

# Use normalized csv_row (complete_one_row does this first)
csv_row_n = fc.normalize_csv_row(csv_row)
print("normalized keys present:", [k for k in ['level_number','field_rows','field_columns','num_colors','bl_metaphor','field_map'] if k in csv_row_n])
print("normalized bl_metaphor:", csv_row_n.get('bl_metaphor'))
print()

# Test: directly invoke _complete_one_seed with different seed_offsets
print("=== _complete_one_seed direct call seed_offset 0..4 ===")
seen_fields = []
for so in range(5):
    r = fc._complete_one_seed(csv_row_n, None, False, so)
    fa = r.get("field_analysis") or {}
    cd = fa.get("cluster_dist") or {}
    pal = r.get("zone_pipeline_palette")
    src = r.get("field_map_source")
    print(f"seed_offset={so} src={src} palette={pal} cluster_count={cd.get('cluster_count')} max={cd.get('max_cluster_size')} score={r.get('score')}")
    # Hash of balloons positions+colors to detect identical field
    bls = r.get("balloons") or []
    sig = tuple(sorted((b["row"], b["col"], b["color"]) for b in bls))
    seen_fields.append(hash(sig))
print()
print("balloon signature hashes:", seen_fields)
print("unique hashes:", len(set(seen_fields)))
