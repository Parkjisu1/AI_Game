"""
OCRReader — Text/Number Extraction from Screen Regions
=======================================================
PaddleOCR → pytesseract 순으로 폴백.
엔진 없으면 빈 결과 반환 (크래시 없음).
"""

import re
from typing import Dict, Optional, Tuple

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
            log("  [OCRReader] No OCR engine available — returning empty readings")

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        OCR 정확도 향상을 위한 전처리:
        grayscale → 2x 업스케일 → adaptive threshold
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
        elif self._engine == "tesseract":
            raw_text, confidence = self._run_tesseract(processed)
        else:
            return reading

        reading.raw_text = raw_text.strip()
        reading.confidence = confidence
        return reading

    def _run_paddle(self, img: np.ndarray) -> Tuple[str, float]:
        """PaddleOCR 실행 — (text, confidence) 반환."""
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

    def _run_tesseract(self, img: np.ndarray) -> Tuple[str, float]:
        """pytesseract 실행 — (text, confidence) 반환."""
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
        - "1.2K" → 1200.0
        - "3.5M" → 3500000.0
        - "12,345" → 12345.0
        - "42" → 42.0
        - 파싱 불가 → None
        """
        if not text:
            return None

        text = text.strip().replace(",", "")

        # K/M/B 단위 처리 (대소문자 무관)
        multiplier = 1.0
        if text.upper().endswith("K"):
            multiplier = 1_000.0
            text = text[:-1]
        elif text.upper().endswith("M"):
            multiplier = 1_000_000.0
            text = text[:-1]
        elif text.upper().endswith("B"):
            multiplier = 1_000_000_000.0
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

    def read_all(
        self,
        image: np.ndarray,
        ocr_regions: Dict[str, dict],
    ) -> Dict[str, OCRReading]:
        """
        설정 딕셔너리에 정의된 모든 OCR 영역을 읽는다.

        Args:
            image: BGR 스크린샷
            ocr_regions: {name: {"region": [x,y,w,h], "numeric": true/false, "name": "gold"}}

        Returns:
            {region_name: OCRReading}
        """
        results: Dict[str, OCRReading] = {}

        for key, cfg in ocr_regions.items():
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
