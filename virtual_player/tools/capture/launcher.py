"""
Genre Capture Launcher — 통합 GUI
====================================
장르 선택 → 장르별 설정 패널 → 캡처 시작/종료.
기존 ClickCapture v3 GUI와 동일한 다크 테마.

Usage:
    python -m virtual_player.tools.capture.launcher
    또는 빌드 후 exe 실행
"""

import ctypes
import json
import os
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional, Tuple

from .base import (
    ADBConnection,
    BaseCaptureEngine,
    EmulatorRegistry,
    SessionManager,
    TapMonitor,
)
from .theme import SunoTheme
from .puzzle_capture import PuzzleCaptureEngine
from .idle_capture import IdleCaptureEngine
from .action_capture import ActionCaptureEngine


# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────

def _config_path() -> Path:
    # EXE: exe 옆에 저장 / 개발: 소스 옆에 저장
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / "capture_config.json"
    return Path(__file__).parent / "capture_config.json"


def load_config() -> dict:
    defaults = {
        "emulator_type": "BlueStacks",
        "adb_path": "",
        "serial": "auto",
        "output_folder": str(Path.home() / "Desktop" / "ClickCaptures"),
        "genre": "puzzle",
        "cooldown": 0.3,
        "episode_timeout": 30,
        "swipe_threshold": 50,
        "long_press_ms": 600,
        # Puzzle
        "puzzle_before_after": True,
        "puzzle_after_delay_ms": 500,
        "puzzle_board_roi": "",
        # Idle
        "idle_after_delay_ms": 1000,
        "idle_auto_snapshot_sec": 0,
        "idle_value_regions": "",
        "idle_mask_regions": "",
        # Action
        "action_classify_mode": "fingerprint",
        "action_after_delay_ms": 800,
        "action_yolo_path": "",
        "action_fingerprint_db": "",
        "action_learning_mode": False,
    }
    cfg_path = _config_path()
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_config(cfg: dict):
    try:
        with open(_config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _parse_roi_string(s: str) -> Optional[Tuple[int, int, int, int]]:
    """'100,200,300,400' → (100, 200, 300, 400)"""
    if not s.strip():
        return None
    try:
        parts = [int(x.strip()) for x in s.split(",")]
        if len(parts) == 4:
            return tuple(parts)
    except (ValueError, TypeError):
        pass
    return None


def _parse_region_dict(s: str) -> dict:
    """
    'gold=100,50,200,30;diamond=100,90,200,30'
    → {'gold': (100,50,200,30), 'diamond': (100,90,200,30)}
    """
    result = {}
    if not s.strip():
        return result
    for item in s.split(";"):
        item = item.strip()
        if "=" not in item:
            continue
        name, coords = item.split("=", 1)
        roi = _parse_roi_string(coords)
        if roi:
            result[name.strip()] = roi
    return result


def _parse_region_list(s: str) -> list:
    """'100,200,300,400;500,600,200,200' → [(100,200,300,400), ...]"""
    result = []
    if not s.strip():
        return result
    for item in s.split(";"):
        roi = _parse_roi_string(item)
        if roi:
            result.append(roi)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# GUI App
# ═══════════════════════════════════════════════════════════════════════════════

class GenreCaptureApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Genre Capture v1")
        self.root.geometry("780x720")
        self.root.resizable(True, True)
        self.root.minsize(680, 600)

        SunoTheme.apply(root)

        self.cfg = load_config()
        self._running = False
        self._monitor: Optional[TapMonitor] = None
        self._engine: Optional[BaseCaptureEngine] = None
        self._adb: Optional[ADBConnection] = None
        self._session: Optional[SessionManager] = None
        self._capture_thread: Optional[threading.Thread] = None

        self._build_ui()
        self._apply_config()

    # ── UI Construction ──

    def _build_ui(self):
        T = SunoTheme
        pad = 16

        # ── Header ──
        header = tk.Frame(self.root, bg=T.CARD, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        accent_bar = tk.Frame(header, bg=T.ACCENT, width=3)
        accent_bar.pack(side="left", fill="y", padx=(pad, 0), pady=12)

        title_frame = tk.Frame(header, bg=T.CARD)
        title_frame.pack(side="left", padx=(8, 0))
        tk.Label(title_frame, text="Genre Capture",
                 font=("Segoe UI", 13, "bold"), fg=T.TEXT, bg=T.CARD).pack(side="left")
        tk.Label(title_frame, text="v1",
                 font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD).pack(side="left", padx=(6, 0), pady=(4, 0))

        self.var_status_dot = tk.StringVar(value="")
        self.lbl_status_dot = tk.Label(
            header, textvariable=self.var_status_dot,
            font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD)
        self.lbl_status_dot.pack(side="right", padx=(0, pad))

        tk.Frame(self.root, bg=T.BORDER, height=1).pack(fill="x")

        main = tk.Frame(self.root, bg=T.BG)
        main.pack(fill="both", expand=True, padx=pad, pady=6)

        # ── Emulator + Device ──
        emu_section = tk.Frame(main, bg=T.CARD, highlightbackground=T.BORDER, highlightthickness=1)
        emu_section.pack(fill="x", pady=(6, 4))
        emu_inner = tk.Frame(emu_section, bg=T.CARD)
        emu_inner.pack(fill="x", padx=12, pady=10)
        emu_inner.columnconfigure(1, weight=1)

        tk.Label(emu_inner, text="Emulator", font=T.FONT_BOLD, fg=T.TEXT, bg=T.CARD
                 ).grid(row=0, column=0, sticky="w")
        emu_frame = tk.Frame(emu_inner, bg=T.CARD)
        emu_frame.grid(row=0, column=1, padx=(12, 0), sticky="ew")

        self.var_emu = tk.StringVar(value="BlueStacks")
        installed = EmulatorRegistry.detect_installed()
        options = list(dict.fromkeys(installed + ["BlueStacks", "LDPlayer", "Custom"]))
        self.cmb_emu = ttk.Combobox(emu_frame, textvariable=self.var_emu,
                                     values=options, width=16, state="readonly")
        self.cmb_emu.pack(side="left")
        self.cmb_emu.bind("<<ComboboxSelected>>", self._on_emu_changed)

        self.lbl_emu_status = tk.Label(emu_frame, text="", font=T.FONT_SMALL, fg=T.SUCCESS, bg=T.CARD)
        self.lbl_emu_status.pack(side="left", padx=(10, 0))

        tk.Label(emu_inner, text="ADB", font=T.FONT_BOLD, fg=T.TEXT, bg=T.CARD
                 ).grid(row=1, column=0, sticky="w", pady=(6, 0))
        adb_frame = tk.Frame(emu_inner, bg=T.CARD)
        adb_frame.grid(row=1, column=1, padx=(12, 0), sticky="ew", pady=(6, 0))
        self.var_adb = tk.StringVar()
        ttk.Entry(adb_frame, textvariable=self.var_adb, width=48).pack(side="left", fill="x", expand=True)
        ttk.Button(adb_frame, text="...", width=3, command=self._browse_adb).pack(side="left", padx=(4, 0))

        tk.Label(emu_inner, text="Device", font=T.FONT_BOLD, fg=T.TEXT, bg=T.CARD
                 ).grid(row=2, column=0, sticky="w", pady=(6, 0))
        dev_frame = tk.Frame(emu_inner, bg=T.CARD)
        dev_frame.grid(row=2, column=1, padx=(12, 0), sticky="ew", pady=(6, 0))
        self.var_serial = tk.StringVar()
        self.cmb_serial = ttk.Combobox(dev_frame, textvariable=self.var_serial, width=24)
        self.cmb_serial.pack(side="left")
        ttk.Button(dev_frame, text="Scan", width=6, command=self._refresh_devices).pack(side="left", padx=(4, 0))
        ttk.Button(dev_frame, text="Test", width=6, command=self._test_adb).pack(side="left", padx=(4, 0))

        tk.Label(emu_inner, text="Output", font=T.FONT_BOLD, fg=T.TEXT, bg=T.CARD
                 ).grid(row=3, column=0, sticky="w", pady=(6, 0))
        out_frame = tk.Frame(emu_inner, bg=T.CARD)
        out_frame.grid(row=3, column=1, padx=(12, 0), sticky="ew", pady=(6, 0))
        self.var_output = tk.StringVar()
        ttk.Entry(out_frame, textvariable=self.var_output, width=48).pack(side="left", fill="x", expand=True)
        ttk.Button(out_frame, text="...", width=3, command=self._browse_output).pack(side="left", padx=(4, 0))

        # ── Genre Selection ──
        genre_section = tk.Frame(main, bg=T.CARD, highlightbackground=T.BORDER, highlightthickness=1)
        genre_section.pack(fill="x", pady=4)
        genre_inner = tk.Frame(genre_section, bg=T.CARD)
        genre_inner.pack(fill="x", padx=12, pady=10)

        tk.Label(genre_inner, text="Genre", font=T.FONT_HEADING, fg=T.TEXT, bg=T.CARD
                 ).pack(side="left")

        self.var_genre = tk.StringVar(value="puzzle")
        for genre, color in SunoTheme.GENRE_COLORS.items():
            label_map = {"puzzle": "Puzzle", "idle": "Idle", "action": "RPG / SLG"}
            rb = tk.Radiobutton(
                genre_inner, text=label_map[genre], variable=self.var_genre, value=genre,
                bg=T.CARD, fg=color, selectcolor=T.SURFACE,
                activebackground=T.CARD, activeforeground=color,
                font=T.FONT_BOLD, indicatoron=0, padx=16, pady=6,
                borderwidth=1, relief="flat",
                command=self._on_genre_changed)
            rb.pack(side="left", padx=(12, 0))

        # ── Genre-specific settings (notebook) ──
        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="x", pady=4)

        self._build_puzzle_tab()
        self._build_idle_tab()
        self._build_action_tab()

        # ── Common settings ──
        common_section = tk.Frame(main, bg=T.CARD, highlightbackground=T.BORDER, highlightthickness=1)
        common_section.pack(fill="x", pady=4)
        common_inner = tk.Frame(common_section, bg=T.CARD)
        common_inner.pack(fill="x", padx=12, pady=8)

        tk.Label(common_inner, text="Cooldown", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD).pack(side="left")
        self.var_cooldown = tk.StringVar()
        ttk.Entry(common_inner, textvariable=self.var_cooldown, width=5).pack(side="left", padx=(6, 0))
        tk.Label(common_inner, text="sec", font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD).pack(side="left", padx=(2, 16))

        tk.Label(common_inner, text="Episode timeout", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD).pack(side="left")
        self.var_episode_timeout = tk.StringVar()
        ttk.Entry(common_inner, textvariable=self.var_episode_timeout, width=5).pack(side="left", padx=(6, 0))
        tk.Label(common_inner, text="sec", font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD).pack(side="left", padx=(2, 0))

        # ── Buttons ──
        btn_frame = tk.Frame(main, bg=T.BG)
        btn_frame.pack(fill="x", pady=(8, 4))

        self.btn_start = ttk.Button(btn_frame, text="Start Capture", style="Accent.TButton", command=self._on_start)
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(btn_frame, text="Stop", style="Danger.TButton", command=self._on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=(8, 0))
        ttk.Button(btn_frame, text="Open Folder", command=self._open_folder).pack(side="left", padx=(8, 0))

        self.var_count = tk.StringVar(value="0 captures")
        tk.Label(btn_frame, textvariable=self.var_count, font=T.FONT_BOLD, fg=T.ACCENT, bg=T.BG).pack(side="right")

        # ── App Info ──
        self.var_app = tk.StringVar(value="")
        tk.Label(main, textvariable=self.var_app, font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.BG, anchor="w"
                 ).pack(fill="x", pady=(0, 2))

        # ── Log ──
        log_section = tk.Frame(main, bg=T.CARD, highlightbackground=T.BORDER, highlightthickness=1)
        log_section.pack(fill="both", expand=True, pady=(4, 6))

        log_header = tk.Frame(log_section, bg=T.CARD)
        log_header.pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(log_header, text="Log", font=T.FONT_BOLD, fg=T.TEXT_DIM, bg=T.CARD).pack(side="left")

        self.log_text = tk.Text(
            log_section, height=8, font=T.FONT_LOG,
            bg="#111113", fg=T.TEXT_DIM, insertbackground=T.TEXT, selectbackground=T.ACCENT,
            borderwidth=0, highlightthickness=0, wrap="word", state="disabled", padx=12, pady=8)
        self.log_text.pack(fill="both", expand=True, padx=1, pady=(4, 1))
        self.log_text.tag_configure("time", foreground=T.TEXT_MUTED)
        self.log_text.tag_configure("info", foreground=T.TEXT_DIM)
        self.log_text.tag_configure("success", foreground=T.SUCCESS)
        self.log_text.tag_configure("error", foreground=T.ERROR)
        self.log_text.tag_configure("accent", foreground=T.ACCENT)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_puzzle_tab(self):
        T = SunoTheme
        frame = tk.Frame(self.notebook, bg=T.CARD)
        self.notebook.add(frame, text="  Puzzle  ")
        inner = tk.Frame(frame, bg=T.CARD)
        inner.pack(fill="x", padx=12, pady=10)

        self.var_puzzle_ba = tk.BooleanVar()
        ttk.Checkbutton(inner, text="Before / After pair", variable=self.var_puzzle_ba).pack(side="left")

        tk.Label(inner, text="Delay", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD).pack(side="left", padx=(16, 0))
        self.var_puzzle_delay = tk.StringVar()
        ttk.Entry(inner, textvariable=self.var_puzzle_delay, width=5).pack(side="left", padx=(6, 0))
        tk.Label(inner, text="ms", font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD).pack(side="left", padx=(2, 16))

        tk.Label(inner, text="Board ROI", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD).pack(side="left")
        self.var_puzzle_roi = tk.StringVar()
        ttk.Entry(inner, textvariable=self.var_puzzle_roi, width=20).pack(side="left", padx=(6, 0))
        tk.Label(inner, text="x,y,w,h", font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD).pack(side="left", padx=(4, 0))

    def _build_idle_tab(self):
        T = SunoTheme
        frame = tk.Frame(self.notebook, bg=T.CARD)
        self.notebook.add(frame, text="  Idle  ")
        inner = tk.Frame(frame, bg=T.CARD)
        inner.pack(fill="x", padx=12, pady=10)

        r = 0
        inner.columnconfigure(1, weight=1)

        tk.Label(inner, text="After delay", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD
                 ).grid(row=r, column=0, sticky="w")
        delay_f = tk.Frame(inner, bg=T.CARD)
        delay_f.grid(row=r, column=1, sticky="w", padx=(8, 0))
        self.var_idle_delay = tk.StringVar()
        ttk.Entry(delay_f, textvariable=self.var_idle_delay, width=5).pack(side="left")
        tk.Label(delay_f, text="ms", font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD).pack(side="left", padx=(2, 8))

        tk.Label(delay_f, text="Auto snapshot", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD).pack(side="left")
        self.var_idle_auto = tk.StringVar()
        ttk.Entry(delay_f, textvariable=self.var_idle_auto, width=5).pack(side="left", padx=(6, 0))
        tk.Label(delay_f, text="sec (0=off)", font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD).pack(side="left", padx=(2, 0))

        r += 1
        tk.Label(inner, text="Value regions", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD
                 ).grid(row=r, column=0, sticky="w", pady=(6, 0))
        vr_f = tk.Frame(inner, bg=T.CARD)
        vr_f.grid(row=r, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))
        self.var_idle_values = tk.StringVar()
        ttk.Entry(vr_f, textvariable=self.var_idle_values, width=50).pack(side="left", fill="x", expand=True)

        r += 1
        tk.Label(inner, text="", font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD
                 ).grid(row=r, column=0, sticky="w")
        tk.Label(inner, text="name=x,y,w,h;name2=x,y,w,h  (OCR regions)",
                 font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD
                 ).grid(row=r, column=1, sticky="w", padx=(8, 0))

        r += 1
        tk.Label(inner, text="Mask regions", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD
                 ).grid(row=r, column=0, sticky="w", pady=(6, 0))
        mr_f = tk.Frame(inner, bg=T.CARD)
        mr_f.grid(row=r, column=1, sticky="ew", padx=(8, 0), pady=(6, 0))
        self.var_idle_masks = tk.StringVar()
        ttk.Entry(mr_f, textvariable=self.var_idle_masks, width=50).pack(side="left", fill="x", expand=True)

        r += 1
        tk.Label(inner, text="", font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD
                 ).grid(row=r, column=0, sticky="w")
        tk.Label(inner, text="x,y,w,h;x2,y2,w2,h2  (animation areas to exclude)",
                 font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD
                 ).grid(row=r, column=1, sticky="w", padx=(8, 0))

    def _build_action_tab(self):
        T = SunoTheme
        frame = tk.Frame(self.notebook, bg=T.CARD)
        self.notebook.add(frame, text="  RPG/SLG  ")
        inner = tk.Frame(frame, bg=T.CARD)
        inner.pack(fill="x", padx=12, pady=10)
        inner.columnconfigure(1, weight=1)

        r = 0
        tk.Label(inner, text="Classify", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD
                 ).grid(row=r, column=0, sticky="w")
        cls_f = tk.Frame(inner, bg=T.CARD)
        cls_f.grid(row=r, column=1, padx=(8, 0), sticky="w")
        self.var_action_mode = tk.StringVar()
        for mode in ["fingerprint", "yolo", "manual"]:
            ttk.Radiobutton(cls_f, text=mode.capitalize(), variable=self.var_action_mode,
                             value=mode).pack(side="left", padx=(0, 8))

        r += 1
        tk.Label(inner, text="After delay", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD
                 ).grid(row=r, column=0, sticky="w", pady=(6, 0))
        ad_f = tk.Frame(inner, bg=T.CARD)
        ad_f.grid(row=r, column=1, padx=(8, 0), sticky="w", pady=(6, 0))
        self.var_action_delay = tk.StringVar()
        ttk.Entry(ad_f, textvariable=self.var_action_delay, width=5).pack(side="left")
        tk.Label(ad_f, text="ms", font=T.FONT_SMALL, fg=T.TEXT_MUTED, bg=T.CARD).pack(side="left", padx=(2, 0))

        r += 1
        tk.Label(inner, text="YOLO model", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD
                 ).grid(row=r, column=0, sticky="w", pady=(6, 0))
        yf = tk.Frame(inner, bg=T.CARD)
        yf.grid(row=r, column=1, padx=(8, 0), sticky="ew", pady=(6, 0))
        self.var_action_yolo = tk.StringVar()
        ttk.Entry(yf, textvariable=self.var_action_yolo, width=40).pack(side="left", fill="x", expand=True)
        ttk.Button(yf, text="...", width=3, command=lambda: self._browse_file(self.var_action_yolo, "YOLO model", "*.pt")).pack(side="left", padx=(4, 0))

        r += 1
        tk.Label(inner, text="FP DB", font=T.FONT, fg=T.TEXT_DIM, bg=T.CARD
                 ).grid(row=r, column=0, sticky="w", pady=(6, 0))
        ff = tk.Frame(inner, bg=T.CARD)
        ff.grid(row=r, column=1, padx=(8, 0), sticky="ew", pady=(6, 0))
        self.var_action_fp_db = tk.StringVar()
        ttk.Entry(ff, textvariable=self.var_action_fp_db, width=40).pack(side="left", fill="x", expand=True)
        ttk.Button(ff, text="...", width=3, command=lambda: self._browse_file(self.var_action_fp_db, "Fingerprint DB", "*.json")).pack(side="left", padx=(4, 0))

        r += 1
        self.var_action_learn = tk.BooleanVar()
        ttk.Checkbutton(inner, text="Learning mode (save low-confidence fingerprints)",
                         variable=self.var_action_learn
                         ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(6, 0))

    # ── Config Apply/Save ──

    def _apply_config(self):
        self.var_emu.set(self.cfg.get("emulator_type", "BlueStacks"))
        adb = self.cfg.get("adb_path", "")
        if not adb or not Path(adb).exists():
            adb = EmulatorRegistry.find_adb(self.var_emu.get())
        if not adb or not Path(adb).exists():
            # deps 폴더에서 설치된 ADB 폴백
            from .deps import _find_adb
            adb = _find_adb() or ""
        self.var_adb.set(adb)
        self.var_serial.set(self.cfg.get("serial", "auto"))
        self.var_output.set(self.cfg.get("output_folder", ""))
        self.var_genre.set(self.cfg.get("genre", "puzzle"))
        self.var_cooldown.set(str(self.cfg.get("cooldown", 0.3)))
        self.var_episode_timeout.set(str(self.cfg.get("episode_timeout", 30)))
        # Puzzle
        self.var_puzzle_ba.set(self.cfg.get("puzzle_before_after", True))
        self.var_puzzle_delay.set(str(self.cfg.get("puzzle_after_delay_ms", 500)))
        self.var_puzzle_roi.set(self.cfg.get("puzzle_board_roi", ""))
        # Idle
        self.var_idle_delay.set(str(self.cfg.get("idle_after_delay_ms", 1000)))
        self.var_idle_auto.set(str(self.cfg.get("idle_auto_snapshot_sec", 0)))
        self.var_idle_values.set(self.cfg.get("idle_value_regions", ""))
        self.var_idle_masks.set(self.cfg.get("idle_mask_regions", ""))
        # Action
        self.var_action_mode.set(self.cfg.get("action_classify_mode", "fingerprint"))
        self.var_action_delay.set(str(self.cfg.get("action_after_delay_ms", 800)))
        self.var_action_yolo.set(self.cfg.get("action_yolo_path", ""))
        self.var_action_fp_db.set(self.cfg.get("action_fingerprint_db", ""))
        self.var_action_learn.set(self.cfg.get("action_learning_mode", False))

        self._update_emu_status()
        self._on_genre_changed()
        self.root.after(500, self._refresh_devices)

    def _save_current_config(self):
        self.cfg.update({
            "emulator_type": self.var_emu.get(),
            "adb_path": self.var_adb.get(),
            "serial": self.var_serial.get(),
            "output_folder": self.var_output.get(),
            "genre": self.var_genre.get(),
            "cooldown": float(self.var_cooldown.get() or 0.3),
            "episode_timeout": int(self.var_episode_timeout.get() or 30),
            "puzzle_before_after": self.var_puzzle_ba.get(),
            "puzzle_after_delay_ms": int(self.var_puzzle_delay.get() or 500),
            "puzzle_board_roi": self.var_puzzle_roi.get(),
            "idle_after_delay_ms": int(self.var_idle_delay.get() or 1000),
            "idle_auto_snapshot_sec": int(self.var_idle_auto.get() or 0),
            "idle_value_regions": self.var_idle_values.get(),
            "idle_mask_regions": self.var_idle_masks.get(),
            "action_classify_mode": self.var_action_mode.get(),
            "action_after_delay_ms": int(self.var_action_delay.get() or 800),
            "action_yolo_path": self.var_action_yolo.get(),
            "action_fingerprint_db": self.var_action_fp_db.get(),
            "action_learning_mode": self.var_action_learn.get(),
        })
        save_config(self.cfg)

    # ── Event Handlers ──

    def _on_genre_changed(self):
        genre = self.var_genre.get()
        tab_map = {"puzzle": 0, "idle": 1, "action": 2}
        self.notebook.select(tab_map.get(genre, 0))

        color = SunoTheme.GENRE_COLORS.get(genre, SunoTheme.ACCENT)
        self.lbl_status_dot.config(fg=color)

    def _on_emu_changed(self, event=None):
        emu = self.var_emu.get()
        if emu != "Custom":
            adb = EmulatorRegistry.find_adb(emu)
            if adb:
                self.var_adb.set(adb)
        self._update_emu_status()
        self._log(f"Emulator: {emu}", tag="accent")
        self.root.after(300, self._refresh_devices)

    def _update_emu_status(self):
        adb = self.var_adb.get()
        if adb and Path(adb).exists():
            self.lbl_emu_status.config(text="ADB found", fg=SunoTheme.SUCCESS)
        else:
            self.lbl_emu_status.config(text="ADB not found", fg=SunoTheme.ERROR)

    def _browse_adb(self):
        path = filedialog.askopenfilename(title="Select ADB", filetypes=[("EXE", "*.exe"), ("All", "*.*")])
        if path:
            self.var_adb.set(path)
            self._update_emu_status()

    def _browse_output(self):
        folder = filedialog.askdirectory(title="Output folder")
        if folder:
            self.var_output.set(folder)

    def _browse_file(self, var: tk.StringVar, title: str, ftype: str):
        path = filedialog.askopenfilename(title=title, filetypes=[(ftype, ftype), ("All", "*.*")])
        if path:
            var.set(path)

    def _open_folder(self):
        f = self.var_output.get()
        if f and Path(f).exists():
            os.startfile(f)

    def _refresh_devices(self):
        adb = self.var_adb.get()
        if not adb or not Path(adb).exists():
            return
        devices = ADBConnection.detect_devices(adb)
        if devices:
            serials = [d[0] for d in devices]
            self.cmb_serial["values"] = serials
            if self.var_serial.get() not in serials and self.var_serial.get() != "auto":
                self.var_serial.set(serials[0])
            self._log(f"Devices: {', '.join(serials)}", tag="success")
        else:
            self.cmb_serial["values"] = []
            self._log("No devices", tag="error")

    def _test_adb(self):
        adb = self._resolve_adb()
        if not adb:
            return
        try:
            app = adb.get_foreground_app()
            self._log(f"OK  device={adb.serial}  app={app}", tag="success")
        except Exception as e:
            self._log(f"Failed: {e}", tag="error")

    def _resolve_adb(self) -> Optional[ADBConnection]:
        adb_path = self.var_adb.get()
        if not adb_path or not Path(adb_path).exists():
            messagebox.showerror("Error", f"ADB not found: {adb_path}")
            return None
        serial = self.var_serial.get().strip()
        if not serial or serial.lower() == "auto":
            devices = ADBConnection.detect_devices(adb_path)
            if not devices:
                messagebox.showerror("Error", "No devices connected.")
                return None
            serial = devices[0][0]
            self.var_serial.set(serial)
        return ADBConnection(adb_path, serial)

    # ── Logging ──

    def _log(self, msg: str, tag: str = "info"):
        ts = datetime.now().strftime("%H:%M:%S")
        def _append():
            self.log_text.config(state="normal")
            self.log_text.insert("end", f" {ts} ", "time")
            self.log_text.insert("end", f" {msg}\n", tag)
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        self.root.after(0, _append)

    # ── Start / Stop ──

    def _on_start(self):
        adb = self._resolve_adb()
        if not adb:
            return
        output = self.var_output.get()
        if not output:
            messagebox.showerror("Error", "Select output folder.")
            return

        self._save_current_config()
        self._adb = adb

        output_root = Path(output)
        output_root.mkdir(parents=True, exist_ok=True)

        self._session = SessionManager(output_root, adb)
        try:
            self._session.set_episode_timeout(int(self.var_episode_timeout.get()))
        except ValueError:
            pass

        # 장르별 엔진 생성
        genre = self.var_genre.get()
        log_fn = lambda msg, tag="info": self._log(msg, tag=tag)

        if genre == "puzzle":
            self._engine = PuzzleCaptureEngine(
                adb, self._session,
                log_fn=log_fn,
                before_after=self.var_puzzle_ba.get(),
                after_delay=int(self.var_puzzle_delay.get() or 500) / 1000.0,
                board_roi=_parse_roi_string(self.var_puzzle_roi.get()),
            )
        elif genre == "idle":
            self._engine = IdleCaptureEngine(
                adb, self._session,
                log_fn=log_fn,
                value_regions=_parse_region_dict(self.var_idle_values.get()),
                mask_regions=_parse_region_list(self.var_idle_masks.get()),
                after_delay=int(self.var_idle_delay.get() or 1000) / 1000.0,
                continuous_interval=float(self.var_idle_auto.get() or 0),
            )
        elif genre == "action":
            self._engine = ActionCaptureEngine(
                adb, self._session,
                log_fn=log_fn,
                classify_mode=self.var_action_mode.get(),
                yolo_model_path=self.var_action_yolo.get() or None,
                fingerprint_db_path=self.var_action_fp_db.get() or None,
                after_delay=int(self.var_action_delay.get() or 800) / 1000.0,
                learning_mode=self.var_action_learn.get(),
            )
        else:
            return

        # 상태 갱신
        self._running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.var_status_dot.set(f"Recording ({genre})")
        self.lbl_status_dot.config(fg=SunoTheme.GENRE_COLORS.get(genre, SunoTheme.ACCENT))

        # 앱 감지
        self._session.current_app = adb.get_foreground_app()
        self.var_app.set(f"{self._session.app_label}  ({self._session.current_app})")

        # 모니터 + 엔진 시작
        emu_type = self.var_emu.get()
        self._monitor = TapMonitor(
            emu_type=emu_type,
            swipe_threshold=self.cfg.get("swipe_threshold", 50),
            long_press_ms=self.cfg.get("long_press_ms", 600),
        )
        self._monitor.start()
        self._log(f"Window: {self._monitor.get_emu_info()}", tag="accent")

        self._engine.on_start()
        self._session.start_episode()

        self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._capture_thread.start()
        self._poll_ui()

    def _on_stop(self):
        self._running = False
        if self._engine:
            self._engine.on_stop()
        if self._session:
            self._session.end_episode()
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="disabled")
        self.var_status_dot.set("Stopping...")

        def _cleanup():
            if self._capture_thread and self._capture_thread.is_alive():
                self._capture_thread.join(timeout=3)
            if self._monitor:
                self._monitor.stop()
            self.root.after(0, self._on_stop_done)
        threading.Thread(target=_cleanup, daemon=True).start()

    def _on_stop_done(self):
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        total = self._session.total_captures if self._session else 0
        episodes = self._session.episode_id if self._session else 0
        self.var_status_dot.set("Stopped")
        self.lbl_status_dot.config(fg=SunoTheme.TEXT_MUTED)
        self._log(f"Stopped  total={total}  episodes={episodes}", tag="accent")

    def _on_close(self):
        self._running = False
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1)
        if self._monitor:
            self._monitor.stop()
        self._save_current_config()
        self.root.destroy()

    # ── Capture Loop ──

    def _capture_loop(self):
        try:
            cooldown = float(self.var_cooldown.get())
        except ValueError:
            cooldown = 0.3

        app_check_interval = 3.0
        last_app_check = 0.0
        last_capture_time = 0.0

        # Idle 자동 스냅샷
        idle_auto_interval = 0.0
        last_auto_snapshot = 0.0
        if isinstance(self._engine, IdleCaptureEngine):
            idle_auto_interval = self._engine.continuous_interval

        while self._running:
            now = time.time()

            # 앱 전환 체크
            if now - last_app_check > app_check_interval:
                old = self._session.check_app_change()
                if old:
                    self._log(f"App: {self._session.app_label}")
                    self.root.after(0, lambda: self.var_app.set(
                        f"{self._session.app_label}  ({self._session.current_app})"))
                last_app_check = now

            # 에피소드 타임아웃
            self._session.check_timeout()

            # 제스처 이벤트 처리
            if self._monitor and self._running:
                events = self._monitor.pop_events()
                for evt in events:
                    if not self._running:
                        break
                    if evt["time"] - last_capture_time < cooldown:
                        continue
                    last_capture_time = evt["time"]
                    self._engine.process_event(evt)

            # Idle 자동 스냅샷
            if idle_auto_interval > 0 and now - last_auto_snapshot > idle_auto_interval:
                if isinstance(self._engine, IdleCaptureEngine):
                    self._engine.take_auto_snapshot()
                last_auto_snapshot = now

            time.sleep(0.05)

    def _poll_ui(self):
        if not self._running:
            return
        total = self._session.total_captures if self._session else 0
        self.var_count.set(f"{total} captures")
        self.root.after(500, self._poll_ui)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    # ── 의존성 자동 설치 ──
    from .deps import ensure_dependencies
    root = tk.Tk()
    root.withdraw()  # 메인 윈도우 숨김 → 셋업 먼저

    dep_status = ensure_dependencies(root)

    # deps에서 찾은 ADB를 기본 config에 반영
    root.deiconify()
    app = GenreCaptureApp(root)

    # ADB가 deps에서 설치되었으면 config에 반영
    if dep_status.adb_path and not app.var_adb.get():
        app.var_adb.set(dep_status.adb_path)
        app._update_emu_status()

    root.mainloop()


if __name__ == "__main__":
    main()
