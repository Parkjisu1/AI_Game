"""YOLO board 검출기 학습 — 1 클래스(board)"""
import multiprocessing
if __name__ == '__main__':
    multiprocessing.freeze_support()
    from ultralytics import YOLO
    model = YOLO("yolov8s.pt")
    results = model.train(
        data=r"E:\AI\virtual_player\yolo\pixelflow\dataset_board\dataset.yaml",
        epochs=200, imgsz=640, batch=8, device=0, workers=0,
        patience=30,
        project=r"E:\AI\virtual_player\yolo\pixelflow\runs",
        name="board_detector", exist_ok=True,
        augment=True, flipud=0.5, fliplr=0.5, scale=0.3,
    )
    print(f"\nDone! Best: {results.save_dir}/weights/best.pt")
