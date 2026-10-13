#!/usr/bin/env python3
"""
project_fork — Fork로 신규 프로젝트 생성 (소스 Git → 새 Git → 등록)

지수님 수동 흐름의 자동화:
  ① 소스 Git에서 완성 baseline pull   → git clone --origin baseline
  ② 새 원격 Git 생성                    → gh repo create (빌드 호스트 gh 인증)
  ③ 새 Git에 연동 = 신규 프로젝트        → --remote origin --push
  ④ (수동엔 없던) 계약 상속 + 출처 등록   → qa 카탈로그 복사 + hermes_projects

git/gh 명령은 빌드 호스트(머신 B, Windows)에서 SSH로 실행한다 —
Mother엔 gh도 GitHub 접근키도 없고, 빌드 호스트가 gh(jisupark-tech) 인증을 갖고 있다.

CLI:
  python project_fork.py --new MyGame --baseline BalloonFlow --dry-run
  python project_fork.py --new MyGame --baseline BalloonFlow
  python project_fork.py --new _smoketest --baseline BalloonFlow --shallow --delete-after
"""
from __future__ import annotations
import argparse, os, re, subprocess, sys, datetime

MACHINE_B_HOST = os.environ.get("MACHINE_B_HOST", "user@100.92.43.9")
PROJECTS_ROOT = os.environ.get("MACHINE_B_PROJECTS_ROOT", "C:/projects")
DEFAULT_OWNER = os.environ.get("GITHUB_REPO_OWNER", "jisupark-tech")
# executor 규약과 일치: MONGODB_URI / MONGODB_DB (legacy MONGO_* 도 폴백)
MONGO_URI = os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI", "")
DB_NAME = os.environ.get("MONGODB_DB") or os.environ.get("MONGO_DB", "aigame")
# baseline 이름 → {owner, name, dir}. 미등록 baseline은 hermes_projects 조회로 보강.
KNOWN_BASELINES = {
    "balloonflow": {"owner": "jisupark-tech", "name": "BalloonFlow", "dir": "C:/projects/balloonflow"},
}

NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{1,48}$")


class ForkError(Exception):
    """fork 실패 — 라이브러리로 쓰일 때 SystemExit 대신 사용(워처 프로세스 보호)."""


def _run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=timeout, check=False)


def _ssh_b(win_cmd: str, timeout: int = 300) -> subprocess.CompletedProcess:
    """빌드 호스트에서 Windows cmd 실행."""
    return _run(["ssh", "-o", "BatchMode=yes", MACHINE_B_HOST, win_cmd], timeout=timeout)


def resolve_baseline(name: str) -> dict:
    key = (name or "").strip().lower()
    if key in KNOWN_BASELINES:
        return KNOWN_BASELINES[key]
    # hermes_projects 레지스트리에서 조회
    if MONGO_URI:
        try:
            from pymongo import MongoClient
            c = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            try:
                doc = c[DB_NAME]["hermes_projects"].find_one({"project": key}, {"repo": 1, "_id": 0})
            finally:
                c.close()
            repo = (doc or {}).get("repo") or {}
            if repo.get("name"):
                return {"owner": repo.get("owner") or DEFAULT_OWNER,
                        "name": repo["name"], "dir": repo.get("dir") or f"{PROJECTS_ROOT}/{key}"}
        except Exception as e:
            print(f"[warn] baseline 레지스트리 조회 실패: {e}", file=sys.stderr)
    raise ForkError(f"[error] baseline '{name}' 을 알 수 없음 (KNOWN_BASELINES / hermes_projects 미등록)")


def fork_project(new_name: str, baseline: str, owner: str = DEFAULT_OWNER,
                 private: bool = True, shallow: bool = False,
                 dry_run: bool = False, delete_after: bool = False) -> dict:
    if not NAME_RE.match(new_name):
        raise ForkError(f"[error] 잘못된 프로젝트명: {new_name!r} (영문 시작, 2~49자, [A-Za-z0-9_-])")

    base = resolve_baseline(baseline)
    base_url = f"https://github.com/{base['owner']}/{base['name']}.git"
    new_dir = f"{PROJECTS_ROOT}/{new_name}"
    new_slug = f"{owner}/{new_name}"
    vis = "--private" if private else "--public"
    # 주의: 얕은 clone(--depth)은 새 원격으로 push 시 index-pack 실패 → 항상 전체 clone.
    if shallow:
        print("[warn] --shallow 무시: 얕은 clone은 새 레포 push가 불가(index-pack 실패)", file=sys.stderr)

    # STEP 1: 소스 Git clone (origin을 baseline으로 명명 → 상류 유지)
    clone_cmd = f'git clone --origin baseline {base_url} "{new_dir}"'
    # STEP 2+3: 새 원격 Git 생성 + origin 연결 + push
    create_cmd = f'cd /d "{new_dir}" && gh repo create {new_slug} {vis} --source . --remote origin --push'
    sha_cmd = f'git -C "{new_dir}" rev-parse HEAD'

    plan = {
        "new_name": new_name, "new_slug": new_slug, "new_dir": new_dir,
        "baseline": f"{base['owner']}/{base['name']}", "baseline_url": base_url,
        "commands": [
            f"[preflight] gh repo view {new_slug}  (존재하면 중단)",
            f"[preflight] dir exists? {new_dir}  (존재하면 중단)",
            f"[step1] {clone_cmd}",
            f'[step1b] git -C "{new_dir}" lfs fetch --all baseline  (LFS 객체 확보)',
            f"[step2+3] {create_cmd}",
            f"[sha] {sha_cmd}",
            f"[step4] qa/features/{baseline.lower()}.yaml → qa/features/{new_name.lower()}.yaml (계약 상속)",
            f"[step4] hermes_projects insert (forked_from={base['name']}, fork_sha=...)",
        ],
    }

    if dry_run:
        plan["dry_run"] = True
        return plan

    # ── preflight guards (클로버 방지) ──
    view = _ssh_b(f"gh repo view {new_slug}", timeout=30)
    if view.returncode == 0:
        raise ForkError(f"[error] 이미 존재하는 레포: {new_slug} — 중단")
    dir_check = _ssh_b(f'if exist "{new_dir}" (echo DIR_EXISTS) else (echo DIR_FREE)', timeout=30)
    if "DIR_EXISTS" in dir_check.stdout:
        raise ForkError(f"[error] 이미 존재하는 디렉터리: {new_dir} — 중단")

    # ── STEP 1: clone ──
    print(f"[step1] clone {base_url} → {new_dir}")
    r1 = _ssh_b(clone_cmd, timeout=1800)
    if r1.returncode != 0:
        raise ForkError(f"[error] clone 실패:\n{r1.stderr[-800:]}")

    # ── STEP 1b: LFS 객체 전량 확보 ──
    # baseline이 Git LFS를 쓰면 clone만으론 일부 객체가 로컬에 없어 새 레포 push가 실패한다
    # (index-pack / missing object). baseline 리모트에서 모든 LFS 객체를 받아둔다.
    print("[step1b] git lfs fetch --all baseline")
    rlfs = _ssh_b(f'git -C "{new_dir}" lfs fetch --all baseline', timeout=1800)
    if rlfs.returncode != 0:
        print(f"[warn] lfs fetch 경고(비 LFS 레포면 무시): {rlfs.stderr[-300:]}", file=sys.stderr)

    # ── STEP 2+3: create new remote + push (LFS 포함) ──
    print(f"[step2+3] gh repo create {new_slug} + push")
    r2 = _ssh_b(create_cmd, timeout=1800)
    if r2.returncode != 0:
        # 롤백: 로컬 clone 삭제 + 이미 생성됐을 수 있는 원격 레포 삭제 시도
        _ssh_b(f'rmdir /s /q "{new_dir}"', timeout=120)
        del_r = _ssh_b(f"gh repo delete {new_slug} --yes", timeout=60)
        orphan = "" if del_r.returncode == 0 else (
            f"\n[!] 원격 레포 {new_slug} 가 생성됐으나 자동 삭제 실패 "
            f"— gh 토큰에 delete_repo 스코프 필요. 수동 정리 요망.")
        raise ForkError(f"[error] gh repo create/push 실패 (롤백 시도함):\n{r2.stderr[-800:]}{orphan}")

    sha = (_ssh_b(sha_cmd, timeout=30).stdout or "").strip().split()[0][:12] if True else ""

    # ── STEP 4: 계약 상속 (best-effort, Mother/monorepo 로컬 파일) ──
    catalog = _inherit_catalog(baseline.lower(), new_name.lower())

    # ── STEP 4: 출처 등록 ──
    registered = _register(new_name, owner, new_dir, base, sha)

    result = {
        "success": True,
        "new_repo": f"https://github.com/{new_slug}",
        "new_dir": new_dir,
        "baseline": f"{base['owner']}/{base['name']}",
        "fork_sha": sha,
        "catalog_inherited": catalog,
        "registered": registered,
        "remotes": "origin=신규 프로젝트, baseline=원본(상류)",
    }

    if delete_after:
        print(f"[cleanup] --delete-after → 테스트 레포/디렉터리 삭제")
        _ssh_b(f"gh repo delete {new_slug} --yes", timeout=60)
        _ssh_b(f'rmdir /s /q "{new_dir}"', timeout=120)
        _unregister(new_name)
        result["deleted_after"] = True

    return result


def _inherit_catalog(baseline_key: str, new_key: str) -> str:
    """qa/features/{baseline}.yaml → {new}.yaml 복사 (계약 상속). 로컬 파일 기준."""
    # feature_gate 와 동일 규약: QA_FEATURE_DIR, 기본은 모듈 옆 qa/features
    # (배포 위치 ~/.hermes/watcher/qa/features 에 실제 카탈로그가 있음)
    base_dir = os.environ.get("QA_FEATURE_DIR",
                              os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa", "features"))
    src = os.path.abspath(os.path.join(base_dir, f"{baseline_key}.yaml"))
    dst = os.path.abspath(os.path.join(base_dir, f"{new_key}.yaml"))
    if not os.path.isfile(src):
        return f"skip (baseline 카탈로그 없음: {src})"
    if os.path.isfile(dst):
        return f"skip (이미 존재: {dst})"
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = f.read()
        header = (f"# INHERITED from {baseline_key}.yaml on "
                  f"{datetime.datetime.now(datetime.timezone.utc).isoformat()}\n"
                  f"# 이 게임의 REQUIRED 기능 계약. 변환 스펙이 명시적으로 제거하지 않는 한 보존 대상.\n")
        with open(dst, "w", encoding="utf-8") as f:
            f.write(header + data)
        return f"inherited → {dst}"
    except Exception as e:
        return f"error: {e}"


def _register(new_name: str, owner: str, new_dir: str, base: dict, sha: str) -> str:
    if not MONGO_URI:
        return "skip (MONGO_URI 없음)"
    try:
        from pymongo import MongoClient
        c = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        try:
            c[DB_NAME]["hermes_projects"].update_one(
                {"project": new_name.lower()},
                {"$set": {
                    "project": new_name.lower(),
                    "repo": {"host": MACHINE_B_HOST, "dir": new_dir,
                             "owner": owner, "name": new_name, "type": "unity"},
                    "forked_from": base["name"],
                    "fork_sha": sha,
                    "created_by": "hermes",
                    "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                }},
                upsert=True,
            )
        finally:
            c.close()
        return f"hermes_projects.{new_name.lower()} (forked_from={base['name']}, sha={sha})"
    except Exception as e:
        return f"error: {e}"


def _unregister(new_name: str) -> None:
    if not MONGO_URI:
        return
    try:
        from pymongo import MongoClient
        c = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        try:
            c[DB_NAME]["hermes_projects"].delete_one({"project": new_name.lower()})
        finally:
            c.close()
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True, help="신규 프로젝트/레포 이름")
    ap.add_argument("--baseline", required=True, help="fork 원본 (예: BalloonFlow)")
    ap.add_argument("--owner", default=DEFAULT_OWNER)
    ap.add_argument("--public", action="store_true", help="공개 레포 (기본 private)")
    ap.add_argument("--shallow", action="store_true", help="--depth 1 얕은 clone (테스트용)")
    ap.add_argument("--dry-run", action="store_true", help="명령 계획만 출력, 부작용 없음")
    ap.add_argument("--delete-after", action="store_true", help="생성 후 즉시 삭제 (스모크 테스트)")
    a = ap.parse_args()

    try:
        res = fork_project(a.new, a.baseline, owner=a.owner, private=not a.public,
                           shallow=a.shallow, dry_run=a.dry_run, delete_after=a.delete_after)
    except ForkError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    print()
    if res.get("dry_run"):
        print(f"=== DRY RUN: {res['new_slug']}  ⟵  {res['baseline']} ===")
        for c in res["commands"]:
            print("  " + c)
    else:
        import json
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
