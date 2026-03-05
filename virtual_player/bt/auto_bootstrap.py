"""
Auto Bootstrap -- Zero-Shot Game Learning
==========================================
Connects bootstrap modules to PlayEngineV2 for fully autonomous startup:

Phase 0 (Cold Start, ~5min):
  1. Launch game
  2. Take 20 screenshots while randomly tapping
  3. Cluster screenshots (pHash) → auto screen_types
  4. Vision AI labels each cluster → screen names
  5. Track tap→screen_change → auto nav_graph edges
  6. Detect genre from OCR + UI patterns

Phase 1 (Warm Play, ongoing):
  - PlayEngineV2 runs with auto-generated trees
  - OutcomeTracker records results
  - New screens auto-added to nav_graph + BT
  - Vision actions promoted to BT after 3 successes

After Phase 0, NO human input needed.
"""

import json
import logging
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AutoBootstrap:
    """Zero-shot game bootstrapper. Generates all configs needed for PlayEngineV2."""

    COLD_START_TAPS = 30        # Number of random taps during cold start
    TAP_WAIT = 2.0              # Wait after each tap for screen to settle
    CLUSTER_THRESHOLD = 12      # pHash hamming distance for same screen
    MIN_SCREENSHOTS = 15        # Minimum screenshots before building profile

    def __init__(
        self,
        game_id: str,
        package_name: str,
        data_dir: Path,
        screenshot_fn: Callable[[str], Optional[Path]],
        tap_fn: Callable[[int, int, float], None],
        back_fn: Optional[Callable[[], None]] = None,
        vision_fn: Optional[Callable] = None,
        screen_width: int = 1080,
        screen_height: int = 1920,
    ):
        self._game_id = game_id
        self._package = package_name
        self._data_dir = data_dir
        self._screenshot = screenshot_fn
        self._tap = tap_fn
        self._back_fn = back_fn
        self._vision_fn = vision_fn
        self._w = screen_width
        self._h = screen_height

        # Results
        self._screenshots: List[Path] = []
        self._screen_types: Dict[str, str] = {}
        self._nav_edges: List[Dict] = {}
        self._detected_genre: str = "unknown"

    def run(self) -> Dict[str, Any]:
        """Execute cold start bootstrap.

        Returns dict with:
          - nav_graph_path: Path to generated nav_graph.json
          - screen_types: {screen_type: description}
          - genre: Detected genre
          - screenshots: Number of screenshots taken
          - clusters: Number of unique screens found
        """
        print(f"[Bootstrap] Starting cold start for '{self._game_id}' ({self._package})")
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Phase 0a: Random exploration + screenshot collection
        print(f"[Bootstrap] Phase 0a: Collecting {self.COLD_START_TAPS} screenshots...")
        self._explore_and_collect()

        # Phase 0b: Cluster screenshots
        print(f"[Bootstrap] Phase 0b: Clustering {len(self._screenshots)} screenshots...")
        clusters = self._cluster_screenshots()
        print(f"[Bootstrap] Found {len(clusters)} unique screen clusters")

        # Phase 0c: Label clusters (Vision AI or auto-name)
        print(f"[Bootstrap] Phase 0c: Labeling screen clusters...")
        screen_types = self._label_clusters(clusters)
        self._screen_types = screen_types

        # Phase 0d: Detect genre
        print(f"[Bootstrap] Phase 0d: Detecting genre...")
        self._detected_genre = self._detect_genre()
        print(f"[Bootstrap] Genre: {self._detected_genre}")

        # Phase 0e: Build and save nav_graph
        print(f"[Bootstrap] Phase 0e: Building nav_graph...")
        nav_graph = self._build_nav_graph(clusters, screen_types)
        nav_path = self._data_dir / "nav_graph.json"
        nav_path.write_text(json.dumps(nav_graph, indent=2, ensure_ascii=False), encoding="utf-8")

        # Phase 0f: Save screen_types
        st_path = self._data_dir / "screen_types.json"
        st_path.write_text(json.dumps(screen_types, indent=2, ensure_ascii=False), encoding="utf-8")

        # Phase 0g: Save reference screenshots (first of each cluster)
        ref_dir = self._data_dir / "reference_db"
        ref_dir.mkdir(parents=True, exist_ok=True)
        for label, paths in clusters.items():
            if paths:
                import shutil
                dest = ref_dir / f"{label}_ref.png"
                shutil.copy2(str(paths[0]), str(dest))

        result = {
            "nav_graph_path": str(nav_path),
            "screen_types": screen_types,
            "genre": self._detected_genre,
            "screenshots": len(self._screenshots),
            "clusters": len(clusters),
        }

        print(f"[Bootstrap] Cold start complete:")
        print(f"  Screens: {len(screen_types)}")
        print(f"  Genre: {self._detected_genre}")
        print(f"  Nav graph: {nav_path}")

        return result

    # ------------------------------------------------------------------
    # Phase 0a: Exploration
    # ------------------------------------------------------------------

    def _explore_and_collect(self) -> None:
        """Random taps + screenshots to discover screens."""
        # Tap zones: avoid edges, focus on interactive areas
        zones = [
            # Center area (main content)
            (self._w * 0.2, self._h * 0.15, self._w * 0.8, self._h * 0.7),
            # Bottom bar (navigation)
            (self._w * 0.05, self._h * 0.85, self._w * 0.95, self._h * 0.95),
            # Top bar (back/close buttons)
            (self._w * 0.7, self._h * 0.02, self._w * 0.98, self._h * 0.1),
        ]

        last_screenshot = None
        transition_log: List[Dict] = []

        for i in range(self.COLD_START_TAPS):
            # Take screenshot BEFORE tap
            before_path = self._screenshot(f"boot_{i:03d}_before")
            if before_path:
                self._screenshots.append(before_path)

            # Pick random zone (60% center, 25% bottom, 15% top)
            r = random.random()
            if r < 0.6:
                zone = zones[0]
            elif r < 0.85:
                zone = zones[1]
            else:
                zone = zones[2]

            x = random.randint(int(zone[0]), int(zone[2]))
            y = random.randint(int(zone[1]), int(zone[3]))

            self._tap(x, y, self.TAP_WAIT)

            # Take screenshot AFTER tap
            after_path = self._screenshot(f"boot_{i:03d}_after")
            if after_path:
                self._screenshots.append(after_path)

                # Track potential transition
                if before_path:
                    transition_log.append({
                        "before": str(before_path),
                        "after": str(after_path),
                        "x": x, "y": y,
                        "index": i,
                    })

            # Occasionally press back (20% chance) to explore more screens
            if random.random() < 0.2 and self._back_fn:
                self._back_fn()
                time.sleep(1.0)
                back_path = self._screenshot(f"boot_{i:03d}_back")
                if back_path:
                    self._screenshots.append(back_path)

            print(f"  [{i+1}/{self.COLD_START_TAPS}] tap({x},{y}) -> {len(self._screenshots)} screenshots")

        # Save transition log for nav_graph building
        self._transition_log = transition_log

    # ------------------------------------------------------------------
    # Phase 0b: Clustering
    # ------------------------------------------------------------------

    def _cluster_screenshots(self) -> Dict[str, List[Path]]:
        """Cluster screenshots by visual similarity."""
        from ..bootstrap.screen_fingerprinter import ScreenFingerprinter

        fingerprinter = ScreenFingerprinter(
            threshold=self.CLUSTER_THRESHOLD,
            label_fn=None,  # Auto-label first, then rename with Vision
        )

        return fingerprinter.cluster_screenshots(self._screenshots)

    # ------------------------------------------------------------------
    # Phase 0c: Labeling
    # ------------------------------------------------------------------

    def _label_clusters(self, clusters: Dict[str, List[Path]]) -> Dict[str, str]:
        """Label each cluster with a meaningful screen type name."""
        if self._vision_fn:
            return self._label_with_vision(clusters)
        return self._label_auto(clusters)

    def _label_with_vision(self, clusters: Dict[str, List[Path]]) -> Dict[str, str]:
        """Use Vision AI to label clusters."""
        labels = {}
        prompt = (
            "This is a mobile game screenshot. Classify this screen into ONE of these categories:\n"
            "lobby, battle, town, menu_shop, menu_equipment, menu_inventory, "
            "menu_skill, stage_select, dialog, popup, loading, title, settings, "
            "gacha, quest, map, board, level_select, result, ad, unknown\n"
            "Reply with ONLY the category name."
        )

        rename_map = {}  # old_label -> new_label
        seen_labels = set()

        for old_label, paths in clusters.items():
            if not paths:
                continue
            try:
                result = self._vision_fn(paths[0], old_label, [])
                if result and isinstance(result, dict):
                    new_label = result.get("description", old_label).strip().lower()
                elif result and isinstance(result, str):
                    new_label = result.strip().lower()
                else:
                    new_label = old_label

                # Deduplicate
                if new_label in seen_labels:
                    new_label = f"{new_label}_{len(seen_labels)}"
                seen_labels.add(new_label)
                rename_map[old_label] = new_label
                labels[new_label] = f"Auto-labeled ({len(paths)} screenshots)"
            except Exception as e:
                logger.debug("Vision labeling failed for %s: %s", old_label, e)
                labels[old_label] = f"Auto-discovered ({len(paths)} screenshots)"

        return labels

    def _label_auto(self, clusters: Dict[str, List[Path]]) -> Dict[str, str]:
        """Auto-label without Vision AI (just numbered)."""
        return {
            label: f"Auto-discovered screen ({len(paths)} screenshots)"
            for label, paths in clusters.items()
        }

    # ------------------------------------------------------------------
    # Phase 0d: Genre detection
    # ------------------------------------------------------------------

    def _detect_genre(self) -> str:
        """Detect genre from collected data."""
        try:
            from ..bootstrap.genre_detector import GenreDetector

            # Collect OCR texts from screenshots
            ocr_texts = []
            try:
                from ..perception.ocr_reader import OCRReader
                import cv2
                ocr = OCRReader()
                # Sample up to 5 screenshots for OCR
                samples = self._screenshots[:5]
                for path in samples:
                    img = cv2.imread(str(path))
                    if img is not None:
                        results = ocr.read_full_screen(img)
                        ocr_texts.extend([t[0] for t in results if isinstance(t[0], str)])
            except Exception:
                pass

            detector = GenreDetector()
            discovery_data = {
                "screens": {st: {"visit_count": 1} for st in self._screen_types},
                "transitions": getattr(self, "_transition_log", []),
            }
            genre, scores = detector.detect(discovery_data, ocr_texts)
            return genre
        except Exception as e:
            logger.warning("Genre detection failed: %s", e)
            return "casual"  # Safe default

    # ------------------------------------------------------------------
    # Phase 0e: Nav graph building
    # ------------------------------------------------------------------

    def _build_nav_graph(
        self, clusters: Dict[str, List[Path]], screen_types: Dict[str, str],
    ) -> Dict:
        """Build nav_graph from transition log + clusters."""
        from ..bootstrap.screen_fingerprinter import ScreenFingerprinter, _compute_phash, _hamming_distance

        # Build pHash index for cluster matching
        cluster_hashes: Dict[str, str] = {}  # label -> representative hash
        for label, paths in clusters.items():
            if paths:
                h = _compute_phash(paths[0])
                if h:
                    cluster_hashes[label] = h

        def _path_to_cluster(path: Path) -> str:
            """Map a screenshot path to its cluster label."""
            h = _compute_phash(path)
            if h is None:
                return "unknown"
            best_label = "unknown"
            best_dist = self.CLUSTER_THRESHOLD + 1
            for label, ch in cluster_hashes.items():
                dist = _hamming_distance(h, ch)
                if dist < best_dist:
                    best_dist = dist
                    best_label = label
            return best_label if best_dist <= self.CLUSTER_THRESHOLD else "unknown"

        # Build nodes
        nodes = {}
        for label, desc in screen_types.items():
            nodes[label] = {
                "screen_type": label,
                "visit_count": len(clusters.get(label, [])),
                "in_screen_actions": [],
                "elements": [],
            }

        # Build edges from transition log
        edges = []
        seen_edges = set()
        transition_log = getattr(self, "_transition_log", [])

        for t in transition_log:
            before_path = Path(t["before"])
            after_path = Path(t["after"])

            before_cluster = _path_to_cluster(before_path)
            after_cluster = _path_to_cluster(after_path)

            # Only add edge if screens are different (actual transition)
            if before_cluster != after_cluster and before_cluster != "unknown" and after_cluster != "unknown":
                edge_key = f"{before_cluster}->{after_cluster}"
                if edge_key not in seen_edges:
                    edges.append({
                        "source": before_cluster,
                        "target": after_cluster,
                        "action": {
                            "action_type": "tap",
                            "x": t["x"],
                            "y": t["y"],
                            "description": f"bootstrap tap at ({t['x']},{t['y']})",
                            "element": "",
                            "category": "navigation",
                        },
                        "success_count": 1,
                    })
                    seen_edges.add(edge_key)
                else:
                    # Increment success count for existing edge
                    for edge in edges:
                        if edge["source"] == before_cluster and edge["target"] == after_cluster:
                            edge["success_count"] += 1
                            break

        return {"nodes": nodes, "edges": edges}


def create_bootstrapped_engine(
    game_id: str,
    package_name: str,
    screenshot_fn: Callable,
    tap_fn: Callable,
    back_fn: Optional[Callable] = None,
    swipe_fn: Optional[Callable] = None,
    vision_fn: Optional[Callable] = None,
    persona: Any = None,
    play_duration: int = 300,
    screen_width: int = 1080,
    screen_height: int = 1920,
    relaunch_fn: Optional[Callable] = None,
    adb_fn: Optional[Callable] = None,
    data_dir: Optional[Path] = None,
) -> Any:
    """Convenience: run bootstrap + create PlayEngineV2 in one call.

    Usage:
        engine = create_bootstrapped_engine(
            game_id="my_game",
            package_name="com.example.game",
            screenshot_fn=..., tap_fn=..., back_fn=...,
        )
        result = engine.run()  # Fully autonomous from here
    """
    from ..config import DATA_DIR
    from ..play_engine_v2 import PlayEngineV2

    game_dir = data_dir or (DATA_DIR / "games" / game_id)

    # Check if bootstrap already done
    nav_path = game_dir / "nav_graph.json"
    st_path = game_dir / "screen_types.json"

    if nav_path.exists() and st_path.exists():
        print(f"[AutoBootstrap] Using existing data from {game_dir}")
        screen_types = json.loads(st_path.read_text(encoding="utf-8"))
        genre = "casual"  # Default; will be overridden by profile if exists
    else:
        # Run cold start
        bootstrap = AutoBootstrap(
            game_id=game_id,
            package_name=package_name,
            data_dir=game_dir,
            screenshot_fn=screenshot_fn,
            tap_fn=tap_fn,
            back_fn=back_fn,
            vision_fn=vision_fn,
            screen_width=screen_width,
            screen_height=screen_height,
        )
        result = bootstrap.run()
        genre = result["genre"]

    # Load nav_graph
    nav_graph = None
    try:
        from ..navigation.nav_graph import NavigationGraph
        if nav_path.exists():
            nav_graph = NavigationGraph.load(nav_path)
    except Exception:
        pass

    # Build screen classifier
    detect_screen_fn = lambda path: "unknown"
    try:
        from ..navigation.classifier import ScreenClassifier
        from ..brain.reference_db import ReferenceDB
        ref_dir = game_dir / "reference_db"
        if ref_dir.exists():
            ref_db = ReferenceDB.load(ref_dir)
            if st_path.exists():
                st = json.loads(st_path.read_text(encoding="utf-8"))
            else:
                st = {s: s for s in ref_db.get_screen_types()}
            classifier = ScreenClassifier(
                genre_screen_types=st,
                cache_dir=game_dir / "temp" / "classifier_cache",
                reference_db=ref_db,
            )
            detect_screen_fn = lambda path: classifier.classify(path).screen_type
    except Exception:
        pass

    # OCR
    read_text_fn = lambda path: []
    try:
        from ..perception.ocr_reader import OCRReader
        import cv2
        ocr = OCRReader()
        def _read(path):
            img = cv2.imread(str(path))
            return ocr.read_full_screen(img) if img is not None else []
        read_text_fn = _read
    except Exception:
        pass

    # Create engine
    engine = PlayEngineV2(
        genre=genre,
        screenshot_fn=screenshot_fn,
        tap_fn=tap_fn,
        detect_screen_fn=detect_screen_fn,
        read_text_fn=read_text_fn,
        play_duration=play_duration,
        persona=persona,
        nav_graph=nav_graph,
        back_fn=back_fn,
        swipe_fn=swipe_fn,
        relaunch_fn=relaunch_fn,
        vision_fn=vision_fn,
        temp_dir=game_dir / "temp" / "play_v2",
        cache_dir=game_dir / "bt_cache",
        input_method="input_tap",
        game_package=package_name,
        adb_fn=adb_fn,
        screen_width=screen_width,
        screen_height=screen_height,
    )

    return engine
