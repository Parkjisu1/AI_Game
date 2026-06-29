"""
Click Capture v3 — Emulator Auto Screenshot (GUI)
===================================================
exe로 빌드하여 바로 실행 가능.
에뮬레이터(BlueStacks / LDPlayer) 선택 후 탭할 때마다 스크린샷 저장.

v3 변경:
  - 에뮬레이터 선택 UI (BlueStacks / LDPlayer / Custom)
  - 선택에 따라 ADB 자동 탐지 + 윈도우 탐지 연동
  - SUNO-inspired 다크 테마 UI

v2 기능 유지:
  - Before/After 페어 캡처
  - 좌표 정규화, Delta Score, 에피소드 구분, 제스처 확장

빌드: python build_click_capture.py
실행: ClickCapture.exe
"""

import ctypes
import ctypes.wintypes
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Optional, Tuple

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# ---------------------------------------------------------------------------
# Emulator Registry
# ---------------------------------------------------------------------------
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
            r"C:\Program Files (x86)\Microvirt\MEmu\adb.exe",
        ],
        "window_patterns": [
            (None, "MEmu"),
        ],
    },
}


def find_adb_for_emulator(emu_type: str) -> str:
    """선택된 에뮬레이터 타입에 맞는 ADB 경로 자동 탐지."""
    if emu_type in _EMULATORS:
        for p in _EMULATORS[emu_type]["adb_candidates"]:
            if Path(p).exists():
                return p
    # fallback: Android SDK
    sdk_path = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
    if Path(sdk_path).exists():
        return sdk_path
    ah = os.environ.get("ANDROID_HOME", "")
    if ah:
        p = os.path.join(ah, "platform-tools", "adb.exe")
        if Path(p).exists():
            return p
    return ""


def detect_installed_emulators() -> list:
    """설치된 에뮬레이터 목록 반환."""
    found = []
    for name, info in _EMULATORS.items():
        for p in info["adb_candidates"]:
            if Path(p).exists():
                found.append(name)
                break
    return found if found else ["Custom"]


def get_window_patterns(emu_type: str) -> list:
    """에뮬레이터 타입에 해당하는 윈도우 패턴만 반환."""
    if emu_type in _EMULATORS:
        return _EMULATORS[emu_type]["window_patterns"]
    # Custom: 모든 에뮬레이터 패턴 합침
    all_patterns = []
    for info in _EMULATORS.values():
        all_patterns.extend(info["window_patterns"])
    return all_patterns


# ---------------------------------------------------------------------------
# Delta Score
# ---------------------------------------------------------------------------
def compute_delta(img_bytes_a: bytes, img_bytes_b: bytes) -> float:
    if not _HAS_PIL or not img_bytes_a or not img_bytes_b:
        return -1.0
    try:
        a = Image.open(io.BytesIO(img_bytes_a)).convert("L").resize((270, 480))
        b = Image.open(io.BytesIO(img_bytes_b)).convert("L").resize((270, 480))
        pa, pb = list(a.getdata()), list(b.getdata())
        diff = sum(1 for x, y in zip(pa, pb) if abs(x - y) > 25)
        return round(diff / len(pa), 4)
    except Exception:
        return -1.0


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def get_config_path() -> Path:
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    return base / "click_capture_config.json"


def detect_devices(adb_path: str) -> list:
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


def load_config() -> dict:
    defaults = {
        "emulator_type": "BlueStacks",
        "adb_path": "",
        "serial": "auto",
        "output_folder": str(Path.home() / "Desktop" / "ClickCaptures"),
        "cooldown": 0.3,
        "before_after": True,
        "after_delay_ms": 500,
        "episode_timeout": 30,
        "swipe_threshold": 50,
        "long_press_ms": 600,
    }
    cfg_path = get_config_path()
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_config(cfg: dict):
    try:
        with open(get_config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# ADB Utility
# ---------------------------------------------------------------------------
_ADB = ""
_SERIAL = ""


def adb_cmd(*args: str, timeout: float = 10) -> subprocess.CompletedProcess:
    cmd = [_ADB, "-s", _SERIAL] + list(args)
    return subprocess.run(
        cmd, capture_output=True, timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def adb_shell(*args: str, timeout: float = 10) -> str:
    result = adb_cmd("shell", *args, timeout=timeout)
    return result.stdout.decode("utf-8", errors="replace").strip()


# ---------------------------------------------------------------------------
# Foreground App
# ---------------------------------------------------------------------------
def get_foreground_app() -> str:
    try:
        out = adb_shell("dumpsys", "activity", "activities",
                        "|", "grep", "mResumedActivity", timeout=5)
        match = re.search(r"([a-zA-Z][a-zA-Z0-9_.]+)/", out)
        if match:
            return match.group(1)
    except Exception:
        pass
    try:
        out = adb_shell("dumpsys", "activity", "recents",
                        "|", "grep", "topActivity", timeout=5)
        match = re.search(r"([a-zA-Z][a-zA-Z0-9_.]+)/", out)
        if match:
            return match.group(1)
    except Exception:
        pass
    return "unknown_app"


# ---------------------------------------------------------------------------
# App Label
# ---------------------------------------------------------------------------
_app_name_cache: dict = {}


def get_app_label(package: str) -> str:
    if package in _app_name_cache:
        return _app_name_cache[package]
    parts = package.split(".")
    label = parts[-1] if len(parts) > 1 else package
    label = re.sub(r"[^\w\-.]", "_", label)
    _app_name_cache[package] = label
    return label


# ---------------------------------------------------------------------------
# Screenshot
# ---------------------------------------------------------------------------
def screenshot_adb(save_path: Path) -> bool:
    try:
        result = adb_cmd("exec-out", "screencap", "-p", timeout=10)
        if result.returncode == 0 and len(result.stdout) > 100:
            save_path.write_bytes(result.stdout)
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Emulator Window Detection (filtered by emulator type)
# ---------------------------------------------------------------------------
def _find_emulator_hwnd(emu_type: str = "BlueStacks") -> Optional[int]:
    """선택된 에뮬레이터 타입의 윈도우 핸들만 탐색."""
    user32 = ctypes.windll.user32
    patterns = get_window_patterns(emu_type)
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


def _get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                     ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    rect = RECT()
    if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


# ---------------------------------------------------------------------------
# TapMonitor
# ---------------------------------------------------------------------------
class TapMonitor:
    """Windows WH_MOUSE_LL hook for emulator click/swipe/long_press detection."""

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
        self._emu_hwnd = _find_emulator_hwnd(self._emu_type)
        if self._emu_hwnd:
            self._emu_rect = _get_window_rect(self._emu_hwnd)
        self._running = True
        self._thread = threading.Thread(target=self._hook_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        # UnhookWindowsHookEx is called by _hook_loop thread itself (lines 492-494)
        # Calling it from a different thread causes the message pump to deadlock.
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
            self._emu_hwnd = _find_emulator_hwnd(self._emu_type)
        if self._emu_hwnd:
            self._emu_rect = _get_window_rect(self._emu_hwnd)

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
                        evt["action"] = "swipe"
                        evt["x"] = rx
                        evt["y"] = ry
                        evt["end_x"] = end_rx
                        evt["end_y"] = end_ry
                        evt["duration_ms"] = hold_ms
                    elif hold_ms >= self._long_press_ms:
                        evt["action"] = "long_press"
                        evt["x"] = rx
                        evt["y"] = ry
                        evt["hold_ms"] = hold_ms
                    else:
                        evt["action"] = "tap"
                        evt["x"] = rx
                        evt["y"] = ry

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


# ---------------------------------------------------------------------------
# Theme — SUNO-inspired Dark UI
# ---------------------------------------------------------------------------
class SunoTheme:
    """SUNO HomePage-inspired dark color palette for tkinter."""
    BG = "#0d0d0d"
    CARD = "#161618"
    SURFACE = "#1c1c1f"
    BORDER = "#2a2a2e"
    ACCENT = "#8b5cf6"
    ACCENT_HOVER = "#a78bfa"
    ACCENT_DIM = "#6d42d4"
    TEXT = "#e4e4e7"
    TEXT_DIM = "#8b8b94"
    TEXT_MUTED = "#57575e"
    SUCCESS = "#34d399"
    WARNING = "#fbbf24"
    ERROR = "#f87171"
    FONT = ("Segoe UI", 9)
    FONT_BOLD = ("Segoe UI", 9, "bold")
    FONT_HEADING = ("Segoe UI", 11, "bold")
    FONT_SMALL = ("Segoe UI", 8)
    FONT_LOG = ("Cascadia Code", 9)
    RADIUS = 8

    @classmethod
    def apply(cls, root: tk.Tk):
        root.configure(bg=cls.BG)

        style = ttk.Style()
        style.theme_use("clam")

        # Global
        style.configure(".",
                         background=cls.BG,
                         foreground=cls.TEXT,
                         fieldbackground=cls.SURFACE,
                         bordercolor=cls.BORDER,
                         darkcolor=cls.SURFACE,
                         lightcolor=cls.SURFACE,
                         troughcolor=cls.BG,
                         selectbackground=cls.ACCENT,
                         selectforeground="#ffffff",
                         font=cls.FONT)

        # Frames
        style.configure("TFrame", background=cls.BG)
        style.configure("Card.TFrame", background=cls.CARD)
        style.configure("Surface.TFrame", background=cls.SURFACE)

        # Labels
        style.configure("TLabel", background=cls.BG, foreground=cls.TEXT, font=cls.FONT)
        style.configure("Heading.TLabel", font=cls.FONT_HEADING, foreground=cls.TEXT)
        style.configure("Dim.TLabel", foreground=cls.TEXT_DIM, font=cls.FONT)
        style.configure("Muted.TLabel", foreground=cls.TEXT_MUTED, font=cls.FONT_SMALL)
        style.configure("Card.TLabel", background=cls.CARD, foreground=cls.TEXT, font=cls.FONT)
        style.configure("CardDim.TLabel", background=cls.CARD, foreground=cls.TEXT_DIM, font=cls.FONT)
        style.configure("Accent.TLabel", foreground=cls.ACCENT, font=cls.FONT_BOLD)
        style.configure("Success.TLabel", foreground=cls.SUCCESS, font=cls.FONT_BOLD)
        style.configure("Error.TLabel", foreground=cls.ERROR, font=cls.FONT_BOLD)

        # LabelFrame
        style.configure("TLabelframe",
                         background=cls.CARD,
                         foreground=cls.TEXT_DIM,
                         bordercolor=cls.BORDER,
                         font=cls.FONT_SMALL)
        style.configure("TLabelframe.Label",
                         background=cls.CARD,
                         foreground=cls.TEXT_DIM,
                         font=cls.FONT_SMALL)

        # Buttons
        style.configure("TButton",
                         background=cls.SURFACE,
                         foreground=cls.TEXT,
                         bordercolor=cls.BORDER,
                         padding=(12, 6),
                         font=cls.FONT)
        style.map("TButton",
                   background=[("active", cls.BORDER), ("disabled", cls.BG)],
                   foreground=[("disabled", cls.TEXT_MUTED)])

        style.configure("Accent.TButton",
                         background=cls.ACCENT,
                         foreground="#ffffff",
                         bordercolor=cls.ACCENT_DIM,
                         padding=(16, 8),
                         font=cls.FONT_BOLD)
        style.map("Accent.TButton",
                   background=[("active", cls.ACCENT_HOVER), ("disabled", cls.TEXT_MUTED)])

        style.configure("Danger.TButton",
                         background="#dc2626",
                         foreground="#ffffff",
                         bordercolor="#991b1b",
                         padding=(16, 8),
                         font=cls.FONT_BOLD)
        style.map("Danger.TButton",
                   background=[("active", "#ef4444"), ("disabled", cls.TEXT_MUTED)])

        # Entry
        style.configure("TEntry",
                         fieldbackground=cls.SURFACE,
                         foreground=cls.TEXT,
                         bordercolor=cls.BORDER,
                         insertcolor=cls.TEXT,
                         padding=5)
        style.map("TEntry",
                   bordercolor=[("focus", cls.ACCENT)],
                   fieldbackground=[("focus", "#1e1e22")])

        # Combobox
        style.configure("TCombobox",
                         fieldbackground=cls.SURFACE,
                         foreground=cls.TEXT,
                         bordercolor=cls.BORDER,
                         arrowcolor=cls.TEXT_DIM,
                         padding=5)
        style.map("TCombobox",
                   bordercolor=[("focus", cls.ACCENT)],
                   fieldbackground=[("readonly", cls.SURFACE)])

        # Checkbutton
        style.configure("TCheckbutton",
                         background=cls.CARD,
                         foreground=cls.TEXT,
                         font=cls.FONT)
        style.map("TCheckbutton",
                   background=[("active", cls.CARD)])

        # Radiobutton
        style.configure("TRadiobutton",
                         background=cls.CARD,
                         foreground=cls.TEXT,
                         font=cls.FONT)
        style.map("TRadiobutton",
                   background=[("active", cls.CARD)])

        # Separator
        style.configure("TSeparator", background=cls.BORDER)

        # Notebook (tabs)
        style.configure("TNotebook", background=cls.BG, bordercolor=cls.BORDER)
        style.configure("TNotebook.Tab",
                         background=cls.SURFACE,
                         foreground=cls.TEXT_DIM,
                         padding=(12, 6))
        style.map("TNotebook.Tab",
                   background=[("selected", cls.CARD)],
                   foreground=[("selected", cls.TEXT)])

        # Scrollbar
        style.configure("Vertical.TScrollbar",
                         background=cls.SURFACE,
                         bordercolor=cls.BG,
                         arrowcolor=cls.TEXT_DIM,
                         troughcolor=cls.BG)


# ---------------------------------------------------------------------------
# GUI App
# ---------------------------------------------------------------------------
class ClickCaptureApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Click Capture")
        self.root.geometry("720x640")
        self.root.resizable(True, True)
        self.root.minsize(620, 520)

        SunoTheme.apply(root)

        self.cfg = load_config()
        self._running = False
        self._monitor: Optional[TapMonitor] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._current_app = ""
        self._counters: dict = {}
        self._last_capture_time = 0.0
        self._total = 0
        self._episode_id = 0
        self._episode_action_count = 0
        self._episode_start_time = 0.0
        self._last_action_time = 0.0
        self._prev_frame_bytes: bytes = b""
        self._emu_resolution: Tuple[int, int] = (0, 0)

        self._build_ui()
        self._apply_config()

    def _build_ui(self):
        T = SunoTheme
        pad_x = 16
        pad_y = 6

        # ── Header ──
        header = tk.Frame(self.root, bg=T.CARD, height=56)
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)

        # title with accent bar
        accent_bar = tk.Frame(header, bg=T.ACCENT, width=3)
        accent_bar.pack(side="left", fill="y", padx=(pad_x, 0), pady=12)

        title_frame = tk.Frame(header, bg=T.CARD)
        title_frame.pack(side="left", padx=(8, 0), anchor="w")
        tk.Label(title_frame, text="Click Capture",
                 font=("Segoe UI", 13, "bold"), fg=T.TEXT, bg=T.CARD
                 ).pack(side="left")
        tk.Label(title_frame, text="v3",
                 font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD
                 ).pack(side="left", padx=(6, 0), pady=(4, 0))

        # status indicator in header
        self.var_status_dot = tk.StringVar(value="")
        self.lbl_status_dot = tk.Label(
            header, textvariable=self.var_status_dot,
            font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD)
        self.lbl_status_dot.pack(side="right", padx=(0, pad_x))

        # Thin separator
        tk.Frame(self.root, bg=T.BORDER, height=1).pack(fill="x")

        # ── Main content ──
        main = tk.Frame(self.root, bg=T.BG)
        main.pack(fill="both", expand=True, padx=pad_x, pady=pad_y)

        # ── Section: Emulator Selection ──
        emu_section = tk.Frame(main, bg=T.CARD, highlightbackground=T.BORDER,
                                highlightthickness=1)
        emu_section.pack(fill="x", pady=(pad_y, 4))

        emu_inner = tk.Frame(emu_section, bg=T.CARD)
        emu_inner.pack(fill="x", padx=12, pady=10)

        tk.Label(emu_inner, text="Emulator",
                 font=T.FONT_BOLD, fg=T.TEXT, bg=T.CARD
                 ).grid(row=0, column=0, sticky="w")

        self.var_emu_type = tk.StringVar(value="BlueStacks")
        installed = detect_installed_emulators()
        all_options = list(dict.fromkeys(installed + ["BlueStacks", "LDPlayer", "Custom"]))

        emu_combo_frame = tk.Frame(emu_inner, bg=T.CARD)
        emu_combo_frame.grid(row=0, column=1, padx=(12, 0), sticky="w")

        self.cmb_emu = ttk.Combobox(
            emu_combo_frame, textvariable=self.var_emu_type,
            values=all_options, width=16, state="readonly")
        self.cmb_emu.pack(side="left")
        self.cmb_emu.bind("<<ComboboxSelected>>", self._on_emulator_changed)

        self.lbl_emu_status = tk.Label(
            emu_combo_frame, text="", font=T.FONT_SMALL, fg=T.SUCCESS, bg=T.CARD)
        self.lbl_emu_status.pack(side="left", padx=(10, 0))

        # ADB path (same row, right side)
        tk.Label(emu_inner, text="ADB",
                 font=T.FONT_BOLD, fg=T.TEXT, bg=T.CARD
                 ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        adb_frame = tk.Frame(emu_inner, bg=T.CARD)
        adb_frame.grid(row=1, column=1, padx=(12, 0), sticky="ew", pady=(6, 0))
        emu_inner.columnconfigure(1, weight=1)

        self.var_adb = tk.StringVar()
        self.ent_adb = ttk.Entry(adb_frame, textvariable=self.var_adb, width=48)
        self.ent_adb.pack(side="left", fill="x", expand=True)
        ttk.Button(adb_frame, text="...", width=3,
                   command=self._browse_adb).pack(side="left", padx=(4, 0))

        # ── Section: Connection ──
        conn_section = tk.Frame(main, bg=T.CARD, highlightbackground=T.BORDER,
                                 highlightthickness=1)
        conn_section.pack(fill="x", pady=4)

        conn_inner = tk.Frame(conn_section, bg=T.CARD)
        conn_inner.pack(fill="x", padx=12, pady=10)

        # Device row
        tk.Label(conn_inner, text="Device",
                 font=T.FONT_BOLD, fg=T.TEXT, bg=T.CARD
                 ).grid(row=0, column=0, sticky="w")

        dev_frame = tk.Frame(conn_inner, bg=T.CARD)
        dev_frame.grid(row=0, column=1, padx=(12, 0), sticky="ew")
        conn_inner.columnconfigure(1, weight=1)

        self.var_serial = tk.StringVar()
        self.cmb_serial = ttk.Combobox(dev_frame, textvariable=self.var_serial, width=24)
        self.cmb_serial.pack(side="left")
        ttk.Button(dev_frame, text="Scan", width=6,
                   command=self._refresh_devices).pack(side="left", padx=(4, 0))
        ttk.Button(dev_frame, text="Test", width=6,
                   command=self._test_adb).pack(side="left", padx=(4, 0))

        # Output folder row
        tk.Label(conn_inner, text="Output",
                 font=T.FONT_BOLD, fg=T.TEXT, bg=T.CARD
                 ).grid(row=1, column=0, sticky="w", pady=(6, 0))

        out_frame = tk.Frame(conn_inner, bg=T.CARD)
        out_frame.grid(row=1, column=1, padx=(12, 0), sticky="ew", pady=(6, 0))

        self.var_output = tk.StringVar()
        ttk.Entry(out_frame, textvariable=self.var_output, width=48
                  ).pack(side="left", fill="x", expand=True)
        ttk.Button(out_frame, text="...", width=3,
                   command=self._browse_output).pack(side="left", padx=(4, 0))

        # ── Section: Capture Settings ──
        cap_section = tk.Frame(main, bg=T.CARD, highlightbackground=T.BORDER,
                                highlightthickness=1)
        cap_section.pack(fill="x", pady=4)

        cap_inner = tk.Frame(cap_section, bg=T.CARD)
        cap_inner.pack(fill="x", padx=12, pady=10)

        # Row 1: cooldown + before/after
        opt_row1 = tk.Frame(cap_inner, bg=T.CARD)
        opt_row1.pack(fill="x")

        tk.Label(opt_row1, text="Cooldown",
                 font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD).pack(side="left")
        self.var_cooldown = tk.StringVar()
        ttk.Entry(opt_row1, textvariable=self.var_cooldown, width=5
                  ).pack(side="left", padx=(6, 0))
        tk.Label(opt_row1, text="sec",
                 font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD
                 ).pack(side="left", padx=(2, 16))

        self.var_before_after = tk.BooleanVar()
        ttk.Checkbutton(opt_row1, text="Before / After pair",
                         variable=self.var_before_after).pack(side="left")

        tk.Label(opt_row1, text="Delay",
                 font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD
                 ).pack(side="left", padx=(16, 0))
        self.var_after_delay = tk.StringVar()
        ttk.Entry(opt_row1, textvariable=self.var_after_delay, width=5
                  ).pack(side="left", padx=(6, 0))
        tk.Label(opt_row1, text="ms",
                 font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD
                 ).pack(side="left", padx=(2, 0))

        # Row 2: episode timeout
        opt_row2 = tk.Frame(cap_inner, bg=T.CARD)
        opt_row2.pack(fill="x", pady=(6, 0))

        tk.Label(opt_row2, text="Episode timeout",
                 font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD).pack(side="left")
        self.var_episode_timeout = tk.StringVar()
        ttk.Entry(opt_row2, textvariable=self.var_episode_timeout, width=5
                  ).pack(side="left", padx=(6, 0))
        tk.Label(opt_row2, text="sec",
                 font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD
                 ).pack(side="left", padx=(2, 0))

        # ── Action buttons ──
        btn_frame = tk.Frame(main, bg=T.BG)
        btn_frame.pack(fill="x", pady=(8, 4))

        self.btn_start = ttk.Button(
            btn_frame, text="Start Capture", style="Accent.TButton",
            command=self._on_start)
        self.btn_start.pack(side="left")

        self.btn_stop = ttk.Button(
            btn_frame, text="Stop", style="Danger.TButton",
            command=self._on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))

        ttk.Button(btn_frame, text="Open Folder",
                   command=self._open_folder).pack(side="left", padx=(8, 0))

        # Capture counter
        self.var_count = tk.StringVar(value="0 captures")
        tk.Label(btn_frame, textvariable=self.var_count,
                 font=T.FONT_BOLD, fg=T.ACCENT, bg=T.BG
                 ).pack(side="right")

        # ── App info ──
        self.var_app = tk.StringVar(value="")
        tk.Label(main, textvariable=self.var_app,
                 font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.BG, anchor="w"
                 ).pack(fill="x", pady=(0, 2))

        # ── Log ──
        log_section = tk.Frame(main, bg=T.CARD, highlightbackground=T.BORDER,
                                highlightthickness=1)
        log_section.pack(fill="both", expand=True, pady=(4, pad_y))

        log_header = tk.Frame(log_section, bg=T.CARD)
        log_header.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(log_header, text="Log", font=T.FONT_BOLD,
                 fg=T.TEXT_DIM, bg=T.CARD).pack(side="left")

        self.log_text = tk.Text(
            log_section, height=10, font=T.FONT_LOG,
            bg="#111113", fg=T.TEXT_DIM,
            insertbackground=T.TEXT, selectbackground=T.ACCENT,
            borderwidth=0, highlightthickness=0,
            wrap="word", state="disabled", padx=12, pady=8)
        self.log_text.pack(fill="both", expand=True, padx=1, pady=(4, 1))

        # Log tag colors
        self.log_text.tag_configure("time", foreground=T.TEXT_MUTED)
        self.log_text.tag_configure("info", foreground=T.TEXT_DIM)
        self.log_text.tag_configure("success", foreground=T.SUCCESS)
        self.log_text.tag_configure("error", foreground=T.ERROR)
        self.log_text.tag_configure("accent", foreground=T.ACCENT)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_config(self):
        emu_type = self.cfg.get("emulator_type", "BlueStacks")
        self.var_emu_type.set(emu_type)

        adb = self.cfg.get("adb_path", "")
        if not adb or not Path(adb).exists():
            adb = find_adb_for_emulator(emu_type)
        self.var_adb.set(adb)

        self.var_serial.set(self.cfg.get("serial", "auto"))
        self.var_output.set(self.cfg.get("output_folder", ""))
        self.var_cooldown.set(str(self.cfg.get("cooldown", 0.3)))
        self.var_before_after.set(self.cfg.get("before_after", True))
        self.var_after_delay.set(str(self.cfg.get("after_delay_ms", 500)))
        self.var_episode_timeout.set(str(self.cfg.get("episode_timeout", 30)))

        self._update_emu_status()
        self.root.after(500, self._refresh_devices)

    def _update_emu_status(self):
        emu = self.var_emu_type.get()
        adb = self.var_adb.get()
        if adb and Path(adb).exists():
            self.lbl_emu_status.config(text="ADB found", fg=SunoTheme.SUCCESS)
        else:
            self.lbl_emu_status.config(text="ADB not found", fg=SunoTheme.ERROR)

    def _on_emulator_changed(self, event=None):
        emu_type = self.var_emu_type.get()
        if emu_type == "Custom":
            self._update_emu_status()
            return
        adb = find_adb_for_emulator(emu_type)
        if adb:
            self.var_adb.set(adb)
        self._update_emu_status()
        self._log(f"Emulator: {emu_type}", tag="accent")
        if adb:
            self._log(f"  ADB: {adb}", tag="success")
        else:
            self._log(f"  ADB not found for {emu_type}", tag="error")
        self.root.after(300, self._refresh_devices)

    def _save_current_config(self):
        self.cfg["emulator_type"] = self.var_emu_type.get()
        self.cfg["adb_path"] = self.var_adb.get()
        self.cfg["serial"] = self.var_serial.get()
        self.cfg["output_folder"] = self.var_output.get()
        try:
            self.cfg["cooldown"] = float(self.var_cooldown.get())
        except ValueError:
            self.cfg["cooldown"] = 0.3
        self.cfg["before_after"] = self.var_before_after.get()
        try:
            self.cfg["after_delay_ms"] = int(self.var_after_delay.get())
        except ValueError:
            self.cfg["after_delay_ms"] = 500
        try:
            self.cfg["episode_timeout"] = int(self.var_episode_timeout.get())
        except ValueError:
            self.cfg["episode_timeout"] = 30
        save_config(self.cfg)

    # ── Log ──
    def _log(self, msg: str, tag: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        def _append():
            self.log_text.config(state="normal")
            start = self.log_text.index("end-1c")
            self.log_text.insert("end", f" {ts} ", "time")
            self.log_text.insert("end", f" {msg}\n", tag)
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _append)

    # ── Device detection ──
    def _refresh_devices(self):
        adb_path = self.var_adb.get()
        if not adb_path or not Path(adb_path).exists():
            return
        devices = detect_devices(adb_path)
        if devices:
            serials = [d[0] for d in devices]
            self.cmb_serial["values"] = serials
            if self.var_serial.get() not in serials and self.var_serial.get() != "auto":
                self.var_serial.set(serials[0])
            self._log(f"Devices: {', '.join(serials)}", tag="success")
        else:
            self.cmb_serial["values"] = []
            self._log("No devices connected", tag="error")

    def _resolve_serial(self) -> bool:
        global _ADB, _SERIAL
        _ADB = self.var_adb.get()

        if not _ADB or not Path(_ADB).exists():
            messagebox.showerror("Error",
                f"ADB not found:\n{_ADB}\n\nSelect the correct emulator or browse for ADB.")
            return False

        serial = self.var_serial.get().strip()
        if serial and serial.lower() != "auto":
            _SERIAL = serial
            return True

        devices = detect_devices(_ADB)
        if not devices:
            emu = self.var_emu_type.get()
            messagebox.showerror("Error",
                f"No devices connected.\n\n"
                f"Make sure {emu} is running,\n"
                f"then click 'Scan' to refresh.")
            return False

        _SERIAL = devices[0][0]
        self.var_serial.set(_SERIAL)
        self._log(f"Auto-detected: {_SERIAL}", tag="success")
        return True

    # ── Button handlers ──
    def _browse_adb(self):
        path = filedialog.askopenfilename(
            title="Select ADB executable",
            filetypes=[("Executable", "*.exe"), ("All", "*.*")])
        if path:
            self.var_adb.set(path)
            self._update_emu_status()

    def _browse_output(self):
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.var_output.set(folder)

    def _open_folder(self):
        folder = self.var_output.get()
        if folder and Path(folder).exists():
            os.startfile(folder)
        else:
            messagebox.showinfo("Info", "Output folder not yet created.")

    def _test_adb(self):
        if not self._resolve_serial():
            return
        try:
            app = get_foreground_app()
            self._log(f"Connection OK  device={_SERIAL}  app={app}", tag="success")
        except Exception as e:
            self._log(f"Connection failed: {e}", tag="error")

    def _on_start(self):
        if not self._resolve_serial():
            return

        output_folder = self.var_output.get()
        if not output_folder:
            messagebox.showerror("Error", "Select an output folder first.")
            return

        try:
            cooldown = float(self.var_cooldown.get())
        except ValueError:
            cooldown = 0.3

        self._save_current_config()

        self._output_root = Path(output_folder)
        self._output_root.mkdir(parents=True, exist_ok=True)
        self._cooldown = cooldown
        self._counters = {}
        self._total = 0
        self._last_capture_time = 0.0

        self._running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.var_status_dot.set("Recording...")
        self.lbl_status_dot.config(fg=SunoTheme.SUCCESS)

        self._before_after = self.var_before_after.get()
        try:
            self._after_delay = int(self.var_after_delay.get()) / 1000.0
        except ValueError:
            self._after_delay = 0.5
        try:
            self._episode_timeout = int(self.var_episode_timeout.get())
        except ValueError:
            self._episode_timeout = 30

        swipe_th = self.cfg.get("swipe_threshold", 50)
        lp_ms = self.cfg.get("long_press_ms", 600)
        emu_type = self.var_emu_type.get()

        self._monitor = TapMonitor(
            emu_type=emu_type, swipe_threshold=swipe_th, long_press_ms=lp_ms)
        self._monitor.start()
        emu_info = self._monitor.get_emu_info()
        self._log(f"Window: {emu_info}", tag="accent")

        self._detect_resolution()

        self._current_app = get_foreground_app()
        app_label = get_app_label(self._current_app)
        self.var_app.set(f"{app_label}  ({self._current_app})")
        self._log(f"Capture started  output={output_folder}")
        self._log(f"App: {self._current_app}")
        if self._before_after:
            self._log(f"Before/After ON  delay={int(self._after_delay*1000)}ms")
        if self._emu_resolution != (0, 0):
            self._log(f"Resolution: {self._emu_resolution[0]}x{self._emu_resolution[1]}")

        self._start_new_episode()

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        self._poll_ui()

    def _on_stop(self):
        self._running = False
        self._end_current_episode()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self.var_status_dot.set("Stopping...")
        self.lbl_status_dot.config(fg=SunoTheme.TEXT_MUTED)

        def _cleanup():
            # Wait for capture thread to finish (may be blocked on ADB up to 10s)
            if self._capture_thread and self._capture_thread.is_alive():
                self._capture_thread.join(timeout=3)
            # Stop mouse hook (waits for hook thread to self-unhook)
            if self._monitor:
                self._monitor.stop()
            # Update UI from main thread
            self.root.after(0, self._on_stop_done)

        threading.Thread(target=_cleanup, daemon=True).start()

    def _on_stop_done(self):
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.var_status_dot.set("Stopped")
        self.lbl_status_dot.config(fg=SunoTheme.TEXT_MUTED)
        self._log(f"Stopped  total={self._total}  episodes={self._episode_id}", tag="accent")
        self._log_summary()

    def _on_close(self):
        self._running = False
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1)
        if self._monitor:
            self._monitor.stop()
        self._save_current_config()
        self.root.destroy()

    # ── Resolution ──
    def _detect_resolution(self):
        try:
            out = adb_shell("wm", "size", timeout=5)
            match = re.search(r"(\d+)x(\d+)", out)
            if match:
                self._emu_resolution = (int(match.group(1)), int(match.group(2)))
                return
        except Exception:
            pass
        self._emu_resolution = (0, 0)

    # ── Episode management ──
    def _start_new_episode(self):
        self._episode_id += 1
        self._episode_action_count = 0
        self._episode_start_time = time.time()
        self._last_action_time = time.time()
        self._prev_frame_bytes = b""
        self._log(f"Episode #{self._episode_id}", tag="accent")
        self._log_episode_event("episode_start")

    def _end_current_episode(self):
        if self._episode_action_count > 0:
            dur = int(time.time() - self._episode_start_time)
            self._log(f"Episode #{self._episode_id} end  actions={self._episode_action_count}  {dur}s")
            self._log_episode_event("episode_end", extra={
                "duration_sec": dur,
                "action_count": self._episode_action_count,
            })

    def _check_episode_timeout(self):
        if self._episode_action_count > 0 and (time.time() - self._last_action_time) > self._episode_timeout:
            self._end_current_episode()
            self._start_new_episode()

    def _log_episode_event(self, event_type: str, extra: dict = None):
        app_label = get_app_label(self._current_app)
        app_dir = self._output_root / app_label
        app_dir.mkdir(parents=True, exist_ok=True)
        log_path = app_dir / "session_log.jsonl"
        entry = {
            "event": event_type,
            "episode_id": self._episode_id,
            "app": self._current_app,
            "timestamp": datetime.now().isoformat(),
        }
        if extra:
            entry.update(extra)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    # ── Screenshot bytes ──
    def _screenshot_bytes(self) -> bytes:
        try:
            result = adb_cmd("exec-out", "screencap", "-p", timeout=10)
            if result.returncode == 0 and len(result.stdout) > 1000:
                return result.stdout
        except Exception:
            pass
        return b""

    # ── Capture loop ──
    def _capture_loop(self):
        app_check_interval = 3.0
        last_app_check = 0.0

        while self._running:
            now = time.time()

            if now - last_app_check > app_check_interval:
                try:
                    new_app = get_foreground_app()
                    if new_app != self._current_app:
                        old_label = get_app_label(self._current_app)
                        new_label = get_app_label(new_app)
                        self._end_current_episode()
                        self._current_app = new_app
                        self._start_new_episode()
                        self._log(f"App changed: {old_label} -> {new_label}")
                        self.root.after(0, lambda: self.var_app.set(
                            f"{new_label}  ({new_app})"))
                except Exception:
                    pass
                last_app_check = now

            self._check_episode_timeout()

            if self._monitor and self._running:
                events = self._monitor.pop_events()
                for evt in events:
                    if not self._running:
                        break
                    evt_time = evt["time"]
                    if evt_time - self._last_capture_time < self._cooldown:
                        continue
                    self._last_capture_time = evt_time
                    self._last_action_time = evt_time
                    self._take_screenshot_v2(evt)

            time.sleep(0.05)

    def _take_screenshot_v2(self, evt: dict):
        action = evt["action"]
        x, y = evt["x"], evt["y"]

        app_label = get_app_label(self._current_app)
        app_dir = self._output_root / app_label
        app_dir.mkdir(parents=True, exist_ok=True)

        count = self._counters.get(app_label, 0) + 1
        self._counters[app_label] = count
        self._total += 1
        self._episode_action_count += 1

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        seq = count

        before_bytes = self._screenshot_bytes()
        if not before_bytes:
            self._log(f"[{app_label}] #{count} FAILED  {action}({x},{y})", tag="error")
            return

        if self._before_after:
            before_name = f"click_{ts}_{seq:04d}_before.png"
        else:
            before_name = f"click_{ts}_{seq:04d}.png"

        before_path = app_dir / before_name
        before_path.write_bytes(before_bytes)

        delta = compute_delta(self._prev_frame_bytes, before_bytes)
        self._prev_frame_bytes = before_bytes

        after_name = None
        after_bytes = b""
        if self._before_after:
            time.sleep(self._after_delay)
            after_bytes = self._screenshot_bytes()
            if after_bytes:
                after_name = f"click_{ts}_{seq:04d}_after.png"
                (app_dir / after_name).write_bytes(after_bytes)
                self._total += 1

        res_w, res_h = self._emu_resolution
        norm_x = round(x / res_w, 4) if res_w > 0 else None
        norm_y = round(y / res_h, 4) if res_h > 0 else None

        action_str = action
        if action == "swipe":
            action_str = f"swipe({x},{y}->{evt.get('end_x')},{evt.get('end_y')} {evt.get('duration_ms')}ms)"
        elif action == "long_press":
            action_str = f"long_press({x},{y} {evt.get('hold_ms')}ms)"
        else:
            action_str = f"tap({x},{y})"

        delta_str = f" d={delta:.2%}" if delta >= 0 else ""
        pair_str = " +after" if after_name else ""
        self._log(f"[{app_label}] #{count}  {action_str}{pair_str}{delta_str}")

        self._log_event_v2(app_dir, evt, before_name, after_name, delta, norm_x, norm_y, seq)

    def _log_event_v2(self, app_dir: Path, evt: dict, before_file: str,
                      after_file: Optional[str], delta: float,
                      norm_x: Optional[float], norm_y: Optional[float], seq: int):
        log_path = app_dir / "session_log.jsonl"
        entry = {
            "seq": seq,
            "episode_id": self._episode_id,
            "timestamp": datetime.now().isoformat(),
            "action": evt["action"],
            "x": evt["x"],
            "y": evt["y"],
            "norm_x": norm_x,
            "norm_y": norm_y,
            "resolution": list(self._emu_resolution) if self._emu_resolution != (0, 0) else None,
            "file": before_file,
            "app": self._current_app,
            "delta_from_prev": delta if delta >= 0 else None,
        }
        if evt["action"] == "swipe":
            entry["end_x"] = evt.get("end_x")
            entry["end_y"] = evt.get("end_y")
            entry["duration_ms"] = evt.get("duration_ms")
            if self._emu_resolution != (0, 0):
                rw, rh = self._emu_resolution
                entry["norm_end_x"] = round(evt.get("end_x", 0) / rw, 4)
                entry["norm_end_y"] = round(evt.get("end_y", 0) / rh, 4)
        elif evt["action"] == "long_press":
            entry["hold_ms"] = evt.get("hold_ms")
        if after_file:
            entry["after_file"] = after_file

        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _log_summary(self):
        if not self._counters:
            return
        self._log("--- Summary ---", tag="accent")
        for app_label, count in sorted(self._counters.items()):
            self._log(f"  {app_label}: {count}")
        self._log(f"  Total: {self._total}  Episodes: {self._episode_id}")
        if self._emu_resolution != (0, 0):
            self._log(f"  Resolution: {self._emu_resolution[0]}x{self._emu_resolution[1]}")
        if not _HAS_PIL:
            self._log("  (PIL not installed - Delta Score disabled)")

    # ── UI polling ──
    def _poll_ui(self):
        if not self._running:
            return
        self.var_count.set(f"{self._total} captures")
        self.root.after(500, self._poll_ui)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    # High DPI
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    root = tk.Tk()
    app = ClickCaptureApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
