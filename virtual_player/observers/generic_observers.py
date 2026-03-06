"""
Generic Observers -- Genre-Independent Parameter Observers
==========================================================
UI, Economy, Monetization, Progression observers that work across all game genres.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .base import ObserverBase, ScreenCaptureFn

logger = logging.getLogger(__name__)

# Type alias for OCR function
OCRFn = Callable[[Path], List[Tuple[str, float, int, int]]]


class UIObserver(ObserverBase):
    """Observes UI layout: screen resolution, nav bar structure, screen states."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[OCRFn] = None,
        detect_screen_fn: Optional[Callable] = None,
        screen_width: int = 1080,
        screen_height: int = 1920,
    ):
        super().__init__(1, "UIMapping", "ux", capture_fn, observations)
        self._ocr = ocr_fn
        self._detect_screen = detect_screen_fn
        self._screen_width = screen_width
        self._screen_height = screen_height

    def run(self) -> None:
        self.observe("screen_resolution",
                     f"{self._screen_width}x{self._screen_height}",
                     confidence=1.0,
                     notes="Device resolution")

        p = self.screenshot("ui_scan")
        if not p:
            return

        # Count nav bar icons via pixel analysis
        try:
            from PIL import Image
            import numpy as np
            img = Image.open(p)
            arr = np.array(img)
            nav_y = int(self._screen_height * 0.94)
            if nav_y < arr.shape[0]:
                nav_row = arr[nav_y, :, :]
                # Count icon transitions via saturation
                count = self._count_nav_icons(nav_row)
                self.observe("nav_bar_icons_count", count, confidence=0.7,
                             notes=f"Pixel-scanned nav bar at y={nav_y}")
        except Exception as e:
            logger.debug("Nav icon scan failed: %s", e)

        # OCR for screen text
        if self._ocr and p:
            texts = self._ocr(p)
            if texts:
                self.observe("ui_text_sample", [t[0] for t in texts[:10]],
                             confidence=0.6, notes="First 10 OCR text items")

    def _count_nav_icons(self, nav_row) -> int:
        """Count nav bar icons by scanning for color transitions."""
        import numpy as np
        # Convert to HSV-like saturation check
        r, g, b = nav_row[:, 0], nav_row[:, 1], nav_row[:, 2]
        max_c = np.maximum(np.maximum(r, g), b).astype(float)
        min_c = np.minimum(np.minimum(r, g), b).astype(float)
        saturation = np.where(max_c > 0, (max_c - min_c) / max_c * 100, 0)
        brightness = max_c / 255.0 * 100

        in_icon = False
        icon_count = 0
        gap = 0
        for i in range(len(saturation)):
            if saturation[i] > 40 and brightness[i] > 50:
                if not in_icon:
                    icon_count += 1
                    in_icon = True
                gap = 0
            else:
                gap += 1
                if gap > 30:
                    in_icon = False
        return icon_count


class EconomyObserver(ObserverBase):
    """Observes economy: currencies, lives, resource types."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[OCRFn] = None,
    ):
        super().__init__(2, "Economy", "economy", capture_fn, observations)
        self._ocr = ocr_fn

    def run(self) -> None:
        p = self.screenshot("economy_scan")
        if not p or not self._ocr:
            return

        texts = self._ocr(p)
        currencies = self._detect_currencies(texts)
        if currencies:
            self.observe("currency_types", currencies, confidence=0.6,
                         notes="Detected via OCR keyword matching")

        lives = self._detect_lives(texts)
        if lives is not None:
            self.observe("lives_max_count", lives, confidence=0.5,
                         notes="Estimated from OCR text")

    def _detect_currencies(self, texts: List[Tuple]) -> List[str]:
        """Detect currency types from OCR text."""
        currency_keywords = {
            "gold": ["gold", "coin", "money", "골드", "코인"],
            "gem": ["gem", "diamond", "crystal", "보석", "다이아", "크리스탈"],
            "stamina": ["stamina", "energy", "스태미나", "에너지"],
            "heart": ["heart", "life", "하트", "라이프"],
        }
        found = []
        all_text = " ".join(t[0].lower() for t in texts if isinstance(t, tuple))
        for currency, keywords in currency_keywords.items():
            if any(kw in all_text for kw in keywords):
                found.append(currency)
        return found

    def _detect_lives(self, texts: List[Tuple]) -> Optional[int]:
        """Try to detect max lives count."""
        import re
        for text, conf, _, _ in texts:
            if isinstance(text, str):
                # Match "3/5" or "♥ 5" patterns
                m = re.search(r"(\d+)\s*/\s*(\d+)", text)
                if m:
                    return int(m.group(2))
        return None


class MonetizationObserver(ObserverBase):
    """Observes monetization: ads, IAP, special offers."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[OCRFn] = None,
    ):
        super().__init__(3, "Monetization", "bm", capture_fn, observations)
        self._ocr = ocr_fn
        self._ad_count = 0
        self._levels_played = 0

    def record_ad(self) -> None:
        """Call when an ad is detected during gameplay."""
        self._ad_count += 1

    def record_level(self) -> None:
        """Call when a level is completed."""
        self._levels_played += 1

    def run(self) -> None:
        if self._levels_played > 0:
            freq = self._ad_count / self._levels_played
            self.observe("interstitial_ad_freq", round(freq, 2),
                         confidence=0.6,
                         notes=f"{self._ad_count} ads in {self._levels_played} levels")

        p = self.screenshot("monetization_scan")
        if not p or not self._ocr:
            return

        texts = self._ocr(p)
        iap = self._detect_iap(texts)
        if iap:
            self.observe("iap_packages_visible", iap, confidence=0.5,
                         notes="IAP packages detected via OCR")

    def _detect_iap(self, texts: List[Tuple]) -> List[str]:
        """Detect IAP packages from text."""
        iap_keywords = ["$", "₩", "¥", "€", "buy", "purchase", "pack", "패키지", "구매"]
        found = []
        for text, conf, _, _ in texts:
            if isinstance(text, str):
                for kw in iap_keywords:
                    if kw.lower() in text.lower():
                        found.append(text)
                        break
        return found[:5]  # Max 5 packages


class ProgressionObserver(ObserverBase):
    """Observes progression: level system, difficulty, star ratings."""

    def __init__(
        self,
        capture_fn: ScreenCaptureFn,
        observations: Dict[str, List],
        ocr_fn: Optional[OCRFn] = None,
    ):
        super().__init__(4, "Progression", "content", capture_fn, observations)
        self._ocr = ocr_fn
        self._level_stats: List[Dict] = []

    def record_level_result(self, level_data: Dict) -> None:
        """Record a level result for progression analysis."""
        self._level_stats.append(level_data)

    def run(self) -> None:
        p = self.screenshot("progression_scan")
        if p and self._ocr:
            texts = self._ocr(p)
            level = self._detect_level_number(texts)
            if level is not None:
                self.observe("current_level_number", level, confidence=0.7,
                             notes="Detected via OCR")

        if self._level_stats:
            self._analyze_difficulty_curve()

    def _detect_level_number(self, texts: List[Tuple]) -> Optional[int]:
        """Detect current level number from OCR text."""
        import re
        for text, conf, _, _ in texts:
            if isinstance(text, str):
                m = re.search(r"(?:level|lv|stage|레벨|스테이지)\s*[.:]?\s*(\d+)", text, re.I)
                if m:
                    return int(m.group(1))
        return None

    def _analyze_difficulty_curve(self) -> None:
        """Analyze difficulty progression from recorded levels."""
        if len(self._level_stats) < 3:
            return

        mid = len(self._level_stats) // 2
        early = self._level_stats[:mid]
        late = self._level_stats[mid:]

        def avg_difficulty(levels):
            vals = [l.get("difficulty", l.get("car_count", 0)) for l in levels]
            return sum(vals) / len(vals) if vals else 0

        early_avg = avg_difficulty(early)
        late_avg = avg_difficulty(late)

        if late_avg > early_avg * 1.3:
            curve = "increasing"
        elif late_avg < early_avg * 0.8:
            curve = "decreasing"
        else:
            curve = "flat"

        self.observe("difficulty_curve_type", curve, confidence=0.5,
                     notes=f"early_avg={early_avg:.1f}, late_avg={late_avg:.1f}")
