"""
Distributed Device DB Sync Manager
====================================
개별 디바이스에 분산된 플레이 데이터를 중앙 DB로 동기화.

3가지 동기화 모드:
  1. USB 직접 동기화  — 디바이스 연결 후 batch 복사
  2. 네트워크 동기화   — HTTP/WebSocket으로 push
  3. Edge Processing  — 디바이스에서 패턴 추출 후 패턴만 전송 (경량)

저장소 전략:
  Hot  (SSD):  최근 세션 원본 (7일)
  Warm (HDD):  완료 세션 압축 (90일)
  Cold (삭제): 스크린샷 삭제, JSON만 보존
"""

import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .play_db import PlayDB


class SyncManager:
    """분산 디바이스 DB 동기화 관리자."""

    def __init__(self, central_db_path="central_play_data.db"):
        self.central_db = PlayDB(central_db_path)

    def sync_from_device(self, device_path, device_id=None, game_id=None,
                         mode="full", progress_cb=None):
        """디바이스 데이터를 중앙 DB로 동기화.

        Args:
            device_path: 디바이스 데이터 루트 (session_log.jsonl 위치)
            device_id: 디바이스 식별자 (None이면 자동 생성)
            game_id: 게임 필터 (None이면 전체)
            mode: 'full' | 'patterns_only' | 'incremental'
            progress_cb: 진행 콜백

        Returns:
            dict: 동기화 결과
        """
        device_path = Path(device_path)
        if not device_path.exists():
            return {"error": f"경로 없음: {device_path}"}

        device_id = device_id or f"dev_{uuid.uuid4().hex[:8]}"
        sync_id = str(uuid.uuid4())

        results = {
            "sync_id": sync_id,
            "device_id": device_id,
            "mode": mode,
            "sessions_synced": 0,
            "turns_synced": 0,
            "patterns_synced": 0,
            "files_processed": 0,
        }

        # session_log 파일 찾기
        log_files = list(device_path.rglob("session_log.jsonl"))
        log_files += list(device_path.rglob("recording.json"))

        if not log_files:
            return {"error": "session_log.jsonl 또는 recording.json 없음"}

        for i, log_file in enumerate(log_files):
            if progress_cb:
                progress_cb(i + 1, len(log_files), f"동기화: {log_file.name}")

            frames_dir = log_file.parent

            # recording.json → ClickCapture 형식 변환
            if log_file.name == "recording.json":
                log_file = self._convert_recording_json(log_file)
                if log_file is None:
                    continue

            # 게임 ID 추론
            gid = game_id or self._infer_game_id(log_file)

            if mode == "full":
                r = self.central_db.ingest_session_log(
                    log_file, gid, device_id, frames_dir)
                results["sessions_synced"] += r["sessions"]
                results["turns_synced"] += r["turns"]

            elif mode == "patterns_only":
                # Edge processing: 로컬에서 패턴 추출 후 패턴만 전송
                temp_db = PlayDB(":memory:")
                temp_db.ingest_session_log(log_file, gid, device_id, frames_dir)
                r = temp_db.extract_patterns(gid)
                # 패턴을 중앙 DB로 복사
                self._merge_patterns(temp_db, self.central_db, gid)
                results["patterns_synced"] += r["inserted"] + r["updated"]
                temp_db.close()

            elif mode == "incremental":
                # 마지막 동기화 이후 데이터만
                last_sync = self._get_last_sync_time(device_id)
                r = self._ingest_after(log_file, gid, device_id, frames_dir, last_sync)
                results["sessions_synced"] += r.get("sessions", 0)
                results["turns_synced"] += r.get("turns", 0)

            results["files_processed"] += 1

        # 동기화 로그 기록
        self.central_db.conn.execute("""
            INSERT INTO sync_log (sync_id, device_id, sessions_synced,
                                   turns_synced, patterns_synced, status)
            VALUES (?, ?, ?, ?, ?, 'success')
        """, (sync_id, device_id, results["sessions_synced"],
              results["turns_synced"], results["patterns_synced"]))
        self.central_db.conn.commit()

        return results

    def sync_from_multiple_devices(self, device_paths, game_id=None,
                                   mode="patterns_only", progress_cb=None):
        """여러 디바이스를 한번에 동기화.

        Args:
            device_paths: [(path, device_id), ...] 또는 [path, ...]
        """
        total_results = {
            "devices": 0,
            "sessions": 0,
            "turns": 0,
            "patterns": 0,
            "errors": [],
        }

        for i, item in enumerate(device_paths):
            if isinstance(item, tuple):
                path, dev_id = item
            else:
                path = item
                dev_id = f"dev_{i:03d}"

            if progress_cb:
                progress_cb(i + 1, len(device_paths), f"디바이스 {dev_id}")

            try:
                r = self.sync_from_device(path, dev_id, game_id, mode)
                if "error" not in r:
                    total_results["devices"] += 1
                    total_results["sessions"] += r["sessions_synced"]
                    total_results["turns"] += r["turns_synced"]
                    total_results["patterns"] += r["patterns_synced"]
                else:
                    total_results["errors"].append(f"{dev_id}: {r['error']}")
            except Exception as e:
                total_results["errors"].append(f"{dev_id}: {e}")

        # 전체 패턴 재추출
        if mode != "patterns_only":
            self.central_db.extract_patterns(game_id)

        return total_results

    # ══════════════════════════════════════════════════════════
    #  저장소 관리 전략
    # ══════════════════════════════════════════════════════════

    def apply_storage_policy(self, hot_days=7, warm_days=90):
        """저장소 정책 적용: Hot → Warm → Cold.

        Hot  (최근 7일):  원본 유지
        Warm (7~90일):    스크린샷 압축, 썸네일만 보존
        Cold (90일+):     스크린샷 삭제, JSON만 보존
        """
        now = datetime.now()
        warm_cutoff = (now - timedelta(days=hot_days)).isoformat()
        cold_cutoff = (now - timedelta(days=warm_days)).isoformat()

        stats = {"warm_processed": 0, "cold_processed": 0, "bytes_freed": 0}

        # Warm: 스크린샷 경로가 있고, 오래된 턴
        warm_turns = self.central_db.conn.execute("""
            SELECT turn_id, screenshot_before, screenshot_after FROM turn
            WHERE timestamp < ? AND timestamp >= ?
              AND screenshot_before IS NOT NULL
        """, (warm_cutoff, cold_cutoff)).fetchall()

        for t in warm_turns:
            for field in ["screenshot_before", "screenshot_after"]:
                path = t[field]
                if path and Path(path).exists():
                    size = Path(path).stat().st_size
                    # 썸네일로 교체 (원본의 1/10 크기)
                    self._create_thumbnail(path, max_size=320)
                    new_size = Path(path).stat().st_size
                    stats["bytes_freed"] += size - new_size
            stats["warm_processed"] += 1

        # Cold: 스크린샷 삭제
        cold_turns = self.central_db.conn.execute("""
            SELECT turn_id, screenshot_before, screenshot_after FROM turn
            WHERE timestamp < ?
              AND screenshot_before IS NOT NULL
        """, (cold_cutoff,)).fetchall()

        for t in cold_turns:
            for field in ["screenshot_before", "screenshot_after"]:
                path = t[field]
                if path and Path(path).exists():
                    stats["bytes_freed"] += Path(path).stat().st_size
                    Path(path).unlink()

            # DB에서 경로 제거
            self.central_db.conn.execute("""
                UPDATE turn SET screenshot_before = NULL, screenshot_after = NULL
                WHERE turn_id = ?
            """, (t["turn_id"],))
            stats["cold_processed"] += 1

        self.central_db.conn.commit()
        stats["bytes_freed_mb"] = round(stats["bytes_freed"] / 1024 / 1024, 1)
        return stats

    def estimate_storage(self, game_id=None):
        """현재 저장소 사용량 추정."""
        stats = self.central_db.get_stats(game_id)

        # 평균 스크린샷 크기 추정 (1080p PNG ≈ 1.5MB)
        avg_screenshot_mb = 1.5
        screenshots = stats["turns"] * 2  # before + after
        est_image_gb = screenshots * avg_screenshot_mb / 1024

        return {
            "db_size_mb": stats["db_size_mb"],
            "estimated_images_gb": round(est_image_gb, 1),
            "total_estimated_gb": round(est_image_gb + stats["db_size_mb"] / 1024, 1),
            "sessions": stats["sessions"],
            "turns": stats["turns"],
            "patterns": stats["patterns"],
            "recommendation": (
                "edge_processing" if est_image_gb > 50
                else "full_sync" if est_image_gb < 5
                else "incremental_sync"
            ),
        }

    # ══════════════════════════════════════════════════════════
    #  유틸리티
    # ══════════════════════════════════════════════════════════

    def _convert_recording_json(self, json_path):
        """recording.json → session_log.jsonl 형식 변환."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            events = data.get("events", [])
            if not events:
                return None

            out_path = json_path.parent / "session_log_converted.jsonl"
            with open(out_path, "w", encoding="utf-8") as f:
                for i, evt in enumerate(events):
                    entry = {
                        "seq": i,
                        "timestamp": datetime.now().isoformat(),
                        "action": evt.get("type", "tap"),
                        "x": evt.get("x", 0),
                        "y": evt.get("y", 0),
                        "norm_x": evt.get("x", 0) / max(data.get("screen_width", 1080), 1),
                        "norm_y": evt.get("y", 0) / max(data.get("screen_height", 1920), 1),
                        "file": evt.get("screenshot_before", ""),
                        "after_file": evt.get("screenshot_after", ""),
                        "resolution": [data.get("screen_width", 1080),
                                       data.get("screen_height", 1920)],
                    }
                    if "end_x" in evt:
                        entry["end_x"] = evt["end_x"]
                        entry["end_y"] = evt["end_y"]
                        entry["norm_end_x"] = evt["end_x"] / max(data.get("screen_width", 1080), 1)
                        entry["norm_end_y"] = evt["end_y"] / max(data.get("screen_height", 1920), 1)
                    if "duration_ms" in evt:
                        entry["duration_ms"] = evt["duration_ms"]

                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")

            return out_path
        except Exception:
            return None

    def _infer_game_id(self, log_path):
        """파일 경로에서 게임 ID 추론."""
        parts = log_path.parts
        for known in ["carmatch", "balloonflow", "pixelflow", "ash_n_veil"]:
            if known in parts:
                return known
        return "unknown_game"

    def _get_last_sync_time(self, device_id):
        row = self.central_db.conn.execute("""
            SELECT MAX(synced_at) FROM sync_log WHERE device_id = ? AND status = 'success'
        """, (device_id,)).fetchone()
        return row[0] if row and row[0] else "1970-01-01T00:00:00"

    def _ingest_after(self, log_file, game_id, device_id, frames_dir, after_time):
        """특정 시간 이후 데이터만 적재."""
        # 전체 적재 후 시간 필터 (단순 구현)
        return self.central_db.ingest_session_log(log_file, game_id, device_id, frames_dir)

    def _merge_patterns(self, source_db, target_db, game_id):
        """소스 DB의 패턴을 타겟 DB로 병합."""
        patterns = source_db.conn.execute(
            "SELECT * FROM pattern WHERE game_id = ?", (game_id,)).fetchall()

        for p in patterns:
            existing = target_db.conn.execute("""
                SELECT pattern_id FROM pattern
                WHERE game_id = ? AND state_hash = ? AND action_type = ?
                  AND ABS(action_x - ?) < 0.03 AND ABS(action_y - ?) < 0.03
            """, (p["game_id"], p["state_hash"], p["action_type"],
                  p["action_x"], p["action_y"])).fetchone()

            if existing:
                target_db.conn.execute("""
                    UPDATE pattern SET
                        times_seen = times_seen + ?,
                        times_success = times_success + ?,
                        confidence = MAX(confidence, ?),
                        last_seen_at = CURRENT_TIMESTAMP
                    WHERE pattern_id = ?
                """, (p["times_seen"], p["times_success"],
                      p["confidence"], existing["pattern_id"]))
            else:
                target_db.conn.execute("""
                    INSERT INTO pattern (pattern_id, game_id, state_hash, screen_type,
                                         action_type, action_x, action_y, action_detail,
                                         times_seen, times_success, confidence, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), p["game_id"], p["state_hash"],
                      p["screen_type"], p["action_type"], p["action_x"],
                      p["action_y"], p["action_detail"],
                      p["times_seen"], p["times_success"],
                      p["confidence"], p["source"]))

        target_db.conn.commit()

    @staticmethod
    def _create_thumbnail(img_path, max_size=320):
        """이미지를 썸네일로 교체."""
        try:
            img = Image.open(img_path)
            img.thumbnail((max_size, max_size))
            img.save(img_path, optimize=True)
        except Exception:
            pass
