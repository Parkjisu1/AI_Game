"""
PixelForge — Pixel Art Generator
=================================
PixelLab 스타일 텍스트→픽셀아트 생성 파이프라인.
SD 1.5 + Pixel Art LoRA + 후처리 (color quantization, grid snap).

사용법:
  python pixelforge.py --prompt "a warrior with sword" --size 64
  python pixelforge.py --prompt "forest background" --size 128 --palette 16
  python pixelforge.py --prompt "health bar UI" --size 64 --style-ref style.png
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

# ── 환경 설정 ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
CACHE_DIR = Path("E:/AI/sd_models")
LORA_DIR = SCRIPT_DIR / "loras"
OUTPUT_DIR = SCRIPT_DIR / "output"

os.environ["HF_HOME"] = str(CACHE_DIR / "huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(CACHE_DIR / "hub")
os.environ["TORCH_HOME"] = str(CACHE_DIR / "torch")

OUTPUT_DIR.mkdir(exist_ok=True)
LORA_DIR.mkdir(exist_ok=True)


# ═══════════════════════════════════════════════════════════
#  1. POST-PROCESSING: 핵심 — 깨끗한 픽셀아트 보장
# ═══════════════════════════════════════════════════════════

# 인게임 29색 팔레트 (pixelflow 실제 데이터 기반)
PALETTE_29 = [
    (252, 106, 175),  # 1  핑크
    (80, 232, 246),   # 2  시안
    (137, 80, 248),   # 3  보라
    (254, 213, 85),   # 4  노랑
    (115, 254, 102),  # 5  라임
    (253, 161, 76),   # 6  주황
    (255, 255, 255),  # 7  흰
    (65, 65, 65),     # 8  검정
    (110, 168, 250),  # 9  하늘
    (57, 174, 46),    # 10 초록
    (252, 94, 94),    # 11 빨강
    (50, 107, 248),   # 12 파랑
    (58, 165, 139),   # 13 청록
    (231, 167, 250),  # 14 연보라
    (183, 199, 251),  # 15 연파랑
    (106, 74, 48),    # 16 갈색
    (254, 227, 169),  # 17 살구
    (253, 183, 193),  # 18 연분홍
    (158, 61, 94),    # 19 와인
    (167, 221, 148),  # 20 연초록
    (89, 46, 126),    # 21 진보라
    (220, 120, 129),  # 22 코랄
    (217, 217, 231),  # 23 연회색
    (111, 114, 127),  # 24 회색
    (252, 56, 165),   # 25 마젠타
    (253, 180, 88),   # 26 연주황
    (137, 10, 8),     # 27 진빨강
    (111, 175, 177),  # 28 민트
    (100, 80, 60),    # 29 암갈색
]

FIXED_PALETTES = {
    "pixelflow": PALETTE_29,  # 인게임 실제 팔레트
    "vivid": [                # 핵심 원색 12종
        (252, 94, 94), (253, 161, 76), (254, 213, 85),
        (57, 174, 46), (50, 107, 248), (255, 255, 255),
        (65, 65, 65), (252, 106, 175), (137, 80, 248),
        (80, 232, 246), (106, 74, 48), (217, 217, 231),
    ],
}


def quantize_colors(img: Image.Image, n_colors: int = 16,
                    fixed_palette: str = None) -> Image.Image:
    """색상 양자화 — 고정 팔레트 또는 K-means.

    fixed_palette: 'vivid', 'warm', 'cool' 중 선택하면 해당 팔레트 강제 적용.
    """
    arr = np.array(img)
    h, w, c = arr.shape
    pixels = arr.reshape(-1, c).astype(np.float32)

    if fixed_palette and fixed_palette in FIXED_PALETTES:
        # 고정 팔레트: 각 픽셀을 가장 가까운 팔레트 색상으로
        pal = np.array(FIXED_PALETTES[fixed_palette], dtype=np.float32)
        result = np.zeros_like(pixels, dtype=np.uint8)
        chunk = 10000
        for i in range(0, len(pixels), chunk):
            p = pixels[i:i+chunk]
            dists = np.sum((p[:, None, :] - pal[None, :, :]) ** 2, axis=2)
            nearest = np.argmin(dists, axis=1)
            result[i:i+chunk] = pal[nearest].astype(np.uint8)
        return Image.fromarray(result.reshape(h, w, c))

    # K-means fallback
    from sklearn.cluster import KMeans
    kmeans = KMeans(n_clusters=n_colors, n_init=3, max_iter=100, random_state=42)
    kmeans.fit(pixels)
    centers = kmeans.cluster_centers_.astype(np.uint8)
    labels = kmeans.labels_

    quantized = centers[labels].reshape(h, w, c)
    return Image.fromarray(quantized)


def snap_to_grid(img: Image.Image, pixel_size: int) -> Image.Image:
    """Grid snapping — 모든 픽셀을 균일한 크기로 정렬.

    1. 이미지를 pixel_size 블록으로 나눔
    2. 각 블록 내 가장 빈번한 색상으로 채움
    3. 결과: 깨끗한 픽셀 그리드
    """
    arr = np.array(img)
    h, w, c = arr.shape

    # 블록 단위로 나누기
    bh = h // pixel_size
    bw = w // pixel_size
    result = np.zeros((bh, bw, c), dtype=np.uint8)

    for by in range(bh):
        for bx in range(bw):
            block = arr[by*pixel_size:(by+1)*pixel_size,
                        bx*pixel_size:(bx+1)*pixel_size]
            # 블록 내 최빈 색상 (mode)
            pixels = block.reshape(-1, c)
            # 빠른 mode: 각 색상을 정수로 변환 후 bincount
            keys = pixels[:, 0].astype(np.uint32) * 65536 + \
                   pixels[:, 1].astype(np.uint32) * 256 + \
                   pixels[:, 2].astype(np.uint32)
            counts = np.bincount(keys)
            dominant = counts.argmax()
            r = (dominant >> 16) & 0xFF
            g = (dominant >> 8) & 0xFF
            b = dominant & 0xFF
            result[by, bx] = [r, g, b]

    return Image.fromarray(result)


def upscale_nearest(img: Image.Image, scale: int = 8) -> Image.Image:
    """Nearest-neighbor 업스케일 — 블러 없이 확대."""
    w, h = img.size
    return img.resize((w * scale, h * scale), Image.NEAREST)


def remove_background(img: Image.Image) -> Image.Image:
    """배경 제거 (rembg 사용, 없으면 단색 배경 제거 fallback)."""
    try:
        from rembg import remove
        return remove(img)
    except ImportError:
        # Fallback: 코너 색상 기반 단순 제거
        arr = np.array(img.convert("RGBA"))
        bg_color = arr[0, 0, :3]  # 좌상단 = 배경색 추정
        tolerance = 30
        diff = np.abs(arr[:, :, :3].astype(int) - bg_color.astype(int))
        mask = np.all(diff < tolerance, axis=2)
        arr[mask, 3] = 0  # 투명 처리
        return Image.fromarray(arr)


def apply_palette(img: Image.Image, palette: list) -> Image.Image:
    """강제 팔레트 적용 — 각 픽셀을 가장 가까운 팔레트 색상으로."""
    if not palette:
        return img
    arr = np.array(img)
    h, w, c = arr.shape
    pal = np.array(palette, dtype=np.float32)  # (N, 3)
    pixels = arr[:, :, :3].reshape(-1, 3).astype(np.float32)

    # 각 픽셀에서 가장 가까운 팔레트 색상 찾기 (유클리드 거리)
    # 메모리 효율: 청크 처리
    result = np.zeros_like(pixels, dtype=np.uint8)
    chunk = 10000
    for i in range(0, len(pixels), chunk):
        p = pixels[i:i+chunk]
        dists = np.sum((p[:, None, :] - pal[None, :, :]) ** 2, axis=2)
        nearest = np.argmin(dists, axis=1)
        result[i:i+chunk] = pal[nearest].astype(np.uint8)

    out = result.reshape(h, w, 3)
    # 알파 채널 보존
    if c == 4:
        out = np.concatenate([out, arr[:, :, 3:]], axis=2)
    return Image.fromarray(out)


def extract_main_object(img: Image.Image) -> Image.Image:
    """SD 출력에서 가장 큰 단일 오브젝트만 크롭.

    Connected Component 방식: 배경 제거 → 가장 큰 연결 영역 → 크롭.
    여러 오브젝트가 생성되어도 가장 큰 것만 추출.
    """
    from scipy import ndimage

    arr = np.array(img.convert("RGB"))
    h, w, _ = arr.shape

    # 배경색 추정: 4 코너 10x10 영역 평균
    margin = 10
    corners = [arr[:margin, :margin], arr[:margin, -margin:],
               arr[-margin:, :margin], arr[-margin:, -margin:]]
    bg_color = np.mean(np.concatenate(
        [c.reshape(-1, 3) for c in corners], axis=0), axis=0)

    # 전경 마스크 (배경과 다른 픽셀)
    diff = np.sqrt(np.sum((arr.astype(float) - bg_color) ** 2, axis=2))
    fg_mask = diff > 35

    if not fg_mask.any():
        return img

    # Connected Components — 가장 큰 영역만 선택
    labeled, n_features = ndimage.label(fg_mask)
    if n_features > 1:
        sizes = ndimage.sum(fg_mask, labeled, range(1, n_features + 1))
        largest_id = np.argmax(sizes) + 1
        fg_mask = labeled == largest_id

    # 바운딩 박스
    row_mask = np.any(fg_mask, axis=1)
    col_mask = np.any(fg_mask, axis=0)
    y_min, y_max = np.where(row_mask)[0][[0, -1]]
    x_min, x_max = np.where(col_mask)[0][[0, -1]]

    # 패딩 (오브젝트 주변 여백)
    pad = max(5, min(h, w) // 15)
    y_min = max(0, y_min - pad)
    y_max = min(h - 1, y_max + pad)
    x_min = max(0, x_min - pad)
    x_max = min(w - 1, x_max + pad)

    # 정사각형으로 맞추기
    obj_h = y_max - y_min + 1
    obj_w = x_max - x_min + 1
    side = max(obj_h, obj_w)
    cx = (x_min + x_max) // 2
    cy = (y_min + y_max) // 2
    half = side // 2

    crop_x1 = max(0, cx - half)
    crop_y1 = max(0, cy - half)
    crop_x2 = min(w, crop_x1 + side)
    crop_y2 = min(h, crop_y1 + side)

    return img.crop((crop_x1, crop_y1, crop_x2, crop_y2))


def postprocess_pixel_art(img: Image.Image, target_size: int = 64,
                          n_colors: int = 16, palette: list = None,
                          remove_bg: bool = False) -> dict:
    """전체 후처리 파이프라인.

    Returns:
        dict with 'raw' (SD 원본), 'pixel' (후처리), 'preview' (확대)
    """
    raw = img.copy()

    # 0) 배경 제거 모드: 메인 오브젝트 크롭
    if remove_bg:
        img = extract_main_object(img)

    # ── 핵심: 완벽한 픽셀 그리드 보장 ──
    # 크롭 후 크기가 달라질 수 있으므로, 정확한 배수로 리사이즈
    grid_res = target_size * 8  # 예: 64*8=512
    img = img.resize((grid_res, grid_res), Image.LANCZOS)
    pixel_size = 8  # 고정 블록 크기

    # 1) 인게임 29색 팔레트로 양자화 (K-means 대신 실제 게임 색상 강제)
    quantized_full = quantize_colors(img, n_colors, fixed_palette="pixelflow")

    # 2) Grid snap: 블록 단위로 최빈 색상 추출 → 완벽 균일 픽셀
    snapped = snap_to_grid(quantized_full, pixel_size)

    # 3) 추가 팔레트 (사용자 지정, 선택)
    if palette:
        snapped = apply_palette(snapped, palette)

    # 4) 배경 제거 (선택)
    if remove_bg:
        snapped = remove_background(snapped)

    # 5) 미리보기용 확대 (nearest neighbor — 블러 없음)
    scale = max(1, 512 // target_size)
    preview = upscale_nearest(snapped, scale)

    return {
        "raw": raw,
        "pixel": snapped,
        "preview": preview,
    }


# ═══════════════════════════════════════════════════════════
#  2. SD PIPELINE: 이미지 생성
# ═══════════════════════════════════════════════════════════

_pipe_cache = {}


def load_pipeline(mode="txt2img", model_id="runwayml/stable-diffusion-v1-5",
                  lora_path=None, ip_adapter=False):
    """SD 파이프라인 로드 (캐시)."""
    import torch

    cache_key = f"{model_id}:{mode}:{lora_path}:{ip_adapter}"
    if cache_key in _pipe_cache:
        return _pipe_cache[cache_key]

    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32

    print(f"[PixelForge] Loading {mode} pipeline... ({model_id})")

    if mode == "img2img":
        from diffusers import AutoPipelineForImage2Image
        pipe = AutoPipelineForImage2Image.from_pretrained(
            model_id, torch_dtype=dtype, cache_dir=str(CACHE_DIR),
            safety_checker=None, requires_safety_checker=False)
    else:
        from diffusers import AutoPipelineForText2Image
        pipe = AutoPipelineForText2Image.from_pretrained(
            model_id, torch_dtype=dtype, cache_dir=str(CACHE_DIR),
            safety_checker=None, requires_safety_checker=False)

    pipe = pipe.to(device)
    if device == "cuda" and not ip_adapter:
        pipe.enable_attention_slicing()

    # LoRA 로드
    if lora_path:
        lora_file = Path(lora_path)
        if lora_file.exists():
            print(f"[PixelForge] Loading LoRA: {lora_file.name}")
            pipe.load_lora_weights(str(lora_file.parent),
                                  weight_name=lora_file.name)
        else:
            print(f"[PixelForge] Loading LoRA from HF: {lora_path}")
            pipe.load_lora_weights(lora_path)

    # IP-Adapter 로드 (스타일 참조 생성용)
    if ip_adapter:
        ip_model_dir = CACHE_DIR / "ip_adapter"
        ip_weight = ip_model_dir / "models" / "ip-adapter-plus_sd15.safetensors"
        if ip_weight.exists():
            print(f"[PixelForge] Loading IP-Adapter Plus...")
            pipe.load_ip_adapter(
                str(ip_model_dir / "models"),
                subfolder="",
                weight_name="ip-adapter-plus_sd15.safetensors")
            print(f"[PixelForge] IP-Adapter loaded")
        else:
            print(f"[PixelForge] WARNING: IP-Adapter weights not found at {ip_weight}")

    _pipe_cache[cache_key] = pipe
    print(f"[PixelForge] Pipeline ready on {device}")
    return pipe


def generate_pixel_art(prompt: str, negative_prompt: str = "",
                       size: int = 64, n_colors: int = 16,
                       palette: list = None, remove_bg: bool = False,
                       steps: int = 25, guidance: float = 7.5,
                       seed: int = -1, lora_path: str = None,
                       style_ref: str = None, style_strength: float = 0.6,
                       count: int = 1) -> list:
    """메인 생성 함수.

    Args:
        prompt: 생성할 이미지 설명
        negative_prompt: 제외할 요소
        size: 최종 픽셀아트 크기 (32, 64, 128 등)
        n_colors: 팔레트 색상 수
        palette: 강제 팔레트 [(r,g,b), ...]
        remove_bg: 배경 제거
        steps: 추론 스텝 수
        guidance: CFG 스케일
        seed: 시드 (-1 = 랜덤)
        lora_path: LoRA 파일 또는 HF 경로
        style_ref: 스타일 참조 이미지 경로 (img2img)
        style_strength: 스타일 참조 강도 (0~1)
        count: 생성할 이미지 수

    Returns:
        list of dict: 각각 { raw, pixel, preview, seed, prompt }
    """
    import torch

    # 픽셀아트 프롬프트 강화 (LoRA 트리거 워드 포함)
    bg_prompt = (", solo, alone, one single object, centered on pure white background, "
                 "isolated, nothing else") if remove_bg else ""
    bg_negative = ("complex background, scenery, landscape, "
                   "multiple, many, two, three, group, collection, crowd, "
                   "pattern, repeating, tileable, sprite sheet, collage, grid, ") if remove_bg else ""
    pixel_prompt = (f"Pixel Art, PIXARFK, {prompt}{bg_prompt}, "
                    f"modern casual game style, cute, colorful, "
                    f"clean crisp pixels, vibrant, high quality")
    pixel_negative = (f"blurry, smooth, photorealistic, 3d render, gradient, "
                      f"anti-aliased, watermark, text, signature, "
                      f"retro, old school, NES, SNES, 8-bit, dithering, dark, gritty, "
                      f"{bg_negative}low quality, jpeg artifacts, {negative_prompt}")

    # SD 생성 해상도: 항상 512 (SD 1.5 최적)
    # 단일 오브젝트가 여러 개 나오는 문제는 후처리에서 중앙 크롭으로 해결
    gen_size = 512

    # 파이프라인 선택
    use_ip_adapter = style_ref and Path(style_ref).exists()
    style_img = None

    if use_ip_adapter:
        # IP-Adapter: txt2img + 스타일 이미지 조건부 생성
        pipe = load_pipeline("txt2img", lora_path=lora_path, ip_adapter=True)
        style_img = Image.open(style_ref).convert("RGB").resize((256, 256), Image.LANCZOS)
        pipe.set_ip_adapter_scale(style_strength)
        print(f"[PixelForge] Style ref: {style_ref} (strength={style_strength})")
    else:
        pipe = load_pipeline("txt2img", lora_path=lora_path)

    results = []
    for i in range(count):
        actual_seed = seed if seed >= 0 else int(time.time() * 1000) % (2**32) + i
        generator = torch.Generator(device="cuda" if torch.cuda.is_available() else "cpu")
        generator.manual_seed(actual_seed)

        print(f"[PixelForge] Generating {i+1}/{count} (seed={actual_seed}, "
              f"gen={gen_size}x{gen_size} → pixel={size}x{size})...")

        t0 = time.time()

        kwargs = dict(
            prompt=pixel_prompt,
            negative_prompt=pixel_negative,
            width=gen_size,
            height=gen_size,
            num_inference_steps=steps,
            guidance_scale=guidance,
            generator=generator,
        )

        # IP-Adapter 스타일 이미지 전달
        if use_ip_adapter and style_img is not None:
            kwargs["ip_adapter_image"] = style_img

        sd_img = pipe(**kwargs).images[0]

        elapsed = time.time() - t0
        print(f"[PixelForge] SD done in {elapsed:.1f}s")

        # 후처리
        result = postprocess_pixel_art(
            sd_img, target_size=size, n_colors=n_colors,
            palette=palette, remove_bg=remove_bg)
        result["seed"] = actual_seed
        result["prompt"] = prompt
        result["elapsed"] = elapsed
        results.append(result)

    return results


def save_results(results: list, prefix: str = "pixelforge"):
    """결과 저장."""
    saved = []
    for i, r in enumerate(results):
        seed = r["seed"]
        tag = f"{prefix}_{seed}"

        # 픽셀아트 (실제 크기)
        pixel_path = OUTPUT_DIR / f"{tag}_pixel.png"
        r["pixel"].save(pixel_path)

        # 미리보기 (확대)
        preview_path = OUTPUT_DIR / f"{tag}_preview.png"
        r["preview"].save(preview_path)

        # SD 원본
        raw_path = OUTPUT_DIR / f"{tag}_raw.png"
        r["raw"].save(raw_path)

        saved.append({
            "pixel": str(pixel_path),
            "preview": str(preview_path),
            "raw": str(raw_path),
            "seed": seed,
            "prompt": r["prompt"],
            "elapsed": r["elapsed"],
        })
        print(f"[PixelForge] Saved: {pixel_path.name} ({r['pixel'].size[0]}x{r['pixel'].size[1]})")

    # 메타데이터
    meta_path = OUTPUT_DIR / f"{prefix}_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(saved, f, indent=2, ensure_ascii=False)
    print(f"[PixelForge] Metadata: {meta_path}")

    return saved


# ═══════════════════════════════════════════════════════════
#  3. BATCH: 여러 에셋 일괄 생성
# ═══════════════════════════════════════════════════════════

def batch_generate(spec_file: str):
    """JSON 스펙 파일로 일괄 생성.

    spec.json 예시:
    {
      "defaults": { "size": 64, "n_colors": 16, "steps": 25 },
      "items": [
        { "prompt": "warrior with sword", "name": "warrior" },
        { "prompt": "healing potion bottle", "name": "potion", "size": 32 },
        { "prompt": "forest tileset ground", "name": "forest_tile", "size": 32, "count": 4 }
      ]
    }
    """
    with open(spec_file, encoding="utf-8") as f:
        spec = json.load(f)

    defaults = spec.get("defaults", {})
    all_results = []

    for item in spec["items"]:
        cfg = {**defaults, **item}
        name = cfg.pop("name", "item")
        prompt = cfg.pop("prompt")
        count = cfg.pop("count", 1)

        results = generate_pixel_art(prompt=prompt, count=count, **cfg)
        save_results(results, prefix=name)
        all_results.extend(results)

    print(f"\n[PixelForge] Batch complete: {len(all_results)} images generated")
    return all_results


# ═══════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="PixelForge — AI Pixel Art Generator")
    parser.add_argument("--prompt", "-p", type=str, help="Image description")
    parser.add_argument("--negative", "-n", type=str, default="", help="Negative prompt")
    parser.add_argument("--size", "-s", type=int, default=64, help="Pixel art size (32/64/128)")
    parser.add_argument("--colors", "-c", type=int, default=16, help="Palette color count")
    parser.add_argument("--remove-bg", action="store_true", help="Remove background")
    parser.add_argument("--steps", type=int, default=25, help="Inference steps")
    parser.add_argument("--guidance", "-g", type=float, default=7.5, help="CFG scale")
    parser.add_argument("--seed", type=int, default=-1, help="Seed (-1=random)")
    parser.add_argument("--lora", type=str, default=None, help="LoRA path or HF ID")
    parser.add_argument("--style-ref", type=str, default=None, help="Style reference image")
    parser.add_argument("--style-strength", type=float, default=0.6, help="Style strength 0~1")
    parser.add_argument("--count", type=int, default=1, help="Number of images")
    parser.add_argument("--name", type=str, default="pixelforge", help="Output prefix")
    parser.add_argument("--batch", type=str, default=None, help="Batch spec JSON file")
    parser.add_argument("--palette-json", type=str, default=None,
                        help="Palette JSON file: [[r,g,b], ...]")

    # 후처리만 (SD 없이)
    parser.add_argument("--postprocess", type=str, default=None,
                        help="Post-process existing image (skip SD)")

    args = parser.parse_args()

    # 배치 모드
    if args.batch:
        batch_generate(args.batch)
        return

    # 팔레트 로드
    palette = None
    if args.palette_json:
        with open(args.palette_json, encoding="utf-8") as f:
            palette = json.load(f)

    # 후처리만 모드
    if args.postprocess:
        img = Image.open(args.postprocess).convert("RGB")
        result = postprocess_pixel_art(
            img, target_size=args.size, n_colors=args.colors,
            palette=palette, remove_bg=args.remove_bg)
        result["seed"] = 0
        result["prompt"] = "postprocess"
        result["elapsed"] = 0
        save_results([result], prefix=args.name)
        return

    # 생성 모드
    if not args.prompt:
        parser.print_help()
        print("\nError: --prompt is required")
        return

    results = generate_pixel_art(
        prompt=args.prompt,
        negative_prompt=args.negative,
        size=args.size,
        n_colors=args.colors,
        palette=palette,
        remove_bg=args.remove_bg,
        steps=args.steps,
        guidance=args.guidance,
        seed=args.seed,
        lora_path=args.lora,
        style_ref=args.style_ref,
        style_strength=args.style_strength,
        count=args.count,
    )
    save_results(results, prefix=args.name)


if __name__ == "__main__":
    main()
