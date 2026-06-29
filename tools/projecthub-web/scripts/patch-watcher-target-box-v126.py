#!/usr/bin/env python3
"""Patch place_target_box to use target_box_size_v2 (v1.2.6 §7.7.5)."""
import sys
PATH = "/home/aimed/.hermes/watcher/field_complete_levels.py"

OLD = '''    # box_size by purpose
    box_size_map = {
        "tutorial": (2, 2),
        "rest":     (2, 2),
        "normal":   (2, 3),
        "hard":     (2, 3),
        "super_hard": (3, 3),
    }
    box_size = box_size_map.get(purpose_type, (2, 3))
    # eggs/box: 78% have 4, 22% have 6
    target_count = 6 if rng.random() < 0.22 else 4'''

NEW = '''    # v1.2.6 §7.7.5: 난이도별 (box_size, eggs) 동시 결정
    # tutorial 2×2/4 → super_hard 3×3/9 단조 증가
    _diff = normalize_purpose(purpose_type)
    box_size, target_count = target_box_size_v2(_diff, rng)'''

def main():
    with open(PATH, encoding="utf-8") as f:
        src = f.read()
    if "target_box_size_v2(_diff" in src:
        print("already patched. abort.")
        return
    if OLD not in src:
        print("OLD pattern not found", file=sys.stderr); sys.exit(1)
    src = src.replace(OLD, NEW, 1)
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("target_box patched ok")

if __name__ == "__main__":
    main()
