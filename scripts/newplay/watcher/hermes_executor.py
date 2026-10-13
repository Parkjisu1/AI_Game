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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from pymongo import MongoClient

import agent_team
import fact_gate
import mirror_lookup
import newplay_kb
import workspace
import overlap
import learning

log = logging.getLogger("newplay-executor")

# 검수 큐가 쓰는 접속 정보. 게임팀 실행기엔 있던 상수가 여기엔 없어서
# 첫 배포 때 NameError 로 큐 적재가 통째로 실패했다(방어 코드 덕에 태스크는 살았다).
MONGO_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("MONGODB_DB", "newteam")

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


MOCKUP_REVIEW_PROMPT = """아래는 `{worker}` 가 만든 **화면 목업**이다. 너는 이것을 검수한다.

# 원래 요청
{title}

## 상세
{description}

# 검수 대상 결과
{result}

{kb}

# 검수 기준 — 목업이다. 프로덕션 기준을 적용하지 마라.
목업은 "설계가 화면으로 어떻게 보이는지" 를 확인하려고 만드는 실험물이다.
**테스트 미포함, lint/build 미실행, i18n 미적용은 반려 사유가 아니다.** 그건 목업의 전제다.

볼 것은 이 셋뿐이다.
1. 설계와 맞는가 — 요청에 적힌 확정 전제를 화면이 반영했는가? 빠진 화면·단계가 있는가?
2. 기존 톤앤매너를 따랐는가 — 새 디자인 언어를 만들어내지 않았는가?
3. **확정되지 않은 전제를 몰래 쓰지 않았는가** — "아니오" 로 판정된 전제를 썼으면 그것만으로 reject.
   미판정 전제를 썼다면 화면이나 설명에 가정임을 표시했는가?

또 하나: 목업이 **실제 동작하는 것처럼 보이게 만들었으면** 지적하라(가짜 성공 화면 등).
목업임을 사용자가 알 수 있어야 한다.

# 출력 (JSON 하나만)
{{"verdict":"approve|revise|reject","score":0-100,
"issues":["구체적 문제 (없으면 빈 배열)"],"comment":"2~4줄 총평"}}"""


#: 코멘트에 실을 산출물 분량. 전문은 태스크의 `deliverable` 에 60,000자까지 남는다.
COMMENT_BODY_CHARS = int(os.environ.get("NEWPLAY_COMMENT_BODY_CHARS", "20000"))


def _comment_body(body: str) -> str:
    """코멘트에 실을 본문. 자를 때는 **잘렸다는 사실을 남긴다.**

    조용히 자르면 표가 중간에 끊기거나 결론이 사라져도 그렇게 끝난 것처럼 보인다.
    데이터는 `deliverable` 에 온전히 있으니, 문제는 유실이 아니라 **알 수 없음** 이다.
    """
    body = body or ""
    if len(body) <= COMMENT_BODY_CHARS:
        return body
    return (body[:COMMENT_BODY_CHARS]
            + f"\n\n---\n\n> ✂️ **여기서 {len(body) - COMMENT_BODY_CHARS:,}자 잘렸습니다** "
              f"(전체 {len(body):,}자).\n"
              "> 전문은 이 작업의 **산출물** 탭에서 볼 수 있습니다.")


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


#: 최신 사용자 지시에 주는 지면. 사실상 통째로 넣는다 —
#: 이게 잘리면 "코멘트로 요청했는데 못 알아듣는다" 가 된다(실측 보고).
HISTORY_LATEST_USER_CHARS = int(os.environ.get("NEWPLAY_HISTORY_LATEST_CHARS", "16000"))
#: 그 외 사용자 코멘트 지면.
HISTORY_USER_CHARS = int(os.environ.get("NEWPLAY_HISTORY_USER_CHARS", "6000"))
#: 헤르메스가 남긴 코멘트 지면. 우리가 쓴 것이라 요약만 있으면 된다.
HISTORY_BOT_CHARS = int(os.environ.get("NEWPLAY_HISTORY_BOT_CHARS", "400"))
#: 이력 전체 상한.
HISTORY_TOTAL_CHARS = int(os.environ.get("NEWPLAY_HISTORY_TOTAL_CHARS", "60000"))

_HERMES_AUTHORS = {"hermes", "hermes-bot", "헤르메스"}


def _is_user(c: dict[str, Any]) -> bool:
    return str(c.get("author") or "").strip().lower() not in _HERMES_AUTHORS


def _search_query(task: dict[str, Any], context: dict[str, Any]) -> str:
    """KB 검색 질의. 제목·본문에 **최신 사용자 지시**를 더한다.

    코멘트를 빼면 티켓 주제가 검색을 지배해서, 나중에 다른 요청을 남겨도
    원래 주제의 코드만 물어온다. 검색이 주제를 못 따라가면 그 뒤 단계가 전부 어긋난다.
    """
    last_user = str(context.get("last_user_reply") or "")[:600]
    return " ".join(x for x in (task.get("title", ""),
                                task.get("description", "") or "",
                                last_user) if x).strip()


def _history(context: dict[str, Any]) -> str:
    """대화 이력. **사용자 지시를 우선 보존한다.**

    예전에는 모든 코멘트를 300자로 잘랐다. 그래서 티켓에 긴 지시를 코멘트로 남기면
    앞부분만 남고, 에이전트는 계속 원래 제목대로만 답했다(NewPlay 팀 보고).

    사용자 코멘트는 **제목·본문보다 나중에 온 지시**다. 지면을 그에 맞게 준다:
      최신 사용자 지시 > 그 외 사용자 코멘트 > 헤르메스가 남긴 코멘트
    """
    rows = list(context.get("comments") or [])
    if not rows:
        return "(없음)"

    latest_user_idx = -1
    for i in range(len(rows) - 1, -1, -1):
        if _is_user(rows[i]):
            latest_user_idx = i
            break

    lines: list[str] = []
    used = 0
    # 뒤에서부터 채운다 — 최신이 살아남아야 한다.
    for i in range(len(rows) - 1, -1, -1):
        c = rows[i]
        text = str(c.get("text") or "")
        if i == latest_user_idx:
            cap, tag = HISTORY_LATEST_USER_CHARS, "사용자 · 가장 최근 지시"
        elif _is_user(c):
            cap, tag = HISTORY_USER_CHARS, "사용자"
        else:
            cap, tag = HISTORY_BOT_CHARS, "헤르메스"
        body = text[:cap]
        if len(text) > cap:
            body += f"\n  …({len(text) - cap}자 생략)"
        entry = f"- [{tag}] {c.get('author', '?')}:\n  " + body.replace("\n", "\n  ")
        if used + len(entry) > HISTORY_TOTAL_CHARS and lines:
            lines.append("- (이전 대화 생략 — 분량 상한)")
            break
        lines.append(entry)
        used += len(entry)

    lines.reverse()
    if latest_user_idx >= 0:
        lines.append("")
        lines.append("**위 '가장 최근 지시' 가 현재 요구사항이다.** 제목·본문과 어긋나면 그쪽이 최신이다 — "
                     "범위를 좁히거나 바꾸라는 뜻일 수 있으니 무엇을 하라는 것인지 그 지시 기준으로 판단해라.")
    return "\n".join(lines)


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

   **전문가가 제안할 일도 묻지 마라.** 담당자를 부르는 이유는 그가 안을 내놓기 때문이다.
   ❌ "어떤 지표가 필요하신가요", "어떤 이벤트를 쌓을까요", "어떤 항목을 넣을까요",
      "어떤 방식을 원하시나요" — 이건 담당자가 **초안을 내고 사용자가 고치는** 순서다.
   설계·정의·제안을 요청받았다면 clarity=clear 로 두고, 담당자가 안을 만들게 하라.
   사용자가 이미 목적을 말했다면(예: "부스터가 클리어율에 얼마나 기여하는지 알고 싶다")
   그 목적만으로 충분하다 — 세부 항목은 담당자가 채운다.
2. team — 어느 팀이 처리하는가?
   **주제어가 아니라 산출물이 무엇인가로 가른다.** '결제'가 들어갔다고 design 이 아니다.

   - "dev"    : 산출물이 **코드 변경**  — 수정/버그/리팩토링/배포 설정
   - "data"   : 산출물이 **지표·로그 정의나 쿼리** — 무엇을 쌓을지, 어떻게 셀지
   - "design" : 산출물이 **새 기획 문서** — 아직 없는 화면 흐름·정책을 만들어야 할 때
   - "chat"   : 산출물이 **설명**  — 이미 있는 것이 어떻게 돌아가는지 알려주기만 하면 될 때

   가르는 질문 하나: "끝나고 나면 무엇이 남는가?"
     코드 diff 가 남는다      → dev
     이벤트/쿼리 정의가 남는다 → data
     새 문서가 남는다          → design
     답변만 남는다             → chat

주의:
   - "이 수치를 바꿔줘"는 dev, "이 수치가 얼마인지 알려줘"는 data 다.
   - "결제 플로우가 어떻게 구성돼 있는지 설명해줘"는 **chat** 이다.
     이미 있는 것을 읽어서 알려주는 일이라 새로 만들 문서가 없다.
   - "결제 실패 시 재시도 정책을 새로 정해줘"는 design 이다. 없던 문서가 생긴다.

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
마크다운으로 답한다.

- **답변 맨 끝에 `## 확인 항목` 을 붙인다.** 사람이 이 결과가 맞는지 판정할 수 있는 항목을
  5~8개, 아래 형식 그대로 적는다. "잘 됐나요?" 가 아니라 **하나씩 O/X 로 답할 수 있는 문장**이어야 한다.

## 확인 항목
- [ ] (판정 가능한 문장 하나)
- [ ] (또 하나)

  좋은 항목: "키는 1주문 1키로 판매한다 — 수량 선택 없음", "환불은 키 미열람 상태에서만 허용한다"
  나쁜 항목: "설계가 적절한가", "구현 가능한가" (판정 기준이 없다)
  네가 세운 **가정**이 있으면 그 가정을 확인 항목으로 올려라 — 가정이 틀리면 결과가 통째로 바뀐다."""

MOCKUP_EXTRA = """- **이건 목업이다.** 실제 동작·API 연동·테스트는 필요 없다. 화면이 보이면 된다.
- 화면 어딘가에 **목업임을 알리는 표시**를 반드시 넣는다(배너 등). 진짜 서비스로 오인되면 안 된다.
- 기존 스토어의 톤앤매너·컴포넌트·SCSS 규칙을 따른다. 새 디자인 언어를 만들지 마라.
- **front-end/ 안에서만** 변경한다. 백엔드는 건드리지 마라.

- **답변 맨 끝에 적용 가능한 패치를 붙인다.** 형식은 아래를 정확히 지킨다.

```diff
diff --git a/front-end/src/... b/front-end/src/...
--- a/front-end/src/...
+++ b/front-end/src/...
@@ -<시작>,<줄수> +<시작>,<줄수> @@
 (문맥)
+추가
```

  * 새 파일은 `--- /dev/null` 과 `+++ b/<경로>` 로 시작하고 모든 줄을 `+` 로 적는다.
  * 기존 파일의 문맥 줄은 원문과 한 글자도 달라선 안 된다.
  * 새로 만든 라우트 경로를 답변 본문에 **한 줄로 명시**한다 — 그래야 미리보기에서 찾아갈 수 있다."""


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

- **"이곳뿐 / 전부 / 없다" 류의 단정을 했다면 그 근거 명령을 남긴다.**
  `## 전수 조사` 섹션에 실제로 돌린 검색을 그대로 적는다. 이 명령은 **다시 실행되어 대조된다.**
  적지 않고 단정하면 근거 없는 주장으로 취급한다.

  ## 전수 조사
  ```bash
  grep -rli "rights reserved" front-end/src
  grep -rli "rights reserved" front-end/public
  ```
  각 명령 아래에 그 검색으로 무엇을 확인했는지 한 줄로 적는다.

  주의:
  - `grep` / `rg` / `git grep` 만 실행된다. 파이프·리다이렉트는 실행되지 않는다.
  - 경로는 레포 루트 기준 상대 경로로 쓴다.
  - **`src` 만 보고 "전부 확인했다" 고 하지 마라.** `public/` 아래 정적 사이트도 같은 레포다
    (실제 사례: 저작권 연도를 `src` 에서 1곳만 찾고 "이 한 곳뿐" 이라 썼는데 `public` 에 19곳이 더 있었다).

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


#: 에이전트 모드(작업장) 사용 여부. 프로젝트에 레포 미러가 있고 dev 팀 작업일 때만 적용된다.
AGENTIC = os.environ.get("NEWPLAY_AGENTIC", "1") != "0"

AGENTIC_EXTRA = """- **너는 지금 이 레포의 격리된 작업 복사본(worktree) 안에 있다.** 파일을 직접 읽고, 직접 고쳐라.
  diff 를 글로 쓰지 말고 실제로 편집한다. 필요한 곳은 전부 고친다(백엔드·프런트 양쪽 표면).
- 고치기 전에 관련 파일을 먼저 읽어 현재 구현을 확인한다. 위 지식베이스 조각은 출발점일 뿐 전부가 아니다.
- 검사 명령이 있으면 돌려 보고 결과를 요약에 적는다. 의존성이 없어 못 돌리면 그 사실을 적는다.
- **git commit / push / checkout / reset 은 하지 마라.** 커밋과 반출은 사람이 결과를 고른 뒤 플랫폼이 한다.
- 레포 밖 파일·시스템 설정은 건드리지 마라.
- 끝나면 아래 형식의 마크다운만 최종 답으로 낸다 (편집 로그가 아니라 결론):

## 변경 요약
- 무엇을 왜 바꿨는지 3~8줄. 건드린 파일마다 한 줄.

## 영향 범위
| 표면 | 해당 파일 | 이번에 고침 | 안 고치면 남는 문제 |

## 검사
- 실행한 명령과 결과 (못 돌렸으면 이유)

## 확인 항목
- [ ] (사람이 O/X 로 판정할 수 있는 문장) × 5~8"""


def _project_doc(name: str) -> dict[str, Any]:
    try:
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        try:
            return cli[DB_NAME]["hermes_projects"].find_one({"project": name}) or {}
        finally:
            cli.close()
    except Exception:  # noqa: BLE001
        return {}


def _overlap_warning(task_id: str, project: str, files: list[str]) -> list[dict[str, Any]]:
    """같은 프로젝트에서 진행 중이거나 검수 대기 중인 다른 작업이 같은 파일을 건드렸는지."""
    if not files:
        return []
    try:
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        try:
            col = cli[DB_NAME]["pixelforge_tasks"]
            from bson import ObjectId
            others = col.find({"_id": {"$ne": ObjectId(task_id)}, "project": project,
                               "status": {"$in": ["in_progress", "review"]},
                               "touched_files": {"$in": files}},
                              {"title": 1, "touched_files": 1, "created_by_email": 1, "branch": 1})
            out = []
            for o in others:
                shared = sorted(set(files) & set(o.get("touched_files") or []))
                if shared:
                    out.append({"task_id": str(o["_id"]), "title": o.get("title", ""),
                                "owner": o.get("created_by_email", ""), "branch": o.get("branch", ""),
                                "files": shared})
            return out
        finally:
            cli.close()
    except Exception as e:  # noqa: BLE001
        log.warning("겹침 조회 실패(무시): %s", e)
        return []


def _run_work_agentic(task: dict[str, Any], context: dict[str, Any], team: str, sub: str,
                      tr: dict[str, Any], writer, task_id: str, role: str, kb: str,
                      proj: dict[str, Any]) -> dict[str, Any]:
    """작업장 경로: worktree 생성 → 에이전트 실행(파일 직접 편집) → diff·검사·커밋 → 겹침 경고 → 검수 큐."""
    project = str(task.get("project") or "")
    repo = proj.get("repo") or {}
    default_branch = str(repo.get("default_branch") or "main")
    actor = agent_team.current_actor()

    ok, note = workspace.ensure_origin(project, default_branch)
    if not ok:
        _comment(writer, task_id, f"⚠️ 작업장 준비 실패({note}) — 제안 모드로 진행합니다.")
        return {}
    wt = workspace.create_worktree(project, task_id, actor, default_branch)
    if not wt.get("ok"):
        _comment(writer, task_id, f"⚠️ {wt.get('error')} — 제안 모드로 진행합니다.")
        return {}
    _persist(task, writer, task_id, {"worktree": wt["path"], "branch": wt["branch"], "base_rev": wt["base"],
                                     "workspace_at": datetime.now(timezone.utc).isoformat()})

    checks = list(((proj.get("workspace") or {}).get("checks")) or [])
    # ── 대리 모드("○○처럼"): 담당자의 프로필을 입는다. 계정은 여전히 요청자 것(actor). 설계서 §6-3.
    act_as = str(task.get("act_as") or "").lower().strip()
    if not act_as and str(task.get("mode") or "") == "proxy":
        try:
            import profiles as _pf
            act_as = _pf.owner_for(project, newplay_kb.paths(_search_query(task, context), top=6)) or ""
            if act_as:
                _persist(task, writer, task_id, {"act_as": act_as, "act_as_auto": True})
                _comment(writer, task_id, f"👤 담당 영역으로 보아 **{act_as}** 처럼 작업합니다 (자동 지정).")
        except Exception as e:  # noqa: BLE001
            log.warning("담당자 자동 지정 실패(무시): %s", e)
    profile_block = ""
    if act_as:
        # 본인이 대리 작업을 꺼두었거나 프로필이 없으면 그 사람 이름으로 일하지 않는다(라벨·검사 습관 모두 쓰지 않음).
        try:
            import profiles as _pf
            prof = _pf.get(act_as, project)
        except Exception as e:  # noqa: BLE001
            log.warning("프로필 조회 실패(무시): %s", e)
            prof = {}
        if not prof or prof.get("enabled") is False:
            why = "대리 작업을 꺼두셨습니다" if prof else "아직 작업 프로필이 없습니다"
            _comment(writer, task_id, f"ℹ️ **{act_as}** 님은 {why} — 그 사람 이름을 붙이지 않고 일반 개발자로 작업합니다.")
            _persist(task, writer, task_id, {"act_as_declined": act_as, "act_as": "", "mode": "delegate"})
            task["act_as"] = ""; task["mode"] = "delegate"   # 뒤에서 다시 저장할 때 proxy 로 되돌아가지 않도록
            act_as = ""
        else:
            try:
                profile_block = _pf.as_prompt_block(act_as, project, _pf.exemplar_diffs(act_as, project))
                pchecks = _pf.safe_checks(list(prof.get("checks") or []))
                seen = {c.get("cmd") for c in checks}
                checks += [c for c in pchecks if c.get("cmd") and c.get("cmd") not in seen][:4]
                if profile_block:
                    kb = kb + "\n\n" + profile_block
            except Exception as e:  # noqa: BLE001
                log.warning("프로필 블록 실패(무시): %s", e)
    check_hint = ("\n검사 명령: " + "; ".join(f"`{c.get('cmd')}` (cwd {c.get('cwd') or '.'})" for c in checks)) if checks else ""
    prompt = WORK_PROMPT.format(
        title=task.get("title", ""),
        description=task.get("description", "") or "(없음)",
        enriched=tr.get("enriched") or "(없음)",
        history=_history(context),
        kb=kb,
        extra=AGENTIC_EXTRA + check_hint,
    )
    role_label = f"proxy:{act_as}" if act_as else role
    timeout = int(os.environ.get("NEWPLAY_AGENT_TIMEOUT", "1800"))
    _comment(writer, task_id, f"🛠️ **{role}** 작업장에서 실행 중… (브랜치 `{wt['branch']}`, 기준 `{wt['base']}`, 최대 {timeout // 60}분)")
    # 실행 동안 20초마다 터치셋을 기록하고, 다른 활성 작업과 파일이 겹치면 그 즉시 양쪽에 알린다 (감시자의 기계 층)
    with overlap.LiveTouchWatcher(task_id, project, wt["path"],
                                  persist=lambda f: _persist(task, writer, task_id, f),
                                  comment=lambda tid, text: _comment(writer, tid, text),
                                  title=str(task.get("title") or "")):
        resp = agent_team.invoke_agentic(role, prompt, cwd=wt["path"], timeout=timeout)
    agent_team.log_session(task, role, resp, prompt)
    if not resp.success:
        _comment(writer, task_id, f"❌ {role} 실패: {resp.error[:400]}")
        return {"success": False, "error": resp.error or f"{role} failed", "next_status": "review"}

    body = (resp.output or "").strip() or "(빈 응답)"
    diff, files = workspace.stage_and_diff(wt["path"])
    results = workspace.run_checks(wt["path"], checks) if checks else []
    sha = workspace.commit(wt["path"], f"[{task_id[-8:]}] {str(task.get('title') or '')[:60]}\n\nProjectHub task: {task_id}\nBy: {actor or 'ai'}", actor) if diff else ""
    meta = resp.structured or {}
    _persist(task, writer, task_id, {
        "deliverable": body[:60000], "deliverable_role": role_label,
        "deliverable_at": datetime.now(timezone.utc).isoformat(),
        "acceptance_criteria": _extract_criteria(body),
        "touched_files": files, "proposed_patch": diff[:400000], "patch_files": files,
        "patch_role": role_label, "patch_at": datetime.now(timezone.utc).isoformat(),
        "mode": ("proxy" if act_as else str(task.get("mode") or "delegate")),
        "commit": sha, "checks": results, "agent_meta": meta,
    })

    # ── 겹침 판정: 파일 겹침은 경고, 같은 줄 구간 겹침은 충돌(머지 보류). 충돌일 때만 감시자 LLM 이 요약한다.
    my_hunks = workspace.hunks(wt["path"], wt["base"]) if diff else {}   # 커밋 뒤라 base 기준으로
    _persist(task, writer, task_id, {"hunks": {k: [list(x) for x in v] for k, v in my_hunks.items()}})
    overlaps = overlap.conflicts(task_id, project, my_hunks) if my_hunks else _overlap_warning(task_id, project, files)
    merge_hold = any(o.get("conflict") for o in overlaps)
    if overlaps:
        _persist(task, writer, task_id, {"overlaps": overlaps, "merge_hold": merge_hold})
        lines = [("⛔ **구간 충돌** — 같은 파일의 같은 줄을 고친 진행 중 작업이 있습니다. 머지 보류 상태로 두었습니다. 회의장에서 순서를 정하세요."
                  if merge_hold else "⚠️ **겹침 경고** — 같은 파일을 건드리는 진행 중 작업이 있습니다. 머지 전에 순서를 정하세요.")]
        for o in overlaps:
            mark = "⛔" if o.get("conflict") else "⚠️"
            lines.append(f"- {mark} `{o['task_id'][-8:]}` {o['title'][:40]} ({o['owner'] or '?'}, `{o['branch']}`): " + ", ".join((o.get('conflict_files') or o['files'])[:6]))
            _comment(writer, o["task_id"], f"{mark} 겹침: `{task_id[-8:]}` {str(task.get('title') or '')[:40]} 이(가) 같은 파일을 건드렸습니다: " + ", ".join(o['files'][:6]))
        _comment(writer, task_id, "\n".join(lines))
        if merge_hold:
            try:
                other = next(o for o in overlaps if o.get("conflict"))
                cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
                try:
                    from bson import ObjectId
                    od = cli[DB_NAME]["pixelforge_tasks"].find_one({"_id": ObjectId(other["task_id"])}, {"proposed_patch": 1, "title": 1}) or {}
                finally:
                    cli.close()
                note = overlap.assess_with_llm(diff, str(od.get("proposed_patch") or ""), str(task.get("title") or ""), str(od.get("title") or ""), agent_team.invoke)
                _persist(task, writer, task_id, {"guard_note": note})
                _comment(writer, task_id, "🛡️ **감시자 판정**\n" + note)
            except Exception as e:  # noqa: BLE001
                log.warning("감시자 판정 실패(무시): %s", e)

    header = ((f"### 👤 {act_as} 처럼 작업 (요청 {actor or '?'}) — {role}" if act_as else f"### 🛠️ {role}") + f" 결과 ({resp.model}, {resp.duration_sec:.0f}s"
              + (f", {meta.get('num_turns')}턴" if meta.get('num_turns') else "") + ")"
              + f"\n\n> 브랜치 `{wt['branch']}`" + (f" · 커밋 `{sha}`" if sha else " · **변경 없음**")
              + f" · 파일 {len(files)}개" + (" · " + ", ".join(f"{'✅' if r['ok'] else '❌'} {r['name']}" for r in results) if results else "")
              + "\n> 자동 머지 없음 — **결과를 확인하고 채택하면** 그때 반출됩니다.")
    _comment(writer, task_id, f"{header}\n\n{_comment_body(body)}")
    if results:
        _comment(writer, task_id, workspace.checks_block(results))

    review_body = body + ("\n\n## 실제 diff (요약)\n```diff\n" + diff[:20000] + "\n```" if diff else "\n\n(파일 변경 없음)")
    queued = _enqueue_review(task, team, sub, role, review_body, kb + "\n\n" + workspace.checks_block(results), task_id,
                             enriched=tr.get("enriched") or "")
    return {"success": True, "summary": f"{team}/{sub} — {role} 작업장 완료 · 파일 {len(files)}개" + (" · 검수 대기" if queued else ""),
            "next_status": "review",
            "metadata": {"team": team, "sub_team": sub, "role": role, "model": resp.model,
                         "branch": wt["branch"], "files": len(files), "review_queued": queued}}


def _run_work(task: dict[str, Any], context: dict[str, Any], team: str, sub: str,
              tr: dict[str, Any], writer, task_id: str) -> dict[str, Any]:
    role = SUB_ROLE.get(team, {}).get(sub) or SUB_ROLE.get(team, {}).get("general")
    if not role:
        return {"success": False, "error": f"{team}/{sub} 에 매핑된 역할이 없습니다", "next_status": "review"}

    query = _search_query(task, context)
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

    # 최신 지시 전용 검색 — 티켓 주제와 별개로 한 번 더 찾는다.
    #
    # 질의에 코멘트를 이어 붙이는 것만으로는 부족했다(실측): 제목+본문이 길면
    # 임베딩이 그쪽으로 쏠려서 나중에 온 지시가 묻힌다.
    # 분과/전체 이중 검색과 같은 논리다 — 한 번의 검색으로 두 관심사를 동시에
    # 만족시키려 하면 둘 다 어중간해진다.
    _latest = str(context.get("last_user_reply") or "").strip()
    if len(_latest) >= 15:
        latest_block = newplay_kb.as_prompt_block(_latest[:600], top=4)
        if latest_block:
            kb += ("\n\n## 가장 최근 지시로 따로 찾은 코드\n"
                   "(티켓 제목이 아니라 **마지막 코멘트** 를 기준으로 검색한 결과다. "
                   "요청이 도중에 바뀌었다면 이쪽이 맞는 근거다.)\n\n" + latest_block)
    if not kb:
        kb = "## 관련 코드\n(지식베이스 검색 결과 없음 — 코드 근거 없이 답하고 있음을 명시할 것)"

    # 되먹임: 사람이 채택한 과거 작업의 결정 메모 중 유사한 것을 붙인다 (거부된 결과는 여기 없다).
    try:
        mem = learning.similar_memos(str(task.get("project") or ""), query)
        if mem:
            kb = kb + "\n\n" + mem
    except Exception as e:  # noqa: BLE001
        log.warning("유사 메모 주입 실패(무시): %s", e)

    # 검색이 잡아준 파일들의 **미러 짝**을 사실 관계로 덧붙인다.
    # 검색은 유사도라 반대편 표면을 놓칠 수 있다(실측: paymentMethodName.ts 누락).
    # 미러 그래프는 "같은 상수값을 공유한다"는 결정적 근거라 성격이 다르다.
    # dev 에만 붙인다 — 미러는 "두 구현 중 한쪽만 고쳤나"를 묻는 것이라
    # 구현을 고치지 않는 일(로그 설계·기획 문서)에는 해당이 없다.
    if team == "dev":
        try:
            hit_paths = newplay_kb.paths(query, top=6)
            mirror = mirror_lookup.as_prompt_block(hit_paths)
            if mirror:
                kb = kb + "\n\n" + mirror
        except Exception as e:  # noqa: BLE001
            log.warning("미러 블록 생성 실패(무시): %s: %s", type(e).__name__, e)

    # ── 작업장 경로: dev 작업이고 프로젝트에 레포 미러가 있으면 worktree 안에서 도구를 쓰며 일한다.
    # 목업·비dev 작업과 레포 없는 프로젝트는 예전 제안 모드 그대로.
    if AGENTIC and team == "dev" and not task.get("mockup_of") and task.get("project"):
        proj = _project_doc(str(task.get("project")))
        if (proj.get("repo") or {}).get("dir") or os.path.isdir(workspace.project_paths(str(task.get("project")))["mirror"]):
            res = _run_work_agentic(task, context, team, sub, tr, writer, task_id, role, kb, proj)
            if res:
                return res

    prompt = WORK_PROMPT.format(
        title=task.get("title", ""),
        description=task.get("description", "") or "(없음)",
        enriched=tr.get("enriched") or "(없음)",
        history=_history(context),
        kb=kb,
        extra=(MOCKUP_EXTRA if task.get("mockup_of") else (DEV_EXTRA if team == "dev" else "")),
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

    # 산출물과 확인 항목을 태스크에 구조화해 저장한다.
    # 코멘트에만 두면 긴 문서가 스크롤에 묻혀 읽기도 판정하기도 어렵다.
    criteria = _extract_criteria(body)
    _persist(task, writer, task_id, {
        "deliverable": body[:60000],
        "deliverable_role": role,
        "deliverable_at": datetime.now(timezone.utc).isoformat(),
        "acceptance_criteria": criteria,
    })

    # ── 기계 검증: 인용한 줄을 실제로 열고, 패치를 실제로 적용해 본다.
    # LLM 검수 앞에 두는 이유는 두 가지다.
    #   1. 검수자가 파일 대조에 시간을 쓰지 않아도 된다 — 사실은 이미 표로 와 있다
    #   2. 기계가 확실히 아는 것(패치가 안 붙는다)을 문장 읽기로 판정하게 두지 않는다
    # 실패해도 작업을 죽이지 않는다. 어디까지나 보조 근거다.
    gate_block = ""
    if team == "dev":
        try:
            gres = fact_gate.check(body)
            gate_block = fact_gate.as_prompt_block(gres)
            _persist(task, writer, task_id, {
                "fact_gate": {
                    "repo_rev": gres.get("repo_rev"),
                    "citations": len(gres.get("citations") or []),
                    "bad_citations": gres.get("bad_citations"),
                    "patches": len(gres.get("patches") or []),
                    "bad_patches": gres.get("bad_patches"),
                    "hard_failures": gres.get("hard_failures"),
                    "at": datetime.now(timezone.utc).isoformat(),
                },
            })
            if gres.get("hard_failures"):
                _comment(writer, task_id,
                         f"🔎 **기계 검증** (레포 `{gres.get('repo_rev')}`): "
                         f"확인 불가·불일치 {gres['hard_failures']}건 발견 — 검수에 함께 전달합니다.\n\n"
                         + gate_block[:4000])
        except Exception as e:  # noqa: BLE001
            log.warning("기계 검증 실패(무시): %s: %s", type(e).__name__, e)

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

    _comment(writer, task_id, f"{header}\n\n{_comment_body(body)}")

    # ── 검수는 전용 풀로 넘기고 슬롯을 즉시 반납한다.
    # 여기서 기다리면 코더 342초 + 검수 158초 = 500초 동안 슬롯 하나가 잠긴다(실측).
    # 검수자에게 코드 근거와 함께 **기계가 확인한 사실**을 넘긴다.
    # 이게 있으면 검수는 대조가 아니라 판단에 집중할 수 있다.
    review_kb = (kb + "\n\n" + gate_block) if gate_block else kb
    queued = _enqueue_review(task, team, sub, role, body, review_kb, task_id,
                             enriched=tr.get("enriched") or "")

    return {
        "success": True,
        "summary": f"{team}/{sub} — {role} 완료" + (" · 검수 대기" if queued else ""),
        "next_status": "review",
        "metadata": {"team": team, "sub_team": sub, "role": role,
                     "model": resp.model, "review_queued": queued},
    }


# ─────────────────────────────────────────────────────────── 검수 큐
# 검수 전용 스레드 풀. 메인 워커 슬롯(HERMES_WORKER_SLOTS)과 **분리**돼 있어
# 검수가 아무리 오래 걸려도 새 태스크 처리를 막지 않는다.
_REVIEW_SLOTS = int(os.environ.get("NEWPLAY_REVIEW_SLOTS", "2"))
_REVIEW_POOL = ThreadPoolExecutor(max_workers=_REVIEW_SLOTS, thread_name_prefix="newplay-review")
_REVIEW_COL = "newplay_review_queue"
_recovered = False
_recover_lock = threading.Lock()


def _mark_review(task_id: str, status: str, verdict: str = "") -> None:
    """검수 진행 상태를 태스크 문서에 남긴다.

    화면이 이 필드를 읽어 '검수 중 / 통과 / 보완 필요'를 보여준다.
    실패해도 조용히 넘어간다 — 표시용이라 본 작업을 막을 이유가 없다.
    """
    try:
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        doc = {"review_status": status,
               "review_at": datetime.now(timezone.utc).isoformat()}
        if verdict:
            doc["review_verdict"] = verdict
        from bson import ObjectId as _OID
        try:
            key = {"_id": _OID(str(task_id))}
        except Exception:  # noqa: BLE001
            key = {"_id": task_id}
        cli[DB_NAME]["pixelforge_tasks"].update_one(key, {"$set": doc})
        cli.close()
    except Exception as e:  # noqa: BLE001
        log.debug("검수 상태 기록 실패(무시): %s: %s", type(e).__name__, e)


def _queue_col():
    cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return cli, cli[DB_NAME][_REVIEW_COL]


def _enqueue_review(task: dict[str, Any], team: str, sub: str, worker: str,
                    result: str, kb: str, task_id: str,
                    rnd: int = 0, history: list[dict[str, Any]] | None = None,
                    enriched: str = "") -> bool:
    """검수를 큐에 넣고 전용 풀에 던진다.

    Mongo 에도 남기는 이유: 프로세스 안 큐만 쓰면 워처 재시작 시 검수가 통째로 사라진다.
    사용자 입장에서는 "검수 대기" 라고 써놓고 영영 안 오는 상태가 된다.
    """
    rrole = (REVIEW_ROLE.get(team) or {}).get(sub, (REVIEW_ROLE.get(team) or {}).get("general"))
    if not rrole or rrole == worker:
        return False
    try:
        cli, col = _queue_col()
        doc = {
            "task_id": task_id,
            "task_title": task.get("title", ""),
            "team": team, "sub_team": sub,
            "worker_role": worker, "review_role": rrole,
            "result": result[:60000], "kb": kb[:40000],
            "mockup_of": task.get("mockup_of"),
            "status": "pending",
            # 재작업이 원본 요청을 다시 읽어야 해서 함께 넣는다.
            # (검수도 지금까지 description 없이 판정하고 있었다 — 같이 고친다)
            "description": (task.get("description") or "")[:6000],
            "enriched": enriched[:3000],
            "round": rnd,
            "history": history or [],
            # 검수도 같은 사람 계정으로 — 검수 풀은 다른 스레드라 여기 적어 넘긴다
            "actor": agent_team.current_actor(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        qid = col.insert_one(doc).inserted_id
        cli.close()
    except Exception as e:  # noqa: BLE001
        log.warning("검수 큐 적재 실패(동기 폴백): %s: %s", type(e).__name__, e)
        return False

    _mark_review(task_id, "pending")
    _REVIEW_POOL.submit(_run_queued_review, str(qid))
    _ensure_recovery()
    return True


def _run_queued_review(qid: str) -> None:
    """큐 항목 하나를 검수한다. 실패해도 절대 raise 하지 않는다."""
    from bson import ObjectId
    from projecthub_writer import ProjectHubWriter as _PHW
    cli = None
    try:
        cli, col = _queue_col()
        oid = ObjectId(qid)
        # 원자적 클레임 — 재개 로직과 중복 실행되지 않게
        doc = col.find_one_and_update(
            {"_id": oid, "status": "pending"},
            {"$set": {"status": "running", "claimed_at": datetime.now(timezone.utc).isoformat()}},
        )
        if not doc:
            return
        agent_team.set_actor(str(doc.get("actor") or ""))
        _mark_review(doc["task_id"], "running")

        writer = _PHW(cli[DB_NAME]["pixelforge_tasks"])
        task = {"_id": doc["task_id"], "title": doc.get("task_title", ""),
                "description": doc.get("description", ""), "mockup_of": doc.get("mockup_of")}
        res = _review(task, doc["team"], doc["sub_team"], doc["worker_role"],
                      doc.get("result", ""), doc.get("kb", ""), writer, doc["task_id"])
        verdict = str(res.get("verdict") or "")
        # 기계 지표를 함께 쌓는다 — 정체 판정을 LLM 점수에만 기대면 노이즈에 흔들린다
        # (실측: 같은 입력에 52점 / 70점).
        try:
            _g = fact_gate.check(doc.get("result", "")) if doc.get("team") == "dev" else {}
        except Exception:  # noqa: BLE001
            _g = {}
        history = list(doc.get("history") or []) + [{
            "round": int(doc.get("round", 0)),
            "verdict": verdict,
            "score": res.get("score"),
            "issues": res.get("issues") or [],
            "gate": {"hard": _g.get("hard_failures"), "bad_cites": _g.get("bad_citations")},
        }]
        col.update_one({"_id": oid}, {"$set": {
            "status": "done", "verdict": verdict, "score": res.get("score"),
            "history": history,
            "finished_at": datetime.now(timezone.utc).isoformat()}})
        _mark_review(doc["task_id"], "done", verdict)
        _maybe_rework(col, doc, res, history, writer)
    except Exception as e:  # noqa: BLE001
        log.exception("검수 큐 처리 실패: %s", qid)
        try:
            _d = locals().get("doc")
            if _d:
                _mark_review(_d["task_id"], "failed")
        except Exception:  # noqa: BLE001
            pass
        try:
            if cli is not None:
                from bson import ObjectId as _OID
                cli[DB_NAME][_REVIEW_COL].update_one(
                    {"_id": _OID(qid)},
                    {"$set": {"status": "failed", "error": f"{type(e).__name__}: {e}"[:400]}})
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            if cli is not None:
                cli.close()
        except Exception:  # noqa: BLE001
            pass


# ─────────────────────────────────────────────────── 자동 재작업
# 검수 지적을 코더에게 되먹여 다시 작업시킨다.
#
# 근거(실측): 지적 6건을 되먹였더니 55점 → 91점, 라이브에서도 64점 → 87점.
#            한 사이클로 반려가 통과가 된다. 그 되먹임을 사람이 손으로 돌리고 있었을 뿐이다.
#
# 전용 풀을 쓰는 이유: 재작업 한 번이 코더 300초 + 검수 180초다.
#   메인 워커 슬롯(2개)에서 돌리면 새 작업 처리가 통째로 막히고,
#   검수 풀을 같이 쓰면 긴 코더 호출이 검수를 굶긴다.
AUTO_REWORK = os.environ.get("NEWPLAY_AUTO_REWORK", "1") != "0"
REWORK_MAX_ROUNDS = int(os.environ.get("NEWPLAY_REWORK_MAX_ROUNDS", "2"))
#: 이만큼도 안 오르면 같은 자리를 맴도는 것으로 본다.
REWORK_MIN_GAIN = float(os.environ.get("NEWPLAY_REWORK_MIN_GAIN", "3"))
#: 재작업 시간 배수. 원 작업 상한에 곱한다(실측 근거는 _run_rework 주석 참조).
REWORK_TIMEOUT_FACTOR = float(os.environ.get("NEWPLAY_REWORK_TIMEOUT_FACTOR", "2.0"))
_REWORK_POOL = ThreadPoolExecutor(
    max_workers=int(os.environ.get("NEWPLAY_REWORK_SLOTS", "1")),
    thread_name_prefix="newplay-rework")


def _rework_stop_reason(doc: dict[str, Any], res: dict[str, Any],
                        history: list[dict[str, Any]]) -> str:
    """재작업을 멈춰야 하는 이유. 돌려도 되면 빈 문자열.

    멈추는 조건이 이 기능의 핵심이다 — 없으면 무한히 토큰을 태운다.
    """
    if not AUTO_REWORK:
        return ""                      # 꺼져 있으면 조용히 아무것도 안 한다
    v = str(res.get("verdict") or "")
    if v not in ("revise", "reject"):
        return ""                      # 통과했거나 판정 없음 — 재작업 대상이 아니다
    if not (res.get("issues") or []):
        return "지적 내용이 없어 무엇을 고쳐야 할지 알 수 없습니다"
    rnd = int(doc.get("round", 0))
    if rnd >= REWORK_MAX_ROUNDS:
        return f"{REWORK_MAX_ROUNDS}회 재작업했지만 통과하지 못했습니다"
    # 정체 판정 — **두 신호가 모두** 나빠졌을 때만.
    #
    # 검수 점수 하나로 판단하면 안 된다: 같은 산출물·같은 모델인데 52점과 70점이 나온다(실측).
    # 그 편차에 가드가 발동해 멀쩡한 재작업을 중단시켰다.
    # 기계 지표(하드 실패, 미해소 인용)는 같은 입력이면 같은 값이라 흔들리지 않는다.
    # 한쪽이라도 나아졌으면 한 번 더 준다 — 라운드 상한이 있어 최악의 경우는 그대로다.
    if len(history) >= 2:
        prev, cur = history[-2], history[-1]
        ps, cs = prev.get("score"), cur.get("score")
        score_stalled = (isinstance(ps, (int, float)) and isinstance(cs, (int, float))
                         and (cs - ps) < REWORK_MIN_GAIN)
        gate_stalled = _gate_defects(cur) >= _gate_defects(prev)
        if score_stalled and gate_stalled:
            return (f"재작업했지만 점수({ps} → {cs})도 기계 검증 결함"
                    f"({_gate_defects(prev)} → {_gate_defects(cur)})도 나아지지 않았습니다")
    return ""


def _gate_defects(h: dict[str, Any]) -> int:
    """그 회차의 기계로 확인된 결함 수. 없으면 비교에서 빠지도록 큰 값을 피해 0 을 쓴다."""
    g = h.get("gate") or {}
    return int(g.get("hard") or 0) + int(g.get("bad_cites") or 0)


def _maybe_rework(col, doc: dict[str, Any], res: dict[str, Any],
                  history: list[dict[str, Any]], writer) -> None:
    """검수 결과를 보고 재작업을 걸거나, 왜 멈추는지 남긴다."""
    v = str(res.get("verdict") or "")
    if v not in ("revise", "reject") or not AUTO_REWORK:
        return
    stop = _rework_stop_reason(doc, res, history)
    if stop:
        _comment(writer, doc["task_id"],
                 f"🛑 **자동 재작업 중단** — {stop}. 사람 검수로 넘깁니다.\n\n"
                 + _history_table(history))
        _mark_review(doc["task_id"], "needs_human", v)
        return
    try:
        nxt = col.insert_one({
            **{k: doc[k] for k in ("task_id", "task_title", "team", "sub_team",
                                   "worker_role", "review_role", "kb", "mockup_of",
                                   "description", "enriched") if k in doc},
            "status": "rework_pending",
            "round": int(doc.get("round", 0)) + 1,
            "history": history,
            "issues": res.get("issues") or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).inserted_id
    except Exception as e:  # noqa: BLE001
        log.warning("재작업 적재 실패: %s: %s", type(e).__name__, e)
        return
    rnd = int(doc.get("round", 0)) + 1
    _comment(writer, doc["task_id"],
             f"🔁 **자동 재작업 {rnd}/{REWORK_MAX_ROUNDS}회차 시작** — "
             f"검수 지적 {len(res.get('issues') or [])}건을 반영해 다시 작업합니다.")
    _mark_review(doc["task_id"], "reworking", v)
    _REWORK_POOL.submit(_run_rework, str(nxt))


def _history_table(history: list[dict[str, Any]]) -> str:
    L = ["| 회차 | 판정 | 점수 | 지적 |", "|---|---|---|---|"]
    for h in history:
        L.append(f"| {h.get('round', 0)} | {h.get('verdict') or '-'} | "
                 f"{h.get('score') if h.get('score') is not None else '-'} | "
                 f"{len(h.get('issues') or [])}건 |")
    return "\n".join(L)


def _run_rework(qid: str) -> None:
    """지적을 반영해 다시 작업하고, 결과를 다시 검수 큐에 올린다. 절대 raise 하지 않는다."""
    from bson import ObjectId
    from projecthub_writer import ProjectHubWriter as _PHW
    cli = None
    try:
        cli, col = _queue_col()
        oid = ObjectId(qid)
        doc = col.find_one_and_update(
            {"_id": oid, "status": "rework_pending"},
            {"$set": {"status": "reworking",
                      "claimed_at": datetime.now(timezone.utc).isoformat()}})
        if not doc:
            return

        writer = _PHW(cli[DB_NAME]["pixelforge_tasks"])
        task_id = doc["task_id"]
        team, sub = doc["team"], doc["sub_team"]
        role = doc["worker_role"]
        rnd = int(doc.get("round", 1))

        issues = doc.get("issues") or []
        feedback = ("검수에서 아래가 지적됐다. **전부 해소해서 다시 낸다.**\n"
                    "지적을 반박하려면 반박 근거를 파일·줄 번호로 제시한다. 무시하지 않는다.\n\n"
                    + "\n".join(f"{i}. {x}" for i, x in enumerate(issues, 1)))

        prompt = WORK_PROMPT.format(
            title=doc.get("task_title", ""),
            description=doc.get("description") or "(없음)",
            enriched=doc.get("enriched") or "(없음)",
            history=feedback,
            kb=doc.get("kb", ""),
            extra=(MOCKUP_EXTRA if doc.get("mockup_of") else (DEV_EXTRA if team == "dev" else "")),
        )
        # 재작업은 원 작업보다 오래 걸린다 — 원래 요구사항에 더해 지적 N건을 동시에 만족시켜야 한다.
        # 실측: 원 작업 659초였는데 재작업이 dev 상한 900초를 넘겨 타임아웃 났다.
        # 멈춰야 할 이유(품질 정체)가 아닌데 멈추면 루프가 무의미해진다.
        timeout = int({"design": 1500, "data": 1200, "dev": 900}.get(team, 900)
                      * REWORK_TIMEOUT_FACTOR)
        resp = agent_team.invoke(role, prompt, timeout=timeout)
        agent_team.log_session({"_id": task_id, "title": doc.get("task_title", "")},
                               role, resp, prompt)

        if not resp.success:
            col.update_one({"_id": oid}, {"$set": {"status": "failed",
                                                   "error": (resp.error or "")[:400]}})
            _comment(writer, task_id,
                     f"🛑 **자동 재작업 중단** — 재작업 실행이 실패했습니다: {(resp.error or '')[:200]}. "
                     "직전 결과는 그대로 두고 사람 검수로 넘깁니다.")
            _mark_review(task_id, "needs_human")
            return

        body = (resp.output or "").strip() or "(빈 응답)"

        # 재작업 결과도 똑같이 기계 검증을 거친다 — 안 하면 새 산출물만 검증 없이 통과한다.
        gate_block = ""
        if team == "dev":
            try:
                gres = fact_gate.check(body)
                gate_block = fact_gate.as_prompt_block(gres)
                _persist({"_id": task_id}, writer, task_id, {"fact_gate": {
                    "repo_rev": gres.get("repo_rev"), "repo_date": gres.get("repo_date"),
                    "citations": len(gres.get("citations") or []),
                    "bad_citations": gres.get("bad_citations"),
                    "patches": len(gres.get("patches") or []),
                    "bad_patches": gres.get("bad_patches"),
                    "hard_failures": gres.get("hard_failures"),
                    "at": datetime.now(timezone.utc).isoformat()}})
            except Exception as e:  # noqa: BLE001
                log.warning("재작업 기계 검증 실패(무시): %s: %s", type(e).__name__, e)

        _persist({"_id": task_id}, writer, task_id, {
            "deliverable": body[:60000],
            "deliverable_role": role,
            "deliverable_at": datetime.now(timezone.utc).isoformat(),
            "acceptance_criteria": _extract_criteria(body),
            "rework_round": rnd,
        })
        if team == "dev":
            patch, pfiles = _extract_patch(body)
            if patch:
                _persist({"_id": task_id}, writer, task_id, {
                    "proposed_patch": patch, "patch_files": pfiles, "patch_role": role,
                    "patch_at": datetime.now(timezone.utc).isoformat()})

        _comment(writer, task_id,
                 f"### 🔁 재작업 {rnd}회차 결과 ({resp.model}, {resp.duration_sec:.0f}s)\n\n"
                 + _comment_body(body))

        col.update_one({"_id": oid}, {"$set": {
            "status": "reworked", "result": body[:60000],
            "finished_at": datetime.now(timezone.utc).isoformat()}})

        # 다시 검수로. round 를 넘겨 상한이 유지된다.
        review_kb = (doc.get("kb", "") + "\n\n" + gate_block) if gate_block else doc.get("kb", "")
        _enqueue_review({"title": doc.get("task_title", ""),
                         "description": doc.get("description", ""),
                         "mockup_of": doc.get("mockup_of")},
                        team, sub, role, body, review_kb, task_id,
                        rnd=rnd, history=doc.get("history") or [],
                        enriched=doc.get("enriched", ""))
    except Exception as e:  # noqa: BLE001
        log.exception("재작업 처리 실패: %s", qid)
        try:
            if cli is not None:
                from bson import ObjectId as _OID
                cli[DB_NAME][_REVIEW_COL].update_one(
                    {"_id": _OID(qid)},
                    {"$set": {"status": "failed", "error": f"{type(e).__name__}: {e}"[:400]}})
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            if cli is not None:
                cli.close()
        except Exception:  # noqa: BLE001
            pass


#: 큐 청소 주기(초). 재작업 한 사이클(코더 15분 + 검수 20분)보다 길게 잡을 이유가 없다.
_SWEEP_INTERVAL = int(os.environ.get("NEWPLAY_QUEUE_SWEEP_SEC", "600"))


def _ensure_recovery() -> None:
    """떠 있는 검수·재작업을 되살리는 청소 스레드를 띄운다(프로세스당 한 번).

    1회성이 아니라 **주기**여야 한다. 1회성이면 "새 검수가 적재될 때"만 돌아서,
    워처가 재작업 도중 죽고 그 뒤로 새 태스크가 안 들어오면 rework_pending 이 영영 방치된다.
    화면에는 "AI 재작업 중" 이 계속 떠 있어, 멈춘 것을 진행 중인 것처럼 보여준다.
    """
    global _recovered
    with _recover_lock:
        if _recovered:
            return
        _recovered = True

    def _loop() -> None:
        while True:
            try:
                _recover_reviews()
            except Exception:  # noqa: BLE001
                log.exception("큐 청소 실패(계속 진행)")
            time.sleep(_SWEEP_INTERVAL)

    threading.Thread(target=_loop, daemon=True, name="newplay-queue-sweep").start()


def _recover_reviews() -> None:
    try:
        cli, col = _queue_col()
        # running 인데 오래 방치된 것 = 죽은 프로세스가 물고 있던 것
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=40)).isoformat()
        col.update_many({"status": "running", "claimed_at": {"$lt": cutoff}},
                        {"$set": {"status": "pending"}})
        col.update_many({"status": "reworking", "claimed_at": {"$lt": cutoff}},
                        {"$set": {"status": "rework_pending"}})
        for d in col.find({"status": "pending"}).limit(20):
            _REVIEW_POOL.submit(_run_queued_review, str(d["_id"]))
        for d in col.find({"status": "rework_pending"}).limit(10):
            _REWORK_POOL.submit(_run_rework, str(d["_id"]))
        cli.close()
    except Exception as e:  # noqa: BLE001
        log.warning("검수 큐 재개 실패: %s: %s", type(e).__name__, e)


#: 검수에 넘길 산문 분량. 패치는 여기 포함되지 않는다(아래 설명 참조).
REVIEW_PROSE_CHARS = int(os.environ.get("NEWPLAY_REVIEW_PROSE_CHARS", "12000"))
#: 패치 분량 상한. 산문과 달리 **뒤에서 자르지 않고** 통째로 넣는 것이 목적이다.
REVIEW_PATCH_CHARS = int(os.environ.get("NEWPLAY_REVIEW_PATCH_CHARS", "24000"))


def _review_body(result: str) -> str:
    """검수에 넘길 본문. 산문은 줄이되 **패치는 자르지 않는다.**

    왜 이렇게까지 하나 (실측):
        예전에는 그냥 `result[:12000]` 이었다. 패치는 답변 끝에 붙는데
        산출물이 15,717자였던 날, backend diff(13,423자 지점)가 통째로 잘렸다.
        검수는 "backend 훅이 한 줄도 없다"고 반려했고 — 자기가 본 것은 맞았다 —
        그 오판이 재작업 정체 판정까지 발동시켰다.
        검수 대상의 본체는 패치다. 그걸 못 보게 하면 검수가 아니다.
    """
    if not result:
        return ""
    patch, _files = _extract_patch(result)
    if not patch:
        return result[:REVIEW_PROSE_CHARS + REVIEW_PATCH_CHARS]
    # 산문에서 diff 블록을 들어낸 뒤 줄인다 — 같은 내용을 두 번 넣지 않기 위해.
    prose = re.sub(r"```diff\s*\n.*?```", "\n(패치는 아래에 전문으로 첨부)\n", result, flags=re.S)
    if len(prose) > REVIEW_PROSE_CHARS:
        prose = prose[:REVIEW_PROSE_CHARS] + "\n\n…(설명이 길어 이후 생략)"
    return (prose + "\n\n## 첨부된 패치 전문\n"
            + "(검수는 이 패치를 근거로 판단한다. 잘리지 않은 전체다.)\n\n```diff\n"
            + patch[:REVIEW_PATCH_CHARS] + "\n```")


def _review(task: dict[str, Any], team: str, sub: str, worker: str, result: str,
            kb: str, writer, task_id: str) -> dict[str, Any]:
    """작업 결과를 검수 역할이 다시 본다. 실패해도 태스크를 죽이지 않는다(검수는 보조 게이트).

    판정만이 아니라 **지적과 점수까지** 돌려준다 — 자동 재작업이 그것을 입력으로 쓴다.
    지적 없이 "revise" 만 되먹이면 코더는 무엇을 고쳐야 할지 모른다.
    """
    rrole = (REVIEW_ROLE.get(team) or {}).get(sub, (REVIEW_ROLE.get(team) or {}).get("general"))
    if not rrole or rrole == worker:
        return {}

    # 목업 태스크(mockup_of 로 생성)는 기준이 다르다.
    tmpl = MOCKUP_REVIEW_PROMPT if task.get("mockup_of") else REVIEW_PROMPT
    prompt = tmpl.format(
        worker=worker,
        title=task.get("title", ""),
        description=task.get("description", "") or "(없음)",
        result=_review_body(result),
        kb=kb,
    )
    resp = agent_team.invoke(rrole, prompt, timeout=1200, want_json=True)
    agent_team.log_session(task, rrole, resp, prompt)
    if not resp.success:
        _comment(writer, task_id, f"⚠️ {rrole} 검수 실패: {resp.error[:200]} — 결과는 그대로 두고 사람 검수로 넘깁니다.")
        return {}

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
    return {"verdict": v, "score": score, "issues": issues,
            "comment": str(out.get("comment") or "")[:1200], "role": rrole}


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


def _extract_criteria(text: str) -> list[dict[str, Any]]:
    """`## 확인 항목` 아래의 `- [ ]` 목록을 뽑는다.

    사람이 O/X 로 판정할 수 있는 형태로 저장해 둔다 — 문서 전체를 읽고
    "잘 나왔나?" 를 묻는 것보다, 항목별로 맞다/틀리다를 찍는 편이 훨씬 정확하다.
    """
    if not text:
        return []
    m = re.search(r"##\s*확인\s*항목\s*\n(.*?)(?:\n##\s|\Z)", text, re.S)
    if not m:
        return []
    items = re.findall(r"^\s*[-*]\s*\[[ xX]?\]\s*(.+?)\s*$", m.group(1), re.M)
    out: list[dict[str, Any]] = []
    for idx, it in enumerate(items[:12]):
        t = it.strip()
        if len(t) < 4:
            continue
        out.append({"id": f"c{idx}", "text": t[:400], "state": "pending"})
    return out


def _persist(task: dict[str, Any], writer, task_id: str, patch: dict[str, Any]) -> None:
    try:
        writer.patch(task_id, patch)
    except Exception:  # noqa: BLE001
        log.exception("patch 실패")


def _kb_collection_for(project: str) -> str:
    doc = _project_doc(project) if project else {}
    return str(((doc.get("knowledge") or {}).get("collection")) or os.environ.get("NEWPLAY_KB_COLLECTION", "newplay_code_m3"))


def _learning_comment(task_id: str, text: str) -> None:
    try:
        from projecthub_writer import ProjectHubWriter
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        try:
            _comment(ProjectHubWriter(cli[DB_NAME]["pixelforge_tasks"]), task_id, text)
        finally:
            cli.close()
    except Exception as e:  # noqa: BLE001
        log.warning("학습 코멘트 실패(무시): %s", e)


# 되먹임 루프: 사람이 채택(selection.decision=accept)한 작업만 배운다. 워처 프로세스 안 데몬 스레드.
if os.environ.get("NEWPLAY_LEARNING", "1") != "0" and os.environ.get("NEWPLAY_LEARNING_THREAD", "1") != "0":
    try:
        learning.start_learning_thread(agent_team.invoke, agent_team.set_actor, _learning_comment, _kb_collection_for)
        log.info("학습 루프 시작 (채택된 작업 → 결정 메모 + 증분 재색인)")
    except Exception as _e:  # noqa: BLE001
        log.warning("학습 루프 시작 실패: %s", _e)


def execute_task(task: dict[str, Any], context: dict[str, Any],
                 route: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("_id"))
    # 이 작업의 Claude 호출은 **작업을 낸 사람의 계정**으로 나간다 (claude_pool). 없으면 팀 공용/CLI 로그인.
    agent_team.set_actor(str(task.get("created_by_email") or ""))
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
        query = _search_query(task, context)
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
        _comment(writer, task_id, f"### 💬 답변 ({resp.model})\n\n{_comment_body((resp.output or '').strip())}")
        return {"success": True, "summary": "chat 답변 완료", "next_status": "review"}

    sub = _pick_sub_team(task, team, writer, task_id)
    _persist(task, writer, task_id, {"sub_team": sub})
    return _run_work(task, context, team, sub, tr, writer, task_id)
