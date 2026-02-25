#!/usr/bin/env python3
"""
D1-10 Experiment: 10-person AI observations + Level 1 pattern cards (design intent only)
========================================================================================
Condition D1_10: aggregated 10-tester observations + Level 1 patterns (no numeric hints)

Previous baselines:
  C   (1-person observation only):      0.365
  D1  (1-person + L1 pattern):          0.592
  B1  (L1 pattern only):                0.777
  C10 (10-person observation only):     0.850
  D2  (1-person + L2 pattern):          0.963
  B2  (L2 pattern only):                0.978
  D10 (10-person + L2 pattern):         0.985
"""

import os
import sys
import subprocess
import time
import re
from pathlib import Path
from datetime import datetime

# ============================================================================
# CONFIGURATION
# ============================================================================

CLAUDE = r"C:\Users\user\AppData\Roaming\npm\claude.cmd"

BASE = Path(r"E:\AI\projects\CleanRoomTest\multi_tester")
GT_DIR = Path(r"E:\AI\projects\CleanRoomTest\ground_truth")
PAT_DIR = Path(r"E:\AI\projects\CleanRoomTest\pattern_cards\level1_design_intent")

AGG_DIR = BASE / "aggregated"
SPECS_DIR = BASE / "specs"
SCORING_DIR = BASE / "scoring"

GAMES = {
    "tapshift":  {"name": "Tap Shift",  "prefix": "TS"},
    "magicsort": {"name": "Magic Sort", "prefix": "MS"},
    "carmatch":  {"name": "Car Match",  "prefix": "CM"},
}

PARAM_LIST = {
    "tapshift": """TS01: total_levels (core_constants) - 총 레벨 수
TS02: max_lives (core_constants) - 최대 생명 수
TS03: max_undo_count (core_constants) - 최대 되돌리기 횟수
TS04: max_hint_count (core_constants) - 최대 힌트 수
TS05: interstitial_frequency (monetization) - 전면광고 빈도
TS06: arrow_move_speed (core_constants) - 화살표 이동 속도
TS07: max_arrow_clamp (core_constants) - 최대 화살표 수 제한
TS08: star_rating_system (scoring) - 별점 시스템 기준
TS09: base_unit (animation) - 기본 단위(픽셀)
TS10: position_snap (animation) - 위치 스냅 값
TS11: duration_clamp (animation) - 애니메이션 지속시간 범위
TS12: stretch_phase (animation) - 스트레칭 단계 비율
TS13: stretch_max (animation) - 최대 스트레칭 배율
TS14: snap_phase (animation) - 스냅 단계 비율
TS15: arrow_colors (visual) - 방향별 화살표 색상
TS16: head_ratio (visual) - 화살표 머리 비율
TS17: shaft_height_ratio (visual) - 화살표 축 높이 비율
TS18: collision_system (algorithm) - 충돌 판정 방식
TS19: performance_complexity (algorithm) - 성능 복잡도
TS20: solver_algorithm (algorithm) - 솔버 알고리즘
TS21: ui_reference_resolution (ui) - UI 기준 해상도
TS22: total_files (architecture) - 총 파일 수
TS23: pattern_count (architecture) - 디자인 패턴 수
TS24: state_count (architecture) - 게임 상태 수
TS25: serialization_format (architecture) - 직렬화 형식
TS26: arrow_directions (gameplay) - 화살표 방향 종류
TS27: arrow_count_progression (difficulty) - 화살표 수 진행
TS28: grid_size_range (gameplay) - 격자 크기 범위
TS29: tap_mechanic (gameplay) - 탭 메커니즘
TS30: goal_condition (gameplay) - 클리어 조건
TS31: level_generation (algorithm) - 레벨 생성 방식
TS32: save_system (architecture) - 저장 시스템""",

    "magicsort": """MS01: bottle_max_height (core_constants) - 병 최대 높이(층)
MS02: colors_total (core_constants) - 전체 색상 수
MS03: colors_playable (core_constants) - 플레이 가능 색상 수
MS04: builtin_levels (level_gen) - 빌트인 레벨 수
MS05: procedural_after_level (level_gen) - 절차적 생성 시작 레벨
MS06: max_gen_attempts (level_gen) - 최대 생성 시도 횟수
MS07: difficulty_tier_count (difficulty) - 난이도 티어 수
MS08: tier_color_counts (difficulty) - 티어별 색상 수
MS09: tier_level_ranges (difficulty) - 티어별 레벨 범위
MS10: par_bonus_values (difficulty) - 파 보너스 값
MS11: par_formula (difficulty) - 파 계산 공식
MS12: max_per_row (visual) - 행당 최대 병 수
MS13: h_spacing (visual) - 수평 간격
MS14: v_spacing (visual) - 수직 간격
MS15: pour_total_duration (animation) - 따르기 총 시간
MS16: lift_height (animation) - 들어올림 높이
MS17: tilt_angle (animation) - 기울기 각도
MS18: starting_coins (economy) - 시작 코인
MS19: starting_gems (economy) - 시작 젬
MS20: booster_type_count (gameplay) - 부스터 종류 수
MS21: booster_initial_counts (gameplay) - 부스터 초기 수량
MS22: undo_max_steps (gameplay) - 되돌리기 최대 단계
MS23: star_rating_3star (scoring) - 3성 기준
MS24: star_rating_2star_threshold (scoring) - 2성 기준
MS25: hint_scoring_system (algorithm) - 힌트 점수화 시스템
MS26: blocker_type_count (gameplay) - 블로커 종류 수
MS27: save_prefix (architecture) - 저장 접두사
MS28: pattern_count (architecture) - 디자인 패턴 수
MS29: state_count (architecture) - 게임 상태 수
MS30: pour_mechanic (gameplay) - 따르기 메커니즘
MS31: win_condition (gameplay) - 승리 조건
MS32: empty_bottles_formula (difficulty) - 빈 병 공식""",

    "carmatch": """CM01: cell_size (core_constants) - 셀 크기
CM02: car_types (core_constants) - 자동차 종류 수
CM03: match_count (core_constants) - 매칭 필요 수
CM04: movement_speed (core_constants) - 이동 속도
CM05: model_scale (visual) - 모델 스케일
CM06: y_offset (visual) - Y 오프셋
CM07: holder_max_slots (gameplay) - 홀더 최대 슬롯
CM08: slot_spacing (visual) - 슬롯 간격
CM09: grid_size_progression (difficulty) - 격자 크기 진행
CM10: scoring_formula (scoring) - 점수 공식
CM11: star_thresholds (scoring) - 별 기준
CM12: max_levels (core_constants) - 최대 레벨 수
CM13: car_sets_formula (difficulty) - 자동차 세트 공식
CM14: booster_types (gameplay) - 부스터 종류
CM15: booster_initial_counts (gameplay) - 부스터 초기 수량
CM16: initial_coins (economy) - 초기 코인
CM17: move_history_max (gameplay) - 이동 히스토리 최대
CM18: tunnel_spawn_count (gameplay) - 터널 스폰 수
CM19: tunnel_placement (gameplay) - 터널 배치
CM20: pathfinding_algorithm (algorithm) - 경로탐색 알고리즘
CM21: storage_count (gameplay) - 임시저장소 수
CM22: daily_reward_progression (economy) - 일일보상 진행
CM23: journey_frequency (gameplay) - 여정 보상 빈도
CM24: camera_angle (visual) - 카메라 각도
CM25: base_height_5x5 (visual) - 5x5 기준 높이
CM26: state_count (architecture) - 게임 상태 수
CM27: namespace (architecture) - 네임스페이스
CM28: tap_mechanic (gameplay) - 탭 메커니즘
CM29: fail_condition (gameplay) - 실패 조건
CM30: win_condition (gameplay) - 승리 조건
CM31: pattern_count (architecture) - 디자인 패턴 수
CM32: serialization (architecture) - 직렬화 방식""",
}

BASELINES = {
    "C":   {"label": "C (1인 관찰)",      "average": 0.365},
    "D1":  {"label": "D1 (1인+L1)",        "average": 0.592},
    "B1":  {"label": "B1 (L1 패턴만)",     "average": 0.777},
    "C10": {"label": "C10 (10인 관찰)",     "average": 0.850},
    "D2":  {"label": "D2 (1인+L2)",        "average": 0.963},
    "B2":  {"label": "B2 (L2 패턴만)",     "average": 0.978},
    "D10": {"label": "D10 (10인+L2)",      "average": 0.985},
}


# ============================================================================
# HELPERS
# ============================================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def ensure_dirs():
    for d in [SPECS_DIR, SCORING_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def _clean_env():
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    env.pop("ANTHROPIC_MODEL", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def claude_text(prompt, timeout=600):
    cmd = [CLAUDE, "--print", "--model", "sonnet"]
    try:
        r = subprocess.run(
            cmd, input=prompt, capture_output=True, encoding="utf-8",
            env=_clean_env(), timeout=timeout, cwd=str(BASE),
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return f"ERROR: rc={r.returncode} {r.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return "ERROR: Timeout"
    except Exception as e:
        return f"ERROR: {e}"


def extract_average(text):
    m = re.search(r'average:\s*([\d.]+)', text)
    return float(m.group(1)) if m else 0.0


def extract_sum(text):
    m = re.search(r'sum:\s*([\d.]+)', text)
    return float(m.group(1)) if m else 0.0


def extract_param_scores(text):
    results = []
    blocks = re.split(r'\n\s*-\s*id:\s*', text)
    for block in blocks[1:]:
        id_m = re.match(r'(\w+)', block)
        name_m = re.search(r'name:\s*["\']?(.+?)["\']?\s*\n', block)
        score_m = re.search(r'score:\s*([\d.]+)', block)
        gt_m = re.search(r'ground_truth:\s*["\']?(.+?)["\']?\s*\n', block)
        gen_m = re.search(r'generated:\s*["\']?(.+?)["\']?\s*\n', block)
        note_m = re.search(r'note:\s*["\']?(.+?)["\']?\s*$', block, re.MULTILINE)
        if id_m and score_m:
            results.append({
                "id": id_m.group(1),
                "name": name_m.group(1).strip() if name_m else "",
                "score": float(score_m.group(1)),
                "ground_truth": gt_m.group(1).strip() if gt_m else "",
                "generated": gen_m.group(1).strip() if gen_m else "",
                "note": note_m.group(1).strip() if note_m else "",
            })
    return results


# ============================================================================
# PHASE 1: SPEC GENERATION (3 Claude CLI calls)
# ============================================================================

def phase1_specs():
    log("=" * 60)
    log("PHASE 1: D1_10 SPEC GENERATION (3 calls)")
    log("  Condition: 10-person observations + Level 1 design intent patterns")
    log("=" * 60)

    for gk, gi in GAMES.items():
        spec_file = SPECS_DIR / f"{gk}_D1_10_spec.yaml"
        if spec_file.exists() and spec_file.stat().st_size > 100:
            log(f"  {gi['name']} D1_10: already exists, skip")
            continue

        agg_file = AGG_DIR / f"{gk}_10x_consensus.txt"
        if not agg_file.exists():
            log(f"  {gi['name']}: no aggregated observation data, skip")
            continue
        agg_text = agg_file.read_text(encoding="utf-8")

        pat_file = PAT_DIR / f"{gk}_patterns.yaml"
        if not pat_file.exists():
            log(f"  {gi['name']}: no L1 pattern card, skip")
            continue
        pat_text = pat_file.read_text(encoding="utf-8")

        params = PARAM_LIST[gk]

        log(f"  {gi['name']} D1_10: generating (10-person obs + L1 patterns)...")

        prompt = f"""당신은 모바일 게임 밸런스 시트 전문가입니다.

다음은 게임 "{gi['name']}"에 대해 10명의 AI 테스터가 관찰한 결과를 집계한 데이터입니다:

{agg_text}

---

추가로 다음 Level 1 설계 의도 패턴 카드를 참조하세요 (설계 패턴과 아키텍처 정보, 구체적 수치 힌트 없음):

{pat_text}

---

위 관찰 데이터와 Level 1 패턴 카드를 함께 활용하여 아래 32개 파라미터의 값을 추정하세요.
패턴 카드의 설계 의도와 아키텍처 정보를 활용하되, 구체적 수치는 관찰 데이터에서 확인된 값을 우선 사용하세요.
관찰에서 직접 확인할 수 없는 파라미터는 패턴 카드의 설계 의도로부터 합리적으로 추론하되,
확신이 없으면 null로 표시하세요.

파라미터 목록:
{params}

YAML 형식으로 출력하세요:
game: "{gi['name']}"
condition: "D1_10"
parameters:
  - id: {gi['prefix']}01
    name: total_levels
    value: (추정값)
    confidence: high/medium/low
    source: "추정 근거"
  - id: {gi['prefix']}02
    name: ...
    ...

중요: 반드시 32개 파라미터 모두 포함하세요. 누락하지 마세요."""

        result = claude_text(prompt, timeout=300)
        spec_file.write_text(result, encoding="utf-8")

        if result.startswith("ERROR"):
            log(f"    -> {result[:80]}")
        else:
            log(f"    -> {len(result)} chars")

    log("\nPhase 1 complete.")


# ============================================================================
# PHASE 2: SCORING (3 Claude CLI calls)
# ============================================================================

def phase2_scoring():
    log("\n" + "=" * 60)
    log("PHASE 2: D1_10 SCORING (3 calls)")
    log("=" * 60)

    for gk, gi in GAMES.items():
        score_file = SCORING_DIR / f"{gk}_D1_10_score.yaml"
        if score_file.exists() and score_file.stat().st_size > 100:
            log(f"  {gi['name']} D1_10: already scored, skip")
            continue

        gt_file = GT_DIR / f"{gk}_ground_truth.yaml"
        if not gt_file.exists():
            log(f"  {gi['name']}: no ground truth, skip")
            continue
        gt_text = gt_file.read_text(encoding="utf-8")

        spec_file = SPECS_DIR / f"{gk}_D1_10_spec.yaml"
        if not spec_file.exists():
            log(f"  {gi['name']} D1_10: no spec file, skip")
            continue
        spec_text = spec_file.read_text(encoding="utf-8")
        if spec_text.startswith("ERROR"):
            log(f"  {gi['name']} D1_10: spec has errors, skip")
            continue

        params = PARAM_LIST[gk]
        log(f"  {gi['name']} D1_10: scoring...")

        prompt = f"""다음 두 데이터를 비교하여 각 파라미터를 채점하세요.

## Ground Truth (원본 소스에서 추출한 정답)

{gt_text}

## Generated Spec (AI가 생성한 추정 밸런스 시트)

{spec_text}

## 채점할 파라미터 목록 (32개)

{params}

## 채점 기준

- 1.0: Exact — 값이 정확히 일치하거나 의미적으로 동일
- 0.7: Close — 값이 20% 이내이거나, 핵심 개념이 일치하고 세부만 다름
- 0.4: Partial — 개념은 맞지만 구체적 값이 다름
- 0.1: Wrong — 완전히 다른 값
- 0.0: Missing — 누락되었거나 null

## 출력 형식 (반드시 이 YAML 형식을 따르세요)

scoring:
  game: "{gi['name']}"
  condition: "D1_10"
  results:
    - id: {gi['prefix']}01
      name: (파라미터명)
      ground_truth: "(실제값)"
      generated: "(추정값)"
      score: 0.0
      note: "(설명)"
    - id: {gi['prefix']}02
      name: ...
      ...
  summary:
    total: 32
    sum: (점수 합계)
    average: (평균)

중요:
- 반드시 32개 파라미터 모두 채점하세요
- Ground Truth에서 각 파라미터의 실제 값을 찾아 비교하세요
- summary의 sum과 average를 정확히 계산하세요"""

        result = claude_text(prompt, timeout=300)
        score_file.write_text(result, encoding="utf-8")

        if result.startswith("ERROR"):
            log(f"    -> {result[:80]}")
        else:
            avg = extract_average(result)
            log(f"    -> {len(result)} chars, average: {avg:.3f}")

    log("\nPhase 2 complete.")


# ============================================================================
# PHASE 3: REPORT GENERATION
# ============================================================================

def phase3_report():
    log("\n" + "=" * 60)
    log("PHASE 3: REPORT GENERATION")
    log("=" * 60)

    scores = {}
    for gk in GAMES:
        sf = SCORING_DIR / f"{gk}_D1_10_score.yaml"
        if sf.exists():
            text = sf.read_text(encoding="utf-8")
            scores[gk] = {
                "average": extract_average(text),
                "sum": extract_sum(text),
                "details": extract_param_scores(text),
            }
        else:
            scores[gk] = {"average": 0.0, "sum": 0.0, "details": []}

    d1_10_avg = sum(scores[g]["average"] for g in GAMES) / 3

    report = f"""# D1-10 실험 결과: 10인 AI 관찰 + Level 1 패턴 카드 (설계 의도)
생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 1. 실험 개요

**조건 D1_10**: 10명 AI 테스터의 집계된 관찰 데이터 + Level 1 패턴 카드 (설계 의도만, 구체적 수치 힌트 없음)

**핵심 질문**: L1 패턴(설계 의도)과 10인 관찰의 조합이 어떤 성능을 보이는가?

---

## 2. D1_10 게임별 결과

| 게임 | D1_10 점수 |
|------|-----------|
| Tap Shift | {scores['tapshift']['average']*100:.1f}% |
| Magic Sort | {scores['magicsort']['average']*100:.1f}% |
| Car Match | {scores['carmatch']['average']*100:.1f}% |
| **평균** | **{d1_10_avg*100:.1f}%** |

---

## 3. 전체 조건 비교표

| # | 조건 | 설명 | 평균 일치도 | D1_10 대비 |
|---|------|------|-----------|-----------|
| 1 | C | 1인 관찰만 | {BASELINES['C']['average']*100:.1f}% | {(BASELINES['C']['average']-d1_10_avg)*100:+.1f}%p |
| 2 | D1 | 1인 관찰 + L1 패턴 | {BASELINES['D1']['average']*100:.1f}% | {(BASELINES['D1']['average']-d1_10_avg)*100:+.1f}%p |
| 3 | B1 | L1 패턴만 (관찰 없음) | {BASELINES['B1']['average']*100:.1f}% | {(BASELINES['B1']['average']-d1_10_avg)*100:+.1f}%p |
| 4 | C10 | 10인 관찰만 | {BASELINES['C10']['average']*100:.1f}% | {(BASELINES['C10']['average']-d1_10_avg)*100:+.1f}%p |
| **5** | **D1_10** | **10인 관찰 + L1 패턴** | **{d1_10_avg*100:.1f}%** | **기준** |
| 6 | D2 | 1인 관찰 + L2 패턴 | {BASELINES['D2']['average']*100:.1f}% | {(BASELINES['D2']['average']-d1_10_avg)*100:+.1f}%p |
| 7 | B2 | L2 패턴만 | {BASELINES['B2']['average']*100:.1f}% | {(BASELINES['B2']['average']-d1_10_avg)*100:+.1f}%p |
| 8 | D10 | 10인 관찰 + L2 패턴 | {BASELINES['D10']['average']*100:.1f}% | {(BASELINES['D10']['average']-d1_10_avg)*100:+.1f}%p |

---

## 4. 분석

### 4-1. 관찰 인원 확대 효과 (L1 패턴 기준)
- D1 (1인+L1): {BASELINES['D1']['average']*100:.1f}% -> D1_10 (10인+L1): {d1_10_avg*100:.1f}% ({(d1_10_avg-BASELINES['D1']['average'])*100:+.1f}%p)

### 4-2. L1 패턴 추가 효과 (10인 관찰 기준)
- C10 (10인 관찰만): {BASELINES['C10']['average']*100:.1f}% -> D1_10 (10인+L1): {d1_10_avg*100:.1f}% ({(d1_10_avg-BASELINES['C10']['average'])*100:+.1f}%p)

### 4-3. 패턴 수준 비교 (10인 관찰 고정)
- D1_10 (10인+L1): {d1_10_avg*100:.1f}%
- D10  (10인+L2): {BASELINES['D10']['average']*100:.1f}%
- L2 vs L1 차이: {(BASELINES['D10']['average']-d1_10_avg)*100:+.1f}%p

---

## 5. 게임별 상세

"""

    for gk, gi in GAMES.items():
        report += f"### 5-{list(GAMES.keys()).index(gk)+1}. {gi['name']}\n\n"
        report += f"**D1_10 평균**: {scores[gk]['average']*100:.1f}%\n\n"

        details = scores[gk].get("details", [])
        if details:
            exact = [p for p in details if p["score"] >= 1.0]
            close = [p for p in details if 0.6 <= p["score"] < 1.0]
            partial = [p for p in details if 0.3 <= p["score"] < 0.6]
            wrong = [p for p in details if 0.0 < p["score"] < 0.3]
            missing = [p for p in details if p["score"] == 0.0]

            if exact:
                names = ", ".join(p["name"] for p in exact[:10])
                extra = f" 외 {len(exact)-10}개" if len(exact) > 10 else ""
                report += f"- 정확 (1.0): {len(exact)}개 -- {names}{extra}\n"
            if close:
                names = ", ".join(p["name"] for p in close[:8])
                report += f"- 근접 (0.7): {len(close)}개 -- {names}\n"
            if partial:
                names = ", ".join(p["name"] for p in partial[:8])
                report += f"- 부분 (0.4): {len(partial)}개 -- {names}\n"
            if wrong:
                names = ", ".join(p["name"] for p in wrong[:5])
                report += f"- 오답 (0.1): {len(wrong)}개 -- {names}\n"
            if missing:
                names = ", ".join(p["name"] for p in missing[:5])
                report += f"- 누락 (0.0): {len(missing)}개 -- {names}\n"
            report += "\n"

    # Conclusion with ranking
    report += "---\n\n## 6. 결론\n\n| 순위 | 조건 | 평균 일치도 |\n|------|------|----------|\n"
    all_conditions = [
        ("C", BASELINES["C"]["average"]), ("D1", BASELINES["D1"]["average"]),
        ("B1", BASELINES["B1"]["average"]), ("C10", BASELINES["C10"]["average"]),
        ("D1_10", d1_10_avg), ("D2", BASELINES["D2"]["average"]),
        ("B2", BASELINES["B2"]["average"]), ("D10", BASELINES["D10"]["average"]),
    ]
    all_conditions.sort(key=lambda x: x[1], reverse=True)
    for rank, (cond, avg) in enumerate(all_conditions, 1):
        marker = " **<--**" if cond == "D1_10" else ""
        report += f"| {rank} | {cond} | {avg*100:.1f}%{marker} |\n"

    report += f"""
---

## 부록: 실험 환경

| 항목 | 내용 |
|------|------|
| AI 모델 | Claude Sonnet 4.6 (스펙 생성, 채점) |
| Ground Truth | 3개 게임의 Unity C# 소스코드에서 직접 추출 |
| 파라미터 | 게임당 32개, 총 96개 |
| 관찰 데이터 | 10명 AI 테스터 합의 관찰 (기존 aggregated 데이터 재사용) |
| 패턴 카드 | Level 1 - 설계 의도만 (구체적 수치 힌트 없음) |
| 총 Claude CLI 호출 | 6회 (스펙 3 + 채점 3) |
| 실험일 | {datetime.now().strftime('%Y-%m-%d')} |
"""

    report_file = BASE / "결과보고서_D1_10.md"
    report_file.write_text(report, encoding="utf-8")
    log(f"  Report written: {report_file}")

    # Console summary
    log(f"\n  D1_10 Average: {d1_10_avg*100:.1f}%")
    for rank, (cond, avg) in enumerate(all_conditions, 1):
        marker = " <-- THIS" if cond == "D1_10" else ""
        log(f"    {rank}. {cond:6s}: {avg*100:.1f}%{marker}")

    log("\nPhase 3 complete.")


# ============================================================================
# MAIN
# ============================================================================

def main():
    start_time = time.time()
    log("=" * 60)
    log("D1-10 Experiment: 10-person observations + Level 1 patterns")
    log(f"Base: {BASE}")
    log("=" * 60)

    ensure_dirs()

    missing = []
    for gk in GAMES:
        agg = AGG_DIR / f"{gk}_10x_consensus.txt"
        pat = PAT_DIR / f"{gk}_patterns.yaml"
        gt = GT_DIR / f"{gk}_ground_truth.yaml"
        if not agg.exists(): missing.append(f"aggregated obs: {agg}")
        if not pat.exists(): missing.append(f"L1 pattern: {pat}")
        if not gt.exists(): missing.append(f"ground truth: {gt}")

    if missing:
        log("ERROR: Missing required input files:")
        for m in missing:
            log(f"  - {m}")
        sys.exit(1)

    log("All required input files verified.")

    phase1_specs()
    phase2_scoring()
    phase3_report()

    elapsed = time.time() - start_time
    log(f"\nAll phases complete! Total time: {elapsed/60:.1f} minutes")


if __name__ == "__main__":
    main()
