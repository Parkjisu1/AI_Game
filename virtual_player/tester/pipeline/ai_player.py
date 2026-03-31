"""
AI Player — Human Play DB 기반 자율 플레이 엔진
================================================
Black-box 접근: ADB 스크린샷 → 상태 인식 → DB 패턴 매칭 → 터치 실행

핵심 흐름:
  1. ADB 스크린샷 캡처
  2. YOLO 화면 분류 (gameplay / lobby / popup / ...)
  3. 이미지 해시 → DB에서 인간 행동 패턴 검색
  4. 패턴 있으면 → 인간처럼 행동
     패턴 없으면 → Lookahead 시뮬레이션 또는 탐색
  5. ADB 터치 실행
  6. 결과 확인 → DB 피드백
"""

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

# 상대 경로 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tester.db.play_db import PlayDB

YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    pass


class ADBController:
    """ADB를 통한 디바이스 제어."""

    def __init__(self, adb_path=None, device=None):
        self.adb_path = adb_path or self._find_adb()
        self.device = device
        self.screen_size = (1080, 1920)
        self._detect_screen_size()

    def _find_adb(self):
        """ADB 경로 자동 탐색."""
        candidates = [
            r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
            r"C:\LDPlayer\LDPlayer9\adb.exe",
            r"C:\Program Files\Nox\bin\nox_adb.exe",
            "adb",
        ]
        for c in candidates:
            if Path(c).exists() or c == "adb":
                return c
        return "adb"

    def _cmd(self, *args):
        cmd = [self.adb_path]
        if self.device:
            cmd += ["-s", self.device]
        cmd += list(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=10)

    def _detect_screen_size(self):
        try:
            r = self._cmd("shell", "wm", "size")
            if r.returncode == 0 and "Physical size" in r.stdout:
                parts = r.stdout.strip().split(":")[-1].strip().split("x")
                self.screen_size = (int(parts[0]), int(parts[1]))
        except Exception:
            pass

    def screenshot(self, save_path):
        """스크린샷 캡처 → 로컬 파일 저장."""
        tmp = "/sdcard/screen_ai.png"
        self._cmd("shell", "screencap", "-p", tmp)
        self._cmd("pull", tmp, str(save_path))
        self._cmd("shell", "rm", tmp)
        return Path(save_path).exists()

    def tap(self, x, y):
        """절대 좌표로 탭."""
        self._cmd("shell", "input", "tap", str(int(x)), str(int(y)))

    def tap_normalized(self, nx, ny):
        """정규화 좌표 [0-1]로 탭."""
        x = int(nx * self.screen_size[0])
        y = int(ny * self.screen_size[1])
        self.tap(x, y)

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        self._cmd("shell", "input", "swipe",
                  str(int(x1)), str(int(y1)),
                  str(int(x2)), str(int(y2)),
                  str(duration_ms))

    def swipe_normalized(self, nx1, ny1, nx2, ny2, duration_ms=300):
        w, h = self.screen_size
        self.swipe(nx1 * w, ny1 * h, nx2 * w, ny2 * h, duration_ms)

    def is_connected(self):
        r = self._cmd("devices")
        return r.returncode == 0 and "device" in r.stdout


class AIPlayer:
    """Human Play DB 기반 AI 플레이어."""

    def __init__(self, db_path, game_id, yolo_model_path=None,
                 adb_path=None, adb_device=None, temp_dir=None):
        self.db = PlayDB(db_path)
        self.game_id = game_id
        self.adb = ADBController(adb_path, adb_device)
        self.temp_dir = Path(temp_dir or "temp_ai_player")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # YOLO 모델 (화면 분류)
        self.yolo_model = None
        if yolo_model_path and YOLO_AVAILABLE and Path(yolo_model_path).exists():
            self.yolo_model = YOLO(str(yolo_model_path))

        # 세션 상태
        self.session_id = None
        self.turn_count = 0
        self.consecutive_no_change = 0
        self.max_no_change = 5  # 5연속 변화 없으면 → 탐색 모드

        # 통계
        self.stats = {
            "total_turns": 0,
            "pattern_hits": 0,
            "pattern_misses": 0,
            "exploration_turns": 0,
        }

    def start_session(self):
        """새 플레이 세션 시작."""
        self.session_id = str(uuid.uuid4())
        self.turn_count = 0
        self.consecutive_no_change = 0

        self.db.conn.execute("""
            INSERT INTO session (session_id, game_id, player_type, started_at)
            VALUES (?, ?, 'ai_v3', ?)
        """, (self.session_id, self.game_id, datetime.now().isoformat()))
        self.db.conn.commit()

        return self.session_id

    def end_session(self, outcome="abandon"):
        """세션 종료."""
        if self.session_id:
            self.db.conn.execute("""
                UPDATE session SET ended_at = ?, outcome = ?, total_turns = ?
                WHERE session_id = ?
            """, (datetime.now().isoformat(), outcome,
                  self.turn_count, self.session_id))
            self.db.conn.commit()
        self.session_id = None

    def play_one_turn(self):
        """1턴 실행: 캡처 → 인식 → 결정 → 실행 → 검증.

        Returns:
            dict: {
                "action": 실행한 행동,
                "source": "pattern" | "exploration" | "rule",
                "result": "match" | "move" | "no_change" | "screen_change",
                "screen_type": 화면 유형,
            }
        """
        self.turn_count += 1
        turn_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        # 1. 스크린샷 캡처
        before_path = self.temp_dir / f"turn_{self.turn_count:04d}_before.png"
        if not self.adb.screenshot(before_path):
            return {"error": "screenshot_failed"}

        # 2. 화면 분류 (YOLO)
        screen_type = self._classify_screen(before_path)

        # 3. 상태 해시 계산
        state_hash = PlayDB._compute_image_hash(before_path)

        # 4. 행동 결정 (3단계 하이브리드)
        action = self._decide_action(state_hash, screen_type, before_path)

        # 5. 실행
        self._execute_action(action)

        # 6. 결과 확인
        time.sleep(0.5)  # 렌더링 대기
        after_path = self.temp_dir / f"turn_{self.turn_count:04d}_after.png"
        self.adb.screenshot(after_path)

        # 7. 변화량 측정
        delta = self._compute_delta(before_path, after_path)
        result = self._classify_result(delta, screen_type)

        # 8. DB 기록
        self._record_turn(turn_id, timestamp, state_hash, screen_type,
                          action, result, delta, before_path, after_path)

        # 9. 패턴 피드백
        if action.get("source") == "pattern":
            self.db.update_from_result(
                state_hash, action["type"],
                action.get("x", 0), action.get("y", 0),
                success=(result in ("match", "screen_change")),
                game_id=self.game_id
            )

        # 10. 연속 무변화 추적
        if result == "no_change":
            self.consecutive_no_change += 1
        else:
            self.consecutive_no_change = 0

        self.stats["total_turns"] += 1

        return {
            "turn": self.turn_count,
            "action": action,
            "result": result,
            "screen_type": screen_type,
            "delta": round(delta, 4),
        }

    def play_level(self, max_turns=200, timeout_sec=300):
        """1레벨을 자동으로 플레이.

        Returns:
            dict: 세션 결과
        """
        self.start_session()
        start_time = time.time()
        turns_log = []

        try:
            for _ in range(max_turns):
                if time.time() - start_time > timeout_sec:
                    self.end_session("timeout")
                    break

                result = self.play_one_turn()
                turns_log.append(result)

                if result.get("error"):
                    break

                # 화면 전환 감지 → 레벨 종료 판단
                if result.get("screen_type") in ("win", "fail", "fail_result"):
                    outcome = "clear" if result["screen_type"] == "win" else "fail"
                    self.end_session(outcome)
                    return {
                        "outcome": outcome,
                        "turns": self.turn_count,
                        "stats": self.stats.copy(),
                        "duration": round(time.time() - start_time, 1),
                    }

                # 너무 오래 변화 없으면 → stuck
                if self.consecutive_no_change >= 10:
                    self.end_session("stuck")
                    return {
                        "outcome": "stuck",
                        "turns": self.turn_count,
                        "stats": self.stats.copy(),
                    }

        except KeyboardInterrupt:
            self.end_session("interrupted")
        except Exception as e:
            self.end_session("crash")
            return {"outcome": "crash", "error": str(e)}

        self.end_session("max_turns")
        return {
            "outcome": "max_turns",
            "turns": self.turn_count,
            "stats": self.stats.copy(),
        }

    # ══════════════════════════════════════════════════════════
    #  내부 메서드
    # ══════════════════════════════════════════════════════════

    def _classify_screen(self, img_path):
        """YOLO로 화면 유형 분류."""
        if self.yolo_model:
            preds = self.yolo_model.predict(str(img_path), verbose=False)
            if preds and preds[0].probs is not None:
                return self.yolo_model.names[int(preds[0].probs.top1)]
        return "unknown"

    def _decide_action(self, state_hash, screen_type, img_path):
        """3단계 하이브리드 의사결정.

        Stage 1: 안전 규칙 (Playbook)
        Stage 2: DB 패턴 매칭
        Stage 3: 탐색 (랜덤 또는 Lookahead)
        """
        # Stage 1: 비-gameplay 화면 → 고정 규칙
        if screen_type != "gameplay" and screen_type != "unknown":
            action = self._handle_non_gameplay(screen_type)
            if action:
                return {**action, "source": "rule", "type": "tap"}

        # Stage 2: DB 패턴 매칭
        patterns = self.db.find_best_action(
            state_hash, self.game_id, screen_type)

        if patterns:
            best = patterns[0]
            self.stats["pattern_hits"] += 1
            return {
                "type": best["action_type"],
                "x": best["x"],
                "y": best["y"],
                "source": "pattern",
                "confidence": best["confidence"],
            }

        # Stage 2.5: 유사 이미지 검색 (fuzzy)
        if self.consecutive_no_change < 3:
            similar = self.db.find_similar_actions(img_path, self.game_id, top_k=3)
            if similar:
                best = similar[0]
                self.stats["pattern_hits"] += 1
                return {
                    "type": best["action_type"],
                    "x": best["x"],
                    "y": best["y"],
                    "source": "pattern_fuzzy",
                    "confidence": best["confidence"],
                }

        # Stage 3: 탐색
        self.stats["pattern_misses"] += 1
        self.stats["exploration_turns"] += 1
        return self._explore(screen_type)

    def _handle_non_gameplay(self, screen_type):
        """비-gameplay 화면 처리 규칙."""
        # 일반적인 팝업/결과 화면 → 화면 중앙 하단 탭 (확인 버튼)
        handlers = {
            "popup": {"x": 0.5, "y": 0.7},
            "win": {"x": 0.5, "y": 0.85},
            "fail": {"x": 0.5, "y": 0.75},
            "fail_result": {"x": 0.5, "y": 0.85},
            "lobby": {"x": 0.5, "y": 0.8},  # 시작 버튼 (대략)
            "ad": {"x": 0.95, "y": 0.05},  # X 버튼 (우상단)
            "loading": None,  # 대기
        }
        return handlers.get(screen_type)

    def _explore(self, screen_type):
        """탐색 모드: 패턴이 없을 때 랜덤 행동."""
        if screen_type == "gameplay":
            # 게임플레이 화면의 보드 영역에서 랜덤 탭
            x = np.random.uniform(0.1, 0.9)
            y = np.random.uniform(0.15, 0.65)  # 보드 영역 추정
        else:
            # 다른 화면은 중앙 하단
            x = np.random.uniform(0.3, 0.7)
            y = np.random.uniform(0.6, 0.9)

        return {
            "type": "tap",
            "x": round(x, 3),
            "y": round(y, 3),
            "source": "exploration",
            "confidence": 0.0,
        }

    def _execute_action(self, action):
        """ADB로 행동 실행."""
        atype = action.get("type", "tap")
        x = action.get("x", 0.5)
        y = action.get("y", 0.5)

        if atype == "tap":
            self.adb.tap_normalized(x, y)
        elif atype == "swipe":
            end_x = action.get("end_x", x)
            end_y = action.get("end_y", y)
            self.adb.swipe_normalized(x, y, end_x, end_y)

        time.sleep(0.3)  # 터치 반응 대기

    def _compute_delta(self, path_a, path_b, size=(270, 480)):
        """두 스크린샷 간 변화량."""
        try:
            a = np.array(Image.open(path_a).convert("L").resize(size), dtype=np.float32)
            b = np.array(Image.open(path_b).convert("L").resize(size), dtype=np.float32)
            return float(np.mean(np.abs(a - b)) / 255.0)
        except Exception:
            return 0.0

    def _classify_result(self, delta, screen_type):
        """변화량으로 결과 분류."""
        if delta > 0.15:
            return "screen_change"
        elif delta > 0.03:
            return "match"  # 보드 변화
        elif delta > 0.01:
            return "move"  # 미세 변화
        else:
            return "no_change"

    def _record_turn(self, turn_id, timestamp, state_hash, screen_type,
                     action, result, delta, before_path, after_path):
        """턴 결과를 DB에 기록."""
        if not self.session_id:
            return

        self.db.conn.execute("""
            INSERT INTO turn (turn_id, session_id, turn_number, timestamp,
                              screenshot_before, screenshot_after, state_hash,
                              screen_type, decision_source, confidence,
                              result, delta_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (turn_id, self.session_id, self.turn_count, timestamp,
              str(before_path), str(after_path), state_hash,
              screen_type, action.get("source", "unknown"),
              action.get("confidence", 0), result, delta))

        action_id = str(uuid.uuid4())
        self.db.conn.execute("""
            INSERT INTO action (action_id, turn_id, action_index, type,
                                x, y, timestamp)
            VALUES (?, ?, 0, ?, ?, ?, ?)
        """, (action_id, turn_id, action.get("type", "tap"),
              action.get("x", 0), action.get("y", 0), timestamp))

        self.db.conn.commit()

    def get_stats(self):
        """현재 통계."""
        db_stats = self.db.get_stats(self.game_id)
        return {
            **self.stats,
            "db": db_stats,
            "pattern_hit_rate": (
                round(self.stats["pattern_hits"] /
                      max(self.stats["total_turns"], 1) * 100, 1)
            ),
        }
