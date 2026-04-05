"""
PixelLab API + Local Cell Renderer Pipeline
============================================
PixelLab API로 고품질 픽셀아트 생성 → 로컬에서 인게임 팔레트 + 셀 보드 렌더링.

사용법:
  # 1. 텍스트로 새 이미지 생성
  python pixellab_pipeline.py --prompt "cute penguin" --cols 50 --rows 50

  # 2. 스타일 참조 + 새 주제
  python pixellab_pipeline.py --prompt "cute dog" --style-ref ref.png --cols 50 --rows 50

  # 3. 배경 없는 캐릭터
  python pixellab_pipeline.py --prompt "cute cat" --cols 50 --rows 50 --transparent

  # 4. 배치 생성
  python pixellab_pipeline.py --batch batch.json

환경변수:
  PIXELLAB_API_KEY=your_api_key_here
"""

import argparse
import base64
import json
import os
import time
from io import BytesIO
from pathlib import Path

import numpy as np
import requests
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

API_BASE = "https://api.pixellab.ai/v2"
API_KEY = os.environ.get("PIXELLAB_API_KEY", "")

# ── 인게임 15색 핵심 팔레트 ──
PALETTE_CORE = np.array([
    [252, 94, 94],    [253, 161, 76],   [254, 213, 85],
    [115, 254, 102],  [57, 174, 46],    [80, 232, 246],
    [50, 107, 248],   [137, 80, 248],   [252, 106, 175],
    [252, 56, 165],   [255, 255, 255],  [65, 65, 65],
    [111, 114, 127],  [106, 74, 48],    [254, 227, 169],
], dtype=np.float32)


# ═══════════════════════════════════════════════════════════
#  1. PixelLab API
# ═══════════════════════════════════════════════════════════

def pixellab_generate(prompt: str, width: int = 128, height: int = 128,
                      remove_bg: bool = True,
                      style_ref: str = None) -> Image.Image:
    """PixelLab Pixflux API로 픽셀아트 생성."""
    if not API_KEY:
        raise ValueError("PIXELLAB_API_KEY 환경변수를 설정하세요")

    headers = {"Authorization": f"Bearer {API_KEY}",
               "Content-Type": "application/json"}

    if style_ref:
        # Bitforge: 스타일 참조 생성
        ref_img = Image.open(style_ref).convert("RGB")
        buf = BytesIO()
        ref_img.save(buf, format="PNG")
        ref_b64 = base64.b64encode(buf.getvalue()).decode()

        payload = {
            "description": prompt,
            "image_size": {"width": width, "height": height},
            "style_image": {"type": "base64",
                            "base64": f"data:image/png;base64,{ref_b64}"},
            "isTransparent": remove_bg,
        }
        endpoint = f"{API_BASE}/create-image-bitforge"
    else:
        # Pixflux: 텍스트 → 픽셀아트
        payload = {
            "description": prompt,
            "negative_description": "blurry, gradient, photorealistic",
            "image_size": {"width": width, "height": height},
            "isTransparent": remove_bg,
        }
        endpoint = f"{API_BASE}/create-image-pixflux"

    print(f"[PixelLab] Generating: '{prompt}' ({width}x{height})...")
    t0 = time.time()
    resp = requests.post(endpoint, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    # base64 → PIL Image
    img_b64 = data["image"]["base64"].split(",")[-1]
    img = Image.open(BytesIO(base64.b64decode(img_b64)))
    elapsed = time.time() - t0
    print(f"[PixelLab] Done in {elapsed:.1f}s (${data.get('cost', '?')})")

    return img


# ═══════════════════════════════════════════════════════════
#  2. 로컬 후처리 (팔레트 + 그리드 + 셀 렌더링)
# ═══════════════════════════════════════════════════════════

def to_palette_grid(img: Image.Image, cols: int, rows: int) -> np.ndarray:
    """이미지 → 인게임 15색 팔레트 그리드."""
    small = img.convert("RGB").resize((cols, rows), Image.NEAREST)
    arr = np.array(small).astype(np.float32)

    grid = np.zeros((rows, cols, 3), dtype=np.uint8)
    for r in range(rows):
        for c in range(cols):
            dists = np.sum((PALETTE_CORE - arr[r, c]) ** 2, axis=1)
            grid[r, c] = PALETTE_CORE[np.argmin(dists)].astype(np.uint8)

    # 고립 셀 제거 (2회)
    for _ in range(2):
        grid = clean_grid(grid)

    return grid


def clean_grid(grid: np.ndarray) -> np.ndarray:
    """고립 셀 제거."""
    from collections import Counter
    rows, cols, _ = grid.shape
    result = grid.copy()
    for r in range(rows):
        for c in range(cols):
            color = tuple(grid[r, c])
            neighbors = []
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols:
                    neighbors.append(tuple(grid[nr, nc]))
            if neighbors and color not in neighbors:
                result[r, c] = Counter(neighbors).most_common(1)[0][0]
    return result


def render_board(grid: np.ndarray, cell_size: int = 24,
                 gap: int = 2, corner: int = 3,
                 transparent: bool = False) -> Image.Image:
    """셀 그리드 → 둥근 블록 보드."""
    from PIL import ImageDraw

    rows, cols, _ = grid.shape
    w = cols * (cell_size + gap) + gap
    h = rows * (cell_size + gap) + gap

    # 배경색 판별
    pixels = grid.reshape(-1, 3)
    keys = pixels[:, 0].astype(np.uint32) * 65536 + \
           pixels[:, 1].astype(np.uint32) * 256 + \
           pixels[:, 2].astype(np.uint32)
    bg_key = np.bincount(keys).argmax()
    bg_color = ((bg_key >> 16) & 0xFF, (bg_key >> 8) & 0xFF, bg_key & 0xFF)

    if transparent:
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    else:
        img = Image.new("RGBA", (w, h), (42, 42, 80, 255))

    draw = ImageDraw.Draw(img)

    for r in range(rows):
        for c in range(cols):
            color = tuple(int(v) for v in grid[r, c])
            x = gap + c * (cell_size + gap)
            y = gap + r * (cell_size + gap)

            if transparent:
                diff = sum(abs(a - b) for a, b in zip(color, bg_color))
                if diff < 60:
                    continue

            shadow = tuple(max(0, v - 50) for v in color) + (255,)
            draw.rounded_rectangle([x+1, y+1, x+cell_size, y+cell_size],
                                   radius=corner, fill=shadow)
            draw.rounded_rectangle([x, y, x+cell_size-1, y+cell_size-1],
                                   radius=corner, fill=color + (255,))
            hl = tuple(min(255, v + 45) for v in color) + (150,)
            hl_s = max(3, cell_size // 4)
            draw.rounded_rectangle([x+2, y+2, x+hl_s+2, y+hl_s+2],
                                   radius=max(1, corner//2), fill=hl)
    return img


# ═══════════════════════════════════════════════════════════
#  3. 통합 파이프라인
# ═══════════════════════════════════════════════════════════

def generate(prompt: str, cols: int = 50, rows: int = 50,
             cell_size: int = 24, gap: int = 2, corner: int = 3,
             style_ref: str = None, transparent: bool = False,
             api_size: int = 128, name: str = None) -> dict:
    """전체 파이프라인: PixelLab API → 로컬 렌더링."""

    # 1. PixelLab API로 고품질 픽셀아트 생성
    pixel_img = pixellab_generate(
        prompt, width=api_size, height=api_size,
        remove_bg=transparent, style_ref=style_ref)

    # 2. 로컬: 인게임 팔레트 + 그리드 변환
    grid = to_palette_grid(pixel_img, cols, rows)

    # 3. 로컬: 셀 보드 렌더링
    board = render_board(grid, cell_size=cell_size, gap=gap,
                        corner=corner, transparent=transparent)

    # 저장
    tag = name or prompt.replace(" ", "_")[:30]
    pixel_img.save(OUTPUT_DIR / f"{tag}_api.png")
    board.save(OUTPUT_DIR / f"{tag}_board.png")
    Image.fromarray(grid).save(OUTPUT_DIR / f"{tag}_flat.png")

    with open(OUTPUT_DIR / f"{tag}_grid.json", "w") as f:
        json.dump({"cols": cols, "rows": rows, "prompt": prompt,
                   "grid": grid.tolist()}, f)

    print(f"[Pipeline] Board: {OUTPUT_DIR / f'{tag}_board.png'} ({board.size})")
    return {"board": board, "grid": grid, "api_img": pixel_img}


def batch_generate(spec_file: str):
    """배치 생성."""
    with open(spec_file, encoding="utf-8") as f:
        spec = json.load(f)
    defaults = spec.get("defaults", {})
    for item in spec["items"]:
        cfg = {**defaults, **item}
        name = cfg.pop("name", None)
        prompt = cfg.pop("prompt")
        generate(prompt=prompt, name=name, **cfg)


def main():
    p = argparse.ArgumentParser(description="PixelLab + Cell Board Pipeline")
    p.add_argument("--prompt", "-p", type=str, help="Image description")
    p.add_argument("--cols", type=int, default=50, help="Grid columns")
    p.add_argument("--rows", type=int, default=50, help="Grid rows")
    p.add_argument("--cell-size", type=int, default=24, help="Cell pixel size")
    p.add_argument("--gap", type=int, default=2, help="Cell gap")
    p.add_argument("--corner", type=int, default=3, help="Corner radius")
    p.add_argument("--style-ref", type=str, default=None, help="Style reference image")
    p.add_argument("--transparent", action="store_true", help="Transparent BG")
    p.add_argument("--api-size", type=int, default=128, help="API generation size")
    p.add_argument("--name", type=str, default=None, help="Output name")
    p.add_argument("--batch", type=str, default=None, help="Batch spec JSON")

    args = p.parse_args()
    if args.batch:
        batch_generate(args.batch)
    elif args.prompt:
        generate(prompt=args.prompt, cols=args.cols, rows=args.rows,
                 cell_size=args.cell_size, gap=args.gap, corner=args.corner,
                 style_ref=args.style_ref, transparent=args.transparent,
                 api_size=args.api_size, name=args.name)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
