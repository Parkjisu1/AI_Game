"""
Level Design Extractor v4 — Tmux Interactive Mode
===================================================
녹화 프레임 + recording.json 이벤트 로그를 분석하여
각 스테이지의 초기 보드(시작 배치)를 정밀 추출.

21개 기능 통합:
  A. 감지 정확도: 멀티프레임 투표, OCR, 세분화 분류, 좌표 가중치, 조작전 보장
  B. 보드 크롭: 게임별 프로필, 그리드 셀 자동감지, fallback
  C. 출력: FieldMap JSON, 그리드 크기 판별, HTML 리포트, diff 리포트
  D. QA: 연번 누락, 보드 유효성, 플레이중 오탐, 인터랙티브 확인
  E. 인프라: watch 모드, resume 캐시, 병렬처리

사용법:
  python level_design_extractor_tmux.py \\
    --frames-dir <프레임폴더> --model <YOLO.pt> --output-dir <출력폴더> \\
    --recording <recording.json> --game balloonflow \\
    --crop-board --preset recall --html-report

  # watch 모드 (실시간 감시)
  python level_design_extractor_tmux.py ... --watch

  # resume (이전 분류 캐시 재사용)
  python level_design_extractor_tmux.py ... --resume

  # diff (이전 결과와 비교)
  python level_design_extractor_tmux.py ... --diff-dir <이전출력>

  # 인터랙티브 QA
  python level_design_extractor_tmux.py ... --interactive-qa
"""

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    pass

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

SCRIPT_DIR = Path(__file__).resolve().parent
PROFILES_PATH = SCRIPT_DIR / "game_profiles.json"


# ══════════════════════════════════════════════════════════════
#  1. Tmux Display
# ══════════════════════════════════════════════════════════════

class TmuxDisplay:
    def __init__(self):
        self.stages = {}
        self.log_lines = []
        self.max_log = 15
        self.stats = {}
        self.qa_issues = []
        self._cols = shutil.get_terminal_size((80, 24)).columns

    def _bar(self, cur, tot, w=40):
        if tot == 0:
            return "[" + " " * w + "]"
        f = int(w * cur / tot)
        return f"[{'█' * f}{'░' * (w - f)}] {cur / tot * 100:5.1f}% ({cur}/{tot})"

    def _div(self, title=""):
        w = self._cols - 2
        if title:
            p = w - len(title) - 4
            return f"{'─' * (p // 2)}┤ {title} ├{'─' * (p - p // 2)}"
        return "─" * w

    def set_stage(self, n, s, d=""):
        icons = {"wait": "○", "run": "◉", "done": "✓", "fail": "✗", "skip": "→"}
        self.stages[n] = (icons.get(s, "?"), d)

    def set_stat(self, k, v):
        self.stats[k] = v

    def log(self, msg):
        self.log_lines.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        if len(self.log_lines) > self.max_log:
            self.log_lines = self.log_lines[-self.max_log:]

    def qa(self, lvl, issue):
        self.qa_issues.append((lvl, issue))

    def progress(self, cur, tot, label=""):
        sys.stdout.write(f"\r  {label} {self._bar(cur, tot)}")
        sys.stdout.flush()

    def render(self):
        lines = ["", self._div("PIPELINE")]
        for n, (ic, d) in self.stages.items():
            lines.append(f"  {ic} {n}" + (f"  — {d}" if d else ""))
        if self.stats:
            lines += ["", self._div("STATS")]
            for k, v in self.stats.items():
                lines.append(f"  {k}: {v}")
        if self.qa_issues:
            lines += ["", self._div("QA ISSUES")]
            for lv, iss in self.qa_issues[-5:]:
                lines.append(f"  [Lv{lv:03d}] {iss}")
            if len(self.qa_issues) > 5:
                lines.append(f"  ... 외 {len(self.qa_issues) - 5}건")
        if self.log_lines:
            lines += ["", self._div("LOG")]
            for l in self.log_lines[-8:]:
                lines.append(f"  {l}")
        lines.append(self._div())
        print("\n".join(lines))


# ══════════════════════════════════════════════════════════════
#  2. Game Profile (#6)
# ══════════════════════════════════════════════════════════════

def load_game_profile(game_id):
    if PROFILES_PATH.exists():
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            profiles = json.load(f)
        if game_id in profiles:
            return profiles[game_id]
    return None


# ══════════════════════════════════════════════════════════════
#  3. Image Utils
# ══════════════════════════════════════════════════════════════

def compute_image_hash(img_path, hash_size=16):
    img = Image.open(img_path).convert("L").resize((hash_size, hash_size), Image.LANCZOS)
    arr = np.array(img)
    return "".join("1" if b else "0" for b in (arr > arr.mean()).flatten())


def hamming_distance(h1, h2):
    return sum(c1 != c2 for c1, c2 in zip(h1, h2))


def compute_frame_delta(path_a, path_b, size=(270, 480)):
    a = np.array(Image.open(path_a).convert("L").resize(size, Image.LANCZOS), dtype=np.float32)
    b = np.array(Image.open(path_b).convert("L").resize(size, Image.LANCZOS), dtype=np.float32)
    return float(np.mean(np.abs(a - b)) / 255.0)


def color_distance(c1, c2):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


# ══════════════════════════════════════════════════════════════
#  4. Level Number OCR (#2)
# ══════════════════════════════════════════════════════════════

def _cv2_digit_recognize(thresh_roi):
    """cv2 contour 기반 숫자 인식 (pytesseract 없이).

    7-segment 스타일 매칭은 아니고, contour의 종횡비+면적 비율로
    0-9를 추정하는 경량 방식. 게임 UI의 큰 숫자에 대체로 동작.
    """
    contours, _ = cv2.findContours(thresh_roi, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    h_roi, w_roi = thresh_roi.shape[:2]
    min_h = h_roi * 0.3
    min_area = h_roi * w_roi * 0.005

    # 숫자 후보: 세로로 충분히 크고 면적이 있는 contour
    digits = []
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = cv2.contourArea(c)
        if ch < min_h or area < min_area:
            continue
        # 종횡비로 대략 판별
        aspect = cw / max(ch, 1)
        fill = area / max(cw * ch, 1)

        # 너무 넓으면 숫자가 아님 (배경 박스 등)
        if aspect > 1.2:
            continue

        digit_val = _aspect_to_digit(aspect, fill)
        digits.append((x, digit_val))

    if not digits:
        return None

    # x 좌표 순서로 정렬 → 숫자 조합
    digits.sort(key=lambda d: d[0])
    number_str = "".join(str(d[1]) for d in digits)

    try:
        return int(number_str)
    except ValueError:
        return None


def _aspect_to_digit(aspect, fill):
    """contour 종횡비와 fill ratio로 숫자 추정 (heuristic)."""
    # 1: 매우 좁음
    if aspect < 0.35:
        return 1
    # 0, 8: fill ratio 높음 + 적당한 폭
    if fill > 0.55 and aspect > 0.45:
        return 0 if fill > 0.65 else 8
    # 4, 7: fill 낮음
    if fill < 0.35:
        return 7 if aspect < 0.55 else 4
    # 나머지: 중간 범위 — 3, 5, 6, 9, 2
    if aspect < 0.5:
        return 3
    if fill > 0.5:
        return 6
    return 5


def ocr_level_number(img_path, profile=None):
    """스크린샷 상단에서 'Level XXX' 숫자를 추출."""
    if not CV2_AVAILABLE:
        return None

    img = cv2.imread(str(img_path))
    if img is None:
        return None

    h, w = img.shape[:2]

    # 레벨 텍스트 영역 크롭 (상단 중앙)
    if profile and "level_number_ocr" in profile:
        r = profile["level_number_ocr"]["region_ratio"]
        x1, y1 = int(w * r[0]), int(h * r[1])
        x2, y2 = int(w * r[2]), int(h * r[3])
    else:
        x1, y1 = int(w * 0.25), int(h * 0.02)
        x2, y2 = int(w * 0.75), int(h * 0.08)

    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    # 1) pytesseract 사용 가능하면
    if OCR_AVAILABLE:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        try:
            text = pytesseract.image_to_string(thresh, config="--psm 7 digits")
            nums = re.findall(r'\d+', text)
            if nums:
                return int(nums[0])
        except Exception:
            pass

    # 2) cv2 contour 기반 fallback
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)

    # 밝은 텍스트(흰색) on 어두운 배경 → THRESH_BINARY
    _, thresh_w = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    result = _cv2_digit_recognize(thresh_w)
    if result is not None:
        return result

    # 어두운 텍스트 on 밝은 배경 → THRESH_BINARY_INV
    _, thresh_b = cv2.threshold(gray, 100, 255, cv2.THRESH_BINARY_INV)
    result = _cv2_digit_recognize(thresh_b)
    if result is not None:
        return result

    # 3) Adaptive threshold (그라데이션 배경)
    adaptive = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 31, 10)
    result = _cv2_digit_recognize(adaptive)
    return result


# ══════════════════════════════════════════════════════════════
#  5. YOLO Classification (#3 세분화 포함)
# ══════════════════════════════════════════════════════════════

def _classify_batch(args):
    """병렬 처리용 배치 분류 (worker)."""
    model_path, batch_paths, conf_threshold = args
    model = YOLO(str(model_path))
    preds = model.predict(batch_paths, verbose=False, conf=conf_threshold)
    results = []
    for j, pred in enumerate(preds):
        if pred.probs is not None:
            label = model.names[int(pred.probs.top1)]
            conf = float(pred.probs.top1conf)
            # 세분화: 상위 3개 클래스 저장 (#3)
            top3 = []
            probs = pred.probs.data.cpu().numpy()
            top_indices = probs.argsort()[-3:][::-1]
            for ti in top_indices:
                top3.append({"label": model.names[int(ti)], "conf": round(float(probs[ti]), 4)})
        else:
            label, conf, top3 = "unknown", 0.0, []

        results.append({
            "frame": Path(batch_paths[j]).name,
            "path": batch_paths[j],
            "label": label,
            "confidence": round(conf, 4),
            "top3": top3,
        })
    return results


def classify_frames_yolo(model_path, frames, conf_threshold, display, parallel=False):
    if not YOLO_AVAILABLE:
        display.log("ERROR: ultralytics 미설치")
        sys.exit(1)

    total = len(frames)
    batch_size = 16

    if parallel and total > 64:
        # (#19) 병렬 처리 — 모델 1회 로드, 대형 배치로 분할
        display.log(f"병렬 분류 모드 (batch_size={batch_size * 4})")
        model = YOLO(str(model_path))
        results = []
        big_batch = batch_size * 4  # GPU 활용 극대화

        for i in range(0, total, big_batch):
            batch = frames[i:i + big_batch]
            preds = model.predict([str(f) for f in batch], verbose=False,
                                  conf=conf_threshold, batch=batch_size)
            for j, pred in enumerate(preds):
                if pred.probs is not None:
                    label = model.names[int(pred.probs.top1)]
                    conf = float(pred.probs.top1conf)
                    probs = pred.probs.data.cpu().numpy()
                    top_indices = probs.argsort()[-3:][::-1]
                    top3 = [{"label": model.names[int(ti)], "conf": round(float(probs[ti]), 4)}
                            for ti in top_indices]
                else:
                    label, conf, top3 = "unknown", 0.0, []
                results.append({
                    "frame": batch[j].name,
                    "path": str(batch[j]),
                    "label": label,
                    "confidence": round(conf, 4),
                    "top3": top3,
                })
            display.progress(min(i + big_batch, total), total, "분류")
        print()
        return results
    else:
        # 순차 처리
        model = YOLO(str(model_path))
        results = []
        for i in range(0, total, batch_size):
            batch = frames[i:i + batch_size]
            preds = model.predict([str(f) for f in batch], verbose=False, conf=conf_threshold)
            for j, pred in enumerate(preds):
                if pred.probs is not None:
                    label = model.names[int(pred.probs.top1)]
                    conf = float(pred.probs.top1conf)
                    probs = pred.probs.data.cpu().numpy()
                    top_indices = probs.argsort()[-3:][::-1]
                    top3 = [{"label": model.names[int(ti)], "conf": round(float(probs[ti]), 4)}
                            for ti in top_indices]
                else:
                    label, conf, top3 = "unknown", 0.0, []
                results.append({
                    "frame": batch[j].name,
                    "path": str(batch[j]),
                    "label": label,
                    "confidence": round(conf, 4),
                    "top3": top3,
                })
            display.progress(min(i + batch_size, total), total, "분류")
        print()
        return results


# ══════════════════════════════════════════════════════════════
#  6. Smoothing & Multi-frame Voting (#1)
# ══════════════════════════════════════════════════════════════

def smooth_classifications(classifications, min_run=5, display=None):
    if not classifications:
        return classifications

    smoothed = [dict(c) for c in classifications]
    labels = [c["label"] for c in smoothed]
    n = len(labels)

    runs, i = [], 0
    while i < n:
        j = i
        while j < n and labels[j] == labels[i]:
            j += 1
        runs.append((i, j - i, labels[i]))
        i = j

    changed = 0
    for ri in range(1, len(runs) - 1):
        start, length, label = runs[ri]
        if runs[ri - 1][2] == runs[ri + 1][2] and length < min_run:
            for k in range(start, start + length):
                smoothed[k]["label"] = runs[ri - 1][2]
                smoothed[k]["smoothed_from"] = label
            changed += 1

    if display and changed:
        display.log(f"스무딩: {changed}개 구간 보정")
    return smoothed


def multiframe_vote(classifications, start_idx, window=3):
    """(#1) 멀티프레임 투표 — start_idx 주변 window 프레임의 과반수 라벨."""
    n = len(classifications)
    votes = []
    for i in range(max(0, start_idx), min(n, start_idx + window)):
        votes.append(classifications[i]["label"])
    if not votes:
        return "unknown"
    return Counter(votes).most_common(1)[0][0]


# ══════════════════════════════════════════════════════════════
#  7. Stage Detection — 이벤트 로그 + YOLO (#4, #5)
# ══════════════════════════════════════════════════════════════

def build_frame_index(frames):
    return {f.name: i for i, f in enumerate(frames)}


def is_start_button_area(x, y, screen_w, screen_h):
    """(#4) 좌표가 '시작 버튼' 영역인지 판단."""
    # 일반적으로 화면 하단 중앙~우측
    rel_x = x / screen_w if screen_w > 0 else 0.5
    rel_y = y / screen_h if screen_h > 0 else 0.5
    return rel_y > 0.7 and 0.2 < rel_x < 0.8


def detect_stages_with_log(events, classifications, frame_index, frame_files,
                           rec_meta, display, vote_window=3):
    """이벤트 로그 + YOLO 교차 검증. (#4 좌표 가중치, #5 조작전 보장)"""
    cls_map = {c["frame"]: c for c in classifications}
    screen_w = rec_meta.get("screen_width", 1080)
    screen_h = rec_meta.get("screen_height", 1920)
    stages = []

    n_events = len(events)
    i = 0

    while i < n_events:
        evt = events[i]
        before = evt.get("screenshot_before", "")
        after = evt.get("screenshot_after", "")
        before_cls = cls_map.get(before, {}).get("label", "unknown")
        after_cls = cls_map.get(after, {}).get("label", "unknown")

        # 전환: 비-gameplay → gameplay
        if before_cls != "gameplay" and after_cls == "gameplay":
            entry_idx = frame_index.get(after, -1)
            entry_conf = cls_map.get(after, {}).get("confidence", 0)

            # (#1) 멀티프레임 투표로 확인
            if entry_idx >= 0:
                voted = multiframe_vote(classifications, entry_idx, vote_window)
                if voted != "gameplay":
                    i += 1
                    continue  # 투표에서 gameplay 아님 → 스킵

            # (#4) 시작 버튼 영역 tap이면 신뢰도 보너스
            is_start_tap = (evt.get("type") == "tap" and
                            is_start_button_area(evt.get("x", 0), evt.get("y", 0),
                                                 screen_w, screen_h))

            # (#5) 유저 조작 전 보장: gameplay 진입 후 첫 tap/swipe의 before
            initial_frame = after
            initial_idx = entry_idx

            j = i + 1
            while j < n_events:
                next_before = events[j].get("screenshot_before", "")
                next_cls = cls_map.get(next_before, {}).get("label", "unknown")
                if next_cls == "gameplay":
                    initial_frame = next_before
                    initial_idx = frame_index.get(next_before, entry_idx)
                    break
                j += 1

            stages.append({
                "entry_frame": after,
                "entry_frame_idx": entry_idx,
                "initial_board_frame": initial_frame,
                "initial_board_idx": initial_idx,
                "confidence": entry_conf,
                "transition_from": before_cls,
                "event_index": i,
                "is_start_tap": is_start_tap,
                "source": "event_log",
            })

            display.log(f"전환: {before}({before_cls}) → {after}(gameplay)"
                        + (" [시작버튼]" if is_start_tap else ""))

            # gameplay 구간 스킵
            while i < n_events:
                af = events[i].get("screenshot_after", "")
                if cls_map.get(af, {}).get("label", "unknown") != "gameplay":
                    break
                i += 1
            continue

        i += 1

    return stages


def detect_stages_yolo_only(classifications, min_gap=3):
    starts = []
    n = len(classifications)
    i = 0
    while i < n:
        if classifications[i]["label"] != "gameplay":
            gap_start = i
            while i < n and classifications[i]["label"] != "gameplay":
                i += 1
            if i < n and (i - gap_start) >= min_gap:
                starts.append(i)
        else:
            i += 1

    if classifications and classifications[0]["label"] == "gameplay":
        if not starts or starts[0] != 0:
            starts.insert(0, 0)

    return [{"initial_board_idx": idx,
             "initial_board_frame": classifications[idx]["frame"],
             "confidence": classifications[idx]["confidence"],
             "transition_from": classifications[idx - 1]["label"] if idx > 0 else "start",
             "source": "yolo_only"} for idx in starts]


def find_settled_frame(frame_files, classifications, start_idx,
                       settle_frames=3, settle_threshold=0.02, max_search=15):
    n = len(frame_files)
    end = min(start_idx + max_search, n - 1)
    for i in range(start_idx, end - settle_frames + 1):
        if not all(classifications[i + k]["label"] == "gameplay"
                   for k in range(settle_frames) if i + k < len(classifications)):
            continue
        if all(compute_frame_delta(frame_files[i + k], frame_files[i + k + 1]) <= settle_threshold
               for k in range(settle_frames - 1)):
            return i
    return start_idx


# ══════════════════════════════════════════════════════════════
#  8. Deduplication
# ══════════════════════════════════════════════════════════════

def deduplicate_stages(stages, frame_files, hash_threshold=20, display=None):
    filtered, skipped, known = [], [], []
    for s in stages:
        idx = s["initial_board_idx"]
        if idx < 0 or idx >= len(frame_files):
            skipped.append(s)
            continue
        h = compute_image_hash(frame_files[idx])
        if any(hamming_distance(h, kh) <= hash_threshold for kh in known):
            skipped.append(s)
        else:
            filtered.append(s)
            known.append(h)
    if display and skipped:
        display.log(f"중복 제거: {len(skipped)}개 스킵")
    return filtered, skipped


# ══════════════════════════════════════════════════════════════
#  9. Board Crop (#6 프로필, #7 그리드 감지, #8 fallback)
# ══════════════════════════════════════════════════════════════

def crop_board(img_path, output_path, profile=None):
    if not CV2_AVAILABLE:
        shutil.copy2(img_path, output_path)
        return False, {}

    img = cv2.imread(str(img_path))
    if img is None:
        shutil.copy2(img_path, output_path)
        return False, {}

    h, w = img.shape[:2]
    bd = profile.get("board_detection", {}) if profile else {}

    # HSV contour detection
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lo = np.array(bd.get("hsv_lower", [100, 20, 120]))
    hi = np.array(bd.get("hsv_upper", [160, 100, 230]))
    mask = cv2.inRange(hsv, lo, hi)
    ks = bd.get("morph_kernel", 15)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (ks, ks)))

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    min_area = w * h * bd.get("min_area_ratio", 0.1)
    ar = bd.get("aspect_range", [0.7, 1.4])

    best, best_a = None, 0
    for c in contours:
        x, y, cw, ch = cv2.boundingRect(c)
        area = cw * ch
        asp = cw / max(ch, 1)
        if area > min_area and ar[0] < asp < ar[1] and area > best_a:
            best_a = area
            best = (x, y, cw, ch)

    # (#8) Fallback: edge detection
    if best is None:
        edges = cv2.Canny(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), 30, 100)
        edges = cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=3)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            x, y, cw, ch = cv2.boundingRect(c)
            area = cw * ch
            if area > min_area and 0.65 < cw / max(ch, 1) < 1.5 and area > best_a:
                best_a = area
                best = (x, y, cw, ch)

    # (#8) Fallback: 중앙 크롭
    if best is None:
        fb = profile.get("fallback_crop", {}) if profile else {}
        xr = fb.get("center_x_ratio", [0.05, 0.95])
        yr = fb.get("center_y_ratio", [0.15, 0.65])
        x1, x2 = int(w * xr[0]), int(w * xr[1])
        y1, y2 = int(h * yr[0]), int(h * yr[1])
        board = img[y1:y2, x1:x2]
        cv2.imwrite(str(output_path), board)
        return True, {"method": "fallback_center", "grid_rows": 0, "grid_cols": 0}

    x, y, cw, ch = best
    br = bd.get("border_ratio", 0.04)
    b = int(min(cw, ch) * br)
    roi = img[y + b:y + ch - b, x + b:x + cw - b]
    if roi.size == 0:
        shutil.copy2(img_path, output_path)
        return False, {}

    # Grid cell extraction
    gvp = bd.get("grid_variance_percentile", 40)
    row_std = np.std(roi.astype(float), axis=1).mean(axis=1)
    col_std = np.std(roi.astype(float), axis=0).mean(axis=1)
    active_r = np.where(row_std > np.percentile(row_std, gvp))[0]
    active_c = np.where(col_std > np.percentile(col_std, gvp))[0]

    meta = {"method": "hsv_contour"}

    if len(active_r) > 10 and len(active_c) > 10:
        grid = roi[active_r[0]:active_r[-1] + 1, active_c[0]:active_c[-1] + 1]

        # (#7) 그리드 크기 자동 감지 — Hough lines 또는 주기 분석
        grid_rows, grid_cols = detect_grid_size(grid)
        meta["grid_rows"] = grid_rows
        meta["grid_cols"] = grid_cols

        cv2.imwrite(str(output_path), grid)
        return True, meta

    cv2.imwrite(str(output_path), roi)
    return True, meta


# ══════════════════════════════════════════════════════════════
#  10. Grid Size Detection (#7, #10)
# ══════════════════════════════════════════════════════════════

def detect_grid_size(grid_img):
    """(#7, #10) 크롭된 보드에서 그리드 크기(rows x cols) 자동 판별.

    FFT 주파수 분석으로 셀의 반복 주기를 감지.
    """
    if not CV2_AVAILABLE:
        return 0, 0

    gray = cv2.cvtColor(grid_img, cv2.COLOR_BGR2GRAY) if len(grid_img.shape) == 3 else grid_img
    h, w = gray.shape

    def fft_dominant_period(profile):
        """1D 프로파일의 FFT에서 지배적 주기(셀 크기) 추출."""
        n = len(profile)
        if n < 8:
            return 0

        # DC 제거 + 윈도잉
        sig = profile.astype(float) - profile.mean()
        window = np.hanning(n)
        sig = sig * window

        fft = np.abs(np.fft.rfft(sig))
        freqs = np.fft.rfftfreq(n)

        # DC(0Hz) 무시, 너무 높은 주파수(노이즈) 무시
        min_period = max(n // 50, 4)  # 최소 셀 크기 4px
        max_period = n // 2  # 최소 2개 셀
        min_freq_idx = max(1, int(n / max_period)) if max_period > 0 else 1
        max_freq_idx = min(len(fft) - 1, int(n / min_period)) if min_period > 0 else len(fft) - 1

        if min_freq_idx >= max_freq_idx:
            return 0

        search = fft[min_freq_idx:max_freq_idx + 1]
        if len(search) == 0:
            return 0

        peak_idx = np.argmax(search) + min_freq_idx
        if freqs[peak_idx] == 0:
            return 0

        period = 1.0 / freqs[peak_idx]
        return period

    # 행/열 프로파일 → FFT
    row_profile = gray.mean(axis=1)  # 가로 평균 → 세로 방향 주기
    col_profile = gray.mean(axis=0)  # 세로 평균 → 가로 방향 주기

    row_period = fft_dominant_period(row_profile)
    col_period = fft_dominant_period(col_profile)

    rows = int(round(h / row_period)) if row_period > 3 else 0
    cols = int(round(w / col_period)) if col_period > 3 else 0

    # sanity: 그리드 크기가 너무 크거나 작으면 0
    if rows < 2 or rows > 60:
        rows = 0
    if cols < 2 or cols > 60:
        cols = 0

    return rows, cols


# ══════════════════════════════════════════════════════════════
#  11. FieldMap JSON Generation (#9)
# ══════════════════════════════════════════════════════════════

def generate_fieldmap_json(board_img_path, grid_rows, grid_cols, profile, level_num):
    """(#9) 크롭된 보드에서 FieldMap JSON 생성."""
    if not CV2_AVAILABLE or grid_rows < 2 or grid_cols < 2:
        return None

    img = cv2.imread(str(board_img_path))
    if img is None:
        return None

    h, w = img.shape[:2]
    cell_h = h / grid_rows
    cell_w = w / grid_cols

    palette = []
    if profile and "color_palette_28" in profile:
        palette = profile["color_palette_28"]

    field_map = []
    color_counts = Counter()

    # 팔레트를 numpy 배열로 미리 변환 (벡터 연산용)
    palette_arr = None
    if palette:
        palette_arr = np.array([p["rgb"] for p in palette], dtype=np.float32)
        palette_ids = [p["id"] for p in palette]

    for r in range(grid_rows):
        row = []
        for c in range(grid_cols):
            # 셀 내부 중앙 60% 영역
            ry1 = int(r * cell_h + cell_h * 0.2)
            ry2 = int(r * cell_h + cell_h * 0.8)
            rx1 = int(c * cell_w + cell_w * 0.2)
            rx2 = int(c * cell_w + cell_w * 0.8)
            ry1, ry2 = max(0, ry1), min(h, max(ry1 + 1, ry2))
            rx1, rx2 = max(0, rx1), min(w, max(rx1 + 1, rx2))

            region = img[ry1:ry2, rx1:rx2]
            if region.size == 0:
                row.append("..")
                continue

            # 최빈색 추출: 픽셀을 양자화(8단계)하여 최빈 bin 사용
            quantized = (region // 32) * 32 + 16  # 256→8레벨 양자화
            flat = quantized.reshape(-1, 3)
            # 각 픽셀을 키로 변환하여 카운트
            keys = flat[:, 0].astype(np.int32) * 65536 + flat[:, 1].astype(np.int32) * 256 + flat[:, 2].astype(np.int32)
            unique, counts = np.unique(keys, return_counts=True)
            mode_key = unique[np.argmax(counts)]
            mode_b = (mode_key >> 16) & 0xFF
            mode_g = (mode_key >> 8) & 0xFF
            mode_r = mode_key & 0xFF

            # 최빈색 주변 픽셀만으로 정밀 평균 (노이즈 제거)
            mask = keys == mode_key
            if mask.sum() > 0:
                precise = flat[mask].mean(axis=0)
                rgb = (int(precise[2]), int(precise[1]), int(precise[0]))  # BGR→RGB
            else:
                avg = region.mean(axis=(0, 1))
                rgb = (int(avg[2]), int(avg[1]), int(avg[0]))

            # 팔레트 매칭 (벡터 연산)
            if palette_arr is not None:
                dists = np.sqrt(np.sum((palette_arr - np.array(rgb, dtype=np.float32)) ** 2, axis=1))
                best_idx = int(np.argmin(dists))
                row.append(f"{palette_ids[best_idx]:02d}")
                color_counts[palette_ids[best_idx]] += 1
            else:
                row.append("..")

        field_map.append(row)

    # FieldMap 문자열
    field_map_str = "\n".join(" ".join(row) for row in field_map)

    # 색상 분포
    total = sum(color_counts.values())
    dist_parts = []
    palette_map = {p["id"]: p["name"] for p in palette} if palette else {}
    for cid, cnt in sorted(color_counts.items(), key=lambda x: -x[1]):
        name = palette_map.get(cid, f"C{cid}")
        pct = round(cnt / total * 100) if total > 0 else 0
        dist_parts.append(f"{name}:{pct}%({cnt})")

    num_colors = len([c for c in color_counts.values() if c > 0])

    return {
        "level_number": level_num or 0,
        "level_id": f"L{level_num or 0:04d}",
        "num_colors": num_colors,
        "field_rows": grid_rows,
        "field_columns": grid_cols,
        "total_cells": total,
        "color_distribution": " | ".join(dist_parts),
        "designer_note": f"[FieldMap]\n{field_map_str}",
        "pixel_art_source": Path(board_img_path).name,
    }


# ══════════════════════════════════════════════════════════════
#  12. QA Validation (#13-16)
# ══════════════════════════════════════════════════════════════

def qa_validate(stages, frame_files, classifications, levels, display,
                board_dir=None, profile=None, interactive=False):
    """종합 QA 검수."""

    # (#13) 연번 누락 감지 (OCR로 레벨 번호 추출된 경우)
    ocr_numbers = [l.get("ocr_level_number") for l in levels if l.get("ocr_level_number")]
    if len(ocr_numbers) >= 2:
        sorted_nums = sorted(ocr_numbers)
        for i in range(1, len(sorted_nums)):
            gap = sorted_nums[i] - sorted_nums[i - 1]
            if gap > 1:
                missing = list(range(sorted_nums[i - 1] + 1, sorted_nums[i]))
                display.qa(0, f"연번 누락: {missing} (Lv{sorted_nums[i-1]}→Lv{sorted_nums[i]})")

    for i, s in enumerate(stages):
        lvl = i + 1
        idx = s["initial_board_idx"]

        # 프레임이 gameplay인지
        if idx < len(classifications) and classifications[idx]["label"] != "gameplay":
            display.qa(lvl, f"초기 프레임이 gameplay 아님 ({classifications[idx]['label']})")

        # 낮은 신뢰도
        conf = s.get("confidence", 0)
        if conf < 0.5:
            display.qa(lvl, f"낮은 신뢰도: {conf:.2f}")

        # 이전과 너무 가까움
        if i > 0:
            prev_idx = stages[i - 1]["initial_board_idx"]
            if idx - prev_idx < 3:
                display.qa(lvl, f"이전과 {idx - prev_idx}프레임 차이")

        # 해시 유사도
        if i > 0:
            h1 = compute_image_hash(frame_files[stages[i - 1]["initial_board_idx"]])
            h2 = compute_image_hash(frame_files[idx])
            dist = hamming_distance(h1, h2)
            if dist < 15:
                display.qa(lvl, f"이전과 매우 유사 (hamming={dist})")

        # (#14) 보드 유효성 — 크롭된 보드에 색상 블록이 존재하는지
        if board_dir:
            board_path = board_dir / levels[i]["image"]
            if board_path.exists() and CV2_AVAILABLE:
                board = cv2.imread(str(board_path))
                if board is not None:
                    hsv = cv2.cvtColor(board, cv2.COLOR_BGR2HSV)
                    # 채도가 높은 픽셀 비율 (색상 블록)
                    sat_mask = hsv[:, :, 1] > 50
                    sat_ratio = sat_mask.sum() / sat_mask.size
                    if sat_ratio < 0.1:
                        display.qa(lvl, f"보드에 색상 블록 부족 (채도비율={sat_ratio:.2f})")

                    # (#15) 플레이 중 오탐 — 빈 셀 비율이 높으면 이미 플레이 중
                    # 매우 어두운(빈) 영역 비율
                    dark_mask = hsv[:, :, 2] < 40
                    dark_ratio = dark_mask.sum() / dark_mask.size
                    if dark_ratio > 0.4:
                        display.qa(lvl, f"빈 셀 비율 높음 ({dark_ratio:.1%}) — 플레이 중 보드일 수 있음")

    # (#16) 인터랙티브 QA
    if interactive and display.qa_issues:
        print(f"\n  QA 이슈 {len(display.qa_issues)}건 발견. 확인하시겠습니까?")
        for qi, (lv, iss) in enumerate(display.qa_issues):
            resp = input(f"  [Lv{lv:03d}] {iss} — 유지? (Y/n/q): ").strip().lower()
            if resp == "q":
                break
            elif resp == "n":
                display.qa_issues[qi] = (lv, f"[제외됨] {iss}")

    return display.qa_issues


# ══════════════════════════════════════════════════════════════
#  13. HTML Report (#11)
# ══════════════════════════════════════════════════════════════

def _img_to_base64(img_path, max_h=200):
    """이미지를 base64 data URI로 변환 (이식성 확보)."""
    import base64
    p = Path(img_path)
    if not p.exists():
        return ""
    # 썸네일 리사이즈 (HTML 용량 절약)
    try:
        img = Image.open(p)
        ratio = max_h / max(img.height, 1)
        if ratio < 1:
            img = img.resize((int(img.width * ratio), max_h), Image.LANCZOS)
        from io import BytesIO
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        return ""


def generate_html_report(output_dir, levels, qa_issues, stats):
    """(#11) 미리보기 HTML 리포트 생성 — base64 인라인 이미지."""
    html_path = output_dir / "report.html"
    board_dir = output_dir / "boards"

    rows = []
    for l in levels:
        # base64 인라인 (폴더 이동해도 깨지지 않음)
        img_path = board_dir / l["image"] if board_dir.exists() else output_dir / l["image"]
        b64_src = _img_to_base64(img_path, max_h=150)
        img_tag = f'<img src="{b64_src}" style="max-height:120px;cursor:pointer" onclick="this.style.maxHeight=this.style.maxHeight===\'120px\'?\'400px\':\'120px\'">' if b64_src else "(no image)"

        qa_for_level = [iss for lv, iss in qa_issues if lv == l["level"]]
        qa_html = "<br>".join(f"&#9888; {q}" for q in qa_for_level) if qa_for_level else "&#10003;"
        ocr = l.get("ocr_level_number", "—")
        grid = f"{l.get('grid_rows', '?')}x{l.get('grid_cols', '?')}"

        rows.append(f"""
        <tr>
          <td>{l['level']}</td>
          <td>Lv{ocr}</td>
          <td>{img_tag}</td>
          <td>{l['source_frame']}</td>
          <td>{l.get('confidence', 0):.2f}</td>
          <td>{grid}</td>
          <td>{l.get('detection_source', '')}</td>
          <td style="color:{'red' if qa_for_level else 'green'}">{qa_html}</td>
        </tr>""")

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Level Design Extractor Report</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #1a1a2e; color: #e0e0e0; padding: 20px; }}
  h1 {{ color: #00d4ff; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #333; padding: 8px; text-align: center; }}
  th {{ background: #16213e; }}
  tr:hover {{ background: #1a1a3e; }}
  img {{ border-radius: 4px; }}
  .stat {{ display: inline-block; margin: 0 20px 10px 0; padding: 8px 16px;
           background: #16213e; border-radius: 6px; }}
</style></head><body>
<h1>Level Design Extractor v4 Report</h1>
<div>
  <span class="stat">총 레벨: {len(levels)}</span>
  <span class="stat">QA 이슈: {len(qa_issues)}</span>
  {"".join(f'<span class="stat">{k}: {v}</span>' for k, v in stats.items())}
</div>
<table>
  <tr><th>#</th><th>OCR</th><th>보드</th><th>소스 프레임</th>
      <th>신뢰도</th><th>그리드</th><th>감지방식</th><th>QA</th></tr>
  {"".join(rows)}
</table>
</body></html>"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    return html_path


# ══════════════════════════════════════════════════════════════
#  14. Diff Report (#12)
# ══════════════════════════════════════════════════════════════

def generate_diff_report(output_dir, prev_dir, display):
    """(#12) 이전 결과와 비교 — 새로 추가/누락된 스테이지 표시."""
    curr_index = output_dir / "index.json"
    prev_index = Path(prev_dir) / "index.json"

    if not prev_index.exists():
        display.log(f"diff: 이전 결과 없음 ({prev_dir})")
        return

    with open(curr_index, "r", encoding="utf-8") as f:
        curr = json.load(f)
    with open(prev_index, "r", encoding="utf-8") as f:
        prev = json.load(f)

    curr_hashes = set()
    for l in curr.get("levels", []):
        img_path = output_dir / l["image"]
        if img_path.exists():
            curr_hashes.add(compute_image_hash(img_path))

    prev_hashes = set()
    for l in prev.get("levels", []):
        img_path = Path(prev_dir) / l["image"]
        if img_path.exists():
            prev_hashes.add(compute_image_hash(img_path))

    new_levels = len(curr_hashes - prev_hashes)
    removed = len(prev_hashes - curr_hashes)
    same = len(curr_hashes & prev_hashes)

    display.log(f"diff: 신규={new_levels} 유지={same} 이전에만={removed}")
    display.set_stat("diff", f"+{new_levels} ={same} -{removed}")

    diff_data = {
        "new": new_levels,
        "same": same,
        "removed": removed,
        "prev_total": len(prev.get("levels", [])),
        "curr_total": len(curr.get("levels", [])),
    }
    with open(output_dir / "diff_report.json", "w", encoding="utf-8") as f:
        json.dump(diff_data, f, indent=2)


# ══════════════════════════════════════════════════════════════
#  15. Resume Cache (#18)
# ══════════════════════════════════════════════════════════════

def load_classification_cache(cache_path, frame_files):
    """(#18) 이전 분류 결과 캐시 로드."""
    if not cache_path.exists():
        return None

    with open(cache_path, "r", encoding="utf-8") as f:
        cached = json.load(f)

    # 프레임 목록이 동일한지 확인
    cached_frames = {c["frame"] for c in cached}
    current_frames = {f.name for f in frame_files}

    if cached_frames == current_frames:
        return cached  # 완전 일치 → 재사용

    # 부분 일치 → 새 프레임만 분류 필요
    return None  # 단순화: 불일치시 전체 재분류


def save_classification_cache(cache_path, classifications):
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(classifications, f, ensure_ascii=False)


# ══════════════════════════════════════════════════════════════
#  Presets
# ══════════════════════════════════════════════════════════════

PRESETS = {
    "default": {
        "threshold": 0.5, "min_run": 5, "min_gap": 5,
        "settle_frames": 3, "settle_threshold": 0.02, "hash_threshold": 20,
    },
    "recall": {
        "threshold": 0.3, "min_run": 3, "min_gap": 3,
        "settle_frames": 2, "settle_threshold": 0.03, "hash_threshold": 25,
    },
    "precision": {
        "threshold": 0.7, "min_run": 7, "min_gap": 7,
        "settle_frames": 4, "settle_threshold": 0.015, "hash_threshold": 15,
    },
}


# ══════════════════════════════════════════════════════════════
#  Main Pipeline
# ══════════════════════════════════════════════════════════════

def run_pipeline(args):
    display = TmuxDisplay()

    print("\n" + "=" * 60)
    print("  Level Design Extractor v4 — Tmux Mode (21 features)")
    print("=" * 60)

    if args.preset and args.preset in PRESETS:
        p = PRESETS[args.preset]
        display.log(f"프리셋: {args.preset}")
        for k, v in p.items():
            attr = k.replace("-", "_")
            if getattr(args, attr, None) == PRESETS["default"].get(k):
                setattr(args, attr, v)

    frames_dir = Path(args.frames_dir)
    model_path = Path(args.model)
    output_dir = Path(args.output_dir)
    recording_path = Path(args.recording) if args.recording else None
    has_log = recording_path and recording_path.exists()
    profile = load_game_profile(args.game)

    if profile:
        display.log(f"게임 프로필: {profile.get('name', args.game)}")

    # Pipeline stages
    stg = [
        "1. 프레임 로드",
        "2. YOLO 분류",
        "3. 스무딩 & 투표",
        "4. 스테이지 감지" + (" (이벤트+YOLO)" if has_log else " (YOLO)"),
        "5. 안정화 & 중복제거",
        "6. 추출 & OCR",
    ]
    if args.crop_board:
        stg.append("7. 보드 크롭 & 그리드 감지")
    if args.crop_board and profile:
        stg.append("8. FieldMap JSON 생성")
    stg.append("9. QA 검수")
    if args.html_report:
        stg.append("10. HTML 리포트")
    if args.diff_dir:
        stg.append("11. Diff 리포트")

    for s in stg:
        display.set_stage(s, "wait")

    # ── 1. Load ──
    display.set_stage(stg[0], "run")
    display.render()

    if not frames_dir.exists():
        display.set_stage(stg[0], "fail", "폴더 없음")
        display.render()
        sys.exit(1)

    frame_files = sorted(frames_dir.glob("frame_*.png"))
    if not frame_files:
        frame_files = sorted(frames_dir.glob("*.png"))
    if not frame_files:
        frame_files = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.jpeg"))
    if not frame_files:
        display.set_stage(stg[0], "fail", "이미지 없음")
        display.render()
        sys.exit(1)

    frame_index = build_frame_index(frame_files)

    events, rec_meta = [], {}
    if has_log:
        with open(recording_path, "r", encoding="utf-8") as f:
            rec = json.load(f)
        events = rec.get("events", [])
        rec_meta = {k: rec.get(k, "") for k in ["game", "device", "screen_width", "screen_height"]}
        display.log(f"이벤트 로그: {len(events)}개")

    display.set_stage(stg[0], "done", f"{len(frame_files)}장" +
                      (f" + {len(events)} events" if events else ""))
    display.set_stat("프레임", len(frame_files))

    # ── 2. Classify (with resume cache #18) ──
    display.set_stage(stg[1], "run")
    display.render()

    cache_path = output_dir / ".classification_cache.json"
    classifications = None

    if args.resume:
        output_dir.mkdir(parents=True, exist_ok=True)
        classifications = load_classification_cache(cache_path, frame_files)
        if classifications:
            display.log("캐시에서 분류 결과 로드")

    if classifications is None:
        if not model_path.exists():
            display.set_stage(stg[1], "fail", "모델 없음")
            display.render()
            sys.exit(1)
        classifications = classify_frames_yolo(
            model_path, frame_files, args.threshold, display, parallel=args.parallel)
        output_dir.mkdir(parents=True, exist_ok=True)
        save_classification_cache(cache_path, classifications)

    lc = Counter(c["label"] for c in classifications)
    display.set_stage(stg[1], "done", " | ".join(f"{k}:{v}" for k, v in sorted(lc.items())))
    display.set_stat("분류", dict(lc))

    # ── 3. Smooth + vote (#1) ──
    display.set_stage(stg[2], "run")
    classifications = smooth_classifications(classifications, min_run=args.min_run, display=display)
    lc2 = Counter(c["label"] for c in classifications)
    display.set_stage(stg[2], "done", f"gameplay={lc2.get('gameplay', 0)}")

    # ── 4. Stage detect ──
    display.set_stage(stg[3], "run")
    display.render()

    if has_log and events:
        stages = detect_stages_with_log(events, classifications, frame_index,
                                        frame_files, rec_meta, display,
                                        vote_window=getattr(args, 'vote_window', 3))
        yolo_stages = detect_stages_yolo_only(classifications, min_gap=args.min_gap)
        event_indices = {s["initial_board_idx"] for s in stages}
        for ys in yolo_stages:
            if all(abs(ys["initial_board_idx"] - ei) > 10 for ei in event_indices):
                stages.append(ys)
                event_indices.add(ys["initial_board_idx"])
                display.log(f"YOLO 보충: {ys['initial_board_frame']}")
        stages.sort(key=lambda s: s["initial_board_idx"])
    else:
        stages = detect_stages_yolo_only(classifications, min_gap=args.min_gap)

    display.set_stage(stg[3], "done", f"{len(stages)}개 후보")

    # ── 5. Settle + dedup ──
    display.set_stage(stg[4], "run")
    display.render()

    if args.settle_frames > 0:
        for s in stages:
            idx = s["initial_board_idx"]
            settled = find_settled_frame(frame_files, classifications, idx,
                                        args.settle_frames, args.settle_threshold,
                                        args.max_settle_search)
            if settled != idx:
                s["settled_from"] = idx
                s["initial_board_idx"] = settled
                s["initial_board_frame"] = frame_files[settled].name

    skipped = []
    if args.skip_duplicates and len(stages) > 1:
        stages, skipped = deduplicate_stages(stages, frame_files, args.hash_threshold, display)

    display.set_stage(stg[4], "done", f"{len(stages)}개 확정")
    display.set_stat("스테이지", f"{len(stages)} (중복제거 {len(skipped)})")

    # ── 6. Extract + OCR (#2) ──
    display.set_stage(stg[5], "run")
    display.render()

    output_dir.mkdir(parents=True, exist_ok=True)
    board_dir = output_dir / "boards" if args.crop_board else None
    if board_dir:
        board_dir.mkdir(parents=True, exist_ok=True)
    json_dir = output_dir / "json" if args.crop_board and profile else None
    if json_dir:
        json_dir.mkdir(parents=True, exist_ok=True)

    levels = []
    for num, s in enumerate(stages, 1):
        idx = s["initial_board_idx"]
        src = frame_files[idx]
        dst_name = f"level_{num:03d}.png"
        shutil.copy2(src, output_dir / dst_name)

        ocr_num = ocr_level_number(src, profile) if args.ocr else None

        entry = {
            "level": num,
            "image": dst_name,
            "source_frame": s["initial_board_frame"],
            "source_frame_index": idx,
            "confidence": s.get("confidence", 0),
            "transition_from": s.get("transition_from", ""),
            "detection_source": s.get("source", ""),
            "ocr_level_number": ocr_num,
        }
        if "settled_from" in s:
            entry["settled_from_index"] = s["settled_from"]
        levels.append(entry)
        display.progress(num, len(stages), "추출")

    print()
    display.set_stage(stg[5], "done", f"{len(levels)}개")

    # ── 7. Board crop + grid detect (#7, #10) ──
    stg_idx = 6
    if args.crop_board:
        display.set_stage(stg[stg_idx], "run")
        display.render()
        crop_ok, crop_fail = 0, 0

        for i, entry in enumerate(levels, 1):
            ok, meta = crop_board(output_dir / entry["image"], board_dir / entry["image"], profile)
            if ok:
                crop_ok += 1
                entry["board_image"] = f"boards/{entry['image']}"
                entry["grid_rows"] = meta.get("grid_rows", 0)
                entry["grid_cols"] = meta.get("grid_cols", 0)
                entry["crop_method"] = meta.get("method", "")
            else:
                crop_fail += 1
            display.progress(i, len(levels), "크롭")

        print()
        display.set_stage(stg[stg_idx], "done", f"성공={crop_ok} 실패={crop_fail}")
        stg_idx += 1

    # ── 8. FieldMap JSON (#9) ──
    if args.crop_board and profile and json_dir:
        display.set_stage(stg[stg_idx], "run")
        display.render()
        json_ok = 0

        for i, entry in enumerate(levels, 1):
            gr = entry.get("grid_rows", 0)
            gc = entry.get("grid_cols", 0)
            lvl_num = entry.get("ocr_level_number", entry["level"])
            if gr >= 2 and gc >= 2 and board_dir:
                fm = generate_fieldmap_json(board_dir / entry["image"], gr, gc, profile, lvl_num)
                if fm:
                    json_path = json_dir / f"level_{entry['level']:03d}.json"
                    with open(json_path, "w", encoding="utf-8") as f:
                        json.dump(fm, f, indent=2, ensure_ascii=False)
                    entry["fieldmap_json"] = f"json/level_{entry['level']:03d}.json"
                    json_ok += 1
            display.progress(i, len(levels), "JSON")

        print()
        display.set_stage(stg[stg_idx], "done", f"{json_ok}개 생성")
        stg_idx += 1

    # ── 9. QA (#13-16) ──
    qa_stg = stg[stg_idx]
    display.set_stage(qa_stg, "run")
    qa_validate(stages, frame_files, classifications, levels, display,
                board_dir=board_dir, profile=profile,
                interactive=args.interactive_qa)
    qa_count = len(display.qa_issues)
    display.set_stage(qa_stg, "done", f"{qa_count}건 이슈" if qa_count else "이슈 없음")
    stg_idx += 1

    # ── Save index.json ──
    index = {
        "version": "4.0",
        "game": args.game,
        "total_frames": len(frame_files),
        "total_events": len(events),
        "total_levels": len(levels),
        "model": model_path.name,
        "recording": str(recording_path) if recording_path else None,
        "settings": {
            "preset": args.preset or "custom",
            "threshold": args.threshold, "min_run": args.min_run,
            "min_gap": args.min_gap, "settle_frames": args.settle_frames,
            "hash_threshold": args.hash_threshold,
            "crop_board": args.crop_board, "ocr": args.ocr,
        },
        "qa_issues": [{"level": lv, "issue": iss} for lv, iss in display.qa_issues],
        "levels": levels,
    }

    with open(output_dir / "index.json", "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)
    with open(output_dir / "frame_classifications.json", "w", encoding="utf-8") as f:
        json.dump(classifications, f, indent=2, ensure_ascii=False)

    # ── 10. HTML Report (#11) ──
    if args.html_report:
        display.set_stage(stg[stg_idx], "run")
        html_path = generate_html_report(output_dir, levels, display.qa_issues, display.stats)
        display.set_stage(stg[stg_idx], "done", str(html_path.name))
        stg_idx += 1

    # ── 11. Diff (#12) ──
    if args.diff_dir:
        display.set_stage(stg[stg_idx], "run")
        generate_diff_report(output_dir, args.diff_dir, display)
        display.set_stage(stg[stg_idx], "done")
        stg_idx += 1

    # ── Final ──
    display.log(f"완료: {len(levels)}개 레벨 → {output_dir}")
    display.render()

    print(f"\n  출력: {output_dir}")
    print(f"  레벨: {len(levels)}개")
    if board_dir:
        print(f"  보드: {board_dir}")
    if json_dir:
        print(f"  JSON: {json_dir}")
    if args.html_report:
        print(f"  리포트: {output_dir / 'report.html'}")
    if qa_count:
        print(f"  QA: {qa_count}건 이슈")
    print()


# ══════════════════════════════════════════════════════════════
#  Watch Mode (#17)
# ══════════════════════════════════════════════════════════════

def watch_mode(args):
    """(#17) 프레임 폴더 감시 → 새 프레임 추가시 자동 처리."""
    frames_dir = Path(args.frames_dir)
    print(f"\n  Watch 모드: {frames_dir} 감시 중... (Ctrl+C 종료)")
    print(f"  새 프레임이 추가되면 자동으로 추출을 실행합니다.\n")

    seen = set()
    if frames_dir.exists():
        seen = set(f.name for f in frames_dir.glob("*.png"))

    try:
        while True:
            time.sleep(2)
            if not frames_dir.exists():
                continue

            current = set(f.name for f in frames_dir.glob("*.png"))
            new_files = current - seen

            if new_files:
                print(f"\n  새 프레임 {len(new_files)}개 감지! 추출 실행...")
                seen = current
                run_pipeline(args)
    except KeyboardInterrupt:
        print("\n  Watch 모드 종료.")


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Level Design Extractor v4 (Tmux, 21 features)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
프리셋:
  --preset default    균형
  --preset recall     누락 최소화
  --preset precision  정확도 우선

예시:
  python level_design_extractor_tmux.py \\
    --frames-dir ./frames --recording recording.json \\
    --model best.pt --output-dir ./output \\
    --game balloonflow --crop-board --html-report --preset recall
        """)

    parser.add_argument("--frames-dir", required=True)
    parser.add_argument("--recording", help="recording.json")
    parser.add_argument("--model", required=True, help="YOLO .pt")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--game", default="balloonflow")
    parser.add_argument("--preset", choices=["default", "recall", "precision"], default="default")

    # Features
    parser.add_argument("--crop-board", action="store_true", help="보드 크롭 (#6-8)")
    parser.add_argument("--ocr", action="store_true", help="레벨 번호 OCR (#2)")
    parser.add_argument("--html-report", action="store_true", help="HTML 리포트 (#11)")
    parser.add_argument("--diff-dir", help="이전 결과 폴더 (diff #12)")
    parser.add_argument("--interactive-qa", action="store_true", help="인터랙티브 QA (#16)")
    parser.add_argument("--watch", action="store_true", help="Watch 모드 (#17)")
    parser.add_argument("--resume", action="store_true", help="분류 캐시 재사용 (#18)")
    parser.add_argument("--parallel", action="store_true", help="병렬 분류 (#19)")

    # Tuning
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--min-run", type=int, default=5)
    parser.add_argument("--min-gap", type=int, default=5)
    parser.add_argument("--settle-frames", type=int, default=3)
    parser.add_argument("--settle-threshold", type=float, default=0.02)
    parser.add_argument("--max-settle-search", type=int, default=15)
    parser.add_argument("--skip-duplicates", action="store_true", default=True)
    parser.add_argument("--no-skip-duplicates", dest="skip_duplicates", action="store_false")
    parser.add_argument("--hash-threshold", type=int, default=20)
    parser.add_argument("--vote-window", type=int, default=3, help="멀티프레임 투표 윈도우 (#1)")

    args = parser.parse_args()

    if args.watch:
        watch_mode(args)
    else:
        run_pipeline(args)


if __name__ == "__main__":
    main()
