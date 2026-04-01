"""Stage Extractor + Stream Engine exe 빌드."""
import subprocess, sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
VP_ROOT = SCRIPT_DIR.parent

def build(name, script, extra_imports=None):
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile", "--name", name, "--clean",
        "--hidden-import", "PIL", "--hidden-import", "PIL.Image",
        "--hidden-import", "numpy", "--hidden-import", "sqlite3",
        "--hidden-import", "sklearn", "--hidden-import", "sklearn.cluster",
        "--hidden-import", "sklearn.cluster._kmeans",
        "--paths", str(VP_ROOT),
    ]
    # game_profiles.json 포함
    gp = SCRIPT_DIR / "game_profiles.json"
    if gp.exists():
        cmd += ["--add-data", f"{gp};."]

    if extra_imports:
        for imp in extra_imports:
            cmd += ["--hidden-import", imp]

    # YOLO
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
            "--hidden-import", "torch", "--hidden-import", "torchvision",
            "--hidden-import", "cv2",
        ]
    except ImportError:
        pass

    cmd += ["--exclude-module", "matplotlib", "--exclude-module", "pandas",
            "--exclude-module", "IPython", "--exclude-module", "tensorboard"]
    cmd.append(str(script))

    print(f"\n{'='*50}")
    print(f"  Building {name}...")
    print(f"  Script: {script}")
    print(f"{'='*50}\n")

    result = subprocess.run(cmd, cwd=str(VP_ROOT))

    exe = VP_ROOT / "dist" / f"{name}.exe"
    if result.returncode == 0 and exe.exists():
        print(f"\n  OK: {exe} ({exe.stat().st_size/1024/1024:.0f}MB)")
    else:
        print(f"\n  FAILED (exit={result.returncode})")

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("target", choices=["extractor", "engine", "both"], default="both", nargs="?")
    args = p.parse_args()

    if args.target in ("extractor", "both"):
        build("StageExtractor", SCRIPT_DIR / "stage_extractor.py")

    if args.target in ("engine", "both"):
        build("StreamEngine", VP_ROOT / "tester" / "pipeline" / "stream_processor.py",
              extra_imports=["tester", "tester.db", "tester.db.play_db"])
