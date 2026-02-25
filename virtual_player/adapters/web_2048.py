"""
2048 Web Adapter
=================
Playwright로 2048game.com 접속, DOM에서 보드 읽기, 키보드 입력.
"""

import asyncio
from typing import Any, Dict, List, Optional

from .base import GameAdapter
from ..brain.base import TouchInput, ActionType


# ============================================================
# Constants
# ============================================================

GAME_URL = "https://2048game.com/"

# JavaScript to extract board state from DOM tile elements.
# Each .tile has CSS classes like "tile-2 tile-position-1-3" where
# position is (col, row) 1-indexed.
JS_GET_BOARD = r"""() => {
    const board = [[0,0,0,0],[0,0,0,0],[0,0,0,0],[0,0,0,0]];
    document.querySelectorAll('.tile').forEach(tile => {
        const cls = tile.className;
        const valMatch = cls.match(/\btile-(\d+)\b/);
        const posMatch = cls.match(/\btile-position-(\d+)-(\d+)\b/);
        if (valMatch && posMatch) {
            const value = parseInt(valMatch[1]);
            const col = parseInt(posMatch[1]) - 1;
            const row = parseInt(posMatch[2]) - 1;
            if (row >= 0 && row < 4 && col >= 0 && col < 4) {
                board[row][col] = Math.max(board[row][col], value);
            }
        }
    });
    const scoreEl = document.querySelector('.score-container');
    const score = scoreEl ? parseInt(scoreEl.textContent) || 0 : 0;
    const isOver = !!document.querySelector('.game-over');
    return { grid: board, score: score, over: isOver };
}"""

# Key mapping
KEY_MAP = {
    "ArrowUp": "ArrowUp",
    "ArrowDown": "ArrowDown",
    "ArrowLeft": "ArrowLeft",
    "ArrowRight": "ArrowRight",
}


# ============================================================
# Adapter implementation
# ============================================================

class Web2048Adapter(GameAdapter):
    """Playwright 기반 2048 웹 게임 어댑터."""

    def __init__(self, user_agent: str = "", device_profile: Optional[Dict] = None):
        super().__init__(user_agent=user_agent, device_profile=device_profile)
        self._playwright = None
        self._browser = None
        self._page = None

    async def connect(self) -> None:
        """브라우저 실행 및 게임 페이지 접속."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        # Browser launch options
        launch_args = ["--disable-blink-features=AutomationControlled"]
        self._browser = await self._playwright.chromium.launch(
            headless=False, args=launch_args,
        )

        # Use a desktop viewport and UA for reliable rendering.
        # 2048game.com collapses the game board under mobile UAs.
        context_opts = {
            "viewport": {"width": 600, "height": 800},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.6261.64 Safari/537.36"
            ),
        }

        context = await self._browser.new_context(**context_opts)
        self._page = await context.new_page()

        # Navigate to game
        await self._page.goto(GAME_URL, wait_until="domcontentloaded", timeout=60000)

        # Wait for game DOM to be attached (may be hidden behind consent/ad overlays)
        await self._page.wait_for_selector(".tile-container", state="attached", timeout=15000)

        # Dismiss cookie consent if present
        for consent_sel in [
            "button:has-text('Accept')", "button:has-text('Agree')",
            "button:has-text('OK')", ".fc-cta-consent", ".qc-cta-button",
            "[aria-label='Consent']",
        ]:
            try:
                btn = self._page.locator(consent_sel).first
                if await btn.is_visible(timeout=2000):
                    await btn.click()
                    await asyncio.sleep(0.5)
                    break
            except Exception:
                continue

        # Click on the game area to ensure keyboard focus
        try:
            game_container = self._page.locator(".game-container")
            await game_container.click(timeout=3000)
        except Exception:
            # Fallback: click center of page
            await self._page.mouse.click(300, 400)

        self._connected = True

    async def get_game_state(self) -> Any:
        """현재 보드 상태를 DOM에서 읽기."""
        if not self._page:
            return None

        try:
            return await self._page.evaluate(JS_GET_BOARD)
        except Exception as e:
            return {
                "grid": [[0] * 4 for _ in range(4)],
                "score": 0,
                "over": True,
                "error": str(e),
            }

    async def send_input(self, inputs: List[TouchInput]) -> None:
        """키보드 입력 전송."""
        if not self._page:
            return

        for touch in inputs:
            if touch.action_type == ActionType.KEY_PRESS:
                key = KEY_MAP.get(touch.key, touch.key)
                await self._page.keyboard.press(key)
            elif touch.action_type == ActionType.WAIT:
                await asyncio.sleep(touch.duration or 0.1)

    async def disconnect(self) -> None:
        """브라우저 종료."""
        self._connected = False
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._page = None

    async def restart_game(self) -> None:
        """게임 재시작 (retry 버튼 클릭)."""
        if not self._page:
            return
        try:
            retry_btn = self._page.locator(".retry-button")
            if await retry_btn.is_visible():
                await retry_btn.click()
                await asyncio.sleep(0.5)
        except Exception:
            await self._page.reload(wait_until="domcontentloaded")
            await self._page.wait_for_selector(".tile-container", timeout=15000)
