"""
holder_detector v2 재학습 스크립트.

99 라벨 (42 원본 + 57 신규) 로 40-class holder_detector 재학습.

Usage (3080 Ti D: drive 기준):
    cd /d D:\\queue_pipeline_v2
    python run_train_v2.py

Usage (로컬 E:):
    python run_train_v2.py --images E:/AI/.../labeling/images_queue_merged \
                           --labels E:/AI/.../labeling/labels_queue_merged \
                           --classes E:/AI/.../labeling/labels_queue_v2/classes.txt \
                           --output-dataset E:/AI/.../dataset_holder_v2 \
                           --runs-dir E:/AI/.../runs \
                           --name holder_detector_v2
"""
import argparse
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    # 기본값은 3080 Ti D: 드라이브 기준
    ap.add_argument("--images", default=r"D:\labeling_v2\images_queue_merged")
    ap.add_argument("--labels", default=r"D:\labeling_v2\labels_queue_merged")
    ap.add_argument("--classes", default=r"D:\labeling_v2\classes.txt")
    ap.add_argument("--output-dataset", default=r"D:\dataset_holder_v2")
    ap.add_argument("--runs-dir", default=r"D:\runs")
    ap.add_argument("--name", default="holder_detector_v2")
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--patience", type=int, default=40)
    ap.add_argument("--base-weights", default="yolov8s.pt")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    import stage2c_train_holder as s

    # Load 40 classes from classes.txt
    cls_path = Path(args.classes)
    if not cls_path.exists():
        print(f"ERROR: classes.txt not found: {cls_path}", file=sys.stderr)
        return 2
    names = [n.strip().lower() for n in cls_path.read_text(encoding="utf-8").splitlines() if n.strip()]
    class_map = {n: i for i, n in enumerate(names)}
    print(f"Loaded {len(class_map)} classes")

    print(f"Building dataset from:")
    print(f"  images: {args.images}")
    print(f"  labels: {args.labels}")
    print(f"  output: {args.output_dataset}")

    yaml_path = s.build_dataset(args.images, args.labels, args.output_dataset, class_map)
    print(f"Dataset ready: {yaml_path}")

    print(f"\nLoading YOLO ({args.base_weights})...")
    from ultralytics import YOLO
    model = YOLO(args.base_weights)

    print(f"\nTraining {args.name}...")
    print(f"  epochs={args.epochs}, batch={args.batch}, imgsz={args.imgsz}, patience={args.patience}")
    model.train(
        data=str(yaml_path),
        epochs=args.epochs,
        batch=args.batch,
        imgsz=args.imgsz,
        patience=args.patience,
        project=args.runs_dir,
        name=args.name,
        exist_ok=True,
        workers=0,
        cache=False,
        amp=True,
    )
    print(f"\nDone. Best weights: {args.runs_dir}/{args.name}/weights/best.pt")


if __name__ == "__main__":
    sys.exit(main() or 0)
