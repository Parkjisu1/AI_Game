"""
2048 Game Brain
================
4x4 보드 기반 2048 게임 AI.
Expectimax 탐색 (depth 3) + 다중 휴리스틱 평가.

평가 함수:
- Snake-path weighted score (4가지 코너 중 최적)
- Monotonicity (행/열의 단조 증가/감소 유지)
- Smoothness (인접 타일 간 값 차이 최소화)
- Empty cell bonus (빈 칸 많을수록 유리)
- Merge potential (병합 가능한 인접 쌍)
- Max tile in corner bonus
"""

import math
import random
from typing import Any, Dict, List, Optional, Tuple

from .base import GameBrain, GameAction, GameState, TouchInput, ActionType


# ============================================================
# Constants
# ============================================================

BOARD_SIZE = 4
DIRECTIONS = ["up", "down", "left", "right"]
DIRECTION_KEYS = {
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
}

# Expectimax search depth (skill-based)
DEPTH_BY_SKILL = {
    # skill_level range -> search depth
    0.0: 1,
    0.3: 2,
    0.6: 3,
    0.8: 4,
}

# Snake-path weight matrices for all 4 corners.
# Values use powers of 4 for stronger gradient.
_BASE_WEIGHTS = [
    [4**15, 4**14, 4**13, 4**12],
    [4**8,  4**9,  4**10, 4**11],
    [4**7,  4**6,  4**5,  4**4],
    [4**0,  4**1,  4**2,  4**3],
]

def _make_weight_variants() -> List[List[List[float]]]:
    """4가지 코너 회전 weight matrix 생성."""
    w = _BASE_WEIGHTS
    variants = [w]
    # Horizontal flip (top-right corner)
    variants.append([row[::-1] for row in w])
    # Vertical flip (bottom-left corner)
    variants.append(w[::-1])
    # Both flips (bottom-right corner)
    variants.append([row[::-1] for row in w[::-1]])
    return variants

WEIGHT_VARIANTS = _make_weight_variants()

# Evaluation weights
W_WEIGHTED    = 1.0
W_EMPTY       = 2.7    # log2 기반 빈칸 보너스
W_SMOOTHNESS  = 0.1
W_MONOTONIC   = 1.0
W_MERGE       = 0.7
W_CORNER      = 0.5


# ============================================================
# Board helpers
# ============================================================

def _parse_board(raw: Any) -> List[List[int]]:
    """원시 보드 데이터를 4x4 정수 행렬로 변환."""
    if isinstance(raw, list) and len(raw) == BOARD_SIZE:
        return [[int(cell) for cell in row] for row in raw]
    if isinstance(raw, dict) and "grid" in raw:
        return _parse_board(raw["grid"])
    if isinstance(raw, dict) and "cells" in raw:
        cells = raw["cells"]
        board = [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]
        for cell in cells:
            if cell and "position" in cell:
                r, c = cell["position"].get("x", 0), cell["position"].get("y", 0)
                board[c][r] = cell.get("value", 0)
        return board
    return [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]


def _get_score(board: List[List[int]]) -> float:
    """보드 타일 합."""
    return float(sum(cell for row in board for cell in row))


def _is_game_over(board: List[List[int]]) -> bool:
    """이동 가능한 방향이 없으면 게임 오버."""
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            if board[r][c] == 0:
                return False
            if c + 1 < BOARD_SIZE and board[r][c] == board[r][c + 1]:
                return False
            if r + 1 < BOARD_SIZE and board[r][c] == board[r + 1][c]:
                return False
    return True


def _merge_line(line: List[int]) -> Tuple[List[int], bool, int]:
    """한 줄 병합. (결과, 이동여부, 병합으로 얻은 점수) 반환."""
    non_zero = [x for x in line if x != 0]
    merged = []
    merge_score = 0
    skip = False

    for i in range(len(non_zero)):
        if skip:
            skip = False
            continue
        if i + 1 < len(non_zero) and non_zero[i] == non_zero[i + 1]:
            merged.append(non_zero[i] * 2)
            merge_score += non_zero[i] * 2
            skip = True
        else:
            merged.append(non_zero[i])

    result = merged + [0] * (len(line) - len(merged))
    moved = result != line
    return result, moved, merge_score


def _simulate_move(board: List[List[int]], direction: str) -> Optional[List[List[int]]]:
    """방향으로 이동 시뮬레이션. 이동 불가하면 None."""
    new_board = [row[:] for row in board]
    moved = False

    if direction == "left":
        for r in range(BOARD_SIZE):
            new_board[r], row_moved, _ = _merge_line(new_board[r])
            moved = moved or row_moved
    elif direction == "right":
        for r in range(BOARD_SIZE):
            merged, row_moved, _ = _merge_line(new_board[r][::-1])
            new_board[r] = merged[::-1]
            moved = moved or row_moved
    elif direction == "up":
        for c in range(BOARD_SIZE):
            col = [new_board[r][c] for r in range(BOARD_SIZE)]
            merged, col_moved, _ = _merge_line(col)
            for r in range(BOARD_SIZE):
                new_board[r][c] = merged[r]
            moved = moved or col_moved
    elif direction == "down":
        for c in range(BOARD_SIZE):
            col = [new_board[r][c] for r in range(BOARD_SIZE)][::-1]
            merged, col_moved, _ = _merge_line(col)
            merged = merged[::-1]
            for r in range(BOARD_SIZE):
                new_board[r][c] = merged[r]
            moved = moved or col_moved

    return new_board if moved else None


# ============================================================
# Evaluation functions
# ============================================================

def _weighted_score(board: List[List[int]]) -> float:
    """4가지 코너 snake-path 중 최고 점수."""
    best = 0.0
    for weights in WEIGHT_VARIANTS:
        s = 0.0
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                s += board[r][c] * weights[r][c]
        best = max(best, s)
    return best


def _empty_bonus(board: List[List[int]]) -> float:
    """빈 칸 수 기반 보너스 (log 스케일)."""
    empty = sum(1 for row in board for cell in row if cell == 0)
    if empty == 0:
        return -100000.0  # 빈 칸 없음 -> 큰 페널티
    return math.log2(empty) * 100000


def _smoothness(board: List[List[int]]) -> float:
    """인접 타일 간 값 차이의 합 (낮을수록 좋음, 음수 반환)."""
    penalty = 0.0
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            val = board[r][c]
            if val == 0:
                continue
            log_val = math.log2(val)
            # Right neighbor
            if c + 1 < BOARD_SIZE and board[r][c + 1] != 0:
                penalty -= abs(log_val - math.log2(board[r][c + 1]))
            # Down neighbor
            if r + 1 < BOARD_SIZE and board[r + 1][c] != 0:
                penalty -= abs(log_val - math.log2(board[r + 1][c]))
    return penalty * 10000


def _monotonicity(board: List[List[int]]) -> float:
    """행/열의 단조성 평가. 증가 또는 감소 방향 중 더 나은 쪽."""
    total = 0.0

    for r in range(BOARD_SIZE):
        inc = 0.0
        dec = 0.0
        for c in range(BOARD_SIZE - 1):
            cur = math.log2(board[r][c]) if board[r][c] > 0 else 0
            nxt = math.log2(board[r][c + 1]) if board[r][c + 1] > 0 else 0
            if cur > nxt:
                dec += nxt - cur
            else:
                inc += cur - nxt
        total += max(inc, dec)

    for c in range(BOARD_SIZE):
        inc = 0.0
        dec = 0.0
        for r in range(BOARD_SIZE - 1):
            cur = math.log2(board[r][c]) if board[r][c] > 0 else 0
            nxt = math.log2(board[r + 1][c]) if board[r + 1][c] > 0 else 0
            if cur > nxt:
                dec += nxt - cur
            else:
                inc += cur - nxt
        total += max(inc, dec)

    return total * 10000


def _merge_potential(board: List[List[int]]) -> float:
    """병합 가능한 인접 쌍 수."""
    count = 0
    for r in range(BOARD_SIZE):
        for c in range(BOARD_SIZE):
            val = board[r][c]
            if val == 0:
                continue
            if c + 1 < BOARD_SIZE and board[r][c + 1] == val:
                count += 1
            if r + 1 < BOARD_SIZE and board[r + 1][c] == val:
                count += 1
    return count * 10000


def _corner_bonus(board: List[List[int]]) -> float:
    """최대 타일이 코너에 있으면 보너스."""
    max_tile = max(cell for row in board for cell in row)
    corners = [board[0][0], board[0][3], board[3][0], board[3][3]]
    if max_tile in corners:
        return max_tile * 100
    return 0.0


def _evaluate(board: List[List[int]]) -> float:
    """종합 보드 평가."""
    return (
        W_WEIGHTED   * _weighted_score(board) +
        W_EMPTY      * _empty_bonus(board) +
        W_SMOOTHNESS * _smoothness(board) +
        W_MONOTONIC  * _monotonicity(board) +
        W_MERGE      * _merge_potential(board) +
        W_CORNER     * _corner_bonus(board)
    )


# ============================================================
# Expectimax search
# ============================================================

def _get_empty_cells(board: List[List[int]]) -> List[Tuple[int, int]]:
    """빈 칸 좌표 목록."""
    return [(r, c) for r in range(BOARD_SIZE) for c in range(BOARD_SIZE) if board[r][c] == 0]


def _expectimax(board: List[List[int]], depth: int, is_player: bool) -> float:
    """
    Expectimax 탐색.
    - Player node: max over 4 directions
    - Chance node: expected value over random tile spawns
    """
    if depth == 0 or _is_game_over(board):
        return _evaluate(board)

    if is_player:
        best = float("-inf")
        for direction in DIRECTIONS:
            new_board = _simulate_move(board, direction)
            if new_board is not None:
                val = _expectimax(new_board, depth - 1, False)
                best = max(best, val)
        return best if best != float("-inf") else _evaluate(board)
    else:
        # Chance node: random tile spawn (90% -> 2, 10% -> 4)
        empty = _get_empty_cells(board)
        if not empty:
            return _evaluate(board)

        # Optimization: sample at most 6 cells when too many empty
        if len(empty) > 6:
            sampled = random.sample(empty, 6)
        else:
            sampled = empty

        total = 0.0
        for r, c in sampled:
            for tile_val, prob in [(2, 0.9), (4, 0.1)]:
                new_board = [row[:] for row in board]
                new_board[r][c] = tile_val
                total += prob * _expectimax(new_board, depth - 1, True)

        return total / len(sampled)


# ============================================================
# Brain implementation
# ============================================================

class Brain2048(GameBrain):
    """2048 게임 AI 두뇌 (Expectimax + 다중 휴리스틱)."""

    def __init__(self, skill_level: float = 0.5):
        super().__init__(skill_level=skill_level)
        # Determine search depth from skill level
        self._depth = 1
        for threshold, depth in sorted(DEPTH_BY_SKILL.items()):
            if self.skill_level >= threshold:
                self._depth = depth

    def perceive(self, raw_state: Any) -> GameState:
        """원시 상태 -> GameState."""
        board = _parse_board(raw_state)
        max_tile = max(cell for row in board for cell in row) if board else 0

        return GameState(
            raw=raw_state,
            parsed={
                "board": board,
                "max_tile": max_tile,
                "empty_cells": sum(1 for row in board for cell in row if cell == 0),
            },
            score=_get_score(board),
            is_game_over=_is_game_over(board),
        )

    def decide(self, state: GameState) -> GameAction:
        """Expectimax로 최적 방향 결정."""
        board = state.parsed["board"]

        # Skill-based: high skill -> expectimax, low skill -> random
        if random.random() < self.skill_level:
            direction = self._expectimax_move(board)
        else:
            direction = self._random_valid_move(board)

        if direction is None:
            return GameAction(
                name="wait",
                description="No valid moves",
                confidence=0.0,
            )

        return GameAction(
            name=f"swipe_{direction}",
            description=f"Move tiles {direction}",
            confidence=self.skill_level,
            metadata={"direction": direction},
        )

    def translate_to_input(self, action: GameAction) -> List[TouchInput]:
        """방향 -> 키보드 입력."""
        direction = action.metadata.get("direction")
        if not direction or direction not in DIRECTION_KEYS:
            return []

        return [TouchInput(
            action_type=ActionType.KEY_PRESS,
            key=DIRECTION_KEYS[direction],
        )]

    def _expectimax_move(self, board: List[List[int]]) -> Optional[str]:
        """Expectimax 탐색으로 최적 방향 선택."""
        best_score = float("-inf")
        best_direction = None

        for direction in DIRECTIONS:
            new_board = _simulate_move(board, direction)
            if new_board is not None:
                score = _expectimax(new_board, self._depth, False)
                if score > best_score:
                    best_score = score
                    best_direction = direction

        return best_direction

    def _random_valid_move(self, board: List[List[int]]) -> Optional[str]:
        """유효한 랜덤 방향 선택."""
        valid = [d for d in DIRECTIONS if _simulate_move(board, d) is not None]
        return random.choice(valid) if valid else None
