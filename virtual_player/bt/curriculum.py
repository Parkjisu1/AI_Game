"""
Curriculum -- Structured Game Teaching System
==============================================
Defines what a human must teach, validates completeness,
and converts teachings into BT nodes + nav_graph.

Teaching is done via YAML curriculum file:

```yaml
game_id: carmatch
package: com.grandgames.carmatch
input_method: monkey  # or input_tap

core_loop:
  - lobby
  - gameplay
  - win
  - lobby

screens:
  lobby:
    description: "Main menu with Play button"
    actions:
      - name: tap_play
        type: tap
        x: 551
        y: 1498
        target: gameplay
        description: "Start a level"

  gameplay:
    description: "Puzzle board with cars"
    actions:
      - name: tap_car
        type: tap
        x: 540
        y: 700
        description: "Tap a car to send to holder"
    wait_behavior: "Game auto-progresses, just tap cars"

  win:
    description: "Level complete screen"
    actions:
      - name: tap_continue
        type: tap
        x: 540
        y: 1400
        target: lobby

  fail:
    description: "Game over - Out of Space"
    actions:
      - name: tap_retry
        type: tap
        x: 540
        y: 1200
        target: gameplay
      - name: tap_quit
        type: tap
        x: 540
        y: 1400
        target: lobby

danger_zones:
  - region: [0, 1700, 1080, 220]
    reason: "Booster area - may cost currency"
  - keywords: ["purchase", "buy", "구매", "$", "₩"]
    reason: "Real money purchase"

genre: puzzle
```

The curriculum is:
1. Written by human (or AI-assisted via screenshots)
2. Validated for completeness (all core_loop screens defined?)
3. Converted to nav_graph + BT nodes
4. Merged into PlayEngineV2 config
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# Required fields for a valid curriculum
REQUIRED_FIELDS = ["game_id", "package", "screens", "core_loop"]
REQUIRED_SCREEN_FIELDS = ["description"]


class CurriculumValidationError(Exception):
    pass


class Curriculum:
    """Parsed and validated game curriculum."""

    def __init__(self, data: Dict[str, Any]):
        self.game_id: str = data["game_id"]
        self.package: str = data["package"]
        self.input_method: str = data.get("input_method", "input_tap")
        self.genre: str = data.get("genre", "casual")
        self.core_loop: List[str] = data["core_loop"]
        self.screens: Dict[str, Dict] = data["screens"]
        self.danger_zones: List[Dict] = data.get("danger_zones", [])
        self._raw = data

    @classmethod
    def load(cls, path: Path) -> "Curriculum":
        """Load curriculum from YAML file."""
        try:
            import yaml
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
        except ImportError:
            # Fallback: try JSON
            data = json.loads(path.read_text(encoding="utf-8"))
        return cls(data)

    @classmethod
    def from_dict(cls, data: Dict) -> "Curriculum":
        return cls(data)

    def validate(self) -> List[str]:
        """Validate curriculum completeness. Returns list of issues (empty = valid)."""
        issues = []

        # Check required fields
        for field in REQUIRED_FIELDS:
            if field not in self._raw:
                issues.append(f"Missing required field: {field}")

        # Check all core_loop screens are defined
        for screen in self.core_loop:
            if screen not in self.screens:
                issues.append(f"Core loop screen '{screen}' not defined in screens")

        # Check each screen has required fields
        for screen_name, screen_data in self.screens.items():
            for field in REQUIRED_SCREEN_FIELDS:
                if field not in screen_data:
                    issues.append(f"Screen '{screen_name}' missing '{field}'")

            # Check actions have coordinates
            for action in screen_data.get("actions", []):
                if action.get("type") == "tap":
                    if "x" not in action or "y" not in action:
                        issues.append(
                            f"Screen '{screen_name}' action '{action.get('name', '?')}' "
                            f"missing x/y coordinates")

        # Check core_loop has at least 2 screens
        if len(self.core_loop) < 2:
            issues.append("Core loop must have at least 2 screens")

        # Check no orphan screens (screens with no actions and not in core_loop)
        for screen_name, screen_data in self.screens.items():
            actions = screen_data.get("actions", [])
            if not actions and screen_name not in self.core_loop:
                issues.append(f"Screen '{screen_name}' has no actions and is not in core_loop")

        return issues

    def get_completeness_score(self) -> float:
        """Return 0.0~1.0 completeness score."""
        total = 0
        passed = 0

        # Core loop defined?
        total += 1
        if len(self.core_loop) >= 2:
            passed += 1

        # All core_loop screens defined?
        for screen in self.core_loop:
            total += 1
            if screen in self.screens:
                passed += 1

        # Each screen has actions?
        for screen_name, screen_data in self.screens.items():
            total += 1
            if screen_data.get("actions"):
                passed += 1

        # Danger zones defined?
        total += 1
        if self.danger_zones:
            passed += 1

        # Genre specified?
        total += 1
        if self.genre != "casual":  # non-default
            passed += 1

        return passed / total if total > 0 else 0.0

    def to_nav_graph(self) -> Dict:
        """Convert curriculum to nav_graph.json format."""
        nodes = {}
        edges = []

        for screen_name, screen_data in self.screens.items():
            # Build in_screen_actions
            in_screen_actions = []
            for action in screen_data.get("actions", []):
                if "target" not in action:  # In-screen action (no transition)
                    in_screen_actions.append({
                        "element": action.get("name", "unknown"),
                        "category": "interaction",
                        "action_type": action.get("type", "tap"),
                        "x": action.get("x", 540),
                        "y": action.get("y", 960),
                        "description": action.get("description", ""),
                    })

            nodes[screen_name] = {
                "screen_type": screen_name,
                "description": screen_data.get("description", ""),
                "visit_count": 0,
                "in_screen_actions": in_screen_actions,
                "elements": [a.get("name", "") for a in screen_data.get("actions", [])],
            }

            # Build edges from actions with targets
            for action in screen_data.get("actions", []):
                target = action.get("target")
                if target:
                    edges.append({
                        "source": screen_name,
                        "target": target,
                        "action": {
                            "action_type": action.get("type", "tap"),
                            "x": action.get("x", 540),
                            "y": action.get("y", 960),
                            "description": action.get("description", ""),
                            "element": action.get("name", ""),
                            "category": "navigation",
                        },
                        "success_count": 5,  # High confidence (human-taught)
                    })

        return {"nodes": nodes, "edges": edges}

    def to_screen_types(self) -> Dict[str, str]:
        """Convert to screen_types.json format."""
        return {
            name: data.get("description", f"Screen: {name}")
            for name, data in self.screens.items()
        }

    def to_danger_config(self) -> Dict:
        """Convert danger zones to SafetyGuard config."""
        return {
            "blocked_regions": [
                dz for dz in self.danger_zones if "region" in dz
            ],
            "blocked_keywords": [
                kw
                for dz in self.danger_zones if "keywords" in dz
                for kw in dz["keywords"]
            ],
        }

    def save_all(self, data_dir: Path) -> Dict[str, Path]:
        """Save all generated configs to game data directory.

        Returns dict of {config_name: path}.
        """
        data_dir.mkdir(parents=True, exist_ok=True)
        saved = {}

        # nav_graph.json
        nav_path = data_dir / "nav_graph.json"
        nav_path.write_text(
            json.dumps(self.to_nav_graph(), indent=2, ensure_ascii=False),
            encoding="utf-8")
        saved["nav_graph"] = nav_path

        # screen_types.json
        st_path = data_dir / "screen_types.json"
        st_path.write_text(
            json.dumps(self.to_screen_types(), indent=2, ensure_ascii=False),
            encoding="utf-8")
        saved["screen_types"] = st_path

        # curriculum.json (raw backup)
        cur_path = data_dir / "curriculum.json"
        cur_path.write_text(
            json.dumps(self._raw, indent=2, ensure_ascii=False),
            encoding="utf-8")
        saved["curriculum"] = cur_path

        # danger_config.json
        danger = self.to_danger_config()
        if danger["blocked_regions"] or danger["blocked_keywords"]:
            danger_path = data_dir / "danger_config.json"
            danger_path.write_text(
                json.dumps(danger, indent=2, ensure_ascii=False),
                encoding="utf-8")
            saved["danger_config"] = danger_path

        logger.info("Curriculum saved to %s: %s", data_dir, list(saved.keys()))
        return saved


def interactive_teach(
    screenshot_fn,
    tap_fn,
    vision_fn=None,
    game_id: str = "",
    package: str = "",
) -> Dict:
    """AI-assisted interactive teaching session.

    Takes screenshots, asks Vision AI to describe them,
    and builds curriculum interactively.

    Returns curriculum dict ready for Curriculum.from_dict().
    """
    screens = {}
    core_loop = []
    transitions = []

    print("=" * 60)
    print("TEACHING MODE")
    print("=" * 60)
    print("I'll take screenshots and you tell me what each screen is.")
    print("Type 'done' when finished.\n")

    screen_count = 0
    while True:
        # Take screenshot
        path = screenshot_fn(f"teach_{screen_count:03d}")
        if not path:
            print("Screenshot failed. Retrying...")
            continue

        # Vision AI description (if available)
        ai_description = ""
        if vision_fn:
            try:
                result = vision_fn(path, "unknown", [])
                if result and isinstance(result, dict):
                    ai_description = result.get("description", "")
            except Exception:
                pass

        if ai_description:
            print(f"\nAI sees: {ai_description}")

        # Ask user (this is a placeholder - in practice, the user
        # would interact through Claude Code conversation)
        screen_count += 1

    return {
        "game_id": game_id,
        "package": package,
        "screens": screens,
        "core_loop": core_loop,
    }
