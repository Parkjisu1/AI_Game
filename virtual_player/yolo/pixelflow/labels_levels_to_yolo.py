"""
검수된 level XML → YOLO 학습 데이터셋 생성

- 입력: labeling/labels_levels/level_NNN.xml (검수 완료)
- 출력: dataset_levels/{images,labels}/{train,val}
- 기믹 클래스 제외 (이번 주 목표: 셀만)
- 검수된 범위만 사용 (--max-level 옵션)
"""
from __future__ import annotations
import argparse
import shutil
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter

# 자동 경로 탐지
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import LABEL_XML_DIR, LABEL_IMAGES_DIR, DATASET_DIR

DEFAULT_XML = LABEL_XML_DIR
DEFAULT_IMG = LABEL_IMAGES_DIR
DEFAULT_OUT = DATASET_DIR

SEED = 42


def scan_classes(xml_files: list[Path], exclude_gimik: bool = True) -> list[str]:
    """발견된 클래스 목록 (셀만)."""
    seen = []
    seen_set = set()
    for xml in xml_files:
        try:
            tree = ET.parse(xml)
        except ET.ParseError:
            continue
        for obj in tree.getroot().findall("object"):
            name = (obj.find("name").text or "").strip()
            if not name:
                continue
            if exclude_gimik and ("gimik" in name.lower() or "gimmick" in name.lower()):
                continue
            if name not in seen_set:
                seen_set.add(name)
                seen.append(name)
    # cell 순으로 정렬
    return sorted(seen)


def convert_xml(xml_path: Path, class_to_id: dict[str, int]) -> list[str]:
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []
    root = tree.getroot()
    w = int(root.find("size/width").text)
    h = int(root.find("size/height").text)

    lines = []
    for obj in root.findall("object"):
        name = (obj.find("name").text or "").strip()
        cid = class_to_id.get(name)
        if cid is None:
            continue
        bb = obj.find("bndbox")
        xmin = int(float(bb.find("xmin").text))
        ymin = int(float(bb.find("ymin").text))
        xmax = int(float(bb.find("xmax").text))
        ymax = int(float(bb.find("ymax").text))
        cx = ((xmin + xmax) / 2) / w
        cy = ((ymin + ymax) / 2) / h
        bw = (xmax - xmin) / w
        bh = (ymax - ymin) / h
        if 0 <= cx <= 1 and 0 <= cy <= 1 and 0 < bw <= 1 and 0 < bh <= 1:
            lines.append(f"{cid} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    return lines


def find_image_for(xml: Path, img_dir: Path) -> Path | None:
    for ext in (".png", ".jpg", ".jpeg"):
        p = img_dir / f"{xml.stem}{ext}"
        if p.exists():
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--xml-dir", type=Path, default=DEFAULT_XML)
    ap.add_argument("--img-dir", type=Path, default=DEFAULT_IMG)
    ap.add_argument("--dataset-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-level", type=int, default=132,
                    help="이 레벨까지만 학습 (level_NNN.xml에서 NNN <= max-level)")
    ap.add_argument("--val-ratio", type=float, default=0.2)
    args = ap.parse_args()

    # 검수된 범위만
    xml_files = []
    for p in sorted(args.xml_dir.glob("level_*.xml")):
        try:
            num = int(p.stem.split("_")[1])
        except (ValueError, IndexError):
            continue
        if num <= args.max_level:
            xml_files.append(p)

    print(f"[input]  {len(xml_files)} XMLs (level <= {args.max_level})")
    print(f"[output] {args.dataset_dir}")

    # 클래스 자동 수집 (기믹 제외)
    classes = scan_classes(xml_files, exclude_gimik=True)
    class_to_id = {n: i for i, n in enumerate(classes)}

    print(f"\n[classes] {len(classes)}개 (기믹 제외):")
    for i, c in enumerate(classes):
        print(f"  [{i:2d}] {c}")

    # 출력 폴더 정리
    args.dataset_dir.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val"):
        for sub in ("images", "labels"):
            d = args.dataset_dir / sub / split
            if d.exists():
                for f in d.iterdir():
                    if f.is_file():
                        f.unlink()
            d.mkdir(parents=True, exist_ok=True)

    # classes.txt
    (args.dataset_dir / "classes.txt").write_text(
        "\n".join(classes) + "\n", encoding="utf-8"
    )

    # train/val 분할
    random.seed(SEED)
    shuffled = xml_files.copy()
    random.shuffle(shuffled)
    val_count = max(1, int(len(shuffled) * args.val_ratio))
    val_set = set(shuffled[:val_count])

    # 변환
    used = 0
    skipped = 0
    total_bbox = 0
    cls_count: Counter = Counter()

    for xml in xml_files:
        img = find_image_for(xml, args.img_dir)
        if img is None:
            skipped += 1
            continue
        lines = convert_xml(xml, class_to_id)
        if not lines:
            skipped += 1
            continue

        split = "val" if xml in val_set else "train"
        shutil.copy2(img, args.dataset_dir / "images" / split / img.name)
        (args.dataset_dir / "labels" / split / f"{img.stem}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        used += 1
        total_bbox += len(lines)
        for ln in lines:
            cid = int(ln.split()[0])
            cls_count[classes[cid]] += 1

    # dataset.yaml
    names_str = "[" + ", ".join(f"'{c}'" for c in classes) + "]"
    yaml = (
        f"path: {args.dataset_dir}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"nc: {len(classes)}\n"
        f"names: {names_str}\n"
    )
    (args.dataset_dir / "dataset.yaml").write_text(yaml, encoding="utf-8")

    print(f"\n[done]")
    print(f"  사용:  {used} / {len(xml_files)}")
    print(f"  스킵:  {skipped}")
    print(f"  총 bbox: {total_bbox:,}")
    print(f"  train: {used - val_count}장")
    print(f"  val:   {val_count}장")
    print()
    print("[클래스별 bbox]")
    for c in classes:
        bar = "#" * min(40, cls_count[c] // 100)
        print(f"  {c:<22s} {cls_count[c]:6d}  {bar}")
    print()
    print(f"학습 명령:")
    print(f"  python train_auto.py  (단, train_auto.py의 DATA_YAML과 RUN_NAME 수정 필요)")


if __name__ == "__main__":
    main()
