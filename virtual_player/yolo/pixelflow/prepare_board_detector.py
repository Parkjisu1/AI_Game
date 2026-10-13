"""Board 검출용 YOLO 데이터셋 — board 라벨만 추출"""
import os, random, shutil
import xml.etree.ElementTree as ET

SRC_IMG = r"E:\AI\virtual_player\yolo\pixelflow\labeling\images"
SRC_LBL = r"E:\AI\virtual_player\yolo\pixelflow\labeling\labels"
DST = r"E:\AI\virtual_player\yolo\pixelflow\dataset_board"

def extract_board_labels(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    W = int(root.find('size/width').text)
    H = int(root.find('size/height').text)

    labels = []
    for obj in root.findall('object'):
        if obj.find('name').text.strip().lower() == 'board':
            bb = obj.find('bndbox')
            xmin, ymin = int(bb.find('xmin').text), int(bb.find('ymin').text)
            xmax, ymax = int(bb.find('xmax').text), int(bb.find('ymax').text)
            cx = (xmin + xmax) / 2 / W
            cy = (ymin + ymax) / 2 / H
            w = (xmax - xmin) / W
            h = (ymax - ymin) / H
            labels.append(f"0 {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return labels

def main():
    for split in ['train', 'val']:
        os.makedirs(f"{DST}/images/{split}", exist_ok=True)
        os.makedirs(f"{DST}/labels/{split}", exist_ok=True)

    xmls = sorted([f for f in os.listdir(SRC_LBL) if f.endswith('.xml')])
    valid = []
    for xml_name in xmls:
        base = xml_name.replace('.xml', '')
        labels = extract_board_labels(os.path.join(SRC_LBL, xml_name))
        if labels:
            valid.append((base, labels))
            print(f"  {base}: {len(labels)} board bbox")

    random.seed(42)
    random.shuffle(valid)
    split = max(1, int(len(valid) * 0.75))

    for i, (base, labels) in enumerate(valid):
        s = 'train' if i < split else 'val'
        shutil.copy2(f"{SRC_IMG}/{base}.png", f"{DST}/images/{s}/{base}.png")
        with open(f"{DST}/labels/{s}/{base}.txt", 'w') as f:
            f.write('\n'.join(labels) + '\n')

    with open(f"{DST}/dataset.yaml", 'w') as f:
        f.write(f"path: {DST}\ntrain: images/train\nval: images/val\nnc: 1\nnames: ['board']\n")

    print(f"\nTrain: {split}, Val: {len(valid)-split}")

if __name__ == '__main__':
    main()
