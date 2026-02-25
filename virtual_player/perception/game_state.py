"""
GameStateSnapshot — Perception Layer Data Model
================================================
게임 화면에서 추출한 구조화된 상태 정보.
GaugeReading(게이지), OCRReading(텍스트/숫자)를 포함.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
import time


@dataclass
class GaugeReading:
    """HP/MP/XP 등 게이지 바 읽기 결과."""
    name: str                                   # "hp", "mp", "xp"
    percentage: float                           # 0.0~1.0
    color_rgb: Tuple[int, int, int] = (0, 0, 0)
    confidence: float = 0.0


@dataclass
class OCRReading:
    """텍스트/숫자 OCR 읽기 결과."""
    name: str                                           # "gold", "atk_stat"
    raw_text: str = ""
    parsed_value: Optional[float] = None
    confidence: float = 0.0
    region: Tuple[int, int, int, int] = (0, 0, 0, 0)  # x, y, w, h


@dataclass
class GameStateSnapshot:
    """단일 프레임에서 추출한 게임 상태 전체."""
    screen_type: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    gauges: Dict[str, GaugeReading] = field(default_factory=dict)
    resources: Dict[str, OCRReading] = field(default_factory=dict)
    stats: Dict[str, OCRReading] = field(default_factory=dict)

    @property
    def hp_pct(self) -> float:
        return self.gauges.get("hp", GaugeReading("hp", 1.0)).percentage

    @property
    def mp_pct(self) -> float:
        return self.gauges.get("mp", GaugeReading("mp", 1.0)).percentage

    @property
    def gold(self) -> float:
        r = self.resources.get("gold")
        return r.parsed_value if r and r.parsed_value is not None else 0.0

    @property
    def level(self) -> int:
        s = self.stats.get("level")
        return int(s.parsed_value) if s and s.parsed_value is not None else 0

    def to_dict(self) -> dict:
        return {
            "screen_type": self.screen_type,
            "timestamp": self.timestamp,
            "gauges": {
                k: {"pct": v.percentage, "conf": v.confidence}
                for k, v in self.gauges.items()
            },
            "resources": {
                k: {"val": v.parsed_value, "raw": v.raw_text, "conf": v.confidence}
                for k, v in self.resources.items()
            },
            "stats": {
                k: {"val": v.parsed_value, "raw": v.raw_text, "conf": v.confidence}
                for k, v in self.stats.items()
            },
        }
