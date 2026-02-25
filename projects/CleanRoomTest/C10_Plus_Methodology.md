# C10+ 강화 관찰 방법론 상세 기술서

> **문서 버전**: 1.0
> **작성일**: 2026-02-23
> **프로젝트**: CleanRoomTest — 클린룸 게임 스펙 역추정 실험
> **대상 독자**: 방법론을 재현하거나 확장하려는 연구자/엔지니어

---

## 목차

1. [배경 및 문제 정의](#1-배경-및-문제-정의)
2. [실험 조건 전체 맵](#2-실험-조건-전체-맵)
3. [C10+ 방법론 정의](#3-c10-방법론-정의)
4. [10가지 전문 미션 상세](#4-10가지-전문-미션-상세)
5. [자동화 파이프라인 (6단계)](#5-자동화-파이프라인-6단계)
6. [전문가 가중 합의 알고리즘](#6-전문가-가중-합의-알고리즘)
7. [측정 대상: 게임별 32 파라미터](#7-측정-대상-게임별-32-파라미터)
8. [채점 기준](#8-채점-기준)
9. [실험 결과](#9-실험-결과)
10. [실패 사례 분석 (1차 실행)](#10-실패-사례-분석-1차-실행)
11. [카테고리별 개선 분석](#11-카테고리별-개선-분석)
12. [C10+ vs D1_10 비교 및 순차 결합](#12-c10-vs-d1_10-비교-및-순차-결합)
13. [전체 조건 비교표](#13-전체-조건-비교표)
14. [관찰 불가 한계 (Observation Ceiling)](#14-관찰-불가-한계-observation-ceiling)
15. [운영 가이드](#15-운영-가이드)
16. [파일 구조 및 재현 방법](#16-파일-구조-및-재현-방법)

---

## 1. 배경 및 문제 정의

### 1-1. 클린룸 스펙 역추정이란

소스코드에 접근하지 않고, 게임의 외부 관찰만으로 내부 설계 파라미터(밸런스 상수, 알고리즘, 애니메이션 타이밍 등)를 역추정하는 방법론이다.

**활용 시나리오**:
- 경쟁사 게임의 밸런스 분석 (법적으로 안전한 관찰 기반)
- AI 기반 게임 사양서 자동 생성
- QA 테스트 자동화의 기준값 설정

### 1-2. 선행 실험 결과와 한계

| 조건 | 설명 | 정확도 | 한계 |
|------|------|:------:|------|
| A | 게임 컨셉 설명만으로 생성 | 39.5% | 수치 대부분 환각(hallucination) |
| B1 | + Level 1 패턴 카드 (정성적) | 77.7% | 수치 부정확, 아키텍처만 도움 |
| B2 | + Level 2 패턴 카드 (정량적) | 97.8% | **최고**, 그러나 패턴 카드 제작 필요 |
| C | AI 1인 자유 관찰 | 36.5% | 환각, 내부 값 관찰 불가, A보다 낮음 |
| D1 | C + L1 패턴 | 59.2% | 관찰 아티팩트 잔존 |
| D2 | C + L2 패턴 | 96.3% | B2 수준, 관찰 노이즈 미미 |
| C10 | 10인 자유 관찰 합의 | 85.0% | 패턴 카드 없이 85% 달성, 그러나 정밀 측정 부재 |

**C10의 약점 분석**:

| 카테고리 | C10 정확도 | 약점 원인 |
|----------|:---------:|----------|
| 게임플레이/메커니즘 | 95% | 거의 완벽 |
| 수치/밸런스 | 80% | 체계적 역추정 부재, 대략적 관찰만 |
| 애니메이션/타이밍 | 50% | 프레임 단위 측정 불가, "체감" 수준 |
| 시각/레이아웃 | 45% | 픽셀 단위 측정 미수행 |
| 경제 시스템 | 75% | 전체 루프 추적 미완 |
| 아키텍처 (내부 구조) | 0% | 소스코드 접근 불가, 원천 한계 |

### 1-3. C10+의 가설

> **"자유 플레이 + 다수결"을 "전문 미션 + 교차 검증"으로 전환하면, 패턴 카드 없이도 88~90% 정확도에 도달할 수 있다."**

핵심 개선 대상:
- 수치/밸런스: 전담 역추정 테스터 배정
- 애니메이션/타이밍: 프레임 카운트 기반 정량 측정
- 시각/레이아웃: 픽셀 단위 정밀 측정
- 경제 시스템: 전담 트래커의 전체 루프 추적

---

## 2. 실험 조건 전체 맵

```
                        패턴 카드 없음          L1 (정성적)         L2 (정량적)
                    ┌─────────────────┬───────────────────┬───────────────────┐
     1인 관찰       │  C    = 36.5%   │  D1   = 59.2%     │  D2   = 96.3%     │
                    ├─────────────────┼───────────────────┼───────────────────┤
     10인 자유관찰   │  C10  = 85.0%   │  D1_10= 82.5%     │  D10  = 98.5%     │
                    ├─────────────────┼───────────────────┼───────────────────┤
     10인 전문관찰   │  C10+ = 89.5%   │  C10+→L1 = 93.2%  │  (미실험)          │
                    └─────────────────┴───────────────────┴───────────────────┘
     컨셉만          │  A    = 39.5%   │  B1   = 77.7%     │  B2   = 97.8%     │
```

C10+는 이 맵에서 **"패턴 카드 없음 × 10인 전문관찰"** 셀에 위치하며, 순수 관찰만으로 달성 가능한 최고 정확도를 탐색한다.

---

## 3. C10+ 방법론 정의

### 3-1. 핵심 구조 변경

```
[기존 C10]
  10인 × 자유 플레이 → 다수결 합의 → 85.0%

[개선 C10+]
  10인 × 전문 미션 → 도메인별 전문 데이터 + 교차 검증 → 89.5%
```

### 3-2. 설계 원칙

| 원칙 | 설명 |
|------|------|
| **전문화(Specialization)** | 각 테스터에게 하나의 관찰 도메인을 전담 배정 |
| **정량화(Quantification)** | "대략적 관찰" → "프레임 카운트, 픽셀 측정, 의도적 실수" |
| **교차 검증(Cross-Validation)** | 독립 플레이스루 2회 + 전담 검증 테스터 1명 |
| **도메인 가중(Domain Weighting)** | 합의 시 해당 도메인 전문가의 데이터를 우선 |

### 3-3. 실험 대상 게임

| 게임 | 장르 | 패키지명 | 핵심 메커니즘 |
|------|------|---------|-------------|
| Tap Shift | 화살표 슬라이딩 퍼즐 | com.paxiegames.tapshift | 탭 → 화살표 이동 → 보드 탈출 |
| Magic Sort | 물약 정렬 퍼즐 | com.grandgames.magicsort | 탭 → 물약 따르기 → 색상 정렬 |
| Car Match | 3D 자동차 매칭 | com.grandgames.carmatch | 탭 → 자동차 홀더 이동 → 3매칭 |

---

## 4. 10가지 전문 미션 상세

### 미션 1: Full Playthrough A (도메인: gameplay)

**목표**: 레벨 1부터 순차 진행하며 게임 전체 구조 파악

**관찰 항목**:
1. 총 레벨 수 (레벨 선택 화면에서 스크롤 끝까지)
2. 레벨별 보드/격자 크기 변화 (숫자로 기록)
3. 레벨별 오브젝트(화살표/병/자동차) 수 변화
4. 난이도 전환점 (새 메커니즘 등장 레벨)
5. 챕터/구간 구조
6. 클리어 조건, 실패 조건

**자동화 캡처 시퀀스** (8장):
```
메인 메뉴 → 레벨1 보드 → 레벨1 결과 → 레벨3 보드 → 레벨5 결과 →
고레벨 보드 → 레벨 선택 → 레벨 선택(스크롤)
```

**C10+ 기여**: 전담 배정으로 후반부 레벨(50+)까지 반드시 도달. 기존 C10에서는 10인 중 2~3인만 후반까지 진행하여 데이터 부족.

---

### 미션 2: Full Playthrough B (도메인: gameplay)

**목표**: 미션 1과 독립적인 두 번째 플레이스루. 교차 검증용.

**관찰 항목**: 미션 1과 동일하지만, 추가로:
- 메뉴 구조, 버튼 배치, UI 요소
- 게임 정체성 (제목, 장르, 아트 스타일)
- 설정 화면 탐색

**자동화 캡처 시퀀스** (8장):
```
메인 메뉴 → 설정 화면 → 레벨1 → 레벨1 결과 → 레벨2 →
레벨3 결과 → 진행도 → 스크롤
```

**C10+ 기여**: 미션 1과의 독립 비교로 관찰 오류 검출. 불일치 항목은 미션 10(교차검증)에서 최종 확인.

---

### 미션 3: Numeric Data Collection (도메인: numeric)

**목표**: 정확한 숫자값 추출에 특화. **의도적 실수 횟수 조절**로 임계값 역산.

**관찰 항목**:
1. 별점 기준: 실수 0회=?성, 1회=?성, 2회=?성, 3+회=?성
2. 점수/코인 보상: 별점별 보상량
3. 레벨별 데이터 테이블: 레벨#, 격자크기, 오브젝트수, 색상수, 목표이동수
4. 진행 공식 추정: 데이터에서 패턴/공식 역산
5. 부스터 수량, 한계값

**자동화 캡처 시퀀스** (6장):
```
레벨 시작 보드 → 퍼펙트(0실수) 결과 → 2실수 결과 → 5실수 결과 →
고레벨 보드 → 고레벨 결과
```

**핵심 기법 — 의도적 실수 횟수 조절**:
```python
# 0실수 → 3성 확인
play_level(c, taps=3)
shot("02_perfect_result")

# 2실수 → 2성/1성 경계 확인
tap(50, 400, wait=0.5)  # 의도적 빗맞춤
tap(50, 400, wait=0.5)  # 의도적 빗맞춤
play_level(c, taps=4)
shot("03_2mistake_result")

# 5실수 → 0성 경계 확인
for _ in range(5):
    tap(50, 400, wait=0.3)  # 5회 의도적 빗맞춤
play_level(c, taps=5)
shot("04_5mistake_result")
```

이 기법으로 Tap Shift의 별점 임계값을 정확히 역산:
- 0 wrong taps = 3성, 1-2 = 2성, 3-5 = 1성, 6+ = 0성

**C10+ 기여**: 기존 C10에서는 "별점이 3단계" 사실만 확인. C10+는 정확한 임계값 구간까지 역산. (+11%p)

---

### 미션 4: Timing Observation (도메인: timing)

**목표**: 프레임 단위 애니메이션 시간 계측

**관찰 항목**:
1. 오브젝트 이동 애니메이션: 시작→종료 상태, 추정 소요 시간
2. 이동 가속/감속 패턴: 등속 vs ease-in vs ease-out
3. 이동 중 변형: 늘어남(stretch), 축소, 회전 여부
4. 매칭/완성 연출: 사라짐, 바운스, 스케일 변화
5. 팝업 애니메이션: 등장/퇴장 방식
6. 페이지 전환: 페이드, 슬라이드, 즉시
7. 피드백 애니메이션: 막힘 흔들림, 힌트 펄스

**자동화 캡처 시퀀스** (5장):
```
이동 전 → 이동 중(0.3초 후 캡처) → 이동 후 → 팝업 등장 중 → 팝업 완료
```

**핵심 기법 — 프레임 카운트 측정**:
```python
# 이동 직전 캡처
shot("01_before_move")
# 0.3초 후 캡처 (이동 중간 상태)
tap(*c["center"], wait=0.3)
shot("02_during_move")
# 1초 후 캡처 (이동 완료)
time.sleep(1)
shot("03_after_move")
```

스크린샷 간 상태 변화에서 대략적 시간 추정 → 동일 애니메이션 5회 이상 반복 관찰으로 평균값 도출.

**C10+ 기여**: C10에서 **최약점 영역**이었던 애니메이션 타이밍(50%)을 74%까지 +24%p 개선. 다만 내부 이징 곡선의 정확한 수학적 표현 복원에는 한계.

---

### 미션 5: Visual Measurement (도메인: visual)

**목표**: 픽셀 단위 UI 크기, 간격, 비율, 색상 측정

**관찰 항목**:
1. 격자/보드: 전체 크기, 셀 크기, 셀 간격 (px 단위)
2. 오브젝트: 크기, 격자 대비 비율 (model_scale)
3. 홀더/병 영역: 위치(Y좌표), 슬롯 간격
4. UI 요소: 버튼 크기, 여백, 상단/하단 바 높이
5. 색상: 주요 오브젝트 색상의 HEX 코드
6. 화면 비율: 해상도 추정 (16:9, 9:16 등)
7. Y 오프셋: 보드 시작 Y좌표

**자동화 캡처 시퀀스** (6장):
```
소형 격자(초반) → 격자 상세 → 중형 격자 → 대형 격자(후반) →
UI 오버레이 → 설정 UI
```

**핵심 기법 — 다해상도 비율 역산**:
- 에뮬레이터 스크린샷을 이미지 분석으로 픽셀 측정
- 복수 해상도 비교로 내부 기준 해상도 추론
- Tap Shift 결과: base_unit = 60px, position_snap = 30px (half-unit) 정확 도출

**C10+ 기여**: C10의 45%에서 71%로 +26%p 개선. 3D 렌더링 게임(Car Match)의 정확한 오프셋/스케일 복원에는 한계.

---

### 미션 6: Edge Case Testing (도메인: edge_case)

**목표**: 리소스 고갈과 극단적 상태 탐색

**관찰 항목**:
1. 되돌리기(Undo): 최대 몇 회 가능? 소진 후 UI 변화?
2. 힌트: 최대 몇 개? 소진 후 UI 변화?
3. 생명(Lives): 최대 몇 개? 소진 과정? 회복 메커니즘?
4. 부스터: 각 종류별 초기 수량? 소진 후 구매 UI?
5. 홀더/병: 최대 용량? 가득 찰 때의 동작?
6. 실패 조건: 정확히 어떤 상태에서 실패 판정?
7. 재시작 흐름: 실패 후 선택지

**자동화 캡처 시퀀스** (6장):
```python
# 힌트 전부 소진
for i in range(5):
    tap(bx - 200, by, wait=1)
shot("01_hints_used")

# Undo 전부 소진
for i in range(12):
    tap(bx, by, wait=0.5)
shot("02_undos_used")

# 강제 실패 유도
for _ in range(8):
    tap(*c["tl"], wait=0.3)
    tap(*c["br"], wait=0.3)
shot("03_near_fail")
shot("04_fail_state")

# 부스터 상점
tap(*c["booster"], wait=2)
shot("05_booster_shop")
```

**C10+ 기여**: 체계적 극단 테스트로 max_undo=10, max_hint=3, max_lives=3 등 한계값 정확 확인.

---

### 미션 7: Economy Tracking (도메인: economy)

**목표**: 재화 흐름 전체 루프 정밀 추적

**관찰 항목**:
1. 초기 재화: 게임 최초 시작 시 코인/젬 수 (정확한 숫자)
2. 레벨 보상: 레벨별 (별점, 코인 보상) 쌍 기록
3. 부스터 가격: 각 부스터의 코인/젬 가격
4. 일일 보상: 7일 주기 보상 (가능한 범위까지)
5. 여정/마일스톤 보상: 레벨 마일스톤별 보상
6. 광고 빈도: 몇 레벨마다 전면광고 노출?
7. IAP 상품: 상점에 표시된 상품과 가격

**자동화 캡처 시퀀스** (6장):
```
초기 코인 표시 → 레벨1 보상 → 레벨2 보상 → 레벨3 보상 →
상점 화면 → 레벨3 후 코인 상태
```

**C10+ 기여**: 기존 C10에서 가장 큰 오류였던 "시작 코인 = 관찰 시점 코인" 혼동을 해결. 전담 트래커가 코인 변화량을 추적하여 시작값 역산. (+20%p)

---

### 미션 8: Algorithm Behavior (도메인: algorithm)

**목표**: 외부 행동에서 내부 알고리즘 추론

**관찰 항목**:
1. 경로 탐색: 자동차가 장애물을 어떻게 우회하는가?
2. 충돌 판정: 이동 가능/불가능 결정 방식
3. 레벨 생성: 같은 레벨 재시작 시 배치가 바뀌나? (절차적 vs 고정)
4. 힌트 로직: 힌트 추천 수의 패턴
5. 매칭 검사: 연속 동일 타입 감지 방식
6. 교착 판정: 진행 불가 상태 감지 여부

**핵심 기법 — 결정론적/확률적 판별**:
```python
# 동일 레벨 3회 재시작 → 배치 비교
shot("04_restart_layout_1")
press_back(); tap(*c["popup"]); tap(*c["play"])
shot("05_restart_layout_2")
# 배치 동일 → 고정 레벨 데이터 / 배치 변동 → 절차적 생성
```

**C10+ 기여**: Tap Shift에서 DFS+백트래킹 솔버, AABB sweep-to-boundary 충돌 시스템 정확 도출.

---

### 미션 9: State & Flow Mapping (도메인: state)

**목표**: 모든 화면과 전환을 완전 매핑

**관찰 항목**:
1. 화면 목록: 모든 고유 화면 (메인메뉴, 게임, 일시정지, 완료, 실패 등)
2. 전환 다이어그램: A → B (어떤 동작으로)
3. 팝업 목록: 모든 팝업 종류와 출현 조건
4. 설정 옵션: 설정 화면의 모든 항목
5. 저장 동작: 앱 종료 후 재시작 시 보존되는 상태
6. 게임 상태 수: 총 몇 개의 상태가 존재하는가?

**자동화 캡처 시퀀스** (6장):
```
메인 메뉴 → 게임플레이 → 일시정지 팝업 → 완료 팝업 → 설정 → 실패 팝업
```

**C10+ 기여**: Tap Shift 9개 상태, Magic Sort 6개 상태, Car Match 5개 상태 정확 매핑.

---

### 미션 10: Cross-Validation (도메인: cross_validation)

**목표**: 미션 1~9의 불일치 항목 재확인. 근접(0.7) 판정을 정확(1.0)으로 승격.

**관찰 항목**:
1. 별점 기준: 실수 횟수별 별점 변화를 정밀 재관찰
2. 레벨 진행: 격자 크기가 정확히 몇 레벨에서 바뀌는지
3. 부스터 상세: 각 부스터의 정확한 효과와 초기 수량
4. 색상 수: 초반/중반/후반 활성 색상 수
5. 난이도 전환: 어느 레벨에서 체감 난이도가 급변하는지

**자동화 캡처 시퀀스** (5장):
```
3성 시도(퍼펙트) → 1성 시도(6실수) → 진행도 → 부스터 상세 → 후반 레벨
```

**C10+ 기여**: 게임당 8~12건의 0.7→1.0 승격 확인. 전체 정확도에 +12.2%p 기여.

---

## 5. 자동화 파이프라인 (6단계)

### 전체 흐름

```
Phase 1: CAPTURE ──→ Phase 2: VISION ──→ Phase 3: AGGREGATE
(30 sessions)        (30 Claude calls)    (3 Claude calls)
    │                     │                    │
    ▼                     ▼                    ▼
 스크린샷            관찰 텍스트         전문가 합의 문서
 sessions_plus/      observations_plus/   aggregated/
                                              │
Phase 4: SPEC ◄────────────────────────────────┘
(3 Claude calls)
    │
    ▼
Phase 5: SCORING ──→ Phase 6: REPORT
(3 Claude calls)      (집계/마크다운)
```

**총 Claude CLI 호출: ~39회**
**총 소요 시간: 병렬 처리 기준 1.5~2시간**

### Phase 1: CAPTURE (30 세션)

3게임 × 10미션 = 30개 자동화 세션. 각 세션에서 5~8장 스크린샷 캡처.

**도구**:
- BlueStacks 에뮬레이터 (Pie64)
- ADB (Android Debug Bridge) — `HD-Adb.exe`
- Device: `emulator-5554`

**ADB 명령 패턴**:
```bash
# 스크린샷 캡처
adb -s emulator-5554 exec-out screencap -p > screenshot.png

# 탭 입력
adb -s emulator-5554 shell input tap 400 980

# 스와이프 (스크롤)
adb -s emulator-5554 shell input swipe 400 800 400 200 500

# 뒤로가기
adb -s emulator-5554 shell input keyevent KEYCODE_BACK

# 앱 강제 종료
adb -s emulator-5554 shell am force-stop com.paxiegames.tapshift

# 앱 실행
adb -s emulator-5554 shell monkey -p com.paxiegames.tapshift -c android.intent.category.LAUNCHER 1
```

**게임별 좌표 맵**:
```python
COORDS = {
    "tapshift": {
        "play": (400, 980), "settings": (690, 145),
        "center": (400, 550), "tl": (200, 350), "tr": (600, 350),
        "bl": (200, 750), "br": (600, 750),
        "booster": (400, 1100), "popup": (400, 800),
    },
    # magicsort, carmatch도 유사 구조
}
```

**Skip 로직**: 이미 4장 이상 캡처된 세션은 자동 건너뜀 (멱등성 보장).

### Phase 2: VISION (30 Claude 호출)

각 세션의 스크린샷을 Claude Sonnet에게 미션별 전문 프롬프트로 분석 요청.

**호출 방식**:
```python
cmd = [CLAUDE, "--print", "--model", "sonnet", "--allowed-tools", "Read"]
# input: 이미지 경로 목록 + 미션별 전문 프롬프트
# output: 구조화된 관찰 텍스트
```

**출력**: `observations_plus/{game}_session_{01-10}.txt` (30개 파일)

### Phase 3: AGGREGATE (3 Claude 호출)

10명의 전문가 관찰을 도메인 가중치 적용하여 하나의 합의 문서로 통합.

**도메인 가중 규칙**:
```
수치 관련 → 전문가 3 (Numeric) 데이터 우선
타이밍 관련 → 전문가 4 (Timing) 데이터 우선
시각 관련 → 전문가 5 (Visual) 데이터 우선
경제 관련 → 전문가 7 (Economy) 데이터 우선
알고리즘 관련 → 전문가 8 (Algorithm) 데이터 우선
상태/전환 관련 → 전문가 9 (State) 데이터 우선
전문가 1-2: 독립 플레이스루 교차 비교
전문가 10: 재확인으로 신뢰도 상향
```

**출력 구조** (12개 섹션):
1. 게임 정체성
2. UI 구성
3. 게임 메커니즘
4. 수치 데이터 (Numeric Expert 주도)
5. 시각 측정 (Visual Expert 주도)
6. 재화/경제 (Economy Expert 주도)
7. 난이도/레벨 진행
8. 부스터/특수기능
9. 타이밍 (Timing Expert 주도)
10. 알고리즘 추론 (Algorithm Expert 주도)
11. 상태/흐름 (State Expert 주도)
12. 한계값 (Edge Case Expert 주도)

**신뢰도 태깅**:
- `[HIGH]`: 2개 이상 독립 세션에서 동일 값으로 직접 관측
- `[MED]`: 1개 세션 직접 관측 또는 강한 추론 근거
- `[LOW]`: 일반적 장르 관례 또는 간접 추론

**출력**: `aggregated/{game}_10x_plus_consensus.txt` (3개 파일)

### Phase 4: SPEC GENERATION (3 Claude 호출)

합의 문서만으로 (패턴 카드 없이) 32개 파라미터를 추정.

**프롬프트 구조**:
```
입력: 전문가 합의 문서 + 32개 파라미터 목록
규칙:
  [HIGH] 항목 → 확정적 값
  [MED] 항목 → 합리적 추정
  [LOW] 항목 → 추론 기반
  관찰 불가능 → null

출력: YAML 형식 (id, name, value, confidence, source)
```

**출력**: `specs/{game}_C10_plus_spec.yaml` (3개 파일)

### Phase 5: SCORING (3 Claude 호출)

생성된 스펙을 Ground Truth와 파라미터별 비교 채점.

**출력**: `scoring/{game}_C10_plus_score.yaml` (3개 파일)

### Phase 6: REPORT (로컬 집계)

Python 스크립트가 채점 파일에서 average를 추출하여 마크다운 보고서 생성.

**출력**: `결과보고서_C10_plus.md`

---

## 6. 전문가 가중 합의 알고리즘

### 6-1. 가중치 매핑

```
parameter.category → primary_expert → 해당 전문가 데이터 우선 채택
                   → secondary_experts → 보조 참조
                   → cross_validators → 전문가 1, 2, 10의 교차 확인
```

| 파라미터 카테고리 | Primary Expert | Secondary | Cross-Validator |
|-----------------|:--------------:|:---------:|:---------------:|
| 코어 상수 | 3 (Numeric) | 6 (Edge) | 1, 2, 10 |
| 별점/점수 | 3 (Numeric) | 7 (Economy) | 10 |
| 애니메이션 | 4 (Timing) | 5 (Visual) | 10 |
| 시각/레이아웃 | 5 (Visual) | - | 1, 2 |
| 알고리즘 | 8 (Algorithm) | - | 1, 2, 10 |
| UI/해상도 | 5 (Visual) | 9 (State) | 1, 2 |
| 아키텍처 | 9 (State) | 8 (Algorithm) | - |
| 게임플레이 | 1, 2 (Playthrough) | 6 (Edge) | 10 |
| 난이도 | 3 (Numeric) | 1, 2 | 10 |
| 경제 | 7 (Economy) | - | 10 |

### 6-2. 불일치 해결 규칙

1. **Primary Expert 단독 측정 → 채택**: 해당 도메인 전문가만 측정 가능한 값
2. **Primary + Cross-Validator 일치 → 확정**: 신뢰도 [HIGH]
3. **Primary vs Other 불일치 → Primary 우선**: 전문 도메인 가중
4. **모든 전문가 일치 → 확정**: 신뢰도 [HIGH]
5. **다수결 불충분 (3:3 등) → 전문가 10이 재확인**

---

## 7. 측정 대상: 게임별 32 파라미터

### Tap Shift (32개)

| ID | 파라미터 | 카테고리 | 관찰 가능성 |
|----|---------|---------|:----------:|
| TS01 | total_levels | core_constants | O |
| TS02 | max_lives | core_constants | O |
| TS03 | max_undo_count | core_constants | O |
| TS04 | max_hint_count | core_constants | O |
| TS05 | interstitial_frequency | monetization | O |
| TS06 | arrow_move_speed | core_constants | △ (프레임 추정) |
| TS07 | max_arrow_clamp | core_constants | O |
| TS08 | star_rating_system | scoring | O |
| TS09 | base_unit | animation | △ (픽셀 측정) |
| TS10 | position_snap | animation | △ (픽셀 측정) |
| TS11 | duration_clamp | animation | △ (프레임 추정) |
| TS12 | stretch_phase | animation | △ (프레임 추정) |
| TS13 | stretch_max | animation | △ (프레임 추정) |
| TS14 | snap_phase | animation | △ (프레임 추정) |
| TS15 | arrow_colors | visual | O |
| TS16 | head_ratio | visual | O (측정) |
| TS17 | shaft_height_ratio | visual | O (측정) |
| TS18 | collision_system | algorithm | O (행동 추론) |
| TS19 | performance_complexity | algorithm | O (행동 추론) |
| TS20 | solver_algorithm | algorithm | O (힌트 패턴) |
| TS21 | ui_reference_resolution | ui | △ (역산) |
| TS22 | total_files | architecture | **X** |
| TS23 | pattern_count | architecture | **X** |
| TS24 | state_count | architecture | O (전환 매핑) |
| TS25 | serialization_format | architecture | O (행동 추론) |
| TS26 | arrow_directions | gameplay | O |
| TS27 | arrow_count_progression | difficulty | O (다레벨 비교) |
| TS28 | grid_size_range | gameplay | O (측정) |
| TS29 | tap_mechanic | gameplay | O |
| TS30 | goal_condition | gameplay | O |
| TS31 | level_generation | algorithm | O (재시작 비교) |
| TS32 | save_system | architecture | O (행동 추론) |

> **O** = 직접 관찰 가능, **△** = 전문 기법으로 추정 가능, **X** = 소스코드 접근 없이 불가

### Magic Sort / Car Match

동일 구조의 32 파라미터. 게임 특화 항목만 변경:
- Magic Sort: bottle_max_height, colors_total, pour_duration, blocker_type_count 등
- Car Match: cell_size, holder_max_slots, tunnel_spawn_count, pathfinding_algorithm 등

전체 목록은 `run_c10_plus.py`의 `PARAM_LIST` 딕셔너리 참조.

---

## 8. 채점 기준

| 점수 | 판정 | 기준 |
|:----:|------|------|
| 1.0 | Exact | Ground Truth와 정확 일치 |
| 0.7 | Close | 20% 이내 오차 또는 범위 내 포함 |
| 0.4 | Partial | 개념은 맞으나 값이 틀림 |
| 0.1 | Wrong | 잘못된 값 |
| 0.0 | Missing | null 또는 누락 |

**평균 계산**: `average = sum(32개 점수) / 32`

---

## 9. 실험 결과

### 9-1. 최종 결과 (수정 실행)

| 게임 | C10+ 점수 | 1.0 (정확) | 0.7 (근접) | 0.0 (누락) |
|------|:---------:|:----------:|:----------:|:----------:|
| Tap Shift | **90.0%** | 26개 | 4개 | 2개 |
| Magic Sort | **88.7%** | 27개 | 2개 | 3개 |
| Car Match | **89.7%** | 28개 | 1개 | 3개 |
| **평균** | **89.5%** | | | |

### 9-2. C10 대비 개선

| 게임 | C10 | C10+ | 개선 |
|------|:---:|:----:|:----:|
| Tap Shift | 84.4% | 90.0% | +5.6%p |
| Magic Sort | 85.9% | 88.7% | +2.8%p |
| Car Match | 84.7% | 89.7% | +5.0%p |
| **평균** | **85.0%** | **89.5%** | **+4.5%p** |

### 9-3. 게임별 상세 채점 (Tap Shift)

| ID | 파라미터 | Ground Truth | C10+ 생성값 | 점수 |
|----|---------|-------------|------------|:----:|
| TS01 | total_levels | 100 | 100 | 1.0 |
| TS02 | max_lives | 3 | 3 | 1.0 |
| TS03 | max_undo_count | 10 | 10 | 1.0 |
| TS04 | max_hint_count | 3 | 3 | 1.0 |
| TS05 | interstitial_frequency | 3 (every 3 levels) | 3 (every 3 levels) | 1.0 |
| TS06 | arrow_move_speed | 15.0 | 13~16 units/s | 0.7 |
| TS07 | max_arrow_clamp | 20 | 20 | 1.0 |
| TS08 | star_rating_system | 0-star~3-star 4단계 | 0~3성 4단계, wrong tap 기준 | 1.0 |
| TS09 | base_unit | 60.0 | 60 pixels | 1.0 |
| TS10 | position_snap | 30.0 (half-unit) | 30 pixels (half-cell snap) | 1.0 |
| TS11 | duration_clamp | [0.25, 0.7]s | [0.20, 0.65]s | 0.7 |
| TS12 | stretch_phase | first 40% | first 35~45% | 0.7 |
| TS13 | stretch_max | 1.6 | 1.4~1.7 | 0.7 |
| TS14 | snap_phase | last 60% | last 60% | 1.0 |
| TS15 | arrow_colors | up=#4CAF50, ... | 정확 일치 | 1.0 |
| TS16 | head_ratio | 0.35 | 0.35 | 1.0 |
| TS17 | shaft_height_ratio | 0.55 | 0.55 | 1.0 |
| TS18 | collision_system | AABB sweep-to-boundary | AABB sweep-to-boundary | 1.0 |
| TS19 | performance_complexity | O(n) per tap, n<=20 | O(n) per tap, n<=20 | 1.0 |
| TS20 | solver_algorithm | DFS with backtracking | DFS with backtracking | 1.0 |
| TS21 | ui_reference_resolution | [720, 1280] | [720, 1280] | 1.0 |
| TS22 | total_files | 50 | null | 0.0 |
| TS23 | pattern_count | 9 | null | 0.0 |
| TS24 | state_count | 9 | 9 | 1.0 |
| TS25 | serialization_format | JSON (JsonUtility) | JSON (JsonUtility) | 1.0 |
| TS26 | arrow_directions | 4 (up/down/left/right) | 4 (up/down/left/right) | 1.0 |
| TS27 | arrow_count_progression | 6구간 정확 | 6구간 정확 | 1.0 |
| TS28 | grid_size_range | 200×200 ~ 450×450 | 200×200 ~ 450×450 | 1.0 |
| TS29 | tap_mechanic | 정확 | 정확 | 1.0 |
| TS30 | goal_condition | 전체 화살표 보드 탈출 | 전체 화살표 보드 탈출 | 1.0 |
| TS31 | level_generation | 절차적 생성 + JSON | 절차적 생성 + JSON | 1.0 |
| TS32 | save_system | PlayerPrefs 키 목록 | PlayerPrefs 키 목록 | 1.0 |
| | | | **합계/평균** | **28.8 / 0.900** |

> Magic Sort (88.7%), Car Match (89.7%) 상세 채점은 `scoring/` 디렉토리 참조.

---

## 10. 실패 사례 분석 (1차 실행)

### 10-1. 자동 생성된 보고서의 첫 결과

| 게임 | C10+ (1차) | C10 (기준선) | 차이 |
|------|:---------:|:----------:|:----:|
| Tap Shift | 31.6% | 84.4% | **-52.8%p** |
| Magic Sort | 14.1% | 85.9% | **-71.8%p** |
| Car Match | 16.9% | 84.7% | **-67.8%p** |
| **평균** | **20.9%** | **85.0%** | **-64.1%p** |

### 10-2. 실패 원인: GDPR 팝업 미처리

```
[원인]
앱 최초 실행 시 GDPR/약관 동의 팝업이 화면을 가린 채
자동화 스크립트가 탭 좌표를 전송 → 팝업 뒤의 게임 UI에 입력 전달 안됨

[결과]
- 30세션 × 5~8장 = 총 ~180장 스크린샷 중 대부분이 동일한 팝업 화면
- 인게임 보드/격자/결과 화면 0장 확보
- Vision 분석은 로비 정보(코인 85, 레벨 14)만 추출
- Spec 생성은 게임명과 장르 추론에만 의존 → 대부분 null 또는 환각
```

### 10-3. 교훈 및 해결

| 문제 | 해결책 |
|------|--------|
| GDPR 팝업 | 캡처 전 팝업 닫기 탭 추가: `tap(*c["popup"], wait=2)` |
| 앱 상태 비초기화 | `force_stop(pkg)` + `launch_game(pkg)` 순차 실행 |
| 캡처 검증 없음 | 스크린샷 파일 크기 검증: `len(r.stdout) > 1000` |
| 동일 화면 반복 | Skip 로직: `len(existing) >= 4`이면 건너뜀 |

**결론**: C10+ 방법론 자체의 문제가 아닌, 자동화 인프라의 전처리 누락이 원인. 수정 후 재실행에서 89.5% 달성.

---

## 11. 카테고리별 개선 분석

### 11-1. C10 → C10+ 카테고리별 비교

| 카테고리 | C10 | C10+ | 개선 | 개선 요인 |
|---------|:---:|:----:|:----:|----------|
| 게임플레이/메커니즘 | 95% | **97%** | +2%p | 풀스루 + 경계조건 조합 |
| 수치/밸런스 | 80% | **91%** | +11%p | 전담 역추정 + 의도적 실수 |
| 애니메이션/타이밍 | 50% | **74%** | +24%p | 프레임 카운트 정량 측정 |
| 시각/레이아웃 | 45% | **71%** | +26%p | 픽셀 단위 정밀 측정 |
| 경제 시스템 | 75% | **95%** | +20%p | 전담 트래커 전체 루프 추적 |
| 아키텍처 (내부) | 0% | **0%** | - | 관찰 불가 영역, 개선 없음 |

### 11-2. 카테고리별 개선 메커니즘

**수치/밸런스 (+11%p)**:
- Before (C10): "별점이 3단계" 사실만 확인
- After (C10+): 의도적 실수 0/2/5회 → 임계값 구간 [0/1-2/3-5/6+] 정확 역산
- 회귀분석: 여러 레벨의 (오브젝트 수, 레벨 번호) 쌍에서 공식 도출

**애니메이션/타이밍 (+24%p)**:
- Before (C10): "느린/빠른" 체감 수준
- After (C10+): 동일 애니메이션 5회 반복 관찰 + 프레임 카운트
- 한계: 내부 이징 곡선(ease-out sine 등)의 수학적 표현은 복원 불가 → 74%

**시각/레이아웃 (+26%p)**:
- Before (C10): "격자가 커진다" 정도
- After (C10+): 스크린샷 픽셀 측정, 다해상도 비율 역산
- 결과: base_unit=60px, position_snap=30px 정확 도출
- 한계: 3D 렌더링의 정확한 오프셋/스케일 복원 한계 → 71%

**경제 시스템 (+20%p)**:
- Before (C10): 관찰 시점 코인(85)을 시작 코인으로 오인
- After (C10+): 전담 트래커가 레벨별 보상 추적, 시작값 역산
- 결과: Magic Sort 시작코인=100, 시작젬=5 정확 도출

---

## 12. C10+ vs D1_10 비교 및 순차 결합

### 12-1. 두 접근법의 강점

| 항목 | C10+ (전문 관찰) | D1_10 (관찰 + L1 패턴) |
|------|:---:|:---:|
| **정확도** | **89.5%** | **82.5%** |
| 법적 리스크 | 없음 | 안전 (L1 = 일반 설계 지식) |
| API 비용 | ~45회 | ~6회 |
| 패턴 카드 필요 | 불필요 | L1 필요 |
| 소요 시간 | 1.5~2시간 | ~30분 |

### 12-2. 카테고리별 우위

| 카테고리 | C10+ | D1_10 | 우위 |
|---------|:---:|:---:|:----:|
| 수치/밸런스 | **91%** | 84% | C10+ |
| 애니메이션/타이밍 | **74%** | 56% | C10+ |
| 시각/레이아웃 | **71%** | 51% | C10+ |
| 경제 시스템 | **95%** | 89% | C10+ |
| 아키텍처 (내부) | 0% | **41%** | D1_10 |

**핵심**: 두 접근법은 강점이 겹치지 않는 **상호보완 관계**.

### 12-3. 순차 결합 결과

```
C10+ (89.5%) → L1 패턴 보완 (아키텍처 0%→41%) = 93.2%
```

| 결합 방법 | 정확도 | 법적 안전 |
|----------|:------:|:--------:|
| C10+ 단독 | 89.5% | O |
| D1_10 단독 | 82.5% | O |
| **C10+ → L1 순차 결합** | **93.2%** | **O** |

---

## 13. 전체 조건 비교표

| 순위 | 조건 | 정확도 | 패턴 카드 | 관찰 | 법적 리스크 |
|:---:|------|:------:|:---------:|:----:|:----------:|
| 1 | D10 (10인+L2) | **98.5%** | L2 | 10인 자유 | 안전 |
| 2 | B2 (컨셉+L2) | **97.8%** | L2 | 없음 | 안전 |
| 3 | D2 (1인+L2) | **96.3%** | L2 | 1인 자유 | 안전 |
| 4 | C10+→L1 | **93.2%** | L1 | 10인 전문 | 안전 |
| 5 | **C10+** | **89.5%** | 없음 | 10인 전문 | **없음** |
| 6 | C10 (10인 자유) | **85.0%** | 없음 | 10인 자유 | 없음 |
| 7 | D1_10 (10인+L1) | **82.5%** | L1 | 10인 자유 | 안전 |
| 8 | B1 (컨셉+L1) | **77.7%** | L1 | 없음 | 안전 |
| 9 | D1 (1인+L1) | **59.2%** | L1 | 1인 자유 | 안전 |
| 10 | A (컨셉만) | **39.5%** | 없음 | 없음 | - |
| 11 | C (1인 관찰) | **36.5%** | 없음 | 1인 자유 | 없음 |

---

## 14. 관찰 불가 한계 (Observation Ceiling)

### 14-1. 원천적으로 관찰 불가능한 파라미터

| 게임 | 관찰 불가 파라미터 | 개수 |
|------|-----------------|:----:|
| Tap Shift | total_files (50), pattern_count (9) | 2 |
| Magic Sort | max_gen_attempts (100), save_prefix ("MS_"), pattern_count (9) | 3 |
| Car Match | pathfinding_algorithm (A*), namespace ("CarMatch"), pattern_count (8) | 3 |

### 14-2. 이론적 상한 계산

```
관찰 가능 파라미터: 32 - 2~3 = 29~30개
이론적 상한: (29 × 1.0 + 3 × 0.0) / 32 = 90.6%

C10+ 실측: 89.5%
상한 대비 달성률: 89.5% / 90.6% = 98.8%
```

**결론**: C10+는 관찰 가능 영역의 이론적 상한에 거의 도달(98.8%)했다. 추가 개선은 관찰 불가 영역을 L1 패턴 카드로 보완해야만 가능.

---

## 15. 운영 가이드

### 15-1. 전제 조건

| 항목 | 요구사항 |
|------|---------|
| 에뮬레이터 | BlueStacks (Pie64), ADB 활성화 |
| Device ID | emulator-5554 (BlueStacks 기본) |
| 게임 설치 | 대상 게임 3종 APK 설치 완료 |
| Claude CLI | 설치 및 인증 완료 |
| Python | 3.10+ |

### 15-2. 새 게임에 C10+ 적용 시 수정 항목

1. **GAMES 딕셔너리**: 게임명, 패키지명, 접두사
2. **COORDS 딕셔너리**: 게임별 UI 좌표 (에뮬레이터에서 사전 측정)
3. **PARAM_LIST**: 게임별 32개 파라미터 정의
4. **capture_session()**: 게임별 캡처 시퀀스 (탭 좌표, 대기 시간)
5. **Ground Truth**: 소스코드에서 실제 값 추출 (검증용)

### 15-3. 주의사항

| 주의 | 설명 |
|------|------|
| GDPR 팝업 | 각 세션 시작 시 팝업 닫기 탭 필수 |
| 앱 상태 | force_stop → launch_game 순서로 깨끗한 상태 보장 |
| 캡처 타이밍 | 애니메이션 중 캡처를 위해 wait 시간 정밀 조정 |
| 스크린샷 품질 | ADB screencap의 PNG 크기 > 1000 bytes 검증 |
| API 비용 | 전체 ~39회 Claude 호출 (Sonnet 모델) |

### 15-4. 실행 명령

```bash
cd /e/AI/projects/CleanRoomTest/multi_tester
python3 run_c10_plus.py
```

출력 파일:
```
observations_plus/    30개 관찰 텍스트
aggregated/          3개 합의 문서
specs/               3개 C10+ 스펙
scoring/             3개 채점 결과
결과보고서_C10_plus.md  최종 보고서
```

---

## 16. 파일 구조 및 재현 방법

### 16-1. 디렉토리 구조

```
E:\AI\projects\CleanRoomTest\
├── capture_games.sh                     # ADB 스크린샷 캡처 (수동)
├── C10_Plus_Methodology.md              # [본 문서]
│
├── ground_truth/                        # 소스코드 기반 정답값
│   ├── tapshift_ground_truth.yaml       # Tap Shift 32 파라미터
│   ├── magicsort_ground_truth.yaml      # Magic Sort 32 파라미터
│   └── carmatch_ground_truth.yaml       # Car Match 32 파라미터
│
├── pattern_cards/                       # 클린룸 패턴 카드
│   ├── level1_design_intent/            # L1: 정성적 설계 의도
│   └── level2_structural_hint/          # L2: 정량적 수치 힌트
│
├── specs/                               # 조건별 생성 스펙
│   ├── A_concept_only/
│   ├── B1_design_intent/
│   ├── B2_structural_hint/
│   ├── C_ai_user_only/
│   ├── D1_ai_user_design_intent/
│   ├── D2_ai_user_structural_hint/
│   ├── C10_spec/
│   ├── C10_plus_spec/                   # [C10+ 결과]
│   ├── D1_10_spec/
│   └── D10_spec/
│
├── comparison/                          # 분석 보고서
│   ├── full_summary_report.md           # 6조건 비교 (영문)
│   ├── full_comparison_report.yaml
│   ├── summary_report.md
│   └── 결과보고서_한글.md
│
├── multi_tester/                        # 10인 실험 전체
│   ├── run_experiment.py                # C10/D10 메인 실험
│   ├── run_c10_plus.py                  # [C10+ 실험 스크립트]
│   ├── run_d1_10.py                     # D1_10 실험
│   │
│   ├── observations/                    # C10 자유 관찰 (30개)
│   ├── observations_plus/               # C10+ 전문 관찰 (30개)
│   ├── sessions/                        # C10 스크린샷
│   ├── sessions_plus/                   # C10+ 스크린샷
│   │
│   ├── aggregated/                      # 합의 문서
│   │   ├── tapshift_10x_consensus.txt        # C10 합의
│   │   ├── tapshift_10x_plus_consensus.txt   # C10+ 합의
│   │   └── ...
│   │
│   ├── scoring/                         # 채점 결과
│   │   ├── tapshift_C10_score.yaml
│   │   ├── tapshift_C10_plus_score.yaml
│   │   ├── tapshift_D1_10_score.yaml
│   │   ├── tapshift_D10_score.yaml
│   │   └── ... (게임당 4개 × 3게임 = 12개)
│   │
│   ├── 결과보고서_10x.md               # C10/D10 보고서
│   ├── 결과보고서_C10_plus.md           # C10+ 보고서
│   ├── 결과보고서_D1_10.md              # D1_10 보고서
│   └── 결과보고서_통합.md               # C10+ vs D1_10 통합
│
├── ai_user_observations/                # 1인 AI 관찰
├── ai_user_data/                        # 1인 AI 데이터
└── screenshots/                         # 수동 캡처
```

### 16-2. 재현 단계

```
1. BlueStacks 실행 + ADB 연결 확인
   $ adb devices
   → emulator-5554 표시 확인

2. 3개 게임 설치 확인
   $ adb shell pm list packages | grep -E "tapshift|magicsort|carmatch"

3. C10+ 실험 실행
   $ cd /e/AI/projects/CleanRoomTest/multi_tester
   $ python3 run_c10_plus.py

4. 결과 확인
   $ cat 결과보고서_C10_plus.md
   $ cat scoring/tapshift_C10_plus_score.yaml
```

---

## 부록 A: 용어 사전

| 용어 | 정의 |
|------|------|
| **Clean Room** | 소스코드에 접근하지 않고 외부 관찰만으로 내부 구조를 역추정하는 방법론 |
| **Ground Truth** | 소스코드에서 직접 추출한 실제 파라미터 값 |
| **Pattern Card** | 소스코드 참조 없이 작성된 설계 힌트 카드 |
| **L1 (Design Intent)** | 정성적 설계 의도만 기술한 패턴 카드 |
| **L2 (Structural Hint)** | 대략적 수치 범위를 포함한 패턴 카드 |
| **Observation Ceiling** | 관찰만으로 달성 가능한 이론적 정확도 상한 |
| **Domain Weighting** | 합의 시 해당 도메인 전문가 데이터에 가중치 부여 |
| **Cross-Validation** | 독립 관찰 결과를 상호 비교하여 오류 검출 |

## 부록 B: 기준선 데이터

```python
BASELINES = {
    "A":    {"average": 0.395},
    "B1":   {"average": 0.777},
    "B2":   {"average": 0.978},
    "C":    {"average": 0.365, "tapshift": 0.334, "magicsort": 0.347, "carmatch": 0.413},
    "C10":  {"average": 0.850, "tapshift": 0.844, "magicsort": 0.859, "carmatch": 0.847},
    "C10+": {"average": 0.895, "tapshift": 0.900, "magicsort": 0.887, "carmatch": 0.897},
    "D1":   {"average": 0.592},
    "D1_10":{"average": 0.825},
    "D2":   {"average": 0.963},
    "D10":  {"average": 0.985},
}
```

## 부록 C: Score Distribution Heatmap

```
조건별 점수 분포 (96 파라미터 기준)

        1.0    0.7    0.4    0.1    0.0
  A   : ████   ███    ████   ███    ████   (39.5%)
  B1  : ████████████  ████   ██     █      (77.7%)
  B2  : ██████████████████████  █    ·      (97.8%)
  C   : ████   ██     ███    ██     ████████  (36.5%)
  C10 : ██████████████  ███   ██     ██      (85.0%)
  C10+: ███████████████████    ·      ██     (89.5%)
  D10 : ████████████████████████████  ·      (98.5%)
```

---

*본 문서는 CleanRoomTest 프로젝트의 모든 실험 데이터, 스크립트, 채점 결과를 기반으로 작성되었습니다.*
*재현 시 `run_c10_plus.py` 스크립트와 본 문서를 함께 참조하세요.*
