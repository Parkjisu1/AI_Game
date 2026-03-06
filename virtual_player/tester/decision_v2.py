"""
Layer 3 v2: Decision with Lookahead (판단 + 사고)
====================================================
기존 Decision(반사 신경)에 Lookahead(사고력)를 결합.

기존 P0~P5 규칙은 유지하되, P3~P4 단계에서
"아무 차나 탭" 대신 "시뮬레이션으로 최선의 차를 탭"으로 교체.

변경 지점:
  P3 (기존): 홀더에 같은 색 있는 차 → 무조건 탭
  P3 (v2):   홀더에 같은 색 있는 차 중 → 시뮬레이션 점수 최고인 차 탭

  P4 (기존): 앞줄 아무 차 탭
  P4 (v2):   모든 활성 차 시뮬레이션 → 최고 점수 탭

사람이 해야 하는 것:
  - weights 조정 (match_completion=100이 적절한지?)
  - top_k 조정 (2수 탐색 깊이)
  - 새 규칙 추가 (게임별로 다른 특수 규칙)

Swarm이 하는 것:
  - "이 가중치로 3판 했더니 2판 클리어" → 통계 기록
  - weights 미세 조정 제안
"""

from typing import List, Optional

from .playbook import Action, Playbook
from .perception import BoardState, CarInfo
from .memory import GameMemory
from .lookahead import LookaheadSimulator, DeepLookahead


class DecisionV2:
    """Layer 3 v2: 규칙 + 시뮬레이션 하이브리드."""

    def __init__(
        self,
        playbook: Playbook,
        use_deep: bool = False,
        weights: Optional[dict] = None,
    ):
        self.pb = playbook
        self.use_deep = use_deep

        if use_deep:
            self.sim = DeepLookahead(
                match_count=playbook.match_count,
                holder_slots=playbook.holder_slots,
                weights=weights,
            )
        else:
            self.sim = LookaheadSimulator(
                match_count=playbook.match_count,
                holder_slots=playbook.holder_slots,
                weights=weights,
            )

    def decide(self, board: BoardState, memory: GameMemory) -> List[Action]:
        """현재 상태 → Action 리스트.

        P0~P2는 기존과 동일 (긴급 상황은 규칙 우선).
        P3~P4는 Lookahead 시뮬레이션으로 교체.
        """

        # P0: 비-gameplay 화면 → 화면 핸들러
        if board.screen_type != "gameplay":
            return self._handle_non_gameplay(board, memory)

        holder_count = board.holder_count
        color_counts = memory.get_color_counts()

        # P-CRITICAL: 홀더 6칸+ → 즉시 Undo (규칙 우선)
        if holder_count >= self.pb.holder_critical:
            if memory.undo_remaining > 0:
                memory.undo_remaining -= 1
                ux, uy = self.pb.boosters["undo"]
                return [Action("tap", ux, uy, 1.5,
                               f"P-CRIT: Undo (holder={holder_count})")]

        # P1: 홀더에 같은 색 2대 → 3번째 찾기 (규칙 우선)
        for color, count in color_counts.items():
            if count >= (self.pb.match_count - 1):
                target = self._find_active_car_for_match(board, memory, color)
                if target:
                    return [Action("tap", target.x, target.y, 1.5,
                                   f"P1: {color} match ({count}+1)")]

        # P2: 홀더 5칸+ → Undo/Magnet (규칙 우선)
        if holder_count >= self.pb.holder_danger:
            if memory.undo_remaining > 0:
                memory.undo_remaining -= 1
                ux, uy = self.pb.boosters["undo"]
                return [Action("tap", ux, uy, 1.5,
                               f"P2: Undo (holder={holder_count})")]
            if memory.magnet_remaining > 0:
                memory.magnet_remaining -= 1
                mx, my = self.pb.boosters["magnet"]
                return [Action("tap", mx, my, 2.0,
                               f"P2: Magnet (holder={holder_count})")]

        # ============================================
        # P3+P4 통합: Lookahead 시뮬레이션
        # ============================================
        # 기존과의 차이: "아무 차나 탭" 대신 "최적의 차를 탭"
        best = self._find_best_simulated_move(board, memory)
        if best:
            return [Action("tap", best.car.x, best.car.y, 1.5,
                           f"SIM: {best.reason} (score={best.score:.0f})")]

        # P5: Mystery
        if holder_count <= 3:
            for car in board.active_cars:
                if car.is_mystery:
                    if not memory.is_near_failed(car.x, car.y):
                        return [Action("tap", car.x, car.y, 1.5,
                                       f"P5: mystery (holder safe: {holder_count})")]

        # FALLBACK
        if memory.consecutive_fails >= self.pb.max_consecutive_fails:
            if memory.undo_remaining > 0:
                memory.undo_remaining -= 1
                ux, uy = self.pb.boosters["undo"]
                return [Action("tap", ux, uy, 1.5,
                               f"FALLBACK: Undo after {memory.consecutive_fails} fails")]

        if board.active_cars:
            car = board.active_cars[0]
            return [Action("tap", car.x, car.y, 1.5,
                           f"FALLBACK: forced {car.color}")]

        return [Action("wait", wait=2.0, reason="FALLBACK: no cars")]

    def _find_best_simulated_move(
        self, board: BoardState, memory: GameMemory
    ) -> Optional:
        """시뮬레이션으로 최적 탭 선택."""
        holder = memory.holder_colors[:]

        if self.use_deep:
            result = self.sim.get_best_move_deep(board, holder)
        else:
            result = self.sim.get_best_move(board, holder)

        if result is None:
            return None

        # 금지 영역 및 실패 근처 필터링
        if self.pb.is_forbidden_tap(result.car.x, result.car.y):
            return None
        if memory.is_near_failed(result.car.x, result.car.y):
            # 차선 선택
            results = self.sim.evaluate_all_moves(board, holder)
            for r in results:
                if (not self.pb.is_forbidden_tap(r.car.x, r.car.y)
                        and not memory.is_near_failed(r.car.x, r.car.y)):
                    return r
            return None

        return result

    def _find_active_car_for_match(
        self, board: BoardState, memory: GameMemory, color: str
    ) -> Optional[CarInfo]:
        """매칭 완성용 차 찾기."""
        for car in sorted(board.active_cars, key=lambda c: (-c.y, c.stacked)):
            if car.color == color and not car.is_mystery:
                if not memory.is_near_failed(car.x, car.y):
                    if not self.pb.is_forbidden_tap(car.x, car.y):
                        return car
        return None

    def _handle_non_gameplay(self, board: BoardState, memory: GameMemory) -> List[Action]:
        """gameplay이 아닌 화면 처리 (기존과 동일)."""
        screen = board.screen_type

        if screen == "lobby":
            memory.on_game_start()

        if screen in ("popup", "unknown"):
            memory.on_popup()
            if memory.popup_escape_attempts >= 10:
                return [Action("relaunch", wait=5.0,
                               reason=f"Popup stuck ({memory.popup_escape_attempts})")]

        handler = self.pb.screen_handlers.get(screen)
        if handler:
            return handler.actions[:]

        return [Action("back", wait=1.0, reason=f"Unregistered: {screen}")]
