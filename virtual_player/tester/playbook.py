"""
Playbook — TO DO / TO DON'T 규칙 정의
=======================================
게임별 행동 규칙을 정의. AI 자유도를 억제하는 핵심 모듈.

Playbook = {
    판단 우선순위 (P0~P5),
    절대 금지 목록 (NEVER),
    화면별 핸들러 매핑,
    좌표 제약 범위,
}
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Action: Layer 3이 Layer 4에 전달하는 유일한 형태
# ---------------------------------------------------------------------------
@dataclass
class Action:
    """실행할 행동. Layer 3 → Layer 4 전달 단위."""
    type: str               # "tap", "undo", "magnet", "back", "wait", "relaunch"
    x: int = 0
    y: int = 0
    wait: float = 1.5       # 실행 후 대기 시간(초)
    reason: str = ""        # 왜 이 행동을 하는지 (로깅용)

    def __repr__(self):
        if self.type == "tap":
            return f"TAP({self.x},{self.y}) [{self.reason}]"
        return f"{self.type.upper()} [{self.reason}]"


# ---------------------------------------------------------------------------
# ScreenHandler: 화면별 고정 행동
# ---------------------------------------------------------------------------
@dataclass
class ScreenHandler:
    """특정 화면에서 실행할 고정 행동 시퀀스."""
    screen_type: str
    actions: List[Action]
    description: str = ""


# ---------------------------------------------------------------------------
# Playbook: 게임별 규칙 집합
# ---------------------------------------------------------------------------
@dataclass
class Playbook:
    """게임별 TO DO / TO DON'T 규칙."""

    game_id: str
    genre: str

    # 화면별 고정 핸들러 (gameplay 제외)
    screen_handlers: Dict[str, ScreenHandler] = field(default_factory=dict)

    # 게임플레이 좌표 제약
    board_region: Tuple[int, int, int, int] = (30, 250, 1050, 1300)  # x1,y1,x2,y2
    holder_region: Tuple[int, int, int, int] = (130, 1350, 950, 1450)

    # 절대 금지 좌표 영역 (NEVER tap)
    forbidden_regions: List[Tuple[int, int, int, int]] = field(default_factory=list)

    # 절대 금지 키워드 (이 텍스트가 보이면 탭 금지)
    forbidden_keywords: List[str] = field(default_factory=list)

    # 부스터 좌표
    boosters: Dict[str, Tuple[int, int]] = field(default_factory=dict)
    booster_free: Dict[str, str] = field(default_factory=dict)  # booster_name → memory 필드

    # 위험 임계값
    holder_warning: int = 4    # 이 이상이면 주의
    holder_danger: int = 5     # 이 이상이면 Undo
    holder_critical: int = 6   # 이 이상이면 즉시 Undo

    # 실패 에스컬레이션
    max_consecutive_fails: int = 3   # 이 이상 연속 실패 → Undo
    max_total_fails: int = 5         # 이 이상 총 실패 → 게임 재시작

    # 매칭 규칙
    match_count: int = 3        # 몇 개 모이면 매칭 (CarMatch=3)
    holder_slots: int = 7       # 홀더 슬롯 수

    def is_forbidden_tap(self, x: int, y: int) -> bool:
        """이 좌표가 금지 영역인지 체크."""
        for fx1, fy1, fx2, fy2 in self.forbidden_regions:
            if fx1 <= x <= fx2 and fy1 <= y <= fy2:
                return True
        return False

    def is_on_board(self, x: int, y: int) -> bool:
        """이 좌표가 보드 영역 안인지 체크."""
        bx1, by1, bx2, by2 = self.board_region
        return bx1 <= x <= bx2 and by1 <= y <= by2


# ---------------------------------------------------------------------------
# CarMatch Playbook 팩토리
# ---------------------------------------------------------------------------
def create_carmatch_playbook() -> Playbook:
    """CarMatch 전용 Playbook 생성."""

    pb = Playbook(
        game_id="carmatch",
        genre="puzzle_match",
        board_region=(30, 250, 1050, 1300),
        holder_region=(130, 1350, 950, 1450),
        forbidden_regions=[
            (0, 1730, 1080, 1920),  # 부스터 바 (Shuffle 900, Rotate 600)
        ],
        forbidden_keywords=[
            "purchase", "buy", "₩", "$", "install",
            "Add Space", "Play On",
        ],
        boosters={
            "undo":    (108, 1830),
            "magnet":  (324, 1830),
            # shuffle, rotate는 금지이므로 등록하지 않음
        },
        booster_free={
            "undo": "undo_remaining",
            "magnet": "magnet_remaining",
        },
        holder_warning=4,
        holder_danger=5,
        holder_critical=6,
        match_count=3,
        holder_slots=7,
        max_consecutive_fails=3,
        max_total_fails=5,
    )

    # 화면별 고정 핸들러 (gameplay 외)
    pb.screen_handlers = {
        "lobby": ScreenHandler("lobby", [
            Action("tap", 540, 1500, 3.0, "Level N button → start game"),
        ]),
        "win": ScreenHandler("win", [
            Action("tap", 540, 1170, 2.0, "Continue button"),
            Action("tap", 540, 1170, 1.0, "Continue (retry)"),
        ]),
        "fail_outofspace": ScreenHandler("fail_outofspace", [
            Action("tap", 970, 180, 1.5, "X close (decline Add Space 900)"),
        ]),
        "fail_continue": ScreenHandler("fail_continue", [
            Action("tap", 900, 500, 1.5, "X close (decline Play On 900)"),
        ]),
        "fail_result": ScreenHandler("fail_result", [
            Action("tap", 540, 1100, 2.0, "Try Again button"),
        ]),
        "ingame_setting": ScreenHandler("ingame_setting", [
            Action("tap", 310, 1070, 1.5, "Resume button"),
        ]),
        "ingame_quit_confirm": ScreenHandler("ingame_quit_confirm", [
            Action("tap", 880, 550, 1.5, "X close (cancel quit)"),
        ]),
        "ad": ScreenHandler("ad", [
            Action("tap", 1050, 30, 1.0, "Close ad top-right"),
            Action("tap", 30, 30, 1.0, "Close ad top-left"),
            Action("back", wait=1.0, reason="Android back"),
        ]),
        "ad_install": ScreenHandler("ad_install", [
            Action("back", wait=1.5, reason="Back from install page"),
        ]),
        "shop": ScreenHandler("shop", [
            Action("tap", 540, 1870, 2.0, "Home tab (escape shop)"),
        ]),
        "leaderboard": ScreenHandler("leaderboard", [
            Action("tap", 540, 1870, 2.0, "Home tab"),
        ]),
        "journey": ScreenHandler("journey", [
            Action("tap", 540, 1870, 2.0, "Home tab"),
        ]),
        "setting": ScreenHandler("setting", [
            Action("tap", 540, 1870, 2.0, "Home tab"),
        ]),
        "profile": ScreenHandler("profile", [
            Action("tap", 920, 110, 1.5, "X close profile"),
        ]),
        # 이벤트 팝업들 — 전부 X닫기
        "lobby_keyblaze": ScreenHandler("lobby_keyblaze", [
            Action("tap", 885, 340, 1.5, "X close Key Blaze"),
        ]),
        "lobby_streakrace": ScreenHandler("lobby_streakrace", [
            Action("tap", 910, 65, 1.5, "X close Streak Race"),
        ]),
        "lobby_dailytask": ScreenHandler("lobby_dailytask", [
            Action("tap", 910, 580, 1.5, "X close Daily Task"),
        ]),
        "lobby_skylift": ScreenHandler("lobby_skylift", [
            Action("tap", 895, 65, 1.5, "X close Sky Lift"),
        ]),
        "lobby_missiongarage": ScreenHandler("lobby_missiongarage", [
            Action("tap", 905, 60, 1.5, "X close Mission Garage"),
        ]),
        "lobby_skyrally": ScreenHandler("lobby_skyrally", [
            Action("tap", 880, 390, 1.5, "X close Sky Rally"),
        ]),
        "lobby_endlesscoast": ScreenHandler("lobby_endlesscoast", [
            Action("tap", 895, 60, 1.5, "X close Endless Coast"),
        ]),
        "lobby_punchout": ScreenHandler("lobby_punchout", [
            Action("tap", 890, 390, 1.5, "X close Punch Out"),
        ]),
        "lobby_citydeal": ScreenHandler("lobby_citydeal", [
            Action("tap", 895, 230, 1.5, "X close City Deal"),
        ]),
    }

    # info 오버레이들
    for event in ["keyblaze", "streakrace", "skylift", "missiongarage"]:
        info_key = f"lobby_{event}_info"
        pb.screen_handlers[info_key] = ScreenHandler(info_key, [
            Action("tap", 540, 1730, 1.5, f"Tap to Continue ({event} info)"),
        ])

    # unknown / popup — 에스컬레이션
    pb.screen_handlers["unknown"] = ScreenHandler("unknown", [
        Action("back", wait=1.0, reason="Back from unknown screen"),
        Action("tap", 540, 960, 1.0, "Center tap fallback"),
    ])
    pb.screen_handlers["popup"] = ScreenHandler("popup", [
        Action("tap", 970, 180, 0.5, "X close attempt 1 (top-right)"),
        Action("tap", 900, 500, 0.5, "X close attempt 2 (mid-right)"),
        Action("tap", 880, 400, 0.5, "X close attempt 3"),
        Action("back", wait=1.0, reason="Android back"),
    ])

    return pb
