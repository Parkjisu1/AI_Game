"""
AI Game Tester — Pixel Flow Runner
====================================
Pixel Flow 전용 실행기.
CarMatch runner.py 기반, Pixel Flow 전략 적용.

핵심 차이점:
  - 돼지 배치가 메인 전략 (CarMatch의 카드 탭 대신)
  - 홀더 가득 참 → 돼지 희생 처리
  - 컨베이어 벨트 대기 (돼지가 돌아올 때까지)
"""

import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .playbook_pixelflow import create_pixelflow_playbook
from .perception import Perception, BoardState
from .memory import GameMemory
from .decision_pixelflow import DecisionPixelFlow
from .executor import Executor


# ---------------------------------------------------------------------------
# ADB 함수 (기존 시스템 재사용)
# ---------------------------------------------------------------------------
ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
SERIAL = "emulator-5554"
PACKAGE = "com.loomgames.pixelflow"


def adb_screenshot(temp_dir: Path, name: str = "frame") -> Optional[Path]:
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
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "input", "tap", str(x), str(y)],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def adb_back():
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "input", "keyevent", "4"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def adb_relaunch():
    try:
        # Home 먼저 (Play Store 등에서 탈출)
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "input", "keyevent", "3"],
            capture_output=True, timeout=5,
        )
        time.sleep(1)
        # Play Store도 강제 종료 (광고 리다이렉트 방지)
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "am", "force-stop", "com.android.vending"],
            capture_output=True, timeout=5,
        )
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "am", "force-stop", PACKAGE],
            capture_output=True, timeout=5,
        )
        time.sleep(2)
        # 명시적 Activity로 실행 (monkey 대신 — Play Store 오픈 방지)
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "am", "start", "-n",
             f"{PACKAGE}/com.unity3d.player.UnityPlayerActivity"],
            capture_output=True, timeout=5,
        )
        time.sleep(8)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Pixel Flow Runner
# ---------------------------------------------------------------------------
class PixelFlowRunner:
    """Pixel Flow AI Tester 메인 루프."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        temp_dir: Optional[Path] = None,
        log_file: Optional[Path] = None,
    ):
        self.playbook = create_pixelflow_playbook()
        self.temp_dir = temp_dir or Path(
            "E:/AI/virtual_player/data/games/pixelflow/temp/tester"
        )
        self.log_file = log_file or Path(
            "E:/AI/virtual_player/data/games/pixelflow/tester_log.txt"
        )

        # Layers
        self.perception = Perception(model=model, game="pixelflow")
        self.memory = GameMemory()
        self.decision = DecisionPixelFlow(self.playbook)
        self.executor = Executor(
            tap_fn=adb_tap,
            back_fn=adb_back,
            screenshot_fn=lambda: adb_screenshot(self.temp_dir),
            relaunch_fn=adb_relaunch,
            perception=self.perception,
            memory=self.memory,
        )

        self._current_board: Optional[BoardState] = None
        self._running = False
        self._same_screen_count = 0
        self._last_screen_type: Optional[str] = None
        self._non_gameplay_streak = 0  # win/popup 연속 카운트
        self._ad_heart_attempted = False  # 광고 하트 시도 여부

    _STUCK_WARN = 50
    _STUCK_SWEEP = 100
    _STUCK_RELAUNCH = 200  # gameplay에서 200턴까지 허용 (YOLO holder=0이라 모든 턴이 same screen, 실제로는 진행 중)

    def run(self, duration_minutes: int = 60):
        target = datetime.now() + timedelta(minutes=duration_minutes)
        mode = "SDK" if self.perception._use_sdk else "CLI (optimized)"
        self._log("=== Pixel Flow AI Tester START ===")
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

    def _game_loop(self, target: datetime):
        while datetime.now() < target:
            try:
                # Screenshot
                img = adb_screenshot(self.temp_dir, "current")
                if not img:
                    self._log("Screenshot failed, retrying...")
                    time.sleep(2)
                    continue

                # Perception
                t0 = time.time()
                board = self.perception.perceive(img)
                elapsed = time.time() - t0
                self._log(
                    f"Screen: {board.screen_type} | "
                    f"Holder: {board.holder_count}/5 | "
                    f"Vision: {elapsed:.1f}s"
                )

                # Decision에 스크린샷 경로 전달 (PIL 돼지 감지용)
                self.decision.set_screenshot(img)

                # Fail 스크린샷 자동 저장 (YOLO 학습 데이터)
                if board.screen_type == "fail_result":
                    self._save_fail_screenshot(img)

                # Stuck detection
                if board.screen_type == self._last_screen_type:
                    self._same_screen_count += 1
                else:
                    self._same_screen_count = 0
                self._last_screen_type = board.screen_type

                # non-gameplay loop detection (Gold Pack, ad loops, etc.)
                # Also count fake "gameplay" (interactive ads) as non-gameplay
                is_real_game = (board.screen_type == "gameplay"
                                and self.decision._is_real_pixelflow())
                if board.screen_type == "lobby" or is_real_game:
                    self._non_gameplay_streak = 0
                else:
                    self._non_gameplay_streak += 1
                if self._non_gameplay_streak >= 8:
                    self._log("  >> STORE/POPUP LOOP detected, force relaunch")
                    adb_relaunch()
                    self._non_gameplay_streak = 0
                    self._same_screen_count = 0
                    self.decision.reset()
                    time.sleep(5)
                    continue

                if self._same_screen_count >= self._STUCK_RELAUNCH:
                    self._log(
                        f"  >> STUCK RELAUNCH: {board.screen_type} "
                        f"x{self._same_screen_count}"
                    )
                    adb_relaunch()
                    self._same_screen_count = 0
                    self.decision.reset()
                    time.sleep(5)
                    continue
                elif (self._same_screen_count >= self._STUCK_WARN
                      and self._same_screen_count % 3 == 0):
                    self._log(
                        f"  >> STUCK WARNING: {board.screen_type} "
                        f"x{self._same_screen_count}"
                    )

                # Hearts wait (lobby 반복 시)
                if self.memory.is_heart_waiting():
                    remaining = int(self.memory.heart_wait_until - time.time())
                    self._log(f"  >> HEARTS WAIT: {remaining}s remaining")
                    self._same_screen_count = 0
                    time.sleep(30)
                    continue

                # Lobby fail detection
                # lobby→popup(hearts dialog)→lobby cycle also counts
                if board.screen_type == "lobby" and self._current_board:
                    if self._current_board.screen_type in ("lobby", "popup"):
                        self.memory.on_lobby_fail()
                        if self.memory.hearts_empty:
                            # 광고 하트 시도 (한 번만)
                            if not self._ad_heart_attempted:
                                self._ad_heart_attempted = True
                                self._log("  >> Trying ad for free heart...")
                                self._try_ad_heart()
                                self.memory.hearts_empty = False
                                self.memory.lobby_fail_count = 0
                                continue
                            self.memory.start_heart_wait()
                            self._ad_heart_attempted = False
                            self._log(
                                f"  >> HEARTS EMPTY: lobby failed "
                                f"{self.memory.lobby_fail_count}x, "
                                f"waiting {int(self.memory.HEART_REGEN_SECONDS)}s"
                            )
                            continue
                    elif self._current_board.screen_type == "gameplay":
                        self.memory.on_lobby_success()

                # Decision
                actions = self.decision.decide(board, self.memory)
                for a in actions:
                    self._log(f"  Plan: {a}")

                # Execute
                self._current_board = self.executor.execute(actions, board)

                # Stats every 10 turns
                if self.memory.total_turns % 10 == 0:
                    self._log(
                        f"--- Stats: {self.memory.games_won}W/"
                        f"{self.memory.games_failed}F | "
                        f"Taps: {self.memory.total_taps} | "
                        f"Vision: {self.perception.call_count} ---"
                    )

            except Exception as e:
                self._log(f"ERROR: {e}")
                time.sleep(3)

    def _print_report(self):
        self._log("")
        self._log("=" * 50)
        self._log("SESSION COMPLETE")
        self._log("=" * 50)
        self._log(f"Games started:  {self.memory.games_started}")
        self._log(f"Games won:      {self.memory.games_won}")
        self._log(f"Games failed:   {self.memory.games_failed}")
        self._log(f"Total taps:     {self.memory.total_taps}")
        self._log(f"Total turns:    {self.memory.total_turns}")
        self._log(f"Vision calls:   {self.perception.call_count}")

        stats = {
            "game": "pixelflow",
            "games_started": self.memory.games_started,
            "games_won": self.memory.games_won,
            "games_failed": self.memory.games_failed,
            "total_taps": self.memory.total_taps,
            "total_turns": self.memory.total_turns,
            "vision_calls": self.perception.call_count,
            "ended_at": datetime.now().isoformat(),
        }
        stats_path = self.temp_dir / "stats.json"
        stats_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
        self._log(f"Stats saved: {stats_path}")

    def _try_ad_heart(self):
        """광고 시청으로 하트 1개 획득 시도.

        1. Play 탭 → hearts popup
        2. "받기" 버튼 탭 (약 290, 810)
        3. 광고 대기 (최대 35초)
        4. back으로 광고 닫기
        """
        try:
            # 1) Play 탭 → hearts popup 나타남
            adb_tap(502, 1450)
            time.sleep(3)

            # 2) "받기" (watch ad for +1 heart) 탭 — 2026-03-10 verified (387,1168)
            adb_tap(387, 1168)
            self._log("  >> Tapped 받기 ad button")
            time.sleep(5)

            # 3) 광고 대기 (30초) + back으로 닫기 시도
            for i in range(6):
                time.sleep(5)
                adb_back()
                self._log(f"  >> Ad wait {(i+1)*5}s, back pressed")

            # 4) 추가 back + home tab으로 복귀
            time.sleep(2)
            adb_back()
            time.sleep(2)
            adb_tap(540, 1830)  # Home tab
            time.sleep(3)
            self._log("  >> Ad heart attempt done, returning to lobby")
        except Exception as e:
            self._log(f"  >> Ad heart failed: {e}")

    _fail_count = 0

    def _save_fail_screenshot(self, img_path: Path):
        """Fail 스크린샷을 YOLO 학습 데이터로 자동 저장."""
        try:
            import shutil
            self._fail_count += 1
            fail_dir = Path(
                "E:/AI/virtual_player/data/games/pixelflow/yolo_dataset/train/fail"
            )
            fail_dir.mkdir(parents=True, exist_ok=True)
            dest = fail_dir / f"auto_fail_{self._fail_count:03d}.png"
            shutil.copy2(img_path, dest)
            self._log(f"  >> Fail screenshot saved: {dest.name}")
        except Exception:
            pass

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


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Pixel Flow AI Tester")
    parser.add_argument(
        "duration", nargs="?", type=int, default=60,
        help="Duration in minutes (default: 60)",
    )
    parser.add_argument(
        "--model", type=str, default="claude-sonnet-4-6",
        help="Vision model (default: claude-sonnet-4-6)",
    )
    args = parser.parse_args()

    runner = PixelFlowRunner(model=args.model)
    runner.run(duration_minutes=args.duration)


if __name__ == "__main__":
    main()
