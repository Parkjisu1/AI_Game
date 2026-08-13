#!/usr/bin/env python3
"""
qa_compile_report.py — Unity batchmode 컴파일 결과를 기능 QA 의 ②등급 입력으로 만든다.

기능 QA 는 ②컴파일 칸을 "결과 파일이 있을 때만" 판정한다(없으면 미실행).
이 스크립트가 그 결과 파일 `~/.hermes/qa/<project>-compile.json` 을 만든다.

  {ok, verdict, finishedAt, projectPath, errors:[{file,line,code,msg}], tail}

핵심 설계
  - Machine B 에서 **CI 클론**(HERMES_CI_CLONE_DIR)을 컴파일한다. 작업 repo 는 Unity Editor 가
    열고 있어서 batchmode 가 막히기 때문(실측: Unity.exe 상주). CI 클론은 origin/main 으로
    리셋해서 쓰므로 작업 트리를 건드리지 않는다.
  - 에러 파일 경로는 그래프 노드 id(`Analytics/AnalyticsConsts.cs` 형태)와 맞물리도록
    `/1.Scripts/` 이후로 잘라 둔다 — 판정기가 endsWith 로 매칭한다.
  - **판정 불가와 통과를 구분한다.** 에디터 점유·타임아웃은 ok=None 으로 남기고,
    판정기는 그걸 '미실행'으로 표시한다. 여기서 통과로 뭉개면 거짓 초록이 된다.

사용: python qa_compile_report.py [--project balloonflow] [--timeout 900]
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv  # noqa: E402
load_dotenv("/home/aimed/.hermes/watcher/.env")
import graph_projects  # noqa: E402

OUT_DIR = os.environ.get("QA_COMPILE_DIR", "/home/aimed/.hermes/qa")
UNITY = os.environ.get("MACHINE_B_UNITY_EXE",
                       "C:/Program Files/Unity/Hub/Editor/6000.2.7f2/Editor/Unity.exe")
ERR_RE = re.compile(r"^(?P<file>[^(\n]+?)\((?P<line>\d+),\d+\):\s*error\s+(?P<code>CS\d+):\s*(?P<msg>.+)$")


def ssh(host: str, cmd: str, timeout: int):
    return subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-o", "BatchMode=yes", host, cmd],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, check=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="balloonflow")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--work-repo", action="store_true",
                    help="CI 클론 대신 작업 repo 를 컴파일 (에디터가 닫혀 있을 때만)")
    # 실측: -nographics 로 CI 클론을 최초 임포트하면 SpriteAtlasImporter::PackSpriteAtlas 에서
    # Unity 가 크래시한다(exit=21). 아틀라스 패킹은 그래픽 디바이스를 탄다.
    # 그래서 그래픽 모드를 기본으로 두고, 필요할 때만 --nographics 로 끈다.
    ap.add_argument("--nographics", action="store_true", help="-nographics 로 실행(아틀라스 크래시 가능)")
    ap.add_argument("--if-stale", action="store_true",
                    help="직전 결과가 현재 그래프 커밋과 같으면 건너뛴다 (크론용 — Unity 는 비싸다)")
    a = ap.parse_args()

    cfg = graph_projects.resolve(a.project)
    if not cfg:
        print(f"프로젝트 설정 없음: {a.project}", file=sys.stderr)
        return 1

    # 크론에서 매시 도는데 커밋이 그대로면 Unity 를 또 켤 이유가 없다.
    # 판정 기준은 "그래프가 보고 있는 커밋" — 그것과 맞춰야 ②가 ①과 같은 코드를 말한다.
    if a.if_stale:
        try:
            with open(cfg["graph_file"], encoding="utf-8") as fp:
                gsha = re.search(r"@([0-9a-f]{7,40})", json.load(fp).get("generatedFrom", ""))
            prev_path = os.path.join(OUT_DIR, f"{a.project}-compile.json")
            if gsha and os.path.exists(prev_path):
                with open(prev_path, encoding="utf-8") as fp:
                    prev = json.load(fp)
                if prev.get("sha") and gsha.group(1).startswith(prev["sha"]) and prev.get("ok") is not None:
                    print(json.dumps({"skipped": True, "reason": f"이미 {prev['sha']} 판정됨", "verdict": prev.get("verdict")}, ensure_ascii=False))
                    return 0
        except Exception:
            pass  # 판단 못 하면 그냥 컴파일한다

    host = cfg["host"]
    ci = os.environ.get("HERMES_CI_CLONE_DIR", "").strip()
    if a.work_repo or not ci:
        proj_root = cfg["repo_dir"]          # 예: C:/projects/balloonflow/BalloonFlow
        source = "work-repo"
    else:
        # CI 클론의 origin 은 **작업 repo** 다. 그래서 `origin/main` 은 작업 repo 의 *로컬* main 이고,
        # 그래프가 쓰는 GitHub origin/main 과 다를 수 있다(실측: 컴파일 09549c1a vs 그래프 54df2a1b —
        # 다른 커밋을 컴파일해 놓고 통과라고 말할 뻔했다).
        # 작업 repo 의 remote-tracking ref 를 통째로 당겨와 그것으로 맞춘다.
        ssh(host, f'git -C "{ci}" fetch origin "+refs/remotes/origin/{cfg["branch"].split("/")[-1]}:refs/remotes/ghmain"', 240)
        rr = ssh(host, f'git -C "{ci}" reset --hard refs/remotes/ghmain', 120)
        if rr.returncode != 0:  # 폴백 — 최소한 컴파일은 돌린다(SHA 대조가 잡아준다)
            ssh(host, f'git -C "{ci}" fetch origin', 180)
            ssh(host, f'git -C "{ci}" reset --hard origin/main', 120)
        proj_root = f'{ci}/{cfg.get("subdir") or ""}'.rstrip("/")
        source = "ci-clone"
        # 스프라이트 아틀라스 패킹 끄기 (CI 클론 한정, reset 뒤에 매번 적용).
        # 실측: 에셋 최초/재임포트 때 SpriteAtlasImporter::PackSpriteAtlas 에서 Unity 가
        # 크래시해 exit=21 로 죽는다(그래픽 모드에서도 동일). 우리가 알고 싶은 건 CS 에러뿐이고
        # 아틀라스 패킹은 컴파일과 무관하므로 끈다. 작업 repo 는 건드리지 않는다.
        _es = f"{proj_root}/ProjectSettings/EditorSettings.asset"
        ssh(host, 'powershell -NoProfile -Command "'
                  f"(Get-Content '{_es}') -replace 'm_SpritePackerMode: .*','m_SpritePackerMode: 0' "
                  f"| Set-Content '{_es}'\"", 60)

    sha = (ssh(host, f'git -C "{proj_root}/.." rev-parse --short HEAD', 30).stdout or "").strip()[:12]
    gfx = " -nographics" if a.nographics else ""
    cmd = f'"{UNITY}" -batchmode -quit{gfx} -projectPath "{proj_root}" -logFile -'
    try:
        r = ssh(host, cmd, a.timeout)
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        rc = r.returncode
    except subprocess.TimeoutExpired:
        out, rc = "", None

    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    result: dict = {"project": a.project, "finishedAt": now, "projectPath": proj_root,
                    "source": source, "sha": sha, "errors": []}

    if rc is None:
        result.update(ok=None, verdict="indeterminate", reason=f"batchmode 타임아웃({a.timeout}s)")
    elif re.search(r"another Unity instance|Multiple Unity instances|already open|Lockfile",
                   out, re.IGNORECASE):
        result.update(ok=None, verdict="indeterminate", reason="Unity Editor 가 해당 프로젝트를 점유 중")
    else:
        seen: set = set()
        for ln in out.splitlines():
            m = ERR_RE.match(ln.strip())
            if not m:
                continue
            f = m.group("file").replace("\\", "/")
            if "/1.Scripts/" in f:
                f = f.split("/1.Scripts/")[1]
            key = (f, m.group("line"), m.group("code"))
            if key in seen:
                continue
            seen.add(key)
            result["errors"].append({"file": f, "line": int(m.group("line")),
                                     "code": m.group("code"), "msg": m.group("msg")[:200]})
        if result["errors"]:
            result.update(ok=False, verdict="errors")
        elif re.search(r"Compilation failed|Scripts have compiler errors", out):
            # 에러는 났는데 파일별 파싱이 안 된 경우 — 통과로 오인하면 안 된다.
            result.update(ok=None, verdict="indeterminate", reason="컴파일 실패했으나 파일별 파싱 불가")
        elif rc == 0:
            result.update(ok=True, verdict="clean")
        else:
            result.update(ok=None, verdict="indeterminate", reason=f"exit={rc} — 로그 판독 불가")

    result["tail"] = "\n".join(out.splitlines()[-25:])[:3000]
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{a.project}-compile.json")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(result, fp, ensure_ascii=False)
    print(json.dumps({"wrote": path, "verdict": result["verdict"],
                      "errors": len(result["errors"]), "sha": sha,
                      "reason": result.get("reason", "")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
