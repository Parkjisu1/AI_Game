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
    setup_parser.add_argument("--genre", default="", help="Genre (rpg/idle/merge/slg) — auto-detected if omitted")
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
        "record": cmd_record,
        "build-graph": cmd_build_graph,
        "setup": cmd_setup,
        "analyze": cmd_analyze,
        "export": cmd_export,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
