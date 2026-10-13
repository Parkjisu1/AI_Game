"""
YOLOv8 학습 — PixelFlow 블록 검출
"""
import multiprocessing

if __name__ == '__main__':
    multiprocessing.freeze_support()

    from ultralytics import YOLO

    model = YOLO("yolov8s.pt")

    results = model.train(
        data=r"E:\AI\virtual_player\yolo\pixelflow\dataset\dataset.yaml",
        epochs=50,
        imgsz=640,
        batch=8,
        device=0,
        workers=0,        # Windows 호환
        patience=10,
        project=r"E:\AI\virtual_player\yolo\pixelflow\runs",
        name="pixelflow_v1",
        exist_ok=True,
        mosaic=0.5,
        close_mosaic=10,
    )

    print(f"\nTraining complete!")
    print(f"Best model: {results.save_dir}/weights/best.pt")
