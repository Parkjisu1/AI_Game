"""
학습 데이터 준비 — pixelflow 보드 이미지를 LoRA 학습용으로 변환.
1) 이미지를 512x512로 리사이즈
2) 자동 캡션 생성 (색상 분석 기반)
"""

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image

SRC_DIR = Path("E:/AI/virtual_player/data/journal/games/pixelflow/level_designs_verified/boards")
DST_DIR = Path("E:/AI/tools/pixelforge/train_data")
DST_DIR.mkdir(exist_ok=True)

# 인게임 29색 팔레트
PALETTE_29 = {
    1: ("pink", (252, 106, 175)),
    2: ("cyan", (80, 232, 246)),
    3: ("purple", (137, 80, 248)),
    4: ("yellow", (254, 213, 85)),
    5: ("lime", (115, 254, 102)),
    6: ("orange", (253, 161, 76)),
    7: ("white", (255, 255, 255)),
    8: ("black", (65, 65, 65)),
    9: ("sky blue", (110, 168, 250)),
    10: ("green", (57, 174, 46)),
    11: ("red", (252, 94, 94)),
    12: ("blue", (50, 107, 248)),
    13: ("teal", (58, 165, 139)),
    14: ("lavender", (231, 167, 250)),
    15: ("light blue", (183, 199, 251)),
    16: ("brown", (106, 74, 48)),
    17: ("peach", (254, 227, 169)),
    18: ("light pink", (253, 183, 193)),
    19: ("wine", (158, 61, 94)),
    20: ("light green", (167, 221, 148)),
    21: ("dark purple", (89, 46, 126)),
    22: ("coral", (220, 120, 129)),
    23: ("light gray", (217, 217, 231)),
    24: ("gray", (111, 114, 127)),
    25: ("magenta", (252, 56, 165)),
    26: ("light orange", (253, 180, 88)),
    27: ("dark red", (137, 10, 8)),
    28: ("mint", (111, 175, 177)),
    29: ("dark brown", (100, 80, 60)),
}

PAL_ARRAY = np.array([v[1] for v in PALETTE_29.values()], dtype=np.float32)
PAL_NAMES = [v[0] for v in PALETTE_29.values()]


def analyze_colors(img: Image.Image, top_n: int = 5) -> list:
    """이미지의 주요 색상을 29색 팔레트 기준으로 분석."""
    arr = np.array(img.convert("RGB")).reshape(-1, 3).astype(np.float32)
    # 샘플링
    idx = np.random.default_rng(42).choice(len(arr), min(5000, len(arr)), replace=False)
    samples = arr[idx]

    # 각 픽셀 → 가장 가까운 팔레트 색
    dists = np.sum((samples[:, None, :] - PAL_ARRAY[None, :, :]) ** 2, axis=2)
    nearest = np.argmin(dists, axis=1)

    # 빈도 집계
    counts = np.bincount(nearest, minlength=len(PAL_NAMES))
    top_idx = np.argsort(-counts)[:top_n]

    return [PAL_NAMES[i] for i in top_idx if counts[i] > 0]


def generate_caption(img: Image.Image, filename: str) -> str:
    """이미지 분석 기반 자동 캡션."""
    colors = analyze_colors(img, top_n=5)
    color_str = ", ".join(colors[:4])

    # 기본 캡션 구조: 스타일 + 색상
    caption = (f"pixel art cell board, colorful block grid puzzle game level, "
               f"rounded square cells with highlight and shadow, "
               f"vibrant {color_str} colors, casual mobile game style, "
               f"clean uniform grid, pixelflow board")

    return caption


def main():
    images = sorted(SRC_DIR.glob("*.png"))
    print(f"Found {len(images)} images")

    metadata = []
    for i, src in enumerate(images):
        img = Image.open(src)

        # 512x512로 리사이즈
        img_512 = img.convert("RGB").resize((512, 512), Image.LANCZOS)
        dst_img = DST_DIR / src.name
        img_512.save(dst_img)

        # 캡션 생성
        caption = generate_caption(img, src.name)
        caption_path = DST_DIR / f"{src.stem}.txt"
        caption_path.write_text(caption, encoding="utf-8")

        metadata.append({
            "file_name": src.name,
            "text": caption,
        })

        if (i + 1) % 50 == 0:
            print(f"  Processed {i+1}/{len(images)}")

    # metadata.jsonl
    with open(DST_DIR / "metadata.jsonl", "w", encoding="utf-8") as f:
        for m in metadata:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    print(f"\nDone! {len(metadata)} images prepared in {DST_DIR}")
    print(f"Sample caption: {metadata[0]['text'][:100]}...")


if __name__ == "__main__":
    main()
