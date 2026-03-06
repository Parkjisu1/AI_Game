"""
Layer 1: Perception (눈)
=========================
화면을 보고 정해진 JSON 포맷으로만 반환.

TO DO:
  - 홀더 7칸 각각의 색상을 읽어라
  - 보드에서 눈이 보이는 차의 좌표+색상만 리스트로 뽑아라
  - 스택 숫자(x2~x5)를 읽어라
  - Mystery(?)는 "unknown"으로 표기하라
  - 화면 유형을 판별하라

TO DON'T:
  - 자유 텍스트로 설명하지 마라
  - 가려진 차를 추측하지 마라
  - 스택 아래 색상을 추측하지 마라
"""

import base64
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import anthropic


# ---------------------------------------------------------------------------
# 인식 결과 구조체 (고정 포맷)
# ---------------------------------------------------------------------------
@dataclass
class CarInfo:
    """보드 위의 활성 자동차 1대."""
    color: str          # red, blue, green, yellow, orange, purple, pink, cyan, unknown
    x: int              # 중심 x좌표 (0~1080)
    y: int              # 중심 y좌표 (0~1920)
    stacked: int = 1    # 스택 수 (1=단독, 2~5=쌓임)
    is_mystery: bool = False  # ?표시 자동차


@dataclass
class BoardState:
    """한 프레임의 전체 보드 상태. Layer 1 출력 = Layer 2,3 입력."""
    screen_type: str                          # gameplay, lobby, win, fail_*, ad, ...
    holder: List[Optional[str]]               # 7칸: ["red","red","blue",None,None,None,None]
    holder_count: int = 0                     # 사용 중인 칸 수
    active_cars: List[CarInfo] = field(default_factory=list)  # 탭 가능한 차들
    confidence: float = 0.0                   # 인식 신뢰도 (0~1)
    raw_response: str = ""                    # 디버깅용 원본 응답


# ---------------------------------------------------------------------------
# Perception: Vision API 호출 → BoardState 변환
# ---------------------------------------------------------------------------
class Perception:
    """Layer 1: 스크린샷 → 구조화된 BoardState 반환.

    AI 의존 구간: 이미지 인식 (VLM 호출)
    나머지: JSON 파싱 + 검증 (규칙 기반)
    """

    # 허용된 색상 목록 (이 외는 "unknown"으로 강제 변환)
    VALID_COLORS = {
        "red", "blue", "green", "yellow", "orange",
        "purple", "pink", "cyan", "white", "brown", "unknown"
    }

    # 허용된 화면 유형 목록
    VALID_SCREENS = {
        "gameplay", "lobby", "win",
        "fail_outofspace", "fail_continue", "fail_result",
        "ingame_setting", "ingame_quit_confirm",
        "ad", "ad_install",
        "shop", "leaderboard", "journey", "setting",
        "profile", "popup", "unknown",
        # 이벤트 팝업
        "lobby_keyblaze", "lobby_streakrace", "lobby_dailytask",
        "lobby_skylift", "lobby_missiongarage", "lobby_skyrally",
        "lobby_endlesscoast", "lobby_punchout", "lobby_citydeal",
    }

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        timeout: int = 60,
        api_key: Optional[str] = None,
    ):
        self.model = model
        self.timeout = timeout
        self._call_count = 0

        # API 키 확인: 유효한 키가 있으면 SDK 직접 호출, 없으면 CLI 폴백
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._use_sdk = resolved_key.startswith("sk-ant-")
        if self._use_sdk:
            self._client = anthropic.Anthropic(api_key=resolved_key)
        else:
            self._client = None
            self._claude_cmd = "C:/Users/user/AppData/Roaming/npm/claude.cmd"

    def perceive(self, screenshot_path: Path) -> BoardState:
        """스크린샷 → BoardState. 실패 시 unknown 화면 반환."""
        if not screenshot_path.exists():
            return BoardState(screen_type="unknown", holder=[None]*7)

        self._call_count += 1
        raw = self._call_vision(screenshot_path)

        if not raw:
            return BoardState(screen_type="unknown", holder=[None]*7)

        return self._parse_response(raw)

    # 공통 프롬프트
    _PROMPT = """Analyze this 1080x1920 mobile game screenshot. Return ONLY this JSON:

{
  "screen": "<one of: gameplay, lobby, win, fail_outofspace, fail_continue, fail_result, ad, popup, unknown>",
  "holder": [<7 elements: color string or null for empty slots>],
  "active_cars": [
    {"color": "<color>", "x": <int>, "y": <int>, "stacked": <1-5>}
  ]
}

RULES:
- screen: identify the screen type. "gameplay" = parking lot with cars and holder.
- holder: read the 7 bottom slots left-to-right. Use color name or null.
- active_cars: ONLY list cars whose EYES/FACE are visible (not hidden behind other cars).
  Each car has cartoon eyes. If eyes are blocked by another car in front, do NOT list it.
- Valid colors: red, blue, green, yellow, orange, purple, pink, cyan, white, brown, unknown
- For mystery cars (?), use "unknown" as color.
- x,y = CENTER of the car body (not edge).
- stacked: if a number (2,3,4,5) is shown on the spot, use that number. Otherwise 1.
- If screen is NOT "gameplay", set holder to [null,null,null,null,null,null,null] and active_cars to [].
- Output ONLY the JSON. No explanation, no markdown, no text."""

    def _call_vision(self, img_path: Path) -> str:
        """Vision API 호출. SDK 직접 또는 CLI 폴백."""
        if self._use_sdk:
            return self._call_vision_sdk(img_path)
        return self._call_vision_cli(img_path)

    def _call_vision_sdk(self, img_path: Path) -> str:
        """Anthropic SDK 직접 호출 (빠름, ~2-5초)."""
        img_bytes = img_path.read_bytes()
        img_b64 = base64.b64encode(img_bytes).decode("ascii")

        suffix = img_path.suffix.lower()
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(suffix, "image/png")

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": img_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": self._PROMPT,
                        },
                    ],
                }],
            )
            return response.content[0].text
        except Exception:
            return ""

    def _call_vision_cli(self, img_path: Path) -> str:
        """Claude CLI 폴백 (느림, ~20-40초). API 키 없을 때 사용."""
        import subprocess
        import tempfile

        img = str(img_path).replace("\\", "/")
        prompt = f"Use the Read tool to view the screenshot at {img}. Then respond with ONLY the JSON object.\n\n{self._PROMPT}"

        env = os.environ.copy()
        for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
            env.pop(k, None)
        # 잘못된 API 키(placeholder) 제거 → Claude Code 자체 인증 사용
        api_key = env.get("ANTHROPIC_API_KEY", "")
        if api_key and not api_key.startswith("sk-ant-"):
            env.pop("ANTHROPIC_API_KEY", None)
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            r = subprocess.run(
                [self._claude_cmd, "-p",
                 "--model", self.model,
                 "--output-format", "json",
                 "--max-turns", "2",
                 "--tools", "Read",
                 "--allowedTools", "Read"],
                input=prompt,
                capture_output=True,
                timeout=self.timeout,
                encoding="utf-8",
                env=env,
                cwd=tempfile.gettempdir(),
            )
            try:
                outer = json.loads(r.stdout)
                if isinstance(outer, dict):
                    if outer.get("is_error"):
                        return ""
                    return outer.get("result", r.stdout)
                return r.stdout
            except json.JSONDecodeError:
                return r.stdout if r.returncode == 0 else ""

        except (subprocess.TimeoutExpired, Exception):
            return ""

    def _parse_response(self, raw: str) -> BoardState:
        """원본 텍스트 → BoardState. 파싱 실패 시 unknown 반환."""
        text = str(raw).strip()

        # JSON 추출
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return BoardState(screen_type="unknown", holder=[None]*7, raw_response=text[:200])

        try:
            data = json.loads(text[start:end+1])
        except json.JSONDecodeError:
            return BoardState(screen_type="unknown", holder=[None]*7, raw_response=text[:200])

        # screen_type 검증
        screen = str(data.get("screen", "unknown")).lower().strip()
        if screen not in self.VALID_SCREENS:
            # 부분 매칭 시도
            for valid in self.VALID_SCREENS:
                if valid in screen:
                    screen = valid
                    break
            else:
                screen = "unknown"

        # holder 검증 (정확히 7칸)
        raw_holder = data.get("holder", [None]*7)
        if not isinstance(raw_holder, list):
            raw_holder = [None]*7
        holder = []
        for i in range(7):
            if i < len(raw_holder) and raw_holder[i]:
                color = str(raw_holder[i]).lower().strip()
                if color in self.VALID_COLORS:
                    holder.append(color)
                elif color in ("none", "null", "empty", ""):
                    holder.append(None)
                else:
                    holder.append("unknown")
            else:
                holder.append(None)

        holder_count = sum(1 for h in holder if h is not None)

        # active_cars 검증
        raw_cars = data.get("active_cars", [])
        if not isinstance(raw_cars, list):
            raw_cars = []

        active_cars = []
        for car in raw_cars:
            if not isinstance(car, dict):
                continue
            color = str(car.get("color", "unknown")).lower().strip()
            if color not in self.VALID_COLORS:
                color = "unknown"
            x = int(car.get("x", 0))
            y = int(car.get("y", 0))
            stacked = int(car.get("stacked", 1))

            # 좌표 범위 검증 (보드 영역 안이어야 함)
            if 0 < x < 1080 and 100 < y < 1500:
                x = max(0, min(1080, x))
                y = max(0, min(1920, y))
                stacked = max(1, min(5, stacked))
                active_cars.append(CarInfo(
                    color=color, x=x, y=y,
                    stacked=stacked,
                    is_mystery=(color == "unknown"),
                ))

        return BoardState(
            screen_type=screen,
            holder=holder,
            holder_count=holder_count,
            active_cars=active_cars,
            confidence=0.7 if active_cars else 0.3,
            raw_response=text[:300],
        )

    @property
    def call_count(self) -> int:
        return self._call_count
