"""
Learning Runner V2 — pyautogui 기반 통합 러너
===============================================
3-Phase 파이프라인:
  Phase 1: Record — pyautogui로 사람 플레이 녹화
  Phase 2: Learn  — Zone + Patch 기반 자동 분석
  Phase 3: Play   — 학습된 패턴 + 페르소나 AI 플레이

V2 변경사항:
  - pyautogui로 실제 BlueStacks 화면 캡처 (Unity overlay 포함)
  - Zone 기반 의사결정
  - Patch template matching

사용법:
  # 전체 파이프라인
  python -m virtual_player.tester.learning_runner \
    --game pixelflow --package com.loomgames.pixelflow \
    --full 20 60 --persona smart_player

  # 플레이만
  python -m virtual_player.tester.learning_runner \
    --game pixelflow --package com.loomgames.pixelflow \
    --play 60 --persona dumb_newbie --db learned_db.json
"""

import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .playbook import Action
from .perception import Perception, BoardState
from .memory import GameMemory
from .personas.base import PlayerProfile
from .personas.presets import load_persona
from .learning_engine import LearningEngine, LearnedDB
from .learned_decision import LearnedDecision
from .demo_recorder import DemoRecorder, find_bluestacks_window


# ---------------------------------------------------------------------------
# ADB helpers (tap/back/relaunch은 여전히 ADB 사용)
# ---------------------------------------------------------------------------
ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
SERIAL = "emulator-5554"


def _adb_tap(x: int, y: int):
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "input", "tap", str(x), str(y)],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _adb_back():
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "input", "keyevent", "4"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


def _adb_relaunch(package: str):
    try:
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "input", "keyevent", "3"],
            capture_output=True, timeout=5,
        )
        time.sleep(1)
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "am", "force-stop", package],
            capture_output=True, timeout=5,
        )
        time.sleep(2)
        subprocess.run(
            [ADB, "-s", SERIAL, "shell", "am", "start", "-n",
             f"{package}/com.unity3d.player.UnityPlayerActivity"],
            capture_output=True, timeout=5,
        )
        time.sleep(8)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# pyautogui Screenshot
# ---------------------------------------------------------------------------
def _pyautogui_screenshot(
    temp_dir: Path,
    window_region: tuple,
    name: str = "frame",
    resolution: tuple = (1080, 1920),
) -> Optional[Path]:
    """pyautogui로 BlueStacks 화면 캡처 → 게임 해상도로 리사이즈."""
    try:
        import pyautogui
        temp_dir.mkdir(parents=True, exist_ok=True)
        screenshot = pyautogui.screenshot(region=window_region)
        screenshot = screenshot.resize(resolution)
        path = temp_dir / f"{name}.png"
        screenshot.save(str(path))
        return path
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LearningRunner
# ---------------------------------------------------------------------------
class LearningRunner:
    """녹화 → 학습 → 플레이 통합 러너 (V2)."""

    def __init__(
        self,
        game_id: str,
        package: str,
        persona_id: str = "normal_player",
        model: str = "claude-haiku-4-5-20251001",
        data_dir: Optional[Path] = None,
    ):
        self.game_id = game_id
        self.package = package
        self.model = model

        self.data_dir = data_dir or Path(
            f"E:/AI/virtual_player/data/games/{game_id}"
        )
        self.temp_dir = self.data_dir / "temp" / "learning"
        self.db_path = self.data_dir / "learned_db.json"

        try:
            self.persona = load_persona(persona_id)
        except ValueError:
            self.persona = load_persona("normal_player")

        self.learned_db: Optional[LearnedDB] = None
        self.decision: Optional[LearnedDecision] = None

        # BlueStacks 윈도우 영역 (play 시 사용)
        self._window_region: Optional[tuple] = None

    # ===================================================================
    # Phase 1: Record
    # ===================================================================
    def record(self, duration_minutes: int = 5):
        """pyautogui 기반 사람 플레이 녹화."""
        self._log("=== Phase 1: RECORD (V2 pyautogui) ===")
        self._log(f"Game: {self.game_id}")
        self._log(f"Duration: {duration_minutes} min")
        self._log("Play the game normally. Press Ctrl+C when done.")
        self._log("")

        recorder = DemoRecorder(
            game_id=self.game_id,
            output_dir=None,
        )
        recorder.record(duration_minutes=duration_minutes)
        self._log(f"Recording saved: {recorder.output_dir}")
        return recorder.output_dir

    # ===================================================================
    # Phase 2: Learn
    # ===================================================================
    def learn(self, demo_dirs: list = None):
        """데모에서 학습 (V2 Zone + Patch)."""
        self._log("=== Phase 2: LEARN (V2 Zone+Patch) ===")

        if not demo_dirs:
            demos_root = self.data_dir / "demonstrations"
            if demos_root.exists():
                demo_dirs = sorted(demos_root.glob("demo_*"))
            else:
                self._log("No demo directories found!")
                return

        engine = LearningEngine(self.game_id)
        for d in demo_dirs:
            engine.add_demo(Path(d))

        self.learned_db = engine.learn()
        engine.save(self.learned_db, self.db_path)

        self._log(f"Learned DB saved: {self.db_path}")
        self._log(f"  Clusters: {len(self.learned_db.clusters)}")
        self._log(f"  Coord patterns: {len(self.learned_db.action_patterns)}")
        self._log(f"  Zone patterns: {len(self.learned_db.zone_patterns)}")
        self._log(f"  Patch patterns: {len(self.learned_db.patch_patterns)}")
        self._log(f"  Rules: {len(self.learned_db.conditional_rules)}")

    def load_db(self, db_path: Optional[Path] = None):
        path = db_path or self.db_path
        if path.exists():
            self.learned_db = LearningEngine.load(path)
            self._log(f"Loaded DB: {path} (v={self.learned_db.version})")
            self._log(f"  Clusters: {len(self.learned_db.clusters)}")
            self._log(f"  Zone patterns: {len(self.learned_db.zone_patterns)}")
            self._log(f"  Patch patterns: {len(self.learned_db.patch_patterns)}")
        else:
            self._log(f"DB not found: {path}")

    # ===================================================================
    # Phase 3: Play
    # ===================================================================
    def play(self, duration_minutes: int = 60):
        """학습된 패턴으로 AI 플레이 (pyautogui 스크린샷)."""
        if not self.learned_db:
            self.load_db()
        if not self.learned_db:
            self._log("No learned DB! Run learn() first.")
            return

        # BlueStacks 윈도우 찾기
        self._window_region = find_bluestacks_window()
        if not self._window_region:
            self._log("BlueStacks window not found!")
            return

        self._log("=== Phase 3: PLAY (V2 pyautogui) ===")
        self._log(f"BlueStacks: {self._window_region}")
        self._log(f"Persona: {self.persona.persona_name}")
        self._log(f"  Intelligence: {self.persona.intelligence}")
        self._log(f"  Familiarity: {self.persona.familiarity}")
        self._log(f"  Mistake rate: {self.persona.mistake_rate:.0%}")
        self._log(f"  Mode: {self.persona.get_priority_override()}")
        self._log(f"Duration: {duration_minutes} min")
        self._log("")

        # 가장 최근 demo 디렉토리 (패치 파일 참조용)
        demos_root = self.data_dir / "demonstrations"
        demo_dir = None
        if demos_root.exists():
            demo_dirs = sorted(demos_root.glob("demo_*"))
            if demo_dirs:
                demo_dir = demo_dirs[-1]

        self.decision = LearnedDecision(
            learned_db=self.learned_db,
            persona=self.persona,
            demo_dir=demo_dir,
        )

        perception = Perception(model=self.model, game=self.game_id)
        memory = GameMemory()

        target = datetime.now() + timedelta(minutes=duration_minutes)
        same_screen_count = 0
        last_screen = None

        try:
            while datetime.now() < target:
                # pyautogui 스크린샷
                img = _pyautogui_screenshot(
                    self.temp_dir, self._window_region, "current"
                )
                if not img:
                    time.sleep(2)
                    continue

                # Perception
                board = perception.perceive(img)

                # Decision
                self.decision.set_screenshot(img)
                actions = self.decision.decide(board, memory)

                for action in actions:
                    self._log(f"  {action}")

                    if action.type == "tap":
                        _adb_tap(action.x, action.y)
                    elif action.type == "back":
                        _adb_back()
                    elif action.type == "relaunch":
                        _adb_relaunch(self.package)

                    wait = action.wait
                    if self.persona:
                        wait = max(wait, self.persona.get_reaction_delay())
                    time.sleep(wait)

                # Stuck detection
                if board.screen_type == last_screen:
                    same_screen_count += 1
                else:
                    same_screen_count = 0
                last_screen = board.screen_type

                if same_screen_count >= 30:
                    self._log(">> STUCK, relaunch")
                    _adb_relaunch(self.package)
                    same_screen_count = 0
                    self.decision.reset()
                    time.sleep(5)

                if memory.total_turns % 10 == 0:
                    stats = self.decision.stats
                    self._log(
                        f"--- W:{memory.games_won} F:{memory.games_failed} "
                        f"Taps:{memory.total_taps} "
                        f"Patches:{stats.get('patch_templates', 0)} "
                        f"Persona:{self.persona.persona_id} ---"
                    )

        except KeyboardInterrupt:
            self._log("Interrupted")
        finally:
            self._print_report(memory)

    # ===================================================================
    # Full Pipeline
    # ===================================================================
    def run_full(
        self,
        record_minutes: int = 5,
        play_minutes: int = 60,
    ):
        demo_dir = self.record(duration_minutes=record_minutes)
        self.learn(demo_dirs=[demo_dir])
        self.play(duration_minutes=play_minutes)

    def _print_report(self, memory: GameMemory):
        self._log("")
        self._log("=" * 50)
        self._log("SESSION REPORT")
        self._log("=" * 50)
        self._log(f"Game:          {self.game_id}")
        self._log(f"Persona:       {self.persona.persona_name}")
        self._log(f"  IQ:          {self.persona.intelligence}")
        self._log(f"  Familiarity: {self.persona.familiarity}")
        self._log(f"  Mistakes:    {self.persona.mistake_rate:.0%}")
        self._log(f"Games won:     {memory.games_won}")
        self._log(f"Games failed:  {memory.games_failed}")
        self._log(f"Total taps:    {memory.total_taps}")
        self._log(f"Total turns:   {memory.total_turns}")

        if self.decision:
            stats = self.decision.stats
            self._log(f"Clusters:      {stats.get('clusters_known', 0)}")
            self._log(f"Patches:       {stats.get('patch_templates', 0)}")

        report = {
            "game_id": self.game_id,
            "version": "v2",
            "persona": self.persona.persona_id,
            "intelligence": self.persona.intelligence,
            "familiarity": self.persona.familiarity,
            "mistake_rate": self.persona.mistake_rate,
            "games_won": memory.games_won,
            "games_failed": memory.games_failed,
            "total_taps": memory.total_taps,
            "total_turns": memory.total_turns,
            "ended_at": datetime.now().isoformat(),
        }
        report_path = self.temp_dir / "session_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        self._log(f"Report: {report_path}")

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Learning Runner V2 — Record → Learn → Play"
    )
    parser.add_argument("--game", required=True, help="Game ID")
    parser.add_argument("--package", default=None,
                        help="Android package name")
    parser.add_argument("--persona", default="normal_player",
                        help="Persona ID")
    parser.add_argument("--record", type=int, default=0,
                        help="Record N minutes")
    parser.add_argument("--learn-from", nargs="*", default=None,
                        help="Demo directories to learn from")
    parser.add_argument("--play", type=int, default=0,
                        help="Play for N minutes")
    parser.add_argument("--db", default=None,
                        help="Pre-existing learned DB path")
    parser.add_argument("--full", type=int, nargs=2,
                        metavar=("RECORD", "PLAY"), default=None,
                        help="Full pipeline: --full RECORD_MIN PLAY_MIN")
    args = parser.parse_args()

    KNOWN = {
        "carmatch": "com.grandgames.carmatch",
        "pixelflow": "com.loomgames.pixelflow",
    }
    package = args.package or KNOWN.get(args.game, f"com.unknown.{args.game}")

    runner = LearningRunner(
        game_id=args.game,
        package=package,
        persona_id=args.persona,
    )

    if args.db:
        runner.load_db(Path(args.db))

    if args.full:
        runner.run_full(
            record_minutes=args.full[0], play_minutes=args.full[1]
        )
        return

    if args.record > 0:
        runner.record(duration_minutes=args.record)

    if args.learn_from:
        runner.learn(demo_dirs=[Path(d) for d in args.learn_from])
    elif args.record > 0:
        runner.learn()

    if args.play > 0:
        runner.play(duration_minutes=args.play)


if __name__ == "__main__":
    main()
