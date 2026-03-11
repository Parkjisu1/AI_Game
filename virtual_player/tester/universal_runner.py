"""
Universal Game Runner
======================
장르/게임 불문 범용 게임 테스터.

4단계 자동 온보딩:
  1. 게임 패키지명 → 자동 실행
  2. 스크린샷 수집 → OCR 분석 → 장르 추정
  3. Playbook 자동 생성 (또는 기존 Playbook 로드)
  4. GenericDecision으로 플레이 시작

기존 게임별 러너(runner.py, runner_pixelflow.py)를 대체하지 않고 보완.
게임별 러너가 있으면 그쪽이 더 정확하므로 우선 사용.
"""

import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .playbook import Action, Playbook
from .perception import Perception, BoardState
from .memory import GameMemory
from .generic_decision import GenericDecision
from .universal_vision import UniversalVision, ScreenClassifier
from .executor import Executor
from .genres.loader import load_genre, list_genres
from .personas.base import PlayerProfile
from .personas.presets import load_persona


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
# Known games registry
# ---------------------------------------------------------------------------
KNOWN_GAMES = {
    "com.grandgames.carmatch": {
        "game_id": "carmatch",
        "genre": "puzzle_match",
        "playbook_factory": "virtual_player.tester.playbook:create_carmatch_playbook",
    },
    "com.loomgames.pixelflow": {
        "game_id": "pixelflow",
        "genre": "puzzle_match",
        "playbook_factory": "virtual_player.tester.playbook_pixelflow:create_pixelflow_playbook",
    },
}


def _load_playbook_for_package(package: str) -> Optional[Playbook]:
    """알려진 게임이면 Playbook 로드."""
    info = KNOWN_GAMES.get(package)
    if not info:
        return None

    factory_path = info["playbook_factory"]
    module_path, func_name = factory_path.rsplit(":", 1)

    try:
        import importlib
        mod = importlib.import_module(module_path)
        factory = getattr(mod, func_name)
        return factory()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Genre Auto-Detection
# ---------------------------------------------------------------------------
class GenreDetector:
    """스크린샷 분석으로 장르 자동 추정."""

    # 장르별 키워드 시그니처
    GENRE_KEYWORDS = {
        "puzzle_match": ["match", "puzzle", "level", "moves", "score",
                         "holder", "board", "매치", "퍼즐"],
        "idle_rpg": ["hero", "battle", "quest", "stamina", "auto",
                     "영웅", "전투", "퀘스트", "스태미나"],
        "runner_platformer": ["run", "distance", "speed", "jump",
                               "coins", "달리기", "거리"],
        "tower_defense": ["wave", "tower", "deploy", "enemy", "path",
                          "웨이브", "타워", "배치"],
        "card_battle": ["card", "deck", "mana", "turn", "hand",
                        "카드", "덱", "마나", "턴"],
        "simulation": ["build", "produce", "harvest", "timer", "farm",
                        "건설", "생산", "수확"],
    }

    def __init__(self):
        self.vision = UniversalVision()

    def detect_genre(self, screenshots: list) -> str:
        """여러 스크린샷에서 장르 추정."""
        genre_scores = {g: 0 for g in self.GENRE_KEYWORDS}

        for img_path in screenshots:
            ui = self.vision.analyze(img_path)
            all_text = " ".join(t.text.lower() for t in ui.texts)

            for genre, keywords in self.GENRE_KEYWORDS.items():
                for kw in keywords:
                    if kw in all_text:
                        genre_scores[genre] += 1

        if max(genre_scores.values()) == 0:
            return "unknown"

        return max(genre_scores, key=genre_scores.get)


# ---------------------------------------------------------------------------
# UniversalRunner
# ---------------------------------------------------------------------------
class UniversalRunner:
    """범용 게임 테스터 메인 루프.

    사용법:
        # 알려진 게임
        runner = UniversalRunner("com.grandgames.carmatch")
        runner.run(duration_minutes=60)

        # 새 게임 (자동 온보딩)
        runner = UniversalRunner("com.newgame.example")
        runner.run(duration_minutes=60)
    """

    def __init__(
        self,
        package: str,
        game_id: Optional[str] = None,
        genre_id: Optional[str] = None,
        persona_id: str = "tester_bot",
        model: str = "claude-haiku-4-5-20251001",
        enable_llm: bool = True,
        temp_dir: Optional[Path] = None,
        log_file: Optional[Path] = None,
    ):
        self.package = package
        self.model = model
        self.enable_llm = enable_llm

        # 게임 ID
        info = KNOWN_GAMES.get(package, {})
        self.game_id = game_id or info.get("game_id", package.split(".")[-1])

        # 디렉토리
        self.temp_dir = temp_dir or Path(
            f"E:/AI/virtual_player/data/games/{self.game_id}/temp/universal"
        )
        self.log_file = log_file or Path(
            f"E:/AI/virtual_player/data/games/{self.game_id}/universal_log.txt"
        )

        # 장르
        genre_str = genre_id or info.get("genre")
        self.genre = None
        if genre_str and genre_str in list_genres():
            self.genre = load_genre(genre_str)

        # Playbook (알려진 게임이면 로드)
        self.playbook = _load_playbook_for_package(package)

        # 페르소나
        try:
            self.persona = load_persona(persona_id)
        except ValueError:
            self.persona = None
        if self.persona and self.playbook:
            self.persona.apply_to_playbook(self.playbook)

        # 레이어 초기화
        self.perception = Perception(model=model, game=self.game_id)
        self.memory = GameMemory()
        self.vision = UniversalVision()
        self.decision = GenericDecision(
            playbook=self.playbook,
            genre_profile=self.genre,
            vision=self.vision,
            llm_model=model,
            enable_llm=enable_llm,
        )
        self.executor = Executor(
            tap_fn=_adb_tap,
            back_fn=_adb_back,
            screenshot_fn=lambda: _adb_screenshot(self.temp_dir),
            relaunch_fn=lambda: _adb_relaunch(self.package),
            perception=self.perception,
            memory=self.memory,
        )

        self._running = False
        self._same_screen_count = 0
        self._last_screen: Optional[str] = None
        self._non_gameplay_streak = 0

    def run(self, duration_minutes: int = 60):
        """메인 루프 실행."""
        target = datetime.now() + timedelta(minutes=duration_minutes)
        self._log("=== Universal Game Runner START ===")
        self._log(f"Package: {self.package}")
        self._log(f"Game ID: {self.game_id}")
        self._log(f"Genre: {self.genre.genre_name if self.genre else 'auto-detect'}")
        self._log(f"Playbook: {'loaded' if self.playbook else 'auto-generate'}")
        self._log(f"LLM: {'enabled' if self.enable_llm else 'disabled'}")
        self._log(f"Target: {target.strftime('%H:%M:%S')}")
        self._running = True

        # 자동 온보딩 (Playbook 없으면)
        if not self.playbook:
            self._auto_onboard()

        try:
            self._game_loop(target)
        except KeyboardInterrupt:
            self._log("Interrupted by user")
        except Exception as e:
            self._log(f"FATAL: {e}")
        finally:
            self._running = False
            self._print_report()

    def _auto_onboard(self):
        """새 게임 자동 온보딩: 장르 추정 + Playbook 생성."""
        self._log("--- Auto-onboarding ---")

        from .playbook_generator import PlaybookGenerator

        gen = PlaybookGenerator(
            package=self.package,
            game_id=self.game_id,
            output_dir=self.temp_dir / "onboard",
        )

        # 스크린샷 5장 수집
        gen.collect_screens(num_screens=5, interval=3, auto_interact=True)

        # 장르 추정
        if not self.genre:
            detector = GenreDetector()
            screenshots = [s.img_path for s in gen.samples]
            genre_id = detector.detect_genre(screenshots)
            self._log(f"Detected genre: {genre_id}")
            if genre_id in list_genres():
                self.genre = load_genre(genre_id)
                self.decision.genre = self.genre

        # Playbook 생성
        self.playbook = gen.generate()
        self.decision.playbook = self.playbook
        gen.save_playbook(self.playbook)
        gen.save_report()

        self._log(f"Playbook generated: {len(self.playbook.screen_handlers)} handlers")

    def _game_loop(self, target: datetime):
        """메인 게임 루프."""
        current_board = None

        while datetime.now() < target:
            try:
                # Screenshot
                img = _adb_screenshot(self.temp_dir, "current")
                if not img:
                    self._log("Screenshot failed")
                    time.sleep(2)
                    continue

                # Perception
                t0 = time.time()
                board = self.perception.perceive(img)
                elapsed = time.time() - t0

                # UI 분석 (GenericDecision 용)
                self.decision.set_screenshot(img)

                self._log(
                    f"Screen: {board.screen_type} | "
                    f"Holder: {board.holder_count} | "
                    f"Vision: {elapsed:.1f}s"
                )

                # Stuck detection
                if board.screen_type == self._last_screen:
                    self._same_screen_count += 1
                else:
                    self._same_screen_count = 0
                self._last_screen = board.screen_type

                # Non-gameplay loop detection
                if board.screen_type in ("lobby", "gameplay"):
                    self._non_gameplay_streak = 0
                else:
                    self._non_gameplay_streak += 1

                if self._non_gameplay_streak >= 8:
                    self._log(">> POPUP LOOP, relaunch")
                    _adb_relaunch(self.package)
                    self._non_gameplay_streak = 0
                    self._same_screen_count = 0
                    self.decision.reset()
                    time.sleep(5)
                    continue

                if self._same_screen_count >= 200:
                    self._log(f">> STUCK RELAUNCH: {board.screen_type} x{self._same_screen_count}")
                    _adb_relaunch(self.package)
                    self._same_screen_count = 0
                    self.decision.reset()
                    time.sleep(5)
                    continue

                # Hearts wait
                if self.memory.is_heart_waiting():
                    remaining = int(self.memory.heart_wait_until - time.time())
                    self._log(f">> HEARTS WAIT: {remaining}s")
                    self._same_screen_count = 0
                    time.sleep(30)
                    continue

                # Lobby fail detection
                if board.screen_type == "lobby" and current_board:
                    if current_board.screen_type in ("lobby", "popup"):
                        self.memory.on_lobby_fail()
                        if self.memory.hearts_empty:
                            self.memory.start_heart_wait()
                            self._log(">> HEARTS EMPTY")
                            continue
                    elif current_board.screen_type == "gameplay":
                        self.memory.on_lobby_success()

                # Decision
                actions = self.decision.decide(board, self.memory)
                for a in actions:
                    self._log(f"  Plan: {a}")

                # Execute
                current_board = self.executor.execute(actions, board)

                # Stats
                if self.memory.total_turns % 10 == 0:
                    self._log(
                        f"--- Stats: {self.memory.games_won}W/"
                        f"{self.memory.games_failed}F | "
                        f"Taps: {self.memory.total_taps} | "
                        f"LLM: {self.decision.stats['llm_calls']} | "
                        f"Rules: {self.decision.stats['rule_calls']} ---"
                    )

            except Exception as e:
                self._log(f"ERROR: {e}")
                time.sleep(3)

    def _print_report(self):
        """세션 보고서 출력."""
        self._log("")
        self._log("=" * 50)
        self._log("SESSION COMPLETE")
        self._log("=" * 50)
        self._log(f"Package:        {self.package}")
        self._log(f"Game ID:        {self.game_id}")
        self._log(f"Genre:          {self.genre.genre_name if self.genre else 'unknown'}")
        self._log(f"Games started:  {self.memory.games_started}")
        self._log(f"Games won:      {self.memory.games_won}")
        self._log(f"Games failed:   {self.memory.games_failed}")
        self._log(f"Total taps:     {self.memory.total_taps}")
        self._log(f"Total turns:    {self.memory.total_turns}")
        self._log(f"Vision calls:   {self.perception.call_count}")
        self._log(f"LLM calls:      {self.decision.stats['llm_calls']}")
        self._log(f"Rule calls:     {self.decision.stats['rule_calls']}")

        stats = {
            "game": self.game_id,
            "package": self.package,
            "genre": self.genre.genre_id if self.genre else "unknown",
            "games_won": self.memory.games_won,
            "games_failed": self.memory.games_failed,
            "total_taps": self.memory.total_taps,
            "total_turns": self.memory.total_turns,
            "vision_calls": self.perception.call_count,
            "llm_calls": self.decision.stats["llm_calls"],
            "ended_at": datetime.now().isoformat(),
        }
        stats_path = self.temp_dir / "universal_stats.json"
        stats_path.parent.mkdir(parents=True, exist_ok=True)
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Universal Game Runner")
    parser.add_argument("package", help="Android package name (e.g. com.example.game)")
    parser.add_argument("duration", nargs="?", type=int, default=60,
                        help="Duration in minutes (default: 60)")
    parser.add_argument("--genre", type=str, default=None,
                        help=f"Genre override: {list_genres()}")
    parser.add_argument("--persona", type=str, default="tester_bot",
                        help="Player persona (default: tester_bot)")
    parser.add_argument("--model", type=str, default="claude-haiku-4-5-20251001",
                        help="Vision/LLM model")
    parser.add_argument("--no-llm", action="store_true",
                        help="Disable LLM gameplay decisions")
    parser.add_argument("--game-id", type=str, default=None,
                        help="Custom game ID")
    args = parser.parse_args()

    runner = UniversalRunner(
        package=args.package,
        game_id=args.game_id,
        genre_id=args.genre,
        persona_id=args.persona,
        model=args.model,
        enable_llm=not args.no_llm,
    )
    runner.run(duration_minutes=args.duration)


if __name__ == "__main__":
    main()
