"""
labelImg XML → YOLO 자동 변환 파이프라인

- labeling/labels/ 의 모든 XML을 전수 스캔
- 실제 라벨명을 그대로 유지 (공백/오타 포함)
- classes.txt를 안정적으로 생성 (기존 ID 보존, 신규는 뒤에 추가)
- YOLO .txt 라벨 + train/val 분할 + dataset.yaml 자동 생성

사용법:
  python labels_to_yolo.py                 # 기본 경로로 실행
  python labels_to_yolo.py --val-ratio 0.2 # 검증 비율 조정

재실행 안전: 기존 classes.txt의 순서를 보존하며, 신규 클래스만 뒤에 추가
"""
import os
import shutil
import random
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

# ----------------- 기본 경로 -----------------
BASE = Path(r"E:\AI\virtual_player\yolo\pixelflow")
LABELING_DIR = BASE / "labeling"
XML_DIR = LABELING_DIR / "labels"
IMG_SRC_DIR = LABELING_DIR / "images"
DATASET_DIR = BASE / "dataset_auto"
CLASSES_FILE = DATASET_DIR / "classes.txt"

# 난수 시드 (재현성)
SEED = 42


def scan_xml_classes(xml_dir: Path) -> list[str]:
    """모든 XML을 스캔해서 발견된 클래스명 집합 반환 (발견 순서 유지)."""
    discovered = []
    seen = set()
    for xml_path in sorted(xml_dir.glob("*.xml")):
        try:
            tree = ET.parse(xml_path)
        except ET.ParseError as e:
            print(f"  [SKIP] parse error: {xml_path.name} — {e}")
            continue
        for obj in tree.getroot().findall("object"):
            name = (obj.find("name").text or "").strip()
            if name and name not in seen:
                seen.add(name)
                discovered.append(name)
    return discovered


def load_existing_classes(path: Path) -> list[str]:
    """기존 classes.txt 로드 (없으면 빈 리스트)."""
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def sort_classes_stable(discovered: list[str], existing: list[str]) -> list[str]:
    """
    안정 정렬:
    - existing의 순서를 보존 (기존 YOLO class ID 유지)
    - discovered 중 existing에 없는 것은 맨 뒤에 추가
    - 정렬 규칙: cell 계열 먼저, gimik/gimmick 뒤에 (신규 클래스만 적용)
    """
    result = list(existing)  # 기존 순서 유지
    existing_set = set(existing)

    new_items = [c for c in discovered if c not in existing_set]
    # 신규 항목: cell류 먼저, gimik/gimmick 뒤로
    cells_new = [c for c in new_items if "gimik" not in c and "gimmick" not in c]
    gimmicks_new = [c for c in new_items if "gimik" in c or "gimmick" in c]
    result.extend(sorted(cells_new))
    result.extend(sorted(gimmicks_new))
    return result


def convert_xml_to_yolo(xml_path: Path, class_to_id: dict[str, int]) -> list[str]:
    """XML 1개 → YOLO 라인 리스트 (cx, cy, w, h 정규화)."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []
    root = tree.getroot()

    w = int(root.find("size/width").text)
    h = int(root.find("size/height").text)

    lines = []
    unknown = []
    for obj in root.findall("object"):
        name = (obj.find("name").text or "").strip()
        cid = class_to_id.get(name)
        if cid is None:
            unknown.append(name)
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

        # 경계 체크 (비정상 bbox 제외)
        if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < bw <= 1 and 0 < bh <= 1):
            continue

        lines.append(f"{cid} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

    if unknown:
        print(f"  [WARN] {xml_path.name}: unknown classes skipped: {set(unknown)}")
    return lines


def setup_dataset_dirs(root: Path):
    """dataset_auto 폴더 초기화 (images/labels × train/val)."""
    for split in ("train", "val"):
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)


def clear_split_dirs(root: Path):
    """기존 train/val 내용 삭제 (재실행 시 stale 파일 제거)."""
    for split in ("train", "val"):
        for sub in ("images", "labels"):
            d = root / sub / split
            if d.exists():
                for f in d.iterdir():
                    if f.is_file():
                        f.unlink()


def find_image_for_xml(xml_path: Path, img_dir: Path) -> Path | None:
    """XML과 같은 stem을 가진 이미지 파일 찾기."""
    stem = xml_path.stem
    for ext in (".png", ".jpg", ".jpeg"):
        p = img_dir / f"{stem}{ext}"
        if p.exists():
            return p
    # XML 내부의 <filename> 태그로도 시도
    try:
        root = ET.parse(xml_path).getroot()
        fn = root.find("filename")
        if fn is not None and fn.text:
            p = img_dir / fn.text
            if p.exists():
                return p
    except Exception:
        pass
    return None


def write_dataset_yaml(root: Path, classes: list[str]):
    """dataset.yaml 생성."""
    yaml_path = root / "dataset.yaml"
    # YOLO가 'names'를 파이썬 리스트/딕트로 읽으므로 안전하게 따옴표 씌움
    names_str = "[" + ", ".join(f"'{c}'" for c in classes) + "]"
    content = (
        f"path: {root}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"nc: {len(classes)}\n"
        f"names: {names_str}\n"
    )
    yaml_path.write_text(content, encoding="utf-8")
    return yaml_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--val-ratio", type=float, default=0.2)
    ap.add_argument("--xml-dir", type=Path, default=XML_DIR)
    ap.add_argument("--img-dir", type=Path, default=IMG_SRC_DIR)
    ap.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    args = ap.parse_args()

    print(f"[1/5] XML 스캔: {args.xml_dir}")
    discovered = scan_xml_classes(args.xml_dir)
    print(f"  발견된 클래스 {len(discovered)}개:")
    for i, c in enumerate(discovered):
        print(f"    [{i:2d}] {c}")

    # 기존 classes.txt 로드 (있으면 ID 보존)
    existing = load_existing_classes(args.dataset_dir / "classes.txt")
    if existing:
        print(f"\n[기존 classes.txt 발견: {len(existing)}개 클래스 → ID 보존]")

    final_classes = sort_classes_stable(discovered, existing)
    class_to_id = {name: idx for idx, name in enumerate(final_classes)}

    print(f"\n[2/5] 최종 클래스 {len(final_classes)}개:")
    for i, c in enumerate(final_classes):
        marker = " (신규)" if c not in existing else ""
        print(f"    [{i:2d}] {c}{marker}")

    # 출력 폴더 준비
    args.dataset_dir.mkdir(parents=True, exist_ok=True)
    setup_dataset_dirs(args.dataset_dir)
    clear_split_dirs(args.dataset_dir)

    # classes.txt 저장
    (args.dataset_dir / "classes.txt").write_text(
        "\n".join(final_classes) + "\n", encoding="utf-8"
    )

    # XML → YOLO 변환 + train/val 분할
    print(f"\n[3/5] XML 변환 + 이미지 복사")
    xml_files = sorted(args.xml_dir.glob("*.xml"))
    random.seed(SEED)
    random.shuffle(xml_files)

    val_count = max(1, int(len(xml_files) * args.val_ratio))
    val_files = set(xml_files[:val_count])

    total_bbox = 0
    used = 0
    skipped_no_img = 0

    for xml_path in xml_files:
        img_path = find_image_for_xml(xml_path, args.img_dir)
        if img_path is None:
            skipped_no_img += 1
            print(f"  [SKIP] no image: {xml_path.name}")
            continue

        lines = convert_xml_to_yolo(xml_path, class_to_id)
        if not lines:
            continue

        split = "val" if xml_path in val_files else "train"

        # 이미지 복사
        dst_img = args.dataset_dir / "images" / split / img_path.name
        shutil.copy2(img_path, dst_img)

        # 라벨 저장
        dst_lbl = args.dataset_dir / "labels" / split / f"{img_path.stem}.txt"
        dst_lbl.write_text("\n".join(lines) + "\n", encoding="utf-8")

        total_bbox += len(lines)
        used += 1

    print(f"  사용된 이미지: {used} / {len(xml_files)}")
    print(f"  이미지 없음 스킵: {skipped_no_img}")
    print(f"  총 bbox: {total_bbox:,}")

    # 분할 통계
    train_imgs = len(list((args.dataset_dir / "images" / "train").iterdir()))
    val_imgs = len(list((args.dataset_dir / "images" / "val").iterdir()))
    print(f"  train / val = {train_imgs} / {val_imgs}")

    # dataset.yaml 생성
    print(f"\n[4/5] dataset.yaml 생성")
    yaml_path = write_dataset_yaml(args.dataset_dir, final_classes)
    print(f"  -> {yaml_path}")

    # 클래스별 bbox 분포 (통계)
    print(f"\n[5/5] 클래스별 bbox 분포:")
    class_count = {c: 0 for c in final_classes}
    for split in ("train", "val"):
        for lbl_file in (args.dataset_dir / "labels" / split).glob("*.txt"):
            for ln in lbl_file.read_text().splitlines():
                if ln.strip():
                    cid = int(ln.split()[0])
                    class_count[final_classes[cid]] += 1
    for cname in final_classes:
        bar = "#" * min(50, class_count[cname] // 2)
        print(f"  [{class_to_id[cname]:2d}] {cname:<25s} {class_count[cname]:5d}  {bar}")

    print(f"\n[OK] 완료. 학습 명령:")
    print(f"  yolo detect train data={yaml_path} model=yolo11n.pt epochs=100 imgsz=1280")


if __name__ == "__main__":
    main()
