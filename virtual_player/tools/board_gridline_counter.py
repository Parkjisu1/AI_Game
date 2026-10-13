"""
Board GridLine Counter — 셀 마스크의 격자선(갭)을 직접 감지하여 정확한 그리드 추출
1. 보라+노랑 결합 마스크 생성
2. 가로/세로 밀도 프로파일에서 격자선(골) 위치 찾기
3. 격자선 사이 = 셀 → 색상 판정
"""
import sys
import cv2
import numpy as np
from PIL import Image, ImageDraw


def make_color_masks(img_rgb):
    """보라/노랑/초록 셀 마스크 (확장 가능)"""
    r, g, b = img_rgb[:,:,0].astype(int), img_rgb[:,:,1].astype(int), img_rgb[:,:,2].astype(int)
    purple = (b > 180) & (r > 70) & (g < 80) & ((b - g) > 120)
    yellow = (r > 200) & (g > 100) & (b < 80) & ((r - b) > 150)
    green  = (g > 150) & (r < 150) & (b < 100) & ((g - r) > 30) & ((g - b) > 80)
    combined = purple | yellow | green
    return {'P': purple, 'Y': yellow, 'G': green}, combined


def detect_pitch(profile):
    """자기상관(autocorrelation)으로 셀 피치 감지"""
    centered = profile - profile.mean()
    corr = np.correlate(centered, centered, mode='full')
    corr = corr[len(centered):]
    for i in range(20, len(corr) - 1):
        if corr[i] > corr[i-1] and corr[i] > corr[i+1]:
            return i
    return 30


def find_grid_lines_by_pitch(gray_board, axis, pitch):
    """피치 기반 격자선 감지 — 좁은 골만 격자선으로 인정
    axis='col' → 세로 격자선 (가로 위치), axis='row' → 가로 격자선 (세로 위치)
    """
    if axis == 'col':
        profile = np.mean(gray_board, axis=0)
    else:
        profile = np.mean(gray_board, axis=1)

    n = len(profile)

    # Phase sweep: 가능한 시작점에서 pitch 간격으로 배치, 총 밝기가 가장 낮은 것
    best_phase = 0
    best_score = float('inf')
    for phase in range(min(pitch, n)):
        positions = list(range(phase, n, pitch))
        if len(positions) < 2:
            continue
        # 각 위치에서 +-2px 범위의 최소 밝기
        score = 0
        for p in positions:
            lo = max(0, p - 2)
            hi = min(n, p + 3)
            score += np.min(profile[lo:hi])
        score /= len(positions)
        if score < best_score:
            best_score = score
            best_phase = phase

    # 최적 phase에서 격자선 위치 생성, 각 위치를 로컬 최솟값으로 미세 조정
    gridlines = []
    pos = best_phase
    while pos < n:
        lo = max(0, pos - 3)
        hi = min(n, pos + 4)
        local_min = lo + np.argmin(profile[lo:hi])
        gridlines.append(int(local_min))
        pos += pitch

    return gridlines


def analyze(image_path):
    img = Image.open(image_path)
    w, h = img.size
    arr = np.array(img)
    print(f"Image: {w}x{h}")

    # 보드 영역: 상위 55%
    board_area = arr[:int(h * 0.55)]
    bh, bw = board_area.shape[:2]

    # 마스크
    color_masks, combined = make_color_masks(board_area)

    # 행/열 밀도 (결합 마스크)
    row_density = combined.sum(axis=1).astype(float)
    col_density = combined.sum(axis=0).astype(float)

    # 보드가 있는 구간 찾기 (밀도 > 최대의 40% — UI 아이콘 제외)
    row_threshold = row_density.max() * 0.4
    col_threshold = col_density.max() * 0.4
    active_rows = np.where(row_density > row_threshold)[0]
    active_cols = np.where(col_density > col_threshold)[0]

    if len(active_rows) == 0 or len(active_cols) == 0:
        print("ERROR: No board detected")
        return

    y_start, y_end = active_rows[0], active_rows[-1]
    x_start, x_end = active_cols[0], active_cols[-1]
    print(f"Board area: x=[{x_start},{x_end}], y=[{y_start},{y_end}] ({x_end-x_start}x{y_end-y_start}px)")

    # 보드 내부만 잘라서 격자선 찾기
    board_combined = combined[y_start:y_end+1, x_start:x_end+1]
    board_masks = {k: v[y_start:y_end+1, x_start:x_end+1] for k, v in color_masks.items()}
    board_rgb = board_area[y_start:y_end+1, x_start:x_end+1]

    # 밝기(luminance)
    gray = np.mean(board_rgb[:,:,:3].astype(float), axis=2)

    # 피치 감지 (자기상관) — 가로/세로 독립
    pitch_h = detect_pitch(np.mean(gray, axis=0))
    pitch_v = detect_pitch(np.mean(gray, axis=1))

    # 하모닉 보정: 한쪽이 다른 쪽의 ~2배이면 절반으로
    if pitch_v > pitch_h * 1.5:
        pitch_v = pitch_v // 2
    elif pitch_h > pitch_v * 1.5:
        pitch_h = pitch_h // 2

    print(f"Cell pitch: {pitch_h} x {pitch_v} px")

    # 각 축 독립적으로 격자선 찾기
    h_gridlines = find_grid_lines_by_pitch(gray, 'col', pitch_h)
    v_gridlines = find_grid_lines_by_pitch(gray, 'row', pitch_v)

    # 외곽 테두리 셀을 위한 가상 격자선 추가
    # 격자선 간격 중앙값으로 보드 시작/끝에 추가
    if len(h_gridlines) >= 2:
        median_hgap = int(np.median(np.diff(h_gridlines)))
        # 앞쪽: 첫 격자선보다 1간격 앞에 보드 시작이 있을 수 있음
        if h_gridlines[0] > median_hgap * 0.5:
            h_gridlines = [h_gridlines[0] - median_hgap] + h_gridlines
        # 뒤쪽
        board_w_local = board_combined.shape[1]
        if board_w_local - h_gridlines[-1] > median_hgap * 0.5:
            h_gridlines.append(h_gridlines[-1] + median_hgap)

    if len(v_gridlines) >= 2:
        median_vgap = int(np.median(np.diff(v_gridlines)))
        if v_gridlines[0] > median_vgap * 0.5:
            v_gridlines = [v_gridlines[0] - median_vgap] + v_gridlines
        board_h_local = board_combined.shape[0]
        if board_h_local - v_gridlines[-1] > median_vgap * 0.5:
            v_gridlines.append(v_gridlines[-1] + median_vgap)

    n_cols = len(h_gridlines) - 1
    n_rows = len(v_gridlines) - 1

    if n_cols < 1 or n_rows < 1:
        print("WARNING: Too few grid lines detected.")
        return

    # 실제 격자선 간격 통계
    h_gaps = np.diff(h_gridlines)
    v_gaps = np.diff(v_gridlines)
    print(f"\nVertical grid lines (columns): {len(h_gridlines)} lines -> {n_cols} columns")
    print(f"  Gaps: min={min(h_gaps)}, max={max(h_gaps)}, median={np.median(h_gaps):.0f}")
    print(f"Horizontal grid lines (rows): {len(v_gridlines)} lines -> {n_rows} rows")
    print(f"  Gaps: min={min(v_gaps)}, max={max(v_gaps)}, median={np.median(v_gaps):.0f}")

    # 각 셀 색상 판정: 모든 색상 마스크에서 가장 많은 픽셀 = 해당 색
    COLOR_NAMES = {'P': 'Purple', 'Y': 'Yellow', 'G': 'Green'}
    counts = {k: 0 for k in COLOR_NAMES}
    empty_count = 0
    grid_map = []

    for row in range(n_rows):
        row_data = []
        ry1 = v_gridlines[row] + 2
        ry2 = v_gridlines[row + 1] - 2
        for col in range(n_cols):
            rx1 = h_gridlines[col] + 2
            rx2 = h_gridlines[col + 1] - 2

            if ry2 <= ry1 or rx2 <= rx1:
                row_data.append('.')
                empty_count += 1
                continue

            # 각 색상별 픽셀 수
            votes = {}
            for label, mask in board_masks.items():
                votes[label] = mask[ry1:ry2, rx1:rx2].sum()

            best = max(votes, key=votes.get)
            if votes[best] > 0:
                row_data.append(best)
                counts[best] += 1
            else:
                row_data.append('.')
                empty_count += 1
        grid_map.append(row_data)

    # 결과
    print(f"\n{'='*60}")
    print(f"  GRIDLINE CELL COUNT")
    print(f"{'='*60}")
    print(f"  Grid:            {n_cols} x {n_rows}")
    for label, name in COLOR_NAMES.items():
        if counts[label] > 0:
            print(f"  {name:8s} ({label}):  {counts[label]}")
    print(f"  Empty (.):       {empty_count}")
    total = sum(counts.values()) + empty_count
    print(f"  Total:           {total}")
    print(f"{'='*60}")

    print(f"\nGrid map:")
    for i, rd in enumerate(grid_map):
        line = ''.join(rd)
        stats = '  '.join(f"{l}:{sum(1 for c in rd if c == l)}" for l in COLOR_NAMES if sum(1 for c in rd if c == l) > 0)
        dots = sum(1 for c in rd if c == '.')
        if dots > 0:
            stats += f"  .:{dots}"
        print(f"  Row {i+1:2d}: {line}  ({stats})")

    # 시각화: 원본 이미지에 격자선 오버레이
    vis = Image.fromarray(board_area).convert('RGB')
    draw = ImageDraw.Draw(vis)
    for gx in h_gridlines:
        draw.line([(x_start + gx, y_start), (x_start + gx, y_end)], fill=(255, 0, 0), width=1)
    for gy in v_gridlines:
        draw.line([(x_start, y_start + gy), (x_end, y_start + gy)], fill=(255, 0, 0), width=1)

    out = image_path.replace('.png', '_gridline_result.png')
    vis.save(out)
    print(f"\nSaved: {out}")

    return counts


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else \
        r"E:\AI\virtual_player\data\pixelflow\images\click_20260325_101730_0014_after.png"
    analyze(path)
