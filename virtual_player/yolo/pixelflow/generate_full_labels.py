"""
크롭 이미지에서 격자선으로 전체 셀 위치 감지 → HSV 색상 분류 → PascalVOC XML 생성
labelImg에서 열어서 오분류만 수정하면 됨
"""
import os, cv2, numpy as np
from lxml import etree

SRC_IMG = r"E:\AI\virtual_player\yolo\pixelflow\labeling\images"
SRC_LBL = r"E:\AI\virtual_player\yolo\pixelflow\labeling\labels"
CROP_DIR = r"E:\AI\virtual_player\yolo\pixelflow\labeling\crops"

# XML에서 board bbox 추출
import xml.etree.ElementTree as ET

CLASSES = [
    'purple_cell', 'yellow_cell', 'green_cell', 'blue_cell',
    'red_cell', 'pink_cell', 'white_cell', 'black_cell',
    'orange_cell', 'sky_blue_cell', 'brown_cell', 'gimmick',
]


def classify_hsv(h, s, v):
    # 보드 배경 제거: 어둡거나 채도 낮으면 skip
    if v < 80: return None           # 어두운 배경
    if s < 50 and v < 150: return None  # 회색 배경
    if v < 100 and s < 120: return None # 어두운 남색 배경 (핵심 필터)

    # 검은 블록 (밝기 낮지만 어느정도 보임)
    if v < 120 and s < 100: return 'black_cell'
    # 흰색
    if v > 180 and s < 60: return 'white_cell'
    # 채도 너무 낮으면 skip
    if s < 50: return None

    if h < 10 or h > 170: return 'red_cell'
    elif 10 <= h < 22: return 'orange_cell'
    elif 22 <= h < 38: return 'yellow_cell'
    elif 38 <= h < 78: return 'green_cell'
    elif 78 <= h < 98: return 'sky_blue_cell'
    elif 98 <= h < 130: return 'blue_cell'
    elif 130 <= h < 148: return 'purple_cell'
    elif 148 <= h < 170: return 'pink_cell'
    return None


def detect_pitch(profile):
    centered = profile - profile.mean()
    corr = np.correlate(centered, centered, mode='full')
    corr = corr[len(centered):]
    for i in range(15, len(corr) - 1):
        if corr[i] > corr[i-1] and corr[i] > corr[i+1]:
            return i
    return 30


def find_grid_lines(gray, axis, pitch):
    profile = np.mean(gray, axis=0) if axis == 'col' else np.mean(gray, axis=1)
    n = len(profile)
    best_phase, best_score = 0, float('inf')
    for phase in range(min(pitch, n)):
        positions = list(range(phase, n, pitch))
        if len(positions) < 2: continue
        score = sum(np.min(profile[max(0,p-2):min(n,p+3)]) for p in positions) / len(positions)
        if score < best_score:
            best_score = score
            best_phase = phase
    gridlines = []
    pos = best_phase
    while pos < n:
        lo, hi = max(0, pos-3), min(n, pos+4)
        gridlines.append(int(lo + np.argmin(profile[lo:hi])))
        pos += pitch
    return gridlines


def add_edges(gl, size):
    if len(gl) < 2: return gl
    gap = int(np.median(np.diff(gl)))
    if gl[0] > gap * 0.5:
        gl = [gl[0] - gap] + gl
    if size - gl[-1] > gap * 0.5:
        gl.append(gl[-1] + gap)
    return gl


def create_voc_xml(filename, width, height, objects):
    """PascalVOC XML 생성"""
    root = ET.Element('annotation')
    ET.SubElement(root, 'folder').text = 'crops'
    ET.SubElement(root, 'filename').text = filename
    ET.SubElement(root, 'path').text = os.path.join(CROP_DIR, filename)
    src = ET.SubElement(root, 'source')
    ET.SubElement(src, 'database').text = 'Unknown'
    size = ET.SubElement(root, 'size')
    ET.SubElement(size, 'width').text = str(width)
    ET.SubElement(size, 'height').text = str(height)
    ET.SubElement(size, 'depth').text = '3'
    ET.SubElement(root, 'segmented').text = '0'

    for name, xmin, ymin, xmax, ymax in objects:
        obj = ET.SubElement(root, 'object')
        ET.SubElement(obj, 'name').text = name
        ET.SubElement(obj, 'pose').text = 'Unspecified'
        ET.SubElement(obj, 'truncated').text = '0'
        ET.SubElement(obj, 'difficult').text = '0'
        bb = ET.SubElement(obj, 'bndbox')
        ET.SubElement(bb, 'xmin').text = str(int(xmin))
        ET.SubElement(bb, 'ymin').text = str(int(ymin))
        ET.SubElement(bb, 'xmax').text = str(int(xmax))
        ET.SubElement(bb, 'ymax').text = str(int(ymax))

    return root


def process_image(img_path, xml_path):
    # board bbox 추출
    tree = ET.parse(xml_path)
    root = tree.getroot()
    boards = []
    for obj in root.findall('object'):
        if obj.find('name').text.strip().lower() == 'board':
            bb = obj.find('bndbox')
            boards.append((
                int(bb.find('xmin').text), int(bb.find('ymin').text),
                int(bb.find('xmax').text), int(bb.find('ymax').text)
            ))
    if not boards:
        return None

    board = max(boards, key=lambda b: (b[2]-b[0])*(b[3]-b[1]))
    bx1, by1, bx2, by2 = board

    # 크롭
    img = cv2.imread(img_path)
    crop = img[by1:by2, bx1:bx2]
    bh, bw = crop.shape[:2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).astype(float)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

    # 격자선
    pitch_h = detect_pitch(np.mean(gray, axis=0))
    pitch_v = detect_pitch(np.mean(gray, axis=1))
    if pitch_v > pitch_h * 1.5: pitch_v = pitch_v // 2
    elif pitch_h > pitch_v * 1.5: pitch_h = pitch_h // 2

    h_gl = add_edges(find_grid_lines(gray, 'col', pitch_h), bw)
    v_gl = add_edges(find_grid_lines(gray, 'row', pitch_v), bh)

    n_cols = len(h_gl) - 1
    n_rows = len(v_gl) - 1

    # 각 셀 분류
    objects = []
    for row in range(n_rows):
        ry1 = max(0, v_gl[row] + 2)
        ry2 = min(bh, v_gl[row+1] - 2)
        for col in range(n_cols):
            rx1 = max(0, h_gl[col] + 2)
            rx2 = min(bw, h_gl[col+1] - 2)
            if ry2 <= ry1 or rx2 <= rx1: continue

            cell_hsv = hsv[ry1:ry2, rx1:rx2]
            if cell_hsv.size == 0: continue
            avg_h, avg_s, avg_v = np.mean(cell_hsv, axis=(0,1))

            cls_name = classify_hsv(avg_h, avg_s, avg_v)
            if cls_name is None: continue

            objects.append((cls_name, h_gl[col], v_gl[row], h_gl[col+1], v_gl[row+1]))

    return crop, objects, bw, bh


def main():
    os.makedirs(CROP_DIR, exist_ok=True)

    for fname in sorted(os.listdir(SRC_IMG)):
        if not fname.endswith('.png'): continue
        base = fname.replace('.png', '')
        xml_path = os.path.join(SRC_LBL, f"{base}.xml")
        img_path = os.path.join(SRC_IMG, fname)

        if not os.path.exists(xml_path):
            continue

        result = process_image(img_path, xml_path)
        if result is None:
            print(f"  SKIP {base}: no board")
            continue

        crop, objects, bw, bh = result

        # 크롭 이미지 저장
        crop_path = os.path.join(CROP_DIR, f"{base}.png")
        cv2.imwrite(crop_path, crop)

        # XML 저장
        xml_root = create_voc_xml(f"{base}.png", bw, bh, objects)
        xml_str = ET.tostring(xml_root, encoding='unicode')
        # 들여쓰기
        import xml.dom.minidom
        pretty = xml.dom.minidom.parseString(xml_str).toprettyxml(indent='\t')
        # XML 선언 제거
        lines = pretty.split('\n')[1:]
        xml_out = os.path.join(CROP_DIR, f"{base}.xml")
        with open(xml_out, 'w') as f:
            f.write('\n'.join(lines))

        from collections import Counter
        cnt = Counter(o[0] for o in objects)
        top = ', '.join(f"{k}:{v}" for k,v in cnt.most_common(3))
        print(f"  {base}: {bw}x{bh}, {len(objects)} cells ({top})")

    print(f"\nDone! Crops saved to: {CROP_DIR}")
    print(f"Open in labelImg -> review/fix colors -> save")


if __name__ == '__main__':
    main()
