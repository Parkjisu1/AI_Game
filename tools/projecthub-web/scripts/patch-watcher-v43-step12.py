#!/usr/bin/env python3
"""Patch field_complete_levels.py with v43-inspired Step 1+2:
  Step 1: cluster_dist metric in field_analysis (objective visual measurement)
  Step 2: visual_quality score dim (noise + balance) — multi-seed picker reward
"""
import sys

PATH = "/home/aimed/.hermes/watcher/field_complete_levels.py"

# 1) Update SCORE_WEIGHTS
OLD_WEIGHTS = '''# Score 가중치 — v1.2.3 (Soft Rule 추가 dimension)
SCORE_WEIGHTS = {
    "metaphor_score":     0.45,  # 메타포 보존 (visual quality 핵심)
    "mod10_compliance":   0.18,  # 자동 정합
    "hard_rule_pass":     0.12,  # debut/Lock&Key/Glass↔Pipe + placement violations
    "debut_compliance":   0.08,  # intro 격리
    "queue_alignment":    0.05,  # 큐 다트 범위 (warning만)
    "hp_visual_gap":      0.07,  # 셀% vs HP% gap (§12 라인 1275-1283)
    "soft_rule_pass":     0.05,  # 60-lv reappearance, hp_visual_gap_warnings (§11.2)
}'''

NEW_WEIGHTS = '''# Score 가중치 — v1.2.4 (v43 시각 품질 dimension 통합)
SCORE_WEIGHTS = {
    "metaphor_score":     0.35,  # 메타포 보존 (visual quality 핵심) — v43 통합으로 0.45→0.35
    "visual_quality":     0.12,  # NEW (v43): noise(고립셀) + balance(색상 균형)
    "mod10_compliance":   0.18,  # 자동 정합
    "hard_rule_pass":     0.10,  # debut/Lock&Key/Glass↔Pipe + placement violations (0.12→0.10)
    "debut_compliance":   0.08,  # intro 격리
    "queue_alignment":    0.05,  # 큐 다트 범위 (warning만)
    "hp_visual_gap":      0.07,  # 셀% vs HP% gap (§12 라인 1275-1283)
    "soft_rule_pass":     0.05,  # 60-lv reappearance, hp_visual_gap_warnings (§11.2)
}'''

# 2) Insert helper functions before compute_score (line 2052)
HELPERS = '''def compute_cluster_distribution(field_map: list[list[int]]) -> dict:
    """v43 §평가: 같은 색 연결 영역 → 크기 버킷별 비율.

    PixelFlow 비교용 객관 지표. 클래스:
      le3_pct: 1-3셀 짜잘이 클러스터 (노이즈 영역)
      f4to10_pct: 작은 클러스터
      f11to30_pct: 중간 클러스터
      gt30_pct: 큰 메인 형태
    """
    if not field_map or not field_map[0]:
        return {"le3_pct": 0, "f4to10_pct": 0, "f11to30_pct": 0, "gt30_pct": 0,
                "cluster_count": 0, "max_cluster_size": 0}
    H = len(field_map)
    W = len(field_map[0])
    visited = [[False] * W for _ in range(H)]
    cluster_sizes: list[int] = []
    for y in range(H):
        for x in range(W):
            if visited[y][x] or not field_map[y][x]:
                continue
            color = field_map[y][x]
            queue = deque([(y, x)])
            visited[y][x] = True
            sz = 0
            while queue:
                cy, cx = queue.popleft()
                sz += 1
                for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < H and 0 <= nx < W and not visited[ny][nx] and field_map[ny][nx] == color:
                        visited[ny][nx] = True
                        queue.append((ny, nx))
            cluster_sizes.append(sz)
    total = sum(cluster_sizes) or 1
    le3 = sum(s for s in cluster_sizes if s <= 3) * 100 / total
    f4_10 = sum(s for s in cluster_sizes if 4 <= s <= 10) * 100 / total
    f11_30 = sum(s for s in cluster_sizes if 11 <= s <= 30) * 100 / total
    gt30 = sum(s for s in cluster_sizes if s > 30) * 100 / total
    return {
        "le3_pct": round(le3, 1),
        "f4to10_pct": round(f4_10, 1),
        "f11to30_pct": round(f11_30, 1),
        "gt30_pct": round(gt30, 1),
        "cluster_count": len(cluster_sizes),
        "max_cluster_size": max(cluster_sizes) if cluster_sizes else 0,
    }


def compute_visual_quality(field_map: list[list[int]]) -> dict:
    """v43 §평가: noise_score(고립셀) + balance_score(색상 분포 균형).

    noise_score: 4방향 이웃 중 같은 색 0개인 셀 비율. PixelFlow 기준 ~12% 허용.
    balance_score: 색상별 셀수의 분산 — 낮을수록 골고루 분포.

    contrast_score 는 색상 hex 입력 필요해서 STEP 3 단계로 이연.
    """
    if not field_map or not field_map[0]:
        return {"noise_score": 0.0, "balance_score": 0.0, "visual_quality": 0.0}
    H = len(field_map)
    W = len(field_map[0])
    noise = 0
    total_checked = 0
    color_counts: Counter = Counter()
    for y in range(H):
        for x in range(W):
            c = field_map[y][x]
            if not c:
                continue
            color_counts[c] += 1
            total_checked += 1
            same = 0
            total_n = 0
            for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W:
                    total_n += 1
                    if field_map[ny][nx] == c:
                        same += 1
            if total_n > 0 and same == 0:
                noise += 1
    # PixelFlow 기준 ~12% 허용 → 15% 까지는 점수 감점 곡선
    noise_score = 1.0 - min(noise / max(total_checked * 0.15, 1), 1.0)

    if color_counts:
        vals = list(color_counts.values())
        avg = sum(vals) / len(vals)
        variance = sum((v - avg) ** 2 for v in vals) / len(vals)
        balance_score = 1.0 / (1.0 + variance / max(avg ** 2, 1))
    else:
        balance_score = 0.0

    return {
        "noise_score": round(noise_score, 3),
        "balance_score": round(balance_score, 3),
        "visual_quality": round(noise_score * 0.5 + balance_score * 0.5, 3),
    }


'''

# 3) Update compute_score signature + body to accept field_map and compute visual_quality
OLD_COMPUTE_SCORE = '''def compute_score(csv_row: dict, balloons: list[dict], gimmicks: list[dict],
                  color_darts: dict[int, int], metaphor: float,
                  hard_rule_errors: list[str], debut_warnings: list[str],
                  total_cells: int = 0) -> tuple[float, dict[str, float], list[str]]:
    """0-1 종합 점수 + 차원별 + HP visual gap warnings."""
    dims = {}

    # mod10_compliance
    total = sum(color_darts.values())
    color_violations = sum(1 for v in color_darts.values() if v % 10 != 0)
    color_total = len(color_darts) or 1
    dims["mod10_compliance"] = 1.0 if total % 10 == 0 and color_violations == 0 else max(0.0, 1.0 - (color_violations / color_total))

    # metaphor_score (직접 입력)
    dims["metaphor_score"] = metaphor

    # hard_rule_pass
    dims["hard_rule_pass"] = 1.0 if not hard_rule_errors else max(0.0, 1.0 - len(hard_rule_errors) * 0.2)

    # debut_compliance
    dims["debut_compliance"] = 1.0 if not debut_warnings else max(0.0, 1.0 - len(debut_warnings) * 0.1)

    # queue_alignment
    purpose = normalize_purpose(csv_row.get("purpose_type"))
    rng_t = PURPOSE_DART_RANGE.get(purpose, (0, 99999))
    in_range = rng_t[0] <= total <= rng_t[1]
    dims["queue_alignment"] = 1.0 if in_range else 0.7

    # v1.2.3 hp_visual_gap (§12) + soft_rule_pass (§11.2)
    hp_gap_score, hp_gap_warns = compute_hp_visual_gap_score(gimmicks, total_cells)
    dims["hp_visual_gap"] = hp_gap_score

    soft_warns = verify_60lv_reappearance(csv_row, gimmicks)
    dims["soft_rule_pass"] = 1.0 if not soft_warns else max(0.0, 1.0 - len(soft_warns) * 0.1)

    weighted = sum(dims[k] * SCORE_WEIGHTS[k] for k in dims if k in SCORE_WEIGHTS)
    return weighted, dims, hp_gap_warns'''

NEW_COMPUTE_SCORE = '''def compute_score(csv_row: dict, balloons: list[dict], gimmicks: list[dict],
                  color_darts: dict[int, int], metaphor: float,
                  hard_rule_errors: list[str], debut_warnings: list[str],
                  total_cells: int = 0,
                  field_map: list[list[int]] | None = None) -> tuple[float, dict[str, float], list[str]]:
    """0-1 종합 점수 + 차원별 + HP visual gap warnings.

    v1.2.4 (v43 통합): field_map 제공 시 visual_quality dim 계산.
    """
    dims = {}

    # mod10_compliance
    total = sum(color_darts.values())
    color_violations = sum(1 for v in color_darts.values() if v % 10 != 0)
    color_total = len(color_darts) or 1
    dims["mod10_compliance"] = 1.0 if total % 10 == 0 and color_violations == 0 else max(0.0, 1.0 - (color_violations / color_total))

    # metaphor_score (직접 입력)
    dims["metaphor_score"] = metaphor

    # v1.2.4 visual_quality (v43 통합: noise + balance)
    if field_map:
        vq = compute_visual_quality(field_map)
        dims["visual_quality"] = vq["visual_quality"]
    else:
        dims["visual_quality"] = 0.7  # field_map 없으면 중립값

    # hard_rule_pass
    dims["hard_rule_pass"] = 1.0 if not hard_rule_errors else max(0.0, 1.0 - len(hard_rule_errors) * 0.2)

    # debut_compliance
    dims["debut_compliance"] = 1.0 if not debut_warnings else max(0.0, 1.0 - len(debut_warnings) * 0.1)

    # queue_alignment
    purpose = normalize_purpose(csv_row.get("purpose_type"))
    rng_t = PURPOSE_DART_RANGE.get(purpose, (0, 99999))
    in_range = rng_t[0] <= total <= rng_t[1]
    dims["queue_alignment"] = 1.0 if in_range else 0.7

    # v1.2.3 hp_visual_gap (§12) + soft_rule_pass (§11.2)
    hp_gap_score, hp_gap_warns = compute_hp_visual_gap_score(gimmicks, total_cells)
    dims["hp_visual_gap"] = hp_gap_score

    soft_warns = verify_60lv_reappearance(csv_row, gimmicks)
    dims["soft_rule_pass"] = 1.0 if not soft_warns else max(0.0, 1.0 - len(soft_warns) * 0.1)

    weighted = sum(dims[k] * SCORE_WEIGHTS[k] for k in dims if k in SCORE_WEIGHTS)
    return weighted, dims, hp_gap_warns'''

# 4) Update build_field_analysis signature + body to include cluster_dist
OLD_BUILD_FA = '''def build_field_analysis(csv_row: dict, balloons: list[dict], gimmicks: list[dict],
                          color_darts: dict[int, int], chain_groups: list[dict],
                          metaphor: float, applied_rules: list[str],
                          placement_violations: list[str] | None = None,
                          hp_visual_gap_warnings: list[str] | None = None) -> dict:
    total_darts = sum(color_darts.values())'''

NEW_BUILD_FA = '''def build_field_analysis(csv_row: dict, balloons: list[dict], gimmicks: list[dict],
                          color_darts: dict[int, int], chain_groups: list[dict],
                          metaphor: float, applied_rules: list[str],
                          placement_violations: list[str] | None = None,
                          hp_visual_gap_warnings: list[str] | None = None,
                          field_map: list[list[int]] | None = None) -> dict:
    total_darts = sum(color_darts.values())'''

OLD_FA_RETURN = '''        # v1.2.3 §10 라인 1193-1194 신규 필드
        "placement_violations": placement_violations or [],
        "hp_visual_gap_warnings": hp_visual_gap_warnings or [],
    }'''

NEW_FA_RETURN = '''        # v1.2.3 §10 라인 1193-1194 신규 필드
        "placement_violations": placement_violations or [],
        "hp_visual_gap_warnings": hp_visual_gap_warnings or [],
        # v1.2.4 (v43 통합) — 객관 시각 지표
        "cluster_dist": compute_cluster_distribution(field_map) if field_map else None,
        "visual_quality": compute_visual_quality(field_map) if field_map else None,
    }'''

# 5) Update caller in _complete_one_seed to pass field_map
OLD_CALLER = '''    total_cells_int = int(csv_row.get("total_cells", 0) or 0)
    score, dims, hp_gap_warnings = compute_score(csv_row, balloons, all_gimmicks, color_darts,
                                                  metaphor, [], debut_warnings,
                                                  total_cells=total_cells_int)

    # STEP 8: 출력
    field_analysis = build_field_analysis(csv_row, balloons, all_gimmicks,
                                          color_darts, chain_groups, metaphor, applied_rules,
                                          placement_violations=placement_violations,
                                          hp_visual_gap_warnings=hp_gap_warnings)'''

NEW_CALLER = '''    total_cells_int = int(csv_row.get("total_cells", 0) or 0)
    score, dims, hp_gap_warnings = compute_score(csv_row, balloons, all_gimmicks, color_darts,
                                                  metaphor, [], debut_warnings,
                                                  total_cells=total_cells_int,
                                                  field_map=field_map)

    # STEP 8: 출력 — v1.2.4: field_map 전달로 cluster_dist + visual_quality 포함
    field_analysis = build_field_analysis(csv_row, balloons, all_gimmicks,
                                          color_darts, chain_groups, metaphor, applied_rules,
                                          placement_violations=placement_violations,
                                          hp_visual_gap_warnings=hp_gap_warnings,
                                          field_map=field_map)'''


def main():
    with open(PATH, encoding="utf-8") as f:
        src = f.read()

    checks = [
        (OLD_WEIGHTS, NEW_WEIGHTS, "SCORE_WEIGHTS"),
        (OLD_COMPUTE_SCORE, NEW_COMPUTE_SCORE, "compute_score"),
        (OLD_BUILD_FA, NEW_BUILD_FA, "build_field_analysis sig"),
        (OLD_FA_RETURN, NEW_FA_RETURN, "build_field_analysis return"),
        (OLD_CALLER, NEW_CALLER, "_complete_one_seed caller"),
    ]

    if "compute_cluster_distribution" in src:
        print("already patched (cluster_distribution exists). Aborting.", file=sys.stderr)
        sys.exit(1)

    # Verify all OLD blocks present
    for old, _, label in checks:
        if old not in src:
            print(f"ABORT — OLD pattern not found for: {label}", file=sys.stderr)
            sys.exit(1)

    # Insert helpers right before compute_score definition
    marker = "def compute_score(csv_row: dict, balloons: list[dict], gimmicks: list[dict],"
    if marker not in src:
        print("compute_score marker missing!", file=sys.stderr)
        sys.exit(1)
    src = src.replace(marker, HELPERS + marker, 1)

    # Apply replacements
    for old, new, _ in checks:
        src = src.replace(old, new, 1)

    with open(PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("patched ok")


if __name__ == "__main__":
    main()
