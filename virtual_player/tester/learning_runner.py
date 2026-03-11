"""
Learning Runner — 녹화 → 학습 → 플레이 통합 러너
===================================================

3-Phase 자동 파이프라인:
  Phase 1: Record — 사람이 3~5판 플레이 (demo_recorder)
  Phase 2: Learn  — 자동 분석 → learned_db.json (learning_engine)
  Phase 3: Play   — 학습된 패턴 + 페르소나로 AI 플레이 (learned_decision)

사용법:
  # 전체 파이프라인 (녹화→학습→플레이)
  python -m virtual_player.tester.learning_runner \
    --game carmatch --package com.grandgames.carmatch \
    --record 5 --play 60 --persona smart_player

  # 학습만 (기존 데모에서)
  python -m virtual_player.tester.learning_runner \
    --game carmatch --learn-from demo_20260306_100000

  # 기존 DB로 플레이만
  python -m virtual_player.tester.learning_runner \
    --game carmatch --package com.grandgames.carmatch \
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
from .demo_recorder import DemoRecorder


# ---------------------------------------------------------------------------
# ADB helpers
# ---------------------------------------------------------------------------
ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
SERIAL = "emulator-5554"


def _adb_screenshot(temp_dir: Path, name: str = "frame") -> Optional[Path]:
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
# LearningRunner
# ---------------------------------------------------------------------------
class LearningRunner:
    """녹화 → 학습 → 플레이 통합 러너."""

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

        # 페르소나
        try:
            self.persona = load_persona(persona_id)
        except ValueError:
            self.persona = load_persona("normal_player")

        self.learned_db: Optional[LearnedDB] = None
        self.decision: Optional[LearnedDecision] = None

    # ===================================================================
    # Phase 1: Record
    # ===================================================================
    def record(self, duration_minutes: int = 5):
        """사람 플레이 녹화."""
        self._log("=== Phase 1: RECORD ===")
        self._log(f"Game: {self.game_id}")
        self._log(f"Duration: {duration_minutes} min")
        self._log("Play the game normally. Press Ctrl+C when done.")
        self._log("")

        recorder = DemoRecorder(
            game_id=self.game_id,
            output_dir=None,  # 자동 경로
        )
        recorder.record(duration_minutes=duration_minutes)
        self._log(f"Recording saved: {recorder.output_dir}")
        return recorder.output_dir

    # ===================================================================
    # Phase 2: Learn
    # ===================================================================
    def learn(self, demo_dirs: list = None):
        """데모에서 학습."""
        self._log("=== Phase 2: LEARN ===")

        # 데모 디렉토리 자동 탐색
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
        self._log(f"  Patterns: {len(self.learned_db.action_patterns)}")
        self._log(f"  Rules: {len(self.learned_db.conditional_rules)}")

    def load_db(self, db_path: Optional[Path] = None):
        """기존 학습 DB 로드."""
        path = db_path or self.db_path
        if path.exists():
            self.learned_db = LearningEngine.load(path)
            self._log(f"Loaded DB: {path}")
            self._log(f"  Clusters: {len(self.learned_db.clusters)}")
            self._log(f"  Patterns: {len(self.learned_db.action_patterns)}")
        else:
            self._log(f"DB not found: {path}")

    # ===================================================================
    # Phase 3: Play
    # ===================================================================
    def play(self, duration_minutes: int = 60):
        """학습된 패턴으로 AI 플레이."""
        if not self.learned_db:
            self.load_db()
        if not self.learned_db:
            self._log("No learned DB! Run learn() first.")
            return

        self._log("=== Phase 3: PLAY ===")
        self._log(f"Persona: {self.persona.persona_name}")
        self._log(f"  Intelligence: {self.persona.intelligence}")
        self._log(f"  Familiarity: {self.persona.familiarity}")
        self._log(f"  Mistake rate: {self.persona.mistake_rate:.0%}")
        self._log(f"  Mode: {self.persona.get_priority_override()}")
        self._log(f"Duration: {duration_minutes} min")
        self._log("")

        # Decision 엔진 초기화
        self.decision = LearnedDecision(
            learned_db=self.learned_db,
            persona=self.persona,
        )

        # Perception (화면 분류용)
        perception = Perception(model=self.model, game=self.game_id)
        memory = GameMemory()

        target = datetime.now() + timedelta(minutes=duration_minutes)
        same_screen_count = 0
        last_screen = None

        try:
            while datetime.now() < target:
                # Screenshot
                img = _adb_screenshot(self.temp_dir, "current")
                if not img:
                    time.sleep(2)
                    continue

                # Perception (YOLO fast path)
                board = perception.perceive(img)

                # Learned Decision
                self.decision.set_screenshot(img)
                actions = self.decision.decide(board, memory)

                for action in actions:
                    self._log(f"  {action}")

                    # Execute
                    if action.type == "tap":
                        _adb_tap(action.x, action.y)
                    elif action.type == "back":
                        _adb_back()
                    elif action.type == "relaunch":
                        _adb_relaunch(self.package)

                    # 페르소나 반응 지연
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

                # Stats
                if memory.total_turns % 10 == 0:
                    self._log(
                        f"--- W:{memory.games_won} F:{memory.games_failed} "
                        f"Taps:{memory.total_taps} "
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
        """전체 파이프라인: 녹화 → 학습 → 플레이."""
        # Phase 1
        demo_dir = self.record(duration_minutes=record_minutes)

        # Phase 2
        self.learn(demo_dirs=[demo_dir])

        # Phase 3
        self.play(duration_minutes=play_minutes)

    def _print_report(self, memory: GameMemory):
        """세션 리포트."""
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

        # JSON 리포트 저장
        report = {
            "game_id": self.game_id,
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
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
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
        description="Learning Runner — Record → Learn → Play"
    )
    parser.add_argument("--game", required=True, help="Game ID")
    parser.add_argument("--package", default=None,
                        help="Android package name")
    parser.add_argument("--persona", default="normal_player",
                        help="Persona ID (e.g. smart_player, dumb_newbie)")
    parser.add_argument("--record", type=int, default=0,
                        help="Record N minutes of human play")
    parser.add_argument("--learn-from", nargs="*", default=None,
                        help="Demo directories to learn from")
    parser.add_argument("--play", type=int, default=0,
                        help="Play for N minutes")
    parser.add_argument("--db", default=None,
                        help="Pre-existing learned DB path")
    parser.add_argument("--full", type=int, nargs=2, metavar=("RECORD", "PLAY"),
                        default=None,
                        help="Full pipeline: --full RECORD_MIN PLAY_MIN")
    args = parser.parse_args()

    # 패키지명 추정
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

    # 기존 DB 로드
    if args.db:
        runner.load_db(Path(args.db))

    # Full pipeline
    if args.full:
        runner.run_full(record_minutes=args.full[0], play_minutes=args.full[1])
        return

    # Record
    if args.record > 0:
        runner.record(duration_minutes=args.record)

    # Learn
    if args.learn_from:
        runner.learn(demo_dirs=[Path(d) for d in args.learn_from])
    elif args.record > 0:
        # 녹화 직후 자동 학습
        runner.learn()

    # Play
    if args.play > 0:
        runner.play(duration_minutes=args.play)


if __name__ == "__main__":
    main()
