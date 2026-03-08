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

    # 허용된 색상 목록 (이 외는 COLOR_MAP으로 정규화)
    VALID_COLORS = {
        "red", "blue", "green", "yellow", "orange",
        "purple", "pink", "cyan", "white", "brown", "unknown"
    }

    # VLM이 사용하는 다양한 색상명 → 시스템 색상으로 정규화
    # VLM은 사람처럼 세밀한 색명을 사용하므로 여기서 통일
    COLOR_MAP = {
        # 직접 매칭
        "red": "red", "blue": "blue", "green": "green",
        "yellow": "yellow", "orange": "orange", "purple": "purple",
        "pink": "pink", "cyan": "cyan", "white": "white",
        "brown": "brown", "unknown": "unknown",
        # VLM이 자주 쓰는 변형 → 정규화
        "tan": "orange",        # 연한 갈색/황갈색 → 게임에서는 주황계열
        "gold": "yellow",       # 금색 → 노란색
        "golden": "yellow",
        "beige": "orange",      # 베이지 → 주황계열
        "khaki": "orange",
        "cream": "yellow",
        "amber": "orange",
        "coral": "red",         # 코랄 → 빨강계열
        "crimson": "red",
        "scarlet": "red",
        "maroon": "brown",      # 적갈색 → 갈색
        "burgundy": "brown",
        "wine": "brown",
        "violet": "purple",     # 보라색 변형
        "lavender": "purple",
        "indigo": "purple",
        "magenta": "pink",      # 마젠타 → 핑크
        "salmon": "pink",
        "rose": "pink",
        "fuchsia": "pink",
        "lime": "green",        # 라임 → 초록
        "olive": "green",
        "teal": "cyan",         # 틸 → 시안
        "turquoise": "cyan",
        "aqua": "cyan",
        "navy": "blue",         # 네이비 → 파랑
        "sky": "blue",
        "gray": "white",        # 회색 → 흰색 (게임에 회색 차가 없으므로)
        "grey": "white",
        "silver": "white",
        "charcoal": "brown",
        "dark_brown": "brown",
        "light_blue": "cyan",
        "light_green": "green",
        "dark_green": "green",
        "dark_red": "red",
        "dark_blue": "blue",
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

        # 원본 경로 보존 (YOLO OD / OpenCV는 원본 사용)
        self._original_path = screenshot_path

        # CLI 모드일 때 이미지 압축 (VLM 폴백용)
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

    # 압축 비율 추적 (좌표 복원용)
    _compress_scale = 1  # 1 = 원본, 2 = 절반 축소

    def _compress_if_needed(self, img_path: Path) -> Path:
        """CLI 모드에서 이미지를 540x960 JPEG로 압축.

        좌표 복원은 _parse_response에서 _compress_scale을 사용하여 수행.
        VLM에게 좌표 변환을 맡기지 않음 (비결정적이므로).
        """
        if self._use_sdk or not _HAS_PIL:
            self._compress_scale = 1
            return img_path
        try:
            compressed = img_path.parent / f"{img_path.stem}_sm.jpg"
            img = Image.open(img_path)
            orig_w, orig_h = img.size
            target_w, target_h = 540, 960
            img = img.resize((target_w, target_h), Image.LANCZOS)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(compressed, "JPEG", quality=70)
            # 축소 비율 저장 (나중에 좌표에 곱할 값)
            self._compress_scale = round(orig_w / target_w)  # 1080/540 = 2
            return compressed
        except Exception:
            self._compress_scale = 1
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
        """2단계 인식: Phase 1(화면 분류) → Phase 2(차량+홀더 감지).

        Phase 1: YOLO classify (5ms) → 캐시 → CLI 폴백
        Phase 2: YOLO OD (10ms) → OpenCV (50ms) → VLM CLI (100s)
        홀더:    OpenCV 색상 분석 (항상, 10ms)
        """
        # Phase 1: YOLO 로컬 분류 시도
        yolo_screen = self._classify_with_yolo(img_path)
        if yolo_screen is not None:
            screen = yolo_screen
        elif self._last_screen == "gameplay":
            screen = "gameplay"
        else:
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

        # Phase 2: gameplay → 로컬 감지 시도 (YOLO OD / OpenCV)
        original = getattr(self, '_original_path', img_path)
        board = self._detect_local(original)
        if board is not None:
            return board

        # 로컬 감지 실패 → VLM CLI 폴백
        raw2 = self._call_vision_cli(img_path, prompt=self._PROMPT_PHASE2)
        if not raw2:
            self._last_screen = None
            self._call_count += 1
            raw1_retry = self._call_vision_cli(img_path, prompt=self._PROMPT_PHASE1)
            retry_screen = self._parse_screen_type(raw1_retry)
            self._last_screen = retry_screen
            return BoardState(screen_type=retry_screen, holder=[None]*7)

        board = self._parse_response(raw2)

        if not board.active_cars and board.holder_count == 0:
            self._last_screen = None
            self._call_count += 1
            raw1_check = self._call_vision_cli(img_path, prompt=self._PROMPT_PHASE1)
            check_screen = self._parse_screen_type(raw1_check)
            if check_screen != "gameplay":
                self._last_screen = check_screen
                return BoardState(screen_type=check_screen, holder=[None]*7)

        board.screen_type = "gameplay"
        return board

    # 로컬 감지 최소 차량 수 (이 이하면 VLM 폴백)
    _LOCAL_MIN_CARS = 3

    def _detect_local(self, img_path: Path) -> Optional[BoardState]:
        """YOLO OD / OpenCV로 로컬 감지. 실패 시 None → VLM 폴백.

        성공 조건: 차량 3대 이상 감지 (그 이하면 신뢰 불가)
        """
        try:
            from .yolo_detector import HolderDetector, CarDetectorYOLO, CarDetectorCV
        except ImportError:
            return None

        # 홀더: 항상 OpenCV (빠르고 확정적)
        holder_det = getattr(self, '_holder_detector', None)
        if holder_det is None:
            holder_det = HolderDetector()
            self._holder_detector = holder_det

        holder = holder_det.detect(img_path)
        holder_count = sum(1 for h in holder if h is not None)

        # 차량: YOLO OD → OpenCV 체인
        cars_raw = []
        detection_mode = "none"

        if CarDetectorYOLO.is_available():
            cars_raw = CarDetectorYOLO.detect(img_path)
            detection_mode = "yolo_od"

        if len(cars_raw) < self._LOCAL_MIN_CARS:
            cv_det = getattr(self, '_cv_detector', None)
            if cv_det is None:
                cv_det = CarDetectorCV()
                self._cv_detector = cv_det
            cars_raw = cv_det.detect(img_path)
            detection_mode = "opencv"

        if len(cars_raw) < self._LOCAL_MIN_CARS:
            return None  # 로컬 감지 실패 → VLM 폴백

        # dict → CarInfo 변환
        active_cars = []
        for c in cars_raw:
            color = self._normalize_color(c["color"])
            x, y = c["x"], c["y"]
            if 0 < x < 1080 and 100 < y < 1800:
                active_cars.append(CarInfo(
                    color=color, x=x, y=y,
                    stacked=1,
                    is_mystery=(color == "unknown"),
                ))

        return BoardState(
            screen_type="gameplay",
            holder=holder,
            holder_count=holder_count,
            active_cars=active_cars,
            confidence=0.8 if detection_mode == "yolo_od" else 0.6,
            raw_response=f"local:{detection_mode}:{len(active_cars)}cars",
        )

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
- active_cars: List ALL cars whose cartoon EYES are visible (not hidden behind other cars).
  Include cars in the exit lane (moving toward the holder).
- color: Use ONLY one of: red, blue, green, yellow, orange, purple, pink, cyan, white, brown, unknown.
  Map similar colors: tan/beige/gold → orange or yellow. Do NOT use colors outside this list.
- For mystery cars (?), use "unknown" as color.
- x,y = CENTER of the car body in pixels, as seen in the image.
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
    # 좌표는 이미지 그대로 보고 → 코드에서 _compress_scale 곱해서 복원
    _PROMPT_PHASE2 = """This is a car-matching puzzle game screenshot.
Return ONLY this JSON:
{"holder":[<7 slots>],"active_cars":[{"color":"<color>","x":<int>,"y":<int>,"stacked":<1-5>}]}

RULES:
- holder: Read the 7 bottom slots left-to-right. Each slot has a colored car or is empty.
  Use one of: red, blue, green, yellow, orange, purple, pink, cyan, white, brown. Use null if empty.
- active_cars: List ALL cars whose cartoon EYES are visible (not blocked by other cars in front).
  Include cars in the exit lane approaching the holder.
- color: Use the CLOSEST match from: red, blue, green, yellow, orange, purple, pink, cyan, white, brown.
  Tan/beige/gold cars → orange or yellow. Do NOT invent colors outside this list.
- x,y: The pixel coordinates of the CENTER of each car, as seen in THIS image. Do NOT scale or transform.
- stacked: If a number (2,3,4,5) is shown on the parking spot, use that number. Otherwise 1.
- Mystery boxes with "?" → color "unknown".
- ONLY output the JSON. No markdown, no explanation, no notes."""

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

    def _normalize_color(self, raw_color: str) -> str:
        """VLM이 보고한 색상명을 시스템 색상으로 정규화.

        1. COLOR_MAP에서 직접 매칭
        2. 부분 문자열 매칭 (dark_green → green)
        3. 모든 것 실패 → "unknown"
        """
        c = raw_color.lower().strip().replace("-", "_").replace(" ", "_")

        # 빈 값
        if c in ("none", "null", "empty", ""):
            return "unknown"

        # 직접 매칭
        if c in self.COLOR_MAP:
            return self.COLOR_MAP[c]

        # VALID_COLORS에 직접 있으면
        if c in self.VALID_COLORS:
            return c

        # 부분 문자열: "light_blue" → "blue", "dark_red" → "red" 등
        for valid in self.VALID_COLORS:
            if valid in c:
                return valid

        return "unknown"

    def _parse_response(self, raw: str) -> BoardState:
        """원본 텍스트 → BoardState. 파싱 실패 시 unknown 반환.

        좌표 변환: VLM은 압축 이미지(540x960) 기준으로 보고 →
        _compress_scale을 곱해서 원본(1080x1920)으로 복원.
        """
        text = str(raw).strip()
        scale = getattr(self, '_compress_scale', 1)

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
            for valid in self.VALID_SCREENS:
                if valid in screen:
                    screen = valid
                    break
            else:
                screen = "unknown"

        # holder 검증 (정확히 7칸) — 색상 정규화 적용
        raw_holder = data.get("holder", [None]*7)
        if not isinstance(raw_holder, list):
            raw_holder = [None]*7
        holder = []
        for i in range(7):
            if i < len(raw_holder) and raw_holder[i]:
                color = str(raw_holder[i]).lower().strip()
                if color in ("none", "null", "empty", ""):
                    holder.append(None)
                else:
                    holder.append(self._normalize_color(color))
            else:
                holder.append(None)

        holder_count = sum(1 for h in holder if h is not None)

        # active_cars 검증 — 색상 정규화 + 좌표 스케일링 적용
        raw_cars = data.get("active_cars", data.get("cars", []))
        if not isinstance(raw_cars, list):
            raw_cars = []

        active_cars = []
        for car in raw_cars:
            if not isinstance(car, dict):
                continue
            raw_color = str(car.get("color", "unknown")).lower().strip()
            color = self._normalize_color(raw_color)

            try:
                x = int(car.get("x", 0))
                y = int(car.get("y", 0))
                stacked = int(car.get("stacked", 1))
            except (ValueError, TypeError):
                continue

            # 좌표 스케일링: 압축 이미지 좌표 → 원본 해상도
            x = x * scale
            y = y * scale

            # 좌표가 원본 해상도 범위 내인지 검증
            max_x = 1080 * max(1, scale // scale)  # 항상 1080
            max_y = 1920 * max(1, scale // scale)  # 항상 1920

            # 좌표가 여전히 압축 이미지 범위인지 감지
            # (VLM이 이미 2배로 보고했을 수도 있으므로 이중 스케일 방지)
            if scale > 1 and x > 1080:
                # 이미 원본 스케일로 보고된 것 → 스케일 취소
                x = x // scale
                y = y // scale

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
