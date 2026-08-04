"""context_builder.py — NewPlay 컨텍스트 조립.

projecthub_watcher.py 인터페이스: build_context(task) -> dict

담는 것:
  - 프로젝트 설정(hermes_projects) — 레포 위치, 지식베이스 좌표
  - 대화 이력(코멘트) — Translator 가 "사용자가 이미 답했는지"를 보려면 필요하다
  - 지식베이스 상태 — 검색이 죽어 있으면 그 사실을 알고 답해야 한다
"""
from __future__ import annotations

import logging
import os
from typing import Any

from pymongo import MongoClient

import newplay_kb

log = logging.getLogger("newplay-context")

MONGO_URI = os.environ["MONGODB_URI"]
DB_NAME = os.environ.get("MONGODB_DB", "newteam")
DEFAULT_PROJECT = os.environ.get("NEWPLAY_DEFAULT_PROJECT", "webstore")


def _project_config(project: str) -> dict[str, Any]:
    try:
        cli = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        doc = cli[DB_NAME]["hermes_projects"].find_one({"project": project}) or {}
        cli.close()
        return doc
    except Exception as e:  # noqa: BLE001
        log.warning("프로젝트 설정 로드 실패: %s: %s", type(e).__name__, e)
        return {}


def build_context(task: dict[str, Any]) -> dict[str, Any]:
    project = str(task.get("project") or DEFAULT_PROJECT).lower()
    cfg = _project_config(project)

    comments = task.get("comments") or []
    # Hermes 가 남긴 코멘트는 사용자 답변이 아니다. 구분해 둔다.
    hermes_authors = {"hermes", "hermes-bot", "헤르메스"}
    user_replies = [c for c in comments if str(c.get("author") or "").strip().lower() not in hermes_authors]

    return {
        "project": project,
        "project_config": cfg,
        "repo": cfg.get("repo") or {},
        "knowledge": cfg.get("knowledge") or {},
        "kb_health": newplay_kb.health(),
        "comments": comments[-14:],   # 물어봄→답변 패턴이 잘리지 않게 넉넉히
        "last_user_reply": (user_replies[-1].get("text") if user_replies else "") or "",
        "comment_count": len(comments),
    }
