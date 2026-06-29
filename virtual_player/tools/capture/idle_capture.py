"""
Idle Capture — OCR 숫자 추적 + Value Delta
============================================
방치형/Idle 게임용 캡처 엔진.

핵심 차이점:
  화면 변화(픽셀 Delta)가 아닌 **수치 변화(Value Delta)**를 추적.
  - 자동 생산, 타이머, 파티클 등 상시 애니메이션 → 픽셀 Delta 무의미
  - 대신 OCR로 재화/수치 영역을 읽어서 Before/After 값 비교
  - "내 탭이 어떤 수치를 얼마나 바꿨는가"를 기록

구조:
  1. value_regions: OCR로 읽을 영역 정의 {name: (x, y, w, h)}
  2. mask_regions: 애니메이션 영역 → 픽셀 Delta 계산에서 제외
  3. Before: 탭 직전 OCR 스냅샷 (모든 value_regions)
  4. After: 탭 후 OCR 스냅샷
  5. Value Delta: {region_name: after_value - before_value}

JSONL 추가 필드:
  - values_before: {name: "1,234,567"} (OCR 원본 텍스트)
  - values_after: {name: "1,234,890"}
  - value_deltas: {name: 323} (숫자 파싱 후 차이)
  - masked_pixel_delta: 마스크 적용 후 픽셀 Delta (UI 변화만)
"""

import io
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from .base import (
    ADBConnection,
    BaseCaptureEngine,
    SessionManager,
    compute_pixel_delta,
)

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# OCR 엔진은 lazy init — import 시 7초+ 지연 방지
_ocr_initialized = False
_HAS_TESSERACT = False
_HAS_PADDLE = False
_HAS_EASYOCR = False
_paddle_ocr = None
_easyocr_reader = None


def _init_ocr():
    """OCR 엔진 초기화 (첫 사용 시 1회만)."""
    global _ocr_initialized, _HAS_TESSERACT, _HAS_PADDLE, _HAS_EASYOCR
    global _paddle_ocr, _easyocr_reader
    if _ocr_initialized:
        return
    _ocr_initialized = True

    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        _HAS_TESSERACT = True
    except Exception:
        pass

    try:
        from paddleocr import PaddleOCR
        _paddle_ocr = PaddleOCR(use_angle_cls=False, lang="en", show_log=False)
        _HAS_PADDLE = True
    except Exception:
        pass

    try:
        import easyocr
        _easyocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        _HAS_EASYOCR = True
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# OCR Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _ocr_region(img_bytes: bytes, region: Tuple[int, int, int, int]) -> str:
    """이미지 bytes에서 특정 영역의 텍스트를 OCR로 추출."""
    _init_ocr()
    if not _HAS_PIL:
        return ""
    try:
        img = Image.open(io.BytesIO(img_bytes))
        rx, ry, rw, rh = region
        crop = img.crop((rx, ry, rx + rw, ry + rh))

        # 전처리: 2배 확대 + 그레이스케일 (OCR 정확도 향상)
        crop = crop.resize((rw * 2, rh * 2), Image.LANCZOS).convert("L")

        if _HAS_PADDLE:
            import numpy as np
            arr = np.array(crop)
            result = _paddle_ocr.ocr(arr, cls=False)
            if result and result[0]:
                texts = [line[1][0] for line in result[0] if line[1]]
                return " ".join(texts).strip()
            return ""

        if _HAS_EASYOCR:
            import numpy as np
            arr = np.array(crop)
            result = _easyocr_reader.readtext(arr, detail=0)
            return " ".join(result).strip() if result else ""

        if _HAS_TESSERACT:
            text = pytesseract.image_to_string(crop, config="--psm 7 -c tessedit_char_whitelist=0123456789,.$%KMBkmb ")
            return text.strip()

        return ""
    except Exception:
        return ""


def _parse_number(text: str) -> Optional[float]:
    """
    OCR 텍스트에서 숫자 파싱.
    '1,234,567' → 1234567
    '12.5K' → 12500
    '1.2M' → 1200000
    '$99.99' → 99.99
    """
    if not text:
        return None
    cleaned = text.replace(",", "").replace("$", "").replace(" ", "").strip()
    if not cleaned:
        return None

    multiplier = 1.0
    suffix = cleaned[-1].upper()
    if suffix == "K":
        multiplier = 1_000
        cleaned = cleaned[:-1]
    elif suffix == "M":
        multiplier = 1_000_000
        cleaned = cleaned[:-1]
    elif suffix == "B":
        multiplier = 1_000_000_000
        cleaned = cleaned[:-1]

    # 숫자만 추출
    match = re.search(r"[\d.]+", cleaned)
    if match:
        try:
            return float(match.group()) * multiplier
        except ValueError:
            pass
    return None


def _ocr_all_regions(img_bytes: bytes,
                     regions: Dict[str, Tuple[int, int, int, int]]) -> Dict[str, str]:
    """모든 value_regions에 대해 OCR 수행."""
    results = {}
    for name, region in regions.items():
        results[name] = _ocr_region(img_bytes, region)
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Masked Pixel Delta
# ─────────────────────────────────────────────────────────────────────────────

def _compute_masked_delta(img_a: bytes, img_b: bytes,
                          mask_regions: List[Tuple[int, int, int, int]],
                          threshold: int = 25) -> float:
    """
    마스크 영역을 제외한 픽셀 Delta.
    mask_regions: 애니메이션/변동 영역 → 검은색으로 채워서 비교에서 제외.
    """
    if not _HAS_PIL or not img_a or not img_b:
        return -1.0
    try:
        a = Image.open(io.BytesIO(img_a)).convert("L")
        b = Image.open(io.BytesIO(img_b)).convert("L")

        # 마스크 영역 → 동일 값으로 채움 (비교에서 제외)
        for rx, ry, rw, rh in mask_regions:
            for img in (a, b):
                pixels = img.load()
                for mx in range(rx, min(rx + rw, img.width)):
                    for my in range(ry, min(ry + rh, img.height)):
                        pixels[mx, my] = 0

        a = a.resize((270, 480))
        b = b.resize((270, 480))
        pa, pb = list(a.getdata()), list(b.getdata())
        diff = sum(1 for x, y in zip(pa, pb) if abs(x - y) > threshold)
        return round(diff / len(pa), 4)
    except Exception:
        return -1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Idle Capture Engine
# ═══════════════════════════════════════════════════════════════════════════════

class IdleCaptureEngine(BaseCaptureEngine):
    """
    Idle/방치형 장르: OCR Value Delta 기반 캡처.

    설정:
        value_regions: OCR 추적 영역 {name: (x, y, w, h)}
        mask_regions: 애니메이션 마스크 영역 [(x, y, w, h), ...]
        after_delay: After 캡처 대기 시간 (초)
        continuous_interval: 자동 스냅샷 주기 (초, 0이면 비활성)
    """

    GENRE = "idle"

    def __init__(self, adb: ADBConnection, session: SessionManager, **kwargs):
        super().__init__(adb, session, kwargs.get("log_fn"))
        self.value_regions: Dict[str, Tuple[int, int, int, int]] = kwargs.get("value_regions", {})
        self.mask_regions: List[Tuple[int, int, int, int]] = kwargs.get("mask_regions", [])
        self.after_delay: float = kwargs.get("after_delay", 1.0)
        self.continuous_interval: float = kwargs.get("continuous_interval", 0.0)

        # 상태: 마지막으로 읽은 값들
        self._last_values: Dict[str, str] = {}
        self._last_parsed: Dict[str, Optional[float]] = {}
        self._ocr_engine = "none"

    def on_start(self):
        self.detect_resolution()
        self.prev_frame_bytes = b""

        # OCR 엔진 lazy init (여기서 처음 로딩)
        _init_ocr()

        # OCR 엔진 확인
        if _HAS_PADDLE:
            self._ocr_engine = "PaddleOCR"
        elif _HAS_EASYOCR:
            self._ocr_engine = "EasyOCR"
        elif _HAS_TESSERACT:
            self._ocr_engine = "Tesseract"
        else:
            self._ocr_engine = "none"

        self.log(f"[Idle] Capture started  OCR={self._ocr_engine}", tag="accent")
        self.log(f"[Idle] Value regions: {list(self.value_regions.keys())}")
        self.log(f"[Idle] Mask regions: {len(self.mask_regions)} areas")
        if self.continuous_interval > 0:
            self.log(f"[Idle] Auto-snapshot every {self.continuous_interval}s")

        if self._ocr_engine == "none":
            self.log("[Idle] WARNING: No OCR engine — value tracking disabled", tag="error")

        # 초기 스냅샷으로 현재 값 기록
        if self.value_regions and self._ocr_engine != "none":
            initial = self.adb.screenshot_bytes()
            if initial:
                self._last_values = _ocr_all_regions(initial, self.value_regions)
                self._last_parsed = {
                    k: _parse_number(v) for k, v in self._last_values.items()
                }
                self.log(f"[Idle] Initial values: {self._last_values}")

    def on_stop(self):
        self.log(f"[Idle] Capture stopped")

    def process_event(self, evt: dict):
        """Idle 캡처: OCR Before → (탭) → (대기) → OCR After → Value Delta."""
        app_dir = self.session.app_dir
        seq = self.session.record_action()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ── Before Screenshot + OCR ──
        before_bytes = self.adb.screenshot_bytes()
        if not before_bytes:
            self.log(f"[{self.session.app_label}] #{seq} FAILED", tag="error")
            return

        before_name = f"idle_{ts}_{seq:04d}_before.png"
        (app_dir / before_name).write_bytes(before_bytes)

        values_before = {}
        if self.value_regions and self._ocr_engine != "none":
            values_before = _ocr_all_regions(before_bytes, self.value_regions)

        # ── After Screenshot + OCR (대기 후) ──
        time.sleep(self.after_delay)
        after_bytes = self.adb.screenshot_bytes()
        after_name = None
        values_after = {}

        if after_bytes:
            after_name = f"idle_{ts}_{seq:04d}_after.png"
            (app_dir / after_name).write_bytes(after_bytes)
            self.session.total_captures += 1

            if self.value_regions and self._ocr_engine != "none":
                values_after = _ocr_all_regions(after_bytes, self.value_regions)

        # ── Value Delta 계산 ──
        value_deltas = {}
        for name in self.value_regions:
            before_num = _parse_number(values_before.get(name, ""))
            after_num = _parse_number(values_after.get(name, ""))
            if before_num is not None and after_num is not None:
                value_deltas[name] = round(after_num - before_num, 2)

        # ── Masked Pixel Delta (애니메이션 제외한 UI 변화) ──
        masked_delta = None
        if after_bytes and self.mask_regions:
            masked_delta = _compute_masked_delta(
                before_bytes, after_bytes, self.mask_regions)

        # 이전 프레임 대비 delta (참고용)
        delta_prev = compute_pixel_delta(self.prev_frame_bytes, before_bytes)
        self.prev_frame_bytes = before_bytes

        # ── Log ──
        action_str = self.format_action(evt)
        parts = [f"[{self.session.app_label}] #{seq}  {action_str}"]
        if value_deltas:
            changed = {k: v for k, v in value_deltas.items() if v != 0}
            if changed:
                parts.append(f"value_delta={changed}")
            else:
                parts.append("no value change")
        if masked_delta is not None and masked_delta >= 0:
            parts.append(f"ui_delta={masked_delta:.2%}")
        self.log("  ".join(parts))

        # ── JSONL ──
        entry = self.build_base_entry(evt, seq, before_name, after_name)
        entry["values_before"] = values_before if values_before else None
        entry["values_after"] = values_after if values_after else None
        entry["value_deltas"] = value_deltas if value_deltas else None
        entry["masked_pixel_delta"] = masked_delta if masked_delta and masked_delta >= 0 else None
        entry["delta_from_prev"] = delta_prev if delta_prev >= 0 else None
        entry["ocr_engine"] = self._ocr_engine

        self.session.write_log(entry)

        # 마지막 값 업데이트
        if values_after:
            self._last_values = values_after
            self._last_parsed = {
                k: _parse_number(v) for k, v in values_after.items()
            }

    def take_auto_snapshot(self) -> Optional[dict]:
        """
        액션 없이 자동 스냅샷 — 생산율 추적용.
        continuous_interval > 0일 때 capture loop에서 주기적 호출.
        """
        if not self.value_regions or self._ocr_engine == "none":
            return None

        img = self.adb.screenshot_bytes()
        if not img:
            return None

        current = _ocr_all_regions(img, self.value_regions)
        parsed = {k: _parse_number(v) for k, v in current.items()}

        deltas = {}
        for name in self.value_regions:
            prev = self._last_parsed.get(name)
            curr = parsed.get(name)
            if prev is not None and curr is not None:
                deltas[name] = round(curr - prev, 2)

        # 스냅샷 로그
        entry = {
            "event": "auto_snapshot",
            "genre": self.GENRE,
            "episode_id": self.session.episode_id,
            "timestamp": datetime.now().isoformat(),
            "app": self.session.current_app,
            "values": current,
            "auto_deltas": deltas if deltas else None,
        }
        self.session.write_log(entry)

        self._last_values = current
        self._last_parsed = parsed

        changed = {k: v for k, v in deltas.items() if v != 0}
        if changed:
            self.log(f"[Idle] Auto-snap: {changed}", tag="info")

        return entry
