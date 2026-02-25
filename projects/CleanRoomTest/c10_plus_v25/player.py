#!/usr/bin/env python3
"""
C10+ v2.5 Replay Player
=========================
Replays recorded touch events and collects screenshots for the analysis pipeline.

Usage:
  python player.py <game_key>                    # Replay recording + collect screenshots
  python player.py <game_key> --speed 1.5        # 1.5x speed
  python player.py <game_key> --session-split 5  # 5 events per session folder
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from core import (
    SYS_CFG, log, adb_check_device,
    take_screenshot, tap, swipe, get_screen_resolution,
)


# ---------------------------------------------------------------------------
# Replay Engine
# ---------------------------------------------------------------------------

def load_recording(game_key: str) -> Dict:
    """Load recording.json for a game."""
    rec_file = SYS_CFG.base_dir / "recordings" / game_key / "recording.json"
    if not rec_file.exists():
        raise FileNotFoundError(f"No recording found: {rec_file}")
    return json.loads(rec_file.read_text(encoding="utf-8"))


def replay(
    game_key: str,
    speed: float = 1.0,
    session_split: int = 0,
    output_dir: Path = None,
):
    """Replay recorded events and collect screenshots.

    Args:
        game_key: Game identifier
        speed: Playback speed multiplier (1.0 = original, 2.0 = 2x fast)
        session_split: Split screenshots into session folders every N events.
                       0 = auto-detect from recording length.
        output_dir: Override output directory (default: output/{game_key}/sessions)
    """
    if not adb_check_device():
        log(f"ERROR: Device {SYS_CFG.device} not connected.")
        return False

    recording = load_recording(game_key)
    events = recording.get("events", [])
    if not events:
        log("ERROR: Recording has no events.")
        return False

    rec_res = recording.get("resolution", [1080, 1920])
    cur_w, cur_h = get_screen_resolution()

    # Calculate scale factors if resolution differs
    scale_x = cur_w / rec_res[0] if rec_res[0] > 0 else 1.0
    scale_y = cur_h / rec_res[1] if rec_res[1] > 0 else 1.0
    if abs(scale_x - 1.0) > 0.01 or abs(scale_y - 1.0) > 0.01:
        log(f"Resolution scaling: recorded {rec_res[0]}x{rec_res[1]} -> "
            f"current {cur_w}x{cur_h} (scale {scale_x:.2f}x{scale_y:.2f})")

    # Determine output directory
    if output_dir is None:
        output_dir = SYS_CFG.base_dir / "output" / game_key / "sessions"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Auto session split: aim for ~10 sessions
    if session_split <= 0:
        session_split = max(1, len(events) // 10)

    log(f"Replaying {len(events)} events at {speed}x speed")
    log(f"  Session split: every {session_split} events")
    log(f"  Output: {output_dir}\n")

    session_idx = 1
    event_in_session = 0
    shot_idx = 0
    prev_ts = 0.0

    for i, evt in enumerate(events):
        # Determine session folder
        if event_in_session >= session_split:
            session_idx += 1
            event_in_session = 0

        session_dir = output_dir / f"session_{session_idx:02d}"
        session_dir.mkdir(parents=True, exist_ok=True)

        # Wait for timing gap (scaled by speed)
        ts = evt.get("timestamp", 0.0)
        delay = (ts - prev_ts) / speed
        if delay > 0 and i > 0:
            # Cap max delay to avoid extremely long waits
            delay = min(delay, 10.0 / speed)
            time.sleep(delay)
        prev_ts = ts

        # Take screenshot BEFORE the action
        shot_idx += 1
        take_screenshot(session_dir / f"shot_{shot_idx:04d}_before.png")

        # Execute action
        evt_type = evt.get("type", "tap")
        if evt_type == "tap":
            x = int(evt.get("x", 0) * scale_x)
            y = int(evt.get("y", 0) * scale_y)
            tap(x, y, wait=0.3)
            log(f"  [{i+1}/{len(events)}] tap ({x}, {y})")
        elif evt_type == "swipe":
            x1 = int(evt.get("x1", 0) * scale_x)
            y1 = int(evt.get("y1", 0) * scale_y)
            x2 = int(evt.get("x2", 0) * scale_x)
            y2 = int(evt.get("y2", 0) * scale_y)
            dur = evt.get("duration_ms", 300)
            swipe(x1, y1, x2, y2, dur=dur, wait=0.3)
            log(f"  [{i+1}/{len(events)}] swipe ({x1},{y1})->({x2},{y2}) {dur}ms")

        # Take screenshot AFTER the action (with a small settle delay)
        time.sleep(0.5)
        shot_idx += 1
        take_screenshot(session_dir / f"shot_{shot_idx:04d}_after.png")

        event_in_session += 1

    # Summary
    total_sessions = session_idx
    total_shots = shot_idx
    log(f"\nReplay complete!")
    log(f"  Sessions: {total_sessions}")
    log(f"  Screenshots: {total_shots}")
    log(f"  Output: {output_dir}")

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="C10+ v2.5 Replay Player")
    parser.add_argument("game_key", help="Game identifier")
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed (default: 1.0)")
    parser.add_argument("--session-split", type=int, default=0,
                        help="Events per session folder (0 = auto)")
    parser.add_argument("--device", type=str, help="ADB device ID")
    args = parser.parse_args()

    if args.device:
        SYS_CFG.device = args.device

    replay(args.game_key, speed=args.speed, session_split=args.session_split)


if __name__ == "__main__":
    main()
