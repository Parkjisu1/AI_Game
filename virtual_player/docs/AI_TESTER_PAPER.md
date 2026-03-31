# Black-box AI Game Tester: 소스코드 없는 모바일 게임의 자율 플레이, 데이터 추출, 역공학 시스템

**Version 2.0 | 2026-03-31**
**System Codebase: `E:\AI\virtual_player\` (199 Python files, 5-Layer Architecture)**

---

## 목차

1. [Abstract & Problem Statement](#1-abstract--problem-statement)
2. [Related Work](#2-related-work)
3. [System Architecture](#3-system-architecture)
4. [Perception Layer](#4-perception-layer)
5. [Data Collection Pipeline](#5-data-collection-pipeline)
6. [Human Play Database Schema](#6-human-play-database-schema)
7. [AI Decision Engine](#7-ai-decision-engine)
8. [Reverse Engineering Module](#8-reverse-engineering-module)
9. [Distributed Device Management](#9-distributed-device-management)
10. [Self-Improvement Loop](#10-self-improvement-loop)
11. [Evaluation Framework](#11-evaluation-framework)
12. [Implementation Roadmap](#12-implementation-roadmap)
13. [Risk Analysis](#13-risk-analysis)
14. [Appendix A: File Structure](#appendix-a-file-structure)
15. [Appendix B: API Reference](#appendix-b-api-reference)
16. [Appendix C: Supported Game Genres](#appendix-c-supported-game-genres)

---

## 1. Abstract & Problem Statement

### 1.1 배경

모바일 게임 시장은 연간 수십만 개의 신규 타이틀이 출시되며, 경쟁사 분석(competitive intelligence)은 게임 퍼블리셔의 핵심 역량이다. 기존 경쟁사 분석은 인간 테스터가 수동으로 게임을 플레이하며 BM(Business Model), 난이도 커브, UI 흐름을 기록하는 방식으로 수행된다. 이 과정은 다음과 같은 한계를 가진다:

- **확장 불가(Non-scalable)**: 1인 테스터가 1개 게임에 40시간 이상 투자해야 의미 있는 데이터 수집 가능
- **주관적(Subjective)**: 테스터 역량에 따라 데이터 품질 편차가 극심
- **비반복(Non-repeatable)**: 동일 게임을 재테스트할 때 일관성 보장 불가
- **비용(Cost)**: 연간 수백 타이틀 분석 시 인건비가 기하급수적 증가

### 1.2 Black-box 제약 조건

본 시스템은 **소스코드 접근이 불가능한** 환경에서 동작한다. 이는 다음을 의미한다:

| 접근 가능 | 접근 불가능 |
|----------|-----------|
| APK 파일 (설치 가능) | 소스코드, 서버 API |
| 화면 스크린샷 (ADB screencap) | 내부 변수, 메모리 |
| 터치 입력 (ADB input tap) | 게임 로직, 확률 테이블 |
| Logcat 출력 (ADB logcat) | 서버-클라이언트 통신 암호 |
| APK 정적 분석 (제한적) | 난독화된 코드 |

**입력**: Android Emulator(BlueStacks/LDPlayer) 위에서 실행되는 APK
**도구**: ADB(Android Debug Bridge) 만 사용 -- 스크린샷 캡처, 터치 입력, 로그 수집
**출력**: 게임 시스템의 역공학 결과 -- BM 분석, 데이터 테이블 복원, 아키텍처 추론

### 1.3 핵심 목표

```
[APK 설치] → [자율 플레이] → [데이터 수집] → [패턴 분석] → [역공학 결과]
     ↓              ↓              ↓              ↓              ↓
  BlueStacks   AI Decision    TB-scale DB    ML Pipeline    BM Report
                Engine         per device                   Data Tables
                                                           Architecture
```

**Goal 1: 자율 플레이 (Autonomous Play)**
- 미지의 게임을 스스로 학습하여 플레이
- 장르별 행동 패턴 자동 적용
- 인간 수준의 클리어율 달성 (목표: 60%+ for casual games)

**Goal 2: 데이터 추출 (Data Extraction)**
- 레벨별 난이도 커브, 리소스 경제, 진행 시스템 추출
- IAP 트리거, 광고 빈도, Paywall 패턴 탐지
- 화면 흐름 그래프(State Machine) 자동 생성

**Goal 3: 분산 저장 해결 (Distributed Storage)**
- 디바이스 당 TB 단위 데이터 생성 (프레임 + 로그)
- Edge Processing으로 유의미한 이벤트만 중앙 DB 전송
- Hot/Warm/Cold 3-tier 저장 전략

### 1.4 논문 기여(Contribution)

1. **Vision-only Black-box Architecture**: 소스코드 없이 스크린샷만으로 게임 상태를 완전히 파악하는 3-tier fallback 인식 체계 (YOLO → OpenCV → VLM)
2. **Playbook-driven Decision System**: AI 자유도를 억제하고 규칙 기반으로 안전하게 플레이하는 Layered Decision Architecture
3. **Self-improving Swarm Loop**: 4-Agent Cycle (Play → Analyze → Improve → Validate)로 코드를 자동 개선하는 AutoML 적 접근
4. **Edge-first Data Pipeline**: 디바이스에서 경량 분류 후 유의미 이벤트만 중앙 전송하는 TB-scale 분산 수집 아키텍처

---

## 2. Related Work

### 2.1 게임 AI 에이전트 선행 연구

#### 2.1.1 OpenAI Gym / Retro (2016~)

OpenAI Gym은 Atari 게임 등의 표준 벤치마크를 제공하며, 에이전트가 프레임 단위 픽셀 입력을 받아 액션을 출력한다. Retro는 이를 SNES, Genesis 등 레트로 게임으로 확장했다.

**차이점**: Gym/Retro는 게임 에뮬레이터가 reward 함수를 직접 제공하지만, 본 시스템은 reward가 없다. 화면 변화에서 reward를 추론해야 한다. 또한 Gym은 60fps 프레임 단위 입력이지만, 본 시스템은 ADB 제약으로 ~1fps 수준이다.

#### 2.1.2 DeepMind AlphaGo / AlphaStar (2016~2019)

AlphaGo는 Monte Carlo Tree Search + Deep RL로 바둑을 정복했고, AlphaStar는 StarCraft II에서 그랜드마스터 수준을 달성했다. 둘 다 게임 내부 API에 접근하여 완전한 게임 상태를 입력으로 받는다.

**차이점**: 본 시스템은 게임 상태를 직접 받지 못하고 스크린샷에서 추론해야 한다. 또한 AlphaGo/AlphaStar는 단일 게임 특화인 반면, 본 시스템은 multi-game 범용성을 목표로 한다.

#### 2.1.3 Voyager (Wang et al., 2023) -- Minecraft 자율 에이전트

LLM 기반으로 Minecraft를 자율 탐색하며, Skill Library를 구축하여 새로운 기술을 학습한다. Curriculum 기반 자동 진행, Self-verification, Skill 재사용이 핵심이다.

**유사점**: 본 시스템의 ExperienceDB (`tester/swarm/experience_db.py`)는 Voyager의 Skill Library 개념을 적용했다. "이 화면에서 이 좌표를 탭하면 이 결과가 나온다"를 반복 관찰로 축적한다.

**차이점**: Voyager는 Minecraft API (bot 라이브러리)를 사용하여 game state에 접근 가능하지만, 본 시스템은 ADB 스크린샷만 사용한다.

#### 2.1.4 Reflexion (Shinn et al., 2023) -- 자기 반성 에이전트

에이전트가 실패 경험을 자연어 반성(reflection)으로 변환하고, 이를 다음 시도의 컨텍스트로 제공한다. 이를 통해 trial-and-error 학습 효율을 획기적으로 개선했다.

**유사점**: 본 시스템의 Reflector (`tester/swarm/reflector.py`)가 정확히 Reflexion 패턴을 구현한다. 각 플레이 세션 후 Analyst Agent가 반성 프롬프트를 생성하고, 교훈(lesson)을 축적하여 다음 Improve 사이클에 반영한다.

#### 2.1.5 AppAgent (Yang et al., 2023) -- 모바일 앱 자동화

LLM + 스크린샷으로 모바일 앱을 자율 조작하는 에이전트. UI 요소를 인식하고 탭/스와이프 액션을 생성한다.

**차이점**: AppAgent는 일반 앱 UI를 대상으로 하며, 게임의 실시간 인터랙션, 애니메이션, 보상 구조를 다루지 않는다. 본 시스템은 게임 특화 Perception + 장르별 Decision 전략을 제공한다.

### 2.2 본 시스템의 아키텍처 매핑

| 선행 연구 개념 | 본 시스템 구현체 | 파일 위치 |
|-------------|--------------|---------|
| Gym reward function | `Memory.update_from_board()` | `tester/memory.py` |
| AlphaGo MCTS | `LookaheadSimulator` / `DeepLookahead` | `tester/lookahead.py` |
| Voyager Skill Library | `ExperienceDB` | `tester/swarm/experience_db.py` |
| Voyager Curriculum | `GenreProfile.screen_flow` | `tester/genres/base.py` |
| Reflexion self-reflection | `Reflector` | `tester/swarm/reflector.py` |
| AppAgent UI recognition | `Perception` (YOLO + VLM) | `tester/perception.py` |

---

## 3. System Architecture

### 3.1 5-Layer Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                      AI Game Tester System                        │
│                                                                    │
│  ┌────────────────────────────────────────────────────────────┐   │
│  │ Layer 5: Verification (확인)                                 │   │
│  │ - 탭 전/후 홀더 비교                                          │   │
│  │ - 화면 전환 감지                                              │   │
│  │ - 실패 탭 기록                                                │   │
│  │ Latency: ~50ms (비교 로직)                                    │   │
│  └────────────────┬───────────────────────────────────────────┘   │
│                   │ result: car_moved | match_3 | no_change       │
│  ┌────────────────┴───────────────────────────────────────────┐   │
│  │ Layer 4: Execution (손)                                      │   │
│  │ - ADB tap/back/relaunch 실행                                  │   │
│  │ - 액션 후 대기 (애니메이션)                                     │   │
│  │ - 실행 로그 기록                                               │   │
│  │ Latency: 300ms~2s (ADB + animation wait)                     │   │
│  └────────────────┬───────────────────────────────────────────┘   │
│                   │ Action(type, x, y, wait, reason)              │
│  ┌────────────────┴───────────────────────────────────────────┐   │
│  │ Layer 3: Decision (판단)                                      │   │
│  │ - 3-Stage Pipeline: Safety → Pattern → Lookahead             │   │
│  │ - P0~P5 우선순위 고정 분기                                     │   │
│  │ - 화면별 핸들러 라우팅                                          │   │
│  │ Latency: <5ms (규칙 기반, ML 없음)                            │   │
│  └────────────────┬───────────────────────────────────────────┘   │
│                   │ BoardState + GameMemory                       │
│  ┌────────────────┴───────────────────────────────────────────┐   │
│  │ Layer 2: Memory (기억)                                        │   │
│  │ - 고정 크기 단기 기억 (매 게임 리셋)                             │   │
│  │ - 홀더 상태, 실패 탭 좌표 (최근 5개)                             │   │
│  │ - 연속 실패 카운트, 매칭 카운트                                  │   │
│  │ Latency: <1ms (in-memory)                                     │   │
│  └────────────────┬───────────────────────────────────────────┘   │
│                   │ BoardState(screen_type, holder, active_cars)  │
│  ┌────────────────┴───────────────────────────────────────────┐   │
│  │ Layer 1: Perception (눈)                                      │   │
│  │ - YOLO classify: 5ms (screen_type 판별)                       │   │
│  │ - YOLO OD: 10ms (차량 위치 감지)                               │   │
│  │ - OpenCV: 50ms (홀더 색상 분석)                                │   │
│  │ - Claude Vision API: 2~8s (최종 폴백)                         │   │
│  │ Latency: 5ms (최선) ~ 8s (최악, VLM 폴백)                     │   │
│  └────────────────────────────────────────────────────────────┘   │
│                   ↑                                                │
│            ADB screencap (~200ms)                                  │
│            1080 x 1920 PNG                                         │
└──────────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow Diagram

```
[Android Emulator]
       │
       │ ADB screencap -p (200ms)
       ▼
[Screenshot PNG, 1080x1920]
       │
       ├──→ [YOLO Classifier] ──→ screen_type (5ms)
       │         │ confidence < 0.6?
       │         ▼
       ├──→ [OpenCV Template] ──→ screen_type fallback (50ms)
       │         │ still unknown?
       │         ▼
       └──→ [Claude Vision API] ──→ screen_type + detail (2~8s)
                  │
                  ▼
          [BoardState JSON]
          {screen_type, holder[7], active_cars[{color,x,y}]}
                  │
                  ├──→ [Memory] update_from_board()
                  │         │
                  │         ▼
                  │    [GameMemory]
                  │    {holder_count, failed_taps, consecutive_fails, ...}
                  │         │
                  ▼         ▼
          [Decision Engine]
          Safety Rules → Pattern Match → Lookahead Sim
                  │
                  ▼
          [Action List]
          [{type:"tap", x:540, y:800, wait:1.5, reason:"P1: red match"}]
                  │
                  ▼
          [Executor]
          ADB input tap 540 800 → sleep 1.5s
                  │
                  ▼
          [Verification]
          new_screenshot → perceive → compare with prev
                  │
                  ├──→ match_3: turn 종료, 다음 perceive
                  ├──→ car_moved: turn 종료
                  ├──→ no_change: failed_tap 기록
                  └──→ screen_changed: 화면 핸들러 전환
```

### 3.3 Component Responsibility Matrix

| Component | 책임 | AI 의존 | 자유도 | 파일 |
|-----------|------|--------|-------|------|
| Perception | 화면 → 구조화 데이터 | YOLO + VLM | 없음 (고정 포맷 출력) | `tester/perception.py` |
| Memory | 단기 기억, 상태 비교 | 없음 | 없음 (고정 필드) | `tester/memory.py` |
| Decision | 행동 결정 | 없음 (규칙 기반) | 없음 (P0~P5 고정) | `tester/decision.py` |
| Playbook | TO DO / TO DON'T 규칙 | 없음 | 없음 (하드코딩) | `tester/playbook.py` |
| Executor | ADB 명령 실행 | 없음 | 없음 (Action만 실행) | `tester/executor.py` |
| Lookahead | 홀더 시뮬레이션 | 가중치만 | 가중치 범위 제한 | `tester/lookahead.py` |
| Swarm | 자기 개선 루프 | Claude Code | 안전 규칙으로 제한 | `tester/swarm/` |
| ExperienceDB | 장기 기억 | 없음 | 없음 (추가만 가능) | `tester/swarm/experience_db.py` |

### 3.4 핵심 설계 원칙

**"AI 자유도 최소, 규칙 최대"**

본 시스템의 핵심 철학은 AI의 자유도를 극단적으로 제한하는 것이다. 각 레이어의 TO DO / TO DON'T를 명시적으로 정의하여 AI가 예상치 못한 행동을 하는 것을 방지한다.

```python
# 예: Perception Layer의 TO DON'T (tester/perception.py 실제 코드)
"""
TO DON'T:
  - 자유 텍스트로 설명하지 마라
  - 가려진 차를 추측하지 마라
  - 스택 아래 색상을 추측하지 마라
"""
```

```python
# 예: Decision Layer의 TO DON'T (tester/decision.py 실제 코드)
"""
TO DON'T:
  - 랜덤으로 아무 차나 탭하지 마라
  - 비활성(blocked) 차를 탭하지 마라
  - Shuffle/Rotate를 사용하지 마라
  - 금지 영역을 탭하지 마라
"""
```

---

## 4. Perception Layer

Perception Layer는 Black-box 시스템의 핵심이다. 소스코드 없이 화면만 보고 게임 상태를 완전히 파악해야 한다.

### 4.1 Screen Classification: YOLO Pipeline

#### 4.1.1 Dataset 생성

```
수집 (yolo_collector.py)
  → ADB screencap 2초 간격
  → raw/ 폴더에 timestamp_NNNN.png 저장
  → 5분 = 150장, 1시간 = 1800장

분류 (수동 + AI 보조)
  → Perception.perceive()로 자동 라벨링
  → 인간이 검증 + 오분류 수정
  → train/ 과 val/ 폴더에 클래스별 분류

YOLO 학습:
  yolo classify train data=dataset_dir model=yolov8n-cls.pt epochs=50 imgsz=224
```

실제 구현된 클래스 (7개):

| Class | 설명 | 학습 이미지 수 (권장) |
|-------|------|-------------------|
| `gameplay` | 게임플레이 중 (보드 + 홀더 보임) | 500+ |
| `lobby` | 로비 화면 (Level N 버튼) | 200+ |
| `win` | 승리 화면 | 100+ |
| `fail` | 패배 화면 (모든 변형 통합) | 200+ |
| `popup` | 팝업/이벤트 오버레이 | 300+ |
| `ad` | 광고 화면 | 200+ |
| `other` | 기타 (로딩, 설정 등) | 100+ |

#### 4.1.2 YOLO 모델 구조

```python
# tester/perception.py의 실제 모델 경로 구조
_YOLO_PATHS = {
    "carmatch": [
        Path("data/games/carmatch/yolo_dataset/models/screen_classifier_best.pt"),
        Path("data/games/carmatch/yolo_dataset/models/screen_classifier/weights/best.pt"),
    ],
    "pixelflow": [
        Path("data/games/pixelflow/yolo_dataset/models/pixelflow_classifier_best.pt"),
        Path("data/games/pixelflow/yolo_dataset/models/train/weights/best.pt"),
    ],
}
```

성능 지표:
- **추론 속도**: ~5ms (GPU) / ~20ms (CPU) per frame
- **정확도**: 92~97% (7-class, 충분한 학습 데이터 전제)
- **신뢰도 임계값**: 0.6 (이하는 fallback으로 전환)

#### 4.1.3 점진적 학습 (Incremental Training)

```
1. 초기: VLM(Claude Vision)으로 100% 인식 (8초/프레임)
2. 수집: 플레이 중 스크린샷 + VLM 라벨 축적
3. 학습: 500장 이상 모이면 YOLO 학습 → 5ms/프레임
4. 배포: YOLO 모델 교체 → VLM 호출 99% 감소
5. 개선: 오분류 피드백 → 재학습 → 정확도 향상
```

### 4.2 Game State Extraction: Claude Vision API

#### 4.2.1 프롬프트 설계

시스템은 SDK 모드(직접 API)와 CLI 모드(2-phase)를 지원한다.

**SDK 모드 (1-phase, 전체 인식)**:
```
입력: 1080x1920 스크린샷
출력: {"screen": "gameplay", "holder": ["red","red","blue",null,...], "active_cars": [...]}
소요: 2~5초
비용: ~$0.003 per call (Haiku)
```

**CLI 모드 (2-phase, 분리 인식)**:
```
Phase 1: screen_type만 판별 → 1단어 응답 (1~3초)
Phase 2: gameplay일 때만 → holder + active_cars JSON (3~8초)
```

Phase 2는 gameplay에서만 호출되므로 전체 VLM 호출 횟수를 50~70% 절감한다.

#### 4.2.2 비용 최적화

```
모델별 비용/성능 비교:
┌────────────────────┬─────────┬────────┬────────────┐
│ Model              │ Latency │ Cost   │ Accuracy   │
├────────────────────┼─────────┼────────┼────────────┤
│ claude-haiku-4-5   │ 2~3s    │ $0.003 │ 85~90%     │
│ claude-sonnet-4    │ 3~5s    │ $0.015 │ 92~95%     │
│ claude-opus-4      │ 5~10s   │ $0.075 │ 95~98%     │
└────────────────────┴─────────┴────────┴────────────┘

전략: 기본 Haiku, 인식 실패 시 Sonnet으로 escalate
YOLO 도입 후: VLM 호출을 gameplay 상세 인식에만 한정
최종: YOLO + OpenCV로 90%+ 처리, VLM은 <5% fallback
```

#### 4.2.3 이미지 압축 전략

```python
# perception.py의 실제 압축 코드
def _compress_if_needed(self, img_path: Path) -> Path:
    """CLI 모드에서 이미지를 540x960 JPEG로 압축.
    좌표 복원은 _compress_scale을 사용."""
    compressed = img_path.parent / f"{img_path.stem}_sm.jpg"
    img = Image.open(img_path)
    orig_w, orig_h = img.size          # 1080x1920
    target_w, target_h = 540, 960      # 50% 축소
    img = img.resize((target_w, target_h), Image.LANCZOS)
    img.save(compressed, "JPEG", quality=70)
    self._compress_scale = round(orig_w / target_w)  # 2
    return compressed
```

효과:
- 원본 PNG: ~2MB → 압축 JPEG: ~80KB (96% 감소)
- VLM 토큰 소비: ~60% 감소
- 좌표 복원: `x * _compress_scale`, `y * _compress_scale`

### 4.3 OCR Pipeline

게임 화면에서 수치 정보를 추출하는 전용 파이프라인:

```
대상 정보:
  - 레벨 번호 (lobby 화면의 "Level 42")
  - 점수 (gameplay 중 표시되는 점수)
  - 리소스 카운트 (코인, 하트, 키 등)
  - 타이머 (제한 시간)
  - 팝업 텍스트 (가격, 할인율 등)

기술 스택:
  Tier 1: OpenCV 템플릿 매칭 (숫자 0~9 템플릿)
  Tier 2: Tesseract OCR (영어/숫자 한정)
  Tier 3: VLM에 특정 영역 크롭 전달
```

```python
# OCR 영역 정의 예시
OCR_REGIONS = {
    "level_number": {
        "screen": "lobby",
        "region": (380, 1440, 700, 1520),  # x1, y1, x2, y2
        "type": "integer",
        "preprocess": "grayscale + threshold + invert",
    },
    "score": {
        "screen": "gameplay",
        "region": (400, 50, 680, 120),
        "type": "integer",
        "preprocess": "grayscale + threshold",
    },
    "coin_count": {
        "screen": "lobby",
        "region": (850, 30, 1050, 80),
        "type": "integer_with_comma",
        "preprocess": "grayscale + threshold",
    },
}
```

### 4.4 Template Matching

고정된 UI 요소는 OpenCV template matching으로 빠르게 감지한다.

```python
# 템플릿 매칭 대상
TEMPLATES = {
    "close_x": {
        "description": "팝업 닫기 X 버튼",
        "method": cv2.TM_CCOEFF_NORMED,
        "threshold": 0.8,
        "multi_scale": [0.8, 1.0, 1.2],  # 크기 변동 대응
    },
    "play_button": {
        "description": "Level N / Play 버튼",
        "method": cv2.TM_CCOEFF_NORMED,
        "threshold": 0.85,
    },
    "heart_icon": {
        "description": "하트 아이콘 (잔여 생명)",
        "method": cv2.TM_CCOEFF_NORMED,
        "threshold": 0.75,
    },
    "ad_indicator": {
        "description": "광고 표시 (AD, Skip 등)",
        "method": cv2.TM_CCOEFF_NORMED,
        "threshold": 0.7,
    },
}
```

### 4.5 3-Tier Fallback Chain

Perception의 핵심 설계는 3-tier fallback이다:

```
┌───────────────────────────────────────────────────────┐
│ Request: perceive(screenshot.png)                      │
│                                                         │
│  [Tier 1: YOLO] ──→ 5ms, confidence >= 0.6?           │
│       │ YES: screen_type 확정                           │
│       │ NO:                                             │
│       ▼                                                 │
│  [Tier 2: OpenCV] ──→ 50ms, template match?            │
│       │ YES: screen_type + UI 요소 위치                  │
│       │ NO:                                             │
│       ▼                                                 │
│  [Tier 3: VLM] ──→ 2~8s, Claude Vision API             │
│       └→ 완전한 구조화 데이터                             │
│                                                         │
│  gameplay 상세 (차량 + 홀더):                             │
│  [YOLO OD] ──→ [OpenCV Color] ──→ [VLM Detail]         │
│   10ms           50ms               3~8s                │
│   차량 위치       홀더 색상            전체 상세            │
└───────────────────────────────────────────────────────┘
```

실제 구현에서의 판단 로직:

```python
# perception.py의 _perceive_two_phase() 실제 흐름
def _perceive_two_phase(self, img_path):
    # Phase 1: YOLO 로컬 분류 시도
    yolo_screen = self._classify_with_yolo(img_path)
    if yolo_screen is not None:
        screen = yolo_screen           # 5ms 완료
    elif self._last_screen == "gameplay":
        screen = "gameplay"            # 캐시 히트
    else:
        raw1 = self._call_vision_cli(img_path, prompt=self._PROMPT_PHASE1)
        screen = self._parse_screen_type(raw1)  # VLM fallback

    # 비-gameplay면 Phase 1만으로 충분
    if screen != "gameplay":
        return BoardState(screen_type=screen, ...)

    # Phase 2: gameplay → 로컬 감지 (YOLO OD / OpenCV)
    board = self._detect_local(original)
    if board is not None and len(board.active_cars) >= 10:
        return board                   # 로컬 감지 성공

    # 로컬 감지 실패 → VLM CLI 폴백
    raw2 = self._call_vision_cli(img_path, prompt=self._PROMPT_PHASE2)
    return self._parse_response(raw2)
```

### 4.6 색상 정규화 (Color Normalization)

VLM은 인간처럼 다양한 색상명을 사용하므로 시스템 색상으로 정규화가 필수적이다:

```python
# perception.py의 실제 COLOR_MAP (60+ 매핑)
COLOR_MAP = {
    "red": "red", "blue": "blue", "green": "green",
    "yellow": "yellow", "orange": "orange", "purple": "purple",
    "pink": "pink", "cyan": "cyan", "white": "white",
    "brown": "brown", "unknown": "unknown",
    # VLM 변형 → 정규화
    "tan": "orange", "gold": "yellow", "golden": "yellow",
    "beige": "orange", "coral": "red", "crimson": "red",
    "violet": "purple", "lavender": "purple",
    "magenta": "pink", "salmon": "pink",
    "lime": "green", "olive": "green",
    "teal": "cyan", "turquoise": "cyan", "aqua": "cyan",
    "navy": "blue", "gray": "white", "silver": "white",
    # ... 총 60+ 매핑
}
```

---

## 5. Data Collection Pipeline

### 5.1 Edge Processing Architecture

각 디바이스(에뮬레이터)는 경량 분류기를 로컬에서 실행하여, 모든 프레임을 중앙 DB에 전송하는 것을 방지한다.

```
┌─────────────────────────────────────────────────┐
│ Device (BlueStacks Instance)                     │
│                                                   │
│  [ADB screencap] → 1080x1920 PNG (~2MB)          │
│       │                                           │
│       ▼                                           │
│  [YOLO Classifier] (5ms)                          │
│       │                                           │
│       ├── gameplay (80% of frames) → SKIP         │
│       │   (같은 화면 연속이면 저장 안함)              │
│       │                                           │
│       ├── screen_changed → SAVE EVENT             │
│       │   {timestamp, from_screen, to_screen,      │
│       │    compressed_frame.jpg (80KB)}            │
│       │                                           │
│       ├── win/fail → SAVE + FULL FRAME            │
│       │   {timestamp, screen_type, level_info,     │
│       │    full_frame.png (2MB)}                   │
│       │                                           │
│       └── error/crash → SAVE + LOGCAT             │
│           {timestamp, error_type, logcat_tail,     │
│           full_frame.png}                          │
│                                                   │
│  [Local session_log.jsonl]                        │
│  ← 매 이벤트마다 한 줄 append                       │
│                                                   │
│  [Event Buffer] (메모리, 최대 100개)                │
│       │                                           │
│       ▼ (batch upload, 30초마다 or 100개 차면)      │
│  [→ Central Server]                               │
└─────────────────────────────────────────────────┘
```

#### 5.1.1 이벤트 필터링 규칙

```python
class EventFilter:
    """Edge에서 유의미한 이벤트만 선별."""

    SAVE_ALWAYS = {
        "level_start",      # 레벨 시작 (lobby → gameplay 전이)
        "level_end_win",    # 레벨 클리어
        "level_end_fail",   # 레벨 실패
        "iap_prompt",       # IAP 구매 유도 화면 노출
        "ad_shown",         # 광고 노출
        "new_screen",       # 처음 보는 화면 유형
        "crash",            # 앱 크래시
        "error",            # 인식 에러
    }

    SAVE_SAMPLED = {
        "gameplay_action": 0.01,    # gameplay 중 액션의 1%만 저장
        "screen_transition": 1.0,   # 화면 전환은 100% 저장
        "popup_handling": 0.5,      # 팝업 처리의 50%
    }

    SKIP_ALWAYS = {
        "gameplay_idle",        # gameplay 중 변화 없는 프레임
        "duplicate_screenshot", # 연속 동일 화면
    }

    def should_save(self, event_type: str, context: dict) -> bool:
        if event_type in self.SAVE_ALWAYS:
            return True
        if event_type in self.SKIP_ALWAYS:
            return False
        rate = self.SAVE_SAMPLED.get(event_type, 0.0)
        return random.random() < rate
```

#### 5.1.2 프레임 보존 정책

```
보존 프레임 유형별 저장 형식:
┌──────────────────┬───────────────┬──────────────┬─────────────┐
│ Event Type        │ Image Format  │ Resolution   │ Est. Size   │
├──────────────────┼───────────────┼──────────────┼─────────────┤
│ level_start      │ PNG (원본)     │ 1080x1920   │ ~2MB        │
│ level_end        │ PNG (원본)     │ 1080x1920   │ ~2MB        │
│ win/fail screen  │ PNG (원본)     │ 1080x1920   │ ~2MB        │
│ iap_prompt       │ PNG (원본)     │ 1080x1920   │ ~2MB        │
│ screen_transition│ JPEG q=70     │ 540x960     │ ~80KB       │
│ gameplay_sample  │ JPEG q=50     │ 540x960     │ ~50KB       │
│ error            │ PNG (원본)     │ 1080x1920   │ ~2MB        │
└──────────────────┴───────────────┴──────────────┴─────────────┘
```

### 5.2 Streaming Protocol

#### 5.2.1 Device → Central Server 통신

```
프로토콜 선택지:
  Option A: WebSocket (양방향, 저지연)
  Option B: HTTP POST (단방향, 안정적)
  Option C: gRPC (고성능, 타입 안전)

선택: HTTP POST + 배치 업로드 (Option B)

이유:
  - 디바이스가 일시적으로 오프라인이어도 로컬 버퍼 유지
  - 서버 재시작 시 연결 복구 불필요
  - 구현 복잡도 최소 (requests.post로 충분)
  - 실시간성 불필요 (30초 배치로 충분)
```

#### 5.2.2 업로드 프로토콜

```python
class DeviceUploader:
    """디바이스 → 중앙 서버 배치 업로드."""

    BATCH_SIZE = 100          # 최대 이벤트 수
    BATCH_INTERVAL = 30       # 초
    MAX_PAYLOAD_MB = 50       # 배치 당 최대 크기
    RETRY_DELAYS = [1, 5, 30, 60]  # 재시도 간격 (초)

    def upload_batch(self, events: list) -> bool:
        """이벤트 배치 업로드.

        payload = {
            "device_id": "device_001",
            "session_id": "20260331_143000",
            "batch_seq": 42,
            "events": [
                {
                    "timestamp": "2026-03-31T14:30:15.123Z",
                    "event_type": "level_end_win",
                    "data": { ... },
                    "frame_b64": "...(base64 encoded JPEG)..."
                },
                ...
            ]
        }
        """
        payload = self._build_payload(events)
        compressed = gzip.compress(json.dumps(payload).encode())

        for delay in self.RETRY_DELAYS:
            try:
                resp = requests.post(
                    f"{self.server_url}/api/v1/events",
                    data=compressed,
                    headers={
                        "Content-Type": "application/json",
                        "Content-Encoding": "gzip",
                        "X-Device-ID": self.device_id,
                    },
                    timeout=30,
                )
                if resp.status_code == 200:
                    return True
            except requests.RequestException:
                time.sleep(delay)
        return False
```

#### 5.2.3 대역폭 추정

```
디바이스 1대 기준 (1시간 플레이):
  총 스크린샷: ~3600장 (1fps)
  유의미 이벤트: ~200개 (5.5%)
  이벤트 포함 프레임: ~50개 (원본 PNG), ~150개 (압축 JPEG)

  원본 프레임: 50 x 2MB  = 100MB
  압축 프레임: 150 x 80KB = 12MB
  JSON 메타: 200 x 1KB   = 0.2MB
  ──────────────────────────────
  총: ~112MB/hour/device

  대역폭: 112MB / 3600s = ~0.25 Mbps per device
  10대 동시: ~2.5 Mbps (일반 네트워크로 충분)
```

### 5.3 Recording Format

#### 5.3.1 session_log.jsonl 포맷

각 디바이스는 세션 단위로 JSONL (JSON Lines) 파일을 기록한다:

```jsonl
{"ts":"2026-03-31T14:30:00.000Z","evt":"session_start","device":"dev_001","game":"com.grandgames.carmatch","session":"s_20260331_143000"}
{"ts":"2026-03-31T14:30:02.123Z","evt":"screen","type":"lobby","level":42,"confidence":0.95,"source":"yolo"}
{"ts":"2026-03-31T14:30:05.456Z","evt":"action","type":"tap","x":540,"y":1500,"reason":"Level N button","priority":"P0"}
{"ts":"2026-03-31T14:30:08.789Z","evt":"screen","type":"gameplay","confidence":0.92,"source":"yolo","frame":"f_0003.jpg"}
{"ts":"2026-03-31T14:30:10.012Z","evt":"action","type":"tap","x":300,"y":800,"reason":"P1: red match completion (2+1=3)","priority":"P1"}
{"ts":"2026-03-31T14:30:11.500Z","evt":"verify","result":"match_3","holder_before":"[R R B _ _ _ _]","holder_after":"[B _ _ _ _ _ _]"}
{"ts":"2026-03-31T14:30:45.000Z","evt":"level_end","result":"win","level":42,"taps":23,"duration_sec":40,"matches":8}
{"ts":"2026-03-31T14:31:00.000Z","evt":"screen","type":"win","confidence":0.98,"source":"yolo"}
```

#### 5.3.2 Timestamp 동기화

```python
class TimestampSync:
    """디바이스 간 타임스탬프 동기화.

    각 디바이스는 세션 시작 시 NTP 서버와 동기화하고,
    오프셋을 기록하여 중앙 집계 시 보정한다.
    """
    def __init__(self):
        self.ntp_offset_ms = 0

    def sync_with_ntp(self):
        """NTP 서버와 시간 동기화. 오프셋 계산."""
        import ntplib
        c = ntplib.NTPClient()
        response = c.request('pool.ntp.org', version=3)
        self.ntp_offset_ms = int(response.offset * 1000)

    def get_synced_timestamp(self) -> str:
        """NTP 보정된 ISO 타임스탬프."""
        import datetime
        now = datetime.datetime.utcnow()
        corrected = now + datetime.timedelta(milliseconds=self.ntp_offset_ms)
        return corrected.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
```

#### 5.3.3 Episode 분할

```
에피소드 = 1회의 게임 플레이 (lobby → gameplay → win/fail → lobby)

분할 기준:
  START: lobby → gameplay 전이
  END: gameplay/win/fail → lobby 전이 (또는 앱 크래시)
  TIMEOUT: gameplay 5분 이상 변화 없으면 강제 종료

  세션 구조:
  session/
    ├── session_meta.json     (세션 전체 메타)
    ├── session_log.jsonl     (전체 이벤트 로그)
    ├── episodes/
    │   ├── ep_001.json       (에피소드 요약)
    │   ├── ep_002.json
    │   └── ...
    └── frames/
        ├── f_0001.png        (이벤트 프레임)
        ├── f_0002.jpg        (샘플 프레임)
        └── ...
```

---

## 6. Human Play Database Schema

### 6.1 설계 원칙

인간 플레이 데이터를 체계적으로 저장하여 AI의 Pattern Matching과 Reverse Engineering에 활용한다.

```
설계 목표:
  1. 세션 → 에피소드 → 턴 → 액션 4계층 구조
  2. State Hash 기반 패턴 매칭 (동일 상태에서의 다른 행동 비교)
  3. 게임 프로파일 축적 (레벨별 통계, BM 이벤트, UI 흐름)
  4. 분석 캐시 (자주 쿼리되는 집계 결과 사전 계산)
```

### 6.2 Full SQL Schema

```sql
-- ============================================================
-- 1. device: 물리/가상 디바이스 정보
-- ============================================================
CREATE TABLE device (
    device_id       TEXT PRIMARY KEY,                    -- 'dev_001'
    hostname        TEXT NOT NULL,                       -- 물리 머신 호스트명
    emulator_type   TEXT NOT NULL DEFAULT 'bluestacks',  -- bluestacks, ldplayer, memu
    emulator_port   INTEGER NOT NULL DEFAULT 5554,       -- ADB 포트
    screen_width    INTEGER NOT NULL DEFAULT 1080,
    screen_height   INTEGER NOT NULL DEFAULT 1920,
    cpu_cores       INTEGER DEFAULT 4,
    ram_mb          INTEGER DEFAULT 4096,
    status          TEXT NOT NULL DEFAULT 'idle',        -- idle, playing, error, offline
    last_heartbeat  TIMESTAMP,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_device_status ON device(status);

-- ============================================================
-- 2. game_profile: 게임별 프로파일 (역공학 결과 축적)
-- ============================================================
CREATE TABLE game_profile (
    game_id         TEXT PRIMARY KEY,                    -- 'carmatch'
    package_name    TEXT UNIQUE NOT NULL,                -- 'com.grandgames.carmatch'
    game_name       TEXT NOT NULL,                       -- 'Car Match'
    genre           TEXT NOT NULL DEFAULT 'unknown',     -- puzzle_match, idle_rpg, ...
    version_code    INTEGER,
    version_name    TEXT,

    -- 역공학 추출 결과 (JSONB)
    screen_flow_graph   TEXT,                            -- JSON: 화면 전이 그래프
    ui_taxonomy         TEXT,                            -- JSON: UI 컴포넌트 분류
    bm_analysis         TEXT,                            -- JSON: BM 분석 결과
    economy_model       TEXT,                            -- JSON: 리소스 경제 모델
    difficulty_curve    TEXT,                            -- JSON: 레벨별 난이도

    total_sessions  INTEGER NOT NULL DEFAULT 0,
    total_episodes  INTEGER NOT NULL DEFAULT 0,
    total_wins      INTEGER NOT NULL DEFAULT 0,
    total_fails     INTEGER NOT NULL DEFAULT 0,

    yolo_model_path TEXT,                               -- YOLO 모델 파일 경로
    yolo_accuracy   REAL DEFAULT 0.0,                   -- YOLO 정확도

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- 3. session: 플레이 세션 (앱 시작 ~ 종료)
-- ============================================================
CREATE TABLE session (
    session_id      TEXT PRIMARY KEY,                    -- 's_20260331_143000_dev001'
    device_id       TEXT NOT NULL REFERENCES device(device_id),
    game_id         TEXT NOT NULL REFERENCES game_profile(game_id),
    player_type     TEXT NOT NULL DEFAULT 'ai',          -- 'human', 'ai'
    persona         TEXT DEFAULT 'default',              -- 'casual', 'whale', 'grinder'

    started_at      TIMESTAMP NOT NULL,
    ended_at        TIMESTAMP,
    duration_sec    INTEGER,

    episodes_count  INTEGER NOT NULL DEFAULT 0,
    wins            INTEGER NOT NULL DEFAULT 0,
    fails           INTEGER NOT NULL DEFAULT 0,
    total_taps      INTEGER NOT NULL DEFAULT 0,
    total_turns     INTEGER NOT NULL DEFAULT 0,

    -- VLM 사용 통계
    vlm_calls       INTEGER NOT NULL DEFAULT 0,
    vlm_cost_usd    REAL NOT NULL DEFAULT 0.0,
    yolo_calls      INTEGER NOT NULL DEFAULT 0,
    opencv_calls    INTEGER NOT NULL DEFAULT 0,

    -- 세션 메타
    log_path        TEXT,                               -- session_log.jsonl 경로
    frames_dir      TEXT,                               -- 프레임 저장 디렉토리

    status          TEXT NOT NULL DEFAULT 'running',    -- running, completed, crashed
    error_message   TEXT,

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_session_game ON session(game_id, started_at DESC);
CREATE INDEX idx_session_device ON session(device_id, started_at DESC);
CREATE INDEX idx_session_status ON session(status);

-- ============================================================
-- 4. episode: 1회 게임 플레이 (lobby → gameplay → result → lobby)
-- ============================================================
CREATE TABLE episode (
    episode_id      TEXT PRIMARY KEY,                    -- 'ep_s20260331_001'
    session_id      TEXT NOT NULL REFERENCES session(session_id),
    game_id         TEXT NOT NULL REFERENCES game_profile(game_id),
    episode_seq     INTEGER NOT NULL,                    -- 세션 내 순번 (1, 2, 3...)

    level_number    INTEGER,                             -- 게임 내 레벨 번호
    level_hash      TEXT,                                -- 레벨 시작 상태 해시

    started_at      TIMESTAMP NOT NULL,
    ended_at        TIMESTAMP,
    duration_sec    INTEGER,

    result          TEXT,                                -- 'win', 'fail', 'abandon', 'crash'
    fail_reason     TEXT,                                -- 'outofspace', 'timeout', 'crash'

    total_turns     INTEGER NOT NULL DEFAULT 0,
    total_taps      INTEGER NOT NULL DEFAULT 0,
    total_matches   INTEGER NOT NULL DEFAULT 0,
    undo_used       INTEGER NOT NULL DEFAULT 0,
    magnet_used     INTEGER NOT NULL DEFAULT 0,
    max_holder      INTEGER NOT NULL DEFAULT 0,          -- 홀더 최대 사용 수

    -- 보상/구매 이벤트
    coins_earned    INTEGER DEFAULT 0,
    iap_prompted    BOOLEAN DEFAULT FALSE,
    ad_shown_count  INTEGER DEFAULT 0,

    -- 시작 스크린샷 (레벨 레이아웃)
    start_frame     TEXT,                                -- 프레임 파일 경로
    end_frame       TEXT,                                -- 결과 화면 프레임

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_episode_session ON episode(session_id, episode_seq);
CREATE INDEX idx_episode_level ON episode(game_id, level_number);
CREATE INDEX idx_episode_result ON episode(game_id, result);

-- ============================================================
-- 5. turn: 1턴 (perceive → decide → execute → verify)
-- ============================================================
CREATE TABLE turn (
    turn_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id      TEXT NOT NULL REFERENCES episode(episode_id),
    turn_seq        INTEGER NOT NULL,                    -- 에피소드 내 순번

    -- Perception 결과
    screen_type     TEXT NOT NULL,
    perception_source TEXT NOT NULL DEFAULT 'yolo',      -- yolo, opencv, vlm
    perception_ms   INTEGER,                             -- 인식 소요 시간
    confidence      REAL,

    -- Board 상태 (gameplay)
    holder_state    TEXT,                                -- JSON: ["red","red","blue",null,...]
    holder_count    INTEGER,
    active_cars_count INTEGER,
    state_hash      TEXT,                                -- 상태 해시 (패턴 매칭용)

    -- Decision 결과
    decision_priority TEXT,                              -- P0, P1, P2, ...
    decision_reason TEXT,

    -- Execution
    action_type     TEXT NOT NULL,                       -- tap, back, wait, relaunch
    action_x        INTEGER,
    action_y        INTEGER,
    action_wait_ms  INTEGER,

    -- Verification
    verify_result   TEXT,                                -- match_3, car_moved, no_change, screen_changed
    holder_after    TEXT,                                -- JSON: 액션 후 홀더 상태
    holder_count_after INTEGER,

    timestamp       TIMESTAMP NOT NULL,

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_turn_episode ON turn(episode_id, turn_seq);
CREATE INDEX idx_turn_state_hash ON turn(state_hash);
CREATE INDEX idx_turn_screen ON turn(screen_type);
CREATE INDEX idx_turn_decision ON turn(decision_priority);

-- ============================================================
-- 6. action: 개별 ADB 명령 (1턴에 여러 액션 가능)
-- ============================================================
CREATE TABLE action (
    action_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id         INTEGER NOT NULL REFERENCES turn(turn_id),
    action_seq      INTEGER NOT NULL,                    -- 턴 내 순번

    action_type     TEXT NOT NULL,                       -- tap, back, wait, relaunch
    x               INTEGER,
    y               INTEGER,
    wait_ms         INTEGER,
    reason          TEXT,

    -- 실행 결과
    executed_at     TIMESTAMP NOT NULL,
    success         BOOLEAN DEFAULT TRUE,
    error_message   TEXT,

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_action_turn ON action(turn_id, action_seq);

-- ============================================================
-- 7. level_snapshot: 레벨 시작 상태 스냅샷 (레벨 설계 역공학)
-- ============================================================
CREATE TABLE level_snapshot (
    snapshot_id     TEXT PRIMARY KEY,
    game_id         TEXT NOT NULL REFERENCES game_profile(game_id),
    level_number    INTEGER NOT NULL,
    attempt_count   INTEGER NOT NULL DEFAULT 1,          -- 같은 레벨 몇 번째 시도

    -- 보드 상태 (JSON)
    board_layout    TEXT,                                -- 차량 배치, 장애물 등
    car_count       INTEGER,
    color_distribution TEXT,                             -- JSON: {"red":5,"blue":4,...}
    stack_info      TEXT,                                -- JSON: 스택 정보

    -- 난이도 추정
    estimated_difficulty REAL,                           -- 0.0~1.0
    min_moves_estimated INTEGER,                         -- 최소 이동 수 추정
    holder_slots    INTEGER DEFAULT 7,
    match_count     INTEGER DEFAULT 3,

    -- 결과 통계 (반복 플레이로 축적)
    total_attempts  INTEGER NOT NULL DEFAULT 0,
    total_wins      INTEGER NOT NULL DEFAULT 0,
    avg_taps_to_win REAL,
    avg_duration_sec REAL,

    frame_path      TEXT,                                -- 스냅샷 이미지 경로
    state_hash      TEXT,                                -- 레벨 상태 해시

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_snapshot_level ON level_snapshot(game_id, level_number);
CREATE UNIQUE INDEX idx_snapshot_hash ON level_snapshot(game_id, state_hash);

-- ============================================================
-- 8. pattern: 발견된 행동 패턴 (Human Play → AI 학습)
-- ============================================================
CREATE TABLE pattern (
    pattern_id      TEXT PRIMARY KEY,
    game_id         TEXT NOT NULL REFERENCES game_profile(game_id),
    pattern_type    TEXT NOT NULL,                       -- 'screen_handler', 'gameplay_rule',
                                                        -- 'timing', 'sequence'

    -- 패턴 조건
    trigger_screen  TEXT,                                -- 이 화면에서
    trigger_state   TEXT,                                -- JSON: 이 상태일 때
    state_hash      TEXT,                                -- 상태 해시

    -- 패턴 행동
    action_sequence TEXT NOT NULL,                       -- JSON: 실행할 액션 시퀀스
    avg_interval_ms INTEGER,                             -- 평균 액션 간격

    -- 통계
    observed_count  INTEGER NOT NULL DEFAULT 0,
    success_count   INTEGER NOT NULL DEFAULT 0,
    confidence      REAL NOT NULL DEFAULT 0.0,           -- success/observed

    -- 출처
    source          TEXT NOT NULL DEFAULT 'human',       -- 'human', 'ai', 'swarm'
    source_sessions TEXT,                                -- JSON: 관찰된 세션 ID 목록

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pattern_game ON pattern(game_id, pattern_type);
CREATE INDEX idx_pattern_trigger ON pattern(trigger_screen, state_hash);
CREATE INDEX idx_pattern_confidence ON pattern(confidence DESC);

-- ============================================================
-- 9. analytics_cache: 사전 계산된 분석 결과 캐시
-- ============================================================
CREATE TABLE analytics_cache (
    cache_key       TEXT PRIMARY KEY,                    -- 'carmatch:level_curve:v3'
    game_id         TEXT NOT NULL REFERENCES game_profile(game_id),
    cache_type      TEXT NOT NULL,                       -- 'level_curve', 'bm_events',
                                                        -- 'screen_flow', 'economy'

    data_json       TEXT NOT NULL,                       -- JSON: 분석 결과
    data_version    INTEGER NOT NULL DEFAULT 1,
    episodes_included INTEGER NOT NULL DEFAULT 0,        -- 계산에 포함된 에피소드 수

    computed_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP,                           -- 캐시 만료 시각
    is_stale        BOOLEAN NOT NULL DEFAULT FALSE       -- 새 데이터 유입 시 TRUE
);

CREATE INDEX idx_cache_game ON analytics_cache(game_id, cache_type);

-- ============================================================
-- 10. bm_event: BM (Business Model) 이벤트 추적
-- ============================================================
CREATE TABLE bm_event (
    event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id      TEXT NOT NULL REFERENCES episode(episode_id),
    game_id         TEXT NOT NULL REFERENCES game_profile(game_id),

    event_type      TEXT NOT NULL,                       -- 'iap_prompt', 'ad_shown',
                                                        -- 'reward_ad', 'paywall',
                                                        -- 'difficulty_spike', 'energy_gate'
    event_subtype   TEXT,                                -- 상세 유형

    -- 컨텍스트
    trigger_screen  TEXT,                                -- 어떤 화면에서
    trigger_level   INTEGER,                             -- 어떤 레벨에서
    trigger_condition TEXT,                              -- JSON: 트리거 조건
    player_state    TEXT,                                -- JSON: 플레이어 상태 (코인, 레벨 등)

    -- 프레임
    frame_path      TEXT,                                -- 스크린샷 경로

    timestamp       TIMESTAMP NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_bm_game ON bm_event(game_id, event_type);
CREATE INDEX idx_bm_episode ON bm_event(episode_id);
CREATE INDEX idx_bm_level ON bm_event(game_id, trigger_level);

-- ============================================================
-- VIEWS: 자주 사용하는 집계 쿼리
-- ============================================================

-- 레벨별 클리어율
CREATE VIEW v_level_clear_rate AS
SELECT
    e.game_id,
    e.level_number,
    COUNT(*) as total_attempts,
    SUM(CASE WHEN e.result = 'win' THEN 1 ELSE 0 END) as wins,
    ROUND(
        CAST(SUM(CASE WHEN e.result = 'win' THEN 1 ELSE 0 END) AS REAL)
        / COUNT(*), 3
    ) as clear_rate,
    ROUND(AVG(e.duration_sec), 1) as avg_duration,
    ROUND(AVG(e.total_taps), 1) as avg_taps,
    ROUND(AVG(e.total_matches), 1) as avg_matches
FROM episode e
WHERE e.level_number IS NOT NULL
GROUP BY e.game_id, e.level_number
ORDER BY e.game_id, e.level_number;

-- 화면별 인식 정확도
CREATE VIEW v_perception_accuracy AS
SELECT
    t.screen_type,
    t.perception_source,
    COUNT(*) as total,
    ROUND(AVG(t.confidence), 3) as avg_confidence,
    ROUND(AVG(t.perception_ms), 1) as avg_latency_ms
FROM turn t
GROUP BY t.screen_type, t.perception_source
ORDER BY t.screen_type;

-- BM 이벤트 빈도 (레벨별)
CREATE VIEW v_bm_frequency AS
SELECT
    b.game_id,
    b.event_type,
    b.trigger_level,
    COUNT(*) as occurrences,
    COUNT(DISTINCT b.episode_id) as unique_episodes
FROM bm_event b
GROUP BY b.game_id, b.event_type, b.trigger_level
ORDER BY b.game_id, b.trigger_level, occurrences DESC;

-- 세션별 요약
CREATE VIEW v_session_summary AS
SELECT
    s.session_id,
    s.game_id,
    s.device_id,
    s.player_type,
    s.duration_sec,
    s.episodes_count,
    s.wins,
    s.fails,
    ROUND(CAST(s.wins AS REAL) / NULLIF(s.episodes_count, 0), 3) as win_rate,
    s.total_taps,
    ROUND(CAST(s.total_taps AS REAL) / NULLIF(s.episodes_count, 0), 1) as taps_per_game,
    s.vlm_calls,
    s.vlm_cost_usd,
    s.yolo_calls
FROM session s
ORDER BY s.started_at DESC;
```

### 6.3 State Hash 설계

State Hash는 동일한 게임 상태를 빠르게 검색하기 위한 해시값이다:

```python
import hashlib
import json

def compute_state_hash(
    screen_type: str,
    holder: list,
    active_cars_summary: dict,
    level_number: int = None,
) -> str:
    """게임 상태 해시 계산.

    동일 상태 = 동일 해시 → 패턴 매칭에 사용.
    좌표는 무시 (매번 다르므로), 색상 구성만 사용.

    Args:
        screen_type: 화면 유형
        holder: 홀더 상태 ["red", "blue", None, ...]
        active_cars_summary: {"red":3, "blue":2, "unknown":1}
        level_number: 레벨 번호 (알 수 있으면)
    """
    state = {
        "screen": screen_type,
        "holder": sorted([h for h in holder if h is not None]),
        "holder_count": sum(1 for h in holder if h is not None),
        "cars": sorted(active_cars_summary.items()),
    }
    if level_number is not None:
        state["level"] = level_number

    canonical = json.dumps(state, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
```

### 6.4 Data Lifecycle

```
데이터 수명주기:
┌──────────────────────────────────────────────────────────┐
│ Phase 1: Hot (0~24시간)                                   │
│   위치: 디바이스 로컬 SSD                                   │
│   내용: 원본 프레임 + session_log.jsonl + JSON 메타         │
│   용량: ~3GB/device/day                                   │
│   목적: 실시간 분석, 디버깅                                  │
├──────────────────────────────────────────────────────────┤
│ Phase 2: Warm (1~30일)                                    │
│   위치: 중앙 서버 DB + 네트워크 드라이브                      │
│   내용: 이벤트 프레임(압축) + 구조화 데이터(DB rows)          │
│   용량: ~500MB/device/day (원본 대비 85% 절감)              │
│   목적: 패턴 분석, 역공학, 리포트 생성                       │
├──────────────────────────────────────────────────────────┤
│ Phase 3: Cold (30일+)                                     │
│   위치: 아카이브 스토리지 (클라우드 or 외장)                   │
│   내용: JSON 데이터만 (프레임 삭제)                          │
│   용량: ~50MB/device/day (원본 대비 98% 절감)               │
│   목적: 장기 트렌드 분석, 감사                               │
├──────────────────────────────────────────────────────────┤
│ Phase 4: Purge (90일+)                                    │
│   turn, action 테이블 row 삭제                             │
│   episode, analytics_cache 유지                           │
│   bm_event, pattern 영구 보존                             │
└──────────────────────────────────────────────────────────┘
```

```sql
-- Data lifecycle 자동화 SQL
-- Phase 2: Hot → Warm (24시간 경과)
UPDATE session SET status = 'archived_warm'
WHERE status = 'completed'
  AND ended_at < datetime('now', '-1 day');

-- Phase 3: Warm → Cold (30일 경과, 프레임 삭제 마킹)
UPDATE session SET status = 'archived_cold'
WHERE status = 'archived_warm'
  AND ended_at < datetime('now', '-30 days');

-- Phase 4: Purge (90일 경과)
DELETE FROM action WHERE turn_id IN (
    SELECT t.turn_id FROM turn t
    JOIN episode e ON t.episode_id = e.episode_id
    JOIN session s ON e.session_id = s.session_id
    WHERE s.ended_at < datetime('now', '-90 days')
);
DELETE FROM turn WHERE episode_id IN (
    SELECT e.episode_id FROM episode e
    JOIN session s ON e.session_id = s.session_id
    WHERE s.ended_at < datetime('now', '-90 days')
);
```

---

## 7. AI Decision Engine

### 7.1 Safety Rules (Playbook)

Playbook은 게임별 "절대 규칙"을 하드코딩한 모듈이다. AI가 자율적으로 변경할 수 없다.

#### 7.1.1 Playbook 구조

```python
@dataclass
class Playbook:
    game_id: str
    genre: str

    # 화면별 고정 핸들러 (gameplay 제외)
    screen_handlers: Dict[str, ScreenHandler]

    # 좌표 제약
    board_region: Tuple[int, int, int, int]     # 게임 보드 영역
    holder_region: Tuple[int, int, int, int]    # 홀더 영역
    forbidden_regions: List[Tuple[int,int,int,int]]  # 절대 탭 금지

    # 부스터 좌표
    boosters: Dict[str, Tuple[int, int]]

    # 위험 임계값
    holder_warning: int = 4
    holder_danger: int = 5
    holder_critical: int = 6

    # 실패 에스컬레이션
    max_consecutive_fails: int = 3
    max_total_fails: int = 5
```

#### 7.1.2 장르별 TO DO / TO DON'T

**Puzzle Match (CarMatch, Pixel Flow 등)**:
```
TO DO:
  - P0: gameplay 아닌 화면 → 해당 핸들러 실행
  - P1: 홀더에 같은 색 2개 → 보드에서 3번째 찾아 탭
  - P2: 홀더 5칸+ → Undo
  - P3: 홀더에 같은 색 있는 차 탭 (부분 매칭)
  - P4: 앞줄 활성 차 아무거나 탭
  - P5: Mystery(?) → 홀더 3칸 이하일 때만

TO DON'T:
  - 랜덤으로 아무 차나 탭하지 마라
  - 비활성(blocked) 차를 탭하지 마라
  - Shuffle/Rotate를 사용하지 마라
  - 금지 영역(부스터 바 하단)을 탭하지 마라
  - 구매 버튼(Purchase, Buy, $, ₩)을 탭하지 마라
```

**Idle RPG**:
```
TO DO:
  - 자동 전투 활성화
  - 일정 간격으로 스킬 사용
  - 보상 팝업 수집
  - 장비 업그레이드 순환

TO DON'T:
  - 유료 가챠를 당기지 마라
  - PvP 매칭을 하지 마라
  - 길드 관련 기능을 건드리지 마라
```

**Merge Game**:
```
TO DO:
  - 같은 등급 아이템 2개 → 머지
  - 빈 칸에 새 아이템 생성
  - 높은 등급 아이템 우선 머지

TO DON'T:
  - 최고 등급 아이템을 머지하지 마라
  - 보드가 가득 차기 전에 새 아이템 생성하지 마라
```

### 7.2 Pattern Matching from Human Play DB

#### 7.2.1 State Hash 기반 검색

```python
class PatternMatcher:
    """Human Play DB에서 현재 상태와 유사한 패턴 검색."""

    def find_patterns(
        self, state_hash: str, screen_type: str, db_conn
    ) -> list:
        """현재 상태 해시로 패턴 검색.

        검색 순서:
          1. Exact match: 동일 state_hash
          2. Fuzzy match: 같은 screen_type + 유사 holder_count
          3. Genre default: 장르 기본 패턴
        """
        # 1. Exact match
        patterns = db_conn.execute("""
            SELECT * FROM pattern
            WHERE state_hash = ? AND confidence >= 0.5
            ORDER BY confidence DESC LIMIT 5
        """, (state_hash,)).fetchall()

        if patterns:
            return patterns

        # 2. Fuzzy match
        patterns = db_conn.execute("""
            SELECT * FROM pattern
            WHERE trigger_screen = ? AND confidence >= 0.3
            ORDER BY observed_count DESC, confidence DESC LIMIT 10
        """, (screen_type,)).fetchall()

        return patterns
```

#### 7.2.2 Similarity Search (Fuzzy)

```python
def compute_state_similarity(state_a: dict, state_b: dict) -> float:
    """두 게임 상태의 유사도 (0.0 ~ 1.0).

    구성 요소별 가중 유사도:
      - screen_type: 동일이면 1.0, 아니면 0.0 (weight: 0.3)
      - holder_count 차이: 작을수록 높음 (weight: 0.3)
      - color_distribution: 코사인 유사도 (weight: 0.3)
      - level_number: 동일이면 1.0, 5 이내면 0.5 (weight: 0.1)
    """
    score = 0.0

    # Screen type
    if state_a["screen"] == state_b["screen"]:
        score += 0.3

    # Holder count
    diff = abs(state_a["holder_count"] - state_b["holder_count"])
    score += 0.3 * max(0, 1 - diff / 7)

    # Color distribution cosine similarity
    all_colors = set(state_a["cars"].keys()) | set(state_b["cars"].keys())
    if all_colors:
        vec_a = [state_a["cars"].get(c, 0) for c in all_colors]
        vec_b = [state_b["cars"].get(c, 0) for c in all_colors]
        dot = sum(a*b for a,b in zip(vec_a, vec_b))
        norm_a = sum(a*a for a in vec_a) ** 0.5
        norm_b = sum(b*b for b in vec_b) ** 0.5
        if norm_a > 0 and norm_b > 0:
            score += 0.3 * (dot / (norm_a * norm_b))

    # Level number
    if state_a.get("level") and state_b.get("level"):
        level_diff = abs(state_a["level"] - state_b["level"])
        if level_diff == 0:
            score += 0.1
        elif level_diff <= 5:
            score += 0.05

    return score
```

#### 7.2.3 Confidence Scoring

```python
def calculate_pattern_confidence(
    observed: int, success: int,
    recency_weight: float = 0.1,
    days_since_last: int = 0,
) -> float:
    """패턴 신뢰도 계산.

    Wilson Score Interval (하한) 사용:
    적은 관찰 수에서의 과도한 확신을 방지.

    Args:
        observed: 관찰 횟수
        success: 성공 횟수
        recency_weight: 최근성 가중치
        days_since_last: 마지막 관찰 이후 경과 일수
    """
    import math

    if observed == 0:
        return 0.0

    p = success / observed
    z = 1.96  # 95% 신뢰구간

    # Wilson Score 하한
    denominator = 1 + z*z / observed
    center = (p + z*z / (2*observed)) / denominator
    spread = z * math.sqrt(p*(1-p)/observed + z*z/(4*observed*observed)) / denominator
    wilson_lower = center - spread

    # 최근성 감쇠
    recency_factor = math.exp(-recency_weight * days_since_last)

    return max(0.0, min(1.0, wilson_lower * recency_factor))
```

### 7.3 Lookahead Simulation

#### 7.3.1 보드 상태 시뮬레이션

```python
# tester/lookahead.py의 핵심 시뮬레이션 로직
def _simulate_tap(self, car, holder):
    """차 1대를 탭했을 때의 결과 시뮬레이션.

    CarMatch 규칙:
    1. 차를 탭하면 홀더에 해당 색상 추가
    2. 같은 색 3개 모이면 제거
    3. 홀더 7칸 다 차면 게임 오버
    """
    new_holder = holder[:]
    color = car.color

    # 홀더에 추가
    for i in range(self.holder_slots):
        if new_holder[i] is None:
            new_holder[i] = color
            break
    else:
        return SimResult(car=car, score=-200, ...)  # OVERFLOW

    # 매칭 체크 (3개 같은 색 → 제거)
    color_count = sum(1 for h in new_holder if h == color)
    if color_count >= self.match_count:
        # 제거 후 compact
        removed = 0
        for i in range(self.holder_slots):
            if new_holder[i] == color and removed < self.match_count:
                new_holder[i] = None
                removed += 1
        new_holder = self._compact_holder(new_holder)

    return SimResult(car=car, score=self._calculate_score(...), ...)
```

#### 7.3.2 Scoring Weights

```python
# 기본 가중치 (사람이 설정, Swarm이 미세 조정)
DEFAULT_WEIGHTS = {
    "match_completion": 100,    # 매칭 완성 → 최우선
    "match_2_setup": 30,        # 2/3 준비 상태 → 높은 가치
    "new_color_safe": 10,       # 새 색상, 여유 있음 → OK
    "new_color_danger": -50,    # 새 색상, 홀더 위험 → 피하기
    "holder_overflow": -200,    # 게임 오버 → 절대 금지
    "mystery_safe": 5,          # Mystery, 여유 있음 → 약간 OK
    "mystery_danger": -100,     # Mystery, 위험 → 금지
    "front_row_bonus": 5,       # 앞줄 차 → 약간 보너스
    "stacked_penalty": -3,      # 스택 높은 차 → 약간 페널티
}
```

#### 7.3.3 Depth-limited Search

```python
class DeepLookahead(LookaheadSimulator):
    """2수 앞까지 보는 확장 시뮬레이터.

    1수: 모든 가능한 탭 평가
    2수: 상위 K개 후보에 대해 다시 1수 시뮬레이션
    총점: 1수_score + 2수_best_score * discount
    """

    def __init__(self, top_k: int = 5, depth2_discount: float = 0.5):
        self.top_k = top_k
        self.depth2_discount = depth2_discount

    def get_best_move_deep(self, board, holder):
        first_moves = self.evaluate_all_moves(board, holder)
        best_total = float("-inf")
        best_result = None

        for move1 in first_moves[:self.top_k]:  # 상위 5개만
            total_score = move1.score

            # 이 차를 탭한 후 남은 차 중 최선은?
            remaining = [c for c in board.active_cars
                        if not (c.x == move1.car.x and c.y == move1.car.y)]
            if remaining:
                virtual_board = BoardState(
                    screen_type="gameplay",
                    holder=move1.holder_after,
                    active_cars=remaining,
                )
                second_moves = self.evaluate_all_moves(virtual_board, move1.holder_after)
                if second_moves:
                    total_score += second_moves[0].score * self.depth2_discount

            if total_score > best_total:
                best_total = total_score
                best_result = move1  # 1수째 결과에 2수 고려 반영
        return best_result
```

### 7.4 Exploration vs Exploitation

#### 7.4.1 Epsilon-Greedy with Decay

```python
class ExplorationPolicy:
    """탐험 vs 활용 균형 정책.

    초기: 높은 epsilon → 다양한 행동 시도 (탐험)
    학습 후: 낮은 epsilon → 최선의 행동 선택 (활용)
    """

    def __init__(
        self,
        epsilon_start: float = 0.3,
        epsilon_min: float = 0.05,
        decay_rate: float = 0.995,  # 에피소드마다 곱해짐
    ):
        self.epsilon = epsilon_start
        self.epsilon_min = epsilon_min
        self.decay_rate = decay_rate
        self.episodes_played = 0

    def should_explore(self) -> bool:
        """탐험할지 결정."""
        import random
        return random.random() < self.epsilon

    def decay(self):
        """에피소드 종료 시 epsilon 감쇠."""
        self.episodes_played += 1
        self.epsilon = max(
            self.epsilon_min,
            self.epsilon * self.decay_rate
        )

    def get_exploration_action(self, board) -> 'Action':
        """탐험 행동 생성.

        완전한 랜덤이 아님 -- 안전한 범위 내에서의 랜덤:
        - 활성 차 중 랜덤 선택 (forbidden 제외)
        - 또는 아직 탭하지 않은 영역 시도
        """
        import random
        safe_cars = [c for c in board.active_cars
                    if not c.is_mystery and c.y > 300]
        if safe_cars:
            car = random.choice(safe_cars)
            return Action("tap", car.x, car.y, 1.5,
                         f"EXPLORE: random safe car ({car.color})")
        return Action("wait", wait=2.0, reason="EXPLORE: no safe target")
```

#### 7.4.2 Unknown State 처리

```python
def handle_unknown_state(board, memory, experience_db):
    """처음 보는 화면/상태에서의 행동 결정.

    전략:
    1. ExperienceDB에서 유사 화면 검색
    2. 유사 패턴이 있으면 → 그 행동 시도
    3. 없으면 → 안전한 탐색 행동 수행
    """
    # 1. ExperienceDB에서 이 screen_type의 best action 검색
    best = experience_db.get_best_action(board.screen_type)
    if best:
        x, y, confidence = best
        if confidence >= 0.7:
            return [Action("tap", x, y, 1.5,
                          f"EXP_DB: {board.screen_type} ({confidence:.0%})")]

    # 2. 안전한 탐색 시퀀스
    return [
        Action("back", wait=1.0, reason=f"UNKNOWN: try back ({board.screen_type})"),
        Action("tap", 540, 960, 1.0, "UNKNOWN: center tap fallback"),
    ]
```

### 7.5 3-Stage Hybrid Pipeline

Decision Engine은 Safety → Pattern → Lookahead의 3단계 파이프라인으로 동작한다:

```
Stage 1: Safety Rules (Playbook)
  ├── P0: 비-gameplay 화면 핸들러 → 즉시 실행
  ├── P-CRITICAL: 홀더 6칸+ → Undo
  ├── P1: 매칭 완성 가능 → 즉시 실행
  └── 위험 상황 아니면 → Stage 2로

Stage 2: Pattern Matching (ExperienceDB / Human Play DB)
  ├── state_hash로 exact match 검색
  ├── fuzzy match (유사 상태)
  ├── confidence >= 0.7 → 해당 패턴 실행
  └── 매칭 없거나 confidence 낮으면 → Stage 3로

Stage 3: Lookahead Simulation
  ├── 모든 가능한 탭 시뮬레이션
  ├── 2수 앞 탐색 (top-5 후보)
  ├── 최고 점수 행동 선택
  └── 동점이면 앞줄 + 비스택 우선
```

```python
class HybridDecisionEngine:
    """3-Stage 하이브리드 Decision Engine."""

    def __init__(self, playbook, pattern_matcher, lookahead, exploration_policy):
        self.playbook = playbook
        self.pattern_matcher = pattern_matcher
        self.lookahead = lookahead
        self.exploration = exploration_policy

    def decide(self, board, memory):
        # Stage 0: Exploration check
        if self.exploration.should_explore():
            return [self.exploration.get_exploration_action(board)]

        # Stage 1: Safety Rules
        safety_actions = self._check_safety(board, memory)
        if safety_actions:
            return safety_actions

        # Stage 2: Pattern Matching
        state_hash = compute_state_hash(board)
        patterns = self.pattern_matcher.find_patterns(state_hash, board.screen_type)
        if patterns and patterns[0].confidence >= 0.7:
            return self._execute_pattern(patterns[0])

        # Stage 3: Lookahead Simulation
        best = self.lookahead.get_best_move_deep(board, memory.holder_colors)
        if best and best.score > -50:  # 안전한 행동만
            return [Action("tap", best.car.x, best.car.y, 1.5,
                          f"LOOKAHEAD: {best.reason} (score={best.score:.0f})")]

        # Fallback
        return [Action("wait", wait=2.0, reason="NO_OPTION: wait for re-perceive")]
```

---

## 8. Reverse Engineering Module

### 8.1 BM (Business Model) Analysis

역공학의 궁극적 목표는 게임의 수익 구조를 자동으로 분석하는 것이다.

#### 8.1.1 IAP Trigger Detection

```python
class IAPTriggerDetector:
    """IAP 구매 유도 타이밍 감지.

    감지 대상:
    - 레벨 실패 직후 구매 프롬프트
    - 리소스 부족 시 구매 유도
    - 특별 할인 팝업 (시간 제한)
    - 보상형 광고 대안 제시
    """

    # IAP 관련 키워드 (OCR로 감지)
    IAP_KEYWORDS = [
        "purchase", "buy", "shop", "deal", "offer",
        "special", "limited", "sale", "discount",
        "$", "₩", "USD", "KRW",
        "99", "1.99", "4.99", "9.99",  # 일반적 가격대
        "gems", "diamonds", "coins", "gold",
        "no ads", "remove ads", "ad free",
    ]

    def detect_iap_trigger(
        self,
        current_screen: str,
        previous_screens: list,
        level_number: int,
        fail_count: int,
        session_duration_sec: int,
    ) -> dict:
        """IAP 트리거 조건 분석.

        Returns:
            {
                "trigger_type": "post_fail" | "resource_gate" | "time_offer" | "energy_gate",
                "trigger_condition": "failed 3 times on level 42",
                "urgency_signals": ["limited time", "discount"],
                "price_detected": "$4.99",
                "alternative_offered": "watch_ad",
            }
        """
        if current_screen in ("shop", "popup") and "fail" in previous_screens[-3:]:
            return {
                "trigger_type": "post_fail",
                "trigger_condition": f"failed {fail_count}x on level {level_number}",
            }
        return None

    def analyze_iap_frequency(self, db_conn, game_id: str) -> dict:
        """IAP 프롬프트 빈도 분석.

        Returns:
            {
                "prompts_per_session": 3.2,
                "prompts_per_fail": 0.8,
                "avg_level_between_prompts": 5,
                "peak_prompt_levels": [10, 25, 50, 100],
                "post_fail_prompt_rate": 0.65,
            }
        """
        results = db_conn.execute("""
            SELECT
                e.level_number,
                COUNT(*) as prompt_count,
                COUNT(DISTINCT e.episode_id) as episodes
            FROM bm_event b
            JOIN episode e ON b.episode_id = e.episode_id
            WHERE b.game_id = ? AND b.event_type = 'iap_prompt'
            GROUP BY e.level_number
            ORDER BY e.level_number
        """, (game_id,)).fetchall()
        return self._build_frequency_report(results)
```

#### 8.1.2 Currency Flow Tracking

```python
class CurrencyTracker:
    """게임 내 화폐 흐름 추적.

    OCR + 상태 비교로 화폐 변동을 추적한다.
    """

    def track_currency_change(self, before_frame, after_frame, action_performed):
        """액션 전후의 화폐 변동 감지.

        Returns:
            [
                {
                    "currency": "coins",
                    "before": 1500,
                    "after": 1650,
                    "delta": +150,
                    "trigger": "level_win",
                },
            ]
        """
        before_values = self._ocr_currency_regions(before_frame)
        after_values = self._ocr_currency_regions(after_frame)

        changes = []
        for currency, before_val in before_values.items():
            after_val = after_values.get(currency)
            if after_val and after_val != before_val:
                changes.append({
                    "currency": currency,
                    "before": before_val,
                    "after": after_val,
                    "delta": after_val - before_val,
                    "trigger": action_performed,
                })
        return changes if changes else None

    def compute_economy_model(self, db_conn, game_id: str) -> dict:
        """게임 경제 모델 추출.

        Returns:
            {
                "currencies": ["coins", "gems", "hearts"],
                "earn_rates": {
                    "coins": {"per_level_win": 150, "per_ad_watch": 50},
                    "gems": {"per_level_win": 0, "per_ad_watch": 5},
                },
                "spend_rates": {
                    "coins": {"per_booster": 100, "per_extra_moves": 200},
                    "gems": {"per_heart_refill": 10},
                },
                "earn_spend_ratio": {
                    "coins": 1.2,   # 약간 수입>지출 (지속 가능)
                    "gems": 0.3,    # 수입<<지출 (IAP 유도)
                },
            }
        """
        pass  # DB에서 currency flow 집계
```

#### 8.1.3 Paywall Detection

```python
class PaywallDetector:
    """난이도 급상승 + 구매 유도 = Paywall 패턴 감지."""

    def detect_paywall(self, db_conn, game_id: str) -> list:
        """Paywall 후보 레벨 감지.

        Paywall 패턴 = 난이도 급상승 + IAP 프롬프트 증가

        탐지 알고리즘:
        1. 레벨별 클리어율 계산
        2. 연속 3레벨 이상 클리어율 < 30% → 난이도 스파이크
        3. 해당 구간에서 IAP 프롬프트 빈도 > 평균 2x → Paywall 확정
        """
        # 레벨별 클리어율
        levels = db_conn.execute("""
            SELECT level_number,
                   CAST(SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) AS REAL)
                   / COUNT(*) as clear_rate,
                   COUNT(*) as attempts
            FROM episode
            WHERE game_id = ? AND level_number IS NOT NULL
            GROUP BY level_number
            HAVING attempts >= 3
            ORDER BY level_number
        """, (game_id,)).fetchall()

        paywalls = []
        for i in range(len(levels) - 2):
            l1, l2, l3 = levels[i], levels[i+1], levels[i+2]
            if all(l[1] < 0.3 for l in [l1, l2, l3]):  # clear_rate < 30%
                # 이 구간의 IAP 프롬프트 빈도
                iap_count = db_conn.execute("""
                    SELECT COUNT(*) FROM bm_event
                    WHERE game_id = ? AND trigger_level BETWEEN ? AND ?
                    AND event_type = 'iap_prompt'
                """, (game_id, l1[0], l3[0])).fetchone()[0]

                if iap_count > 0:
                    paywalls.append({
                        "start_level": l1[0],
                        "end_level": l3[0],
                        "avg_clear_rate": (l1[1] + l2[1] + l3[1]) / 3,
                        "iap_prompt_count": iap_count,
                        "confidence": "high" if iap_count >= 3 else "medium",
                    })

        return paywalls
```

#### 8.1.4 Ad Frequency Analysis

```python
def analyze_ad_placement(db_conn, game_id: str) -> dict:
    """광고 배치 분석.

    Returns:
        {
            "total_ads_shown": 150,
            "ads_per_session_avg": 5.0,
            "ad_timing": {
                "post_level_complete": 0.6,  # 60%가 레벨 완료 후
                "post_fail": 0.25,           # 25%가 실패 후
                "interstitial": 0.15,        # 15%가 무작위
            },
            "ad_interval_avg_sec": 180,      # 평균 3분마다
            "rewarded_ad_rate": 0.4,         # 40%가 보상형 광고
            "ad_skip_available_sec": 5,      # 5초 후 스킵 가능
        }
    """
    pass
```

### 8.2 Data Table Reconstruction

#### 8.2.1 Level Difficulty Curve Extraction

```python
class DifficultyAnalyzer:
    """레벨 난이도 커브 추출."""

    def extract_difficulty_curve(self, db_conn, game_id: str) -> dict:
        """레벨별 난이도 데이터 추출.

        데이터 소스:
        - 클리어율 (clear_rate)
        - 평균 탭 수 (avg_taps)
        - 평균 소요 시간 (avg_duration)
        - 부스터 사용률 (booster_rate)
        - 재시도 횟수 (retry_count)
        """
        data = db_conn.execute("""
            SELECT
                level_number,
                COUNT(*) as attempts,
                SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins,
                AVG(total_taps) as avg_taps,
                AVG(duration_sec) as avg_duration,
                AVG(undo_used + magnet_used) as avg_boosters,
                AVG(max_holder) as avg_max_holder
            FROM episode
            WHERE game_id = ? AND level_number IS NOT NULL
            GROUP BY level_number
            ORDER BY level_number
        """, (game_id,)).fetchall()

        curve = []
        for row in data:
            clear_rate = row[2] / row[1] if row[1] > 0 else 0
            difficulty = 1 - clear_rate
            # 복합 난이도 (여러 지표 종합)
            composite = (
                0.4 * difficulty +
                0.2 * min(row[3] / 100, 1.0) +
                0.2 * min(row[4] / 300, 1.0) +
                0.2 * min(row[5] / 3, 1.0)
            )
            curve.append({
                "level": row[0],
                "clear_rate": round(clear_rate, 3),
                "difficulty_composite": round(composite, 3),
                "avg_taps": round(row[3], 1),
                "avg_duration_sec": round(row[4], 1),
                "attempts": row[1],
            })

        return {
            "game_id": game_id,
            "levels": curve,
            "difficulty_spikes": self._find_spikes(curve),
        }
```

#### 8.2.2 Drop Rate Estimation

```python
class DropRateEstimator:
    """반복 플레이로 아이템 드롭률 추정.

    특정 레벨을 N번 반복 플레이하여, 드롭 아이템의
    출현 빈도로 확률 테이블을 역추정한다.
    """

    MIN_SAMPLES = 30  # 최소 샘플 수 (통계적 유의미)

    def estimate_drop_rates(self, observations: list) -> dict:
        """관찰 데이터에서 드롭률 추정.

        Args:
            observations: [{"level":42, "drop":"rare_item", "count":3, "total":100}]

        Returns:
            {
                "rare_item": {
                    "estimated_rate": 0.03,
                    "confidence_interval": (0.006, 0.086),
                    "samples": 100,
                },
            }
        """
        from scipy import stats as scipy_stats

        results = {}
        for obs in observations:
            n = obs["total"]
            k = obs["count"]
            if n < self.MIN_SAMPLES:
                continue

            rate = k / n
            # Beta 분포 기반 신뢰구간 (Bayesian)
            alpha = k + 1  # 사전 Beta(1,1) = uniform
            beta_param = n - k + 1
            ci_low = scipy_stats.beta.ppf(0.025, alpha, beta_param)
            ci_high = scipy_stats.beta.ppf(0.975, alpha, beta_param)

            results[obs["drop"]] = {
                "estimated_rate": round(rate, 4),
                "confidence_interval": (round(ci_low, 4), round(ci_high, 4)),
                "samples": n,
            }

        return results
```

### 8.3 Game Architecture Inference

#### 8.3.1 Screen Flow Graph

```python
class ScreenFlowExtractor:
    """화면 전이 그래프 자동 생성.

    관찰된 화면 전이를 State Machine으로 모델링.
    """

    def extract_flow_graph(self, db_conn, game_id: str) -> dict:
        """화면 전이 그래프 추출.

        Returns:
            {
                "nodes": ["lobby", "gameplay", "win", "fail", "popup", "ad", "shop"],
                "edges": [
                    {"from": "lobby", "to": "gameplay", "count": 150, "probability": 0.85},
                    {"from": "gameplay", "to": "win", "count": 80, "probability": 0.53},
                    ...
                ],
                "entry_point": "lobby",
                "cycles": [["lobby","gameplay","win","lobby"], ...],
            }
        """
        transitions = db_conn.execute("""
            SELECT
                t1.screen_type as from_screen,
                t2.screen_type as to_screen,
                COUNT(*) as transition_count
            FROM turn t1
            JOIN turn t2 ON t1.episode_id = t2.episode_id
                AND t2.turn_seq = t1.turn_seq + 1
            JOIN episode e ON t1.episode_id = e.episode_id
            WHERE e.game_id = ?
                AND t1.screen_type != t2.screen_type
            GROUP BY t1.screen_type, t2.screen_type
            ORDER BY transition_count DESC
        """, (game_id,)).fetchall()

        nodes = set()
        edges = []
        from_counts = {}

        for row in transitions:
            nodes.add(row[0])
            nodes.add(row[1])
            from_counts[row[0]] = from_counts.get(row[0], 0) + row[2]
            edges.append({
                "from": row[0],
                "to": row[1],
                "count": row[2],
            })

        # 전이 확률 계산
        for edge in edges:
            total = from_counts.get(edge["from"], 1)
            edge["probability"] = round(edge["count"] / total, 3)

        return {
            "nodes": sorted(nodes),
            "edges": edges,
            "entry_point": self._detect_entry(edges),
        }
```

#### 8.3.2 Tutorial Flow Extraction

```python
class TutorialExtractor:
    """튜토리얼 흐름 자동 추출.

    초기 레벨(1~5)에서의 특수 이벤트를 감지:
    - 강제 가이드 (특정 위치만 탭 가능)
    - 텍스트 팝업 (게임 설명)
    - 하이라이트 (특정 UI 요소 강조)
    - 비정상적으로 쉬운 레벨 (클리어율 95%+)
    """

    def extract_tutorial(self, db_conn, game_id: str) -> dict:
        """튜토리얼 구조 추출.

        Returns:
            {
                "tutorial_levels": [1, 2, 3, 4, 5],
                "tutorial_type": "progressive",
                "steps": [
                    {"level": 1, "forced_taps": 3, "popup_count": 2,
                     "teaches": "basic_tap"},
                    {"level": 2, "forced_taps": 1, "popup_count": 1,
                     "teaches": "matching"},
                ],
                "tutorial_end_level": 5,
                "difficulty_jump_after_tutorial": 0.35,
            }
        """
        pass
```

---

## 9. Distributed Device Management

### 9.1 Device Fleet Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Central Server                              │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────────┐       │
│  │ Task Queue   │ │ DB (SQLite/  │ │ Analytics Engine │       │
│  │ (Redis)      │ │ PostgreSQL)  │ │                  │       │
│  └──────┬──────┘ └──────────────┘ └──────────────────┘       │
│         │                                                      │
│         │ HTTP API (task assign / result collect)               │
└─────────┼──────────────────────────────────────────────────────┘
          │
    ┌─────┼──────────────────────────────────────────┐
    │     │         Physical Machine 1                │
    │  ┌──┴──┐ ┌──────┐ ┌──────┐ ┌──────┐           │
    │  │Task │ │ BS-1 │ │ BS-2 │ │ BS-3 │           │
    │  │Agent│ │:5554 │ │:5556 │ │:5558 │           │
    │  └─────┘ └──────┘ └──────┘ └──────┘           │
    │           dev_001   dev_002   dev_003           │
    └────────────────────────────────────────────────┘
    ┌────────────────────────────────────────────────┐
    │         Physical Machine 2                      │
    │  ┌─────┐ ┌──────┐ ┌──────┐ ┌──────┐           │
    │  │Task │ │ BS-4 │ │ BS-5 │ │ BS-6 │           │
    │  │Agent│ │:5554 │ │:5556 │ │:5558 │           │
    │  └─────┘ └──────┘ └──────┘ └──────┘           │
    │           dev_004   dev_005   dev_006           │
    └────────────────────────────────────────────────┘
```

#### 9.1.1 Task Distribution

```python
class TaskDistributor:
    """디바이스에 작업 분배.

    분배 전략:
    - Round-robin: 기본 (균등 분배)
    - Level-aware: 레벨 범위별 분배 (겹치지 않게)
    - Priority: 미탐색 레벨 우선
    """

    def assign_tasks(self, devices: list, game_id: str, total_levels: int) -> dict:
        """디바이스별 작업 할당.

        Returns:
            {
                "dev_001": {"game": "carmatch", "level_range": (1, 50), "mode": "play"},
                "dev_002": {"game": "carmatch", "level_range": (51, 100), "mode": "play"},
                "dev_003": {"game": "carmatch", "level_range": (1, 30), "mode": "replay"},
            }
        """
        n = len(devices)
        levels_per_device = total_levels // n
        assignments = {}

        for i, device in enumerate(devices):
            start = i * levels_per_device + 1
            end = (i + 1) * levels_per_device if i < n-1 else total_levels
            assignments[device] = {
                "game": game_id,
                "level_range": (start, end),
                "mode": "play",
            }

        return assignments
```

#### 9.1.2 Health Monitoring

```python
class DeviceHealthMonitor:
    """디바이스 상태 모니터링.

    모니터링 항목:
    - ADB 연결 상태
    - 에뮬레이터 프로세스 상태
    - 게임 앱 실행 상태
    - 성능 지표 (FPS, 메모리)
    """

    HEARTBEAT_INTERVAL_SEC = 30
    CRASH_DETECTION_TIMEOUT_SEC = 120
    MAX_CONSECUTIVE_ERRORS = 5

    def check_device(self, device_id: str) -> dict:
        """디바이스 상태 체크."""
        status = {
            "device_id": device_id,
            "adb_connected": self._check_adb(device_id),
            "emulator_running": self._check_emulator(device_id),
            "game_foreground": self._check_game_foreground(device_id),
            "last_screenshot_age_sec": self._get_last_screenshot_age(device_id),
        }

        # 크래시 감지: 마지막 스크린샷이 2분 이상 전이면 의심
        if status["last_screenshot_age_sec"] > self.CRASH_DETECTION_TIMEOUT_SEC:
            status["suspected_crash"] = True
            self._attempt_recovery(device_id)

        return status

    def _attempt_recovery(self, device_id: str):
        """크래시 복구 시도.

        복구 순서:
        1. 게임 강제 종료 + 재시작
        2. ADB 재연결
        3. 에뮬레이터 재시작
        """
        pass  # 순차적 복구 시도
```

### 9.2 Data Aggregation

#### 9.2.1 Edge → Central Pipeline

```
디바이스 → 중앙 데이터 흐름:

  Device (Edge)                       Central Server
  ┌─────────────┐                    ┌──────────────────┐
  │ session_log  │ ──── HTTP POST ──→│ /api/v1/events   │
  │   .jsonl     │     (batch, gzip) │                  │
  │              │                    │ ┌──────────────┐ │
  │ event frames │ ──── HTTP POST ──→│ │ Event Router │ │
  │   .jpg/.png  │     (multipart)   │ │              │ │
  │              │                    │ │ ├→ DB Insert │ │
  │ periodic     │                    │ │ ├→ Frame     │ │
  │ health check │ ←── HTTP GET ────│ │ │  Storage   │ │
  │              │     (heartbeat)    │ │ └→ Analytics │ │
  └─────────────┘                    │ │    Trigger  │ │
                                      │ └──────────────┘ │
                                      └──────────────────┘
```

#### 9.2.2 Conflict Resolution

```python
class ConflictResolver:
    """같은 레벨을 여러 디바이스에서 플레이한 결과 병합.

    정책:
    - 동일 레벨, 다른 디바이스 → 모든 결과 보존 (통계적 가치)
    - 동일 레벨, 동일 결과 → 첫 번째만 유지 (중복 제거)
    - 충돌하는 메타 데이터 → 다수결 또는 최신 우선
    """

    def merge_level_data(self, level_number: int, device_results: list) -> dict:
        """여러 디바이스의 레벨 결과 병합."""
        merged = {
            "level_number": level_number,
            "total_attempts": sum(r["attempts"] for r in device_results),
            "total_wins": sum(r["wins"] for r in device_results),
            "devices_tested": len(device_results),
            "clear_rate": sum(r["wins"] for r in device_results)
                         / max(sum(r["attempts"] for r in device_results), 1),
        }
        return merged
```

### 9.3 Storage Strategy

#### 9.3.1 3-Tier Storage

```
┌─────────────────────────────────────────────────────────┐
│ Hot Storage (SSD, 로컬)                                  │
│ 보존 기간: 0~24시간                                       │
│ 내용: 원본 프레임 + JSONL + 임시 데이터                     │
│ 용량/디바이스: ~3GB/day                                   │
│ 접근: 실시간 (ms 단위)                                    │
├─────────────────────────────────────────────────────────┤
│ Warm Storage (네트워크 드라이브, 압축)                      │
│ 보존 기간: 1~30일                                         │
│ 내용: 이벤트 프레임(JPEG) + DB rows + 분석 캐시            │
│ 용량/디바이스: ~500MB/day                                 │
│ 접근: 초 단위                                             │
├─────────────────────────────────────────────────────────┤
│ Cold Storage (아카이브, 클라우드)                           │
│ 보존 기간: 30~90일                                        │
│ 내용: JSON 메타만 (프레임 삭제)                             │
│ 용량/디바이스: ~50MB/day                                  │
│ 접근: 분 단위                                             │
└─────────────────────────────────────────────────────────┘
```

#### 9.3.2 Total Capacity Planning Formula

```
일일 데이터 생산량 (device 1대, 8시간 플레이):

  Hot  = screenshots + logs + temp
       = (3600*8 * 2MB * 0.055) + (event_count * 1KB) + temp
       ≈ 3.2GB + 0.5MB + 0.3GB
       ≈ 3.5 GB/device/day

  Warm = event_frames + db_rows + cache
       = (200*8 * 80KB) + (turns * 0.5KB) + analytics
       ≈ 128MB + 50MB + 10MB
       ≈ 190 MB/device/day

  Cold = json_meta_only
       = session_meta + episode_meta + pattern_data
       ≈ 50 MB/device/day

총 용량 계획 (N devices, D days):
  Hot:  N * 3.5GB * 1day (롤링)
  Warm: N * 190MB * 30days
  Cold: N * 50MB * 60days

예시: 10 devices, 90일 운영:
  Hot:  10 * 3.5GB    =    35 GB
  Warm: 10 * 190MB * 30 =   57 GB
  Cold: 10 * 50MB * 60  =   30 GB
  ─────────────────────────────
  Total:                   122 GB
```

---

## 10. Self-Improvement Loop

### 10.1 Swarm 4-Agent Cycle

본 시스템의 자기 개선은 4개의 AI Agent가 순환하며 수행한다:

```
┌──────────────────────────────────────────────────────────┐
│                   Swarm Cycle (1회 = ~75분)                │
│                                                            │
│  Phase 1: Player (60분)                                    │
│  ├── 게임 플레이 실행                                       │
│  ├── session_log.jsonl 생성                                │
│  └── session_report.json 출력                              │
│       │                                                    │
│       ▼                                                    │
│  Phase 2: Analyst (5분)                                    │
│  ├── 로그 분석 + 실패 패턴 식별                               │
│  ├── ExperienceDB 통계 참조                                │
│  ├── Reflector 반성 프롬프트 생성                             │
│  └── analysis_report.json 출력                             │
│       │                                                    │
│       ▼                                                    │
│  Phase 3: Improver (5분)                                   │
│  ├── 분석 결과 + 미적용 교훈 읽기                              │
│  ├── playbook.py / decision.py 수정안 생성                  │
│  ├── staging/ 디렉토리에 수정 파일 배치                       │
│  └── change_manifest.json 출력                             │
│       │                                                    │
│       ▼                                                    │
│  Phase 4: Validator (5분)                                  │
│  ├── 변경사항 안전성 검토                                    │
│  ├── 승인/거부 결정                                         │
│  ├── 승인된 변경만 live 코드에 적용                           │
│  └── validation_result.json 출력                           │
│       │                                                    │
│       └── → Phase 1로 반복                                 │
└──────────────────────────────────────────────────────────┘
```

### 10.2 Play Result → Pattern Confidence Update

```python
def update_pattern_from_play(db_conn, episode_result: dict, turns: list):
    """플레이 결과로 패턴 confidence 업데이트.

    에피소드가 win이면:
      해당 에피소드에서 사용된 모든 패턴의 success +1
    에피소드가 fail이면:
      해당 에피소드에서 사용된 패턴 중
      마지막 5턴의 패턴만 fail +1 (실패 원인은 끝부분)
    """
    result = episode_result["result"]

    if result == "win":
        for turn in turns:
            if turn.get("state_hash"):
                db_conn.execute("""
                    UPDATE pattern
                    SET observed_count = observed_count + 1,
                        success_count = success_count + 1,
                        confidence = CAST(success_count + 1 AS REAL)
                                    / (observed_count + 1),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE state_hash = ?
                """, (turn["state_hash"],))

    elif result == "fail":
        fail_turns = turns[-5:]
        for turn in fail_turns:
            if turn.get("state_hash"):
                db_conn.execute("""
                    UPDATE pattern
                    SET observed_count = observed_count + 1,
                        confidence = CAST(success_count AS REAL)
                                    / (observed_count + 1),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE state_hash = ?
                """, (turn["state_hash"],))
```

### 10.3 Weight Optimization Schedule

```python
class WeightOptimizer:
    """Lookahead 가중치 자동 최적화.

    Bayesian Optimization으로 가중치를 미세 조정.
    사람이 초기값 설정 → Swarm이 미세 조정.
    """

    # 가중치 허용 범위 (안전 제약)
    WEIGHT_BOUNDS = {
        "match_completion": (50, 200),
        "match_2_setup": (10, 80),
        "new_color_safe": (0, 30),
        "new_color_danger": (-100, -10),
        "holder_overflow": (-500, -100),
        "mystery_safe": (0, 20),
        "mystery_danger": (-200, -30),
        "front_row_bonus": (0, 20),
        "stacked_penalty": (-10, 0),
    }

    def optimize_step(self, current_weights: dict, recent_results: list) -> dict:
        """1스텝 최적화.

        전략: 현재 가중치에서 1개만 변경하고 결과 비교.
        """
        import random

        current_win_rate = sum(
            1 for r in recent_results if r["result"] == "win"
        ) / max(len(recent_results), 1)

        # 가장 영향력 큰 가중치 선택
        target_key = random.choice(list(self.WEIGHT_BOUNDS.keys()))

        # 작은 변동 적용
        new_weights = current_weights.copy()
        low, high = self.WEIGHT_BOUNDS[target_key]
        delta = (high - low) * 0.1  # 범위의 10%
        new_weights[target_key] = max(low, min(high,
            current_weights[target_key] + random.uniform(-delta, delta)
        ))

        return new_weights
```

### 10.4 Convergence Metrics

```python
class ConvergenceTracker:
    """학습 수렴 추적.

    수렴 판단 기준:
    - 클리어율 변동 < 5% (최근 10 사이클)
    - 패턴 DB 신규 추가 < 1개/사이클
    - 가중치 변동 < 1%
    """

    def is_converged(self, history: list) -> bool:
        if len(history) < 10:
            return False

        recent = history[-10:]
        win_rates = [h["win_rate"] for h in recent]

        # 클리어율 변동
        mean = sum(win_rates) / len(win_rates)
        variance = sum((x - mean) ** 2 for x in win_rates) / len(win_rates)
        win_rate_std = variance ** 0.5
        if win_rate_std > 0.05:
            return False

        # 패턴 DB 성장률
        pattern_growth = [h["new_patterns"] for h in recent]
        if sum(pattern_growth) / len(pattern_growth) > 1.0:
            return False

        return True
```

---

## 11. Evaluation Framework

### 11.1 핵심 메트릭

| Metric | 정의 | 목표 | 측정 주기 |
|--------|------|------|---------|
| **Clear Rate** | 레벨 클리어 성공률 | 60%+ (casual) | 에피소드 단위 |
| **Action Similarity** | 인간 플레이와의 행동 유사도 | 70%+ | 턴 단위 |
| **Pattern Coverage** | 발견된 게임 화면/상태 비율 | 90%+ | 세션 단위 |
| **Extraction Accuracy** | 역공학 데이터의 정확도 | 80%+ | 수동 검증 |
| **Perception Accuracy** | 화면 인식 정확도 | 95%+ | 턴 단위 |
| **VLM Fallback Rate** | VLM 사용 비율 (낮을수록 좋음) | <5% | 세션 단위 |
| **Latency P95** | 인식~실행 95%ile 지연 | <500ms | 턴 단위 |
| **Cost per Hour** | 시간당 VLM 비용 | <$0.10 | 세션 단위 |

### 11.2 A/B Experiment Design

```python
class ABExperiment:
    """Decision Engine A/B 테스트.

    같은 게임, 같은 레벨 범위를 두 가지 전략으로 플레이하고
    성능을 비교한다.
    """

    def run_experiment(
        self,
        game_id: str,
        level_range: tuple,
        strategy_a: str,  # "rule_only"
        strategy_b: str,  # "rule_plus_lookahead"
        episodes_per_arm: int = 50,
    ) -> dict:
        """A/B 실험 실행.

        Returns:
            {
                "arm_a": {
                    "strategy": "rule_only",
                    "episodes": 50,
                    "win_rate": 0.54,
                    "avg_taps": 28.3,
                    "avg_duration_sec": 45.2,
                },
                "arm_b": {
                    "strategy": "rule_plus_lookahead",
                    "episodes": 50,
                    "win_rate": 0.62,
                    "avg_taps": 25.1,
                    "avg_duration_sec": 42.8,
                },
                "p_value": 0.038,
                "significant": True,
                "winner": "arm_b",
                "improvement": "+8%p clear rate",
            }
        """
        pass
```

### 11.3 Baseline Comparisons

```
Baseline 1: Random Agent
  - 활성 차 중 완전 랜덤 탭
  - 기대 클리어율: 5~15% (장르 의존)

Baseline 2: Rule-only Agent (현재 Decision)
  - P0~P5 고정 규칙만 사용
  - 기대 클리어율: 40~60%

Baseline 3: Rule + Lookahead (현재 최선)
  - P0~P5 + 2-depth 시뮬레이션
  - 기대 클리어율: 50~70%

Baseline 4: Human Play
  - 숙련된 인간 테스터
  - 기대 클리어율: 70~90%

Target: Baseline 3 → Baseline 4 수준 (Swarm 학습 후)
```

---

## 12. Implementation Roadmap

### Phase 1: Core Pipeline (완료)

**기간**: 4주
**상태**: COMPLETED

| Deliverable | 파일 | 상태 |
|------------|------|------|
| ADB 연결 + 스크린샷 | `adb/commands.py`, `tester/runner.py` | Done |
| Claude Vision 인식 | `tester/perception.py` | Done |
| 5-Layer 아키텍처 | `tester/decision.py`, `memory.py`, `executor.py` | Done |
| Playbook (CarMatch) | `tester/playbook.py` | Done |
| 기본 실행기 | `tester/runner.py` | Done |
| YOLO 수집/학습 파이프라인 | `tester/yolo_collector.py` | Done |
| YOLO classify 모델 | `data/games/carmatch/yolo_dataset/` | Done |

### Phase 2: Intelligence Layer (완료)

**기간**: 3주
**상태**: COMPLETED

| Deliverable | 파일 | 상태 |
|------------|------|------|
| Lookahead Simulator | `tester/lookahead.py` | Done |
| DeepLookahead (2수) | `tester/lookahead.py` | Done |
| Decision V2 (Lookahead 통합) | `tester/decision_v2.py` | Done |
| Human Demo Recorder | `tester/demo_recorder.py` | Done |
| Learning Engine V2 | `tester/learning_engine.py` | Done |
| Learned Decision | `tester/learned_decision.py` | Done |

### Phase 3: Self-Improvement (완료)

**기간**: 3주
**상태**: COMPLETED

| Deliverable | 파일 | 상태 |
|------------|------|------|
| Swarm Orchestrator | `tester/swarm/orchestrator.py` | Done |
| 4 Agent Roles | `tester/swarm/roles.py` | Done |
| ExperienceDB | `tester/swarm/experience_db.py` | Done |
| Reflector | `tester/swarm/reflector.py` | Done |

### Phase 4: Multi-Game + Reverse Engineering (진행 중)

**기간**: 6주 (예상)
**상태**: IN PROGRESS

| Deliverable | 파일 | 상태 |
|------------|------|------|
| Genre profiles (7종) | `tester/genres/` | Partial |
| Pixel Flow 지원 | `tester/decision_pixelflow.py` | Done |
| Universal Runner | `tester/universal_runner.py` | Done |
| BM Analysis Module | (신규) | TODO |
| Difficulty Curve Extractor | (신규) | TODO |
| Screen Flow Graph | (신규) | TODO |
| Currency Tracker | (신규) | TODO |
| Paywall Detector | (신규) | TODO |

### Phase 5: Distributed Fleet + Production (계획)

**기간**: 8주 (예상)
**상태**: PLANNED

| Deliverable | 파일 | 상태 |
|------------|------|------|
| Central DB (PostgreSQL) | (신규) | TODO |
| Device Fleet Manager | (신규) | TODO |
| Edge Processing Agent | (신규) | TODO |
| Event Streaming API | (신규) | TODO |
| Health Monitor Dashboard | (신규) | TODO |
| Data Lifecycle Automation | (신규) | TODO |
| Analytics Report Generator | (신규) | TODO |

### Phase 의존성 그래프

```
Phase 1 ──→ Phase 2 ──→ Phase 3
  │              │              │
  │              └──→ Phase 4 ──┤
  │                             │
  └─────────────────→ Phase 5 ──┘
```

---

## 13. Risk Analysis

### 13.1 기술 리스크

| # | Risk | Impact | Probability | Mitigation |
|---|------|--------|------------|------------|
| R1 | VLM 인식 오류로 잘못된 탭 | High | Medium | 3-tier fallback + 실패 탭 기록 + 재인식 |
| R2 | 게임 업데이트로 UI 변경 | High | High | YOLO 재학습 파이프라인 자동화, 템플릿 버전 관리 |
| R3 | ADB 연결 불안정 | Medium | Medium | 자동 재연결, 에뮬레이터 재시작, health monitor |
| R4 | VLM API 비용 초과 | Medium | Low | YOLO 우선 사용으로 VLM <5%, 비용 알림 설정 |
| R5 | 에뮬레이터 성능 저하 | Medium | Medium | 주기적 에뮬레이터 재시작, 메모리 정리 |
| R6 | 광고 차단 실패 (무한 루프) | Medium | High | 광고 에스컬레이션 (Phase1→2→3→relaunch) |
| R7 | 하트/에너지 고갈 | Low | High | 하트 대기 모드 (R2 규칙), 다른 게임으로 전환 |
| R8 | TB-scale 디스크 용량 부족 | High | Medium | 3-tier storage + lifecycle automation |
| R9 | 게임사의 Bot Detection | High | Low | 인간 유사 터치 (jitter, delay), 페르소나 다양화 |
| R10 | Swarm의 코드 파괴적 변경 | Critical | Low | Validator Agent + staging + safety rules |

### 13.2 운영 리스크

| # | Risk | Mitigation |
|---|------|------------|
| O1 | 새 게임 장르의 Playbook 부재 | GenreProfile 기본 규칙으로 안전한 탐색부터 시작 |
| O2 | 인식 정확도 저하 (장기 운영) | 주기적 YOLO 재학습, confidence 모니터링 |
| O3 | DB 성능 저하 (데이터 축적) | 인덱스 최적화, 파티셔닝, lifecycle purge |
| O4 | 다국어 게임 텍스트 인식 실패 | 기본 영어/숫자 OCR + VLM 멀티링귀얼 fallback |
| O5 | 에뮬레이터 라이선스 문제 | 무료 에뮬레이터(LDPlayer) 우선, 대안 매핑 |

### 13.3 완화 전략 상세

**R6 (광고 무한 루프) 완화 -- 이미 구현됨:**

```python
# decision.py의 _handle_ad() 실제 구현
def _handle_ad(self, memory):
    attempts = memory.popup_escape_attempts

    if attempts <= 3:
        # Phase 1: 대기 후 BACK
        return [Action("wait", wait=5.0), Action("back", wait=1.0)]

    elif attempts <= 8:
        # Phase 2: X 위치 순차 스캔 (10곳)
        x_positions = [
            (1050, 30), (1040, 60), (1050, 100),
            (30, 30), (50, 60), (1020, 150),
            (30, 100), (540, 1850), (980, 1850), (100, 1850),
        ]
        idx = ((attempts - 4) * 2) % len(x_positions)
        return [Action("wait", wait=3.0),
                Action("tap", *x_positions[idx], 0.5),
                Action("back", wait=1.0)]

    else:
        # Phase 3: 포기 → 앱 재시작
        memory.popup_escape_attempts = 0
        return [Action("relaunch", wait=5.0)]
```

**R10 (Swarm 파괴적 변경) 완화:**

```
Safety Rules for Improver Agent:
  1. 기존 screen_handler 삭제 금지 (추가만 가능)
  2. forbidden_region 축소 금지 (확대만 가능)
  3. threshold 변경 시 +/- 1 step만
  4. 확실하지 않으면 변경하지 않기

Validator Agent 검증:
  1. 모든 변경사항 코드 리뷰
  2. 10분 테스트 실행
  3. 성능 저하 시 즉시 거부
  4. 원칙: "의심스러우면 거부(REJECT)"
```

---

## Appendix A: File Structure

```
E:\AI\virtual_player\                    # 프로젝트 루트
├── __init__.py                          # 패키지 초기화
├── __main__.py                          # 메인 엔트리포인트 (범용 플레이어)
├── config.py                            # 전역 설정 (경로, ADB, 기본값)
├── player.py                            # 범용 플레이어 클래스
├── play_engine.py                       # 플레이 엔진 V1
├── play_engine_v2.py                    # 플레이 엔진 V2 (개선판)
├── state_machine.py                     # 게임 상태 머신
├── input_strategy.py                    # 입력 전략 (터치 패턴)
├── screen_action_resolver.py            # 화면→액션 매핑
├── episode_recorder.py                  # 에피소드 녹화
├── outcome_tracker.py                   # 결과 추적
├── recorder.py                          # 범용 레코더
├── overnight_runner.py                  # 야간 자동 실행
├── overnight_carmatch.py                # CarMatch 야간 실행
│
├── adapters/                            # 어댑터 (게임 인터페이스)
│   ├── base.py                          # 기본 어댑터
│   ├── adb_adapter.py                   # ADB 어댑터
│   └── web_2048.py                      # 웹 2048 어댑터
│
├── adaptive/                            # 적응형 학습
│   ├── failure_memory.py                # 실패 기억
│   ├── loop_detector.py                 # 루프 감지
│   ├── plan_adapter.py                  # 계획 적응
│   └── spatial_memory.py                # 공간 기억
│
├── adb/                                 # ADB 명령어
│   └── commands.py                      # ADB 래퍼 함수
│
├── bootstrap/                           # 게임 부트스트랩 (초기 설정)
│   ├── auto_profile_builder.py          # 자동 프로파일 생성
│   ├── genre_detector.py                # 장르 자동 감지
│   ├── launch_manager.py                # 앱 실행 관리
│   ├── profile_builder.py               # 프로파일 빌더
│   └── screen_fingerprinter.py          # 화면 지문
│
├── brain/                               # AI 두뇌 (의사결정)
│   ├── base.py                          # 기본 브레인
│   ├── brain_2048.py                    # 2048 전용
│   ├── local_vision.py                  # 로컬 비전
│   ├── reference_db.py                  # 참조 DB
│   └── vision_brain.py                  # 비전 브레인
│
├── bt/                                  # Behavior Tree
│   ├── auto_bootstrap.py                # 자동 부트스트랩
│   ├── curriculum.py                    # 커리큘럼
│   ├── nodes.py                         # BT 노드
│   ├── tree_builder.py                  # 트리 빌더
│   └── vision_api.py                    # Vision API 래퍼
│
├── discovery/                           # UI 탐색 엔진
│   ├── discovery_db.py                  # 발견 DB (화면 요소, 전이)
│   ├── exploration_engine.py            # 탐색 엔진
│   └── safety_guard.py                  # 안전 가드
│
├── genre/                               # 장르 스키마
│   ├── schema.py                        # 기본 스키마
│   ├── game_profile.py                  # 게임 프로파일
│   ├── casual_schema.py                 # 캐주얼 게임
│   ├── puzzle_schema.py                 # 퍼즐 게임
│   ├── merge_schema.py                  # 머지 게임
│   ├── idle_schema.py                   # 방치형 게임
│   ├── rpg_schema.py                    # RPG
│   ├── simulation_schema.py             # 시뮬레이션
│   └── setup_wizard.py                  # 설정 마법사
│
├── tester/                              # AI 테스터 핵심 (5-Layer)
│   ├── __main__.py                      # 테스터 엔트리
│   ├── runner.py                        # 5-Layer 통합 실행기
│   ├── runner_pixelflow.py              # PixelFlow 전용 실행기
│   ├── universal_runner.py              # 범용 실행기
│   ├── universal_vision.py              # 범용 비전
│   │
│   ├── perception.py                    # Layer 1: Perception (눈)
│   ├── memory.py                        # Layer 2: Memory (기억)
│   ├── decision.py                      # Layer 3: Decision (판단)
│   ├── decision_v2.py                   # Layer 3: Decision V2 (Lookahead)
│   ├── decision_pixelflow.py            # Layer 3: PixelFlow 전용
│   ├── generic_decision.py              # Layer 3: 범용 Decision
│   ├── executor.py                      # Layer 4+5: Execution + Verify
│   ├── playbook.py                      # Playbook (TO DO / TO DON'T)
│   ├── playbook_pixelflow.py            # PixelFlow Playbook
│   ├── playbook_generator.py            # Playbook 자동 생성
│   ├── lookahead.py                     # Lookahead Simulator
│   │
│   ├── auto_play.py                     # 자동 플레이
│   ├── demo_recorder.py                 # 인간 플레이 녹화
│   ├── demo_analyzer.py                 # 데모 분석
│   ├── learning_engine.py               # Learning Engine V2
│   ├── learned_decision.py              # 학습된 Decision
│   ├── learning_runner.py               # 학습 실행기
│   ├── vision_trainer.py                # Vision 학습기
│   │
│   ├── yolo_collector.py                # YOLO 데이터 수집기
│   ├── yolo_detector.py                 # YOLO 감지기 (차량/홀더)
│   │
│   ├── genres/                          # 장르별 전략
│   │   ├── base.py                      # GenreProfile 기본 클래스
│   │   ├── puzzle_match.py              # 퍼즐 매치
│   │   ├── idle_rpg.py                  # 방치형 RPG
│   │   ├── card_battle.py               # 카드 배틀
│   │   ├── runner_platformer.py         # 러너/플랫포머
│   │   ├── simulation.py                # 시뮬레이션
│   │   ├── tower_defense.py             # 타워 디펜스
│   │   └── loader.py                    # 장르 로더
│   │
│   ├── personas/                        # 플레이어 페르소나
│   │   ├── base.py                      # 기본 페르소나
│   │   └── presets.py                   # 프리셋 (캐주얼, 하드코어 등)
│   │
│   └── swarm/                           # 자기 개선 Swarm
│       ├── orchestrator.py              # Swarm 오케스트레이터
│       ├── roles.py                     # 4 Agent Roles
│       ├── experience_db.py             # 영구 경험 DB
│       └── reflector.py                 # 자기 반성 (Reflexion)
│
├── reasoning/                           # 추론 엔진
│   ├── combat_controller.py             # 전투 제어
│   ├── goal_library.py                  # 목표 라이브러리
│   ├── goal_reasoner.py                 # 목표 추론
│   ├── goap_planner.py                  # GOAP 플래너
│   ├── puzzle_solver.py                 # 퍼즐 솔버
│   ├── quest_tracker.py                 # 퀘스트 추적
│   ├── utility_scorer.py                # 유틸리티 스코어링
│   └── value_estimator.py               # 가치 추정
│
├── touch/                               # 터치 시뮬레이션
│   ├── humanizer.py                     # 인간 유사 터치
│   └── simulator.py                     # 터치 시뮬레이터
│
├── tools/                               # 유틸리티 도구
│   ├── click_capture.py                 # 클릭 캡처
│   ├── level_design_extractor.py        # 레벨 디자인 추출기
│   └── test_zero_api.py                 # API 테스트
│
├── tests/                               # 테스트 코드 (14 files)
│   ├── test_discovery_db.py
│   ├── test_exploration.py
│   ├── test_genre_detector.py
│   ├── test_learning.py
│   └── ...
│
├── data/                                # 데이터 디렉토리
│   ├── games/
│   │   ├── carmatch/                    # CarMatch 게임 데이터
│   │   │   ├── yolo_dataset/            # YOLO 학습 데이터
│   │   │   │   ├── train/               # (7 클래스 폴더)
│   │   │   │   ├── val/
│   │   │   │   └── models/              # 학습된 모델
│   │   │   ├── yolo_od_dataset/         # YOLO OD (차량 감지)
│   │   │   ├── episodes/                # 에피소드 기록
│   │   │   └── level_designs/           # 레벨 디자인
│   │   └── pixelflow/                   # PixelFlow 게임 데이터
│   ├── knowledge/                       # 크로스 게임 지식
│   └── journal/                         # 세션 저널
│
├── docs/                                # 문서
│   └── AI_TESTER_PAPER.md               # 본 문서
│
└── requirements.txt                     # 의존성
```

---

## Appendix B: API Reference

### B.1 Perception API

```python
class Perception:
    """Layer 1: 스크린샷 → 구조화된 BoardState"""

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        timeout: int = 300,
        api_key: str = None,
        game: str = "carmatch",
    ): ...

    def perceive(self, screenshot_path: Path) -> BoardState:
        """스크린샷 → BoardState. 실패 시 unknown 반환.

        내부 동작:
        1. YOLO classify 시도 (5ms)
        2. 실패 시 → OpenCV fallback (50ms)
        3. 실패 시 → VLM API fallback (2~8s)
        4. gameplay이면 → YOLO OD / OpenCV 차량 감지
        5. 실패 시 → VLM 상세 인식
        """

    @property
    def call_count(self) -> int:
        """총 인식 호출 수."""
```

### B.2 Memory API

```python
class GameMemory:
    """Layer 2: 고정 크기 게임 메모리"""

    def update_from_board(self, prev: BoardState, curr: BoardState) -> str:
        """이전/현재 비교 → 결과 판정.
        Returns: 'car_moved' | 'match_3' | 'no_change' | 'screen_changed'"""

    def record_action(self, action: Action): ...
    def on_game_start(self): ...
    def get_color_counts(self) -> dict: ...
    def is_near_failed(self, x: int, y: int, threshold: int = 80) -> bool: ...
    def is_heart_waiting(self) -> bool: ...
```

### B.3 Decision API

```python
class Decision:
    """Layer 3: 고정 분기 기반 의사결정"""

    def __init__(self, playbook: Playbook): ...

    def decide(self, board: BoardState, memory: GameMemory) -> list:
        """현재 상태 → 실행할 Action 리스트.
        P0~P5 우선순위 + NEVER 규칙 + 화면별 핸들러."""
```

### B.4 Executor API

```python
class Executor:
    """Layer 4+5: 행동 실행 + 결과 확인"""

    def __init__(
        self,
        tap_fn, back_fn, screenshot_fn, relaunch_fn,
        perception: Perception,
        memory: GameMemory,
    ): ...

    def execute(self, actions: list, prev_board: BoardState) -> BoardState:
        """Action 리스트 순서대로 실행 → 최종 BoardState 반환.
        화면 전환/매칭 감지 시 즉시 중단."""
```

### B.5 Lookahead API

```python
class LookaheadSimulator:
    """홀더 시뮬레이터"""

    def evaluate_all_moves(self, board: BoardState, holder: list) -> list: ...
    def get_best_move(self, board: BoardState, holder: list): ...

class DeepLookahead(LookaheadSimulator):
    """2수 앞까지 보는 확장 시뮬레이터"""

    def get_best_move_deep(self, board: BoardState, holder: list): ...
```

### B.6 Swarm API

```python
class SwarmOrchestrator:
    """AI 에이전트 군집 오케스트레이터"""

    def __init__(
        self,
        game_id: str = "carmatch",
        play_minutes: int = 60,
        validate_minutes: int = 10,
    ): ...

    def run(self, max_cycles: int = 0, max_hours: float = 0): ...
    # 4 phases: _run_player → _run_analyst → _run_improver → _run_validator

class ExperienceDB:
    """영구 경험 데이터베이스"""

    def record_screen_action(self, screen_type, x, y, success, result_screen): ...
    def get_best_action(self, screen_type): ...
    def get_stats_summary(self) -> dict: ...
```

---

## Appendix C: Supported Game Genres

### C.1 장르별 전략 총괄

| Genre | 구현 파일 | 핵심 전략 | 인식 난이도 | 대표 게임 |
|-------|---------|---------|----------|---------|
| **Puzzle Match** | `genres/puzzle_match.py` | 색상 매칭, 홀더 관리 | Medium | CarMatch, Pixel Flow |
| **Idle RPG** | `genres/idle_rpg.py` | 자동 전투, 보상 수집 | Low | AFK Arena류 |
| **Card Battle** | `genres/card_battle.py` | 카드 선택, 턴제 전투 | High | 하스스톤류 |
| **Runner/Platformer** | `genres/runner_platformer.py` | 타이밍 기반 입력 | Very High | 서브웨이 서퍼류 |
| **Simulation** | `genres/simulation.py` | 자원 관리, 건설 | Medium | 심시티류 |
| **Tower Defense** | `genres/tower_defense.py` | 타워 배치, 업그레이드 | Medium | Kingdom Rush류 |
| **Merge Game** | (genre/merge_schema.py) | 아이템 합성 | Low | Merge Dragons류 |

### C.2 Puzzle Match 전략 상세

```python
# 기존 구현 (tester/genres/puzzle_match.py 기반)
class PuzzleMatchStrategy:
    """퍼즐 매치 장르 전략.

    핵심 메커니즘: N개 동일 아이템 매칭 → 제거
    홀더/보드 기반: 아이템을 선택하면 홀더에 추가, N개 모이면 제거

    전략 우선순위:
    1. 매칭 완성 (홀더에 N-1개 + 보드에 1개)
    2. 위험 회피 (홀더 가득 참 방지)
    3. 부분 매칭 (홀더에 있는 색상 추가)
    4. 안전한 탐색 (여유 있을 때 새 색상)
    """

    # 행동 비중
    action_mix = {
        "select": 0.70,      # 오브젝트 선택 (탭)
        "activate": 0.10,    # 부스터 사용
        "respond": 0.15,     # 팝업/광고 처리
        "wait": 0.05,        # 대기
    }

    # 화면 흐름
    screen_flow = {
        "lobby": ["gameplay"],
        "gameplay": ["win", "fail_outofspace", "fail_holdfull"],
        "win": ["lobby", "ad"],
        "fail_outofspace": ["gameplay", "lobby", "ad"],
        "fail_holdfull": ["gameplay", "lobby"],
        "ad": ["lobby", "gameplay"],
        "popup": ["lobby", "gameplay"],
    }
```

### C.3 Idle RPG 전략 상세

```python
class IdleRPGStrategy:
    """방치형 RPG 전략.

    특성: 대부분 자동 전투, 인간 개입 = 보상 수집 + 업그레이드
    AI 역할: 주기적 화면 확인 → 보상 팝업 탭 → 장비 업그레이드

    전략:
    1. 자동 전투 ON 확인
    2. 30초~1분 간격으로 화면 체크
    3. 보상 팝업 → 수집
    4. 일정 주기로 캐릭터/장비 업그레이드
    5. 일일 퀘스트 / 출석 보상 수집
    """

    action_mix = {
        "navigate": 0.20,
        "select": 0.30,
        "activate": 0.05,
        "wait": 0.30,       # 방치 비중 높음
        "respond": 0.15,
    }

    # 긴 대기 사이클
    check_interval_sec = 60  # 1분마다 화면 확인
```

### C.4 장르별 인식 특수 요구사항

```
Puzzle Match:
  - 색상 인식 정확도 > 90% (핵심)
  - 홀더 상태 정확한 읽기
  - 스택 숫자 OCR

Idle RPG:
  - 자동 전투 ON/OFF 상태 감지
  - 보상 팝업 감지 (다양한 형태)
  - HP/MP 바 읽기

Card Battle:
  - 카드 이미지/텍스트 인식
  - 마나 코스트 읽기
  - 턴 타이머 감지

Runner/Platformer:
  - 프레임 단위 장애물 감지 (높은 FPS 필요)
  - 타이밍 크리티컬 (ADB latency 한계)
  → 이 장르는 Black-box 방식으로 충분한 성능 달성이 어려움

Tower Defense:
  - 그리드 기반 좌표 매핑
  - 적 경로 인식
  - 타워 종류/레벨 식별

Merge Game:
  - 아이템 등급/종류 인식
  - 보드 그리드 매핑
  - 빈 칸 감지
```

---

*본 문서는 `E:\AI\virtual_player\` 코드베이스 199개 Python 파일의 실제 구현을 기반으로 작성되었으며, 미구현 부분(Phase 4~5)은 설계 사양으로 기술하였다.*

*Last updated: 2026-03-31*
