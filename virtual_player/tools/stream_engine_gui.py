"""
Stream Engine GUI — AI Tester용 패턴 DB 구축 (GUI)
====================================================
"""
import json, threading, sys, time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import numpy as np
from PIL import Image, ImageTk

YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    pass

SCRIPT_DIR = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from tester.pipeline.stream_processor import StreamEngine, StreamDB, FrameProcessor, load_game_profile
except ImportError:
    StreamEngine = None


class StreamEngineGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Stream Engine — Pattern DB Builder")
        self.root.geometry("750x550")
        self._running = False
        self._build_ui()

    def _build_ui(self):
        inp = ttk.LabelFrame(self.root, text="입력", padding=8)
        inp.pack(fill="x", padx=10, pady=5)

        ttk.Label(inp, text="이미지 폴더:").grid(row=0, column=0, sticky="w")
        self.input_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.input_var, width=55).grid(row=0, column=1, padx=5)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_dir(self.input_var)).grid(row=0, column=2)

        ttk.Label(inp, text="YOLO 모델:").grid(row=1, column=0, sticky="w", pady=2)
        self.model_var = tk.StringVar()
        ttk.Entry(inp, textvariable=self.model_var, width=55).grid(row=1, column=1, padx=5, pady=2)
        ttk.Button(inp, text="찾기", command=lambda: self._browse_file(self.model_var)).grid(row=1, column=2)

        ttk.Label(inp, text="출력 DB:").grid(row=2, column=0, sticky="w")
        self.db_var = tk.StringVar(value="stream_patterns.db")
        ttk.Entry(inp, textvariable=self.db_var, width=55).grid(row=2, column=1, padx=5)
        ttk.Button(inp, text="찾기", command=self._browse_db).grid(row=2, column=2)

        ttk.Label(inp, text="게임 ID:").grid(row=3, column=0, sticky="w", pady=2)
        self.game_var = tk.StringVar(value="pixelflow")
        ttk.Entry(inp, textvariable=self.game_var, width=20).grid(row=3, column=1, sticky="w", padx=5, pady=2)
        inp.columnconfigure(1, weight=1)

        opt = ttk.LabelFrame(self.root, text="옵션", padding=5)
        opt.pack(fill="x", padx=10, pady=2)

        self.delete_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="처리 후 원본 삭제", variable=self.delete_var).pack(side="left")

        btn = ttk.Frame(self.root)
        btn.pack(fill="x", padx=10, pady=5)
        self.run_btn = ttk.Button(btn, text="처리 시작", command=self._run)
        self.run_btn.pack(side="left")
        self.stop_btn = ttk.Button(btn, text="중지", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=5)
        self.progress = ttk.Progressbar(btn, length=250, maximum=100)
        self.progress.pack(side="right", padx=5)
        self.status_var = tk.StringVar(value="대기 중")
        ttk.Label(btn, textvariable=self.status_var).pack(side="right")

        log_frame = ttk.LabelFrame(self.root, text="로그", padding=3)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        self.log_text = tk.Text(log_frame, font=("Consolas", 9), state="disabled",
                                bg="#1e1e1e", fg="#cccccc")
        self.log_text.pack(fill="both", expand=True)

    def _browse_dir(self, var):
        d = filedialog.askdirectory()
        if d: var.set(d)

    def _browse_file(self, var):
        f = filedialog.askopenfilename(filetypes=[("PyTorch", "*.pt"), ("All", "*.*")])
        if f: var.set(f)

    def _browse_db(self):
        f = filedialog.asksaveasfilename(defaultextension=".db", filetypes=[("SQLite", "*.db")])
        if f: self.db_var.set(f)

    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _stop(self):
        self._running = False

    def _run(self):
        if self._running: return
        if not self.input_var.get():
            messagebox.showerror("오류", "이미지 폴더를 지정해주세요")
            return
        self._running = True
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        threading.Thread(target=self._do_process, daemon=True).start()

    def _do_process(self):
        try:
            input_dir = Path(self.input_var.get())
            game_id = self.game_var.get()
            db_path = self.db_var.get()
            model_path = self.model_var.get() or None
            delete = self.delete_var.get()

            files = sorted(input_dir.glob("*.png"))
            if not files:
                files = sorted(input_dir.glob("*.jpg"))
            total = len(files)
            self.root.after(0, self._log, f"파일: {total}개")

            # DB
            db = StreamDB(db_path)

            # YOLO
            yolo = None
            if model_path and YOLO_AVAILABLE and Path(model_path).exists():
                yolo = YOLO(model_path)
                self.root.after(0, self._log, f"YOLO 로드됨")

            profile = load_game_profile(game_id) if StreamEngine else None
            processor = FrameProcessor(game_id, profile, yolo) if FrameProcessor else None

            stages = 0
            start = time.time()

            for i, fp in enumerate(files):
                if not self._running:
                    self.root.after(0, self._log, "중지됨")
                    break

                if processor:
                    result = processor.process(fp)
                    if result.get("is_stage_start"):
                        stages += 1

                    db.record_frame(game_id, fp.name, result.get("screen_type", "unknown"),
                                    result.get("state_hash"), result.get("is_stage_start", False),
                                    f"{result.get('grid_rows',0)}x{result.get('grid_cols',0)}",
                                    result.get("color_dist", ""), result.get("fieldmap", ""),
                                    result.get("delta", 0))
                else:
                    # processor 없으면 해시만
                    arr = np.array(Image.open(fp).convert("L").resize((16,16)))
                    h = "".join("1" if b else "0" for b in (arr > arr.mean()).flatten())
                    db.record_frame(game_id, fp.name, "unknown", h, False, "", "", "", 0)

                if delete:
                    fp.unlink()

                if (i+1) % 100 == 0 or i == total - 1:
                    elapsed = time.time() - start
                    fps = (i+1) / max(elapsed, 0.1)
                    pct = (i+1) / total * 100
                    self.root.after(0, lambda p=pct: self.progress.configure(value=p))
                    self.root.after(0, lambda: self.status_var.set(
                        f"{i+1}/{total} ({fps:.1f}fps) stages={stages}"))

            db.close()
            elapsed = time.time() - start
            self.root.after(0, self._log,
                f"\n완료: {total}장 처리, {stages} stages, {elapsed:.1f}s\nDB: {db_path}")

        except Exception as e:
            self.root.after(0, self._log, f"ERROR: {e}")
        finally:
            self._running = False
            self.root.after(0, lambda: self.run_btn.configure(state="normal"))
            self.root.after(0, lambda: self.stop_btn.configure(state="disabled"))


def main():
    root = tk.Tk()
    app = StreamEngineGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
