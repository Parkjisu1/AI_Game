"""
Level Design Studio — 올인원 레벨 디자인 도구
===============================================
Tab 1: YOLO 학습 — 새 게임 자동 분류 + 모델 학습
Tab 2: 스테이지 추출 — YOLO로 스테이지 시작 추출
Tab 3: Crop + JSON — 보드 크롭 + 렌더링 범위 매칭 + JSON 변환
Tab 4: 스타일 편집 — 모티프 추출 / 색상 변경 / 합성
Tab 5: AI 변형 — Stable Diffusion (첫 실행시 자동 설치)

첫 실행시:
  - game_profiles.json 내장
  - SD 모델 자동 다운로드 (~3GB, 1회만)
  - YOLO 학습된 모델은 games/<game_id>/ 에 저장

사용법:
  LevelDesignStudio.exe
"""
import json
import os
import random
import shutil
import sqlite3
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageTk, ImageDraw

YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    pass

try:
    from sklearn.cluster import KMeans
    SKLEARN = True
except ImportError:
    SKLEARN = False

SCRIPT_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))

# C드라이브 공간 부족 대비: exe 옆에 studio_data 폴더 사용
# exe가 E:\에 있으면 E:\studio_data에 저장
_exe_dir = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
DATA_DIR = _exe_dir / "studio_data"

# 환경변수: 모든 캐시를 exe 옆 폴더로 (C드라이브 사용 안 함)
os.environ["TMPDIR"] = str(DATA_DIR / "temp")
os.environ["TEMP"] = str(DATA_DIR / "temp")
os.environ["TMP"] = str(DATA_DIR / "temp")
os.environ["HF_HOME"] = str(DATA_DIR / "huggingface")
os.environ["HUGGINGFACE_HUB_CACHE"] = str(DATA_DIR / "huggingface" / "hub")
os.environ["TORCH_HOME"] = str(DATA_DIR / "torch")
os.environ["XDG_CACHE_HOME"] = str(DATA_DIR / "cache")


def load_palette(game_id="balloonflow"):
    for p in [SCRIPT_DIR / "game_profiles.json", Path("game_profiles.json")]:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f).get(game_id, {}).get("color_palette_28", [])
    return []


# ══════════════════════════════════════════════════════════════
#  29-Color Palette (from level-transformer skill)
# ══════════════════════════════════════════════════════════════
PALETTE_29 = {
    1:  (252, 106, 175), 2:  (80, 232, 246),  3:  (137, 80, 248),
    4:  (254, 213, 85),  5:  (115, 254, 102), 6:  (253, 161, 76),
    7:  (255, 255, 255), 8:  (65, 65, 65),    9:  (110, 168, 250),
    10: (57, 174, 46),   11: (252, 94, 94),   12: (50, 107, 248),
    13: (58, 165, 139),  14: (231, 167, 250), 15: (183, 199, 251),
    16: (106, 74, 48),   17: (254, 227, 169), 18: (253, 183, 193),
    19: (158, 61, 94),   20: (167, 221, 148), 21: (89, 46, 126),
    22: (220, 120, 129), 23: (217, 217, 231), 24: (111, 114, 127),
    25: (252, 56, 165),  26: (253, 180, 88),  27: (137, 10, 8),
    28: (111, 175, 177), 29: (100, 80, 60),
}
_PAL_KEYS = sorted(PALETTE_29.keys())
_PAL_ARRAY = np.array([PALETTE_29[k] for k in _PAL_KEYS], dtype=np.float64)


def nearest_palette_color(r, g, b):
    """RGB → 가장 가까운 29색 팔레트 인덱스 (1-indexed)."""
    pixel = np.array([r, g, b], dtype=np.float64)
    dists = np.sqrt(np.sum((_PAL_ARRAY - pixel) ** 2, axis=1))
    return _PAL_KEYS[int(np.argmin(dists))]


def image_to_fieldmap_29(img, grid_w=50, grid_h=50):
    """PIL Image → 29색 팔레트 기반 FieldMap grid (정밀 매핑)."""
    img_resized = img.convert("RGB").resize((grid_w, grid_h), Image.LANCZOS)
    pixels = np.array(img_resized)
    grid = []
    for y in range(grid_h):
        row = []
        for x in range(grid_w):
            r, g, b = pixels[y, x]
            row.append(nearest_palette_color(int(r), int(g), int(b)))
        grid.append(row)
    return grid


def img_hash(path, size=16):
    arr = np.array(Image.open(path).convert("L").resize((size, size)))
    return "".join("1" if b else "0" for b in (arr > arr.mean()).flatten())


# ══════════════════════════════════════════════════════════════
#  Main App
# ══════════════════════════════════════════════════════════════

def apply_dark_theme(root):
    """PixelArtConverter 스타일 다크 테마."""
    BG = "#0c0c10"
    CARD = "#14151a"
    SURFACE = "#1a1b22"
    BORDER = "#252630"
    INPUT = "#1e1f28"
    ACCENT = "#4e8ef7"
    ACCENT2 = "#34d399"
    TEXT = "#e5e7eb"
    TEXT_DIM = "#9ca3af"
    MUTED = "#6b7280"

    root.configure(bg=BG)

    style = ttk.Style()
    style.theme_use("clam")

    style.configure(".", background=BG, foreground=TEXT, bordercolor=BORDER,
                    focuscolor=ACCENT, font=("Segoe UI", 9))
    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("TLabelframe", background=CARD, foreground=ACCENT,
                    bordercolor=BORDER, relief="flat")
    style.configure("TLabelframe.Label", background=CARD, foreground=ACCENT,
                    font=("Segoe UI", 10, "bold"))
    style.configure("TNotebook", background=BG, bordercolor=BORDER,
                    tabmargins=[0, 0, 0, 0])
    style.configure("TNotebook.Tab", background=SURFACE, foreground=MUTED,
                    padding=[16, 8], font=("Segoe UI", 9, "bold"))
    style.map("TNotebook.Tab",
              background=[("selected", ACCENT)],
              foreground=[("selected", "#ffffff")])
    style.configure("TButton", background=ACCENT, foreground="#ffffff",
                    padding=[14, 6], font=("Segoe UI", 9, "bold"),
                    borderwidth=0)
    style.map("TButton",
              background=[("active", "#3b7ee0"), ("pressed", "#2d6bcf")])
    style.configure("Secondary.TButton", background=SURFACE, foreground=TEXT_DIM,
                    padding=[10, 5], borderwidth=1)
    style.map("Secondary.TButton",
              background=[("active", INPUT)])
    style.configure("Success.TButton", background=ACCENT2, foreground="#ffffff",
                    padding=[14, 6], font=("Segoe UI", 9, "bold"))
    style.configure("TEntry", fieldbackground=INPUT, foreground=TEXT,
                    bordercolor=BORDER, insertcolor=TEXT, padding=[8, 6])
    style.map("TEntry", bordercolor=[("focus", ACCENT)])
    style.configure("TSpinbox", fieldbackground=INPUT, foreground=TEXT,
                    bordercolor=BORDER, arrowcolor=TEXT_DIM, padding=[6, 4])
    style.configure("TCheckbutton", background=BG, foreground=TEXT)
    style.map("TCheckbutton", background=[("active", SURFACE)])
    style.configure("TProgressbar", background=ACCENT, troughcolor=INPUT,
                    bordercolor=BORDER, thickness=6)
    style.configure("TScrollbar", background=SURFACE, troughcolor=BG,
                    bordercolor=BORDER, arrowcolor=TEXT_DIM)
    style.configure("TPanedwindow", background=BG)

    return {"bg": BG, "card": CARD, "surface": SURFACE, "border": BORDER,
            "input": INPUT, "accent": ACCENT, "accent2": ACCENT2,
            "text": TEXT, "text_dim": TEXT_DIM, "muted": MUTED}


class LevelDesignStudio:
    def __init__(self, root):
        self.root = root
        self.root.title("Level Design Studio")
        self.root.geometry("1000x750")
        self.root.minsize(900, 650)
        self._running = False

        self.colors = apply_dark_theme(root)
        C = self.colors

        # 타이틀 바
        title_frame = tk.Frame(root, bg=C["card"], height=44)
        title_frame.pack(fill="x")
        title_frame.pack_propagate(False)
        tk.Label(title_frame, text="  Level Design Studio",
                 bg=C["card"], fg="#ffffff",
                 font=("Segoe UI", 14, "bold")).pack(side="left", padx=12, pady=8)
        tk.Label(title_frame, text="v1.0",
                 bg=C["card"], fg=C["accent"],
                 font=("Segoe UI", 9)).pack(side="left", padx=2)
        tk.Frame(title_frame, bg=C["border"], height=1).pack(side="bottom", fill="x")

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self._build_tab_yolo()
        self._build_tab_extract()
        self._build_tab_crop()
        self._build_tab_pixelforge()

    # ── 공통 ──
    def _browse_dir(self, var):
        d = filedialog.askdirectory()
        if d: var.set(d)

    def _browse_file(self, var, ftypes):
        f = filedialog.askopenfilename(filetypes=ftypes + [("All", "*.*")])
        if f: var.set(f)

    def _make_log(self, parent):
        f = ttk.LabelFrame(parent, text="로그", padding=4)
        f.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        t = tk.Text(f, font=("Consolas", 9), state="disabled",
                    bg="#0a0a0e", fg="#9ca3af", insertbackground="#e5e7eb",
                    selectbackground="#4e8ef7", selectforeground="#ffffff",
                    relief="flat", padx=10, pady=6, height=12,
                    borderwidth=0, highlightthickness=1,
                    highlightbackground="#252630", highlightcolor="#4e8ef7")
        t.pack(fill="both", expand=True)
        return t

    def _log(self, widget, msg):
        widget.configure(state="normal")
        widget.insert("end", msg + "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _log_safe(self, widget, msg):
        self.root.after(0, self._log, widget, msg)

    # ══════════════════════════════════════════════════════════
    #  Tab 1: YOLO 학습
    # ══════════════════════════════════════════════════════════

    def _build_tab_yolo(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="1. YOLO 학습")

        inp = ttk.LabelFrame(tab, text="입력", padding=8)
        inp.pack(fill="x", padx=10, pady=5)

        ttk.Label(inp, text="이미지 폴더:").grid(row=0, column=0, sticky="w")
        self.yolo_img_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.yolo_img_var, width=55).grid(row=0, column=1, padx=5)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_dir(self.yolo_img_var)).grid(row=0, column=2)

        ttk.Label(inp, text="session_log:").grid(row=1, column=0, sticky="w", pady=2)
        self.yolo_log_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.yolo_log_var, width=55).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_file(self.yolo_log_var, [("JSONL", "*.jsonl")])).grid(row=1, column=2)

        ttk.Label(inp, text="게임 ID:").grid(row=2, column=0, sticky="w")
        self.yolo_game_var = tk.StringVar(value="new_game")
        ttk.Entry(inp, textvariable=self.yolo_game_var, width=20).grid(row=2, column=1, sticky="w", padx=5)

        ttk.Label(inp, text="출력 폴더:").grid(row=3, column=0, sticky="w", pady=2)
        self.yolo_out_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.yolo_out_var, width=55).grid(row=3, column=1, padx=5, pady=2)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_dir(self.yolo_out_var)).grid(row=3, column=2)
        inp.columnconfigure(1, weight=1)

        btn = ttk.Frame(tab)
        btn.pack(fill="x", padx=10, pady=3)
        ttk.Button(btn, text="자동 분류 + 학습", command=self._run_yolo_train).pack(side="left")
        self.yolo_progress = ttk.Progressbar(btn, length=250, maximum=100)
        self.yolo_progress.pack(side="right", padx=5)
        self.yolo_status = tk.StringVar(value="대기 중")
        ttk.Label(btn, textvariable=self.yolo_status).pack(side="right")

        self.yolo_log = self._make_log(tab)

    def _run_yolo_train(self):
        if self._running: return
        self._running = True
        threading.Thread(target=self._do_yolo_train, daemon=True).start()

    def _do_yolo_train(self):
        try:
            data_dir = Path(self.yolo_img_var.get())
            log_path = Path(self.yolo_log_var.get())
            game_id = self.yolo_game_var.get()
            out_base = Path(self.yolo_out_var.get()) if self.yolo_out_var.get() else DATA_DIR / "games" / game_id

            self._log_safe(self.yolo_log, "이벤트 로드 중...")
            events = []
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    e = json.loads(line.strip())
                    if e.get("event") != "episode_start":
                        events.append(e)
            self._log_safe(self.yolo_log, f"Events: {len(events)}")

            # 자동 분류
            stage_start, gameplay, other = [], [], []
            big_streak = 0
            for evt in events:
                d = evt.get("delta_from_prev")
                if d is None: big_streak = 0; continue
                af = evt.get("after_file", "")
                if not af or not (data_dir / af).exists(): continue
                if d > 0.7: big_streak += 1; other.append(af)
                elif d < 0.05 and big_streak >= 1: stage_start.append(af); big_streak = 0
                elif d < 0.1: gameplay.append(af); big_streak = 0
                else: other.append(af); big_streak = 0

            self._log_safe(self.yolo_log, f"분류: stage_start={len(stage_start)} gameplay={len(gameplay)} other={len(other)}")

            # 데이터셋 생성
            yolo_dir = out_base / "yolo_dataset"
            train_dir = yolo_dir / "train"
            val_dir = yolo_dir / "val"
            for cls in ["gameplay", "lobby", "stage_start"]:
                (train_dir / cls).mkdir(parents=True, exist_ok=True)
                (val_dir / cls).mkdir(parents=True, exist_ok=True)

            random.seed(42)
            for cls_name, cls_list in [("stage_start", stage_start), ("gameplay", gameplay), ("lobby", other)]:
                samples = random.sample(cls_list, min(50, len(cls_list)))
                for i, fn in enumerate(samples):
                    d = train_dir if i < 40 else val_dir
                    shutil.copy2(data_dir / fn, d / cls_name / fn)

            self._log_safe(self.yolo_log, "YOLO 학습 시작...")
            model = YOLO("yolo11n-cls.pt")
            model.train(data=str(yolo_dir), epochs=50, imgsz=224, batch=16,
                        patience=15, project=str(yolo_dir / "models"), name="train_v1",
                        exist_ok=True, device="cpu", verbose=False)

            best = yolo_dir / "models" / "train_v1" / "weights" / "best.pt"
            self._log_safe(self.yolo_log, f"\n완료: {best}")
            self._log_safe(self.yolo_log, f"Classes: {YOLO(str(best)).names}")
            self.root.after(0, lambda: self.yolo_status.set("완료"))

        except Exception as e:
            self._log_safe(self.yolo_log, f"ERROR: {e}")
        finally:
            self._running = False

    # ══════════════════════════════════════════════════════════
    #  Tab 2: 스테이지 추출
    # ══════════════════════════════════════════════════════════

    def _build_tab_extract(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="2. 스테이지 추출")

        inp = ttk.LabelFrame(tab, text="입력", padding=8)
        inp.pack(fill="x", padx=10, pady=5)

        ttk.Label(inp, text="이미지 폴더:").grid(row=0, column=0, sticky="w")
        self.ext_img_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.ext_img_var, width=55).grid(row=0, column=1, padx=5)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_dir(self.ext_img_var)).grid(row=0, column=2)

        ttk.Label(inp, text="session_log:").grid(row=1, column=0, sticky="w", pady=2)
        self.ext_log_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.ext_log_var, width=55).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_file(self.ext_log_var, [("JSONL", "*.jsonl")])).grid(row=1, column=2)

        ttk.Label(inp, text="YOLO 모델:").grid(row=2, column=0, sticky="w")
        self.ext_model_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.ext_model_var, width=55).grid(row=2, column=1, padx=5)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_file(self.ext_model_var, [("PyTorch", "*.pt")])).grid(row=2, column=2)

        ttk.Label(inp, text="출력 폴더:").grid(row=3, column=0, sticky="w", pady=2)
        self.ext_out_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.ext_out_var, width=55).grid(row=3, column=1, padx=5, pady=2)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_dir(self.ext_out_var)).grid(row=3, column=2)
        inp.columnconfigure(1, weight=1)

        btn = ttk.Frame(tab)
        btn.pack(fill="x", padx=10, pady=3)
        ttk.Button(btn, text="추출 시작", command=self._run_extract).pack(side="left")
        self.ext_progress = ttk.Progressbar(btn, length=250, maximum=100)
        self.ext_progress.pack(side="right", padx=5)

        self.ext_log = self._make_log(tab)

    def _run_extract(self):
        if self._running: return
        self._running = True
        threading.Thread(target=self._do_extract, daemon=True).start()

    def _do_extract(self):
        try:
            data_dir = Path(self.ext_img_var.get())
            log_path = Path(self.ext_log_var.get())
            out_dir = Path(self.ext_out_var.get())
            out_dir.mkdir(parents=True, exist_ok=True)

            events = []
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    e = json.loads(line.strip())
                    if e.get("event") != "episode_start":
                        events.append(e)

            targets = [{"idx": i, "file": evt.get("after_file", "")}
                       for i, evt in enumerate(events)
                       if evt.get("delta_from_prev", 0) and evt["delta_from_prev"] > 0.5
                       and evt.get("after_file") and (data_dir / evt["after_file"]).exists()]

            self._log_safe(self.ext_log, f"Events: {len(events)}, Targets: {len(targets)}")

            model = YOLO(self.ext_model_var.get())
            stage_starts = []
            total = len(targets)
            for i in range(0, total, 16):
                batch = targets[i:i + 16]
                paths = [str(data_dir / t["file"]) for t in batch]
                for t, pred in zip(batch, model.predict(paths, verbose=False, stream=True)):
                    if pred.probs and model.names[int(pred.probs.top1)] == "stage_start":
                        stage_starts.append(t)
                self.root.after(0, lambda p=min(i+16,total)/total*100: self.ext_progress.configure(value=p))
                if (i + 16) % 200 < 16:
                    self._log_safe(self.ext_log, f"  {min(i+16,total)}/{total} → {len(stage_starts)}")

            # Dedup
            unique, seen = [], []
            for s in stage_starts:
                h = img_hash(data_dir / s["file"])
                if not any(sum(a != b for a, b in zip(h, sh)) < 20 for sh in seen):
                    unique.append(s); seen.append(h)

            for i, s in enumerate(unique):
                shutil.copy2(data_dir / s["file"], out_dir / f"stage_{i+1:03d}.png")

            with open(out_dir / "index.json", "w", encoding="utf-8") as f:
                json.dump({"total": len(unique), "stages": [
                    {"stage": i+1, "file": f"stage_{i+1:03d}.png", "source": s["file"]}
                    for i, s in enumerate(unique)
                ]}, f, indent=2, ensure_ascii=False)

            self._log_safe(self.ext_log, f"\n완료: {len(unique)}개 → {out_dir}")

        except Exception as e:
            self._log_safe(self.ext_log, f"ERROR: {e}")
        finally:
            self._running = False

    # ══════════════════════════════════════════════════════════
    #  Tab 3: Crop + JSON
    # ══════════════════════════════════════════════════════════

    def _build_tab_crop(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="3. Crop + JSON")

        inp = ttk.LabelFrame(tab, text="입력", padding=8)
        inp.pack(fill="x", padx=10, pady=5)

        ttk.Label(inp, text="추출 폴더:").grid(row=0, column=0, sticky="w")
        self.crop_in_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.crop_in_var, width=55).grid(row=0, column=1, padx=5)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_dir(self.crop_in_var)).grid(row=0, column=2)

        ttk.Label(inp, text="출력 폴더:").grid(row=1, column=0, sticky="w", pady=2)
        self.crop_out_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.crop_out_var, width=55).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_dir(self.crop_out_var)).grid(row=1, column=2)

        opt = ttk.Frame(inp)
        opt.grid(row=2, column=0, columnspan=3, sticky="w", pady=5)

        ttk.Label(opt, text="보드(x,y,w,h):").pack(side="left")
        self.crop_board_var = tk.StringVar(value="155,333,735,663")
        ttk.Entry(opt, textvariable=self.crop_board_var, width=20).pack(side="left", padx=5)

        ttk.Label(opt, text="그리드:").pack(side="left", padx=(10, 0))
        self.crop_grid_var = tk.IntVar(value=50)
        ttk.Spinbox(opt, from_=10, to=50, textvariable=self.crop_grid_var, width=4).pack(side="left", padx=2)

        ttk.Label(opt, text="시작 레벨:").pack(side="left", padx=(10, 0))
        self.crop_start_var = tk.IntVar(value=51)
        ttk.Spinbox(opt, from_=1, to=9999, textvariable=self.crop_start_var, width=5).pack(side="left", padx=2)

        self.crop_flip_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="상하반전", variable=self.crop_flip_var).pack(side="left", padx=10)

        # Cell Profile 옵션
        prof_frame = ttk.Frame(inp)
        prof_frame.grid(row=3, column=0, columnspan=3, sticky="w", pady=3)
        self.crop_cellaware_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(prof_frame, text="Cell-Aware", variable=self.crop_cellaware_var).pack(side="left")
        ttk.Label(prof_frame, text="프로파일:").pack(side="left", padx=(10, 0))
        self.crop_profile_var = tk.StringVar(
            value=str(Path("E:/AI/virtual_player/data/journal/games/pixelflow/cell_profile.json")))
        ttk.Entry(prof_frame, textvariable=self.crop_profile_var, width=40).pack(side="left", padx=5)
        ttk.Button(prof_frame, text="찾기",
                   command=lambda: self._browse_file(self.crop_profile_var, [("JSON", "*.json")])).pack(side="left")

        inp.columnconfigure(1, weight=1)

        btn = ttk.Frame(tab)
        btn.pack(fill="x", padx=10, pady=3)
        ttk.Button(btn, text="Crop + JSON 변환", command=self._run_crop).pack(side="left")
        ttk.Button(btn, text="Cell-Aware 변환", command=self._run_cellaware_crop).pack(side="left", padx=5)
        ttk.Button(btn, text="모티프 추출", command=self._run_motif_extract).pack(side="left", padx=5)
        ttk.Button(btn, text="렌더링 범위 측정", command=self._run_measure_ranges).pack(side="left", padx=5)
        self.crop_progress = ttk.Progressbar(btn, length=250, maximum=100)
        self.crop_progress.pack(side="right", padx=5)

        self.crop_log = self._make_log(tab)

    def _run_motif_extract(self):
        """출력 폴더의 JSON들에서 모티프 추출 (배경색 제거)."""
        out_dir = self.crop_out_var.get()
        if not out_dir:
            messagebox.showwarning("경고", "출력 폴더를 지정하세요")
            return
        out = Path(out_dir)
        jsons = sorted(out.glob("*.json"))
        jsons = [j for j in jsons if "_analysis" not in j.name]
        if not jsons:
            self._log_safe(self.crop_log, "JSON 없음")
            return

        motif_dir = out / "motifs"
        motif_dir.mkdir(exist_ok=True)
        count = 0

        for jf in jsons:
            try:
                grid, data = self._load_grid(str(jf))
                motif, bg = self._extract_motif(grid)
                # 모티프 JSON 저장
                fm = "\n".join(" ".join(f"{c:02d}" for c in row) for row in motif)
                data["designer_note"] = f"[FieldMap]\n{fm}"
                content_counts = Counter(c for row in motif for c in row if c > 0)
                data["num_colors"] = len(content_counts)
                data["color_distribution"] = " ".join(
                    f"c{cid}:{cnt}" for cid, cnt in sorted(content_counts.items(), key=lambda x: -x[1]))
                data["total_cells"] = sum(content_counts.values())
                data["motif_bg_removed"] = bg

                with open(motif_dir / jf.name, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)

                # 모티프 시각화
                img = self._render_grid(motif, cell=8)
                img.save(str(motif_dir / jf.name.replace(".json", ".png")))
                count += 1
            except Exception as e:
                self._log_safe(self.crop_log, f"  {jf.name}: {e}")

        self._log_safe(self.crop_log, f"모티프 추출 완료: {count}/{len(jsons)} → {motif_dir}")

    def _run_measure_ranges(self):
        if self._running: return
        self._running = True
        threading.Thread(target=self._do_measure_ranges, daemon=True).start()

    def _do_measure_ranges(self):
        try:
            in_dir = Path(self.crop_in_var.get())
            palette = load_palette()
            pal_arr = np.array([p["rgb"] for p in palette], dtype=np.float32)
            pal_ids = [p["id"] for p in palette]
            pal_names = {p["id"]: p["name"] for p in palette}

            boards = sorted(in_dir.glob("stage_*.png"))[:20]
            self._log_safe(self.crop_log, f"측정: {len(boards)}장에서 렌더링 범위 추출")

            BOARD = tuple(int(x) for x in self.crop_board_var.get().split(","))
            all_px = {}

            for bp in boards:
                img = np.array(Image.open(bp).convert("RGB"))
                bx, by, bw, bh = BOARD
                board = img[by:by+bh, bx:bx+bw].reshape(-1, 3).astype(np.float32)
                dists = np.sqrt(np.sum((board[:, None, :] - pal_arr[None, :, :]) ** 2, axis=2))
                nearest = np.argmin(dists, axis=1)
                for pi, px in zip(nearest, board):
                    pid = pal_ids[pi]
                    if pid not in all_px: all_px[pid] = []
                    if len(all_px[pid]) < 10000: all_px[pid].append(px)

            ranges = {}
            for pid, pxs in all_px.items():
                if len(pxs) < 100: continue
                arr = np.array(pxs)
                ranges[pid] = {
                    "name": pal_names[pid], "ref_rgb": next(p["rgb"] for p in palette if p["id"] == pid),
                    "render_min": np.percentile(arr, 5, axis=0).tolist(),
                    "render_max": np.percentile(arr, 95, axis=0).tolist(),
                    "render_mean": arr.mean(axis=0).tolist(),
                }

            out = in_dir / "color_render_ranges.json"
            with open(out, "w", encoding="utf-8") as f:
                json.dump(ranges, f, indent=2, ensure_ascii=False)
            self._log_safe(self.crop_log, f"저장: {out} ({len(ranges)} colors)")

        except Exception as e:
            self._log_safe(self.crop_log, f"ERROR: {e}")
        finally:
            self._running = False

    def _run_cellaware_crop(self):
        """Cell-Aware 모드로 Crop + JSON 변환."""
        if self._running: return
        self._running = True
        threading.Thread(target=self._do_cellaware_crop, daemon=True).start()

    def _do_cellaware_crop(self):
        try:
            from cell_aware_analyzer import analyze, analyze_batch, load_profile

            profile_path = self.crop_profile_var.get().strip()
            if not profile_path or not Path(profile_path).exists():
                self._log_safe(self.crop_log, "ERROR: cell_profile.json 경로를 지정해주세요")
                return

            profile = load_profile(profile_path)
            in_dir = Path(self.crop_in_var.get())
            out_dir = Path(self.crop_out_var.get() or str(in_dir / "cell_aware_output"))
            out_dir.mkdir(parents=True, exist_ok=True)
            start_level = self.crop_start_var.get()

            # 보드 크롭 먼저 (고정 영역)
            BOARD = tuple(int(x) for x in self.crop_board_var.get().split(","))
            images = sorted(in_dir.glob("stage_*.png"))
            if not images:
                images = sorted(in_dir.glob("*.png"))

            self._log_safe(self.crop_log, f"Cell-Aware 변환: {len(images)}장, profile={Path(profile_path).name}")
            self._log_safe(self.crop_log, f"  grid: {profile['grid']['rows']}x{profile['grid']['cols']}, "
                          f"frame_colors: {profile['colors'].get('frame_color_names', [])}")

            for i, img_path in enumerate(images):
                level_num = start_level + i
                name = img_path.stem

                # 보드 크롭
                img = np.array(Image.open(img_path).convert("RGB"))
                bx, by, bw, bh = BOARD
                if by + bh <= img.shape[0] and bx + bw <= img.shape[1]:
                    board_crop = img[by:by+bh, bx:bx+bw]
                else:
                    board_crop = img

                # 크롭 이미지 임시 저장
                board_path = out_dir / f"{name}_board.png"
                Image.fromarray(board_crop).save(str(board_path))

                # Cell-Aware 분석
                result = analyze(str(board_path), profile, output_dir=str(out_dir), level_num=level_num)

                if "error" in result:
                    self._log_safe(self.crop_log, f"  [{i+1}] {name}: FAIL - {result['error']}")
                else:
                    self._log_safe(self.crop_log,
                        f"  [{i+1}] Lv{level_num}: {result['num_colors']}색, "
                        f"content={result['elements']['content']}, "
                        f"floor={result['elements']['floor']}")

                pct = (i + 1) / len(images) * 100
                self.root.after(0, lambda p=pct: self.crop_progress.configure(value=p))

            self._log_safe(self.crop_log, f"완료: {out_dir}")

        except Exception as e:
            self._log_safe(self.crop_log, f"ERROR: {e}")
            import traceback
            self._log_safe(self.crop_log, traceback.format_exc())
        finally:
            self._running = False

    def _run_crop(self):
        if self._running: return
        self._running = True
        threading.Thread(target=self._do_crop, daemon=True).start()

    def _do_crop(self):
        try:
            in_dir = Path(self.crop_in_var.get())
            out_dir = Path(self.crop_out_var.get()) if self.crop_out_var.get() else in_dir
            json_dir = out_dir / "json"
            board_dir = out_dir / "boards"
            json_dir.mkdir(parents=True, exist_ok=True)
            board_dir.mkdir(parents=True, exist_ok=True)

            index = json.loads((in_dir / "index.json").read_text(encoding="utf-8"))
            palette = load_palette()
            pal_arr = np.array([p["rgb"] for p in palette], dtype=np.float32) if palette else None
            pal_ids = [p["id"] for p in palette]
            pal_names = {p["id"]: p["name"] for p in palette}

            # 렌더링 범위 로드
            range_path = in_dir / "color_render_ranges.json"
            range_means = {}
            if range_path.exists():
                with open(range_path, encoding="utf-8") as f:
                    rr = json.load(f)
                range_means = {int(k): np.array(v["render_mean"]) for k, v in rr.items()}
                self._log_safe(self.crop_log, f"렌더링 범위 로드: {len(range_means)} colors")

            BOARD = tuple(int(x) for x in self.crop_board_var.get().split(","))
            GRID = self.crop_grid_var.get()
            FLIP = self.crop_flip_var.get()
            START = self.crop_start_var.get()

            def match_center(rgb):
                best_pid, best_d = 8, float("inf")
                for pid, rmean in range_means.items():
                    d = np.sqrt(np.sum((rgb - rmean) ** 2))
                    if d < best_d: best_d, best_pid = d, pid
                return best_pid

            total = len(index["stages"])
            self._log_safe(self.crop_log, f"처리: {total}장 (grid={GRID})")

            for entry in index["stages"]:
                fp = in_dir / entry["file"]
                img = np.array(Image.open(fp).convert("RGB"))
                bx, by, bw, bh = BOARD
                board = img[by:by+bh, bx:bx+bw]
                Image.fromarray(board).save(str(board_dir / entry["file"]))

                pixels = board.reshape(-1, 3).astype(np.float32)

                # 팔레트 매칭 함수 (렌더링 범위 있으면 사용, 없으면 직접 매칭)
                pal_arr_local = np.array([p["rgb"] for p in palette], dtype=np.float32) if palette else None
                pal_ids_local = [p["id"] for p in palette] if palette else []

                def match_to_palette(rgb):
                    if range_means:
                        return match_center(rgb)
                    elif pal_arr_local is not None:
                        bi = int(np.argmin(np.sqrt(np.sum((pal_arr_local - rgb) ** 2, axis=1))))
                        return pal_ids_local[bi]
                    return 8

                if SKLEARN:
                    # 색상 수 추정
                    sample = pixels[::50]
                    pid_counts = Counter(match_to_palette(px) for px in sample)
                    sig = {k for k, v in pid_counts.items() if v > len(sample) * 0.02}
                    k = max(2, min(len(sig), 8))

                    km = KMeans(n_clusters=k, random_state=42, n_init=5, max_iter=30)
                    km.fit(pixels)

                    # 클러스터 → 팔레트 (중복 허용 안 함)
                    color_map = {}
                    used = set()
                    # 클러스터 크기 순으로 매칭 (큰 클러스터 우선)
                    cluster_sizes = [(ci, (km.labels_ == ci).sum()) for ci in range(k)]
                    cluster_sizes.sort(key=lambda x: -x[1])

                    for ci, _ in cluster_sizes:
                        pid = match_to_palette(km.cluster_centers_[ci])
                        if pid in used:
                            # 차선책: 모든 팔레트에서 가장 가까운 미사용 색
                            all_pids = list(range_means.keys()) if range_means else pal_ids_local
                            for alt in sorted(all_pids,
                                              key=lambda p: np.sqrt(np.sum((
                                                  km.cluster_centers_[ci] - (range_means[p] if range_means else pal_arr_local[pal_ids_local.index(p)])
                                              ) ** 2)) if p not in used else float("inf")):
                                if alt not in used:
                                    pid = alt; break
                        color_map[ci] = pid
                        used.add(pid)

                    # 셀 다수결
                    labels_2d = km.labels_.reshape(board.shape[0], board.shape[1])
                    fm_rows, counts = [], Counter()
                    for r in range(GRID):
                        tokens = []
                        for c in range(GRID):
                            y1, y2 = int(r * bh / GRID), int((r + 1) * bh / GRID)
                            x1, x2 = int(c * bw / GRID), int((c + 1) * bw / GRID)
                            majority = Counter(labels_2d[y1:y2, x1:x2].flatten()).most_common(1)[0][0]
                            pid = color_map[majority]
                            tokens.append(f"{pid:02d}"); counts[pid] += 1
                        fm_rows.append(tokens)
                else:
                    fm_rows, counts = [], Counter()
                    for r in range(GRID):
                        tokens = []
                        for c in range(GRID):
                            tokens.append("08"); counts[8] += 1
                        fm_rows.append(tokens)

                if FLIP: fm_rows.reverse()

                fieldmap = "\n".join(" ".join(r) for r in fm_rows)
                tot = sum(counts.values()); nc = len(counts)
                cd = " ".join(f"c{cid}:{cnt}" for cid, cnt in sorted(counts.items(), key=lambda x: -x[1]))
                lv = START + entry["stage"] - 1

                lj = {
                    "level_number": lv, "level_id": f"L{lv:04d}",
                    "pkg": (lv-1)//10+1, "pos": (lv-1)%10+1, "chapter": (lv-1)//50+1,
                    "purpose_type": "Normal", "target_cr": 0, "target_attempts": 0.0,
                    "num_colors": nc, "color_distribution": cd,
                    "field_rows": GRID, "field_columns": GRID, "total_cells": tot,
                    "rail_capacity": 5, "rail_capacity_tier": "S",
                    "queue_columns": min(nc, 5), "queue_rows": 3,
                    "gimmick_hidden": 0, "gimmick_chain": 0, "gimmick_pinata": 0,
                    "gimmick_spawner_t": 0, "gimmick_pin": 0, "gimmick_lock_key": 0,
                    "gimmick_surprise": 0, "gimmick_wall": 0, "gimmick_spawner_o": 0,
                    "gimmick_pinata_box": 0, "gimmick_ice": 0, "gimmick_frozen_dart": 0,
                    "gimmick_curtain": 0, "total_darts": tot,
                    "dart_capacity_range": ",".join([str(tot // max(nc, 1))] * min(nc, 5)),
                    "emotion_curve": "", "designer_note": f"[FieldMap]\n{fieldmap}",
                    "pixel_art_source": entry.get("source", entry["file"]),
                }
                with open(json_dir / f"level_{lv:03d}.json", "w", encoding="utf-8") as f:
                    json.dump(lj, f, indent=2, ensure_ascii=False)

                if entry["stage"] % 50 == 0:
                    self._log_safe(self.crop_log, f"  {entry['stage']}/{total}")
                    self.root.after(0, lambda p=entry["stage"]/total*100: self.crop_progress.configure(value=p))

            self._log_safe(self.crop_log, f"\n완료: boards={board_dir} json={json_dir}")

        except Exception as e:
            self._log_safe(self.crop_log, f"ERROR: {e}")
        finally:
            self._running = False

    # ══════════════════════════════════════════════════════════
    #  Tab 4: 스타일 편집
    # ══════════════════════════════════════════════════════════

    # Tab 4 제거됨 — 모티프 추출은 Tab 3 "모티프 추출" 버튼으로 이동

    def _load_grid(self, json_path):
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        rows = [line.split() for line in data["designer_note"].split("[FieldMap]\n")[1].strip().split("\n")]
        return [[int(t) if t != ".." else 0 for t in row] for row in rows], data

    def _render_grid(self, grid, cell=8):
        palette = load_palette()
        colors = {p["id"]: tuple(p["rgb"]) for p in palette}
        h, w = len(grid), len(grid[0])
        img = Image.new("RGB", (w * cell, h * cell), (40, 40, 40))
        draw = ImageDraw.Draw(img)
        for y, row in enumerate(grid):
            for x, c in enumerate(row):
                color = colors.get(c, (40, 40, 40))
                draw.rectangle([x * cell, y * cell, (x + 1) * cell - 1, (y + 1) * cell - 1], fill=color)
        return img

    def _extract_motif(self, grid):
        h, w = len(grid), len(grid[0])
        border = [grid[0][x] for x in range(w)] + [grid[h-1][x] for x in range(w)] + \
                 [grid[y][0] for y in range(h)] + [grid[y][w-1] for y in range(h)]
        bg = Counter(border).most_common(1)[0][0]
        return [[0 if c == bg else c for c in row] for row in grid], bg

    # _style_op, _style_save 제거됨 — 모티프 추출은 Tab 3의 _run_motif_extract로 이동

    # ══════════════════════════════════════════════════════════
    #  Tab 4: PixelForge — AI 레벨 보드 생성
    # ══════════════════════════════════════════════════════════

    def _pf_analyze_ref(self, path):
        """레퍼런스 이미지 분석 → 셀 크기 + 형태 인식 + 색상."""
        import cv2
        from scipy.signal import find_peaks

        img = Image.open(path)
        arr = np.array(img.convert("RGB"))
        h, w, _ = arr.shape
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)

        # 셀 피치 감지 (autocorrelation)
        cell_w, cell_h = 30, 30
        for axis, size in [(1, h), (0, w)]:
            edges = cv2.Sobel(gray, cv2.CV_64F, 1 - axis, axis, ksize=3)
            profile = np.mean(np.abs(edges), axis=1 if axis == 1 else 0)
            corr = np.correlate(profile, profile, mode="full")
            corr = corr[len(corr) // 2:]
            peaks, _ = find_peaks(corr, distance=10, prominence=corr.max() * 0.1)
            pitch = int(np.median(np.diff(peaks))) if len(peaks) > 1 else 30
            if axis == 1:
                cell_h = pitch
            else:
                cell_w = pitch

        cols = w // cell_w
        rows = h // cell_h

        # BLIP 이미지 캡셔닝 — 형태 인식
        subject = "unknown"
        try:
            from transformers import BlipProcessor, BlipForConditionalGeneration
            bp = BlipProcessor.from_pretrained(
                "Salesforce/blip-image-captioning-base", cache_dir=str(DATA_DIR / "huggingface"))
            bm = BlipForConditionalGeneration.from_pretrained(
                "Salesforce/blip-image-captioning-base", cache_dir=str(DATA_DIR / "huggingface"))
            inputs = bp(img, return_tensors="pt")
            out = bm.generate(**inputs, max_new_tokens=30)
            subject = bp.decode(out[0], skip_special_tokens=True)
            del bp, bm  # 메모리 해제
        except Exception:
            subject = "pixel art board"

        # 주요 색상 분석
        from sklearn.cluster import KMeans
        pixels = arr.reshape(-1, 3).astype(np.float32)
        idx = np.random.default_rng(42).choice(len(pixels), min(5000, len(pixels)), replace=False)
        km = KMeans(n_clusters=6, n_init=3, random_state=42).fit(pixels[idx])
        colors = km.cluster_centers_.astype(int)
        counts = np.bincount(km.predict(pixels[idx]), minlength=6)
        top_idx = np.argsort(-counts)[:4]

        def cn(rgb):
            r, g, b = int(rgb[0]), int(rgb[1]), int(rgb[2])
            if max(r, g, b) - min(r, g, b) < 30:
                return "white" if (r + g + b) / 3 > 200 else "gray"
            if r > g and r > b: return "red"
            if g > r and g > b: return "green"
            if b > r and b > g: return "blue"
            if r > 200 and g > 150: return "orange" if g < 200 else "yellow"
            if r > 150 and b > 150: return "purple"
            return "colorful"

        color_names = list(set(cn(colors[i]) for i in top_idx))

        return cols, rows, subject, color_names

    def _build_tab_pixelforge(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="  PixelForge  ")
        C = self.colors

        # ── 상단: 설정 영역 ──
        settings = ttk.LabelFrame(tab, text="생성 설정", padding=8)
        settings.pack(fill="x", padx=8, pady=(8, 4))

        # Row 0: 레퍼런스 이미지 + 자동 분석
        r0 = tk.Frame(settings, bg=C["card"])
        r0.pack(fill="x", pady=2)
        tk.Label(r0, text="레퍼런스:", bg=C["card"], fg=C["text"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.pf_ref_path = tk.StringVar(value="")
        tk.Entry(r0, textvariable=self.pf_ref_path, width=50,
                 bg=C["input"], fg=C["text"], insertbackground=C["text"],
                 relief="flat").pack(side="left", padx=4)
        ttk.Button(r0, text="찾기", command=lambda: self._browse_file(
            self.pf_ref_path, [("Images", "*.png *.jpg")])).pack(side="left", padx=2)
        ttk.Button(r0, text="🔍 분석", command=self._pf_analyze).pack(side="left", padx=4)

        # Row 1: API Key
        r1 = tk.Frame(settings, bg=C["card"])
        r1.pack(fill="x", pady=2)
        tk.Label(r1, text="API Key:", bg=C["card"], fg=C["text"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.pf_api_key = tk.StringVar(value=os.environ.get("PIXELLAB_API_KEY", ""))
        tk.Entry(r1, textvariable=self.pf_api_key, width=40, show="*",
                 bg=C["input"], fg=C["text"], insertbackground=C["text"],
                 relief="flat").pack(side="left", padx=(4, 12))
        tk.Label(r1, text="잔여:", bg=C["card"], fg=C["text_dim"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.pf_balance = tk.StringVar(value="--")
        tk.Label(r1, textvariable=self.pf_balance, bg=C["card"], fg=C["accent"],
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=4)
        ttk.Button(r1, text="잔액 확인", command=self._pf_check_balance).pack(side="left", padx=4)

        # Row 2: 프롬프트 (자동 입력됨)
        r2 = tk.Frame(settings, bg=C["card"])
        r2.pack(fill="x", pady=2)
        tk.Label(r2, text="프롬프트:", bg=C["card"], fg=C["text"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.pf_prompt = tk.StringVar(value="cute penguin standing, front view")
        tk.Entry(r2, textvariable=self.pf_prompt, width=60,
                 bg=C["input"], fg=C["text"], insertbackground=C["text"],
                 relief="flat", font=("Segoe UI", 10)).pack(side="left", padx=4, fill="x", expand=True)

        # Row 3: 그리드 설정 (자동 입력됨)
        r3 = tk.Frame(settings, bg=C["card"])
        r3.pack(fill="x", pady=2)
        for label, var_name, default in [
            ("Cols:", "pf_cols", 50), ("Rows:", "pf_rows", 50),
            ("Cell Size:", "pf_cell_size", 24), ("API Size:", "pf_api_size", 128),
        ]:
            tk.Label(r3, text=label, bg=C["card"], fg=C["text"],
                     font=("Segoe UI", 9)).pack(side="left", padx=(8, 0))
            var = tk.IntVar(value=default)
            setattr(self, var_name, var)
            tk.Spinbox(r3, from_=8, to=200, textvariable=var, width=5,
                       bg=C["input"], fg=C["text"], relief="flat").pack(side="left", padx=2)

        self.pf_transparent = tk.BooleanVar(value=True)
        ttk.Checkbutton(r3, text="투명 배경", variable=self.pf_transparent).pack(side="left", padx=12)

        # Row 4: 출력 폴더 + 버튼
        r4 = tk.Frame(settings, bg=C["card"])
        r4.pack(fill="x", pady=(4, 0))
        tk.Label(r4, text="출력:", bg=C["card"], fg=C["text"],
                 font=("Segoe UI", 9)).pack(side="left")
        self.pf_output_dir = tk.StringVar(value=str(DATA_DIR))
        tk.Entry(r4, textvariable=self.pf_output_dir, width=40,
                 bg=C["input"], fg=C["text"], insertbackground=C["text"],
                 relief="flat").pack(side="left", padx=4)
        ttk.Button(r4, text="폴더", command=lambda: self._browse_dir(
            self.pf_output_dir)).pack(side="left", padx=2)
        ttk.Button(r4, text="🎨 생성", command=self._pf_generate).pack(side="left", padx=8)
        ttk.Button(r4, text="📂 열기", command=self._pf_open_output).pack(side="left", padx=2)

        # ── 중앙: 미리보기 ──
        preview_frame = ttk.LabelFrame(tab, text="미리보기", padding=4)
        preview_frame.pack(fill="both", expand=True, padx=8, pady=4)

        self.pf_canvas = tk.Canvas(preview_frame, bg=C["surface"],
                                   highlightthickness=0)
        self.pf_canvas.pack(fill="both", expand=True)
        self._pf_photo = None  # keep reference

        # ── 하단: 로그 ──
        self.pf_log = self._make_log(tab)

    def _pf_analyze(self):
        """레퍼런스 이미지 분석 → Cols/Rows/프롬프트 자동 입력."""
        ref = self.pf_ref_path.get().strip()
        if not ref or not Path(ref).exists():
            self._log(self.pf_log, "레퍼런스 이미지를 선택하세요")
            return
        self._log(self.pf_log, "분석 중... (BLIP 로딩)")
        self._running = True

        def _do():
            try:
                cols, rows, subject, colors = self._pf_analyze_ref(ref)
                self.root.after(0, lambda: self.pf_cols.set(cols))
                self.root.after(0, lambda: self.pf_rows.set(rows))
                self.root.after(0, lambda: self.pf_prompt.set(subject))
                self._log_safe(self.pf_log, f"분석 완료:")
                self._log_safe(self.pf_log, f"  셀: {cols}x{rows}")
                self._log_safe(self.pf_log, f"  형태: {subject}")
                self._log_safe(self.pf_log, f"  색상: {', '.join(colors)}")
            except Exception as e:
                self._log_safe(self.pf_log, f"분석 실패: {e}")
            finally:
                self._running = False

        threading.Thread(target=_do, daemon=True).start()

    def _pf_check_balance(self):
        key = self.pf_api_key.get().strip()
        if not key:
            self._log(self.pf_log, "API Key를 입력하세요")
            return
        try:
            import requests
            r = requests.get("https://api.pixellab.ai/v2/balance",
                             headers={"Authorization": f"Bearer {key}"}, timeout=10)
            data = r.json()
            gens = data.get("subscription", {}).get("generations", 0)
            total = data.get("subscription", {}).get("total", 0)
            credits = data.get("credits", {}).get("usd", 0)
            self.pf_balance.set(f"{gens}/{total} + ${credits:.2f}")
            self._log(self.pf_log, f"잔액: {gens}/{total} 생성 + ${credits:.2f} 크레딧")
        except Exception as e:
            self._log(self.pf_log, f"잔액 확인 실패: {e}")

    def _pf_generate(self):
        if self._running:
            return
        self._running = True
        threading.Thread(target=self._pf_generate_thread, daemon=True).start()

    def _pf_generate_thread(self):
        try:
            import requests
            import base64
            from io import BytesIO

            key = self.pf_api_key.get().strip()
            prompt = self.pf_prompt.get().strip()
            cols = self.pf_cols.get()
            rows = self.pf_rows.get()
            cell_size = self.pf_cell_size.get()
            api_size = self.pf_api_size.get()
            transparent = self.pf_transparent.get()

            if not key:
                self._log_safe(self.pf_log, "API Key를 입력하세요")
                return
            if not prompt:
                self._log_safe(self.pf_log, "프롬프트를 입력하세요")
                return

            # 1. PixelLab API 호출
            ref_path = self.pf_ref_path.get().strip()
            has_ref = ref_path and Path(ref_path).exists()
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

            if has_ref:
                # Bitforge: 레퍼런스 스타일 참조 생성
                self._log_safe(self.pf_log, f"[1/4] PixelLab Bitforge (스타일 참조): '{prompt}'...")
                ref_img_raw = Image.open(ref_path).convert("RGB").resize(
                    (min(128, api_size), min(128, api_size)), Image.LANCZOS)
                buf = BytesIO()
                ref_img_raw.save(buf, format="PNG")
                ref_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

                payload = {
                    "description": f"{prompt}, pixel art",
                    "image_size": {"width": api_size, "height": api_size},
                    "init_image": {"type": "base64", "base64": ref_b64},
                    "init_image_strength": 300,
                }
                endpoint = "https://api.pixellab.ai/v2/create-image-bitforge"
            else:
                # Pixflux: 텍스트만으로 생성
                self._log_safe(self.pf_log, f"[1/4] PixelLab Pixflux: '{prompt}' ({api_size}x{api_size})...")
                payload = {
                    "description": f"{prompt}, pixel art",
                    "image_size": {"width": api_size, "height": api_size},
                    "no_background": transparent,
                }
                endpoint = "https://api.pixellab.ai/v2/create-image-pixflux"

            r = requests.post(endpoint, headers=headers, json=payload, timeout=30)
            r.raise_for_status()
            data = r.json()
            img_b64 = data["image"]["base64"].split(",")[-1]
            api_img = Image.open(BytesIO(base64.b64decode(img_b64)))
            self._log_safe(self.pf_log, f"  API 완료: {api_img.size}, mode={api_img.mode}")

            # API 이미지 저장
            tag = prompt.replace(" ", "_")[:30]
            out_dir = Path(self.pf_output_dir.get())
            out_dir.mkdir(parents=True, exist_ok=True)
            api_img.save(out_dir / f"pf_{tag}_api.png")

            # 2. RGB 변환
            rgb_img = Image.new("RGB", api_img.size, (255, 255, 255))
            if api_img.mode == "RGBA":
                rgb_img.paste(api_img, mask=api_img.split()[3])
            else:
                rgb_img = api_img.convert("RGB")

            # 3. 인게임 팔레트 + 그리드 변환
            self._log_safe(self.pf_log, f"[2/4] 인게임 15색 팔레트 매핑 ({cols}x{rows})...")
            PAL = np.array([
                [252,94,94],[253,161,76],[254,213,85],[115,254,102],[57,174,46],
                [80,232,246],[50,107,248],[137,80,248],[252,106,175],[252,56,165],
                [255,255,255],[65,65,65],[111,114,127],[106,74,48],[254,227,169],
            ], dtype=np.float32)

            small = rgb_img.resize((cols, rows), Image.NEAREST)
            arr = np.array(small).astype(np.float32)
            grid = np.zeros((rows, cols, 3), dtype=np.uint8)
            for ry in range(rows):
                for cx in range(cols):
                    dists = np.sum((PAL - arr[ry, cx]) ** 2, axis=1)
                    grid[ry, cx] = PAL[np.argmin(dists)].astype(np.uint8)

            # 고립 셀 제거 (2회)
            from collections import Counter
            for _ in range(2):
                tmp = grid.copy()
                for ry in range(rows):
                    for cx in range(cols):
                        color = tuple(grid[ry, cx])
                        nb = []
                        for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                            nr, nc = ry+dr, cx+dc
                            if 0 <= nr < rows and 0 <= nc < cols:
                                nb.append(tuple(grid[nr, nc]))
                        if nb and color not in nb:
                            tmp[ry, cx] = Counter(nb).most_common(1)[0][0]
                grid = tmp

            self._log_safe(self.pf_log, f"  그리드 생성 완료: {grid.shape}")

            # 4. 셀 보드 렌더링
            self._log_safe(self.pf_log, f"[3/4] 셀 보드 렌더링 (cell={cell_size}px)...")
            from PIL import ImageDraw
            gap, corner = 2, 3
            bw = cols * (cell_size + gap) + gap
            bh = rows * (cell_size + gap) + gap

            # 배경색 판별
            pixels = grid.reshape(-1, 3)
            keys = pixels[:,0].astype(np.uint32)*65536 + pixels[:,1].astype(np.uint32)*256 + pixels[:,2].astype(np.uint32)
            bg_key = int(np.bincount(keys).argmax())
            bg_c = ((bg_key>>16)&0xFF, (bg_key>>8)&0xFF, bg_key&0xFF)

            if transparent:
                board = Image.new("RGBA", (bw, bh), (0,0,0,0))
            else:
                board = Image.new("RGBA", (bw, bh), (42,42,80,255))
            draw = ImageDraw.Draw(board)

            for ry in range(rows):
                for cx in range(cols):
                    color = tuple(int(v) for v in grid[ry, cx])
                    x = gap + cx * (cell_size + gap)
                    y = gap + ry * (cell_size + gap)
                    if transparent and sum(abs(a-b) for a,b in zip(color, bg_c)) < 60:
                        continue
                    shadow = tuple(max(0, v-50) for v in color) + (255,)
                    draw.rounded_rectangle([x+1,y+1,x+cell_size,y+cell_size], radius=corner, fill=shadow)
                    draw.rounded_rectangle([x,y,x+cell_size-1,y+cell_size-1], radius=corner, fill=color+(255,))
                    hl = tuple(min(255,v+45) for v in color) + (150,)
                    hl_s = max(3, cell_size//4)
                    draw.rounded_rectangle([x+2,y+2,x+hl_s+2,y+hl_s+2], radius=max(1,corner//2), fill=hl)

            # 저장
            board_path = out_dir / f"pf_{tag}_board.png"
            board.save(board_path)

            grid_path = out_dir / f"pf_{tag}_grid.json"
            with open(grid_path, "w", encoding="utf-8") as f:
                json.dump({"cols": cols, "rows": rows, "prompt": prompt,
                           "grid": grid.tolist()}, f, indent=2)

            self._log_safe(self.pf_log, f"[4/4] 저장 완료:")
            self._log_safe(self.pf_log, f"  보드: {board_path}")
            self._log_safe(self.pf_log, f"  JSON: {grid_path}")
            self._log_safe(self.pf_log, f"  크기: {board.size} ({cols}x{rows} 셀)")

            # 미리보기 표시
            preview = board.copy()
            pw, ph = preview.size
            max_dim = 600
            if max(pw, ph) > max_dim:
                ratio = max_dim / max(pw, ph)
                preview = preview.resize((int(pw*ratio), int(ph*ratio)), Image.NEAREST)

            self._pf_photo = ImageTk.PhotoImage(preview)
            self.root.after(0, lambda: (
                self.pf_canvas.delete("all"),
                self.pf_canvas.create_image(
                    self.pf_canvas.winfo_width()//2,
                    self.pf_canvas.winfo_height()//2,
                    image=self._pf_photo, anchor="center")))

        except Exception as e:
            self._log_safe(self.pf_log, f"에러: {e}")
            import traceback
            self._log_safe(self.pf_log, traceback.format_exc())
        finally:
            self._running = False

    def _pf_open_output(self):
        out = self.pf_output_dir.get()
        Path(out).mkdir(parents=True, exist_ok=True)
        os.startfile(out)


def main():
    for d in [DATA_DIR, DATA_DIR / "temp", DATA_DIR / "huggingface",
              DATA_DIR / "torch", DATA_DIR / "cache", DATA_DIR / "games"]:
        d.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    app = LevelDesignStudio(root)
    root.mainloop()


if __name__ == "__main__":
    main()
