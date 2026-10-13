#!/usr/bin/env python3
"""Claude OAuth 토큰 keep-alive 워치독.

배경
----
Hermes watcher는 `tool:claude` 역할(Lead/main_coder/reviewer 등)을 headless
`claude -p` 로 호출한다. Claude Max OAuth access token은 TTL이 약 8시간이며,
refreshToken 으로 갱신된다.

문제(재발): 작업 큐가 8시간 넘게 비면 아무도 claude 를 호출하지 않아 토큰이
만료된 채 방치되고, 이후 들어온 작업이 401 로 조용히 실패한다(silent death).
2026-06-24, 2026-06-29 두 차례 다발.

2026-07-30 개편 — 왜 v1이 실패했나
----------------------------------
v1은 `claude -p "reply with exactly: OK"` 의 종료코드로 갱신 성공을 추론했다.
이 설계에 결함 3개가 있었다.

1) 거짓 성공: rc==0 && stdout에 "OK" 만 확인하고 expiresAt 이 실제로 전진했는지
   검증하지 않았다. 2026-07-29 14:00 로그가 증거 —
   `refresh OK — hours_left now 2.0` (성공이라 기록했으나 잔여시간 불변).
   실제 고장을 2시간 가려서 완전 만료까지 방치했다.
2) 오진: 갱신 실패 원인을 구분하지 못하고 전부 "refreshToken 사망 → 재로그인"
   으로 단정했다. 실제 2026-07-29 16:00 사고의 원인은 토큰 사망이 아니라
   OAuth 토큰 엔드포인트의 **계정 단위 HTTP 429 rate limit** 이었다.
   (Mother 100.77.190.68 과 머신B 100.92.43.9 양쪽 IP 모두 429 → IP 아닌 계정 단위)
   재로그인해도 429가 안 풀리면 무의미하므로 오진의 대가가 컸다.
3) 침묵: 429 상태의 `claude -p` 는 내부 재시도로 90초를 소모하고 stdout/stderr
   양쪽에 아무것도 남기지 않는다(rc=124 timeout, 출력 0바이트). 진단 불가.

v2 설계
-------
- 토큰 엔드포인트를 **직접 호출**(curl)하고 HTTP 상태코드로 판정한다.
  · urllib 은 Cloudflare 가 UA 기반으로 403(error 1010) 차단하므로 curl 사용.
- 결과를 3분류: ok / rate_limited / dead.
  · 429            → rate_limited. 재로그인 알림 **금지**, 백오프 후 재시도.
                     RATE_LIMIT_ALERT_AFTER_H 이상 지속될 때만 별도 문안으로 알림.
  · invalid_grant  → dead. 재로그인 알림.
    401/400
  · 그 외          → transient. 조용히 재시도(연속 실패 누적 시 알림).
- 갱신 후 expiresAt 이 **실제로 전진했는지 검증**한다. 안 밀렸으면 실패 처리.
- 크레덴셜은 백업 후 원자적 교체(tmp → os.replace), mode 600 유지,
  accessToken/refreshToken/expiresAt 만 갱신하고 나머지 필드는 보존.
- 동시 실행 락(flock)으로 중복 갱신 시도를 막는다. 429 재발 방지의 핵심.
- 갱신 성공 시 머신 B 로 **즉시 push**. B가 스스로 갱신을 시도하지 않도록
  (=계정 단위 429 유발원 제거) Mother 를 단일 갱신 주체로 만든다.

cron 예: `0 */2 * * *` (2시간마다) — TTL 8h, threshold 4h 이므로 안전.
강제 테스트: `KEEPALIVE_FORCE=1 python claude_token_keepalive.py`
드라이런  : `KEEPALIVE_DRY_RUN=1 ...` (판정만 하고 크레덴셜 미변경)

Slack 인프라는 boot-tripwire/capture.py 와 동일 패턴(projecthub_settings) 재사용.
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CREDS_PATH = Path("/home/aimed/.claude/.credentials.json")
ENV_PATH = "/home/aimed/.hermes/watcher/.env"
STATE_PATH = Path("/home/aimed/.hermes/watcher/.claude_keepalive_state.json")
LOCK_PATH = Path("/home/aimed/.hermes/watcher/.claude_keepalive.lock")
SLACK_TARGET_EMAIL = "jisu.park@gameberry.co.kr"

# Claude Code 공개 OAuth client id.
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

# 토큰 잔여시간이 이 값 미만이면 갱신 시도 (시간 단위). TTL 8h 대비 넉넉히.
THRESHOLD_HOURS = float(os.environ.get("KEEPALIVE_THRESHOLD_HOURS", "4"))

# 429가 이 시간 이상 연속되면 사람 개입 알림(문안은 재로그인이 아니라 '대기/조사').
RATE_LIMIT_ALERT_AFTER_H = float(os.environ.get("KEEPALIVE_RL_ALERT_AFTER_H", "6"))
IMMINENT_DEATH_ALERT_H = float(os.environ.get("KEEPALIVE_IMMINENT_DEATH_H", "2.0"))

# 토큰 회전의 주인(상류). 여기서 받아오는 것이 1순위 — 직접 갱신은 폴백일 뿐이다.
# refresh token 은 쓸 때마다 회전하므로 회전 주체는 계정당 하나여야 한다.
# 대화형 Claude Code 가 도는 워크스테이션(aimed-1)이 그 역할을 맡는다.
UPSTREAM_SOURCE = os.environ.get(
    "KEEPALIVE_UPSTREAM_SOURCE",
    "user@100.77.133.110:C:/Users/user/.claude/.credentials.json",
)

# 크레덴셜 미러 대상(쉼표 구분). 빈 문자열이면 push 생략.
#   - 머신 B(빌드PC)     : Hermes MCP / Unity 빌드
#   - aimed-sub          : NewPlay 워처의 tool="claude" 역할
# 이들은 **받기만** 한다. 스스로 갱신하면 refresh token 이 회전해 나머지가 전부 죽는다.
MIRROR_TARGET = os.environ.get(
    "KEEPALIVE_MIRROR_TARGET",
    'user@100.92.43.9:C:/Users/user/.claude/.credentials.json,'
    'aimed@100.87.87.59:/home/aimed/.claude/.credentials.json',
)
MIRROR_TARGETS = [t.strip() for t in MIRROR_TARGET.split(",") if t.strip()]

DRY_RUN = os.environ.get("KEEPALIVE_DRY_RUN") == "1"


def log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} [keepalive] {msg}", flush=True)


def read_creds() -> dict | None:
    try:
        return json.loads(CREDS_PATH.read_text())
    except Exception as e:  # noqa: BLE001
        log(f"creds read fail: {e}")
        return None


def hours_left_of(d: dict | None) -> float | None:
    if not d:
        return None
    try:
        o = d.get("claudeAiOauth", d)
        exp = float(o.get("expiresAt", 0)) / 1000.0
        return (exp - time.time()) / 3600.0
    except Exception as e:  # noqa: BLE001
        log(f"expiresAt parse fail: {e}")
        return None


def read_hours_left() -> float | None:
    return hours_left_of(read_creds())


def _post_token(refresh_tok: str) -> tuple[int, dict | str]:
    """토큰 엔드포인트 직접 호출. (http_status, parsed_body_or_raw) 반환.

    urllib 은 Cloudflare UA 차단(403 error 1010)을 받으므로 curl 을 쓴다.
    refreshToken 이 프로세스 목록에 노출되지 않도록 body 는 임시파일로 전달한다.
    """
    body = json.dumps(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_tok,
            "client_id": CLIENT_ID,
        }
    )
    bf = rf = None
    try:
        fd, bf = tempfile.mkstemp(prefix="oauth_body_", suffix=".json")
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(body)
        fd2, rf = tempfile.mkstemp(prefix="oauth_resp_", suffix=".json")
        os.close(fd2)
        os.chmod(rf, 0o600)

        r = subprocess.run(
            [
                "curl", "-s", "--max-time", "30",
                "-o", rf, "-w", "%{http_code}",
                "-X", "POST", TOKEN_URL,
                "-H", "Content-Type: application/json",
                "-d", "@" + bf,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        try:
            status = int((r.stdout or "").strip() or 0)
        except ValueError:
            status = 0
        if status == 0:
            return 0, f"curl failed rc={r.returncode} err={(r.stderr or '')[:200]}"
        raw = Path(rf).read_text()
        try:
            return status, json.loads(raw)
        except Exception:  # noqa: BLE001
            return status, raw[:300]
    except Exception as e:  # noqa: BLE001
        return 0, f"{type(e).__name__}: {e}"
    finally:
        for p in (bf, rf):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass


def _err_text(payload: dict | str) -> str:
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            return f"{err.get('type')}: {err.get('message')}"
        return f"{err} {payload.get('error_description', '')}".strip()
    return str(payload)[:200]


def _write_creds(orig: dict, tok: dict) -> None:
    """accessToken/refreshToken/expiresAt 만 갱신하고 나머지 필드는 보존."""
    new = json.loads(json.dumps(orig))  # deep copy
    o = new.get("claudeAiOauth")
    if o is None:
        o = new
    o["accessToken"] = tok["access_token"]
    if tok.get("refresh_token"):
        o["refreshToken"] = tok["refresh_token"]
    expires_in = float(tok.get("expires_in") or 0)
    if expires_in <= 0:
        raise ValueError("expires_in missing/invalid in token response")
    o["expiresAt"] = int((time.time() + expires_in) * 1000)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = CREDS_PATH.with_suffix(CREDS_PATH.suffix + f".bak.{stamp}")
    shutil.copy2(CREDS_PATH, backup)

    fd, tmp = tempfile.mkstemp(dir=str(CREDS_PATH.parent), prefix=".credentials_", suffix=".tmp")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(new, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, CREDS_PATH)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    log(f"creds updated (backup: {backup.name})")


def pull_from_upstream() -> tuple[str, str]:
    """상류에서 크레덴셜을 받아온다. (status, detail) 반환.

    status: ok | stale(상류가 더 낡거나 같음) | unavailable(가져오기 실패) | skipped
    상류 파일이 우리 것보다 유효기간이 길 때만 교체한다. 낡은 걸 덮어써서
    멀쩡한 토큰을 죽이는 사고를 막는 유일한 가드라 반드시 유지할 것.
    """
    if not UPSTREAM_SOURCE:
        return "skipped", "no upstream configured"

    fd, tmp = tempfile.mkstemp(prefix=".upstream_creds_", suffix=".json")
    os.close(fd)
    try:
        r = subprocess.run(
            ["scp", "-q", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes",
             "-o", "StrictHostKeyChecking=accept-new", UPSTREAM_SOURCE, tmp],
            capture_output=True, text=True, timeout=90,
        )
        if r.returncode != 0:
            return "unavailable", f"scp rc={r.returncode} {(r.stderr or '').strip()[:150]}"

        try:
            up = json.loads(Path(tmp).read_text())
        except Exception as e:  # noqa: BLE001
            return "unavailable", f"upstream creds unparsable: {type(e).__name__}"

        up_h = hours_left_of(up)
        if up_h is None:
            return "unavailable", "upstream creds have no expiresAt"

        cur_h = hours_left_of(read_creds())
        if cur_h is not None and up_h <= cur_h + 0.01:
            return "stale", f"upstream {up_h:.2f}h <= local {cur_h:.2f}h"
        if up_h <= 0:
            return "stale", f"upstream already expired ({up_h:.2f}h)"

        if DRY_RUN:
            return "ok", f"DRY_RUN — would install upstream ({cur_h} → {up_h:.2f}h)"

        # 원자적 교체 + 백업 (직접 갱신 경로와 동일한 안전장치)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        if CREDS_PATH.exists():
            shutil.copy2(CREDS_PATH, CREDS_PATH.with_suffix(CREDS_PATH.suffix + f".bak.{stamp}"))
        fd2, tmp2 = tempfile.mkstemp(dir=str(CREDS_PATH.parent), prefix=".credentials_", suffix=".tmp")
        try:
            os.fchmod(fd2, 0o600)
            with os.fdopen(fd2, "w") as fh:
                json.dump(up, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp2, CREDS_PATH)
        except Exception:
            try:
                os.remove(tmp2)
            except OSError:
                pass
            raise

        after = hours_left_of(read_creds())
        if after is None or (cur_h is not None and after <= cur_h + 0.01):
            return "unavailable", "post-install expiresAt did not advance"
        return "ok", f"hours_left {cur_h if cur_h is None else round(cur_h, 2)} -> {round(after, 2)}"
    except Exception as e:  # noqa: BLE001
        return "unavailable", f"{type(e).__name__}: {e}"
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


def refresh_token() -> tuple[str, str]:
    """토큰 갱신 시도. (status, detail) 반환.

    status: ok | rate_limited | dead | transient
    """
    d = read_creds()
    if not d:
        return "transient", "creds unreadable"
    o = d.get("claudeAiOauth", d)
    rt = o.get("refreshToken")
    if not rt:
        return "dead", "no refreshToken in credentials"

    before = hours_left_of(d)
    status, payload = _post_token(rt)

    if status == 429:
        return "rate_limited", _err_text(payload)
    if status in (400, 401):
        detail = _err_text(payload)
        if "invalid_grant" in detail or "invalid_request" in detail:
            return "dead", detail
        return "transient", f"http {status} — {detail}"
    if status != 200:
        return "transient", f"http {status} — {_err_text(payload)}"
    if not isinstance(payload, dict) or not payload.get("access_token"):
        return "transient", f"http 200 but no access_token — {str(payload)[:150]}"

    if DRY_RUN:
        return "ok", f"DRY_RUN — would set expires_in={payload.get('expires_in')}"

    try:
        _write_creds(d, payload)
    except Exception as e:  # noqa: BLE001
        return "transient", f"creds write failed: {type(e).__name__}: {e}"

    # v1의 핵심 결함 보완: expiresAt 이 실제로 전진했는지 검증.
    after = hours_left_of(read_creds())
    if after is None:
        return "transient", "post-write creds unreadable"
    if before is not None and after <= before + 0.01:
        return "transient", f"expiresAt did not advance ({before:.2f}h → {after:.2f}h)"
    return "ok", f"hours_left {before if before is None else round(before, 2)} → {round(after, 2)}"


def mirror_to_machine_b() -> None:
    """갱신/동기화 성공 즉시 모든 미러 대상에 push.

    한 대상이 꺼져 있어도 나머지는 계속 진행한다 — 노트북 한 대 때문에
    다른 머신이 죽은 토큰을 들고 있게 되면 안 된다.
    """
    if not MIRROR_TARGETS or DRY_RUN:
        return
    for target in MIRROR_TARGETS:
        name = target.split(":")[0]
        try:
            r = subprocess.run(
                ["scp", "-q", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes",
                 str(CREDS_PATH), target],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if r.returncode == 0:
                log(f"mirror → {name} OK")
            else:
                log(f"mirror → {name} FAILED rc={r.returncode} err={(r.stderr or '')[:200]}")
        except Exception as e:  # noqa: BLE001
            log(f"mirror → {name} exception: {type(e).__name__}: {e}")


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


def send_slack_alert(kind: str, hours_left: float | None, detail: str) -> None:
    """kind: dead(재로그인 필요) | rate_limited(대기/조사) | transient(반복 실패).

    dedup: 동일 kind 6h 이내 재알림 안 함.
    """
    st = load_state()
    now = time.time()
    last = float(st.get(f"last_alert_ts::{kind}", st.get("last_alert_ts", 0)))
    if now - last < 6 * 3600:
        log(f"alert deduped (kind={kind}, sent < 6h ago)")
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        from pymongo import MongoClient  # type: ignore

        load_dotenv(ENV_PATH)
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            log("no MONGODB_URI — cannot alert")
            return
        # v1은 5s 고정이라 Atlas 리플리카셋 선출 중 알림이 통째로 유실됐다
        # (2026-07-29 16:00 / 2026-07-30 02:00 ReplicaSetNoPrimary). 여유 + 재시도.
        client = MongoClient(uri, serverSelectionTimeoutMS=20000)
        db = client[os.environ.get("MONGODB_DB", "aigame")]
        s = None
        for attempt in range(3):
            try:
                s = (db["projecthub_settings"].find_one({"key": "current"}) or {}).get("settings", {}) or {}
                break
            except Exception as e:  # noqa: BLE001
                log(f"mongo attempt {attempt + 1}/3 failed: {type(e).__name__}")
                time.sleep(5)
        if s is None:
            log("mongo unreachable after 3 attempts — cannot alert")
            return
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
        if kind == "dead":
            text = (
                ":rotating_light: *Claude OAuth — 재로그인 필요*\n"
                f"토큰 잔여: `{hl}` / 토큰 엔드포인트 응답: `{detail[:150]}`\n"
                "refreshToken 이 무효(invalid_grant)입니다. 재인증 외 복구 경로 없음.\n"
                "모든 `tool:claude` 에이전트(Lead/main_coder/reviewer)가 401로 정지됩니다.\n"
                "조치:\n"
                "```ssh aimed@100.77.190.68\n"
                "claude  # /login 으로 풀 OAuth 재인증 (TUI 실행+Ctrl-C는 갱신 안 됨)\n"
                "systemctl --user restart hermes-watcher.service```"
            )
        elif kind == "rate_limited":
            text = (
                ":warning: *Claude OAuth — 갱신이 rate limit 으로 계속 막힘*\n"
                f"토큰 잔여: `{hl}` / 응답: `{detail[:150]}`\n"
                f"{RATE_LIMIT_ALERT_AFTER_H:.0f}시간 이상 429 지속. **재로그인해도 안 풀립니다.**\n"
                "**429 는 대개 레이트리밋이 아니라 회전에서 밀려난 refresh token 입니다.**\n"
                "refresh token 은 쓸 때마다 회전하므로 회전 주체는 계정당 하나여야 하고,\n"
                "그 주인은 워크스테이션(`aimed-1`)입니다. Mother 는 받아오기만 해야 합니다.\n"
                "여기까지 왔다는 건 상류 받아오기도 실패했다는 뜻입니다.\n"
                "```ssh aimed@100.77.190.68\n"
                "tail -50 ~/.hermes/logs/claude_keepalive.log```"
            )
        elif kind == "upstream_down":
            text = (
                ":warning: *Claude OAuth — 상류(워크스테이션)에서 토큰을 못 받아옴*\n"
                f"토큰 잔여: `{hl}` / 사유: `{detail[:150]}`\n"
                "Mother 는 토큰을 직접 갱신하지 않고 워크스테이션(`aimed-1` 100.77.133.110)에서 받아옵니다.\n"
                "그 PC 가 꺼져 있거나 SSH 가 막히면 이 알림이 뜹니다.\n"
                "조치: aimed-1 전원/타일스케일 확인 → 켜지면 자동 복구됩니다.\n"
                "```ssh aimed@100.77.190.68\n"
                "tail -30 ~/.hermes/logs/claude_keepalive.log```"
            )
        elif kind == "imminent_death":
            text = (
                ":rotating_light: *Claude OAuth — 곧 만료되는데 갱신이 안 됨(침묵사망 임박)*\n"
                f"토큰 잔여: `{hl}` / 응답: `{detail[:150]}`\n"
                "만료되면 모든 `tool:claude` 에이전트가 401 로 조용히 정지합니다(6월과 동일).\n"
                "회전 교착(429)은 재인증으로만 풀립니다.\n"
                "조치: 워크스테이션(`aimed-1`)에서 `claude` 재로그인 → Mother 가 pull.\n"
                "```ssh aimed@100.77.190.68\n"
                "tail -50 ~/.hermes/logs/claude_keepalive.log```"
            )
        else:
            text = (
                ":warning: *Claude OAuth 갱신 반복 실패(원인 불명)*\n"
                f"토큰 잔여: `{hl}` / 응답: `{detail[:150]}`\n"
                "```ssh aimed@100.77.190.68\n"
                "tail -50 ~/.hermes/logs/claude_keepalive.log```"
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
            log(f"Slack sent ({kind}): {resp.read().decode()[:120]}")
        st[f"last_alert_ts::{kind}"] = now
        save_state(st)
    except Exception as e:  # noqa: BLE001
        log(f"slack alert exception: {type(e).__name__}: {e}")


def acquire_lock():
    """중복 갱신 시도 차단. 429 재발 방지의 핵심."""
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_PATH, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fh.close()
        return None
    return fh


def main() -> int:
    force = os.environ.get("KEEPALIVE_FORCE") == "1"
    hours_left = read_hours_left()
    log(
        f"hours_left={hours_left if hours_left is None else round(hours_left, 1)} "
        f"threshold={THRESHOLD_HOURS} force={force} dry_run={DRY_RUN}"
    )

    # 상류는 매 실행마다 본다. threshold 로 막으면 워크스테이션이 이미 회전했는데도
    # "내 토큰 4시간 남았으니 됐다"며 넘어가고, 그 사이 CLI 가 만료를 맞아 자격 파일을 깨뜨린다
    # (2026-08-03: expiresAt 이 -496044h 가 되고 claude 가 "Not logged in" 이 됐다).
    # scp 한 번은 싸다. pull_from_upstream 은 상류가 더 신선할 때만 교체하므로 안전하다.
    if hours_left is not None and hours_left >= THRESHOLD_HOURS and not force:
        up_status, up_detail = pull_from_upstream()
        log(f"upstream pull={up_status} detail={up_detail} (token fresh path)")
        if up_status == "ok":
            mirror_to_machine_b()
        return 0

    lock = acquire_lock()
    if lock is None:
        log("another keepalive run holds the lock — skip (avoids duplicate refresh → 429)")
        return 0

    try:
        # 1순위: 상류에서 받아오기. 성공하면 갱신 시도 자체를 하지 않는다.
        # (Mother 가 갱신하면 refresh token 이 회전해 워크스테이션 쪽이 죽는다)
        up_status, up_detail = pull_from_upstream()
        log(f"upstream pull={up_status} detail={up_detail}")
        if up_status == "ok":
            st = load_state()
            for k in list(st):
                if k.startswith("last_alert_ts") or k in ("rate_limited_since", "consecutive_failures"):
                    st.pop(k, None)
            save_state(st)
            mirror_to_machine_b()
            return 0
        if up_status == "unavailable":
            st = load_state()
            since = float(st.get("upstream_down_since") or time.time())
            st["upstream_down_since"] = since
            save_state(st)
            if (time.time() - since) / 3600.0 >= RATE_LIMIT_ALERT_AFTER_H:
                send_slack_alert("upstream_down", hours_left, up_detail)
        else:
            st = load_state()
            if st.pop("upstream_down_since", None) is not None:
                save_state(st)

        # 2순위(폴백): 직접 갱신. 상류가 죽었을 때만 여기까지 온다.
        log("refreshing token via OAuth token endpoint ...")
        status, detail = refresh_token()
        log(f"refresh result={status} detail={detail}")

        st = load_state()
        if status == "ok":
            for k in list(st):
                if k.startswith("last_alert_ts") or k in ("rate_limited_since", "consecutive_failures"):
                    st.pop(k, None)
            save_state(st)
            mirror_to_machine_b()
            return 0

        if status == "rate_limited":
            since = float(st.get("rate_limited_since") or time.time())
            st["rate_limited_since"] = since
            save_state(st)
            stuck_h = (time.time() - since) / 3600.0
            log(f"rate limited for {stuck_h:.1f}h (alert threshold {RATE_LIMIT_ALERT_AFTER_H}h)")
            # 재로그인 알림 금지 — 재로그인해도 429는 안 풀린다.
            if stuck_h >= RATE_LIMIT_ALERT_AFTER_H:
                send_slack_alert("rate_limited", hours_left, detail)
            # 잔여시간 기반 임박 경보: 누적 rate-limit 창(<=4h)이 경보 임계(6h)보다
            # 짧아 침묵사망을 못 알리던 결함 보완 — 만료 임박+갱신 실패면 즉시 알림.
            if hours_left is not None and hours_left < IMMINENT_DEATH_ALERT_H:
                send_slack_alert("imminent_death", hours_left, detail)
            return 1

        if status == "dead":
            send_slack_alert("dead", hours_left, detail)
            return 1

        fails = int(st.get("consecutive_failures") or 0) + 1
        st["consecutive_failures"] = fails
        save_state(st)
        log(f"transient failure #{fails}")
        if fails >= 3:
            send_slack_alert("transient", hours_left, detail)
        return 1
    finally:
        try:
            fcntl.flock(lock, fcntl.LOCK_UN)
            lock.close()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    sys.exit(main())
