# GameForge: AI 게임 개발 파이프라인 | AI Game Development Pipeline

> AI 에이전트 팀이 한 문장의 게임 컨셉으로부터 게임 설계 문서와 Unity C# 소스 코드를 자동 생성합니다.
>
> AI Agent Team that auto-generates game design documents and Unity C# source code from a single concept sentence.

```
입력(Input):  "방치형 RPG, AFK 수입 + 캐릭터 수집 시스템"
출력(Output): 3계층 설계 문서 + 54개 Unity C# 시스템 + 검증 리포트
```

---

## 개요 | Overview

GameForge는 게임 개발을 자동화하는 **자기 강화형 AI 파이프라인**입니다. 설계 문서 작성부터 코드 생성까지 전 과정을 처리합니다.

GameForge is a **self-reinforcing AI pipeline** that automates game development — from design documentation to production-ready code generation.

하나의 게임 컨셉이 **3계층 설계 문서**(게임 설계 → 시스템 스펙 → AI YAML)로 변환된 후, 병렬 AI 에이전트 팀을 통해 Unity C# 소스 코드로 컴파일됩니다. 모든 결과물은 다단계 품질 검증을 거치며, 지식 DB에 축적되어 **프로젝트가 진행될수록 품질이 자동으로 향상**됩니다.

A single game concept is transformed into **3-Layer design documents** (Game Design → System Spec → AI YAML), then compiled into Unity C# source code via parallel AI agent teams. Every output is validated through multi-stage quality gates and accumulated into a knowledge database that **improves quality with each project**.

### 지원 플랫폼 | Supported Platforms

| 플랫폼 | 출력물 | 용도 |
|---------|--------|------|
| **Unity** | C# MonoBehaviour 소스 코드 | 모바일 / PC 게임 |
| **Playable** | 단일 HTML5 파일 | 플레이어블 광고 (Meta, Google, IronSource, AppLovin) |

### 지원 장르 | Supported Genres

Generic, RPG, Idle, SLG, Simulation, Tycoon, Merge, Puzzle, Casual — **9개 장르**

### 핵심 지표 | Key Metrics

| 항목 | 규모 |
|------|------|
| 코드 지식 DB | 958+ 레퍼런스 파일 (8개 장르) |
| 전문가 지식 DB | 20+ 검증된 고품질 파일 |
| 설계 지식 DB | 97+ 설계 문서 |
| 자동화 스크립트 | 18개 스크립트 + 4개 공유 라이브러리 |
| AI 에이전트 | 9개 전문 역할 |
| 검증된 프로젝트 | 6+ (Puzzle, RPG, Idle, Match3, Playable Ads) |

---

## 핵심 아키텍처 | Core Architecture

### 3-AI 역할 분리 (환각 방지) | 3-AI Role Separation (Anti-Hallucination)

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   AI Stage 1    │    │   AI Stage 2    │    │   AI Stage 3    │
│   DB 처리       │ →  │   생성          │ →  │   검증          │
│   DB Processing │    │   Generation    │    │   Validation    │
│                 │    │                 │    │                 │
│ • 소스 파싱     │    │ • 설계 문서     │    │ • 일관성 검증   │
│ • 분류/태깅     │    │ • 코드 생성     │    │ • 밸런스 시뮬   │
│ • DB 저장       │    │ • DB 참조       │    │ • 피드백 생성   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

각 AI는 **단일 역할**에 집중하여 컨텍스트 오염과 환각을 방지합니다.

Each AI focuses on a **single role** to prevent context contamination and hallucination.

### 이중 파이프라인 | Dual Pipeline

```
설계 워크플로우 (8단계)                코드 워크플로우 (4단계)
Design Workflow (8 Stages)            Code Workflow (4 Phases)
──────────────────────────           ────────────────────────
Stage 0: 설계 표준 정의               Phase 0: 코어 아키텍처 (리드 코더)
Stage 1: 지식 DB 처리                 Phase 1: 도메인 시스템 (리드 + 서브 ×2)
Stage 2: 설계 문서 생성               Phase 2: 상위 도메인 (병렬)
Stage 3: 교차 검증                    Phase 3: 게임 레이어 & UI (병렬)
Stage 4: 디렉터 리뷰                      + 다단계 검증
Stage 5: 재생성 평가                      + 지식 축적
Stage 6: 전문가 DB 축적
Stage 7: AI 플레이 검증
Stage 8: 라이브 동기화
```

### 자기 강화 학습 루프 | Self-Reinforcing Knowledge Loop

```
프로젝트 A → 생성 → 검증 → Expert DB
                                ↓
프로젝트 B → 생성 ← Expert DB 참조 (품질 ↑)
          → 검증 → Expert DB (규모 ↑)
                        ↓
프로젝트 C → 생성 ← Expert DB 참조 (품질 ↑↑)
```

프로젝트가 누적될수록 지식 DB가 성장하며 품질이 자연스럽게 향상됩니다.

---

## 에이전트 팀 | Agent Team

```
                    ┌──────────────────────────┐
                    │   Lead (Opus)             │
                    │   PM — 태스크 분배         │
                    └─────────┬────────────────┘
         ┌──────────┬────────┼────────┬──────────┐
    ┌────┴─────┐ ┌──┴───┐   │   ┌────┴────┐ ┌───┴────────┐
    │ Designer │ │ Main │   │   │ Sub     │ │ Playable   │
    │ 설계자   │ │Coder │   │   │Coder ×2 │ │ Coder      │
    │ 3계층    │ │ 코어 │   │   │ 병렬    │ │ HTML5 광고 │
    └──────────┘ │ 설계 │   │   └─────────┘ └────────────┘
                 └──────┘   │
         ┌──────────┐  ┌────┴─────┐  ┌──────────────┐
         │ Design   │  │Validator │  │ DB Builder   │
         │Validator │  │ 코드 QA  │  │ 온디맨드     │
         │ 품질 게  │  └──────────┘  └──────────────┘
         │ 이트     │
         └──────────┘
```

| 에이전트 | 역할 |
|----------|------|
| **Lead** | PM — 태스크 분배, 결과 평가, 단계 게이트 관리 |
| **Designer** | 3계층 설계 문서 (게임 설계 → 시스템 스펙 → AI YAML) |
| **Main Coder** | 코어 아키텍처 + 복잡 시스템 설계 |
| **Sub Coder ×2** | Main Coder 패턴을 따라 병렬 구현 |
| **Playable Coder** | HTML5 단일 파일 플레이어블 광고 |
| **Validator** | 5+1단계 코드 검증 |
| **Design Validator** | 6단계 설계 검증, 품질 게이트 관리 |
| **DB Builder** | 소스 코드 파싱 → 지식 DB (온디맨드) |

---

## 분류 체계 | Classification System

### 코드 분류 | Code Taxonomy

| 축 | 카테고리 |
|----|----------|
| **Layer** (3) | Core / Domain / Game |
| **Genre** (9) | Generic / RPG / Idle / SLG / Simulation / Tycoon / Merge / Puzzle / Casual |
| **Role** (21) | Manager, Controller, Calculator, Processor, Handler, Factory, Service, Validator 등 |
| **행위 태그** | 7 매크로 + 11 마이크로 태그 |

### 설계 분류 | Design Taxonomy

| 축 | 카테고리 |
|----|----------|
| **Domain** (9) | InGame / OutGame / Balance / Content / BM / LiveOps / UX / Social / Meta |
| **Data Type** | formula / table / rule / flow / config / content_data |
| **Source** (6) | original / produced / live / observed / community / generated |

---

## 지식 데이터베이스 | Knowledge Database

### 5단계 검색 우선순위 | 5-Level Search Priority

| 우선순위 | 소스 | 조건 |
|----------|------|------|
| 1 | Expert DB (장르 매칭) | 장르 일치 AND 점수 >= 0.6 |
| 2 | Expert DB (Generic) | 장르 = Generic AND 점수 >= 0.6 |
| 3 | Base DB (장르 매칭) | 장르 일치 |
| 4 | Base DB (Generic) | 장르 = Generic |
| 5 | AI 생성 | 레퍼런스 없음 (최후 수단) |

### 신뢰 점수 시스템 | Trust Score System

| 이벤트 | 점수 변동 |
|--------|-----------|
| 최초 저장 | +0.3 ~ 0.4 |
| 피드백 반영 | +0.1 ~ 0.2 |
| 디렉터 승인 | +0.2 |
| 재사용 성공 | +0.1 |
| 재사용 실패 | -0.1 ~ -0.15 |
| **Expert 승격 기준** | **>= 0.6** |

---

## AI 테스터 (가상 플레이어) | AI Tester (Virtual Player)

AI 기반 자율 게임 테스트 시스템.

AI-powered autonomous game testing system.

### 4계층 지능 구조 | 4-Layer Intelligence

```
Layer 4: 장르 스키마     — RPG / Idle / Merge / SLG / Puzzle 전략
Layer 3: 적응 학습       — 실패 기억, 루프 감지, 공간 기억
Layer 2: 추론            — GOAP 플래너, 목표 라이브러리, 유틸리티 스코어링
Layer 1: 인지            — OCR, 게이지 판독, 상태 감지, 화면 분석
```

### 주요 기능 | Capabilities

- **10개 AI 옵저버**가 32개 게임 파라미터 추정 (~85-89.5% 정확도)
- **5개 게임 장르**에 대한 전용 전략
- **적응형 학습** — 실패 기억 및 루프 감지
- **GOAP** (목표 지향 행동 계획) 기반 의사결정
- **컴퓨터 비전** 기반 화면 분석 (YOLOv11)
- 레벨 1 → 30+ 자율 플레이 테스트

---

## 품질 보증 | Quality Assurance

### 코드 검증 (5+1단계) | Code Validation

1. **Syntax** — 컴파일 오류, 문법 검사
2. **Dependency** — 누락 참조, 순환 의존성
3. **Contract** — provides/requires 인터페이스 매칭
4. **Null Safety** — Null 참조 보호
5. **Pattern** — 아키텍처 패턴 준수
6. **Build** (선택) — Unity 배치모드 검증

### 설계 검증 (6단계) | Design Validation

1. **Cross-Consistency** — 시스템↔밸런스, 콘텐츠↔시스템, BM↔밸런스
2. **User Journey** — Day 1~30 페르소나 시뮬레이션
3. **Gap Detection** — 누락 참조, 미정의 항목 탐지
4. **Self-Verification** — 내부 모순, 완전성 검사
5. **Quality Gates** (6종) — 네이밍 / 완전성 / 의존성 / 로직 흐름 / 중복 / 교차 문서
6. **Build Verification** (선택) — 풀 밸런스 시뮬레이터 실행

---

## 자동화 | Automation

### 명령어 | Commands

| 명령어 | 용도 |
|--------|------|
| `/parse-source` | C# 소스 → 코드 지식 DB |
| `/parse-design` | 설계 문서 → 설계 지식 DB |
| `/generate-design` | 3계층 설계 문서 생성 |
| `/generate-design-v2` | 풀 8단계 설계 워크플로우 |
| `/generate-code` | YAML 스펙 → Unity C# 코드 생성 |
| `/validate-code` | 5단계 코드 검증 |
| `/validate-design` | 6단계 설계 검증 |
| `/sync-live` | 라이브 데이터 동기화 |

### 스크립트 | Scripts

| 카테고리 | 용도 |
|----------|------|
| **DB 파싱** | C# 소스 코드 및 설계 문서를 지식 DB로 파싱 |
| **DB 검색** | 다중 장르, 다중 도메인 우선순위 기반 검색 |
| **시뮬레이션** | 경제 밸런스 시뮬레이션, 플레이 검증 |
| **품질** | KPI 리포트 생성, 품질 지표, 버전 관리 |
| **공유 라이브러리** | YAML 유틸, 안전 I/O, 도메인 분류, 점수 관리 |

---

## 검증된 프로젝트 | Verified Projects

| 프로젝트 | 장르 | 규모 | 결과 |
|----------|------|------|------|
| 퍼즐 게임 A | Puzzle | 50 C# 파일 | 26개 시스템, 풀 파이프라인 |
| 퍼즐 게임 B | Puzzle | 37 C# 파일 | 정렬 퍼즐 전체 시스템 |
| RPG 게임 | RPG (Idle) | 51 C# 파일 | 41개 시스템, 전투/캐릭터/장비 |
| Match3 게임 | Match3 | 34 수정 파일 | 대규모 코드 수정, 83개 이슈 해결 |
| Idle 게임 | Idle | 역공학 분석 | 54개 시스템, 89개 설계 엔트리, B+ 등급 |
| 플레이어블 광고 | 다양 | 8+ HTML5 | 주요 광고 네트워크용 다중 포맷 |

---

## 기술 결정 | Technical Decisions

| 결정 | 이유 |
|------|------|
| **YAML** 설계 문서 포맷 | 사람이 읽기 쉽고 AI가 파싱하기 용이, 주석 지원 |
| **3계층 설계 문서** | 사람의 의도 → 코드 구조로 점진적 변환 |
| **이중 모델 전략** | 아키텍처에는 고추론 모델, 병렬 구현에는 고속 모델 |
| **JS 밸런스 시뮬** | LLM은 반복 계산에서 오차 누적, JS는 정확한 결과 제공 |
| **인덱스 파일 분리** | 인덱스로 경량 검색, 상세 정보는 온디맨드 로딩 |
| **필수 연역 추론** | 설명 없는 실패에서 잘못된 패턴 학습 방지 |

---

## 시작하기 | Getting Started

### 필수 요구사항 | Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- Node.js 18+
- Python 3.13+ (AI 테스터용)
- Android 에뮬레이터 + ADB (플레이 검증용)

### 빠른 시작 | Quick Start

```bash
# 컨셉으로부터 게임 생성
/generate-design "방치형 RPG, AFK 수입 + 캐릭터 수집" --genre idle

# 에이전트 팀 병렬 생성
Make a game. Idle RPG with AFK income. Use Agent Team with 3 Coders.

# 플레이어블 광고 생성
Match3 playable ad, candy theme. Use Agent Team.
```

---

## 라이선스 | License

MIT License

---

*GameForge v2.3 — 2026.03*
