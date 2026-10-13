"""overlap.py — 진행 중인 작업들 사이의 겹침을 **실시간**으로 보고, 끝난 뒤에는 구간 단위 충돌을 판정한다 (P2 감시자의 기계 층).

두 층:
  1) 실시간 터치셋: 작업자 AI 가 worktree 에서 일하는 동안 20초마다 `git status` 를 읽어 `touched_files` 를 작업 문서에 갱신하고,
     같은 프로젝트의 다른 활성 작업과 파일이 겹치면 **그때** 양쪽에 경고 코멘트(파일 집합이 새로 늘었을 때만).
  2) 종료 후 구간 판정: 두 작업의 diff 가 같은 파일의 **같은 줄 구간**을 건드리면 `conflict` — 머지 보류(`merge_hold`).
     이때만 감시자 LLM(요청자 계정)이 두 diff 를 읽고 "의미 충돌 / 순서만 / 한쪽이 포함" 을 사람에게 요약한다.

정책 (env NEWPLAY_OVERLAP_POLICY): warn(기본) — 경고·보류 표시만 / block — 구간 충돌 시 검수 큐에 넣지 않고 사람 선택을 기다림.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from bson import ObjectId
from pymongo import MongoClient

import workspace

log = logging.getLogger("overlap")

MONGO_URI = os.environ.get("MONGODB_URI", "")
DB_NAME = os.environ.get("MONGODB_DB", "newteam")
POLICY = os.environ.get("NEWPLAY_OVERLAP_POLICY", "warn").lower()
LIVE_INTERVAL = int(os.environ.get("NEWPLAY_TOUCH_INTERVAL", "20"))
ACTIVE_STATUSES = ["in_progress", "review"]


def _col():
    cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    return cli, cli[DB_NAME]["pixelforge_tasks"]


def others_touching(task_id: str, project: str, files: list[str]) -> list[dict[str, Any]]:
    """같은 프로젝트의 다른 활성 작업 중 같은 파일을 건드린 것."""
    if not files:
        return []
    cli, col = _col()
    try:
        out = []
        for o in col.find({"_id": {"$ne": ObjectId(task_id)}, "project": project,
                           "status": {"$in": ACTIVE_STATUSES}, "touched_files": {"$in": files}},
                          {"title": 1, "touched_files": 1, "created_by_email": 1, "branch": 1, "worktree": 1, "hunks": 1}):
            shared = sorted(set(files) & set(o.get("touched_files") or []))
            if shared:
                out.append({"task_id": str(o["_id"]), "title": o.get("title", ""), "owner": o.get("created_by_email", ""),
                            "branch": o.get("branch", ""), "worktree": o.get("worktree", ""), "files": shared,
                            "hunks": o.get("hunks") or {}})
        return out
    finally:
        cli.close()


class LiveTouchWatcher:
    """작업자 실행 동안 터치셋을 주기적으로 기록하고 겹침을 즉시 알린다. with 문으로 감싼다."""

    def __init__(self, task_id: str, project: str, wt_path: str, persist: Callable[[dict], None],
                 comment: Callable[[str, str], None], title: str):
        self.task_id, self.project, self.wt, self.persist, self.comment, self.title = task_id, project, wt_path, persist, comment, title
        self._stop = threading.Event()
        self._seen_pairs: set[tuple[str, str]] = set()
        self.files: list[str] = []
        self._t: Optional[threading.Thread] = None

    def _tick(self) -> None:
        files = workspace.touched_files(self.wt)
        if files != self.files:
            self.files = files
            self.persist({"touched_files": files, "touched_at": datetime.now(timezone.utc).isoformat()})
        for o in others_touching(self.task_id, self.project, files):
            new = [f for f in o["files"] if (o["task_id"], f) not in self._seen_pairs]
            if not new:
                continue
            for f in new:
                self._seen_pairs.add((o["task_id"], f))
            self.comment(self.task_id, f"⚠️ 진행 중 겹침: `{o['task_id'][-8:]}` {o['title'][:40]} ({o['owner'] or '?'}) 도 지금 " + ", ".join(new[:6]) + " 을(를) 건드리고 있습니다.")
            self.comment(o["task_id"], f"⚠️ 진행 중 겹침: `{self.task_id[-8:]}` {self.title[:40]} 이(가) 지금 " + ", ".join(new[:6]) + " 을(를) 건드리고 있습니다.")

    def _loop(self) -> None:
        while not self._stop.wait(LIVE_INTERVAL):
            try:
                self._tick()
            except Exception as e:  # noqa: BLE001
                log.warning("터치셋 감시 실패(무시): %s", e)

    def __enter__(self):
        self._t = threading.Thread(target=self._loop, name=f"touch-{self.task_id[-6:]}", daemon=True)
        self._t.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        if self._t:
            self._t.join(timeout=5)
        try:
            self._tick()
        except Exception:  # noqa: BLE001
            pass
        return False


def _ranges_overlap(a: list, b: list) -> bool:
    for s1, e1 in a:
        for s2, e2 in b:
            if s1 <= e2 and s2 <= e1:
                return True
    return False


def conflicts(task_id: str, project: str, my_hunks: dict[str, list]) -> list[dict[str, Any]]:
    """구간 단위 충돌: 같은 파일에서 줄 구간이 겹치는 다른 활성 작업. 파일만 겹치면 warn, 구간까지 겹치면 conflict."""
    files = list(my_hunks.keys())
    res = []
    for o in others_touching(task_id, project, files):
        hard = []
        for f in o["files"]:
            if _ranges_overlap(my_hunks.get(f) or [], (o.get("hunks") or {}).get(f) or []):
                hard.append(f)
        res.append({**{k: o[k] for k in ("task_id", "title", "owner", "branch", "files")},
                    "conflict": bool(hard), "conflict_files": hard})
    return res


def assess_with_llm(my_diff: str, other_diff: str, my_title: str, other_title: str, invoke: Callable) -> str:
    """감시자 LLM(요청자 계정): 구간 충돌이 있을 때만. 사람이 순서를 정할 수 있게 3줄로 요약."""
    prompt = (
        "두 작업이 같은 파일의 같은 구간을 고쳤다. 아래 두 diff 를 비교해 **세 줄**로만 답하라.\n"
        "1) 판정: 의미 충돌 / 순서만 정하면 됨 / 한쪽이 다른 쪽을 포함 중 하나\n"
        "2) 근거: 어느 파일 어느 구간이 어떻게 다른지 한 줄\n"
        "3) 권장: 먼저 합칠 쪽과 이유 한 줄\n\n"
        f"## A: {my_title}\n```diff\n{my_diff[:12000]}\n```\n\n## B: {other_title}\n```diff\n{other_diff[:12000]}\n```"
    )
    resp = invoke("reviewer", prompt, timeout=300)
    return (resp.output or "").strip()[:800] if getattr(resp, "success", False) else f"(감시자 판정 실패: {getattr(resp, 'error', '')[:120]})"
