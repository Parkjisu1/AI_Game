"""
stage2d_all.py — 42,850 identified images에 대해 holder_detector inference 실행.

기존 stage2d_extract_queue.py가 레벨당 대표이미지 1장만 처리하는 반면
이 스크립트는 Stage 1 OCR로 레벨 식별된 모든 이미지를 처리하여
시계열 관찰 로그를 생성한다. (Turn-by-turn queue 복원용)

Input:
    level_to_images.json  — {level: [filename, ...]}
    images directory      — click_*.png 원본
    best.pt               — holder_detector 가중치

Output (JSONL, 이미지당 1줄):
    {"level": 170, "seq": 356, "filename": "...", "holders": [...], "gimmicks": [...]}

Usage (3080 Ti):
    python stage2d_all.py \
        --images-dir F:\\LevelDesignExtractor\\pixelflow \
        --level-mapping .\\stage1_out\\level_to_images.json \
        --weights ..\\..\\yolo\\pixelflow\\runs\\holder_detector\\weights\\best.pt \
        --output .\\queue_all_observations.jsonl \
        --batch 16 --imgsz 1280 --conf 0.25

Usage (로컬 3060 Ti):
    python stage2d_all.py \
        --images-dir F:/LevelDesignExtractor/pixelflow \
        --level-mapping E:/AI/virtual_player/tools/queue_pipeline/stage1_out/level_to_images.json \
        --weights E:/AI/virtual_player/yolo/pixelflow/runs/holder_detector/weights/best.pt \
        --output E:/AI/virtual_player/tools/queue_pipeline/queue_all_observations.jsonl \
        --batch 4 --imgsz 1280 --conf 0.25
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

CLASS_NAMES = [
    *[f"holder_c{i}" for i in range(1, 30)],
    "gimmick_snake", "gimmick_pinata", "gimmick_ice", "gimmick_block",
    "gimmick_wall", "gimmick_key", "gimmick_door", "gimmick_egg",
    "gimmick_hidden", "gimmick_cannon", "current_balloon",
]

SEQ_RE = re.compile(r"click_\d+_\d+_(\d+)_")


def parse_seq(filename: str) -> int:
    """click_20260325_101717_0001_before.png → 1"""
    m = SEQ_RE.search(filename)
    return int(m.group(1)) if m else -1


def load_flat_list(mapping_path: Path, filename_suffix: str = "before"):
    """
    level_to_images.json 로드.

    filename_suffix:
        "before" → 원본 파일명 그대로 (default, 기존 동작)
        "after"  → _before.png → _after.png 치환
    """
    data = json.loads(mapping_path.read_text(encoding="utf-8"))
    items = []
    for level_str, files in data.items():
        try:
            level = int(level_str)
        except ValueError:
            continue
        for fn in files:
            if filename_suffix != "before":
                fn = fn.replace("_before.png", f"_{filename_suffix}.png")
            items.append((level, fn, parse_seq(fn)))
    items.sort(key=lambda x: (x[0], x[2]))
    return items


def load_processed_filenames(output_path: Path) -> set:
    if not output_path.exists():
        return set()
    processed = set()
    with output_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                processed.add(rec["filename"])
            except Exception:
                pass
    return processed


def make_record(level, filename, seq, result):
    holders, gimmicks = [], []
    current_balloon = None
    if result.boxes is not None and len(result.boxes) > 0:
        for box, cls, conf in zip(
            result.boxes.xyxy.cpu().numpy(),
            result.boxes.cls.cpu().numpy(),
            result.boxes.conf.cpu().numpy(),
        ):
            cls_id = int(cls)
            entry = {
                "class": cls_id,
                "name": CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f"cls{cls_id}",
                "bbox": [float(box[0]), float(box[1]), float(box[2]), float(box[3])],
                "cx": float((box[0] + box[2]) / 2),
                "cy": float((box[1] + box[3]) / 2),
                "conf": round(float(conf), 4),
            }
            if cls_id <= 28:
                holders.append(entry)
            elif cls_id <= 38:
                gimmicks.append(entry)
            elif cls_id == 39:
                current_balloon = entry
    holders.sort(key=lambda h: (h["cy"], h["cx"]))
    return {
        "level": level,
        "filename": filename,
        "seq": seq,
        "holder_count": len(holders),
        "holders": holders,
        "gimmick_count": len(gimmicks),
        "gimmicks": gimmicks,
        "current_balloon": current_balloon,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--images-dir", required=True, type=Path)
    p.add_argument("--level-mapping", required=True, type=Path)
    p.add_argument("--weights", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument("--imgsz", type=int, default=1280)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--iou", type=float, default=0.7)
    p.add_argument("--device", default=None, help="'cuda:0' or 'cpu' (ultralytics autodetect)")
    p.add_argument("--limit", type=int, default=0, help="Debug: process only N images")
    p.add_argument("--resume", action="store_true", help="Skip filenames already in output")
    p.add_argument("--filename-suffix", default="before",
                   help="'before' (default) or 'after' — level_to_images.json의 _before.png를 _{suffix}.png로 치환")
    args = p.parse_args()

    if not args.images_dir.exists():
        print(f"ERROR: images-dir not found: {args.images_dir}", file=sys.stderr)
        return 2
    if not args.level_mapping.exists():
        print(f"ERROR: level-mapping not found: {args.level_mapping}", file=sys.stderr)
        return 2
    if not args.weights.exists():
        print(f"ERROR: weights not found: {args.weights}", file=sys.stderr)
        return 2

    try:
        from ultralytics import YOLO
    except ImportError:
        print("pip install ultralytics", file=sys.stderr)
        return 3

    items = load_flat_list(args.level_mapping, filename_suffix=args.filename_suffix)
    print(f"Loaded {len(items)} level-identified images (suffix={args.filename_suffix}) "
          f"across {len(set(i[0] for i in items))} levels")

    processed = load_processed_filenames(args.output) if args.resume else set()
    if processed:
        print(f"Resume mode: {len(processed)} already processed, skipping")

    items = [it for it in items if it[1] not in processed]
    if args.limit > 0:
        items = items[: args.limit]
    if not items:
        print("Nothing to process. Done.")
        return 0

    print(f"Processing {len(items)} images (batch={args.batch}, imgsz={args.imgsz}, conf={args.conf})")
    print(f"Loading model: {args.weights}")
    model = YOLO(str(args.weights))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_f = args.output.open("a", encoding="utf-8")

    t0 = time.time()
    written = 0
    missing = 0
    errors = 0

    for chunk_start in range(0, len(items), args.batch):
        chunk = items[chunk_start : chunk_start + args.batch]
        paths = []
        meta = []
        for level, fn, seq in chunk:
            ip = args.images_dir / fn
            if not ip.exists():
                missing += 1
                continue
            paths.append(str(ip))
            meta.append((level, fn, seq))
        if not paths:
            continue

        try:
            results = model.predict(
                source=paths,
                conf=args.conf,
                iou=args.iou,
                imgsz=args.imgsz,
                device=args.device,
                verbose=False,
                save=False,
            )
        except Exception as e:
            print(f"[BATCH ERROR at {chunk_start}] {e}", file=sys.stderr)
            errors += len(paths)
            continue

        for r, (level, fn, seq) in zip(results, meta):
            rec = make_record(level, fn, seq, r)
            out_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1

        if written > 0 and written % (args.batch * 10) == 0:
            out_f.flush()
            elapsed = time.time() - t0
            rate = written / elapsed if elapsed > 0 else 0
            eta = (len(items) - written) / rate if rate > 0 else 0
            print(
                f"  {written}/{len(items)} ({100*written/len(items):.1f}%)  "
                f"rate={rate:.1f} img/s  ETA={eta/60:.1f}m  missing={missing}  err={errors}"
            )

    out_f.close()
    elapsed = time.time() - t0
    print(f"\nDone. Written {written} records in {elapsed:.1f}s ({written/elapsed:.1f} img/s)")
    print(f"Missing images: {missing}")
    print(f"Batch errors: {errors}")
    print(f"Output: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
