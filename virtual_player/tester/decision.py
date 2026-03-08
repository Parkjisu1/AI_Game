"""
Layer 3: Decision (판단)
=========================
고정 분기 트리. AI 자율판단 금지.
우선순위 P0~P5 + NEVER 규칙.

TO DO:
  - P0: 화면이 gameplay 아니면 → 해당 화면 핸들러
  - P1: 홀더에 같은 색 2대 → 보드에서 3번째 찾아 탭
  - P2: 홀더 5칸+ → Undo
  - P3: 앞줄 활성 차 중 홀더에 같은 색 있는 차 탭
  - P4: 앞줄 활성 차 아무거나 탭
  - P5: Mystery → 홀더 3칸 이하일 때만

TO DON'T:
  - 랜덤으로 아무 차나 탭하지 마라
  - 비활성(blocked) 차를 탭하지 마라
  - Shuffle/Rotate를 사용하지 마라
  - 금지 영역을 탭하지 마라
"""

from typing import List, Optional

from .playbook import Action, Playbook
from .perception import BoardState, CarInfo
from .memory import GameMemory


class Decision:
    """Layer 3: 고정 분기 기반 의사결정.

    AI가 관여하는 부분: 없음. 전부 규칙 기반.
    """

    def __init__(self, playbook: Playbook):
        self.pb = playbook

    def decide(self, board: BoardState, memory: GameMemory) -> List[Action]:
        """현재 상태 → 실행할 Action 리스트.

        Returns: 1개 이상의 Action. 순서대로 실행.
        """

        # =============================================
        # P0: 화면이 gameplay 아니면 → 화면 핸들러
        # =============================================
        if board.screen_type != "gameplay":
            return self._handle_non_gameplay(board, memory)

        # =============================================
        # 이하 gameplay 전용
        # =============================================

        holder_count = board.holder_count
        color_counts = memory.get_color_counts()

        # =============================================
        # P-CRITICAL: 홀더 6칸+ → 즉시 Undo
        # =============================================
        if holder_count >= self.pb.holder_critical:
            if memory.undo_remaining > 0:
                memory.undo_remaining -= 1
                ux, uy = self.pb.boosters["undo"]
                return [Action("tap", ux, uy, 1.5, f"P-CRIT: Undo (holder={holder_count})")]

        # =============================================
        # P1: 홀더에 같은 색 2대 → 보드에서 3번째 찾아 탭
        # =============================================
        for color, count in color_counts.items():
            if count >= (self.pb.match_count - 1):  # 2대 이상
                target = self._find_active_car(board, memory, color)
                if target:
                    return [Action("tap", target.x, target.y, 1.5,
                                   f"P1: {color} match completion ({count}+1={count+1})")]

        # =============================================
        # P2: 홀더 5칸+ → Undo
        # =============================================
        if holder_count >= self.pb.holder_danger:
            if memory.undo_remaining > 0:
                memory.undo_remaining -= 1
                ux, uy = self.pb.boosters["undo"]
                return [Action("tap", ux, uy, 1.5,
                               f"P2: Undo (holder={holder_count}, danger)")]
            # Undo 없으면 Magnet 시도
            if memory.magnet_remaining > 0:
                memory.magnet_remaining -= 1
                mx, my = self.pb.boosters["magnet"]
                return [Action("tap", mx, my, 2.0,
                               f"P2: Magnet (holder={holder_count}, no undo)")]

        # =============================================
        # P3: 앞줄 활성 차 중 홀더에 같은 색 있는 차 탭
        # =============================================
        for car in self._sort_by_priority(board.active_cars):
            if car.color in color_counts and not car.is_mystery:
                if not memory.is_near_failed(car.x, car.y):
                    if not self.pb.is_forbidden_tap(car.x, car.y):
                        return [Action("tap", car.x, car.y, 1.5,
                                       f"P3: {car.color} car (matches {color_counts[car.color]} in holder)")]

        # =============================================
        # P4: 앞줄 활성 차 아무거나 (비Mystery)
        # =============================================
        for car in self._sort_by_priority(board.active_cars):
            if not car.is_mystery:
                if not memory.is_near_failed(car.x, car.y):
                    if not self.pb.is_forbidden_tap(car.x, car.y):
                        return [Action("tap", car.x, car.y, 1.5,
                                       f"P4: {car.color} car (front row clearance)")]

        # =============================================
        # P5: Mystery(?) → 홀더 3칸 이하일 때만
        # =============================================
        if holder_count <= 3:
            for car in board.active_cars:
                if car.is_mystery:
                    if not memory.is_near_failed(car.x, car.y):
                        return [Action("tap", car.x, car.y, 1.5,
                                       f"P5: mystery car (holder safe: {holder_count})")]

        # =============================================
        # FALLBACK: 활성 차가 아예 없거나 전부 실패 근처
        # =============================================
        if memory.consecutive_fails >= self.pb.max_consecutive_fails:
            # Undo로 돌리기
            if memory.undo_remaining > 0:
                memory.undo_remaining -= 1
                ux, uy = self.pb.boosters["undo"]
                return [Action("tap", ux, uy, 1.5,
                               f"FALLBACK: Undo after {memory.consecutive_fails} fails")]

        # 아직 탭할 차가 있지만 전부 failed 근처
        if board.active_cars:
            car = board.active_cars[0]
            return [Action("tap", car.x, car.y, 1.5,
                           f"FALLBACK: forced tap on {car.color} (all near-failed)")]

        # 진짜 아무것도 없음 → 재인식 대기
        return [Action("wait", wait=2.0, reason="FALLBACK: no active cars, wait for re-perceive")]

    def _handle_non_gameplay(self, board: BoardState, memory: GameMemory) -> List[Action]:
        """gameplay이 아닌 화면 처리."""

        screen = board.screen_type

        # 게임 시작 감지
        if screen == "lobby":
            memory.on_game_start()

        # 공통 에스컬레이션: popup, unknown, fail_result, ad 모두 적용
        if screen in ("popup", "unknown", "fail_result", "ad"):
            memory.on_popup()
            if memory.popup_escape_attempts >= 15:
                stuck_count = memory.popup_escape_attempts
                memory.popup_escape_attempts = 0
                return [Action("relaunch", wait=5.0,
                               reason=f"Screen stuck: {screen} ({stuck_count} attempts)")]

        # ad 전용: 스마트 핸들링 (시도 횟수에 따라 다른 전략)
        if screen == "ad":
            return self._handle_ad(memory)

        # Playbook에 등록된 핸들러 사용
        handler = self.pb.screen_handlers.get(screen)
        if handler:
            return handler.actions[:]

        # 미등록 화면 → back 버튼
        return [Action("back", wait=1.0, reason=f"Unregistered screen: {screen}")]

    def _handle_ad(self, memory: GameMemory) -> List[Action]:
        """광고 스마트 핸들링.

        광고 특성:
        - X 버튼이 5~30초 후에야 표시됨
        - X 위치가 광고 네트워크마다 다름 (우상, 좌상, 좌하 등)
        - 너무 빨리 탭하면 광고 인터랙션으로 인식 → X 타이머 리셋
        - BACK 버튼이 작동하는 광고도 있고 안 되는 것도 있음

        전략:
        Phase 1 (1~3회): 대기 후 BACK — 광고 재생 시간 확보
        Phase 2 (4~8회): X 위치 12곳 순차 스캔
        Phase 3 (9회+): relaunch
        """
        attempts = memory.popup_escape_attempts

        if attempts <= 3:
            # Phase 1: 광고가 끝나길 기다림. 급하게 탭하면 역효과.
            return [
                Action("wait", wait=5.0, reason=f"Ad wait (attempt {attempts}, let ad play)"),
                Action("back", wait=1.0, reason="Ad: try BACK after wait"),
            ]

        elif attempts <= 8:
            # Phase 2: X 버튼 위치 순차 스캔 (광고 네트워크별 공통 위치)
            # 한 번에 2곳씩 시도
            x_positions = [
                # (x, y, 설명)
                (1050, 30, "top-right corner"),
                (1040, 60, "top-right offset"),
                (1050, 100, "top-right low"),
                (30, 30, "top-left corner"),
                (50, 60, "top-left offset"),
                (1020, 150, "right side high"),
                (30, 100, "left side high"),
                (540, 1850, "bottom center"),
                (980, 1850, "bottom right"),
                (100, 1850, "bottom left"),
            ]
            # 시도 횟수에 따라 다른 위치 선택
            idx = ((attempts - 4) * 2) % len(x_positions)
            pos1 = x_positions[idx]
            pos2 = x_positions[(idx + 1) % len(x_positions)]

            return [
                Action("wait", wait=3.0, reason=f"Ad wait before X scan (attempt {attempts})"),
                Action("tap", pos1[0], pos1[1], 0.5, f"Ad X: {pos1[2]}"),
                Action("tap", pos2[0], pos2[1], 0.5, f"Ad X: {pos2[2]}"),
                Action("back", wait=1.0, reason="Ad: BACK fallback"),
            ]

        else:
            # Phase 3: 포기 → relaunch
            memory.popup_escape_attempts = 0
            return [Action("relaunch", wait=5.0,
                           reason=f"Ad stuck after {attempts} attempts")]

    def _find_active_car(
        self, board: BoardState, memory: GameMemory, color: str
    ) -> Optional[CarInfo]:
        """보드에서 특정 색상의 활성 차 찾기 (실패 근처 제외)."""
        for car in self._sort_by_priority(board.active_cars):
            if car.color == color and not car.is_mystery:
                if not memory.is_near_failed(car.x, car.y):
                    if not self.pb.is_forbidden_tap(car.x, car.y):
                        return car
        return None

    def _sort_by_priority(self, cars: List[CarInfo]) -> List[CarInfo]:
        """자동차를 탭 우선순위로 정렬.

        규칙:
        - y가 큰(아래쪽) 차 = 앞줄 = 우선
        - 스택이 1인 차 우선 (단독 차)
        - Mystery는 맨 뒤
        """
        return sorted(cars, key=lambda c: (
            c.is_mystery,    # Mystery 맨 뒤
            -c.y,            # y 큰(아래) 게 앞
            c.stacked,       # 스택 적은 게 앞
        ))
