# AI Game Tester v2 — Architecture & Guide

## 목차
1. [시스템 개요](#1-시스템-개요)
2. [아키텍처](#2-아키텍처)
3. [파일 구조](#3-파일-구조)
4. [핵심 5-Layer 시스템](#4-핵심-5-layer-시스템)
5. [전략 엔진 (Lookahead)](#5-전략-엔진-lookahead)
6. [AI Swarm 자동 개선](#6-ai-swarm-자동-개선)
7. [Vision 훈련 파이프라인](#7-vision-훈련-파이프라인)
8. [시연 녹화 시스템](#8-시연-녹화-시스템)
9. [다장르 확장 시스템](#9-다장르-확장-시스템)
10. [사용법](#10-사용법)
11. [진행 로드맵](#11-진행-로드맵)

---

## 1. 시스템 개요

**목적**: AI가 실제 플레이어처럼 모바일 게임을 플레이하여 게임 디자인, 플로우, BM 데이터를 추출하는 시스템.

**핵심 원칙**:
- AI 자유도 = **최소** (이미지 인식만 AI 의존)
- 나머지 = **전부 규칙 기반 코드**
- TO DO / TO DON'T로 경계 고정 → AI가 예측 불가능한 행동을 하지 못하도록 차단

**현재 대상 게임**: CarMatch (puzzle_match 장르)

**기술 스택**:
- Python 3.13
- BlueStacks 에뮬레이터 + ADB
- Claude Vision API (Haiku) — 화면 인식
- Claude Code CLI — Swarm 에이전트 실행

---

## 2. 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                    AI Game Tester v2                         │
│                                                             │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌──────────┐   │
│  │ Layer 1  │──▶│ Layer 2  │──▶│ Layer 3  │──▶│ Layer 4  │   │
│  │Perception│   │ Memory   │   │Decision  │   │Execution │   │
│  │  (눈)    │   │  (기억)  │   │  (판단)  │   │  (손)    │   │
│  └─────────┘   └─────────┘   └─────────┘   └──────────┘   │
│       ▲                                          │          │
│       │              ┌─────────┐                 │          │
│       └──────────────│ Layer 5  │◀────────────────┘          │
│                      │Verify   │                            │
│                      │  (확인)  │                            │
│                      └─────────┘                            │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 지원 시스템                                           │   │
│  │  Playbook ─ 게임별 규칙 (화면 핸들러, 금지 영역)      │   │
│  │  Lookahead ─ 1~2수 전략 시뮬레이션                    │   │
│  │  Swarm ─ AI 군집 자동 개선 (4 에이전트)                │   │
│  │  Vision Trainer ─ 인식 정확도 측정/개선                │   │
│  │  Demo Recorder ─ 사람 플레이 녹화 → 규칙 추출          │   │
│  │  Genres/Personas ─ 다장르 확장 + 플레이어 성향         │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

**데이터 흐름 (1턴 = 약 15초)**:
```
스크린샷 캡처 (ADB) ──▶ Vision AI 인식 ──▶ BoardState JSON
                                                │
    ADB 탭 실행 ◀── Action 리스트 ◀── 규칙 판단 ◀─┘
         │
         ▼
    스크린샷 재캡처 ──▶ 결과 비교 (홀더 변화) ──▶ Memory 업데이트
```

---

## 3. 파일 구조

```
virtual_player/tester/
├── __init__.py              # 패키지 정의, 버전
├── __main__.py              # python -m virtual_player.tester 진입점
├── runner.py                # ★ 메인 루프 (5-Layer 통합 실행)
├── perception.py            # Layer 1: 화면 인식 (Vision API)
├── memory.py                # Layer 2: 단기 기억 (고정 크기)
├── decision.py              # Layer 3: 규칙 기반 판단 (P0~P5)
├── decision_v2.py           # Layer 3 v2: 규칙 + Lookahead 하이브리드
├── executor.py              # Layer 4+5: 실행 + 확인
├── playbook.py              # 게임별 규칙 정의 (TO DO / TO DON'T)
├── lookahead.py             # 전략 시뮬레이터 (1~2수 탐색)
├── vision_trainer.py        # Vision 정확도 측정/개선 도구
├── demo_recorder.py         # 사람 플레이 녹화기
├── demo_analyzer.py         # 녹화 데이터 → Playbook 규칙 추출
├── ARCHITECTURE.md          # ★ 이 문서
│
├── genres/                  # 장르별 프로필
│   ├── __init__.py
│   ├── base.py              # GenreProfile, ActionCategory
│   ├── loader.py            # load_genre(), list_genres()
│   ├── puzzle_match.py      # 퍼즐 매치 장르
│   └── idle_rpg.py          # 아이들 RPG 장르
│
├── personas/                # 플레이어 성향 프로필
│   ├── __init__.py
│   ├── base.py              # PlayerProfile
│   └── presets.py           # 프리셋 (casual_f2p, mid_dolphin, etc.)
│
└── swarm/                   # AI 군집 자동 개선
    ├── __init__.py
    ├── orchestrator.py      # ★ 4-에이전트 사이클 관리
    ├── roles.py             # 에이전트 역할 정의
    ├── experience_db.py     # 영구 경험 DB (Voyager 개념)
    └── reflector.py         # 실패 반성 모듈 (Reflexion 개념)
```

---

## 4. 핵심 5-Layer 시스템

### Layer 1: Perception (눈) — `perception.py`

화면 스크린샷을 정해진 JSON 포맷의 `BoardState`로 변환.

**이 시스템에서 유일하게 AI에 의존하는 부분.**

```python
BoardState:
  screen_type: str     # "gameplay", "lobby", "win", "fail_*", "popup", ...
  holder: [7칸]        # ["red", "red", "blue", None, None, None, None]
  holder_count: int    # 사용 중인 칸 수
  active_cars: [...]   # [{color, x, y, stacked, is_mystery}, ...]
```

**동작 모드**:
| 모드 | 조건 | 속도 | 비용 |
|------|------|------|------|
| SDK 직접 호출 | `ANTHROPIC_API_KEY=sk-ant-...` | 2~5초 | API 과금 |
| CLI 폴백 | API 키 없음 | 12~16초 | Claude Code 구독 |

**허용된 화면 유형** (총 25종):
- 게임플레이: `gameplay`
- 로비: `lobby`, `lobby_keyblaze`, `lobby_streakrace`, `lobby_dailytask` 등 9종
- 게임 결과: `win`, `fail_outofspace`, `fail_continue`, `fail_result`
- 인게임: `ingame_setting`, `ingame_quit_confirm`
- 광고: `ad`, `ad_install`
- 기타: `shop`, `leaderboard`, `journey`, `setting`, `profile`, `popup`, `unknown`

**허용된 차 색상** (11종):
`red`, `blue`, `green`, `yellow`, `orange`, `purple`, `pink`, `cyan`, `white`, `brown`, `unknown`

### Layer 2: Memory (기억) — `memory.py`

고정 크기 메모리. 무한히 쌓지 않음.

| 필드 | 용도 | 제한 |
|------|------|------|
| `holder_colors` | 현재 홀더 7칸 상태 | 7칸 고정 |
| `failed_taps` | 최근 실패 탭 좌표 | 최근 5개만 |
| `consecutive_fails` | 연속 실패 횟수 | 리셋 가능 |
| `turns_since_match` | 마지막 매칭 후 경과 턴 | 카운터 |
| `undo_remaining` | 남은 Undo 횟수 | 초기 2 |
| `magnet_remaining` | 남은 Magnet 횟수 | 초기 1 |

**결과 판정**: 이전/현재 `BoardState` 비교
- `match_3`: 홀더 줄었음 (매칭 발생)
- `car_moved`: 홀더 늘었음 (차 이동)
- `no_change`: 변화 없음 (실패)
- `screen_changed`: 화면 전환

### Layer 3: Decision (판단) — `decision.py`

**고정 분기 트리. AI 자율판단 금지.**

```
우선순위:
  P-CRITICAL: 홀더 6칸+ → 즉시 Undo
  P1: 홀더에 같은 색 2대 → 보드에서 3번째 찾아 탭 (매칭 완성)
  P2: 홀더 5칸+ → Undo 또는 Magnet
  P3: 앞줄 활성 차 중 홀더에 같은 색 있는 차 탭
  P4: 앞줄 활성 차 아무거나 탭
  P5: Mystery(?) → 홀더 3칸 이하일 때만
  FALLBACK: Undo → 강제 탭 → 대기
```

**비-gameplay 화면**: `Playbook.screen_handlers`에 등록된 고정 좌표로 탭.

### Layer 3 v2: Decision + Lookahead — `decision_v2.py`

P0~P2는 기존 규칙 유지 (긴급 상황은 규칙 우선).
**P3~P4를 Lookahead 시뮬레이션으로 교체** → "아무 차나 탭" 대신 "최적의 차를 탭".

### Layer 4+5: Execution + Verification — `executor.py`

- Layer 3이 결정한 Action만 실행 (자체 판단 없음)
- 탭 후 스크린샷 재촬영 → 결과 비교
- 화면 전환 또는 매칭 발생 시 즉시 중단 (남은 Action 폐기)

### Playbook — `playbook.py`

게임별 TO DO / TO DON'T 규칙.

```python
CarMatch Playbook:
  board_region:       (30, 250, 1050, 1300)     # 차가 있는 영역
  holder_region:      (130, 1350, 950, 1450)    # 홀더 영역
  forbidden_regions:  [(0, 1730, 1080, 1920)]   # 부스터 바 (Shuffle/Rotate 금지)
  boosters:           {undo: (108,1830), magnet: (324,1830)}
  match_count:        3                          # 3개 모이면 매칭
  holder_slots:       7                          # 홀더 7칸
  screen_handlers:    {25개 화면별 고정 탭 좌표}
```

---

## 5. 전략 엔진 (Lookahead) — `lookahead.py`

기존 P3/P4는 "앞에 보이는 차를 아무거나 탭" → **클리어 0회**.
Lookahead는 "각 차를 탭하면 홀더가 어떻게 되는지 시뮬레이션" → 최적 선택.

### 시뮬레이션 원리

```
현재 홀더: [red, red, blue, _, _, _, _]
활성 차: red(300,800), green(500,900), blue(700,700)

시뮬레이션 결과:
  red 탭  → 매칭! [blue, _, _, _, _, _, _]  score=102 ★ 최고
  blue 탭 → 셋업  [red, red, blue, blue, _, _, _]  score=29
  green 탭 → 신규  [red, red, blue, green, _, _, _]  score=12
```

### 점수 가중치 (사람이 조정, Swarm이 미세 튜닝)

| 가중치 | 기본값 | 의미 |
|--------|--------|------|
| `match_completion` | +100 | 매칭을 완성시키는 탭 |
| `match_2_setup` | +30 | 홀더에 같은 색 2개가 되는 탭 |
| `new_color_safe` | +10 | 새 색상이지만 홀더 여유 있음 |
| `new_color_danger` | -50 | 새 색상이고 홀더 위험 |
| `holder_overflow` | -200 | 홀더가 꽉 차는 탭 |
| `mystery_safe` | +5 | Mystery 차 (홀더 여유) |
| `mystery_danger` | -100 | Mystery 차 (홀더 위험) |
| `front_row_bonus` | +5 | 앞줄 차 보너스 |
| `stacked_penalty` | -3 | 스택 높은 차 페널티 |

### DeepLookahead (2수 탐색)

1수 시뮬레이션 → 상위 5개 후보 선택 → 각 후보에 대해 2수째 최선 시뮬레이션 → 합산 점수로 최종 판단.

```
depth2_discount = 0.5  (2수째 점수에 50% 가중)
```

---

## 6. AI Swarm 자동 개선 — `swarm/`

사람이 자는 동안(12시간+) AI 군집이 자동으로 플레이 → 분석 → 개선 → 검증 사이클을 반복.

### 4-에이전트 사이클

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Player  │────▶│ Analyst  │────▶│ Improver │────▶│Validator │
│  (60분)  │     │  (5분)   │     │  (5분)   │     │  (10분)  │
│ 게임 실행 │     │ 로그 분석 │     │ 코드 개선 │     │ 변경 검증 │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
      ▲                                                   │
      └───────────────────────────────────────────────────┘
```

| 에이전트 | 역할 | 입력 | 출력 |
|----------|------|------|------|
| Player | 게임 플레이 | playbook.py | session_report.json |
| Analyst | 실패 패턴 식별 | session_report + log | analysis_report.json |
| Improver | 코드/설정 수정 (staging) | analysis_report | change_manifest.json |
| Validator | 수정 검증 + 승인/거절 | change_manifest | validation_result.json |

### 안전 규칙 (Improver)
- 화면 핸들러는 추가만 가능 (삭제 금지)
- 금지 영역은 더 엄격하게만 변경 가능 (완화 금지)
- 임계값은 ±1 단계만 조정 가능
- 확신 없으면 변경하지 않음

### 영구 저장소

**Experience DB** (`experience_db.py`) — Voyager(2023) Skill Library 개념:
```json
{
  "screen_actions": {
    "lobby": {"(540,1500)": {"success": 15, "fail": 0, "result": "gameplay"}}
  }
}
```
- 화면+좌표 → 성공/실패 횟수 → confidence 계산
- 세션 간 영구 유지

**Reflector** (`reflector.py`) — Reflexion(2023) 개념:
```json
{
  "situation": "popup 화면에서 X 좌표 (970,180) 탭 시도",
  "outcome": "10회 연속 실패",
  "analysis": "이 팝업의 X 버튼은 (885,340)에 있음",
  "lesson": "lobby_punchout X 좌표를 (885,340)으로 수정",
  "applied": false
}
```
- 실패를 자연어로 반성 → 다음 사이클에 교훈 적용

---

## 7. Vision 훈련 파이프라인 — `vision_trainer.py`

현재 Vision 정확도를 체계적으로 측정하고 개선하는 도구.

### 3단계 프로세스

```
Phase A: Reference DB 구축 (사람)
  스크린샷 50~100장에 정답 라벨 → JSON
  예: {"frame_042.png": {"screen_type": "gameplay", "holder": ["red","red","blue",null,...], ...}}

Phase B: 정확도 측정 (자동)
  현재 프롬프트로 Reference DB 전체를 인식
  → 정답과 비교 → screen 정확도, holder 정확도, car 정확도 산출

Phase C: 프롬프트 튜닝 (사람+Swarm)
  오류 패턴 분석 → 프롬프트에 힌트 추가 → Phase B 재실행 → 정확도 변화 확인
```

### 구성 요소

| 클래스 | 역할 |
|--------|------|
| `ReferenceDB` | 정답 라벨 저장/관리 (사람이 채움) |
| `VisionEvaluator` | Perception 출력 vs 정답 비교 → 정확도 통계 |
| `PromptTuner` | 프롬프트 A/B 테스트 + 개선 힌트 자동 생성 |

---

## 8. 시연 녹화 시스템 — `demo_recorder.py`, `demo_analyzer.py`

사람이 게임을 플레이하면 자동으로 행동을 기록하여 Playbook 규칙을 추출.

### 녹화 과정

```
사람이 BlueStacks에서 게임 플레이
          │
    ADB getevent로 터치 이벤트 캡처
          │
    터치마다 pre/post 스크린샷 자동 저장
          │
    JSONL 로그 생성:
      {"frame": 1, "action": {"type": "tap", "x": 540, "y": 1500},
       "pre_screenshot": "frames/pre_0001.png",
       "post_screenshot": "frames/post_0001.png", "interval_sec": 2.3}
```

### 분석 과정

```
1. 라벨링: 각 스크린샷의 screen_type 자동 판별 (Vision API)
2. 클러스터링: 같은 화면에서 반복되는 탭 좌표 → screen_handler 후보
3. 전이 분석: 화면 A → 탭 → 화면 B 패턴 → screen_flow 생성
4. Playbook 초안 출력 (JSON) → 사람이 검토/수정
```

---

## 9. 다장르 확장 시스템 — `genres/`, `personas/`

### 3-Tier 분리

```
Genre (장르)          Game (게임)           Player (플레이어)
genres/               playbook.py           personas/
puzzle_match.py       carmatch_playbook     casual_f2p
idle_rpg.py           ashveil_playbook      mid_dolphin
                                            hardcore_whale
```

| Tier | 담당 | 예시 |
|------|------|------|
| Genre | 장르 공통 패턴 | "퍼즐 게임은 lobby→gameplay→win/fail 흐름" |
| Game (Playbook) | 게임 고유 규칙 | "CarMatch는 홀더 7칸, 3매칭" |
| Player (Persona) | 플레이어 성향 | "캐주얼은 홀더 4칸에서 불안" |

### 새 게임 추가 순서

1. 장르 확인 → `genres/`에 해당 장르가 있는지 체크 (없으면 새로 생성)
2. `playbook.py`에 `create_{gameid}_playbook()` 함수 추가
3. 시연 녹화로 화면 핸들러 좌표 수집 → Playbook에 반영
4. `runner.py`에서 해당 Playbook으로 실행

### 페르소나 프리셋

| ID | 성향 | holder 불안 | 부스터 | 과금 |
|----|------|------------|--------|------|
| `casual_f2p` | 보수적 | 4칸 | 빨리 사용 | 안 함 |
| `mid_dolphin` | 보통 | 5칸 | 적당히 | 소액 |
| `hardcore_whale` | 공격적 | 6칸 | 아낌 | 대량 |
| `tester_bot` | 최대 탐색 | 5칸 | 적당히 | 안 함 |

---

## 10. 사용법

### 환경 요구사항
- Python 3.10+
- BlueStacks 5 + CarMatch 설치
- Claude Code CLI (`C:/Users/user/AppData/Roaming/npm/claude.cmd`)
- (선택) Anthropic API Key (`ANTHROPIC_API_KEY=sk-ant-...`)

### 기본 실행

```bash
cd E:\AI

# 기본 실행 (60분, 규칙 기반 판단)
python -m virtual_player.tester 60

# Lookahead 1수 시뮬레이션
python -m virtual_player.tester 60 --lookahead

# Deep Lookahead 2수 시뮬레이션
python -m virtual_player.tester 60 --deep

# 오버나이트 (9시간)
python -m virtual_player.tester 540 --lookahead
```

### 시연 녹화

```bash
# 사람이 게임 플레이하면서 녹화 (Ctrl+C로 종료)
python -m virtual_player.tester.demo_recorder --game carmatch

# 제한 시간 녹화 (10분)
python -m virtual_player.tester.demo_recorder --game carmatch --duration 10
```

### Vision 훈련

```bash
# 1. 정답 라벨링 (Python 코드로)
python -c "
from virtual_player.tester.vision_trainer import ReferenceDB
from pathlib import Path

db = ReferenceDB(Path('data/games/carmatch/reference_db.json'))
db.add_label('frame_001.png', 'lobby')
db.add_label('frame_042.png', 'gameplay',
    holder=['red','red','blue',None,None,None,None],
    active_cars=[{'color':'green','x':450,'y':800}])
db.save()
"

# 2. 정확도 측정
python -c "
from virtual_player.tester.vision_trainer import ReferenceDB, VisionEvaluator
from pathlib import Path

db = ReferenceDB(Path('data/games/carmatch/reference_db.json'))
evaluator = VisionEvaluator(db, Path('data/games/carmatch/screenshots'))
result = evaluator.evaluate()
print(f'Screen accuracy: {result[\"screen_accuracy\"]}')
print(f'Holder accuracy: {result[\"holder_accuracy\"]}')
print(f'Errors: {result[\"error_count\"]}')
"
```

### AI Swarm

```bash
# 1사이클 테스트 (5분 플레이)
python -m virtual_player.tester.swarm.orchestrator --game carmatch --cycles 1 --play-min 5

# 12시간 자동 실행
python -m virtual_player.tester.swarm.orchestrator --game carmatch --hours 12

# 무제한 (Ctrl+C로 종료)
python -m virtual_player.tester.swarm.orchestrator --game carmatch
```

---

## 11. 진행 로드맵

### Phase 1: 기반 검증 (현재)

| 항목 | 상태 | 설명 |
|------|------|------|
| 5-Layer 코어 | ✅ 완료 | perception, memory, decision, executor, runner |
| Playbook (CarMatch) | ✅ 완료 | 25개 화면 핸들러 등록 |
| Perception 듀얼 모드 | ✅ 완료 | SDK + CLI 폴백 |
| Lookahead 시뮬레이터 | ✅ 완료 | 1수 + 2수 탐색 |
| DecisionV2 통합 | ✅ 완료 | runner.py에 --lookahead, --deep 플래그 |
| Vision Trainer | ✅ 완료 | ReferenceDB, Evaluator, PromptTuner |
| Demo Recorder | ✅ 완료 | ADB getevent 기반 녹화 |
| Swarm 시스템 | ✅ 완료 | orchestrator, experience_db, reflector |
| 다장르 구조 | ✅ 완료 | genres, personas, loader |

### Phase 2: 실전 테스트 + 데이터 수집 ← 다음 단계

| 항목 | 담당 | 작업 내용 |
|------|------|-----------|
| BlueStacks 실전 테스트 | 사람 | `--lookahead` 플래그로 CarMatch 실행, 기존 대비 성능 비교 |
| ReferenceDB 라벨링 | 사람 | 스크린샷 50~100장에 정답(screen_type, holder, cars) 부여 |
| 시연 녹화 | 사람 | CarMatch 10분 플레이 녹화 → demo_analyzer로 규칙 추출 |
| Swarm 첫 사이클 | 사람+AI | `--cycles 1 --play-min 5`로 전체 파이프라인 검증 |
| API 키 적용 | 사람 | 유효한 API 키 설정 시 인식 속도 12초 → 3초 (4배 향상) |

### Phase 3: 정확도 개선

| 항목 | 담당 | 작업 내용 |
|------|------|-----------|
| Vision 정확도 80%+ | 사람+AI | ReferenceDB로 측정 → 프롬프트 튜닝 → 재측정 반복 |
| Lookahead 가중치 조정 | Swarm | 플레이 통계 기반으로 weights 미세 조정 |
| 화면 핸들러 보완 | Swarm | 새 팝업/이벤트 화면 자동 감지 → 핸들러 추가 |

### Phase 4: 다장르 확장

| 항목 | 담당 | 작업 내용 |
|------|------|-----------|
| 2번째 게임 Playbook | 사람 | 시연 녹화 → Playbook 초안 → 수동 보정 |
| idle_rpg 장르 테스트 | 사람+AI | Ash & Veil용 Playbook + Persona 적용 |
| 새 장르 프로필 추가 | 사람 | merge, runner, strategy 등 |

### Phase 5: 자율 운영

| 항목 | 담당 | 작업 내용 |
|------|------|-----------|
| Swarm 장시간 실행 | AI | 12시간+ 자동 플레이 + 개선 사이클 |
| 로컬 CV 전환 | 사람+AI | Vision API 호출 90% 감소 (화면 분류 모델 학습) |
| 클리어율 50%+ | 전체 | 전략 + 인식 + 경험 축적 종합 |

---

## 참고 논문

| 논문 | 핵심 개념 | 적용 부분 |
|------|-----------|-----------|
| Voyager (2023) | Skill Library — 성공한 행동을 영구 저장 | Experience DB |
| Reflexion (2023) | 자연어 반성 → 다음 시도에 적용 | Reflector |
| AppAgent (2024) | 모바일 앱 자동 조작 | 전체 아키텍처 참고 |
| CRADLE (2024) | 게임을 위한 범용 에이전트 프레임워크 | 5-Layer 설계 참고 |
| SPRING (2024) | 게임 매뉴얼 기반 상황별 판단 | Playbook 개념 |
| GamingAgent (2025) | 멀티모달 게임 에이전트 | Vision + Decision 통합 |
