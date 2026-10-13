"""XML (PascalVOC) → YOLO 포맷 변환"""
import os, xml.etree.ElementTree as ET

LABEL_DIR = r"E:\AI\virtual_player\yolo\pixelflow\labeling\labels"

# 사용자가 입력한 클래스명 → YOLO 클래스 ID 매핑
CLASSES = [
    'block_purple',   # 0
    'block_yellow',   # 1
    'block_green',    # 2
    'block_blue',     # 3
    'block_red',      # 4
    'block_pink',     # 5
    'block_white',    # 6
    'block_black',    # 7
    'block_orange',   # 8
    'block_cyan',     # 9
    'block_brown',    # 10
    'gimmick',        # 11
]

NAME_MAP = {
    'purple cell':      0,
    'yellow cell':      1,
    'green cell':       2,
    'dark green cell':  2,
    'blue cell':        3,
    'red cell':         4,
    'pink cell':        5,
    'hot pink cell':    5,
    'white cell':       6,
    'whtie cell':       6,   # typo
    'white yellow cell':1,
    'black cell':       7,
    'orange cell':      8,
    'sky blue cell':    9,
    'brown cell':       10,
    'brown red cell':   10,
    'pinata gimik':     11,
    'ice gimik':        11,
    'key gimik':        11,
    'hidden gimik':     11,
}

def convert(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    w = int(root.find('size/width').text)
    h = int(root.find('size/height').text)

    labels = []
    for obj in root.findall('object'):
        name = obj.find('name').text.strip().lower()
        cls_id = NAME_MAP.get(name)
        if cls_id is None:
            print(f"  WARNING: unknown class '{name}' in {xml_path}")
            continue

        xmin = int(obj.find('bndbox/xmin').text)
        ymin = int(obj.find('bndbox/ymin').text)
        xmax = int(obj.find('bndbox/xmax').text)
        ymax = int(obj.find('bndbox/ymax').text)

        cx = ((xmin + xmax) / 2) / w
        cy = ((ymin + ymax) / 2) / h
        bw = (xmax - xmin) / w
        bh = (ymax - ymin) / h

        labels.append(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

    # .txt 저장
    txt_path = xml_path.replace('.xml', '.txt')
    with open(txt_path, 'w') as f:
        f.write('\n'.join(labels) + '\n')

    return len(labels)

total = 0
for fname in sorted(os.listdir(LABEL_DIR)):
    if fname.endswith('.xml'):
        n = convert(os.path.join(LABEL_DIR, fname))
        print(f"{fname} -> {n} labels")
        total += n

print(f"\nTotal: {total} labels converted")
print(f"Classes: {CLASSES}")
