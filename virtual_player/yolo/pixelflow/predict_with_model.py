"""
학습된 YOLO로 새 이미지에 자동 라벨 생성 (PascalVOC XML).
Hybrid Auto-Detect보다 정확 (mAP 높을 때).

사용:
  python predict_with_model.py                       # labeling/images_levels 전체
  python predict_with_model.py --conf 0.4
"""
from __future__ import annotations
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import LABEL_IMAGES_DIR, LABELING_DIR, LEVELS_MODEL_WEIGHTS


def _indent(elem, level=0):
    i = "\n" + level * "\t"
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "\t"
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    if not elem.tail or not elem.tail.strip():
        elem.tail = i


def save_xml(img_path, w, h, detections, names, xml_path):
    root = ET.Element("annotation")
    ET.SubElement(root, "folder").text = img_path.parent.name
    ET.SubElement(root, "filename").text = img_path.name
    ET.SubElement(root, "path").text = str(img_path)
    src = ET.SubElement(root, "source")
    ET.SubElement(src, "database").text = "YOLO-Predicted"
    sz = ET.SubElement(root, "size")
    ET.SubElement(sz, "width").text = str(w)
    ET.SubElement(sz, "height").text = str(h)
    ET.SubElement(sz, "depth").text = "3"
    ET.SubElement(root, "segmented").text = "0"

    for box in detections:
        cid = int(box.cls)
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
        obj = ET.SubElement(root, "object")
        ET.SubElement(obj, "name").text = names[cid]
        ET.SubElement(obj, "pose").text = "Unspecified"
        ET.SubElement(obj, "truncated").text = "0"
        ET.SubElement(obj, "difficult").text = "0"
        bb = ET.SubElement(obj, "bndbox")
        ET.SubElement(bb, "xmin").text = str(int(x1))
        ET.SubElement(bb, "ymin").text = str(int(y1))
        ET.SubElement(bb, "xmax").text = str(int(x2))
        ET.SubElement(bb, "ymax").text = str(int(y2))

    _indent(root)
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(xml_path, encoding="utf-8", xml_declaration=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", type=Path, default=LEVELS_MODEL_WEIGHTS)
    ap.add_argument("--dir", type=Path, default=LABEL_IMAGES_DIR)
    ap.add_argument("--out", type=Path,
                    default=LABELING_DIR / "labels_predicted")
    ap.add_argument("--conf", type=float, default=0.35)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--imgsz", type=int, default=1920)
    args = ap.parse_args()

    if not args.weights.exists():
        print(f"[ERROR] 모델 없음: {args.weights}")
        return

    from ultralytics import YOLO
    model = YOLO(str(args.weights))

    images = sorted(p for p in args.dir.iterdir()
                    if p.suffix.lower() in {".png", ".jpg"})
    print(f"[model] {args.weights}")
    print(f"[input] {len(images)} images")
    print(f"[out]   {args.out}")
    args.out.mkdir(parents=True, exist_ok=True)

    total_bbox = 0
    cls_count: Counter = Counter()
    for i, p in enumerate(images):
        img = cv2.imread(str(p))
        if img is None:
            continue
        h, w = img.shape[:2]
        r = model(img, imgsz=args.imgsz, conf=args.conf, iou=args.iou,
                  verbose=False)[0]
        save_xml(p, w, h, r.boxes, r.names, args.out / f"{p.stem}.xml")
        total_bbox += len(r.boxes)
        for box in r.boxes:
            cls_count[r.names[int(box.cls)]] += 1
        if (i + 1) % 25 == 0 or i == len(images) - 1:
            print(f"  [{i+1}/{len(images)}] {p.name}: {len(r.boxes)} bboxes")

    print()
    print(f"=== Summary ===  Total bbox: {total_bbox:,}")
    for n, c in cls_count.most_common():
        print(f"  {n:<22s} {c:,}")
    print()
    print(f"라벨이 {args.out}에 생성됨.")
    print(f"label_editor 에서 검수: python label_editor.py --labels {args.out}")


if __name__ == "__main__":
    main()
