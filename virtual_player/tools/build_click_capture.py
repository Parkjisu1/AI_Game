"""
ClickCapture exe 빌드 스크립트
===============================
실행: python build_click_capture.py

결과물: dist/ClickCapture.exe (단일 파일)
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent / "click_capture.py"
ICON = Path(__file__).parent / "click_capture.ico"


def main():
    # PyInstaller 설치 확인
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("[*] PyInstaller 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                    # 단일 exe
        "--windowed",                   # 콘솔 창 없음 (GUI)
        "--name", "ClickCapture",       # exe 이름
        "--clean",                      # 빌드 캐시 정리
    ]

    # 아이콘 파일이 있으면 사용
    if ICON.exists():
        cmd += ["--icon", str(ICON)]

    cmd.append(str(SCRIPT))

    print(f"\n[*] 빌드 시작...")
    print(f"    명령: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=str(SCRIPT.parent))

    if result.returncode == 0:
        exe_path = SCRIPT.parent / "dist" / "ClickCapture.exe"
        print(f"\n{'='*50}")
        print(f"  빌드 성공!")
        print(f"  {exe_path}")
        print(f"  크기: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
        print(f"{'='*50}")
    else:
        print(f"\n[!] 빌드 실패 (exit code: {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    main()
