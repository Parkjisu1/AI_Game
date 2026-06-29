import os, json
from pymongo import MongoClient
from bson import ObjectId
c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ.get("MONGODB_DB", "aigame")]

sess = db["pixelforge_pipeline_sessions"].find_one({"_id": ObjectId("6a167beee63453fc3198f7c2")})
tl = sess.get("target_levels") or []
print(f"session target_levels (first 30): {tl[:30]}")
print(f"  total count: {len(tl)}")

job = db["pixelforge_v43_jobs"].find_one({"_id": ObjectId("6a167beee63453fc3198f7c3")})
tl2 = job.get("target_levels") or []
print(f"v43 job target_levels (first 30): {tl2[:30]}")

with open("/home/aimed/.hermes/v43_out/6a167beee63453fc3198f7c3/evaluation.json") as f:
    d = json.load(f)
processed = sorted([r["level"] for r in d])
print(f"processed levels (from eval.json): {processed}")
print(f"  count: {len(processed)}")

target = set(tl)
got = set(processed)
missing = sorted(target - got)
print(f"\nMISSING from output (first 30): {missing[:30]}")
print(f"  count: {len(missing)}")

# What rows does the CSV have for missing levels?
import csv
csv_path = job.get("csv_path")
print(f"\nCSV path: {csv_path}")
if csv_path and os.path.exists(csv_path):
    with open(csv_path, "r", encoding="utf-8") as f:
        rd = list(csv.reader(f))
    lv_col_rows = {}
    for row in rd[3:]:
        if row and row[0].strip().isdigit():
            lv = int(row[0].strip())
            lv_col_rows[lv] = row
    csv_lvs = sorted(lv_col_rows.keys())
    print(f"CSV has rows for levels: {csv_lvs[:15]} ... ({len(csv_lvs)} total)")
    # For first 5 missing, dump their CSV row category
    for lv in missing[:8]:
        if lv in lv_col_rows:
            r = lv_col_rows[lv]
            bl_meta = r[51] if len(r) > 51 else "??"
            bl_cat = r[52] if len(r) > 52 else "??"
            print(f"  Lv {lv}: bl_meta={bl_meta!r} bl_cat={bl_cat!r}")
        else:
            print(f"  Lv {lv}: NOT IN CSV")
