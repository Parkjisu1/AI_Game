"""platform_deploy.py — 플랫폼(ProjectHub NewPlay 인스턴스)과 AI 워처를 고치고 배포한다.

webstore 변경(change_ledger.py)과 결정적으로 다른 점:
    **되돌릴 때 쓸 화면이 같이 죽을 수 있다.**
    webstore 는 git 트리에 적용만 하고 끝이라 실패해도 플랫폼은 멀쩡하다.
    플랫폼은 적용 = 빌드 + 재기동이라, 잘못되면 되돌리기 버튼 자체에 접근할 수 없다.

그래서 되돌리기를 **사람이 누르는 것에 의존하지 않는다.** 서버가 스스로 판단한다:

    1. 지금 상태를 되돌아갈 지점으로 기록
    2. .next(빌드 산출물) 백업 — 빌드가 실패하면 반쯤 망가진 상태로 남기 때문
    3. 패치 적용 + 커밋
    4. 빌드 → 실패하면 되돌리고 .next 복원. **서비스는 건드리지도 않았다**
    5. 재기동 → 헬스체크
    6. 응답이 없으면 되돌리고 다시 빌드·재기동. 사람이 개입하지 않아도 살아난다

마지막 방어선은 SSH 로 직접 돌리는 `rollback.sh` 다 — 이 모듈까지 망가진 경우를 위해.

두 대상 (Profile):
    platform — 웹 플랫폼 `~/projecthub-newteam`. 빌드 = `npm run build`, 헬스 = HTTP 응답.
               범위 `src/`, `public/`.
    watcher  — AI 워처 `~/.hermes-newteam/watcher`. AI 의 역할 분배·라우팅·실행·검수 로직이
               여기 있다(agent_team / task_router / hermes_executor / context_builder …).
               빌드 = py_compile + import 검사, 헬스 = 재기동 후 서비스가 살아서 "starting"
               로그를 찍는지. 범위 = 최상위 `*.py`. 단 **이 배포 장치 자체**(platform_deploy /
               change_ledger / ledger_cli / token_mint)는 제외 — 범위를 강제하는 코드를
               그 범위 안에서 고칠 수 있으면 보장이 보장이 아니다. 의존성(requirements.lock)도
               제외 — pip 이 필요해 실패 양상이 다르다(package.json 을 뺀 것과 같은 이유).

범위: 프로파일 밖은 적용하지 않는다. 특히 `.env*` 는 **git 에 없고** 여기서도 막는다 —
      비밀이 패치로 들어오거나 나가면 안 된다.
"""
from __future__ import annotations

import ast
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

NODE_BIN = os.environ.get("NEWPLAY_NODE_BIN", os.path.expanduser("~/.nvm/versions/node/v20.20.2/bin"))
#: 런타임: systemd(현재 PC) 또는 docker(compose). docker 면 빌드는 web 컨테이너 안에서, 재기동은 docker restart, 헬스는 docker inspect.
RUNTIME = os.environ.get("NEWPLAY_RUNTIME", "systemd").lower()
WEB_CONTAINER = os.environ.get("NEWPLAY_WEB_CONTAINER", "newplay-web-1")
WATCHER_CONTAINER = os.environ.get("NEWPLAY_WATCHER_CONTAINER", "newplay-watcher-1")
LEARNER_CONTAINER = os.environ.get("NEWPLAY_LEARNER_CONTAINER", "newplay-learner-1")
MONGO_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("MONGODB_DB", "newteam")

#: 헬스체크가 이 안에 통과하지 못하면 실패로 본다.
HEALTH_TIMEOUT = int(os.environ.get("NEWPLAY_PLATFORM_HEALTH_TIMEOUT", "60"))


@dataclass(frozen=True)
class Profile:
    name: str
    tree: str
    service: str
    ledger: str
    #: 접두 일치 허용 목록. "" 는 최상위 포함 전부(아래 suffix/deny 로 다시 좁힌다).
    allowed_roots: tuple[str, ...]
    #: 허용 확장자. None 이면 제한 없음.
    allowed_suffixes: tuple[str, ...] | None = None
    #: 항상 거부하는 파일명(basename).
    denied_files: tuple[str, ...] = ()
    #: 최상위 파일만 허용할지(하위 디렉터리 거부).
    top_level_only: bool = False
    #: 빌드 산출물(.next) 백업이 필요한지.
    backs_up_next: bool = False
    #: 사람이 읽는 범위 설명.
    scope_label: str = ""
    health_url: str = ""
    health_log: str = ""
    health_log_marker: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


PLATFORM = Profile(
    name="platform",
    tree=os.environ.get("NEWPLAY_PLATFORM_TREE", os.path.expanduser("~/projecthub-newteam")),
    service=os.environ.get("NEWPLAY_PLATFORM_SERVICE", "projecthub-newteam"),
    ledger="newplay_platform_ledger",
    allowed_roots=tuple(
        r.strip() for r in os.environ.get("NEWPLAY_PLATFORM_ROOTS", "src/,public/").split(",")
        if r.strip()
    ),
    backs_up_next=True,
    scope_label="src/, public/",
    health_url=os.environ.get("NEWPLAY_PLATFORM_HEALTH", "http://127.0.0.1:3000/login"),
)

#: 배포 장치 자신. 워처 범위에서 영구 제외 — 범위를 강제하는 코드는 그 범위 밖에 있어야 한다.
WATCHER_GUARD_FILES = ("platform_deploy.py", "change_ledger.py", "ledger_cli.py", "token_mint.py")

WATCHER = Profile(
    name="watcher",
    tree=os.environ.get("NEWPLAY_WATCHER_TREE", os.path.expanduser("~/.hermes-newteam/watcher")),
    service=os.environ.get("NEWPLAY_WATCHER_SERVICE", "hermes-newteam"),
    ledger="newplay_watcher_ledger",
    allowed_roots=("",),
    allowed_suffixes=(".py",),
    denied_files=WATCHER_GUARD_FILES + ("requirements.lock",),
    top_level_only=True,
    scope_label="최상위 *.py (배포 장치 4개·requirements.lock 제외)",
    health_log=os.environ.get("NEWPLAY_WATCHER_LOG", os.path.expanduser("~/.hermes-newteam/logs/watcher.log")),
    health_log_marker="ProjectHub Watcher starting",
)

PROFILES = {PLATFORM.name: PLATFORM, WATCHER.name: WATCHER}

# ── 하위 호환: 예전 모듈 상수 이름을 참조하는 코드가 있을 수 있다.
TREE = PLATFORM.tree
SERVICE = PLATFORM.service
HEALTH_URL = PLATFORM.health_url
ALLOWED_ROOTS = PLATFORM.allowed_roots
LEDGER = PLATFORM.ledger


def profile_of(name: str) -> Profile:
    p = PROFILES.get(name or "")
    if not p:
        raise ValueError(f"알 수 없는 대상: {name}")
    return p


def _run(args: list[str], cwd: str, timeout: int = 600) -> tuple[int, str, str]:
    env = dict(os.environ)
    env["PATH"] = NODE_BIN + os.pathsep + env.get("PATH", "")
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, env=env)
    except (subprocess.TimeoutExpired, OSError) as e:
        return -1, "", f"{type(e).__name__}: {e}"
    return r.returncode, r.stdout, r.stderr


def _git(p: Profile, *args: str, timeout: int = 120) -> tuple[int, str, str]:
    return _run(["git", *args], cwd=p.tree, timeout=timeout)


def patch_files(patch: str) -> list[str]:
    """Git이 해석한 변경 목록. 삭제·바이너리·이름 변경의 양쪽 경로를 포함한다."""
    r = subprocess.run(["git", "apply", "--numstat", "-z", "--recount", "-"],
                       input=(patch if patch.endswith("\n") else patch + "\n").encode("utf-8"), capture_output=True, timeout=30)
    if r.returncode:
        raise ValueError(r.stderr.decode("utf-8", "replace")[:300])
    files = {entry.split(b"\t", 2)[2].decode("utf-8") for entry in r.stdout.split(b"\0") if entry}
    # --numstat은 rename/copy의 목적지만 반환한다. 보호 파일인 원본도 검사한다.
    for raw in re.findall(r"^(?:rename|copy) from (.+)$", patch, re.M):
        source = ast.literal_eval("b" + raw).decode("utf-8") if raw.startswith('"') else raw
        files.add(source)
    if not files:
        raise ValueError("변경 파일이 없는 패치")
    return sorted(files)


def check_scope(files: list[str], p: Profile = PLATFORM) -> list[str]:
    bad = []
    for f in files:
        q = f.strip()
        if not q or q.startswith("/") or ".." in q.split("/"):
            bad.append(f)
            continue
        base = os.path.basename(q)
        # 비밀 파일은 어떤 경우에도 안 된다.
        if base.startswith(".env"):
            bad.append(f)
            continue
        if base in p.denied_files:
            bad.append(f)
            continue
        if p.top_level_only and "/" in q:
            bad.append(f)
            continue
        if p.allowed_suffixes and not q.endswith(p.allowed_suffixes):
            bad.append(f)
            continue
        if not any(q.startswith(root) for root in p.allowed_roots):
            bad.append(f)
    return bad


# ── 헬스체크 ──────────────────────────────────────────────────────────────

def _health_http(p: Profile) -> tuple[bool, str]:
    """플랫폼이 응답하는지. 재기동 직후엔 잠깐 안 뜨므로 잠시 기다려 준다."""
    deadline = time.time() + HEALTH_TIMEOUT
    last = ""
    while time.time() < deadline:
        rc, out, _e = _run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", p.health_url],
                           cwd=p.tree, timeout=20)
        last = out.strip()
        if rc == 0 and last and last[0] in "23":
            return True, last
        time.sleep(3)
    return False, last or "무응답"


def _svc_prop(p: Profile, prop: str) -> str:
    if RUNTIME == "docker":
        # systemd 속성 이름을 docker inspect 로 흉내낸다: ActiveState(active/failed), SubState(running), NRestarts(RestartCount)
        name = WEB_CONTAINER if p.name == "platform" else WATCHER_CONTAINER
        fmt = {"ActiveState": "{{if .State.Running}}active{{else}}failed{{end}}",
               "SubState": "{{.State.Status}}", "NRestarts": "{{.RestartCount}}"}.get(prop, "{{.State.Status}}")
        rc, out, _e = _run(["docker", "inspect", "-f", fmt, name], cwd=p.tree, timeout=20)
        return out.strip() if rc == 0 else ""
    rc, out, _e = _run(["systemctl", "--user", "show", p.service, "-p", prop, "--value"],
                       cwd=p.tree, timeout=20)
    return out.strip() if rc == 0 else ""


def _health_service(p: Profile, since: float, restarts_before: str = "0") -> tuple[bool, str]:
    """워처가 재기동 후 살아서 시작 로그를 찍었는지.

    HTTP 가 없는 데몬이라 세 가지를 본다: ① 유닛이 failed 가 아님 ② 재기동 이후 로그에
    시작 마커가 찍힘 ③ 그 뒤로 몇 초를 더 버팀(시작 직후 죽는 경우를 잡기 위해 —
    Restart=on-failure 라 죽어도 systemd 가 되살려 "active" 로 보일 수 있다).
    """
    deadline = time.time() + HEALTH_TIMEOUT
    marker_seen_at: float | None = None
    last = ""
    while time.time() < deadline:
        state = _svc_prop(p, "ActiveState")
        sub = _svc_prop(p, "SubState")
        restarts = _svc_prop(p, "NRestarts")
        last = f"{state}/{sub} restarts={restarts}"
        if state == "failed" or (restarts and restarts != restarts_before):
            return False, last
        if marker_seen_at is None and state == "active" and _log_has_marker_since(p, since):
            marker_seen_at = time.time()
        if marker_seen_at is not None and time.time() - marker_seen_at >= 8 and state == "active":
            return True, last
        time.sleep(2)
    return False, last or "무응답"


def _log_has_marker_since(p: Profile, since: float) -> bool:
    if not p.health_log_marker:
        return True
    if RUNTIME == "docker":
        # 컨테이너는 stdout 으로 로그를 낸다 — 파일 대신 docker logs 에서 마커를 찾는다
        name = WEB_CONTAINER if p.name == "platform" else WATCHER_CONTAINER
        rc, out, err = _run(["docker", "logs", "--since", datetime.fromtimestamp(since - 1, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), name],
                            cwd=p.tree, timeout=30)
        return p.health_log_marker in (out or "") + (err or "")
    if not p.health_log:
        return True
    try:
        if os.path.getmtime(p.health_log) < since - 1:
            return False
        with open(p.health_log, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            f.seek(max(0, size - 64 * 1024))
            tail = f.read().decode("utf-8", "replace")
    except OSError:
        return False
    cutoff = datetime.fromtimestamp(since - 1).strftime("%Y-%m-%d %H:%M:%S")
    for line in tail.splitlines():
        if p.health_log_marker in line and line[:19] >= cutoff:
            return True
    return False


def _health(p: Profile, since: float, restarts_before: str = "0") -> tuple[bool, str]:
    if p.health_url:
        return _health_http(p)
    watcher_restarts, _, learner_restarts = restarts_before.partition(":")
    ok, detail = _health_service(p, since, watcher_restarts)
    if ok and RUNTIME == "docker" and p.name == "watcher":
        rc, out, err = _run(["docker", "inspect", "-f", "{{.State.Running}} {{.RestartCount}}", LEARNER_CONTAINER],
                            cwd=p.tree, timeout=20)
        ok = rc == 0 and out.strip() == "true " + learner_restarts
        detail += f"; learner={out.strip() or err[:200]}"
    return ok, detail


# ── 빌드 ─────────────────────────────────────────────────────────────────

def _build(p: Profile, files: list[str]) -> tuple[bool, str]:
    """성공 여부와 (실패 시) 오류 꼬리."""
    if p.name == "platform":
        if RUNTIME == "docker":
            # 소스 볼륨은 web 컨테이너와 공유된다 — 빌드는 node 가 있는 web 컨테이너 안에서
            rc, out, err = _run(["docker", "exec", "-w", "/srv/web", WEB_CONTAINER, "npm", "run", "build"], cwd=p.tree, timeout=900)
        else:
            rc, out, err = _run(["npm", "run", "build"], cwd=p.tree, timeout=900)
        if rc != 0:
            return False, "\n".join((err or out).strip().splitlines()[-12:])[:1500]
        return True, ""

    # watcher: 컴파일 → import. import 는 실제 환경(.env 가 os.environ 에 이미 있음)에서
    # 돌려 NameError·ImportError 같이 py_compile 이 못 잡는 것을 잡는다.
    # 현재 PC 는 venv, 컨테이너는 이미지의 파이썬(의존성 내장) — venv 가 없으면 지금 실행 중인 인터프리터로
    import sys as _sys
    py = os.path.join(p.tree, "venv", "bin", "python")
    if not os.path.exists(py):
        py = _sys.executable
    present = [f for f in files if os.path.exists(os.path.join(p.tree, f))]
    if present:
        rc, out, err = _run([py, "-m", "py_compile", *present], cwd=p.tree, timeout=120)
        if rc != 0:
            return False, (err or out).strip()[-1500:]
    mods = [os.path.splitext(f)[0] for f in present if f.endswith(".py")]
    if mods:
        code = "import importlib,sys\n" + "".join(f"importlib.import_module({m!r})\n" for m in mods)
        try:
            rc, out, err = _run([py, "-c", code], cwd=p.tree, timeout=90)
        except subprocess.TimeoutExpired:
            return False, "import 검사가 90초 안에 끝나지 않았습니다 — 모듈 최상위에서 무언가를 기다리고 있습니다"
        if rc != 0:
            return False, (err or out).strip()[-1500:]
    return True, ""


def _col(p: Profile):
    from pymongo import MongoClient
    cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return cli, cli[DB_NAME][p.ledger]


def _record(p: Profile, doc: dict[str, Any]) -> None:
    try:
        cli, col = _col(p)
        col.insert_one({"target": p.name, **doc})
        cli.close()
    except Exception as e:  # noqa: BLE001
        log.warning("%s 원장 기록 실패(무시): %s: %s", p.name, type(e).__name__, e)


def dry_run(patch: str, p: Profile = PLATFORM) -> dict[str, Any]:
    try:
        files = patch_files(patch)
    except (ValueError, SyntaxError, UnicodeError, IndexError, OSError, subprocess.TimeoutExpired) as e:
        return {"files": [], "ok": False, "target": p.name, "reason": f"패치 경로를 해석할 수 없습니다: {e}"}
    res: dict[str, Any] = {"files": files, "ok": False, "target": p.name}
    bad = check_scope(files, p)
    res["out_of_scope"] = bad
    if bad:
        res["reason"] = (f"{p.name} 에서 고칠 수 있는 곳은 {p.scope_label} 뿐입니다. "
                         "범위 밖: " + ", ".join(bad[:5]))
        return res
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8", newline="\n") as f:
        f.write(patch if patch.endswith("\n") else patch + "\n")
        pf = f.name
    try:
        rc, _o, err = _git(p, "apply", "--check", "--recount", pf)
        res["applies"] = rc == 0
        if rc != 0:
            res["reason"] = "지금 코드에 붙지 않습니다: " + (err.strip().splitlines() or ["원인 불명"])[0][:200]
            return res
    finally:
        try:
            os.unlink(pf)
        except OSError:
            pass
    res["ok"] = True
    return res


def _restore(p: Profile, rollback_sha: str, next_backup: str | None) -> bool:
    """되돌아간다. 여기서 실패하면 사람이 개입해야 하므로 로그를 남긴다."""
    rc, _out, err = _git(p, "reset", "--hard", rollback_sha)
    if rc:
        log.error("코드 복원 실패: %s", err)
        return False
    if next_backup and os.path.isdir(next_backup):
        live = os.path.join(p.tree, ".next")
        try:
            if os.path.isdir(live):
                shutil.rmtree(live)
            shutil.move(next_backup, live)
        except Exception:  # noqa: BLE001
            log.exception("빌드 산출물 복원 실패 — 재빌드가 필요하다")
            return False
    return True


def _checked_build(p: Profile, files: list[str]) -> tuple[bool, str]:
    try:
        return _build(p, files)
    except Exception as e:  # 빌드 예외도 동일한 복구·원장 경로로 보낸다.
        return False, f"{type(e).__name__}: {e}"[:1500]


def _restart_and_check(p: Profile) -> tuple[bool, str]:
    try:
        since, nr = _restart(p)
        return _health(p, since, nr)
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"[:1500]


def _restart(p: Profile) -> tuple[float, str]:
    """재기동하고 (시각, 재기동 전 NRestarts) 를 돌려준다.
    NRestarts 는 누적값이라 절대값이 아니라 **증가 여부**로 시작 직후 사망을 판정한다."""
    before = _svc_prop(p, "NRestarts") or "0"
    since = time.time()
    if RUNTIME == "docker":
        names = [WEB_CONTAINER] if p.name == "platform" else [WATCHER_CONTAINER, LEARNER_CONTAINER]
        if p.name == "watcher":
            rc, out, err = _run(["docker", "inspect", "-f", "{{.RestartCount}}", LEARNER_CONTAINER], cwd=p.tree, timeout=20)
            if rc:
                raise RuntimeError(f"learner 확인 실패: {err}")
            before += ":" + out.strip()
        rc, _out, err = _run(["docker", "restart", *names], cwd=p.tree, timeout=180)
    else:
        rc, _out, err = _run(["systemctl", "--user", "restart", p.service], cwd=p.tree, timeout=180)
    if rc:
        raise RuntimeError(f"재기동 실패: {err}")
    return since, before


def deploy(patch: str, task_id: str, title: str, actor: str, p: Profile = PLATFORM) -> dict[str, Any]:
    """변경을 적용·빌드·재기동한다. 잘못되면 스스로 되돌린다.

    **모든 결말을 원장에 남긴다** — 분리 실행(detached)에서는 stdout 이 아무에게도
    안 보이므로, 원장이 유일한 결과 통로다. 실측: 사전 검사 실패가 기록되지 않아
    클라이언트 폴링이 6분을 빈손으로 기다렸다.
    """
    pre = dry_run(patch, p)
    if not pre.get("ok"):
        _record(p, {"task_id": task_id, "task_title": title, "files": pre.get("files") or [],
                    "status": "rejected", "applied_by": actor,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "error": str(pre.get("reason") or "")[:500]})
        return {"ok": False, **pre}
    files = pre["files"]

    rc, sha, _e = _git(p, "rev-parse", "HEAD")
    rollback = sha.strip()
    if not rollback:
        return {"ok": False, "reason": "현재 커밋을 확인할 수 없습니다(git 저장소가 맞습니까?)"}

    # 빌드가 실패하면 .next 가 반쯤 덮어써진 채로 남는다. 미리 떠 둔다.
    next_backup = None
    live_next = os.path.join(p.tree, ".next")
    if p.backs_up_next and os.path.isdir(live_next):
        next_backup = live_next + ".rollback"
        if os.path.isdir(next_backup):
            shutil.rmtree(next_backup)
        shutil.copytree(live_next, next_backup, symlinks=True)

    steps: list[str] = []

    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8", newline="\n") as f:
        f.write(patch if patch.endswith("\n") else patch + "\n")
        pf = f.name
    try:
        rc, _o, err = _git(p, "apply", "--recount", pf)
        if rc != 0:
            _restore(p, rollback, next_backup)
            _record(p, {"task_id": task_id, "task_title": title, "files": files,
                        "status": "apply_failed", "applied_by": actor,
                        "at": datetime.now(timezone.utc).isoformat(),
                        "error": err.strip()[:500]})
            return {"ok": False, "reason": f"적용 실패: {err.strip()[:300]}", "files": files}
    finally:
        try:
            os.unlink(pf)
        except OSError:
            pass
    steps.append("패치 적용")

    _git(p, "add", "--", *files)
    digest = hashlib.sha256(patch.encode("utf-8")).hexdigest()[:12]
    msg = (f"{title[:72]}\n\nProjectHub task: {task_id}\nApplied-by: {actor}\n"
           f"Patch-sha256: {digest}\n")
    rc, _o, err = _git(p, "-c", "user.name=hermes", "-c", "user.email=hermes@newplay.local",
                       "commit", "--author", f"{actor} <{actor}>", "-m", msg)
    if rc != 0:
        _restore(p, rollback, next_backup)
        return {"ok": False, "reason": f"커밋 실패: {err.strip()[:300]}", "files": files}
    _rc, newsha, _e = _git(p, "rev-parse", "--short", "HEAD")
    commit = newsha.strip()
    steps.append(f"커밋 {commit}")

    # ── 빌드. 여기서 실패하면 **서비스는 아직 건드리지 않았다**.
    ok, build_err = _checked_build(p, files)
    if not ok:
        recovered = _restore(p, rollback, next_backup)
        _record(p, {"task_id": task_id, "task_title": title, "files": files, "commit": commit,
                    "status": "build_failed", "applied_by": actor,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "error": build_err, "recovered": recovered})
        return {"ok": False, "reason": "빌드 실패 — 이전 상태로 복원했습니다." if recovered else "빌드 실패 — 복원도 실패했습니다. 수동 복구가 필요합니다.",
                "recovered": recovered, "build_error": build_err, "files": files, "steps": steps}
    steps.append("빌드 성공")

    # ── 재기동 + 헬스체크. 여기부터가 실제 위험 구간이다.
    ok, code = _restart_and_check(p)
    if not ok:
        steps.append(f"헬스체크 실패({code}) — 되돌리는 중")
        restored = _restore(p, rollback, next_backup)
        ok2, code2 = _restart_and_check(p) if restored else (False, "코드/산출물 복원 실패")
        _record(p, {"task_id": task_id, "task_title": title, "files": files, "commit": commit,
                    "status": "rolled_back" if ok2 else "recovery_failed", "applied_by": actor, "recovered": ok2,
                    "at": datetime.now(timezone.utc).isoformat(),
                    "error": f"헬스체크 {code} → 자동 복구 {'성공' if ok2 else '실패'}({code2})"})
        return {"ok": False,
                "reason": (f"배포 후 {p.name} 이 응답하지 않아 자동으로 되돌렸습니다."
                           + ("" if ok2 else " **복구도 실패했습니다 — SSH 로 rollback.sh 를 돌려야 합니다.**")),
                "recovered": ok2, "files": files, "steps": steps}

    steps.append(f"헬스체크 통과({code})")
    if next_backup and os.path.isdir(next_backup):
        shutil.rmtree(next_backup, ignore_errors=True)

    _record(p, {"task_id": task_id, "task_title": title, "files": files, "commit": commit,
                "base": rollback[:7], "patch_sha256": digest,
                "status": "deployed", "applied_by": actor,
                "at": datetime.now(timezone.utc).isoformat()})
    return {"ok": True, "commit": commit, "files": files, "steps": steps, "target": p.name}


def rollback_to(commit: str, actor: str, p: Profile = PLATFORM) -> dict[str, Any]:
    """지정 커밋으로 되돌리고 다시 배포한다."""
    if not re.fullmatch(r"[0-9a-f]{7,40}", commit or ""):
        return {"ok": False, "reason": "커밋 해시 형식이 아닙니다"}
    rc, original, err = _git(p, "rev-parse", "HEAD")
    if rc:
        return {"ok": False, "reason": f"현재 커밋 확인 실패: {err[:300]}"}
    next_backup = None
    live_next = os.path.join(p.tree, ".next")
    if p.backs_up_next and os.path.isdir(live_next):
        next_backup = tempfile.mkdtemp(prefix=".next-rollback-", dir=p.tree)
        shutil.copytree(live_next, next_backup, dirs_exist_ok=True, symlinks=True)
    rc, _o, err = _git(p, "-c", "user.name=hermes", "-c", "user.email=hermes@newplay.local",
                       "revert", "--no-edit", commit)
    if rc != 0:
        _git(p, "revert", "--abort")
        if next_backup:
            shutil.rmtree(next_backup, ignore_errors=True)
        _record(p, {"status": "rollback_failed", "revert_of": commit, "healthy": False,
                    "applied_by": actor, "at": datetime.now(timezone.utc).isoformat(), "error": err[:500]})
        return {"ok": False, "reason": f"되돌리기 실패: {err.strip()[:300]}"}
    _rc, changed, _e = _git(p, "diff", "--name-only", "HEAD~1", "HEAD")
    built, build_err = _checked_build(p, [f for f in changed.split("\n") if f.strip()])
    ok, code = _restart_and_check(p) if built else (False, build_err)
    if not ok:
        restored = _restore(p, original.strip(), next_backup)
        recovered, recovery_detail = _restart_and_check(p) if restored and built else (restored, "빌드 전 상태 복원")
        reason = f"되돌리기 실패({code}); 원상 복구 {'성공' if recovered else '실패'}({recovery_detail})"
        _record(p, {"status": "rollback_failed", "revert_of": commit, "healthy": False,
                    "recovered": recovered, "applied_by": actor,
                    "at": datetime.now(timezone.utc).isoformat(), "error": reason[:1500]})
        return {"ok": False, "target": p.name, "reason": reason, "recovered": recovered}
    _rc, sha, _e = _git(p, "rev-parse", "--short", "HEAD")
    _record(p, {"status": "reverted", "revert_of": commit, "commit": sha.strip(),
                "applied_by": actor, "at": datetime.now(timezone.utc).isoformat(),
                "healthy": ok})
    if next_backup:
        shutil.rmtree(next_backup, ignore_errors=True)
    return {"ok": ok, "revert_commit": sha.strip(), "target": p.name,
            "reason": "" if ok else f"되돌렸으나 헬스체크 실패({code})"}


def history(limit: int = 30, p: Profile = PLATFORM) -> list[dict[str, Any]]:
    try:
        cli, col = _col(p)
        try:
            return [{k: v for k, v in d.items() if k != "_id"}
                    for d in col.find({}).sort("at", -1).limit(limit)]
        finally:
            cli.close()
    except Exception:  # noqa: BLE001
        return []
