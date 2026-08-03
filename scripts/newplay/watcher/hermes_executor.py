"""hermes_executor.py — NewPlay 태스크 실행.

projecthub_watcher.py 인터페이스:
    execute_task(task, context, route) -> {"success","summary","error","next_status","metadata"}

흐름:
    Translator(팀 판정 + 정보충분성) → 팀별 PM(분과 배정) → 분과 역할 실행 → 코멘트 + review

원칙 두 가지:
  1. **자동 완료하지 않는다.** 결과는 항상 review 로 두고 사람이 판정한다.
     게임팀에서 "chat = 즉시 done" 이던 시절 처음 태스크가 무조건 완료로 넘어가는 문제가 있었다.
  2. **할 수 없는 일을 한 척하지 않는다.** 지금 newplay 노드의 deploy key 가 GitHub 에
     등록돼 있지 않아 코드 push 가 불가능하다. dev 요청은 지식베이스 기반 분석까지만 하고
     "무엇이 막혀 있는지"를 코멘트에 남긴다.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

import agent_team
import newplay_kb

log = logging.getLogger("newplay-executor")

# 분과 → 실행 역할. hermes_agent_roles 에 등록된 이름과 일치해야 한다.
SUB_ROLE = {
    "dev": {
        "backend": "dev_backend_coder",
        "frontend": "dev_frontend_coder",
        "infra": "dev_infra_engineer",
        "qa": "qa_test_writer",
        "general": "main_coder",
    },
    "data": {
        "bq": "data_analyst",
        "logspec": "data_logspec",
        "review": "data_reviewer",
        "general": "data_analyst",
    },
    "design": {
        "ux": "design_ux_writer",
        "general": "design_ux_writer",
    },
}
PM_ROLE = {"dev": "dev_pm", "data": "data_pm", "design": "design_pm"}

# KB 검색 시 분과별로 좁힐 영역 — 프런트 질문에 백엔드 코드가 딸려오면 답이 흐려진다.
AREA_HINT = {"backend": "backend", "frontend": "front-end", "infra": "", "qa": ""}


def _comment(writer, task_id: str, text: str) -> None:
    try:
        writer.add_comment(task_id, text, author="hermes")
    except Exception:  # noqa: BLE001
        log.exception("코멘트 실패")


def _history(context: dict[str, Any]) -> str:
    rows = context.get("comments") or []
    if not rows:
        return "(없음)"
    return "\n".join(
        f"- [{c.get('author', '?')}]: {str(c.get('text') or '')[:300]}" for c in rows
    )


# ─────────────────────────────────────────────────────────── Translator
TRANSLATOR_PROMPT = """너는 NewPlay 팀(blocore/webstore — 결제 웹 플랫폼)의 요청 분류기다.

레포 구조: backend/(Express 5.1 + TypeORM/MySQL), front-end/(React 19 + Vite 7 + SCSS).
게임 프로젝트가 아니다. 레벨·밸런스·캐릭터 같은 게임 개념은 여기 없다.

# 요청
{title}

## 상세
{description}

## 이전 대화
{history}

# 판정할 것
1. clarity — 지금 정보로 진행할 수 있는가?
   - "clear": 진행 가능
   - "needs_input": 핵심 정보가 없어 물어봐야 함 (질문 최대 3개)
   - "cancel": 사용자가 중단을 요청함
2. team — 어느 팀이 처리하는가?
   - "dev"    : 코드 수정/버그/리팩토링/배포 설정
   - "data"   : 지표·로그·쿼리·분석 (BigQuery)
   - "design" : 화면 흐름·결제 정책 문서
   - "chat"   : 위에 안 맞는 질문·설명 요청

주의: "이 수치를 바꿔줘"는 dev, "이 수치가 얼마인지 알려줘"는 data 다.

# 출력 (JSON 하나만)
{{"clarity":"clear|needs_input|cancel","team":"dev|data|design|chat",
"reason":"한 줄 근거","questions":["needs_input 일 때만"],
"enriched":"clear 일 때 — 정제된 요구사항 2~4줄"}}"""


def _translate(task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    prompt = TRANSLATOR_PROMPT.format(
        title=task.get("title", ""),
        description=task.get("description", "") or "(없음)",
        history=_history(context),
    )
    resp = agent_team.invoke("translator", prompt, timeout=120, want_json=True)
    agent_team.log_session(task, "translator", resp, prompt)
    if not resp.success:
        return {"ok": False, "error": resp.error}
    out = resp.structured or {}
    return {
        "ok": True,
        "clarity": str(out.get("clarity") or "clear").lower(),
        "team": str(out.get("team") or "chat").lower(),
        "reason": str(out.get("reason") or ""),
        "questions": [q for q in (out.get("questions") or []) if isinstance(q, str)][:3],
        "enriched": str(out.get("enriched") or ""),
        "raw": resp.output,
    }


# ─────────────────────────────────────────────────────────── PM
PM_PROMPT = """너는 {team} 팀 PM 이다. 아래 요청을 어느 분과가 맡을지 하나 고른다.

선택지: {options}

# 요청
{title}

## 상세
{description}

# 출력 (JSON 하나만)
{{"sub_team":"<선택지 중 하나>","reason":"한 줄 근거"}}"""


def _pick_sub_team(task: dict[str, Any], team: str, writer, task_id: str) -> str:
    known = list(SUB_ROLE.get(team, {}).keys())
    # DB 에 분과가 추가되면 자동 반영 (UI 에서 늘릴 수 있다)
    for s in agent_team.sub_teams_of(team):
        if s not in known:
            known.append(s)

    stored = str(task.get("sub_team") or "").lower()
    if task.get("sub_team_override") and stored:
        _comment(writer, task_id, f"🔒 **{PM_ROLE.get(team, 'pm')} 스킵** — 사용자 수동 지정: `{stored}` 분과")
        return stored

    pm = PM_ROLE.get(team)
    if not pm:
        return "general"
    prompt = PM_PROMPT.format(
        team=team, options=" | ".join(known),
        title=task.get("title", ""), description=task.get("description", "") or "(없음)",
    )
    resp = agent_team.invoke(pm, prompt, timeout=120, want_json=True)
    agent_team.log_session(task, pm, resp, prompt)
    if not resp.success:
        _comment(writer, task_id, f"⚠️ {pm} 실패: {resp.error[:200]} — `general` 로 진행")
        return "general"
    out = resp.structured or {}
    sub = str(out.get("sub_team") or "general").lower().strip()
    if sub not in known:
        sub = "general"
    _comment(writer, task_id, f"📋 **{pm}** 판정: `{sub}` 분과 — {str(out.get('reason') or '')[:200]}")
    return sub


# ─────────────────────────────────────────────────────────── 실행
WORK_PROMPT = """# 요청
{title}

## 상세
{description}

## 정제된 요구사항
{enriched}

## 이전 대화
{history}

{kb}

# 지시
너의 역할 정의에 적힌 원칙을 그대로 따른다.
- 지식베이스에서 가져온 코드가 위에 있으면 그것을 근거로 답한다. 없는 동작을 있다고 하지 마라.
- 파일을 언급할 때는 경로와 줄 번호를 함께 적는다.
{extra}
마크다운으로 답한다."""

DEV_EXTRA = """- **지금은 레포에 쓰기(commit/push)를 할 수 없다.** newplay 노드의 deploy key 가
  GitHub 에 아직 등록되지 않았다. 그러니 "고쳤다"고 쓰지 말고, 어떤 파일의 어디를
  어떻게 바꿔야 하는지 diff 수준으로 제시한다.
- 변경안에는 그에 맞는 검증 명령(yarn lint / build / test, 어느 워크스페이스인지)을 함께 적는다."""


def _run_work(task: dict[str, Any], context: dict[str, Any], team: str, sub: str,
              tr: dict[str, Any], writer, task_id: str) -> dict[str, Any]:
    role = SUB_ROLE.get(team, {}).get(sub) or SUB_ROLE.get(team, {}).get("general")
    if not role:
        return {"success": False, "error": f"{team}/{sub} 에 매핑된 역할이 없습니다", "next_status": "review"}

    query = f"{task.get('title', '')} {task.get('description', '') or ''}".strip()
    kb = newplay_kb.as_prompt_block(query, top=6, area=AREA_HINT.get(sub, ""))
    if not kb:
        kb = "## 관련 코드\n(지식베이스 검색 결과 없음 — 코드 근거 없이 답하고 있음을 명시할 것)"

    prompt = WORK_PROMPT.format(
        title=task.get("title", ""),
        description=task.get("description", "") or "(없음)",
        enriched=tr.get("enriched") or "(없음)",
        history=_history(context),
        kb=kb,
        extra=(DEV_EXTRA if team == "dev" else ""),
    )

    _comment(writer, task_id, f"⚙️ **{role}** 실행 중... (`{team}/{sub}` 분과)")
    resp = agent_team.invoke(role, prompt, timeout=600)
    agent_team.log_session(task, role, resp, prompt)

    if not resp.success:
        _comment(writer, task_id, f"❌ {role} 실패: {resp.error[:400]}")
        return {"success": False, "error": resp.error or f"{role} failed", "next_status": "review"}

    body = (resp.output or "").strip() or "(빈 응답)"
    header = f"### ⚙️ {role} 결과 ({resp.model}, {resp.duration_sec:.0f}s)"
    if team == "dev":
        header += "\n\n> 🔒 레포 쓰기 권한이 없어 **제안까지만** 수행했습니다. deploy key 등록 후 자동 적용이 가능해집니다."
    _comment(writer, task_id, f"{header}\n\n{body[:9000]}")

    return {
        "success": True,
        "summary": f"{team}/{sub} — {role} 완료",
        "next_status": "review",
        "metadata": {"team": team, "sub_team": sub, "role": role, "model": resp.model},
    }


def _persist(task: dict[str, Any], writer, task_id: str, patch: dict[str, Any]) -> None:
    try:
        writer.patch(task_id, patch)
    except Exception:  # noqa: BLE001
        log.exception("patch 실패")


def execute_task(task: dict[str, Any], context: dict[str, Any],
                 route: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("_id"))
    writer = context.get("_writer")
    if writer is None:
        # watcher 가 writer 를 컨텍스트에 안 넣는 구조라 직접 만든다.
        from pymongo import MongoClient
        from projecthub_writer import ProjectHubWriter
        cli = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5000)
        writer = ProjectHubWriter(cli[os.environ.get("MONGODB_DB", "newteam")]["pixelforge_tasks"])

    if route.get("action") == "skip":
        return {"success": True, "summary": route.get("reason", "skip"), "next_status": "review"}

    kb = context.get("kb_health") or {}
    if not kb.get("ok"):
        _comment(writer, task_id, f"⚠️ 지식베이스 접근 실패 — 코드 근거 없이 진행합니다. ({str(kb.get('error'))[:150]})")

    # ── 사용자가 팀을 지정했으면 Translator 를 건너뛴다
    params = route.get("params") or {}
    if params.get("override") and params.get("team"):
        team = str(params["team"]).lower()
        tr = {"clarity": "clear", "team": team, "enriched": ""}
        _comment(writer, task_id, f"🔒 **Translator 스킵** — 사용자 수동 배정: `{team}` 팀")
    else:
        tr = _translate(task, context)
        if not tr.get("ok"):
            _comment(writer, task_id, f"⚠️ Translator 실행 실패: {str(tr.get('error'))[:200]} — 수동 확인 필요")
            return {"success": True, "summary": "Translator 실패 — review 대기", "next_status": "review"}

        if tr["clarity"] == "cancel":
            _comment(writer, task_id, f"🛑 **작업 취소 감지** — {tr.get('reason', '')[:300]}\n\n변경 없이 완료 처리합니다.")
            return {"success": True, "summary": "취소", "next_status": "done"}

        if tr["clarity"] == "needs_input" and tr.get("questions"):
            qs = "\n".join(f"- {q}" for q in tr["questions"])
            _comment(writer, task_id,
                     "🤔 **정보 확인 필요** — 진행하려면 아래에 답변 부탁드립니다.\n\n"
                     f"{qs}\n\n_이 코멘트에 답변을 남기시면 자동으로 재개됩니다._")
            return {"success": True, "summary": "사용자 답변 대기", "next_status": "review"}

        team = tr["team"]

    _persist(task, writer, task_id, {"team": team})

    if team == "chat":
        query = f"{task.get('title', '')} {task.get('description', '') or ''}".strip()
        kbblock = newplay_kb.as_prompt_block(query, top=5) or "## 관련 코드\n(검색 결과 없음)"
        prompt = WORK_PROMPT.format(
            title=task.get("title", ""), description=task.get("description", "") or "(없음)",
            enriched=tr.get("enriched") or "(없음)", history=_history(context),
            kb=kbblock, extra="",
        )
        resp = agent_team.invoke("lead", prompt, timeout=300)
        agent_team.log_session(task, "lead", resp, prompt)
        if not resp.success:
            _comment(writer, task_id, f"❌ 답변 실패: {resp.error[:300]}")
            return {"success": False, "error": resp.error, "next_status": "review"}
        _comment(writer, task_id, f"### 💬 답변 ({resp.model})\n\n{(resp.output or '').strip()[:9000]}")
        return {"success": True, "summary": "chat 답변 완료", "next_status": "review"}

    sub = _pick_sub_team(task, team, writer, task_id)
    _persist(task, writer, task_id, {"sub_team": sub})
    return _run_work(task, context, team, sub, tr, writer, task_id)
