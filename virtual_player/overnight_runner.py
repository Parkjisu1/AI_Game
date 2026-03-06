"""Overnight automated test runner for multiple games."""
import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class OvernightRunner:
    """Runs AI Tester on multiple games sequentially with logging and reporting."""

    def __init__(self, games: list, total_hours: float = 12.0,
                 report_dir: str = "E:/AI/virtual_player/data/reports"):
        """
        Args:
            games: List of game configs [{"game_id": "ash_n_veil", "duration_s": 3600}, ...]
            total_hours: Total run time in hours
            report_dir: Where to save reports
        """
        self._games = games
        self._total_hours = total_hours
        self._report_dir = Path(report_dir)
        self._report_dir.mkdir(parents=True, exist_ok=True)
        self._results = {}

    def run(self):
        """Main execution loop: rotate between games."""
        start_time = time.time()
        end_time = start_time + self._total_hours * 3600
        cycle = 0

        logger.info("=== Overnight Runner Started ===")
        logger.info("Games: %s", [g['game_id'] for g in self._games])
        logger.info("Total hours: %s", self._total_hours)
        logger.info("End time: %s", datetime.fromtimestamp(end_time).strftime('%Y-%m-%d %H:%M'))

        while time.time() < end_time:
            cycle += 1
            for game_cfg in self._games:
                if time.time() >= end_time:
                    break

                game_id = game_cfg["game_id"]
                duration = min(game_cfg.get("duration_s", 1800), end_time - time.time())
                if duration <= 0:
                    break

                logger.info("\n--- Cycle %d: %s (%.0fs) ---", cycle, game_id, duration)
                result = self._run_game(game_id, int(duration), game_cfg)

                # Accumulate results
                if game_id not in self._results:
                    self._results[game_id] = {
                        "total_time_s": 0,
                        "cycles": 0,
                        "battles": 0,
                        "errors": 0,
                        "unknown_screens": 0,
                        "quests_completed": 0,
                        "skills_used": 0,
                        "puzzle_moves": 0,
                        "puzzle_wins": 0,
                        "level_start": None,
                        "level_end": None,
                        "gold_start": None,
                        "gold_end": None,
                    }

                stats = self._results[game_id]
                stats["total_time_s"] += result.get("duration_s", 0)
                stats["cycles"] += 1
                stats["battles"] += result.get("battles", 0)
                stats["errors"] += result.get("errors", 0)
                stats["unknown_screens"] += result.get("unknown_screens", 0)
                stats["quests_completed"] += result.get("quests_completed", 0)
                stats["skills_used"] += result.get("skills_used", 0)
                stats["puzzle_moves"] += result.get("puzzle_moves", 0)
                stats["puzzle_wins"] += result.get("puzzle_wins", 0)

                # Track level/gold progression
                if stats["level_start"] is None:
                    stats["level_start"] = result.get("level_start")
                    stats["gold_start"] = result.get("gold_start")
                stats["level_end"] = result.get("level_end")
                stats["gold_end"] = result.get("gold_end")

                # Brief cooldown between games
                time.sleep(5)

        total_elapsed = time.time() - start_time
        logger.info("\n=== Overnight Runner Complete (%.1fh) ===", total_elapsed / 3600)

        # Generate report
        report = self._generate_report(total_elapsed)
        self._save_report(report)
        print(report)
        return self._results

    def _run_game(self, game_id: str, duration_s: int, game_cfg: dict) -> dict:
        """Run a single game session via TestOrchestrator.run_play_only()."""
        result = {
            "duration_s": 0,
            "battles": 0,
            "errors": 0,
            "unknown_screens": 0,
            "quests_completed": 0,
            "skills_used": 0,
            "puzzle_moves": 0,
            "puzzle_wins": 0,
        }

        try:
            # Import here to avoid circular imports at module level
            from virtual_player.test_orchestrator import TestOrchestrator

            orchestrator = TestOrchestrator(
                package_name=game_cfg.get("package_name", ""),
                play_duration=duration_s,
                game_id=game_id,
            )

            # Run play phase only (skips bootstrap if profile exists)
            play_result = orchestrator.run_play_only()

            if play_result:
                action_counts = play_result.get("action_counts", {})
                error_list = play_result.get("errors", [])
                result.update({
                    "duration_s": play_result.get("duration_s", duration_s),
                    "battles": action_counts.get("grind_battle", 0),
                    "errors": len(error_list) if isinstance(error_list, list) else int(error_list),
                    "unknown_screens": play_result.get("unknown_screen_count", 0),
                    "quests_completed": play_result.get("quests_completed", 0),
                    "skills_used": play_result.get("skills_used", 0),
                    "puzzle_moves": play_result.get("puzzle_moves", 0),
                    "puzzle_wins": play_result.get("puzzle_wins", 0),
                    "level_start": play_result.get("level_start"),
                    "level_end": play_result.get("level_end"),
                    "gold_start": play_result.get("gold_start"),
                    "gold_end": play_result.get("gold_end"),
                })

        except Exception as e:
            logger.error("Game %s error: %s", game_id, e, exc_info=True)
            result["errors"] += 1

        return result

    def _generate_report(self, total_elapsed: float) -> str:
        """Generate human-readable overnight report."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            "# AI Tester Overnight Report",
            f"**Date**: {timestamp}",
            f"**Total Runtime**: {total_elapsed/3600:.1f} hours",
            "",
        ]

        for game_id, stats in self._results.items():
            hours = stats['total_time_s'] / 3600
            lines.append(f"## {game_id}")
            lines.append(f"- **Play time**: {hours:.1f}h ({stats['cycles']} cycles)")
            lines.append(f"- **Battles**: {stats['battles']}")

            if stats['level_start'] and stats['level_end']:
                lines.append(f"- **Level**: {stats['level_start']} -> {stats['level_end']}")
            if stats['gold_start'] is not None and stats['gold_end'] is not None:
                gold_delta = (stats['gold_end'] or 0) - (stats['gold_start'] or 0)
                lines.append(
                    f"- **Gold**: {stats['gold_start']} -> {stats['gold_end']} (Δ{gold_delta:+.0f})")

            lines.append(f"- **Skills used**: {stats['skills_used']}")
            lines.append(f"- **Quests completed**: {stats['quests_completed']}")

            if stats['puzzle_moves'] > 0:
                win_rate = (stats['puzzle_wins'] / max(stats['cycles'], 1)) * 100
                lines.append(f"- **Puzzle moves**: {stats['puzzle_moves']}")
                lines.append(f"- **Puzzle wins**: {stats['puzzle_wins']} ({win_rate:.0f}% win rate)")

            unknown_rate = stats['unknown_screens'] / max(stats['cycles'], 1)
            lines.append(
                f"- **Unknown screens**: {stats['unknown_screens']} ({unknown_rate:.1f}/cycle)")
            lines.append(f"- **Errors**: {stats['errors']}")
            lines.append("")

        # Summary
        total_errors = sum(s['errors'] for s in self._results.values())
        total_battles = sum(s['battles'] for s in self._results.values())
        lines.append("## Summary")
        lines.append(f"- Total battles: {total_battles}")
        lines.append(f"- Total errors: {total_errors}")
        lines.append(f"- Stability: {'GOOD' if total_errors < 5 else 'NEEDS_ATTENTION'}")

        return "\n".join(lines)

    def _save_report(self, report: str):
        """Save report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        # Save markdown report
        report_path = self._report_dir / f"overnight_{timestamp}.md"
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)

        # Save raw JSON results
        json_path = self._report_dir / f"overnight_{timestamp}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(self._results, f, indent=2, ensure_ascii=False)

        logger.info("Report saved: %s", report_path)


def main():
    parser = argparse.ArgumentParser(description="AI Tester Overnight Runner")
    parser.add_argument("--hours", type=float, default=12.0, help="Total run hours")
    parser.add_argument("--games", nargs="+", default=["ash_n_veil", "carmatch"],
                        help="Game IDs to test")
    parser.add_argument("--cycle-duration", type=int, default=1800,
                        help="Duration per game per cycle (seconds)")
    args = parser.parse_args()

    # Setup logging
    log_dir = Path("E:/AI/virtual_player/data/reports")
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / f"overnight_{timestamp}.log", encoding='utf-8'),
            logging.StreamHandler(),
        ],
    )

    # Game configs
    GAME_CONFIGS = {
        "ash_n_veil": {
            "game_id": "ash_n_veil",
            "package_name": "studio.gameberry.anv",
            "duration_s": args.cycle_duration,
        },
        "carmatch": {
            "game_id": "carmatch",
            "package_name": "com.grandgames.carmatch",
            "duration_s": args.cycle_duration,
        },
    }

    games = [GAME_CONFIGS[g] for g in args.games if g in GAME_CONFIGS]
    if not games:
        print(f"No valid games. Available: {list(GAME_CONFIGS.keys())}")
        sys.exit(1)

    runner = OvernightRunner(games=games, total_hours=args.hours)
    runner.run()


if __name__ == "__main__":
    main()
