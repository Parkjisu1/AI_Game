"""
AI Game Tester v2 — Main Runner
=================================
5-Layer 통합 실행기.

Perception → Memory → Decision → Execution → Verification
(눈)         (기억)    (판단)      (손)          (확인)

자유도 최소, 규칙 최대.
"""

import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .playbook import Playbook, create_carmatch_playbook
from .perception import Perception, BoardState
from .memory import GameMemory
from .decision import Decision
from .decision_v2 import DecisionV2
from .executor import Executor


# ---------------------------------------------------------------------------
# ADB 함수 (기존 시스템 재사용)
# ---------------------------------------------------------------------------
ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
SERIAL = "emulator-5554"


def adb_screenshot(temp_dir: Path, name: str = "frame") -> Optional[Path]:
    """ADB 스크린샷 캡처."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(
            [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"],
            capture_output=True, timeout=10,
        )
        if len(r.stdout) < 1000:
            return None
        path = temp_dir / f"{name}.png"
        path.write_bytes(r.stdout)
        return path
    except Exception:
        return None


def adb_tap(x: int, y: int):
    """ADB 탭."""
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "input", "tap", str(x), str(y)],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def adb_back():
    """ADB back 버튼."""
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "input", "keyevent", "4"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def adb_relaunch(package: str = "com.grandgames.carmatch"):
    """게임 강제 종료 + 재시작."""
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "am", "force-stop", package],
            capture_output=True, timeout=5,
        )
        time.sleep(2)
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "monkey", "-p", package,
             "-c", "android.intent.category.LAUNCHER", "1"],
            capture_output=True, timeout=5,
        )
        time.sleep(5)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------
class TesterRunner:
    """AI Game Tester v2 메인 루프."""

    def __init__(
        self,
        playbook: Optional[Playbook] = None,
        model: str = "claude-sonnet-4-6",
        temp_dir: Optional[Path] = None,
        log_file: Optional[Path] = None,
        use_lookahead: bool = False,
        use_deep_lookahead: bool = False,
        lookahead_weights: Optional[dict] = None,
    ):
        self.playbook = playbook or create_carmatch_playbook()
        self.temp_dir = temp_dir or Path("E:/AI/virtual_player/data/games/carmatch/temp/tester_v2")
        self.log_file = log_file or Path("E:/AI/virtual_player/data/games/carmatch/tester_v2_log.txt")

        # Layer 초기화
        self.perception = Perception(model=model)
        self.memory = GameMemory()
        if use_lookahead or use_deep_lookahead:
            self.decision = DecisionV2(
                self.playbook,
                use_deep=use_deep_lookahead,
                weights=lookahead_weights,
            )
        else:
            self.decision = Decision(self.playbook)
        self.executor = Executor(
            tap_fn=adb_tap,
            back_fn=adb_back,
            screenshot_fn=lambda: adb_screenshot(self.temp_dir),
            relaunch_fn=adb_relaunch,
            perception=self.perception,
            memory=self.memory,
        )

        # 상태
        self._current_board: Optional[BoardState] = None
        self._running = False
        self._skip_next_perception = False  # 예측 스킵 플래그
        self._assumed_screen: Optional[str] = None  # 스킵 시 가정할 화면

        # Stuck 감지
        self._same_screen_count = 0
        self._last_screen_type: Optional[str] = None
        self._ad_first_seen: Optional[float] = None  # 광고 최초 감지 시각

    def run(self, duration_minutes: int = 60):
        """메인 루프 실행."""
        target = datetime.now() + timedelta(minutes=duration_minutes)

        mode = "SDK" if self.perception._use_sdk else "CLI (optimized)"
        self._log(f"=== AI Game Tester v2 START ===")
        self._log(f"Game: {self.playbook.game_id}")
        self._log(f"Target: {target.strftime('%Y-%m-%d %H:%M')}")
        self._log(f"Model: {self.perception.model} | Mode: {mode}")
        self._running = True

        try:
            self._game_loop(target)
        except KeyboardInterrupt:
            self._log("Interrupted by user")
        except Exception as e:
            self._log(f"FATAL ERROR: {e}")
        finally:
            self._running = False
            self._print_report()

    # 예측 가능한 화면 전환 (action 후 예상 결과)
    # key: (현재 screen_type, action reason 키워드)
    # value: (예상 다음 screen, 대기 시간)
    # NOTE: fail_result 제거 — Try Again 좌표가 불확실하여 무한루프 원인
    _PREDICTABLE_TRANSITIONS = {
        ("lobby", "Level N"):           ("gameplay", 4.0),
        ("win", "Continue"):            ("lobby", 3.0),
    }

    # Stuck 감지: 같은 화면 연속 반복 카운터
    _STUCK_WARN = 5       # 경고 로그
    _STUCK_SWEEP = 10     # 다양한 좌표 시도
    _STUCK_RELAUNCH = 20  # 게임 재시작

    def _game_loop(self, target: datetime):
        """핵심 루프: perceive → decide → execute → verify."""

        while datetime.now() < target:
            try:
                # Step 1: 스크린샷
                img = adb_screenshot(self.temp_dir, "current")
                if not img:
                    self._log("Screenshot failed, retrying...")
                    time.sleep(2)
                    continue

                # Step 2: Layer 1 — Perception
                if self._skip_next_perception and self._assumed_screen:
                    assumed = self._assumed_screen
                    self._skip_next_perception = False
                    self._assumed_screen = None
                    if assumed != "gameplay":
                        # 비-gameplay 예측 → Vision 스킵 OK
                        board = BoardState(screen_type=assumed, holder=[None]*7)
                        self._log(f"Screen: {board.screen_type} (predicted, skip vision)")
                    else:
                        # gameplay 예측 → Phase 1 스킵하되 Phase 2는 실행
                        self.perception._last_screen = "gameplay"
                        t0 = time.time()
                        board = self.perception.perceive(img)
                        elapsed = time.time() - t0
                        self._log(f"Screen: {board.screen_type} | "
                                  f"Holder: {self._format_holder(board.holder)} | "
                                  f"Cars: {len(board.active_cars)} | "
                                  f"Vision: {elapsed:.1f}s (P1 skip)")
                else:
                    t0 = time.time()
                    board = self.perception.perceive(img)
                    elapsed = time.time() - t0
                    self._log(f"Screen: {board.screen_type} | "
                              f"Holder: {self._format_holder(board.holder)} | "
                              f"Cars: {len(board.active_cars)} | "
                              f"Vision: {elapsed:.1f}s")

                prev_board = self._current_board or board

                # Stuck 감지: 같은 화면 연속 반복 카운트
                if board.screen_type == self._last_screen_type:
                    self._same_screen_count += 1
                else:
                    self._same_screen_count = 0
                    self._ad_first_seen = None
                self._last_screen_type = board.screen_type

                # Stuck 에스컬레이션
                if self._same_screen_count >= self._STUCK_RELAUNCH:
                    self._log(f"  >> STUCK RELAUNCH: {board.screen_type} x{self._same_screen_count}")
                    adb_relaunch()
                    self._same_screen_count = 0
                    self._ad_first_seen = None
                    continue
                elif self._same_screen_count >= self._STUCK_WARN and self._same_screen_count % 5 == 0:
                    self._log(f"  >> STUCK WARNING: {board.screen_type} x{self._same_screen_count}")

                # Step 3: Layer 2 — Memory 업데이트 (첫 턴이 아니면)
                if self._current_board is not None:
                    # 이미 executor에서 업데이트되므로 여기선 스킵
                    pass

                # Step 4: Layer 3 — Decision
                actions = self.decision.decide(board, self.memory)
                for a in actions:
                    self._log(f"  Plan: {a}")

                # Step 5: Layer 4+5 — Execute + Verify
                self._current_board = self.executor.execute(actions, board)

                # 예측 스킵 판정: 이 액션 후 화면 전환이 예상되는가?
                self._check_predictable_transition(board.screen_type, actions)

                # 주기적 통계
                if self.memory.total_turns % 10 == 0:
                    self._log(f"--- Stats: {self.memory.games_won}W/"
                              f"{self.memory.games_failed}F | "
                              f"Taps: {self.memory.total_taps} | "
                              f"Matches: {self.memory.total_matches} | "
                              f"Vision: {self.perception.call_count} ---")

            except Exception as e:
                self._log(f"ERROR: {e}")
                time.sleep(3)

    def _check_predictable_transition(self, screen: str, actions):
        """액션 후 예측 가능한 화면 전환이면 다음 턴 Vision 스킵."""
        for action in actions:
            for (src_screen, keyword), (dest, wait) in self._PREDICTABLE_TRANSITIONS.items():
                if screen == src_screen and keyword in action.reason:
                    self._skip_next_perception = True
                    self._assumed_screen = dest
                    self._log(f"  >> Predict: {src_screen} -> {dest} (skip next vision, wait {wait}s)")
                    time.sleep(wait)
                    return

    def _print_report(self):
        """최종 보고서."""
        self._log("")
        self._log("=" * 50)
        self._log("SESSION COMPLETE")
        self._log("=" * 50)
        self._log(f"Games started:  {self.memory.games_started}")
        self._log(f"Games won:      {self.memory.games_won}")
        self._log(f"Games failed:   {self.memory.games_failed}")
        self._log(f"Total taps:     {self.memory.total_taps}")
        self._log(f"Total matches:  {self.memory.total_matches}")
        self._log(f"Total turns:    {self.memory.total_turns}")
        self._log(f"Vision calls:   {self.perception.call_count}")

        # JSON 통계 저장
        stats = {
            "games_started": self.memory.games_started,
            "games_won": self.memory.games_won,
            "games_failed": self.memory.games_failed,
            "total_taps": self.memory.total_taps,
            "total_matches": self.memory.total_matches,
            "total_turns": self.memory.total_turns,
            "vision_calls": self.perception.call_count,
            "ended_at": datetime.now().isoformat(),
        }
        stats_path = self.temp_dir / "stats.json"
        stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
        self._log(f"Stats saved: {stats_path}")

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        try:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _format_holder(self, holder: list) -> str:
        parts = []
        for h in holder:
            if h is None:
                parts.append("_")
            else:
                parts.append(h[0].upper())
        return "[" + " ".join(parts) + "]"


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main():
    """커맨드라인 실행."""
    import argparse
    parser = argparse.ArgumentParser(description="AI Game Tester v2")
    parser.add_argument("duration", nargs="?", type=int, default=60,
                        help="Duration in minutes (default: 60)")
    parser.add_argument("--lookahead", action="store_true",
                        help="Use 1-move lookahead simulation")
    parser.add_argument("--deep", action="store_true",
                        help="Use 2-move deep lookahead simulation")
    parser.add_argument("--model", type=str, default="claude-sonnet-4-6",
                        help="Vision model (default: claude-sonnet-4-6)")
    args = parser.parse_args()

    runner = TesterRunner(
        model=args.model,
        use_lookahead=args.lookahead,
        use_deep_lookahead=args.deep,
    )
    runner.run(duration_minutes=args.duration)


if __name__ == "__main__":
    main()
