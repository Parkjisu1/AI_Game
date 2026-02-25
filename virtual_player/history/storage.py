"""
History Storage
================
SQLite를 사용한 게임 플레이 이력 저장.
sessions, actions, touch_events 3개 테이블.
"""

import sqlite3
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from ..config import DB_DIR, HISTORY_DB_NAME


class HistoryStorage:
    """SQLite 기반 이력 저장소."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (DB_DIR / HISTORY_DB_NAME)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_tables(self) -> None:
        cursor = self._conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                game_id TEXT NOT NULL,
                persona_name TEXT NOT NULL,
                pattern_name TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL,
                duration_seconds REAL,
                action_count INTEGER DEFAULT 0,
                final_score REAL DEFAULT 0,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                timestamp REAL NOT NULL,
                action_name TEXT NOT NULL,
                action_description TEXT DEFAULT '',
                confidence REAL DEFAULT 1.0,
                game_score REAL DEFAULT 0,
                game_state_summary TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );

            CREATE TABLE IF NOT EXISTS touch_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                x REAL DEFAULT 0,
                y REAL DEFAULT 0,
                end_x REAL DEFAULT 0,
                end_y REAL DEFAULT 0,
                duration REAL DEFAULT 0,
                key_name TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (action_id) REFERENCES actions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_actions_session ON actions(session_id);
            CREATE INDEX IF NOT EXISTS idx_touch_action ON touch_events(action_id);
        """)
        self._conn.commit()

    # -- Session CRUD --

    def insert_session(self, session_id: str, game_id: str, persona_name: str,
                       pattern_name: str, start_time: float,
                       metadata: Optional[Dict] = None) -> None:
        self._conn.execute(
            "INSERT INTO sessions (session_id, game_id, persona_name, pattern_name, start_time, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, game_id, persona_name, pattern_name, start_time,
             json.dumps(metadata or {})),
        )
        self._conn.commit()

    def update_session(self, session_id: str, end_time: float,
                       duration_seconds: float, action_count: int,
                       final_score: float) -> None:
        self._conn.execute(
            "UPDATE sessions SET end_time=?, duration_seconds=?, action_count=?, final_score=? "
            "WHERE session_id=?",
            (end_time, duration_seconds, action_count, final_score, session_id),
        )
        self._conn.commit()

    # -- Action CRUD --

    def insert_action(self, session_id: str, timestamp: float, action_name: str,
                      action_description: str = "", confidence: float = 1.0,
                      game_score: float = 0, game_state_summary: str = "",
                      metadata: Optional[Dict] = None) -> int:
        cursor = self._conn.execute(
            "INSERT INTO actions (session_id, timestamp, action_name, action_description, "
            "confidence, game_score, game_state_summary, metadata) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, timestamp, action_name, action_description, confidence,
             game_score, game_state_summary, json.dumps(metadata or {})),
        )
        self._conn.commit()
        return cursor.lastrowid

    # -- Touch event CRUD --

    def insert_touch_event(self, action_id: int, action_type: str,
                           x: float = 0, y: float = 0,
                           end_x: float = 0, end_y: float = 0,
                           duration: float = 0, key_name: str = "",
                           metadata: Optional[Dict] = None) -> None:
        self._conn.execute(
            "INSERT INTO touch_events (action_id, action_type, x, y, end_x, end_y, "
            "duration, key_name, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (action_id, action_type, x, y, end_x, end_y, duration, key_name,
             json.dumps(metadata or {})),
        )
        self._conn.commit()

    # -- Query methods --

    def get_sessions(self, game_id: Optional[str] = None) -> List[Dict]:
        query = "SELECT * FROM sessions"
        params = []
        if game_id:
            query += " WHERE game_id = ?"
            params.append(game_id)
        query += " ORDER BY start_time DESC"
        rows = self._conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def get_actions(self, session_id: str) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM actions WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_touch_events(self, action_id: int) -> List[Dict]:
        rows = self._conn.execute(
            "SELECT * FROM touch_events WHERE action_id = ? ORDER BY id",
            (action_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_action_summary(self, game_id: Optional[str] = None) -> Dict[str, int]:
        """액션 이름별 횟수 집계."""
        query = "SELECT a.action_name, COUNT(*) as cnt FROM actions a"
        params = []
        if game_id:
            query += " JOIN sessions s ON a.session_id = s.session_id WHERE s.game_id = ?"
            params.append(game_id)
        query += " GROUP BY a.action_name ORDER BY cnt DESC"
        rows = self._conn.execute(query, params).fetchall()
        return {row["action_name"]: row["cnt"] for row in rows}

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
