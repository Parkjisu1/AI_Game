import os, json, sys
from pymongo import MongoClient
from bson import ObjectId

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ.get("MONGODB_DB", "aigame")]

fc_id = sys.argv[1] if len(sys.argv) > 1 else "6a168661379a1df579153faf"
fc = db["pixelforge_field_complete_jobs"].find_one({"_id": ObjectId(fc_id)})
if not fc:
    print(f"FC job {fc_id} not found"); sys.exit(1)

print(f"=== FC job {fc_id} ===")
print(f"  status       = {fc.get('status')}")
print(f"  preset       = {fc.get('preset')}")
print(f"  csv_source   = {fc.get('csv_source')}")
print(f"  source_pipeline = {fc.get('source_pipeline')}")
print(f"  row_count    = {fc.get('row_count')}")
print(f"  totals       = {fc.get('totals')}")
print(f"  error        = {fc.get('error')}")
print()
print(f"=== csv_rows ({len(fc.get('csv_rows') or [])} rows) ===")
for r in (fc.get("csv_rows") or [])[:3]:
    print(f"  Lv {r.get('level_number')}: cells={r.get('total_cells')} cols={r.get('field_columns')} rows={r.get('field_rows')}"
          f" nc={r.get('num_colors')} purpose={r.get('purpose_type')}"
          f" field_map_len={len(r.get('field_map') or '')}")
    # gimmick fields
    g = {k: v for k, v in r.items() if k.startswith("gimmick_") and v}
    if g: print(f"    gimmicks: {g}")

print(f"\n=== results ===")
for r in (fc.get("results") or [])[:5]:
    print(f"  Lv {r.get('level_number')}: ok={r.get('ok')} score={r.get('score')}")
    print(f"    balloons={len(r.get('balloons') or [])} gimmicks={len(r.get('gimmicks') or [])}")
    print(f"    error={r.get('error')}")
    if r.get("warnings"):
        print(f"    warnings: {r.get('warnings')[:5]}")
    if r.get("validation_failures"):
        print(f"    validation_failures: {r.get('validation_failures')}")
    if r.get("error_trace"):
        print(f"    error_trace (truncated): {(r.get('error_trace') or '')[:800]}")

# field_complete watcher log 확인
log_path = f"/home/aimed/.hermes/logs/field_complete_{fc_id}.log"
print(f"\n=== watcher log: {log_path} ===")
if os.path.exists(log_path):
    with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    # 마지막 50라인
    for line in lines[-50:]:
        print(f"  {line.rstrip()}")
else:
    print("  (not found)")
