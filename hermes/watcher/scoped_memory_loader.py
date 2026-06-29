"""
Scoped Memory Loader — 팀/롤/프로젝트에 따라 Hermes 메모리 파일들을 계층적으로 로드

로드 순서 (우선순위 낮음 → 높음):
  1. global/*.md
  2. teams/[genre]/_shared/*.md
  2b. teams/[genre]/_shared/[pipeline_hint]/*.md|*.yaml  (조건부 — design 파이프라인 등)
  3. teams/[genre]/[team]/team.md, conventions.md
  4. teams/[genre]/[team]/roles/[role].md
  5. teams/[genre]/[team]/projects/[project].md
  6. users/[slack_id].md  (개인 선호, DM 상황에서만)

각 파일은 ~500~1500 토큰 기준. 초과 시 Hermes 쪽에서 자동 압축.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("scoped-memory-loader")

# ──────────────────────────────────────────────
# 메모리 루트 경로
# ──────────────────────────────────────────────
MEMORY_ROOT = Path(
    os.environ.get(
        "HERMES_MEMORY_ROOT",
        "/home/aimed/.hermes/memories",
    )
)


# ──────────────────────────────────────────────
# 파일 읽기 (캐시)
# ──────────────────────────────────────────────
@lru_cache(maxsize=128)
def _read_file(path_str: str) -> Optional[str]:
    """경로를 문자열로 받아 파일 내용 반환 (캐시용)"""
    path = Path(path_str)
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        log.exception("Failed to read %s", path)
        return None


def invalidate_cache() -> None:
    """메모리 파일이 변경됐을 때 호출 (rsync 후 등)"""
    _read_file.cache_clear()


# ──────────────────────────────────────────────
# 메인 로드 함수
# ──────────────────────────────────────────────
def load_scoped_memory(
    *,
    team: Optional[str] = None,
    genre: Optional[str] = None,
    role: Optional[str] = None,
    project: Optional[str] = None,
    slack_id: Optional[str] = None,
    include_user_private: bool = False,
    pipeline_hint: Optional[str] = None,
) -> list[dict[str, Any]]:
    """
    스코프에 맞는 메모리 파일들을 순서대로 로드.

    반환:
      [
        {"path": "global/tech-stack.md", "content": "..."},
        {"path": "teams/puzzle/aimed-puzzle/team.md", "content": "..."},
        ...
      ]

    include_user_private=True면 users/[slack_id].md도 포함. DM 채널에서만 True.
    pipeline_hint이 지정되면 _shared/<pipeline_hint>/*.md|*.yaml 추가 로드 (예: 'design').
    """
    files: list[dict[str, Any]] = []

    def _add(relative_path: str) -> None:
        full = MEMORY_ROOT / relative_path
        content = _read_file(str(full))
        if content is not None:
            files.append({"path": relative_path, "content": content})
        else:
            log.debug("Memory file not found (skipping): %s", relative_path)

    # 1. Global 파일들 (전사 공통)
    global_dir = MEMORY_ROOT / "global"
    if global_dir.is_dir():
        for p in sorted(global_dir.glob("*.md")):
            _add(f"global/{p.name}")

    # 2. 장르 공통 (_shared) — *.md만 always 로드
    if genre:
        shared_dir = MEMORY_ROOT / "teams" / genre / "_shared"
        if shared_dir.is_dir():
            for p in sorted(shared_dir.glob("*.md")):
                _add(f"teams/{genre}/_shared/{p.name}")

    # 2b. 파이프라인 전용 표준 (_shared/<pipeline_hint>/) — 해당 파이프라인 태스크만 로드
    #     design 파이프라인일 때 puzzle 표준 명세(methodologies + parameters/component_map yaml)를 주입.
    #     dev/art는 토큰 부담 없음.
    if genre and pipeline_hint:
        # 파이프라인 디렉토리 이름은 단순화 (영문/숫자/언더스코어만 허용)
        safe_hint = "".join(c for c in pipeline_hint if c.isalnum() or c == "_")
        if safe_hint:
            pipe_dir = MEMORY_ROOT / "teams" / genre / "_shared" / safe_hint
            if pipe_dir.is_dir():
                for ext in ("*.md", "*.yaml", "*.yml"):
                    for p in sorted(pipe_dir.glob(ext)):
                        _add(f"teams/{genre}/_shared/{safe_hint}/{p.name}")

    # 3. 팀 파일 (team.md, conventions.md)
    if genre and team:
        team_dir = MEMORY_ROOT / "teams" / genre / team
        if team_dir.is_dir():
            _add(f"teams/{genre}/{team}/team.md")
            _add(f"teams/{genre}/{team}/conventions.md")

            # 4. 롤 가이드
            if role:
                _add(f"teams/{genre}/{team}/roles/{role}.md")

            # 5. 프로젝트 상태
            if project:
                _add(f"teams/{genre}/{team}/projects/{project}.md")

    # 6. 개인 메모리 (DM 상황만)
    if include_user_private and slack_id:
        _add(f"users/{slack_id}.md")

    # MEMORY.md는 항상 끝에 추가 (Hermes가 기본 주입하는 최소 공통 맥락)
    _add("MEMORY.md")

    log.info("Loaded %d memory files (team=%s, role=%s, project=%s, pipeline=%s)",
             len(files), team, role, project, pipeline_hint)
    return files


# ──────────────────────────────────────────────
# 토큰 추정 (대략)
# ──────────────────────────────────────────────
def estimate_total_tokens(files: list[dict[str, Any]]) -> int:
    """
    로드된 메모리 파일들의 총 토큰 수 대략 추정.
    한글 기준 문자 수 * 0.7 정도로 가정 (매우 근사).
    """
    total_chars = sum(len(f["content"]) for f in files)
    return int(total_chars * 0.7)


# ──────────────────────────────────────────────
# 편의: 컨텍스트 문자열로 합치기
# ──────────────────────────────────────────────
def format_as_prompt(files: list[dict[str, Any]]) -> str:
    """
    메모리 파일들을 LLM 프롬프트에 주입할 수 있는 형태로 포맷.
    """
    parts: list[str] = []
    for f in files:
        parts.append(f"### [MEMORY] {f['path']}\n\n{f['content']}\n")
    return "\n".join(parts)
