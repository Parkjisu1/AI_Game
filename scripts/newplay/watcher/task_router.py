"""task_router.py — NewPlay 라우팅.

projecthub_watcher.py 가 요구하는 인터페이스만 맞춘다:
    route_task(task, context) -> {"action", "reason", "stage", "params", "auto_execute"}

실제 팀 분류(dev/data/design/chat)는 LLM(Translator)이 하므로 여기서는
"실행 가능한가"만 결정한다. 키워드로 팀을 추측하지 않는다 —
게임팀에서 설명에 섞인 hex 문자열이 'db' 로 오탐돼 엉뚱한 파이프라인을 탄 전례가 있다.
"""
from __future__ import annotations

from typing import Any

# hermes_stopped 로 중단된 태스크는 손대지 않는다.
def route_task(task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if task.get("hermes_stopped"):
        return {
            "action": "skip",
            "reason": "hermes_stopped=true — 사용자가 중단시킨 태스크",
            "stage": 0,
            "params": {},
            "auto_execute": False,
        }

    # 사용자가 팀을 손으로 지정했으면 그대로 존중한다(team_override).
    team = str(task.get("team") or "").lower()
    if task.get("team_override") and team:
        return {
            "action": "team_pipeline",
            "reason": f"사용자 수동 배정: {team}",
            "stage": 1,
            "params": {"team": team, "override": True},
            "auto_execute": True,
        }

    return {
        "action": "team_pipeline",
        "reason": "Translator 가 팀을 판정한다",
        "stage": 1,
        "params": {},
        "auto_execute": True,
    }
