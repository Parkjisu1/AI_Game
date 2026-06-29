import sys
sys.path.insert(0, "/home/aimed/.hermes/watcher")
import field_complete_levels as fc

csv_row = {
    "level_number": 1,
    "pkg": 1, "pos": 1, "chapter": 1,
    "purpose_type": "튜토리얼",
    "field_rows": 16, "field_columns": 16,
    "total_cells": 256, "num_colors": 3,
    "rail_capacity": 40,
    "queue_columns": 3, "queue_rows": 8,
    "bl_metaphor": "나선",
    "designer_note": "[Source]\nArt batch xyz\n[Metaphor]\n나선\n[Mode] v42_zone_pipeline",
    "gimmick_hidden": 0, "gimmick_chain": 0, "gimmick_pinata": 0, "gimmick_glass_pipe": 0,
    "gimmick_pin": 0, "gimmick_lock_key": 0, "gimmick_surprise": 0, "gimmick_wall": 0,
    "gimmick_spawner_o": 0, "gimmick_spawner_t": 0, "gimmick_pinata_box": 0,
    "gimmick_ice": 0, "gimmick_frozen_dart": 0, "gimmick_curtain": 0,
}

print("=== single seed ===")
r = fc.complete_one_row(csv_row, n_candidates=1, allow_escalation=False)
print("ok:", r.get("ok"))
print("field_map_source:", r.get("field_map_source"))
print("score:", r.get("score"))
print("balloons:", len(r.get("balloons", [])))
fa = r.get("field_analysis") or {}
print("cluster_dist:", fa.get("cluster_dist"))
print("visual_quality:", fa.get("visual_quality"))
print("zone_pipeline_palette:", r.get("zone_pipeline_palette"))

print()
print("=== multi-seed 5 candidates ===")
r5 = fc.complete_one_row(csv_row, n_candidates=5, allow_escalation=False, keep_all_candidates=True)
print("best score:", r5.get("score"), "source:", r5.get("field_map_source"))
for i, c in enumerate(r5.get("all_candidates", [])):
    cd = (c.get("field_analysis") or {}).get("cluster_dist") or {}
    vq = (c.get("field_analysis") or {}).get("visual_quality") or {}
    score = c.get("score", 0)
    le3 = cd.get("le3_pct")
    gt30 = cd.get("gt30_pct")
    noise = vq.get("noise_score")
    print(f"  seed {i}: score={score:.3f} le3={le3} gt30={gt30} noise={noise}")

# also test different metaphors
print()
print("=== different metaphors, nc=3 ===")
for meta in ["헤링본", "체크 패턴", "동심 사각", "광선 다발"]:
    cr = dict(csv_row)
    cr["bl_metaphor"] = meta
    cr["designer_note"] = f"[Source]\n[Metaphor]\n{meta}\n[Mode] v42_zone_pipeline"
    rr = fc.complete_one_row(cr, n_candidates=1, allow_escalation=False)
    fa = rr.get("field_analysis") or {}
    cd = fa.get("cluster_dist") or {}
    print(f"  [{meta}] source={rr.get('field_map_source')} score={rr.get('score'):.3f} balloons={len(rr.get('balloons',[]))} le3={cd.get('le3_pct')} gt30={cd.get('gt30_pct')}")
