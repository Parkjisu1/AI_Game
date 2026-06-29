#!/usr/bin/env python3
"""Patch field_complete_levels.py with FC spec v1.2.9 + v1.2.16 + v1.2.21.

v1.2.9: Wooden Board PF size 분포 — 99.4% 다중 셀 (1×1 0.6%, 2×2 19%, ...).
v1.2.16: PO 결정 — Iron Wall 정사각 3종만 (1×1, 2×2, 3×3). HB=1×1 (이미 충족).
v1.2.21: IW 4×2 → 2×2 대체.
"""
import sys
PATH = "/home/aimed/.hermes/watcher/field_complete_levels.py"

# 1) Add wooden_board_size_v3 helper after wooden_board_hp_v2
SIZE_V3_HELPER = '''
def wooden_board_size_v3(rng: random.Random) -> tuple[int, int]:
    """v1.2.9 §7.7.1 정정 — PF Hard Pixel `pixels` 배열 areaX/areaY 분포.
    이전 v1.2.6 은 healths 만 보고 1×1 가정. 실제 PF 는 99.4% 다중 셀.
    분포 (PF picked 311 인스턴스):
        2×2 19% | 4×1 15% | 2×4 15% | 3×1 10% | 4×4 9%
        1×3 8%  | 3×3 7%  | 4×2 7%  | 2×6 4%  | 1×1 0.6%
        + 기타 (3×2, 2×3, 1×2, 2×1, 1×4, 5×5, 6×6 등) ~5%
    """
    options = [
        ((2, 2), 0.19),
        ((4, 1), 0.15),
        ((2, 4), 0.15),
        ((3, 1), 0.10),
        ((4, 4), 0.09),
        ((1, 3), 0.08),
        ((3, 3), 0.07),
        ((4, 2), 0.07),
        ((2, 6), 0.04),
        ((3, 2), 0.025),
        ((2, 3), 0.025),
        ((1, 2), 0.015),
        ((2, 1), 0.015),
        ((5, 5), 0.005),
        ((6, 6), 0.005),
        ((1, 1), 0.006),
    ]
    sizes = [s for s, _ in options]
    weights = [w for _, w in options]
    idx = _weighted_choice(sizes, weights, rng)
    return sizes[idx]


'''

OLD_HP_V2 = '''def iron_wall_y_v2(difficulty: str, rng: random.Random) -> float:'''

NEW_HP_V2 = SIZE_V3_HELPER + OLD_HP_V2

# 2) Update place_wooden_board: replace `size = (1,1) if cluster < 30 else (2,3)` with v3
OLD_WB_SIZE = '''        size = (1, 1) if c["size"] < 30 else (2, 3)'''
NEW_WB_SIZE = '''        # v1.2.9 §7.7.1 — PF 사이즈 분포. cluster 가 너무 작으면 fallback 1×1 / 2×2.
        proposed_size = wooden_board_size_v3(rng)
        if c["size"] < proposed_size[0] * proposed_size[1] * 2:
            # cluster 가 작으면 더 작은 사이즈
            size = (1, 1) if c["size"] < 8 else (2, 2)
        else:
            size = proposed_size'''

# 3) Update iron_wall pf_wall bbox distribution — v1.2.16 + v1.2.21 정사각 3종만
OLD_IW_BBOX = '''        # PF 모드: cluster 외부, 상단 위치
        for i in range(count):
            # bbox 분포 (PF 실측)
            r_pick = rng.random()
            if r_pick < 0.72:
                bbox = (2, 2)
            elif r_pick < 0.88:
                bbox = (4, 2)
            else:
                bbox = (3, 3)'''

NEW_IW_BBOX = '''        # PF 모드: cluster 외부, 상단 위치
        for i in range(count):
            # v1.2.16 + v1.2.21 (PO 결정): 정사각 3종만 (1×1, 2×2, 3×3).
            # PF 비정사각 (2×1·1×2·4×2) 차용 X — 4×2 87%는 2×2 로 대체.
            # PF picked 분포 정합: 2×2 87% / 3×3 8% / 1×1 3% (실측).
            r_pick = rng.random()
            if r_pick < 0.87:
                bbox = (2, 2)
            elif r_pick < 0.95:
                bbox = (3, 3)
            else:
                bbox = (1, 1)'''


def main():
    with open(PATH, encoding="utf-8") as f:
        src = f.read()
    if "wooden_board_size_v3" in src:
        print("already patched. abort.")
        sys.exit(0)
    for old, new, lbl in [
        (OLD_HP_V2, NEW_HP_V2, "insert wooden_board_size_v3"),
        (OLD_WB_SIZE, NEW_WB_SIZE, "wooden_board size v1.2.9"),
        (OLD_IW_BBOX, NEW_IW_BBOX, "iron_wall pf_wall bbox v1.2.16/21"),
    ]:
        if old not in src:
            print(f"ABORT — pattern not found: {lbl}", file=sys.stderr); sys.exit(1)
        src = src.replace(old, new, 1)
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("patched ok")


if __name__ == "__main__":
    main()
