"""
Cell Renderer — 이미지를 퍼즐 보드 스타일 셀 그리드로 변환
===========================================================
SD 생성 이미지 → NxN 셀 그리드 → 둥근 사각형 블록 렌더링

레퍼런스: pixelflow boards (620x690, ~20x23 셀, 둥근 블록, 그림자)
"""

import argparse
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


def image_to_grid(img: Image.Image, cols: int, rows: int,
                  n_colors: int = 16) -> np.ndarray:
    """이미지를 cols x rows 컬러 그리드로 변환.

    각 셀 = 해당 블록 영역의 최빈 색상 (하나의 셀 = 하나의 색상).
    Returns: (rows, cols, 3) numpy array
    """
    from sklearn.cluster import KMeans

    arr = np.array(img.convert("RGB"))
    h, w, _ = arr.shape

    # 먼저 전체 이미지의 팔레트를 결정
    pixels_all = arr.reshape(-1, 3).astype(np.float32)
    # 샘플링 (성능)
    sample_idx = np.random.default_rng(42).choice(
        len(pixels_all), min(10000, len(pixels_all)), replace=False)
    kmeans = KMeans(n_clusters=n_colors, n_init=3, max_iter=100, random_state=42)
    kmeans.fit(pixels_all[sample_idx])
    palette = kmeans.cluster_centers_.astype(np.uint8)

    # 각 셀의 대표 색상 추출
    cell_h = h / rows
    cell_w = w / cols
    grid = np.zeros((rows, cols, 3), dtype=np.uint8)

    for r in range(rows):
        for c in range(cols):
            y1 = int(r * cell_h)
            y2 = int((r + 1) * cell_h)
            x1 = int(c * cell_w)
            x2 = int((c + 1) * cell_w)
            block = arr[y1:y2, x1:x2].reshape(-1, 3).astype(np.float32)

            # 블록 평균 색상 → 가장 가까운 팔레트 색상
            avg = block.mean(axis=0)
            dists = np.sum((palette.astype(float) - avg) ** 2, axis=1)
            grid[r, c] = palette[np.argmin(dists)]

    return grid, palette


def find_bg_color(grid: np.ndarray) -> tuple:
    """그리드에서 가장 빈번한 색상 = 배경색으로 판별."""
    rows, cols, _ = grid.shape
    pixels = grid.reshape(-1, 3)
    keys = pixels[:, 0].astype(np.uint32) * 65536 + \
           pixels[:, 1].astype(np.uint32) * 256 + \
           pixels[:, 2].astype(np.uint32)
    counts = np.bincount(keys)
    dominant = counts.argmax()
    return ((dominant >> 16) & 0xFF, (dominant >> 8) & 0xFF, dominant & 0xFF)


def render_cell_board(grid: np.ndarray, cell_size: int = 28,
                      gap: int = 2, corner_radius: int = 4,
                      bg_color: tuple = (40, 40, 60),
                      shadow: bool = True,
                      transparent_bg: bool = False) -> Image.Image:
    """셀 그리드를 퍼즐 보드 스타일로 렌더링.

    Args:
        grid: (rows, cols, 3) 색상 배열
        cell_size: 각 셀 블록의 픽셀 크기
        gap: 셀 사이 간격
        corner_radius: 둥근 모서리 반경
        bg_color: 배경색
        shadow: 블록 그림자 효과
        transparent_bg: 투명 배경 (PNG)
    """
    rows, cols, _ = grid.shape
    img_w = cols * (cell_size + gap) + gap
    img_h = rows * (cell_size + gap) + gap

    if transparent_bg:
        img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        grid_bg = find_bg_color(grid)  # 최빈 색상 = 배경
    else:
        img = Image.new("RGBA", (img_w, img_h), bg_color + (255,))
        grid_bg = None

    draw = ImageDraw.Draw(img)

    for r in range(rows):
        for c in range(cols):
            color = tuple(grid[r, c])
            x = gap + c * (cell_size + gap)
            y = gap + r * (cell_size + gap)

            # 투명 모드: 배경색과 유사한 셀은 스킵
            if grid_bg is not None:
                diff = sum(abs(int(a) - int(b)) for a, b in zip(color, grid_bg))
                if diff < 60:
                    continue

            # 그림자 (어두운 색, 1px 오프셋)
            if shadow and not transparent_bg:
                shadow_color = tuple(max(0, int(v) - 60) for v in color)
                draw.rounded_rectangle(
                    [x + 1, y + 1, x + cell_size, y + cell_size],
                    radius=corner_radius,
                    fill=shadow_color + (255,))

            # 메인 블록
            draw.rounded_rectangle(
                [x, y, x + cell_size - 1, y + cell_size - 1],
                radius=corner_radius,
                fill=color + (255,))

            # 하이라이트 (밝은 색, 좌상단 — 레퍼런스 수준으로 크게)
            highlight = tuple(min(255, int(v) + 50) for v in color)
            hl_size = max(3, cell_size // 4)
            draw.rounded_rectangle(
                [x + 2, y + 2, x + hl_size + 2, y + hl_size + 2],
                radius=max(1, corner_radius // 2),
                fill=highlight + (160,))

    return img


def render_flat_grid(grid: np.ndarray, cell_size: int = 1,
                     transparent_bg: bool = False,
                     bg_threshold: int = -1) -> Image.Image:
    """순수 플랫 픽셀 그리드 (블록 효과 없이 정확한 셀).

    cell_size=1이면 각 셀이 정확히 1px.
    transparent_bg=True이면 배경색 셀을 투명 처리.
    """
    rows, cols, _ = grid.shape
    if transparent_bg:
        img = Image.new("RGBA", (cols * cell_size, rows * cell_size), (0, 0, 0, 0))
    else:
        img = Image.new("RGB", (cols * cell_size, rows * cell_size))

    arr = np.array(img)

    for r in range(rows):
        for c in range(cols):
            color = tuple(grid[r, c])
            y1, y2 = r * cell_size, (r + 1) * cell_size
            x1, x2 = c * cell_size, (c + 1) * cell_size

            if transparent_bg and bg_threshold >= 0:
                # 코너 색상과 유사한 셀 = 투명
                brightness = sum(color) / 3
                if brightness > 240 or brightness < 15:
                    continue  # 투명 유지

            if img.mode == "RGBA":
                arr[y1:y2, x1:x2] = list(color) + [255]
            else:
                arr[y1:y2, x1:x2] = color

    return Image.fromarray(arr)


def process_image(input_path: str, cols: int = 20, rows: int = 20,
                  n_colors: int = 16, cell_size: int = 28,
                  gap: int = 2, corner_radius: int = 4,
                  style: str = "board", transparent_bg: bool = False,
                  output_name: str = None):
    """이미지를 셀 그리드로 변환하고 렌더링."""

    img = Image.open(input_path).convert("RGB")
    print(f"[CellRenderer] Input: {input_path} ({img.size})")
    print(f"[CellRenderer] Grid: {cols}x{rows}, {n_colors} colors, style={style}")

    # 1) 이미지 → 셀 그리드
    grid, palette = image_to_grid(img, cols, rows, n_colors)
    print(f"[CellRenderer] Palette: {len(palette)} colors extracted")

    # 2) 렌더링
    if style == "board":
        rendered = render_cell_board(
            grid, cell_size=cell_size, gap=gap,
            corner_radius=corner_radius,
            transparent_bg=transparent_bg)
    elif style == "flat":
        rendered = render_flat_grid(
            grid, cell_size=cell_size,
            transparent_bg=transparent_bg,
            bg_threshold=0 if transparent_bg else -1)
    else:
        raise ValueError(f"Unknown style: {style}")

    # 3) 저장
    name = output_name or Path(input_path).stem
    ext = "png"  # 항상 PNG (투명 지원)

    rendered_path = OUTPUT_DIR / f"{name}_cells.{ext}"
    rendered.save(rendered_path)
    print(f"[CellRenderer] Saved: {rendered_path} ({rendered.size})")

    # 그리드 데이터도 JSON으로 저장
    grid_data = {
        "cols": cols, "rows": rows,
        "n_colors": n_colors,
        "palette": palette.tolist(),
        "grid": grid.tolist(),
    }
    json_path = OUTPUT_DIR / f"{name}_grid.json"
    with open(json_path, "w") as f:
        json.dump(grid_data, f)
    print(f"[CellRenderer] Grid data: {json_path}")

    return rendered, grid, palette


def main():
    parser = argparse.ArgumentParser(description="Cell Renderer — Image to Cell Grid")
    parser.add_argument("input", type=str, help="Input image path")
    parser.add_argument("--cols", type=int, default=20, help="Grid columns")
    parser.add_argument("--rows", type=int, default=20, help="Grid rows")
    parser.add_argument("--colors", "-c", type=int, default=16, help="Palette colors")
    parser.add_argument("--cell-size", type=int, default=28, help="Cell pixel size")
    parser.add_argument("--gap", type=int, default=2, help="Cell gap")
    parser.add_argument("--corner", type=int, default=4, help="Corner radius")
    parser.add_argument("--style", choices=["board", "flat"], default="board")
    parser.add_argument("--transparent", action="store_true", help="Transparent background")
    parser.add_argument("--name", type=str, default=None, help="Output name")

    args = parser.parse_args()
    process_image(
        args.input, cols=args.cols, rows=args.rows,
        n_colors=args.colors, cell_size=args.cell_size,
        gap=args.gap, corner_radius=args.corner,
        style=args.style, transparent_bg=args.transparent,
        output_name=args.name)


if __name__ == "__main__":
    main()
