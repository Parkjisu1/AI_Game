#!/usr/bin/env python3
"""Watcher 패치: v1.2.14 (Barricade/Snake HP intent helpers) + v1.2.10/20 (Snake 기믹 신규).

Adds:
- barricade_hp_from_length(length, intent) — 4단계 intent (fast/normal/slow/boss/cathartic)
- snake_hp_from_cells(total_cells, intent) — 5단계 intent
- place_snake(...) — PF MainGridPoints + SnakeGridPoints 모사 (debut lv 81, Lock&Key 대체)
- grow_snake_body_segments — zigzag 60% + jump 40% (v1.2.17 실측 정합)
- BL_DEBUT_LV["gimmick_snake"] = 81
- track_b: csv_row.gimmick_snake > 0 일 때 place_snake 호출
"""
import sys
PATH = "/home/aimed/.hermes/watcher/field_complete_levels.py"

# 1) Add HP intent helpers + Snake placement after barricade_length_v2
HELPERS = '''
# ─────────────────────────────────────────────────────
# v1.2.14 HP × Length 독립 — intent 기반 라이프 (PO 직감 검증)
# ─────────────────────────────────────────────────────

def barricade_hp_from_length(length: int, intent: str, rng: random.Random) -> int:
    """Barricade HP를 cell length와 의도로 결정.
    intent: 'fast'(1-2/cell, 빨리 제거) / 'normal'(2-3) / 'slow'(4-5) / 'boss'(6-7).
    PO 직감 검증: 같은 length 에도 HP variance 존재 (퍽퍽 vs 천천히)."""
    ratio_range = {
        "fast": (1, 2),
        "normal": (2, 3),
        "slow": (4, 5),
        "boss": (6, 7),
    }.get(intent, (2, 3))
    return max(1, length * rng.randint(*ratio_range))


def snake_hp_from_cells(total_cells: int, intent: str, rng: random.Random) -> int:
    """Snake HP를 총 셀 수와 의도로 결정.
    intent: 'cathartic'(0.5/cell, 대폭발) / 'normal'(1-2) / 'tough'(3-4) / 'boss'(5-12)."""
    if intent == "cathartic":
        return max(20, int(total_cells * 0.5))
    if intent == "tough":
        return int(total_cells * rng.uniform(3.0, 4.0))
    if intent == "boss":
        return int(total_cells * rng.uniform(5.0, 12.0))
    return int(total_cells * rng.uniform(1.0, 2.0))


def difficulty_to_intent(difficulty: str, gimmick_type: str = "Barricade") -> str:
    """난이도 → HP intent 매핑. Barricade·Snake 공통."""
    mapping = {
        "tutorial":   "fast",
        "rest":       "fast",
        "normal":     "normal",
        "hard":       "slow",
        "super_hard": "boss",
    }
    return mapping.get(difficulty, "normal")


# ─────────────────────────────────────────────────────
# v1.2.10/20 Snake 신규 기믹 (Lock & Key 대체 후보, debut lv 81)
# ─────────────────────────────────────────────────────

def grow_snake_body_segments(head_anchor, head_size, n_segments,
                              available_cells, used: set, rng: random.Random,
                              field_h: int, field_w: int):
    """SnakeGridPoints 모사 — 마디를 n_segments 개 walk.
    v1.2.17 실측 정합: zigzag(≤2칸) 60% + jump(>2칸) 40%.

    각 마디 = head_size 크기 셀 블록. 연속 곡선 보장 (꺾이는 corner 좌표).
    """
    segments = []
    cur = tuple(head_anchor)
    used_local = set(used)
    used_local.update(_rect_cells(head_anchor, head_size))

    for _seg_idx in range(n_segments):
        # zigzag vs jump 선택
        if rng.random() < 0.60:
            # zigzag: 인접 2칸 step (4방향)
            step_distance = rng.choice([2, 2, 2, 3])
        else:
            # jump: 3-35칸 long-tail
            step_distance = rng.randint(3, min(15, max(3, field_h // 2)))

        # 4방향 중 하나
        directions = [(0, step_distance), (0, -step_distance),
                      (step_distance, 0), (-step_distance, 0)]
        rng.shuffle(directions)

        placed = False
        for dy, dx in directions:
            nxt_anchor = (cur[0] + dy, cur[1] + dx)
            seg_cells = _rect_cells(nxt_anchor, head_size)
            if all(0 <= r < field_h and 0 <= c < field_w and (r, c) not in used_local
                   and (r, c) in available_cells
                   for r, c in seg_cells):
                segments.append(seg_cells)
                used_local.update(seg_cells)
                cur = nxt_anchor
                placed = True
                break
        if not placed:
            # 더 작은 step 으로 재시도 (1칸 인접)
            for dy, dx in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nxt_anchor = (cur[0] + dy, cur[1] + dx)
                seg_cells = _rect_cells(nxt_anchor, head_size)
                if all(0 <= r < field_h and 0 <= c < field_w and (r, c) not in used_local
                       and (r, c) in available_cells
                       for r, c in seg_cells):
                    segments.append(seg_cells)
                    used_local.update(seg_cells)
                    cur = nxt_anchor
                    placed = True
                    break
        if not placed:
            break  # 더 이상 갈 곳 없음
    return segments


def _rect_cells(anchor, size):
    """anchor (top-left) + size (rows, cols) → cell list."""
    r0, c0 = anchor
    h, w = size
    return [(r0 + dr, c0 + dc) for dr in range(h) for dc in range(w)]


def place_snake(clusters: list[dict], count: int, csv_row: dict,
                used: set, rng: random.Random,
                field_h: int, field_w: int,
                field_map: list[list[int]]) -> list[dict]:
    """v1.2.10/20 gimmick_snake — debut lv 81 (PO 결정 시 변경).
    PF MainGridPoints (머리 마디) + SnakeGridPoints (몸 마디 좌표 시퀀스) 모사.
    """
    if not clusters or count == 0:
        return []
    purpose = normalize_purpose(csv_row.get("purpose_type"))
    intent = difficulty_to_intent(purpose, "Snake")

    # available_cells = 모든 cluster cells (메타포 포함) — Snake 는 메타포 위 가능
    available_cells: set = set()
    for c in clusters:
        available_cells.update(c["cells"])
    available_cells -= used

    result = []
    for i in range(count):
        # 머리 마디 사이즈: PF 82% 2×2 + 18% 3×3
        head_size = (2, 2) if rng.random() < 0.82 else (3, 3)

        # 머리 anchor 후보 — 비-메타포 영역 우선
        non_meta = compute_non_metaphor_cells(clusters)
        head_candidates = [c for c in non_meta
                           if c not in used and 0 <= c[0] < field_h - head_size[0]
                           and 0 <= c[1] < field_w - head_size[1]]
        if not head_candidates:
            head_candidates = [c for c in available_cells
                               if 0 <= c[0] < field_h - head_size[0]
                               and 0 <= c[1] < field_w - head_size[1]]
        if not head_candidates:
            continue
        # score-based pick (Snake 는 PF Y 상단 58% 편중)
        scored = score_placement_candidates(head_candidates, "Snake", field_h, field_w)
        head_anchor = scored[0][0] if scored else head_candidates[0]

        head_cells = _rect_cells(head_anchor, head_size)
        if any((r, c) in used or not (0 <= r < field_h and 0 <= c < field_w)
               for r, c in head_cells):
            continue

        # 몸 마디 수: PF 빈도 (mode 4, med 8)
        body_n_options = [2, 4, 7, 8, 10, 14, 32]
        body_weights = [0.13, 0.16, 0.13, 0.13, 0.08, 0.06, 0.05]
        body_n = body_n_options[_weighted_choice(body_n_options, body_weights, rng)]

        # 몸 walk
        used_for_snake = set(head_cells)
        body_segments = grow_snake_body_segments(
            head_anchor, head_size, body_n,
            available_cells, used_for_snake, rng,
            field_h, field_w,
        )
        # 색 결정 — 우세 색 (cluster centroid 셀의 색)
        cr, cc = head_anchor
        color = field_map[cr][cc] if 0 <= cr < field_h and 0 <= cc < field_w else 1

        # HP 결정 (v1.2.14 intent)
        total_cells_snake = len(head_cells) + sum(len(s) for s in body_segments)
        hp = snake_hp_from_cells(total_cells_snake, intent, rng)

        # used 갱신
        all_cells = list(head_cells)
        for seg in body_segments:
            all_cells.extend(seg)
        used.update(all_cells)

        result.append({
            "type": "Snake",
            "main_grid_points": [list(c) for c in head_cells],
            "snake_grid_points": [[list(c) for c in seg] for seg in body_segments],
            "cells": all_cells,
            "head_size": list(head_size),
            "n_segments": len(body_segments),
            "color": color,
            "material": color,
            "count": hp,
            "life": hp,
            "intent": intent,
        })
    return result


'''

# Insert helpers after barricade_length_v2
INSERT_AFTER = '''def barricade_length_v2(difficulty: str, rng: random.Random) -> int:'''

# Update BL_DEBUT_LV — add gimmick_snake
OLD_DEBUT_LV = '''BL_DEBUT_LV = {
    "gimmick_hidden":      11,    # Hidden Dart Box (큐)
    "gimmick_chain":       21,    # Linked Dart Box (큐)
    "gimmick_pinata":      31,    # Wooden Board (필드)
    "gimmick_glass_pipe":  41,    # Glass Pipe (큐)
    "gimmick_pin":         61,    # Barricade (필드)
    "gimmick_lock_key":    81,    # Lock & Key (1.0 SKIP)
    "gimmick_surprise":   101,    # Hidden Balloon (필드)
    "gimmick_wall":       121,    # Iron Wall (필드)
    "gimmick_spawner_o":  141,    # Pipe (큐)
    "gimmick_pinata_box": 161,    # Target Box (필드)
    "gimmick_ice":        201,    # Frozen Layer (필드)
    "gimmick_frozen_dart":241,    # Frozen Dart Box (큐)
    "gimmick_curtain":    301,    # Color Curtain (1.1+)
}'''

NEW_DEBUT_LV = '''BL_DEBUT_LV = {
    "gimmick_hidden":      11,    # Hidden Dart Box (큐)
    "gimmick_chain":       21,    # Linked Dart Box (큐)
    "gimmick_pinata":      31,    # Wooden Board (필드)
    "gimmick_glass_pipe":  41,    # Glass Pipe (큐)
    "gimmick_pin":         61,    # Barricade (필드)
    "gimmick_lock_key":    81,    # Lock & Key (보류, Snake 대체 후보)
    "gimmick_snake":       81,    # v1.2.10/20 Snake — Lock&Key 대체 (TBD PO)
    "gimmick_surprise":   101,    # Hidden Balloon (필드)
    "gimmick_wall":       121,    # Iron Wall (필드)
    "gimmick_spawner_o":  141,    # Pipe (큐)
    "gimmick_pinata_box": 161,    # Target Box (필드)
    "gimmick_ice":        201,    # Frozen Layer (필드)
    "gimmick_frozen_dart":241,    # Frozen Dart Box (큐)
    "gimmick_curtain":    301,    # Color Curtain (1.1+)
}'''

# Update FIELD_GIMMICKS — add Snake
OLD_FIELD_GIM = '''FIELD_GIMMICKS = {
    "gimmick_pinata":     "Wooden_Board",
    "gimmick_pin":        "Barricade",
    "gimmick_surprise":   "Hidden_Balloon",
    "gimmick_wall":       "Iron_Wall",
    "gimmick_pinata_box": "Target_Box",
    "gimmick_ice":        "Frozen_Layer",
    # "gimmick_curtain":  "Color_Curtain",  # 1.1+
}'''

NEW_FIELD_GIM = '''FIELD_GIMMICKS = {
    "gimmick_pinata":     "Wooden_Board",
    "gimmick_pin":        "Barricade",
    "gimmick_snake":      "Snake",         # v1.2.10/20 신규
    "gimmick_surprise":   "Hidden_Balloon",
    "gimmick_wall":       "Iron_Wall",
    "gimmick_pinata_box": "Target_Box",
    "gimmick_ice":        "Frozen_Layer",
    # "gimmick_curtain":  "Color_Curtain",  # 1.1+
}'''

# Update INT_FIELDS to include gimmick_snake
OLD_INT_FIELDS = '''    "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_glass_pipe",
    "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
    "gimmick_spawner_o", "gimmick_spawner_t", "gimmick_pinata_box",
    "gimmick_ice", "gimmick_frozen_dart", "gimmick_curtain",
}'''

NEW_INT_FIELDS = '''    "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_glass_pipe",
    "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
    "gimmick_spawner_o", "gimmick_spawner_t", "gimmick_pinata_box",
    "gimmick_ice", "gimmick_frozen_dart", "gimmick_curtain",
    "gimmick_snake",  # v1.2.10/20 신규
}'''

# Update Barricade caller to use HP intent
OLD_BR_CALL = '''        # v1.2.6 §7.7.6 난이도별 단조 증가 length
        length = barricade_length_v2(purpose_type, rng)'''

NEW_BR_CALL = '''        # v1.2.6 §7.7.6 난이도별 단조 증가 length
        length = barricade_length_v2(purpose_type, rng)
        # v1.2.14 HP × Length 독립 — intent 매핑 (purpose → fast/normal/slow/boss)
        _br_intent = difficulty_to_intent(purpose_type, "Barricade")'''

OLD_BR_RESULT = '''        result.append({
            "type": "Barricade",
            "row": cells[0][0], "col": cells[0][1],
            "cells": cells,
            "length": len(cells),
            "life": len(cells),  # BL 1-dart/cell 모델 — life = length
        })'''

NEW_BR_RESULT = '''        # v1.2.14: HP 는 length 와 독립 — intent 로 ratio 결정
        _br_hp = barricade_hp_from_length(len(cells), _br_intent, rng)
        result.append({
            "type": "Barricade",
            "row": cells[0][0], "col": cells[0][1],
            "cells": cells,
            "length": len(cells),
            "life": _br_hp,
            "intent": _br_intent,
        })'''

# Update track_b — add snake call between Barricade and the end
OLD_TRACK_B_BR = '''    # 6. Barricade (gimmick_pin) — buffer 1
    cnt = int(csv_row.get("gimmick_pin", 0))
    if cnt > 0 and lv >= BL_DEBUT_LV["gimmick_pin"]:
        purpose = normalize_purpose(csv_row.get("purpose_type"))
        ba = place_barricade(clusters, cnt, used_cells, rng,
                              purpose_type=purpose, field_h=field_h, field_w=field_w)
        gimmicks.extend(ba)
        _expand_used_with_buffer(ba, used_cells, buffer=1)

    return gimmicks'''

NEW_TRACK_B_BR = '''    # 6. Barricade (gimmick_pin) — buffer 1
    cnt = int(csv_row.get("gimmick_pin", 0))
    if cnt > 0 and lv >= BL_DEBUT_LV["gimmick_pin"]:
        purpose = normalize_purpose(csv_row.get("purpose_type"))
        ba = place_barricade(clusters, cnt, used_cells, rng,
                              purpose_type=purpose, field_h=field_h, field_w=field_w)
        gimmicks.extend(ba)
        _expand_used_with_buffer(ba, used_cells, buffer=1)

    # 7. v1.2.10/20 Snake (gimmick_snake) — debut lv 81, buffer 1
    cnt = int(csv_row.get("gimmick_snake", 0))
    if cnt > 0 and lv >= BL_DEBUT_LV["gimmick_snake"]:
        sn = place_snake(clusters, cnt, csv_row, used_cells, rng,
                          field_h=field_h, field_w=field_w, field_map=field_map)
        gimmicks.extend(sn)
        _expand_used_with_buffer(sn, used_cells, buffer=1)

    return gimmicks'''


PATCHES = [
    (INSERT_AFTER, INSERT_AFTER + HELPERS.replace("def barricade_length_v2", "def __dummy_for_anchor"),
     "WILL DO INSERTION SEPARATELY"),
    (OLD_DEBUT_LV, NEW_DEBUT_LV, "BL_DEBUT_LV add gimmick_snake"),
    (OLD_FIELD_GIM, NEW_FIELD_GIM, "FIELD_GIMMICKS add Snake"),
    (OLD_INT_FIELDS, NEW_INT_FIELDS, "INT_FIELDS add gimmick_snake"),
    (OLD_BR_CALL, NEW_BR_CALL, "barricade intent setup"),
    (OLD_BR_RESULT, NEW_BR_RESULT, "barricade HP from intent"),
    (OLD_TRACK_B_BR, NEW_TRACK_B_BR, "track_b snake call"),
]


def main():
    with open(PATH, encoding="utf-8") as f:
        src = f.read()
    if "place_snake" in src:
        print("already patched (place_snake exists). abort.")
        sys.exit(0)

    # Insert HELPERS after barricade_length_v2 function block
    # barricade_length_v2 is a multi-line function — find its end (next blank line + def or ── comment)
    bl_marker = "def barricade_length_v2(difficulty: str, rng: random.Random) -> int:"
    if bl_marker not in src:
        print("ABORT: barricade_length_v2 marker missing", file=sys.stderr); sys.exit(1)
    idx = src.find(bl_marker)
    # Find function end — next top-level "def " or "# ──" after this
    rest = src[idx + len(bl_marker):]
    end_match = None
    for marker in ["\n\ndef ", "\n\n# ──", "\n\nPALETTE", "\n\nclass "]:
        i = rest.find(marker)
        if i >= 0 and (end_match is None or i < end_match):
            end_match = i
    if end_match is None:
        print("ABORT: cannot find end of barricade_length_v2"); sys.exit(1)
    end_pos = idx + len(bl_marker) + end_match
    src = src[:end_pos] + "\n\n" + HELPERS + src[end_pos:]

    # Apply non-insertion patches
    for old, new, lbl in PATCHES[1:]:
        if old not in src:
            print(f"ABORT — pattern not found: {lbl}", file=sys.stderr); sys.exit(1)
        src = src.replace(old, new, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("patched ok")


if __name__ == "__main__":
    main()
