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

    # 화면별 고정 핸들러
    pb.screen_handlers = {
        # 로비: "플레이" 버튼 탭 — 2026-03-09 re-verified (502, 1450)
        "lobby": ScreenHandler("lobby", [
            Action("tap", 502, 1450, 3.0, "플레이 button → start level"),
        ]),

        # 승리: back 먼저 (Gold Pack 오분류 대비) → 계속하기
        "win": ScreenHandler("win", [
            Action("back", wait=1.0, reason="Back first (Gold Pack safety)"),
            Action("tap", 502, 1450, 1.0, "플레이/계속하기 button"),
            Action("tap", 540, 1830, 1.0, "Home tab fallback"),
        ]),

        # 공간 부족 (결제 유도) — X 닫기 — 2026-03-10 verified (826,495)
        "fail_outofspace": ScreenHandler("fail_outofspace", [
            Action("tap", 826, 495, 1.5, "X close (공간이 부족해요)"),
            Action("back", wait=1.0, reason="Back from outofspace"),
        ]),

        # 슬롯 가득 참 — 홀더에서 돼지 희생 (첫 번째 슬롯)
        "fail_holdfull": ScreenHandler("fail_holdfull", [
            Action("tap", 185, 930, 1.5, "Sacrifice holder pig slot 1"),
        ]),

        # 실패 결과 — X close 먼저 (outofspace dialog), 그다음 다시 도전
        "fail_result": ScreenHandler("fail_result", [
            Action("tap", 826, 495, 1.0, "X close (outofspace safety)"),
            Action("back", wait=1.0, reason="Back from fail dialog"),
            Action("tap", 537, 1198, 2.0, "다시 도전! (Retry)"),
        ]),

        # 실패 결과 (YOLO가 fail로 분류하는 경우도 포함)
        "fail": ScreenHandler("fail", [
            Action("tap", 826, 495, 1.0, "X close (outofspace)"),
            Action("back", wait=1.0, reason="Back from fail"),
            Action("tap", 537, 1198, 2.0, "다시 도전! (Retry)"),
        ]),

        # 로딩 화면 — 대기 (interactive ad / 새로운 기능 팝업이 loading으로 분류될 수 있음)
        "loading": ScreenHandler("loading", [
            Action("wait", wait=3.0, reason="Loading / ad wait..."),
            Action("tap", 539, 1577, 1.0, "계속하기 button (level-up screen)"),
            Action("back", wait=2.0, reason="Back (dismiss ad if stuck)"),
        ]),

        # 인게임 설정
        "ingame_setting": ScreenHandler("ingame_setting", [
            Action("tap", 540, 960, 1.5, "Resume / center tap"),
        ]),

        # 알 수 없는 팝업 — 에스컬레이션
        "unknown": ScreenHandler("unknown", [
            Action("back", wait=1.0, reason="Back from unknown"),
            Action("tap", 540, 1830, 1.0, "Home tab fallback"),
        ]),

        "popup": ScreenHandler("popup", [
            Action("back", wait=1.5, reason="Android back (safest dismiss)"),
            Action("tap", 497, 97, 1.0, "Gold Pack X close (top-right)"),
            Action("tap", 540, 1830, 1.0, "Home/pig tab (escape shop)"),
            Action("back", wait=1.0, reason="Android back fallback"),
        ]),

        # 광고 관련
        "ad": ScreenHandler("ad", [
            Action("back", wait=1.5, reason="Back from ad"),
        ]),
        "ad_install": ScreenHandler("ad_install", [
            Action("back", wait=1.5, reason="Back from install page"),
        ]),
    }

    return pb
