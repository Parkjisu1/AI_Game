"""전체 레벨 추출 + 부분 평가 (356 level images)
=================================================

입력: F:/LevelDesignExtractor/LevelDesignExtractor_v4.0/LevelDesignExtractor_v4.0/OutPut/
출력: batch_all_levels_run/
  ├── levels/       per-level JSON (전체 356)
  ├── viz/          per-level 시각화 (라벨 있는 것은 GT 비교, 없는 것은 pred-only)
  ├── summary.csv   per-level 지표 (라벨 있는 것만 상세 평가)
  ├── summary.json  집계 (전체 + 라벨 서브셋 분리)
  ├── errors.log
  └── README.md
"""
from __future__ import annotations
import sys
import json
import csv
import traceback
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter, defaultdict
from typing import Optional

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from hybrid_extractor import extract_level, GimmickDetector, CellDetector
from cell_aware_analyzer import load_profile

F_SRC_DIR = Path(
    r"F:\LevelDesignExtractor\LevelDesignExtractor_v4.0\LevelDesignExtractor_v4.0\OutPut"
)
LABELED_IMG_DIR = HERE / "labeling" / "images_levels"  # 라벨링에 쓴 이미지 (204장)
XML_DIR = HERE / "labeling" / "labels_levels"  # GT XML
PROFILE_PATH = ROOT / "data" / "pixelflow" / "profile" / "cell_profile.json"
OUT_DIR = HERE / "batch_all_levels_run"

GIMMICK_NAMES = {
    'hidden gimik', 'pinata gimik', 'snake gimik', 'ice gimik',
    'block gimik', 'wall gimik', 'key gimik', 'door gimik',
    'egg gimik', 'cannon gimik',
}


def parse_gt(xml_path: Path) -> dict:
    if not xml_path.exists():
        return {"cells": [], "gimmicks": [], "gimmick_types": Counter()}
    root = ET.parse(xml_path).getroot()
    cells, gimmicks, types = [], [], Counter()
    for obj in root.findall("object"):
        name = (obj.find("name").text or "").strip().lower()
        bb = obj.find("bndbox")
        x1 = int(float(bb.find("xmin").text))
        y1 = int(float(bb.find("ymin").text))
        x2 = int(float(bb.find("xmax").text))
        y2 = int(float(bb.find("ymax").text))
        entry = {"name": name, "bbox": (x1, y1, x2, y2)}
        if name in GIMMICK_NAMES:
            gimmicks.append(entry)
            types[name] += 1
        else:
            cells.append(entry)
    return {"cells": cells, "gimmicks": gimmicks, "gimmick_types": types}


def bbox_iou(a, b):
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def match_gimmicks(pred, gt, iou_thr=0.5):
    matched_gt = set()
    tp = type_correct = 0
    type_confusion = []
    for p in pred:
        best_iou = 0.0
        best_j = -1
        for j, g in enumerate(gt):
            if j in matched_gt:
                continue
            iou = bbox_iou(p["bbox"], g["bbox"])
            if iou > best_iou:
                best_iou = iou
                best_j = j
        if best_iou >= iou_thr and best_j >= 0:
            matched_gt.add(best_j)
            tp += 1
            if p.get("name") == gt[best_j].get("name"):
                type_correct += 1
            else:
                type_confusion.append((p.get("name", ""), gt[best_j].get("name", "")))
    return {
        "tp": tp, "fp": len(pred) - tp, "fn": len(gt) - tp,
        "type_correct": type_correct, "type_confusion": type_confusion,
    }


def compute_prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return p, r, f


def render_viz(img_bgr, result, gt, out_path, has_gt):
    vis = img_bgr.copy()
    if has_gt:
        for g in gt["gimmicks"]:
            x1, y1, x2, y2 = g["bbox"]
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
    # Pred: type별 색상
    TYPE_COLORS = {
        "hidden gimik": (100, 100, 100), "ice gimik": (255, 200, 100),
        "pinata gimik": (200, 100, 200), "snake gimik": (50, 200, 50),
        "key gimik": (0, 215, 255), "block gimik": (255, 0, 255),
        "door gimik": (50, 100, 150), "egg gimik": (200, 255, 255),
        "wall gimik": (50, 50, 100), "cannon gimik": (100, 0, 200),
    }
    for g in result.get("gimmick_positions", []):
        color = TYPE_COLORS.get(g["type"], (0, 0, 255))
        cv2.circle(vis, (g["x"], g["y"]), 10, color, -1)
        cv2.circle(vis, (g["x"], g["y"]), 12, (0, 0, 0), 1)
    # 요약
    gim_str = " ".join(f"{k}:{v}" for k, v in result.get("gimmicks", {}).items())
    gt_str = (
        " GT=" + " ".join(f"{k}:{v}" for k, v in gt["gimmick_types"].items())
        if has_gt else ""
    )
    txt = (
        f"L{result.get('level_number', '?')} "
        f"{result.get('field_rows', '?')}x{result.get('field_columns', '?')} "
        f"cells={result.get('total_cells', '?')} | {gim_str}{gt_str}"
    )
    cv2.putText(vis, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
    cv2.putText(vis, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.imwrite(str(out_path), vis)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "levels").mkdir(exist_ok=True)
    (OUT_DIR / "viz").mkdir(exist_ok=True)
    errors_log = OUT_DIR / "errors.log"
    errors_log.write_text("", encoding="utf-8")

    if not F_SRC_DIR.exists():
        print(f"WARNING: F source dir not found: {F_SRC_DIR}")
        print("F 드라이브가 없어 labeling/images_levels/ 만 처리합니다.")

    print(f"Loading profile: {PROFILE_PATH}")
    profile = load_profile(str(PROFILE_PATH))
    print(f"Loading gimmick detector...")
    detector = GimmickDetector()
    if detector._model is None:
        print("ERROR: gimmick model failed to load")
        return
    print(f"Loading cell detector (YOLO cell_only, hires=OFF)...")
    cell_det = CellDetector(use_hires=False)
    if cell_det._model is None:
        print("WARNING: cell model failed — using pixel fallback")

    # 레벨별 이미지 소스 결정: 라벨링용(우선) > F 원본 (없으면 스킵)
    labeled_names = {p.stem for p in LABELED_IMG_DIR.glob("level_*.png")}
    f_names = {p.stem for p in F_SRC_DIR.glob("level_*.png")} if F_SRC_DIR.exists() else set()
    all_names = sorted(labeled_names | f_names)

    def resolve(name: str) -> Path:
        if name in labeled_names:
            return LABELED_IMG_DIR / f"{name}.png"
        return F_SRC_DIR / f"{name}.png"

    all_imgs = [resolve(n) for n in all_names]
    print(f"Source: labeled={len(labeled_names)}, F-only={len(f_names - labeled_names)}, "
          f"total={len(all_imgs)}\n")

    rows = []
    gimmick_totals = {"tp": 0, "fp": 0, "fn": 0, "type_correct": 0}
    gimmick_totals["type_confusion"] = []
    cell_totals = {"pred_sum": 0, "gt_sum": 0, "abs_err_sum": 0}
    all_gimmick_counts: Counter = Counter()  # 전체 탐지 기믹 타입 분포
    total_cells_all = 0
    labeled_count = 0

    for idx, img_path in enumerate(all_imgs, 1):
        level_name = img_path.stem
        xml_path = XML_DIR / f"{level_name}.xml"
        has_gt = xml_path.exists()

        try:
            level_num_str = level_name.replace("level_", "")
            level_num = int(level_num_str)
        except ValueError:
            level_num = idx

        try:
            img_bgr = cv2.imread(str(img_path))
            if img_bgr is None:
                errors_log.write_text(
                    errors_log.read_text(encoding="utf-8")
                    + f"{level_name}: cv2.imread failed\n",
                    encoding="utf-8",
                )
                continue

            gt = parse_gt(xml_path) if has_gt else None
            raw_dets = detector.detect(img_bgr)
            result = extract_level(img_path, profile, level_num, detector, cell_det)
            if "error" in result:
                errors_log.write_text(
                    errors_log.read_text(encoding="utf-8")
                    + f"{level_name}: {result['error']}\n",
                    encoding="utf-8",
                )
                continue

            # JSON 저장
            (OUT_DIR / "levels" / f"{level_name}.json").write_text(
                json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
            )

            # 전체 통계
            for k, v in result.get("gimmicks", {}).items():
                all_gimmick_counts[k] += v
            total_cells_all += result.get("total_cells", 0)

            row = {
                "level": level_name,
                "has_gt": has_gt,
                "field_rows": result.get("field_rows", 0),
                "field_columns": result.get("field_columns", 0),
                "cells_pred": result.get("total_cells", 0),
                "num_colors": result.get("num_colors", 0),
                "gim_pred_total": sum(result.get("gimmicks", {}).values()),
                "gim_types_pred": ",".join(
                    f"{k}:{v}" for k, v in result.get("gimmicks", {}).items()
                ),
            }

            # GT가 있으면 평가
            if has_gt:
                labeled_count += 1
                pred_gimmicks = [
                    {"bbox": d["bbox"], "name": d["type"]} for d in raw_dets
                ]
                m = match_gimmicks(pred_gimmicks, gt["gimmicks"])
                gimmick_totals["tp"] += m["tp"]
                gimmick_totals["fp"] += m["fp"]
                gimmick_totals["fn"] += m["fn"]
                gimmick_totals["type_correct"] += m["type_correct"]
                gimmick_totals["type_confusion"].extend(m["type_confusion"])

                cells_gt = len(gt["cells"])
                cells_pred = result.get("total_cells", 0)
                cell_totals["pred_sum"] += cells_pred
                cell_totals["gt_sum"] += cells_gt
                cell_totals["abs_err_sum"] += abs(cells_pred - cells_gt)

                p, r, f = compute_prf(m["tp"], m["fp"], m["fn"])
                row.update({
                    "cells_gt": cells_gt,
                    "cells_diff": cells_pred - cells_gt,
                    "gim_gt_total": len(gt["gimmicks"]),
                    "gim_types_gt": ",".join(
                        f"{k}:{v}" for k, v in gt["gimmick_types"].items()
                    ),
                    "gim_tp": m["tp"],
                    "gim_fp": m["fp"],
                    "gim_fn": m["fn"],
                    "gim_p": round(p, 3),
                    "gim_r": round(r, 3),
                    "gim_f1": round(f, 3),
                    "type_correct": m["type_correct"],
                })

            rows.append(row)
            render_viz(img_bgr, result, gt if has_gt else None, OUT_DIR / "viz" / f"{level_name}.png", has_gt)

            if idx % 30 == 0:
                print(f"  [{idx}/{len(all_imgs)}] {level_name}  "
                      f"cells={result.get('total_cells', 0)} "
                      f"gim={sum(result.get('gimmicks', {}).values())}")

        except Exception as e:
            errors_log.write_text(
                errors_log.read_text(encoding="utf-8")
                + f"{level_name}: {e}\n{traceback.format_exc()}\n",
                encoding="utf-8",
            )

    # Summary CSV: 모든 row 포함 (has_gt 플래그로 구분)
    if rows:
        all_keys = sorted({k for r in rows for k in r.keys()})
        csv_path = OUT_DIR / "summary.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=all_keys)
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in all_keys})

    # Summary JSON
    gp, gr, gf = compute_prf(
        gimmick_totals["tp"], gimmick_totals["fp"], gimmick_totals["fn"]
    )
    type_acc = (
        gimmick_totals["type_correct"] / gimmick_totals["tp"]
        if gimmick_totals["tp"] > 0 else 0.0
    )
    cell_mae = (
        cell_totals["abs_err_sum"] / labeled_count if labeled_count > 0 else 0.0
    )
    confusion_counts = Counter(tuple(t) for t in gimmick_totals["type_confusion"])
    summary = {
        "total_images_processed": len(rows),
        "labeled_subset": labeled_count,
        "overall_stats": {
            "total_cells_extracted": total_cells_all,
            "total_gimmicks_extracted": sum(all_gimmick_counts.values()),
            "gimmick_type_distribution_pred": dict(all_gimmick_counts.most_common()),
        },
        "labeled_subset_evaluation": {
            "gimmicks": {
                "tp": gimmick_totals["tp"],
                "fp": gimmick_totals["fp"],
                "fn": gimmick_totals["fn"],
                "precision": round(gp, 4),
                "recall": round(gr, 4),
                "f1": round(gf, 4),
                "type_accuracy": round(type_acc, 4),
                "type_correct": gimmick_totals["type_correct"],
                "top_confusions": [
                    {"pred": p, "gt": g, "count": c}
                    for (p, g), c in confusion_counts.most_common(10)
                ],
            },
            "cells": {
                "mae": round(cell_mae, 2),
                "total_pred": cell_totals["pred_sum"],
                "total_gt": cell_totals["gt_sum"],
            },
        },
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    readme = f"""# Batch All Levels Extraction

Total levels processed: {len(rows)}
Labeled subset (evaluated): {labeled_count}

## Overall (all {len(rows)} levels)
- Total cells: {total_cells_all}
- Total gimmicks: {sum(all_gimmick_counts.values())}
- Gimmick distribution: {dict(all_gimmick_counts.most_common(5))}

## Labeled Subset Eval
- Gimmick P/R/F1: {gp:.3f} / {gr:.3f} / {gf:.3f}
- Type classification accuracy: {type_acc:.3f}
- Cell count MAE: {cell_mae:.2f}

## Outputs
- `levels/*.json`  per-level extraction (all levels)
- `viz/*.png`      visualizations (GT green if available, pred colored dots)
- `summary.csv`    per-level metrics
- `summary.json`   aggregate metrics
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")

    print("\n" + "=" * 50)
    print(f"Done. Output: {OUT_DIR}")
    print(f"Total processed: {len(rows)} (labeled: {labeled_count})")
    print(f"Labeled eval — Gim P/R/F1: {gp:.3f}/{gr:.3f}/{gf:.3f}")
    print(f"Labeled eval — Type accuracy: {type_acc:.3f}")
    print(f"Labeled eval — Cell MAE: {cell_mae:.2f}")
    print(f"Overall — cells={total_cells_all}, gimmicks={sum(all_gimmick_counts.values())}")


if __name__ == "__main__":
    main()
