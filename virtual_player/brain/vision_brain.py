"""
Vision Brain (3-Tier)
======================
AI brain for Android games using 3-tier decision architecture.

L0: Reflex Cache (pHash → action, <50ms)
L1: Tactical Rules (nav_graph BFS, <200ms) + local template element finder
L2: Local Behavior Tree (SSIM classification + template matching + zone explore)
    Falls back to Claude Vision API only if local vision is unavailable.

Robustness:
- Deferred caching: L2 results only committed after screen change confirmed
- Failed edge tracking: L1 edges that don't work are excluded from future BFS
- Popup stuck prevention: cached dismiss coords invalidated after N failures
- Element coord cache: L1+BT results cached per screen_type+element
"""

import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .base import GameBrain, GameState, GameAction, TouchInput, ActionType
from ..adb import log, get_device_resolution
from ..navigation.classifier import ScreenClassifier, ScreenClassification, compute_phash
from ..navigation.nav_graph import NavigationGraph, NavEdge, NavAction
from ..navigation.popup_handler import PopupHandler
from ..navigation.screen_navigator import ScreenNavigator
from ..pattern_db.reflex_cache import ReflexCache, CachedAction
from ..pattern_db.tactical_rules import TacticalRules, GameObjective


class VisionBrain(GameBrain):
    """3-Tier decision brain for vision-based game playing.

    With optional intelligent layers:
    - Layer 1 (State Perception): Read HP/gold/stats from screenshots
    - Layer 2+3 (Goal Reasoning + Adaptive Planning): GOAP + utility AI + failure memory
    """

    _STUCK_THRESHOLD = 3       # Same screen N times → stuck
    _POPUP_RETRY_LIMIT = 5     # Popup dismiss failures before re-vision
    _POPUP_GIVEUP_LIMIT = 10   # Total popup failures before back key
    _L2_BACK_THRESHOLD = 4     # L2 attempts before trying systematic explore
    _L2_EXPLORE_ZONES = [      # Systematic tap zones (ratio of screen)
        (0.5, 0.95),   # bottom center (tab bar)
        (0.15, 0.95),  # bottom left (tab)
        (0.85, 0.95),  # bottom right (tab)
        (0.05, 0.05),  # top-left (back)
        (0.95, 0.05),  # top-right (settings/close)
        (0.5, 0.5),    # center (content)
        (0.05, 0.5),   # left sidebar
        (0.95, 0.5),   # right sidebar
    ]

    def __init__(
        self,
        screen_types: Dict[str, str],
        game_package: str,
        cache_dir: Path,
        skill_level: float = 0.5,
        nav_graph_path: Optional[Path] = None,
        screen_equivalences: Optional[Dict[str, str]] = None,
        state_reader=None,
        plan_adapter=None,
    ):
        super().__init__(skill_level=skill_level)
        self.game_package = game_package
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.screen_types = screen_types
        self._equivs = screen_equivalences or {}

        # Load reference DB for local vision
        self._reference_db = None
        self._local_vision = None
        # Reference DB: try games/{game}/reference_db first, then cache parent
        data_dir = cache_dir.parent.parent  # data/cache/game -> data/
        game_id = cache_dir.name            # e.g., "ash_n_veil"
        ref_db_candidates = [
            data_dir / "games" / game_id / "reference_db",
            cache_dir.parent / "reference_db",
            cache_dir / "reference_db",
        ]
        ref_db_path = next((p for p in ref_db_candidates if p.exists()), None)
        if ref_db_path:
            try:
                from .reference_db import ReferenceDB
                self._reference_db = ReferenceDB.load(ref_db_path)
                from .local_vision import LocalVision
                self._local_vision = LocalVision(self._reference_db)
                log(f"  [Brain] Reference DB loaded from {ref_db_path}")
            except Exception as e:
                log(f"  [Brain] Reference DB load failed: {e}")

        # Initialize components
        self.classifier = ScreenClassifier(screen_types, cache_dir / "classifier",
                                           reference_db=self._reference_db)
        self.popup_handler = PopupHandler(game_package, cache_dir / "popups",
                                          reference_db=self._reference_db)
        self.reflex_cache = ReflexCache(cache_dir / "reflex")
        self.graph = NavigationGraph()
        self.tactical = TacticalRules(self.graph, cache_dir / "tactical")

        # Load nav graph if available
        if nav_graph_path and nav_graph_path.exists():
            self.graph = NavigationGraph.load(nav_graph_path)
            self.tactical = TacticalRules(self.graph, cache_dir / "tactical")

        # State tracking
        self._last_classification: Optional[ScreenClassification] = None
        self._last_hash: Optional[int] = None
        self._current_target: Optional[str] = None
        self._objectives: List[GameObjective] = []
        self._decision_stats = {"l0": 0, "l1": 0, "l2": 0, "popup": 0}
        self._prev_screen: Optional[str] = None
        self._same_screen_count: int = 0

        # Deferred caching: only cache L2 results after confirming screen changed
        self._pending_cache: Optional[dict] = None
        # Track last L1 edge for failure marking
        self._last_l1_edge: Optional[NavEdge] = None

        # Popup stuck prevention
        self._popup_fail_count: int = 0
        self._popup_fail_type: Optional[str] = None

        # Element coordinate cache: (screen_type, element) -> (x, y)
        self._element_coord_cache: Dict[Tuple[str, str], Tuple[int, int]] = {}
        # Edges that failed with recorded coords — get one retry with Vision
        self._vision_retry_edges: set = set()  # (source, target, element)

        # Oscillation detection: track recent screens to detect A→B→A→B loops
        self._screen_history: List[str] = []  # last N screen types
        self._OSCILLATION_WINDOW = 6  # how many screens to track
        self._last_l0_target: Optional[str] = None  # track L0 action's intended target

        # L2 stuck tracking: consecutive L2 attempts on same screen
        self._l2_stuck_screen: Optional[str] = None
        self._l2_stuck_count: int = 0
        self._l2_recent_coords: List[Tuple[int, int]] = []  # coords tried
        self._l2_explore_idx: int = 0  # index into _L2_EXPLORE_ZONES

        # --- Intelligent layers (optional) ---
        self._state_reader = state_reader       # Layer 1: StateReader
        self._plan_adapter = plan_adapter       # Layer 2+3: PlanAdapter
        self._current_goap_action = None        # Current GOAP action being executed

    # --- GameBrain Interface ---

    def perceive(self, raw_state: Any) -> GameState:
        """Classify a screenshot into a GameState."""
        screenshot_path = Path(raw_state)

        # Compute perceptual hash for L0 cache
        self._last_hash = compute_phash(screenshot_path)

        # Classify screen (2-tier: pHash cache -> Vision API)
        cls = self.classifier.classify(screenshot_path)
        self._last_classification = cls

        # Deferred caching: commit pending L2 result only if screen changed
        # to a REAL screen (not a popup — popups are overlays, not real transitions)
        if self._pending_cache:
            prev = self._pending_cache["screen_type"]
            intended_target = self._pending_cache["target"]
            is_popup_dest = any(
                cls.screen_type.startswith(p)
                for p in PopupHandler.POPUP_PREFIXES
            )
            if cls.screen_type != prev and not is_popup_dest:
                # Only cache with target context if we reached the intended target.
                # If we ended up on a WRONG screen, cache with actual destination
                # as context (not original target) to avoid poisoning L0 cache.
                if intended_target and cls.screen_type != intended_target:
                    log(f"  [Brain] Deferred cache: {prev}->{cls.screen_type} "
                        f"(wrong target, wanted {intended_target}, skipping L0)")
                else:
                    log(f"  [Brain] Deferred cache commit: {prev}->{cls.screen_type}")
                    self._store_in_cache(
                        self._pending_cache["screen_type"],
                        self._pending_cache["target"],
                        self._pending_cache["action"],
                        phash=self._pending_cache["hash"],
                    )
                self._pending_cache = None
            elif cls.screen_type == prev:
                # Same screen — action didn't work, discard
                self._pending_cache = None
            # else: popup appeared — keep pending, will commit when popup dismissed

        # L1 edge validation: check if we reached the expected target
        if self._last_l1_edge:
            is_popup_screen = any(
                cls.screen_type.startswith(p)
                for p in PopupHandler.POPUP_PREFIXES
            )
            if not is_popup_screen:
                if cls.screen_type == self._last_l1_edge.target:
                    # Reached the intended target — edge succeeded
                    log(f"  [Brain] L1 edge succeeded: ->{cls.screen_type}")
                    self._last_l1_edge = None
                elif cls.screen_type != self._last_l1_edge.source:
                    # Reached a WRONG screen — edge coords/action is incorrect
                    edge = self._last_l1_edge
                    edge_key = (edge.source, edge.target, edge.action.element)
                    elem_key = (edge.source, edge.action.element)
                    if edge_key not in self._vision_retry_edges:
                        self._vision_retry_edges.add(edge_key)
                        if elem_key in self._element_coord_cache:
                            del self._element_coord_cache[elem_key]
                        log(f"  [Brain] Wrong screen ({cls.screen_type} instead of "
                            f"{edge.target}), will retry: {edge.source}->{edge.target}")
                    else:
                        self.tactical.mark_edge_failed(edge)
                        if elem_key in self._element_coord_cache:
                            del self._element_coord_cache[elem_key]
                        log(f"  [Brain] Wrong screen 2x, edge failed: "
                            f"{edge.source}->{edge.target}")
                    self._last_l1_edge = None

        # L0 wrong-screen detection: if L0 intended target X but we got Y
        if self._last_l0_target:
            is_popup_screen = any(
                cls.screen_type.startswith(p)
                for p in PopupHandler.POPUP_PREFIXES
            )
            if not is_popup_screen and cls.screen_type != self._last_l0_target:
                # L0 cache action led to wrong screen — invalidate it
                log(f"  [Brain] L0 cache wrong: wanted {self._last_l0_target}, "
                    f"got {cls.screen_type}, invalidating L0 entry")
                self.reflex_cache.invalidate_by_type(
                    self._prev_screen or "", context=self._last_l0_target)
            self._last_l0_target = None

        # Track screen history for oscillation detection
        self._screen_history.append(cls.screen_type)
        if len(self._screen_history) > self._OSCILLATION_WINDOW:
            self._screen_history = self._screen_history[-self._OSCILLATION_WINDOW:]

        # Popup stuck: screen changed away from popup → reset counter
        if self._popup_fail_type and cls.screen_type != self._popup_fail_type:
            self._popup_fail_count = 0
            self._popup_fail_type = None

        parsed = {
            "screen_type": cls.screen_type,
            "confidence": cls.confidence,
            "sub_info": cls.sub_info,
            "is_popup": self.popup_handler.is_popup(cls),
        }

        # --- Layer 1: State Perception ---
        if self._state_reader:
            try:
                snapshot = self._state_reader.read_state(screenshot_path, cls.screen_type)
                parsed["snapshot"] = snapshot
            except Exception as e:
                log(f"  [Brain] StateReader error: {e}")

        return GameState(
            raw=screenshot_path,
            parsed=parsed,
            score=0.0,
            is_game_over=False,
            timestamp=time.time(),
        )

    def decide(self, state: GameState) -> GameAction:
        """3-tier decision: L0 (reflex) -> L1 (tactical) -> L2 (vision)."""
        screen_type = state.parsed.get("screen_type", "unknown")
        is_popup = state.parsed.get("is_popup", False)

        # --- Handle popups first (with stuck prevention) ---
        if is_popup:
            self._decision_stats["popup"] += 1
            return self._handle_popup(state)

        # --- Stuck detection (non-popup screens only) ---
        if screen_type == self._prev_screen:
            self._same_screen_count += 1
        else:
            self._same_screen_count = 0
            self._prev_screen = screen_type

        is_stuck = self._same_screen_count >= self._STUCK_THRESHOLD

        # --- Oscillation detection (A→B→A→B pattern) ---
        is_oscillating = False
        if len(self._screen_history) >= 4:
            h = self._screen_history
            # Check for A→B→A→B pattern (last 4 entries)
            if (h[-1] == h[-3] and h[-2] == h[-4]
                    and h[-1] != h[-2]):
                is_oscillating = True
                log(f"  [Brain] OSCILLATION detected: {h[-2]}↔{h[-1]}, "
                    f"treating as stuck")

        if is_oscillating:
            is_stuck = True

        # --- Intelligent layers: PlanAdapter (GOAP + utility AI) ---
        if self._plan_adapter and state.parsed.get("snapshot"):
            try:
                goap_action = self._plan_adapter.decide(state.parsed["snapshot"])
                if goap_action and goap_action.required_screen:
                    # GOAP wants us to navigate to a specific screen
                    self._current_target = goap_action.required_screen
                    self._current_goap_action = goap_action
                    log(f"  [Brain GOAP] Target: {goap_action.required_screen} "
                        f"(action: {goap_action.name})")

                # If we're ON the required screen, execute the GOAP action
                if (self._current_goap_action
                        and screen_type == self._current_goap_action.required_screen
                        and self._current_goap_action.execute_fn):
                    result = self._current_goap_action.execute_fn(state)
                    if result:
                        self._plan_adapter.reasoner.advance()
                        self._current_goap_action = None
                        return result
            except Exception as e:
                log(f"  [Brain GOAP] Error: {e}")

        # --- L0: Reflex cache (skip if stuck) ---
        target = self._get_current_target(screen_type)

        # L0 type+context (goal-aware) — preferred when we have a target
        if target and not is_stuck:
            cached = self.reflex_cache.lookup_by_type(screen_type, context=target)
            if cached:
                self._decision_stats["l0"] += 1
                self._last_l0_target = target  # track for wrong-screen detection
                log(f"  [Brain L0] Type cache: {screen_type}->{target}: "
                    f"{cached.action_type} ({cached.x},{cached.y})")
                return self._cached_to_action(cached, "L0_type")

        # L0 hash lookup disabled — context-free pHash matching causes
        # oscillation loops (e.g., lobby→menu_shop→lobby→...) because it
        # replays actions regardless of the current goal. The type+context
        # lookup above handles goal-aware caching for known situations.

        # --- L1: Tactical nav_graph pathfinding (skip if stuck) ---
        if target and self.graph.nodes and not is_stuck:
            edge = self.tactical.get_next_action(screen_type, target, self._equivs)
            if edge:
                self._decision_stats["l1"] += 1
                log(f"  [Brain L1] Tactical: {screen_type}->{edge.target} "
                    f"via {edge.action.action_type} [{edge.action.element}]")
                self._last_l1_edge = edge
                action = self._edge_to_action(edge)
                self.tactical.advance_plan()
                return action

        # --- L2: Local BT decision (replaces Claude Vision) ---
        self._decision_stats["l2"] += 1
        if is_stuck:
            if self._last_l1_edge:
                edge_key = (self._last_l1_edge.source,
                            self._last_l1_edge.target,
                            self._last_l1_edge.action.element)
                elem_key = (self._last_l1_edge.source,
                            self._last_l1_edge.action.element)

                if edge_key not in self._vision_retry_edges:
                    # First failure: recorded coords didn't work → try Vision next
                    self._vision_retry_edges.add(edge_key)
                    if elem_key in self._element_coord_cache:
                        del self._element_coord_cache[elem_key]
                    log(f"  [Brain] Coords failed, will retry with Vision: "
                        f"{self._last_l1_edge.source}->{self._last_l1_edge.target} "
                        f"[{self._last_l1_edge.action.element}]")
                else:
                    # Second failure: Vision coords also failed → mark edge dead
                    self.tactical.mark_edge_failed(self._last_l1_edge)
                    if elem_key in self._element_coord_cache:
                        del self._element_coord_cache[elem_key]
                    log(f"  [Brain] Marked failed edge: {self._last_l1_edge.source}"
                        f"->{self._last_l1_edge.target} "
                        f"[{self._last_l1_edge.action.element}]")
                self._last_l1_edge = None
            self.tactical.clear_plan()
            if is_oscillating:
                log(f"  [Brain L2] OSCILLATION → L2 on {screen_type}")
            else:
                log(f"  [Brain L2] STUCK on {screen_type} ({self._same_screen_count}x), fresh vision")
            self._same_screen_count = 0
            self._screen_history.clear()
        else:
            log(f"  [Brain L2] Vision: screen={screen_type} target={target}")

        # Track L2 stuck count per screen for explore escalation
        if screen_type == self._l2_stuck_screen:
            self._l2_stuck_count += 1
        else:
            self._l2_stuck_screen = screen_type
            self._l2_stuck_count = 1
            self._l2_recent_coords = []
            self._l2_explore_idx = 0

        # L2 escalation: Vision(1-4) → Explore zones(5-12) → Back(13+)
        if self._l2_stuck_count > self._L2_BACK_THRESHOLD:
            zone_idx = self._l2_stuck_count - self._L2_BACK_THRESHOLD - 1
            if zone_idx < len(self._L2_EXPLORE_ZONES):
                # Systematic exploration: try each zone
                rx, ry = self._L2_EXPLORE_ZONES[zone_idx]
                w, h = get_device_resolution()
                x, y = int(w * rx), int(h * ry)
                self._l2_recent_coords.append((x, y))
                log(f"  [Brain L2] EXPLORE zone {zone_idx}: ({x},{y}) "
                    f"[{self._l2_stuck_count}x on {screen_type}]")
                action = self._make_tap_action(x, y, f"L2_explore_{screen_type}")
                # Deferred caching for explore actions too
                self._pending_cache = {
                    "screen_type": screen_type,
                    "target": target,
                    "action": action,
                    "hash": self._last_hash,
                }
                return action
            else:
                # All zones exhausted → Back key escape
                log(f"  [Brain L2] ESCAPE: {screen_type} stuck {self._l2_stuck_count}x, Back key")
                self._l2_stuck_count = 0
                self._l2_recent_coords = []
                self._l2_explore_idx = 0
                return GameAction(
                    name=f"L2_back_escape_{screen_type}",
                    description=f"L2_back_escape_{screen_type}",
                    inputs=[TouchInput(action_type=ActionType.KEY_PRESS, key="back")],
                )

        action = self._vision_decide(state, target, force_different=is_stuck)

        # Deferred caching: wait for next perceive() to confirm
        self._pending_cache = {
            "screen_type": screen_type,
            "target": target,
            "action": action,
            "hash": self._last_hash,
        }

        return action

    def translate_to_input(self, action: GameAction) -> List[TouchInput]:
        return action.inputs

    # --- Objectives ---

    def set_objectives(self, objectives: List[GameObjective]):
        self._objectives = objectives
        self.tactical.set_objectives(objectives)

    def set_target(self, target: str):
        self._current_target = target

    # --- Nav Graph ---

    def load_nav_graph(self, path: Path):
        self.graph = NavigationGraph.load(path)
        self.tactical = TacticalRules(self.graph, self.cache_dir / "tactical")

    # --- Internal ---

    def _is_equivalent(self, screen_a: str, screen_b: str) -> bool:
        if screen_a == screen_b:
            return True
        base_a = self._equivs.get(screen_a, screen_a)
        base_b = self._equivs.get(screen_b, screen_b)
        return base_a == base_b

    def _get_current_target(self, current_screen: str) -> Optional[str]:
        """Determine what screen to navigate to next."""
        if self._current_target:
            if self._is_equivalent(current_screen, self._current_target):
                self._current_target = None
            else:
                return self._current_target

        obj = self.tactical.get_current_objective()
        if obj:
            for target in obj.target_screens:
                if not self._is_equivalent(current_screen, target):
                    return target
            obj.completed = True

        # Free play: explore least-visited reachable screens
        if self.graph.nodes:
            candidates = [
                s for s in self.graph.get_all_screen_types()
                if not self._is_equivalent(current_screen, s) and s != "unknown"
                and not s.startswith("popup_") and s not in ("loading", "black_screen")
            ]
            if candidates:
                candidates.sort(
                    key=lambda s: self.graph.nodes[s].visit_count
                    if s in self.graph.nodes else 0
                )
                failed = getattr(self.tactical, '_failed_edges', set())
                for c in candidates:
                    path = self.graph.find_path(current_screen, c, excluded_edges=failed)
                    if path is not None and len(path) > 0:
                        return c
                # No L1 path available — return None so L2 explores freely
                return None

        return None

    # --- Popup Handling (with stuck prevention) ---

    def _handle_popup(self, state: GameState) -> GameAction:
        """Handle popup with retry-aware stuck prevention.

        Strategy:
        1. Try cached dismiss coords (up to POPUP_RETRY_LIMIT)
        2. On limit: invalidate cache, ask Vision for new coords
        3. On POPUP_GIVEUP_LIMIT: press Back key
        """
        cls = self._last_classification
        screenshot_path = Path(state.raw)

        if not cls:
            return self._make_wait_action("no_classification")

        popup_type = cls.screen_type

        # Track consecutive popup failures
        if popup_type == self._popup_fail_type:
            self._popup_fail_count += 1
        else:
            self._popup_fail_count = 1
            self._popup_fail_type = popup_type

        # Stage 3: Give up — press Back key
        if self._popup_fail_count >= self._POPUP_GIVEUP_LIMIT:
            log(f"  [Brain] Popup {popup_type} GIVEUP ({self._popup_fail_count}x), pressing Back")
            self._popup_fail_count = 0
            return GameAction(
                name=f"back_dismiss_{popup_type}",
                description=f"back_dismiss_{popup_type}",
                inputs=[TouchInput(action_type=ActionType.KEY_PRESS, key="back")],
            )

        # Stage 2: Cached coords failed too many times — re-ask Vision
        if self._popup_fail_count >= self._POPUP_RETRY_LIMIT:
            # Invalidate cached coords
            if popup_type in self.popup_handler._dismiss_cache:
                del self.popup_handler._dismiss_cache[popup_type]
                log(f"  [Brain] Popup {popup_type} cache invalidated, re-asking Vision")

            coords = self.popup_handler._find_close_button(screenshot_path)
            if coords:
                x, y = coords
                self.popup_handler._dismiss_cache[popup_type] = coords
                self.popup_handler._save_cache()
                log(f"  [Brain] Popup {popup_type} dismiss (re-vision: {x},{y})")
                return self._make_tap_action(x, y, f"dismiss_popup_{popup_type}")

            # Vision also failed — fallback tap
            log(f"  [Brain] Popup {popup_type} Vision re-try failed, fallback")
            return self._make_tap_action(960, 320, f"popup_fallback_{popup_type}")

        # Stage 1: Try cached coords (normal path)
        if popup_type in self.popup_handler._dismiss_cache:
            x, y = self.popup_handler._dismiss_cache[popup_type]
            log(f"  [Brain] Popup {popup_type} dismiss (cached: {x},{y}) "
                f"[attempt {self._popup_fail_count}/{self._POPUP_RETRY_LIMIT}]")
            return self._make_tap_action(x, y, f"dismiss_popup_{popup_type}")

        # No cache yet — ask Vision
        coords = self.popup_handler._find_close_button(screenshot_path)
        if coords:
            x, y = coords
            self.popup_handler._dismiss_cache[popup_type] = coords
            self.popup_handler._save_cache()
            log(f"  [Brain] Popup {popup_type} dismiss (vision: {x},{y})")
            return self._make_tap_action(x, y, f"dismiss_popup_{popup_type}")

        log(f"  [Brain] Popup {popup_type} fallback dismiss")
        return self._make_tap_action(960, 320, f"popup_fallback_{popup_type}")

    # --- L1 Edge Execution (Vision-guided with caching) ---

    def _edge_to_action(self, edge: NavEdge) -> GameAction:
        """Convert a NavEdge to a GameAction.

        Strategy: recorded coords first (fast), Vision only when coords fail.
        L1 provides "what" (element + target), recorded coords provide "where",
        Vision provides "where" as fallback when recorded coords are stale.
        """
        act = edge.action
        name = f"L1_{edge.source}->{edge.target}"

        if act.action_type == "back":
            return GameAction(
                name=name, description=name,
                inputs=[TouchInput(action_type=ActionType.KEY_PRESS, key="back")],
            )

        # Check element coordinate cache (from successful Vision lookups)
        if act.element:
            cache_key = (edge.source, act.element)
            if cache_key in self._element_coord_cache:
                x, y = self._element_coord_cache[cache_key]
                log(f"  [Brain L1] Cached coords: {act.element} at ({x},{y})")
                return self._make_tap_action(x, y, name)

        # Try recorded coordinates from nav_graph (fast, no API call)
        # Skip if this edge already failed with recorded coords (needs Vision)
        edge_key = (edge.source, edge.target, act.element)
        needs_vision = edge_key in self._vision_retry_edges
        has_recorded_coords = (act.x != 0 or act.y != 0) and not needs_vision
        if has_recorded_coords:
            if act.action_type == "tap" or (
                act.action_type == "swipe"
                and abs(act.x - act.x2) < 30 and abs(act.y - act.y2) < 30
            ):
                log(f"  [Brain L1] Recorded coords: {act.element} at ({act.x},{act.y})")
                return self._make_tap_action(act.x, act.y, name)
            elif act.action_type == "swipe":
                log(f"  [Brain L1] Recorded swipe: ({act.x},{act.y})->({act.x2},{act.y2})")
                return self._make_swipe_action(act.x, act.y, act.x2, act.y2, name)

        # No recorded coords — use local template matching to find the element
        screenshot_path = (Path(self._last_classification.screenshot_path)
                          if self._last_classification else None)
        if screenshot_path and screenshot_path.exists() and act.element:
            coords = self._local_find_element(edge, screenshot_path)
            if coords:
                x, y = coords
                if act.element:
                    self._element_coord_cache[(edge.source, act.element)] = (x, y)
                log(f"  [Brain L1+BT] {act.element} at ({x},{y})")
                return self._make_tap_action(x, y, name)

        return self._make_wait_action(name)

    def _local_find_element(self, edge: NavEdge,
                            screenshot_path=None) -> Optional[tuple]:
        """Find an element using local template matching.

        Returns (x, y) or None.
        """
        if not self._local_vision:
            return None
        if screenshot_path is None:
            screenshot_path = (Path(self._last_classification.screenshot_path)
                              if self._last_classification else None)
        if not screenshot_path or not screenshot_path.exists():
            return None
        return self._local_vision.find_element_by_region(
            screenshot_path, edge.source, edge.action.element
        )

    # --- L2 Vision ---

    def _vision_decide(self, state: GameState, target: Optional[str],
                       force_different: bool = False) -> GameAction:
        """Local behavior tree decision (replaces Claude Vision L2).

        BT strategy:
        1. Template-match known elements for target screen edges
        2. Try any outgoing edge from current screen
        3. Systematic zone exploration
        """
        screenshot_path = Path(state.raw)
        screen_type = state.parsed.get("screen_type", "unknown")
        w, h = get_device_resolution()

        # --- BT Node 1: Try template-matching edges toward target ---
        if target and self._local_vision and self.graph.nodes:
            edges = self.graph.get_edges_from(screen_type)
            target_edges = [e for e in edges if e.target == target]
            for edge in target_edges:
                coords = self._local_find_element(edge, screenshot_path)
                if coords:
                    x, y = coords
                    self._l2_recent_coords.append((x, y))
                    log(f"  [Brain BT] Target edge: {edge.action.element} "
                        f"at ({x},{y}) -> {target}")
                    return self._make_tap_action(
                        x, y, f"BT_target_{edge.action.element}")

        # --- BT Node 2: Try any outgoing edge from current screen ---
        if self._local_vision and self.graph.nodes:
            failed = getattr(self.tactical, '_failed_edges', set())
            for edge in self.graph.get_edges_from(screen_type):
                edge_key = (edge.source, edge.target, edge.action.element)
                if edge_key in failed:
                    continue
                # Skip recently tried coordinates
                coords = self._local_find_element(edge, screenshot_path)
                if coords:
                    x, y = coords
                    # Avoid re-tapping same coords
                    if not any(abs(x-px) < 30 and abs(y-py) < 30
                               for px, py in self._l2_recent_coords[-6:]):
                        self._l2_recent_coords.append((x, y))
                        log(f"  [Brain BT] Any edge: {edge.action.element} "
                            f"at ({x},{y}) -> {edge.target}")
                        return self._make_tap_action(
                            x, y, f"BT_edge_{edge.action.element}")

        # --- BT Node 3: Systematic zone exploration ---
        zone_idx = self._l2_explore_idx % len(self._L2_EXPLORE_ZONES)
        rx, ry = self._L2_EXPLORE_ZONES[zone_idx]
        x, y = int(w * rx), int(h * ry)
        self._l2_explore_idx += 1
        self._l2_recent_coords.append((x, y))
        log(f"  [Brain BT] Explore zone {zone_idx}: ({x},{y})")
        return self._make_tap_action(x, y, f"BT_explore_{zone_idx}")

    # --- Caching ---

    def _store_in_cache(self, screen_type: str, target: Optional[str],
                        action: GameAction, phash: Optional[int] = None):
        """Store a verified-successful action in L0 cache."""
        if not action.inputs:
            return

        inp = action.inputs[0]
        cached = CachedAction(
            action_type=inp.action_type.value,
            x=int(inp.x),
            y=int(inp.y),
            x2=int(inp.end_x),
            y2=int(inp.end_y),
            description=action.description,
        )

        use_hash = phash if phash is not None else self._last_hash
        context = target or ""
        self.reflex_cache.store(use_hash, screen_type, cached, context)

        if target:
            self.tactical.learn_pattern(
                screen_type,
                {"action_type": inp.action_type.value,
                 "x": int(inp.x), "y": int(inp.y), "target": target},
                success=True,
            )

    # --- Action Builders ---

    def _make_tap_action(self, x: int, y: int, name: str) -> GameAction:
        return GameAction(
            name=name, description=name,
            inputs=[TouchInput(action_type=ActionType.TAP, x=float(x), y=float(y))],
        )

    def _make_swipe_action(self, x1: int, y1: int, x2: int, y2: int,
                           name: str) -> GameAction:
        return GameAction(
            name=name, description=name,
            inputs=[TouchInput(
                action_type=ActionType.SWIPE,
                x=float(x1), y=float(y1),
                end_x=float(x2), end_y=float(y2),
                duration=0.3,
            )],
        )

    def _make_wait_action(self, name: str) -> GameAction:
        return GameAction(
            name=name, description=name,
            inputs=[TouchInput(action_type=ActionType.WAIT, duration=1.0)],
        )

    def _cached_to_action(self, cached: CachedAction, name: str) -> GameAction:
        if cached.action_type == "tap":
            return self._make_tap_action(cached.x, cached.y, name)
        elif cached.action_type == "swipe":
            return self._make_swipe_action(
                cached.x, cached.y, cached.x2, cached.y2, name
            )
        elif cached.action_type == "back":
            return GameAction(
                name=name, description=name,
                inputs=[TouchInput(action_type=ActionType.KEY_PRESS, key="back")],
            )
        return self._make_wait_action(name)

    # --- Stats & Persistence ---

    def get_decision_stats(self) -> Dict[str, int]:
        return {
            **self._decision_stats,
            "classifier": self.classifier.get_stats(),
            "reflex": self.reflex_cache.get_stats(),
        }

    def save_all_caches(self):
        self.classifier.save_cache()
        self.reflex_cache.save()
        self.tactical.save()
        self.popup_handler._save_cache()
        log(f"  [Brain] All caches saved. Stats: {self._decision_stats}")
