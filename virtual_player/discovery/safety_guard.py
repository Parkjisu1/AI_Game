"""
SafetyGuard -- Prevent Real Purchases During Exploration
=========================================================
Blocks taps near real-money purchase keywords and caps resource spending.

Extracted from smart_player.py and made game-agnostic.
"""

import logging
from typing import List, Optional, Sequence, Tuple, Union

logger = logging.getLogger(__name__)

# Type for OCR text items: can be (text, confidence, y, x) tuples or plain strings
OCRItem = Union[str, Tuple, List]


class SafetyGuard:
    """Blocks taps that might trigger real-money purchases."""

    DEFAULT_DANGER_KEYWORDS = [
        "결제", "구매 확인", "실제 화폐", "현금", "카드",
        "purchase", "real money", "$", "₩",
    ]
    DEFAULT_CAUTION_KEYWORDS = [
        "다이아몬드", "보석", "diamond", "gem", "패키지", "package",
    ]
    DEFAULT_MAX_RESOURCE_SPEND = 50000

    def __init__(
        self,
        danger_keywords: Optional[List[str]] = None,
        caution_keywords: Optional[List[str]] = None,
        max_resource_spend: int = DEFAULT_MAX_RESOURCE_SPEND,
    ):
        """
        Args:
            danger_keywords: Keywords that BLOCK taps entirely. Uses defaults if None.
            caution_keywords: Keywords that log warnings but allow taps. Uses defaults if None.
            max_resource_spend: Max resource delta before blocking further spending.
        """
        self.danger_keywords = danger_keywords or list(self.DEFAULT_DANGER_KEYWORDS)
        self.caution_keywords = caution_keywords or list(self.DEFAULT_CAUTION_KEYWORDS)
        self.max_resource_spend = max_resource_spend

        self._resource_start: float = 0
        self.blocked_count: int = 0

    def is_safe_to_tap(
        self,
        screen_type: str,
        x: int,
        y: int,
        ocr_texts: Optional[Sequence[OCRItem]] = None,
    ) -> bool:
        """
        Check if tapping (x, y) is safe based on on-screen OCR text.

        Args:
            screen_type: Current screen identifier.
            x, y: Tap coordinates.
            ocr_texts: OCR results -- list of (text, conf, ...) tuples or plain strings.

        Returns:
            True if safe to tap, False if blocked.
        """
        if not ocr_texts:
            return True

        all_text = " ".join(
            t[0] if isinstance(t, (tuple, list)) else str(t)
            for t in ocr_texts
        ).lower()

        for kw in self.danger_keywords:
            if kw.lower() in all_text:
                logger.warning(
                    "SAFETY BLOCKED tap (%d,%d) on [%s] -- danger keyword '%s'",
                    x, y, screen_type, kw,
                )
                self.blocked_count += 1
                return False

        for kw in self.caution_keywords:
            if kw.lower() in all_text:
                logger.info(
                    "SAFETY CAUTION at (%d,%d) on [%s] -- '%s' detected",
                    x, y, screen_type, kw,
                )

        return True

    def check_resource_limit(self, current_amount: float) -> bool:
        """
        Check if resource spending is within the allowed limit.

        Call this periodically with the current resource amount (gold, gems, etc.).
        The first call sets the baseline. Subsequent calls check the delta.

        Returns:
            True if within limit, False if exceeded.
        """
        if self._resource_start == 0:
            self._resource_start = current_amount
            return True

        spent = self._resource_start - current_amount
        if spent > self.max_resource_spend:
            logger.warning(
                "SAFETY: Resource limit exceeded (spent %.0f > max %d)",
                spent, self.max_resource_spend,
            )
            return False
        return True

    def reset(self) -> None:
        """Reset resource tracking and blocked count."""
        self._resource_start = 0
        self.blocked_count = 0
