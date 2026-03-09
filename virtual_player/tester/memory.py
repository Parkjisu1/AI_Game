"""
Layer 2: Memory (기억)
=======================
고정 필드만 업데이트. 무한히 쌓지 않음.

TO DO:
  - 직전 행동과 결과만 기억하라
  - 홀더 변화를 추적하라 (이전 vs 현재)
  - 실패한 탭 좌표를 최근 5개만 기억하라
  - 매칭 이후 경과 턴만 카운트하라

TO DON'T:
  - 전체 게임 히스토리를 유지하지 마라
  - 보드 전체 변화를 추적하지 마라
  - 무한히 쌓지 마라
  - 복잡한 통계를 계산하지 마라
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .playbook import Action
from .perception import BoardState


@dataclass
class GameMemory:
    """고정 크기 게임 메모리. 확장 금지."""

    # 홀더 상태
    holder_count: int = 0
    holder_colors: List[Optional[str]] = field(default_factory=lambda: [None]*7)

    # 직전 행동
    last_action: Optional[Action] = None
    last_result: str = "none"  # car_moved, no_change, match_3, screen_changed, game_over

    # 실패 추적 (최근 5개만)
    failed_taps: List[Tuple[int, int]] = field(default_factory=list)
    consecutive_fails: int = 0

    # 매칭 추적
    turns_since_match: int = 0
    total_matches: int = 0

    # 부스터 잔여
    undo_remaining: int = 2
    magnet_remaining: int = 1

    # 게임 통계
    games_started: int = 0
    games_won: int = 0
    games_failed: int = 0
    total_taps: int = 0
    total_turns: int = 0

    # 팝업 탈출 카운터
    popup_escape_attempts: int = 0

    # 하트 관리 (R2)
    hearts_empty: bool = False
    lobby_fail_count: int = 0          # lobby에서 게임 시작 실패 연속 횟수
    heart_wait_until: float = 0.0      # 하트 대기 종료 시각 (time.time())
    LOBBY_FAIL_THRESHOLD: int = 6      # 이 횟수 이상 연속 실패 → 하트 없음 판정
    HEART_REGEN_SECONDS: float = 600   # 하트 1개 재생 시간 (10분)

    MAX_FAILED_TAPS = 5

    def update_from_board(self, prev: BoardState, curr: BoardState) -> str:
        """이전 / 현재 BoardState 비교 → 결과 판정 + 메모리 업데이트.

        Returns: 결과 문자열 (car_moved, no_change, match_3, screen_changed)
        """
        self.total_turns += 1

        # 화면이 바뀌었으면
        if prev.screen_type != curr.screen_type:
            # popup_escape_attempts: "좋은" 화면으로 전환될 때만 리셋
            # ad↔popup 순환에서 리셋되면 에스컬레이션 불가
            if curr.screen_type in ("gameplay", "lobby", "win"):
                self.popup_escape_attempts = 0
            self.consecutive_fails = 0

            if curr.screen_type == "win":
                self.games_won += 1
                self.last_result = "screen_changed"
                return "screen_changed"
            elif curr.screen_type.startswith("fail"):
                self.games_failed += 1
                self.last_result = "screen_changed"
                return "screen_changed"
            elif curr.screen_type == "lobby":
                self.last_result = "screen_changed"
                return "screen_changed"

            self.last_result = "screen_changed"
            return "screen_changed"

        # gameplay → gameplay: 홀더 변화 비교
        if curr.screen_type == "gameplay":
            self.holder_colors = curr.holder[:]
            self.holder_count = curr.holder_count

            prev_count = prev.holder_count
            curr_count = curr.holder_count

            if curr_count < prev_count:
                # 홀더 줄었다 = 매칭 발생
                self.total_matches += 1
                self.turns_since_match = 0
                self.consecutive_fails = 0
                self.last_result = "match_3"
                return "match_3"
            elif curr_count > prev_count:
                # 홀더 늘었다 = 차가 이동함
                self.consecutive_fails = 0
                self.turns_since_match += 1
                self.last_result = "car_moved"
                return "car_moved"
            else:
                # 변화 없음
                self.consecutive_fails += 1
                self.turns_since_match += 1
                if self.last_action and self.last_action.type == "tap":
                    self._add_failed_tap(self.last_action.x, self.last_action.y)
                self.last_result = "no_change"
                return "no_change"

        self.last_result = "no_change"
        return "no_change"

    def _add_failed_tap(self, x: int, y: int):
        """실패 탭 추가 (최근 N개만 유지)."""
        self.failed_taps.append((x, y))
        if len(self.failed_taps) > self.MAX_FAILED_TAPS:
            self.failed_taps = self.failed_taps[-self.MAX_FAILED_TAPS:]

    def is_near_failed(self, x: int, y: int, threshold: int = 80) -> bool:
        """좌표가 최근 실패 탭 근처인지."""
        for fx, fy in self.failed_taps:
            if abs(fx - x) < threshold and abs(fy - y) < threshold:
                return True
        return False

    def record_action(self, action: Action):
        """실행한 행동 기록."""
        self.last_action = action
        if action.type == "tap":
            self.total_taps += 1

    def on_game_start(self):
        """새 게임 시작 시 리셋."""
        self.games_started += 1
        self.holder_count = 0
        self.holder_colors = [None] * 7
        self.failed_taps.clear()
        self.consecutive_fails = 0
        self.turns_since_match = 0
        self.undo_remaining = 2
        self.magnet_remaining = 1
        self.popup_escape_attempts = 0

    def on_popup(self):
        """팝업 화면 진입 시."""
        self.popup_escape_attempts += 1

    def on_lobby_fail(self):
        """lobby에서 게임 시작 실패 (Level N 탭 후 여전히 lobby)."""
        self.lobby_fail_count += 1
        if self.lobby_fail_count >= self.LOBBY_FAIL_THRESHOLD:
            self.hearts_empty = True

    def on_lobby_success(self):
        """lobby에서 게임 시작 성공 (gameplay 진입)."""
        self.lobby_fail_count = 0
        self.hearts_empty = False

    def start_heart_wait(self):
        """하트 대기 모드 시작 (30분)."""
        import time
        self.heart_wait_until = time.time() + self.HEART_REGEN_SECONDS

    def is_heart_waiting(self) -> bool:
        """현재 하트 대기 중인지."""
        import time
        if self.heart_wait_until <= 0:
            return False
        if time.time() >= self.heart_wait_until:
            # 대기 완료 → 리셋
            self.heart_wait_until = 0.0
            self.hearts_empty = False
            self.lobby_fail_count = 0
            return False
        return True

    def get_color_counts(self) -> Dict[str, int]:
        """홀더 내 색상별 개수."""
        counts: Dict[str, int] = {}
        for c in self.holder_colors:
            if c is not None:
                counts[c] = counts.get(c, 0) + 1
        return counts
