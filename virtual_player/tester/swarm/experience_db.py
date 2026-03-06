"""
Experience DB — 경험 축적 데이터베이스
=========================================
Voyager(2023)의 Skill Library 개념을 게임 테스팅에 적용.

"이 화면에서 이 좌표를 탭하면 이 결과가 나온다"를
반복 관찰로 축적하여 확신도(confidence)를 높인다.

기존 Memory(Layer 2)와의 차이:
  Memory: 1판 안에서의 단기 기억 (매 게임 리셋)
  ExperienceDB: 전체 세션에 걸친 장기 기억 (영구 저장)
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ExperienceDB:
    """영구 경험 데이터베이스.

    저장 구조:
    {
      "screen_actions": {
        "lobby": {
          "(540,1500)": {"success": 15, "fail": 0, "result": "gameplay"},
          "(200,800)": {"success": 0, "fail": 3, "result": "unknown"}
        },
        "popup": {
          "(885,340)": {"success": 8, "fail": 2, "result": "lobby"}
        }
      },
      "screen_recognition": {
        "lobby": {"correct": 45, "wrong": 3},
        "popup": {"correct": 30, "wrong": 5}
      },
      "color_accuracy": {
        "red": {"correct": 20, "wrong": 5},
        "blue": {"correct": 18, "wrong": 7}
      },
      "failure_patterns": [
        {"screen": "gameplay", "holder": 6, "action": "tap car", "count": 5}
      ]
    }
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._data: Dict = {
            "screen_actions": defaultdict(lambda: defaultdict(
                lambda: {"success": 0, "fail": 0, "result": "unknown"}
            )),
            "screen_recognition": defaultdict(
                lambda: {"correct": 0, "wrong": 0}
            ),
            "color_accuracy": defaultdict(
                lambda: {"correct": 0, "wrong": 0}
            ),
            "failure_patterns": [],
            "total_sessions": 0,
            "total_games": 0,
            "total_wins": 0,
        }
        self._load()

    def _load(self):
        """파일에서 로드."""
        if self.db_path.exists():
            try:
                raw = json.loads(self.db_path.read_text(encoding="utf-8"))
                # defaultdict로 변환
                for screen, actions in raw.get("screen_actions", {}).items():
                    for coord, stats in actions.items():
                        self._data["screen_actions"][screen][coord] = stats
                for screen, stats in raw.get("screen_recognition", {}).items():
                    self._data["screen_recognition"][screen] = stats
                for color, stats in raw.get("color_accuracy", {}).items():
                    self._data["color_accuracy"][color] = stats
                self._data["failure_patterns"] = raw.get("failure_patterns", [])
                self._data["total_sessions"] = raw.get("total_sessions", 0)
                self._data["total_games"] = raw.get("total_games", 0)
                self._data["total_wins"] = raw.get("total_wins", 0)
            except (json.JSONDecodeError, Exception):
                pass

    def save(self):
        """파일에 저장."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # defaultdict → 일반 dict로 변환
        serializable = {
            "screen_actions": {
                screen: dict(actions)
                for screen, actions in self._data["screen_actions"].items()
            },
            "screen_recognition": dict(self._data["screen_recognition"]),
            "color_accuracy": dict(self._data["color_accuracy"]),
            "failure_patterns": self._data["failure_patterns"][-100:],
            "total_sessions": self._data["total_sessions"],
            "total_games": self._data["total_games"],
            "total_wins": self._data["total_wins"],
        }
        self.db_path.write_text(
            json.dumps(serializable, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def record_screen_action(
        self, screen_type: str, x: int, y: int,
        success: bool, result_screen: str = "unknown"
    ):
        """화면+좌표 행동 결과 기록."""
        coord = f"({x},{y})"
        entry = self._data["screen_actions"][screen_type][coord]
        if success:
            entry["success"] = entry.get("success", 0) + 1
        else:
            entry["fail"] = entry.get("fail", 0) + 1
        if result_screen != "unknown":
            entry["result"] = result_screen

    def get_best_action(self, screen_type: str) -> Optional[Tuple[int, int, float]]:
        """해당 화면에서 가장 성공률 높은 좌표 반환.

        Returns: (x, y, confidence) 또는 None
        """
        actions = self._data["screen_actions"].get(screen_type, {})
        best = None
        best_score = -1

        for coord, stats in actions.items():
            total = stats.get("success", 0) + stats.get("fail", 0)
            if total < 2:
                continue
            score = stats.get("success", 0) / total
            if score > best_score:
                best_score = score
                # "(540,1500)" → (540, 1500)
                nums = coord.strip("()").split(",")
                best = (int(nums[0]), int(nums[1]), best_score)

        return best

    def record_failure_pattern(
        self, screen: str, holder_count: int,
        action_desc: str
    ):
        """실패 패턴 기록."""
        self._data["failure_patterns"].append({
            "screen": screen,
            "holder": holder_count,
            "action": action_desc,
        })

    def get_stats_summary(self) -> dict:
        """통계 요약."""
        total_actions = sum(
            stats.get("success", 0) + stats.get("fail", 0)
            for actions in self._data["screen_actions"].values()
            for stats in actions.values()
        )
        total_success = sum(
            stats.get("success", 0)
            for actions in self._data["screen_actions"].values()
            for stats in actions.values()
        )
        return {
            "total_sessions": self._data["total_sessions"],
            "total_games": self._data["total_games"],
            "total_wins": self._data["total_wins"],
            "total_recorded_actions": total_actions,
            "overall_success_rate": (
                round(total_success / total_actions, 3) if total_actions > 0 else 0
            ),
            "known_screens": len(self._data["screen_actions"]),
            "failure_patterns_count": len(self._data["failure_patterns"]),
        }
