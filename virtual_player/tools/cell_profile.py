"""
Cell Profile Builder — 게임별 셀 프로파일 생성
================================================
검증된 레벨 JSON + 스크린샷에서 셀 속성을 추출하여
cell_profile.json을 생성.

사용법:
  python cell_profile.py --game pixelflow \
    --levels-dir E:/AI/virtual_player/data/journal/games/pixelflow/level_designs_verified \
    --output E:/AI/virtual_player/data/journal/games/pixelflow/cell_profile.json
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image


# 29색 팔레트
PALETTE_29 = {
    1: (252,106,175), 2: (80,232,246),  3: (137,80,248),
    4: (254,213,85),  5: (115,254,102), 6: (253,161,76),
    7: (255,255,255), 8: (65,65,65),    9: (110,168,250),
    10:(57,174,46),   11:(252,94,94),   12:(50,107,248),
    13:(58,165,139),  14:(231,167,250), 15:(183,199,251),
    16:(106,74,48),   17:(254,227,169), 18:(253,183,193),
    19:(158,61,94),   20:(167,221,148), 21:(89,46,126),
    22:(220,120,129), 23:(217,217,231), 24:(111,114,127),
    25:(252,56,165),  26:(253,180,88),  27:(137,10,8),
    28:(111,175,177), 29:(100,80,60),
}

COLOR_NAMES = {
    1:'Pink', 2:'Cyan', 3:'Purple', 4:'Yellow', 5:'Green', 6:'Orange',
    7:'White', 8:'Dark', 9:'LightBlue', 10:'DarkGreen', 11:'Red', 12:'Blue',
    13:'Teal', 14:'Lavender', 15:'Periwinkle', 16:'Brown', 17:'Peach',
    18:'LightPink', 19:'Maroon', 20:'MintGreen', 21:'DarkPurple',
    22:'DustyRose', 23:'Silver', 24:'Gray', 25:'HotPink', 26:'Amber',
    27:'DarkRed', 28:'SageTeal', 29:'BrownDark',
}


def build_profile(levels_dir, render_ranges_path=None):
    """검증 레벨 데이터에서 셀 프로파일 추출."""

    levels_dir = Path(levels_dir)
    json_dir = levels_dir / "json"
    boards_dir = levels_dir / "boards"

    # 1) JSON 분석 — 그리드/색상 통계
    jsons = sorted(json_dir.glob("level_*.json")) if json_dir.exists() else []
    if not jsons:
        print(f"No level JSONs found in {json_dir}")
        return None

    grid_rows_all = Counter()
    grid_cols_all = Counter()
    edge_colors = Counter()
    content_colors = Counter()
    all_colors_used = Counter()

    for jf in jsons:
        with open(jf, encoding="utf-8") as f:
            d = json.load(f)

        rows = d.get("field_rows", 50)
        cols = d.get("field_columns", 50)
        grid_rows_all[rows] += 1
        grid_cols_all[cols] += 1

        # FieldMap 파싱
        dn = d.get("designer_note", "")
        fm = dn.replace("[FieldMap]\n", "").replace("[FieldMap]", "").strip()
        if not fm:
            continue

        grid = []
        for line in fm.split("\n"):
            tokens = line.strip().split()
            grid.append([int(t) for t in tokens])

        if not grid:
            continue

        R, C = len(grid), len(grid[0])

        # 가장자리 색상 (프레임/바닥 후보)
        for r in range(R):
            for c in range(C):
                v = grid[r][c]
                all_colors_used[v] += 1
                # 가장자리: 좌2열, 우5열, 상2행, 하2행
                is_edge = (c < 2 or c >= C - 5 or r < 2 or r >= R - 2)
                if is_edge:
                    edge_colors[v] += 1
                else:
                    content_colors[v] += 1

    # 가장 흔한 그리드 크기
    common_rows = grid_rows_all.most_common(1)[0][0]
    common_cols = grid_cols_all.most_common(1)[0][0]

    # 프레임 색상 판별: 가장자리에서 80% 이상인 색상
    total_edge = sum(edge_colors.values())
    frame_colors = []
    for cid, cnt in edge_colors.most_common():
        ratio = cnt / total_edge
        if ratio > 0.02:  # 2% 이상
            # 콘텐츠 영역에서의 비율과 비교
            content_ratio = content_colors.get(cid, 0) / max(sum(content_colors.values()), 1)
            edge_ratio = cnt / total_edge
            # 가장자리 비율이 콘텐츠 비율보다 2배 이상이면 프레임 후보
            if edge_ratio > content_ratio * 1.5 or edge_ratio > 0.3:
                frame_colors.append(cid)

    # 2) 이미지 분석 — 셀 픽셀 크기
    cell_px = None
    board_size = None
    if boards_dir.exists():
        board_imgs = sorted(boards_dir.glob("*.png"))[:10]
        sizes = []
        for bp in board_imgs:
            img = Image.open(bp)
            w, h = img.size
            sizes.append((w, h))
            cw = w / common_cols
            ch = h / common_rows

        if sizes:
            avg_w = np.mean([s[0] for s in sizes])
            avg_h = np.mean([s[1] for s in sizes])
            cell_px = {
                "width": round(avg_w / common_cols, 2),
                "height": round(avg_h / common_rows, 2),
            }
            board_size = {
                "width": round(avg_w),
                "height": round(avg_h),
            }

    # 3) 렌더 범위 로드
    render_ranges = {}
    if render_ranges_path and Path(render_ranges_path).exists():
        with open(render_ranges_path, encoding="utf-8") as f:
            render_ranges = json.load(f)

    # 4) 프로파일 생성
    profile = {
        "game_id": "pixelflow",
        "grid": {
            "rows": common_rows,
            "cols": common_cols,
            "total_cells": common_rows * common_cols,
            "fixed": True,  # 모든 레벨에서 고정
        },
        "cell": {
            "px_width": cell_px["width"] if cell_px else None,
            "px_height": cell_px["height"] if cell_px else None,
            "shape": "square",  # Pixelflow는 정사각 셀
            "sample_ratio": 0.5,  # 셀 중심 50%만 샘플링
        },
        "board": {
            "px_width": board_size["width"] if board_size else None,
            "px_height": board_size["height"] if board_size else None,
        },
        "colors": {
            "palette_size": 29,
            "palette": {str(k): {"rgb": list(v), "name": COLOR_NAMES.get(k, f"C{k}")}
                        for k, v in PALETTE_29.items()},
            "frame_colors": frame_colors,  # 프레임/바닥에 주로 사용되는 색상
            "frame_color_names": [COLOR_NAMES.get(c, f"C{c}") for c in frame_colors],
        },
        "ignore_elements": {
            "frame": {
                "description": "좌측 2열 + 우측 5열 + 상하 2행은 프레임 영역",
                "left_cols": 2,
                "right_cols": 5,
                "top_rows": 2,
                "bottom_rows": 2,
            },
            "floor_tile": {
                "description": "c8(Dark), c21(DarkPurple)이 바닥/프레임의 주요 색상",
                "color_ids": [c for c in frame_colors if c in (8, 21)],
            },
            "conveyor": {
                "description": "특정 방향성 패턴 — 향후 학습 필요",
                "detected": False,
            },
        },
        "statistics": {
            "levels_analyzed": len(jsons),
            "colors_used": len(all_colors_used),
            "most_common_colors": [
                {"id": cid, "name": COLOR_NAMES.get(cid, f"C{cid}"),
                 "count": cnt, "pct": round(cnt / sum(all_colors_used.values()) * 100, 1)}
                for cid, cnt in all_colors_used.most_common(10)
            ],
        },
    }

    # 렌더 범위 추가
    if render_ranges:
        profile["render_ranges"] = render_ranges

    return profile


def main():
    parser = argparse.ArgumentParser(description="Cell Profile Builder")
    parser.add_argument("--game", default="pixelflow")
    parser.add_argument("--levels-dir", required=True, help="검증 레벨 폴더")
    parser.add_argument("--render-ranges", help="color_render_ranges.json 경로")
    parser.add_argument("--output", "-o", required=True, help="출력 경로")
    args = parser.parse_args()

    profile = build_profile(args.levels_dir, args.render_ranges)
    if profile:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, ensure_ascii=False)
        print(f"Profile saved: {args.output}")
        print(f"  Grid: {profile['grid']['rows']}x{profile['grid']['cols']}")
        print(f"  Cell: {profile['cell']['px_width']}x{profile['cell']['px_height']}px")
        print(f"  Frame colors: {profile['colors']['frame_color_names']}")
        print(f"  Levels analyzed: {profile['statistics']['levels_analyzed']}")


if __name__ == "__main__":
    main()
