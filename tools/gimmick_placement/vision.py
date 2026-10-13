"""
STEP 0 — AI Vision 영역 분석 (선택적 모듈).
보드 PNG → gpt-4o(vision) → 의미 영역(head/body/limbs/empty) JSON.
실패/저신뢰 시 None 반환 → 호출측이 휴리스틱 detect_regions로 fallback (= 명세 fallback).

코어(gimmick_placement.py)는 stdlib만 의존; 본 모듈만 openai/dotenv 의존 (lazy import).
"""
from __future__ import annotations

import json
import os
from collections import Counter

import gimmick_placement as gp

# STEP 0 표준 프롬프트 (명세 §STEP 0)
VISION_PROMPT = """이 픽셀아트 이미지를 분석해주세요. 게임 레벨 디자인 분석입니다.
보드 크기: {W}×{H} (셀 단위). 좌표 원점 = 좌하단(게임 좌표계), x→오른쪽, y→위.

다음 정보를 JSON으로만 출력:
{{
  "category": "Animal|Object|Nature|Character|Abstract|Food|Holiday|Symbol|Geometric|Art",
  "metaphor": "구체 메타포 (예: 고무오리, 토끼 얼굴)",
  "motif_bbox": [x_min, y_min, x_max, y_max],
  "motif_main_colors": [palette_idx, ...],
  "background_color": palette_idx,
  "regions": {{
    "head": {{"bbox": [x0,y0,x1,y1], "exists": true|false}},
    "body": {{"bbox": [x0,y0,x1,y1], "exists": true|false}},
    "limbs_left": {{"bbox": [x0,y0,x1,y1], "exists": true|false}},
    "limbs_right": {{"bbox": [x0,y0,x1,y1], "exists": true|false}},
    "accessories_top": {{"bbox": [x0,y0,x1,y1], "exists": true|false}}
  }},
  "empty_regions": [
    {{"side": "top|bottom|left|right|corner_TL|corner_TR|corner_BL|corner_BR", "bbox": [x0,y0,x1,y1]}}
  ],
  "metaphor_complexity": "simple|moderate|detailed"
}}
주의: bbox는 [x_min,y_min,x_max,y_max], 보드 좌표계(0~{W}-1, 0~{H}-1). palette_idx는 1~28. exists=false는 해당 부위 없음."""


def analyze_board_vision(board: dict, model: str = "gpt-4o", indexing: str = "auto",
                         timeout: float = 60.0, env_path: str = "/home/aimed/.hermes/watcher/.env") -> dict | None:
    """보드 → vision JSON. 실패 시 None."""
    try:
        from openai import OpenAI
        try:
            from dotenv import load_dotenv
            if env_path and os.path.exists(env_path):
                load_dotenv(env_path)
        except Exception:  # noqa: BLE001
            pass
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return None
        if indexing == "auto":
            cols = [b["color"] for b in board.get("balloons", [])]
            indexing = "bl" if (cols and min(cols) == 0) else "pf"
        base_png = gp.render_variant_png(
            board, {"name": "", "instances": [], "validation": None},
            cell=12, flip_y=True, indexing=indexing)
        W, H = board["field_columns"], board["field_rows"]
        client = OpenAI(api_key=api_key, timeout=timeout, max_retries=2)
        messages = [{"role": "user", "content": [
            {"type": "text", "text": VISION_PROMPT.format(W=W, H=H)},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base_png}"}},
        ]}]
        content = None
        for _ in range(3):  # gpt-4o가 간헐적으로 빈 content 반환 → 재시도
            resp = client.chat.completions.create(
                model=model, messages=messages,
                response_format={"type": "json_object"}, max_tokens=1500,
            )
            content = resp.choices[0].message.content
            if content:
                break
        if not content:
            return {"_vision_error": "empty content after retries"}
        return json.loads(content)
    except Exception as e:  # noqa: BLE001
        return {"_vision_error": f"{type(e).__name__}: {e}"}


def _bbox_cells(bbox, nonbg, flip, H):
    x0, y0, x1, y1 = bbox
    if x0 > x1:
        x0, x1 = x1, x0
    if y0 > y1:
        y0, y1 = y1, y0
    out = set()
    for (x, y) in nonbg:
        yy = (H - 1 - y) if flip else y
        if x0 <= x <= x1 and y0 <= yy <= y1:
            out.add((x, y))
    return out


def resolve_regions_from_vision(vision: dict, board: dict) -> list[dict]:
    """
    vision 응답 → 휴리스틱 detect_regions 와 동일 형식의 region 리스트 (+ 'label').
    좌상단/좌하단 좌표 불일치는 motif_bbox 교차가 많은 쪽으로 자동 정합.
    매핑 실패(저신뢰) 시 빈 리스트 → 호출측 fallback.
    """
    if not vision or vision.get("_vision_error"):
        return []
    grid, W, H, bg = gp.board_to_grid(board)
    nonbg = {(x, y) for (x, y), c in grid.items() if c != bg}
    if not nonbg:
        return []

    # 방향 정합: motif_bbox 를 양쪽으로 시도 → 교차 많은 쪽
    mb = vision.get("motif_bbox")
    flip = False
    if isinstance(mb, list) and len(mb) == 4:
        as_is = len(_bbox_cells(mb, nonbg, False, H))
        flipped = len(_bbox_cells(mb, nonbg, True, H))
        flip = flipped > as_is

    regions: list[dict] = []
    rdict = vision.get("regions", {}) or {}
    for label in ["body", "head", "limbs_left", "limbs_right", "accessories_top"]:
        r = rdict.get(label)
        if not (isinstance(r, dict) and r.get("exists") and isinstance(r.get("bbox"), list)):
            continue
        cells = _bbox_cells(r["bbox"], nonbg, flip, H)
        if len(cells) >= 6:
            col = Counter(grid[c] for c in cells).most_common(1)[0][0]
            reg = gp._region_of(cells, col)
            reg["label"] = "motif_" + label
            regions.append(reg)

    # empty_regions (frame) — 빈 셀 기반 (배치 collateral 회피용)
    allcells = set(grid.keys())
    emptyset = {(x, y) for x in range(W) for y in range(H)} - allcells
    for er in (vision.get("empty_regions") or []):
        bb = er.get("bbox")
        if not (isinstance(bb, list) and len(bb) == 4):
            continue
        x0, y0, x1, y1 = bb
        cells = {(x, y) for (x, y) in emptyset
                 if min(x0, x1) <= x <= max(x0, x1) and min(y0, y1) <= ((H - 1 - y) if flip else y) <= max(y0, y1)}
        if len(cells) >= 6:
            reg = gp._region_of(cells, bg)
            reg["label"] = "frame_" + str(er.get("side", "?"))
            reg["is_empty"] = True
            regions.append(reg)

    return regions
