"""
YOLO 데이터셋 v2 — 보드 영역만 크롭 + 개선된 색상 분류
핵심 변경:
1. 보드 영역만 크롭하여 셀이 크게 보이도록
2. HSV 기반 색상 분류로 정확도 향상
3. 크롭 이미지 + 라벨을 YOLO 포맷으로 저장
"""
import os, sys, shutil, random
import cv2
import numpy as np
from PIL import Image

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
    'empty',          # 11
]

SRC_DIR = r"E:\AI\virtual_player\data\pixelflow\images"
DST_DIR = r"E:\AI\virtual_player\yolo\pixelflow\dataset_v2"


def classify_hsv(h, s, v):
    """HSV 기반 색상 분류 (더 정확)"""
    # 너무 어두우면 skip (보드 배경)
    if v < 40:
        return None
    # 검은 블록 (약간 밝은 회색)
    if v < 80 and s < 80:
        return 7
    # 흰색
    if v > 180 and s < 50:
        return 6
    # 채도 낮으면 회색 계열 — skip
    if s < 40:
        return None

    # 색상(Hue) 기반 분류 (OpenCV: H=0~180)
    if h < 10 or h > 170:      # 빨강
        return 4
    elif 10 <= h < 22:          # 주황
        return 8
    elif 22 <= h < 35:          # 노랑
        return 1
    elif 35 <= h < 75:          # 초록
        return 2
    elif 75 <= h < 95:          # 시안
        return 9
    elif 95 <= h < 130:         # 파랑
        return 3
    elif 130 <= h < 145:        # 보라
        return 0
    elif 145 <= h < 165:        # 분홍
        return 5
    elif 165 <= h <= 170:       # 분홍~빨강
        return 5

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
    if axis == 'col':
        profile = np.mean(gray, axis=0)
    else:
        profile = np.mean(gray, axis=1)
    n = len(profile)
    best_phase = 0
    best_score = float('inf')
    for phase in range(min(pitch, n)):
        positions = list(range(phase, n, pitch))
        if len(positions) < 2:
            continue
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
    if len(gl) < 2:
        return gl
    gap = int(np.median(np.diff(gl)))
    if gl[0] > gap * 0.5:
        gl = [gl[0] - gap] + gl
    if size - gl[-1] > gap * 0.5:
        gl.append(gl[-1] + gap)
    return gl


def find_board_and_crop(img_bgr):
    """보드 영역 감지 후 크롭. (crop_img, x0, y0) 반환"""
    h, w = img_bgr.shape[:2]
    search = img_bgr[:int(h * 0.55)]

    # 밝은 픽셀 밀도로 보드 영역 찾기
    gray = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    _, bright = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY)

    row_d = bright.sum(axis=1).astype(float)
    col_d = bright.sum(axis=0).astype(float)
    thr_r = row_d.max() * 0.35
    thr_c = col_d.max() * 0.35
    ar = np.where(row_d > thr_r)[0]
    ac = np.where(col_d > thr_c)[0]

    if len(ar) == 0 or len(ac) == 0:
        return None, 0, 0

    y0, y1 = ar[0], ar[-1]
    x0, x1 = ac[0], ac[-1]

    # 약간의 패딩
    pad = 5
    y0 = max(0, y0 - pad)
    x0 = max(0, x0 - pad)
    y1 = min(search.shape[0], y1 + pad)
    x1 = min(w, x1 + pad)

    return img_bgr[y0:y1, x0:x1], x0, y0


def auto_label_cropped(crop_bgr):
    """크롭된 보드 이미지에서 셀 라벨 생성. 좌표는 크롭 이미지 기준."""
    bh, bw = crop_bgr.shape[:2]
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY).astype(float)
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)

    pitch_h = detect_pitch(np.mean(gray, axis=0))
    pitch_v = detect_pitch(np.mean(gray, axis=1))
    if pitch_v > pitch_h * 1.5:
        pitch_v = pitch_v // 2
    elif pitch_h > pitch_v * 1.5:
        pitch_h = pitch_h // 2

    h_gl = add_edges(find_grid_lines(gray, 'col', pitch_h), bw)
    v_gl = add_edges(find_grid_lines(gray, 'row', pitch_v), bh)

    n_cols = len(h_gl) - 1
    n_rows = len(v_gl) - 1
    if n_cols < 1 or n_rows < 1:
        return []

    labels = []
    for row in range(n_rows):
        ry1 = max(0, v_gl[row] + 3)
        ry2 = min(bh, v_gl[row+1] - 3)
        for col in range(n_cols):
            rx1 = max(0, h_gl[col] + 3)
            rx2 = min(bw, h_gl[col+1] - 3)
            if ry2 <= ry1 or rx2 <= rx1:
                continue

            cell_hsv = hsv[ry1:ry2, rx1:rx2]
            if cell_hsv.size == 0:
                continue
            avg_h, avg_s, avg_v = np.mean(cell_hsv, axis=(0,1))

            cls_id = classify_hsv(avg_h, avg_s, avg_v)
            if cls_id is None:
                continue

            # YOLO 포맷 (크롭 이미지 기준 정규화)
            cx = ((h_gl[col] + h_gl[col+1]) / 2) / bw
            cy = ((v_gl[row] + v_gl[row+1]) / 2) / bh
            w_n = (h_gl[col+1] - h_gl[col]) / bw
            h_n = (v_gl[row+1] - v_gl[row]) / bh

            labels.append((cls_id, cx, cy, w_n, h_n))

    return labels


def main():
    # 이미지 선택
    sample_indices = [
        1, 14, 44, 50, 100, 150, 200, 300, 400, 500,
        600, 700, 800, 900, 1000, 1500, 2000, 3000, 5000, 7000, 10000
    ]
    all_files = sorted(os.listdir(SRC_DIR))
    selected = []
    for idx in sample_indices:
        for suffix in [f"_{idx:04d}_before.png", f"_{idx:04d}_after.png"]:
            for f in all_files:
                if f.endswith(suffix):
                    selected.append(f)
    selected = sorted(set(selected))
    print(f"Selected {len(selected)} images")

    random.seed(42)
    random.shuffle(selected)
    split = int(len(selected) * 0.8)
    train_imgs, val_imgs = selected[:split], selected[split:]

    total_labels = 0
    for split_name, img_list in [('train', train_imgs), ('val', val_imgs)]:
        img_dir = os.path.join(DST_DIR, 'images', split_name)
        lbl_dir = os.path.join(DST_DIR, 'labels', split_name)
        os.makedirs(img_dir, exist_ok=True)
        os.makedirs(lbl_dir, exist_ok=True)

        for fname in img_list:
            src = os.path.join(SRC_DIR, fname)
            img_bgr = cv2.imread(src)
            if img_bgr is None:
                continue

            crop, x0, y0 = find_board_and_crop(img_bgr)
            if crop is None:
                continue

            labels = auto_label_cropped(crop)
            if not labels:
                continue

            # 크롭 이미지 저장
            basename = os.path.splitext(fname)[0]
            cv2.imwrite(os.path.join(img_dir, f"{basename}.jpg"), crop)

            # 라벨 저장
            with open(os.path.join(lbl_dir, f"{basename}.txt"), 'w') as f:
                for cls_id, cx, cy, w_n, h_n in labels:
                    f.write(f"{cls_id} {cx:.6f} {cy:.6f} {w_n:.6f} {h_n:.6f}\n")

            total_labels += len(labels)
            from collections import Counter
            cnt = Counter(CLASSES[l[0]] for l in labels)
            top3 = ', '.join(f"{k.replace('block_','')}:{v}" for k,v in cnt.most_common(3))
            print(f"  [{split_name}] {fname}: {len(labels)} ({top3})")

    print(f"\nTotal: {total_labels} labels")

    # dataset.yaml
    with open(os.path.join(DST_DIR, 'dataset.yaml'), 'w') as f:
        f.write(f"path: {DST_DIR}\ntrain: images/train\nval: images/val\n")
        f.write(f"nc: {len(CLASSES)}\nnames: {CLASSES}\n")
    print(f"Saved: dataset.yaml")


if __name__ == '__main__':
    main()
