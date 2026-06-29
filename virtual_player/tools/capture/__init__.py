"""
Genre-specific Capture Pipeline
================================
Puzzle / Idle / Action(RPG·SLG) 장르별 캡처 모듈.

- base: ADB, 에뮬레이터, 제스처, 세션 공통 인프라
- puzzle_capture: Before/After + Board Delta
- idle_capture: OCR 숫자 추적 + Value Delta
- action_capture: YOLO 화면 분류 + 상태 전이
- launcher: 통합 GUI 런처
"""

from .base import (
    ADBConnection,
    EmulatorRegistry,
    TapMonitor,
    SessionManager,
    compute_pixel_delta,
)

__all__ = [
    "ADBConnection",
    "EmulatorRegistry",
    "TapMonitor",
    "SessionManager",
    "compute_pixel_delta",
]
