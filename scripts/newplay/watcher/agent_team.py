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


def _call_claude(prompt: str, timeout: int, cwd: Optional[str] = None,
                 model: str = "") -> tuple[bool, str, str]:
    """Claude Code CLI. 자격은 ~/.claude/.credentials.json (워크스테이션에서 미러됨).

    `--model` 을 반드시 넘긴다. 안 넘기면 CLI 기본 모델이 돌면서 DB·세션 로그에는
    역할에 적힌 모델명이 찍혀 **기록이 거짓말을 한다**
    (실측 2026-08-03: DB 는 claude-opus-4-7, 실제로는 claude-opus-4-8 이 돌고 있었다).
    """
    cmd = [CLAUDE_BIN, "-p", prompt]
    if model:
        cmd += ["--model", model]
    try:
        p = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=timeout,
            cwd=cwd or os.path.expanduser("~"),
        )
        if p.returncode != 0:
            return False, p.stdout or "", (p.stderr or f"claude exit {p.returncode}")[:400]
        return True, p.stdout or "", ""
    except FileNotFoundError:
        return False, "", f"claude CLI 없음 ({CLAUDE_BIN})"
    except subprocess.TimeoutExpired:
        return False, "", f"claude 타임아웃 ({timeout}s)"
    except Exception as e:  # noqa: BLE001
        return False, "", f"{type(e).__name__}: {e}"


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
    if tool == "claude":
        ok, out, err = _call_claude(full, tmo, cwd, model=model)
    else:
        ok, out, err = _call_litellm(model, full, tmo)
    dur = _now() - t0

    resp = AgentResponse(success=ok, output=out, error=err, model=model, tool=tool, duration_sec=dur)
    if ok:
        resp.structured = _extract_json(out)
    else:
        log.warning("[%s] 실패 (%s/%s): %s", role, tool, model, err[:200])
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
