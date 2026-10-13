"""
Auto Labeler — 격자선 감지 + 색상 분류 → YOLO 포맷 라벨 자동 생성
격자 내 색상 블록만 라벨링 (기믹은 수동 추가 필요)
출력: YOLO 포맷 (class_id cx cy w h) — 정규화 좌표
"""
import sys, os, shutil
import cv2
import numpy as np
from PIL import Image

# 클래스 정의 (색상 블록 + 빈칸)
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

# RGB 기반 색상 판정 함수들
def classify_color(r, g, b):
    """RGB 평균값으로 색상 분류 → class_id 반환, None이면 미분류"""
    if np.isnan(r) or np.isnan(g) or np.isnan(b):
        return None
    ri, gi, bi = int(r), int(g), int(b)

    # 검정/어두운 (빈칸 또는 검은 블록)
    if ri < 60 and gi < 60 and bi < 60:
        return None  # 너무 어두우면 보드 배경 — skip

    # 검은 블록 (약간 밝은 검정)
    if ri < 80 and gi < 80 and bi < 80:
        return 7  # block_black

    # 흰색
    if ri > 200 and gi > 200 and bi > 200:
        return 6  # block_white

    # 보라 (B 높고 G 낮음)
    if bi > 180 and ri > 70 and gi < 80 and (bi - gi) > 120:
        return 0  # block_purple

    # 노랑/주황 계열
    if ri > 200 and gi > 100 and bi < 80:
        if gi > 160:
            return 1  # block_yellow
        else:
            return 8  # block_orange

    # 초록
    if gi > 150 and ri < 150 and bi < 100 and (gi - ri) > 30:
        return 2  # block_green

    # 파랑 (B 높고 R 낮음, G 낮~중)
    if bi > 150 and ri < 100 and gi < 150 and (bi - ri) > 80:
        return 3  # block_blue

    # 시안 (G+B 높고 R 낮음)
    if gi > 150 and bi > 150 and ri < 100:
        return 9  # block_cyan

    # 빨강
    if ri > 180 and gi < 80 and bi < 80:
        return 4  # block_red

    # 분홍
    if ri > 180 and gi < 130 and bi > 100 and ri > bi:
        return 5  # block_pink

    # 갈색
    if ri > 120 and gi > 60 and gi < 120 and bi < 60:
        return 10  # block_brown

    return None  # 미분류


def detect_pitch(profile):
    centered = profile - profile.mean()
    corr = np.correlate(centered, centered, mode='full')
    corr = corr[len(centered):]
    for i in range(20, len(corr) - 1):
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
        score = 0
        for p in positions:
            lo = max(0, p - 2)
            hi = min(n, p + 3)
            score += np.min(profile[lo:hi])
        score /= len(positions)
        if score < best_score:
            best_score = score
            best_phase = phase

    gridlines = []
    pos = best_phase
    while pos < n:
        lo = max(0, pos - 3)
        hi = min(n, pos + 4)
        local_min = lo + np.argmin(profile[lo:hi])
        gridlines.append(int(local_min))
        pos += pitch

    return gridlines


def add_edge_gridlines(gridlines, board_size):
    if len(gridlines) < 2:
        return gridlines
    median_gap = int(np.median(np.diff(gridlines)))
    if gridlines[0] > median_gap * 0.5:
        gridlines = [gridlines[0] - median_gap] + gridlines
    if board_size - gridlines[-1] > median_gap * 0.5:
        gridlines.append(gridlines[-1] + median_gap)
    return gridlines


def auto_label(image_path, output_dir=None):
    """이미지에서 셀 위치+색상 감지 → YOLO 라벨 생성"""
    img = Image.open(image_path)
    W, H = img.size
    arr = np.array(img)

    # 보드 영역
    board_area = arr[:int(H * 0.55)]
    r, g, b = board_area[:,:,0].astype(int), board_area[:,:,1].astype(int), board_area[:,:,2].astype(int)

    # 결합 마스크 (모든 밝은 색)
    bright = (r + g + b) > 200  # 어두운 배경 제외
    colored = bright & ~((r > 200) & (g > 200) & (b > 200) & ((abs(r-g) + abs(g-b)) < 30))  # 순수 회색 제외
    # 더 넓은 마스크: 어떤 채널이든 밝은 것
    any_bright = (r > 120) | (g > 120) | (b > 120)
    combined = any_bright & (board_area[:,:,0] + board_area[:,:,1] + board_area[:,:,2] > 150)

    row_d = combined.sum(axis=1).astype(float)
    col_d = combined.sum(axis=0).astype(float)
    active_r = np.where(row_d > row_d.max() * 0.4)[0]
    active_c = np.where(col_d > col_d.max() * 0.4)[0]

    if len(active_r) == 0 or len(active_c) == 0:
        return []

    y0, y1 = active_r[0], active_r[-1]
    x0, x1 = active_c[0], active_c[-1]

    board_rgb = board_area[y0:y1+1, x0:x1+1]
    bh, bw = board_rgb.shape[:2]
    gray = np.mean(board_rgb[:,:,:3].astype(float), axis=2)

    # 피치
    pitch_h = detect_pitch(np.mean(gray, axis=0))
    pitch_v = detect_pitch(np.mean(gray, axis=1))
    if pitch_v > pitch_h * 1.5:
        pitch_v = pitch_v // 2
    elif pitch_h > pitch_v * 1.5:
        pitch_h = pitch_h // 2

    # 격자선
    h_gl = find_grid_lines(gray, 'col', pitch_h)
    v_gl = find_grid_lines(gray, 'row', pitch_v)
    h_gl = add_edge_gridlines(h_gl, bw)
    v_gl = add_edge_gridlines(v_gl, bh)

    n_cols = len(h_gl) - 1
    n_rows = len(v_gl) - 1

    if n_cols < 1 or n_rows < 1:
        return []

    # 각 셀 라벨링
    labels = []
    for row in range(n_rows):
        ry1 = v_gl[row] + 2
        ry2 = v_gl[row + 1] - 2
        for col in range(n_cols):
            rx1 = h_gl[col] + 2
            rx2 = h_gl[col + 1] - 2

            if ry2 <= ry1 or rx2 <= rx1:
                continue

            # 셀 중심 RGB
            cell = board_rgb[ry1:ry2, rx1:rx2, :3]
            avg_r, avg_g, avg_b = np.mean(cell, axis=(0,1))

            cls_id = classify_color(avg_r, avg_g, avg_b)
            if cls_id is None:
                continue

            # YOLO 포맷: 정규화 좌표 (이미지 전체 기준)
            # 셀의 이미지 좌표
            img_x1 = x0 + h_gl[col]
            img_y1 = y0 + v_gl[row]
            img_x2 = x0 + h_gl[col + 1]
            img_y2 = y0 + v_gl[row + 1]

            cx = (img_x1 + img_x2) / 2 / W
            cy = (img_y1 + img_y2) / 2 / H
            bw_norm = (img_x2 - img_x1) / W
            bh_norm = (img_y2 - img_y1) / H

            labels.append((cls_id, cx, cy, bw_norm, bh_norm))

    # 라벨 파일 저장
    if output_dir:
        basename = os.path.splitext(os.path.basename(image_path))[0]
        label_path = os.path.join(output_dir, f"{basename}.txt")
        with open(label_path, 'w') as f:
            for cls_id, cx, cy, bw_n, bh_n in labels:
                f.write(f"{cls_id} {cx:.6f} {cy:.6f} {bw_n:.6f} {bh_n:.6f}\n")

    return labels


def main():
    if len(sys.argv) < 2:
        print("Usage: python auto_label.py <image_or_dir> [--output-dir=<dir>]")
        return

    target = sys.argv[1]
    output_dir = None
    for a in sys.argv:
        if a.startswith('--output-dir='):
            output_dir = a.split('=', 1)[1]

    if os.path.isfile(target):
        labels = auto_label(target, output_dir)
        print(f"{os.path.basename(target)}: {len(labels)} labels")
        # 클래스별 카운트
        from collections import Counter
        cnt = Counter(CLASSES[l[0]] for l in labels)
        for name, c in cnt.most_common():
            print(f"  {name}: {c}")
    elif os.path.isdir(target):
        files = sorted([f for f in os.listdir(target) if f.endswith('.png')])
        for f in files:
            labels = auto_label(os.path.join(target, f), output_dir)
            if labels:
                cnt = Counter(CLASSES[l[0]] for l in labels)
                summary = ', '.join(f"{CLASSES[l[0]][6:]}:{c}" for l, c in Counter(l[0] for l in labels).most_common())
                print(f"{f}: {len(labels)} ({summary})")


if __name__ == '__main__':
    from collections import Counter
    main()
