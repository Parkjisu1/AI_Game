"""
YOLO Object Detection + OpenCV 색상 분석
==========================================
Phase 2 대체: VLM (~100s) → YOLO OD (~10ms) / OpenCV (~50ms)

3단계 감지 체인:
  1. YOLO OD (학습된 모델 있으면) → ~10ms, 최고 정확도
  2. OpenCV HSV 색상 분석 (폴백) → ~50ms, 합리적 정확도
  3. VLM CLI (최후 수단) → ~100s, 불안정

홀더 감지: OpenCV 색상 분석 (항상 사용, ML 불필요)

사용법:
  # OpenCV로 자동 라벨링
  python -m virtual_player.tester.yolo_detector annotate

  # train/val 분리
  python -m virtual_player.tester.yolo_detector split

  # YOLO OD 학습
  python -m virtual_player.tester.yolo_detector train

  # 테스트 (홀더 + 차량)
  python -m virtual_player.tester.yolo_detector test --image path/to/gameplay.png
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------
OD_DATASET_DIR = Path("E:/AI/virtual_player/data/games/carmatch/yolo_od_dataset")
OD_IMAGES_DIR = OD_DATASET_DIR / "images"
OD_LABELS_DIR = OD_DATASET_DIR / "labels"
OD_MODEL_DIR = OD_DATASET_DIR / "models"

# gameplay 스크린샷 원본 (YOLO classify용으로 이미 수집된 것)
GAMEPLAY_SOURCE = Path("E:/AI/virtual_player/data/games/carmatch/yolo_dataset/train/gameplay")

# 게임 좌표 (1080x1920 기준)
BOARD_REGION = (30, 250, 1050, 1350)      # 보드 영역
HOLDER_REGION = (130, 1350, 950, 1450)    # 홀더 영역

# YOLO OD 클래스 (11개)
CAR_CLASSES = [
    "red", "blue", "green", "yellow", "orange",
    "purple", "pink", "cyan", "white", "brown", "mystery"
]
CLASS_TO_ID = {name: i for i, name in enumerate(CAR_CLASSES)}


# ---------------------------------------------------------------------------
# HolderDetector: 홀더 7칸 색상 감지 (OpenCV, 고정 위치)
# ---------------------------------------------------------------------------
class HolderDetector:
    """홀더 7칸 색상 감지 — OpenCV HSV 기반.

    홀더 위치가 게임에서 고정이므로 ML 불필요.
    각 슬롯의 중심점에서 색상을 샘플링하여 판별.
    """

    SLOT_X_CENTERS = [188, 305, 422, 539, 656, 773, 890]  # 7칸 x좌표
    SLOT_Y_CENTER = 1400   # 홀더 중앙 y
    SAMPLE_RADIUS = 15     # 샘플링 반경 (px)

    # 빈 홀더 배경 HSV: H≈115, S≈89, V≈138 (파란 회색 톤)
    # 이 범위에 가까우면 빈 슬롯으로 판정
    EMPTY_H_RANGE = (108, 125)
    EMPTY_S_RANGE = (60, 110)
    EMPTY_V_RANGE = (110, 170)

    # HSV 색상 판별 규칙: (색상명, [(H_low, H_high), ...], S_min, V_min)
    # 차가 홀더에 들어오면 배경보다 채도가 높고 색이 뚜렷함
    COLOR_RULES = [
        ("red",    [(0, 10), (170, 179)], 120, 100),
        ("orange", [(10, 22)],            120, 120),
        ("yellow", [(22, 38)],            120, 140),
        ("green",  [(38, 80)],            100, 80),
        ("cyan",   [(80, 100)],           120, 100),
        ("blue",   [(100, 130)],          120, 100),
        ("purple", [(130, 160)],          100, 80),
        ("pink",   [(160, 175)],          60,  120),
        ("brown",  [(8, 25)],             80,  40),
        ("white",  [(0, 179)],            0,   200),
    ]

    def detect(self, img_path: Path) -> List[Optional[str]]:
        """원본 이미지에서 홀더 7칸 색상 읽기."""
        if not _HAS_CV2:
            return [None] * 7

        img = cv2.imread(str(img_path))
        if img is None:
            return [None] * 7

        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        h_img, w_img = img.shape[:2]

        # 이미지 크기 보정 (원본이 아닐 수 있음)
        sx = w_img / 1080
        sy = h_img / 1920

        result = []
        for slot_x in self.SLOT_X_CENTERS:
            cx = int(slot_x * sx)
            cy = int(self.SLOT_Y_CENTER * sy)
            r = max(1, int(self.SAMPLE_RADIUS * sx))

            y1, y2 = max(0, cy - r), min(h_img, cy + r)
            x1, x2 = max(0, cx - r), min(w_img, cx + r)

            patch = hsv[y1:y2, x1:x2]
            if patch.size == 0:
                result.append(None)
                continue

            avg_h = float(np.mean(patch[:, :, 0]))
            avg_s = float(np.mean(patch[:, :, 1]))
            avg_v = float(np.mean(patch[:, :, 2]))

            # 빈 슬롯 체크: 홀더 배경색(H≈115, S≈89, V≈138)과 유사하면 빈 것
            if (self.EMPTY_H_RANGE[0] <= avg_h <= self.EMPTY_H_RANGE[1] and
                self.EMPTY_S_RANGE[0] <= avg_s <= self.EMPTY_S_RANGE[1] and
                self.EMPTY_V_RANGE[0] <= avg_v <= self.EMPTY_V_RANGE[1]):
                result.append(None)
                continue

            # 채도가 매우 낮으면 빈 것
            if avg_s < 30:
                result.append(None)
                continue

            color = self._classify_hsv(avg_h, avg_s, avg_v)
            result.append(color)

        return result

    def _classify_hsv(self, h: float, s: float, v: float) -> Optional[str]:
        """HSV 평균 → 색상명."""
        if s < 25:
            return "white" if v > 180 else None

        for name, h_ranges, s_min, v_min in self.COLOR_RULES:
            if s < s_min or v < v_min:
                continue
            for h_low, h_high in h_ranges:
                if h_low <= h <= h_high:
                    # brown vs orange: 밝기가 낮으면 brown
                    if name == "orange" and v < 140:
                        return "brown"
                    return name
        return "unknown"


# ---------------------------------------------------------------------------
# CarDetectorCV: OpenCV 색상 분석 기반 차량 감지
# ---------------------------------------------------------------------------
class CarDetectorCV:
    """OpenCV 기반 차량 감지 — YOLO OD 학습 전 즉시 사용 가능.

    HSV 색상 세그멘테이션 → 컨투어 → 바운딩 박스.
    정확도는 YOLO OD보다 낮지만, 학습 데이터 없이 즉시 동작.
    """

    # HSV 범위: (H_low, S_low, V_low, H_high, S_high, V_high)
    # 주의: 주차장 배경 = H:130-145, S:75-180, V:140-215
    #        도로/레인 = H:112-115, S:79-90, V:138-160
    # → 배경과 겹치지 않도록 S_low를 높게 설정
    HSV_RANGES = {
        "red":    [(0, 130, 100, 10, 255, 255), (170, 130, 100, 179, 255, 255)],
        "orange": [(10, 130, 120, 22, 255, 255)],
        "yellow": [(22, 130, 140, 38, 255, 255)],
        "green":  [(38, 100, 80, 80, 255, 255)],
        "cyan":   [(80, 120, 80, 100, 255, 255)],
        "blue":   [(100, 120, 80, 128, 255, 255)],  # H<128 to avoid parking bg
        "purple": [(135, 190, 80, 155, 255, 255)],   # S>190 to skip parking bg (S=181)
        "pink":   [(155, 60, 120, 175, 200, 255)],
        "brown":  [(8, 80, 30, 25, 200, 130)],
        "white":  [(0, 0, 200, 179, 25, 255)],
    }

    # 차량 크기 필터 (1080x1920 기준 면적)
    # 차량 1대 ≈ 100x80px = 8000px² ~ 120x100 = 12000px²
    MIN_CAR_AREA = 4000
    MAX_CAR_AREA = 20000

    def detect(self, img_path: Path) -> List[dict]:
        """차량 감지 → [{color, x, y, w, h}, ...]

        좌표는 원본 이미지 해상도 기준.
        """
        if not _HAS_CV2:
            return []

        img = cv2.imread(str(img_path))
        if img is None:
            return []

        h_img, w_img = img.shape[:2]
        sx, sy = w_img / 1080, h_img / 1920

        # 보드 영역 크롭
        bx1 = int(BOARD_REGION[0] * sx)
        by1 = int(BOARD_REGION[1] * sy)
        bx2 = int(BOARD_REGION[2] * sx)
        by2 = int(BOARD_REGION[3] * sy)

        board = img[by1:by2, bx1:bx2]
        hsv = cv2.cvtColor(board, cv2.COLOR_BGR2HSV)

        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        detections = []

        for color_name, ranges in self.HSV_RANGES.items():
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
            for (hl, sl, vl, hh, sh, vh) in ranges:
                mask |= cv2.inRange(hsv, np.array([hl, sl, vl]), np.array([hh, sh, vh]))

            # 노이즈 제거
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            for cnt in contours:
                area = cv2.contourArea(cnt)
                scaled_area = area / (sx * sy)

                if scaled_area < self.MIN_CAR_AREA or scaled_area > self.MAX_CAR_AREA:
                    continue

                x, y, w, h = cv2.boundingRect(cnt)
                if w < 3 or h < 3:
                    continue

                # 보드 크롭 좌표 → 원본 해상도
                cx = int((x + w / 2 + bx1) / sx)
                cy = int((y + h / 2 + by1) / sy)
                bw = int(w / sx)
                bh = int(h / sy)

                detections.append({
                    "color": color_name,
                    "x": cx, "y": cy,
                    "w": bw, "h": bh,
                    "area": scaled_area,
                })

        # NMS: 겹치는 박스 제거
        return self._nms(detections, iou_threshold=0.3)

    def _nms(self, dets: List[dict], iou_threshold: float) -> List[dict]:
        if not dets:
            return []
        dets = sorted(dets, key=lambda d: d["area"], reverse=True)
        keep = []
        for det in dets:
            if not any(self._iou(det, k) > iou_threshold for k in keep):
                keep.append(det)
        return keep

    @staticmethod
    def _iou(a: dict, b: dict) -> float:
        ax1, ay1 = a["x"] - a["w"] // 2, a["y"] - a["h"] // 2
        ax2, ay2 = a["x"] + a["w"] // 2, a["y"] + a["h"] // 2
        bx1, by1 = b["x"] - b["w"] // 2, b["y"] - b["h"] // 2
        bx2, by2 = b["x"] + b["w"] // 2, b["y"] + b["h"] // 2

        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)

        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0

        inter = (ix2 - ix1) * (iy2 - iy1)
        union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
        return inter / max(union, 1)


# ---------------------------------------------------------------------------
# CarDetectorYOLO: YOLO OD 기반 차량 감지
# ---------------------------------------------------------------------------
class CarDetectorYOLO:
    """YOLO Object Detection 기반 차량 감지.

    학습된 모델 필요. 없으면 CarDetectorCV 폴백.
    """

    _model = None
    _model_path = OD_MODEL_DIR / "car_detector_best.pt"

    @classmethod
    def is_available(cls) -> bool:
        if cls._model_path.exists():
            return True
        alt = OD_MODEL_DIR / "car_detector" / "weights" / "best.pt"
        if alt.exists():
            cls._model_path = alt
            return True
        return False

    @classmethod
    def load(cls):
        if cls._model is not None:
            return cls._model
        if not cls.is_available():
            return None
        try:
            from ultralytics import YOLO
            cls._model = YOLO(str(cls._model_path))
            return cls._model
        except Exception:
            return None

    @classmethod
    def detect(cls, img_path: Path, conf: float = 0.35) -> List[dict]:
        model = cls.load()
        if model is None:
            return []

        results = model(str(img_path), verbose=False, conf=conf)
        detections = []

        if results and len(results[0].boxes) > 0:
            boxes = results[0].boxes
            for i in range(len(boxes)):
                cls_id = int(boxes.cls[i])
                conf_val = float(boxes.conf[i])
                x1, y1, x2, y2 = boxes.xyxy[i].tolist()

                color = CAR_CLASSES[cls_id] if cls_id < len(CAR_CLASSES) else "unknown"
                detections.append({
                    "color": color,
                    "x": int((x1 + x2) / 2),
                    "y": int((y1 + y2) / 2),
                    "w": int(x2 - x1),
                    "h": int(y2 - y1),
                    "conf": conf_val,
                })

        return detections


# ---------------------------------------------------------------------------
# AutoAnnotator: YOLO OD 학습 데이터 자동 생성
# ---------------------------------------------------------------------------
class AutoAnnotator:
    """OpenCV 색상 분석으로 바운딩 박스를 자동 생성.

    완벽하지는 않지만, 초기 학습 데이터 구축에 충분.
    수동 검수 후 학습하면 더 높은 정확도 달성.
    """

    def __init__(self):
        self.cv_detector = CarDetectorCV()

    def annotate_dir(self, source_dir: Path, split: str = "train"):
        """디렉토리 내 모든 gameplay 이미지를 자동 라벨링."""
        images = sorted(source_dir.glob("*.png")) + sorted(source_dir.glob("*.jpg"))
        if not images:
            print(f"[Annotate] No images in {source_dir}")
            return

        img_out = OD_IMAGES_DIR / split
        lbl_out = OD_LABELS_DIR / split
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)

        print(f"[Annotate] Processing {len(images)} images → {split}")

        total_cars = 0
        for i, img_path in enumerate(images):
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            h_img, w_img = img.shape[:2]

            dets = self.cv_detector.detect(img_path)
            total_cars += len(dets)

            # 이미지 복사
            dest_img = img_out / img_path.name
            if not dest_img.exists():
                shutil.copy2(img_path, dest_img)

            # YOLO OD 라벨 형식: class_id x_center y_center width height (0~1 정규화)
            label_path = lbl_out / f"{img_path.stem}.txt"
            with open(label_path, "w") as f:
                for det in dets:
                    cls_id = CLASS_TO_ID.get(det["color"], 10)
                    # 좌표를 원본 이미지 크기로 정규화
                    cx = det["x"] / w_img
                    cy = det["y"] / h_img
                    bw = det["w"] / w_img
                    bh = det["h"] / h_img
                    # 범위 클립
                    cx = max(0.0, min(1.0, cx))
                    cy = max(0.0, min(1.0, cy))
                    bw = max(0.001, min(1.0, bw))
                    bh = max(0.001, min(1.0, bh))
                    f.write(f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")

            if (i + 1) % 20 == 0 or i == len(images) - 1:
                print(f"  [{i+1}/{len(images)}] {img_path.name}: {len(dets)} cars")

        avg = total_cars / max(len(images), 1)
        print(f"\n[Annotate] Done. {total_cars} cars in {len(images)} images (avg {avg:.1f}/img)")

    def create_data_yaml(self):
        """YOLO OD data.yaml 생성."""
        yaml_path = OD_DATASET_DIR / "data.yaml"
        content = (
            f"path: {str(OD_DATASET_DIR).replace(chr(92), '/')}\n"
            f"train: images/train\n"
            f"val: images/val\n"
            f"\n"
            f"nc: {len(CAR_CLASSES)}\n"
            f"names: {CAR_CLASSES}\n"
        )
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(content, encoding="utf-8")
        print(f"[Annotate] Created {yaml_path}")


# ---------------------------------------------------------------------------
# 학습 / 유틸리티
# ---------------------------------------------------------------------------
def split_train_val(val_ratio: float = 0.2):
    """train에서 일부를 val로 분리."""
    import random

    train_imgs = OD_IMAGES_DIR / "train"
    train_lbls = OD_LABELS_DIR / "train"
    val_imgs = OD_IMAGES_DIR / "val"
    val_lbls = OD_LABELS_DIR / "val"

    val_imgs.mkdir(parents=True, exist_ok=True)
    val_lbls.mkdir(parents=True, exist_ok=True)

    images = sorted(train_imgs.glob("*.png")) + sorted(train_imgs.glob("*.jpg"))
    if len(images) < 5:
        print(f"[Split] Not enough images ({len(images)})")
        return

    random.shuffle(images)
    val_count = max(1, int(len(images) * val_ratio))

    for img_path in images[:val_count]:
        shutil.move(str(img_path), str(val_imgs / img_path.name))
        lbl = train_lbls / f"{img_path.stem}.txt"
        if lbl.exists():
            shutil.move(str(lbl), str(val_lbls / lbl.name))

    print(f"[Split] {len(images) - val_count} train, {val_count} val")


def train_car_detector(epochs: int = 100, imgsz: int = 640):
    """YOLO OD 차량 감지 모델 학습."""
    from ultralytics import YOLO

    yaml_path = OD_DATASET_DIR / "data.yaml"
    if not yaml_path.exists():
        print("[Train] data.yaml not found. Run 'annotate' first.")
        return

    train_labels = list((OD_LABELS_DIR / "train").glob("*.txt"))
    if len(train_labels) < 10:
        print(f"[Train] Not enough data ({len(train_labels)} images). Need at least 10.")
        return

    # val이 없으면 자동 분리
    val_imgs = OD_IMAGES_DIR / "val"
    if not val_imgs.exists() or len(list(val_imgs.glob("*"))) == 0:
        print("[Train] Auto-splitting train/val...")
        split_train_val()

    OD_MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[Train] YOLO OD training: {epochs} epochs, {imgsz}px")
    print(f"[Train] Classes: {CAR_CLASSES}")

    model = YOLO("yolo11n.pt")
    results = model.train(
        data=str(yaml_path),
        epochs=epochs,
        imgsz=imgsz,
        batch=8,
        project=str(OD_MODEL_DIR),
        name="car_detector",
        exist_ok=True,
    )

    best = OD_MODEL_DIR / "car_detector" / "weights" / "best.pt"
    if best.exists():
        final = OD_MODEL_DIR / "car_detector_best.pt"
        shutil.copy2(best, final)
        print(f"\n[Train] Best model: {final}")

    return results


def test_detection(image_path: str):
    """단일 이미지에서 홀더 + 차량 감지 테스트."""
    path = Path(image_path)
    if not path.exists():
        print(f"[Test] File not found: {path}")
        return

    print(f"[Test] Image: {path}")
    print(f"[Test] Size: {path.stat().st_size:,} bytes")

    # 홀더 감지
    holder_det = HolderDetector()
    holder = holder_det.detect(path)
    filled = sum(1 for h in holder if h is not None)
    print(f"\n[Holder] {holder} ({filled}/7 filled)")

    # YOLO OD 감지
    if CarDetectorYOLO.is_available():
        cars_yolo = CarDetectorYOLO.detect(path)
        print(f"\n[YOLO OD] {len(cars_yolo)} cars:")
        for c in cars_yolo:
            print(f"  {c['color']:8} @ ({c['x']:4},{c['y']:4}) "
                  f"size=({c['w']:3}x{c['h']:3}) conf={c.get('conf',0):.2f}")
    else:
        print("\n[YOLO OD] Model not trained yet")

    # OpenCV 감지
    cv_det = CarDetectorCV()
    cars_cv = cv_det.detect(path)
    print(f"\n[OpenCV] {len(cars_cv)} cars:")
    for c in cars_cv:
        print(f"  {c['color']:8} @ ({c['x']:4},{c['y']:4}) "
              f"size=({c['w']:3}x{c['h']:3}) area={c['area']:.0f}")


def dataset_status():
    """데이터셋 현황."""
    print(f"[Status] OD Dataset: {OD_DATASET_DIR}\n")

    for split in ("train", "val"):
        imgs = OD_IMAGES_DIR / split
        lbls = OD_LABELS_DIR / split
        img_count = len(list(imgs.glob("*"))) if imgs.exists() else 0
        lbl_count = len(list(lbls.glob("*.txt"))) if lbls.exists() else 0
        print(f"  {split}: {img_count} images, {lbl_count} labels")

    model_path = OD_MODEL_DIR / "car_detector_best.pt"
    print(f"\n  Model: {'EXISTS' if model_path.exists() else 'NOT TRAINED'}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="YOLO Car Detector for CarMatch")
    sub = parser.add_subparsers(dest="command")

    p_ann = sub.add_parser("annotate", help="Auto-annotate gameplay images with OpenCV")
    p_ann.add_argument("--source", type=str, default=str(GAMEPLAY_SOURCE))
    p_ann.add_argument("--split", type=str, default="train")

    p_train = sub.add_parser("train", help="Train YOLO OD model")
    p_train.add_argument("--epochs", type=int, default=100)
    p_train.add_argument("--imgsz", type=int, default=640)

    p_test = sub.add_parser("test", help="Test detection on single image")
    p_test.add_argument("--image", required=True)

    sub.add_parser("split", help="Split train/val (80/20)")
    sub.add_parser("status", help="Show dataset status")

    args = parser.parse_args()

    if args.command == "annotate":
        ann = AutoAnnotator()
        ann.annotate_dir(Path(args.source), args.split)
        ann.create_data_yaml()
    elif args.command == "train":
        train_car_detector(epochs=args.epochs, imgsz=args.imgsz)
    elif args.command == "test":
        test_detection(args.image)
    elif args.command == "split":
        split_train_val()
    elif args.command == "status":
        dataset_status()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
