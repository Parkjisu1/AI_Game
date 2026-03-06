"""
ProfileBuilder -- Auto-Generate Game Profile from DiscoveryDB
==============================================================
Converts DiscoveryDB exploration results into:
- profile.yaml (game profile for VirtualPlayer)
- nav_graph.json (screen transition graph)
- screen_types.json (discovered screen types)
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


class ProfileBuilder:
    """Builds game profile from DiscoveryDB exploration data."""

    def __init__(
        self,
        game_id: str,
        package_name: str,
        genre: str = "unknown",
        output_dir: Optional[Path] = None,
    ):
        """
        Args:
            game_id: Game identifier (e.g. "carmatch").
            package_name: Android package name.
            genre: Detected genre (rpg, idle, puzzle, etc.).
            output_dir: Where to write output files. Defaults to
                        virtual_player/data/games/{game_id}/.
        """
        self.game_id = game_id
        self.package_name = package_name
        self.genre = genre

        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = (
                Path(__file__).parent.parent / "data" / "games" / game_id
            )

    def build_from_discovery(
        self,
        discovery_data: Dict[str, Any],
        screen_types: Optional[Dict[str, str]] = None,
        screen_width: int = 1080,
        screen_height: int = 1920,
        auto_builder=None,
        screenshots: Optional[List[Path]] = None,
    ) -> Dict[str, Path]:
        """
        Build all profile files from DiscoveryDB data.

        Args:
            discovery_data: Output of DiscoveryDB.to_dict().
            screen_types: {screen_name: description}. Auto-generated if None.
            screen_width: Device width.
            screen_height: Device height.

        Returns:
            Dict of {file_type: Path} for created files.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        created = {}

        # 0. AutoProfileBuilder: Vision-enhanced nav_graph + reference_db (optional)
        if auto_builder is not None:
            try:
                screenshot_paths = [str(p) for p in (screenshots or [])]
                auto_profile = auto_builder.build_from_discovery(
                    discovery_data, screenshot_paths)
                # Merge vision-detected screen_rois into discovery_data for downstream use
                discovery_data = dict(discovery_data)
                discovery_data["screen_rois"] = auto_profile.get("screen_rois", {})
                discovery_data["fallback_positions"] = auto_profile.get("fallback_positions", [])
                logger.info("AutoProfileBuilder completed -- %d ROIs detected",
                            len(auto_profile.get("screen_rois", {})))
            except Exception as e:
                logger.warning("AutoProfileBuilder failed (continuing without): %s", e)

        # 1. Screen types
        if screen_types is None:
            screen_types = self._infer_screen_types(discovery_data)
        st_path = self.output_dir / "screen_types.json"
        self._write_json(st_path, screen_types)
        created["screen_types"] = st_path

        # 2. Nav graph
        nav_graph = self._build_nav_graph(discovery_data)
        ng_path = self.output_dir / "nav_graph.json"
        self._write_json(ng_path, nav_graph)
        created["nav_graph"] = ng_path

        # 3. Profile YAML
        profile = self._build_profile(
            discovery_data, screen_types, screen_width, screen_height
        )
        if _YAML_AVAILABLE:
            profile_path = self.output_dir / "profile.yaml"
            with open(profile_path, "w", encoding="utf-8") as f:
                yaml.dump(profile, f, default_flow_style=False, allow_unicode=True)
        else:
            profile_path = self.output_dir / "profile.json"
            self._write_json(profile_path, profile)
        created["profile"] = profile_path

        logger.info("Profile built for %s: %s", self.game_id,
                     {k: str(v) for k, v in created.items()})
        return created

    def _infer_screen_types(self, data: Dict) -> Dict[str, str]:
        """Infer screen types from DiscoveryDB screens."""
        screens = data.get("screens", {})
        types = {}
        for name, sdata in screens.items():
            tags = sdata.get("tags", [])
            elements = sdata.get("elements", [])
            elem_count = len(elements)
            visits = sdata.get("visit_count", 0)
            desc = f"Auto-discovered ({elem_count} elements, {visits} visits)"
            if tags:
                desc += f" [{', '.join(tags)}]"
            types[name] = desc
        return types

    def _build_nav_graph(self, data: Dict) -> Dict:
        """Convert DiscoveryDB transitions to NavGraph format."""
        screens = data.get("screens", {})
        transitions = data.get("transitions", [])

        nodes = {}
        for name, sdata in screens.items():
            elements = sdata.get("elements", [])
            nodes[name] = {
                "screen_type": name,
                "description": f"Auto-discovered screen",
                "visit_count": sdata.get("visit_count", 0),
                "elements": [
                    {"label": e.get("label", ""), "x": e["x"], "y": e["y"]}
                    for e in elements[:10]  # Top 10 elements
                ],
            }

        edges = []
        for t in transitions:
            via = t.get("via", [])
            action = via[0] if via else {"action": "unknown"}
            edges.append({
                "source": t["from_screen"],
                "target": t["to_screen"],
                "action": action,
                "success_count": t.get("success_count", 0),
            })

        return {"nodes": nodes, "edges": edges}

    def _build_profile(
        self,
        data: Dict,
        screen_types: Dict[str, str],
        screen_width: int,
        screen_height: int,
    ) -> Dict:
        """Build game profile dict."""
        screens = data.get("screens", {})

        # Detect home/hub screen (most visited or tagged)
        home_screen = "lobby"
        max_visits = 0
        for name, sdata in screens.items():
            visits = sdata.get("visit_count", 0)
            tags = sdata.get("tags", [])
            if "hub" in tags or "main" in tags:
                home_screen = name
                break
            if visits > max_visits:
                max_visits = visits
                home_screen = name

        profile: Dict[str, Any] = {
            "game_id": self.game_id,
            "game_name": self.game_id.replace("_", " ").title(),
            "package": self.package_name,
            "genre": self.genre,
            "screen_width": screen_width,
            "screen_height": screen_height,
            "home_screen": home_screen,
            "auto_generated": True,
            "screen_types": list(screen_types.keys()),
            "metadata": {
                "source": "auto_bootstrap",
                "screens_discovered": len(screens),
                "transitions_discovered": len(data.get("transitions", [])),
            },
        }

        # Merge AutoProfileBuilder artifacts if present
        if data.get("screen_rois"):
            profile["screen_rois"] = data["screen_rois"]
        if data.get("fallback_positions"):
            profile["fallback_positions"] = data["fallback_positions"]

        return profile

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        """Atomic JSON write."""
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        try:
            tmp.replace(path)
        except OSError:
            if path.exists():
                path.unlink()
            tmp.rename(path)
