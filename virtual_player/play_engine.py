"""
PlayEngine -- Active Game Play Loop
====================================
GOAP-driven play loop that screenshots, detects screens, reads state,
plans actions, navigates, and executes. Replaces passive-only Phase 2.

Usage:
    engine = PlayEngine(genre="rpg", ...)
    result = engine.run()
"""

import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class PlayEngine:
    """Active game play engine using GOAP decision-making."""

    MAX_SCREENSHOTS = 200
    STUCK_THRESHOLD = 5  # same screen N times -> escape
    EXPLORE_GRID_COLS = 5
    EXPLORE_GRID_ROWS = 8
    ADB_SCREENSHOT_RETRIES = 3

    def __init__(
        self,
        genre: str,
        screenshot_fn: Callable[[str], Optional[Path]],
        tap_fn: Callable[[int, int, float], None],
        detect_screen_fn: Callable[[Path], str],
        read_text_fn: Callable[[Path], List[Tuple[str, float, int, int]]],
        state_reader: Optional[Any] = None,
        navigator: Optional[Any] = None,
        reasoner: Optional[Any] = None,
        play_duration: int = 300,
        observers: Optional[List[Any]] = None,
        screen_width: int = 1080,
        screen_height: int = 1920,
        temp_dir: Optional[Path] = None,
        screen_action_resolver: Optional[Any] = None,
        activity_scheduler: Optional[Any] = None,
        pattern_executor: Optional[Any] = None,
        relaunch_fn: Optional[Callable[[], bool]] = None,
        back_fn: Optional[Callable[[], None]] = None,
        game_fallback_positions: Optional[List[Tuple[int, int]]] = None,
        gauge_bars: Optional[Dict[str, Dict[str, Any]]] = None,
        input_method: str = "input_tap",
        exploration_engine: Optional[Any] = None,
        fingerprinter: Optional[Any] = None,
        value_estimator: Optional[Any] = None,
        combat_controller: Optional[Any] = None,
    ):
        """
        Args:
            genre: Game genre key ("rpg", "idle", etc.).
            screenshot_fn: (label) -> Path. Captures screenshot.
            tap_fn: (x, y, wait) -> None. ADB tap.
            detect_screen_fn: (path) -> screen_type string.
            read_text_fn: (path) -> [(text, conf, y, x), ...].
            state_reader: Optional StateReader for structured state extraction.
            navigator: Optional ScreenNavigator for screen transitions.
            reasoner: Optional GoalReasoner for GOAP decisions.
            play_duration: Total play time in seconds.
            observers: List of ObserverBase instances to run periodically.
            screen_width: Device screen width.
            screen_height: Device screen height.
            temp_dir: Directory for screenshot cleanup tracking.
            screen_action_resolver: Optional ScreenActionResolver for nav-graph-based actions.
            activity_scheduler: Optional ActivityScheduler for screen rotation.
            pattern_executor: Optional PatternExecutor for learned behavior replay.
            relaunch_fn: Optional callback to restart the game after crash. Returns True if successful.
            back_fn: Optional callback to press Android back key.
            game_fallback_positions: Game-specific tap positions for stuck escape.
            combat_controller: Optional CombatController for skill rotation during battle.
        """
        self.genre = genre
        self._screenshot = screenshot_fn
        self._tap = tap_fn
        self._detect_screen = detect_screen_fn
        self._read_text = read_text_fn
        self._state_reader = state_reader
        self._navigator = navigator
        self._reasoner = reasoner
        self.play_duration = play_duration
        self._observers = observers or []
        self._screen_width = screen_width
        self._screen_height = screen_height
        self._temp_dir = temp_dir
        self._resolver = screen_action_resolver
        self._scheduler = activity_scheduler
        self._pattern_executor = pattern_executor
        self._relaunch_fn = relaunch_fn
        self._back_fn = back_fn
        self._game_fallback_positions = game_fallback_positions
        self._gauge_bars = gauge_bars or {}
        self._input_method = input_method
        self._exploration_engine = exploration_engine
        self._fingerprinter = fingerprinter
        self._value_estimator = value_estimator
        self._combat_controller = combat_controller
        self._ad_handler: Optional[Any] = None
        self._ad_detector: Optional[Any] = None

        # Runtime state
        self._tick_count = 0
        self._screens_visited: Dict[str, int] = {}
        self._actions_executed: List[str] = []
        self._last_screen_type = "unknown"
        self._same_screen_count = 0
        self._stuck_escape_count = 0  # consecutive stuck escapes on same screen type
        self._last_stuck_screen = ""
        self._explore_index = 0
        self._observer_interval = 10  # Run observers every N ticks
        self._screenshot_paths: List[Path] = []

    def run(self) -> Dict[str, Any]:
        """
        Execute the active play loop for play_duration seconds.

        Returns:
            {tick_count, screens_visited, actions_executed, duration, observer_results}
        """
        start_time = time.time()
        print(f"[PlayEngine] Starting {self.play_duration}s play session (genre={self.genre})")
        logger.info("PlayEngine: starting %ds play session (genre=%s)", self.play_duration, self.genre)

        observer_errors: List[str] = []

        while time.time() - start_time < self.play_duration:
            self._tick_count += 1

            try:
                self._tick(start_time)
            except Exception as e:
                logger.warning("PlayEngine tick %d error: %s", self._tick_count, e)

            # Run observers periodically
            if self._tick_count % self._observer_interval == 0:
                for obs in self._observers:
                    try:
                        obs.run()
                    except Exception as e:
                        observer_errors.append(f"{getattr(obs, 'name', 'unknown')}: {e}")
                        logger.warning("Observer error: %s", e)

            # Cleanup old screenshots periodically
            if self._tick_count % 50 == 0:
                self._cleanup_old_screenshots()

        # Final observer pass
        for obs in self._observers:
            try:
                obs.run()
            except Exception as e:
                observer_errors.append(f"{getattr(obs, 'name', 'unknown')}: {e}")

        duration = time.time() - start_time
        print(f"\n[PlayEngine] DONE - {self._tick_count} ticks, "
              f"{len(self._screens_visited)} screen types, "
              f"{len(self._actions_executed)} actions in {duration:.0f}s")
        print(f"[PlayEngine] Screens visited: {dict(self._screens_visited)}")
        logger.info(
            "PlayEngine: done - %d ticks, %d screens, %d actions in %.0fs",
            self._tick_count, len(self._screens_visited),
            len(self._actions_executed), duration,
        )

        return {
            "tick_count": self._tick_count,
            "screens_visited": dict(self._screens_visited),
            "actions_executed": self._actions_executed,
            "duration": duration,
            "observer_errors": observer_errors,
        }

    def _tick(self, start_time: float) -> None:
        """Single play loop iteration.

        Decision cascade:
        1. GOAP decide -> execute if action found
        1.5. PatternExecutor -> replay learned behavior patterns
        2. ScreenActionResolver -> nav graph in_screen_actions (interaction/scroll)
        3. ActivityScheduler -> navigate to target via ScreenNavigator
        4. _explore_fallback() (last resort, grid taps)
        """
        # 1. Screenshot
        path = self._take_screenshot(f"play_{self._tick_count:04d}")
        if path is None:
            logger.warning("PlayEngine: screenshot failed at tick %d", self._tick_count)
            time.sleep(1.0)
            return

        # 2. Detect screen
        screen_type = self._detect_screen(path)
        self._screens_visited[screen_type] = self._screens_visited.get(screen_type, 0) + 1

        elapsed = time.time() - start_time
        remaining = self.play_duration - elapsed
        print(f"[PlayEngine] Tick {self._tick_count}: screen='{screen_type}' | "
              f"{elapsed:.0f}s/{self.play_duration}s ({remaining:.0f}s left)")

        # 3. Stuck detection
        if screen_type == self._last_screen_type:
            self._same_screen_count += 1
        else:
            self._same_screen_count = 0
            self._last_screen_type = screen_type
            # Reset stuck escape counter on screen change
            if screen_type != self._last_stuck_screen:
                self._stuck_escape_count = 0

        if self._same_screen_count >= self.STUCK_THRESHOLD:
            # Track consecutive stuck escapes on same screen type
            if screen_type == self._last_stuck_screen:
                self._stuck_escape_count += 1
            else:
                self._stuck_escape_count = 1
                self._last_stuck_screen = screen_type
            print(f"[PlayEngine] STUCK on '{screen_type}' ({self._same_screen_count} times, "
                  f"escape #{self._stuck_escape_count}), escaping...")
            logger.info("PlayEngine: stuck on '%s' (%d times, escape #%d), escaping",
                        screen_type, self._same_screen_count, self._stuck_escape_count)
            self._handle_stuck(screen_type)
            self._same_screen_count = 0
            return

        # 4. Read text for context
        texts = self._read_text(path)

        # --- Decision Cascade ---

        # Level 0: Ad detection -> handle ad and return to game
        if self._ad_detector is not None:
            try:
                ocr_texts = [t[0] for t in texts if isinstance(t[0], str)]
                ad_state = self._ad_detector.detect(str(path), ocr_texts)
                if ad_state.is_ad and self._ad_handler is not None:
                    print(f"[PlayEngine] AD DETECTED: type={ad_state.ad_type}")
                    result = self._ad_handler.handle_ad(ad_state)
                    self._actions_executed.append(result)
                    self._same_screen_count = 0
                    return
            except Exception as e:
                logger.debug("PlayEngine: ad detection error: %s", e)

        # Level 0.5: Unknown screen -> trigger exploration engine
        if screen_type == "unknown" and self._exploration_engine is not None:
            print(f"[PlayEngine] Unknown screen -- triggering ExplorationEngine (max_taps=5)")
            try:
                explore_result = self._exploration_engine.explore_current_screen(
                    screen_type="unknown", max_taps=5)
                transitions_found = explore_result.get("transitions_found", 0)
                elements_found = explore_result.get("elements_found", 0)
                print(f"[PlayEngine] Exploration result: {elements_found} elements, "
                      f"{transitions_found} transitions")
                if transitions_found > 0:
                    # A new screen was reached -- reset stuck counter so we continue normally
                    self._same_screen_count = 0
                    self._actions_executed.append("explore:unknown->transition")
                    # Optionally fingerprint the new screen
                    if self._fingerprinter is not None:
                        try:
                            new_path = self._take_screenshot("explore_new_screen")
                            if new_path:
                                self._fingerprinter.add_screenshot(new_path)
                        except Exception as fp_err:
                            logger.debug("PlayEngine: fingerprinter error: %s", fp_err)
                else:
                    self._actions_executed.append("explore:unknown->no_transition")
            except Exception as e:
                logger.warning("PlayEngine: exploration engine error: %s", e)
            return

        # Level 0.7: PuzzleSolver -- board recognition + targeted tap for puzzle genres
        if self.genre == "puzzle" and screen_type in ("gameplay", "battle"):
            try:
                move = self._try_puzzle_solve(path)
                if move is not None:
                    logger.info("PlayEngine: puzzle solve move=%s", move)
                    self._actions_executed.append(f"puzzle:{move[0]},{move[1]}")
                    self._same_screen_count = 0
                    return
            except Exception as e:
                logger.debug("PlayEngine: puzzle solver error: %s", e)

        # Level 0.8: CombatController -- skill rotation during battle
        if screen_type == "battle" and self._combat_controller is not None:
            try:
                game_state = self._build_snapshot(screen_type, texts, path)
                combat_action = self._combat_controller.tick(str(path), game_state)
                if combat_action:
                    print(f"[PlayEngine] CombatController: {combat_action}")
                    self._actions_executed.append(combat_action)
                    # Don't return -- let GOAP also run for strategic decisions
            except Exception as e:
                logger.debug("PlayEngine: combat_controller error: %s", e)

        # Level 1: GOAP decision (if reasoner available)
        action = None
        if self._reasoner:
            try:
                snapshot = self._build_snapshot(screen_type, texts, path)
                action = self._reasoner.decide(snapshot)
            except Exception as e:
                logger.debug("PlayEngine: reasoner error: %s", e)

        if action:
            action_name = getattr(action, "name", str(action))
            print(f"[PlayEngine] GOAP action: {action_name}")
            _before_state = snapshot if self._value_estimator is not None else None
            _action_start = time.time()
            self._execute_action(action, screen_type)
            if self._value_estimator is not None and _before_state is not None:
                try:
                    _after_path = self._take_screenshot(f"ve_{self._tick_count:04d}")
                    _after_state = self._build_snapshot(screen_type, [], _after_path) if _after_path else {}
                    self._value_estimator.record_outcome(
                        action_name, _before_state, _after_state, time.time() - _action_start)
                except Exception as _ve_err:
                    logger.debug("PlayEngine: value_estimator record error: %s", _ve_err)
            return

        # Level 1.5: PatternExecutor -- replay learned behavior patterns
        if self._pattern_executor:
            try:
                ocr_texts = [t[0] for t in texts if isinstance(t[0], str)]
                # Check if a learned pattern matches the current context
                if not self._pattern_executor.is_executing:
                    matched = self._pattern_executor.try_match(
                        screen_type, screenshot_path=path, ocr_texts=ocr_texts)
                    if matched:
                        self._pattern_executor.start_pattern(matched)

                # Execute next step of active pattern
                if self._pattern_executor.is_executing:
                    step_result = self._pattern_executor.execute_step(
                        screen_type, screenshot_path=path)
                    if step_result:
                        print(f"[PlayEngine] Pattern: {step_result}")
                        self._actions_executed.append(
                            f"pattern:{self._pattern_executor.active_pattern_name}")
                        return
            except Exception as e:
                logger.debug("PlayEngine: pattern executor error: %s", e)

        # Level 2: ScreenActionResolver -- nav graph in_screen_actions
        if self._resolver:
            # First, close overlays/popups
            if self._resolver.is_closeable(screen_type):
                print(f"[PlayEngine] Closing overlay: {screen_type}")
                self._resolver.close_overlay(screen_type)
                self._actions_executed.append(f"close:{screen_type}")
                return

            result = self._resolver.resolve(screen_type)
            if result:
                print(f"[PlayEngine] NavGraph action: {result}")
                self._actions_executed.append(f"nav:{result}")
                return

        # Level 3: ActivityScheduler -- time to switch screens?
        if self._scheduler:
            target = self._scheduler.tick(screen_type)
            if target and self._navigator:
                print(f"[PlayEngine] Scheduler: {screen_type}->{target}")
                try:
                    self._navigator.navigate_to(target)
                    self._actions_executed.append(f"sched:{screen_type}->{target}")
                except Exception as e:
                    logger.debug("PlayEngine: scheduler navigation failed: %s", e)
                return

        # Level 4: Explore fallback (last resort)
        self._explore_fallback()

    def _take_screenshot(self, label: str) -> Optional[Path]:
        """Take screenshot with retry logic."""
        for attempt in range(self.ADB_SCREENSHOT_RETRIES):
            path = self._screenshot(label)
            if path and path.exists():
                self._screenshot_paths.append(path)
                return path
            if attempt < self.ADB_SCREENSHOT_RETRIES - 1:
                time.sleep(0.5)
        return None

    def _build_snapshot(self, screen_type: str, texts: List, path: Path) -> Dict[str, Any]:
        """Build a snapshot dict suitable for GoalReasoner.decide()."""
        snapshot: Dict[str, Any] = {"screen_type": screen_type}

        # If state_reader available, get structured state
        if self._state_reader:
            try:
                state = self._state_reader.read_state(path, screen_type)
                if hasattr(state, "to_world_dict"):
                    snapshot.update(state.to_world_dict())
                else:
                    # Extract what we can from the snapshot
                    if hasattr(state, "gauges"):
                        for name, val in state.gauges.items():
                            if hasattr(val, "ratio"):
                                snapshot[f"{name}_pct"] = val.ratio
                    if hasattr(state, "resources"):
                        for name, reading in state.resources.items():
                            if hasattr(reading, "parsed_value") and reading.parsed_value is not None:
                                snapshot[name] = reading.parsed_value
            except Exception as e:
                logger.debug("PlayEngine: state reader error: %s", e)

        # OCR fallback: extract numbers from text
        for text_str, conf, y, x in texts:
            if isinstance(text_str, str):
                import re
                # Simple gold/gem/score extraction
                for keyword in ["gold", "gem", "score", "coin", "diamond"]:
                    if keyword in text_str.lower():
                        m = re.search(r"[\d,]+\.?\d*", text_str)
                        if m:
                            try:
                                val = float(m.group().replace(",", ""))
                                snapshot.setdefault(keyword, val)
                            except ValueError:
                                pass

        # Battle screen: detect MP depletion from bar pixels
        if screen_type == "battle":
            try:
                mp_pct = self._detect_mp_ratio(path)
                if mp_pct is not None:
                    snapshot["mp_pct"] = mp_pct
                    snapshot["needs_potion"] = mp_pct < 0.2
                    if mp_pct < 0.2:
                        print(f"[PlayEngine] Low MP detected: {mp_pct:.1%}")
            except Exception as e:
                logger.debug("PlayEngine: MP detection error: %s", e)

        # Append resource rates from ValueEstimator (flattened by WorldState.from_snapshot)
        if self._value_estimator is not None:
            snapshot["resource_rates"] = self._value_estimator.get_resource_rates()

        return snapshot

    def _detect_mp_ratio(self, screenshot_path: Path) -> Optional[float]:
        """Detect MP bar fill ratio from battle screen using gauge_bars config.

        Reads bar position and empty-color thresholds from self._gauge_bars["mp"].
        Returns ratio 0.0-1.0 or None if no config or detection fails.
        """
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

            bar_row = img[y, x_start:x_end, :]  # BGR
            red_ch = bar_row[:, 2].astype(float)
            blue_ch = bar_row[:, 0].astype(float)
            empty = (red_ch > r_min) & (blue_ch < b_max)
            ratio = 1.0 - float(np.sum(empty)) / max(1, len(empty))
            return ratio
        except Exception:
            return None

    def _execute_action(self, action: Any, current_screen: str) -> None:
        """Execute a GOAP action by navigating and tapping."""
        action_name = getattr(action, "name", str(action))
        required_screen = getattr(action, "required_screen", None)

        # Skip actions blocked on the current screen (e.g., buy_potion during battle)
        blocked_screens = getattr(action, "blocked_screens", [])
        if blocked_screens and current_screen in blocked_screens:
            print(f"[PlayEngine] Skipping '{action_name}' - blocked on '{current_screen}'")
            self._actions_executed.append(f"blocked:{action_name}")
            if self._reasoner:
                self._reasoner.advance()
            return

        # Navigate to required screen if needed
        if required_screen and required_screen != current_screen:
            # Monkey input can't target specific coordinates -- skip navigation
            if self._input_method == "monkey":
                print(f"[PlayEngine] Monkey mode: can't navigate {current_screen}->{required_screen}, exploring")
                self._explore_fallback()
                return
            # If stuck navigating (3+ attempts on same screen), try back key first
            if self._same_screen_count >= 3 and self._back_fn:
                print(f"[PlayEngine] Nav stuck on '{current_screen}' "
                      f"({self._same_screen_count}x), pressing back to clear popups")
                self._back_fn()
                self._actions_executed.append("nav:back_clear")
                return

            navigated = False
            # Try nav graph edge first (fast, reliable)
            if self._resolver:
                try:
                    graph = getattr(self._resolver, "_graph", None)
                    if graph:
                        edges = graph.get_edges_from(current_screen)
                        for edge in edges:
                            if edge.target == required_screen:
                                print(f"[PlayEngine] Nav edge: {current_screen}->{required_screen} "
                                      f"@({edge.action.x},{edge.action.y})")
                                self._tap(edge.action.x, edge.action.y, 3.0)
                                navigated = True
                                break
                except Exception as e:
                    logger.debug("PlayEngine: nav edge failed: %s", e)
            # Fallback to navigator
            if not navigated and self._navigator:
                try:
                    self._navigator.navigate_to(required_screen)
                    navigated = True
                except Exception as e:
                    logger.debug("PlayEngine: navigation failed: %s", e)
            # After navigation, return early -- let next tick verify screen changed
            if navigated:
                self._actions_executed.append(f"nav:{current_screen}->{required_screen}")
                return

        # Execute via action metadata or screen center tap
        metadata = getattr(action, "metadata", {})
        wait_time = metadata.get("wait", 3.0) if isinstance(metadata, dict) else 1.0
        if isinstance(metadata, dict):
            tap_x = metadata.get("tap_x")
            tap_y = metadata.get("tap_y")
            if tap_x is not None and tap_y is not None:
                # Pre-tap check: ensure button is active (e.g., stage_select move button)
                # Only runs when we're already on the required screen
                pre_check = metadata.get("pre_tap_check")
                if pre_check and callable(pre_check):
                    try:
                        check_path = self._take_screenshot(f"precheck_{self._tick_count:04d}")
                        if check_path:
                            if not pre_check(check_path, self._tap):
                                print(f"[PlayEngine] Pre-tap check: '{action_name}' button inactive, "
                                      f"selecting target first")
                                # Don't tap the main button yet -- let next tick re-check
                                self._actions_executed.append(f"precheck:{action_name}")
                                self._same_screen_count = 0
                                return
                    except Exception as e:
                        logger.debug("PlayEngine: pre-tap check error: %s", e)

                self._tap(int(tap_x), int(tap_y), wait_time)
                self._actions_executed.append(action_name)
                self._same_screen_count = 0
                logger.info("PlayEngine: executed '%s' at (%s, %s)", action_name, tap_x, tap_y)
                if self._reasoner:
                    self._reasoner.advance()
                return

        # No tap coordinates -- just wait (e.g., wait_in_battle)
        if isinstance(metadata, dict) and metadata.get("wait"):
            import time as _time
            print(f"[PlayEngine] Waiting {wait_time:.0f}s for '{action_name}'")
            _time.sleep(wait_time)
            self._actions_executed.append(action_name)
            self._same_screen_count = 0
            if self._reasoner:
                self._reasoner.advance()
            return

        # Default: tap center of screen as generic action
        cx, cy = self._screen_width // 2, self._screen_height // 2
        self._tap(cx, cy, 1.0)
        self._actions_executed.append(action_name)
        logger.info("PlayEngine: executed '%s' (center tap)", action_name)

        if self._reasoner:
            self._reasoner.advance()

    def _explore_fallback(self) -> None:
        """Grid-based exploration when no GOAP action is available."""
        cell_w = self._screen_width // self.EXPLORE_GRID_COLS
        cell_h = self._screen_height // self.EXPLORE_GRID_ROWS

        col = self._explore_index % self.EXPLORE_GRID_COLS
        row = (self._explore_index // self.EXPLORE_GRID_COLS) % self.EXPLORE_GRID_ROWS

        x = col * cell_w + cell_w // 2
        y = row * cell_h + cell_h // 2

        self._tap(x, y, 0.8)
        self._explore_index += 1
        self._actions_executed.append(f"explore_{col}_{row}")

    def _handle_stuck(self, screen_type: str = "unknown") -> None:
        """Try to escape a stuck state using nav graph knowledge.

        Strategies (in order):
        0. Back key (skip if already on lobby/battle -- those are playable screens)
        1. If 'unknown': relaunch game immediately (crash recovery)
        2. Resolver: close overlay via nav edges -> known close button coords
        3. Resolver: transition target -> nav edge with highest success
        4. Navigator: go to hub (lobby/battle)
        5. Fallback: game-specific positions + random tap
        """
        # Strategy 0: Android back key (safe escape for overlays/popups)
        # On first stuck: skip back key for playable screens (lobby/battle/town)
        # On 2nd+ stuck on same screen: use back key anyway (likely misclassified overlay)
        playable_screens = ("lobby", "battle", "town")
        use_back = self._back_fn and (
            screen_type not in playable_screens or self._stuck_escape_count >= 2
        )
        if use_back:
            print(f"[PlayEngine] Stuck escape: back key on '{screen_type}' "
                  f"(escape #{self._stuck_escape_count})")
            self._back_fn()
            self._actions_executed.append("stuck:back")
            return

        # Strategy 1: If stuck on "unknown", try relaunching (likely crash/ANR)
        if screen_type == "unknown" and self._relaunch_fn:
            print("[PlayEngine] Stuck on 'unknown' -- attempting game restart...")
            try:
                if self._relaunch_fn():
                    self._actions_executed.append("stuck:relaunch")
                    print("[PlayEngine] Game relaunched successfully")
                    return
            except Exception as e:
                logger.warning("PlayEngine: relaunch failed: %s", e)

        # Strategy 2: Use resolver to close overlay
        if self._resolver and self._resolver.is_closeable(screen_type):
            self._resolver.close_overlay(screen_type)
            self._actions_executed.append(f"stuck:close:{screen_type}")
            return

        # Strategy 3: Use resolver to find best transition (execute edge directly)
        if self._resolver:
            target = self._resolver.get_transition_target(screen_type)
            if target:
                # Try direct edge execution first (more reliable than navigator)
                try:
                    graph = getattr(self._resolver, "_graph", None)
                    if graph:
                        edges = graph.get_edges_from(screen_type)
                        for edge in edges:
                            if edge.target == target:
                                self._tap(edge.action.x, edge.action.y, 1.5)
                                self._actions_executed.append(f"stuck:edge:{screen_type}->{target}")
                                print(f"[PlayEngine] Stuck escape: edge {screen_type}->{target} "
                                      f"@({edge.action.x},{edge.action.y})")
                                return
                except Exception as e:
                    logger.debug("PlayEngine: stuck edge failed: %s", e)
                # Fallback to navigator
                if self._navigator:
                    try:
                        self._navigator.navigate_to(target)
                        self._actions_executed.append(f"stuck:nav:{screen_type}->{target}")
                        return
                    except Exception as e:
                        logger.debug("PlayEngine: stuck nav failed: %s", e)

        # Strategy 4: Navigate to hub via navigator
        if self._navigator:
            for hub in ("lobby", "battle"):
                try:
                    if self._navigator.navigate_to(hub):
                        self._actions_executed.append(f"stuck:hub:{hub}")
                        return
                except Exception:
                    continue

        # Strategy 5: Fallback close positions (game-specific or generic)
        fallback_positions = self._game_fallback_positions or [
            (540, 1870),   # Bottom center (close/confirm buttons)
            (978, 165),    # Top-right X button (verified for common RPGs)
            (60, 80),      # Top-left back arrow
        ]
        for x, y in fallback_positions:
            self._tap(x, y, 1.0)

        # Strategy 6: Random explore tap
        import random
        x = random.randint(100, self._screen_width - 100)
        y = random.randint(300, self._screen_height - 300)
        self._tap(x, y, 1.0)
        self._actions_executed.append("stuck:fallback")

    def _try_puzzle_solve(self, screenshot_path: Any) -> Optional[Tuple[int, int]]:
        """Run BoardReader + PuzzleSolver and tap the best cell.

        Returns (row, col) if a move was executed, None otherwise.
        Requires self._puzzle_board_config to be set (dict with board_rect, rows, cols, etc.)
        and self._puzzle_game_type to be set (e.g. "carmatch", "match3").
        Both are set lazily via self._init_puzzle_components() on first call.
        """
        self._init_puzzle_components()
        if self._board_reader is None or self._puzzle_solver is None:
            return None

        board_config = getattr(self, "_puzzle_board_config", None)
        if board_config is None:
            return None

        board = self._board_reader.read_board(str(screenshot_path), board_config)
        if board is None:
            return None

        game_type = getattr(self, "_puzzle_game_type", "generic")
        move = self._puzzle_solver.solve(board, game_type)
        if move is None:
            return None

        screen_x, screen_y = self._board_reader.board_to_screen_coords(
            move[0], move[1], board_config)
        print(f"[PlayEngine] Puzzle: tapping cell ({move[0]},{move[1]}) "
              f"-> screen ({screen_x},{screen_y})")
        self._tap(screen_x, screen_y, 1.0)
        return move

    def _init_puzzle_components(self) -> None:
        """Lazy-init BoardReader and PuzzleSolver (avoids cv2 import at module level)."""
        if getattr(self, "_puzzle_components_init", False):
            return
        self._puzzle_components_init = True
        self._board_reader = None
        self._puzzle_solver = None
        try:
            from .perception.board_reader import BoardReader
            from .reasoning.puzzle_solver import PuzzleSolver
            self._board_reader = BoardReader()
            self._puzzle_solver = PuzzleSolver()
            logger.info("PlayEngine: puzzle components initialized")
        except Exception as e:
            logger.warning("PlayEngine: could not init puzzle components: %s", e)

    def configure_ad_handling(self, game_package: str, launch_activity: str,
                             adb_fn, read_text_fn=None) -> None:
        """Configure ad detection and handling for autonomous play.

        Args:
            game_package: Target game package (e.g., "studio.gameberry.anv")
            launch_activity: Main activity for force-return
            adb_fn: ADB command runner callable
            read_text_fn: OCR text reader callable (optional, uses self._read_text if None)
        """
        try:
            from .perception.ad_detector import AdDetector, AdHandler
            self._ad_detector = AdDetector(
                game_package=game_package,
                adb_fn=adb_fn,
                read_text_fn=read_text_fn or self._read_text,
            )
            self._ad_handler = AdHandler(
                game_package=game_package,
                launch_activity=launch_activity,
                adb_fn=adb_fn,
                tap_fn=self._tap,
                screenshot_fn=self._screenshot,
                detector=self._ad_detector,
            )
            logger.info("PlayEngine: ad handling configured for %s", game_package)
        except Exception as e:
            logger.warning("PlayEngine: could not configure ad handling: %s", e)

    def configure_puzzle(self, board_config: dict, game_type: str = "carmatch") -> None:
        """Configure puzzle board layout and game type.

        Call this after constructing PlayEngine when genre="puzzle".

        Args:
            board_config: Dict with keys board_rect, rows, cols, holder_rect, holder_slots.
                          Use PuzzleSchema.get_board_config(game_type) for defaults.
            game_type: "carmatch" | "match3" | "generic"
        """
        self._puzzle_board_config = board_config
        self._puzzle_game_type = game_type
        logger.info("PlayEngine: puzzle configured -- game_type=%s, board_rect=%s",
                    game_type, board_config.get("board_rect"))

    def _cleanup_old_screenshots(self) -> None:
        """Keep only the most recent MAX_SCREENSHOTS files."""
        if self._temp_dir is None:
            return

        try:
            png_files = sorted(self._temp_dir.glob("*.png"))
            if len(png_files) > self.MAX_SCREENSHOTS:
                to_delete = png_files[:len(png_files) - self.MAX_SCREENSHOTS]
                for f in to_delete:
                    try:
                        f.unlink()
                    except OSError:
                        pass
                logger.debug("PlayEngine: cleaned up %d old screenshots", len(to_delete))
        except Exception as e:
            logger.debug("PlayEngine: cleanup error: %s", e)
