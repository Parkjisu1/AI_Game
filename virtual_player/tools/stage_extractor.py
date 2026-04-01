"""
Stage Extractor — 스테이지 시작 화면 추출 + Crop + JSON 변환
=============================================================
10만장+ 이미지에서 스테이지 시작 화면만 추출하고,
보드를 크롭하여 게임 레벨 데이터 JSON으로 변환.

사용법:
  # 1단계: 추출
  StageExtractor.exe extract
    --input-dir F:/pixelflow
    --log F:/pixelflow/session_log.jsonl
    --model best.pt
    --output-dir ./extracted

  # 2단계: Crop + JSON
  StageExtractor.exe crop
    --input-dir ./extracted
    --output-dir ./levels
    --grid 50 --game pixelflow --start-level 51
"""
import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

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


def load_palette(game_id):
    for p in [SCRIPT_DIR / "game_profiles.json",
              Path(__file__).resolve().parent / "game_profiles.json",
              Path("game_profiles.json")]:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                profiles = json.load(f)
            if game_id in profiles:
                return profiles[game_id].get("color_palette_28", [])
    return []


def img_hash(path, size=16):
    arr = np.array(Image.open(path).convert("L").resize((size, size)))
    return "".join("1" if b else "0" for b in (arr > arr.mean()).flatten())


# ══════════════════════════════════════════════════════════════
#  EXTRACT: session_log + YOLO로 스테이지 시작 추출
# ══════════════════════════════════════════════════════════════

def cmd_extract(args):
    data_dir = Path(args.input_dir)
    log_path = Path(args.log)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not YOLO_AVAILABLE:
        print("ERROR: ultralytics 필요. pip install ultralytics")
        return

    # 1. JSON 파싱
    events = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            e = json.loads(line.strip())
            if e.get("event") != "episode_start":
                events.append(e)
    print(f"Events: {len(events)}")

    # 2. delta > 0.5 후보
    targets = []
    for i, evt in enumerate(events):
        d = evt.get("delta_from_prev")
        if d and d > 0.5:
            af = evt.get("after_file", "")
            if af and (data_dir / af).exists():
                targets.append({"idx": i, "file": af})
    print(f"Delta candidates: {len(targets)}")

    # 3. YOLO stage_start 필터
    model = YOLO(args.model)
    print(f"YOLO: {len(targets)} images...")

    stage_starts = []
    for i in range(0, len(targets), 16):
        batch = targets[i:i + 16]
        paths = [str(data_dir / t["file"]) for t in batch]
        for t, pred in zip(batch, model.predict(paths, verbose=False, stream=True)):
            if pred.probs and model.names[int(pred.probs.top1)] == "stage_start":
                stage_starts.append(t)
        done = min(i + 16, len(targets))
        if done % 200 < 16:
            print(f"  {done}/{len(targets)} -> {len(stage_starts)} stage_starts")

    print(f"Stage starts: {len(stage_starts)}")

    # 4. 중복 제거
    unique, seen = [], []
    for s in stage_starts:
        fp = data_dir / s["file"]
        h = img_hash(fp)
        if not any(sum(a != b for a, b in zip(h, sh)) < 20 for sh in seen):
            unique.append(s)
            seen.append(h)
    print(f"Unique: {len(unique)}")

    # 5. 저장
    entries = []
    for i, s in enumerate(unique):
        dst = f"stage_{i + 1:03d}.png"
        shutil.copy2(data_dir / s["file"], out_dir / dst)
        entries.append({"stage": i + 1, "file": dst, "source": s["file"]})

    with open(out_dir / "index.json", "w", encoding="utf-8") as f:
        json.dump({"total": len(entries), "stages": entries}, f, indent=2, ensure_ascii=False)

    print(f"\nSaved: {out_dir} ({len(unique)} stages)")


# ══════════════════════════════════════════════════════════════
#  CROP + JSON: 보드 크롭 + 레벨 데이터 JSON 생성
# ══════════════════════════════════════════════════════════════

def cmd_crop(args):
    in_dir = Path(args.input_dir)
    out_dir = Path(args.output_dir)
    board_dir = out_dir / "boards"
    json_dir = out_dir / "json"
    board_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    index = json.loads((in_dir / "index.json").read_text(encoding="utf-8"))
    palette = load_palette(args.game)
    pal_arr = np.array([p["rgb"] for p in palette], dtype=np.float32) if palette else None
    pal_ids = [p["id"] for p in palette] if palette else []
    pal_names = {p["id"]: p["name"] for p in palette} if palette else {}

    BOARD = tuple(args.board_rect) if args.board_rect else (155, 333, 735, 663)
    GRID = args.grid
    FLIP = args.flip
    START = args.start_level

    print(f"Processing {len(index['stages'])} stages (grid={GRID}x{GRID})")

    for entry in index["stages"]:
        fp = in_dir / entry["file"]
        img = np.array(Image.open(fp).convert("RGB"))

        bx, by, bw, bh = BOARD
        board = img[by:by + bh, bx:bx + bw]
        Image.fromarray(board).save(str(board_dir / entry["file"]))

        # K-Means 색상 보정
        km, color_map = None, None
        if SKLEARN and pal_arr is not None:
            board_bgr = board[:, :, ::-1]
            pixels_rgb = board.reshape(-1, 3).astype(np.float32)
            dists_all = np.sqrt(np.sum((pixels_rgb[:, None, :] - pal_arr[None, :, :]) ** 2, axis=2))
            nearest = np.argmin(dists_all, axis=1)
            id_counts = Counter(pal_ids[n] for n in nearest)
            sig = {k: v for k, v in id_counts.items() if v > len(nearest) * 0.01}
            k = max(2, min(len(sig), 8))

            km = KMeans(n_clusters=k, random_state=42, n_init=5, max_iter=30)
            km.fit(board_bgr.reshape(-1, 3).astype(np.float32))

            color_map = {}
            for ci, center in enumerate(km.cluster_centers_):
                rgb = np.array([center[2], center[1], center[0]], dtype=np.float32)
                bi = int(np.argmin(np.sqrt(np.sum((pal_arr - rgb) ** 2, axis=1))))
                color_map[ci] = pal_ids[bi]

        # FieldMap
        ch_sz, cw_sz = bh / GRID, bw / GRID
        fm_rows, color_counts = [], {}

        for r in range(GRID):
            tokens = []
            for c in range(GRID):
                cy = int((r + 0.5) * ch_sz)
                cx = int((c + 0.5) * cw_sz)
                m = max(1, int(min(ch_sz, cw_sz) * 0.15))
                cell = board[max(0, cy - m):min(bh, cy + m), max(0, cx - m):min(bw, cx + m)]
                cell_bgr = cell[:, :, ::-1]

                if km and color_map:
                    avg = cell_bgr.mean(axis=(0, 1)).reshape(1, -1).astype(np.float32)
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
        total_cells = sum(color_counts.values())
        num_colors = len(color_counts)
        color_dist = " ".join(
            f"c{cid}:{cnt}" for cid, cnt in sorted(color_counts.items(), key=lambda x: -x[1]))

        level_num = START + entry["stage"] - 1

        level_json = {
            "level_number": level_num,
            "level_id": f"L{level_num:04d}",
            "pkg": (level_num - 1) // 10 + 1,
            "pos": (level_num - 1) % 10 + 1,
            "chapter": (level_num - 1) // 50 + 1,
            "purpose_type": "Normal",
            "target_cr": 0, "target_attempts": 0.0,
            "num_colors": num_colors,
            "color_distribution": color_dist,
            "field_rows": GRID, "field_columns": GRID,
            "total_cells": total_cells,
            "rail_capacity": 5, "rail_capacity_tier": "S",
            "queue_columns": min(num_colors, 5), "queue_rows": 3,
            "gimmick_hidden": 0, "gimmick_chain": 0, "gimmick_pinata": 0,
            "gimmick_spawner_t": 0, "gimmick_pin": 0, "gimmick_lock_key": 0,
            "gimmick_surprise": 0, "gimmick_wall": 0, "gimmick_spawner_o": 0,
            "gimmick_pinata_box": 0, "gimmick_ice": 0, "gimmick_frozen_dart": 0,
            "gimmick_curtain": 0,
            "total_darts": total_cells,
            "dart_capacity_range": ",".join(
                [str(total_cells // max(num_colors, 1))] * min(num_colors, 5)),
            "emotion_curve": "",
            "designer_note": f"[FieldMap]\n{fieldmap}",
            "pixel_art_source": entry.get("source", entry["file"])
        }

        with open(json_dir / f"level_{level_num:03d}.json", "w", encoding="utf-8") as f:
            json.dump(level_json, f, indent=2, ensure_ascii=False)

        if entry["stage"] % 50 == 0:
            print(f"  {entry['stage']}/{len(index['stages'])}")

    print(f"\nDone: boards={board_dir} json={json_dir}")


def main():
    parser = argparse.ArgumentParser(description="Stage Extractor")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("extract", help="스테이지 시작 화면 추출")
    p.add_argument("--input-dir", required=True, help="이미지 폴더")
    p.add_argument("--log", required=True, help="session_log.jsonl")
    p.add_argument("--model", required=True, help="YOLO .pt 경로")
    p.add_argument("--output-dir", required=True, help="출력 폴더")
    p.add_argument("--game", default="pixelflow")

    p = sub.add_parser("crop", help="Crop + JSON 변환")
    p.add_argument("--input-dir", required=True, help="extract 결과 폴더")
    p.add_argument("--output-dir", required=True, help="출력 폴더")
    p.add_argument("--game", default="pixelflow")
    p.add_argument("--grid", type=int, default=50, help="그리드 크기 (기본 50)")
    p.add_argument("--board-rect", type=int, nargs=4, help="보드 좌표 x y w h")
    p.add_argument("--start-level", type=int, default=51, help="시작 레벨 번호")
    p.add_argument("--flip", action="store_true", default=True, help="FieldMap 상하반전")
    p.add_argument("--no-flip", dest="flip", action="store_false")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return
    {"extract": cmd_extract, "crop": cmd_crop}[args.command](args)


if __name__ == "__main__":
    main()
