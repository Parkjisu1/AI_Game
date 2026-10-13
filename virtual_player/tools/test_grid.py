"""grid_detector 테스트 — 보드 크롭 후 그리드 차원 탐지"""
import sys
import cv2
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cell_aware_analyzer import find_board_region, load_profile
from grid_detector import detect_grid_dimensions


def test_image(img_path, profile, expected_rows=None, expected_cols=None):
    img_bgr = cv2.imread(str(img_path))
    if img_bgr is None:
        print(f"  ERR: cannot read {img_path}")
        return

    # 1. 보드 크롭
    board_bgr, crop_rect = find_board_region(img_bgr, profile)
    board_rgb = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2RGB)

    # 2. 그리드 탐지
    result = detect_grid_dimensions(board_rgb)

    mark = ""
    if expected_rows and expected_cols:
        if result["rows"] == expected_rows and result["cols"] == expected_cols:
            mark = " [MATCH]"
        else:
            mark = f" [expected {expected_rows}x{expected_cols}]"

    print(
        f"  {Path(img_path).name}: "
        f"board={board_rgb.shape[1]}x{board_rgb.shape[0]}, "
        f"grid={result['cols']}x{result['rows']}, "
        f"pitch={result['pitch_h']:.1f}x{result['pitch_v']:.1f}, "
        f"conf={result['confidence']:.2f}{mark}"
    )
    return result


if __name__ == "__main__":
    profile = load_profile(
        r"E:\AI\virtual_player\data\pixelflow\profile\cell_profile.json"
    )

    img_dir = Path(r"E:\AI\virtual_player\data\pixelflow\images")
    # level_051 소스 (FieldMap 40x40)
    samples = [
        ("click_20260325_102002_0171_after.png", 40, 40),
        ("click_20260325_101717_0001_after.png", None, None),
        ("click_20260325_101730_0014_after.png", None, None),
        ("click_20260325_101759_0044_after.png", None, None),
    ]

    for fname, er, ec in samples:
        p = img_dir / fname
        if p.exists():
            test_image(p, profile, er, ec)
        else:
            print(f"  SKIP (not found): {fname}")
