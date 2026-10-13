"""
Dependency Auto-Installer
==========================
첫 실행 시 누락된 의존성(Tesseract, ADB)을 자동 설치.
설치 위치: %LOCALAPPDATA%\\ClickCapture\\deps (유저 로컬 → 관리자 불필요, 한글/공백 경로 안전)
폴백: EXE 옆 deps/ 폴더 (쓰기 권한 있을 때만)

설치 대상:
  - Tesseract-OCR 5.5 (Idle 모드 OCR용) ~75MB
  - ADB platform-tools (에뮬레이터 ADB 없을 때 폴백) ~10MB
"""

import io
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

try:
    import tkinter as tk
    from tkinter import ttk
    _HAS_TK = True
except Exception:
    _HAS_TK = False

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

def _app_root() -> Path:
    """EXE 위치 또는 소스 디렉토리."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def _user_local_root() -> Path:
    """유저 로컬 설치 루트 (%LOCALAPPDATA%\\ClickCapture)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "ClickCapture"


def _deps_dir() -> Path:
    """
    의존성 설치 폴더.
    1순위: %LOCALAPPDATA%\\ClickCapture\\deps (유저 로컬, 관리자 불필요)
    2순위: EXE 옆 deps/ (레거시 호환 — 이미 있으면 그대로 사용)
    """
    legacy = _app_root() / "deps"
    if legacy.exists() and any(legacy.iterdir()):
        return legacy
    return _user_local_root() / "deps"


def _log_path() -> Path:
    return _user_local_root() / "deps_install.log"


def _log(msg: str):
    """설치 로그를 파일에 기록 (디버깅용)."""
    try:
        p = _log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass


def _deps_config_path() -> Path:
    return _user_local_root() / "deps_config.json"


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

def _build_ssl_context() -> ssl.SSLContext:
    """
    SSL 컨텍스트 생성 (certifi → 시스템 인증서 → 검증 없음 순서 폴백).
    오래된 Windows에서 GitHub/Google HTTPS 실패 방지.
    """
    # 1. certifi (PyInstaller 번들에 포함)
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass

    # 2. 시스템 기본
    try:
        ctx = ssl.create_default_context()
        return ctx
    except Exception:
        pass

    # 3. 최후의 수단: 검증 비활성화 (보안 경고)
    _log("WARNING: SSL 검증 비활성화 — 시스템 인증서 로드 실패")
    ctx = ssl._create_unverified_context()
    return ctx


def _download_with_progress(url: str, dest: Path,
                            progress_cb: Callable[[int, int], None],
                            max_retries: int = 3) -> Tuple[bool, str]:
    """
    URL 다운로드 + 진행률 콜백 + 재시도.

    Returns: (성공 여부, 에러 메시지)
    """
    last_err = ""
    ctx = _build_ssl_context()

    for attempt in range(1, max_retries + 1):
        try:
            _log(f"Download attempt {attempt}: {url}")
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0) ClickCapture/1.0",
                "Accept": "*/*",
            })
            resp = urlopen(req, timeout=60, context=ctx)
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

            if total > 0 and downloaded < total:
                raise IOError(f"불완전 다운로드 ({downloaded}/{total} bytes)")

            _log(f"Download OK: {dest} ({downloaded} bytes)")
            return True, ""
        except HTTPError as e:
            last_err = f"HTTP {e.code}: {e.reason}"
            _log(f"HTTPError: {last_err}")
        except URLError as e:
            last_err = f"네트워크 오류: {e.reason}"
            _log(f"URLError: {last_err}")
        except ssl.SSLError as e:
            last_err = f"SSL 오류: {e}"
            _log(f"SSLError: {last_err}")
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            _log(f"Exception: {last_err}\n{traceback.format_exc()}")

        if dest.exists():
            try: dest.unlink()
            except Exception: pass

        if attempt < max_retries:
            time.sleep(2 * attempt)  # exponential backoff

    return False, last_err or "알 수 없는 오류"


def _install_tesseract(progress_cb: Callable[[str, int, int], None]) -> Tuple[Optional[str], str]:
    """
    Tesseract 다운로드 + 설치 (유저 로컬, 관리자 불필요).

    Returns: (tesseract.exe 경로 또는 None, 에러 메시지)
    """
    deps = _deps_dir()
    try:
        deps.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        return None, f"설치 폴더 생성 실패: {e}"

    installer_path = deps / "tesseract_installer.exe"
    install_dir = deps / "tesseract"

    # 이미 설치됨?
    exe = install_dir / "tesseract.exe"
    if exe.exists():
        return str(exe), ""

    # 다운로드
    progress_cb("Tesseract OCR 다운로드 중...", 0, 0)
    def on_progress(downloaded, total):
        progress_cb("Tesseract OCR 다운로드 중...", downloaded, total)

    ok, err = _download_with_progress(TESSERACT_URL, installer_path, on_progress)
    if not ok:
        progress_cb(f"다운로드 실패: {err}", 0, 0)
        return None, err

    # 사일런트 설치 (NSIS /D= 는 마지막 인자여야 하며 절대경로 필수)
    progress_cb("Tesseract OCR 설치 중...", 0, 0)
    try:
        install_dir.mkdir(parents=True, exist_ok=True)
        abs_dir = str(install_dir.resolve())
        _log(f"Tesseract install: /S /D={abs_dir}")

        result = subprocess.run(
            [str(installer_path), "/S", f"/D={abs_dir}"],
            capture_output=True, timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        _log(f"Tesseract installer exit={result.returncode}")

        if exe.exists():
            try: installer_path.unlink()
            except Exception: pass
            progress_cb("Tesseract OCR 설치 완료", 1, 1)
            return str(exe), ""

        # 설치 실패 → 폴백: 7zip-sfx 형태로 직접 추출 시도
        err_msg = f"설치 실패 (exit={result.returncode}). tesseract.exe 미생성. 경로={abs_dir}"
        _log(err_msg)
        progress_cb("설치 실패 — 로그 확인: " + str(_log_path()), 0, 0)
        return None, err_msg
    except subprocess.TimeoutExpired:
        return None, "설치 타임아웃 (180초 초과)"
    except Exception as e:
        _log(f"Tesseract install exception: {traceback.format_exc()}")
        return None, f"설치 예외: {e}"


def _install_adb(progress_cb: Callable[[str, int, int], None]) -> Tuple[Optional[str], str]:
    """
    ADB platform-tools 다운로드 + 설치.

    Returns: (adb.exe 경로 또는 None, 에러 메시지)
    """
    deps = _deps_dir()
    try:
        deps.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        return None, f"설치 폴더 생성 실패: {e}"

    zip_path = deps / "platform-tools.zip"
    install_dir = deps / "platform-tools"

    exe = install_dir / "adb.exe"
    if exe.exists():
        return str(exe), ""

    progress_cb("ADB Platform Tools 다운로드 중...", 0, 0)
    def on_progress(downloaded, total):
        progress_cb("ADB Platform Tools 다운로드 중...", downloaded, total)

    ok, err = _download_with_progress(ADB_URL, zip_path, on_progress)
    if not ok:
        progress_cb(f"다운로드 실패: {err}", 0, 0)
        return None, err

    # ZIP 압축 해제
    progress_cb("ADB 압축 해제 중...", 0, 0)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(deps)
        if exe.exists():
            try: zip_path.unlink()
            except Exception: pass
            progress_cb("ADB 설치 완료", 1, 1)
            return str(exe), ""
        return None, "압축 해제 후 adb.exe 미발견"
    except Exception as e:
        _log(f"ADB unzip exception: {traceback.format_exc()}")
        return None, f"압축 해제 실패: {e}"


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

    def __init__(self, parent, status: DepStatus):
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
        errors = []

        if "tesseract" in missing:
            result, err = _install_tesseract(self._update_progress)
            ok = result is not None
            if not ok and err:
                errors.append(f"Tesseract: {err}")
            self.win.after(0, lambda: self._status_labels["Tesseract OCR"].config(
                text="OK" if ok else "FAILED",
                fg=self.SUCCESS if ok else self.ERROR))

        if "adb" in missing:
            result, err = _install_adb(self._update_progress)
            ok = result is not None
            if not ok and err:
                errors.append(f"ADB: {err}")
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
            if errors:
                msg = " | ".join(errors)[:200]
                self._update_progress(f"일부 실패: {msg}", 0, 0)
                self.lbl_detail.config(text=f"로그: {_log_path()}")
            else:
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

def ensure_dependencies(parent=None) -> DepStatus:
    """
    의존성 확인 + 누락 시 설치 다이얼로그.

    - 이미 설치 완료된 적 있으면 (deps_config.json 존재) 빠르게 통과
    - 누락 있으면 SetupDialog 표시 (tkinter 없으면 자동 skip)

    Returns: DepStatus (경로 정보 포함)
    """
    _log(f"ensure_dependencies start — frozen={getattr(sys, 'frozen', False)}, "
         f"app_root={_app_root()}, deps_dir={_deps_dir()}")

    # 이전 설정 로드 → PATH에 추가
    cfg = _load_deps_config()
    if cfg.get("tesseract_path") and Path(cfg["tesseract_path"]).exists():
        tess_dir = str(Path(cfg["tesseract_path"]).parent)
        os.environ["PATH"] = tess_dir + os.pathsep + os.environ.get("PATH", "")
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = cfg["tesseract_path"]
        except ImportError:
            pass

    if cfg.get("adb_path") and Path(cfg["adb_path"]).exists():
        adb_dir = str(Path(cfg["adb_path"]).parent)
        os.environ["PATH"] = adb_dir + os.pathsep + os.environ.get("PATH", "")

    status = DepStatus()
    _log(f"DepStatus: tesseract={status.tesseract_path}, adb={status.adb_path}")

    if status.all_ok:
        status.apply_to_env()
        return status

    # tkinter 없으면 다이얼로그 불가 → skip
    if not _HAS_TK:
        _log("tkinter 없음 — 의존성 다이얼로그 skip")
        status.apply_to_env()
        return status

    # 누락 있으면 다이얼로그
    try:
        dialog = SetupDialog(parent, status)
        result = dialog.run()
        return result
    except Exception as e:
        _log(f"SetupDialog 실패: {traceback.format_exc()}")
        status.apply_to_env()
        return status
