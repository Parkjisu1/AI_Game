"""
User Name Resolver — Task의 author/assignee 이름을 user_registry.yaml에 매칭

ProjectHub의 task.assignee는 단순 문자열("김대리" 등)이라,
user_registry.yaml의 `users` 맵에 선언된 사용자들 중 이름이 맞는 사람을 찾아서
team/role/projects 정보로 확장합니다.

경로 A(스키마 무수정) 원칙: Slack user ID 없이 이름만으로 조회 가능하게 설계.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

log = logging.getLogger("user-name-resolver")


# ──────────────────────────────────────────────
# 설정 — 기본 registry 경로
# ──────────────────────────────────────────────
DEFAULT_REGISTRY_PATH = Path(
    os.environ.get(
        "HERMES_USER_REGISTRY",
        "/home/aimed/.hermes/memories/user_registry.yaml",
    )
)


# ──────────────────────────────────────────────
# YAML 로딩 (캐시, TTL 5분)
# ──────────────────────────────────────────────
@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
    """
    user_registry.yaml 읽기. 실패 시 빈 dict 반환.

    LRU cache는 5분 TTL을 외부에서 관리 (invalidate_cache() 호출).
    """
    path = DEFAULT_REGISTRY_PATH
    if not path.exists():
        log.warning("User registry not found: %s", path)
        return {"users": {}, "channels": {}, "genres": {}}

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        log.info("Loaded user registry: %d users", len(data.get("users", {})))
        return data
    except Exception:
        log.exception("Failed to load user registry")
        return {"users": {}, "channels": {}, "genres": {}}


def invalidate_cache() -> None:
    """registry YAML 파일이 변경됐을 때 호출"""
    _load_registry.cache_clear()


# ──────────────────────────────────────────────
# 이름 매칭
# ──────────────────────────────────────────────
def resolve_by_name(name: str) -> Optional[dict[str, Any]]:
    """
    이름 문자열로 사용자 정보 조회.

    반환 예시:
      {
        "slack_id": "U012ABC34",
        "name": "김대리",
        "team": "aimed-puzzle",
        "genre": "puzzle",
        "role": "designer",
        "projects": ["balloonflow"],
        "preferences": {...}
      }

    매칭 규칙 (우선순위):
      1. 정확한 name 일치 (대소문자 무시, 공백 trim)
      2. registry 키(Slack user ID) 일치
      3. None (매칭 실패)
    """
    if not name:
        return None

    name_clean = name.strip().lower()
    registry = _load_registry()
    users = registry.get("users", {})

    # 1. name 필드로 매칭
    for slack_id, user_info in users.items():
        if not isinstance(user_info, dict):
            continue
        stored_name = (user_info.get("name") or "").strip().lower()
        if stored_name and stored_name == name_clean:
            return {"slack_id": slack_id, **user_info}

    # 2. slack_id(키)로 매칭 — "U012ABC34"로 직접 조회한 경우
    if name in users:
        user_info = users[name]
        if isinstance(user_info, dict):
            return {"slack_id": name, **user_info}

    # 3. 부분 일치 (예: "김" 입력 시 "김대리" 매칭) — 애매하니 명시적 요청 시만
    # TODO: Phase 2에 fuzzy 매칭 추가 검토

    log.debug("No user match for name=%r", name)
    return None


def resolve_by_channel(channel: str) -> Optional[dict[str, Any]]:
    """
    Slack 채널명 → 기본 스코프 조회 (채널 단위 기본값).
    Phase 1엔 ProjectHub만 쓰니 거의 사용 안 하지만, Phase 2 Slack 연동 대비.
    """
    if not channel:
        return None
    registry = _load_registry()
    channels = registry.get("channels", {})
    return channels.get(channel)


# ──────────────────────────────────────────────
# 프로젝트 추론
# ──────────────────────────────────────────────
def infer_project_from_text(text: str, registry_projects: Optional[list[str]] = None) -> Optional[str]:
    """
    Task title/description에서 프로젝트명 추론.

    예: "Balloonflow 레벨 47 재밸런싱" → "balloonflow"
    """
    if not text:
        return None
    lower = text.lower()

    # registry에 등록된 프로젝트 우선 매칭
    known_projects = registry_projects or _all_known_projects()
    for proj in known_projects:
        if proj.lower() in lower:
            return proj

    return None


def _all_known_projects() -> list[str]:
    """registry에서 모든 사용자의 projects 합집합"""
    registry = _load_registry()
    projects: set[str] = set()
    for user_info in registry.get("users", {}).values():
        if isinstance(user_info, dict):
            for p in user_info.get("projects", []) or []:
                projects.add(p)
    return sorted(projects)


# ──────────────────────────────────────────────
# 프로젝트 → 장르 매핑 (사용자 정보 부재 시 폴백)
# ──────────────────────────────────────────────
# user_registry에 등록되지 않은 사용자가 만든 task도 적절한 장르 컨텍스트를
# 받을 수 있도록 project 이름에서 genre를 추론한다.
PROJECT_GENRE_MAP: dict[str, str] = {
    "balloonflow": "puzzle",
    "fantapuzzle": "puzzle",
    "carmatch": "puzzle",
    "magicsort": "puzzle",
    "shifttap": "puzzle",
    "tamplepuzzle": "puzzle",
    "sortpuzzlebase": "puzzle",
    "dropcat": "puzzle",
    "ashandveil": "rpg",
    "ash_n_veil": "rpg",
    "veilbreaker": "rpg",
    "idlemoney": "idle",
}


def infer_genre_from_project(project: Optional[str]) -> Optional[str]:
    """프로젝트 이름에서 장르를 추론. 매핑 없으면 None."""
    if not project:
        return None
    return PROJECT_GENRE_MAP.get(project.lower())


# ──────────────────────────────────────────────
# 통합 조회 — task로부터 전체 스코프 추론
# ──────────────────────────────────────────────
def resolve_scope_from_task(task: dict[str, Any]) -> dict[str, Any]:
    """
    Task 전체 맥락(assignor/comments/title/description)에서
    team/role/project 스코프를 최대한 추론.

    반환:
      {
        "team": str | None,
        "genre": str | None,
        "role": str | None,
        "project": str | None,
        "user": dict | None,  # resolve_by_name() 결과
      }
    """
    scope: dict[str, Any] = {
        "team": None,
        "genre": None,
        "role": None,
        "project": None,
        "user": None,
    }

    # 1. 누가 요청했는지 추정
    #    - comments 중 hermes 아닌 첫 author = 최초 요청자
    #    - 없으면 assignee를 과거에 누가 넘긴 건지 알 수 없으니 skip
    requester_name: Optional[str] = None
    for comment in task.get("comments") or []:
        author = (comment.get("author") or "").strip()
        if author and author.lower() not in {"hermes", "hermes-bot", "헤르메스"}:
            requester_name = author
            break

    if requester_name:
        user = resolve_by_name(requester_name)
        if user:
            scope["user"] = user
            scope["team"] = user.get("team")
            scope["genre"] = user.get("genre")
            scope["role"] = user.get("role")

    # 2. 프로젝트 추론: user.projects에 하나만 있으면 그것, 아니면 title/description에서 매칭
    if scope["user"]:
        user_projects = scope["user"].get("projects") or []
        if len(user_projects) == 1:
            scope["project"] = user_projects[0]

    if not scope["project"]:
        text = f"{task.get('title', '')} {task.get('description', '')}"
        inferred = infer_project_from_text(text)
        if inferred:
            scope["project"] = inferred

    # 3. genre 폴백: user_registry 미등록 케이스도 project→genre 매핑으로 보정
    #    (puzzle 표준 등 _shared/<pipeline>/ 자동 로드에 필요)
    if not scope["genre"] and scope["project"]:
        scope["genre"] = infer_genre_from_project(scope["project"])

    return scope
