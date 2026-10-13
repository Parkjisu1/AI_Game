# AIMED — AI 기반 게임 개발 워크플로우 및 자체 도구 체계

> **분류**: 대외 공유용 · Confidential
> **작성**: AIMED
> **버전**: v1.0 (2026-05-26)
> **대상**: OpenAI 협업 논의 (비즈니스 요약 + 기술 심층)

---

## 목차

- [0. Executive Summary (요약)](#0-executive-summary-요약)
- [1. 서론](#1-서론)
- [2. 시스템 전체 조망](#2-시스템-전체-조망)
- [Part I. GameForge — AI 코드·기획 생성 파이프라인](#part-i-gameforge--ai-코드기획-생성-파이프라인)
- [Part II. Virtual Player — 자율 게임 플레이 AI 테스터](#part-ii-virtual-player--자율-게임-플레이-ai-테스터)
- [Part III. PixelForge — 레벨 자동 생성](#part-iii-pixelforge--레벨-자동-생성)
- [Part IV. YOLO 멀티장르 라벨러 + 비전 파이프라인](#part-iv-yolo-멀티장르-라벨러--비전-파이프라인)
- [Part V. ProjectHub — MCP 서버 + Unity 브리지](#part-v-projecthub--mcp-서버--unity-브리지)
- [Part VI. Hermes — 자율 태스크 라우팅 데몬](#part-vi-hermes--자율-태스크-라우팅-데몬)
- [Part VII. BalloonLoop — 통합 레퍼런스 프로젝트](#part-vii-balloonloop--통합-레퍼런스-프로젝트)
- [8. 정량 성과 종합](#8-정량-성과-종합)
- [9. 한계 및 향후 과제](#9-한계-및-향후-과제)
- [10. 결론](#10-결론)
- [부록](#부록)

---

## 0. Executive Summary (요약)

AIMED는 모바일 게임 개발의 **전 주기(기획 → 코드 → 콘텐츠 → 테스트 → 운영)** 를 AI로 자동화·증강하는 자체 시스템군을 구축·운영하고 있습니다. 단일 챗봇 수준의 활용이 아니라, **역할이 분리된 다중 AI 에이전트**가 표준화된 DB·계약·검증 체계 위에서 협업하는 **파이프라인형 AI 조직**을 운영 중입니다.

### 핵심 메시지 4가지

1. **"코드 조각"이 아닌 "작동하는 시스템"을 생성한다.**
   파일 간 연결을 명시적 계약(Integration Contract System)으로 추적·검증하여, 대규모 자동 생성 코드의 통합 실패를 구조적으로 방지합니다.

2. **환각(hallucination)을 프로세스로 통제한다.**
   정규화된 분류 체계 + 검증 DB 참조 의무화 + 6대 환각 방지 규칙 + 자동 검증 훅으로, 생성 AI의 신뢰성 문제를 엔지니어링 규율로 전환했습니다.

3. **AI가 게임을 직접 플레이해서 검증한다.**
   화면만 보고(비전) 게임을 사람처럼 자율 플레이하는 AI 테스터를 운영하며, 자사 빌드의 밸런스·진행·클리어 가능성을 실측 검증합니다.

4. **실제로 게임을 출시 수준까지 만들었다.**
   본 체계로 자사 퍼즐 게임 **BalloonLoop**의 기획서·시스템 명세·300개 레벨·Unity 코드·APK/AAB 빌드까지 생산했습니다. 단순 PoC가 아니라 **출하 가능 산출물**을 확보했습니다.

### 운영 규모 (2026-05-26 실측, MongoDB)

| 지표 | 값 | 의미 |
|------|----|----|
| AI 에이전트 정의 | 11종 | PM/기획/코딩/검증/리뷰 역할 분리 |
| 에이전트 실행 트레이스 누적 | **2,465건** | 실가동 증거 |
| 에이전트 세션 누적 | **1,319건** | 누적 세션 |
| 토큰 사용 기록 | **912건** | 비용 추적 |
| 자동 생성 레벨(그리드) | **5,093건** | 레벨 후보 자동 생성 |
| 출하 레벨 세트 | **300개** | BalloonLoop 출하 레벨 |
| 도메인 설계 원칙 누적 | **241건** | 축적된 설계 원칙 |
| 팀 품질 점수 기록 | 209 + 799건 | 코드/기획 팀 신뢰도 추적 |

> 본 백서는 이 체계를 구성하는 **7개 축**(GameForge, Virtual Player, PixelForge 레벨 생성, YOLO 라벨러, ProjectHub, Hermes, BalloonLoop)을 논문 구조(배경 → 방법 → 결과)로 기술합니다.

---

## 1. 서론

### 1.1 배경 — 생성 AI를 "게임 스튜디오"로 운영하기

생성 AI를 코드/문서 생성에 쓰는 것은 흔합니다. 그러나 게임 개발은 (a) 다수 파일이 런타임에 서로 호출·구독하는 **고결합 시스템**이고, (b) 기획 의도가 코드·콘텐츠·밸런스에 일관되게 관철되어야 하며, (c) "컴파일 통과"가 곧 "플레이 가능"을 의미하지 않는 **검증 비용이 큰 도메인**입니다.

AIMED는 이 세 가지 난제를 정면으로 다루기 위해, 단일 모델 호출이 아니라 **역할 분리 + 계약 + 검증 + 실플레이 테스트**를 결합한 다층 시스템을 설계했습니다.

### 1.2 설계 3대 원칙

| 원칙 | 정의 | 구현 |
|------|------|------|
| **3-AI 분리** | DB 가공 AI / 기획 AI / 코드 생성 AI 를 분리 | 11종 에이전트, 모델 차등 배정 (Opus=전략·아키텍처, Sonnet=도메인 실행) |
| **환각 방지** | 정규화 분류 체계 + DB 참조 의무화 | 4단 분류(Layer/Genre/Role/Tag), 5-Tier 검색 우선순위, 6대 환각 방지 규칙 |
| **병렬 작업** | Phase 내 노드를 다중 에이전트로 동시 생성 | Agent Teams, Integration Contract System으로 병렬 생성물 통합 보증 |

### 1.3 문서 범위

본 백서가 다루는 시스템:

| Part | 시스템 | 한 줄 정의 |
|------|--------|-----------|
| I | GameForge 파이프라인 | AI 기획서 → 코드 자동 생성 + 검증 |
| II | Virtual Player / AI Tester | 비전 기반 자율 게임 플레이 테스터 |
| III | PixelForge | 이미지 → 플레이 가능 레벨 자동 생성 |
| IV | YOLO 라벨러 | 멀티장르 비전 학습 데이터 도구 |
| V | ProjectHub | MCP 기반 Unity 제어 + 태스크 보드 |
| VI | Hermes | 자율 태스크 라우팅 데몬(원격 서버) |
| VII | BalloonLoop | 본 체계로 제작한 자사 퍼즐 게임 |
| I.9 | AI_WORK_FLOW_TEST | 파이프라인이 생성한 게임 프로젝트군 |

---

## 2. 시스템 전체 조망

### 2.1 7개 축의 관계도

```
                         ┌──────────────────────────────────────────────┐
                         │   사람 (디렉터 / 기획자 / 개발자 / PM)         │
                         └───────────────┬──────────────────────────────┘
                                         │ 태스크 생성 / 검수 / 의사결정
                                         ▼
   ┌───────────────────────────  ProjectHub (Part V)  ───────────────────────────┐
   │  웹 태스크 보드 + MCP 서버 + Unity 브리지   (원격 운영 서버 + 빌드 머신)        │
   └───────────────┬───────────────────────────────────────────┬─────────────────┘
                   │ 태스크 이벤트(MongoDB Change Stream)         │ Unity 에디터 제어(HTTP)
                   ▼                                              ▼
   ┌──────────  Hermes (Part VI)  ──────────┐         ┌─── Unity Editor (BalloonLoop) ───┐
   │  자율 태스크 라우팅 데몬                │         │  씬/프리팹/SerializeField 조회·수정 │
   │  watcher → context → router → executor  │         └──────────────────────────────────┘
   └───────────────┬─────────────────────────┘
                   │ 액션 분기
        ┌──────────┼───────────────────────────────┬───────────────────────┐
        ▼          ▼                                ▼                       ▼
 ┌─────────────┐  ┌──────────────────────┐  ┌────────────────────┐  ┌──────────────────┐
 │ GameForge   │  │ Virtual Player        │  │ PixelForge 레벨생성 │  │ YOLO 라벨러/비전  │
 │ (Part I)    │  │ (Part II)             │  │ (Part III)          │  │ (Part IV)         │
 │ 기획→코드   │  │ 자율 플레이 테스트    │  │ 레벨 자동 생성      │  │ 비전 학습 데이터  │
 │ 생성·검증   │  │ (BlueStacks+ADB)      │  │ (이미지→레벨)       │  │                  │
 └──────┬──────┘  └──────────┬────────────┘  └─────────┬──────────┘  └────────┬─────────┘
        │                    │ 밸런스 실측             │ 레벨 데이터          │ 인식 모델
        └────────────────────┴─────────────────────────┴──────────────────────┘
                                         │
                                         ▼
                         ┌──────────────────────────────────────┐
                         │  MongoDB Atlas (30+ 컬렉션)            │
                         │  지식 DB(코드/기획) + 운영 텔레메트리   │
                         └──────────────────────┬───────────────┘
                                                ▼
                         ┌──────────────────────────────────────┐
                         │  BalloonLoop (Part VII) — 통합 산출물  │
                         │  기획 → 레벨 → 코드 → APK/AAB          │
                         └──────────────────────────────────────┘
```

### 2.2 데이터 중추: MongoDB

모든 축이 단일 MongoDB Atlas 데이터베이스를 공유합니다. 2026-05-26 실측 기준 **30개 컬렉션**이 가동 중이며, 크게 세 부류로 나뉩니다.

**(A) 지식 DB — 재사용 가능한 검증 자산**

| 항목 | 건수 | 내용 |
|------|------|------|
| 코드 베이스 | 141 | 파싱된 C# 소스 (Layer/Genre/Role/Tag 분류) |
| 검증 코드(Expert) | 0 | 검증 통과(score≥0.6) 코드 — 현재 승격 대기 |
| 기획 베이스 | 40 | 기획 데이터 (Domain/Genre 분류) |
| 검증 기획(Expert) | 20 | 검증 통과 기획 (Puzzle 정규화 완료) |
| Unity 설정 | 19 | 씬/프리팹 설정(RectTransform/Canvas) 파싱 |
| 규칙 | 7 | 피드백에서 추출된 규칙 |
| 검토 대기 | 3 | 검토 대기 큐 |

**(B) PixelForge 운영 — 레벨/콘텐츠 생산 라인**

| 항목 | 건수 | 내용 |
|------|------|------|
| 자동 생성 레벨 | **5,093** | 자동 생성 그리드 레벨 후보 |
| 출하 레벨 세트 | 300 | BalloonLoop 출하 레벨 |
| 레벨 생성 잡 | 403 | 생성 작업 큐 |
| 생성 감사 로그 | 677 | 감사 이력 |
| 태스크 | 267 | 운영 태스크 |
| 배치 요청 | 40 | 배치 생성 요청 |
| 아트 에셋 | 379 | 아트 자산 |
| 레벨 백업 | 52 | 버전 백업 |

**(C) Hermes 텔레메트리 — 실가동 증거**

| 항목 | 건수 | 내용 |
|------|------|------|
| 에이전트 실행 트레이스 | **2,465** | 실행 기록 |
| 에이전트 세션 | **1,319** | 세션 기록 |
| 토큰 사용/비용 | 912 | 비용 추적 |
| 기획 팀 품질 점수 | 799 | 품질 평가 이력 |
| 도메인 설계 원칙 | 241 | 축적된 원칙 |
| 코드 팀 품질 점수 | 209 | 품질 평가 이력 |
| 에이전트 역할 정의 | 44 | 역할 정의 |
| 프롬프트 개선 패치 | 14 | 자가 개선 이력 |
| 활동 로그 | 469 | 운영 로그 |

> **주석(투명성)**: 사내 기록에는 과거 대규모 재임베딩 시점(2026-03)에 코드 베이스 6,060건/Unity 설정 21K건 규모가 있었으나, 이후 구 프로젝트 아카이빙 및 컬렉션 재편으로 현재 상주 건수는 위 실측값입니다. 본 백서는 **2026-05-26 실측값**을 정본으로 사용합니다.

---

# Part I. GameForge — AI 코드·기획 생성 파이프라인

> 핵심: 기획서를 입력하면 검증된 Unity C# 코드(또는 HTML5 플레이어블 광고)를 자동 생성

### I.1 3-AI 분리 철학

생성 AI를 "만능 1인"으로 쓰면 (a) 컨텍스트가 비대해지고 (b) 역할 충돌로 품질이 저하됩니다. GameForge는 인간 게임 스튜디오의 직무 분화를 그대로 모사합니다.

```
DB 가공 AI  ─┐
             ├─→  서로 다른 책임·모델·제약을 가진 11종 에이전트
기획 AI     ─┤      (각 에이전트는 고유 페르소나·금지규칙으로 정의됨)
             │
코드 생성 AI ─┘
```

### I.2 Agent Team "AI-Game-Creator" (11종)

에이전트 명세는 다음과 같습니다. 모델 배정은 **전략·아키텍처 = Opus**, **도메인 실행·검증 = Sonnet** 원칙을 따릅니다.

| 에이전트 | 모델 | 역할 | 핵심 제약 |
|----------|------|------|-----------|
| **Lead** | Opus | PM — 태스크 분배·조율·평가, Phase Gate, 계약 검증 | 코드를 직접 작성하지 않음 |
| **Designer** | Sonnet | 3-Layer 기획서 생성(YAML+Docx 듀얼 출력) | Quality Gate 소유 안 함(자가 점검만) |
| **Main Coder** | Opus | Phase 0 Core 아키텍처 + 복잡 시스템 + `_ARCHITECTURE.md`/`_CONTRACTS.yaml`/`_ASSET_MANIFEST.yaml` | 계약의 단독 작성자 |
| **Sub Coder ×2** | Sonnet | Phase 1+ 일반 노드 병렬 구현 | `_CONTRACTS.yaml` 선행 독해 의무 |
| **Playable Coder** | Sonnet | HTML5 단일 파일 플레이어블 광고 | 외부 요청 금지, CTA 필수 |
| **Validator** | Sonnet | 코드 5+1.5단계 검증 (Stage 5.5 통합 검증 포함) | 계약↔코드 교차 검증 |
| **Design Validator** | Sonnet | 기획 6단계 검증, 점수 산출, Expert 승격 | Quality Gate 단독 소유 |
| **DB Builder** | Sonnet | C# → Code DB (호출 시) | Write 권한 제한 |
| **Design DB Builder** | Sonnet | 기획 문서 → Design DB (호출 시) | 정규화 책임 |
| **Reviewer (Product)** | Sonnet | 기획 품질 QA (10개 기준 / Result·Trust·Operation 축) | — |
| **Reviewer (Business)** | Sonnet | 사업성 QA (9개 기준 + Reality Gate) | FAIL 시 BLOCK |

**병렬 실행 규칙**: Phase 0(Main Coder 단독, Core 전담) → Phase 1+(Main + Sub ×2 병렬) → Phase 간 의존성은 이전 Phase 검증 통과 후 진행.

### I.3 정규화 분류 체계 (환각 방지의 1차 방어선)

모든 코드 자산은 4차원으로 분류되어 DB에 저장·검색됩니다.

```
Layer (3)        Genre (9)                Role (21)              Tag (대 7 / 소 11)
─────────        ─────────                ─────────              ──────────────────
Core             Generic, RPG, Idle,      Manager, Controller,   대: StateControl,
Domain           Merge, SLG, Tycoon,      Calculator, Processor, ValueModification,
Game             Simulation, Puzzle,      Handler, Provider,     ConditionCheck …
                 Casual                   Factory, Pool, State…  소: Compare, Spawn,
                                          (클래스명 패턴 매칭)    Despawn, Aggregate…
```

이 분류는 **검색 키**이자 **환각 탐지 기준**입니다. 예) "BattleManager를 Core로 분류"하면 규칙 위반(→ Domain이 정답)으로 잡힙니다.

### I.4 5-Tier DB 검색 우선순위 (생성 전 의무)

모든 생성 작업은 **DB 검색을 선행**해야 하며, DB 미검색 직접 생성은 "환각 위험"으로 간주되어 Validator가 거부할 수 있습니다.

| 순위 | 검색 대상 | 조건 |
|------|-----------|------|
| 1 | Expert DB (해당 장르) | genre 일치 AND score≥0.6 |
| 2 | Expert DB (Generic) | generic AND score≥0.6 |
| 3 | Genre Base DB | genre 일치 |
| 4 | Generic Base DB | generic |
| 5 | AI 신규 생성 | 위 4개 결과 없음 (Validator 엄격 검증) |

### I.5 Integration Contract System (ICS) — 본 파이프라인의 핵심 차별점

> **문제**: 40개 파일을 다중 에이전트가 동시 생성하면, 이벤트 발행/구독 불일치, ObjectPool 키-프리팹 누락, SerializeField 와이어링 누락, 메서드 시그니처 불일치로 "컴파일은 되지만 작동 안 하는" 코드가 양산됩니다.
>
> **해법**: 파일 간 연결을 **명시적 계약 문서**로 추적하고 자동 검증합니다.

**3대 산출물** (Main Coder가 Phase 0에 생성, Phase마다 갱신):

| 산출물 | 추적 대상 |
|--------|-----------|
| `_ARCHITECTURE.md` | 전체 구조 설명 |
| `_CONTRACTS.yaml` | **events**(발행자/구독자), **pool_keys**(키↔프리팹↔소비자), **serialized_fields**(필드↔씬오브젝트), **method_calls**(호출자↔대상), **asset_requirements** |
| `_ASSET_MANIFEST.yaml` | prefabs, scenes, editor_scripts, resources |

**Validator Stage 5.5 — 통합 검증**: 기존 5단계 검증 후, 계약의 각 항목이 실제 코드에 존재하는지 교차 검증합니다.

| 체크 | 검증 방법 | 실패 |
|------|-----------|------|
| 이벤트 계약 | publisher/subscriber 파일에 실제 Publish/Subscribe 코드 존재 | error |
| Pool 키 계약 | prefab 파일 + consumer의 Get/Return 코드 존재 | error |
| SerializeField 계약 | `[SerializeField]` 존재 + SceneBuilder의 WireField 호출 존재 | error |
| 메서드 호출 계약 | caller에 호출 코드 + target에 메서드 존재 | error |
| 양방향 일관성 | 코드의 Publish/Subscribe가 계약에 역등록되어 있는지 | warning |

**Error Fix Protocol** (에러 수정 시 기획 이탈 방지 3단계): ① 컨텍스트 로드(깨진 파일 + L3 YAML + 계약 + 호출자/의존성 전부 실독) → ② 수정 제약(Public API 삭제 금지, SerializeField 제거 금지, 로직 우회형 null 체크 금지) → ③ 수정 후 계약·기획·자가 검증 재실행.

### I.6 Design Workflow (Stage 0~8)

기획을 8단계로 프로그램화한 워크플로우. **YAML(AI용) + Docx(사람용) 듀얼 출력**이 표준입니다.

```
Stage 0  설계 표준      장르 최초 1회 — 구성요소 맵 + 파라미터(상세도 기준) + 데이터 스키마
Stage 1  DB 가공        기획 문서 / AI Tester 관찰 → Design DB
Stage 2  기획 생성      컨셉(Core Fun) → 도메인별 생성 → BM
Stage 3  통합 검증      교차 일관성 + 유저 여정 시뮬 + 누락 검출
Stage 4  디렉터 검수    사람 검수 (피드백 없으면 Stage 6으로)
Stage 5  재생성 평가    피드백 반영 확인 + 히스토리 분석
Stage 6  DB 축적        score 산출 → Expert DB 승격(≥0.6) → Rules 추출
   ↓ Code Workflow 실행 ↓
Stage 7  플레이 검증    AI Tester (가속/장기/대규모 시뮬)
Stage 8  라이브 동기화  밸런스 패치 → 버전 → KPI
```

### I.7 신뢰도 점수 + Expert 승격 (자가 학습 루프)

생성물은 재사용 성패에 따라 점수가 변동되고, 임계값(0.6) 이상이면 **Expert DB로 승격**되어 차기 생성의 1순위 참조 자산이 됩니다.

| 이벤트 | 코드 점수 |
|--------|-----------|
| 초기 저장 | 0.4 |
| 피드백 반영 | +0.2 |
| 재사용 성공(1회) | +0.1 |
| 재사용 실패(1회) | −0.15 |
| 타 장르 재사용 성공 | +0.1 (Generic 승격 검토) |
| **Expert 승격 임계값** | **≥0.6** |

구현: 점수 관리 공유 라이브러리 (점수 이벤트 상수, 신뢰도 이력 갱신, 임계값 자동 승격).

### I.8 자동화 인프라 — 훅 / 규칙 / 스크립트 / 웹

**자동 훅 5종**: 커밋·저장 시 자동 실행.

| 훅 | 트리거 | 역할 |
|----|--------|------|
| pre-commit-validate | 커밋 전 | 하드코딩·TODO 포맷·JSON 유효성·Unity 금지 패턴 검사 (ERROR 시 커밋 차단) |
| post-commit-audit | 커밋 후 | 감사 로그 기록 |
| asset-validate | 에셋 저장 시 | 네이밍/경로/크기/ICS 크로스체크 (ERROR 시 저장 차단) |
| gap-detect | Phase 완료 후 | 누락 문서/계약 감지 |
| context-preserve | 컨텍스트 압축 시 | 상태 스냅샷 저장 |

**경로별 코딩 규칙 6종**: glob 패턴 매칭으로 해당 경로 파일 편집 시 자동 로드 — 런타임(new GameObject 금지, ObjectPool 필수), 에디터(InitializeOnLoad+delayCall, EditorPrefs 1회 가드), SDK(조건부 컴파일 필수), 데이터(ScriptableObject), 디자인 워크플로우(YAML 포맷), 플레이어블(단일 파일·CTA).

**스크립트 레이어** (35+종): 공유 라이브러리 위에 구축.
- 공유 라이브러리: MongoDB API + Expert 승격, 통합 YAML 파서, 점수 생명주기 관리, 도메인 정규화, 원자적 쓰기(병렬 에이전트 동시성).
- DB: 소스 파싱 / 검색 / 배치 적재
- 기획: 기획 파싱 / 코드 변환 / 버전 관리
- 검증: 플레이 검증 / 가상 플레이어 브리지 / 밸런스 시뮬
- 문서/리포트: KPI 생성 / 품질 리포트 / 토큰 추적

**웹 인터페이스 2종**:
- 사내 AI 챗/조회 UI (Gradio): 대시보드/Design/Review/Log 페이지, MongoDB 직결.
- 사내 운영 대시보드 (Node.js + EJS): 컬렉션 병렬 집계, 세션 인증, 에셋 업로드.

**명령어 20종** (슬래시 커맨드): `/parse-source`, `/generate-code`, `/validate-code`, `/parse-design`, `/generate-design-v2`, `/validate-design`, `/sync-live`, `/code-review`, `/balance-check`, `/scope-check`, `/sprint-plan`, `/retrospective`, `/estimate`, `/gate-check`, `/map-systems`, `/release-checklist`, `/team-code`, `/team-design`, `/team-polish`, `/evaluate-workflow`.

### I.9 산출 증거 — AI_WORK_FLOW_TEST (파이프라인 생성 프로젝트군)

GameForge 파이프라인은 "한 게임"이 아니라 **다수의 Unity 게임 프로젝트**를 실제로 생성해 왔습니다. 텍스트 기획서로부터 런타임 코드·에디터 스크립트·데이터 에셋·씬 구성까지 AI가 만들어 내며, 사람은 아트·최종 검수에 집중합니다.

| 프로젝트 | 성격 |
|----------|------|
| CarMatching | 차량 매칭 퍼즐 — Unity 프로젝트 일체 생성 |
| DropCat | 캐주얼 드롭 퍼즐 |
| MagicSort | 정렬 퍼즐 |
| ShiftTap | 타이밍 탭 캐주얼 |
| VeilBreaker | 퍼즐/액션 |
| Puzzle / Playable | 퍼즐 빌드 + HTML5 플레이어블 광고군 |

→ 즉, GameForge는 단발성 산출이 아니라 **반복적으로 게임 프로젝트를 찍어내는 생산 라인**으로 가동되었음을 보여주는 증거입니다.

---

# Part II. Virtual Player — 자율 게임 플레이 AI 테스터

> 규모: 약 296개 Python 파일 | 핵심: 화면만 보고 게임을 사람처럼 자율 플레이

### II.1 목적 — 블랙박스 게임 분석

설치된 게임을 화면 기반으로 자율 플레이하는 이중 역할 분석기입니다.

| 역할 | 내용 | 워크플로우 연계 |
|------|------|----------------|
| **PRIMARY: 자사 빌드 자동 검증** | 페르소나별 자율 플레이 → 승률·진행 속도·클리어 가능성·과금 트리거 실측 → 기획 피드백 | Stage 7 |
| **SECONDARY: 플레이 데이터 수집** | 화면 관찰로 난이도 곡선·진행 지표 추정 → Design DB(source: observed) | Stage 1 입력 |

### II.2 5계층 파이프라인

```
[화면 캡처]
   │
   ▼
Layer 1  지각(Perception)      스크린샷 → 구조화 BoardState JSON
   │     · 1차: YOLO 분류(~5ms) + OpenCV 공간분석(~50ms)
   │     · 폴백: Claude Vision (2~8s, 로컬 실패 시에만)   (지각 모듈 7종)
   ▼
Layer 2  기억(Memory)          고정 크기 작업기억 (홀더 슬롯, 실패 탭 이력, 연속 실패 카운터)
   │
   ▼
Layer 3  결정(Decision)        규칙 기반 우선순위 트리 P0~P5 (런타임 RL/LLM 미사용 → 재현성·안전)
   │     · P0: 긴급(홀더 풀 → Undo)  · P1~P5: 1~2수 룩어헤드 가중 휴리스틱
   │                                                       (3-Tier 비전 두뇌)
   ▼
Layer 4  실행(Execution)       ADB tap/back/relaunch
   │
   ▼
Layer 5  검증(Verification)    전/후 스크린샷 비교 → match/moved/no_change/screen_changed
```

### II.3 핵심 기법

- **3-Tier 비전 폴백** (비용 최소화): L0 지각 해시(pHash) 반사 캐시(~50ms) → L1 SSIM 템플릿 매칭 + 전술 규칙 → L2 로컬 탐색 존(8 영역) → L3 Claude Vision(최후, 정답 보정용). 반복 화면 캐시 적중으로 API 호출을 최소화.
- **페르소나**: casual / hardcore / whale / newbie / returning 5종, 반응속도·정확도·전략·인내·위험감수·탐색률·과금임계 등 파라미터화.
- **행동 트리(BT)**: 커리큘럼 학습(YAML 정의), 무인 부트스트랩 탐색 모드.
- **적응 학습**: 실패 좌표 무효화, 스턱(루프) 탐지, 요소 좌표 캐시, GOAP 상태전이 학습.
- **장르 옵저버**: Puzzle/Idle/Merge/RPG/SLG 장르별 파라미터 추출기(장르당 ~30~50 파라미터).

### II.4 기술 스택 / 패키징

- **언어/런타임**: Python 3.13, YAML 설정/커리큘럼
- **라이브러리**: ultralytics(YOLO), opencv-python, Pillow, torch, anthropic SDK(폴백), OCR(선택)
- **인프라**: ADB(BlueStacks), SQLite3(세션/패턴 저장)
- **배포 산출물**(PyInstaller → exe): 테스터 본체, 레벨 디자인 GUI(diffusers 내장), 레벨 스타일 에디터 등 데스크톱 실행파일군

> **정량 주석**: 인식 정확도 목표는 80%+이며, 일부 코드 규모/적중률 수치는 내부 설계 문서 기반 추정으로, 본 백서에서는 검증된 항목 위주로 기재했습니다.

---

# Part III. PixelForge — 레벨 자동 생성

> 핵심: 이미지 한 장에서 1:1 구조가 보증된 플레이 가능한 레벨을 자동 생성하는 **자체 개발 에이전트**

### III.1 목적 — 수작업 레벨 설계의 대체

레벨 1개를 사람이 손으로 그리는 대신, **이미지 → 구조 분석 → 플레이 가능한 레벨**을 자체 개발 에이전트가 자동 생성합니다. 난이도 곡선·색상 팔레트·기믹 배치를 코드가 보장하여 대량 콘텐츠를 빠르고 일관되게 생산합니다.

### III.2 레벨 생성 에이전트 — 2종 분류 후 진행

레벨의 시각 소스를 먼저 **2종으로 분류**하고, 유형에 맞는 생성 백엔드로 라우팅합니다. **분류·라우팅·후처리·검증 로직(에이전트 알고리즘)은 AIMED가 자체 개발**했으며, 이미지 생성 자체는 외부 생성 모델을 **도구로 활용**합니다.

| 입력 유형 | 생성 백엔드(활용) | 적합 사례 |
|-----------|------------------|-----------|
| **[픽셀아트]** | **PixelLab** (AI 픽셀아트 생성) | 사물·캐릭터·아이콘형 도안 |
| **[추상 / 패턴]** | **Claude** (패턴·도형 레이아웃 생성) | 기하·대칭·동심·나선 등 추상 구성 |

> 정리: **에이전트 알고리즘은 자체 제작**(분류기 + 변환 파이프라인 + 품질 게이트 + 자동 보정 봇), **생성 모델(PixelLab·Claude)은 백엔드로 활용**. 두 경로 모두 동일한 필드→큐 변환·검증 단계를 거쳐 규격이 통일됩니다.

### III.3 2단계 변환 파이프라인

| 단계 | 입력 | 출력 |
|------|------|------|
| **Stage 1 필드 생성** | 생성된 이미지(픽셀아트 / 추상패턴) | 색상·기믹이 매핑된 보드(필드 분석 잠금) |
| **Stage 2 큐 생성** | 필드 분석(불변) | 매거진 분포 + 큐 기믹 배치 → 레벨 |

**1:1 구조 보증**: 다트 수 = 풍선 수 + 기믹 수명 합 (5배수 정렬, 자동 검산). 필드가 확정되면 큐 생성은 필드를 수정하지 않고 분배만 수행하여 구조적 정합성을 보장합니다.

### III.4 배치 품질 알고리즘 (cowork 패턴)

레벨 배경의 공백 배치가 시각 품질을 좌우합니다. 이를 알고리즘으로 통제합니다.

- 구성 배치 **cowork 패턴 13종** + 공백 탐지로 시각 품질 관리
- 클러스터 페널티 강화 + 하드 리밋으로 산만한 배치 차단
- 단일 클러스터 비율 **53% → 69%**(+16pp), 최악 클러스터 **71% 감소**, 손실 0

### III.5 규모 및 검증

- 누적 **5,093개** 레벨 후보 자동 생성 → **300개** 출하 세트로 큐레이션
- **Field Completer 에이전트**가 미완성 draft를 자동 완성 (실측 품질 평균 0.978 / PASS 임계 0.85)
- **자동 보정 봇**이 생성 결과의 색상·구조 오류를 교정
- **Hard/Soft Rule 엔진**이 클리어 가능성(이론적 클리어 순서 존재)과 난이도 곡선을 검증
- 생성된 레벨은 **Virtual Player(Part II)** 가 자율 플레이로 재검증 — 생성과 검증이 폐루프를 이룸

### III.6 기술 스택

- **생성 백엔드(활용)**: PixelLab(픽셀아트), Claude(추상/패턴)
- **에이전트·파이프라인(자체 개발)**: Python(NumPy) 기반 분류·변환·cowork 배치·품질 게이트·자동 보정
- 큐 생성기 규칙(매거진 분포, 연결 다트 박스 의존성, Hidden anti-clustering, Pipe 색 다양성 등) 10개 Soft Rule + Hard Rule 군으로 정의 → 출하 타이틀 BalloonLoop 레벨 명세(v3.15)에 반영

---

# Part IV. YOLO 멀티장르 라벨러 + 비전 파이프라인

> 핵심: AI Tester 비전 모델 강화를 위한 멀티장르 학습 데이터 도구(데스크톱 라벨러)

### IV.1 라벨링 도구

PySide6 기반 데스크톱 GUI. 장르 선택(puzzle/slg/idle/custom) 후 클래스 로드, 4개 모드(Select/Draw/Reclassify/Erase) + 50단계 Undo + 런타임 클래스 추가. 출력은 **Pascal VOC XML → YOLO 정규화 txt** 변환 지원. 약 1,500줄 단일 GUI, PyInstaller 패키징.

### IV.2 클래스 분류 체계 / 학습 데이터

| 장르 | 클래스 수 | 예시 |
|------|-----------|------|
| puzzle | 12 | block_purple/yellow…, gimmick |
| **slg** | **180** | btn_*, hud_*, building_*(22), hero_*(13), marker_*(13), combat_*(9) |
| idle | 53 | prod_unit, upgrade_btn, manager_card, prestige_btn |

학습 데이터셋(puzzle 특화): dataset(89), cell_only(157), gimmick(62), holder(34), auto(33). 모델 변형: cell_only v1~v3, gimmick_detector v1/v3, holder_detector v3, pixelflow v1~v3, board_detector. 베이스 yolov8s(640px, 50~300 epochs).

### IV.3 성능 / 보조 위상 전환

배치 평가(204 레벨): 기믹 검출 Precision 0.623 / Recall 0.884 / **F1 0.731**, 타입 분류 정확도 **0.995**(공간 매칭 후 타입은 거의 정확), 셀 카운트 MAE 130.05. 초기 Jaccard ~0.474 한계 → **순수 YOLO만으로는 게임 상태 이해 불충분** 판단.

→ **하이브리드 인식으로 전환**: YOLO 보드 ROI + FFT 그리드 검출 + 픽셀 색상 분류 + YOLO 기믹 후처리. 결과적으로 YOLO는 **기믹·타입 분류 보조**로 유지하고, 그리드 구조·셀 정체성은 기하+픽셀 분석에 의존. YOLO는 테스트 자동화의 보조 인식기로 역할이 재정의됨.

---

# Part V. ProjectHub — MCP 서버 + Unity 브리지

> 핵심: AI 에이전트가 Unity 에디터를 **프로그래밍적으로 제어**하고, 사람은 웹 태스크 보드로 협업

### V.1 목적 / 이중 역할

원격 운영 서버에서 systemd 서비스로 가동. (1) **태스크 추적**: Next.js 웹 대시보드(137+ 태스크, 첨부/협업 메타데이터), (2) **에셋 오케스트레이션**: MCP(Model Context Protocol) 서버가 Claude에게 Unity 씬/프리팹/SerializeField/ScriptableObject 조회·수정 API를 노출.

### V.2 MCP 서버 아키텍처 (2-tier HTTP 포워딩, 무외부의존)

```
Claude ──HTTP:7900──▶  MCP 서버 (Node.js, node:http만 사용)
                              │ HTTP
                              ▼
                       Unity 브리지 :7901 (C# HttpListener)
                              │
                              ▼
                       Unity Editor API
```

**현재 가동(Tier 1 thin slice, 조회 3종)**: `inspect.scene.list`, `inspect.console.read_errors`(에러 링버퍼 500), `inspect.compilation.status` + `ping`/`health`. **계획(Phase 2, 15종)**: scene/asset/prefab/serializedfield read, prefab/gameobject/serializedfield/scriptableobject **modify**, compile/references/contracts **validate**, undo/list **tx**.

인증: Bearer 토큰, 30초 타임아웃(AbortController), 에러 코드 체계(`mcp.timeout`, `unity.*`, `ics.*`).

### V.3 Unity 브리지

워커 스레드 HttpListener + 메인 스레드 마샬링(`EditorApplication.update` + `ConcurrentQueue<Action>`). `[InitializeOnLoad]` 정적 생성자로 리스너 시작, `AssemblyReloadEvents.beforeAssemblyReload`로 도메인 리로드 전 안전 종료(EADDRINUSE 방지). Unity `JsonUtility`의 dict/array 미지원으로 수동 StringBuilder JSON 인코딩.

**계획된 ICS Write-Through Saga**: Modify 도구 실행 시 `_CONTRACTS.yaml`/`_ASSET_MANIFEST.yaml` 자동 갱신, 실패 시 auto-undo → 코드/씬과 YAML 메타데이터 무드리프트 보증.

### V.4 핵심 알고리즘 (실측 지표)

**(A) 레벨 배치 공백 탐지 (cowork 패턴 최적화)**: 17개 패턴 중 시각적으로 불량한 "scatter 공백"을 유발하는 4종 제외 → 13패턴. 클러스터 페널티 강화, 클러스터 하드 리밋 도입, 단일 클러스터 타이브레이커 추가.

| 지표 | 적용 전(17p) | 적용 후(13p) |
|------|-------------|-------------|
| 단일 클러스터 비율 | 53% | **69%** (+16pp) |
| 최악 클러스터 수 | 21(chevron) | 6(wave) (**−71%**) |
| REJECTED(>8) | 0 | 0 (무손실) |

**(B) Tasks API 슬림화**: 목록 응답에서 이미지/첨부 제외 + has_image 플래그 + 코멘트 최근 5개만 + 상세는 별도 엔드포인트 lazy fetch + 인덱스 3종.

| 지표 | 전 | 후 |
|------|----|----|
| `/api/tasks` JSON 크기 | 6,624KB | **185KB (−97.2%)** |
| 첫 로드 체감 | ~50s | ~1s (**50×**) |

### V.5 인프라 / 기술 스택

- **운영 서버**(Linux): systemd 서비스, Next.js / React / TypeScript / Tailwind, next-auth, MongoDB 드라이버
- **빌드 머신**(Windows): MCP 서버(Node, 작업 스케줄러로 상주), 배포/정리 스크립트
- MCP/브리지 모두 **외부 의존성 0** (Node 표준 http, C# 표준 라이브러리만)

---

# Part VI. Hermes — 자율 태스크 라우팅 데몬

> 핵심: ProjectHub 태스크 이벤트에 반응하여 적절한 AI 액션으로 자동 라우팅하는 24/7 데몬 (원격 운영 서버 가동)

### VI.1 위상 — "에이전트 팀을 대체하지 않고, 태스크를 그들에게 라우팅"

Hermes는 빌드 도구가 아니라 **반응형 태스크 자동화 레이어**입니다. 사람이 ProjectHub에 태스크를 만들면(`assignee=hermes`), MongoDB Change Stream으로 감지하여 컨텍스트를 적재하고 액션을 실행한 뒤 상태를 되돌려 씁니다.

### VI.2 구조 / 흐름

```
[지식베이스]        Git 추적 메모리 (전역 / 팀 / 프로젝트 / 사용자 범위)
[Watcher 데몬 6종]
   · 이벤트 리스너    — MongoDB Change Stream 감지
   · 컨텍스트 빌더    — 범위별 메모리 + DB 컨텍스트 번들
   · 태스크 라우터    — 태그/키워드 → 액션 분기(질의 / 시뮬 / 빌드 / 생성)
   · 실행기          — 분기된 액션 실행
   · 상태 기록기      — 태스크 상태·코멘트 원자적 갱신
[운영]             systemd 서비스 + LLM 프록시 설정
```

```
팀이 태스크 생성(todo) → Change Stream 감지 → 컨텍스트 적재 → 액션 분기 → 실행 → 상태(in_progress→done) 갱신 → UI 실시간 반영
```

**Stage 게이팅**: Stage 1(DB질의·챗, 상시) / Stage 2(시뮬레이션) / Stage 3(빌드) / Stage 4~6(GameForge 기획·코딩, 2주 파일럿 후 활성 권장, 환경변수로 제어).

### VI.3 실가동 증거

Part 0/2의 텔레메트리가 Hermes 산출물입니다: **trace 2,465 / session 1,319 / token_usage 912 / domain_principles 241 / team_scores 209+799 / prompt_patches 14**. 즉, Hermes는 실험이 아니라 **누적 가동 중인 운영 시스템**이며, 도메인 원칙·프롬프트 패치가 축적되며 스스로 개선되는 구조입니다.

---

# Part VII. BalloonLoop — 통합 레퍼런스 프로젝트

> 핵심: 위 6개 축이 실제로 합류하여 **출하 가능한 게임**을 만들어낸 증명

### VII.1 게임 정의

- **장르**: 퍼즐 / 큐-정렬 (다트를 색상 매칭으로 발사하여 풍선 그리드 클리어)
- **메커니즘**: 1:1 히트(다트 1=풍선 1), 홀더 큐 오버플로(5슬롯) 실패 조건
- **플랫폼**: Unity 2022 LTS, Android 1080×1920 세로, APK + AAB
- **타깃**: 미국, 여성 70%, 평균 32세, ASMR/만족감 선호
- **디자인 필러**: 전략적 긴장(색 선택 압박), 폭발적 만족(연쇄 팝), 시각적 명료성, 즉각 이해, 비대칭 연출

### VII.2 프로젝트 구성

| 구성 | 내용 | 규모 |
|------|------|------|
| 게임 코드베이스 | Unity 프로젝트 + 형상관리(Phase 0~17) | 12GB+ |
| 설계 문서 | 20+ 마크다운 명세(큐생성기, 픽셀아트 워크플로우, 기믹, 교차검증) | ~500KB |
| 레벨 데이터 | 마스터 엑셀 + 생성 300레벨 JSON + 변환기(.NET 8) | ~57MB |
| 히스토리 | 타임라인 + 교차검증 결과 | 10KB |
| 레벨 재생성 v43 | 듀얼 변형 A/B 아트 세트 | 200MB+ |
| 출하 빌드 | APK / AAB | ~200MB |

### VII.3 AI 워크플로우 산출물 (듀얼 출력 표준)

Stage 0(설계 표준) → Tier 1(컨셉, 306줄) → Tier 2(게임 기획 256줄, 시스템 명세 619줄/33시스템, 빌드 오더 851줄) → Tier 3(L3 노드 10종). **YAML(AI 검증·코드생성·DB)** 과 **Docx(디렉터 검수)** 를 항상 함께 출력하는 것이 본 프로젝트에서 확립된 표준입니다. (검증 기획 20건 정규화 완료)

### VII.4 핵심 혁신 — 픽셀아트 → 레벨 변환 파이프라인

픽셀아트 → 레벨 변환 워크플로우(481줄 명세)에 정의된 2단계 파이프라인:
- **Stage 1 필드 생성**: 이미지 입력 → 전처리(리사이즈+색 양자화) → 파싱 → 색상 매핑(팔레트 28, 레벨당 최대 11색 Hard Rule) → 파라미터 매핑 → 기믹 오버레이 → 필드 분석 잠금
- **Stage 2 큐 생성**: 필드 분석(불변) → 매거진 분포 분해 → 그리드 배치 → 큐 기믹 자동 배치(10 후보, 디자이너 1택) → 검증 → 레벨 출력
- **1:1 구조 보증**: 다트 수 = 풍선 수 + 기믹 수명 합 (5배수 정렬)

큐 생성기 명세는 v3.15 기준 **10,666줄**에 달하며, 매거진 분포(cap20 백본 62~68%)·연결 다트 박스(위상정렬로 의존성 사이클 회피)·Hidden 풍선 anti-clustering·Pipe 색 다양성 게이팅 등 10개 Soft Rule + Hard Rule 군을 정의합니다.

### VII.5 다른 도구와의 합류

- **PixelForge 레벨 생성(Part III)** → `PixelArtConverter`(.NET 8) 이미지→레벨 변환 파이프라인 → 300 정본 세트 큐레이션
- **AI Tester(Part II)** → 클리어 가능성 정리(theorem) 검증 + 밸런스 실측
- **ProjectHub/Hermes(Part V/VI)** → 레벨 배치 생성·태스크 자동화
- **GameForge(Part I)** → 기획서→C# 코드(Phase 0~17), DOTween 마이그레이션, 다트 타겟팅 수정 등

### VII.6 야간 자율 디버깅 사례

Phase 17 단계에서 다트 타겟팅(월드 위치 기반·직사) 수정, DOTween 이관, 경로 차단(그리드 점유) 검사 최적화 등이 이뤄졌습니다. 설계 명세 → 코드 생성 → 근본 원인 분석 → 야간 안정화로 이어지는 **AI 증강 개발 속도**를 실증합니다.

---

## 8. 정량 성과 종합

### 8.1 시스템별 핵심 지표

| 영역 | 지표 | 값 |
|------|------|----|
| GameForge | 에이전트 정의 / 명령어 / 훅 / 규칙 | 11 / 20 / 5 / 6 |
| GameForge | 공유 라이브러리 규모 | YAML 파서 531줄, DB 클라이언트 324줄 |
| Virtual Player | Python 파일 / 페르소나 / 장르 옵저버 | ~296 / 5 / 7 |
| Virtual Player | 비전 폴백 계층 | 4-Tier(pHash→SSIM→탐색→Vision) |
| PixelForge | 자동 생성 레벨 / 출하 세트 | 5,093 / 300 |
| PixelForge | 단일 클러스터 비율 개선 | 53% → 69% |
| YOLO 비전 | SLG 클래스 수 / 기믹 F1 / 타입 정확도 | 180 / 0.731 / 0.995 |
| ProjectHub | API 슬림화 / MCP 도구(현재/계획) | −97.2% / 3·15 |
| Hermes | trace / session / token 기록 | 2,465 / 1,319 / 912 |
| BalloonLoop | 출하 레벨 / 명세 규모 / 빌드 | 300 / 큐명세 10,666줄 / APK+AAB |
| AI_WORK_FLOW_TEST | AI 생성 게임 프로젝트 | 6+ 종 |
| DB 전체 | 가동 컬렉션 / 자동생성 레벨 | 30 / 5,093 |

### 8.2 핵심 차별화 포인트 4선

1. **통합 계약 검증(ICS)** — 다중 에이전트 병렬 생성의 통합 실패를 계약 문서 + Stage 5.5 교차 검증으로 구조적으로 차단(업계 일반의 "코드 스니펫 생성"과 구분).
2. **환각의 프로세스화** — 분류 체계 + DB 의무 검색 + 6대 규칙 + 차단형 훅으로, 신뢰성을 모델 성능이 아닌 **시스템 규율**로 확보.
3. **자율 플레이 검증** — 비전으로 게임을 직접 플레이해 밸런스를 실측하고, 생성 레벨을 재검증하는 폐루프(Part II↔III).
4. **실 출하 증명** — PoC가 아니라 BalloonLoop 출하 빌드(APK/AAB)까지 도달, 운영 텔레메트리(trace 2,465)로 실가동 입증.

---

## 9. 한계 및 향후 과제

| 영역 | 현재 한계 | 향후 |
|------|-----------|------|
| 코드 공간 품질 | AI가 코드 텍스트는 잘 생성하나 Unity pivot/anchor·컴포넌트 링크 등 **공간 배치 실행 품질**이 낮음 | 검증된 템플릿 분리 + 생성 후 자동 검증 레이어(ProjectHub MCP Modify 도구로 직접 와이어링) |
| Expert DB | `code_expert` 현재 0건 (승격 파이프라인 가동 초기) | 재사용 성공 누적으로 승격 자산 확보 |
| 레벨 생성 검증 | 자동 생성 레벨의 클리어 가능성 자동 판정 고도화 필요 | Virtual Player 실측 검증 루프 강화 |
| MCP | Tier 1(조회 3종)만 라이브 | Phase 2 Modify/Validate 12종 + ICS Write-Through |
| Hermes | Stage 4~6(생성 워크플로우) 게이팅 상태 | 파일럿 후 단계적 활성 |

---

## 10. 결론

AIMED의 AI 활용은 "생성 AI를 호출하는" 수준을 넘어, **역할 분리된 다중 에이전트가 표준 DB·명시적 계약·자동 검증·실플레이 테스트 위에서 협업하는 게임 스튜디오형 시스템**으로 성숙했습니다. 본 백서가 다룬 7개 축은 독립 도구가 아니라 **단일 데이터 중추(MongoDB)로 연결된 하나의 유기체**이며, 그 결과물로 자사 퍼즐 게임 BalloonLoop를 출하 수준까지 생산했습니다.

핵심은 **신뢰성을 모델이 아닌 엔지니어링으로 확보**했다는 점입니다 — 분류 체계, 계약 시스템, 환각 방지 규칙, 차단형 훅, 자율 플레이 검증이 결합되어, 생성 AI의 근본적 약점(환각·통합 실패·검증 비용)을 프로세스로 통제합니다. 이는 OpenAI 최신 모델과 결합될 때 더 큰 레버리지를 낼 수 있는 **검증 가능한 AI 운영 프레임워크**입니다.

---

## 부록

### 부록 A. MongoDB 컬렉션 인벤토리 요약 (2026-05-26 실측, 30개 컬렉션)

```
[지식 DB]          코드 베이스 141 · 검증 코드 0 · 기획 베이스 40 · 검증 기획 20
                   Unity 설정 19 · 규칙 7 · 검토 대기 3
[PixelForge 운영]  자동 생성 레벨 5,093 · 출하 레벨 300 · 생성 잡 403 · 감사 로그 677
                   태스크 267 · 배치 요청 40 · 아트 에셋 379 · 레벨 백업 52 (외 다수)
[Hermes 텔레메트리] 실행 트레이스 2,465 · 세션 1,319 · 토큰 사용 912 · 기획 품질 점수 799
                   도메인 원칙 241 · 코드 품질 점수 209 · 역할 정의 44 · 프롬프트 패치 14
[공통]             활동 로그 469 · 사용자 3 · 설정 다수
```

### 부록 B. 분류 체계 상세

- **Layer(3)**: Core / Domain / Game
- **Genre(9)**: Generic, RPG, Idle, Merge, SLG, Tycoon, Simulation, Puzzle, Casual
- **Role(21)**: Manager, Controller, Calculator, Processor, Handler, Listener, Provider, Factory, Service, Validator, Converter, Builder, Pool, State, Command, Observer, Helper, Wrapper, Context, Config, UX
- **Tag 대기능(7)**: StateControl, ValueModification, ConditionCheck, ResourceTransfer, DataSync, FlowControl, ResponseTrigger
- **Tag 소기능(11)**: Compare, Calculate, Find, Validate, Assign, Notify, Delay, Spawn, Despawn, Iterate, Aggregate
- **Design Domain(9)**: InGame, OutGame, Balance, Content, BM, LiveOps, UX, Social, Meta

### 부록 C. 기술 스택 요약

| 영역 | 스택 |
|------|------|
| 에이전트 오케스트레이션 | Claude (Opus 4.x / Sonnet 4.x), 커스텀 에이전트 정의, MCP |
| 스크립트/백엔드 | Node.js, Python |
| 비전/ML | ultralytics YOLOv8, OpenCV, PyTorch, Stable Diffusion(레벨 아트) |
| 웹 | Next.js 16/React 19/TS(ProjectHub), Express+EJS(platform), Gradio(webapp) |
| 게임 엔진 | Unity 2022 LTS, C#, DOTween |
| 데이터 | MongoDB Atlas, SQLite(로컬 세션), Excel(레벨 설계) |
| 레벨 생성 / 테스트 자동화 | NumPy 자체 알고리즘, 색상 양자화, ADB(BlueStacks) |
| 패키징 | PyInstaller(.exe), .NET 8(레벨 변환기) |

### 부록 D. 용어집

| 용어 | 정의 |
|------|------|
| ICS | Integration Contract System. 파일 간 연결(이벤트·풀키·필드·호출)을 명시적 계약 문서로 추적·검증하는 체계 |
| MCP | Model Context Protocol. AI가 외부 도구(여기선 Unity 에디터)를 표준 방식으로 제어하는 프로토콜 |
| BT (Behavior Tree) | 행동 트리. AI 테스터의 의사결정을 노드 트리로 구성하는 방식 |
| GOAP | Goal-Oriented Action Planning. 목표 기반으로 상태 전이를 학습·계획하는 기법 |
| pHash / SSIM | 화면 유사도 판정 기법(지각 해시 / 구조적 유사도) — 비전 캐시·매칭에 사용 |
| Field Completer | 미완성 레벨 draft를 자동 완성하는 생성 에이전트 |
| 1:1 구조 보증 | 다트 수 = 풍선 수 + 기믹 수명 합 — 레벨 클리어 가능성의 구조적 전제 |
| Expert DB | 신뢰도 점수 ≥0.6으로 검증 승격된 재사용 자산 컬렉션 |
| Stage 5.5 | Validator의 파일 간 통합 검증 단계 |
| cowork 패턴 | 레벨 배경 공백 배치를 결정하는 13종 기하 패턴 |
| 페르소나 | 행동 특성(반응속도·과금성향 등)이 다른 가상 유저 유형 — 테스트 시뮬레이션 단위 |

---

*문서 끝. 본 백서의 모든 정량 수치는 2026-05-26 시점 실측 또는 명시된 산출물 기준이며, 추정값은 본문에 별도 표기했습니다.*
