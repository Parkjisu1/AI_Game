"""
Smart Player — Pixel Flow (v3 Fingerprint)
=============================================
Vision-based autonomous player for Pixel Flow.

Architecture:
  1. ADB screenshot
  2. YOLO screen classification (gameplay / lobby / win / fail / popup / loading)
  3. Non-gameplay → playbook handler (lobby→play, win→continue, fail→retry)
  4. Gameplay:
     a. Board parse → color distribution → 29-dim fingerprint
     b. Search fingerprint.db for cosine-similar past human board states
     c. Pick best match: delta < 0 (progress) preferred, similarity > 0.7
     d. Execute human's action_x, action_y (already ADB coordinates)
     e. Fallback: round-robin pig tap if no good fingerprint match
     f. Exploration mode (stall 5+): fingerprint first, then AI DB/PlayDB/zones

Key features:
  - Fingerprint DB: ~7700 human gameplay states with board fingerprints + actions
  - Cosine similarity search (vectorized numpy, ~900KB in memory)
  - Progress-aware: prefers actions where human achieved delta_cells < 0
  - Graceful fallback: FP match → explore DB → PlayDB → round-robin

Dependencies:
  - cell_aware_analyzer.py (board parsing)
  - decision_pixelflow.py (detect_queue_pigs — pig position via white text clusters)
  - playbook_pixelflow.py (screen handlers)
  - YOLO model (screen classification)
  - cell_profile.json (color palette + render ranges)
  - fingerprint.db (human gameplay fingerprint database)
"""

import argparse
import concurrent.futures
import json
import sqlite3
import subprocess
import sys
import time
import uuid
from collections import Counter, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Path setup for imports
# ---------------------------------------------------------------------------
_TOOLS_DIR = Path("E:/AI/virtual_player/tools")
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from cell_aware_analyzer import (
    build_render_palette,
    extract_cell_colors,
    cc_smooth,
    classify_pixel,
    load_profile,
    COLOR_NAMES,
    PALETTE_29,
)
from virtual_player.tester.decision_pixelflow import detect_queue_pigs
from virtual_player.tester.playbook_pixelflow import create_pixelflow_playbook
from virtual_player.tester.playbook import Action


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
SERIAL = "emulator-5554"
PACKAGE = "com.loomgames.pixelflow"
ACTIVITY = "com.unity3d.player.UnityPlayerActivity"

CELL_PROFILE_PATH = Path(
    "E:/AI/virtual_player/data/journal/games/pixelflow/cell_profile.json"
)
YOLO_MODEL_PATH = Path(
    "E:/AI/virtual_player/data/journal/games/pixelflow/"
    "yolo_dataset/models/train_v3/weights/best.pt"
)

# Board crop coordinates (1080x1920 resolution, hardcoded — auto-detect fails)
BOARD_Y1, BOARD_Y2 = 150, 815
BOARD_X1, BOARD_X2 = 170, 905

# Holder region (5 slots)
HOLDER_Y1, HOLDER_Y2 = 880, 980
HOLDER_X1, HOLDER_X2 = 110, 780
HOLDER_SLOT_COUNT = 5

# Queue pig detection region (matches decision_pixelflow.py)
QUEUE_Y1, QUEUE_Y2 = 970, 1700
QUEUE_X1, QUEUE_X2 = 220, 750

# Empty holder slot colors (Dark / DarkPurple background)
EMPTY_HOLDER_COLORS = {8, 21, 24, 29}  # Dark, DarkPurple, Gray, BrownDark

# Frame/background colors (not game content)
FRAME_COLORS = {8, 21}  # Dark, DarkPurple

# Colors that are NEVER game tiles (structural/decoration elements)
# Game tiles = colored pixel art pieces that pigs eat
# These are board structure: frame, empty space, conveyor rails
NON_TILE_COLORS = {
    7,   # White — empty space inside board
    8,   # Dark — frame/floor
    9,   # LightBlue — conveyor rail elements
    15,  # Periwinkle — conveyor belt rail
    21,  # DarkPurple — frame
    23,  # Silver — conveyor decoration
    24,  # Gray — conveyor/frame structural
    28,  # SageTeal — board border decoration
}

# AI play database path (separate from human PlayDB)
AI_PLAY_DB_PATH = Path("E:/AI/virtual_player/data/db/ai_play_pixelflow.db")

# Fingerprint database path (human gameplay fingerprints, ~7700 rows)
FINGERPRINT_DB_PATH = Path("E:/AI/virtual_player/data/pixelflow/db/fingerprint.db")

# Fingerprint search constants
FP_SIMILARITY_THRESHOLD = 0.78  # Cycle 5 2026-04-09: rolled back toward Cycle 3's
# 0.80 level after Cycle 4's 0.65 produced WORSE results (40% -> 25% WR).
# The pool-widening argument was wrong — low-similarity matches mislead.
FP_TOP_K = 8                    # Cycle 5: between Cycle 3 (5) and Cycle 4 (12).

# Learning constants
COOLDOWN_TURNS = 2          # Turns to avoid re-tapping same color
LEARNING_INTERVAL = 10      # Check patterns every N turns
MIN_CONFIDENCE_AVOID = 0.3  # Avoid actions below this confidence

# Human PlayDB path (read-only reference)
PLAY_DB_PATH = Path("E:/AI/virtual_player/data/db/play_data.db")

# ClickCapture → ADB coordinate mapping constants
# ClickCapture captured mouse coords on landscape BlueStacks window
# Game runs in portrait mode, ADB uses portrait coords (1080x1920)
# Calibrated from 3 pig positions: error 3-7px
CLICK_TO_ADB_SCALE_X = 1.778
CLICK_TO_ADB_OFFSET_X = 60.0
CLICK_TO_ADB_SCALE_Y = 1.613

# ADB screen bounds for clipping
ADB_SCREEN_W = 1080
ADB_SCREEN_H = 1920


def click_to_adb(click_x: float, click_y: float) -> Tuple[int, int]:
    """Convert ClickCapture raw window pixel coords to ADB tap coords.

    Use this when you have the original mouse coordinates from the capture
    window (before normalization). For PlayDB normalized coords, use
    norm_to_adb() instead.
    """
    adb_x = int(CLICK_TO_ADB_SCALE_X * click_x + CLICK_TO_ADB_OFFSET_X)
    adb_y = int(CLICK_TO_ADB_SCALE_Y * click_y)
    # Clip to screen bounds
    adb_x = max(0, min(adb_x, ADB_SCREEN_W))
    adb_y = max(0, min(adb_y, ADB_SCREEN_H))
    return adb_x, adb_y


def norm_to_adb(norm_x: float, norm_y: float) -> Tuple[int, int]:
    """Convert PlayDB normalized coords to ADB tap coords.

    ClickCapture normalized with wm size 1920x1080 (landscape):
      norm_x = raw_mouse_x / 1920
      norm_y = raw_mouse_y / 1080
    First recover raw mouse coords, then apply click_to_adb mapping.
    """
    raw_x = norm_x * 1920  # landscape window x
    raw_y = norm_y * 1080  # landscape window y
    return click_to_adb(raw_x, raw_y)


# ---------------------------------------------------------------------------
# ADB Functions
# ---------------------------------------------------------------------------
def adb_screenshot(adb: str, serial: str, temp_dir: Path) -> Optional[Path]:
    """Capture screenshot via ADB exec-out screencap."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            [adb, "-s", serial, "exec-out", "screencap", "-p"],
            capture_output=True, timeout=10,
        )
        if len(r.stdout) < 1000:
            return None
        path = temp_dir / "smart_frame.png"
        path.write_bytes(r.stdout)
        return path
    except Exception:
        return None


def adb_tap(adb: str, serial: str, x: int, y: int):
    try:
        subprocess.run(
            [adb, "-s", serial, "shell", "input", "tap", str(x), str(y)],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def adb_back(adb: str, serial: str):
    try:
        subprocess.run(
            [adb, "-s", serial, "shell", "input", "keyevent", "4"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def adb_relaunch(adb: str, serial: str):
    """Force-stop and relaunch PixelFlow."""
    try:
        subprocess.run(
            [adb, "-s", serial, "shell", "input", "keyevent", "3"],
            capture_output=True, timeout=5,
        )
        time.sleep(1)
        subprocess.run(
            [adb, "-s", serial, "shell", "am", "force-stop",
             "com.android.vending"],
            capture_output=True, timeout=5,
        )
        subprocess.run(
            [adb, "-s", serial, "shell", "am", "force-stop", PACKAGE],
            capture_output=True, timeout=5,
        )
        time.sleep(2)
        subprocess.run(
            [adb, "-s", serial, "shell", "am", "start", "-n",
             f"{PACKAGE}/{ACTIVITY}"],
            capture_output=True, timeout=5,
        )
        time.sleep(8)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ADB Recovery (3-tier escalation)
# ---------------------------------------------------------------------------
BLUESTACKS_DIR = Path(r"C:\Program Files\BlueStacks_nxt")
HD_PLAYER_EXE = BLUESTACKS_DIR / "HD-Player.exe"
BLUESTACKS_INSTANCE = "Nougat32"


def adb_health_check(adb: str, serial: str) -> bool:
    """Return True if ADB+device responds to a trivial shell command."""
    try:
        r = subprocess.run(
            [adb, "-s", serial, "shell", "echo", "ok"],
            capture_output=True, timeout=5, text=True,
        )
        return "ok" in (r.stdout or "")
    except Exception:
        return False


def adb_recover_tier1(adb: str, serial: str) -> bool:
    """Tier 1: Restart ADB server only (cheap, ~5s)."""
    try:
        subprocess.run([adb, "kill-server"], capture_output=True, timeout=10)
        time.sleep(1)
        subprocess.run([adb, "start-server"], capture_output=True, timeout=10)
        time.sleep(2)
        subprocess.run(
            [adb, "connect", "localhost:5555"],
            capture_output=True, timeout=5,
        )
        time.sleep(2)
        return adb_health_check(adb, serial)
    except Exception:
        return False


def adb_recover_tier2(adb: str, serial: str) -> bool:
    """Tier 2: Relaunch BlueStacks HD-Player process (~30s)."""
    try:
        # Kill any HD-Player running
        subprocess.run(
            ["taskkill", "/F", "/IM", "HD-Player.exe"],
            capture_output=True, timeout=10,
        )
        time.sleep(3)
        # Restart instance
        subprocess.Popen(
            [str(HD_PLAYER_EXE), "--instance", BLUESTACKS_INSTANCE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # BlueStacks needs time to boot the Android instance
        time.sleep(25)
        # Re-establish ADB
        subprocess.run([adb, "kill-server"], capture_output=True, timeout=10)
        time.sleep(1)
        subprocess.run([adb, "start-server"], capture_output=True, timeout=10)
        time.sleep(2)
        subprocess.run(
            [adb, "connect", "localhost:5555"],
            capture_output=True, timeout=5,
        )
        time.sleep(3)
        return adb_health_check(adb, serial)
    except Exception:
        return False


def adb_recover_tier3(adb: str, serial: str) -> bool:
    """Tier 3: Aggressive BlueStacks instance restart with longer wait (~90s).

    Only kills HD-Player.exe (the user-facing instance window) — leaves
    BstkSVC.exe / BlueStacksHelper.exe alone because killing those can
    leave the BlueStacks engine in a state that needs manual recovery.
    """
    try:
        # Kill ALL HD-Player processes (catches stale instances too)
        subprocess.run(
            ["taskkill", "/F", "/IM", "HD-Player.exe"],
            capture_output=True, timeout=10,
        )
        time.sleep(8)
        subprocess.Popen(
            [str(HD_PLAYER_EXE), "--instance", BLUESTACKS_INSTANCE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        # Longer wait — Tier 3 means previous tiers failed, so the engine
        # is probably struggling. Give it generous time to come up.
        time.sleep(60)
        subprocess.run([adb, "kill-server"], capture_output=True, timeout=10)
        time.sleep(1)
        subprocess.run([adb, "start-server"], capture_output=True, timeout=10)
        time.sleep(2)
        subprocess.run(
            [adb, "connect", "localhost:5555"],
            capture_output=True, timeout=5,
        )
        time.sleep(5)
        return adb_health_check(adb, serial)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# YOLO Screen Classifier
# ---------------------------------------------------------------------------
class ScreenClassifier:
    """YOLO-based screen type classifier with timeout protection."""

    INFER_TIMEOUT = 10.0  # seconds — abort if YOLO hangs
    MAX_TIMEOUTS_BEFORE_RELOAD = 3

    def __init__(self, model_path: Path):
        self._model = None
        self._model_path = model_path
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="yolo"
        )
        self._timeout_count = 0

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from ultralytics import YOLO
            self._model = YOLO(str(self._model_path))
        except Exception as e:
            print(f"[WARN] YOLO load failed: {e}")

    def _reload_model(self):
        """Force-reload the model after repeated timeouts.

        Critical: A hung worker thread holds a reference to the old model and
        keeps the single-worker executor blocked forever. Replacing self._model
        alone does NOT free that thread — we must also abandon the executor and
        spawn a fresh one so new submissions can actually run.
        """
        # Abandon the old executor (the hung thread will leak, but that's OK
        # because the process restarts the model anyway)
        try:
            old_executor = self._executor
            self._executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="yolo"
            )
            old_executor.shutdown(wait=False)
        except Exception:
            pass
        self._model = None
        self._timeout_count = 0
        self._ensure_model()

    def shutdown(self):
        """Cleanly shut down the YOLO executor."""
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass

    def _infer(self, img_path_str: str) -> str:
        results = self._model(img_path_str, verbose=False)
        if results and len(results) > 0:
            r = results[0]
            if hasattr(r, "probs") and r.probs is not None:
                cls_id = int(r.probs.top1)
                return self._model.names.get(cls_id, "unknown")
        return "unknown"

    def classify(self, img_path: Path) -> str:
        """Classify screenshot → screen type. Returns 'unknown' on error/timeout."""
        self._ensure_model()
        if self._model is None:
            return "unknown"
        future = self._executor.submit(self._infer, str(img_path))
        try:
            result = future.result(timeout=self.INFER_TIMEOUT)
            self._timeout_count = 0
            return result
        except concurrent.futures.TimeoutError:
            self._timeout_count += 1
            print(f"[WARN] YOLO classify timeout #{self._timeout_count}")
            future.cancel()
            if self._timeout_count >= self.MAX_TIMEOUTS_BEFORE_RELOAD:
                print("[WARN] YOLO too many timeouts — reloading model")
                try:
                    self._reload_model()
                except Exception as e:
                    print(f"[WARN] YOLO reload failed: {e}")
            return "unknown"
        except Exception:
            return "unknown"


# ---------------------------------------------------------------------------
# Board Parser (wraps cell_aware_analyzer)
# ---------------------------------------------------------------------------
class BoardParser:
    """Parse the game board into a color-count map."""

    def __init__(self, profile: dict):
        self._profile = profile
        # Build render palette for pig color matching
        self._pal_keys, self._pal_arr = build_render_palette(profile)
        self._render_palette = {}
        if "render_ranges" in profile:
            for cid_str, info in profile["render_ranges"].items():
                mean = info.get("render_mean", info.get("ref_rgb"))
                self._render_palette[int(cid_str)] = np.array(mean, dtype=np.float64)

    def parse(self, img_cv: np.ndarray) -> Dict[int, int]:
        """Parse board from full screenshot.

        Returns:
            color_counts: {color_id: cell_count} for actual game tiles only.
                          Frame, background, conveyor, and dominant empty-space
                          colors are dynamically excluded.
        """
        # Hardcoded board crop (auto-detect unreliable)
        board_bgr = img_cv[BOARD_Y1:BOARD_Y2, BOARD_X1:BOARD_X2]
        if board_bgr.size == 0:
            return {}

        # Convert to RGB (cell_aware_analyzer v2 expects RGB)
        board_rgb = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2RGB)

        # Extract cell colors (v2 API: multi-sample voting)
        grid = extract_cell_colors(
            board_rgb, self._profile, self._pal_keys, self._pal_arr
        )

        # CC smoothing (noise reduction)
        grid = cc_smooth(grid, min_size=3)
        grid = cc_smooth(grid, min_size=2)

        # Apply frame margins from profile to exclude border/conveyor areas
        fr = self._profile.get('ignore_elements', {}).get('frame', {})
        top = fr.get('top_rows', 2)
        bot = fr.get('bottom_rows', 2)
        left = fr.get('left_cols', 2)
        right = fr.get('right_cols', 5)
        rows = self._profile['grid']['rows']
        cols = self._profile['grid']['cols']

        # Count colors only in inner area (exclude frame margins)
        # NON_TILE_COLORS = structural elements that are never game tiles
        color_counts = Counter()
        for r in range(top, rows - bot):
            for c in range(left, cols - right):
                cid = grid[r][c]
                if cid in NON_TILE_COLORS:
                    continue
                color_counts[cid] += 1

        # Remove zero/negative entries
        return {cid: cnt for cid, cnt in color_counts.items() if cnt > 0}

    def match_color(self, r: int, g: int, b: int) -> int:
        """Match an RGB pixel to the nearest palette color using render means."""
        pixel = np.array([r, g, b], dtype=np.float64)
        best_cid = 8  # Default: Dark
        best_dist = float("inf")

        for cid, mean_rgb in self._render_palette.items():
            dist = np.sqrt(np.sum((mean_rgb - pixel) ** 2))
            if dist < best_dist:
                best_dist = dist
                best_cid = cid

        # Also check raw palette for colors without render data
        for cid, rgb in PALETTE_29.items():
            if cid in self._render_palette:
                continue
            pal_rgb = np.array(rgb, dtype=np.float64)
            dist = np.sqrt(np.sum((pal_rgb - pixel) ** 2))
            if dist < best_dist:
                best_dist = dist
                best_cid = cid

        return best_cid


# ---------------------------------------------------------------------------
# Pig Color Detector
# ---------------------------------------------------------------------------
def detect_pig_color(
    img_arr: np.ndarray,
    pig_x: int,
    pig_y: int,
    parser: BoardParser,
    sample_radius: int = 30,
) -> int:
    """Detect the color of a queue pig at (pig_x, pig_y).

    Strategy: Sample a ring around the pig center (the center itself is the
    white number text). Look at pixels in a donut region (radius 15-30) and
    find the dominant non-white, non-dark color.
    """
    h, w = img_arr.shape[:2]
    # Sample box around pig, avoiding center (white text)
    y1 = max(0, pig_y - sample_radius)
    y2 = min(h, pig_y + sample_radius)
    x1 = max(0, pig_x - sample_radius)
    x2 = min(w, pig_x + sample_radius)

    region = img_arr[y1:y2, x1:x2]
    if region.size == 0:
        return 0

    rh, rw = region.shape[:2]
    cy, cx = rh // 2, rw // 2

    # Collect non-center pixels (donut: distance 10-30 from center)
    samples = []
    for dy in range(-sample_radius, sample_radius + 1, 3):
        for dx in range(-sample_radius, sample_radius + 1, 3):
            dist = (dy * dy + dx * dx) ** 0.5
            if dist < 10 or dist > sample_radius:
                continue
            py = cy + dy
            px = cx + dx
            if 0 <= py < rh and 0 <= px < rw:
                r, g, b = region[py, px, 0], region[py, px, 1], region[py, px, 2]
                # Skip near-white (text) and near-black (background)
                if r > 200 and g > 200 and b > 200:
                    continue
                if r < 40 and g < 40 and b < 40:
                    continue
                samples.append((int(r), int(g), int(b)))

    if not samples:
        return 0

    # Match each sample to palette, vote
    color_votes = Counter()
    for r, g, b in samples:
        cid = parser.match_color(r, g, b)
        if cid not in EMPTY_HOLDER_COLORS:
            color_votes[cid] += 1

    if not color_votes:
        return 0

    return color_votes.most_common(1)[0][0]


# ---------------------------------------------------------------------------
# Holder Parser
# ---------------------------------------------------------------------------
def parse_holder(
    img_arr: np.ndarray,
    parser: BoardParser,
) -> List[int]:
    """Parse the 5 holder slots, returning color_id per slot (0 = empty).

    Each slot is sampled at its center. Empty slots are Dark/DarkPurple.
    """
    h, w = img_arr.shape[:2]
    if h < HOLDER_Y2 or w < HOLDER_X2:
        return [0] * HOLDER_SLOT_COUNT

    holder_width = HOLDER_X2 - HOLDER_X1
    slot_width = holder_width // HOLDER_SLOT_COUNT

    slots = []
    for i in range(HOLDER_SLOT_COUNT):
        cx = HOLDER_X1 + i * slot_width + slot_width // 2
        cy = (HOLDER_Y1 + HOLDER_Y2) // 2

        # Sample a small region around center (5x5)
        region = img_arr[cy - 2:cy + 3, cx - 2:cx + 3]
        if region.size == 0:
            slots.append(0)
            continue

        avg_r = int(region[:, :, 0].mean())
        avg_g = int(region[:, :, 1].mean())
        avg_b = int(region[:, :, 2].mean())

        # Dark background check (empty slot)
        if avg_r < 80 and avg_g < 80 and avg_b < 130:
            slots.append(0)
            continue

        cid = parser.match_color(avg_r, avg_g, avg_b)
        if cid in EMPTY_HOLDER_COLORS:
            slots.append(0)
        else:
            slots.append(cid)

    return slots


# ---------------------------------------------------------------------------
# AI Play Database (sqlite3, separate from human PlayDB)
# ---------------------------------------------------------------------------
class AIPlayDB:
    """Lightweight sqlite3 database for AI turn/session/pattern tracking."""

    def __init__(self, db_path: Path = AI_PLAY_DB_PATH):
        self._db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _ensure_conn(self):
        if self._conn is not None:
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), timeout=10)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        c = self._conn
        c.execute("""
            CREATE TABLE IF NOT EXISTS ai_turn (
                turn_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp TEXT,
                screen_type TEXT,
                board_cells INTEGER,
                board_colors INTEGER,
                action_type TEXT,
                action_x INTEGER,
                action_y INTEGER,
                action_color TEXT,
                result_delta INTEGER,
                holder_occupied INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS ai_session (
                session_id TEXT PRIMARY KEY,
                started_at TEXT,
                ended_at TEXT,
                outcome TEXT,
                total_turns INTEGER,
                start_cells INTEGER,
                end_cells INTEGER,
                level_cleared BOOLEAN DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS ai_pattern (
                pattern_id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_color_count INTEGER,
                holder_occupied INTEGER,
                action_color TEXT,
                times_tried INTEGER DEFAULT 0,
                times_good INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.5,
                UNIQUE(board_color_count, holder_occupied, action_color)
            )
        """)
        # Exploration patterns: what to do when stuck
        c.execute("""
            CREATE TABLE IF NOT EXISTS explore_pattern (
                explore_id INTEGER PRIMARY KEY AUTOINCREMENT,
                stall_context TEXT,
                tap_x INTEGER,
                tap_y INTEGER,
                times_tried INTEGER DEFAULT 0,
                times_worked INTEGER DEFAULT 0,
                confidence REAL DEFAULT 0.5,
                last_used TEXT,
                UNIQUE(stall_context, tap_x, tap_y)
            )
        """)
        c.commit()

    def record_explore(self, stall_context: str, tap_x: int, tap_y: int, worked: bool):
        """Record exploration result. stall_context = 'cells_N_colors_M_holder_K'."""
        self._ensure_conn()
        self._conn.execute("""
            INSERT INTO explore_pattern (stall_context, tap_x, tap_y, times_tried, times_worked, last_used)
            VALUES (?,?,?,1,?,?)
            ON CONFLICT(stall_context, tap_x, tap_y) DO UPDATE SET
                times_tried = times_tried + 1,
                times_worked = times_worked + ?,
                confidence = CAST(times_worked + ? AS REAL) / (times_tried + 1),
                last_used = ?
        """, (stall_context, tap_x, tap_y, 1 if worked else 0,
              datetime.now().isoformat(),
              1 if worked else 0, 1 if worked else 0,
              datetime.now().isoformat()))
        self._conn.commit()

    def get_best_explore(self, stall_context: str, top_k: int = 5):
        """Get previously successful exploration taps for this context.

        Cycle 13 2026-04-09: instead of strict confidence DESC ordering —
        which caused (660,1500) to dominate across all sessions — pull a
        larger pool and shuffle. This keeps all learned coords in rotation
        so the player tries each one across sessions.
        """
        self._ensure_conn()
        rows = self._conn.execute("""
            SELECT tap_x, tap_y, confidence, times_tried, times_worked
            FROM explore_pattern
            WHERE stall_context = ? AND times_worked > 0
            ORDER BY confidence DESC, times_worked DESC
            LIMIT ?
        """, (stall_context, top_k * 4)).fetchall()
        import random
        random.shuffle(rows)
        return [(r[0], r[1], r[2]) for r in rows[:top_k]]

    def record_turn(
        self, session_id: str, screen_type: str,
        board_cells: int, board_colors: int,
        action_type: str, action_x: int, action_y: int,
        action_color: str, result_delta: int, holder_occupied: int,
    ):
        self._ensure_conn()
        self._conn.execute(
            """INSERT INTO ai_turn
               (session_id, timestamp, screen_type, board_cells, board_colors,
                action_type, action_x, action_y, action_color,
                result_delta, holder_occupied)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (session_id, datetime.now().isoformat(), screen_type,
             board_cells, board_colors, action_type, action_x, action_y,
             action_color, result_delta, holder_occupied),
        )
        self._conn.commit()

    def update_pattern(
        self, board_color_count: int, holder_occupied: int,
        action_color: str, is_good: bool,
    ):
        self._ensure_conn()
        # Upsert pattern row
        self._conn.execute(
            """INSERT INTO ai_pattern (board_color_count, holder_occupied, action_color,
                                       times_tried, times_good, confidence)
               VALUES (?,?,?,1,?,0.5)
               ON CONFLICT(board_color_count, holder_occupied, action_color)
               DO UPDATE SET
                   times_tried = times_tried + 1,
                   times_good = times_good + ?,
                   confidence = CAST(times_good + ? AS REAL) / MAX(times_tried + 1, 1)
            """,
            (board_color_count, holder_occupied, action_color,
             1 if is_good else 0,
             1 if is_good else 0,
             1 if is_good else 0),
        )
        self._conn.commit()

    def get_pattern_confidence(
        self, board_color_count: int, holder_occupied: int, action_color: str,
    ) -> Optional[float]:
        """Return confidence for a (board_color_count, holder_occupied, action_color) triple."""
        self._ensure_conn()
        row = self._conn.execute(
            """SELECT confidence, times_tried FROM ai_pattern
               WHERE board_color_count=? AND holder_occupied=? AND action_color=?""",
            (board_color_count, holder_occupied, action_color),
        ).fetchone()
        if row and row[1] >= 5:  # Need at least 5 tries for meaningful confidence
            return row[0]
        return None

    def start_session(self, session_id: str, start_cells: int):
        self._ensure_conn()
        self._conn.execute(
            """INSERT OR REPLACE INTO ai_session
               (session_id, started_at, start_cells, total_turns, outcome)
               VALUES (?,?,?,0,'in_progress')""",
            (session_id, datetime.now().isoformat(), start_cells),
        )
        self._conn.commit()

    def end_session(
        self, session_id: str, outcome: str,
        total_turns: int, end_cells: int,
    ):
        self._ensure_conn()
        self._conn.execute(
            """UPDATE ai_session
               SET ended_at=?, outcome=?, total_turns=?, end_cells=?,
                   level_cleared=?
               WHERE session_id=?""",
            (datetime.now().isoformat(), outcome, total_turns, end_cells,
             1 if outcome == "win" else 0, session_id),
        )
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Fingerprint Searcher (human gameplay fingerprint DB)
# ---------------------------------------------------------------------------
class FingerprintSearcher:
    """Search fingerprint.db for past human plays similar to current board state.

    Loads all fingerprints into memory once (~7700 x 29 floats = ~900KB),
    then performs vectorized cosine similarity search per query.

    Schema (fingerprint.db / board_state table):
        state_id, file_name, timestamp, total_cells, num_colors,
        color_vector (JSON), fingerprint (JSON, 29-dim L2-normed),
        action_x (ADB), action_y (ADB), action_type,
        delta_cells, after_cells, episode_id, session_outcome
    """

    def __init__(self, db_path: Path = FINGERPRINT_DB_PATH):
        self._path = db_path
        self._ids: List[int] = []
        self._fp_matrix: Optional[np.ndarray] = None  # (N, 29)
        self._actions: List[Tuple[int, int]] = []      # (adb_x, adb_y)
        self._deltas: List[int] = []
        self._loaded = False

    def _ensure_cache(self):
        """Load all fingerprints from DB into memory (one-time).

        FIX 2026-04-08: Filter to only include rows from WINNING sessions.
        Previously loaded all 7736 rows including 2541 from failed sessions —
        that taught the player bad patterns. Now JOINs with play_data.db
        (session table, outcome='clear') so only winning tap patterns survive.
        """
        if self._loaded:
            return
        self._loaded = True  # Mark loaded even on failure to avoid repeated attempts

        if not self._path.exists():
            return

        # play_data.db sits next to fingerprint.db in the pixelflow/db folder
        play_db_path = self._path.parent / "play_data.db"

        conn = None
        try:
            conn = sqlite3.connect(str(self._path), timeout=10)
            # Check if real_delta column exists
            cols = [r[1] for r in conn.execute("PRAGMA table_info(board_state)")]
            if "real_delta" in cols:
                delta_expr = "COALESCE(b.real_delta, b.delta_cells)"
            else:
                delta_expr = "b.delta_cells"

            rows = []
            win_filter_used = False
            if play_db_path.exists():
                try:
                    conn.execute(
                        f"ATTACH DATABASE '{play_db_path.as_posix()}' AS pd"
                    )
                    rows = conn.execute(f"""
                        SELECT b.state_id, b.fingerprint, b.action_x, b.action_y,
                               {delta_expr} as delta,
                               b.total_cells, b.num_colors
                        FROM board_state b
                        JOIN pd.turn t ON t.screenshot_before = b.file_name
                        JOIN pd.session s ON s.session_id = t.session_id
                        WHERE b.action_x IS NOT NULL
                          AND b.fingerprint IS NOT NULL
                          AND s.outcome = 'clear'
                    """).fetchall()
                    win_filter_used = True
                except Exception as e:
                    print(f"[WARN] FingerprintSearcher WIN-filter join failed: {e}")
                    rows = []
                finally:
                    try:
                        conn.execute("DETACH DATABASE pd")
                    except Exception:
                        pass

            # Fallback: load all rows if WIN-filter join failed
            if not rows:
                rows = conn.execute(f"""
                    SELECT b.state_id, b.fingerprint, b.action_x, b.action_y,
                           {delta_expr} as delta,
                           b.total_cells, b.num_colors
                    FROM board_state b
                    WHERE b.action_x IS NOT NULL AND b.fingerprint IS NOT NULL
                """).fetchall()
                win_filter_used = False

            print(
                f"[FingerprintSearcher] Loaded {len(rows)} rows "
                f"(win_only={win_filter_used})"
            )
        except Exception as e:
            print(f"[WARN] FingerprintSearcher load failed: {e}")
            return
        finally:
            if conn:
                conn.close()

        if not rows:
            return

        ids = []
        fps = []
        actions = []
        deltas = []

        for r in rows:
            try:
                fp = json.loads(r[1])
                if not isinstance(fp, list) or len(fp) == 0:
                    continue
                ids.append(r[0])
                fps.append(fp)
                actions.append((int(r[2]), int(r[3])))
                deltas.append(int(r[4]) if r[4] is not None else 0)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

        if fps:
            self._ids = ids
            self._fp_matrix = np.array(fps, dtype=np.float64)
            self._actions = actions
            self._deltas = deltas

    def search(self, current_fp: List[float], top_k: int = FP_TOP_K) -> List[dict]:
        """Find top-K similar past board states by cosine similarity.

        Returns list sorted by: (1) delta < 0 first (progress), (2) similarity desc.
        Each entry: {"state_id", "action_x", "action_y", "similarity", "delta"}.
        """
        self._ensure_cache()
        if self._fp_matrix is None or len(self._fp_matrix) == 0:
            return []

        query = np.array(current_fp, dtype=np.float64)
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return []

        # Vectorized cosine similarity
        dots = self._fp_matrix @ query
        norms = np.linalg.norm(self._fp_matrix, axis=1) * query_norm
        norms[norms == 0] = 1.0
        similarities = dots / norms

        # Pre-filter: grab more candidates than needed, then sort
        candidate_count = min(top_k * 3, len(similarities))
        top_indices = np.argsort(-similarities)[:candidate_count]

        results = []
        for idx in top_indices:
            sim = float(similarities[idx])
            results.append({
                "state_id": self._ids[idx],
                "action_x": self._actions[idx][0],
                "action_y": self._actions[idx][1],
                "similarity": sim,
                "delta": self._deltas[idx],
            })

        # Filter out-of-bounds coordinates (mouse taps on sidebar/outside game)
        valid = [r for r in results
                 if 50 <= r["action_x"] <= 1030 and 50 <= r["action_y"] <= 1870]

        # Deduplicate by action coordinates (keep highest similarity per unique tap)
        seen_coords = {}
        for r in sorted(valid, key=lambda r: -r["similarity"]):
            key = (r["action_x"] // 30, r["action_y"] // 30)  # 30px grid dedup
            if key not in seen_coords:
                seen_coords[key] = r

        unique_results = list(seen_coords.values())

        # Prioritize: actions that caused PROGRESS (real_delta < 0) first
        progress = sorted([r for r in unique_results if r["delta"] < 0],
                          key=lambda r: (r["delta"], -r["similarity"]))  # most progress first
        no_progress = sorted([r for r in unique_results if r["delta"] >= 0],
                             key=lambda r: -r["similarity"])

        return (progress + no_progress)[:top_k]

    @property
    def is_available(self) -> bool:
        """Check if fingerprint data is loaded and usable."""
        self._ensure_cache()
        return self._fp_matrix is not None and len(self._fp_matrix) > 0

    def close(self):
        """Release cached data."""
        self._fp_matrix = None
        self._ids = []
        self._actions = []
        self._deltas = []
        self._loaded = False


# ---------------------------------------------------------------------------
# PlayDB Reference (read-only human play patterns)
# ---------------------------------------------------------------------------
class PlayDBReference:
    """Read-only reference to human play patterns stored in play_data.db.

    This is SEPARATE from AIPlayDB. We never write to this database.
    Used to bootstrap AI decisions with human tap patterns.
    """

    def __init__(self, db_path: Path = PLAY_DB_PATH):
        self._path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _ensure_conn(self) -> bool:
        """Open connection if DB exists. Returns False if DB unavailable."""
        if self._conn is not None:
            return True
        if not self._path.exists():
            return False
        try:
            self._conn = sqlite3.connect(str(self._path), timeout=10)
            self._conn.row_factory = sqlite3.Row
            return True
        except Exception:
            return False

    def get_screen_actions(
        self, screen_type: str, top_k: int = 5
    ) -> List[Tuple[int, int, int]]:
        """Get most common human tap positions for a screen type.

        Returns [(adb_x, adb_y, count), ...] sorted by frequency desc.
        Coordinates are converted from PlayDB normalized to ADB space.
        """
        if not self._ensure_conn():
            return []
        try:
            rows = self._conn.execute('''
                SELECT a.x, a.y, COUNT(*) as cnt
                FROM action a
                JOIN turn t ON t.turn_id = a.turn_id
                JOIN session s ON s.session_id = t.session_id
                WHERE s.game_id = 'pixelflow'
                  AND t.screen_type = ?
                  AND a.type = 'tap'
                GROUP BY ROUND(a.x, 2), ROUND(a.y, 2)
                ORDER BY cnt DESC
                LIMIT ?
            ''', (screen_type, top_k)).fetchall()

            result = []
            for r in rows:
                ax, ay = norm_to_adb(r['x'], r['y'])
                result.append((ax, ay, r['cnt']))
            return result
        except Exception:
            return []

    def get_gameplay_sequence(
        self, limit: int = 20
    ) -> List[Tuple[int, int]]:
        """Get human gameplay action sequence (ADB coords).

        Returns [(adb_x, adb_y), ...] from recent successful sessions.
        Useful for bootstrapping exploration when AI has no learned patterns.
        """
        if not self._ensure_conn():
            return []
        try:
            rows = self._conn.execute('''
                SELECT a.x, a.y
                FROM action a
                JOIN turn t ON t.turn_id = a.turn_id
                JOIN session s ON s.session_id = t.session_id
                WHERE s.game_id = 'pixelflow'
                  AND t.screen_type = 'gameplay'
                  AND a.type = 'tap'
                ORDER BY t.timestamp, a.action_index
                LIMIT ?
            ''', (limit,)).fetchall()
            return [norm_to_adb(r['x'], r['y']) for r in rows]
        except Exception:
            return []

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Strategy Engine
# ---------------------------------------------------------------------------
class Strategy:
    """Decides which pig to tap based on board state, queue, holder, and learning.

    Priority (revised):
      P1: Queue pig whose color is ALREADY in holder (merge = safe)
      P2: Queue pig whose color has FEWEST remaining board cells (clear fast)
      P3: Queue pig, any non-cooldown color
      P4: Queue pig, ignore cooldown (last resort)

    Cooldown: After tapping a color, that color is avoided for COOLDOWN_TURNS turns
    (the pig is travelling on the conveyor — tapping the same color again just wastes
    a holder slot).

    Learning: Every LEARNING_INTERVAL turns, consult ai_pattern table to prefer
    high-confidence colors and avoid low-confidence ones.
    """

    def __init__(self):
        self._last_tapped_color: int = 0
        self._cooldown_map: Dict[int, int] = {}  # color_id → turns remaining
        self._turn_counter: int = 0

    def tick_cooldowns(self):
        """Decrement cooldown counters. Call once per turn."""
        self._turn_counter += 1
        expired = [cid for cid, t in self._cooldown_map.items() if t <= 1]
        for cid in expired:
            del self._cooldown_map[cid]
        for cid in list(self._cooldown_map):
            self._cooldown_map[cid] -= 1

    def record_tap(self, color_id: int):
        """Record that we tapped a color — start cooldown."""
        self._last_tapped_color = color_id
        if color_id > 0:
            self._cooldown_map[color_id] = COOLDOWN_TURNS

    def _is_on_cooldown(self, color_id: int) -> bool:
        return color_id in self._cooldown_map

    def choose_action(
        self,
        board_colors: Dict[int, int],
        queue_pigs: List[Tuple[int, int, int]],  # (x, y, color_id)
        holder_slots: List[int],
        playbook,
        ai_db: Optional["AIPlayDB"] = None,
    ) -> Optional[Action]:
        """Choose the best pig to tap.

        Args:
            board_colors: {color_id: remaining_cell_count}
            queue_pigs: [(x, y, color_id), ...]
            holder_slots: [color_id_or_0, ...] for 5 slots
            playbook: Playbook instance (unused currently)
            ai_db: AIPlayDB for pattern lookup (optional)

        Returns:
            Action to execute, or None for wait
        """
        self.tick_cooldowns()

        occupied = sum(1 for s in holder_slots if s > 0)
        holder_colors = set(s for s in holder_slots if s > 0)
        board_color_set = set(board_colors.keys())

        # Separate queue pigs into colored (known) vs unknown (cid==0)
        colored_pigs = [
            (x, y, cid) for x, y, cid in queue_pigs
            if cid > 0 and board_colors.get(cid, 0) > 0
        ]
        unknown_pigs = [(x, y, cid) for x, y, cid in queue_pigs if cid == 0]
        # Pigs whose color doesn't match any board color (color detected but 0 cells)
        no_match_pigs = [
            (x, y, cid) for x, y, cid in queue_pigs
            if cid > 0 and board_colors.get(cid, 0) == 0
        ]

        # Stuck-holder detection: holder full (5/5) and ALL holder colors have
        # 0 remaining board cells → need a ? pig or any pig to break the stalemate
        holder_stuck = (
            occupied >= 5
            and holder_colors
            and all(board_colors.get(hc, 0) == 0 for hc in holder_colors)
        )
        if holder_stuck:
            # Prioritize ? pigs to break the deadlock
            if unknown_pigs:
                px, py, _ = unknown_pigs[0]
                self.record_tap(0)
                return Action(
                    "tap", px, py, 2.5,
                    f"[P0:holder-stuck] Tap ? pig to break deadlock "
                    f"(holder full, no matching board cells)"
                )
            # No ? pigs — tap any pig (forced attempt)
            if queue_pigs:
                px, py, pcid = queue_pigs[0]
                color_name = COLOR_NAMES.get(pcid, "?")
                self.record_tap(pcid)
                return Action(
                    "tap", px, py, 2.5,
                    f"[P0:holder-stuck-force] Tap pig color={color_name} "
                    f"(holder full, no ? pigs, forced)"
                )

        if colored_pigs:
            # --- Learning filter ---
            # If we have enough data, penalize low-confidence actions
            confidence_scores: Dict[int, Optional[float]] = {}
            if ai_db and self._turn_counter % LEARNING_INTERVAL < 3:
                n_colors = len(board_colors)
                for _, _, cid in colored_pigs:
                    color_name = COLOR_NAMES.get(cid, str(cid))
                    conf = ai_db.get_pattern_confidence(n_colors, occupied, color_name)
                    confidence_scores[cid] = conf

            # --- P1: Color already in holder (merge — safe, no new slot used) ---
            p1_pigs = [
                (x, y, cid) for x, y, cid in colored_pigs
                if cid in holder_colors and not self._is_on_cooldown(cid)
            ]
            if p1_pigs:
                # Among holder-matching, pick fewest remaining cells
                p1_pigs.sort(key=lambda p: board_colors.get(p[2], 0))
                best = p1_pigs[0]
                return self._make_action(best, board_colors, len(colored_pigs), "P1:holder-merge")

            # --- P2: Fewest remaining cells on board (clear fast → free holder slot) ---
            p2_pigs = [
                (x, y, cid) for x, y, cid in colored_pigs
                if not self._is_on_cooldown(cid)
            ]
            # Filter out low-confidence actions if learning data available
            if p2_pigs and confidence_scores:
                safe_pigs = [
                    p for p in p2_pigs
                    if confidence_scores.get(p[2]) is None  # no data = OK
                    or confidence_scores[p[2]] >= MIN_CONFIDENCE_AVOID
                ]
                if safe_pigs:
                    p2_pigs = safe_pigs

            if p2_pigs:
                p2_pigs.sort(key=lambda p: board_colors.get(p[2], 0))
                best = p2_pigs[0]
                return self._make_action(best, board_colors, len(colored_pigs), "P2:fewest-cells")

            # --- P2.5: Unknown color pigs — tap when no better colored option ---
            if unknown_pigs:
                px, py, _ = unknown_pigs[0]
                self.record_tap(0)
                return Action(
                    "tap", px, py, 2.5,
                    f"[P2.5:unknown-pig] Tap ? pig (no non-cooldown colored pigs)"
                )

            # --- P3: Any non-cooldown pig (color may not be on board) ---
            p3_pigs = [
                (x, y, cid) for x, y, cid in queue_pigs
                if cid > 0 and not self._is_on_cooldown(cid)
            ]
            if p3_pigs:
                best = p3_pigs[0]
                return self._make_action(best, board_colors, len(queue_pigs), "P3:any-non-cd")

            # --- P4: Ignore cooldown (last resort) ---
            best = colored_pigs[0]
            return self._make_action(best, board_colors, len(colored_pigs), "P4:ignore-cd")

        # No colored pigs matched board — try unknown pigs
        if unknown_pigs:
            px, py, _ = unknown_pigs[0]
            self.record_tap(0)
            return Action(
                "tap", px, py, 2.5,
                f"[P2.5:unknown-pig] Tap ? pig (no colored pigs match board)"
            )

        # Pigs detected but colors don't match board — tap first anyway
        if no_match_pigs:
            px, py, pcid = no_match_pigs[0]
            color_name = COLOR_NAMES.get(pcid, "?")
            self.record_tap(pcid)
            return Action(
                "tap", px, py, 2.5,
                f"[P3:no-match] Tap pig color={color_name} "
                f"(0 board cells, but only option)"
            )

        # Any remaining pigs (fallback)
        if queue_pigs:
            px, py, pcid = queue_pigs[0]
            color_name = COLOR_NAMES.get(pcid, "?")
            self.record_tap(pcid)
            return Action(
                "tap", px, py, 2.5,
                f"[P5:fallback] Tap pig color={color_name} (last resort)"
            )

        # No pigs — wait for conveyor
        return None

    def _make_action(
        self,
        pig: Tuple[int, int, int],
        board_colors: Dict[int, int],
        queue_count: int,
        reason: str,
    ) -> Action:
        bx, by, bcid = pig
        remaining = board_colors.get(bcid, 0)
        color_name = COLOR_NAMES.get(bcid, "?")
        self.record_tap(bcid)
        return Action(
            "tap", bx, by, 2.5,
            f"[{reason}] Tap pig color={color_name} "
            f"(remaining={remaining} cells, queue={queue_count} pigs)"
        )


# ---------------------------------------------------------------------------
# Smart Player
# ---------------------------------------------------------------------------
class SmartPixelFlowPlayer:
    """Vision-based autonomous PixelFlow player.

    Integrates:
      - YOLO screen classifier
      - cell_aware_analyzer board parser
      - PIL queue pig detection + color matching
      - Holder slot parsing
      - Color-priority strategy
    """

    def __init__(
        self,
        adb_path: str = ADB,
        device: str = SERIAL,
        temp_dir: Optional[Path] = None,
        log_file: Optional[Path] = None,
    ):
        self.adb = adb_path
        self.device = device
        self.temp_dir = temp_dir or Path(
            "E:/AI/virtual_player/data/games/pixelflow/temp/smart"
        )
        self.log_file = log_file or Path(
            "E:/AI/virtual_player/data/games/pixelflow/smart_player_log.txt"
        )

        # Modules
        self.playbook = create_pixelflow_playbook()
        self.classifier = ScreenClassifier(YOLO_MODEL_PATH)
        self.profile = load_profile(str(CELL_PROFILE_PATH))
        self.board_parser = BoardParser(self.profile)
        self.strategy = Strategy()
        self.ai_db = AIPlayDB()
        self.play_db_ref = PlayDBReference()
        self.fingerprint_searcher = FingerprintSearcher()

        # State
        self._turn = 0
        self._screenshot_fails = 0
        self._last_recovery_tier = 0  # 0=none, 1/2/3 = last attempted recovery
        self._image_load_fails = 0    # consecutive cv2.imread failures
        self._dumpsys_fails = 0       # consecutive dumpsys failures
        self._slow_iter_count = 0     # consecutive slow iterations (>30s)
        self._intentional_sleep_seconds = 0.0  # subtracted from iter time in watchdog
        self._games_started = 0
        self._games_won = 0
        self._games_failed = 0
        self._same_screen_count = 0
        self._last_screen = ""
        self._non_gameplay_streak = 0
        self._problem_screen_streak = 0  # screens that aren't real progress (popup/fail/unknown/loading)
        self._recent_outcomes: deque = deque(maxlen=10)  # session outcome history

        # Session / learning state
        self._session_id: Optional[str] = None
        self._session_turn_count: int = 0
        self._prev_board_cells: int = 0
        self._stall_turns: int = 0  # Consecutive turns with no board change
        self._last_action_color: str = ""
        self._last_action_x: int = 0
        self._last_action_y: int = 0

        # Heart management
        self._consecutive_lobby: int = 0
        self._heart_wait_until: float = 0
        self._HEART_REGEN_SECONDS: int = 900  # 15분 대기 (하트 1개 충전)

        # Exploration mode — activated when stuck
        self._explore_mode: bool = False
        self._explore_index: int = 0
        self._explore_last_cells: int = 0
        self._explore_last_ncolors: int = 0
        self._explore_last_tap: Tuple[int, int] = (0, 0)
        # Exploration zones: Cycle 10 2026-04-09. Cycles 6-9 plateaued at
        # ~250 cells because the holder kept locking to a single colour and
        # only one queue tap (660,1500) was discovered each session. Move
        # holder sacrifice to the FRONT so each session begins by clearing
        # one slot — that should let new colours enter and unblock progress.
        self._EXPLORE_ZONES = [
            # Holder slots first (sacrifice to free a stuck colour slot)
            (185, 930), (310, 930), (435, 930), (560, 930), (685, 930),
            # Queue area (y ~ 1400-1700) — primary tap target
            (280, 1500), (400, 1500), (530, 1500), (660, 1500), (780, 1500),
            (280, 1600), (400, 1600), (530, 1600), (660, 1600), (780, 1600),
            (380, 1400), (530, 1400), (700, 1400),
            (380, 1700), (530, 1700), (700, 1700),
            # Board centre (chain/lock interactions — last resort)
            (400, 400), (540, 400), (680, 400),
            (400, 550), (540, 550), (680, 550),
            (400, 700), (540, 700), (680, 700),
            # UI elements (undo, hint buttons)
            (100, 860), (980, 860),
        ]

    def run(self, duration_minutes: int = 60):
        """Main loop."""
        target = datetime.now() + timedelta(minutes=duration_minutes)
        self._log("=" * 60)
        self._log("Smart PixelFlow Player START")
        self._log(f"Duration: {duration_minutes} min | Target: {target:%H:%M:%S}")
        self._log(f"ADB: {self.adb} | Device: {self.device}")
        self._log(f"YOLO: {YOLO_MODEL_PATH.name}")
        self._log(f"Profile: {CELL_PROFILE_PATH.name}")
        fp_status = "loaded" if self.fingerprint_searcher.is_available else "unavailable"
        self._log(f"Fingerprint DB: {FINGERPRINT_DB_PATH.name} ({fp_status})")
        self._log(f"FP threshold: {FP_SIMILARITY_THRESHOLD}, top_k: {FP_TOP_K}")
        self._log("=" * 60)

        try:
            self._game_loop(target)
        except KeyboardInterrupt:
            self._log("Interrupted by user")
        except Exception as e:
            self._log(f"FATAL: {e}")
            import traceback
            self._log(traceback.format_exc())
        finally:
            self._end_session("timeout")
            self._print_report()
            self.ai_db.close()
            self.play_db_ref.close()
            self.fingerprint_searcher.close()
            self.classifier.shutdown()

    def _force_recovery(self, tier: int):
        """Run an ADB recovery tier directly, used by non-screenshot paths
        (image-load failures, slow-iter watchdog, etc.).

        Does NOT touch _screenshot_fails so the regular escalation ladder
        keeps its own state.
        """
        self._log(f"  >> ADB FORCE RECOVERY Tier {tier}")
        ok = False
        if tier == 1:
            ok = adb_recover_tier1(self.adb, self.device)
        elif tier == 2:
            ok = adb_recover_tier2(self.adb, self.device)
        elif tier == 3:
            ok = adb_recover_tier3(self.adb, self.device)
        if ok:
            self._log(f"  >> Tier {tier} succeeded — relaunching app")
            adb_relaunch(self.adb, self.device)
        else:
            self._log(f"  >> Tier {tier} FAILED")

    def _handle_screenshot_failure(self):
        """Escalating ADB recovery when screenshots fail.

        Tier 1 (30 fails)  : restart adb server only           ~5s
        Tier 2 (100 fails) : relaunch BlueStacks HD-Player    ~30s
        Tier 3 (300 fails) : full BlueStacks helper restart   ~60s
        After Tier 3 we keep trying Tier 3 every 300 fails.
        """
        n = self._screenshot_fails

        # Periodic status log every 10 fails
        if n % 10 == 0:
            self._log(f"T{self._turn}: Screenshot failed x{n}")

        # Decide which tier (only attempt each tier once per outage)
        target_tier = 0
        if n >= 300 and self._last_recovery_tier < 3:
            target_tier = 3
        elif n >= 100 and self._last_recovery_tier < 2:
            target_tier = 2
        elif n >= 30 and self._last_recovery_tier < 1:
            target_tier = 1
        elif n >= 600 and n % 300 == 0:
            # Stuck for very long even after tier 3 — try tier 3 again
            target_tier = 3

        if target_tier == 0:
            time.sleep(2)
            return

        self._log(f"  >> ADB RECOVERY Tier {target_tier} (after {n} fails)")
        ok = False
        if target_tier == 1:
            ok = adb_recover_tier1(self.adb, self.device)
        elif target_tier == 2:
            ok = adb_recover_tier2(self.adb, self.device)
        elif target_tier == 3:
            ok = adb_recover_tier3(self.adb, self.device)

        self._last_recovery_tier = target_tier
        if ok:
            self._log(f"  >> Tier {target_tier} succeeded — relaunching app")
            adb_relaunch(self.adb, self.device)
        else:
            self._log(f"  >> Tier {target_tier} FAILED")

    # Iteration watchdog thresholds
    _ITER_SLOW_THRESHOLD = 30.0   # log warning above this many seconds
    _ITER_SLOW_LIMIT = 5          # consecutive slow iters → escalate

    def _game_loop(self, target: datetime):
        while datetime.now() < target:
            self._turn += 1
            iter_start = time.time()
            self._intentional_sleep_seconds = 0.0  # subtracted from elapsed in watchdog
            try:
                # 1. Screenshot
                img_path = adb_screenshot(self.adb, self.device, self.temp_dir)
                if not img_path:
                    self._screenshot_fails += 1
                    self._handle_screenshot_failure()
                    continue
                if self._screenshot_fails > 0:
                    self._log(f"T{self._turn}: Screenshot recovered after {self._screenshot_fails} fails")
                self._screenshot_fails = 0
                self._last_recovery_tier = 0

                # 2. Check if we're still in PixelFlow (every 5 turns to reduce overhead)
                if self._turn % 5 == 0:
                    try:
                        fg = subprocess.run(
                            [self.adb, "-s", self.device, "shell", "dumpsys", "window"],
                            capture_output=True, text=True, timeout=5,
                            encoding='utf-8', errors='ignore',
                        )
                        # Reset dumpsys fail counter on success
                        if self._dumpsys_fails > 0:
                            self._dumpsys_fails = 0
                        if PACKAGE not in fg.stdout:
                            self._log(f"T{self._turn}: AD REDIRECT detected")
                            adb_back(self.adb, self.device)
                            time.sleep(1)
                            adb_back(self.adb, self.device)
                            time.sleep(2)
                            fg2 = subprocess.run(
                                [self.adb, "-s", self.device, "shell", "dumpsys", "window"],
                                capture_output=True, text=True, timeout=5,
                                encoding='utf-8', errors='ignore',
                            )
                            if PACKAGE not in fg2.stdout:
                                self._log(f"  Still outside, relaunching")
                                adb_relaunch(self.adb, self.device)
                            continue
                    except subprocess.TimeoutExpired:
                        self._dumpsys_fails += 1
                        if self._dumpsys_fails % 5 == 1:
                            self._log(f"T{self._turn}: dumpsys timeout x{self._dumpsys_fails}")
                    except Exception as e:
                        self._dumpsys_fails += 1
                        if self._dumpsys_fails % 5 == 1:
                            self._log(f"T{self._turn}: dumpsys error: {type(e).__name__}")

                # 3. YOLO classify
                screen = self.classifier.classify(img_path)

                # 3a. Override YOLO misclassification BEFORE stuck tracking:
                #     YOLO classifies gameplay as "stage_start" — detect board to correct
                if screen in ("stage_start", "lobby"):
                    if self._has_board(img_path):
                        screen = "gameplay"

                # 3b. Update stuck counter with the corrected screen value
                self._update_stuck(screen)

                # Issue F: STUCK detection — same screen 50 turns (was 150)
                if self._same_screen_count >= 50:
                    self._log(f"T{self._turn}: STUCK ({screen} x{self._same_screen_count}), relaunch")
                    adb_relaunch(self.adb, self.device)
                    self._same_screen_count = 0
                    self._non_gameplay_streak = 0
                    self._problem_screen_streak = 0
                    continue

                # Non-gameplay loop (store/popup trap)
                # Issue E: loading is NOT a "safe" screen — only gameplay/lobby/win/stage_start reset
                if screen in ("gameplay", "lobby", "stage_start", "win"):
                    self._non_gameplay_streak = 0
                else:
                    self._non_gameplay_streak += 1

                # FIX 2026-04-08: reduced 8 -> 5 after cycle 1 observed 4 popup
                # loops wasting ~40s each. Popup screens after a failed session
                # rarely recover via tapping — better to relaunch fast.
                if self._non_gameplay_streak >= 5:
                    self._log(f"T{self._turn}: POPUP LOOP ({screen}), relaunch")
                    adb_relaunch(self.adb, self.device)
                    self._non_gameplay_streak = 0
                    self._same_screen_count = 0
                    self._problem_screen_streak = 0
                    continue

                # Issue G: problem-screen streak — popup/fail/unknown/loading without real progress
                # Only resets on genuine gameplay/lobby/win/stage_start
                # Detects popup⇄loading ping-pong that defeats _non_gameplay_streak
                if screen in ("gameplay", "lobby", "stage_start", "win"):
                    self._problem_screen_streak = 0
                elif screen in ("popup", "fail", "fail_result", "fail_outofspace",
                                "loading", "unknown"):
                    self._problem_screen_streak += 1

                if self._problem_screen_streak >= 15:
                    self._log(
                        f"T{self._turn}: PROBLEM STREAK ({screen} x{self._problem_screen_streak}), relaunch"
                    )
                    adb_relaunch(self.adb, self.device)
                    self._problem_screen_streak = 0
                    self._non_gameplay_streak = 0
                    self._same_screen_count = 0
                    continue

                if screen != "gameplay":
                    self._handle_non_gameplay(screen, img_path=img_path)
                    continue

                # 4. Gameplay → vision + strategy
                self._consecutive_lobby = 0  # Reset heart counter on gameplay entry
                self._handle_gameplay(img_path)

            except Exception as e:
                self._log(f"T{self._turn}: ERROR: {e}")
                time.sleep(3)
            finally:
                # Issue A: iteration watchdog (subtract intentional sleeps)
                raw_elapsed = time.time() - iter_start
                elapsed = raw_elapsed - self._intentional_sleep_seconds
                if elapsed > self._ITER_SLOW_THRESHOLD:
                    self._slow_iter_count += 1
                    self._log(
                        f"T{self._turn}: SLOW ITER {elapsed:.1f}s "
                        f"(consecutive x{self._slow_iter_count})"
                    )
                    if self._slow_iter_count >= self._ITER_SLOW_LIMIT:
                        self._log(
                            f"  >> {self._slow_iter_count} slow iters in a row — forcing ADB recovery"
                        )
                        self._screenshot_fails = 100  # jump to Tier 2
                        self._handle_screenshot_failure()
                        self._slow_iter_count = 0
                else:
                    self._slow_iter_count = 0

    def _has_board(self, img_path: Path) -> bool:
        """Quick check: is there a game board in the screenshot?

        The board has a distinctive pattern: DarkPurple(c21) frame surrounding
        colored tiles in a grid. Check for the presence of DarkPurple frame
        pixels in the board region — lobby/stage_start screens don't have this.
        """
        try:
            img = cv2.imread(str(img_path))
            if img is None:
                return False
            board = img[BOARD_Y1:BOARD_Y2, BOARD_X1:BOARD_X2]
            # DarkPurple frame: render_mean ~(64, 69, 119) in BGR=(119, 69, 64)
            # Check left edge of board region for DarkPurple pixels
            edge = board[:, :30, :]  # left 30 pixels
            b, g, r = edge[:, :, 0], edge[:, :, 1], edge[:, :, 2]
            # DarkPurple: R=50-80, G=55-80, B=100-135
            dark_purple = ((r > 45) & (r < 85) & (g > 50) & (g < 85) &
                           (b > 95) & (b < 140))
            dp_ratio = dark_purple.sum() / max(edge.shape[0] * edge.shape[1], 1)
            # Board frame should have >30% DarkPurple on left edge
            return dp_ratio > 0.30
        except Exception:
            return False

    def _is_hearts_popup(self, img_path: Path) -> bool:
        """Pixel-based detection for the '하트를 채워요!' (hearts empty) popup.

        YOLO misclassifies this popup as 'fail', causing an infinite tap loop.
        The popup has a distinctive bright-yellow '받기 +1' (watch-ad) button
        in a consistent region, which we detect by counting yellow pixels.

        Empirical signature (from diag_frames/frame_002.png):
          - ~19,669 bright yellow pixels in (x:200-500, y:1100-1250)
          - Color: BGR ~ (41, 186, 247) which is RGB(247, 186, 41)
          - Button centroid: (375, 1168)

        Returns True if the yellow-button pixel count exceeds threshold.
        """
        try:
            img = cv2.imread(str(img_path))
            if img is None:
                return False
            # cv2 loads as BGR
            zone = img[1100:1250, 200:500]  # (y, x)
            b = zone[:, :, 0]
            g = zone[:, :, 1]
            r = zone[:, :, 2]
            yellow = (r > 200) & (g > 170) & (b < 120)
            count = int(yellow.sum())
            return count > 3000  # conservative threshold (~15% of region)
        except Exception:
            return False

    def _handle_non_gameplay(self, screen: str, img_path: Optional[Path] = None):
        """Execute playbook actions for non-gameplay screens.

        Issue #2: lobby/stage_start use hardcoded play button (540,1450).
        Issue #3: fail/popup try multiple close positions.
        Issue #4: win tries multiple continue positions.
        Issue #6: session starts on gameplay entry, NOT on lobby.
        FIX 2026-04-08: pixel-detect hearts-empty popup (YOLO misreads it as 'fail').
        """
        # Heart wait check — if waiting, sleep until hearts regen
        if time.time() < self._heart_wait_until:
            remaining = int(self._heart_wait_until - time.time())
            if remaining > 0:
                # Issue D: chunked sleep so the loop can detect ADB death mid-wait
                self._log(f"T{self._turn}: [{screen}] HEARTS WAIT: {remaining}s remaining, sleeping in 5s chunks...")
                chunks = min(6, max(1, remaining // 5))  # at most 30s before re-loop
                for _ in range(chunks):
                    if time.time() >= self._heart_wait_until:
                        break
                    time.sleep(5)
                    self._intentional_sleep_seconds += 5.0
                    # Quick health check between chunks
                    if not adb_health_check(self.adb, self.device):
                        self._log(f"  ADB died during heart wait — aborting wait")
                        self._heart_wait_until = 0
                        return
                # Heart wait is intentional — reset stuck counters so the
                # watchdogs don't fire on lobby x N during regen
                self._same_screen_count = 0
                self._problem_screen_streak = 0
                self._non_gameplay_streak = 0
                return
            else:
                # Heart wait just ended — reset lobby counter to avoid immediate re-trigger
                self._consecutive_lobby = 0
                self._heart_wait_until = 0

        # --- Track game state transitions BEFORE action selection ---
        # Heart depletion detection: lobby appears repeatedly without gameplay in between
        if screen == "lobby":
            self._consecutive_lobby += 1
            if self._consecutive_lobby >= 5:
                # 5x lobby in a row = no hearts left
                self._heart_wait_until = time.time() + self._HEART_REGEN_SECONDS
                self._consecutive_lobby = 0
                self._log(
                    f"T{self._turn}: HEARTS DEPLETED — lobby x{5}, "
                    f"waiting {self._HEART_REGEN_SECONDS}s for regen"
                )
                return
            self._games_started += 1
            # Issue #6: Do NOT start session here — session starts on gameplay entry
        else:
            self._consecutive_lobby = 0

        if screen in ("win",):
            self._games_won += 1
            self._end_session("win")
        elif screen in ("fail", "fail_result", "fail_outofspace"):
            self._games_failed += 1
            self._end_session("fail")

        # --- Issue #2: lobby/stage_start → hardcoded play button (skip PlayDB) ---
        if screen in ("lobby", "stage_start"):
            self._log(f"T{self._turn}: [{screen}] Hardcoded play button (540,1450)")
            adb_tap(self.adb, self.device, 540, 1450)
            time.sleep(2.0)
            return

        # --- Issue #4: win → try multiple continue button positions ---
        if screen == "win":
            self._log(f"T{self._turn}: [{screen}] Multi-tap continue positions")
            for wx, wy in [(540, 1500), (540, 1200), (540, 800)]:
                adb_tap(self.adb, self.device, wx, wy)
                time.sleep(1.0)
            return

        # --- Issue #3: fail/popup → try multiple close/retry positions ---
        if screen in ("fail", "fail_result", "fail_outofspace", "popup"):
            # FIX 2026-04-08: hearts-empty popup is misclassified as 'fail' by YOLO.
            # Pixel-detect the bright yellow 받기 +1 button — if present, this is
            # NOT a real fail screen but a heart-exhaustion popup. Trigger the
            # existing heart-wait flow instead of tapping blindly.
            if img_path is not None and self._is_hearts_popup(img_path):
                self._log(
                    f"T{self._turn}: [{screen}] HEARTS-EMPTY popup detected "
                    f"(pixel match). Waiting {self._HEART_REGEN_SECONDS}s for regen."
                )
                self._heart_wait_until = time.time() + self._HEART_REGEN_SECONDS
                # Reset watchdogs so they don't fire while we wait
                self._same_screen_count = 0
                self._non_gameplay_streak = 0
                self._problem_screen_streak = 0
                # Undo the accidental end_session(fail) triggered above
                self._games_failed = max(0, self._games_failed - 1)
                return
            self._log(f"T{self._turn}: [{screen}] Multi-tap close/retry positions")
            for cx, cy in [(825, 340), (540, 850), (540, 1200), (540, 1500)]:
                adb_tap(self.adb, self.device, cx, cy)
                time.sleep(0.8)
            return

        # --- Other screens: try PlayDB human patterns ---
        human_taps = self.play_db_ref.get_screen_actions(screen, top_k=3)
        if human_taps:
            self._log(
                f"T{self._turn}: [{screen}] PlayDB: {len(human_taps)} patterns, "
                f"trying top 2"
            )
            for ax, ay, cnt in human_taps[:2]:
                adb_tap(self.adb, self.device, ax, ay)
                time.sleep(1.5)
            return

        # --- Fallback to playbook handler ---
        handler = self.playbook.screen_handlers.get(screen)
        if not handler:
            handler = self.playbook.screen_handlers.get("unknown")

        if not handler:
            self._log(f"T{self._turn}: [{screen}] No handler, back")
            adb_back(self.adb, self.device)
            time.sleep(1)
            return

        self._log(f"T{self._turn}: [{screen}] → {len(handler.actions)} actions")
        for action in handler.actions:
            self._execute_action(action)

    def _compute_fingerprint(self, board_colors: Dict[int, int]) -> List[float]:
        """Compute a 29-dim L2-normalized fingerprint from board color counts.

        Matches the fingerprint format stored in fingerprint.db:
        each dimension = proportion of that color_id (1..29) among total cells,
        then L2-normalized.
        """
        total_cells = sum(board_colors.values())
        fp = [0.0] * 29
        if total_cells > 0:
            for cid, cnt in board_colors.items():
                if 1 <= cid <= 29:
                    fp[cid - 1] = cnt / total_cells
        norm = sum(v * v for v in fp) ** 0.5
        if norm > 0:
            fp = [v / norm for v in fp]
        return fp

    def _handle_gameplay(self, img_path: Path):
        """Parse board, search fingerprint DB for human-like action, execute, record results.

        Decision flow:
          1. Parse board -> color distribution -> 29-dim fingerprint
          2. Search fingerprint.db for similar past human board states
          3. Pick best match (delta < 0 preferred, similarity > threshold)
          4. Fallback: round-robin pig tap if no good fingerprint match
          5. Exploration mode (stall 5+): fingerprint search first, then fallback zones
        """
        t0 = time.time()

        # Load image
        img_cv = cv2.imread(str(img_path))
        try:
            img_arr = np.array(Image.open(img_path))
        except Exception:
            img_arr = None

        if img_cv is None or img_arr is None:
            self._image_load_fails += 1
            self._log(
                f"T{self._turn}: [gameplay] Image load failed x{self._image_load_fails}"
            )
            # Escalate: if image keeps failing, the screenshot stream is corrupt
            # Treat it like an ADB outage and trigger recovery
            if self._image_load_fails >= 10:
                self._log(
                    f"  >> Image load failed {self._image_load_fails}x — forcing ADB recovery"
                )
                # Force Tier-2 recovery without polluting screenshot_fails counter
                self._force_recovery(tier=2)
                self._image_load_fails = 0
            else:
                time.sleep(2)
            return
        # Reset on successful load
        self._image_load_fails = 0

        # 4a. Parse board -> remaining colors
        board_colors = self.board_parser.parse(img_cv)
        total_cells = sum(board_colors.values())
        n_colors = len(board_colors)

        # -- Turn result tracking: compare with previous board state --
        delta = total_cells - self._prev_board_cells if self._prev_board_cells > 0 else 0
        if self._prev_board_cells > 0 and self._last_action_color and self._session_id:
            is_good = delta < 0  # Negative delta = cells decreased = progress
            # Record the PREVIOUS action's result
            occupied_prev = sum(1 for s in parse_holder(img_arr, self.board_parser) if s > 0)
            try:
                self.ai_db.record_turn(
                    session_id=self._session_id,
                    screen_type="gameplay",
                    board_cells=self._prev_board_cells,
                    board_colors=n_colors,
                    action_type="tap",
                    action_x=self._last_action_x,
                    action_y=self._last_action_y,
                    action_color=self._last_action_color,
                    result_delta=delta,
                    holder_occupied=occupied_prev,
                )
                self.ai_db.update_pattern(
                    board_color_count=n_colors,
                    holder_occupied=occupied_prev,
                    action_color=self._last_action_color,
                    is_good=is_good,
                )
            except Exception as e:
                self._log(f"  [DB] Record error: {e}")

        # Stall detection: no change for many turns -> enter exploration mode
        if self._prev_board_cells > 0 and delta == 0:
            self._stall_turns += 1
        elif delta < 0:
            # Progress! If we were exploring, record the successful tap
            if self._explore_mode and self._explore_last_tap != (0, 0):
                ctx = f"cells_{self._explore_last_cells}_colors_{self._explore_last_ncolors}"
                self.ai_db.record_explore(ctx, self._explore_last_tap[0],
                                          self._explore_last_tap[1], worked=True)
                self._log(f"  [LEARN] Explore tap ({self._explore_last_tap[0]},{self._explore_last_tap[1]}) WORKED! (d={delta})")
            self._stall_turns = 0
            self._explore_mode = False
            self._explore_index = 0
        else:
            # Board changed but not progress (noise) -- partial reset
            if self._stall_turns > 0:
                self._stall_turns = max(0, self._stall_turns - 1)

        # Enter exploration mode after N stall turns
        # Cycle 8 2026-04-09: 5 -> 3. Cycle 6/7 showed each session produced
        # exactly one WORKED tap (30-40 cell drop) then re-stalled into a fail.
        # Reaching explore faster lets us chain multiple successful taps inside
        # a single session before the game-over screen fires.
        STALL_THRESHOLD = 3
        if self._stall_turns >= STALL_THRESHOLD and not self._explore_mode:
            self._explore_mode = True
            self._explore_index = 0
            self._explore_last_cells = total_cells
            self._explore_last_ncolors = n_colors
            self._log(f"  [EXPLORE] Entering exploration mode (stall x{self._stall_turns})")

        # Give up after extensive exploration (50 explore attempts)
        if self._stall_turns >= STALL_THRESHOLD + 50:
            self._log(f"T{self._turn}: STUCK after exploration ({self._stall_turns} turns)")
            self._end_session("stuck")
            self._stall_turns = 0
            self._explore_mode = False

        # FIX 2026-04-09: Board stagnation / growth abandonment.
        # Cycle 2: sessions 3 & 4 ran 50 turns while cells grew 272->287.
        # Cycle 3: BOARD GROWING never fired because deltas were +0 (not +1).
        # New heuristic: if no progress (delta >= 0) for 20 straight turns while
        # holder is ~saturated, abandon and relaunch — the level is unwinnable
        # from this state.
        if not hasattr(self, "_no_progress_streak"):
            self._no_progress_streak = 0
        if delta >= 0:
            self._no_progress_streak += 1
        else:
            self._no_progress_streak = 0
        if self._no_progress_streak >= 20:
            self._log(
                f"T{self._turn}: NO PROGRESS {self._no_progress_streak} turns "
                f"(cells={total_cells}) — abandoning session + relaunch"
            )
            self._end_session("stuck")
            self._no_progress_streak = 0
            self._stall_turns = 0
            self._explore_mode = False
            adb_relaunch(self.adb, self.device)
            return

        # Auto-start session if not yet active (gameplay detected without lobby)
        if self._session_id is None:
            self._start_session(start_cells=total_cells)

        # Board cleared check (must be BEFORE updating _prev_board_cells)
        if total_cells == 0 and self._prev_board_cells > 0:
            self._log(f"T{self._turn}: Board cleared! (win)")
            self._end_session("win")
            return

        # Update prev board cells AFTER board-clear check
        self._prev_board_cells = total_cells

        # ------------------------------------------------------------------
        # 4b. Fingerprint-based action selection
        # ------------------------------------------------------------------
        # Compute current board fingerprint (29-dim)
        current_fp = self._compute_fingerprint(board_colors)

        # Search fingerprint.db for similar human board states
        fp_action = None
        fp_matches = self.fingerprint_searcher.search(current_fp, top_k=FP_TOP_K)

        if fp_matches:
            # Issue #5: Filter to delta < 0 (actual progress) AND pig queue region
            # Pig queue region: y:1400-1700, x:300-750 (where queue pigs live)
            # FIX 2026-04-08: widened 1400-1600 -> 1400-1700 after analysing
            # 2604 WIN delta<0 rows — 2495 sit in 1400-1700 (was missing ~100 valid taps).
            filtered = [
                m for m in fp_matches
                if m["delta"] < 0
                and 300 <= m["action_x"] <= 750
                and 1400 <= m["action_y"] <= 1700
            ]
            # If no filtered matches, allow any delta < 0 match (broader region)
            if not filtered:
                filtered = [m for m in fp_matches if m["delta"] < 0]

            if filtered:
                # Skip FP if stalling too long — FP keeps picking same ineffective taps
                # FIX 2026-04-09: Cycle 2 showed sessions of 50 turns all stuck on
                # same ~5 FP coords. Drop from 10 -> 5 so explore kicks in sooner.
                if self._stall_turns < 5:
                    # Cycle 9 2026-04-09: tighter dedup. Cycle 8 showed (660,1500)
                    # being replayed every session with diminishing returns
                    # (d=-39 -> -3 -> -1). Larger window + finer grid spreads
                    # taps more aggressively across the queue.
                    recent = getattr(self, "_recent_fp_cells", None)
                    if recent is None:
                        recent = deque(maxlen=8)
                        self._recent_fp_cells = recent
                    recent_set = set(recent)
                    fresh = [
                        m for m in filtered
                        if (m["action_x"] // 30, m["action_y"] // 30) not in recent_set
                    ]
                    pool = fresh if fresh else filtered
                    match_idx = self._session_turn_count % len(pool)
                    best = pool[match_idx]
                    if best["similarity"] >= FP_SIMILARITY_THRESHOLD:
                        fp_action = Action(
                            "tap", best["action_x"], best["action_y"], 2.0,
                            f"[FP:{best['similarity']:.2f}] Human pattern "
                            f"(delta={best['delta']}, id={best['state_id']})"
                        )
                        recent.append(
                            (best["action_x"] // 30, best["action_y"] // 30)
                        )

        # Holder info for logging
        holder_slots = parse_holder(img_arr, self.board_parser)
        occupied = sum(1 for s in holder_slots if s > 0)

        # ------------------------------------------------------------------
        # Action priority:
        #   1. Fingerprint match (both normal and explore mode)
        #   2. Explore mode fallback (AI DB -> PlayDB -> zones)
        #   3. Normal mode fallback (round-robin pig tap)
        # ------------------------------------------------------------------
        QUEUE_PIG_POSITIONS = [
            (380, 1500),   # Left pig
            (530, 1500),   # Center pig
            (700, 1500),   # Right pig
        ]

        action = None

        if fp_action is not None:
            # Fingerprint DB match -- use human pattern
            action = fp_action
        elif self._explore_mode:
            # --- EXPLORATION MODE (no fingerprint match) ---
            ctx = f"cells_{self._explore_last_cells}_colors_{self._explore_last_ncolors}"
            known_good_raw = self.ai_db.get_best_explore(ctx, top_k=8)
            playdb_gameplay_raw = self.play_db_ref.get_gameplay_sequence(limit=10)

            # FIX 2026-04-09 Cycle 5: filter out taps below y=1750. Cycle 3/4
            # showed (876, 1784) had conf 1.00 in AI_DB but it hits a 'next
            # level' / ad popup trigger, producing fake wins that end sessions
            # without any real gameplay. Keep explores inside the actual play
            # area (queue pigs live at y≈1400-1700).
            known_good = [
                (x, y, c) for (x, y, c) in known_good_raw
                if y <= 1750 and 50 <= x <= 1030
            ][:3]
            playdb_positions = [
                (px, py) for px, py in playdb_gameplay_raw
                if py <= 1750 and 50 <= px <= 1030
            ]

            n_ai = len(known_good)
            n_playdb = len(playdb_positions)

            if self._explore_index < n_ai:
                ex, ey, conf = known_good[self._explore_index]
                action = Action("tap", ex, ey, 1.5,
                    f"[EXPLORE:AI_DB] Tap ({ex},{ey}) conf={conf:.2f}")
                self._explore_last_tap = (ex, ey)
                self._explore_index += 1
            elif self._explore_index < n_ai + n_playdb:
                pdb_idx = self._explore_index - n_ai
                ex, ey = playdb_positions[pdb_idx]
                action = Action("tap", ex, ey, 1.5,
                    f"[EXPLORE:PlayDB] Tap ({ex},{ey}) human pattern #{pdb_idx+1}")
                self._explore_last_tap = (ex, ey)
                self._explore_index += 1
            else:
                # Record failure for the PREVIOUS explore tap (if it didn't help)
                if (self._explore_last_tap != (0, 0)
                        and delta >= 0
                        and self._stall_turns > STALL_THRESHOLD):
                    self.ai_db.record_explore(
                        ctx, self._explore_last_tap[0],
                        self._explore_last_tap[1], worked=False)

                zone_idx = (self._explore_index - n_ai - n_playdb) % len(self._EXPLORE_ZONES)
                ex, ey = self._EXPLORE_ZONES[zone_idx]
                action = Action("tap", ex, ey, 1.5,
                    f"[EXPLORE:ZONE:{zone_idx}] Tap zone ({ex},{ey})")
                self._explore_last_tap = (ex, ey)
                self._explore_index += 1
        else:
            # --- NORMAL MODE fallback: round-robin pig tapping ---
            pig_index = self._session_turn_count % len(QUEUE_PIG_POSITIONS)
            px, py = QUEUE_PIG_POSITIONS[pig_index]
            action = Action("tap", px, py, 2.0,
                f"[Fallback] Round-robin pig #{pig_index+1} at ({px},{py})")

        elapsed = time.time() - t0
        self._session_turn_count += 1

        # Log
        color_summary = ", ".join(
            f"{COLOR_NAMES.get(cid, '?')}:{cnt}"
            for cid, cnt in sorted(board_colors.items(), key=lambda x: -x[1])[:5]
        )
        mode_str = "FP" if fp_action is not None else ("EXPLORE" if self._explore_mode else "NORMAL")
        fp_info = ""
        if fp_matches:
            fp_info = f" fp_top={fp_matches[0]['similarity']:.2f}"
        pig_summary = f"{mode_str} stall={self._stall_turns}{fp_info}"
        holder_summary = "/".join(
            COLOR_NAMES.get(s, "-") if s > 0 else "_" for s in holder_slots
        )
        delta_str = f" d={delta:+d}" if self._prev_board_cells > 0 else ""

        self._log(
            f"T{self._turn}: [gameplay] "
            f"Board={total_cells}cells/{n_colors}colors{delta_str} "
            f"[{color_summary}] | "
            f"Queue=[{pig_summary}] | "
            f"Holder=[{holder_summary}] ({occupied}/5) | "
            f"{elapsed:.1f}s"
        )

        # 4f. Execute and track what we did
        if action:
            self._log(f"  -> {action}")
            self._execute_action(action)
            # Track what we tapped for learning
            if fp_action is not None:
                self._last_action_color = f"fp_{action.x}_{action.y}"
            elif self._explore_mode:
                self._last_action_color = f"explore_{action.x}_{action.y}"
            else:
                self._last_action_color = f"pig_{action.x}_{action.y}"
            self._last_action_x = action.x
            self._last_action_y = action.y
        else:
            self._log(f"  -> Wait (no action available)")
            self._last_action_color = ""
            time.sleep(2)

    def _start_session(self, start_cells: int = 0):
        """Begin a new AI play session."""
        if self._session_id is not None:
            # End previous session if still open
            self._end_session("interrupted")
        self._session_id = uuid.uuid4().hex[:12]
        self._session_turn_count = 0
        self._prev_board_cells = start_cells
        self._stall_turns = 0
        self._last_action_color = ""
        try:
            self.ai_db.start_session(self._session_id, start_cells)
            self._log(f"  [SESSION] Started {self._session_id} (start_cells={start_cells})")
        except Exception as e:
            self._log(f"  [SESSION] Start error: {e}")

    def _end_session(self, outcome: str):
        """End the current AI play session."""
        if self._session_id is None:
            return
        try:
            self.ai_db.end_session(
                self._session_id, outcome,
                self._session_turn_count, self._prev_board_cells,
            )
            self._log(
                f"  [SESSION] Ended {self._session_id}: {outcome} "
                f"({self._session_turn_count} turns, end_cells={self._prev_board_cells})"
            )
        except Exception as e:
            self._log(f"  [SESSION] End error: {e}")
        # Issue J: track outcomes for fail-rate watchdog
        if outcome not in ("timeout", "interrupted"):
            self._recent_outcomes.append(outcome)
            self._check_session_failrate()
        self._session_id = None
        self._session_turn_count = 0
        self._prev_board_cells = 0
        self._stall_turns = 0
        self._last_action_color = ""

    def _check_session_failrate(self):
        """Issue J: detect chronic session failures and trigger recovery.

        If the last 10 sessions are all non-win, the AI is clearly stuck in a
        bad pattern (wrong level, broken vision, etc.). Force a relaunch and
        give the game a brief cool-down before resuming.
        """
        if len(self._recent_outcomes) < 10:
            return
        wins = sum(1 for o in self._recent_outcomes if o == "win")
        if wins == 0:
            outcomes_str = ",".join(self._recent_outcomes)
            self._log(
                f"  >> SESSION WATCHDOG: 10 sessions, 0 wins [{outcomes_str}] "
                f"— forcing relaunch + 60s cooldown"
            )
            adb_relaunch(self.adb, self.device)
            time.sleep(60)
            # Mark this as intentional so the iteration watchdog doesn't fire
            self._intentional_sleep_seconds += 60.0
            self._recent_outcomes.clear()
            self._same_screen_count = 0
            self._non_gameplay_streak = 0
            self._problem_screen_streak = 0

    def _execute_action(self, action: Action):
        """Execute a single action via ADB."""
        if action.type == "tap":
            adb_tap(self.adb, self.device, action.x, action.y)
        elif action.type == "back":
            adb_back(self.adb, self.device)
        elif action.type == "wait":
            pass  # Just wait
        elif action.type == "relaunch":
            adb_relaunch(self.adb, self.device)

        if action.wait > 0:
            time.sleep(action.wait)

    def _update_stuck(self, screen: str):
        """Track same-screen count for stuck detection."""
        if screen == self._last_screen:
            self._same_screen_count += 1
        else:
            self._same_screen_count = 0
        self._last_screen = screen

    def _print_report(self):
        self._log("")
        self._log("=" * 60)
        self._log("SESSION COMPLETE")
        self._log("=" * 60)
        self._log(f"Total turns:   {self._turn}")
        self._log(f"Games started: {self._games_started}")
        self._log(f"Games won:     {self._games_won}")
        self._log(f"Games failed:  {self._games_failed}")

        self._log(f"AI Play DB: {AI_PLAY_DB_PATH}")
        fp_status = "loaded" if self.fingerprint_searcher.is_available else "unavailable"
        self._log(f"Fingerprint DB: {FINGERPRINT_DB_PATH} ({fp_status})")

        stats = {
            "game": "pixelflow",
            "mode": "smart_player_v3_fingerprint",
            "total_turns": self._turn,
            "games_started": self._games_started,
            "games_won": self._games_won,
            "games_failed": self._games_failed,
            "ai_db_path": str(AI_PLAY_DB_PATH),
            "ended_at": datetime.now().isoformat(),
        }
        stats_path = self.temp_dir / "smart_stats.json"
        stats_path.parent.mkdir(parents=True, exist_ok=True)
        stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
        self._log(f"Stats saved: {stats_path}")

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Smart PixelFlow Player — vision-based autonomous gameplay"
    )
    parser.add_argument(
        "--duration", type=int, default=60,
        help="Duration in minutes (default: 60)",
    )
    parser.add_argument(
        "--adb", type=str, default=ADB,
        help=f"ADB path (default: {ADB})",
    )
    parser.add_argument(
        "--device", type=str, default=SERIAL,
        help=f"Device serial (default: {SERIAL})",
    )
    args = parser.parse_args()

    player = SmartPixelFlowPlayer(adb_path=args.adb, device=args.device)
    player.run(duration_minutes=args.duration)


if __name__ == "__main__":
    main()
