#!/usr/bin/env python3
"""Insert metaphor→ZoneMap priority between designer_note [FieldMap] and default_layout.

When designer_note has no [FieldMap] block but CSV has bl_metaphor recognized in
zone_pipeline.METAPHOR_ZONE_MAP, generate field_map from that metaphor using v43.
seed_offset passes through → multi-seed becomes REAL structural diversity.
"""
import sys

PATH = "/home/aimed/.hermes/watcher/field_complete_levels.py"

# 1) Add zone_pipeline import after existing imports (defensive try/except)
OLD_IMPORTS = '''log = logging.getLogger("field-complete")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")'''

NEW_IMPORTS = '''log = logging.getLogger("field-complete")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# v43 hybrid pipeline (metaphor → ZoneMap → BL field_map)
# 호출: STEP 2 designer_note [FieldMap] 없을 때 bl_metaphor 기반 자동 생성
try:
    import zone_pipeline as _zp
    _ZP_AVAILABLE = True
except Exception as _zp_err:
    _ZP_AVAILABLE = False
    log.warning("zone_pipeline import failed (%s) — STEP 2 will use generate_default_layout fallback only", _zp_err)'''

# 2) Insert priority 2.5 (metaphor) between priority 2 (designer_note) and priority 3 (default)
OLD_STEP2 = '''    # 우선순위 2: designer_note의 [FieldMap]
    if field_map is None:
        field_map = parse_field_map(csv_row.get("designer_note", "") or "")
        if field_map is not None:
            field_map_source = "designer_note_fieldmap"

    # 우선순위 3: default 생성
    if field_map is None:
        field_map = generate_default_layout(
            int(csv_row.get("field_rows", 0) or 0),
            int(csv_row.get("field_columns", 0) or 0),
            int(csv_row.get("total_cells", 0) or 0),
            csv_row.get("color_distribution", "") or "",
        )
        field_map_source = "default_layout"'''

NEW_STEP2 = '''    # 우선순위 2: designer_note의 [FieldMap]
    if field_map is None:
        field_map = parse_field_map(csv_row.get("designer_note", "") or "")
        if field_map is not None:
            field_map_source = "designer_note_fieldmap"

    # 우선순위 2.5: bl_metaphor → v43 ZoneMap (시드별 구조 다양성 — multi-seed 진짜 효과)
    if field_map is None and _ZP_AVAILABLE:
        _bl_meta = csv_row.get("bl_metaphor") or csv_row.get("pf_metaphor") or ""
        if _bl_meta and _zp.is_metaphor_recognized(_bl_meta):
            _rows = int(csv_row.get("field_rows", 0) or 0)
            _cols = int(csv_row.get("field_columns", 0) or 0)
            _ncs = int(csv_row.get("num_colors", 0) or 0)
            _lv = int(csv_row.get("level_number", 0) or 1)
            if _rows > 0 and _cols > 0 and _ncs > 0:
                try:
                    _zp_grid, _zp_palette = _zp.generate_field_from_metaphor(
                        rows=_rows, cols=_cols, num_colors=_ncs,
                        metaphor=_bl_meta, level=_lv, seed_offset=seed_offset,
                    )
                    if _zp_grid and len(_zp_grid) == _rows and len(_zp_grid[0]) == _cols:
                        field_map = _zp_grid
                        field_map_source = f"metaphor_v43:{_bl_meta}"
                        # palette IDs 기록 (downstream 검사용)
                        result["zone_pipeline_palette"] = _zp_palette
                except Exception as _zp_e:
                    log.warning("zone_pipeline failed for lv%s metaphor=%r: %s — falling back",
                                csv_row.get("level_number"), _bl_meta, _zp_e)

    # 우선순위 3: default 생성
    if field_map is None:
        field_map = generate_default_layout(
            int(csv_row.get("field_rows", 0) or 0),
            int(csv_row.get("field_columns", 0) or 0),
            int(csv_row.get("total_cells", 0) or 0),
            csv_row.get("color_distribution", "") or "",
        )
        field_map_source = "default_layout"'''


def main():
    with open(PATH, encoding="utf-8") as f:
        src = f.read()
    if "_ZP_AVAILABLE" in src:
        print("already patched. abort.")
        sys.exit(0)
    for old, new, lbl in [(OLD_IMPORTS, NEW_IMPORTS, "imports"),
                          (OLD_STEP2, NEW_STEP2, "STEP 2 priority 2.5")]:
        if old not in src:
            print(f"ABORT — OLD pattern not found: {lbl}", file=sys.stderr)
            sys.exit(1)
        src = src.replace(old, new, 1)
    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("patched ok")


if __name__ == "__main__":
    main()
