"""
ClickCapture exe 빌드 스크립트 (신버전 — capture/ 패키지)
===========================================================
장르별 캡처 파이프라인 (Puzzle/Idle/Action) + 자동 의존성 다운로드.

Python 3.10 권장 (Windows 7+ 호환).
실행: python build_capture.py

결과물: dist/ClickCapture.exe (단일 파일)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ENTRY = HERE / "capture" / "__main__.py"
ICON = HERE / "click_capture.ico"
DIST = HERE / "dist"
BUILD = HERE / "build"
SPEC = HERE / "ClickCapture.spec"


HIDDEN_IMPORTS = [
    # GUI
    "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.messagebox",
    # 이미지 처리
    "PIL", "PIL._tkinter_finder", "PIL.Image", "PIL.ImageTk",
    # Stdlib used dynamically
    "zipfile", "ssl", "ctypes", "ctypes.wintypes",
    "urllib", "urllib.request", "urllib.error",
    # SSL 인증서
    "certifi",
    # OCR (Idle 모드)
    "pytesseract",
    # 패키지 서브모듈
    "virtual_player.tools.capture.base",
    "virtual_player.tools.capture.deps",
    "virtual_player.tools.capture.theme",
    "virtual_player.tools.capture.puzzle_capture",
    "virtual_player.tools.capture.idle_capture",
    "virtual_player.tools.capture.action_capture",
    "virtual_player.tools.capture.launcher",
]


def main():
    # PyInstaller 확인
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("[*] PyInstaller 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 필수 패키지 확인
    for mod in ("certifi", "PIL", "pytesseract"):
        try:
            __import__(mod)
            print(f"[OK] {mod}")
        except ImportError:
            print(f"[*] {mod} 설치 중...")
            pkg = {"PIL": "Pillow"}.get(mod, mod)
            subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

    # 빌드 전 정리
    for p in (DIST, BUILD, SPEC):
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                try: p.unlink()
                except Exception: pass

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",                   # GUI 모드 — 콘솔 없음, 크래시는 crash.log로 기록
        "--name", "ClickCapture",
        "--clean",
        "--noconfirm",
        # certifi 인증서 번들 포함 (SSL 핸드셰이크 실패 방지)
        "--collect-data", "certifi",
        # PIL 전체 수집 (format 플러그인)
        "--collect-submodules", "PIL",
    ]

    # Hidden imports
    for mod in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", mod]

    # 제외할 대용량 모듈 (용량 절감)
    for mod in ("matplotlib", "numpy.distutils", "scipy", "pandas", "IPython",
                "notebook", "jupyter", "torch", "tensorflow"):
        cmd += ["--exclude-module", mod]

    # 아이콘
    if ICON.exists():
        cmd += ["--icon", str(ICON)]

    cmd.append(str(ENTRY))

    print("\n[*] 빌드 시작...")
    print("    Python:", sys.version.split()[0])
    print("    Entry :", ENTRY)
    print()

    # cwd = virtual_player 상위 (E:/AI) — 패키지 import 경로 해결
    project_root = HERE.parent.parent  # E:/AI
    result = subprocess.run(cmd, cwd=str(project_root))

    if result.returncode == 0:
        exe_path = project_root / "dist" / "ClickCapture.exe"
        if not exe_path.exists():
            # PyInstaller may put it in HERE/dist depending on cwd
            alt = HERE / "dist" / "ClickCapture.exe"
            if alt.exists():
                exe_path = alt
        print(f"\n{'='*60}")
        print(f"  빌드 성공!")
        print(f"  {exe_path}")
        if exe_path.exists():
            print(f"  크기: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
        print(f"{'='*60}")
    else:
        print(f"\n[!] 빌드 실패 (exit code: {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    main()
