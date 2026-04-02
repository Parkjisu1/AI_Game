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
DATA_DIR = SCRIPT_DIR / "studio_data"


def load_palette(game_id="balloonflow"):
    for p in [SCRIPT_DIR / "game_profiles.json", Path("game_profiles.json")]:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f).get(game_id, {}).get("color_palette_28", [])
    return []


def img_hash(path, size=16):
    arr = np.array(Image.open(path).convert("L").resize((size, size)))
    return "".join("1" if b else "0" for b in (arr > arr.mean()).flatten())


# ══════════════════════════════════════════════════════════════
#  Main App
# ══════════════════════════════════════════════════════════════

class LevelDesignStudio:
    def __init__(self, root):
        self.root = root
        self.root.title("Level Design Studio")
        self.root.geometry("1000x750")
        self.root.minsize(900, 650)
        self._running = False

        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        self._build_tab_yolo()
        self._build_tab_extract()
        self._build_tab_crop()
        self._build_tab_style()
        self._build_tab_ai()

    # ── 공통 ──
    def _browse_dir(self, var):
        d = filedialog.askdirectory()
        if d: var.set(d)

    def _browse_file(self, var, ftypes):
        f = filedialog.askopenfilename(filetypes=ftypes + [("All", "*.*")])
        if f: var.set(f)

    def _make_log(self, parent):
        f = ttk.LabelFrame(parent, text="로그", padding=3)
        f.pack(fill="both", expand=True, padx=5, pady=5)
        t = tk.Text(f, font=("Consolas", 9), state="disabled", bg="#1e1e1e", fg="#cccccc", height=12)
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

        self.crop_flip_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="상하반전", variable=self.crop_flip_var).pack(side="left", padx=10)

        inp.columnconfigure(1, weight=1)

        btn = ttk.Frame(tab)
        btn.pack(fill="x", padx=10, pady=3)
        ttk.Button(btn, text="Crop + JSON 변환", command=self._run_crop).pack(side="left")
        ttk.Button(btn, text="렌더링 범위 측정", command=self._run_measure_ranges).pack(side="left", padx=5)
        self.crop_progress = ttk.Progressbar(btn, length=250, maximum=100)
        self.crop_progress.pack(side="right", padx=5)

        self.crop_log = self._make_log(tab)

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
                if SKLEARN and range_means:
                    sample = pixels[::50]
                    pid_counts = Counter(match_center(px) for px in sample)
                    sig = {k for k, v in pid_counts.items() if v > len(sample) * 0.02}
                    k = max(2, min(len(sig), 8))
                    km = KMeans(n_clusters=k, random_state=42, n_init=5, max_iter=30)
                    km.fit(pixels)
                    color_map = {}
                    used = set()
                    for ci in range(k):
                        pid = match_center(km.cluster_centers_[ci])
                        if pid in used:
                            for alt in sorted(range_means.keys(),
                                              key=lambda p: np.sqrt(np.sum((km.cluster_centers_[ci] - range_means[p]) ** 2))):
                                if alt not in used: pid = alt; break
                        color_map[ci] = pid; used.add(pid)

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

    def _build_tab_style(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="4. 스타일 편집")

        top = ttk.Frame(tab)
        top.pack(fill="x", padx=10, pady=5)

        ttk.Label(top, text="JSON A:").pack(side="left")
        self.style_a_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.style_a_var, width=30).pack(side="left", padx=3)
        ttk.Button(top, text="찾기", command=lambda: self._browse_file(self.style_a_var, [("JSON", "*.json")])).pack(side="left")

        ttk.Label(top, text="JSON B:").pack(side="left", padx=(10, 0))
        self.style_b_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.style_b_var, width=30).pack(side="left", padx=3)
        ttk.Button(top, text="찾기", command=lambda: self._browse_file(self.style_b_var, [("JSON", "*.json")])).pack(side="left")

        btn = ttk.Frame(tab)
        btn.pack(fill="x", padx=10, pady=3)
        ttk.Button(btn, text="모티프 추출", command=lambda: self._style_op("motif")).pack(side="left")
        ttk.Button(btn, text="A→B 스타일 적용", command=lambda: self._style_op("restyle")).pack(side="left", padx=3)
        ttk.Button(btn, text="A+B 합성", command=lambda: self._style_op("combine")).pack(side="left", padx=3)
        ttk.Button(btn, text="JSON 저장", command=self._style_save).pack(side="left", padx=3)

        # 미리보기
        self.style_canvas = tk.Canvas(tab, bg="#2d2d2d", height=400)
        self.style_canvas.pack(fill="both", expand=True, padx=10, pady=5)

        self._style_result = None

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

    def _style_op(self, op):
        try:
            palette = load_palette()
            if op == "motif":
                grid_a, _ = self._load_grid(self.style_a_var.get())
                motif, bg = self._extract_motif(grid_a)
                self._style_result = motif
            elif op == "restyle":
                grid_a, _ = self._load_grid(self.style_a_var.get())
                grid_b, _ = self._load_grid(self.style_b_var.get())
                motif_b, bg_b = self._extract_motif(grid_b)
                colors_a = sorted(set(c for row in grid_a for c in row if c != 0))
                colors_b = sorted(set(c for row in motif_b for c in row if c != 0))
                remap = {c_b: colors_a[i % len(colors_a)] for i, c_b in enumerate(colors_b)}
                remap[0] = 0
                bg_a = Counter(c for row in grid_a for c in row).most_common(1)[0][0]
                self._style_result = [[bg_a if c == 0 else remap.get(c, c) for c in row] for row in motif_b]
            elif op == "combine":
                grid_a, _ = self._load_grid(self.style_a_var.get())
                grid_b, _ = self._load_grid(self.style_b_var.get())
                motif_a, _ = self._extract_motif(grid_a)
                motif_b, _ = self._extract_motif(grid_b)
                h, w = len(grid_a), len(grid_a[0])
                bg = Counter(c for row in grid_a for c in row).most_common(1)[0][0]
                combined = [[0] * w for _ in range(h)]
                for y in range(h):
                    for x in range(w):
                        a = motif_a[y][x] if y < len(motif_a) and x < len(motif_a[0]) else 0
                        b = motif_b[y][x] if y < len(motif_b) and x < len(motif_b[0]) else 0
                        combined[y][x] = a if x < w // 2 and a != 0 else (b if b != 0 else (a if a != 0 else bg))
                self._style_result = combined

            if self._style_result:
                img = self._render_grid(self._style_result, cell=8)
                self._photo = ImageTk.PhotoImage(img)
                cw = self.style_canvas.winfo_width() or 500
                ch = self.style_canvas.winfo_height() or 400
                self.style_canvas.delete("all")
                self.style_canvas.create_image(cw // 2, ch // 2, image=self._photo, anchor="center")

        except Exception as e:
            messagebox.showerror("오류", str(e))

    def _style_save(self):
        if not self._style_result:
            messagebox.showwarning("경고", "먼저 스타일 작업을 실행하세요")
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path: return

        grid = self._style_result
        fm = "\n".join(" ".join(f"{c:02d}" for c in row) for row in grid)
        counts = Counter(c for row in grid for c in row if c != 0)
        nc = len(counts); tot = sum(counts.values())
        cd = " ".join(f"c{cid}:{cnt}" for cid, cnt in sorted(counts.items(), key=lambda x: -x[1]))

        lj = {"level_number": 1, "level_id": "L0001", "pkg": 1, "pos": 1, "chapter": 1,
              "purpose_type": "Normal", "target_cr": 0, "target_attempts": 0.0,
              "num_colors": nc, "color_distribution": cd,
              "field_rows": len(grid), "field_columns": len(grid[0]), "total_cells": tot,
              "rail_capacity": 5, "rail_capacity_tier": "S", "queue_columns": min(nc, 5), "queue_rows": 3,
              "gimmick_hidden": 0, "gimmick_chain": 0, "gimmick_pinata": 0, "gimmick_spawner_t": 0,
              "gimmick_pin": 0, "gimmick_lock_key": 0, "gimmick_surprise": 0, "gimmick_wall": 0,
              "gimmick_spawner_o": 0, "gimmick_pinata_box": 0, "gimmick_ice": 0,
              "gimmick_frozen_dart": 0, "gimmick_curtain": 0, "total_darts": tot,
              "dart_capacity_range": ",".join([str(tot // max(nc, 1))] * min(nc, 5)),
              "emotion_curve": "", "designer_note": f"[FieldMap]\n{fm}",
              "pixel_art_source": "style_editor"}

        with open(path, "w", encoding="utf-8") as f:
            json.dump(lj, f, indent=2, ensure_ascii=False)
        messagebox.showinfo("저장", f"저장 완료: {path}")

    # ══════════════════════════════════════════════════════════
    #  Tab 5: AI 변형 (SD)
    # ══════════════════════════════════════════════════════════

    def _build_tab_ai(self):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text="5. AI 변형 (SD)")

        info = ttk.LabelFrame(tab, text="Stable Diffusion", padding=10)
        info.pack(fill="x", padx=10, pady=10)

        self.sd_status_var = tk.StringVar(value="미설치 — '설치' 버튼을 눌러주세요")
        ttk.Label(info, textvariable=self.sd_status_var, font=("", 11)).pack()

        btn = ttk.Frame(info)
        btn.pack(pady=10)
        ttk.Button(btn, text="SD 설치/확인", command=self._check_sd).pack(side="left", padx=5)
        ttk.Button(btn, text="이미지 생성", command=self._run_sd).pack(side="left", padx=5)

        ttk.Label(info, text="프롬프트:").pack(anchor="w", padx=5)
        self.sd_prompt_var = tk.StringVar(value="a cute cat pixel art, 50x50 grid")
        ttk.Entry(info, textvariable=self.sd_prompt_var, width=70).pack(fill="x", padx=5, pady=3)

        self.sd_canvas = tk.Canvas(tab, bg="#2d2d2d")
        self.sd_canvas.pack(fill="both", expand=True, padx=10, pady=5)

        self.sd_log = self._make_log(tab)

    def _check_sd(self):
        try:
            import diffusers
            self.sd_status_var.set(f"설치됨: diffusers {diffusers.__version__}")
        except ImportError:
            self.sd_status_var.set("설치 중...")
            threading.Thread(target=self._install_sd, daemon=True).start()

    def _install_sd(self):
        import subprocess
        self._log_safe(self.sd_log, "diffusers 설치 중... (첫 실행시 1회)")
        subprocess.run([sys.executable, "-m", "pip", "install", "diffusers", "transformers", "accelerate"],
                       capture_output=True)
        self.root.after(0, lambda: self.sd_status_var.set("설치 완료 — 모델 다운로드는 첫 생성시"))
        self._log_safe(self.sd_log, "설치 완료")

    def _run_sd(self):
        if self._running: return
        self._running = True
        threading.Thread(target=self._do_sd, daemon=True).start()

    def _do_sd(self):
        try:
            self._log_safe(self.sd_log, "SD 모델 로드 중...")
            from diffusers import AutoPipelineForText2Image
            import torch
            pipe = AutoPipelineForText2Image.from_pretrained(
                "stabilityai/sdxl-turbo", torch_dtype=torch.float32)
            self._log_safe(self.sd_log, "생성 중...")
            result = pipe(self.sd_prompt_var.get(), num_inference_steps=4, guidance_scale=0.0)
            img = result.images[0].resize((400, 400))
            img.save(str(DATA_DIR / "sd_output.png"))

            self._sd_photo = ImageTk.PhotoImage(img)
            cw = self.sd_canvas.winfo_width() or 500
            ch = self.sd_canvas.winfo_height() or 400
            self.root.after(0, lambda: (
                self.sd_canvas.delete("all"),
                self.sd_canvas.create_image(cw // 2, ch // 2, image=self._sd_photo, anchor="center")
            ))
            self._log_safe(self.sd_log, "완료! 이미지를 PNG→JSON 탭에서 변환하세요")

        except Exception as e:
            self._log_safe(self.sd_log, f"ERROR: {e}")
        finally:
            self._running = False


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    app = LevelDesignStudio(root)
    root.mainloop()


if __name__ == "__main__":
    main()
