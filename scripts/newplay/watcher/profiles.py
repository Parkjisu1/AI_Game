"""profiles.py — 사람의 "작업 프로필"(설계서 §7): 세션·채택 브랜치·검수 코멘트에서 자동으로 쌓이고, 대리 모드가 입는다.

프로필 = person_profiles 문서 (email × project):
    enabled, role_label, areas{prefix: weight}, conventions[{text, evidence}], principles[], checks[{cmd,cwd}],
    review_rules[], style{first_moves[]}, exemplars[task_id], stats{}, owner_notes, updated_at

원천:
    - work_sessions (직접 모드 전사 요약: commands, files, extracted)      → areas, checks, style
    - pixelforge_tasks 채택분 (touched_files, proposed_patch)             → areas, exemplars
    - 검수 코멘트/반려 사유                                                → review_rules
    - mem_<project>_m3 의 owner 메모                                       → principles (대리 시 검색으로 붙음)
규칙:
    - 관례·원칙은 근거 2건 이상일 때 승격(1건은 후보). areas 는 채택 파일 수 누적, 90일 감쇠.
    - 대리 결과는 담당자 본인이 채택했을 때만 exemplar 로.
    - enabled=false 면 대리 모드에서 제외.
"""
from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo import MongoClient

log = logging.getLogger("profiles")
MONGO_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("MONGODB_DB", "newteam")
PROMPT_CAP = int(os.environ.get("NEWPLAY_PROFILE_PROMPT_CHARS", "12000"))
# 전사에서 주워 담는 "검증 습관". 이 명령들은 나중에 대리 모드에서 **자동으로 실행**되므로 좁게 잡는다.
# 검사 동사(test/lint/typecheck/build/check/format 등)만 허용하고, 셸 메타문자가 섞인 줄은 통째로 버린다.
CHECK_VERB = r"(?:test|tests|lint|typecheck|type-check|tsc|check|build|format|fmt|verify|vitest|jest|pytest|biome|eslint|prettier)"
CHECK_RE = re.compile(
    rf"^(?![\s\S]*[\r\n])(?:(?:yarn|pnpm|npx)(?:\s+(?:run|workspace\s+\S+))?\s+{CHECK_VERB}"
    rf"|npm\s+(?:run\s+)?{CHECK_VERB}"
    rf"|(?:python\s+-m\s+)?pytest|tsc|biome\s+\S*check\S*|vitest|jest|eslint|prettier\s+--check)\b[^;&|`$><]*$",
    re.I)


def safe_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """저장된 옛 프로필도 실행 직전에 같은 단일 명령 규칙으로 거른다."""
    return [c for c in checks if isinstance(c, dict) and isinstance(c.get("cmd"), str)
            and CHECK_RE.fullmatch(c["cmd"])]


def _db():
    cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return cli, cli[DB_NAME]


# ── 전사 파서 (Claude Code ~/.claude/projects/<cwd>/<session>.jsonl) ────────

def parse_transcript(path: str) -> dict[str, Any]:
    """전사 JSONL 에서 사람 지시·도구 사용·명령·파일을 뽑는다. 형식이 달라도 죽지 않는다."""
    user_msgs, commands, files, tools = [], [], set(), Counter()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    j = json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                msg = j.get("message") if isinstance(j.get("message"), dict) else j
                role = j.get("type") or msg.get("role")
                content = msg.get("content")
                blocks = content if isinstance(content, list) else ([{"type": "text", "text": content}] if isinstance(content, str) else [])
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    if role == "user" and b.get("type") == "text" and b.get("text"):
                        user_msgs.append(str(b["text"])[:400])
                    if b.get("type") == "tool_use":
                        name = str(b.get("name") or ""); tools[name] += 1
                        inp = b.get("input") or {}
                        if name == "Bash" and inp.get("command"):
                            commands.append(str(inp["command"])[:200])
                        for k in ("file_path", "path", "notebook_path"):
                            if inp.get(k):
                                files.add(str(inp[k]))
    except OSError:
        pass
    return {"user_msgs": user_msgs[:40], "commands": commands[:80], "files": sorted(files)[:100], "tools": dict(tools)}


def find_transcripts(home_dir: str, since_iso: str = "", project: str = "") -> list[str]:
    """개인 홈(/data/home/<user>)의 Claude Code 전사 파일. since 이후 수정된 것만.

    project 를 주면 그 프로젝트 폴더에서 일한 전사만 고른다(Claude Code 는 작업 폴더 경로를 디렉터리 이름으로 쓴다).
    한 사람이 여러 프로젝트를 동시에 띄워도 다른 프로젝트의 파일이 이 프로필로 섞이지 않게 하려는 것이다.
    """
    base = os.path.join(home_dir, ".claude", "projects")
    out, wide = [], []
    try:
        since = datetime.fromisoformat(since_iso.replace("Z", "+00:00")).timestamp() if since_iso else 0
    except Exception:  # noqa: BLE001
        since = 0
    key = re.sub(r"[^a-z0-9]+", "-", (project or "").lower()).strip("-")
    for root, _d, fs in os.walk(base):
        for fn in fs:
            if fn.endswith(".jsonl"):
                p = os.path.join(root, fn)
                try:
                    if os.path.getmtime(p) >= since - 1:
                        wide.append(p)
                        # Claude의 폴더 이름은 절대 작업 경로를 인코딩한다. 프로젝트
                        # 이름만 부분 검색하면 web이 webstore의 기록까지 가져온다.
                        folder = os.path.relpath(root, base).split(os.sep)[0].lower()
                        if key and (folder.startswith(f"-data-git-{key}-wt-")
                                    or folder == f"-data-git-{key}-origin"):
                            out.append(p)
                except OSError:
                    pass
    if key and wide and not out:
        log.info("전사 %d건이 있으나 프로젝트 %s 폴더에서 일한 것이 아니어서 제외함", len(wide), project)
    return sorted(out if key else wide)


# ── 프로필 갱신 ─────────────────────────────────────────────────────────

def _prefix(path: str, depth: int = 3) -> str:
    parts = [p for p in path.replace("\\", "/").split("/") if p and p != "."]
    # /data/git/<project>/wt/<id>/... 처럼 절대경로면 wt 뒤부터
    if "wt" in parts:
        i = parts.index("wt"); parts = parts[i + 2:]
    return "/".join(parts[:depth])


def _defaults(email: str, project: str) -> dict[str, Any]:
    return {"email": email.lower(), "project": project, "enabled": True, "role_label": "", "areas": {}, "conventions": [], "principles": [],
            "checks": [], "review_rules": [], "style": {"first_moves": []}, "exemplars": [], "owner_notes": "",
            "stats": {"sessions": 0, "accepted": 0, "proxied_accepted": 0}}


def get(email: str, project: str) -> dict[str, Any]:
    cli, db = _db()
    try:
        return db["person_profiles"].find_one({"email": email.lower(), "project": project}) or {}
    finally:
        cli.close()


def update_from_session(email: str, project: str, session: dict[str, Any]) -> None:
    """직접 모드 세션 종료 → areas(파일)·checks(명령)·style 갱신. 프로필을 끈 사람은 기록하지 않는다."""
    cli, db = _db()
    try:
        col = db["person_profiles"]
        cur = col.find_one({"email": email.lower(), "project": project}, {"enabled": 1})
        if cur and cur.get("enabled") is False:
            return   # "끄기" = 수집도 중단. 세션 문서는 남지만 프로필에는 쌓이지 않는다.
        doc = col.find_one({"email": email.lower(), "project": project}) or {"email": email.lower(), "project": project, "enabled": True,
                                                                                "areas": {}, "conventions": [], "principles": [], "checks": [],
                                                                                "review_rules": [], "style": {"first_moves": []}, "exemplars": [],
                                                                                "stats": {"sessions": 0, "accepted": 0, "proxied_accepted": 0}}
        areas = dict(doc.get("areas") or {})
        for f in session.get("files") or []:
            pre = _prefix(f)
            if pre:
                areas[pre] = round(areas.get(pre, 0) + 1, 2)
        checks = safe_checks(list(doc.get("checks") or []))
        seen = {c.get("cmd") for c in checks}
        for cmd in session.get("commands") or []:
            c = cmd.strip()
            if CHECK_RE.fullmatch(c) and c not in seen and len(checks) < 8:
                checks.append({"cmd": c, "cwd": ".", "source": "session"}); seen.add(c)
        stats = dict(doc.get("stats") or {}); stats["sessions"] = int(stats.get("sessions", 0)) + 1
        setv = {"areas": areas, "checks": checks, "stats": stats, "updated_at": datetime.now(timezone.utc).isoformat()}
        col.update_one({"email": email.lower(), "project": project},
                       {"$set": setv, "$setOnInsert": {k: v for k, v in _defaults(email, project).items() if k not in setv}}, upsert=True)
    finally:
        cli.close()


def update_from_accepted(task: dict[str, Any], accepted_by: str) -> None:
    """채택된 작업 → 담당자(요청자 또는 act_as)의 areas·exemplars. 대리 결과는 담당자 본인이 채택했을 때만 exemplar."""
    email = str(task.get("act_as") or task.get("created_by_email") or "").lower()
    project = str(task.get("project") or "")
    if not email or not project:
        return
    is_proxy = bool(task.get("act_as"))
    by = (accepted_by or "").lower()
    cli, db = _db()
    try:
        col = db["person_profiles"]
        doc = col.find_one({"email": email, "project": project}) or {"email": email, "project": project, "enabled": True, "areas": {},
                                                                     "conventions": [], "principles": [], "checks": [], "review_rules": [],
                                                                     "style": {"first_moves": []}, "exemplars": [], "stats": {"sessions": 0, "accepted": 0, "proxied_accepted": 0}}
        if doc.get("enabled") is False:
            return
        areas = dict(doc.get("areas") or {})
        for f in task.get("touched_files") or []:
            pre = _prefix(f)
            if pre:
                areas[pre] = round(areas.get(pre, 0) + 2, 2)      # 채택은 세션보다 가중치 2배
        ex = list(doc.get("exemplars") or [])
        tid = str(task.get("_id"))
        allow_exemplar = (not is_proxy) or (by == email)
        if allow_exemplar and tid not in ex and len(str(task.get("proposed_patch") or "")) <= 4000 and all(c.get("ok") for c in (task.get("checks") or [])):
            ex = ([tid] + ex)[:8]
        stats = dict(doc.get("stats") or {})
        stats["accepted"] = int(stats.get("accepted", 0)) + (0 if is_proxy else 1)
        stats["proxied_accepted"] = int(stats.get("proxied_accepted", 0)) + (1 if is_proxy else 0)
        setv = {"areas": areas, "exemplars": ex, "stats": stats, "updated_at": datetime.now(timezone.utc).isoformat()}
        col.update_one({"email": email, "project": project},
                       {"$set": setv, "$setOnInsert": {k: v for k, v in _defaults(email, project).items() if k not in setv}}, upsert=True)
    finally:
        cli.close()


def add_review_rule(email: str, project: str, rule: str, evidence: str) -> None:
    cli, db = _db()
    try:
        db["person_profiles"].update_one({"email": email.lower(), "project": project},
                                         {"$addToSet": {"review_rules": {"text": rule[:200], "evidence": evidence}}, "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    finally:
        cli.close()


# ── 대리 모드용 ───────────────────────────────────────────────────────────

def owner_for(project: str, paths: list[str]) -> Optional[str]:
    """건드릴 파일들의 prefix 와 프로필 areas 를 대조해 담당자 자동 지정. 동률·없음이면 None."""
    cli, db = _db()
    try:
        best: list[tuple[float, str]] = []
        for p in db["person_profiles"].find({"project": project, "enabled": {"$ne": False}}):
            areas = p.get("areas") or {}
            score = sum(areas.get(_prefix(f), 0) + areas.get(_prefix(f, 2), 0) * 0.5 for f in paths)
            if score > 0:
                best.append((score, p["email"]))
        best.sort(reverse=True)
        if not best or (len(best) > 1 and best[0][0] == best[1][0]):
            return None
        return best[0][1]
    finally:
        cli.close()


def as_prompt_block(email: str, project: str, exemplar_diffs: list[str]) -> str:
    """대리 모드 프롬프트 블록(설계서 §6-3 순서 고정, 12k 자 상한)."""
    p = get(email, project)
    if not p or p.get("enabled") is False:
        return ""
    areas = sorted((p.get("areas") or {}).items(), key=lambda kv: -kv[1])[:8]
    L = [f"# 너는 지금 {email} 처럼 일한다 — 아래는 그 사람이 남긴 기록에서 추출한 작업 방식이다. 이 방식을 따르되, 근거가 없는 것은 지어내지 마라.",
         f"## 역할·담당 영역: {p.get('role_label') or '(자동 추정 전)'}",
         *[f"- {k} (가중치 {v})" for k, v in areas],
         "## 코딩 관례" ] + [f"- {c.get('text')} (근거 {', '.join(map(str, c.get('evidence') or []))[:60]})" for c in (p.get("conventions") or [])[:8]] + \
        ["## 결정 원칙"] + [f"- {x}" for x in (p.get("principles") or [])[:8]] + \
        ["## 검증 습관 (끝나기 전에 이 명령들을 돌린다)"] + [f"- `{c.get('cmd')}` (cwd {c.get('cwd') or '.'})" for c in safe_checks(p.get("checks") or [])[:6]] + \
        ["## 이 사람이라면 반려할 것 (자기 검열)"] + [f"- {r.get('text') if isinstance(r, dict) else r}" for r in (p.get("review_rules") or [])[:6]]
    if p.get("owner_notes"):
        L.insert(1, f"## 본인 메모 (최우선)\n{str(p['owner_notes'])[:800]}")
    for i, d in enumerate(exemplar_diffs[:2]):
        L.append(f"## 예시 diff {i+1} (이 사람이 채택한 실제 변경)\n```diff\n{d[:2500]}\n```")
    text = "\n".join(L)
    return text[:PROMPT_CAP]


def exemplar_diffs(email: str, project: str, n: int = 2) -> list[str]:
    p = get(email, project)
    ids = (p.get("exemplars") or [])[:n]
    if not ids:
        return []
    from bson import ObjectId
    cli, db = _db()
    try:
        out = []
        for tid in ids:
            try:
                t = db["pixelforge_tasks"].find_one({"_id": ObjectId(tid)}, {"proposed_patch": 1})
                if t and t.get("proposed_patch"):
                    out.append(str(t["proposed_patch"]))
            except Exception:  # noqa: BLE001
                pass
        return out
    finally:
        cli.close()


def summary(email: str, project: str) -> dict[str, Any]:
    """화면·API 용 요약(원문 노출 없음)."""
    p = get(email, project)
    if not p:
        return {}
    return {"email": p["email"], "project": p["project"], "enabled": p.get("enabled", True), "role_label": p.get("role_label"),
            "areas": dict(sorted((p.get("areas") or {}).items(), key=lambda kv: -kv[1])[:10]),
            "conventions": len(p.get("conventions") or []), "principles": len(p.get("principles") or []),
            "checks": [c.get("cmd") for c in (p.get("checks") or [])], "review_rules": len(p.get("review_rules") or []),
            "exemplars": len(p.get("exemplars") or []), "stats": p.get("stats"), "updated_at": p.get("updated_at")}
