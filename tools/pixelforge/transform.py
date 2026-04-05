"""
PixelForge Transform — 레퍼런스 이미지 → 셀 보드 변형
=====================================================
레퍼런스 이미지를 SD img2img로 변형 후, 인게임 팔레트 + 셀 보드 렌더링.

사용법:
  # 기본: 레퍼런스 이미지를 25x25 셀 보드로 변환
  python transform.py ref.png --prompt "cute cat" --cols 25 --rows 25

  # 사이즈 변경
  python transform.py ref.png --prompt "forest" --cols 40 --rows 50

  # SD 없이 레퍼런스만 셀 보드로 변환
  python transform.py ref.png --cols 30 --rows 30 --no-sd

  # 투명 배경
  python transform.py ref.png --prompt "mushroom" --cols 25 --rows 25 --transparent
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path("E:/AI/sd_models")
OUTPUT_DIR = SCRIPT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

os.environ["HF_HOME"] = str(CACHE_DIR / "huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(CACHE_DIR / "hub")
os.environ["TORCH_HOME"] = str(CACHE_DIR / "torch")

# ── 인게임 팔레트 ──
# 핵심 15색 (유사색 병합 — 회색/갈색 계열 줄임, 선명한 색상 위주)
PALETTE_CORE = np.array([
    [252, 94, 94],    # 빨강
    [253, 161, 76],   # 주황
    [254, 213, 85],   # 노랑
    [115, 254, 102],  # 라임
    [57, 174, 46],    # 초록
    [80, 232, 246],   # 시안
    [50, 107, 248],   # 파랑
    [137, 80, 248],   # 보라
    [252, 106, 175],  # 핑크
    [252, 56, 165],   # 마젠타
    [255, 255, 255],  # 흰
    [65, 65, 65],     # 검정
    [111, 114, 127],  # 회색
    [106, 74, 48],    # 갈색
    [254, 227, 169],  # 살구
], dtype=np.float32)

# 전체 29색 (필요시 사용)
PALETTE_29 = np.array([
    [252, 106, 175], [80, 232, 246],  [137, 80, 248],
    [254, 213, 85],  [115, 254, 102], [253, 161, 76],
    [255, 255, 255], [65, 65, 65],    [110, 168, 250],
    [57, 174, 46],   [252, 94, 94],   [50, 107, 248],
    [58, 165, 139],  [231, 167, 250], [183, 199, 251],
    [106, 74, 48],   [254, 227, 169], [253, 183, 193],
    [158, 61, 94],   [167, 221, 148], [89, 46, 126],
    [220, 120, 129], [217, 217, 231], [111, 114, 127],
    [252, 56, 165],  [253, 180, 88],  [137, 10, 8],
    [111, 175, 177], [100, 80, 60],
], dtype=np.float32)


def clean_grid(grid: np.ndarray) -> np.ndarray:
    """그리드 클린업 — 고립 셀 제거 + 노이즈 정리.

    주변 4셀과 모두 다른 색상인 셀 = 노이즈 → 주변 최빈 색으로 교체.
    """
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

            if not neighbors:
                continue

            # 현재 셀이 이웃 중 아무와도 같지 않으면 = 고립 셀
            if color not in neighbors:
                # 이웃 중 가장 빈번한 색으로 교체
                from collections import Counter
                most_common = Counter(neighbors).most_common(1)[0][0]
                result[r, c] = most_common

    return result


def image_to_grid(img: Image.Image, cols: int, rows: int,
                  use_full_palette: bool = False) -> np.ndarray:
    """이미지 → (rows, cols, 3) 그리드.

    핵심 15색 팔레트로 매핑 (유사색 병합, 노이즈 감소).
    use_full_palette=True면 29색 전체 사용.
    """
    palette = PALETTE_29 if use_full_palette else PALETTE_CORE

    # 목표 크기로 리사이즈 (각 셀 = 1px)
    # NEAREST: 경계 블렌딩 없이 칼같은 엣지 유지
    small = img.convert("RGB").resize((cols, rows), Image.NEAREST)
    arr = np.array(small).astype(np.float32)

    # 각 픽셀을 팔레트에서 가장 가까운 색으로
    grid = np.zeros((rows, cols, 3), dtype=np.uint8)
    for r in range(rows):
        for c in range(cols):
            pixel = arr[r, c]
            dists = np.sum((palette - pixel) ** 2, axis=1)
            grid[r, c] = palette[np.argmin(dists)].astype(np.uint8)

    # 고립 셀 제거 (노이즈 클린업 — 2회 반복)
    grid = clean_grid(grid)
    grid = clean_grid(grid)

    return grid


def find_bg_color(grid: np.ndarray) -> tuple:
    """그리드에서 가장 빈번한 색상."""
    pixels = grid.reshape(-1, 3)
    keys = pixels[:, 0].astype(np.uint32) * 65536 + \
           pixels[:, 1].astype(np.uint32) * 256 + \
           pixels[:, 2].astype(np.uint32)
    counts = np.bincount(keys)
    dominant = counts.argmax()
    return ((dominant >> 16) & 0xFF, (dominant >> 8) & 0xFF, dominant & 0xFF)


def render_board(grid: np.ndarray, cell_size: int = 24,
                 gap: int = 2, corner_radius: int = 3,
                 bg_color: tuple = (42, 42, 80),
                 transparent: bool = False) -> Image.Image:
    """셀 그리드 → 둥근 블록 보드 렌더링 (레퍼런스 스타일)."""
    rows, cols, _ = grid.shape
    img_w = cols * (cell_size + gap) + gap
    img_h = rows * (cell_size + gap) + gap

    if transparent:
        img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
        grid_bg = find_bg_color(grid)
    else:
        img = Image.new("RGBA", (img_w, img_h), bg_color + (255,))
        grid_bg = None

    draw = ImageDraw.Draw(img)

    for r in range(rows):
        for c in range(cols):
            color = tuple(int(v) for v in grid[r, c])
            x = gap + c * (cell_size + gap)
            y = gap + r * (cell_size + gap)

            # 투명 모드: 배경색 셀 스킵
            if grid_bg is not None:
                diff = sum(abs(a - b) for a, b in zip(color, grid_bg))
                if diff < 60:
                    continue

            # 그림자
            shadow_color = tuple(max(0, v - 50) for v in color) + (255,)
            draw.rounded_rectangle(
                [x + 1, y + 1, x + cell_size, y + cell_size],
                radius=corner_radius, fill=shadow_color)

            # 메인 블록
            draw.rounded_rectangle(
                [x, y, x + cell_size - 1, y + cell_size - 1],
                radius=corner_radius, fill=color + (255,))

            # 하이라이트
            hl = tuple(min(255, v + 45) for v in color) + (150,)
            hl_size = max(3, cell_size // 4)
            draw.rounded_rectangle(
                [x + 2, y + 2, x + hl_size + 2, y + hl_size + 2],
                radius=max(1, corner_radius // 2), fill=hl)

    return img


def extract_canny(img: Image.Image, low: int = 50, high: int = 150) -> Image.Image:
    """Canny 엣지 추출 — 형태 윤곽선."""
    import cv2
    arr = np.array(img.convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, low, high)
    return Image.fromarray(edges).convert("RGB")


def sd_transform(ref_img: Image.Image, prompt: str,
                 strength: float = 0.55, steps: int = 28,
                 guidance: float = 8.0, seed: int = -1,
                 lora_path: str = None,
                 cn_scale: float = 0.8) -> Image.Image:
    """SD img2img 변형. cn_scale>0이면 ControlNet, 0이면 순수 img2img."""
    import torch
    from diffusers import UniPCMultistepScheduler

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    merged_unet = SCRIPT_DIR / "loras" / "pixelflow_merged"
    use_merged = lora_path and "pixelflow" in str(lora_path) and merged_unet.exists()

    ref_512 = ref_img.convert("RGB").resize((512, 512), Image.LANCZOS)

    if cn_scale > 0:
        # ── ControlNet 모드 (구조 유지) ──
        from diffusers import (StableDiffusionControlNetImg2ImgPipeline,
                               ControlNetModel)
        print(f"[Transform] Loading ControlNet (cn_scale={cn_scale})...")
        controlnet = ControlNetModel.from_pretrained(
            "lllyasviel/sd-controlnet-canny",
            torch_dtype=dtype, cache_dir=str(CACHE_DIR))

        if use_merged:
            from diffusers import UNet2DConditionModel
            unet = UNet2DConditionModel.from_pretrained(
                str(merged_unet), torch_dtype=dtype)
            pipe = StableDiffusionControlNetImg2ImgPipeline.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                unet=unet, controlnet=controlnet,
                torch_dtype=dtype, cache_dir=str(CACHE_DIR),
                safety_checker=None, requires_safety_checker=False)
        else:
            pipe = StableDiffusionControlNetImg2ImgPipeline.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                controlnet=controlnet,
                torch_dtype=dtype, cache_dir=str(CACHE_DIR),
                safety_checker=None, requires_safety_checker=False)

        canny_img = extract_canny(ref_512, low=30, high=120)
        extra_kwargs = {"control_image": canny_img,
                        "controlnet_conditioning_scale": cn_scale}
    else:
        # ── 순수 img2img 모드 (형태 변경) ──
        from diffusers import AutoPipelineForImage2Image
        print(f"[Transform] Loading img2img (no ControlNet, reshape mode)...")

        if use_merged:
            from diffusers import UNet2DConditionModel
            unet = UNet2DConditionModel.from_pretrained(
                str(merged_unet), torch_dtype=dtype)
            pipe = AutoPipelineForImage2Image.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                unet=unet, torch_dtype=dtype, cache_dir=str(CACHE_DIR),
                safety_checker=None, requires_safety_checker=False)
        else:
            pipe = AutoPipelineForImage2Image.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                torch_dtype=dtype, cache_dir=str(CACHE_DIR),
                safety_checker=None, requires_safety_checker=False)

        extra_kwargs = {}

    pipe.scheduler = UniPCMultistepScheduler.from_config(pipe.scheduler.config)
    if device == "cuda":
        pipe.enable_model_cpu_offload()
        pipe.enable_attention_slicing()

    # 외부 LoRA
    if lora_path and not use_merged:
        lora_p = Path(lora_path)
        if lora_p.exists() and lora_p.suffix == ".safetensors":
            pipe.load_lora_weights(str(lora_p.parent), weight_name=lora_p.name)

    actual_seed = seed if seed >= 0 else int(time.time() * 1000) % (2**32)
    generator = torch.Generator(device=device).manual_seed(actual_seed)

    pixel_prompt = (f"Pixel Art, PIXARFK, {prompt}, "
                    f"modern casual game style, cute, colorful, "
                    f"clean crisp pixels, vibrant, high quality")
    pixel_negative = ("blurry, photorealistic, 3d render, gradient, "
                      "dark, gritty, low quality, jpeg artifacts, noise")

    print(f"[Transform] Generating (seed={actual_seed}, strength={strength})...")
    t0 = time.time()
    result = pipe(
        prompt=pixel_prompt,
        negative_prompt=pixel_negative,
        image=ref_512,
        strength=strength,
        num_inference_steps=steps,
        guidance_scale=guidance,
        generator=generator,
        **extra_kwargs,
    ).images[0]
    elapsed = time.time() - t0
    mode_str = "ControlNet" if cn_scale > 0 else "img2img"
    print(f"[Transform] {mode_str} done in {elapsed:.1f}s")

    return result, actual_seed


def transform(ref_path: str, prompt: str = None,
              cols: int = 25, rows: int = 25,
              cell_size: int = 24, gap: int = 2, corner: int = 3,
              strength: float = 0.55, steps: int = 28,
              guidance: float = 8.0, seed: int = -1,
              lora_path: str = None,
              transparent: bool = False,
              no_sd: bool = False,
              cn_scale: float = 0.8,
              name: str = None) -> dict:
    """메인 변형 함수.

    Args:
        ref_path: 레퍼런스 이미지 경로
        prompt: 변형 프롬프트 (None이면 레퍼런스만 셀 보드 변환)
        cols/rows: 그리드 크기
        cell_size/gap/corner: 셀 렌더링 옵션
        strength: SD 변형 강도 (0=원본 유지, 1=완전 새로 생성)
        cn_scale: ControlNet 강도 (0=OFF, 0.5~1.5=형태 유지)
        transparent: 투명 배경 PNG
        no_sd: SD 없이 레퍼런스만 셀 보드로 변환
    """
    ref_img = Image.open(ref_path).convert("RGB")

    # 자동 크롭: 테두리/UI 제거 (8% 마진)
    w, h = ref_img.size
    margin = int(min(w, h) * 0.08)
    ref_img = ref_img.crop((margin, margin, w - margin, h - margin))

    print(f"[Transform] Reference: {ref_path} (cropped to {ref_img.size})")
    print(f"[Transform] Grid: {cols}x{rows}, cell={cell_size}px")

    # 변형 모드 자동 선택
    if not no_sd and prompt:
        if cn_scale <= 0:
            # 형태 변경 모드: ControlNet OFF, 높은 strength
            mode = "reshape"
            actual_strength = max(strength, 0.8)
        elif strength <= 0.4:
            # 리컬러 모드: 약한 변형, ControlNet 불필요
            mode = "recolor"
            cn_scale = 0  # ControlNet OFF
            actual_strength = strength
        else:
            # 구조 유지 모드: ControlNet ON
            mode = "structure"
            actual_strength = strength

        print(f"[Transform] Mode: {mode} (strength={actual_strength}, cn_scale={cn_scale})")

        sd_img, actual_seed = sd_transform(
            ref_img, prompt, strength=actual_strength, steps=steps,
            guidance=guidance, seed=seed, lora_path=lora_path,
            cn_scale=cn_scale)
        source = sd_img
    else:
        source = ref_img
        actual_seed = 0

    # 인게임 29색 팔레트 → 셀 그리드
    grid = image_to_grid(source, cols, rows)
    print(f"[Transform] Grid extracted: {grid.shape}")

    # 셀 보드 렌더링
    board = render_board(grid, cell_size=cell_size, gap=gap,
                        corner_radius=corner, transparent=transparent)

    # 저장
    tag = name or Path(ref_path).stem
    seed_tag = f"_s{actual_seed}" if actual_seed else ""

    board_path = OUTPUT_DIR / f"{tag}_{cols}x{rows}{seed_tag}_board.png"
    board.save(board_path)
    print(f"[Transform] Board: {board_path} ({board.size})")

    # flat 버전 (1셀=1px, 정확한 그리드 데이터)
    flat_path = OUTPUT_DIR / f"{tag}_{cols}x{rows}{seed_tag}_flat.png"
    flat = Image.fromarray(grid)
    flat.save(flat_path)

    # SD 변형 원본도 저장
    if not no_sd and prompt:
        raw_path = OUTPUT_DIR / f"{tag}_{cols}x{rows}{seed_tag}_raw.png"
        source.save(raw_path)

    # 그리드 JSON
    grid_path = OUTPUT_DIR / f"{tag}_{cols}x{rows}{seed_tag}_grid.json"
    with open(grid_path, "w") as f:
        json.dump({
            "cols": cols, "rows": rows,
            "seed": actual_seed,
            "prompt": prompt or "",
            "ref": ref_path,
            "grid": grid.tolist(),
        }, f)

    print(f"[Transform] Done!")
    return {"board": board, "grid": grid, "seed": actual_seed}


def main():
    p = argparse.ArgumentParser(description="PixelForge Transform")
    p.add_argument("ref", type=str, help="Reference image path")
    p.add_argument("--prompt", "-p", type=str, default=None, help="Transform prompt")
    p.add_argument("--cols", type=int, default=25, help="Grid columns")
    p.add_argument("--rows", type=int, default=25, help="Grid rows")
    p.add_argument("--cell-size", type=int, default=24, help="Cell pixel size")
    p.add_argument("--gap", type=int, default=2, help="Cell gap")
    p.add_argument("--corner", type=int, default=3, help="Corner radius")
    p.add_argument("--strength", "-s", type=float, default=0.55, help="SD strength 0~1")
    p.add_argument("--steps", type=int, default=28, help="SD steps")
    p.add_argument("--guidance", "-g", type=float, default=8.0, help="CFG scale")
    p.add_argument("--seed", type=int, default=-1, help="Seed")
    p.add_argument("--lora", type=str, default=None, help="LoRA path")
    p.add_argument("--transparent", action="store_true", help="Transparent BG")
    p.add_argument("--no-sd", action="store_true", help="No SD, just convert to board")
    p.add_argument("--cn-scale", type=float, default=1.2, help="ControlNet strength (0.5~1.5)")
    p.add_argument("--name", type=str, default=None, help="Output name")

    args = p.parse_args()
    transform(
        args.ref, prompt=args.prompt,
        cols=args.cols, rows=args.rows,
        cell_size=args.cell_size, gap=args.gap, corner=args.corner,
        strength=args.strength, steps=args.steps,
        guidance=args.guidance, seed=args.seed,
        lora_path=args.lora, transparent=args.transparent,
        no_sd=args.no_sd, cn_scale=args.cn_scale, name=args.name)


if __name__ == "__main__":
    main()
