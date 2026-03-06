"""Board state reader: screenshot -> grid of cell colors/types."""
import cv2
import numpy as np
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict

logger = logging.getLogger(__name__)


@dataclass
class BoardState:
    grid: List[List[str]]           # 2D grid of cell types (color names or "empty")
    rows: int
    cols: int
    holder: Optional[List[str]] = None  # holding area (CarMatch holder slots)
    raw_colors: Optional[List[List[Tuple[int, int, int]]]] = None  # HSV values per cell


class BoardReader:
    """Reads puzzle board state from screenshots."""

    # Default color map: HSV ranges -> color names
    DEFAULT_COLOR_MAP = {
        "red":    {"h_range": (0, 10),   "s_min": 80, "v_min": 80},
        "red2":   {"h_range": (170, 180), "s_min": 80, "v_min": 80},  # red wraps around hue
        "orange": {"h_range": (10, 25),  "s_min": 80, "v_min": 80},
        "yellow": {"h_range": (25, 35),  "s_min": 80, "v_min": 80},
        "green":  {"h_range": (35, 85),  "s_min": 80, "v_min": 80},
        "cyan":   {"h_range": (85, 100), "s_min": 80, "v_min": 80},
        "blue":   {"h_range": (100, 130), "s_min": 80, "v_min": 80},
        "purple": {"h_range": (130, 170), "s_min": 80, "v_min": 80},
    }

    def __init__(self, color_map: Optional[Dict] = None):
        self._color_map = color_map or self.DEFAULT_COLOR_MAP

    def read_board(self, screenshot_path: str, board_config: dict) -> Optional[BoardState]:
        """
        Read board state from screenshot.

        board_config keys:
            board_rect: (x, y, w, h) -- board area on screen
            rows: int
            cols: int
            holder_rect: (x, y, w, h) -- optional holder area
            holder_slots: int -- number of holder slots
            color_map: optional override
        """
        img = cv2.imread(screenshot_path)
        if img is None:
            logger.warning("BoardReader: could not read screenshot: %s", screenshot_path)
            return None

        # Allow per-call color map override
        color_map_override = board_config.get("color_map")
        if color_map_override:
            self._color_map = color_map_override

        rect = board_config.get("board_rect", (0, 0, img.shape[1], img.shape[0]))
        rows = board_config.get("rows", 8)
        cols = board_config.get("cols", 8)

        x, y, w, h = rect
        board_img = img[y:y + h, x:x + w]
        hsv_img = cv2.cvtColor(board_img, cv2.COLOR_BGR2HSV)

        cell_h = h // rows
        cell_w = w // cols

        grid = []
        raw_colors = []
        for r in range(rows):
            row = []
            color_row = []
            for c in range(cols):
                # Sample center of cell
                cy = r * cell_h + cell_h // 2
                cx = c * cell_w + cell_w // 2
                # Sample 5×5 area around center
                y1 = max(0, cy - 2)
                y2 = min(hsv_img.shape[0], cy + 3)
                x1 = max(0, cx - 2)
                x2 = min(hsv_img.shape[1], cx + 3)

                sample = hsv_img[y1:y2, x1:x2]
                avg_hsv = tuple(int(v) for v in np.mean(sample, axis=(0, 1)))
                color_row.append(avg_hsv)

                color_name = self._classify_color(avg_hsv)
                row.append(color_name)
            grid.append(row)
            raw_colors.append(color_row)

        # Read holder if configured
        holder = None
        holder_rect = board_config.get("holder_rect")
        holder_slots = board_config.get("holder_slots", 0)
        if holder_rect and holder_slots > 0:
            holder = self._read_holder(img, holder_rect, holder_slots)

        return BoardState(
            grid=grid,
            rows=rows,
            cols=cols,
            holder=holder,
            raw_colors=raw_colors,
        )

    def _read_holder(self, img: np.ndarray, holder_rect: tuple, slots: int) -> List[str]:
        """Read holder/hand area colors."""
        x, y, w, h = holder_rect
        holder_img = img[y:y + h, x:x + w]
        hsv_img = cv2.cvtColor(holder_img, cv2.COLOR_BGR2HSV)

        slot_w = w // slots
        result = []
        for i in range(slots):
            cx = i * slot_w + slot_w // 2
            cy = h // 2
            sample = hsv_img[max(0, cy - 2):cy + 3, max(0, cx - 2):cx + 3]
            avg_hsv = tuple(int(v) for v in np.mean(sample, axis=(0, 1)))
            result.append(self._classify_color(avg_hsv))
        return result

    def _classify_color(self, hsv: tuple) -> str:
        """Classify HSV value to color name."""
        h, s, v = hsv
        if s < 40 or v < 40:
            return "empty"

        for name, cfg in self._color_map.items():
            h_lo, h_hi = cfg["h_range"]
            if (h_lo <= h <= h_hi
                    and s >= cfg.get("s_min", 50)
                    and v >= cfg.get("v_min", 50)):
                if name == "red2":
                    return "red"
                return name
        return "unknown"

    def board_to_screen_coords(self, row: int, col: int, board_config: dict) -> Tuple[int, int]:
        """Convert board grid position to screen tap coordinates."""
        x, y, w, h = board_config["board_rect"]
        cell_h = h // board_config["rows"]
        cell_w = w // board_config["cols"]
        screen_x = x + col * cell_w + cell_w // 2
        screen_y = y + row * cell_h + cell_h // 2
        return screen_x, screen_y
