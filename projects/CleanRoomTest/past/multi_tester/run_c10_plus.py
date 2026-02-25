#!/usr/bin/env python3
"""
C10+ Enhanced 10-Person Observation Experiment
===============================================
Specialized Missions + Cross-Validation (no pattern cards)
Condition: C10_plus (pure observation only)

Previous baselines:
  C   (1-person free play):   0.365
  C10 (10-person free play):  0.850
  Target: C10+ = 0.88~0.90
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

SESSIONS_DIR = BASE / "sessions_plus"
OBS_DIR = BASE / "observations_plus"
AGG_DIR = BASE / "aggregated"
SPECS_DIR = BASE / "specs"
SCORING_DIR = BASE / "scoring"

GAMES = {
    "tapshift":  {"name": "Tap Shift",  "package": "com.paxiegames.tapshift",   "prefix": "TS"},
    "magicsort": {"name": "Magic Sort", "package": "com.grandgames.magicsort",  "prefix": "MS"},
    "carmatch":  {"name": "Car Match",  "package": "com.grandgames.carmatch",   "prefix": "CM"},
}

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

SESSION_MISSIONS = {
    1:  {"name": "Full Playthrough A",     "domain": "gameplay",         "desc": "레벨 1부터 10+레벨 진행, 난이도 곡선 관찰"},
    2:  {"name": "Full Playthrough B",     "domain": "gameplay",         "desc": "독립 플레이스루, 메뉴 탐색 포함 교차검증"},
    3:  {"name": "Numeric Data Collection","domain": "numeric",          "desc": "레벨별 수치(오브젝트수, 색상수, 별점) 수집"},
    4:  {"name": "Timing Observation",     "domain": "timing",           "desc": "애니메이션 속도, 전환 시간, 이동 타이밍 관찰"},
    5:  {"name": "Visual Measurement",     "domain": "visual",           "desc": "격자 크기, 간격, 색상, UI 레이아웃 측정"},
    6:  {"name": "Edge Case Testing",      "domain": "edge_case",        "desc": "한계값 테스트 - 힌트/되돌리기/생명 소진"},
    7:  {"name": "Economy Tracking",       "domain": "economy",          "desc": "초기 재화, 레벨 보상, 상점 가격 추적"},
    8:  {"name": "Algorithm Behavior",     "domain": "algorithm",        "desc": "경로탐색, 충돌판정, 레벨생성 방식 추론"},
    9:  {"name": "State & Flow Mapping",   "domain": "state",            "desc": "화면 전환, 팝업 목록, 상태 머신 매핑"},
    10: {"name": "Cross-Validation",       "domain": "cross_validation", "desc": "약점 항목 재확인, 별점 기준 정밀 관찰"},
}

# Mission-specific vision prompts
VISION_PROMPTS = {
    1: """{game_name} 게임 - 전문가 1: Full Playthrough A

당신은 게임 구조 분석 전문가입니다. 이 스크린샷들은 레벨 1부터 순서대로 진행한 플레이스루입니다.

분석 항목:
1. 총 레벨 수 (레벨 선택 화면에서 확인)
2. 레벨별 보드/격자 크기 변화 (숫자로 기록)
3. 레벨별 오브젝트(화살표/병/자동차) 수 변화
4. 난이도 전환점 (새 메커니즘 등장 레벨)
5. 챕터/구간 구조
6. 클리어 조건, 실패 조건

규칙: 모든 숫자를 정확히 기록. 레벨 번호와 관찰값을 테이블로 정리.""",

    2: """{game_name} 게임 - 전문가 2: Full Playthrough B (교차검증)

당신은 게임 구조 분석 전문가입니다. 이 스크린샷들은 독립적인 두 번째 플레이스루입니다.

분석 항목 (전문가 1과 동일하지만 독립 관찰):
1. 총 레벨 수, 챕터 구조
2. 레벨별 보드 크기, 오브젝트 수 변화
3. 난이도 전환점
4. 메뉴 구조, 버튼 배치, UI 요소
5. 게임 정체성 (제목, 장르, 아트 스타일)

규칙: 전문가 1의 결과를 보지 않고 독립 분석. 모든 숫자를 테이블로 정리.""",

    3: """{game_name} 게임 - 전문가 3: 수치 역추정 전문가

당신은 게임 밸런스 수치 분석 전문가입니다. 스크린샷에서 정확한 숫자값을 추출하세요.

필수 수집 데이터:
1. 별점 기준: 실수 0회=?성, 1회=?성, 2회=?성, 3+회=?성
2. 점수/코인 보상: 별점별 보상량
3. 레벨별 데이터 (테이블): 레벨#, 격자크기, 오브젝트수, 색상수, 목표이동수
4. 진행 공식 추정: 위 데이터에서 패턴/공식 역산
5. 부스터 수량, 한계값

출력 형식: 반드시 정확한 숫자를 테이블로 정리. 추정값은 (추정) 표시.""",

    4: """{game_name} 게임 - 전문가 4: 타이밍 측정 전문가

당신은 게임 애니메이션 타이밍 분석 전문가입니다. 스크린샷의 상태 변화로 타이밍을 추론하세요.

분석 항목:
1. 오브젝트 이동 애니메이션: 시작→종료 상태, 추정 소요 시간
2. 이동 가속/감속 패턴: 등속 vs ease-in vs ease-out
3. 이동 중 변형: 늘어남(stretch), 축소, 회전 여부
4. 매칭/완성 연출: 사라짐, 바운스, 스케일 변화
5. 팝업 애니메이션: 등장/퇴장 방식
6. 페이지 전환: 페이드, 슬라이드, 즉시
7. 피드백 애니메이션: 막힘 흔들림, 힌트 펄스

규칙: 스크린샷 간 변화로 대략적 시간 추정. 초 단위로 기록.""",

    5: """{game_name} 게임 - 전문가 5: 시각 측정 전문가

당신은 UI/UX 측정 전문가입니다. 스크린샷에서 다음을 픽셀 단위로 분석하세요.

필수 측정:
1. 격자/보드: 전체 크기, 셀 크기, 셀 간격 (px 단위)
2. 오브젝트: 크기, 격자 대비 비율 (model_scale)
3. 홀더/병 영역: 위치(Y좌표), 슬롯 간격
4. UI 요소: 버튼 크기, 여백, 상단/하단 바 높이
5. 색상: 주요 오브젝트 색상의 HEX 코드 (가능한 정확하게)
6. 화면 비율: 해상도 추정 (16:9, 9:16 등)
7. Y 오프셋: 보드 시작 Y좌표

출력: 모든 측정값을 px 단위 숫자로 기록. 비율은 소수점으로.""",

    6: """{game_name} 게임 - 전문가 6: 경계조건 탐색 전문가

당신은 게임 한계값 테스트 전문가입니다. 리소스 고갈과 극단적 상태를 분석하세요.

필수 확인:
1. 되돌리기(Undo): 최대 몇 회 가능? 소진 후 UI 변화?
2. 힌트: 최대 몇 개? 소진 후 UI 변화?
3. 생명(Lives): 최대 몇 개? 소진 과정? 회복 메커니즘?
4. 부스터: 각 종류별 초기 수량? 소진 후 구매 UI?
5. 홀더/병: 최대 용량? 가득 찰 때의 동작?
6. 실패 조건: 정확히 어떤 상태에서 실패 판정?
7. 재시작 흐름: 실패 후 선택지 (재시작, 부스터 구매, 메뉴)

규칙: 정확한 최대/최소 숫자 기록. 소진 전후 상태 비교.""",

    7: """{game_name} 게임 - 전문가 7: 경제 시스템 전문가

당신은 게임 경제 분석 전문가입니다. 재화 흐름을 정밀 추적하세요.

필수 추적:
1. 초기 재화: 게임 최초 시작 시 코인/젬 수 (정확한 숫자)
2. 레벨 보상: 레벨별 (별점, 코인 보상) 쌍 기록
3. 부스터 가격: 각 부스터의 코인/젬 가격
4. 일일 보상: 7일 주기 보상 (가능한 범위까지)
5. 여정/마일스톤 보상: 레벨 마일스톤별 보상
6. 광고 빈도: 몇 레벨마다 전면광고 노출?
7. IAP 상품: 상점에 표시된 상품과 가격

출력: 모든 재화값을 정확한 숫자로 기록. 보상 테이블 작성.""",

    8: """{game_name} 게임 - 전문가 8: 알고리즘 행동 분석 전문가

당신은 게임 알고리즘 추론 전문가입니다. 외부 행동에서 내부 알고리즘을 추론하세요.

분석 항목:
1. 경로 탐색: 자동차/오브젝트가 장애물을 어떻게 우회하는가? (최단경로? 휴리스틱?)
2. 충돌 판정: 이동 가능/불가능을 어떻게 결정하는가? (AABB? 원형? 레이캐스트?)
3. 레벨 생성: 같은 레벨 재시작 시 배치가 바뀌나? (절차적 vs 고정)
4. 힌트 로직: 힌트가 추천하는 수의 패턴은? (최적? 랜덤? 점수기반?)
5. 매칭 검사: 연속 동일 타입 감지 방식
6. 교착 판정: 더 이상 진행 불가한 상태를 감지하는가?

규칙: 관찰된 행동 패턴에서 논리적으로 추론. 확실한 것과 추론을 구분.""",

    9: """{game_name} 게임 - 전문가 9: 상태/흐름 매핑 전문가

당신은 게임 상태 머신 분석 전문가입니다. 모든 화면과 전환을 매핑하세요.

필수 매핑:
1. 화면 목록: 모든 고유 화면(메인메뉴, 게임, 일시정지, 완료, 실패 등)
2. 전환 다이어그램: 화면 A -> 화면 B (어떤 동작으로)
3. 팝업 목록: 모든 팝업 종류와 출현 조건
4. 설정 옵션: 설정 화면의 모든 항목
5. 저장 동작: 앱 종료 후 재시작 시 보존되는 상태
6. 게임 상태 수: 총 몇 개의 상태가 존재하는가?

출력: 상태 목록과 전환 다이어그램을 텍스트로 작성.""",

    10: """{game_name} 게임 - 전문가 10: 교차검증 전문가

당신은 게임 데이터 검증 전문가입니다. 핵심 파라미터를 정밀 재확인하세요.

집중 확인 항목:
1. 별점 기준: 실수 횟수별 별점 변화를 정밀 관찰
2. 레벨 진행: 격자 크기가 정확히 몇 레벨에서 바뀌는지
3. 부스터 상세: 각 부스터의 정확한 효과와 초기 수량
4. 색상 수: 초반/중반/후반 활성 색상 수
5. 난이도 전환: 어느 레벨에서 체감 난이도가 급변하는지

규칙: 최대한 정밀하게 관찰. 불확실하면 여러 번 시도하여 확인.""",
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
    "C":   {"average": 0.365, "tapshift": 0.334, "magicsort": 0.347, "carmatch": 0.413},
    "C10": {"average": 0.850, "tapshift": 0.844, "magicsort": 0.859, "carmatch": 0.847},
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
    cmd = [ADB, "-s", DEVICE] + [str(a) for a in args]
    return subprocess.run(cmd, capture_output=True, timeout=timeout)


def take_screenshot(path):
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
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    env.pop("ANTHROPIC_MODEL", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def claude_vision(prompt, images, timeout=180):
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
        if id_m and score_m:
            results.append({
                "id": id_m.group(1),
                "name": name_m.group(1).strip() if name_m else "",
                "score": float(score_m.group(1)),
            })
    return results


# ============================================================================
# PHASE 1: CAPTURE (30 specialized sessions)
# ============================================================================

def play_level(c, taps=5, wait_after=2):
    """Helper: play one level with N taps then wait."""
    positions = ["center", "tl", "tr", "bl", "br", "center", "tl", "tr"]
    for i in range(min(taps, len(positions))):
        tap(*c[positions[i]], wait=0.8)
    time.sleep(wait_after)


def capture_session(game_key, session_id):
    c = COORDS[game_key]
    sdir = SESSIONS_DIR / game_key / f"session_{session_id:02d}"
    sdir.mkdir(parents=True, exist_ok=True)
    shots = []

    def shot(name):
        p = sdir / f"{name}.png"
        if take_screenshot(p):
            shots.append(p)

    # --- Session 1: Full Playthrough A (8 shots) ---
    if session_id == 1:
        tap(*c["popup"], wait=2)
        shot("01_main_menu")
        # Play levels 1-3
        tap(*c["play"], wait=3)
        shot("02_level1_board")
        play_level(c, taps=3)
        shot("03_level1_result")
        # Continue to level 3
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        play_level(c, taps=4)
        shot("04_level3_board")
        # Continue to level 5
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        play_level(c, taps=5)
        shot("05_level5_result")
        # Skip to higher levels
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        play_level(c, taps=6)
        shot("06_higher_level")
        # Level select scroll
        press_back(wait=1.5)
        tap(*c["popup"], wait=2)
        shot("07_level_select")
        swipe(400, 800, 400, 200, dur=500, wait=2)
        shot("08_level_select_scrolled")

    # --- Session 2: Full Playthrough B (8 shots) ---
    elif session_id == 2:
        tap(*c["popup"], wait=2)
        shot("01_main_menu_b")
        tap(*c["settings"], wait=2)
        shot("02_settings")
        press_back(wait=1.5)
        tap(*c["play"], wait=3)
        shot("03_level1_b")
        play_level(c, taps=3)
        shot("04_level1_result_b")
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("05_level2_b")
        play_level(c, taps=4)
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        play_level(c, taps=5)
        shot("06_level3_result_b")
        tap(*c["popup"], wait=2)
        shot("07_progression_b")
        swipe(400, 400, 400, 800, dur=500, wait=2)
        shot("08_scroll_b")

    # --- Session 3: Numeric Data Collection (6 shots) ---
    elif session_id == 3:
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("01_level_start_board")
        # Perfect play
        play_level(c, taps=3)
        shot("02_perfect_result")
        # Play with 2 mistakes
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        tap(50, 400, wait=0.5)  # intentional miss
        tap(50, 400, wait=0.5)  # intentional miss
        play_level(c, taps=4)
        shot("03_2mistake_result")
        # Play with 5 mistakes
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        for _ in range(5):
            tap(50, 400, wait=0.3)
        play_level(c, taps=5)
        shot("04_5mistake_result")
        # Higher level for data
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("05_higher_level_board")
        play_level(c, taps=6)
        shot("06_higher_level_result")

    # --- Session 4: Timing Observation (5 shots) ---
    elif session_id == 4:
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("01_before_move")
        tap(*c["center"], wait=0.3)  # capture mid-animation
        shot("02_during_move")
        time.sleep(1)
        shot("03_after_move")
        # Trigger popup
        play_level(c, taps=4)
        shot("04_popup_appearing")
        time.sleep(0.5)
        shot("05_popup_visible")

    # --- Session 5: Visual Measurement (6 shots) ---
    elif session_id == 5:
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("01_small_grid_clean")
        time.sleep(1)
        shot("02_grid_detail")
        # Higher level for larger grid
        play_level(c, taps=4)
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("03_medium_grid")
        play_level(c, taps=5)
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("04_larger_grid")
        # UI overlay
        press_back(wait=1.5)
        shot("05_ui_overlay")
        tap(*c["popup"], wait=2)
        tap(*c["settings"], wait=2)
        shot("06_settings_ui")

    # --- Session 6: Edge Case Testing (6 shots) ---
    elif session_id == 6:
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        # Use all hints
        bx, by = c["booster"]
        for i in range(5):
            tap(bx - 200, by, wait=1)
        shot("01_hints_used")
        # Use all undos
        tap(*c["center"], wait=0.8)
        for i in range(12):
            tap(bx, by, wait=0.5)
        shot("02_undos_used")
        # Force fail
        press_back(wait=1.5)
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        for _ in range(8):
            tap(*c["tl"], wait=0.3)
            tap(*c["br"], wait=0.3)
        time.sleep(3)
        shot("03_near_fail")
        shot("04_fail_state")
        # Booster shop
        tap(*c["booster"], wait=2)
        shot("05_booster_shop")
        tap(*c["popup"], wait=2)
        shot("06_after_fail")

    # --- Session 7: Economy Tracking (6 shots) ---
    elif session_id == 7:
        tap(*c["popup"], wait=2)
        shot("01_initial_coins")
        tap(*c["play"], wait=3)
        play_level(c, taps=3)
        shot("02_level1_reward")
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        play_level(c, taps=4)
        shot("03_level2_reward")
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        play_level(c, taps=5)
        shot("04_level3_reward")
        tap(*c["popup"], wait=2)
        tap(200, 145, wait=2)  # shop button area
        shot("05_shop")
        press_back(wait=1.5)
        shot("06_coins_after_levels")

    # --- Session 8: Algorithm Behavior (5 shots) ---
    elif session_id == 8:
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("01_initial_layout")
        # Tap blocked areas
        tap(50, 400, wait=1)
        tap(750, 400, wait=1)
        shot("02_blocked_feedback")
        # Play and observe paths
        tap(*c["center"], wait=2)
        tap(*c["tl"], wait=2)
        shot("03_movement_path")
        # Restart same level
        press_back(wait=1.5)
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("04_restart_layout_1")
        press_back(wait=1.5)
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        shot("05_restart_layout_2")

    # --- Session 9: State & Flow Mapping (6 shots) ---
    elif session_id == 9:
        tap(*c["popup"], wait=2)
        shot("01_main_menu")
        tap(*c["play"], wait=3)
        shot("02_gameplay")
        press_back(wait=1.5)
        shot("03_pause_popup")
        tap(*c["popup"], wait=2)
        play_level(c, taps=5)
        shot("04_complete_popup")
        tap(*c["popup"], wait=2)
        tap(*c["settings"], wait=2)
        shot("05_settings")
        press_back(wait=1.5)
        # Try triggering fail
        tap(*c["play"], wait=3)
        for _ in range(6):
            tap(*c["tl"], wait=0.3)
            tap(*c["br"], wait=0.3)
        time.sleep(3)
        shot("06_fail_popup")

    # --- Session 10: Cross-Validation (5 shots) ---
    elif session_id == 10:
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        # Perfect play -> 3 star
        play_level(c, taps=3)
        shot("01_3star_attempt")
        # Poor play -> 1 star
        tap(*c["popup"], wait=2)
        tap(*c["play"], wait=3)
        for _ in range(6):
            tap(50, 400, wait=0.3)
        play_level(c, taps=5)
        shot("02_1star_attempt")
        # Level progression
        tap(*c["popup"], wait=2)
        shot("03_progression")
        # Booster detail
        tap(*c["play"], wait=3)
        tap(c["booster"][0], c["booster"][1], wait=2)
        shot("04_booster_detail")
        # Difficulty transition
        press_back(wait=1.5)
        tap(*c["popup"], wait=2)
        swipe(400, 800, 400, 200, dur=500, wait=2)
        shot("05_later_levels")

    return shots


def phase1_capture():
    log("=" * 60)
    log("PHASE 1: CAPTURE (3 games x 10 specialized sessions)")
    log("=" * 60)

    for gk, gi in GAMES.items():
        log(f"\n--- {gi['name']} ({gi['package']}) ---")
        for sid in range(1, 11):
            mission = SESSION_MISSIONS[sid]
            sdir = SESSIONS_DIR / gk / f"session_{sid:02d}"
            existing = list(sdir.glob("*.png")) if sdir.exists() else []
            if len(existing) >= 4:
                log(f"  Session {sid:02d}: {mission['name']} -already {len(existing)} shots, skip")
                continue

            log(f"  Session {sid:02d}: {mission['name']}")
            force_stop(gi["package"])
            launch_game(gi["package"], wait=8)
            shots = capture_session(gk, sid)
            log(f"    -> {len(shots)} screenshots")

        force_stop(gi["package"])

    log("\nPhase 1 complete.")


# ============================================================================
# PHASE 2: VISION ANALYSIS (30 mission-specific calls)
# ============================================================================

def phase2_vision():
    log("\n" + "=" * 60)
    log("PHASE 2: VISION ANALYSIS (30 mission-specific calls)")
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
                obs_file.write_text(f"ERROR: No screenshots\n", encoding="utf-8")
                continue

            mission = SESSION_MISSIONS[sid]
            log(f"  Session {sid:02d}: {mission['name']} -{len(images)} images...")

            prompt = VISION_PROMPTS[sid].format(game_name=gi["name"])
            result = claude_vision(prompt, images, timeout=180)
            obs_file.write_text(result, encoding="utf-8")

            if result.startswith("ERROR"):
                log(f"    -> {result[:80]}")
            else:
                log(f"    -> {len(result)} chars")

    log("\nPhase 2 complete.")


# ============================================================================
# PHASE 3: ENHANCED AGGREGATION (expert-weighted, 3 calls)
# ============================================================================

def phase3_aggregate():
    log("\n" + "=" * 60)
    log("PHASE 3: ENHANCED AGGREGATION (expert-weighted)")
    log("=" * 60)

    for gk, gi in GAMES.items():
        agg_file = AGG_DIR / f"{gk}_10x_plus_consensus.txt"
        if agg_file.exists() and agg_file.stat().st_size > 100:
            log(f"  {gi['name']}: already aggregated, skip")
            continue

        log(f"  {gi['name']}: loading specialist observations...")
        obs_texts = []
        for sid in range(1, 11):
            obs_file = OBS_DIR / f"{gk}_session_{sid:02d}.txt"
            if obs_file.exists():
                text = obs_file.read_text(encoding="utf-8")
                if not text.startswith("ERROR"):
                    m = SESSION_MISSIONS[sid]
                    obs_texts.append(
                        f"=== 전문가 {sid}: {m['name']} (도메인: {m['domain']}) ===\n"
                        f"미션: {m['desc']}\n\n{text}"
                    )

        if not obs_texts:
            log(f"    -> No valid observations, skip")
            continue

        log(f"  {gi['name']}: aggregating {len(obs_texts)} specialist observations...")
        all_obs = "\n\n".join(obs_texts)

        prompt = f"""게임 "{gi['name']}"에 대한 {len(obs_texts)}명의 전문가 AI 테스터 관찰을 통합하세요.
각 테스터는 다른 전문 도메인을 담당했습니다.

{all_obs}

---

통합 규칙 (전문가 도메인 가중치 적용):
1. 도메인 전문성 우선: 해당 도메인 전문가 데이터를 일반 관찰보다 우선
   - 수치 → 전문가 3(Numeric), 타이밍 → 전문가 4(Timing), 시각 → 전문가 5(Visual)
   - 경제 → 전문가 7(Economy), 알고리즘 → 전문가 8(Algorithm), 상태 → 전문가 9(State)
2. 교차검증: 전문가 1과 2의 독립 플레이스루 비교
3. 전문가 10의 재확인으로 신뢰도 상향
4. 측정 정밀도: 전문가 3, 5의 구체적 수치 > 대략적 추정

출력: 12개 섹션으로 구성된 합의 문서
1. 게임 정체성  2. UI 구성  3. 게임 메커니즘  4. 수치 데이터 (Numeric Expert)
5. 시각 측정 (Visual Expert)  6. 재화/경제 (Economy Expert)
7. 난이도/레벨 진행  8. 부스터/특수기능  9. 타이밍 (Timing Expert)
10. 알고리즘 추론 (Algorithm Expert)  11. 상태/흐름 (State Expert)
12. 한계값 (Edge Case Expert)

각 항목에 [HIGH]/[MED]/[LOW] 신뢰도 표시."""

        result = claude_text(prompt, timeout=300)
        agg_file.write_text(result, encoding="utf-8")

        if result.startswith("ERROR"):
            log(f"    -> {result[:80]}")
        else:
            log(f"    -> {len(result)} chars consensus")

    log("\nPhase 3 complete.")


# ============================================================================
# PHASE 4: SPEC GENERATION (3 calls, no pattern cards)
# ============================================================================

def phase4_specs():
    log("\n" + "=" * 60)
    log("PHASE 4: C10+ SPEC GENERATION (observation only)")
    log("=" * 60)

    for gk, gi in GAMES.items():
        spec_file = SPECS_DIR / f"{gk}_C10_plus_spec.yaml"
        if spec_file.exists() and spec_file.stat().st_size > 100:
            log(f"  {gi['name']}: already exists, skip")
            continue

        agg_file = AGG_DIR / f"{gk}_10x_plus_consensus.txt"
        if not agg_file.exists():
            log(f"  {gi['name']}: no aggregated data, skip")
            continue
        agg_text = agg_file.read_text(encoding="utf-8")
        params = PARAM_LIST[gk]

        log(f"  {gi['name']} C10+: generating (enhanced obs only)...")
        prompt = f"""당신은 모바일 게임 밸런스 시트 전문가입니다.

다음은 "{gi['name']}"에 대해 10명의 전문가 AI 테스터가 각자 다른 미션으로 관찰한 결과를 도메인 가중치 적용하여 집계한 데이터입니다:

{agg_text}

---

위 관찰 데이터만 사용하여 아래 32개 파라미터를 추정하세요.
[HIGH] 항목은 확정적으로, [MED]는 합리적 추정, [LOW]는 추론.
관찰 불가능한 내부 구조 파라미터는 null로 표시.

파라미터 목록:
{params}

YAML 형식:
game: "{gi['name']}"
condition: "C10_plus"
parameters:
  - id: {gi['prefix']}01
    name: total_levels
    value: (추정값)
    confidence: high/medium/low
    source: "어떤 전문가의 어떤 데이터 기반인지"
  ...

반드시 32개 모두 포함."""

        result = claude_text(prompt, timeout=300)
        spec_file.write_text(result, encoding="utf-8")
        log(f"    -> {'ERROR' if result.startswith('ERROR') else f'{len(result)} chars'}")

    log("\nPhase 4 complete.")


# ============================================================================
# PHASE 5: SCORING (3 calls)
# ============================================================================

def phase5_scoring():
    log("\n" + "=" * 60)
    log("PHASE 5: C10+ SCORING")
    log("=" * 60)

    for gk, gi in GAMES.items():
        score_file = SCORING_DIR / f"{gk}_C10_plus_score.yaml"
        if score_file.exists() and score_file.stat().st_size > 100:
            log(f"  {gi['name']}: already scored, skip")
            continue

        gt_file = GT_DIR / f"{gk}_ground_truth.yaml"
        spec_file = SPECS_DIR / f"{gk}_C10_plus_spec.yaml"
        if not gt_file.exists() or not spec_file.exists():
            log(f"  {gi['name']}: missing files, skip")
            continue

        gt_text = gt_file.read_text(encoding="utf-8")
        spec_text = spec_file.read_text(encoding="utf-8")
        if spec_text.startswith("ERROR"):
            log(f"  {gi['name']}: spec error, skip")
            continue

        params = PARAM_LIST[gk]
        log(f"  {gi['name']} C10+: scoring...")

        prompt = f"""다음 두 데이터를 비교하여 각 파라미터를 채점하세요.

## Ground Truth
{gt_text}

## Generated Spec
{spec_text}

## 파라미터 목록 (32개)
{params}

## 채점 기준
- 1.0: Exact  - 0.7: Close (20% 이내)  - 0.4: Partial  - 0.1: Wrong  - 0.0: Missing

## 출력
scoring:
  game: "{gi['name']}"
  condition: "C10_plus"
  results:
    - id: {gi['prefix']}01
      name: (파라미터명)
      ground_truth: "(실제값)"
      generated: "(추정값)"
      score: 0.0
      note: "(설명)"
    ...
  summary:
    total: 32
    sum: (합계)
    average: (평균)

32개 모두 채점. sum/average 정확히 계산."""

        result = claude_text(prompt, timeout=300)
        score_file.write_text(result, encoding="utf-8")

        if result.startswith("ERROR"):
            log(f"    -> {result[:80]}")
        else:
            avg = extract_average(result)
            log(f"    -> average: {avg:.3f}")

    log("\nPhase 5 complete.")


# ============================================================================
# PHASE 6: REPORT
# ============================================================================

def phase6_report():
    log("\n" + "=" * 60)
    log("PHASE 6: REPORT")
    log("=" * 60)

    scores = {}
    for gk in GAMES:
        sf = SCORING_DIR / f"{gk}_C10_plus_score.yaml"
        if sf.exists():
            text = sf.read_text(encoding="utf-8")
            scores[gk] = extract_average(text)
        else:
            scores[gk] = 0.0

    c10p_avg = sum(scores[g] for g in GAMES) / 3
    c10_avg = BASELINES["C10"]["average"]
    c_avg = BASELINES["C"]["average"]

    report = f"""# C10+ 강화 10인 관찰 실험 보고서
생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 결과

| 게임 | C10+ | C10 (기존) | 개선 |
|------|------|-----------|------|
| Tap Shift | {scores['tapshift']*100:.1f}% | {BASELINES['C10']['tapshift']*100:.1f}% | {(scores['tapshift']-BASELINES['C10']['tapshift'])*100:+.1f}%p |
| Magic Sort | {scores['magicsort']*100:.1f}% | {BASELINES['C10']['magicsort']*100:.1f}% | {(scores['magicsort']-BASELINES['C10']['magicsort'])*100:+.1f}%p |
| Car Match | {scores['carmatch']*100:.1f}% | {BASELINES['C10']['carmatch']*100:.1f}% | {(scores['carmatch']-BASELINES['C10']['carmatch'])*100:+.1f}%p |
| **평균** | **{c10p_avg*100:.1f}%** | {c10_avg*100:.1f}% | **{(c10p_avg-c10_avg)*100:+.1f}%p** |

## 비교
| 조건 | 점수 |
|------|------|
| C (1인 자유 관찰) | {c_avg*100:.1f}% |
| C10 (10인 자유 관찰) | {c10_avg*100:.1f}% |
| **C10+ (10인 전문 관찰)** | **{c10p_avg*100:.1f}%** |
| 목표 | 88~90% |

## 실험 환경
| 항목 | 내용 |
|------|------|
| AI 모델 | Claude Sonnet 4.6 |
| 세션 전략 | 전문 미션 10종 |
| 스크린샷 | 세션당 5-8장 |
| Claude CLI 호출 | ~39회 |
| 실험일 | {datetime.now().strftime('%Y-%m-%d')} |
"""

    report_file = BASE / "결과보고서_C10_plus.md"
    report_file.write_text(report, encoding="utf-8")
    log(f"  Report: {report_file}")
    log(f"  C10+ average: {c10p_avg*100:.1f}% (target: 88-90%)")
    log(f"  C10 baseline: {c10_avg*100:.1f}%")
    log(f"  Delta: {(c10p_avg-c10_avg)*100:+.1f}%p")


# ============================================================================
# MAIN
# ============================================================================

def main():
    start_time = time.time()
    log("=" * 60)
    log("C10+ Enhanced 10-Person Observation Experiment")
    log(f"Base: {BASE}")
    log("=" * 60)

    ensure_dirs()

    r = adb_run("devices")
    if DEVICE.encode() not in r.stdout:
        log(f"ERROR: Device {DEVICE} not found. Start BlueStacks first.")
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
