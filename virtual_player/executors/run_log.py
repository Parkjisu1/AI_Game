"""
Run Log -- Persistent Session Logging for Learning
===================================================
Append-only JSON log tracking every action, screen transitions,
gold changes, deaths, and success/failure rates.

Log files stored at: data/cache/{game_id}/run_logs/
"""

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ActionRecord:
    """Single action record in the run log."""
    timestamp: float
    loop: int
    action_name: str
    screen_before: str
    screen_after: str
    gold_before: float
    gold_after: float
    success: bool
    death: bool = False
    goap_goal: str = ""
    notes: str = ""


class RunLog:
    """Append-only session log for cross-session learning."""

    def __init__(self, log_dir: Path):
        self._log_dir = log_dir
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_path = self._log_dir / f"session_{self._session_id}.jsonl"
        self._records: List[ActionRecord] = []
        self._session_start = time.time()

    def record(
        self,
        loop: int,
        action_name: str,
        screen_before: str,
        screen_after: str,
        gold_before: float,
        gold_after: float,
        success: bool,
        death: bool = False,
        goap_goal: str = "",
        notes: str = "",
    ):
        """Append a single action record."""
        rec = ActionRecord(
            timestamp=time.time(),
            loop=loop,
            action_name=action_name,
            screen_before=screen_before,
            screen_after=screen_after,
            gold_before=gold_before,
            gold_after=gold_after,
            success=success,
            death=death,
            goap_goal=goap_goal,
            notes=notes,
        )
        self._records.append(rec)
        # Append to JSONL file immediately
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(rec)) + "\n")

    def summary(self) -> Dict:
        """Generate session summary statistics."""
        if not self._records:
            return {"total_actions": 0}

        total = len(self._records)
        successes = sum(1 for r in self._records if r.success)
        deaths = sum(1 for r in self._records if r.death)
        battles = sum(1 for r in self._records if r.action_name == "grind_battle")

        gold_values = [r.gold_after for r in self._records if r.gold_after > 0]
        gold_start = self._records[0].gold_before
        gold_end = self._records[-1].gold_after if gold_values else gold_start

        duration = time.time() - self._session_start
        gold_per_battle = (
            (gold_end - gold_start) / battles if battles > 0 else 0.0
        )

        return {
            "session_id": self._session_id,
            "duration_seconds": round(duration, 1),
            "total_actions": total,
            "success_rate": round(successes / total, 3) if total > 0 else 0,
            "deaths": deaths,
            "battles": battles,
            "gold_start": gold_start,
            "gold_end": gold_end,
            "gold_per_battle": round(gold_per_battle, 1),
            "actions_breakdown": self._action_breakdown(),
        }

    def _action_breakdown(self) -> Dict[str, int]:
        """Count of each action type."""
        breakdown: Dict[str, int] = {}
        for r in self._records:
            breakdown[r.action_name] = breakdown.get(r.action_name, 0) + 1
        return breakdown

    def save_summary(self):
        """Save session summary to a separate file."""
        summary = self.summary()
        summary_path = self._log_dir / f"summary_{self._session_id}.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

    @staticmethod
    def load_all_summaries(log_dir: Path) -> List[Dict]:
        """Load all session summaries for cross-session analysis."""
        summaries = []
        for p in sorted(log_dir.glob("summary_*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                summaries.append(data)
            except Exception:
                continue
        return summaries
