"""셀 정확도 상세 분석 (기믹 포함/제외)
==========================================

기존 batch_all_levels_run/levels/*.json + labels_levels/*.xml 을 이용해
재추론 없이 셀 카운트 정확도 재계산.

지표:
  - cells_pred = hybrid_extractor의 total_cells (content_fieldmap non-zero 개수)
  - cells_gt_pure = GT XML의 셀 bbox 개수 (기믹 제외)
  - cells_gt_incl_gim = GT XML의 모든 bbox 개수 (셀 + 기믹)
  - diff_pure, diff_incl = per-level 차이
  - MAE, MAPE — 두 기준

per-level 비교 + 최악/최선 10개 + 분포 시각화 출력.
"""
from __future__ import annotations
import sys
import json
import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter
import statistics

HERE = Path(__file__).resolve().parent
LEVELS_DIR = HERE / "batch_all_levels_run" / "levels"
XML_DIR = HERE / "labeling" / "labels_levels"
OUT_DIR = HERE / "batch_all_levels_run"

GIMMICK_NAMES = {
    'hidden gimik', 'pinata gimik', 'snake gimik', 'ice gimik',
    'block gimik', 'wall gimik', 'key gimik', 'door gimik',
    'egg gimik', 'cannon gimik',
}


def parse_gt_counts(xml_path: Path) -> tuple[int, int, Counter]:
    """(cells_pure, gimmicks, gimmick_types) 리턴."""
    root = ET.parse(xml_path).getroot()
    cells = gimmicks = 0
    types: Counter = Counter()
    for obj in root.findall("object"):
        name = (obj.find("name").text or "").strip().lower()
        if name in GIMMICK_NAMES:
            gimmicks += 1
            types[name] += 1
        else:
            cells += 1
    return cells, gimmicks, types


def main():
    rows = []
    pure_errs = []
    incl_errs = []
    pure_rel_errs = []
    incl_rel_errs = []

    for xml_path in sorted(XML_DIR.glob("level_*.xml")):
        level = xml_path.stem
        json_path = LEVELS_DIR / f"{level}.json"
        if not json_path.exists():
            continue
        data = json.loads(json_path.read_text(encoding="utf-8"))
        cells_gt_pure, gim_gt, gim_types = parse_gt_counts(xml_path)
        cells_gt_incl = cells_gt_pure + gim_gt
        cells_pred = data.get("total_cells", 0)

        gim_pred = sum(data.get("gimmicks", {}).values())

        # errors (pred vs GT)
        err_pure = cells_pred - cells_gt_pure
        err_incl = cells_pred - cells_gt_incl
        rel_pure = abs(err_pure) / cells_gt_pure if cells_gt_pure > 0 else 0.0
        rel_incl = abs(err_incl) / cells_gt_incl if cells_gt_incl > 0 else 0.0
        pure_errs.append(err_pure)
        incl_errs.append(err_incl)
        pure_rel_errs.append(rel_pure)
        incl_rel_errs.append(rel_incl)

        rows.append({
            "level": level,
            "field_rows": data.get("field_rows", 0),
            "field_columns": data.get("field_columns", 0),
            "cells_pred": cells_pred,
            "cells_gt_pure": cells_gt_pure,
            "cells_gt_incl_gim": cells_gt_incl,
            "diff_pure": err_pure,
            "diff_incl": err_incl,
            "rel_err_pure": round(rel_pure, 4),
            "rel_err_incl": round(rel_incl, 4),
            "gim_pred": gim_pred,
            "gim_gt": gim_gt,
            "gim_types_gt": ",".join(f"{k}:{v}" for k, v in gim_types.items()),
        })

    if not rows:
        print("No rows to analyze.")
        return

    # 부분 라벨 의심 필터링: GT_pure < 50이면 라벨 불완전으로 간주
    LABEL_COMPLETE_THRESHOLD = 50
    well_labeled = [r for r in rows if r["cells_gt_pure"] >= LABEL_COMPLETE_THRESHOLD]
    partial = [r for r in rows if r["cells_gt_pure"] < LABEL_COMPLETE_THRESHOLD]
    print(f"\n라벨 품질 구분:")
    print(f"  완전 라벨 (cells_gt >= {LABEL_COMPLETE_THRESHOLD}): {len(well_labeled)}")
    print(f"  부분 라벨 (cells_gt < {LABEL_COMPLETE_THRESHOLD}):  {len(partial)}")
    if partial:
        print(f"  부분 라벨 예시: {[r['level'] for r in partial[:10]]}")

    # 완전 라벨 subset 지표
    pure_errs_wl = [r["diff_pure"] for r in well_labeled]
    incl_errs_wl = [r["diff_incl"] for r in well_labeled]
    pure_rel_errs_wl = [r["rel_err_pure"] for r in well_labeled]
    incl_rel_errs_wl = [r["rel_err_incl"] for r in well_labeled]

    # 전체 지표 계산
    def stats(errs, rel_errs, label):
        abs_errs = [abs(e) for e in errs]
        pos = sum(1 for e in errs if e > 0)
        neg = sum(1 for e in errs if e < 0)
        zero = sum(1 for e in errs if e == 0)
        print(f"\n=== {label} ===")
        print(f"  MAE (절대 오차 평균): {sum(abs_errs)/len(abs_errs):.2f} cells")
        print(f"  MAPE (상대 오차 평균): {sum(rel_errs)/len(rel_errs)*100:.2f}%")
        print(f"  Median abs error:     {statistics.median(abs_errs):.1f}")
        print(f"  Max abs error:        {max(abs_errs)}")
        print(f"  과탐(pred>GT): {pos}  |  미탐(pred<GT): {neg}  |  정확: {zero}")
        print(f"  평균 편향 (pred-GT): {sum(errs)/len(errs):+.2f}")

    stats(pure_errs, pure_rel_errs, "[전체 204] 기믹 제외 (cells only)")
    stats(incl_errs, incl_rel_errs, "[전체 204] 기믹 포함 (cells + gimmicks)")
    if well_labeled:
        stats(pure_errs_wl, pure_rel_errs_wl, f"[완전 라벨 {len(well_labeled)}] 기믹 제외")
        stats(incl_errs_wl, incl_rel_errs_wl, f"[완전 라벨 {len(well_labeled)}] 기믹 포함")

    # 정확도 분포 (|err| 기준 버킷)
    def bucket(rel_errs):
        buckets = {"≤1%": 0, "1-5%": 0, "5-10%": 0, "10-20%": 0, ">20%": 0}
        for r in rel_errs:
            pct = r * 100
            if pct <= 1: buckets["≤1%"] += 1
            elif pct <= 5: buckets["1-5%"] += 1
            elif pct <= 10: buckets["5-10%"] += 1
            elif pct <= 20: buckets["10-20%"] += 1
            else: buckets[">20%"] += 1
        return buckets

    print(f"\n=== 상대 오차 분포 [전체 {len(rows)}, 기믹 포함] ===")
    for k, v in bucket(incl_rel_errs).items():
        pct = v / len(incl_rel_errs) * 100
        bar = "#" * int(pct / 2)
        print(f"  {k:>6s}: {v:3d} ({pct:5.1f}%) {bar}")

    if well_labeled:
        print(f"\n=== 상대 오차 분포 [완전 라벨 {len(well_labeled)}, 기믹 포함] ===")
        for k, v in bucket(incl_rel_errs_wl).items():
            pct = v / len(incl_rel_errs_wl) * 100
            bar = "#" * int(pct / 2)
            print(f"  {k:>6s}: {v:3d} ({pct:5.1f}%) {bar}")

    # Worst 10 / Best 10 (기믹 포함 기준)
    rows_sorted = sorted(rows, key=lambda r: -abs(r["diff_incl"]))
    print(f"\n=== Worst 10 (기믹 포함 기준) ===")
    print(f"  {'level':<12} {'pred':>6} {'gt_incl':>8} {'diff':>6} {'rel%':>6}  gt_types")
    for r in rows_sorted[:10]:
        print(f"  {r['level']:<12} {r['cells_pred']:>6} {r['cells_gt_incl_gim']:>8} "
              f"{r['diff_incl']:>+6} {r['rel_err_incl']*100:>5.1f}%  {r['gim_types_gt']}")

    rows_best = sorted(rows, key=lambda r: abs(r["diff_incl"]))
    print(f"\n=== Best 10 (기믹 포함 기준) ===")
    print(f"  {'level':<12} {'pred':>6} {'gt_incl':>8} {'diff':>6} {'rel%':>6}")
    for r in rows_best[:10]:
        print(f"  {r['level']:<12} {r['cells_pred']:>6} {r['cells_gt_incl_gim']:>8} "
              f"{r['diff_incl']:>+6} {r['rel_err_incl']*100:>5.1f}%")

    # CSV 저장
    out_csv = OUT_DIR / "cell_accuracy.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nSaved: {out_csv}")


if __name__ == "__main__":
    main()
