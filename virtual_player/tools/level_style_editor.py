"""
Level Style Editor — JSON/PNG 레벨 데이터 변환 도구
=====================================================
기능:
  1. JSON → PNG: FieldMap을 팔레트 색상으로 시각화
  2. PNG → JSON: 아무 이미지를 게임 팔레트로 변환하여 레벨 JSON 생성
  3. 스타일 변경: 기존 JSON의 색상 배치를 새 이미지로 교체

AI 불필요 — K-Means + 팔레트 매칭으로 동작.

사용법:
  python level_style_editor.py              # GUI 실행
  python level_style_editor.py --cli        # CLI 모드
    --png-to-json <이미지> --output <json>  # PNG → JSON
    --json-to-png <json> --output <png>     # JSON → PNG
"""
import argparse
import json
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from pathlib import Path
from collections import Counter

import numpy as np
from PIL import Image, ImageTk, ImageDraw

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
                profiles = json.load(f)
            if game_id in profiles:
                return profiles[game_id].get("color_palette_28", [])
    return []


# ══════════════════════════════════════════════════════════════
#  Core: PNG ↔ JSON 변환
# ══════════════════════════════════════════════════════════════

def png_to_fieldmap(img_path, grid_size=50, palette=None, num_colors=None):
    """PNG 이미지 → FieldMap + JSON 데이터.

    1. 이미지를 grid_size x grid_size로 리사이즈
    2. K-Means로 대표색 추출
    3. 대표색을 팔레트에 매칭
    4. FieldMap 생성
    """
    img = Image.open(img_path).convert("RGB")
    img_resized = img.resize((grid_size, grid_size), Image.LANCZOS)
    pixels = np.array(img_resized).reshape(-1, 3).astype(np.float32)

    pal_arr = np.array([p["rgb"] for p in palette], dtype=np.float32) if palette else None
    pal_ids = [p["id"] for p in palette] if palette else []

    # K-Means로 색상 클러스터링
    if num_colors:
        k = num_colors
    elif SKLEARN:
        # 자동 k 결정: 팔레트 매칭 후 유의미 색상 수
        if pal_arr is not None:
            dists = np.sqrt(np.sum((pixels[:, None, :] - pal_arr[None, :, :]) ** 2, axis=2))
            nearest = np.argmin(dists, axis=1)
            id_counts = Counter(pal_ids[n] for n in nearest)
            sig = {k: v for k, v in id_counts.items() if v > len(nearest) * 0.02}
            k = max(2, min(len(sig), 8))
        else:
            k = 5
    else:
        k = 5

    if SKLEARN:
        km = KMeans(n_clusters=k, random_state=42, n_init=5, max_iter=30)
        km.fit(pixels)
        labels = km.labels_.reshape(grid_size, grid_size)

        # 클러스터 → 팔레트 매칭
        color_map = {}
        for ci, center in enumerate(km.cluster_centers_):
            rgb = center.astype(np.float32)
            if pal_arr is not None:
                bi = int(np.argmin(np.sqrt(np.sum((pal_arr - rgb) ** 2, axis=1))))
                color_map[ci] = pal_ids[bi]
            else:
                color_map[ci] = ci + 1
    else:
        labels = np.zeros((grid_size, grid_size), dtype=int)
        color_map = {0: 1}

    # FieldMap 생성 (상하반전)
    fm_rows = []
    color_counts = Counter()
    for y in range(grid_size - 1, -1, -1):  # 반전
        tokens = []
        for x in range(grid_size):
            pid = color_map[labels[y][x]]
            tokens.append(f"{pid:02d}")
            color_counts[pid] += 1
        fm_rows.append(tokens)

    return fm_rows, dict(color_counts)


def fieldmap_to_image(fm_rows, palette, cell_size=10):
    """FieldMap → PIL Image (시각화)."""
    pal_colors = {p["id"]: tuple(p["rgb"]) for p in palette}

    rows = len(fm_rows)
    cols = len(fm_rows[0]) if fm_rows else 0

    img = Image.new("RGB", (cols * cell_size, rows * cell_size), (40, 40, 40))
    draw = ImageDraw.Draw(img)

    for r, row in enumerate(fm_rows):
        for c, token in enumerate(row):
            pid = int(token) if token != ".." else 0
            color = pal_colors.get(pid, (40, 40, 40))
            x1, y1 = c * cell_size, r * cell_size
            draw.rectangle([x1, y1, x1 + cell_size - 1, y1 + cell_size - 1], fill=color)

    return img


def build_level_json(fm_rows, color_counts, level_num=1, grid_size=50, source=""):
    """FieldMap + 색상 카운트 → BalloonFlow 호환 JSON."""
    total = sum(color_counts.values())
    num_colors = len(color_counts)
    color_dist = " ".join(
        f"c{cid}:{cnt}" for cid, cnt in sorted(color_counts.items(), key=lambda x: -x[1]))
    fieldmap = "\n".join(" ".join(r) for r in fm_rows)

    return {
        "level_number": level_num,
        "level_id": f"L{level_num:04d}",
        "pkg": (level_num - 1) // 10 + 1,
        "pos": (level_num - 1) % 10 + 1,
        "chapter": (level_num - 1) // 50 + 1,
        "purpose_type": "Normal",
        "target_cr": 0, "target_attempts": 0.0,
        "num_colors": num_colors,
        "color_distribution": color_dist,
        "field_rows": grid_size, "field_columns": grid_size,
        "total_cells": total,
        "rail_capacity": 5, "rail_capacity_tier": "S",
        "queue_columns": min(num_colors, 5), "queue_rows": 3,
        "gimmick_hidden": 0, "gimmick_chain": 0, "gimmick_pinata": 0,
        "gimmick_spawner_t": 0, "gimmick_pin": 0, "gimmick_lock_key": 0,
        "gimmick_surprise": 0, "gimmick_wall": 0, "gimmick_spawner_o": 0,
        "gimmick_pinata_box": 0, "gimmick_ice": 0, "gimmick_frozen_dart": 0,
        "gimmick_curtain": 0,
        "total_darts": total,
        "dart_capacity_range": ",".join(
            [str(total // max(num_colors, 1))] * min(num_colors, 5)),
        "emotion_curve": "",
        "designer_note": f"[FieldMap]\n{fieldmap}",
        "pixel_art_source": source,
    }


def load_json_fieldmap(json_path):
    """기존 JSON에서 FieldMap 파싱."""
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    note = data.get("designer_note", "")
    if "[FieldMap]" not in note:
        return None, data
    parts = note.split("[FieldMap]\n", 1)
    rows = [line.split() for line in parts[1].strip().split("\n")]
    return rows, data


# ══════════════════════════════════════════════════════════════
#  GUI
# ══════════════════════════════════════════════════════════════

class LevelStyleEditor:
    def __init__(self, root):
        self.root = root
        self.root.title("Level Style Editor")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)

        self.palette = load_palette()
        self.fm_rows = None
        self.color_counts = {}
        self.preview_img = None
        self.grid_size = tk.IntVar(value=50)
        self.level_num = tk.IntVar(value=1)
        self.num_colors = tk.IntVar(value=0)  # 0=auto

        self._build_ui()

    def _build_ui(self):
        # ── 상단: 버튼 ──
        toolbar = ttk.Frame(self.root)
        toolbar.pack(fill="x", padx=10, pady=5)

        ttk.Button(toolbar, text="PNG 열기 → 변환", command=self._open_png).pack(side="left", padx=2)
        ttk.Button(toolbar, text="JSON 열기", command=self._open_json).pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Button(toolbar, text="JSON 저장", command=self._save_json).pack(side="left", padx=2)
        ttk.Button(toolbar, text="PNG 저장", command=self._save_png).pack(side="left", padx=2)

        # ── 설정 ──
        settings = ttk.LabelFrame(self.root, text="설정", padding=5)
        settings.pack(fill="x", padx=10, pady=2)

        ttk.Label(settings, text="그리드:").pack(side="left")
        ttk.Spinbox(settings, from_=10, to=50, textvariable=self.grid_size, width=4).pack(side="left", padx=2)

        ttk.Label(settings, text="레벨 번호:").pack(side="left", padx=(10, 0))
        ttk.Spinbox(settings, from_=1, to=9999, textvariable=self.level_num, width=5).pack(side="left", padx=2)

        ttk.Label(settings, text="색상 수 (0=자동):").pack(side="left", padx=(10, 0))
        ttk.Spinbox(settings, from_=0, to=28, textvariable=self.num_colors, width=3).pack(side="left", padx=2)

        # ── 중앙: 미리보기 ──
        preview_frame = ttk.LabelFrame(self.root, text="미리보기", padding=5)
        preview_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.canvas = tk.Canvas(preview_frame, bg="#2d2d2d")
        self.canvas.pack(fill="both", expand=True)

        # ── 하단: 정보 ──
        info_frame = ttk.Frame(self.root)
        info_frame.pack(fill="x", padx=10, pady=5)

        self.info_var = tk.StringVar(value="PNG 또는 JSON을 열어주세요")
        ttk.Label(info_frame, textvariable=self.info_var).pack(side="left")

        # ── 팔레트 표시 ──
        pal_frame = ttk.LabelFrame(self.root, text="팔레트 (28색)", padding=3)
        pal_frame.pack(fill="x", padx=10, pady=(0, 5))

        self.pal_canvas = tk.Canvas(pal_frame, height=25, bg="#1a1a2e")
        self.pal_canvas.pack(fill="x")
        self._draw_palette()

    def _draw_palette(self):
        self.pal_canvas.delete("all")
        w = self.pal_canvas.winfo_width() or 880
        cell_w = w / len(self.palette) if self.palette else 30
        for i, p in enumerate(self.palette):
            r, g, b = p["rgb"]
            color = f"#{r:02x}{g:02x}{b:02x}"
            x = i * cell_w
            self.pal_canvas.create_rectangle(x, 0, x + cell_w, 25, fill=color, outline="")

    def _open_png(self):
        path = filedialog.askopenfilename(
            title="PNG 이미지 선택",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"), ("All", "*.*")])
        if not path:
            return

        grid = self.grid_size.get()
        nc = self.num_colors.get() or None

        self.fm_rows, self.color_counts = png_to_fieldmap(
            path, grid, self.palette, nc)

        self._update_preview()
        num_c = len(self.color_counts)
        self.info_var.set(f"PNG 변환 완료: {grid}x{grid}, {num_c}색 | {Path(path).name}")

    def _open_json(self):
        path = filedialog.askopenfilename(
            title="JSON 레벨 선택",
            filetypes=[("JSON", "*.json"), ("All", "*.*")])
        if not path:
            return

        rows, data = load_json_fieldmap(path)
        if rows is None:
            messagebox.showerror("오류", "FieldMap을 찾을 수 없습니다")
            return

        self.fm_rows = rows
        self.level_num.set(data.get("level_number", 1))
        self.grid_size.set(data.get("field_rows", len(rows)))

        # 색상 카운트 재계산
        self.color_counts = Counter()
        for row in rows:
            for token in row:
                if token != "..":
                    self.color_counts[int(token)] = self.color_counts.get(int(token), 0) + 1

        self._update_preview()
        self.info_var.set(f"JSON 로드: Lv{data.get('level_number', '?')}, "
                          f"{len(rows)}x{len(rows[0])}, {len(self.color_counts)}색")

    def _update_preview(self):
        if not self.fm_rows:
            return

        # FieldMap → 이미지
        canvas_w = self.canvas.winfo_width() or 600
        canvas_h = self.canvas.winfo_height() or 500
        grid = len(self.fm_rows)
        cell_size = max(2, min(canvas_w, canvas_h) // grid)

        img = fieldmap_to_image(self.fm_rows, self.palette, cell_size)
        self.preview_img = img

        # 캔버스에 표시
        self._photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(canvas_w // 2, canvas_h // 2,
                                  image=self._photo, anchor="center")

    def _save_json(self):
        if not self.fm_rows:
            messagebox.showwarning("경고", "먼저 PNG 또는 JSON을 열어주세요")
            return

        path = filedialog.asksaveasfilename(
            title="JSON 저장",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")])
        if not path:
            return

        data = build_level_json(
            self.fm_rows, self.color_counts,
            level_num=self.level_num.get(),
            grid_size=self.grid_size.get(),
            source="style_editor")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        self.info_var.set(f"JSON 저장: {path}")

    def _save_png(self):
        if not self.preview_img:
            messagebox.showwarning("경고", "먼저 PNG 또는 JSON을 열어주세요")
            return

        path = filedialog.asksaveasfilename(
            title="PNG 저장",
            defaultextension=".png",
            filetypes=[("PNG", "*.png")])
        if not path:
            return

        # 고해상도 저장
        img = fieldmap_to_image(self.fm_rows, self.palette, cell_size=20)
        img.save(path)
        self.info_var.set(f"PNG 저장: {path}")


# ══════════════════════════════════════════════════════════════
#  CLI 모드
# ══════════════════════════════════════════════════════════════

def cli_png_to_json(args):
    palette = load_palette(args.game)
    nc = args.num_colors or None
    fm_rows, counts = png_to_fieldmap(args.input, args.grid, palette, nc)
    data = build_level_json(fm_rows, counts, args.level, args.grid, str(args.input))
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved: {args.output} ({len(counts)} colors)")


def cli_json_to_png(args):
    palette = load_palette(args.game)
    rows, data = load_json_fieldmap(args.input)
    if rows is None:
        print("ERROR: No FieldMap found")
        return
    img = fieldmap_to_image(rows, palette, cell_size=args.cell_size)
    img.save(args.output)
    print(f"Saved: {args.output} ({img.size[0]}x{img.size[1]})")


def main():
    parser = argparse.ArgumentParser(description="Level Style Editor")
    parser.add_argument("--cli", action="store_true", help="CLI 모드")
    parser.add_argument("--game", default="balloonflow")

    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("png2json", help="PNG → JSON")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--grid", type=int, default=50)
    p.add_argument("--level", type=int, default=1)
    p.add_argument("--num-colors", type=int, default=0)

    p = sub.add_parser("json2png", help="JSON → PNG")
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--cell-size", type=int, default=20)

    args = parser.parse_args()

    if args.cli or args.command:
        if args.command == "png2json":
            cli_png_to_json(args)
        elif args.command == "json2png":
            cli_json_to_png(args)
        else:
            parser.print_help()
    else:
        root = tk.Tk()
        app = LevelStyleEditor(root)
        root.mainloop()


if __name__ == "__main__":
    main()
