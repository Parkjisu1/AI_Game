"""
TestOrchestrator -- 4-Phase AI Tester Pipeline
===============================================
Integrates Bootstrap -> Play -> Extract -> Journal into a single pipeline.

Usage:
    python -m virtual_player test --package com.grandgames.carmatch
"""

import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .config import (
    ADB_PATH, ADB_DEVICE, ADB_TEMP_DIR,
    KNOWLEDGE_DB, JOURNAL_DIR, DESIGN_DB_ROOT,
)
from .bootstrap.launch_manager import LaunchManager
from .bootstrap.screen_fingerprinter import ScreenFingerprinter
from .bootstrap.profile_builder import ProfileBuilder
from .bootstrap.auto_profile_builder import AutoProfileBuilder
from .bootstrap.genre_detector import GenreDetector
from .discovery.discovery_db import DiscoveryDB
from .discovery.exploration_engine import ExplorationEngine
from .discovery.safety_guard import SafetyGuard
from .genre.game_profile import get_schema_for_genre
from .knowledge.knowledge_base import KnowledgeBase
from .knowledge.transfer_engine import TransferEngine
from .journal.session_journal import SessionJournal
from .journal.pattern_extractor import PatternExtractor
from .navigation.classifier import ScreenClassifier
from .observers.aggregator import ParameterAggregator
from .observers.exporter import DesignDBExporter, DomainGroup
from .observers.generic_observers import (
    UIObserver, EconomyObserver, MonetizationObserver, ProgressionObserver,
)
from .perception.ocr_reader import OCRReader
from .perception.gauge_reader import GaugeReader
from .perception.region_registry import RegionRegistry
from .perception.state_reader import StateReader
from .play_engine import PlayEngine
from .genre.game_profile import GameProfile
from .input_strategy import InputStrategy

logger = logging.getLogger(__name__)

# Game data directory root (contains per-game profiles, nav graphs, reference DBs)
GAME_DATA_ROOT = Path(__file__).parent / "data" / "games"


class TestOrchestrator:
    """4-Phase pipeline: Bootstrap -> Play -> Extract -> Journal."""

    def __init__(
        self,
        package_name: str,
        adb_path: str = ADB_PATH,
        device: str = ADB_DEVICE,
        play_duration: int = 300,
        explore_taps: int = 40,
        dry_run: bool = False,
        game_id: str = "",
    ):
        """
        Args:
            package_name: Android package name.
            adb_path: Path to ADB executable.
            device: ADB device identifier.
            play_duration: Total play time in seconds (Phase 2).
            explore_taps: Number of exploration taps (Phase 1).
            dry_run: If True, don't write to Design DB.
            game_id: Override derived game ID (default: last segment of package_name).
        """
        self.package_name = package_name
        self.adb_path = adb_path
        self.device = device
        self.play_duration = play_duration
        self.explore_taps = explore_taps
        self.dry_run = dry_run

        # Derived game ID (override with explicit game_id)
        self.game_id = game_id if game_id else package_name.split(".")[-1]

        # State
        self._temp_dir = ADB_TEMP_DIR / self.game_id
        self._screenshot_count = 0
        self._phase_results: Dict[str, Dict] = {}
        self._errors: List[str] = []

        # Perception (lazy init after genre detection)
        self._classifier: Optional[ScreenClassifier] = None
        self._ocr_reader: Optional[OCRReader] = None
        self._state_reader: Optional[StateReader] = None

        # Game data (loaded from data/games/{game_id}/ if available)
        self._game_profile: Optional[GameProfile] = None
        self._game_data_dir: Optional[Path] = None
        self._existing_nav_graph_path: Optional[Path] = None
        self._existing_ref_db = None  # ReferenceDB or None

        # Input strategy (default: input_tap, updated after profile load)
        self._input_strategy = InputStrategy(self._adb, package_name, "input_tap")

        # OCR cache to avoid redundant reads of the same screenshot
        self._ocr_cache: Dict[str, List[Tuple[str, float, int, int]]] = {}

    def run(self) -> Dict[str, Any]:
        """
        Execute the full 4-phase pipeline.

        Returns:
            Session summary dict.
        """
        start_time = time.time()
        print("=" * 60)
        print(f"AI Tester: {self.package_name}")
        print(f"  Duration: {self.play_duration}s | Explore taps: {self.explore_taps} | Dry run: {self.dry_run}")
        print("=" * 60)
        logger.info("=" * 60)
        logger.info("AI Tester: %s", self.package_name)
        logger.info("=" * 60)

        self._temp_dir.mkdir(parents=True, exist_ok=True)

        # Phase 1: Bootstrap
        bootstrap_result = self._phase_bootstrap()
        self._phase_results["bootstrap"] = bootstrap_result

        genre = bootstrap_result.get("genre", "unknown")
        discovery_data = bootstrap_result.get("discovery_data", {})
        print(f"\n[Phase 1 DONE] Genre={genre} | Screens={len(discovery_data.get('screens', {}))} | "
              f"Status={bootstrap_result.get('status')}")

        # Phase 2: Play
        print(f"\n--- Phase 2: Play ({self.play_duration}s) ---")
        play_result = self._phase_play(genre, discovery_data)
        self._phase_results["play"] = play_result

        # Phase 3: Extract
        print(f"\n--- Phase 3: Extract ---")
        extract_result = self._phase_extract(genre, play_result)
        self._phase_results["extract"] = extract_result
        print(f"[Phase 3 DONE] Params={extract_result.get('param_count', 0)} | "
              f"Files={len(extract_result.get('files_written', []))}")

        # Phase 4: Journal
        print(f"\n--- Phase 4: Journal ---")
        duration = time.time() - start_time
        journal_result = self._phase_journal(genre, duration)
        self._phase_results["journal"] = journal_result

        # Update knowledge base
        self._update_knowledge(genre, bootstrap_result, extract_result)

        summary = {
            "package_name": self.package_name,
            "genre": genre,
            "duration_seconds": duration,
            "phase_results": self._phase_results,
            "screens_discovered": len(discovery_data.get("screens", {})),
            "parameters_extracted": extract_result.get("param_count", 0),
            "files_written": extract_result.get("files_written", []),
            "errors": self._errors,
        }

        logger.info("=" * 60)
        logger.info("AI Tester complete: %s (%.0fs)", self.package_name, duration)
        logger.info("Genre: %s | Screens: %d | Params: %d",
                     genre,
                     summary["screens_discovered"],
                     summary["parameters_extracted"])
        logger.info("=" * 60)

        return summary

    # ------------------------------------------------------------------
    # Existing game data loader
    # ------------------------------------------------------------------

    def _load_existing_game_data(self) -> bool:
        """Load pre-existing game data if available (profile, nav_graph, reference_db).

        Returns True if game data was found and loaded.
        """
        # Try game_id first, then check by package_name
        game_data_dir = GAME_DATA_ROOT / self.game_id
        if not game_data_dir.exists():
            # Try mapping common package patterns (e.g. studio.gameberry.anv -> ash_n_veil)
            for candidate in GAME_DATA_ROOT.iterdir() if GAME_DATA_ROOT.exists() else []:
                if candidate.is_dir():
                    profile_path = candidate / "profile.yaml"
                    if profile_path.exists():
                        try:
                            profile = GameProfile.load(profile_path)
                            if profile.package_name == self.package_name:
                                game_data_dir = candidate
                                break
                        except Exception:
                            continue

        if not game_data_dir.exists():
            print(f"[GameData] No existing data at {game_data_dir}")
            return False

        self._game_data_dir = game_data_dir
        print(f"[GameData] Found existing game data: {game_data_dir}")

        # Load profile.yaml
        profile_path = game_data_dir / "profile.yaml"
        if profile_path.exists():
            try:
                self._game_profile = GameProfile.load(profile_path)
                # Update input strategy from profile
                if self._game_profile.input_method:
                    self._input_strategy = InputStrategy(
                        self._adb, self.package_name, self._game_profile.input_method)
                print(f"[GameData] Profile loaded: genre={self._game_profile.genre}, "
                      f"game={self._game_profile.game_name}, "
                      f"input={self._game_profile.input_method}, "
                      f"gauges={len(self._game_profile.gauge_overrides)}, "
                      f"screen_rois={len(self._game_profile.screen_rois)}")
            except Exception as e:
                print(f"[GameData] Profile load failed: {e}")
                logger.warning("Profile load failed: %s", e)

        # Check nav_graph.json
        nav_path = game_data_dir / "nav_graph.json"
        if nav_path.exists():
            self._existing_nav_graph_path = nav_path
            print(f"[GameData] Nav graph found: {nav_path}")

        # Load reference DB
        ref_db_dir = game_data_dir / "reference_db"
        ref_index = ref_db_dir / "index.json"
        if ref_index.exists():
            try:
                from .brain.reference_db import ReferenceDB
                self._existing_ref_db = ReferenceDB.load(ref_db_dir)
                total = len(self._existing_ref_db.get_all_entries())
                types = self._existing_ref_db.get_screen_types()
                print(f"[GameData] Reference DB loaded: {total} entries, "
                      f"{len(types)} screen types: {types}")
            except Exception as e:
                print(f"[GameData] Reference DB load failed: {e}")
                logger.warning("Reference DB load failed: %s", e)

        # Load screen_types.json
        screen_types_path = game_data_dir / "screen_types.json"
        if screen_types_path.exists():
            try:
                import json
                self._existing_screen_types = json.loads(
                    screen_types_path.read_text(encoding="utf-8"))
                print(f"[GameData] Screen types loaded: {len(self._existing_screen_types)} types")
            except Exception as e:
                logger.debug("Screen types load failed: %s", e)
                self._existing_screen_types = {}
        else:
            self._existing_screen_types = {}

        return self._game_profile is not None

    # ------------------------------------------------------------------
    # Phase 1: Bootstrap
    # ------------------------------------------------------------------

    def _phase_bootstrap(self) -> Dict[str, Any]:
        """Launch game, explore screens, detect genre, apply transfer."""
        logger.info("--- Phase 1: Bootstrap ---")
        phase_start = time.time()
        result: Dict[str, Any] = {"status": "running"}

        try:
            # Load existing game data FIRST (profile, nav_graph, reference_db)
            has_game_data = self._load_existing_game_data()

            # Early OCR init (before exploration, so text detection works)
            self._ocr_reader = OCRReader()
            print(f"[Bootstrap] OCR reader initialized (engine: {self._ocr_reader.engine_name if hasattr(self._ocr_reader, 'engine_name') else 'default'})")

            # Launch
            launcher = LaunchManager(
                adb_path=self.adb_path,
                device=self.device,
                screenshot_fn=self._screenshot,
                tap_fn=self._tap,
            )

            launched = launcher.launch(self.package_name)
            if not launched:
                result["status"] = "failed"
                result["error"] = "Launch failed"
                self._errors.append("Game launch failed")
                return result
            print(f"[Bootstrap] Game launched: {self.package_name}")

            # Dismiss popups
            launcher.dismiss_initial_popups()
            screen_w, screen_h = launcher.get_device_resolution()
            print(f"[Bootstrap] Resolution: {screen_w}x{screen_h}")

            # Explore
            discovery_path = self._temp_dir / "discovery_db.json"
            db = DiscoveryDB(db_path=discovery_path,
                             screen_width=screen_w, screen_height=screen_h)
            safety = SafetyGuard()

            explorer = ExplorationEngine(
                db=db, safety=safety,
                screenshot_fn=self._screenshot,
                tap_fn=self._tap,
                detect_screen_fn=self._detect_screen,
                read_screen_text_fn=self._read_screen_text,
                close_overlay_fn=self._close_overlay,
                screen_width=screen_w,
                screen_height=screen_h,
            )

            # Initial exploration
            for screen_type in ["lobby", "unknown"]:
                explore_result = explorer.explore_current_screen(
                    screen_type, max_taps=self.explore_taps // 2)
                print(f"[Bootstrap] Explored '{screen_type}': {explore_result.get('elements_found', 0)} elements")
                if explore_result["elements_found"] > 0:
                    break

            db.save()

            # Fingerprint screens
            fingerprinter = ScreenFingerprinter()
            screenshots = sorted(self._temp_dir.glob("*.png"))
            screen_types = {}
            for ss in screenshots[:20]:
                label = fingerprinter.add_screenshot(ss)
                screen_types[label] = f"Auto-discovered"

            # Collect OCR texts from exploration screenshots for genre detection
            ocr_texts = []
            for ss in screenshots[:10]:
                try:
                    texts = self._read_screen_text(ss)
                    ocr_texts.extend([t[0] for t in texts])
                except Exception:
                    pass
            print(f"[Bootstrap] OCR collected: {len(ocr_texts)} text fragments from {min(len(screenshots), 10)} screenshots")
            if ocr_texts:
                sample = ocr_texts[:5]
                print(f"[Bootstrap] OCR sample: {sample}")

            # Detect genre (use profile if available, otherwise detect)
            if self._game_profile and self._game_profile.genre:
                genre = self._game_profile.genre
                genre_scores = {genre: 1.0}
                print(f"[Bootstrap] Genre from profile: {genre} (skipping detection)")
            else:
                detector = GenreDetector()
                genre, genre_scores = detector.detect(
                    db.to_dict(), ocr_texts, screen_types)
                print(f"[Bootstrap] Genre detected: {genre} (scores: {genre_scores})")

            # Merge existing screen types from game data
            if hasattr(self, '_existing_screen_types') and self._existing_screen_types:
                for st, desc in self._existing_screen_types.items():
                    if st not in screen_types:
                        screen_types[st] = desc
                print(f"[Bootstrap] Screen types after merge: {len(screen_types)} total")

            # Knowledge transfer
            kb = KnowledgeBase(db_path=KNOWLEDGE_DB)
            transfer = TransferEngine(kb)
            transfer_data = transfer.get_transfer_data(self.package_name, genre)
            if transfer_data:
                discovery_data = transfer.apply_transfer(transfer_data, db.to_dict())
                logger.info("Applied knowledge transfer from %d games",
                            len(transfer_data.get("source_games", [])))
            else:
                discovery_data = db.to_dict()

            # Build profile (with optional AutoProfileBuilder for Vision-enhanced artifacts)
            game_data_dir = GAME_DATA_ROOT / self.game_id
            auto_builder = AutoProfileBuilder(
                game_id=self.game_id,
                genre=genre,
                data_dir=str(game_data_dir),
                vision_fn=None,  # Wire a vision_fn here to enable LLM screen labeling
            )
            builder = ProfileBuilder(
                self.game_id, self.package_name, genre,
                output_dir=self._temp_dir / "profile",
            )
            builder.build_from_discovery(
                discovery_data, screen_types, screen_w, screen_h,
                auto_builder=auto_builder,
                screenshots=screenshots,
            )
            print(f"[Bootstrap] AutoProfileBuilder: nav_graph + reference_db saved to {game_data_dir}")

            # Initialize perception stack now that genre is known
            self._init_perception(genre, screen_w, screen_h)

            result.update({
                "status": "success",
                "genre": genre,
                "genre_scores": genre_scores,
                "discovery_data": discovery_data,
                "screen_types": screen_types,
                "screen_width": screen_w,
                "screen_height": screen_h,
                "duration": time.time() - phase_start,
            })

        except Exception as e:
            logger.exception("Bootstrap failed")
            result["status"] = "error"
            result["error"] = str(e)
            result["genre"] = "unknown"
            result["discovery_data"] = {}
            self._errors.append(f"Bootstrap: {e}")

        return result

    # ------------------------------------------------------------------
    # Phase 2: Play
    # ------------------------------------------------------------------

    def _phase_play(
        self, genre: str, discovery_data: Dict,
    ) -> Dict[str, Any]:
        """Play the game actively and collect observations."""
        logger.info("--- Phase 2: Play ---")
        phase_start = time.time()
        result: Dict[str, Any] = {"status": "running"}

        observations: Dict[str, List] = {}

        try:
            # Create all observers (generic + genre-specific)
            observers = self._create_observers(genre, observations)

            # Build optional reasoner
            reasoner = self._create_reasoner(genre)

            # Build optional navigator
            navigator = self._create_navigator(genre, discovery_data)

            # Build ScreenActionResolver + ActivityScheduler from nav graph
            screen_action_resolver = None
            activity_scheduler = None
            nav_graph = getattr(navigator, "graph", None) if navigator else None

            if nav_graph and len(nav_graph.nodes) > 0:
                try:
                    from .screen_action_resolver import ScreenActionResolver, ActivityScheduler
                    screen_action_resolver = ScreenActionResolver(
                        nav_graph=nav_graph,
                        tap_fn=self._tap,
                    )
                    activity_scheduler = ActivityScheduler(nav_graph=nav_graph)
                    print(f"[Play] ScreenActionResolver + ActivityScheduler created "
                          f"({len(nav_graph.nodes)} nodes)")
                except Exception as e:
                    print(f"[Play] WARNING: Could not create resolver/scheduler: {e}")
                    logger.warning("Could not create resolver/scheduler: %s", e)

            # Enrich GOAP actions with tap coordinates from nav graph
            if reasoner and nav_graph:
                try:
                    from .reasoning.goal_library import enrich_actions_from_nav_graph
                    actions = getattr(reasoner, "_planner", None)
                    action_list = getattr(actions, "_actions", []) if actions else []
                    enriched = enrich_actions_from_nav_graph(action_list, nav_graph)
                    if enriched:
                        print(f"[Play] Enriched {enriched} GOAP actions with nav graph coordinates")
                except Exception as e:
                    logger.debug("Could not enrich actions: %s", e)

            # Build HierarchicalPatternExecutor from learned patterns (if any)
            pattern_executor = None
            try:
                from .learning import PatternDB, HierarchicalPatternExecutor
                pattern_db_path = (self._game_data_dir / "pattern_db.json"
                                  if self._game_data_dir else None)
                if pattern_db_path and pattern_db_path.exists():
                    pattern_db = PatternDB(pattern_db_path)
                    if pattern_db.count > 0:
                        pattern_executor = HierarchicalPatternExecutor(
                            pattern_db=pattern_db,
                            tap_fn=self._tap,
                            read_text_fn=self._read_screen_text_from_path,
                            detect_screen_fn=self._detect_screen,
                            nav_graph=nav_graph,
                            back_fn=self._press_back,
                            navigate_to_fn=(navigator.navigate_to if navigator else None),
                            screenshot_fn=self._screenshot,
                            screen_width=self._phase_results.get("bootstrap", {}).get("screen_width", 1080),
                            screen_height=self._phase_results.get("bootstrap", {}).get("screen_height", 1920),
                        )
                        print(f"[Play] HierarchicalPatternExecutor loaded ({pattern_db.count} patterns)")
            except Exception as e:
                logger.debug("Could not create pattern executor: %s", e)

            # Resolve game-specific fallback positions from profile
            game_fallback = None
            if self._game_profile and self._game_profile.fallback_positions:
                game_fallback = [tuple(p) for p in self._game_profile.fallback_positions]

            # Build ExplorationEngine for unknown-screen adaptation (L4)
            play_exploration_engine = None
            play_fingerprinter = None
            try:
                screen_w = self._phase_results.get("bootstrap", {}).get("screen_width", 1080)
                screen_h = self._phase_results.get("bootstrap", {}).get("screen_height", 1920)
                discovery_path = self._temp_dir / "discovery_db.json"
                play_db = DiscoveryDB(
                    db_path=discovery_path, screen_width=screen_w, screen_height=screen_h)
                play_safety = SafetyGuard()
                play_exploration_engine = ExplorationEngine(
                    db=play_db,
                    safety=play_safety,
                    screenshot_fn=self._screenshot,
                    tap_fn=self._tap,
                    detect_screen_fn=self._detect_screen,
                    read_screen_text_fn=self._read_screen_text,
                    close_overlay_fn=self._close_overlay,
                    screen_width=screen_w,
                    screen_height=screen_h,
                )
                play_fingerprinter = ScreenFingerprinter()
                print("[Play] ExplorationEngine created for unknown-screen adaptation")
            except Exception as e:
                logger.warning("Could not create play exploration engine: %s", e)

            # Run active play engine
            engine = PlayEngine(
                genre=genre,
                screenshot_fn=self._screenshot,
                tap_fn=self._tap,
                detect_screen_fn=self._detect_screen,
                read_text_fn=self._read_screen_text_from_path,
                state_reader=self._state_reader,
                navigator=navigator,
                reasoner=reasoner,
                play_duration=self.play_duration,
                observers=observers,
                screen_width=self._phase_results.get("bootstrap", {}).get("screen_width", 1080),
                screen_height=self._phase_results.get("bootstrap", {}).get("screen_height", 1920),
                temp_dir=self._temp_dir,
                screen_action_resolver=screen_action_resolver,
                activity_scheduler=activity_scheduler,
                pattern_executor=pattern_executor,
                relaunch_fn=self._relaunch_game,
                back_fn=self._press_back,
                game_fallback_positions=game_fallback,
                gauge_bars=self._game_profile.gauge_bars if self._game_profile else None,
                input_method=self._game_profile.input_method if self._game_profile else "input_tap",
                exploration_engine=play_exploration_engine,
                fingerprinter=play_fingerprinter,
            )

            engine_result = engine.run()

            result.update({
                "status": "success",
                "observations": observations,
                "observer_count": len(observers),
                "tick_count": engine_result.get("tick_count", 0),
                "screens_visited": engine_result.get("screens_visited", {}),
                "actions_executed": engine_result.get("actions_executed", []),
                "duration": time.time() - phase_start,
            })

        except Exception as e:
            logger.exception("Play phase failed")
            result["status"] = "error"
            result["error"] = str(e)
            result["observations"] = observations
            self._errors.append(f"Play: {e}")

        return result

    def _create_reasoner(self, genre: str) -> Optional[Any]:
        """Create a GOAP reasoner for the genre, or None if unavailable."""
        try:
            from .reasoning.goal_reasoner import build_reasoner_for_genre
            reasoner_genre = genre
            if self._game_profile and self._game_profile.reasoner_genre:
                reasoner_genre = self._game_profile.reasoner_genre
                print(f"[Reasoner] Genre override: {genre} -> {reasoner_genre}")
            return build_reasoner_for_genre(reasoner_genre)
        except Exception as e:
            logger.debug("Could not create reasoner for genre '%s': %s", genre, e)
            return None

    def _create_navigator(self, genre: str, discovery_data: Dict) -> Optional[Any]:
        """Create a screen navigator if classifier and nav graph are available."""
        if self._classifier is None:
            return None
        try:
            from .navigation.screen_navigator import ScreenNavigator
            from .navigation.nav_graph import NavigationGraph
            from .navigation.popup_handler import PopupHandler

            # Load existing nav graph if available
            if self._existing_nav_graph_path and self._existing_nav_graph_path.exists():
                graph = NavigationGraph.load(self._existing_nav_graph_path)
                print(f"[Navigator] Loaded existing nav graph: "
                      f"{len(graph.nodes)} nodes, {len(graph.edges)} edges")
            else:
                graph = NavigationGraph()
                print(f"[Navigator] Created empty nav graph (no existing data)")

            popup_cache_dir = self._temp_dir / "popup_cache"
            popup_handler = PopupHandler(
                game_package=self.package_name,
                cache_dir=popup_cache_dir,
                reference_db=self._existing_ref_db,
            )
            return ScreenNavigator(
                graph=graph,
                classifier=self._classifier,
                popup_handler=popup_handler,
                temp_dir=self._temp_dir / "nav",
            )
        except Exception as e:
            print(f"[Navigator] ERROR: Could not create navigator: {e}")
            logger.warning("Could not create navigator: %s", e)
            return None

    # ------------------------------------------------------------------
    # Phase 3: Extract
    # ------------------------------------------------------------------

    def _phase_extract(
        self, genre: str, play_result: Dict,
    ) -> Dict[str, Any]:
        """Aggregate observations and export to Design DB."""
        logger.info("--- Phase 3: Extract ---")
        phase_start = time.time()
        result: Dict[str, Any] = {"status": "running"}

        try:
            observations = play_result.get("observations", {})

            # Aggregate
            aggregator = ParameterAggregator()
            aggregated = aggregator.aggregate(observations)

            observed_count = sum(
                1 for v in aggregated.values()
                if v.get("status") == "observed"
            )

            # Build domain groups dynamically from observed params
            domain_groups = self._build_domain_groups(genre, aggregated)

            # Export
            exporter = DesignDBExporter(
                project=self.game_id.replace("_", " ").title(),
                genre=genre.capitalize(),
                package_name=self.package_name,
                domain_groups=domain_groups,
                db_root=DESIGN_DB_ROOT,
            )

            files_written = exporter.export(aggregated, dry_run=self.dry_run)

            result.update({
                "status": "success",
                "param_count": observed_count,
                "total_params": len(aggregated),
                "files_written": [str(p) for p in files_written],
                "summary": aggregator.summary(aggregated),
                "duration": time.time() - phase_start,
            })

        except Exception as e:
            logger.exception("Extract phase failed")
            result["status"] = "error"
            result["error"] = str(e)
            result["param_count"] = 0
            self._errors.append(f"Extract: {e}")

        return result

    # ------------------------------------------------------------------
    # Phase 4: Journal
    # ------------------------------------------------------------------

    def _phase_journal(
        self, genre: str, total_duration: float,
    ) -> Dict[str, Any]:
        """Write session journal and extract patterns."""
        logger.info("--- Phase 4: Journal ---")
        result: Dict[str, Any] = {"status": "running"}

        try:
            journal = SessionJournal(journal_dir=JOURNAL_DIR)

            session_data = {
                "phase_results": self._phase_results,
                "duration_seconds": total_duration,
                "screens_discovered": len(
                    self._phase_results.get("bootstrap", {})
                        .get("discovery_data", {}).get("screens", {})
                ),
                "parameters_extracted": (
                    self._phase_results.get("extract", {}).get("param_count", 0)
                ),
                "errors": self._errors,
            }

            paths = journal.write(
                self.package_name, genre, session_data,
                tags=[genre, "ai_tester", self.game_id],
            )

            # Extract patterns
            extractor = PatternExtractor()
            bootstrap_data = self._phase_results.get("bootstrap", {})
            discovery = bootstrap_data.get("discovery_data", {})
            pattern_counts = extractor.analyze_session({
                "discovery_data": discovery,
                "phase_results": self._phase_results,
            })

            result.update({
                "status": "success",
                "journal_paths": {k: str(v) for k, v in paths.items()},
                "patterns": pattern_counts,
            })

        except Exception as e:
            logger.exception("Journal phase failed")
            result["status"] = "error"
            result["error"] = str(e)
            self._errors.append(f"Journal: {e}")

        return result

    # ------------------------------------------------------------------
    # Knowledge update
    # ------------------------------------------------------------------

    def _update_knowledge(
        self, genre: str,
        bootstrap_result: Dict,
        extract_result: Dict,
    ) -> None:
        """Update the knowledge base with session results."""
        try:
            kb = KnowledgeBase(db_path=KNOWLEDGE_DB)
            kb.register_game(self.package_name, genre, self.game_id)
            kb.record_session(self.package_name, {
                "screen_types": bootstrap_result.get("screen_types", {}),
                "nav_patterns": [],
                "parameters": {},
                "learned_actions": [],
            })
            kb.save()
        except Exception as e:
            logger.warning("Knowledge update failed: %s", e)

    # ------------------------------------------------------------------
    # Perception init (lazy, after genre detection)
    # ------------------------------------------------------------------

    def _init_perception(self, genre: str, screen_w: int, screen_h: int) -> None:
        """Initialize perception stack after genre is known."""
        try:
            schema = get_schema_for_genre(genre)
            screen_types = schema.get_screen_types() if schema else {}

            # Merge existing screen types from game data
            if hasattr(self, '_existing_screen_types') and self._existing_screen_types:
                for st, desc in self._existing_screen_types.items():
                    if st not in screen_types:
                        screen_types[st] = desc

            # ScreenClassifier (with reference DB if available)
            cache_dir = self._temp_dir / "classifier_cache"
            self._classifier = ScreenClassifier(
                genre_screen_types=screen_types,
                cache_dir=cache_dir,
                reference_db=self._existing_ref_db,
            )
            if self._existing_ref_db:
                print(f"[Perception] Classifier initialized with reference DB "
                      f"({len(self._existing_ref_db.get_all_entries())} refs)")

            # OCR Reader (multi-engine fallback)
            self._ocr_reader = OCRReader()

            # StateReader (gauge + OCR + region registry)
            gauge_reader = GaugeReader()
            registry = RegionRegistry()

            # Register genre-specific ROIs from schema
            if schema:
                for screen_type, roi in schema.get_default_screen_rois().items():
                    registry.register(screen_type, roi)
                # Register gauge profiles
                for profile in schema.get_gauge_profiles():
                    gauge_reader.add_profile(profile)

            # Apply game-specific overrides from profile.yaml
            if self._game_profile:
                # Register gauge overrides (e.g. XP bar HSV for Ash & Veil)
                for gauge_name, override in self._game_profile.gauge_overrides.items():
                    try:
                        from .perception.gauge_reader import GaugeProfile
                        profile = GaugeProfile(
                            name=gauge_name,
                            hsv_lower=tuple(override.get("hsv_lower", [0, 0, 0])),
                            hsv_upper=tuple(override.get("hsv_upper", [180, 255, 255])),
                            color_rgb=tuple(override.get("color_rgb", [255, 255, 255])),
                        )
                        gauge_reader.add_profile(profile)
                        print(f"[Perception] Gauge override applied: {gauge_name}")
                    except Exception as e:
                        logger.debug("Gauge override '%s' failed: %s", gauge_name, e)

                # Register game-specific screen ROIs
                for screen_type, rois in self._game_profile.screen_rois.items():
                    try:
                        registry.register(screen_type, rois)
                        print(f"[Perception] Screen ROI applied: {screen_type} "
                              f"({len(rois)} regions)")
                    except Exception as e:
                        logger.debug("Screen ROI '%s' failed: %s", screen_type, e)

            self._state_reader = StateReader(
                gauge_reader=gauge_reader,
                ocr_reader=self._ocr_reader,
                registry=registry,
            )

            print(f"[Perception] Initialized: genre='{genre}', "
                  f"{len(screen_types)} screen types, "
                  f"gauges={len(gauge_reader._profiles) if hasattr(gauge_reader, '_profiles') else '?'}")
            logger.info("Perception initialized for genre='%s' (%d screen types)",
                        genre, len(screen_types))
        except Exception as e:
            logger.warning("Perception init failed: %s (falling back to stubs)", e)

    # ------------------------------------------------------------------
    # Genre-specific observer factory
    # ------------------------------------------------------------------

    def _create_observers(
        self,
        genre: str,
        observations: Dict[str, List],
    ) -> List[Any]:
        """Create generic + genre-specific observers."""
        ocr_fn = self._read_screen_text_from_path

        # Generic observers (always)
        observers = [
            UIObserver(self._screenshot, observations, ocr_fn=ocr_fn),
            EconomyObserver(self._screenshot, observations, ocr_fn=ocr_fn),
            MonetizationObserver(self._screenshot, observations, ocr_fn=ocr_fn),
            ProgressionObserver(self._screenshot, observations, ocr_fn=ocr_fn),
        ]

        # Genre-specific observers
        genre_observers = self._get_genre_observers(genre, observations, ocr_fn)
        observers.extend(genre_observers)

        return observers

    def _get_genre_observers(
        self,
        genre: str,
        observations: Dict[str, List],
        ocr_fn: Callable,
    ) -> List[Any]:
        """Return genre-specific observers."""
        genre_lower = genre.lower()

        if genre_lower == "rpg":
            from .observers.rpg_observers import CombatObserver, TownObserver, QuestObserver
            return [
                CombatObserver(self._screenshot, observations, ocr_fn=ocr_fn),
                TownObserver(self._screenshot, observations, ocr_fn=ocr_fn),
                QuestObserver(self._screenshot, observations, ocr_fn=ocr_fn),
            ]
        elif genre_lower == "puzzle":
            from .observers.puzzle_observers import BoardObserver, MatchObserver
            return [
                BoardObserver(self._screenshot, observations),
                MatchObserver(self._screenshot, observations),
            ]
        elif genre_lower == "idle":
            try:
                from .observers.idle_observers import (
                    IdleProgressObserver, IdleUpgradeObserver, IdleAutomationObserver,
                )
                return [
                    IdleProgressObserver(self._screenshot, observations, ocr_fn=ocr_fn),
                    IdleUpgradeObserver(self._screenshot, observations, ocr_fn=ocr_fn),
                    IdleAutomationObserver(self._screenshot, observations, ocr_fn=ocr_fn),
                ]
            except ImportError:
                return []
        elif genre_lower == "merge":
            try:
                from .observers.merge_observers import (
                    MergeBoardObserver, MergeOrderObserver, MergeEnergyObserver,
                )
                return [
                    MergeBoardObserver(self._screenshot, observations),
                    MergeOrderObserver(self._screenshot, observations, ocr_fn=ocr_fn),
                    MergeEnergyObserver(self._screenshot, observations, ocr_fn=ocr_fn),
                ]
            except ImportError:
                return []
        elif genre_lower == "slg":
            try:
                from .observers.slg_observers import (
                    SLGResourceObserver, SLGMilitaryObserver, SLGTerritoryObserver,
                )
                return [
                    SLGResourceObserver(self._screenshot, observations, ocr_fn=ocr_fn),
                    SLGMilitaryObserver(self._screenshot, observations, ocr_fn=ocr_fn),
                    SLGTerritoryObserver(self._screenshot, observations, ocr_fn=ocr_fn),
                ]
            except ImportError:
                return []

        return []

    # ------------------------------------------------------------------
    # Domain group builder
    # ------------------------------------------------------------------

    def _build_domain_groups(
        self, genre: str, aggregated: Dict,
    ) -> List[DomainGroup]:
        """Dynamically build domain groups from observed parameters."""
        # Group params by a simple domain heuristic
        domain_map: Dict[str, List[str]] = {}
        for pid, data in aggregated.items():
            if data.get("status") != "observed":
                continue
            name = data.get("name", pid)
            # Simple domain classification by param name
            if any(k in name for k in ["board", "match", "holder", "combat", "skill"]):
                domain_map.setdefault("ingame", []).append(pid)
            elif any(k in name for k in ["level", "quest", "stage", "progression"]):
                domain_map.setdefault("content", []).append(pid)
            elif any(k in name for k in ["difficulty", "lives", "score", "win", "fail"]):
                domain_map.setdefault("balance", []).append(pid)
            elif any(k in name for k in ["ad", "iap", "currency", "monetization", "shop"]):
                domain_map.setdefault("bm", []).append(pid)
            elif any(k in name for k in ["screen", "nav", "ui", "resolution"]):
                domain_map.setdefault("ux", []).append(pid)
            else:
                domain_map.setdefault("ingame", []).append(pid)

        groups = []
        for domain, params in domain_map.items():
            groups.append(DomainGroup(
                domain=domain,
                design_id=f"{self.game_id}__{domain}__auto",
                system=f"Auto-detected {domain.upper()} parameters",
                balance_area=domain,
                params=params,
                provides=[f"{domain}_params"],
                tags=[genre, domain, "auto_detected"],
            ))

        return groups

    # ------------------------------------------------------------------
    # ADB helpers
    # ------------------------------------------------------------------

    def _adb(self, args: list, timeout: int = 10, retries: int = 2, binary: bool = False):
        """Run ADB command with retry logic and reconnect on failure.

        Args:
            binary: If True, capture stdout as raw bytes (for screencap).
        """
        cmd = [self.adb_path, "-s", self.device] + args
        for attempt in range(retries + 1):
            try:
                if binary:
                    result = subprocess.run(
                        cmd, capture_output=True, timeout=timeout)
                else:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True,
                        encoding="utf-8", errors="replace", timeout=timeout)
                if result.returncode == 0:
                    return result
                # Non-zero return -- retry if attempts remain
                if attempt < retries:
                    logger.debug("ADB returned %d, retrying (%d/%d)",
                                 result.returncode, attempt + 1, retries)
                    self._adb_reconnect()
                    time.sleep(0.5)
                else:
                    return result
            except subprocess.TimeoutExpired:
                if attempt < retries:
                    logger.debug("ADB timeout, retrying (%d/%d)", attempt + 1, retries)
                    time.sleep(0.5)
                else:
                    return None
            except OSError as e:
                logger.warning("ADB OS error: %s", e)
                if attempt < retries:
                    self._adb_reconnect()
                    time.sleep(1.0)
                else:
                    return None
        return None

    def _adb_reconnect(self) -> None:
        """Attempt to reconnect ADB."""
        try:
            subprocess.run(
                [self.adb_path, "reconnect"],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            pass

    def _screenshot(self, label: str = "") -> Optional[Path]:
        """Take a screenshot via ADB."""
        self._screenshot_count += 1
        path = self._temp_dir / f"{self._screenshot_count:04d}_{label}.png"
        result = self._adb(
            ["exec-out", "screencap", "-p"],
            timeout=10,
            binary=True,
        )
        if result and result.returncode == 0 and result.stdout:
            path.write_bytes(result.stdout)
            return path
        return None

    def _tap(self, x: int, y: int, wait: float = 1.0) -> None:
        """Tap at coordinates via InputStrategy (input_tap, monkey, or auto)."""
        self._input_strategy.tap(x, y, wait)

    def _press_back(self) -> None:
        """Press Android back key via ADB."""
        self._adb(["shell", "input", "keyevent", "KEYCODE_BACK"])
        time.sleep(1.5)

    # (fallback positions moved to per-game profile.yaml)

    def _relaunch_game(self) -> bool:
        """Force-stop and relaunch the game. Returns True if successful."""
        print(f"[Orchestrator] Relaunching {self.package_name}...")
        self._adb(["shell", "am", "force-stop", self.package_name])
        time.sleep(3)
        activity = (
            self._game_profile.launch_activity
            if self._game_profile and self._game_profile.launch_activity
            else "com.unity3d.player.UnityPlayerActivity"
        )
        result = self._adb([
            "shell", "am", "start", "-n",
            f"{self.package_name}/{activity}",
        ])
        if result and result.returncode == 0:
            print(f"[Orchestrator] Game relaunched, waiting 20s for load...")
            time.sleep(20)
            return True
        return False

    def _detect_screen(self, path: Path) -> str:
        """Classify screen using hash cache + SSIM reference DB + OCR keyword fallback.

        Priority:
        1. Hash cache lookup (fast, <50ms)
        2. SSIM reference DB matching (if loaded, ~200ms)
        3. OCR keyword classification (~2s)
        """
        from .navigation.classifier import compute_phash, ScreenClassification

        # Tier 1: Hash cache lookup (fast, <50ms)
        if self._classifier is not None:
            try:
                img_hash = compute_phash(path)
                if img_hash is not None:
                    cached = self._classifier._find_in_cache(img_hash)
                    if cached:
                        return cached.screen_type
            except Exception as e:
                logger.debug("Hash lookup error: %s", e)

        # Tier 2: SSIM reference DB matching (direct LocalVision, no Claude API)
        if self._existing_ref_db is not None:
            try:
                from .brain.local_vision import LocalVision
                lv = LocalVision(self._existing_ref_db)
                screen_type_ssim, confidence = lv.classify_screen(path)
                if screen_type_ssim != "unknown" and confidence >= 0.4:
                    # Cache in hash cache for fast future lookups
                    if self._classifier is not None:
                        try:
                            img_hash = compute_phash(path)
                            if img_hash is not None:
                                self._classifier._hash_cache[img_hash] = ScreenClassification(
                                    screen_type=screen_type_ssim,
                                    confidence=confidence,
                                    sub_info={"method": "local_ssim"},
                                    screenshot_path=path,
                                )
                        except Exception:
                            pass
                    return screen_type_ssim
            except Exception as e:
                logger.debug("LocalVision error: %s", e)

        # Tier 2.5: Pixel heuristic (fast, ~10ms, proven from smart_player.py)
        pixel_result = self._pixel_heuristic_classify(path)
        if pixel_result:
            # Cache the result for future hash lookups
            if self._classifier is not None:
                try:
                    img_hash = compute_phash(path)
                    if img_hash is not None:
                        self._classifier._hash_cache[img_hash] = ScreenClassification(
                            screen_type=pixel_result,
                            confidence=0.65,
                            sub_info={"method": "pixel_heuristic"},
                            screenshot_path=path,
                        )
                except Exception:
                    pass
            return pixel_result

        # Tier 3: OCR keyword classification (fallback, ~2s with cached OCR)
        screen_type = self._ocr_classify_screen(path)

        # Cache the result for future hash lookups
        if screen_type != "unknown" and self._classifier is not None:
            try:
                img_hash = compute_phash(path)
                if img_hash is not None:
                    self._classifier._hash_cache[img_hash] = ScreenClassification(
                        screen_type=screen_type,
                        confidence=0.7,
                        sub_info={"method": "ocr_keywords"},
                        screenshot_path=path,
                    )
            except Exception:
                pass

        return screen_type

    # Screen type keyword patterns for OCR-based classification
    _SCREEN_KEYWORDS = {
        "battle": [
            "attack", "hp", "damage", "skill", "auto battle", "combo",
            "공격", "스킬", "전투", "데미지", "체력", "자동전투",
        ],
        "town": [
            "shop", "market", "potion", "equip", "workshop",
            "상점", "마을", "포션", "장비", "공방",
        ],
        "lobby": [
            "play", "start", "tap to start", "touch to start",
            "시작", "플레이", "터치",
        ],
        "menu": ["settings", "option", "account", "설정", "옵션", "계정"],
        "inventory": [
            "inventory", "item", "bag", "인벤토리", "아이템", "가방",
        ],
        "shop": [
            "buy", "purchase", "price", "gem", "diamond", "package",
            "구매", "가격", "젬", "다이아", "패키지",
        ],
        "quest": [
            "quest", "mission", "reward", "complete", "accept",
            "퀘스트", "미션", "보상", "완료", "수락",
        ],
        "map": [
            "map", "stage", "chapter", "world", "travel", "move",
            "지도", "스테이지", "챕터", "이동하기",
        ],
        "gacha": [
            "summon", "gacha", "draw", "pull", "recruit",
            "소환", "뽑기", "모집",
        ],
        "result": [
            "victory", "defeat", "clear", "result", "exp gained",
            "승리", "패배", "클리어", "결과",
        ],
    }

    def _pixel_heuristic_classify(self, path: Path) -> Optional[str]:
        """Fast pixel-based screen classification using configurable rules.

        Reads y_top, y_bot, and rules from self._game_profile.pixel_heuristic.
        Each rule has a screen_type and a condition string evaluated against
        'std' (pixel std dev) and 'mean' (pixel mean) of the region.
        Returns None if no config or no rule matches.
        """
        if not self._game_profile or not self._game_profile.pixel_heuristic:
            return None
        config = self._game_profile.pixel_heuristic
        rules = config.get("rules")
        if not rules:
            return None
        try:
            import cv2
            import numpy as np
            img = cv2.imread(str(path))
            if img is None:
                return None
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            y_top = min(config.get("y_top", 1700), h - 80)
            y_bot = min(config.get("y_bot", 1780), h)
            region = gray[y_top:y_bot, :]
            std = float(np.std(region))
            mean = float(np.mean(region))

            for rule in rules:
                condition = rule.get("condition", "")
                screen_type = rule.get("screen_type")
                if not screen_type or not condition:
                    continue
                # Evaluate condition with std/mean in scope (safe: no builtins)
                try:
                    if eval(condition, {"__builtins__": {}}, {"std": std, "mean": mean}):
                        return screen_type
                except Exception:
                    continue
        except Exception as e:
            logger.debug("Pixel heuristic error: %s", e)
        return None

    def _ocr_classify_screen(self, path: Path) -> str:
        """Fast screen type detection via OCR keywords."""
        texts = self._read_screen_text(path)
        if not texts:
            return "unknown"

        text_combined = " ".join(t[0].lower() for t in texts if isinstance(t[0], str))

        best_match = "unknown"
        best_score = 0
        for screen_type, keywords in self._SCREEN_KEYWORDS.items():
            score = sum(1 for k in keywords if k.lower() in text_combined)
            if score > best_score:
                best_score = score
                best_match = screen_type

        if best_score >= 1:
            return best_match
        return "unknown"

    def _read_screen_text(self, path: Path) -> List[Tuple[str, float, int, int]]:
        """Read all text from screenshot using OCRReader (cached per path)."""
        cache_key = str(path)
        if cache_key in self._ocr_cache:
            return self._ocr_cache[cache_key]

        result: List[Tuple[str, float, int, int]] = []
        if self._ocr_reader is not None:
            try:
                import cv2
                image = cv2.imread(str(path))
                if image is not None:
                    result = self._ocr_reader.read_full_screen(image)
            except ImportError:
                logger.debug("cv2 not available for OCR")
            except Exception as e:
                logger.debug("OCR read error: %s", e)

        # Cache result (keep cache small)
        self._ocr_cache[cache_key] = result
        if len(self._ocr_cache) > 30:
            oldest = next(iter(self._ocr_cache))
            del self._ocr_cache[oldest]

        return result

    def run_play_only(self) -> Dict[str, Any]:
        """Run Phase 2 (Play) only, skipping full bootstrap when profile already exists.

        Loads existing profile/nav_graph if available, then runs PlayEngine for
        play_duration seconds. Returns a result dict compatible with OvernightRunner.

        Returns:
            {duration_s, action_counts, errors, unknown_screen_count,
             quests_completed, skills_used, puzzle_moves, puzzle_wins,
             level_start, level_end, gold_start, gold_end}
        """
        start_time = time.time()
        self._temp_dir.mkdir(parents=True, exist_ok=True)

        # Initialize OCR (needed by _phase_play)
        if self._ocr_reader is None:
            self._ocr_reader = OCRReader()

        # Load existing game data (profile, nav_graph, reference_db)
        has_data = self._load_existing_game_data()

        # Initialize perception using profile genre if available
        genre = "unknown"
        if self._game_profile:
            genre = self._game_profile.genre or "unknown"
            screen_w = 1080
            screen_h = 1920
            self._init_perception(genre, screen_w, screen_h)
            self._phase_results["bootstrap"] = {
                "screen_width": screen_w,
                "screen_height": screen_h,
                "genre": genre,
            }
        else:
            logger.warning("run_play_only: no profile found for %s, using defaults", self.game_id)
            self._phase_results["bootstrap"] = {
                "screen_width": 1080,
                "screen_height": 1920,
                "genre": genre,
            }

        # Build discovery data from existing nav graph if present
        discovery_data: Dict = {}
        if self._existing_nav_graph_path and self._existing_nav_graph_path.exists():
            try:
                import json as _json
                raw = _json.loads(self._existing_nav_graph_path.read_text(encoding="utf-8"))
                discovery_data = {"screens": {n: {} for n in raw.get("nodes", [])}}
            except Exception as e:
                logger.debug("run_play_only: nav graph load failed: %s", e)

        # Run play phase
        play_result = self._phase_play(genre, discovery_data)

        # Extract overnight-relevant stats from play result
        actions_executed: List[str] = play_result.get("actions_executed", [])
        screens_visited: Dict[str, int] = play_result.get("screens_visited", {})

        # Count action types
        action_counts: Dict[str, int] = {}
        for a in actions_executed:
            key = a.split(":")[0] if ":" in a else a
            action_counts[key] = action_counts.get(key, 0) + 1

        skills_used = sum(1 for a in actions_executed if a.startswith("combat:"))
        puzzle_moves = action_counts.get("puzzle_move", 0)
        puzzle_wins = action_counts.get("puzzle_win", 0)
        quests_completed = action_counts.get("quest_complete", 0)
        unknown_screens = screens_visited.get("unknown", 0)

        # Extract level/gold from observations if available
        observations = play_result.get("observations", {})
        level_readings = observations.get("level", [])
        gold_readings = observations.get("gold", [])

        def _first(lst):
            return lst[0] if lst else None

        def _last(lst):
            return lst[-1] if lst else None

        duration_s = time.time() - start_time

        return {
            "duration_s": duration_s,
            "action_counts": action_counts,
            "errors": self._errors,
            "unknown_screen_count": unknown_screens,
            "quests_completed": quests_completed,
            "skills_used": skills_used,
            "puzzle_moves": puzzle_moves,
            "puzzle_wins": puzzle_wins,
            "level_start": _first(level_readings),
            "level_end": _last(level_readings),
            "gold_start": _first(gold_readings),
            "gold_end": _last(gold_readings),
            "play_status": play_result.get("status"),
            "tick_count": play_result.get("tick_count", 0),
        }

    def _read_screen_text_from_path(self, path: Path) -> List[Tuple[str, float, int, int]]:
        """Wrapper for OCR from path."""
        return self._read_screen_text(path)

    def _close_overlay(self, max_attempts: int = 3) -> None:
        """Try to close popups."""
        for _ in range(max_attempts):
            self._tap(540, 1700, 1.5)
