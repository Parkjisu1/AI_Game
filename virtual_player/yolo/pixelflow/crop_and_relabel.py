"""
board 라벨로 크롭 → 셀 라벨 좌표를 크롭 기준으로 변환 → 데이터셋 생성
"""
import os, random
import xml.etree.ElementTree as ET
from PIL import Image

SRC_IMG = r"E:\AI\virtual_player\yolo\pixelflow\labeling\images"
SRC_LBL = r"E:\AI\virtual_player\yolo\pixelflow\labeling\labels"
DST = r"E:\AI\virtual_player\yolo\pixelflow\dataset_crop"

CLASSES = [
    'block_purple', 'block_yellow', 'block_green', 'block_blue',
    'block_red', 'block_pink', 'block_white', 'block_black',
    'block_orange', 'block_cyan', 'block_brown', 'gimmick',
]

NAME_MAP = {
    'purple cell': 0, 'yellow cell': 1, 'green cell': 2, 'dark green cell': 2,
    'blue cell': 3, 'red cell': 4, 'pink cell': 5, 'hot pink cell': 5,
    'white cell': 6, 'whtie cell': 6, 'white yellow cell': 1,
    'black cell': 7, 'orange cell': 8, 'sky blue cell': 9,
    'brown cell': 10, 'brown red cell': 10,
    'pinata gimik': 11, 'ice gimik': 11, 'key gimik': 11, 'hidden gimik': 11,
}


def process(xml_path, img_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    W = int(root.find('size/width').text)
    H = int(root.find('size/height').text)

    # board 바운딩박스 찾기 (가장 큰 것)
    boards = []
    cells = []
    for obj in root.findall('object'):
        name = obj.find('name').text.strip().lower()
        bb = obj.find('bndbox')
        xmin = int(bb.find('xmin').text)
        ymin = int(bb.find('ymin').text)
        xmax = int(bb.find('xmax').text)
        ymax = int(bb.find('ymax').text)
        if name == 'board':
            boards.append((xmin, ymin, xmax, ymax))
        else:
            cls_id = NAME_MAP.get(name)
            if cls_id is not None:
                cells.append((cls_id, xmin, ymin, xmax, ymax))

    if not boards:
        return None, 0

    # 가장 큰 board 사용
    board = max(boards, key=lambda b: (b[2]-b[0]) * (b[3]-b[1]))
    bx1, by1, bx2, by2 = board
    bw = bx2 - bx1
    bh = by2 - by1

    # 이미지 크롭
    img = Image.open(img_path)
    crop = img.crop((bx1, by1, bx2, by2))

    # 셀 라벨을 크롭 좌표로 변환
    labels = []
    for cls_id, xmin, ymin, xmax, ymax in cells:
        # 보드 밖에 있는 셀은 무시
        if xmax <= bx1 or xmin >= bx2 or ymax <= by1 or ymin >= by2:
            continue

        # 크롭 좌표로 변환 + 클리핑
        cx1 = max(0, xmin - bx1)
        cy1 = max(0, ymin - by1)
        cx2 = min(bw, xmax - bx1)
        cy2 = min(bh, ymax - by1)

        # YOLO 포맷
        cx = (cx1 + cx2) / 2 / bw
        cy = (cy1 + cy2) / 2 / bh
        w_n = (cx2 - cx1) / bw
        h_n = (cy2 - cy1) / bh

        if w_n > 0.001 and h_n > 0.001:
            labels.append(f"{cls_id} {cx:.6f} {cy:.6f} {w_n:.6f} {h_n:.6f}")

    return crop, labels


def main():
    os.makedirs(f"{DST}/images/train", exist_ok=True)
    os.makedirs(f"{DST}/images/val", exist_ok=True)
    os.makedirs(f"{DST}/labels/train", exist_ok=True)
    os.makedirs(f"{DST}/labels/val", exist_ok=True)

    xmls = [f for f in os.listdir(SRC_LBL) if f.endswith('.xml')]
    results = []

    for xml_name in sorted(xmls):
        base = xml_name.replace('.xml', '')
        img_path = os.path.join(SRC_IMG, f"{base}.png")
        xml_path = os.path.join(SRC_LBL, xml_name)

        if not os.path.exists(img_path):
            continue

        crop, labels = process(xml_path, img_path)
        if crop is None:
            print(f"  SKIP {base}: no board label")
            continue

        results.append((base, crop, labels))
        print(f"  {base}: board cropped {crop.size[0]}x{crop.size[1]}, {len(labels)} cell labels")

    # train/val 분할 (80/20)
    random.seed(42)
    random.shuffle(results)
    split = max(1, int(len(results) * 0.8))

    total = 0
    for i, (base, crop, labels) in enumerate(results):
        split_name = 'train' if i < split else 'val'
        crop.convert('RGB').save(f"{DST}/images/{split_name}/{base}.jpg")
        with open(f"{DST}/labels/{split_name}/{base}.txt", 'w') as f:
            f.write('\n'.join(labels) + '\n' if labels else '')
        total += len(labels)
        print(f"  [{split_name}] {base}: {len(labels)} labels")

    # dataset.yaml
    with open(f"{DST}/dataset.yaml", 'w') as f:
        f.write(f"path: {DST}\ntrain: images/train\nval: images/val\n")
        f.write(f"nc: {len(CLASSES)}\nnames: {CLASSES}\n")

    print(f"\nTotal: {total} labels, {len(results)} images")
    print(f"Train: {split}, Val: {len(results)-split}")


if __name__ == '__main__':
    main()
