"""YOLOv8 학습 v3 — 보드 크롭 이미지"""
import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()
    from ultralytics import YOLO

    model = YOLO("yolov8s.pt")
    results = model.train(
        data=r"E:\AI\virtual_player\yolo\pixelflow\dataset_crop\dataset.yaml",
        epochs=150,
        imgsz=1280,
        batch=4,
        device=0,
        workers=0,
        patience=30,
        project=r"E:\AI\virtual_player\yolo\pixelflow\runs",
        name="pixelflow_v3",
        exist_ok=True,
        augment=True,
        mosaic=0.3,
        close_mosaic=30,
        flipud=0.5,
        fliplr=0.5,
        scale=0.3,
    )
    print(f"\nDone! Best: {results.save_dir}/weights/best.pt")
