"""
GameAdapter Abstract Base Class
================================
게임과의 연결을 담당하는 어댑터 인터페이스.
connect → get_game_state → send_input → disconnect.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..brain.base import TouchInput


# ============================================================
# Abstract base class
# ============================================================

class GameAdapter(ABC):
    """
    게임 연결 어댑터 추상 클래스.

    각 게임/플랫폼은 이 클래스를 상속하여:
    1. connect(): 게임에 연결 (브라우저 실행, 앱 연결 등)
    2. get_game_state(): 현재 게임 상태 읽기
    3. send_input(): 입력 전송
    4. disconnect(): 연결 종료
    """

    def __init__(self, user_agent: str = "", device_profile: Optional[Dict[str, Any]] = None):
        """
        Args:
            user_agent: 브라우저 UA 문자열.
            device_profile: 디바이스 프로필 (해상도, DPI 등).
        """
        self.user_agent = user_agent
        self.device_profile = device_profile or {}
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        """게임에 연결."""
        ...

    @abstractmethod
    async def get_game_state(self) -> Any:
        """현재 게임 상태를 반환."""
        ...

    @abstractmethod
    async def send_input(self, inputs: List[TouchInput]) -> None:
        """입력 이벤트 목록을 게임에 전송."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """연결 종료 및 리소스 정리."""
        ...

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        return False
