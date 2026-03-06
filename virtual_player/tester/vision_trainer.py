"""
Vision Trainer — Vision 정확도 개선 도구
==========================================
사람이 해야 하는 것:
  1. 스크린샷에 정답 라벨 붙이기 (screen_type, holder, cars)
  2. AI 인식 결과와 정답 비교 → 오류 패턴 파악
  3. 오류 패턴에 맞게 프롬프트 수정

Swarm이 하는 것:
  - 자동으로 스크린샷 수집 (Player Agent가 생성)
  - AI 인식 결과를 reference와 비교
  - 정확도 통계 자동 생성
  - 프롬프트 변형 후보 생성 + A/B 테스트

개선 방법론:
  Phase A: Reference DB 구축 (사람)
    스크린샷 50~100장에 정답 라벨 → JSON
    → "이 이미지의 정답은 lobby" 같은 ground truth

  Phase B: 정확도 측정 (자동)
    현재 프롬프트로 Reference DB 전체를 인식
    → 정답과 비교 → screen 정확도, holder 정확도, car 정확도 산출

  Phase C: 프롬프트 튜닝 (사람+Swarm)
    오류가 많은 유형 분석
    → 프롬프트에 힌트 추가
    → 다시 Phase B → 정확도 변화 측정

  Phase D: 로컬 CV 전환 (장기)
    Reference DB를 학습 데이터로
    → 화면 분류 모델 학습 (screen_type)
    → 색상 인식 모델 학습 (holder colors)
    → VLM 호출을 90% 줄임

사용법:
  # 1. 정답 라벨링 (사람)
  python -m virtual_player.tester.vision_trainer label --dir screenshots/

  # 2. 정확도 측정 (자동)
  python -m virtual_player.tester.vision_trainer evaluate

  # 3. 오류 보고서 생성
  python -m virtual_player.tester.vision_trainer report
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .perception import Perception, BoardState


class ReferenceDB:
    """정답 라벨 데이터베이스.

    사람이 채우는 ground truth.
    각 스크린샷에 대한 정확한 screen_type, holder, active_cars 정보.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._entries: Dict[str, dict] = {}  # filename → ground truth
        self._load()

    def _load(self):
        if self.db_path.exists():
            try:
                self._entries = json.loads(
                    self.db_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, Exception):
                pass

    def save(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.write_text(
            json.dumps(self._entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_label(
        self,
        image_filename: str,
        screen_type: str,
        holder: Optional[List] = None,
        active_cars: Optional[List[dict]] = None,
        notes: str = "",
    ):
        """정답 라벨 추가.

        사람이 호출하는 함수:
          db.add_label("frame_001.png", "lobby")
          db.add_label("frame_042.png", "gameplay",
            holder=["red","red","blue",None,None,None,None],
            active_cars=[{"color":"green","x":450,"y":800}])
        """
        self._entries[image_filename] = {
            "screen_type": screen_type,
            "holder": holder or [None] * 7,
            "active_cars": active_cars or [],
            "notes": notes,
        }

    def get_label(self, image_filename: str) -> Optional[dict]:
        return self._entries.get(image_filename)

    def count(self) -> int:
        return len(self._entries)

    def get_all(self) -> Dict[str, dict]:
        return self._entries


class VisionEvaluator:
    """Vision 정확도 측정기.

    Reference DB의 정답과 현재 Perception의 출력을 비교.
    """

    def __init__(
        self,
        reference_db: ReferenceDB,
        images_dir: Path,
        perception: Optional[Perception] = None,
    ):
        self.ref_db = reference_db
        self.images_dir = images_dir
        self.perception = perception or Perception()

    def evaluate(self) -> dict:
        """전체 Reference DB에 대해 정확도 측정.

        Returns: {
            "total": N,
            "screen_accuracy": 0.85,
            "holder_accuracy": 0.78,
            "car_count_accuracy": 0.70,
            "errors": [
                {"image": "x.png", "field": "screen",
                 "expected": "lobby", "got": "popup"}
            ]
        }
        """
        total = 0
        screen_correct = 0
        holder_correct = 0
        car_count_correct = 0
        errors = []

        for filename, ground_truth in self.ref_db.get_all().items():
            img_path = self.images_dir / filename
            if not img_path.exists():
                continue

            total += 1
            result = self.perception.perceive(img_path)

            # Screen type 비교
            expected_screen = ground_truth["screen_type"]
            if result.screen_type == expected_screen:
                screen_correct += 1
            else:
                errors.append({
                    "image": filename,
                    "field": "screen_type",
                    "expected": expected_screen,
                    "got": result.screen_type,
                })

            # Holder 비교 (gameplay일 때만)
            if expected_screen == "gameplay":
                expected_holder = ground_truth.get("holder", [None] * 7)
                holder_match = sum(
                    1 for a, b in zip(expected_holder, result.holder)
                    if a == b
                ) / 7
                if holder_match >= 0.8:
                    holder_correct += 1
                else:
                    errors.append({
                        "image": filename,
                        "field": "holder",
                        "expected": expected_holder,
                        "got": result.holder,
                        "match_rate": round(holder_match, 2),
                    })

                # Active cars 개수 비교
                expected_count = len(ground_truth.get("active_cars", []))
                actual_count = len(result.active_cars)
                if abs(expected_count - actual_count) <= 1:
                    car_count_correct += 1
                else:
                    errors.append({
                        "image": filename,
                        "field": "car_count",
                        "expected": expected_count,
                        "got": actual_count,
                    })

        gameplay_count = sum(
            1 for gt in self.ref_db.get_all().values()
            if gt["screen_type"] == "gameplay"
        )

        return {
            "total": total,
            "screen_accuracy": round(screen_correct / total, 3) if total else 0,
            "holder_accuracy": (
                round(holder_correct / gameplay_count, 3)
                if gameplay_count else 0
            ),
            "car_count_accuracy": (
                round(car_count_correct / gameplay_count, 3)
                if gameplay_count else 0
            ),
            "errors": errors,
            "error_count": len(errors),
        }


class PromptTuner:
    """프롬프트 A/B 테스트.

    현재 프롬프트와 후보 프롬프트의 정확도를 비교.

    사람이 하는 것: 프롬프트 후보 작성
    이 도구가 하는 것: 양쪽 정확도 측정 + 비교 보고서

    Swarm이 하는 것:
    - 오류 패턴 분석 → 프롬프트 후보 자동 생성
    - "holder 인식이 약하다" → "Pay extra attention to the 7 holder slots"
      같은 힌트를 자동 추가
    """

    def __init__(
        self,
        reference_db: ReferenceDB,
        images_dir: Path,
    ):
        self.ref_db = reference_db
        self.images_dir = images_dir

    def compare_prompts(
        self,
        prompt_a: str,
        prompt_b: str,
        sample_count: int = 10,
    ) -> dict:
        """두 프롬프트의 정확도 비교.

        비용이 높으므로 sample_count개만 테스트.

        Returns: {
            "prompt_a_accuracy": 0.85,
            "prompt_b_accuracy": 0.90,
            "winner": "b",
            "details": [...]
        }
        """
        # 샘플 선택
        all_files = list(self.ref_db.get_all().keys())[:sample_count]

        results_a = []
        results_b = []

        for filename in all_files:
            img_path = self.images_dir / filename
            if not img_path.exists():
                continue

            ground_truth = self.ref_db.get_label(filename)

            # Prompt A
            perc_a = Perception()
            perc_a._PROMPT = prompt_a
            result_a = perc_a.perceive(img_path)
            results_a.append(result_a.screen_type == ground_truth["screen_type"])

            # Prompt B
            perc_b = Perception()
            perc_b._PROMPT = prompt_b
            result_b = perc_b.perceive(img_path)
            results_b.append(result_b.screen_type == ground_truth["screen_type"])

        acc_a = sum(results_a) / len(results_a) if results_a else 0
        acc_b = sum(results_b) / len(results_b) if results_b else 0

        return {
            "prompt_a_accuracy": round(acc_a, 3),
            "prompt_b_accuracy": round(acc_b, 3),
            "winner": "a" if acc_a > acc_b else "b" if acc_b > acc_a else "tie",
            "sample_count": len(all_files),
        }

    def suggest_prompt_improvements(self, eval_result: dict) -> List[str]:
        """평가 결과에서 프롬프트 개선 힌트 자동 생성.

        Swarm의 Analyst Agent가 호출.
        """
        suggestions = []

        for error in eval_result.get("errors", []):
            field = error["field"]
            expected = error["expected"]
            got = error["got"]

            if field == "screen_type":
                if expected == "lobby" and got == "unknown":
                    suggestions.append(
                        "Add hint: 'lobby screen has a large Level N button "
                        "at bottom and a car character in center'"
                    )
                elif expected.startswith("lobby_") and got == "popup":
                    suggestions.append(
                        f"Add hint: '{expected} has specific event name "
                        f"like {expected.replace('lobby_', '').title()} in header'"
                    )
                elif expected == "gameplay" and got == "unknown":
                    suggestions.append(
                        "Add hint: 'gameplay screen has a parking lot with "
                        "colored 3D cars and a holder strip at bottom'"
                    )

            elif field == "holder":
                suggestions.append(
                    "Add hint: 'Read holder slots very carefully left to right. "
                    "Each slot contains one car color or is empty'"
                )

            elif field == "car_count":
                suggestions.append(
                    "Add hint: 'Only count cars whose cartoon EYES are fully visible. "
                    "Partially hidden cars should NOT be counted'"
                )

        # 중복 제거
        return list(dict.fromkeys(suggestions))
