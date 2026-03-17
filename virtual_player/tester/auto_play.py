"""
Pixel Flow Auto-Player v5 (Targeted Monkey Scripts)
=====================================================
Uses monkey SCRIPT files with exact coordinates for all overlay interactions.
Monkey scripts reach Unity overlay layer via InputManager.injectInputEvent().

Key findings:
  - Monkey script events pass THROUGH popup overlays to game elements behind them
  - Dialog/popup BUTTONS (X close, 받기 etc.) CANNOT be clicked by monkey script
  - Store opens when touching top bar (y<130) or bottom nav (y>1800)
  - Pigs deploy fine even with popups overlaying the game

Safe zones (ONLY tap here):
  y=200-1780, x=50-950 — avoids all store/settings triggers

Danger zones (NEVER touch):
  y<200: hearts/coins +buttons, store triggers
  y>1780: bottom nav (store/home tabs)
  x>950, y<200: gear icon
"""

import subprocess
import time
import sys
import traceback
from pathlib import Path
from datetime import datetime

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print("ERROR: pip install Pillow numpy")
    sys.exit(1)

ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
SERIAL = "emulator-5554"
PACKAGE = "com.loomgames.pixelflow"
TEMP = Path("E:/AI/virtual_player/data/games/pixelflow/temp/tester")
TEMP.mkdir(parents=True, exist_ok=True)
LOG_FILE = TEMP / "auto_log.txt"
SCRIPT_PATH = "/sdcard/pf_monkey.txt"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def adb(cmd_args):
    try:
        r = subprocess.run(
            [ADB, "-s", SERIAL] + cmd_args,
            capture_output=True, timeout=10,
        )
        return r
    except Exception as e:
        log(f"  ADB error: {e}")
        return None


def screenshot():
    r = adb(["exec-out", "screencap", "-p"])
    if r and len(r.stdout) > 1000:
        path = TEMP / "auto.png"
        path.write_bytes(r.stdout)
        return path
    return None


def tap(x, y):
    adb(["shell", "input", "tap", str(x), str(y)])


def back():
    adb(["shell", "input", "keyevent", "4"])


def monkey_script(taps, throttle_ms=80):
    """Run monkey script with exact coordinate taps.
    Events reach Unity overlay layer and pass through popup overlays.
    Writes script to local temp file, pushes to device, then runs monkey.
    """
    if not taps:
        return
    lines = [
        "type= user",
        f"count= {len(taps)}",
        "speed= 1.0",
        "start data >>",
    ]
    for x, y in taps:
        lines.append(f"DispatchPointer(0,0,0,{x},{y},1,1,0,1,1,0,0)")
        lines.append(f"DispatchPointer(0,0,1,{x},{y},1,1,0,1,1,0,0)")
        lines.append(f"UserWait({throttle_ms})")
    script = "\n".join(lines) + "\n"
    # Write to local temp file, then push to device (avoids shell escaping issues)
    local_script = TEMP / "monkey_script.txt"
    local_script.write_text(script, encoding="utf-8")
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "push", str(local_script), SCRIPT_PATH],
            capture_output=True, timeout=10,
        )
    except Exception as e:
        log(f"  Push script error: {e}")
        return
    try:
        timeout = max(30, len(taps) * throttle_ms // 500 + 10)
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "monkey",
             "-p", PACKAGE, "-f", SCRIPT_PATH, "1"],
            capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log(f"  Monkey script timeout ({len(taps)} taps)")
    except Exception as e:
        log(f"  Monkey script error: {e}")


def generate_drag_to_belt():
    """Drag gestures: drag pigs from queue upward toward belt entry.
    Connected pigs (Level 15+) may need dragging instead of tapping.
    Belt entry is at bottom-right of board (~650, 800).
    Pig queue is around y=1100-1300, x=350-550.
    """
    drags = []
    # Drag from each pig position upward to belt entry area
    for start_y in range(1150, 1350, 50):
        for start_x in range(350, 600, 60):
            # Drag up to belt entry area
            drags.append((start_x, start_y, 600, 850))
    # Also try dragging to holder slots
    for start_y in range(1150, 1350, 50):
        for start_x in range(350, 600, 60):
            drags.append((start_x, start_y, 400, 980))
    return drags


def monkey_script_drags(drags, move_steps=5, throttle_ms=30):
    """Run monkey script with drag gestures (touch down, move, touch up).
    Each drag is (x1, y1, x2, y2).
    """
    if not drags:
        return
    lines = [
        "type= user",
        f"count= {len(drags) * (move_steps + 2)}",
        "speed= 1.0",
        "start data >>",
    ]
    for x1, y1, x2, y2 in drags:
        # Touch down
        lines.append(f"DispatchPointer(0,0,0,{x1},{y1},1,1,0,1,1,0,0)")
        lines.append(f"UserWait({throttle_ms})")
        # Move steps
        for i in range(1, move_steps + 1):
            frac = i / move_steps
            mx = int(x1 + (x2 - x1) * frac)
            my = int(y1 + (y2 - y1) * frac)
            lines.append(f"DispatchPointer(0,0,2,{mx},{my},1,1,0,1,1,0,0)")
            lines.append(f"UserWait({throttle_ms})")
        # Touch up
        lines.append(f"DispatchPointer(0,0,1,{x2},{y2},1,1,0,1,1,0,0)")
        lines.append(f"UserWait({throttle_ms * 2})")
    script = "\n".join(lines) + "\n"
    local_script = TEMP / "monkey_script.txt"
    local_script.write_text(script, encoding="utf-8")
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "push", str(local_script), SCRIPT_PATH],
            capture_output=True, timeout=10,
        )
    except Exception as e:
        log(f"  Push drag script error: {e}")
        return
    try:
        timeout = max(30, len(drags) * (move_steps + 2) * throttle_ms // 500 + 15)
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "monkey",
             "-p", PACKAGE, "-f", SCRIPT_PATH, "1"],
            capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        log(f"  Drag script timeout ({len(drags)} drags)")
    except Exception as e:
        log(f"  Drag script error: {e}")


def generate_full_screen_taps():
    """Full screen safe zone tap grid.
    Dismisses any invisible overlay popups/tutorials.
    Avoids: y<200 (top bar), y>1780 (bottom nav), edges.
    """
    taps = []
    for y in range(250, 1750, 80):
        for x in range(100, 950, 100):
            taps.append((x, y))
    return taps


def generate_tutorial_dismiss_taps():
    """Focused taps to dismiss tutorial overlays.
    ONLY the 계속하기 button area — NOTHING else.
    Any center-screen taps risk hitting overlay purchase buttons → store.
    """
    taps = []
    # Tutorial 계속하기 button area: y=1300-1440, x=200-520
    for y in range(1300, 1440, 15):
        for x in range(200, 520, 30):
            taps.append((x, y))
    return taps


def generate_dialog_dismiss_taps():
    """Taps for win/fail/popup dialog buttons.
    Covers y=900-1300 center area where buttons appear.
    Avoids y<900 — 트레이 추가 popup purchase button at y~780.
    """
    taps = []
    for y in range(900, 1300, 30):
        for x in range(200, 700, 50):
            taps.append((x, y))
    return taps


def generate_deploy_taps():
    """Focused taps on pig queue area.

    Level 15+ has connected pig tutorial. Too many rapid taps confuse it.
    Use moderate grid covering main pig positions.
    """
    taps = []
    # Pig queue area: y=1050-1500, x=250-600
    for y in range(1050, 1500, 40):
        for x in range(250, 610, 50):
            taps.append((x, y))
    return taps


def generate_deploy_taps_wide():
    """Extended taps: queue + holder slots + belt area.
    Used as second pass after initial deploy.
    """
    taps = []
    # Holder slots: y=930-1010, x=130-700
    for y in range(930, 1020, 25):
        for x in range(130, 710, 70):
            taps.append((x, y))
    # Queue: y=1050-1500, x=250-600
    for y in range(1050, 1500, 40):
        for x in range(250, 610, 50):
            taps.append((x, y))
    return taps


def generate_play_taps():
    """Taps covering the Play button area in lobby.
    Play button: large yellow button around (360, 1450).
    Verified: yellow pixels at x=200-530, y=1400-1500.
    """
    taps = []
    for y in range(1380, 1520, 20):
        for x in range(200, 560, 40):
            taps.append((x, y))
    return taps


def relaunch():
    log("  >> RELAUNCHING game...")
    adb(["shell", "input", "keyevent", "3"])
    time.sleep(1)
    adb(["shell", "am", "force-stop", "com.android.vending"])
    adb(["shell", "am", "force-stop", PACKAGE])
    time.sleep(2)
    adb(["shell", "am", "start", "-n",
         f"{PACKAGE}/com.unity3d.player.UnityPlayerActivity"])
    time.sleep(10)


# ---- Screen Detection ----

def detect_screen(arr):
    h, w = arr.shape[:2]
    if h < 1000:
        return "unknown"
    # Ensure RGB (drop alpha if RGBA)
    if arr.shape[2] == 4:
        arr = arr[:, :, :3]

    # Hearts dialog (purple overlay)
    if h > 1000:
        purple = arr[500:800, 200:600]
        pr, pg, pb = purple[:,:,0].astype(int), purple[:,:,1].astype(int), purple[:,:,2].astype(int)
        purple_px = (pr > 80) & (pr < 180) & (pg > 40) & (pg < 130) & (pb > 130) & (pb < 220)
        if purple_px.sum() > 10000:
            return "hearts_empty"

    # Store/gold pack: dark bottom half
    if h > 1800:
        bottom = arr[1200:1800, 100:700]
        bt = bottom[:,:,0].astype(int) + bottom[:,:,1].astype(int) + bottom[:,:,2].astype(int)
        if (bt < 80).sum() > bottom.shape[0] * bottom.shape[1] * 0.5:
            return "store"

    # Dialog overlay (fail/win/popup)
    if h > 1200 and w > 700:
        dialog = arr[700:900, 250:650]
        r, g, b = dialog[:,:,0].astype(int), dialog[:,:,1].astype(int), dialog[:,:,2].astype(int)
        light_blue = (r > 150) & (g > 200) & (b > 230) & (b > r + 30)
        if light_blue.sum() > 5000:
            yellow = arr[1130:1280, 250:750]
            r2, g2, b2 = yellow[:,:,0].astype(int), yellow[:,:,1].astype(int), yellow[:,:,2].astype(int)
            if ((r2 > 200) & (g2 > 170) & (b2 < 120)).sum() > 3000:
                return "fail"
            if ((g2 > 180) & (r2 < 120) & (b2 < 120)).sum() > 1000:
                return "win"
            return "popup"

    # Lobby
    if h > 1300:
        bg = arr[600:900, 200:600]
        r, g, b = bg[:,:,0].astype(int), bg[:,:,1].astype(int), bg[:,:,2].astype(int)
        if ((r < 30) & (g > 140) & (b > 240)).sum() > 10000:
            return "lobby"

    # Gameplay
    if h > 1800:
        board = arr[250:700, 180:650]
        rb, gb, bb = board[:,:,0].astype(int), board[:,:,1].astype(int), board[:,:,2].astype(int)
        maxc = np.maximum(np.maximum(rb, gb), bb)
        minc = np.minimum(np.minimum(rb, gb), bb)
        if (((maxc - minc) > 60) & (maxc > 150)).sum() > 5000:
            return "gameplay"
        # Nearly-cleared: check belt
        belt = arr[790:850, 200:600]
        rb2, gb2, bb2 = belt[:,:,0].astype(int), belt[:,:,1].astype(int), belt[:,:,2].astype(int)
        if ((rb2 > 120) & (rb2 < 200) & (gb2 > 120) & (gb2 < 200) & (bb2 > 140) & (bb2 < 220)).sum() > 2000:
            return "gameplay"

    # Popup fallback
    center = arr[400:800, 200:600]
    if ((center[:,:,0].astype(int) + center[:,:,1].astype(int) + center[:,:,2].astype(int)) < 100).sum() > 40000:
        return "popup"

    return "unknown"


def count_board_pixels(arr):
    if arr.shape[0] < 1000:
        return 999999
    board = arr[250:700, 180:650]
    r, g, b = board[:,:,0].astype(int), board[:,:,1].astype(int), board[:,:,2].astype(int)
    maxc = np.maximum(np.maximum(r, g), b)
    minc = np.minimum(np.minimum(r, g), b)
    return int((((maxc - minc) > 60) & (maxc > 150)).sum())


# ---- Main Game Loop ----

def play_game(duration_minutes=60):
    start = time.time()
    end_time = start + duration_minutes * 60
    turn = 0
    games_won = 0
    games_failed = 0
    stuck_count = 0
    last_screen = None
    lobby_fail_count = 0
    non_gameplay_count = 0
    last_board_pixels = 999999
    gameplay_turns = 0
    deploy_cycle = 0
    tutorial_dismissed = False
    board_unchanged_count = 0  # consecutive turns with same board pixel count

    log(f"=== Pixel Flow Auto-Player v5 (Safe Monkey) START ===")
    log(f"Duration: {duration_minutes} minutes")
    log(f"Target end: {datetime.fromtimestamp(end_time).strftime('%H:%M:%S')}")

    while time.time() < end_time:
        try:
            turn += 1
            img_path = screenshot()
            if not img_path:
                log("Screenshot failed, retrying...")
                time.sleep(3)
                continue

            arr = np.array(Image.open(img_path))
            screen = detect_screen(arr)

            # Stuck detection
            if screen == last_screen:
                stuck_count += 1
            else:
                stuck_count = 0
            last_screen = screen

            # Non-gameplay streak
            if screen in ("gameplay", "lobby", "win", "fail"):
                non_gameplay_count = 0
            else:
                non_gameplay_count += 1

            if non_gameplay_count >= 12:
                log(f"  >> Non-gameplay streak x{non_gameplay_count}, relaunching...")
                relaunch()
                non_gameplay_count = 0
                stuck_count = 0
                lobby_fail_count = 0
                gameplay_turns = 0
                tutorial_dismissed = False
                continue

            if turn % 3 == 0:
                log(f"Turn {turn}: screen={screen} stuck={stuck_count} | W:{games_won} F:{games_failed}")

            # ---- LOBBY ----
            if screen == "lobby":
                lobby_fail_count += 1
                if lobby_fail_count > 10:
                    wait_mins = 8
                    log(f"Hearts empty! Waiting {wait_mins} min for regen...")
                    time.sleep(wait_mins * 60)
                    lobby_fail_count = 0
                    relaunch()
                    continue
                log(f"  Lobby: tapping Play (attempt {lobby_fail_count})")
                monkey_script(generate_play_taps(), throttle_ms=50)
                time.sleep(10)
                # Check if we actually entered gameplay before tutorial dismiss
                check_img = screenshot()
                if check_img:
                    try:
                        check_arr = np.array(Image.open(check_img))
                        check_screen = detect_screen(check_arr)
                        if check_screen != "gameplay":
                            log(f"  Play tap → {check_screen} (not gameplay, skipping tutorial)")
                            continue
                    except Exception:
                        pass
                # Dismiss tutorial/popup overlays
                if not tutorial_dismissed:
                    log("  Dismissing tutorial...")
                    monkey_script(generate_tutorial_dismiss_taps(), throttle_ms=20)
                    time.sleep(5)
                    # Second pass for multi-step tutorials
                    monkey_script(generate_tutorial_dismiss_taps(), throttle_ms=20)
                    time.sleep(3)
                    tutorial_dismissed = True
                last_board_pixels = 999999
                gameplay_turns = 0
                deploy_cycle = 0
                continue

            # ---- WIN ----
            if screen == "win":
                games_won += 1
                lobby_fail_count = 0
                tutorial_dismissed = False
                last_board_pixels = 999999
                gameplay_turns = 0
                deploy_cycle = 0
                board_unchanged_count = 0
                log(f"WIN! (total: {games_won})")
                # Tap dialog buttons with safe grid
                monkey_script(generate_dialog_dismiss_taps(), throttle_ms=15)
                time.sleep(5)
                continue

            # ---- FAIL ----
            if screen == "fail":
                games_failed += 1
                tutorial_dismissed = False
                last_board_pixels = 999999
                gameplay_turns = 0
                deploy_cycle = 0
                board_unchanged_count = 0
                log(f"FAIL! (total: {games_failed})")
                monkey_script(generate_dialog_dismiss_taps(), throttle_ms=15)
                time.sleep(5)
                continue

            # ---- HEARTS EMPTY ----
            if screen == "hearts_empty":
                # Try 받기 (watch ad for +1 heart) button via monkey script
                # Button at approx (300, 870) on overlay
                log("  Hearts empty! Trying ad button...")
                monkey_script([(300, 870), (280, 860), (320, 880), (300, 870)],
                              throttle_ms=300)
                time.sleep(5)
                # Check if ad started (screen changes)
                check = screenshot()
                if check:
                    check_arr = np.array(Image.open(check))
                    check_screen = detect_screen(check_arr)
                    if check_screen != "hearts_empty":
                        log(f"  >> Ad button worked? Screen: {check_screen}")
                        # Wait for ad to finish
                        time.sleep(35)
                        back()
                        time.sleep(3)
                        back()
                        time.sleep(3)
                        relaunch()
                        lobby_fail_count = 0
                        continue
                # Ad didn't work, fall back to wait
                wait_mins = 8
                log(f"  Ad failed, waiting {wait_mins} min for regen...")
                back()
                time.sleep(2)
                time.sleep(wait_mins * 60)
                lobby_fail_count = 0
                relaunch()
                continue

            # ---- STORE ----
            if screen == "store":
                log(f"  >> Store detected (stuck={stuck_count})")
                # Can't close store via overlay buttons
                # Try home icon at bottom (background layer)
                tap(405, 1850)
                time.sleep(3)
                if stuck_count > 3:
                    # Force relaunch
                    log("  >> Store stuck, relaunching...")
                    relaunch()
                    stuck_count = 0
                    gameplay_turns = 0
                    tutorial_dismissed = False
                continue

            # ---- POPUP ----
            if screen == "popup":
                log(f"  >> Popup (stuck={stuck_count})")
                # Try safe grid to dismiss
                monkey_script(generate_dialog_dismiss_taps(), throttle_ms=15)
                time.sleep(3)
                if stuck_count > 8:
                    relaunch()
                    stuck_count = 0
                    lobby_fail_count = 0
                    gameplay_turns = 0
                    tutorial_dismissed = False
                continue

            # ---- UNKNOWN ----
            if screen == "unknown":
                if stuck_count > 5:
                    log(f"  >> Unknown x{stuck_count}, relaunching...")
                    relaunch()
                    stuck_count = 0
                    tutorial_dismissed = False
                else:
                    log("  >> Unknown screen, trying safe grid")
                    monkey_script(generate_dialog_dismiss_taps(), throttle_ms=15)
                    time.sleep(2)
                continue

            # ---- GAMEPLAY ----
            lobby_fail_count = 0
            gameplay_turns += 1

            board_px = count_board_pixels(arr)
            progress = last_board_pixels - board_px
            if abs(progress) < 50:
                board_unchanged_count += 1
            else:
                board_unchanged_count = 0
            if turn % 3 == 0:
                log(f"  Board: {board_px} (delta={progress}) gp={gameplay_turns} unchg={board_unchanged_count}")
            last_board_pixels = board_px

            # Board frozen: escalating recovery
            # Each cycle is ~50s, so 5 turns = ~4 min
            if board_unchanged_count > 3 and gameplay_turns > 2:
                if board_unchanged_count <= 5:
                    # Full screen tap to dismiss any invisible popup/tutorial
                    log(f"  >> Board stuck {board_unchanged_count} turns, full screen dismiss...")
                    full_taps = generate_full_screen_taps()
                    monkey_script(full_taps, throttle_ms=15)
                    time.sleep(10)
                elif board_unchanged_count <= 7:
                    # Try dragging pigs to belt (connected pig mechanic)
                    log(f"  >> Board stuck {board_unchanged_count} turns, trying drags...")
                    drags = generate_drag_to_belt()
                    monkey_script_drags(drags, move_steps=5, throttle_ms=30)
                    time.sleep(15)
                elif board_unchanged_count > 8:
                    log(f"  >> Board frozen {board_unchanged_count} turns, relaunching...")
                    relaunch()
                    stuck_count = 0
                    gameplay_turns = 0
                    board_unchanged_count = 0
                    tutorial_dismissed = False
                    continue

            # Deploy strategy: multi-phase with pauses for tutorial/eating.
            # Connected pig pairs (Level 15+) are tutorial levels - need time.
            deploy_cycle += 1
            taps = generate_deploy_taps()
            if deploy_cycle <= 3 or deploy_cycle % 5 == 0:
                log(f"  Deploy #{deploy_cycle}: {len(taps)} taps, board={board_px}")

            # Deploy all available pigs to fill belt
            monkey_script(taps, throttle_ms=30)
            time.sleep(3)
            # Second pass to catch any missed pigs
            monkey_script(taps, throttle_ms=30)
            # Wait for belt to clear: 5 pigs eating ~20-40 tiles each
            # Belt full (5/5) means no new deploys until pigs finish eating.
            # Background layer may not update until eating cycle completes.
            # Wait 45s for full eating+belt travel cycle.
            time.sleep(45)

            # Board cleared check
            if board_px < 500:
                log(f"  Board nearly clear! ({board_px} px)")

            # Stuck: board not clearing after many deploys
            # Connected pig pairs can freeze game state entirely
            if gameplay_turns > 30 and stuck_count > 25:
                log(f"  >> Gameplay stuck x{stuck_count}, board={board_px}")
                if stuck_count > 40:
                    log("  >> Board frozen (likely connected pig lock), relaunching...")
                    relaunch()
                    stuck_count = 0
                    gameplay_turns = 0
                    tutorial_dismissed = False

        except Exception as e:
            log(f"ERROR: {e}")
            traceback.print_exc()
            time.sleep(3)

    log(f"\n=== SESSION COMPLETE ===")
    log(f"Games won:    {games_won}")
    log(f"Games failed: {games_failed}")
    log(f"Total turns:  {turn}")


if __name__ == "__main__":
    minutes = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    play_game(minutes)
