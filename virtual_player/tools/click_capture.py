"""
Click Capture — BlueStacks 클릭 감지 자동 스크린샷 (GUI)
=========================================================
exe로 빌드하여 바로 실행 가능.
블루스택에서 탭할 때마다 스크린샷 저장, 게임 변경 시 폴더 자동 분리.

빌드: python build_click_capture.py
실행: ClickCapture.exe
"""

import ctypes
import ctypes.wintypes
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

# ---------------------------------------------------------------------------
# 설정 파일 (exe 옆에 저장)
# ---------------------------------------------------------------------------
def get_config_path() -> Path:
    """exe와 같은 폴더에 config.json 저장."""
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
    return base / "click_capture_config.json"


def find_adb_path() -> str:
    """ADB 경로 자동 탐지. BlueStacks, LDPlayer, Nox, MEmu, Android SDK 순으로 검색."""
    candidates = [
        # BlueStacks
        r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
        r"C:\Program Files (x86)\BlueStacks_nxt\HD-Adb.exe",
        # LDPlayer
        r"C:\LDPlayer\LDPlayer9\adb.exe",
        r"C:\LDPlayer\LDPlayer4.0\adb.exe",
        # Nox
        r"C:\Program Files\Nox\bin\nox_adb.exe",
        r"C:\Program Files (x86)\Nox\bin\nox_adb.exe",
        # MEmu
        r"C:\Program Files\Microvirt\MEmu\adb.exe",
        r"C:\Program Files (x86)\Microvirt\MEmu\adb.exe",
        # Android SDK (common locations)
        os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
        os.path.expandvars(r"%ANDROID_HOME%\platform-tools\adb.exe") if os.environ.get("ANDROID_HOME") else "",
    ]
    for p in candidates:
        if p and Path(p).exists():
            return p
    return r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"


def detect_devices(adb_path: str) -> list:
    """ADB devices 명령으로 연결된 디바이스 목록 반환. [(serial, status), ...]"""
    try:
        result = subprocess.run(
            [adb_path, "devices"],
            capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        lines = result.stdout.decode("utf-8", errors="replace").strip().splitlines()
        devices = []
        for line in lines[1:]:  # skip "List of devices attached"
            parts = line.strip().split("\t")
            if len(parts) >= 2 and parts[1] in ("device", "emulator"):
                devices.append((parts[0], parts[1]))
        return devices
    except Exception:
        return []


def load_config() -> dict:
    defaults = {
        "adb_path": find_adb_path(),
        "serial": "auto",
        "output_folder": str(Path.home() / "Desktop" / "ClickCaptures"),
        "cooldown": 0.3,
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
# ADB 유틸
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
# 포그라운드 앱 감지
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
# 앱 라벨
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
# 스크린샷
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
# 에뮬레이터 윈도우 탐지
# ---------------------------------------------------------------------------
def _find_emulator_hwnd() -> Optional[int]:
    """에뮬레이터 렌더링 윈도우 핸들 반환 (BlueStacks, LDPlayer, Nox, MEmu 등)."""
    user32 = ctypes.windll.user32
    # 에뮬레이터 윈도우 클래스/타이틀 패턴
    _EMU_PATTERNS = [
        # BlueStacks 5
        ("HwndWrapper[Bluestacks_nxt_*", None),
        (None, "BlueStacks App Player"),
        (None, "BlueStacks"),
        # LDPlayer
        (None, "LDPlayer"),
        ("LDPlayerMainFrame", None),
        # Nox
        (None, "NoxPlayer"),
        ("Qt5QWindowIcon", "NoxPlayer"),
        # MEmu
        (None, "MEmu"),
    ]
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
        for pat_cls, pat_title in _EMU_PATTERNS:
            cls_ok = pat_cls is None or cls.startswith(pat_cls.rstrip("*"))
            title_ok = pat_title is None or pat_title.lower() in title.lower()
            if cls_ok and title_ok:
                found.append(hwnd)
                return True
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
    user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
    return found[0] if found else None


def _get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """윈도우의 (left, top, right, bottom) 스크린 좌표 반환."""

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                     ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    rect = RECT()
    if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return (rect.left, rect.top, rect.right, rect.bottom)
    return None


# ---------------------------------------------------------------------------
# 탭 모니터 (Windows 저수준 마우스 훅)
# ---------------------------------------------------------------------------
class TapMonitor:
    """Windows WH_MOUSE_LL 훅으로 에뮬레이터 윈도우 위 클릭 감지."""

    WH_MOUSE_LL = 14
    WM_LBUTTONDOWN = 0x0201

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._tap_events: list = []
        self._lock = threading.Lock()
        self._hook = None
        self._emu_hwnd: Optional[int] = None
        self._emu_rect: Optional[Tuple[int, int, int, int]] = None
        self._rect_update_time = 0.0

    def start(self):
        self._emu_hwnd = _find_emulator_hwnd()
        if self._emu_hwnd:
            self._emu_rect = _get_window_rect(self._emu_hwnd)
        self._running = True
        self._thread = threading.Thread(target=self._hook_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._hook:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            except Exception:
                pass
            self._hook = None

    def pop_taps(self) -> list:
        with self._lock:
            taps = self._tap_events[:]
            self._tap_events.clear()
        return taps

    def get_emu_info(self) -> str:
        if self._emu_hwnd:
            buf = ctypes.create_unicode_buffer(256)
            ctypes.windll.user32.GetWindowTextW(self._emu_hwnd, buf, 256)
            return buf.value or "Emulator"
        return "Not found"

    def _update_rect(self):
        """에뮬레이터 윈도우 좌표 갱신 (1초마다)."""
        now = time.time()
        if now - self._rect_update_time < 1.0:
            return
        self._rect_update_time = now
        if not self._emu_hwnd or not ctypes.windll.user32.IsWindow(self._emu_hwnd):
            self._emu_hwnd = _find_emulator_hwnd()
        if self._emu_hwnd:
            self._emu_rect = _get_window_rect(self._emu_hwnd)

    def _is_in_emulator(self, x: int, y: int) -> bool:
        self._update_rect()
        if not self._emu_rect:
            return False
        l, t, r, b = self._emu_rect
        return l <= x <= r and t <= y <= b

    def _hook_loop(self):
        """메시지 루프 + 저수준 마우스 훅."""
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
            if nCode >= 0 and wParam == self.WM_LBUTTONDOWN:
                ms = lParam.contents
                sx, sy = ms.pt.x, ms.pt.y
                if self._is_in_emulator(sx, sy):
                    # 에뮬레이터 윈도우 내 상대 좌표 계산
                    l, t, _, _ = self._emu_rect
                    rx, ry = sx - l, sy - t
                    now = time.time()
                    with self._lock:
                        self._tap_events.append((now, rx, ry))
            return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

        # prevent GC of callback
        self._hook_proc = HOOKPROC(low_level_mouse_proc)
        self._hook = user32.SetWindowsHookExW(
            self.WH_MOUSE_LL, self._hook_proc, None, 0)

        msg = ctypes.wintypes.MSG()
        while self._running:
            # PeekMessage를 사용하여 훅 메시지 처리 (블로킹 방지)
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            else:
                time.sleep(0.01)

        if self._hook:
            user32.UnhookWindowsHookEx(self._hook)
            self._hook = None


# ---------------------------------------------------------------------------
# GUI 앱
# ---------------------------------------------------------------------------
class ClickCaptureApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Click Capture — Emulator Auto Screenshot")
        self.root.geometry("680x520")
        self.root.resizable(True, True)

        self.cfg = load_config()
        self._running = False
        self._monitor: Optional[TapMonitor] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._current_app = ""
        self._counters: dict = {}
        self._last_capture_time = 0.0
        self._total = 0

        self._build_ui()
        self._apply_config()

    # ---- UI 구성 ----
    def _build_ui(self):
        # 설정 프레임
        settings = ttk.LabelFrame(self.root, text="설정", padding=8)
        settings.pack(fill="x", padx=10, pady=(10, 5))

        # ADB 경로
        row0 = ttk.Frame(settings)
        row0.pack(fill="x", pady=2)
        ttk.Label(row0, text="ADB 경로:", width=12).pack(side="left")
        self.var_adb = tk.StringVar()
        ttk.Entry(row0, textvariable=self.var_adb, width=50).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(row0, text="찾기", width=5, command=self._browse_adb).pack(side="left")

        # Device (auto-detect dropdown)
        row1 = ttk.Frame(settings)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="디바이스:", width=12).pack(side="left")
        self.var_serial = tk.StringVar()
        self.cmb_serial = ttk.Combobox(row1, textvariable=self.var_serial, width=30)
        self.cmb_serial.pack(side="left")
        ttk.Button(row1, text="검색", width=5, command=self._refresh_devices).pack(side="left", padx=(5, 0))

        # 쿨다운
        ttk.Label(row1, text="  쿨다운(초):", width=10).pack(side="left")
        self.var_cooldown = tk.StringVar()
        ttk.Entry(row1, textvariable=self.var_cooldown, width=8).pack(side="left")

        # 저장 폴더
        row2 = ttk.Frame(settings)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="저장 폴더:", width=12).pack(side="left")
        self.var_output = tk.StringVar()
        ttk.Entry(row2, textvariable=self.var_output, width=50).pack(side="left", fill="x", expand=True, padx=(0, 5))
        ttk.Button(row2, text="찾기", width=5, command=self._browse_output).pack(side="left")

        # 상태 바
        status_frame = ttk.Frame(self.root)
        status_frame.pack(fill="x", padx=10, pady=5)

        self.var_status = tk.StringVar(value="대기 중")
        self.lbl_status = ttk.Label(status_frame, textvariable=self.var_status,
                                     font=("맑은 고딕", 10, "bold"))
        self.lbl_status.pack(side="left")

        self.var_app = tk.StringVar(value="")
        ttk.Label(status_frame, textvariable=self.var_app,
                  foreground="gray").pack(side="left", padx=(15, 0))

        self.var_count = tk.StringVar(value="캡처: 0장")
        ttk.Label(status_frame, textvariable=self.var_count).pack(side="right")

        # 버튼
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.btn_start = ttk.Button(btn_frame, text="▶  시작", command=self._on_start)
        self.btn_start.pack(side="left", padx=(0, 5))

        self.btn_stop = ttk.Button(btn_frame, text="■  정지", command=self._on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(0, 5))

        ttk.Button(btn_frame, text="폴더 열기", command=self._open_folder).pack(side="left", padx=(0, 5))

        ttk.Button(btn_frame, text="ADB 연결 테스트", command=self._test_adb).pack(side="right")

        # 로그
        log_frame = ttk.LabelFrame(self.root, text="로그", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        self.log_text = scrolledtext.ScrolledText(
            log_frame, height=12, font=("Consolas", 9),
            state="disabled", wrap="word"
        )
        self.log_text.pack(fill="both", expand=True)

        # 윈도우 닫기 이벤트
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_config(self):
        self.var_adb.set(self.cfg.get("adb_path", ""))
        self.var_serial.set(self.cfg.get("serial", "auto"))
        self.var_output.set(self.cfg.get("output_folder", ""))
        self.var_cooldown.set(str(self.cfg.get("cooldown", 0.3)))
        # 시작 시 디바이스 자동 검색
        self.root.after(500, self._refresh_devices)

    def _save_current_config(self):
        self.cfg["adb_path"] = self.var_adb.get()
        self.cfg["serial"] = self.var_serial.get()
        self.cfg["output_folder"] = self.var_output.get()
        try:
            self.cfg["cooldown"] = float(self.var_cooldown.get())
        except ValueError:
            self.cfg["cooldown"] = 0.3
        save_config(self.cfg)

    # ---- 로그 ----
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", f"[{ts}] {msg}\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _append)

    # ---- 디바이스 탐지 ----
    def _refresh_devices(self):
        """ADB로 연결된 디바이스 목록을 검색하여 드롭다운 갱신."""
        adb_path = self.var_adb.get()
        if not Path(adb_path).exists():
            messagebox.showerror("오류", f"ADB 파일을 찾을 수 없습니다:\n{adb_path}")
            return
        devices = detect_devices(adb_path)
        if devices:
            serials = [d[0] for d in devices]
            self.cmb_serial["values"] = serials
            if self.var_serial.get() not in serials:
                self.var_serial.set(serials[0])
            self._log(f"디바이스 {len(devices)}개 발견: {', '.join(serials)}")
        else:
            self.cmb_serial["values"] = []
            self._log("연결된 디바이스가 없습니다. 에뮬레이터를 실행하세요.")

    def _resolve_serial(self) -> bool:
        """serial이 'auto'이거나 비어있으면 자동 탐지. 성공 시 True."""
        global _ADB, _SERIAL
        _ADB = self.var_adb.get()

        if not Path(_ADB).exists():
            messagebox.showerror("오류", f"ADB 파일을 찾을 수 없습니다:\n{_ADB}")
            return False

        serial = self.var_serial.get().strip()
        if serial and serial.lower() != "auto":
            _SERIAL = serial
            return True

        # 자동 탐지
        devices = detect_devices(_ADB)
        if not devices:
            messagebox.showerror("오류",
                "연결된 디바이스가 없습니다.\n\n"
                "에뮬레이터(BlueStacks, LDPlayer 등)가 실행 중인지 확인하세요.")
            return False

        _SERIAL = devices[0][0]
        self.var_serial.set(_SERIAL)
        self._log(f"디바이스 자동 감지: {_SERIAL}")
        if len(devices) > 1:
            others = ", ".join(d[0] for d in devices[1:])
            self._log(f"  다른 디바이스도 발견: {others}")
        return True

    # ---- 버튼 핸들러 ----
    def _browse_adb(self):
        path = filedialog.askopenfilename(
            title="ADB 실행 파일 선택",
            filetypes=[("Executable", "*.exe"), ("All", "*.*")],
        )
        if path:
            self.var_adb.set(path)

    def _browse_output(self):
        folder = filedialog.askdirectory(title="스크린샷 저장 폴더 선택")
        if folder:
            self.var_output.set(folder)

    def _open_folder(self):
        folder = self.var_output.get()
        if folder and Path(folder).exists():
            os.startfile(folder)
        else:
            messagebox.showinfo("알림", "폴더가 아직 생성되지 않았습니다.")

    def _test_adb(self):
        if not self._resolve_serial():
            return

        try:
            app = get_foreground_app()
            messagebox.showinfo("성공",
                f"ADB 연결 성공!\n디바이스: {_SERIAL}\n현재 앱: {app}")
        except Exception as e:
            messagebox.showerror("오류", f"ADB 연결 실패:\n{e}")

    def _on_start(self):
        if not self._resolve_serial():
            return

        output_folder = self.var_output.get()
        if not output_folder:
            messagebox.showerror("오류", "저장 폴더를 선택하세요.")
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
        self.var_status.set("실행 중...")

        self._monitor = TapMonitor()
        self._monitor.start()
        emu_info = self._monitor.get_emu_info()
        self._log(f"에뮬레이터 윈도우: {emu_info}")

        self._current_app = get_foreground_app()
        app_label = get_app_label(self._current_app)
        self.var_app.set(f"현재 앱: {app_label} ({self._current_app})")
        self._log(f"캡처 시작 — 저장: {output_folder}")
        self._log(f"현재 앱: {self._current_app} ({app_label})")
        self._log(f"클릭 감지 방식: Windows 마우스 훅 (에뮬레이터 윈도우 영역)")

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()

        # UI 업데이트 타이머
        self._poll_ui()

    def _on_stop(self):
        self._running = False
        if self._monitor:
            self._monitor.stop()
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.var_status.set("정지됨")
        self._log(f"캡처 정지 — 총 {self._total}장")
        self._log_summary()

    def _on_close(self):
        self._running = False
        if self._monitor:
            self._monitor.stop()
        self._save_current_config()
        self.root.destroy()

    # ---- 캡처 루프 (백그라운드 스레드) ----
    def _capture_loop(self):
        app_check_interval = 3.0
        last_app_check = 0.0

        while self._running:
            now = time.time()

            # 앱 변경 감지
            if now - last_app_check > app_check_interval:
                try:
                    new_app = get_foreground_app()
                    if new_app != self._current_app:
                        old_label = get_app_label(self._current_app)
                        new_label = get_app_label(new_app)
                        self._current_app = new_app
                        self._log(f"앱 변경: {old_label} → {new_label} ({new_app})")
                        self.root.after(0, lambda: self.var_app.set(
                            f"현재 앱: {new_label} ({new_app})"))
                except Exception:
                    pass
                last_app_check = now

            # 탭 이벤트 처리
            if self._monitor:
                taps = self._monitor.pop_taps()
                for tap_time, x, y in taps:
                    if tap_time - self._last_capture_time < self._cooldown:
                        continue
                    self._last_capture_time = tap_time
                    self._take_screenshot(x, y)

            time.sleep(0.05)

    def _take_screenshot(self, x: int, y: int):
        app_label = get_app_label(self._current_app)
        app_dir = self._output_root / app_label
        app_dir.mkdir(parents=True, exist_ok=True)

        count = self._counters.get(app_label, 0) + 1
        self._counters[app_label] = count
        self._total += 1

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"click_{ts}_{count:04d}.png"
        save_path = app_dir / filename

        ok = screenshot_adb(save_path)
        if ok:
            self._log(f"[{app_label}] #{count} — tap({x},{y}) → {filename}")
            self._log_event(app_dir, x, y, filename)
        else:
            self._log(f"[{app_label}] #{count} FAILED — tap({x},{y})")

    def _log_event(self, app_dir: Path, x: int, y: int, filename: str):
        log_path = app_dir / "session_log.jsonl"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "tap_x": x,
            "tap_y": y,
            "file": filename,
            "app": self._current_app,
        }
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _log_summary(self):
        if not self._counters:
            return
        self._log("--- 요약 ---")
        for app_label, count in sorted(self._counters.items()):
            self._log(f"  {app_label}: {count}장")
        self._log(f"  합계: {self._total}장")

    # ---- UI 폴링 (메인 스레드) ----
    def _poll_ui(self):
        if not self._running:
            return
        self.var_count.set(f"캡처: {self._total}장")
        self.root.after(500, self._poll_ui)


# ---------------------------------------------------------------------------
# 엔트리포인트
# ---------------------------------------------------------------------------
def main():
    root = tk.Tk()

    # 고DPI 지원
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    app = ClickCaptureApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
