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

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# YOLO 로컬 분류 모델 (Phase 1 대체: 8초 → 5ms)
_YOLO_MODEL = None
_YOLO_CLASSES = None  # {0: "ad", 1: "fail", ...}

def _load_yolo():
    """YOLO 모델 lazy load. 없으면 None 반환."""
    global _YOLO_MODEL, _YOLO_CLASSES
    if _YOLO_MODEL is not None:
        return _YOLO_MODEL
    model_path = Path("E:/AI/virtual_player/data/games/carmatch/yolo_dataset/models/screen_classifier_best.pt")
    if not model_path.exists():
        # 학습 산출물에서 찾기
        alt = Path("E:/AI/virtual_player/data/games/carmatch/yolo_dataset/models/screen_classifier/weights/best.pt")
        if alt.exists():
            model_path = alt
        else:
            return None
    try:
        from ultralytics import YOLO
        _YOLO_MODEL = YOLO(str(model_path))
        _YOLO_CLASSES = _YOLO_MODEL.names  # {0: "ad", 1: "fail", ...}
        return _YOLO_MODEL
    except Exception:
        return None


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
        timeout: int = 300,
        api_key: Optional[str] = None,
    ):
        self.model = model
        self.timeout = timeout
        self._call_count = 0
        self._last_screen: Optional[str] = None  # 이전 턴 screen_type 캐시

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

        # CLI 모드일 때 이미지 압축 (1.7MB → ~200KB)
        actual_path = self._compress_if_needed(screenshot_path)

        self._call_count += 1

        # CLI 모드: 2단계 인식 (Phase 1: screen_type → Phase 2: 상세)
        if not self._use_sdk:
            return self._perceive_two_phase(actual_path)

        # SDK 모드: 기존 1단계 전체 인식
        raw = self._call_vision(actual_path)
        if not raw:
            return BoardState(screen_type="unknown", holder=[None]*7)
        return self._parse_response(raw)

    def _compress_if_needed(self, img_path: Path) -> Path:
        """CLI 모드에서 이미지를 540x960 JPEG로 압축."""
        if self._use_sdk or not _HAS_PIL:
            return img_path
        try:
            compressed = img_path.parent / f"{img_path.stem}_sm.jpg"
            img = Image.open(img_path)
            img = img.resize((540, 960), Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(compressed, "JPEG", quality=70)
            return compressed
        except Exception:
            return img_path

    # YOLO 7클래스 → Perception screen_type 매핑
    _YOLO_TO_SCREEN = {
        "gameplay": "gameplay",
        "lobby": "lobby",
        "win": "win",
        "fail": "fail_result",
        "popup": "popup",
        "ad": "ad",
        "other": "unknown",
    }

    def _classify_with_yolo(self, img_path: Path) -> Optional[str]:
        """YOLO로 screen_type 분류. 실패 시 None 반환."""
        model = _load_yolo()
        if model is None:
            return None
        try:
            results = model(str(img_path), verbose=False)
            if results and results[0].probs is not None:
                top1_idx = results[0].probs.top1
                top1_conf = results[0].probs.top1conf.item()
                class_name = results[0].names[top1_idx]
                # 신뢰도 60% 이상이면 채택
                if top1_conf >= 0.6:
                    return self._YOLO_TO_SCREEN.get(class_name, "unknown")
            return None
        except Exception:
            return None

    def _perceive_two_phase(self, img_path: Path) -> BoardState:
        """2단계 인식: Phase 1(YOLO or CLI) → Phase 2(상세).

        우선순위: YOLO(5ms) → gameplay 캐시 → CLI Phase 1(8초)
        """
        # Phase 1: YOLO 로컬 분류 시도
        yolo_screen = self._classify_with_yolo(img_path)
        if yolo_screen is not None:
            screen = yolo_screen
        elif self._last_screen == "gameplay":
            # YOLO 없으면 이전 턴 캐시 사용
            screen = "gameplay"
        else:
            # YOLO도 없고 캐시도 없으면 CLI 폴백
            raw1 = self._call_vision_cli(img_path, prompt=self._PROMPT_PHASE1)
            screen = self._parse_screen_type(raw1)

        self._last_screen = screen

        # 비-gameplay면 Phase 1만으로 충분
        if screen != "gameplay":
            return BoardState(
                screen_type=screen,
                holder=[None] * 7,
                holder_count=0,
                confidence=0.5,
                raw_response="",
            )

        # Phase 2: gameplay → holder + active_cars 상세 분석
        raw2 = self._call_vision_cli(img_path, prompt=self._PROMPT_PHASE2)
        if not raw2:
            # Phase 2 실패 → 화면이 바뀌었을 가능성 → Phase 1 재시도
            self._last_screen = None
            self._call_count += 1
            raw1_retry = self._call_vision_cli(img_path, prompt=self._PROMPT_PHASE1)
            retry_screen = self._parse_screen_type(raw1_retry)
            self._last_screen = retry_screen
            return BoardState(screen_type=retry_screen, holder=[None]*7)

        board = self._parse_response(raw2)

        # Phase 2 응답에 차가 0대이고 홀더도 비어있으면 → 화면 전환 의심
        if not board.active_cars and board.holder_count == 0:
            # Phase 1으로 재확인
            self._last_screen = None
            self._call_count += 1
            raw1_check = self._call_vision_cli(img_path, prompt=self._PROMPT_PHASE1)
            check_screen = self._parse_screen_type(raw1_check)
            if check_screen != "gameplay":
                self._last_screen = check_screen
                return BoardState(screen_type=check_screen, holder=[None]*7)

        board.screen_type = "gameplay"
        return board

    # --- 프롬프트 ---

    # SDK용: 1단계로 전부 인식 (빠르니까 OK)
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

    # CLI Phase 1: screen_type만 (짧고 빠름)
    _PROMPT_PHASE1 = """Look at this mobile game screenshot and identify the screen type.
Reply with ONLY one word from this list:
gameplay, lobby, win, fail_outofspace, fail_continue, fail_result, ad, popup, lobby_keyblaze, lobby_streakrace, lobby_dailytask, lobby_skylift, lobby_missiongarage, lobby_skyrally, lobby_endlesscoast, lobby_punchout, lobby_citydeal, shop, leaderboard, journey, setting, profile, ingame_setting, ingame_quit_confirm, unknown

Hints:
- "gameplay" = parking lot with colored 3D cartoon cars and a holder bar at bottom
- "lobby" = large Level N button at bottom, car character in center
- "lobby_*" = event popup overlay on lobby (Key Blaze, Streak Race, etc.)
- "win" = congratulations/victory screen
- "fail_*" = game over with options (Add Space, Play On, Try Again)
- "popup" = any modal dialog or overlay

Reply with ONLY the one word. No JSON, no explanation."""

    # CLI Phase 2: gameplay 상세 (holder + cars)
    # 주의: 압축 이미지(540x960)로 인식하므로 좌표는 원본(1080x1920) 기준으로 2배 해서 보고하도록 지시
    _PROMPT_PHASE2 = """This is a "gameplay" screen from a car-matching puzzle game (original resolution 1080x1920, this image is scaled down).
Return ONLY this JSON:
{"holder":[<7 slots: color or null>],"active_cars":[{"color":"<color>","x":<int>,"y":<int>,"stacked":<1-5>}]}

RULES:
- holder: 7 bottom slots left-to-right. Colors: red,blue,green,yellow,orange,purple,pink,cyan,white,brown,unknown. null if empty.
- active_cars: ONLY cars with visible EYES/FACE (not hidden). Max 8 cars.
- IMPORTANT: x,y coordinates must be for the ORIGINAL 1080x1920 resolution. Since this image is 540x960, multiply your pixel readings by 2.
- Mystery cars (?) = "unknown" color.
- stacked: number shown on spot (2-5), or 1 if none.
- ONLY output the JSON object."""

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

    def _call_vision_cli(self, img_path: Path, prompt: Optional[str] = None) -> str:
        """Claude CLI 폴백. prompt 파라미터로 Phase 1/2 전환."""
        import subprocess
        import tempfile

        img = str(img_path).replace("\\", "/")
        use_prompt = prompt or self._PROMPT
        full_prompt = f"Use the Read tool to view the image at {img}. Then respond.\n\n{use_prompt}"

        env = os.environ.copy()
        for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
            env.pop(k, None)
        api_key = env.get("ANTHROPIC_API_KEY", "")
        if api_key and not api_key.startswith("sk-ant-"):
            env.pop("ANTHROPIC_API_KEY", None)
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            r = subprocess.run(
                [self._claude_cmd, "-p",
                 "--model", self.model,
                 "--output-format", "json",
                 "--max-turns", "5",
                 "--tools", "Read",
                 "--allowedTools", "Read"],
                input=full_prompt,
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

    def _parse_screen_type(self, raw: str) -> str:
        """Phase 1 응답에서 screen_type 추출."""
        if not raw:
            return "unknown"
        text = raw.strip().lower().replace('"', '').replace("'", "")
        # 여러 줄이면 첫 줄만
        text = text.split("\n")[0].strip()
        # 단어 단위로 매칭
        for word in text.split():
            cleaned = word.strip(".,;:!?(){}[]")
            if cleaned in self.VALID_SCREENS:
                return cleaned
        # 부분 매칭
        for valid in self.VALID_SCREENS:
            if valid in text:
                return valid
        return "unknown"

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

            # 좌표 범위 검증 (보드+출구 영역)
            if 0 < x < 1080 and 100 < y < 1800:
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
