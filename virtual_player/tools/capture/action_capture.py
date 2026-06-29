"""
Action Capture — YOLO 화면 분류 + 상태 전이 기록
=================================================
RPG / SLG 장르용 캡처 엔진.

핵심 차이점:
  RPG/SLG는 화면 전환이 빈번하고 같은 화면 내에서도 변화가 크다.
  → 픽셀 Delta 대신 **화면 타입(screen_type) 전이**를 추적.
  → "로비에서 탭 → 전투로 전환" 같은 상태 전이가 학습 데이터.

구조:
  1. 화면 분류: YOLO 모델 또는 히스토그램 fingerprint로 현재 화면 타입 판별
  2. ROI Delta: 화면 타입별 의미 있는 영역만 비교
  3. 상태 전이 기록: screen_before → action → screen_after

분류 모드:
  - yolo: YOLO 모델로 화면 분류 (가장 정확)
  - fingerprint: 색상 히스토그램 기반 유사도 매칭
  - manual: 사용자가 수동으로 현재 화면 라벨링

JSONL 추가 필드:
  - screen_before: 탭 전 화면 타입
  - screen_after: 탭 후 화면 타입
  - screen_changed: bool (화면 전환 여부)
  - transition: "lobby→battle" 형태
  - confidence: 분류 신뢰도
  - roi_deltas: {영역명: delta} (화면 타입별 ROI)
"""

import io
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .base import (
    ADBConnection,
    BaseCaptureEngine,
    SessionManager,
    compute_pixel_delta,
    compute_roi_deltas,
)

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


# ─────────────────────────────────────────────────────────────────────────────
# Screen Classifier — YOLO / Fingerprint / Manual
# ─────────────────────────────────────────────────────────────────────────────

class ScreenClassifier:
    """화면 타입 분류기 (YOLO > Fingerprint > Manual 폴백)."""

    def __init__(self, mode: str = "fingerprint",
                 yolo_model_path: Optional[str] = None,
                 fingerprint_db: Optional[Dict[str, Any]] = None,
                 screen_types: Optional[List[str]] = None):
        self.mode = mode
        self.screen_types = screen_types or []
        self._yolo_model = None
        self._fingerprint_db = fingerprint_db or {}
        self._manual_label = "unknown"

        if mode == "yolo" and yolo_model_path:
            self._load_yolo(yolo_model_path)

    def _load_yolo(self, model_path: str):
        try:
            from ultralytics import YOLO
            self._yolo_model = YOLO(model_path)
        except Exception:
            self._yolo_model = None

    def classify(self, img_bytes: bytes) -> Tuple[str, float]:
        """
        화면 분류.

        Returns:
            (screen_type, confidence)
        """
        if self.mode == "yolo" and self._yolo_model:
            return self._classify_yolo(img_bytes)
        elif self.mode == "fingerprint":
            return self._classify_fingerprint(img_bytes)
        else:
            return self._manual_label, 1.0

    def _classify_yolo(self, img_bytes: bytes) -> Tuple[str, float]:
        if not _HAS_PIL or not self._yolo_model:
            return "unknown", 0.0
        try:
            img = Image.open(io.BytesIO(img_bytes))
            results = self._yolo_model.predict(img, verbose=False)
            if results and len(results) > 0:
                result = results[0]
                if result.probs is not None:
                    top_idx = result.probs.top1
                    conf = float(result.probs.top1conf)
                    label = result.names[top_idx]
                    return label, round(conf, 4)
            return "unknown", 0.0
        except Exception:
            return "unknown", 0.0

    def _classify_fingerprint(self, img_bytes: bytes) -> Tuple[str, float]:
        """색상 히스토그램 기반 매칭."""
        if not _HAS_PIL or not self._fingerprint_db:
            return "unknown", 0.0
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((128, 128))
            arr = np.array(img)
            hist = self._compute_histogram(arr)

            best_type = "unknown"
            best_sim = 0.0
            for stype, ref_hist in self._fingerprint_db.items():
                ref = np.array(ref_hist, dtype=np.float32)
                sim = self._histogram_similarity(hist, ref)
                if sim > best_sim:
                    best_sim = sim
                    best_type = stype

            return best_type, round(best_sim, 4)
        except Exception:
            return "unknown", 0.0

    def set_manual_label(self, label: str):
        self._manual_label = label

    @staticmethod
    def _compute_histogram(arr: np.ndarray, bins: int = 32) -> np.ndarray:
        """RGB 히스토그램 (3채널 × bins)."""
        hists = []
        for c in range(3):
            h, _ = np.histogram(arr[:, :, c].ravel(), bins=bins, range=(0, 256))
            h = h.astype(np.float32)
            total = h.sum()
            if total > 0:
                h /= total
            hists.append(h)
        return np.concatenate(hists)

    @staticmethod
    def _histogram_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """히스토그램 교차 유사도 (0~1)."""
        if len(a) != len(b):
            return 0.0
        return float(np.minimum(a, b).sum())

    def build_fingerprint(self, img_bytes: bytes) -> Optional[list]:
        """현재 프레임의 fingerprint 생성 (DB 등록용)."""
        if not _HAS_PIL:
            return None
        try:
            img = Image.open(io.BytesIO(img_bytes)).convert("RGB").resize((128, 128))
            arr = np.array(img)
            hist = self._compute_histogram(arr)
            return hist.tolist()
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────────────────────
# State Machine — 화면 전이 추적
# ─────────────────────────────────────────────────────────────────────────────

class ScreenStateMachine:
    """화면 전이 패턴 기록/통계."""

    def __init__(self):
        self.current_screen: str = "unknown"
        self.transitions: List[Dict[str, str]] = []
        self.transition_counts: Dict[str, int] = defaultdict(int)
        self.screen_durations: Dict[str, float] = defaultdict(float)
        self._screen_enter_time: float = 0.0

    def update(self, new_screen: str, action: str = "") -> Optional[dict]:
        """
        화면 전이 업데이트.

        Returns:
            전이 발생 시 {from, to, action, duration} 딕셔너리. 미발생 시 None.
        """
        if new_screen == self.current_screen:
            return None

        now = time.time()
        duration = now - self._screen_enter_time if self._screen_enter_time > 0 else 0

        transition = {
            "from": self.current_screen,
            "to": new_screen,
            "action": action,
            "duration_on_prev": round(duration, 2),
            "timestamp": datetime.now().isoformat(),
        }
        self.transitions.append(transition)

        key = f"{self.current_screen}→{new_screen}"
        self.transition_counts[key] += 1
        self.screen_durations[self.current_screen] += duration

        self.current_screen = new_screen
        self._screen_enter_time = now

        return transition

    def get_summary(self) -> dict:
        return {
            "total_transitions": len(self.transitions),
            "top_transitions": dict(
                sorted(self.transition_counts.items(), key=lambda x: -x[1])[:10]
            ),
            "screen_time": dict(
                sorted(self.screen_durations.items(), key=lambda x: -x[1])
            ),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Action Capture Engine (RPG / SLG)
# ═══════════════════════════════════════════════════════════════════════════════

class ActionCaptureEngine(BaseCaptureEngine):
    """
    RPG/SLG 장르: 화면 분류 + 상태 전이 기반 캡처.

    설정:
        classify_mode: "yolo" | "fingerprint" | "manual"
        yolo_model_path: YOLO cls 모델 경로
        fingerprint_db_path: fingerprint DB JSON 경로
        screen_types: 가능한 화면 타입 목록
        roi_per_screen: 화면 타입별 ROI 정의
            {"lobby": {"gold": (x,y,w,h), "level": (x,y,w,h)}, ...}
        after_delay: After 캡처 대기 시간 (초)
    """

    GENRE = "action"

    def __init__(self, adb: ADBConnection, session: SessionManager, **kwargs):
        super().__init__(adb, session, kwargs.get("log_fn"))
        self.after_delay: float = kwargs.get("after_delay", 0.8)

        # 화면 분류기
        classify_mode = kwargs.get("classify_mode", "fingerprint")
        yolo_path = kwargs.get("yolo_model_path")
        fp_db = self._load_fingerprint_db(kwargs.get("fingerprint_db_path"))
        screen_types = kwargs.get("screen_types", [])

        self.classifier = ScreenClassifier(
            mode=classify_mode,
            yolo_model_path=yolo_path,
            fingerprint_db=fp_db,
            screen_types=screen_types,
        )

        # 화면 타입별 ROI
        self.roi_per_screen: Dict[str, Dict[str, Tuple[int, int, int, int]]] = \
            kwargs.get("roi_per_screen", {})

        # 상태 머신
        self.state_machine = ScreenStateMachine()

        # fingerprint 학습 모드
        self._learning_mode: bool = kwargs.get("learning_mode", False)

    @staticmethod
    def _load_fingerprint_db(path: Optional[str]) -> dict:
        if not path:
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def on_start(self):
        self.detect_resolution()
        self.prev_frame_bytes = b""

        self.log(f"[Action] Capture started  mode={self.classifier.mode}", tag="accent")
        self.log(f"[Action] Screen types: {self.classifier.screen_types or 'auto'}")
        self.log(f"[Action] ROI screens: {list(self.roi_per_screen.keys())}")
        if self._learning_mode:
            self.log("[Action] Learning mode ON — fingerprints will be saved", tag="accent")

        # 초기 화면 분류
        initial = self.adb.screenshot_bytes()
        if initial:
            stype, conf = self.classifier.classify(initial)
            self.state_machine.current_screen = stype
            self.state_machine._screen_enter_time = time.time()
            self.log(f"[Action] Initial screen: {stype} ({conf:.2%})")

    def on_stop(self):
        summary = self.state_machine.get_summary()
        self.log(f"[Action] Transitions: {summary['total_transitions']}")
        if summary["top_transitions"]:
            self.log(f"[Action] Top: {summary['top_transitions']}")

        # 요약 저장
        summary_entry = {
            "event": "session_summary",
            "genre": self.GENRE,
            "episode_id": self.session.episode_id,
            "timestamp": datetime.now().isoformat(),
            "summary": summary,
        }
        self.session.write_log(summary_entry)

    def process_event(self, evt: dict):
        """
        Action 캡처:
        1. Before 스크린샷 → 화면 분류
        2. (대기)
        3. After 스크린샷 → 화면 분류
        4. 상태 전이 기록 + ROI Delta
        """
        app_dir = self.session.app_dir
        seq = self.session.record_action()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ── Before ──
        before_bytes = self.adb.screenshot_bytes()
        if not before_bytes:
            self.log(f"[{self.session.app_label}] #{seq} FAILED", tag="error")
            return

        before_name = f"action_{ts}_{seq:04d}_before.png"
        (app_dir / before_name).write_bytes(before_bytes)

        screen_before, conf_before = self.classifier.classify(before_bytes)

        # ── After ──
        time.sleep(self.after_delay)
        after_bytes = self.adb.screenshot_bytes()
        after_name = None
        screen_after = screen_before
        conf_after = conf_before

        if after_bytes:
            after_name = f"action_{ts}_{seq:04d}_after.png"
            (app_dir / after_name).write_bytes(after_bytes)
            self.session.total_captures += 1
            screen_after, conf_after = self.classifier.classify(after_bytes)

        # ── 상태 전이 ──
        action_str = self.format_action(evt)
        transition = self.state_machine.update(screen_after, action_str)
        screen_changed = transition is not None

        # ── ROI Delta (화면 타입별) ──
        roi_deltas = None
        if after_bytes and screen_before in self.roi_per_screen:
            rois = self.roi_per_screen[screen_before]
            roi_deltas = compute_roi_deltas(before_bytes, after_bytes, rois)

        # ── Log ──
        parts = [f"[{self.session.app_label}] #{seq}  {action_str}"]
        parts.append(f"[{screen_before}→{screen_after}]")
        if screen_changed:
            parts.append("TRANSITION")
        if conf_before < 0.5:
            parts.append(f"conf={conf_before:.0%}")
        if roi_deltas:
            changed_rois = {k: f"{v:.2%}" for k, v in roi_deltas.items() if v > 0.01}
            if changed_rois:
                parts.append(f"roi={changed_rois}")
        self.log("  ".join(parts), tag="accent" if screen_changed else "info")

        # ── JSONL ──
        entry = self.build_base_entry(evt, seq, before_name, after_name)
        entry["screen_before"] = screen_before
        entry["screen_after"] = screen_after
        entry["confidence_before"] = conf_before
        entry["confidence_after"] = conf_after
        entry["screen_changed"] = screen_changed
        entry["transition"] = f"{screen_before}→{screen_after}" if screen_changed else None
        if roi_deltas:
            entry["roi_deltas"] = {k: v for k, v in roi_deltas.items() if v >= 0}
        if transition:
            entry["transition_detail"] = transition

        self.session.write_log(entry)

        # ── Learning mode: fingerprint 저장 ──
        if self._learning_mode and after_bytes:
            self._save_learning_data(after_bytes, screen_after, conf_after, app_dir, seq)

    def _save_learning_data(self, img_bytes: bytes, screen_type: str,
                            confidence: float, app_dir: Path, seq: int):
        """학습 모드: 분류 결과가 낮은 프레임의 fingerprint를 저장."""
        if confidence > 0.8:
            return
        fp = self.classifier.build_fingerprint(img_bytes)
        if fp is None:
            return
        learn_dir = app_dir / "_learning"
        learn_dir.mkdir(exist_ok=True)
        entry = {
            "seq": seq,
            "screen_type": screen_type,
            "confidence": confidence,
            "fingerprint": fp,
            "timestamp": datetime.now().isoformat(),
        }
        learn_path = learn_dir / "fingerprint_candidates.jsonl"
        try:
            with open(learn_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def register_fingerprint(self, screen_type: str, img_bytes: bytes) -> bool:
        """현재 프레임을 특정 화면 타입의 fingerprint로 등록."""
        fp = self.classifier.build_fingerprint(img_bytes)
        if fp is not None:
            self.classifier._fingerprint_db[screen_type] = fp
            self.log(f"[Action] Registered fingerprint: {screen_type}", tag="success")
            return True
        return False

    def save_fingerprint_db(self, path: str):
        """현재 fingerprint DB를 파일로 저장."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.classifier._fingerprint_db, f, indent=2)
            self.log(f"[Action] Fingerprint DB saved: {path}", tag="success")
        except Exception as e:
            self.log(f"[Action] DB save failed: {e}", tag="error")
