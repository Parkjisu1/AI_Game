"""
Session Analytics
==================
통계 분석 및 보고서 생성.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..config import REPORTS_DIR
from .storage import HistoryStorage


class SessionAnalytics:
    """세션 분석 및 보고서 생성."""

    def __init__(self, storage: HistoryStorage):
        self.storage = storage

    def summary(self, game_id: Optional[str] = None) -> Dict[str, Any]:
        """전체 통계 요약."""
        sessions = self.storage.get_sessions(game_id)
        if not sessions:
            return {"total_sessions": 0, "message": "No data"}

        action_summary = self.storage.get_action_summary(game_id)
        total_actions = sum(action_summary.values())
        durations = [s["duration_seconds"] for s in sessions if s["duration_seconds"]]
        scores = [s["final_score"] for s in sessions]

        return {
            "game_id": game_id or "all",
            "total_sessions": len(sessions),
            "total_actions": total_actions,
            "avg_duration_seconds": sum(durations) / len(durations) if durations else 0,
            "avg_score": sum(scores) / len(scores) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "action_distribution": action_summary,
            "personas_used": list(set(s["persona_name"] for s in sessions)),
            "patterns_used": list(set(s["pattern_name"] for s in sessions)),
        }

    def print_summary(self, game_id: Optional[str] = None) -> str:
        """콘솔 출력용 포맷된 요약."""
        stats = self.summary(game_id)
        if stats.get("total_sessions", 0) == 0:
            return "No session data found."

        lines = [
            f"=== VirtualPlayer Analytics ===",
            f"Game: {stats['game_id']}",
            f"Sessions: {stats['total_sessions']}",
            f"Total actions: {stats['total_actions']}",
            f"Avg duration: {stats['avg_duration_seconds']:.1f}s",
            f"Avg score: {stats['avg_score']:.1f}",
            f"Max score: {stats['max_score']:.1f}",
            f"Personas: {', '.join(stats['personas_used'])}",
            f"Patterns: {', '.join(stats['patterns_used'])}",
            f"",
            f"Action distribution:",
        ]
        for action_name, count in stats["action_distribution"].items():
            pct = (count / stats["total_actions"] * 100) if stats["total_actions"] > 0 else 0
            lines.append(f"  {action_name}: {count} ({pct:.1f}%)")

        return "\n".join(lines)

    def save_report(self, game_id: Optional[str] = None,
                    output_path: Optional[Path] = None) -> Path:
        """JSON 보고서 파일 저장."""
        stats = self.summary(game_id)
        if output_path is None:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{game_id or 'all'}_{timestamp}.json"
            output_path = REPORTS_DIR / filename

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        return output_path
