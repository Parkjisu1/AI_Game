#!/usr/bin/env python3
"""
코드 그래프 자동 갱신 + 회귀(regression) 탐지.
cron(Mother)에서 주기 실행: 대상 브랜치 SHA 가 변하면 →
  archive 추출 → node로 그래프 재생성 + 직전 스냅샷 대비 diff →
  사라진 클래스/메서드 있으면 작성자(박지수)에게 Slack 경고 →
  public/<project>-graph.json 갱신(/balloonflow?project=… 자동 최신화).

프로젝트별 설정은 graph_projects.py 가 푼다 (BUILTIN + hermes_projects 레지스트리).
인자 없이 실행하면 **등록된 프로젝트 전부**를 순회한다 — 기존 cron 줄을 그대로 두면
BalloonFlow 는 하던 대로 돌고, 새 게임은 레지스트리에 올리기만 하면 따라 들어온다.

  python bf_graph_refresh.py                    # 전체
  python bf_graph_refresh.py --project nextpr   # 하나만
  python bf_graph_refresh.py --list             # 설정 확인 (변경 없음)
  python bf_graph_refresh.py --project X --force  # SHA 같아도 재생성
"""
import os, sys, json, subprocess, tarfile, shutil, urllib.request
from dotenv import load_dotenv

load_dotenv("/home/aimed/.hermes/watcher/.env")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import graph_projects  # noqa: E402

NODE = "/home/aimed/.nvm/versions/node/v20.20.2/bin/node"
MJS = "/home/aimed/.hermes/watcher/bf_graph_refresh.mjs"
ENRICH = "/home/aimed/.hermes/watcher/graph/enrich-code-graph.js"
#: 기능 QA 판정기. 그래프가 갱신될 때마다 기능 카탈로그를 다시 대조한다
#: — 코드가 사라지면 "그 기능이 깨졌다"가 push 즉시 화면에 뜬다.
FEATCHK = "/home/aimed/.hermes/watcher/graph/qa-feature-check.mjs"
FEATDIR = "/home/aimed/.hermes/watcher/qa/features"
USER_EMAIL = "jisu.park@gameberry.co.kr"
SSHOPT = ["-o", "ConnectTimeout=15", "-o", "BatchMode=yes"]


def ssh(host, cmd, timeout=180):
    return subprocess.run(["ssh", *SSHOPT, host, cmd], capture_output=True, text=True, timeout=timeout)


# 검수 결과를 받을 담당자. **HERMES_ASSIGNEE_NAMES(hermes/헤르메스/…)에 없는 이름이어야 한다.**
# 그래야 projecthub_watcher.py:130 의 픽업 조건에 걸리지 않아 Hermes가 이 task를
# 자동 실행하지 않는다 — BalloonFlow는 "검수만, 코드 수정 없음" 정책이므로 이게 핵심이다.
REVIEW_ASSIGNEE = os.environ.get("HERMES_REVIEW_ASSIGNEE", "박지수")


def create_review_task(cfg, sha, rf, rm):
    """회귀 검수 결과를 ProjectHub Task로 등록(담당=박지수).

    Slack DM은 흘러가 버리므로 추적 가능한 task로도 남긴다.
    멱등: cron이 10분마다 돌고 같은 SHA가 여러 번 관측될 수 있어,
    같은 review_key 로 아직 안 끝난 task가 있으면 새로 만들지 않는다.
    실패해도 그래프 갱신엔 영향 없도록 non-fatal.
    """
    try:
        from datetime import datetime, timezone
        from pymongo import MongoClient
        db = MongoClient(os.environ["MONGODB_URI"],
                         serverSelectionTimeoutMS=8000)[os.environ.get("MONGODB_DB", "aigame")]
        tasks = db["pixelforge_tasks"]
        # 프로젝트별로 키를 나눈다 — 안 그러면 A 프로젝트의 열린 검수 task 때문에
        # 같은 시각 B 프로젝트의 회귀가 조용히 묻힌다.
        key = f"graph_regression:{cfg['project']}:{sha[:8]}"
        if tasks.find_one({"hermes_review_key": key, "status": {"$ne": "done"}}):
            print("review task: already open for", key, "- skip")
            return

        desc = ["Hermes 그래프 검수에서 **기존에 있던 코드가 사라진 것**을 감지했습니다.",
                f"대상 커밋: `origin/main @{sha[:8]}`", ""]
        if rf:
            desc.append(f"### 🔴 사라진 클래스/파일 {len(rf)}개")
            desc += [f"- `{x}`" for x in rf[:30]]
            if len(rf) > 30:
                desc.append(f"- …외 {len(rf) - 30}개")
            desc.append("")
        if rm:
            desc.append(f"### 🟠 메서드가 제거된 파일 {len(rm)}개")
            for x in rm[:30]:
                desc.append(f"- `{x.get('file')}` — {', '.join((x.get('gone') or [])[:10])}")
            desc.append("")
        desc += ["### 확인 방법",
                 f"https://aimed.tailf6f809.ts.net/balloonflow?project={cfg['project']} 에서 코드그래프 확인",
                 "",
                 "의도된 삭제면 이 task를 done 처리하세요. 의도치 않았다면 복구가 필요합니다.",
                 "",
                 "_정적 추출 기반이라 동적 디스패치는 탐지되지 않습니다. Hermes는 이 task를 "
                 "자동 실행하지 않습니다(담당자가 hermes가 아님)._"]

        now = datetime.now(timezone.utc).isoformat()
        n_total = len(rf) + len(rm)
        res = tasks.insert_one({
            "title": f"[검수] {cfg['display_name']} 회귀 의심 — 사라진 코드 {n_total}건 (@{sha[:8]})",
            "description": "\n".join(desc),
            "assignee": REVIEW_ASSIGNEE,
            "status": "todo",
            "priority": "high",
            "project": cfg["project"],
            "created_by_email": USER_EMAIL,
            "created_via": "graph_regression_review",
            "hermes_review_key": key,
            "comments": [],
            "created_at": now,
            "updated_at": now,
        })
        print("review task created:", res.inserted_id, "assignee:", REVIEW_ASSIGNEE)
    except Exception as e:
        print("review task fail (non-fatal):", e)


def slack(text):
    try:
        from pymongo import MongoClient
        db = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=4000)[os.environ.get("MONGODB_DB", "aigame")]
        doc = db["projecthub_settings"].find_one({"key": "current"})
        s = (doc or {}).get("settings", {}) if doc else {}
        webhooks = s.get("slack_assignee_webhooks", []) or []
        token = s.get("slack_bot_token", "")
        m = next((w for w in webhooks if (w.get("email") or "").strip().lower() == USER_EMAIL), None)
        if not m or not m.get("slack_user_id") or not token:
            print("slack skip: no match/token"); return
        req = urllib.request.Request(
            "https://slack.com/api/chat.postMessage",
            data=json.dumps({"channel": m["slack_user_id"], "text": text}).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=10).read()
        print("slack sent")
    except Exception as e:
        print("slack fail:", e)


# ── push→RAG 동기화: 변경된 .cs만 code_base 임베딩 갱신 ──────────────
# 그래프(QA)는 push마다 갱신되지만 code_base(RAG)는 수동이던 갭을 제거.
# 실패해도 그래프 갱신에는 영향 없음 (best-effort).
LAYER_BY_FOLDER = {
    "Core": "Core", "Data": "Game", "InGame": "Domain", "Manager": "Domain",
    "UI": "Game", "Popup": "Game", "UX": "Game", "Controller": "Domain",
    "Analytics": "Domain", "UA": "Game", "Debug": "Game",
}
ROLE_SUFFIX = [("Manager", "Manager"), ("Controller", "Controller"), ("Calculator", "Calculator"),
               ("Processor", "Processor"), ("Handler", "Handler"), ("Listener", "Listener"),
               ("Provider", "Provider"), ("Factory", "Factory"), ("Service", "Service"),
               ("Validator", "Validator"), ("Builder", "Builder"), ("Pool", "Pool"),
               ("Effect", "UX"), ("Tweener", "UX"), ("Config", "Config"), ("Helper", "Helper")]


def _role_of(name):
    for suf, role in ROLE_SUFFIX:
        if name.endswith(suf):
            return role
    return "Component"


def delta_embed(cfg, sha, last, tmp_root):
    """last..sha 사이 변경된 스크립트 .cs를 code_base에 업서트, 삭제분은 제거."""
    if not last:
        print("embed skip: first run (no prev sha)")
        return
    r = ssh(cfg["host"], f'git -C {cfg["repo_dir"]} diff --name-status {last} {sha} -- {cfg["scripts"]}')
    if r.returncode != 0:
        print("embed skip: diff fail", (r.stderr or "")[:150])
        return
    changed, deleted = [], []
    for ln in (r.stdout or "").splitlines():
        parts = ln.replace("\r", "").split("\t")
        if len(parts) < 2 or not parts[-1].endswith(".cs"):
            continue
        base = os.path.basename(parts[-1])
        if base.endswith(".local.cs"):  # 시크릿 제외 (delta_embed_bf_code와 동일 정책)
            continue
        if parts[0].startswith("D"):
            deleted.append(base[:-3])
        else:  # A/M/R*
            # git 루트는 C:/projects/balloonflow (상위) → diff 경로에 "BalloonFlow/" 접두.
            # archive 추출본(tmp)은 "Assets/..."부터 시작 → Assets/ 기준으로 정규화.
            rel = parts[-1]
            if "Assets/" in rel:
                rel = rel[rel.index("Assets/"):]
            changed.append(rel)
    if not changed and not deleted:
        print("embed: no .cs changes")
        return
    from pymongo import MongoClient
    db = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=6000)[os.environ.get("MONGODB_DB", "aigame")]
    col = db.code_base
    embed_project = cfg["embed_project"]
    if deleted:
        res = col.delete_many({"project": embed_project, "fileId": {"$in": deleted}})
        print(f"embed: removed {res.deleted_count} docs (deleted files: {deleted[:10]})")
    items = []
    for rel in changed:
        p = os.path.join(tmp_root, rel)
        if not os.path.isfile(p):
            continue
        txt = open(p, encoding="utf-8", errors="ignore").read()
        if len(txt.strip()) < 40:
            continue
        cls = os.path.basename(rel)[:-3]
        folder = os.path.basename(os.path.dirname(rel))
        items.append((cls, folder, txt))
    if not items:
        print("embed: no readable changed files")
        return
    from openai import OpenAI
    cli = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    for s in range(0, len(items), 64):
        batch = items[s:s + 64]
        resp = cli.embeddings.create(model="text-embedding-3-small", input=[b[2][:8000] for b in batch])
        for (cls, folder, txt), e in zip(batch, resp.data):
            col.update_one({"fileId": cls, "project": embed_project}, {"$set": {
                "fileId": cls, "project": embed_project, "genre": cfg.get("genre", "generic"),
                "layer": LAYER_BY_FOLDER.get(folder, "Game"), "role": _role_of(cls),
                "system": folder, "source": "internal_produced",
                "className": cls, "text": txt[:12000], "content": txt[:12000],
                "embedding": e.embedding, "embed_model": "text-embedding-3-small",
                "embedded_from_sha": sha[:8],
            }, "$setOnInsert": {"score": 0.4}}, upsert=True)
    print(f"embed: upserted {len(items)} changed files ({[i[0] for i in items[:10]]})")


def _code_base_count(project):
    """code_base 에 이 프로젝트 문서가 몇 건인지. 실패하면 0 취급(=enrich 생략)."""
    try:
        from pymongo import MongoClient
        db = MongoClient(os.environ["MONGODB_URI"],
                         serverSelectionTimeoutMS=6000)[os.environ.get("MONGODB_DB", "aigame")]
        return db.code_base.count_documents({"project": project})
    except Exception as e:
        print("code_base count fail:", e)
        return 0


def refresh(cfg, force=False):
    """프로젝트 하나의 그래프를 갱신. 예외는 호출자가 잡아 다음 프로젝트로 넘어간다."""
    slug, host, repo = cfg["project"], cfg["host"], cfg["repo_dir"]
    branch, scripts = cfg["branch"], cfg["scripts"]
    PUBLIC, SHAFILE = cfg["graph_file"], cfg["sha_file"]
    print(f"\n=== [{slug}] {host}:{repo} @{branch} ({scripts})")

    # 1. 대상 브랜치 SHA
    ssh(host, f'git -C {repo} fetch origin', timeout=120)
    r = ssh(host, f'git -C {repo} rev-parse {branch}')
    sha = (r.stdout or "").strip().replace("\r", "")
    if not sha:
        print("no sha:", (r.stderr or "")[:200]); return
    last = open(SHAFILE).read().strip() if os.path.exists(SHAFILE) else ""
    if sha == last and not force and os.path.exists(PUBLIC):
        print("no change", sha[:8]); return
    print("new sha", sha[:8], "prev", (last[:8] or "-"))

    # 2. archive + scp + extract — tar 이름을 프로젝트별로 나눈다.
    #    (동시에 돌면 같은 파일을 서로 덮어써 다른 프로젝트 소스로 그래프가 만들어진다)
    remote_tar = f"C:/projects/gr_{slug}.tar"
    local_tar = f"/tmp/gr_{slug}.tar"
    ssh(host, f'git -C {repo} archive --format=tar --output={remote_tar} {branch} {scripts}')
    tmp = f"/tmp/gr_{slug}"
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp, exist_ok=True)
    subprocess.run(["scp", *SSHOPT, f"{host}:{remote_tar}", local_tar],
                   capture_output=True, text=True, timeout=180)
    if not os.path.exists(local_tar):
        print("scp failed:", local_tar); return
    with tarfile.open(local_tar) as t:
        t.extractall(tmp)
    ssh(host, f'del {remote_tar.replace("/", chr(92))}')

    src = os.path.join(tmp, scripts)
    if not os.path.isdir(src):
        print("extract failed, no", src); return
    newjson = f"/tmp/gr_{slug}_new.json"

    # 3. node 추출 + diff (마지막 인자 = 경로 자르기 기준. 프로젝트마다 스크립트 폴더명이 다를 수 있다)
    res = subprocess.run([NODE, MJS, src, PUBLIC, newjson,
                          f"{branch} @{sha[:8]} ({cfg['display_name']})", cfg["split_marker"]],
                         capture_output=True, text=True, timeout=180)
    print("node out:", (res.stdout or "")[-300:], "| err:", (res.stderr or "")[-200:])
    removed = {}
    try:
        removed = json.loads((res.stdout or "").strip().splitlines()[-1])
    except Exception as e:
        print("parse removed fail:", e)

    # 4. 회귀 시 Slack
    rf = removed.get("removedFiles", []) or []
    rm = removed.get("removedMethods", []) or []
    # 첫 생성(직전 스냅샷 없음)은 전부 "새로 생긴 것"이라 회귀가 아니다.
    first_run = not last or not os.path.exists(PUBLIC)
    if (rf or rm) and not first_run:
        lines = [f"⚠️ *{cfg['display_name']} push 회귀 의심* ({branch} @{sha[:8]})",
                 "기존에 있던 코드가 사라졌습니다 — 의도된 변경인지 확인하세요:"]
        if rf:
            lines.append(f"🔴 사라진 클래스/파일 {len(rf)}개: " + ", ".join(rf[:15]))
        for x in rm[:15]:
            lines.append(f"🟠 {x.get('file')}: 메서드 제거 — {', '.join((x.get('gone') or [])[:8])}")
        lines.append(f"→ https://aimed.tailf6f809.ts.net/balloonflow?project={slug} 에서 확인")
        slack("\n".join(lines))
        # Slack은 흘러가므로 추적 가능한 Task로도 남긴다(담당=박지수, Hermes 자동실행 안 함).
        create_review_task(cfg, sha, rf, rm)
        print("REGRESSION:", len(rf), "files,", len(rm), "method-sets")
    elif first_run:
        print("first run — 회귀 판정 생략(비교 대상 없음)")
    else:
        print("no regression")

    # 5. public 갱신 + SHA 저장
    if os.path.exists(newjson):
        shutil.copy(newjson, PUBLIC)
        print("public updated")
        # 5-1. 엣지 타입 부여 (code_base.integration 과 클래스명으로 조인).
        # mjs 그래프는 "본문에 클래스명이 보이면 엣지"라 타입이 없고,
        # 그래서 노드 절반 이상이 순환 판정으로 묻혀 신호 역할을 못 한다.
        # 재생성 직후 타입을 덧씌운다 — 기존 필드는 두고 추가만 하므로
        # 소비자(/balloonflow, DNA 그라운딩, 음성 질의)는 무영향.
        # 실패해도 그래프 갱신 자체는 유효하므로 비치명 처리.
        try:
            # code_base 에 이 프로젝트 문서가 없으면 **건너뛴다.**
            # 실측: 0건이어도 enrich 는 돌아서 타입드 QA(전부 orphan)로 원본 QA 를 덮어썼다
            # (ok:60/cycle:106/entry:16 → orphan:191). 타입을 못 붙일 바엔 안 붙이는 게 낫다.
            if _code_base_count(cfg["embed_project"]) == 0:
                print(f"enrich: skip — code_base 에 project={cfg['embed_project']} 문서 0건 "
                      f"(엣지 타입 없이 기본 그래프만 사용)")
            else:
                _env = dict(os.environ, NODE_PATH="/home/aimed/projecthub-web/node_modules")
                # --project 필수: 기본값이 BalloonFlow 라서, 안 넘기면 다른 게임 그래프에
                # BalloonFlow 의 code_base 로 만든 엣지 타입이 덧씌워진다(실측으로 확인).
                _r = subprocess.run([NODE, ENRICH, "--graph", PUBLIC,
                                     "--project", cfg["embed_project"]],
                                    capture_output=True, text=True, timeout=180, env=_env)
                _out = (_r.stdout or _r.stderr or "").strip().replace("\n", " | ")
                print("enrich:", _out[:300])
        except Exception as _e:
            print("enrich fail (non-fatal):", _e)

        # 5-2. 기능 QA 재판정 — 카탈로그(qa/features/<project>.yaml)를 갱신된 그래프와 대조.
        # 그래프가 "파일이 있다/없다"를 말한다면 이쪽은 "그 기능이 성립한다/깨졌다"를 말한다.
        # 카탈로그가 없는 프로젝트는 조용히 건너뛴다(아직 기능을 정의하지 않은 것일 뿐).
        try:
            if os.path.exists(os.path.join(FEATDIR, f"{cfg['project']}.yaml")):
                _env = dict(os.environ, NODE_PATH="/home/aimed/projecthub-web/node_modules")
                _r = subprocess.run(
                    [NODE, FEATCHK, "--project", cfg["project"],
                     "--public", graph_projects.PUBLIC_DIR, "--catalog", FEATDIR],
                    capture_output=True, text=True, timeout=180, env=_env)
                print("feature-qa:", (_r.stdout or _r.stderr or "").strip().replace("\n", " | ")[:300])
            else:
                print(f"feature-qa: skip — 카탈로그 없음 ({cfg['project']}.yaml)")
        except Exception as _e:
            print("feature-qa fail (non-fatal):", _e)

    os.makedirs(os.path.dirname(SHAFILE), exist_ok=True)
    with open(SHAFILE, "w") as f:
        f.write(sha)

    # 6. push→RAG 동기화 (best-effort — 실패해도 그래프 갱신엔 영향 없음)
    #    프로젝트마다 OpenAI 임베딩 비용이 붙으므로 cfg.embed 로 켠 것만 한다.
    if cfg.get("embed"):
        try:
            delta_embed(cfg, sha, last, tmp)
        except Exception as e:
            print("delta embed fail (non-fatal):", e)
    else:
        print("embed: disabled for this project")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        os.unlink(local_tar)
    except OSError:
        pass
    print(f"[{slug}] done")


def main():
    args = sys.argv[1:]
    only = None
    if "--project" in args:
        only = args[args.index("--project") + 1].strip().lower()
    force = "--force" in args

    projects = graph_projects.all_projects()
    if only:
        projects = [c for c in projects if c["project"] == only]
        if not projects:
            print(f"unknown project: {only}")
            print("사용 가능:", ", ".join(c["project"] for c in graph_projects.all_projects()))
            sys.exit(1)

    if "--list" in args:
        for c in projects:
            print(f"{c['project']:<18} {c['display_name']:<20} {c['host']}:{c['repo_dir']} "
                  f"@{c['branch']} {c['scripts']}  embed={c.get('embed')}")
        return

    print(f"대상 {len(projects)}개: " + ", ".join(c["project"] for c in projects))
    for cfg in projects:
        # 한 프로젝트가 실패해도 나머지는 계속 — 머신 하나가 꺼져 있다고
        # 다른 게임 그래프까지 멈추면 안 된다.
        try:
            refresh(cfg, force=force)
        except Exception as e:
            print(f"[{cfg['project']}] FAILED (non-fatal): {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
