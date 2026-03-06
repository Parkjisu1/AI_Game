"""
PlayEngine v2 -- BT + State Machine Architecture
==================================================
Replaces GOAP-driven decision cascade with:
  1. ScreenStateMachine for screen tracking + verified stuck detection
  2. Per-screen Behavior Trees with 3-layer fallback (BT -> Discovery -> Vision)
  3. OutcomeTracker for action result tracking + Vision->BT node promotion
  4. Persona-driven decision diversity via PersonaGate + EpsilonRandom

Key fixes over v1:
  - Stuck escape VERIFIES screen change before resetting counter
  - Multiple escalating escape strategies (not same edge every time)
  - FailureMemory + LoopDetector integrated into escape logic
  - Actions have outcome tracking -> BT evolves over time
"""

import logging
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .bt.nodes import BTContext, Status
from .bt.tree_builder import TreeBuilder
from .episode_recorder import EpisodeRecorder, ExperienceLearner
from .outcome_tracker import OutcomeTracker
from .state_machine import ScreenStateMachine

logger = logging.getLogger(__name__)


class PlayEngineV2:
    """BT + State Machine play engine."""

    MAX_SCREENSHOTS = 200
    ADB_SCREENSHOT_RETRIES = 3

    def __init__(
        self,
        genre: str,
        screenshot_fn: Callable[[str], Optional[Path]],
        tap_fn: Callable[[int, int, float], None],
        detect_screen_fn: Callable[[Path], str],
        read_text_fn: Callable[[Path], List[Tuple[str, float, int, int]]],
        play_duration: int = 300,
        screen_width: int = 1080,
        screen_height: int = 1920,
        # Optional components
        persona: Any = None,
        nav_graph: Any = None,
        state_reader: Any = None,
        back_fn: Optional[Callable[[], None]] = None,
        swipe_fn: Optional[Callable[[int, int, int, int, float], None]] = None,
        relaunch_fn: Optional[Callable[[], bool]] = None,
        vision_fn: Optional[Callable] = None,
        observers: Optional[List[Any]] = None,
        temp_dir: Optional[Path] = None,
        cache_dir: Optional[Path] = None,
        input_method: str = "input_tap",
        # Puzzle support
        combat_controller: Any = None,
        gauge_bars: Optional[Dict[str, Dict[str, Any]]] = None,
        # Ad handling
        game_package: str = "",
        launch_activity: str = "",
        adb_fn: Optional[Callable] = None,
    ):
        self.genre = genre
        self._screenshot = screenshot_fn
        self._tap = tap_fn
        self._detect_screen = detect_screen_fn
        self._read_text = read_text_fn
        self.play_duration = play_duration
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._persona = persona
        self._state_reader = state_reader
        self._back_fn = back_fn
        self._swipe_fn = swipe_fn
        self._relaunch_fn = relaunch_fn
        self._vision_fn = vision_fn
        self._observers = observers or []
        self._temp_dir = temp_dir
        self._input_method = input_method
        self._combat_controller = combat_controller
        self._gauge_bars = gauge_bars or {}
        self._game_package = game_package
        self._launch_activity = launch_activity
        self._adb_fn = adb_fn

        # Ad handling (lazy init)
        self._ad_detector: Any = None
        self._ad_handler: Any = None

        # Episode recording
        self._episode_recorder: Optional[EpisodeRecorder] = None
        self._experience_learner: Optional[ExperienceLearner] = None
        data_dir = (temp_dir or Path("temp")).parent
        # Try to find the actual data dir (virtual_player/data)
        for candidate in [Path("virtual_player/data"), Path("data"), data_dir / "data"]:
            if candidate.exists() and (candidate / "games").exists():
                data_dir = candidate
                break
        try:
            self._episode_recorder = EpisodeRecorder(
                game_id=game_package.split(".")[-1] if game_package else genre,
                data_dir=data_dir,
            )
            self._experience_learner = ExperienceLearner(
                game_id=game_package.split(".")[-1] if game_package else genre,
                data_dir=data_dir,
            )
        except Exception as e:
            logger.warning("Episode recorder init failed: %s", e)

        # Core components
        cache = cache_dir or (temp_dir or Path("temp")) / "bt_cache"
        self._sm = ScreenStateMachine()
        self._outcome = OutcomeTracker(
            cache_path=cache / "outcome_tracker.json",
            on_promote=self._on_node_promoted,
        )

        # Build behavior trees
        epsilon = 0.1
        if persona and hasattr(persona, 'skill'):
            epsilon = getattr(persona.skill, 'explore_rate', 0.1) * 0.5
        self._tree_builder = TreeBuilder(
            nav_graph=nav_graph,
            promoted_actions=self._outcome.get_promoted_actions(),
            epsilon=epsilon,
        )
        self._trees = self._tree_builder.build_all()

        # Runtime state
        self._tick_count = 0
        self._actions_executed: List[str] = []
        self._screenshot_paths: List[Path] = []
        self._observer_interval = 10
        self._last_screenshot_path: Optional[Path] = None

    def run(self) -> Dict[str, Any]:
        """Execute the play loop."""
        start_time = time.time()
        persona_name = self._persona.name if self._persona else "default"
        print(f"[PlayEngineV2] Starting {self.play_duration}s session "
              f"(genre={self.genre}, persona={persona_name})")

        # Start episode recording
        if self._episode_recorder:
            ep_id = self._episode_recorder.start_episode()
            print(f"[PlayEngineV2] Recording episode #{ep_id}")

        observer_errors: List[str] = []

        while time.time() - start_time < self.play_duration:
            self._tick_count += 1
            try:
                self._tick()
            except Exception as e:
                logger.warning("PlayEngineV2 tick %d error: %s", self._tick_count, e)

            # Observers
            if self._tick_count % self._observer_interval == 0:
                for obs in self._observers:
                    try:
                        obs.run()
                    except Exception as e:
                        observer_errors.append(f"{getattr(obs, 'name', '?')}: {e}")

            # Cleanup
            if self._tick_count % 50 == 0:
                self._cleanup_old_screenshots()

        duration = time.time() - start_time
        stats = self._outcome.get_stats()

        # End episode recording
        episode_outcome = self._detect_episode_outcome()
        if self._episode_recorder and self._episode_recorder.is_recording:
            ep_path = self._episode_recorder.end_episode(
                outcome=episode_outcome,
                fail_reason=self._sm.last_screen if episode_outcome == "fail" else None,
            )
            print(f"[PlayEngineV2] Episode saved: {ep_path}")

        # Update experience summary
        if self._experience_learner:
            summary = self._experience_learner.generate_summary()
            if summary:
                print(f"[PlayEngineV2] Experience: {summary[:120]}...")

        print(f"\n[PlayEngineV2] DONE - {self._tick_count} ticks, "
              f"{len(self._actions_executed)} actions in {duration:.0f}s")
        print(f"[PlayEngineV2] Outcome stats: {stats}")

        return {
            "tick_count": self._tick_count,
            "actions_executed": self._actions_executed,
            "duration": duration,
            "outcome_stats": stats,
            "episode_outcome": episode_outcome,
            "observer_errors": observer_errors,
        }

    def _tick(self) -> None:
        """Single play loop iteration."""

        # 1. Screenshot
        path = self._take_screenshot(f"v2_{self._tick_count:04d}")
        if path is None:
            time.sleep(1.0)
            return
        self._last_screenshot_path = path

        # 2. Detect screen
        screen_type = self._detect_screen(path)
        screen_changed = self._sm.update(screen_type)

        elapsed_info = f"tick={self._tick_count}, screen='{screen_type}'"
        if not screen_changed:
            elapsed_info += f", same={self._sm.same_screen_ticks}"
        print(f"[V2] {elapsed_info}")

        # 3. Record outcome of previous action (if any)
        self._outcome.record_result(screen_changed, screen_type)

        # 3a. Report failed vision tap to VisionPlanner
        if not screen_changed and self._vision_fn and hasattr(self._vision_fn, 'report_tap_failed'):
            from .bt.nodes import VisionQuery
            if VisionQuery.last_tap is not None:
                tap = VisionQuery.last_tap
                self._vision_fn.report_tap_failed(tap["x"], tap["y"], tap.get("description", ""))
                VisionQuery.last_tap = None

        # 3b. Record to episode
        if self._episode_recorder and self._episode_recorder.is_recording:
            last_action = self._actions_executed[-1] if self._actions_executed else ""
            self._episode_recorder.record_action(
                tick=self._tick_count,
                screen_type=screen_type,
                action_name=last_action,
                context={"screen_changed": screen_changed},
            )

        # 4. Ad detection
        if self._handle_ad(path, screen_type):
            return

        # 5. Stuck detection (with escalating strategies)
        strategy = self._sm.get_stuck_strategy()
        if strategy:
            self._handle_stuck(strategy, screen_type, path)
            return

        # 6. Oscillation detection
        osc = self._sm.get_oscillation()
        if osc:
            print(f"[V2] Oscillation detected: {osc[0]} <-> {osc[1]}, breaking out")
            self._try_break_oscillation(osc)
            return

        # 7. Read text for context
        texts = self._read_text(path)
        ocr_texts = [t[0] for t in texts if isinstance(t[0], str)]

        # 8. Build snapshot
        snapshot = self._build_snapshot(screen_type, texts, path)

        # 9. Combat controller (battle screen only)
        if screen_type == "battle" and self._combat_controller:
            try:
                action = self._combat_controller.tick(str(path), snapshot)
                if action:
                    print(f"[V2] Combat: {action}")
                    self._actions_executed.append(f"combat:{action}")
                    # Don't return -- let BT also run
            except Exception as e:
                logger.debug("V2: combat error: %s", e)

        # 10. Execute Behavior Tree for current screen
        tree = self._tree_builder.get_tree(screen_type)
        if tree is None:
            logger.warning("V2: no tree for '%s'", screen_type)
            return

        ctx = BTContext(
            screen_type=screen_type,
            screenshot_path=path,
            persona=self._persona,
            tap_fn=self._tap,
            swipe_fn=self._swipe_fn,
            back_fn=self._back_fn,
            snapshot=snapshot,
            ocr_texts=ocr_texts,
            vision_fn=self._vision_fn,
            outcome_tracker=self._outcome,
            tick_count=self._tick_count,
            screen_width=self._screen_width,
            screen_height=self._screen_height,
        )

        status = tree.root.tick(ctx)
        self._actions_executed.append(f"bt:{screen_type}:{status.value}")

        if status == Status.FAILURE:
            print(f"[V2] BT FAILURE for '{screen_type}' - no action taken")

    # ------------------------------------------------------------------
    # Stuck handling (escalating strategies)
    # ------------------------------------------------------------------

    def _handle_stuck(self, strategy: str, screen_type: str, path: Path) -> None:
        """Execute stuck escape strategy, then VERIFY it worked."""
        print(f"[V2] Stuck strategy: {strategy} on '{screen_type}'")

        if strategy == "bt_alternative":
            # Reset the tree and re-tick (forces different branch selection)
            tree = self._tree_builder.get_tree(screen_type)
            if tree:
                tree.root.reset()
            # Also try a random tap in a different area
            x = random.randint(100, self._screen_width - 100)
            y = random.randint(200, self._screen_height - 400)
            self._tap(x, y, 1.0)

        elif strategy == "back_key":
            if self._back_fn:
                self._back_fn()
            else:
                self._tap(60, 80, 1.0)  # top-left back arrow

        elif strategy == "navigate_hub":
            # Try to tap common hub navigation targets
            hub_taps = [
                (540, 1870),   # bottom nav center
                (100, 1870),   # bottom nav left
                (980, 1870),   # bottom nav right
            ]
            target = random.choice(hub_taps)
            self._tap(target[0], target[1], 2.0)

        elif strategy == "discovery":
            # Random area exploration
            for _ in range(3):
                x = random.randint(50, self._screen_width - 50)
                y = random.randint(100, self._screen_height - 200)
                self._tap(x, y, 0.5)

        elif strategy == "vision":
            if self._vision_fn:
                try:
                    result = self._vision_fn(path, screen_type, [])
                    if result:
                        x = result.get("x", self._screen_width // 2)
                        y = result.get("y", self._screen_height // 2)
                        self._tap(x, y, 1.5)
                except Exception as e:
                    logger.debug("V2: vision stuck escape error: %s", e)
            else:
                # Aggressive random + back
                if self._back_fn:
                    self._back_fn()
                x = random.randint(100, self._screen_width - 100)
                y = random.randint(300, self._screen_height - 300)
                self._tap(x, y, 1.0)

        elif strategy == "relaunch":
            if self._relaunch_fn:
                try:
                    self._relaunch_fn()
                except Exception as e:
                    logger.warning("V2: relaunch failed: %s", e)

        self._actions_executed.append(f"stuck:{strategy}")

        # VERIFY: Take new screenshot and check if screen changed
        time.sleep(1.0)
        verify_path = self._take_screenshot(f"verify_{self._tick_count:04d}")
        if verify_path:
            new_screen = self._detect_screen(verify_path)
            escaped = self._sm.verify_escape(new_screen)
            if escaped:
                print(f"[V2] Escape SUCCESS: '{screen_type}' -> '{new_screen}'")
            else:
                print(f"[V2] Escape FAILED: still on '{screen_type}' "
                      f"(will escalate next tick)")

    def _try_break_oscillation(self, screens: Tuple[str, str]) -> None:
        """Break out of A<->B oscillation by going somewhere new."""
        # Try back key first
        if self._back_fn:
            self._back_fn()
            self._actions_executed.append("osc:back")
            return
        # Try a completely different area
        x = random.randint(100, self._screen_width - 100)
        y = random.randint(self._screen_height // 3, self._screen_height * 2 // 3)
        self._tap(x, y, 1.5)
        self._actions_executed.append("osc:random")

    # ------------------------------------------------------------------
    # Ad handling
    # ------------------------------------------------------------------

    def _handle_ad(self, path: Path, screen_type: str) -> bool:
        """Detect and handle ads. Returns True if ad was handled."""
        if self._ad_detector is None:
            self._init_ad_handling()
        if self._ad_detector is None:
            return False
        try:
            texts = self._read_text(path)
            ocr_texts = [t[0] for t in texts if isinstance(t[0], str)]
            ad_state = self._ad_detector.detect(str(path), ocr_texts)
            if ad_state.is_ad and self._ad_handler:
                print(f"[V2] AD: {ad_state.ad_type}")
                result = self._ad_handler.handle_ad(ad_state)
                self._actions_executed.append(f"ad:{result}")
                return True
        except Exception as e:
            logger.debug("V2: ad detection error: %s", e)
        return False

    def _init_ad_handling(self) -> None:
        if not self._game_package or not self._adb_fn:
            return
        try:
            from .perception.ad_detector import AdDetector, AdHandler
            self._ad_detector = AdDetector(
                game_package=self._game_package,
                adb_fn=self._adb_fn,
                read_text_fn=self._read_text,
            )
            self._ad_handler = AdHandler(
                game_package=self._game_package,
                launch_activity=self._launch_activity,
                adb_fn=self._adb_fn,
                tap_fn=self._tap,
                screenshot_fn=self._screenshot,
                detector=self._ad_detector,
            )
        except Exception as e:
            logger.debug("V2: ad init failed: %s", e)

    # ------------------------------------------------------------------
    # Snapshot building
    # ------------------------------------------------------------------

    def _build_snapshot(self, screen_type: str, texts: List, path: Path) -> Dict[str, Any]:
        """Build game state snapshot for BT context."""
        snapshot: Dict[str, Any] = {"screen_type": screen_type}

        if self._state_reader:
            try:
                state = self._state_reader.read_state(path, screen_type)
                if hasattr(state, "to_world_dict"):
                    snapshot.update(state.to_world_dict())
                else:
                    if hasattr(state, "gauges"):
                        for name, val in state.gauges.items():
                            if hasattr(val, "ratio"):
                                snapshot[f"{name}_pct"] = val.ratio
                    if hasattr(state, "resources"):
                        for name, reading in state.resources.items():
                            if hasattr(reading, "parsed_value") and reading.parsed_value is not None:
                                snapshot[name] = reading.parsed_value
            except Exception as e:
                logger.debug("V2: state reader error: %s", e)

        # OCR resource extraction
        import re
        for text_str, conf, y, x in texts:
            if isinstance(text_str, str):
                for keyword in ["gold", "gem", "score", "coin", "diamond"]:
                    if keyword in text_str.lower():
                        m = re.search(r"[\d,]+\.?\d*", text_str)
                        if m:
                            try:
                                snapshot.setdefault(keyword, float(m.group().replace(",", "")))
                            except ValueError:
                                pass

        # Battle MP detection
        if screen_type == "battle":
            mp_pct = self._detect_mp_ratio(path)
            if mp_pct is not None:
                snapshot["mp_pct"] = mp_pct
                snapshot["needs_potion"] = mp_pct < 0.2

        return snapshot

    def _detect_mp_ratio(self, screenshot_path: Path) -> Optional[float]:
        bar_cfg = self._gauge_bars.get("mp")
        if not bar_cfg:
            return None
        try:
            import cv2
            import numpy as np
            img = cv2.imread(str(screenshot_path))
            if img is None:
                return None
            y = bar_cfg.get("y", 66)
            x_start = bar_cfg.get("x_start", 140)
            x_end = bar_cfg.get("x_end", 250)
            empty_color = bar_cfg.get("empty_color", {})
            r_min = empty_color.get("r_min", 180)
            b_max = empty_color.get("b_max", 80)
            bar_row = img[y, x_start:x_end, :]
            red_ch = bar_row[:, 2].astype(float)
            blue_ch = bar_row[:, 0].astype(float)
            empty = (red_ch > r_min) & (blue_ch < b_max)
            return 1.0 - float(np.sum(empty)) / max(1, len(empty))
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _take_screenshot(self, label: str) -> Optional[Path]:
        for attempt in range(self.ADB_SCREENSHOT_RETRIES):
            path = self._screenshot(label)
            if path and path.exists():
                self._screenshot_paths.append(path)
                return path
            if attempt < self.ADB_SCREENSHOT_RETRIES - 1:
                time.sleep(0.5)
        return None

    def _cleanup_old_screenshots(self) -> None:
        if self._temp_dir is None:
            return
        try:
            png_files = sorted(self._temp_dir.glob("*.png"))
            if len(png_files) > self.MAX_SCREENSHOTS:
                for f in png_files[:len(png_files) - self.MAX_SCREENSHOTS]:
                    try:
                        f.unlink()
                    except OSError:
                        pass
        except Exception:
            pass

    def _detect_episode_outcome(self) -> str:
        """Detect win/fail/timeout from the action history."""
        # Check last few screens visited
        recent_screens = []
        for action_str in reversed(self._actions_executed[-20:]):
            parts = action_str.split(":")
            if len(parts) >= 2:
                recent_screens.append(parts[1])

        # Win detection: visited 'win' screen
        if any("win" in s for s in recent_screens[:5]):
            return "win"

        # Fail detection: visited fail screens
        if any("fail" in s for s in recent_screens[:5]):
            return "fail"

        return "timeout"

    def _on_node_promoted(self, screen_type: str, action: Dict) -> None:
        """Callback when OutcomeTracker promotes a vision action to BT node."""
        self._tree_builder.add_promoted_node(screen_type, action)
        print(f"[V2] NODE PROMOTED: '{action.get('name')}' on '{screen_type}' "
              f"-> now a permanent BT node")

    # ------------------------------------------------------------------
    # Public API for ad/puzzle config (compatibility with v1)
    # ------------------------------------------------------------------

    def configure_ad_handling(self, game_package: str, launch_activity: str,
                             adb_fn, read_text_fn=None) -> None:
        self._game_package = game_package
        self._launch_activity = launch_activity
        self._adb_fn = adb_fn
        self._init_ad_handling()

    def configure_puzzle(self, board_config: dict, game_type: str = "carmatch") -> None:
        self._puzzle_board_config = board_config
        self._puzzle_game_type = game_type
