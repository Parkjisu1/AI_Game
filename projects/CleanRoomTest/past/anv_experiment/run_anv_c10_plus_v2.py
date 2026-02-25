#!/usr/bin/env python3
"""
C10+ v2 Enhanced Observation Experiment — Ash N Veil: Fast Idle Action
======================================================================
v2 개선사항:
  1. Numeric 미션 분할 (Early/Late) → 회귀분석 데이터 포인트 확대
  2. Visual 미션에 다해상도 비교 추가 → 기준 해상도 역산
  3. Idle RPG 특화 미션 재설계 (장비/가챠/스킬 전담)

Target: v1=89.5% → v2=~91% (패턴카드 없이)
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

BASE = Path(r"E:\AI\projects\CleanRoomTest\anv_experiment")
GT_DIR = BASE / "ground_truth"

SESSIONS_DIR = BASE / "sessions_plus"
OBS_DIR = BASE / "observations_plus"
AGG_DIR = BASE / "aggregated"
SPECS_DIR = BASE / "specs"
SCORING_DIR = BASE / "scoring"

GAME = {
    "key": "anv",
    "name": "Ash N Veil: Fast Idle Action",
    "package": "studio.gameberry.anv",
    "prefix": "ANV",
    "genre": "Idle RPG / Action",
}

# BlueStacks 에뮬레이터 좌표 (800x1280 기준, 실측 필요)
# TODO: 실제 게임 설치 후 좌표 재측정 필요
COORDS = {
    "center": (400, 640),
    "play": (400, 1000),
    "back": (60, 60),
    "settings": (720, 60),
    "popup_close": (400, 900),     # 팝업 닫기/확인
    "popup_x": (650, 200),         # 팝업 X 버튼
    # 하단 메뉴바
    "menu_char": (80, 1230),       # 캐릭터
    "menu_skill": (200, 1230),     # 스킬
    "menu_field": (400, 1230),     # 필드 (중앙)
    "menu_summon": (560, 1230),    # 소환
    "menu_shop": (680, 1230),      # 상점
    # 전투 화면
    "joystick_area": (150, 900),   # 가상 조이스틱
    "skill_1": (550, 950),         # 스킬 슬롯 1
    "skill_2": (630, 870),         # 스킬 슬롯 2
    "skill_3": (710, 950),         # 스킬 슬롯 3
    # 장비 화면
    "gear_slot_1": (200, 400),     # 무기
    "gear_slot_2": (200, 500),     # 방어구
    "gear_enhance": (400, 1100),   # 강화 버튼
    # 소환 화면
    "summon_1x": (250, 900),       # 1회 소환
    "summon_10x": (550, 900),      # 10연차 소환
}

# ============================================================================
# v2 미션 재설계: Idle RPG 특화 10 미션
# ============================================================================

SESSION_MISSIONS = {
    1:  {
        "name": "Full Playthrough A — 챕터 진행",
        "domain": "gameplay",
        "desc": "챕터 1부터 순차 진행, 스테이지 구조/보스/난이도 곡선 관찰",
    },
    2:  {
        "name": "Full Playthrough B — UI/메뉴 탐색",
        "domain": "gameplay",
        "desc": "독립 플레이스루, 마을/상점/설정 등 전체 메뉴 구조 매핑",
    },
    3:  {
        "name": "v2: Numeric Early — 초반 수치 수집",
        "domain": "numeric_early",
        "desc": "레벨 1~15: HP/공격력/경험치 테이블, 장비 기초 강화 비용 수집",
    },
    4:  {
        "name": "v2: Numeric Late — 후반 스케일링",
        "domain": "numeric_late",
        "desc": "레벨 30+: 성장 공식 역산, 후반 보스 HP, 스케일링 계수 검증",
    },
    5:  {
        "name": "v2: Visual + 다해상도 — 정밀 측정",
        "domain": "visual",
        "desc": "픽셀 측정 + 다해상도(720/1080/1440) UI 스케일링 비교",
    },
    6:  {
        "name": "Equipment & Enhancement — 장비 시스템",
        "domain": "equipment",
        "desc": "장비 종류/등급/강화 비용 곡선/옵션 구조 전수 조사",
    },
    7:  {
        "name": "Economy & Idle — 경제/방치 보상",
        "domain": "economy",
        "desc": "재화 흐름, 방치 보상/시간, 일일 출석, 상점 가격 전체 추적",
    },
    8:  {
        "name": "Gacha & Pets — 소환/펫 시스템",
        "domain": "gacha",
        "desc": "아바타/펫 소환 비용, 등급별 확률, 효과, 중복 처리",
    },
    9:  {
        "name": "Skills & Combat — 스킬/전투 알고리즘",
        "domain": "combat",
        "desc": "스킬 쿨다운, 데미지 공식, 공격 속도, 회피 판정, 상태이상",
    },
    10: {
        "name": "Cross-Validation — 교차 검증",
        "domain": "cross_validation",
        "desc": "약점 항목 재확인, 수치 불일치 해소, 최종 합의",
    },
}

# 미션별 비전 프롬프트
VISION_PROMPTS = {
    1: """Ash N Veil: Fast Idle Action — 전문가 1: 챕터 진행 분석

당신은 Idle RPG 구조 분석 전문가입니다.

분석 항목:
1. 총 챕터 수, 챕터당 스테이지 수
2. 스테이지별 몬스터 수/종류 변화
3. 보스 등장 패턴 (매 챕터 마지막? 특정 스테이지?)
4. 오토 전투 해금 시점
5. 난이도 전환점 (체감 벽 구간)
6. 새 기능 해금 레벨 목록
7. 챕터 클리어 보상 구조

규칙: 모든 숫자를 정확히 기록. 챕터별 데이터를 테이블로 정리.""",

    2: """Ash N Veil — 전문가 2: UI/메뉴 구조 매핑

당신은 UI/UX 분석 전문가입니다.

분석 항목:
1. 메인 화면 레이아웃 (상단바, 하단 메뉴, 전투 영역)
2. 하단 메뉴 탭 목록과 각 탭의 하위 메뉴
3. 마을/거점 구조
4. 설정 화면 옵션 전체 목록
5. 알림/미션/퀘스트 UI
6. 팝업 종류 (레벨업, 장비 획득, 업적 등)
7. 화면 전환 방식 (슬라이드, 페이드, 즉시)

규칙: 전문가 1과 독립 관찰. 모든 화면을 빠짐없이 기록.""",

    3: """Ash N Veil — 전문가 3: 초반 수치 수집 (v2 강화)

당신은 게임 밸런스 수치 분석 전문가입니다. 초반 구간(레벨 1~15)에 집중합니다.

필수 수집 데이터:
1. 레벨별 테이블: 레벨, 필요 EXP, HP, 공격력, 방어력
2. 몬스터 HP: 챕터1 스테이지별 일반몹/보스 HP
3. 장비 기초 가격: 각 종류별 Common 가격
4. 장비 강화 비용: 1강→2강→3강→... 비용 곡선 (최소 5단계)
5. 스킬 강화 비용: 레벨별 비용 (최소 5단계)
6. EXP 획득량: 몬스터 처치당 EXP (일반몹/보스)
7. 골드 획득량: 몬스터 처치당 골드
8. 초기 재화: 튜토리얼 직후 골드/젬 보유량

출력: 반드시 정확한 숫자를 테이블로 정리. 추정값은 (추정) 표시.
v2 규칙: 각 데이터 포인트를 최소 3회 확인하여 신뢰도 확보.""",

    4: """Ash N Veil — 전문가 4: 후반 스케일링 검증 (v2 신규)

당신은 게임 성장 곡선 분석 전문가입니다. 후반 구간(레벨 30+)에 집중합니다.

필수 수집 데이터:
1. 레벨별 테이블 (30~50): 레벨, 필요 EXP, HP, 공격력
2. 초반 데이터와 비교: 성장률이 선형/지수/로그인지 판별
3. 후반 보스 HP: 챕터 후반 보스의 HP (초반 보스 대비 배율)
4. 장비 강화 후반 비용: 10강→15강→20강 비용 (초반 대비 배율)
5. 후반 해금 콘텐츠: Ash, Rift, Rune, Soul Link, Void 등
6. 일일 던전/보스 레이드 조건 및 보상

v2 목적: 초반(전문가 3)과 후반(전문가 4) 데이터를 합쳐 성장 공식 회귀분석.
최소 10개 이상 데이터 포인트 확보 목표.""",

    5: """Ash N Veil — 전문가 5: 시각 측정 + 다해상도 비교 (v2 강화)

당신은 UI/UX 측정 전문가입니다.

필수 측정:
1. 전투 화면: 캐릭터 크기, HP바 크기/위치, 스킬 아이콘 크기
2. 하단 메뉴바: 높이, 아이콘 간격 (px 단위)
3. 상단 HUD: 재화 표시 영역, 레벨 표시, 미니맵
4. 팝업: 크기, 여백, 버튼 크기
5. 폰트 크기: 데미지 숫자, UI 텍스트
6. 색상: HP바(빨강), EXP바(파랑/초록), 등급 색상 코드

v2 추가 (다해상도):
7. 현재 해상도에서 특정 UI 요소의 픽셀 크기 정밀 기록
8. UI 스케일링 방식 추론 (Scale With Screen Size? Fixed?)
9. 가능하면 기준 해상도 추정

출력: 모든 측정값을 px 단위 숫자로 기록.""",

    6: """Ash N Veil — 전문가 6: 장비 시스템 전수 조사

당신은 RPG 장비 시스템 분석 전문가입니다.

필수 확인:
1. 장비 슬롯: 종류 목록 (무기/방어구/투구/부츠/망토/화살통...)
2. 등급 체계: Common/Uncommon/Rare/Epic 외 추가 등급?
3. 각 등급 색상 코드
4. 강화 시스템: 최대 강화 단계, 실패 확률 유무
5. 강화 비용 곡선: 단계별 코인 비용 (최소 10단계)
6. 장비 옵션/부옵션 구조
7. 세트 효과 존재 여부
8. 장비 획득 방식: 필드 드롭, 상점, 던전, 제작
9. 장비 분해/판매 시스템

규칙: 각 슬롯의 실제 장비명과 수치를 기록.""",

    7: """Ash N Veil — 전문가 7: 경제 + 방치 보상 전체 추적

당신은 게임 경제 분석 전문가입니다.

필수 추적:
1. 재화 종류: 골드, 젬, 소환권 외 추가 재화?
2. 초기 재화: 튜토리얼 직후 각 재화 보유량
3. 방치(Idle) 보상: 시간당 골드/EXP (정확한 수치)
4. 방치 최대 축적 시간: 몇 시간치까지 쌓이는지
5. 일일 출석 보상: 7일 주기 각 날의 보상 내용
6. 퀘스트/미션 보상: 일일/주간/업적 보상
7. 상점 가격표: 젬→골드 환율, 주요 아이템 가격
8. IAP 상품: 모든 패키지와 실제 가격 (USD/KRW)
9. 광고 보상: 광고 시청 시 보상량, 일일 광고 시청 한도

출력: 모든 재화값을 정확한 숫자로 기록. 보상 테이블 작성.""",

    8: """Ash N Veil — 전문가 8: 소환/가챠 + 펫 시스템

당신은 가챠 분석 전문가입니다.

필수 확인:
1. 아바타 소환 비용: 1회 소환 (젬), 10연차 소환 (젬)
2. 아바타 등급: Common/Rare/Epic/Legendary + 확률표
3. 아바타 효과: 등급별 스탯 보너스 (방어력, 공속, HP 등)
4. 아바타 중복 시 처리: 합성? 조각 전환?
5. 펫 소환 비용: 1회/10연차
6. 펫 등급 및 확률
7. 펫 효과: 전투 지원? 스탯 보너스? 아이템 수집?
8. 소환권 획득 방법: 미션, 출석, 이벤트 등
9. 천장(Pity) 시스템 존재 여부

규칙: 확률은 게임 내 표시값 그대로 기록. 미표시면 50회 이상 소환 데이터 수집 후 추정.""",

    9: """Ash N Veil — 전문가 9: 스킬 + 전투 알고리즘

당신은 전투 시스템 분석 전문가입니다.

필수 분석:
1. 기본 공격: 자동 공격 속도 (초당 타수), 공격 방식 (근거리/원거리)
2. 스킬 슬롯 수: 최대 장착 수
3. 스킬별 쿨다운: 각 스킬의 쿨타임 (초 단위)
4. 스킬 데미지 배율: 기본 공격 대비 배율
5. 데미지 공식 추론: (공격력 - 방어력) × 배율? 다른 공식?
6. 크리티컬: 크리율, 크리 배율
7. 회피 시스템: 존재 여부, 회피율
8. 상태이상: 종류 (스턴, 슬로우, 독 등)
9. 보스 패턴: 보스 특수 공격 패턴

규칙: 관찰된 행동에서 논리적으로 추론. 확실한 것과 추론을 구분.""",

    10: """Ash N Veil — 전문가 10: 교차 검증 (v2)

당신은 데이터 검증 전문가입니다.

집중 확인 항목:
1. 전문가 3(초반)과 4(후반)의 수치 연결 검증: 성장 곡선 연속성
2. 강화 비용 곡선의 정확한 공식 확정
3. 아바타/펫 소환 확률의 교차 검증
4. 방치 보상의 정확한 시간당 수치
5. 장비 등급별 스탯 차이 검증

v2 규칙: 불일치 항목마다 최소 3회 추가 관찰로 해소.""",
}

# ============================================================================
# 32 파라미터 정의 (Idle RPG 특화)
# ============================================================================

PARAM_LIST = """ANV01: chapter_count (progression) - 총 챕터 수
ANV02: stages_per_chapter (progression) - 챕터당 스테이지 수
ANV03: boss_stage_pattern (progression) - 보스 등장 패턴 (매 챕터 끝? N스테이지마다?)
ANV04: gear_slot_types (equipment) - 장비 슬롯 종류 (무기/방어구/투구/부츠/망토/화살통)
ANV05: gear_rarity_grades (equipment) - 장비 등급 수 및 이름
ANV06: gear_enhance_max (equipment) - 장비 최대 강화 단계
ANV07: gear_enhance_cost_formula (equipment) - 강화 비용 공식 (단계별)
ANV08: skill_max_slots (combat) - 스킬 최대 장착 수
ANV09: skill_rarity_grades (combat) - 스킬 등급 수 및 이름
ANV10: skill_cooldown_range (combat) - 스킬 쿨다운 범위 (최소~최대 초)
ANV11: auto_attack_speed (combat) - 자동 공격 속도 (초당 타수)
ANV12: damage_formula (combat) - 데미지 계산 공식
ANV13: critical_rate_base (combat) - 기본 크리티컬 확률
ANV14: critical_multiplier (combat) - 크리티컬 데미지 배율
ANV15: avatar_rarity_grades (gacha) - 아바타 등급 (Common/Rare/Epic/Legendary)
ANV16: avatar_summon_1x_cost (gacha) - 아바타 1회 소환 비용 (젬)
ANV17: avatar_summon_10x_cost (gacha) - 아바타 10연차 소환 비용 (젬)
ANV18: pet_types_count (gacha) - 펫 종류 수
ANV19: starting_gold (economy) - 초기 골드 (튜토리얼 후)
ANV20: starting_gems (economy) - 초기 젬
ANV21: idle_gold_per_hour (economy) - 방치 시간당 골드 수익
ANV22: idle_max_accumulation (economy) - 방치 보상 최대 축적 시간
ANV23: daily_attendance_days (economy) - 일일 출석 주기 (일)
ANV24: exp_formula_type (progression) - EXP 성장 곡선 타입 (선형/지수/로그)
ANV25: hp_growth_formula (progression) - HP 성장 공식 (레벨별)
ANV26: attack_growth_formula (progression) - 공격력 성장 공식 (레벨별)
ANV27: feature_unlock_levels (progression) - 기능 해금 레벨 목록
ANV28: movement_speed (visual) - 캐릭터 이동 속도
ANV29: ui_reference_resolution (visual) - UI 기준 해상도
ANV30: state_count (architecture) - 게임 상태 수 (메인/전투/마을/인벤/소환/설정 등)
ANV31: save_system (architecture) - 저장 방식 (서버/로컬/하이브리드)
ANV32: interstitial_ad_frequency (monetization) - 전면광고 빈도"""

# ============================================================================
# BASELINES
# ============================================================================

BASELINES = {
    "C10+_v1_avg": 0.895,  # 기존 퍼즐 게임 기준
}

# ============================================================================
# HELPERS (기존 run_c10_plus.py와 동일 구조)
# ============================================================================

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def ensure_dirs():
    for d in [SESSIONS_DIR, OBS_DIR, AGG_DIR, SPECS_DIR, SCORING_DIR, GT_DIR]:
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


def force_stop():
    adb_run("shell", "am", "force-stop", GAME["package"])
    time.sleep(1)


def launch_game(wait=12):
    adb_run("shell", "monkey", "-p", GAME["package"], "-c",
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


# ============================================================================
# PHASE 1: CAPTURE (10 specialized sessions)
# ============================================================================

def dismiss_popups():
    """초기 팝업(GDPR, 공지, 출석 등) 닫기 — v1 실패 교훈 반영"""
    for _ in range(5):
        tap(*COORDS["popup_close"], wait=1)
        tap(*COORDS["popup_x"], wait=0.5)
    press_back(wait=1)


def capture_session(session_id):
    c = COORDS
    sdir = SESSIONS_DIR / f"session_{session_id:02d}"
    sdir.mkdir(parents=True, exist_ok=True)
    shots = []

    def shot(name):
        p = sdir / f"{name}.png"
        if take_screenshot(p):
            shots.append(p)

    # ----- 공통: 팝업 처리 -----
    dismiss_popups()

    # === Session 1: Full Playthrough A (10 shots) ===
    if session_id == 1:
        shot("01_main_field")
        # 챕터 진행
        for stage in range(1, 6):
            time.sleep(15)  # 자동 전투 대기
            shot(f"02_stage{stage}_battle")
        # 보스전
        time.sleep(20)
        shot("07_boss_battle")
        shot("08_boss_result")
        # 챕터 2 진입
        time.sleep(5)
        shot("09_chapter2_start")
        time.sleep(15)
        shot("10_chapter2_progress")

    # === Session 2: UI/메뉴 탐색 (10 shots) ===
    elif session_id == 2:
        shot("01_main_screen")
        tap(*c["menu_char"], wait=2)
        shot("02_character_screen")
        tap(*c["menu_skill"], wait=2)
        shot("03_skill_screen")
        tap(*c["menu_summon"], wait=2)
        shot("04_summon_screen")
        tap(*c["menu_shop"], wait=2)
        shot("05_shop_screen")
        tap(*c["settings"], wait=2)
        shot("06_settings")
        press_back(wait=1)
        tap(*c["menu_field"], wait=2)
        shot("07_field_return")
        # 퀘스트/미션
        tap(720, 300, wait=2)  # 우측 퀘스트 영역
        shot("08_quest_screen")
        press_back(wait=1)
        # 마을/거점
        tap(400, 200, wait=2)
        shot("09_village")
        shot("10_daily_attendance")

    # === Session 3: Numeric Early (8 shots) ===
    elif session_id == 3:
        shot("01_initial_stats")
        # 레벨업 관찰
        time.sleep(10)
        shot("02_level_2_stats")
        time.sleep(10)
        shot("03_level_3_stats")
        # 몬스터 HP 확인
        time.sleep(5)
        shot("04_monster_hp")
        # 장비 강화 비용
        tap(*c["menu_char"], wait=2)
        tap(*c["gear_slot_1"], wait=1)
        shot("05_gear_detail")
        tap(*c["gear_enhance"], wait=1)
        shot("06_enhance_cost_1")
        tap(*c["gear_enhance"], wait=1)
        shot("07_enhance_cost_2")
        tap(*c["gear_enhance"], wait=1)
        shot("08_enhance_cost_3")

    # === Session 4: Numeric Late (8 shots) ===
    elif session_id == 4:
        # 계정이 충분히 진행된 상태에서 캡처
        shot("01_late_game_stats")
        tap(*c["menu_char"], wait=2)
        shot("02_high_level_gear")
        tap(*c["gear_enhance"], wait=1)
        shot("03_high_enhance_cost")
        press_back(wait=1)
        tap(*c["menu_field"], wait=2)
        time.sleep(15)
        shot("04_late_monster_hp")
        shot("05_late_boss_battle")
        time.sleep(20)
        shot("06_late_boss_result")
        # 상위 콘텐츠
        shot("07_rift_or_void")
        shot("08_endgame_content")

    # === Session 5: Visual + Multi-Resolution (8 shots) ===
    elif session_id == 5:
        shot("01_full_battle_ui")
        shot("02_character_closeup")
        tap(*c["menu_char"], wait=2)
        shot("03_inventory_ui")
        tap(*c["menu_skill"], wait=2)
        shot("04_skill_ui")
        press_back(wait=1)
        tap(*c["menu_field"], wait=2)
        # HP바 상세
        shot("05_hp_bar_detail")
        # 데미지 숫자
        time.sleep(5)
        shot("06_damage_numbers")
        # 하단 메뉴바
        shot("07_bottom_menu_detail")
        # 전체 화면 해상도
        shot("08_full_screen_reference")

    # === Session 6: Equipment System (8 shots) ===
    elif session_id == 6:
        tap(*c["menu_char"], wait=2)
        shot("01_all_gear_slots")
        # 각 슬롯
        for i, slot_y in enumerate([400, 500, 600, 700, 800, 900], 1):
            tap(200, slot_y, wait=1)
            shot(f"0{i+1}_gear_slot_{i}")
        # 강화 반복
        tap(*c["gear_slot_1"], wait=1)
        tap(*c["gear_enhance"], wait=1)
        shot("08_enhance_progression")

    # === Session 7: Economy & Idle (8 shots) ===
    elif session_id == 7:
        shot("01_initial_currencies")
        # 전투 후 보상
        time.sleep(15)
        shot("02_battle_rewards")
        # 방치 보상 확인
        shot("03_idle_reward_panel")
        # 상점
        tap(*c["menu_shop"], wait=2)
        shot("04_gem_shop")
        swipe(400, 800, 400, 300, dur=500, wait=1)
        shot("05_iap_packages")
        press_back(wait=1)
        # 출석
        shot("06_daily_attendance")
        # 퀘스트 보상
        tap(720, 300, wait=2)
        shot("07_quest_rewards")
        press_back(wait=1)
        shot("08_currencies_after")

    # === Session 8: Gacha & Pets (8 shots) ===
    elif session_id == 8:
        tap(*c["menu_summon"], wait=2)
        shot("01_summon_main")
        # 아바타 소환 화면
        shot("02_avatar_summon")
        # 확률 표시 확인
        tap(700, 300, wait=1)  # 확률표 버튼
        shot("03_probability_table")
        press_back(wait=1)
        # 1회 소환
        tap(*c["summon_1x"], wait=3)
        shot("04_summon_result_1x")
        # 10연차 소환 (비용 확인만)
        shot("05_10x_cost_display")
        # 펫 탭
        swipe(400, 400, 100, 400, dur=300, wait=1)
        shot("06_pet_summon")
        shot("07_pet_list")
        shot("08_pet_detail")

    # === Session 9: Skills & Combat (8 shots) ===
    elif session_id == 9:
        tap(*c["menu_skill"], wait=2)
        shot("01_skill_list")
        # 각 스킬 상세
        tap(200, 400, wait=1)
        shot("02_skill_detail_1")
        tap(200, 500, wait=1)
        shot("03_skill_detail_2")
        press_back(wait=1)
        tap(*c["menu_field"], wait=2)
        # 전투 중 스킬 사용
        tap(*c["skill_1"], wait=2)
        shot("04_skill_1_used")
        tap(*c["skill_2"], wait=2)
        shot("05_skill_2_used")
        # 쿨다운 관찰
        shot("06_cooldown_state")
        # 크리티컬 관찰
        time.sleep(5)
        shot("07_critical_hit")
        # 보스 패턴
        time.sleep(20)
        shot("08_boss_pattern")

    # === Session 10: Cross-Validation (8 shots) ===
    elif session_id == 10:
        shot("01_verify_currencies")
        tap(*c["menu_char"], wait=2)
        shot("02_verify_stats")
        tap(*c["gear_enhance"], wait=1)
        shot("03_verify_enhance_cost")
        press_back(wait=1)
        tap(*c["menu_summon"], wait=2)
        shot("04_verify_summon_cost")
        press_back(wait=1)
        tap(*c["menu_field"], wait=2)
        time.sleep(10)
        shot("05_verify_damage")
        shot("06_verify_idle_reward")
        tap(*c["menu_skill"], wait=2)
        shot("07_verify_cooldown")
        shot("08_verify_final")

    return shots


def phase1_capture():
    log("=" * 60)
    log("PHASE 1: CAPTURE (10 specialized sessions)")
    log("=" * 60)

    for sid in range(1, 11):
        mission = SESSION_MISSIONS[sid]
        sdir = SESSIONS_DIR / f"session_{sid:02d}"
        existing = list(sdir.glob("*.png")) if sdir.exists() else []
        if len(existing) >= 6:
            log(f"  Session {sid:02d}: {mission['name']} — already {len(existing)} shots, skip")
            continue

        log(f"  Session {sid:02d}: {mission['name']}")
        force_stop()
        launch_game(wait=12)
        shots = capture_session(sid)
        log(f"    -> {len(shots)} screenshots")

    force_stop()
    log("\nPhase 1 complete.")


# ============================================================================
# PHASE 2: VISION ANALYSIS (10 Claude calls)
# ============================================================================

def phase2_vision():
    log("\n" + "=" * 60)
    log("PHASE 2: VISION ANALYSIS (10 mission-specific calls)")
    log("=" * 60)

    for sid in range(1, 11):
        obs_file = OBS_DIR / f"anv_session_{sid:02d}.txt"
        if obs_file.exists() and obs_file.stat().st_size > 100:
            log(f"  Session {sid:02d}: already analyzed, skip")
            continue

        sdir = SESSIONS_DIR / f"session_{sid:02d}"
        images = sorted(sdir.glob("*.png")) if sdir.exists() else []
        if not images:
            log(f"  Session {sid:02d}: no screenshots, skip")
            obs_file.write_text("ERROR: No screenshots\n", encoding="utf-8")
            continue

        mission = SESSION_MISSIONS[sid]
        log(f"  Session {sid:02d}: {mission['name']} — {len(images)} images...")

        prompt = VISION_PROMPTS[sid]
        result = claude_vision(prompt, images, timeout=180)
        obs_file.write_text(result, encoding="utf-8")

        if result.startswith("ERROR"):
            log(f"    -> {result[:80]}")
        else:
            log(f"    -> {len(result)} chars")

    log("\nPhase 2 complete.")


# ============================================================================
# PHASE 3: ENHANCED AGGREGATION (v2: 도메인 가중 + 회귀분석 강화)
# ============================================================================

def phase3_aggregate():
    log("\n" + "=" * 60)
    log("PHASE 3: ENHANCED AGGREGATION (v2 expert-weighted)")
    log("=" * 60)

    agg_file = AGG_DIR / "anv_10x_plus_consensus.txt"
    if agg_file.exists() and agg_file.stat().st_size > 100:
        log("  Already aggregated, skip")
        return

    obs_texts = []
    for sid in range(1, 11):
        obs_file = OBS_DIR / f"anv_session_{sid:02d}.txt"
        if obs_file.exists():
            text = obs_file.read_text(encoding="utf-8")
            if not text.startswith("ERROR"):
                m = SESSION_MISSIONS[sid]
                obs_texts.append(
                    f"=== 전문가 {sid}: {m['name']} (도메인: {m['domain']}) ===\n"
                    f"미션: {m['desc']}\n\n{text}"
                )

    if not obs_texts:
        log("  No valid observations, skip")
        return

    log(f"  Aggregating {len(obs_texts)} specialist observations...")
    all_obs = "\n\n".join(obs_texts)

    prompt = f"""게임 "Ash N Veil: Fast Idle Action"에 대한 {len(obs_texts)}명의 전문가 AI 테스터 관찰을 통합하세요.

{all_obs}

---

통합 규칙 (v2 도메인 가중치 + 회귀분석 강화):

1. 도메인 전문성 우선:
   - 초반 수치 → 전문가 3, 후반 수치 → 전문가 4
   - 장비 → 전문가 6, 경제/방치 → 전문가 7
   - 가챠 → 전문가 8, 전투 → 전문가 9
   - 시각 → 전문가 5

2. v2 회귀분석 강화:
   - 전문가 3(초반)과 4(후반)의 데이터를 합쳐 성장 공식 회귀분석
   - HP/공격력/EXP의 레벨별 값에서 성장 곡선 타입(선형/지수/로그) 판별
   - 강화 비용의 단계별 값에서 비용 공식 도출

3. 교차 검증: 전문가 1-2의 독립 관찰 비교, 전문가 10 재확인

출력 구조:
1. 게임 정체성 (장르, 핵심 루프)
2. 챕터/스테이지 구조
3. 전투 시스템 (공격, 스킬, 크리티컬, 보스)
4. 장비 시스템 (슬롯, 등급, 강화, 옵션)
5. 성장 공식 (HP, 공격력, EXP — 회귀분석 결과)
6. 소환/가챠 시스템 (비용, 확률, 등급)
7. 펫 시스템
8. 경제/재화 흐름
9. 방치(Idle) 시스템
10. UI/시각 측정
11. 기능 해금/진행
12. 모네타이제이션

각 항목에 [HIGH]/[MED]/[LOW] 신뢰도 표시."""

    result = claude_text(prompt, timeout=300)
    agg_file.write_text(result, encoding="utf-8")

    if result.startswith("ERROR"):
        log(f"    -> {result[:80]}")
    else:
        log(f"    -> {len(result)} chars consensus")

    log("\nPhase 3 complete.")


# ============================================================================
# PHASE 4: SPEC GENERATION (1 call)
# ============================================================================

def phase4_specs():
    log("\n" + "=" * 60)
    log("PHASE 4: C10+ v2 SPEC GENERATION")
    log("=" * 60)

    spec_file = SPECS_DIR / "anv_C10_plus_v2_spec.yaml"
    if spec_file.exists() and spec_file.stat().st_size > 100:
        log("  Already exists, skip")
        return

    agg_file = AGG_DIR / "anv_10x_plus_consensus.txt"
    if not agg_file.exists():
        log("  No aggregated data, skip")
        return
    agg_text = agg_file.read_text(encoding="utf-8")

    log("  Generating spec (enhanced obs + regression)...")
    prompt = f"""당신은 모바일 Idle RPG 게임 밸런스 시트 전문가입니다.

다음은 "Ash N Veil: Fast Idle Action"에 대해 10명의 전문가 AI 테스터의 관찰을 통합한 데이터입니다:

{agg_text}

---

위 관찰 데이터만 사용하여 아래 32개 파라미터를 추정하세요.
[HIGH] 항목은 확정적으로, [MED]는 합리적 추정, [LOW]는 추론.
관찰 불가능한 내부 파라미터는 null로 표시.

파라미터 목록:
{PARAM_LIST}

YAML 형식:
game: "Ash N Veil: Fast Idle Action"
condition: "C10_plus_v2"
parameters:
  - id: ANV01
    name: chapter_count
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
# PHASE 5: SCORING (GT가 있는 경우에만)
# ============================================================================

def phase5_scoring():
    log("\n" + "=" * 60)
    log("PHASE 5: SCORING (requires ground truth)")
    log("=" * 60)

    gt_file = GT_DIR / "anv_ground_truth.yaml"
    spec_file = SPECS_DIR / "anv_C10_plus_v2_spec.yaml"

    if not gt_file.exists():
        log("  Ground Truth 파일 없음 — 애쉬앤베일 팀 검토 후 생성 필요")
        log("  → 대신 Team Review 템플릿 생성")
        generate_review_template()
        return

    if not spec_file.exists():
        log("  Spec 파일 없음, skip")
        return

    gt_text = gt_file.read_text(encoding="utf-8")
    spec_text = spec_file.read_text(encoding="utf-8")

    score_file = SCORING_DIR / "anv_C10_plus_v2_score.yaml"
    if score_file.exists() and score_file.stat().st_size > 100:
        log("  Already scored, skip")
        return

    log("  Scoring...")
    prompt = f"""다음 두 데이터를 비교하여 각 파라미터를 채점하세요.

## Ground Truth
{gt_text}

## Generated Spec
{spec_text}

## 파라미터 목록 (32개)
{PARAM_LIST}

## 채점 기준
- 1.0: Exact  - 0.7: Close (20% 이내)  - 0.4: Partial  - 0.1: Wrong  - 0.0: Missing

## 출력
scoring:
  game: "Ash N Veil: Fast Idle Action"
  condition: "C10_plus_v2"
  results:
    - id: ANV01
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
# TEAM REVIEW TEMPLATE (GT 없을 때 사용)
# ============================================================================

def generate_review_template():
    """애쉬앤베일 팀이 검토할 수 있는 양식 생성"""
    spec_file = SPECS_DIR / "anv_C10_plus_v2_spec.yaml"
    if not spec_file.exists():
        log("  Spec 파일 없음, 리뷰 템플릿 생성 불가")
        return

    spec_text = spec_file.read_text(encoding="utf-8")

    params = PARAM_LIST.strip().split("\n")
    rows = []
    for p in params:
        pid = p.split(":")[0].strip()
        pname = p.split("-")[-1].strip() if "-" in p else p
        rows.append(f"| {pid} | {pname} | (AI 추정값) | | | |")

    table = "\n".join(rows)

    review = f"""# Ash N Veil: Fast Idle Action — C10+ v2 분석 결과 검토 요청

**생성일**: {datetime.now().strftime('%Y-%m-%d')}
**분석 방법**: C10+ v2 강화 관찰 방법론 (소스코드 미참조, 순수 관찰)
**AI 모델**: Claude Sonnet 4.6
**테스터 수**: 10명 전문 미션 (v2: Numeric 분할 + 다해상도 비교)

---

## 검토 방법

1. 아래 32개 파라미터에 대해 AI가 추정한 값을 확인합니다
2. **실제값** 칸에 귀사의 실제 수치를 기입해 주세요
3. **정확도** 칸에 판정을 기입해 주세요:
   - `정확` (1.0): 정확히 일치
   - `근접` (0.7): 20% 이내 오차
   - `부분` (0.4): 개념은 맞으나 수치 틀림
   - `오답` (0.1): 잘못된 값
   - `누락` (0.0): AI가 추정하지 못함 (null)
4. **비고** 칸에 추가 코멘트를 남겨 주세요

---

## AI 생성 스펙

```yaml
{spec_text}
```

---

## 검토 양식

| ID | 파라미터 | AI 추정값 | 실제값 | 정확도 | 비고 |
|----|---------|----------|--------|:------:|------|
{table}

---

## 종합

| 항목 | 값 |
|------|-----|
| 정확 (1.0) 개수 | /32 |
| 근접 (0.7) 개수 | /32 |
| 부분 (0.4) 개수 | /32 |
| 오답 (0.1) 개수 | /32 |
| 누락 (0.0) 개수 | /32 |
| **총점** | /32 |
| **평균 정확도** | % |

---

## 참고: C10+ v2 방법론

이 분석은 소스코드에 접근하지 않고, 10명의 AI 테스터가 각각 전문 영역을 담당하여
게임을 관찰한 결과를 도메인 가중치 적용 합의로 통합한 것입니다.

### v2 개선 사항 (기존 v1 대비)
- **Numeric 미션 분할**: 초반(1-15레벨)과 후반(30+레벨) 데이터를 별도 수집하여 성장 공식 회귀분석 정확도 향상
- **다해상도 비교**: UI 기준 해상도 역산을 위한 복수 해상도 측정
- **Idle RPG 특화**: 장비/가챠/방치 시스템 전담 테스터 배정

### 기존 검증 실적 (3개 퍼즐 게임 기준)
| 조건 | 정확도 |
|------|:------:|
| C10+ v1 (전문 관찰) | 89.5% |
| C10+ v2 (목표) | ~91% |
| C10+ → L1 결합 | 93.2% |

---

*검토 완료 후 이 문서를 회신해 주시면, Ground Truth로 사용하여 정확도를 산출하겠습니다.*
"""
    review_file = BASE / "ANV_Review_Template.md"
    review_file.write_text(review, encoding="utf-8")
    log(f"  Review template: {review_file}")


# ============================================================================
# PHASE 6: REPORT
# ============================================================================

def phase6_report():
    log("\n" + "=" * 60)
    log("PHASE 6: REPORT")
    log("=" * 60)

    # Score가 있으면 점수 기반 보고, 없으면 리뷰 대기 보고
    score_file = SCORING_DIR / "anv_C10_plus_v2_score.yaml"
    spec_file = SPECS_DIR / "anv_C10_plus_v2_spec.yaml"

    if score_file.exists():
        text = score_file.read_text(encoding="utf-8")
        avg = extract_average(text)
        score_status = f"**{avg*100:.1f}%**"
    else:
        score_status = "**팀 검토 대기 중**"

    report = f"""# Ash N Veil: C10+ v2 강화 관찰 실험 보고서
생성일: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 실험 개요

| 항목 | 내용 |
|------|------|
| 대상 게임 | Ash N Veil: Fast Idle Action (studio.gameberry.anv) |
| 장르 | Idle RPG / Action |
| 방법론 | C10+ v2 (전문 미션 10종 + 회귀분석 + 다해상도) |
| AI 모델 | Claude Sonnet 4.6 |
| 파라미터 수 | 32개 |
| 패턴 카드 | 미사용 (순수 관찰) |

## v2 개선 사항

| 개선 | 내용 | 예상 효과 |
|------|------|----------|
| Numeric 분할 | 초반/후반 별도 수집 → 회귀분석 | 수치 정확도 +3~5%p |
| 다해상도 비교 | UI 기준 해상도 역산 | reference_resolution 적중 |
| RPG 특화 미션 | 장비/가챠/스킬 전담 | 도메인 커버리지 확대 |

## 결과

정확도: {score_status}

## 미션 구성 (v2)

| # | 미션 | 도메인 | v2 변경점 |
|---|------|--------|----------|
| 1 | Full Playthrough A | gameplay | - |
| 2 | Full Playthrough B | gameplay | - |
| 3 | **Numeric Early** | numeric | v2: 초반 특화 분할 |
| 4 | **Numeric Late** | numeric | v2: 후반 스케일링 신규 |
| 5 | **Visual + Multi-Res** | visual | v2: 다해상도 비교 추가 |
| 6 | Equipment & Enhancement | equipment | RPG 특화 신규 |
| 7 | Economy & Idle | economy | 방치 보상 전담 |
| 8 | Gacha & Pets | gacha | RPG 특화 신규 |
| 9 | Skills & Combat | combat | RPG 특화 신규 |
| 10 | Cross-Validation | cross_val | - |

## 비용 및 시간

| 항목 | 수치 |
|------|------|
| Claude CLI 호출 | ~14회 (Vision 10 + Aggregate 1 + Spec 1 + Score 1 + Report 1) |
| 예상 소요 시간 | 분석 ~2시간 + 보고서 제작 ~2시간 = **총 ~4시간** |
| 게임 규모 추가분 | Idle RPG(중형) → +1~2시간 |
| 추가 비용 | 없음 (Claude API 기존 사용분) |

## 다음 단계

1. [ ] 스크립트 실행 (BlueStacks + 게임 설치 필요)
2. [ ] 생성된 스펙을 애쉬앤베일 팀에 전달 (Review Template)
3. [ ] 팀 검토 결과 수신 → Ground Truth 확정
4. [ ] 정확도 산출 및 최종 보고
"""
    report_file = BASE / "결과보고서_ANV_C10_plus_v2.md"
    report_file.write_text(report, encoding="utf-8")
    log(f"  Report: {report_file}")


# ============================================================================
# MAIN
# ============================================================================

def main():
    start_time = time.time()
    log("=" * 60)
    log("C10+ v2 — Ash N Veil: Fast Idle Action")
    log(f"Base: {BASE}")
    log("=" * 60)

    ensure_dirs()

    # ADB 연결 확인
    r = adb_run("devices")
    if DEVICE.encode() not in r.stdout:
        log(f"WARNING: Device {DEVICE} not found. Capture phase will be skipped.")
        log("스크린샷이 이미 있으면 Phase 2부터 진행합니다.")

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
