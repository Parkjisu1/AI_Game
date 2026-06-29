#!/usr/bin/env python3
"""
주기 골든 회귀 실행 (cron 전용) — hermes_eval_runs에 새 batch를 적재.

_golden_ok(prompt_self_improvement)이 이 결과를 읽어 '프롬프트 변경이 생성 품질을
떨어뜨렸는가'(회귀)를 판정한다. 절대 점수는 낮으니(생성형 필드매칭 ~0.21) 회귀 추세만 본다.

cron 예시 (주간, 일요일 18:00 UTC):
  0 18 * * 0 /home/aimed/.hermes/watcher/venv/bin/python \
    /home/aimed/.hermes/watcher/run_golden_eval.py \
    >> /home/aimed/.hermes/logs/golden_eval.log 2>&1

주의:
- claude OAuth(~/.claude/.credentials.json)가 유효해야 함(만료 시 401). refreshToken으로 자동갱신.
- agent_team._invoke_claude_code의 stdin=DEVNULL 덕에 cron(비대화) 컨텍스트에서 동작.
- 현재 골든 추출은 design_level_designer만 지원(harness/eval.py).
"""
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/aimed/.hermes/watcher")
from dotenv import load_dotenv
load_dotenv("/home/aimed/.hermes/watcher/.env")

from harness import eval as ev

ROLE = "design_level_designer"
MAX_CASES = 20

print("[%s] golden eval start: role=%s max=%d" % (
    datetime.now(timezone.utc).isoformat(), ROLE, MAX_CASES))
summary = ev.run_all_eval(role=ROLE, max_cases=MAX_CASES)
print("[%s] done: %d/%d passed, avg=%.3f, %ss" % (
    datetime.now(timezone.utc).isoformat(),
    summary.get("passed", 0), summary.get("total", 0),
    summary.get("avg_score", 0.0), summary.get("duration_sec", 0)))
