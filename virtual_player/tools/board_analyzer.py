"""
Board Analyzer v2 — Connected Components + Color Clustering
=============================================================
게임 스크린샷에서 퍼즐 보드를 정밀 분석.

기존 FFT 방식의 한계를 극복:
  - Connected Components로 개별 셀 감지
  - K-means 색상 클러스터링으로 타일 색상 분류
  - 가장자리 불완전 셀 자동 제거
  - 워터마크/텍스트 자동 무시

사용법:
  python board_analyzer.py <이미지> [--output-dir <출력폴더>] [--game balloonflow]
  python board_analyzer.py <이미지폴더> --batch [--output-dir <출력폴더>]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


# ══════════════════════════════════════════════════════════════
#  1. Board Crop (개선 — 타일 시작점 기준)
# ══════════════════════════════════════════════════════════════

def crop_board_precise(img):
    """프레임이 아닌 타일 시작점을 기준으로 보드를 크롭.

    단계:
      1. 채도가 높은 영역 = 타일 (프레임/배경은 무채색)
      2. 타일 영역의 bounding box = 보드
    """
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # 채도 > 40인 픽셀 = 색이 있는 타일
    sat_mask = hsv[:, :, 1] > 40
    # 밝기도 어느 정도 있어야 (너무 어두운 건 갭/배경)
    val_mask = hsv[:, :, 2] > 60
    tile_mask = (sat_mask & val_mask).astype(np.uint8) * 255

    # 모폴로지로 노이즈 제거 + 타일 연결
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    tile_mask = cv2.morphologyEx(tile_mask, cv2.MORPH_CLOSE, kernel)
    tile_mask = cv2.morphologyEx(tile_mask, cv2.MORPH_OPEN, kernel)

    # 타일 영역의 bounding box
    coords = cv2.findNonZero(tile_mask)
    if coords is None:
        return img, (0, 0, w, h)

    x, y, bw, bh = cv2.boundingRect(coords)

    # 약간의 패딩 (셀 갭 포함)
    pad = 3
    x = max(0, x - pad)
    y = max(0, y - pad)
    bw = min(w - x, bw + pad * 2)
    bh = min(h - y, bh + pad * 2)

    return img[y:y + bh, x:x + bw], (x, y, bw, bh)


# ══════════════════════════════════════════════════════════════
#  2. Grid Detection (Connected Components)
# ══════════════════════════════════════════════════════════════

def detect_grid_cc(board_img):
    """Connected Components로 개별 셀을 감지하여 그리드 크기 결정.

    단계:
      1. 타일 색상 마스크 (채도 기반)
      2. erode로 인접 셀 분리
      3. connectedComponents로 개별 셀 카운트
      4. 셀 위치의 x,y 클러스터링 → rows, cols
      5. 가장자리 불완전 셀 제거

    Returns:
      rows, cols, cell_positions[(cx, cy, w, h)], cell_size
    """
    h, w = board_img.shape[:2]
    hsv = cv2.cvtColor(board_img, cv2.COLOR_BGR2HSV)

    # 채도 있는 픽셀 = 타일
    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    tile_mask = ((sat > 30) & (val > 50)).astype(np.uint8) * 255

    # erode로 인접 셀 분리 (셀 사이 갭 확대)
    # 갭 크기를 추정: 이미지 크기의 ~0.5%
    gap_size = max(2, int(min(w, h) * 0.005))
    erode_kernel = cv2.getStructuringElement(cv2.MORPH_RECT,
                                              (gap_size, gap_size))
    separated = cv2.erode(tile_mask, erode_kernel, iterations=1)

    # Connected Components
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        separated, connectivity=8)

    # 배경(label 0) 제외, 면적 필터
    min_area = (min(w, h) / 50) ** 2  # 최소 셀 면적
    max_area = (min(w, h) / 3) ** 2   # 최대 셀 면적 (너무 크면 병합된 것)

    cells = []
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        cx, cy = centroids[i]
        cw = stats[i, cv2.CC_STAT_WIDTH]
        ch = stats[i, cv2.CC_STAT_HEIGHT]

        if min_area < area < max_area:
            cells.append({
                "cx": cx, "cy": cy,
                "x": stats[i, cv2.CC_STAT_LEFT],
                "y": stats[i, cv2.CC_STAT_TOP],
                "w": cw, "h": ch,
                "area": area,
            })

    if not cells:
        return 0, 0, [], 0

    # 셀 크기 추정 (중간값)
    widths = [c["w"] for c in cells]
    heights = [c["h"] for c in cells]
    med_w = np.median(widths)
    med_h = np.median(heights)
    cell_size = (med_w + med_h) / 2

    # 가장자리 불완전 셀 제거 (평균의 60% 미만)
    min_w = med_w * 0.6
    min_h = med_h * 0.6
    cells = [c for c in cells if c["w"] >= min_w and c["h"] >= min_h]

    if not cells:
        return 0, 0, [], cell_size

    # x, y 좌표 클러스터링 → rows, cols 결정
    xs = sorted(set(round(c["cx"] / cell_size) for c in cells))
    ys = sorted(set(round(c["cy"] / cell_size) for c in cells))

    # 실제 row/col 수
    cols = len(xs)
    rows = len(ys)

    # 셀 위치 정규화 (grid 좌표로 변환)
    for c in cells:
        c["grid_col"] = round(c["cx"] / cell_size)
        c["grid_row"] = round(c["cy"] / cell_size)

    return rows, cols, cells, cell_size


# ══════════════════════════════════════════════════════════════
#  3. Color Extraction (K-means + Palette Matching)
# ══════════════════════════════════════════════════════════════

def extract_cell_colors(board_img, cells, cell_size, palette=None):
    """각 셀의 중심 색상을 추출하고 팔레트에 매칭.

    Returns:
      grid_map[row][col] = {"color_id": int, "rgb": (r,g,b), "name": str}
    """
    h, w = board_img.shape[:2]

    # 그리드 맵 초기화
    if not cells:
        return [], {}

    max_row = max(c["grid_row"] for c in cells) + 1
    max_col = max(c["grid_col"] for c in cells) + 1

    grid_map = [[None for _ in range(max_col)] for _ in range(max_row)]
    color_counts = Counter()

    # 팔레트 준비
    pal_arr = None
    pal_ids = []
    pal_names = {}
    if palette:
        pal_arr = np.array([p["rgb"] for p in palette], dtype=np.float32)
        pal_ids = [p["id"] for p in palette]
        pal_names = {p["id"]: p["name"] for p in palette}

    for c in cells:
        # 셀 중심 50% 영역 샘플링
        cx, cy = int(c["cx"]), int(c["cy"])
        margin = max(1, int(cell_size * 0.2))
        y1 = max(0, cy - margin)
        y2 = min(h, cy + margin)
        x1 = max(0, cx - margin)
        x2 = min(w, cx + margin)

        region = board_img[y1:y2, x1:x2]
        if region.size == 0:
            continue

        # 최빈색 추출
        q = (region // 32) * 32 + 16
        flat = q.reshape(-1, 3)
        keys = flat[:, 0].astype(int) * 65536 + flat[:, 1].astype(int) * 256 + flat[:, 2].astype(int)
        unique, counts = np.unique(keys, return_counts=True)
        mode_key = unique[np.argmax(counts)]
        b_val = (mode_key >> 16) & 0xFF
        g_val = (mode_key >> 8) & 0xFF
        r_val = mode_key & 0xFF
        rgb = (r_val, g_val, b_val)

        # 팔레트 매칭
        if pal_arr is not None:
            dists = np.sqrt(np.sum((pal_arr - np.array(rgb, dtype=np.float32)) ** 2, axis=1))
            best_idx = int(np.argmin(dists))
            color_id = pal_ids[best_idx]
            color_name = pal_names.get(color_id, f"C{color_id}")
        else:
            # 팔레트 없으면 RGB 값 직접 사용
            color_id = 0
            color_name = f"#{r_val:02x}{g_val:02x}{b_val:02x}"

        r_idx = c["grid_row"]
        c_idx = c["grid_col"]
        if 0 <= r_idx < max_row and 0 <= c_idx < max_col:
            grid_map[r_idx][c_idx] = {
                "color_id": color_id,
                "rgb": rgb,
                "name": color_name,
            }
            color_counts[color_id] += 1

    return grid_map, dict(color_counts)


# ══════════════════════════════════════════════════════════════
#  4. FieldMap 생성
# ══════════════════════════════════════════════════════════════

def generate_fieldmap(grid_map, rows, cols):
    """grid_map → FieldMap 문자열."""
    lines = []
    for r in range(rows):
        row_tokens = []
        for c in range(cols):
            if r < len(grid_map) and c < len(grid_map[r]) and grid_map[r][c]:
                cid = grid_map[r][c]["color_id"]
                row_tokens.append(f"{cid:02d}")
            else:
                row_tokens.append("..")
        lines.append(" ".join(row_tokens))
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
#  5. 시각화
# ══════════════════════════════════════════════════════════════

def draw_grid_overlay(board_img, cells, cell_size, grid_map=None):
    """분석 결과를 시각화."""
    vis = board_img.copy()

    for c in cells:
        x, y, w, h = int(c["x"]), int(c["y"]), int(c["w"]), int(c["h"])
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 1)

        # 색상 ID 표시
        if grid_map:
            r_idx = c["grid_row"]
            c_idx = c["grid_col"]
            if r_idx < len(grid_map) and c_idx < len(grid_map[r_idx]) and grid_map[r_idx][c_idx]:
                cid = grid_map[r_idx][c_idx]["color_id"]
                cv2.putText(vis, str(cid), (int(c["cx"]) - 5, int(c["cy"]) + 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255, 255, 255), 1)

    return vis


# ══════════════════════════════════════════════════════════════
#  6. Full Analysis Pipeline
# ══════════════════════════════════════════════════════════════

def analyze_board(img_path, palette=None, output_dir=None):
    """단일 이미지 전체 분석.

    Returns:
        dict: {rows, cols, cell_size, grid_map, fieldmap, color_distribution, ...}
    """
    img = cv2.imread(str(img_path))
    if img is None:
        return {"error": f"Cannot read: {img_path}"}

    # 1. 보드 크롭
    board, crop_rect = crop_board_precise(img)
    bh, bw = board.shape[:2]

    # 2. 그리드 감지
    rows, cols, cells, cell_size = detect_grid_cc(board)

    if rows < 2 or cols < 2:
        return {
            "error": "Grid detection failed",
            "board_size": (bw, bh),
            "cells_found": len(cells),
        }

    # 3. 색상 추출
    grid_map, color_counts = extract_cell_colors(board, cells, cell_size, palette)

    # 4. FieldMap
    fieldmap = generate_fieldmap(grid_map, rows, cols)

    # 5. 통계
    total_cells = sum(color_counts.values())
    num_colors = len([v for v in color_counts.values() if v > 0])

    # 색상 분포 문자열
    pal_names = {p["id"]: p["name"] for p in palette} if palette else {}
    dist_parts = []
    for cid, cnt in sorted(color_counts.items(), key=lambda x: -x[1]):
        name = pal_names.get(cid, f"C{cid}")
        pct = round(cnt / max(total_cells, 1) * 100, 1)
        dist_parts.append(f"{name}:{pct}%({cnt})")

    result = {
        "source": str(img_path),
        "board_size": (bw, bh),
        "grid_rows": rows,
        "grid_cols": cols,
        "cell_size": round(cell_size, 1),
        "total_cells": total_cells,
        "num_colors": num_colors,
        "color_distribution": " | ".join(dist_parts),
        "fieldmap": fieldmap,
        "color_counts": color_counts,
    }

    # 출력 저장
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        name = Path(img_path).stem

        # 크롭 이미지
        cv2.imwrite(str(out / f"{name}_board.png"), board)

        # 그리드 오버레이
        overlay = draw_grid_overlay(board, cells, cell_size, grid_map)
        cv2.imwrite(str(out / f"{name}_grid.png"), overlay)

        # JSON
        json_result = {k: v for k, v in result.items() if k != "color_counts"}
        json_result["color_counts"] = {str(k): v for k, v in color_counts.items()}
        with open(out / f"{name}_analysis.json", "w", encoding="utf-8") as f:
            json.dump(json_result, f, indent=2, ensure_ascii=False)

    return result


def analyze_batch(input_dir, palette=None, output_dir=None):
    """폴더 내 모든 이미지 일괄 분석."""
    input_dir = Path(input_dir)
    images = sorted(input_dir.glob("*.png")) + sorted(input_dir.glob("*.jpg"))

    if not images:
        print(f"No images found in {input_dir}")
        return []

    results = []
    for i, img_path in enumerate(images):
        print(f"  [{i + 1}/{len(images)}] {img_path.name}", end=" ")
        r = analyze_board(img_path, palette, output_dir)

        if "error" in r:
            print(f"FAIL: {r['error']}")
        else:
            print(f"OK: {r['grid_rows']}x{r['grid_cols']} "
                  f"({r['total_cells']} cells, {r['num_colors']} colors)")

        results.append(r)

    # 요약
    ok = sum(1 for r in results if "error" not in r)
    print(f"\n  완료: {ok}/{len(results)} 성공")

    return results


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════

def load_palette(game_id):
    """game_profiles.json에서 팔레트 로드."""
    profiles_path = Path(__file__).parent / "game_profiles.json"
    if profiles_path.exists():
        with open(profiles_path, "r", encoding="utf-8") as f:
            profiles = json.load(f)
        if game_id in profiles:
            return profiles[game_id].get("color_palette_28", [])
    return []


def main():
    parser = argparse.ArgumentParser(description="Board Analyzer v2")
    parser.add_argument("input", help="이미지 파일 또는 폴더")
    parser.add_argument("--output-dir", "-o", help="출력 폴더")
    parser.add_argument("--game", default="balloonflow", help="게임 ID (팔레트 선택)")
    parser.add_argument("--batch", action="store_true", help="폴더 일괄 처리")
    parser.add_argument("--no-palette", action="store_true", help="팔레트 없이 분석")

    args = parser.parse_args()
    palette = [] if args.no_palette else load_palette(args.game)

    if args.batch or Path(args.input).is_dir():
        results = analyze_batch(args.input, palette, args.output_dir)
    else:
        r = analyze_board(args.input, palette, args.output_dir or ".")
        if "error" in r:
            print(f"Error: {r['error']}")
        else:
            print(f"\nGrid: {r['grid_rows']}x{r['grid_cols']}")
            print(f"Cells: {r['total_cells']}")
            print(f"Colors: {r['num_colors']}")
            print(f"Distribution: {r['color_distribution']}")
            print(f"\nFieldMap:")
            print(r["fieldmap"])


if __name__ == "__main__":
    main()
