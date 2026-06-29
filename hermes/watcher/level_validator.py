"""
Level Grid Validator — 결정성 검증.

design_level_designer가 만든 grid이 다음 조건을 만족하는지 LLM 없이 검사:
  1. symmetry — 명시한 대칭이 모든 셀에서 깨지지 않는다
  2. palette — 사용된 색 인덱스가 모두 spec.palette 안에 있다 (BalloonFlow 24색 범주 내)
  3. count_mod_10 — 색상별 셀 카운트가 10의 배수
  4. dimensions — width × height가 cells 길이와 일치, 모든 행 길이 동일
  5. axis_clear (옵션) — 4-fold/4-fold-rotate 대칭은 axis/center 비어있어야 함

빈 셀은 -1로 표현 (BalloonFlow color index와 충돌 회피).

사용:
    from level_validator import validate_grid, ValidationResult

    result = validate_grid(cells, symmetry="2-fold-h", palette=[0, 1, 3, 10])
    if not result.ok:
        print(result.errors)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

EMPTY = -1

# 지원 대칭 종류
SYMMETRIES = {
    "none",          # 무대칭
    "2-fold-h",      # 좌우 대칭 (vertical axis)
    "2-fold-v",      # 상하 대칭 (horizontal axis)
    "4-fold",        # 좌우+상하 (D2 group)
    "diagonal",      # 주대각선 대칭 (transpose)
    "4-fold-rot",    # 90° 회전 대칭 (radial 만화경)
}

# BalloonFlow 색상 인덱스 범위 (BalloonController.BalloonColors[0..23])
BALLOONFLOW_PALETTE_MAX = 23


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    color_counts: dict[int, int] = field(default_factory=dict)
    filled_cells: int = 0
    empty_cells: int = 0


def _check_dimensions(cells: list[list[int]], width: int, height: int) -> list[str]:
    errs: list[str] = []
    if len(cells) != height:
        errs.append(f"height mismatch: cells has {len(cells)} rows, spec says {height}")
        return errs
    for r, row in enumerate(cells):
        if len(row) != width:
            errs.append(f"row {r} width = {len(row)}, expected {width}")
    return errs


def _check_palette(
    cells: list[list[int]], palette: Iterable[int],
) -> tuple[list[str], dict[int, int]]:
    errs: list[str] = []
    palette_set = set(palette)
    counts: dict[int, int] = {}
    for r, row in enumerate(cells):
        for c, v in enumerate(row):
            if v == EMPTY:
                continue
            if not isinstance(v, int) or v < 0 or v > BALLOONFLOW_PALETTE_MAX:
                errs.append(f"cell ({r},{c}) = {v} — out of BalloonFlow range 0..{BALLOONFLOW_PALETTE_MAX}")
                continue
            if v not in palette_set:
                errs.append(f"cell ({r},{c}) = color {v} not in declared palette {sorted(palette_set)}")
                continue
            counts[v] = counts.get(v, 0) + 1
    return errs, counts


def _check_count_mod_10(counts: dict[int, int]) -> list[str]:
    errs: list[str] = []
    for color, n in counts.items():
        if n % 10 != 0:
            errs.append(f"color {color}: count={n} is not a multiple of 10")
    return errs


def _check_symmetry(cells: list[list[int]], symmetry: str) -> list[str]:
    if symmetry == "none":
        return []
    errs: list[str] = []
    h = len(cells)
    w = len(cells[0]) if cells else 0

    def _eq(a: int, b: int) -> bool:
        return a == b

    if symmetry == "2-fold-h":
        # 좌우 대칭: cells[r][c] == cells[r][w-1-c]
        for r in range(h):
            for c in range(w // 2):
                if not _eq(cells[r][c], cells[r][w - 1 - c]):
                    errs.append(f"2-fold-h broken at ({r},{c}) <> ({r},{w - 1 - c})")
    elif symmetry == "2-fold-v":
        # 상하 대칭: cells[r][c] == cells[h-1-r][c]
        for r in range(h // 2):
            for c in range(w):
                if not _eq(cells[r][c], cells[h - 1 - r][c]):
                    errs.append(f"2-fold-v broken at ({r},{c}) <> ({h - 1 - r},{c})")
    elif symmetry == "4-fold":
        # 좌우 + 상하 둘 다
        for r in range(h):
            for c in range(w):
                v = cells[r][c]
                if not _eq(v, cells[r][w - 1 - c]):
                    errs.append(f"4-fold (h) broken at ({r},{c})")
                    break
                if not _eq(v, cells[h - 1 - r][c]):
                    errs.append(f"4-fold (v) broken at ({r},{c})")
                    break
    elif symmetry == "diagonal":
        if h != w:
            errs.append(f"diagonal symmetry requires square grid, got {h}x{w}")
        else:
            for r in range(h):
                for c in range(r + 1, w):
                    if not _eq(cells[r][c], cells[c][r]):
                        errs.append(f"diagonal broken at ({r},{c}) <> ({c},{r})")
    elif symmetry == "4-fold-rot":
        # 90° 회전 대칭: cells[r][c] == cells[c][h-1-r] (정사각 가정)
        if h != w:
            errs.append(f"4-fold-rot symmetry requires square grid, got {h}x{w}")
        else:
            for r in range(h):
                for c in range(w):
                    rotated = cells[c][h - 1 - r]
                    if not _eq(cells[r][c], rotated):
                        errs.append(f"4-fold-rot broken at ({r},{c}) <> ({c},{h - 1 - r})")
                        break
                if errs and "4-fold-rot" in errs[-1]:
                    break
    else:
        errs.append(f"unknown symmetry: {symmetry}")

    # 첫 5개만 보고하고 그 뒤는 요약 (스팸 방지)
    if len(errs) > 5:
        kept = errs[:5]
        kept.append(f"... and {len(errs) - 5} more symmetry violations")
        return kept
    return errs


def _check_axis_clear(
    cells: list[list[int]], symmetry: str,
) -> list[str]:
    """
    4-fold / 4-fold-rot 대칭은 axis/center를 비워두는 정책 (color 카운트가
    10의 배수 보장을 위해). axis는 odd 그리드의 중앙 행/열.
    """
    if symmetry not in {"4-fold", "4-fold-rot"}:
        return []
    h = len(cells)
    w = len(cells[0]) if cells else 0
    if h % 2 == 0 or w % 2 == 0:
        return []
    cr, cc = h // 2, w // 2
    errs: list[str] = []
    if symmetry == "4-fold":
        # 중앙 행 + 중앙 열 비어야 함
        for c in range(w):
            if cells[cr][c] != EMPTY:
                errs.append(f"axis-clear violated: cells[{cr}][{c}] = {cells[cr][c]}")
                break
        for r in range(h):
            if cells[r][cc] != EMPTY:
                errs.append(f"axis-clear violated: cells[{r}][{cc}] = {cells[r][cc]}")
                break
    elif symmetry == "4-fold-rot":
        # 중심 1셀만 비어야 함 (회전축)
        if cells[cr][cc] != EMPTY:
            errs.append(f"axis-clear violated: center cells[{cr}][{cc}] = {cells[cr][cc]}")
    return errs


def validate_grid(
    cells: list[list[int]],
    *,
    symmetry: str,
    palette: Iterable[int],
    width: int | None = None,
    height: int | None = None,
    enforce_axis_clear: bool = True,
) -> ValidationResult:
    """
    grid + spec → 위반 목록. ok=True 이면 모든 검사 통과.
    """
    if symmetry not in SYMMETRIES:
        return ValidationResult(ok=False, errors=[f"unknown symmetry: {symmetry}"])
    if not cells or not cells[0]:
        return ValidationResult(ok=False, errors=["empty grid"])

    h = len(cells)
    w = len(cells[0])
    if width is None:
        width = w
    if height is None:
        height = h

    errs: list[str] = []
    errs += _check_dimensions(cells, width, height)
    if errs:
        # 차원이 깨지면 다른 검사 의미 없음
        return ValidationResult(ok=False, errors=errs)

    palette_errs, counts = _check_palette(cells, palette)
    errs += palette_errs
    errs += _check_count_mod_10(counts)
    errs += _check_symmetry(cells, symmetry)
    if enforce_axis_clear:
        errs += _check_axis_clear(cells, symmetry)

    filled = sum(counts.values())
    empty = w * h - filled

    return ValidationResult(
        ok=(len(errs) == 0),
        errors=errs,
        color_counts=counts,
        filled_cells=filled,
        empty_cells=empty,
    )


def format_report(result: ValidationResult) -> str:
    """사람 읽기 쉬운 검증 리포트."""
    lines = []
    if result.ok:
        lines.append("✅ Grid validation PASSED")
    else:
        lines.append(f"❌ Grid validation FAILED ({len(result.errors)} error(s))")
    lines.append(f"   filled={result.filled_cells}, empty={result.empty_cells}")
    if result.color_counts:
        cc = ", ".join(
            f"c{k}={v}" for k, v in sorted(result.color_counts.items())
        )
        lines.append(f"   color counts: {cc}")
    for e in result.errors[:10]:
        lines.append(f"   ✗ {e}")
    if len(result.errors) > 10:
        lines.append(f"   ... and {len(result.errors) - 10} more")
    for w in result.warnings[:5]:
        lines.append(f"   ⚠ {w}")
    return "\n".join(lines)


# ───────── self-test ─────────
if __name__ == "__main__":
    # 간단한 5x5 grid로 sanity check
    g_ok = [
        [-1, -1, -1, -1, -1],
        [-1,  0,  1,  0, -1],
        [-1,  1,  2,  1, -1],
        [-1,  0,  1,  0, -1],
        [-1, -1, -1, -1, -1],
    ]
    # color 0 = 4, color 1 = 4, color 2 = 1 — 10의 배수가 아님 → fail
    r = validate_grid(g_ok, symmetry="4-fold", palette=[0, 1, 2])
    print("[test1: 4-fold + counts NOT multiple of 10]")
    print(format_report(r))
    assert not r.ok and any("multiple of 10" in e for e in r.errors)

    # 정상 케이스: 모든 색 0
    g_empty = [[-1]*5 for _ in range(5)]
    r = validate_grid(g_empty, symmetry="4-fold", palette=[0, 1])
    print("\n[test2: empty grid]")
    print(format_report(r))
    assert r.ok

    # 비대칭 검출
    g_broken = [[0, 1, 2, 3, 4]] + [[-1]*5 for _ in range(4)]
    r = validate_grid(g_broken, symmetry="2-fold-h", palette=[0, 1, 2, 3, 4])
    print("\n[test3: broken 2-fold-h]")
    print(format_report(r))
    assert not r.ok and any("2-fold-h broken" in e for e in r.errors)

    print("\n✅ validator self-test passed")
