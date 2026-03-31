"""
AI Game Tester v3 — exe 빌드 스크립트
"""
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
VP_ROOT = SCRIPT_DIR.parent
MAIN_SCRIPT = VP_ROOT / "tester" / "pipeline" / "main.py"
SCHEMA_SQL = VP_ROOT / "tester" / "db" / "schema.sql"
PROFILES = SCRIPT_DIR / "game_profiles.json"


def main():
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("[*] PyInstaller 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    data_files = []
    if SCHEMA_SQL.exists():
        data_files += ["--add-data", f"{SCHEMA_SQL};tester/db"]
    if PROFILES.exists():
        data_files += ["--add-data", f"{PROFILES};."]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "AIGameTester",
        "--clean",
        "--hidden-import", "PIL",
        "--hidden-import", "PIL.Image",
        "--hidden-import", "numpy",
        "--hidden-import", "sqlite3",
        "--hidden-import", "tester",
        "--hidden-import", "tester.db",
        "--hidden-import", "tester.db.play_db",
        "--hidden-import", "tester.db.sync_manager",
        "--hidden-import", "tester.pipeline",
        "--hidden-import", "tester.pipeline.ai_player",
        *data_files,
        "--paths", str(VP_ROOT),
        "--exclude-module", "matplotlib",
        "--exclude-module", "scipy",
        "--exclude-module", "pandas",
        "--exclude-module", "IPython",
        "--exclude-module", "jupyter",
        "--exclude-module", "tensorboard",
        str(MAIN_SCRIPT),
    ]

    # YOLO는 선택적 (없어도 동작)
    try:
        import ultralytics
        cmd += [
            "--hidden-import", "ultralytics",
            "--hidden-import", "ultralytics.nn",
            "--hidden-import", "ultralytics.nn.tasks",
            "--hidden-import", "ultralytics.models",
            "--hidden-import", "ultralytics.models.yolo",
            "--hidden-import", "ultralytics.models.yolo.classify",
            "--hidden-import", "ultralytics.utils",
            "--hidden-import", "torch",
            "--hidden-import", "torchvision",
            "--hidden-import", "cv2",
        ]
        print(f"[OK] ultralytics {ultralytics.__version__} — YOLO 포함 빌드")
    except ImportError:
        print("[!] ultralytics 미설치 — YOLO 없이 빌드 (패턴 매칭만 사용)")

    print(f"\n[*] 빌드 시작: {MAIN_SCRIPT.name}")
    result = subprocess.run(cmd, cwd=str(VP_ROOT))

    if result.returncode == 0:
        exe = VP_ROOT / "dist" / "AIGameTester.exe"
        if exe.exists():
            size = exe.stat().st_size / 1024 / 1024
            print(f"\n{'='*50}")
            print(f"  빌드 성공: {exe}")
            print(f"  크기: {size:.1f} MB")
            print(f"{'='*50}")
    else:
        print(f"\n[!] 빌드 실패 (exit: {result.returncode})")
        sys.exit(1)


if __name__ == "__main__":
    main()
