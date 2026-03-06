# AI Game Tester — Multi-Genre Expansion Analysis
## 다장르 확장 가능성 분석

> 작성일: 2026-03-06
> 기반: tester v2 (5-Layer Constrained Architecture)
> 현재 지원: CarMatch (puzzle_match), Ash & Veil (idle_rpg)

---

## 1. 다른 장르의 게임도 테스트가 가능한가?

### 결론: 가능하다. 단, 장르별로 "교체해야 하는 레이어"가 다르다.

현재 5-Layer 구조의 장르별 재사용성:

```
Layer           | 장르 무관 (공통) | 장르별 교체 필요
----------------|-----------------|------------------
L1 Perception   | 50%             | 50% (프롬프트+파서)
L2 Memory       | 30%             | 70% (상태 구조 자체가 다름)
L3 Decision     | 10%             | 90% (핵심 게임 로직)
L4 Execution    | 90%             | 10% (ADB는 공통)
L5 Verification | 60%             | 40% (성공/실패 판단 기준)
```

### 장르별 난이도 매트릭스

```
장르              | 난이도 | 이유                              | 예시 게임
------------------|--------|-----------------------------------|------------------
Puzzle (Match)    | ★★☆☆☆ | 이산 상태, 턴제, 정적 보드         | CarMatch, Candy Crush
Idle/Clicker      | ★☆☆☆☆ | 대부분 탭+대기, 판단 단순          | Ash & Veil, Cookie Clicker
Merge             | ★★☆☆☆ | 드래그+드롭, 아이템 인식           | Merge Dragons, EverMerge
Simulation/Tycoon | ★★★☆☆ | 복합 UI, 리소스 관리, 시간 의존    | Township, SimCity
Word/Trivia       | ★★★☆☆ | OCR 필수, 언어 이해 필요           | Wordle, Wordscapes
Tower Defense     | ★★★☆☆ | 배치 위치 판단, 타이밍             | Kingdom Rush
RPG (Turn-based)  | ★★★★☆ | 스킬 선택, 속성 상성, 장비 관리    | Summoners War
Action/Arcade     | ★★★★★ | 실시간 반응, 프레임 단위 판단      | Subway Surfers
Strategy (RTS)    | ★★★★★ | 복합 판단, 장기 전략, 멀티유닛     | Clash Royale
Shooter           | ★★★★★ | 정밀 에이밍, 실시간, 3D 공간인식   | PUBG Mobile
```

### 현실적으로 단기 확장 가능한 장르 (6개월 이내)

1. **Idle/Clicker** — 이미 Ash & Veil로 검증 중. Playbook만 작성하면 됨
2. **Puzzle (다른 게임)** — CarMatch 구조 90% 재사용. 프롬프트+핸들러만 교체
3. **Merge** — 드래그 액션 추가 필요하지만 상태 구조는 퍼즐과 유사
4. **Simulation/Tycoon** — UI 네비게이션 중심. 복잡하지만 실시간 아님

### 단기 확장이 어려운 장르

- **Action/Arcade**: 1프레임=16ms인데 Vision API=2000ms. 물리적으로 불가능
- **Shooter/MOBA**: 에이밍+이동 동시 제어. ADB tap으로는 한계
- **RTS**: 멀티유닛 동시 제어, 미니맵+본맵 이중 인식 필요

---

## 2. 테스트를 위해 필요한 작업/설정/역할/페르소나

### 새 게임 추가 시 필요한 작업 (체크리스트)

```
Phase 1: 정보 수집 (사람이 해야 함)
├── [ ] 게임 설치 + 실행 확인 (BlueStacks)
├── [ ] 화면 유형 목록 작성 (스크린샷 30~50장)
├── [ ] 핵심 게임플레이 1판 녹화 (화면+탭 좌표)
├── [ ] UI 좌표 측정 (버튼, 보드, 금지 영역)
└── [ ] 게임 규칙 정리 (승리/패배 조건, 매칭 규칙 등)

Phase 2: Playbook 작성 (사람+AI 협업)
├── [ ] screen_handlers 등록 (화면 유형 → 고정 행동)
├── [ ] forbidden_regions 정의 (탭 금지 영역)
├── [ ] boosters 좌표 등록
├── [ ] 우선순위 트리 설계 (P0~Pn)
└── [ ] Perception 프롬프트 커스텀 (게임 고유 오브젝트)

Phase 3: 테스트 + 보정 (AI 실행, 사람 감독)
├── [ ] 10분 테스트 → 로그 검토
├── [ ] 좌표 오차 보정
├── [ ] 누락된 화면 유형 추가
└── [ ] 의사결정 우선순위 조정
```

### 3계층 페르소나 구조

현재 시스템은 게임별 Playbook이 곧 페르소나인데, 이를 **3계층으로 분리**해야 다장르 확장이 가능해진다.

```
┌─────────────────────────────────────────────────────┐
│ Layer A: Genre Persona (장르 페르소나)                 │
│ "나는 퍼즐 게임 플레이어다"                            │
│ - 장르 공통 행동 패턴                                  │
│ - 장르 공통 실패 대응                                  │
│ - 장르 공통 UI 패턴 (back=팝업닫기, X=우상단 등)       │
├─────────────────────────────────────────────────────┤
│ Layer B: Game Persona (게임 페르소나)                  │
│ "나는 CarMatch를 플레이하는 사람이다"                   │
│ - 게임 고유 규칙 (3-match, 7-slot holder)             │
│ - 게임 고유 화면 목록 (30개)                           │
│ - 게임 고유 좌표+부스터                                │
├─────────────────────────────────────────────────────┤
│ Layer C: Player Persona (플레이어 페르소나)             │
│ "나는 초보/중급/고급 플레이어다"                        │
│ - 부스터 사용 성향 (보수적 vs 적극적)                   │
│ - 리스크 허용도 (holder 몇 칸에서 불안해하는가)         │
│ - 과금 성향 (무과금/소과금/고래)                        │
│ - 플레이 패턴 (짧은 세션 vs 장시간)                    │
└─────────────────────────────────────────────────────┘
```

### 코드 구조 매핑

```
Layer A (Genre)  →  GenreProfile (MD 파일 또는 YAML)
                    장르별 공통 규칙을 코드화
                    예: puzzle_match.yaml, idle_rpg.yaml, merge.yaml

Layer B (Game)   →  Playbook (현재 playbook.py)
                    게임 고유 규칙, 좌표, 화면 핸들러
                    예: create_carmatch_playbook(), create_ashveil_playbook()

Layer C (Player) →  PlayerProfile (새로 추가 필요)
                    플레이 스타일 파라미터
                    예: casual_f2p.yaml, hardcore_dolphin.yaml
```

### Layer C (Player Persona) 파라미터 예시

```yaml
# casual_f2p.yaml — 무과금 캐주얼 유저
player_type: "casual_f2p"

behavior:
  session_duration_min: 5        # 평균 세션 5분
  sessions_per_day: 3            # 하루 3번
  retry_on_fail: 1               # 실패 시 1회 재도전

risk_tolerance:
  holder_worry_at: 4             # holder 4칸부터 불안
  use_booster_at: 5              # 5칸에서 부스터 사용
  accept_ad_reward: true         # 광고 보상 수락

monetization:
  will_purchase: false           # 과금 안 함
  watch_ads: true                # 광고 시청 O
  max_ad_per_session: 3          # 세션당 광고 최대 3회

skill_level:
  look_ahead_turns: 1            # 1수 앞만 봄
  color_recognition_accuracy: 0.85  # 가끔 색 헷갈림
  tap_precision_px: 30           # 탭 정확도 ±30px
```

```yaml
# hardcore_whale.yaml — 고과금 하드코어 유저
player_type: "hardcore_whale"

behavior:
  session_duration_min: 30
  sessions_per_day: 8
  retry_on_fail: 5

risk_tolerance:
  holder_worry_at: 5
  use_booster_at: 6
  accept_ad_reward: false        # 광고 안 봄 (과금으로 해결)

monetization:
  will_purchase: true
  max_purchase_per_day: 3
  purchase_trigger: "fail_3_times"  # 3번 연속 실패 시 구매

skill_level:
  look_ahead_turns: 3
  color_recognition_accuracy: 0.95
  tap_precision_px: 10
```

---

## 3. 장르별 플레이어 행동 패턴 분석 → 페르소나 생성 방법

### 핵심 문제: "플레이어가 뭘 하는지"를 어떻게 데이터화하는가?

### 방법 1: 행동 분류 프레임워크 (Genre Action Taxonomy)

모든 모바일 게임의 플레이어 행동을 **7가지 범주**로 분류:

```
┌──────────────────────────────────────────────────────────────┐
│ 1. NAVIGATE  — 화면 간 이동 (탭 버튼, 스와이프, back)           │
│ 2. SELECT    — 게임 오브젝트 선택 (차 탭, 캐릭터 선택)          │
│ 3. PLACE     — 오브젝트 배치 (드래그&드롭, 타워 설치)            │
│ 4. ACTIVATE  — 능력/부스터 사용 (스킬, 아이템, Undo)            │
│ 5. WAIT      — 의도적 대기 (타이머, 쿨다운, 관찰)               │
│ 6. DECIDE    — 리소스 분배 (업그레이드 선택, 장비 교체)          │
│ 7. RESPOND   — 반응형 행동 (팝업 닫기, 광고 처리, 보상 수령)     │
└──────────────────────────────────────────────────────────────┘
```

장르별 행동 비중:

```
장르            | NAV  | SEL  | PLACE| ACT  | WAIT | DEC  | RESP
----------------|------|------|------|------|------|------|------
Puzzle (Match)  | 15%  | 40%  |  0%  | 10%  |  5%  | 15%  | 15%
Idle/Clicker    | 20%  | 10%  |  0%  |  5%  | 30%  | 20%  | 15%
Merge           | 10%  | 15%  | 35%  |  5%  | 10%  | 15%  | 10%
Sim/Tycoon      | 25%  | 10%  | 15%  | 10%  | 15%  | 15%  | 10%
TD              | 10%  |  5%  | 30%  | 20%  | 10%  | 20%  |  5%
Turn RPG        | 15%  | 20%  |  0%  | 25%  |  5%  | 25%  | 10%
```

### 방법 2: 세션 패턴 분석 (Session Flow Template)

실제 플레이어의 1세션을 **Phase 단위**로 분해:

```
[CarMatch 세션 예시 — 캐주얼 F2P]

Phase 1: 진입 (30초)
  RESPOND: 이벤트 팝업 X 닫기 (×3)
  NAVIGATE: 로비에서 Level N 탭

Phase 2: 초반 (60초)
  SELECT: 앞줄 차 탭 (×4~6)
  WAIT: 애니메이션 대기 (×4~6)

Phase 3: 중반 (120초)
  SELECT: 같은 색 매칭 시도 (P1 행동)
  ACTIVATE: holder 꽉 차면 Undo (1회)
  SELECT: 계속 탭 (×8~12)

Phase 4: 종반 (60초)
  ACTIVATE: 위기 시 Magnet 사용
  SELECT: 마지막 차들 정리

Phase 5: 결과 (20초)
  RESPOND: 승리 → Continue 탭
  RESPOND: 패배 → Try Again 탭 (1회) 또는 포기
  RESPOND: 광고 제안 → 수락 또는 X

Phase 6: 이탈 (10초)
  NAVIGATE: 로비 복귀 또는 앱 종료
```

### 방법 3: 데이터 수집 → 자동 페르소나 추출

```
[수집]                    [분석]                    [페르소나]
실제 플레이 로그     →    패턴 클러스터링      →    자동 페르소나 생성
(탭 좌표+시간+화면)       (K-means 등)              (YAML 출력)

수집 데이터:
- tap_log: [(timestamp, x, y, screen_type), ...]
- session_log: [(start, end, result, taps, matches), ...]
- purchase_log: [(timestamp, item, price), ...]
- ad_log: [(timestamp, accepted, type), ...]
```

이 방법이 가장 이상적이지만, **초기에는 수동 관찰 + 수동 YAML 작성**이 현실적이다.

---

## 4. 실제 플레이어가 AI를 학습시키는 가장 효율적인 구조

### 핵심 원칙: AI에게 "판단"을 가르치지 말고, "상황→행동 매핑"을 가르쳐라

### 4단계 학습 파이프라인

```
Stage 1: Demonstration (시연)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
사람이 플레이하면서 자동 기록

입력: 스크린샷 + 탭 좌표 + 타임스탬프
도구: ADB 탭 로거 (터치 이벤트 캡처) + 스크린 레코더

기록 포맷:
{
  "frame": 1,
  "timestamp": "2026-03-06T10:00:01",
  "screenshot": "demo_0001.png",
  "action": {"type": "tap", "x": 450, "y": 800},
  "screen_type": null,          ← AI가 나중에 채움
  "annotation": null            ← 사람이 선택적으로 추가
}

필요 시연 횟수: 게임당 5~10판 (다양한 상황 포함)


Stage 2: Annotation (주석)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI가 자동 라벨링 + 사람이 교정

자동 생성:
- screen_type (Vision API로 자동 판별)
- holder 상태 (자동 인식)
- 탭 대상 오브젝트 색상 (자동 인식)

사람이 교정:
- 잘못된 screen_type 수정
- 잘못된 색상 수정
- "왜 이 행동을 했는지" 1줄 메모 (선택)

교정 도구: 간단한 웹 UI 또는 스프레드시트
예: "frame 23: screen_type을 popup→lobby_punchout으로 수정"


Stage 3: Rule Extraction (규칙 추출)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
annotated 데이터에서 Playbook 규칙 자동 추출

입력: Stage 2의 교정된 로그
출력: Playbook 초안

추출 가능한 규칙:
- 화면 A에서 항상 (x, y) 탭 → screen_handler 등록
- gameplay에서 holder 5칸 이후 Undo 사용 → holder_danger = 5
- 특정 영역을 절대 탭하지 않음 → forbidden_region 추가
- 같은 색 2개 있을 때 3번째를 찾아 탭 → P1 규칙 확인

AI가 초안 생성 → 사람이 검토+수정


Stage 4: Validation (검증)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
AI가 플레이 → 사람이 "이건 아니야" 피드백

피드백 형태 (가장 효율적인 순서):
1. "이 화면에서는 X를 탭해야 해" (직접 지시)
2. "이 행동은 틀렸어" (부정 피드백)
3. "이 상황에서는 절대 Y하지 마" (금지 추가)
4. "맞아, 잘했어" (긍정 피드백 — 가장 덜 유용)
```

### 정보 제공 포맷 비교

```
방법                    | 효율 | 사람 공수 | AI 학습 효과
------------------------|------|----------|-------------
A. 자유 텍스트 설명      | ★☆☆ | 높음     | 낮음 (해석 모호)
B. 스프레드시트 규칙표   | ★★☆ | 중간     | 중간 (구조화되었으나 맥락 부족)
C. 시연 녹화 + 주석     | ★★★ | 중간     | 높음 (상황-행동 직접 매핑)
D. YAML Playbook 직접   | ★★☆ | 높음     | 높음 (정확하나 전문가만 가능)
E. 시연 + AI 추출 + 교정| ★★★ | 낮음     | 최고 (자동화+인간 교정)
```

**권장: E 방식 (시연 → AI 자동 추출 → 인간 교정)**

### 시연 녹화 시 필수 포함 상황

```
게임당 최소 시연:
[ ] 정상 클리어 1판 (기본 흐름)
[ ] 실패 + 재도전 1판 (실패 처리 흐름)
[ ] 부스터/아이템 사용 1판 (부스터 타이밍)
[ ] 팝업/광고 처리 3~5건 (팝업 핸들링)
[ ] 위기 상황 대응 1판 (holder 가득 찼을 때 등)
[ ] 로비 네비게이션 (설정, 상점, 이벤트 진입+탈출)

총 소요 시간: 30~60분 / 게임
```

### 시연 기록 도구 구현 (필요한 코드)

```python
# 핵심: ADB 이벤트 캡처 + 스크린샷 동기화
# adb shell getevent -l  → 터치 이벤트 실시간 캡처
# adb exec-out screencap -p  → 이벤트 발생 시 스크린샷

# 출력: demonstration_log.jsonl
# 각 줄 = {"frame": N, "ts": "...", "img": "demo_N.png",
#           "action": {"type":"tap","x":400,"y":800}}
```

---

## 5. 이미지 인식 + 좌표 하이브리드 방식의 유효성

### 질문 핵심: "좌표만 = 매크로" vs "이미지+좌표 = 지능적 행동"

### 명확한 구분

```
순수 매크로:
  1. 스크린샷 안 봄
  2. 항상 같은 좌표를 같은 순서로 탭
  3. 화면 상태와 무관하게 동작
  4. 게임이 조금만 바뀌면 즉시 깨짐

  예: AutoHotKey 스크립트
      tap(540, 1500)  # 무조건 여기 탭
      sleep(3000)
      tap(540, 1170)  # 무조건 여기 탭

현재 시스템 (이미지+좌표 하이브리드):
  1. 매 프레임 스크린샷 분석 (Vision AI)
  2. "무엇이 보이는지"에 따라 행동 결정
  3. 좌표는 "어디를 탭할지"의 보조 수단
  4. UI 위치가 바뀌면 좌표만 수정하면 됨

  예: 현재 시스템
      board = perceive(screenshot)     # 뭐가 보이는지 판단
      if board.screen_type == "popup": # 상황에 따라 다른 행동
          actions = handle_popup()
      else:
          actions = find_best_car(board)  # AI가 찾은 차 탭
```

### 하이브리드 방식의 역할 분담

```
┌────────────────────────────────────────────────────────┐
│              이미지 인식의 역할 (AI, 동적)               │
│                                                        │
│  "이 화면이 뭐지?"      → screen_type 판별              │
│  "홀더에 뭐가 있지?"    → holder 색상 인식               │
│  "탭 가능한 차가 뭐지?" → active_cars 좌표+색상 인식     │
│  "이 버튼이 뭐지?"      → UI 요소 식별                  │
│                                                        │
│  = 매 프레임 다른 결과 (게임 상태에 따라)                 │
├────────────────────────────────────────────────────────┤
│              좌표의 역할 (규칙, 고정)                    │
│                                                        │
│  "Undo 버튼은 여기"     → 부스터 좌표 (고정)             │
│  "여기는 탭 금지"       → forbidden_region (고정)        │
│  "X 닫기는 우상단"      → 팝업 핸들러 좌표 (고정)        │
│  "보드 영역은 여기"     → board_region (고정)            │
│                                                        │
│  = 항상 같은 값 (UI 레이아웃이 바뀌지 않는 한)            │
└────────────────────────────────────────────────────────┘
```

### 이것이 매크로가 아닌 이유

| 기준 | 매크로 | 현재 하이브리드 |
|------|--------|----------------|
| 화면을 보는가? | X | O (Vision AI) |
| 상황별 다른 행동? | X (고정 시퀀스) | O (Decision tree) |
| 게임 상태 이해? | X | O (BoardState) |
| 실패 시 대응? | X (계속 반복) | O (에스컬레이션) |
| 새 화면 대응? | X (멈춤) | O (unknown → back) |
| 승리/패배 인식? | X | O (screen_type) |

### 다른 게임 적용 시 효과

```
게임 변경 시 교체 비용:

순수 매크로:     좌표 전부 재작성 + 타이밍 전부 재측정 = 100% 재작성
순수 이미지 AI:  프롬프트만 수정하면 되지만 정확도 불안정 = 50% 재작성 + 불안정
하이브리드:      고정 좌표 교체 + 프롬프트 교체 = 40% 재작성 + 안정적
```

### 하이브리드의 장르별 적용 효과

```
장르            | 고정좌표 비중 | 이미지인식 비중 | 하이브리드 효과
----------------|-------------|----------------|----------------
Puzzle          | 30%         | 70%            | ★★★★★ (최적)
Idle            | 50%         | 50%            | ★★★★☆ (좋음)
Merge           | 20%         | 80%            | ★★★★☆ (좋음)
Sim/Tycoon      | 40%         | 60%            | ★★★☆☆ (보통)
Turn RPG        | 25%         | 75%            | ★★★☆☆ (보통)
Action          | 10%         | 90%            | ★★☆☆☆ (부족 — 속도 한계)
```

**결론**: 하이브리드는 **턴제/비실시간 게임**에서 가장 효과적이다.
고정 좌표가 "뼈대"(UI 구조), 이미지 인식이 "눈"(현재 상태 파악)의 역할.

---

## 6. 구현 로드맵 — 새 게임 추가 파이프라인

### Phase 1: GenreProfile 시스템 (공통 기반)

```
E:\AI\virtual_player\
├── genres/                          ← 신규
│   ├── puzzle_match.yaml            ← 퍼즐 매치 장르 공통
│   ├── idle_rpg.yaml                ← 방치형 RPG 장르 공통
│   ├── merge.yaml                   ← 머지 장르 공통
│   └── simulation.yaml              ← 시뮬레이션 장르 공통
├── personas/                        ← 신규
│   ├── casual_f2p.yaml
│   ├── mid_dolphin.yaml
│   └── hardcore_whale.yaml
├── tester/
│   ├── playbook.py                  ← 기존 (게임별 Playbook)
│   ├── genre_profile.py             ← 신규 (장르 공통 로더)
│   ├── player_profile.py            ← 신규 (페르소나 로더)
│   ├── perception.py                ← 기존 (프롬프트만 교체 가능하게)
│   ├── decision.py                  ← 기존 → 장르별 Decision 서브클래스
│   └── demo_recorder.py             ← 신규 (시연 녹화 도구)
└── data/games/
    ├── carmatch/                    ← 기존
    │   ├── playbook_carmatch.yaml
    │   └── demonstrations/          ← 시연 데이터
    ├── ashveil/                     ← 기존 (확장)
    │   ├── playbook_ashveil.yaml
    │   └── demonstrations/
    └── [new_game]/                  ← 새 게임
        ├── playbook_[game].yaml
        ├── screen_types.json
        └── demonstrations/
```

### Phase 2: 시연 녹화기 (Demo Recorder)

```python
# demo_recorder.py — 사람의 플레이를 기록하는 도구
#
# 사용법: python -m virtual_player.demo_recorder --game carmatch
#
# 기능:
# 1. ADB getevent로 터치 이벤트 실시간 캡처
# 2. 터치 발생 시 스크린샷 자동 저장
# 3. (터치 직전, 직후) 프레임 쌍으로 저장
# 4. JSONL 로그 출력
#
# 출력: data/games/carmatch/demonstrations/demo_001.jsonl
```

### Phase 3: Playbook 자동 생성기

```python
# playbook_generator.py
#
# 입력: demonstration JSONL + 스크린샷 폴더
# 처리:
#   1. Vision API로 각 스크린샷 screen_type 자동 라벨링
#   2. screen_type별 탭 좌표 클러스터링
#   3. 반복 패턴 추출 → screen_handler 후보 생성
#   4. 금지 영역 추론 (한 번도 탭하지 않은 영역)
# 출력: playbook 초안 YAML
```

---

## 7. 요약 — 5개 질문 답변

### Q1: 다른 장르도 테스트 가능한가?
**가능하다.** 단, 비실시간(턴제/퍼즐/방치/머지/시뮬레이션)에 한해.
실시간 장르(액션/슈팅/RTS)는 Vision API 응답 속도(2~5초) 때문에 물리적 한계.

### Q2: 필요한 작업/설정/역할/페르소나는?
**3계층 페르소나**: Genre(장르) + Game(게임) + Player(플레이어).
새 게임 추가는 Playbook 1개 + Perception 프롬프트 1개 + 시연 5~10판.

### Q3: 장르별 행동 패턴 → 페르소나 생성 방법은?
**7가지 행동 범주(NAV/SEL/PLACE/ACT/WAIT/DEC/RESP)** 프레임워크로 분류.
가장 효율적 경로: 시연 녹화 → AI 자동 추출 → 인간 교정.

### Q4: 실제 플레이어가 AI 학습시키는 최효율 구조는?
**4단계**: Demonstration(시연) → Annotation(주석) → Rule Extraction(규칙추출) → Validation(검증).
핵심은 "자유 텍스트 설명"이 아니라 **"상황-행동 쌍"을 스크린샷+탭로그로 직접 제공**.

### Q5: 이미지+좌표 하이브리드는 유효한가?
**매우 유효하다.** 매크로와의 결정적 차이는 "화면 상태를 인식하고 상황별 다른 행동을 한다"는 것.
고정 좌표는 UI 뼈대(버튼 위치), 이미지 인식은 게임 상태(현재 보드). 역할이 분리되어 있어
게임 교체 시에도 고정 좌표만 업데이트하면 나머지 로직을 재사용할 수 있다.
턴제/비실시간 장르에서 효과가 가장 크고, 다른 게임에도 동일하게 적용 가능하다.
