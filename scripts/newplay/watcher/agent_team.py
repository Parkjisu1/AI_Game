"""agent_team.py — NewPlay 에이전트 호출 계층.

역할 정의(모델·페르소나)는 newteam DB 의 hermes_agent_roles 에서 읽는다.
호출 경로는 두 가지다.
  tool="litellm" → Mother 의 LiteLLM 게이트웨이(:4000). 모델: sub-coder-agent / validator-agent / gpt-4o …
  tool="claude"  → 로컬 Claude Code CLI (`claude -p`).

게임팀 agent_team.py 를 그대로 가져오지 않은 이유:
  그쪽은 Unity/BalloonFlow 전용 프롬프트 템플릿 20여 개와 레벨 생성기·아트 파이프라인이
  얽혀 있어서, 결제 웹 플랫폼에 옮기면 쓰지도 않을 코드가 오작동할 여지만 커진다.
  여기서는 "역할 하나를 페르소나와 함께 부른다"는 최소 계약만 구현한다.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

import requests
from pymongo import MongoClient

log = logging.getLogger("newplay-agent")

MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("MONGODB_DB", "newteam")
LITELLM_URL = os.environ.get("LITELLM_URL", "http://100.77.190.68:4000")
LITELLM_KEY = os.environ.get("LITELLM_MASTER_KEY", "")
CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")
DEFAULT_TIMEOUT = int(os.environ.get("NEWPLAY_AGENT_TIMEOUT", "300"))

# 역할 캐시 — 매 호출마다 DB 를 때리지 않되, UI 에서 페르소나를 고치면 곧 반영되도록 짧게 잡는다.
_ROLE_CACHE: dict[str, Any] = {"ts": 0.0, "rows": {}}
_ROLE_TTL = 10.0


@dataclass
class AgentResponse:
    success: bool
    output: str = ""
    error: str = ""
    model: str = ""
    tool: str = ""
    structured: Optional[dict[str, Any]] = None
    duration_sec: float = 0.0
    #: 실제로 호출에 쓴 Claude 계정(이메일). "" = CLI 로그인 자격 또는 claude 가 아닌 도구
    account: str = ""


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def load_roles(force: bool = False) -> dict[str, dict[str, Any]]:
    """role 이름 → 역할 문서. archived 는 제외한다."""
    if not force and _ROLE_CACHE["rows"] and (_now() - _ROLE_CACHE["ts"]) < _ROLE_TTL:
        return _ROLE_CACHE["rows"]
    try:
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        rows = list(cli[DB_NAME]["hermes_agent_roles"].find({"archived": {"$ne": True}}))
        cli.close()
        _ROLE_CACHE["rows"] = {str(r.get("role")): r for r in rows if r.get("role")}
        _ROLE_CACHE["ts"] = _now()
    except Exception as e:  # noqa: BLE001
        log.warning("역할 로드 실패(캐시 유지): %s: %s", type(e).__name__, e)
    return _ROLE_CACHE["rows"]


def sub_teams_of(team: str) -> list[str]:
    """DB 에 실제로 존재하는 분과 목록. UI 에서 분과를 늘리면 자동 반영된다."""
    rows = load_roles()
    subs = {str(r.get("sub_team") or "general") for r in rows.values() if r.get("team") == team}
    return sorted(subs)


def _extract_json(text: str) -> Optional[dict[str, Any]]:
    """응답에서 JSON 블록을 뽑는다. 모델이 설명을 덧붙여도 살아남게."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fenced.group(1)] if fenced else []
    # 가장 바깥 중괄호 덩어리
    first, last = text.find("{"), text.rfind("}")
    if first >= 0 and last > first:
        candidates.append(text[first:last + 1])
    for c in candidates:
        try:
            v = json.loads(c)
            if isinstance(v, dict):
                return v
        except Exception:  # noqa: BLE001
            continue
    return None


def _call_litellm(model: str, prompt: str, timeout: int) -> tuple[bool, str, str]:
    if not LITELLM_KEY:
        return False, "", "LITELLM_MASTER_KEY 미설정"
    try:
        r = requests.post(
            f"{LITELLM_URL}/v1/chat/completions",
            headers={"Authorization": f"Bearer {LITELLM_KEY}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=timeout,
        )
        if r.status_code != 200:
            return False, "", f"litellm {r.status_code}: {r.text[:300]}"
        return True, (r.json()["choices"][0]["message"]["content"] or ""), ""
    except Exception as e:  # noqa: BLE001
        return False, "", f"{type(e).__name__}: {e}"


import threading

import claude_pool

# 지금 처리 중인 작업을 낸 사람(이메일). 스레드마다 다르다 — 검수 풀은 별도 스레드에서 돈다.
_actor = threading.local()


def set_actor(email: str) -> None:
    """이 스레드에서 이후 Claude 호출이 어느 팀원 계정으로 나갈지 정한다. 실행기가 작업 시작 시 부른다."""
    _actor.email = (email or "").strip().lower()


def current_actor() -> str:
    return getattr(_actor, "email", "") or ""


#: 인증 실패 문구 (실측 2026-09-14, claude 2.1.197, 둘 다 stdout·exit 1):
#:   "Not logged in · Please run /login"
#:   "Failed to authenticate. API Error: 401 OAuth access token is invalid."
_AUTH_FAIL = ("not logged in", "failed to authenticate", "oauth access token", "401", "invalid api key")
#: 플랜에 없는 모델을 요구했을 때 — 한 단계 낮춰 재시도한다 (Pro 플랜엔 Opus 가 없다)
_MODEL_FALLBACK = os.environ.get("NEWPLAY_CLAUDE_MODEL_FALLBACK", "claude-sonnet-5")
_MODEL_FAIL = ("model", "not available", "does not have access", "permission")


def _run_claude_once(prompt: str, timeout: int, cwd: Optional[str], model: str,
                     token: Optional[str], extra_args: Optional[list[str]] = None) -> tuple[bool, str, str, int]:
    cmd = [CLAUDE_BIN, "-p", prompt]
    if model:
        cmd += ["--model", model]
    if extra_args:
        cmd += list(extra_args)
    env = dict(os.environ)
    if token:
        env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    else:
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=cwd or os.path.expanduser("~"), env=env)
        if p.returncode != 0:
            return False, p.stdout or "", ((p.stderr or "") + " " + (p.stdout or ""))[:400] or f"claude exit {p.returncode}", p.returncode
        return True, p.stdout or "", "", 0
    except FileNotFoundError:
        return False, "", f"claude CLI 없음 ({CLAUDE_BIN})", -1
    except subprocess.TimeoutExpired:
        return False, "", f"claude 타임아웃 ({timeout}s)", -2
    except Exception as e:  # noqa: BLE001
        return False, "", f"{type(e).__name__}: {e}", -3


def _call_claude(prompt: str, timeout: int, cwd: Optional[str] = None,
                 model: str = "", extra_args: Optional[list[str]] = None) -> tuple[bool, str, str, str]:
    """Claude Code CLI. 자격은 **작업을 낸 사람의 토큰**(claude_pool) → 팀 공용 → CLI 로그인 순.

    `--model` 을 반드시 넘긴다. 안 넘기면 CLI 기본 모델이 돌면서 DB·세션 로그에는
    역할에 적힌 모델명이 찍혀 **기록이 거짓말을 한다**
    (실측 2026-08-03: DB 는 claude-opus-4-7, 실제로는 claude-opus-4-8 이 돌고 있었다).

    돌려주는 4번째 값 = 실제로 쓴 계정(이메일, "" 는 CLI 로그인). 세션 로그에 남긴다.
    한도 문구가 보이면 그 계정을 쉬게 하고 다음 후보로, 인증 실패면 그 계정을 건너뛰고 다음 후보로.
    플랜에 없는 모델이면 같은 계정으로 폴백 모델 1회.
    """
    attempts: list[str] = []
    for account, token in claude_pool.candidates(current_actor()):
        ok, out, err, rc = _run_claude_once(prompt, timeout, cwd, model, token, extra_args)
        if ok:
            return True, out, "", account
        low = (err or "").lower()
        if rc == -1 or rc == -2:
            return False, out, err, account
        if claude_pool.looks_limited(low):
            claude_pool.mark_limited(account or "_login")
            attempts.append(f"[{account or 'login'}] 한도: {err[:120]}")
            continue
        if any(k in low for k in _AUTH_FAIL):
            attempts.append(f"[{account or 'login'}] 인증 실패: {err[:120]}")
            continue
        if model and model != _MODEL_FALLBACK and any(k in low for k in _MODEL_FAIL):
            ok2, out2, err2, _ = _run_claude_once(prompt, timeout, cwd, _MODEL_FALLBACK, token, extra_args)
            if ok2:
                log.warning("[%s] 모델 %s 불가 → %s 로 실행", account or "login", model, _MODEL_FALLBACK)
                return True, out2, "", account
            attempts.append(f"[{account or 'login'}] {err2[:120]}")
            continue
        # 그 밖의 실패는 계정 문제가 아니다 — 다른 계정으로 돌려봐야 같다
        return False, out, err, account
    return False, "", ("Claude 계정 전부 실패: " + " | ".join(attempts)) if attempts else "Claude 자격 없음", ""


def invoke(role: str, prompt: str, timeout: Optional[int] = None,
           cwd: Optional[str] = None, want_json: bool = False) -> AgentResponse:
    """역할 하나를 호출한다. 페르소나는 프롬프트 최상단에 주입된다."""
    rows = load_roles()
    r = rows.get(role)
    if not r:
        return AgentResponse(False, error=f"역할 '{role}' 이 hermes_agent_roles 에 없습니다")

    tool = str(r.get("tool") or "litellm").lower()
    model = str(r.get("model") or "sub-coder-agent")
    persona = str(r.get("persona") or "").strip()
    tmo = timeout or DEFAULT_TIMEOUT

    full = prompt
    if persona:
        full = f"# 너의 역할\n{persona}\n\n---\n\n{prompt}"
    if want_json:
        full += "\n\n반드시 JSON 객체 하나만 반환한다. 설명 문장을 덧붙이지 마라."

    t0 = _now()
    account = ""
    if tool == "claude":
        ok, out, err, account = _call_claude(full, tmo, cwd, model=model)
    else:
        ok, out, err = _call_litellm(model, full, tmo)
    dur = _now() - t0

    resp = AgentResponse(success=ok, output=out, error=err, model=model, tool=tool,
                         duration_sec=dur, account=account)
    if ok:
        resp.structured = _extract_json(out)
    else:
        log.warning("[%s] 실패 (%s/%s): %s", role, tool, model, err[:200])
    return resp


#: 에이전트 모드에서 허용하는 도구. worktree 는 일회용이라 Bash 까지 연다(테스트·빌드 실행용).
#: 원격 push 는 사람이 고른 뒤 워처가 한다 — 작업자 프롬프트에 "commit/push 금지" 를 박는다.
AGENT_TOOLS = os.environ.get("NEWPLAY_AGENT_TOOLS", "Read,Edit,Write,MultiEdit,Glob,Grep,Bash").split(",")
AGENT_MAX_TURNS = int(os.environ.get("NEWPLAY_AGENT_MAX_TURNS", "80"))


def invoke_agentic(role: str, prompt: str, cwd: str, timeout: Optional[int] = None) -> AgentResponse:
    """역할을 **worktree 안에서 도구를 쓰는 에이전트**로 호출한다 (로컬 Claude Code 와 같은 방식).

    `claude -p` 에 --allowedTools 를 주면 비대화형에서도 파일 편집·명령 실행이 된다.
    --output-format json 으로 최종 답·비용·턴 수를 구조화해 받는다. 계정·폴백 규칙은 invoke 와 같다.
    """
    import json as _json
    rows = load_roles()
    r = rows.get(role)
    if not r:
        return AgentResponse(False, error=f"역할 '{role}' 이 hermes_agent_roles 에 없습니다")
    model = str(r.get("model") or "claude-sonnet-5")
    persona = str(r.get("persona") or "").strip()
    tmo = timeout or DEFAULT_TIMEOUT
    full = (f"# 너의 역할\n{persona}\n\n---\n\n{prompt}") if persona else prompt
    extra = ["--allowedTools", *AGENT_TOOLS, "--max-turns", str(AGENT_MAX_TURNS), "--output-format", "json"]
    t0 = _now()
    ok, out, err, account = _call_claude(full, tmo, cwd, model=model, extra_args=extra)
    dur = _now() - t0
    text, meta = out, {}
    if ok:
        try:
            j = _json.loads(out)
            if isinstance(j, dict):
                text = str(j.get("result") or "")
                meta = {k: j.get(k) for k in ("num_turns", "total_cost_usd", "duration_ms", "is_error", "subtype") if k in j}
                if j.get("is_error"):
                    ok = False
                    err = f"agent error: {text[:300]}"
        except Exception:  # noqa: BLE001
            pass  # json 이 아니면 원문 그대로
    resp = AgentResponse(success=ok, output=text, error=err, model=model, tool="claude-agent",
                         duration_sec=dur, account=account)
    resp.structured = meta or None
    if not ok:
        log.warning("[%s] 에이전트 실패 (%s): %s", role, model, err[:200])
    return resp


def log_session(task: dict[str, Any], role: str, resp: AgentResponse, prompt: str) -> None:
    """hermes_agent_sessions 기록 — /agents 화면의 실시간 활동 피드가 이걸 읽는다."""
    try:
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        cli[DB_NAME]["hermes_agent_sessions"].insert_one({
            "task_id": str(task.get("_id")),
            "task_title": task.get("title", ""),
            "role": role,
            "model": resp.model,
            "tool": resp.tool,
            "account": resp.account,
            "success": resp.success,
            "error": resp.error[:500] if resp.error else "",
            "duration_sec": round(resp.duration_sec, 2),
            "output_len": len(resp.output or ""),
            "output_preview": (resp.output or "")[:2000],
            "prompt_preview": (prompt or "")[:2000],
            "created_at": datetime.now(timezone.utc),
        })
        cli.close()
    except Exception as e:  # noqa: BLE001
        log.warning("세션 기록 실패: %s: %s", type(e).__name__, e)
