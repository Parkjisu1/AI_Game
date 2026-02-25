"""
Tap Shift: Arrow Escape Puzzle - Level Generator
Generates 100 solvable levels with guaranteed validity using DFS/backtracking.
"""

import json
import os
import random

OUTPUT_DIR = r"E:\ShiftTap\My project\Assets\Resources\Levels"

UP = 0
DOWN = 1
LEFT = 2
RIGHT = 3

DIR_NAMES = {0: "Up", 1: "Down", 2: "Left", 3: "Right"}

DIR_VECTORS = {
    UP: (0, 1),
    DOWN: (0, -1),
    LEFT: (-1, 0),
    RIGHT: (1, 0),
}


def can_remove_arrow(arrow, occupied, grid_width, grid_height):
    x, y, d = arrow
    dx, dy = DIR_VECTORS[d]
    cx, cy = x + dx, y + dy
    while 0 <= cx < grid_width and 0 <= cy < grid_height:
        if (cx, cy) in occupied:
            return False
        cx += dx
        cy += dy
    return True


def is_solvable(arrows, grid_width, grid_height):
    if not arrows:
        return True
    occupied = set((a[0], a[1]) for a in arrows)
    for i, arrow in enumerate(arrows):
        if can_remove_arrow(arrow, occupied - {(arrow[0], arrow[1])}, grid_width, grid_height):
            remaining = arrows[:i] + arrows[i+1:]
            if is_solvable(remaining, grid_width, grid_height):
                return True
    return False


def find_solution_order(arrows, grid_width, grid_height):
    if not arrows:
        return []
    occupied = set((a[0], a[1]) for a in arrows)
    for i, arrow in enumerate(arrows):
        if can_remove_arrow(arrow, occupied - {(arrow[0], arrow[1])}, grid_width, grid_height):
            remaining = arrows[:i] + arrows[i+1:]
            sub_order = find_solution_order(remaining, grid_width, grid_height)
            if sub_order is not None:
                return [arrow] + sub_order
    return None


def generate_solvable_level(grid_width, grid_height, num_arrows, max_attempts=2000):
    for attempt in range(max_attempts):
        arrows = []
        occupied = set()
        all_cells = [(x, y) for x in range(grid_width) for y in range(grid_height)]
        success = True
        for step in range(num_arrows):
            random.shuffle(all_cells)
            candidates = []
            for cell in all_cells:
                if cell in occupied:
                    continue
                for d in [UP, DOWN, LEFT, RIGHT]:
                    ac = (cell[0], cell[1], d)
                    if can_remove_arrow(ac, occupied, grid_width, grid_height):
                        candidates.append(ac)
            if not candidates:
                success = False
                break
            chosen = random.choice(candidates)
            arrows.append(chosen)
            occupied.add((chosen[0], chosen[1]))
        if success and len(arrows) == num_arrows:
            if is_solvable(arrows, grid_width, grid_height):
                return arrows
    for attempt in range(max_attempts * 2):
        all_cells = [(x, y) for x in range(grid_width) for y in range(grid_height)]
        random.shuffle(all_cells)
        if len(all_cells) < num_arrows:
            return None
        selected = all_cells[:num_arrows]
        dirs = [random.randint(0, 3) for _ in range(num_arrows)]
        arrows = [(c[0], c[1], dirs[i]) for i, c in enumerate(selected)]
        if is_solvable(arrows, grid_width, grid_height):
            return arrows
    return None


def generate_tutorial_level(level_id):
    if level_id == 1:
        return {"gridWidth": 3, "gridHeight": 3, "arrows": [(1, 1, RIGHT)]}
    elif level_id == 2:
        return {"gridWidth": 3, "gridHeight": 3, "arrows": [(0, 0, DOWN), (2, 2, UP)]}
    elif level_id == 3:
        return {"gridWidth": 3, "gridHeight": 3, "arrows": [(0, 1, RIGHT), (1, 1, RIGHT), (2, 1, RIGHT)]}


def get_level_params(level_id):
    if level_id <= 3:
        return None
    if level_id <= 20:
        progress = (level_id - 4) / 16.0
        if progress < 0.4:
            gw, gh = 3, 3
        elif progress < 0.7:
            gw, gh = 3, 4
        else:
            gw, gh = 4, 4
        num = 3 + int(progress * 3)
        num = max(3, min(6, num))
    elif level_id <= 50:
        progress = (level_id - 21) / 29.0
        if progress < 0.3:
            gw, gh = 4, 4
        elif progress < 0.6:
            gw, gh = 4, 5
        else:
            gw, gh = 5, 5
        num = 6 + int(progress * 4)
        num = max(6, min(10, num))
    else:
        progress = (level_id - 51) / 49.0
        if progress < 0.3:
            gw, gh = 5, 5
        elif progress < 0.6:
            gw, gh = 5, 6
        else:
            gw, gh = 6, 6
        num = 10 + int(progress * 5)
        num = max(10, min(15, num))
    num = min(num, gw * gh)
    return (gw, gh, num)


def arrows_to_json(level_id, grid_width, grid_height, arrows):
    arrow_list = [{"x": x, "y": y, "direction": d} for (x, y, d) in arrows]
    return {
        "levelId": level_id,
        "gridWidth": grid_width,
        "gridHeight": grid_height,
        "arrows": arrow_list,
        "par": len(arrows),
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    random.seed(42)
    total = 0
    failed = []
    for lid in range(1, 101):
        if lid <= 3:
            data = generate_tutorial_level(lid)
            gw, gh = data["gridWidth"], data["gridHeight"]
            arrows = data["arrows"]
        else:
            params = get_level_params(lid)
            gw, gh, na = params
            arrows = generate_solvable_level(gw, gh, na)
            if arrows is None:
                print(f"FAILED level {lid} ({gw}x{gh}, {na} arrows)")
                failed.append(lid)
                continue
        if not is_solvable(arrows, gw, gh):
            print(f"ERROR: Level {lid} failed verification!")
            failed.append(lid)
            continue
        solution = find_solution_order(arrows, gw, gh)
        lj = arrows_to_json(lid, gw, gh, arrows)
        fn = f"level_{lid:03d}.json"
        fp = os.path.join(OUTPUT_DIR, fn)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(lj, f, indent=2)
        total += 1
        tier = "Tutorial" if lid <= 3 else "Easy" if lid <= 20 else "Medium" if lid <= 50 else "Hard"
        ss = " -> ".join([f"({a[0]},{a[1]},{DIR_NAMES[a[2]]})" for a in solution]) if solution else "N/A"
        print(f"[{tier:8s}] Level {lid:3d}: {gw}x{gh}, {len(arrows):2d} arrows | Solution: {ss}")
    print()
    print("=" * 60)
    print(f"Generated {total}/100 levels.")
    if failed:
        print(f"Failed: {failed}")
    else:
        print("All 100 levels generated and verified solvable!")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
