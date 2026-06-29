"""
Level Grid Generator — 결정성 격자 생성기.

핵심 원칙: LLM은 spec(symmetry, palette, density, seed)만 제공하고,
실제 격자는 이 모듈이 deterministic 알고리즘으로 그린다. → 픽셀 정확도, 대칭, 색상별
10의 배수 카운트가 자동 보장.

대칭 종류별 fundamental domain (한 번만 그리면 나머지가 mirror/rotate로 채워지는 영역):
  - none           : 전체
  - 2-fold-h       : 좌측 절반 (axis 열 1개 비움)
  - 2-fold-v       : 상단 절반 (axis 행 1개 비움)
  - 4-fold         : 좌상 quadrant (axis 행/열 둘 다 비움)
  - diagonal       : upper triangle (대각선 비움)
  - 4-fold-rot     : 좌상 quadrant (회전 중심 1셀 비움)

색상별 카운트 = (fundamental에서 그 색이 차지한 셀 수) × (대칭 expansion factor)
대칭 expansion factor:
  - none:        1
  - 2-fold:      2
  - 4-fold/rot:  4
  - diagonal:    2 (대각선 셀은 1배지만 우리는 대각선을 비우는 정책)

따라서:
  - none:           color count must be multiple of 10  → fund cells per color = 10·N (N≥0)
  - 2-fold:         count = 2·F, want %10==0 → F % 5 == 0  → fund cells per color = 5·N
  - 4-fold/rot:     count = 4·F, want %10==0 → F % 5 == 0  → fund cells per color = 5·N
                    (하지만 expansion이 4배이므로 총 카운트는 20·N)
  - diagonal:       count = 2·F → F % 5 == 0 → fund cells per color = 5·N

구현: fundamental 영역의 셀들을 시드 셔플 → 색상별 quota를 5·N (또는 none이면 10·N) 단위로 떼서
순서대로 채움 → 나머지는 빈셀(-1) → 대칭 변환으로 전체 격자 완성.

사용:
    from level_grid_generator import GridSpec, generate_grid

    spec = GridSpec(
        width=25, height=25,
        symmetry="4-fold",
        palette=[0, 1, 3, 10],     # BalloonFlow color indices
        per_color_count={0: 40, 1: 20, 3: 60, 10: 20},  # 각 색상의 총 셀 수 (10의 배수)
        seed=42,
    )
    cells = generate_grid(spec)
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from level_validator import EMPTY, SYMMETRIES, BALLOONFLOW_PALETTE_MAX

# 대칭별 expansion 배수 (axis/center를 비우는 정책 하)
EXPANSION = {
    "none":        1,
    "2-fold-h":    2,
    "2-fold-v":    2,
    "4-fold":      4,
    "diagonal":    2,
    "4-fold-rot":  4,
}

# 구조 패턴: fundamental domain 셀을 어떤 순서로 정렬할지 결정.
# 정렬된 순서대로 색이 배정되므로 → 의미 있는 형태(동심원/부채꼴/회오리)가 나타남.
# "random"은 옛 동작 (랜덤 셔플 → 대칭 노이즈, 기본 아님).
PATTERNS = {"random", "rings", "rays", "spiral", "diamond", "blocks"}


@dataclass
class GridSpec:
    width: int
    height: int
    symmetry: str
    palette: list[int]               # BalloonFlow color indices, e.g. [0, 1, 3, 10]
    per_color_count: dict[int, int]  # color index → 총 셀 수 (10의 배수)
    seed: int = 0
    name: str = ""                   # 갤러리 표시용 라벨
    pattern: str = "rings"           # 구조 패턴 — 위 PATTERNS 중 하나
    # palette 순서가 의미 있다 — 첫 색이 focal(중심), 마지막이 peripheral(외곽).


@dataclass
class GenerationResult:
    cells: list[list[int]]
    spec: GridSpec
    total_filled: int
    fundamental_cells_filled: int
    notes: list[str] = field(default_factory=list)


def _fundamental_coords(width: int, height: int, symmetry: str) -> list[tuple[int, int]]:
    """대칭 종류에 맞는 fundamental domain 좌표 (axis/center 제외)."""
    if symmetry == "none":
        return [(r, c) for r in range(height) for c in range(width)]
    if symmetry == "2-fold-h":
        # 좌측 절반 (axis 열 c == width//2 제외)
        cx = width // 2
        return [(r, c) for r in range(height) for c in range(cx)]
    if symmetry == "2-fold-v":
        cy = height // 2
        return [(r, c) for r in range(cy) for c in range(width)]
    if symmetry == "4-fold":
        cx, cy = width // 2, height // 2
        return [(r, c) for r in range(cy) for c in range(cx)]
    if symmetry == "diagonal":
        # upper triangle (r < c only — diagonal 자체는 비움)
        if width != height:
            raise ValueError("diagonal symmetry requires square grid")
        n = width
        return [(r, c) for r in range(n) for c in range(r + 1, n)]
    if symmetry == "4-fold-rot":
        if width != height:
            raise ValueError("4-fold-rot requires square grid")
        # 좌상 quadrant (회전 중심 (cy, cx) 제외 — odd면 중심 1셀)
        cx, cy = width // 2, height // 2
        return [(r, c) for r in range(cy) for c in range(cx)]
    raise ValueError(f"unknown symmetry: {symmetry}")


def _expand(
    grid: list[list[int]], r: int, c: int, value: int,
    width: int, height: int, symmetry: str,
) -> None:
    """fundamental 셀 1개 → 대칭 변환된 모든 셀에 같은 값 칠하기."""
    grid[r][c] = value
    if symmetry == "none":
        return
    if symmetry in {"2-fold-h", "4-fold"}:
        grid[r][width - 1 - c] = value
    if symmetry in {"2-fold-v", "4-fold"}:
        grid[height - 1 - r][c] = value
    if symmetry == "4-fold":
        grid[height - 1 - r][width - 1 - c] = value
    if symmetry == "diagonal":
        grid[c][r] = value
    if symmetry == "4-fold-rot":
        # 90°, 180°, 270° 회전
        # (r,c) → (c, h-1-r) → (h-1-r, w-1-c) → (w-1-c, r)
        grid[c][height - 1 - r] = value
        grid[height - 1 - r][width - 1 - c] = value
        grid[width - 1 - c][r] = value


def _sort_fundamental_by_pattern(
    coords: list[tuple[int, int]],
    pattern: str, width: int, height: int, seed: int,
) -> list[tuple[int, int]]:
    """
    fundamental domain 좌표를 pattern에 따라 결정성 정렬.
    같은 (pattern, seed) → 같은 결과.

    배정 규칙: palette 순서대로 fundamental cells에서 chunk를 떼어 색 배정 →
    pattern에 따라 첫 색은 focal(중심/내측/한 부채꼴), 마지막 색은 peripheral.
    """
    if pattern not in PATTERNS:
        raise ValueError(f"unknown pattern: {pattern}")

    cy = (height - 1) / 2.0
    cx = (width - 1) / 2.0

    if pattern == "random":
        rng = random.Random(seed)
        out = list(coords)
        rng.shuffle(out)
        return out

    if pattern == "rings":
        # 거리 기반 (중심 → 외곽). 같은 거리는 (r, c) tiebreak.
        # seed로 inward/outward 토글: 짝수 → 안쪽 먼저, 홀수 → 바깥쪽 먼저
        sign = 1 if (seed % 2 == 0) else -1
        return sorted(
            coords,
            key=lambda rc: (sign * ((rc[0] - cy) ** 2 + (rc[1] - cx) ** 2), rc[0], rc[1]),
        )

    if pattern == "diamond":
        # Manhattan 거리 (마름모형 동심)
        sign = 1 if (seed % 2 == 0) else -1
        return sorted(
            coords,
            key=lambda rc: (sign * (abs(rc[0] - cy) + abs(rc[1] - cx)), rc[0], rc[1]),
        )

    if pattern == "rays":
        # 각도(atan2) 기반 — 4-fold-rot과 잘 어울리는 부채꼴 분할
        # seed로 시작 각도 회전 (다양한 ray 방향)
        offset = (seed % 360) * math.pi / 180.0
        def key(rc: tuple[int, int]) -> tuple[float, float]:
            dy, dx = rc[0] - cy, rc[1] - cx
            angle = math.atan2(dy, dx) + offset
            # 정규화 [0, 2π)
            angle = angle % (2 * math.pi)
            radius = math.sqrt(dy * dy + dx * dx)
            # 같은 각도 안에서는 외곽 먼저 → 부채꼴이 가장자리부터 안으로 채워짐
            return (angle, -radius)
        return sorted(coords, key=key)

    if pattern == "spiral":
        # 거리 + 각도 결합 — 회오리 형태
        # cycles: seed mod 4 + 1 (1~4 turns)
        cycles = (seed % 4) + 1
        max_r = math.sqrt(cy * cy + cx * cx) or 1.0
        def key(rc: tuple[int, int]) -> tuple[float, int, int]:
            dy, dx = rc[0] - cy, rc[1] - cx
            angle = math.atan2(dy, dx) % (2 * math.pi)  # [0, 2π)
            radius = math.sqrt(dy * dy + dx * dx)
            phase = (radius / max_r) * cycles + angle / (2 * math.pi)
            return (phase, rc[0], rc[1])
        return sorted(coords, key=key)

    if pattern == "blocks":
        # NxN 블록 단위로 묶음 — 큰 모자이크
        rng = random.Random(seed)
        block_size = rng.choice([2, 3, 4])
        # 블록 내부 셀들이 인접하도록 (block_index, intra_index) 키 사용
        # 그리고 블록 자체의 순서는 시드 기반으로 결정성 셔플
        block_ids = sorted({(r // block_size, c // block_size) for (r, c) in coords})
        # 블록 ID를 시드로 셔플
        block_order = list(range(len(block_ids)))
        rng.shuffle(block_order)
        block_rank = {block_ids[i]: rank for rank, i in enumerate(block_order)}
        return sorted(
            coords,
            key=lambda rc: (block_rank[(rc[0] // block_size, rc[1] // block_size)], rc[0], rc[1]),
        )

    raise ValueError(f"unhandled pattern: {pattern}")


def _required_fundamental_count(total_count: int, symmetry: str) -> int:
    """총 셀 수 → fundamental 영역에서 칠해야 할 셀 수."""
    expansion = EXPANSION[symmetry]
    if total_count % expansion != 0:
        raise ValueError(
            f"per_color_count {total_count} not divisible by expansion {expansion} for {symmetry}"
        )
    return total_count // expansion


def generate_grid(spec: GridSpec) -> GenerationResult:
    """
    spec → 25x25 (혹은 임의 W×H) 격자. validator가 검증할 모든 invariant 만족.

    실패 케이스:
      - per_color_count가 10의 배수가 아님
      - 대칭에 맞지 않는 카운트 (예: 4-fold인데 20의 배수 아님)
      - palette 외 색이 per_color_count에 있음
      - fundamental cells가 부족 (sum of per_color_count > fundamental capacity)
    """
    if spec.symmetry not in SYMMETRIES:
        raise ValueError(f"unknown symmetry: {spec.symmetry}")

    # palette 검증
    palette_set = set(spec.palette)
    for color in spec.per_color_count.keys():
        if color not in palette_set:
            raise ValueError(f"color {color} not in palette {spec.palette}")
        if not (0 <= color <= BALLOONFLOW_PALETTE_MAX):
            raise ValueError(f"color {color} out of BalloonFlow range 0..{BALLOONFLOW_PALETTE_MAX}")
    # 카운트 검증
    for color, n in spec.per_color_count.items():
        if n < 0:
            raise ValueError(f"color {color}: negative count {n}")
        if n % 10 != 0:
            raise ValueError(f"color {color}: count {n} must be multiple of 10")

    # fundamental 영역
    fund = _fundamental_coords(spec.width, spec.height, spec.symmetry)
    fund_capacity = len(fund)

    # 색상별 fundamental count
    expansion = EXPANSION[spec.symmetry]
    fund_quota: dict[int, int] = {}
    for color, n in spec.per_color_count.items():
        fund_quota[color] = _required_fundamental_count(n, spec.symmetry)
    fund_total = sum(fund_quota.values())
    if fund_total > fund_capacity:
        raise ValueError(
            f"requested {fund_total} fundamental cells but capacity is {fund_capacity} "
            f"({spec.symmetry} on {spec.width}x{spec.height}). "
            f"Reduce per_color_count or pick lower-symmetry."
        )

    # fundamental 정렬 — pattern이 의미 있는 형태(동심원/부채꼴/회오리)를 만든다.
    fund_sorted = _sort_fundamental_by_pattern(
        fund, spec.pattern or "rings", spec.width, spec.height, spec.seed,
    )

    # 색상 순서: spec.palette 순서대로 = 첫 색이 focal(정렬 시작점), 마지막이 peripheral.
    grid = [[EMPTY] * spec.width for _ in range(spec.height)]
    cursor = 0
    for color in spec.palette:
        n = fund_quota.get(color, 0)
        if n == 0:
            continue
        chunk = fund_sorted[cursor : cursor + n]
        cursor += n
        for (r, c) in chunk:
            _expand(grid, r, c, color, spec.width, spec.height, spec.symmetry)

    total_filled = sum(spec.per_color_count.values())
    notes: list[str] = []
    if cursor < fund_capacity:
        empty_fund = fund_capacity - cursor
        notes.append(
            f"{empty_fund}/{fund_capacity} fundamental cells left empty "
            f"(= {empty_fund * expansion} grid cells)"
        )

    return GenerationResult(
        cells=grid, spec=spec,
        total_filled=total_filled,
        fundamental_cells_filled=cursor,
        notes=notes,
    )


def suggest_per_color_count(
    *, width: int, height: int, symmetry: str,
    palette: list[int], total_filled_target: int, seed: int = 0,
) -> dict[int, int]:
    """
    LLM이 직접 per_color_count를 만들기 어려울 때 helper.
    target ≈ total_filled_target에 맞춰 색상별로 균등 분배 (10의 배수 + 대칭 배수).

    반환: {color: count} where 모든 count는 10의 배수, 합 ≤ target, 대칭 expansion 배수.
    """
    if not palette:
        return {}
    expansion = EXPANSION[symmetry]
    # 10의 배수 + expansion의 배수 = lcm(10, expansion) 의 배수
    import math
    unit = math.lcm(10, expansion)
    n_colors = len(palette)
    # 각 색상에 unit씩 할당, target 채울 때까지
    per = max(unit, (total_filled_target // (n_colors * unit)) * unit)
    if per * n_colors > _max_total_filled(width, height, symmetry):
        per = _max_total_filled(width, height, symmetry) // n_colors
        per = (per // unit) * unit  # round down to unit
    rng = random.Random(seed)
    counts = {c: per for c in palette}
    # 남는 여유분을 랜덤 색상에 unit씩 배분
    remaining = total_filled_target - per * n_colors
    while remaining >= unit:
        c = rng.choice(palette)
        # 용량 체크: 이 색을 더 늘리면 fundamental 초과?
        if (counts[c] + unit) // expansion + sum(v // expansion for k, v in counts.items() if k != c) > _fundamental_capacity(width, height, symmetry):
            break
        counts[c] += unit
        remaining -= unit
    return counts


def _fundamental_capacity(width: int, height: int, symmetry: str) -> int:
    return len(_fundamental_coords(width, height, symmetry))


def _max_total_filled(width: int, height: int, symmetry: str) -> int:
    return _fundamental_capacity(width, height, symmetry) * EXPANSION[symmetry]


# ───────── self-test ─────────
if __name__ == "__main__":
    from level_validator import validate_grid, format_report

    test_cases = [
        # (label, spec)  — 모든 pattern을 4-fold-rot 25x25에서 비교
        ("p-rings",   GridSpec(width=25, height=25, symmetry="4-fold-rot",
            palette=[0, 2, 13, 17], per_color_count={0: 40, 2: 60, 13: 60, 17: 40},
            pattern="rings", seed=10)),
        ("p-rays",    GridSpec(width=25, height=25, symmetry="4-fold-rot",
            palette=[0, 2, 13, 17], per_color_count={0: 40, 2: 60, 13: 60, 17: 40},
            pattern="rays", seed=10)),
        ("p-spiral",  GridSpec(width=25, height=25, symmetry="4-fold-rot",
            palette=[0, 2, 13, 17], per_color_count={0: 40, 2: 60, 13: 60, 17: 40},
            pattern="spiral", seed=10)),
        ("p-diamond", GridSpec(width=25, height=25, symmetry="4-fold",
            palette=[0, 2, 13, 17], per_color_count={0: 40, 2: 60, 13: 60, 17: 40},
            pattern="diamond", seed=10)),
        ("p-blocks",  GridSpec(width=25, height=25, symmetry="4-fold",
            palette=[0, 2, 13, 17], per_color_count={0: 40, 2: 60, 13: 60, 17: 40},
            pattern="blocks", seed=10)),
        ("p-random",  GridSpec(width=25, height=25, symmetry="4-fold-rot",
            palette=[0, 2, 13, 17], per_color_count={0: 40, 2: 60, 13: 60, 17: 40},
            pattern="random", seed=10)),
    ]

    all_ok = True
    for label, spec in test_cases:
        print(f"\n=== {label} ({spec.symmetry}, {spec.width}×{spec.height}) ===")
        try:
            result = generate_grid(spec)
        except Exception as e:
            print(f"  GENERATE FAILED: {type(e).__name__}: {e}")
            all_ok = False
            continue
        v = validate_grid(
            result.cells, symmetry=spec.symmetry, palette=spec.palette,
            width=spec.width, height=spec.height,
        )
        print(format_report(v))
        if not v.ok:
            all_ok = False

    # 결정성 테스트: 같은 시드는 같은 결과
    s1 = GridSpec(25, 25, "4-fold", [0, 1], {0: 20, 1: 40}, seed=99)
    a = generate_grid(s1).cells
    b = generate_grid(s1).cells
    assert a == b, "non-deterministic with same seed!"
    print("\n=== determinism check ===")
    print("✅ same seed → same grid")

    # 실패 케이스 — 카운트가 잘못
    print("\n=== error cases ===")
    try:
        generate_grid(GridSpec(25, 25, "4-fold", [0], {0: 30}, seed=0))  # 30 not divisible by 4
        print("✗ should have raised")
        all_ok = False
    except ValueError as e:
        print(f"✓ raised as expected: {e}")

    try:
        generate_grid(GridSpec(25, 25, "none", [0], {0: 35}, seed=0))  # 35 not multiple of 10
        print("✗ should have raised")
        all_ok = False
    except ValueError as e:
        print(f"✓ raised as expected: {e}")

    try:
        generate_grid(GridSpec(10, 10, "4-fold", [0, 1, 2, 3, 4],
                               {c: 20 for c in [0, 1, 2, 3, 4]}, seed=0))
        # 4-fold 10x10 fundamental = 5x5 = 25, 5 colors × 5 = 25 — OK
        print("✓ tight fit accepted")
    except ValueError as e:
        print(f"  unexpected: {e}")

    print(f"\n{'✅ all generator self-tests passed' if all_ok else '❌ some tests failed'}")
