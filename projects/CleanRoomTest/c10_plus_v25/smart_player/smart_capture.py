"""
Smart Capture Orchestrator
============================
Runs 10 AI missions sequentially using SmartNavigator.
Each mission: fresh game launch -> popup dismiss -> navigate -> capture screenshots.
"""

import time
from pathlib import Path
from typing import Optional

from core import (
    SYS_CFG, log, force_stop, launch_game, take_screenshot,
)
from genres import GenreBase, GameConfig, MissionPlan
from smart_player.classifier import ScreenClassifier
from smart_player.nav_graph import NavigationGraph
from smart_player.popup_handler import PopupHandler
from smart_player.navigator import SmartNavigator
from smart_player.mission_router import MissionRouter


def build_nav_graph(game_key: str, genre: GenreBase) -> Optional[Path]:
    """Build navigation graph from recording.json + frames.

    Process:
    1. Load recording.json + frames/
    2. Classify all frames
    3. Build graph from frame transitions
    4. Save to recordings/{game_key}/nav_graph.json

    Returns path to saved graph, or None on failure.
    """
    rec_dir = SYS_CFG.base_dir / "recordings" / game_key
    rec_file = rec_dir / "recording.json"
    frames_dir = rec_dir / "frames"

    if not rec_file.exists():
        log(f"  [SmartCapture] No recording found: {rec_file}")
        log(f"  [SmartCapture] Record first: python run.py {game_key} record")
        return None

    if not frames_dir.exists() or not list(frames_dir.glob("*.png")):
        log(f"  [SmartCapture] No frames in {frames_dir}")
        return None

    log(f"  [SmartCapture] Building nav graph from recording...")

    # Classify all frames
    screen_types = genre.get_screen_types()
    cache_dir = rec_dir / "cache"
    classifier = ScreenClassifier(screen_types, cache_dir)

    frame_files = sorted(frames_dir.glob("frame_*.png"))
    log(f"  [SmartCapture] Classifying {len(frame_files)} frames...")

    classifications = {}
    for frame_path in frame_files:
        cls = classifier.classify(frame_path)
        classifications[frame_path.name] = cls.screen_type

    # Save classifications
    import json
    cls_file = rec_dir / "classifications.json"
    cls_file.write_text(
        json.dumps(classifications, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log(f"  [SmartCapture] Classifications saved: {cls_file}")

    # Build graph
    graph = NavigationGraph.build_from_recording(rec_file, classifications)

    # Save graph
    graph_path = rec_dir / "nav_graph.json"
    graph.save(graph_path)

    # Save classifier cache for future use
    classifier.save_cache()

    return graph_path


def _load_or_build_graph(game_key: str, genre: GenreBase,
                         graph_path: Optional[Path] = None) -> Optional[NavigationGraph]:
    """Load existing nav graph or build from recording."""
    # Try explicit path first
    if graph_path and graph_path.exists():
        return NavigationGraph.load(graph_path)

    # Try default location
    default_path = SYS_CFG.base_dir / "recordings" / game_key / "nav_graph.json"
    if default_path.exists():
        log(f"  [SmartCapture] Loading existing graph: {default_path}")
        return NavigationGraph.load(default_path)

    # Build from recording
    built_path = build_nav_graph(game_key, genre)
    if built_path:
        return NavigationGraph.load(built_path)

    return None


def smart_capture(game_key: str, genre: GenreBase, game: GameConfig,
                  sessions_dir: Path, graph_path: Path = None) -> bool:
    """Run 10 AI missions using smart navigation.

    Each mission:
    1. Force-stop + relaunch game
    2. Dismiss initial popups, reach lobby
    3. Navigate to target screens per mission plan
    4. Capture required screenshots
    5. Save to sessions_dir/session_01~10/

    Args:
        game_key: Game identifier
        genre: Genre module instance
        game: GameConfig for the game
        sessions_dir: Output directory for session screenshots
        graph_path: Optional explicit path to nav_graph.json

    Returns True if at least one mission completed successfully.
    """
    log("=" * 60)
    log(f"SMART CAPTURE — {game.name}")
    log("=" * 60)

    # 1. Load or build navigation graph
    graph = _load_or_build_graph(game_key, genre, graph_path)
    if not graph:
        log("  [SmartCapture] ERROR: No navigation graph available")
        log(f"  [SmartCapture] Record first: python run.py {game_key} record")
        return False

    log(f"  [SmartCapture] Graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    # 2. Initialize components
    screen_types = genre.get_screen_types()
    mission_plans = genre.get_mission_targets()

    if not mission_plans:
        log("  [SmartCapture] ERROR: No mission plans defined for this genre")
        return False

    cache_dir = SYS_CFG.base_dir / "recordings" / game_key / "cache"
    classifier = ScreenClassifier(screen_types, cache_dir)
    popup = PopupHandler(game.package, cache_dir)
    router = MissionRouter(graph, mission_plans)

    success_count = 0

    # 3. Execute missions 1~10
    for mission_id in sorted(mission_plans.keys()):
        plan = mission_plans[mission_id]
        session_dir = sessions_dir / f"session_{mission_id:02d}"

        # Skip if already has enough screenshots
        existing = list(session_dir.glob("*.png")) if session_dir.exists() else []
        if len(existing) >= 3:
            log(f"  Mission {mission_id:02d}: already {len(existing)} shots, skip")
            success_count += 1
            continue

        session_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = cache_dir / f"nav_temp_{mission_id:02d}"

        log(f"\n  Mission {mission_id:02d}: {plan.strategy} strategy")
        log(f"    Targets: {', '.join(plan.targets)}")

        # Ensure game is running (don't restart if already running)
        from core import adb_run
        r = adb_run("shell", "dumpsys", "window", timeout=5)
        game_running = game.package.encode() in (r.stdout or b"")
        if not game_running:
            launch_game(game.package, wait=8)
        # Don't press back — it triggers "quit game?" dialog in many games

        # Initialize navigator for this mission
        navigator = SmartNavigator(
            graph=graph,
            classifier=classifier,
            popup_handler=popup,
            session_dir=session_dir,
            temp_dir=temp_dir,
            screen_equivalences=genre.get_screen_equivalences(),
        )

        # Initial classification + popup dismissal
        cls = navigator.take_and_classify()
        log(f"    Initial screen: {cls.screen_type}")

        # Dismiss startup popups (up to 5 attempts)
        for _ in range(5):
            if popup.is_popup(cls):
                popup.dismiss(cls, navigator.state.last_screenshot)
                time.sleep(1.5)
                cls = navigator.take_and_classify()
            else:
                break

        # Start mission tracking
        progress = router.start_mission(mission_id)
        if not progress:
            continue

        # Plan visit order
        visit_order = router.plan_visit_order(mission_id, cls.screen_type)
        log(f"    Visit order: {' -> '.join(visit_order)}")

        # Navigate and capture
        shot_idx = 0
        while not router.is_mission_complete(mission_id):
            if navigator.state.step_count >= SmartNavigator.MAX_STEPS:
                log(f"    Step limit reached ({SmartNavigator.MAX_STEPS})")
                break

            # Get next target
            target = router.get_next_target(mission_id, navigator.state.current_screen)
            if not target:
                log(f"    All targets fulfilled")
                break

            # Navigate to target (navigate_to handles equivalences)
            if navigator.state.current_screen == target or navigator._is_equivalent(navigator.state.current_screen, target):
                # Already there (or equivalent) — just capture
                pass
            else:
                reached = navigator.navigate_to(target)
                if not reached:
                    progress.record_stuck()
                    log(f"    Could not reach {target}, stuck={progress.stuck_consecutive}")
                    continue

            # Capture screenshot at target
            shot_idx += 1
            shot_name = f"{shot_idx:02d}_{target}"
            navigator.capture_for_mission(target, shot_name)
            progress.record_capture(target)

            log(f"    [{shot_idx}] Captured {target} "
                f"({progress.captured.get(target, 0)}/{plan.required_screenshots.get(target, 1)})")

            # Check if we should move to next target
            required = plan.required_screenshots.get(target, 1)
            captured = progress.captured.get(target, 0)
            if captured >= required:
                # Move on by re-evaluating next target in next loop iteration
                pass

        # Mission complete
        shots = list(session_dir.glob("*.png"))
        log(f"    Mission {mission_id:02d} done: {len(shots)} screenshots, "
            f"{navigator.state.step_count} steps")
        log(f"    Progress: {router.get_progress_summary(mission_id)}")

        if shots:
            success_count += 1

    # Cleanup (don't force-stop — leave game running for user)
    classifier.save_cache()

    log(f"\n  Smart capture complete: {success_count}/{len(mission_plans)} missions")
    return success_count > 0
