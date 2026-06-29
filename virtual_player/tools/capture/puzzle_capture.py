"""
Puzzle Capture — Before/After + Board Delta
=============================================
퍼즐 게임용 캡처 엔진.
- 화면이 정적 → Before/After 페어로 인과관계 명확
- Full-frame Delta + 선택적 Board ROI Delta
- 기존 ClickCapture v3 동작과 호환

JSONL 추가 필드:
  - delta_from_prev: 이전 프레임 대비 전체 변화율
  - delta_before_after: Before↔After 변화율
  - board_delta: (ROI 설정 시) 보드 영역만의 변화율
"""

import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

from .base import (
    ADBConnection,
    BaseCaptureEngine,
    SessionManager,
    compute_pixel_delta,
    compute_roi_deltas,
)


class PuzzleCaptureEngine(BaseCaptureEngine):
    """
    퍼즐 장르: Before/After 페어 + 픽셀 Delta.

    설정:
        before_after: Before/After 페어 캡처 여부
        after_delay: After 캡처 대기 시간 (초)
        board_roi: 보드 영역 좌표 (x, y, w, h) — 선택
    """

    GENRE = "puzzle"

    def __init__(self, adb: ADBConnection, session: SessionManager, **kwargs):
        super().__init__(adb, session, kwargs.get("log_fn"))
        self.before_after: bool = kwargs.get("before_after", True)
        self.after_delay: float = kwargs.get("after_delay", 0.5)
        self.board_roi: Optional[Tuple[int, int, int, int]] = kwargs.get("board_roi")

    def on_start(self):
        self.detect_resolution()
        self.prev_frame_bytes = b""
        self.log(f"[Puzzle] Capture started", tag="accent")
        if self.before_after:
            self.log(f"[Puzzle] Before/After ON  delay={int(self.after_delay*1000)}ms")
        if self.board_roi:
            self.log(f"[Puzzle] Board ROI: {self.board_roi}")

    def on_stop(self):
        self.log(f"[Puzzle] Capture stopped")

    def process_event(self, evt: dict):
        """퍼즐 캡처: Before 스크린샷 → (대기) → After 스크린샷."""
        app_dir = self.session.app_dir
        seq = self.session.record_action()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ── Before ──
        before_bytes = self.adb.screenshot_bytes()
        if not before_bytes:
            self.log(f"[{self.session.app_label}] #{seq} FAILED", tag="error")
            return

        suffix = "_before" if self.before_after else ""
        before_name = f"click_{ts}_{seq:04d}{suffix}.png"
        (app_dir / before_name).write_bytes(before_bytes)

        # Delta: 이전 프레임 대비
        delta_prev = compute_pixel_delta(self.prev_frame_bytes, before_bytes)
        self.prev_frame_bytes = before_bytes

        # ── After (optional) ──
        after_name = None
        delta_ba = None
        board_delta = None

        if self.before_after:
            time.sleep(self.after_delay)
            after_bytes = self.adb.screenshot_bytes()
            if after_bytes:
                after_name = f"click_{ts}_{seq:04d}_after.png"
                (app_dir / after_name).write_bytes(after_bytes)
                self.session.total_captures += 1

                # Before↔After 전체 Delta
                delta_ba = compute_pixel_delta(before_bytes, after_bytes)

                # Board ROI Delta (설정 시)
                if self.board_roi:
                    board_delta = compute_pixel_delta(
                        before_bytes, after_bytes, region=self.board_roi)

        # ── Log ──
        action_str = self.format_action(evt)
        parts = [f"[{self.session.app_label}] #{seq}  {action_str}"]
        if after_name:
            parts.append("+after")
        if delta_prev >= 0:
            parts.append(f"d_prev={delta_prev:.2%}")
        if delta_ba is not None and delta_ba >= 0:
            parts.append(f"d_ba={delta_ba:.2%}")
        if board_delta is not None and board_delta >= 0:
            parts.append(f"board={board_delta:.2%}")
        self.log("  ".join(parts))

        # ── JSONL ──
        entry = self.build_base_entry(evt, seq, before_name, after_name)
        entry["delta_from_prev"] = delta_prev if delta_prev >= 0 else None
        if delta_ba is not None:
            entry["delta_before_after"] = delta_ba if delta_ba >= 0 else None
        if board_delta is not None:
            entry["board_delta"] = board_delta if board_delta >= 0 else None
        if self.board_roi:
            entry["board_roi"] = list(self.board_roi)

        self.session.write_log(entry)
