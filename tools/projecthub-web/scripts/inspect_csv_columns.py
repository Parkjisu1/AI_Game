"""CSV 컬럼 인덱스 검증 — bl_metaphor / bl_category 가 실제 몇 번째 컬럼인가."""
import os
import csv
import io
from pymongo import MongoClient

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ.get("MONGODB_DB", "aigame")]
doc = db["pixelforge_csv_versions"].find_one({"is_latest": True}, projection={"csv_text": 1})
csv_text = doc["csv_text"]

# csv.reader 로 진짜 파싱 (quoted 처리 포함)
reader = list(csv.reader(io.StringIO(csv_text)))
print(f"총 라인 수: {len(reader)}")
print(f"\n=== header row [1] (English) — 총 {len(reader[1])} cols ===")
for i, name in enumerate(reader[1]):
    print(f"  [{i:>3}] {name}")

# Lv 3 row 의 값 dump
print("\n=== Lv 3 row values (col idx → English header → 값) ===")
header = reader[1]
target_keys = {"bl_metaphor", "bl_category", "pf_metaphor", "pf_category", "designer_note",
               "field_columns", "field_rows", "num_colors", "level_number",
               "bl 메타포", "bl 카테고리", "pf 메타포", "pf 카테고리"}
for row in reader[2:]:
    if not row or not row[0].strip():
        continue
    if row[0].strip().strip('"') == "3":
        for i, val in enumerate(row):
            h_en = header[i] if i < len(header) else ""
            h_kr = reader[2][i] if i < len(reader[2]) else ""
            kl = (h_en + " " + h_kr).lower()
            if any(t in kl for t in ["metaphor", "category", "메타포", "카테고리", "note", "purpose"]):
                print(f"  [{i:>3}] en='{h_en}' kr='{h_kr}' → val={val!r}"[:200])
        break
