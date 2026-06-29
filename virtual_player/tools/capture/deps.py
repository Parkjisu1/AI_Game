"""
Dependency Auto-Installer
==========================
첫 실행 시 누락된 의존성(Tesseract, ADB)을 자동 설치.
EXE 옆 deps/ 폴더에 설치 → 시스템 오염 없음, 이식 가능.

설치 대상:
  - Tesseract-OCR 5.5 (Idle 모드 OCR용) ~75MB
  - ADB platform-tools (에뮬레이터 ADB 없을 때 폴백) ~10MB
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

def _app_root() -> Path:
    """EXE 위치 또는 소스 디렉토리."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _deps_dir() -> Path:
    return _app_root() / "deps"


def _deps_config_path() -> Path:
    return _app_root() / "deps_config.json"


def _load_deps_config() -> dict:
    p = _deps_config_path()
    if p.exists():
        try:
            with open(p, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_deps_config(cfg: dict):
    try:
        with open(_deps_config_path(), "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Dependency Definitions
# ─────────────────────────────────────────────────────────────────────────────

TESSERACT_URL = "https://github.com/UB-Mannheim/tesseract/releases/download/v5.5.0/tesseract-ocr-w64-setup-5.5.0.20241111.exe"
TESSERACT_SIZE_MB = 75

ADB_URL = "https://dl.google.com/android/repository/platform-tools-latest-windows.zip"
ADB_SIZE_MB = 12


def _find_tesseract() -> Optional[str]:
    """시스템에서 Tesseract 찾기."""
    # 1. deps 폴더
    local = _deps_dir() / "tesseract" / "tesseract.exe"
    if local.exists():
        return str(local)

    # 2. 일반 설치 경로
    for path in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]:
        if Path(path).exists():
            return path

    # 3. PATH
    try:
        result = subprocess.run(
            ["where", "tesseract"], capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        if result.returncode == 0:
            p = result.stdout.decode().strip().splitlines()[0].strip()
            if Path(p).exists():
                return p
    except Exception:
        pass

    return None


def _find_adb() -> Optional[str]:
    """시스템에서 ADB 찾기."""
    # 1. deps 폴더
    local = _deps_dir() / "platform-tools" / "adb.exe"
    if local.exists():
        return str(local)

    # 2. 에뮬레이터 ADB (base.py의 EmulatorRegistry 로직)
    for path in [
        r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
        r"C:\Program Files (x86)\BlueStacks_nxt\HD-Adb.exe",
        r"C:\LDPlayer\LDPlayer9\adb.exe",
    ]:
        if Path(path).exists():
            return path

    # 3. PATH
    try:
        result = subprocess.run(
            ["where", "adb"], capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0)
        if result.returncode == 0:
            p = result.stdout.decode().strip().splitlines()[0].strip()
            if Path(p).exists():
                return p
    except Exception:
        pass

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Download + Install Logic
# ─────────────────────────────────────────────────────────────────────────────

def _download_with_progress(url: str, dest: Path,
                            progress_cb: Callable[[int, int], None]) -> bool:
    """URL 다운로드 + 진행률 콜백."""
    try:
        req = Request(url, headers={"User-Agent": "GenreCapture/1.0"})
        resp = urlopen(req, timeout=60)
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 64 * 1024

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                progress_cb(downloaded, total)
        return True
    except Exception:
        if dest.exists():
            dest.unlink()
        return False


def _install_tesseract(progress_cb: Callable[[str, int, int], None]) -> Optional[str]:
    """
    Tesseract 다운로드 + 설치.

    Returns: tesseract.exe 경로 또는 None
    """
    deps = _deps_dir()
    deps.mkdir(parents=True, exist_ok=True)
    installer_path = deps / "tesseract_installer.exe"
    install_dir = deps / "tesseract"

    # 이미 설치됨?
    exe = install_dir / "tesseract.exe"
    if exe.exists():
        return str(exe)

    # 다운로드
    progress_cb("Tesseract OCR 다운로드 중...", 0, 0)

    def on_progress(downloaded, total):
        progress_cb("Tesseract OCR 다운로드 중...", downloaded, total)

    if not _download_with_progress(TESSERACT_URL, installer_path, on_progress):
        progress_cb("다운로드 실패", 0, 0)
        return None

    # 사일런트 설치 (지정 경로)
    progress_cb("Tesseract OCR 설치 중...", 0, 0)
    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [str(installer_path), "/S", f"/D={install_dir}"],
            capture_output=True, timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        # 설치 후 확인
        if exe.exists():
            # 설치 파일 정리
            try:
                installer_path.unlink()
            except Exception:
                pass
            progress_cb("Tesseract OCR 설치 완료", 1, 1)
            return str(exe)
        else:
            progress_cb("설치 실패 — tesseract.exe를 찾을 수 없습니다", 0, 0)
            return None
    except Exception as e:
        progress_cb(f"설치 실패: {e}", 0, 0)
        return None


def _install_adb(progress_cb: Callable[[str, int, int], None]) -> Optional[str]:
    """
    ADB platform-tools 다운로드 + 설치.

    Returns: adb.exe 경로 또는 None
    """
    deps = _deps_dir()
    deps.mkdir(parents=True, exist_ok=True)
    zip_path = deps / "platform-tools.zip"
    install_dir = deps / "platform-tools"

    exe = install_dir / "adb.exe"
    if exe.exists():
        return str(exe)

    progress_cb("ADB Platform Tools 다운로드 중...", 0, 0)

    def on_progress(downloaded, total):
        progress_cb("ADB Platform Tools 다운로드 중...", downloaded, total)

    if not _download_with_progress(ADB_URL, zip_path, on_progress):
        progress_cb("다운로드 실패", 0, 0)
        return None

    # ZIP 압축 해제
    progress_cb("ADB 압축 해제 중...", 0, 0)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(deps)
        if exe.exists():
            try:
                zip_path.unlink()
            except Exception:
                pass
            progress_cb("ADB 설치 완료", 1, 1)
            return str(exe)
        else:
            progress_cb("설치 실패", 0, 0)
            return None
    except Exception as e:
        progress_cb(f"압축 해제 실패: {e}", 0, 0)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Dependency Status
# ─────────────────────────────────────────────────────────────────────────────

class DepStatus:
    def __init__(self):
        self.tesseract_path = _find_tesseract()
        self.adb_path = _find_adb()

    @property
    def tesseract_ok(self) -> bool:
        return self.tesseract_path is not None

    @property
    def adb_ok(self) -> bool:
        return self.adb_path is not None

    @property
    def all_ok(self) -> bool:
        return self.tesseract_ok and self.adb_ok

    @property
    def missing(self) -> List[str]:
        m = []
        if not self.tesseract_ok:
            m.append("tesseract")
        if not self.adb_ok:
            m.append("adb")
        return m

    def apply_to_env(self):
        """발견된 경로를 pytesseract에 설정 + PATH에 추가."""
        if self.tesseract_path:
            try:
                import pytesseract
                pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
            except ImportError:
                pass

            tess_dir = str(Path(self.tesseract_path).parent)
            if tess_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = tess_dir + os.pathsep + os.environ.get("PATH", "")

        if self.adb_path:
            adb_dir = str(Path(self.adb_path).parent)
            if adb_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")


# ═══════════════════════════════════════════════════════════════════════════════
# Setup Dialog (tkinter)
# ═══════════════════════════════════════════════════════════════════════════════

class SetupDialog:
    """첫 실행 시 의존성 자동 설치 다이얼로그."""

    BG = "#0d0d0d"
    CARD = "#161618"
    BORDER = "#2a2a2e"
    ACCENT = "#8b5cf6"
    TEXT = "#e4e4e7"
    TEXT_DIM = "#8b8b94"
    SUCCESS = "#34d399"
    ERROR = "#f87171"
    WARNING = "#fbbf24"

    def __init__(self, parent: Optional[tk.Tk], status: DepStatus):
        self.status = status
        self.result_status: Optional[DepStatus] = None
        self._cancelled = False

        if parent:
            self.win = tk.Toplevel(parent)
        else:
            self.win = tk.Tk()

        self.win.title("Genre Capture — Setup")
        self.win.geometry("520x400")
        self.win.resizable(False, False)
        self.win.configure(bg=self.BG)

        self._build()

    def _build(self):
        # Header
        header = tk.Frame(self.win, bg=self.CARD, height=50)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Dependencies Setup",
                 font=("Segoe UI", 12, "bold"), fg=self.TEXT, bg=self.CARD
                 ).pack(side="left", padx=16)

        tk.Frame(self.win, bg=self.BORDER, height=1).pack(fill="x")

        body = tk.Frame(self.win, bg=self.BG)
        body.pack(fill="both", expand=True, padx=16, pady=12)

        # Status table
        tk.Label(body, text="Dependency Check",
                 font=("Segoe UI", 10, "bold"), fg=self.TEXT, bg=self.BG
                 ).pack(anchor="w")

        status_frame = tk.Frame(body, bg=self.CARD, highlightbackground=self.BORDER, highlightthickness=1)
        status_frame.pack(fill="x", pady=(8, 0))
        sf = tk.Frame(status_frame, bg=self.CARD)
        sf.pack(fill="x", padx=12, pady=10)

        items = [
            ("Tesseract OCR", self.status.tesseract_ok, self.status.tesseract_path,
             "Idle 모드 숫자 인식용", f"~{TESSERACT_SIZE_MB}MB"),
            ("ADB (Android Debug Bridge)", self.status.adb_ok, self.status.adb_path,
             "에뮬레이터 스크린샷/제어", f"~{ADB_SIZE_MB}MB"),
        ]

        self._status_labels = {}
        for i, (name, ok, path, desc, size) in enumerate(items):
            row = tk.Frame(sf, bg=self.CARD)
            row.pack(fill="x", pady=(0, 6) if i < len(items) - 1 else 0)

            icon = "OK" if ok else "MISSING"
            color = self.SUCCESS if ok else self.WARNING
            tk.Label(row, text=icon, font=("Segoe UI", 9, "bold"),
                     fg=color, bg=self.CARD, width=8).pack(side="left")
            tk.Label(row, text=name, font=("Segoe UI", 9, "bold"),
                     fg=self.TEXT, bg=self.CARD).pack(side="left")
            tk.Label(row, text=f"({desc})", font=("Segoe UI", 8),
                     fg=self.TEXT_DIM, bg=self.CARD).pack(side="left", padx=(6, 0))

            if ok:
                short = str(path)[-50:] if path and len(str(path)) > 50 else (path or "")
                tk.Label(row, text=short, font=("Segoe UI", 7),
                         fg=self.TEXT_DIM, bg=self.CARD).pack(side="right")
            else:
                tk.Label(row, text=size, font=("Segoe UI", 8),
                         fg=self.WARNING, bg=self.CARD).pack(side="right")

            lbl_status = tk.Label(row, text="", font=("Segoe UI", 8),
                                  fg=self.TEXT_DIM, bg=self.CARD)
            lbl_status.pack(side="right", padx=(0, 8))
            self._status_labels[name] = lbl_status

        # Progress
        self.lbl_progress = tk.Label(body, text="", font=("Segoe UI", 9),
                                     fg=self.TEXT_DIM, bg=self.BG, anchor="w")
        self.lbl_progress.pack(fill="x", pady=(12, 0))

        self.progress = ttk.Progressbar(body, mode="determinate", length=480)
        self.progress.pack(fill="x", pady=(4, 0))

        self.lbl_detail = tk.Label(body, text="", font=("Segoe UI", 8),
                                   fg=self.TEXT_DIM, bg=self.BG, anchor="w")
        self.lbl_detail.pack(fill="x", pady=(2, 0))

        # Buttons
        btn_frame = tk.Frame(body, bg=self.BG)
        btn_frame.pack(fill="x", pady=(16, 0))

        if not self.status.all_ok:
            self.btn_install = tk.Button(
                btn_frame, text="Install Missing",
                font=("Segoe UI", 10, "bold"), fg="#ffffff", bg=self.ACCENT,
                activebackground="#a78bfa", padx=20, pady=6, relief="flat",
                command=self._on_install)
            self.btn_install.pack(side="left")

        self.btn_skip = tk.Button(
            btn_frame, text="Skip" if not self.status.all_ok else "Continue",
            font=("Segoe UI", 9), fg=self.TEXT_DIM, bg=self.CARD,
            activebackground=self.BORDER, padx=16, pady=6, relief="flat",
            command=self._on_skip)
        self.btn_skip.pack(side="left", padx=(8, 0))

        if self.status.all_ok:
            tk.Label(body, text="All dependencies found. Ready to go!",
                     font=("Segoe UI", 9, "bold"), fg=self.SUCCESS, bg=self.BG
                     ).pack(pady=(8, 0))

    def _on_install(self):
        self.btn_install.config(state="disabled", text="Installing...")
        self.btn_skip.config(state="disabled")
        threading.Thread(target=self._install_all, daemon=True).start()

    def _on_skip(self):
        self.result_status = DepStatus()
        self.result_status.apply_to_env()
        self.win.destroy()

    def _update_progress(self, text: str, downloaded: int, total: int):
        def _do():
            self.lbl_progress.config(text=text)
            if total > 0:
                pct = min(100, int(downloaded / total * 100))
                self.progress["value"] = pct
                mb_done = downloaded / 1024 / 1024
                mb_total = total / 1024 / 1024
                self.lbl_detail.config(text=f"{mb_done:.1f} / {mb_total:.1f} MB ({pct}%)")
            else:
                self.progress["value"] = 0
                self.lbl_detail.config(text="")
        self.win.after(0, _do)

    def _install_all(self):
        missing = self.status.missing

        if "tesseract" in missing:
            result = _install_tesseract(self._update_progress)
            ok = result is not None
            self.win.after(0, lambda: self._status_labels["Tesseract OCR"].config(
                text="OK" if ok else "FAILED",
                fg=self.SUCCESS if ok else self.ERROR))

        if "adb" in missing:
            result = _install_adb(self._update_progress)
            ok = result is not None
            self.win.after(0, lambda: self._status_labels["ADB (Android Debug Bridge)"].config(
                text="OK" if ok else "FAILED",
                fg=self.SUCCESS if ok else self.ERROR))

        # 재확인
        new_status = DepStatus()
        new_status.apply_to_env()

        # 경로 기록
        cfg = _load_deps_config()
        if new_status.tesseract_path:
            cfg["tesseract_path"] = new_status.tesseract_path
        if new_status.adb_path:
            cfg["adb_path"] = new_status.adb_path
        cfg["setup_done"] = True
        _save_deps_config(cfg)

        self.result_status = new_status

        def _done():
            self._update_progress("설치 완료!", 1, 1)
            self.btn_skip.config(state="normal", text="Continue")
            if hasattr(self, 'btn_install'):
                self.btn_install.config(state="disabled", text="Done")
        self.win.after(0, _done)

    def run(self) -> DepStatus:
        """다이얼로그 실행, 완료 후 DepStatus 반환."""
        self.win.grab_set()
        self.win.wait_window()
        return self.result_status or DepStatus()


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════

def ensure_dependencies(parent: Optional[tk.Tk] = None) -> DepStatus:
    """
    의존성 확인 + 누락 시 설치 다이얼로그.

    - 이미 설치 완료된 적 있으면 (deps_config.json 존재) 빠르게 통과
    - 누락 있으면 SetupDialog 표시

    Returns: DepStatus (경로 정보 포함)
    """
    # 이전 설정 로드 → PATH에 추가
    cfg = _load_deps_config()
    if cfg.get("tesseract_path"):
        tess_dir = str(Path(cfg["tesseract_path"]).parent)
        os.environ["PATH"] = tess_dir + os.pathsep + os.environ.get("PATH", "")
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_path"]
        except ImportError:
            pass

    if cfg.get("adb_path"):
        adb_dir = str(Path(cfg["adb_path"]).parent)
        os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")

    status = DepStatus()

    if status.all_ok:
        status.apply_to_env()
        return status

    # 누락 있으면 다이얼로그
    dialog = SetupDialog(parent, status)
    result = dialog.run()
    return result
