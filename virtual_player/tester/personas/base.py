"""
PlayerProfile — 플레이어 페르소나 정의
========================================
AI가 "어떤 유형의 플레이어처럼" 행동할지 결정하는 파라미터.

2축 페르소나 시스템:
  축 1: 과금 성향 (F2P ↔ Whale)
  축 2: 스킬/지능 (멍청 ↔ 똑똑, 초보 ↔ 숙련)

스킬 파라미터가 Decision 레이어의 행동을 직접 변화시킨다:
  - 멍청한 플레이어: 랜덤 탭, 위험 무시, 부스터 낭비
  - 똑똑한 플레이어: 최적 순서, 수 읽기, 부스터 절약
  - 초보 플레이어: 느린 반응, 튜토리얼 따라감, 실수 많음
  - 숙련 플레이어: 빠른 판단, UI 스킵, 효율적 동선
"""

from dataclasses import dataclass, field
from typing import List
import random


@dataclass
class PlayerProfile:
    """플레이어 성향 프로필.

    Playbook의 임계값을 오버라이드하여 플레이 스타일을 조절.
    """

    persona_id: str              # casual_f2p, smart_veteran, dumb_newbie, ...
    persona_name: str            # "Smart Veteran Player"

    # ===== 세션 행동 =====
    session_duration_min: int = 10      # 평균 세션 길이 (분)
    sessions_per_day: int = 3           # 하루 접속 횟수
    retry_on_fail: int = 1              # 실패 시 재도전 횟수

    # ===== 리스크 허용도 =====
    holder_worry_at: int = 4            # 불안 시작 지점
    holder_use_booster_at: int = 5      # 부스터 사용 지점
    holder_panic_at: int = 6            # 즉시 Undo 지점

    # ===== 과금 성향 =====
    will_purchase: bool = False         # 과금 의향
    watch_ads: bool = True              # 광고 시청 여부
    max_ads_per_session: int = 3        # 세션당 최대 광고

    # ===== 플레이 스킬 (핵심 차별화) =====
    look_ahead_turns: int = 1           # 몇 수 앞을 보는가 (0=안 봄, 3=고수)
    tap_precision_px: int = 30          # 탭 오차 범위 (0=정확, 50=부정확)
    decision_speed_sec: float = 1.5     # 판단 소요 시간 (0.5=빠름, 5.0=느림)

    # ===== 지능/전략 수준 (0.0~1.0) =====
    intelligence: float = 0.5
    # 0.0: 완전 멍청 — 랜덤 탭, 규칙 무시, 위험 인식 불가
    # 0.3: 약간 멍청 — 가끔 맞는 선택, 자주 실수
    # 0.5: 보통 — 기본 규칙 따름, 가끔 실수
    # 0.7: 똑똑 — 우선순위 정확, 실수 적음
    # 1.0: 천재 — 항상 최적 선택, 수 읽기 완벽

    # ===== 숙련도 (0.0~1.0) =====
    familiarity: float = 0.5
    # 0.0: 완전 초보 — UI 헤매기, 튜토리얼 필요, 느린 반응
    # 0.3: 초보 — 기본 UI는 알지만 실수 잦음
    # 0.5: 보통 — 메뉴 탐색 가능, 가끔 헤맴
    # 0.7: 익숙 — UI 빠르게 탐색, 팝업 즉시 닫기
    # 1.0: 베테랑 — 최적 동선, 불필요 화면 스킵, 즉각 반응

    # ===== 실수율 (0.0~1.0) =====
    mistake_rate: float = 0.1
    # 0.0: 실수 안 함
    # 0.1: 10% 확률로 잘못된 위치 탭
    # 0.3: 30% 확률로 실수 (초보 수준)
    # 0.5: 50% 확률로 실수 (멍청한 플레이어)

    # ===== 탐색 성향 (0.0~1.0) =====
    exploration_tendency: float = 0.3
    # 0.0: 알려진 경로만 따름 (로봇적)
    # 0.3: 가끔 새로운 버튼 탭 (보통 유저)
    # 0.7: 자주 메뉴 탐색, 상점 방문 (호기심 많은 유저)
    # 1.0: 모든 버튼 다 눌러봄 (테스터/초보)

    # ===== 인내심 (0.0~1.0) =====
    patience: float = 0.5
    # 0.0: 즉시 포기, 1초라도 로딩되면 나감
    # 0.3: 실패 2~3번이면 나감
    # 0.5: 적당히 재시도
    # 0.7: 꽤 참을성 있음
    # 1.0: 무한 재시도 (봇)

    # ===== 부스터 성향 =====
    booster_save_tendency: float = 0.5  # 0=즉시 사용, 1=끝까지 아낌

    # ===== 이탈 조건 =====
    quit_after_consecutive_fails: int = 3   # 연속 실패 시 이탈
    quit_after_minutes: int = 30            # 최대 플레이 시간

    # ===== 행동 수정 메서드 =====

    def should_make_mistake(self) -> bool:
        """이번 탭에서 실수할지 결정."""
        return random.random() < self.mistake_rate

    def jitter_tap(self, x: int, y: int) -> tuple:
        """탭 좌표에 사람같은 오차 추가."""
        if self.tap_precision_px == 0:
            return (x, y)
        jx = x + random.randint(-self.tap_precision_px, self.tap_precision_px)
        jy = y + random.randint(-self.tap_precision_px, self.tap_precision_px)
        return (max(0, jx), max(0, jy))

    def should_explore(self) -> bool:
        """이번 턴에 탐색 행동을 할지 결정."""
        return random.random() < self.exploration_tendency

    def get_reaction_delay(self) -> float:
        """사람같은 반응 지연 시간 (초)."""
        base = self.decision_speed_sec
        # 익숙할수록 빠름
        familiarity_bonus = self.familiarity * base * 0.5
        # 랜덤 변동 ±30%
        jitter = base * random.uniform(-0.3, 0.3)
        return max(0.2, base - familiarity_bonus + jitter)

    def should_use_booster(self, danger_level: float) -> bool:
        """부스터 사용 판단.

        danger_level: 0.0(안전) ~ 1.0(위험)
        똑똑한 플레이어: 위험할 때만 사용
        멍청한 플레이어: 랜덤하게 사용 or 안 사용
        """
        if self.intelligence < 0.3:
            # 멍청: 50% 확률로 무시, 50% 확률로 필요 없을 때 사용
            return random.random() < 0.3
        threshold = 1.0 - self.intelligence  # 똑똑할수록 낮은 위험에서도 정확 판단
        return danger_level > (threshold * self.booster_save_tendency)

    def should_quit(self, consecutive_fails: int, minutes_played: float) -> bool:
        """이탈 판단."""
        if minutes_played > self.quit_after_minutes:
            return True
        # 인내심에 따라 확률적 이탈
        if consecutive_fails >= self.quit_after_consecutive_fails:
            quit_prob = 1.0 - self.patience
            return random.random() < quit_prob
        return False

    def get_priority_override(self) -> str:
        """지능에 따른 Decision 우선순위 모드.

        Returns:
            "optimal"  — P1→P2→P3 순서 정확히 따름
            "decent"   — 대체로 따르지만 가끔 P3 먼저
            "random"   — 우선순위 무시, 눈에 보이는 것 탭
            "worst"    — 의도적으로 나쁜 선택 (위험한 것 먼저)
        """
        if self.intelligence >= 0.8:
            return "optimal"
        elif self.intelligence >= 0.5:
            return "decent"
        elif self.intelligence >= 0.2:
            return "random"
        else:
            return "worst"

    def apply_to_playbook(self, playbook) -> None:
        """Playbook의 임계값을 이 페르소나에 맞게 조절."""
        playbook.holder_warning = self.holder_worry_at
        playbook.holder_danger = self.holder_use_booster_at
        playbook.holder_critical = self.holder_panic_at
        playbook.max_consecutive_fails = self.quit_after_consecutive_fails
