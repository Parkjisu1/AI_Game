"""Worst 20% cell count cases 원인 분석
==========================================

가설 검증:
  H1: 큰 보드일수록 YOLO가 놓침 (max_det=5000 여유 있지만 작은 셀 탐지 어려움)
  H2: 색상 수 많으면 셀 경계 모호 → 탐지 실패
  H3: 특정 기믹 (pinata, snake) 있으면 셀로 오탐
  H4: 보드 탐지 실패로 크롭 영역 밖 → 셀 카운트 왜곡
  H5: 이미지 자체가 부분 라벨 (GT 불완전)

출력:
  - worst/best subset 특성 비교 (평균 보드 크기, 색상 수, 기믹 수 등)
  - worst 30 레벨의 상세 정보
  - best 30과의 대조
  - 가설별 판정
"""
from __future__ import annotations
import json
import csv
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter
import statistics

HERE = Path(__file__).resolve().parent
LEVELS_DIR = HERE / "batch_all_levels_run" / "levels"
XML_DIR = HERE / "labeling" / "labels_levels"
CSV_PATH = HERE / "batch_all_levels_run" / "cell_accuracy.csv"

GIMMICK_NAMES = {
    'hidden gimik', 'pinata gimik', 'snake gimik', 'ice gimik',
    'block gimik', 'wall gimik', 'key gimik', 'door gimik',
    'egg gimik', 'cannon gimik',
}


def load_rows():
    rows = []
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                r["rel_err_incl"] = float(r["rel_err_incl"])
                r["cells_gt_pure"] = int(r["cells_gt_pure"])
                r["cells_gt_incl_gim"] = int(r["cells_gt_incl_gim"])
                r["cells_pred"] = int(r["cells_pred"])
                r["field_rows"] = int(r["field_rows"])
                r["field_columns"] = int(r["field_columns"])
                r["diff_incl"] = int(r["diff_incl"])
                r["gim_pred"] = int(r["gim_pred"])
                r["gim_gt"] = int(r["gim_gt"])
                rows.append(r)
            except (KeyError, ValueError):
                continue
    return rows


def get_level_data(level: str) -> dict:
    p = LEVELS_DIR / f"{level}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    rows = load_rows()

    # 완전 라벨만 사용 (cells_gt_pure >= 50)
    well_labeled = [r for r in rows if r["cells_gt_pure"] >= 50]

    # 오차 구간별 서브셋
    worst = sorted(
        [r for r in well_labeled if r["rel_err_incl"] > 0.2],
        key=lambda r: -r["rel_err_incl"],
    )
    good = [r for r in well_labeled if r["rel_err_incl"] <= 0.05]
    mid = [r for r in well_labeled if 0.05 < r["rel_err_incl"] <= 0.2]

    print(f"Subsets (완전 라벨 {len(well_labeled)}):")
    print(f"  ≤5%:  {len(good):3d}")
    print(f"  5-20%: {len(mid):3d}")
    print(f"  >20%: {len(worst):3d}  ← Worst 분석 대상\n")

    # 통계 비교: 평균 보드 크기, 색상 수, 기믹 수
    def enrich(row_subset):
        sizes, colors, gim_pred_counts, gim_gt_counts, cells_pred_list = [], [], [], [], []
        for r in row_subset:
            ld = get_level_data(r["level"])
            if not ld:
                continue
            sizes.append(r["field_rows"] * r["field_columns"])
            colors.append(ld.get("num_colors", 0))
            gim_pred_counts.append(r["gim_pred"])
            gim_gt_counts.append(r["gim_gt"])
            cells_pred_list.append(r["cells_pred"])
        return {
            "n": len(sizes),
            "avg_board_size": statistics.mean(sizes) if sizes else 0,
            "median_board_size": statistics.median(sizes) if sizes else 0,
            "avg_num_colors": statistics.mean(colors) if colors else 0,
            "avg_gim_pred": statistics.mean(gim_pred_counts) if gim_pred_counts else 0,
            "avg_gim_gt": statistics.mean(gim_gt_counts) if gim_gt_counts else 0,
            "avg_cells_pred": statistics.mean(cells_pred_list) if cells_pred_list else 0,
        }

    stats_good = enrich(good)
    stats_mid = enrich(mid)
    stats_worst = enrich(worst)

    print("=== Subset 특성 비교 ===")
    print(f"{'metric':<22} {'≤5%':>12} {'5-20%':>12} {'>20%':>12}")
    for k in ["n", "avg_board_size", "median_board_size", "avg_num_colors",
              "avg_gim_pred", "avg_gim_gt", "avg_cells_pred"]:
        gv, mv, wv = stats_good[k], stats_mid[k], stats_worst[k]
        print(f"{k:<22} {gv:>12.1f} {mv:>12.1f} {wv:>12.1f}")

    # H1: 보드 크기 상관관계
    print("\n=== H1: 보드 크기와 오차 ===")
    print(f"  ≤5% 평균 보드: {stats_good['avg_board_size']:.0f} cells")
    print(f"  >20% 평균 보드: {stats_worst['avg_board_size']:.0f} cells")
    ratio = stats_worst['avg_board_size'] / max(1, stats_good['avg_board_size'])
    print(f"  비율: worst가 {ratio:.2f}배 "
          f"{'(큰 보드에서 실패 ← H1 지지)' if ratio > 1.3 else '(차이 적음 ← H1 약함)'}")

    # H2: 색상 수 상관관계
    print("\n=== H2: 색상 수와 오차 ===")
    print(f"  ≤5% 평균 색상 수: {stats_good['avg_num_colors']:.1f}")
    print(f"  >20% 평균 색상 수: {stats_worst['avg_num_colors']:.1f}")

    # H3: 기믹 수 상관관계
    print("\n=== H3: 기믹 수와 오차 ===")
    print(f"  ≤5% 평균 기믹: {stats_good['avg_gim_pred']:.1f}")
    print(f"  >20% 평균 기믹: {stats_worst['avg_gim_pred']:.1f}")

    # Worst 30 상세
    print("\n=== Worst 30 상세 ===")
    print(f"{'level':<12} {'rxc':>7} {'pred':>6} {'gt_incl':>8} {'rel%':>6} "
          f"{'n_col':>5} {'gim_p/g':>8}  gt_types")
    for r in worst[:30]:
        ld = get_level_data(r["level"])
        nc = ld.get("num_colors", 0) if ld else 0
        sz = f"{r['field_rows']}x{r['field_columns']}"
        print(f"  {r['level']:<11} {sz:>7} {r['cells_pred']:>6} {r['cells_gt_incl_gim']:>8} "
              f"{r['rel_err_incl']*100:>5.1f}% {nc:>5} "
              f"{r['gim_pred']:>3}/{r['gim_gt']:<3}  {r['gim_types_gt']}")

    # Best 10 비교용
    good_sorted = sorted(good, key=lambda r: r["rel_err_incl"])[:10]
    print("\n=== Best 10 (참고) ===")
    print(f"{'level':<12} {'rxc':>7} {'pred':>6} {'gt_incl':>8} {'rel%':>6} {'n_col':>5}")
    for r in good_sorted:
        ld = get_level_data(r["level"])
        nc = ld.get("num_colors", 0) if ld else 0
        sz = f"{r['field_rows']}x{r['field_columns']}"
        print(f"  {r['level']:<11} {sz:>7} {r['cells_pred']:>6} {r['cells_gt_incl_gim']:>8} "
              f"{r['rel_err_incl']*100:>5.1f}% {nc:>5}")


if __name__ == "__main__":
    main()
