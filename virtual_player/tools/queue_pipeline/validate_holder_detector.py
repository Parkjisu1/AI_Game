"""
holder_detector 모델 검증 스크립트.

- 44장 labeling 이미지에 inference 실행
- train(33) / val(9) / unlabeled(2) 분리해서 통계 계산
- Pascal VOC XML 라벨과 매칭해서 per-image detection 카운트 비교
- 결과 시각화 → runs/holder_detector_validation/

Usage:
    python validate_holder_detector.py
"""
from pathlib import Path
import xml.etree.ElementTree as ET
import json
import sys
from collections import Counter, defaultdict

ROOT = Path("E:/AI/virtual_player/yolo/pixelflow")
WEIGHTS = ROOT / "runs/holder_detector/weights/best.pt"
IMG_DIR = ROOT / "labeling/images_queue"
LBL_DIR = ROOT / "labeling/labels_queue"
VAL_DIR = ROOT / "dataset_holder/images/val"
OUT_DIR = ROOT / "runs/holder_detector_validation"

CLASS_NAMES = [
    *[f"holder_c{i}" for i in range(1, 30)],
    "gimmick_snake", "gimmick_pinata", "gimmick_ice", "gimmick_block",
    "gimmick_wall", "gimmick_key", "gimmick_door", "gimmick_egg",
    "gimmick_hidden", "gimmick_cannon", "current_balloon",
]

def parse_xml(xml_path):
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []
    objs = []
    for obj in tree.getroot().findall("object"):
        name = obj.findtext("name", "").strip()
        bb = obj.find("bndbox")
        if bb is None:
            continue
        objs.append({
            "name": name,
            "xmin": float(bb.findtext("xmin", 0)),
            "ymin": float(bb.findtext("ymin", 0)),
            "xmax": float(bb.findtext("xmax", 0)),
            "ymax": float(bb.findtext("ymax", 0)),
        })
    return objs

def iou(a, b):
    xA = max(a["xmin"], b["xmin"]); yA = max(a["ymin"], b["ymin"])
    xB = min(a["xmax"], b["xmax"]); yB = min(a["ymax"], b["ymax"])
    inter = max(0, xB - xA) * max(0, yB - yA)
    a_area = (a["xmax"]-a["xmin"]) * (a["ymax"]-a["ymin"])
    b_area = (b["xmax"]-b["xmin"]) * (b["ymax"]-b["ymin"])
    union = a_area + b_area - inter
    return inter / union if union > 0 else 0.0

def main():
    try:
        from ultralytics import YOLO
    except ImportError:
        print("ultralytics 필요: pip install ultralytics", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    val_names = {p.stem for p in VAL_DIR.glob("*.png")}
    img_files = sorted(IMG_DIR.glob("*.png"))
    print(f"Loading model: {WEIGHTS}")
    model = YOLO(str(WEIGHTS))
    print(f"Inference on {len(img_files)} images (conf=0.25, iou=0.7)")

    per_image_results = []
    tp_total = fp_total = fn_total = 0
    type_correct = type_wrong = 0
    class_pred_hist = Counter()
    class_gt_hist = Counter()

    for img_path in img_files:
        stem = img_path.stem
        split = "val" if stem in val_names else ("unlabeled" if not (LBL_DIR / f"{stem}.xml").exists() else "train")
        results = model.predict(source=str(img_path), conf=0.25, iou=0.7, verbose=False, save=True, project=str(OUT_DIR), name="pred", exist_ok=True)
        r = results[0]
        preds = []
        if r.boxes is not None:
            for box, cls, conf in zip(r.boxes.xyxy.cpu().numpy(), r.boxes.cls.cpu().numpy(), r.boxes.conf.cpu().numpy()):
                cls_id = int(cls)
                preds.append({
                    "xmin": float(box[0]), "ymin": float(box[1]),
                    "xmax": float(box[2]), "ymax": float(box[3]),
                    "name": CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f"cls{cls_id}",
                    "conf": float(conf),
                })
                class_pred_hist[preds[-1]["name"]] += 1

        gts = parse_xml(LBL_DIR / f"{stem}.xml") if split != "unlabeled" else []
        for g in gts:
            class_gt_hist[g["name"]] += 1

        tp = fp = fn = 0
        matched_pred = set()
        for gi, g in enumerate(gts):
            best_iou = 0.0; best_pi = -1
            for pi, p in enumerate(preds):
                if pi in matched_pred: continue
                i = iou(g, p)
                if i > best_iou:
                    best_iou = i; best_pi = pi
            if best_iou >= 0.5 and best_pi >= 0:
                matched_pred.add(best_pi)
                tp += 1
                if preds[best_pi]["name"] == g["name"]:
                    type_correct += 1
                else:
                    type_wrong += 1
            else:
                fn += 1
        fp = len(preds) - len(matched_pred)

        if split != "unlabeled":
            tp_total += tp; fp_total += fp; fn_total += fn

        per_image_results.append({
            "file": img_path.name, "split": split,
            "gt_count": len(gts), "pred_count": len(preds),
            "tp": tp, "fp": fp, "fn": fn,
        })

    prec = tp_total / (tp_total + fp_total) if (tp_total + fp_total) > 0 else 0.0
    rec = tp_total / (tp_total + fn_total) if (tp_total + fn_total) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    type_acc = type_correct / (type_correct + type_wrong) if (type_correct + type_wrong) > 0 else 0.0

    report = {
        "total_images": len(img_files),
        "overall": {
            "tp": tp_total, "fp": fp_total, "fn": fn_total,
            "precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
            "type_accuracy": round(type_acc, 4),
        },
        "per_split": {},
        "class_pred_hist": dict(class_pred_hist.most_common()),
        "class_gt_hist": dict(class_gt_hist.most_common()),
        "per_image": per_image_results,
    }
    for split in ("train", "val", "unlabeled"):
        imgs = [r for r in per_image_results if r["split"] == split]
        if not imgs: continue
        s_tp = sum(r["tp"] for r in imgs); s_fp = sum(r["fp"] for r in imgs); s_fn = sum(r["fn"] for r in imgs)
        sp = s_tp / (s_tp + s_fp) if (s_tp + s_fp) > 0 else 0.0
        sr = s_tp / (s_tp + s_fn) if (s_tp + s_fn) > 0 else 0.0
        report["per_split"][split] = {
            "images": len(imgs), "tp": s_tp, "fp": s_fp, "fn": s_fn,
            "precision": round(sp, 4), "recall": round(sr, 4),
            "avg_gt": round(sum(r["gt_count"] for r in imgs) / len(imgs), 2),
            "avg_pred": round(sum(r["pred_count"] for r in imgs) / len(imgs), 2),
        }

    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print("\n=== REPORT ===")
    print(json.dumps(report["overall"], indent=2))
    print("\n--- Per-split ---")
    print(json.dumps(report["per_split"], indent=2))
    print(f"\nReport: {OUT_DIR / 'report.json'}")
    print(f"Predictions visualized in: {OUT_DIR / 'pred'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
