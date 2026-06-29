"""세션의 FC job 의 results 기반으로 export ZIP 안의 JSON 형태를 재현해 Unity 임포터 친화성 진단."""
import os, json, sys
from pymongo import MongoClient
from bson import ObjectId

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ.get("MONGODB_DB", "aigame")]

# 가장 최근 FC job (해당 session 의)
sess_id = sys.argv[1] if len(sys.argv) > 1 else "6a168358e63453fc3198f7c4"
sess = db["pixelforge_pipeline_sessions"].find_one({"_id": ObjectId(sess_id)})
fc_id = (sess.get("field_complete_job") or {}).get("job_id")
if not fc_id:
    print("No FC job linked"); sys.exit(1)

fc = db["pixelforge_field_complete_jobs"].find_one({"_id": ObjectId(fc_id)})
results = fc.get("results") or []
csv_rows = fc.get("csv_rows") or []
print(f"=== FC {fc_id} ===")
print(f"  totals: {fc.get('totals')}")
print(f"  csv_rows: {len(csv_rows)}")
print(f"  results: {len(results)}")

ok_results = [r for r in results if r.get("ok") and r.get("balloons")]
print(f"  ok results with balloons: {len(ok_results)}")
if not ok_results:
    print("\n→ Export ZIP 안에 들어갈 JSON 0건! Unity import 결과는 빈 폴더라 '안 보임'.")
    print("  원인: FC 단계에서 ok=True 인 결과가 없어서 export 가 만들 JSON 자체가 없음.")
    sys.exit(0)

# 첫 ok 결과로 JSON 시뮬레이션
r = ok_results[0]
lv = r["level_number"]
csv_by_lv = {c.get("level_number"): c for c in csv_rows}
csv_row = csv_by_lv.get(lv, {})

# export route 의 toBalloonFlowFormat 시뮬
rows = int(csv_row.get("field_rows") or 0)
cols = int(csv_row.get("field_columns") or 0)
balloons = r.get("balloons") or []
gimmicks = r.get("gimmicks") or []

# buildFieldMap
grid = [[".." for _ in range(cols)] for _ in range(rows)]
for b in balloons:
    rr, cc, color = b.get("row"), b.get("col"), b.get("color")
    if rr is not None and cc is not None and color is not None and 0 <= rr < rows and 0 <= cc < cols:
        grid[rr][cc] = f"{color:02d}"
# 기믹은 빈 cell에 표시
for g in gimmicks:
    cells = g.get("cells") or []
    if not cells and g.get("row") is not None and g.get("col") is not None:
        cells = [[g["row"], g["col"]]]
    for c in cells:
        if not isinstance(c, list) or len(c) < 2: continue
        rr, cc = c[0], c[1]
        if 0 <= rr < rows and 0 <= cc < cols and grid[rr][cc] == "..":
            if g.get("type") == "Hidden_Balloon" and g.get("hidden_color") is not None:
                grid[rr][cc] = f"{g['hidden_color']:02d}"
            elif g.get("color") is not None:
                grid[rr][cc] = f"{g['color']:02d}"
field_map_text = "\n".join(" ".join(r) for r in grid)

fa = r.get("field_analysis") or {}
color_darts = fa.get("color_darts") or {}
color_dist_str = " ".join(f"{k}:{v}" for k, v in color_darts.items())

pkg = int(csv_row.get("pkg") or 0) or ((lv-1)//20 + 1)
pos = int(csv_row.get("pos") or 0) or ((lv-1) % 20 + 1)

bf = {
    "levelId": lv,
    "packageId": pkg,
    "positionInPackage": pos,
    "level_number": lv,
    "level_id": f"BF_{lv:03d}",
    "pkg": pkg,
    "pos": pos,
    "chapter": int(csv_row.get("chapter") or 0) or pkg,
    "purpose_type": r.get("normalized_purpose") or csv_row.get("purpose_type") or "normal",
    "target_cr": 85,
    "target_attempts": 1.5,
    "num_colors": int(csv_row.get("num_colors") or 0),
    "color_distribution": color_dist_str,
    "field_rows": rows,
    "field_columns": cols,
    "total_cells": int(csv_row.get("total_cells") or 0) or len(balloons),
    "rail_capacity": int(csv_row.get("rail_capacity") or 0),
    "queue_columns": int(csv_row.get("queue_columns") or 0),
    "queue_rows": int(csv_row.get("queue_rows") or 0),
    "designer_note": (
        f"[Source]\nfield-complete v1.1 algorithm\nscore={r.get('score'):.4f}\n\n"
        f"[Accuracy]\nfield_complete_score={r.get('score'):.4f}\nmetaphor=?\nauto_color_dist=?\n\n"
        f"[FieldMap]\n{field_map_text}"
    ),
    "pixel_art_source": "",
}

# Unity 임포터 진단
print(f"\n=== Simulated JSON for Lv {lv} ===")
diag = []
# Path 1: LevelEpisode — JSON 에 "levels" 키 포함?
has_levels_key = '"levels"' in json.dumps(bf)
diag.append(f"  LevelEpisode path  : contains '\"levels\"' = {has_levels_key} → {'TRIED' if has_levels_key else 'SKIPPED'}")
# Path 2: LevelConfig — JSON 에 "levelId" 키 + (rail / gridRows / gridCols / balloons) 필요
has_levelId_key = '"levelId"' in json.dumps(bf)
has_rail = "rail" in bf and bf["rail"] is not None
has_gridRows = "gridRows" in bf and (bf.get("gridRows") or 0) > 0
has_gridCols = "gridCols" in bf and (bf.get("gridCols") or 0) > 0
has_balloons = "balloons" in bf and bf.get("balloons")
diag.append(f"  LevelConfig path   : contains '\"levelId\"' = {has_levelId_key}")
diag.append(f"      rail={has_rail} gridRows={has_gridRows} gridCols={has_gridCols} balloons={has_balloons}")
diag.append(f"      → all camelCase missing 이라 LevelConfig 진입 후 즉시 fail-back to Legacy")
# Path 3: Legacy JsonLevelData — field_rows > 0 필요
diag.append(f"  Legacy JsonLevel   : field_rows = {bf['field_rows']} > 0 = {bf['field_rows'] > 0}")
diag.append(f"      → entry.json.field_rows = {bf['field_rows']}, entry.error = {'(없음)' if bf['field_rows'] > 0 else 'OK'}")

# FieldMap 파싱
field_map_index = bf["designer_note"].find("[FieldMap]")
diag.append(f"  designer_note '[FieldMap]' at index {field_map_index}")
if field_map_index >= 0:
    after = bf["designer_note"][field_map_index + len("[FieldMap]"):]
    lines_after = [l.strip() for l in after.split("\n") if l.strip()]
    diag.append(f"  FieldMap 라인 수 = {len(lines_after)} (예상 rows={rows})")
    if lines_after:
        first_tokens = lines_after[0].split(" ")
        diag.append(f"  첫 줄 토큰 수 = {len(first_tokens)} (예상 cols={cols})")
        diag.append(f"  첫 줄 샘플 = {lines_after[0][:80]}")

for d in diag: print(d)

# 풍선 개수
non_empty = sum(1 for row in grid for cell in row if cell != "..")
diag2 = f"  total non-empty cells in field_map = {non_empty}  (balloons in result: {len(balloons)})"
print(diag2)

# JSON 파일 저장
out_path = "/tmp/sample_lv1_export.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(bf, f, indent=2, ensure_ascii=False)
print(f"\n→ sample written to {out_path} ({os.path.getsize(out_path)} bytes)")
