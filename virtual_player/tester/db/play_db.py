"""
Human Play Database — CRUD + Pattern Learning
==============================================
인간 플레이 데이터(이미지 + 터치 JSON)를 구조화하고,
AI Tester가 활용할 수 있는 행동 패턴으로 변환.

핵심 흐름:
  1. ingest_session_log() — ClickCapture JSONL → DB 적재
  2. extract_patterns()   — 세션 데이터 → 행동 패턴 추출
  3. find_best_action()   — 현재 상태 → 가장 적합한 행동 반환
  4. update_from_result()  — AI 실행 결과로 패턴 confidence 갱신
"""

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class PlayDB:
    """인간 플레이 데이터베이스 관리자."""

    def __init__(self, db_path="play_data.db"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()

    def _init_schema(self):
        if SCHEMA_PATH.exists():
            with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
                self.conn.executescript(f.read())
            self.conn.commit()

    def close(self):
        self.conn.close()

    # ══════════════════════════════════════════════════════════
    #  1. 데이터 적재 — ClickCapture JSONL → DB
    # ══════════════════════════════════════════════════════════

    def ingest_session_log(self, jsonl_path, game_id, device_id="default",
                           frames_dir=None, progress_cb=None):
        """ClickCapture의 session_log.jsonl을 DB에 적재.

        Args:
            jsonl_path: session_log.jsonl 경로
            game_id: 게임 식별자
            device_id: 디바이스 ID
            frames_dir: 스크린샷 폴더 (None이면 jsonl과 같은 폴더)
            progress_cb: fn(current, total, msg) 콜백

        Returns:
            dict: {sessions: int, turns: int, actions: int}
        """
        jsonl_path = Path(jsonl_path)
        if frames_dir is None:
            frames_dir = jsonl_path.parent

        # 디바이스/게임 등록
        self._ensure_device(device_id)
        self._ensure_game(game_id)

        # JSONL 읽기
        events = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))

        if not events:
            return {"sessions": 0, "turns": 0, "actions": 0}

        # 에피소드 분할 (episode_id 기준 또는 시간 gap)
        episodes = self._split_episodes(events)

        total_sessions = 0
        total_turns = 0
        total_actions = 0

        for ep_idx, episode in enumerate(episodes):
            session_id = str(uuid.uuid4())
            started = episode[0].get("timestamp", datetime.now().isoformat())
            ended = episode[-1].get("timestamp", started)

            # 세션 생성
            self.conn.execute("""
                INSERT INTO session (session_id, device_id, game_id, player_type,
                                     started_at, ended_at, total_taps, source_file, source_device)
                VALUES (?, ?, ?, 'human', ?, ?, ?, ?, ?)
            """, (session_id, device_id, game_id, started, ended,
                  len(episode), str(jsonl_path), device_id))

            # 각 이벤트 → 턴 + 액션
            for i, evt in enumerate(episode):
                turn_id = str(uuid.uuid4())
                action_id = str(uuid.uuid4())

                screenshot_before = evt.get("file")
                screenshot_after = evt.get("after_file")

                # 스크린샷 → 상태 해시
                state_hash = None
                if screenshot_before and frames_dir:
                    img_path = frames_dir / screenshot_before
                    if img_path.exists():
                        state_hash = self._compute_image_hash(img_path)

                # 이미지 변화량
                delta = evt.get("delta_from_prev", 0)

                self.conn.execute("""
                    INSERT INTO turn (turn_id, session_id, turn_number, timestamp,
                                      screenshot_before, screenshot_after, state_hash,
                                      decision_source, delta_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'human', ?)
                """, (turn_id, session_id, i + 1,
                      evt.get("timestamp", started),
                      screenshot_before, screenshot_after,
                      state_hash, delta))

                # 액션
                norm_x = evt.get("norm_x", evt.get("x", 0) / 1080)
                norm_y = evt.get("norm_y", evt.get("y", 0) / 1920)

                self.conn.execute("""
                    INSERT INTO action (action_id, turn_id, action_index, type,
                                        x, y, end_x, end_y, duration_ms, timestamp)
                    VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?, ?)
                """, (action_id, turn_id, evt.get("action", "tap"),
                      norm_x, norm_y,
                      evt.get("norm_end_x"), evt.get("norm_end_y"),
                      evt.get("duration_ms"), evt.get("timestamp", started)))

                total_turns += 1
                total_actions += 1

            total_sessions += 1

            if progress_cb:
                progress_cb(ep_idx + 1, len(episodes),
                            f"세션 {ep_idx + 1}/{len(episodes)}")

        self.conn.commit()

        # 디바이스 통계 업데이트
        self.conn.execute("""
            UPDATE device SET total_sessions = total_sessions + ?, last_sync_at = ?
            WHERE device_id = ?
        """, (total_sessions, datetime.now().isoformat(), device_id))
        self.conn.commit()

        return {"sessions": total_sessions, "turns": total_turns, "actions": total_actions}

    def _split_episodes(self, events, gap_seconds=30):
        """이벤트를 에피소드로 분할 (episode_id 또는 시간 gap)."""
        if not events:
            return []

        # episode_id가 있으면 그걸로 분할
        if "episode_id" in events[0]:
            episodes = {}
            for evt in events:
                eid = evt.get("episode_id", "default")
                if eid not in episodes:
                    episodes[eid] = []
                episodes[eid].append(evt)
            return list(episodes.values())

        # 없으면 시간 gap으로 분할
        episodes = [[events[0]]]
        for i in range(1, len(events)):
            try:
                t1 = datetime.fromisoformat(events[i - 1].get("timestamp", ""))
                t2 = datetime.fromisoformat(events[i].get("timestamp", ""))
                gap = (t2 - t1).total_seconds()
            except (ValueError, TypeError):
                gap = 0

            if gap > gap_seconds:
                episodes.append([])
            episodes[-1].append(events[i])

        return [ep for ep in episodes if ep]

    # ══════════════════════════════════════════════════════════
    #  2. 패턴 추출 — 세션 → 행동 패턴
    # ══════════════════════════════════════════════════════════

    def extract_patterns(self, game_id=None, min_occurrences=2):
        """DB의 턴 데이터에서 행동 패턴을 추출/업데이트.

        동일한 state_hash에서 동일한 행동이 반복되면 → 패턴으로 등록.
        """
        query = """
            SELECT t.state_hash, t.screen_type, t.session_id,
                   a.type as action_type, a.x, a.y,
                   t.delta_score, s.outcome, s.game_id
            FROM turn t
            JOIN action a ON a.turn_id = t.turn_id AND a.action_index = 0
            JOIN session s ON s.session_id = t.session_id
            WHERE t.state_hash IS NOT NULL
              AND s.player_type = 'human'
        """
        params = []
        if game_id:
            query += " AND s.game_id = ?"
            params.append(game_id)

        rows = self.conn.execute(query, params).fetchall()

        # state_hash + 행동 좌표(양자화) → 그룹화
        pattern_groups = {}
        for row in rows:
            # 좌표를 5% 단위로 양자화 (비슷한 위치를 같은 패턴으로)
            qx = round(row["x"] * 20) / 20  # 0.05 단위
            qy = round(row["y"] * 20) / 20
            key = (row["game_id"], row["state_hash"],
                   row["action_type"], qx, qy)

            if key not in pattern_groups:
                pattern_groups[key] = {
                    "count": 0, "success": 0, "deltas": [],
                    "screen_type": row["screen_type"],
                }
            pg = pattern_groups[key]
            pg["count"] += 1
            if row["outcome"] == "clear":
                pg["success"] += 1
            if row["delta_score"]:
                pg["deltas"].append(row["delta_score"])

        # 패턴 DB에 UPSERT
        inserted = 0
        updated = 0
        for (gid, shash, atype, ax, ay), stats in pattern_groups.items():
            if stats["count"] < min_occurrences:
                continue

            confidence = min(0.9, 0.3 + (stats["success"] / max(stats["count"], 1)) * 0.6)
            avg_delta = np.mean(stats["deltas"]) if stats["deltas"] else 0

            existing = self.conn.execute("""
                SELECT pattern_id, times_seen, times_success FROM pattern
                WHERE game_id = ? AND state_hash = ? AND action_type = ?
                  AND ABS(action_x - ?) < 0.03 AND ABS(action_y - ?) < 0.03
            """, (gid, shash, atype, ax, ay)).fetchone()

            if existing:
                self.conn.execute("""
                    UPDATE pattern SET
                        times_seen = times_seen + ?,
                        times_success = times_success + ?,
                        avg_delta_score = ?,
                        confidence = ?,
                        last_seen_at = CURRENT_TIMESTAMP
                    WHERE pattern_id = ?
                """, (stats["count"], stats["success"], avg_delta,
                      confidence, existing["pattern_id"]))
                updated += 1
            else:
                self.conn.execute("""
                    INSERT INTO pattern (pattern_id, game_id, state_hash, screen_type,
                                         action_type, action_x, action_y,
                                         times_seen, times_success, avg_delta_score,
                                         confidence, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'human')
                """, (str(uuid.uuid4()), gid, shash, stats["screen_type"],
                      atype, ax, ay, stats["count"], stats["success"],
                      avg_delta, confidence))
                inserted += 1

        self.conn.commit()
        return {"inserted": inserted, "updated": updated, "total_groups": len(pattern_groups)}

    # ══════════════════════════════════════════════════════════
    #  3. 행동 검색 — AI가 현재 상태에서 무엇을 할지
    # ══════════════════════════════════════════════════════════

    def find_best_action(self, state_hash, game_id=None, screen_type=None,
                         min_confidence=0.3, limit=5):
        """현재 상태에서 가장 적합한 행동 패턴을 검색.

        Args:
            state_hash: 현재 화면의 이미지 해시
            game_id: 게임 필터
            screen_type: 화면 유형 필터
            min_confidence: 최소 신뢰도
            limit: 반환할 최대 패턴 수

        Returns:
            list[dict]: 최적 행동 후보 목록 (confidence 내림차순)
        """
        query = """
            SELECT pattern_id, action_type, action_x, action_y, action_detail,
                   confidence, times_seen, times_success, avg_delta_score, source
            FROM pattern
            WHERE state_hash = ?
              AND confidence >= ?
        """
        params = [state_hash, min_confidence]

        if game_id:
            query += " AND (game_id = ? OR game_id IS NULL)"
            params.append(game_id)
        if screen_type:
            query += " AND (screen_type = ? OR screen_type IS NULL)"
            params.append(screen_type)

        query += " ORDER BY confidence DESC, times_success DESC LIMIT ?"
        params.append(limit)

        rows = self.conn.execute(query, params).fetchall()

        return [{
            "action_type": r["action_type"],
            "x": r["action_x"],
            "y": r["action_y"],
            "detail": r["action_detail"],
            "confidence": r["confidence"],
            "success_rate": (r["times_success"] / r["times_seen"] * 100
                             if r["times_seen"] > 0 else 0),
            "times_seen": r["times_seen"],
            "source": r["source"],
        } for r in rows]

    def find_similar_actions(self, image_path, game_id=None, top_k=10):
        """이미지 유사도 기반 행동 검색 (해시 매칭 실패 시 fallback).

        정확한 해시 매칭이 안 되면, hamming distance가 가까운 패턴을 검색.
        """
        target_hash = self._compute_image_hash(image_path)

        # 1차: 정확 매칭
        exact = self.find_best_action(target_hash, game_id)
        if exact:
            return exact

        # 2차: 유사 해시 검색 (hamming distance)
        all_patterns = self.conn.execute("""
            SELECT pattern_id, state_hash, action_type, action_x, action_y,
                   confidence, times_seen, times_success, source
            FROM pattern
            WHERE game_id = ? AND confidence >= 0.3
            ORDER BY confidence DESC
            LIMIT 1000
        """, (game_id,)).fetchall()

        # Hamming distance 계산
        candidates = []
        for p in all_patterns:
            if p["state_hash"] and len(p["state_hash"]) == len(target_hash):
                dist = sum(c1 != c2 for c1, c2 in zip(target_hash, p["state_hash"]))
                candidates.append((dist, p))

        candidates.sort(key=lambda x: x[0])

        return [{
            "action_type": p["action_type"],
            "x": p["action_x"],
            "y": p["action_y"],
            "confidence": p["confidence"] * max(0, 1 - dist / 256),  # 거리에 따라 감쇠
            "hamming_distance": dist,
            "times_seen": p["times_seen"],
            "source": f"{p['source']}(fuzzy)",
        } for dist, p in candidates[:top_k] if dist < 50]  # threshold

    # ══════════════════════════════════════════════════════════
    #  4. 결과 피드백 — AI 실행 후 패턴 갱신
    # ══════════════════════════════════════════════════════════

    def update_from_result(self, state_hash, action_type, action_x, action_y,
                           success, game_id=None):
        """AI 실행 결과로 패턴 confidence를 업데이트."""
        row = self.conn.execute("""
            SELECT pattern_id, confidence, times_seen, times_success FROM pattern
            WHERE state_hash = ? AND action_type = ?
              AND ABS(action_x - ?) < 0.05 AND ABS(action_y - ?) < 0.05
              AND (game_id = ? OR game_id IS NULL)
            LIMIT 1
        """, (state_hash, action_type, action_x, action_y, game_id)).fetchone()

        if row:
            new_seen = row["times_seen"] + 1
            new_success = row["times_success"] + (1 if success else 0)
            new_conf = min(0.95, row["confidence"] + (0.03 if success else -0.05))
            new_conf = max(0.05, new_conf)

            self.conn.execute("""
                UPDATE pattern SET
                    times_seen = ?,
                    times_success = ?,
                    confidence = ?,
                    last_seen_at = CURRENT_TIMESTAMP
                WHERE pattern_id = ?
            """, (new_seen, new_success, new_conf, row["pattern_id"]))
            self.conn.commit()
            return True
        return False

    # ══════════════════════════════════════════════════════════
    #  유틸리티
    # ══════════════════════════════════════════════════════════

    def _ensure_device(self, device_id):
        self.conn.execute(
            "INSERT OR IGNORE INTO device (device_id) VALUES (?)", (device_id,))

    def _ensure_game(self, game_id):
        self.conn.execute(
            "INSERT OR IGNORE INTO game_profile (game_id) VALUES (?)", (game_id,))

    @staticmethod
    def _compute_image_hash(img_path, hash_size=16):
        """평균 해시 — 빠르고 회전/크기 불변."""
        img = Image.open(img_path).convert("L").resize(
            (hash_size, hash_size), Image.LANCZOS)
        arr = np.array(img)
        return "".join("1" if b else "0" for b in (arr > arr.mean()).flatten())

    def get_stats(self, game_id=None):
        """DB 통계 반환."""
        where = "WHERE game_id = ?" if game_id else ""
        params = (game_id,) if game_id else ()

        sessions = self.conn.execute(
            f"SELECT COUNT(*) FROM session {where}", params).fetchone()[0]
        turns = self.conn.execute(
            f"""SELECT COUNT(*) FROM turn t JOIN session s ON s.session_id = t.session_id
                {where}""", params).fetchone()[0]
        patterns = self.conn.execute(
            f"SELECT COUNT(*) FROM pattern {where.replace('game_id', 'game_id')}", params
        ).fetchone()[0] if game_id else self.conn.execute(
            "SELECT COUNT(*) FROM pattern").fetchone()[0]
        devices = self.conn.execute("SELECT COUNT(*) FROM device").fetchone()[0]

        return {
            "sessions": sessions,
            "turns": turns,
            "patterns": patterns,
            "devices": devices,
            "db_size_mb": round(self.db_path.stat().st_size / 1024 / 1024, 2)
                          if self.db_path.exists() else 0,
        }

    def cleanup_low_patterns(self, min_confidence=0.15, min_seen=3):
        """저성과 패턴 정리."""
        result = self.conn.execute("""
            DELETE FROM pattern
            WHERE confidence < ? OR (times_seen >= ? AND
                  CAST(times_success AS REAL) / times_seen < 0.1)
        """, (min_confidence, min_seen))
        self.conn.commit()
        return result.rowcount
