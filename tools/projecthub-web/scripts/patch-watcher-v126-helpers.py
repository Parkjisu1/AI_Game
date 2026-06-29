#!/usr/bin/env python3
"""Patch field_complete_levels.py with v1.2.6 difficulty-based bimodal/trimodal helpers.

Spec ref: 02_BalloonFlow_필드완성_명세_v1_2.md §7.7 (v1.2.6)
Why: 단일 PF_LIFE_DISTRIBUTIONS 분포는 분포 형태(bimodal/trimodal)와 난이도 차이를 무시.
실제 PF 1-300 분석은 Wooden Board HP bimodal, Iron Wall Y trimodal 등 양극화 패턴.
"""
import sys

PATH = "/home/aimed/.hermes/watcher/field_complete_levels.py"

# Insertion point: after PF_PLACEMENT_BIAS def (line ~251)
HELPERS = '''
# ─────────────────────────────────────────────────────
# v1.2.6 난이도별 분포 헬퍼 (§7.7) — PF 1-300 분포 기반
# 단일 평균이 아닌 bimodal/trimodal/단조증가 패턴 반영.
# ─────────────────────────────────────────────────────

def wooden_board_hp_v2(size_cells: int, difficulty: str, rng: random.Random) -> int:
    """§7.7.1 — 바이모달. 78% 소HP(4-10) + 17% 대HP spike(20+).
    난이도 ↑ = 대HP cluster 비율 ↑.
    size_cells: 클러스터 셀 수. size 곱셈은 BL 사이즈 곡선.
    """
    big_spike_chance = {
        "tutorial": 0.05, "rest": 0.10,
        "normal": 0.17,
        "hard": 0.30, "super_hard": 0.40,
    }.get(difficulty, 0.17)

    if rng.random() < big_spike_chance:
        # 대HP: PF mode 20 (88% of big), 30+ rare
        idx = _weighted_choice([20, 30, 40, 50], [0.70, 0.15, 0.10, 0.05], rng)
        base = [20, 30, 40, 50][idx]
    else:
        # 소HP: PF 빈도 5/6/10/4/7/8/9 (mode-aware)
        vals = [4, 5, 6, 7, 8, 9, 10]
        weights = [0.13, 0.18, 0.15, 0.11, 0.04, 0.03, 0.14]
        idx = _weighted_choice(vals, weights, rng)
        base = vals[idx]
    # size 곱셈 (BL 사이즈 곡선)
    if size_cells >= 9:
        return base * 3
    if size_cells >= 4:
        return base * 2
    return base


def iron_wall_y_v2(difficulty: str, rng: random.Random) -> float:
    """§7.7.3 — 양극 trimodal. 상단(0.0-0.2) vs 중앙(0.4-0.6) vs 하단(0.8-1.0).
    난이도 ↑ = 중앙 감소 + 양극화 강화.
    """
    profile = {
        "tutorial":   [0.43, 0.21, 0.36],
        "rest":       [0.43, 0.21, 0.36],
        "normal":     [0.50, 0.18, 0.32],
        "hard":       [0.59, 0.09, 0.32],
        "super_hard": [0.55, 0.15, 0.30],
    }.get(difficulty, [0.50, 0.18, 0.32])
    zones = ["top", "mid", "bot"]
    idx = _weighted_choice(zones, profile, rng)
    zone = zones[idx]
    if zone == "top":
        return rng.uniform(0.0, 0.2)
    if zone == "mid":
        return rng.uniform(0.4, 0.6)
    return rng.uniform(0.8, 1.0)


def frozen_layer_health_per_cell_v2(difficulty: str, rng: random.Random) -> int:
    """§7.7.4 — 난이도별 비대칭 분포. PF Medium mode 1, VH mode 8."""
    if difficulty in ("tutorial", "rest"):
        return 1  # 학습용
    if difficulty == "normal":
        # PF Medium mode 1.1 (27%)
        idx = _weighted_choice([1, 2], [0.70, 0.30], rng)
        return [1, 2][idx]
    if difficulty == "hard":
        idx = _weighted_choice([1, 2, 3], [0.40, 0.30, 0.30], rng)
        return [1, 2, 3][idx]
    # super_hard: PF VH mode 8 (15%), spread
    idx = _weighted_choice([1, 2, 3, 8], [0.30, 0.20, 0.20, 0.30], rng)
    return [1, 2, 3, 8][idx]


def hidden_balloon_pct_cap_v2(difficulty: str) -> float:
    """§7.7.2 — 난이도별 점유율 cap (board pixels 대비)."""
    return {
        "tutorial": 0.03, "rest": 0.03,
        "normal": 0.05,        # PF Medium med 1.8%
        "hard": 0.08,
        "super_hard": 0.12,    # PF Very Hard med 9.4%
    }.get(difficulty, 0.05)


def target_box_size_v2(difficulty: str, rng: random.Random) -> tuple[tuple[int, int], int]:
    """§7.7.5 — 난이도별 box size (rows, cols) + eggs."""
    if difficulty in ("tutorial", "rest"):
        return ((2, 2), 4)
    if difficulty == "normal":
        opts = [((2, 2), 4), ((2, 3), 6)]
        idx = _weighted_choice(opts, [0.70, 0.30], rng)
        return opts[idx]
    if difficulty == "hard":
        opts = [((2, 3), 6), ((3, 3), 9)]
        idx = _weighted_choice(opts, [0.60, 0.40], rng)
        return opts[idx]
    # super_hard
    opts = [((3, 3), 9), ((2, 3), 6)]
    idx = _weighted_choice(opts, [0.60, 0.40], rng)
    return opts[idx]


def barricade_length_v2(difficulty: str, rng: random.Random) -> int:
    """§7.7.6 — 난이도별 단조 증가. PF HP / 10 가이드 (BL 1-dart/cell)."""
    length_dist = {
        "tutorial":   ([3, 4], [0.70, 0.30]),
        "rest":       ([3, 4], [0.70, 0.30]),
        "normal":     ([3, 5, 6], [0.30, 0.40, 0.30]),
        "hard":       ([5, 6, 7], [0.30, 0.30, 0.40]),
        "super_hard": ([6, 7, 8], [0.25, 0.25, 0.50]),
    }.get(difficulty, ([3, 5, 6], [0.30, 0.40, 0.30]))
    vals, weights = length_dist
    idx = _weighted_choice(vals, weights, rng)
    return vals[idx]

'''

# Modify score_placement_candidates to accept y_target_override
OLD_SCORE_SIG = '''def score_placement_candidates(candidates: list[tuple[int, int]],
                               gimmick_type: str,
                               field_h: int,
                               field_w: int,
                               cluster: dict | None = None) -> list[tuple[tuple[int, int], float]]:
    """각 후보 셀에 PF 위치 편중 기반 점수 부여.
    returns sorted desc by score: [(cell, score), ...]"""
    bias = PF_PLACEMENT_BIAS.get(gimmick_type, {})
    y_target = bias.get("y_target", 0.5)'''

NEW_SCORE_SIG = '''def score_placement_candidates(candidates: list[tuple[int, int]],
                               gimmick_type: str,
                               field_h: int,
                               field_w: int,
                               cluster: dict | None = None,
                               y_target_override: float | None = None) -> list[tuple[tuple[int, int], float]]:
    """각 후보 셀에 PF 위치 편중 기반 점수 부여.
    v1.2.6: y_target_override 로 trimodal Y 가능 (Iron Wall pf_wall).
    returns sorted desc by score: [(cell, score), ...]"""
    bias = PF_PLACEMENT_BIAS.get(gimmick_type, {})
    y_target = y_target_override if y_target_override is not None else bias.get("y_target", 0.5)'''

# Update place_iron_wall pf_wall mode to use trimodal Y
OLD_IW_PF_WALL = '''            if not candidates:
                continue
            scored = score_placement_candidates(candidates, "Iron_Wall", field_h, field_w)
            top = scored[: max(1, len(scored) // 5)]
            anchor = top[rng.randrange(min(5, len(top)))][0]'''

NEW_IW_PF_WALL = '''            if not candidates:
                continue
            # v1.2.6 §7.7.3: trimodal Y (top/mid/bot)
            _iw_diff = normalize_purpose(_iw_purpose)
            _y_target = iron_wall_y_v2(_iw_diff, rng)
            scored = score_placement_candidates(candidates, "Iron_Wall", field_h, field_w,
                                                 y_target_override=_y_target)
            top = scored[: max(1, len(scored) // 5)]
            anchor = top[rng.randrange(min(5, len(top)))][0]'''

# place_iron_wall signature add purpose_type
OLD_IW_SIG = '''def place_iron_wall(clusters: list[dict], count: int, rng: random.Random,
                    mode: str = "bl_outline",
                    field_h: int = 0, field_w: int = 0) -> list[dict]:'''

NEW_IW_SIG = '''def place_iron_wall(clusters: list[dict], count: int, rng: random.Random,
                    mode: str = "bl_outline",
                    field_h: int = 0, field_w: int = 0,
                    purpose_type: str = "normal") -> list[dict]:'''

OLD_IW_BODY_START = '''    """gimmick_wall: v1.2.3 mode-split.
    mode='bl_outline' (default): count=1 → 전 outline 연속선, count>=2 → +분할벽.
    mode='pf_wall': PF 패턴 (2×2 72% / 4×2 16%), cluster 외부 + 상단 (Y=0.26)."""
    if not clusters:
        return []
    walls = []'''

NEW_IW_BODY_START = '''    """gimmick_wall: v1.2.3 mode-split, v1.2.6 trimodal Y in pf_wall.
    mode='bl_outline' (default): count=1 → 전 outline 연속선, count>=2 → +분할벽.
    mode='pf_wall': PF 패턴 (2×2 72% / 4×2 16%), v1.2.6 trimodal Y."""
    if not clusters:
        return []
    walls = []
    _iw_purpose = purpose_type'''

# Caller in track_b — pass purpose_type
OLD_TRACK_B_IW = '''        walls = place_iron_wall(clusters, cnt, rng,
                                 mode=iw_mode, field_h=field_h, field_w=field_w)'''

NEW_TRACK_B_IW = '''        walls = place_iron_wall(clusters, cnt, rng,
                                 mode=iw_mode, field_h=field_h, field_w=field_w,
                                 purpose_type=normalize_purpose(csv_row.get("purpose_type")))'''

# Frozen Layer: use v2 helper instead of pick_pf_grounded_life
OLD_FROZEN_CALL = '''        # counter 계산 (PF Health/cell 분포)
        per_cell_health = pick_pf_grounded_life("Frozen_Layer", "per_cell", rng)'''

NEW_FROZEN_CALL = '''        # counter 계산 — v1.2.6 §7.7.4 난이도별 비대칭 분포
        per_cell_health = frozen_layer_health_per_cell_v2(_fl_difficulty, rng)'''

# Frozen Layer signature: add difficulty param via purpose_type
OLD_FROZEN_SIG = '''def place_frozen_layer(clusters: list[dict], count: int, field_map: list[list[int]],
                       rng: random.Random) -> list[dict]:'''

NEW_FROZEN_SIG = '''def place_frozen_layer(clusters: list[dict], count: int, field_map: list[list[int]],
                       rng: random.Random, purpose_type: str = "normal") -> list[dict]:'''

OLD_FROZEN_BODY_START = '''    counter = cells × pick_pf_grounded_life("Frozen_Layer", "per_cell")."""
    if not clusters or count == 0:
        return []'''

NEW_FROZEN_BODY_START = '''    counter = cells × frozen_layer_health_per_cell_v2(difficulty) — v1.2.6 난이도별."""
    _fl_difficulty = normalize_purpose(purpose_type)
    if not clusters or count == 0:
        return []'''

OLD_TRACK_B_FROZEN = '''        frozen = place_frozen_layer(clusters, cnt, field_map, rng)'''
NEW_TRACK_B_FROZEN = '''        frozen = place_frozen_layer(clusters, cnt, field_map, rng,
                                     purpose_type=normalize_purpose(csv_row.get("purpose_type")))'''

# Wooden Board: use v2 helper
OLD_WB_CALL = '''        # v1.2.3: PF Hard Pixel HP 분포 sampling
        size_key = "1x1" if size == (1, 1) else "2x3"
        life = pick_pf_grounded_life("Wooden_Board", size_key, rng)'''

NEW_WB_CALL = '''        # v1.2.6 §7.7.1 bimodal HP (난이도별 spike chance)
        life = wooden_board_hp_v2(len(cells), _wb_difficulty, rng)'''

OLD_WB_SIG = '''def place_wooden_board(clusters: list[dict], count: int,'''
NEW_WB_SIG = '''def place_wooden_board(clusters: list[dict], count: int,
                        purpose_type: str = "normal","""  # placeholder, will fix below
def _wb_sig_marker():
    pass
'''

# Actually wooden_board sig is multi-line. Let me handle differently - just add purpose_type internal lookup at function start
OLD_WB_FUNC_HEAD = '''def place_wooden_board(clusters: list[dict], count: int,
                       used: set[tuple[int, int]],
                       rng: random.Random,
                       field_h: int = 0, field_w: int = 0) -> list[dict]:'''

NEW_WB_FUNC_HEAD = '''def place_wooden_board(clusters: list[dict], count: int,
                       used: set[tuple[int, int]],
                       rng: random.Random,
                       field_h: int = 0, field_w: int = 0,
                       purpose_type: str = "normal") -> list[dict]:'''

OLD_WB_DOC = '''    """gimmick_pinata: v1.2.3 — score_placement_candidates + find_first_valid 라우팅.
    centroid 회피, redundant interior 우선, PF Hard Pixel HP 분포 라이프."""
    if not clusters or count == 0:
        return []'''
NEW_WB_DOC = '''    """gimmick_pinata: v1.2.3 routing + v1.2.6 bimodal HP (난이도별 spike chance).
    centroid 회피, redundant interior 우선, 78% 소HP + 17% 대HP."""
    _wb_difficulty = normalize_purpose(purpose_type)
    if not clusters or count == 0:
        return []'''

OLD_TRACK_B_WB = '''        wb = place_wooden_board(clusters, cnt, used_cells, rng,
                                 field_h=field_h, field_w=field_w)'''
NEW_TRACK_B_WB = '''        wb = place_wooden_board(clusters, cnt, used_cells, rng,
                                 field_h=field_h, field_w=field_w,
                                 purpose_type=normalize_purpose(csv_row.get("purpose_type")))'''

# Barricade: use v2 helper (replaces fixed PF Door distribution)
OLD_BR_CALL = '''        # PF Door 분포 기반 length pick
        length = pick_pf_grounded_life("Barricade", "length", rng)'''

NEW_BR_CALL = '''        # v1.2.6 §7.7.6 난이도별 단조 증가 length
        length = barricade_length_v2(purpose_type, rng)'''

# place_barricade already accepts purpose_type. Verify name binding.

# Caller in track_b already passes purpose=normalize_purpose(...) for barricade.

# Verify pick_pf_grounded_life for Target_Box per_target — keep as-is (size_v2 not needed for now).

PATCHES = [
    (OLD_SCORE_SIG, NEW_SCORE_SIG, "score_placement_candidates sig"),
    (OLD_IW_SIG, NEW_IW_SIG, "place_iron_wall sig"),
    (OLD_IW_BODY_START, NEW_IW_BODY_START, "place_iron_wall doc+_iw_purpose"),
    (OLD_IW_PF_WALL, NEW_IW_PF_WALL, "iron_wall pf_wall trimodal Y"),
    (OLD_TRACK_B_IW, NEW_TRACK_B_IW, "track_b iron_wall purpose"),
    (OLD_FROZEN_SIG, NEW_FROZEN_SIG, "place_frozen_layer sig"),
    (OLD_FROZEN_BODY_START, NEW_FROZEN_BODY_START, "place_frozen_layer doc"),
    (OLD_FROZEN_CALL, NEW_FROZEN_CALL, "frozen_layer v2 helper"),
    (OLD_TRACK_B_FROZEN, NEW_TRACK_B_FROZEN, "track_b frozen purpose"),
    (OLD_WB_FUNC_HEAD, NEW_WB_FUNC_HEAD, "place_wooden_board sig"),
    (OLD_WB_DOC, NEW_WB_DOC, "place_wooden_board doc + _wb_difficulty"),
    (OLD_WB_CALL, NEW_WB_CALL, "wooden_board v2 helper"),
    (OLD_TRACK_B_WB, NEW_TRACK_B_WB, "track_b wooden_board purpose"),
    (OLD_BR_CALL, NEW_BR_CALL, "barricade v2 helper"),
]


def main():
    with open(PATH, encoding="utf-8") as f:
        src = f.read()

    if "wooden_board_hp_v2" in src:
        print("already patched (wooden_board_hp_v2 exists). Aborting.", file=sys.stderr)
        sys.exit(1)

    # Verify all OLD blocks present (dry-run)
    for old, _, label in PATCHES:
        if old not in src:
            print(f"ABORT — OLD pattern not found for: {label}", file=sys.stderr)
            # print surrounding lines
            for line in old.split("\n")[:3]:
                print(f"  expected: {line!r}", file=sys.stderr)
            sys.exit(1)

    # Insert helpers right after PF_PLACEMENT_BIAS dict (before pick_pf_grounded_life func)
    marker = "def pick_pf_grounded_life(gimmick_type: str, ctx: str | None,"
    if marker not in src:
        print("ABORT: pick_pf_grounded_life marker missing", file=sys.stderr)
        sys.exit(1)
    src = src.replace(marker, HELPERS + "\n" + marker, 1)

    # Apply replacements
    for old, new, label in PATCHES:
        if old not in src:
            print(f"WARN: pattern lost after preceding patch: {label}", file=sys.stderr)
            continue
        src = src.replace(old, new, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("patched ok")


if __name__ == "__main__":
    main()
