"""
Vision API via Claude CLI
==========================
Calls Claude CLI with game screenshots for gameplay decisions.
Uses batch analysis: one call → multiple planned moves.

Returns dict: {action, x, y, description}
Compatible with VisionQuery node's vision_fn interface.
"""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class VisionPlanner:
    """Batch vision planner using Claude CLI.

    One Claude call analyzes the screen and returns N planned moves.
    Subsequent calls return cached moves until the plan is exhausted
    or the screen changes.
    """

    def __init__(
        self,
        claude_cmd: str = "C:/Users/user/AppData/Roaming/npm/claude.cmd",
        model: str = "haiku",
        game_context: str = "",
        batch_size: int = 4,
        timeout: int = 60,
    ):
        self.claude_cmd = claude_cmd
        self.model = model
        self.game_context = game_context
        self.batch_size = batch_size
        self.timeout = timeout

        # Cached plan
        self._plan: List[Dict[str, Any]] = []
        self._plan_screen: str = ""
        self._plan_tick: int = 0
        self._call_count: int = 0
        self._cache_hits: int = 0

    def __call__(
        self,
        screenshot_path: Any,
        screen_type: str,
        ocr_texts: List[str],
    ) -> Optional[Dict[str, Any]]:
        """vision_fn interface: (path, screen_type, texts) -> action dict."""

        # If screen changed, invalidate plan
        if screen_type != self._plan_screen:
            self._plan.clear()

        # Return cached move if available
        if self._plan:
            move = self._plan.pop(0)
            self._cache_hits += 1
            logger.info("VisionPlanner: cached move %s (%d remaining)",
                        move.get("description", "?"), len(self._plan))
            return move

        # No cached moves — call Claude CLI
        result = self._query_claude(screenshot_path, screen_type, ocr_texts)
        if not result:
            return None

        self._plan_screen = screen_type

        # Parse batch response
        moves = result if isinstance(result, list) else [result]
        if not moves:
            return None

        # First move returned immediately, rest cached
        first = moves[0]
        self._plan = moves[1:]
        return first

    def _query_claude(
        self,
        screenshot_path: Any,
        screen_type: str,
        ocr_texts: List[str],
    ) -> Optional[List[Dict[str, Any]]]:
        """Call Claude CLI with screenshot for batch move planning."""
        path = Path(screenshot_path)
        if not path.exists():
            return None

        self._call_count += 1
        prompt = self._build_prompt(screen_type, ocr_texts)

        try:
            start = time.time()
            # Use Read tool to view the screenshot via Claude CLI
            # Forward slashes for cross-platform compatibility
            img_path = str(path).replace("\\", "/")
            full_prompt = (
                f"Use the Read tool to view the screenshot at {img_path}. "
                f"Then respond with ONLY the JSON array.\n\n{prompt}"
            )
            cmd = [
                self.claude_cmd,
                "-p", full_prompt,
                "--model", self.model,
                "--output-format", "json",
                "--max-turns", "2",
                "--tools", "Read",
                "--allowedTools", "Read",
            ]

            # Clean env to avoid inherited Claude Code vars and bad API keys
            import os
            env = os.environ.copy()
            for key in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
                env.pop(key, None)
            # Remove placeholder API keys so CLI uses its own subscription auth
            api_key = env.get("ANTHROPIC_API_KEY", "")
            if not api_key or not api_key.startswith("sk-ant-"):
                env.pop("ANTHROPIC_API_KEY", None)

            r = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.timeout,
                text=True,
                env=env,
            )

            elapsed = time.time() - start
            logger.info("VisionPlanner: Claude CLI took %.1fs (call #%d)",
                        elapsed, self._call_count)

            if r.returncode != 0:
                logger.warning("VisionPlanner: CLI error: %s", r.stderr[:200])
                return None

            return self._parse_response(r.stdout)

        except subprocess.TimeoutExpired:
            logger.warning("VisionPlanner: CLI timeout (%ds)", self.timeout)
            return None
        except Exception as e:
            logger.warning("VisionPlanner: error: %s", e)
            return None

    def _build_prompt(self, screen_type: str, ocr_texts: List[str]) -> str:
        """Build the prompt for Claude."""
        ocr_str = ", ".join(ocr_texts[:15]) if ocr_texts else "none"

        prompt = f"""You are an AI game player. Analyze this game screenshot and plan your next {self.batch_size} moves.

GAME CONTEXT: {self.game_context}
CURRENT SCREEN: {screen_type}
OCR TEXT ON SCREEN: {ocr_str}
SCREEN SIZE: 1080 x 1920 pixels

RULES:
- Return a JSON array of {self.batch_size} moves (or fewer if game state will change)
- Each move: {{"action": "tap", "x": <int>, "y": <int>, "description": "<what and why>"}}
- Supported actions: "tap", "back", "wait"
- For "wait": {{"action": "wait", "seconds": 2, "description": "waiting for animation"}}
- x range: 0-1080, y range: 0-1920
- Be precise with coordinates — tap on the exact UI element
- NEVER tap on ads or purchase buttons
- If this is a puzzle/match game, analyze the board and plan strategic moves

Return ONLY the JSON array, no other text. Example:
[
  {{"action": "tap", "x": 540, "y": 700, "description": "tap blue car in center"}},
  {{"action": "wait", "seconds": 3, "description": "wait for car animation"}},
  {{"action": "tap", "x": 250, "y": 500, "description": "tap matching blue car"}}
]"""
        return prompt

    def _parse_response(self, raw: str) -> Optional[List[Dict[str, Any]]]:
        """Parse Claude CLI JSON response into move list."""
        try:
            # Claude CLI --output-format json wraps in {"result": "..."}
            outer = json.loads(raw)
            text = outer.get("result", raw) if isinstance(outer, dict) else raw
        except json.JSONDecodeError:
            text = raw

        # Find JSON array in the text
        text = text.strip()

        # Try to extract JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            json_str = text[start:end + 1]
            try:
                moves = json.loads(json_str)
                if isinstance(moves, list):
                    # Validate each move
                    valid = []
                    for m in moves:
                        if not isinstance(m, dict):
                            continue
                        action = m.get("action", "tap")
                        if action == "wait":
                            valid.append({
                                "action": "wait",
                                "seconds": m.get("seconds", 2),
                                "description": m.get("description", "wait"),
                            })
                        elif action in ("tap", "back"):
                            x = int(m.get("x", 540))
                            y = int(m.get("y", 960))
                            # Clamp to screen bounds
                            x = max(0, min(1080, x))
                            y = max(0, min(1920, y))
                            valid.append({
                                "action": action,
                                "x": x,
                                "y": y,
                                "description": m.get("description", "vision_move"),
                            })
                    return valid if valid else None
            except json.JSONDecodeError:
                pass

        # Fallback: try to parse single object
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                m = json.loads(text[start:end + 1])
                if isinstance(m, dict) and "x" in m:
                    return [m]
            except json.JSONDecodeError:
                pass

        logger.warning("VisionPlanner: could not parse response: %s", text[:200])
        return None

    def get_stats(self) -> Dict[str, Any]:
        return {
            "api_calls": self._call_count,
            "cache_hits": self._cache_hits,
            "pending_plan": len(self._plan),
        }


# ============================================================
# Game-specific contexts
# ============================================================

GAME_CONTEXTS = {
    "carmatch": (
        "CarMatch is a 3D car parking puzzle on a 1080x1920 screen. "
        "BOARD: A parking lot viewed from above with colored cars in rows/lanes. "
        "Colors: red, orange, yellow, green, cyan, blue, purple, pink. "
        "HOLDER: 7 slots at the bottom (~y1430). Cars you tap go here. "
        "MATCHING: When 3 same-color cars are in the holder, they match and vanish. "
        "LOSE: If all 7 slots fill with no match possible, 'Out of Space!' = fail. "
        "GIMMICKS: "
        "1) BLOCKED CARS: Cars behind others cannot be tapped. Clear the front car first. "
        "2) STACKED SPOTS: A number (4, 5) on a spot means cars stacked there. "
        "   Tap to take the top car; number decreases. Colors underneath are hidden. "
        "3) MYSTERY CARS (?): Unknown color until tapped. Risky - only tap with 3+ empty holder slots. "
        "4) LOCKED CARS: Have a lock icon. Unlock after clearing certain matches. "
        "BOOSTERS (bottom bar ~y1830): "
        "- Undo (1st, free x2): Sends last car back to board. Use on bad moves. "
        "- Magnet (2nd, free x1): Auto-matches 3 same-color cars from board. Save for emergencies. "
        "- Shuffle (3rd, 900 coins): Randomizes board. DO NOT USE - costs coins. "
        "- Rotate (4th, 600 coins): Rearranges cars. DO NOT USE - costs coins. "
        "STRATEGY: "
        "- Count visible colors before tapping. Tap cars that complete a 3-match first. "
        "- If 2 red in holder, find the 3rd red on board immediately. "
        "- Never have more than 2 incomplete colors in holder at once. "
        "- Clear front-row and stacked spots first to reveal hidden cars. "
        "- If holder has 5+ cars with no match coming, use free Undo immediately. "
        "LIVES & ADS: "
        "- Limited lives. Each fail costs 1 life. "
        "- If lives = 0, 'More Lives' popup appears. Watch ad for +1 life (tap green button). "
        "- After win/lose, ads may appear. Close with X (top-right or top-left). Never tap Install. "
        "FLOW: Lobby (tap green Level N) -> Gameplay (tap cars) -> Win (tap Continue) -> Lobby. "
        "On fail: tap X to skip 'Add Space', X to skip 'Play On', then 'Try Again' or X to lobby."
    ),
    "default": (
        "A mobile game. Look at the screen and decide what to tap. "
        "Prefer interactive elements (buttons, game objects). "
        "Avoid ads and purchase buttons."
    ),
}


def create_vision_fn(
    game_id: str = "default",
    claude_cmd: str = "C:/Users/user/AppData/Roaming/npm/claude.cmd",
    model: str = "haiku",
    batch_size: int = 4,
    data_dir: str = "",
) -> VisionPlanner:
    """Factory: create a vision_fn for use with PlayEngineV2."""
    context = GAME_CONTEXTS.get(game_id, GAME_CONTEXTS["default"])

    # Inject experience summary if available
    if data_dir:
        from ..episode_recorder import ExperienceLearner
        from pathlib import Path
        try:
            learner = ExperienceLearner(game_id, Path(data_dir))
            summary = learner.get_cached_summary()
            if summary:
                context = context + " " + summary
        except Exception:
            pass

    return VisionPlanner(
        claude_cmd=claude_cmd,
        model=model,
        game_context=context,
        batch_size=batch_size,
    )
