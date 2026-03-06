"""
StateReader -- Perception Layer Orchestrator
============================================
스크린샷 경로 + 화면 타입을 받아 GameStateSnapshot을 반환.
GaugeReader, OCRReader, RegionRegistry를 조합하여 완전한 상태 추출.
"""

from pathlib import Path

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

from .game_state import GameStateSnapshot
from .gauge_reader import GaugeReader
from .ocr_reader import OCRReader
from .region_registry import RegionRegistry
from ..adb import log


class StateReader:
    """게임 스크린샷에서 구조화된 상태를 추출하는 오케스트레이터."""

    def __init__(
        self,
        gauge_reader: GaugeReader,
        ocr_reader: OCRReader,
        registry: RegionRegistry,
    ):
        self._gauge = gauge_reader
        self._ocr = ocr_reader
        self._registry = registry

    def read_state(self, screenshot_path: Path, screen_type: str) -> GameStateSnapshot:
        """
        스크린샷 파일에서 주어진 화면 타입의 게임 상태를 읽는다.

        Args:
            screenshot_path: 스크린샷 파일 경로 (.png/.jpg)
            screen_type: 화면 타입 식별자 ("ingame", "lobby" 등)

        Returns:
            GameStateSnapshot -- ROI 설정이 없으면 빈 스냅샷 반환
        """
        snapshot = GameStateSnapshot(screen_type=screen_type)

        # 1. 화면 타입에 대한 ROI 설정 조회
        roi = self._registry.get(screen_type)
        if roi is None:
            log(f"  [StateReader] No ROI config for screen_type='{screen_type}' -- skipping")
            return snapshot

        # 2. 이미지 로드
        if not _CV2_AVAILABLE:
            log("  [StateReader] cv2 not available -- cannot read image")
            return snapshot

        image = cv2.imread(str(screenshot_path))
        if image is None:
            log(f"  [StateReader] Failed to load image: {screenshot_path}")
            return snapshot

        # 3. 게이지 읽기
        if roi.gauge_regions:
            snapshot.gauges = self._gauge.read_all_gauges(image, roi.gauge_regions)

        # 4. OCR 영역 읽기 (리소스 vs 스탯 분리)
        if roi.ocr_regions:
            all_ocr = self._ocr.read_all(image, roi.ocr_regions)
            for key, reading in all_ocr.items():
                # Combined OCR 결과에서 카테고리 조회
                combined_cfg = roi.ocr_regions.get("_combined", {})
                combined_fields = combined_cfg.get("fields", {})
                if key in combined_fields:
                    category = combined_fields[key].get("category", "resources")
                else:
                    cfg = roi.ocr_regions.get(key, {})
                    category = cfg.get("category", "resources")
                if category == "stats":
                    snapshot.stats[key] = reading
                else:
                    snapshot.resources[key] = reading

        # 5. 결과 로깅
        log(
            f"  [StateReader] {screen_type}: "
            f"HP={snapshot.hp_pct:.0%}, "
            f"MP={snapshot.mp_pct:.0%}, "
            f"Gold={snapshot.gold}"
        )

        return snapshot
