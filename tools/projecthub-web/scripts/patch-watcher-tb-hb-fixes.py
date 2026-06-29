#!/usr/bin/env python3
"""두 건 mini-fix:
1) Target Box per_target_life — 옛 pick_pf_grounded_life → 난이도별 v2 분포
2) Hidden Balloon pct_cap 강제 — count > cap*total_cells 시 자동 감소
"""
import sys
PATH = "/home/aimed/.hermes/watcher/field_complete_levels.py"

# helper: target_box_per_target_life_v2 추가
HELPER_TB = '''
def target_box_per_target_life_v2(difficulty: str, rng: random.Random) -> int:
    """v1.2.6 +α: 난이도별 per-target HP (이전 pick_pf_grounded_life 대체).
    PF eggBoxes Eggs[].Count mode 10/12/20 + 난이도 ↑ HP ↑."""
    if difficulty in ("tutorial", "rest"):
        return rng.choice([5, 5, 8, 10])
    if difficulty == "normal":
        return rng.choices([5, 10, 12, 15], weights=[0.20, 0.35, 0.25, 0.20])[0]
    if difficulty == "hard":
        return rng.choices([10, 12, 15, 20], weights=[0.20, 0.30, 0.30, 0.20])[0]
    # super_hard
    return rng.choices([15, 20, 25, 30], weights=[0.25, 0.30, 0.25, 0.20])[0]


'''

OLD_TB_CALL = '''        per_target_life = pick_pf_grounded_life("Target_Box", "per_target", rng)'''
NEW_TB_CALL = '''        # v1.2.6+ 난이도별 per-target HP (audit 2026-05-26)
        per_target_life = target_box_per_target_life_v2(_diff, rng)'''

# Hidden Balloon pct_cap 강제 — count > cap*total_cells 면 감소
OLD_HB_INTRO = '''def place_hidden_balloon(clusters: list[dict], count: int,
                         non_meta: list[tuple[int, int]],
                         used: set[tuple[int, int]],
                         rng: random.Random,
                         field_map: list[list[int]]) -> list[dict]:
    """gimmick_surprise: 메타포 보존 — cluster interior (dense area)에서 cluster 비례 sampling.
    outline 인접 셀은 제외 (윤곽 보존)."""
    if not clusters or count == 0:
        return []'''

NEW_HB_INTRO = '''def place_hidden_balloon(clusters: list[dict], count: int,
                         non_meta: list[tuple[int, int]],
                         used: set[tuple[int, int]],
                         rng: random.Random,
                         field_map: list[list[int]],
                         purpose_type: str = "normal") -> list[dict]:
    """gimmick_surprise: 메타포 보존 — cluster interior 에서 cluster 비례 sampling.
    v1.2.16+: 1×1 only. v1.2.6+ pct_cap_v2 강제 — count > cap × board_balloon_cells 면 자동 감소.
    outline 인접 셀은 제외 (윤곽 보존)."""
    if not clusters or count == 0:
        return []
    # v1.2.6 §7.7.2 pct_cap 강제 — board_balloon_cells 의 cap% 초과 시 감소
    board_balloon_cells = sum(c["size"] for c in clusters if not c["is_symbol"])
    diff = normalize_purpose(purpose_type)
    pct_cap = hidden_balloon_pct_cap_v2(diff)
    max_allowed = max(1, int(board_balloon_cells * pct_cap))
    if count > max_allowed:
        log.warning("place_hidden_balloon: count %d > cap (%.0f%% × %d = %d) → 감소",
                    count, pct_cap * 100, board_balloon_cells, max_allowed)
        count = max_allowed'''

# track_b 의 call site 도 purpose_type 전달
OLD_HB_TRACK = '''        hb = place_hidden_balloon(clusters, cnt, non_meta, used_cells, rng, field_map)'''
NEW_HB_TRACK = '''        hb = place_hidden_balloon(clusters, cnt, non_meta, used_cells, rng, field_map,
                                   purpose_type=normalize_purpose(csv_row.get("purpose_type")))'''


def main():
    with open(PATH, encoding="utf-8") as f:
        src = f.read()
    if "target_box_per_target_life_v2" in src:
        print("already patched. abort.")
        sys.exit(0)
    # Insert TB helper after barricade_length_v2 (or any v2 helper area)
    anchor = "def hidden_balloon_pct_cap_v2"
    if anchor not in src:
        print("anchor not found", file=sys.stderr); sys.exit(1)
    src = src.replace(anchor, HELPER_TB + anchor, 1)

    for old, new, lbl in [
        (OLD_TB_CALL, NEW_TB_CALL, "TB per_target_life v2"),
        (OLD_HB_INTRO, NEW_HB_INTRO, "HB pct_cap intro"),
        (OLD_HB_TRACK, NEW_HB_TRACK, "track_b HB purpose"),
    ]:
        if old not in src:
            print(f"ABORT: {lbl} not found", file=sys.stderr); sys.exit(1)
        src = src.replace(old, new, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("patched ok")


if __name__ == "__main__":
    main()
