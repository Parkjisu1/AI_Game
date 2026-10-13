# Stage 2d: Extract queue info from representative images.
# For each level:
#   1. Load representative image
#   2. YOLO holder_detector -> bbox list
#   3. Per bbox: color (palette match) + count (OCR digit)
#   4. Sort by position -> queue order
# Output: queue_by_level.json
#
# Usage:
#   python stage2d_extract_queue.py \
#     --representatives path/to/level_to_representative.json \
#     --source path/to/click_image_folder \
#     --weights runs/holder_detector/weights/best.pt \
#     --palette path/to/cell_profile.json \
#     --output queue_by_level.json
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np


def load_palette(profile_path):
    """Return dict {color_id: (R,G,B)} from cell_profile.json."""
    try:
        data = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    except Exception:
        return {}
    palette = {}
    # Common formats:
    # {"colors": {"c1": [R,G,B], ...}} or {"palette": [[R,G,B], ...]}
    if "colors" in data and isinstance(data["colors"], dict):
        for k, v in data["colors"].items():
            m = re.search(r"(\d+)", str(k))
            if m and isinstance(v, list) and len(v) >= 3:
                palette[int(m.group(1))] = tuple(int(x) for x in v[:3])
    elif "palette" in data and isinstance(data["palette"], list):
        for i, v in enumerate(data["palette"], 1):
            if isinstance(v, list) and len(v) >= 3:
                palette[i] = tuple(int(x) for x in v[:3])
    return palette


def nearest_color(rgb, palette):
    if not palette:
        return 0
    best_id = 0
    best_dist = float("inf")
    r, g, b = rgb
    for cid, (pr, pg, pb) in palette.items():
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_dist:
            best_dist = d
            best_id = cid
    return best_id


def preprocess_for_ocr(img_bgr):
    """Same style as Stage 1: grayscale + binary + 3x upscale."""
    if img_bgr.size == 0:
        return img_bgr
    big = cv2.resize(img_bgr, None, fx=3.0, fy=3.0,
                     interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def extract_count_from_crop(crop, reader):
    """OCR a holder crop and return (count, conf)."""
    if crop.size == 0:
        return None, 0.0
    processed = preprocess_for_ocr(crop)
    try:
        results = reader.readtext(processed, detail=1, paragraph=False)
    except Exception:
        return None, 0.0
    best = None
    best_conf = 0.0
    for _, text, conf in results:
        m = re.search(r"\d{1,3}", text)
        if m:
            n = int(m.group())
            if 1 <= n <= 999 and conf > best_conf:
                best = n
                best_conf = conf
    return best, best_conf


def bbox_center_color(img_bgr, bbox):
    """Return central pixel RGB of a bbox."""
    x1, y1, x2, y2 = bbox
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    if 0 <= cy < img_bgr.shape[0] and 0 <= cx < img_bgr.shape[1]:
        b, g, r = img_bgr[cy, cx]
        return (int(r), int(g), int(b))
    return (0, 0, 0)


def process_level(level_num, img_path, model, reader, palette,
                  conf_threshold=0.25):
    img = cv2.imread(str(img_path))
    if img is None:
        return {"level": level_num, "error": "imread failed", "holders": []}

    results = model(img, verbose=False, conf=conf_threshold, imgsz=1920)
    boxes = []
    for box in results[0].boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
        cls_id = int(box.cls[0].item()) if box.cls is not None else 0
        det_conf = float(box.conf[0].item()) if box.conf is not None else 0.0
        boxes.append({
            "x1": int(x1), "y1": int(y1),
            "x2": int(x2), "y2": int(y2),
            "class": cls_id, "det_conf": det_conf,
        })

    holders = []
    for b in boxes:
        bbox = (b["x1"], b["y1"], b["x2"], b["y2"])
        rgb = bbox_center_color(img, bbox)
        color_id = nearest_color(rgb, palette)
        crop = img[b["y1"]:b["y2"], b["x1"]:b["x2"]]
        count, ocr_conf = extract_count_from_crop(crop, reader)
        holders.append({
            "bbox": [b["x1"], b["y1"], b["x2"], b["y2"]],
            "class": b["class"],
            "det_conf": round(b["det_conf"], 3),
            "color": color_id,
            "color_rgb": list(rgb),
            "count": count,
            "ocr_conf": round(ocr_conf, 3),
            "center_x": (b["x1"] + b["x2"]) // 2,
            "center_y": (b["y1"] + b["y2"]) // 2,
        })

    # Sort by position: rail runs around the board; approximate clockwise order.
    # Simple ordering: bottom-first (high y), then by x.
    holders.sort(key=lambda h: (-h["center_y"], h["center_x"]))
    for i, h in enumerate(holders):
        h["order"] = i

    return {
        "level": level_num,
        "source_image": img_path.name,
        "holder_count": len(holders),
        "holders": holders,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--representatives", required=True)
    ap.add_argument("--source", required=True,
                    help="Folder containing click_*.png images")
    ap.add_argument("--weights", required=True,
                    help="YOLO holder_detector best.pt")
    ap.add_argument("--palette", default="",
                    help="cell_profile.json (optional)")
    ap.add_argument("--output", required=True)
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()

    reps = json.loads(Path(args.representatives).read_text(encoding="utf-8"))
    source_dir = Path(args.source)
    palette = load_palette(args.palette) if args.palette else {}

    print("Loading YOLO holder detector...")
    from ultralytics import YOLO
    model = YOLO(args.weights)

    print("Loading EasyOCR...")
    import easyocr
    reader = easyocr.Reader(["en"], gpu=True)

    result = {}
    total = 0
    for level, files in reps.items():
        if not files:
            continue
        img_name = files[0]
        img_path = source_dir / img_name
        if not img_path.exists():
            continue
        total += 1
        r = process_level(level, img_path, model, reader, palette, args.conf)
        result[str(level)] = r
        if total % 20 == 0:
            print("[" + str(total) + "] level=" + str(level)
                  + " holders=" + str(r.get("holder_count", 0)))

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    print("Done. Levels processed: " + str(total))
    print("Output: " + str(out))


if __name__ == "__main__":
    main()
