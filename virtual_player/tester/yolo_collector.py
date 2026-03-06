"""
YOLO 학습용 스크린샷 자동 수집기
==================================
1단계: 수집 — 일정 간격으로 스크린샷 캡처 (자동)
2단계: 분류 — 캡처된 이미지를 화면 유형별 폴더에 분류 (사람 or AI)
3단계: 학습 — YOLO classify train 실행

사용법:
  # 수집 (2초 간격, 5분간)
  python -m virtual_player.tester.yolo_collector collect --interval 2 --duration 5

  # AI 자동 분류 (기존 Perception 사용)
  python -m virtual_player.tester.yolo_collector label

  # 학습
  python -m virtual_player.tester.yolo_collector train

  # 테스트
  python -m virtual_player.tester.yolo_collector test --image path/to/image.png
"""

import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
SERIAL = "emulator-5554"

# 데이터셋 경로
DATASET_DIR = Path("E:/AI/virtual_player/data/games/carmatch/yolo_dataset")
RAW_DIR = DATASET_DIR / "raw"           # 미분류 스크린샷
TRAIN_DIR = DATASET_DIR / "train"       # 학습용 (화면 유형별 폴더)
VAL_DIR = DATASET_DIR / "val"           # 검증용
MODEL_DIR = DATASET_DIR / "models"      # 학습된 모델

# 분류할 화면 유형 (YOLO 클래스)
SCREEN_CLASSES = [
    "gameplay",
    "lobby",
    "win",
    "fail",
    "popup",
    "ad",
    "other",
]


def collect_screenshots(interval: float = 2.0, duration_minutes: int = 5):
    """일정 간격으로 스크린샷 수집."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    end_time = time.time() + duration_minutes * 60
    count = 0

    print(f"[Collector] Capturing every {interval}s for {duration_minutes}min")
    print(f"[Collector] Output: {RAW_DIR}")
    print(f"[Collector] Play the game normally. Ctrl+C to stop early.\n")

    try:
        while time.time() < end_time:
            count += 1
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = RAW_DIR / f"frame_{ts}_{count:04d}.png"

            try:
                r = subprocess.run(
                    [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
                    capture_output=True, timeout=10,
                )
                if len(r.stdout) > 1000:
                    path.write_bytes(r.stdout)
                    print(f"  [{ts}] #{count} saved ({len(r.stdout):,} bytes)")
                else:
                    print(f"  [{ts}] #{count} failed (too small)")
            except Exception as e:
                print(f"  [{ts}] #{count} error: {e}")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n[Collector] Stopped by user.")

    print(f"\n[Collector] Total: {count} screenshots in {RAW_DIR}")


def auto_label_with_vision():
    """기존 Perception(CLI)으로 자동 분류.

    느리지만 초기 데이터셋 구축에 유용.
    """
    from .perception import Perception

    # 분류 폴더 생성
    for cls in SCREEN_CLASSES:
        (TRAIN_DIR / cls).mkdir(parents=True, exist_ok=True)

    raw_files = sorted(RAW_DIR.glob("*.png"))
    if not raw_files:
        print("[Label] No raw images found. Run 'collect' first.")
        return

    print(f"[Label] Auto-labeling {len(raw_files)} images with Vision AI...")
    print(f"[Label] This uses CLI mode (~8s per image for Phase 1)")

    perception = Perception()
    stats = {cls: 0 for cls in SCREEN_CLASSES}

    for i, img_path in enumerate(raw_files):
        # Phase 1만 사용 (screen_type만)
        compressed = perception._compress_if_needed(img_path)
        raw = perception._call_vision_cli(compressed, prompt=perception._PROMPT_PHASE1)
        screen = perception._parse_screen_type(raw)

        # 클래스 매핑
        if screen.startswith("fail"):
            cls = "fail"
        elif screen.startswith("lobby_") or screen == "lobby":
            cls = "lobby" if screen == "lobby" else "popup"
        elif screen in ("ad", "ad_install"):
            cls = "ad"
        elif screen in ("gameplay", "win"):
            cls = screen
        elif screen in ("popup", "shop", "leaderboard", "journey",
                        "setting", "profile", "ingame_setting",
                        "ingame_quit_confirm"):
            cls = "other" if screen in ("shop", "leaderboard", "journey",
                                         "setting", "profile") else "popup"
        else:
            cls = "other"

        # 복사
        dest = TRAIN_DIR / cls / img_path.name
        shutil.copy2(img_path, dest)
        stats[cls] += 1

        print(f"  [{i+1}/{len(raw_files)}] {img_path.name} → {cls} ({screen})")

    print(f"\n[Label] Done. Distribution:")
    for cls, count in sorted(stats.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"  {cls}: {count}")


def split_train_val(val_ratio: float = 0.2):
    """train에서 일부를 val로 분리."""
    import random

    for cls in SCREEN_CLASSES:
        train_cls = TRAIN_DIR / cls
        val_cls = VAL_DIR / cls
        val_cls.mkdir(parents=True, exist_ok=True)

        files = list(train_cls.glob("*.png"))
        if len(files) < 5:
            continue

        random.shuffle(files)
        val_count = max(1, int(len(files) * val_ratio))

        for f in files[:val_count]:
            shutil.move(str(f), val_cls / f.name)

        print(f"  {cls}: {len(files) - val_count} train, {val_count} val")


def train_screen_classifier(epochs: int = 50, imgsz: int = 224):
    """YOLO 화면 분류 모델 학습."""
    from ultralytics import YOLO

    # train/val 확인
    train_total = sum(len(list((TRAIN_DIR / cls).glob("*.png")))
                      for cls in SCREEN_CLASSES if (TRAIN_DIR / cls).exists())
    if train_total < 20:
        print(f"[Train] Not enough data ({train_total} images). Need at least 20.")
        print(f"[Train] Run 'collect' then 'label' first.")
        return

    # val이 없으면 자동 분리
    val_total = sum(len(list((VAL_DIR / cls).glob("*.png")))
                    for cls in SCREEN_CLASSES if (VAL_DIR / cls).exists())
    if val_total == 0:
        print("[Train] Splitting train/val (80/20)...")
        split_train_val()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[Train] Starting YOLO classification training")
    print(f"[Train] Dataset: {DATASET_DIR}")
    print(f"[Train] Epochs: {epochs}, Image size: {imgsz}")

    model = YOLO("yolo11n-cls.pt")  # nano 모델 (가장 빠름)
    results = model.train(
        data=str(DATASET_DIR),
        epochs=epochs,
        imgsz=imgsz,
        batch=16,
        project=str(MODEL_DIR),
        name="screen_classifier",
        exist_ok=True,
    )

    # 최적 모델 복사
    best_path = MODEL_DIR / "screen_classifier" / "weights" / "best.pt"
    if best_path.exists():
        final_path = MODEL_DIR / "screen_classifier_best.pt"
        shutil.copy2(best_path, final_path)
        print(f"\n[Train] Best model saved: {final_path}")

    return results


def test_model(image_path: str):
    """학습된 모델로 단일 이미지 테스트."""
    from ultralytics import YOLO

    model_path = MODEL_DIR / "screen_classifier_best.pt"
    if not model_path.exists():
        print(f"[Test] Model not found: {model_path}")
        print(f"[Test] Run 'train' first.")
        return

    model = YOLO(str(model_path))
    results = model(image_path)

    for r in results:
        probs = r.probs
        top5 = probs.top5
        top5conf = probs.top5conf.tolist()
        names = r.names

        print(f"\n[Test] {image_path}")
        for idx, conf in zip(top5, top5conf):
            print(f"  {names[idx]:15} {conf*100:5.1f}%")


def dataset_status():
    """데이터셋 현황 출력."""
    print(f"[Status] Dataset: {DATASET_DIR}\n")

    raw_count = len(list(RAW_DIR.glob("*.png"))) if RAW_DIR.exists() else 0
    print(f"  Raw (unlabeled): {raw_count}")

    print(f"\n  Train:")
    train_total = 0
    for cls in SCREEN_CLASSES:
        d = TRAIN_DIR / cls
        count = len(list(d.glob("*.png"))) if d.exists() else 0
        train_total += count
        if count > 0:
            print(f"    {cls:15} {count}")
    print(f"    {'TOTAL':15} {train_total}")

    print(f"\n  Val:")
    val_total = 0
    for cls in SCREEN_CLASSES:
        d = VAL_DIR / cls
        count = len(list(d.glob("*.png"))) if d.exists() else 0
        val_total += count
        if count > 0:
            print(f"    {cls:15} {count}")
    print(f"    {'TOTAL':15} {val_total}")

    model_path = MODEL_DIR / "screen_classifier_best.pt"
    print(f"\n  Model: {'EXISTS' if model_path.exists() else 'NOT TRAINED'}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="YOLO Screen Classifier Tool")
    sub = parser.add_subparsers(dest="command")

    # collect
    p_collect = sub.add_parser("collect", help="Collect screenshots from game")
    p_collect.add_argument("--interval", type=float, default=2.0,
                           help="Capture interval in seconds (default: 2)")
    p_collect.add_argument("--duration", type=int, default=5,
                           help="Duration in minutes (default: 5)")

    # label
    sub.add_parser("label", help="Auto-label raw images with Vision AI")

    # train
    p_train = sub.add_parser("train", help="Train YOLO classifier")
    p_train.add_argument("--epochs", type=int, default=50)
    p_train.add_argument("--imgsz", type=int, default=224)

    # test
    p_test = sub.add_parser("test", help="Test model on single image")
    p_test.add_argument("--image", required=True, help="Image path")

    # status
    sub.add_parser("status", help="Show dataset status")

    args = parser.parse_args()

    if args.command == "collect":
        collect_screenshots(interval=args.interval, duration_minutes=args.duration)
    elif args.command == "label":
        auto_label_with_vision()
    elif args.command == "train":
        train_screen_classifier(epochs=args.epochs, imgsz=args.imgsz)
    elif args.command == "test":
        test_model(args.image)
    elif args.command == "status":
        dataset_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
