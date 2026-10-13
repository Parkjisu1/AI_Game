"""
검수된 level 라벨로 YOLO 학습.
- 데이터: dataset_levels/ (52 train + 13 val, 43K bboxes)
- 베이스: yolo26n.pt
- 출력: runs/levels_v1/
"""
"""
YOLO 학습 — 인자 옵션:
  --finetune           best.pt 기반 fine-tune (이전 학습 유지)
  --epochs N           epoch 수 (기본: 데이터 수에 따라 자동)
  --batch N            배치 크기 (기본: 2)
  --imgsz N            이미지 크기 (기본: 1920)
  --run-name X         결과 폴더명 (기본: levels_v1)
"""
from ultralytics import YOLO
from pathlib import Path
import torch
import sys
import argparse

# 자동 경로 탐지
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import (
    PIXELFLOW_DIR, DATASET_DIR, RUNS_DIR, BASE_MODEL, LEVELS_MODEL_WEIGHTS,
)

DATA_YAML = DATASET_DIR / "dataset.yaml"


def count_train_images() -> int:
    """학습 이미지 수 조회."""
    train_dir = DATASET_DIR / "images" / "train"
    if not train_dir.exists():
        return 0
    return len(list(train_dir.glob("*.png")) + list(train_dir.glob("*.jpg")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--finetune", action="store_true",
                    help="이전 best.pt 기반 fine-tune (이전 학습 유지)")
    ap.add_argument("--epochs", type=int, default=0,
                    help="epoch 수 (0=자동: 데이터 수에 따라)")
    ap.add_argument("--batch", type=int, default=2)
    ap.add_argument("--imgsz", type=int, default=1920)
    ap.add_argument("--run-name", default="levels_v1")
    args = ap.parse_args()

    print(f"[env] GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
    print(f"[data] {DATA_YAML}")

    # 베이스 모델 결정
    if args.finetune and LEVELS_MODEL_WEIGHTS.exists():
        base = LEVELS_MODEL_WEIGHTS
        print(f"[mode] Fine-tune from previous best: {base}")
    else:
        base = BASE_MODEL
        print(f"[mode] From scratch: {base}")

    # epoch 자동 조정 (데이터 수에 따라)
    if args.epochs == 0:
        n = count_train_images()
        if n < 30:
            epochs = 300; patience = 60   # 적은 데이터: 오래 학습
        elif n < 100:
            epochs = 200; patience = 40   # 중간
        else:
            epochs = 150; patience = 30   # 충분한 데이터: 빠르게
        print(f"[auto] {n} train images → epochs={epochs}, patience={patience}")
    else:
        epochs = args.epochs
        patience = max(20, epochs // 5)

    model = YOLO(str(base))

    model.train(
        data=str(DATA_YAML),
        project=str(RUNS_DIR),
        name=args.run_name,
        exist_ok=True,

        # 학습 강도 (자동 조정됨)
        epochs=epochs,
        patience=patience,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=4,
        device=0,
        seed=42,

        # 최적화
        optimizer="AdamW",
        lr0=0.001,
        lrf=0.01,
        weight_decay=0.0005,
        warmup_epochs=5,
        cos_lr=True,

        # Augmentation (셀 크기 다양화)
        mosaic=1.0,
        mixup=0.10,
        copy_paste=0.10,
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.3,
        degrees=0.0,
        translate=0.1,
        scale=0.4,          # ±40% 스케일 변동 → 셀 크기 일반화
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.5,

        box=7.5,
        cls=0.5,
        dfl=1.5,

        save=True,
        save_period=-1,
        plots=True,
        verbose=True,
    )

    print("\n[OK] 학습 완료")
    print(f"  weights: {RUNS_DIR / args.run_name / 'weights' / 'best.pt'}")
    print(f"  results: {RUNS_DIR / args.run_name / 'results.csv'}")


if __name__ == "__main__":
    main()
