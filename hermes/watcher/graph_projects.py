#!/usr/bin/env python3
"""
graph_projects.py — 코드 그래프를 만들 프로젝트 목록/설정을 한 곳에서 푼다.

배경
  `/balloonflow` 화면과 `bf_graph_refresh.py` 가 BalloonFlow 를 상수로 박고 있었다
  (`REPO`, `PUBLIC`, `SHAFILE`, 그래프 파일명, 회귀 Slack 문구까지).
  게임이 늘어날 때마다 코드를 복제해야 하는 구조라, 설정만 늘리면 되도록 분리한다.

설정 출처 (뒤가 앞을 덮어씀)
  1. BUILTIN            — 레지스트리에 없는 레거시(BalloonFlow)
  2. hermes_projects    — 온보딩된 프로젝트(repo.host/dir, display_name, genre)
  3. hermes_projects.graph — 프로젝트별 그래프 설정 오버라이드
     { "enabled": true, "subdir": "BalloonFlow", "scripts": "Assets/1.Scripts",
       "branch": "origin/main", "embed_project": "BalloonFlow" }

`subdir` 는 git 루트 밑 Unity 프로젝트 폴더다.
  C:/projects/crewflowrotation (git 루트) / CrewFlowRotation (Unity) / Assets/1.Scripts
"""
from __future__ import annotations

import os
from typing import Any

PUBLIC_DIR = os.environ.get("NEWPLAY_GRAPH_PUBLIC", "/home/aimed/projecthub-web/public")
STATE_DIR = os.environ.get("HERMES_GRAPH_STATE", "/home/aimed/.hermes")

#: 레지스트리에 없는 레거시. BalloonFlow 는 hermes_projects 에 온보딩된 적이 없다.
BUILTIN: dict[str, dict[str, Any]] = {
    "balloonflow": {
        "project": "balloonflow",
        "display_name": "BalloonFlow",
        "genre": "puzzle",
        "host": "user@100.92.43.9",
        "root": "C:/projects/balloonflow",
        "subdir": "BalloonFlow",
        "scripts": "Assets/1.Scripts",
        "branch": "origin/main",
        # code_base 업서트 시 쓰는 project 값 (기존 문서와 맞춰야 한다 — 대소문자 주의)
        "embed_project": "BalloonFlow",
        "embed": True,
        "enabled": True,
    },
}


def _split_marker(scripts: str) -> str:
    """mjs 가 파일 경로에서 상대경로를 자를 기준. `Assets/1.Scripts` → `/1.Scripts/`"""
    tail = (scripts or "").rstrip("/").split("/")[-1] or "1.Scripts"
    return f"/{tail}/"


def _db():
    from pymongo import MongoClient
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        return None
    return MongoClient(uri, serverSelectionTimeoutMS=8000)[os.environ.get("MONGODB_DB", "aigame")]


def _from_registry(doc: dict[str, Any]) -> dict[str, Any] | None:
    """hermes_projects 문서 → 그래프 설정. 그래프를 만들 수 없으면 None."""
    repo = doc.get("repo") or {}
    host, root = repo.get("host"), repo.get("dir")
    if not host or not root:
        return None

    g = doc.get("graph") or {}
    if g.get("enabled") is False:
        return None

    # Unity(C#) 만 지원한다 — 추출기(bf_graph_refresh.mjs)가 .cs 파서다.
    # 명시적으로 켜 준 경우엔 존중한다(다른 추출기를 붙였을 수 있으므로).
    engine = str((doc.get("profile") or {}).get("engine") or "")
    if g.get("enabled") is not True and repo.get("type") != "unity" and "Unity" not in engine:
        return None

    slug = str(doc.get("project") or "").strip().lower()
    if not slug:
        return None
    display = str(doc.get("display_name") or slug)
    return {
        "project": slug,
        "display_name": display,
        "genre": doc.get("genre") or "generic",
        "host": host,
        "root": str(root).rstrip("/"),
        # Unity 프로젝트 폴더명은 보통 display_name 과 같다. 다르면 graph.subdir 로 지정.
        "subdir": g.get("subdir", display),
        "scripts": g.get("scripts", "Assets/1.Scripts"),
        "branch": g.get("branch", "origin/main"),
        "embed_project": g.get("embed_project", display),
        # 임베딩(code_base 업서트)은 기본 끔 — 켜면 프로젝트마다 OpenAI 비용이 붙는다.
        "embed": bool(g.get("embed", False)),
        "enabled": True,
    }


def resolve(slug: str) -> dict[str, Any] | None:
    """프로젝트 하나의 그래프 설정. 없으면 None."""
    slug = (slug or "").strip().lower()
    for cfg in all_projects():
        if cfg["project"] == slug:
            return cfg
    return None


def all_projects() -> list[dict[str, Any]]:
    """그래프를 만들 수 있는 프로젝트 전부. BUILTIN 이 앞, 레지스트리가 뒤."""
    out: dict[str, dict[str, Any]] = {k: dict(v) for k, v in BUILTIN.items()}
    try:
        db = _db()
        if db is not None:
            for doc in db["hermes_projects"].find({}):
                cfg = _from_registry(doc)
                if cfg:
                    # BUILTIN 과 겹치면 레지스트리 값으로 덮되, 빠진 키는 BUILTIN 을 유지
                    base = out.get(cfg["project"], {})
                    out[cfg["project"]] = {**base, **cfg}
    except Exception:
        pass  # DB 없어도 BUILTIN 으로는 돈다
    for cfg in out.values():
        cfg["repo_dir"] = "/".join(x for x in [cfg["root"], cfg.get("subdir") or ""] if x)
        cfg["graph_file"] = os.path.join(PUBLIC_DIR, f"{cfg['project']}-graph.json")
        cfg["sha_file"] = os.path.join(STATE_DIR, f"{cfg['project']}_graph.lastsha")
        cfg["split_marker"] = _split_marker(cfg["scripts"])
    return sorted(out.values(), key=lambda c: (c["project"] != "balloonflow", c["project"]))


if __name__ == "__main__":  # 설정 점검용
    import json
    for c in all_projects():
        print(json.dumps(c, ensure_ascii=False))
