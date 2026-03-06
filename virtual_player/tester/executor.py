"""
Layer 4: Execution (손) + Layer 5: Verification (확인)
=======================================================
Layer 3 결과만 실행. 자체 판단 금지.

TO DO (Layer 4):
  - Layer 3이 결정한 좌표만 탭하라
  - 탭 후 대기하라 (애니메이션)
  - 결과를 memory에 기록하라

TO DON'T (Layer 4):
  - 자체적으로 좌표를 변경하지 마라
  - 대기 없이 연속 탭하지 마라
  - 기록 없이 진행하지 마라

TO DO (Layer 5):
  - 탭 전후 홀더 변화를 비교하라
  - 변화 없으면 failed_tap에 추가하라
  - 화면이 바뀌면 새 화면 핸들러로 전환하라

TO DON'T (Layer 5):
  - 보드 전체를 비교하지 마라
  - 같은 좌표를 재시도하지 마라
  - 무한히 재시도하지 마라
"""

import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from .playbook import Action, Playbook
from .perception import BoardState, Perception
from .memory import GameMemory
from .decision import Decision


class Executor:
    """Layer 4+5: 행동 실행 + 결과 확인.

    ADB 함수를 주입받아 실행. 자체 판단 없음.
    """

    def __init__(
        self,
        tap_fn: Callable[[int, int], None],
        back_fn: Callable[[], None],
        screenshot_fn: Callable[[], Optional[Path]],
        relaunch_fn: Callable[[], None],
        perception: Perception,
        memory: GameMemory,
    ):
        self._tap = tap_fn
        self._back = back_fn
        self._screenshot = screenshot_fn
        self._relaunch = relaunch_fn
        self._perception = perception
        self._memory = memory

    def execute(self, actions: List[Action], prev_board: BoardState) -> BoardState:
        """Action 리스트를 순서대로 실행하고, 최종 BoardState 반환.

        각 Action 실행 후:
        1. wait 대기
        2. 스크린샷 → perceive
        3. memory 업데이트
        4. 화면 전환 감지 시 즉시 중단 (남은 Action 버림)
        """
        current_board = prev_board

        for action in actions:
            self._log_action(action)
            self._memory.record_action(action)

            # 실행
            if action.type == "tap":
                self._tap(action.x, action.y)
            elif action.type == "back":
                self._back()
            elif action.type == "relaunch":
                self._relaunch()
            elif action.type == "wait":
                pass  # wait만 아래서 처리
            # 그 외는 무시 (안전)

            # 대기
            time.sleep(action.wait)

            # Layer 5: 확인 (스크린샷 → perceive → compare)
            img = self._screenshot()
            if img:
                new_board = self._perception.perceive(img)
                result = self._memory.update_from_board(current_board, new_board)
                self._log_result(action, result, new_board)
                current_board = new_board

                # 화면 전환 감지 → 즉시 중단
                if result == "screen_changed":
                    break

                # 매칭 발생 → 즉시 중단 (재분석 필요)
                if result == "match_3":
                    break

        return current_board

    def _log_action(self, action: Action):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {action}", flush=True)

    def _log_result(self, action: Action, result: str, board: BoardState):
        ts = datetime.now().strftime("%H:%M:%S")
        holder_str = self._format_holder(board.holder)
        cars_count = len(board.active_cars)

        if result == "match_3":
            print(f"[{ts}]   >> MATCH! Holder: {holder_str}", flush=True)
        elif result == "car_moved":
            print(f"[{ts}]   >> moved. Holder: {holder_str} ({cars_count} cars visible)", flush=True)
        elif result == "no_change":
            print(f"[{ts}]   >> no change (fail #{self._memory.consecutive_fails})", flush=True)
        elif result == "screen_changed":
            print(f"[{ts}]   >> screen changed → {board.screen_type}", flush=True)

    def _format_holder(self, holder: list) -> str:
        """홀더를 [R R B _ _ _ _] 형식으로 표시."""
        parts = []
        for h in holder:
            if h is None:
                parts.append("_")
            else:
                parts.append(h[0].upper())  # 첫 글자 대문자
        return "[" + " ".join(parts) + "]"
