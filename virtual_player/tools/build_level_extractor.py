"""
LevelDesignExtractor exe 빌드 스크립트
======================================
실행: python build_level_extractor.py

결과물: dist/LevelDesignExtractor.exe (단일 파일)
"""

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCRIPT_GUI = SCRIPT_DIR / "level_design_extractor_gui.py"
SCRIPT_CLI = SCRIPT_DIR / "level_design_extractor_tmux.py"


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", action="store_true", help="v4 CLI(tmux) 버전 빌드")
    build_args = ap.parse_args()

    SCRIPT = SCRIPT_CLI if build_args.cli else SCRIPT_GUI
    # PyInstaller 확인
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("[*] PyInstaller 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # ultralytics 확인
    try:
        import ultralytics
        print(f"[OK] ultralytics {ultralytics.__version__}")
    except ImportError:
        print("[!] ultralytics 미설치 — pip install ultralytics 후 다시 실행")
        sys.exit(1)

    name = "LevelDesignExtractor_CLI" if build_args.cli else "LevelDesignExtractor"
    windowed = [] if build_args.cli else ["--windowed"]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        *windowed,
        "--name", name,
        "--clean",
        # 필수 hidden imports
        "--hidden-import", "PIL",
        "--hidden-import", "PIL._imagingtk",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "numpy",
        "--hidden-import", "ultralytics",
        "--hidden-import", "ultralytics.nn",
        "--hidden-import", "ultralytics.nn.tasks",
        "--hidden-import", "ultralytics.models",
        "--hidden-import", "ultralytics.models.yolo",
        "--hidden-import", "ultralytics.models.yolo.classify",
        "--hidden-import", "ultralytics.utils",
        "--hidden-import", "torch",
        "--hidden-import", "torchvision",
        # v4: cv2, base64, concurrent
        "--hidden-import", "cv2",
        "--hidden-import", "base64",
        "--hidden-import", "concurrent.futures",
        "--hidden-import", "hashlib",
        "--hidden-import", "io",
        # game_profiles.json 데이터 파일 포함
        "--add-data", f"{SCRIPT_DIR / 'game_profiles.json'};.",
        # 불필요한 대형 패키지 제외 (빌드 크기 절감)
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "notebook",
        "--exclude-module", "tensorboard",
    ]

    cmd.append(str(SCRIPT))

    print(f"\n[*] 빌드 시작...")
    print(f"    대상: {SCRIPT.name}")
    print(f"    (YOLO + PyTorch 포함으로 시간이 걸릴 수 있습니다)\n")

    result = subprocess.run(cmd, cwd=str(SCRIPT.parent))

    if result.returncode == 0:
        exe_path = SCRIPT.parent / "dist" / "LevelDesignExtractor.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / 1024 / 1024
            print(f"\n{'='*50}")
            print(f"  빌드 성공!")
            print(f"  {exe_path}")
            print(f"  크기: {size_mb:.1f} MB")
            print(f"{'='*50}")
        else:
            print(f"\n[OK] 빌드 완료 — dist/ 폴더를 확인하세요")
    else:
        print(f"\n[!] 빌드 실패 (exit code: {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    main()
