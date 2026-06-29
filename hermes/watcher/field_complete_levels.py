"""
Field Completer — CSV row → v3.15 JSON (balloons + gimmicks + field_analysis)

명세 문서: BalloonFlow_필드완성_명세.md (v1.2.3, 2026-05-19)
변경: HR 17-19 공존 매트릭스, PF 라이프 분포, score_placement_candidates,
      Iron_Wall mode-split, Barricade adjacent_inner + length, Target_Box box-structure,
      Frozen_Layer 모델 교체 (block_size + counter)
호출 방식: ProjectHub /api/agents/field-complete → spawn this script with --request <id>

기능:
  STEP 1: 입력 검증 (debut gate, ≤5종, color range, mod-10 잠재 검증)
  STEP 2: FieldMap 확보 (designer_note 파싱 또는 기본 레이아웃)
  STEP 3: 클러스터 분석 (color cluster + metaphor priority)
  STEP 4: Track A — PixelFlow 패턴 차용 (PF gimmick data 있을 때만)
  STEP 5: Track B — BalloonFlow 고유 기믹 합성 (7종 필드 기믹)
  STEP 6: mod-10 라이프 정합 (색상별 + 전체)
  STEP 7: 메타포 보존 검증 (5 술어 + 점수)
  STEP 8: v3.15 JSON 출력 + field_analysis

Score function:
  0-1 종합 점수. 0.85 미달 시 Claude LLM escalation (STEP 4-5 재실행).

LLM Auto-Escalation:
  ANTHROPIC_API_KEY 환경변수 있고 점수 < 0.85일 때 1회 escalation.
  없으면 deterministic 결과로 종료.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

log = logging.getLogger("field-complete")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# v43 hybrid pipeline (metaphor → ZoneMap → BL field_map)
# 호출: STEP 2 designer_note [FieldMap] 없을 때 bl_metaphor 기반 자동 생성
try:
    import zone_pipeline as _zp
    _ZP_AVAILABLE = True
except Exception as _zp_err:
    _ZP_AVAILABLE = False
    log.warning("zone_pipeline import failed (%s) — STEP 2 will use generate_default_layout fallback only", _zp_err)


# ─────────────────────────────────────────────────────
# 상수 (명세 §3, §7)
# ─────────────────────────────────────────────────────

# 도입 lv 게이트 (기믹명세 §0-12 정합)
BL_DEBUT_LV = {
    "gimmick_hidden":      11,    # Hidden Dart Box (큐)
    "gimmick_chain":       21,    # Linked Dart Box (큐)
    "gimmick_pinata":      31,    # Wooden Board (필드)
    "gimmick_glass_pipe":  41,    # Glass Pipe (큐)
    "gimmick_pin":         61,    # Barricade (필드)
    "gimmick_lock_key":    81,    # Lock & Key (보류, Snake 대체 후보)
    "gimmick_snake":       81,    # v1.2.10/20 Snake — Lock&Key 대체 (TBD PO)
    "gimmick_surprise":   101,    # Hidden Balloon (필드)
    "gimmick_wall":       121,    # Iron Wall (필드)
    "gimmick_spawner_o":  141,    # Pipe (큐)
    "gimmick_pinata_box": 161,    # Target Box (필드)
    "gimmick_ice":        201,    # Frozen Layer (필드)
    "gimmick_frozen_dart":241,    # Frozen Dart Box (큐)
    "gimmick_curtain":    301,    # Color Curtain (1.1+)
}

# 도입 lv 격리 룰 (G8, BeatChart §6-2)
INTRO_LVS = {11, 21, 31, 41, 61, 101, 121, 141, 161, 201, 241}  # 81 SKIP

# 필드 기믹 7종 (Track B 대상; Lock & Key SKIP, Color Curtain 1.1+)
FIELD_GIMMICKS = {
    "gimmick_pinata":     "Wooden_Board",
    "gimmick_pin":        "Barricade",
    "gimmick_snake":      "Snake",         # v1.2.10/20 신규
    "gimmick_surprise":   "Hidden_Balloon",
    "gimmick_wall":       "Iron_Wall",
    "gimmick_pinata_box": "Target_Box",
    "gimmick_ice":        "Frozen_Layer",
    # "gimmick_curtain":  "Color_Curtain",  # 1.1+
}

# 큐 측 5종 (chainGroupId 외 본 알고리즘 책임 없음)
QUEUE_GIMMICKS = {
    "gimmick_hidden":     "Hidden_Dart_Box",
    "gimmick_chain":      "Linked_Dart_Box",
    "gimmick_glass_pipe": "Glass_Pipe",
    "gimmick_spawner_o":  "Pipe",
    "gimmick_frozen_dart":"Frozen_Dart_Box",
}

# PKG별 다트 cap (BeatChart Hard Rule)
PKG_DART_CAP = {
    1: 1400, 2: 1500, 3: 1600, 4: 1700, 5: 1800,
    6: 1900, 7: 2000, 8: 2100, 9: 2200, 10: 2300,
    11: 2400, 12: 2500, 13: 2500, 14: 2500, 15: 2500,
}

# 큐생성기 §2-2 정합 범위 (warning만)
PURPOSE_DART_RANGE = {
    "tutorial":   (380, 720),
    "rest":       (450, 800),
    "normal":     (650, 1100),
    "hard":       (700, 1200),
    "super_hard": (800, 1400),
}

# 한글 purpose_type 매핑 (pixelforge_levels 컬렉션 KO 표기 지원)
PURPOSE_KO_TO_EN = {
    "튜토리얼": "tutorial",
    "휴식":    "rest",
    "노말":    "normal",
    "하드":    "hard",
    "슈퍼하드": "super_hard",
    "슈하":    "super_hard",
    "Tutorial": "tutorial",
    "Rest":    "rest",
    "Normal":  "normal",
    "Hard":    "hard",
    "SuperHard": "super_hard",
    "Super_Hard": "super_hard",
}


def normalize_purpose(p: str | None) -> str:
    if not p:
        return "normal"
    p = str(p).strip()
    return PURPOSE_KO_TO_EN.get(p, p.lower().replace("-", "_").replace(" ", "_"))


# 숫자 필드 자동 변환 (pixelforge_levels는 string으로 저장된 경우 多)
INT_FIELDS = {
    "level_number", "pkg", "pos", "chapter", "field_rows", "field_columns",
    "total_cells", "num_colors", "queue_columns", "queue_rows",
    "rail_capacity", "hard_tier", "total_darts", "gimmick_type_count",
    "gimmick_hidden", "gimmick_chain", "gimmick_pinata", "gimmick_glass_pipe",
    "gimmick_pin", "gimmick_lock_key", "gimmick_surprise", "gimmick_wall",
    "gimmick_spawner_o", "gimmick_spawner_t", "gimmick_pinata_box",
    "gimmick_ice", "gimmick_frozen_dart", "gimmick_curtain",
    "gimmick_snake",  # v1.2.10/20 신규
}


def normalize_csv_row(row: dict) -> dict:
    """CSV row를 알고리즘 친화적으로 정규화.
    - 숫자 필드 string → int
    - color_distribution 빈값일 때 num_colors+total_cells로 자동 생성
    - purpose_type 한글→영문
    """
    out = dict(row)
    # 숫자 필드 변환
    for k in INT_FIELDS:
        if k in out and out[k] not in (None, ""):
            try:
                out[k] = int(out[k])
            except (ValueError, TypeError):
                pass
    # purpose_type 정규화
    out["purpose_type"] = normalize_purpose(out.get("purpose_type"))
    # total_cells 자동 보강 (field_rows × field_columns × 0.65 휴리스틱)
    tc = out.get("total_cells")
    if not tc or int(tc or 0) == 0:
        fr = int(out.get("field_rows", 0) or 0)
        fc = int(out.get("field_columns", 0) or 0)
        if fr > 0 and fc > 0:
            out["total_cells"] = int(fr * fc * 0.65)
            out["_total_cells_auto"] = True
    # color_distribution 자동 생성 / 보강
    cd = out.get("color_distribution")
    if not cd or str(cd).strip() == "":
        # case 1: 완전히 비어있음 → 균등 분배 (c1, c2, ..., cN)
        nc = int(out.get("num_colors", 4) or 4)
        tc = int(out.get("total_cells", 0) or 0)
        if nc > 0 and tc > 0:
            per = tc // nc
            remainder = tc - per * nc
            parts = []
            for i in range(nc):
                count = per + (1 if i < remainder else 0)
                parts.append(f"c{i+1}:{count}")
            out["color_distribution"] = " ".join(parts)
            out["_color_distribution_auto"] = True
    else:
        # case 2: 'c1, c2' 같이 카운트 없는 형식 → 카운트 보강
        parsed = _parse_color_distribution(str(cd))
        if parsed and all(count == 0 for _, count in parsed):
            tc = int(out.get("total_cells", 0) or 0)
            n = len(parsed)
            if n > 0 and tc > 0:
                per = tc // n
                remainder = tc - per * n
                parts = []
                for i, (c, _) in enumerate(parsed):
                    count = per + (1 if i < remainder else 0)
                    parts.append(f"c{c}:{count}")
                out["color_distribution"] = " ".join(parts)
                out["_color_distribution_auto"] = True
    return out

# 점수 임계값
SCORE_THRESHOLD = 0.85
ESCALATION_THRESHOLD = 2  # Ouroboros economics 룰 차용

# Score 가중치 — v1.2.4 (v43 시각 품질 dimension 통합)
SCORE_WEIGHTS = {
    "metaphor_score":     0.35,  # 메타포 보존 (visual quality 핵심) — v43 통합으로 0.45→0.35
    "visual_quality":     0.12,  # NEW (v43): noise(고립셀) + balance(색상 균형)
    "mod10_compliance":   0.18,  # 자동 정합
    "hard_rule_pass":     0.10,  # debut/Lock&Key/Glass↔Pipe + placement violations (0.12→0.10)
    "debut_compliance":   0.08,  # intro 격리
    "queue_alignment":    0.05,  # 큐 다트 범위 (warning만)
    "hp_visual_gap":      0.07,  # 셀% vs HP% gap (§12 라인 1275-1283)
    "soft_rule_pass":     0.05,  # 60-lv reappearance, hp_visual_gap_warnings (§11.2)
}

# LLM escalation 임계: 활성 기믹이 있고 score < 이 값이면 호출
ESCALATION_SCORE_THRESHOLD = 0.95

# PF 1-300 데이터 기반 라이프 분포 (v1.2.3 §7.6)
PF_LIFE_DISTRIBUTIONS = {
    "Wooden_Board": {
        # PF Hard Pixels HP 분포 (n=311, med=7, top: 5, 6, 20, 10, 4, 7)
        # 1×1 cluster small (<30 cells) → med-low life
        "1x1": [(5, 0.18), (6, 0.15), (7, 0.13), (10, 0.14), (15, 0.10),
                (20, 0.15), (30, 0.10), (50, 0.05)],
        # 2×3 cluster large → med-high life
        "2x3": [(12, 0.20), (15, 0.30), (18, 0.30), (21, 0.20)],
    },
    "Frozen_Layer": {
        # PF Ice Health/cell 분포 (n=62, med 2.0, p25=1.0, p75=3.33)
        "per_cell": [(1, 0.25), (2, 0.40), (3, 0.25), (4, 0.10)],
    },
    "Target_Box": {
        # BL spec 권장 (PF는 box HP 미보유)
        "per_target": [(5, 0.35), (10, 0.40), (15, 0.25)],
    },
    "Barricade": {
        # PF Door Count med=50, Count/cell med=12.5 → length = clamp(Count/10, 3, 8)
        "length": [(3, 0.30), (5, 0.40), (6, 0.15), (8, 0.15)],
    },
}

# PF 1-300 데이터 기반 위치 편중 (v1.2.3 §5-4)
# 각 기믹 타입별 점수 가중치 (y_target, y_weight, edge_bonus, corner_bonus, centrality_bonus)
PF_PLACEMENT_BIAS = {
    "Iron_Wall":     {"y_target": 0.26, "y_weight": 1.5, "edge_bonus": 0.3, "corner_bonus": 0.4, "centrality_bonus": 0.0},
    "Wooden_Board":  {"y_target": 0.50, "y_weight": 1.0, "edge_bonus": 0.0, "corner_bonus": 0.0, "centrality_bonus": 0.2},
    "Hidden_Balloon": {"y_target": 0.46, "y_weight": 1.0, "edge_bonus": 0.0, "corner_bonus": 0.0, "centrality_bonus": 0.0, "edge_penalty": 0.5},
    "Barricade":     {"y_target": 0.52, "y_weight": 0.8, "edge_bonus": 0.3, "corner_bonus": 0.5, "centrality_bonus": 0.0},
    "Target_Box":    {"y_target": 0.16, "y_weight": 1.2, "edge_bonus": 0.5, "corner_bonus": 0.2, "centrality_bonus": 1.0},
    "Frozen_Layer":  {"y_target": 0.45, "y_weight": 1.0, "edge_bonus": 0.0, "corner_bonus": 0.0, "centrality_bonus": 0.0},
}



# ─────────────────────────────────────────────────────
# v1.2.6 난이도별 분포 헬퍼 (§7.7) — PF 1-300 분포 기반
# 단일 평균이 아닌 bimodal/trimodal/단조증가 패턴 반영.
# ─────────────────────────────────────────────────────

def wooden_board_hp_v2(size_cells: int, difficulty: str, rng: random.Random) -> int:
    """§7.7.1 — 바이모달. 78% 소HP(4-10) + 17% 대HP spike(20+).
    난이도 ↑ = 대HP cluster 비율 ↑.
    size_cells: 클러스터 셀 수. size 곱셈은 BL 사이즈 곡선.
    """
    big_spike_chance = {
        "tutorial": 0.05, "rest": 0.10,
        "normal": 0.17,
        "hard": 0.30, "super_hard": 0.40,
    }.get(difficulty, 0.17)

    if rng.random() < big_spike_chance:
        # 대HP: PF mode 20 (88% of big), 30+ rare
        idx = _weighted_choice([20, 30, 40, 50], [0.70, 0.15, 0.10, 0.05], rng)
        base = [20, 30, 40, 50][idx]
    else:
        # 소HP: PF 빈도 5/6/10/4/7/8/9 (mode-aware)
        vals = [4, 5, 6, 7, 8, 9, 10]
        weights = [0.13, 0.18, 0.15, 0.11, 0.04, 0.03, 0.14]
        idx = _weighted_choice(vals, weights, rng)
        base = vals[idx]
    # size 곱셈 (BL 사이즈 곡선)
    if size_cells >= 9:
        return base * 3
    if size_cells >= 4:
        return base * 2
    return base



def wooden_board_size_v3(rng: random.Random) -> tuple[int, int]:
    """v1.2.9 §7.7.1 정정 — PF Hard Pixel `pixels` 배열 areaX/areaY 분포.
    이전 v1.2.6 은 healths 만 보고 1×1 가정. 실제 PF 는 99.4% 다중 셀.
    분포 (PF picked 311 인스턴스):
        2×2 19% | 4×1 15% | 2×4 15% | 3×1 10% | 4×4 9%
        1×3 8%  | 3×3 7%  | 4×2 7%  | 2×6 4%  | 1×1 0.6%
        + 기타 (3×2, 2×3, 1×2, 2×1, 1×4, 5×5, 6×6 등) ~5%
    """
    options = [
        ((2, 2), 0.19),
        ((4, 1), 0.15),
        ((2, 4), 0.15),
        ((3, 1), 0.10),
        ((4, 4), 0.09),
        ((1, 3), 0.08),
        ((3, 3), 0.07),
        ((4, 2), 0.07),
        ((2, 6), 0.04),
        ((3, 2), 0.025),
        ((2, 3), 0.025),
        ((1, 2), 0.015),
        ((2, 1), 0.015),
        ((5, 5), 0.005),
        ((6, 6), 0.005),
        ((1, 1), 0.006),
    ]
    sizes = [s for s, _ in options]
    weights = [w for _, w in options]
    idx = _weighted_choice(sizes, weights, rng)
    return sizes[idx]


def iron_wall_y_v2(difficulty: str, rng: random.Random) -> float:
    """§7.7.3 — 양극 trimodal. 상단(0.0-0.2) vs 중앙(0.4-0.6) vs 하단(0.8-1.0).
    난이도 ↑ = 중앙 감소 + 양극화 강화.
    """
    profile = {
        "tutorial":   [0.43, 0.21, 0.36],
        "rest":       [0.43, 0.21, 0.36],
        "normal":     [0.50, 0.18, 0.32],
        "hard":       [0.59, 0.09, 0.32],
        "super_hard": [0.55, 0.15, 0.30],
    }.get(difficulty, [0.50, 0.18, 0.32])
    zones = ["top", "mid", "bot"]
    idx = _weighted_choice(zones, profile, rng)
    zone = zones[idx]
    if zone == "top":
        return rng.uniform(0.0, 0.2)
    if zone == "mid":
        return rng.uniform(0.4, 0.6)
    return rng.uniform(0.8, 1.0)


def frozen_layer_health_per_cell_v2(difficulty: str, rng: random.Random) -> int:
    """§7.7.4 — 난이도별 비대칭 분포. PF Medium mode 1, VH mode 8."""
    if difficulty in ("tutorial", "rest"):
        return 1  # 학습용
    if difficulty == "normal":
        # PF Medium mode 1.1 (27%)
        idx = _weighted_choice([1, 2], [0.70, 0.30], rng)
        return [1, 2][idx]
    if difficulty == "hard":
        idx = _weighted_choice([1, 2, 3], [0.40, 0.30, 0.30], rng)
        return [1, 2, 3][idx]
    # super_hard: PF VH mode 8 (15%), spread
    idx = _weighted_choice([1, 2, 3, 8], [0.30, 0.20, 0.20, 0.30], rng)
    return [1, 2, 3, 8][idx]



def target_box_per_target_life_v2(difficulty: str, rng: random.Random) -> int:
    """v1.2.6 +α: 난이도별 per-target HP (이전 pick_pf_grounded_life 대체).
    PF eggBoxes Eggs[].Count mode 10/12/20 + 난이도 ↑ HP ↑."""
    if difficulty in ("tutorial", "rest"):
        return rng.choice([5, 5, 8, 10])
    if difficulty == "normal":
        return rng.choices([5, 10, 12, 15], weights=[0.20, 0.35, 0.25, 0.20])[0]
    if difficulty == "hard":
        return rng.choices([10, 12, 15, 20], weights=[0.20, 0.30, 0.30, 0.20])[0]
    # super_hard
    return rng.choices([15, 20, 25, 30], weights=[0.25, 0.30, 0.25, 0.20])[0]


def hidden_balloon_pct_cap_v2(difficulty: str) -> float:
    """§7.7.2 — 난이도별 점유율 cap (board pixels 대비)."""
    return {
        "tutorial": 0.03, "rest": 0.03,
        "normal": 0.05,        # PF Medium med 1.8%
        "hard": 0.08,
        "super_hard": 0.12,    # PF Very Hard med 9.4%
    }.get(difficulty, 0.05)


def target_box_size_v2(difficulty: str, rng: random.Random) -> tuple[tuple[int, int], int]:
    """§7.7.5 — 난이도별 box size (rows, cols) + eggs."""
    if difficulty in ("tutorial", "rest"):
        return ((2, 2), 4)
    if difficulty == "normal":
        opts = [((2, 2), 4), ((2, 3), 6)]
        idx = _weighted_choice(opts, [0.70, 0.30], rng)
        return opts[idx]
    if difficulty == "hard":
        opts = [((2, 3), 6), ((3, 3), 9)]
        idx = _weighted_choice(opts, [0.60, 0.40], rng)
        return opts[idx]
    # super_hard
    opts = [((3, 3), 9), ((2, 3), 6)]
    idx = _weighted_choice(opts, [0.60, 0.40], rng)
    return opts[idx]


def barricade_length_v2(difficulty: str, rng: random.Random) -> int:
    """§7.7.6 — 난이도별 단조 증가. PF HP / 10 가이드 (BL 1-dart/cell)."""
    length_dist = {
        "tutorial":   ([3, 4], [0.70, 0.30]),
        "rest":       ([3, 4], [0.70, 0.30]),
        "normal":     ([3, 5, 6], [0.30, 0.40, 0.30]),
        "hard":       ([5, 6, 7], [0.30, 0.30, 0.40]),
        "super_hard": ([6, 7, 8], [0.25, 0.25, 0.50]),
    }.get(difficulty, ([3, 5, 6], [0.30, 0.40, 0.30]))
    vals, weights = length_dist
    idx = _weighted_choice(vals, weights, rng)
    return vals[idx]



# ─────────────────────────────────────────────────────
# v1.2.14 HP × Length 독립 — intent 기반 라이프 (PO 직감 검증)
# ─────────────────────────────────────────────────────

def barricade_hp_from_length(length: int, intent: str, rng: random.Random) -> int:
    """Barricade HP를 cell length와 의도로 결정.
    intent: 'fast'(1-2/cell, 빨리 제거) / 'normal'(2-3) / 'slow'(4-5) / 'boss'(6-7).
    PO 직감 검증: 같은 length 에도 HP variance 존재 (퍽퍽 vs 천천히)."""
    ratio_range = {
        "fast": (1, 2),
        "normal": (2, 3),
        "slow": (4, 5),
        "boss": (6, 7),
    }.get(intent, (2, 3))
    return max(1, length * rng.randint(*ratio_range))


def snake_hp_from_cells(total_cells: int, intent: str, rng: random.Random) -> int:
    """Snake HP를 총 셀 수와 의도로 결정.
    intent: 'cathartic'(0.5/cell, 대폭발) / 'normal'(1-2) / 'tough'(3-4) / 'boss'(5-12)."""
    if intent == "cathartic":
        return max(20, int(total_cells * 0.5))
    if intent == "tough":
        return int(total_cells * rng.uniform(3.0, 4.0))
    if intent == "boss":
        return int(total_cells * rng.uniform(5.0, 12.0))
    return int(total_cells * rng.uniform(1.0, 2.0))


def difficulty_to_intent(difficulty: str, gimmick_type: str = "Barricade") -> str:
    """난이도 → HP intent 매핑. Barricade·Snake 공통."""
    mapping = {
        "tutorial":   "fast",
        "rest":       "fast",
        "normal":     "normal",
        "hard":       "slow",
        "super_hard": "boss",
    }
    return mapping.get(difficulty, "normal")


# ─────────────────────────────────────────────────────
# v1.2.10/20 Snake 신규 기믹 (Lock & Key 대체 후보, debut lv 81)
# ─────────────────────────────────────────────────────

def grow_snake_body_segments(head_anchor, head_size, n_segments,
                              available_cells, used: set, rng: random.Random,
                              field_h: int, field_w: int):
    """SnakeGridPoints 모사 — 마디를 n_segments 개 walk.
    v1.2.17 실측 정합: zigzag(≤2칸) 60% + jump(>2칸) 40%.

    각 마디 = head_size 크기 셀 블록. 연속 곡선 보장 (꺾이는 corner 좌표).
    """
    segments = []
    cur = tuple(head_anchor)
    used_local = set(used)
    used_local.update(_rect_cells(head_anchor, head_size))

    for _seg_idx in range(n_segments):
        # zigzag vs jump 선택
        if rng.random() < 0.60:
            # zigzag: 인접 2칸 step (4방향)
            step_distance = rng.choice([2, 2, 2, 3])
        else:
            # jump: 3-35칸 long-tail
            step_distance = rng.randint(3, min(15, max(3, field_h // 2)))

        # 4방향 중 하나
        directions = [(0, step_distance), (0, -step_distance),
                      (step_distance, 0), (-step_distance, 0)]
        rng.shuffle(directions)

        placed = False
        for dy, dx in directions:
            nxt_anchor = (cur[0] + dy, cur[1] + dx)
            seg_cells = _rect_cells(nxt_anchor, head_size)
            if all(0 <= r < field_h and 0 <= c < field_w and (r, c) not in used_local
                   and (r, c) in available_cells
                   for r, c in seg_cells):
                segments.append(seg_cells)
                used_local.update(seg_cells)
                cur = nxt_anchor
                placed = True
                break
        if not placed:
            # 더 작은 step 으로 재시도 (1칸 인접)
            for dy, dx in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nxt_anchor = (cur[0] + dy, cur[1] + dx)
                seg_cells = _rect_cells(nxt_anchor, head_size)
                if all(0 <= r < field_h and 0 <= c < field_w and (r, c) not in used_local
                       and (r, c) in available_cells
                       for r, c in seg_cells):
                    segments.append(seg_cells)
                    used_local.update(seg_cells)
                    cur = nxt_anchor
                    placed = True
                    break
        if not placed:
            break  # 더 이상 갈 곳 없음
    return segments


def _rect_cells(anchor, size):
    """anchor (top-left) + size (rows, cols) → cell list."""
    r0, c0 = anchor
    h, w = size
    return [(r0 + dr, c0 + dc) for dr in range(h) for dc in range(w)]


def place_snake(clusters: list[dict], count: int, csv_row: dict,
                used: set, rng: random.Random,
                field_h: int, field_w: int,
                field_map: list[list[int]]) -> list[dict]:
    """v1.2.10/20 gimmick_snake — debut lv 81 (PO 결정 시 변경).
    PF MainGridPoints (머리 마디) + SnakeGridPoints (몸 마디 좌표 시퀀스) 모사.
    """
    if not clusters or count == 0:
        return []
    purpose = normalize_purpose(csv_row.get("purpose_type"))
    intent = difficulty_to_intent(purpose, "Snake")

    # available_cells = 모든 cluster cells (메타포 포함) — Snake 는 메타포 위 가능
    available_cells: set = set()
    for c in clusters:
        available_cells.update(c["cells"])
    available_cells -= used

    result = []
    for i in range(count):
        # 머리 마디 사이즈: PF 82% 2×2 + 18% 3×3
        head_size = (2, 2) if rng.random() < 0.82 else (3, 3)

        # 머리 anchor 후보 — 비-메타포 영역 우선
        non_meta = compute_non_metaphor_cells(clusters)
        head_candidates = [c for c in non_meta
                           if c not in used and 0 <= c[0] < field_h - head_size[0]
                           and 0 <= c[1] < field_w - head_size[1]]
        if not head_candidates:
            head_candidates = [c for c in available_cells
                               if 0 <= c[0] < field_h - head_size[0]
                               and 0 <= c[1] < field_w - head_size[1]]
        if not head_candidates:
            continue
        # score-based pick (Snake 는 PF Y 상단 58% 편중)
        scored = score_placement_candidates(head_candidates, "Snake", field_h, field_w)
        head_anchor = scored[0][0] if scored else head_candidates[0]

        head_cells = _rect_cells(head_anchor, head_size)
        if any((r, c) in used or not (0 <= r < field_h and 0 <= c < field_w)
               for r, c in head_cells):
            continue

        # 몸 마디 수: PF 빈도 (mode 4, med 8)
        body_n_options = [2, 4, 7, 8, 10, 14, 32]
        body_weights = [0.13, 0.16, 0.13, 0.13, 0.08, 0.06, 0.05]
        body_n = body_n_options[_weighted_choice(body_n_options, body_weights, rng)]

        # 몸 walk
        used_for_snake = set(head_cells)
        body_segments = grow_snake_body_segments(
            head_anchor, head_size, body_n,
            available_cells, used_for_snake, rng,
            field_h, field_w,
        )
        # 색 결정 — 우세 색 (cluster centroid 셀의 색)
        cr, cc = head_anchor
        color = field_map[cr][cc] if 0 <= cr < field_h and 0 <= cc < field_w else 1

        # HP 결정 (v1.2.14 intent)
        total_cells_snake = len(head_cells) + sum(len(s) for s in body_segments)
        hp = snake_hp_from_cells(total_cells_snake, intent, rng)

        # used 갱신
        all_cells = list(head_cells)
        for seg in body_segments:
            all_cells.extend(seg)
        used.update(all_cells)

        result.append({
            "type": "Snake",
            "main_grid_points": [list(c) for c in head_cells],
            "snake_grid_points": [[list(c) for c in seg] for seg in body_segments],
            "cells": all_cells,
            "head_size": list(head_size),
            "n_segments": len(body_segments),
            "color": color,
            "material": color,
            "count": hp,
            "life": hp,
            "intent": intent,
        })
    return result




def pick_pf_grounded_life(gimmick_type: str, ctx: str | None,
                          rng: random.Random) -> int:
    """PF 분포 가중 random sampling.
    ctx: '1x1', '2x3', 'per_cell', 'per_target', 'length' 등 sub-key.
    """
    dist = PF_LIFE_DISTRIBUTIONS.get(gimmick_type, {})
    if isinstance(dist, dict) and ctx and ctx in dist:
        items = dist[ctx]
    elif isinstance(dist, list):
        items = dist
    else:
        # default fallback
        return 5
    total = sum(w for _, w in items)
    r = rng.uniform(0, total)
    acc = 0.0
    for v, w in items:
        acc += w
        if r <= acc:
            return v
    return items[-1][0]


def score_placement_candidates(candidates: list[tuple[int, int]],
                               gimmick_type: str,
                               field_h: int,
                               field_w: int,
                               cluster: dict | None = None,
                               y_target_override: float | None = None) -> list[tuple[tuple[int, int], float]]:
    """각 후보 셀에 PF 위치 편중 기반 점수 부여.
    v1.2.6: y_target_override 로 trimodal Y 가능 (Iron Wall pf_wall).
    returns sorted desc by score: [(cell, score), ...]"""
    bias = PF_PLACEMENT_BIAS.get(gimmick_type, {})
    y_target = y_target_override if y_target_override is not None else bias.get("y_target", 0.5)
    y_weight = bias.get("y_weight", 0.0)
    edge_bonus = bias.get("edge_bonus", 0.0)
    corner_bonus = bias.get("corner_bonus", 0.0)
    centrality_bonus = bias.get("centrality_bonus", 0.0)
    edge_penalty = bias.get("edge_penalty", 0.0)

    centroid = cluster.get("centroid") if cluster else None
    outline_set = set(cluster.get("outline", [])) if cluster else set()
    field_diag = (field_h ** 2 + field_w ** 2) ** 0.5

    scored = []
    for r, c in candidates:
        # base score = 1
        score = 1.0
        # Y 편중 (target에 가까울수록 가중)
        if field_h > 0:
            y_norm = r / max(1, field_h - 1)
            y_dist = abs(y_norm - y_target)
            score += y_weight * (1.0 - y_dist * 2)  # y_dist=0 → +weight, y_dist=0.5 → 0
        # edge / corner bonus
        is_edge = r == 0 or r == field_h - 1 or c == 0 or c == field_w - 1
        if is_edge:
            score += edge_bonus
        is_outline = (r, c) in outline_set
        if is_outline:
            # outline cell — 일부 기믹 (Barricade)에 보너스
            score += edge_bonus * 0.5
        # corner detection (outline 이웃 ≤ 1)
        if (r, c) in outline_set:
            nb_outline = sum(1 for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                             if (dr, dc) != (0, 0) and (r + dr, c + dc) in outline_set)
            if nb_outline <= 1:
                score += corner_bonus
        # centrality (cluster centroid 거리)
        if centroid and centrality_bonus > 0:
            cdist = ((r - centroid[0]) ** 2 + (c - centroid[1]) ** 2) ** 0.5
            score += centrality_bonus * (1.0 - min(1.0, cdist / max(1, field_diag / 3)))
        # edge_penalty (Hidden_Balloon은 outline 회피)
        if edge_penalty > 0 and is_outline:
            score -= edge_penalty
        scored.append(((r, c), score))
    scored.sort(key=lambda x: -x[1])
    return scored


def find_first_valid(scored: list[tuple[tuple[int, int], float]],
                     size: tuple[int, int],
                     cluster_cells: list[tuple[int, int]],
                     excluded: set[tuple[int, int]]) -> tuple[int, int] | None:
    """scored 후보 desc 순서대로, size bbox가 cluster_cells 안에 들어가는 첫 셀."""
    h, w = size
    cluster_set = set(cluster_cells)
    for cell, _ in scored:
        if cell in excluded:
            continue
        r0, c0 = cell
        all_inside = True
        for dr in range(h):
            for dc in range(w):
                cc = (r0 + dr, c0 + dc)
                if cc not in cluster_set or cc in excluded:
                    all_inside = False
                    break
            if not all_inside:
                break
        if all_inside:
            return cell
    return None


def furthest_apart_scored(scored: list[tuple[tuple[int, int], float]],
                          n: int) -> list[tuple[int, int]]:
    """그리디 farthest-point selection + score 가중치.
    첫 셀은 가장 높은 score, 이후 selected에서 max-distance + score combined."""
    if not scored:
        return []
    selected = [scored[0][0]]
    remaining = [s for s in scored[1:]]
    while len(selected) < n and remaining:
        best_idx = 0
        best_metric = -1.0
        for i, (cell, score) in enumerate(remaining):
            min_d = min(((cell[0] - s[0]) ** 2 + (cell[1] - s[1]) ** 2) ** 0.5
                        for s in selected)
            # 가중 결합: distance 80% + score 20%
            metric = min_d * 0.8 + score * 0.2
            if metric > best_metric:
                best_metric = metric
                best_idx = i
        selected.append(remaining.pop(best_idx)[0])
    return selected


def compute_adjacent_inner_cells(outline_cells: list[tuple[int, int]],
                                 cluster_cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """outline 셀에 1셀 안쪽 cluster 셀들."""
    outline_set = set(outline_cells)
    cluster_set = set(cluster_cells)
    inner_cells = cluster_set - outline_set
    adjacent = set()
    for cell in inner_cells:
        r, c = cell
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            if (r + dr, c + dc) in outline_set:
                adjacent.add(cell)
                break
    return list(adjacent)


def identify_corner_regions(adjacent_inner: list[tuple[int, int]],
                            outline_cells: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """adjacent_inner 중 cluster corner 근처 (outline 이웃 ≤ 1인 영역)."""
    outline_set = set(outline_cells)
    corner_inner = []
    for cell in adjacent_inner:
        r, c = cell
        # 인근 outline의 corner 여부
        nb_outline_neighbors = []
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if (dr, dc) == (0, 0):
                    continue
                nb = (r + dr, c + dc)
                if nb in outline_set:
                    nb_outline_neighbors.append(nb)
        # outline 이웃이 정확히 2개 이하 = corner 영역
        if len(nb_outline_neighbors) <= 2:
            corner_inner.append(cell)
    return corner_inner


def clip_rect_to_cluster_bbox(pos: tuple[int, int],
                              bbox_size: tuple[int, int],
                              clusters: list[dict]) -> tuple[tuple[int, int], list[tuple[int, int]]]:
    """가장 가까운 cluster의 cells에 직사각형 clipping.
    anchor가 cluster 외부이면 cluster centroid로 shift (Frozen_Layer는 cluster 내부 배치 보장).
    returns ((h, w), cells)."""
    if not clusters:
        return bbox_size, [pos]
    # 가장 가까운 cluster 찾기 (anchor와 거리 기준)
    r0, c0 = pos
    nearest = None
    min_d = float("inf")
    for c in clusters:
        cr, cc = c.get("centroid", (0, 0))
        d = (r0 - cr) ** 2 + (c0 - cc) ** 2
        if d < min_d:
            min_d = d
            nearest = c
    if not nearest:
        return bbox_size, [pos]
    cluster_set = set(nearest["cells"])
    bh, bw = bbox_size

    # anchor가 cluster 외부이거나 너무 멀면 cluster centroid 기준으로 shift
    if pos not in cluster_set:
        cr, cc = nearest["centroid"]
        r0 = max(0, cr - bh // 2)
        c0 = max(0, cc - bw // 2)

    # bbox 내에서 cluster_set과 교집합만
    cells = []
    for dr in range(bh):
        for dc in range(bw):
            cell = (r0 + dr, c0 + dc)
            if cell in cluster_set:
                cells.append(cell)

    # 교집합이 너무 적으면 anchor 이동 — cluster bbox에 더 깊이 들어가기
    if len(cells) < (bh * bw) // 4:
        # cluster 내 모든 셀 중 anchor 가까운 위치들 시도
        rs_all = [c[0] for c in nearest["cells"]]
        cs_all = [c[1] for c in nearest["cells"]]
        c_min_r, c_max_r = min(rs_all), max(rs_all)
        c_min_c, c_max_c = min(cs_all), max(cs_all)
        # cluster bbox 안에서 격자 시도
        best_cells = cells
        for try_r in range(c_min_r, c_max_r + 1, max(1, bh // 2)):
            for try_c in range(c_min_c, c_max_c + 1, max(1, bw // 2)):
                trial = []
                for dr in range(bh):
                    for dc in range(bw):
                        cell = (try_r + dr, try_c + dc)
                        if cell in cluster_set:
                            trial.append(cell)
                if len(trial) > len(best_cells):
                    best_cells = trial
                    if len(best_cells) >= (bh * bw) * 0.7:
                        break
            if len(best_cells) >= (bh * bw) * 0.7:
                break
        cells = best_cells

    if not cells:
        return bbox_size, [pos]

    rs = [c[0] for c in cells]
    cs = [c[1] for c in cells]
    actual_h = max(rs) - min(rs) + 1
    actual_w = max(cs) - min(cs) + 1
    return (actual_h, actual_w), cells


# BalloonFlow 24색 팔레트 RGB (page.tsx와 동일)
BL_PALETTE_RGB = [
    (252, 106, 175), ( 80, 232, 246), (137,  80, 248), (254, 213,  85),
    (115, 254, 102), (253, 161,  76), (255, 255, 255), ( 65,  65,  65),
    (110, 168, 250), ( 57, 174,  46), (252,  94,  94), ( 50, 107, 248),
    ( 58, 165, 139), (231, 167, 250), (183, 199, 251), (106,  74,  48),
    (254, 227, 169), (253, 183, 193), (158,  61,  94), (167, 221, 148),
    ( 89,  46, 126), (220, 120, 129), (217, 217, 231), (111, 114, 127),
]


def decode_image_to_palette_grid(image_base64: str, target_rows: int, target_cols: int) -> list[list[int]] | None:
    """image_base64 (PNG) → 2D BL color index grid (1-based, 0=transparent).
    target_rows × target_cols로 리사이즈."""
    if not image_base64:
        return None
    try:
        import base64
        from io import BytesIO
        from PIL import Image
        # data URL prefix 제거
        s = image_base64
        if "," in s:
            s = s.split(",", 1)[1]
        png_bytes = base64.b64decode(s)
        img = Image.open(BytesIO(png_bytes)).convert("RGBA")
        if img.size != (target_cols, target_rows):
            img = img.resize((target_cols, target_rows), Image.NEAREST)
        pixels = img.load()
        grid: list[list[int]] = []
        for r in range(target_rows):
            row = []
            for c in range(target_cols):
                px = pixels[c, r]
                if px[3] < 128:  # transparent
                    row.append(-1)
                else:
                    # 가장 가까운 BL 팔레트
                    bl_idx = _nearest_bl_index(px[:3])
                    row.append(bl_idx + 1)  # 1-based
            grid.append(row)
        return grid
    except Exception as e:
        log.warning("image decode failed: %s", e)
        return None


def _nearest_bl_index(rgb: tuple) -> int:
    r, g, b = rgb[:3]
    best = 0
    best_d = float("inf")
    for i, (pr, pg, pb) in enumerate(BL_PALETTE_RGB):
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best_d:
            best_d = d
            best = i
    return best


def compute_color_importance(image_grid: list[list[int]] | None,
                             field_map: list[list[int]]) -> dict[int, float]:
    """색상별 importance (0-1). 적게 나타날수록 = 시각적 핵심.
    image_grid가 있으면 그걸 사용, 없으면 field_map.
    importance = 1 - (color_count / total_cells)."""
    grid = image_grid or field_map
    counter: Counter = Counter()
    total = 0
    for row in grid:
        for c in row:
            if c >= 0:
                counter[c] += 1
                total += 1
    if total == 0:
        return {}
    importance = {}
    for color, count in counter.items():
        # 적게 나타날수록 importance ↑ (희소 색 = 강조)
        freq = count / total
        # importance = 1 / (1 + 5 * freq) → freq 0.05 ≈ 0.8, freq 0.5 ≈ 0.29
        importance[color] = 1.0 / (1.0 + 5.0 * freq)
    return importance


def image_metaphor_penalty(image_grid: list[list[int]] | None,
                          field_map: list[list[int]],
                          gimmicks: list[dict]) -> float:
    """기믹 셀들의 평균 importance. 0=완벽 (낮은 importance 셀에만), 1=최악 (희소 색 침범).
    metaphor_score에서 (1 - 이 값)으로 통합."""
    importance = compute_color_importance(image_grid, field_map)
    if not importance:
        return 0.0
    total_imp = 0.0
    cnt = 0
    for g in gimmicks:
        # Hidden_Balloon/Frozen_Layer는 색상 보존 → penalty 면제
        if g.get("type") in ("Hidden_Balloon", "Frozen_Layer"):
            continue
        cells = []
        if "cells" in g:
            for c in g.get("cells", []):
                if isinstance(c, (list, tuple)) and len(c) == 2:
                    cells.append((c[0], c[1]))
        elif "row" in g and "col" in g:
            cells.append((g["row"], g["col"]))
        for r, col in cells:
            if 0 <= r < len(field_map) and 0 <= col < len(field_map[0]):
                color = field_map[r][col]
                if color >= 0:
                    total_imp += importance.get(color, 0)
                    cnt += 1
    return total_imp / max(1, cnt)


# ─────────────────────────────────────────────────────
# 환경
# ─────────────────────────────────────────────────────

def _load_dotenv(env_path: str = "") -> None:
    if not env_path:
        env_path = str(Path(__file__).resolve().parent / ".env")
    p = Path(env_path)
    if not p.exists():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────
# STEP 1: 입력 검증
# ─────────────────────────────────────────────────────

def validate_input(csv_row: dict, partial_json: dict | None = None) -> tuple[bool, list[str]]:
    """Returns (passed, errors)."""
    errors: list[str] = []
    required = ["level_number", "pkg", "purpose_type",
                "field_rows", "field_columns", "total_cells", "num_colors",
                "color_distribution", "queue_columns", "rail_capacity"]
    for f in required:
        if csv_row.get(f) in (None, ""):
            errors.append(f"missing field: {f}")
    if errors:
        return False, errors

    if int(csv_row.get("field_rows", 0)) > 50:
        errors.append(f"field_rows {csv_row['field_rows']} > 50")
    if int(csv_row.get("field_columns", 0)) > 40:
        errors.append(f"field_columns {csv_row['field_columns']} > 40")
    nc = int(csv_row.get("num_colors", 0))
    if nc < 2 or nc > 11:
        errors.append(f"num_colors {nc} out of [2,11]")

    # 기믹 종 수 ≤ 5
    active_gim = [k for k in csv_row if k.startswith("gimmick_") and int(csv_row.get(k, 0)) > 0]
    if len(active_gim) > 5:
        errors.append(f"too many gimmick types: {len(active_gim)} > 5")

    # Lock & Key SKIP
    if int(csv_row.get("gimmick_lock_key", 0)) > 0:
        errors.append("Lock & Key SKIP in 1.0 — set gimmick_lock_key=0")

    # debut gate
    lv = int(csv_row["level_number"])
    for gim in active_gim:
        debut = BL_DEBUT_LV.get(gim)
        if debut and lv < debut:
            errors.append(f"{gim} at lv{lv} < debut {debut}")

    # Glass Pipe / Pipe 혼합
    has_glass = int(csv_row.get("gimmick_glass_pipe", 0)) > 0
    has_pipe = int(csv_row.get("gimmick_spawner_o", 0)) > 0
    if has_glass and has_pipe:
        errors.append("Glass Pipe + Pipe 혼합 금지")

    # Hard Rule 17/18/19 — 공존 매트릭스 (v1.2.1/v1.2.2)
    # PF 0번 = BL 금지 원칙
    has_wall = int(csv_row.get("gimmick_wall", 0)) > 0
    has_ice = int(csv_row.get("gimmick_ice", 0)) > 0
    has_pin = int(csv_row.get("gimmick_pin", 0)) > 0
    has_surprise = int(csv_row.get("gimmick_surprise", 0)) > 0
    if has_wall and has_ice:
        errors.append("HR 17: Iron_Wall × Frozen_Layer 동시 금지 (PF=0, deadlock 위험)")
    if has_pin and has_surprise:
        errors.append("HR 18: Barricade × Hidden_Balloon 동시 금지 (PF=0)")
    if has_surprise and has_wall:
        errors.append("HR 19: Hidden_Balloon × Iron_Wall 동시 금지 (PF=0, 시각+물리 이중 가림)")

    return (len(errors) == 0), errors


def check_intro_isolation(csv_row: dict) -> list[str]:
    """G8 — 도입 lv 격리. warning만 반환."""
    warnings: list[str] = []
    lv = int(csv_row["level_number"])
    active_gim = [k for k in csv_row if k.startswith("gimmick_") and int(csv_row.get(k, 0)) > 0]
    if lv in INTRO_LVS:
        new_gim = _lookup_intro_gimmick(lv)
        for g in active_gim:
            if g != new_gim:
                warnings.append(f"intro lv {lv}: {g} should be 0 (only {new_gim} expected)")
    return warnings


def _lookup_intro_gimmick(intro_lv: int) -> str | None:
    for gim, debut in BL_DEBUT_LV.items():
        if debut == intro_lv:
            return gim
    return None


# ─────────────────────────────────────────────────────
# STEP 2: FieldMap 확보
# ─────────────────────────────────────────────────────

def parse_field_map(designer_note: str) -> list[list[int]] | None:
    """designer_note 텍스트에서 [FieldMap] 섹션 파싱.
    Returns 2D list of int color codes, or None if not found.
    `..` = empty (-1)."""
    if not designer_note:
        return None
    m = re.search(r"\[FieldMap\]\s*\n([\s\S]+?)(?:\n\s*\[|\Z)", designer_note)
    if not m:
        return None
    return _parse_field_map_text(m.group(1))


def _parse_field_map_text(text: str) -> list[list[int]] | None:
    """raw 텍스트 (공백 + newline 구분 2자리 코드) → 2D 정수 리스트.
    pixelforge_levels.field_map (string) 직접 파싱에도 사용."""
    if not text:
        return None
    rows = []
    for line in text.strip().split("\n"):
        cells = line.strip().split()
        if not cells:
            continue
        row = []
        for c in cells:
            if c == "..":
                row.append(-1)
            else:
                try:
                    row.append(int(c))
                except ValueError:
                    row.append(-1)
        rows.append(row)
    return rows if rows else None


def apply_palette_mapping(field_map: list[list[int]], palette_mapping: dict | None) -> list[list[int]]:
    """raw 코드(field_map)을 palette_mapping으로 BL color index로 변환.
    palette_mapping = {'1': 8, '2': 1, ...} (1-based key → BL 1-based index).
    매핑 없는 코드는 그대로 유지."""
    if not palette_mapping:
        return field_map
    # key는 str일 수 있고 int일 수 있음
    pm = {}
    for k, v in palette_mapping.items():
        try:
            pm[int(k)] = int(v)
        except (ValueError, TypeError):
            continue
    if not pm:
        return field_map
    return [[pm.get(c, c) if c >= 0 else c for c in row] for row in field_map]


def generate_default_layout(field_rows: int, field_columns: int,
                             total_cells: int, color_dist: str) -> list[list[int]]:
    """기본 직사각형 레이아웃. color_distribution 비율대로 stripe로 채움."""
    color_counts = _parse_color_distribution(color_dist)
    cells = field_rows * field_columns
    grid = [[-1] * field_columns for _ in range(field_rows)]
    # 셀 수만큼 채움 (외곽 빈 칸 일부)
    margin_v = max(0, (cells - total_cells) // (2 * field_columns))
    flat_idx = 0
    cells_per_color = []
    for c, n in color_counts:
        cells_per_color.extend([c] * n)
    for r in range(margin_v, field_rows - margin_v):
        for col in range(field_columns):
            if flat_idx < len(cells_per_color):
                grid[r][col] = cells_per_color[flat_idx]
                flat_idx += 1
            else:
                grid[r][col] = -1
    return grid


def _parse_color_distribution(s: str) -> list[tuple[int, int]]:
    """'c6:280 c9:220 c1:140' → [(6, 280), (9, 220), (1, 140)]
    또는 'c1, c2' 같이 카운트 없는 형식도 처리 (각 0으로 반환)."""
    if not s:
        return []
    result = []
    # 공백/콤마 모두 구분자
    tokens = re.split(r"[\s,]+", s.strip())
    for tok in tokens:
        if not tok:
            continue
        m = re.match(r"c?(\d+):(\d+)", tok)
        if m:
            result.append((int(m.group(1)), int(m.group(2))))
        else:
            # 'c1' 같이 카운트 없으면 0 (호출자가 보강)
            m2 = re.match(r"c?(\d+)", tok)
            if m2:
                result.append((int(m2.group(1)), 0))
    return result


# ─────────────────────────────────────────────────────
# STEP 3: 클러스터 분석
# ─────────────────────────────────────────────────────

def extract_clusters(field_map: list[list[int]]) -> list[dict]:
    """Connected components by color. 4-connectivity."""
    rows = len(field_map)
    cols = len(field_map[0]) if rows else 0
    visited = [[False] * cols for _ in range(rows)]
    clusters: list[dict] = []
    for r in range(rows):
        for c in range(cols):
            if visited[r][c] or field_map[r][c] < 0:
                continue
            color = field_map[r][c]
            # BFS
            queue = deque([(r, c)])
            cells: list[tuple[int, int]] = []
            while queue:
                rr, cc = queue.popleft()
                if rr < 0 or rr >= rows or cc < 0 or cc >= cols:
                    continue
                if visited[rr][cc] or field_map[rr][cc] != color:
                    continue
                visited[rr][cc] = True
                cells.append((rr, cc))
                queue.extend([(rr+1, cc), (rr-1, cc), (rr, cc+1), (rr, cc-1)])
            if cells:
                clusters.append({
                    "color": color,
                    "cells": cells,
                    "size": len(cells),
                    "centroid": _centroid(cells),
                    "outline": _outline(cells, field_map),
                })
    return clusters


def _centroid(cells: list[tuple[int, int]]) -> tuple[int, int]:
    rs = [c[0] for c in cells]
    cs = [c[1] for c in cells]
    return (sum(rs) // len(rs), sum(cs) // len(cs))


def _outline(cells: list[tuple[int, int]], field_map: list[list[int]]) -> list[tuple[int, int]]:
    """Cells on cluster boundary (have ≥1 non-same neighbor)."""
    rows = len(field_map)
    cols = len(field_map[0])
    cell_set = set(cells)
    outline = []
    for r, c in cells:
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if nr < 0 or nr >= rows or nc < 0 or nc >= cols:
                outline.append((r, c)); break
            if (nr, nc) not in cell_set:
                outline.append((r, c)); break
    return outline


def assign_metaphor_priority(clusters: list[dict]) -> list[dict]:
    """가장 작은 cluster를 symbol로 marking."""
    if not clusters:
        return clusters
    total = sum(c["size"] for c in clusters)
    sizes = [c["size"] for c in clusters]
    min_size = min(sizes)
    for c in clusters:
        c["ratio"] = c["size"] / total
        c["is_symbol"] = (c["size"] == min_size)
    return clusters


def compute_non_metaphor_cells(clusters: list[dict]) -> list[tuple[int, int]]:
    """기믹 배치 가능 영역 = symbol 제외 + outline 제외 + centroid 제외."""
    non_meta = []
    for c in clusters:
        if c["is_symbol"]:
            continue
        outline_set = set(c["outline"])
        for cell in c["cells"]:
            if cell in outline_set:
                continue
            if cell == c["centroid"]:
                continue
            non_meta.append(cell)
    return non_meta


# ─────────────────────────────────────────────────────
# STEP 4: Track A — PixelFlow 패턴 차용 (v0.1: stub, debut gate만)
# ─────────────────────────────────────────────────────

def track_a(csv_row: dict, clusters: list[dict], partial_json: dict | None = None) -> list[dict]:
    """PixelFlow gimmick data가 있으면 패턴 차용. 없으면 빈 결과 (Track B에서 전부 처리)."""
    lv = int(csv_row["level_number"])
    # debut gate 통과 여부
    track_a_eligible = {
        "gimmick_wall": lv >= 121,
        "gimmick_surprise": lv >= 101,
        "gimmick_ice": lv >= 201,
    }
    # v0.1: PixelFlow JSON 직접 입력은 v0.2+에서. 현재는 Track B가 모두 처리.
    return []


# ─────────────────────────────────────────────────────
# STEP 5: Track B — BalloonFlow 고유 기믹 합성
# ─────────────────────────────────────────────────────

def track_b(csv_row: dict, clusters: list[dict], field_map: list[list[int]],
            seed_offset: int = 0) -> list[dict]:
    """7종 필드 기믹 합성. 우선순위 순서대로 배치. seed_offset으로 다중 후보.
    충돌 회피: 각 기믹은 used_cells (자신 셀 + 1셀 buffer) 회피."""
    gimmicks: list[dict] = []
    lv = int(csv_row["level_number"])
    seed = lv * 13 + 7 + seed_offset * 1009
    rng = random.Random(seed)

    non_meta = compute_non_metaphor_cells(clusters)
    used_cells: set[tuple[int, int]] = set()

    field_h = len(field_map)
    field_w = len(field_map[0]) if field_h else 0

    # 1. Iron Wall (gimmick_wall) — 구조 먼저
    cnt = int(csv_row.get("gimmick_wall", 0))
    if cnt > 0 and lv >= BL_DEBUT_LV["gimmick_wall"]:
        # designer_note에서 mode 추출
        note = str(csv_row.get("designer_note", ""))
        iw_mode = "pf_wall" if "[mode=pf_wall]" in note else "bl_outline"
        walls = place_iron_wall(clusters, cnt, rng,
                                 mode=iw_mode, field_h=field_h, field_w=field_w,
                                 purpose_type=normalize_purpose(csv_row.get("purpose_type")))
        gimmicks.extend(walls)
        _expand_used_with_buffer(walls, used_cells, buffer=0)  # wall은 자체 셀만

    # 2. Frozen Layer (gimmick_ice)
    cnt = int(csv_row.get("gimmick_ice", 0))
    if cnt > 0 and lv >= BL_DEBUT_LV["gimmick_ice"]:
        frozen = place_frozen_layer(clusters, cnt, field_map, rng,
                                     purpose_type=normalize_purpose(csv_row.get("purpose_type")))
        gimmicks.extend(frozen)
        _expand_used_with_buffer(frozen, used_cells, buffer=0)  # ice는 색상 보존

    # 3. Hidden Balloon (gimmick_surprise)
    cnt = int(csv_row.get("gimmick_surprise", 0))
    if cnt > 0 and lv >= BL_DEBUT_LV["gimmick_surprise"]:
        hb = place_hidden_balloon(clusters, cnt, non_meta, used_cells, rng, field_map,
                                   purpose_type=normalize_purpose(csv_row.get("purpose_type")))
        gimmicks.extend(hb)

    # 4. Wooden Board (gimmick_pinata) — buffer 1 (다른 기믹과 격리)
    cnt = int(csv_row.get("gimmick_pinata", 0))
    if cnt > 0 and lv >= BL_DEBUT_LV["gimmick_pinata"]:
        wb = place_wooden_board(clusters, cnt, used_cells, rng,
                                 field_h=field_h, field_w=field_w,
                                 purpose_type=normalize_purpose(csv_row.get("purpose_type")))
        gimmicks.extend(wb)
        _expand_used_with_buffer(wb, used_cells, buffer=1)

    # 5. Target Box (gimmick_pinata_box) — buffer 1
    cnt = int(csv_row.get("gimmick_pinata_box", 0))
    if cnt > 0 and lv >= BL_DEBUT_LV["gimmick_pinata_box"]:
        purpose = normalize_purpose(csv_row.get("purpose_type"))
        # v1.2.3 §7.4 [target_mode=sparse] 파싱
        note = str(csv_row.get("designer_note", ""))
        sparse_mode = "[target_mode=sparse]" in note
        tb = place_target_box(clusters, cnt, used_cells, rng,
                               purpose_type=purpose, sparse=sparse_mode)
        gimmicks.extend(tb)
        _expand_used_with_buffer(tb, used_cells, buffer=1)

    # 6. Barricade (gimmick_pin) — buffer 1
    cnt = int(csv_row.get("gimmick_pin", 0))
    if cnt > 0 and lv >= BL_DEBUT_LV["gimmick_pin"]:
        purpose = normalize_purpose(csv_row.get("purpose_type"))
        ba = place_barricade(clusters, cnt, used_cells, rng,
                              purpose_type=purpose, field_h=field_h, field_w=field_w)
        gimmicks.extend(ba)
        _expand_used_with_buffer(ba, used_cells, buffer=1)

    # 7. v1.2.10/20 Snake (gimmick_snake) — debut lv 81, buffer 1
    cnt = int(csv_row.get("gimmick_snake", 0))
    if cnt > 0 and lv >= BL_DEBUT_LV["gimmick_snake"]:
        sn = place_snake(clusters, cnt, csv_row, used_cells, rng,
                          field_h=field_h, field_w=field_w, field_map=field_map)
        gimmicks.extend(sn)
        _expand_used_with_buffer(sn, used_cells, buffer=1)

    return gimmicks


# ─────────────────────────────────────────────────────
# §7.5 Placement Violations (Hard Rule 12-16, v1.2)
# ─────────────────────────────────────────────────────

def detect_blocked_paths(balloons: list[dict], gimmicks: list[dict],
                          field_h: int, field_w: int) -> list[str]:
    """HR 12: Iron Wall + Barricade가 어떤 색의 모든 셀을 위에서 차단 시 위반.
    각 색상에 대해 적어도 1개 셀이 위에서 도달 가능해야."""
    violations = []
    blocker_cells: set[tuple[int, int]] = set()
    for g in gimmicks:
        if g.get("type") in ("Iron_Wall", "Barricade"):
            for cell in g.get("cells", []) or []:
                if isinstance(cell, (list, tuple)) and len(cell) == 2:
                    blocker_cells.add((cell[0], cell[1]))
    if not blocker_cells:
        return violations
    # 색상별로 적어도 1셀이 reachable인지 확인
    by_color: dict[int, list[tuple[int, int]]] = {}
    for b in balloons:
        by_color.setdefault(b["color"], []).append((b["row"], b["col"]))
    for color, cells in by_color.items():
        any_reachable = False
        for r, c in cells:
            # 위쪽 같은 column에 blocker 있는지
            blocked = any((br < r and bc == c) for br, bc in blocker_cells)
            if not blocked:
                any_reachable = True
                break
        if not any_reachable:
            violations.append(f"HR12: color c{color} all cells blocked from top by Iron_Wall/Barricade")
    return violations


def verify_hidden_color_supply(gimmicks: list[dict], balloons: list[dict]) -> list[str]:
    """HR 13: Hidden Balloon의 hidden_color는 다트 공급에 존재해야.
    balloons의 color 집합이 다트 공급. hidden_color가 이 집합에 있어야."""
    violations = []
    balloon_colors = set(b["color"] for b in balloons)
    for g in gimmicks:
        if g.get("type") == "Hidden_Balloon":
            hc = g.get("hidden_color")
            if hc is not None and hc not in balloon_colors:
                violations.append(f"HR13: Hidden_Balloon hidden_color c{hc} not in dart supply")
                break
    return violations


def verify_target_color_exists(gimmicks: list[dict], balloons: list[dict]) -> list[str]:
    """HR 15: Target Box의 target_color는 보드 풍선 색에 존재해야."""
    violations = []
    balloon_colors = set(b["color"] for b in balloons)
    for g in gimmicks:
        if g.get("type") == "Target_Box":
            tc = g.get("target_color")
            if tc is not None and tc not in balloon_colors:
                violations.append(f"HR15: Target_Box target_color c{tc} not on board")
    return violations


def verify_solid_invariant(gimmicks: list[dict]) -> list[str]:
    """HR 16: 1셀당 최대 1 solid 기믹 (WB/BR/Target/IW non-outline)."""
    violations = []
    cell_owner: dict[tuple[int, int], str] = {}
    SOLID_TYPES = {"Wooden_Board", "Barricade", "Target_Box"}
    for g in gimmicks:
        typ = g.get("type")
        # Iron_Wall은 outline 모드에서 colocate 허용 (색상 보존)
        if typ not in SOLID_TYPES:
            continue
        cells = g.get("cells", []) or []
        if not cells and "row" in g:
            cells = [(g["row"], g["col"])]
        for cell in cells:
            if isinstance(cell, (list, tuple)) and len(cell) == 2:
                key = (cell[0], cell[1])
                if key in cell_owner and cell_owner[key] != typ:
                    violations.append(
                        f"HR16: cell ({key[0]},{key[1]}) has both {cell_owner[key]} and {typ}"
                    )
                cell_owner[key] = typ
    return violations[:5]  # 최대 5개만 보고


def verify_chain_dag(chain_groups: list[dict]) -> list[str]:
    """HR 8: chainGroupId DAG (acyclic).
    각 chain group 간 의존성 graph. 같은 color hint를 공유하는 그룹이 서로 인접 시 사이클 가능.
    단순 검증: 그룹 id 중복 + group_id 순서가 단조 증가하는지.
    """
    violations = []
    if not chain_groups:
        return violations
    seen_ids = set()
    for g in chain_groups:
        gid = g.get("chainGroupId")
        if gid is None:
            continue
        if gid in seen_ids:
            violations.append(f"HR8: chainGroupId {gid} duplicated (DAG violated)")
        seen_ids.add(gid)
    # link_n 합 검증 — 각 그룹 link_n의 합이 원본 gimmick_chain 값과 같아야 (큐 명세 §5.3.1)
    # 본 함수는 group 자체만 검증; 합산 검증은 _complete_one_seed에서
    return violations


def validate_dart_cap(pkg: int, total_darts: int) -> list[str]:
    """HR 7: PKG별 다트 cap 검증. warning만."""
    cap = PKG_DART_CAP.get(pkg, 99999)
    if total_darts > cap:
        return [f"HR7: PKG {pkg} total_darts {total_darts} > cap {cap}"]
    return []


def verify_placement(balloons: list[dict], gimmicks: list[dict],
                     field_h: int, field_w: int,
                     chain_groups: list[dict] | None = None,
                     pkg: int = 0,
                     total_darts: int = 0) -> list[str]:
    """§7.5 통합 검증. HR 7, 8, 12-16."""
    violations = []
    violations.extend(detect_blocked_paths(balloons, gimmicks, field_h, field_w))
    violations.extend(verify_hidden_color_supply(gimmicks, balloons))
    violations.extend(verify_target_color_exists(gimmicks, balloons))
    violations.extend(verify_solid_invariant(gimmicks))
    if chain_groups:
        violations.extend(verify_chain_dag(chain_groups))
    if pkg > 0 and total_darts > 0:
        violations.extend(validate_dart_cap(pkg, total_darts))
    return violations


def _expand_used_with_buffer(placed: list[dict], used: set, buffer: int = 1) -> None:
    """기믹 셀 + buffer 셀 만큼 used에 추가. 다음 기믹이 인접하지 못하게."""
    new_cells = set()
    for g in placed:
        cells = []
        if "cells" in g:
            for c in g.get("cells", []):
                if isinstance(c, (list, tuple)) and len(c) == 2:
                    cells.append((c[0], c[1]))
        elif "row" in g and "col" in g:
            cells.append((g["row"], g["col"]))
        for r, c in cells:
            new_cells.add((r, c))
            if buffer > 0:
                for dr in range(-buffer, buffer + 1):
                    for dc in range(-buffer, buffer + 1):
                        new_cells.add((r + dr, c + dc))
    used.update(new_cells)


def place_iron_wall(clusters: list[dict], count: int, rng: random.Random,
                    mode: str = "bl_outline",
                    field_h: int = 0, field_w: int = 0,
                    purpose_type: str = "normal") -> list[dict]:
    """gimmick_wall: v1.2.3 mode-split, v1.2.6 trimodal Y in pf_wall.
    mode='bl_outline' (default): count=1 → 전 outline 연속선, count>=2 → +분할벽.
    mode='pf_wall': PF 패턴 (2×2 72% / 4×2 16%), v1.2.6 trimodal Y."""
    if not clusters:
        return []
    walls = []
    _iw_purpose = purpose_type

    if mode == "pf_wall" and field_h > 0:
        # PF 모드: cluster 외부, 상단 위치
        for i in range(count):
            # v1.2.16 + v1.2.21 (PO 결정): 정사각 3종만 (1×1, 2×2, 3×3).
            # PF 비정사각 (2×1·1×2·4×2) 차용 X — 4×2 87%는 2×2 로 대체.
            # PF picked 분포 정합: 2×2 87% / 3×3 8% / 1×1 3% (실측).
            r_pick = rng.random()
            if r_pick < 0.87:
                bbox = (2, 2)
            elif r_pick < 0.95:
                bbox = (3, 3)
            else:
                bbox = (1, 1)
            # 모든 셀 후보
            cluster_cells_set = set()
            for c in clusters:
                cluster_cells_set.update(c["cells"])
            candidates = []
            for r in range(field_h):
                for c in range(field_w):
                    if (r, c) not in cluster_cells_set:
                        candidates.append((r, c))
            if not candidates:
                continue
            # v1.2.6 §7.7.3: trimodal Y (top/mid/bot)
            _iw_diff = normalize_purpose(_iw_purpose)
            _y_target = iron_wall_y_v2(_iw_diff, rng)
            scored = score_placement_candidates(candidates, "Iron_Wall", field_h, field_w,
                                                 y_target_override=_y_target)
            top = scored[: max(1, len(scored) // 5)]
            anchor = top[rng.randrange(min(5, len(top)))][0]
            # bbox 셀들
            cells = []
            for dr in range(bbox[0]):
                for dc in range(bbox[1]):
                    cell = (anchor[0] + dr, anchor[1] + dc)
                    if 0 <= cell[0] < field_h and 0 <= cell[1] < field_w:
                        cells.append(cell)
            if cells:
                walls.append({
                    "type": "Iron_Wall",
                    "structure_id": i + 1,
                    "cells": cells,
                    "shape": "pf_block",
                    "mode": "pf_wall",
                    "bbox": list(bbox),
                    "life": 0,
                })
        return walls

    # bl_outline 모드 (default): 디자이너 의도 보존 — 전 outline 사용
    sorted_clusters = sorted(clusters, key=lambda c: c["size"], reverse=True)
    # 1번째: 가장 큰 cluster의 전 outline
    if count >= 1:
        c = sorted_clusters[0]
        walls.append({
            "type": "Iron_Wall",
            "structure_id": 1,
            "cells": list(c["outline"]),
            "shape": "outline",
            "mode": "bl_outline",
            "life": 0,
            "color": c["color"],
        })
    # 추가: 다음 큰 cluster들의 outline
    for i, c in enumerate(sorted_clusters[1:count], start=2):
        walls.append({
            "type": "Iron_Wall",
            "structure_id": i,
            "cells": list(c["outline"]),
            "shape": "cluster_boundary",
            "mode": "bl_outline",
            "life": 0,
            "color": c["color"],
        })
    return walls


def place_frozen_layer(clusters: list[dict], count: int, field_map: list[list[int]],
                       rng: random.Random, purpose_type: str = "normal") -> list[dict]:
    """gimmick_ice: v1.2.3 — PF 데이터 기반 block_size + counter + clip_rect.
    n_instances = max(1, round(count / 64)), block_size 결정, cluster bbox clipping.
    counter = cells × frozen_layer_health_per_cell_v2(difficulty) — v1.2.6 난이도별."""
    _fl_difficulty = normalize_purpose(purpose_type)
    if not clusters or count == 0:
        return []

    n_instances = max(1, round(count / 64))
    cells_per = count // n_instances
    # PF block_size 분포: <16→(4,4), <64→(8,8), <144→(12,12), else (16,16)
    if cells_per < 16:
        bbox_size = (4, 4)
    elif cells_per < 64:
        bbox_size = (8, 8)
    elif cells_per < 144:
        bbox_size = (12, 12)
    else:
        bbox_size = (16, 16)

    field_h = len(field_map)
    field_w = len(field_map[0]) if field_h else 0

    result = []
    used_cells_for_ice: set[tuple[int, int]] = set()
    for i in range(n_instances):
        # 후보 = 모든 non-empty cells (cluster 무관, FL은 어디든 OK)
        # 단, 이미 ice 처리된 셀 제외
        candidates = []
        for r in range(field_h):
            for c in range(field_w):
                if field_map[r][c] >= 0 and (r, c) not in used_cells_for_ice:
                    candidates.append((r, c))
        if not candidates:
            break
        # PF 위치 편중 적용 (Y=0.45 center, X=0.50)
        scored = score_placement_candidates(candidates, "Frozen_Layer", field_h, field_w)
        if not scored:
            break
        # top-N pool에서 random pick (다양성)
        top_pool = scored[: max(1, len(scored) // 4)]
        pick_idx = rng.randrange(min(len(top_pool), 5))
        anchor = top_pool[pick_idx][0]

        # clip rectangle to cluster bbox
        actual_bbox, cells = clip_rect_to_cluster_bbox(anchor, bbox_size, clusters)
        if not cells:
            continue
        # 이미 사용된 셀 제외
        cells = [c for c in cells if c not in used_cells_for_ice]
        if not cells:
            continue
        used_cells_for_ice.update(cells)

        # counter 계산 — v1.2.6 §7.7.4 난이도별 비대칭 분포
        per_cell_health = frozen_layer_health_per_cell_v2(_fl_difficulty, rng)
        counter_val = len(cells) * per_cell_health

        result.append({
            "type": "Frozen_Layer",
            "cells": cells,
            "block_size": list(actual_bbox),
            "counter": counter_val,
            "life_modifier": 1,
            "covers_all": False,
        })
    return result


def place_hidden_balloon(clusters: list[dict], count: int,
                         non_meta: list[tuple[int, int]],
                         used: set[tuple[int, int]],
                         rng: random.Random,
                         field_map: list[list[int]],
                         purpose_type: str = "normal") -> list[dict]:
    """gimmick_surprise: 메타포 보존 — cluster interior 에서 cluster 비례 sampling.
    v1.2.16+: 1×1 only. v1.2.6+ pct_cap_v2 강제 — count > cap × board_balloon_cells 면 자동 감소.
    outline 인접 셀은 제외 (윤곽 보존)."""
    if not clusters or count == 0:
        return []
    # v1.2.6 §7.7.2 pct_cap 강제 — board_balloon_cells 의 cap% 초과 시 감소
    board_balloon_cells = sum(c["size"] for c in clusters if not c["is_symbol"])
    diff = normalize_purpose(purpose_type)
    pct_cap = hidden_balloon_pct_cap_v2(diff)
    max_allowed = max(1, int(board_balloon_cells * pct_cap))
    if count > max_allowed:
        log.warning("place_hidden_balloon: count %d > cap (%.0f%% × %d = %d) → 감소",
                    count, pct_cap * 100, board_balloon_cells, max_allowed)
        count = max_allowed
    non_meta_set = set(non_meta) - used
    non_symbol = [c for c in clusters if not c["is_symbol"]]
    if not non_symbol:
        return []
    # cluster당 quota (size 비례)
    total_avail = sum(c["size"] for c in non_symbol)
    quotas = [int(round(count * c["size"] / total_avail)) for c in non_symbol]
    diff = count - sum(quotas)
    if diff != 0 and quotas:
        quotas[0] += diff
    result = []
    for c, q in zip(non_symbol, quotas):
        if q <= 0:
            continue
        outline_set = set(c["outline"])
        cluster_set = set(c["cells"])
        # interior = 8-이웃이 모두 cluster 내부인 셀
        interior_cells = []
        for cell in c["cells"]:
            if cell in outline_set or cell in used:
                continue
            r, col = cell
            interior_neighbors = sum(
                1 for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                if (dr, dc) != (0, 0) and (r + dr, col + dc) in cluster_set
            )
            # 6+ 이웃 cluster 내부 = "dense interior"
            if interior_neighbors >= 6:
                interior_cells.append(cell)
        # interior가 부족하면 non_outline으로 fallback
        if len(interior_cells) < q:
            non_outline = [cell for cell in c["cells"]
                           if cell not in outline_set and cell not in used
                           and cell != c["centroid"]]
            interior_cells = interior_cells + [cell for cell in non_outline
                                                if cell not in interior_cells]
        if not interior_cells:
            continue
        n = min(q, len(interior_cells))
        sampled = rng.sample(interior_cells, n)
        for cell in sampled:
            r, col = cell
            result.append({
                "type": "Hidden_Balloon",
                "row": r, "col": col,
                "hidden_color": field_map[r][col],
                "life": 1,
            })
            used.add(cell)
    return result


def place_wooden_board(clusters: list[dict], count: int,
                       used: set[tuple[int, int]],
                       rng: random.Random,
                       field_h: int = 0, field_w: int = 0,
                       purpose_type: str = "normal") -> list[dict]:
    """gimmick_pinata: v1.2.3 routing + v1.2.6 bimodal HP (난이도별 spike chance).
    centroid 회피, redundant interior 우선, 78% 소HP + 17% 대HP."""
    _wb_difficulty = normalize_purpose(purpose_type)
    if not clusters or count == 0:
        return []
    sorted_clusters = sorted(clusters, key=lambda c: c["size"], reverse=True)
    result = []
    for c in sorted_clusters:
        if c["is_symbol"]:
            continue
        if len(result) >= count:
            break
        # v1.2.9 §7.7.1 — PF 사이즈 분포. cluster 가 너무 작으면 fallback 1×1 / 2×2.
        proposed_size = wooden_board_size_v3(rng)
        if c["size"] < proposed_size[0] * proposed_size[1] * 2:
            # cluster 가 작으면 더 작은 사이즈
            size = (1, 1) if c["size"] < 8 else (2, 2)
        else:
            size = proposed_size
        cluster_set = set(c["cells"])
        outline_set = set(c["outline"])
        # interior 후보 (8-이웃 7+ cluster)
        candidates = []
        for cell in c["cells"]:
            if cell in outline_set or cell == c["centroid"] or cell in used:
                continue
            r, col = cell
            interior_count = sum(
                1 for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                if (dr, dc) != (0, 0) and (r + dr, col + dc) in cluster_set
            )
            if interior_count >= 7:
                candidates.append(cell)
        if not candidates:
            candidates = [cell for cell in c["cells"]
                          if cell not in outline_set and cell != c["centroid"]
                          and cell not in used]
        if not candidates:
            continue
        # v1.2.3: score_placement_candidates 라우팅
        scored = score_placement_candidates(candidates, "Wooden_Board",
                                            field_h or 50, field_w or 40, cluster=c)
        # find_first_valid로 size bbox 안착
        excluded = outline_set | {c["centroid"]} | used
        start_cell = find_first_valid(scored, size, c["cells"], excluded)
        if start_cell is None:
            # fallback: top scored 셀에서 단일 1×1
            start_cell = scored[0][0] if scored else None
            if start_cell is None:
                continue
            size = (1, 1)
        cells = _expand_rect(start_cell, size, c["cells"], used)
        if not cells:
            continue
        # v1.2.6 §7.7.1 bimodal HP (난이도별 spike chance)
        life = wooden_board_hp_v2(len(cells), _wb_difficulty, rng)
        for cell in cells:
            used.add(cell)
        result.append({
            "type": "Wooden_Board",
            "row": cells[0][0], "col": cells[0][1],
            "cells": cells,
            "size": list(size),
            "color": c["color"],
            "life": life,
            "life_adjustable": True,  # mod-10 정합 시 +5/+15 가능
        })
    return result


def _expand_rect(start: tuple[int, int], size: tuple[int, int],
                 cluster_cells: list[tuple[int, int]],
                 used: set[tuple[int, int]]) -> list[tuple[int, int]]:
    """centroid에서 size (h, w) 직사각형으로 확장. cluster 내 + 미사용 셀만."""
    h, w = size
    r0, c0 = start
    cluster_set = set(cluster_cells)
    cells = []
    for dr in range(h):
        for dc in range(w):
            cell = (r0 + dr, c0 + dc)
            if cell in cluster_set and cell not in used:
                cells.append(cell)
    return cells if len(cells) == h * w else (cells[:1] if cells else [])


def place_target_box(clusters: list[dict], count: int,
                     used: set[tuple[int, int]], rng: random.Random,
                     purpose_type: str = "normal",
                     sparse: bool = False) -> list[dict]:
    """gimmick_pinata_box: v1.2.3 — box_size by purpose + target_count + per_target_life.
    sparse=True: PF egg pattern (box 안에 4 of N target만, 나머지는 빈 셀)."""
    if not clusters or count == 0:
        return []

    # v1.2.6 §7.7.5: 난이도별 (box_size, eggs) 동시 결정
    # tutorial 2×2/4 → super_hard 3×3/9 단조 증가
    _diff = normalize_purpose(purpose_type)
    box_size, target_count = target_box_size_v2(_diff, rng)

    eligible = [c for c in clusters if not c["is_symbol"]]
    if not eligible:
        return []
    weights = [c["size"] ** 0.5 for c in eligible]
    result = []
    attempted = set()
    for _ in range(count * 3):
        if len(result) >= count:
            break
        idx = _weighted_choice(eligible, weights, rng)
        if idx in attempted:
            continue
        attempted.add(idx)
        c = eligible[idx]
        # centroid 우선 (Target_Box는 메타포 정점 의도)
        anchor = c["centroid"]
        # box 영역 확보 (centroid 중심)
        bh, bw = box_size
        r0 = max(0, anchor[0] - bh // 2)
        c0 = max(0, anchor[1] - bw // 2)
        cluster_set = set(c["cells"])
        box_cells = []
        for dr in range(bh):
            for dc in range(bw):
                cell = (r0 + dr, c0 + dc)
                if cell in cluster_set and cell not in used:
                    box_cells.append(cell)
        if len(box_cells) < bh * bw // 2:  # 절반 이상 채워야
            continue

        # sparse mode: box 셀 중 target_count 만큼만 활성 (나머지는 빈 셀)
        if sparse and len(box_cells) > target_count:
            # uniform sampling target_count cells
            active_cells = rng.sample(box_cells, target_count)
        else:
            active_cells = box_cells

        # v1.2.6+ 난이도별 per-target HP (audit 2026-05-26)
        per_target_life = target_box_per_target_life_v2(_diff, rng)
        target_color = _adjacent_color(c, clusters)
        result.append({
            "type": "Target_Box",
            "row": active_cells[0][0], "col": active_cells[0][1],
            "cells": active_cells,
            "box_size": list(box_size),
            "target_count": target_count,
            "per_target_life": per_target_life,
            "target_color": target_color,
            "life": per_target_life * target_count,
            "color": c["color"],
            "sparse": sparse,
        })
        used.update(active_cells)
    return result


def _weighted_choice(items: list, weights: list[float], rng: random.Random) -> int:
    """weighted random pick index."""
    total = sum(weights)
    if total <= 0:
        return rng.randrange(len(items))
    r = rng.uniform(0, total)
    acc = 0.0
    for i, w in enumerate(weights):
        acc += w
        if r <= acc:
            return i
    return len(items) - 1


def _adjacent_color(cluster: dict, all_clusters: list[dict]) -> int:
    """가장 가까운 cluster의 색 (자기 자신 제외)."""
    others = [c for c in all_clusters if c["color"] != cluster["color"]]
    if not others:
        return cluster["color"]
    cr, cc = cluster["centroid"]
    min_d = float("inf")
    best = others[0]
    for o in others:
        or_, oc = o["centroid"]
        d = (cr - or_) ** 2 + (cc - oc) ** 2
        if d < min_d:
            min_d = d
            best = o
    return best["color"]


def place_barricade(clusters: list[dict], count: int,
                    used: set[tuple[int, int]], rng: random.Random,
                    purpose_type: str = "normal",
                    field_h: int = 0, field_w: int = 0) -> list[dict]:
    """gimmick_pin: v1.2.3 — adjacent_inner placement + multi-cell length.
    PF Door Count med=50 → length=clamp(round(Count/10), 3, 8).
    outline 자체가 아닌 adjacent_inner (1셀 안쪽) corner 영역."""
    if not clusters or count == 0:
        return []

    # adjacent_inner corner 영역 후보
    candidates: list[tuple[int, int]] = []
    for c in clusters:
        outline = c["outline"]
        if len(outline) < 4:
            continue
        adjacent_inner = compute_adjacent_inner_cells(outline, c["cells"])
        corner_inner = identify_corner_regions(adjacent_inner, outline)
        candidates.extend(corner_inner)
    candidates = [c for c in candidates if c not in used]
    if not candidates:
        return []

    # score 적용 + furthest_apart_scored
    scored = score_placement_candidates(candidates, "Barricade", field_h, field_w)
    selected_anchors = furthest_apart_scored(scored, count)
    result = []
    for anchor in selected_anchors:
        if anchor in used:
            continue
        # v1.2.6 §7.7.6 난이도별 단조 증가 length
        length = barricade_length_v2(purpose_type, rng)
        # v1.2.14 HP × Length 독립 — intent 매핑 (purpose → fast/normal/slow/boss)
        _br_intent = difficulty_to_intent(purpose_type, "Barricade")
        # outline 평행 방향 (간략화: 가까운 outline 따라 1×N 직선)
        cells = _lay_pin_cells(anchor, length, clusters, used)
        if not cells:
            continue
        used.update(cells)
        # v1.2.14: HP 는 length 와 독립 — intent 로 ratio 결정
        _br_hp = barricade_hp_from_length(len(cells), _br_intent, rng)
        result.append({
            "type": "Barricade",
            "row": cells[0][0], "col": cells[0][1],
            "cells": cells,
            "length": len(cells),
            "life": _br_hp,
            "intent": _br_intent,
        })
    return result


def _lay_pin_cells(anchor: tuple[int, int], length: int,
                   clusters: list[dict],
                   used: set[tuple[int, int]]) -> list[tuple[int, int]]:
    """anchor에서 outline 평행 방향으로 length개 셀 배치.
    8 방향 시도 + cluster 무관 placement (PF Barricade는 outline-tangent)."""
    nearest_cluster = None
    min_d = float("inf")
    for c in clusters:
        cr, cc = c["centroid"]
        d = (anchor[0] - cr) ** 2 + (anchor[1] - cc) ** 2
        if d < min_d:
            min_d = d
            nearest_cluster = c
    if not nearest_cluster:
        return [anchor]
    cluster_set = set(nearest_cluster["cells"])
    # 8 방향 시도 (대각선 포함) — best length 방향 채택
    directions = [(0, 1), (1, 0), (0, -1), (-1, 0),
                  (1, 1), (1, -1), (-1, 1), (-1, -1)]
    best_cells = [anchor]
    for dr, dc in directions:
        cells = [anchor]
        for step in range(1, length):
            nxt = (anchor[0] + dr * step, anchor[1] + dc * step)
            if nxt in cluster_set and nxt not in used:
                cells.append(nxt)
            else:
                break
        if len(cells) > len(best_cells):
            best_cells = cells
        if len(best_cells) >= length:
            break
    # 그래도 1개라면 anchor 주변 cluster 셀들로 fallback (인접 셀 BFS)
    if len(best_cells) < min(2, length):
        from collections import deque as _deque
        queue = _deque([anchor])
        visited = {anchor}
        fallback = [anchor]
        while queue and len(fallback) < length:
            r, c = queue.popleft()
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nb = (r + dr, c + dc)
                if nb in cluster_set and nb not in visited and nb not in used:
                    visited.add(nb)
                    fallback.append(nb)
                    queue.append(nb)
                    if len(fallback) >= length:
                        break
        if len(fallback) > len(best_cells):
            best_cells = fallback
    return best_cells


def _find_corners(outline: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """outline 셀 중 코너 (2개 이상 이웃 outline)."""
    outline_set = set(outline)
    corners = []
    for r, c in outline:
        neighbor_count = sum(
            1 for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]
            if (r+dr, c+dc) in outline_set
        )
        if neighbor_count <= 2:  # corner: 0~2 neighbors
            corners.append((r, c))
    return corners


def _max_distance_n(cells: list[tuple[int, int]], n: int,
                    used: set[tuple[int, int]]) -> list[tuple[int, int]]:
    """N개를 서로 max distance로."""
    available = [c for c in cells if c not in used]
    if not available:
        return []
    if len(available) <= n:
        return available
    selected = [available[0]]
    while len(selected) < n:
        best = None
        best_d = -1.0
        for cell in available:
            if cell in selected:
                continue
            min_d = min((cell[0] - s[0]) ** 2 + (cell[1] - s[1]) ** 2 for s in selected)
            if min_d > best_d:
                best_d = min_d
                best = cell
        if best is None:
            break
        selected.append(best)
    return selected


# ─────────────────────────────────────────────────────
# Chain Group (큐 측이지만 본 알고리즘이 개수 결정)
# ─────────────────────────────────────────────────────

def assign_chain_groups(csv_row: dict, clusters: list[dict]) -> list[dict]:
    chain_count = int(csv_row.get("gimmick_chain", 0))
    if chain_count == 0:
        return []
    purpose = normalize_purpose(csv_row.get("purpose_type"))
    link_ns = _split_chain_link_n(chain_count, purpose)
    groups = []
    for i, n in enumerate(link_ns):
        candidates = _propose_chain_candidates(clusters, n, n_candidates=4)
        groups.append({
            "chainGroupId": i + 1,
            "link_n": n,
            "color_hint": clusters[0]["color"] if clusters else None,
            "candidate_positions": candidates,
            "final_position": None,  # 큐생성기 §5.3.2 결정
        })
    return groups


def _split_chain_link_n(total: int, purpose: str) -> list[int]:
    """95%/5% 룰. 큐 명세 §5.3.1."""
    if total <= 0:
        return []
    if total == 2:
        return [2]
    if total == 3:
        return [3]
    if total % 2 == 0:
        return [2] * (total // 2)
    return [2] * ((total - 3) // 2) + [3]


def _propose_chain_candidates(clusters: list[dict], link_n: int, n_candidates: int) -> list[list[list[int]]]:
    """클러스터당 1개 후보 (가장 큰 N개)."""
    if not clusters:
        return []
    sorted_c = sorted(clusters, key=lambda c: c["size"], reverse=True)
    candidates = []
    for c in sorted_c[:n_candidates]:
        if len(c["cells"]) < link_n:
            continue
        # 인접한 link_n개 셀
        for cell in c["cells"]:
            chain = _grow_adjacent_chain(cell, c["cells"], link_n)
            if len(chain) == link_n:
                candidates.append([[r, col] for r, col in chain])
                break
    return candidates


def _grow_adjacent_chain(start: tuple[int, int], cluster_cells: list[tuple[int, int]],
                         length: int) -> list[tuple[int, int]]:
    cluster_set = set(cluster_cells)
    chain = [start]
    visited = {start}
    while len(chain) < length:
        added = False
        for cell in list(chain):
            r, c = cell
            for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nb = (r+dr, c+dc)
                if nb in cluster_set and nb not in visited:
                    chain.append(nb)
                    visited.add(nb)
                    added = True
                    if len(chain) >= length:
                        return chain
                    break
            if added:
                break
        if not added:
            break
    return chain


# ─────────────────────────────────────────────────────
# STEP 6: mod-10 정합
# ─────────────────────────────────────────────────────

def build_balloons(field_map: list[list[int]], gimmicks: list[dict]) -> list[dict]:
    """field_map의 비-기믹 셀을 풍선으로."""
    used_cells: set[tuple[int, int]] = set()
    for g in gimmicks:
        if "cells" in g:
            for cell in g["cells"]:
                if isinstance(cell, (list, tuple)) and len(cell) == 2:
                    used_cells.add(tuple(cell))
        elif "row" in g and "col" in g:
            used_cells.add((g["row"], g["col"]))

    balloons = []
    rows = len(field_map)
    cols = len(field_map[0]) if rows else 0
    for r in range(rows):
        for c in range(cols):
            if field_map[r][c] < 0:
                continue
            if (r, c) in used_cells:
                continue
            balloons.append({
                "row": r, "col": c,
                "color": field_map[r][c],
                "life": 1,
            })
    return balloons


def compute_color_darts(balloons: list[dict], gimmicks: list[dict]) -> dict[int, int]:
    """색상별 다트 = 풍선 + 기믹 라이프 (같은 색)."""
    color_darts: dict[int, int] = defaultdict(int)
    for b in balloons:
        color_darts[b["color"]] += b["life"]
    for g in gimmicks:
        c = g.get("color")
        if c is None:
            continue
        life = g.get("life", 0)
        if isinstance(life, list):
            life = sum(life)
        if life > 0:
            color_darts[c] += life
    return dict(color_darts)


def reconcile_mod10(color_darts: dict[int, int],
                    balloons: list[dict],
                    gimmicks: list[dict]) -> tuple[dict[int, int], list[str]]:
    """색상별 + 전체 10배수 정합. 라이프 우선 조정 → 부족 시 풍선 라이프 +1로 마무리."""
    warnings = []
    for color, total in list(color_darts.items()):
        rem = total % 10
        if rem == 0:
            continue
        delta = 10 - rem  # 부족분
        # 우선순위 1: Wooden Board 라이프 + (±2 가능)
        wb = [g for g in gimmicks if g.get("type") == "Wooden_Board" and g.get("color") == color]
        wb_capacity = len(wb) * 2
        if wb and wb_capacity >= delta:
            remain = delta
            for g in wb:
                if remain <= 0:
                    break
                add = min(2, remain)
                g["life"] = g.get("life", 0) + add
                remain -= add
            color_darts[color] = total + delta
            continue
        # 우선순위 2: Wooden Board로 일부만 충당 가능
        partial = 0
        if wb:
            for g in wb:
                add = min(2, delta - partial)
                if add <= 0:
                    break
                g["life"] = g.get("life", 0) + add
                partial += add
            color_darts[color] = total + partial
            delta -= partial
            if delta == 0:
                continue
        # 우선순위 3: 해당 색 풍선의 life +1 (delta개 풍선만)
        color_balloons = [b for b in balloons if b["color"] == color]
        if len(color_balloons) >= delta:
            # 결정성: row, col 정렬 후 앞에서부터 delta개에 +1
            sorted_b = sorted(color_balloons, key=lambda b: (b["row"], b["col"]))
            for b in sorted_b[:delta]:
                b["life"] = b.get("life", 1) + 1
            color_darts[color] = total + delta
        else:
            warnings.append(f"mod10 unrecoverable: color={color} total={total} rem={rem} delta={delta} balloons_avail={len(color_balloons)}")
    return color_darts, warnings


# ─────────────────────────────────────────────────────
# STEP 7: 메타포 보존 점수
# ─────────────────────────────────────────────────────

def metaphor_score(original_field: list[list[int]],
                   gimmicks: list[dict],
                   clusters: list[dict],
                   image_grid: list[list[int]] | None = None) -> float:
    """0-1 점수. P1-P5 술어 + 더 엄격한 평가 (v0.3).
    이전 버전이 0.99-1.0 너무 쉽게 나오던 문제 해결."""
    if not clusters:
        return 1.0
    score = 0.0
    outline_cells = set()
    for c in clusters:
        outline_cells.update(c["outline"])
    used_by_gim = set()
    iron_wall_cells = set()
    for g in gimmicks:
        cells: list[tuple[int, int]] = []
        if "cells" in g:
            for cell in g.get("cells", []):
                if isinstance(cell, (list, tuple)) and len(cell) == 2:
                    cells.append((cell[0], cell[1]))
        elif "row" in g and "col" in g:
            cells.append((g["row"], g["col"]))
        used_by_gim.update(cells)
        if g.get("type") == "Iron_Wall":
            iron_wall_cells.update(cells)

    # P1: outline 침범 — Iron Wall 제외 + 엄격한 페널티 (외곽 1셀당 -1)
    non_iron_outline_used = (outline_cells & used_by_gim) - iron_wall_cells
    if outline_cells:
        # 엄격: 침범 비율의 제곱 (작은 침범도 강하게 페널티)
        violation_ratio = len(non_iron_outline_used) / len(outline_cells)
        p1 = max(0.0, 1.0 - violation_ratio * 2.0)  # 50% 침범 = 0점
    else:
        p1 = 1.0
    score += 0.35 * p1

    # P2: symbol cluster intact (절대 침범 금지 — 1셀이라도 침범 시 큰 페널티)
    symbol_clusters = [c for c in clusters if c["is_symbol"]]
    if symbol_clusters:
        symbol_cells = set()
        for sc in symbol_clusters:
            symbol_cells.update(sc["cells"])
        symbol_violated = len(symbol_cells & used_by_gim)
        # 침범 셀 1개당 5% 감점 (5셀 침범 = 25% 감점)
        p2 = max(0.0, 1.0 - symbol_violated * 0.05)
    else:
        p2 = 1.0
    score += 0.25 * p2

    # P3: centroid 보존 (Target_Box만 허용)
    centroids = set(c["centroid"] for c in clusters)
    centroid_used_by_non_allowed = set()
    for g in gimmicks:
        if g.get("type") in ("Hidden_Balloon", "Target_Box"):
            continue
        if "row" in g and "col" in g:
            cell = (g["row"], g["col"])
            if cell in centroids:
                centroid_used_by_non_allowed.add(cell)
        for cell in g.get("cells", []) or []:
            if isinstance(cell, (list, tuple)) and tuple(cell) in centroids:
                centroid_used_by_non_allowed.add(tuple(cell))
    p3 = 1.0 - (len(centroid_used_by_non_allowed) / max(1, len(centroids)))
    score += 0.15 * p3

    # P4: cluster 형태 보존 — 변경 셀 비율
    total_cells = sum(c["size"] for c in clusters)
    if total_cells > 0:
        # 의도적으로 색이 변경된 셀 (Iron Wall, Wooden Board, Barricade, Target Box)
        # Hidden Balloon, Frozen Layer는 색상 정보 보존
        truly_modified = set()
        for g in gimmicks:
            if g.get("type") in ("Hidden_Balloon", "Frozen_Layer"):
                continue
            if "row" in g and "col" in g:
                truly_modified.add((g["row"], g["col"]))
            for cell in g.get("cells", []) or []:
                if isinstance(cell, (list, tuple)) and len(cell) == 2:
                    truly_modified.add((cell[0], cell[1]))
        modify_ratio = len(truly_modified) / total_cells
        # 5% 이하 = 1.0, 20% 이상 = 0
        p4 = max(0.0, min(1.0, 1.0 - (modify_ratio - 0.05) / 0.15))
    else:
        p4 = 1.0
    score += 0.15 * p4

    # P5: 가시성 — 기믹 분포 균형 (한쪽에 몰림 페널티)
    if used_by_gim and total_cells > 50:
        rs = [c[0] for c in used_by_gim]
        cs = [c[1] for c in used_by_gim]
        if len(rs) > 1:
            mean_r = sum(rs) / len(rs)
            var_r = sum((r - mean_r) ** 2 for r in rs) / len(rs)
            mean_c = sum(cs) / len(cs)
            var_c = sum((c - mean_c) ** 2 for c in cs) / len(cs)
            field_max = max(max(rs) - min(rs), max(cs) - min(cs), 1)
            p5 = min(1.0, (var_r + var_c) ** 0.5 / (field_max / 3))
        else:
            p5 = 1.0
    else:
        p5 = 1.0
    score += 0.05 * p5

    # P6 (NEW v0.4): 이미지 기반 importance — 희소 색 침범 페널티
    # image_grid가 있을 때만 추가 평가. 가중치 0.05.
    p6 = 1.0
    if image_grid:
        try:
            penalty = image_metaphor_penalty(image_grid, original_field, gimmicks)
            # penalty 0 = 완벽, 0.5+ = 희소색 침범 심각
            p6 = max(0.0, 1.0 - penalty * 1.5)  # 2/3 침범 = 0
        except Exception:
            p6 = 1.0
    score += 0.05 * p6

    return min(1.0, max(0.0, score))


# ─────────────────────────────────────────────────────
# Score 함수 (전체)
# ─────────────────────────────────────────────────────

def compute_hp_visual_gap_score(gimmicks: list[dict], total_cells: int) -> tuple[float, list[str]]:
    """§12 라인 1275-1283: 셀% vs HP% gap.
    HP-heavy 기믹의 시각적 셀 점유 대비 다트 부담 비율 균형.
    Frozen_Layer counter / Wooden_Board life / Target_Box per_target_life × target_count
    의 ratio가 셀 점유 비율과 일치할수록 점수 ↑.
    """
    warnings = []
    if not gimmicks or total_cells == 0:
        return 1.0, warnings
    total_gim_cells = 0
    total_gim_hp = 0
    for g in gimmicks:
        cells_n = len(g.get("cells", []) or []) if "cells" in g else 1
        life = g.get("life", 0) or 0
        counter = g.get("counter", 0) or 0
        # Frozen은 counter, 나머지는 life
        hp = counter if g.get("type") == "Frozen_Layer" else life
        total_gim_cells += cells_n
        total_gim_hp += hp
    if total_gim_cells == 0 or total_gim_hp == 0:
        return 1.0, warnings
    cell_pct = total_gim_cells / total_cells
    # 다트 ratio = HP / (총 풍선 1 + 기믹 HP)
    hp_pct = total_gim_hp / max(1, total_gim_hp + (total_cells - total_gim_cells))
    # gap이 작을수록 균형, 클수록 페널티
    gap = abs(cell_pct - hp_pct)
    # 80/50/20/0 stepping (§12 라인 1280)
    if gap < 0.08:
        score = 1.0
    elif gap < 0.20:
        score = 0.80
    elif gap < 0.35:
        score = 0.50
    elif gap < 0.50:
        score = 0.20
    else:
        score = 0.0
    if gap > 0.20:
        warnings.append(f"HP/visual gap {gap:.2%} (cell={cell_pct:.2%} vs hp={hp_pct:.2%})")
    return score, warnings


def verify_60lv_reappearance(csv_row: dict, gimmicks: list[dict]) -> list[str]:
    """§11.2 #6: 기믹 사용 후 30 lv 이내 재등장 권장 (Soft Rule).
    history 외부 의존이라 실제 조회는 어렵지만, 현 단일 호출에서는 active 기믹의 debut 거리 체크로 대체.
    """
    warnings = []
    lv = int(csv_row.get("level_number", 0) or 0)
    if lv == 0:
        return warnings
    active_types = set(g.get("type") for g in gimmicks if g.get("type"))
    for typ in active_types:
        # type → CSV col → debut
        col = None
        for k, v in FIELD_GIMMICKS.items():
            if v == typ:
                col = k
                break
        if col is None:
            continue
        debut = BL_DEBUT_LV.get(col, 0)
        if debut and lv - debut > 60:
            # 60 lv 넘게 사용 안 했다면 (history 없으므로 가정)
            # — 실제로는 history collection 조회 필요. 현재는 spec 의도만 기록
            warnings.append(f"60-lv reappearance check: {typ} debut at {debut}, current lv {lv} — history 조회 필요")
    return warnings


def compute_cluster_distribution(field_map: list[list[int]]) -> dict:
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


def compute_score(csv_row: dict, balloons: list[dict], gimmicks: list[dict],
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
    return weighted, dims, hp_gap_warns


# ─────────────────────────────────────────────────────
# STEP 8: v3.15 JSON 출력
# ─────────────────────────────────────────────────────

def build_field_analysis(csv_row: dict, balloons: list[dict], gimmicks: list[dict],
                          color_darts: dict[int, int], chain_groups: list[dict],
                          metaphor: float, applied_rules: list[str],
                          placement_violations: list[str] | None = None,
                          hp_visual_gap_warnings: list[str] | None = None,
                          field_map: list[list[int]] | None = None) -> dict:
    total_darts = sum(color_darts.values())
    gim_life = defaultdict(int)
    for g in gimmicks:
        gim_life[g.get("type", "Unknown")] += g.get("life", 0) or 0
    gim_positions = []
    for g in gimmicks:
        entry: dict[str, Any] = {
            "type": g.get("type"),
            "cells": g.get("cells") if "cells" in g else [[g["row"], g["col"]]],
        }
        # v1.2.3 신규 필드 전파
        for k in ("mode", "structure_id", "block_size", "counter", "bbox",
                  "box_size", "target_count", "per_target_life", "length",
                  "size", "life", "target_color", "hidden_color", "color"):
            if k in g:
                entry[k] = g[k]
        gim_positions.append(entry)
    return {
        "total_cells": int(csv_row.get("total_cells", 0)),
        "field_rows": int(csv_row.get("field_rows", 0)),
        "field_columns": int(csv_row.get("field_columns", 0)),
        "color_darts": {f"c{k}": v for k, v in color_darts.items()},
        "total_darts": total_darts,
        "total_darts_rounded": ((total_darts + 9) // 10) * 10,
        "gimmick_life": dict(gim_life),
        "gimmick_positions": gim_positions,
        "chain_groups_planned": chain_groups,
        "metaphor_preservation_score": round(metaphor, 4),
        "applied_rules": applied_rules,
        # v1.2.3 §10 라인 1193-1194 신규 필드
        "placement_violations": placement_violations or [],
        "hp_visual_gap_warnings": hp_visual_gap_warnings or [],
        # v1.2.4 (v43 통합) — 객관 시각 지표
        "cluster_dist": compute_cluster_distribution(field_map) if field_map else None,
        "visual_quality": compute_visual_quality(field_map) if field_map else None,
    }


# ─────────────────────────────────────────────────────
# 메인 알고리즘 — 1 row 처리
# ─────────────────────────────────────────────────────

def complete_one_row(csv_row: dict, partial_json: dict | None = None,
                     allow_escalation: bool = True,
                     n_candidates: int = 10,
                     keep_all_candidates: bool = False) -> dict:
    """CSV 1행 → 완성 레벨 결과 dict.
    n_candidates: 1이면 단일 시드, 2+이면 n개 후보 생성 후 best pick.
    keep_all_candidates: True면 result['all_candidates']에 n개 모두 포함 (UI picker용).
    """
    csv_row = normalize_csv_row(csv_row)
    if n_candidates <= 1:
        return _complete_one_seed(csv_row, partial_json, allow_escalation, seed_offset=0)
    # 다중 후보 생성
    candidates = []
    for i in range(n_candidates):
        cand = _complete_one_seed(csv_row, partial_json, allow_escalation=False, seed_offset=i)
        if cand.get("ok"):
            candidates.append(cand)
    if not candidates:
        return _complete_one_seed(csv_row, partial_json, allow_escalation, seed_offset=0)
    # 최고 점수 pick (tie-break: gimmick 다양성 ↑, balloon count 동일이면 metaphor_score ↑)
    candidates.sort(key=lambda r: (
        -(r.get("score", 0) or 0),
        -(len(set(g.get("type") for g in r.get("gimmicks", [])))),
        -(r.get("score_dims", {}).get("metaphor_score", 0) or 0),
    ))
    best = candidates[0]
    # 후보 통계 첨부
    best["candidates_meta"] = {
        "n_tried": n_candidates,
        "n_ok": len(candidates),
        "score_range": [round(min(c["score"] for c in candidates), 4),
                         round(max(c["score"] for c in candidates), 4)],
        "score_distribution": [round(c["score"], 4) for c in candidates],
    }
    # keep_all_candidates: UI picker에 전체 후보 노출
    if keep_all_candidates:
        # balloons는 모든 후보 동일 (field_map 보존). 후보별로 다른 건 gimmicks + scores
        best["all_candidates"] = [{
            "seed_offset": c.get("seed_offset", -1),
            "score": c.get("score", 0),
            "score_dims": c.get("score_dims", {}),
            "gimmicks": c.get("gimmicks", []),
            "field_analysis": c.get("field_analysis", {}),
        } for c in candidates]
    # escalation 결정: 활성 기믹 있고 score < 0.95이면 호출
    active_gim_count = sum(1 for k in FIELD_GIMMICKS if int(csv_row.get(k, 0) or 0) > 0)
    should_escalate = (
        allow_escalation
        and active_gim_count > 0
        and best.get("score", 0) < ESCALATION_SCORE_THRESHOLD
    )
    if should_escalate:
        api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                escalated = _escalate_to_llm(csv_row, best, api_key)
                # 채택 기준 (visual 우선):
                # (1) metaphor 점수가 ≥ 0.02 더 좋으면 무조건 채택 (visual quality 단일 지표)
                # (2) 종합 score 향상도 채택
                # (3) score 동률 + meta 향상도 채택
                old_score = best.get("score", 0)
                new_score = escalated.get("score", 0)
                old_meta = best.get("score_dims", {}).get("metaphor_score", 0)
                new_meta = escalated.get("score_dims", {}).get("metaphor_score", 0)
                meta_improved = (new_meta - old_meta) >= 0.02
                score_improved = new_score > old_score
                near_tie_meta_better = abs(new_score - old_score) < 0.005 and new_meta > old_meta
                if meta_improved or score_improved or near_tie_meta_better:
                    best = escalated
                    best["escalated"] = True
                    best["escalation_reason"] = (
                        "meta_improved" if meta_improved
                        else "score_improved" if score_improved
                        else "near_tie_meta_better"
                    )
                    best["iterations"] = 2
                else:
                    best["llm_attempted"] = True
                    best["llm_old_score"] = old_score
                    best["llm_new_score"] = new_score
                    best["llm_old_meta"] = old_meta
                    best["llm_new_meta"] = new_meta
                    best["llm_skipped_reason"] = f"no improvement (score {old_score:.3f}→{new_score:.3f}, meta {old_meta:.3f}→{new_meta:.3f})"
            except Exception as e:
                log.exception("escalation failed for lv%s", csv_row.get("level_number"))
                best["escalation_error"] = str(e)
        else:
            best["escalation_skipped"] = "OPENAI_API_KEY/ANTHROPIC_API_KEY not set"
    return best


def _complete_one_seed(csv_row: dict, partial_json: dict | None,
                       allow_escalation: bool, seed_offset: int) -> dict:
    """단일 seed로 한 번 처리 (escalation 없음, 후보 생성용)."""
    t0 = time.monotonic()
    result: dict[str, Any] = {
        "level_number": csv_row.get("level_number"),
        "ok": False,
        "score": 0.0,
        "iterations": 1,
        "escalated": False,
        "normalized_purpose": csv_row.get("purpose_type"),
        "color_distribution_auto": csv_row.get("_color_distribution_auto", False),
    }

    # STEP 1
    valid, errors = validate_input(csv_row, partial_json)
    if not valid:
        result["error"] = "validation"
        result["errors"] = errors
        return result
    debut_warnings = check_intro_isolation(csv_row)

    # STEP 2 — FieldMap 확보 (우선순위: existing field_map > designer_note [FieldMap] > default)
    field_map = None
    field_map_source = "default"

    # 우선순위 1: csv_row.field_map (pixelforge_levels의 string 또는 array)
    raw_fm = csv_row.get("field_map")
    if raw_fm:
        if isinstance(raw_fm, str) and raw_fm.strip():
            field_map = _parse_field_map_text(raw_fm)
            field_map_source = "field_map_string"
        elif isinstance(raw_fm, list) and raw_fm:
            # 이미 2D array면 정수 강제 변환
            try:
                field_map = [[int(c) if c is not None else -1 for c in row] for row in raw_fm]
                field_map_source = "field_map_array"
            except (ValueError, TypeError):
                field_map = None
    # palette_mapping 적용 (raw 코드 → BL color index)
    if field_map is not None and csv_row.get("palette_mapping"):
        field_map = apply_palette_mapping(field_map, csv_row["palette_mapping"])

    # 우선순위 2: designer_note의 [FieldMap]
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
        field_map_source = "default_layout"

    result["field_map_source"] = field_map_source

    # STEP 3
    clusters = extract_clusters(field_map)
    clusters = assign_metaphor_priority(clusters)

    # STEP 4-5
    track_a_gim = track_a(csv_row, clusters, partial_json)
    track_b_gim = track_b(csv_row, clusters, field_map, seed_offset=seed_offset)
    all_gimmicks = track_a_gim + track_b_gim

    # Chain groups
    chain_groups = assign_chain_groups(csv_row, clusters)

    # STEP 6 (balloons + reconcile)
    balloons = build_balloons(field_map, all_gimmicks)
    color_darts = compute_color_darts(balloons, all_gimmicks)
    color_darts, mod10_warnings = reconcile_mod10(color_darts, balloons, all_gimmicks)

    # STEP 7
    # 이미지 grid 디코드 (있으면 image-based 평가)
    image_grid = None
    if csv_row.get("image_base64") and csv_row.get("field_rows") and csv_row.get("field_columns"):
        image_grid = decode_image_to_palette_grid(
            csv_row["image_base64"],
            int(csv_row["field_rows"]),
            int(csv_row["field_columns"]),
        )
    metaphor = metaphor_score(field_map, all_gimmicks, clusters, image_grid)

    # §7.5 Placement Violations (HR 7, 8, 12-16)
    field_h_ = len(field_map)
    field_w_ = len(field_map[0]) if field_h_ else 0
    pkg_val = int(csv_row.get("pkg", 0) or 0)
    total_darts_now = sum(color_darts.values())
    placement_violations = verify_placement(
        balloons, all_gimmicks, field_h_, field_w_,
        chain_groups=chain_groups,
        pkg=pkg_val,
        total_darts=total_darts_now,
    )

    # Score
    applied_rules = (
        [f"track_a_{g['type']}" for g in track_a_gim] +
        [f"track_b_{g['type']}" for g in track_b_gim] +
        (["mod10_color_balanced"] if not mod10_warnings else []) +
        (["metaphor_outline_preserved"] if metaphor >= 0.85 else [])
    )

    total_cells_int = int(csv_row.get("total_cells", 0) or 0)
    score, dims, hp_gap_warnings = compute_score(csv_row, balloons, all_gimmicks, color_darts,
                                                  metaphor, [], debut_warnings,
                                                  total_cells=total_cells_int,
                                                  field_map=field_map)

    # STEP 8: 출력 — v1.2.4: field_map 전달로 cluster_dist + visual_quality 포함
    field_analysis = build_field_analysis(csv_row, balloons, all_gimmicks,
                                          color_darts, chain_groups, metaphor, applied_rules,
                                          placement_violations=placement_violations,
                                          hp_visual_gap_warnings=hp_gap_warnings,
                                          field_map=field_map)

    result.update({
        "ok": True,
        "score": round(score, 4),
        "score_dims": {k: round(v, 4) for k, v in dims.items()},
        "balloons": balloons,
        "gimmicks": all_gimmicks,
        "field_analysis": field_analysis,
        "warnings": mod10_warnings + debut_warnings,
        "placement_violations": placement_violations,
        "duration_sec": round(time.monotonic() - t0, 2),
        "seed_offset": seed_offset,
    })
    # placement violation은 hard_rule_pass에 감점
    if placement_violations:
        dims["hard_rule_pass"] = max(0.0, dims.get("hard_rule_pass", 1.0) - 0.15 * len(placement_violations))
        # score 재계산
        score = sum(dims[k] * SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS)
        result["score"] = round(score, 4)
        result["score_dims"] = {k: round(v, 4) for k, v in dims.items()}
    # _complete_one_seed는 escalation 안 함 (complete_one_row에서 처리)
    return result


def _escalate_to_llm(csv_row: dict, det_result: dict, api_key: str) -> dict:
    """OpenAI GPT-5-mini (또는 anthropic) 호출하여 STEP 4-5 재실행.
    프롬프트: field_map + bl_metaphor + 활성 기믹 → JSON 배치 응답.
    반환된 배치를 다시 score하여 기존 결과보다 좋으면 채택."""
    log.info("[escalation] calling OpenAI for lv%s", csv_row.get("level_number"))

    try:
        from openai import OpenAI
    except ImportError:
        det_result["escalation_error"] = "openai package not installed"
        return det_result

    # v1.2.3: timeout 60초 강제 (이전엔 무한 대기로 watcher zombie 발생)
    client = OpenAI(api_key=api_key, timeout=60.0, max_retries=1)

    # 현재 field_map + active gimmicks 정보
    lv = csv_row.get("level_number")
    bl_metaphor = csv_row.get("bl_metaphor", "") or csv_row.get("designer_note", "")[:200]
    field_map_text = csv_row.get("field_map", "") or "(missing)"
    active_gim = {k: int(csv_row.get(k, 0) or 0) for k in FIELD_GIMMICKS if int(csv_row.get(k, 0) or 0) > 0}
    if not active_gim:
        # 활성 기믹 없으면 LLM 호출 의미 없음
        return det_result

    cur_gimmicks = det_result.get("gimmicks", [])
    cur_score = det_result.get("score", 0)
    cur_dims = det_result.get("score_dims", {})

    # 기믹 타입 → CSV 컬럼 매핑 (count 강제용)
    TYPE_TO_COL = {
        "Iron_Wall": "gimmick_wall",
        "Wooden_Board": "gimmick_pinata",
        "Hidden_Balloon": "gimmick_surprise",
        "Barricade": "gimmick_pin",
        "Target_Box": "gimmick_pinata_box",
        "Frozen_Layer": "gimmick_ice",
    }
    # CSV active count를 type별로 변환
    active_by_type = {}
    for typ, col in TYPE_TO_COL.items():
        v = int(csv_row.get(col, 0) or 0)
        if v > 0:
            active_by_type[typ] = v

    count_constraint = "\n".join(
        f'- {typ}: EXACTLY {n} gimmick objects (Iron_Wall, Wooden_Board, Target_Box, Barricade = 1 obj each; Hidden_Balloon, Frozen_Layer = cells count)'
        for typ, n in active_by_type.items()
    )

    system_prompt = f"""You are a BalloonFlow level designer assistant.

You receive an existing level's field_map (2D grid of color codes) + designer metaphor + active gimmick counts.
Your job: propose THREE DIFFERENT gimmick placements that PRESERVE the visual metaphor while satisfying gameplay rules.

CRITICAL COUNT CONSTRAINTS (MUST match exactly):
{count_constraint}

CRITICAL RULES (must follow):
1. Iron_Wall: don't cover the entire outline; only corners + entry points. Preserve silhouette.
2. Wooden_Board (size 1×1 life=5 or 2×3 life=15): place on visually-redundant cells (interior, not centroid).
3. Hidden_Balloon (life=1): place inside cluster mass (dense interior), preserve hidden_color from field_map.
4. Barricade (life=3): outline mid-section, AVOID corners (corners are metaphor peaks).
5. Target_Box (life=1, target_color=adjacent color): cluster centroid OK only for target_box.
6. Frozen_Layer (life_modifier=1): cover non-key clusters or low ratio cells.

COUNT INTERPRETATION:
- Iron_Wall, Wooden_Board, Target_Box, Barricade: count = number of separate gimmick OBJECTS (each with own cells)
- Hidden_Balloon, Frozen_Layer: count = total cells across all objects (you may merge into 1 object with N cells)

DIVERSITY: provide 3 placements that explore different visual trade-offs (conservative, balanced, bold).

OUTPUT JSON ONLY:
{{"candidates": [
  {{"label": "conservative", "gimmicks": [{{"type": "Iron_Wall", "cells": [[r,c],...], "life": 0, "structure_id": 1}}], "reasoning": "..."}},
  {{"label": "balanced", "gimmicks": [...], "reasoning": "..."}},
  {{"label": "bold", "gimmicks": [...], "reasoning": "..."}}
]}}"""

    user_prompt = f"""Level {lv}
Metaphor: {bl_metaphor}
Field size: {csv_row.get('field_rows')} x {csv_row.get('field_columns')}
Active gimmicks: {active_gim}

Current heuristic score: {cur_score} (meta={cur_dims.get('metaphor_score')})
Current gimmick types: {dict((g.get('type'), 1) for g in cur_gimmicks)}

Field map (raw color codes, .. = empty):
{field_map_text[:2500]}

Propose 3 ALTERNATIVE placements. We will pick the best."""

    try:
        resp = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        if not content:
            det_result["escalation_error"] = "empty LLM response"
            return det_result
        parsed = json.loads(content)
        # 2가지 응답 형식 지원 (단일 또는 N candidates)
        if "candidates" in parsed:
            candidates_raw = parsed["candidates"]
        elif "gimmicks" in parsed:
            candidates_raw = [parsed]
        else:
            det_result["escalation_error"] = "unexpected LLM response format"
            return det_result

        balloons = det_result.get("balloons", [])
        # 각 후보 점수화 — metaphor 우선, 동률이면 종합 score
        best_result = det_result
        best_meta = det_result.get("score_dims", {}).get("metaphor_score", 0)
        best_score = det_result.get("score", 0)
        candidates_summary = []

        for cand in candidates_raw:
            proposed_gimmicks = cand.get("gimmicks", [])
            label = cand.get("label", "unlabeled")
            if not proposed_gimmicks:
                continue

            # Count enforcement: 활성 카운트 over면 truncate
            from collections import Counter as _Cnt
            type_counts = _Cnt(g.get("type") for g in proposed_gimmicks)
            kept_gimmicks = []
            type_kept: dict[str, int] = {}
            for g in proposed_gimmicks:
                typ = g.get("type")
                if typ not in active_by_type:
                    continue  # 활성 안 한 기믹 타입 제외
                target = active_by_type[typ]
                kept = type_kept.get(typ, 0)
                if typ in ("Hidden_Balloon", "Frozen_Layer"):
                    # cells 수로 측정. 셀 누적이 target 넘으면 truncate
                    cur_cells = sum(len(kg.get("cells", [g_]) if "cells" in kg else [1])
                                    for kg in [g for g in kept_gimmicks if g.get("type") == typ])
                    new_cells = len(g.get("cells", []) or []) or 1
                    if cur_cells + new_cells > target:
                        # 마지막 가믹 cells 자름
                        if "cells" in g:
                            g["cells"] = g["cells"][: max(0, target - cur_cells)]
                        if g["cells"]:
                            kept_gimmicks.append(g)
                            type_kept[typ] = kept + 1
                        continue
                    kept_gimmicks.append(g)
                    type_kept[typ] = kept + 1
                else:
                    # object 수 기준
                    if kept >= target:
                        continue
                    kept_gimmicks.append(g)
                    type_kept[typ] = kept + 1
            proposed_gimmicks = kept_gimmicks
            if not proposed_gimmicks:
                continue

            # 새 결과 구성
            new_color_darts = compute_color_darts(balloons, proposed_gimmicks)
            new_color_darts, mod10_warns = reconcile_mod10(new_color_darts, balloons, proposed_gimmicks)
            # metaphor 재산출 (clusters 다시 빌드 비싸므로 단순 평가)
            # — image grid가 있으면 importance penalty도 적용
            image_grid = decode_image_to_palette_grid(
                csv_row.get("image_base64", ""),
                int(csv_row.get("field_rows", 0) or 0),
                int(csv_row.get("field_columns", 0) or 0),
            ) if csv_row.get("image_base64") else None
            field_map_obj = None
            raw_fm = csv_row.get("field_map")
            if isinstance(raw_fm, str) and raw_fm:
                field_map_obj = _parse_field_map_text(raw_fm)
                if field_map_obj and csv_row.get("palette_mapping"):
                    field_map_obj = apply_palette_mapping(field_map_obj, csv_row["palette_mapping"])

            # cluster 다시 계산
            clusters_recomp = extract_clusters(field_map_obj) if field_map_obj else []
            clusters_recomp = assign_metaphor_priority(clusters_recomp)
            new_meta = metaphor_score(field_map_obj or [], proposed_gimmicks, clusters_recomp, image_grid)

            new_dims = dict(cur_dims)
            new_dims["metaphor_score"] = new_meta
            new_dims["mod10_compliance"] = 1.0 if not mod10_warns else 0.5
            new_score_val = sum(new_dims[k] * SCORE_WEIGHTS[k] for k in SCORE_WEIGHTS)

            candidates_summary.append({
                "label": label,
                "score": round(new_score_val, 4),
                "meta": round(new_meta, 4),
                "gimmicks_count": len(proposed_gimmicks),
                "reasoning": cand.get("reasoning", "")[:200],
            })

            # picking: metaphor 우위 (≥0.02 차이) OR 종합 score 우위
            meta_better = (new_meta - best_meta) >= 0.02
            score_better = new_score_val > best_score
            if meta_better or score_better:
                best_meta = new_meta
                best_score = new_score_val
                new_result = dict(det_result)
                new_result["gimmicks"] = proposed_gimmicks
                new_result["llm_reasoning"] = cand.get("reasoning", "")
                new_result["llm_label"] = label
                new_result["llm_pick_reason"] = "meta" if meta_better else "score"
                new_result["score"] = round(new_score_val, 4)
                new_result["score_dims"] = {k: round(v, 4) for k, v in new_dims.items()}
                new_result["field_analysis"] = {
                    **(det_result.get("field_analysis") or {}),
                    "color_darts": {f"c{k}": v for k, v in new_color_darts.items()},
                    "total_darts": sum(new_color_darts.values()),
                    "applied_rules": (det_result.get("field_analysis", {}).get("applied_rules", [])) + ["llm_escalation"],
                }
                best_result = new_result

        if best_result is not det_result:
            best_result["llm_candidates_summary"] = candidates_summary
        else:
            det_result["llm_candidates_summary"] = candidates_summary
            det_result["llm_attempted"] = True

        return best_result
    except Exception as e:
        log.exception("LLM call failed")
        det_result["escalation_error"] = f"{type(e).__name__}: {e}"
        return det_result


# ─────────────────────────────────────────────────────
# DB / Request 처리
# ─────────────────────────────────────────────────────

JOBS_COLLECTION = "pixelforge_field_complete_jobs"
LEVELS_COLLECTION = "pixelforge_levels"


def _pull_job(req_id: str) -> dict[str, Any]:
    from pymongo import MongoClient
    from bson import ObjectId
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI not set")
    db_name = os.environ.get("MONGODB_DB", "aigame")
    db = MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    doc = db[JOBS_COLLECTION].find_one({"_id": ObjectId(req_id)})
    if not doc:
        raise RuntimeError(f"job {req_id} not found")
    db[JOBS_COLLECTION].update_one(
        {"_id": doc["_id"]},
        {"$set": {"status": "running", "started_at": _iso_now()}},
    )
    return doc


def _finalize_job(req_id: str, *, results: list[dict], error: str = "") -> None:
    from pymongo import MongoClient
    from bson import ObjectId
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        return
    db_name = os.environ.get("MONGODB_DB", "aigame")
    db = MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    totals = {
        "ok": sum(1 for r in results if r.get("ok")),
        "fail": sum(1 for r in results if not r.get("ok")),
        "escalated": sum(1 for r in results if r.get("escalated")),
        "avg_score": round(
            sum(r.get("score", 0) for r in results if r.get("ok")) /
            max(1, sum(1 for r in results if r.get("ok"))),
            4
        ),
    }
    update = {
        "status": "failed" if error else "done",
        "finished_at": _iso_now(),
        "results": results,
        "totals": totals,
    }
    if error:
        update["error"] = error
    db[JOBS_COLLECTION].update_one({"_id": ObjectId(req_id)}, {"$set": update})


def _build_field_map_from_balloons(balloons: list, gimmicks: list, rows: int, cols: int) -> str:
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
    return "\n".join(" ".join(row) for row in grid)


def _save_levels_to_db(results: list[dict], job_id: str) -> None:
    """각 ok 결과를 pixelforge_levels에 upsert."""
    from pymongo import MongoClient
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        return
    db_name = os.environ.get("MONGODB_DB", "aigame")
    db = MongoClient(uri, serverSelectionTimeoutMS=2000)[db_name]
    coll = db[LEVELS_COLLECTION]
    now = _iso_now()
    for r in results:
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


# ─────────────────────────────────────────────────────
# main
# ─────────────────────────────────────────────────────

def main() -> int:
    _load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", help="pixelforge_field_complete_jobs _id")
    ap.add_argument("--input", help="CSV row JSON file (for testing without DB)")
    ap.add_argument("--output", help="output path (for --input mode)")
    args = ap.parse_args()

    if args.input:
        # 테스트 모드: 단일 row JSON 파일
        rows = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if isinstance(rows, dict):
            rows = [rows]
        results = [complete_one_row(r) for r in rows]
        out_path = args.output or "field_complete_output.json"
        Path(out_path).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[test] {len(rows)} rows → {out_path}")
        for r in results:
            print(f"  lv{r.get('level_number')}: ok={r.get('ok')} score={r.get('score', 0):.3f} escalated={r.get('escalated', False)}")
        return 0

    if not args.request:
        print("Usage: --request <job_id> or --input <rows.json>", file=sys.stderr)
        return 1

    request_id = args.request
    error_str = ""
    results: list[dict] = []
    try:
        doc = _pull_job(request_id)
        csv_rows = list(doc.get("csv_rows") or [])
        if not csv_rows:
            raise RuntimeError("no csv_rows in job")
        keep_all = bool(doc.get("keep_all_candidates", False))
        allow_esc = bool(doc.get("allow_escalation", True))
        print(f"[job {request_id}] processing {len(csv_rows)} rows (keep_all={keep_all})")
        for i, row in enumerate(csv_rows):
            t = time.monotonic()
            r = complete_one_row(row, allow_escalation=allow_esc, keep_all_candidates=keep_all)
            r["idx"] = i
            results.append(r)
            print(f"  #{i} lv={r.get('level_number')}: ok={r.get('ok')} "
                  f"score={r.get('score', 0):.3f} "
                  f"escalated={r.get('escalated', False)} "
                  f"({time.monotonic()-t:.1f}s)")
        _save_levels_to_db(results, request_id)
    except Exception as e:
        error_str = f"{type(e).__name__}: {e}"
        log.exception("job failed")

    try:
        _finalize_job(request_id, results=results, error=error_str)
    except Exception:
        log.exception("finalize failed")

    print(f"=== DONE: ok={sum(1 for r in results if r.get('ok'))}/{len(results)} ===")
    return 0 if not error_str else 1


if __name__ == "__main__":
    sys.exit(main())
