#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_onboard.py — 새 프로젝트/인수인계 레포 온보딩 분석기.

목적: Hermes가 BalloonFlow 외의 레포(새로 판 것 / 인수받은 진행 중인 것)에서도
정확히 작업을 이어가도록, 기존 그라운딩 자산 4종을 자동 생성한다.
  1) hermes_projects 레지스트리 (project→genre/team + repo 설정)  ← routing/scope
  2) scoped memory: teams/<genre>/<team>/projects/<project>.md + conventions.md
  3) ICS 초안: _ARCHITECTURE.md (레포 dir에 저장 옵션)
  4) (옵션) code_base 임베딩 트리거 안내

원칙(거짓 없음): 레포의 **실데이터만** 결정론적으로 수집(파일트리·핵심파일·git로그·
스택감지·TODO밀도) → LLM은 그 사실에 근거해서만 프로파일 합성(파일/시스템 창작 금지).

사용:
  # 로컬에 체크아웃된 레포 분석 (원격 레포는 먼저 /tmp에 clone)
  python project_onboard.py --project MyGame --genre casual --team dev \
      --path /tmp/mygame --mode handover \
      --host user@100.92.43.9 --dir C:/projects/mygame --owner myorg --name MyGame --type unity

  --mode new       : 갓 판 레포(스캐폴딩/초기) — 무엇을 갖췄고 무엇부터 만들지
  --mode handover  : 진행 중 인수 — 무엇이 done/미완이고 어떻게 이어갈지 (기본)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
from pymongo import MongoClient

load_dotenv("/home/aimed/.hermes/watcher/.env")
MEM_ROOT = Path(os.environ.get("HERMES_MEM_ROOT", "/home/aimed/.hermes/memories/teams"))
SKIP_DIRS = {".git", "node_modules", "Library", "obj", "bin", "Temp", "Logs", ".vs", "dist", "build", ".next", "venv", "__pycache__", "Packages"}
CODE_EXT = {".cs", ".js", ".jsx", ".ts", ".tsx", ".py", ".cpp", ".h", ".hpp", ".c", ".java", ".go", ".gd", ".lua", ".rs", ".kt", ".swift"}
# 에셋/바이너리 — 구조/샘플 분석에서 제외(파일 수 홍수 방지). ext_count에는 집계.
ASSET_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".ico", ".bmp", ".tga", ".psd",
             ".mp3", ".wav", ".ogg", ".aac", ".mp4", ".mov", ".ttf", ".otf", ".woff", ".woff2", ".eot",
             ".fbx", ".obj", ".anim", ".controller", ".mat", ".asset", ".meta", ".unity", ".prefab", ".spriteatlas"}


def sh(cmd: list[str], cwd: str | None = None, timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip()
    except Exception as e:  # noqa: BLE001
        return f"(err: {e})"


# ── 1. 결정론적 사실 수집 (레포 실데이터) ───────────────────────────
def gather(path: str) -> dict:
    root = Path(path)
    facts: dict = {"root": str(root)}
    files: list[str] = []          # 코드/설정 파일만 (에셋 제외)
    ext_count: dict[str, int] = {}  # 전체 확장자 집계 (에셋 포함 — 스택 감지용)
    asset_total = 0
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not d.startswith(".")]
        rel = os.path.relpath(dp, root)
        for fn in fns:
            ext = os.path.splitext(fn)[1].lower()
            ext_count[ext] = ext_count.get(ext, 0) + 1
            if ext in ASSET_EXT:
                asset_total += 1
                continue  # 에셋은 파일 목록서 제외 (홍수 방지)
            rp = os.path.normpath(os.path.join(rel, fn)) if rel != "." else fn
            files.append(rp)
        if len(files) > 6000:
            break
    facts["file_count"] = len(files)
    facts["asset_count"] = asset_total
    facts["ext_count"] = dict(sorted(ext_count.items(), key=lambda x: -x[1])[:15])
    # 상위 디렉토리 구조 (2뎁스) — 코드 파일 수 우선 정렬(에셋 디렉토리에 밀리지 않게)
    top_total: dict[str, int] = {}
    top_code: dict[str, int] = {}
    for f in files:
        parts = f.split(os.sep)
        key = parts[0] if len(parts) == 1 else os.sep.join(parts[:2])
        top_total[key] = top_total.get(key, 0) + 1
        if os.path.splitext(f)[1].lower() in CODE_EXT:
            top_code[key] = top_code.get(key, 0) + 1
    ranked = sorted(top_total.keys(), key=lambda k: (-top_code.get(k, 0), -top_total[k]))[:30]
    facts["structure"] = {k: {"files": top_total[k], "code": top_code.get(k, 0)} for k in ranked}

    # 스택 감지 (결정론적)
    names = {f.lower() for f in files}
    def has(sub: str) -> bool: return any(sub in n for n in names)
    stack = []
    if has("assets" + os.sep) or has("projectsettings") or ".unity" in facts["ext_count"] or ".prefab" in facts["ext_count"]:
        stack.append("Unity")
    if "package.json" in [os.path.basename(f).lower() for f in files]:
        stack.append("Node/JS")
    if any(os.path.basename(f).lower() in ("requirements.txt", "pyproject.toml") for f in files):
        stack.append("Python")
    if has("pubspec.yaml"):
        stack.append("Flutter")
    facts["detected_stack"] = stack or ["unknown"]

    # 핵심 파일 내용 (크기 제한)
    key_files: dict[str, str] = {}
    for pat in ["README.md", "README", "package.json", "ProjectSettings/ProjectVersion.txt", "CLAUDE.md", "pubspec.yaml", "pyproject.toml"]:
        p = root / pat
        if p.exists() and p.is_file():
            try: key_files[pat] = p.read_text(errors="ignore")[:2500]
            except Exception: pass
    # .csproj / .sln 이름
    facts["csproj"] = [f for f in files if f.lower().endswith((".csproj", ".sln"))][:20]
    facts["key_files"] = key_files

    # 코드 컨벤션 샘플: 소스 파일 6개의 상단 25줄 (namespace/구조 감지용)
    samples: dict[str, str] = {}
    srcs = [f for f in files if os.path.splitext(f)[1].lower() in CODE_EXT]
    for f in srcs[:6]:
        try:
            with open(root / f, errors="ignore") as fh:
                samples[f] = "".join(fh.readlines()[:25])[:1200]
        except Exception: pass
    facts["code_samples"] = samples

    # git 로그 + TODO 밀도
    facts["git_branch"] = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=path)
    facts["git_log"] = sh(["git", "log", "--oneline", "-20"], cwd=path)
    facts["git_branches"] = sh(["git", "branch", "-a"], cwd=path)[:1500]
    excl = " ".join(f"--exclude-dir={d}" for d in SKIP_DIRS)
    grep = sh(["bash", "-lc", f"grep -rIn {excl} --include=*.cs --include=*.js --include=*.jsx --include=*.ts --include=*.tsx --include=*.py -E 'TODO|FIXME|HACK|XXX' {path!r} 2>/dev/null | wc -l"])
    facts["todo_markers"] = grep.strip()
    return facts


# ── 2. LLM 합성 (사실 기반, 창작 금지) ──────────────────────────────
SYS = """You are onboarding an autonomous dev team onto a REAL code repository.
Analyze ONLY the provided factual observations (file tree, structure, key file contents, code samples, git log, detected stack, TODO density).
Produce a JSON project profile that lets coder agents continue work accurately WITHOUT re-exploring.
STRICT: do NOT invent files, systems, or facts not evidenced by the observations. If unknown → null or "unknown".

Return JSON only:
{
 "engine": "Unity|Node|Python|... (from detected_stack)",
 "language": "",
 "build_command": "best guess from evidence or 'unknown'",
 "summary": "2-3 문장, 이 프로젝트가 무엇인지 (한국어)",
 "structure": [{"dir":"","purpose":"한국어 역할"}],
 "conventions": {"namespace_pattern":"코드샘플서 관찰된 것 or null","file_naming":"","notable":["관찰된 패턴 0-5"]},
 "key_systems": [{"name":"","evidence_files":["관찰된 파일만"],"responsibility":"한국어"}],
 "entry_points": ["관찰된 진입점 파일/씬 or []"],
 "state": {"maturity":"scaffold|early|in_progress|mature","done_summary":"한국어 관찰기반","incomplete":["미완/TODO 근거 항목 (한국어)"]},
 "continue_guidance": ["이 레포에서 안전하게 작업 이어가는 지침 3-6 (한국어, 컨벤션·주의점)"],
 "risks": ["관찰된 리스크 (한국어)"],
 "confidence": "high|medium|low (증거 충분도)"
}"""


def synthesize(facts: dict, mode: str) -> dict:
    cli = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    payload = json.dumps(facts, ensure_ascii=False)[:24000]
    r = cli.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYS},
            {"role": "user", "content": f"mode={mode}\n관찰 사실(JSON):\n{payload}"},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    return json.loads(r.choices[0].message.content or "{}")


# ── 3. 영속화 (기존 그라운딩 자산으로) ──────────────────────────────
def profile_to_md(project: str, genre: str, team: str, repo: dict, profile: dict, mode: str) -> str:
    p = profile
    lines = [f"# 프로젝트 프로파일 — {project}", "",
             f"> 온보딩({mode}) 자동 생성 · genre={genre} team={team} · confidence={p.get('confidence','?')}", "",
             f"**엔진/언어**: {p.get('engine','?')} / {p.get('language','?')}  ",
             f"**빌드**: `{p.get('build_command','unknown')}`  ",
             f"**레포**: {repo.get('host','?')}:{repo.get('dir','?')} ({repo.get('owner','?')}/{repo.get('name','?')}, {repo.get('type','code')})", "",
             f"## 개요\n{p.get('summary','')}", "",
             "## 디렉토리 구조"]
    for s in p.get("structure", []): lines.append(f"- `{s.get('dir','')}` — {s.get('purpose','')}")
    c = p.get("conventions", {}) or {}
    lines += ["", "## 컨벤션", f"- 네임스페이스: `{c.get('namespace_pattern') or 'unknown'}`", f"- 파일 네이밍: {c.get('file_naming','')}"]
    for n in (c.get("notable") or []): lines.append(f"- {n}")
    lines += ["", "## 핵심 시스템"]
    for k in p.get("key_systems", []): lines.append(f"- **{k.get('name','')}** — {k.get('responsibility','')} ({', '.join(k.get('evidence_files',[])[:4])})")
    st = p.get("state", {}) or {}
    lines += ["", f"## 상태 ({st.get('maturity','?')})", st.get("done_summary", "")]
    if st.get("incomplete"): lines += ["", "### 미완/이어할 것"] + [f"- {x}" for x in st["incomplete"]]
    if p.get("continue_guidance"): lines += ["", "## 작업 이어가기 지침"] + [f"- {x}" for x in p["continue_guidance"]]
    if p.get("risks"): lines += ["", "## 리스크"] + [f"- {x}" for x in p["risks"]]
    lines += ["", f"*생성: {datetime.now(timezone.utc).isoformat()}*"]
    return "\n".join(lines)


def _detect_scripts_dir(host: str, root: str, unity_sub: str) -> str:
    """Unity 프로젝트에서 .cs 가 가장 많이 모인 Assets 하위 폴더를 찾는다.

    graph 설정의 기본값은 `Assets/1.Scripts` 인데 이건 BalloonFlow 규약이다. IdleFrontier 는
    `Assets/IdleFrontier/Scripts` 라 기본값으로는 그래프가 비어서 나온다. 실제 배치를 보고 정한다.
    """
    import subprocess as _sp
    from collections import Counter
    base = f"{root}/{unity_sub}" if unity_sub else root
    r = _sp.run(["ssh", host, f'git -C "{root}" ls-files "*.cs"'],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=60, check=False)
    cnt: Counter = Counter()
    for line in (r.stdout or "").splitlines():
        p = line.strip().replace("\\", "/")
        if "/Assets/" not in p and not p.startswith("Assets/"):
            continue
        # Assets 이후 두 단계까지를 후보로 본다 (Assets/X, Assets/X/Y)
        tail = p.split("Assets/", 1)[1]
        parts = tail.split("/")
        if len(parts) >= 2:
            cnt["Assets/" + parts[0]] += 1
        if len(parts) >= 3:
            cnt["Assets/" + parts[0] + "/" + parts[1]] += 1
    if not cnt:
        return "Assets/1.Scripts"

    # 포크 프로젝트 주의: 베이스라인 게임의 스크립트가 훨씬 많아 밀도만 보면 그쪽이 뽑힌다
    # (실측: IdleFrontier → Assets/IdleMoney/Scripts). 프로젝트 이름과 일치하는 폴더를 우선한다.
    want = (unity_sub or "").strip("/").lower()
    if want:
        named = [(k, v) for k, v in cnt.items() if want in k.lower()]
        if named:
            return max(named, key=lambda kv: (kv[1] * (1 + kv[0].count("/") * 0.25)))[0]

    # 이름 단서가 없으면 밀도 × 깊이 가중 — 얕은 Assets/X 는 항상 더 크므로 깊이를 보정한다.
    best = max(cnt.items(), key=lambda kv: (kv[1] * (1 + kv[0].count("/") * 0.25)))
    _ = base
    return best[0]


def _ensure_graph_config(project: str, repo: dict) -> str:
    """레지스트리에 graph 설정을 쓰고 그래프/카탈로그를 1회 생성한다."""
    import subprocess as _sp
    slug = (project or "").strip().lower()
    unity_sub = repo.get("name") or ""
    scripts = _detect_scripts_dir(repo["host"], repo["dir"], unity_sub)

    # 이 모듈엔 _db() 헬퍼가 없다 — persist() 와 같은 방식으로 직접 연결한다.
    db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
    db["hermes_projects"].update_one(
        {"project": slug},
        {"$set": {"graph": {"enabled": True, "subdir": unity_sub,
                            "scripts": scripts, "branch": "origin/main",
                            "embed_project": unity_sub or slug}}},
    )

    r = _sp.run([sys.executable, "/home/aimed/.hermes/watcher/bf_graph_refresh.py",
                 "--project", slug, "--force"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=900, check=False)
    tail = (r.stdout or r.stderr or "").strip().splitlines()
    return f"graph scripts={scripts} rc={r.returncode} :: " + (tail[-1][:160] if tail else "")


def persist(project: str, genre: str, team_dir: str, team: str, repo: dict, profile: dict, mode: str, facts: dict) -> dict:
    db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
    now = datetime.now(timezone.utc).isoformat()
    # (1) hermes_projects 레지스트리 — routing/scope 그라운딩
    db["hermes_projects"].update_one(
        {"project": project.lower()},
        {"$set": {
            "project": project.lower(), "display_name": project, "genre": genre, "team": team,
            "repo": repo, "profile": profile, "mode": mode,
            "facts_digest": {k: facts.get(k) for k in ("detected_stack", "file_count", "ext_count", "structure", "git_branch", "todo_markers")},
            "onboarded_at": now,
        }},
        upsert=True)
    # (2) scoped memory — projects/<project>.md
    mem_dir = MEM_ROOT / genre / team_dir / "projects"
    mem_dir.mkdir(parents=True, exist_ok=True)
    md_path = mem_dir / f"{project.lower()}.md"
    md_path.write_text(profile_to_md(project, genre, team, repo, profile, mode), encoding="utf-8")
    # (3) conventions.md (팀 dir에 없으면 시드)
    conv = MEM_ROOT / genre / team_dir / "conventions.md"
    wrote_conv = False
    c = profile.get("conventions", {}) or {}
    if not conv.exists() and (c.get("namespace_pattern") or c.get("notable")):
        conv.parent.mkdir(parents=True, exist_ok=True)
        cl = [f"# {project} 코드 컨벤션 (온보딩 감지)", ""]
        if c.get("namespace_pattern"): cl.append(f"- 네임스페이스: `{c['namespace_pattern']}`")
        if c.get("file_naming"): cl.append(f"- 파일 네이밍: {c['file_naming']}")
        for n in (c.get("notable") or []): cl.append(f"- {n}")
        conv.write_text("\n".join(cl), encoding="utf-8")
        wrote_conv = True
    # 2026-09-14: 온보딩 시 컴파일 베이스라인을 캡처한다. 없으면 게이트가 기존 에러를 전부 새 에러로
    # 계산해 모든 요청이 그 프로젝트의 누적 부채에 막힌다 (NextPR IAPManager 사례).
    # 주의: persist() 의 인자명은 `repo` 다. 초판이 `registry_doc` 을 참조해 NameError 로 매번 죽었고
    # except 가 삼켜 조용히 skip 됐다 — 베이스라인이 어느 프로젝트에도 없던 이유의 절반.
    _is_unity = isinstance(repo, dict) and repo.get("type") == "unity" and repo.get("host") and repo.get("dir")
    if _is_unity:
        try:
            import hermes_executor as _hx
            print("   ", _hx.capture_compile_baseline(repo["host"], repo["dir"], repo.get("name")))
        except Exception as _e:
            print("    baseline capture skipped:", _e)

        # 코드 그래프 + 기능 카탈로그 — feature_gate 의 입력. 없으면 그 게이트가 새 게임에서만
        # indeterminate 로 빠진다(가장 필요한 곳에서 꺼져 있던 문제).
        try:
            print("    graph/catalog 생성 중 ...")
            print("   ", _ensure_graph_config(project, repo))
        except Exception as _e:
            print("    graph/catalog skipped:", _e)
    return {"registry": "hermes_projects", "memory_md": str(md_path), "conventions_written": wrote_conv}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--genre", default="generic")
    ap.add_argument("--team", default="dev")
    ap.add_argument("--team-dir", default=None, help="scoped memory 팀 디렉토리명 (기본: aimed-<genre> 없으면 <team>)")
    ap.add_argument("--path", required=True, help="분석할 로컬 레포 경로 (원격은 먼저 clone)")
    ap.add_argument("--mode", default="handover", choices=["new", "handover"])
    ap.add_argument("--host", default="")
    ap.add_argument("--dir", default="")
    ap.add_argument("--owner", default=os.environ.get("GITHUB_REPO_OWNER", ""))
    ap.add_argument("--name", default="")
    ap.add_argument("--type", default="code", choices=["code", "unity"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not os.path.isdir(a.path):
        print(f"ERROR: --path 없음: {a.path}"); return 2
    team_dir = a.team_dir or (f"aimed-{a.genre}" if a.genre != "generic" else a.team)
    repo = {"host": a.host, "dir": a.dir, "owner": a.owner, "name": a.name or a.project, "type": a.type}

    print(">> 1) 레포 사실 수집 (결정론적) ...")
    facts = gather(a.path)
    print(f"   files={facts['file_count']} stack={facts['detected_stack']} todo={facts['todo_markers']} branch={facts['git_branch']}")

    print(">> 2) 프로파일 합성 (gpt-4o, 사실 기반) ...")
    profile = synthesize(facts, a.mode)
    print(f"   engine={profile.get('engine')} maturity={profile.get('state',{}).get('maturity')} confidence={profile.get('confidence')}")

    if a.dry_run:
        print(json.dumps(profile, ensure_ascii=False, indent=2)); return 0

    print(">> 3) 영속화 (hermes_projects + scoped memory) ...")
    res = persist(a.project, a.genre, team_dir, a.team, repo, profile, a.mode, facts)
    print(f"   {res}")
    print("\n✅ 온보딩 완료. 다음: code_base 임베딩(delta_embed 패턴) + HERMES_REPO_<SUBTEAM>_* env 설정으로 라우팅 연결.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
