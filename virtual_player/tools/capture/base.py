"""
Capture Base — 장르 공통 인프라
================================
ADB 연결, 에뮬레이터 탐지, 제스처 감지, 세션 관리, Delta 계산.
각 장르 캡처 모듈이 이 클래스를 상속/조합해서 사용.
"""

import ctypes
import ctypes.wintypes
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ═══════════════════════════════════════════════════════════════════════════════
# Emulator Registry
# ═══════════════════════════════════════════════════════════════════════════════

_EMULATORS = {
    "BlueStacks": {
        "adb_candidates": [
            r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
            r"C:\Program Files (x86)\BlueStacks_nxt\HD-Adb.exe",
            r"C:\Program Files\BlueStacks5\HD-Adb.exe",
            r"C:\Program Files\BlueStacks\HD-Adb.exe",
        ],
        "window_patterns": [
            ("HwndWrapper[Bluestacks_nxt_", None),
            (None, "BlueStacks App Player"),
            (None, "BlueStacks"),
        ],
    },
    "LDPlayer": {
        "adb_candidates": [
            r"C:\LDPlayer\LDPlayer9\adb.exe",
            r"C:\LDPlayer\LDPlayer4.0\adb.exe",
            r"C:\Program Files\LDPlayer\LDPlayer9\adb.exe",
            r"C:\Program Files (x86)\LDPlayer\LDPlayer9\adb.exe",
            r"D:\LDPlayer\LDPlayer9\adb.exe",
        ],
        "window_patterns": [
            ("LDPlayerMainFrame", None),
            (None, "LDPlayer"),
        ],
    },
    "Nox": {
        "adb_candidates": [
            r"C:\Program Files\Nox\bin\nox_adb.exe",
            r"C:\Program Files (x86)\Nox\bin\nox_adb.exe",
        ],
        "window_patterns": [
            (None, "NoxPlayer"),
            ("Qt5QWindowIcon", "NoxPlayer"),
        ],
    },
    "MEmu": {
        "adb_candidates": [
            r"C:\Program Files\Microvirt\MEmu\adb.exe",
            r"D:\Program Files\Microvirt\MEmu\adb.exe",
        ],
        "window_patterns": [
            (None, "MEmu"),
        ],
    },
}


class EmulatorRegistry:
    """에뮬레이터 탐지/ADB 경로 검색."""

    @staticmethod
    def find_adb(emu_type: str) -> str:
        if emu_type not in _EMULATORS:
            return ""
        for path in _EMULATORS[emu_type]["adb_candidates"]:
            if Path(path).exists():
                return path
        return ""

    @staticmethod
    def detect_installed() -> List[str]:
        found = []
        for name, info in _EMULATORS.items():
            for path in info["adb_candidates"]:
                if Path(path).exists():
                    found.append(name)
                    break
        return found if found else ["Custom"]

    @staticmethod
    def get_window_patterns(emu_type: str) -> list:
        if emu_type in _EMULATORS:
            return _EMULATORS[emu_type]["window_patterns"]
        all_p = []
        for info in _EMULATORS.values():
            all_p.extend(info["window_patterns"])
        return all_p

    @staticmethod
    def all_types() -> List[str]:
        return list(_EMULATORS.keys()) + ["Custom"]


# ═══════════════════════════════════════════════════════════════════════════════
# ADB Connection
# ═══════════════════════════════════════════════════════════════════════════════

class ADBConnection:
    """ADB 래퍼 — 스크린샷, shell 명령, 포그라운드 앱 감지."""

    def __init__(self, adb_path: str, serial: str):
        self.adb_path = adb_path
        self.serial = serial
        self._app_name_cache: Dict[str, str] = {}

    def cmd(self, *args: str, timeout: float = 10) -> subprocess.CompletedProcess:
        cmd_list = [self.adb_path, "-s", self.serial] + list(args)
        return subprocess.run(
            cmd_list, capture_output=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

    def shell(self, *args: str, timeout: float = 10) -> str:
        result = self.cmd("shell", *args, timeout=timeout)
        return result.stdout.decode("utf-8", errors="replace").strip()

    def screenshot_bytes(self) -> bytes:
        try:
            result = self.cmd("exec-out", "screencap", "-p", timeout=10)
            if result.returncode == 0 and len(result.stdout) > 1000:
                return result.stdout
        except Exception:
            pass
        return b""

    def screenshot_save(self, save_path: Path) -> bool:
        data = self.screenshot_bytes()
        if data:
            save_path.write_bytes(data)
            return True
        return False

    def get_foreground_app(self) -> str:
        for cmd_args, pattern in [
            (("dumpsys", "activity", "activities", "|", "grep", "mResumedActivity"),
             r"([a-zA-Z][a-zA-Z0-9_.]+)/"),
            (("dumpsys", "activity", "recents", "|", "grep", "topActivity"),
             r"([a-zA-Z][a-zA-Z0-9_.]+)/"),
        ]:
            try:
                out = self.shell(*cmd_args, timeout=5)
                match = re.search(pattern, out)
                if match:
                    return match.group(1)
            except Exception:
                pass
        return "unknown_app"

    def get_app_label(self, package: str) -> str:
        if package in self._app_name_cache:
            return self._app_name_cache[package]
        parts = package.split(".")
        label = parts[-1] if len(parts) > 1 else package
        label = re.sub(r"[^\w\-.]", "_", label)
        self._app_name_cache[package] = label
        return label

    def get_resolution(self) -> Tuple[int, int]:
        try:
            out = self.shell("wm", "size", timeout=5)
            match = re.search(r"(\d+)x(\d+)", out)
            if match:
                return (int(match.group(1)), int(match.group(2)))
        except Exception:
            pass
        return (0, 0)

    @staticmethod
    def detect_devices(adb_path: str) -> List[Tuple[str, str]]:
        try:
            result = subprocess.run(
                [adb_path, "devices"],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            lines = result.stdout.decode("utf-8", errors="replace").strip().splitlines()
            devices = []
            for line in lines[1:]:
                parts = line.strip().split("\t")
                if len(parts) >= 2 and parts[1] in ("device", "emulator"):
                    devices.append((parts[0], parts[1]))
            return devices
        except Exception:
            return []


# ═══════════════════════════════════════════════════════════════════════════════
# Window Detection
# ═══════════════════════════════════════════════════════════════════════════════

def find_emulator_hwnd(emu_type: str = "BlueStacks") -> Optional[int]:
    user32 = ctypes.windll.user32
    patterns = EmulatorRegistry.get_window_patterns(emu_type)
    found = []

    def _enum_cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf_cls = ctypes.create_unicode_buffer(256)
        buf_title = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf_cls, 256)
        user32.GetWindowTextW(hwnd, buf_title, 256)
        cls = buf_cls.value
        title = buf_title.value
        for pat_cls, pat_title in patterns:
            cls_ok = pat_cls is None or cls.startswith(pat_cls.rstrip("*"))
            title_ok = pat_title is None or pat_title.lower() in title.lower()
            if cls_ok and title_ok:
                found.append(hwnd)
                return True
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
    return found[0] if found else None


def get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                     ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    rect = RECT()
    if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# TapMonitor — Windows WH_MOUSE_LL hook
# ═══════════════════════════════════════════════════════════════════════════════

class TapMonitor:
    """에뮬레이터 클릭/스와이프/롱프레스 감지."""

    WH_MOUSE_LL = 14
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP = 0x0202
    WM_MOUSEMOVE = 0x0200

    def __init__(self, emu_type: str = "BlueStacks",
                 swipe_threshold: int = 50, long_press_ms: int = 600):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._gesture_events: list = []
        self._lock = threading.Lock()
        self._hook = None
        self._emu_type = emu_type
        self._emu_hwnd: Optional[int] = None
        self._emu_rect: Optional[Tuple[int, int, int, int]] = None
        self._rect_update_time = 0.0
        self._swipe_threshold = swipe_threshold
        self._long_press_ms = long_press_ms
        self._down_time: float = 0.0
        self._down_pos: Optional[Tuple[int, int]] = None
        self._down_screen: Optional[Tuple[int, int]] = None
        self._move_pos: Optional[Tuple[int, int]] = None

    def start(self):
        self._emu_hwnd = find_emulator_hwnd(self._emu_type)
        if self._emu_hwnd:
            self._emu_rect = get_window_rect(self._emu_hwnd)
        self._running = True
        self._thread = threading.Thread(target=self._hook_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def pop_events(self) -> list:
        with self._lock:
            events = self._gesture_events[:]
            self._gesture_events.clear()
        return events

    def pop_taps(self) -> list:
        events = self.pop_events()
        return [(e["time"], e["x"], e["y"]) for e in events if e["action"] == "tap"]

    def get_emu_info(self) -> str:
        if self._emu_hwnd:
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(self._emu_hwnd, buf, 256)
            return buf.value or self._emu_type
        return "Not found"

    def _update_rect(self):
        now = time.time()
        if now - self._rect_update_time < 1.0:
            return
        self._rect_update_time = now
        if not self._emu_hwnd or not ctypes.windll.user32.IsWindow(self._emu_hwnd):
            self._emu_hwnd = find_emulator_hwnd(self._emu_type)
        if self._emu_hwnd:
            self._emu_rect = get_window_rect(self._emu_hwnd)

    def _is_in_emulator(self, x: int, y: int) -> bool:
        self._update_rect()
        if not self._emu_rect:
            return False
        l, t, r, b = self._emu_rect
        return l <= x <= r and t <= y <= b

    def _to_relative(self, sx: int, sy: int) -> Tuple[int, int]:
        l, t, _, _ = self._emu_rect
        return sx - l, sy - t

    def _hook_loop(self):
        user32 = ctypes.windll.user32

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("pt", POINT), ("mouseData", ctypes.c_ulong),
                         ("flags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                         ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_int, ctypes.c_int, ctypes.POINTER(MSLLHOOKSTRUCT))

        def low_level_mouse_proc(nCode, wParam, lParam):
            if nCode < 0:
                return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)
            ms = lParam.contents
            sx, sy = ms.pt.x, ms.pt.y

            if wParam == self.WM_LBUTTONDOWN:
                if self._is_in_emulator(sx, sy):
                    self._down_time = time.time()
                    self._down_pos = self._to_relative(sx, sy)
                    self._down_screen = (sx, sy)
                    self._move_pos = self._down_pos
                else:
                    self._down_pos = None
            elif wParam == self.WM_MOUSEMOVE:
                if self._down_pos is not None and self._emu_rect:
                    self._move_pos = self._to_relative(sx, sy)
            elif wParam == self.WM_LBUTTONUP:
                if self._down_pos is not None:
                    up_time = time.time()
                    hold_ms = int((up_time - self._down_time) * 1000)
                    rx, ry = self._down_pos
                    end_rx, end_ry = self._move_pos or self._down_pos
                    dist = ((end_rx - rx) ** 2 + (end_ry - ry) ** 2) ** 0.5
                    evt = {"time": self._down_time}
                    if dist >= self._swipe_threshold:
                        evt.update(action="swipe", x=rx, y=ry,
                                   end_x=end_rx, end_y=end_ry, duration_ms=hold_ms)
                    elif hold_ms >= self._long_press_ms:
                        evt.update(action="long_press", x=rx, y=ry, hold_ms=hold_ms)
                    else:
                        evt.update(action="tap", x=rx, y=ry)
                    with self._lock:
                        self._gesture_events.append(evt)
                    self._down_pos = None
                    self._move_pos = None

            return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

        self._hook_proc = HOOKPROC(low_level_mouse_proc)
        self._hook = user32.SetWindowsHookExW(
            self.WH_MOUSE_LL, self._hook_proc, None, 0)

        msg = ctypes.wintypes.MSG()
        while self._running:
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.01)

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None


# ═══════════════════════════════════════════════════════════════════════════════
# Delta Computation
# ═══════════════════════════════════════════════════════════════════════════════

def compute_pixel_delta(img_a: bytes, img_b: bytes,
                        threshold: int = 25,
                        region: Optional[Tuple[int, int, int, int]] = None) -> float:
    """
    두 스크린샷의 픽셀 변화 비율 (0.0~1.0).

    Args:
        img_a, img_b: PNG bytes
        threshold: 변화로 간주할 최소 픽셀 차이 (0-255)
        region: (x, y, w, h) — 특정 영역만 비교. None이면 전체.

    Returns:
        변화 비율 (0.0=동일, 1.0=전부 다름), 실패 시 -1.0
    """
    if not _HAS_PIL or not img_a or not img_b:
        return -1.0
    try:
        a = Image.open(io.BytesIO(img_a))
        b = Image.open(io.BytesIO(img_b))
        if region:
            rx, ry, rw, rh = region
            a = a.crop((rx, ry, rx + rw, ry + rh))
            b = b.crop((rx, ry, rx + rw, ry + rh))
        a = a.convert("L").resize((270, 480))
        b = b.convert("L").resize((270, 480))
        pa, pb = list(a.getdata()), list(b.getdata())
        diff = sum(1 for x, y in zip(pa, pb) if abs(x - y) > threshold)
        return round(diff / len(pa), 4)
    except Exception:
        return -1.0


def compute_roi_deltas(img_a: bytes, img_b: bytes,
                       regions: Dict[str, Tuple[int, int, int, int]],
                       threshold: int = 25) -> Dict[str, float]:
    """여러 ROI 영역의 Delta를 한번에 계산."""
    if not _HAS_PIL or not img_a or not img_b:
        return {name: -1.0 for name in regions}
    try:
        a = Image.open(io.BytesIO(img_a))
        b = Image.open(io.BytesIO(img_b))
        results = {}
        for name, (rx, ry, rw, rh) in regions.items():
            try:
                ca = a.crop((rx, ry, rx + rw, ry + rh)).convert("L")
                cb = b.crop((rx, ry, rx + rw, ry + rh)).convert("L")
                if ca.size[0] == 0 or ca.size[1] == 0:
                    results[name] = -1.0
                    continue
                pa, pb = list(ca.getdata()), list(cb.getdata())
                diff = sum(1 for x, y in zip(pa, pb) if abs(x - y) > threshold)
                results[name] = round(diff / len(pa), 4)
            except Exception:
                results[name] = -1.0
        return results
    except Exception:
        return {name: -1.0 for name in regions}


# ═══════════════════════════════════════════════════════════════════════════════
# Session Manager
# ═══════════════════════════════════════════════════════════════════════════════

class SessionManager:
    """에피소드/세션 JSONL 로깅 관리."""

    def __init__(self, output_root: Path, adb: ADBConnection):
        self.output_root = output_root
        self.adb = adb
        self.current_app = ""
        self.episode_id = 0
        self.episode_action_count = 0
        self.episode_start_time = 0.0
        self.last_action_time = 0.0
        self.total_captures = 0
        self.counters: Dict[str, int] = {}
        self._episode_timeout = 30

    @property
    def app_label(self) -> str:
        return self.adb.get_app_label(self.current_app)

    @property
    def app_dir(self) -> Path:
        d = self.output_root / self.app_label
        d.mkdir(parents=True, exist_ok=True)
        return d

    def set_episode_timeout(self, seconds: int):
        self._episode_timeout = seconds

    def start_episode(self) -> int:
        self.episode_id += 1
        self.episode_action_count = 0
        self.episode_start_time = time.time()
        self.last_action_time = time.time()
        self._write_event("episode_start")
        return self.episode_id

    def end_episode(self):
        if self.episode_action_count > 0:
            dur = int(time.time() - self.episode_start_time)
            self._write_event("episode_end", {
                "duration_sec": dur,
                "action_count": self.episode_action_count,
            })

    def check_timeout(self) -> bool:
        if (self.episode_action_count > 0
                and (time.time() - self.last_action_time) > self._episode_timeout):
            self.end_episode()
            self.start_episode()
            return True
        return False

    def check_app_change(self) -> Optional[str]:
        new_app = self.adb.get_foreground_app()
        if new_app != self.current_app:
            old = self.current_app
            self.end_episode()
            self.current_app = new_app
            self.start_episode()
            return old
        return None

    def record_action(self) -> int:
        """액션 카운터 증가, seq 반환."""
        label = self.app_label
        count = self.counters.get(label, 0) + 1
        self.counters[label] = count
        self.total_captures += 1
        self.episode_action_count += 1
        self.last_action_time = time.time()
        return count

    def write_log(self, entry: dict):
        log_path = self.app_dir / "session_log.jsonl"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _write_event(self, event_type: str, extra: Optional[dict] = None):
        entry = {
            "event": event_type,
            "episode_id": self.episode_id,
            "app": self.current_app,
            "timestamp": datetime.now().isoformat(),
        }
        if extra:
            entry.update(extra)
        self.write_log(entry)


# ═══════════════════════════════════════════════════════════════════════════════
# Base Capture Engine (abstract)
# ═══════════════════════════════════════════════════════════════════════════════

class BaseCaptureEngine(ABC):
    """
    장르별 캡처 엔진의 공통 인터페이스.
    각 장르 모듈은 이걸 상속해서 process_event()를 구현.
    """

    GENRE = "base"

    def __init__(self, adb: ADBConnection, session: SessionManager,
                 log_fn: Optional[Callable] = None):
        self.adb = adb
        self.session = session
        self._log_fn = log_fn or (lambda msg, **kw: None)
        self.resolution: Tuple[int, int] = (0, 0)
        self.prev_frame_bytes: bytes = b""

    def log(self, msg: str, tag: str = "info"):
        self._log_fn(msg, tag=tag)

    def detect_resolution(self):
        self.resolution = self.adb.get_resolution()

    def normalize_coords(self, x: int, y: int) -> Tuple[Optional[float], Optional[float]]:
        rw, rh = self.resolution
        if rw > 0 and rh > 0:
            return round(x / rw, 4), round(y / rh, 4)
        return None, None

    @abstractmethod
    def process_event(self, evt: dict):
        """제스처 이벤트 처리 — 장르별 구현 필수."""

    @abstractmethod
    def on_start(self):
        """캡처 시작 시 초기화."""

    @abstractmethod
    def on_stop(self):
        """캡처 종료 시 정리."""

    def format_action(self, evt: dict) -> str:
        action = evt["action"]
        x, y = evt["x"], evt["y"]
        if action == "swipe":
            return f"swipe({x},{y}->{evt.get('end_x')},{evt.get('end_y')} {evt.get('duration_ms')}ms)"
        elif action == "long_press":
            return f"long_press({x},{y} {evt.get('hold_ms')}ms)"
        return f"tap({x},{y})"

    def build_base_entry(self, evt: dict, seq: int, before_file: str,
                         after_file: Optional[str] = None) -> dict:
        """JSONL 공통 필드."""
        nx, ny = self.normalize_coords(evt["x"], evt["y"])
        entry = {
            "seq": seq,
            "genre": self.GENRE,
            "episode_id": self.session.episode_id,
            "timestamp": datetime.now().isoformat(),
            "action": evt["action"],
            "x": evt["x"],
            "y": evt["y"],
            "norm_x": nx,
            "norm_y": ny,
            "resolution": list(self.resolution) if self.resolution != (0, 0) else None,
            "file": before_file,
            "app": self.session.current_app,
        }
        if evt["action"] == "swipe":
            entry["end_x"] = evt.get("end_x")
            entry["end_y"] = evt.get("end_y")
            entry["duration_ms"] = evt.get("duration_ms")
            rw, rh = self.resolution
            if rw > 0:
                entry["norm_end_x"] = round(evt.get("end_x", 0) / rw, 4)
                entry["norm_end_y"] = round(evt.get("end_y", 0) / rh, 4)
        elif evt["action"] == "long_press":
            entry["hold_ms"] = evt.get("hold_ms")
        if after_file:
            entry["after_file"] = after_file
        return entry
