"""
dataset_auto 학습 스크립트

- 40장/29클래스 소규모 데이터에 맞춘 설정
- 강한 augmentation + 오래 학습 + early stopping
- RTX 3060 Ti (8GB) 기준 배치 크기 조정
"""
from ultralytics import YOLO
from pathlib import Path
import torch

BASE = Path(r"E:\AI\virtual_player\yolo\pixelflow")
DATA_YAML = BASE / "dataset_auto" / "dataset.yaml"
BASE_MODEL = BASE / "yolo26n.pt"
RUN_NAME = "auto_v1"


def main():
    print(f"[env] GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
    print(f"[env] CUDA: {torch.cuda.is_available()}")
    print(f"[data] {DATA_YAML}")
    print(f"[model] {BASE_MODEL}")

    model = YOLO(str(BASE_MODEL))

    model.train(
        data=str(DATA_YAML),
        project=str(BASE / "runs"),
        name=RUN_NAME,
        exist_ok=True,

        # 학습 강도
        epochs=200,
        patience=40,
        imgsz=1280,
        batch=4,
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

        # 작은 데이터용 강한 augmentation
        mosaic=1.0,
        mixup=0.15,
        copy_paste=0.1,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        degrees=0.0,
        translate=0.1,
        scale=0.3,
        shear=0.0,
        perspective=0.0,
        flipud=0.0,
        fliplr=0.5,

        # 로스 가중치
        box=7.5,
        cls=0.5,
        dfl=1.5,

        # 저장/로깅
        save=True,
        save_period=-1,
        plots=True,
        verbose=True,
    )

    print("\n[OK] 학습 완료")
    print(f"  weights: {BASE / 'runs' / RUN_NAME / 'weights' / 'best.pt'}")
    print(f"  results: {BASE / 'runs' / RUN_NAME / 'results.csv'}")


if __name__ == "__main__":
    main()
