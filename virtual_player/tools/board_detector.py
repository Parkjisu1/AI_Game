"""
Board Region Detector v3 (YOLO-based)
======================================
학습된 board_detector.pt를 사용하여 정확하게 보드 영역 크롭.

특징:
- mAP50 1.0 (6장 학습, val=2) — 작은 데이터셋이지만 보드 패턴이 일관돼서 신뢰도 높음
- confidence 가장 높은 bbox 선택
- YOLO 로드 실패 시 HSV fallback

사용:
  from board_detector import BoardDetector
  detector = BoardDetector()
  board_img, bbox = detector.detect(img_bgr)
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional
import numpy as np
import cv2


class BoardDetector:
    DEFAULT_WEIGHTS = Path(
        r"E:\AI\virtual_player\yolo\pixelflow\runs\board_detector\weights\best.pt"
    )

    def __init__(
        self,
        weights_path: Optional[Path] = None,
        min_confidence: float = 0.5,
        pad: int = 4,
    ):
        self.weights = Path(weights_path) if weights_path else self.DEFAULT_WEIGHTS
        self.min_conf = min_confidence
        self.pad = pad
        self._model = None
        self._load_model()

    def _load_model(self):
        """YOLO 모델 lazy load."""
        if not self.weights.exists():
            print(f"[BoardDetector] weights not found: {self.weights}")
            return
        try:
            from ultralytics import YOLO
            self._model = YOLO(str(self.weights))
        except Exception as e:
            print(f"[BoardDetector] load failed: {e}")

    def detect(
        self, img_bgr: np.ndarray
    ) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """보드 영역 크롭.

        Returns:
            (board_bgr, (x, y, w, h))
        """
        h, w = img_bgr.shape[:2]

        if self._model is None:
            # Fallback: HSV
            return self._hsv_fallback(img_bgr)

        # YOLO 추론
        results = self._model(img_bgr, verbose=False)
        if len(results) == 0 or len(results[0].boxes) == 0:
            return self._hsv_fallback(img_bgr)

        boxes = results[0].boxes
        # confidence 최고 bbox
        confs = boxes.conf.cpu().numpy()
        best_idx = int(np.argmax(confs))
        if confs[best_idx] < self.min_conf:
            return self._hsv_fallback(img_bgr)

        x1, y1, x2, y2 = boxes.xyxy[best_idx].cpu().numpy()

        x0 = max(0, int(x1) - self.pad)
        y0 = max(0, int(y1) - self.pad)
        x1 = min(w, int(x2) + self.pad)
        y1 = min(h, int(y2) + self.pad)

        return img_bgr[y0:y1, x0:x1], (x0, y0, x1 - x0, y1 - y0)

    def _hsv_fallback(
        self, img_bgr: np.ndarray
    ) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        """YOLO 실패 시 HSV 기반 fallback (정확도 낮음)."""
        h, w = img_bgr.shape[:2]
        hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
        mask = ((hsv[:, :, 1] > 40) & (hsv[:, :, 2] > 50)).astype(np.uint8) * 255
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
        mask = cv2.dilate(mask, k, iterations=2)

        num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if num <= 1:
            return img_bgr, (0, 0, w, h)

        # aspect ratio 0.8~1.3 범위 + 면적 최대
        best_idx = None
        best_area = 0
        for i in range(1, num):
            x, y, bw, bh, area = stats[i]
            if bh == 0:
                continue
            ar = bw / bh
            if 0.8 <= ar <= 1.3 and area > best_area:
                best_area = area
                best_idx = i

        if best_idx is None:
            best_idx = int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) + 1

        x = int(stats[best_idx, cv2.CC_STAT_LEFT])
        y = int(stats[best_idx, cv2.CC_STAT_TOP])
        bw = int(stats[best_idx, cv2.CC_STAT_WIDTH])
        bh = int(stats[best_idx, cv2.CC_STAT_HEIGHT])

        x0 = max(0, x - self.pad)
        y0 = max(0, y - self.pad)
        x1 = min(w, x + bw + self.pad)
        y1 = min(h, y + bh + self.pad)
        return img_bgr[y0:y1, x0:x1], (x0, y0, x1 - x0, y1 - y0)


# 편의 함수 (기존 호환성)
_default_detector: Optional[BoardDetector] = None


def detect_board_region(
    img_bgr: np.ndarray,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """기본 detector 사용."""
    global _default_detector
    if _default_detector is None:
        _default_detector = BoardDetector()
    return _default_detector.detect(img_bgr)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python board_detector.py <image>")
        sys.exit(1)

    img = cv2.imread(sys.argv[1])
    if img is None:
        print(f"Cannot read: {sys.argv[1]}")
        sys.exit(1)

    d = BoardDetector()
    print(f"Original: {img.shape[1]}x{img.shape[0]}")
    print(f"Model:    {d.weights} (loaded: {d._model is not None})")

    board, rect = d.detect(img)
    print(f"Board:    {board.shape[1]}x{board.shape[0]}")
    print(f"Rect:     x={rect[0]}, y={rect[1]}, w={rect[2]}, h={rect[3]}")

    out = sys.argv[1].replace(".png", "_board.png").replace(".jpg", "_board.jpg")
    cv2.imwrite(out, board)
    print(f"Saved: {out}")
