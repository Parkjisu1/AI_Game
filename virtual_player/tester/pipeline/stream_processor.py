"""
Stream Processor — 대용량 이미지 스트리밍 처리 엔진
=====================================================
10만장+ 이미지를 디스크/메모리 부담 없이 처리.

핵심 원칙:
  - 이미지를 1장씩 메모리에 로드 → 처리 → 즉시 해제
  - 원본 이미지는 처리 후 선택적 삭제
  - DB에는 패턴(JSON)만 저장 (~1KB/턴)
  - 메모리 사용: 상시 ~10MB

사용법:
  # 폴더 스트리밍 (기존 데이터)
  python stream_processor.py process \\
    --input-dir <이미지폴더> --game pixelflow --delete-after

  # 실시간 감시 (녹화 중)
  python stream_processor.py watch \\
    --input-dir <녹화폴더> --game pixelflow

  # 디바이스 → 중앙 스트리밍
  python stream_processor.py sync \\
    --source <디바이스경로> --target <중앙DB> --game pixelflow
"""

import gc
import hashlib
import json
import os
import sqlite3
import sys
import time
import uuid
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

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


# ══════════════════════════════════════════════════════════════
#  Game Profile (고정 좌표)
# ══════════════════════════════════════════════════════════════

def load_game_profile(game_id):
    """game_profiles.json에서 게임 프로필 로드."""
    for p in [
        Path(__file__).resolve().parent.parent.parent / "tools" / "game_profiles.json",
        Path("game_profiles.json"),
    ]:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                profiles = json.load(f)
            if game_id in profiles:
                return profiles[game_id]
    return None


# ══════════════════════════════════════════════════════════════
#  Lightweight DB (스트리밍 전용, 최소 스키마)
# ══════════════════════════════════════════════════════════════

class StreamDB:
    """스트리밍 처리용 경량 DB. 패턴만 저장."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self._init()
        self._batch = []
        self._batch_size = 100

    def _init(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS frame_record (
                frame_id    TEXT PRIMARY KEY,
                game_id     TEXT,
                timestamp   TEXT,
                file_name   TEXT,
                screen_type TEXT,
                state_hash  TEXT,
                is_stage_start BOOLEAN DEFAULT 0,
                board_grid  TEXT,
                color_dist  TEXT,
                fieldmap    TEXT,
                delta_from_prev REAL DEFAULT 0,
                processed_at TEXT
            );
            CREATE TABLE IF NOT EXISTS pattern (
                pattern_id  TEXT PRIMARY KEY,
                game_id     TEXT,
                state_hash  TEXT NOT NULL,
                screen_type TEXT,
                action_type TEXT,
                action_x    REAL,
                action_y    REAL,
                times_seen  INTEGER DEFAULT 1,
                times_success INTEGER DEFAULT 0,
                confidence  REAL DEFAULT 0.5,
                source      TEXT DEFAULT 'stream'
            );
            CREATE TABLE IF NOT EXISTS stream_stats (
                game_id     TEXT PRIMARY KEY,
                total_frames INTEGER DEFAULT 0,
                gameplay_frames INTEGER DEFAULT 0,
                stage_starts INTEGER DEFAULT 0,
                patterns    INTEGER DEFAULT 0,
                last_frame  TEXT,
                last_updated TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_fr_hash ON frame_record(state_hash);
            CREATE INDEX IF NOT EXISTS idx_fr_stage ON frame_record(is_stage_start);
            CREATE INDEX IF NOT EXISTS idx_pat_hash ON pattern(state_hash);
        """)
        self.conn.commit()

    def record_frame(self, game_id, file_name, screen_type, state_hash,
                     is_stage_start, board_grid, color_dist, fieldmap, delta):
        """프레임 처리 결과 기록 (배치)."""
        self._batch.append((
            str(uuid.uuid4()), game_id, datetime.now().isoformat(),
            file_name, screen_type, state_hash, is_stage_start,
            board_grid, color_dist, fieldmap, delta, datetime.now().isoformat()
        ))
        if len(self._batch) >= self._batch_size:
            self._flush()

    def _flush(self):
        if not self._batch:
            return
        self.conn.executemany("""
            INSERT OR IGNORE INTO frame_record
            (frame_id, game_id, timestamp, file_name, screen_type, state_hash,
             is_stage_start, board_grid, color_dist, fieldmap, delta_from_prev, processed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, self._batch)
        self.conn.commit()
        self._batch.clear()

    def update_stats(self, game_id, total, gameplay, stages, patterns):
        self.conn.execute("""
            INSERT OR REPLACE INTO stream_stats
            (game_id, total_frames, gameplay_frames, stage_starts, patterns, last_updated)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (game_id, total, gameplay, stages, patterns, datetime.now().isoformat()))
        self.conn.commit()

    def get_stats(self, game_id):
        row = self.conn.execute(
            "SELECT * FROM stream_stats WHERE game_id = ?", (game_id,)).fetchone()
        if row:
            return dict(zip(["game_id", "total_frames", "gameplay_frames",
                             "stage_starts", "patterns", "last_frame", "last_updated"], row))
        return None

    def close(self):
        self._flush()
        self.conn.close()


# ══════════════════════════════════════════════════════════════
#  Frame Processor (1장 처리 단위)
# ══════════════════════════════════════════════════════════════

class FrameProcessor:
    """이미지 1장을 처리하는 단위 프로세서.

    메모리에 1장만 로드하고, 처리 후 즉시 해제.
    """

    def __init__(self, game_id, profile=None, yolo_model=None):
        self.game_id = game_id
        self.profile = profile
        self.yolo_model = yolo_model

        # 보드 좌표 (프로필에서 로드 또는 None)
        self.board_rect = None
        if profile and "board_rect" in profile:
            r = profile["board_rect"]
            self.board_rect = (r["x"], r["y"], r["w"], r["h"])

        # 팔레트
        self.palette = None
        self.pal_arr = None
        if profile and "color_palette_28" in profile:
            self.palette = profile["color_palette_28"]
            self.pal_arr = np.array([p["rgb"] for p in self.palette], dtype=np.float32)
            self.pal_ids = [p["id"] for p in self.palette]
            self.pal_names = {p["id"]: p["name"] for p in self.palette}

        # 이전 프레임 해시 (delta 계산용)
        self._prev_hash = None
        self._prev_gray_small = None

    def process(self, img_path):
        """이미지 1장 처리 → 결과 dict 반환.

        Returns:
            dict: {
                screen_type, state_hash, is_stage_start,
                grid_rows, grid_cols, color_dist, fieldmap,
                delta_from_prev
            }
        """
        img_path = Path(img_path)
        result = {
            "file": img_path.name,
            "screen_type": "unknown",
            "state_hash": None,
            "is_stage_start": False,
            "grid_rows": 0, "grid_cols": 0,
            "color_dist": "",
            "fieldmap": "",
            "delta": 0.0,
        }

        # 이미지 로드
        if CV2_AVAILABLE:
            img = cv2.imread(str(img_path))
        else:
            img = np.array(Image.open(img_path).convert("RGB"))[:, :, ::-1]

        if img is None:
            return result

        h, w = img.shape[:2]

        # 1) 이미지 해시
        small_gray = cv2.resize(
            cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if CV2_AVAILABLE else img[:,:,0],
            (16, 16)
        ).astype(np.float32)
        mean_val = small_gray.mean()
        result["state_hash"] = "".join(
            "1" if b else "0" for b in (small_gray > mean_val).flatten())

        # 2) Delta (이전 프레임과 비교)
        if self._prev_gray_small is not None:
            result["delta"] = float(
                np.mean(np.abs(small_gray - self._prev_gray_small)) / 255.0)
        self._prev_gray_small = small_gray.copy()

        # 3) 스테이지 전환 감지 (delta > 0.15 후 안정)
        if result["delta"] > 0.15:
            self._in_transition = True
        elif hasattr(self, '_in_transition') and self._in_transition and result["delta"] < 0.08:
            result["is_stage_start"] = True
            self._in_transition = False

        # 4) YOLO 화면 분류
        if self.yolo_model:
            preds = self.yolo_model.predict(str(img_path), verbose=False)
            if preds and preds[0].probs is not None:
                result["screen_type"] = self.yolo_model.names[int(preds[0].probs.top1)]

        # 5) 보드 분석 (gameplay 또는 stage_start일 때만)
        if result["is_stage_start"] or result["screen_type"] == "gameplay":
            board_info = self._analyze_board(img)
            result.update(board_info)

        # 메모리 해제
        del img
        gc.collect()

        return result

    def _analyze_board(self, img):
        """보드 영역 분석 → 그리드 + 색상."""
        info = {"grid_rows": 0, "grid_cols": 0, "color_dist": "", "fieldmap": ""}
        h, w = img.shape[:2]

        # 보드 크롭
        if self.board_rect:
            bx, by, bw, bh = self.board_rect
        else:
            # 기본: 상부 중앙 60%
            bx = int(w * 0.1)
            by = int(h * 0.15)
            bw = int(w * 0.8)
            bh = int(h * 0.4)

        board = img[by:by + bh, bx:bx + bw]
        if board.size == 0:
            return info

        # 자기상관으로 셀 크기 감지
        gray = cv2.cvtColor(board, cv2.COLOR_BGR2GRAY) if CV2_AVAILABLE else board[:,:,0]
        lap = np.abs(cv2.Laplacian(gray, cv2.CV_64F)).astype(np.uint8) if CV2_AVAILABLE else gray

        cell_h = self._autocorr_period(lap.mean(axis=1))
        cell_w = self._autocorr_period(lap.mean(axis=0))

        if cell_h < 5 or cell_w < 5:
            return info

        rows = round(bh / cell_h)
        cols = round(bw / cell_w)
        info["grid_rows"] = rows
        info["grid_cols"] = cols

        # 색상 추출
        if self.pal_arr is not None and rows > 0 and cols > 0:
            ch_sz = bh / rows
            cw_sz = bw / cols
            fm_rows = []
            counts = {}

            for r in range(rows):
                tokens = []
                for c in range(cols):
                    cy = int((r + 0.5) * ch_sz)
                    cx = int((c + 0.5) * cw_sz)
                    m = max(2, int(min(ch_sz, cw_sz) * 0.15))
                    cell = board[max(0, cy-m):min(bh, cy+m), max(0, cx-m):min(bw, cx+m)]
                    if cell.size == 0:
                        tokens.append(".."); continue

                    avg = cell.mean(axis=(0, 1))
                    rgb = np.array([avg[2], avg[1], avg[0]], dtype=np.float32)
                    bi = int(np.argmin(np.sqrt(np.sum((self.pal_arr - rgb)**2, axis=1))))
                    pid = self.pal_ids[bi]
                    tokens.append(f"{pid:02d}")
                    counts[pid] = counts.get(pid, 0) + 1

                fm_rows.append(tokens)

            info["fieldmap"] = "\n".join(" ".join(r) for r in fm_rows)
            total = sum(counts.values())
            info["color_dist"] = " | ".join(
                f"{self.pal_names.get(k, '?')}:{v}"
                for k, v in sorted(counts.items(), key=lambda x: -x[1])
            )

        return info

    @staticmethod
    def _autocorr_period(signal, min_p=8, max_p=None):
        n = len(signal)
        if max_p is None:
            max_p = n // 3
        sig = signal.astype(float) - signal.mean()
        if np.std(sig) < 1:
            return 0
        corr = np.correlate(sig, sig, mode='full')[n - 1:]
        if corr[0] == 0:
            return 0
        corr = corr / corr[0]
        for i in range(min_p, min(max_p, len(corr) - 1)):
            if corr[i - 1] < corr[i] > corr[i + 1] and corr[i] > 0.2:
                return i
        return 0


# ══════════════════════════════════════════════════════════════
#  Stream Engine (메인 루프)
# ══════════════════════════════════════════════════════════════

class StreamEngine:
    """대용량 이미지 스트리밍 처리 엔진.

    메모리: 상시 ~10MB
    디스크: DB 파일 하나 (~50MB for 10만장)
    속도: ~100장/초 (YOLO 없이), ~20장/초 (YOLO 포함)
    """

    def __init__(self, game_id, db_path=None, yolo_model_path=None,
                 profile=None, delete_after=False):
        self.game_id = game_id
        self.delete_after = delete_after
        self.profile = profile or load_game_profile(game_id)

        # DB
        db_path = db_path or f"stream_{game_id}.db"
        self.db = StreamDB(db_path)

        # YOLO
        yolo_model = None
        if yolo_model_path and YOLO_AVAILABLE and Path(yolo_model_path).exists():
            yolo_model = YOLO(str(yolo_model_path))

        # Processor
        self.processor = FrameProcessor(game_id, self.profile, yolo_model)

        # 통계
        self.stats = {
            "total": 0, "gameplay": 0, "stage_starts": 0,
            "errors": 0, "deleted": 0,
        }

    def process_directory(self, input_dir, pattern="*.png", progress_interval=100):
        """폴더의 이미지를 스트리밍 처리.

        이미지를 1장씩 로드 → 처리 → DB 기록 → (선택) 삭제.
        전체 이미지를 메모리에 올리지 않음.
        """
        input_dir = Path(input_dir)
        files = sorted(input_dir.glob(pattern))
        total = len(files)

        if total == 0:
            print(f"  No files matching {pattern} in {input_dir}")
            return self.stats

        print(f"\n  Streaming: {total} files from {input_dir}")
        print(f"  DB: {self.db.db_path}")
        print(f"  Delete after: {self.delete_after}")
        print(f"  {'='*50}")

        start_time = time.time()
        stage_starts = []

        for i, fp in enumerate(files):
            try:
                result = self.processor.process(fp)
                self.stats["total"] += 1

                if result["screen_type"] == "gameplay":
                    self.stats["gameplay"] += 1
                if result["is_stage_start"]:
                    self.stats["stage_starts"] += 1
                    stage_starts.append(fp.name)

                # DB 기록
                self.db.record_frame(
                    self.game_id, fp.name, result["screen_type"],
                    result["state_hash"], result["is_stage_start"],
                    f"{result['grid_rows']}x{result['grid_cols']}",
                    result["color_dist"], result["fieldmap"],
                    result["delta"]
                )

                # 원본 삭제
                if self.delete_after:
                    fp.unlink()
                    self.stats["deleted"] += 1

            except Exception as e:
                self.stats["errors"] += 1

            # 진행 표시
            if (i + 1) % progress_interval == 0 or i == total - 1:
                elapsed = time.time() - start_time
                fps = (i + 1) / max(elapsed, 0.1)
                eta = (total - i - 1) / max(fps, 0.1)
                mem_mb = self._get_memory_mb()

                print(f"\r  [{i+1}/{total}] "
                      f"{fps:.1f} fps | "
                      f"ETA {eta:.0f}s | "
                      f"stages={self.stats['stage_starts']} | "
                      f"mem={mem_mb:.0f}MB", end="", flush=True)

        print()
        elapsed = time.time() - start_time

        # 통계 저장
        self.db.update_stats(
            self.game_id, self.stats["total"], self.stats["gameplay"],
            self.stats["stage_starts"], 0)

        # 요약
        print(f"\n  {'='*50}")
        print(f"  완료: {self.stats['total']}장 처리 ({elapsed:.1f}초)")
        print(f"  속도: {self.stats['total']/max(elapsed,0.1):.1f} fps")
        print(f"  스테이지 시작: {self.stats['stage_starts']}개")
        if stage_starts:
            for s in stage_starts[:10]:
                print(f"    {s}")
            if len(stage_starts) > 10:
                print(f"    ... 외 {len(stage_starts)-10}개")
        print(f"  에러: {self.stats['errors']}")
        if self.delete_after:
            print(f"  삭제: {self.stats['deleted']}장")
        print(f"  DB: {self.db.db_path} ({self.db.db_path.stat().st_size/1024:.0f}KB)")

        return self.stats

    def watch_directory(self, input_dir, pattern="*.png", poll_sec=2):
        """폴더를 감시하며 새 이미지가 추가되면 즉시 처리."""
        input_dir = Path(input_dir)
        print(f"\n  Watching: {input_dir} (Ctrl+C to stop)")
        print(f"  Pattern: {pattern}")

        seen = set()
        if input_dir.exists():
            seen = set(f.name for f in input_dir.glob(pattern))
            print(f"  Existing files: {len(seen)} (skipped)")

        try:
            while True:
                if not input_dir.exists():
                    time.sleep(poll_sec)
                    continue

                current = set(f.name for f in input_dir.glob(pattern))
                new_files = sorted(current - seen)

                if new_files:
                    print(f"\n  New: {len(new_files)} files")
                    for fn in new_files:
                        fp = input_dir / fn
                        result = self.processor.process(fp)
                        self.stats["total"] += 1

                        if result["is_stage_start"]:
                            self.stats["stage_starts"] += 1
                            print(f"    [STAGE] {fn}: {result['grid_rows']}x{result['grid_cols']}")

                        self.db.record_frame(
                            self.game_id, fn, result["screen_type"],
                            result["state_hash"], result["is_stage_start"],
                            f"{result['grid_rows']}x{result['grid_cols']}",
                            result["color_dist"], result["fieldmap"],
                            result["delta"])

                        if self.delete_after:
                            fp.unlink()

                    seen = current

                time.sleep(poll_sec)

        except KeyboardInterrupt:
            print(f"\n  Stopped. Total: {self.stats['total']} processed")

    def close(self):
        self.db.close()

    @staticmethod
    def _get_memory_mb():
        try:
            import psutil
            return psutil.Process().memory_info().rss / 1024 / 1024
        except ImportError:
            return 0


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Stream Processor — Large-scale image processing")
    sub = parser.add_subparsers(dest="command")

    # process
    p = sub.add_parser("process", help="폴더 일괄 스트리밍 처리")
    p.add_argument("--input-dir", required=True)
    p.add_argument("--game", required=True)
    p.add_argument("--db", help="DB 경로")
    p.add_argument("--model", help="YOLO 모델")
    p.add_argument("--delete-after", action="store_true", help="처리 후 원본 삭제")
    p.add_argument("--pattern", default="*.png")

    # watch
    p = sub.add_parser("watch", help="폴더 실시간 감시")
    p.add_argument("--input-dir", required=True)
    p.add_argument("--game", required=True)
    p.add_argument("--db", help="DB 경로")
    p.add_argument("--model", help="YOLO 모델")
    p.add_argument("--delete-after", action="store_true")

    # stats
    p = sub.add_parser("stats", help="처리 통계")
    p.add_argument("--db", required=True)
    p.add_argument("--game", required=True)

    args = parser.parse_args()

    if args.command == "process":
        engine = StreamEngine(args.game, args.db, args.model, delete_after=args.delete_after)
        engine.process_directory(args.input_dir, args.pattern)
        engine.close()

    elif args.command == "watch":
        engine = StreamEngine(args.game, args.db, args.model, delete_after=args.delete_after)
        engine.watch_directory(args.input_dir)
        engine.close()

    elif args.command == "stats":
        db = StreamDB(args.db)
        s = db.get_stats(args.game)
        if s:
            print(json.dumps(s, indent=2, ensure_ascii=False))
        else:
            print("No stats found")
        db.close()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
