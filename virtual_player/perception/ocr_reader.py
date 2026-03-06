"""
OCRReader -- Text/Number Extraction from Screen Regions
=======================================================
PaddleOCR -> pytesseract 순으로 폴백.
엔진 없으면 빈 결과 반환 (크래시 없음).
"""

import re
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

from .game_state import OCRReading
from ..adb import log


class OCRReader:
    """멀티 엔진 OCR 리더 (PaddleOCR / Tesseract / None)."""

    def __init__(self):
        self._engine: Optional[str] = None
        self._paddle = None
        self._tesseract_available = False

        # PaddleOCR 우선 시도
        try:
            from paddleocr import PaddleOCR  # type: ignore
            self._paddle = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
            self._engine = "paddle"
            log("  [OCRReader] Engine: PaddleOCR")
        except Exception:
            pass

        # fallback: EasyOCR
        if self._engine is None:
            try:
                import easyocr  # type: ignore
                self._easyocr = easyocr.Reader(["en"], gpu=False, verbose=False)
                self._engine = "easyocr"
                log("  [OCRReader] Engine: EasyOCR")
            except Exception:
                self._easyocr = None

        # fallback: pytesseract
        if self._engine is None:
            try:
                import pytesseract  # type: ignore
                pytesseract.get_tesseract_version()
                self._tesseract_available = True
                self._engine = "tesseract"
                log("  [OCRReader] Engine: Tesseract")
            except Exception:
                pass

        if self._engine is None:
            log("  [OCRReader] No OCR engine available -- returning empty readings")

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        OCR 정확도 향상을 위한 전처리:
        grayscale -> 2x 업스케일 -> adaptive threshold
        """
        if not _CV2_AVAILABLE:
            return image

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # 2배 업스케일
        h, w = gray.shape
        resized = cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_LINEAR)
        # Adaptive threshold (텍스트/배경 분리)
        processed = cv2.adaptiveThreshold(
            resized, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,
            C=2,
        )
        return processed

    def read_text(
        self,
        image: np.ndarray,
        region: Tuple[int, int, int, int],
    ) -> OCRReading:
        """
        지정 ROI에서 텍스트를 읽는다.

        Args:
            image: BGR 전체 스크린샷
            region: (x, y, w, h)

        Returns:
            OCRReading
        """
        x, y, w, h = region
        reading = OCRReading(name="", region=region)

        if self._engine is None or not _CV2_AVAILABLE:
            return reading

        if w <= 0 or h <= 0:
            return reading

        roi = image[y:y + h, x:x + w]
        if roi.size == 0:
            return reading

        processed = self._preprocess(roi)

        if self._engine == "paddle":
            raw_text, confidence = self._run_paddle(processed)
        elif self._engine == "easyocr":
            raw_text, confidence = self._run_easyocr(roi)  # EasyOCR uses original color image
        elif self._engine == "tesseract":
            raw_text, confidence = self._run_tesseract(processed)
        else:
            return reading

        reading.raw_text = raw_text.strip()
        reading.confidence = confidence
        return reading

    def _run_paddle(self, img: np.ndarray) -> Tuple[str, float]:
        """PaddleOCR 실행 -- (text, confidence) 반환."""
        try:
            # PaddleOCR은 BGR 이미지를 받으므로, grayscale이면 3채널로 변환
            if len(img.shape) == 2 and _CV2_AVAILABLE:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            result = self._paddle.ocr(img, cls=False)
            if not result or not result[0]:
                return "", 0.0
            # 모든 텍스트 라인을 합치고 평균 신뢰도 계산
            texts = []
            confs = []
            for line in result[0]:
                if line and len(line) >= 2:
                    text_info = line[1]
                    texts.append(text_info[0])
                    confs.append(float(text_info[1]))
            combined = " ".join(texts)
            avg_conf = sum(confs) / len(confs) if confs else 0.0
            return combined, avg_conf
        except Exception as e:
            log(f"  [OCRReader] PaddleOCR error: {e}")
            return "", 0.0

    # EasyOCR segfaults on images taller than ~960px on some systems (PyTorch issue).
    _EASYOCR_MAX_DIM = 960

    def _safe_easyocr_resize(self, img: np.ndarray) -> Tuple[np.ndarray, float]:
        """Resize image for safe EasyOCR processing. Returns (image, scale_factor)."""
        h, w = img.shape[:2]
        # Upscale tiny images
        if _CV2_AVAILABLE and (h < 80 or w < 200):
            img = cv2.resize(img, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
            return img, 3.0
        # Downscale large images to prevent segfault
        max_dim = max(h, w)
        if _CV2_AVAILABLE and max_dim > self._EASYOCR_MAX_DIM:
            scale = self._EASYOCR_MAX_DIM / max_dim
            new_w, new_h = int(w * scale), int(h * scale)
            img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
            return img, scale
        return img, 1.0

    def _run_easyocr(self, img: np.ndarray) -> Tuple[str, float]:
        """EasyOCR 실행 -- (text, confidence) 반환. 작은 이미지는 3x 업스케일."""
        try:
            img, _ = self._safe_easyocr_resize(img)
            results = self._easyocr.readtext(img, detail=1, paragraph=False)
            if not results:
                return "", 0.0
            texts = []
            confs = []
            for (bbox, text, conf) in results:
                texts.append(text)
                confs.append(float(conf))
            combined = " ".join(texts)
            avg_conf = sum(confs) / len(confs) if confs else 0.0
            return combined, avg_conf
        except Exception as e:
            log(f"  [OCRReader] EasyOCR error: {e}")
            return "", 0.0

    def _run_tesseract(self, img: np.ndarray) -> Tuple[str, float]:
        """pytesseract 실행 -- (text, confidence) 반환."""
        try:
            import pytesseract  # type: ignore
            # 숫자/영어 전용 설정
            config = "--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,KMkm%+"
            data = pytesseract.image_to_data(img, config=config, output_type=pytesseract.Output.DICT)
            texts = []
            confs = []
            for i, txt in enumerate(data["text"]):
                if txt.strip():
                    texts.append(txt.strip())
                    confs.append(float(data["conf"][i]))
            combined = " ".join(texts)
            avg_conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
            return combined, avg_conf
        except Exception as e:
            log(f"  [OCRReader] Tesseract error: {e}")
            return "", 0.0

    def _parse_numeric(self, text: str) -> Optional[float]:
        """
        텍스트를 숫자로 파싱.
        - "Lv.23" -> 23.0
        - "1.2K" -> 1200.0
        - "3.5M" -> 3500000.0
        - "12,345" -> 12345.0
        - "14,606A" -> 14606.0 (A는 무시)
        - "42" -> 42.0
        - 파싱 불가 -> None
        """
        if not text:
            return None

        text = text.strip()

        # "Lv.23" / "LV23" 패턴 처리
        lv_match = re.search(r"[Ll][Vv]\.?\s*(\d+)", text)
        if lv_match:
            return float(lv_match.group(1))

        # 콤마와 공백 제거 (OCR이 "5 470"을 반환하는 경우)
        text = text.replace(",", "").replace(" ", "")
        # 마침표가 천 단위 구분자인지 소수점인지 판별
        # "14.606" 같은 건 천 단위 구분자일 가능성 높음 (소수점 뒤 3자리)
        dot_match = re.match(r"^(\d+)\.(\d{3})(\D|$)", text)
        if dot_match:
            text = dot_match.group(1) + dot_match.group(2) + text[dot_match.end(2):]

        # K/M/B/A 단위 처리 (대소문자 무관)
        multiplier = 1.0
        upper = text.upper()
        if upper.endswith("K"):
            multiplier = 1_000.0
            text = text[:-1]
        elif upper.endswith("M"):
            multiplier = 1_000_000.0
            text = text[:-1]
        elif upper.endswith("B"):
            multiplier = 1_000_000_000.0
            text = text[:-1]
        elif upper.endswith("A"):
            # A 단위 (Ash & Veil 등 게임 특유 표기, 무시)
            text = text[:-1]

        # 숫자 추출
        match = re.search(r"[\d.]+", text)
        if not match:
            return None

        try:
            value = float(match.group()) * multiplier
            return value
        except ValueError:
            return None

    def read_combined(
        self,
        image: np.ndarray,
        combined_region: Tuple[int, int, int, int],
        field_map: Dict[str, dict],
    ) -> Dict[str, OCRReading]:
        """
        넓은 영역을 한 번에 OCR한 뒤, x좌표로 필드를 분류.
        작은 개별 ROI보다 정확도가 훨씬 높음 (EasyOCR 특성).

        Args:
            image: BGR 스크린샷
            combined_region: (x, y, w, h) -- 전체 OCR 대상 영역
            field_map: {name: {"x_range": [x_min, x_max], "numeric": bool, "category": str}}

        Returns:
            {field_name: OCRReading}
        """
        results: Dict[str, OCRReading] = {}
        if self._engine is None or not _CV2_AVAILABLE:
            return results

        x, y, w, h = combined_region
        if w <= 0 or h <= 0:
            return results

        roi = image[y:y + h, x:x + w]
        if roi.size == 0:
            return results

        # 3x 업스케일 후 OCR (단, EasyOCR 안전 한도 초과 시 축소)
        rh, rw = roi.shape[:2]
        scale = 3
        target_h, target_w = rh * scale, rw * scale
        max_dim = max(target_h, target_w)
        if max_dim > self._EASYOCR_MAX_DIM:
            scale = self._EASYOCR_MAX_DIM / max(rh, rw)
            target_h, target_w = int(rh * scale), int(rw * scale)
        upscaled = cv2.resize(roi, (target_w, target_h), interpolation=cv2.INTER_CUBIC)

        detections = []
        if self._engine == "easyocr":
            try:
                raw_results = self._easyocr.readtext(upscaled, detail=1, paragraph=False)
                for (bbox, text, conf) in raw_results:
                    # bbox 좌표를 원본 스케일로 변환 (combined_region 기준)
                    cx = int((bbox[0][0] + bbox[2][0]) / 2) // scale + x
                    detections.append((cx, text, float(conf)))
            except Exception as e:
                log(f"  [OCRReader] Combined OCR error: {e}")
        elif self._engine == "paddle":
            try:
                if len(upscaled.shape) == 2:
                    upscaled = cv2.cvtColor(upscaled, cv2.COLOR_GRAY2BGR)
                raw_results = self._paddle.ocr(upscaled, cls=False)
                if raw_results and raw_results[0]:
                    for line in raw_results[0]:
                        if line and len(line) >= 2:
                            bbox = line[0]
                            cx = int((bbox[0][0] + bbox[2][0]) / 2) // scale + x
                            detections.append((cx, line[1][0], float(line[1][1])))
            except Exception as e:
                log(f"  [OCRReader] Combined OCR error: {e}")

        # x좌표로 필드에 매핑
        for fname, fcfg in field_map.items():
            x_range = fcfg.get("x_range", [0, 9999])
            is_numeric = fcfg.get("numeric", False)

            best_text = ""
            best_conf = 0.0

            for cx, text, conf in detections:
                if x_range[0] <= cx <= x_range[1]:
                    if conf > best_conf:
                        best_text = text
                        best_conf = conf

            reading = OCRReading(name=fname, region=combined_region)
            reading.raw_text = best_text.strip()
            reading.confidence = best_conf
            if is_numeric and reading.raw_text:
                reading.parsed_value = self._parse_numeric(reading.raw_text)
            results[fname] = reading

        return results

    def read_all(
        self,
        image: np.ndarray,
        ocr_regions: Dict[str, dict],
    ) -> Dict[str, OCRReading]:
        """
        설정 딕셔너리에 정의된 모든 OCR 영역을 읽는다.
        _combined 키가 있으면 결합 OCR을 우선 사용.

        Args:
            image: BGR 스크린샷
            ocr_regions: {name: {"region": [x,y,w,h], "numeric": true/false, ...}}
                         특수 키 "_combined": {"region": [...], "fields": {...}} 로 결합 OCR 지원

        Returns:
            {region_name: OCRReading}
        """
        results: Dict[str, OCRReading] = {}

        # 결합 OCR 처리
        combined_cfg = ocr_regions.get("_combined")
        if combined_cfg:
            combined_region = tuple(combined_cfg.get("region", [0, 0, 0, 0]))
            field_map = combined_cfg.get("fields", {})
            if len(combined_region) == 4 and field_map:
                results.update(self.read_combined(image, combined_region, field_map))

        # 개별 ROI 처리 (결합 OCR로 이미 읽은 필드는 건너뜀)
        for key, cfg in ocr_regions.items():
            if key == "_combined" or key in results:
                continue

            region_list = cfg.get("region", [0, 0, 0, 0])
            region = tuple(region_list)
            if len(region) != 4:
                continue

            is_numeric = cfg.get("numeric", False)
            display_name = cfg.get("name", key)

            reading = self.read_text(image, region)
            reading.name = display_name

            if is_numeric and reading.raw_text:
                reading.parsed_value = self._parse_numeric(reading.raw_text)

            results[key] = reading

        return results

    def read_full_screen(
        self,
        image: np.ndarray,
        languages: Optional[List[str]] = None,
    ) -> List[Tuple[str, float, int, int]]:
        """
        Run OCR on the full screen image and return all detected text with positions.

        Args:
            image: BGR full screenshot.
            languages: Language codes (ignored if engine doesn't support).

        Returns:
            List of (text, confidence, y_center, x_center) tuples.
        """
        results: List[Tuple[str, float, int, int]] = []

        if self._engine is None:
            return results

        try:
            if self._engine == "easyocr":
                resized, scale = self._safe_easyocr_resize(image)
                raw = self._easyocr.readtext(resized, detail=1, paragraph=False)
                inv_scale = 1.0 / scale if scale != 0 else 1.0
                for bbox, text, conf in raw:
                    cx = int((bbox[0][0] + bbox[2][0]) / 2 * inv_scale)
                    cy = int((bbox[0][1] + bbox[2][1]) / 2 * inv_scale)
                    results.append((text, float(conf), cy, cx))
            elif self._engine == "paddle":
                if _CV2_AVAILABLE and len(image.shape) == 2:
                    image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
                raw = self._paddle.ocr(image, cls=False)
                if raw and raw[0]:
                    for line in raw[0]:
                        if line and len(line) >= 2:
                            bbox = line[0]
                            cx = int((bbox[0][0] + bbox[2][0]) / 2)
                            cy = int((bbox[0][1] + bbox[2][1]) / 2)
                            results.append((line[1][0], float(line[1][1]), cy, cx))
            elif self._engine == "tesseract":
                import pytesseract  # type: ignore
                data = pytesseract.image_to_data(
                    image, output_type=pytesseract.Output.DICT)
                for i, txt in enumerate(data["text"]):
                    if txt.strip():
                        cx = data["left"][i] + data["width"][i] // 2
                        cy = data["top"][i] + data["height"][i] // 2
                        conf = float(data["conf"][i]) / 100.0
                        results.append((txt.strip(), conf, cy, cx))
        except Exception as e:
            log(f"  [OCRReader] read_full_screen error: {e}")

        return results
