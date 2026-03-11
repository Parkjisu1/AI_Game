"""
Persona Presets — 플레이어 프리셋
==================================

2축 시스템:
  축 1 — 과금 성향: F2P, Dolphin, Whale
  축 2 — 스킬/지능: Dumb, Normal, Smart, Veteran

조합 예시:
  smart_f2p      = 똑똑하지만 무과금
  dumb_whale     = 멍청하지만 과금 많이
  newbie_curious = 초보인데 탐색 좋아함
  veteran_tired  = 숙련자인데 지침 (대충 플레이)
"""

from typing import Dict, List

from .base import PlayerProfile

# 프리셋 레지스트리
_PRESETS: Dict[str, PlayerProfile] = {}


def _register_builtins():
    """내장 프리셋 등록."""

    # =================================================================
    # 축 1: 과금 성향 기반 (기존 호환)
    # =================================================================
    _PRESETS["casual_f2p"] = PlayerProfile(
        persona_id="casual_f2p",
        persona_name="Casual F2P Player",
        session_duration_min=5,
        sessions_per_day=3,
        retry_on_fail=1,
        holder_worry_at=4,
        holder_use_booster_at=5,
        holder_panic_at=6,
        will_purchase=False,
        watch_ads=True,
        max_ads_per_session=3,
        look_ahead_turns=1,
        tap_precision_px=30,
        decision_speed_sec=2.0,
        intelligence=0.5,
        familiarity=0.4,
        mistake_rate=0.15,
        exploration_tendency=0.2,
        patience=0.4,
        booster_save_tendency=0.3,
        quit_after_consecutive_fails=3,
        quit_after_minutes=15,
    )

    _PRESETS["mid_dolphin"] = PlayerProfile(
        persona_id="mid_dolphin",
        persona_name="Mid-spending Dolphin",
        session_duration_min=15,
        sessions_per_day=5,
        retry_on_fail=3,
        holder_worry_at=4,
        holder_use_booster_at=5,
        holder_panic_at=6,
        will_purchase=True,
        watch_ads=True,
        max_ads_per_session=5,
        look_ahead_turns=2,
        tap_precision_px=20,
        decision_speed_sec=1.5,
        intelligence=0.6,
        familiarity=0.6,
        mistake_rate=0.1,
        exploration_tendency=0.3,
        patience=0.6,
        booster_save_tendency=0.5,
        quit_after_consecutive_fails=5,
        quit_after_minutes=30,
    )

    _PRESETS["hardcore_whale"] = PlayerProfile(
        persona_id="hardcore_whale",
        persona_name="Hardcore Whale",
        session_duration_min=30,
        sessions_per_day=8,
        retry_on_fail=5,
        holder_worry_at=5,
        holder_use_booster_at=6,
        holder_panic_at=7,
        will_purchase=True,
        watch_ads=False,
        max_ads_per_session=0,
        look_ahead_turns=3,
        tap_precision_px=10,
        decision_speed_sec=1.0,
        intelligence=0.7,
        familiarity=0.8,
        mistake_rate=0.05,
        exploration_tendency=0.2,
        patience=0.8,
        booster_save_tendency=0.2,
        quit_after_consecutive_fails=10,
        quit_after_minutes=60,
    )

    # =================================================================
    # 축 2: 스킬/지능 기반 (새로 추가)
    # =================================================================

    # --- 멍청한 플레이어 (Dumb) ---
    # 규칙 이해 못함, 랜덤 탭, 위험 무시, 부스터 낭비
    _PRESETS["dumb_newbie"] = PlayerProfile(
        persona_id="dumb_newbie",
        persona_name="Dumb Newbie (멍청한 초보)",
        session_duration_min=5,
        sessions_per_day=2,
        retry_on_fail=1,
        holder_worry_at=6,          # 위험해도 못 느낌
        holder_use_booster_at=7,    # 부스터 존재도 모름
        holder_panic_at=7,
        will_purchase=False,
        watch_ads=False,            # 광고 개념도 모름
        max_ads_per_session=0,
        look_ahead_turns=0,         # 수 읽기 전혀 안 함
        tap_precision_px=50,        # 탭이 매우 부정확
        decision_speed_sec=4.0,     # 뭘 할지 한참 고민
        intelligence=0.1,           # 거의 랜덤
        familiarity=0.0,            # 첫 플레이
        mistake_rate=0.5,           # 50% 실수
        exploration_tendency=0.8,   # 아무 데나 막 누름
        patience=0.2,               # 금방 포기
        booster_save_tendency=0.0,  # 부스터 보이면 바로 누름
        quit_after_consecutive_fails=2,
        quit_after_minutes=8,
    )

    # --- 멍청하지만 끈기 있는 플레이어 ---
    # 전략 없지만 꾸준히 시도, 실패해도 계속 재도전
    _PRESETS["dumb_persistent"] = PlayerProfile(
        persona_id="dumb_persistent",
        persona_name="Dumb but Persistent (멍청하지만 끈기)",
        session_duration_min=20,
        sessions_per_day=4,
        retry_on_fail=5,
        holder_worry_at=6,
        holder_use_booster_at=7,
        holder_panic_at=7,
        will_purchase=False,
        watch_ads=True,
        max_ads_per_session=5,
        look_ahead_turns=0,
        tap_precision_px=40,
        decision_speed_sec=3.0,
        intelligence=0.2,
        familiarity=0.3,
        mistake_rate=0.4,
        exploration_tendency=0.5,
        patience=0.9,               # 매우 참을성 있음
        booster_save_tendency=0.1,
        quit_after_consecutive_fails=10,
        quit_after_minutes=45,
    )

    # --- 보통 플레이어 (Normal) ---
    # 기본 규칙 이해, 가끔 실수, 적당한 속도
    _PRESETS["normal_player"] = PlayerProfile(
        persona_id="normal_player",
        persona_name="Normal Player (보통 유저)",
        session_duration_min=10,
        sessions_per_day=3,
        retry_on_fail=2,
        holder_worry_at=4,
        holder_use_booster_at=5,
        holder_panic_at=6,
        will_purchase=False,
        watch_ads=True,
        max_ads_per_session=3,
        look_ahead_turns=1,
        tap_precision_px=20,
        decision_speed_sec=2.0,
        intelligence=0.5,
        familiarity=0.5,
        mistake_rate=0.1,
        exploration_tendency=0.3,
        patience=0.5,
        booster_save_tendency=0.5,
        quit_after_consecutive_fails=4,
        quit_after_minutes=20,
    )

    # --- 똑똑한 플레이어 (Smart) ---
    # 최적 순서 판단, 수 읽기, 실수 거의 없음
    _PRESETS["smart_player"] = PlayerProfile(
        persona_id="smart_player",
        persona_name="Smart Player (똑똑한 유저)",
        session_duration_min=15,
        sessions_per_day=4,
        retry_on_fail=3,
        holder_worry_at=4,
        holder_use_booster_at=5,
        holder_panic_at=6,
        will_purchase=False,
        watch_ads=True,
        max_ads_per_session=2,
        look_ahead_turns=3,         # 3수 앞까지 봄
        tap_precision_px=10,        # 정확한 탭
        decision_speed_sec=1.0,     # 빠른 판단
        intelligence=0.85,          # 거의 최적 선택
        familiarity=0.7,
        mistake_rate=0.03,          # 실수 거의 없음
        exploration_tendency=0.15,
        patience=0.7,
        booster_save_tendency=0.7,  # 부스터 아낌
        quit_after_consecutive_fails=5,
        quit_after_minutes=30,
    )

    # --- 숙련된 베테랑 (Veteran) ---
    # UI 완벽 숙지, 최적 동선, 팝업 즉시 처리
    _PRESETS["veteran"] = PlayerProfile(
        persona_id="veteran",
        persona_name="Veteran Player (숙련 유저)",
        session_duration_min=20,
        sessions_per_day=5,
        retry_on_fail=3,
        holder_worry_at=4,
        holder_use_booster_at=5,
        holder_panic_at=6,
        will_purchase=False,
        watch_ads=False,            # 광고 안 봄 (시간 아까움)
        max_ads_per_session=0,
        look_ahead_turns=2,
        tap_precision_px=5,         # 매우 정확
        decision_speed_sec=0.5,     # 즉각 반응
        intelligence=0.75,
        familiarity=1.0,            # 완전 숙련
        mistake_rate=0.02,
        exploration_tendency=0.05,  # 알 건 다 알아서 탐색 안 함
        patience=0.6,
        booster_save_tendency=0.6,
        quit_after_consecutive_fails=5,
        quit_after_minutes=30,
    )

    # --- 안 익숙한 초보 (Unfamiliar Newbie) ---
    # 지능은 보통이지만 UI를 모름, 헤매다가 학습
    _PRESETS["unfamiliar_newbie"] = PlayerProfile(
        persona_id="unfamiliar_newbie",
        persona_name="Unfamiliar Newbie (안 익숙한 초보)",
        session_duration_min=8,
        sessions_per_day=2,
        retry_on_fail=2,
        holder_worry_at=5,
        holder_use_booster_at=6,
        holder_panic_at=6,
        will_purchase=False,
        watch_ads=True,
        max_ads_per_session=2,
        look_ahead_turns=1,
        tap_precision_px=35,
        decision_speed_sec=3.5,     # 뭘 눌러야 할지 고민
        intelligence=0.5,           # 이해력은 보통
        familiarity=0.1,            # UI 전혀 모름
        mistake_rate=0.25,          # 잘못된 버튼 자주 누름
        exploration_tendency=0.6,   # 메뉴 여기저기 누름
        patience=0.4,
        booster_save_tendency=0.3,
        quit_after_consecutive_fails=3,
        quit_after_minutes=12,
    )

    # --- 지친 숙련자 (Tired Veteran) ---
    # 다 아는데 귀찮아서 대충 플레이
    _PRESETS["tired_veteran"] = PlayerProfile(
        persona_id="tired_veteran",
        persona_name="Tired Veteran (지친 숙련자)",
        session_duration_min=5,
        sessions_per_day=2,
        retry_on_fail=1,
        holder_worry_at=5,
        holder_use_booster_at=6,
        holder_panic_at=7,          # 위험해도 귀찮아서 무시
        will_purchase=False,
        watch_ads=False,
        max_ads_per_session=0,
        look_ahead_turns=1,         # 아는데 안 봄
        tap_precision_px=25,        # 대충 탭
        decision_speed_sec=1.5,
        intelligence=0.7,           # 알긴 아는데
        familiarity=0.9,            # UI는 잘 앎
        mistake_rate=0.15,          # 귀찮아서 실수
        exploration_tendency=0.05,  # 새로운 거 관심 없음
        patience=0.15,              # 금방 나감
        booster_save_tendency=0.1,  # 귀찮으니 바로 사용
        quit_after_consecutive_fails=2,
        quit_after_minutes=8,
    )

    # --- 호기심 많은 탐험가 ---
    # 게임 클리어보다 구석구석 탐색에 관심
    _PRESETS["curious_explorer"] = PlayerProfile(
        persona_id="curious_explorer",
        persona_name="Curious Explorer (호기심 탐험가)",
        session_duration_min=15,
        sessions_per_day=3,
        retry_on_fail=1,
        holder_worry_at=4,
        holder_use_booster_at=5,
        holder_panic_at=6,
        will_purchase=False,
        watch_ads=True,
        max_ads_per_session=3,
        look_ahead_turns=1,
        tap_precision_px=20,
        decision_speed_sec=2.5,     # 화면 구경하느라 느림
        intelligence=0.5,
        familiarity=0.3,
        mistake_rate=0.1,
        exploration_tendency=0.9,   # 모든 메뉴, 버튼 탐색
        patience=0.7,               # 탐색이 재밌으니 오래 함
        booster_save_tendency=0.5,
        quit_after_consecutive_fails=4,
        quit_after_minutes=25,
    )

    # =================================================================
    # 특수 목적
    # =================================================================

    # --- 자동 테스터 봇 (기존 호환) ---
    _PRESETS["tester_bot"] = PlayerProfile(
        persona_id="tester_bot",
        persona_name="Automated Tester (no quit, max endurance)",
        session_duration_min=540,
        sessions_per_day=1,
        retry_on_fail=999,
        holder_worry_at=4,
        holder_use_booster_at=5,
        holder_panic_at=6,
        will_purchase=False,
        watch_ads=False,
        max_ads_per_session=0,
        look_ahead_turns=1,
        tap_precision_px=0,
        decision_speed_sec=0.0,
        intelligence=0.5,
        familiarity=0.5,
        mistake_rate=0.0,
        exploration_tendency=0.0,
        patience=1.0,
        booster_save_tendency=0.5,
        quit_after_consecutive_fails=999,
        quit_after_minutes=999,
    )

    # --- 스트레스 테스터 (최악의 행동) ---
    # 의도적으로 나쁜 선택, 에지 케이스 발견용
    _PRESETS["stress_tester"] = PlayerProfile(
        persona_id="stress_tester",
        persona_name="Stress Tester (최악의 행동으로 버그 탐색)",
        session_duration_min=30,
        sessions_per_day=1,
        retry_on_fail=999,
        holder_worry_at=7,          # 위험 완전 무시
        holder_use_booster_at=7,
        holder_panic_at=7,
        will_purchase=False,
        watch_ads=False,
        max_ads_per_session=0,
        look_ahead_turns=0,
        tap_precision_px=60,        # 일부러 부정확
        decision_speed_sec=0.3,     # 매우 빠른 연타
        intelligence=0.0,           # 최악의 선택
        familiarity=0.0,
        mistake_rate=0.7,           # 70% 실수
        exploration_tendency=1.0,   # 모든 곳 탭
        patience=1.0,               # 절대 안 나감
        booster_save_tendency=0.0,  # 보이는 거 다 누름
        quit_after_consecutive_fails=999,
        quit_after_minutes=999,
    )


def load_persona(persona_id: str) -> PlayerProfile:
    """프리셋 ID로 PlayerProfile 로드."""
    if not _PRESETS:
        _register_builtins()

    profile = _PRESETS.get(persona_id)
    if profile is None:
        raise ValueError(
            f"Unknown persona: {persona_id}. "
            f"Available: {list(_PRESETS.keys())}"
        )
    return profile


def list_personas() -> List[str]:
    """등록된 페르소나 목록."""
    if not _PRESETS:
        _register_builtins()
    return list(_PRESETS.keys())
