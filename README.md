# GameForge: AI-Driven Game Development Pipeline

> **AI 에이전트 팀 기반의 게임 기획서 자동 생성 및 Unity C# 코드 생성 파이프라인**

```
Input:  "Idle RPG를 만들어줘. 방치 수익 + 캐릭터 수집."
Output: 기획서 3-Layer + Unity C# 소스코드 54개 시스템 + 검증 리포트
```

---

## Table of Contents

1. [프로젝트 개요](#1-프로젝트-개요)
2. [해결하려는 문제](#2-해결하려는-문제)
3. [설계 원칙](#3-설계-원칙)
4. [시스템 아키텍처](#4-시스템-아키텍처)
5. [이중 파이프라인](#5-이중-파이프라인)
6. [분류 체계](#6-분류-체계)
7. [에이전트 팀 구조](#7-에이전트-팀-구조)
8. [데이터베이스 아키텍처](#8-데이터베이스-아키텍처)
9. [신뢰도 점수 시스템](#9-신뢰도-점수-시스템)
10. [AI Tester & Virtual Player](#10-ai-tester--virtual-player)
11. [도구 및 스크립트](#11-도구-및-스크립트)
12. [품질 보증 체계](#12-품질-보증-체계)
13. [프로젝트 구조](#13-프로젝트-구조)
14. [실행 방법](#14-실행-방법)
15. [검증된 프로젝트](#15-검증된-프로젝트)
16. [기술적 의사결정 근거](#16-기술적-의사결정-근거)
17. [Workflow 검증 현황](#17-workflow-검증-현황)

---

## 1. 프로젝트 개요

GameForge는 게임 개발의 두 축인 **기획**과 **코드 생성**을 AI 에이전트 팀이 자동화하는 파이프라인입니다.

한 줄의 게임 컨셉으로부터 3-Layer 기획서(게임 기획서 → 시스템 명세서 → AI_기획서 YAML)를 생성하고, 이를 기반으로 Unity C# 소스코드를 병렬 생성·검증하며, 검증된 결과물을 DB에 축적하여 다음 프로젝트의 품질을 높이는 **자기강화 순환 구조**를 가집니다.

### 지원 플랫폼

| 플랫폼 | 출력물 | 용도 |
|--------|--------|------|
| **Unity** | C# MonoBehaviour 소스코드 | 모바일/PC 게임 |
| **Playable** | 단일 HTML5 파일 (`playable.html`) | 플레이어블 광고 (Facebook, Google Ads, IronSource, AppLovin) |

### 지원 장르

Generic(공통), RPG, Idle, SLG, Simulation, Tycoon, Merge, Puzzle, Casual — 총 9종.

### 수치 요약

| 항목 | 규모 |
|------|------|
| Code DB (Base) | 958개 파일, 8개 장르 |
| Code DB (Expert) | 20개 파일 (score >= 0.6) |
| Design DB (Base) | 97개 파일 |
| 자동화 스크립트 | 18개 (17 JS + 1 Python) + 4개 공유 라이브러리 |
| 커스텀 에이전트 | 9종 (Lead 포함) |
| 슬래시 커맨드 | 8종 |
| 검증 완료 프로젝트 | 4개 (Puzzle 2, RPG 1, Idle 1) |

---

## 2. 해결하려는 문제

### 2.1 LLM의 게임 코드 생성 한계

LLM에게 "RPG 전투 시스템 만들어줘"라고 요청하면 매번 다른 구조, 다른 네이밍, 다른 패턴의 코드를 생성합니다. 프로젝트 내 시스템 간 일관성이 없고, 이전 프로젝트에서 잘 동작했던 코드를 활용하지 못합니다.

**근본 원인**: LLM에게 "참조할 기존 코드"와 "따라야 할 구조적 규칙"이 없기 때문입니다.

### 2.2 기획서와 코드의 괴리

기획자가 작성한 기획서를 개발자가 해석하여 코드로 구현하는 과정에서 의도가 변질됩니다. AI 코드 생성에서도 동일한 문제가 발생합니다 — 기획 의도를 정확히 반영하는 코드가 나오지 않습니다.

**근본 원인**: 기획서의 형식이 AI가 해석하기에 모호하고, 기획→코드 변환 규칙이 정의되어 있지 않기 때문입니다.

### 2.3 환각(Hallucination) 문제

하나의 AI에게 "기획도 하고 코드도 짜고 검증도 해"라고 시키면, 역할 전환 과정에서 환각이 발생합니다. 기획에서 정의하지 않은 기능을 코드에서 만들어내거나, 검증 과정에서 존재하지 않는 파일을 참조합니다.

**근본 원인**: 하나의 AI가 너무 많은 역할을 수행하면 컨텍스트 오염이 발생합니다.

### GameForge의 해결 방식

```
문제: 참조 없는 코드 생성     → 해결: Base/Expert DB + 5단계 검색 우선순위
문제: 기획↔코드 괴리          → 해결: 3-Layer 기획서 + YAML 노드 → 코드 자동 변환
문제: 환각                    → 해결: 3-AI 역할 분리 (DB 가공 / 생성 / 검증)
문제: 일관성 없는 구조         → 해결: 정규화된 분류 체계 (Layer > Genre > Role > Tag)
문제: 품질이 축적되지 않음      → 해결: 신뢰도 점수 + Expert DB 승격 + Rules 추출
```

---

## 3. 설계 원칙

### 3.1 3-AI 역할 분리 (Anti-Hallucination Architecture)

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   1단계 AI      │    │   2단계 AI      │    │   3단계 AI      │
│   DB 가공       │ →  │   생성          │ →  │   검증          │
│                 │    │                 │    │                 │
│ • 소스 파싱     │    │ • 기획서 생성    │    │ • 일관성 검증    │
│ • 분류/태깅     │    │ • 코드 생성     │    │ • 밸런스 시뮬    │
│ • DB 저장       │    │ • DB 참조       │    │ • 피드백 생성    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

하나의 AI가 여러 역할을 전환하면 이전 역할의 컨텍스트가 다음 역할을 오염시킵니다. 각 AI가 하나의 역할에만 집중하도록 분리함으로써:

- **전문성 향상**: 각 AI가 자신의 역할에 최적화된 컨텍스트만 유지
- **환각 방지**: 역할 전환 없이 일관된 출력
- **병렬 처리**: 독립된 역할이므로 동시 실행 가능

### 3.2 DB 참조 필수 원칙

코드를 생성할 때 반드시 기존 DB를 검색하고, 유사 코드가 있으면 참조합니다.

```
검색 우선순위:
1. Expert DB (해당 장르)     — 검증된 고품질 코드 (score >= 0.6)
2. Expert DB (Generic)       — 장르 무관 검증 코드
3. Base DB (해당 장르)       — 파싱된 기존 코드
4. Base DB (Generic)         — 장르 무관 기존 코드
5. 자체 생성                 — 참조 없음 (최후의 수단)
```

이 우선순위를 통해 AI가 "근거 없는 코드"를 생성하는 것을 최소화합니다. 5순위로 갈수록 디렉터(사람)의 검수 강도가 높아집니다.

### 3.3 정규화된 분류 체계

모든 코드와 기획 자료는 동일한 분류 체계로 태깅됩니다. 이를 통해 AI가 "어떤 장르의 어떤 시스템에 해당하는 코드"를 정확히 검색할 수 있습니다.

```
코드: Layer(3) > Genre(9) > Role(21) > Tag(대기능 7 + 소기능 11)
기획: Domain(9) > Genre(9) > System > 다중 태그(balance_area, data_type, source, version)
```

### 3.4 디렉터 포지셔닝

사람은 "AI에게 지시하는 관리자"가 아니라 "게임의 방향을 결정하는 디렉터"로 포지셔닝됩니다.

```
디렉터(사람): 상위 디렉션 제공 (의도, 방향성, 제약조건)
    → AI: 실행 (DB 참조 → 구체화, 수치 채우기, 양산)
        → 디렉터: 검증 (의도대로인가 판단)
            → 통과: 다음 단계
            → 피드백: AI 재실행
```

DB가 축적될수록 디렉션의 상세도가 줄어듭니다:
- **DB 부족기**: "데미지 공식은 ATK×배율-DEF×0.5로, 최소 데미지는 ATK의 5%로 해줘"
- **DB 풍부기**: "RPG 전투 밸런스 잡아줘, 초반은 쉽게" (한 줄이면 충분)

---

## 4. 시스템 아키텍처

### 전체 흐름

```
                    ┌──────────────────────────────────────────┐
                    │           GameForge Pipeline              │
                    └──────────────────────────────────────────┘

┌─────────────┐     ┌─────────────────────────────────────┐     ┌─────────────┐
│             │     │        Design Workflow (8단계)        │     │             │
│  기존 자료   │ ──→ │  DB 가공 → 기획 생성 → 통합 검증     │ ──→ │  기획 결과물  │
│  (기획/코드) │     │  → 디렉터 검수 → DB 축적             │     │  (YAML)     │
│             │     │  → 플레이 검증 → 라이브 동기화        │     │             │
└─────────────┘     └──────────────────┬──────────────────┘     └──────┬──────┘
                                       │                               │
                                       │   자동 변환                    │
                                       │                               ▼
┌─────────────┐     ┌─────────────────────────────────────┐     ┌─────────────┐
│             │     │        Code Workflow (6단계)          │     │             │
│  Base Code  │ ──→ │  기획서 가공 → 코드 생성 (병렬)       │ ──→ │  C# 소스코드 │
│  DB         │     │  → 검증 → 피드백 → DB 축적           │     │  + HTML5    │
│             │     │                                      │     │             │
└─────────────┘     └──────────────────────────────────────┘     └─────────────┘
                                       │
                                       ▼
                              ┌─────────────────┐
                              │    Expert DB     │
                              │  (축적 → 재사용)  │
                              └─────────────────┘
```

### 자기강화 순환 (Self-Reinforcing Loop)

```
프로젝트 A 코드 생성 → 검증 → Expert DB 축적
                                    ↓
프로젝트 B 코드 생성 ← Expert DB 참조 (품질 ↑)
                    → 검증 → Expert DB 축적 (규모 ↑)
                                    ↓
프로젝트 C 코드 생성 ← Expert DB 참조 (품질 ↑↑)
         ...
```

프로젝트를 거듭할수록 Expert DB가 풍부해지고, AI가 참조할 고품질 코드가 많아지므로 생성 품질이 자연스럽게 상승합니다. 동시에 반복 피드백에서 추출한 Rules가 축적되어, 같은 실수를 반복하지 않습니다.

---

## 5. 이중 파이프라인

GameForge는 **기획 파이프라인**과 **코드 파이프라인**을 독립적으로 운영하며, 두 파이프라인이 자동 변환 규칙으로 연결됩니다.

### 5.1 기획 파이프라인 (Design Workflow — 8단계)

```
1단계  Base Design DB 가공     ← 기존 기획 자료, AI Tester 관찰
2단계  기획 생성                ← 디렉터 디렉션 + DB 참조
  ├ 2-1  컨셉 정의
  ├ 2-2  시스템 기획            ← 도메인 간 병렬 가능
  ├ 2-3  밸런스 기획            ← balance-simulator.js로 수치 검증
  ├ 2-4  콘텐츠 기획
  └ 2-5  BM/LiveOps 기획
3단계  통합 검증                ← 교차 일관성 + 유저 여정 시뮬레이션
4단계  디렉터 검수 및 피드백
5단계  재생성 평가
6단계  Expert Design DB 축적
7단계  플레이 검증              ← AI Tester 실제 플레이 (빌드 필요)
8단계  라이브 운영 DB 동기화     ← 출시 후 데이터 버전 관리
```

### 5.2 코드 파이프라인 (Code Workflow — 6단계)

```
Phase 0  Core 시스템           ← Main Coder 단독 (Singleton, EventManager, Pool)
Phase 1  기본 Domain           ← Main Coder + Sub Coder x2 병렬
Phase 2  상위 Domain           ← Main Coder + Sub Coder x2 병렬
Phase 3  Game Layer (UI)       ← Main Coder + Sub Coder x2 병렬
         검증                  ← Validator가 완료 순서대로 즉시 검증
         피드백/재생성          ← 실패 시 해당 Coder에게 피드백
         DB 축적               ← 검증 통과 코드 Expert DB 저장
```

### 5.3 파이프라인 연결: 기획→코드 자동 변환

| 기획 출력물 | 코드 입력 | 변환 방식 |
|------------|----------|----------|
| concept.yaml → design_pillars | game_design.yaml → concept | 직접 매핑 |
| 시스템별 YAML → rules, data_tables | system_spec.yaml → systems[] | 구조 변환 |
| balance_sheet.yaml → 공식, 테이블 | nodes/*.yaml → logicFlow | AI가 코드 로직으로 번역 |
| 콘텐츠 데이터 → 몬스터/스테이지 테이블 | 데이터 테이블 (JSON/CSV) | 형식 변환 |

### 5.4 Playable 광고 파이프라인 (경량)

Unity 파이프라인과 분기되는 HTML5 단일 파일 생성 경로입니다.

```
Designer → 플레이어블 기획 YAML (노드 1개)
    → Playable Coder → playable.html (단일 파일)
        → Validator → 4단계 규격 검증 (Isolation/Interaction/CTA/Size)
```

| 광고 네트워크 | 최대 크기 | 최대 시간 |
|-------------|----------|----------|
| Facebook/Meta | 2 MB | 제한없음 |
| Google Ads | 5 MB | 60초 |
| IronSource | 5 MB | 30초 |
| AppLovin | 5 MB | 30초 |

기술 제약: 외부 HTTP 요청 불가, 모든 에셋 인라인(Base64 또는 Canvas 도형), 순수 Canvas API 또는 Phaser.js 인라인.

---

## 6. 분류 체계

분류 체계는 AI가 코드와 기획 자료를 **정확히 검색하고 재사용**하기 위한 핵심 인프라입니다. 코드와 기획은 각각 영역에 최적화된 분류 축을 가지되, Genre는 통일하여 상호 참조가 가능하도록 설계했습니다.

### 6.1 코드 분류 (Code Taxonomy)

```
Layer (3종)  ─  코드의 의존성 계층. 빌드 순서를 결정합니다.
  │
  ├── Core     장르 무관 기반 (Singleton, Pool, Event, Util)
  ├── Domain   재사용 도메인 (Battle, Character, Inventory, Quest)
  └── Game     프로젝트 특화 (Page, Popup, Element, partial class)

Genre (9종)  ─  게임 장르. DB 파티셔닝 단위입니다.
  │
  └── Generic / RPG / Idle / SLG / Simulation / Tycoon / Merge / Puzzle / Casual

Role (21종)  ─  클래스의 역할 패턴. 클래스명 접미사로 자동 분류합니다.
  │
  ├── Manager, Controller, Calculator, Processor, Handler, Listener
  ├── Provider, Factory, Service, Validator, Converter, Builder
  ├── Pool, State, Command, Observer, Helper, Wrapper
  └── Context, Config, UX

Tag  ─  메서드 단위의 행동 분류입니다.
  ├── 대기능 (7종): StateControl, ValueModification, ConditionCheck,
  │                 ResourceTransfer, DataSync, FlowControl, ResponseTrigger
  └── 소기능 (11종): Compare, Calculate, Find, Validate, Assign,
                     Notify, Delay, Spawn, Despawn, Iterate, Aggregate
```

### 6.2 기획 분류 (Design Taxonomy)

```
Domain (9종)  ─  기획자의 실제 업무 분업에 대응합니다.
  │
  ├── InGame    전투, 조작, 스킬, AI, 스테이지
  ├── OutGame   인벤토리, 장비, 가챠, 강화
  ├── Balance   성장 곡선, 재화, 난이도, 확률
  ├── Content   스토리, 퀘스트, 이벤트, 레벨디자인
  ├── BM        과금 구조, 패키지, 시즌패스
  ├── LiveOps   업데이트, 이벤트 캘린더, 보상 정책
  ├── UX        화면 전환, 튜토리얼, HUD
  ├── Social    길드, 랭킹, 채팅, 거래소
  └── Meta      업적, 컬렉션, 프레스티지

data_type (6종)  ─  기획 데이터의 형태
  │
  └── formula / table / rule / flow / config / content_data

source (6종)  ─  데이터 출처의 성격
  │
  ├── internal_original   자사 기존 프로젝트 실증 데이터
  ├── internal_produced   Workflow로 생성 + 디렉터 검증
  ├── internal_live       라이브 운영 중 수정된 데이터
  ├── observed            AI Tester 외부 게임 관찰
  ├── community           위키, 가이드 등 공개 데이터
  └── generated           AI 생성, 미검증 상태
```

### 6.3 기획↔코드 도메인 매핑

기획 결과물을 코드 Workflow로 넘길 때의 자동 변환 관계입니다.

| 기획 Domain | 코드 Domain | 대표 Role |
|------------|-------------|-----------|
| InGame | Battle, Skill, Character, Stage | Manager, Calculator |
| OutGame | Inventory, Shop, Item | Manager, Provider |
| Balance | (각 Domain의 Calculator/Processor) | Calculator, Processor |
| Content | Quest, Stage, Reward | Manager, Factory |
| BM | Shop, IAP | Service, Manager |
| LiveOps | Config + Service + Scheduler | Config, Service |
| UX | UI, Audio | Controller, UX |
| Social | Network, Guild | Manager, Service |
| Meta | Achievement, Collection | Manager, Observer |

---

## 7. 에이전트 팀 구조

### 7.1 팀 구성

```
                         ┌────────────────────────────────┐
                         │   Team Lead (Opus 4.6)         │
                         │   PM - 태스크 분배/조율/평가     │
                         │   delegate 모드                 │
                         │   lead.md                       │
                         └───────────┬────────────────────┘
              ┌──────────────┬───────┼───────┬──────────────┐
        ┌─────┴──────┐ ┌────┴────┐  │  ┌────┴────┐  ┌──────┴───────┐
        │  Designer  │ │  Main   │  │  │  Sub    │  │  Playable   │
        │(Sonnet 4.6)│ │  Coder  │  │  │ Coder×2 │  │  Coder      │
        │  기획 전문  │ │(Opus4.6)│  │  │(Son4.6) │  │ (Son 4.6)   │
        └────────────┘ │ Core+핵심│  │  │ 병렬 구현│  │  HTML5 광고  │
                       └─────────┘  │  └─────────┘  └─────────────┘
              ┌────────────────┐ ┌──┴─────────┐   ┌──────────────┐
              │ Design Valid.  │ │  Validator  │   │  DB Builder  │
              │  (Sonnet 4.6)  │ │ (Sonnet 4.6)│   │ (Sonnet 4.6) │
              │ Quality Gates  │ │  QA 검증    │   │  호출형      │
              │  소유권        │ └────────────┘   └──────────────┘
              └────────────────┘
```

### 7.2 역할별 설계 근거

| Agent | Model | 역할 범위 | 페르소나 특징 |
|-------|-------|----------|-------------|
| **Lead** | claude-opus-4-6 | 태스크 분배, 산출물 평가, Phase Gate 관리 | MUST NOT 10개 + 5종 산출물별 평가 기준표 |
| **Designer** | claude-sonnet-4-6 | L1(기획서) → L2(명세서) → L3(YAML 노드) | MUST NOT 11개 + Quality Gates 자가점검만 (최종 판정은 Design Validator) |
| **Main Coder** | claude-opus-4-6 | Phase 0 Core 전담 + _ARCHITECTURE.md + 복잡 시스템 | MUST NOT 12개 + DB 검색 필수 + Contract-First |
| **Sub Coder** | claude-sonnet-4-6 × 2 | Main 패턴 준수하여 할당 노드 구현 | MUST NOT 14개 + 4개 필수 참조 파일 |
| **Playable Coder** | claude-sonnet-4-6 | HTML5 단일 파일 플레이어블 광고 | MUST NOT 10개 + 네트워크 규격 준수 |
| **Validator** | claude-sonnet-4-6 | 5+1단계 검증 (Optional: Build Verification) | MUST NOT 10개 + 증거 기반 피드백 |
| **Design Validator** | claude-sonnet-4-6 | 6단계 검증 + **Quality Gates 소유권** | MUST NOT 10개 + 밸런스 시뮬레이터 연동 |
| **DB Builder** | claude-sonnet-4-6 | C# 파싱 → Code DB (호출형) | MUST NOT 10개 + 분류 규칙 엄격 |
| **Design DB Builder** | claude-sonnet-4-6 | 기획 파싱 → Design DB (호출형) | MUST NOT 10개 + 큐레이션 리포트 필수 |

### 7.3 기획 전용 에이전트 (Design Workflow)

| Agent | 역할 | 담당 단계 | Quality Gates |
|-------|------|----------|--------------|
| **Design DB Builder** | 기획 자료 파싱 → 정규화 → Base Design DB 저장 | 1단계, 8단계 | - |
| **Designer (design mode)** | 8단계 기획 워크플로우 실행 | 0~6단계 | 자가 점검만 |
| **Design Validator** | 교차 검증, 밸런스 시뮬, 점수 관리 | 3단계, 5단계, 7단계 | **최종 판정권 (sole owner)** |

### 7.4 병렬 실행 규칙

```
Phase 0:  Main Coder 단독
          ├── Singleton, EventManager, ObjectPool 등 Core 시스템
          └── _ARCHITECTURE.md 생성 (Sub Coder가 따를 패턴 정의)

Phase 1+: Main Coder (복잡) + Sub Coder A (일반) + Sub Coder B (일반) 병렬
          └── Validator: 완료 순서대로 즉시 검증
              ├── 통과 → Expert DB 후보
              └── 실패 → 해당 Coder에게 피드백 → 재생성

Phase 간: 이전 Phase 전체 완료 (Validator 검증 통과) 후 다음 Phase 진행
```

---

## 8. 데이터베이스 아키텍처

### 8.1 Code DB

```
db/
├── base/                          ← 파싱된 소스코드 (958개 파일)
│   ├── generic/                   ← 장르 무관 공통 (50개)
│   │   └── core/
│   │       ├── index.json         ← 경량 인덱스 (검색용)
│   │       └── files/
│   │           └── {fileId}.json  ← 상세 정보 (AST, contracts)
│   ├── rpg/    (189개)
│   ├── idle/   (282개)
│   ├── puzzle/ (120개)
│   ├── tycoon/ (92개)
│   ├── playable/ (83개)
│   ├── simulation/ (73개)
│   ├── slg/    (62개)
│   └── merge/  (7개)
│
├── expert/                        ← 검증된 고품질 코드 (20개)
│   ├── index.json
│   └── files/{fileId}.json
│
└── rules/                         ← 축적된 피드백 규칙
    ├── generic_rules.json
    ├── genre_rules.json
    └── domain_rules.json
```

**인덱스 스키마** (검색 시 먼저 읽는 경량 데이터):
```json
{
  "fileId": "battle_manager_001",
  "layer": "Domain",
  "genre": "Rpg",
  "role": "Manager",
  "system": "Battle",
  "score": 0.6,
  "provides": ["battle_result", "damage_calculation"],
  "requires": ["character_stats", "skill_data"]
}
```

### 8.2 Design DB

```
db/design/
├── base/                          ← 기획 자료 (97개 파일)
│   └── {genre}/
│       ├── {domain}/              ← 레이어 2: 세부 요소 태깅
│       │   ├── index.json
│       │   └── files/{designId}.json
│       └── projects/              ← 레이어 1: 프로젝트 통짜
│           └── {project}.json
│
├── expert/                        ← 검증된 기획 (score >= 0.6)
│   ├── index.json
│   └── files/{designId}.json
│
└── rules/                         ← 기획 피드백 규칙
    ├── generic_rules.json
    ├── genre_rules.json
    └── domain_rules.json
```

### 8.3 2-Layer 저장 설계 근거

Design DB는 2개 레이어로 저장됩니다. 이유:

| 레이어 | 용도 | 왜 필요한가 |
|--------|------|------------|
| **레이어 1** (프로젝트 단위) | "이 게임의 전체 기획이 어떤 구조였고 결과가 어땠는지" | 프로젝트 간 비교, 전체 맥락 보존 |
| **레이어 2** (요소 단위 태깅) | "데미지 공식만", "가챠 확률만" 뽑아서 교차 비교 | AI가 특정 기획 요소 생성 시 유사 사례 검색 |

레이어 1만 있으면 검색이 불가능하고, 레이어 2만 있으면 맥락이 손실됩니다. 두 레이어의 조합으로 "검색 가능하면서 맥락도 보존"하는 구조를 구현했습니다.

### 8.4 인덱스-파일 분리 설계 근거

모든 DB는 `index.json` + `files/` 구조로 되어 있습니다.

```
DB 규모가 커져도 인덱스만 읽으면 검색 가능 (index.json ≈ 수 KB)
상세 정보는 필요할 때만 개별 파일 로드 (files/{id}.json)
대용량 JSON 한 번에 로드하는 실수 방지
```

> **Git 관리 정책**: DB 데이터 파일(`db/base/`, `db/expert/`, `db/design/base/`, `db/design/expert/`)은 대용량이므로 `.gitignore`로 제외하여 로컬에서만 관리합니다. Git에는 피드백 규칙(`db/rules/`, `db/design/rules/`)과 도구(스크립트, 에이전트, 커맨드)만 추적합니다.

---

## 9. 신뢰도 점수 시스템

### 9.1 코드 신뢰도

| 이벤트 | 점수 변동 |
|--------|----------|
| 초기 저장 | 0.4 |
| 피드백 반영 완료 | +0.2 |
| 다른 프로젝트에서 재사용 성공 (1회당) | +0.1 |
| 다른 프로젝트에서 재사용 실패 (1회당) | -0.15 |
| 다른 장르에서 재사용 성공 | +0.1 (Generic 승격 검토) |
| **Expert DB 승격 임계값** | **>= 0.6** |

### 9.2 기획 신뢰도

기획은 코드와 달리 "에러 없음 = 품질"이 아닙니다. "재밌는가, 성과가 났는가, 돈을 벌었는가"가 중요합니다. 이를 반영하여:

**자동 점수 (게이트키퍼)**: AI가 판단하는 3가지 지표의 가중 평균
```
(논리 완결성 × 0.4) + (밸런스 안정성 × 0.4) + (구현 복잡도 × 0.2)

>= 0.35 → 초기 점수 0.4 부여
<  0.35 → 초기 점수 0.3 부여 (저품질 경고)
```

**이벤트 기반 점수**: 실제 사용과 검증을 통해 변동
```
디렉터 승인 (피드백 없이)  +0.2
피드백 반영 후 승인        +0.1
다른 프로젝트 참조 성공     +0.1
참조 후 부적합 판정        -0.1  (사유 기록 필수)
시뮬레이션 결과 괴리 >20%  -0.15
3회 참조, 0회 채택         -0.2  (Expert 강등 검토)
```

**사후 라벨링** (출시 후, 별도 필드):
```
시장 성과 등급: S / A / B / C / F
원인 분석 태그: 아는 만큼만 기록

※ 사후 라벨은 신뢰도 점수에 반영하지 않음
   → 시장 성과는 마케팅, 타이밍 등 기획 외 요인에 영향받으므로
      기획 품질 점수와 혼합하면 DB 오염 발생
```

### 9.3 감점 원칙

```
1. 감점은 반드시 사유를 명시적으로 기록해야 적용
2. "원인 불명"인 경우 감점하지 않음 (잘못된 규칙 학습 방지)
3. 감점으로 0.6 미만이 되면 Expert DB에서 Base DB로 강등
```

---

## 10. AI Tester & Virtual Player

### 10.1 개요

AI Tester는 **실제 게임을 플레이하여 기획 의도를 실증 검증**하는 시스템입니다. BlueStacks 에뮬레이터 + ADB를 통해 게임을 자동으로 플레이하고, 화면 인식 → 의사결정 → 입력 실행의 루프를 수행합니다.

**두 가지 역할**:
- **PRIMARY**: 외부 게임 → Design DB 데이터 수집 (Stage 1 입력). 10명 AI 관찰로 32개 파라미터 추정, 정확도 85~89.5%
- **SECONDARY**: 자사 게임 빌드 검증 (Stage 7). 밸런스 예측값 vs 실측값 비교

### 10.2 4-Layer 지능 아키텍처

```
Layer 4: Genre Schema
  └── RPG / Idle / Merge / SLG / Puzzle 별 전문 전략

Layer 3: Adaptive (적응형 학습)
  ├── failure_memory    실패 기억 → 같은 실수 반복 방지
  ├── loop_detector     루프 탐지 → 무한 반복 탈출
  ├── spatial_memory    공간 기억 → UI 위치 학습
  └── plan_adapter      계획 적응 → 상황에 맞게 계획 수정

Layer 2: Reasoning (의사결정)
  ├── GOAP Planner      Goal-Oriented Action Planning
  ├── goal_library      목표 라이브러리
  ├── goal_reasoner     목표 추론
  └── utility_scorer    유틸리티 점수 기반 행동 선택

Layer 1: Perception (인지)
  ├── OCR Reader        텍스트 인식 (레벨, 재화, 메뉴)
  ├── Gauge Reader      게이지 인식 (HP, MP, 경험치)
  ├── State Reader      게임 상태 판별
  └── Screen Analyzer   화면 분류 (ReferenceDB 기반)
```

### 10.3 활용 시나리오

| 시나리오 | 방법 | 목적 |
|---------|------|------|
| **자사 게임 가속 테스트** | 10~20배속 + AI 플레이 | 30일치 플레이를 반나절에 완료, 기획 예측 vs 실측 비교 |
| **외부 게임 분석** | 실시간 관찰 (10명 AI 전문가) | 32개 파라미터 추정 → Design DB 저장 |
| **대규모 시뮬레이션** | 페르소나 × N 인스턴스 | 1000명 가상 유저 동시 시뮬 → 병목/이탈 지점 발견 |

### 10.4 AI Tester → Design DB 변환

AI Tester의 32개 파라미터(9카테고리)가 Design DB의 9개 도메인으로 자동 매핑됩니다.

```
progression (5)  → Content + Balance
growth (5)       → Balance
equipment (4)    → OutGame + Balance
combat (6)       → InGame + Balance
gacha (4)        → OutGame + BM
economy (5)      → Balance + BM
system (1)       → InGame
visual (1)       → UX
architecture (1) → (제외: 코드 영역)
```

---

## 11. 도구 및 스크립트

### 11.1 슬래시 커맨드

| 커맨드 | 용도 | 담당 Agent |
|--------|------|-----------|
| `/parse-source [path]` | C# 소스코드 → Code DB 파싱 | DB Builder |
| `/parse-design [path]` | 기획 문서 → Design DB 파싱 | Design DB Builder |
| `/generate-design [input]` | 기획서 + 명세서 생성 | Designer |
| `/generate-design-v2 [input]` | 8단계 기획 워크플로우 실행 | Designer (design mode) |
| `/generate-code [yaml]` | YAML 기획서 → C# 코드 생성 | Main/Sub Coder |
| `/validate-code [path]` | 코드 5단계 검증 | Validator |
| `/validate-design [project]` | 기획 4단계 검증 | Design Validator |
| `/sync-live [project]` | 라이브 데이터 → DB 동기화 | Design DB Builder |

### 11.2 자동 트리거 스킬

| 스킬 | 트리거 조건 | 역할 |
|------|-----------|------|
| `db-search` | 코드 생성 중 DB 참조 필요 시 | 5단계 우선순위 검색 |
| `game-patterns` | 게임 아키텍처 설계 시 | 설계 패턴 가이드 |
| `unity-csharp` | C# 코드 작성 시 | Unity 코딩 규칙 |

### 11.3 Node.js 스크립트

**DB 가공 & 파싱**
| 스크립트 | 기능 |
|---------|------|
| `parser.js` | C# 소스 파싱 → AST → Code DB |
| `parser.py` | C# 소스 파싱 (Python 버전) |
| `design-parser.js` | 기획 문서 정규화 → Design DB |
| `batch-parse-project.js` | Unity JSON 테이블 일괄 파싱 |
| `batch-parse-yaml-designs.js` | YAML 기획서 일괄 파싱 |
| `migrate-design-domains.js` | 도메인 마이그레이션 도구 |

**DB 검색**
| 스크립트 | 기능 |
|---------|------|
| `db-search.js` | Code DB 검색 (장르/레이어/역할 필터) |
| `design-db-search.js` | Design DB 검색 (도메인/장르/데이터타입 필터) |
| `format-search.js` | 검색 결과 포매팅 유틸리티 |

**시뮬레이션 & 검증**
| 스크립트 | 기능 |
|---------|------|
| `balance-simulator.js` | 경제/전투/가챠 시뮬레이션 (seeded PRNG) |
| `play-verification.js` | AI Tester 기반 플레이 검증 (accelerated/longterm/mass) |
| `virtual-player-bridge.js` | Virtual Player ↔ Design DB 연동 |

**품질 & 분석**
| 스크립트 | 기능 |
|---------|------|
| `design-version.js` | 기획 버전 관리 (semver + phase + score) |
| `generate-kpi.js` | 프로젝트별 KPI 리포트 자동 생성 |
| `quality_report.js` | 코드 품질 리포트 |
| `analyze.js` | Code DB 분석 |
| `c10-to-design-db.js` | AI Tester C10 파라미터 → Design Domain 변환 |
| `design-to-code-bridge.js` | 기획 정보 → 코드 생성 입력 변환 |

### 11.4 공유 라이브러리 (scripts/lib/)

| 라이브러리 | 기능 | 설계 이유 |
|-----------|------|----------|
| `yaml-utils.js` | 통합 YAML 파서 (js-yaml fallback) | 6개의 중복 파서를 통합하여 일관성 확보 |
| `safe-io.js` | 원자적 파일 쓰기 (.tmp → rename) | Windows 환경에서 파일 손상 방지 |
| `domain-utils.js` | 도메인 정규화 ("combat"→"ingame") | 비정형 입력을 표준 분류로 통일 |
| `score-manager.js` | 점수 계산 (INITIAL 0.4, Expert >= 0.6) | 점수 로직을 중앙화하여 일관성 보장 |

---

## 12. 품질 보증 체계

### 12.1 코드 검증 5+1단계

| 단계 | 검증 항목 | 실패 시 |
|------|----------|--------|
| 1. Syntax | 컴파일 오류, 문법 오류 | 즉시 수정 후 재검증 |
| 2. Dependency | 참조 누락, 순환 의존성 | 의존성 정리 후 재검증 |
| 3. Contract | provides/requires 일치 여부 | 인터페이스 재조정 |
| 4. NullSafety | null 참조 가능성, 방어 코드 | null 체크 추가 |
| 5. Pattern | 아키텍처 패턴 준수 | Main Coder 패턴 참조하여 재작성 |
| 6. Build (Optional) | Unity batchmode 빌드 검증 | CS 에러 피드백 전달 |

### 12.2 Playable 검증 4단계

| 단계 | 검증 항목 |
|------|----------|
| 1. Isolation | 외부 HTTP 요청 없음 |
| 2. Interaction | 터치 + 마우스 이벤트 존재 |
| 3. CTA | Install 버튼 + URL + 표시 트리거 |
| 4. Size | 파일 크기 < 네트워크 제한 |

### 12.3 기획 검증 6단계

| 단계 | 검증 항목 |
|------|----------|
| 1. Cross-Consistency | 시스템↔밸런스, 콘텐츠↔시스템, BM↔밸런스, UX↔시스템 |
| 2. User Journey Simulation | Day 1~30 페르소나 기반 진행 추적 |
| 3. Gap Detection | 참조 누락, 미정의 아이템, 접근 불가 기능 |
| 4. Self-Verification | 내부 모순, 완성도 체크, 빌드오더 사이클 검증 |
| 5. Quality Gates (6종) | Cross-Layer Naming / L3 Completeness / Dependency / logicFlow / Copy-Paste / Cross-Doc |
| 6. Build Verification (Optional) | 밸런스 시뮬레이터 전체 모드 실행 |

### 12.4 플레이 검증 성공/실패 기준

| 지표 | Pass | Warn | Fail |
|------|------|------|------|
| 레벨 도달 시간 (예측 대비) | ±15% | ±15~30% | >±30% |
| 재화 잔고 (예측 대비) | ±20% | ±20~40% | >±40% |
| DPS 밸런스 (최강 vs 평균) | ±10% | ±10~25% | >±25% |
| D7 리텐션 (목표 대비) | ±5%p | ±5~10%p | >±10%p |
| 스테이지 클리어율 (목표 대비) | ±10% | ±10~20% | >±20% |

### 12.5 디렉터 개입 수준 (Design Workflow)

| 수준 | 조건 | AI 행동 |
|------|------|---------|
| **Level 1 — 자동** | DB 참조 기반 수치 미세조정, 콘텐츠 양산, 검증 통과 DB 저장 | AI 자율 실행 |
| **Level 2 — 보고** | 시뮬레이션 이상치 수정, 경미한 불일치 조정 | 진행하되 결과 보고 |
| **Level 3 — 승인** | 디자인 필러 변경, 시스템 추가/삭제, BM 과금 결정 | 디렉터 승인 필수 |

---

## 13. 프로젝트 구조

```
E:\AI\
│
├── CLAUDE.md                          # 마스터 컨텍스트 (분류 체계, 규칙, 설정 일체)
├── README.md                          # 이 문서
│
├── .claude/
│   ├── agents/                        # 커스텀 에이전트 정의 (9종, 전체 영어)
│   │   ├── lead.md                    #   PM — 태스크 분배/평가 (Opus 4.6)
│   │   ├── designer.md                #   기획 AI (Sonnet 4.6)
│   │   ├── main-coder.md              #   메인 코드 생성 AI (Opus 4.6)
│   │   ├── sub-coder.md               #   서브 코드 생성 AI (Sonnet 4.6)
│   │   ├── playable-coder.md          #   HTML5 광고 AI (Sonnet 4.6)
│   │   ├── validator.md               #   코드 검증 AI (Sonnet 4.6)
│   │   ├── db-builder.md              #   코드 DB 구축 AI (Sonnet 4.6)
│   │   ├── design-db-builder.md       #   기획 DB 구축 AI (Sonnet 4.6)
│   │   └── design-validator.md        #   기획 검증 AI — Quality Gates 소유 (Sonnet 4.6)
│   ├── commands/                      # 슬래시 커맨드 (8종)
│   └── skills/                        # 자동 트리거 스킬 (3종)
│
├── db/                                # 데이터베이스
│   ├── base/                          #   Code Base DB (.gitignore — 로컬 전용)
│   ├── expert/                        #   Code Expert DB (.gitignore — 로컬 전용)
│   ├── rules/                         #   코드 피드백 규칙 (Git 추적)
│   ├── design/
│   │   ├── base/                      #     Design Base DB (.gitignore — 로컬 전용)
│   │   ├── expert/                    #     Design Expert DB (.gitignore — 로컬 전용)
│   │   └── rules/                     #     기획 피드백 규칙 (Git 추적)
│   └── ui_meta/                       #   UI 프리팹 메타데이터 (Git 추적)
│
├── projects/                          # 프로젝트별 작업 폴더
│   ├── {ProjectName}/
│   │   ├── designs/                   #   기획서 (Layer 1/2/3)
│   │   ├── design_workflow/           #   8단계 워크플로우 결과물
│   │   ├── output/                    #   생성된 코드 (C# / HTML5)
│   │   └── feedback/                  #   검증 피드백
│   └── Playable/                      #   플레이어블 광고 프로젝트들
│
├── scripts/                           # 자동화 스크립트 (18개 + lib 4개)
│   ├── lib/                           #   공유 라이브러리 (4종)
│   ├── balance-simulator.js           #   밸런스 시뮬레이션
│   ├── db-search.js                   #   Code DB 검색
│   ├── design-db-search.js            #   Design DB 검색
│   └── ...
│
├── virtual_player/                    # AI Virtual Player (Python)
│   ├── brain/                         #   지능 엔진
│   ├── perception/                    #   화면 인식
│   ├── reasoning/                     #   의사결정 (GOAP)
│   ├── adaptive/                      #   적응형 학습
│   ├── genre/                         #   장르별 스키마
│   └── navigation/                    #   화면 네비게이션
│
├── ai_tester/                         # Cross-genre 게임 테스트 프레임워크 (개발 중)
│   ├── core/                          #   ADB, 상태 추적, UI 탐색
│   ├── strategies/                    #   장르별 전략
│   └── runner.py                      #   실행 엔진
│
├── docs/                              # 문서
│   ├── WORKFLOW.md                    #   통합 워크플로우 문서
│   └── Claude_Code_TMux_Guide.txt    #   TMux 가이드
│
├── proposal/                          # Workflow 설계 문서
│   ├── workflow/                      #   현행 워크플로우 (정본)
│   │   ├── AI_workflow_개발.md        #     코드 Workflow 원본 (6단계)
│   │   ├── AI_workflow_기획_v2.0.md   #     기획 Workflow 정본 (8단계)
│   │   └── AI_workflow_통합_구조.md   #     두 Workflow 구별/연결/진화
│   └── reviews/                       #   리뷰 및 히스토리
│       ├── AI_workflow_개발_원본.txt  #     코드 Workflow 원본 텍스트 (보존)
│       ├── AI_workflow_기획_v1.0.md   #     기획 Workflow v1.0 (대체됨)
│       └── AI_workflow_기획_*리뷰.md  #     리뷰 문서 (3건)
│
├── History/                           # 프로젝트별 KPI 및 히스토리
│   ├── KPI_Template.md
│   └── {ProjectName}/
│       ├── KPI.md
│       └── Project_History.md
│
└── Feedback/                          # 워크플로우 개선 피드백
```

---

## 14. 실행 방법

### 14.1 전제 조건

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI 설치
- Node.js 18+
- Python 3.13+ (AI Tester 사용 시)
- BlueStacks + ADB (플레이 검증 시)

### 14.2 게임 코드 생성 (Unity)

```bash
# 단일 세션
/generate-design "Idle RPG, 방치 수익 + 캐릭터 수집" --genre idle

# Agent Team 병렬 생성
게임을 만들어줘. Idle RPG, 방치 수익 + 캐릭터 수집. Agent Team으로 병렬 진행해줘. Coder 3명.
```

### 14.3 플레이어블 광고 생성

```bash
# 기획 + 코드 한 번에
match3 플레이어블 광고를 만들어줘. 캔디 테마. Agent Team으로 진행해줘.
```

### 14.4 기획서만 생성 (코드 없이)

```bash
# 8단계 기획 워크플로우
/generate-design-v2 "Idle RPG, 방치 수익 + 캐릭터 수집" --genre idle --workflow_mode design
```

### 14.5 기존 코드/기획 DB에 추가

```bash
# C# 소스코드 파싱
/parse-source E:\Projects\MyGame\Assets\Scripts --genre rpg

# 기획 문서 파싱
/parse-design E:\Docs\GameDesign --genre idle

# 일괄 파싱 (스크립트)
node scripts/batch-parse-project.js --tables E:\Projects\MyGame\Tables --genre idle --project MyGame
```

### 14.6 밸런스 시뮬레이션

```bash
node scripts/balance-simulator.js --input balance_params.yaml --mode economy --seed 42
node scripts/balance-simulator.js --input balance_params.yaml --mode combat --iterations 10000
```

### 14.7 DB 검색

```bash
# Code DB
node scripts/db-search.js --genre idle --layer Domain --role Manager --top 10

# Design DB
node scripts/design-db-search.js --genre idle --domain balance --top 20 --json
```

---

## 15. 검증된 프로젝트

| 프로젝트 | 장르 | 생성 파일 | 주요 결과 |
|---------|------|----------|----------|
| **DropTheCat** | Puzzle | 50개 C# | 26 노드, 전체 파이프라인 1회전 완료 |
| **MagicSort** | Puzzle | 37개 C# | 정렬 퍼즐 전체 시스템 생성 |
| **VeilBreaker** | RPG (Idle) | 51개 C# | 41 노드, 전투/캐릭터/장비 시스템 |
| **CarMatch** | Match3 | 34개 수정 | 기존 코드 대규모 수정, 83건 이슈 처리 |
| **IdleMoney** | Idle | 역설계 완료 | 54 시스템 역설계, 89건 Design DB, B+ 등급 |
| **Playable 광고** | 다수 | 8+ HTML5 | pin_pull, match3, runner, SLG 등 |

### KPI 추적 결과

| 지표 | DropTheCat | CarMatch | VeilBreaker |
|------|-----------|----------|-------------|
| 전체 노드 수 | 26 | 34 (수정) | 41 |
| DB 참조율 | 0% (초기) | 0% (초기) | 0% (초기) |
| 피드백 횟수 | 8 | 83 | 5 |
| 빌드 성공 여부 | 미확인 | 수정 성공 | 미확인 |

> **참고**: DB 참조율 0%는 초기 프로젝트에서 Expert DB가 아직 축적되지 않았기 때문입니다. 프로젝트가 진행됨에 따라 Expert DB가 성장하면 자연스럽게 참조율이 상승하는 구조입니다.

---

## 16. 기술적 의사결정 근거

### 16.1 왜 YAML인가 (기획서 형식)

**선택지**: JSON, YAML, Markdown, 자유 형식

**결정**: YAML

**근거**:
- AI가 구조화된 데이터를 정확히 파싱해야 하므로 자유 형식/Markdown 제외
- JSON은 주석 불가, 가독성 낮음 — 기획자가 직접 읽고 수정해야 하므로 부적합
- YAML은 주석 가능, 계층 구조 명확, 사람이 읽기 쉬움
- AI의 YAML 생성 정확도가 JSON과 동등하게 높음

### 16.2 왜 3-Layer 기획서인가

**문제**: AI에게 기획서를 주면 해석이 모호하여 의도와 다른 코드가 나옴

**해결**: 기획서를 3단계로 구조화하여 점진적으로 구체화

```
Layer 1: 게임 기획서     — 사람이 읽기 위한 문서 (컨셉, 시스템 관계)
Layer 2: 시스템 명세서    — AI가 이해하기 위한 구조 (각 시스템의 규칙, 데이터)
Layer 3: AI_기획서 YAML  — 코드로 직접 변환 가능한 최종 형식 (노드별 logicFlow)
```

Layer 1만 있으면 AI가 해석을 많이 해야 하고, Layer 3만 있으면 전체 맥락이 없습니다. 3단계 구조는 "사람의 의도"를 "코드의 구조"로 점진적으로 변환하는 번역 과정입니다.

### 16.3 왜 Main Coder에 Opus를 쓰는가

**문제**: Core 시스템(Singleton, EventManager, Pool)은 프로젝트 전체의 기반이므로 설계 실수가 전체에 전파됨

**결정**: Main Coder에 Opus (고추론 모델), Sub Coder에 Sonnet (고속 모델)

**근거**:
- Phase 0의 Core 아키텍처 설계는 전체 시스템 구조를 이해해야 하므로 추론 능력이 핵심
- Main Coder가 `_ARCHITECTURE.md`를 생성하면, Sub Coder는 이 패턴을 따라 구현만 하면 됨
- Sub Coder는 이미 정의된 패턴을 빠르게 구현하는 것이 중요하므로 속도 우선
- Opus 1 + Sonnet 2 조합이 Opus 3보다 비용 효율적이면서 품질 유지

### 16.4 왜 밸런스 시뮬레이션을 JS로 분리하는가

**문제**: LLM은 수학적 시뮬레이션(확률, 장기 경제 모델링)에서 부정확함

**결정**: AI가 파라미터를 YAML로 생성 → `balance-simulator.js`가 수학 실행 → AI가 결과 해석

**근거**:
- LLM은 "30일간 재화 Source/Sink 추적" 같은 반복 계산에서 누적 오차 발생
- JavaScript로 시뮬레이션하면 정확한 수치 결과 보장
- AI는 결과 해석(이상치 발견, 조정 제안)에 집중 — 이것이 AI의 강점
- Seeded PRNG를 사용하여 동일 파라미터에 대해 재현 가능한 결과

### 16.5 왜 인덱스-파일 분리 구조인가

**문제**: DB 규모가 커지면(1000+ 파일) 전체 로드 시 메모리/시간 문제

**결정**: `index.json` (경량 메타데이터) + `files/{id}.json` (상세 데이터) 분리

**근거**:
- 검색 시 인덱스만 읽으면 됨 (수 KB)
- 상세 정보는 매칭된 파일만 개별 로드
- AI의 컨텍스트 윈도우를 효율적으로 사용
- 파일 단위이므로 Git diff가 깔끔함

### 16.6 왜 감점에 사유 기록이 필수인가

**문제**: 원인 불명인 감점이 축적되면 AI가 잘못된 패턴을 "나쁜 것"으로 학습

**결정**: 감점 시 반드시 사유 기록, "원인 불명"이면 감점 불가

**근거**:
- 게임의 실패 원인은 기획 외 요인(마케팅, 타이밍, 경쟁작)일 수 있음
- 근거 없는 감점이 축적되면 DB 전체의 신뢰도가 오염됨
- 사후 라벨(시장 성과)과 신뢰도 점수를 별도 관리하는 것도 같은 이유
- "알 수 있는 것만 점수에 반영"하는 보수적 접근이 DB 장기 건전성 확보

### 16.7 왜 사후 라벨을 신뢰도 점수에 반영하지 않는가

**문제**: "S등급 게임의 기획 = 좋은 기획"이라는 가정이 항상 성립하지 않음

**결정**: 사후 라벨은 별도 필드, 검색 필터로만 활용

**근거**:
- 시장 성과가 좋아도 기획이 나쁠 수 있음 (IP 파워, 마케팅 버프)
- 시장 성과가 나빠도 기획이 좋을 수 있음 (시장 타이밍, 경쟁작)
- 두 지표를 혼합하면 "마케팅이 좋았던 게임의 밸런스 공식"이 고점수를 받는 오류
- 분리하면 "이 공식을 쓴 게임이 A등급이었다"는 맥락은 유지하면서, 공식 자체의 품질 점수는 독립적으로 관리

---

## 17. Workflow 검증 현황

> 2026-02-26 기준

### 검증 결과 요약

| 컴포넌트 | 상태 | 비고 |
|---------|------|------|
| Code Workflow (Phase 0~4) | PASS | 4 Phase 구조, Agent Team 병렬, Validator 5단계 — 문서 간 일관성 확인 |
| Design Workflow (Stage 1~6) | PASS | 8단계 파이프라인, 피드백 14종, Quality Gates 6종 — v2.0 기준 통일 완료 |
| Design Workflow (Stage 7~8) | PASS (문서) | 플레이 검증 + 라이브 동기화 — 스크립트 구현 완료 (play-verification.js, design-version.js) |
| AI Tester | PASS (구현) | 4-Layer 아키텍처 코드 완료, Ash&Veil 실전 테스트 완료 (Lv.25→31) |
| Agent 정의 (9종) | PASS | lead, designer, main-coder, sub-coder, playable-coder, validator, db-builder, design-db-builder, design-validator — 전체 영어 재작성, MUST NOT 억제문 + Hallucination Prevention 추가 (2026-03-06) |

### 문서 정합성 (2026-02-26 수정 완료)

- `CLAUDE.md` ↔ `WORKFLOW.md`: 8단계 구조 통일, 피드백 14종 표준화
- `proposal/workflow/AI_workflow_기획_v2.0.md`: 정본 — 모든 하위 문서의 기준
- `proposal/workflow/AI_workflow_통합_구조.md`: 코드/기획 두 Workflow 구별 및 연결 문서화

### 알려진 제한사항

- AI Tester Stage 7 실행은 빌드(APK)가 필요하여, 현재까지 Ash&Veil(외부 게임)에서만 실전 테스트 완료
- Stage 8 라이브 동기화는 L1(수동) 수준이며, L2(반자동) → L3(자동) 확장 예정
- 대규모 가상 유저 시뮬레이션 (Stage 7-3)은 Phase A(10명) MVP 단계

---

## License

This project is proprietary software. All rights reserved.

---

*GameForge v2.2 — 2026.03 (Agent 9종 영어 재작성, Lead Agent 신설, LLM 모델 업데이트, Quality Gates 소유권 일원화, Validator Build Verification 추가)*
