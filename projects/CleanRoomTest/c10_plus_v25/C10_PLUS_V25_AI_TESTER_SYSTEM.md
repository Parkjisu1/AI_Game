# C10+ v2.5 AI Tester System — Complete Specification

> **Version**: 2.5
> **Last Updated**: 2026-02-24
> **Purpose**: 어떤 LLM이든 이 문서만으로 시스템을 이해하고 운영할 수 있는 완전한 사양서

---

## 1. 시스템 개요

### 1.1 C10+ v2.5란?

**C10+ v2.5**는 모바일 게임의 내부 파라미터(밸런스 시트)를 **소스코드 접근 없이** AI 관찰만으로 추정하는 자동화 파이프라인입니다.

- **C** = Claude (AI 모델)
- **10** = 10명의 전문 AI 테스터 (각각 다른 역할)
- **+** = 도메인 가중 합의 (domain-weighted consensus)
- **v2.5** = OCR + Wiki + APK 에셋 보강 버전

### 1.2 핵심 아이디어

소스코드가 없는 게임에서 32개 핵심 파라미터(HP 공식, 가챠 확률, 강화 비용 등)를 추정합니다.

```
1명 자유 관찰 (C)       → 36.5% 정확도
10명 자유 관찰 (C10)    → 85.0% 정확도
10명 전문 관찰 (C10+)   → 89.5% 정확도 (퍼즐)
10명 전문 + OCR/Wiki/APK (C10+ v2.5) → 목표 60%+ (RPG/SLG/Idle)
```

### 1.3 해결하는 문제

| 문제 | 원인 | 해결 |
|------|------|------|
| 하드코딩 좌표 스크립트 실패 | Unity uiautomator 미지원 | Vision 기반 AI 네비게이션 |
| 동적 UI 처리 불가 | 팝업/튜토리얼/순차 언락 | 팝업 핸들러 + 적응형 탐색 |
| 상태 무시 기계적 재생 | Dumb Replay (player.py) | 화면 인식 → 판단 → 실행 루프 |

---

## 2. 파이프라인 아키텍처 (6-Phase)

```
[유저 10분 플레이]
    ↓ recorder.py (터치 녹화 + 스크린샷)
recordings/{game}/recording.json + frames/*.png
    ↓ classifier.py (화면 분류)
classifications.json
    ↓ nav_graph.py (네비게이션 그래프 빌드)
nav_graph.json
    ↓ smart_capture.py (10개 AI 미션 실행)
output/{game}/sessions/session_01~10/*.png

[Phase 1]   CAPTURE — 10개 미션별 스크린샷 수집
[Phase 1.5] OCR — 숫자 영역 자동 추출 (M2)
[Phase 2]   VISION — Claude Sonnet 세션별 분석
[Phase 2.5] WIKI — 커뮤니티 데이터 교차검증 (M3)
[Phase 3]   AGGREGATE — 도메인 가중 합의
[Phase 4]   SPEC — 32개 파라미터 추정 (YAML)
[Phase 5]   SCORING — Ground Truth 비교 채점
[Phase 6]   REPORT — 최종 보고서 생성
```

### 2.1 Phase 1: CAPTURE (스크린샷 수집)

3가지 캡처 모드:

| 모드 | 플래그 | 설명 |
|------|--------|------|
| **Auto** | (기본) | 장르별 하드코딩 좌표 스크립트 실행 |
| **Replay** | `--replay` | 유저 녹화 터치 이벤트 재생 |
| **Smart** | `--smart` | AI 네비게이션 (Vision + 그래프) — **권장** |

Smart 모드는 유저가 10분 플레이한 녹화 데이터를 기반으로 네비게이션 그래프를 구축하고, AI가 자율적으로 게임 화면을 탐색합니다.

### 2.2 Phase 1.5: OCR 전처리 (M2)

장르 모듈에서 정의한 OCR 영역(좌표 크롭)에서 숫자를 자동 추출합니다.

```python
ocr_regions = {
    "player_level": (20, 20, 100, 30),   # (x, y, width, height)
    "hp_bar": (50, 60, 200, 20),
    "gold": (600, 20, 150, 30),
    ...
}
```

### 2.3 Phase 2: VISION 분석

각 세션의 스크린샷을 Claude Sonnet에 전송하여, 세션별 전문가 프롬프트로 분석합니다.

- 10개 세션 × 각 5~8장 스크린샷 = 총 50~80장
- 세션별 전용 분석 프롬프트 (아래 Section 4 참조)
- OCR 데이터가 있으면 프롬프트에 주입하여 정밀도 향상

### 2.4 Phase 2.5: WIKI 교차검증 (M3)

커뮤니티 위키/가이드 데이터를 검색하여 관찰 결과를 교차검증합니다.

```python
wiki_keywords = [
    "Ash N Veil guide",
    "Ash N Veil gacha rates",
    "Ash N Veil tier list",
    ...
]
```

### 2.5 Phase 3: AGGREGATE (도메인 가중 합의)

10명 전문가의 관찰을 **도메인 가중치**를 적용하여 통합합니다.

```
도메인 전문성 우선:
  gameplay → 전문가 1, 2
  numeric → 전문가 3, 4
  visual → 전문가 5
  equipment → 전문가 6
  economy → 전문가 7
  gacha → 전문가 8
  combat → 전문가 9
  cross_validation → 전문가 10
```

통합 규칙:
1. 도메인 전문가의 관찰이 비전문가보다 우선
2. 전문가 1과 2의 독립 플레이스루 비교
3. 전문가 10의 교차검증으로 신뢰도 상향
4. 구체적 수치 > 대략적 추정
5. OCR 데이터 > Vision 분석
6. APK 에셋 데이터 = 최고 신뢰도
7. 커뮤니티 데이터는 관찰 일치 시 보조 확인

### 2.6 Phase 4: SPEC 생성

합의 문서에서 32개 파라미터를 YAML로 추정합니다.

```yaml
game: "Ash N Veil: Fast Idle Action"
genre: "Idle RPG"
condition: "C10_plus_v25"
parameters:
  - id: ANV01
    name: max_chapter
    value: 20
    confidence: high
    source: "관찰"
```

### 2.7 Phase 5: SCORING

Ground Truth(실제 게임 데이터)와 비교하여 채점합니다.

| 판정 | 점수 | 기준 |
|------|:----:|------|
| Exact | 1.0 | 정확 일치 |
| Close | 0.7 | 20% 이내 차이 |
| Partial | 0.4 | 방향 맞으나 수치 오차 |
| Wrong | 0.1 | 완전히 다른 값 |
| Missing | 0.0 | null 또는 미응답 |

### 2.8 Phase 6: REPORT

최종 보고서 MD 파일 생성 (정확도, 세션 정보, 사용된 기능 등).

---

## 3. Smart Player 서브시스템

Smart Player는 Phase 1의 핵심으로, AI가 자율적으로 게임을 탐색합니다.

### 3.1 전체 구조

```
smart_player/
├── __init__.py           # 패키지 export
├── classifier.py         # 2-Tier 화면 분류 (해시 캐시 + Claude Vision)
├── nav_graph.py          # 네비게이션 그래프 (화면 전환 맵)
├── navigator.py          # 핵심 탐색 엔진 (인식→판단→실행→검증)
├── popup_handler.py      # 팝업/튜토리얼 감지 + 닫기
├── mission_router.py     # 미션 → 목표 화면 매핑 + 경로 계획
└── smart_capture.py      # 10개 미션 오케스트레이터
```

### 3.2 ScreenClassifier (classifier.py)

**2-Tier 분류 시스템:**

| Tier | 방식 | 속도 | 정확도 | API 호출 |
|------|------|------|--------|----------|
| **Tier 1** | 퍼셉추얼 해시 캐시 | ~10ms | 높음 (동일 화면) | 없음 |
| **Tier 2** | Claude Vision (haiku) | ~15-20s | 매우 높음 | 1회 |

```python
@dataclass
class ScreenClassification:
    screen_type: str          # e.g. "menu_summon"
    confidence: float         # 0.0 ~ 1.0
    sub_info: Dict[str, Any]  # e.g. {"tab": "hero", "page": 1}
    screenshot_path: Path
```

**퍼셉추얼 해시 알고리즘:**
1. 이미지를 8x8 그레이스케일로 리사이즈
2. 평균 밝기 기준으로 64-bit 해시 생성
3. 해밍 거리 ≤ 10이면 캐시 히트 (같은 화면으로 판정)

**Claude Vision 분류 프롬프트:**
```
모바일 게임 스크린샷을 분류하세요.
화면 타입 목록: {screen_types}

팝업 판별 규칙:
- 팝업 = 메인 화면 위에 별도 창/패널이 떠서 뒤의 게임 화면을 가리는 오버레이
- 팝업이 아닌 것: 하단 채팅 로그, 알림 텍스트 바, 인게임 HUD, 스킬바, 메뉴바
- 화면 전체를 차지하는 메뉴/상점/캐릭터 화면은 해당 화면 타입으로 분류

출력 (JSON만): {"screen_type": "...", "confidence": 0.X, "sub_info": {}}
```

### 3.3 NavigationGraph (nav_graph.py)

화면 전환 관계를 방향 그래프로 표현합니다.

```python
@dataclass
class NavNode:
    screen_type: str              # "lobby", "menu_shop", etc.
    visit_count: int              # 녹화 중 방문 횟수
    sample_screenshots: List[str] # 예시 스크린샷 (최대 3장)

@dataclass
class NavAction:
    action_type: str    # "tap" | "swipe" | "back" | "vision"
    x: int; y: int      # 탭/스와이프 시작 좌표
    x2: int; y2: int    # 스와이프 끝 좌표
    description: str    # 설명

@dataclass
class NavEdge:
    source: str          # 출발 화면
    target: str          # 도착 화면
    action: NavAction    # 실행할 액션
    success_count: int   # 성공 횟수 (높을수록 신뢰)
```

**그래프 빌드 모드:**

| 모드 | 조건 | 액션 타입 |
|------|------|-----------|
| **Event-based** | recording.json에 터치 이벤트 있음 | tap/swipe (정확한 좌표) |
| **Frame-sequence** | 터치 이벤트 없음 (BlueStacks 등) | vision (AI가 좌표 결정) |

**Frame-sequence 모드 특이사항:**
- 연속 프레임 간 화면 타입이 바뀌면 Edge 생성
- 자동으로 **역방향 Edge** 추가 (대부분의 화면은 뒤로 가기가 가능)
- Edge의 `action_type="vision"` → Navigator가 Claude Vision으로 탭 좌표를 결정

**BFS 최단 경로:** `find_path(source, target)` — 노드 간 최단 Edge 시퀀스 반환

### 3.4 SmartNavigator (navigator.py)

핵심 탐색 엔진. **인식 → 판단 → 실행 → 검증** 루프를 실행합니다.

**설정 상수:**
```python
MAX_RETRIES = 3       # 경로 재시도 횟수
MAX_STEPS = 80        # 미션당 최대 스텝 (~20s/step = ~27분)
STUCK_THRESHOLD = 5   # 연속 실패 시 포기
```

**navigate_to(target) 알고리즘:**
```
1. 현재 화면 == target? → 성공
2. 화면 동등성 확인 (battle ≈ lobby)? → 성공
3. 최대 3회 반복:
   a. BFS로 경로 탐색
   b. 경로 없으면 → 탐험 모드 (_explore_for_path)
   c. 경로 실행 (_execute_path)
      - 각 Edge마다: 액션 실행 → 스크린샷 → 분류 → 검증
      - 팝업이면 → dismiss
      - 화면 안 바뀌면 → 폴백 닫기 버튼 시도
      - 예상 화면 아니면 → 재경로 계산
4. 전부 실패 → 허브 복구 (_fallback_to_hub)
   - lobby, menu_inventory 등 연결 많은 노드로 이동 시도
   - Vision으로 home/back 버튼 탐지
```

**Vision Navigation 프롬프트 (Edge action_type="vision" 시):**
```
I'm playing a mobile game. Current screen type: {current}.
I need to navigate to: {target}.

IMPORTANT: Device resolution is {w}x{h} pixels.
Return coordinates in this EXACT pixel range.

CRITICAL: If you see a quit/exit confirmation dialog,
tap 'No'/'취소'. NEVER tap 'Yes' on exit dialogs.

Return JSON: {"action": "tap", "x": <pixel_x>, "y": <pixel_y>, "reason": "..."}
```

**화면 동등성 (Screen Equivalence):**

특정 장르에서 물리적으로 같은 화면이지만 다르게 분류되는 경우 처리:

```python
# Idle RPG 예시
equivalences = {
    "battle": "lobby",   # 자동전투 = 로비/필드 화면
    "loading": "lobby",  # 로딩은 자동으로 로비로 전환
}
```

**폴백 닫기 버튼 좌표 (1080x1920 기준):**
```python
FALLBACK_CLOSE_POSITIONS = [
    (540, 1880),   # 하단 중앙 X
    (540, 1850),   # 하단 중앙 약간 위
    (420, 1880),   # 하단 중앙-왼쪽
    (1020, 80),    # 우상단 X
    (60, 80),      # 좌상단 뒤로
    (540, 100),    # 상단 중앙
]
```

### 3.5 PopupHandler (popup_handler.py)

팝업/튜토리얼 오버레이를 감지하고 닫습니다.

**팝업 판별:** `screen_type.startswith("popup_")`

**닫기 전략:**
1. 캐시된 좌표 확인 (이전에 같은 타입 팝업을 닫은 좌표)
2. Claude Vision으로 닫기 버튼 탐지
3. 폴백: 일반적인 닫기 버튼 위치 순차 탭

**튜토리얼 처리:** Claude Vision으로 하이라이트/손가락 아이콘 위치 탐지 → 해당 좌표 탭

**주의:** `press_back()` 미사용 — 많은 게임에서 뒤로 가기가 "게임 종료" 팝업을 트리거

### 3.6 MissionRouter (mission_router.py)

10개 미션 각각의 목표 화면과 필요 스크린샷 수를 관리합니다.

**전략별 타겟 선택:**

| 전략 | 로직 |
|------|------|
| `sequential` | 선언 순서대로 방문 |
| `breadth_first` | 가장 적게 캡처된 타겟 우선 |
| `depth_first` | 현재 화면이 타겟이면 머무르기 |
| `data_focused` | 부족분 가장 큰 타겟 우선 |
| `economy_track` | data_focused와 동일 |
| `combat_focused` | data_focused와 동일 |
| `visual_sweep` | breadth_first와 동일 |

**미션 완료 조건 (OR):**
1. 모든 `required_screenshots` 충족
2. `max_time_minutes` 초과
3. 5회 연속 stuck

**자동 필터링:** 네비게이션 그래프에 없는 목표 화면은 자동 제거

### 3.7 SmartCapture (smart_capture.py)

10개 미션의 실행 오케스트레이터.

**미션당 실행 흐름:**
```
1. 게임 실행 확인 (미실행 시 launch)
2. SmartNavigator 초기화
3. 초기 화면 분류 + 팝업 최대 5회 닫기
4. MissionRouter.start_mission() → 진행 추적 시작
5. 방문 순서 계획 (최근접 이웃 휴리스틱)
6. While not complete:
   a. 다음 타겟 결정
   b. 네비게이션 (동등성 체크 포함)
   c. 스크린샷 캡처
   d. 진행률 기록
7. 결과 저장 → 다음 미션
```

**스킵 로직:** 이미 3장 이상 스크린샷이 있는 세션은 건너뜀

---

## 4. 10명 AI 테스터 역할 (Idle RPG)

### 4.1 역할 요약

| # | 역할 | 도메인 | 유형 | 전략 |
|---|------|--------|------|------|
| 1 | Full Playthrough A | gameplay | Core | sequential |
| 2 | Full Playthrough B (UI Mapping) | gameplay | Core | breadth_first |
| 3 | Numeric Early (Lv.1~15) | numeric | Flex | data_focused |
| 4 | Numeric Late (Lv.30+) | numeric | Flex | data_focused |
| 5 | Visual + Multi-Resolution | visual | Core | visual_sweep |
| 6 | Equipment & Enhancement | equipment | Flex | depth_first |
| 7 | Economy & Idle Rewards | economy | Flex | economy_track |
| 8 | Gacha & Pet System | gacha | Flex | depth_first |
| 9 | Skills & Combat Algorithm | combat | Flex | combat_focused |
| 10 | Cross-Validation | cross_validation | Core | breadth_first |

- **Core** (4명): 장르 무관 공통 역할 (1, 2, 5, 10)
- **Flex** (6명): 장르 특화 역할 (3, 4, 6, 7, 8, 9)

### 4.2 미션 타겟 & 필요 스크린샷

#### Mission 1: Full Playthrough A
```
타겟: lobby, battle, menu_character, menu_inventory
필요: lobby×1, battle×2, menu_character×1, menu_inventory×1
전략: sequential
시간: 5분
```

#### Mission 2: Full Playthrough B (UI Mapping)
```
타겟: lobby, menu_character, menu_inventory, menu_shop, skill_detail,
      quest_list, equipment_enhance, settings
필요: 각 1장씩
전략: breadth_first
시간: 5분
```

#### Mission 3: Numeric Early (Lv.1~15)
```
타겟: menu_character, equipment_detail, skill_detail, menu_shop
필요: menu_character×2, equipment_detail×1, skill_detail×1, menu_shop×1
전략: data_focused
시간: 5분
```

#### Mission 4: Numeric Late (Lv.30+)
```
타겟: menu_character, equipment_enhance, battle, equipment_detail
필요: menu_character×2, equipment_enhance×1, battle×1, equipment_detail×1
전략: data_focused
시간: 5분
```

#### Mission 5: Visual + Multi-Resolution
```
타겟: lobby, battle, menu_character
필요: lobby×2, battle×2, menu_character×2
전략: visual_sweep
시간: 5분
```

#### Mission 6: Equipment & Enhancement
```
타겟: equipment_detail, equipment_enhance
필요: equipment_detail×3, equipment_enhance×3
전략: depth_first
시간: 5분
```

#### Mission 7: Economy & Idle Rewards
```
타겟: lobby, menu_shop, quest_list, menu_inventory
필요: lobby×1, menu_shop×2, quest_list×1, menu_inventory×1
전략: economy_track
시간: 5분
```

#### Mission 8: Gacha & Pet System
```
타겟: menu_shop, menu_inventory, settings
필요: menu_shop×2, menu_inventory×1, settings×1
전략: depth_first
시간: 5분
```

#### Mission 9: Skills & Combat Algorithm
```
타겟: skill_detail, battle, menu_character
필요: skill_detail×2, battle×4, menu_character×1
전략: combat_focused
시간: 5분
```

#### Mission 10: Cross-Validation
```
타겟: lobby, menu_character, menu_inventory, menu_shop,
      equipment_detail, skill_detail
필요: 각 1장씩
전략: breadth_first
시간: 5분
```

### 4.3 세션별 Vision 분석 프롬프트 (Phase 2)

각 세션의 스크린샷을 분석할 때 사용하는 전문가 프롬프트입니다.

---

#### 전문가 1: 챕터 진행 플레이스루

```
{game_name} - 전문가 1: 챕터 진행 플레이스루

당신은 Idle RPG 구조 분석 전문가입니다. 스크린샷은 게임 시작부터 순서대로 진행한 기록입니다.

분석 항목:
1. 스테이지/챕터 구조: 총 몇 챕터, 챕터당 몇 스테이지?
2. 보스전 구조: 몇 스테이지마다 보스? 보스 특수 메커니즘?
3. 자동전투 해금 시점: 어느 레벨/스테이지에서 자동전투 가능?
4. 난이도 모드: 노말/하드/헬 등 난이도 분기?
5. 전투 기본 흐름: 웨이브 수, 몬스터 출현 패턴
6. 클리어/실패 조건, 별점 시스템 유무
7. 튜토리얼 구성: 몇 단계? 어떤 시스템을 가르치나?

규칙: 스테이지 번호, 몬스터 수, 보스 HP 등 모든 숫자를 테이블로 정리.
```

---

#### 전문가 2: UI/메뉴 전수 매핑

```
{game_name} - 전문가 2: UI/메뉴 전수 매핑

당신은 모바일 게임 UI 분석 전문가입니다. 모든 메뉴와 화면을 매핑하세요.

필수 매핑:
1. 하단 메뉴바: 각 탭 이름과 기능 (캐릭터/스킬/필드/소환/상점 등)
2. 각 탭의 서브메뉴: 모든 하위 화면 목록
3. 설정 화면: 그래픽/사운드/계정/알림 등 모든 옵션
4. 팝업 목록: 모든 팝업 종류와 출현 조건
5. 알림 아이콘: 빨간 점(dot)이 표시되는 조건
6. 메인 HUD: 상단 표시 정보 (레벨, 닉네임, 재화, 스테이지)
7. 버튼 레이아웃: 각 화면의 주요 버튼 위치와 기능

출력: 화면별 트리 구조로 정리. 스크린샷 번호 참조.
```

---

#### 전문가 3: 초반 수치 수집 (Lv.1~15)

```
{game_name} - 전문가 3: 초반 수치 수집 (Lv.1~15)

당신은 게임 밸런스 수치 분석 전문가입니다. 초반 구간의 정확한 수치를 수집하세요.

필수 수집:
1. 캐릭터 기본 스탯 (Lv.1): HP, ATK, DEF, SPD 각각의 정확한 숫자
2. 레벨업 증가량: Lv.1→2, 2→3, ... 15까지 각 레벨의 스탯 변화
3. 레벨업 비용: 각 레벨업에 필요한 골드/경험치
4. 장비 초기값: 첫 장비의 스탯, 강화 1회 비용
5. 스킬 초기값: 첫 스킬의 데미지/쿨다운
6. 초기 재화량: 시작 시 골드, 젬, 기타 재화

출력 형식:
| Lv | HP | ATK | DEF | EXP필요 | 골드필요 |
|----|-----|-----|-----|---------|---------|
| 1  | ?? | ??  | ??  | ??      | ??      |
| 2  | ?? | ??  | ??  | ??      | ??      |
...
반드시 정확한 숫자만 기록. 모르면 "관찰불가" 표시.
```

---

#### 전문가 4: 후반 스케일링 (Lv.30+)

```
{game_name} - 전문가 4: 후반 스케일링 (Lv.30+)

당신은 게임 성장 곡선 분석 전문가입니다. 후반 구간의 스케일링 패턴을 분석하세요.

필수 분석:
1. Lv.30+ 스탯: HP, ATK, DEF의 후반 수치 (5레벨 간격으로)
2. 성장 공식 추론: 선형? 지수? 로그? 구간별 다른 공식?
3. 강화 비용 스케일링: 초반 vs 후반 비용 비율
4. 경험치 곡선: 레벨업에 필요한 EXP가 어떻게 증가하는지
5. 몬스터 스탯 스케일링: 스테이지별 몬스터 HP/ATK 변화
6. 골드 획득 스케일링: 후반 스테이지의 골드 보상량

회귀분석 시도:
- 데이터 포인트 3개 이상이면 공식 역산 시도
- 예: HP = a + b×Lv (선형), HP = a × b^Lv (지수), HP = a × Lv^b (거듭제곱)
- R² 값을 추정하여 모델 적합도 표시

출력: 레벨별 데이터 테이블 + 추정 공식.
```

---

#### 전문가 5: 시각 측정 + 다해상도 비교

```
{game_name} - 전문가 5: 시각 측정 + 다해상도 비교

당신은 UI/UX 정밀 측정 전문가입니다.

기본 측정 (현재 해상도):
1. 화면 해상도: 전체 화면 크기
2. HUD 영역: 상단바 높이, 하단 메뉴바 높이 (px)
3. 전투 영역: 사용 가능한 게임플레이 영역 크기
4. 버튼 크기: 주요 버튼의 가로×세로 (px)
5. 폰트 크기: HP/ATK 등 주요 텍스트 크기 추정
6. 캐릭터 크기: 플레이어/몬스터 스프라이트 크기
7. UI 여백: 요소 간 간격

다해상도 비교 (v2 추가):
- 동일 화면의 720p/1080p/1440p 캡처가 있으면:
  - 각 해상도에서 동일 UI 요소의 px 크기 비교
  - 스케일링 비율 계산 → 기준 해상도(reference resolution) 역산

출력: 모든 측정값을 px 단위로. 비율은 소수점 2자리.
```

---

#### 전문가 6: 장비/강화 전수 조사

```
{game_name} - 전문가 6: 장비/강화 전수 조사

당신은 RPG 장비 시스템 분석 전문가입니다. 장비 관련 모든 것을 조사하세요.

필수 조사:
1. 장비 슬롯: 총 몇 개? 각 슬롯 이름
2. 장비 등급: 등급 체계, 각 등급 색상
3. 장비 스탯: 등급별 기본 스탯 범위
4. 강화 시스템:
   - 강화 최대 레벨
   - 각 강화 레벨의 비용 (골드/재료)
   - 강화 성공률 (있다면)
   - 강화 실패 시 패널티
5. 세트 효과: 세트 장비 구성과 세트 보너스
6. 장비 획득 경로: 가챠/드롭/제작/상점 등
7. 분해/매각: 불필요 장비 처리 시 획득 재화

출력: 등급별, 슬롯별 데이터 테이블. 강화 비용 테이블.
```

---

#### 전문가 7: 경제/방치 보상 전담

```
{game_name} - 전문가 7: 경제/방치 보상 전담

당신은 모바일 게임 경제 분석 전문가입니다.

필수 추적:
1. 재화 종류: 모든 재화 이름, 아이콘, 용도
2. 초기 재화: 게임 시작 시 보유량
3. 주요 수입원:
   - 스테이지 클리어 보상 (골드/EXP/장비)
   - 방치(Idle) 보상: 분당/시간당 획득량, 최대 축적 시간
   - 출석 보상: 7일/30일 패턴
   - 일일 퀘스트: 보상 종류와 양
   - 업적 보상
4. 주요 지출처:
   - 레벨업/강화/스킬/가챠 비용
5. 상점: 모든 상품과 가격표
6. VIP/월정액: 혜택 상세
7. 광고: 보상형 광고 빈도와 보상량

출력: 수입/지출 테이블. 방치 보상 계산식.
```

---

#### 전문가 8: 가챠/펫 시스템 전수 조사

```
{game_name} - 전문가 8: 가챠/펫 시스템 전수 조사

당신은 가챠 시스템 분석 전문가입니다.

필수 조사:
1. 소환 종류: 캐릭터/장비/펫 각 카테고리
2. 소환 비용: 1회/10연차 (젬/티켓)
3. 등급 확률: SSR/SR/R/N 각 등급의 확률 (%)
4. 천장(Pity) 시스템: 몇 회 소환 시 확정?
5. 펫 시스템: 등급/종류, 스킬/효과, 성장 방식
6. 중복 처리: 이미 보유한 캐릭터 중복 소환 시 보상
7. 무료 소환: 일일 무료 횟수, 쿨다운

출력: 가챠 확률표, 비용표, 천장 시스템 정리.
```

---

#### 전문가 9: 스킬/전투 알고리즘 분석

```
{game_name} - 전문가 9: 스킬/전투 알고리즘 분석

당신은 전투 시스템 분석 전문가입니다.

필수 분석:
1. 스킬 목록: 모든 액티브/패시브 스킬, 각 효과
2. 쿨다운: 각 스킬의 쿨다운 시간 (초)
3. 데미지 공식 추론:
   - 기본 공격 = ATK × ? - DEF × ?
   - 크리티컬: 확률, 배율
   - 속성 상성: 유리/불리 배율
4. 공격 속도: 자동공격 주기 (초)
5. 버프/디버프: 종류, 지속시간, 중첩 여부
6. 전투 AI:
   - 자동전투 시 스킬 사용 패턴
   - 타겟 선택 로직
7. 전투 종료 조건

출력: 스킬 테이블, 데미지 공식 추정, 전투 AI 패턴.
```

---

#### 전문가 10: 교차검증 (전 영역)

```
{game_name} - 전문가 10: 교차검증 (전 영역)

당신은 데이터 검증 전문가입니다. 다른 9명의 관찰에서 약점이 될 수 있는 항목을 재확인하세요.

집중 확인:
1. 성장 공식: 전문가 3(초반)과 4(후반) 데이터 일관성
2. 가챠 확률: 공시된 확률 vs 실제 관찰
3. 방치 보상: 표시된 시간당 보상 vs 실제 축적량
4. 장비 강화: 비용 테이블의 규칙성
5. 스킬 쿨다운: 전투에서 측정 가능한 쿨다운
6. UI 수치: 표시된 HP/ATK와 전투 관찰 수치 일치 여부

규칙: 불일치 발견 시 어떤 값이 맞는지 판단 근거 제시.
```

---

## 5. 화면 타입 정의 (Idle RPG)

### 5.1 공통 화면 타입 (GenreBase, 11종)

| 타입 | 설명 |
|------|------|
| `loading` | 로딩/스플래시 화면 |
| `lobby` | 메인 로비/홈 화면 |
| `battle` | 활성 게임플레이/전투 화면 |
| `battle_result` | 승리/패배 결과 화면 |
| `settings` | 설정/옵션 메뉴 |
| `popup_reward` | 보상 팝업 오버레이 |
| `popup_ad` | 광고 팝업 |
| `popup_tutorial` | 튜토리얼 하이라이트 오버레이 |
| `popup_announcement` | 공지/이벤트 팝업 |
| `popup_unknown` | 미확인 팝업 오버레이 |
| `unknown` | 판별 불가 |

### 5.2 Idle RPG 추가 화면 타입 (13종)

| 타입 | 설명 |
|------|------|
| `stage_select` | 스테이지/챕터 선택 화면 |
| `menu_character` | 캐릭터 스탯/정보 화면 |
| `menu_skill` | 스킬 목록/업그레이드 화면 |
| `menu_inventory` | 인벤토리/가방 화면 |
| `menu_summon` | 가챠/소환 메인 화면 |
| `menu_shop` | 인게임 상점 화면 |
| `equipment_detail` | 장비 상세 스탯 뷰 |
| `equipment_enhance` | 장비 강화 화면 |
| `skill_detail` | 개별 스킬 상세 팝업 |
| `summon_rates` | 가챠 확률표 |
| `summon_result` | 소환 결과 표시 |
| `quest_list` | 퀘스트/미션 목록 화면 |
| `black_screen` | 전환 검은 화면 |

### 5.3 화면 동등성 (Idle RPG)

```python
{
    "battle": "lobby",   # 자동전투 = 로비/필드 화면
    "loading": "lobby",  # 로딩은 자동 전환됨
}
```

---

## 6. 32개 파라미터 정의 (Idle RPG — Ash N Veil)

```
ANV01: max_chapter (progression) - 최대 챕터 수
ANV02: stages_per_chapter (progression) - 챕터당 스테이지 수
ANV03: boss_frequency (progression) - 보스 등장 빈도 (몇 스테이지마다)
ANV04: auto_battle_unlock (progression) - 자동전투 해금 조건
ANV05: difficulty_modes (progression) - 난이도 모드 수
ANV06: base_hp_lv1 (growth) - Lv.1 기본 HP
ANV07: base_atk_lv1 (growth) - Lv.1 기본 ATK
ANV08: hp_growth_formula (growth) - HP 성장 공식 (선형/지수/구간)
ANV09: atk_growth_formula (growth) - ATK 성장 공식
ANV10: exp_curve_formula (growth) - EXP 곡선 공식
ANV11: gear_slot_count (equipment) - 장비 슬롯 수
ANV12: gear_grade_count (equipment) - 장비 등급 수
ANV13: enhance_max_level (equipment) - 강화 최대 레벨
ANV14: enhance_cost_formula (equipment) - 강화 비용 공식
ANV15: active_skill_count (combat) - 액티브 스킬 수
ANV16: skill_cooldown_range (combat) - 스킬 쿨다운 범위 (초)
ANV17: auto_attack_speed (combat) - 자동공격 주기 (초)
ANV18: damage_formula (combat) - 데미지 공식 (ATK/DEF 관계)
ANV19: critical_rate (combat) - 크리티컬 확률 (%)
ANV20: critical_multiplier (combat) - 크리티컬 배율
ANV21: gacha_cost_1x (gacha) - 1회 소환 비용
ANV22: gacha_cost_10x (gacha) - 10연차 소환 비용
ANV23: gacha_ssr_rate (gacha) - SSR 확률 (%)
ANV24: gacha_pity_count (gacha) - 천장 횟수
ANV25: currency_types (economy) - 재화 종류 수
ANV26: idle_gold_per_min (economy) - 방치 골드/분
ANV27: idle_max_accumulation (economy) - 방치 최대 축적 시간
ANV28: attendance_days (economy) - 출석 보상 주기 (일)
ANV29: daily_quest_count (economy) - 일일 퀘스트 수
ANV30: pet_system_exists (system) - 펫 시스템 유무
ANV31: ui_reference_resolution (visual) - UI 기준 해상도
ANV32: state_count (architecture) - 게임 상태 수 (메인/전투/로비 등)
```

### 파라미터 카테고리 분포

| 카테고리 | 파라미터 수 | IDs |
|----------|:-----------:|-----|
| progression | 5 | ANV01~05 |
| growth | 5 | ANV06~10 |
| equipment | 4 | ANV11~14 |
| combat | 6 | ANV15~20 |
| gacha | 4 | ANV21~24 |
| economy | 5 | ANV25~29 |
| system | 1 | ANV30 |
| visual | 1 | ANV31 |
| architecture | 1 | ANV32 |

---

## 7. 도메인 가중치 & 합의 규칙

### 7.1 도메인 → 전문가 매핑

```python
{
    "gameplay":         [1, 2],   # 플레이스루
    "numeric":          [3, 4],   # 수치 전문
    "visual":           [5],      # 시각 측정
    "equipment":        [6],      # 장비 전담
    "economy":          [7],      # 경제 전담
    "gacha":            [8],      # 가챠 전담
    "combat":           [9],      # 전투 전담
    "cross_validation": [10],     # 교차검증
}
```

### 7.2 합의 문서 섹션 (Idle RPG)

1. 게임 정체성 (장르, 세계관, 아트)
2. UI 구성 (메뉴 구조, 하단바, 팝업)
3. 전투 메커니즘 (자동/수동, 스킬, 속성)
4. 캐릭터 성장 (레벨업, 스탯, 각성)
5. 장비 시스템 (슬롯, 등급, 강화, 세트)
6. 가챠/소환 시스템 (비용, 확률, 천장)
7. 펫/동료 시스템
8. 경제/재화 (골드, 젬, 방치보상, 출석)
9. 스테이지/콘텐츠 진행 (챕터, 보스, 던전)
10. 스킬 시스템 (쿨다운, 버프, 시너지)
11. 시각 측정 (UI 크기, 해상도, 레이아웃)
12. 초반 수치 vs 후반 수치 (성장 곡선 회귀분석)

### 7.3 Idle RPG 특화 합의 규칙

- 수치 전문가 3(초반)과 4(후반)의 데이터를 병합하여 성장 곡선 회귀분석 실시
- 가챠 확률은 게임 내 공시 데이터를 최우선 채택
- 방치 보상은 전문가 7의 시간당 수치를 정밀 확인
- 데미지 공식은 전문가 9의 전투 관찰에서 역산 (ATK, DEF, 크리, 속성 반영)
- 장비 강화 비용은 전문가 6의 전수 조사 데이터 채택

---

## 8. 네비게이션 그래프 예시 (Ash N Veil)

### 8.1 노드 (11종)

```
lobby, menu_shop, battle, loading, menu_character,
menu_inventory, skill_detail, quest_list,
equipment_enhance, equipment_detail, settings
```

### 8.2 연결 관계

```
lobby ←→ menu_shop
lobby ←→ battle
lobby ←→ menu_character
lobby ←→ loading

battle ←→ loading

menu_character ←→ menu_inventory

menu_inventory ←→ skill_detail
menu_inventory ←→ quest_list
menu_inventory ←→ equipment_enhance
menu_inventory ←→ equipment_detail
menu_inventory ←→ menu_shop
menu_inventory ←→ settings
menu_inventory ←→ menu_character

quest_list ←→ equipment_enhance
```

### 8.3 허브 노드

| 노드 | 연결 Edge 수 | 역할 |
|------|:------------:|------|
| `menu_inventory` | 14 | 최대 허브 — 대부분의 서브화면 연결 |
| `lobby` | 8 | 메인 허브 — 게임 루트 |
| `menu_shop` | 4 | 보조 허브 |

---

## 9. 게임 설정 (GameConfig)

### 9.1 Ash N Veil

```python
GameConfig(
    key="ash_n_veil",
    name="Ash N Veil: Fast Idle Action",
    package="studio.gameberry.anv",
    prefix="ANV",
)
```

### 9.2 좌표 정의 (coords)

```python
# 공통
"center": (400, 640), "play": (400, 1000),
"back": (60, 60), "settings": (720, 60),
"popup_close": (400, 900), "popup_x": (650, 200),

# 하단 메뉴바
"menu_char": (80, 1230), "menu_skill": (200, 1230),
"menu_field": (400, 1230), "menu_summon": (560, 1230),
"menu_shop": (680, 1230),

# 전투 화면
"joystick_area": (150, 900),
"skill_1": (550, 950), "skill_2": (630, 870), "skill_3": (710, 950),
"auto_btn": (750, 800),

# 장비 화면
"gear_slot_1~3", "gear_enhance", "gear_tab_weapon/armor/acc"

# 소환 화면
"summon_1x", "summon_10x", "summon_tab_hero/gear/pet"
```

### 9.3 OCR 영역

```python
"player_level": (20, 20, 100, 30),
"hp_bar": (50, 60, 200, 20),
"gold": (600, 20, 150, 30),
"gem": (600, 50, 150, 30),
"atk_stat": (100, 400, 120, 25),
"hp_stat": (100, 430, 120, 25),
"stage_number": (300, 50, 200, 30),
```

---

## 10. CLI 사용법

```bash
# 녹화 (유저 10분 플레이)
python run.py ash_n_veil record

# 스마트 캡처 + 전체 파이프라인 (권장)
python run.py ash_n_veil --smart

# 기존 스크린샷으로 분석만
python run.py ash_n_veil --skip-capture

# 녹화 재생 + 분석
python run.py ash_n_veil --replay --replay-speed 1.5

# 기능 선택적 비활성화
python run.py ash_n_veil --smart --no-ocr --no-wiki

# 등록된 게임/장르 목록
python run.py --list

# APK 에셋 추출 포함
python run.py ash_n_veil --smart --apk /path/to/game.apk

# 모델 선택
python run.py ash_n_veil --smart --model opus
```

---

## 11. 출력 디렉토리 구조

```
output/{game_key}/
├── sessions/              # Phase 1 스크린샷
│   ├── session_01/        # Mission 1 스크린샷들
│   ├── session_02/        # Mission 2 스크린샷들
│   └── ...session_10/
├── ocr_data/              # Phase 1.5 OCR 추출 결과
│   └── ocr_results.json
├── observations/          # Phase 2 Vision 분석 텍스트
│   ├── session_01.txt
│   └── ...session_10.txt
├── wiki_data/             # Phase 2.5 커뮤니티 데이터
│   └── community_data.txt
├── asset_data/            # PRE APK 에셋 추출
│   └── extracted_assets.json
├── aggregated/            # Phase 3 합의 문서
│   └── consensus.txt
├── specs/                 # Phase 4 파라미터 추정
│   └── {game}_C10_plus_v25_spec.yaml
├── scoring/               # Phase 5 채점 결과
│   └── {game}_C10_plus_v25_score.yaml
├── ground_truth/          # 게임팀 제공 실제값
│   └── {game}_ground_truth.yaml
└── report/                # Phase 6 보고서
    ├── {game}_C10_plus_v25_report.md
    └── {game}_review_template.md
```

---

## 12. 새로운 장르/게임 추가 방법

### 12.1 장르 모듈 생성

```python
# genres/my_genre.py
from genres import GenreBase, GameConfig, Mission, MissionPlan, register_genre

class MyGenre(GenreBase):
    @property
    def genre_name(self) -> str:
        return "My Genre"

    @property
    def genre_key(self) -> str:
        return "my_genre"

    def get_games(self) -> Dict[str, GameConfig]: ...
    def get_missions(self) -> Dict[int, Mission]: ...
    def get_vision_prompt(self, session_id, game_name) -> str: ...
    def get_parameters(self, game_key) -> str: ...
    def get_domain_weights(self) -> Dict[str, List[int]]: ...
    def capture_session(self, ctx, session_id): ...

    # Smart Player 지원 (선택)
    def get_screen_types(self) -> Dict[str, str]: ...
    def get_mission_targets(self) -> Dict[int, MissionPlan]: ...
    def get_screen_equivalences(self) -> Dict[str, str]: ...

register_genre(MyGenre())
```

### 12.2 등록

```python
# genres/__init__.py > load_all_genres()
def load_all_genres():
    from genres import puzzle, idle_rpg, merge, my_genre  # 추가
```

### 12.3 필수 구현 메서드

| 메서드 | 설명 | 필수 |
|--------|------|:----:|
| `genre_name` | 사람이 읽는 장르명 | O |
| `genre_key` | 기계 키 | O |
| `get_games()` | GameConfig 딕셔너리 | O |
| `get_missions()` | 10개 Mission 정의 | O |
| `get_vision_prompt()` | 세션별 분석 프롬프트 | O |
| `get_parameters()` | 32개 파라미터 정의 | O |
| `get_domain_weights()` | 도메인 가중치 | O |
| `capture_session()` | 좌표 기반 캡처 스크립트 | O |
| `get_screen_types()` | 화면 타입 사전 | Smart용 |
| `get_mission_targets()` | 미션별 타겟/전략 | Smart용 |
| `get_screen_equivalences()` | 화면 동등성 맵 | Smart용 |

---

## 13. 기술 스택 & 의존성

| 구성요소 | 기술 |
|----------|------|
| AI 모델 (분류) | Claude Haiku (빠른 분류) |
| AI 모델 (분석) | Claude Sonnet (Vision 분석) |
| AI 모델 (합의/추정) | Claude Sonnet/Opus (텍스트) |
| 디바이스 제어 | ADB (Android Debug Bridge) |
| 에뮬레이터 | BlueStacks (HD-Adb.exe) |
| 이미지 처리 | PIL/Pillow (퍼셉추얼 해시) |
| OCR | pytesseract (선택) |
| 언어 | Python 3.13 |

### ADB 설정

```python
adb_path = "C:\\Program Files\\BlueStacks_nxt\\HD-Adb.exe"
device = "emulator-5554"
```

---

## 14. 알려진 제한사항 & 향후 개선

### 14.1 현재 제한사항

| 제한 | 원인 | 영향 |
|------|------|------|
| Claude Vision API 지연 | ~15-20s/호출 | 미션당 5-10분 소요 |
| Vision Nav 정확도 | 비정형 UI 버튼 인식 실패 | 일부 네비게이션 실패 |
| BlueStacks 터치 캡처 불가 | getevent 미지원 | Frame-sequence 모드 강제 |
| 해상도 의존성 | 좌표가 1080x1920 기준 | 다른 해상도에서 폴백 좌표 오작동 가능 |

### 14.2 향후 개선 방향

1. **배치 분류**: 여러 스크린샷을 한 번에 분류하여 API 호출 절감
2. **좌표 캐시**: 성공한 Vision Nav 좌표를 Edge에 저장하여 재사용
3. **Template Matching**: 특정 UI 요소(X 버튼 등)를 OpenCV로 직접 매칭
4. **병렬 미션**: 독립적인 미션을 동시 실행 (다중 에뮬레이터)
5. **적응형 시간 예산**: API 응답 시간에 따라 미션 시간 자동 조절

---

## 부록 A: 파일 경로 요약

```
c10_plus_v25/
├── run.py                          # CLI 진입점
├── pipeline.py                     # 6-Phase 파이프라인
├── core.py                         # ADB + Claude API 헬퍼
├── recorder.py                     # 터치 녹화
├── player.py                       # 단순 재생 (레거시)
├── smart_player/                   # Smart Player 패키지
│   ├── __init__.py
│   ├── classifier.py               # 화면 분류기
│   ├── nav_graph.py                # 네비게이션 그래프
│   ├── navigator.py                # 탐색 엔진
│   ├── popup_handler.py            # 팝업 핸들러
│   ├── mission_router.py           # 미션 라우터
│   └── smart_capture.py            # 오케스트레이터
├── genres/                         # 장르 모듈
│   ├── __init__.py                 # GenreBase + 레지스트리
│   ├── idle_rpg.py                 # Idle RPG (Ash N Veil)
│   ├── puzzle.py                   # 퍼즐 (Car Match 등)
│   └── merge.py                    # 머지 게임
├── recordings/                     # 녹화 데이터
│   └── {game_key}/
│       ├── recording.json          # 터치 이벤트 + 메타데이터
│       ├── frames/                 # 녹화 중 스크린샷
│       ├── cache/                  # 분류기 캐시
│       ├── classifications.json    # 프레임별 화면 분류 결과
│       └── nav_graph.json          # 네비게이션 그래프
└── output/                         # 분석 결과
    └── {game_key}/                 # (Section 11 참조)
```

---

## 부록 B: 핵심 데이터 흐름 다이어그램

```
                    ┌─────────────────┐
                    │  유저 10분 플레이  │
                    └────────┬────────┘
                             │ recorder.py
                    ┌────────▼────────┐
                    │ recording.json  │
                    │ + frames/*.png  │
                    └────────┬────────┘
                             │ classifier.py
                    ┌────────▼────────┐
                    │ classifications │
                    │ .json           │
                    └────────┬────────┘
                             │ nav_graph.py
                    ┌────────▼────────┐
                    │ nav_graph.json  │
                    │ (11 nodes,      │
                    │  26 edges)      │
                    └────────┬────────┘
                             │ smart_capture.py
                    ┌────────▼────────┐
                    │  10 AI Missions  │
                    │  ┌─── M1 ──┐    │
                    │  │ navigate │    │
                    │  │ classify │    │    navigator.py
                    │  │ capture  │    │    + popup_handler.py
                    │  └─────────┘    │    + mission_router.py
                    │  ┌─── M2 ──┐    │
                    │  │  ...     │    │
                    │  └─────────┘    │
                    │  ... M3~M10 ... │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───┐  ┌──────▼──────┐  ┌───▼────────┐
     │ sessions/  │  │ OCR (M2)    │  │ Wiki (M3)  │
     │ 01~10/*.png│  │ ocr_results │  │ community  │
     └────────┬───┘  └──────┬──────┘  └───┬────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │ Phase 2: Vision Analysis
                    ┌────────▼────────┐
                    │ observations/   │
                    │ session_01~10   │
                    │ .txt            │
                    └────────┬────────┘
                             │ Phase 3: Aggregate
                    ┌────────▼────────┐
                    │ consensus.txt   │
                    └────────┬────────┘
                             │ Phase 4: Spec
                    ┌────────▼────────┐
                    │ spec.yaml       │
                    │ (32 params)     │
                    └────────┬────────┘
                             │ Phase 5: Score
                    ┌────────▼────────┐
                    │ score.yaml      │
                    │ (vs ground      │
                    │  truth)         │
                    └────────┬────────┘
                             │ Phase 6: Report
                    ┌────────▼────────┐
                    │ report.md       │
                    └─────────────────┘
```

---

*이 문서는 C10+ v2.5 AI Tester System의 완전한 사양서입니다. 어떤 LLM이든 이 문서를 참조하여 시스템을 이해하고, 새로운 장르 모듈을 추가하거나, 파이프라인을 실행할 수 있습니다.*
