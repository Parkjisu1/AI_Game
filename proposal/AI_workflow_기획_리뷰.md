# AI 기획 Workflow 초안 — 교차 검증 리뷰

> **리뷰 대상**: AI_workflow_기획.md (v1.1, 2026-02-24)
> **리뷰 일자**: 2026-02-25

---

# 1차 리뷰: AI_workflow_기획.md ↔ CLAUDE.md 교차 검증

> 첨부된 두 문서(기획 Workflow 초안 + CLAUDE.md) 기준으로 비교한 결과입니다.

---

## 잘 대응된 부분

두 문서 간 구조적 대칭이 의도적으로 잘 설계되어 있습니다.

| 항목 | CLAUDE.md (코드) | 기획 문서 | 판정 |
|------|-----------------|----------|:----:|
| AI 분리 원칙 | 3-AI (DB 가공, 코드 생성, 검증) | 3-AI (DB 가공, 기획 생성, 검증) | 일치 |
| DB 검색 우선순위 | Expert(장르) → Expert(Generic) → Base(장르) → Base(Generic) → AI 생성 | 동일 5단계 | 일치 |
| 신뢰도 초기값 | 0.4 | 0.4 | 일치 |
| Expert DB 승격 | >= 0.6 | >= 0.6 | 일치 |
| Rules 추출 | Generic 규칙 + 장르별 규칙 | Generic 규칙 + 장르별 규칙 + 도메인별 규칙 | 확장 |
| 피드백 형식 | JSON (category, severity, suggestion) | JSON (category, section, direction, designPillarCheck) | 확장 |

특히 기획 문서가 코드 Workflow를 **단순 복사가 아니라 기획 특성에 맞게 확장**한 부분이 좋습니다:
- 피드백에 `designPillarCheck` (디자인 필러 위반 여부) 추가
- Rules에 도메인별 규칙 추가
- 사후 라벨링(시장 성과) 별도 관리 — 기획만의 고유한 요소

---

## 불일치 항목

### 1. Genre 목록

| CLAUDE.md | 기획 문서 |
|-----------|----------|
| Generic, RPG, Idle, Merge, SLG, Tycoon, Simulation, Puzzle, **Playable** | Generic, RPG, Idle, SLG, Simulation, Tycoon, Merge, Puzzle, **Casual** |

CLAUDE.md에서 `Playable`을 장르로 분류하고 있고 (DB 위치 섹션에서 `db/base/playable/`도 명시), 기획 문서에서는 `Casual`로 대체했습니다.

기획 문서의 판단(Playable은 플랫폼이지 장르가 아님)에 동의합니다. 다만 **통일하지 않으면 DB 검색 키가 불일치**하므로, 양쪽 중 하나로 맞춰야 합니다.

- CLAUDE.md의 `platform: playable` 분기 구조(Playable 광고 섹션)가 이미 장르와 플랫폼을 분리하고 있으니, 장르 목록에서 `Playable` → `Casual`로 바꾸는 게 자연스럽습니다.

---

### 2. 신뢰도 점수 변동 — 코드와 비대칭

| 이벤트 | CLAUDE.md (코드) | 기획 문서 |
|--------|:---------------:|:--------:|
| 초기 저장 | 0.4 | 0.4 |
| 피드백 반영 완료 | +0.2 | — |
| 디렉터 검증 통과 (피드백 없이) | — | +0.2 |
| 피드백 반영 후 승인 | — | +0.1 |
| 재사용 성공 | +0.1 | — |
| 다른 프로젝트에서 참조 성공 | — | +0.1 |
| 다른 장르에서 재사용 성공 | +0.1 (Generic 승격) | +0.1 (Generic 승격) |
| **재사용 실패** | **-0.15** | **없음** |

차이점 2가지:

**a) 이벤트명 변경**: 코드의 "피드백 반영 완료 +0.2" → 기획의 "디렉터 검증 통과 +0.2 / 피드백 반영 후 승인 +0.1"으로 분리. 이건 기획 특성(사람이 최종 승인)을 반영한 것이라 합리적입니다.

**b) 감점 메커니즘 부재**: 코드에는 `재사용 실패: -0.15`가 있는데 기획에는 없습니다. 의도적인지 확인이 필요합니다.
- 의도적이라면: "기획은 코드와 달리 실패/성공 판단이 모호하므로 감점하지 않는다"는 근거를 명시
- 누락이라면: "다른 프로젝트에서 참조했으나 부적합 판정: -0.15" 추가

---

### 3. 기획 문서에만 존재하는 자동 점수 (0~1.0 × 3종)

기획 문서 6단계에 **자동 점수** 3종이 추가되어 있습니다:

```
논리 완결성: 0~1.0
밸런스 안정성: 0~1.0
구현 복잡도: 0~1.0
```

CLAUDE.md에는 이런 개념이 없습니다. 기획 특성상 필요한 추가인데, **이벤트 기반 신뢰도 점수와의 관계가 정의되지 않았습니다.**

- 자동 점수는 신뢰도 점수의 초기값을 결정하는 건지?
- 별도 독립 지표인지?
- Expert DB 승격에 자동 점수가 관여하는지?

이 관계가 빠지면 실제 구현 시 "점수가 두 종류인데 어떤 걸로 승격 판단하지?"가 됩니다.

---

### 4. 분류 체계 대응 — 매핑 테이블 불완전

기획 문서 L865~876의 "기획 도메인 → 코드 Domain 매핑":

| 기획 도메인 | 코드 Domain | 상태 |
|------------|-------------|:----:|
| InGame | Battle, Skill, Character, Stage | OK |
| OutGame | Inventory, Shop, Item | OK |
| Balance | 각 Domain의 Calculator/Processor | OK |
| Content | Quest, Stage, Reward | OK |
| BM | Shop, IAP | OK |
| UX | UI, Audio | OK |
| Social | Network, Guild | OK |
| Meta | Achievement, Collection | OK |
| **LiveOps** | **(없음)** | **누락** |

CLAUDE.md의 Role 21종에는 LiveOps에 해당하는 패턴(예: Scheduler, Policy)이 직접적으로 없어서 매핑이 어려울 수 있지만, "해당 없음" 또는 "추후 정의"라도 명시되면 좋겠습니다.

---

### 5. 기획 문서 내부 불일치 — 복합 장르

기획 문서 자체 내에서:
- L104: Genre 9종 목록에 `Idle RPG` 없음 (단일 장르만)
- L118~119: 예시에서 `genre: Idle RPG` 사용

분류 체계에서 단일 장르만 정의했는데, 바로 아래 예시에서 복합 장르를 쓰고 있어 **문서 내부 일관성**이 깨집니다.

---

## 기획 문서 고유 강점 (코드 Workflow에 없는 것)

코드 Workflow 대비 기획 문서가 가진 고유한 가치:

| 항목 | 설명 | 평가 |
|------|------|------|
| **디렉터 포지셔닝** | DB 축적에 따라 디렉션 상세도가 줄어드는 3단계 비전 | 실무적으로 설득력 있음 |
| **실패 데이터 처리** | 원인 불명이면 반면교사로 안 쓴다 | AI 학습 오염 방지에 핵심 |
| **사후 라벨 분리** | 시장 성과를 신뢰도 점수와 혼합하지 않음 | 정확한 판단. 외부 변수 오염 방지 |
| **입력 자료 현실적 처리** | "밸런스 시트만 있는 경우" 등 실제 상황별 대응 | 현업 자료 상태를 잘 반영 |
| **라이브 DB 버전 관리** | KPI 인과관계 기록 포함 | 코드에는 없는 기획 고유 요소, 차기 프로젝트에 큰 가치 |
| **7단계 플레이 검증** | 문서 검증을 넘어 실제 플레이 기반 실증 | 코드에 없는 단계, 파이프라인 완결성 향상 |
| **8단계 라이브 동기화** | 출시 후 데이터 순환 구조 | 장기 DB 축적 관점에서 필수 |

---

## 1차 리뷰 요약

| 유형 | 항목 | 긴급도 |
|------|------|:------:|
| 불일치 | Genre 목록 (Playable vs Casual) | 높음 |
| 불일치 | 감점 메커니즘 부재 | 중간 |
| 미정의 | 자동 점수와 신뢰도 점수 관계 | 높음 |
| 미정의 | 복합 장르 처리 규칙 | 중간 |
| 누락 | LiveOps → 코드 Domain 매핑 | 낮음 |
| 내부 불일치 | Genre 단일 목록 vs Idle RPG 예시 | 중간 |

---
---

# 2차 리뷰: 내부 시스템 자료 기반 심화 검증

> CLAUDE.md 외에 실제 구현된 시스템 자료들(Agent 정의서, AI Tester 사양서, DB 실제 구조, Workflow 문서, 피드백 히스토리)과 대조한 심화 분석입니다.

> 검증 기준:
> - `WORKFLOW.md` (통합 워크플로우)
> - `.claude/agents/` (designer.md, validator.md, db-builder.md 등 6종)
> - `C10_PLUS_V25_AI_TESTER_SYSTEM.md` (AI Tester 사양서)
> - `C10_Plus_개선방안.md` (AI Tester 개선 로드맵)
> - `db/` 실제 디렉토리 구조 및 스키마
> - `virtual_player/` 소스 구조
> - `Feedback/Workflow_Improvements.md` (실전 피드백)

---

## A. 파이프라인 연결 단절 — AI Tester → Design DB

### 문제

기획 문서 L221~227:
> "AI Tester 시스템으로 순수 관찰 분석"
> "32개 파라미터 추정 결과를 Base Design DB로 가공 (source: observed)"

AI Tester 실제 출력 형식 (C10+ v2.5 사양서 L139~149):
```yaml
parameters:
  - id: ANV18
    name: damage_formula
    category: combat        # ← AI Tester 카테고리
    value: "ATK × 1.2 - DEF × 0.5"
    confidence: high
```

Design DB 입력에 필요한 형식 (기획 문서 L114~125):
```yaml
domain: InGame              # ← 기획 도메인
genre: Idle RPG
system: 전투 > 데미지 판정
balance_area: 전투 밸런스
data_type: 공식/수치
source: observed
```

**이 변환 규칙이 어디에도 없습니다.** AI Tester의 9개 카테고리(progression, growth, equipment, combat, gacha, economy, system, visual, architecture)가 기획 도메인 9종으로 어떻게 매핑되는지 정의가 필요합니다.

### 매핑 제안

```
AI Tester 카테고리     →  기획 도메인    설명
──────────────────────────────────────────────────
progression (5개)     →  InGame       스테이지/챕터 구조
growth (5개)          →  Balance      성장 곡선, 경험치
equipment (4개)       →  OutGame      장비/강화 시스템
combat (6개)          →  InGame       전투 메커니즘
gacha (4개)           →  OutGame + BM 가챠 시스템, 과금 포인트
economy (5개)         →  Balance + BM 재화 밸런스, 방치 보상
system (1개)          →  Meta         시스템 구조
visual (1개)          →  UX           UI 기준 해상도
architecture (1개)    →  (제외)       코드 아키텍처 (기획 DB 대상 아님)
```

---

## B. Base Design DB 물리적 구조 — 코드 DB와 대비

### 코드 DB (이미 구현됨)

db-builder.md에 정의된 실제 구조:
```
db/base/{genre}/{layer}/
├── index.json          ← 경량 인덱스 (fileId, layer, genre, role, score, provides, requires)
└── files/
    └── {fileId}.json   ← 상세 (namespace, usings, classes, methods, fields)
```

실제 `db/base/generic/core/index.json`에 55+ 파일이 저장되어 있고, `db/expert/`에도 검증된 코드가 축적되어 있습니다.

### 기획 DB (미정의)

기획 문서에는 "레이어 1(통짜), 레이어 2(태깅)"이라는 개념만 있고:
- 물리적 디렉토리 경로 없음
- 인덱스/상세 파일 스키마 없음
- 검색 API/방법 없음

### 제안 구조

```
db/design/
├── base/
│   └── {genre}/
│       ├── {domain}/
│       │   ├── index.json             # 레이어 2 인덱스
│       │   └── files/
│       │       └── {designId}.json    # 레이어 2 상세
│       └── _projects/
│           └── {project}.json         # 레이어 1 (프로젝트 통짜)
├── expert/
│   ├── index.json
│   └── files/
└── rules/
    ├── generic_design_rules.json
    └── genre_design_rules.json
```

인덱스 스키마:
```json
{
  "designId": "ash_n_veil_damage_formula",
  "projectRef": "ash_n_veil",
  "domain": "InGame",
  "genre": "Idle",
  "system": "전투 > 데미지 판정",
  "balance_area": "전투 밸런스",
  "data_type": "공식/수치",
  "source": "internal_original",
  "score": 0.6,
  "version": "1.2.0",
  "performance_grade": null,
  "provides": ["damage_formula", "min_damage_rule"],
  "requires": ["atk_stat", "def_stat"]
}
```

---

## C. 기획 Validator Agent 부재

### 코드 쪽 (구현됨)

`validator.md`가 정의되어 있습니다:
- 5단계 검증 (Syntax → Dependency → Contract → NullSafety → Pattern)
- 피드백 JSON 형식, 카테고리 7종
- 점수 관리 + Expert DB 승격 프로세스
- KPI 보고서 생성

### 기획 쪽 (미정의)

기획 3단계 "통합 검증"이 있지만, **누가 수행하는지** Agent 정의가 없습니다.

CLAUDE.md의 Agent Team 구성(6+1명)에도 Design Validator는 없습니다. 현재 Validator Agent는 "코드 검증 전문"으로 정의되어 있어 기획 검증은 수행 범위 밖입니다.

### 제안

```yaml
# .claude/agents/design-validator.md (신규)
name: design-validator
model: sonnet
description: "기획 검증 전문 AI - 교차 일관성, 유저 여정, 누락 검출, 밸런스 시뮬레이션"

검증 4단계:
  1. 교차 일관성: 시스템↔밸런스, 콘텐츠↔시스템, BM↔밸런스, UX↔시스템
  2. 유저 여정: Day 1~30 시뮬레이션
  3. 누락 검출: 참조되는데 정의 안 된 아이템/스킬/스탯
  4. 디자인 필러 체크: 핵심 컨셉 부합 여부

피드백 카테고리: 기획 문서 L475~489의 14종 사용
```

---

## D. 가상 유저 테스트 — 90%+ 조건 이미 달성 가능

기획 문서 L648:
> "AI Tester 관찰 정확도가 90%+ 달성되면, AI 가상 유저 에이전트를 생성하여 천~만 명 규모 동시 시뮬레이션이 가능"

`C10_Plus_개선방안.md`의 실제 데이터:

```
v1 (현재):  89.5%
v2.5 (예상): 93~95%  (OCR + Wiki + APK 에셋, 추가 구현 ~4시간, 비용 0원)
```

v2.5를 적용하면 **선행 조건(90%+)이 즉시 충족**됩니다. 또한 `virtual_player/` 에 이미 아래 인프라가 구현되어 있습니다:

```
virtual_player/
├── brain/          # AI 의사결정 엔진
├── navigation/     # 화면 탐색, 팝업 핸들링
├── session/        # 세션 관리, 패턴 추적
├── touch/          # 터치 휴먼화
├── history/        # 분석, 트래킹
└── adapters/       # ADB, Web 등 어댑터
```

"AI Tester → 가상 유저"는 새로 만드는 게 아니라 **기존 인프라의 모드 전환**에 가깝습니다.

다만 스케일업 로드맵은 별도 필요:

| 단계 | 규모 | 전제 조건 | 활용 |
|------|------|-----------|------|
| Phase A | 10명 (현재) | v2.5 적용 | 파라미터 추정 |
| Phase B | 100명 | 자사 서버 가속 API | 스테이지 클리어율, 병목 |
| Phase C | 1000명+ | 서버 시뮬레이션 환경 | 경제 시뮬, 메타 분석 |

---

## E. 2단계 기획 생성 — 병렬화 구체화

### 코드 쪽 (상세 정의됨)

WORKFLOW.md에 Phase별 의존성 + 병렬 실행이 다이어그램으로 정의:

```
Phase 0: Main Coder 단독 (Core)
Phase 1: Main(복잡) + Sub x2(일반) 병렬
Phase 2: 동일 패턴 병렬
Phase 간: Validator 검증 통과 후 다음 Phase
```

### 기획 쪽 (순서만 명시)

기획 문서 L246~248:
> "시스템 기획 → 콘텐츠 기획 → 밸런스 기획 → BM 기획 → 통합 검증"

의존성/병렬화 규칙이 없습니다. 제안:

```
Phase 0: 컨셉 정의 (2-1) ────── 선행 없음, Designer 단독
Phase 1: 시스템 기획 (2-2) ──── Phase 0 의존
         ├─ InGame 시스템들 ─┐
         ├─ OutGame 시스템들 ─┤  ← 도메인 간 병렬 가능
         └─ Social/Meta ─────┘
Phase 2: 밸런스 (2-3) + 콘텐츠 (2-4) ── Phase 1 의존
         (밸런스와 콘텐츠 부분 병렬 가능)
Phase 3: BM (2-5) ──────────── Phase 2 의존
Phase 4: 통합 검증 ─────────── 전체 의존
```

Agent Team으로 운영할 경우, Designer를 도메인별로 분할(시스템 Designer + 밸런스 Designer)하면 Phase 1 내부 병렬이 가능합니다.

---

## F. 기획 ↔ 코드 피드백 연쇄

기획 문서 L863~876에 기획 도메인 → 코드 Domain 매핑이 있는데, 이걸 **양방향**으로 확장하면:

```
기획 3단계에서 발견:
  BALANCE.FORMULA_ERROR (데미지 공식 오류)
      ↓ 매핑: Balance → Calculator/Processor Role
코드 쪽 영향:
  DamageCalculator.cs 재생성 필요
      ↓ validator.md 피드백 카테고리
  CONTRACT.SIGNATURE_MISMATCH 자동 생성
```

현재 `Feedback/Workflow_Improvements.md`에서 확인된 실전 문제(SDK 40%, 빌드 30%, UI 20%)도 이런 연쇄 구조로 기획 → 코드 영향을 추적할 수 있습니다.

---

## G. 사후 라벨 활용 + 라이브 동기화 자동화

### 사후 라벨 검색 활용

기획 문서에 `performance_grade: S/A/B/C/F`가 있지만 검색 시 활용법이 없습니다.

```yaml
# 검색 쿼리 예시
query:
  domain: Balance
  genre: RPG
  filter:
    performance_grade: ["S", "A"]     # A등급 이상 프로젝트만
    source: ["internal_original"]      # 실증 데이터만
```

"A등급 프로젝트에서 사용된 Idle RPG 방치보상 공식"처럼 **성과 기반 필터링**이 가능해지면 DB 실질적 가치가 올라갑니다.

### 라이브 동기화 자동화 수준

8단계의 트리거 주체(누가 입력하는가)를 단계적으로 정의:

| 레벨 | 방식 | 시점 |
|------|------|------|
| L1 수동 | 디렉터가 패치 후 직접 입력 | 즉시 가능 |
| L2 반자동 | 밸런스 시트 변경 감지 → AI가 diff → 디렉터 승인 | DB 축적 후 |
| L3 자동 | 서버 API 연동 → 자동 버전 추가 + KPI 연동 | 라이브 서비스 중 |

---

## 종합 우선순위

| 순위 | 항목 | 출처 | 긴급도 |
|:----:|------|:----:|:------:|
| 1 | Genre 통일 (Playable vs Casual) | 1차 | 높음 |
| 2 | 자동 점수 / 신뢰도 관계 정의 | 1차 | 높음 |
| 3 | Design DB 물리적 구조 | 2차 | 높음 |
| 4 | AI Tester → Design DB 변환 규칙 | 2차 | 높음 |
| 5 | 복합 장르 처리 규칙 | 1차 | 중간 |
| 6 | 감점 메커니즘 확인 | 1차 | 중간 |
| 7 | 2단계 병렬화 규칙 | 2차 | 중간 |
| 8 | Design Validator Agent 정의 | 2차 | 중간 |
| 9 | LiveOps 매핑 | 1차 | 낮음 |
| 10 | 사후 라벨 검색 활용 | 2차 | 낮음 |
| 11 | 라이브 동기화 자동화 수준 | 2차 | 낮음 |
| 12 | 기획 ↔ 코드 피드백 연쇄 | 2차 | 낮음 |

- **1~4번**: 구현 착수 전 확정 필수
- **5~8번**: 구현 초기에 잡으면 좋음
- **9~12번**: 운영하면서 점진적으로

---

전체적으로 코드 Workflow와의 구조적 대칭이 잘 잡혀 있고, 기획 고유의 확장(디렉터 포지셔닝, 사후 라벨, 라이브 버전 관리)도 현실적입니다. 위 항목들만 보완하면 바로 구현 단계로 넘어갈 수 있는 수준입니다.
