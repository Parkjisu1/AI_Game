"""change_ledger.py — NewPlay 변경을 **범위 안에서만, 이력을 남기며** 적용한다.

왜 이 모듈이 있나:
    NewPlay 팀이 에이전트 제안을 직접 적용할 수 있게 하려는데,
    그 권한을 SSH 로 주면 **ProjectHub 까지 열린다.** 같은 서버에 같은 계정으로 있기 때문이다.
    그래서 SSH 를 주지 않고, 플랫폼을 통과하는 경로 하나만 연다.
    그 경로에 범위 검사를 박으면 "webstore 만" 이 구조로 강제된다 — 약속이 아니라 코드로.

무엇을 보장하나:
    1. 범위   — 허용된 레포 루트 밖은 적용되지 않는다(ProjectHub 는 아예 다른 트리다)
    2. 이력   — 적용 = git 커밋. `git log` 가 이력이고 `git revert` 가 되돌리기다
    3. 충돌   — 적용 전에 두 가지를 본다:
                 (a) 기반이 낡았는가 — 지금 트리에 붙는가
                 (b) 다른 열린 변경과 같은 파일을 건드리는가
                 걸리면 **양쪽 작업 스레드에 서로를 언급하는 글**을 남긴다
    4. 격리   — main 을 직접 건드리지 않는다. 작업마다 브랜치를 따로 판다

무엇을 보장하지 않나:
    원격 push 는 아직 못 한다(deploy key 미등록). 브랜치는 서버에 남고,
    키가 등록되면 그 브랜치를 그대로 밀어 PR 로 만들면 된다.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

#: 적용 전용 worktree. 미리보기(newplay-preview)·검증(newplay-verify) 트리와 분리한다 —
#: 미리보기는 빌드 때마다 `git clean -fd` 를 돌아서 커밋을 보존할 수 없다.
APPLY_TREE = os.environ.get("NEWPLAY_APPLY_TREE", os.path.expanduser("~/newplay-apply"))
SOURCE_REPO = os.environ.get("NEWPLAY_SOURCE_REPO", os.path.expanduser("~/newplay-preview/webstore"))

MONGO_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("MONGODB_DB", "newteam")
LEDGER = "newplay_change_ledger"

#: **여기 없는 경로는 적용되지 않는다.**
#: ProjectHub 는 애초에 다른 트리라 닿을 수 없지만, 그건 우연히 그런 것이다.
#: 규칙으로 박아 두면 나중에 트리 구성이 바뀌어도 범위가 유지된다.
ALLOWED_ROOTS = tuple(
    r.strip() for r in os.environ.get("NEWPLAY_ALLOWED_ROOTS", "front-end/,backend/").split(",")
    if r.strip()
)


class ScopeError(Exception):
    """허용 범위 밖을 건드리려 할 때."""


def _git(*args: str, cwd: str | None = None, timeout: int = 120) -> tuple[int, str, str]:
    r = subprocess.run(["git", *args], cwd=cwd or APPLY_TREE,
                       capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout, r.stderr


def patch_files(patch: str) -> list[str]:
    """패치가 건드리는 파일 목록. `+++ b/` 기준."""
    return sorted(set(re.findall(r"^\+\+\+ b/(.+?)\s*$", patch or "", re.M)))


def check_scope(files: list[str]) -> list[str]:
    """허용 범위를 벗어난 파일 목록. 비어 있으면 통과.

    경로 탈출(`..`, 절대경로)도 여기서 막는다 — git apply 가 알아서 막아 주긴 하지만,
    범위 판단을 그 우연에 맡기지 않는다.
    """
    bad = []
    for f in files:
        p = f.strip()
        if not p or p.startswith("/") or ".." in p.split("/"):
            bad.append(f)
            continue
        if not any(p.startswith(root) for root in ALLOWED_ROOTS):
            bad.append(f)
    return bad


def ensure_tree() -> str:
    """적용 전용 worktree 를 준비한다(없으면 만든다)."""
    if os.path.isdir(os.path.join(APPLY_TREE, ".git")) or os.path.exists(os.path.join(APPLY_TREE, ".git")):
        return APPLY_TREE
    os.makedirs(os.path.dirname(APPLY_TREE), exist_ok=True)
    rc, _o, e = _git("worktree", "add", "-B", "hermes/apply", APPLY_TREE, "main", cwd=SOURCE_REPO)
    if rc != 0:
        raise RuntimeError(f"적용 트리 생성 실패: {e.strip()[:300]}")
    return APPLY_TREE


def _col():
    from pymongo import MongoClient
    cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return cli, cli[DB_NAME][LEDGER]


def open_changes(exclude_task: str = "") -> list[dict[str, Any]]:
    """아직 되돌려지지 않은 적용 내역. 충돌 판단의 기준."""
    cli, col = _col()
    try:
        q: dict[str, Any] = {"status": "applied"}
        if exclude_task:
            q["task_id"] = {"$ne": exclude_task}
        return list(col.find(q).sort("applied_at", -1).limit(200))
    finally:
        cli.close()


def find_conflicts(files: list[str], task_id: str) -> list[dict[str, Any]]:
    """같은 파일을 건드리는 다른 변경들.

    파일 단위로 본다. 줄 단위까지 보면 정확해지지만, 실제로 사람이 부딪히는 지점은
    "같은 파일을 둘이 고쳤다" 이고, 그 시점에 서로 알기만 해도 대부분 예방된다.
    """
    fs = set(files)
    out = []
    for c in open_changes(exclude_task=task_id):
        overlap = sorted(fs & set(c.get("files") or []))
        if overlap:
            out.append({**c, "overlap": overlap})
    return out


def dry_run(patch: str, task_id: str) -> dict[str, Any]:
    """적용하지 않고 판정만 한다. 화면에서 '적용' 누르기 전에 보여줄 것."""
    files = patch_files(patch)
    result: dict[str, Any] = {"files": files, "ok": False}

    out_of_scope = check_scope(files)
    result["out_of_scope"] = out_of_scope
    if out_of_scope:
        result["reason"] = ("허용 범위 밖 파일이 있습니다: " + ", ".join(out_of_scope[:5])
                            + f" (허용: {', '.join(ALLOWED_ROOTS)})")
        return result

    try:
        ensure_tree()
    except Exception as e:  # noqa: BLE001
        result["reason"] = f"적용 트리를 준비하지 못했습니다: {e}"
        return result

    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8") as f:
        f.write(patch if patch.endswith("\n") else patch + "\n")
        pf = f.name
    try:
        rc, _o, err = _git("apply", "--check", "--recount", pf)
        result["applies"] = rc == 0
        if rc != 0:
            result["reason"] = ("지금 코드에 붙지 않습니다 — 기반이 달라졌을 수 있습니다: "
                                + err.strip().splitlines()[0][:200] if err.strip() else "적용 불가")
            return result
    finally:
        try:
            os.unlink(pf)
        except OSError:
            pass

    result["conflicts"] = find_conflicts(files, task_id)
    result["ok"] = True
    return result


def apply_change(patch: str, task_id: str, title: str, actor: str) -> dict[str, Any]:
    """패치를 적용하고 커밋한다. 범위 밖이면 아무것도 하지 않는다.

    커밋이 곧 이력이다 — 누가·언제·어떤 작업에서 나온 변경인지 커밋 메시지에 남긴다.
    되돌리기는 `revert_change()` 가 `git revert` 로 처리한다.
    """
    pre = dry_run(patch, task_id)
    if not pre.get("ok"):
        return {"ok": False, **pre}

    files = pre["files"]
    ensure_tree()

    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8") as f:
        f.write(patch if patch.endswith("\n") else patch + "\n")
        pf = f.name
    try:
        rc, _o, err = _git("apply", "--recount", pf)
        if rc != 0:
            return {"ok": False, "reason": f"적용 실패: {err.strip()[:300]}", "files": files}
    finally:
        try:
            os.unlink(pf)
        except OSError:
            pass

    _git("add", "--", *files)
    digest = hashlib.sha256(patch.encode("utf-8")).hexdigest()[:12]
    msg = (f"{title[:72]}\n\n"
           f"ProjectHub task: {task_id}\n"
           f"Applied-by: {actor}\n"
           f"Patch-sha256: {digest}\n")
    rc, _o, err = _git("-c", f"user.name=hermes", "-c", "user.email=hermes@newplay.local",
                       "commit", "--author", f"{actor} <{actor}>", "-m", msg)
    if rc != 0:
        _git("reset", "--hard", "HEAD")
        return {"ok": False, "reason": f"커밋 실패: {err.strip()[:300]}", "files": files}

    _rc, sha, _e = _git("rev-parse", "--short", "HEAD")
    _rc, base, _e = _git("rev-parse", "--short", "HEAD~1")
    commit = sha.strip()

    cli, col = _col()
    try:
        col.insert_one({
            "task_id": task_id, "task_title": title,
            "files": files, "commit": commit, "base": base.strip(),
            "patch_sha256": digest,
            "status": "applied", "applied_by": actor,
            "applied_at": datetime.now(timezone.utc).isoformat(),
        })
    finally:
        cli.close()

    return {"ok": True, "commit": commit, "files": files,
            "conflicts": pre.get("conflicts") or []}


def revert_change(commit: str, actor: str) -> dict[str, Any]:
    """되돌리기. 커밋을 지우지 않고 revert 커밋을 얹는다 — 이력이 남아야 한다."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit or ""):
        return {"ok": False, "reason": "커밋 해시 형식이 아닙니다"}
    ensure_tree()
    rc, _o, err = _git("-c", "user.name=hermes", "-c", "user.email=hermes@newplay.local",
                       "revert", "--no-edit", commit)
    if rc != 0:
        _git("revert", "--abort")
        return {"ok": False, "reason": f"되돌리기 실패(다른 변경과 겹칩니다): {err.strip()[:300]}"}
    _rc, sha, _e = _git("rev-parse", "--short", "HEAD")

    cli, col = _col()
    try:
        col.update_one({"commit": commit}, {"$set": {
            "status": "reverted", "reverted_by": actor,
            "reverted_at": datetime.now(timezone.utc).isoformat(),
            "revert_commit": sha.strip(),
        }})
    finally:
        cli.close()
    return {"ok": True, "revert_commit": sha.strip()}


def _post_comment(task_id: str, text: str) -> None:
    """작업 스레드에 글을 남긴다. 실패해도 조용히 넘어간다(알림은 보조 기능)."""
    from bson import ObjectId
    from pymongo import MongoClient
    try:
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        try:
            key = {"_id": ObjectId(str(task_id))}
        except Exception:  # noqa: BLE001
            key = {"_id": task_id}
        cli[DB_NAME]["pixelforge_tasks"].update_one(key, {"$push": {"comments": {
            "id": hashlib.sha1(f"{task_id}{text[:80]}{datetime.now(timezone.utc)}"
                               .encode()).hexdigest()[:16],
            "text": text,
            "author": "hermes",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }}})
        cli.close()
    except Exception as e:  # noqa: BLE001
        log.warning("충돌 알림 실패(무시): %s: %s", type(e).__name__, e)


def notify_conflicts(task_id: str, title: str, conflicts: list[dict[str, Any]],
                     actor: str) -> int:
    """겹치는 변경이 있으면 **양쪽 작업 스레드에 서로를 언급하는 글**을 남긴다.

    한쪽에만 남기면 상대는 자기 변경이 덮일 수 있다는 걸 모른다.
    충돌은 두 사람 사이에서 일어나므로 알림도 양쪽이어야 한다.
    """
    if not conflicts:
        return 0
    n = 0
    for c in conflicts:
        other_id = str(c.get("task_id") or "")
        other_title = str(c.get("task_title") or "(제목 없음)")
        overlap = c.get("overlap") or []
        files = "\n".join(f"- `{f}`" for f in overlap[:10])
        more = f"\n- …외 {len(overlap) - 10}개" if len(overlap) > 10 else ""

        _post_comment(task_id, (
            f"⚠️ **같은 파일을 건드리는 다른 변경이 있습니다**\n\n"
            f"상대 작업: **{other_title}** (`{other_id}`)\n"
            f"적용자: {c.get('applied_by', '?')} · 커밋 `{c.get('commit', '?')}`\n\n"
            f"겹치는 파일:\n{files}{more}\n\n"
            f"먼저 적용된 쪽이 살아 있습니다. 이 변경을 적용하면 같은 줄에서 부딪힐 수 있으니 "
            f"상대 작업의 내용을 먼저 확인해 주세요."))

        if other_id:
            _post_comment(other_id, (
                f"⚠️ **이 작업의 변경과 겹치는 다른 작업이 있습니다**\n\n"
                f"상대 작업: **{title}** (`{task_id}`)\n"
                f"적용 시도: {actor}\n\n"
                f"겹치는 파일:\n{files}{more}\n\n"
                f"이 작업의 변경(`{c.get('commit', '?')}`)이 먼저 적용돼 있습니다. "
                f"상대 쪽이 같은 파일을 고치려 하니 조율이 필요합니다."))
            n += 1
    return n


def history(limit: int = 30) -> list[dict[str, Any]]:
    """적용 이력. 화면에 그대로 뿌릴 수 있는 형태."""
    cli, col = _col()
    try:
        return [{k: v for k, v in d.items() if k != "_id"}
                for d in col.find({}).sort("applied_at", -1).limit(limit)]
    finally:
        cli.close()
