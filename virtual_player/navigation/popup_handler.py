"""
Popup Handler
==============
Detects and dismisses popups, tutorials, and unexpected overlays.
Uses Claude Vision to find close/dismiss button coordinates dynamically.

Ported from C10+ smart_player/popup_handler.py.
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

from ..adb import log, tap, take_screenshot, claude_vision_classify, get_device_resolution
from .classifier import ScreenClassification


class PopupHandler:
    """Handles popup detection and dismissal with coordinate caching."""

    POPUP_PREFIXES = ("popup_",)

    def __init__(self, game_package: str, cache_dir: Path, reference_db=None):
        self.game_package = game_package
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._reference_db = reference_db
        self._local_vision = None

        # Cache: popup screen_type -> (x, y) dismiss coordinates
        self._dismiss_cache: Dict[str, Tuple[int, int]] = {}
        self._cache_file = cache_dir / "popup_dismiss_cache.json"
        self._load_cache()

    def is_popup(self, classification: ScreenClassification) -> bool:
        """Check if classification indicates a popup overlay."""
        return any(
            classification.screen_type.startswith(prefix)
            for prefix in self.POPUP_PREFIXES
        )

    def dismiss(self, classification: ScreenClassification,
                screenshot_path: Path) -> bool:
        """Try to dismiss the popup.

        Strategy:
        1. Check cached dismiss coordinates for this popup type
        2. If no cache, ask Claude Vision for close button location
        3. Tap the found coordinates
        4. Cache result for future use
        """
        popup_type = classification.screen_type

        # 1. Try cached coordinates (L0 -- instant)
        if popup_type in self._dismiss_cache:
            x, y = self._dismiss_cache[popup_type]
            log(f"  [Popup] Dismissing {popup_type} (cached: {x},{y})")
            tap(x, y, wait=1.5)
            return True

        # 2. Ask Claude Vision for close button (L2)
        coords = self._find_close_button(screenshot_path)
        if coords:
            x, y = coords
            log(f"  [Popup] Dismissing {popup_type} (vision: {x},{y})")
            self._dismiss_cache[popup_type] = coords
            self._save_cache()
            tap(x, y, wait=1.5)
            return True

        # 3. Fallback: try common close button positions
        log(f"  [Popup] Fallback dismiss for {popup_type}")
        return self._fallback_dismiss()

    def handle_tutorial(self, classification: ScreenClassification,
                        screenshot_path: Path) -> bool:
        """Handle tutorial highlight overlays."""
        if classification.screen_type != "popup_tutorial":
            return False

        coords = self._find_tutorial_target(screenshot_path)
        if coords:
            x, y = coords
            log(f"  [Popup] Tutorial tap: {x},{y}")
            tap(x, y, wait=2.0)
            return True

        log(f"  [Popup] Tutorial fallback: tap center")
        tap(400, 640, wait=2.0)
        return True

    def _find_close_button(self, screenshot_path: Path) -> Optional[Tuple[int, int]]:
        """Find close/dismiss button using local vision (OpenCV).

        Falls back to Claude Vision API only if local vision fails.
        """
        # Try local vision first (zero API cost)
        coords = self._find_close_button_local(screenshot_path)
        if coords:
            return coords

        # Fallback: Claude Vision API
        w, h = get_device_resolution()
        prompt = f"""이 모바일 게임 스크린샷에서 팝업을 닫을 수 있는 버튼 좌표를 찾으세요.

중요: 디바이스 해상도는 {w}x{h} 픽셀입니다. 좌표를 이 범위(x: 0~{w}, y: 0~{h})로 반환하세요.

규칙:
- 게임 종료/나가기 확인 팝업이면, 반드시 "아니오"/"취소"/"No" 버튼 좌표를 선택하세요.
- 절대로 "예"/"확인"/"Yes" 버튼을 선택하지 마세요 (종료/나가기 팝업일 때).
- 일반 팝업이면: X 버튼, 닫기 버튼, 확인 버튼, OK 버튼 등을 선택하세요.

출력 (JSON만):
{{"x": 정수, "y": 정수, "button_type": "close/cancel/confirm/outside"}}"""

        result = claude_vision_classify(prompt, screenshot_path, model="haiku")
        x = result.get("x")
        y = result.get("y")
        if x is not None and y is not None:
            return (int(x), int(y))
        return None

    def _find_close_button_local(self, screenshot_path: Path) -> Optional[Tuple[int, int]]:
        """Find close button using local OpenCV vision."""
        if not self._reference_db:
            return None
        try:
            if self._local_vision is None:
                from ..brain.local_vision import LocalVision
                self._local_vision = LocalVision(self._reference_db)
            coords = self._local_vision.find_close_button(screenshot_path)
            if coords:
                log(f"  [Popup] Local close button found: {coords}")
            return coords
        except Exception as e:
            log(f"  [Popup] Local close button error: {e}")
            return None

    def _find_tutorial_target(self, screenshot_path: Path) -> Optional[Tuple[int, int]]:
        """Find tutorial highlight target using local vision (brightness detection).

        Falls back to Claude Vision API only if local vision fails.
        """
        # Try local vision first
        if self._reference_db:
            try:
                if self._local_vision is None:
                    from ..brain.local_vision import LocalVision
                    self._local_vision = LocalVision(self._reference_db)
                coords = self._local_vision.find_tutorial_target(screenshot_path)
                if coords:
                    log(f"  [Popup] Local tutorial target found: {coords}")
                    return coords
            except Exception as e:
                log(f"  [Popup] Local tutorial target error: {e}")

        # Fallback: Claude Vision API
        w, h = get_device_resolution()
        prompt = f"""이 모바일 게임 스크린샷에서 튜토리얼 하이라이트 영역의 좌표를 찾으세요.

중요: 디바이스 해상도는 {w}x{h} 픽셀입니다. 좌표를 이 범위로 반환하세요.

찾을 것: 밝게 강조된 버튼, 손가락 아이콘이 가리키는 곳,
반짝이는 UI 요소, "여기를 터치하세요" 안내 영역.

출력 (JSON만):
{{"x": 정수, "y": 정수, "target": "설명"}}"""

        result = claude_vision_classify(prompt, screenshot_path, model="haiku")
        x = result.get("x")
        y = result.get("y")
        if x is not None and y is not None:
            return (int(x), int(y))
        return None

    def _fallback_dismiss(self) -> bool:
        """Try common popup dismiss locations."""
        fallback_coords = [
            (960, 320),   # Top-right X button
            (540, 1400),  # Bottom center confirm
            (540, 1550),  # Lower confirm
            (1050, 160),  # Far top-right X
        ]
        for x, y in fallback_coords:
            tap(x, y, wait=0.8)
        return True

    def _load_cache(self):
        """Load dismiss coordinate cache."""
        if not self._cache_file.exists():
            return
        try:
            data = json.loads(self._cache_file.read_text(encoding="utf-8"))
            for k, v in data.items():
                self._dismiss_cache[k] = (v["x"], v["y"])
        except Exception:
            pass

    def _save_cache(self):
        """Save dismiss coordinate cache."""
        data = {k: {"x": v[0], "y": v[1]} for k, v in self._dismiss_cache.items()}
        self._cache_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
