"""
Reflector — 실패 반성 + 자기 개선 모듈
=========================================
Reflexion(Shinn et al., 2023) 논문의 핵심 개념 적용:
"에이전트가 실패를 자연어로 반성하고, 그 반성을 다음 시도에 활용"

기존 시스템과의 차이:
  Memory(Layer 2): "실패 탭 좌표 5개 기억" → 단순 좌표 회피
  Reflector: "왜 실패했는지 분석하고, 무엇을 바꿔야 하는지 기록"
            → 다음 사이클에서 같은 실수를 구조적으로 방지

Reflection 저장 형식:
{
  "reflections": [
    {
      "session": "20260306_100000",
      "situation": "popup 화면에서 X 좌표 (970,180) 탭 시도",
      "outcome": "10회 연속 실패, 팝업 탈출 불가",
      "analysis": "이 팝업의 X 버튼은 (885,340)에 있음. (970,180)은 빈 영역",
      "lesson": "lobby_punchout 화면의 X 좌표를 (885,340)으로 수정해야 함",
      "applied": true
    }
  ]
}
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class Reflector:
    """실패 반성 + 교훈 축적.

    Reflexion 논문의 핵심:
    1. 시도 (attempt)
    2. 결과 관찰 (observe)
    3. 반성 (reflect) — "왜 실패했는가?"
    4. 교훈 저장 (store lesson)
    5. 다음 시도에 교훈 적용 (apply)
    """

    def __init__(self, reflections_path: Path):
        self.path = reflections_path
        self._reflections: List[dict] = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self._reflections = data.get("reflections", [])
            except (json.JSONDecodeError, Exception):
                pass

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"reflections": self._reflections[-200:]}
        self.path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add_reflection(
        self,
        situation: str,
        outcome: str,
        analysis: str,
        lesson: str,
    ):
        """새 반성 추가."""
        self._reflections.append({
            "timestamp": datetime.now().isoformat(),
            "situation": situation,
            "outcome": outcome,
            "analysis": analysis,
            "lesson": lesson,
            "applied": False,
        })

    def get_relevant_lessons(self, screen_type: str, max_lessons: int = 5) -> List[str]:
        """현재 화면과 관련된 교훈 조회."""
        relevant = []
        for r in reversed(self._reflections):
            if screen_type in r.get("situation", "") or screen_type in r.get("lesson", ""):
                relevant.append(r["lesson"])
                if len(relevant) >= max_lessons:
                    break
        return relevant

    def get_unapplied_lessons(self) -> List[dict]:
        """아직 적용되지 않은 교훈 목록."""
        return [r for r in self._reflections if not r.get("applied", False)]

    def mark_applied(self, lesson_text: str):
        """교훈을 '적용됨'으로 마킹."""
        for r in self._reflections:
            if r["lesson"] == lesson_text:
                r["applied"] = True

    def generate_reflection_prompt(self, log_excerpt: str) -> str:
        """로그 일부를 기반으로 반성 프롬프트 생성.

        이 프롬프트를 Analyst Agent에게 전달하면
        자연어로 반성 내용을 생성한다.
        """
        recent_lessons = [r["lesson"] for r in self._reflections[-10:]]
        lessons_text = "\n".join(f"  - {l}" for l in recent_lessons) if recent_lessons else "  (none yet)"

        return f"""Analyze this game session log and generate reflections.

Recent log:
{log_excerpt}

Previously learned lessons:
{lessons_text}

For each failure or suboptimal behavior in the log, generate a reflection:
{{
  "situation": "what was happening",
  "outcome": "what went wrong",
  "analysis": "why it went wrong (root cause)",
  "lesson": "what to change to prevent this (be specific: file, function, value)"
}}

Return a JSON array of reflections. Focus on NEW problems, not ones already covered by previous lessons."""
