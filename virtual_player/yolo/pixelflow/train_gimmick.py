"""YOLO 기믹 검출기 학습"""
import multiprocessing
if __name__ == '__main__':
    multiprocessing.freeze_support()
    from ultralytics import YOLO
    model = YOLO("yolov8s.pt")
    results = model.train(
        data=r"E:\AI\virtual_player\yolo\pixelflow\dataset_gimmick\dataset.yaml",
        epochs=300, imgsz=640, batch=4, device=0, workers=0,
        patience=50,
        project=r"E:\AI\virtual_player\yolo\pixelflow\runs",
        name="gimmick_detector", exist_ok=True,
        augment=True, flipud=0.5, fliplr=0.5, scale=0.4, mosaic=0.5,
    )
    print(f"\nDone! Best: {results.save_dir}/weights/best.pt")
