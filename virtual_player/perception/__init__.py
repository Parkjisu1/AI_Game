"""
Perception Package -- Layer 1: State Perception
===============================================
스크린샷에서 구조화된 게임 상태를 추출하는 레이어.

주요 클래스:
  - GameStateSnapshot: 추출된 게임 상태 데이터 모델
  - GaugeReader: HP/MP/XP 게이지 바 픽셀 분석
  - OCRReader: 텍스트/숫자 인식 (PaddleOCR / Tesseract)
  - RegionRegistry: 화면별 ROI 설정 관리
  - StateReader: 위 모듈들을 조합한 오케스트레이터
"""

from .game_state import GameStateSnapshot, GaugeReading, OCRReading
from .gauge_reader import GaugeReader, GaugeProfile
from .ocr_reader import OCRReader
from .region_registry import RegionRegistry, ScreenROI
from .state_reader import StateReader

__all__ = [
    "GameStateSnapshot",
    "GaugeReading",
    "OCRReading",
    "GaugeReader",
    "GaugeProfile",
    "OCRReader",
    "RegionRegistry",
    "ScreenROI",
    "StateReader",
]
