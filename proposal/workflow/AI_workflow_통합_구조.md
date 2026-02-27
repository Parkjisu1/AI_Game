# AI Workflow 통합 구조

> **Purpose**: AI_Workflow_개발(Code)과 AI_Workflow_기획(Design) 두 워크플로우의 구별, 연결, 진화를 한눈에 정리한 문서
> **Created**: 2026-02-26
> **Last Updated**: 2026-02-27
> **Source Documents**:
> - `proposal/workflow/AI_workflow_개발.md` — 코드 Workflow 원본 (6단계, .txt에서 .md로 변환)
> - `proposal/workflow/AI_workflow_기획_v2.0.md` — 기획 Workflow 정본 v2.1 (Stage 0~8)

---

## 1. 개요: 두 Workflow의 정의와 관계

이 시스템은 게임 제작을 **기획**과 **코드** 두 개의 독립적인 파이프라인으로 분리합니다.
각 파이프라인은 자체 DB, 자체 검증 루프, 자체 Expert DB를 갖고 독립 실행이 가능하지만,
연결하면 기획서 생성 → 코드 생성 → 플레이 검증까지 이어지는 완전한 게임 제작 파이프라인이 됩니다.

```
AI_Workflow_개발 = Code Workflow (코드 생성 파이프라인)
  범위: 소스코드 DB 가공 → 기획서 기반 코드 생성 → 검증 → Expert Code DB 축적
  입력: C# 소스코드 + AI_기획서(YAML)
  출력: Unity C# 코드 / HTML5 Playable 광고
  DB:   db/base/{genre}/, db/expert/, db/rules/

AI_Workflow_기획 = Design Workflow (기획 생성 파이프라인)
  범위: 기획 자료 DB 가공 → 기획서 생성 → 검증 → Expert Design DB 축적
  입력: 게임 컨셉/URL/레퍼런스 + Design DB
  출력: 3-Layer 기획서 (game_design → system_spec → AI_기획서 YAML)
  DB:   db/design/base/{genre}/, db/design/expert/, db/design/rules/
```

**공통 원칙**: 역할 전환에 의한 환각현상 방지를 위해 AI를 분리합니다.
- 코드: DB 가공 AI / 기획서 제작 AI / 코드 생성 AI (3분리)
- 기획: DB 가공 AI / 기획 생성 AI / 검증 AI (3분리)

---

## 2. AI_Workflow_개발 (Code Workflow)

### 2-1. 원본 6단계 요약

`AI_workflow_개발.txt`에서 정의한 원래 구조:

| 단계 | 명칭 | 핵심 내용 |
|------|------|-----------|
| 1단계 | Base Code DB 가공 | 자사 소스를 Layer > Genre > 대기능 > 소기능으로 분류, DB 축적 |
| 2단계 | 기획서 제작/가공 | URL/컨셉 입력 → 기획서 → 시스템 명세서 → AI_기획서(YAML) |
| 3단계 | 코드 생성 | AI_기획서 파싱 → DB 검색 → 코드 생성 → 1차 자가 검증 |
| 4단계 | 피드백/재생성 | 사용자 검수 → 피드백 작성 → 코드 재생성 |
| 5단계 | 재생성 평가 | 피드백 반영 확인, 히스토리 분석, 차이점 기록 |
| 6단계 | DB 축적 | 신뢰도 점수 계산 → Expert DB 저장(≥0.6) → Rules 추출 |

### 2-2. 원본 대비 디벨롭된 항목

| 영역 | Before (원본) | After (현재) |
|------|--------------|-------------|
| **분류 체계** | Layer 2종 (Core, Domain) + Role | Layer 3종 (Core, Domain, **Game** 추가) + Role 21종 (UX 추가) |
| **장르** | 7종 (Generic~Merge) | 9종 (**Puzzle, Casual** 추가) |
| **기획서 생성** | 원본 2단계에 포함 (단일 AI) | **독립 Workflow로 분리** (Design Workflow Stage 0~8) |
| **코드 생성** | 단일 AI가 순차 진행 | **Agent Team 병렬** — Main Coder(Opus) + Sub Coder×2(Sonnet) |
| **검증** | 사용자 수동 검수 | **Validator Agent 5단계 자동 검증** |
| **피드백+평가+축적** | 4·5·6단계 분리 | **Phase 4로 통합** (검증→피드백→재생성→축적 원스톱) |
| **Platform** | Unity C#만 | **Playable 광고(HTML5)** 추가 — Playable Coder Agent |
| **SDK 지원** | 없음 | Firebase/AdMob/IAP **조건부 컴파일 가이드** |
| **빌드 설정** | 없음 | **Android 빌드 설정 + 에러 패턴 5종** |
| **씬 구성** | 없음 | **3씬 규칙 + SceneBuilder 패턴** |

### 2-3. 현재 Phase 구조 (Code Workflow)

원본 6단계를 4개 Phase로 재편:

| Phase | 원본 대응 | 내용 |
|-------|-----------|------|
| Phase 1: DB 구축 | 1단계 | 소스 파싱 → Layer/Genre/Role/Tag 분류 → DB 저장 |
| Phase 2: 기획서 변환 | 2단계 (변환 부분만) | Design Stage 6 완료된 기획서 → 시스템 명세서 → AI_기획서 |
| Phase 3: 코드 생성 | 3단계 | AI_기획서 → DB 검색 → 코드 생성 → 자가 검증 |
| Phase 4: 검증 & 축적 | 4·5·6단계 통합 | Validator 검증 → 피드백 → 재생성 → 점수 산출 → Expert DB |

**핵심 변경**: 원본 2단계의 "기획서 제작" 기능이 Design Workflow로 완전 분리됨.
현재 Phase 2는 이미 완성된 기획서를 코드용 포맷으로 **변환**하는 역할만 수행.

---

## 3. AI_Workflow_기획 (Design Workflow)

### 3-1. Stage 0~8 요약

원본에 없던 **완전 신규** 워크플로우. `AI_workflow_기획_v2.0.md`(v2.1)에서 정의.

| 단계 | 명칭 | 핵심 내용 |
|------|------|-----------|
| Stage 0 | 장르별 설계 표준 + 디렉션 히스토리 | 장르별 파라미터 정의 + 디렉터 판단 패턴 축적 (장르 최초 1회 + 상시 보완) |
| Stage 1 | Base Design DB 가공 | 기획 자료/AI Tester 관찰 → 정규화(0단계 스키마 참조) → 설계 의도 분석 → 디렉터 큐레이션 → DB 축적 |
| Stage 2 | 기획 생성 | 2-1 컨셉 → 2-2 시스템 → 2-3 밸런스∥2-4 콘텐츠 → 2-5 BM |
| Stage 3 | 통합 검증 | 교차 일관성 + 유저 여정 시뮬 + 누락 검출 |
| Stage 4 | 디렉터 검수 | 사람이 검수, 피드백 없으면 Stage 6으로 |
| Stage 5 | 재생성 평가 | 피드백 반영 확인 + 히스토리 분석 |
| Stage 6 | DB 축적 | 신뢰도 점수 산출 → Expert Design DB(≥0.6) → Rules 추출 |
| Stage 7 | 플레이 검증 | AI Tester — 가속/장기/대규모 시뮬 (빌드 필요) |
| Stage 8 | 라이브 동기화 | 밸런스 패치 → 버전 추가 → KPI 기록 |

### 3-2. 원본에 없던 완전 신규 항목

Design Workflow는 원본 `AI_workflow_개발.txt`에 존재하지 않았습니다.
원본 2단계 "기획서 제작"에서 **기획서 구조·명세서 구조·AI 기획서 구조**만 정의했을 뿐,
기획 자체의 생성 파이프라인(DB → 생성 → 검증 → 축적)은 없었습니다.

신규 추가된 핵심 개념:
- **Stage 0: 장르별 설계 표준** — 장르마다 "무엇을 정의해야 하는지" 기준 (구성요소 맵, 파라미터, DB 스키마)
- **Stage 0: 디렉션 히스토리** — 디렉터의 반복 판단 패턴을 자동 축적 (L1 수동 → L2 반자동 → L3 자동)
- **Stage 1: 설계 의도 분석 + 디렉터 큐레이션** — 기계적 파싱이 아닌, AI 분석 + 디렉터 승인 후 DB 저장
- **Design DB** (9 Domain × 9 Genre) — 기획 전용 데이터베이스
- **기획 도메인 9종** — InGame, OutGame, Balance, Content, BM, LiveOps, UX, Social, Meta
- **2-Layer 저장** — 프로젝트 통짜(Layer 1) + 세부 요소 태깅(Layer 2)
- **피드백 14종 카테고리** — SYSTEM(3) + BALANCE(4) + CONTENT(2) + BM(2) + UX(2) + DIRECTION(1)
- **Design 신뢰도 점수** — 자동 점수 3종(논리 완결성·밸런스 안정성·구현 복잡도) → 신뢰도
- **Quality Gates 6종** — IdleMoney 실전 교훈 반영 (명칭 일관성, L3 완성도, 의존성 등)
- **AI Tester** — PRIMARY: 외부 게임 관찰(Stage 1 입력) / SECONDARY: 자사 빌드 검증(Stage 7)
- **라이브 동기화** — 출시 후 버전 관리 + KPI 기록

### 3-3. 독립 실행 가능 범위

```
기획 Workflow 독립 실행:
  /generate-design-v2 만으로 Stage 0~6 완료 가능
  → 코드 생성 없이 기획서 + Design DB 산출물 확보
  → 사람 개발자에게 기획서 전달 가능
  → Stage 7~8은 빌드가 필요하므로 코드 Workflow 없이는 실행 불가

기획 없이 코드만:
  기존 기획서(YAML)가 있으면 Code Phase 2부터 직접 진행 가능
  → /generate-code 로 코드 생성
```

---

## 4. 연결 구조

### 4-1. 전체 연결 다이어그램

```
┌──────────────────────────────────────────────────┐
│  AI_Workflow_기획 (Design Workflow)               │
│  독립 실행 가능: Stage 0~6                         │
│                                                   │
│  Stage 0 (설계 표준 + 디렉션 히스토리) ← 장르 최초 1회│
│      ↓                                            │
│  Stage 1 (DB 가공 + 설계 분석 + 디렉터 큐레이션)   │
│      ↓                                            │
│  Stage 2 (기획 생성: 컨셉→시스템→밸런스/콘텐츠→BM) │
│      ↓                                            │
│  Stage 3 (통합 검증)                               │
│      ↓                                            │
│  Stage 4 (디렉터 검수) ──피드백──→ Stage 5 (재생성) │
│      ↓ (승인)                         ↓ (완료)    │
│  Stage 6 (DB 축적)  ←─────────────────┘           │
│      ↓                                            │
│  출력: 3-Layer 기획서                              │
│    L1: game_design.yaml                           │
│    L2: system_spec.yaml + build_order.yaml        │
│    L3: nodes/*.yaml (AI_기획서)                    │
└────────────────────┬─────────────────────────────┘
                     │
              기획서 전달 (호출/참조)
                     │
┌────────────────────▼─────────────────────────────┐
│  AI_Workflow_개발 (Code Workflow)                  │
│                                                   │
│  Phase 1 (DB 구축) ← 별도: 소스코드 파싱           │
│      ↓                                            │
│  Phase 2 (기획서 변환) ← Stage 6 기획서 수신       │
│      ↓                                            │
│  Phase 3 (코드 생성) — Main + Sub×2 병렬           │
│      ↓                                            │
│  Phase 4 (검증 & 축적) — Validator 검증            │
│      ↓                                            │
│  출력: Unity C# / HTML5 Playable                  │
└────────────────────┬─────────────────────────────┘
                     │
                 빌드 완료
                     │
┌────────────────────▼─────────────────────────────┐
│  공유 단계 (양쪽 결과물 필요)                       │
│                                                   │
│  Stage 7 (플레이 검증)                             │
│    7-1 자사 가속 테스트                             │
│    7-2 장기 테스트                                  │
│    7-3 대규모 가상 유저 시뮬레이션                   │
│      ↓ 이슈 발견 시 → Design Stage 2로 역방향 피드백│
│                                                   │
│  Stage 8 (라이브 동기화)                            │
│    밸런스 패치 → Design DB 새 버전                  │
│    KPI 기록 → 다음 프로젝트 Stage 1 입력으로 순환   │
└──────────────────────────────────────────────────┘
```

### 4-2. 연결 포인트 상세

#### 기획 → 코드 연결 (정방향)
```
트리거: Design Stage 6 완료 (기획서 확정)
전달물: 3-Layer 기획서
  - L3 nodes/*.yaml → Code Phase 2가 수신
  - L2 build_order.yaml → Phase 순서 결정
  - L2 system_spec.yaml → 시스템 간 의존성 참조
수신측: Code Phase 2 (기획서 변환)
  - AI_기획서 YAML 파싱 → 메타데이터 추출
  - Base Code DB 검색 → 참조 코드 선정
  - 코드 생성 착수
```

#### 코드 → 기획 연결 (역방향)
```
트리거: Code Phase 4 완료 (빌드 생성)
전달물: 플레이 가능한 빌드 (APK 등)
수신측: Design Stage 7 (플레이 검증)
  - AI Tester가 빌드를 실행하여 실측 데이터 수집
  - 기획 예측값 vs 실측값 비교
  - 차이가 큰 부분 → Stage 2로 되돌아가 기획 수정
```

#### Stage 7 역방향 피드백 경로
```
밸런스 이슈 (수치만 문제):
  → 기획 Stage 2-3 (밸런스) 수정 → 코드 Calculator Role만 재생성
시스템 이슈 (설계 문제):
  → 기획 Stage 2-2 (시스템) 수정 → 코드 해당 Phase부터 재시작
양쪽 이슈 (기획+코드):
  → 기획 Stage 2 전체 수정 → 코드 전체 재생성
```

---

## 5. 진화 비교표

### 5-1. 원본 6단계 ↔ 현재 매핑

| 원본 6단계 | 현재 Code Phase | 현재 Design Stage | 변화 설명 |
|-----------|----------------|-------------------|-----------|
| (없음) | — | **Stage 0** (설계 표준 + 디렉션) | **완전 신규**. 장르별 파라미터 정의 + 디렉터 판단 패턴 축적 |
| 1단계: Base Code DB 가공 | **Phase 1** (DB 구축) | **Stage 1** (Design DB 가공) | 양쪽 각자 DB 구축. 기획은 설계 분석 + 디렉터 큐레이션 추가 |
| 2단계: 기획서 제작/가공 | **Phase 2** (변환만) | **Stage 2~6** (기획 전체) | **최대 변화**. 원본의 기획서 생성이 독립 Workflow(Stage 0~8)로 분리. Code Phase 2는 변환만 담당 |
| 3단계: 코드 생성 | **Phase 3** (코드 생성) | — | Code 전용. Agent Team 병렬화 추가 (Main + Sub×2) |
| 4단계: 피드백/재생성 | **Phase 4** (일부) | **Stage 4~5** | 양쪽 각자 피드백 루프. 기획은 디렉터 검수, 코드는 Validator 자동 검증 |
| 5단계: 재생성 평가 | **Phase 4** (일부) | **Stage 5** | Code에서는 Phase 4로 통합 |
| 6단계: DB 축적 | **Phase 4** (일부) | **Stage 6** | 양쪽 각자 Expert DB. 기획은 사후 라벨(시장 성과) 추가 |
| (없음) | — | **Stage 7** (플레이 검증) | **완전 신규**. AI Tester 기반 실증 검증 |
| (없음) | — | **Stage 8** (라이브 동기화) | **완전 신규**. 출시 후 버전 관리 + KPI 기록 |

### 5-2. 원본에 없었던 신규 항목 (19개)

| # | 항목 | 분류 | 신규 유형 |
|---|------|------|-----------|
| 1 | Agent Team (7명 구성 + 병렬 규칙) | Code | 완전 신규 |
| 2 | Game Layer 추가 (3종 Layer) | Code | 확장 |
| 3 | Puzzle/Casual 장르 추가 (9종) | 공통 | 확장 |
| 4 | UX Role 추가 (21종 Role) | Code | 확장 |
| 5 | Playable 광고 파이프라인 | Code | 완전 신규 |
| 6 | SDK 통합 가이드 (Firebase/AdMob/IAP) | Code | 완전 신규 |
| 7 | Android 빌드 설정 + 에러 패턴 5종 | Code | 완전 신규 |
| 8 | Scene 구성 규칙 (3씬 + Builder) | Code | 완전 신규 |
| 9 | Validator 5단계 검증 (Code) | Code | 상세화 |
| 10 | Design Workflow Stage 0~8 전체 | Design | 완전 신규 |
| 11 | Design DB (9 Domain × 9 Genre) | Design | 완전 신규 |
| 12 | Design 피드백 14종 카테고리 | Design | 완전 신규 |
| 13 | Design 신뢰도 점수 (Code와 분리) | Design | 완전 신규 |
| 14 | AI Tester (PRIMARY/SECONDARY) | Design | 완전 신규 |
| 15 | Quality Gates 6종 | Design | 완전 신규 |
| 16 | Stage 0: 장르별 설계 표준 (구성요소 맵 + 파라미터 + DB 스키마) | Design | 완전 신규 |
| 17 | Stage 0: 디렉션 히스토리 (디렉터 판단 패턴 자동 축적) | Design | 완전 신규 |
| 18 | 프로덕션 스크립트 15개 + 라이브러리 4개 | 공통 | 완전 신규 |
| 19 | KPI & 히스토리 관리 | 공통 | 완전 신규 |

### 5-3. 원본 구조가 보존된 항목

원본에서 정의한 핵심 설계 원칙은 그대로 유지:

| 원본 원칙 | 현재 상태 |
|----------|-----------|
| 3-AI 분리 (환각 방지) | 유지. Code 3분리 + Design 3분리 |
| Layer > Genre > 대기능 > 소기능 분류 | 유지. Layer/Genre 확장, 대기능→Tag(7종), 소기능→Tag(11종) |
| DB 검색 우선순위 (Expert→Base→생성) | 유지. Code/Design 양쪽 동일 구조 |
| 신뢰도 점수 체계 (0.4 시작, ≥0.6 승격) | 유지. Design용 점수 별도 추가 (자동 점수 3종 + 사후 라벨) |
| 기획서 구조 (기획서→명세서→AI_기획서) | 유지. 3-Layer 구조로 명칭 정리 (L1/L2/L3) |
| Rules 추출 (Generic/장르별) | 유지. Design은 도메인별 규칙 추가 |

---

## 6. 독립성과 호출 관계 정리

### 기획 Workflow 독립 실행
```
/generate-design-v2 [게임 컨셉]
  → Stage 0~6 완료
  → 산출물: 3-Layer 기획서 + Design DB 엔트리
  → 코드 생성 없이 기획서만 확보 가능
  → 사람 개발자에게 기획서를 전달하여 수동 개발 가능
```

### 코드 Workflow에서 기획 호출
```
게임을 만들어줘. Agent Team으로 진행.
  → 기획서가 없으면: 기획 Workflow(Stage 0~6)부터 실행
  → 기획서가 있으면: Code Phase 2~4 바로 진행
```

### 기획 없이 코드만
```
기존 기획서(YAML)가 있으면 Phase 2부터 직접 진행 가능
  → /generate-code [yaml 경로]
  → Phase 2(변환) → Phase 3(생성) → Phase 4(검증)
```

### 공유 단계 (Stage 7~8)
```
Stage 7 (플레이 검증): 기획 기획서 + 코드 빌드 양쪽 필요
  → 기획 예측값과 실측값 비교가 목적
  → 빌드 없이는 실행 불가

Stage 8 (라이브 동기화): 출시된 게임 필요
  → 라이브 패치 데이터를 Design DB에 버전 관리
  → 다음 프로젝트의 Stage 1 입력으로 순환
```

---

## 7. Proposal 문서 관계도

```
proposal/
├── workflow/                                    ← 현행 워크플로우 문서
│   ├── AI_workflow_개발.md                      ← 코드 Workflow 원본 (.txt→.md 변환)
│   │     정의: Base Code DB, 분류 체계, 기획서 구조, 코드 생성, 피드백, DB 축적
│   ├── AI_workflow_기획_v2.0.md                 ← 기획 Workflow 정본 v2.1 (Stage 0~8)
│   │     정의: 설계 표준, Design DB, 기획 생성, 검증, AI Tester, Quality Gates, 라이브 동기화
│   └── AI_workflow_통합_구조.md                 ← 이 문서
│         역할: 두 워크플로우의 구별, 연결, 진화를 정리
│
├── reviews/                                     ← 리뷰 및 히스토리
│   ├── AI_workflow_개발_원본.txt                ← 코드 Workflow 원본 텍스트 (보존)
│   ├── AI_workflow_기획_v1.0.md                 ← 기획 Workflow v1.0 (v2.0에 의해 대체)
│   ├── AI_workflow_기획_리뷰.md                 ← v1.0 리뷰
│   ├── AI_workflow_기획_1차리뷰.md              ← 1차 리뷰
│   └── AI_workflow_기획_2차리뷰.md              ← 2차 리뷰 → v2.0 반영됨

docs/
└── WORKFLOW.md                                  ← 시스템 문서 (v2.1 반영 완료)

CLAUDE.md                                        ← 마스터 컨텍스트 (v2.1 반영 완료)
```

### 문서 간 역할 분담

| 문서 | 역할 | 참조 시점 |
|------|------|-----------|
| `proposal/workflow/AI_workflow_개발.md` | 코드 Workflow 원본 설계 의도 확인 | 설계 근거 추적 시 |
| `proposal/workflow/AI_workflow_기획_v2.0.md` | 기획 Workflow 전체 사양서 (v2.1, Stage 0~8) | 기획 Workflow 실행 시 |
| `proposal/workflow/AI_workflow_통합_구조.md` | 두 Workflow의 관계와 진화 확인 | 전체 구조 파악 시 |
| `CLAUDE.md` | AI Agent 실행 시 마스터 컨텍스트 | 항상 |
| `docs/WORKFLOW.md` | Agent Team 구성과 파이프라인 상세 | 코드 생성 실행 시 |

---

## 8. 요약

1. **AI_Workflow_개발(원본)**은 6단계 코드 생성 파이프라인이었음
2. 원본의 2단계 "기획서 제작"이 **AI_Workflow_기획**이라는 독립 Stage 0~8 파이프라인으로 확장됨
3. **Stage 0(설계 표준 + 디렉션 히스토리)**이 인프라 단계로 추가 — 장르별 "무엇을 정의해야 하는지" 기준 정의
4. **Stage 1에 설계 의도 분석 + 디렉터 큐레이션** 추가 — 기계적 파싱이 아닌 AI 분석 + 디렉터 승인 후 DB 저장
5. 현재 Code Workflow는 4개 Phase로 재편, 원본 4·5·6단계가 Phase 4로 통합
6. **기획 Workflow는 독립 실행 가능** (Stage 0~6), 코드 Workflow 없이 기획서만 산출 가능
7. **코드 Workflow는 기획서가 필요** — 없으면 기획 Workflow 호출, 있으면 Phase 2부터 진행
8. **Stage 7~8은 공유 단계** — 기획 예측 + 코드 빌드 양쪽이 있어야 실행 가능
9. 원본 대비 **19개 신규 항목**이 추가됨 (Code 9개, Design 8개, 공통 2개)
