"""
Level Grid → PNG 렌더러 (PIL).

generator가 만든 cells array를 BalloonFlow 24색을 사용해 PNG로 그린다.
픽셀 단위 정확도. 격자선·색상별 카운트 라벨 옵션 포함.

design_level_designer 결과물의 시각 미리보기 + Unity import 전 검수용.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger("level-png")

# BalloonFlow BalloonController.BalloonColors 그대로 (RGB 0-255)
BALLOONFLOW_COLORS_RGB: list[tuple[int, int, int]] = [
    (252, 106, 175),  #  0: HotPink
    ( 80, 232, 246),  #  1: Cyan
    (137,  80, 248),  #  2: Purple
    (254, 213,  85),  #  3: Yellow
    (115, 254, 102),  #  4: Green
    (253, 161,  76),  #  5: Orange
    (255, 255, 255),  #  6: White
    ( 65,  65,  65),  #  7: DarkGray
    (110, 168, 250),  #  8: SkyBlue
    ( 57, 174,  46),  #  9: Forest
    (252,  94,  94),  # 10: Red
    ( 50, 107, 248),  # 11: Blue
    ( 58, 165, 139),  # 12: Teal
    (231, 167, 250),  # 13: Lavender
    (183, 199, 251),  # 14: Periwinkle
    (106,  74,  48),  # 15: Brown
    (254, 227, 169),  # 16: Cream
    (253, 183, 193),  # 17: Pink
    (158,  61,  94),  # 18: Wine
    (167, 221, 148),  # 19: Mint
    ( 89,  46, 126),  # 20: Indigo
    (220, 120, 129),  # 21: Rose
    (217, 217, 231),  # 22: Silver
    (111, 114, 127),  # 23: Gray
]
BALLOONFLOW_COLOR_NAMES = [
    "HotPink", "Cyan", "Purple", "Yellow", "Green", "Orange", "White",
    "DarkGray", "SkyBlue", "Forest", "Red", "Blue", "Teal", "Lavender",
    "Periwinkle", "Brown", "Cream", "Pink", "Wine", "Mint", "Indigo",
    "Rose", "Silver", "Gray",
]

EMPTY_BG = (245, 245, 248)   # 빈셀 배경
GRID_LINE = (200, 200, 210)
TITLE_BG  = (28, 30, 42)
TITLE_FG  = (240, 240, 245)


def render_grid_to_png(
    cells: list[list[int]],
    *,
    cell_size_px: int = 32,
    grid_line_px: int = 1,
    show_legend: bool = True,
    title: str = "",
) -> bytes:
    """
    cells (-1=empty, 0..23=color index) → PNG bytes.

    레이아웃:
      ┌─────────────────────────┐
      │ Title (optional)        │  height=40
      ├─────────────────────────┤
      │                         │
      │   Grid (W×H × cell_px)  │
      │                         │
      ├─────────────────────────┤
      │ Color legend (optional) │  height=30 per row × ceil(N/6) rows
      └─────────────────────────┘
    """
    from PIL import Image, ImageDraw, ImageFont

    h = len(cells)
    w = len(cells[0]) if h else 0
    if w == 0 or h == 0:
        raise ValueError("empty grid")

    grid_w = w * cell_size_px + grid_line_px
    grid_h = h * cell_size_px + grid_line_px

    title_h = 40 if title else 0

    # legend: 사용된 색만
    used_colors = sorted({v for row in cells for v in row if v != -1})
    legend_h = 0
    legend_per_row = max(1, grid_w // 110)
    legend_rows = (len(used_colors) + legend_per_row - 1) // legend_per_row if show_legend and used_colors else 0
    if show_legend and legend_rows:
        legend_h = 12 + 28 * legend_rows

    total_w = grid_w + 16  # padding
    total_h = title_h + grid_h + legend_h + 16

    img = Image.new("RGBA", (total_w, total_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 11)
    except OSError:
        font = ImageFont.load_default()
        font_small = ImageFont.load_default()

    y_off = 8

    # Title bar
    if title:
        draw.rectangle((8, y_off, total_w - 8, y_off + title_h - 4), fill=TITLE_BG)
        draw.text((16, y_off + 8), title, fill=TITLE_FG, font=font)
        y_off += title_h

    # Grid border + background
    grid_x0 = 8
    grid_y0 = y_off
    draw.rectangle(
        (grid_x0, grid_y0, grid_x0 + grid_w, grid_y0 + grid_h),
        fill=EMPTY_BG, outline=GRID_LINE, width=grid_line_px,
    )
    # 셀 그리기
    color_counts: dict[int, int] = {}
    for r in range(h):
        for c in range(w):
            v = cells[r][c]
            x0 = grid_x0 + c * cell_size_px + grid_line_px
            y0 = grid_y0 + r * cell_size_px + grid_line_px
            x1 = x0 + cell_size_px - grid_line_px
            y1 = y0 + cell_size_px - grid_line_px
            if v != -1:
                if 0 <= v < len(BALLOONFLOW_COLORS_RGB):
                    rgb = BALLOONFLOW_COLORS_RGB[v]
                    color_counts[v] = color_counts.get(v, 0) + 1
                else:
                    rgb = (255, 0, 255)  # invalid color → magenta
                draw.rectangle((x0, y0, x1, y1), fill=rgb)
    # 격자 선 (10번째마다 진한 선 → 가독성)
    if cell_size_px >= 12:
        for c in range(w + 1):
            x = grid_x0 + c * cell_size_px
            color = GRID_LINE if c % 10 != 0 else (140, 140, 150)
            draw.line(
                (x, grid_y0, x, grid_y0 + grid_h),
                fill=color, width=grid_line_px,
            )
        for r in range(h + 1):
            y = grid_y0 + r * cell_size_px
            color = GRID_LINE if r % 10 != 0 else (140, 140, 150)
            draw.line(
                (grid_x0, y, grid_x0 + grid_w, y),
                fill=color, width=grid_line_px,
            )

    y_off = grid_y0 + grid_h + 8

    # Legend
    if show_legend and used_colors:
        draw.text((10, y_off), "Colors used:", fill=(60, 60, 70), font=font_small)
        y_off += 14
        for i, ci in enumerate(used_colors):
            row = i // legend_per_row
            col = i % legend_per_row
            x0 = 10 + col * 110
            y0 = y_off + row * 22
            rgb = BALLOONFLOW_COLORS_RGB[ci] if 0 <= ci < len(BALLOONFLOW_COLORS_RGB) else (255, 0, 255)
            draw.rectangle((x0, y0, x0 + 16, y0 + 16), fill=rgb, outline=(60, 60, 70))
            name = BALLOONFLOW_COLOR_NAMES[ci] if 0 <= ci < len(BALLOONFLOW_COLOR_NAMES) else "?"
            cnt = color_counts.get(ci, 0)
            draw.text(
                (x0 + 22, y0 + 1),
                f"{ci}:{name} ({cnt})",
                fill=(50, 50, 60), font=font_small,
            )

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def save_grid_png(
    cells: list[list[int]], output_path: str,
    **kwargs,
) -> str:
    """파일로 저장 후 절대경로 반환."""
    data = render_grid_to_png(cells, **kwargs)
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return str(p.resolve())


# ───────── self-test ─────────
if __name__ == "__main__":
    import os, sys
    from level_grid_generator import GridSpec, generate_grid

    out_dir = Path(os.environ.get("LEVEL_TEST_OUT", "/tmp/level_test"))
    out_dir.mkdir(parents=True, exist_ok=True)

    # 같은 spec에서 pattern만 바꿔 시각 비교
    base_palette = [0, 2, 13, 17, 21]  # 분홍-보라 톤
    base_counts = {0: 40, 2: 40, 13: 60, 17: 40, 21: 20}
    cases = [
        ("pattern_rings_4foldrot", GridSpec(
            width=25, height=25, symmetry="4-fold-rot",
            palette=base_palette, per_color_count=base_counts,
            pattern="rings", seed=42,
        )),
        ("pattern_rays_4foldrot", GridSpec(
            width=25, height=25, symmetry="4-fold-rot",
            palette=base_palette, per_color_count=base_counts,
            pattern="rays", seed=42,
        )),
        ("pattern_spiral_4foldrot", GridSpec(
            width=25, height=25, symmetry="4-fold-rot",
            palette=base_palette, per_color_count=base_counts,
            pattern="spiral", seed=42,
        )),
        ("pattern_diamond_4fold", GridSpec(
            width=25, height=25, symmetry="4-fold",
            palette=base_palette, per_color_count=base_counts,
            pattern="diamond", seed=42,
        )),
        ("pattern_blocks_4fold", GridSpec(
            width=25, height=25, symmetry="4-fold",
            palette=base_palette, per_color_count=base_counts,
            pattern="blocks", seed=42,
        )),
        ("pattern_random_4foldrot", GridSpec(
            width=25, height=25, symmetry="4-fold-rot",
            palette=base_palette, per_color_count=base_counts,
            pattern="random", seed=42,
        )),
    ]

    for name, spec in cases:
        result = generate_grid(spec)
        png = render_grid_to_png(
            result.cells, cell_size_px=24,
            title=f"{name} · {spec.symmetry} · {spec.width}×{spec.height} · seed={spec.seed}",
        )
        path = out_dir / f"{name}.png"
        path.write_bytes(png)
        print(f"✓ wrote {path} ({len(png)} bytes)")

    print(f"\n✅ {len(cases)} PNGs saved to {out_dir}")
