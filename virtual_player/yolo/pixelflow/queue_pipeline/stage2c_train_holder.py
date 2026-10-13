# Stage 2c: Train YOLO holder detector from labeled images.
# Converts VOC XML labels to YOLO format and trains a 1-class model.
#
# Usage:
#   python stage2c_train_holder.py \
#     --images path/to/labeling/images_queue \
#     --labels path/to/labeling/labels_queue \
#     --output-dataset path/to/dataset_holder \
#     --runs-dir path/to/runs \
#     --epochs 150 --imgsz 1280 --batch 4
from __future__ import annotations
import argparse
import random
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def voc_to_yolo(xml_path, class_map):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    size = root.find("size")
    w = int(size.find("width").text)
    h = int(size.find("height").text)
    lines = []
    for obj in root.findall("object"):
        name = (obj.find("name").text or "").strip().lower()
        if name not in class_map:
            continue
        cls_id = class_map[name]
        bb = obj.find("bndbox")
        x1 = float(bb.find("xmin").text)
        y1 = float(bb.find("ymin").text)
        x2 = float(bb.find("xmax").text)
        y2 = float(bb.find("ymax").text)
        cx = (x1 + x2) / 2 / w
        cy = (y1 + y2) / 2 / h
        bw = (x2 - x1) / w
        bh = (y2 - y1) / h
        lines.append(
            str(cls_id) + " "
            + ("%.6f" % cx) + " "
            + ("%.6f" % cy) + " "
            + ("%.6f" % bw) + " "
            + ("%.6f" % bh)
        )
    return lines


def build_dataset(images_dir, labels_dir, out_dir, class_map,
                  val_ratio=0.2, seed=42):
    images_dir = Path(images_dir)
    labels_dir = Path(labels_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for split in ("train", "val"):
        (out_dir / "images" / split).mkdir(parents=True, exist_ok=True)
        (out_dir / "labels" / split).mkdir(parents=True, exist_ok=True)

    # Collect labeled pairs
    xmls = sorted(labels_dir.glob("*.xml"))
    pairs = []
    for xml in xmls:
        img = images_dir / (xml.stem + ".png")
        if img.exists():
            pairs.append((img, xml))

    if len(pairs) < 5:
        print("ERROR: need at least 5 labeled images (got "
              + str(len(pairs)) + ")")
        sys.exit(1)

    random.seed(seed)
    random.shuffle(pairs)

    split_idx = max(1, int(len(pairs) * (1.0 - val_ratio)))
    train = pairs[:split_idx]
    val = pairs[split_idx:]
    if not val:
        val = train[:1]

    def copy_pairs(pair_list, split):
        count = 0
        for img, xml in pair_list:
            yolo_lines = voc_to_yolo(xml, class_map)
            if not yolo_lines:
                continue
            dst_img = out_dir / "images" / split / img.name
            dst_lbl = (out_dir / "labels" / split / (img.stem + ".txt"))
            shutil.copy2(img, dst_img)
            dst_lbl.write_text("\n".join(yolo_lines), encoding="utf-8")
            count += 1
        return count

    n_train = copy_pairs(train, "train")
    n_val = copy_pairs(val, "val")
    print("Train: " + str(n_train) + "  Val: " + str(n_val))

    # dataset.yaml
    names = sorted(class_map, key=lambda k: class_map[k])
    yaml_content = (
        "path: " + str(out_dir.resolve()).replace("\\", "/") + "\n"
        + "train: images/train\n"
        + "val: images/val\n"
        + "names:\n"
        + "\n".join("  " + str(class_map[n]) + ": " + n for n in names) + "\n"
    )
    (out_dir / "dataset.yaml").write_text(yaml_content, encoding="utf-8")
    return out_dir / "dataset.yaml"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--output-dataset", required=True)
    ap.add_argument("--runs-dir", default="runs")
    ap.add_argument("--name", default="holder_detector")
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--patience", type=int, default=40)
    ap.add_argument("--base-weights", default="yolov8s.pt")
    ap.add_argument("--single-class", action="store_true",
                    help="Use single 'holder' class only")
    args = ap.parse_args()

    if args.single_class:
        class_map = {"holder": 0}
    else:
        class_map = {"holder": 0, "current_balloon": 1}

    print("Building dataset...")
    yaml_path = build_dataset(
        args.images, args.labels, args.output_dataset, class_map
    )
    print("Dataset ready: " + str(yaml_path))

    print("Loading YOLO...")
    from ultralytics import YOLO
    model = YOLO(args.base_weights)

    print("Training...")
    model.train(
        data=str(yaml_path),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        patience=args.patience,
        project=args.runs_dir,
        name=args.name,
        exist_ok=True,
        workers=0,
        cache=False,
        amp=True,
    )
    print("Done. Best weights at: " + args.runs_dir + "/" + args.name
          + "/weights/best.pt")


if __name__ == "__main__":
    main()
