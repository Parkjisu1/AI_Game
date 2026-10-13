"""
Board Pixel Counter — 색상별 총 픽셀 / 셀 1개 픽셀 = 셀 개수
그리드 정렬 불필요. 가장 단순하고 안정적.
"""
import sys
import numpy as np
from PIL import Image


COLOR_DEFS = {
    'P': ('Purple', lambda r,g,b: (b > 180) & (r > 70) & (g < 80) & ((b-g) > 120)),
    'Y': ('Yellow', lambda r,g,b: (r > 200) & (g > 100) & (b < 80) & ((r-b) > 150)),
    'G': ('Green',  lambda r,g,b: (g > 150) & (r < 150) & (b < 100) & ((g-r) > 30) & ((g-b) > 80)),
}


def detect_pitch(profile):
    """자기상관으로 셀 피치 감지"""
    centered = profile - profile.mean()
    corr = np.correlate(centered, centered, mode='full')
    corr = corr[len(centered):]
    for i in range(20, len(corr) - 1):
        if corr[i] > corr[i-1] and corr[i] > corr[i+1]:
            return i
    return 30


def analyze(image_path):
    img = Image.open(image_path)
    w, h = img.size
    arr = np.array(img)
    print(f"Image: {w}x{h}")

    # 보드 영역: 상위 55%
    board = arr[:int(h * 0.55)]
    r, g, b = board[:,:,0].astype(int), board[:,:,1].astype(int), board[:,:,2].astype(int)

    # 각 색상 마스크 + 결합
    masks = {}
    combined = np.zeros(r.shape, dtype=bool)
    for label, (name, fn) in COLOR_DEFS.items():
        m = fn(r, g, b)
        masks[label] = m
        combined |= m

    # 보드 바운딩 박스 (밀도 40% 이상)
    row_d = combined.sum(axis=1).astype(float)
    col_d = combined.sum(axis=0).astype(float)
    active_r = np.where(row_d > row_d.max() * 0.4)[0]
    active_c = np.where(col_d > col_d.max() * 0.4)[0]

    if len(active_r) == 0 or len(active_c) == 0:
        print("ERROR: No board detected")
        return

    y0, y1 = active_r[0], active_r[-1]
    x0, x1 = active_c[0], active_c[-1]

    # 보드 내부로 크롭
    board_crop = board[y0:y1+1, x0:x1+1]
    bh, bw = board_crop.shape[:2]
    gray = np.mean(board_crop[:,:,:3].astype(float), axis=2)

    # 피치 감지 (가로 기준 — 빈칸 영향 적음)
    pitch = detect_pitch(np.mean(gray, axis=0))
    print(f"Board: {bw}x{bh}px, pitch={pitch}px")

    # 셀 1개의 색상 픽셀 수 측정:
    # 보드 내에서 색상 마스크가 ON인 영역의 평균 "덩어리 크기" 사용
    # 또는 간단히: pitch^2 * fill_ratio (fill_ratio ~= 0.75-0.85)
    # 더 정확한 방법: 작은 connected component의 중앙값 면적
    import cv2
    sample_mask = (combined[y0:y1+1, x0:x1+1] * 255).astype(np.uint8)
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(sample_mask, connectivity=4)

    # 컴포넌트 면적들 (배경=0 제외)
    areas = stats[1:, cv2.CC_STAT_AREA]
    if len(areas) == 0:
        print("ERROR: No colored components found")
        return

    # 셀 1개 면적: 가장 작은 유효 컴포넌트들의 중앙값 (단일 셀)
    # pitch^2 의 0.3~1.5배 범위 내 컴포넌트 = 단일 셀
    pitch_sq = pitch * pitch
    single_cell_areas = areas[(areas > pitch_sq * 0.3) & (areas < pitch_sq * 1.5)]

    if len(single_cell_areas) > 0:
        cell_px = np.median(single_cell_areas)
    else:
        # fallback: pitch^2 * 0.8
        cell_px = pitch_sq * 0.8

    print(f"Cell pixel area: {cell_px:.0f}px (pitch^2={pitch_sq})")

    # 색상별 셀 카운트 = 보드 내 해당 색 총 픽셀 / 셀 1개 픽셀
    print(f"\n{'='*50}")
    print(f"  PIXEL-BASED CELL COUNT")
    print(f"{'='*50}")
    total = 0
    for label, (name, fn) in COLOR_DEFS.items():
        m = fn(
            board_crop[:,:,0].astype(int),
            board_crop[:,:,1].astype(int),
            board_crop[:,:,2].astype(int)
        )
        px_count = m.sum()
        cell_count = round(px_count / cell_px)
        if cell_count > 0:
            print(f"  {name:8s} ({label}):  {cell_count:4d}  ({px_count:,}px / {cell_px:.0f}px)")
            total += cell_count

    # 빈칸 추정: 그리드 총 셀 - 색칠된 셀
    est_cols = round(bw / pitch)
    est_rows = round(bh / pitch)
    est_total = est_cols * est_rows
    empty = max(0, est_total - total)
    print(f"  {'Empty':8s} (.):  {empty:4d}")
    print(f"  {'':8s}        ----")
    print(f"  {'Grid':8s}     :  ~{est_cols}x{est_rows} = {est_total}")
    print(f"  {'Colored':8s}  :  {total}")
    print(f"{'='*50}")

    return total


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else \
        r"E:\AI\virtual_player\data\pixelflow\images\click_20260325_101759_0044_after.png"
    analyze(path)
