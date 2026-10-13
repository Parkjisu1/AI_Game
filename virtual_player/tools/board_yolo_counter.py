"""
Board YOLO Counter — YOLO-World zero-shot으로 PixelFlow 블록 검출/카운트
학습 데이터 없이 텍스트 프롬프트로 블록을 찾음
"""
import sys
import cv2
import numpy as np
from ultralytics import YOLOWorld


def analyze(image_path, conf=0.15):
    # YOLO-World 로드 (zero-shot)
    model = YOLOWorld("yolov8s-worldv2")

    # 검출할 클래스 정의
    model.set_classes(["purple block", "yellow block", "green block"])

    # 추론
    results = model.predict(
        image_path,
        conf=conf,
        iou=0.3,
        imgsz=1024,
        verbose=False
    )

    result = results[0]
    boxes = result.boxes
    print(f"Image: {result.orig_shape[1]}x{result.orig_shape[0]}")
    print(f"Detected: {len(boxes)} objects (conf >= {conf})")

    # 클래스별 카운트
    names = result.names
    counts = {}
    for cls_id in range(len(names)):
        cls_name = names[cls_id]
        cls_count = (boxes.cls == cls_id).sum().item()
        if cls_count > 0:
            counts[cls_name] = int(cls_count)

    print(f"\n{'='*50}")
    print(f"  YOLO-World CELL COUNT")
    print(f"{'='*50}")
    for name, count in counts.items():
        print(f"  {name:20s}: {count}")
    print(f"  {'Total':20s}: {sum(counts.values())}")
    print(f"{'='*50}")

    # 시각화 저장
    annotated = result.plot()
    out_path = image_path.replace('.png', '_yolo_result.png')
    cv2.imwrite(out_path, annotated)
    print(f"\nSaved: {out_path}")

    # confidence 분포
    if len(boxes) > 0:
        confs = boxes.conf.cpu().numpy()
        print(f"\nConfidence stats: min={confs.min():.3f}, max={confs.max():.3f}, mean={confs.mean():.3f}")

    return counts


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else \
        r"E:\AI\virtual_player\data\pixelflow\images\click_20260325_101759_0044_after.png"

    conf = 0.15
    for a in sys.argv:
        if a.startswith('--conf='):
            conf = float(a.split('=')[1])

    analyze(path, conf)
