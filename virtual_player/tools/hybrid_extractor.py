"""
Hybrid Level Extractor (Cells + Gimmicks)
==========================================
옵션 C 하이브리드 파이프라인:
- 보드 크롭: YOLO board_detector
- 그리드 차원: FFT grid_detector
- 셀 색상: cell_aware_analyzer (픽셀 분석)
- 기믹 탐지: YOLO 커스텀 모델 (auto_v1)

출력: 표준 Level JSON 포맷
"""
from __future__ import annotations
import sys
import json
from pathlib import Path
from collections import Counter
from typing import Optional

import cv2
import numpy as np

# 같은 폴더 모듈 로드
sys.path.insert(0, str(Path(__file__).parent))
from cell_aware_analyzer import analyze as analyze_cells, load_profile
from gimmick_classifier import GimmickClassifier


# ══════════════════════════════════════════════════════════════
#  Cell Detection (YOLO cell_only v3, 2026-04-20)
# ══════════════════════════════════════════════════════════════

class CellDetector:
    """YOLO 셀 탐지기 (단일 `cell` 클래스, max_det=5000).

    v1 (2026-04-16, 250 stages): P 0.975 / R 0.330 / mAP50 0.333.
    v2 (2026-04-18, 155 epochs): P 0.953 / R 0.348 / mAP50 0.342.
    v3 (2026-04-20, 300 epochs): P 0.949 / R 0.348 / mAP50 0.343 / mAP50-95 0.310.
    """

    DEFAULT_WEIGHTS = Path(
        r"E:\AI\virtual_player\yolo\pixelflow\runs\cell_only_v3\weights\best.pt"
    )

    def __init__(
        self,
        weights: Optional[Path] = None,
        min_confidence: float = 0.25,
        max_det: int = 5000,
        imgsz: int = 1920,
        use_hires: bool = True,
    ):
        self.weights = Path(weights) if weights else self.DEFAULT_WEIGHTS
        self.min_conf = min_confidence
        self.max_det = max_det
        self.imgsz = imgsz
        self.use_hires = use_hires
        self._model = None
        self._load()

    def _load(self):
        if not self.weights.exists():
            print(f"[CellDetector] weights not found: {self.weights}")
            return
        try:
            from ultralytics import YOLO
            self._model = YOLO(str(self.weights))
        except Exception as e:
            print(f"[CellDetector] load failed: {e}")

    def _run(self, img_bgr: np.ndarray, conf: float, imgsz: Optional[int] = None) -> list[tuple[int, int, int, int]]:
        use_imgsz = imgsz if imgsz is not None else self.imgsz
        results = self._model(
            img_bgr, verbose=False,
            conf=conf, max_det=self.max_det, imgsz=use_imgsz,
        )
        boxes = []
        for box in results[0].boxes:
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
            boxes.append((int(x1), int(y1), int(x2), int(y2)))
        return boxes

    def _adaptive_conf(
        self, img_bgr: np.ndarray, imgsz: int, expected_min: int
    ) -> list[tuple[int, int, int, int]]:
        """주어진 imgsz에서 conf를 단계적으로 낮춰가며 셀 탐지."""
        boxes = self._run(img_bgr, self.min_conf, imgsz)
        if len(boxes) >= expected_min:
            return boxes
        for fallback_conf in [0.1, 0.05, 0.02, 0.01]:
            retry = self._run(img_bgr, fallback_conf, imgsz)
            if len(retry) > len(boxes):
                boxes = retry
            if len(boxes) >= expected_min:
                break
        return boxes

    def detect(
        self,
        img_bgr: np.ndarray,
        expected_min_cells: int = 50,
        try_hires: Optional[bool] = None,
    ) -> list[tuple[int, int, int, int]]:
        if try_hires is None:
            try_hires = self.use_hires
        """다단계 적응형 셀 탐지.

        전략:
          1. imgsz=1920, conf=0.25 (빠름, 일반 이미지용)
          2. 결과 부족 시 같은 imgsz에서 conf 낮춰 재시도
          3. 여전히 부족하거나 bbox 중간 크기가 작은 경우 (대형 보드):
             imgsz=2560으로 재검출 후 cells 더 많으면 채택
          4. 2560에서도 부족하면 conf 낮춰 재시도
        """
        if self._model is None:
            return []

        # Stage 1-2: imgsz=1920 with adaptive conf
        boxes = self._adaptive_conf(img_bgr, 1920, expected_min_cells)

        if not try_hires:
            return boxes

        # Stage 3: 대형 보드 감지 heuristic
        # - bbox 중간 크기가 작거나(<40px = 작은 셀 = 큰 보드)
        # - 결과가 baseline보다 최소 미만이면
        # 대형 보드만 aggressive hires 적용 (작은 셀, 많은 개수)
        # 다른 케이스는 baseline 유지 — 재학습 없이 해결 어려움
        median_size = 100.0
        if boxes:
            sizes = [max(b[2] - b[0], b[3] - b[1]) for b in boxes]
            median_size = float(np.median(sizes))

        if not (median_size < 38 and len(boxes) >= 1000):
            return boxes

        # 대형 보드: imgsz=2560에서 conf 낮춰가며 best 선택
        # FP 상한: 2.5x baseline
        fp_limit = int(len(boxes) * 2.5)
        best = boxes
        for conf in [0.25, 0.1, 0.05, 0.02, 0.01]:
            c = self._run(img_bgr, conf, 2560)
            if len(c) > len(best) and len(c) <= fp_limit:
                best = c
        return best

    @staticmethod
    def estimate_grid(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int]:
        """bbox 분포에서 (rows, cols) 추정.

        방식: 셀 중심 좌표의 x, y 각각을 클러스터링 (median cell size를 threshold로).
        """
        if not boxes:
            return 0, 0
        arr = np.array(boxes)  # (N, 4)
        widths = arr[:, 2] - arr[:, 0]
        heights = arr[:, 3] - arr[:, 1]
        w_med = float(np.median(widths)) if len(widths) else 1.0
        h_med = float(np.median(heights)) if len(heights) else 1.0
        cxs = (arr[:, 0] + arr[:, 2]) / 2
        cys = (arr[:, 1] + arr[:, 3]) / 2

        def count_lines(values: np.ndarray, cell_size: float) -> int:
            sv = np.sort(values)
            if len(sv) == 0:
                return 0
            thr = cell_size * 0.5
            lines = 1
            last = sv[0]
            for v in sv[1:]:
                if v - last > thr:
                    lines += 1
                    last = v
                else:
                    last = (last + v) / 2  # soft update
            return lines

        cols = count_lines(cxs, w_med)
        rows = count_lines(cys, h_med)
        return rows, cols


# ══════════════════════════════════════════════════════════════
#  기믹 Detection
# ══════════════════════════════════════════════════════════════

class GimmickDetector:
    """YOLO 기믹 탐지기 (학습된 모델 래퍼).

    새 모델 (2026-04-17): runs/gimmick_detector — 단일 클래스 `gimmick`,
    mAP50 0.75, max_det=1000.
    """

    DEFAULT_WEIGHTS = Path(
        r"E:\AI\virtual_player\yolo\pixelflow\runs\gimmick_detector\weights\best.pt"
    )

    def __init__(
        self,
        weights: Optional[Path] = None,
        classes_file: Optional[Path] = None,
        min_confidence: float = 0.4,
        max_det: int = 1000,
        use_type_classifier: bool = True,
    ):
        self.weights = Path(weights) if weights else self.DEFAULT_WEIGHTS
        self.min_conf = min_confidence
        self.max_det = max_det
        self._model = None
        self._gimmick_ids: dict[int, str] = {}
        self._load()
        # 색 기반 타입 분류기 (단일 `gimmick` → 10종 세분화)
        self._type_classifier = GimmickClassifier() if use_type_classifier else None

    def _load(self):
        if not self.weights.exists():
            print(f"[GimmickDetector] weights not found: {self.weights}")
            return
        try:
            from ultralytics import YOLO
            self._model = YOLO(str(self.weights))
            # YOLO 모델 내장 names 사용 (classes.txt 불필요)
            self._gimmick_ids = {
                i: name for i, name in self._model.names.items()
                if "gimik" in name.lower() or "gimmick" in name.lower()
            }
        except Exception as e:
            print(f"[GimmickDetector] load failed: {e}")

    @property
    def gimmick_types(self) -> list[str]:
        """YOLO가 탐지할 수 있는 기믹 클래스명 목록."""
        return list(self._gimmick_ids.values())

    def detect(self, img_bgr: np.ndarray) -> list[dict]:
        """이미지에서 기믹 탐지.

        Returns:
            [{'type': str, 'bbox': (x1,y1,x2,y2), 'conf': float}, ...]
        """
        if self._model is None:
            return []

        results = self._model(
            img_bgr, verbose=False,
            conf=self.min_conf, max_det=self.max_det,
        )
        gimmicks = []
        for box in results[0].boxes:
            cid = int(box.cls)
            if cid not in self._gimmick_ids:
                continue
            conf = float(box.conf)
            if conf < self.min_conf:
                continue
            x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
            bbox = (int(x1), int(y1), int(x2), int(y2))
            # 세부 타입 분류 (색 기반)
            if self._type_classifier is not None and self._type_classifier.signatures:
                type_name, type_dist = self._type_classifier.classify(img_bgr, bbox)
            else:
                type_name = self._gimmick_ids[cid]
                type_dist = 0.0
            gimmicks.append({
                "type": type_name,
                "type_distance": round(type_dist, 1),
                "bbox": bbox,
                "conf": conf,
            })
        return gimmicks


# ══════════════════════════════════════════════════════════════
#  Hybrid Level Extractor
# ══════════════════════════════════════════════════════════════

def extract_level(
    img_path: str | Path,
    profile: dict,
    level_num: int = 1,
    gimmick_detector: Optional[GimmickDetector] = None,
    cell_detector: Optional[CellDetector] = None,
) -> dict:
    """단일 이미지에서 레벨 데이터 추출.

    파이프라인:
      1. 보드 크롭 (YOLO)
      2. 그리드 차원 탐지 (FFT)
      3. 셀 색상 분류 (픽셀)
      4. 기믹 탐지 (YOLO)
      5. 표준 Level JSON 생성

    Returns:
        {
          level_number, level_id,
          field_rows, field_columns, total_cells,
          num_colors, color_distribution,
          gimmicks: {<type>: count},
          gimmick_positions: [{type, x, y, conf}, ...],
          fieldmap, ...
        }
    """
    img_path = Path(img_path)
    img_bgr = cv2.imread(str(img_path))
    if img_bgr is None:
        return {"error": f"Cannot read: {img_path}"}

    # 1-3. 셀 분석 (보드 크롭 + 그리드 탐지 + 셀 색상)
    cell_result = analyze_cells(
        str(img_path), profile, level_num=level_num, auto_grid=True
    )
    if "error" in cell_result:
        return cell_result

    # 4. 기믹 탐지 (원본 이미지 + 보드 크롭 좌표 둘 다 활용)
    gimmicks_raw = []
    gimmick_counts: Counter = Counter()

    if gimmick_detector is not None:
        # 원본 이미지에서 탐지 (YOLO는 원본 해상도 학습)
        detections = gimmick_detector.detect(img_bgr)

        # 보드 영역 내 기믹만 필터
        crop_x, crop_y, crop_w, crop_h = cell_result["crop_rect"]
        board_x1 = crop_x
        board_y1 = crop_y
        board_x2 = crop_x + crop_w
        board_y2 = crop_y + crop_h

        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            # 기믹 중심점이 보드 영역 내에 있는지
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            if not (board_x1 <= cx <= board_x2 and board_y1 <= cy <= board_y2):
                continue
            gimmicks_raw.append(det)
            gimmick_counts[det["type"]] += 1

    # 5. 표준 Level JSON
    colors_str = cell_result.get("color_distribution", "")
    # 'c12(Blue):281 c4(Yellow):124' → 'c12:281 c4:124'
    clean_colors = " ".join(
        tok.split("(")[0] + ":" + tok.split(":")[-1]
        for tok in colors_str.split()
        if ":" in tok
    )

    # content_fieldmap에서 non-zero 셀 수 집계 (구버전 fallback)
    total_content_pixel = 0
    for line in cell_result["content_fieldmap"].split("\n"):
        for tok in line.split():
            if tok != "00":
                total_content_pixel += 1

    # YOLO cell_only로 셀 카운트 (2026-04-16 모델, 97.5% 정확)
    yolo_cell_count = None
    yolo_grid_rows = yolo_grid_cols = None
    if cell_detector is not None and cell_detector._model is not None:
        cell_boxes = cell_detector.detect(img_bgr)
        yolo_cell_count = len(cell_boxes)
        yolo_grid_rows, yolo_grid_cols = CellDetector.estimate_grid(cell_boxes)

    # 최종 값: YOLO 우선, 없으면 픽셀 fallback
    final_total_cells = yolo_cell_count if yolo_cell_count is not None else total_content_pixel
    final_rows = yolo_grid_rows if yolo_grid_rows else cell_result["grid_rows"]
    final_cols = yolo_grid_cols if yolo_grid_cols else cell_result["grid_cols"]

    return {
        "level_number": level_num,
        "level_id": f"L{level_num:04d}",
        "pkg": (level_num - 1) // 50 + 1,
        "pos": (level_num - 1) % 50 + 1,
        "chapter": (level_num - 1) // 250 + 1,

        # 그리드 차원 (YOLO bbox 분포 기반, FFT fallback)
        "field_rows": final_rows,
        "field_columns": final_cols,
        "total_cells": final_total_cells,
        "grid_confidence": cell_result.get("grid_confidence", 0.0),

        # 참고값 (두 방식 비교용)
        "total_cells_yolo": yolo_cell_count,
        "total_cells_pixel": total_content_pixel,
        "grid_rows_pixel": cell_result["grid_rows"],
        "grid_cols_pixel": cell_result["grid_cols"],

        # 셀 색상 (픽셀 분석)
        "num_colors": cell_result["num_colors"],
        "color_distribution": clean_colors,

        # 기믹 (YOLO)
        "gimmicks": dict(gimmick_counts),
        "gimmick_types_available": (
            gimmick_detector.gimmick_types if gimmick_detector else []
        ),
        "gimmick_positions": [
            {
                "type": g["type"],
                "x": (g["bbox"][0] + g["bbox"][2]) // 2,
                "y": (g["bbox"][1] + g["bbox"][3]) // 2,
                "conf": round(g["conf"], 3),
                "type_distance": g.get("type_distance", 0.0),
            }
            for g in gimmicks_raw
        ],

        # FieldMap (셀 색상 그리드)
        "fieldmap": cell_result["fieldmap"],
        "content_fieldmap": cell_result["content_fieldmap"],

        # 메타
        "pixel_art_source": img_path.name,
        "extractor": "hybrid_v1",
    }


# ══════════════════════════════════════════════════════════════
#  Batch 처리
# ══════════════════════════════════════════════════════════════

def extract_batch(
    img_paths: list[Path],
    profile_path: Path,
    output_dir: Path,
    level_offset: int = 1,
) -> list[dict]:
    """여러 이미지 일괄 추출."""
    profile = load_profile(str(profile_path))
    detector = GimmickDetector()

    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for i, img_path in enumerate(img_paths):
        level_num = level_offset + i
        result = extract_level(img_path, profile, level_num, detector)

        if "error" not in result:
            # JSON 저장
            out_path = output_dir / f"level_{level_num:03d}.json"
            out_path.write_text(
                json.dumps(result, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        results.append(result)

    return results


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?", help="단일 이미지 테스트")
    ap.add_argument("--level", type=int, default=1)
    ap.add_argument(
        "--profile",
        default=r"E:\AI\virtual_player\data\pixelflow\profile\cell_profile.json",
    )
    ap.add_argument("--no-gimmick", action="store_true", help="기믹 탐지 비활성화")
    args = ap.parse_args()

    if not args.image:
        print("Usage: python hybrid_extractor.py <image> [--level N]")
        sys.exit(1)

    profile = load_profile(args.profile)
    detector = None if args.no_gimmick else GimmickDetector()

    result = extract_level(args.image, profile, args.level, detector)

    # 보기 좋게 출력 (fieldmap은 축약)
    preview = dict(result)
    if "fieldmap" in preview:
        preview["fieldmap"] = preview["fieldmap"][:200] + "..." if len(preview["fieldmap"]) > 200 else preview["fieldmap"]
    if "content_fieldmap" in preview:
        preview["content_fieldmap"] = preview["content_fieldmap"][:200] + "..." if len(preview["content_fieldmap"]) > 200 else preview["content_fieldmap"]

    print(json.dumps(preview, indent=2, ensure_ascii=False))
