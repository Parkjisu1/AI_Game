"""Auto profile builder: screenshots + discovery -> profile.yaml + nav_graph + reference_db."""
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class AutoProfileBuilder:
    """Automatically builds game profile from bootstrap exploration results.

    Wraps ProfileBuilder with optional Vision LLM screen labeling and ROI detection.
    When vision_fn is None, falls back to discovery_db metadata (screen_id labels).
    """

    def __init__(
        self,
        game_id: str,
        genre: str,
        data_dir: str,
        vision_fn=None,
    ):
        """
        Args:
            game_id: Game identifier (e.g., "ash_n_veil")
            genre: Detected genre (e.g., "rpg", "puzzle")
            data_dir: Path to game data dir (e.g., virtual_player/data/games/ash_n_veil/)
            vision_fn: Optional callable(image_path, prompt) -> str for LLM vision
        """
        self._game_id = game_id
        self._genre = genre
        self._data_dir = Path(data_dir)
        self._vision_fn = vision_fn

    def build_from_discovery(self, discovery_db: dict, screenshots: List[str]) -> dict:
        """
        Build profile from DiscoveryDB data and screenshots.

        Args:
            discovery_db: DiscoveryDB export dict (screens, transitions, elements)
            screenshots: List of screenshot paths from exploration

        Returns:
            profile dict (ready to save as YAML)
        """
        profile = {
            "game_id": self._game_id,
            "genre": self._genre,
            "input_method": "auto",
            "fallback_positions": [],
        }

        # 1. Select representative screenshots (most diverse screens)
        representative = self._select_representative(screenshots, discovery_db, max_count=15)

        # 2. Label screens via Vision LLM (if available)
        screen_labels = {}
        if self._vision_fn and representative:
            screen_labels = self._label_screens(representative)

        # 3. Build nav_graph from discovery transitions
        nav_graph = self._build_nav_graph(discovery_db, screen_labels)

        # 4. Build reference_db from clustered screenshots
        ref_db = self._build_reference_db(discovery_db, screen_labels)

        # 5. Detect gauges and ROIs via Vision LLM
        screen_rois = {}
        if self._vision_fn and representative:
            screen_rois = self._detect_rois(representative, screen_labels)

        profile["screen_rois"] = screen_rois

        # 6. Extract fallback positions from discovery safe_taps
        safe_positions = discovery_db.get("safe_taps", [])
        if safe_positions:
            profile["fallback_positions"] = safe_positions[:5]

        # Save artifacts
        self._save_nav_graph(nav_graph)
        self._save_reference_db(ref_db)

        logger.info(
            "AutoProfileBuilder: built profile for '%s' -- %d screens, %d edges, %d ROIs",
            self._game_id,
            len(nav_graph.get("nodes", {})),
            len(nav_graph.get("edges", [])),
            len(screen_rois),
        )

        return profile

    def _select_representative(
        self, screenshots: List[str], discovery_db: dict, max_count: int = 15
    ) -> List[str]:
        """Select most diverse screenshots for LLM labeling."""
        screens = discovery_db.get("screens", {})
        selected = []
        seen_types = set()

        # First pass: one per discovered screen type (using stored screenshot path)
        for screen_id, info in screens.items():
            screenshot = info.get("screenshot")
            if screenshot and os.path.exists(screenshot) and screen_id not in seen_types:
                selected.append(screenshot)
                seen_types.add(screen_id)
                if len(selected) >= max_count:
                    break

        # Second pass: fill remaining from screenshots list
        for path in screenshots:
            if path not in selected and os.path.exists(path):
                selected.append(path)
                if len(selected) >= max_count:
                    break

        return selected

    def _label_screens(self, screenshots: List[str]) -> Dict[str, str]:
        """Use Vision LLM to label each screenshot with screen type."""
        labels = {}
        prompt = (
            "This is a mobile game screenshot. Classify this screen into ONE category:\n"
            "battle, lobby, town, menu_shop, menu_equipment, menu_inventory, "
            "menu_skill, stage_select, dialog, popup, loading, title, settings, "
            "gacha, quest, map, board, level_select, result\n"
            "Reply with ONLY the category name, nothing else."
        )

        for path in screenshots:
            try:
                label = self._vision_fn(path, prompt).strip().lower()
                labels[path] = label
                logger.info("Labeled %s -> %s", os.path.basename(path), label)
            except Exception as e:
                logger.warning("Failed to label %s: %s", path, e)

        return labels

    def _build_nav_graph(self, discovery_db: dict, screen_labels: dict) -> dict:
        """Build nav_graph.json from discovery transitions."""
        screens = discovery_db.get("screens", {})
        transitions = discovery_db.get("transitions", [])

        nodes = {}
        edges = []

        # Create nodes from discovered screens
        for screen_id, info in screens.items():
            screenshot = info.get("screenshot", "")
            label = screen_labels.get(screenshot, screen_id)
            nodes[label] = {
                "screen_type": label,
                "visit_count": info.get("visit_count", 1),
                "sample_screenshots": [],
                "elements": [],
                "in_screen_actions": info.get("actions", []),
            }

        # Create edges from transitions (deduplicated)
        seen_edges = set()
        for t in transitions:
            from_screen = t.get("from", t.get("from_screen", "unknown"))
            to_screen = t.get("to", t.get("to_screen", "unknown"))
            via = t.get("via", [])
            action = via[0] if via else t.get("action", {})

            edge_key = f"{from_screen}->{to_screen}"
            if edge_key not in seen_edges:
                # Normalize action to NavigationGraph schema
                if isinstance(action, dict):
                    norm_action = {
                        "action_type": action.get("action_type", action.get("action", "tap")),
                        "x": action.get("x", 0),
                        "y": action.get("y", 0),
                        "x2": action.get("x2", 0),
                        "y2": action.get("y2", 0),
                        "description": action.get("description", action.get("label", "")),
                        "element": action.get("element", ""),
                        "category": action.get("category", "navigation"),
                    }
                else:
                    norm_action = action
                edges.append({
                    "source": from_screen,
                    "target": to_screen,
                    "action": norm_action,
                    "success_count": t.get("success_count", t.get("count", 1)),
                })
                seen_edges.add(edge_key)

        return {"nodes": nodes, "edges": edges}

    def _build_reference_db(self, discovery_db: dict, screen_labels: dict) -> dict:
        """Build reference_db from discovery screen fingerprints."""
        screens = discovery_db.get("screens", {})
        ref_db: Dict[str, Any] = {"screens": {}}

        for screen_id, info in screens.items():
            screenshot = info.get("screenshot", "")
            label = screen_labels.get(screenshot, screen_id)
            fingerprint = info.get("fingerprint")

            if fingerprint:
                ref_db["screens"][label] = {
                    "fingerprint": fingerprint,
                    "screenshot": screenshot,
                    "confidence": 0.7,
                }

        return ref_db

    def _detect_rois(self, screenshots: List[str], screen_labels: dict) -> dict:
        """Use Vision LLM to detect gauge bars, text regions, buttons."""
        rois = {}
        prompt = (
            "This mobile game screenshot shows a game screen. "
            "Identify these UI elements with pixel coordinates [x, y, width, height]:\n"
            "1. HP bar (if visible)\n"
            "2. MP/Energy bar (if visible)\n"
            "3. XP bar (if visible)\n"
            "4. Gold/currency display\n"
            "5. Level display\n"
            "Reply in JSON format: {\"hp_bar\": [x,y,w,h], \"mp_bar\": [x,y,w,h], ...}\n"
            "Only include elements you can clearly see. Use null for unseen elements."
        )

        for path in screenshots:
            label = screen_labels.get(path, "unknown")
            if label == "unknown":
                continue

            try:
                result = self._vision_fn(path, prompt)
                json_match = re.search(r'\{[^}]+\}', result)
                if json_match:
                    roi_data = json.loads(json_match.group())
                    screen_roi = {}
                    for key, coords in roi_data.items():
                        if coords and isinstance(coords, list) and len(coords) == 4:
                            screen_roi[key] = {
                                "region": coords,
                                "type": "gauge" if "bar" in key else "ocr",
                            }
                    if screen_roi:
                        rois[label] = screen_roi
            except Exception as e:
                logger.warning("ROI detection failed for %s: %s", path, e)

        return rois

    def _save_nav_graph(self, nav_graph: dict) -> None:
        """Save nav_graph.json to game data directory."""
        self._data_dir.mkdir(parents=True, exist_ok=True)
        path = self._data_dir / "nav_graph.json"
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(nav_graph, f, indent=2, ensure_ascii=False)
        try:
            tmp.replace(path)
        except OSError:
            if path.exists():
                path.unlink()
            tmp.rename(path)
        logger.info("Saved nav_graph to %s", path)

    def _save_reference_db(self, ref_db: dict) -> None:
        """Save reference_db/index.json to game data directory."""
        ref_dir = self._data_dir / "reference_db"
        ref_dir.mkdir(parents=True, exist_ok=True)
        path = ref_dir / "index.json"
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(ref_db, f, indent=2, ensure_ascii=False)
        try:
            tmp.replace(path)
        except OSError:
            if path.exists():
                path.unlink()
            tmp.rename(path)
        logger.info("Saved reference_db to %s", path)

    def refine_profile(self, profile: dict, play_log: dict) -> dict:
        """Refine profile after first play session using failure analysis."""
        stuck_screens = play_log.get("stuck_screens", [])

        # Add ROI stubs for screens where stuck occurred (for future vision labeling)
        for stuck in stuck_screens:
            screen = stuck.get("screen_type", "unknown")
            if screen not in profile.get("screen_rois", {}):
                logger.info("Refinement: adding ROI stub for stuck screen '%s'", screen)
                profile.setdefault("screen_rois", {})[screen] = {}

        return profile
