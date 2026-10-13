"""cell_only 단일 클래스 학습 데이터셋 생성 (204장 전체 활용)

입력: labeling/labels_levels/*.xml (204개)
출력: dataset_cell_only/ (single class 'cell')
      모든 non-gimik bbox를 class 0 'cell'로 통합

--max-level 기본 300 (전체)
"""
from __future__ import annotations
import argparse
import shutil
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_XML = Path(r"E:\AI\virtual_player\yolo\pixelflow\labeling\labels_levels")
DEFAULT_IMG = Path(r"E:\AI\virtual_player\yolo\pixelflow\labeling\images_levels")
DEFAULT_OUT = Path(r"E:\AI\virtual_player\yolo\pixelflow\dataset_cell_only")

SEED = 42


def convert_xml(xml_path: Path) -> list[str]:
    """모든 non-gimik bbox를 class 0 'cell'로 변환."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []
    root = tree.getroot()
    w = int(root.find("size/width").text)
    h = int(root.find("size/height").text)

    lines = []
    for obj in root.findall("object"):
        name = (obj.find("name").text or "").strip().lower()
        # 기믹 제외
        if "gimik" in name or "gimmick" in name:
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
            # class 0 ('cell')로 고정
            lines.append(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    return lines


def find_image(xml: Path, img_dir: Path) -> Path | None:
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
    ap.add_argument("--max-level", type=int, default=300)
    ap.add_argument("--val-ratio", type=float, default=0.2)
    ap.add_argument("--min-bboxes", type=int, default=50,
                    help="XML에 bbox가 이 수 미만이면 스킵 (부분 라벨 제외)")
    args = ap.parse_args()

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

    # 출력 폴더 초기화
    if args.dataset_dir.exists():
        shutil.rmtree(args.dataset_dir)
    for split in ("train", "val"):
        for sub in ("images", "labels"):
            (args.dataset_dir / sub / split).mkdir(parents=True, exist_ok=True)

    # 1차: 변환 가능한 것만 수집 (부분 라벨 제외)
    valid: list[tuple[Path, list[str]]] = []
    partial_skipped = 0
    for xml in xml_files:
        img = find_image(xml, args.img_dir)
        if img is None:
            continue
        lines = convert_xml(xml)
        if len(lines) < args.min_bboxes:
            partial_skipped += 1
            continue
        valid.append((img, lines))

    print(f"  [valid]    {len(valid)} images (bbox >= {args.min_bboxes})")
    print(f"  [skipped]  {partial_skipped} images (partial label)")

    # train/val 분할
    random.seed(SEED)
    random.shuffle(valid)
    val_count = max(1, int(len(valid) * args.val_ratio))

    total_bbox = 0
    for i, (img, lines) in enumerate(valid):
        split = "val" if i < val_count else "train"
        shutil.copy2(img, args.dataset_dir / "images" / split / img.name)
        (args.dataset_dir / "labels" / split / f"{img.stem}.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
        total_bbox += len(lines)

    # dataset.yaml (portable: path: .)
    yaml = (
        "path: .\n"
        "train: images/train\n"
        "val: images/val\n"
        "nc: 1\n"
        "names: ['cell']\n"
    )
    (args.dataset_dir / "dataset.yaml").write_text(yaml, encoding="utf-8")

    print(f"\n[done]")
    print(f"  Train: {len(valid) - val_count}장")
    print(f"  Val:   {val_count}장")
    print(f"  Total bbox: {total_bbox:,}")
    print(f"\n  Dataset: {args.dataset_dir}")


if __name__ == "__main__":
    main()
