"""
YAML Exporter
==============
Stage 2 (AI 기획서 생성) 입력용 YAML 내보내기.
게임 플레이 데이터를 구조화된 YAML로 변환.
"""

import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..config import REPORTS_DIR
from ..history.storage import HistoryStorage


class YamlExporter:
    """Stage 2 입력용 YAML 내보내기."""

    def __init__(self, storage: HistoryStorage):
        self.storage = storage

    def export(self, game_id: str, output_path: Optional[Path] = None) -> Path:
        """게임 플레이 데이터를 YAML로 내보내기."""
        sessions = self.storage.get_sessions(game_id)
        if not sessions:
            raise ValueError(f"No sessions found for game '{game_id}'")

        # Build export structure
        export_data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "game_id": game_id,
            "summary": self._build_summary(sessions, game_id),
            "behavior_patterns": self._build_behavior_patterns(sessions),
            "session_details": self._build_session_details(sessions),
        }

        # Determine output path
        if output_path is None:
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = REPORTS_DIR / f"{game_id}_stage2_{timestamp}.yaml"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(export_data, f, default_flow_style=False,
                      allow_unicode=True, sort_keys=False)

        return output_path

    def _build_summary(self, sessions: List[Dict], game_id: str) -> Dict[str, Any]:
        """통계 요약 생성."""
        action_dist = self.storage.get_action_summary(game_id)
        total_actions = sum(action_dist.values())
        durations = [s["duration_seconds"] for s in sessions if s["duration_seconds"]]
        scores = [s["final_score"] for s in sessions]

        return {
            "total_sessions": len(sessions),
            "total_actions": total_actions,
            "avg_duration_seconds": round(sum(durations) / len(durations), 1) if durations else 0,
            "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            "max_score": max(scores) if scores else 0,
            "action_distribution": {
                name: {"count": count, "ratio": round(count / total_actions, 3) if total_actions else 0}
                for name, count in action_dist.items()
            },
        }

    def _build_behavior_patterns(self, sessions: List[Dict]) -> List[Dict[str, Any]]:
        """행동 패턴 분석."""
        patterns = []

        # Group sessions by persona
        by_persona: Dict[str, List[Dict]] = {}
        for s in sessions:
            by_persona.setdefault(s["persona_name"], []).append(s)

        for persona_name, persona_sessions in by_persona.items():
            durations = [s["duration_seconds"] for s in persona_sessions if s["duration_seconds"]]
            scores = [s["final_score"] for s in persona_sessions]
            patterns.append({
                "persona": persona_name,
                "session_count": len(persona_sessions),
                "avg_duration": round(sum(durations) / len(durations), 1) if durations else 0,
                "avg_score": round(sum(scores) / len(scores), 1) if scores else 0,
            })

        return patterns

    def _build_session_details(self, sessions: List[Dict]) -> List[Dict[str, Any]]:
        """세션별 상세 정보 (최근 10개)."""
        details = []
        for session in sessions[:10]:
            actions = self.storage.get_actions(session["session_id"])
            action_names = [a["action_name"] for a in actions]

            # Count consecutive same actions (streaks)
            streaks = []
            if action_names:
                current = action_names[0]
                count = 1
                for name in action_names[1:]:
                    if name == current:
                        count += 1
                    else:
                        if count >= 3:
                            streaks.append({"action": current, "length": count})
                        current = name
                        count = 1
                if count >= 3:
                    streaks.append({"action": current, "length": count})

            details.append({
                "session_id": session["session_id"],
                "persona": session["persona_name"],
                "pattern": session["pattern_name"],
                "duration_seconds": session["duration_seconds"],
                "action_count": session["action_count"],
                "final_score": session["final_score"],
                "action_sequence_sample": action_names[:50],
                "notable_streaks": streaks,
            })

        return details
