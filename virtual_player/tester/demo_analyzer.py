"""
Demo Analyzer — 시연 데이터 → Playbook 규칙 추출
===================================================
사람의 시연 녹화(demo_log.jsonl + 스크린샷)를 분석하여
Playbook 초안을 자동 생성.

AI가 시연 데이터를 "이해"하는 과정:

1단계: 라벨링 (각 스크린샷의 screen_type 판별)
  - pre_0001.png → "lobby"
  - pre_0002.png → "gameplay"
  → Vision API 호출로 자동 수행

2단계: 패턴 추출 (같은 화면에서 반복되는 탭 좌표 클러스터링)
  - "lobby" 화면에서 항상 (540, 1500) 근처를 탭
  → screen_handler 후보로 등록

3단계: 전이 분석 (화면 A → 탭 → 화면 B 패턴)
  - lobby → tap(540,1500) → gameplay
  - gameplay → tap(car) → gameplay
  - gameplay → ... → win
  → screen_flow 자동 생성

4단계: Playbook 초안 출력 (JSON)
  - screen_handlers, forbidden_regions 등 자동 생성
  - 사람이 검토 + 수정

사용법:
  python -m virtual_player.tester.demo_analyzer \\
    --demo E:/AI/virtual_player/data/games/carmatch/demonstrations/demo_20260306_100000
"""

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .perception import Perception, BoardState


class DemoAnalyzer:
    """시연 데이터 분석기."""

    def __init__(
        self,
        demo_dir: Path,
        perception: Optional[Perception] = None,
    ):
        self.demo_dir = Path(demo_dir)
        self.log_path = self.demo_dir / "demo_log.jsonl"
        self.perception = perception or Perception()

        self._entries: List[dict] = []
        self._labeled: List[dict] = []  # screen_type이 추가된 entries

    def analyze(self) -> dict:
        """전체 분석 파이프라인 실행.

        Returns: Playbook 초안 dict
        """
        print(f"[Analyzer] Loading demo: {self.demo_dir}")

        # 1. 로그 로드
        self._load_entries()
        print(f"[Analyzer] Loaded {len(self._entries)} frames")

        # 2. 라벨링 (Vision API)
        self._label_screenshots()
        print(f"[Analyzer] Labeled {len(self._labeled)} frames")

        # 3. 패턴 추출
        handlers = self._extract_screen_handlers()
        print(f"[Analyzer] Extracted {len(handlers)} screen handlers")

        # 4. 전이 분석
        transitions = self._extract_transitions()
        print(f"[Analyzer] Extracted {len(transitions)} screen transitions")

        # 5. 금지 영역 추론
        forbidden = self._infer_forbidden_regions()

        # 6. 초안 생성
        draft = {
            "screen_handlers": handlers,
            "screen_flow": transitions,
            "forbidden_regions": forbidden,
            "total_frames": len(self._entries),
            "unique_screens": list(set(
                e.get("pre_screen", "unknown") for e in self._labeled
            )),
            "avg_interval_sec": self._avg_interval(),
        }

        # 저장
        output_path = self.demo_dir / "playbook_draft.json"
        output_path.write_text(
            json.dumps(draft, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[Analyzer] Draft saved: {output_path}")

        return draft

    def _load_entries(self):
        """JSONL 로그 로드."""
        self._entries = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._entries.append(json.loads(line))

    def _label_screenshots(self):
        """각 프레임의 pre/post 스크린샷에 screen_type 라벨 추가.

        모든 프레임을 라벨링하면 Vision API 비용이 크므로,
        간격이 짧은 연속 프레임은 건너뛴다.
        """
        self._labeled = []
        last_screen = "unknown"

        for i, entry in enumerate(self._entries):
            labeled = dict(entry)

            pre_path = self.demo_dir / entry["pre_screenshot"]
            if pre_path.exists():
                # 이전 프레임과 간격이 1초 미만이면 같은 화면으로 간주
                if entry["interval_sec"] < 1.0 and i > 0:
                    labeled["pre_screen"] = last_screen
                else:
                    board = self.perception.perceive(pre_path)
                    labeled["pre_screen"] = board.screen_type
                    last_screen = board.screen_type
            else:
                labeled["pre_screen"] = "unknown"

            self._labeled.append(labeled)

    def _extract_screen_handlers(self) -> Dict[str, dict]:
        """같은 화면에서 반복되는 탭 좌표 → screen_handler 후보.

        예: "lobby" 화면에서 매번 (540±30, 1500±30) → handler 등록
        """
        # screen_type별 탭 좌표 수집
        screen_taps: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
        for entry in self._labeled:
            screen = entry.get("pre_screen", "unknown")
            if screen == "gameplay":
                continue  # gameplay 탭은 다양하므로 handler 대상 아님
            action = entry.get("action", {})
            if action.get("type") == "tap":
                screen_taps[screen].append((action["x"], action["y"]))

        handlers = {}
        for screen, taps in screen_taps.items():
            if len(taps) < 2:
                continue

            # 좌표 클러스터링 (단순: 중심점)
            avg_x = sum(t[0] for t in taps) // len(taps)
            avg_y = sum(t[1] for t in taps) // len(taps)

            # 분산이 작으면 고정 좌표 handler
            var_x = sum((t[0] - avg_x) ** 2 for t in taps) / len(taps)
            var_y = sum((t[1] - avg_y) ** 2 for t in taps) / len(taps)

            if var_x < 5000 and var_y < 5000:  # 표준편차 ~70px 이내
                handlers[screen] = {
                    "tap_x": avg_x,
                    "tap_y": avg_y,
                    "sample_count": len(taps),
                    "variance": {"x": round(var_x, 1), "y": round(var_y, 1)},
                    "confidence": "high" if var_x < 2000 and var_y < 2000 else "medium",
                }

        return handlers

    def _extract_transitions(self) -> Dict[str, List[str]]:
        """화면 전이 패턴 추출.

        pre_screen[i] → action → pre_screen[i+1] 패턴.
        """
        transitions: Dict[str, Counter] = defaultdict(Counter)

        for i in range(len(self._labeled) - 1):
            src = self._labeled[i].get("pre_screen", "unknown")
            dst = self._labeled[i + 1].get("pre_screen", "unknown")
            if src != dst:
                transitions[src][dst] += 1

        # Counter → sorted list
        result = {}
        for src, counter in transitions.items():
            result[src] = [dst for dst, _ in counter.most_common()]

        return result

    def _infer_forbidden_regions(self) -> List[List[int]]:
        """사람이 한 번도 탭하지 않은 영역 = 금지 후보.

        화면을 그리드로 나누고, 탭 빈도 0인 영역 추출.
        (단, gameplay 탭은 제외하고 UI 영역만 분석)
        """
        # 단순히 y > 1700 영역 (보통 부스터 바)을 체크
        low_taps = [
            e for e in self._labeled
            if e.get("action", {}).get("y", 0) > 1700
            and e.get("pre_screen") == "gameplay"
        ]

        # gameplay 중 하단 영역을 탭한 적이 없으면 금지 후보
        if len(low_taps) == 0:
            return [[0, 1700, 1080, 1920]]

        return []

    def _avg_interval(self) -> float:
        """평균 탭 간격."""
        intervals = [
            e["interval_sec"] for e in self._entries
            if e["interval_sec"] > 0
        ]
        return round(sum(intervals) / len(intervals), 2) if intervals else 0.0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Demo Analyzer — Extract rules from demonstration")
    parser.add_argument("--demo", required=True, help="Path to demo directory")
    args = parser.parse_args()

    analyzer = DemoAnalyzer(demo_dir=Path(args.demo))
    draft = analyzer.analyze()

    print("\n=== Playbook Draft ===")
    print(json.dumps(draft, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
