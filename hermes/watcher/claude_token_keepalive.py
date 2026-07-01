#!/usr/bin/env python3
"""Claude OAuth 토큰 keep-alive 워치독.

배경
----
Hermes watcher는 `tool:claude` 역할(Lead/main_coder/reviewer 등)을 headless
`claude -p` 로 호출한다. Claude Max OAuth access token은 TTL이 약 8시간이며,
`claude` 를 호출하면 refreshToken 으로 자동 갱신된다.

문제(재발): 작업 큐가 8시간 넘게 비면 아무도 claude 를 호출하지 않아 토큰이
만료된 채 방치되고, 이후 들어온 작업이 401 로 조용히 실패한다(silent death).
2026-06-24, 2026-06-29 두 차례 다발.

대응(이 스크립트)
----------------
- expiresAt 이 THRESHOLD_HOURS 미만이면 cheap `claude -p` 를 호출해 선제 갱신.
- 갱신에 성공하면(=refreshToken 유효) 조용히 종료.
- 갱신에 실패하면(=refreshToken 사망 → 사람 재로그인 필요) Slack DM 발송.
  transient 오류 재알림 방지를 위해 dedup 상태파일 사용.

cron 예: `0 */2 * * *` (2시간마다) — TTL 8h, threshold 4h 이므로 매우 안전.
강제 테스트: `KEEPALIVE_FORCE=1 python claude_token_keepalive.py`

Slack 인프라는 boot-tripwire/capture.py 와 동일 패턴(projecthub_settings) 재사용.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CREDS_PATH = Path("/home/aimed/.claude/.credentials.json")
ENV_PATH = "/home/aimed/.hermes/watcher/.env"
STATE_PATH = Path("/home/aimed/.hermes/watcher/.claude_keepalive_state.json")
SLACK_TARGET_EMAIL = "jisu.park@gameberry.co.kr"

# 토큰 잔여시간이 이 값 미만이면 갱신 시도 (시간 단위). TTL 8h 대비 넉넉히.
THRESHOLD_HOURS = float(os.environ.get("KEEPALIVE_THRESHOLD_HOURS", "4"))
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} [keepalive] {msg}", flush=True)


def read_hours_left() -> float | None:
    try:
        d = json.loads(CREDS_PATH.read_text())
        o = d.get("claudeAiOauth", d)
        exp = float(o.get("expiresAt", 0)) / 1000.0
        return (exp - time.time()) / 3600.0
    except Exception as e:  # noqa: BLE001
        log(f"creds read fail: {e}")
        return None


def refresh_token() -> bool:
    """cheap claude 호출로 토큰 갱신. 성공 시 True."""
    try:
        r = subprocess.run(
            [CLAUDE_BIN, "-p", "reply with exactly: OK"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=90,
        )
        ok = r.returncode == 0 and "OK" in (r.stdout or "")
        if not ok:
            log(f"refresh call failed rc={r.returncode} err={(r.stderr or '')[:200]}")
        return ok
    except Exception as e:  # noqa: BLE001
        log(f"refresh exception: {e}")
        return False


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:  # noqa: BLE001
        return {}


def save_state(st: dict) -> None:
    try:
        STATE_PATH.write_text(json.dumps(st))
    except Exception as e:  # noqa: BLE001
        log(f"state write fail: {e}")


def send_slack_alert(hours_left: float | None) -> None:
    """refreshToken 사망 → 재로그인 필요 알림. dedup: 6h 이내 재알림 안 함."""
    st = load_state()
    now = time.time()
    last = float(st.get("last_alert_ts", 0))
    if now - last < 6 * 3600:
        log("alert deduped (sent < 6h ago)")
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        from pymongo import MongoClient  # type: ignore

        load_dotenv(ENV_PATH)
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            log("no MONGODB_URI — cannot alert")
            return
        db = MongoClient(uri, serverSelectionTimeoutMS=5000)[os.environ.get("MONGODB_DB", "aigame")]
        s = (db["projecthub_settings"].find_one({"key": "current"}) or {}).get("settings", {}) or {}
        webhooks = s.get("slack_assignee_webhooks") or []
        bot_token = s.get("slack_bot_token") or ""
        target = next(
            (w for w in webhooks if (w.get("email") or "").strip().lower() == SLACK_TARGET_EMAIL),
            None,
        )
        if not target or not target.get("slack_user_id") or not bot_token:
            log("no slack target/token — cannot alert")
            return
        hl = f"{hours_left:.1f}h" if hours_left is not None else "unknown"
        text = (
            ":rotating_light: *Claude OAuth 갱신 실패 — 재로그인 필요*\n"
            f"토큰 잔여: `{hl}` — 자동 갱신(refreshToken)이 실패했습니다.\n"
            "모든 `tool:claude` 에이전트(Lead/main_coder/reviewer)가 401로 정지됩니다.\n"
            "조치:\n"
            "```ssh aimed@100.77.190.68\n"
            "claude  # /login 으로 풀 OAuth 재인증 (TUI 실행+Ctrl-C는 갱신 안 됨)\n"
            "systemctl --user restart hermes-watcher.service```"
        )
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=json.dumps({"channel": target["slack_user_id"], "text": text}).encode(),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {bot_token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            log(f"Slack sent: {resp.read().decode()[:120]}")
        st["last_alert_ts"] = now
        save_state(st)
    except Exception as e:  # noqa: BLE001
        log(f"slack alert exception: {e}")


def main() -> int:
    force = os.environ.get("KEEPALIVE_FORCE") == "1"
    hours_left = read_hours_left()
    log(f"hours_left={hours_left if hours_left is None else round(hours_left, 1)} threshold={THRESHOLD_HOURS} force={force}")

    if hours_left is not None and hours_left >= THRESHOLD_HOURS and not force:
        log("token fresh — skip")
        return 0

    log("refreshing token via claude -p ...")
    if refresh_token():
        after = read_hours_left()
        log(f"refresh OK — hours_left now {after if after is None else round(after, 1)}")
        # 성공 시 alert dedup 리셋(다음 실패 즉시 알림 가능)
        st = load_state()
        if st.pop("last_alert_ts", None) is not None:
            save_state(st)
        return 0

    log("refresh FAILED — refreshToken likely dead, alerting")
    send_slack_alert(hours_left)
    return 1


if __name__ == "__main__":
    sys.exit(main())
