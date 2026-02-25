#!/usr/bin/env python3
"""
C10+ v2.5 — Genre-Modular Game Analysis Pipeline
==================================================
Usage:
  python run.py <game_key> [options]
  python run.py <game_key> record         # Record user touch events
  python run.py <game_key> --replay       # Replay recording + full pipeline

Examples:
  python run.py ash_n_veil                # Full pipeline (capture + analysis)
  python run.py ash_n_veil record         # Record user gameplay
  python run.py ash_n_veil --replay       # Replay recording + analysis
  python run.py ash_n_veil --smart        # Smart AI navigation (requires recording)
  python run.py ash_n_veil --skip-capture # Skip ADB capture, analyze existing screenshots
  python run.py carmatch --no-wiki        # Disable wiki cross-reference
  python run.py --list                    # List all available games

Options:
  record            Record user touch events (Ctrl+C to stop)
  --smart           Use AI navigation for Phase 1 (requires recording first)
  --replay          Replay recorded events for Phase 1, then continue pipeline
  --replay-speed    Replay speed multiplier (default: 1.0)
  --skip-capture    Skip Phase 1 (ADB screenshot capture)
  --no-ocr          Disable M2 (OCR preprocessing)
  --no-wiki         Disable M3 (Community wiki cross-reference)
  --no-assets       Disable M4 (APK asset extraction)
  --apk <path>      Set APK file path for asset extraction
  --device <id>     ADB device ID (default: emulator-5554)
  --model <model>   Claude model (default: sonnet)
  --list            List all registered games and genres
"""

import sys
import argparse
from pathlib import Path

# Ensure package imports work
sys.path.insert(0, str(Path(__file__).parent))

from core import SYS_CFG, log
from genres import load_all_genres, find_game, _GENRE_REGISTRY
from pipeline import run_pipeline


def list_games():
    """Print all registered games and genres."""
    load_all_genres()
    log("Registered genres and games:\n")
    for genre in _GENRE_REGISTRY.values():
        games = genre.get_games()
        missions = genre.get_missions()
        flex_count = sum(1 for m in missions.values() if m.flex)
        log(f"  [{genre.genre_key}] {genre.genre_name} - {len(games)} game(s), "
            f"Core 4 + Flex {flex_count} testers")
        for key, game in games.items():
            log(f"    {key:20s}  {game.name:30s}  {game.package}")
        log("")

    log("Tester Role Comparison:")
    log(f"  {'#':>3} | {'Puzzle':25s} | {'Idle RPG':25s} | {'Merge':25s}")
    log(f"  {'-'*3}-+-{'-'*25}-+-{'-'*25}-+-{'-'*25}")
    for sid in range(1, 11):
        row = f"  {sid:3d} |"
        for gkey in ["puzzle", "idle_rpg", "merge"]:
            genre = _GENRE_REGISTRY.get(gkey)
            if genre:
                missions = genre.get_missions()
                m = missions.get(sid)
                name = m.name[:25] if m else "(none)"
                row += f" {name:25s} |"
            else:
                row += f" {'(not loaded)':25s} |"
        log(row)
    log("")


def main():
    parser = argparse.ArgumentParser(
        description="C10+ v2.5: Genre-Modular Game Analysis Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py ash_n_veil                 Full analysis of Ash N Veil
  python run.py ash_n_veil record          Record user gameplay
  python run.py ash_n_veil --smart          Smart AI navigation + analysis
  python run.py ash_n_veil --replay        Replay recording + analysis
  python run.py carmatch --skip-capture    Analyze existing screenshots
  python run.py --list                     Show all available games
        """,
    )
    parser.add_argument("game", nargs="?", help="Game key to analyze")
    parser.add_argument("action", nargs="?", choices=["record"],
                        help="Subcommand: 'record' to record user gameplay")
    parser.add_argument("--list", action="store_true", help="List all games and genres")
    parser.add_argument("--smart", action="store_true",
                        help="Use AI navigation for Phase 1 (requires recording first)")
    parser.add_argument("--replay", action="store_true",
                        help="Use recorded events for Phase 1 capture")
    parser.add_argument("--replay-speed", type=float, default=1.0,
                        help="Replay speed multiplier (default: 1.0)")
    parser.add_argument("--skip-capture", action="store_true", help="Skip ADB capture phase")
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR preprocessing")
    parser.add_argument("--no-wiki", action="store_true", help="Disable wiki cross-reference")
    parser.add_argument("--no-assets", action="store_true", help="Disable APK asset extraction")
    parser.add_argument("--apk", type=str, help="APK file path for asset extraction")
    parser.add_argument("--device", type=str, help="ADB device ID")
    parser.add_argument("--model", type=str, choices=["sonnet", "opus", "haiku"],
                        help="Claude model to use")

    args = parser.parse_args()

    if args.list:
        list_games()
        return

    if not args.game:
        parser.print_help()
        return

    # Apply configuration
    if args.device:
        SYS_CFG.device = args.device
    if args.model:
        SYS_CFG.claude_model = args.model
    if args.no_ocr:
        SYS_CFG.features["ocr"] = False
    if args.no_wiki:
        SYS_CFG.features["wiki"] = False
    if args.no_assets:
        SYS_CFG.features["assets"] = False

    # Set APK path if provided
    if args.apk:
        load_all_genres()
        result = find_game(args.game)
        if result:
            _, game = result
            game.apk_path = args.apk

    # Handle record subcommand
    if args.action == "record":
        from recorder import record
        record(args.game)
        return

    # Run pipeline
    run_pipeline(
        args.game,
        skip_capture=args.skip_capture,
        replay=args.replay,
        replay_speed=args.replay_speed,
        smart=args.smart,
    )


if __name__ == "__main__":
    main()
