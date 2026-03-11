"""
Phase 2: Generic Decision Engine
==================================
범용 의사결정 엔진. 게임별 하드코딩 없이 동작.

전략:
  - P0: UI 네비게이션 (popup/ad/fail/lobby) → 규칙 기반 (빠름, 무료)
  - P1: Gameplay → LLM 판단 (스크린샷 + 상황 설명 → 행동 선택)
  - Fallback: 텍스트 기반 버튼 탐색

LLM은 gameplay 상태에서만 호출 → 비용 최소화.
"""

import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .playbook import Action, Playbook
from .perception import BoardState
from .memory import GameMemory
from .universal_vision import UIState, UniversalVision, ScreenClassifier

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False


class GenericDecision:
    """범용 의사결정 엔진.

    게임별 decision 파일 없이 작동.
    UI 네비게이션은 규칙, gameplay는 LLM.
    """

    def __init__(
        self,
        playbook: Optional[Playbook] = None,
        genre_profile=None,
        vision: Optional[UniversalVision] = None,
        llm_model: str = "claude-haiku-4-5-20251001",
        enable_llm: bool = True,
    ):
        self.playbook = playbook
        self.genre = genre_profile
        self.vision = vision or UniversalVision()
        self.classifier = ScreenClassifier()
        self.llm_model = llm_model
        self.enable_llm = enable_llm
        self._llm_client = None
        self._screenshot_path: Optional[Path] = None
        self._ui_state: Optional[UIState] = None
        self._llm_calls = 0
        self._rule_calls = 0

    def set_screenshot(self, path: Path):
        """현재 스크린샷 경로 설정."""
        self._screenshot_path = path
        self._ui_state = None  # 캐시 무효화

    def _get_ui_state(self) -> Optional[UIState]:
        """UI 상태 캐시 반환/갱신."""
        if self._ui_state is None and self._screenshot_path:
            self._ui_state = self.vision.analyze(self._screenshot_path)
        return self._ui_state

    def decide(self, board: BoardState, memory: GameMemory) -> List[Action]:
        """현재 상태 → 실행할 Action 리스트.

        P0: 하트 대기 → 대기
        P1: 비-gameplay 화면 → 규칙 기반 UI 네비게이션
        P2: gameplay → Playbook 핸들러 (있으면)
        P3: gameplay → LLM 판단 (Playbook 없으면)
        P4: fallback → OCR 기반 버튼 탐색
        """
        screen = board.screen_type

        # P0: 하트 대기
        if memory.is_heart_waiting():
            remaining = int(memory.heart_wait_until - time.time())
            return [Action("wait", wait=30.0,
                           reason=f"Hearts wait: {remaining}s remaining")]

        # P1: 비-gameplay → 규칙 기반 네비게이션
        if screen != "gameplay":
            return self._handle_navigation(board, memory)

        # P2: gameplay + Playbook 핸들러 존재 → Playbook 사용
        if self.playbook:
            handler = self.playbook.screen_handlers.get("gameplay")
            if handler:
                return handler.actions[:]

        # P3: gameplay → LLM 판단
        if self.enable_llm and self._screenshot_path:
            actions = self._llm_decide(board, memory)
            if actions:
                return actions

        # P4: fallback → OCR 기반 범용 탭
        return self._fallback_decide(board, memory)

    # -----------------------------------------------------------------------
    # P1: UI Navigation (규칙 기반)
    # -----------------------------------------------------------------------
    def _handle_navigation(self, board: BoardState, memory: GameMemory) -> List[Action]:
        """비-gameplay 화면 처리. 규칙 + OCR 조합."""
        screen = board.screen_type
        self._rule_calls += 1

        # Playbook 핸들러 존재하면 우선 사용
        if self.playbook:
            handler = self.playbook.screen_handlers.get(screen)
            if handler:
                if screen == "lobby":
                    memory.on_game_start()
                return handler.actions[:]

        # Playbook 없을 때 → OCR 기반 범용 처리
        ui = self._get_ui_state()
        if ui is None:
            return [Action("back", wait=1.0, reason=f"No UI data for {screen}")]

        # lobby → Play/Start 버튼 찾기
        if screen == "lobby":
            memory.on_game_start()
            return self._find_and_tap_button(
                ui, ["play", "start", "시작", "level", "레벨", "stage"],
                fallback_reason="lobby: no play button found"
            )

        # win → Continue 버튼
        if screen == "win":
            return self._find_and_tap_button(
                ui, ["continue", "next", "계속", "다음", "ok", "확인"],
                fallback_reason="win: no continue button"
            )

        # fail → Retry 버튼
        if screen.startswith("fail"):
            memory.on_popup()
            return self._find_and_tap_button(
                ui, ["retry", "try again", "다시", "도전", "again"],
                fallback_reason="fail: no retry button"
            )

        # ad → X 닫기 시도
        if screen == "ad":
            memory.on_popup()
            return self._handle_ad(ui, memory)

        # popup → X 닫기 또는 OK
        if screen in ("popup", "unknown"):
            memory.on_popup()
            # relaunch 에스컬레이션
            if memory.popup_escape_attempts >= 15:
                memory.popup_escape_attempts = 0
                return [Action("relaunch", wait=5.0,
                               reason=f"Stuck on {screen} ({memory.popup_escape_attempts} attempts)")]
            return self._handle_popup(ui)

        # shop → 홈/뒤로
        if screen in ("shop", "store"):
            return self._find_and_tap_button(
                ui, ["home", "back", "홈", "뒤로", "close", "닫기"],
                fallback_action=Action("back", wait=1.0, reason="shop: back fallback")
            )

        # 기타 미등록 화면
        return [Action("back", wait=1.0, reason=f"Unknown screen: {screen}")]

    def _find_and_tap_button(
        self,
        ui: UIState,
        keywords: List[str],
        fallback_reason: str = "button not found",
        fallback_action: Optional[Action] = None,
    ) -> List[Action]:
        """OCR 텍스트에서 키워드 매칭 → 버튼 탭."""
        # 위험 키워드 필터
        forbidden = UniversalVision.FORBIDDEN_KEYWORDS

        for kw in keywords:
            # 버튼 영역에서 찾기
            btn = ui.find_button_with_text(kw)
            if btn and not any(f in btn.text.lower() for f in forbidden):
                return [Action("tap", btn.cx, btn.cy, 2.0,
                               f"Button: '{btn.text}' at ({btn.cx},{btn.cy})")]

            # 텍스트에서 찾기
            text = ui.find_text(kw)
            if text and not any(f in text.text.lower() for f in forbidden):
                return [Action("tap", text.x, text.y, 2.0,
                               f"Text: '{text.text}' at ({text.x},{text.y})")]

        if fallback_action:
            return [fallback_action]

        return [Action("back", wait=1.0, reason=fallback_reason)]

    def _handle_ad(self, ui: UIState, memory: GameMemory) -> List[Action]:
        """광고 처리: X 닫기 버튼 탐색."""
        attempts = memory.popup_escape_attempts

        # X 닫기 버튼이 OCR/Contour로 감지되면 사용
        if ui.close_buttons:
            best_x = ui.close_buttons[0]
            return [Action("tap", best_x.cx, best_x.cy, 1.0,
                           f"Ad close X at ({best_x.cx},{best_x.cy})")]

        if attempts <= 3:
            # Phase 1: 대기 후 back
            return [
                Action("wait", wait=5.0, reason=f"Ad wait (attempt {attempts})"),
                Action("back", wait=1.0, reason="Ad: try BACK"),
            ]
        elif attempts <= 8:
            # Phase 2: 일반적인 X 위치 스캔
            x_positions = [
                (1050, 30), (1040, 60), (1050, 100),
                (30, 30), (50, 60),
                (1020, 150), (30, 100),
            ]
            idx = ((attempts - 4) * 2) % len(x_positions)
            p1 = x_positions[idx]
            p2 = x_positions[(idx + 1) % len(x_positions)]
            return [
                Action("wait", wait=3.0, reason=f"Ad X scan (attempt {attempts})"),
                Action("tap", p1[0], p1[1], 0.5, f"Ad X: pos{idx}"),
                Action("tap", p2[0], p2[1], 0.5, f"Ad X: pos{idx+1}"),
                Action("back", wait=1.0, reason="Ad: BACK fallback"),
            ]
        else:
            memory.popup_escape_attempts = 0
            return [Action("relaunch", wait=5.0,
                           reason=f"Ad stuck after {attempts} attempts")]

    def _handle_popup(self, ui: UIState) -> List[Action]:
        """팝업 처리: X 닫기 또는 OK/확인."""
        # X 닫기 버튼
        if ui.close_buttons:
            best_x = ui.close_buttons[0]
            return [Action("tap", best_x.cx, best_x.cy, 1.0,
                           f"Popup close X at ({best_x.cx},{best_x.cy})")]

        # OK/확인/닫기 버튼
        actions = self._find_and_tap_button(
            ui, ["ok", "confirm", "close", "확인", "닫기", "cancel", "취소"],
            fallback_action=Action("back", wait=1.0, reason="popup: back fallback"),
        )
        return actions

    # -----------------------------------------------------------------------
    # P3: LLM Gameplay Decision
    # -----------------------------------------------------------------------
    def _get_llm_client(self):
        """LLM 클라이언트 lazy init."""
        if self._llm_client is None and _HAS_ANTHROPIC:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key.startswith("sk-ant-"):
                self._llm_client = anthropic.Anthropic(api_key=api_key)
        return self._llm_client

    def _llm_decide(self, board: BoardState, memory: GameMemory) -> Optional[List[Action]]:
        """LLM에게 gameplay 판단 요청."""
        client = self._get_llm_client()
        if client is None:
            return None

        import base64
        img_path = self._screenshot_path
        if not img_path or not img_path.exists():
            return None

        try:
            img_bytes = img_path.read_bytes()
            img_b64 = base64.b64encode(img_bytes).decode("ascii")
            suffix = img_path.suffix.lower()
            media_type = {
                ".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
            }.get(suffix, "image/png")

            # 장르 힌트
            genre_hint = ""
            if self.genre:
                genre_hint = f"\nGame genre: {self.genre.genre_name}\n"
                genre_hint += f"Never do: {', '.join(self.genre.never_do[:3])}\n"
                genre_hint += f"Always do: {', '.join(self.genre.always_do[:3])}\n"

            prompt = f"""You are playing a mobile game. Look at this screenshot and decide what to tap.
{genre_hint}
Current state:
- Screen: {board.screen_type}
- Holder count: {board.holder_count}/{self.playbook.holder_slots if self.playbook else '?'}

Return ONLY JSON:
{{"actions": [{{"type": "tap", "x": <int>, "y": <int>, "reason": "<why>"}}]}}

Rules:
- Coordinates are in the original image resolution (1080x1920)
- NEVER tap purchase/buy/install buttons
- Prefer gameplay-advancing actions (clear board, match colors, deploy units)
- If unsure, tap the most prominent interactive element
- Maximum 2 actions per response"""

            response = client.messages.create(
                model=self.llm_model,
                max_tokens=256,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64", "media_type": media_type, "data": img_b64}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )

            raw = response.content[0].text
            self._llm_calls += 1

            # JSON 파싱
            start = raw.find("{")
            end = raw.rfind("}")
            if start < 0 or end <= start:
                return None

            data = json.loads(raw[start:end+1])
            actions_data = data.get("actions", [])

            actions = []
            for a in actions_data[:2]:
                atype = a.get("type", "tap")
                x = int(a.get("x", 540))
                y = int(a.get("y", 960))
                reason = a.get("reason", "LLM decision")

                # 안전 체크
                if self.playbook and self.playbook.is_forbidden_tap(x, y):
                    continue

                actions.append(Action(atype, x, y, 2.0, f"LLM: {reason}"))

            return actions if actions else None

        except Exception:
            return None

    # -----------------------------------------------------------------------
    # P4: Fallback
    # -----------------------------------------------------------------------
    def _fallback_decide(self, board: BoardState, memory: GameMemory) -> List[Action]:
        """OCR 기반 범용 폴백."""
        ui = self._get_ui_state()

        if ui and ui.buttons:
            # 가장 큰 버튼 (보통 메인 액션)
            biggest = max(ui.buttons, key=lambda b: b.width * b.height)
            # 금지 키워드 확인
            if not any(f in biggest.text.lower() for f in UniversalVision.FORBIDDEN_KEYWORDS):
                return [Action("tap", biggest.cx, biggest.cy, 2.0,
                               f"Fallback: biggest button '{biggest.text}'")]

        # 화면 중앙 탭
        return [Action("tap", 540, 960, 2.0, "Fallback: center tap")]

    # -----------------------------------------------------------------------
    # Stats
    # -----------------------------------------------------------------------
    @property
    def stats(self) -> Dict[str, int]:
        return {
            "llm_calls": self._llm_calls,
            "rule_calls": self._rule_calls,
        }

    def reset(self):
        """새 게임 시작 시 리셋."""
        self._screenshot_path = None
        self._ui_state = None
