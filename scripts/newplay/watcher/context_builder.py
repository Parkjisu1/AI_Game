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


#: 헤르메스가 남긴 코멘트 중 몇 개까지 넘길지. 진행 로그라 최근 것만 있으면 된다.
_MAX_BOT_COMMENTS = int(os.environ.get("NEWPLAY_CTX_BOT_COMMENTS", "12"))


def build_context(task: dict[str, Any]) -> dict[str, Any]:
    project = str(task.get("project") or DEFAULT_PROJECT).lower()
    cfg = _project_config(project)

    comments = task.get("comments") or []
    # Hermes 가 남긴 코멘트는 사용자 답변이 아니다. 구분해 둔다.
    hermes_authors = {"hermes", "hermes-bot", "헤르메스"}
    user_replies = [c for c in comments if str(c.get("author") or "").strip().lower() not in hermes_authors]

    # 사용자 지시는 **전부** 넘긴다. 헤르베스 진행 로그만 최근 것으로 줄인다.
    #
    # 예전에는 `comments[-14:]` 로 둘을 똑같이 셌다. 그런데 헤르메스는 한 태스크에서
    # 코멘트를 대여섯 개씩 남긴다(실행 중 / 결과 / 검수 / 재작업 …).
    # 그래서 대화가 조금만 길어지면 정작 잘리면 안 되는 **사용자 지시가 먼저 밀려났다**.
    # 분량 조절은 프롬프트 조립(_history)에서 하고, 여기서는 버리지 않는다.
    bot_kept = [c for c in comments
                if str(c.get("author") or "").strip().lower() in hermes_authors][-_MAX_BOT_COMMENTS:]
    keep = {id(c) for c in user_replies} | {id(c) for c in bot_kept}
    selected = [c for c in comments if id(c) in keep]

    return {
        "project": project,
        "project_config": cfg,
        "repo": cfg.get("repo") or {},
        "knowledge": cfg.get("knowledge") or {},
        "kb_health": newplay_kb.health(),
        "comments": selected,   # 사용자 지시 전부 + 헤르메스 최근 것
        "last_user_reply": (user_replies[-1].get("text") if user_replies else "") or "",
        "comment_count": len(comments),
    }
