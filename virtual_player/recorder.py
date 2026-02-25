"""
Gameplay Recorder (Event-Driven)
==================================
Records user touch events with precise before/after screenshots.

Two capture modes (auto-detected):
  1. getevent mode  — real Android devices / emulators that support getevent
  2. mouse capture  — BlueStacks / Windows emulators (captures host mouse clicks)

Both modes produce identical output:
  recording.json with events[] each having screenshot_before/screenshot_after.

Usage:
  python -m virtual_player record --game ash_n_veil
  python -m virtual_player build-graph --game ash_n_veil --screens screen_types.json
"""

import ctypes
import re
import json
import sys
import time
import threading
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .adb import adb_cfg, adb_run, adb_check_device, get_device_resolution, take_screenshot, log


# ---------------------------------------------------------------------------
# getevent utilities
# ---------------------------------------------------------------------------

_LINE_RE = re.compile(
    r'\[\s*([\d.]+)\]\s+\S+:\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)'
)
_ABS_MAX_RE = re.compile(r'max\s+(\d+)')


def find_touch_device() -> str:
    """Auto-detect the touch input device."""
    r = adb_run("shell", "getevent", "-il", timeout=10)
    if r.returncode != 0 or not r.stdout:
        return "/dev/input/event1"

    text = r.stdout.decode("utf-8", errors="replace")
    current_device = ""
    for line in text.splitlines():
        if line.startswith("add device"):
            parts = line.split(":")
            if len(parts) >= 2:
                current_device = parts[-1].strip()
        elif "ABS_MT_POSITION_X" in line and current_device:
            return current_device

    return "/dev/input/event1"


def _get_input_axis_max(device: str = "") -> Tuple[int, int]:
    """Query input device axis max values for coordinate scaling."""
    r = adb_run("shell", "getevent", "-il", device, timeout=5)
    if r.returncode != 0 or not r.stdout:
        return 0, 0

    text = r.stdout.decode("utf-8", errors="replace")
    x_max, y_max = 0, 0
    current_axis = None
    for line in text.splitlines():
        if "ABS_MT_POSITION_X" in line:
            m = _ABS_MAX_RE.search(line)
            if m:
                x_max = int(m.group(1))
            else:
                current_axis = "x"
        elif "ABS_MT_POSITION_Y" in line:
            m = _ABS_MAX_RE.search(line)
            if m:
                y_max = int(m.group(1))
            else:
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


def _scale_coord(raw: int, axis_max: int, screen_max: int) -> int:
    if axis_max > 0:
        return int(raw * screen_max / axis_max)
    return raw


def _test_getevent(touch_device: str) -> bool:
    """Test if getevent actually captures events by sending a tap and checking."""
    cmd = [adb_cfg.adb_path, "-s", adb_cfg.device,
           "shell", f"getevent -lt {touch_device} & GEID=$!; "
                    f"sleep 0.5; input tap 1 1; sleep 1; kill $GEID 2>/dev/null; wait $GEID 2>/dev/null"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=10)
        output = r.stdout.decode("utf-8", errors="replace")
        return "EV_ABS" in output or "EV_SYN" in output
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Windows Mouse Capture (for BlueStacks)
# ---------------------------------------------------------------------------

def _find_bluestacks_hwnd() -> Optional[int]:
    """Find BlueStacks App Player window handle."""
    if sys.platform != "win32":
        return None

    user32 = ctypes.windll.user32
    from ctypes import wintypes

    found = []

    def _enum_cb(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if "BlueStacks App Player" in title:
                if user32.IsWindowVisible(hwnd):
                    found.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)

    return found[0] if found else None


def _screen_to_game_coords(screen_x: int, screen_y: int, hwnd: int,
                           game_w: int, game_h: int) -> Tuple[int, int]:
    """Translate Windows screen coordinates to game coordinates.

    Returns (-1, -1) if the point is outside the BlueStacks client area.
    """
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    # Convert screen coords to client coords
    pt = wintypes.POINT(screen_x, screen_y)
    user32.ScreenToClient(hwnd, ctypes.byref(pt))

    # Get client area size
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    client_w = rect.right
    client_h = rect.bottom

    if pt.x < 0 or pt.y < 0 or pt.x > client_w or pt.y > client_h:
        return -1, -1

    # Scale to game resolution
    game_x = int(pt.x * game_w / client_w) if client_w > 0 else 0
    game_y = int(pt.y * game_h / client_h) if client_h > 0 else 0
    return game_x, game_y


# ---------------------------------------------------------------------------
# Recording directory
# ---------------------------------------------------------------------------

def get_recordings_dir(game_key: str) -> Path:
    """Get the recordings directory for a game."""
    return adb_cfg.data_dir / "recordings" / game_key


# ---------------------------------------------------------------------------
# Record (auto-detect mode)
# ---------------------------------------------------------------------------

def record(game_key: str, transition_wait: float = 0.8):
    """Record user touch events with event-driven screenshots.

    Auto-detects capture mode:
      - getevent: for real devices / emulators with working getevent
      - mouse capture: for BlueStacks (captures Windows mouse clicks)

    Args:
        game_key: Game identifier (e.g. 'ash_n_veil')
        transition_wait: Seconds to wait after touch for screen transition (default 0.8)
    """
    if not adb_check_device():
        log(f"ERROR: Device {adb_cfg.device} not connected.")
        return None

    rec_dir = get_recordings_dir(game_key)
    frames_dir = rec_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    screen_w, screen_h = get_device_resolution()
    log(f"Screen resolution: {screen_w}x{screen_h}")

    # Test getevent
    touch_device = find_touch_device()
    log(f"Touch device: {touch_device}")
    log(f"Testing getevent...")
    getevent_works = _test_getevent(touch_device)

    if getevent_works:
        log(f"getevent OK — using getevent mode")
        return _record_getevent(game_key, rec_dir, frames_dir,
                                screen_w, screen_h, touch_device, transition_wait)
    else:
        # Try Windows mouse capture (BlueStacks)
        hwnd = _find_bluestacks_hwnd()
        if hwnd:
            log(f"getevent unavailable — using Windows mouse capture (BlueStacks)")
            return _record_mouse_capture(game_key, rec_dir, frames_dir,
                                         screen_w, screen_h, hwnd, transition_wait)
        else:
            log(f"ERROR: getevent not working and BlueStacks window not found.")
            log(f"Cannot record touch events.")
            return None


# ---------------------------------------------------------------------------
# Mode 1: getevent recording
# ---------------------------------------------------------------------------

def _record_getevent(game_key: str, rec_dir: Path, frames_dir: Path,
                     screen_w: int, screen_h: int, touch_device: str,
                     transition_wait: float):
    """Record using Android getevent (for real devices)."""
    input_x_max, input_y_max = _get_input_axis_max(touch_device)
    if input_x_max > 0:
        log(f"Input axis max: X={input_x_max}, Y={input_y_max}")
    else:
        log("Input axis max not detected; assuming raw == screen coords")

    stop_file = rec_dir / ".stop"
    if stop_file.exists():
        stop_file.unlink()

    log(f"Recording to: {rec_dir}")
    log(f"Transition wait: {transition_wait}s")

    # Initial screenshot
    frame_idx = 1
    initial_frame = f"frame_{frame_idx:04d}.png"
    take_screenshot(frames_dir / initial_frame)
    latest_frame = initial_frame
    log(f"  Initial screenshot: {initial_frame}")
    log(f"\nPlay the game now. Press Ctrl+C to stop recording.\n")

    lock = threading.Lock()
    events: List[Dict] = []
    stop_event = threading.Event()
    base_time: List[Optional[float]] = [None]
    touch_positions: List[Tuple[int, int]] = []
    touch_start_time: List[Optional[float]] = [None]
    cur_x_y: List[int] = [0, 0]

    cmd = [adb_cfg.adb_path, "-s", adb_cfg.device,
           "shell", "getevent", "-lt", touch_device]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _event_loop():
        nonlocal frame_idx, latest_frame

        for raw_line in proc.stdout:
            if stop_event.is_set():
                break
            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            m = _LINE_RE.match(line)
            if not m:
                continue

            ts = float(m.group(1))
            ev_type = m.group(2)
            ev_code = m.group(3)
            ev_value = int(m.group(4), 16)

            if base_time[0] is None:
                base_time[0] = ts

            if ev_type == "EV_ABS":
                if ev_code == "ABS_MT_TRACKING_ID":
                    if ev_value == 0xFFFFFFFF:
                        # Touch UP
                        if touch_start_time[0] is not None and touch_positions:
                            _handle_getevent_up(
                                ts, touch_start_time[0], list(touch_positions),
                                frames_dir, screen_w, screen_h,
                                input_x_max, input_y_max, base_time[0],
                                transition_wait, lock, events,
                            )
                        touch_start_time[0] = None
                        touch_positions.clear()
                    else:
                        touch_start_time[0] = ts
                        touch_positions.clear()
                elif ev_code == "ABS_MT_POSITION_X":
                    cur_x_y[0] = ev_value
                elif ev_code == "ABS_MT_POSITION_Y":
                    cur_x_y[1] = ev_value
            elif ev_type == "EV_SYN" and ev_code == "SYN_REPORT":
                if touch_start_time[0] is not None:
                    touch_positions.append((cur_x_y[0], cur_x_y[1]))

    def _handle_getevent_up(end_ts, start_ts, positions, f_dir, sw, sh,
                            ixm, iym, bt, tw, lk, evts):
        nonlocal frame_idx, latest_frame

        before_frame = latest_frame
        time.sleep(tw)

        with lk:
            frame_idx += 1
            after_name = f"frame_{frame_idx:04d}.png"
        take_screenshot(f_dir / after_name)
        latest_frame = after_name

        first, last = positions[0], positions[-1]
        x1 = _scale_coord(first[0], ixm, sw)
        y1 = _scale_coord(first[1], iym, sh)
        dx, dy = abs(last[0] - first[0]), abs(last[1] - first[1])
        dist = (dx**2 + dy**2) ** 0.5
        dur = max(0, int((end_ts - start_ts) * 1000))

        if dist < 50 and dur < 500:
            evt = {"type": "tap", "timestamp": round(start_ts - bt, 3),
                   "x": x1, "y": y1,
                   "screenshot_before": before_frame, "screenshot_after": after_name}
        else:
            x2 = _scale_coord(last[0], ixm, sw)
            y2 = _scale_coord(last[1], iym, sh)
            evt = {"type": "swipe", "timestamp": round(start_ts - bt, 3),
                   "x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": dur,
                   "screenshot_before": before_frame, "screenshot_after": after_name}

        with lk:
            evts.append(evt)
        coord = f"({evt.get('x', evt.get('x1'))},{evt.get('y', evt.get('y1'))})"
        log(f"  #{len(evts)} {evt['type']} {coord}  [{before_frame} -> {after_name}]")

    reader_thread = threading.Thread(target=_event_loop, daemon=True)
    reader_thread.start()

    try:
        while not stop_event.is_set():
            if stop_file.exists():
                log("\nStop signal received...")
                try:
                    stop_file.unlink()
                except OSError:
                    pass
                stop_event.set()
                break
            time.sleep(0.2)
    except KeyboardInterrupt:
        log("\nStopping recording...")
        stop_event.set()

    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()
    reader_thread.join(timeout=3)

    return _save_recording(game_key, rec_dir, events, screen_w, screen_h,
                           "getevent", transition_wait, frame_idx,
                           input_x_max=input_x_max, input_y_max=input_y_max)


# ---------------------------------------------------------------------------
# Mode 2: Windows mouse capture (BlueStacks)
# ---------------------------------------------------------------------------

def _record_mouse_capture(game_key: str, rec_dir: Path, frames_dir: Path,
                          screen_w: int, screen_h: int, hwnd: int,
                          transition_wait: float):
    """Record using Windows mouse capture (for BlueStacks)."""
    from ctypes import wintypes
    user32 = ctypes.windll.user32

    # Log window info
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    log(f"BlueStacks window: hwnd={hwnd}, client={rect.right}x{rect.bottom}")
    log(f"Coordinate mapping: {rect.right}x{rect.bottom} -> {screen_w}x{screen_h}")

    stop_file = rec_dir / ".stop"
    if stop_file.exists():
        stop_file.unlink()

    log(f"Recording to: {rec_dir}")
    log(f"Transition wait: {transition_wait}s")

    # Initial screenshot
    frame_idx = 1
    initial_frame = f"frame_{frame_idx:04d}.png"
    take_screenshot(frames_dir / initial_frame)
    latest_frame = initial_frame
    log(f"  Initial screenshot: {initial_frame}")
    log(f"\nPlay the game now. Press Ctrl+C to stop recording.\n")

    events: List[Dict] = []
    start_time = time.time()
    mouse_was_down = False
    click_start_time: Optional[float] = None
    click_game_x, click_game_y = 0, 0
    click_before_frame = ""

    VK_LBUTTON = 0x01

    try:
        while True:
            # Check stop signal
            if stop_file.exists():
                log("\nStop signal received...")
                try:
                    stop_file.unlink()
                except OSError:
                    pass
                break

            # Poll mouse state
            mouse_down = bool(user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000)

            if mouse_down and not mouse_was_down:
                # --- Mouse DOWN ---
                pt = wintypes.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                gx, gy = _screen_to_game_coords(pt.x, pt.y, hwnd, screen_w, screen_h)

                if gx >= 0:
                    # Click is within BlueStacks
                    click_before_frame = latest_frame
                    click_start_time = time.time()
                    click_game_x, click_game_y = gx, gy

            elif not mouse_down and mouse_was_down:
                # --- Mouse UP ---
                if click_start_time is not None:
                    # Measure duration BEFORE transition wait
                    release_time = time.time()
                    dur_ms = int((release_time - click_start_time) * 1000)

                    # Get release position for swipe detection
                    pt = wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(pt))
                    rel_gx, rel_gy = _screen_to_game_coords(pt.x, pt.y, hwnd, screen_w, screen_h)
                    if rel_gx < 0:
                        rel_gx, rel_gy = click_game_x, click_game_y

                    # Wait for screen transition
                    time.sleep(transition_wait)

                    # Take "after" screenshot
                    frame_idx += 1
                    after_name = f"frame_{frame_idx:04d}.png"
                    take_screenshot(frames_dir / after_name)
                    latest_frame = after_name

                    # Classify tap vs swipe
                    dx = abs(rel_gx - click_game_x)
                    dy = abs(rel_gy - click_game_y)
                    dist = (dx**2 + dy**2) ** 0.5
                    timestamp = round(click_start_time - start_time, 3)

                    if dist < 50 and dur_ms < 500:
                        evt = {
                            "type": "tap",
                            "timestamp": timestamp,
                            "x": click_game_x, "y": click_game_y,
                            "screenshot_before": click_before_frame,
                            "screenshot_after": after_name,
                        }
                    else:
                        evt = {
                            "type": "swipe",
                            "timestamp": timestamp,
                            "x1": click_game_x, "y1": click_game_y,
                            "x2": rel_gx, "y2": rel_gy,
                            "duration_ms": dur_ms,
                            "screenshot_before": click_before_frame,
                            "screenshot_after": after_name,
                        }

                    events.append(evt)
                    coord = f"({evt.get('x', evt.get('x1'))},{evt.get('y', evt.get('y1'))})"
                    log(f"  #{len(events)} {evt['type']} {coord}  "
                        f"[{click_before_frame} -> {after_name}]")

                    click_start_time = None

            mouse_was_down = mouse_down
            time.sleep(0.015)  # ~66Hz polling

    except KeyboardInterrupt:
        log("\nStopping recording...")

    return _save_recording(game_key, rec_dir, events, screen_w, screen_h,
                           "mouse_capture", transition_wait, frame_idx)


# ---------------------------------------------------------------------------
# Save recording
# ---------------------------------------------------------------------------

def _save_recording(game_key: str, rec_dir: Path, events: List[Dict],
                    screen_w: int, screen_h: int,
                    mode: str, transition_wait: float, frame_count: int,
                    input_x_max: int = 0, input_y_max: int = 0) -> Path:
    """Save recording.json with all events."""
    recording = {
        "game": game_key,
        "device": adb_cfg.device,
        "resolution": [screen_w, screen_h],
        "recorded_at": datetime.now().isoformat(),
        "mode": mode,
        "transition_wait": transition_wait,
        "input_axis_max": {"x": input_x_max, "y": input_y_max},
        "events": events,
    }

    rec_file = rec_dir / "recording.json"
    rec_file.write_text(json.dumps(recording, ensure_ascii=False, indent=2), encoding="utf-8")

    tap_count = sum(1 for e in events if e["type"] == "tap")
    swipe_count = sum(1 for e in events if e["type"] == "swipe")
    log(f"\nRecording saved: {rec_file}")
    log(f"  Mode: {mode}")
    log(f"  Events: {len(events)} ({tap_count} taps, {swipe_count} swipes)")
    log(f"  Frames: {frame_count}")

    return rec_file


# ---------------------------------------------------------------------------
# Vision Annotation
# ---------------------------------------------------------------------------

_ANNOTATE_PROMPT_TEMPLATE = """모바일 게임에서 사용자의 터치 조작을 분석합니다.
Before 이미지(터치 전)와 After 이미지(터치 후)를 비교하세요.

터치 정보: {action_type} at ({x},{y}) on {res_w}x{res_h} screen

가능한 화면 타입:
{screen_types_text}

다음 JSON 형식으로 정확히 응답하세요:
{{
  "before_screen": "화면 타입",
  "after_screen": "화면 타입",
  "element": "터치한 UI 요소의 식별 이름 (영문, snake_case. 예: shop_button, back_icon, character_list, scroll_area, item_slot_1, empty_area)",
  "category": "navigation 또는 interaction 또는 scroll 또는 idle",
  "screen_changed": true 또는 false,
  "description": "이 행동이 게임 안에서 하는 역할 설명 (한줄)"
}}

category 판단 기준:
- navigation: 화면 타입이 바뀜 (다른 화면으로 이동)
- interaction: 같은 화면이지만 내용이 바뀜 (팝업 열기, 아이템 선택, 탭 전환 등)
- scroll: 같은 화면에서 스크롤/스와이프로 보이는 영역이 이동
- idle: 빈 영역 터치 등 의미 있는 변화 없음

주의사항:
- before_screen과 after_screen은 반드시 위 화면 타입 목록에서 선택
- element는 화면에서 터치 좌표({x},{y})에 해당하는 실제 UI 요소를 영문 snake_case로 명명
- 같은 화면 타입이라도 스크롤 위치만 다르면 category는 "scroll"
- 두 이미지가 거의 동일하면 category는 "idle"
"""


def _annotate_event(event: Dict, frames_dir: Path,
                    screen_types: Dict[str, str],
                    res_w: int, res_h: int) -> Optional[Dict]:
    """Annotate a single recorded event using Vision comparison."""
    from .adb import claude_vision_annotate

    before_frame = event.get("screenshot_before", "")
    after_frame = event.get("screenshot_after", "")
    if not before_frame or not after_frame:
        return None

    before_path = frames_dir / before_frame
    after_path = frames_dir / after_frame
    if not before_path.exists() or not after_path.exists():
        return None

    action_type = event.get("type", "tap")
    if action_type == "tap":
        x, y = event.get("x", 0), event.get("y", 0)
    else:
        x, y = event.get("x1", 0), event.get("y1", 0)

    screen_types_text = "\n".join(f"  - {k}: {v}" for k, v in screen_types.items())

    prompt = _ANNOTATE_PROMPT_TEMPLATE.format(
        action_type=action_type, x=x, y=y,
        res_w=res_w, res_h=res_h,
        screen_types_text=screen_types_text,
    )

    result = claude_vision_annotate(prompt, before_path, after_path,
                                     model="haiku", timeout=90)

    if "error" in result:
        log(f"    [Annotate] Error: {result.get('error')}")
        return None

    annotation = {
        "seq": event.get("_seq", 0),
        "timestamp": event.get("timestamp", 0),
        "action_type": action_type,
        "x": x, "y": y,
        "screenshot_before": before_frame,
        "screenshot_after": after_frame,
        "before_screen": result.get("before_screen", "unknown"),
        "after_screen": result.get("after_screen", "unknown"),
        "element": result.get("element", ""),
        "category": result.get("category", "unknown"),
        "screen_changed": result.get("screen_changed", False),
        "description": result.get("description", ""),
    }

    if action_type == "swipe":
        annotation["x2"] = event.get("x2", 0)
        annotation["y2"] = event.get("y2", 0)
        annotation["duration_ms"] = event.get("duration_ms", 0)

    return annotation


# ---------------------------------------------------------------------------
# Graph Builder (Vision-Annotated)
# ---------------------------------------------------------------------------

def build_graph(game_key: str, screen_types: Dict[str, str]) -> Optional[Path]:
    """Build annotated nav_graph.json from recording via Vision comparison.

    For each recorded touch event:
    1. Send before + after screenshots to Claude Vision
    2. Get: screen types, element name, category (navigation/scroll/interaction/idle)
    3. navigation -> graph edge, scroll/interaction -> node's in_screen_actions

    Args:
        game_key: Game identifier
        screen_types: Dict of {screen_type: description}

    Returns:
        Path to saved nav_graph.json, or None on failure.
    """
    rec_dir = get_recordings_dir(game_key)
    rec_file = rec_dir / "recording.json"
    frames_dir = rec_dir / "frames"

    if not rec_file.exists():
        log(f"ERROR: No recording found: {rec_file}")
        log(f"Record first: python -m virtual_player record --game {game_key}")
        return None

    if not frames_dir.exists() or not list(frames_dir.glob("*.png")):
        log(f"ERROR: No frames in {frames_dir}")
        return None

    data = json.loads(rec_file.read_text(encoding="utf-8"))
    events = data.get("events", [])
    resolution = data.get("resolution", [1080, 1920])
    res_w, res_h = resolution[0], resolution[1]

    if not events:
        log(f"ERROR: No events in recording")
        return None

    log(f"Building annotated nav graph...")
    log(f"  Recording: {rec_file}")
    log(f"  Events to annotate: {len(events)}")
    log(f"  Resolution: {res_w}x{res_h}")
    log(f"")

    annotations: List[Dict] = []
    for i, event in enumerate(events):
        event["_seq"] = i + 1
        log(f"  [{i+1}/{len(events)}] Annotating {event['type']} "
            f"({event.get('x', event.get('x1', '?'))},{event.get('y', event.get('y1', '?'))})...")

        annotation = _annotate_event(event, frames_dir, screen_types, res_w, res_h)

        if annotation:
            annotations.append(annotation)
            cat_icon = {"navigation": "->", "scroll": "~~",
                        "interaction": "**", "idle": "--"}.get(annotation["category"], "??")
            log(f"    {cat_icon} [{annotation['before_screen']}] "
                f"{annotation['element']} ({annotation['category']}) "
                f"[{annotation['after_screen']}]")
            log(f"       {annotation['description']}")
        else:
            log(f"    !! Annotation failed, skipping")

    log(f"\n  Annotated: {len(annotations)}/{len(events)} events")

    # Save annotations
    ann_file = rec_dir / "annotations.json"
    ann_file.write_text(
        json.dumps(annotations, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"  Annotations saved: {ann_file}")

    # Summary
    cat_counts: Dict[str, int] = {}
    element_counts: Dict[str, int] = {}
    for ann in annotations:
        cat = ann.get("category", "unknown")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        elem = ann.get("element", "")
        if elem:
            element_counts[elem] = element_counts.get(elem, 0) + 1

    log(f"\n  Categories:")
    for c, n in sorted(cat_counts.items(), key=lambda x: -x[1]):
        log(f"    {c}: {n}")
    log(f"  Elements:")
    for e, n in sorted(element_counts.items(), key=lambda x: -x[1]):
        log(f"    {e}: {n}")

    # Build graph
    from .navigation.nav_graph import NavigationGraph
    graph = NavigationGraph.build_from_annotated(annotations)

    graph_path = rec_dir / "nav_graph.json"
    graph.save(graph_path)

    game_data_dir = adb_cfg.data_dir / "games" / game_key
    game_data_dir.mkdir(parents=True, exist_ok=True)
    graph_copy_path = game_data_dir / "nav_graph.json"
    graph.save(graph_copy_path)
    log(f"  Graph also copied to: {graph_copy_path}")

    return graph_path
