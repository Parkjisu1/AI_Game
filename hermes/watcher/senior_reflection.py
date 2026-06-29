"""
Senior Reflection — 작업 완료 후 추상화된 도메인 원칙을 추출해 누적.

failure_learning이 "같은 실수 반복 방지"를 다룬다면, 이 모듈은 "성공·실패 양쪽에서
일반화된 시니어 노하우"를 누적한다.

Trigger: Reviewer 점수 부여 후 또는 task done 시.
Storage: hermes_domain_principles 컬렉션.
Use: 새 task의 Lead 프롬프트에 같은 (team, sub_team) 원칙들 자동 주입.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("senior-reflection")

PRINCIPLES_COLLECTION = "hermes_domain_principles"
MAX_PRINCIPLES_PER_TASK = 3
MAX_PRINCIPLES_INJECTED = 5  # Lead 프롬프트에 한 번에 주입할 최대 원칙 수
MIN_SCORE_FOR_REFLECTION = 70  # 이 점수 미만이면 reflection 스킵 (학습 가치 낮음)


def _get_db():
    try:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            return None
        db_name = os.environ.get("MONGODB_DB", "aigame")
        return MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    except Exception:
        return None


def reflect_on_task(
    *,
    task_id: str,
    title: str,
    description: str,
    team: str,
    sub_team: str,
    verdict: str,
    score: Optional[int],
    files_changed: list[str],
    diff_summary: str,
    reviewer_notes: str,
) -> int:
    """
    작업 완료 후 senior_reflector 에이전트 호출 → principles 누적.
    반환: 저장된 원칙 수.
    """
    if score is not None and score < MIN_SCORE_FOR_REFLECTION:
        log.debug("[reflect] score %s < %s — skip", score, MIN_SCORE_FOR_REFLECTION)
        return 0

    db = _get_db()
    if db is None:
        return 0

    try:
        from agent_team import ExecutionEnv, invoke_agent, SENIOR_REFLECTION_TEMPLATE
        from pathlib import Path
    except Exception as e:
        log.warning("[reflect] import failed: %s", e)
        return 0

    prompt = SENIOR_REFLECTION_TEMPLATE.format(
        title=title or "(no title)",
        team=team or "?",
        sub_team=sub_team or "general",
        description=(description or "")[:1000],
        verdict=verdict or "?",
        score=score if score is not None else "?",
        files=", ".join((files_changed or [])[:10]) or "(none)",
        diff_summary=(diff_summary or "")[:1500],
        reviewer_notes=(reviewer_notes or "")[:800],
    )

    env = ExecutionEnv(
        mode="local", cwd=str(Path.home()), timeout_sec=90,
        task_id=task_id, task_title=title or "",
        team=team, sub_team=sub_team,
    )
    # 'senior_reflector' 역할 우선, 없으면 reviewer로 폴백
    resp = invoke_agent("senior_reflector", prompt, env)
    if not resp.success:
        log.info("[reflect] senior_reflector unavailable — fallback to reviewer")
        resp = invoke_agent("reviewer", prompt, env)
        if not resp.success:
            return 0

    out = resp.structured or {}
    principles = out.get("principles") or []
    if not isinstance(principles, list):
        return 0

    saved = 0
    now = datetime.now(timezone.utc).isoformat()
    for p in principles[:MAX_PRINCIPLES_PER_TASK]:
        if not isinstance(p, dict):
            continue
        text = (p.get("principle") or "").strip()
        if not text or len(text) > 400:
            continue
        # applies_to_teams 정규화 — list[str] 만 허용, "all"/원본 sub_team 자동 처리
        raw_atos = p.get("applies_to_teams") or []
        if not isinstance(raw_atos, list):
            raw_atos = []
        applies_to_teams = []
        for t in raw_atos:
            if not isinstance(t, str):
                continue
            v = t.strip().lower()
            if v and v != (sub_team or "general"):  # 본인 sub_team은 자동 포함이므로 제외
                applies_to_teams.append(v)
        # 비슷한 원칙 중복 방지 — 동일 (team, sub_team)에 같은 텍스트 있으면 카운트만 +1
        existing = db[PRINCIPLES_COLLECTION].find_one({
            "team": team, "sub_team": sub_team, "principle": text,
        })
        if existing:
            update_doc: dict[str, Any] = {
                "$inc": {"reinforced_count": 1},
                "$addToSet": {"task_ids": task_id},
                "$set": {"last_seen_at": now},
            }
            # applies_to_teams 누적 (새 reflection이 더 넓은 적용 범위 제안하면 합집합)
            if applies_to_teams:
                update_doc["$addToSet"] = {
                    "task_ids": task_id,
                    "applies_to_teams": {"$each": applies_to_teams},
                }
            db[PRINCIPLES_COLLECTION].update_one({"_id": existing["_id"]}, update_doc)
            continue
        db[PRINCIPLES_COLLECTION].insert_one({
            "team": team,
            "sub_team": sub_team or "general",
            "principle": text,
            "applies_to": (p.get("applies_to") or "")[:200],
            "applies_to_teams": applies_to_teams,
            "why": (p.get("why") or "")[:300],
            "task_ids": [task_id],
            "reinforced_count": 1,
            "created_at": now,
            "last_seen_at": now,
            "source_score": score,
        })
        saved += 1

    if saved:
        log.info("[reflect] %d new principles saved (team=%s sub=%s)", saved, team, sub_team)
    return saved


def load_principles_text(team: str, sub_team: str, limit: int = MAX_PRINCIPLES_INJECTED) -> str:
    """
    Lead 프롬프트에 주입할 누적 원칙 텍스트.
    우선순위:
      1. 같은 (team, sub_team) 원칙 (본인 sub_team이 직접 만든 것)
      2. 같은 team의 다른 sub_team에서 만들었지만 applies_to_teams에 본인을 포함하거나 "all"
      3. 같은 team의 general 원칙
    reinforced_count 큰 것 + 최근 것 우선. 텍스트 중복 제거.
    """
    db = _get_db()
    if db is None:
        return ""
    sub_team_norm = (sub_team or "general").lower()

    def _by_score(rows: list[dict]) -> list[dict]:
        return sorted(
            rows,
            key=lambda r: (int(r.get("reinforced_count", 1)), r.get("last_seen_at", "")),
            reverse=True,
        )

    try:
        # ① sub_team specific
        own_rows = list(
            db[PRINCIPLES_COLLECTION].find({"team": team, "sub_team": sub_team_norm})
            .sort([("reinforced_count", -1), ("last_seen_at", -1)])
        )
        # ② cross-team (같은 team이지만 다른 sub_team에서 본인을 applies_to_teams로 지목)
        cross_rows: list[dict] = []
        if len(own_rows) < limit:
            cross_rows = list(
                db[PRINCIPLES_COLLECTION].find({
                    "team": team,
                    "sub_team": {"$ne": sub_team_norm},
                    "applies_to_teams": {"$in": [sub_team_norm, "all"]},
                })
                .sort([("reinforced_count", -1), ("last_seen_at", -1)])
                .limit(limit * 2)
            )
        # ③ general 폴백
        general_rows: list[dict] = []
        if len(own_rows) + len(cross_rows) < limit and sub_team_norm != "general":
            general_rows = list(
                db[PRINCIPLES_COLLECTION].find({"team": team, "sub_team": "general"})
                .sort([("reinforced_count", -1), ("last_seen_at", -1)])
                .limit(limit)
            )

        # 합치고 텍스트 중복 제거 + limit
        seen_text: set[str] = set()
        merged: list[tuple[dict, str]] = []  # (row, source_label)
        for r in _by_score(own_rows):
            t = r.get("principle") or ""
            if t and t not in seen_text:
                seen_text.add(t)
                merged.append((r, "own"))
            if len(merged) >= limit:
                break
        for r in _by_score(cross_rows):
            if len(merged) >= limit:
                break
            t = r.get("principle") or ""
            if t and t not in seen_text:
                seen_text.add(t)
                merged.append((r, "cross"))
        for r in _by_score(general_rows):
            if len(merged) >= limit:
                break
            t = r.get("principle") or ""
            if t and t not in seen_text:
                seen_text.add(t)
                merged.append((r, "general"))
    except Exception:
        log.exception("load_principles_text failed")
        return ""

    if not merged:
        return ""

    lines = ["## 🎓 누적된 도메인 원칙 (시니어 노하우 — 과거 작업에서 추출)"]
    for r, src in merged:
        rc = int(r.get("reinforced_count", 1))
        marker = "★" if rc >= 3 else "·"
        applies = r.get("applies_to", "")
        applies_str = f" [{applies}]" if applies else ""
        src_tag = ""
        if src == "cross":
            src_tag = f" 〈{r.get('sub_team', '?')}분과→{sub_team_norm}〉"
        elif src == "general":
            src_tag = " 〈general〉"
        lines.append(f"  {marker}{applies_str}{src_tag} {r['principle']}")
    lines.append("")
    return "\n".join(lines) + "\n---\n\n"
