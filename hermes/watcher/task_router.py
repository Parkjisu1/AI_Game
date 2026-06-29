"""
Task Router — Task 제목/설명/태그를 분석해 적절한 실행 도구 선택

반환 action 타입:
  - "db_query"       : MongoDB 쿼리 (Stage 1)
  - "simulation"     : scripts/balance-simulator.js 등 (Stage 2)
  - "apk_build"      : 머신 B SSH 빌드 (Stage 3)
  - "gameforge_design" : /generate-design (Stage 4)
  - "gameforge_code"   : /generate-code, /validate-code (Stage 5)
  - "gameforge_pipeline" : 풀 파이프라인 (Stage 6)
  - "chat"           : 단순 질의응답 (기본 fallback)
  - "review_needed"  : 자동 처리 불가, 사람 개입 필요

Stage 1 (현재 활성): db_query, chat, apk_build, simulation
Stage 2+ (점진 활성): gameforge_* — 설정으로 켜고 끔
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

log = logging.getLogger("task-router")


# ──────────────────────────────────────────────
# 활성 Stage (환경변수로 제어)
# ──────────────────────────────────────────────
# 기본값: Stage 1~3만 자동 처리. GameForge 호출은 수동 승인 필요.
ACTIVE_STAGES = set(
    int(s) for s in os.environ.get("HERMES_ACTIVE_STAGES", "1,2,3").split(",")
    if s.strip().isdigit()
)


# ──────────────────────────────────────────────
# 태그 추출 — #tag 또는 [tag] 형식 지원
# ──────────────────────────────────────────────
TAG_PATTERNS = [
    re.compile(r"#(\w+)"),       # #unity
    re.compile(r"\[(\w+(?:-\w+)*)\]"),  # [unity] 또는 [unity-modify]
]


def extract_tags(text: str) -> set[str]:
    """title/description에서 #태그 또는 [태그] 추출"""
    if not text:
        return set()
    tags: set[str] = set()
    for pat in TAG_PATTERNS:
        for m in pat.finditer(text):
            tags.add(m.group(1).lower())
    return tags


# ──────────────────────────────────────────────
# 키워드 매핑 (태그 없을 때 fallback)
# ──────────────────────────────────────────────
KEYWORD_RULES = [
    # (키워드 집합, action, required_stage)
    # 주의: 순서 중요. 상위 규칙이 먼저 매칭됨.
    # unity_modify가 sync/pull보다 우선 — [unity][sync] 같은 조합 태스크는
    # unity_modify로 가야 함 (unity 파이프라인의 branch_prep 단계에서 이미
    # git fetch + pull --rebase를 수행하므로 sync가 자동 포함됨).
    # 순수 "[sync] main 최신화"처럼 unity 언급 없을 때만 git_sync로 떨어짐.
    ({"unity", "c#", ".cs", "수정", "patch"}, "unity_modify", 3),
    ({"pull", "sync", "동기화", "최신화", "main에서", "main 반영"}, "git_sync", 1),
    ({"apk", "gradle", "릴리스", "release", "assembleRelease", "apk 빌드"}, "apk_build", 3),
    ({"db", "쿼리", "조회", "검색", "리스트"}, "db_query", 1),
    ({"balance", "밸런스", "시뮬", "simulation", "클리어율"}, "simulation", 2),
    # 아트·기획·UI 작업: Translator가 팀 분류하도록 chat 핸들러로 보낸다 (Translator → PM → 분과 파이프라인)
    # 주의: 이 룰은 review_needed보다 위에 있어야 하며, GameForge stage4는 명시적 [generate-design] 태그일 때만 작동
    ({"아트", "art", "이미지 생성", "image gen", "스프라이트", "sprite", "일러스트", "illustration", "ui 세트", "ui 디자인", "ui 작업", "atlas", "아틀라스",
      # design/level 격자 패턴 키워드 — Translator가 team=design 으로 분류, design_pm이 sub_team=level 결정
      "만화경", "kaleidoscope", "격자", "grid 패턴", "grid pattern", "tilemap", "타일맵", "스테이지 레이아웃", "level layout"}, "chat", 1),
    ({"generate-design"}, "gameforge_design", 4),
    ({"코드", "phase", "main coder", "sub coder"}, "gameforge_code", 5),
    ({"파이프라인", "pipeline", "end-to-end", "e2e"}, "gameforge_pipeline", 6),
    ({"학습", "훈련", "train", "qlora", "파인튜닝"}, "training", 5),
    # review_needed는 명시적 트리거(사람 개입 필요)일 때만. "리뷰", "review" 단어가 description 본문에
    # 자연스럽게 들어가는 케이스(예: "art_ui_reviewer 참고")는 매칭하면 안 됨.
    ({"사람 개입", "manual review", "review needed", "수동 처리 필요", "자동 처리 불가"}, "review_needed", 1),
]


# ──────────────────────────────────────────────
# 라우팅 결정
# ──────────────────────────────────────────────
def route_task(task: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    """
    Task를 분석해 실행 action 결정.

    반환:
      {
        "action": str,           # 위 action 타입 중 하나
        "reason": str,           # 왜 이 action을 골랐는지
        "stage": int,            # 필요한 stage 레벨
        "params": dict,          # 실행에 필요한 파라미터
        "auto_execute": bool,    # True면 자동 실행, False면 사람 승인 필요
      }
    """
    title = task.get("title", "")
    description = task.get("description", "")
    combined = f"{title}\n{description}".lower()

    # 1. 태그 기반 라우팅 (우선순위 최상)
    all_tags = extract_tags(f"{title} {description}")
    tag_action = _tag_to_action(all_tags)
    if tag_action:
        action = tag_action
        reason = f"tag match: {all_tags}"
    else:
        # 2. 키워드 기반
        action, reason = _keyword_to_action(combined)

    # 3. Stage 활성 여부 확인
    required_stage = _stage_for_action(action)
    auto_execute = required_stage in ACTIVE_STAGES

    # 4. 파라미터 추출
    params = _extract_params(task, action)

    result = {
        "action": action,
        "reason": reason,
        "stage": required_stage,
        "params": params,
        "auto_execute": auto_execute,
    }

    if not auto_execute:
        result["notice"] = (
            f"Stage {required_stage}는 현재 비활성화됨. "
            f"환경변수 HERMES_ACTIVE_STAGES에 {required_stage} 추가 필요."
        )
        log.info("Action %s requires stage %d (not active) — routing to review", action, required_stage)
        # 비활성 stage면 review_needed로 강제 변경
        result["action"] = "review_needed"
        result["deferred_action"] = action

    log.info("Routed: action=%s, stage=%d, auto=%s, reason=%s",
             result["action"], required_stage, auto_execute, reason)
    return result


# ──────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────
TAG_ACTION_MAP = {
    "sync": "git_sync",            # 단순 git pull 동기화 (에이전트 호출 없음)
    "pull": "git_sync",
    "db-query": "db_query",
    "query": "db_query",
    "search": "db_query",
    "simulation": "simulation",
    "sim": "simulation",
    "balance": "simulation",
    "apk-build": "apk_build",
    "build": "apk_build",
    "unity": "unity_modify",       # 멀티 에이전트 팀 — C# 수정 + PR
    "code-change": "unity_modify",
    "fix": "unity_modify",
    "patch": "unity_modify",
    # 아트·기획·UI 태그: chat으로 보내서 Translator가 team 분류 → PM → 해당 분과 파이프라인
    "아트": "chat",
    "art": "chat",
    "ui": "chat",
    "image": "chat",
    "이미지": "chat",
    "sprite": "chat",
    "스프라이트": "chat",
    "illust": "chat",
    "illustration": "chat",
    "일러스트": "chat",
    "원화": "chat",
    "concept": "chat",
    "background": "chat",
    "배경": "chat",
    "기획": "chat",
    "plan": "chat",
    "content": "chat",
    "level": "chat",
    "레벨": "chat",
    "design": "chat",              # 기획 태그는 chat으로 (GameForge stage4는 [generate-design] 명시 태그만)
    "generate-design": "gameforge_design",
    "code": "gameforge_code",
    "validate": "gameforge_code",
    "pipeline": "gameforge_pipeline",
    "train": "training",
    "ask": "chat",
    "chat": "chat",
    # review 태그는 의도적인 사람 개입 요청일 때만 — 일반 작업에 [review_needed] 명시한 경우만
    "review_needed": "review_needed",
}


def _tag_to_action(tags: set[str]) -> str | None:
    # 우선순위: unity_modify가 git_sync를 흡수 (unity 파이프라인의 branch_prep이
    # 자동으로 pull --rebase를 수행하므로 sync를 따로 돌릴 필요 없음).
    # 동일하게 "fix/patch/code-change"처럼 코드 수정 태그가 붙으면 sync 무시.
    UNITY_MODIFY_TAGS = {"unity", "code-change", "fix", "patch"}
    if tags & UNITY_MODIFY_TAGS:
        return "unity_modify"
    for tag in tags:
        if tag in TAG_ACTION_MAP:
            return TAG_ACTION_MAP[tag]
    return None


def _keyword_to_action(text: str) -> tuple[str, str]:
    for keywords, action, _stage in KEYWORD_RULES:
        for kw in keywords:
            if kw in text:
                return action, f"keyword match: {kw}"
    return "chat", "no specific keyword — default to chat"


def _stage_for_action(action: str) -> int:
    mapping = {
        "db_query": 1,
        "chat": 1,
        "review_needed": 1,
        "git_sync": 1,         # 에이전트 없는 단순 git pull
        "simulation": 2,
        "apk_build": 3,
        "unity_modify": 3,     # 멀티 에이전트 Unity 코드 수정 + PR
        "gameforge_design": 4,
        "gameforge_code": 5,
        "training": 5,
        "gameforge_pipeline": 6,
    }
    return mapping.get(action, 99)


def _extract_params(task: dict[str, Any], action: str) -> dict[str, Any]:
    """action별 필요한 파라미터 추출 (description 파싱 등)"""
    title = task.get("title", "")
    description = task.get("description", "")

    params: dict[str, Any] = {
        "title": title,
        "description": description,
        "priority": task.get("priority", "medium"),
        "related_levels": task.get("related_levels", ""),
    }

    if action == "apk_build":
        # 버전 태그 추출 "v1.3" 등
        version_match = re.search(r"v?(\d+\.\d+(?:\.\d+)?)", f"{title} {description}")
        if version_match:
            params["version"] = version_match.group(1)

    elif action == "simulation":
        # 레벨 범위 추출 "레벨 47-52"
        level_match = re.search(r"레벨\s*(\d+(?:-\d+)?)", f"{title} {description}")
        if level_match:
            params["level_range"] = level_match.group(1)

    elif action in ("gameforge_design", "gameforge_code"):
        # 장르, 기능 키워드
        params["genre_hint"] = _extract_genre(description)

    return params


def _extract_genre(text: str) -> str | None:
    """description에서 장르 키워드 추출"""
    text_lower = text.lower()
    for genre in ["puzzle", "퍼즐", "slg", "idle", "방치형", "rpg"]:
        if genre in text_lower:
            return genre
    return None
