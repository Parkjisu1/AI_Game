"""
Build Fingerprint DB
====================
Parses PixelFlow gameplay screenshots into board-state fingerprints
with associated player actions and deltas.

Usage:
    python build_fingerprint_db.py [--limit N] [--workers 1]

Output: E:/AI/virtual_player/data/pixelflow/db/fingerprint.db
"""

import argparse
import json
import math
import os
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

# ── Paths ────────────────────────────────────────────────────────
IMAGE_DIR = Path("F:/LevelDesignExtractor/pixelflow")
STREAM_DB = Path("E:/AI/virtual_player/data/pixelflow/db/stream.db")
SESSION_LOG = Path("E:/AI/virtual_player/data/pixelflow/db/session_log.jsonl")
PROFILE_PATH = Path("E:/AI/virtual_player/data/pixelflow/profile/cell_profile.json")
OUTPUT_DB = Path("E:/AI/virtual_player/data/pixelflow/db/fingerprint.db")

# ── Board crop (1080x1920 portrait) ─────────────────────────────
BOARD_Y0, BOARD_Y1 = 150, 815
BOARD_X0, BOARD_X1 = 170, 905

# ── Grid margins (frame exclusion) ──────────────────────────────
MARGIN_TOP = 2
MARGIN_BOTTOM = 2
MARGIN_LEFT = 2
MARGIN_RIGHT = 5

# ── Non-tile color IDs (frame/background/conveyor) ──────────────
NON_TILE_COLORS = {7, 8, 9, 15, 21, 23, 24, 28}

# ── Coordinate transform: mouse -> ADB ──────────────────────────
ADB_SCALE_X = 1.778
ADB_OFFSET_X = 60
ADB_SCALE_Y = 1.613


# ═══════════════════════════════════════════════════════════════
#  Import board parsing functions from cell_aware_analyzer
# ═══════════════════════════════════════════════════════════════

# Add tools directory to path for import
_tools_dir = str(Path(__file__).resolve().parent)
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from cell_aware_analyzer import (
    build_render_palette,
    cc_smooth,
    extract_cell_colors,
    load_profile,
)


def init_output_db(db_path: Path) -> sqlite3.Connection:
    """Create fingerprint.db with schema if it doesn't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS board_state (
            state_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            file_name   TEXT UNIQUE,
            timestamp   TEXT,
            total_cells INTEGER,
            num_colors  INTEGER,
            color_vector TEXT,
            fingerprint TEXT,
            action_x    INTEGER,
            action_y    INTEGER,
            action_type TEXT,
            delta_cells REAL,
            after_file  TEXT,
            episode_id  INTEGER,
            session_outcome TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_fingerprint_cells
        ON board_state(total_cells, num_colors)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_episode
        ON board_state(episode_id)
    """)
    conn.commit()
    return conn


def load_session_log(log_path: Path) -> dict:
    """Load session_log.jsonl -> {before_file: action_info}."""
    action_map = {}
    episode_outcomes = {}

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Track episode events (no clear/fail in current data,
            # but keep the structure for future enrichment)
            if d.get("event") == "episode_end":
                eid = d.get("episode_id")
                if eid is not None:
                    episode_outcomes[eid] = d.get("outcome")  # None for now
                continue

            # Action entries
            if d.get("action") in ("tap", "swipe") and "file" in d:
                action_map[d["file"]] = {
                    "x": d.get("x"),
                    "y": d.get("y"),
                    "action": d["action"],
                    "after_file": d.get("after_file"),
                    "episode_id": d.get("episode_id"),
                    "timestamp": d.get("timestamp"),
                    "delta_from_prev": d.get("delta_from_prev"),
                }

    return action_map, episode_outcomes


def get_gameplay_before_files(stream_db_path: Path) -> list:
    """Query stream.db for gameplay before-image filenames."""
    conn = sqlite3.connect(str(stream_db_path))
    cur = conn.execute(
        "SELECT file_name FROM frame_record "
        "WHERE screen_type='gameplay' AND file_name LIKE '%_before%' "
        "ORDER BY file_name"
    )
    files = [row[0] for row in cur]
    conn.close()
    return files


def get_already_processed(out_conn: sqlite3.Connection) -> set:
    """Return set of file_names already in fingerprint.db."""
    cur = out_conn.execute("SELECT file_name FROM board_state")
    return {row[0] for row in cur}


def parse_board(img_path: Path, profile, pal_keys, pal_arr):
    """Parse a single image -> (color_counts, total_cells, num_colors).

    Returns None if image cannot be read.
    """
    img = cv2.imread(str(img_path))
    if img is None:
        return None

    # Crop board region
    board_bgr = img[BOARD_Y0:BOARD_Y1, BOARD_X0:BOARD_X1]
    board_rgb = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2RGB)

    # Extract cell grid
    grid = extract_cell_colors(board_rgb, profile, pal_keys, pal_arr)
    grid = cc_smooth(grid, min_size=3)

    # Count tile colors (excluding non-tile and frame margins)
    rows = profile["grid"]["rows"]
    cols = profile["grid"]["cols"]
    color_counts = Counter()

    row_end = rows - MARGIN_BOTTOM
    col_end = cols - MARGIN_RIGHT

    for r in range(MARGIN_TOP, row_end):
        for c in range(MARGIN_LEFT, col_end):
            cid = grid[r][c]
            if cid not in NON_TILE_COLORS:
                color_counts[cid] += 1

    total = sum(color_counts.values())
    num_colors = len(color_counts)

    return color_counts, total, num_colors


def make_fingerprint(color_counts: Counter, total: int) -> list:
    """Build 29-dim L2-normalized fingerprint vector."""
    fp = [0.0] * 29
    if total > 0:
        for cid, cnt in color_counts.items():
            if 1 <= cid <= 29:
                fp[cid - 1] = cnt / total

    # L2 normalize
    norm = math.sqrt(sum(v * v for v in fp))
    if norm > 0:
        fp = [v / norm for v in fp]

    return fp


def mouse_to_adb(mx, my):
    """Convert ClickCapture mouse coords to ADB coords."""
    if mx is None or my is None:
        return None, None
    adb_x = int(ADB_SCALE_X * mx + ADB_OFFSET_X)
    adb_y = int(ADB_SCALE_Y * my)
    return adb_x, adb_y


def process_batch(
    files: list,
    action_map: dict,
    episode_outcomes: dict,
    profile: dict,
    pal_keys,
    pal_arr,
    out_conn: sqlite3.Connection,
    commit_every: int = 100,
):
    """Process a list of before-image files and insert into DB."""
    total_files = len(files)
    processed = 0
    skipped = 0
    errors = 0
    t0 = time.time()

    for i, fn in enumerate(files):
        img_path = IMAGE_DIR / fn

        if not img_path.exists():
            skipped += 1
            continue

        try:
            result = parse_board(img_path, profile, pal_keys, pal_arr)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  [ERROR] {fn}: {e}")
            continue

        if result is None:
            skipped += 1
            continue

        color_counts, total_cells, num_colors = result
        fp = make_fingerprint(color_counts, total_cells)

        # Color vector as dict {cid: count}
        color_vector = {str(k): v for k, v in sorted(color_counts.items())}

        # Action info
        action = action_map.get(fn, {})
        mx = action.get("x")
        my = action.get("y")
        adb_x, adb_y = mouse_to_adb(mx, my)
        action_type = action.get("action")
        after_file = action.get("after_file")
        episode_id = action.get("episode_id")
        timestamp = action.get("timestamp")
        delta_from_prev = action.get("delta_from_prev")

        # Session outcome (currently None in data)
        outcome = episode_outcomes.get(episode_id) if episode_id else None

        try:
            out_conn.execute(
                """INSERT OR IGNORE INTO board_state
                   (file_name, timestamp, total_cells, num_colors,
                    color_vector, fingerprint,
                    action_x, action_y, action_type,
                    delta_cells, after_file,
                    episode_id, session_outcome)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    fn,
                    timestamp,
                    total_cells,
                    num_colors,
                    json.dumps(color_vector),
                    json.dumps([round(v, 6) for v in fp]),
                    adb_x,
                    adb_y,
                    action_type,
                    delta_from_prev,
                    after_file,
                    episode_id,
                    outcome,
                ),
            )
            processed += 1
        except sqlite3.IntegrityError:
            # Already exists (shouldn't happen with INSERT OR IGNORE)
            pass

        # Progress
        done = i + 1
        if done % commit_every == 0 or done == total_files:
            out_conn.commit()
            elapsed = time.time() - t0
            rate = done / elapsed if elapsed > 0 else 0
            eta_sec = (total_files - done) / rate if rate > 0 else 0
            eta_min = eta_sec / 60
            print(
                f"  [{done}/{total_files}] "
                f"processed={processed} skipped={skipped} errors={errors} "
                f"rate={rate:.1f} img/s  ETA={eta_min:.1f}min"
            )

    out_conn.commit()
    elapsed = time.time() - t0
    print(
        f"\nDone: {processed} inserted, {skipped} skipped, {errors} errors "
        f"in {elapsed:.1f}s ({elapsed/60:.1f}min)"
    )
    return processed


def main():
    parser = argparse.ArgumentParser(
        description="Build fingerprint DB from PixelFlow gameplay screenshots"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limit number of images to process (0=all)"
    )
    parser.add_argument(
        "--workers", type=int, default=1,
        help="Number of workers (reserved for future multiprocessing)"
    )
    parser.add_argument(
        "--commit-every", type=int, default=100,
        help="Commit and report progress every N images"
    )
    args = parser.parse_args()

    # 1. Load profile
    print(f"Loading cell profile: {PROFILE_PATH}")
    profile = load_profile(str(PROFILE_PATH))
    pal_keys, pal_arr = build_render_palette(profile)
    print(f"  Palette: {len(pal_keys)} colors (render palette)")

    # 2. Load session log
    print(f"Loading session log: {SESSION_LOG}")
    action_map, episode_outcomes = load_session_log(SESSION_LOG)
    print(f"  Actions: {len(action_map)} entries, Episodes: {len(episode_outcomes)}")

    # 3. Get gameplay before files from stream.db
    print(f"Querying gameplay files from: {STREAM_DB}")
    gameplay_files = get_gameplay_before_files(STREAM_DB)
    print(f"  Gameplay before images: {len(gameplay_files)}")

    # 4. Filter already processed
    print(f"Opening output DB: {OUTPUT_DB}")
    out_conn = init_output_db(OUTPUT_DB)
    already = get_already_processed(out_conn)
    remaining = [f for f in gameplay_files if f not in already]
    print(f"  Already processed: {len(already)}, Remaining: {len(remaining)}")

    if args.limit > 0:
        remaining = remaining[: args.limit]
        print(f"  Limited to: {len(remaining)}")

    if not remaining:
        print("Nothing to process.")
        out_conn.close()
        return

    # 5. Process
    print(f"\nProcessing {len(remaining)} images...")
    process_batch(
        remaining,
        action_map,
        episode_outcomes,
        profile,
        pal_keys,
        pal_arr,
        out_conn,
        commit_every=args.commit_every,
    )

    # 6. Summary stats
    cur = out_conn.execute("SELECT COUNT(*) FROM board_state")
    total_rows = cur.fetchone()[0]
    cur = out_conn.execute(
        "SELECT COUNT(*) FROM board_state WHERE action_x IS NOT NULL"
    )
    with_action = cur.fetchone()[0]
    cur = out_conn.execute("SELECT COUNT(DISTINCT episode_id) FROM board_state")
    episodes = cur.fetchone()[0]
    cur = out_conn.execute(
        "SELECT AVG(total_cells), AVG(num_colors) FROM board_state"
    )
    avg_cells, avg_colors = cur.fetchone()

    print(f"\n=== Fingerprint DB Summary ===")
    print(f"  Total rows:       {total_rows}")
    print(f"  With action:      {with_action}")
    print(f"  Episodes:         {episodes}")
    print(f"  Avg tile cells:   {avg_cells:.1f}")
    print(f"  Avg color count:  {avg_colors:.1f}")
    print(f"  DB path:          {OUTPUT_DB}")

    out_conn.close()


if __name__ == "__main__":
    main()
