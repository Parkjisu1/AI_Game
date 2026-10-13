"""
Board Analyzer v2 — 하이브리드 파이프라인
1. 보드 크롭 (YOLO 또는 밝기 감지)
2. 격자선 감지 (밝기 프로파일 + 자기상관 피치)
3. RGB+HSV 복합 색상 분류
4. 결과 출력 + 시각화
"""
import sys, os
import cv2
import numpy as np


# ===== 색상 분류 (RGB 우선 + HSV 보조) =====
def classify_cell(rgb_region, hsv_region):
    """셀 영역의 RGB+HSV 통계로 색상 분류"""
    if rgb_region.size == 0:
        return None

    avg_r, avg_g, avg_b = np.mean(rgb_region, axis=(0,1))
    avg_h, avg_s, avg_v = np.mean(hsv_region, axis=(0,1))
    ri, gi, bi = int(avg_r), int(avg_g), int(avg_b)
    hi, si, vi = int(avg_h), int(avg_s), int(avg_v)

    # 배경 필터 (빈칸 = 보드 어두운 남색 배경 RGB~(50-65,50-65,85-110))
    brightness = (ri + gi + bi) / 3
    if brightness < 75:
        return None  # 어두움 = 빈칸
    if ri < 80 and gi < 80 and bi < 130:
        return None  # 보드 배경 (어두운 남색)
    if vi < 100 and si < 100:
        return None  # 어둡고 채도 낮음

    # RGB 확실한 분류
    if bi > 180 and ri > 70 and gi < 80 and (bi - gi) > 120:
        return 'P'
    if ri > 200 and gi > 130 and bi < 80:
        return 'Y'
    if ri > 200 and 80 < gi < 170 and bi < 60:
        return 'O'
    if gi > 150 and ri < 150 and bi < 100 and (gi - ri) > 30:
        return 'G'
    if ri > 180 and gi < 80 and bi < 80:
        return 'R'
    if ri > 200 and gi > 200 and bi > 200:
        return 'W'
    if vi < 120 and si > 30:
        return 'K'

    # HSV 보조 분류
    if si > 50 and vi > 100:
        if hi < 10 or hi > 170: return 'R'
        elif 10 <= hi < 22: return 'O'
        elif 22 <= hi < 38: return 'Y'
        elif 38 <= hi < 78: return 'G'
        elif 78 <= hi < 98: return 'C'
        elif 98 <= hi < 130: return 'B'
        elif 130 <= hi < 148: return 'P'
        elif 148 <= hi < 170: return 'F'

    return None


COLOR_NAMES = {
    'P': 'Purple', 'Y': 'Yellow', 'G': 'Green', 'B': 'Blue',
    'R': 'Red', 'F': 'Pink', 'W': 'White', 'K': 'Black',
    'O': 'Orange', 'C': 'Cyan',
}


# ===== 격자선 =====
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


# ===== 보드 크롭 =====
def crop_board(img_bgr, yolo_model=None):
    """YOLO 모델이 있으면 사용, 없으면 밝기 기반 감지"""
    h, w = img_bgr.shape[:2]

    if yolo_model:
        results = yolo_model.predict(img_bgr, conf=0.5, verbose=False)
        if len(results[0].boxes) > 0:
            box = results[0].boxes[0].xyxy[0].cpu().numpy().astype(int)
            return img_bgr[box[1]:box[3], box[0]:box[2]], box

    # fallback: 밝기 기반
    search = img_bgr[:int(h * 0.55)]
    gray_s = cv2.cvtColor(search, cv2.COLOR_BGR2GRAY)
    _, bright = cv2.threshold(gray_s, 60, 255, cv2.THRESH_BINARY)
    row_d = bright.sum(axis=1).astype(float)
    col_d = bright.sum(axis=0).astype(float)
    ar = np.where(row_d > row_d.max() * 0.4)[0]
    ac = np.where(col_d > col_d.max() * 0.4)[0]
    if len(ar) == 0 or len(ac) == 0:
        return None, None
    return img_bgr[ar[0]:ar[-1], ac[0]:ac[-1]], (ac[0], ar[0], ac[-1], ar[-1])


# ===== 메인 분석 =====
def analyze_board(board_bgr):
    bh, bw = board_bgr.shape[:2]

    # 프레임 제거: 채도+밝기 높은 영역 = 실제 셀 (프레임은 어두움)
    hsv_tmp = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2HSV)
    cell_mask = (hsv_tmp[:,:,1].astype(float) > 80) & (hsv_tmp[:,:,2].astype(float) > 100)
    row_d = cell_mask.sum(axis=1).astype(float)
    col_d = cell_mask.sum(axis=0).astype(float)
    ar = np.where(row_d > row_d.max() * 0.15)[0]
    ac = np.where(col_d > col_d.max() * 0.15)[0]
    if len(ar) > 0 and len(ac) > 0:
        pad = 3
        board_bgr = board_bgr[max(0,ar[0]-pad):min(bh,ar[-1]+pad),
                               max(0,ac[0]-pad):min(bw,ac[-1]+pad)]
        bh, bw = board_bgr.shape[:2]

    board_rgb = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2RGB)
    board_hsv = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2HSV)
    gray = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2GRAY).astype(float)

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
        return None

    grid = []
    counts = {}
    for row in range(n_rows):
        row_data = []
        ry1 = max(0, v_gl[row] + 3)
        ry2 = min(bh, v_gl[row+1] - 3)
        for col in range(n_cols):
            rx1 = max(0, h_gl[col] + 3)
            rx2 = min(bw, h_gl[col+1] - 3)
            if ry2 <= ry1 or rx2 <= rx1:
                row_data.append('.')
                continue
            label = classify_cell(board_rgb[ry1:ry2, rx1:rx2], board_hsv[ry1:ry2, rx1:rx2])
            if label:
                row_data.append(label)
                counts[label] = counts.get(label, 0) + 1
            else:
                row_data.append('.')
        grid.append(row_data)

    # 프레임 행/열 제거: 전체가 K(black), B(blue), 또는 .(empty)인 행/열 트림
    frame_chars = {'K', 'B', '.'}

    # 상단 트림
    top_trim = 0
    for row in grid:
        if all(c in frame_chars for c in row):
            top_trim += 1
        else:
            break
    # 하단 트림
    bot_trim = 0
    for row in reversed(grid):
        if all(c in frame_chars for c in row):
            bot_trim += 1
        else:
            break
    # 좌측 트림
    left_trim = 0
    for col in range(n_cols):
        if all(grid[r][col] in frame_chars for r in range(len(grid))):
            left_trim += 1
        else:
            break
    # 우측 트림
    right_trim = 0
    for col in range(n_cols - 1, -1, -1):
        if all(grid[r][col] in frame_chars for r in range(len(grid))):
            right_trim += 1
        else:
            break

    if top_trim or bot_trim or left_trim or right_trim:
        end_row = n_rows - bot_trim if bot_trim else n_rows
        end_col = n_cols - right_trim if right_trim else n_cols
        grid = [row[left_trim:end_col] for row in grid[top_trim:end_row]]
        n_rows = len(grid)
        n_cols = len(grid[0]) if grid else 0
        # 카운트 재계산
        counts = {}
        for row in grid:
            for c in row:
                if c != '.':
                    counts[c] = counts.get(c, 0) + 1

    return {
        'grid': grid, 'counts': counts,
        'cols': n_cols, 'rows': n_rows,
        'pitch_h': pitch_h, 'pitch_v': pitch_v,
        'h_gridlines': h_gl, 'v_gridlines': v_gl,
    }


def print_result(result):
    if not result:
        print("ERROR: No grid detected")
        return
    grid, counts = result['grid'], result['counts']
    n_cols, n_rows = result['cols'], result['rows']
    colored = sum(counts.values())
    empty = n_cols * n_rows - colored

    print(f"\n{'='*60}")
    print(f"  BOARD ANALYSIS")
    print(f"{'='*60}")
    print(f"  Grid:  {n_cols} x {n_rows} = {n_cols*n_rows}")
    print(f"  Pitch: {result['pitch_h']} x {result['pitch_v']}px")
    for label, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {COLOR_NAMES.get(label,label):8s} ({label}):  {count}")
    if empty > 0:
        print(f"  {'Empty':8s} (.):  {empty}")
    print(f"{'='*60}")

    print(f"\nGrid map:")
    for i, row in enumerate(grid):
        line = ''.join(row)
        stats = '  '.join(f"{l}:{sum(1 for c in row if c==l)}"
                          for l in sorted(set(row)) if l != '.')
        dots = sum(1 for c in row if c == '.')
        if dots:
            stats += f"  .:{dots}"
        print(f"  Row {i+1:2d}: {line}  ({stats})")


def detect_gimmicks(img_bgr, model_path=None):
    """YOLO 기믹 검출"""
    if not model_path or not os.path.exists(model_path):
        return []
    from ultralytics import YOLO
    model = YOLO(model_path)
    results = model.predict(img_bgr, conf=0.3, verbose=False)
    gimmicks = []
    for box in results[0].boxes:
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
        conf = box.conf[0].item()
        gimmicks.append({'bbox': (x1, y1, x2, y2), 'conf': conf})
    return gimmicks


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else \
        r"E:\AI\virtual_player\data\pixelflow\images\click_20260325_101730_0014_after.png"

    img = cv2.imread(path)
    print(f"Image: {img.shape[1]}x{img.shape[0]}")

    # YOLO 모델 로드
    BOARD_MODEL = r"E:\AI\virtual_player\yolo\pixelflow\runs\board_detector\weights\best.pt"
    GIMMICK_MODEL = r"E:\AI\virtual_player\yolo\pixelflow\runs\gimmick_detector\weights\best.pt"

    from ultralytics import YOLO
    yolo_board = YOLO(BOARD_MODEL) if os.path.exists(BOARD_MODEL) else None

    # 1. 보드 크롭 + 셀 분석
    board, bbox = crop_board(img, yolo_board)
    if board is None:
        print("ERROR: No board found")
        sys.exit(1)
    print(f"Board crop: {board.shape[1]}x{board.shape[0]}px")

    result = analyze_board(board)
    print_result(result)

    # 2. 기믹 검출
    gimmicks = detect_gimmicks(img, GIMMICK_MODEL)
    if gimmicks:
        print(f"\nGimmicks detected: {len(gimmicks)}")
        for i, g in enumerate(gimmicks):
            x1, y1, x2, y2 = g['bbox']
            print(f"  #{i+1}: ({x1},{y1})->({x2},{y2}) conf={g['conf']:.2f}")

    # 3. 시각화
    out = path.replace('.png', '_analyzed.png')
    vis = img.copy()
    # 보드 영역 표시
    if bbox is not None:
        cv2.rectangle(vis, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0, 255, 0), 2)
    # 기믹 표시
    for g in gimmicks:
        x1, y1, x2, y2 = g['bbox']
        cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 0, 255), 2)
        cv2.putText(vis, f"gimmick {g['conf']:.2f}", (x1, y1-5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    cv2.imwrite(out, vis)
    print(f"\nSaved: {out}")
