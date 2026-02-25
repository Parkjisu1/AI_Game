"""
GaugeReader — HP/MP/XP Bar Pixel Analysis
==========================================
OpenCV HSV 색상 필터로 게이지 바 비율을 측정.
OCR 불필요, 게이지당 <10ms 목표.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import cv2
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False

from .game_state import GaugeReading
from ..adb import log


@dataclass
class GaugeProfile:
    """게이지 색상 프로필 정의."""
    name: str
    hsv_lower: Tuple[int, int, int]
    hsv_upper: Tuple[int, int, int]
    color_rgb: Tuple[int, int, int] = (0, 0, 0)
    # 두 번째 색상 범위 (빨간색처럼 HSV wrap-around가 필요한 경우)
    hsv_lower2: Optional[Tuple[int, int, int]] = None
    hsv_upper2: Optional[Tuple[int, int, int]] = None


# 기본 색상 프로필
_DEFAULT_PROFILES: List[GaugeProfile] = [
    GaugeProfile(
        name="hp_green",
        hsv_lower=(35, 80, 80),
        hsv_upper=(85, 255, 255),
        color_rgb=(0, 200, 0),
    ),
    GaugeProfile(
        name="hp_red",
        hsv_lower=(0, 80, 80),
        hsv_upper=(10, 255, 255),
        color_rgb=(200, 0, 0),
        # 빨간색은 HSV에서 wrap-around가 있으므로 두 범위 필요
        hsv_lower2=(170, 80, 80),
        hsv_upper2=(180, 255, 255),
    ),
    GaugeProfile(
        name="mp_blue",
        hsv_lower=(100, 80, 80),
        hsv_upper=(130, 255, 255),
        color_rgb=(0, 0, 200),
    ),
    GaugeProfile(
        name="xp_yellow",
        hsv_lower=(20, 80, 80),
        hsv_upper=(35, 255, 255),
        color_rgb=(200, 200, 0),
    ),
]


class GaugeReader:
    """HSV 색상 마스크 기반 게이지 비율 측정기."""

    def __init__(self, profiles: Optional[List[GaugeProfile]] = None):
        self._profiles = list(profiles) if profiles is not None else list(_DEFAULT_PROFILES)
        # 이름으로 빠른 조회
        self._profile_map: Dict[str, GaugeProfile] = {p.name: p for p in self._profiles}

    def add_profile(self, profile: GaugeProfile) -> None:
        """추가 색상 프로필을 등록 (기존 동일 이름은 덮어쓰기)."""
        self._profile_map[profile.name] = profile
        self._profiles = [p for p in self._profiles if p.name != profile.name]
        self._profiles.append(profile)

    def read_gauge(
        self,
        image: np.ndarray,
        region: Tuple[int, int, int, int],
        profile: GaugeProfile,
    ) -> GaugeReading:
        """
        지정 ROI에서 게이지 비율을 읽는다.

        Args:
            image: BGR 전체 스크린샷 (numpy array)
            region: (x, y, w, h) ROI
            profile: 색상 프로필

        Returns:
            GaugeReading (percentage 0.0~1.0)
        """
        if not _CV2_AVAILABLE:
            return GaugeReading(name=profile.name, percentage=0.0, confidence=0.0)

        x, y, w, h = region
        if w <= 0 or h <= 0:
            return GaugeReading(name=profile.name, percentage=0.0, confidence=0.0)

        # ROI 크롭
        roi = image[y:y + h, x:x + w]
        if roi.size == 0:
            return GaugeReading(name=profile.name, percentage=0.0, confidence=0.0)

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        total_pixels = roi.shape[0] * roi.shape[1]

        # 색상 마스크 생성
        lower = np.array(profile.hsv_lower, dtype=np.uint8)
        upper = np.array(profile.hsv_upper, dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)

        # wrap-around 범위가 있으면 OR 결합
        if profile.hsv_lower2 is not None and profile.hsv_upper2 is not None:
            lower2 = np.array(profile.hsv_lower2, dtype=np.uint8)
            upper2 = np.array(profile.hsv_upper2, dtype=np.uint8)
            mask2 = cv2.inRange(hsv, lower2, upper2)
            mask = cv2.bitwise_or(mask, mask2)

        colored_pixels = int(cv2.countNonZero(mask))
        percentage = colored_pixels / total_pixels if total_pixels > 0 else 0.0
        percentage = max(0.0, min(1.0, percentage))

        # 신뢰도: 색상 픽셀 비율이 높을수록 신뢰 (최소 임계 5% 이상)
        confidence = min(1.0, percentage * 2.0) if percentage > 0.05 else 0.0

        return GaugeReading(
            name=profile.name,
            percentage=percentage,
            color_rgb=profile.color_rgb,
            confidence=confidence,
        )

    def read_all_gauges(
        self,
        image: np.ndarray,
        gauge_regions: Dict[str, dict],
    ) -> Dict[str, GaugeReading]:
        """
        설정 딕셔너리에 정의된 모든 게이지를 읽는다.

        Args:
            image: BGR 스크린샷
            gauge_regions: {name: {"region": [x,y,w,h], "profile": "hp_green"}}
                           또는 {name: {"region": [x,y,w,h], "hsv_lower": [...], "hsv_upper": [...]}}

        Returns:
            {gauge_name: GaugeReading}
        """
        results: Dict[str, GaugeReading] = {}

        for name, cfg in gauge_regions.items():
            region = tuple(cfg.get("region", [0, 0, 0, 0]))
            if len(region) != 4:
                continue

            # 프로필 결정
            profile_name = cfg.get("profile")
            if profile_name and profile_name in self._profile_map:
                profile = self._profile_map[profile_name]
            elif "hsv_lower" in cfg and "hsv_upper" in cfg:
                # 인라인 커스텀 프로필
                profile = GaugeProfile(
                    name=name,
                    hsv_lower=tuple(cfg["hsv_lower"]),
                    hsv_upper=tuple(cfg["hsv_upper"]),
                )
            else:
                # 프로필 미지정 → auto detect
                reading = self.auto_detect(image, region)
                if reading:
                    reading.name = name
                    results[name] = reading
                continue

            reading = self.read_gauge(image, region, profile)
            reading.name = name
            results[name] = reading

        return results

    def auto_detect(
        self,
        image: np.ndarray,
        region: Tuple[int, int, int, int],
    ) -> Optional[GaugeReading]:
        """
        모든 프로필을 시도하여 가장 높은 픽셀 비율을 보이는 프로필을 반환.
        최소 임계값 5% 미만이면 None 반환.
        """
        best: Optional[GaugeReading] = None
        best_pct = 0.05  # 최소 임계값

        for profile in self._profiles:
            reading = self.read_gauge(image, region, profile)
            if reading.percentage > best_pct:
                best_pct = reading.percentage
                best = reading

        if best:
            log(f"  [GaugeReader] auto_detect: {best.name} @ {best.percentage:.0%}")

        return best
