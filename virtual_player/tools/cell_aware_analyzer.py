"""
Cell-Aware Board Analyzer v2
==============================
Multi-sample voting + render palette + CC smoothing.
GT FieldMap은 y-flip되어 저장됨 → 분석 시 보정 필요.

정확도: 250개 verified image 기준 평균 75.4% (v1 대비 ~2배)

사용법:
  python cell_aware_analyzer.py <이미지> --profile <cell_profile.json>
  python cell_aware_analyzer.py <이미지폴더> --batch --profile <cell_profile.json>
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw


# ══════════════════════════════════════════════════════════════
#  29-Color Palette
# ══════════════════════════════════════════════════════════════
PALETTE_29 = {
    1: (252, 106, 175), 2: (80, 232, 246), 3: (137, 80, 248),
    4: (254, 213, 85), 5: (115, 254, 102), 6: (253, 161, 76),
    7: (255, 255, 255), 8: (65, 65, 65), 9: (110, 168, 250),
    10: (57, 174, 46), 11: (252, 94, 94), 12: (50, 107, 248),
    13: (58, 165, 139), 14: (231, 167, 250), 15: (183, 199, 251),
    16: (106, 74, 48), 17: (254, 227, 169), 18: (253, 183, 193),
    19: (158, 61, 94), 20: (167, 221, 148), 21: (89, 46, 126),
    22: (220, 120, 129), 23: (217, 217, 231), 24: (111, 114, 127),
    25: (252, 56, 165), 26: (253, 180, 88), 27: (137, 10, 8),
    28: (111, 175, 177), 29: (100, 80, 60),
}
_PAL_KEYS = sorted(PALETTE_29.keys())
_PAL_ARRAY = np.array([PALETTE_29[k] for k in _PAL_KEYS], dtype=np.float64)

COLOR_NAMES = {
    1: 'Pink', 2: 'Cyan', 3: 'Purple', 4: 'Yellow', 5: 'Green', 6: 'Orange',
    7: 'White', 8: 'Dark', 9: 'LightBlue', 10: 'DarkGreen', 11: 'Red', 12: 'Blue',
    13: 'Teal', 14: 'Lavender', 15: 'Periwinkle', 16: 'Brown', 17: 'Peach',
    18: 'LightPink', 19: 'Maroon', 20: 'MintGreen', 21: 'DarkPurple',
    22: 'DustyRose', 23: 'Silver', 24: 'Gray', 25: 'HotPink', 26: 'Amber',
    27: 'DarkRed', 28: 'SageTeal', 29: 'BrownDark',
}


def load_profile(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ══════════════════════════════════════════════════════════════
#  Render Palette (게임 실제 렌더 색상)
# ══════════════════════════════════════════════════════════════

def build_render_palette(profile):
    """프로파일의 render_ranges에서 렌더 팔레트 구축."""
    if "render_ranges" not in profile:
        return _PAL_KEYS, _PAL_ARRAY

    render_pal = {}
    for cid_str, info in profile["render_ranges"].items():
        mean = info.get("render_mean", info.get("ref_rgb"))
        if mean:
            render_pal[int(cid_str)] = np.array(mean, dtype=np.float64)

    if not render_pal:
        return _PAL_KEYS, _PAL_ARRAY

    keys = sorted(render_pal.keys())
    arr = np.array([render_pal[k] for k in keys], dtype=np.float64)
    return keys, arr


# ══════════════════════════════════════════════════════════════
#  Smart Pixel Classification (어두운 색상 특별 처리)
# ══════════════════════════════════════════════════════════════

def classify_pixel(pixel, pal_keys, pal_arr):
    """단일 픽셀 분류. 어두운 픽셀에 특별 처리."""
    r, g, b = float(pixel[0]), float(pixel[1]), float(pixel[2])
    brightness = max(r, g, b)

    # 매우 어두운 픽셀: 채널 비율로 분류
    if brightness < 60:
        if brightness < 15:
            return 8  # 거의 검정 → c8 (Dark)
        blue_ratio = b / (brightness + 1)
        green_ratio = g / (brightness + 1)
        if blue_ratio > 0.6 and b > r * 1.5:
            return 21  # 푸른 기운 → c21 (DarkPurple)
        if green_ratio > 0.6 and g > r * 1.5:
            return 10  # 녹색 기운 → c10 (DarkGreen)
        return 8  # 중립 어두움 → c8

    # 일반: 유클리드 거리
    px = np.array([r, g, b], dtype=np.float64)
    dists = np.sqrt(np.sum((pal_arr - px) ** 2, axis=1))
    return pal_keys[int(np.argmin(dists))]


# ══════════════════════════════════════════════════════════════
#  1. Board Detection
# ══════════════════════════════════════════════════════════════

def find_board_region(img_cv, profile):
    """스크린샷에서 보드 영역 크롭."""
    h, w = img_cv.shape[:2]
    hsv = cv2.cvtColor(img_cv, cv2.COLOR_BGR2HSV)

    sat_mask = hsv[:, :, 1] > 30
    val_mask = hsv[:, :, 2] > 40
    tile_mask = (sat_mask & val_mask).astype(np.uint8) * 255

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    tile_mask = cv2.morphologyEx(tile_mask, cv2.MORPH_CLOSE, kernel)

    coords = cv2.findNonZero(tile_mask)
    if coords is None:
        return img_cv, (0, 0, w, h)

    x, y, bw, bh = cv2.boundingRect(coords)
    pad = 2
    x = max(0, x - pad)
    y = max(0, y - pad)
    bw = min(w - x, bw + pad * 2)
    bh = min(h - y, bh + pad * 2)

    return img_cv[y:y + bh, x:x + bw], (x, y, bw, bh)


# ══════════════════════════════════════════════════════════════
#  2. Multi-Sample Cell Classification
# ══════════════════════════════════════════════════════════════

def extract_cell_colors(board_rgb, profile, pal_keys, pal_arr):
    """다중 샘플 투표 기반 셀 색상 추출.

    각 셀에서 9개 포인트를 샘플링하고, 가중 투표로 색상 결정.
    중앙 픽셀은 3배 가중치, 중앙 영역 median은 2배 가중치.
    """
    h, w = board_rgb.shape[:2]
    grid_rows = profile["grid"]["rows"]
    grid_cols = profile["grid"]["cols"]
    ch = h / grid_rows
    cw = w / grid_cols

    grid = [[0] * grid_cols for _ in range(grid_rows)]

    for r in range(grid_rows):
        for c in range(grid_cols):
            y0 = int(r * ch)
            y1 = int((r + 1) * ch)
            x0 = int(c * cw)
            x1 = int((c + 1) * cw)
            cell = board_rgb[y0:y1, x0:x1]
            cell_h, cell_w = cell.shape[:2]

            if cell_h == 0 or cell_w == 0:
                grid[r][c] = 21  # default background
                continue

            votes = Counter()

            # 9-point grid (30%, 50%, 70% of cell)
            for fy in [0.3, 0.5, 0.7]:
                for fx in [0.3, 0.5, 0.7]:
                    sy = min(cell_h - 1, max(0, int(fy * cell_h)))
                    sx = min(cell_w - 1, max(0, int(fx * cell_w)))
                    pixel = cell[sy, sx].astype(np.float64)
                    cid = classify_pixel(pixel, pal_keys, pal_arr)
                    weight = 3 if (fy == 0.5 and fx == 0.5) else 1
                    votes[cid] += weight

            # 중앙 영역 median (25%-75%)
            center_area = cell[cell_h // 4:3 * cell_h // 4,
                               cell_w // 4:3 * cell_w // 4]
            if center_area.size > 0:
                med = np.median(
                    center_area.reshape(-1, 3), axis=0
                ).astype(np.float64)
                votes[classify_pixel(med, pal_keys, pal_arr)] += 2

            grid[r][c] = votes.most_common(1)[0][0]

    return grid


# ══════════════════════════════════════════════════════════════
#  3. Connected Component Smoothing
# ══════════════════════════════════════════════════════════════

def cc_smooth(grid, min_size=3):
    """작은 연결 성분을 주변 색상으로 교체."""
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    visited = [[False] * cols for _ in range(rows)]
    components = []

    for r in range(rows):
        for c in range(cols):
            if visited[r][c]:
                continue
            color = grid[r][c]
            cells = []
            queue = [(r, c)]
            visited[r][c] = True
            while queue:
                cr, cc_ = queue.pop(0)
                cells.append((cr, cc_))
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = cr + dr, cc_ + dc
                    if (0 <= nr < rows and 0 <= nc < cols
                            and not visited[nr][nc]
                            and grid[nr][nc] == color):
                        visited[nr][nc] = True
                        queue.append((nr, nc))
            components.append((color, cells))

    new_grid = [row[:] for row in grid]
    for color, cells in components:
        if len(cells) <= min_size:
            neighbors = Counter()
            for cr, cc_ in cells:
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = cr + dr, cc_ + dc
                    if (0 <= nr < rows and 0 <= nc < cols
                            and grid[nr][nc] != color):
                        neighbors[grid[nr][nc]] += 1
            if neighbors:
                replacement = neighbors.most_common(1)[0][0]
                for cr, cc_ in cells:
                    new_grid[cr][cc_] = replacement
    return new_grid


# ══════════════════════════════════════════════════════════════
#  4. Frame/Floor Classification
# ══════════════════════════════════════════════════════════════

def classify_elements(grid, profile):
    """배경/프레임 자동 분류."""
    rows = len(grid)
    cols = len(grid[0]) if grid else 0

    edge_colors = Counter()
    for r in range(rows):
        for c in range(cols):
            if c < 3 or c >= cols - 3 or r < 3 or r >= rows - 3:
                edge_colors[grid[r][c]] += 1

    profile_frame_colors = set(profile.get("colors", {}).get("frame_colors", []))
    bg_color = edge_colors.most_common(1)[0][0]
    bg_colors = {bg_color}
    for fc in profile_frame_colors:
        if edge_colors.get(fc, 0) > 0:
            bg_colors.add(fc)

    frame_mask = [[False] * cols for _ in range(rows)]
    content_grid = [row[:] for row in grid]
    frame_count = 0
    content_count = 0

    for r in range(rows):
        for c in range(cols):
            if grid[r][c] in bg_colors:
                frame_mask[r][c] = True
                content_grid[r][c] = 0
                frame_count += 1
            else:
                content_count += 1

    return content_grid, frame_mask, {
        "frame": frame_count,
        "floor": 0,
        "content": content_count,
        "bg_color": bg_color,
        "bg_colors": list(bg_colors),
    }


# ══════════════════════════════════════════════════════════════
#  5. FieldMap / JSON Generation
# ══════════════════════════════════════════════════════════════

def grid_to_fieldmap(grid, flip_y=True):
    """grid → FieldMap 문자열. flip_y=True: 게임 좌표계로 상하반전."""
    rows = grid[::-1] if flip_y else grid
    return "\n".join(" ".join(f"{v:02d}" for v in row) for row in rows)


def grid_to_level_json(grid, content_grid, level_num=1, stats=None):
    """grid → 완전한 레벨 JSON."""
    content_counts = Counter(v for row in content_grid for v in row if v > 0)

    fm = grid_to_fieldmap(grid, flip_y=True)

    return {
        "level_number": level_num,
        "level_id": f"L{level_num:04d}",
        "pkg": (level_num - 1) // 50 + 1,
        "pos": (level_num - 1) % 50 + 1,
        "chapter": (level_num - 1) // 250 + 1,
        "purpose_type": "Normal",
        "target_cr": 0,
        "target_attempts": 0.0,
        "num_colors": len(content_counts),
        "color_distribution": " ".join(
            f"c{cid}:{cnt}" for cid, cnt in
            sorted(content_counts.items(), key=lambda x: -x[1])
        ),
        "field_rows": len(grid),
        "field_columns": len(grid[0]) if grid else 0,
        "total_cells": sum(content_counts.values()),
        "rail_capacity": 5,
        "rail_capacity_tier": "S",
        "queue_columns": min(len(content_counts), 5),
        "queue_rows": 3,
        "gimmick_hidden": 0, "gimmick_chain": 0, "gimmick_pinata": 0,
        "gimmick_spawner_t": 0, "gimmick_pin": 0, "gimmick_lock_key": 0,
        "gimmick_surprise": 0, "gimmick_wall": 0, "gimmick_spawner_o": 0,
        "gimmick_pinata_box": 0, "gimmick_ice": 0, "gimmick_frozen_dart": 0,
        "gimmick_curtain": 0,
        "total_darts": sum(content_counts.values()),
        "emotion_curve": "",
        "designer_note": f"[FieldMap]\n{fm}",
        **(stats or {}),
    }


# ══════════════════════════════════════════════════════════════
#  6. Visualization
# ══════════════════════════════════════════════════════════════

def render_grid(grid, cell_size=12, frame_mask=None, render_colors=None):
    """grid → PIL Image."""
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    img = Image.new("RGB", (cols * cell_size, rows * cell_size), (20, 20, 30))
    draw = ImageDraw.Draw(img)

    for r in range(rows):
        for c in range(cols):
            cid = grid[r][c]
            if render_colors and cid in render_colors:
                color = tuple(int(v) for v in render_colors[cid])
            else:
                color = PALETTE_29.get(cid, (30, 30, 40))

            if frame_mask and frame_mask[r][c]:
                color = tuple(max(0, v // 3) for v in color)

            x0 = c * cell_size
            y0 = r * cell_size
            draw.rectangle(
                [x0, y0, x0 + cell_size - 1, y0 + cell_size - 1],
                fill=color
            )

    return img


# ══════════════════════════════════════════════════════════════
#  7. Full Pipeline
# ══════════════════════════════════════════════════════════════

def analyze(img_path, profile, output_dir=None, level_num=1):
    """단일 이미지 cell-aware 분석.

    Returns:
        dict: {grid, content_grid, fieldmap, level_json, stats, ...}
    """
    img_cv = cv2.imread(str(img_path))
    if img_cv is None:
        return {"error": f"Cannot read: {img_path}"}

    # 1. 보드 크롭 (이미 크롭된 이미지라면 그대로)
    board_cv, crop_rect = find_board_region(img_cv, profile)
    board_rgb = cv2.cvtColor(board_cv, cv2.COLOR_BGR2RGB)

    # 2. 렌더 팔레트 구축
    pal_keys, pal_arr = build_render_palette(profile)

    # 3. 다중 샘플 투표 기반 셀 색상 추출
    grid = extract_cell_colors(board_rgb, profile, pal_keys, pal_arr)

    # 4. CC 스무딩 (노이즈 제거)
    grid = cc_smooth(grid, min_size=3)
    grid = cc_smooth(grid, min_size=2)

    # 5. 프레임/배경 분류
    content_grid, frame_mask, element_stats = classify_elements(grid, profile)

    # 6. 잡색 필터링 (전체 콘텐츠의 2% 미만)
    content_colors = Counter(v for row in content_grid for v in row if v > 0)
    total_content = sum(content_colors.values())
    if total_content > 0:
        min_count = max(1, int(total_content * 0.02))
        major_colors = {cid for cid, cnt in content_colors.items()
                        if cnt >= min_count}
        minor_colors = {cid for cid, cnt in content_colors.items()
                        if cnt < min_count}

        if minor_colors and major_colors:
            pal_arr_m = np.array([
                PALETTE_29.get(c, (128, 128, 128)) for c in major_colors
            ], dtype=np.float64)
            major_list = list(major_colors)

            remap = {}
            for mc in minor_colors:
                mc_rgb = np.array(
                    PALETTE_29.get(mc, (128, 128, 128)), dtype=np.float64
                )
                dists = np.sqrt(np.sum((pal_arr_m - mc_rgb) ** 2, axis=1))
                remap[mc] = major_list[int(np.argmin(dists))]

            for r in range(len(content_grid)):
                for c in range(len(content_grid[0])):
                    if content_grid[r][c] in remap:
                        content_grid[r][c] = remap[content_grid[r][c]]
                    if grid[r][c] in remap:
                        grid[r][c] = remap[grid[r][c]]

            content_colors = Counter(
                v for row in content_grid for v in row if v > 0
            )

    # 7. FieldMap (flip_y=True: 게임 좌표계)
    fieldmap = grid_to_fieldmap(grid, flip_y=True)
    content_fieldmap = grid_to_fieldmap(content_grid, flip_y=True)

    result = {
        "source": str(img_path),
        "grid_rows": profile["grid"]["rows"],
        "grid_cols": profile["grid"]["cols"],
        "crop_rect": crop_rect,
        "elements": element_stats,
        "num_colors": len(content_colors),
        "color_distribution": " ".join(
            f"c{cid}({COLOR_NAMES.get(cid, '?')}):{cnt}"
            for cid, cnt in content_colors.most_common()
        ),
        "fieldmap": fieldmap,
        "content_fieldmap": content_fieldmap,
    }

    # 출력
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        name = Path(img_path).stem

        render_colors = None
        if "render_ranges" in profile:
            render_colors = {}
            for cid_str, info in profile["render_ranges"].items():
                m = info.get("render_mean", info.get("ref_rgb"))
                render_colors[int(cid_str)] = tuple(int(v) for v in m)

        vis_full = render_grid(
            grid, cell_size=10, frame_mask=None, render_colors=render_colors
        )
        vis_full.save(str(out / f"{name}_grid_full.png"))

        vis_content = render_grid(
            grid, cell_size=10, frame_mask=frame_mask,
            render_colors=render_colors
        )
        vis_content.save(str(out / f"{name}_grid_content.png"))

        level_json = grid_to_level_json(grid, content_grid, level_num)
        with open(out / f"{name}.json", "w", encoding="utf-8") as f:
            json.dump(level_json, f, indent=2, ensure_ascii=False)

        with open(out / f"{name}_analysis.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    return result


def analyze_batch(input_dir, profile, output_dir=None, start_level=1):
    """폴더 일괄 분석."""
    input_dir = Path(input_dir)
    images = sorted(input_dir.glob("*.png")) + sorted(input_dir.glob("*.jpg"))

    if not images:
        print(f"No images in {input_dir}")
        return []

    results = []
    for i, img_path in enumerate(images):
        level_num = start_level + i
        print(f"  [{i + 1}/{len(images)}] {img_path.name}", end=" ")
        r = analyze(img_path, profile, output_dir, level_num)
        if "error" in r:
            print(f"FAIL: {r['error']}")
        else:
            print(f"OK: {r['num_colors']}색, "
                  f"content={r['elements']['content']}, "
                  f"frame={r['elements']['frame']}")
        results.append(r)

    ok = sum(1 for r in results if "error" not in r)
    print(f"\n  완료: {ok}/{len(results)}")
    return results


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Cell-Aware Board Analyzer v2")
    parser.add_argument("input", help="이미지 파일 또는 폴더")
    parser.add_argument("--profile", "-p", required=True, help="cell_profile.json")
    parser.add_argument("--output-dir", "-o", help="출력 폴더")
    parser.add_argument("--batch", action="store_true")
    parser.add_argument("--start-level", type=int, default=1)
    args = parser.parse_args()

    profile = load_profile(args.profile)

    if args.batch or Path(args.input).is_dir():
        analyze_batch(args.input, profile, args.output_dir, args.start_level)
    else:
        r = analyze(args.input, profile, args.output_dir or ".")
        if "error" in r:
            print(f"Error: {r['error']}")
        else:
            print(f"Grid: {r['grid_rows']}x{r['grid_cols']}")
            print(f"Colors: {r['num_colors']}")
            print(f"Elements: {r['elements']}")
            print(f"Distribution: {r['color_distribution']}")


if __name__ == "__main__":
    main()
