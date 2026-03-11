"""
Phase 1: Universal Vision — OCR + UI Element Detection
========================================================
범용 UI 인식 모듈. 게임별 하드코딩 없이 화면 요소를 자동 감지.

3단계 파이프라인:
  1. OCR (EasyOCR) → 텍스트 + 바운딩 박스
  2. Contour Detection (OpenCV) → 버튼/아이콘 영역
  3. Color Analysis → 주요 색상 분포

출력: UIState (구조화된 화면 정보)
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import time

import cv2
import numpy as np

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

# EasyOCR lazy init (첫 호출 시 ~2초 로딩)
_ocr_reader = None


def _get_ocr():
    global _ocr_reader
    if _ocr_reader is None:
        import easyocr
        _ocr_reader = easyocr.Reader(["en", "ko"], gpu=False, verbose=False)
    return _ocr_reader


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------
@dataclass
class TextElement:
    """OCR로 감지된 텍스트 요소."""
    text: str
    x: int              # 중심 x
    y: int              # 중심 y
    x1: int             # bbox 좌상단
    y1: int
    x2: int             # bbox 우하단
    y2: int
    confidence: float
    is_button: bool = False  # 버튼 내부 텍스트인지


@dataclass
class UIRegion:
    """감지된 UI 영역 (버튼, 아이콘, 패널 등)."""
    x1: int
    y1: int
    x2: int
    y2: int
    region_type: str    # "button", "icon", "panel", "close_x", "input_field"
    color: str = ""     # 주요 색상
    text: str = ""      # 포함된 텍스트
    confidence: float = 0.0

    @property
    def cx(self) -> int:
        return (self.x1 + self.x2) // 2

    @property
    def cy(self) -> int:
        return (self.y1 + self.y2) // 2

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1


@dataclass
class UIState:
    """화면의 구조화된 UI 상태."""
    texts: List[TextElement] = field(default_factory=list)
    buttons: List[UIRegion] = field(default_factory=list)
    close_buttons: List[UIRegion] = field(default_factory=list)
    panels: List[UIRegion] = field(default_factory=list)
    dominant_colors: List[Tuple[str, float]] = field(default_factory=list)
    has_dark_overlay: bool = False
    screen_brightness: float = 0.0
    processing_time: float = 0.0

    def find_text(self, keyword: str, case_sensitive: bool = False) -> Optional[TextElement]:
        """키워드가 포함된 텍스트 요소 찾기."""
        for t in self.texts:
            text = t.text if case_sensitive else t.text.lower()
            target = keyword if case_sensitive else keyword.lower()
            if target in text:
                return t
        return None

    def find_all_text(self, keyword: str, case_sensitive: bool = False) -> List[TextElement]:
        """키워드가 포함된 모든 텍스트 요소."""
        results = []
        for t in self.texts:
            text = t.text if case_sensitive else t.text.lower()
            target = keyword if case_sensitive else keyword.lower()
            if target in text:
                results.append(t)
        return results

    def find_button_with_text(self, keyword: str) -> Optional[UIRegion]:
        """특정 텍스트가 포함된 버튼 찾기."""
        kw = keyword.lower()
        for b in self.buttons:
            if kw in b.text.lower():
                return b
        return None

    def get_closest_button(self, x: int, y: int) -> Optional[UIRegion]:
        """좌표에 가장 가까운 버튼."""
        if not self.buttons:
            return None
        return min(self.buttons, key=lambda b: (b.cx - x)**2 + (b.cy - y)**2)


# ---------------------------------------------------------------------------
# UniversalVision
# ---------------------------------------------------------------------------
class UniversalVision:
    """범용 UI 인식 엔진.

    게임별 YOLO 모델 없이도 화면을 구조적으로 이해.
    OCR + OpenCV contour + 색상 분석 조합.
    """

    # 일반적인 모바일 게임 UI 텍스트 (다국어)
    BUTTON_KEYWORDS = {
        # 영어
        "play", "start", "continue", "retry", "ok", "yes", "no",
        "cancel", "close", "back", "next", "skip", "claim",
        "collect", "watch", "free", "buy", "shop", "home",
        "confirm", "accept", "decline", "install", "download",
        # 한국어
        "시작", "계속", "다시", "확인", "취소", "닫기",
        "받기", "보기", "구매", "상점", "홈", "도전",
        "수집", "무료", "광고", "설치",
        # 일본어
        "開始", "続ける", "リトライ", "確認", "キャンセル",
    }

    FORBIDDEN_KEYWORDS = {
        "purchase", "buy", "install", "download",
        "구매", "설치", "결제",
        "krw", "usd", "₩", "$",
    }

    def __init__(self, use_ocr: bool = True, use_contour: bool = True):
        self.use_ocr = use_ocr
        self.use_contour = use_contour

    def analyze(self, img_path: Path) -> UIState:
        """스크린샷 분석 → UIState 반환."""
        t0 = time.time()
        state = UIState()

        img = cv2.imread(str(img_path))
        if img is None:
            return state

        h, w = img.shape[:2]

        # 1. OCR
        if self.use_ocr:
            state.texts = self._run_ocr(img_path, w, h)

        # 2. Contour-based UI detection
        if self.use_contour:
            regions = self._detect_ui_regions(img)
            for r in regions:
                if r.region_type == "close_x":
                    state.close_buttons.append(r)
                elif r.region_type == "button":
                    state.buttons.append(r)
                elif r.region_type == "panel":
                    state.panels.append(r)

        # 3. OCR 텍스트를 버튼에 매핑
        self._map_text_to_buttons(state)

        # 4. 색상 분석
        state.dominant_colors = self._analyze_colors(img)
        state.screen_brightness = img.mean() / 255.0
        state.has_dark_overlay = self._check_dark_overlay(img)

        state.processing_time = time.time() - t0
        return state

    def _run_ocr(self, img_path: Path, img_w: int, img_h: int) -> List[TextElement]:
        """EasyOCR로 텍스트 감지."""
        try:
            reader = _get_ocr()
            results = reader.readtext(str(img_path))
        except Exception:
            return []

        texts = []
        for bbox, text, conf in results:
            if conf < 0.3 or len(text.strip()) == 0:
                continue

            # bbox: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            xs = [int(p[0]) for p in bbox]
            ys = [int(p[1]) for p in bbox]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)

            is_btn = any(kw in text.lower() for kw in self.BUTTON_KEYWORDS)

            texts.append(TextElement(
                text=text.strip(),
                x=(x1 + x2) // 2,
                y=(y1 + y2) // 2,
                x1=x1, y1=y1, x2=x2, y2=y2,
                confidence=conf,
                is_button=is_btn,
            ))

        return texts

    def _detect_ui_regions(self, img: np.ndarray) -> List[UIRegion]:
        """OpenCV로 UI 영역 감지."""
        h, w = img.shape[:2]
        regions = []

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # --- X 버튼 감지 (원형 + 내부 X 패턴) ---
        regions.extend(self._detect_close_buttons(img, gray))

        # --- 직사각형 버튼 감지 ---
        regions.extend(self._detect_rect_buttons(img, gray, w, h))

        return regions

    def _detect_close_buttons(self, img: np.ndarray, gray: np.ndarray) -> List[UIRegion]:
        """X 닫기 버튼 감지 (원형 + X자 패턴)."""
        results = []
        h, w = gray.shape[:2]

        # 엣지 기반 원 감지
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT,
            dp=1.2, minDist=50,
            param1=100, param2=40,
            minRadius=15, maxRadius=50,
        )

        if circles is not None:
            circles = np.round(circles[0]).astype(int)
            for cx, cy, r in circles:
                # 화면 가장자리 근처의 원만 (X 버튼은 보통 코너/엣지에 위치)
                edge_margin = w * 0.15
                is_edge = (cx < edge_margin or cx > w - edge_margin or
                           cy < h * 0.25)

                if not is_edge:
                    continue

                # 원 내부에 X자 패턴이 있는지 확인
                roi = gray[max(0,cy-r):cy+r, max(0,cx-r):cx+r]
                if roi.size == 0:
                    continue

                # X 패턴: 대각선 방향 엣지가 강함
                edges = cv2.Canny(roi, 50, 150)
                if edges.sum() > roi.size * 0.05:  # 엣지 밀도가 충분
                    results.append(UIRegion(
                        x1=cx-r, y1=cy-r, x2=cx+r, y2=cy+r,
                        region_type="close_x",
                        confidence=0.6,
                    ))

        return results

    def _detect_rect_buttons(
        self, img: np.ndarray, gray: np.ndarray, w: int, h: int
    ) -> List[UIRegion]:
        """직사각형 버튼 감지."""
        results = []

        # 적응형 이진화
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 11, 2,
        )

        # 모폴로지 연산으로 노이즈 제거 + 영역 연결
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            x1, y1, bw, bh = cv2.boundingRect(cnt)
            x2, y2 = x1 + bw, y1 + bh
            area = bw * bh

            # 버튼 크기 필터: 화면의 5%~40% 너비, 높이 30~150px
            if bw < w * 0.1 or bw > w * 0.8:
                continue
            if bh < 30 or bh > 200:
                continue
            if area < 3000 or area > w * h * 0.3:
                continue

            # 종횡비: 버튼은 보통 가로가 긴 직사각형
            aspect = bw / max(bh, 1)
            if aspect < 1.2 or aspect > 12:
                continue

            # 버튼 내부 색상 균일도 체크
            roi = img[y1:y2, x1:x2]
            if roi.size == 0:
                continue
            std = roi.std()
            if std > 80:  # 너무 복잡한 영역은 버튼이 아님
                continue

            # 주요 색상 추출
            avg_color = roi.mean(axis=(0, 1))
            color_name = self._classify_color(avg_color)

            results.append(UIRegion(
                x1=x1, y1=y1, x2=x2, y2=y2,
                region_type="button",
                color=color_name,
                confidence=0.5,
            ))

        return results

    def _map_text_to_buttons(self, state: UIState):
        """OCR 텍스트를 가장 가까운 버튼 영역에 매핑."""
        for text in state.texts:
            # 텍스트 bbox와 겹치는 버튼 찾기
            for btn in state.buttons:
                if (text.x1 >= btn.x1 - 10 and text.x2 <= btn.x2 + 10 and
                    text.y1 >= btn.y1 - 10 and text.y2 <= btn.y2 + 10):
                    btn.text = text.text
                    btn.confidence = max(btn.confidence, text.confidence)
                    text.is_button = True
                    break

        # 버튼 영역에 매핑 안 된 버튼 텍스트 → 새 버튼으로 생성
        for text in state.texts:
            if text.is_button and not any(
                b.text == text.text for b in state.buttons
            ):
                margin = 15
                state.buttons.append(UIRegion(
                    x1=text.x1 - margin,
                    y1=text.y1 - margin,
                    x2=text.x2 + margin,
                    y2=text.y2 + margin,
                    region_type="button",
                    text=text.text,
                    confidence=text.confidence * 0.8,
                ))

    def _analyze_colors(self, img: np.ndarray) -> List[Tuple[str, float]]:
        """이미지 주요 색상 분석."""
        # 리사이즈 (속도)
        small = cv2.resize(img, (108, 192))
        pixels = small.reshape(-1, 3).astype(np.float32)

        # K-means 클러스터링
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        try:
            _, labels, centers = cv2.kmeans(
                pixels, 5, None, criteria, 3, cv2.KMEANS_PP_CENTERS
            )
        except cv2.error:
            return []

        # 각 클러스터 비율
        total = len(labels)
        results = []
        for i, center in enumerate(centers):
            ratio = (labels == i).sum() / total
            color_name = self._classify_color(center)
            results.append((color_name, ratio))

        results.sort(key=lambda x: -x[1])
        return results

    def _check_dark_overlay(self, img: np.ndarray) -> bool:
        """다크 오버레이 (팝업/다이얼로그 배경) 감지."""
        h, w = img.shape[:2]
        # 화면 가장자리 4곳의 밝기
        corners = [
            img[int(h*0.3):int(h*0.35), :int(w*0.1)],     # 좌측
            img[int(h*0.3):int(h*0.35), int(w*0.9):],      # 우측
            img[:int(h*0.05), int(w*0.3):int(w*0.7)],      # 상단 중앙
            img[int(h*0.95):, int(w*0.3):int(w*0.7)],      # 하단 중앙
        ]
        dark_count = sum(
            1 for c in corners
            if c.size > 0 and c.mean() < 40
        )
        return dark_count >= 3

    @staticmethod
    def _classify_color(bgr: np.ndarray) -> str:
        """BGR 값 → 색상명."""
        b, g, r = float(bgr[0]), float(bgr[1]), float(bgr[2])
        brightness = (r + g + b) / 3

        if brightness < 30:
            return "black"
        if brightness > 220 and max(r, g, b) - min(r, g, b) < 30:
            return "white"
        if brightness > 150 and max(r, g, b) - min(r, g, b) < 25:
            return "gray"

        if r > 180 and g < 100 and b < 100:
            return "red"
        if r < 100 and g > 180 and b < 100:
            return "green"
        if r < 100 and g < 100 and b > 180:
            return "blue"
        if r > 180 and g > 180 and b < 100:
            return "yellow"
        if r > 180 and g > 100 and b < 80:
            return "orange"
        if r > 150 and g < 80 and b > 150:
            return "purple"
        if r > 200 and g > 100 and b > 150:
            return "pink"
        if r < 80 and g > 180 and b > 180:
            return "cyan"

        # 가장 큰 채널 기준
        if r >= g and r >= b:
            return "red" if r > 150 else "brown"
        if g >= r and g >= b:
            return "green"
        return "blue"


# ---------------------------------------------------------------------------
# Universal Screen Classifier (YOLO-free)
# ---------------------------------------------------------------------------
class ScreenClassifier:
    """YOLO 없이 화면 유형 분류.

    OCR 텍스트 + 색상 + 레이아웃으로 범용 분류.
    """

    # 화면별 텍스트 시그니처
    SCREEN_SIGNATURES = {
        "lobby": {
            "keywords": ["play", "start", "level", "시작", "레벨", "stage"],
            "weight": 1.0,
        },
        "gameplay": {
            "keywords": ["score", "moves", "time", "점수", "이동"],
            "weight": 0.8,
        },
        "win": {
            "keywords": ["congratulations", "victory", "clear", "완료", "승리",
                         "클리어", "계속"],
            "weight": 1.0,
        },
        "fail": {
            "keywords": ["fail", "game over", "retry", "try again", "실패",
                         "다시", "도전"],
            "weight": 1.0,
        },
        "popup": {
            "keywords": ["ok", "cancel", "confirm", "확인", "취소", "닫기"],
            "weight": 0.5,
        },
        "ad": {
            "keywords": ["install", "download", "get", "설치", "다운로드",
                         "free", "reward"],
            "weight": 0.8,
        },
        "shop": {
            "keywords": ["shop", "store", "buy", "purchase", "상점", "구매",
                         "krw", "usd", "₩", "$"],
            "weight": 0.9,
        },
    }

    def classify(self, ui_state: UIState) -> Tuple[str, float]:
        """UIState → (screen_type, confidence)."""
        scores = {}

        for screen, sig in self.SCREEN_SIGNATURES.items():
            score = 0.0
            for kw in sig["keywords"]:
                matches = ui_state.find_all_text(kw)
                score += len(matches) * sig["weight"]
            scores[screen] = score

        # 다크 오버레이 보정
        if ui_state.has_dark_overlay:
            scores["popup"] = scores.get("popup", 0) + 2.0
            scores["ad"] = scores.get("ad", 0) + 1.0

        # 밝기 보정
        if ui_state.screen_brightness < 0.15:
            scores["ad"] = scores.get("ad", 0) + 1.0

        if not scores or max(scores.values()) == 0:
            return "unknown", 0.0

        best = max(scores, key=scores.get)
        total = sum(scores.values())
        conf = scores[best] / total if total > 0 else 0.0

        return best, min(conf, 1.0)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------
def analyze_screenshot(img_path: Path) -> UIState:
    """단일 스크린샷 분석 (편의 함수)."""
    vision = UniversalVision()
    return vision.analyze(img_path)
