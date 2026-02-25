#!/usr/bin/env python3
"""
10x AI Tester Experiment: Clean Room Pattern Validation
=======================================================
3 games x 10 sessions = 30 sessions
Compares C10 (10-tester observations) vs D10 (10-tester + patterns)

Previous baselines (1-tester):
  C  (observation only):   36.5%
  D2 (observation+pattern): 96.3%
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

ADB = r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe"
DEVICE = "emulator-5554"
CLAUDE = r"C:\Users\user\AppData\Roaming\npm\claude.cmd"

BASE = Path(r"E:\AI\projects\CleanRoomTest\multi_tester")
GT_DIR = Path(r"E:\AI\projects\CleanRoomTest\ground_truth")
PAT_DIR = Path(r"E:\AI\projects\CleanRoomTest\pattern_cards\level2_structural_hint")

SESSIONS_DIR = BASE / "sessions"
OBS_DIR = BASE / "observations"
AGG_DIR = BASE / "aggregated"
SPECS_DIR = BASE / "specs"
SCORING_DIR = BASE / "scoring"

GAMES = {
    "tapshift":  {"name": "Tap Shift",  "package": "com.paxiegames.tapshift",   "prefix": "TS"},
    "magicsort": {"name": "Magic Sort", "package": "com.grandgames.magicsort",  "prefix": "MS"},
    "carmatch":  {"name": "Car Match",  "package": "com.grandgames.carmatch",   "prefix": "CM"},
}

# Per-game UI coordinates (portrait ~800x1280)
COORDS = {
    "tapshift": {
        "play": (400, 980), "settings": (690, 145),
        "center": (400, 550), "tl": (200, 350), "tr": (600, 350),
        "bl": (200, 750), "br": (600, 750),
        "booster": (400, 1100), "popup": (400, 800),
    },
    "magicsort": {
        "play": (400, 900), "settings": (690, 145),
        "center": (400, 500), "tl": (100, 350), "tr": (700, 350),
        "bl": (100, 700), "br": (700, 700),
        "booster": (400, 1050), "popup": (400, 800),
    },
    "carmatch": {
        "play": (400, 900), "settings": (690, 145),
        "center": (400, 450), "tl": (200, 250), "tr": (600, 250),
        "bl": (200, 650), "br": (600, 650),
        "booster": (400, 1050), "popup": (400, 800),
    },
}

SESSION_DESCS = {
    1:  "런치 + 메인 메뉴",
    2:  "기본 플레이 (2-3탭)",
    3:  "다중 탭 플레이 (5+)",
    4:  "설정 화면",
    5:  "보드 가장자리 탭",
    6:  "부스터 영역",
    7:  "재시작 흐름",
    8:  "장시간 플레이 (8+탭)",
    9:  "레벨 셀렉트 스크롤",
    10: "빠른 플레이 + 뒤로가기",
}

# 32 parameters per game (from full_comparison_report.yaml)
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

# Previous experiment baselines (1-tester)
BASELINES = {
    "C":  {"tapshift": 0.3344, "magicsort": 0.3469, "carmatch": 0.4125, "average": 0.3646},
    "D2": {"tapshift": 0.9625, "magicsort": 0.9344, "carmatch": 0.9906, "average": 0.9625},
}


# ============================================================================
# HELPERS
# ============================================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def ensure_dirs():
    for d in [SESSIONS_DIR, OBS_DIR, AGG_DIR, SPECS_DIR, SCORING_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def adb_run(*args, timeout=30):
    """Run ADB command and return CompletedProcess."""
    cmd = [ADB, "-s", DEVICE] + [str(a) for a in args]
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def take_screenshot(path):
    """Capture screenshot via ADB."""
    path.parent.mkdir(parents=True, exist_ok=True)
    r = adb_run("exec-out", "screencap", "-p")
    if r.returncode == 0 and r.stdout and len(r.stdout) > 1000:
        path.write_bytes(r.stdout)
        return True
    return False


def tap(x, y, wait=1.5):
    adb_run("shell", "input", "tap", str(int(x)), str(int(y)))
    time.sleep(wait)


def swipe(x1, y1, x2, y2, dur=300, wait=1.5):
    adb_run("shell", "input", "swipe",
            str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(dur)))
    time.sleep(wait)


def press_back(wait=1.5):
    adb_run("shell", "input", "keyevent", "KEYCODE_BACK")
    time.sleep(wait)


def force_stop(pkg):
    adb_run("shell", "am", "force-stop", pkg)
    time.sleep(1)


def launch_game(pkg, wait=8):
    adb_run("shell", "monkey", "-p", pkg, "-c",
            "android.intent.category.LAUNCHER", "1")
    time.sleep(wait)


def _clean_env():
    """Environment for Claude CLI: remove API key + session vars, set UTF-8."""
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    # Remove Claude Code session variables to allow nested invocation
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    env.pop("ANTHROPIC_MODEL", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def claude_vision(prompt, images, timeout=120):
    """Claude CLI with image analysis via Read tool.

    Prompt is sent via stdin. Image paths are referenced in the prompt
    and Claude uses the Read tool to load them.
    """
    # Build prompt that references image files
    img_list = "\n".join(f"  - {p}" for p in images)
    full_prompt = (
        f"다음 이미지 파일들을 Read 도구로 읽어서 분석하세요:\n{img_list}\n\n{prompt}"
    )
    cmd = [CLAUDE, "--print", "--model", "sonnet", "--allowed-tools", "Read"]
    try:
        r = subprocess.run(
            cmd, input=full_prompt, capture_output=True, encoding="utf-8",
            env=_clean_env(), timeout=timeout, cwd=str(BASE),
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return f"ERROR: rc={r.returncode} {r.stderr[:500]}"
    except subprocess.TimeoutExpired:
        return "ERROR: Timeout"
    except Exception as e:
        return f"ERROR: {e}"


def claude_text(prompt, timeout=300):
    """Claude CLI with text prompt via stdin."""
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


# ============================================================================
# PHASE 1: CAPTURE (30 sessions)
# ============================================================================

def capture_session(game_key, session_id):
    """Run one capture session, return list of screenshot Paths."""
    c = COORDS[game_key]
    sdir = SESSIONS_DIR / game_key / f"session_{session_id:02d}"
    sdir.mkdir(parents=True, exist_ok=True)
    shots = []

    def shot(name):
        p = sdir / f"{name}.png"
        if take_screenshot(p):
            shots.append(p)

    if session_id == 1:  # Launch + Main Menu
        shot("01_launch")
        tap(*c["popup"], wait=2)
        shot("02_main_menu")
        tap(*c["settings"], wait=2)
        shot("03_settings")

    elif session_id == 2:  # Basic Play (2-3 taps)
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("01_gameplay")
        tap(*c["center"], wait=1.5)
        tap(*c["tl"], wait=1.5)
        shot("02_after_taps")
        tap(*c["tr"], wait=1.5)
        shot("03_more_play")

    elif session_id == 3:  # Multi-tap Play (5+)
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("01_start")
        for pos in ["tl", "tr", "center", "bl", "br"]:
            tap(*c[pos], wait=1)
        shot("02_mid")
        tap(*c["center"], wait=1)
        tap(*c["tl"], wait=1)
        shot("03_after_many")

    elif session_id == 4:  # Settings
        tap(*c["popup"], wait=2)
        shot("01_main")
        tap(*c["settings"], wait=2)
        shot("02_settings")
        press_back(wait=1.5)
        shot("03_back")

    elif session_id == 5:  # Board Edge Taps
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("01_board")
        tap(50, 400, wait=1)
        tap(750, 400, wait=1)
        tap(400, 100, wait=1)
        tap(400, 1200, wait=1)
        shot("02_edges")
        shot("03_result")

    elif session_id == 6:  # Booster Area
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("01_gameplay")
        bx, by = c["booster"]
        tap(bx, by, wait=1.5)
        shot("02_booster")
        tap(bx - 200, by, wait=1.5)
        tap(bx + 200, by, wait=1.5)
        shot("03_boosters")

    elif session_id == 7:  # Restart Flow
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("01_playing")
        press_back(wait=1.5)
        shot("02_pause")
        tap(*c["popup"], wait=2)
        shot("03_after")

    elif session_id == 8:  # Extended Play (8+ taps)
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("01_start")
        for pos in ["center", "tl", "tr", "bl", "br", "center", "tl", "br"]:
            tap(*c[pos], wait=0.8)
        shot("02_many_taps")
        tap(*c["tr"], wait=0.8)
        tap(*c["bl"], wait=0.8)
        shot("03_extended")

    elif session_id == 9:  # Level Select Scroll
        tap(*c["popup"], wait=2)
        shot("01_level_select")
        swipe(400, 400, 400, 900, dur=500, wait=2)
        shot("02_scrolled_down")
        swipe(400, 900, 400, 200, dur=500, wait=2)
        swipe(400, 900, 400, 200, dur=500, wait=2)
        shot("03_scrolled_up")

    elif session_id == 10:  # Quick Play + Back
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        tap(*c["center"], wait=1)
        shot("01_quick")
        press_back(wait=1.5)
        shot("02_popup")
        tap(*c["popup"], wait=2)
        shot("03_final")

    return shots


def phase1_capture():
    """Phase 1: Capture 3 games x 10 sessions = 30 sessions."""
    log("=" * 60)
    log("PHASE 1: CAPTURE (3 games x 10 sessions = 30)")
    log("=" * 60)

    for gk, gi in GAMES.items():
        log(f"\n--- {gi['name']} ({gi['package']}) ---")
        for sid in range(1, 11):
            sdir = SESSIONS_DIR / gk / f"session_{sid:02d}"
            existing = list(sdir.glob("*.png")) if sdir.exists() else []
            if len(existing) >= 3:
                log(f"  Session {sid:02d}: {SESSION_DESCS[sid]} — already {len(existing)} shots, skip")
                continue

            log(f"  Session {sid:02d}: {SESSION_DESCS[sid]}")
            force_stop(gi["package"])
            launch_game(gi["package"], wait=8)
            shots = capture_session(gk, sid)
            log(f"    -> {len(shots)} screenshots")

        force_stop(gi["package"])

    log("\nPhase 1 complete.")


# ============================================================================
# PHASE 2: VISION ANALYSIS (30 Claude CLI calls)
# ============================================================================

VISION_PROMPT_TEMPLATE = """{game_name} 게임 - 세션 {sid} ({desc})

당신은 모바일 게임 전문 테스터입니다. 다음 스크린샷들을 분석하여 관찰 가능한 모든 게임 정보를 상세히 기록하세요.

분석 항목:
1. 게임 정체성: 제목, 부제, 장르, 아트 스타일
2. UI 구성: 메뉴 구조, 버튼, 아이콘, 레이아웃, 팝업
3. 게임 메커니즘: 조작 방식, 보드/필드 구조, 매칭/클리어 조건, 엔티티 종류와 수
4. 재화/점수: 코인, 젬, 별, 점수 시스템, 표시 위치와 현재 값
5. 난이도: 레벨 번호, 진행 구조, 보드 크기, 엔티티 수
6. 부스터: 종류, 수량, 아이콘 위치, 이름
7. 특수 기능: 힌트, 되돌리기, 설정 옵션, 장애물, 터널, 저장소

규칙:
- 스크린샷에서 직접 보이는 정보만 기록 (추측 최소화)
- 불확실한 정보는 "(불확실)" 표시
- 숫자 값(레벨 번호, 코인 수, 슬롯 수 등)은 정확하게 기록
- 색상, 크기, 배치 등 시각 정보도 기록"""


def phase2_vision():
    """Phase 2: Vision analysis for each session (30 calls)."""
    log("\n" + "=" * 60)
    log("PHASE 2: VISION ANALYSIS (30 calls)")
    log("=" * 60)

    for gk, gi in GAMES.items():
        log(f"\n--- {gi['name']} ---")
        for sid in range(1, 11):
            obs_file = OBS_DIR / f"{gk}_session_{sid:02d}.txt"
            if obs_file.exists() and obs_file.stat().st_size > 100:
                log(f"  Session {sid:02d}: already analyzed, skip")
                continue

            sdir = SESSIONS_DIR / gk / f"session_{sid:02d}"
            images = sorted(sdir.glob("*.png")) if sdir.exists() else []
            if not images:
                log(f"  Session {sid:02d}: no screenshots, skip")
                obs_file.write_text(f"ERROR: No screenshots for session {sid}\n", encoding="utf-8")
                continue

            log(f"  Session {sid:02d}: analyzing {len(images)} images...")
            prompt = VISION_PROMPT_TEMPLATE.format(
                game_name=gi["name"], sid=sid, desc=SESSION_DESCS[sid]
            )
            result = claude_vision(prompt, images, timeout=120)
            obs_file.write_text(result, encoding="utf-8")

            if result.startswith("ERROR"):
                log(f"    -> {result[:80]}")
            else:
                log(f"    -> {len(result)} chars")

    log("\nPhase 2 complete.")


# ============================================================================
# PHASE 3: AGGREGATION (3 Claude CLI calls)
# ============================================================================

def phase3_aggregate():
    """Phase 3: Aggregate 10 observations per game into consensus (3 calls)."""
    log("\n" + "=" * 60)
    log("PHASE 3: AGGREGATION (3 calls)")
    log("=" * 60)

    for gk, gi in GAMES.items():
        agg_file = AGG_DIR / f"{gk}_10x_consensus.txt"
        if agg_file.exists() and agg_file.stat().st_size > 100:
            log(f"  {gi['name']}: already aggregated, skip")
            continue

        log(f"  {gi['name']}: loading 10 observations...")
        obs_texts = []
        for sid in range(1, 11):
            obs_file = OBS_DIR / f"{gk}_session_{sid:02d}.txt"
            if obs_file.exists():
                text = obs_file.read_text(encoding="utf-8")
                if not text.startswith("ERROR"):
                    obs_texts.append(
                        f"=== 테스터 {sid} ({SESSION_DESCS[sid]}) ===\n{text}"
                    )

        if not obs_texts:
            log(f"    -> No valid observations, skip")
            continue

        log(f"  {gi['name']}: aggregating {len(obs_texts)} observations...")
        all_obs = "\n\n".join(obs_texts)

        prompt = f"""다음은 게임 "{gi['name']}"에 대한 {len(obs_texts)}명의 AI 테스터가 각각 독립적으로 관찰한 결과입니다.

{all_obs}

---

위 관찰들을 하나의 합의(consensus) 문서로 통합하세요.

통합 규칙:
1. 다수결 원칙: 과반수(6+/10) 이상이 동의하는 값을 대표값으로 채택
2. 모든 고유 관찰 포함: 1-2명만 관찰한 내용도 "(소수 관찰)" 표시로 포함
3. 신뢰도 표시: 각 항목에 (N/10) 형태로 동의 비율 표시
4. 충돌 해결: 서로 다른 값이 있으면 가장 빈도 높은 값 채택, 나머지는 대안으로 기록
5. 카테고리별 정리: 게임 정체성, UI, 메커니즘, 재화, 난이도, 부스터, 특수기능

출력 형식:
# {gi['name']} - 10인 AI 테스터 합의 관찰

## 1. 게임 정체성
(제목, 장르, 아트 스타일, 방향 등)

## 2. UI 구성
(메뉴, 버튼, 레이아웃 등)

## 3. 게임 메커니즘
(조작, 보드, 매칭/클리어, 엔티티 종류 등)

## 4. 재화/점수
(코인, 젬, 별, 점수 등)

## 5. 난이도/레벨
(레벨 수, 진행, 보드 크기 등)

## 6. 부스터
(종류, 수량, 기능 등)

## 7. 특수 기능
(힌트, 되돌리기, 장애물, 터널 등)"""

        result = claude_text(prompt, timeout=300)
        agg_file.write_text(result, encoding="utf-8")

        if result.startswith("ERROR"):
            log(f"    -> {result[:80]}")
        else:
            log(f"    -> {len(result)} chars consensus")

    log("\nPhase 3 complete.")


# ============================================================================
# PHASE 4: BALANCE SHEET GENERATION (6 Claude CLI calls)
# ============================================================================

def phase4_specs():
    """Phase 4: Generate balance sheets - C10 and D10 per game (6 calls)."""
    log("\n" + "=" * 60)
    log("PHASE 4: SPEC GENERATION (6 calls: 3 games x 2 conditions)")
    log("=" * 60)

    for gk, gi in GAMES.items():
        agg_file = AGG_DIR / f"{gk}_10x_consensus.txt"
        if not agg_file.exists():
            log(f"  {gi['name']}: no aggregated data, skip")
            continue
        agg_text = agg_file.read_text(encoding="utf-8")
        params = PARAM_LIST[gk]

        # --- C10: observations only ---
        c10_file = SPECS_DIR / f"{gk}_C10_spec.yaml"
        if c10_file.exists() and c10_file.stat().st_size > 100:
            log(f"  {gi['name']} C10: already exists, skip")
        else:
            log(f"  {gi['name']} C10: generating (observations only)...")
            prompt = f"""당신은 모바일 게임 밸런스 시트 전문가입니다.

다음은 게임 "{gi['name']}"에 대해 10명의 AI 테스터가 관찰한 결과를 집계한 데이터입니다:

{agg_text}

---

위 관찰 데이터만 사용하여 아래 32개 파라미터의 값을 추정하세요.
관찰에서 직접 확인할 수 없는 파라미터는 관찰 가능한 정보로부터 합리적으로 추론하되,
확신이 없으면 null로 표시하세요.

파라미터 목록:
{params}

YAML 형식으로 출력하세요:
game: "{gi['name']}"
condition: "C10"
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
            c10_file.write_text(result, encoding="utf-8")
            log(f"    -> {'ERROR' if result.startswith('ERROR') else f'{len(result)} chars'}")

        # --- D10: observations + patterns ---
        d10_file = SPECS_DIR / f"{gk}_D10_spec.yaml"
        if d10_file.exists() and d10_file.stat().st_size > 100:
            log(f"  {gi['name']} D10: already exists, skip")
        else:
            log(f"  {gi['name']} D10: generating (observations + patterns)...")
            pat_file = PAT_DIR / f"{gk}_patterns.yaml"
            pat_text = pat_file.read_text(encoding="utf-8") if pat_file.exists() else "(패턴 카드 없음)"

            prompt = f"""당신은 모바일 게임 밸런스 시트 전문가입니다.

다음은 게임 "{gi['name']}"에 대해 10명의 AI 테스터가 관찰한 결과를 집계한 데이터입니다:

{agg_text}

---

추가로 다음 구조적 힌트 패턴 카드를 참조하세요 (원본 소스에서 추출한 설계 패턴):

{pat_text}

---

위 관찰 데이터와 패턴 카드를 함께 활용하여 아래 32개 파라미터의 값을 추정하세요.
패턴 카드에 구체적 값(근사치 포함)이 있으면 우선 사용하고, 관찰 데이터로 보완하세요.

파라미터 목록:
{params}

YAML 형식으로 출력하세요:
game: "{gi['name']}"
condition: "D10"
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
            d10_file.write_text(result, encoding="utf-8")
            log(f"    -> {'ERROR' if result.startswith('ERROR') else f'{len(result)} chars'}")

    log("\nPhase 4 complete.")


# ============================================================================
# PHASE 5: SCORING (6 Claude CLI calls)
# ============================================================================

def phase5_scoring():
    """Phase 5: Score generated specs against ground truth (6 calls)."""
    log("\n" + "=" * 60)
    log("PHASE 5: SCORING (6 calls: 3 games x 2 conditions)")
    log("=" * 60)

    for gk, gi in GAMES.items():
        gt_file = GT_DIR / f"{gk}_ground_truth.yaml"
        if not gt_file.exists():
            log(f"  {gi['name']}: no ground truth, skip")
            continue
        gt_text = gt_file.read_text(encoding="utf-8")
        params = PARAM_LIST[gk]

        for cond in ["C10", "D10"]:
            score_file = SCORING_DIR / f"{gk}_{cond}_score.yaml"
            if score_file.exists() and score_file.stat().st_size > 100:
                log(f"  {gi['name']} {cond}: already scored, skip")
                continue

            spec_file = SPECS_DIR / f"{gk}_{cond}_spec.yaml"
            if not spec_file.exists():
                log(f"  {gi['name']} {cond}: no spec file, skip")
                continue
            spec_text = spec_file.read_text(encoding="utf-8")
            if spec_text.startswith("ERROR"):
                log(f"  {gi['name']} {cond}: spec has errors, skip")
                continue

            log(f"  {gi['name']} {cond}: scoring...")

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
  condition: "{cond}"
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

    log("\nPhase 5 complete.")


# ============================================================================
# PHASE 6: REPORT GENERATION
# ============================================================================

def extract_average(text):
    """Extract average score from scoring output text."""
    m = re.search(r'average:\s*([\d.]+)', text)
    return float(m.group(1)) if m else 0.0


def extract_sum(text):
    """Extract sum from scoring output text."""
    m = re.search(r'sum:\s*([\d.]+)', text)
    return float(m.group(1)) if m else 0.0


def extract_param_scores(text):
    """Extract individual parameter scores from scoring YAML."""
    results = []
    # Split on parameter blocks
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


def phase6_report():
    """Phase 6: Generate final comparison report in Korean."""
    log("\n" + "=" * 60)
    log("PHASE 6: REPORT GENERATION")
    log("=" * 60)

    # Collect scores
    scores = {}
    for gk in GAMES:
        scores[gk] = {}
        for cond in ["C10", "D10"]:
            sf = SCORING_DIR / f"{gk}_{cond}_score.yaml"
            if sf.exists():
                text = sf.read_text(encoding="utf-8")
                scores[gk][cond] = extract_average(text)
                scores[gk][f"{cond}_sum"] = extract_sum(text)
                scores[gk][f"{cond}_details"] = extract_param_scores(text)
            else:
                scores[gk][cond] = 0.0
                scores[gk][f"{cond}_sum"] = 0.0
                scores[gk][f"{cond}_details"] = []

    # Compute averages
    c10_avg = sum(scores[g]["C10"] for g in GAMES) / 3
    d10_avg = sum(scores[g]["D10"] for g in GAMES) / 3
    c_avg = BASELINES["C"]["average"]
    d2_avg = BASELINES["D2"]["average"]

    # Build report
    report = f"""# 10x AI 테스터 실험: 클린룸 패턴 검증 보고서

## 1. 실험 목적

1명의 AI 테스터 관찰이 아닌 **10명의 AI 테스터**가 독립적으로 관찰한 데이터를 집계하면,
관찰 정확도가 개선되는지를 검증합니다.

**핵심 질문**: N명 AI 테스터의 집계된 관찰이 1명보다 얼마나 나은가? 패턴 정보와 결합하면?

**비교 기준(원본 데이터)**: 각 게임의 Unity C# 소스코드에서 직접 추출한 밸런스 테이블
(상수, 알고리즘, 타이밍, 아키텍처 등 게임당 32개 핵심 파라미터)

**실험 대상**: 3개 모바일 퍼즐 게임 (Tap Shift, Magic Sort, Car Match)

---

## 2. 2-Way 비교 결과: 원본 대비 일치도 (%)

### 총괄표

| # | 테스트 조건 | Tap Shift | Magic Sort | Car Match | **평균 일치도** |
|---|-----------|-----------|------------|-----------|--------------|
| C10 | 10인 AI 관찰만 (패턴 없음) | {scores['tapshift']['C10']*100:.1f}% | {scores['magicsort']['C10']*100:.1f}% | {scores['carmatch']['C10']*100:.1f}% | **{c10_avg*100:.1f}%** |
| D10 | 10인 AI 관찰 + 패턴정보 | {scores['tapshift']['D10']*100:.1f}% | {scores['magicsort']['D10']*100:.1f}% | {scores['carmatch']['D10']*100:.1f}% | **{d10_avg*100:.1f}%** |

### 핵심 수치

- 10인 관찰만 (C10): **{c10_avg*100:.1f}%**
- 10인 + 패턴 (D10): **{d10_avg*100:.1f}%**
- 패턴 추가 효과 (C10→D10): **{(d10_avg-c10_avg)*100:+.1f}%p**

---

## 3. 이전 실험(1인) 대비 비교표

| 조건 | 설명 | Tap Shift | Magic Sort | Car Match | **평균** | **Δ vs 기준** |
|------|------|-----------|------------|-----------|---------|-------------|
| C (1인) | 1인 AI 관찰만 | {BASELINES['C']['tapshift']*100:.1f}% | {BASELINES['C']['magicsort']*100:.1f}% | {BASELINES['C']['carmatch']*100:.1f}% | **{c_avg*100:.1f}%** | 기준선 |
| **C10 (10인)** | 10인 AI 관찰만 | {scores['tapshift']['C10']*100:.1f}% | {scores['magicsort']['C10']*100:.1f}% | {scores['carmatch']['C10']*100:.1f}% | **{c10_avg*100:.1f}%** | **{(c10_avg-c_avg)*100:+.1f}%p** |
| D2 (1인) | 1인 AI + 패턴 | {BASELINES['D2']['tapshift']*100:.1f}% | {BASELINES['D2']['magicsort']*100:.1f}% | {BASELINES['D2']['carmatch']*100:.1f}% | **{d2_avg*100:.1f}%** | 기준선 |
| **D10 (10인)** | 10인 AI + 패턴 | {scores['tapshift']['D10']*100:.1f}% | {scores['magicsort']['D10']*100:.1f}% | {scores['carmatch']['D10']*100:.1f}% | **{d10_avg*100:.1f}%** | **{(d10_avg-d2_avg)*100:+.1f}%p** |

### 수치 요약

- **10인 집계 효과 (관찰만)**: C {c_avg*100:.1f}% → C10 {c10_avg*100:.1f}% ({(c10_avg-c_avg)*100:+.1f}%p)
- **10인 집계 효과 (패턴 포함)**: D2 {d2_avg*100:.1f}% → D10 {d10_avg*100:.1f}% ({(d10_avg-d2_avg)*100:+.1f}%p)
- **패턴 정보의 효과 (10인)**: C10 {c10_avg*100:.1f}% → D10 {d10_avg*100:.1f}% ({(d10_avg-c10_avg)*100:+.1f}%p)

---

## 4. 상세 분석

"""

    # Per-game detailed analysis
    for gk, gi in GAMES.items():
        report += f"### 4-{list(GAMES.keys()).index(gk)+1}. {gi['name']}\n\n"

        c10_det = scores[gk].get("C10_details", [])
        d10_det = scores[gk].get("D10_details", [])
        c10_by_id = {p["id"]: p for p in c10_det}
        d10_by_id = {p["id"]: p for p in d10_det}

        # C10 summary
        report += f"**C10 (관찰만)**: 평균 {scores[gk]['C10']*100:.1f}%\n\n"
        if c10_det:
            exact = [p for p in c10_det if p["score"] >= 1.0]
            close = [p for p in c10_det if 0.6 <= p["score"] < 1.0]
            missing = [p for p in c10_det if p["score"] == 0.0]
            wrong = [p for p in c10_det if 0.0 < p["score"] <= 0.1]

            if exact:
                names = ", ".join(p["name"] for p in exact[:8])
                report += f"- 정확 (1.0): {len(exact)}개 — {names}\n"
            if close:
                names = ", ".join(p["name"] for p in close[:5])
                report += f"- 근접 (0.7): {len(close)}개 — {names}\n"
            if missing:
                names = ", ".join(p["name"] for p in missing[:8])
                report += f"- 누락 (0.0): {len(missing)}개 — {names}\n"
            if wrong:
                names = ", ".join(p["name"] for p in wrong[:5])
                report += f"- 오답 (0.1): {len(wrong)}개 — {names}\n"
            report += "\n"

        # D10 summary
        report += f"**D10 (관찰 + 패턴)**: 평균 {scores[gk]['D10']*100:.1f}%\n\n"
        if d10_det:
            exact = [p for p in d10_det if p["score"] >= 1.0]
            missing = [p for p in d10_det if p["score"] == 0.0]
            if exact:
                names = ", ".join(p["name"] for p in exact[:8])
                extra = f" 외 {len(exact)-8}개" if len(exact) > 8 else ""
                report += f"- 정확 (1.0): {len(exact)}개 — {names}{extra}\n"
            if missing:
                names = ", ".join(p["name"] for p in missing[:5])
                report += f"- 누락 (0.0): {len(missing)}개 — {names}\n"
            report += "\n"

        # Compare C10 vs D10
        if c10_det and d10_det:
            improved = []
            degraded = []
            for pid in c10_by_id:
                if pid in d10_by_id:
                    cs = c10_by_id[pid]["score"]
                    ds = d10_by_id[pid]["score"]
                    if ds > cs:
                        improved.append((c10_by_id[pid]["name"], cs, ds))
                    elif ds < cs:
                        degraded.append((c10_by_id[pid]["name"], cs, ds))

            if improved:
                report += f"**패턴 추가로 개선 ({len(improved)}개)**:\n\n"
                report += "| 파라미터 | C10 | D10 |\n|---------|-----|-----|\n"
                for name, cs, ds in improved[:10]:
                    report += f"| {name} | {cs:.1f} | {ds:.1f} |\n"
                report += "\n"

            if degraded:
                report += f"**패턴 추가로 악화 ({len(degraded)}개)**:\n\n"
                report += "| 파라미터 | C10 | D10 |\n|---------|-----|-----|\n"
                for name, cs, ds in degraded[:5]:
                    report += f"| {name} | {cs:.1f} | {ds:.1f} |\n"
                report += "\n"

    # Conclusion
    report += """---

## 5. 결론

| 조건 | 원본 대비 일치도 | 1인 대비 변화 |
|------|---------------|-------------|
"""
    report += f"| C (1인 관찰만) | **{c_avg*100:.1f}%** | 기준선 |\n"
    report += f"| **C10 (10인 관찰만)** | **{c10_avg*100:.1f}%** | **{(c10_avg-c_avg)*100:+.1f}%p** |\n"
    report += f"| D2 (1인 + 패턴) | **{d2_avg*100:.1f}%** | 기준선 |\n"
    report += f"| **D10 (10인 + 패턴)** | **{d10_avg*100:.1f}%** | **{(d10_avg-d2_avg)*100:+.1f}%p** |\n\n"

    if c10_avg > c_avg:
        delta = (c10_avg - c_avg) * 100
        report += f"10명의 AI 테스터를 집계하면 관찰 정확도가 {c_avg*100:.1f}% → {c10_avg*100:.1f}%로 "
        report += f"**{delta:+.1f}%p 향상**됩니다.\n\n"
    else:
        report += f"10명의 AI 테스터 집계에도 관찰 정확도는 {c10_avg*100:.1f}%로, "
        report += f"1인({c_avg*100:.1f}%) 대비 의미 있는 개선이 없습니다.\n\n"

    if d10_avg > d2_avg:
        report += f"패턴 카드와 결합 시, 10인 집계(D10: {d10_avg*100:.1f}%)가 "
        report += f"1인(D2: {d2_avg*100:.1f}%)보다 **{(d10_avg-d2_avg)*100:+.1f}%p 향상**됩니다.\n\n"
    elif abs(d10_avg - d2_avg) < 0.02:
        report += f"패턴 카드와 결합 시, 10인 집계(D10: {d10_avg*100:.1f}%)는 "
        report += f"1인(D2: {d2_avg*100:.1f}%)과 유사한 수준입니다 ({(d10_avg-d2_avg)*100:+.1f}%p).\n\n"
    else:
        report += f"패턴 카드와 결합 시, 10인 집계(D10: {d10_avg*100:.1f}%)는 "
        report += f"1인(D2: {d2_avg*100:.1f}%)보다 {(d10_avg-d2_avg)*100:+.1f}%p입니다.\n\n"

    pattern_effect = (d10_avg - c10_avg) * 100
    report += f"패턴 정보의 기여도(C10→D10): **{pattern_effect:+.1f}%p** "
    report += f"(이전 1인 실험 C→D2: {(d2_avg-c_avg)*100:+.1f}%p)\n"

    # Appendix
    report += f"""
---

## 부록: 실험 환경

| 항목 | 내용 |
|------|------|
| AI 모델 | Claude Sonnet 4.6 (비전 분석, 스펙 생성, 채점) |
| Ground Truth | 3개 게임의 Unity C# 소스코드에서 직접 추출 |
| 파라미터 | 게임당 32개, 총 96개 |
| AI 테스터 수 | 10명 (게임당 10개 독립 세션) |
| 총 세션 수 | 30 (3게임 × 10세션) |
| 스크린샷 | 세션당 3장, 총 90장 |
| 총 Claude CLI 호출 | ~45회 (비전 30 + 집계 3 + 스펙 6 + 채점 6) |
| 총 채점 수 | 192 (96 파라미터 × 2 조건) |
| 에뮬레이터 | BlueStacks (Pie64) + ADB (emulator-5554) |
| 세션 전략 | 메뉴/플레이/설정/부스터/스크롤 등 10가지 탐색 패턴 |
| 실험일 | {datetime.now().strftime('%Y-%m-%d')} |
"""

    report_file = BASE / "결과보고서_10x.md"
    report_file.write_text(report, encoding="utf-8")
    log(f"  Report written: {report_file}")
    log(f"  C10 average: {c10_avg*100:.1f}%")
    log(f"  D10 average: {d10_avg*100:.1f}%")
    log(f"  C(1) baseline: {c_avg*100:.1f}%, D2(1) baseline: {d2_avg*100:.1f}%")

    log("\nPhase 6 complete.")


# ============================================================================
# MAIN
# ============================================================================

def main():
    start_time = time.time()
    log("=" * 60)
    log("10x AI Tester Experiment: Clean Room Pattern Validation")
    log(f"Base: {BASE}")
    log("=" * 60)

    ensure_dirs()

    # Check ADB device
    r = adb_run("devices")
    if DEVICE.encode() not in r.stdout:
        log(f"ERROR: Device {DEVICE} not found.")
        log("Start BlueStacks first, then re-run.")
        sys.exit(1)
    log(f"ADB device {DEVICE} connected.")

    phase1_capture()
    phase2_vision()
    phase3_aggregate()
    phase4_specs()
    phase5_scoring()
    phase6_report()

    elapsed = time.time() - start_time
    log(f"\nAll phases complete! Total time: {elapsed/60:.1f} minutes")


if __name__ == "__main__":
    main()
