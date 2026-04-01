"""
Stage Extractor GUI — 스테이지 추출 + Crop + JSON (GUI 버전)
=============================================================
다른 디바이스에서도 바로 실행 가능한 독립형 GUI.
"""
import json, shutil, threading, sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from collections import Counter

import numpy as np
from PIL import Image, ImageTk

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


def load_palette(game_id="balloonflow"):
    for p in [SCRIPT_DIR / "game_profiles.json",
              Path(__file__).resolve().parent / "game_profiles.json"]:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f).get(game_id, {}).get("color_palette_28", [])
    return []


class StageExtractorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Stage Extractor")
        self.root.geometry("850x700")
        self.root.minsize(750, 600)
        self._running = False
        self._results = []
        self._build_ui()

    def _build_ui(self):
        # ── 입력 설정 ──
        inp = ttk.LabelFrame(self.root, text="입력", padding=8)
        inp.pack(fill="x", padx=10, pady=5)

        ttk.Label(inp, text="이미지 폴더:").grid(row=0, column=0, sticky="w")
        self.input_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.input_var, width=55).grid(row=0, column=1, padx=5)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_dir(self.input_var)).grid(row=0, column=2)

        ttk.Label(inp, text="session_log:").grid(row=1, column=0, sticky="w", pady=2)
        self.log_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.log_var, width=55).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_file(self.log_var, [("JSONL", "*.jsonl"), ("JSON", "*.json")])).grid(row=1, column=2)

        ttk.Label(inp, text="YOLO 모델:").grid(row=2, column=0, sticky="w")
        self.model_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.model_var, width=55).grid(row=2, column=1, padx=5)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_file(self.model_var, [("PyTorch", "*.pt")])).grid(row=2, column=2)

        ttk.Label(inp, text="출력 폴더:").grid(row=3, column=0, sticky="w", pady=2)
        self.output_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.output_var, width=55).grid(row=3, column=1, padx=5, pady=2)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_dir(self.output_var)).grid(row=3, column=2)
        inp.columnconfigure(1, weight=1)

        # ── 옵션 ──
        opt = ttk.LabelFrame(self.root, text="옵션", padding=8)
        opt.pack(fill="x", padx=10, pady=2)

        ttk.Label(opt, text="그리드:").pack(side="left")
        self.grid_var = tk.IntVar(value=50)
        ttk.Spinbox(opt, from_=10, to=50, textvariable=self.grid_var, width=4).pack(side="left", padx=2)

        ttk.Label(opt, text="시작 레벨:").pack(side="left", padx=(10, 0))
        self.start_var = tk.IntVar(value=51)
        ttk.Spinbox(opt, from_=1, to=9999, textvariable=self.start_var, width=5).pack(side="left", padx=2)

        ttk.Label(opt, text="보드 좌표(x,y,w,h):").pack(side="left", padx=(10, 0))
        self.board_var = tk.StringVar(value="155,333,735,663")
        ttk.Entry(opt, textvariable=self.board_var, width=18).pack(side="left", padx=2)

        self.flip_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="상하반전", variable=self.flip_var).pack(side="left", padx=10)

        # ── 실행 ──
        btn = ttk.Frame(self.root)
        btn.pack(fill="x", padx=10, pady=5)

        self.run_btn = ttk.Button(btn, text="1. 추출 시작", command=self._run_extract)
        self.run_btn.pack(side="left")

        self.crop_btn = ttk.Button(btn, text="2. Crop + JSON", command=self._run_crop)
        self.crop_btn.pack(side="left", padx=5)

        self.open_btn = ttk.Button(btn, text="출력 폴더 열기", command=self._open_output, state="disabled")
        self.open_btn.pack(side="left", padx=5)

        self.progress = ttk.Progressbar(btn, length=200, maximum=100)
        self.progress.pack(side="right", padx=5)

        self.status_var = tk.StringVar(value="대기 중")
        ttk.Label(btn, textvariable=self.status_var).pack(side="right", padx=5)

        # ── 로그 + 미리보기 ──
        bottom = ttk.PanedWindow(self.root, orient="horizontal")
        bottom.pack(fill="both", expand=True, padx=10, pady=5)

        log_frame = ttk.LabelFrame(bottom, text="로그", padding=3)
        self.log_text = tk.Text(log_frame, width=45, height=18, font=("Consolas", 9),
                                state="disabled", bg="#1e1e1e", fg="#cccccc")
        self.log_text.pack(fill="both", expand=True)
        bottom.add(log_frame, weight=3)

        prev_frame = ttk.LabelFrame(bottom, text="미리보기", padding=3)
        self.preview = tk.Canvas(prev_frame, bg="#2d2d2d", width=250)
        self.preview.pack(fill="both", expand=True)
        self.level_list = tk.Listbox(prev_frame, height=6, font=("Consolas", 9))
        self.level_list.pack(fill="x", pady=2)
        self.level_list.bind("<<ListboxSelect>>", self._on_select)
        bottom.add(prev_frame, weight=2)

    def _browse_dir(self, var):
        d = filedialog.askdirectory()
        if d: var.set(d)

    def _browse_file(self, var, ftypes):
        f = filedialog.askopenfilename(filetypes=ftypes + [("All", "*.*")])
        if f: var.set(f)

    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _log_safe(self, msg):
        self.root.after(0, self._log, msg)

    def _open_output(self):
        out = self.output_var.get()
        if out and Path(out).exists():
            import os; os.startfile(out)

    def _run_extract(self):
        if self._running: return
        for var, name in [(self.input_var, "이미지 폴더"), (self.log_var, "session_log"),
                          (self.model_var, "YOLO 모델"), (self.output_var, "출력 폴더")]:
            if not var.get().strip():
                messagebox.showerror("오류", f"{name}을 지정해주세요")
                return
        self._running = True
        self.run_btn.configure(state="disabled")
        threading.Thread(target=self._do_extract, daemon=True).start()

    def _do_extract(self):
        try:
            data_dir = Path(self.input_var.get())
            log_path = Path(self.log_var.get())
            out_dir = Path(self.output_var.get())
            out_dir.mkdir(parents=True, exist_ok=True)

            self._log_safe("이벤트 로드 중...")
            events = []
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    e = json.loads(line.strip())
                    if e.get("event") != "episode_start":
                        events.append(e)
            self._log_safe(f"Events: {len(events)}")

            targets = []
            for i, evt in enumerate(events):
                d = evt.get("delta_from_prev")
                if d and d > 0.5:
                    af = evt.get("after_file", "")
                    if af and (data_dir / af).exists():
                        targets.append({"idx": i, "file": af})
            self._log_safe(f"Delta 후보: {len(targets)}")

            model = YOLO(self.model_var.get())
            self._log_safe(f"YOLO 분류 시작...")

            stage_starts = []
            total = len(targets)
            for i in range(0, total, 16):
                batch = targets[i:i+16]
                paths = [str(data_dir / t["file"]) for t in batch]
                for t, pred in zip(batch, model.predict(paths, verbose=False, stream=True)):
                    if pred.probs and model.names[int(pred.probs.top1)] == "stage_start":
                        stage_starts.append(t)
                done = min(i+16, total)
                pct = done / total * 100
                self.root.after(0, lambda p=pct: self.progress.configure(value=p))
                if done % 200 < 16:
                    self._log_safe(f"  {done}/{total} → {len(stage_starts)} stages")

            self._log_safe(f"Stage starts: {len(stage_starts)}")

            # 중복 제거
            unique, seen = [], []
            for s in stage_starts:
                fp = data_dir / s["file"]
                arr = np.array(Image.open(fp).convert("L").resize((16,16)))
                h = "".join("1" if b else "0" for b in (arr > arr.mean()).flatten())
                if not any(sum(a!=b for a,b in zip(h,sh)) < 20 for sh in seen):
                    unique.append(s); seen.append(h)

            self._log_safe(f"Unique: {len(unique)}")

            entries = []
            for i, s in enumerate(unique):
                dst = f"stage_{i+1:03d}.png"
                shutil.copy2(data_dir / s["file"], out_dir / dst)
                entries.append({"stage": i+1, "file": dst, "source": s["file"]})

            with open(out_dir / "index.json", "w", encoding="utf-8") as f:
                json.dump({"total": len(entries), "stages": entries}, f, indent=2, ensure_ascii=False)

            self._results = [(out_dir / e["file"], e) for e in entries]
            self._log_safe(f"\n완료: {len(unique)}개 → {out_dir}")

            def update():
                self.open_btn.configure(state="normal")
                self.level_list.delete(0, "end")
                for e in entries:
                    self.level_list.insert("end", f"Stage {e['stage']:03d}")
            self.root.after(0, update)

        except Exception as e:
            self._log_safe(f"ERROR: {e}")
            import traceback
            self._log_safe(traceback.format_exc())
        finally:
            self._running = False
            self.root.after(0, lambda: self.run_btn.configure(state="normal"))

    def _run_crop(self):
        out_dir = Path(self.output_var.get())
        if not (out_dir / "index.json").exists():
            messagebox.showwarning("경고", "먼저 '추출 시작'을 실행하세요")
            return

        self._running = True
        self.crop_btn.configure(state="disabled")
        threading.Thread(target=self._do_crop, daemon=True).start()

    def _do_crop(self):
        try:
            out_dir = Path(self.output_var.get())
            board_dir = out_dir / "boards"
            json_dir = out_dir / "json"
            board_dir.mkdir(exist_ok=True)
            json_dir.mkdir(exist_ok=True)

            index = json.loads((out_dir / "index.json").read_text(encoding="utf-8"))
            palette = load_palette()
            pal_arr = np.array([p["rgb"] for p in palette], dtype=np.float32) if palette else None
            pal_ids = [p["id"] for p in palette] if palette else []

            board_str = self.board_var.get().split(",")
            BOARD = tuple(int(x.strip()) for x in board_str)
            GRID = self.grid_var.get()
            FLIP = self.flip_var.get()
            START = self.start_var.get()

            self._log_safe(f"Crop + JSON: {len(index['stages'])}장, grid={GRID}")

            for entry in index["stages"]:
                fp = out_dir / entry["file"]
                img = np.array(Image.open(fp).convert("RGB"))
                bx, by, bw, bh = BOARD
                board = img[by:by+bh, bx:bx+bw]
                Image.fromarray(board).save(str(board_dir / entry["file"]))

                # K-Means
                km, color_map = None, None
                if SKLEARN and pal_arr is not None:
                    board_flat = board.reshape(-1, 3).astype(np.float32)
                    dists = np.sqrt(np.sum((board_flat[:, None, :] - pal_arr[None, :, :]) ** 2, axis=2))
                    nearest = np.argmin(dists, axis=1)
                    id_counts = Counter(pal_ids[n] for n in nearest)
                    sig = {k: v for k, v in id_counts.items() if v > len(nearest) * 0.01}
                    k = max(2, min(len(sig), 8))
                    km = KMeans(n_clusters=k, random_state=42, n_init=5, max_iter=30)
                    km.fit(board[:,:,::-1].reshape(-1, 3).astype(np.float32))
                    color_map = {}
                    for ci, center in enumerate(km.cluster_centers_):
                        rgb = np.array([center[2], center[1], center[0]], dtype=np.float32)
                        bi = int(np.argmin(np.sqrt(np.sum((pal_arr - rgb) ** 2, axis=1))))
                        color_map[ci] = pal_ids[bi]

                ch_sz, cw_sz = bh / GRID, bw / GRID
                fm_rows, color_counts = [], {}
                for r in range(GRID):
                    tokens = []
                    for c in range(GRID):
                        cy = int((r + 0.5) * ch_sz)
                        cx = int((c + 0.5) * cw_sz)
                        m = max(1, int(min(ch_sz, cw_sz) * 0.15))
                        cell = board[max(0, cy-m):min(bh, cy+m), max(0, cx-m):min(bw, cx+m)]
                        if km and color_map:
                            avg = cell[:,:,::-1].mean(axis=(0,1)).reshape(1,-1).astype(np.float32)
                            pid = color_map[km.predict(avg)[0]]
                        elif pal_arr is not None:
                            avg = cell.mean(axis=(0, 1))
                            rgb = np.array([avg[0], avg[1], avg[2]], dtype=np.float32)
                            bi = int(np.argmin(np.sqrt(np.sum((pal_arr - rgb) ** 2, axis=1))))
                            pid = pal_ids[bi]
                        else:
                            pid = 0
                        tokens.append(f"{pid:02d}")
                        color_counts[pid] = color_counts.get(pid, 0) + 1
                    fm_rows.append(tokens)

                if FLIP:
                    fm_rows.reverse()

                fieldmap = "\n".join(" ".join(r) for r in fm_rows)
                total = sum(color_counts.values())
                nc = len(color_counts)
                cd = " ".join(f"c{cid}:{cnt}" for cid, cnt in sorted(color_counts.items(), key=lambda x: -x[1]))
                lv = START + entry["stage"] - 1

                lj = {
                    "level_number": lv, "level_id": f"L{lv:04d}",
                    "pkg": (lv-1)//10+1, "pos": (lv-1)%10+1, "chapter": (lv-1)//50+1,
                    "purpose_type": "Normal", "target_cr": 0, "target_attempts": 0.0,
                    "num_colors": nc, "color_distribution": cd,
                    "field_rows": GRID, "field_columns": GRID, "total_cells": total,
                    "rail_capacity": 5, "rail_capacity_tier": "S",
                    "queue_columns": min(nc, 5), "queue_rows": 3,
                    "gimmick_hidden":0,"gimmick_chain":0,"gimmick_pinata":0,
                    "gimmick_spawner_t":0,"gimmick_pin":0,"gimmick_lock_key":0,
                    "gimmick_surprise":0,"gimmick_wall":0,"gimmick_spawner_o":0,
                    "gimmick_pinata_box":0,"gimmick_ice":0,"gimmick_frozen_dart":0,
                    "gimmick_curtain":0,
                    "total_darts": total,
                    "dart_capacity_range": ",".join([str(total//max(nc,1))]*min(nc,5)),
                    "emotion_curve": "", "designer_note": f"[FieldMap]\n{fieldmap}",
                    "pixel_art_source": entry.get("source", entry["file"]),
                }
                with open(json_dir / f"level_{lv:03d}.json", "w", encoding="utf-8") as f:
                    json.dump(lj, f, indent=2, ensure_ascii=False)

                if entry["stage"] % 50 == 0:
                    self._log_safe(f"  {entry['stage']}/{len(index['stages'])}")

            self._log_safe(f"\nCrop+JSON 완료: boards={board_dir} json={json_dir}")

        except Exception as e:
            self._log_safe(f"ERROR: {e}")
        finally:
            self._running = False
            self.root.after(0, lambda: self.crop_btn.configure(state="normal"))

    def _on_select(self, event):
        sel = self.level_list.curselection()
        if not sel or not self._results: return
        idx = sel[0]
        if idx >= len(self._results): return
        img_path, entry = self._results[idx]
        if not img_path.exists(): return
        img = Image.open(img_path)
        cw = self.preview.winfo_width() or 250
        ch = self.preview.winfo_height() or 400
        ratio = min(cw / img.width, ch / img.height)
        img = img.resize((max(1, int(img.width * ratio)), max(1, int(img.height * ratio))))
        self._photo = ImageTk.PhotoImage(img)
        self.preview.delete("all")
        self.preview.create_image(cw // 2, ch // 2, image=self._photo, anchor="center")


def main():
    root = tk.Tk()
    app = StageExtractorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
