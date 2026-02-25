"""
VirtualPlayer Orchestrator
============================
메인 루프: connect → perceive → decide → input → log.
모든 모듈을 통합하여 자동 게임 플레이를 실행합니다.

Modes:
- Web mode (기존): Brain registry + Adapter registry로 게임 플레이
- ADB mode (신규): VisionBrain + ADBAdapter로 Android 게임 플레이
"""

import asyncio
import time
import uuid
from pathlib import Path
from typing import Dict, Optional

from .config import (
    DEFAULT_GAME, DEFAULT_PERSONA, DEFAULT_SESSION_PATTERN,
    DEFAULT_SESSION_COUNT, ADB_CACHE_DIR, ADB_TEMP_DIR,
)
from .brain import get_brain, create_vision_brain, GameBrain
from .brain.base import GameState
from .adapters import get_adapter, create_adb_adapter, GameAdapter
from .persona import get_persona, load_devices, generate_user_agent, Persona
from .touch import TouchSimulator, Humanizer
from .session import SessionManager, get_session_pattern
from .history import Tracker, HistoryStorage


# ============================================================
# Orchestrator
# ============================================================

class VirtualPlayer:
    """가상 플레이어 오케스트레이터."""

    def __init__(
        self,
        game_id: str = DEFAULT_GAME,
        persona_name: str = DEFAULT_PERSONA,
        session_pattern: str = DEFAULT_SESSION_PATTERN,
        # ADB mode parameters
        adb_mode: bool = False,
        package_name: str = "",
        screen_types: Optional[Dict[str, str]] = None,
        nav_graph_path: Optional[Path] = None,
        screen_equivalences: Optional[Dict[str, str]] = None,
        # Intelligent layer parameters
        profile_path: Optional[Path] = None,
    ):
        self.game_id = game_id
        self.persona_name = persona_name
        self.session_pattern_name = session_pattern
        self.adb_mode = adb_mode

        # Initialize persona
        self.persona: Persona = get_persona(persona_name)
        devices = load_devices()
        self.device = self.persona.pick_device(devices)
        self.user_agent = generate_user_agent(self.device)

        if adb_mode:
            # --- ADB mode: VisionBrain + ADBAdapter ---
            if not package_name:
                raise ValueError("package_name is required for ADB mode")
            if not screen_types:
                raise ValueError("screen_types dict is required for ADB mode")

            cache_dir = ADB_CACHE_DIR / game_id

            # --- Build intelligent layers if profile is provided ---
            state_reader = None
            plan_adapter = None
            if profile_path and profile_path.exists():
                state_reader, plan_adapter = self._build_intelligent_layers(
                    profile_path, cache_dir
                )

            self.brain: GameBrain = create_vision_brain(
                screen_types=screen_types,
                game_package=package_name,
                cache_dir=cache_dir,
                skill_level=self.persona.skill.strategy,
                nav_graph_path=nav_graph_path,
                screen_equivalences=screen_equivalences,
                state_reader=state_reader,
                plan_adapter=plan_adapter,
            )
            self.adapter: GameAdapter = create_adb_adapter(
                package_name=package_name,
                temp_dir=ADB_TEMP_DIR / game_id,
            )
        else:
            # --- Web mode (기존): Brain registry + Adapter registry ---
            self.brain = get_brain(game_id, skill_level=self.persona.skill.strategy)
            device_profile = {
                "name": self.device.name,
                "width": self.device.width,
                "height": self.device.height,
                "dpi": self.device.dpi,
            }
            self.adapter = get_adapter(
                game_id,
                user_agent=self.user_agent,
                device_profile=device_profile,
            )

        # Initialize touch simulator
        humanizer = Humanizer()
        self.touch_sim = TouchSimulator(humanizer=humanizer)

        # Initialize session manager
        pattern = get_session_pattern(session_pattern)
        self.session_mgr = SessionManager(pattern)

        # Initialize history
        self.storage = HistoryStorage()
        self.storage.connect()
        self.tracker = Tracker(self.storage)

    async def play_session(self) -> dict:
        """게임 1세션 플레이."""
        session_id = str(uuid.uuid4())[:8]

        print(f"[VirtualPlayer] Session {session_id} starting...")
        print(f"  Game: {self.game_id}")
        print(f"  Persona: {self.persona.name} (skill={self.persona.skill.strategy:.1f})")
        print(f"  Device: {self.device.name}")
        print(f"  Pattern: {self.session_pattern_name}")

        # Start session
        session_state = self.session_mgr.start(
            session_id=session_id,
            game_id=self.game_id,
            persona_name=self.persona_name,
        )
        self.tracker.begin_session(
            session_id=session_id,
            game_id=self.game_id,
            persona_name=self.persona_name,
            pattern_name=self.session_pattern_name,
            metadata={"device": self.device.name, "ua": self.user_agent},
        )

        # Connect to game
        async with self.adapter:
            last_state: Optional[GameState] = None
            action_count = 0

            while not session_state.is_finished:
                # Update session state
                session_state = self.session_mgr.update()
                if session_state.is_finished:
                    break

                # Handle breaks
                if session_state.is_on_break:
                    await asyncio.sleep(1.0)
                    continue

                # Get game state
                raw_state = await self.adapter.get_game_state()
                game_state = self.brain.perceive(raw_state)

                # Check game over
                if game_state.is_game_over:
                    print(f"  Game Over! Score: {game_state.score:.0f}")
                    # Try to restart if adapter supports it
                    if hasattr(self.adapter, 'restart_game'):
                        await self.adapter.restart_game()
                        await asyncio.sleep(1.0)
                        continue
                    else:
                        break

                # Decide action
                action = self.brain.decide(game_state)
                if not action.inputs:
                    action.inputs = self.brain.translate_to_input(action)

                # Humanize inputs
                humanized = await self.touch_sim.prepare_inputs(
                    action.inputs, fatigue=session_state.fatigue
                )
                action.inputs = humanized

                # Track pre-action screen for outcome reporting
                prev_screen = game_state.parsed.get("screen_type")

                # Send input
                await self.adapter.send_input(action.inputs)

                # Record
                self.tracker.record_action(action, game_state)
                self.session_mgr.record_action()
                action_count += 1
                last_state = game_state

                # Maybe take a break
                self.session_mgr.maybe_take_break()

                # Wait before next action
                delay = self.touch_sim.get_delay_before_next(
                    fatigue=session_state.fatigue
                )
                await asyncio.sleep(delay)

                # Progress report every 50 actions
                if action_count % 50 == 0:
                    score = last_state.score if last_state else 0
                    print(f"  ... {action_count} actions, score={score:.0f}, "
                          f"fatigue={session_state.fatigue:.2f}")

        # End session
        final_state = self.session_mgr.finish()
        self.tracker.end_session(
            duration_seconds=final_state.elapsed_seconds,
            action_count=final_state.action_count,
        )

        final_score = last_state.score if last_state else 0
        print(f"[VirtualPlayer] Session {session_id} finished.")
        print(f"  Duration: {final_state.elapsed_seconds:.1f}s")
        print(f"  Actions: {action_count}")
        print(f"  Final score: {final_score:.0f}")

        return {
            "session_id": session_id,
            "duration": final_state.elapsed_seconds,
            "actions": action_count,
            "score": final_score,
        }

    async def play_multiple(self, count: int = 1) -> list:
        """여러 세션 연속 플레이."""
        results = []
        for i in range(count):
            print(f"\n{'='*50}")
            print(f"Session {i+1}/{count}")
            print(f"{'='*50}")
            result = await self.play_session()
            results.append(result)
            if i < count - 1:
                # Brief pause between sessions
                await asyncio.sleep(2.0)
        return results

    def _build_intelligent_layers(self, profile_path: Path, cache_dir: Path):
        """Build Layer 1-3 components from a GameProfile YAML.

        Returns (state_reader, plan_adapter) or (None, None) on failure.
        """
        try:
            from .genre import GameProfile, get_schema_for_genre
            from .perception import GaugeReader, GaugeProfile, OCRReader, RegionRegistry, StateReader
            from .reasoning import build_reasoner_for_genre
            from .adaptive import FailureMemory, LoopDetector, SpatialMemory, PlanAdapter

            profile = GameProfile.load(profile_path)
            genre = profile.genre
            print(f"  [VirtualPlayer] Profile loaded: {profile.game_name} ({genre})")

            # Layer 1: State Perception
            gauge_reader = GaugeReader()
            # Apply gauge overrides from profile
            if profile.gauge_overrides:
                for name, cfg in profile.gauge_overrides.items():
                    if "hsv_lower" in cfg and "hsv_upper" in cfg:
                        gauge_reader.add_profile(GaugeProfile(
                            name=name,
                            hsv_lower=tuple(cfg["hsv_lower"]),
                            hsv_upper=tuple(cfg["hsv_upper"]),
                            color_rgb=tuple(cfg.get("color_rgb", (0, 0, 0))),
                        ))

            ocr_reader = OCRReader()
            registry = RegionRegistry()

            # Apply screen ROIs from profile
            # Profile format: {screen: {name: {type, region, ...}}}
            # Registry format: {screen: {gauge_regions: {...}, ocr_regions: {...}}}
            if profile.screen_rois:
                converted = {}
                for screen_type, entries in profile.screen_rois.items():
                    gauge_regions = {}
                    ocr_regions = {}
                    for name, cfg in entries.items():
                        roi_type = cfg.get("type", "ocr")
                        if roi_type == "gauge":
                            gauge_name = cfg.get("gauge_name", name)
                            gauge_regions[gauge_name] = {
                                "region": cfg.get("region", [0, 0, 0, 0]),
                                "profile": cfg.get("profile", gauge_name),
                            }
                        else:
                            ocr_regions[name] = {
                                "region": cfg.get("region", [0, 0, 0, 0]),
                                "numeric": cfg.get("numeric", False),
                                "category": cfg.get("category", "resources"),
                            }
                    converted[screen_type] = {
                        "gauge_regions": gauge_regions,
                        "ocr_regions": ocr_regions,
                    }
                registry.load_from_dict(converted)

            # Apply genre defaults for screens not in profile
            schema = get_schema_for_genre(genre)
            if schema:
                genre_rois = schema.get_default_screen_rois()
                registry.set_genre_defaults(genre_rois)

            state_reader = StateReader(gauge_reader, ocr_reader, registry)

            # Layer 2: Goal Reasoning
            reasoner = build_reasoner_for_genre(genre)

            # Layer 3: Adaptive Planning
            failure_memory = FailureMemory(cache_dir / "failure_memory.json")
            loop_detector = LoopDetector()
            spatial_memory = SpatialMemory(cache_dir / "spatial_memory.json")
            plan_adapter = PlanAdapter(reasoner, failure_memory, loop_detector, spatial_memory)

            print(f"  [VirtualPlayer] Intelligent layers loaded (genre={genre})")
            return state_reader, plan_adapter

        except Exception as e:
            print(f"  [VirtualPlayer] Failed to load intelligent layers: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    def close(self) -> None:
        """리소스 정리."""
        # Save VisionBrain caches in ADB mode
        if self.adb_mode and hasattr(self.brain, 'save_all_caches'):
            self.brain.save_all_caches()
        self.storage.close()
