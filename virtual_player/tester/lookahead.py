"""
Lookahead Simulator — 1~2수 앞을 보는 전략 엔진
===================================================
현재 Decision(P0~P5)은 "반사 신경" — 지금 보이는 것만 보고 판단.
이 모듈은 "사고력" — "이 차를 탭하면 홀더가 어떻게 될까?"를 시뮬레이션.

사람이 해야 하는 부분:
  1. 게임 규칙을 시뮬레이터에 정확히 코딩
  2. 점수 함수(scoring)의 가중치 조정
  3. 시뮬레이션 결과를 보고 규칙 추가/수정

AI(Swarm)가 하는 부분:
  - 시뮬레이션 결과 로그 수집
  - "이 가중치로 했을 때 클리어율이 올랐다/내렸다" 통계
  - 가중치 미세 조정 제안

원리:
  현재 보드 상태 → 가능한 탭 N개 열거
  → 각 탭의 결과를 가상으로 시뮬레이션 (홀더에 차 추가, 매칭 체크)
  → 각 결과에 점수 부여
  → 최고 점수의 탭 선택

CarMatch 규칙:
  - 차를 탭하면 → 홀더에 해당 색상 추가
  - 홀더에 같은 색 3개 모이면 → 3개 제거 (매칭)
  - 홀더 7칸 다 차면 → 게임 오버
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

from .perception import BoardState, CarInfo


@dataclass
class SimResult:
    """시뮬레이션 결과."""
    car: CarInfo                    # 탭할 차
    score: float                    # 점수 (높을수록 좋음)
    holder_after: List[Optional[str]]  # 탭 후 홀더 상태
    holder_count_after: int         # 탭 후 홀더 사용 칸 수
    causes_match: bool              # 매칭이 발생하는가
    match_color: Optional[str]      # 매칭 색상
    reason: str                     # 선택 이유


class LookaheadSimulator:
    """홀더 시뮬레이터.

    사람이 코딩해야 하는 것: 게임 규칙 (match_count, holder_slots)
    AI가 튜닝하는 것: 점수 가중치 (weights)
    """

    def __init__(
        self,
        match_count: int = 3,
        holder_slots: int = 7,
        weights: Optional[dict] = None,
    ):
        self.match_count = match_count
        self.holder_slots = holder_slots

        # 점수 가중치 — 사람이 초기값 설정, Swarm이 미세 조정
        self.weights = weights or {
            "match_completion": 100,    # 매칭을 완성시키는 탭
            "match_2_setup": 30,        # 홀더에 같은 색 2개가 되는 탭
            "new_color_safe": 10,       # 새 색상이지만 홀더 여유 있음
            "new_color_danger": -50,    # 새 색상이고 홀더 위험
            "holder_overflow": -200,    # 홀더가 꽉 차는 탭
            "mystery_safe": 5,         # Mystery 차 (홀더 여유 있을 때)
            "mystery_danger": -100,    # Mystery 차 (홀더 위험할 때)
            "front_row_bonus": 5,      # 앞줄 차 보너스
            "stacked_penalty": -3,     # 스택 높은 차 페널티 (per stack)
        }

    def evaluate_all_moves(
        self, board: BoardState, holder: List[Optional[str]]
    ) -> List[SimResult]:
        """모든 가능한 탭을 시뮬레이션하고 점수 매김.

        Args:
            board: 현재 보드 상태
            holder: 현재 홀더 상태 (7칸)

        Returns:
            점수 내림차순으로 정렬된 SimResult 리스트
        """
        results = []

        for car in board.active_cars:
            result = self._simulate_tap(car, holder)
            results.append(result)

        # 점수 내림차순
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    def get_best_move(
        self, board: BoardState, holder: List[Optional[str]]
    ) -> Optional[SimResult]:
        """최선의 탭 1개 반환."""
        results = self.evaluate_all_moves(board, holder)
        return results[0] if results else None

    def _simulate_tap(
        self, car: CarInfo, holder: List[Optional[str]]
    ) -> SimResult:
        """차 1대를 탭했을 때의 결과 시뮬레이션.

        CarMatch 규칙:
        1. 차를 탭하면 홀더에 해당 색상이 추가됨
        2. 같은 색 3개가 모이면 제거됨
        3. 홀더 7칸이 다 차면 게임 오버
        """
        # 홀더 복사
        new_holder = holder[:]
        color = car.color

        # Mystery 차 처리
        if car.is_mystery or color == "unknown":
            holder_count = sum(1 for h in new_holder if h is not None)
            if holder_count <= 3:
                return SimResult(
                    car=car, score=self.weights["mystery_safe"],
                    holder_after=new_holder,
                    holder_count_after=holder_count,
                    causes_match=False, match_color=None,
                    reason="mystery car, holder safe",
                )
            else:
                return SimResult(
                    car=car, score=self.weights["mystery_danger"],
                    holder_after=new_holder,
                    holder_count_after=holder_count,
                    causes_match=False, match_color=None,
                    reason="mystery car, holder dangerous",
                )

        # 홀더에 색상 추가
        added = False
        for i in range(self.holder_slots):
            if new_holder[i] is None:
                new_holder[i] = color
                added = True
                break

        if not added:
            # 홀더 꽉 참 → 게임 오버
            return SimResult(
                car=car, score=self.weights["holder_overflow"],
                holder_after=new_holder,
                holder_count_after=self.holder_slots,
                causes_match=False, match_color=None,
                reason=f"OVERFLOW: {color} car would fill holder",
            )

        # 매칭 체크
        color_count_in_holder = sum(1 for h in new_holder if h == color)
        causes_match = color_count_in_holder >= self.match_count

        if causes_match:
            # 매칭 발생 → 3개 제거
            removed = 0
            for i in range(self.holder_slots):
                if new_holder[i] == color and removed < self.match_count:
                    new_holder[i] = None
                    removed += 1
            # None을 뒤로 밀기 (홀더 정렬)
            new_holder = self._compact_holder(new_holder)

        holder_count_after = sum(1 for h in new_holder if h is not None)

        # 점수 계산
        score = self._calculate_score(
            car, color, causes_match,
            color_count_in_holder, holder_count_after
        )

        # 이유 생성
        if causes_match:
            reason = f"MATCH: {color} x{self.match_count} → holder {holder_count_after}"
        elif color_count_in_holder == self.match_count - 1:
            reason = f"SETUP: {color} {color_count_in_holder}/{self.match_count} in holder"
        else:
            reason = f"NEW: {color} → holder {holder_count_after}/{self.holder_slots}"

        return SimResult(
            car=car, score=score,
            holder_after=new_holder,
            holder_count_after=holder_count_after,
            causes_match=causes_match,
            match_color=color if causes_match else None,
            reason=reason,
        )

    def _calculate_score(
        self, car: CarInfo, color: str,
        causes_match: bool, color_count: int,
        holder_count_after: int,
    ) -> float:
        """탭의 점수 계산.

        사람이 설계하는 부분: 이 점수 공식.
        "어떤 탭이 좋은 탭인가?"의 기준을 정의.
        """
        score = 0.0

        # 매칭 완성
        if causes_match:
            score += self.weights["match_completion"]

        # 2/3 셋업 (매칭 직전)
        elif color_count == self.match_count - 1:
            score += self.weights["match_2_setup"]

        # 새 색상
        elif holder_count_after <= 4:
            score += self.weights["new_color_safe"]
        else:
            score += self.weights["new_color_danger"]

        # 오버플로우 위험
        if holder_count_after >= self.holder_slots:
            score += self.weights["holder_overflow"]

        # 앞줄 보너스 (y가 클수록 앞줄)
        score += (car.y / 1920) * self.weights["front_row_bonus"]

        # 스택 페널티
        if car.stacked > 1:
            score += (car.stacked - 1) * self.weights["stacked_penalty"]

        return score

    def _compact_holder(self, holder: List[Optional[str]]) -> List[Optional[str]]:
        """홀더에서 None을 뒤로 밀기."""
        filled = [h for h in holder if h is not None]
        return filled + [None] * (self.holder_slots - len(filled))


# ---------------------------------------------------------------------------
# 2수 Lookahead (Depth 2)
# ---------------------------------------------------------------------------
class DeepLookahead(LookaheadSimulator):
    """2수 앞까지 보는 확장 시뮬레이터.

    1수 시뮬레이션으로 상위 K개 후보 선택
    → 각 후보에 대해 2수째 최선을 시뮬레이션
    → 1수+2수 합산 점수로 최종 판단

    사람이 해야 하는 것:
      - top_k 값 조정 (너무 크면 느림, 작으면 놓침)
      - depth2_discount 조정 (2수째를 얼마나 중시할지)
    """

    def __init__(self, top_k: int = 5, depth2_discount: float = 0.5, **kwargs):
        super().__init__(**kwargs)
        self.top_k = top_k
        self.depth2_discount = depth2_discount

    def get_best_move_deep(
        self, board: BoardState, holder: List[Optional[str]]
    ) -> Optional[SimResult]:
        """2수 탐색으로 최선의 탭 선택."""
        # 1수 시뮬레이션
        first_moves = self.evaluate_all_moves(board, holder)
        if not first_moves:
            return None

        best_result = None
        best_total = float("-inf")

        # 상위 K개만 2수 탐색
        for move1 in first_moves[:self.top_k]:
            total_score = move1.score

            # 2수: 이 차를 탭한 후, 남은 차 중 최선은?
            remaining_cars = [
                c for c in board.active_cars
                if not (c.x == move1.car.x and c.y == move1.car.y)
            ]

            if remaining_cars:
                # 가상 보드 생성
                virtual_board = BoardState(
                    screen_type="gameplay",
                    holder=move1.holder_after,
                    holder_count=move1.holder_count_after,
                    active_cars=remaining_cars,
                )
                second_moves = self.evaluate_all_moves(
                    virtual_board, move1.holder_after
                )
                if second_moves:
                    total_score += second_moves[0].score * self.depth2_discount

            if total_score > best_total:
                best_total = total_score
                # 1수째 결과에 2수 고려 점수 반영
                best_result = SimResult(
                    car=move1.car,
                    score=total_score,
                    holder_after=move1.holder_after,
                    holder_count_after=move1.holder_count_after,
                    causes_match=move1.causes_match,
                    match_color=move1.match_color,
                    reason=f"{move1.reason} [depth2: +{total_score - move1.score:.0f}]",
                )

        return best_result
