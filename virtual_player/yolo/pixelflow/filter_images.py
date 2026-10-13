"""
Image Filter Tool v2 (Palette + Grid Heuristic)
===============================================
게임 보드는 고유한 29색 팔레트와 강한 격자 패턴을 가짐.
광고/메뉴/로딩 화면은 일반 사진/그래픽 → 팔레트 매칭 낮음.

지표 2가지:
  1. 팔레트 매칭률 (palette_ratio) — 픽셀 중 29색 팔레트에 가까운 비율
  2. 그리드 강도 (grid_strength)    — FFT autocorrelation peak

판정:
  [game]    palette >= 0.5 AND grid_strength >= 0.03
  [partial] palette >= 0.3 OR grid_strength >= 0.02
  [skip]    그 외 (광고/메뉴)

사용법:
  python filter_images.py
  python filter_images.py --move       # skip 이미지 이동
  python filter_images.py --thresh 0.4 # 임계값 조정
"""
from __future__ import annotations
import argparse
import sys
import shutil
import json
from pathlib import Path

import cv2
import numpy as np

TOOLS_DIR = Path(r"E:\AI\virtual_player\tools")
sys.path.insert(0, str(TOOLS_DIR))

from cell_aware_analyzer import PALETTE_29


# 팔레트를 numpy 배열로
_PAL_RGB = np.array(list(PALETTE_29.values()), dtype=np.float64)


def palette_match_ratio(img_bgr: np.ndarray, max_dist: float = 40.0, sample: int = 2000) -> float:
    """픽셀을 샘플링하여 팔레트와의 최소 거리 평가.

    Returns:
        0~1 값. 팔레트에 가까운 픽셀 비율.
    """
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).reshape(-1, 3).astype(np.float64)
    # 샘플링
    if len(rgb) > sample:
        idx = np.random.RandomState(42).choice(len(rgb), sample, replace=False)
        rgb = rgb[idx]

    # 각 픽셀의 팔레트 최소 거리
    # rgb: (N, 3), _PAL_RGB: (29, 3)
    diff = rgb[:, None, :] - _PAL_RGB[None, :, :]  # (N, 29, 3)
    dists = np.sqrt(np.sum(diff ** 2, axis=2))     # (N, 29)
    min_dists = dists.min(axis=1)                   # (N,)

    return float((min_dists <= max_dist).mean())


def grid_strength(img_bgr: np.ndarray) -> float:
    """이미지의 수평/수직 반복 패턴 강도 (FFT peak).

    Returns:
        0~1 값. 클수록 강한 그리드 패턴.
    """
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float64)
    h, w = gray.shape

    # 보드는 보통 이미지 가운데에 있으므로 중앙 60%만 분석
    y0, y1 = int(h * 0.2), int(h * 0.8)
    x0, x1 = int(w * 0.2), int(w * 0.8)
    region = gray[y0:y1, x0:x1]

    # 수평/수직 프로파일
    col_prof = region.mean(axis=0)
    row_prof = region.mean(axis=1)

    def _peak_strength(profile: np.ndarray) -> float:
        centered = profile - profile.mean()
        if centered.std() < 1e-6:
            return 0.0
        # FFT magnitude
        spec = np.abs(np.fft.rfft(centered))
        if len(spec) < 3:
            return 0.0
        # DC 제거, 셀 피치 범위(10~50 px)의 주파수 대역에서 peak
        n = len(profile)
        k_min = max(1, n // 50)
        k_max = min(len(spec) - 1, n // 10)
        if k_max <= k_min:
            return 0.0
        band = spec[k_min:k_max + 1]
        total = spec[1:].sum()
        if total <= 0:
            return 0.0
        return float(band.max() / total)

    return max(_peak_strength(col_prof), _peak_strength(row_prof))


def score_image(img_bgr: np.ndarray,
                palette_threshold: float = 0.5,
                grid_threshold: float = 0.03) -> dict:
    pal_r = palette_match_ratio(img_bgr)
    grid_s = grid_strength(img_bgr)

    if pal_r >= palette_threshold and grid_s >= grid_threshold:
        category = "game"
    elif pal_r >= palette_threshold * 0.6 or grid_s >= grid_threshold * 0.6:
        category = "partial"
    else:
        category = "skip"

    return {
        "category": category,
        "palette_ratio": round(pal_r, 3),
        "grid_strength": round(grid_s, 4),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dir", type=Path,
        default=Path(r"E:\AI\virtual_player\yolo\pixelflow\labeling\images"),
    )
    ap.add_argument(
        "--out", type=Path,
        default=Path(r"E:\AI\virtual_player\yolo\pixelflow\labeling"),
    )
    ap.add_argument("--move", action="store_true")
    ap.add_argument("--thresh", type=float, default=0.5, help="palette_ratio 임계값")
    args = ap.parse_args()

    images = sorted(
        p for p in args.dir.iterdir()
        if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    print(f"[input] {len(images)} images")
    print(f"[thresholds] palette >= {args.thresh}, grid >= 0.03")

    results: list[dict] = []
    cat_counts = {"game": 0, "partial": 0, "skip": 0}

    for i, img_path in enumerate(images):
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        res = score_image(img, palette_threshold=args.thresh)
        res["file"] = img_path.name
        results.append(res)
        cat_counts[res["category"]] += 1
        if (i + 1) % 25 == 0 or i == len(images) - 1:
            print(
                f"  [{i+1}/{len(images)}] {img_path.name}: "
                f"{res['category']} (pal={res['palette_ratio']}, grid={res['grid_strength']})"
            )

    # 리스트 파일
    for cat in ("game", "partial", "skip"):
        lst = args.out / f"images_{cat}.txt"
        with lst.open("w", encoding="utf-8") as f:
            for r in results:
                if r["category"] == cat:
                    f.write(f"{r['file']}\n")

    # 리포트
    (args.out / "filter_report.json").write_text(
        json.dumps({"total": len(images), "counts": cat_counts, "results": results},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    if args.move:
        print("\n[move] 파일 이동 중...")
        for cat in ("game", "partial", "skip"):
            dst_dir = args.dir.parent / f"images_{cat}"
            dst_dir.mkdir(exist_ok=True)
            moved = 0
            for r in results:
                if r["category"] == cat:
                    src = args.dir / r["file"]
                    dst = dst_dir / r["file"]
                    if src.exists():
                        shutil.move(str(src), str(dst))
                        moved += 1
            print(f"  {dst_dir.name}: {moved} moved")

    print(f"\n=== Summary ===")
    print(f"  [game]    {cat_counts['game']:3d}  ← 라벨링 대상")
    print(f"  [partial] {cat_counts['partial']:3d}  ← 검토 필요")
    print(f"  [skip]    {cat_counts['skip']:3d}  ← 광고/메뉴")


if __name__ == "__main__":
    main()
