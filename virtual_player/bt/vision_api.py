"""
Vision API via Claude CLI
==========================
Calls Claude CLI with game screenshots for gameplay decisions.
Uses batch analysis: one call -> multiple planned moves.
Tracks failed taps and feeds them back to avoid repeating mistakes.

Returns dict: {action, x, y, description}
Compatible with VisionQuery node's vision_fn interface.
"""

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class VisionPlanner:
    """Batch vision planner using Claude CLI.

    One Claude call analyzes the screen and returns N planned moves.
    Subsequent calls return cached moves until the plan is exhausted
    or the screen changes. Tracks failed taps to avoid repeating them.
    """

    def __init__(
        self,
        claude_cmd: str = "C:/Users/user/AppData/Roaming/npm/claude.cmd",
        model: str = "claude-haiku-4-5-20251001",
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
        self._call_count: int = 0
        self._cache_hits: int = 0

        # Failed tap tracking (reset on screen change)
        self._failed_taps: List[Dict[str, Any]] = []
        self._consecutive_fails: int = 0

    def __call__(
        self,
        screenshot_path: Any,
        screen_type: str,
        ocr_texts: List[str],
    ) -> Optional[Dict[str, Any]]:
        """vision_fn interface: (path, screen_type, texts) -> action dict."""

        # If screen changed, reset everything
        if screen_type != self._plan_screen:
            if self._plan_screen:
                print(f"[AI] Screen changed: {self._plan_screen} -> {screen_type}, replanning")
            self._plan.clear()
            self._failed_taps.clear()
            self._consecutive_fails = 0

        # Return cached move if available
        if self._plan:
            move = self._plan.pop(0)
            self._cache_hits += 1
            desc = move.get("description", "?")
            action = move.get("action", "?")
            if action == "tap":
                print(f"[AI] Cached move ({len(self._plan)} left): "
                      f"tap ({move['x']},{move['y']}) - {desc}")
            elif action == "wait":
                pass  # Don't spam wait messages
            return move

        # No cached moves - call Claude CLI
        print(f"[AI] Analyzing screenshot... (this takes ~20-30s)")
        result = self._query_claude(screenshot_path, screen_type, ocr_texts)
        if not result:
            self._consecutive_fails += 1
            print(f"[AI] Analysis failed (attempt {self._consecutive_fails}/3)")
            if self._consecutive_fails >= 3:
                print(f"[AI] Falling back to random tap")
                return self._fallback_tap(screen_type)
            return None

        self._plan_screen = screen_type
        self._consecutive_fails = 0

        # Parse batch response
        moves = result if isinstance(result, list) else [result]
        if not moves:
            return None

        tap_count = sum(1 for m in moves if m.get("action") == "tap")
        print(f"[AI] Got {tap_count} tap moves planned:")
        for m in moves:
            if m.get("action") == "tap":
                print(f"  -> ({m['x']},{m['y']}): {m.get('description','?')}")

        # First move returned immediately, rest cached
        first = moves[0]
        self._plan = moves[1:]
        return first

    def report_tap_failed(self, x: int, y: int, description: str = "") -> None:
        """Called by engine when a tap didn't change the screen."""
        self._failed_taps.append({"x": x, "y": y, "description": description})
        # Invalidate remaining cached plan since it was based on wrong assumptions
        self._plan.clear()

    def _fallback_tap(self, screen_type: str) -> Dict[str, Any]:
        """Generate a fallback tap when Vision AI keeps failing."""
        import random
        # For gameplay: tap in the car board area (y: 200-1300), avoid holder area
        if screen_type == "gameplay":
            # Avoid previously failed coordinates
            for _ in range(10):
                x = random.randint(50, 1030)
                y = random.randint(200, 1200)
                if not self._is_near_failed(x, y):
                    return {"action": "tap", "x": x, "y": y,
                            "description": "fallback: random board tap"}
        return {"action": "tap", "x": 540, "y": 700,
                "description": "fallback: center tap"}

    def _is_near_failed(self, x: int, y: int, threshold: int = 80) -> bool:
        """Check if coordinates are near a previously failed tap."""
        for f in self._failed_taps[-10:]:  # Only check last 10
            if abs(f["x"] - x) < threshold and abs(f["y"] - y) < threshold:
                return True
        return False

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
            img_path = str(path).replace("\\", "/")
            full_prompt = (
                f"Use the Read tool to view the screenshot at {img_path}. "
                f"Then respond with ONLY the JSON array.\n\n{prompt}"
            )

            # Clean env
            env = os.environ.copy()
            for key in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
                env.pop(key, None)
            api_key = env.get("ANTHROPIC_API_KEY", "")
            if not api_key or not api_key.startswith("sk-ant-"):
                env.pop("ANTHROPIC_API_KEY", None)
            env["PYTHONIOENCODING"] = "utf-8"

            # Pipe prompt via stdin to avoid cmd.exe special char issues
            r = subprocess.run(
                [
                    self.claude_cmd,
                    "-p",
                    "--model", self.model,
                    "--output-format", "json",
                    "--max-turns", "2",
                    "--tools", "Read",
                    "--allowedTools", "Read",
                ],
                input=full_prompt,
                capture_output=True,
                timeout=self.timeout,
                encoding="utf-8",
                env=env,
                cwd=tempfile.gettempdir(),
            )

            elapsed = time.time() - start
            print(f"VisionPlanner: CLI {elapsed:.1f}s (call #{self._call_count})")

            if r.returncode != 0:
                err = r.stderr[:300] if r.stderr else "(no stderr)"
                out = r.stdout[:300] if r.stdout else "(no stdout)"
                print(f"VisionPlanner: CLI error (rc={r.returncode}): {out}")
                return None

            return self._parse_response(r.stdout)

        except subprocess.TimeoutExpired:
            print(f"VisionPlanner: CLI timeout ({self.timeout}s)")
            return None
        except Exception as e:
            print(f"VisionPlanner: error: {e}")
            return None

    def _build_prompt(self, screen_type: str, ocr_texts: List[str]) -> str:
        """Build the prompt for Claude with failed-tap feedback."""
        ocr_str = ", ".join(ocr_texts[:15]) if ocr_texts else "none"

        # Build failed taps context
        failed_context = ""
        if self._failed_taps:
            failed_list = [f"({f['x']},{f['y']})" for f in self._failed_taps[-8:]]
            failed_context = (
                f"\n\nFAILED TAPS (these coordinates did NOT work, "
                f"the car was blocked or nothing happened): {', '.join(failed_list)}"
                f"\nDo NOT tap these areas again. Find DIFFERENT cars to tap."
            )

        prompt = f"""Analyze this 1080x1920 pixel game screenshot and plan moves.

COORDINATE REFERENCE POINTS (use these to calibrate your coordinates):
- "Level N" text: center ~(540, 120)
- Coin display (top-left): ~(60, 50)
- Board top edge: ~y=250
- Board bottom edge: ~y=1300
- Board left edge: ~x=30, right edge: ~x=1050
- Holder slots (7 boxes): y=1400, spread from x=130 to x=950
- Booster buttons: y=1830, x=108/324/540/756/972
- Cars are 3D models, each roughly 100-130px wide, 80-120px tall
- The board has parking lanes. Cars face downward or sideways.

{self.game_context}
SCREEN: {screen_type} | OCR: {ocr_str}{failed_context}

RULES:
1. Check HOLDER (y~1400): count cars and their colors.
2. If 2 same-color in holder, find 3rd on board and tap it immediately.
3. ACTIVE vs BLOCKED: A car is ACTIVE (tappable) if you can see its EYES/FACE. If eyes are hidden behind another car, it is BLOCKED. ONLY tap cars with visible eyes!
4. Each car tap coordinate must be the CENTER of the car body (not the edge).
5. Keep holder under 5 cars. Use Undo booster (108, 1830) if 5+ with no match.
6. NEVER tap boosters at y>1800 unless using Undo.

Return JSON array of {self.batch_size} tap moves. Include 1.5s wait between taps.
Format: [{{"action":"tap","x":<0-1080>,"y":<0-1920>,"description":"<color> car <position>"}},{{"action":"wait","seconds":1.5,"description":"animation"}}]

ONLY output the JSON array."""
        return prompt

    def _parse_response(self, raw: str) -> Optional[List[Dict[str, Any]]]:
        """Parse Claude CLI JSON response into move list."""
        try:
            outer = json.loads(raw)
            text = outer.get("result", raw) if isinstance(outer, dict) else raw
        except json.JSONDecodeError:
            text = raw

        text = text.strip()

        # Try to extract JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            json_str = text[start:end + 1]
            try:
                moves = json.loads(json_str)
                if isinstance(moves, list):
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
                            x = max(0, min(1080, x))
                            y = max(0, min(1920, y))
                            # Skip if too close to previously failed taps
                            if not self._is_near_failed(x, y):
                                valid.append({
                                    "action": action,
                                    "x": x,
                                    "y": y,
                                    "description": m.get("description", "vision_move"),
                                })
                            else:
                                logger.info("VisionPlanner: skipping (%d,%d) near failed tap", x, y)
                    if valid:
                        # Auto-insert waits between taps for animation
                        spaced = []
                        for i, v in enumerate(valid):
                            spaced.append(v)
                            if v["action"] == "tap" and i < len(valid) - 1:
                                spaced.append({
                                    "action": "wait",
                                    "seconds": 1.5,
                                    "description": "wait for car animation",
                                })
                        return spaced
                    return None
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

        print(f"VisionPlanner: could not parse response: {text[:200]}")
        return None

    def get_stats(self) -> Dict[str, Any]:
        return {
            "api_calls": self._call_count,
            "cache_hits": self._cache_hits,
            "pending_plan": len(self._plan),
            "failed_taps": len(self._failed_taps),
        }


# ============================================================
# Game-specific contexts
# ============================================================

GAME_CONTEXTS = {
    "carmatch": (
        "CarMatch is a 3D car parking puzzle on a 1080x1920 screen. "
        "BOARD: A parking lot viewed from above with colored cars in rows/lanes. "
        "Cars are 3D models sitting in parking spots. "
        "Colors: red, orange, yellow, green, cyan, blue, purple, pink. "
        "HOLDER: 7 slots at the bottom of the screen (~y1350-1450). "
        "Cars you tap move from the board to the holder. "
        "MATCHING: When 3 same-color cars are in the holder, they vanish (matched). "
        "LOSE: If all 7 holder slots fill with no match possible = game over. "
        "BLOCKED vs ACTIVE CARS: "
        "- ACTIVE (tappable): You can see the car's EYES/FACE. These cars can be tapped. "
        "- BLOCKED (not tappable): The car's eyes are hidden behind another car in front. "
        "- ONLY tap cars whose eyes/face are visible! "
        "- To unblock a car, tap the car in front of it first. "
        "STACKED SPOTS: A number (2,3,4,5) on a spot means multiple cars stacked. "
        "Tap to take the top car; the number decreases. Colors underneath are hidden. "
        "MYSTERY CARS (?): Unknown color until tapped. Only tap when 3+ holder slots empty. "
        "LOCKED CARS: Have a lock icon. Unlock after clearing certain matches. "
        "BOOSTERS (bottom bar ~y1830): "
        "- Undo (leftmost): Sends last car back. Use when holder is filling up. "
        "- Magnet (2nd): Auto-matches 3 same-color from board. Save for emergencies. "
        "- Shuffle (3rd, 900 coins): DO NOT USE. "
        "- Rotate (4th, 600 coins): DO NOT USE. "
        "STRATEGY: "
        "- ALWAYS check holder first. If 2 same-color cars in holder, find the 3rd on board. "
        "- If no match possible, tap front-row cars to unblock cars behind them. "
        "- Keep holder under 5 cars. If 5+, use Undo booster immediately. "
        "- Tap cars that are clearly visible and unblocked. "
        "- After each tap, wait 1-2 seconds for the car animation to complete. "
        "FLOW: Lobby -> Gameplay -> Win/Fail -> Lobby. "
        "On fail: close popups with X buttons, then Try Again or back to lobby."
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
    model: str = "claude-haiku-4-5-20251001",
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
