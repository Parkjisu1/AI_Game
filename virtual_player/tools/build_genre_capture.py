"""
Genre Capture → EXE 빌드 스크립트
===================================
Usage: python build_genre_capture.py
Output: dist/GenreCapture.exe
"""

import PyInstaller.__main__
from pathlib import Path

root = Path(__file__).parent
capture_dir = root / "capture"

PyInstaller.__main__.run([
    str(root / "genre_capture_entry.py"),
    "--name=GenreCapture",
    "--onefile",
    "--windowed",
    "--noconfirm",
    "--clean",
    f"--distpath={root / 'dist'}",
    f"--workpath={root / 'build'}",
    f"--specpath={root}",
    # capture 패키지 전체 포함
    f"--add-data={capture_dir};capture",
    # 의존성
    "--hidden-import=PIL",
    "--hidden-import=PIL.Image",
    "--hidden-import=numpy",
    "--hidden-import=pytesseract",
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
])
