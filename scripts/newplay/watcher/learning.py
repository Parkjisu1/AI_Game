"""learning.py — 되먹임(P3): **사람이 채택한 결과만** 배운다.

세 가지:
  1) 결정 메모: 채택된 작업에 대해 요청자 계정의 AI 가 "문제·원인·결론·건드린 파일·보류한 대안" 을 쓴다. 사람이 고칠 수 있다.
  2) 메모리 컬렉션 `mem_<project>_m3`(bge-m3 1024d): 결정 메모를 임베딩. 새 작업 시작 시 유사 메모 3건이 컨텍스트에 붙는다.
  3) 증분 재색인: 채택 diff 가 건드린 파일만 코드 지식베이스(`kb collection`)에서 그 파일 청크를 지우고 다시 넣는다.
     → 색인이 저절로 신선해진다. 거부·보류된 결과는 손대지 않는다(오염 방지).

트리거: 작업 문서 `selection.decision == "accept"` 이고 `learned_at` 이 없으면. 워처가 60초마다 훑는다(learning_loop).
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import requests
from pymongo import MongoClient

log = logging.getLogger("learning")

MONGO_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("MONGODB_DB", "newteam")
QDRANT = os.environ.get("NEWPLAY_QDRANT_URL", "http://127.0.0.1:6343")
OLLAMA = os.environ.get("NEWPLAY_OLLAMA_URL", "http://127.0.0.1:11434")
EMBED_MODEL = os.environ.get("NEWPLAY_EMBED_MODEL", "bge-m3")
DIM = 1024
CHUNK_LINES = int(os.environ.get("NEWPLAY_CHUNK_LINES", "60"))
LOOP_INTERVAL = int(os.environ.get("NEWPLAY_LEARN_INTERVAL", "60"))
SESSION_STALE_H = int(os.environ.get("NEWPLAY_SESSION_STALE_HOURS", "12"))   # 끝맺지 못한 직접 모드 세션을 닫는 기준

MEMO_PROMPT = """아래는 사람이 **채택한** 작업 결과다. 다음 작업들이 참고할 "결정 메모"를 한국어로 쓴다. 사실만, 12줄 이내.

## 문제
(한 줄)
## 원인
(한 줄, 코드 근거 파일:줄)
## 결론
(무엇을 어떻게 바꿨는지 2~4줄)
## 건드린 파일
- 경로 — 한 줄 이유
## 보류·거부된 대안과 이유
(있으면. 없으면 "없음")
## 다음에 같은 문제가 오면
(한 줄 지침)

# 작업: {title}
{description}

# 결과 요약
{deliverable}

# 실제 diff (앞부분)
```diff
{diff}
```"""


def _db():
    cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return cli, cli[DB_NAME]


def _embed(texts: list[str]) -> list[list[float]]:
    r = requests.post(f"{OLLAMA}/api/embed", json={"model": EMBED_MODEL, "input": [t[:2000] for t in texts], "keep_alive": -1}, timeout=300)
    r.raise_for_status()
    return r.json()["embeddings"]


def _ensure(collection: str) -> None:
    r = requests.get(f"{QDRANT}/collections/{collection}", timeout=10)
    if r.status_code == 200:
        return
    requests.put(f"{QDRANT}/collections/{collection}", json={"vectors": {"size": DIM, "distance": "Cosine"}}, timeout=30).raise_for_status()
    for key in ("project", "path", "task_id", "owner"):
        requests.put(f"{QDRANT}/collections/{collection}/index", json={"field_name": key, "field_schema": "keyword"}, timeout=30)


def mem_collection(project: str) -> str:
    return f"mem_{re.sub(r'[^a-z0-9_]+', '_', (project or 'default').lower())}_m3"


# ── 1·2) 결정 메모 + 메모리 ───────────────────────────────────────────────

def write_memo(task: dict[str, Any], invoke) -> str:
    prompt = MEMO_PROMPT.format(
        title=task.get("title", ""), description=(task.get("description") or "")[:3000],
        deliverable=(task.get("deliverable") or "")[:6000], diff=(task.get("proposed_patch") or "")[:8000])
    # 메모 작성 역할: env 지정 → dev_pm → main_coder → reviewer 순으로 되는 것을 쓴다(역할 구성이 팀마다 다르다)
    roles = [r for r in [os.environ.get("NEWPLAY_MEMO_ROLE", ""), "dev_pm", "main_coder", "reviewer"] if r]
    last = ""
    for role in roles:
        resp = invoke(role, prompt, timeout=300)
        if getattr(resp, "success", False) and (resp.output or "").strip():
            return (resp.output or "").strip()[:6000]
        last = f"{role}: {getattr(resp, 'error', '')[:120]}"
    raise RuntimeError(f"결정 메모 생성 실패 — {last}")


def remember(project: str, task_id: str, owner: str, title: str, memo: str, files: list[str]) -> None:
    col = mem_collection(project)
    _ensure(col)
    vec = _embed([f"{title}\n{memo}"])[0]
    pid = str(uuid.UUID(hashlib.md5(f"memo|{task_id}".encode()).hexdigest()))
    requests.put(f"{QDRANT}/collections/{col}/points?wait=true", json={"points": [{
        "id": pid, "vector": vec,
        "payload": {"project": project, "task_id": task_id, "owner": owner, "title": title, "memo": memo,
                    "files": files[:50], "at": datetime.now(timezone.utc).isoformat()}}]}, timeout=60).raise_for_status()


def similar_memos(project: str, query: str, top: int = 3) -> str:
    """새 작업 프롬프트에 붙일 "과거 유사 작업과 결론" 블록. 없으면 빈 문자열."""
    col = mem_collection(project)
    try:
        if requests.get(f"{QDRANT}/collections/{col}", timeout=5).status_code != 200:
            return ""
        vec = _embed([query])[0]
        r = requests.post(f"{QDRANT}/collections/{col}/points/search",
                          json={"vector": vec, "limit": top, "with_payload": True, "score_threshold": 0.45}, timeout=30)
        r.raise_for_status()
        hits = r.json().get("result") or []
    except Exception as e:  # noqa: BLE001
        log.warning("메모리 검색 실패(무시): %s", e)
        return ""
    if not hits:
        return ""
    lines = ["## 과거 유사 작업과 결론 (사람이 채택한 것만)", "같은 문제면 같은 결론을 따르고, 다르면 왜 다른지 밝혀라.", ""]
    for h in hits:
        p = h["payload"]
        lines.append(f"### {p.get('title')} (score {h.get('score', 0):.2f}, {p.get('owner') or '?'}, 작업 {str(p.get('task_id'))[-8:]})")
        lines.append(str(p.get("memo") or "")[:1500])
        lines.append("")
    return "\n".join(lines)


# ── 3) 증분 재색인 ───────────────────────────────────────────────────────

def _area(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else ""


def _lang(path: str) -> str:
    ext = os.path.splitext(path)[1].lstrip(".")
    return {"ts": "typescript", "tsx": "tsx", "js": "javascript", "scss": "scss", "css": "css", "md": "markdown", "json": "json"}.get(ext, ext)


def reindex_files(project: str, kb_collection: str, worktree: str, files: list[str], sha: str) -> int:
    """채택된 worktree 의 파일들만 다시 색인. 반환: 넣은 청크 수. 삭제된 파일은 색인에서도 지운다."""
    _ensure(kb_collection)
    total = 0
    for rel in files:
        # 기존 청크 제거 (path 필터)
        requests.post(f"{QDRANT}/collections/{kb_collection}/points/delete?wait=true",
                      json={"filter": {"must": [{"key": "path", "match": {"value": rel}}]}}, timeout=60)
        full = os.path.join(worktree, rel)
        if not os.path.isfile(full):
            continue
        try:
            text = open(full, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        lines = text.splitlines()
        pts, chunk_texts = [], []
        for start in range(0, max(len(lines), 1), CHUNK_LINES):
            body = "\n".join(lines[start:start + CHUNK_LINES])
            if not body.strip():
                continue
            s, e = start + 1, min(start + CHUNK_LINES, len(lines))
            header = f"[{project}/{_area(rel)}] {rel} ({_lang(rel)}) lines {s}-{e}\n"
            chunk_texts.append(header + body)
            pid = str(uuid.UUID(hashlib.md5(f"{project}|{rel}|{s}|{sha}".encode()).hexdigest()))
            pts.append({"id": pid, "payload": {"project": project, "area": _area(rel), "path": rel, "kind": "code",
                                               "lang": _lang(rel), "startLine": s, "endLine": e, "sha": sha,
                                               "symbols": [], "text": header + body}})
        for i in range(0, len(pts), 8):
            vecs = _embed(chunk_texts[i:i + 8])
            for p, v in zip(pts[i:i + 8], vecs):
                p["vector"] = v
            requests.put(f"{QDRANT}/collections/{kb_collection}/points?wait=true", json={"points": pts[i:i + 8]}, timeout=120).raise_for_status()
        total += len(pts)
    return total


# ── 트리거 루프 ──────────────────────────────────────────────────────────

def learn_task(task: dict[str, Any], invoke, set_actor, comment, kb_collection: str) -> dict[str, Any]:
    task_id = str(task["_id"]); project = str(task.get("project") or "")
    owner = str(task.get("created_by_email") or "")
    set_actor(owner)
    files = list(task.get("touched_files") or task.get("patch_files") or [])
    memo = write_memo(task, invoke)
    remember(project, task_id, owner, str(task.get("title") or ""), memo, files)
    n = 0
    wt = str(task.get("worktree") or "")
    if wt and os.path.isdir(wt) and files:
        n = reindex_files(project, kb_collection, wt, files, str(task.get("commit") or "accepted"))
    comment(task_id, f"🧠 **학습 완료** — 결정 메모를 메모리에 저장했고, 파일 {len(files)}개({n} 청크)를 지식베이스에 다시 색인했습니다.\n\n{memo[:2500]}")
    return {"memo": memo, "reindexed": n, "files": files}


HOME_ROOT = os.environ.get("NEWPLAY_HOME_ROOT", "/data/newplay/home")   # gateway 가 /home/app 로 마운트하는 개인 홈


def _safe_user(email: str) -> str:
    """개인 홈 폴더 이름. **gateway 의 규칙과 반드시 같아야 한다** — 다르면 전사를 못 찾아 프로필이 비어 버린다.
    주소 전체를 쓴다(앞부분만 쓰면 다른 도메인의 동명이인이 같은 폴더를 쓴다)."""
    e = (email or "").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", e).strip("-") or "anon"
    return slug[:27] + "-" + hashlib.sha256(e.encode()).hexdigest()[:12]


def _home_dir(email: str) -> str:
    """충돌 가능한 옛 폴더로 폴백하지 않는다. 옛 데이터는 지우지 않고 보존한다."""
    return os.path.join(HOME_ROOT, _safe_user(email))


def process_session(db, s: dict[str, Any]) -> dict[str, Any]:
    """직접 모드 세션 종료 → 전사 파싱 → work_sessions.extracted → 프로필 갱신 (설계서 §6-4)."""
    import profiles
    email = str(s.get("email") or ""); project = str(s.get("project") or "")
    home = _home_dir(email)
    paths = profiles.find_transcripts(home, str(s.get("started_at") or ""), project)
    merged = {"user_msgs": [], "commands": [], "files": [], "tools": {}}
    for p in paths:
        r = profiles.parse_transcript(p)
        merged["user_msgs"] += r["user_msgs"]; merged["commands"] += r["commands"]; merged["files"] += r["files"]
        for k, v in r["tools"].items():
            merged["tools"][k] = merged["tools"].get(k, 0) + v
    # 브랜치의 실제 변경 파일도 합친다
    wt = str(s.get("worktree") or "")
    if wt and os.path.isdir(wt):
        try:
            import subprocess
            out = subprocess.run(["git", "-C", wt, "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True, timeout=30).stdout
            merged["files"] += [l[3:].strip() for l in out.splitlines() if len(l) > 3]
            # 커밋에서 파일을 뽑을 땐 **이 사람이 이 브랜치에서 만든 커밋만** 본다.
            # 기준이 없을 때 최근 커밋을 그냥 집으면 남이 한 일이 그 사람 영역으로 둔갑한다(실측).
            base = str(s.get("base_rev") or "")
            if not base:
                head = subprocess.run(["git", "-C", wt, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"],
                                      capture_output=True, text=True, timeout=15).stdout.strip()
                for cand in ([head] if head else []) + ["origin/main", "main", "master"]:
                    mb = subprocess.run(["git", "-C", wt, "merge-base", "HEAD", cand], capture_output=True, text=True, timeout=15)
                    if mb.returncode == 0 and mb.stdout.strip():
                        base = mb.stdout.strip(); break
            if base:
                log_out = subprocess.run(["git", "-C", wt, "log", "--name-only", "--format=", f"{base}..HEAD"],
                                         capture_output=True, text=True, timeout=30).stdout
                merged["files"] += [l.strip() for l in log_out.splitlines() if l.strip()]
        except Exception:  # noqa: BLE001
            pass
    merged["files"] = sorted(set(merged["files"]))[:200]
    summary = ""
    if merged["user_msgs"]:
        summary = "요청: " + " / ".join(m.replace("\n", " ")[:120] for m in merged["user_msgs"][:5])
    db["work_sessions"].update_one({"_id": s["_id"]}, {"$set": {"transcripts": paths[:20], "files": merged["files"], "commands": merged["commands"][:80],
                                                                "tools": merged["tools"], "summary": summary[:2000],
                                                                "processed_at": datetime.now(timezone.utc).isoformat()}})
    if email and project:
        profiles.update_from_session(email, project, merged)
    return merged


def learning_loop(invoke, set_actor, comment, kb_collection_for) -> None:
    """워처/learner 프로세스에서 돈다. ① 채택됐지만 아직 배우지 않은 작업 ② 끝났지만 아직 처리 안 된 직접 모드 세션."""
    import profiles
    while True:
        try:
            cli, db = _db()
            try:
                col = db["pixelforge_tasks"]
                for t in col.find({"selection.decision": "accept", "learned_at": {"$exists": False}}).limit(3):
                    try:
                        res = learn_task(t, invoke, set_actor, comment, kb_collection_for(str(t.get("project") or "")))
                        col.update_one({"_id": t["_id"]}, {"$set": {"learned_at": datetime.now(timezone.utc).isoformat(),
                                                                    "decision_memo": res["memo"], "reindexed_chunks": res["reindexed"]}})
                        try:
                            profiles.update_from_accepted(t, str((t.get("selection") or {}).get("by") or ""))
                        except Exception as e:  # noqa: BLE001
                            log.warning("프로필 갱신 실패(채택) %s: %s", t.get("_id"), e)
                    except Exception as e:  # noqa: BLE001
                        log.warning("학습 실패 %s: %s", t.get("_id"), e)
                        col.update_one({"_id": t["_id"]}, {"$set": {"learn_error": str(e)[:300], "learn_error_at": datetime.now(timezone.utc).isoformat()}})
                # 게이트웨이가 죽는 등으로 끝맺지 못한 세션은 영원히 미처리로 남는다 → 오래된 것은 닫아 준다.
                stale_before = (datetime.now(timezone.utc) - timedelta(hours=SESSION_STALE_H)).isoformat()
                db["work_sessions"].update_many(
                    {"mode": "direct", "ended_at": {"$exists": False}, "started_at": {"$lt": stale_before}},
                    {"$set": {"ended_at": datetime.now(timezone.utc).isoformat(), "ended_reason": "stale"}})
                for s in db["work_sessions"].find({"ended_at": {"$exists": True}, "processed_at": {"$exists": False}, "mode": "direct"}).limit(5):
                    try:
                        r = process_session(db, s)
                        log.info("세션 처리 %s: 파일 %d 명령 %d", s.get("_id"), len(r["files"]), len(r["commands"]))
                    except Exception as e:  # noqa: BLE001
                        log.warning("세션 처리 실패 %s: %s", s.get("_id"), e)
                        db["work_sessions"].update_one({"_id": s["_id"]}, {"$set": {"processed_at": datetime.now(timezone.utc).isoformat(), "process_error": str(e)[:300]}})
            finally:
                cli.close()
        except Exception as e:  # noqa: BLE001
            log.warning("학습 루프 오류(계속): %s", e)
        time.sleep(LOOP_INTERVAL)


def start_learning_thread(invoke, set_actor, comment, kb_collection_for) -> threading.Thread:
    t = threading.Thread(target=learning_loop, args=(invoke, set_actor, comment, kb_collection_for), name="learning", daemon=True)
    t.start()
    return t
