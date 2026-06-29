#!/usr/bin/env python3
"""
BalloonFlow 그래프 자동 갱신 + 회귀(regression) 탐지.
cron(Mother)에서 주기 실행: origin/main SHA 변하면 →
  archive 추출 → node로 그래프 재생성 + 직전 스냅샷 대비 diff →
  사라진 클래스/메서드 있으면 작성자(박지수)에게 Slack 경고 →
  public/balloonflow-graph.json 갱신(/balloonflow 자동 최신화).
"""
import os, sys, json, subprocess, tarfile, shutil, urllib.request
from dotenv import load_dotenv

load_dotenv("/home/aimed/.hermes/watcher/.env")

MB = "user@100.92.43.9"
REPO = "C:/projects/balloonflow/BalloonFlow"
NODE = "/home/aimed/.nvm/versions/node/v20.20.2/bin/node"
MJS = "/home/aimed/.hermes/watcher/bf_graph_refresh.mjs"
PUBLIC = "/home/aimed/projecthub-web/public/balloonflow-graph.json"
SHAFILE = "/home/aimed/.hermes/bf_graph.lastsha"
USER_EMAIL = "jisu.park@gameberry.co.kr"
SSHOPT = ["-o", "ConnectTimeout=15", "-o", "BatchMode=yes"]


def ssh(cmd, timeout=180):
    return subprocess.run(["ssh", *SSHOPT, MB, cmd], capture_output=True, text=True, timeout=timeout)


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


def main():
    # 1. origin/main SHA
    ssh(f'git -C {REPO} fetch origin', timeout=120)
    r = ssh(f'git -C {REPO} rev-parse origin/main')
    sha = (r.stdout or "").strip().replace("\r", "")
    if not sha:
        print("no sha:", r.stderr[:200]); return
    last = open(SHAFILE).read().strip() if os.path.exists(SHAFILE) else ""
    if sha == last:
        print("no change", sha[:8]); return
    print("new sha", sha[:8], "prev", (last[:8] or "-"))

    # 2. archive + scp + extract
    ssh(f'git -C {REPO} archive --format=tar --output=C:/projects/bf_gr.tar origin/main Assets/1.Scripts')
    tmp = "/tmp/bf_gr"
    shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp, exist_ok=True)
    subprocess.run(["scp", *SSHOPT, f"{MB}:C:/projects/bf_gr.tar", "/tmp/bf_gr.tar"], capture_output=True, text=True, timeout=120)
    with tarfile.open("/tmp/bf_gr.tar") as t:
        t.extractall(tmp)
    ssh('del C:\\projects\\bf_gr.tar')

    src = os.path.join(tmp, "Assets/1.Scripts")
    if not os.path.isdir(src):
        print("extract failed, no", src); return
    newjson = "/tmp/bf_gr_new.json"

    # 3. node 추출 + diff
    res = subprocess.run([NODE, MJS, src, PUBLIC, newjson, f"origin/main @{sha[:8]} (BalloonFlow)"],
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
    if rf or rm:
        lines = [f"⚠️ *BalloonFlow push 회귀 의심* (origin/main @{sha[:8]})",
                 "기존에 있던 코드가 사라졌습니다 — 의도된 변경인지 확인하세요:"]
        if rf:
            lines.append(f"🔴 사라진 클래스/파일 {len(rf)}개: " + ", ".join(rf[:15]))
        for x in rm[:15]:
            lines.append(f"🟠 {x.get('file')}: 메서드 제거 — {', '.join((x.get('gone') or [])[:8])}")
        lines.append("→ https://aimed.tailf6f809.ts.net/balloonflow 에서 확인")
        slack("\n".join(lines))
        print("REGRESSION:", len(rf), "files,", len(rm), "method-sets")
    else:
        print("no regression")

    # 5. public 갱신 + SHA 저장
    if os.path.exists(newjson):
        shutil.copy(newjson, PUBLIC)
        print("public updated")
    os.makedirs(os.path.dirname(SHAFILE), exist_ok=True)
    with open(SHAFILE, "w") as f:
        f.write(sha)
    print("done")


if __name__ == "__main__":
    main()
