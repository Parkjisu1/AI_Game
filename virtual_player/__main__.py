"""
VirtualPlayer CLI
==================
play/play-adb/record/build-graph/analyze/export 서브커맨드.

Usage:
    # Web mode (기존)
    python -m virtual_player play --game 2048-web --persona casual --session evening --count 1

    # ADB mode (Android 게임)
    python -m virtual_player play-adb --package com.example.game --game my-game --screens screens.json --count 3

    # Record manual gameplay (getevent + screenshots)
    python -m virtual_player record --game ash_n_veil

    # Build nav_graph from recording
    python -m virtual_player build-graph --game ash_n_veil --screens data/games/ash_n_veil/screen_types.json

    python -m virtual_player analyze --game 2048-web
    python -m virtual_player export --game 2048-web --format yaml --output ./data/reports/2048_stage2.yaml
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from .config import DEFAULT_GAME, DEFAULT_PERSONA, DEFAULT_SESSION_PATTERN, DEFAULT_SESSION_COUNT


# ============================================================
# Register game modules
# ============================================================

def _register_games() -> None:
    """게임별 Brain/Adapter 등록."""
    from .brain import register_brain
    from .brain.brain_2048 import Brain2048
    from .adapters import register_adapter
    from .adapters.web_2048 import Web2048Adapter

    register_brain("2048-web", Brain2048)
    register_adapter("2048-web", Web2048Adapter)


# ============================================================
# Subcommands
# ============================================================

def cmd_play(args: argparse.Namespace) -> None:
    """게임 플레이 실행 (Web mode)."""
    _register_games()

    from .player import VirtualPlayer

    player = VirtualPlayer(
        game_id=args.game,
        persona_name=args.persona,
        session_pattern=args.session,
    )

    try:
        results = asyncio.run(player.play_multiple(count=args.count))
        print(f"\n{'='*50}")
        print(f"All {len(results)} session(s) complete.")
        total_actions = sum(r["actions"] for r in results)
        avg_score = sum(r["score"] for r in results) / len(results) if results else 0
        print(f"Total actions: {total_actions}")
        print(f"Average score: {avg_score:.0f}")
    finally:
        player.close()


def cmd_play_adb(args: argparse.Namespace) -> None:
    """Android 게임 플레이 (ADB mode)."""
    from .player import VirtualPlayer

    # Load screen types from JSON file
    screens_path = Path(args.screens)
    if not screens_path.exists():
        print(f"Error: Screen types file not found: {screens_path}", file=sys.stderr)
        print(f"Create a JSON file with format: {{\"lobby\": \"Main game lobby\", ...}}")
        sys.exit(1)

    screen_types = json.loads(screens_path.read_text(encoding="utf-8"))

    # Optional: load screen equivalences
    screen_equivs = None
    if args.equivalences:
        eq_path = Path(args.equivalences)
        if eq_path.exists():
            screen_equivs = json.loads(eq_path.read_text(encoding="utf-8"))

    # Optional: nav graph path
    nav_graph_path = Path(args.nav_graph) if args.nav_graph else None

    # Configure ADB settings
    if args.adb_path:
        from .adb import adb_cfg
        adb_cfg.adb_path = args.adb_path
    if args.device:
        from .adb import adb_cfg
        adb_cfg.device = args.device

    # Optional: game profile for intelligent layers
    profile_path = Path(args.profile) if args.profile else None

    player = VirtualPlayer(
        game_id=args.game,
        persona_name=args.persona,
        session_pattern=args.session,
        adb_mode=True,
        package_name=args.package,
        screen_types=screen_types,
        nav_graph_path=nav_graph_path,
        screen_equivalences=screen_equivs,
        profile_path=profile_path,
    )

    try:
        results = asyncio.run(player.play_multiple(count=args.count))
        print(f"\n{'='*50}")
        print(f"All {len(results)} session(s) complete.")
        total_actions = sum(r["actions"] for r in results)
        print(f"Total actions: {total_actions}")

        # Print decision stats
        if hasattr(player.brain, 'get_decision_stats'):
            stats = player.brain.get_decision_stats()
            print(f"\nDecision stats:")
            for k, v in stats.items():
                if isinstance(v, dict):
                    print(f"  {k}: {v}")
                else:
                    print(f"  {k}: {v}")
    finally:
        player.close()


def cmd_teach(args: argparse.Namespace) -> None:
    """Validate and install game curriculum."""
    from .bt.curriculum import Curriculum
    from .config import DATA_DIR

    curriculum_path = Path(args.curriculum)
    if not curriculum_path.exists():
        print(f"Error: Curriculum file not found: {curriculum_path}", file=sys.stderr)
        sys.exit(1)

    curriculum = Curriculum.load(curriculum_path)

    # Validate
    issues = curriculum.validate()
    score = curriculum.get_completeness_score()
    print(f"Curriculum: {curriculum.game_id}")
    print(f"Genre: {curriculum.genre}")
    print(f"Screens: {len(curriculum.screens)}")
    print(f"Core loop: {' -> '.join(curriculum.core_loop)}")
    print(f"Completeness: {score:.0%}")

    if issues:
        print(f"\nIssues ({len(issues)}):")
        for issue in issues:
            print(f"  - {issue}")

    if args.validate_only:
        if not issues:
            print("\nValidation PASSED")
        else:
            print(f"\nValidation FAILED ({len(issues)} issues)")
            sys.exit(1)
        return

    if issues:
        print(f"\nWarning: {len(issues)} issues found. Saving anyway...")

    # Save all configs
    game_dir = DATA_DIR / "games" / args.game
    saved = curriculum.save_all(game_dir)
    print(f"\nSaved to {game_dir}:")
    for name, path in saved.items():
        print(f"  {name}: {path}")

    print(f"\nNow run:")
    print(f"  python -m virtual_player play-v2 "
          f"--package {curriculum.package} --game {args.game} --duration 300")


def cmd_play_v2(args: argparse.Namespace) -> None:
    """Play with BT + State Machine architecture (v2 engine)."""
    from .config import ADB_PATH, ADB_DEVICE, DATA_DIR
    from .persona.archetypes import get_persona
    import subprocess

    adb_path = args.adb_path or ADB_PATH
    device = args.device or ADB_DEVICE
    game_dir = DATA_DIR / "games" / args.game
    temp_dir = game_dir / "temp" / "play_v2"
    temp_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = game_dir / "bt_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    persona = get_persona(args.persona)
    print(f"[play-v2] Persona: {persona.name} "
          f"(risk={persona.skill.risk_tolerance}, "
          f"explore={persona.skill.explore_rate}, "
          f"spend={persona.skill.spend_threshold})")

    # Screenshot function
    _ss_count = [0]
    def screenshot_fn(label=""):
        _ss_count[0] += 1
        local = temp_dir / f"v2_{_ss_count[0]:04d}_{label}.png"
        try:
            cmd = [adb_path, "-s", device, "exec-out", "screencap", "-p"]
            r = subprocess.run(cmd, capture_output=True, timeout=10)
            if r.returncode == 0 and len(r.stdout) > 100:
                local.write_bytes(r.stdout)
                return local
        except Exception:
            pass
        return None

    # ADB function
    def adb_fn(command_str):
        cmd = [adb_path, "-s", device] + command_str.split()
        return subprocess.run(cmd, capture_output=True, timeout=15, text=True)

    # Tap function
    input_method = args.input_method or "input_tap"
    def tap_fn(x, y, wait=1.0):
        import time as _t
        if input_method == "monkey":
            subprocess.run(
                [adb_path, "-s", device, "shell",
                 f"monkey -p {args.package} --pct-touch 100 -v 1 --throttle 100 1"],
                capture_output=True, timeout=10)
        else:
            subprocess.run(
                [adb_path, "-s", device, "shell", "input", "tap", str(x), str(y)],
                capture_output=True, timeout=5)
        _t.sleep(wait)

    # Back key
    def back_fn():
        subprocess.run(
            [adb_path, "-s", device, "shell", "input", "keyevent", "4"],
            capture_output=True, timeout=5)

    # Swipe function
    def swipe_fn(x1, y1, x2, y2, wait=1.5):
        import time as _t
        subprocess.run(
            [adb_path, "-s", device, "shell", "input", "swipe",
             str(x1), str(y1), str(x2), str(y2), "300"],
            capture_output=True, timeout=10)
        _t.sleep(wait)

    # Screen classifier
    detect_screen_fn = lambda path: "unknown"
    try:
        from .navigation.classifier import ScreenClassifier
        from .brain.reference_db import ReferenceDB

        ref_db_dir = game_dir / "reference_db"
        if ref_db_dir.exists():
            ref_db = ReferenceDB.load(ref_db_dir)
            screen_types_file = game_dir / "screen_types.json"
            if screen_types_file.exists():
                st = json.loads(screen_types_file.read_text(encoding="utf-8"))
            else:
                st = {s: s for s in ref_db.get_screen_types()}
            classifier = ScreenClassifier(
                genre_screen_types=st,
                cache_dir=temp_dir / "classifier_cache",
                reference_db=ref_db,
            )
            detect_screen_fn = lambda path: classifier.classify(path).screen_type
            print(f"[play-v2] Classifier loaded ({len(ref_db.get_all_entries())} refs)")
    except Exception as e:
        print(f"[play-v2] No classifier: {e}")

    # OCR reader
    read_text_fn = lambda path: []
    try:
        from .perception.ocr_reader import OCRReader
        import cv2
        ocr = OCRReader()
        def _read(path):
            img = cv2.imread(str(path))
            return ocr.read_full_screen(img) if img is not None else []
        read_text_fn = _read
        print(f"[play-v2] OCR loaded")
    except Exception as e:
        print(f"[play-v2] No OCR: {e}")

    # Nav graph
    nav_graph = None
    try:
        from .navigation.nav_graph import NavigationGraph
        ng_path = game_dir / "nav_graph.json"
        if ng_path.exists():
            nav_graph = NavigationGraph.load(ng_path)
            print(f"[play-v2] Nav graph loaded ({len(nav_graph.nodes)} nodes)")
    except Exception as e:
        print(f"[play-v2] No nav graph: {e}")

    # State reader
    state_reader = None
    try:
        profile_path = game_dir / "profile.yaml"
        if profile_path.exists():
            from .genre.game_profile import GameProfile
            from .perception.state_reader import StateReader
            profile = GameProfile.load(profile_path)
            state_reader = StateReader(profile)
            print(f"[play-v2] State reader loaded (genre={profile.genre})")
    except Exception as e:
        print(f"[play-v2] No state reader: {e}")

    # Relaunch function
    def relaunch_fn():
        subprocess.run(
            [adb_path, "-s", device, "shell", "am", "force-stop", args.package],
            capture_output=True, timeout=5)
        import time as _t
        _t.sleep(2)
        subprocess.run(
            [adb_path, "-s", device, "shell", "monkey", "-p", args.package,
             "-c", "android.intent.category.LAUNCHER", "1"],
            capture_output=True, timeout=5)
        _t.sleep(5)
        return True

    # Genre from profile or args
    genre = args.genre or "rpg"
    try:
        profile_path = game_dir / "profile.yaml"
        if profile_path.exists():
            from .genre.game_profile import GameProfile
            profile = GameProfile.load(profile_path)
            genre = profile.genre
    except Exception:
        pass

    # Auto-bootstrap mode: zero human input needed
    if args.auto_bootstrap:
        from .bt.auto_bootstrap import create_bootstrapped_engine
        engine = create_bootstrapped_engine(
            game_id=args.game,
            package_name=args.package,
            screenshot_fn=screenshot_fn,
            tap_fn=tap_fn,
            back_fn=back_fn,
            swipe_fn=swipe_fn,
            persona=persona,
            play_duration=args.duration,
            relaunch_fn=relaunch_fn,
            adb_fn=adb_fn,
        )
        result = engine.run()
        print(f"\n{'='*50}")
        print(f"PlayEngineV2 (Auto-Bootstrap) Results")
        print(f"{'='*50}")
        print(f"Ticks: {result['tick_count']}")
        print(f"Duration: {result['duration']:.0f}s")
        print(f"Actions: {len(result['actions_executed'])}")
        print(f"Outcome: {result['outcome_stats']}")
        return

    # Build and run PlayEngineV2
    from .play_engine_v2 import PlayEngineV2

    engine = PlayEngineV2(
        genre=genre,
        screenshot_fn=screenshot_fn,
        tap_fn=tap_fn,
        detect_screen_fn=detect_screen_fn,
        read_text_fn=read_text_fn,
        play_duration=args.duration,
        persona=persona,
        nav_graph=nav_graph,
        state_reader=state_reader,
        back_fn=back_fn,
        swipe_fn=swipe_fn,
        relaunch_fn=relaunch_fn,
        temp_dir=temp_dir,
        cache_dir=cache_dir,
        input_method=input_method,
        game_package=args.package,
        adb_fn=adb_fn,
    )

    result = engine.run()

    print(f"\n{'='*50}")
    print(f"PlayEngineV2 Results")
    print(f"{'='*50}")
    print(f"Ticks: {result['tick_count']}")
    print(f"Duration: {result['duration']:.0f}s")
    print(f"Actions: {len(result['actions_executed'])}")
    print(f"Outcome: {result['outcome_stats']}")


def cmd_record(args: argparse.Namespace) -> None:
    """Record manual gameplay (touch events + screenshots)."""
    from .recorder import record

    # Configure ADB settings
    if args.adb_path:
        from .adb import adb_cfg
        adb_cfg.adb_path = args.adb_path
    if args.device:
        from .adb import adb_cfg
        adb_cfg.device = args.device

    record(args.game, transition_wait=args.wait)


def cmd_build_graph(args: argparse.Namespace) -> None:
    """Build nav_graph.json from recorded gameplay."""
    from .recorder import build_graph

    # Configure ADB settings (needed for classifier's Claude Vision calls)
    if args.adb_path:
        from .adb import adb_cfg
        adb_cfg.adb_path = args.adb_path
    if args.device:
        from .adb import adb_cfg
        adb_cfg.device = args.device

    # Load screen types
    screens_path = Path(args.screens)
    if not screens_path.exists():
        print(f"Error: Screen types file not found: {screens_path}", file=sys.stderr)
        print(f"Create a JSON file: {{\"lobby\": \"Main game lobby\", ...}}")
        sys.exit(1)

    screen_types = json.loads(screens_path.read_text(encoding="utf-8"))
    result = build_graph(args.game, screen_types)

    if result:
        print(f"\nNav graph built successfully: {result}")
    else:
        print("\nFailed to build nav graph.", file=sys.stderr)
        sys.exit(1)


def cmd_analyze(args: argparse.Namespace) -> None:
    """통계 분석 출력."""
    from .history import HistoryStorage, SessionAnalytics

    with HistoryStorage() as storage:
        analytics = SessionAnalytics(storage)
        report = analytics.print_summary(game_id=args.game or None)
        print(report)

        if args.save:
            path = analytics.save_report(game_id=args.game or None)
            print(f"\nReport saved to: {path}")


def cmd_setup(args: argparse.Namespace) -> None:
    """Setup a new game profile with genre defaults."""
    from .genre import SetupWizard, get_schema_for_genre
    from .config import DATA_DIR

    games_dir = DATA_DIR / "games"

    # Auto-detect genre from screen types if not specified
    genre = args.genre
    if not genre and args.screens:
        screens_path = Path(args.screens)
        if screens_path.exists():
            screen_types = json.loads(screens_path.read_text(encoding="utf-8"))
            wizard = SetupWizard(games_dir)
            genre = wizard.auto_detect_genre(screen_types)
            print(f"Auto-detected genre: {genre}")

    if not genre:
        genre = "rpg"
        print(f"Using default genre: {genre}")

    wizard = SetupWizard(games_dir)
    profile = wizard.setup(args.game, args.package, genre)

    print(f"\nGame profile created:")
    print(f"  Game: {profile.game_name} ({profile.game_id})")
    print(f"  Genre: {profile.genre}")
    print(f"  Profile: {games_dir / args.game / 'profile.yaml'}")
    print(f"\nUse with: play-adb --profile {games_dir / args.game / 'profile.yaml'} ...")


def cmd_test(args: argparse.Namespace) -> None:
    """Run AI Tester: zero-knowledge bootstrap + play + extract + journal."""
    from .test_orchestrator import TestOrchestrator

    # Configure ADB settings
    adb_path = args.adb_path or ""
    device = args.device or ""

    if adb_path:
        from .config import ADB_PATH
    else:
        from .config import ADB_PATH
        adb_path = ADB_PATH

    if device:
        pass
    else:
        from .config import ADB_DEVICE
        device = ADB_DEVICE

    orchestrator = TestOrchestrator(
        package_name=args.package,
        adb_path=adb_path,
        device=device,
        play_duration=args.duration,
        explore_taps=args.explore_taps,
        dry_run=args.dry_run,
    )

    result = orchestrator.run()

    print(f"\n{'='*60}")
    print(f"AI Tester Results: {args.package}")
    print(f"{'='*60}")
    print(f"Genre: {result['genre']}")
    print(f"Duration: {result['duration_seconds']:.0f}s")
    print(f"Screens discovered: {result['screens_discovered']}")
    print(f"Parameters extracted: {result['parameters_extracted']}")

    if result['files_written']:
        print(f"\nDesign DB files:")
        for f in result['files_written']:
            print(f"  {f}")

    if result['errors']:
        print(f"\nErrors ({len(result['errors'])}):")
        for e in result['errors']:
            print(f"  - {e}")


def cmd_test_search(args: argparse.Namespace) -> None:
    """Search past AI Tester sessions."""
    from .journal.search import JournalSearch
    from .config import JOURNAL_DIR

    search = JournalSearch(journal_dir=JOURNAL_DIR)

    if args.list_games:
        games = search.list_games()
        if games:
            print("Known games:")
            for g in games:
                print(f"  {g}")
        else:
            print("No journal entries found.")
        return

    results = search.search(
        query=args.query or "",
        package_name=args.package or None,
        genre=args.genre or None,
        limit=args.limit,
    )

    if not results:
        print("No matching sessions found.")
        return

    print(f"Found {len(results)} session(s):\n")
    for r in results:
        print(f"  [{r['timestamp'][:10]}] {r['session_id']}")
        print(f"    Package: {r['package_name']} | Genre: {r['genre']}")
        if r['tags']:
            print(f"    Tags: {', '.join(r['tags'])}")
        print()


def cmd_learn(args: argparse.Namespace) -> None:
    """Record user demonstration and learn behavior patterns."""
    from .config import ADB_PATH, ADB_DEVICE, DATA_DIR
    from .learning import PatternRecorder, PatternDB
    from pathlib import Path

    adb_path = args.adb_path or ADB_PATH
    device = args.device or ADB_DEVICE

    # Pattern DB path
    game_dir = DATA_DIR / "games" / args.game
    game_dir.mkdir(parents=True, exist_ok=True)
    db_path = game_dir / "pattern_db.json"
    pattern_db = PatternDB(db_path)

    print(f"[Learn] Pattern DB: {db_path} ({pattern_db.count} existing patterns)")
    print(f"[Learn] Category: {args.category}")
    print(f"[Learn] Pattern name: {args.name}")
    print(f"")

    # Build detect_screen_fn from reference DB if available
    detect_screen_fn = None
    try:
        from .navigation.classifier import ScreenClassifier
        from .brain.reference_db import ReferenceDB

        ref_db_dir = game_dir / "reference_db"
        if ref_db_dir.exists():
            ref_db = ReferenceDB.load(ref_db_dir)
            screen_types = {st: st for st in ref_db.get_screen_types()}
            cache_dir = game_dir / "temp" / "learn" / "classifier_cache"
            classifier = ScreenClassifier(
                genre_screen_types=screen_types,
                cache_dir=cache_dir,
                reference_db=ref_db,
            )
            detect_screen_fn = lambda path: classifier.classify(path).screen_type
            print(f"[Learn] Screen classifier loaded ({len(ref_db.get_all_entries())} references)")
    except Exception as e:
        print(f"[Learn] No screen classifier: {e}")

    # Build read_text_fn from OCR reader if available
    read_text_fn = None
    try:
        from .perception.ocr_reader import OCRReader
        import cv2
        ocr = OCRReader()

        def _read_text_from_path(path):
            img = cv2.imread(str(path))
            if img is None:
                return []
            return ocr.read_full_screen(img)

        read_text_fn = _read_text_from_path
        print(f"[Learn] OCR reader loaded")
    except Exception as e:
        print(f"[Learn] No OCR reader: {e}")

    # Build nav_graph if available
    nav_graph = None
    try:
        from .navigation.nav_graph import NavigationGraph
        nav_graph_path = game_dir / "nav_graph.json"
        if nav_graph_path.exists():
            nav_graph = NavigationGraph.load(nav_graph_path)
            print(f"[Learn] Nav graph loaded ({len(nav_graph.nodes)} nodes)")
    except Exception as e:
        print(f"[Learn] No nav graph: {e}")

    # Build screenshot function
    import subprocess
    temp_dir = game_dir / "temp" / "learn"
    temp_dir.mkdir(parents=True, exist_ok=True)
    _ss_count = [0]

    def screenshot_fn(label=""):
        _ss_count[0] += 1
        local = temp_dir / f"learn_{_ss_count[0]:04d}_{label}.png"
        try:
            cmd = [adb_path]
            if device:
                cmd.extend(["-s", device])
            cmd.extend(["exec-out", "screencap", "-p"])
            r = subprocess.run(cmd, capture_output=True, timeout=10)
            if r.returncode == 0 and len(r.stdout) > 100:
                local.write_bytes(r.stdout)
                return local
        except Exception:
            pass
        return None

    recorder = PatternRecorder(
        screenshot_fn=screenshot_fn,
        detect_screen_fn=detect_screen_fn or (lambda path: "unknown"),
        read_text_fn=read_text_fn or (lambda path: []),
        pattern_db=pattern_db,
        nav_graph=nav_graph,
        adb_path=adb_path,
        device=device,
    )

    print(f"\n{'='*50}")
    print(f"RECORDING: '{args.name}' (category: {args.category})")
    print(f"Play the game normally. Press Ctrl+C to stop recording.")
    print(f"{'='*50}\n")

    try:
        recorder.start_recording(args.name, args.category)
        recorder.record_loop()  # Blocks until Ctrl+C
    except KeyboardInterrupt:
        pass
    finally:
        print(f"\n[Learn] Stopping recording...")
        pattern = recorder.stop_recording()
        if pattern:
            print(f"\n{'='*50}")
            print(f"Pattern saved: '{pattern.name}'")
            print(f"  Category: {pattern.category}")
            print(f"  Steps: {len(pattern.steps)}")
            print(f"  DB total: {pattern_db.count} patterns")
            print(f"{'='*50}")
        else:
            print(f"[Learn] No pattern recorded (no steps captured)")


def cmd_export(args: argparse.Namespace) -> None:
    """Stage 2 YAML 내보내기."""
    from .history import HistoryStorage
    from .export import YamlExporter

    output_path = Path(args.output) if args.output else None

    with HistoryStorage() as storage:
        exporter = YamlExporter(storage)
        try:
            path = exporter.export(
                game_id=args.game,
                output_path=output_path,
            )
            print(f"Exported to: {path}")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


# ============================================================
# Argument parser
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    """CLI 인자 파서 생성."""
    parser = argparse.ArgumentParser(
        prog="virtual_player",
        description="VirtualPlayer - AI Game Player Framework",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # play (web mode)
    play_parser = subparsers.add_parser("play", help="Play a web game")
    play_parser.add_argument("--game", default=DEFAULT_GAME, help="Game ID (default: 2048-web)")
    play_parser.add_argument("--persona", default=DEFAULT_PERSONA, help="Persona name (default: casual)")
    play_parser.add_argument("--session", default=DEFAULT_SESSION_PATTERN, help="Session pattern (default: evening)")
    play_parser.add_argument("--count", type=int, default=DEFAULT_SESSION_COUNT, help="Number of sessions (default: 1)")

    # play-adb (Android mode)
    adb_parser = subparsers.add_parser("play-adb", help="Play an Android game via ADB")
    adb_parser.add_argument("--package", required=True, help="Android package name (e.g. com.example.game)")
    adb_parser.add_argument("--game", required=True, help="Game ID for caching/history")
    adb_parser.add_argument("--screens", required=True, help="Path to screen_types JSON file")
    adb_parser.add_argument("--nav-graph", default="", help="Path to nav_graph.json (optional)")
    adb_parser.add_argument("--equivalences", default="", help="Path to screen equivalences JSON (optional)")
    adb_parser.add_argument("--persona", default=DEFAULT_PERSONA, help="Persona name (default: casual)")
    adb_parser.add_argument("--session", default=DEFAULT_SESSION_PATTERN, help="Session pattern (default: evening)")
    adb_parser.add_argument("--count", type=int, default=1, help="Number of sessions (default: 1)")
    adb_parser.add_argument("--profile", default="", help="Path to game profile YAML (enables intelligent layers)")
    adb_parser.add_argument("--adb-path", default="", help="ADB executable path (optional)")
    adb_parser.add_argument("--device", default="", help="ADB device ID (optional)")

    # teach (create curriculum for a game)
    teach_parser = subparsers.add_parser("teach", help="Create game curriculum (what AI needs to know)")
    teach_parser.add_argument("--game", required=True, help="Game ID")
    teach_parser.add_argument("--curriculum", required=True, help="Path to curriculum YAML file")
    teach_parser.add_argument("--validate-only", action="store_true", help="Only validate, don't save")

    # play-v2 (BT + State Machine)
    v2_parser = subparsers.add_parser("play-v2", help="Play with BT + State Machine engine (v2)")
    v2_parser.add_argument("--package", required=True, help="Android package name")
    v2_parser.add_argument("--game", required=True, help="Game ID for caching/history")
    v2_parser.add_argument("--persona", default="casual", help="Persona (casual/hardcore/whale/newbie/returning)")
    v2_parser.add_argument("--duration", type=int, default=300, help="Play duration in seconds")
    v2_parser.add_argument("--genre", default="", help="Genre override (auto-detected from profile if available)")
    v2_parser.add_argument("--input-method", default="input_tap", help="ADB input method (input_tap/monkey)")
    v2_parser.add_argument("--adb-path", default="", help="ADB executable path")
    v2_parser.add_argument("--device", default="", help="ADB device ID")
    v2_parser.add_argument("--auto-bootstrap", action="store_true",
                           help="Auto-discover screens/nav on first run (no manual setup needed)")

    # record (manual gameplay recording)
    rec_parser = subparsers.add_parser("record", help="Record manual gameplay (touch + screenshots)")
    rec_parser.add_argument("--game", required=True, help="Game ID (e.g. ash_n_veil)")
    rec_parser.add_argument("--wait", type=float, default=0.8, help="Transition wait after touch UP in seconds (default: 0.8)")
    rec_parser.add_argument("--adb-path", default="", help="ADB executable path (optional)")
    rec_parser.add_argument("--device", default="", help="ADB device ID (optional)")

    # build-graph (build nav_graph from recording)
    bg_parser = subparsers.add_parser("build-graph", help="Build nav_graph.json from recorded gameplay")
    bg_parser.add_argument("--game", required=True, help="Game ID (must match record --game)")
    bg_parser.add_argument("--screens", required=True, help="Path to screen_types JSON file")
    bg_parser.add_argument("--adb-path", default="", help="ADB executable path (optional)")
    bg_parser.add_argument("--device", default="", help="ADB device ID (optional)")

    # setup (new game profile)
    setup_parser = subparsers.add_parser("setup", help="Setup a new game profile with genre defaults")
    setup_parser.add_argument("--game", required=True, help="Game ID (e.g. ash_n_veil)")
    setup_parser.add_argument("--package", required=True, help="Android package name")
    setup_parser.add_argument("--genre", default="", help="Genre (rpg/idle/merge/slg) -- auto-detected if omitted")
    setup_parser.add_argument("--screens", default="", help="Path to screen_types JSON for genre auto-detection")

    # analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze play history")
    analyze_parser.add_argument("--game", default="", help="Game ID filter (empty for all)")
    analyze_parser.add_argument("--save", action="store_true", help="Save report to file")

    # export
    export_parser = subparsers.add_parser("export", help="Export data for Stage 2")
    export_parser.add_argument("--game", required=True, help="Game ID")
    export_parser.add_argument("--format", default="yaml", choices=["yaml"], help="Export format")
    export_parser.add_argument("--output", default="", help="Output file path")

    # test (AI Tester)
    test_parser = subparsers.add_parser("test", help="Run AI Tester on a mobile game")
    test_parser.add_argument("--package", required=True, help="Android package name (e.g. com.grandgames.carmatch)")
    test_parser.add_argument("--duration", type=int, default=300, help="Play duration in seconds (default: 300)")
    test_parser.add_argument("--explore-taps", type=int, default=40, help="Exploration taps per screen (default: 40)")
    test_parser.add_argument("--dry-run", action="store_true", help="Don't write to Design DB")
    test_parser.add_argument("--adb-path", default="", help="ADB executable path (optional)")
    test_parser.add_argument("--device", default="", help="ADB device ID (optional)")

    # learn (behavior pattern recording)
    learn_parser = subparsers.add_parser("learn", help="Record user demonstration to learn behavior patterns")
    learn_parser.add_argument("--game", required=True, help="Game ID (e.g. ash_n_veil)")
    learn_parser.add_argument("--name", required=True, help="Pattern name (e.g. complete_quest_1)")
    learn_parser.add_argument("--category", default="quest", choices=["quest", "popup", "upgrade", "shop", "navigation"],
                              help="Pattern category (default: quest)")
    learn_parser.add_argument("--description", default="", help="Human-readable description of the pattern")
    learn_parser.add_argument("--adb-path", default="", help="ADB executable path (optional)")
    learn_parser.add_argument("--device", default="", help="ADB device ID (optional)")

    # test-search (Search journal)
    search_parser = subparsers.add_parser("test-search", help="Search past AI Tester sessions")
    search_parser.add_argument("--query", default="", help="Full-text search query")
    search_parser.add_argument("--package", default="", help="Filter by package name")
    search_parser.add_argument("--genre", default="", help="Filter by genre")
    search_parser.add_argument("--limit", type=int, default=20, help="Max results (default: 20)")
    search_parser.add_argument("--list-games", action="store_true", help="List all known games")

    return parser


# ============================================================
# Main
# ============================================================

def main() -> None:
    """CLI 진입점."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "play": cmd_play,
        "play-adb": cmd_play_adb,
        "play-v2": cmd_play_v2,
        "teach": cmd_teach,
        "record": cmd_record,
        "build-graph": cmd_build_graph,
        "setup": cmd_setup,
        "analyze": cmd_analyze,
        "export": cmd_export,
        "test": cmd_test,
        "test-search": cmd_test_search,
        "learn": cmd_learn,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
