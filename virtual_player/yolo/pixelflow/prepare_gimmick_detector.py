"""기믹 검출용 YOLO 데이터셋 — gimmick 라벨만 추출 (전체 이미지 사용)"""
import os, random, shutil
import xml.etree.ElementTree as ET

SRC_IMG = r"E:\AI\virtual_player\yolo\pixelflow\labeling\images_levels"
SRC_LBL = r"E:\AI\virtual_player\yolo\pixelflow\labeling\labels_levels"
DST = r"E:\AI\virtual_player\yolo\pixelflow\dataset_gimmick"

# 단일 클래스로 통합 (10종 기믹 → gimmick 하나)
CLASSES = ['gimmick']
NAME_MAP = {
    'hidden gimik': 0,
    'pinata gimik': 0,
    'snake gimik': 0,
    'ice gimik': 0,
    'block gimik': 0,
    'wall gimik': 0,
    'key gimik': 0,
    'door gimik': 0,
    'egg gimik': 0,
    'cannon gimik': 0,
}
GIMMICK_NAMES = set(NAME_MAP.keys())

def extract(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    W = int(root.find('size/width').text)
    H = int(root.find('size/height').text)
    labels = []
    for obj in root.findall('object'):
        name = obj.find('name').text.strip().lower()
        cls_id = NAME_MAP.get(name)
        if cls_id is None:
            continue
        bb = obj.find('bndbox')
        xmin, ymin = int(bb.find('xmin').text), int(bb.find('ymin').text)
        xmax, ymax = int(bb.find('xmax').text), int(bb.find('ymax').text)
        cx = (xmin + xmax) / 2 / W
        cy = (ymin + ymax) / 2 / H
        w = (xmax - xmin) / W
        h = (ymax - ymin) / H
        labels.append(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return labels

def main():
    for s in ['train', 'val']:
        os.makedirs(f"{DST}/images/{s}", exist_ok=True)
        os.makedirs(f"{DST}/labels/{s}", exist_ok=True)

    valid = []
    for xml_name in sorted(os.listdir(SRC_LBL)):
        if not xml_name.endswith('.xml'): continue
        base = xml_name.replace('.xml', '')
        labels = extract(os.path.join(SRC_LBL, xml_name))
        if labels:
            valid.append((base, labels))
            print(f"  {base}: {len(labels)} gimmicks")

    if not valid:
        print("No gimmick labels found!")
        return

    random.seed(42)
    random.shuffle(valid)
    split = max(1, int(len(valid) * 0.75))

    for i, (base, labels) in enumerate(valid):
        s = 'train' if i < split else 'val'
        shutil.copy2(f"{SRC_IMG}/{base}.png", f"{DST}/images/{s}/{base}.png")
        with open(f"{DST}/labels/{s}/{base}.txt", 'w') as f:
            f.write('\n'.join(labels) + '\n')

    with open(f"{DST}/dataset.yaml", 'w') as f:
        f.write(f"path: {DST}\ntrain: images/train\nval: images/val\n")
        f.write(f"nc: {len(CLASSES)}\nnames: {CLASSES}\n")

    print(f"\nTrain: {split}, Val: {len(valid)-split}, Total gimmicks: {sum(len(l) for _,l in valid)}")

if __name__ == '__main__':
    main()
