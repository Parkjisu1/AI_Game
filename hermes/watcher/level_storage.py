"""
Level Storage — pixelforge_levels 컬렉션 + PNG 디스크 저장.

스키마 (pixelforge_levels 컬렉션):
  _id              ObjectId
  task_id          str (선택 — task에서 트리거됐으면)
  task_title       str
  created_by_email str
  created_at       ISO datetime

  # spec (LLM이 결정한 것)
  name             str       — 사람이 보기 좋은 라벨
  width            int       — 25, 30 등
  height           int       — 25
  symmetry         str       — "none" | "2-fold-h" | "2-fold-v" | "4-fold" | "diagonal" | "4-fold-rot"
  palette          int[]     — BalloonFlow color indices (0..23) 의 부분집합, 2-11개
  per_color_count  {int:int} — 각 색상의 총 셀 수 (10의 배수)
  seed             int

  # result (generator 출력)
  cells            int[][]   — height × width, -1 = empty
  png_filename     str       — STORAGE_DIR 기준 상대경로 (예: "2026-04-28/<id>.png")

  # validation (validator 출력)
  validation       {
    ok           bool,
    errors       str[],
    color_counts {int:int},
    filled_cells int,
    empty_cells  int,
  }

  # 후속 추적
  reviewer_score    int        (선택 — design_level_reviewer가 매긴 0-100)
  reviewer_notes    str
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("level-storage")


def compute_structure_hash(cells: list[list[int]]) -> str:
    """
    색상 정체 무시 — cells의 STRUCTURE만으로 해시.
    첫 등장 색상 → 0, 두 번째 색상 → 1, ... 로 normalize.
    빈칸(-1)은 그대로.
    => 같은 구조 + 다른 팔레트 = 같은 hash → dedup 가능.
    """
    color_map: dict[int, int] = {}
    next_id = 0
    parts: list[str] = []
    for row in cells:
        rn: list[str] = []
        for c in row:
            if c == -1 or c is None:
                rn.append("-")
            else:
                if c not in color_map:
                    color_map[c] = next_id
                    next_id += 1
                rn.append(str(color_map[c]))
        parts.append(",".join(rn))
    s = "|".join(parts)
    return hashlib.sha256(s.encode()).hexdigest()[:32]


def structure_exists(structure_hash: str) -> bool:
    """이 structure_hash로 저장된 레벨이 이미 있는지."""
    db = _get_db()
    if db is None:
        return False
    try:
        return db[LEVELS_COLLECTION].count_documents(
            {"structure_hash": structure_hash}, limit=1
        ) > 0
    except Exception:
        return False

# 별도 컬렉션 — pixelforge_levels는 BalloonFlow 게임 자체의 레벨 데이터(chapter, gimmick 등)가
# 300건 들어있는 기존 컬렉션. 우리 grid level은 schema가 완전히 달라 격리한다.
LEVELS_COLLECTION = "pixelforge_grid_levels"
LEVELS_STORAGE_DIR = os.environ.get(
    "LEVELS_STORAGE_DIR", "/home/aimed/projecthub-web/data/levels",
)


def _get_db():
    try:
        from pymongo import MongoClient
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            return None
        db_name = os.environ.get("MONGODB_DB", "aigame")
        return MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    except Exception:
        return None


def save_level(
    *,
    spec: dict[str, Any],
    cells: list[list[int]],
    png_bytes: bytes,
    validation: dict[str, Any],
    task_id: Optional[str] = None,
    task_title: str = "",
    created_by_email: str = "",
    name: str = "",
    team_id: Optional[str] = None,        # 경쟁 팀 ID (hermes_native/geometric/organic/tile)
    pattern_chosen: Optional[str] = None, # 팀이 고른 패턴 이름
    mood: Optional[str] = None,           # batch 분류 (warm/cool/pastel/vivid)
    extra_meta: Optional[dict[str, Any]] = None,  # 추가 batch metadata
) -> dict[str, Any]:
    """
    레벨 1건 저장: PNG → 디스크, document → DB.
    반환: {"id": str, "png_filename": str, "abs_png_path": str}
    """
    db = _get_db()
    if db is None:
        raise RuntimeError("MongoDB unavailable")

    from bson import ObjectId
    oid = ObjectId()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rel_filename = f"{today}/{oid}.png"
    abs_path = Path(LEVELS_STORAGE_DIR) / rel_filename
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(png_bytes)

    doc = {
        "_id": oid,
        "task_id": task_id,
        "task_title": task_title,
        "created_by_email": (created_by_email or "").strip().lower(),
        "created_at": datetime.now(timezone.utc).isoformat(),

        "name": name or "(unnamed level)",
        "width":  int(spec.get("width", 0)),
        "height": int(spec.get("height", 0)),
        "symmetry": spec.get("symmetry") or "none",
        "pattern": spec.get("pattern") or "rings",
        "palette": list(spec.get("palette") or []),
        # MongoDB는 dict key가 string이어야 함 — int 색상 인덱스를 str로 변환
        "per_color_count": {
            str(k): int(v) for k, v in (spec.get("per_color_count") or {}).items()
        },
        "seed": int(spec.get("seed", 0)),

        # 색상 무시 구조 hash — 색상만 다른 변형 dedup용
        "structure_hash": compute_structure_hash(cells),

        "cells": cells,
        "png_filename": rel_filename,

        "validation": validation,

        # 경쟁 팀 메타 (T3+)
        "team_id": team_id,
        "pattern_chosen": pattern_chosen,
        "user_score": None,        # 사용자 1~5 별점 (T4에서 set)
        "user_score_at": None,
        # Batch 메타 (Q-batch)
        "mood": mood,
        "batch_meta": extra_meta or {},
    }
    db[LEVELS_COLLECTION].insert_one(doc)

    # 양방향 링크: task가 있으면 generated_level_ids에 추가
    if task_id:
        try:
            db["pixelforge_tasks"].update_one(
                {"_id": ObjectId(task_id)},
                {"$addToSet": {"generated_level_ids": str(oid)},
                 "$set": {"updated_at": datetime.utcnow().isoformat()}},
            )
        except Exception:
            log.exception("task back-reference update failed")

    return {
        "id": str(oid),
        "png_filename": rel_filename,
        "abs_png_path": str(abs_path),
    }


def fetch_level(level_id: str) -> Optional[dict[str, Any]]:
    db = _get_db()
    if db is None:
        return None
    try:
        from bson import ObjectId
        return db[LEVELS_COLLECTION].find_one({"_id": ObjectId(level_id)})
    except Exception:
        return None


# ───────── self-test ─────────
if __name__ == "__main__":
    """샘플 1건 저장 후 다시 fetch해서 round-trip 검증."""
    from level_grid_generator import GridSpec, generate_grid
    from level_validator import validate_grid
    from level_png_renderer import render_grid_to_png

    spec_obj = GridSpec(
        width=25, height=25, symmetry="4-fold-rot",
        palette=[2, 4, 17, 13, 0],
        per_color_count={2: 40, 4: 20, 17: 60, 13: 20, 0: 40},
        seed=42, name="L2-roundtrip-test",
    )
    result = generate_grid(spec_obj)
    v = validate_grid(
        result.cells, symmetry=spec_obj.symmetry, palette=spec_obj.palette,
        width=spec_obj.width, height=spec_obj.height,
    )
    png = render_grid_to_png(
        result.cells, cell_size_px=24,
        title=f"L2 roundtrip · {spec_obj.symmetry}",
    )

    saved = save_level(
        spec={
            "width": spec_obj.width, "height": spec_obj.height,
            "symmetry": spec_obj.symmetry, "palette": spec_obj.palette,
            "per_color_count": spec_obj.per_color_count, "seed": spec_obj.seed,
        },
        cells=result.cells, png_bytes=png,
        validation={
            "ok": v.ok, "errors": v.errors,
            "color_counts": {str(k): v_ for k, v_ in v.color_counts.items()},
            "filled_cells": v.filled_cells,
            "empty_cells": v.empty_cells,
        },
        name=spec_obj.name,
        created_by_email="hermes-self-test@aimed.xyz",
    )
    print(f"✓ saved level id={saved['id']}")
    print(f"  png path: {saved['abs_png_path']}")

    # round-trip
    doc = fetch_level(saved["id"])
    assert doc is not None
    assert doc["symmetry"] == "4-fold-rot"
    assert len(doc["cells"]) == 25
    assert doc["validation"]["ok"]
    print(f"✓ round-trip fetch — symmetry={doc['symmetry']}, "
          f"cells={len(doc['cells'])}x{len(doc['cells'][0])}, "
          f"valid={doc['validation']['ok']}")
    print("\n✅ L2 storage roundtrip passed")
