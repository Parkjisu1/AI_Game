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
import re
from datetime import datetime, timezone
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

# 분과 → 검수 역할. 작업 결과를 같은 급의 모델이 다시 본다.
# 리뷰어를 안 부르면 카탈로그에만 있고 아무 일도 안 하는 역할이 된다 —
# 게임팀에서 data 팀 역할이 그 상태로 방치돼 요청이 전부 chat 으로 새던 전례가 있다.
REVIEW_ROLE = {
    "dev": {
        "backend": "dev_backend_reviewer",
        "frontend": "dev_frontend_reviewer",
        "infra": "dev_infra_reviewer",
        "qa": "qa_reviewer",
        "general": "reviewer",
    },
    "data": {"review": None, "bq": "data_reviewer", "logspec": "data_reviewer", "general": "data_reviewer"},
    "design": {"ux": "design_ux_reviewer", "general": "design_ux_reviewer"},
}

REVIEW_PROMPT = """아래는 같은 팀의 `{worker}` 가 낸 결과다. 너는 이것을 검수한다.

# 원래 요청
{title}

## 상세
{description}

# 검수 대상 결과
{result}

{kb}

# 검수 기준
- 인용된 파일·줄 번호가 실제 근거와 맞는가? 위 "관련 코드"에 없는 내용을 단정하지 않았는가?
- **빠뜨린 표면이 없는가?** 이 레포는 같은 개념이 backend 와 front-end 에 따로 구현된 경우가 많다.
  프런트만 고치고 이메일·엑셀·어드민 API 를 놓치면 절반만 고친 것이다.
  "영향 범위" 표가 없거나, 표는 있는데 한쪽 표면을 근거 없이 "해당 없음" 처리했으면 revise 다.
- **고쳐야 할 성격인데 테스트 제안이 없으면 revise** 다(표시 오류·버그 수정 등).
- 요청 범위를 넘어선 제안이 섞이지 않았는가?
- 결제·금액·권한을 다뤘다면 실패 경로(타임아웃·중복요청·부분환불·통화)가 검토됐는가?
- 검증 명령(어느 워크스페이스에서 무엇을 돌릴지)이 빠지지 않았는가?

통과시킬 근거가 부족하면 통과시키지 마라. "아마 맞을 것"은 반려 사유다.

# 출력 (JSON 하나만)
{{"verdict":"approve|revise|reject","score":0-100,
"issues":["구체적 문제 (없으면 빈 배열)"],"comment":"2~4줄 총평"}}"""

# KB 검색 시 분과별로 좁힐 영역 — 프런트 질문에 백엔드 코드가 딸려오면 답이 흐려진다.
AREA_HINT = {"backend": "backend", "frontend": "front-end", "infra": "", "qa": ""}


def _comment(writer, task_id: str, text: str) -> None:
    try:
        writer.add_comment(task_id, text, author="hermes")
    except Exception:  # noqa: BLE001
        log.exception("코멘트 실패")


HERMES_AUTHORS = {"hermes", "hermes-bot", "헤르메스"}
ASK_MARK = "정보 확인 필요"


def _asked_and_answered(context: dict[str, Any]) -> tuple[bool, str]:
    """이미 물어봤고 사용자가 답했는가? (답했으면 True, 답변 텍스트)

    Translator 는 프롬프트만으로는 같은 질문을 반복한다 — 실측에서 3라운드를 돌며
    글자만 조금 바꾼 동일 질문을 다시 냈다(Game Key 판매 태스크, 코멘트 11개).
    사용자 입장에서는 답을 줬는데도 계속 되묻는 것이라 진행이 막힌다.
    그래서 프롬프트에 맡기지 않고 코드로 끊는다.
    """
    comments = context.get("comments") or []
    last_ask = -1
    for i, c in enumerate(comments):
        author = str(c.get("author") or "").strip().lower()
        if author in HERMES_AUTHORS and ASK_MARK in str(c.get("text") or ""):
            last_ask = i
    if last_ask < 0:
        return False, ""
    replies = [
        str(c.get("text") or "").strip()
        for c in comments[last_ask + 1:]
        if str(c.get("author") or "").strip().lower() not in HERMES_AUTHORS
        and str(c.get("text") or "").strip()
    ]
    return (len(replies) > 0), "\n".join(replies)


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
   - "needs_input": **사용자만 답할 수 있는** 정보가 없어 물어봐야 함 (질문 최대 3개)
   - "cancel": 사용자가 중단을 요청함

   **중요 — 코드에 관한 것은 묻지 마라.** 레포 전체(1,236파일)가 의미 검색 가능한
   지식베이스에 들어 있어서, 담당 에이전트가 파일명·구현 위치·현재 동작을 스스로 찾는다.
   ❌ 묻지 말 것: "어떤 파일인가요", "어떤 프레임워크인가요", "현재 어떻게 구현돼 있나요"
   ✅ 물어도 되는 것: 사용자의 **의도·선택·값** — 예) "A안과 B안 중 무엇으로 할까요",
      "적용 대상이 프로덕션인가요 QA인가요", "기한이 언제인가요"
   즉 코드를 읽으면 알 수 있는 것이면 clarity=clear 로 두고 진행시켜라.
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
  어떻게 바꿔야 하는지 제시한다.
- 변경안에는 그에 맞는 검증 명령(yarn lint / build / test, 어느 워크스페이스인지)을 함께 적는다.

- **영향 범위를 먼저 훑고 시작한다. 답변 맨 앞에 "영향 범위" 표를 넣는다.**
  이 레포는 같은 개념이 backend 와 front-end 에 **따로 구현돼 있는 경우가 많다.**
  한쪽만 고치면 화면은 맞는데 영수증 메일·정산 엑셀·어드민 API 는 그대로 틀린 채로 남는다.
  (실제 사례: 결제수단 표시명 — 프런트 매핑만 고치면 `backend/src/lib/paymentMethodName.ts`
   가 쓰는 메일·엑셀은 여전히 코드값을 뿌린다)
  표에는 이렇게 적는다:
  | 표면 | 해당 파일 | 이번에 고치나 | 안 고치면 남는 문제 |
  최소한 다음을 확인하고 각각 "해당 없음" 이라도 적는다:
  프런트 화면 / 백엔드 API 응답 / 이메일·PDF·엑셀 등 문서 산출물 / 어드민 화면 / DB 저장값.

- **버그 수정이나 표시 오류 수정이면 재현 테스트를 함께 제시한다.**
  어느 파일에 어떤 케이스를 추가할지 적는다. 테스트 없이 "고쳤다" 고만 하지 않는다.

- **답변 맨 끝에 적용 가능한 패치를 하나 붙인다.** 설명과 별개로, 아래 형식을 정확히 지킨다.
  이 블록은 사람이 읽는 용도가 아니라 `git apply` 로 그대로 먹여 미리보기를 빌드하는 데 쓴다.

```diff
diff --git a/front-end/src/... b/front-end/src/...
--- a/front-end/src/...
+++ b/front-end/src/...
@@ -<시작>,<줄수> +<시작>,<줄수> @@
 (문맥 3줄)
-지울 줄
+넣을 줄
 (문맥 3줄)
```

  규칙:
  * 경로는 레포 루트 기준(`front-end/...`, `backend/...`). `a/`·`b/` 접두사 필수.
  * 문맥 줄은 **실제 파일 내용과 한 글자도 달라선 안 된다.** 위 "관련 코드" 에 있는 원문을 그대로 쓴다.
    확신이 없으면 그 파일은 패치에 넣지 말고 설명으로만 남긴다 — 틀린 패치는 적용 자체가 실패한다.
  * 프런트(front-end/) 변경만 미리보기에 반영된다. 백엔드 변경은 패치에 넣어도 화면에 안 보인다.
  * 바꿀 게 없으면 diff 블록을 아예 넣지 않는다. 빈 블록을 만들지 마라."""


def _run_work(task: dict[str, Any], context: dict[str, Any], team: str, sub: str,
              tr: dict[str, Any], writer, task_id: str) -> dict[str, Any]:
    role = SUB_ROLE.get(team, {}).get(sub) or SUB_ROLE.get(team, {}).get("general")
    if not role:
        return {"success": False, "error": f"{team}/{sub} 에 매핑된 역할이 없습니다", "next_status": "review"}

    query = f"{task.get('title', '')} {task.get('description', '') or ''}".strip()
    # 분과로 검색을 좁히면 **반대편 표면이 통째로 안 보인다.**
    # 실측(결제수단 표시명 태스크): area=front-end 로 좁히자
    # backend/src/lib/paymentMethodName.ts(무필터 4위)가 빠졌고,
    # 그 결과 백엔드(영수증 메일·정산 엑셀)의 같은 문제를 제안에서 누락했다.
    # 사람이 낸 PR(EW-2839)은 그 파일을 128줄 고쳤다.
    # → 분과 중심 + 전체 교차, 두 번 검색해 합친다.
    kb = newplay_kb.as_prompt_block(query, top=5, area=AREA_HINT.get(sub, ""))
    cross = newplay_kb.as_prompt_block(query, top=5)
    if cross:
        kb = (kb + "\n\n" + cross) if kb else cross
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

    # 역할 성격에 따라 필요한 시간이 다르다.
    # 실측: dev 코더는 220~240초면 끝나지만, design 문서 작성은 600초를 넘겨 타임아웃 났다
    # (Game Key 판매 태스크 — ASIS 가 긴 기획 문서라 산출물도 길다).
    timeout = {"design": 1500, "data": 1200, "dev": 900}.get(team, 900)
    _comment(writer, task_id, f"⚙️ **{role}** 실행 중... (`{team}/{sub}` 분과, 최대 {timeout // 60}분)")
    resp = agent_team.invoke(role, prompt, timeout=timeout)
    agent_team.log_session(task, role, resp, prompt)

    if not resp.success:
        _comment(writer, task_id, f"❌ {role} 실패: {resp.error[:400]}")
        return {"success": False, "error": resp.error or f"{role} failed", "next_status": "review"}

    body = (resp.output or "").strip() or "(빈 응답)"
    header = f"### ⚙️ {role} 결과 ({resp.model}, {resp.duration_sec:.0f}s)"

    # dev 제안은 패치를 따로 떼어 저장한다 — 플랫폼 화면에서 미리보기로 빌드할 수 있게.
    # 저장만 할 뿐 레포·운영·QA 어디에도 적용하지 않는다.
    if team == "dev":
        patch, pfiles = _extract_patch(body)
        if patch:
            _persist(task, writer, task_id, {
                "proposed_patch": patch,
                "patch_files": pfiles,
                "patch_role": role,
                "patch_at": datetime.now(timezone.utc).isoformat(),
            })
            fe = [f for f in pfiles if f.startswith("front-end/")]
            header += (
                "\n\n> 🔒 레포 쓰기 권한이 없어 **제안까지만** 수행했습니다."
                f"\n> 📦 적용 가능한 패치를 저장했습니다 — 대상 {len(pfiles)}개 파일"
                + (f" (프런트 {len(fe)}개)" if fe else "")
                + "\n> **플랫폼 현황 → 앱 화면 → 수정안**에서 실제 화면으로 확인할 수 있습니다."
                + ("" if fe else "\n> ⚠️ 프런트 변경이 없어 미리보기 화면에는 차이가 안 보입니다.")
            )
        else:
            header += "\n\n> 🔒 레포 쓰기 권한이 없어 **제안까지만** 수행했습니다. (적용 가능한 패치 형식은 포함되지 않았습니다)"

    _comment(writer, task_id, f"{header}\n\n{body[:9000]}")

    # ── 검수 단계
    verdict = _review(task, team, sub, role, body, kb, writer, task_id)

    return {
        "success": True,
        "summary": f"{team}/{sub} — {role} 완료" + (f" · 검수 {verdict}" if verdict else ""),
        "next_status": "review",
        "metadata": {"team": team, "sub_team": sub, "role": role,
                     "model": resp.model, "verdict": verdict},
    }


def _review(task: dict[str, Any], team: str, sub: str, worker: str, result: str,
            kb: str, writer, task_id: str) -> str:
    """작업 결과를 검수 역할이 다시 본다. 실패해도 태스크를 죽이지 않는다(검수는 보조 게이트)."""
    rrole = (REVIEW_ROLE.get(team) or {}).get(sub, (REVIEW_ROLE.get(team) or {}).get("general"))
    if not rrole or rrole == worker:
        return ""

    prompt = REVIEW_PROMPT.format(
        worker=worker,
        title=task.get("title", ""),
        description=task.get("description", "") or "(없음)",
        result=result[:12000],
        kb=kb,
    )
    resp = agent_team.invoke(rrole, prompt, timeout=1200, want_json=True)
    agent_team.log_session(task, rrole, resp, prompt)
    if not resp.success:
        _comment(writer, task_id, f"⚠️ {rrole} 검수 실패: {resp.error[:200]} — 결과는 그대로 두고 사람 검수로 넘깁니다.")
        return ""

    out = resp.structured or {}
    v = str(out.get("verdict") or "").lower()
    score = out.get("score")
    issues = [str(i) for i in (out.get("issues") or [])][:6]
    icon = {"approve": "✅", "revise": "🟡", "reject": "❌"}.get(v, "ℹ️")
    lines = [f"### {icon} {rrole} 검수: `{v or '판정없음'}`" + (f" ({score}점)" if score is not None else "")]
    if issues:
        lines.append("")
        lines += [f"- {i}" for i in issues]
    if out.get("comment"):
        lines += ["", str(out["comment"])[:1200]]
    _comment(writer, task_id, "\n".join(lines))
    return v


def _extract_patch(text: str) -> tuple[str, list[str]]:
    """답변 끝의 ```diff 블록을 뽑는다. (패치문자열, 대상파일목록)

    미리보기 빌드에 그대로 먹일 것이라 형식이 어긋나면 차라리 버린다 —
    깨진 패치를 저장해두면 화면에서 "미리보기" 를 눌렀을 때 그때서야 실패한다.
    """
    if not text:
        return "", []
    blocks = re.findall(r"```diff\s*\n(.*?)```", text, re.S)
    if not blocks:
        return "", []
    # 여러 개면 이어 붙인다(파일별로 나눠 쓰는 경우가 있다)
    patch = "\n".join(b.rstrip() for b in blocks).strip()
    if not patch:
        return "", []
    # 최소 형식 검증: diff 헤더와 hunk 가 하나씩은 있어야 한다
    if "diff --git" not in patch or "@@" not in patch:
        log.info("diff 블록이 있으나 형식이 불완전 — 저장하지 않음")
        return "", []
    files = sorted(set(re.findall(r"^\+\+\+ b/(.+)$", patch, re.M)))
    if not patch.endswith("\n"):
        patch += "\n"   # git apply 는 마지막 개행이 없으면 거부한다
    return patch, files


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

        # 이미 물어봤고 사용자가 답했으면 다시 묻지 않는다.
        # 답이 부족해도 그걸 전제로 진행하고, 무엇을 가정했는지 코멘트에 남긴다 —
        # 되묻기를 반복하는 것보다 가정을 밝히고 결과를 내는 편이 훨씬 낫다.
        answered, replies = _asked_and_answered(context)
        if tr["clarity"] == "needs_input" and answered:
            _comment(writer, task_id,
                     "↩️ **이미 답변을 받았으므로 되묻지 않고 진행합니다.**\n\n"
                     f"받은 답변:\n> {replies[:600]}\n\n"
                     "_부족한 부분은 가정하고 진행하며, 가정한 내용은 결과에 명시합니다._")
            tr["clarity"] = "clear"
            tr["enriched"] = (tr.get("enriched") or "") + f"\n\n[사용자 답변]\n{replies[:1200]}"

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
        resp = agent_team.invoke("lead", prompt, timeout=600)
        agent_team.log_session(task, "lead", resp, prompt)
        if not resp.success:
            _comment(writer, task_id, f"❌ 답변 실패: {resp.error[:300]}")
            return {"success": False, "error": resp.error, "next_status": "review"}
        _comment(writer, task_id, f"### 💬 답변 ({resp.model})\n\n{(resp.output or '').strip()[:9000]}")
        return {"success": True, "summary": "chat 답변 완료", "next_status": "review"}

    sub = _pick_sub_team(task, team, writer, task_id)
    _persist(task, writer, task_id, {"sub_team": sub})
    return _run_work(task, context, team, sub, tr, writer, task_id)
