"""
Level Design Extractor v2 — GUI
=================================
녹화 프레임에서 각 스테이지의 시작 보드(초기 배치)만 추출하는 GUI 도구.

v2 개선:
  - 분류 스무딩: 짧은 오분류 깜빡임 무시
  - 보드 안정화: 전환 후 보드가 안정된 프레임 선택
  - 전역 중복 제거: 모든 기존 레벨과 해시 비교
"""

import json
import os
import shutil
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import numpy as np
from PIL import Image, ImageTk

# ── YOLO 로드 ──
YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    pass


# ══════════════════════════════════════════════════════════════
#  핵심 로직 (level_design_extractor.py와 동일)
# ══════════════════════════════════════════════════════════════

def classify_frames_yolo(model_path, frames, conf_threshold, progress_cb=None):
    model = YOLO(str(model_path))
    results = []
    batch_size = 16
    total = len(frames)

    for i in range(0, total, batch_size):
        batch = frames[i:i + batch_size]
        batch_paths = [str(f) for f in batch]
        preds = model.predict(batch_paths, verbose=False, conf=conf_threshold)

        for j, pred in enumerate(preds):
            if pred.probs is not None:
                top_cls = int(pred.probs.top1)
                top_conf = float(pred.probs.top1conf)
                label = model.names[top_cls]
            else:
                label = "unknown"
                top_conf = 0.0

            results.append({
                "frame": batch[j].name,
                "path": str(batch[j]),
                "label": label,
                "confidence": round(top_conf, 4),
            })

        done = min(i + batch_size, total)
        if progress_cb:
            progress_cb(done, total, f"분류 중: {done}/{total}")

    return results


def smooth_classifications(classifications, min_run=5, log_cb=None):
    """짧은 오분류 구간을 주변 라벨로 스무딩."""
    if not classifications:
        return classifications

    smoothed = [dict(c) for c in classifications]
    labels = [c["label"] for c in smoothed]
    n = len(labels)

    # Run-length encoding
    runs = []
    i = 0
    while i < n:
        label = labels[i]
        j = i
        while j < n and labels[j] == label:
            j += 1
        runs.append((i, j - i, label))
        i = j

    # 짧은 구간을 양쪽 라벨로 대체
    changed = 0
    for ri in range(1, len(runs) - 1):
        start, length, label = runs[ri]
        prev_label = runs[ri - 1][2]
        next_label = runs[ri + 1][2]

        if prev_label == next_label and length < min_run:
            for k in range(start, start + length):
                smoothed[k]["label"] = prev_label
                smoothed[k]["smoothed_from"] = label
            changed += length

    if changed > 0 and log_cb:
        log_cb(f"  스무딩: {changed}개 프레임 보정")

    return smoothed


def detect_stage_starts_v2(classifications, min_gap=5):
    """진짜 스테이지 시작만 감지. 비-gameplay 구간이 min_gap 이상일 때만."""
    starts = []
    n = len(classifications)

    i = 0
    while i < n:
        label = classifications[i]["label"]

        if label != "gameplay":
            gap_start = i
            while i < n and classifications[i]["label"] != "gameplay":
                i += 1
            gap_length = i - gap_start

            if i < n and gap_length >= min_gap:
                starts.append(i)
        else:
            i += 1

    # 첫 프레임이 gameplay인 경우
    if classifications and classifications[0]["label"] == "gameplay":
        if not starts or starts[0] != 0:
            starts.insert(0, 0)

    return starts


def compute_image_hash(img_path, hash_size=16):
    img = Image.open(img_path).convert("L").resize((hash_size, hash_size), Image.LANCZOS)
    arr = np.array(img)
    mean = arr.mean()
    bits = (arr > mean).flatten()
    return "".join("1" if b else "0" for b in bits)


def hamming_distance(h1, h2):
    return sum(c1 != c2 for c1, c2 in zip(h1, h2))


def compute_frame_delta(path_a, path_b, size=(270, 480)):
    """두 프레임 간 변화율 (0.0 ~ 1.0)."""
    img_a = np.array(Image.open(path_a).convert("L").resize(size, Image.LANCZOS), dtype=np.float32)
    img_b = np.array(Image.open(path_b).convert("L").resize(size, Image.LANCZOS), dtype=np.float32)
    diff = np.abs(img_a - img_b)
    return float(np.mean(diff) / 255.0)


def find_settled_frame(frame_files, classifications, start_idx,
                       settle_frames=3, settle_threshold=0.02, max_search=15):
    """전환 후 보드가 안정된 프레임 찾기."""
    n = len(frame_files)
    search_end = min(start_idx + max_search, n - 1)

    for i in range(start_idx, search_end - settle_frames + 1):
        all_gameplay = all(
            classifications[i + k]["label"] == "gameplay"
            for k in range(settle_frames)
            if i + k < len(classifications)
        )
        if not all_gameplay:
            continue

        stable = True
        for k in range(settle_frames - 1):
            delta = compute_frame_delta(frame_files[i + k], frame_files[i + k + 1])
            if delta > settle_threshold:
                stable = False
                break

        if stable:
            return i

    return start_idx


def filter_duplicates_global(start_indices, frames, hash_threshold=20):
    """모든 기존 레벨과 비교하여 중복 제거."""
    if not start_indices:
        return [], []

    filtered = []
    skipped = []
    known_hashes = []

    for idx in start_indices:
        curr_hash = compute_image_hash(frames[idx])

        is_duplicate = False
        for prev_hash in known_hashes:
            dist = hamming_distance(prev_hash, curr_hash)
            if dist <= hash_threshold:
                skipped.append((idx, frames[idx].name, dist))
                is_duplicate = True
                break

        if not is_duplicate:
            filtered.append(idx)
            known_hashes.append(curr_hash)

    return filtered, skipped


# ══════════════════════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════════════════════

class LevelDesignExtractorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Level Design Extractor v2")
        self.root.geometry("800x750")
        self.root.resizable(True, True)
        self.root.minsize(720, 650)

        self._running = False
        self._extracted_levels = []

        self._build_ui()

    def _build_ui(self):
        # ── 상단: 입력 설정 ──
        input_frame = ttk.LabelFrame(self.root, text="입력 설정", padding=10)
        input_frame.pack(fill="x", padx=10, pady=(10, 5))

        ttk.Label(input_frame, text="프레임 폴더:").grid(row=0, column=0, sticky="w", pady=2)
        self.frames_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.frames_var, width=55).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(input_frame, text="찾아보기", command=self._browse_frames).grid(row=0, column=2, pady=2)

        ttk.Label(input_frame, text="YOLO 모델:").grid(row=1, column=0, sticky="w", pady=2)
        self.model_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.model_var, width=55).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(input_frame, text="찾아보기", command=self._browse_model).grid(row=1, column=2, pady=2)

        ttk.Label(input_frame, text="출력 폴더:").grid(row=2, column=0, sticky="w", pady=2)
        self.output_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.output_var, width=55).grid(row=2, column=1, padx=5, pady=2)
        ttk.Button(input_frame, text="찾아보기", command=self._browse_output).grid(row=2, column=2, pady=2)

        # v4: recording.json
        ttk.Label(input_frame, text="recording.json:").grid(row=3, column=0, sticky="w", pady=2)
        self.recording_var = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.recording_var, width=55).grid(row=3, column=1, padx=5, pady=2)
        ttk.Button(input_frame, text="찾아보기", command=self._browse_recording).grid(row=3, column=2, pady=2)

        input_frame.columnconfigure(1, weight=1)

        # ── 옵션 (2줄) ──
        opt_frame = ttk.LabelFrame(self.root, text="옵션", padding=10)
        opt_frame.pack(fill="x", padx=10, pady=5)

        # Row 0: 기본 설정
        ttk.Label(opt_frame, text="Confidence:").grid(row=0, column=0, sticky="w")
        self.threshold_var = tk.DoubleVar(value=0.5)
        ttk.Spinbox(opt_frame, from_=0.1, to=1.0, increment=0.05,
                     textvariable=self.threshold_var, width=6).grid(row=0, column=1, sticky="w", padx=5)

        self.dedup_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="전역 중복 제거", variable=self.dedup_var).grid(
            row=0, column=2, padx=10)

        ttk.Label(opt_frame, text="중복 거리:").grid(row=0, column=3, sticky="w")
        self.hash_thresh_var = tk.IntVar(value=20)
        ttk.Spinbox(opt_frame, from_=5, to=50, increment=5,
                     textvariable=self.hash_thresh_var, width=5).grid(row=0, column=4, sticky="w", padx=5)

        # Row 1: v2 신규 설정
        ttk.Label(opt_frame, text="스무딩(min_run):").grid(row=1, column=0, sticky="w", pady=(5, 0))
        self.min_run_var = tk.IntVar(value=5)
        ttk.Spinbox(opt_frame, from_=2, to=20, increment=1,
                     textvariable=self.min_run_var, width=6).grid(row=1, column=1, sticky="w", padx=5, pady=(5, 0))

        ttk.Label(opt_frame, text="최소 갭(min_gap):").grid(row=1, column=2, sticky="w", pady=(5, 0))
        self.min_gap_var = tk.IntVar(value=5)
        ttk.Spinbox(opt_frame, from_=2, to=30, increment=1,
                     textvariable=self.min_gap_var, width=5).grid(row=1, column=3, sticky="w", padx=5, pady=(5, 0))

        ttk.Label(opt_frame, text="안정화 프레임:").grid(row=1, column=4, sticky="w", pady=(5, 0))
        self.settle_var = tk.IntVar(value=3)
        ttk.Spinbox(opt_frame, from_=0, to=10, increment=1,
                     textvariable=self.settle_var, width=5).grid(row=1, column=5, sticky="w", padx=5, pady=(5, 0))

        # Row 2: v4 옵션
        self.crop_board_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="보드 크롭", variable=self.crop_board_var).grid(
            row=2, column=0, padx=5, pady=(5, 0), sticky="w")

        self.ocr_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="레벨 번호 OCR", variable=self.ocr_var).grid(
            row=2, column=1, columnspan=2, padx=5, pady=(5, 0), sticky="w")

        self.html_report_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt_frame, text="HTML 리포트", variable=self.html_report_var).grid(
            row=2, column=3, padx=5, pady=(5, 0), sticky="w")

        ttk.Label(opt_frame, text="프리셋:").grid(row=2, column=4, sticky="w", pady=(5, 0))
        self.preset_var = tk.StringVar(value="default")
        ttk.Combobox(opt_frame, textvariable=self.preset_var,
                      values=["default", "recall", "precision"],
                      width=10, state="readonly").grid(row=2, column=5, sticky="w", padx=5, pady=(5, 0))

        # ── 실행 버튼 ──
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.run_btn = ttk.Button(btn_frame, text="추출 시작", command=self._on_run)
        self.run_btn.pack(side="left")

        self.open_btn = ttk.Button(btn_frame, text="출력 폴더 열기", command=self._open_output, state="disabled")
        self.open_btn.pack(side="left", padx=10)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(btn_frame, variable=self.progress_var,
                                             maximum=100, length=300)
        self.progress_bar.pack(side="right", padx=5)

        self.status_var = tk.StringVar(value="대기 중")
        ttk.Label(btn_frame, textvariable=self.status_var).pack(side="right", padx=5)

        # ── 하단: 로그 + 미리보기 ──
        bottom = ttk.PanedWindow(self.root, orient="horizontal")
        bottom.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # 로그
        log_frame = ttk.LabelFrame(bottom, text="로그", padding=5)
        self.log_text = tk.Text(log_frame, width=45, height=18, font=("Consolas", 9),
                                state="disabled", bg="#1e1e1e", fg="#cccccc",
                                insertbackground="#cccccc")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")
        bottom.add(log_frame, weight=3)

        # 미리보기
        preview_frame = ttk.LabelFrame(bottom, text="미리보기", padding=5)
        self.preview_canvas = tk.Canvas(preview_frame, bg="#2d2d2d", width=200, height=350)
        self.preview_canvas.pack(fill="both", expand=True)
        self.preview_label = ttk.Label(preview_frame, text="추출 후 레벨 클릭")
        self.preview_label.pack()

        self.level_listbox = tk.Listbox(preview_frame, height=6, font=("Consolas", 9))
        self.level_listbox.pack(fill="x", pady=(5, 0))
        self.level_listbox.bind("<<ListboxSelect>>", self._on_level_select)
        bottom.add(preview_frame, weight=2)

        self._auto_detect_paths()

    def _auto_detect_paths(self):
        base = Path(__file__).resolve().parent.parent
        if hasattr(sys, '_MEIPASS'):
            base = Path(sys.executable).parent

        # 배포 패키지 구조: exe 옆에 models/ 폴더 있는지 확인
        exe_dir = Path(sys.executable).parent if hasattr(sys, '_MEIPASS') else Path(__file__).resolve().parent
        model_beside = exe_dir / "models" / "best.pt"
        sample_frames = exe_dir / "sample_data" / "frames"
        sample_output = exe_dir / "output"

        if model_beside.exists():
            self.model_var.set(str(model_beside))
            if sample_frames.exists():
                self.frames_var.set(str(sample_frames))
            if sample_output.exists() or exe_dir.exists():
                self.output_var.set(str(sample_output))
            return

        # 기존 data/ 구조 탐색
        recordings = base / "data" / "recordings"
        if not recordings.exists():
            recordings = Path("data/recordings")

        if recordings.exists():
            games = [d for d in recordings.iterdir() if d.is_dir() and (d / "frames").exists()]
            if games:
                game = games[0]
                self.frames_var.set(str(game / "frames"))
                self.output_var.set(str(base / "data" / "games" / game.name / "level_designs"))

                for version in ["screen_classifier_v2", "screen_classifier"]:
                    mp = base / "data" / "games" / game.name / "yolo_dataset" / "models" / version / "weights" / "best.pt"
                    if mp.exists():
                        self.model_var.set(str(mp))
                        break

    def _browse_frames(self):
        d = filedialog.askdirectory(title="프레임 폴더 선택")
        if d:
            self.frames_var.set(d)

    def _browse_model(self):
        f = filedialog.askopenfilename(title="YOLO 모델 선택", filetypes=[("PyTorch", "*.pt")])
        if f:
            self.model_var.set(f)

    def _browse_recording(self):
        f = filedialog.askopenfilename(title="recording.json 선택",
                                       filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if f:
            self.recording_var.set(f)

    def _browse_output(self):
        d = filedialog.askdirectory(title="출력 폴더 선택")
        if d:
            self.output_var.set(d)

    def _open_output(self):
        out = self.output_var.get()
        if out and Path(out).exists():
            os.startfile(out)

    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log_safe(self, msg):
        self.root.after(0, self._log, msg)

    def _progress(self, current, total, msg=""):
        pct = (current / total * 100) if total > 0 else 0
        self.root.after(0, lambda: self.progress_var.set(pct))
        if msg:
            self.root.after(0, lambda: self.status_var.set(msg))

    def _on_run(self):
        if self._running:
            return

        frames_dir = Path(self.frames_var.get().strip())
        model_path = Path(self.model_var.get().strip())
        output_dir = Path(self.output_var.get().strip())

        if not frames_dir.exists():
            messagebox.showerror("오류", f"프레임 폴더가 없습니다:\n{frames_dir}")
            return
        if not model_path.exists():
            messagebox.showerror("오류", f"YOLO 모델이 없습니다:\n{model_path}")
            return
        if not YOLO_AVAILABLE:
            messagebox.showerror("오류", "ultralytics 미설치.\npip install ultralytics")
            return

        self._running = True
        self.run_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.level_listbox.delete(0, "end")
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        t = threading.Thread(target=self._run_extraction, args=(frames_dir, model_path, output_dir), daemon=True)
        t.start()

    def _run_extraction(self, frames_dir, model_path, output_dir):
        try:
            self._do_extract(frames_dir, model_path, output_dir)
        except Exception as e:
            self._log_safe(f"\n[ERROR] {e}")
            import traceback
            self._log_safe(traceback.format_exc())
            self.root.after(0, lambda: messagebox.showerror("오류", str(e)))
        finally:
            self._running = False
            self.root.after(0, lambda: self.run_btn.configure(state="normal"))

    def _do_extract(self, frames_dir, model_path, output_dir):
        """v4 파이프라인 — 이벤트 로그 + 보드 크롭 + HTML 리포트 통합."""
        # v4 tmux 모듈 import
        try:
            import level_design_extractor_tmux as v4
        except ImportError:
            # exe 빌드 시 같은 폴더에 있을 수도 있음
            import importlib.util
            tmux_path = Path(__file__).resolve().parent / "level_design_extractor_tmux.py"
            if not tmux_path.exists():
                # src/ 폴더 체크
                tmux_path = Path(sys.executable).parent / "src" / "level_design_extractor_tmux.py"
            if tmux_path.exists():
                spec = importlib.util.spec_from_file_location("v4", tmux_path)
                v4 = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(v4)
            else:
                raise ImportError("level_design_extractor_tmux.py를 찾을 수 없습니다")

        # 프리셋 적용
        preset = self.preset_var.get()
        presets = v4.PRESETS
        p = presets.get(preset, presets["default"])
        threshold = self.threshold_var.get()
        min_run = self.min_run_var.get()
        min_gap = self.min_gap_var.get()
        settle = self.settle_var.get()
        hash_thresh = self.hash_thresh_var.get()

        # 프리셋 값이 기본과 같으면 프리셋 적용
        if threshold == 0.5:
            threshold = p.get("threshold", threshold)
        if min_run == 5:
            min_run = p.get("min_run", min_run)
        if min_gap == 5:
            min_gap = p.get("min_gap", min_gap)

        do_crop = self.crop_board_var.get()
        do_html = self.html_report_var.get()
        game_id = "balloonflow"
        profile = v4.load_game_profile(game_id)

        # 1. 프레임 로드
        frame_files = sorted(frames_dir.glob("frame_*.png"))
        if not frame_files:
            frame_files = sorted(frames_dir.glob("*.png"))
        if not frame_files:
            frame_files = sorted(frames_dir.glob("*.jpg")) + sorted(frames_dir.glob("*.jpeg"))
        if not frame_files:
            raise FileNotFoundError(f"이미지 파일이 없습니다: {frames_dir}")

        frame_index = v4.build_frame_index(frame_files)
        self._log_safe(f"[1/8] 프레임 로드: {len(frame_files)}장")

        # recording.json 로드
        rec_path_str = self.recording_var.get().strip()
        events, rec_meta = [], {}
        if rec_path_str:
            rec_path = Path(rec_path_str)
            if rec_path.exists():
                with open(rec_path, "r", encoding="utf-8") as f:
                    rec = json.load(f)
                events = rec.get("events", [])
                rec_meta = {k: rec.get(k, "") for k in ["game", "device", "screen_width", "screen_height"]}
                self._log_safe(f"  이벤트 로그: {len(events)}개")

        # 2. YOLO 분류
        self._log_safe(f"[2/8] YOLO 분류 (threshold={threshold})")
        classifications = classify_frames_yolo(model_path, frame_files, threshold,
                                                progress_cb=self._progress)

        label_counts = {}
        for c in classifications:
            label_counts[c["label"]] = label_counts.get(c["label"], 0) + 1
        self._log_safe(f"  분류: {label_counts}")

        # 3. 스무딩
        self._log_safe(f"[3/8] 스무딩 (min_run={min_run})")
        classifications = v4.smooth_classifications(classifications, min_run=min_run)

        # 4. 스테이지 감지 (이벤트 + YOLO)
        self._log_safe(f"[4/8] 스테이지 감지")
        self._progress(0, 1, "스테이지 감지 중...")

        class _LogAdapter:
            def __init__(self, log_fn):
                self._log = log_fn
                self.qa_issues = []
            def log(self, msg):
                self._log(msg)
            def qa(self, lvl, issue):
                self.qa_issues.append((lvl, issue))

        display_adapter = _LogAdapter(self._log_safe)

        if events:
            stages = v4.detect_stages_with_log(events, classifications, frame_index,
                                                frame_files, rec_meta, display_adapter)
            yolo_stages = v4.detect_stages_yolo_only(classifications, min_gap=min_gap)
            event_indices = {s["initial_board_idx"] for s in stages}
            for ys in yolo_stages:
                if all(abs(ys["initial_board_idx"] - ei) > 10 for ei in event_indices):
                    stages.append(ys)
                    event_indices.add(ys["initial_board_idx"])
            stages.sort(key=lambda s: s["initial_board_idx"])
        else:
            stages = v4.detect_stages_yolo_only(classifications, min_gap=min_gap)

        self._log_safe(f"  후보: {len(stages)}개")

        # 5. 안정화 + 중복 제거
        self._log_safe(f"[5/8] 안정화 & 중복 제거")
        if settle > 0:
            for s in stages:
                idx = s["initial_board_idx"]
                settled = v4.find_settled_frame(frame_files, classifications, idx,
                                                settle, 0.02, 15)
                if settled != idx:
                    s["initial_board_idx"] = settled
                    s["initial_board_frame"] = frame_files[settled].name

        if self.dedup_var.get() and len(stages) > 1:
            stages, skipped = v4.deduplicate_stages(stages, frame_files, hash_thresh)
            self._log_safe(f"  중복 제거: {len(skipped)}개 스킵")

        self._log_safe(f"  확정: {len(stages)}개")

        # 6. 추출
        self._log_safe(f"[6/8] 추출 -> {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
        board_dir = output_dir / "boards" if do_crop else None
        if board_dir:
            board_dir.mkdir(parents=True, exist_ok=True)

        levels = []
        for num, s in enumerate(stages, 1):
            idx = s["initial_board_idx"]
            src = frame_files[idx]
            dst_name = f"level_{num:03d}.png"
            shutil.copy2(src, output_dir / dst_name)

            entry = {
                "level": num,
                "image": dst_name,
                "source_frame": s.get("initial_board_frame", ""),
                "source_frame_index": idx,
                "confidence": s.get("confidence", 0),
                "transition_from": s.get("transition_from", ""),
                "detection_source": s.get("source", ""),
            }
            levels.append(entry)
            self._progress(num, len(stages), f"추출: {num}/{len(stages)}")

        # 7. 보드 크롭
        if do_crop and board_dir:
            self._log_safe(f"[7/8] 보드 크롭")
            crop_ok = 0
            for i, entry in enumerate(levels, 1):
                ok, meta = v4.crop_board(output_dir / entry["image"],
                                          board_dir / entry["image"], profile)
                if ok:
                    crop_ok += 1
                    entry["board_image"] = f"boards/{entry['image']}"
                    entry["grid_rows"] = meta.get("grid_rows", 0)
                    entry["grid_cols"] = meta.get("grid_cols", 0)
                self._progress(i, len(levels), f"크롭: {i}/{len(levels)}")
            self._log_safe(f"  크롭 성공: {crop_ok}/{len(levels)}")
        else:
            self._log_safe(f"[7/8] 보드 크롭 — 건너뜀")

        # 8. 저장
        self._log_safe(f"[8/8] 메타데이터 저장")
        index = {
            "version": "4.0",
            "total_frames": len(frame_files),
            "total_events": len(events),
            "total_levels": len(levels),
            "model": model_path.name,
            "settings": {
                "preset": preset,
                "threshold": threshold,
                "min_run": min_run,
                "min_gap": min_gap,
                "settle_frames": settle,
                "crop_board": do_crop,
            },
            "levels": levels,
        }
        with open(output_dir / "index.json", "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        with open(output_dir / "frame_classifications.json", "w", encoding="utf-8") as f:
            json.dump(classifications, f, indent=2, ensure_ascii=False)

        # HTML 리포트
        if do_html:
            try:
                v4.generate_html_report(output_dir, levels, display_adapter.qa_issues,
                                         {"프레임": len(frame_files), "이벤트": len(events)})
                self._log_safe(f"  HTML 리포트: report.html")
            except Exception as e:
                self._log_safe(f"  HTML 리포트 실패: {e}")

        self._extracted_levels = [(output_dir / lv["image"], lv) for lv in levels]

        self._log_safe(f"\n완료: {len(levels)}개 레벨 추출")
        self._log_safe(f"  출력: {output_dir}")
        if board_dir:
            self._log_safe(f"  보드: {board_dir}")
        self._progress(100, 100, f"완료 — {len(levels)}개 레벨")

        def _update_ui():
            self.open_btn.configure(state="normal")
            self.level_listbox.delete(0, "end")
            for lv in levels:
                self.level_listbox.insert("end", f"Level {lv['level']:03d}  ({lv['source_frame']})")
        self.root.after(0, _update_ui)

    def _on_level_select(self, event):
        sel = self.level_listbox.curselection()
        if not sel or not self._extracted_levels:
            return
        idx = sel[0]
        if idx >= len(self._extracted_levels):
            return

        img_path, lv = self._extracted_levels[idx]
        if not img_path.exists():
            return

        img = Image.open(img_path)
        canvas_w = self.preview_canvas.winfo_width()
        canvas_h = self.preview_canvas.winfo_height()
        if canvas_w < 10:
            canvas_w, canvas_h = 200, 350

        ratio = min(canvas_w / img.width, canvas_h / img.height)
        new_w = max(1, int(img.width * ratio))
        new_h = max(1, int(img.height * ratio))
        img_resized = img.resize((new_w, new_h), Image.LANCZOS)

        self._preview_photo = ImageTk.PhotoImage(img_resized)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(canvas_w // 2, canvas_h // 2,
                                          image=self._preview_photo, anchor="center")
        self.preview_label.configure(
            text=f"Level {lv['level']} | {lv['transition_from']}->gameplay | conf={lv['confidence']}")


def main():
    root = tk.Tk()
    app = LevelDesignExtractorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
