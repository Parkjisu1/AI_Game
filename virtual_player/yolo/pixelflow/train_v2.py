"""YOLOv8 학습 v2 — 수동 라벨 데이터"""
import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    from ultralytics import YOLO

    model = YOLO("yolov8s.pt")
    results = model.train(
        data=r"E:\AI\virtual_player\yolo\pixelflow\dataset_manual\dataset.yaml",
        epochs=100,
        imgsz=1280,       # 고해상도 (작은 블록 검출)
        batch=4,           # VRAM 맞춤
        device=0,
        workers=0,
        patience=20,
        project=r"E:\AI\virtual_player\yolo\pixelflow\runs",
        name="pixelflow_v2",
        exist_ok=True,
        # 소량 데이터 보강
        augment=True,
        mosaic=0.3,
        close_mosaic=20,
        flipud=0.5,
        fliplr=0.5,
        scale=0.3,
    )
    print(f"\nDone! Best: {results.save_dir}/weights/best.pt")
