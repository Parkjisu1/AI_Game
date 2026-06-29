"""GenreCapture EXE 진입점 — PyInstaller용 래퍼."""
import sys
import os

# EXE 실행 시 capture 패키지를 찾을 수 있도록 경로 추가
if getattr(sys, 'frozen', False):
    base = os.path.dirname(sys.executable)
    # PyInstaller _MEIPASS (temp extraction dir)
    meipass = getattr(sys, '_MEIPASS', base)
    for p in [base, meipass]:
        if p not in sys.path:
            sys.path.insert(0, p)
else:
    base = os.path.dirname(os.path.abspath(__file__))

from capture.launcher import main
main()
