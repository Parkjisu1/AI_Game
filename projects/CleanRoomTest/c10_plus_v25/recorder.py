#!/usr/bin/env python3
"""
C10+ v2.5 Replay Recorder
==========================
Records user touch events + screenshots from a live game session.

Usage:
  python recorder.py <game_key>         # Start recording (Ctrl+C to stop)
  python recorder.py <game_key> --list  # List existing recordings
"""

import sys
import re
import json
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from core import (
    SYS_CFG, log, adb_check_device,
    take_screenshot, getevent_start, getevent_stop, get_screen_resolution,
    find_touch_device,
)


# ---------------------------------------------------------------------------
# getevent parser
# ---------------------------------------------------------------------------

# Typical getevent -lt output lines:
#   [   12345.678901] /dev/input/event1: EV_ABS       ABS_MT_TRACKING_ID   00000001
#   [   12345.678902] /dev/input/event1: EV_ABS       ABS_MT_POSITION_X    0000021c
#   [   12345.678903] /dev/input/event1: EV_ABS       ABS_MT_POSITION_Y    000003c0
#   [   12345.678904] /dev/input/event1: EV_SYN       SYN_REPORT           00000000

_LINE_RE = re.compile(
    r'\[\s*([\d.]+)\]\s+\S+:\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)'
)

# getevent reports raw coordinates that may need scaling.
# We detect the input device's axis max and scale to screen resolution.
_ABS_MAX_RE = re.compile(r'max\s+(\d+)')


def _get_input_axis_max(device: str = "") -> Tuple[int, int]:
    """Query input device axis max values for coordinate scaling."""
    from core import adb_run
    r = adb_run("shell", "getevent", "-il", device, timeout=5)
    if r.returncode != 0 or not r.stdout:
        return 0, 0

    text = r.stdout.decode("utf-8", errors="replace")
    x_max, y_max = 0, 0
    current_axis = None
    for line in text.splitlines():
        if "ABS_MT_POSITION_X" in line:
            current_axis = "x"
        elif "ABS_MT_POSITION_Y" in line:
            current_axis = "y"
        elif current_axis and "max" in line:
            m = _ABS_MAX_RE.search(line)
            if m:
                if current_axis == "x":
                    x_max = int(m.group(1))
                else:
                    y_max = int(m.group(1))
                current_axis = None
        elif line.strip() and not line.startswith(" "):
            current_axis = None
    return x_max, y_max


class TouchEvent:
    """A single parsed touch interaction (tap or swipe)."""

    def __init__(self):
        self.start_time: float = 0
        self.end_time: float = 0
        self.positions: List[Tuple[int, int]] = []  # raw positions

    @property
    def duration_ms(self) -> int:
        return max(0, int((self.end_time - self.start_time) * 1000))

    def classify(self, tap_threshold_px: int = 50, tap_threshold_ms: int = 500):
        """Classify as tap or swipe based on movement and duration."""
        if len(self.positions) < 2:
            return "tap"
        first = self.positions[0]
        last = self.positions[-1]
        dx = abs(last[0] - first[0])
        dy = abs(last[1] - first[1])
        dist = (dx ** 2 + dy ** 2) ** 0.5
        if dist < tap_threshold_px and self.duration_ms < tap_threshold_ms:
            return "tap"
        return "swipe"


def parse_getevent_output(
    raw: str,
    screen_w: int, screen_h: int,
    input_x_max: int = 0, input_y_max: int = 0,
) -> List[Dict]:
    """Parse getevent -lt output into a list of touch event dicts.

    Scales raw coordinates to screen resolution if axis max values are known.
    """
    events: List[Dict] = []
    current: Optional[TouchEvent] = None
    cur_x, cur_y = 0, 0
    base_time: Optional[float] = None
    tracking_active = False

    for line in raw.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue

        ts = float(m.group(1))
        ev_type = m.group(2)
        ev_code = m.group(3)
        ev_value = int(m.group(4), 16)

        if base_time is None:
            base_time = ts

        if ev_type == "EV_ABS":
            if ev_code == "ABS_MT_TRACKING_ID":
                if ev_value == 0xFFFFFFFF:
                    # Touch up
                    if current is not None:
                        current.end_time = ts
                        events.append(_build_event_dict(
                            current, base_time, screen_w, screen_h,
                            input_x_max, input_y_max,
                        ))
                        current = None
                    tracking_active = False
                else:
                    # Touch down
                    current = TouchEvent()
                    current.start_time = ts
                    tracking_active = True
            elif ev_code == "ABS_MT_POSITION_X":
                cur_x = ev_value
            elif ev_code == "ABS_MT_POSITION_Y":
                cur_y = ev_value

        elif ev_type == "EV_SYN" and ev_code == "SYN_REPORT":
            if current is not None and tracking_active:
                current.positions.append((cur_x, cur_y))

    # Handle lingering touch (no explicit release)
    if current is not None and current.positions:
        current.end_time = current.start_time + 0.1
        events.append(_build_event_dict(
            current, base_time, screen_w, screen_h,
            input_x_max, input_y_max,
        ))

    return events


def _scale_coord(raw: int, axis_max: int, screen_max: int) -> int:
    """Scale raw getevent coordinate to screen pixel."""
    if axis_max > 0:
        return int(raw * screen_max / axis_max)
    # If no axis max known, assume raw == screen pixel
    return raw


def _build_event_dict(
    te: TouchEvent, base_time: float,
    screen_w: int, screen_h: int,
    input_x_max: int, input_y_max: int,
) -> Dict:
    """Convert a TouchEvent into a JSON-serializable dict."""
    event_type = te.classify()
    first = te.positions[0]
    last = te.positions[-1]
    x1 = _scale_coord(first[0], input_x_max, screen_w)
    y1 = _scale_coord(first[1], input_y_max, screen_h)

    result = {
        "type": event_type,
        "timestamp": round(te.start_time - base_time, 3),
    }

    if event_type == "tap":
        result["x"] = x1
        result["y"] = y1
    else:
        x2 = _scale_coord(last[0], input_x_max, screen_w)
        y2 = _scale_coord(last[1], input_y_max, screen_h)
        result["x1"] = x1
        result["y1"] = y1
        result["x2"] = x2
        result["y2"] = y2
        result["duration_ms"] = te.duration_ms

    return result


# ---------------------------------------------------------------------------
# Recorder
# ---------------------------------------------------------------------------

def get_recordings_dir(game_key: str) -> Path:
    return SYS_CFG.base_dir / "recordings" / game_key


def record(game_key: str):
    """Record user touch events and screenshots from a live session.

    Captures getevent output in a background thread while taking periodic
    screenshots. On Ctrl+C, saves events + frames to recordings/{game_key}/.
    """
    if not adb_check_device():
        log(f"ERROR: Device {SYS_CFG.device} not connected.")
        return

    rec_dir = get_recordings_dir(game_key)
    frames_dir = rec_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    screen_w, screen_h = get_screen_resolution()
    log(f"Screen resolution: {screen_w}x{screen_h}")

    # Auto-detect touch device
    touch_device = find_touch_device()
    log(f"Touch device: {touch_device}")

    # Detect input axis max values for coordinate scaling
    input_x_max, input_y_max = _get_input_axis_max(touch_device)
    if input_x_max > 0:
        log(f"Input axis max: X={input_x_max}, Y={input_y_max}")
    else:
        log("Input axis max not detected; assuming raw == screen coords")

    # Stop signal file — GUI writes this to request graceful stop
    stop_file = rec_dir / ".stop"
    if stop_file.exists():
        stop_file.unlink()

    log(f"Recording to: {rec_dir}")
    log("Play the game now. Press Ctrl+C or use GUI [Stop] to stop recording.\n")

    # Capture getevent in background
    getevent_output_lines: List[str] = []
    proc = getevent_start(touch_device)

    def _read_getevent():
        for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            getevent_output_lines.append(line)

    reader_thread = threading.Thread(target=_read_getevent, daemon=True)
    reader_thread.start()

    # Take screenshots periodically (before/after touch detection via timing)
    frame_idx = 0
    screenshot_interval = 2.0  # seconds between auto-screenshots
    try:
        while True:
            # Check for stop signal from GUI
            if stop_file.exists():
                log("\nStop signal received from GUI...")
                try:
                    stop_file.unlink()
                except OSError:
                    pass
                break
            frame_idx += 1
            fname = f"frame_{frame_idx:04d}.png"
            take_screenshot(frames_dir / fname)
            # Sleep in small increments to check stop signal more often
            for _ in range(int(screenshot_interval * 5)):
                if stop_file.exists():
                    break
                time.sleep(0.2)
    except KeyboardInterrupt:
        log("\nStopping recording...")

    # Stop getevent
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()
    reader_thread.join(timeout=3)

    # Parse events
    raw_output = "\n".join(getevent_output_lines)
    events = parse_getevent_output(
        raw_output, screen_w, screen_h, input_x_max, input_y_max,
    )

    # Assign screenshot references to events
    frame_files = sorted(frames_dir.glob("frame_*.png"))
    frame_times = []
    for f in frame_files:
        frame_times.append(f.name)

    # Simple assignment: each event gets nearest screenshots
    for i, evt in enumerate(events):
        ts = evt["timestamp"]
        # Calculate which frame index corresponds (based on screenshot_interval)
        frame_num = max(0, int(ts / screenshot_interval))
        before_idx = min(frame_num, len(frame_times) - 1) if frame_times else 0
        after_idx = min(frame_num + 1, len(frame_times) - 1) if frame_times else 0
        if frame_times:
            evt["screenshot_before"] = frame_times[before_idx]
            evt["screenshot_after"] = frame_times[after_idx]

    # Save recording
    recording = {
        "game": game_key,
        "device": SYS_CFG.device,
        "resolution": [screen_w, screen_h],
        "recorded_at": datetime.now().isoformat(),
        "screenshot_interval": screenshot_interval,
        "input_axis_max": {"x": input_x_max, "y": input_y_max},
        "events": events,
    }

    rec_file = rec_dir / "recording.json"
    rec_file.write_text(json.dumps(recording, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"\nRecording saved: {rec_file}")
    log(f"  Events: {len(events)} ({sum(1 for e in events if e['type'] == 'tap')} taps, "
        f"{sum(1 for e in events if e['type'] == 'swipe')} swipes)")
    log(f"  Frames: {len(frame_times)}")


def list_recordings(game_key: str):
    """List existing recordings for a game."""
    rec_dir = get_recordings_dir(game_key)
    rec_file = rec_dir / "recording.json"
    if not rec_file.exists():
        log(f"No recordings found for '{game_key}'")
        return

    data = json.loads(rec_file.read_text(encoding="utf-8"))
    frames_dir = rec_dir / "frames"
    frame_count = len(list(frames_dir.glob("frame_*.png"))) if frames_dir.exists() else 0

    log(f"Recording for '{game_key}':")
    log(f"  Recorded at: {data.get('recorded_at', 'unknown')}")
    log(f"  Device:      {data.get('device', 'unknown')}")
    log(f"  Resolution:  {data.get('resolution', [0, 0])}")
    log(f"  Events:      {len(data.get('events', []))}")
    log(f"  Frames:      {frame_count}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="C10+ v2.5 Replay Recorder")
    parser.add_argument("game_key", help="Game identifier")
    parser.add_argument("--list", action="store_true", help="List existing recordings")
    parser.add_argument("--device", type=str, help="ADB device ID")
    args = parser.parse_args()

    if args.device:
        SYS_CFG.device = args.device

    if args.list:
        list_recordings(args.game_key)
    else:
        record(args.game_key)


if __name__ == "__main__":
    main()
