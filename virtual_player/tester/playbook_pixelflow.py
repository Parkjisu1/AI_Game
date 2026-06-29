"""
Playbook — Pixel Flow 전용 규칙
================================
Pixel Flow 게임 전용 TO DO / TO DON'T.

게임 핵심:
  - 보드: 색 픽셀 그리드 (2-4색)
  - 돼지: 탭하면 컨베이어 벨트 진입 → 같은 색 픽셀 섭취 → 홀더로 복귀
  - 홀더: 5칸. 꽉 차면 돼지 희생 또는 패배
  - 모든 픽셀 제거 → 승리 (40 코인)
"""

from .playbook import Action, Playbook, ScreenHandler


def create_pixelflow_playbook() -> Playbook:
    """Pixel Flow 전용 Playbook 생성."""

    pb = Playbook(
        game_id="pixelflow",
        genre="puzzle_pixel",
        # 보드 영역 (컨베이어 벨트 포함)
        board_region=(130, 150, 720, 750),
        # 홀더 영역 — 2026-03-09 verified
        holder_region=(110, 880, 780, 980),
        forbidden_regions=[
            # 상단 코인/하트/+ 버튼 영역 (실수 탭 방지)
            (0, 0, 1080, 100),
            # 코인 + 버튼 (골드 팩 열림 방지)
            (720, 50, 810, 90),
            # 하트 + 버튼
            (490, 30, 560, 80),
        ],
        forbidden_keywords=[
            "purchase", "buy", "₩", "$", "install",
            "900",  # 공간이 부족해요 (900 코인 결제)
            "KRW", "골드 팩", "Gold Pack",
        ],
        boosters={},  # Pixel Flow에는 부스터 없음 (확인 필요)
        booster_free={},
        holder_warning=3,   # 홀더 3칸 차면 주의
        holder_danger=4,    # 4칸 차면 위험
        holder_critical=5,  # 5칸 = 가득 참
        match_count=0,      # 매칭 없음 (자동 섭취)
        holder_slots=5,     # 5칸 홀더
        max_consecutive_fails=5,
        max_total_fails=3,
    )

    # 화면별 핸들러 — DB 패턴 기반: 사람은 back 안 쓰고 탭만 함
    # 모든 화면에서 돼지 영역 탭이 가장 효과적 (PlayDB 분석 결과)
    pb.screen_handlers = {
        # 로비 → 플레이 버튼
        "lobby": ScreenHandler("lobby", [
            Action("tap", 540, 1450, 3.0, "플레이 button"),
        ]),

        # 승리 → 계속하기 (하단 탭)
        "win": ScreenHandler("win", [
            Action("tap", 540, 1500, 2.0, "Continue/next tap"),
            Action("tap", 540, 1450, 1.0, "플레이 fallback"),
        ]),

        # 공간 부족 팝업 → X 닫기 (2026-04-05 verified)
        "fail_outofspace": ScreenHandler("fail_outofspace", [
            Action("tap", 825, 340, 2.0, "X close popup"),
        ]),

        # 실패 → X 닫기 + 화면 탭 (다시 도전/계속)
        "fail_result": ScreenHandler("fail_result", [
            Action("tap", 825, 340, 1.5, "X close popup"),
            Action("tap", 540, 1500, 2.0, "Retry/continue tap"),
        ]),

        "fail": ScreenHandler("fail", [
            Action("tap", 825, 340, 1.5, "X close popup"),
            Action("tap", 540, 1500, 2.0, "Retry/continue tap"),
        ]),

        # 로딩 → 대기 + 탭
        "loading": ScreenHandler("loading", [
            Action("wait", wait=3.0, reason="Loading wait"),
            Action("tap", 540, 1500, 1.0, "Continue tap"),
        ]),

        # 팝업 → 탭으로 닫기 (back 안 씀)
        "popup": ScreenHandler("popup", [
            Action("tap", 825, 340, 1.5, "X close popup"),
            Action("tap", 540, 1500, 1.0, "Center tap dismiss"),
        ]),

        # 알 수 없는 화면 → 탭
        "unknown": ScreenHandler("unknown", [
            Action("tap", 540, 1500, 1.5, "Center tap"),
        ]),

        # 광고 → 탭으로 닫기 시도
        "ad": ScreenHandler("ad", [
            Action("tap", 1030, 50, 1.5, "X close ad (top-right)"),
            Action("tap", 540, 1500, 1.0, "Center tap"),
        ]),
        "ad_install": ScreenHandler("ad_install", [
            Action("back", wait=1.5, reason="Back from install page"),
        ]),
    }

    return pb
