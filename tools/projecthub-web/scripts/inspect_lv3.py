import os
from pymongo import MongoClient

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ.get("MONGODB_DB", "aigame")]

doc = db["pixelforge_levels"].find_one({"level_number": 3})
print("=== Lv 3 pixelforge_levels ===")
if doc:
    for k in sorted(doc.keys()):
        v = doc[k]
        kl = k.lower()
        if any(x in kl for x in ["meta", "categor", "tier", "motif", "pattern", "style", "theme", "purpose", "designer"]):
            sv = repr(v)
            print(f"  {k} = {sv[:200]}")
else:
    print("  (no doc)")

csv = db["pixelforge_csv_versions"].find_one(
    {"is_latest": True},
    projection={"csv_text": 1, "version": 1, "label": 1, "delimiter": 1, "header_rows": 1, "row_count": 1},
)
if csv:
    ver = csv.get("version")
    lbl = csv.get("label")
    print(f"\n=== latest CSV {ver} '{lbl}' ===")
    print(f"  delimiter={csv.get('delimiter')!r} header={csv.get('header_rows')} rows={csv.get('row_count')}")
    lines = csv["csv_text"].split("\n")
    print("--- first 4 lines (header) ---")
    for i, ln in enumerate(lines[:4]):
        print(f"  [{i}] {ln[:400]}")
    print("--- Lv 3 row ---")
    for ln in lines[4:]:
        first = ln.split(",", 1)[0].strip().strip('"')
        if first == "3":
            print(f"  {ln[:800]}")
            break
else:
    print("\n(no latest CSV)")
