"""
Genre Capture → EXE 빌드 스크립트
===================================
Usage: py -3.10 build_genre_capture.py  (Windows 7+ 호환을 위해 Python 3.10 권장)
Output: virtual_player/dist/GenreCapture.exe

2026-04-14 업그레이드:
  - certifi SSL 인증서 번들 (GitHub/Google HTTPS 실패 방지)
  - 크래시 핸들러는 launcher.py 내부로 이식됨 (crash.log 기록)
  - deps.py 유저 로컬 설치 경로 (%LOCALAPPDATA%) 사용
"""

import subprocess
import sys
import PyInstaller.__main__
from pathlib import Path

root = Path(__file__).parent
capture_dir = root / "capture"

# 필수 런타임 패키지 확인
for mod, pkg in (("certifi", "certifi"), ("PIL", "Pillow"), ("pytesseract", "pytesseract")):
    try:
        __import__(mod)
    except ImportError:
        print(f"[*] {pkg} 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

PyInstaller.__main__.run([
    str(root / "genre_capture_entry.py"),
    "--name=GenreCapture",
    "--onefile",
    "--windowed",
    "--noconfirm",
    "--clean",
    f"--distpath={root.parent / 'dist'}",
    f"--workpath={root.parent / 'build'}",
    f"--specpath={root}",
    # capture 패키지 전체 포함 (소스 파일째로 번들)
    f"--add-data={capture_dir};capture",
    # SSL 인증서 번들 — 오래된 Windows에서 HTTPS 실패 방지
    "--collect-data=certifi",
    # PIL 서브모듈 전체 수집 (format 플러그인)
    "--collect-submodules=PIL",
    # 의존성
    "--hidden-import=PIL",
    "--hidden-import=PIL.Image",
    "--hidden-import=PIL.ImageTk",
    "--hidden-import=numpy",
    "--hidden-import=pytesseract",
    "--hidden-import=certifi",
    "--hidden-import=ssl",
    "--hidden-import=ctypes",
    "--hidden-import=ctypes.wintypes",
    "--hidden-import=zipfile",
    "--hidden-import=urllib.request",
    "--hidden-import=urllib.error",
    "--hidden-import=tkinter",
    "--hidden-import=tkinter.ttk",
    "--hidden-import=tkinter.filedialog",
    "--hidden-import=tkinter.messagebox",
    # EXE 크기 줄이기 — 무거운 패키지 제외
    "--exclude-module=torch",
    "--exclude-module=tensorflow",
    "--exclude-module=paddle",
    "--exclude-module=paddleocr",
    "--exclude-module=easyocr",
    "--exclude-module=ultralytics",
    "--exclude-module=matplotlib",
    "--exclude-module=scipy",
    "--exclude-module=cv2",
    "--exclude-module=pandas",
    "--exclude-module=IPython",
    "--exclude-module=jupyter",
])
