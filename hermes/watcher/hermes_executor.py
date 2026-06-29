"""
Hermes Executor — 라우팅 결정된 action을 실제 실행

실행 도구별 분기:
  - db_query       : 직접 MongoDB 쿼리 (pymongo)
  - simulation     : scripts/balance-simulator.js subprocess 호출
  - apk_build      : SSH to 머신 B (paramiko 또는 subprocess)
  - gameforge_*    : Mother 로컬에서 `claude -p "/generate-..."` 호출
  - training       : Mother 로컬에서 Python 학습 스크립트 호출
  - chat           : Hermes CLI `hermes --print "..."` 호출
  - review_needed  : 실행 없이 사람 개입 요청 메시지만

Phase 1(현재) 구현: db_query, simulation, apk_build, chat, review_needed
Phase 2+: gameforge_*, training (Claude Code 비대화 모드 필요)
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any

from pymongo import MongoClient

log = logging.getLogger("hermes-executor")


# ──────────────────────────────────────────────
# 환경 설정
# ──────────────────────────────────────────────
MONGO_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("MONGODB_DB", "aigame")

GAMEFORGE_ROOT = Path(os.environ.get("GAMEFORGE_ROOT", "/home/aimed/gameforge"))
MACHINE_B_HOST = os.environ.get("MACHINE_B_HOST", "user@100.92.43.9")
MACHINE_B_PROJECT_DIR = os.environ.get("MACHINE_B_PROJECT_DIR", "C:/projects/balloonflow")
MACHINE_B_UNITY_DIR = os.environ.get("MACHINE_B_UNITY_DIR", "C:/projects/balloonflow/BalloonFlow")
HERMES_BRANCH_PREFIX = os.environ.get("HERMES_BRANCH_PREFIX", "hermes/")
GITHUB_REPO_OWNER = os.environ.get("GITHUB_REPO_OWNER", "jisupark-tech")
GITHUB_REPO_NAME = os.environ.get("GITHUB_REPO_NAME", "BalloonFlow")

# ──────────────────────────────────────────────
# Multi-repo: sub_team별 레포 라우팅
# ──────────────────────────────────────────────
# 기본 레포 (BalloonFlow Unity, 머신 B). sub_team override가 없으면 이걸 사용.
DEFAULT_REPO = {
    "host":  MACHINE_B_HOST,
    "dir":   MACHINE_B_PROJECT_DIR,
    "owner": GITHUB_REPO_OWNER,
    "repo":  GITHUB_REPO_NAME,
    "type":  "unity",
}

# sub_team별 override — env vars로만 활성화. host + dir 둘 다 있어야 등록됨.
#   HERMES_REPO_<SUBTEAM>_HOST   (예: user@100.92.43.9, aimed@100.77.190.68)
#   HERMES_REPO_<SUBTEAM>_DIR    (절대 경로 — Windows: "C:/projects/foo", Linux: "/home/aimed/foo")
#   HERMES_REPO_<SUBTEAM>_OWNER  (옵션 — 미지정 시 기본 owner)
#   HERMES_REPO_<SUBTEAM>_NAME   (옵션 — 미지정 시 기본 repo)
#   HERMES_REPO_<SUBTEAM>_TYPE   (옵션 — "unity"/"code", 미지정 시 "code")
SUBTEAM_REPO_OVERRIDES: dict[str, dict[str, str]] = {}
for _sub in ("ui", "server", "ingame", "outgame", "general", "background", "illustration", "content", "level"):
    _h = os.environ.get(f"HERMES_REPO_{_sub.upper()}_HOST")
    _d = os.environ.get(f"HERMES_REPO_{_sub.upper()}_DIR")
    if _h and _d:
        SUBTEAM_REPO_OVERRIDES[_sub] = {
            "host":  _h,
            "dir":   _d,
            "owner": os.environ.get(f"HERMES_REPO_{_sub.upper()}_OWNER", GITHUB_REPO_OWNER),
            "repo":  os.environ.get(f"HERMES_REPO_{_sub.upper()}_NAME", GITHUB_REPO_NAME),
            "type":  os.environ.get(f"HERMES_REPO_{_sub.upper()}_TYPE", "code"),
        }


def get_repo_config(sub_team: str) -> dict[str, str]:
    """sub_team에 매핑된 레포 설정 반환. 미설정이면 DEFAULT_REPO."""
    return SUBTEAM_REPO_OVERRIDES.get((sub_team or "general").lower(), DEFAULT_REPO)

# Claude Code 비대화 모드 타임아웃
CLAUDE_TIMEOUT = int(os.environ.get("CLAUDE_CLI_TIMEOUT_SEC", "600"))

# ProjectHub (Mother) 내부 API 호출용 — art 파이프라인이 /api/designs/generate 로 POST
PROJECTHUB_URL = os.environ.get("PROJECTHUB_URL", "http://127.0.0.1:3000")
HERMES_INTERNAL_API_KEY = os.environ.get("HERMES_INTERNAL_API_KEY", "")


# ──────────────────────────────────────────────
# 메인 디스패처
# ──────────────────────────────────────────────
def execute_task(
    task: dict[str, Any],
    context: dict[str, Any],
    route: dict[str, Any],
) -> dict[str, Any]:
    """
    route["action"]에 따라 분기 실행.

    반환:
      {
        "success": bool,
        "summary": str,           # 성공 시 사용자용 요약 (코멘트로 포스트)
        "error": str,             # 실패 시 에러 메시지
        "next_status": str,       # "done" | "review" | "in_progress"
        "metadata": dict,         # 추가 정보 (로그용)
      }
    """
    action = route["action"]

    # ── 인플라이트 중단 가드 (LLM 무관) ──────────────────────
    # 긴 phase 실행 중 사용자가 '⛔ 중단'을 누르면 현재 subprocess는 못 멈추지만,
    # DB에서 최신 hermes_stopped 를 재조회해 다음 phase / 재작업이 시작되는 것을 차단.
    # (watcher dispatch 가드와 이중 방어 — task dict 가 stale 한 경우 대비.)
    try:
        from bson import ObjectId as _OID
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        _fresh = _client[DB_NAME]["pixelforge_tasks"].find_one(
            {"_id": _OID(str(task.get("_id")))},
            {"hermes_stopped": 1},
        )
        # 팬텀루프 차단: task가 DB에서 삭제됐는데 in-flight rework 루프(change stream replay)가
        # 계속 도는 경우, 여기서 존재 확인으로 끊는다. 삭제된 task는 hermes_stopped 플래그를
        # 걸 doc 자체가 없어 stop 가드로는 못 멈춤 → 존재 가드가 유일한 결정론적 차단점.
        if _fresh is None:
            log.info("  🗑️ Task no longer exists (deleted) — aborting to prevent phantom rework: %s", task.get("_id"))
            return {
                "success": True,
                "summary": "🗑️ 태스크가 삭제되어 처리를 중단합니다.",
                "next_status": "review",
                "metadata": {"action": action, "deleted": True},
            }
        if _fresh and _fresh.get("hermes_stopped"):
            log.info("  ⛔ STOPPED flag detected at execute entry — aborting: %s", task.get("_id"))
            return {
                "success": True,
                "summary": "⛔ 사용자 중단 요청 감지 — 처리를 시작하지 않습니다.",
                "next_status": "review",
                "metadata": {"action": action, "stopped": True},
            }
    except Exception:
        log.debug("stop-flag precheck failed (non-fatal)", exc_info=True)

    handler = _HANDLERS.get(action, _handle_unknown)
    try:
        return handler(task, context, route)
    except Exception as e:
        log.exception("Executor failed for action=%s", action)
        return {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "next_status": "review",
            "metadata": {"action": action},
        }


# ──────────────────────────────────────────────
# Handler: db_query (Stage 1)
# ──────────────────────────────────────────────
def _handle_db_query(task: dict[str, Any], context: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    """
    단순 MongoDB 조회. Hermes LLM 없이도 수행 가능한 케이스를 여기서 처리.

    예: "code_expert 최근 10개 보여줘" → 직접 쿼리 → 결과 포맷팅
    """
    text = f"{task.get('title', '')} {task.get('description', '')}".lower()

    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[DB_NAME]

    # 간단한 룰 기반 쿼리 추출 (Phase 1엔 이 정도로 충분)
    if "code_expert" in text or "코드" in text:
        results = list(db.code_expert.find(
            {"score": {"$gte": 0.6}},
            projection={"_id": 0, "fileId": 1, "genre": 1, "role": 1, "score": 1},
        ).sort("score", -1).limit(10))
        summary = _format_code_results(results)
    elif "design_expert" in text or "설계" in text:
        results = list(db.design_expert.find(
            {},
            projection={"_id": 0, "docId": 1, "score": 1, "summary": 1},
        ).sort("score", -1).limit(10))
        summary = _format_design_results(results)
    else:
        # Hermes LLM으로 fallback — 자연어 → MongoDB 쿼리 변환
        return _handle_chat(task, context, route)

    return {
        "success": True,
        "summary": summary,
        "next_status": "done",
        "metadata": {"query_type": "db_query", "result_count": len(results)},
    }


def _format_code_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "📊 code_expert 조회 결과: (없음)"
    lines = ["📊 **code_expert 상위 10개** (신뢰도 순)", ""]
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. `{r.get('fileId', '?')}` — "
            f"{r.get('genre', '?')}/{r.get('role', '?')} "
            f"(score: {r.get('score', 0):.2f})"
        )
    return "\n".join(lines)


def _format_design_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "📊 design_expert 조회 결과: (없음)"
    lines = ["📊 **design_expert 상위 10개** (신뢰도 순)", ""]
    for i, r in enumerate(results, 1):
        lines.append(
            f"{i}. `{r.get('docId', '?')}` (score: {r.get('score', 0):.2f})"
        )
        summary = (r.get("summary") or "")[:100]
        if summary:
            lines.append(f"   {summary}")
    return "\n".join(lines)


# ──────────────────────────────────────────────
# Handler: simulation (Stage 2)
# ──────────────────────────────────────────────
def _handle_simulation(task: dict[str, Any], context: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    """
    GameForge scripts/balance-simulator.js 호출.
    """
    params = route.get("params", {})
    level_range = params.get("level_range", "")

    script_path = GAMEFORGE_ROOT / "scripts" / "balance-simulator.js"
    if not script_path.is_file():
        return {
            "success": False,
            "error": f"balance-simulator.js not found at {script_path}. GameForge 미동기화?",
            "next_status": "review",
        }

    cmd = ["node", str(script_path)]
    if level_range:
        cmd += ["--levels", level_range]

    log.info("Running simulation: %s", " ".join(shlex.quote(c) for c in cmd))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(GAMEFORGE_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "시뮬레이션 타임아웃 (5분 초과)",
            "next_status": "review",
        }

    if proc.returncode != 0:
        return {
            "success": False,
            "error": f"시뮬레이션 실패 (exit={proc.returncode}): {proc.stderr[:500]}",
            "next_status": "review",
        }

    return {
        "success": True,
        "summary": f"📈 **밸런스 시뮬 결과**\n\n```\n{proc.stdout[:1500]}\n```",
        "next_status": "review",  # 사람이 결과 보고 적용 여부 결정
        "metadata": {"stdout_length": len(proc.stdout)},
    }


# ──────────────────────────────────────────────
# Handler: apk_build (Stage 3)
# ──────────────────────────────────────────────
def _handle_apk_build(task: dict[str, Any], context: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    """
    머신 B에 SSH로 접속해 Gradle 빌드.
    """
    params = route.get("params", {})
    version = params.get("version", "")

    # Windows에선 PowerShell 명령이지만, 머신 B가 Windows이므로 cmd.exe로 실행
    # (OpenSSH on Windows는 기본 shell이 cmd or PowerShell)
    remote_cmd = (
        f'cd /D "{MACHINE_B_PROJECT_DIR}" && '
        f'git pull && '
        f'gradlew.bat assembleRelease'
    )

    ssh_cmd = ["ssh", MACHINE_B_HOST, remote_cmd]
    log.info("Running APK build: %s", " ".join(shlex.quote(c) for c in ssh_cmd))

    try:
        proc = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=1200,  # 20분
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "빌드 타임아웃 (20분 초과)",
            "next_status": "review",
        }

    if proc.returncode != 0:
        return {
            "success": False,
            "error": f"빌드 실패 (exit={proc.returncode})\n\n```\n{proc.stderr[-1000:]}\n```",
            "next_status": "review",
        }

    return {
        "success": True,
        "summary": (
            f"✅ **APK 빌드 완료** ({version})\n\n"
            f"머신 B: {MACHINE_B_HOST}\n"
            f"빌드 디렉토리: {MACHINE_B_PROJECT_DIR}/app/build/outputs/apk/release/\n\n"
            f"빌드 로그 요약:\n```\n{proc.stdout[-800:]}\n```"
        ),
        "next_status": "review",  # 사람이 APK 다운로드 → 테스트 후 done
        "metadata": {"version": version, "stdout_length": len(proc.stdout)},
    }


# ──────────────────────────────────────────────
# Handler: chat — Hermes CLI 비대화 호출 (Stage 1)
# ──────────────────────────────────────────────
def _handle_chat(task: dict[str, Any], context: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    """
    Hermes 담당자에게 온 일반 태스크 엔트리포인트.

    기존 "chat = 즉시 Claude 답변 + done" 동작은 사용자 기대와 다름 —
    처음 태스크가 무조건 '완료'로 넘어가버림. 올바른 흐름:

        1. Translator 전처리: 의도 명확성(clarity) + 팀 분류(team) 판정
        2. needs_input  → 질문 코멘트 + Slack DM + status=review 로 대기
        3. cancel       → done (코드 변경 없음)
        4. rollback     → _handle_rollback
        5. clear + team == "art"     → 아트 파이프라인 (이미지 생성)
           clear + team == "design"  → 기획 파이프라인 placeholder (미연결)
           clear + team == "dev"     → unity_modify 핸들러에 위임
           clear + team == "chat"    → 순수 Q&A (Claude 답변 → review)
        6. team_override=True 인 경우 Translator 판정 무시하고 지정 팀으로

    (기존 PREFER_CLAUDE_CODE 플로우는 team=chat 경로에만 유지)
    """
    # ── Phase 0: 사용자 수동 팀 재배정 존중 ──────────────
    stored_team = (task.get("team") or "").lower()
    team_override = bool(task.get("team_override"))
    if team_override and stored_team == "art":
        return _execute_art_pipeline(task)
    if team_override and stored_team == "design":
        return _execute_design_pipeline(task)
    if team_override and stored_team == "dev":
        return _handle_unity_modify(task, context, route)

    # ── Phase 1: Translator 전처리 ────────────────────────
    tr = _run_translator_preflight(task)
    if not tr.get("ok"):
        # Translator 자체 실패 — 보수적으로 사용자가 볼 수 있게 review로 대기
        _post_comment(task, f"⚠️ Translator 실행 실패: {tr.get('error', 'unknown')[:200]} — 수동 확인 필요")
        return {"success": True, "summary": "Translator 실패 — review 대기", "next_status": "review"}

    clarity = (tr.get("clarity") or "clear").lower()
    translator_team = (tr.get("team") or "chat").lower()

    if clarity == "cancel":
        reason = tr.get("cancel_reason") or "사용자가 작업 중단 요청"
        _post_comment(task, f"🛑 **작업 취소 감지** — {reason[:300]}\n\n코드 변경 없이 완료 처리합니다.")
        return {"success": True, "summary": f"취소: {reason[:200]}", "next_status": "done"}

    if clarity == "rollback":
        reason = tr.get("rollback_reason") or "사용자 롤백 요청"
        _post_comment(task, f"🔄 **롤백 요청 감지** — {reason[:300]}")
        return _handle_rollback(task, reason)

    if clarity == "needs_input":
        questions = [q for q in (tr.get("questions") or []) if isinstance(q, str)][:3]
        preamble = (tr.get("question_preamble") or "").strip()
        current_state = (tr.get("current_state") or "").strip()
        if questions:
            q_md = (
                "🤔 **정보 확인 필요** — 진행하려면 아래에 답변 부탁드립니다.\n\n"
                + (f"{preamble}\n\n" if preamble else "")
                + (f"_현황: {current_state}_\n\n" if current_state else "")
                + "\n".join(f"- {q}" for q in questions)
                + "\n\n_이 코멘트에 답변을 남기시거나, Slack DM에 그대로 답해주세요 — 자동으로 재개됩니다._"
            )
            _post_comment(task, q_md)
            try:
                _send_slack_question(
                    email=(task.get("created_by_email") or "").strip().lower(),
                    task_id=str(task.get("_id")), title=task.get("title", ""),
                    preamble=preamble, current_state=current_state,
                    questions=questions,
                    fallback_assignee=(task.get("assignee") or ""),
                )
            except Exception:
                log.exception("Slack DM (질문) 발송 실패")
            return {"success": True, "summary": "Translator: 사용자 답변 대기", "next_status": "review"}

    # clarity == "clear" — 팀별 디스패치
    if translator_team == "art":
        _persist_team(task, "art")
        return _execute_art_pipeline(task)
    if translator_team == "dev":
        _persist_team(task, "dev")
        # unity_modify가 자체 Translator를 한 번 더 돌리지만, clear 판정이므로 동일 결과.
        # 추후 최적화: task._translator_cached 전달해 중복 호출 스킵
        return _handle_unity_modify(task, context, route)
    if translator_team == "design":
        _persist_team(task, "design")
        return _execute_design_pipeline(task)

    # team == "chat" — 순수 Q&A. Claude 답변 후 review(기존 done 대신) — 사용자가 확인 후 done 처리
    _persist_team(task, "chat")
    prompt = _build_chat_prompt(task, context)
    prefer_claude_code = os.environ.get("PREFER_CLAUDE_CODE", "").lower() in {"1", "true", "yes"}

    if prefer_claude_code and _claude_available():
        result = _invoke_claude_code(prompt, task, context)
    elif _hermes_available():
        result = _invoke_hermes(prompt, task, context)
        if not result.get("success") and _claude_available():
            err = (result.get("error") or "").lower()
            if any(kw in err for kw in ["out of extra usage", "rate_limit", "quota", "credit"]):
                result = _invoke_claude_code(prompt, task, context)
    elif _claude_available():
        result = _invoke_claude_code(prompt, task, context)
    else:
        return {"success": False, "error": "Hermes/Claude Code 미설치", "next_status": "review"}

    # chat 답변은 자동 완료가 아니라 사용자 확인(review)으로 — "무조건 완료" 문제 해결
    if result.get("success"):
        result["next_status"] = "review"
    return result


# ── Translator preflight 공용 헬퍼 ─────────────────────────────
def _run_translator_preflight(task: dict[str, Any]) -> dict[str, Any]:
    """
    Translator만 가볍게 돌리고 구조화 결과 반환. clarity/team/questions/... 포함.
    {"ok": False, "error": "..."} 또는 {"ok": True, "clarity": ..., "team": ..., ...}
    """
    try:
        from agent_team import ExecutionEnv, invoke_agent, TRANSLATOR_PROMPT_TEMPLATE
    except Exception as e:
        return {"ok": False, "error": f"import failed: {e}"}

    title = task.get("title", "")
    description = task.get("description", "")
    all_comments = task.get("comments") or []
    comments_text = "\n".join(
        f"- [{c.get('author', '?')}]: {(c.get('text') or '')[:300]}"
        for c in all_comments[-8:]
    ) or "(없음)"

    # 가장 최근 사용자(non-hermes) 코멘트를 description에 합친다.
    # description이 비고 답변이 comments에만 있을 때 LLM이 답변을 description의 일부로
    # 인식하지 못해 같은 needs_input을 반복하는 문제 방지.
    HERMES_AUTHORS = {"hermes", "hermes-bot", "헤르메스"}
    last_user_reply = ""
    for c in reversed(all_comments):
        auth = (c.get("author") or "").strip().lower()
        if not auth or auth in HERMES_AUTHORS:
            continue
        if (c.get("kind") or "") == "ask_owner":
            continue
        last_user_reply = (c.get("text") or "").strip()
        break
    enriched_description = description or "(설명 없음)"
    if last_user_reply:
        enriched_description = (
            f"{enriched_description}\n\n"
            f"## 사용자 보충 답변 (이전 hermes 질문에 대한 답변 — description의 일부로 처리)\n"
            f"{last_user_reply}"
        )

    env = ExecutionEnv(
        mode="local", cwd=str(Path.home()), timeout_sec=60,
        task_id=str(task.get("_id")), task_title=title,
    )
    prompt = TRANSLATOR_PROMPT_TEMPLATE.format(
        title=title, description=enriched_description, comments=comments_text,
    )
    resp = invoke_agent("translator", prompt, env)
    if not resp.success:
        return {"ok": False, "error": resp.error or "translator failed"}
    out = dict(resp.structured or {})
    out["ok"] = True
    return out


def _post_comment(task: dict[str, Any], text: str) -> None:
    """task_id에 hermes author로 코멘트 추가 (예외 무시)"""
    try:
        from projecthub_writer import ProjectHubWriter as _PHW
        from pymongo import MongoClient as _MC
        _c = _MC(MONGO_URI)
        _wr = _PHW(_c[DB_NAME]["pixelforge_tasks"])
        _wr.add_comment(str(task.get("_id")), text, author="hermes")
    except Exception:
        log.exception("_post_comment failed")


def _persist_team(task: dict[str, Any], team: str) -> None:
    """Translator 판정 팀을 DB에 기록 — 이후 조회/UI 배지에 반영"""
    try:
        from bson import ObjectId
        from datetime import datetime
        from pymongo import MongoClient as _MC
        _c = _MC(MONGO_URI)
        _c[DB_NAME]["pixelforge_tasks"].update_one(
            {"_id": ObjectId(str(task.get("_id")))},
            {"$set": {"team": team, "updated_at": datetime.utcnow().isoformat()}},
        )
    except Exception:
        log.exception("_persist_team failed")


def _persist_sub_team(task: dict[str, Any], sub_team: str) -> None:
    """PM이 결정한 sub_team을 DB에 기록"""
    try:
        from bson import ObjectId
        from datetime import datetime
        from pymongo import MongoClient as _MC
        _c = _MC(MONGO_URI)
        _c[DB_NAME]["pixelforge_tasks"].update_one(
            {"_id": ObjectId(str(task.get("_id")))},
            {"$set": {"sub_team": sub_team, "updated_at": datetime.utcnow().isoformat()}},
        )
    except Exception:
        log.exception("_persist_sub_team failed")


def _run_pm(task: dict[str, Any], team: str, comment_fn) -> str:
    """
    Translator 다음 단계: PM이 sub_team 결정.
    실패 시 'general' 폴백.
    """
    try:
        from agent_team import ExecutionEnv, invoke_agent, build_pm_prompt
    except Exception as e:
        log.warning("PM imports failed: %s — fallback general", e)
        return "general"

    res = build_pm_prompt(team, task.get("title", ""), task.get("description", ""))
    if res is None:
        return "general"
    prompt, opts = res

    pm_role = f"{team}_pm"
    env = ExecutionEnv(
        mode="local", cwd=str(Path.home()), timeout_sec=60,
        task_id=str(task.get("_id")), task_title=task.get("title", ""),
    )
    resp = invoke_agent(pm_role, prompt, env)
    if not resp.success:
        comment_fn(f"⚠️ {pm_role} 실패: {resp.error or '?'} — `general` 분과로 진행")
        return "general"
    out = resp.structured or {}
    sub_team = (out.get("sub_team") or "general").lower().strip()
    reason = (out.get("reason") or "").strip()
    if sub_team not in opts:
        sub_team = "general"
    comment_fn(f"📋 **{pm_role}** 판정: `{sub_team}` 분과 — {reason[:200]}")
    return sub_team


REVIEWER_USER_REJECT_PENALTY = int(os.environ.get("HERMES_REVIEWER_REJECT_PENALTY", "25"))


def _penalize_previous_reviewer(task_id: str) -> None:
    """
    사용자가 review 상태에서 reject(=재작업 트리거)했을 때, 직전 사이클에서 APPROVED를
    찍었던 reviewer에게 페널티 점수를 기록한다 — Reviewer가 자기 판정 품질에 책임을 지게.

    멱등성: 동일 task_id의 가장 최근 APPROVED 이후 'user_rejected_after_approval'
    레코드가 이미 있으면 중복 기록하지 않는다.
    """
    try:
        from pymongo import MongoClient as _MC
        from datetime import datetime
        _c = _MC(MONGO_URI)
        coll = _c[DB_NAME]["hermes_team_scores"]
        # 가장 최근 APPROVED reviewer 점수 찾기
        latest_approved = coll.find_one(
            {"task_id": task_id, "verdict": "APPROVED",
             "role": {"$regex": "reviewer$", "$options": "i"}},
            sort=[("created_at", -1)],
        )
        if not latest_approved:
            return
        # 이미 그 이후로 penalty가 기록됐으면 스킵
        approved_at = latest_approved.get("created_at", "")
        existing_penalty = coll.find_one({
            "task_id": task_id,
            "role": latest_approved.get("role"),
            "verdict": "user_rejected_after_approval",
            "created_at": {"$gt": approved_at},
        })
        if existing_penalty:
            return
        coll.insert_one({
            "task_id": task_id,
            "team": latest_approved.get("team"),
            "sub_team": latest_approved.get("sub_team") or "general",
            "role": latest_approved.get("role"),
            "score": REVIEWER_USER_REJECT_PENALTY,
            "verdict": "user_rejected_after_approval",
            "summary": (
                f"Reviewer가 APPROVED({latest_approved.get('score')}/100) 했지만 "
                f"사용자가 review 상태에서 reject 코멘트로 재작업 트리거"
            )[:500],
            "created_at": datetime.utcnow().isoformat(),
            "linked_approved_at": approved_at,
        })
        log.info("⚖️ [reviewer-self-eval] %s 페널티 기록 — task=%s",
                 latest_approved.get("role"), task_id)
        # 진실성 게이트: 사람이 거부 = 직전 학습이 거짓이었음. 이 task에서 파생된
        # 시니어 원칙 회수 + RAG '우수예시' 강등 + 보류 학습 취소.
        try:
            from truth_gate import on_falsified
            on_falsified(task_id, reason="user_rejected_after_approval")
        except Exception:
            log.exception("on_falsified failed")
        # Phase 5 패치 트래킹에도 페널티 반영 (악화 시 자동 revert 트리거)
        try:
            from prompt_self_improvement import track_score_for_patches
            track_score_for_patches(
                role=latest_approved.get("role") or "reviewer",
                score=REVIEWER_USER_REJECT_PENALTY,
            )
        except Exception:
            log.exception("track_score_for_patches penalty failed")
    except Exception:
        log.exception("_penalize_previous_reviewer failed")


def _record_quality_score(
    *, task_id: str, team: str, sub_team: str, role: str,
    score: int, verdict: str, summary: str = "",
    files_changed: "list[str] | None" = None, diff_summary: str = "",
    title: str = "", description: str = "", coder_role: str = "",
) -> None:
    """
    Reviewer/검수 결과를 hermes_team_scores 컬렉션에 누적 — 보상 체계 데이터 적재.
    Phase 2 시점에는 수집만, Phase 3에서 모델 승격·메모리 우선순위에 활용.
    Phase 5: 같은 role의 active 패치들에 효과 누적 → 악화 시 자동 revert.
    """
    clamped = int(max(0, min(100, score)))
    try:
        from datetime import datetime
        from pymongo import MongoClient as _MC
        _c = _MC(MONGO_URI)
        _c[DB_NAME]["hermes_team_scores"].insert_one({
            "task_id": task_id,
            "team": team,
            "sub_team": sub_team or "general",
            "role": role,
            "score": clamped,
            "verdict": (verdict or "")[:32],
            "summary": (summary or "")[:500],
            "created_at": datetime.utcnow().isoformat(),
        })
    except Exception:
        log.exception("_record_quality_score failed")

    # Phase 5: 패치 효과 트래킹 — 표본 충분히 쌓이고 악화면 자동 revert
    try:
        from prompt_self_improvement import track_score_for_patches
        track_score_for_patches(role=role, score=clamped)
    except Exception:
        log.exception("track_score_for_patches failed")

    # 진실성 게이트(B+C): 리뷰 시점엔 학습을 '즉시' 하지 않는다(= LLM이 LLM을 채점한 결과로
    # 시니어 원칙/RAG-good을 만들면 검증 안 된 성공을 학습 → 환각 강화). 대신 근거(diff 등)와
    # 함께 보류만 하고, 작업이 done으로 ship(객관적 수용)될 때 truth_gate가 grounded reflect로
    # 확정한다. (기존엔 빈 diff·점수만으로 원칙을 만들던 '근거 없는 확신' 표면도 같이 제거)
    if role.endswith("reviewer") or role == "reviewer":
        try:
            from truth_gate import defer_learning
            defer_learning(
                task_id=task_id, team=team, sub_team=sub_team or "general",
                reviewer_role=role, coder_role=coder_role,
                score=clamped, verdict=verdict, summary=summary,
                files_changed=files_changed or [], diff_summary=diff_summary,
                title=title, description=description,
            )
        except Exception:
            log.exception("defer_learning failed")


def _record_gate_event(*, task_id: str, gate: str, result: str, reason: str = "",
                       merge_state: "str | None" = None) -> None:
    """
    게이트 결정을 hermes_gate_events에 기록(측정) + merge_state SSOT 영속화.
    실패해도 머지 흐름을 절대 막지 않음(try/except). off→warn→block 승격의 FP율 측정 토대.
    result: pass | warn | block | merged | indeterminate
    """
    try:
        from datetime import datetime
        from pymongo import MongoClient as _MC
        from bson import ObjectId as _OID
        _c = _MC(MONGO_URI)
        _c[DB_NAME]["hermes_gate_events"].insert_one({
            "task_id": task_id, "gate": gate, "result": result,
            "reason": (reason or "")[:500],
            "created_at": datetime.utcnow().isoformat(),
        })
        if merge_state:
            try:
                _c[DB_NAME]["pixelforge_tasks"].update_one(
                    {"_id": _OID(task_id)},
                    {"$set": {
                        "hermes_merge_state": merge_state,
                        "hermes_merge_reason": (reason or "")[:300],
                        "hermes_merge_updated_at": datetime.utcnow().isoformat(),
                    }},
                )
            except Exception:
                log.exception("_record_gate_event merge_state update failed")
    except Exception:
        log.exception("_record_gate_event failed")


def _extract_pr_info_from_task(task: dict[str, Any]) -> dict[str, str]:
    """Task 코멘트·메타데이터에서 PR URL과 브랜치를 찾는다."""
    pr_url = ""
    branch = ""
    comments = task.get("comments") or []
    for c in comments:
        text = c.get("text") or ""
        m = re.search(r"https?://github\.com/[^\s)]+/pull/\d+", text)
        if m and not pr_url:
            pr_url = m.group(0)
        m2 = re.search(r"hermes/[a-f0-9]{6,}", text)
        if m2 and not branch:
            branch = m2.group(0)
    return {"pr_url": pr_url, "branch": branch}


def _handle_rollback(task: dict[str, Any], reason: str) -> dict[str, Any]:
    """이전 PR을 close하고 필요 시 revert commit 생성."""
    task_id = str(task.get("_id"))
    info = _extract_pr_info_from_task(task)
    pr_url = info["pr_url"]
    branch = info["branch"]

    from projecthub_writer import ProjectHubWriter
    client = MongoClient(MONGO_URI)
    writer = ProjectHubWriter(client[DB_NAME]["pixelforge_tasks"])

    def _c(t: str) -> None:
        try:
            writer.add_comment(task_id, t, author="hermes")
        except Exception:
            pass

    _c(f"🔄 **롤백 시작** — {reason}")

    if not pr_url and not branch:
        _c("⚠️ 롤백 실패: 이전 PR URL 또는 브랜치를 찾을 수 없습니다 (이미 정리되었거나 push 이력 없음).")
        return {"success": True, "summary": "롤백 대상 없음 — done", "next_status": "done"}

    # PR close + branch 삭제 시도 (merge 전이면 충분)
    close_ok = False
    if pr_url:
        close_cmd = f'gh pr close {pr_url} --comment "Hermes auto-rollback: {reason[:100]}" --delete-branch'
        r = subprocess.run(
            ["ssh", MACHINE_B_HOST, f'cd "{MACHINE_B_PROJECT_DIR}" && {close_cmd}'],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
        )
        close_ok = r.returncode == 0
        if close_ok:
            _c(f"✅ PR 닫고 브랜치 삭제 완료: {pr_url}")
        else:
            _c(f"⚠️ PR close 실패 (이미 머지되었거나 권한 부족): {r.stderr[:200] or r.stdout[:200]}")

    # merge 된 경우 revert commit (close_ok가 아니라도 시도)
    if not close_ok and branch:
        # GitHub PR가 이미 merged면 merge commit sha 찾아 revert
        find_merge = subprocess.run(
            ["ssh", MACHINE_B_HOST, f'cd "{MACHINE_B_PROJECT_DIR}" && git log main --merges --oneline -50'],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
        )
        merge_sha = ""
        for line in (find_merge.stdout or "").splitlines():
            if branch in line:
                merge_sha = line.split()[0]
                break
        if merge_sha:
            _c(f"🔀 merge commit 발견: {merge_sha} — revert commit 생성")
            revert_cmds = (
                f'cd "{MACHINE_B_PROJECT_DIR}" && '
                f'git checkout main && '
                f'git pull --rebase origin main && '
                f'git revert -m 1 --no-edit {merge_sha} && '
                f'git push origin main'
            )
            rr = subprocess.run(
                ["ssh", MACHINE_B_HOST, revert_cmds],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False,
            )
            if rr.returncode == 0:
                _c(f"✅ revert commit push 완료 (main에 반영)")
            else:
                _c(f"⚠️ revert 실패: {rr.stderr[:300] or rr.stdout[:300]}")
                return {"success": False, "error": "revert failed", "next_status": "review"}

    return {"success": True, "summary": f"롤백 완료: {reason[:150]}", "next_status": "done"}


def _send_slack_notice(email: str, text: str, fallback_assignee: str = "") -> None:
    """
    이메일 → Slack User ID → DM 발송 (범용).
    email이 Settings의 slack_assignee_webhooks에 매핑돼 있고 bot_token이 있을 때만 동작.
    email 매칭 실패 시 fallback_assignee 이름으로 재조회 (legacy task에 created_by_email 누락 대응).
    """
    if not email and not fallback_assignee:
        log.info("Slack DM skip: no email and no fallback assignee")
        return
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=3000)
        db = client[DB_NAME]
        doc = db["projecthub_settings"].find_one({"key": "current"})
        settings = (doc or {}).get("settings", {}) if doc else {}
        webhooks = settings.get("slack_assignee_webhooks", []) or []
        bot_token = settings.get("slack_bot_token", "")
        match = None
        if email:
            low = email.strip().lower()
            for w in webhooks:
                if (w.get("email") or "").strip().lower() == low:
                    match = w
                    break
        if not match and fallback_assignee:
            fa = fallback_assignee.strip().lower()
            for w in webhooks:
                if (w.get("assignee") or "").strip().lower() == fa:
                    match = w
                    log.info("Slack DM: email lookup failed, using assignee fallback=%s", fallback_assignee)
                    break
        if not match or not match.get("slack_user_id") or not bot_token:
            log.info(
                "Slack DM skip: email=%s assignee=%s match=%s token=%s",
                email, fallback_assignee, bool(match), bool(bot_token),
            )
            return
        user_id = match["slack_user_id"]
        import urllib.request
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=json.dumps({"channel": user_id, "text": text}).encode("utf-8"),
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {bot_token}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            log.info("Slack DM response: %s", body[:200])
    except Exception:
        log.exception("_send_slack_notice failed")


def _send_slack_question(
    email: str,
    task_id: str,
    title: str,
    preamble: str,
    current_state: str,
    questions: list[str],
    fallback_assignee: str = "",
) -> None:
    """Task 생성자에게 Slack DM으로 질문 발송 (needs_input 시)."""
    task_url = f"https://aimed.tailf6f809.ts.net/tasks"
    q_lines = "\n".join(f"• {q}" for q in questions[:3])
    text = (
        f"🤖 *Hermes 질문* — `{title}`\n\n"
        + (f"{preamble}\n\n" if preamble else "")
        + (f"_현황: {current_state}_\n\n" if current_state else "")
        + f"{q_lines}\n\n"
        f"📝 *답변*: ProjectHub 작업 코멘트로 남겨주세요 (이 DM은 알림 전용 — 답장 인식 안 됨)\n"
        f"   → {task_url}"
    )
    _send_slack_notice(email, text, fallback_assignee=fallback_assignee)


def _send_slack_success(email: str, title: str, summary: str, pr_url: str = "", fallback_assignee: str = "") -> None:
    """작업 완료 DM — 리뷰 요청."""
    text = (
        f"✅ *작업 완료* — `{title}`\n\n"
        f"{summary[:500]}\n\n"
        + (f"🔗 PR: {pr_url}\n\n" if pr_url else "")
        + f"📝 리뷰 부탁드려요. 문제·승인은 ProjectHub 작업 코멘트로 남겨주세요 (이 DM은 알림 전용)."
    )
    _send_slack_notice(email, text, fallback_assignee=fallback_assignee)


def _send_slack_failure(email: str, title: str, reason: str, category: str = "", fallback_assignee: str = "") -> None:
    """작업 실패 DM — 재시도 선택지 제공."""
    cat = f" [{category}]" if category else ""
    text = (
        f"❌ *작업 실패*{cat} — `{title}`\n\n"
        f"원인: {reason[:400]}\n\n"
        f"📝 *선택* (ProjectHub 작업 코멘트로 — 이 DM은 알림 전용):\n"
        f"1) *재시도* — 코멘트에 `재시도` 또는 `retry`\n"
        f"2) *수정 지시* — 추가 지시를 코멘트로 남기면 반영해 재시도\n"
        f"3) *중단* — `그만` 또는 `done`"
    )
    _send_slack_notice(email, text, fallback_assignee=fallback_assignee)


def _format_attachments_section(task: dict[str, Any]) -> str:
    """task.attachments를 LLM 프롬프트 섹션으로 직렬화. 없으면 빈 문자열."""
    attachments = task.get("attachments") or []
    if not isinstance(attachments, list) or not attachments:
        return ""
    MAX_CHARS_PER_FILE = 50_000  # 파일 하나당 프롬프트 투입 상한
    lines = [f"\n## 첨부 파일 ({len(attachments)}개)\n"]
    for i, att in enumerate(attachments, 1):
        if not isinstance(att, dict):
            continue
        name = att.get("name", "unknown")
        kind = (att.get("kind") or "text").lower()
        size = att.get("size", 0)
        content = att.get("content", "") or ""
        truncated_note = ""
        if len(content) > MAX_CHARS_PER_FILE:
            content = content[:MAX_CHARS_PER_FILE]
            truncated_note = f"\n...[truncated — 원본 {size} bytes]"
        fence = "json" if kind == "json" else ("markdown" if kind == "md" else "")
        lines.append(f"### [{i}] {kind.upper()}: `{name}` ({size} bytes)")
        lines.append(f"```{fence}")
        lines.append(content + truncated_note)
        lines.append("```\n")
    return "\n".join(lines)


def _build_chat_prompt(task: dict[str, Any], context: dict[str, Any]) -> str:
    """
    Task + 대화 이력 + 스코프 정보를 LLM에게 전달할 프롬프트로 조립.
    """
    title = task.get("title", "")
    description = task.get("description", "")
    comments = task.get("comments", [])
    scope = context.get("scope", {})

    lines = [
        f"# ProjectHub 작업 처리 요청",
        f"",
        f"## 작업 정보",
        f"- 제목: {title}",
        f"- 설명: {description}",
        f"- 우선순위: {task.get('priority', 'medium')}",
    ]

    if scope.get("team"):
        lines.append(f"- 팀: {scope['team']}")
    if scope.get("role"):
        lines.append(f"- 작성자 롤: {scope['role']}")
    if scope.get("project"):
        lines.append(f"- 프로젝트: {scope['project']}")

    if comments:
        lines.append("\n## 대화 이력")
        for c in comments[-10:]:  # 최근 10개만
            author = c.get("author", "?")
            text = c.get("text", "")
            lines.append(f"- **{author}**: {text}")

    attach_section = _format_attachments_section(task)
    if attach_section:
        lines.append(attach_section)

    lines.append("\n## 응답 지침")
    lines.append("- 작업 맥락에 맞춰 답변하세요.")
    lines.append("- 필요한 정보가 부족하면 명시적으로 요청하세요.")
    lines.append("- 마크다운 포맷 사용 가능.")

    return "\n".join(lines)


def _hermes_available() -> bool:
    try:
        proc = subprocess.run(["hermes", "--version"], capture_output=True, timeout=5)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _claude_available() -> bool:
    try:
        proc = subprocess.run(["claude", "--version"], capture_output=True, timeout=5)
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _invoke_hermes(prompt: str, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """hermes --print 비대화 호출"""
    try:
        proc = subprocess.run(
            ["hermes", "--print", prompt],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Hermes 타임아웃", "next_status": "review"}

    if proc.returncode != 0:
        return {
            "success": False,
            "error": f"Hermes 실패: {proc.stderr[:500]}",
            "next_status": "review",
        }

    return {
        "success": True,
        "summary": proc.stdout.strip(),
        "next_status": "done",
        "metadata": {"backend": "hermes"},
    }


def _invoke_claude_code(prompt: str, task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """claude -p 비대화 호출 (Hermes 미설치 시 fallback)"""
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt],
            capture_output=True,
            text=True,
            timeout=CLAUDE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Claude Code 타임아웃", "next_status": "review"}

    if proc.returncode != 0:
        return {
            "success": False,
            "error": f"Claude Code 실패: {proc.stderr[:500]}",
            "next_status": "review",
        }

    return {
        "success": True,
        "summary": proc.stdout.strip(),
        "next_status": "done",
        "metadata": {"backend": "claude-code"},
    }


# ──────────────────────────────────────────────
# Handler: review_needed
# ──────────────────────────────────────────────
def _handle_review_needed(task: dict[str, Any], context: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    """
    자동 처리 불가 — 사람 개입 필요함을 명시적으로 표시.
    """
    deferred = route.get("deferred_action")
    notice = route.get("notice", "")

    msg = "🤚 **사람의 개입이 필요한 작업입니다.**\n\n"
    if deferred:
        msg += f"감지된 의도: `{deferred}` (Stage {route.get('stage')})\n"
    if notice:
        msg += f"\n{notice}\n"
    msg += "\n작업을 세분화하거나, 파워유저가 Mother SSH로 직접 처리하세요."

    return {
        "success": True,  # 시스템 실패는 아님
        "summary": msg,
        "next_status": "review",
        "metadata": {"deferred_action": deferred},
    }


# ──────────────────────────────────────────────
# Handler: unknown
# ──────────────────────────────────────────────
def _handle_unknown(task: dict[str, Any], context: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    action = route.get("action", "?")
    return {
        "success": False,
        "error": f"알 수 없는 action: {action}",
        "next_status": "review",
    }


# ──────────────────────────────────────────────
# 실패 카테고리화 헬퍼
# ──────────────────────────────────────────────
def _categorize_git_error(output: str) -> str:
    """git 에러 메시지 → 카테고리"""
    low = (output or "").lower()
    if "non-fast-forward" in low or "rejected" in low and "fetch first" in low:
        return "non_fast_forward"
    if "permission denied" in low or "authentication failed" in low or "could not read username" in low:
        return "auth_failure"
    if "timeout" in low or "timed out" in low:
        return "timeout"
    if "merge conflict" in low or "conflict" in low:
        return "merge_conflict"
    if "nothing to commit" in low:
        return "empty_commit"
    if "rejected" in low:
        return "rejected_other"
    return "unknown"


def _log_and_maybe_learn(
    task_id: str, category: str, details: str,
    agent_role: Optional[str] = None,
) -> None:
    """
    실패를 MongoDB에 기록하고, 임계값 초과 시 학습 스킬 자동 생성.
    agent_role이 주어지면 prompt self-improvement reflection도 트리거.
    Hermes 자가 강화 핵심.
    """
    try:
        from pymongo import MongoClient
        from failure_learning import record_failure, generate_learned_skill

        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[DB_NAME]

        record_failure(db, task_id=task_id, category=category, details=details, agent_role=agent_role)
        skill_path = generate_learned_skill(db, category)
        if skill_path:
            log.info("📚 학습 스킬 생성/갱신: %s", skill_path)

        # Phase 5: role 명시되면 prompt self-improvement reflection 트리거
        # (REFLECTION_THRESHOLD 미만이면 내부에서 자동 거름)
        if agent_role:
            try:
                from prompt_self_improvement import reflect_and_propose
                saved = reflect_and_propose(role=agent_role, failure_category=category)
                if saved > 0:
                    log.info("🔁 [self-improve] role=%s에 새 패치 %d개 저장", agent_role, saved)
            except Exception:
                log.exception("reflect_and_propose 실패 (무시하고 계속)")
    except Exception:
        log.exception("_log_and_maybe_learn 실패 (무시하고 계속)")


def _fmt_failure(category: str, details: str) -> str:
    """구조화된 실패 리포트 포맷"""
    category_descriptions = {
        "branch_prep": "브랜치 준비 실패 (git fetch/pull/checkout 중)",
        "commit_failed": "커밋 실패 (변경 없음 또는 git 상태 이상)",
        "push_failed": "푸시 실패 (재시도 후에도 실패)",
        "non_fast_forward": "원격 브랜치 분기 — 재시도 중 추가 커밋 푸시됨",
        "auth_failure": "인증 실패 — GitHub credential 설정 확인 필요",
        "timeout": "SSH/네트워크 타임아웃",
        "merge_conflict": "머지 충돌 — 수동 해결 필요",
        "empty_commit": "변경사항 없음",
        "validator_rejected": "Validator가 변경사항 거부",
        "reviewer_rejected": "Reviewer가 변경사항 거부",
        "no_changes_made": "에이전트가 파일 수정 안 함",
        "unknown": "미분류 에러",
    }
    desc = category_descriptions.get(category, category)
    return (
        f"[{category}] {desc}\n\n"
        f"--- 상세 로그 ---\n{details[-500:]}"
    )


# ──────────────────────────────────────────────
# Handler: git_sync — 단순 main 동기화 (에이전트 호출 없음)
# ──────────────────────────────────────────────
def _handle_git_sync(task: dict[str, Any], context: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    """
    빌드 컴(머신 B)의 작업 트리를 origin/main 최신으로 동기화.
    에이전트 호출 없이 git pull만 수행. 비용 $0, 소요 수 초.

    사용 케이스:
      - "main 브랜치에서 pull해줘"
      - "[sync] 빌드 컴 최신화"
      - "본 프로젝트 변경사항 반영"
    """
    task_id = str(task.get("_id"))

    # ProjectHub writer (코멘트 기록)
    from projecthub_writer import ProjectHubWriter
    client = MongoClient(MONGO_URI)
    writer = ProjectHubWriter(client[DB_NAME]["pixelforge_tasks"])

    def _comment(text: str) -> None:
        try:
            writer.add_comment(task_id, text, author="hermes")
        except Exception:
            pass

    # 어느 레포를 sync할지 결정 — task.sub_team 우선, 없으면 default 레포
    sync_sub_team = (task.get("sub_team") or "general").lower()
    sync_repo = get_repo_config(sync_sub_team)
    sync_host = sync_repo["host"]
    sync_dir = sync_repo["dir"]
    if sync_repo is not DEFAULT_REPO:
        _comment(f"🔄 Git 동기화 시작 — `{sync_sub_team}` 분과 → `{sync_repo['owner']}/{sync_repo['repo']}` @ `{sync_host}`")
    else:
        _comment("🔄 Git 동기화 시작 (main 브랜치 최신화)")

    # 머신 B는 Windows cmd — bash `|| true` 미지원. stash를 별도 호출로 분리.
    subprocess.run(
        ["ssh", sync_host,
         f'cd "{sync_dir}" && git stash push -u -m "hermes-autosave-sync"'],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, check=False,
    )

    sync_cmd = (
        f'cd "{sync_dir}" && '
        f'git fetch origin && '
        f'git checkout main && '
        f'git pull --rebase origin main && '
        f'echo SYNC_OK && '
        f'git log --oneline -5'
    )

    result = subprocess.run(
        ["ssh", sync_host, sync_cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=120, check=False,
    )

    if "SYNC_OK" not in result.stdout:
        _log_and_maybe_learn(
            task_id=task_id, category="git_sync_failed",
            details=result.stderr or result.stdout,
        )
        return {
            "success": False,
            "error": _fmt_failure("git_sync_failed",
                                  result.stderr[:400] or result.stdout[-400:]),
            "next_status": "review",
            "failure_category": "git_sync_failed",
        }

    # 최근 커밋 추출
    commits_section = ""
    if "=== 최근 5개 커밋 ===" in result.stdout:
        commits_section = result.stdout.split("=== 최근 5개 커밋 ===", 1)[1].strip()

    summary = (
        f"✅ **Git 동기화 완료**\n\n"
        f"빌드 컴(머신 B)이 `origin/main` 최신 상태로 업데이트됐습니다.\n"
        f"Unity Editor 열려 있으면 Assets 자동 재임포트.\n\n"
        f"**최근 커밋**:\n```\n{commits_section[:800]}\n```"
    )

    # 성공 기록
    try:
        from failure_learning import record_success
        record_success(
            client[DB_NAME],
            task_id=task_id,
            metadata={"action": "git_sync"},
        )
    except Exception:
        pass

    return {
        "success": True,
        "summary": summary,
        "next_status": "done",
        "metadata": {"action": "git_sync"},
    }


# ──────────────────────────────────────────────
# Handler: unity_modify — 멀티 에이전트 코드 수정 + PR
# ──────────────────────────────────────────────
def _execute_art_pipeline(task: dict[str, Any]) -> dict[str, Any]:
    """
    🎨 아트팀 파이프라인 — 이미지 생성 요청을 처리하고 갤러리에 저장.

    1. art_prompter  — 사용자 요청 → GPT Image 2 프롬프트 확장
    2. POST /api/designs/generate (task_id 포함) — 이미지 생성 + MongoDB 저장
                                                + 양방향: pixelforge_tasks.generated_design_ids 업데이트
    3. art_reviewer  — 프롬프트 품질 간이 검수 (시각 검수는 사용자 몫)
    4. Task에 갤러리 링크 댓글 + next_status=done
    """
    from agent_team import (
        ExecutionEnv, invoke_agent, resolve_role,
        ART_PROMPTER_TEMPLATE, ART_REVIEWER_TEMPLATE,
        is_9slice_request, get_9slice_guidance, parse_border_px,
    )
    from projecthub_writer import ProjectHubWriter as _PHW
    from pymongo import MongoClient as _MC

    task_id = str(task.get("_id"))
    title = task.get("title", "")
    description = task.get("description", "")
    if task.get("_hermes_is_rework"):
        _penalize_previous_reviewer(task_id)
    all_comments = task.get("comments") or []
    comments_text = "\n".join(
        f"- [{c.get('author', '?')}]: {(c.get('text') or '')[:300]}"
        for c in all_comments[-8:]
    ) or "(없음)"

    _c = _MC(MONGO_URI)
    writer = _PHW(_c[DB_NAME]["pixelforge_tasks"])

    def _comment(text: str) -> None:
        try:
            writer.add_comment(task_id, text, author="hermes")
        except Exception:
            log.exception("art pipeline comment post failed")

    _comment("🎨 **아트팀 파이프라인** 진입 — 이미지 생성 처리 중")

    # PM이 art sub_team 결정 (사용자 수동 지정 시 스킵)
    stored_sub = (task.get("sub_team") or "").lower()
    sub_override = bool(task.get("sub_team_override"))
    if sub_override and stored_sub:
        art_sub_team = stored_sub
        _comment(f"🔒 **art_pm 스킵** — 사용자 수동 지정: `{art_sub_team}` 분과")
    else:
        art_sub_team = _run_pm(task, "art", _comment)
        _persist_sub_team(task, art_sub_team)

    # 분과별 특화 프롬프터/리뷰어가 있으면 그쪽 사용, 없으면 general 폴백
    prompter_role = resolve_role("art", art_sub_team, "prompter") if art_sub_team != "general" else "art_prompter"
    reviewer_role_art = resolve_role("art", art_sub_team, "reviewer") if art_sub_team != "general" else "art_reviewer"
    # resolve_role 폴백이 'prompter'/'reviewer' 가 되면 generic art 역할로 회귀
    if prompter_role in {"prompter"}:
        prompter_role = "art_prompter"
    if reviewer_role_art in {"reviewer"}:
        reviewer_role_art = "art_reviewer"

    # ── Step 1: art_prompter ────────────────────────────────────────
    env = ExecutionEnv(
        mode="local", cwd=str(Path.home()), timeout_sec=180,
        task_id=task_id, task_title=title,
        team="art", sub_team=art_sub_team,
    )
    # Phase 3: 같은 분과 best-practice 주입 (점수≥85 최근 작업 요약)
    bp_section = ""
    try:
        from agent_team import format_best_practices_section as _fbp_a
        bp_section = _fbp_a("art", art_sub_team, limit=2)
    except Exception:
        log.debug("art best-practice skipped", exc_info=True)

    # 9-slice 모드 감지 — title/description/comments 어디든 키워드 있으면 가이드 주입
    nine_slice = is_9slice_request(title, description, comments_text)
    nine_slice_section = ""
    if nine_slice:
        border_px = parse_border_px(f"{title} {description}", default=96)
        nine_slice_section = get_9slice_guidance(border_px=border_px, output_size="1024x1024")
        _comment(f"🧩 **9-Slice 모드** 감지 — border={border_px}px, flat fill 강제 가이드 적용")

    prompter_prompt = ART_PROMPTER_TEMPLATE.format(
        title=title, description=description or "(설명 없음)", comments=comments_text,
    ) + bp_section + nine_slice_section
    pr = invoke_agent(prompter_role, prompter_prompt, env)
    if not pr.success:
        _comment(f"❌ **art_prompter** 실패: {pr.error}")
        return {"success": False, "error": f"art_prompter failed: {pr.error}", "next_status": "review"}

    structured = pr.structured or {}
    image_prompt = (structured.get("image_prompt") or "").strip()
    size = (structured.get("size") or "auto")
    n = int(structured.get("n") or 1)
    quality = (structured.get("quality") or "auto")
    tags = structured.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(t)[:30] for t in tags if isinstance(t, (str, int))][:10]

    if not image_prompt:
        _comment(f"❌ **art_prompter** 가 image_prompt를 생성하지 않음")
        return {"success": False, "error": "no image prompt", "next_status": "review"}

    _comment(
        f"✍️ **art_prompter** ({pr.model}, {pr.duration_sec:.1f}s) — 프롬프트 확장\n"
        f"```\n{image_prompt[:600]}\n```\n"
        f"_크기: {size} · 수량: {n} · 품질: {quality}_"
    )

    # ── Step 2: /api/designs/generate 호출 ────────────────────────
    import urllib.request, urllib.error
    api_url = PROJECTHUB_URL.rstrip("/") + "/api/designs/generate"
    payload = json.dumps({
        "prompt": image_prompt,
        "n": max(1, min(4, n)),
        "size": size,
        "quality": quality,
        "tags": tags,
        "task_id": task_id,
        "task_title": title,
    }).encode("utf-8")

    req = urllib.request.Request(api_url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    if HERMES_INTERNAL_API_KEY:
        # Authorization Bearer + X-Hermes-Key 둘 다 — Next.js 16에서 커스텀 X-* 헤더 차단되는 경우 폴백
        req.add_header("Authorization", f"Bearer {HERMES_INTERNAL_API_KEY}")
        req.add_header("X-Hermes-Key", HERMES_INTERNAL_API_KEY)
    created_by = (task.get("created_by_email") or "").strip().lower()
    if created_by:
        req.add_header("X-Hermes-On-Behalf-Of", created_by)

    result: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        _comment(f"❌ 이미지 생성 API 실패 ({e.code}): {body}")
        return {"success": False, "error": f"image gen HTTP {e.code}", "next_status": "review"}
    except Exception as e:
        _comment(f"❌ 이미지 생성 호출 실패: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e), "next_status": "review"}

    if not result.get("ok"):
        err = result.get("error") or "unknown"
        _comment(f"❌ 이미지 생성 실패: {err}")
        return {"success": False, "error": str(err), "next_status": "review"}

    design_id = str(result.get("id") or "")
    images = result.get("images") or []
    _comment(
        f"🖼 **이미지 생성 완료** — {len(images)}장 · Design `{design_id[-8:]}`\n"
        f"- 🔗 갤러리에서 보기: `/gallery?task_id={task_id}`\n"
        f"- 🔍 상세: `/gallery#design={design_id}`"
    )

    # ── Step 3: art_reviewer (시각 검수 — 첫 이미지 절대경로를 env.image_path로 주입)
    designs_storage = os.environ.get(
        "DESIGNS_STORAGE_DIR", "/home/aimed/projecthub-web/data/designs",
    )
    first_image_path = ""
    if images:
        first_filename = (images[0] or {}).get("filename") or ""
        if first_filename:
            first_image_path = str(Path(designs_storage) / first_filename)

    # ── Step 2.5: art_validator (규격 게이트 — reviewer 전 2-게이트) [granular_v1]
    _art_val_role = resolve_role("art", art_sub_team, "validator")
    if _art_val_role not in {"validator", "art_reviewer", "reviewer"}:
        _av_prompt = (
            f"아트 산출물 규격 검증(품질평가 아닌 정합검증). 태스크: {title}\n"
            f"image_prompt: {image_prompt}\n이미지: {first_image_path or '(경로없음)'}\n"
            "①요청 사이즈/비율 ②투명배경(요청시) ③9-slice 규칙(해당시 균일내부/테두리장식) "
            "④팔레트/색수 ⑤피사체 잘림/씬화 여부 를 각 OK/WARN/FAIL로. "
            "JSON으로 {verdict: ok|revise|fail, quality_score: 0-100, notes: str}."
        )
        _av_prev = getattr(env, "image_path", None)
        env.image_path = first_image_path or None
        try:
            _avr = invoke_agent(_art_val_role, _av_prompt, env)
        finally:
            env.image_path = _av_prev
        if _avr.success:
            _avs = _avr.structured or {}
            _avv = (_avs.get("verdict") or "ok").lower()
            try:
                _avsc = int(_avs.get("quality_score")) if _avs.get("quality_score") is not None else 70
            except (TypeError, ValueError):
                _avsc = 70
            _comment(f"\U0001F50D **{_art_val_role}** 규격검증: `{_avv}` — {(_avs.get('notes') or '')[:180]}")
            _record_quality_score(task_id=task_id, team="art", sub_team=art_sub_team,
                                  role=_art_val_role, score=_avsc, verdict=_avv,
                                  summary=(_avs.get('notes') or '')[:300])

    reviewer_prompt = ART_REVIEWER_TEMPLATE.format(
        title=title, description=description or "(설명 없음)",
        gpt_prompt=image_prompt, n=len(images),
        image_path=first_image_path or "(이미지 경로 없음 — verdict=cannot_review)",
    )
    # reviewer 호출 동안만 env.image_path를 첫 이미지로 설정 (Read 도구가 이 경로를 읽도록)
    prev_image_path = getattr(env, "image_path", None)
    env.image_path = first_image_path or None
    try:
        rv = invoke_agent(reviewer_role_art, reviewer_prompt, env)
    finally:
        env.image_path = prev_image_path
    if rv.success:
        rs = rv.structured or {}
        verdict = (rs.get("verdict") or "ok").lower()
        notes = (rs.get("notes") or "").strip()
        icon = "✅" if verdict == "ok" else ("⚠️" if verdict == "revise" else "🔁")
        score = rs.get("quality_score")
        try:
            score = int(score) if score is not None else None
        except (TypeError, ValueError):
            score = None
        _comment(
            f"{icon} **{reviewer_role_art}** ({rv.model}) — {verdict}"
            + (f" · 품질 점수 **{score}/100**" if score is not None else "")
            + f"\n{notes[:500]}"
        )
        if score is not None:
            _record_quality_score(
                task_id=task_id, team="art", sub_team=art_sub_team,
                role=reviewer_role_art, score=score,
                verdict=verdict, summary=notes[:500],
            )
    else:
        _comment(f"ℹ️ {reviewer_role_art} 스킵: {rv.error}")

    return {
        "success": True,
        "summary": f"아트 파이프라인 완료 — 이미지 {len(images)}장 생성, 갤러리 저장",
        "next_status": "done",
    }


def _execute_chat_only(task: dict[str, Any]) -> dict[str, Any]:
    """
    💬 팀 = chat — 코드/이미지 생성 없이 대화만 처리.
    기존 _handle_chat 재활용 (route/context 없이 호출용 얇은 어댑터).
    """
    # _handle_chat은 context/route를 받지만 대부분 무시하므로 빈 값 전달
    return _handle_chat(task, context={}, route={})


# ──────────────────────────────────────────────
# Design 팀 파이프라인 — level / content
# ──────────────────────────────────────────────
def _check_team_results_health(
    team_results: dict[str, Any], spec: dict[str, Any],
) -> tuple[bool, str]:
    """
    LLM 없이 4팀 결과의 명백한 실패 패턴 감지.
    실패면 (False, reason). 통과면 (True, "ok").

    검사:
      1. 성공 팀 < 2 → 너무 적음
      2. 모든 팀의 filled < width*height*0.10 → 너무 빈약
      3. 모든 팀이 1색만 사용 → degenerate
      4. 모든 팀에서 한 색이 80%+ 차지 → 한 색 dominant noise
    """
    if len(team_results) < 2:
        return False, f"successful teams: {len(team_results)}/4"

    total_cells = max(1, spec["width"] * spec["height"])
    sparse_count = 0
    mono_count = 0
    dominant_count = 0

    for tid, tr in team_results.items():
        filled = sum(tr.per_color_count.values())
        if filled < total_cells * 0.10:
            sparse_count += 1
        n_colors = len(tr.per_color_count)
        if n_colors <= 1:
            mono_count += 1
        if filled > 0:
            max_color = max(tr.per_color_count.values())
            if max_color / filled > 0.80:
                dominant_count += 1

    n = len(team_results)
    issues = []
    if sparse_count >= n:
        issues.append(f"전 팀 너무 빈약 (filled<10%)")
    if mono_count >= n:
        issues.append(f"전 팀 1색만")
    if dominant_count >= n:
        issues.append(f"전 팀 한 색 80%+ 지배")

    if issues:
        return False, "; ".join(issues)
    return True, "ok"


def _with_trace(span_name: str):
    """
    H3 helper — 함수 전체를 trace_context + root span으로 감쌈.
    pipeline 전체 호출 트리가 1개 trace_id 아래에 정렬됨.
    """
    from functools import wraps

    def decorator(fn):
        @wraps(fn)
        def wrapper(task, *args, **kwargs):
            try:
                from harness.tracing import trace_context, span as _trace_span
            except ImportError:
                return fn(task, *args, **kwargs)
            task_id = str(task.get("_id")) if isinstance(task, dict) else None
            team = (task.get("team") if isinstance(task, dict) else None) or ""
            sub_team = (task.get("sub_team") if isinstance(task, dict) else None) or ""
            with trace_context(task_id=task_id):
                with _trace_span(span_name, task_id=task_id, team=team, sub_team=sub_team):
                    return fn(task, *args, **kwargs)
        return wrapper
    return decorator


@_with_trace("design_pipeline")
def _execute_design_pipeline(task: dict[str, Any]) -> dict[str, Any]:
    """
    📐 기획팀 파이프라인.

    sub_team='level' :  design_pm → design_level_designer (LLM, spec only) →
                        level_grid_generator (결정성 코드) → level_validator (코드) →
                        실패 시 새 seed로 1회 재시도 → PNG 렌더 → pixelforge_levels 저장
                        → design_level_reviewer (PNG + 검증 리포트 보고 점수)
    sub_team='content': 미연결 — review 대기 (Session 15 추가 예정)
    """
    from agent_team import ExecutionEnv, invoke_agent
    from projecthub_writer import ProjectHubWriter as _PHW
    from pymongo import MongoClient as _MC

    task_id = str(task.get("_id"))
    short_id = task_id[-8:]
    title = task.get("title", "")
    description = task.get("description", "")

    _c = _MC(MONGO_URI)
    _wr = _PHW(_c[DB_NAME]["pixelforge_tasks"])

    def _comment(text: str) -> None:
        try:
            _wr.add_comment(task_id, text, author="hermes")
        except Exception:
            log.exception("comment failed")

    # ── PM이 sub_team 결정 (사용자 수동 지정 시 스킵)
    stored_sub = (task.get("sub_team") or "").lower()
    sub_override = bool(task.get("sub_team_override"))
    if sub_override and stored_sub:
        sub_team = stored_sub
        _comment(f"🔒 **design_pm 스킵** — 사용자 수동 지정: `{sub_team}` 분과")
    else:
        sub_team = _run_pm(task, "design", _comment)
        _persist_sub_team(task, sub_team)

    if sub_team == "content":
        return _execute_content_pipeline(task, title, description, task_id, _comment)

    if sub_team == "motif":
        return _execute_design_motif_pipeline(task)

    if sub_team != "level":
        # PM이 unknown sub_team 줬을 때 폴백 (기본은 level)
        _comment(f"ℹ️ PM이 `{sub_team}`을 선택 — `level` 분과로 진행합니다.")
        sub_team = "level"

    # ── Step 1: design_level_designer (LLM이 spec만 만든다)
    _comment("🧩 **design_level_designer** 격자 spec 생성 중...")
    designer_env = ExecutionEnv(
        mode="local", cwd=str(Path.home()), timeout_sec=120,
        task_id=task_id, task_title=title,
        team="design", sub_team="level",
    )
    designer_prompt = _build_level_designer_prompt(title, description, task)
    designer_resp = invoke_agent("design_level_designer", designer_prompt, designer_env)
    if not designer_resp.success:
        _comment(f"❌ designer 실패: {designer_resp.error}")
        return {"success": False, "error": designer_resp.error or "designer failed",
                "next_status": "review"}

    raw_spec = designer_resp.structured or {}
    if not raw_spec or not raw_spec.get("symmetry"):
        # JSON 없거나 핵심 필드 누락 — 사용자에게 알려주고 review로
        _comment(
            f"⚠️ designer가 spec JSON을 제대로 반환하지 못했습니다. "
            f"응답 샘플:\n```\n{designer_resp.output[:400]}\n```"
        )
        return {"success": False, "error": "designer returned non-JSON",
                "next_status": "review"}

    # spec 정규화
    try:
        spec = _normalize_level_spec(raw_spec)
    except Exception as e:
        _comment(f"❌ spec 정규화 실패: {type(e).__name__}: {e}")
        return {"success": False, "error": str(e), "next_status": "review"}

    rationale = (raw_spec.get("rationale") or "")[:300]
    _comment(
        f"📋 **spec 결정** ({designer_resp.model})\n"
        f"  - name: `{spec['name']}`\n"
        f"  - {spec['width']}×{spec['height']} · symmetry=`{spec['symmetry']}` · pattern=`{spec.get('pattern', 'rings')}`\n"
        f"  - palette: {spec['palette']} (첫 색=focal, 마지막=peripheral)\n"
        f"  - per_color_count: { {str(k): v for k, v in spec['per_color_count'].items()} }\n"
        f"  - density={spec.get('density', 0.32):.0%} · mask=`{spec.get('mask_shape', 'radial')}` · seed={spec['seed']}\n"
        f"  - rationale: {rationale}"
    )

    # ── Step 2: 4팀 경쟁 fan-out — 같은 spec, 다른 backend로 동시 생성
    from level_validator import validate_grid
    from level_png_renderer import render_grid_to_png
    from level_storage import save_level
    from design_teams import TEAMS, TeamRequest, run_team
    import concurrent.futures as _futures

    user_prompt_full = f"{title}\n{description or ''}".strip()

    _comment(
        f"🏁 **{len(TEAMS)}팀 경쟁 시작** — 같은 spec, 다른 알고리즘으로 병렬 생성\n"
        + "\n".join(f"  - {t.icon} `{tid}` ({t.label}) — {t.philosophy[:60]}"
                    for tid, t in TEAMS.items())
    )

    def _run_4_teams(seed_val: int) -> tuple[dict[str, Any], dict[str, str]]:
        """4팀을 ThreadPool로 병렬 실행. (results, errors) 반환."""
        req = TeamRequest(
            width=spec["width"], height=spec["height"],
            palette=spec["palette"],
            per_color_count=spec["per_color_count"],
            seed=seed_val,
            user_prompt=user_prompt_full,
            density=spec.get("density", 0.32),
            mask_shape=spec.get("mask_shape", "radial"),
        )

        def _run_one(tid: str) -> tuple[str, Optional[Any], Optional[str]]:
            try:
                return tid, run_team(tid, req), None
            except Exception as e:
                log.exception("[team:%s] failed", tid)
                return tid, None, f"{type(e).__name__}: {e}"

        team_ids = list(TEAMS.keys())
        team_results_local: dict[str, Any] = {}
        team_errors_local: dict[str, str] = {}
        with _futures.ThreadPoolExecutor(max_workers=4) as pool:
            for fut in _futures.as_completed(
                [pool.submit(_run_one, tid) for tid in team_ids]
            ):
                tid, res, err = fut.result()
                if res is not None:
                    team_results_local[tid] = res
                else:
                    team_errors_local[tid] = err or "unknown"
        return team_results_local, team_errors_local

    team_results, team_errors = _run_4_teams(spec["seed"])

    if not team_results:
        _comment(f"❌ 4팀 모두 생성 실패:\n" +
                 "\n".join(f"  - `{tid}`: {err}" for tid, err in team_errors.items()))
        return {"success": False, "error": "all teams failed", "next_status": "review"}

    # Q-C: 자동 health check — 명백한 실패면 seed 바꿔 1회 재시도
    health_ok, health_reason = _check_team_results_health(team_results, spec)
    if not health_ok:
        _comment(
            f"⚠️ **자동 재시도** — 1차 결과 품질 저조: {health_reason}. "
            f"새 seed로 4팀 재생성 중..."
        )
        retry_seed = spec["seed"] + 1000
        team_results_v2, team_errors_v2 = _run_4_teams(retry_seed)
        if team_results_v2:
            health_ok2, health_reason2 = _check_team_results_health(team_results_v2, spec)
            if health_ok2 or len(team_results_v2) > len(team_results):
                # 더 나은 결과 채택
                team_results = team_results_v2
                team_errors = team_errors_v2
                spec["seed"] = retry_seed
                _comment(f"✓ 재시도 성공 — {len(team_results)}팀 결과 채택 (seed={retry_seed})")
            else:
                _comment(f"ℹ️ 재시도도 약함 ({health_reason2}) — 1차 결과 유지")
        else:
            _comment("ℹ️ 재시도 실패 — 1차 결과 유지")

    # ── Step 3: 각 팀 결과 PNG 렌더 + DB 저장 (team_id 포함)
    cell_size_px = 22 if spec["width"] >= 20 else 32
    saved_levels: list[dict[str, Any]] = []  # [{team_id, level_id, png_filename, ...}]
    for tid in TEAMS.keys():
        if tid not in team_results:
            continue
        tr = team_results[tid]
        tspec = TEAMS[tid]
        # 검증 — hermes_native만 strict, 나머지는 informational
        v = validate_grid(
            tr.cells, symmetry="none",  # 팀별 symmetry가 다양함 → 본 검증은 lenient
            palette=tr.palette,
            width=tr.width, height=tr.height,
            enforce_axis_clear=False,
        )
        # palette 외 색이 들어왔는지만 보면 됨. 10-multiple 어긋나면 경고 표시.

        # PNG 렌더
        try:
            level_name = f"{tid}_{tr.pattern_chosen}"
            png_bytes = render_grid_to_png(
                tr.cells, cell_size_px=cell_size_px,
                title=f"{tspec.icon} {tspec.label} · {tr.pattern_chosen} · seed={tr.seed}",
            )
        except Exception as e:
            _comment(f"⚠️ {tid}: PNG 렌더 실패 — {e}")
            team_errors[tid] = f"render: {e}"
            continue

        try:
            saved = save_level(
                spec={
                    "width": tr.width, "height": tr.height,
                    "symmetry": "none",  # 팀마다 다름 — pattern_chosen이 진짜 식별자
                    "palette": tr.palette,
                    "per_color_count": tr.per_color_count,
                    "seed": tr.seed,
                    "pattern": tr.pattern_chosen,
                    "density": spec.get("density", 0.32),
                    "mask_shape": spec.get("mask_shape", "radial"),
                },
                cells=tr.cells, png_bytes=png_bytes,
                validation={
                    "ok": v.ok,
                    "errors": v.errors,
                    "color_counts": {str(k): vv for k, vv in v.color_counts.items()},
                    "filled_cells": v.filled_cells,
                    "empty_cells": v.empty_cells,
                    "lenient": True,  # 팀별 symmetry 미강제
                },
                task_id=task_id,
                task_title=title,
                created_by_email=task.get("created_by_email") or "",
                name=level_name,
                team_id=tid,
                pattern_chosen=tr.pattern_chosen,
            )
            # 🎈 BalloonFlow JSON 자동 변환 + task.attachments push (실패해도 흐름 유지)
            try:
                _export_balloonflow_attachment(
                    task=task, saved_id=saved["id"], level_name=level_name,
                )
            except Exception:
                log.exception("[bf-export] hook failed for team %s", tid)
            saved_levels.append({
                "team_id": tid,
                "team_label": tspec.label,
                "team_icon": tspec.icon,
                "level_id": saved["id"],
                "png_filename": saved["png_filename"],
                "pattern_chosen": tr.pattern_chosen,
                "filled": v.filled_cells,
                "color_count": len(v.color_counts),
            })
        except Exception as e:
            _comment(f"⚠️ {tid}: 저장 실패 — {e}")
            team_errors[tid] = f"save: {e}"

    if not saved_levels:
        _comment("❌ 저장 단계에서 모두 실패")
        return {"success": False, "error": "no levels saved", "next_status": "review"}

    # ── Step 4: 결과 요약 코멘트 (UI는 T4에서 4-썸네일 + 별점)
    summary_lines = ["🎨 **4팀 결과** — `/tasks?id=" + task_id + "`에서 비교·별점:"]
    for sl in saved_levels:
        summary_lines.append(
            f"  - {sl['team_icon']} **{sl['team_label']}** "
            f"(`{sl['team_id']}`/`{sl['pattern_chosen']}`) → "
            f"`/levels#level={sl['level_id']}` · {sl['filled']} filled · "
            f"{sl['color_count']} colors"
        )
    if team_errors:
        summary_lines.append("")
        summary_lines.append("⚠️ 일부 팀 실패:")
        for tid, err in team_errors.items():
            summary_lines.append(f"  - `{tid}`: {err}")
    _comment("\n".join(summary_lines))

    return {
        "success": True,
        "summary": (
            f"design/level {len(TEAMS)}팀 경쟁 완료 — {len(saved_levels)}/{len(TEAMS)} 팀 결과 저장. "
            f"별점 매겨주세요."
        ),
        "next_status": "review",  # 사용자 별점 대기
        "metadata": {
            "team_levels": saved_levels,
            "team_errors": team_errors,
            "spec": spec,
        },
    }


# ──────────────────────────────────────────────────────────────────────
# design/content 분과 — 컨텐츠 기획서 작성 파이프라인
# ──────────────────────────────────────────────────────────────────────
def _execute_content_pipeline(
    task: dict[str, Any],
    title: str,
    description: str,
    task_id: str,
    _comment,
) -> dict[str, Any]:
    """
    design/content 파이프라인 (피드백 루프 통합):
      1. (rework 시) 디렉터 review points 추출 — 직전 hermes 코멘트 이후의 비-hermes 코멘트 모두
      2. design_content_lead — 작업 계획 (rework 시 review point별 응답 계획 포함)
      3. design_content_writer — 마크다운 본문 (rework 시 "리뷰 응답" 섹션 필수)
      4. design_content_reviewer — 4축 점수 (완결성/일관성/응답품질/개선도) + verdict
      5. 점수 → 보상/페널티 (hermes_team_scores) — Lead/Writer/Reviewer 각각 기록
      6. attachment 저장 + 점수 카드 코멘트 + status=review (디렉터 재검수 요청)
      7. Slack DM (req 이메일이 있으면)

    표준 컨텍스트(puzzle methodologies + parameters/component_map)는 context_builder가
    pipeline_hint='design' + genre 감지 시 _shared/design/*에서 자동 주입.
    """
    import time as _time
    from datetime import datetime as _dt, timezone as _tz
    from agent_team import ExecutionEnv, invoke_agent
    from pymongo import MongoClient as _MC
    from bson import ObjectId

    is_rework = bool(task.get("_hermes_is_rework"))
    review_points = _extract_review_points(task) if is_rework else []
    prev_md = _last_attachment_md(task)
    if is_rework:
        if review_points:
            joined = "\n".join(f"  • {p}" for p in review_points[:6])
            _comment(f"🔁 **REWORK 모드** — 디렉터 리뷰 {len(review_points)}건 감지\n{joined}")
        else:
            _comment("🔁 REWORK 모드 — 단, 명시적 review point 추출 실패 (마지막 코멘트 사용)")

    # ── Step 1: Lead — 작업 계획 수립 (rework 시 review point별 응답 계획 포함)
    _comment("📋 **design_content_lead** 작업 계획 수립 중...")
    lead_env = ExecutionEnv(
        mode="local", cwd=str(Path.home()), timeout_sec=180,
        task_id=task_id, task_title=title,
        team="design", sub_team="content",
    )
    lead_prompt = _build_content_lead_prompt(title, description, task, is_rework, review_points, prev_md)
    lead_resp = invoke_agent("design_content_lead", lead_prompt, lead_env)
    if not lead_resp.success:
        _comment(f"❌ lead 실패: {lead_resp.error}")
        return {"success": False, "error": lead_resp.error or "content_lead failed",
                "next_status": "review"}
    plan_text = (lead_resp.output or "").strip()
    if not plan_text:
        _comment("⚠️ lead가 빈 응답 — review 대기")
        return {"success": False, "error": "empty plan", "next_status": "review"}
    _comment(f"📋 작업 계획:\n```\n{plan_text[:700]}\n```")

    # ── Step 2: Writer — 마크다운 본문 (timeout 600s — 5분→10분 상향, 큰 본문 대응)
    _comment("✍️ **design_content_writer** 문서 작성 중...")
    writer_env = ExecutionEnv(
        mode="local", cwd=str(Path.home()), timeout_sec=600,
        task_id=task_id, task_title=title,
        team="design", sub_team="content",
    )
    writer_prompt = _build_content_writer_prompt(
        title, description, plan_text, task, is_rework, review_points, prev_md
    )
    writer_resp = invoke_agent("design_content_writer", writer_prompt, writer_env)
    if not writer_resp.success:
        _comment(f"❌ writer 실패: {writer_resp.error}")
        return {"success": False, "error": writer_resp.error or "content_writer failed",
                "next_status": "review"}
    md_text = _extract_markdown_body(writer_resp.output or "")
    if not md_text or len(md_text) < 200:
        _comment(
            f"⚠️ writer 출력이 너무 짧거나 마크다운이 아닙니다 "
            f"({len(md_text)} chars). 응답 샘플:\n```\n{(writer_resp.output or '')[:400]}\n```"
        )
        return {"success": False, "error": "writer returned non-markdown",
                "next_status": "review"}

    # ── Step 2.5: design validator (스키마/계약/밸런스 정합 게이트) [granular_v1]
    _des_sub = (task.get("sub_team") or "content")
    _des_val_role = resolve_role("design", _des_sub, "validator")
    if _des_val_role not in {"validator", "reviewer"}:
        _dv_env = ExecutionEnv(mode="local", cwd=str(Path.home()), timeout_sec=120,
                               task_id=task_id, task_title=title, team="design", sub_team=_des_sub)
        _dv_prompt = (
            f"기획 문서 정합 검증(품질평가 아닌 스키마/계약/밸런스 검증). 태스크: {title}\n"
            f"=== 문서 ===\n{md_text[:6000]}\n=== 끝 ===\n"
            "①필수 섹션/스키마 ②수치 근거(공식/DB) ③계약/교차참조 일관성 ④밸런스 명백한 오류 "
            "를 각 OK/WARN/FAIL로. JSON {verdict: ok|revise|fail, quality_score: 0-100, notes: str}."
        )
        _dvr = invoke_agent(_des_val_role, _dv_prompt, _dv_env)
        if _dvr.success:
            _dvs = _dvr.structured or {}
            _dvv = (_dvs.get("verdict") or "ok").lower()
            try:
                _dvsc = int(_dvs.get("quality_score")) if _dvs.get("quality_score") is not None else 70
            except (TypeError, ValueError):
                _dvsc = 70
            _comment(f"\U0001F50D **{_des_val_role}** 정합검증: `{_dvv}` — {(_dvs.get('notes') or '')[:180]}")
            _record_quality_score(task_id=task_id, team="design", sub_team=_des_sub,
                                  role=_des_val_role, score=_dvsc, verdict=_dvv,
                                  summary=(_dvs.get('notes') or '')[:300])

    # ── Step 3: Reviewer — 4축 평가
    _comment("🔎 **design_content_reviewer** 4축 검수 중...")
    reviewer_env = ExecutionEnv(
        mode="local", cwd=str(Path.home()), timeout_sec=180,
        task_id=task_id, task_title=title,
        team="design", sub_team="content",
    )
    reviewer_prompt = _build_content_reviewer_prompt(
        title, description, md_text, is_rework, review_points, prev_md
    )
    try:
        from reviewer_retrieval import build_retrieval_block as _retr_block
        _retr = _retr_block(title, description, task_id)
        if _retr:
            reviewer_prompt += "\n\n" + _retr
    except Exception:
        log.exception("reviewer_retrieval injection failed (non-fatal)")
    reviewer_resp = invoke_agent("design_content_reviewer", reviewer_prompt, reviewer_env)
    review_raw = (reviewer_resp.output or "").strip()
    scores = _parse_reviewer_scores(review_raw, reviewer_resp.structured)
    total = scores.get("total", 0)
    verdict = scores.get("verdict", "REVIEW")

    # ── Step 4: 점수 기록 (Lead / Writer / Reviewer 각각, 보상 체계 누적)
    # Lead·Writer는 reviewer가 매긴 본문 점수의 가중치를 받음 (writer=full, lead=plan_alignment)
    # Reviewer는 자체 결과의 일관성을 self-rated (간이값) 부여
    _record_quality_score(
        task_id=task_id, team="design", sub_team="content",
        role="design_content_writer", score=total, verdict=verdict,
        summary=scores.get("brief", "")[:500],
    )
    _record_quality_score(
        task_id=task_id, team="design", sub_team="content",
        role="design_content_lead",
        score=min(100, total + (5 if scores.get("plan_alignment_bonus") else 0)),
        verdict=verdict, summary=f"plan→writer alignment ({total} base)",
    )
    _record_quality_score(
        task_id=task_id, team="design", sub_team="content",
        role="design_content_reviewer",
        score=80 if scores.get("breakdown") else 50,  # 4축 출력 안 되면 자체 페널티
        verdict="OK" if scores.get("breakdown") else "WEAK",
        summary="reviewer self-coherence",
    )

    # 보상/페널티 라벨 (시각화용)
    reward_label, reward_emoji = _reward_label_for(total)

    # ── Step 5: 첨부 저장
    cycle = _next_cycle_number(task)
    safe_title = "".join(c if (c.isalnum() or c in "-_") else "_" for c in title.replace("[", "").replace("]", "_"))[:80]
    fname = f"{safe_title or 'content'}_v{cycle}.md"
    att = {
        "id": f"{int(_time.time()*1000)}-content-v{cycle}",
        "kind": "md",
        "name": fname,
        "mime": "text/markdown",
        "size": len(md_text.encode("utf-8")),
        "content": md_text,
    }
    try:
        _c = _MC(MONGO_URI, serverSelectionTimeoutMS=5000)
        _c[DB_NAME]["pixelforge_tasks"].update_one(
            {"_id": ObjectId(task_id)},
            {"$push": {"attachments": att}, "$set": {"updated_at": _dt.now(_tz.utc).isoformat()}},
        )
    except Exception:
        log.exception("attachment save failed")
        return {"success": False, "error": "attachment save failed", "next_status": "review"}

    # ── Step 6: 점수 카드 코멘트 (시각적 요약)
    _comment(_build_score_card_comment(
        cycle=cycle, fname=fname, md_chars=len(md_text),
        scores=scores, reward_label=reward_label, reward_emoji=reward_emoji,
        is_rework=is_rework, review_points=review_points,
    ))

    # ── Step 7: 디렉터에게 Slack DM (재검수 요청)
    try:
        creator = (task.get("created_by_email") or "").strip().lower()
        _send_slack_success(
            email=creator, title=title,
            summary=(
                f"v{cycle} 결과물 첨부 — {reward_emoji} {total}/100 ({verdict})\n"
                f"파일: {fname} ({len(md_text):,} chars)\n"
                + (f"리뷰 응답: {len(review_points)}건" if is_rework else "초안")
            ),
            pr_url="",
            fallback_assignee=(task.get("assignee") or ""),
        )
    except Exception:
        log.exception("slack notify failed")

    return {
        "success": True,
        "summary": f"design/content v{cycle} 완료 — {fname} ({total}/100 {verdict})",
        "next_status": "review",
        "metadata": {
            "attachment": fname, "size": att["size"],
            "score": total, "verdict": verdict, "cycle": cycle,
            "review_points": len(review_points),
        },
    }


def _extract_review_points(task: dict[str, Any]) -> list[str]:
    """
    rework 모드: 마지막 hermes 코멘트 이후의 모든 비-hermes 코멘트를 review points로 추출.
    각 항목은 200자 이내로 자름.
    """
    comments = task.get("comments") or []
    HERMES_NAMES = {"hermes", "hermes-bot", "헤르메스"}
    # 뒤에서 앞으로 훑으며 hermes 코멘트 만나면 stop. 그 사이 비-hermes들이 review points.
    points: list[str] = []
    for c in reversed(comments):
        author = (c.get("author") or "").strip().lower()
        if author in HERMES_NAMES:
            break
        text = (c.get("text") or "").strip()
        if not text:
            continue
        # ask_owner 코멘트는 시스템 발송이므로 스킵
        if (c.get("kind") or "") == "ask_owner":
            continue
        points.append(text[:300])
    points.reverse()  # 시간순
    return points


def _last_attachment_md(task: dict[str, Any]) -> str:
    """직전 산출물(.md) 본문. rework 시 비교용. 없거나 너무 길면 빈 문자열 또는 발췌."""
    atts = task.get("attachments") or []
    md_atts = [a for a in atts if (a.get("kind") == "md" and a.get("content"))]
    if not md_atts:
        return ""
    last = md_atts[-1]
    content = last.get("content") or ""
    # 너무 길면 발췌 (reviewer 비교에는 충분)
    return content[:6000] + ("\n\n... [v1 truncated]" if len(content) > 6000 else "")


def _next_cycle_number(task: dict[str, Any]) -> int:
    """이미 첨부된 .md 개수 + 1 = 이번 cycle (v1, v2, ...)."""
    atts = task.get("attachments") or []
    return sum(1 for a in atts if a.get("kind") == "md") + 1


def _parse_reviewer_scores(raw: str, structured: Any = None) -> dict[str, Any]:
    """
    Reviewer 응답에서 4축 점수 추출. 구조화된 응답(structured) 우선.
    실패 시 텍스트에서 점수: NN/100 패턴 fallback.

    반환:
      {
        "completeness": int (0-25),
        "consistency": int (0-25),
        "response_quality": int (0-25),  # rework 시에만 의미
        "improvement": int (0-25),       # rework 시에만 의미
        "total": int (0-100),
        "verdict": "APPROVED" | "REVISE" | "REJECT" | "REVIEW",
        "breakdown": bool (4축 모두 잡혔으면 True),
        "plan_alignment_bonus": bool,
        "brief": str,
      }
    """
    import re as _re
    out = {
        "completeness": 0, "consistency": 0,
        "response_quality": 0, "improvement": 0,
        "total": 0, "verdict": "REVIEW",
        "breakdown": False, "plan_alignment_bonus": False,
        "brief": "",
    }
    # 1차: structured(JSON)에서
    if isinstance(structured, dict):
        for k_in, k_out in (("completeness", "completeness"), ("consistency", "consistency"),
                            ("response_quality", "response_quality"), ("improvement", "improvement"),
                            ("response", "response_quality")):
            v = structured.get(k_in)
            if isinstance(v, (int, float)):
                out[k_out] = max(0, min(25, int(v)))
        if structured.get("verdict"):
            out["verdict"] = str(structured["verdict"])[:16].upper()
        if structured.get("strengths"):
            out["brief"] = str(structured["strengths"])[:300]
        if structured.get("plan_alignment"):
            out["plan_alignment_bonus"] = True

    # 2차: raw 텍스트에서 점수 추출
    if not out["breakdown"]:
        # "완결성: 22/25" 패턴
        for label, key in (("완결성", "completeness"), ("일관성", "consistency"),
                           ("응답품질", "response_quality"), ("응답 품질", "response_quality"),
                           ("개선도", "improvement"), ("정합성", "consistency"),
                           ("실용성", "improvement")):
            m = _re.search(rf"{label}[:：]\s*(\d+)\s*/\s*25", raw)
            if m:
                out[key] = max(0, min(25, int(m.group(1))))

    # 합계
    breakdown_total = (
        out["completeness"] + out["consistency"]
        + out["response_quality"] + out["improvement"]
    )
    if breakdown_total > 0:
        out["total"] = min(100, breakdown_total)
        out["breakdown"] = breakdown_total >= 25  # 최소 한 축 이상 잡혀야 인정
    else:
        # fallback: "점수: 85/100" 또는 "quality_score: 85"
        m = _re.search(r"(?:점수|score|quality_score)[:：]?\s*(\d+)\s*(?:/100)?", raw, _re.IGNORECASE)
        if m:
            out["total"] = max(0, min(100, int(m.group(1))))

    # verdict 정규화
    raw_upper = raw.upper()
    if "APPROVED" in raw_upper or "PASS" in raw_upper:
        out["verdict"] = "APPROVED"
    elif "REJECT" in raw_upper or "FAIL" in raw_upper:
        out["verdict"] = "REJECT"
    elif "REVISE" in raw_upper or "재작성" in raw or "수정" in raw:
        out["verdict"] = "REVISE"
    elif out["total"] >= 80:
        out["verdict"] = "APPROVED"
    elif out["total"] >= 60:
        out["verdict"] = "REVISE"
    elif out["total"] > 0:
        out["verdict"] = "REJECT"

    if not out["brief"]:
        # raw에서 "강점:" 다음 라인 추출
        m = _re.search(r"강점[:：]\s*([^\n]+)", raw)
        if m:
            out["brief"] = m.group(1).strip()[:300]

    return out


def _reward_label_for(score: int) -> tuple[str, str]:
    """점수 → (라벨, 이모지). 보상/페널티 시각화 + team_score 추적용."""
    if score >= 85:
        return ("EXCELLENT (+2 보상)", "🌟")
    if score >= 70:
        return ("GOOD (+1 보상)", "✅")
    if score >= 50:
        return ("NEUTRAL (변동 없음)", "➖")
    if score >= 30:
        return ("WEAK (-1 페널티)", "⚠️")
    return ("BAD (-2 페널티)", "❌")


def _build_score_card_comment(
    *, cycle: int, fname: str, md_chars: int,
    scores: dict[str, Any], reward_label: str, reward_emoji: str,
    is_rework: bool, review_points: list[str],
) -> str:
    """점수 카드 형식 코멘트. ProjectHub UI에서 한눈에 파악 가능."""
    total = scores.get("total", 0)
    verdict = scores.get("verdict", "REVIEW")
    bd = (
        f"  • 완결성:    {scores['completeness']}/25\n"
        f"  • 일관성:    {scores['consistency']}/25\n"
        f"  • 응답품질:  {scores['response_quality']}/25 {'(rework)' if is_rework else '(N/A 초안)'}\n"
        f"  • 개선도:    {scores['improvement']}/25 {'(vs v' + str(cycle-1) + ')' if cycle > 1 else '(N/A 초안)'}\n"
    )
    rework_line = (
        f"\n📝 리뷰 응답: {len(review_points)}건 처리\n"
        if is_rework else "\n📝 초안 cycle (v1)\n"
    )
    return (
        f"📊 **v{cycle} 검수 완료** {reward_emoji} **{total}/100** ({verdict})\n"
        f"\n축별 점수:\n{bd}"
        f"{rework_line}"
        f"\n팀 점수 갱신: design/content — {reward_label}\n"
        f"\n📎 결과물: `{fname}` ({md_chars:,} chars)\n"
        f"`/tasks` → 상세 모달 → **결과물** 섹션에서 다운로드.\n"
        f"\n💬 추가 리뷰 코멘트 → 자동 재작업 (cycle v{cycle+1})\n"
        f"만족스러우면 status를 `done`으로 변경해주세요."
    )


def _scoped_standards_block(
    task: dict[str, Any], *, full: bool = True, max_chars: int = 50000, pipeline_hint: str = "design",
) -> str:
    """
    A8 배선: scoped memory(팀 표준/디렉션)를 실제로 프롬프트에 주입.
    이전엔 load_scoped_memory 결과가 어디에도 주입되지 않아(format_as_prompt 호출처 0건)
    프롬프트가 "표준 자동주입됨"이라 말만 하고 실제 표준은 없던 사문화 상태였음.

    full=True  → 표준 본문 전체 (Writer 등 실제 인용 주체용, max_chars로 상한)
    full=False → 표준 파일명 목록만 (Lead 계획용, 저비용)
    실패 시 빈 문자열 (기존 동작 유지).
    """
    try:
        from user_name_resolver import resolve_scope_from_task
        from scoped_memory_loader import load_scoped_memory, format_as_prompt
        scope = resolve_scope_from_task(task)
        files = load_scoped_memory(
            team=scope.get("team"), genre=scope.get("genre"),
            role=scope.get("role"), project=scope.get("project"),
            include_user_private=False, pipeline_hint=pipeline_hint,
        )
        if not files:
            return ""
        if not full:
            names = "\n".join(f"- {f['path']}" for f in files)
            return "\n\n## 📚 인용 가능한 팀 표준/디렉션 목록 (본문은 Writer에 주입됨)\n" + names
        text = format_as_prompt(files)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... [표준 일부 생략 — 길이 제한]"
        return "\n\n## 📚 주입된 팀 표준/디렉션 (적극 참조·인용, §섹션 명시)\n" + text
    except Exception:
        log.debug("scoped standards injection skipped (non-fatal)", exc_info=True)
        return ""


def _build_content_lead_prompt(
    title: str, description: str, task: dict[str, Any],
    is_rework: bool = False, review_points: list[str] = None, prev_md: str = "",
) -> str:
    """Lead에게 컨텐츠 작업 계획 수립 지시. rework 모드면 review point별 응답 계획 포함."""
    review_points = review_points or []
    comments = task.get("comments") or []
    recent = "\n".join(
        f"- [{c.get('author', '?')}]: {(c.get('text') or '')[:200]}"
        for c in comments[-5:]
    ) or "(없음)"

    rework_block = ""
    if is_rework and review_points:
        pts = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(review_points[:6]))
        rework_block = (
            f"\n## 🔁 REWORK 모드 — 디렉터 리뷰 응답 필수\n"
            f"이전 cycle 결과물에 대해 디렉터가 다음 사항을 지적했습니다:\n{pts}\n\n"
            f"**계획에 다음을 반드시 포함**:\n"
            f"- 각 review point에 어떻게 답변할지 (1:1 매핑)\n"
            f"- 본문 어느 섹션을 추가/수정할지\n"
            f"- 이전 산출물의 어떤 가정/수치를 변경할지\n"
        )
    elif is_rework:
        rework_block = (
            f"\n## 🔁 REWORK 모드 — 명시적 review point 추출 실패\n"
            f"최근 코멘트(아래)를 단서로 개선 방향 추정\n"
        )

    return (
        "다음 컨텐츠 기획 task의 **작업 계획**을 수립해주세요.\n\n"
        f"## Task\n"
        f"제목: {title}\n"
        f"설명: {description or '(설명 없음)'}\n"
        f"{rework_block}\n"
        f"## 최근 코멘트\n{recent}\n\n"
        f"## 출력 형식 (자유 형식, 짧게 — 500자 이내)\n"
        f"1. 어떤 섹션을 포함할지 (제목 list)\n"
        f"2. 어떤 표준/디렉션 문서를 인용할지\n"
        f"3. 어떤 합리적 가정을 둘지 (불명확한 항목)\n"
        + (f"4. 각 review point별 응답 계획 (1:1)\n" if is_rework else "")
        + f"\n## 주의\n"
        f"- 인용 가능한 팀 표준 목록이 아래에 주입됨 (본문은 Writer 단계에서 주입됨) — 어떤 표준을 인용할지 계획에 반영\n"
        f"- 사용자에게 추가 질문 자제. 합리적 가정으로 진행하고 designer_note에 명시"
        + _scoped_standards_block(task, full=False)
    )


def _build_content_writer_prompt(
    title: str, description: str, plan: str, task: dict[str, Any],
    is_rework: bool = False, review_points: list[str] = None, prev_md: str = "",
) -> str:
    """Writer에게 마크다운 본문 작성 지시. rework 시 '리뷰 응답' 섹션 + prev_md 발췌."""
    review_points = review_points or []
    # RAG: 관련 기획 디렉션(design_base) + 유사 task 주입 (실패 시 빈 문자열)
    _design_ctx = ""
    try:
        from hermes_atlas_retrieval import build_design_block
        _design_ctx = build_design_block(title, description)
    except Exception:
        log.debug("design retrieval skipped (writer)", exc_info=True)
    rework_block = ""
    if is_rework and review_points:
        pts = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(review_points[:6]))
        prev_excerpt = ""
        if prev_md:
            prev_excerpt = f"\n## 이전 산출물 (v{1} 발췌)\n{prev_md[:2500]}\n"
        rework_block = (
            f"\n## 🔁 REWORK — 본문에 반드시 포함할 추가 섹션\n"
            f"### `## 리뷰 응답 (이전 cycle 디렉터 피드백)` 섹션 — 본문 상단부에 배치\n"
            f"각 review point에 대해 **답변 + 변경 내용 요약 + 본문 어느 섹션이 바뀌었는지**:\n{pts}\n"
            f"{prev_excerpt}"
        )

    return (
        "다음 task의 **컨텐츠 기획서를 마크다운으로 작성**해주세요.\n\n"
        f"## Task\n"
        f"제목: {title}\n"
        f"설명: {description or '(설명 없음)'}\n"
        f"{rework_block}\n"
        f"## Lead가 수립한 계획\n{plan}\n\n"
        f"## 작성 규칙\n"
        f"1. **마크다운만** 출력 (코드 블록 등으로 감싸지 말고, 본문 그대로)\n"
        f"2. 첫 줄은 `# 제목`으로 시작\n"
        f"3. 컨텍스트의 puzzle 표준(parameters/cross_validation 등)을 적극 인용. 인용 시 §섹션 명시\n"
        f"4. 수치는 task 설명의 확정값 + 자동 주입 표준을 우선 사용\n"
        f"5. 불확실한 가정은 `### 디자이너 노트(designer_note)` 섹션에 명시\n"
        f"6. 마지막에 `## 변경 이력` 표 + `## 관련 문서` 리스트 필수\n"
        + (f"7. **리뷰 응답** 섹션을 본문 상단(## 1 또는 2)에 명시적으로 배치\n" if is_rework else "")
        + f"\n## 절대 금지\n"
        f"- 사용자에게 되묻기 (\"X를 알려주세요\" 등) — 합리적 가정 + designer_note로 처리\n"
        f"- 마크다운 외 형식 (JSON / YAML 단독 출력 금지. yaml 코드블록은 본문 안에서 OK)\n"
        f"- 코드 블록으로 전체 본문 감싸기 (```markdown ... ``` 같은 wrapper 금지)"
        + _design_ctx
        + _scoped_standards_block(task, full=True)
    )


def _build_content_reviewer_prompt(
    title: str, description: str, md_text: str,
    is_rework: bool = False, review_points: list[str] = None, prev_md: str = "",
) -> str:
    """Reviewer에게 4축 평가 지시. JSON 출력 권장."""
    review_points = review_points or []
    excerpt = md_text[:3500] + ("\n... [truncated]" if len(md_text) > 3500 else "")

    rework_block = ""
    if is_rework and review_points:
        pts = "\n".join(f"  {i+1}. {p}" for i, p in enumerate(review_points[:6]))
        prev_block = (
            f"\n## 이전 cycle (v1) 본문 발췌\n{prev_md[:2000]}\n"
            if prev_md else "\n## 이전 cycle 본문 없음\n"
        )
        rework_block = (
            f"\n## 🔁 REWORK 모드 — rework 응답 품질 평가 포함\n"
            f"디렉터가 v1에 대해 다음을 지적:\n{pts}\n"
            f"{prev_block}"
        )

    return (
        "다음 컨텐츠 기획서를 **4축으로 검수**하고 JSON으로 점수를 출력해주세요.\n\n"
        f"## Task\n"
        f"제목: {title}\n"
        f"설명: {description or '(설명 없음)'}\n"
        f"{rework_block}\n"
        f"## 작성된 문서 (최대 3500자 발췌)\n{excerpt}\n\n"
        f"## 평가 4축 (각 0-25점, 합계 0-100)\n"
        f"1. **완결성 (completeness)**: task 설명의 모든 요구사항을 다뤘는가\n"
        f"2. **일관성 (consistency)**: cross_validation 기준 수치(부스터 가격, 코인, 라이프 등)가 다른 디렉션 문서와 일치하는가\n"
        + (f"3. **응답품질 (response_quality)**: 디렉터의 review point들에 1:1로 명확히 답변했는가\n"
           f"4. **개선도 (improvement)**: 이전 cycle 대비 명확한 개선이 있는가\n"
           if is_rework else
           f"3. **응답품질 (response_quality)**: 초안이라 N/A — 25점 부여\n"
           f"4. **개선도 (improvement)**: 초안이라 N/A — 25점 부여\n")
        + f"\n## 출력 형식 — JSON only (다른 텍스트 금지)\n"
        f"```json\n"
        f"{{\n"
        f'  "completeness": <0-25>,\n'
        f'  "consistency": <0-25>,\n'
        f'  "response_quality": <0-25>,\n'
        f'  "improvement": <0-25>,\n'
        f'  "verdict": "APPROVED" | "REVISE" | "REJECT",\n'
        f'  "strengths": "<1-2문장>",\n'
        f'  "concerns": "<1-2문장 — 구체적 항목>",\n'
        f'  "plan_alignment": <true|false>\n'
        f"}}\n"
        f"```\n"
        f"verdict 기준: 80+ APPROVED / 60-79 REVISE / <60 REJECT"
    )


def _extract_markdown_body(text: str) -> str:
    """
    Writer 응답에서 마크다운 본문 추출.
    1) ```markdown ... ``` 래퍼가 있으면 안쪽만
    2) 없으면 # 시작 줄 부터 끝까지
    3) 둘 다 없으면 전체
    """
    s = (text or "").strip()
    if not s:
        return ""
    # ```markdown ... ``` 또는 ``` ... ``` 래퍼 처리
    import re as _re
    m = _re.search(r"^```(?:markdown|md)?\s*\n(.*)\n```\s*$", s, flags=_re.DOTALL)
    if m:
        return m.group(1).strip()
    # # 헤더로 시작하는 첫 줄부터
    lines = s.splitlines()
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("#"):
            return "\n".join(lines[i:]).strip()
    return s


def _build_level_designer_prompt(title: str, description: str, task: dict[str, Any]) -> str:
    """designer에게 사용자 요청 + 직전 시도 컨텍스트 전달."""
    comments = task.get("comments") or []
    recent = "\n".join(
        f"- [{c.get('author', '?')}]: {(c.get('text') or '')[:200]}"
        for c in comments[-5:]
    ) or "(없음)"
    return (
        "Generate a level grid spec (JSON only — no prose outside the code block).\n\n"
        f"## User Task\n"
        f"Title: {title}\n"
        f"Description: {description or '(설명 없음)'}\n\n"
        f"## Recent comments (for context)\n{recent}\n\n"
        f"## Reminder\n"
        f"You output spec ONLY. The deterministic generator draws the actual cells with "
        f"perfect symmetry and 10-multiple counts. Pick palette colors from BalloonFlow's "
        f"24-color set (indices 0..23). Use 4-fold-rot for kaleidoscope feel by default.\n\n"
        f"Return JSON only in a ```json``` block per your persona spec."
    )


def _build_level_reviewer_prompt(
    *, title: str, description: str, spec: dict[str, Any],
    validation_report, image_path: str,
) -> str:
    color_counts = ", ".join(f"c{k}={v}" for k, v in sorted(validation_report.color_counts.items()))
    return (
        "Review this generated level. Use Read tool to view the PNG before scoring.\n\n"
        f"## User Task\n"
        f"Title: {title}\n"
        f"Description: {description or '(설명 없음)'}\n\n"
        f"## Image path (use Read tool)\n"
        f"{image_path}\n\n"
        f"## Spec (designer가 결정한 것)\n"
        f"  - name: {spec['name']}\n"
        f"  - {spec['width']}×{spec['height']} · symmetry={spec['symmetry']}\n"
        f"  - palette: {spec['palette']}\n"
        f"  - per_color_count: { {str(k): v for k, v in spec['per_color_count'].items()} }\n"
        f"  - seed: {spec['seed']}\n\n"
        f"## Validation report (이미 통과한 사실들)\n"
        f"  - symmetry={spec['symmetry']} ✓ (위반 0건)\n"
        f"  - 색상별 카운트 모두 10의 배수 ✓ ({color_counts})\n"
        f"  - palette 모두 BalloonFlow 0..23 범위 ✓\n"
        f"  - filled={validation_report.filled_cells}, empty={validation_report.empty_cells}\n\n"
        f"Now Read the PNG and evaluate VISUAL quality only (palette harmony, density, "
        f"composition, request fit). Return JSON only per your persona output format."
    )


def _normalize_level_spec(raw: dict[str, Any]) -> dict[str, Any]:
    """designer 응답 → 검증된 dict. 잘못된 값은 ValueError."""
    width = int(raw.get("width", 25))
    height = int(raw.get("height", 25))
    symmetry = str(raw.get("symmetry") or "4-fold-rot").lower()
    if symmetry not in {"none", "2-fold-h", "2-fold-v", "4-fold", "diagonal", "4-fold-rot"}:
        raise ValueError(f"unknown symmetry: {symmetry}")

    palette_raw = raw.get("palette") or []
    if not isinstance(palette_raw, list) or not palette_raw:
        raise ValueError("palette must be non-empty list of int color indices")
    palette: list[int] = []
    for v in palette_raw:
        try:
            iv = int(v)
        except (TypeError, ValueError):
            raise ValueError(f"palette element {v!r} not int")
        if not (0 <= iv <= 23):
            raise ValueError(f"palette color {iv} out of BalloonFlow range 0..23")
        if iv not in palette:
            palette.append(iv)
    if not (2 <= len(palette) <= 11):
        raise ValueError(f"palette size {len(palette)} not in 2..11")

    pcc_raw = raw.get("per_color_count") or {}
    if not isinstance(pcc_raw, dict):
        raise ValueError("per_color_count must be dict")
    pcc: dict[int, int] = {}
    for k, v in pcc_raw.items():
        try:
            ck = int(k)
            cv = int(v)
        except (TypeError, ValueError):
            raise ValueError(f"per_color_count entry {k}:{v} not int-convertible")
        if ck not in palette:
            raise ValueError(f"per_color_count has color {ck} not in palette")
        pcc[ck] = cv

    seed = int(raw.get("seed", 0)) or 0
    name = str(raw.get("name") or "level")[:80]
    pattern = str(raw.get("pattern") or "rings").lower()
    if pattern not in {"random", "rings", "rays", "spiral", "diamond", "blocks"}:
        raise ValueError(f"unknown pattern: {pattern}")

    # 모양 제어 — density(0.15~0.6) + mask_shape (radial 기본 — 인게임 puzzle focal)
    try:
        density = float(raw.get("density", 0.32))
    except (TypeError, ValueError):
        density = 0.32
    density = max(0.05, min(0.85, density))
    mask_shape = str(raw.get("mask_shape") or "radial").lower()
    if mask_shape not in {"uniform", "radial", "ring", "corners"}:
        mask_shape = "radial"

    return {
        "width": width, "height": height,
        "symmetry": symmetry, "palette": palette,
        "per_color_count": pcc,
        "seed": seed, "name": name, "pattern": pattern,
        "density": density, "mask_shape": mask_shape,
    }


@_with_trace("unity_modify")
def _should_abort(task_id: Any) -> bool:
    """A7 협조적 취소: stage 경계에서 호출. task가 삭제됐거나 hermes_stopped면 True.
    happy-path엔 영향 없음(중단 플래그/삭제일 때만 True). 경량 단일 쿼리."""
    try:
        from bson import ObjectId as _OID
        _c = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
        d = _c[DB_NAME]["pixelforge_tasks"].find_one({"_id": _OID(str(task_id))}, {"hermes_stopped": 1})
        return (d is None) or bool(d.get("hermes_stopped"))
    except Exception:
        return False


def _abort_result(stage: str) -> dict[str, Any]:
    return {
        "success": True,
        "summary": f"⛔ 중단 요청 감지 — '{stage}' 단계 전에 파이프라인을 멈췄습니다.",
        "next_status": "review",
        "metadata": {"stopped_at": stage},
    }


def _handle_unity_modify(task: dict[str, Any], context: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    """
    5-역할 에이전트 팀으로 Unity 코드 수정 + Git PR 생성.

    Lead → Main Coder → Sub Coder ×2(병렬) → Validator → Reviewer → Git 워크플로우

    현재(OpenAI 키 대기): 모든 역할 Claude Code 호출
    OpenAI 키 도착 후: agent_team.AGENT_ROLES 테이블 수정으로 자동 전환
    """
    from agent_team import (
        ExecutionEnv, invoke_agent, run_parallel_agents,
        LEAD_PROMPT_TEMPLATE, MAIN_CODER_PROMPT_TEMPLATE,
        SUB_CODER_PROMPT_TEMPLATE, VALIDATOR_PROMPT_TEMPLATE, REVIEWER_PROMPT_TEMPLATE,
        TRANSLATOR_PROMPT_TEMPLATE,
    )

    task_id = str(task.get("_id"))
    short_id = task_id[-8:]
    title = task.get("title", "")
    description = task.get("description", "")
    is_rework = bool(task.get("_hermes_is_rework"))

    # Reviewer 자가 평가 — 사용자가 reject한 직후 이 사이클이 시작되므로,
    # 이전 사이클에서 APPROVED 했던 reviewer에게 페널티를 기록한다.
    if is_rework:
        _penalize_previous_reviewer(task_id)

    # === Phase-based execution: 이미 분할된 task면 현재 phase로 description 좁힘 ===
    phase_plan = task.get("phase_plan") or []
    current_phase_n = int(task.get("current_phase") or 1)
    phase_log = task.get("phase_log") or []
    is_phased = bool(phase_plan)
    if is_phased and current_phase_n <= len(phase_plan):
        cur_phase = phase_plan[current_phase_n - 1]
        prev_log_text = "\n".join(
            f"  - phase {e.get('phase')}: {e.get('summary', '')[:200]} (commit: {e.get('commit', '?')[:8]})"
            for e in phase_log
        ) or "  (없음 — 첫 phase)"
        description = (
            f"[PHASE {current_phase_n}/{len(phase_plan)}: {cur_phase.get('name')}]\n\n"
            f"## 원본 태스크\n{description}\n\n"
            f"## 이번 phase 범위 (이번 사이클에 할 것만)\n"
            f"- 영역: {cur_phase.get('name')}\n"
            f"- 대상 파일 후보: {', '.join(cur_phase.get('files') or [])}\n"
            f"- 예상 변경량: {cur_phase.get('estimated_lines', '?')}줄\n"
            f"- 분할 근거: {cur_phase.get('rationale', '')}\n\n"
            f"## 이전 phase 완료 내역\n{prev_log_text}\n\n"
            f"이번 phase 범위 안에서만 작업하고 commit 가능한 단위로 마무리. "
            f"다음 phase는 별도 사이클에서 자동 진행됨. 절대 phase_plan 다시 반환하지 말 것."
        )

    # === 팀 기반 분기 (Session 13+14) ===================================
    # 사용자가 수동으로 재배정한 팀(team_override=True)은 Translator 판정을 덮어쓰지 않고
    # 즉시 해당 파이프라인으로 라우팅한다 — Unity git 브랜치 준비 같은 dev-only 단계를
    # 아트/챗 태스크에 대해 실행하지 않도록.
    stored_team = (task.get("team") or "").lower()
    team_override = bool(task.get("team_override"))
    if team_override and stored_team == "art":
        log.info("[team_dispatch] %s → art pipeline (user override)", short_id)
        return _execute_art_pipeline(task)
    if team_override and stored_team == "chat":
        log.info("[team_dispatch] %s → chat handler (user override)", short_id)
        return _execute_chat_only(task)
    if team_override and stored_team == "design":
        log.info("[team_dispatch] %s → design pipeline (user override)", short_id)
        return _execute_design_pipeline(task)

    # 전체 코멘트 이력 (이전 Hermes 작업 + 사용자 피드백 포함)
    all_comments = task.get("comments") or []
    comments_text = "\n".join(
        f"- [{c.get('author', '?')}]: {(c.get('text') or '')[:300]}"
        for c in all_comments[-8:]  # 최근 8개
    ) or "(없음)"

    # writer는 image/rework 처리에서 모두 필요하므로 맨 먼저
    from projecthub_writer import ProjectHubWriter as _PHW
    from pymongo import MongoClient as _MC
    _c = _MC(MONGO_URI)
    _wr = _PHW(_c[DB_NAME]["pixelforge_tasks"])

    def _early_comment(text: str) -> None:
        try:
            _wr.add_comment(task_id, text, author="hermes")
        except Exception:
            log.exception("early comment failed")

    # ── Multi-repo 라우팅 — PM이 sub_team을 결정한 뒤 그에 매핑된 레포로 모든 후속 작업 진행
    # 사용자가 수동 지정(sub_team_override=True)했으면 PM 스킵.
    stored_sub_team = (task.get("sub_team") or "").lower()
    sub_team_override = bool(task.get("sub_team_override"))
    if sub_team_override and stored_sub_team:
        sub_team = stored_sub_team
        _early_comment(f"🔒 **PM 스킵** — 사용자 수동 지정: `{sub_team}` 분과")
    else:
        sub_team = _run_pm(task, "dev", _early_comment)
        _persist_sub_team(task, sub_team)

    repo = get_repo_config(sub_team)
    repo_host = repo["host"]
    repo_dir = repo["dir"]
    if repo is not DEFAULT_REPO:
        _early_comment(
            f"📦 **레포 라우팅** — `{sub_team}` 분과 → "
            f"`{repo['owner']}/{repo['repo']}` @ `{repo_host}` (`{repo_dir}`)"
        )

    # 이미지 첨부 처리 (task.image_base64가 있으면 해당 레포 호스트로 전송)
    # env 생성 전에 실행되어야 함 (image_path를 env에 주입)
    remote_image_path: Optional[str] = None
    img_b64 = task.get("image_base64")
    if img_b64:
        try:
            import base64 as _b64
            # data:image/png;base64,XXX 형식 또는 raw base64
            if "," in img_b64:
                img_b64 = img_b64.split(",", 1)[1]
            img_bytes = _b64.b64decode(img_b64)
            local_tmp = f"/tmp/task_{short_id}.png"
            with open(local_tmp, "wb") as f:
                f.write(img_bytes)
            remote_image_path = f"C:/tmp/task_{short_id}.png"
            subprocess.run(
                ["ssh", repo_host, "if not exist C:\\tmp mkdir C:\\tmp"],
                capture_output=True, timeout=10, check=False,
            )
            subprocess.run(
                ["scp", "-q", local_tmp, f"{repo_host}:{remote_image_path}"],
                capture_output=True, timeout=30, check=False,
            )
            log.info("[unity_modify] 이미지 첨부됨: %d bytes → %s",
                     len(img_bytes), remote_image_path)
        except Exception:
            log.exception("이미지 처리 실패 (이미지 없이 진행)")
            remote_image_path = None

    # A2 회귀 차단 — task별 고유 브랜치. 기존 단일 공용 `hermes` 브랜치 + 무조건 force-push가
    # 직전 task의 미머지 작업을 덮어써 사라지게 하던 회귀("이전 구현 사라짐/롤백")를 근본 차단.
    # 같은 task의 phase/rework는 같은 브랜치 재사용(축적), 다른 task와는 절대 충돌하지 않음.
    branch_name = f"hermes/{str(task_id)[-8:]}"
    env = ExecutionEnv(
        mode="remote_ssh",
        ssh_host=repo_host,
        cwd=repo_dir,
        timeout_sec=600,
        image_path=remote_image_path,  # 이미지 있으면 모든 에이전트에 전달됨
        task_id=task_id,
        task_title=title,
        team="dev",
        sub_team=sub_team,
    )

    user_feedback = ""
    previous_summary = ""
    if is_rework:
        # 마지막 사용자 코멘트 = 피드백
        for c in reversed(all_comments):
            author = (c.get("author") or "").strip().lower()
            if author not in {"hermes", "hermes-bot", "헤르메스"}:
                user_feedback = c.get("text") or ""
                break
        # 이전 세션 링크
        prev_session = _wr.get_linked_session(task_id) or {}
        previous_summary = prev_session.get("summary") or ""
        log.info("[unity_modify] REWORK MODE — feedback=%s chars, prev_branch=%s",
                 len(user_feedback), prev_session.get("branch"))

    writer = _wr  # 위에서 생성한 writer 재사용

    def _comment(text: str) -> None:
        try:
            writer.add_comment(task_id, text, author="hermes")
        except Exception:
            log.exception("comment post failed")

    log.info("[unity_modify] %s — branch=%s%s",
             title, branch_name, " [REWORK]" if is_rework else "")

    if is_rework:
        _comment(
            f"♻️ **재작업 감지** — 사용자 피드백 반영\n"
            f"> {user_feedback[:500]}\n\n"
            f"이전 작업: `{branch_name}` 이어받기"
        )
    if remote_image_path:
        _comment("🖼️ 첨부 이미지 감지 — 에이전트들이 이미지 참조 가능")

    # ── Step 0: git 브랜치 준비
    # 재작업(rework): 기존 브랜치 체크아웃 후 main을 rebase (충돌 시 cancel)
    # 신규(new):     main fetch/pull 후 새 브랜치 생성
    # 공통 안전 청소:
    #   - git stash push -u: 추적 파일 + 추적 안 된 gitignore 제외 파일 stash
    #     (Unity Library/Temp 같이 .gitignore된 파일은 stash 안 됨 = 안전)
    #   - git reset --hard HEAD: tracked 파일만 HEAD 상태로 복귀
    #   - git clean 제거: Unity가 Library/ 잠그고 있으면 실패 + 재컴파일 유발
    #     Unity 생성물은 어차피 .gitignore라 git 동작에 무관
    import time as _t
    stash_tag = f"hermes-autosave-{int(_t.time())}"
    # 머신 B는 Windows cmd — bash의 `|| true` 미지원. stash를 별도 호출로 분리해
    # 실패해도 무시하고 다음 단계 진행. 본 git 체인은 cmd의 `&&` 만 사용 (성공 시만 다음).
    _comment(f"🔧 `{branch_name}` 브랜치 준비 (main 최신 반영){' [재작업]' if is_rework else ''}")

    # 1단계: stash (실패 무시 — stash할 게 없으면 자연스럽게 exit≠0)
    subprocess.run(
        ["ssh", repo_host,
         f'cd "{repo_dir}" && git stash push -u -m "{stash_tag}"'],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=30, check=False,
    )

    # 2단계: 본 git 체인 — 실패하면 branch_prep 에러
    git_cmds = (
        f'cd "{repo_dir}" && '
        f'git reset --hard HEAD && '
        f'git fetch origin --prune && '
        f'git checkout main && '
        f'git pull --rebase origin main && '
        f'git checkout -B {branch_name} origin/main'
    )

    git_prep = subprocess.run(
        ["ssh", repo_host, git_cmds],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False,
    )
    if git_prep.returncode != 0:
        _prep_out = git_prep.stderr or git_prep.stdout
        _log_and_maybe_learn(
            task_id=task_id, category="branch_prep",
            details=_prep_out,
        )
        # 충돌 시 작성자에게 경과 Slack — 기존 작업을 덮어쓰지 않고 중단(롤백 방지)
        if _categorize_git_error(_prep_out or "") == "merge_conflict":
            _send_slack_failure(
                email=(task.get("created_by_email") or ""),
                title=title,
                reason=f"⚠️ 브랜치 준비 중 main과 충돌(rebase conflict). 기존 작업을 덮어쓰지 않고 중단했습니다 — 수동 확인 필요.\n{(_prep_out or '')[-300:]}",
                category="merge_conflict",
                fallback_assignee=(task.get("assignee") or ""),
            )
        return {
            "success": False,
            "error": _fmt_failure("branch_prep", git_prep.stderr[:300] or git_prep.stdout[-300:]),
            "next_status": "review",
            "failure_category": "branch_prep",
        }

    # 첨부 파일 섹션 (Lead 프롬프트에만 주입 — Lead가 main_coder_task에 필요한 정보를 녹여 전달)
    attach_section = _format_attachments_section(task)

    # 재작업 시 주입할 "이전 시도 로그" — 첫 호출이면 빈 문자열
    rework_log_section = ""
    if is_rework:
        try:
            from agent_session_log import format_rework_context
            rework_log_section = format_rework_context(task_id)
        except Exception:
            log.exception("format_rework_context failed (ignored)")
            rework_log_section = ""

    # 벡터 유사 과거 태스크 — Lead가 경험 기반으로 판단하도록 (Atlas 통일; 구 Qdrant 경로 대체)
    similar_sessions_section = ""
    try:
        from hermes_atlas_retrieval import build_similar_tasks_block
        similar_sessions_section = build_similar_tasks_block(title, description, exclude_id=task_id)
    except Exception:
        log.debug("similar tasks (atlas) lookup skipped", exc_info=True)

    # RAG: 유사 검증 코드(code_base) + 관련 기획 디렉션(design_base) — Lead/Main Coder가 재사용하도록
    code_design_section = ""
    try:
        from hermes_atlas_retrieval import build_code_context, build_design_context
        code_design_section = build_code_context(title, description) + build_design_context(title, description)
    except Exception:
        log.debug("code/design retrieval skipped", exc_info=True)

    # P2-G DNA 1-hop 그라운딩 (HERMES_GROUNDING on). 순수 additive·실패시 '' (비치명).
    if os.environ.get("HERMES_GROUNDING", "off").lower() in {"on", "1", "true", "warn", "block"}:
        try:
            from bf_graph_context import build_graph_context
            code_design_section += build_graph_context(title, description)
        except Exception:
            log.debug("graph grounding skipped", exc_info=True)

    # 가시화 마커 — RAG 가 실제로 발동했는지 task 코멘트로 노출 (효과 측정/디버깅용)
    try:
        _n_code = code_design_section.count("(layer=")
        _n_design = code_design_section.count("(domain=")
        _n_task = similar_sessions_section.count("\n- [")
        if _n_code or _n_design or _n_task:
            _comment(
                f"🔎 **RAG 참조** — 검증코드 {_n_code} · 기획디렉션 {_n_design} · 유사task {_n_task}건 "
                f"(생성 프롬프트에 자동 주입)"
            )
    except Exception:
        log.debug("RAG marker comment skipped", exc_info=True)

    # Phase 3 보상 체계: 같은 분과의 점수≥85 best-practice 1~2건을 Lead 프롬프트에 주입
    best_practices_section = ""
    try:
        from agent_team import format_best_practices_section as _fbp
        best_practices_section = _fbp("dev", sub_team, limit=2)
    except Exception:
        log.debug("best-practice section skipped", exc_info=True)

    # Phase 6 시니어 진화: 누적된 도메인 원칙 주입 (senior_reflection.py)
    principles_section = ""
    try:
        from senior_reflection import load_principles_text
        principles_section = load_principles_text("dev", sub_team)
    except Exception:
        log.debug("principles section skipped", exc_info=True)

    # ── Step 0.5: Translator — 자연어 해석 + 정보 부족 시 생성자에게 Slack DM 질문
    _comment("🔎 **Translator** 자연어 해석 중...")
    translator_prompt = TRANSLATOR_PROMPT_TEMPLATE.format(
        title=title, description=description or "(설명 없음)", comments=comments_text,
    )
    translator_resp = invoke_agent("translator", translator_prompt, env)

    if translator_resp.success:
        tr = translator_resp.structured or {}
        clarity = (tr.get("clarity") or "clear").lower()
        if clarity == "cancel":
            reason = (tr.get("cancel_reason") or "사용자가 작업 중단 요청").strip()
            _comment(f"🛑 **작업 취소 감지** — {reason}\n\n코드 변경 없이 완료 처리합니다.")
            return {
                "success": True,
                "summary": f"사용자 요청으로 취소: {reason[:200]}",
                "next_status": "done",
            }
        if clarity == "rollback":
            reason = (tr.get("rollback_reason") or "사용자 롤백 요청").strip()
            _comment(f"🔄 **롤백 요청 감지** — {reason}")
            return _handle_rollback(task, reason)
        # 재작업 루프에선 질문 반복 금지 — 이미 한 번 물었으니 이번엔 가진 정보로 진행
        if clarity == "needs_input" and is_rework:
            _comment(
                "ℹ️ Translator가 여전히 정보 부족 판정했지만 **재작업 사이클**이므로 "
                "질문 반복 대신 Lead에게 현재 정보로 진행 지시합니다."
            )
            clarity = "clear"
            # enriched_description 없으면 원본 description + 사용자 최근 답변 사용
            if not (tr.get("enriched_description") or "").strip():
                recent_user = ""
                for c in reversed(all_comments):
                    if (c.get("author") or "").lower() not in {"hermes", "hermes-bot", "헤르메스"}:
                        recent_user = (c.get("text") or "")[:500]
                        break
                if recent_user:
                    description = f"{description}\n\n[사용자 추가 지시]\n{recent_user}"
        if clarity == "needs_input":
            questions = [q for q in (tr.get("questions") or []) if isinstance(q, str)][:3]
            preamble = (tr.get("question_preamble") or "").strip()
            current_state = (tr.get("current_state") or "").strip()
            if questions:
                q_md = (
                    f"🤔 **정보 확인 필요** — 진행하려면 아래에 답변 부탁드립니다.\n\n"
                    + (f"{preamble}\n\n" if preamble else "")
                    + (f"_현황: {current_state}_\n\n" if current_state else "")
                    + "\n".join(f"- {q}" for q in questions)
                    + "\n\n_이 코멘트에 답변을 남기시거나, Slack DM에 그대로 답해주세요 — 자동으로 재개됩니다._"
                )
                _comment(q_md)
                try:
                    _send_slack_question(
                        email=(task.get("created_by_email") or "").strip().lower(),
                        task_id=task_id, title=title,
                        preamble=preamble, current_state=current_state,
                        questions=questions,
                        fallback_assignee=(task.get("assignee") or ""),
                    )
                except Exception:
                    log.exception("Slack DM 발송 실패 (무시하고 계속)")
                return {
                    "success": True,  # 에러 아님 — 정상적 pause
                    "summary": "Translator: 사용자 답변 대기 중 (질문 발송됨)",
                    "next_status": "review",
                }

        # clear — enriched_description이 있으면 Lead에 쓸 description 교체
        enriched = (tr.get("enriched_description") or "").strip()
        if enriched:
            description = enriched
            _comment(
                f"✅ **Translator** ({translator_resp.model}, {translator_resp.duration_sec:.1f}s) — "
                f"요구사항 구체화 완료"
            )
        else:
            _comment(f"✅ **Translator** ({translator_resp.model}) — 원본 명확")

        # Translator가 판정한 team이 dev가 아니면 해당 파이프라인으로 전환 (사용자가 override 안 했을 때만)
        translator_team = (tr.get("team") or "dev").lower()
        if not team_override and translator_team in {"art", "chat", "design"}:
            _comment(
                f"🔀 **팀 라우팅** — Translator가 `{translator_team}` 팀으로 분류했습니다. "
                f"해당 파이프라인으로 전환합니다."
            )
            # DB에 team 저장 — 다음 재작업 사이클에서도 일관성 유지
            try:
                from bson import ObjectId as _OID
                from datetime import datetime as _DT
                _c[DB_NAME]["pixelforge_tasks"].update_one(
                    {"_id": _OID(task_id)},
                    {"$set": {"team": translator_team, "updated_at": _DT.utcnow().isoformat()}},
                )
            except Exception:
                log.exception("failed to persist translator team")
            if translator_team == "art":
                return _execute_art_pipeline(task)
            if translator_team == "chat":
                return _execute_chat_only(task)
            if translator_team == "design":
                return _execute_design_pipeline(task)
    else:
        _comment(f"⚠️ Translator 실패: {translator_resp.error} — 원본 그대로 Lead 진행")

    # PM은 이미 함수 초입에서 호출됨 — sub_team 결정 + 레포 라우팅 완료
    # Phase 2: sub_team-aware role resolution
    # is_general이면 기존 7-단계 파이프라인(main_coder + sub_coder×N + validator + reviewer + optimizer)
    # 분과(ui/server/ingame/outgame)면 단순화: dev_<sub>_lead → dev_<sub>_coder → dev_<sub>_reviewer + 공용 validator
    is_general = (sub_team == "general")
    from agent_team import resolve_role as _resolve_role
    lead_role           = _resolve_role("dev", sub_team, "lead")
    main_coder_role     = "main_coder" if is_general else _resolve_role("dev", sub_team, "coder")
    sub_coder_role      = "sub_coder" if is_general else None  # 분과는 병렬 sub_coder 안 씀
    validator_role      = _resolve_role("dev", sub_team, "validator")  # → 거의 'validator' 폴백
    optimizer_role      = _resolve_role("dev", sub_team, "optimizer")  # → 'optimizer' 폴백
    opt_reviewer_role   = _resolve_role("dev", sub_team, "optimization_reviewer")
    reviewer_role       = _resolve_role("dev", sub_team, "reviewer")
    if not is_general:
        _comment(
            f"🧭 **분과 라우팅** — `{sub_team}` 파이프라인:\n"
            f"  Lead=`{lead_role}` · Coder=`{main_coder_role}` · Reviewer=`{reviewer_role}`"
        )

    # ── Step 1: Lead — 계획 수립 (재작업 시 피드백 포함)
    if is_rework:
        _comment("🧠 **Lead Agent** 피드백 반영 계획 수립 중...")
        lead_prompt = (
            f"{LEAD_PROMPT_TEMPLATE.format(title=title, description=description, comments=comments_text)}\n\n"
            f"## ⚠️ IMPORTANT: This is a REWORK\n"
            f"Previous work summary:\n{previous_summary[:800]}\n\n"
            f"User feedback (must address):\n> {user_feedback[:1000]}\n\n"
            f"Your plan MUST explicitly address the user's feedback. "
            f"Do not repeat previous mistakes. Identify what specifically to change vs. previous work."
            f"{rework_log_section}"
            f"{code_design_section}"
            f"{similar_sessions_section}"
            f"{best_practices_section}"
            f"{principles_section}"
            f"{attach_section}"
        )
    else:
        _comment("🧠 **Lead Agent** 태스크 분석 중...")
        lead_prompt = (
            LEAD_PROMPT_TEMPLATE.format(
                title=title, description=description, comments=comments_text,
            )
            + code_design_section
            + similar_sessions_section
            + best_practices_section
            + principles_section
            + attach_section
        )

    lead_resp = invoke_agent(lead_role, lead_prompt, env)
    if not lead_resp.success:
        _comment(f"❌ Lead 실패: {lead_resp.error}")
        return {"success": False, "error": lead_resp.error, "next_status": "review"}

    plan = lead_resp.structured or {}
    plan_summary = plan.get("summary") or lead_resp.output[:500]

    # ── Phase 분할 감지 — Lead가 phase_plan 반환했고 task에 아직 plan 없으면 저장 + 첫 phase 실행
    existing_phase_plan = task.get("phase_plan")
    proposed_plan = plan.get("phase_plan")
    if proposed_plan and not existing_phase_plan and isinstance(proposed_plan, list) and len(proposed_plan) > 1:
        try:
            from bson import ObjectId as _OID
            from datetime import datetime as _DT
            normalized = []
            for i, p in enumerate(proposed_plan, 1):
                if not isinstance(p, dict):
                    continue
                normalized.append({
                    "n": int(p.get("n") or i),
                    "name": str(p.get("name") or f"phase {i}")[:200],
                    "files": list(p.get("files") or [])[:30],
                    "estimated_lines": int(p.get("estimated_lines") or 0),
                    "rationale": str(p.get("rationale") or "")[:500],
                    "status": "pending",
                })
            _c[DB_NAME]["pixelforge_tasks"].update_one(
                {"_id": _OID(task_id)},
                {"$set": {
                    "phase_plan": normalized,
                    "current_phase": 1,
                    "phase_log": [],
                    "updated_at": _DT.utcnow().isoformat(),
                }},
            )
            _comment(
                f"🪜 **큰 작업 감지 — {len(normalized)} phase로 분할**\n"
                + "\n".join(f"  {p['n']}. **{p['name']}** ({p['estimated_lines']}줄, {len(p['files'])}파일)" for p in normalized)
                + f"\n\n→ phase 1부터 자동 진행 (각 phase 완료마다 자동으로 다음 phase 트리거)"
            )
            # 첫 phase는 다음 사이클(catch-up)에서 처리되도록 status=todo로 전환
            return {
                "success": True,
                "summary": f"phase 분할 ({len(normalized)}개) — 다음 사이클부터 phase 1 자동 진행",
                "next_status": "todo",
            }
        except Exception:
            log.exception("phase_plan 저장 실패 — 일반 흐름으로 진행")

    _comment(
        f"✅ **Lead Agent** ({lead_resp.model}, {lead_resp.duration_sec:.1f}s)\n"
        f"```\n{plan_summary}\n```"
    )

    main_task = plan.get("main_coder_task") or description
    sub_tasks = plan.get("sub_tasks") or []

    # ── Step 2: Main Coder — 핵심 변경 (환각 감지 + 재시도 포함)
    _comment("👨‍💻 **Main Coder** (Opus 4.7) 핵심 구현 중...")
    main_prompt_base = MAIN_CODER_PROMPT_TEMPLATE.format(
        lead_plan=plan_summary, main_task=main_task,
    ) + code_design_section  # RAG: 유사 검증 코드 + 관련 기획 디렉션 직접 주입

    main_resp = None
    main_files = []
    actual_changes = False
    MAX_MAIN_ATTEMPTS = 3  # 1 + 최대 2회 재시도

    for attempt in range(1, MAX_MAIN_ATTEMPTS + 1):
        current_prompt = main_prompt_base
        if attempt > 1:
            # 재시도: 이전 실패 맥락 추가
            current_prompt = (
                f"⚠️ PREVIOUS ATTEMPT FAILED VERIFICATION\n"
                f"You previously claimed to modify files but `git status` showed no actual changes.\n"
                f"This is attempt {attempt}/{MAX_MAIN_ATTEMPTS}.\n\n"
                f"MUST DO THIS TIME:\n"
                f"- Use the Edit or Write tool to ACTUALLY modify files (not just describe)\n"
                f"- Verify each Edit call succeeds (no error)\n"
                f"- If truly no file changes are needed, respond with:\n"
                f"  ```json\n"
                f"  {{\"files_modified\": [], \"summary\": \"explanation why no changes needed\"}}\n"
                f"  ```\n\n"
                f"---\n\n"
                f"{main_prompt_base}"
            )

        if _should_abort(task_id):
            return _abort_result("구현(Main Coder)")
        main_resp = invoke_agent(main_coder_role, current_prompt, env)
        if not main_resp.success:
            _comment(f"❌ Main Coder 시도 {attempt} 실패: {main_resp.error}")
            if attempt == MAX_MAIN_ATTEMPTS:
                return {"success": False, "error": main_resp.error, "next_status": "review"}
            continue

        main_files = (main_resp.structured or {}).get("files_modified", [])
        claimed_count = len(main_files)

        # 실재 검증: git status로 실제 변경 확인
        verify = subprocess.run(
            ["ssh", env.ssh_host,
             f'cd "{env.cwd}" && git status --porcelain'],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, check=False,
        )
        git_status_lines = [l for l in (verify.stdout or "").splitlines() if l.strip()]
        actual_changes = len(git_status_lines) > 0

        _comment(
            f"{'✅' if actual_changes or claimed_count == 0 else '⚠️'} "
            f"**Main Coder** ({main_resp.model}, {main_resp.duration_sec:.1f}s, attempt {attempt}/{MAX_MAIN_ATTEMPTS})\n"
            f"주장: {claimed_count}개 파일 / 실재 변경: {len(git_status_lines)}개"
        )

        # 케이스 분석
        if claimed_count == 0 and not actual_changes:
            # 에이전트가 "할 일 없음"이라 했고 실제 변경도 없음 — 일관성 OK
            _comment("ℹ️ Main Coder가 '변경 불필요' 판정 (일관성 있음)")
            break
        elif claimed_count > 0 and actual_changes:
            # 주장과 실재 일치 — 성공
            _comment(f"수정 파일: {', '.join(main_files[:5])}")
            break
        elif claimed_count > 0 and not actual_changes:
            # 환각: 주장했지만 실재 없음
            _log_and_maybe_learn(
                task_id=task_id, category="main_coder_hallucination",
                details=f"Attempt {attempt}: claimed {claimed_count} files but git clean",
                agent_role=main_coder_role,
            )
            if attempt < MAX_MAIN_ATTEMPTS:
                _comment(f"🔄 환각 감지 — 강화 프롬프트로 재시도 ({attempt+1}/{MAX_MAIN_ATTEMPTS})")
                continue
            else:
                _comment("🚨 Main Coder 환각 3회 반복 — 사람 개입 필요")
                return {
                    "success": False,
                    "error": "Main Coder claimed modifications but git status clean after 3 attempts",
                    "next_status": "review",
                    "failure_category": "main_coder_hallucination",
                }
        elif claimed_count == 0 and actual_changes:
            # 에이전트가 "할 일 없음"이라 했는데 실제로 변경이 있음 (이상)
            _comment(f"⚠️ 에이전트 '변경 없음' 주장했지만 git에 변경 있음 ({len(git_status_lines)}개)")
            # 이 경우 유용한 변경일 수 있으니 그대로 진행
            break

    # ── Step 3: Sub Coders 병렬 (OpenAI 키 도착 시 GPT-4o로 전환됨)
    sub_responses: list = []
    # 분과(non-general)는 단일 coder 모델 — 병렬 sub_coder 스킵
    if sub_tasks and sub_coder_role:
        _comment(f"🔀 **Sub Coder ×{min(len(sub_tasks), 2)}** 병렬 실행 중...")
        sub_prompts = [
            SUB_CODER_PROMPT_TEMPLATE.format(lead_plan=plan_summary, sub_task=st)
            for st in sub_tasks[:2]
        ]
        sub_responses = run_parallel_agents(
            [(sub_coder_role, p) for p in sub_prompts], env, max_workers=2,
        )
        for i, r in enumerate(sub_responses, 1):
            if r.success:
                files = (r.structured or {}).get("files_modified", [])
                _comment(
                    f"✅ Sub Coder #{i} ({r.model}, {r.duration_sec:.1f}s) "
                    f"— {len(files)}개 파일"
                )
            else:
                _comment(f"⚠️ Sub Coder #{i} 실패: {r.error}")

    # ── Step 4: diff 체크
    diff_check = subprocess.run(
        ["ssh", repo_host,
         f'cd "{repo_dir}" && '
         f'git diff --stat && echo ---END--- && git diff --name-only'],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
    )
    if "---END---" not in diff_check.stdout:
        _comment("⚠️ git diff 조회 실패")
        return {"success": False, "error": "diff check failed", "next_status": "review"}

    diff_stat = diff_check.stdout.split("---END---")[0].strip()
    changed_files = diff_check.stdout.split("---END---")[1].strip().split("\n")
    changed_files = [f for f in changed_files if f]

    # G1↔G2 연결: 이 작업이 실제로 수정한 파일을 노드 저널에 기록 → 라이브 뷰에서 코드그래프로 점프
    try:
        from hermes_node_journal import record_files
        record_files(task_id, changed_files)
    except Exception:
        pass

    # 큰 수정 / 환각 의심 탐지 → 작성자 Slack (배포 전 사람이 보도록)
    # 결정론으로 못 막는 영역(시맨틱·동적디스패치)은 '의심 신호'로 알림 처리.
    try:
        import re as _re
        _ins = int((_re.search(r"(\d+)\s+insertion", diff_stat or "") or [0, 0])[1]) if _re.search(r"(\d+)\s+insertion", diff_stat or "") else 0
        _del = int((_re.search(r"(\d+)\s+deletion", diff_stat or "") or [0, 0])[1]) if _re.search(r"(\d+)\s+deletion", diff_stat or "") else 0
        _signals = []
        if len(changed_files) >= 6 or (_ins + _del) >= 300:
            _signals.append(f"큰 수정 ({len(changed_files)}파일, +{_ins}/-{_del}줄)")
        if _del > 50 and _del > _ins * 2:
            _signals.append(f"대량 삭제 의심 (-{_del} vs +{_ins}) — 기능 삭제/롤백 가능성")
        _claimed = (main_resp.structured or {}).get("files_modified") if (main_resp and main_resp.structured) else None
        if isinstance(_claimed, list) and _claimed:
            _cs = {os.path.basename(str(f)) for f in _claimed}
            _as = {os.path.basename(f) for f in changed_files}
            if _cs and not (_cs & _as):
                _signals.append("주장-실제 불일치 (보고한 수정 파일이 실제 변경과 다름) — 환각 의심")
        if _signals:
            _send_slack_failure(
                email=(task.get("created_by_email") or ""),
                title=title,
                reason="⚠️ 큰 수정/환각 의심 — 배포 전 검토 권장:\n- " + "\n- ".join(_signals)
                       + f"\n변경: {', '.join(os.path.basename(f) for f in changed_files[:10])}",
                category="large_or_suspect",
                fallback_assignee=(task.get("assignee") or ""),
            )
            _comment("⚠️ 큰 수정/환각 의심 신호 → 작성자에게 Slack: " + "; ".join(_signals))
    except Exception:
        log.debug("suspicion detect skipped (non-fatal)", exc_info=True)

    if not changed_files:
        _log_and_maybe_learn(
            task_id=task_id, category="no_changes_made",
            details=f"Lead: {len(lead_resp.output)} chars; Main: {len(main_resp.output)} chars",
            agent_role=main_coder_role,
        )
        _comment("ℹ️ 변경된 파일 없음 — 에이전트들이 코드 수정을 수행하지 않았습니다")
        _send_slack_failure(
            email=(task.get("created_by_email") or ""),
            title=title,
            reason="에이전트들이 실제 코드를 수정하지 못했습니다. 요구사항을 좀 더 구체적으로 지시해주시면 다시 시도 가능.",
            category="no_changes_made",
            fallback_assignee=(task.get("assignee") or ""),
        )
        return {
            "success": False,
            "error": "No file changes made by agents",
            "next_status": "review",
            "failure_category": "no_changes_made",
        }

    _comment(f"📝 **변경 요약**\n```\n{diff_stat[:800]}\n```")

    # ── Step 5: Validator — 검증 게이트 (MCP 라이브 Unity 상태 주입)
    _comment("🔍 **Validator** 검증 중...")

    # MCP에서 실제 컴파일 에러 + 콘솔 에러 가져오기 (옵션, 실패 시 silent skip)
    mcp_findings_block = ""
    mcp_compile_errors: list[dict] = []
    mcp_console_errors: list[dict] = []
    mcp_ok = False  # MCP 컴파일 조회 성공 여부 (P0a 게이트: 실패=indeterminate, clean과 구분)
    try:
        from mcp_client import McpClient, McpError
        _mcp = McpClient(timeout=10.0)
        try:
            comp = _mcp.call("inspect.compilation.status")
            mcp_ok = True
            mcp_compile_errors = [m for m in comp.get("messages", []) if m.get("is_error")]
            console = _mcp.call("inspect.console.read_errors", {"limit": 30})
            mcp_console_errors = console.get("errors", [])
        except McpError as e:
            log.warning("MCP query failed (validator will use diff only): %s", e)
    except Exception:
        log.exception("MCP client init failed (validator skip)")

    if mcp_compile_errors or mcp_console_errors:
        lines = ["", "## 🔴 Live Unity Editor State (MCP 직접 조회)"]
        if mcp_compile_errors:
            lines.append(f"\n**컴파일 에러 {len(mcp_compile_errors)}건:**")
            for e in mcp_compile_errors[:10]:
                file = e.get("file", "?").split("/")[-1] if e.get("file") else "?"
                lines.append(f"- {file}:{e.get('line','?')} — {(e.get('message') or '')[:200]}")
        if mcp_console_errors:
            lines.append(f"\n**런타임 콘솔 에러 {len(mcp_console_errors)}건 (최근):**")
            for e in mcp_console_errors[:5]:
                lines.append(f"- [{e.get('type','?')}] {(e.get('message') or '')[:200]}")
        lines.append("\n**중요**: 위 에러들은 추정이 아닌 Unity Editor의 실제 상태입니다. issues에 반드시 포함하고 passed=false 처리하세요.")
        mcp_findings_block = "\n".join(lines)

    validator_resp = invoke_agent(
        validator_role,
        VALIDATOR_PROMPT_TEMPLATE.format(
            changes_summary=f"Diff stats:\n{diff_stat}\n\nFiles: {', '.join(changed_files)}{mcp_findings_block}"
        ),
        env,
    )
    validator_verdict = validator_resp.structured or {"passed": False, "issues": ["no structured response"]}
    passed = validator_verdict.get("passed", False)

    # MCP가 컴파일 에러 보고했는데 Validator가 passed=true 반환했으면 강제 override
    if mcp_compile_errors and passed:
        log.warning("Validator returned passed=true but MCP found %d compile errors — overriding", len(mcp_compile_errors))
        validator_verdict["passed"] = False
        existing_issues = list(validator_verdict.get("issues") or [])
        for e in mcp_compile_errors[:5]:
            file = (e.get("file") or "?").split("/")[-1]
            existing_issues.append(f"[MCP] Compile error {file}:{e.get('line','?')} — {(e.get('message') or '')[:120]}")
        validator_verdict["issues"] = existing_issues
        passed = False

    _comment(
        f"{'✅' if passed else '⚠️'} **Validator** ({validator_resp.model})"
        + (f" + MCP({len(mcp_compile_errors)} compile errors)" if mcp_compile_errors else "")
        + f"\nPass: {passed}\n"
        f"Issues: {', '.join(validator_verdict.get('issues', [])[:3])}"
    )

    # Validator 이슈가 있어도 차단 X — 경고로 수집해 PR description에 포함
    warnings: list[str] = []
    if not passed:
        _log_and_maybe_learn(
            task_id=task_id, category="validator_warning",
            details=str(validator_verdict.get("issues", [])),
            agent_role=validator_role,
        )
        issues_text = "\n".join(f"- {i}" for i in validator_verdict.get("issues", [])[:5])
        _comment(
            f"⚠️ **Validator 경고** (차단 X — PR에 기록)\n{issues_text}"
        )
        warnings.append(f"**Validator:**\n{issues_text}")

    # ── Step 5.5: Optimizer + Opt Reviewer (조건부) — #optimize 태그/키워드일 때만
    text_blob = f"{title}\n{description}".lower()
    optimize_tag = bool(re.search(r"(?:\[|#)(optimize|최적화|performance|성능)\b|(?:\[|#)(optimize|최적화|performance|성능)(?:\]|$)", text_blob))
    optimize_kw = any(kw in text_blob for kw in ["최적화", "optimize", "optimization", "성능 개선", "performance"])
    if optimize_tag or optimize_kw:
        _comment("⚡ **Optimizer** (Claude Opus) 성능 최적화 패스 중...")
        optimizer_prompt = (
            f"Main Coder가 방금 수정한 아래 파일들의 성능 안티패턴을 제거하세요.\n"
            f"변경 파일: {', '.join(changed_files)}\n\n"
            f"## 지침\n"
            f"- Unity 성능 안티패턴 제거: Update/FixedUpdate 안의 GetComponent·FindObjectOfType,\n"
            f"  매 프레임 문자열 concat/new, boxing, 불필요한 Instantiate·GC alloc 루프,\n"
            f"  LINQ 남용, List.Contains in hot path, foreach in hot path\n"
            f"- **기능/동작 변경 금지** — 외부에서 본 행동이 달라지면 안 됨\n"
            f"- Edit/Write 툴로 실제 파일 수정. 수정 없으면 (이미 최적화된 상태면) files_modified=[] 반환\n\n"
            f"## 출력 JSON\n"
            f'```json\n{{"files_modified": [...], "optimizations": ["설명1", ...], "summary": "..."}}\n```'
        )
        opt_resp = invoke_agent(optimizer_role, optimizer_prompt, env)

        if not opt_resp.success:
            _comment(f"⚠️ Optimizer 실패: {opt_resp.error} — 최적화 건너뛰고 Reviewer로 진행")
        else:
            opt_struct = opt_resp.structured or {}
            opt_summary = opt_struct.get("summary") or opt_resp.output[:300]
            _comment(f"⚡ **Optimizer** ({opt_resp.model}, {opt_resp.duration_sec:.1f}s)\n```\n{opt_summary[:500]}\n```")

            # Optimizer가 실제 파일을 수정했는지 확인
            verify_opt = subprocess.run(
                ["ssh", env.ssh_host, f'cd "{env.cwd}" && git status --porcelain'],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=30, check=False,
            )
            opt_changed_files = [
                line[3:].strip()
                for line in (verify_opt.stdout or "").splitlines()
                if line.strip() and line[3:].strip() not in changed_files
            ]

            if not opt_changed_files:
                _comment("ℹ️ Optimizer가 추가 변경을 수행하지 않음 (이미 최적화 완료 또는 대상 없음)")
            else:
                # Opt Reviewer — 최적화가 정확성 깨지 않았는지 검증
                _comment(f"🔬 **Optimization Reviewer** 최적화 검증 중... ({len(opt_changed_files)}개 추가 변경)")
                opt_rev_prompt = (
                    f"Optimizer가 방금 {', '.join(opt_changed_files)} 파일을 추가로 수정했습니다.\n"
                    f"`git diff HEAD~1 HEAD -- <파일>` 또는 `git diff -- <파일>`로 변경사항을 확인하고 판정하세요.\n\n"
                    f"## 판정 기준\n"
                    f"1. **정확성**: 기능/로직/사이드이펙트가 이전과 동일한가? (동일하지 않으면 reject)\n"
                    f"2. **실제 개선**: GC alloc 감소, 연산 횟수 감소, 메모리 사용 감소 중 하나라도 확인되는가?\n"
                    f"3. **안전성**: 레이스 컨디션/Null 참조 신규 도입되지 않았는가?\n\n"
                    f"## 출력 JSON\n"
                    f'```json\n{{"passed": true/false, "concerns": ["..."], "actual_wins": ["..."]}}\n```'
                )
                opt_rev_resp = invoke_agent(opt_reviewer_role, opt_rev_prompt, env)
                opt_verdict = opt_rev_resp.structured or {"passed": False, "concerns": ["no structured response"]}
                passed_opt = bool(opt_verdict.get("passed"))
                _comment(
                    f"{'✅' if passed_opt else '⚠️'} **Opt Reviewer** ({opt_rev_resp.model})\n"
                    f"Pass: {passed_opt}\n"
                    f"Wins: {', '.join(opt_verdict.get('actual_wins', [])[:3]) or '(none)'}\n"
                    f"Concerns: {', '.join(opt_verdict.get('concerns', [])[:3]) or '(none)'}"
                )
                if not passed_opt:
                    _log_and_maybe_learn(
                        task_id=task_id, category="optimizer_rejected",
                        details=str(opt_verdict.get("concerns", [])),
                        agent_role=optimizer_role,
                    )
                    _comment("⚠️ Opt Reviewer 거부 — 최적화 변경이 남아있습니다. 사람 검토 필요 (status=review)")
                    return {
                        "success": False,
                        "error": "Optimization reviewer rejected",
                        "next_status": "review",
                        "failure_category": "optimizer_rejected",
                    }
                # 통과 — changed_files 갱신하고 diff_stat 재계산
                changed_files.extend(opt_changed_files)
                diff_refresh = subprocess.run(
                    ["ssh", env.ssh_host, f'cd "{env.cwd}" && git diff --stat HEAD'],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=30, check=False,
                )
                if diff_refresh.returncode == 0 and diff_refresh.stdout:
                    diff_stat = diff_refresh.stdout[:2000]

    # ── Step 6: Reviewer — 최종 품질 게이트
    _comment("👀 **Reviewer** (Claude Max Opus) 최종 리뷰 중...")
    _reviewer_prompt = REVIEWER_PROMPT_TEMPLATE.format(
        changes_summary=f"Files: {', '.join(changed_files)}\n\nDiff stat:\n{diff_stat}",
        validator_verdict=json.dumps(validator_verdict, indent=2, ensure_ascii=False),
    )
    try:
        from reviewer_retrieval import build_retrieval_block as _retr_block
        _retr = _retr_block(title, description, task_id)
        if _retr:
            _reviewer_prompt += "\n\n" + _retr
    except Exception:
        log.exception("reviewer_retrieval injection failed (non-fatal)")
    reviewer_resp = invoke_agent(reviewer_role, _reviewer_prompt, env)
    # Phase 0 배포 차단 게이트 — Reviewer 거부 시 자동 머지 차단(advisory→blocking).
    # HERMES_MERGE_GATE=block(기본)|warn. 회귀/환각/외과규칙 위반 Reviewer 판정을 실효화.
    _merge_blocked = False
    _block_reason = ""
    _MERGE_GATE = os.environ.get("HERMES_MERGE_GATE", "block").lower()
    reviewer_verdict = reviewer_resp.structured or {"verdict": "REQUEST_CHANGES"}
    _q_score = reviewer_verdict.get("quality_score")
    try:
        _q_score = int(_q_score) if _q_score is not None else None
    except (TypeError, ValueError):
        _q_score = None
    _comment(
        f"{'✅ APPROVED' if reviewer_verdict.get('verdict') == 'APPROVED' else '🔄 REQUEST_CHANGES'} "
        f"**Reviewer** ({reviewer_resp.model})"
        + (f" · 품질 점수 **{_q_score}/100**" if _q_score is not None else "")
    )

    # 보상 체계 — 품질 점수를 hermes_team_scores에 누적 (Phase 2: 데이터 적재만)
    if _q_score is not None:
        _record_quality_score(
            task_id=task_id, team="dev", sub_team=sub_team,
            role=reviewer_role, score=_q_score,
            verdict=str(reviewer_verdict.get("verdict") or ""),
            summary=str((reviewer_verdict.get("strengths") or [""])[0])[:500],
            # 진실성 게이트(C): 실제 변경 파일 + diff를 근거로 전달 (수용 시 grounded reflect)
            files_changed=changed_files, diff_summary=diff_stat,
            title=title, description=description, coder_role=main_coder_role,
        )

    if reviewer_verdict.get("verdict") != "APPROVED":
        # 진실성 게이트(A): 리뷰어가 거부한 건 'coder가 거부당할 결과물을 냈다'는 실패다.
        # 이전엔 reviewer 역할에 패치를 학습시켜 리뷰어가 '덜 거부'하도록 길들여졌음(귀속 버그).
        # → coder 역할에 귀속해 coder가 더 나은 코드를 내도록 학습.
        _log_and_maybe_learn(
            task_id=task_id, category="reviewer_rejected",
            details=str(reviewer_verdict.get("required_changes", [])),
            agent_role=main_coder_role,
        )
        required = "\n".join(f"- {c}" for c in reviewer_verdict.get("required_changes", [])[:5])
        warnings.append(f"**Reviewer:**\n{required}")
        reviewer_skipped_request = True
        if _MERGE_GATE == "block":
            _merge_blocked = True
            _block_reason = "Reviewer REQUEST_CHANGES"
            _comment(f"⛔ **Reviewer 거부 → 자동배포 차단** (수동 검토 필요)\n{required}")
        else:
            _comment(f"⚠️ **Reviewer 경고** (차단 X — PR에 기록)\n{required}")
    else:
        reviewer_skipped_request = False
    # 게이트 결정 기록(측정) + merge_state SSOT 영속화 (비차단)
    _record_gate_event(
        task_id=task_id, gate="reviewer",
        result=("pass" if reviewer_verdict.get("verdict") == "APPROVED" else ("block" if _merge_blocked else "warn")),
        reason=_block_reason,
        merge_state=("blocked" if _merge_blocked else None),
    )
    # ── Step 6.5: (선택) Unity 컴파일 체크 — HERMES_VERIFY_COMPILE=true 그리고 unity 레포일 때만
    if (os.environ.get("HERMES_VERIFY_COMPILE", "").lower() in {"1", "true", "yes"}
            and repo.get("type") == "unity"):
        _comment("🏗️ Unity 컴파일 체크 중 (최대 3분)...")
        unity_editor = os.environ.get(
            "MACHINE_B_UNITY_EXE",
            "C:/Program Files/Unity/Hub/Editor/6000.2.7f2/Editor/Unity.exe",
        )
        unity_cmd = (
            f'"{unity_editor}" -batchmode -quit -nographics '
            f'-projectPath "{repo_dir}/BalloonFlow" '
            f'-logFile -'
        )
        compile_result = subprocess.run(
            ["ssh", repo_host, unity_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240, check=False,
        )
        log_tail = (compile_result.stdout or "") + "\n" + (compile_result.stderr or "")
        has_error = bool(re.search(r"error CS\d+|Compilation failed|Scripts have compiler errors", log_tail))
        if has_error:
            # 관련 에러 라인 뽑기
            err_lines = [
                ln for ln in log_tail.splitlines()
                if re.search(r"error CS\d+|Compilation failed", ln)
            ][:5]
            err_text = "\n".join(err_lines) or "(상세 로그 파싱 실패)"
            _comment(f"❌ **Unity 컴파일 에러** — push 차단\n```\n{err_text}\n```")
            _log_and_maybe_learn(
                task_id=task_id, category="compile_error",
                details=err_text,
            )
            _send_slack_failure(
                email=(task.get("created_by_email") or ""),
                title=title,
                reason=f"Unity 컴파일 에러:\n{err_text[:300]}",
                category="compile_error",
                fallback_assignee=(task.get("assignee") or ""),
            )
            return {
                "success": False,
                "error": "Unity compile errors",
                "next_status": "review",
                "failure_category": "compile_error",
            }
        _comment("✅ Unity 컴파일 통과")

    # ── 진실성 게이트(E): 컴파일 미검증 APPROVED는 자동 push 보류 (거짓 '완료' 방지)
    # HERMES_REQUIRE_COMPILE=block(기본)|warn|off. Unity MCP로 컴파일을 확인했고 에러 없을 때만
    # '검증되게 작동함'으로 본다. MCP 미응답(mcp_ok=False)이면 증명 불가 → block 모드에선 review로
    # 보류(사람이 컴파일/플레이 확인). MCP가 자주 다운돼 백로그가 쌓이면 warn으로 완화 가능.
    _REQ_COMPILE = os.environ.get("HERMES_REQUIRE_COMPILE", "block").lower()
    _compile_verified = bool(mcp_ok and not mcp_compile_errors)
    if (not _merge_blocked and not _compile_verified
            and reviewer_verdict.get("verdict") == "APPROVED" and _REQ_COMPILE != "off"):
        _record_gate_event(task_id=task_id, gate="compile_required",
                           result=("block" if _REQ_COMPILE == "block" else "warn"),
                           reason="compile unverified (MCP unavailable) on APPROVED")
        if _REQ_COMPILE == "block":
            _comment("⚠️ **컴파일 검증 불가**(Unity MCP 미응답) — Reviewer APPROVED이나 "
                     "자동배포 보류. 수동 컴파일/플레이 확인 후 done 처리 필요. "
                     "(해제: HERMES_REQUIRE_COMPILE=warn)")
            return {
                "success": True,
                "summary": "Reviewer APPROVED이나 컴파일 미검증 — 수동 확인 위해 review 보류",
                "next_status": "review",
            }
        _comment("⚠️ 컴파일 검증 불가(MCP 미응답) — warn 모드라 배포는 진행하되 수동 확인 권장.")

    # ── Step 7: commit + push (non-fast-forward 시 자동 rebase 재시도)
    # A7 취소 체크포인트: 되돌릴 수 없는 commit/push 직전 — 중단 시 여기서 멈춤(push 방지)
    if _should_abort(task_id):
        return _abort_result("Git commit/push")
    _comment("📦 Git commit + push 중...")
    commit_msg = title.replace('"', "'")[:72]

    # commit (secret-leak hardened: gitignore 보장 + 시크릿 경로 unstage + 내용 스캔)
    # Why: 과거 PR #92에서 git add -A 가 .env 토큰을 그대로 push/merge. 1차=대상 repo .gitignore,
    #      2차=시크릿 경로 강제 unstage, 3차=staged 추가라인 시그니처 스캔 → 적중 시 commit/push 차단.
    _gi_patterns = ".env .env.* *.pem *.key id_rsa id_rsa.* run_mcp.cmd mcp.log mcp.err"
    _reset_specs = "'*.env' '.env' '.env.*' '*.pem' '*.key' 'id_rsa' 'id_rsa.*' 'run_mcp.cmd' 'mcp.log' 'mcp.err'"
    _leak_re = ('BEGIN ([A-Z ]+ )?PRIVATE KEY|xox[baprs]-[0-9A-Za-z-]{10,}|'
                'AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{36,}')
    commit_cmd = (
        'cd "' + repo_dir + '" || exit 9\n'
        'for p in ' + _gi_patterns + '; do grep -qxF "$p" .gitignore 2>/dev/null || echo "$p" >> .gitignore; done\n'
        'git add -A\n'
        'git reset -q -- ' + _reset_specs + ' 2>/dev/null\n'
        'LEAK=$(git diff --cached -U0 | grep -E "^\\+" | grep -Ein \'' + _leak_re + '\' | head -5)\n'
        'if [ -n "$LEAK" ]; then echo HERMES_SECRET_LEAK_DETECTED; echo "$LEAK"; git reset -q; exit 42; fi\n'
        'git commit -m "hermes: ' + commit_msg + '" -m "Task: ' + str(task_id) + '" 2>&1\n'
    )
    commit_result = subprocess.run(
        ["ssh", repo_host, commit_cmd],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
    )
    if commit_result.returncode == 42 or "HERMES_SECRET_LEAK_DETECTED" in (commit_result.stdout or ""):
        _leak_detail = (commit_result.stdout or "")[-400:]
        _comment("🔒 시크릿 의심 패턴 감지 — commit/push 차단 (Error Fix Protocol 필요)\n"
                 "```\n" + _leak_detail + "\n```")
        return {
            "success": False,
            "error": _fmt_failure("secret_leak_blocked", _leak_detail),
            "next_status": "review",
            "failure_category": "secret_leak_blocked",
        }
    if commit_result.returncode != 0:
        _comment(f"❌ git commit 실패:\n```\n{commit_result.stdout[-400:]}\n```")
        return {
            "success": False,
            "error": _fmt_failure("commit_failed", commit_result.stdout[-400:]),
            "next_status": "review",
            "failure_category": "commit_failed",
        }

    # push (최대 3회 재시도: non-fast-forward → pull --rebase → 재 push)
    # 재작업 시 force-with-lease로 이전 브랜치 강제 업데이트 (안전한 force)
    push_success = False
    push_output = ""
    # A2: 신규 task는 고유 브랜치 신규 생성이라 force 불필요(plain push).
    # rework(자기 PR 갱신)만 안전한 --force-with-lease — 다른 곳에서 push됐으면 거부(작업 보호).
    # 무조건 --force(직전 작업 덮어쓰는 회귀 원인)는 폐지.
    force_flag = " --force-with-lease" if is_rework else ""
    for attempt in range(1, 4):
        push_cmd = (
            f'cd "{repo_dir}" && '
            f'git push -u origin {branch_name}{force_flag} 2>&1'
        )
        push = subprocess.run(
            ["ssh", repo_host, push_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False,
        )
        push_output = push.stdout
        if push.returncode == 0:
            push_success = True
            break

        # 실패 카테고리 분석
        category = _categorize_git_error(push_output)
        _comment(f"⚠️ Push 시도 {attempt}/3 실패 — {category}")

        if category == "non_fast_forward" and attempt < 3:
            # rebase 재시도
            rebase_cmd = (
                f'cd "{repo_dir}" && '
                f'git pull --rebase origin {branch_name} 2>&1'
            )
            rebase = subprocess.run(
                ["ssh", repo_host, rebase_cmd],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
            )
            _comment(f"🔄 rebase 시도 → {_categorize_git_error(rebase.stdout)}")
            continue
        elif category == "auth_failure":
            # gh auth setup-git으로 자동 복구 시도 (1회만)
            if attempt == 1:
                _comment("🔑 git credential helper 재설정 중...")
                subprocess.run(
                    ["ssh", repo_host, "gh auth setup-git"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
                )
                continue
            break
        else:
            # 재시도 불가 실패
            break

    if not push_success:
        failure_cat = _categorize_git_error(push_output)
        _log_and_maybe_learn(
            task_id=task_id, category=failure_cat,
            details=push_output,
        )
        _comment(f"❌ git push 최종 실패:\n```\n{push_output[-400:]}\n```")
        return {
            "success": False,
            "error": _fmt_failure("push_failed", push_output[-400:]),
            "next_status": "review",
            "failure_category": failure_cat,
        }

    # ── Step 8: PR 생성
    pr_body = (
        f"## Automated by Hermes\n\n"
        f"**Task ID**: {task_id}\n"
        f"**Branch**: {branch_name}\n\n"
        f"### Changes\n{diff_stat[:1500]}\n\n"
        f"### Lead Plan\n{plan_summary[:500]}\n\n"
        f"### Validator Issues (if any)\n"
        f"{chr(10).join('- ' + i for i in validator_verdict.get('issues', [])[:3])}\n\n"
        + (
            f"### ⚠️ AI 게이트 경고 (통과 필수 아님, 참고용)\n{chr(10).join(warnings)}\n"
            if warnings else ""
        )
    )
    # 기존 open PR 있으면 재사용 (단일 hermes 브랜치가 force-push로 업데이트되므로
    # PR은 그대로 살아있고 새 commit만 반영됨)
    existing_pr = subprocess.run(
        ["ssh", repo_host,
         f'cd "{repo_dir}" && gh pr list --head {branch_name} --state open --json url --jq ".[0].url // empty"'],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
    )
    pr_url = (existing_pr.stdout or "").strip()

    if pr_url:
        _comment(f"ℹ️ 기존 open PR 재사용: {pr_url}")
    else:
        pr_cmd = (
            f'cd "{repo_dir}" && '
            f'gh pr create --title "hermes: {commit_msg}" '
            f'--body @- --base main --head {branch_name} 2>&1'
        )
        pr = subprocess.run(
            ["ssh", repo_host, pr_cmd],
            input=pr_body, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60, check=False,
        )
        for line in pr.stdout.splitlines():
            if line.startswith("https://github.com/"):
                pr_url = line.strip()
                break

    if not pr_url:
        _comment(f"⚠️ PR 생성 실패:\n```\n{pr.stdout[-400:]}\n```")
        return {
            "success": True,  # push는 성공했으니 부분 성공
            "summary": f"브랜치 push 완료: `{branch_name}` — PR 수동 생성 필요",
            "next_status": "review",
        }

    # ── P0a 컴파일 게이트 (MCP 결과 재사용, fail-INDETERMINATE). HERMES_COMPILE_GATE=off|warn|block
    # MCP 미가용=indeterminate → 절대 차단 안 함(야간 editor-off 전체 락업 방지). 실제 CS 에러만 block.
    _compile_gate = os.environ.get("HERMES_COMPILE_GATE", "off").lower()
    if _compile_gate in ("warn", "block") and repo.get("type") == "unity":
        if mcp_ok and mcp_compile_errors:
            _cstate, _creason = "error", f"컴파일 에러 {len(mcp_compile_errors)}건 (MCP)"
        elif mcp_ok:
            _cstate, _creason = "clean", ""
        else:
            _cstate, _creason = "indeterminate", "MCP 미가용 — 컴파일 검증 불가(차단 안 함)"
        if _cstate == "error" and _compile_gate == "block":
            _merge_blocked = True
            _block_reason = _creason
            _comment(f"⛔ **컴파일 게이트 차단** — {_creason}")
            _record_gate_event(task_id=task_id, gate="compile", result="block", reason=_creason, merge_state="blocked")
        else:
            _record_gate_event(task_id=task_id, gate="compile", result=_cstate, reason=_creason)
            if _cstate == "error":
                _comment(f"⚠️ **컴파일 경고**(차단 X — warn 모드) — {_creason}")
            elif _cstate == "indeterminate":
                _comment("ℹ️ 컴파일 검증 불가(MCP 미가용) — 차단 안 함, 머지 진행")

    # ── 자동 머지 (HERMES_AUTO_MERGE=false로 끌 수 있음. 기본 on)
    # 팀원들이 git pull로 바로 받을 수 있게 main에 즉시 반영.
    # conflict가 있으면 머지 실패 → PR만 남기고 수동 처리.
    auto_merge = os.environ.get("HERMES_AUTO_MERGE", "true").lower() in {"1", "true", "yes"}
    if _merge_blocked:
        # 게이트 차단 — main 머지 안 하고 PR만 보존, 사람 검토로. 작성자에게 Slack.
        auto_merge = False
        _comment(f"⛔ 배포 게이트 차단: {_block_reason} — main 머지 안 함, PR만 보존. 검토 후 수동 머지/재작업.")
        _send_slack_failure(
            email=(task.get("created_by_email") or ""),
            title=title,
            reason=f"⛔ 배포 차단 — {_block_reason}. Hermes가 자동 머지하지 않고 멈췄습니다(검토 필요).\nPR: {pr_url}",
            category="merge_gate_blocked",
            fallback_assignee=(task.get("assignee") or ""),
        )
    merged = False
    if auto_merge:
        merge_cmd = (
            f'cd "{repo_dir}" && '
            f'gh pr merge {pr_url} --squash --delete-branch 2>&1'
        )
        mr = subprocess.run(
            ["ssh", repo_host, merge_cmd],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=90, check=False,
        )
        if mr.returncode == 0:
            merged = True
            _record_gate_event(task_id=task_id, gate="merge", result="merged", merge_state="merged")
            _comment(f"🚀 **main으로 자동 머지 완료** (squash + 브랜치 삭제)\n팀원은 `git pull origin main`으로 받을 수 있음.")
        else:
            # conflict / permission / 등등
            err = (mr.stdout or mr.stderr)[-400:]
            _comment(f"⚠️ 자동 머지 실패 — PR은 열려있음 (수동 머지 필요):\n```\n{err}\n```")
            # Hermes 변경과 기존(사용자) 변경 충돌 → 작성자에게 경과 Slack (기능 덮어쓰지 않고 PR 보존)
            if _categorize_git_error(mr.stdout or mr.stderr or "") == "merge_conflict":
                _send_slack_failure(
                    email=(task.get("created_by_email") or ""),
                    title=title,
                    reason=f"⚠️ Hermes 변경과 기존 코드가 충돌(merge conflict). 기능을 덮어쓰지 않고 PR을 열어둡니다 — 수동 머지/충돌 해결 필요.\nPR: {pr_url}\n{err[:300]}",
                    category="merge_conflict",
                    fallback_assignee=(task.get("assignee") or ""),
                )

    # Hermes 세션 링크 기록 (재작업 시 참조용)
    try:
        writer.link_hermes_session(
            task_id=task_id,
            session_id=f"unity_modify_{short_id}",
            scope={
                "branch": branch_name,
                "pr_url": pr_url,
                "summary": plan_summary[:500],
                "is_rework": is_rework,
            },
        )
    except Exception:
        log.exception("session link failed")

    # 성공도 기록 (실패/성공 비율 트래킹)
    try:
        from pymongo import MongoClient
        from failure_learning import record_success
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        record_success(
            client[DB_NAME],
            task_id=task_id,
            metadata={
                "action": "unity_modify",
                "is_rework": is_rework,
                "files_changed": len(changed_files),
                "pr_url": pr_url,
            },
        )
    except Exception:
        pass

    # ── Phase 완료 처리: phase_plan 있는 task면 phase_log 누적 + 다음 phase 결정
    # 게이트 차단 시 phase 자동진행 금지(미머지 상태로 다음 phase 진행하면 회귀) → review로.
    auto_advance_status = "review"
    if is_phased and not _merge_blocked:
        try:
            from bson import ObjectId as _OID
            from datetime import datetime as _DT
            log_entry = {
                "phase": current_phase_n,
                "name": phase_plan[current_phase_n - 1].get("name", "") if current_phase_n <= len(phase_plan) else "",
                "commit": "",  # branch 단일이라 SHA는 PR에서 추적
                "pr_url": pr_url,
                "files": changed_files[:20],
                "summary": plan_summary[:300],
                "completed_at": _DT.utcnow().isoformat(),
            }
            is_last = current_phase_n >= len(phase_plan)
            update_set = {
                "current_phase": current_phase_n + 1,
                "updated_at": _DT.utcnow().isoformat(),
            }
            # CAS(compare-and-swap): current_phase가 여전히 이 phase일 때만 진행.
            # 같은 phase가 중복 디스패치되면 두 번째 advance는 matched_count=0 →
            # 중복 PR 양산(#220~228)의 self-retrigger 고리를 끊는다.
            _adv_res = _c[DB_NAME]["pixelforge_tasks"].update_one(
                {"_id": _OID(task_id), "current_phase": current_phase_n},
                {"$push": {"phase_log": log_entry}, "$set": update_set},
            )
            if _adv_res.matched_count == 0:
                # 다른 디스패치가 이미 이 phase를 진행시킴 — 재트리거 금지(중복 실행 감지)
                log.warning(
                    "  ⚠️ phase advance CAS 실패 (current_phase != %d) — 중복 실행 감지, 자동 재트리거 안 함",
                    current_phase_n,
                )
                auto_advance_status = "review"
            elif not is_last:
                # 다음 phase 자동 트리거 — status=todo로 두면 watcher가 picks up
                auto_advance_status = "todo"
                _comment(
                    f"✅ **Phase {current_phase_n}/{len(phase_plan)} 완료** — 다음 phase 자동 진행됩니다.\n"
                    f"PR: {pr_url}"
                )
            else:
                _comment(
                    f"🏁 **전체 {len(phase_plan)} phase 완료** — 최종 리뷰 단계.\n"
                    f"PR: {pr_url}"
                )
        except Exception:
            log.exception("phase_log 갱신 실패 — 기본 review 흐름")

    summary = (
        f"{'♻️' if is_rework else '🎉'} **팀 작업 {'재' if is_rework else ''}완료**"
        + (f" (phase {current_phase_n}/{len(phase_plan)})" if is_phased else "")
        + f"\n\n"
        f"- 브랜치: `{branch_name}`\n"
        f"- 변경 파일: {len(changed_files)}개\n"
        f"- PR: {pr_url}\n"
        f"{'- 피드백 반영 포함' if is_rework else ''}\n\n"
        f"추가 피드백 있으면 **이 태스크 코멘트로** 남겨주세요 → Hermes가 자동 재작업합니다."
    )
    # 요청자에게 완료 DM (리뷰 요청)
    _send_slack_success(
        email=(task.get("created_by_email") or ""),
        title=title,
        summary=f"브랜치 `{branch_name}`에 변경 파일 {len(changed_files)}개 반영됨. {'(재작업 완료)' if is_rework else ''}",
        pr_url=pr_url,
        fallback_assignee=(task.get("assignee") or ""),
    )
    return {
        "success": True,
        "summary": summary,
        "next_status": auto_advance_status,
        "metadata": {
            "branch": branch_name,
            "pr_url": pr_url,
            "files_changed": len(changed_files),
            "is_rework": is_rework,
            "phase": current_phase_n if is_phased else None,
            "total_phases": len(phase_plan) if is_phased else None,
            "agent_durations": {
                "lead": lead_resp.duration_sec,
                "main_coder": main_resp.duration_sec,
                "validator": validator_resp.duration_sec,
                "reviewer": reviewer_resp.duration_sec,
            },
        },
    }


# ──────────────────────────────────────────────
# design/motif pipeline — PixelLab 호출로 비선형 모티프 cells 생성
# ──────────────────────────────────────────────
def _execute_design_motif_pipeline(task: dict[str, Any]) -> dict[str, Any]:
    """🎨 design/motif 파이프라인.

    선형 패턴(level)과 달리 비선형 모티프(코끼리, 캐릭터, 일러스트)를 PixelLab으로 생성한다.

    흐름:
      1. PixelForge /api/internal/generate-cells 호출 (Bearer HERMES_INTERNAL_API_KEY)
      2. cells + image_base64 응답 수신
      3. save_level()로 pixelforge_grid_levels 저장 (PNG bytes 첨부)
      4. _export_balloonflow_attachment hook이 자동 발화 → BalloonFlow JSON 첨부
    """
    import urllib.request
    import base64 as _b64
    from projecthub_writer import ProjectHubWriter as _PHW
    from pymongo import MongoClient as _MC

    task_id = str(task.get("_id"))
    title = task.get("title", "")
    description = task.get("description", "")

    _c = _MC(MONGO_URI)
    _wr = _PHW(_c[DB_NAME]["pixelforge_tasks"])

    def _comment(text: str) -> None:
        try:
            _wr.add_comment(task_id, text, author="hermes")
        except Exception:
            log.exception("comment failed")

    # 1) prompt 구성 — title + description + 마지막 사용자 답변
    HERMES_AUTHORS = {"hermes", "hermes-bot", "헤르메스"}
    last_user_reply = ""
    for c in reversed(task.get("comments") or []):
        auth = (c.get("author") or "").strip().lower()
        if not auth or auth in HERMES_AUTHORS:
            continue
        if (c.get("kind") or "") == "ask_owner":
            continue
        last_user_reply = (c.get("text") or "").strip()
        break
    prompt_raw = " ".join(filter(None, [title, description, last_user_reply])).strip()
    if not prompt_raw:
        _comment("❌ motif: prompt 비어있음 (title/description/사용자 답변 모두 공란)")
        return {"success": False, "error": "empty prompt", "next_status": "review"}

    # 2) 메타 추출 (task.metadata 우선, 없으면 default)
    md = task.get("metadata") or {}
    if not isinstance(md, dict):
        md = {}
    width = int(md.get("gridCols") or md.get("width") or 20)
    height = int(md.get("gridRows") or md.get("height") or 20)
    num_colors = int(md.get("num_colors") or md.get("numColors") or 5)

    _comment(
        f"🎨 **design_motif** PixelLab 호출 중... "
        f"({width}×{height}, {num_colors}색)\n```\n{prompt_raw[:200]}\n```"
    )

    # 3) PixelForge internal API 호출
    api_key = os.environ.get("HERMES_INTERNAL_API_KEY", "")
    if not api_key:
        _comment("❌ motif: HERMES_INTERNAL_API_KEY 미설정")
        return {"success": False, "error": "no hermes key", "next_status": "review"}
    base = os.environ.get("PIXELFORGE_BASE_URL", "http://127.0.0.1:3002").rstrip("/")
    url = f"{base}/pixelforge/api/internal/generate-cells"
    payload = json.dumps({
        "prompt": prompt_raw,
        "width": width, "height": height, "num_colors": num_colors,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _comment(f"❌ motif: PixelForge 호출 실패 — {e}")
        return {"success": False, "error": f"pixelforge: {e}", "next_status": "review"}

    if not data.get("ok"):
        _comment(f"❌ motif: PixelForge 응답 실패 — {data.get('error')}")
        return {"success": False, "error": str(data.get("error", "pixelforge failed")),
                "next_status": "review"}

    cells = data.get("cells") or []
    palette_bf = data.get("palette_balloonflow") or []
    image_b64 = data.get("image_base64") or ""
    filled = int(data.get("filled", 0))
    pipeline = data.get("pipeline", "")
    job_id = data.get("pixellab_job_id", "")
    prompt_en = data.get("prompt_translated", "")
    _comment(
        f"✓ PixelLab 완료 — filled={filled}, palette={palette_bf}, pipeline={pipeline}\n"
        f"job_id={job_id}\nprompt(en)={prompt_en[:120]}"
    )

    if not cells or not image_b64:
        _comment("❌ motif: cells 또는 PNG 누락")
        return {"success": False, "error": "no cells or image", "next_status": "review"}

    # 4) save_level — pixelforge_grid_levels에 저장 + 기존 hook 자동 발화
    try:
        from level_storage import save_level
    except Exception as e:
        _comment(f"❌ motif: save_level import 실패 — {e}")
        return {"success": False, "error": f"import: {e}", "next_status": "review"}

    try:
        png_bytes = _b64.b64decode(image_b64)
    except Exception as e:
        _comment(f"❌ motif: PNG 디코드 실패 — {e}")
        return {"success": False, "error": f"png decode: {e}", "next_status": "review"}

    per_color_count: dict[int, int] = {}
    for row in cells:
        for v in row:
            if isinstance(v, int) and v >= 0:
                per_color_count[v] = per_color_count.get(v, 0) + 1

    level_name = f"motif_{task_id[-8:]}"
    try:
        saved = save_level(
            spec={
                "width": width, "height": height,
                "symmetry": "none",
                "palette": palette_bf,
                "per_color_count": per_color_count,
                "seed": 0,
                "pattern": "motif",
            },
            cells=cells, png_bytes=png_bytes,
            validation={
                "ok": True, "errors": [],
                "color_counts": {str(k): v for k, v in per_color_count.items()},
                "filled_cells": filled,
                "empty_cells": width * height - filled,
                "lenient": True,
            },
            task_id=task_id,
            task_title=title,
            created_by_email=task.get("created_by_email") or "",
            name=level_name,
            team_id="motif",
            pattern_chosen="motif",
            extra_meta={"pixellab_job_id": job_id, "prompt_en": prompt_en},
        )
    except Exception as e:
        log.exception("[motif] save_level failed")
        _comment(f"❌ motif: save_level 실패 — {e}")
        return {"success": False, "error": f"save: {e}", "next_status": "review"}

    _comment(f"✓ 격자 저장 완료 — level_id={saved['id'][-8:]}")

    # 5) BalloonFlow auto-export hook 호출 (다른 흐름과 동일)
    try:
        _export_balloonflow_attachment(
            task=task, saved_id=saved["id"], level_name=level_name,
        )
    except Exception:
        log.exception("[bf-export] motif hook failed")

    _comment("🎈 BalloonFlow JSON이 자동 첨부됐습니다.")

    return {
        "success": True,
        "next_status": "review",
        "metadata": {
            "level_id": saved["id"],
            "filled": filled,
            "palette": palette_bf,
            "pixellab_job_id": job_id,
        },
    }


# ──────────────────────────────────────────────
# BalloonFlow auto-export hook
# ──────────────────────────────────────────────
def _export_balloonflow_attachment(
    *,
    task: dict[str, Any],
    saved_id: str,
    level_name: str,
) -> bool:
    """save_level() 직후 호출. ProjectHub의 export 라우트를 Hermes 키로 호출해
    BalloonFlow Level JSON을 task.attachments에 push.

    task.metadata의 다음 키를 export query로 전달:
      targetLevel, packageId, pos, queueColumns, railCapacity,
      difficulty, flipY, balloonScale, difficultyPurpose, seed,
      targetClearRate, star1, star2, star3, hp, levelId
    실패 시 False 반환 (호출자 흐름 차단 X).
    """
    import urllib.request, urllib.parse
    from datetime import datetime as _dt2, timezone as _tz2
    from bson import ObjectId
    from pymongo import MongoClient
    import time as _t

    api_key = os.environ.get("HERMES_INTERNAL_API_KEY", "")
    if not api_key:
        log.warning("[bf-export] HERMES_INTERNAL_API_KEY missing — skip auto-export")
        return False
    base = os.environ.get("PROJECTHUB_BASE_URL", "http://127.0.0.1:3000").rstrip("/")

    md = task.get("metadata") or {}
    if not isinstance(md, dict):
        md = {}
    qs: dict[str, str] = {"format": "balloonflow"}
    forward = ("targetLevel", "packageId", "pos", "queueColumns", "railCapacity",
               "difficulty", "flipY", "balloonScale", "difficultyPurpose", "seed",
               "targetClearRate", "star1", "star2", "star3", "hp", "levelId")
    for k in forward:
        v = md.get(k)
        if v is None or v == "":
            continue
        qs[k] = "1" if v is True else ("0" if v is False else str(v))

    url = f"{base}/api/levels/{saved_id}/export?{urllib.parse.urlencode(qs)}"

    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {api_key}")
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body)
    except Exception as e:
        log.warning(f"[bf-export] export call failed for {saved_id}: {e}")
        return False

    task_id_raw = task.get("_id") or task.get("task_id")
    if not task_id_raw:
        return False
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", level_name or f"level-{saved_id}")
    json_text = json.dumps(data, ensure_ascii=False, indent=2)
    att = {
        "id": f"{int(_t.time()*1000)}-bf-{saved_id[-6:]}",
        "kind": "json",
        "name": f"{safe_name}.balloonflow.json",
        "mime": "application/json",
        "size": len(json_text.encode("utf-8")),
        "content": json_text,
        "level_id": saved_id,
        "auto_generated": True,
        "source": "balloonflow_auto_export",
    }
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client[DB_NAME]["pixelforge_tasks"].update_one(
            {"_id": ObjectId(str(task_id_raw))},
            {"$push": {"attachments": att},
             "$set": {"updated_at": _dt2.now(_tz2.utc).isoformat()}},
        )
        v = (data.get("_pixelflow_meta") or {}).get("validation") or {}
        log.info(
            f"[bf-export] {att['name']} attached — "
            f"color_match={v.get('color_dart_match')} "
            f"holders={v.get('holder_count')} "
            f"size={att['size']:,}B"
        )
        return True
    except Exception:
        log.exception("[bf-export] attachment push failed")
        return False


# ──────────────────────────────────────────────
# Handler 등록 테이블
# ──────────────────────────────────────────────
_HANDLERS = {
    "db_query": _handle_db_query,
    "chat": _handle_chat,
    "simulation": _handle_simulation,
    "apk_build": _handle_apk_build,
    "unity_modify": _handle_unity_modify,  # 5-역할 팀 코드 수정
    "git_sync": _handle_git_sync,          # 단순 main 동기화 (에이전트 없음)
    "review_needed": _handle_review_needed,
    # Stage 4~6 (GameForge 본격 통합)은 Phase 2에서
    # "gameforge_design": _handle_gameforge_design,
    # "gameforge_code":   _handle_gameforge_code,
    # "gameforge_pipeline": _handle_gameforge_pipeline,
    # "training":         _handle_training,
}
