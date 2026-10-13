# Queue Stage 1 - OCR top region for level number.
# Wide ROI + position-based filter (exclude corner UI like coins, gears).
from __future__ import annotations
import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path
from collections import defaultdict

import cv2
import numpy as np


def top_strip(img_bgr):
    # Crop badge area tight, preprocess for OCR clarity.
    h, w = img_bgr.shape[:2]
    y1 = int(h * 0.015)
    y2 = int(h * 0.065)
    x1 = int(w * 0.38)
    x2 = int(w * 0.62)
    crop = img_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return crop
    # Upscale 3x for better OCR resolution
    big = cv2.resize(crop, None, fx=3.0, fy=3.0,
                     interpolation=cv2.INTER_CUBIC)
    # Grayscale + adaptive threshold (makes white text on blue bg very crisp)
    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)
    # White text on darker bg: keep light pixels
    _, binary = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
    # Convert back to 3-channel (EasyOCR prefers BGR)
    return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)


def bbox_center(bbox):
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    return (sum(xs) / 4.0, sum(ys) / 4.0)


def process_image(img_path, reader, min_conf, debug_dir=None, debug_idx=None):
    img = cv2.imread(str(img_path))
    if img is None:
        return None, 0.0, "imread failed"
    roi = top_strip(img)
    if roi.size == 0:
        return None, 0.0, "empty ROI"

    try:
        results = reader.readtext(roi, detail=1, paragraph=False)
    except Exception as e:
        return None, 0.0, "ocr error: " + str(e)

    if debug_dir is not None and debug_idx is not None and debug_idx < 5:
        # Save first 5 ROIs with OCR overlay for inspection.
        vis = roi.copy()
        for bbox, text, conf in results:
            pts = np.array(bbox, dtype=np.int32)
            cv2.polylines(vis, [pts], True, (0, 255, 0), 2)
        cv2.imwrite(str(Path(debug_dir) / (img_path.stem + "_roi.png")), vis)

    # ROI is tightly cropped to badge + preprocessed.
    # Any digit from OCR is potentially the level number.
    best_level = None
    best_conf = 0.0
    texts = []
    for bbox, text, conf in results:
        cx, cy = bbox_center(bbox)
        texts.append(
            text + "(" + ("%.2f" % conf)
            + ",cx=" + ("%.0f" % cx) + ")"
        )
        m = re.search(r"\d{1,3}", text)
        if not m:
            continue
        n = int(m.group())
        if not (1 <= n <= 500):
            continue
        if conf > best_conf:
            best_level = n
            best_conf = conf

    if best_level is None or best_conf < min_conf:
        return None, best_conf, " | ".join(texts)
    return best_level, best_conf, " | ".join(texts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--confidence", type=float, default=0.3)
    ap.add_argument("--only-before", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--gpu", action="store_true", default=True)
    ap.add_argument("--debug", action="store_true",
                    help="Save first 5 ROIs as PNG for inspection")
    args = ap.parse_args()

    in_dir = Path(args.input)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    debug_dir = out_dir / "debug_rois" if args.debug else None
    if debug_dir is not None:
        debug_dir.mkdir(exist_ok=True)

    if not in_dir.exists():
        print("ERROR: input not found: " + str(in_dir))
        sys.exit(1)

    print("Loading EasyOCR (GPU=" + str(args.gpu) + ")...")
    import easyocr
    reader = easyocr.Reader(["ko", "en"], gpu=args.gpu)
    print("EasyOCR ready.")

    print("Scanning " + str(in_dir) + "...")
    if args.only_before:
        images = [
            p for p in in_dir.iterdir()
            if p.suffix.lower() == ".png" and p.stem.endswith("_before")
        ]
    else:
        images = [p for p in in_dir.iterdir() if p.suffix.lower() == ".png"]
    images.sort()
    if args.limit > 0:
        images = images[: args.limit]
    total = len(images)
    print("Found " + str(total) + " images to process.\n")

    csv_path = out_dir / "image_to_level.csv"
    skipped_path = out_dir / "skipped.txt"
    log_path = out_dir / "run_log.txt"

    # Resume support: load previously processed filenames from existing CSV
    processed = set()
    level_to_imgs = defaultdict(list)
    skipped = []
    ok_count = 0
    if csv_path.exists():
        try:
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                r = csv.reader(f)
                header_read = False
                for row in r:
                    if not header_read:
                        header_read = True
                        continue
                    if not row:
                        continue
                    fn = row[0]
                    processed.add(fn)
                    if len(row) >= 2 and row[1]:
                        try:
                            lvl = int(row[1])
                            level_to_imgs[lvl].append(fn)
                            ok_count += 1
                        except ValueError:
                            skipped.append(fn)
                    else:
                        skipped.append(fn)
            print("Resuming. Already processed: " + str(len(processed)))
        except Exception as e:
            print("Could not resume, starting fresh: " + str(e))
            processed = set()
            level_to_imgs = defaultdict(list)
            skipped = []
            ok_count = 0

    t_start = time.time()
    mode = "a" if processed else "w"
    with open(csv_path, mode, encoding="utf-8-sig", newline="") as f, \
         open(log_path, "a", encoding="utf-8") as logf:
        w = csv.writer(f)
        if mode == "w":
            w.writerow(["filename", "level", "confidence", "ocr_raw"])
        for idx, img_path in enumerate(images, 1):
            if img_path.name in processed:
                continue
            level, conf, raw = process_image(
                img_path, reader, args.confidence, debug_dir, idx - 1
            )
            # Sanitize raw for CSV (strip control chars)
            safe_raw = "".join(c for c in raw if ord(c) >= 32 or c in "\t")
            if level is None:
                skipped.append(img_path.name)
                w.writerow([img_path.name, "", "%.3f" % conf, safe_raw])
            else:
                level_to_imgs[level].append(img_path.name)
                w.writerow([img_path.name, level, "%.3f" % conf, safe_raw])
                ok_count += 1
            if idx % 500 == 0:
                elapsed = time.time() - t_start
                rate = idx / elapsed if elapsed > 0 else 0
                eta = (total - idx) / rate if rate > 0 else 0
                msg = ("[" + str(idx) + "/" + str(total) + "] "
                       "ok=" + str(ok_count) + " skip=" + str(len(skipped))
                       + " rate=" + ("%.1f" % rate) + " img/s  "
                       "ETA=" + ("%.1f" % (eta / 60)) + "min")
                print(msg)
                logf.write(msg + "\n")
                logf.flush()

    with open(out_dir / "level_to_images.json", "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in sorted(level_to_imgs.items())},
                  f, indent=2, ensure_ascii=False)
    skipped_path.write_text("\n".join(skipped), encoding="utf-8")

    elapsed = time.time() - t_start
    summary = {
        "total_images": total,
        "identified": ok_count,
        "skipped": len(skipped),
        "elapsed_seconds": round(elapsed, 1),
        "rate_img_per_sec": round(total / elapsed, 2) if elapsed > 0 else 0,
        "levels_found": len(level_to_imgs),
        "level_distribution": {
            str(k): len(v) for k, v in sorted(level_to_imgs.items())
        },
    }
    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print("\n=== Done ===")
    print("Total: " + str(total) + "  Identified: " + str(ok_count)
          + "  Skipped: " + str(len(skipped)))
    print("Levels found: " + str(len(level_to_imgs)))
    print("Elapsed: " + ("%.1f" % (elapsed / 60)) + " min  Rate: "
          + ("%.1f" % (total / elapsed)) + " img/s")
    print("Output: " + str(out_dir))


if __name__ == "__main__":
    main()
