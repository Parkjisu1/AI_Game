"""Puzzle solver: board state -> best move coordinates."""
import logging
from typing import Optional, Tuple, List

from ..perception.board_reader import BoardState

logger = logging.getLogger(__name__)


class PuzzleSolver:
    """Solves puzzle games given board state."""

    def solve(self, board: BoardState, game_type: str = "carmatch") -> Optional[Tuple[int, int]]:
        """
        Find best move. Returns (row, col) grid position to tap, or None.
        """
        if game_type == "carmatch":
            return self._solve_carmatch(board)
        elif game_type == "match3":
            return self._solve_match3(board)
        else:
            return self._solve_generic(board)

    # ------------------------------------------------------------------
    # Solvers per game type
    # ------------------------------------------------------------------

    def _solve_carmatch(self, board: BoardState) -> Optional[Tuple[int, int]]:
        """
        CarMatch: holder에 있는 색상과 같은 색 차량을 보드에서 찾아 탭.
        holder 비어있으면 보드에서 가장 많은 색상 선택.
        """
        if not board.holder:
            return self._pick_most_common(board)

        holder_colors = [c for c in board.holder if c not in ("empty", "unknown")]
        if not holder_colors:
            return self._pick_most_common(board)

        # Priority: match first holder slot color (bottom rows first -- easier to clear)
        target_color = holder_colors[0]
        pos = self._find_color(board, target_color)
        if pos is not None:
            logger.info("CarMatch: target=%s, found at %s", target_color, pos)
            return pos

        # Try remaining holder colors
        for color in holder_colors[1:]:
            pos = self._find_color(board, color)
            if pos is not None:
                logger.info("CarMatch: fallback color=%s, found at %s", color, pos)
                return pos

        # No holder color on board -- pick any non-empty cell
        return self._pick_any(board)

    def _solve_match3(self, board: BoardState) -> Optional[Tuple[int, int]]:
        """
        Match3: check all adjacent swaps, find one that creates 3+ match.
        Returns the cell to tap (first of the swap pair).
        """
        best_score = 0
        best_pos: Optional[Tuple[int, int]] = None

        for r in range(board.rows):
            for c in range(board.cols):
                # Try swap right
                if c + 1 < board.cols:
                    score = self._eval_swap(board, r, c, r, c + 1)
                    if score > best_score:
                        best_score = score
                        best_pos = (r, c)
                # Try swap down
                if r + 1 < board.rows:
                    score = self._eval_swap(board, r, c, r + 1, c)
                    if score > best_score:
                        best_score = score
                        best_pos = (r, c)

        if best_score >= 3:
            logger.info("Match3: best swap at %s, score=%d", best_pos, best_score)
            return best_pos
        return self._pick_any(board)

    def _solve_generic(self, board: BoardState) -> Optional[Tuple[int, int]]:
        """Generic: pick most common non-empty color."""
        return self._pick_most_common(board)

    # ------------------------------------------------------------------
    # Match3 helpers
    # ------------------------------------------------------------------

    def _eval_swap(self, board: BoardState, r1: int, c1: int, r2: int, c2: int) -> int:
        """Evaluate a swap: return number of tiles in matches it would create."""
        # Deep copy grid with swap applied
        grid = [row[:] for row in board.grid]
        grid[r1][c1], grid[r2][c2] = grid[r2][c2], grid[r1][c1]

        matches = 0

        # Horizontal runs
        for r in range(board.rows):
            count = 1
            for c in range(1, board.cols):
                if grid[r][c] == grid[r][c - 1] and grid[r][c] not in ("empty", "unknown"):
                    count += 1
                else:
                    if count >= 3:
                        matches += count
                    count = 1
            if count >= 3:
                matches += count

        # Vertical runs
        for c in range(board.cols):
            count = 1
            for r in range(1, board.rows):
                if grid[r][c] == grid[r - 1][c] and grid[r][c] not in ("empty", "unknown"):
                    count += 1
                else:
                    if count >= 3:
                        matches += count
                    count = 1
            if count >= 3:
                matches += count

        return matches

    # ------------------------------------------------------------------
    # Cell selection helpers
    # ------------------------------------------------------------------

    def _find_color(self, board: BoardState, color: str) -> Optional[Tuple[int, int]]:
        """Find first occurrence of color scanning bottom-up (easier to clear)."""
        for r in range(board.rows - 1, -1, -1):
            for c in range(board.cols):
                if board.grid[r][c] == color:
                    return (r, c)
        return None

    def _pick_most_common(self, board: BoardState) -> Optional[Tuple[int, int]]:
        """Pick a cell with the most common color on the board."""
        color_count: dict = {}
        for r in range(board.rows):
            for c in range(board.cols):
                color = board.grid[r][c]
                if color not in ("empty", "unknown"):
                    color_count[color] = color_count.get(color, 0) + 1

        if not color_count:
            return None

        best_color = max(color_count, key=color_count.get)
        return self._find_color(board, best_color)

    def _pick_any(self, board: BoardState) -> Optional[Tuple[int, int]]:
        """Pick any non-empty cell."""
        for r in range(board.rows):
            for c in range(board.cols):
                if board.grid[r][c] not in ("empty", "unknown"):
                    return (r, c)
        return None
