"""Hybrid 파이프라인 배치 추출 + 자가 평가 (Run 스타일 리포트)
=============================================================

입력: labeling/images_levels 내 모든 이미지
출력: batch_hybrid_run/
  ├── levels/           per-level JSON (hybrid_extractor 결과)
  ├── viz/              per-level 시각화 PNG
  ├── summary.csv       per-level 지표 (셀/기믹 Precision, Recall, F1)
  ├── summary.json      전체 통계 (avg metrics, class-wise)
  ├── errors.log        처리 실패 이미지 로그
  └── README.md         결과 요약

평가 대상:
  - 셀 개수 (GT: labels_levels XML의 non-gimik name 수 vs 예측)
  - 기믹 개수 (GT: gimik name 수 vs 예측)
  - 기믹 위치 매칭 (IoU ≥ 0.5 기준)
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
ROOT = HERE.parent.parent  # virtual_player/
sys.path.insert(0, str(ROOT / "tools"))
from hybrid_extractor import extract_level, GimmickDetector
from cell_aware_analyzer import load_profile

IMG_DIR = HERE / "labeling" / "images_levels"
XML_DIR = HERE / "labeling" / "labels_levels"
PROFILE_PATH = ROOT / "data" / "pixelflow" / "profile" / "cell_profile.json"
OUT_DIR = HERE / "batch_hybrid_run"

GIMMICK_NAMES = {
    'hidden gimik', 'pinata gimik', 'snake gimik', 'ice gimik',
    'block gimik', 'wall gimik', 'key gimik', 'door gimik',
    'egg gimik', 'cannon gimik',
}


def parse_gt(xml_path: Path) -> dict:
    """XML에서 GT bbox 로드."""
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


def bbox_iou(a: tuple, b: tuple) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    ua = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / ua if ua > 0 else 0.0


def match_gimmicks(pred: list[dict], gt: list[dict], iou_thr: float = 0.5) -> dict:
    """예측 bbox와 GT bbox를 IoU로 매칭. 타입 일치 여부도 체크.

    pred/gt: [{"bbox":(...), "name":str}, ...]
    """
    matched_gt = set()
    tp = 0
    type_correct = 0  # IoU 매칭되고 타입까지 일치
    type_confusion = []  # (pred_type, gt_type) 오분류 케이스
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
            gt_name = gt[best_j].get("name", "")
            pred_name = p.get("name", "")
            if pred_name == gt_name:
                type_correct += 1
            else:
                type_confusion.append((pred_name, gt_name))
    fp = len(pred) - tp
    fn = len(gt) - tp
    return {"tp": tp, "fp": fp, "fn": fn,
            "type_correct": type_correct,
            "type_confusion": type_confusion}


def compute_prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    return p, r, f


def render_viz(img_bgr: np.ndarray, result: dict, gt: dict, out_path: Path):
    """시각화: GT=녹색, Pred=빨강."""
    vis = img_bgr.copy()
    # GT gimmicks (녹색)
    for g in gt["gimmicks"]:
        x1, y1, x2, y2 = g["bbox"]
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 2)
    # Pred gimmicks (빨강, center→bbox 복원 불가하므로 원으로 표시)
    for g in result.get("gimmick_positions", []):
        cv2.circle(vis, (g["x"], g["y"]), 12, (0, 0, 255), 2)
    # 요약 텍스트
    txt = (
        f"Cells pred={result.get('total_cells', '?')} GT={len(gt['cells'])} | "
        f"Gimmicks pred={sum(result.get('gimmicks', {}).values())} GT={len(gt['gimmicks'])}"
    )
    cv2.putText(vis, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 3)
    cv2.putText(vis, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 1)
    cv2.imwrite(str(out_path), vis)


def main():
    OUT_DIR.mkdir(exist_ok=True)
    (OUT_DIR / "levels").mkdir(exist_ok=True)
    (OUT_DIR / "viz").mkdir(exist_ok=True)
    errors_log = OUT_DIR / "errors.log"
    errors_log.write_text("", encoding="utf-8")

    print(f"Loading profile: {PROFILE_PATH}")
    profile = load_profile(str(PROFILE_PATH))
    print(f"Loading gimmick detector...")
    detector = GimmickDetector()
    if detector._model is None:
        print("ERROR: gimmick model failed to load")
        return

    # 대상 이미지: XML이 있는 것만 (평가 가능)
    xml_files = sorted(XML_DIR.glob("level_*.xml"))
    print(f"Found {len(xml_files)} labeled images\n")

    rows = []
    gimmick_totals = {"tp": 0, "fp": 0, "fn": 0}
    cell_totals = {"pred_sum": 0, "gt_sum": 0, "abs_err_sum": 0}
    per_class_stats: dict[str, dict] = defaultdict(lambda: {"gt": 0, "covered_by_pred": 0})

    for idx, xml_path in enumerate(xml_files, 1):
        level_name = xml_path.stem  # "level_050"
        img_path = IMG_DIR / f"{level_name}.png"
        if not img_path.exists():
            continue

        level_num_str = level_name.replace("level_", "")
        try:
            level_num = int(level_num_str)
        except ValueError:
            level_num = idx

        try:
            img_bgr = cv2.imread(str(img_path))
            gt = parse_gt(xml_path)

            # pred 복원을 위해 detector.detect를 직접 호출 (bbox 확보)
            raw_dets = detector.detect(img_bgr)
            result = extract_level(img_path, profile, level_num, detector)
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

            # gimmick 매칭 (bbox 기반 IoU + 타입 일치)
            pred_gimmicks = [{"bbox": d["bbox"], "name": d["type"]} for d in raw_dets]
            m = match_gimmicks(pred_gimmicks, gt["gimmicks"])

            # 누적 통계
            gimmick_totals["tp"] += m["tp"]
            gimmick_totals["fp"] += m["fp"]
            gimmick_totals["fn"] += m["fn"]
            gimmick_totals.setdefault("type_correct", 0)
            gimmick_totals["type_correct"] += m["type_correct"]
            gimmick_totals.setdefault("type_confusion", [])
            gimmick_totals["type_confusion"].extend(m["type_confusion"])

            cells_pred = result.get("total_cells", 0)
            cells_gt = len(gt["cells"])
            cell_totals["pred_sum"] += cells_pred
            cell_totals["gt_sum"] += cells_gt
            cell_totals["abs_err_sum"] += abs(cells_pred - cells_gt)

            # 클래스별 GT 카운트 (예측은 단일 클래스라 매칭 시 커버 여부만)
            for gname, gcount in gt["gimmick_types"].items():
                per_class_stats[gname]["gt"] += gcount
            # per-level row
            p, r, f = compute_prf(m["tp"], m["fp"], m["fn"])
            rows.append({
                "level": level_name,
                "cells_pred": cells_pred,
                "cells_gt": cells_gt,
                "cells_diff": cells_pred - cells_gt,
                "gim_pred": len(raw_dets),
                "gim_gt": len(gt["gimmicks"]),
                "gim_tp": m["tp"],
                "gim_fp": m["fp"],
                "gim_fn": m["fn"],
                "gim_precision": round(p, 3),
                "gim_recall": round(r, 3),
                "gim_f1": round(f, 3),
                "gt_types": ",".join(f"{k}:{v}" for k, v in gt["gimmick_types"].items()),
            })

            # 시각화
            render_viz(img_bgr, result, gt, OUT_DIR / "viz" / f"{level_name}.png")

            if idx % 20 == 0:
                print(f"  [{idx}/{len(xml_files)}] {level_name} "
                      f"cells {cells_pred}/{cells_gt}  "
                      f"gim P={p:.2f} R={r:.2f}")

        except Exception as e:
            errors_log.write_text(
                errors_log.read_text(encoding="utf-8")
                + f"{level_name}: {e}\n{traceback.format_exc()}\n",
                encoding="utf-8",
            )

    # Summary CSV
    csv_path = OUT_DIR / "summary.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    # Summary JSON
    gp, gr, gf = compute_prf(
        gimmick_totals["tp"], gimmick_totals["fp"], gimmick_totals["fn"]
    )
    cell_mae = cell_totals["abs_err_sum"] / len(rows) if rows else 0.0
    cell_mape = (
        sum(abs(row["cells_diff"]) / row["cells_gt"] for row in rows if row["cells_gt"] > 0)
        / max(1, sum(1 for row in rows if row["cells_gt"] > 0))
    )
    # 타입 분류 정확도 집계
    type_acc = (
        gimmick_totals.get("type_correct", 0) / gimmick_totals["tp"]
        if gimmick_totals["tp"] > 0 else 0.0
    )
    confusion_counts = Counter(tuple(t) for t in gimmick_totals.get("type_confusion", []))
    top_confusions = [
        {"pred": p, "gt": g, "count": c}
        for (p, g), c in confusion_counts.most_common(15)
    ]
    summary = {
        "total_levels_processed": len(rows),
        "gimmicks": {
            "tp": gimmick_totals["tp"],
            "fp": gimmick_totals["fp"],
            "fn": gimmick_totals["fn"],
            "precision": round(gp, 4),
            "recall": round(gr, 4),
            "f1": round(gf, 4),
            "type_accuracy": round(type_acc, 4),
            "type_correct": gimmick_totals.get("type_correct", 0),
            "top_confusions": top_confusions,
        },
        "cells": {
            "mae": round(cell_mae, 2),
            "mape": round(cell_mape, 4),
            "total_pred": cell_totals["pred_sum"],
            "total_gt": cell_totals["gt_sum"],
        },
        "gimmick_class_distribution_gt": dict(
            sorted(
                {k: v["gt"] for k, v in per_class_stats.items()}.items(),
                key=lambda x: -x[1],
            )
        ),
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # README
    readme = f"""# Batch Hybrid Evaluation Report

Processed: {len(rows)} levels

## Gimmick Detection (IoU>=0.5)
- Precision: {gp:.3f}
- Recall:    {gr:.3f}
- F1:        {gf:.3f}
- TP={gimmick_totals['tp']}, FP={gimmick_totals['fp']}, FN={gimmick_totals['fn']}

## Cell Count Accuracy
- MAE: {cell_mae:.2f} cells per level
- MAPE: {cell_mape*100:.2f}%
- Total pred/GT: {cell_totals['pred_sum']} / {cell_totals['gt_sum']}

## Outputs
- `levels/*.json` - per-level hybrid extraction result
- `viz/*.png`     - GT (green box) vs Pred (red circle)
- `summary.csv`   - per-level metrics
- `summary.json`  - aggregate metrics
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")

    print("\n" + "=" * 50)
    print(f"Done. Output: {OUT_DIR}")
    print(f"Gimmick P/R/F1: {gp:.3f} / {gr:.3f} / {gf:.3f}")
    print(f"Cell MAE: {cell_mae:.2f} / MAPE: {cell_mape*100:.2f}%")


if __name__ == "__main__":
    main()
