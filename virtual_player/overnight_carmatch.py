"""
Overnight CarMatch Auto-Player
================================
Simple loop: screenshot -> analyze -> tap -> repeat
Runs until target time (default: next 9:00 AM).
Handles all screens: lobby, gameplay, win, fail, ads.
Self-correcting: tracks failed taps and adjusts.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

# Config
ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
SERIAL = "emulator-5554"
CLAUDE_CMD = "C:/Users/user/AppData/Roaming/npm/claude.cmd"
MODEL = "claude-haiku-4-5-20251001"
TIMEOUT = 90  # seconds per Vision AI call
DATA_DIR = Path(__file__).parent / "data"
TEMP_DIR = DATA_DIR / "games" / "carmatch" / "temp" / "overnight"
LOG_FILE = DATA_DIR / "games" / "carmatch" / "overnight_log.txt"

# Stats
stats = {
    "games_started": 0,
    "games_won": 0,
    "games_failed": 0,
    "total_taps": 0,
    "vision_calls": 0,
    "vision_errors": 0,
    "ads_closed": 0,
    "started_at": datetime.now().isoformat(),
}


def log(msg: str):
    """Print and log to file."""
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def screenshot(name: str = "frame") -> Path:
    """Take ADB screenshot and save to temp dir."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
        capture_output=True, timeout=10
    )
    path = TEMP_DIR / f"{name}.png"
    path.write_bytes(r.stdout)
    return path


def tap(x: int, y: int, wait: float = 1.0):
    """Tap screen via ADB."""
    subprocess.run(
        [ADB, "-s", SERIAL, "shell", "input", "tap", str(x), str(y)],
        capture_output=True, timeout=5
    )
    stats["total_taps"] += 1
    time.sleep(wait)


def back():
    """Press back button."""
    subprocess.run(
        [ADB, "-s", SERIAL, "shell", "input", "keyevent", "4"],
        capture_output=True, timeout=5
    )
    time.sleep(1)


def ask_vision(img_path: Path, context: str, batch: int = 6) -> list:
    """Call Claude CLI to analyze screenshot and plan moves."""
    stats["vision_calls"] += 1
    img = str(img_path).replace("\\", "/")

    prompt = f"""Use the Read tool to view the screenshot at {img}. Then respond with ONLY the JSON array.

Analyze this 1080x1920 pixel mobile game screenshot.

COORDINATE REFERENCE (1080x1920 screen):
- Top bar with coins/level: y=0-150
- Game board area: y=250 to y=1300, x=30 to x=1050
- Holder (7 slots at bottom): y=1350-1450
- Booster buttons: y=1800-1870
- Cars are 3D models ~100-130px wide, ~80-120px tall
- A car is TAPPABLE if you can see its eyes/windshield (not hidden behind another car)

{context}

Return JSON array of {batch} moves. Each tap move:
{{"action":"tap","x":<0-1080>,"y":<0-1920>,"description":"<what to tap>"}}
Wait move: {{"action":"wait","seconds":1.5,"description":"animation"}}

Include a 1.5s wait after each tap for animation.
ONLY output the JSON array, nothing else."""

    env = os.environ.copy()
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        env.pop(k, None)
    api_key = env.get("ANTHROPIC_API_KEY", "")
    if not api_key or not api_key.startswith("sk-ant-"):
        env.pop("ANTHROPIC_API_KEY", None)
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        start = time.time()
        r = subprocess.run(
            [CLAUDE_CMD, "-p",
             "--model", MODEL,
             "--output-format", "json",
             "--max-turns", "2",
             "--tools", "Read",
             "--allowedTools", "Read"],
            input=prompt,
            capture_output=True,
            timeout=TIMEOUT,
            encoding="utf-8",
            env=env,
            cwd=tempfile.gettempdir(),
        )
        elapsed = time.time() - start

        if r.returncode != 0:
            log(f"Vision error (rc={r.returncode}): {r.stdout[:200]}")
            stats["vision_errors"] += 1
            return []

        log(f"Vision AI: {elapsed:.0f}s")

        # Parse response
        try:
            outer = json.loads(r.stdout)
            text = outer.get("result", r.stdout) if isinstance(outer, dict) else r.stdout
        except json.JSONDecodeError:
            text = r.stdout

        text = str(text).strip()
        start_i = text.find("[")
        end_i = text.rfind("]")
        if start_i >= 0 and end_i > start_i:
            moves = json.loads(text[start_i:end_i + 1])
            if isinstance(moves, list):
                valid = []
                for m in moves:
                    if not isinstance(m, dict):
                        continue
                    action = m.get("action", "tap")
                    if action == "wait":
                        valid.append(m)
                    elif action == "tap":
                        x = max(0, min(1080, int(m.get("x", 540))))
                        y = max(0, min(1920, int(m.get("y", 960))))
                        valid.append({"action": "tap", "x": x, "y": y,
                                      "description": m.get("description", "?")})
                return valid
        log(f"Vision parse error: {text[:150]}")
        return []

    except subprocess.TimeoutExpired:
        log(f"Vision timeout ({TIMEOUT}s)")
        stats["vision_errors"] += 1
        return []
    except Exception as e:
        log(f"Vision error: {e}")
        stats["vision_errors"] += 1
        return []


def detect_screen(img_path: Path) -> str:
    """Quick screen detection via Vision AI (simple prompt)."""
    img = str(img_path).replace("\\", "/")
    prompt = f"""Use the Read tool to view the screenshot at {img}. Then respond with ONLY one word.

This is a CarMatch mobile game screenshot (1080x1920).
What screen is this? Reply with EXACTLY one of these words:
- lobby (main menu with Level button and car in center)
- gameplay (parking lot puzzle board with colored cars)
- win (level complete / congratulations)
- fail (out of space / game over)
- ad (advertisement / video ad playing)
- popup (any popup dialog over the game)
- other (anything else)

Reply with ONLY the one word, nothing else."""

    env = os.environ.copy()
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        env.pop(k, None)
    api_key = env.get("ANTHROPIC_API_KEY", "")
    if not api_key or not api_key.startswith("sk-ant-"):
        env.pop("ANTHROPIC_API_KEY", None)
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        r = subprocess.run(
            [CLAUDE_CMD, "-p",
             "--model", MODEL,
             "--output-format", "json",
             "--max-turns", "2",
             "--tools", "Read",
             "--allowedTools", "Read"],
            input=prompt,
            capture_output=True,
            timeout=60,
            encoding="utf-8",
            env=env,
            cwd=tempfile.gettempdir(),
        )
        if r.returncode != 0:
            return "unknown"

        outer = json.loads(r.stdout)
        text = outer.get("result", "").strip().lower()
        for screen in ("lobby", "gameplay", "win", "fail", "ad", "popup"):
            if screen in text:
                return screen
        return "other"
    except Exception:
        return "unknown"


def handle_lobby():
    """In lobby: tap the Level button to start a game."""
    log("LOBBY: Tapping Level button to start game")
    tap(540, 1500, 3)  # Level N button
    stats["games_started"] += 1


def handle_gameplay(img_path: Path, failed_coords: list) -> list:
    """In gameplay: analyze board and tap cars."""
    failed_str = ""
    if failed_coords:
        coords = [f"({x},{y})" for x, y in failed_coords[-6:]]
        failed_str = (f"\nPREVIOUS FAILED TAPS (nothing happened): {', '.join(coords)}"
                      f"\nAvoid these areas. Find DIFFERENT tappable cars.")

    context = (
        "CarMatch puzzle: tap colored cars to move them to the holder (bottom). "
        "3 same-color cars in holder = match and vanish. "
        "TAPPABLE CARS: You can see the car's EYES/FACE/WINDSHIELD. "
        "BLOCKED CARS: Eyes hidden behind another car - NOT tappable. "
        "ONLY tap cars with visible eyes! "
        "PRIORITY: If 2 same-color cars in holder, find the 3rd on board. "
        "If no match available, tap FRONT ROW cars (visible eyes, bottom of board). "
        "HOLDER at y~1400 shows collected cars. "
        "DO NOT tap boosters (y>1800) unless using Undo (x=108,y=1830) when holder is full."
        + failed_str
    )

    moves = ask_vision(img_path, context, batch=6)

    if not moves:
        log("No moves from Vision, trying random front-row tap")
        import random
        x = random.randint(100, 1000)
        y = random.randint(1050, 1250)  # Front row area
        return [{"action": "tap", "x": x, "y": y, "description": "random front-row"}]

    return moves


def handle_win():
    """Win screen: tap Continue and go back to lobby."""
    log("WIN! Tapping Continue")
    stats["games_won"] += 1
    tap(540, 1400, 2)  # Continue button
    tap(540, 1400, 2)  # Extra tap in case


def handle_fail():
    """Fail screen: close popups and retry."""
    log("FAIL: Closing popups")
    stats["games_failed"] += 1
    # Close "Add Space" popup (X button top-right)
    tap(970, 180, 1.5)
    # Close "Play On" popup (X button)
    tap(900, 500, 1.5)
    # Tap "Try Again" or close
    tap(540, 1100, 2)
    # If still on fail, go back to lobby
    tap(540, 1500, 2)


def handle_ad():
    """Ad screen: try to close it."""
    log("AD: Attempting to close")
    stats["ads_closed"] += 1
    # Try common close button positions
    tap(1020, 80, 1)    # Top-right X
    tap(60, 80, 1)      # Top-left X
    tap(1020, 160, 1)   # Slightly lower
    back()              # Android back button


def handle_popup():
    """Popup: try to close it."""
    log("POPUP: Attempting to close")
    tap(970, 180, 1)    # Top-right X
    back()


def run_game_loop(target_time: datetime):
    """Main game loop running until target_time."""
    log(f"=== OVERNIGHT CARMATCH STARTED ===")
    log(f"Target: run until {target_time.strftime('%Y-%m-%d %H:%M')}")
    log(f"Stats reset: {json.dumps(stats)}")

    failed_gameplay_coords = []
    consecutive_unknown = 0
    last_screen = ""

    while datetime.now() < target_time:
        try:
            # Take screenshot
            img = screenshot("current")

            # Detect screen
            screen = detect_screen(img)
            log(f"Screen: {screen}")

            if screen != last_screen:
                failed_gameplay_coords.clear()
                consecutive_unknown = 0
            last_screen = screen

            if screen == "lobby":
                handle_lobby()

            elif screen == "gameplay":
                moves = handle_gameplay(img, failed_gameplay_coords)
                tapped = False
                for move in moves:
                    if move.get("action") == "tap":
                        x, y = move["x"], move["y"]
                        desc = move.get("description", "?")
                        log(f"  TAP ({x},{y}): {desc}")
                        tap(x, y, 0.5)
                        tapped = True

                        # Check if tap worked by taking quick screenshot
                        time.sleep(1.0)
                        check = screenshot("check")
                        check_screen = detect_screen(check)
                        if check_screen == "gameplay":
                            # Still gameplay - might have worked (car moved to holder)
                            # or might have failed (blocked car)
                            pass
                        elif check_screen == "win":
                            handle_win()
                            break
                        elif check_screen == "fail":
                            handle_fail()
                            break
                        elif check_screen == "ad":
                            handle_ad()
                            break

                    elif move.get("action") == "wait":
                        time.sleep(move.get("seconds", 1.5))

                if not tapped:
                    # Nothing worked, try random tap
                    import random
                    x = random.randint(100, 1000)
                    y = random.randint(900, 1200)
                    log(f"  RANDOM TAP ({x},{y})")
                    tap(x, y, 1.5)

            elif screen == "win":
                handle_win()

            elif screen == "fail":
                handle_fail()

            elif screen == "ad":
                handle_ad()

            elif screen == "popup":
                handle_popup()

            else:
                consecutive_unknown += 1
                log(f"Unknown screen (attempt {consecutive_unknown})")
                if consecutive_unknown >= 3:
                    # Try back button then home
                    back()
                    time.sleep(1)
                if consecutive_unknown >= 5:
                    # Try to relaunch
                    log("Too many unknowns, relaunching game")
                    subprocess.run(
                        [ADB, "-s", SERIAL, "shell", "am", "force-stop",
                         "com.grandgames.carmatch"],
                        capture_output=True, timeout=5)
                    time.sleep(2)
                    subprocess.run(
                        [ADB, "-s", SERIAL, "shell", "monkey", "-p",
                         "com.grandgames.carmatch", "-c",
                         "android.intent.category.LAUNCHER", "1"],
                        capture_output=True, timeout=5)
                    time.sleep(5)
                    consecutive_unknown = 0

        except Exception as e:
            log(f"ERROR: {e}")
            time.sleep(5)

        # Brief status every 10 vision calls
        if stats["vision_calls"] % 10 == 0 and stats["vision_calls"] > 0:
            log(f"--- Stats: {stats['games_won']}W/{stats['games_failed']}F, "
                f"{stats['total_taps']} taps, {stats['vision_calls']} AI calls ---")

    # Final report
    stats["ended_at"] = datetime.now().isoformat()
    log(f"\n{'='*50}")
    log(f"OVERNIGHT SESSION COMPLETE")
    log(f"{'='*50}")
    log(f"Duration: {stats['started_at']} to {stats['ended_at']}")
    log(f"Games started: {stats['games_started']}")
    log(f"Games won: {stats['games_won']}")
    log(f"Games failed: {stats['games_failed']}")
    log(f"Total taps: {stats['total_taps']}")
    log(f"Vision AI calls: {stats['vision_calls']}")
    log(f"Vision errors: {stats['vision_errors']}")
    log(f"Ads closed: {stats['ads_closed']}")

    # Save stats
    stats_path = DATA_DIR / "games" / "carmatch" / "overnight_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    log(f"Stats saved to {stats_path}")


if __name__ == "__main__":
    # Target: next 9:00 AM
    now = datetime.now()
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    # Clear old log
    if LOG_FILE.exists():
        LOG_FILE.unlink()

    run_game_loop(target)
