"""
gimmick_placement CLI shim — pixelforge-web(TS)가 child_process로 호출.

순수 변환만 수행 (DB 접근 없음 — board는 TS가 Mongo에서 읽어 stdin으로 전달).
stdin:  {"cmd": "variants"|"commit", "board": {...}, "gimmick_type": "Wooden",
         "indexing": "bl"|"pf"|"auto", "variant_index": N(commit 시)}
stdout: JSON 결과 ({"ok": true, ...} 또는 {"ok": false, "error": ...})
"""
import json
import sys
import traceback

import gimmick_placement as gp


def _resolve_indexing(board, indexing):
    if indexing and indexing != "auto":
        return indexing
    colors = [b["color"] for b in board.get("balloons", [])]
    return "bl" if (colors and min(colors) == 0) else "pf"


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        cmd = payload["cmd"]
        board = payload["board"]
        gt = payload.get("gimmick_type", "Wooden")
        indexing = _resolve_indexing(board, payload.get("indexing", "auto"))
        use_vision = bool(payload.get("use_vision"))
        grid, W, H, bg = gp.board_to_grid(board)
        lm = gp.board_life_map(board)  # 표준풍선 dart 가중치(life 합 정합)

        # 선택적 vision 영역 분석 (실패 시 None → 휴리스틱 fallback)
        vinfo = None
        regions = None
        if use_vision:
            try:
                import vision as vz
                v = vz.analyze_board_vision(board)
                if v and not v.get("_vision_error"):
                    regions = vz.resolve_regions_from_vision(v, board) or None
                    vinfo = {"metaphor": v.get("metaphor"), "category": v.get("category"),
                             "regions_used": len(regions or []),
                             "labels": [r.get("label") for r in (regions or [])]}
                elif v:
                    vinfo = {"error": v.get("_vision_error")}
            except Exception as e:  # noqa: BLE001
                vinfo = {"error": f"{type(e).__name__}: {e}"}

        if cmd == "variants":
            variants = gp.generate_variants(board, gt, regions=regions)
            out = []
            for v in variants:
                fix = gp.auto_fix_variant(grid, v, gt, life_map=lm)  # 미리보기: auto-fix 시 결과 예고
                out.append({
                    "name": v["name"],
                    "instances": v["instances"],
                    "validation": v["validation"],
                    "auto_fix_clean": fix["clean"],
                    "designer_needed": fix["designer_needed"],
                    "preview_b64": gp.render_variant_png(board, v, indexing=indexing),
                })
            print(json.dumps({"ok": True, "grid": {"W": W, "H": H, "bg": bg},
                              "gimmick_type": gt, "indexing": indexing,
                              "vision": vinfo, "variants": out}))

        elif cmd == "commit":
            # 선택안을 직접 받음(권장) — vision 비결정성/index 미스매치 방지.
            # 하위호환: variant 없으면 variant_index로 재생성(휴리스틱 결정론적 경로만 안전).
            chosen = payload.get("variant")
            if chosen is None:
                variants = gp.generate_variants(board, gt, regions=regions)
                idx = int(payload.get("variant_index", -1))
                if not (0 <= idx < len(variants)):
                    print(json.dumps({"ok": False, "error": f"variant_index out of range: {idx}"}))
                    return 1
                chosen = variants[idx]
            chosen.setdefault("gimmick_type", gt)
            fix = gp.auto_fix_variant(grid, chosen, gt, life_map=lm)  # 10배수 자동보정
            merged = gp.apply_variant(board, fix["variant"], gt)  # 병합 → 최종 board
            print(json.dumps({
                "ok": True,
                "chosen": fix["variant"].get("name"),
                "merged": merged,
                "adjustments": fix["adjustments"],
                "designer_needed": fix["designer_needed"],
                "clean": fix["clean"],
                "validation": fix["validation"],
                "preview_b64": gp.render_variant_png(board, fix["variant"], indexing=indexing),
            }))
        else:
            print(json.dumps({"ok": False, "error": f"unknown cmd: {cmd}"}))
            return 1
        return 0
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}",
                          "trace": traceback.format_exc()[-800:]}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
