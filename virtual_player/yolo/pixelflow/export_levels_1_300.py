"""1~300 스테이지 정보 일괄 추출 + 통합 JSON/CSV 생성.

입력: batch_all_levels_run/levels/*.json (이미 추출된 per-level 데이터)
출력:
  - export_1_300/levels_1_300.json   (통합 JSON)
  - export_1_300/levels_1_300.csv    (핵심 필드 CSV)
  - export_1_300/missing.txt         (누락된 레벨 번호)
  - export_1_300/summary.json        (집계 통계)
"""
from __future__ import annotations
import json
import csv
from pathlib import Path
from collections import Counter

HERE = Path(__file__).resolve().parent
SRC = HERE / "batch_all_levels_run" / "levels"
OUT = HERE / "export_1_300"
OUT.mkdir(exist_ok=True)

START, END = 1, 300

records = []
missing = []
total_cells = 0
total_gimmicks = 0
gimmick_counter: Counter = Counter()
color_counter: Counter = Counter()

for n in range(START, END + 1):
    fname = f"level_{n:03d}.json"
    fp = SRC / fname
    if not fp.exists():
        missing.append(n)
        continue
    d = json.loads(fp.read_text(encoding="utf-8"))
    cells = d.get("total_cells_yolo", 0)
    gims = d.get("gimmick_positions", [])
    total_cells += cells
    total_gimmicks += len(gims)
    for g in gims:
        gtype = g.get("type") if isinstance(g, dict) else None
        if gtype:
            gimmick_counter[gtype] += 1

    # 색상 분포 집계
    cd = d.get("color_distribution", "")
    for part in cd.split():
        if ":" in part:
            col, cnt = part.split(":")
            try:
                color_counter[col] += int(cnt)
            except ValueError:
                pass

    records.append(d)

# 통합 JSON (전체)
(OUT / "levels_1_300.json").write_text(
    json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
)

# CSV (핵심 필드)
csv_fields = [
    "level_number", "level_id", "field_rows", "field_columns",
    "total_cells", "total_cells_yolo", "total_cells_pixel",
    "grid_confidence", "num_colors", "color_distribution",
    "gimmick_count", "gimmick_types",
]
with (OUT / "levels_1_300.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(csv_fields)
    for d in records:
        gim_positions = d.get("gimmick_positions", [])
        gim_types = sorted({
            g.get("type", "") for g in gim_positions if isinstance(g, dict)
        })
        row = [
            d.get("level_number", ""),
            d.get("level_id", ""),
            d.get("field_rows", 0),
            d.get("field_columns", 0),
            d.get("total_cells", 0),
            d.get("total_cells_yolo", 0),
            d.get("total_cells_pixel", 0),
            f"{d.get('grid_confidence', 0):.3f}",
            d.get("num_colors", 0),
            d.get("color_distribution", ""),
            len(gim_positions),
            "|".join(gim_types),
        ]
        w.writerow(row)

# 누락 목록
(OUT / "missing.txt").write_text(
    "\n".join(str(n) for n in missing), encoding="utf-8"
)

# 집계
summary = {
    "range": [START, END],
    "total_levels_expected": END - START + 1,
    "extracted": len(records),
    "missing_count": len(missing),
    "missing_levels": missing,
    "aggregate": {
        "total_cells": total_cells,
        "total_gimmicks": total_gimmicks,
        "avg_cells_per_level": (
            round(total_cells / len(records), 1) if records else 0
        ),
        "gimmick_type_distribution": dict(gimmick_counter.most_common()),
        "color_distribution_top20": dict(color_counter.most_common(20)),
    },
}
(OUT / "summary.json").write_text(
    json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
)

print(f"Extracted: {len(records)}/{END-START+1}")
print(f"Missing:   {len(missing)}  -> {missing[:20]}")
print(f"Total cells:    {total_cells:,}")
print(f"Total gimmicks: {total_gimmicks:,}")
print(f"\nOutput: {OUT}")
print(f"  - levels_1_300.json  ({len(records)} levels)")
print(f"  - levels_1_300.csv   ({len(records)} rows)")
print(f"  - summary.json")
print(f"  - missing.txt")
