"""workspace.py — 프로젝트별 작업장: 작업마다 격리된 git worktree 를 만들고, 변경·검사·커밋을 다룬다.

왜 필요한가:
    지금까지 dev 역할은 "diff 텍스트"를 답으로 썼다(레포 접근 없음). 로컬 Claude Code 보다 못한 이유가 이것이다.
    이 모듈은 작업자 AI 에게 **진짜 체크아웃**을 준다 — 작업 하나 = worktree 하나 = 브랜치 하나.
    병렬 작업이 서로 파일을 덮지 않고(게임팀에서 워커 3개가 트리 1개를 공유해 서로 지우던 사고),
    결과는 브랜치·diff·건드린 파일 목록으로 남아 사람이 고른 뒤에만 밖으로 나간다.

레이아웃 (WSL, newplay 사용자):
    ~/work/<project>/origin/           원본 클론 (미러 /mnt/c/newplay/repos/<project> 에서). 읽기 전용 취급
    ~/work/<project>/wt/<task_id>/     작업별 worktree, 브랜치 ai/<user>/<task_id 앞 8자>

프로젝트 설정 (hermes_projects 문서):
    project, repo.default_branch, repo.dir(윈도우 미러 경로), repo.workspaces
    workspace.checks: [{name, cmd, cwd, timeout}]  — 검사 명령(선택). 없으면 검사 생략
    knowledge.collection                          — 지식베이스 컬렉션(프로젝트별)
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from typing import Any, Optional

log = logging.getLogger("workspace")

WORK_ROOT = os.environ.get("NEWPLAY_WORK_ROOT", os.path.expanduser("~/work"))
MIRROR_ROOT = os.environ.get("NEWPLAY_MIRROR_ROOT", "/mnt/c/newplay/repos")
GIT_ENV = {"GIT_AUTHOR_NAME": "newplay-ai", "GIT_AUTHOR_EMAIL": "ai@newplay.local",
           "GIT_COMMITTER_NAME": "newplay-ai", "GIT_COMMITTER_EMAIL": "ai@newplay.local"}


def _run(args: list[str], cwd: str, timeout: int = 300, env: Optional[dict] = None) -> tuple[int, str, str]:
    e = dict(os.environ)
    e.update(GIT_ENV)
    if env:
        e.update(env)
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, env=e)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return -2, "", f"timeout {timeout}s"
    except FileNotFoundError as ex:
        return -1, "", str(ex)


def _git(cwd: str, *args: str, timeout: int = 300) -> tuple[int, str, str]:
    return _run(["git", *args], cwd, timeout)


# ── 프로젝트 ────────────────────────────────────────────────────────────

def project_paths(project: str) -> dict[str, str]:
    root = os.path.join(WORK_ROOT, project)
    return {"root": root, "origin": os.path.join(root, "origin"), "wt": os.path.join(root, "wt"),
            "mirror": os.path.join(MIRROR_ROOT, project)}


def ensure_origin(project: str, default_branch: str = "main") -> tuple[bool, str]:
    """원본 클론을 준비한다. 없으면 미러에서 클론, 있으면 미러에서 ff-only 로 갱신."""
    p = project_paths(project)
    os.makedirs(p["root"], exist_ok=True)
    os.makedirs(p["wt"], exist_ok=True)
    if not os.path.isdir(os.path.join(p["origin"], ".git")):
        if not os.path.isdir(os.path.join(p["mirror"], ".git")):
            return False, f"미러가 없습니다: {p['mirror']}"
        rc, _o, err = _git(p["root"], "clone", "-q", "--branch", default_branch, p["mirror"], "origin", timeout=900)
        if rc != 0:
            return False, f"클론 실패: {err.strip()[:300]}"
        # 미러의 진짜 원격을 기억해 둔다(나중에 push 용). 실제 push 는 사람 선택 후에만.
        rc, url, _e = _git(p["mirror"], "remote", "get-url", "origin")
        if rc == 0 and url.strip():
            _git(p["origin"], "remote", "add", "upstream", url.strip())
        return True, "cloned"
    _git(p["origin"], "fetch", "-q", "origin", timeout=600)
    rc, _o, err = _git(p["origin"], "merge", "-q", "--ff-only", f"origin/{default_branch}")
    return True, ("updated" if rc == 0 else f"갱신 보류({err.strip()[:120]})")


def origin_rev(project: str) -> str:
    rc, out, _e = _git(project_paths(project)["origin"], "rev-parse", "--short", "HEAD")
    return out.strip() if rc == 0 else ""


# ── worktree ───────────────────────────────────────────────────────────

def _branch_name(actor: str, task_id: str) -> str:
    user = re.sub(r"[^a-z0-9]+", "-", (actor or "anon").split("@")[0].lower()).strip("-") or "anon"
    return f"ai/{user}/{task_id[-8:]}"


def create_worktree(project: str, task_id: str, actor: str, default_branch: str = "main") -> dict[str, Any]:
    """작업용 worktree 를 만든다(이미 있으면 재사용). 반환: {ok, path, branch, base}"""
    p = project_paths(project)
    path = os.path.join(p["wt"], task_id)
    branch = _branch_name(actor, task_id)
    if os.path.isdir(os.path.join(path, ".git")) or os.path.isfile(os.path.join(path, ".git")):
        return {"ok": True, "path": path, "branch": branch, "base": origin_rev(project), "reused": True}
    # 같은 브랜치가 남아 있으면(이전 시도) 지우고 새로
    _git(p["origin"], "branch", "-D", branch)
    rc, _o, err = _git(p["origin"], "worktree", "add", "-q", "-b", branch, path, default_branch, timeout=600)
    if rc != 0:
        _git(p["origin"], "worktree", "prune")
        rc, _o, err = _git(p["origin"], "worktree", "add", "-q", "-b", branch, path, default_branch, timeout=600)
        if rc != 0:
            return {"ok": False, "error": f"worktree 생성 실패: {err.strip()[:300]}"}
    return {"ok": True, "path": path, "branch": branch, "base": origin_rev(project)}


def touched_files(path: str) -> list[str]:
    """지금까지 건드린 파일(추가·수정·삭제·미추적)."""
    rc, out, _e = _git(path, "status", "--porcelain", "--untracked-files=all")
    if rc != 0:
        return []
    files = []
    for line in out.splitlines():
        if len(line) > 3:
            f = line[3:].strip()
            if " -> " in f:
                f = f.split(" -> ", 1)[1]
            files.append(f)
    return sorted(set(files))


def stage_and_diff(path: str) -> tuple[str, list[str]]:
    """전부 스테이징하고 diff 텍스트와 파일 목록을 돌려준다(커밋은 하지 않음)."""
    _git(path, "add", "-A")
    rc, diff, _e = _git(path, "diff", "--cached", "--no-color")
    rc2, names, _e2 = _git(path, "diff", "--cached", "--name-only")
    files = [n.strip() for n in names.splitlines() if n.strip()] if rc2 == 0 else []
    return (diff if rc == 0 else ""), files


def commit(path: str, message: str, actor: str) -> str:
    """스테이징된 변경을 브랜치에 커밋. 반환: 짧은 커밋 해시 ("" 이면 변경 없음/실패)."""
    rc, _o, _e = _git(path, "diff", "--cached", "--quiet")
    if rc == 0:
        return ""
    author = f"{actor or 'newplay-ai'} <{actor or 'ai@newplay.local'}>"
    rc, _o, err = _git(path, "commit", "-q", "--author", author, "-m", message)
    if rc != 0:
        log.warning("커밋 실패: %s", err.strip()[:200])
        return ""
    rc, sha, _e = _git(path, "rev-parse", "--short", "HEAD")
    return sha.strip() if rc == 0 else ""


def hunks(path: str, base: str = "") -> dict[str, list[tuple[int, int]]]:
    """파일별 변경 구간(새 파일 기준 시작줄, 끝줄). 겹침 판정용.
    base 를 주면 base..작업트리 전체(커밋 전후 무관), 없으면 스테이징된 변경만."""
    args = ["diff", "--no-color", "-U0"] + ([base] if base else ["--cached"])
    rc, out, _e = _git(path, *args)
    res: dict[str, list[tuple[int, int]]] = {}
    if rc != 0:
        return res
    cur = ""
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            cur = line[6:].strip()
        elif line.startswith("@@") and cur:
            m = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if m:
                s = int(m.group(1)); n = int(m.group(2) or 1)
                res.setdefault(cur, []).append((s, s + max(n, 1) - 1))
    return res


def remove_worktree(project: str, task_id: str, keep_branch: bool = True) -> None:
    p = project_paths(project)
    path = os.path.join(p["wt"], task_id)
    _git(p["origin"], "worktree", "remove", "--force", path)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    _git(p["origin"], "worktree", "prune")


# ── 검사 ────────────────────────────────────────────────────────────────

def run_checks(path: str, checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """프로젝트가 정의한 검사 명령을 worktree 에서 돌린다. 각 항목: {name, ok, code, tail}."""
    results = []
    for c in checks or []:
        name = str(c.get("name") or c.get("cmd") or "check")
        cwd = os.path.join(path, str(c.get("cwd") or "."))
        cmd = str(c.get("cmd") or "")
        if not cmd:
            continue
        env = {"PATH": os.path.expanduser("~/.nvm/versions/node/v20.20.2/bin") + ":" + os.environ.get("PATH", "")}
        rc, out, err = _run(["bash", "-lc", cmd], cwd, timeout=int(c.get("timeout") or 600), env=env)
        tail = "\n".join(((out or "") + "\n" + (err or "")).strip().splitlines()[-25:])
        results.append({"name": name, "cmd": cmd, "ok": rc == 0, "code": rc, "tail": tail[:3000]})
    return results


def checks_block(results: list[dict[str, Any]]) -> str:
    if not results:
        return ""
    lines = ["## 검사 결과 (worktree 에서 실제 실행)"]
    for r in results:
        lines.append(f"- {'✅' if r['ok'] else '❌'} `{r['name']}` (exit {r['code']})")
        if not r["ok"] and r.get("tail"):
            lines.append("```\n" + r["tail"][-1200:] + "\n```")
    return "\n".join(lines)
