"""
Update fingerprint.db with After-image board parsing.
Computes actual cell delta (before_cells - after_cells) per color.

Adds columns:
  after_total_cells  — total tile cells in After image
  after_color_vector — JSON color counts after tap
  real_delta         — after_total - before_total (negative = progress)
  color_delta        — JSON per-color change {"1": -40, "6": 0, ...}
"""

import json
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cell_aware_analyzer import (
    build_render_palette, extract_cell_colors, cc_smooth, load_profile,
)

# Paths
FINGERPRINT_DB = Path("E:/AI/virtual_player/data/pixelflow/db/fingerprint.db")
CELL_PROFILE = Path("E:/AI/virtual_player/data/pixelflow/profile/cell_profile.json")
IMAGES_DIR = Path("F:/LevelDesignExtractor/pixelflow")

# Board crop (portrait 1080x1920)
BOARD_Y1, BOARD_Y2 = 150, 815
BOARD_X1, BOARD_X2 = 170, 905

NON_TILE_COLORS = {7, 8, 9, 15, 21, 23, 24, 28}


def parse_board(img_path, profile, pal_keys, pal_arr):
    """Parse board from image, return color counts dict."""
    img = cv2.imread(str(img_path))
    if img is None:
        return None

    board = img[BOARD_Y1:BOARD_Y2, BOARD_X1:BOARD_X2]
    board_rgb = cv2.cvtColor(board, cv2.COLOR_BGR2RGB)
    grid = extract_cell_colors(board_rgb, profile, pal_keys, pal_arr)
    grid = cc_smooth(grid, min_size=3)

    fr = profile.get("ignore_elements", {}).get("frame", {})
    top = fr.get("top_rows", 2)
    bot = fr.get("bottom_rows", 2)
    left = fr.get("left_cols", 2)
    right = fr.get("right_cols", 5)
    rows = profile["grid"]["rows"]
    cols = profile["grid"]["cols"]

    counts = Counter()
    for r in range(top, rows - bot):
        for c in range(left, cols - right):
            cid = grid[r][c]
            if cid not in NON_TILE_COLORS:
                counts[cid] += 1

    return dict(counts)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    print(f"Loading cell profile: {CELL_PROFILE}")
    profile = load_profile(str(CELL_PROFILE))
    pal_keys, pal_arr = build_render_palette(profile)
    print(f"  Palette: {len(pal_keys)} colors")

    conn = sqlite3.connect(str(FINGERPRINT_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Add columns if not exist
    existing = [r[1] for r in conn.execute("PRAGMA table_info(board_state)")]
    for col, typ in [
        ("after_total_cells", "INTEGER"),
        ("after_color_vector", "TEXT"),
        ("real_delta", "INTEGER"),
        ("color_delta", "TEXT"),
    ]:
        if col not in existing:
            conn.execute(f"ALTER TABLE board_state ADD COLUMN {col} {typ}")
            print(f"  Added column: {col}")
    conn.commit()

    # Get rows that need After parsing
    rows = conn.execute("""
        SELECT state_id, file_name, after_file, color_vector, total_cells
        FROM board_state
        WHERE after_file IS NOT NULL AND after_file != ''
          AND real_delta IS NULL
        ORDER BY state_id
    """).fetchall()

    total = len(rows)
    if args.limit > 0:
        rows = rows[:args.limit]
        print(f"  Limited to {args.limit} of {total}")

    print(f"Processing {len(rows)} After images...")
    t0 = time.time()
    processed = 0
    errors = 0

    for i, row in enumerate(rows):
        after_path = IMAGES_DIR / row["after_file"]
        if not after_path.exists():
            errors += 1
            continue

        after_counts = parse_board(after_path, profile, pal_keys, pal_arr)
        if after_counts is None:
            errors += 1
            continue

        after_total = sum(after_counts.values())
        before_total = row["total_cells"]
        real_delta = after_total - before_total

        # Per-color delta
        before_counts = json.loads(row["color_vector"]) if row["color_vector"] else {}
        all_colors = set(before_counts.keys()) | set(str(k) for k in after_counts.keys())
        color_delta = {}
        for cid in all_colors:
            before_val = before_counts.get(cid, before_counts.get(str(cid), 0))
            after_val = after_counts.get(int(cid), 0)
            diff = after_val - before_val
            if diff != 0:
                color_delta[str(cid)] = diff

        conn.execute("""
            UPDATE board_state SET
                after_total_cells = ?,
                after_color_vector = ?,
                real_delta = ?,
                color_delta = ?
            WHERE state_id = ?
        """, (
            after_total,
            json.dumps({str(k): v for k, v in after_counts.items()}),
            real_delta,
            json.dumps(color_delta),
            row["state_id"],
        ))

        processed += 1
        if (i + 1) % 100 == 0:
            conn.commit()
            elapsed = time.time() - t0
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = (len(rows) - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{len(rows)}] processed={processed} errors={errors} "
                  f"rate={rate:.1f}/s ETA={remaining/60:.1f}min")

    conn.commit()
    elapsed = time.time() - t0
    print(f"\nDone: {processed} updated, {errors} errors in {elapsed:.0f}s ({elapsed/60:.1f}min)")

    # Summary
    stats = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN real_delta < 0 THEN 1 ELSE 0 END) as progress,
            SUM(CASE WHEN real_delta = 0 THEN 1 ELSE 0 END) as no_change,
            SUM(CASE WHEN real_delta > 0 THEN 1 ELSE 0 END) as regression,
            AVG(real_delta) as avg_delta
        FROM board_state WHERE real_delta IS NOT NULL
    """).fetchone()
    print(f"\n=== Delta Summary ===")
    print(f"  Progress (delta<0): {stats[1]}")
    print(f"  No change (delta=0): {stats[2]}")
    print(f"  Regression (delta>0): {stats[3]}")
    print(f"  Avg delta: {stats[4]:.1f}")

    conn.close()


if __name__ == "__main__":
    main()
