"""
StateMatcher — YOLO 관찰 상태를 APK 정답 큐의 어느 position인지 매칭.

용도:
  1. AI Tester가 "지금 라인 N의 head shooter는 무엇?"이라고 묻는 경우
  2. APK queue의 어느 진행도(progress)인지 추정
  3. 다음에 어떤 holder가 보일지 predict

원리:
  - APK는 게임 정답 (라인별 shooter 시퀀스)
  - YOLO는 화면에서 현재 visible holders를 봄
  - 두 데이터 매칭 → 현재 게임 상태 추정
"""
from typing import List, Dict, Optional, Tuple
from collections import Counter

from .level_loader import LevelLoader, COLOR_NAMES


class StateMatcher:
    """게임 상태 매칭."""

    def __init__(self, loader: LevelLoader):
        self.loader = loader

    def match_lines(self, level_num: int, observed_line_heads: List[dict],
                    variant: Optional[str] = None) -> List[dict]:
        """
        관찰된 line heads를 APK lines에 매칭.

        Args:
            level_num: 현재 레벨 번호
            observed_line_heads: RuntimeDetector.get_visible_state()['line_heads']
            variant: APK 변형

        Returns:
            매칭 결과 리스트:
              [{observed_line, apk_line, match, observed_material,
                expected_material, position_estimate}]
        """
        queue = self.loader.get_queue(level_num, variant)
        if not queue:
            return []

        apk_lines = queue.get("lines", [])
        if not apk_lines:
            return []

        # APK head materials per line (현재 시작 시점)
        apk_heads_by_line = {}
        for line in apk_lines:
            li = line.get("line_index")
            shooters = line.get("shooters", [])
            if shooters:
                apk_heads_by_line[li] = shooters[0].get("material")

        # Try direct index match (observed line 0 → apk line 0, etc.)
        results = []
        for obs in observed_line_heads:
            obs_line = obs.get("line", -1)
            obs_mat = obs.get("material")
            apk_mat = apk_heads_by_line.get(obs_line)
            results.append({
                "observed_line": obs_line,
                "observed_material": obs_mat,
                "observed_name": obs.get("name", "?"),
                "apk_line": obs_line,
                "expected_material": apk_mat,
                "expected_name": COLOR_NAMES.get(apk_mat, "?") if apk_mat else None,
                "match": obs_mat == apk_mat if (obs_mat and apk_mat) else False,
                "match_confidence": obs.get("conf", 0),
            })
        return results

    def estimate_progress(self, level_num: int,
                          observed_state: dict,
                          variant: Optional[str] = None) -> dict:
        """
        현재 게임 상태가 APK queue의 어느 진행도(progress)에 해당하는지 추정.

        Args:
            level_num: 레벨
            observed_state: RuntimeDetector.get_visible_state() 결과

        Returns:
          {
            "estimated_total_shooters": int,
            "estimated_consumed": int,
            "progress_pct": float,
            "per_line_estimate": [{line, total, head_position}]
          }
        """
        queue = self.loader.get_queue(level_num, variant)
        if not queue:
            return {}

        observed_heads = observed_state.get("line_heads", [])
        observed_dist = Counter(h["material"] for h in observed_state.get("holders", []))

        per_line = []
        for line in queue.get("lines", []):
            li = line.get("line_index")
            shooters = line.get("shooters", [])
            head_pos = 0
            # Find observed head for this line
            obs_for_line = next((h for h in observed_heads if h["line"] == li), None)
            if obs_for_line:
                obs_mat = obs_for_line.get("material")
                # Walk shooters, find first match
                for i, s in enumerate(shooters):
                    if s.get("material") == obs_mat:
                        head_pos = i
                        break
            per_line.append({
                "line": li,
                "total_shooters": len(shooters),
                "estimated_head_position": head_pos,
                "remaining": len(shooters) - head_pos,
            })

        total_shooters = sum(p["total_shooters"] for p in per_line)
        consumed = sum(p["estimated_head_position"] for p in per_line)
        progress_pct = round(consumed / max(1, total_shooters) * 100, 1)

        return {
            "estimated_total_shooters": total_shooters,
            "estimated_consumed": consumed,
            "progress_pct": progress_pct,
            "per_line_estimate": per_line,
        }

    def predict_next_taps(self, level_num: int,
                           observed_state: dict, n: int = 5,
                           variant: Optional[str] = None) -> List[dict]:
        """
        APK 정답 기반으로 "다음 N개 탭에서 등장할 holder material" 예측.

        의미: AI Tester가 다음 행동을 결정할 때 참고 가능.
        """
        progress = self.estimate_progress(level_num, observed_state, variant)
        queue = self.loader.get_queue(level_num, variant)
        if not progress or not queue:
            return []

        next_taps = []
        per_line = {p["line"]: p for p in progress["per_line_estimate"]}
        for line in queue.get("lines", []):
            li = line.get("line_index")
            shooters = line.get("shooters", [])
            head_pos = per_line.get(li, {}).get("estimated_head_position", 0)
            for i in range(head_pos, min(head_pos + n, len(shooters))):
                s = shooters[i]
                next_taps.append({
                    "line": li,
                    "position": s.get("position_in_line"),
                    "id": s.get("id"),
                    "material": s.get("material"),
                    "material_name": s.get("material_name", COLOR_NAMES.get(s.get("material"), "?")),
                    "ammo": s.get("ammo", 1),
                })
        return next_taps[:n]


if __name__ == "__main__":
    loader = LevelLoader()
    matcher = StateMatcher(loader)

    # Mock observed state
    mock_state = {
        "line_heads": [
            {"line": 0, "material": 24, "name": "holder_c24", "conf": 0.85},
            {"line": 1, "material": 14, "name": "holder_c14", "conf": 0.80},
            {"line": 2, "material": 9, "name": "holder_c9", "conf": 0.78},
            {"line": 3, "material": 4, "name": "holder_c4", "conf": 0.82},
        ],
        "holders": [],
    }

    print("=== Mock Test: Level 184 ===")
    matches = matcher.match_lines(184, mock_state["line_heads"])
    for m in matches:
        check = "✓" if m["match"] else "✗"
        print(f"  Line {m['observed_line']}: observed={m['observed_name']} "
              f"vs expected={m['expected_name']} {check}")

    progress = matcher.estimate_progress(184, mock_state)
    print(f"\nProgress: {progress.get('progress_pct')}% "
          f"({progress.get('estimated_consumed')}/{progress.get('estimated_total_shooters')})")

    next_taps = matcher.predict_next_taps(184, mock_state, n=5)
    print(f"\nNext 5 predicted taps:")
    for t in next_taps:
        print(f"  Line {t['line']}: {t['material_name']} (id={t['id']}, ammo={t['ammo']})")
