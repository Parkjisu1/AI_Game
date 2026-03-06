"""
PlayerProfile — 플레이어 페르소나 정의
========================================
AI가 "어떤 유형의 플레이어처럼" 행동할지 결정하는 파라미터.

이 파라미터들이 Decision 레이어의 임계값을 조절한다:
- 보수적 플레이어: holder 4칸에서 불안 → Undo 일찍 사용
- 적극적 플레이어: holder 6칸까지 버팀 → Undo 늦게 사용
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class PlayerProfile:
    """플레이어 성향 프로필.

    Playbook의 임계값을 오버라이드하여 플레이 스타일을 조절.
    """

    persona_id: str              # casual_f2p, mid_dolphin, hardcore_whale
    persona_name: str            # "Casual F2P Player"

    # 세션 행동
    session_duration_min: int = 10      # 평균 세션 길이 (분)
    sessions_per_day: int = 3           # 하루 접속 횟수
    retry_on_fail: int = 1              # 실패 시 재도전 횟수

    # 리스크 허용도 (Playbook 임계값 오버라이드)
    holder_worry_at: int = 4            # 불안 시작 지점
    holder_use_booster_at: int = 5      # 부스터 사용 지점
    holder_panic_at: int = 6            # 즉시 Undo 지점

    # 과금 성향
    will_purchase: bool = False         # 과금 의향
    watch_ads: bool = True              # 광고 시청 여부
    max_ads_per_session: int = 3        # 세션당 최대 광고

    # 플레이 스킬
    look_ahead_turns: int = 1           # 몇 수 앞을 보는가
    tap_precision_px: int = 30          # 탭 정확도 오차 (px)
    decision_speed_sec: float = 1.5     # 판단 소요 시간

    # 부스터 성향
    booster_save_tendency: float = 0.5  # 0=즉시 사용, 1=끝까지 아낌
    # 0.0: 가능하면 바로 사용
    # 0.5: 위험할 때만 사용
    # 1.0: 정말 필요할 때만 사용

    # 이탈 조건
    quit_after_consecutive_fails: int = 3   # 연속 실패 시 이탈
    quit_after_minutes: int = 30            # 최대 플레이 시간

    def apply_to_playbook(self, playbook) -> None:
        """Playbook의 임계값을 이 페르소나에 맞게 조절."""
        playbook.holder_warning = self.holder_worry_at
        playbook.holder_danger = self.holder_use_booster_at
        playbook.holder_critical = self.holder_panic_at
        playbook.max_consecutive_fails = self.quit_after_consecutive_fails
