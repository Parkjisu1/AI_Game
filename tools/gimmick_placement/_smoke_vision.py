"""라이브 vision 스모크: Lv34 완성보드 → analyze_board_vision → resolve_regions."""
import json
import os

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/aimed/.hermes/watcher/.env")
import gimmick_placement as gp
import vision as vz

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ.get("MONGODB_DB", "aigame")]
best = None
for j in db.pixelforge_field_complete_jobs.find({"status": "done"}, {"results": 1, "finished_at": 1}):
    for r in j.get("results", []):
        if r.get("level_number") == 34 and r.get("ok") and r.get("balloons"):
            if best is None or j.get("finished_at", "") > best[0]:
                best = (j.get("finished_at", ""), r)
r = best[1]
fa = r.get("field_analysis", {})
board = {"field_rows": fa.get("field_rows"), "field_columns": fa.get("field_columns"),
         "balloons": r["balloons"], "gimmicks": []}
print("board", board["field_columns"], "x", board["field_rows"], "balloons", len(board["balloons"]))

v = vz.analyze_board_vision(board)
if v and v.get("_vision_error"):
    print("VISION ERROR:", v["_vision_error"])
    raise SystemExit(1)
print("\n=== vision ===")
print("category:", v.get("category"), "| metaphor:", v.get("metaphor"), "| complexity:", v.get("metaphor_complexity"))
print("motif_bbox:", v.get("motif_bbox"), "| bg:", v.get("background_color"), "| main_colors:", v.get("motif_main_colors"))
print("regions:", {k: (val.get("exists"), val.get("bbox")) for k, val in (v.get("regions") or {}).items()})
print("empty_regions:", [(e.get("side"), e.get("bbox")) for e in (v.get("empty_regions") or [])])

regions = vz.resolve_regions_from_vision(v, board)
print("\n=== resolved regions (휴리스틱 형식) ===")
for reg in regions:
    print(f"  {reg.get('label'):<22} color=c{reg['color']} size={reg['size']} bbox={reg['bbox_w']}x{reg['bbox_h']} empty={reg.get('is_empty', False)}")

# 비교: 휴리스틱 detect_regions 상위 3
grid, W, H, bg = gp.board_to_grid(board)
print("\n=== 휴리스틱 detect_regions 상위 3 ===")
for reg in gp.detect_regions(grid, bg)[:3]:
    print(f"  c{reg['color']} size={reg['size']} bbox={reg['bbox_w']}x{reg['bbox_h']}")
print("\nSMOKE OK" if regions else "\nVISION RETURNED BUT NO REGIONS MAPPED (fallback to heuristic)")
