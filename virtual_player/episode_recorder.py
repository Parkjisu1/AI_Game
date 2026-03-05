"""
Episode Recorder & Experience Learner
======================================
Records full game episodes (action sequences + outcome),
then extracts patterns to improve future play.

Flow:
  1. EpisodeRecorder: captures each game session as an episode
  2. ExperienceLearner: analyzes episodes -> generates strategy text
  3. Strategy text injected into Vision AI context -> smarter play

Episode JSON format:
  {
    "game_id": "carmatch",
    "episode_id": 5,
    "started_at": "2026-03-05T15:30:00",
    "ended_at": "2026-03-05T15:32:14",
    "outcome": "win",           # win / fail / timeout / unknown
    "duration_sec": 134,
    "actions": [
      {"tick": 1, "screen": "lobby", "action": "tap_play", "x": 540, "y": 1500},
      {"tick": 2, "screen": "gameplay", "action": "tap_car", "x": 300, "y": 600,
       "context": {"holder_slots_used": 2, "colors_in_holder": ["red", "red"]}},
      ...
    ],
    "stats": {
      "total_taps": 42,
      "screens_visited": ["lobby", "gameplay", "win"],
      "fail_reason": null
    }
  }
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EpisodeRecorder:
    """Records a single game episode (one play session from lobby to outcome)."""

    def __init__(self, game_id: str, data_dir: Path):
        self.game_id = game_id
        self.episodes_dir = data_dir / "games" / game_id / "episodes"
        self.episodes_dir.mkdir(parents=True, exist_ok=True)
        self._current: Optional[Dict] = None
        self._episode_id = self._next_episode_id()

    def start_episode(self) -> int:
        """Start recording a new episode. Returns episode_id."""
        self._episode_id = self._next_episode_id()
        self._current = {
            "game_id": self.game_id,
            "episode_id": self._episode_id,
            "started_at": datetime.now().isoformat(),
            "ended_at": None,
            "outcome": "unknown",
            "duration_sec": 0,
            "actions": [],
            "stats": {
                "total_taps": 0,
                "screens_visited": [],
                "fail_reason": None,
            },
        }
        logger.info("Episode %d started", self._episode_id)
        return self._episode_id

    def record_action(
        self,
        tick: int,
        screen_type: str,
        action_name: str,
        x: int = 0,
        y: int = 0,
        context: Optional[Dict] = None,
    ) -> None:
        """Record a single action within the current episode."""
        if self._current is None:
            return
        entry = {
            "tick": tick,
            "screen": screen_type,
            "action": action_name,
            "x": x,
            "y": y,
            "timestamp": time.time(),
        }
        if context:
            entry["context"] = context
        self._current["actions"].append(entry)

        # Track screens visited
        visited = self._current["stats"]["screens_visited"]
        if screen_type and screen_type not in visited:
            visited.append(screen_type)

        if "tap" in action_name:
            self._current["stats"]["total_taps"] += 1

    def end_episode(
        self,
        outcome: str,
        fail_reason: Optional[str] = None,
    ) -> Path:
        """End the current episode and save to disk.

        Args:
            outcome: "win", "fail", "timeout", "unknown"
            fail_reason: optional reason (e.g. "out_of_space", "lives_exhausted")

        Returns:
            Path to saved episode JSON file.
        """
        if self._current is None:
            # No episode in progress, create a minimal one
            self.start_episode()

        self._current["ended_at"] = datetime.now().isoformat()
        self._current["outcome"] = outcome
        started = datetime.fromisoformat(self._current["started_at"])
        self._current["duration_sec"] = int(
            (datetime.now() - started).total_seconds()
        )
        if fail_reason:
            self._current["stats"]["fail_reason"] = fail_reason

        path = self.episodes_dir / f"episode_{self._episode_id:04d}.json"
        path.write_text(
            json.dumps(self._current, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(
            "Episode %d ended: %s (%d actions, %ds)",
            self._episode_id,
            outcome,
            len(self._current["actions"]),
            self._current["duration_sec"],
        )
        self._current = None
        return path

    @property
    def is_recording(self) -> bool:
        return self._current is not None

    @property
    def current_action_count(self) -> int:
        if self._current is None:
            return 0
        return len(self._current["actions"])

    def _next_episode_id(self) -> int:
        existing = list(self.episodes_dir.glob("episode_*.json"))
        if not existing:
            return 1
        ids = []
        for p in existing:
            try:
                ids.append(int(p.stem.split("_")[1]))
            except (IndexError, ValueError):
                pass
        return max(ids) + 1 if ids else 1


class ExperienceLearner:
    """Analyzes episode history and generates strategy insights.

    Reads all episodes for a game, computes win/fail patterns,
    and produces a text summary that can be injected into Vision AI context.
    """

    def __init__(self, game_id: str, data_dir: Path):
        self.game_id = game_id
        self.episodes_dir = data_dir / "games" / game_id / "episodes"
        self.summary_path = data_dir / "games" / game_id / "experience_summary.txt"

    def load_episodes(self) -> List[Dict]:
        """Load all episode files."""
        if not self.episodes_dir.exists():
            return []
        episodes = []
        for p in sorted(self.episodes_dir.glob("episode_*.json")):
            try:
                episodes.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception as e:
                logger.warning("Failed to load %s: %s", p, e)
        return episodes

    def analyze(self) -> Dict[str, Any]:
        """Analyze all episodes and return statistics."""
        episodes = self.load_episodes()
        if not episodes:
            return {"total": 0, "wins": 0, "fails": 0, "win_rate": 0.0}

        wins = [e for e in episodes if e["outcome"] == "win"]
        fails = [e for e in episodes if e["outcome"] == "fail"]
        total = len(episodes)

        # Average actions per outcome
        avg_actions_win = (
            sum(len(e["actions"]) for e in wins) / len(wins) if wins else 0
        )
        avg_actions_fail = (
            sum(len(e["actions"]) for e in fails) / len(fails) if fails else 0
        )

        # Average duration
        avg_dur_win = (
            sum(e["duration_sec"] for e in wins) / len(wins) if wins else 0
        )
        avg_dur_fail = (
            sum(e["duration_sec"] for e in fails) / len(fails) if fails else 0
        )

        # Fail reasons
        fail_reasons: Dict[str, int] = {}
        for e in fails:
            reason = e.get("stats", {}).get("fail_reason", "unknown")
            fail_reasons[reason] = fail_reasons.get(reason, 0) + 1

        # Screen visit patterns (what screens appear in wins vs fails)
        win_screens = set()
        fail_screens = set()
        for e in wins:
            win_screens.update(e.get("stats", {}).get("screens_visited", []))
        for e in fails:
            fail_screens.update(e.get("stats", {}).get("screens_visited", []))

        # Recent trend (last 10 episodes)
        recent = episodes[-10:]
        recent_wins = sum(1 for e in recent if e["outcome"] == "win")
        recent_rate = recent_wins / len(recent) if recent else 0

        return {
            "total": total,
            "wins": len(wins),
            "fails": len(fails),
            "win_rate": len(wins) / total if total > 0 else 0,
            "recent_win_rate": recent_rate,
            "avg_actions_win": round(avg_actions_win, 1),
            "avg_actions_fail": round(avg_actions_fail, 1),
            "avg_duration_win": round(avg_dur_win, 1),
            "avg_duration_fail": round(avg_dur_fail, 1),
            "fail_reasons": fail_reasons,
            "win_screens": sorted(win_screens),
            "fail_screens": sorted(fail_screens),
        }

    def generate_summary(self) -> str:
        """Generate a human-readable experience summary for Vision AI injection.

        Returns:
            Strategy text string, or empty string if not enough data.
        """
        stats = self.analyze()
        if stats["total"] < 3:
            return ""

        lines = []
        lines.append(
            f"LEARNED FROM {stats['total']} GAMES "
            f"(win rate: {stats['win_rate']:.0%}, "
            f"recent: {stats['recent_win_rate']:.0%}):"
        )

        # Win/fail action comparison
        if stats["avg_actions_win"] > 0 and stats["avg_actions_fail"] > 0:
            if stats["avg_actions_fail"] < stats["avg_actions_win"] * 0.6:
                lines.append(
                    f"- Fails happen fast (avg {stats['avg_actions_fail']:.0f} taps vs "
                    f"{stats['avg_actions_win']:.0f} for wins). Think more before tapping."
                )
            elif stats["avg_actions_fail"] > stats["avg_actions_win"] * 1.4:
                lines.append(
                    f"- Fails involve too many taps ({stats['avg_actions_fail']:.0f} vs "
                    f"{stats['avg_actions_win']:.0f} for wins). Be more decisive."
                )

        # Fail reasons
        if stats["fail_reasons"]:
            top_reason = max(stats["fail_reasons"], key=stats["fail_reasons"].get)
            count = stats["fail_reasons"][top_reason]
            lines.append(
                f"- Most common fail: {top_reason} ({count}/{stats['fails']} fails). "
                f"Actively avoid this pattern."
            )

        # Win rate trend
        if stats["total"] >= 10:
            if stats["recent_win_rate"] > stats["win_rate"] + 0.1:
                lines.append("- Getting better! Keep current strategy.")
            elif stats["recent_win_rate"] < stats["win_rate"] - 0.1:
                lines.append(
                    "- Recent performance declining. Be more careful with holder management."
                )

        summary = " ".join(lines)
        self.summary_path.write_text(summary, encoding="utf-8")
        logger.info("Experience summary updated: %s", self.summary_path)
        return summary

    def get_cached_summary(self) -> str:
        """Get the last generated summary (without re-analyzing)."""
        if self.summary_path.exists():
            return self.summary_path.read_text(encoding="utf-8").strip()
        return ""
