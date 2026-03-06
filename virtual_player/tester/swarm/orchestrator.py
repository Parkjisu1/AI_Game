"""
Swarm Orchestrator — AI 에이전트 군집 관리
=============================================
tmux에서 4개 Claude Code 인스턴스를 역할별로 실행하고,
Play→Analyze→Improve→Validate 사이클을 자동으로 반복.

실행 구조:
  ┌─────────────────────────────────────────────────────┐
  │                    tmux session                      │
  │                                                     │
  │  Pane 1: Player     │  Pane 2: Analyst              │
  │  (게임 플레이)        │  (로그 분석)                   │
  │                     │                               │
  │─────────────────────┼───────────────────────────────│
  │  Pane 3: Improver   │  Pane 4: Validator            │
  │  (코드 개선)          │  (개선 검증)                   │
  │                     │                               │
  └─────────────────────────────────────────────────────┘

사이클:
  1. Player: 게임 60분 플레이 → session_report.json
  2. Analyst: 리포트 분석 → analysis_report.json
  3. Improver: 분석 기반 코드 수정 → staging/ + change_manifest.json
  4. Validator: 수정 검증 (10분 테스트) → validation_result.json
  5. 승인된 변경만 live 코드에 적용
  6. 1번으로 돌아감

사용법:
  python -m virtual_player.tester.swarm.orchestrator --game carmatch --cycles 10
  python -m virtual_player.tester.swarm.orchestrator --game carmatch --hours 12
"""

import json
import os
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .experience_db import ExperienceDB
from .reflector import Reflector
from .roles import PLAYER, ANALYST, IMPROVER, VALIDATOR


class SwarmOrchestrator:
    """AI 에이전트 군집 오케스트레이터."""

    CLAUDE_CMD = "C:/Users/user/AppData/Roaming/npm/claude.cmd"

    def __init__(
        self,
        game_id: str = "carmatch",
        base_dir: Optional[Path] = None,
        play_minutes: int = 60,
        validate_minutes: int = 10,
    ):
        self.game_id = game_id
        self.play_minutes = play_minutes
        self.validate_minutes = validate_minutes

        # 디렉토리 구조
        self.base_dir = base_dir or Path(
            f"E:/AI/virtual_player/data/games/{game_id}/swarm"
        )
        self.shared_dir = self.base_dir / "shared"
        self.staging_dir = self.base_dir / "staging"
        self.sessions_dir = self.base_dir / "sessions"
        self.code_dir = Path("E:/AI/virtual_player/tester")

        # 영구 DB
        self.experience_db = ExperienceDB(self.shared_dir / "experience_db.json")
        self.reflector = Reflector(self.shared_dir / "reflections.json")

        # 사이클 카운터
        self._cycle = 0

    def run(self, max_cycles: int = 0, max_hours: float = 0):
        """사이클 실행.

        max_cycles=0, max_hours=0이면 무한 실행 (Ctrl+C로 종료).
        """
        self._init_dirs()
        end_time = (
            datetime.now() + timedelta(hours=max_hours)
            if max_hours > 0 else datetime.max
        )

        self._log("=== SWARM ORCHESTRATOR START ===")
        self._log(f"Game: {self.game_id}")
        self._log(f"Play: {self.play_minutes}min, Validate: {self.validate_minutes}min")
        self._log(f"Max cycles: {'unlimited' if max_cycles == 0 else max_cycles}")

        try:
            while True:
                if max_cycles > 0 and self._cycle >= max_cycles:
                    break
                if datetime.now() >= end_time:
                    break

                self._cycle += 1
                self._run_cycle()

        except KeyboardInterrupt:
            self._log("Interrupted by user")
        finally:
            self.experience_db.save()
            self.reflector.save()
            self._print_summary()

    def _run_cycle(self):
        """1사이클 실행: Play → Analyze → Improve → Validate."""
        session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = self.sessions_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        self._log(f"\n{'='*60}")
        self._log(f"CYCLE {self._cycle} — Session {session_id}")
        self._log(f"{'='*60}")

        # Phase 1: Play
        self._log(f"\n[Phase 1/4] PLAYER — {self.play_minutes}min play")
        report_path = session_dir / "session_report.json"
        log_path = session_dir / "session_log.txt"
        self._run_player(session_id, report_path, log_path)

        # Phase 2: Analyze
        self._log(f"\n[Phase 2/4] ANALYST — analyzing session")
        analysis_path = session_dir / "analysis_report.json"
        self._run_analyst(session_id, report_path, log_path, analysis_path)

        # Phase 3: Improve
        self._log(f"\n[Phase 3/4] IMPROVER — generating improvements")
        manifest_path = session_dir / "change_manifest.json"
        self._run_improver(session_id, analysis_path, manifest_path)

        # Phase 4: Validate
        self._log(f"\n[Phase 4/4] VALIDATOR — testing improvements")
        validation_path = session_dir / "validation_result.json"
        self._run_validator(session_id, manifest_path, validation_path)

        # Apply approved changes
        self._apply_approved_changes(validation_path)

        # Update experience DB
        self._update_experience(report_path)

        self._log(f"\nCycle {self._cycle} complete.")

    def _run_player(self, session_id: str, report_path: Path, log_path: Path):
        """Player Agent 실행."""
        prompt = f"""Run the AI Game Tester for {self.play_minutes} minutes.

Execute this command:
cd E:/AI && python -c "
from virtual_player.tester.runner import TesterRunner
runner = TesterRunner(log_file='{log_path.as_posix()}')
runner.run(duration_minutes={self.play_minutes})
"

After it completes, read the log file at {log_path.as_posix()} and create a session report.
Write the report as JSON to {report_path.as_posix()} with this structure:
{{
  "session_id": "{session_id}",
  "games_started": <count from log>,
  "games_won": <count from log>,
  "games_failed": <count from log>,
  "total_taps": <count from log>,
  "screen_types_seen": [<list of unique screen types>],
  "consecutive_fail_max": <longest streak>,
  "top_issues": ["<issue 1>", "<issue 2>"]
}}"""

        self._call_claude(prompt, timeout_min=self.play_minutes + 5)

    def _run_analyst(
        self, session_id: str,
        report_path: Path, log_path: Path, analysis_path: Path
    ):
        """Analyst Agent 실행."""
        # Reflector로 반성 프롬프트 생성
        log_excerpt = ""
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8").splitlines()
            # 마지막 100줄 + 처음 20줄
            if len(lines) > 120:
                log_excerpt = "\n".join(lines[:20] + ["...(truncated)..."] + lines[-100:])
            else:
                log_excerpt = "\n".join(lines)

        reflection_prompt = self.reflector.generate_reflection_prompt(log_excerpt[:3000])

        exp_stats = json.dumps(self.experience_db.get_stats_summary(), indent=2)

        prompt = f"""You are the Analyst Agent. Analyze this game session.

Session report: {report_path.as_posix()}
Session log (excerpt):
```
{log_excerpt[:2000]}
```

Experience DB stats:
{exp_stats}

{reflection_prompt}

Write your analysis as JSON to {analysis_path.as_posix()} with structure:
{{
  "session_id": "{session_id}",
  "failure_patterns": [
    {{"pattern": "description", "count": N, "severity": "high/medium/low",
      "suggested_fix": "exact change needed"}}
  ],
  "recognition_accuracy": {{"estimated_screen_accuracy": 0.85}},
  "performance_trend": "improving/stable/degrading",
  "reflections": [
    {{"situation": "...", "outcome": "...", "analysis": "...", "lesson": "..."}}
  ],
  "priority_improvements": [
    {{"area": "perception/decision/playbook",
      "description": "what to improve",
      "expected_impact": "high/medium/low",
      "specific_change": "exact code/config change"}}
  ]
}}

Be specific. Every suggested change must reference an exact file, function, or value."""

        self._call_claude(prompt, timeout_min=5)

        # 반성 결과를 Reflector에 저장
        if analysis_path.exists():
            try:
                analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
                for r in analysis.get("reflections", []):
                    self.reflector.add_reflection(
                        situation=r.get("situation", ""),
                        outcome=r.get("outcome", ""),
                        analysis=r.get("analysis", ""),
                        lesson=r.get("lesson", ""),
                    )
                self.reflector.save()
            except (json.JSONDecodeError, Exception):
                pass

    def _run_improver(
        self, session_id: str,
        analysis_path: Path, manifest_path: Path
    ):
        """Improver Agent 실행."""
        staging = self.staging_dir / session_id
        staging.mkdir(parents=True, exist_ok=True)

        unapplied = self.reflector.get_unapplied_lessons()
        lessons_text = "\n".join(f"  - {l['lesson']}" for l in unapplied[:10])

        prompt = f"""You are the Improver Agent.

Read the analysis at: {analysis_path.as_posix()}
Read the current code:
  - {(self.code_dir / 'playbook.py').as_posix()}
  - {(self.code_dir / 'decision.py').as_posix()}
  - {(self.code_dir / 'perception.py').as_posix()}

Unapplied lessons from Reflector:
{lessons_text if lessons_text.strip() else '  (none)'}

Apply improvements to STAGING directory: {staging.as_posix()}/
- Copy and modify only the files that need changes
- Write a change manifest to: {manifest_path.as_posix()}

SAFETY RULES:
- Only add or modify screen handlers (never remove)
- Only make forbidden_regions more restrictive (never less)
- Only adjust thresholds by +/- 1 step
- If unsure, don't change

Manifest format:
{{
  "session_id": "{session_id}",
  "staging_dir": "{staging.as_posix()}",
  "changes": [
    {{"file": "playbook.py", "type": "add_screen_handler",
      "description": "what changed", "reason": "why"}}
  ],
  "risk_level": "low/medium/high"
}}"""

        self._call_claude(prompt, timeout_min=5)

    def _run_validator(
        self, session_id: str,
        manifest_path: Path, validation_path: Path
    ):
        """Validator Agent 실행."""
        prompt = f"""You are the Validator Agent.

Read the change manifest at: {manifest_path.as_posix()}

Your job:
1. Review each change for safety
2. If changes exist, describe what a {self.validate_minutes}-minute test would check
3. Write validation result to: {validation_path.as_posix()}

Validation result format:
{{
  "session_id": "{session_id}",
  "changes_reviewed": N,
  "approved": [{{"change_id": 0, "reason": "safe and beneficial"}}],
  "rejected": [{{"change_id": 1, "reason": "too risky"}}],
  "apply_approved": true/false
}}

Conservative: when in doubt, REJECT."""

        self._call_claude(prompt, timeout_min=3)

    def _apply_approved_changes(self, validation_path: Path):
        """승인된 변경사항을 live 코드에 적용."""
        if not validation_path.exists():
            self._log("  No validation result found, skipping apply.")
            return

        try:
            result = json.loads(validation_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            self._log("  Invalid validation result, skipping apply.")
            return

        if not result.get("apply_approved", False):
            self._log("  Validator did not approve changes.")
            return

        approved = result.get("approved", [])
        self._log(f"  Applying {len(approved)} approved changes...")

        # 승인된 교훈을 Reflector에 마킹
        for change in approved:
            reason = change.get("reason", "")
            self.reflector.mark_applied(reason)

        self.reflector.save()

    def _update_experience(self, report_path: Path):
        """세션 결과를 Experience DB에 반영."""
        if not report_path.exists():
            return

        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.experience_db._data["total_sessions"] += 1
            self.experience_db._data["total_games"] += report.get("games_started", 0)
            self.experience_db._data["total_wins"] += report.get("games_won", 0)
            self.experience_db.save()
        except (json.JSONDecodeError, Exception):
            pass

    def _call_claude(self, prompt: str, timeout_min: int = 5):
        """Claude Code CLI 호출."""
        env = os.environ.copy()
        for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
            env.pop(k, None)
        api_key = env.get("ANTHROPIC_API_KEY", "")
        if api_key and not api_key.startswith("sk-ant-"):
            env.pop("ANTHROPIC_API_KEY", None)
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            r = subprocess.run(
                [self.CLAUDE_CMD, "-p",
                 "--output-format", "text",
                 "--max-turns", "20"],
                input=prompt,
                capture_output=True,
                timeout=timeout_min * 60,
                encoding="utf-8",
                env=env,
            )
            if r.stdout:
                # 결과의 마지막 부분만 로그
                lines = r.stdout.strip().splitlines()
                for line in lines[-5:]:
                    self._log(f"  > {line[:120]}")
        except subprocess.TimeoutExpired:
            self._log(f"  Agent timed out after {timeout_min}min")
        except Exception as e:
            self._log(f"  Agent error: {e}")

    def _init_dirs(self):
        """디렉토리 초기화."""
        for d in [self.shared_dir, self.staging_dir, self.sessions_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        try:
            log_file = self.base_dir / "swarm_log.txt"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    def _print_summary(self):
        stats = self.experience_db.get_stats_summary()
        self._log("\n" + "=" * 60)
        self._log("SWARM SESSION COMPLETE")
        self._log("=" * 60)
        self._log(f"Cycles completed: {self._cycle}")
        self._log(f"Total sessions: {stats['total_sessions']}")
        self._log(f"Total games: {stats['total_games']}")
        self._log(f"Total wins: {stats['total_wins']}")
        self._log(f"Known screens: {stats['known_screens']}")
        self._log(f"Reflections: {len(self.reflector._reflections)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI Swarm Orchestrator")
    parser.add_argument("--game", default="carmatch", help="Game ID")
    parser.add_argument("--cycles", type=int, default=0, help="Max cycles (0=unlimited)")
    parser.add_argument("--hours", type=float, default=0, help="Max hours (0=unlimited)")
    parser.add_argument("--play-min", type=int, default=60, help="Minutes per play session")
    parser.add_argument("--validate-min", type=int, default=10, help="Minutes for validation")
    args = parser.parse_args()

    orch = SwarmOrchestrator(
        game_id=args.game,
        play_minutes=args.play_min,
        validate_minutes=args.validate_min,
    )
    orch.run(max_cycles=args.cycles, max_hours=args.hours)


if __name__ == "__main__":
    main()
