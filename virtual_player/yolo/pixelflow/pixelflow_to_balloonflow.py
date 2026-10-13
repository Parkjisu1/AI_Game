"""PixelFlow 추출 데이터 → BalloonFlow LevelDesign (CSV + JSON).

출력:
  - balloonflow_autogen/BalloonFlow_LevelDesign_auto.csv (전체 보기용)
  - balloonflow_autogen/json/BF_XXX.json (300개, BF의 JSON Importer용)
  - balloonflow_autogen/json/level_XXX.png (이미지 복사, Importer가 자동 참조)
  - balloonflow_autogen/review_notes.md (검수 포인트)

JSON 포맷은 BallonFlow_Git/Assets/Editor/LevelJsonImporterWindow.cs의
JsonLevelData 구조체와 1:1 대응 (snake_case).

매핑 규칙:
  - 직접 복사: 10개 컬럼
  - 자동 계산 (Design Rules 기반): 18개 컬럼
  - 기믹 매핑 (PixelFlow 10종 → BF 13종): 10 직접, 3 (t_spawner, pin, frozen_dart, pinata_box, curtain) 은 0
  - 디자이너 검수 필요: 3개 컬럼 (emotion_curve, designer_note, target_cr 보정)
"""
from __future__ import annotations
import json
import csv
import shutil
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SRC = HERE / "export_1_300" / "levels_1_300.json"
OUT = HERE / "balloonflow_autogen"
OUT_JSON = OUT / "json"
OUT.mkdir(exist_ok=True)
OUT_JSON.mkdir(exist_ok=True)

# PNG 원본 위치 (라벨링 + F 드라이브)
LABELED_IMG_DIR = HERE / "labeling" / "images_levels"
F_SRC_DIR = Path(
    r"F:\LevelDesignExtractor\LevelDesignExtractor_v4.0\LevelDesignExtractor_v4.0\OutPut"
)

# ─────────────────────────────────────────────────────────
# 기믹 매핑 (PixelFlow 키 → BF 컬럼명)
# ─────────────────────────────────────────────────────────
GIMMICK_MAP = {
    "hidden gimik":  "gimmick_hidden",
    "snake gimik":   "gimmick_chain",     # snake = chain 유사 구조
    "pinata gimik":  "gimmick_pinata",
    "key gimik":     "gimmick_lock_key",
    "door gimik":    "gimmick_lock_key",  # door도 lock_key로 통합
    "egg gimik":     "gimmick_surprise",  # egg = surprise balloon
    "wall gimik":    "gimmick_wall",
    "block gimik":   "gimmick_wall",      # block도 wall로 통합
    "ice gimik":     "gimmick_ice",
    "cannon gimik":  "gimmick_spawner_o", # cannon = 불투명 spawner
}

BF_GIMMICK_COLS = [
    "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_spawner_t",
    "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
    "gimmick_spawner_o", "gimmick_pinata_box", "gimmick_ice",
    "gimmick_frozen_dart", "gimmick_curtain",
]

# ─────────────────────────────────────────────────────────
# 계산 헬퍼
# ─────────────────────────────────────────────────────────
def round_to_5(n: int) -> int:
    return ((n + 4) // 5) * 5


def compute_pkg_pos(level_num: int) -> tuple[int, int, int]:
    pkg = (level_num - 1) // 20 + 1
    pos = (level_num - 1) % 20 + 1
    chapter = (pkg - 1) // 5 + 1
    return pkg, pos, chapter


def compute_purpose(pkg: int, pos: int) -> str:
    if pkg == 1 and pos <= 3:
        return "튜토리얼"
    if pos in (4, 9, 14, 19):
        return "하드" if pos <= 14 else "슈퍼하드"
    if pos in (5, 10, 15, 20):
        return "휴식"
    return "일반"


def compute_cr(purpose: str) -> int:
    return {"튜토리얼": 91, "휴식": 85, "일반": 72, "하드": 55, "슈퍼하드": 45}.get(
        purpose, 70
    )


def compute_attempts(purpose: str) -> float:
    return {"튜토리얼": 1.0, "휴식": 1.0, "일반": 2.0, "하드": 3.0, "슈퍼하드": 4.0}.get(
        purpose, 2.0
    )


def compute_rail(total_darts: int) -> tuple[int, str, str]:
    if total_darts <= 300:
        return 50, "~300", "5,10,20"
    if total_darts <= 500:
        return 100, "301~500", "5,10,20,30"
    if total_darts <= 700:
        return 150, "501~700", "5,10,20,30,40"
    return 200, "701+", "5,10,20,30,40,50"


def compute_queue(num_colors: int, purpose: str) -> tuple[int, int]:
    if purpose == "튜토리얼":
        cols = 2
    elif num_colors <= 3:
        cols = 2
    elif num_colors <= 5:
        cols = 3
    elif num_colors <= 7:
        cols = 4
    else:
        cols = 5
    return cols, 6


def compute_emotion(purpose: str) -> str:
    return {
        "튜토리얼": "안심", "휴식": "안심",
        "일반": "몰입", "하드": "긴장", "슈퍼하드": "긴장고조",
    }.get(purpose, "몰입")


BACKGROUND_CODE = "21"  # PixelFlow fieldmap에서 배경 표시 토큰


def parse_fieldmap_to_grid(fieldmap: str) -> list[list[str]]:
    """PixelFlow fieldmap 문자열 → 2D 그리드 (패딩 포함).

    각 행의 토큰 수가 다를 수 있어 최대 컬럼 수로 맞추고 짧은 행은 배경으로 채움.
    """
    if not fieldmap:
        return []
    lines = [line.strip() for line in fieldmap.split("\n") if line.strip()]
    if not lines:
        return []
    grid = [line.split() for line in lines]
    max_cols = max(len(row) for row in grid)
    for row in grid:
        while len(row) < max_cols:
            row.append(BACKGROUND_CODE)
    return grid


def trim_background(grid: list[list[str]]) -> tuple[list[list[str]], int, int]:
    """그리드에서 배경만 있는 외곽 행/열 제거. 반환: (trimmed, left_offset, top_offset)."""
    if not grid:
        return grid, 0, 0
    rows = len(grid)
    cols = len(grid[0])

    # 상/하 경계
    top = 0
    while top < rows and all(c == BACKGROUND_CODE for c in grid[top]):
        top += 1
    bottom = rows - 1
    while bottom >= top and all(c == BACKGROUND_CODE for c in grid[bottom]):
        bottom -= 1
    # 좌/우 경계
    left = 0
    while left < cols and all(grid[r][left] == BACKGROUND_CODE for r in range(top, bottom + 1)):
        left += 1
    right = cols - 1
    while right >= left and all(grid[r][right] == BACKGROUND_CODE for r in range(top, bottom + 1)):
        right -= 1

    if bottom < top or right < left:
        return [], 0, 0  # 전부 배경

    trimmed = [grid[r][left:right + 1] for r in range(top, bottom + 1)]
    return trimmed, left, top


def grid_to_bf_fieldmap(grid: list[list[str]]) -> str:
    """PixelFlow 그리드 → BF [FieldMap] 텍스트.

    - 배경 "21" → ".."
    - 색상 코드 (03, 04, 28 등) → 정수 그대로 (1-based)
    """
    lines = []
    for row in grid:
        tokens = [".." if v == BACKGROUND_CODE else v for v in row]
        lines.append(" ".join(tokens))
    return "\n".join(lines)


def count_cells_in_grid(grid: list[list[str]]) -> int:
    return sum(1 for row in grid for v in row if v != BACKGROUND_CODE)


def colors_in_grid(grid: list[list[str]]) -> dict[str, int]:
    from collections import Counter
    c = Counter()
    for row in grid:
        for v in row:
            if v != BACKGROUND_CODE:
                c[v] += 1
    return dict(c)


def analyze_composition(fieldmap: str, rows: int, cols: int) -> str:
    """그리드 기반 구성 분석 (좌우대칭 / 상하대칭 / 4방향대칭 / 비대칭)."""
    grid = parse_fieldmap_to_grid(fieldmap)
    grid, _, _ = trim_background(grid)
    if not grid or len(grid) < 3 or len(grid[0]) < 3:
        return "미분석"
    try:
        lr_sym = all(row == list(reversed(row)) for row in grid)
        ud_sym = grid == list(reversed(grid))
        if lr_sym and ud_sym:
            return "4방향대칭"
        if lr_sym:
            return "좌우대칭"
        if ud_sym:
            return "상하대칭"
        return "비대칭"
    except Exception:
        return "미분석"


def color_distribution_to_bf(cd: str, total_cells: int, num_colors: int) -> str:
    """PixelFlow 팔레트 색 → BF 색 번호로 리매핑 (많은 순 → c1, c2, ...).

    각 색상 수는 5의 배수로 반올림.
    """
    if not cd:
        return ""
    pairs = []
    for part in cd.split():
        if ":" in part:
            col, cnt = part.split(":")
            try:
                pairs.append((col, int(cnt)))
            except ValueError:
                pass
    pairs.sort(key=lambda x: -x[1])
    pairs = pairs[:num_colors] if num_colors > 0 else pairs
    adjusted = [round_to_5(cnt) for _, cnt in pairs]
    return ",".join(f"c{i+1}:{adjusted[i]}" for i in range(len(adjusted)))


def map_gimmicks(gimmick_positions: list) -> dict[str, int]:
    counts = {col: 0 for col in BF_GIMMICK_COLS}
    for g in gimmick_positions:
        if not isinstance(g, dict):
            continue
        gtype = g.get("type")
        bf_col = GIMMICK_MAP.get(gtype)
        if bf_col and bf_col in counts:
            counts[bf_col] += 1
    return counts


def copy_png(level_num: int, dst_dir: Path) -> str:
    """PixelFlow 원본 PNG를 dst에 복사. 반환: 복사된 파일명."""
    fname = f"level_{level_num:03d}.png"
    # 우선순위: labeled (E:\AI) → F:\ OutPut
    for src_dir in [LABELED_IMG_DIR, F_SRC_DIR]:
        src = src_dir / fname
        if src.exists():
            dst = dst_dir / fname
            if not dst.exists():
                shutil.copy2(src, dst)
            return fname
    return fname  # 못 찾아도 이름은 반환 (BF importer가 경고 출력)


# ─────────────────────────────────────────────────────────
# 메인 변환
# ─────────────────────────────────────────────────────────
def convert():
    records = json.loads(SRC.read_text(encoding="utf-8"))
    print(f"Loaded {len(records)} levels from {SRC.name}")

    bf_headers = [
        "level_number", "level_id", "pkg", "pos", "chapter",
        "purpose_type", "target_cr", "target_attempts",
        "num_colors", "color_distribution",
        "field_rows", "field_columns", "total_cells",
        "rail_capacity", "rail_capacity_tier",
        "queue_columns", "queue_rows",
    ] + BF_GIMMICK_COLS + [
        "total_darts", "dart_capacity_range",
        "emotion_curve", "designer_note", "pixel_art_source",
    ]

    csv_rows = []
    json_count = 0
    png_copied = 0
    png_missing = []
    review_notes = []

    for d in records:
        n = d.get("level_number", 0)
        pkg, pos, chap = compute_pkg_pos(n)
        purpose = compute_purpose(pkg, pos)
        cr = compute_cr(purpose)
        attempts = compute_attempts(purpose)

        # === YOLO 추출 fieldmap을 BF FieldMap으로 변환 (핵심) ===
        raw_grid = parse_fieldmap_to_grid(d.get("fieldmap", ""))
        trimmed_grid, _, _ = trim_background(raw_grid)
        if trimmed_grid:
            field_rows = len(trimmed_grid)
            field_cols = len(trimmed_grid[0])
            total_cells = count_cells_in_grid(trimmed_grid)
            color_counts = colors_in_grid(trimmed_grid)
            num_colors = len(color_counts)
            bf_fieldmap = grid_to_bf_fieldmap(trimmed_grid)
        else:
            # fieldmap 없거나 전부 배경 → JSON 메타 데이터 fallback
            field_rows = d.get("field_rows", 0)
            field_cols = d.get("field_columns", 0)
            total_cells = d.get("total_cells_yolo", 0)
            num_colors = d.get("num_colors", 0)
            bf_fieldmap = ""

        gim_positions = d.get("gimmick_positions", [])
        gim_counts = map_gimmicks(gim_positions)
        gim_total = sum(gim_counts.values())

        # total_darts: 기믹 1개당 라이프 평균 2 가정
        darts = round_to_5(total_cells + gim_total * 2)
        darts = max(darts, 150)

        rail, tier, cap_range = compute_rail(darts)
        qcols, _ = compute_queue(num_colors, purpose)
        qrows = max(6, total_cells // max(1, qcols * 10))

        # color_distribution: fieldmap에서 직접 계산한 실제 셀 수
        # (FieldMap과 총합 일치시키기 위해 반올림 X — Design Rule 위반은 디자이너 조정)
        if trimmed_grid:
            cd_bf = ",".join(
                f"c{int(code)}:{cnt}"
                for code, cnt in sorted(color_counts.items(), key=lambda x: -x[1])
            )
        else:
            cd_bf = color_distribution_to_bf(
                d.get("color_distribution", ""), total_cells, num_colors
            )

        comp = analyze_composition(d.get("fieldmap", ""), field_rows, field_cols)
        note_parts = [f"[Composition] {comp}", "[Shape] 미정", f"[Pattern] C{num_colors}색 미정"]
        if gim_total > 0:
            gim_types = [k.replace("gimmick_", "") for k, v in gim_counts.items() if v > 0]
            note_parts.append(f"[Gimmick] {','.join(gim_types)}")
        else:
            note_parts.append("[Gimmick] 없음")
        note_parts.append("[Empty] 미분석")
        # ★ [FieldMap] 섹션 추가 — BF 임포터가 이걸 직접 파싱
        if bf_fieldmap:
            note_parts.append("[FieldMap]\n" + bf_fieldmap)
        note = " ".join(note_parts[:-1] if bf_fieldmap else note_parts) + \
               ("\n" + note_parts[-1] if bf_fieldmap else "")

        emotion = compute_emotion(purpose)

        # PNG 복사
        png_name = copy_png(n, OUT_JSON)
        src_png = (LABELED_IMG_DIR / png_name) if (LABELED_IMG_DIR / png_name).exists() \
                  else (F_SRC_DIR / png_name)
        if src_png.exists():
            png_copied += 1
        else:
            png_missing.append(n)

        # BF JSON 레코드 (struct와 1:1)
        bf_record = {
            "level_number": n,
            "level_id": f"BF_{n:03d}",
            "pkg": pkg, "pos": pos, "chapter": chap,
            "purpose_type": purpose,
            "target_cr": cr,
            "target_attempts": attempts,
            "num_colors": num_colors,
            "color_distribution": cd_bf,
            "field_rows": field_rows,
            "field_columns": field_cols,
            "total_cells": total_cells,
            "rail_capacity": rail,
            "rail_capacity_tier": tier,
            "queue_columns": qcols,
            "queue_rows": qrows,
            **gim_counts,
            "total_darts": darts,
            "dart_capacity_range": cap_range,
            "emotion_curve": emotion,
            "designer_note": note,
            "pixel_art_source": png_name,
        }

        # 개별 JSON 파일 저장
        json_path = OUT_JSON / f"BF_{n:03d}.json"
        json_path.write_text(
            json.dumps(bf_record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        json_count += 1

        csv_rows.append(bf_record)

        if comp == "미분석":
            review_notes.append(f"L{n}: composition 미분석")
        if gim_total > 5:
            review_notes.append(f"L{n}: 기믹 종류 {gim_total}개 (5종 Hard 초과)")

    # CSV (요약용)
    csv_path = OUT / "BalloonFlow_LevelDesign_auto.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=bf_headers)
        w.writeheader()
        w.writerows(csv_rows)

    # 검수 노트
    notes_md = OUT / "review_notes.md"
    with notes_md.open("w", encoding="utf-8") as f:
        f.write("# BalloonFlow Auto-Generated — Review Notes\n\n")
        f.write(f"**Source**: {SRC.name} (300 levels)\n\n")
        f.write("## 출력 파일\n")
        f.write(f"- `BalloonFlow_LevelDesign_auto.csv` — 전체 보기용 (Excel 호환)\n")
        f.write(f"- `json/BF_XXX.json` — BF의 JSON Importer용 (300개)\n")
        f.write(f"- `json/level_XXX.png` — BF Importer가 자동 참조하는 이미지 (300개)\n\n")
        f.write("## BalloonFlow에서 Import 방법\n")
        f.write("1. Unity 에디터에서 **BalloonFlow > Import Level Data From JSON** 메뉴\n")
        f.write("2. **폴더 추가...** 버튼 클릭\n")
        f.write(f"3. `{OUT_JSON}` 폴더 선택\n")
        f.write("4. 저장 대상 선택 (Origin / AI Extractor / Transform Extractor)\n")
        f.write("5. **...에 추가** 버튼으로 LevelDatabase.asset에 반영\n\n")
        f.write("## 이미지 처리\n")
        f.write("- BF 임포터가 `pixel_art_source` 필드로 같은 폴더 PNG 자동 탐색\n")
        f.write("- JSON과 PNG가 함께 있어야 정확한 풍선 배치 (픽셀→BF 28색 매핑)\n\n")
        f.write("## 디자이너 검수 필요\n")
        f.write("- **designer_note**: [Composition] 자동 추정됨, [Shape]/[Pattern]/[Empty] 수동\n")
        f.write("- **emotion_curve**: purpose 기반 기본값, 필요 시 조정\n")
        f.write("- **color_distribution**: 5 배수 근사 (total_cells 약간 차이 가능)\n")
        f.write("- **target_cr/attempts**: purpose별 기본값, 테스트 후 조정\n")
        f.write("- **gimmick_spawner_t/pin/frozen_dart/pinata_box/curtain**: 전부 0 (PixelFlow에 없음)\n\n")
        f.write(f"## 이슈 {len(review_notes)}건\n")
        for ln in review_notes[:50]:
            f.write(f"- {ln}\n")

    print(f"\n=== 완료 ===")
    print(f"JSON 파일: {json_count}개 → {OUT_JSON}/")
    print(f"PNG 복사: {png_copied}개")
    if png_missing:
        print(f"PNG 누락: {len(png_missing)} (예: {png_missing[:5]})")
    print(f"CSV: {csv_path.name}")
    print(f"검수 노트: {notes_md.name}")

    # 집계
    purposes: dict[str, int] = {}
    for r in csv_rows:
        purposes[r["purpose_type"]] = purposes.get(r["purpose_type"], 0) + 1
    print(f"\n=== 요약 ===")
    for p, c in purposes.items():
        print(f"  {p}: {c} 레벨")
    print(f"  기믹 총합: {sum(sum(r[g] for g in BF_GIMMICK_COLS) for r in csv_rows)}")
    print(f"  검수 플래그: {len(review_notes)}")


if __name__ == "__main__":
    convert()
