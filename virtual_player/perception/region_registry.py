"""
RegionRegistry -- ROI (Region of Interest) 설정 관리
=====================================================
화면 타입별로 게이지/OCR 영역 설정을 등록하고 조회.
게임 프로필 YAML 또는 JSON 파일에서 로드 가능.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from ..adb import log


@dataclass
class ScreenROI:
    """단일 화면 타입의 ROI 설정 묶음."""
    screen_type: str
    # name -> {"region": [x,y,w,h], "profile": "hp_green"} or {"hsv_lower": [...], "hsv_upper": [...]}
    gauge_regions: Dict[str, dict] = field(default_factory=dict)
    # name -> {"region": [x,y,w,h], "numeric": bool, "name": str}
    ocr_regions: Dict[str, dict] = field(default_factory=dict)


class RegionRegistry:
    """화면 타입별 ROI 설정 레지스트리."""

    def __init__(self):
        self._registry: Dict[str, ScreenROI] = {}

    def register(self, screen_type: str, roi: ScreenROI) -> None:
        """화면 타입에 ROI 설정을 등록한다."""
        self._registry[screen_type] = roi
        log(f"  [RegionRegistry] Registered: {screen_type} "
            f"({len(roi.gauge_regions)} gauges, {len(roi.ocr_regions)} ocr)")

    def get(self, screen_type: str) -> Optional[ScreenROI]:
        """화면 타입에 해당하는 ROI 설정을 반환. 없으면 None."""
        return self._registry.get(screen_type)

    def load_from_dict(self, config: dict) -> None:
        """
        딕셔너리(게임 프로필 YAML 파싱 결과)에서 ROI 설정을 로드.

        예상 구조:
        {
          "ingame": {
            "gauge_regions": {"hp": {"region": [x,y,w,h], "profile": "hp_green"}},
            "ocr_regions": {"gold": {"region": [x,y,w,h], "numeric": true, "name": "gold"}}
          },
          "lobby": { ... }
        }
        """
        for screen_type, roi_cfg in config.items():
            if not isinstance(roi_cfg, dict):
                continue
            roi = ScreenROI(
                screen_type=screen_type,
                gauge_regions=roi_cfg.get("gauge_regions", {}),
                ocr_regions=roi_cfg.get("ocr_regions", {}),
            )
            self.register(screen_type, roi)

    def load_from_file(self, path: Path) -> None:
        """
        JSON 파일에서 ROI 설정을 로드.

        Args:
            path: .json 파일 경로
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = json.load(f)
            self.load_from_dict(config)
            log(f"  [RegionRegistry] Loaded from: {path}")
        except FileNotFoundError:
            log(f"  [RegionRegistry] File not found: {path}")
        except json.JSONDecodeError as e:
            log(f"  [RegionRegistry] JSON parse error: {e}")
        except Exception as e:
            log(f"  [RegionRegistry] Load error: {e}")

    def set_genre_defaults(self, genre_rois: Dict[str, ScreenROI]) -> None:
        """
        장르 스키마에서 기본 ROI를 설정한다.
        이미 등록된 화면 타입은 덮어쓰지 않음 (게임별 설정 우선).

        Args:
            genre_rois: {screen_type: ScreenROI} 장르 기본값
        """
        for screen_type, roi in genre_rois.items():
            if screen_type not in self._registry:
                self.register(screen_type, roi)
                log(f"  [RegionRegistry] Genre default applied: {screen_type}")
