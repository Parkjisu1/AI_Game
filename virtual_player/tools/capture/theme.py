"""
SunoTheme — SUNO-inspired Dark UI
===================================
기존 click_capture.py의 SunoTheme을 공용으로 분리.
"""

import tkinter as tk
from tkinter import ttk


class SunoTheme:
    BG = "#0d0d0d"
    CARD = "#161618"
    SURFACE = "#1c1c1f"
    BORDER = "#2a2a2e"
    ACCENT = "#8b5cf6"
    ACCENT_HOVER = "#a78bfa"
    ACCENT_DIM = "#6d42d4"
    TEXT = "#e4e4e7"
    TEXT_DIM = "#8b8b94"
    TEXT_MUTED = "#57575e"
    SUCCESS = "#34d399"
    WARNING = "#fbbf24"
    ERROR = "#f87171"
    FONT = ("Segoe UI", 9)
    FONT_BOLD = ("Segoe UI", 9, "bold")
    FONT_HEADING = ("Segoe UI", 11, "bold")
    FONT_SMALL = ("Segoe UI", 8)
    FONT_LOG = ("Cascadia Code", 9)

    # 장르별 액센트 컬러
    GENRE_COLORS = {
        "puzzle": "#8b5cf6",   # 퍼플 (기존)
        "idle": "#f59e0b",     # 앰버
        "action": "#ef4444",   # 레드
    }

    @classmethod
    def apply(cls, root: tk.Tk):
        root.configure(bg=cls.BG)
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".",
                         background=cls.BG, foreground=cls.TEXT,
                         fieldbackground=cls.SURFACE, bordercolor=cls.BORDER,
                         darkcolor=cls.SURFACE, lightcolor=cls.SURFACE,
                         troughcolor=cls.BG,
                         selectbackground=cls.ACCENT, selectforeground="#ffffff",
                         font=cls.FONT)

        # Frames
        style.configure("TFrame", background=cls.BG)
        style.configure("Card.TFrame", background=cls.CARD)

        # Labels
        style.configure("TLabel", background=cls.BG, foreground=cls.TEXT, font=cls.FONT)
        style.configure("Heading.TLabel", font=cls.FONT_HEADING, foreground=cls.TEXT)
        style.configure("Dim.TLabel", foreground=cls.TEXT_DIM, font=cls.FONT)
        style.configure("Muted.TLabel", foreground=cls.TEXT_MUTED, font=cls.FONT_SMALL)
        style.configure("Card.TLabel", background=cls.CARD, foreground=cls.TEXT, font=cls.FONT)
        style.configure("CardDim.TLabel", background=cls.CARD, foreground=cls.TEXT_DIM, font=cls.FONT)
        style.configure("Accent.TLabel", foreground=cls.ACCENT, font=cls.FONT_BOLD)
        style.configure("Success.TLabel", foreground=cls.SUCCESS, font=cls.FONT_BOLD)
        style.configure("Error.TLabel", foreground=cls.ERROR, font=cls.FONT_BOLD)

        # LabelFrame
        style.configure("TLabelframe",
                         background=cls.CARD, foreground=cls.TEXT_DIM,
                         bordercolor=cls.BORDER, font=cls.FONT_SMALL)
        style.configure("TLabelframe.Label",
                         background=cls.CARD, foreground=cls.TEXT_DIM, font=cls.FONT_SMALL)

        # Buttons
        style.configure("TButton",
                         background=cls.SURFACE, foreground=cls.TEXT,
                         bordercolor=cls.BORDER, padding=(12, 6), font=cls.FONT)
        style.map("TButton",
                   background=[("active", cls.BORDER), ("disabled", cls.BG)],
                   foreground=[("disabled", cls.TEXT_MUTED)])

        style.configure("Accent.TButton",
                         background=cls.ACCENT, foreground="#ffffff",
                         bordercolor=cls.ACCENT_DIM, padding=(16, 8), font=cls.FONT_BOLD)
        style.map("Accent.TButton",
                   background=[("active", cls.ACCENT_HOVER), ("disabled", cls.TEXT_MUTED)])

        style.configure("Danger.TButton",
                         background="#dc2626", foreground="#ffffff",
                         bordercolor="#991b1b", padding=(16, 8), font=cls.FONT_BOLD)
        style.map("Danger.TButton",
                   background=[("active", "#ef4444"), ("disabled", cls.TEXT_MUTED)])

        # Entry
        style.configure("TEntry",
                         fieldbackground=cls.SURFACE, foreground=cls.TEXT,
                         bordercolor=cls.BORDER, insertcolor=cls.TEXT, padding=5)
        style.map("TEntry",
                   bordercolor=[("focus", cls.ACCENT)],
                   fieldbackground=[("focus", "#1e1e22")])

        # Combobox
        style.configure("TCombobox",
                         fieldbackground=cls.SURFACE, foreground=cls.TEXT,
                         bordercolor=cls.BORDER, arrowcolor=cls.TEXT_DIM, padding=5)
        style.map("TCombobox",
                   bordercolor=[("focus", cls.ACCENT)],
                   fieldbackground=[("readonly", cls.SURFACE)])

        # Checkbutton
        style.configure("TCheckbutton",
                         background=cls.CARD, foreground=cls.TEXT, font=cls.FONT)
        style.map("TCheckbutton", background=[("active", cls.CARD)])

        # Radiobutton
        style.configure("TRadiobutton",
                         background=cls.CARD, foreground=cls.TEXT, font=cls.FONT)
        style.map("TRadiobutton", background=[("active", cls.CARD)])

        # Separator
        style.configure("TSeparator", background=cls.BORDER)

        # Notebook (tabs)
        style.configure("TNotebook", background=cls.BG, bordercolor=cls.BORDER)
        style.configure("TNotebook.Tab",
                         background=cls.SURFACE, foreground=cls.TEXT_DIM, padding=(12, 6))
        style.map("TNotebook.Tab",
                   background=[("selected", cls.CARD)],
                   foreground=[("selected", cls.TEXT)])

        # Scrollbar
        style.configure("Vertical.TScrollbar",
                         background=cls.SURFACE, bordercolor=cls.BG,
                         arrowcolor=cls.TEXT_DIM, troughcolor=cls.BG)

        # Genre-specific button styles
        for genre, color in cls.GENRE_COLORS.items():
            style.configure(f"{genre.capitalize()}.TButton",
                             background=color, foreground="#ffffff",
                             bordercolor=color, padding=(16, 8), font=cls.FONT_BOLD)
            style.map(f"{genre.capitalize()}.TButton",
                       background=[("active", color), ("disabled", cls.TEXT_MUTED)])
