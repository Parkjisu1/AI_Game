#!/usr/bin/env python3
"""One-time patch: add field_map computation to ~/.hermes/watcher/field_complete_levels.py:_save_levels_to_db."""
import sys

PATH = "/home/aimed/.hermes/watcher/field_complete_levels.py"

HELPER = '''def _build_field_map_from_balloons(balloons: list, gimmicks: list, rows: int, cols: int) -> str:
    """FC 결과의 balloons + gimmicks → BalloonFlow [FieldMap] 텍스트 그리드.

    Importer가 designer_note[FieldMap]를 파싱.
    2자리 0-padding color code (1-based: c1→"01"), empty→"..".
    """
    if rows <= 0 or cols <= 0:
        return ""
    grid = [[".."] * cols for _ in range(rows)]
    for b in balloons or []:
        r = b.get("row")
        c = b.get("col")
        color = b.get("color")
        if (
            isinstance(r, int) and isinstance(c, int)
            and 0 <= r < rows and 0 <= c < cols
            and isinstance(color, int)
        ):
            grid[r][c] = f"{color:02d}"
    for g in gimmicks or []:
        cells = []
        gcells = g.get("cells")
        if isinstance(gcells, list):
            for cc in gcells:
                if isinstance(cc, (list, tuple)) and len(cc) >= 2:
                    cells.append((cc[0], cc[1]))
        elif isinstance(g.get("row"), int) and isinstance(g.get("col"), int):
            cells.append((g["row"], g["col"]))
        for (r, c) in cells:
            if isinstance(r, int) and isinstance(c, int) and 0 <= r < rows and 0 <= c < cols and grid[r][c] == "..":
                if g.get("type") == "Hidden_Balloon" and isinstance(g.get("hidden_color"), int):
                    grid[r][c] = f'{g["hidden_color"]:02d}'
                elif isinstance(g.get("color"), int):
                    grid[r][c] = f'{g["color"]:02d}'
    return "\\n".join(" ".join(row) for row in grid)


'''

OLD = '''    for r in results:
        if not r.get("ok"):
            continue
        lv = r.get("level_number")
        if lv is None:
            continue
        doc = {
            "level_number": lv,
            "field_completed": True,
            "field_complete_job_id": job_id,
            "field_complete_score": r.get("score"),
            "balloons": r.get("balloons"),
            "gimmicks": r.get("gimmicks"),
            "field_analysis": r.get("field_analysis"),
            "warnings": r.get("warnings"),
            "escalated": r.get("escalated", False),
            "updated_at": now,
        }
        # Upsert key = level_number only.
        # 디자이너 행에 worker 결과 필드를 merge (중복 행 생성 방지, 2026-05-21 fix).
        coll.update_one(
            {"level_number": lv},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
'''

NEW = '''    for r in results:
        if not r.get("ok"):
            continue
        lv = r.get("level_number")
        if lv is None:
            continue
        doc = {
            "level_number": lv,
            "field_completed": True,
            "field_complete_job_id": job_id,
            "field_complete_score": r.get("score"),
            "balloons": r.get("balloons"),
            "gimmicks": r.get("gimmicks"),
            "field_analysis": r.get("field_analysis"),
            "field_complete_warnings": r.get("warnings"),
            "field_complete_escalated": r.get("escalated", False),
            "updated_at": now,
        }

        # field_map 계산 — 디자이너 행에 이미 있으면 보존, 비어있을 때만 채움.
        # 2026-05-21 fix: /levels Queue 생성 + JSON Vault export 에 field_map 필요.
        existing = coll.find_one({"level_number": lv}, {"field_map": 1, "field_rows": 1, "field_columns": 1})
        has_fm = bool(existing and isinstance(existing.get("field_map"), str) and existing.get("field_map", "").strip())
        if not has_fm:
            fa = r.get("field_analysis") or {}
            existing_rows = existing.get("field_rows") if existing else None
            existing_cols = existing.get("field_columns") if existing else None
            try:
                rows = int(existing_rows or fa.get("field_rows") or 0)
            except (TypeError, ValueError):
                rows = int(fa.get("field_rows") or 0)
            try:
                cols = int(existing_cols or fa.get("field_columns") or 0)
            except (TypeError, ValueError):
                cols = int(fa.get("field_columns") or 0)
            fm = _build_field_map_from_balloons(r.get("balloons") or [], r.get("gimmicks") or [], rows, cols)
            if fm:
                doc["field_map"] = fm
                doc["field_map_source"] = "field_complete_v1"

        # Upsert key = level_number only.
        # 디자이너 행에 worker 결과 필드를 merge (중복 행 생성 방지, 2026-05-21 fix).
        coll.update_one(
            {"level_number": lv},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
'''

MARKER = "def _save_levels_to_db(results: list[dict], job_id: str) -> None:"

with open(PATH, encoding="utf-8") as f:
    src = f.read()

if OLD not in src:
    print("OLD pattern not found!", file=sys.stderr)
    sys.exit(1)
if MARKER not in src:
    print("marker not found", file=sys.stderr)
    sys.exit(1)
if "_build_field_map_from_balloons" in src:
    print("already patched (helper present)")
    sys.exit(0)

src2 = src.replace(MARKER, HELPER + MARKER, 1)
src2 = src2.replace(OLD, NEW, 1)
with open(PATH, "w", encoding="utf-8") as f:
    f.write(src2)
print("patched ok")
