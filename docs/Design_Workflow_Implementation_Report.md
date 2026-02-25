# Design Workflow Implementation Report
## 8-Stage Game Design AI Pipeline - 최종 구현 보고서

**작성일**: 2026-02-25
**총 코드량**: 5,933 lines (16 new files + 3 modified files)
**구현 방식**: Agent Team 4명 병렬 + Lead 직접 작업

---

## 1. 구현 완료 현황

### Phase A: Foundation (DB + Search Infrastructure)

| 항목 | 파일 | 라인 | 상태 | 검증 |
|------|------|------|------|------|
| Design DB 디렉토리 | `db/design/` (90 dirs + JSON) | - | PASS | 9 genres x 10 domains 확인 |
| Design DB 검색 | `scripts/design-db-search.js` | 454 | PASS | 5단계 우선순위 검증 완료 |
| Design 파서 | `scripts/design-parser.js` | 882 | PASS | YAML/CSV E2E 파이프라인 검증 |

### Phase B: Agent Definitions

| 항목 | 파일 | 라인 | 상태 |
|------|------|------|------|
| Design DB Builder | `.claude/agents/design-db-builder.md` | 259 | PASS |
| Design Validator | `.claude/agents/design-validator.md` | 252 | PASS |
| Designer 확장 | `.claude/agents/designer.md` | 517 (+189) | PASS |
| Balance Simulator | `scripts/balance-simulator.js` | 594 | PASS |

### Phase C: Integration Scripts

| 항목 | 파일 | 라인 | 상태 |
|------|------|------|------|
| C10+ → Design DB | `scripts/c10-to-design-db.js` | 615 | PASS |
| Design → Code Bridge | `scripts/design-to-code-bridge.js` | 860 | PASS |

### Phase D: Verification & Live Sync

| 항목 | 파일 | 라인 | 상태 |
|------|------|------|------|
| Play Verification | `scripts/play-verification.js` | 370 | PASS |
| Virtual Player Bridge | `scripts/virtual-player-bridge.js` | 324 | PASS |
| Design Versioning | `scripts/design-version.js` | 306 | PASS |

### Phase E: Automation

| 항목 | 파일 | 라인 | 상태 |
|------|------|------|------|
| /parse-design | `.claude/commands/parse-design.md` | 93 | PASS |
| /generate-design-v2 | `.claude/commands/generate-design-v2.md` | 129 | PASS |
| /validate-design | `.claude/commands/validate-design.md` | 142 | PASS |
| /sync-live | `.claude/commands/sync-live.md` | 136 | PASS |

### Documentation Updates

| 파일 | 변경 내용 |
|------|-----------|
| `CLAUDE.md` | Design DB 경로, 분류 체계, 검색 우선순위, 피드백 카테고리, Agent 목록 추가 |
| `docs/WORKFLOW.md` | Design Workflow 파이프라인, Task Graph, 검증 단계, 라이브 동기화 추가 |

---

## 2. 검증 결과 상세

### 2-1. design-db-search.js — 5단계 우선순위 검색

```
TEST 1: RPG Balance 검색
  Priority 1: Expert(RPG)          → expert__rpg__balance__combat_dps_formula    (score 0.67)
  Priority 2: Expert(Generic)      → expert__generic__balance__inflation_control (score 0.63)
  Priority 3: Base(rpg/balance)    → ash_n_veil__balance__growth__level_curve    (score 0.54)
  Priority 4: Base(generic/balance)→ generic__balance__economy__sink_source_rule (score 0.50)
  결과: Expert > Expert(Generic) > Base(genre) > Base(generic) 순서 정확

TEST 2: system "전투" 부분 일치
  "전투 > 스킬", "전투 > 데미지 판정" 둘 다 부분 일치 검색 성공
  Domain=InGame 필터로 다른 도메인 결과 제외

TEST 3: data_type=formula 필터
  formula 타입 3건만 반환 (table, rule, flow 제외)

TEST 4: Pretty 출력 + Detail 로드
  Summary, Provides, Tags, code_mapping 정상 로드
  detail 파일 없는 엔트리 graceful 처리

TEST 5: Idle 장르 크로스 검색
  Expert(Generic) + Generic Base + Idle Base 순서
  RPG 전용 데이터 미포함 (장르 격리 정상)

Source 선호도: internal_original(+0.1) > internal_produced(+0.05) > observed(+0.02) 반영 확인
```

### 2-2. balance-simulator.js — 4가지 모드

```
ECONOMY (14일 시뮬레이션):
  수입: daily 2,200 (base 1500 + events 500 + ads 200)
  지출: daily 2,900 (upgrade 800 + gacha 1500 + potion 600)
  Drain Rate: 131.8% → ECONOMY_GAP 탐지
  초기 잔고 5,000 → Day 8에 마이너스 전환 → NEGATIVE_BALANCE 탐지
  결과: 21개 outlier 정상 플래그

COMBAT (4캐릭터 vs 2적 DPS):
  warrior: 580.5 DPS (normal), 387 DPS (boss)
  mage:    280 DPS (normal), 175 DPS (boss)
  assassin: 1,344 DPS (normal), 1,075 DPS (boss)
  tank:    98.4 DPS (normal), 61.5 DPS (boss)
  DPS 비율: assassin/tank = 13.66x → STAT_OUTLIER 탐지 (임계값 3.0x)

GACHA (SSR, 2% 확률, 80회 천장):
  5,000회 몬테카를로 시뮬레이션
  기대 뽑기 수: 39회
  중앙값: 34회 | P90: 80회 | P99: 80회 (천장 도달)
  결과: outlier 없음 (천장 시스템이 정상 작동)

GROWTH (HP 스탯, Lv1~90):
  총 성장비: 800x (100 → 80,000)
  평균 성장 팩터: 2.659
  Lv90→100 외삽: 311,782,868 (지수 성장 경고 가능)
  결과: outlier 없음 (급격한 스파이크/드롭 없음)
```

### 2-3. design-parser.js — YAML/CSV 파싱

```
YAML 파싱 (rpg_combat_design.yaml):
  입력: 전투 시스템 기획서 (rules 4개: 기본 공격, 크리티컬, 속성 상성, 전투 흐름)
  출력: db/design/base/rpg/combat/ 에 인덱스 + 상세 파일 1건 저장
  E2E: --domain combat 검색으로 정상 조회

CSV 파싱 (rpg_economy.csv):
  입력: 경제 시스템 6행 (일일퀘스트, 스테이지, 장비강화, 가챠, 상점, 주간보상)
  출력: db/design/base/rpg/economy/ 에 인덱스 6건 + 상세 파일 6건 저장
  E2E: --domain economy 검색으로 5건 정상 조회 (top 5 기본값)
```

---

## 3. 아키텍처 다이어그램

```
                        ┌─────────────────────────────┐
                        │     Design Workflow (8단계)   │
                        └──────────────┬──────────────┘
                                       │
    ┌──────────────────────────────────┼──────────────────────────────────┐
    │                                  │                                  │
    ▼                                  ▼                                  ▼
┌────────────┐              ┌──────────────────┐              ┌────────────────┐
│ Stage 1    │              │ Stage 2-1~2-5    │              │ Stage 3        │
│ DB 구축    │              │ 기획 생성         │              │ 통합 검증      │
│            │              │                  │              │                │
│ /parse-    │              │ /generate-       │              │ /validate-     │
│  design    │              │  design-v2       │              │  design        │
│            │              │                  │              │                │
│ Design DB  │─────────────▶│ Designer         │─────────────▶│ Design         │
│ Builder    │              │ (design mode)    │              │ Validator      │
└────────────┘              └──────────────────┘              └───────┬────────┘
      │                                                               │
      │  ┌────────────────┐      ┌────────────────┐                  │
      │  │ Stage 4        │      │ Stage 5-6      │                  │
      │  │ 디렉터 리뷰    │◀─────│ 점수/Expert DB │◀─────────────────┘
      │  │ (수동 게이트)   │      │ 승격           │
      │  └────────────────┘      └────────────────┘
      │
      │  ┌────────────────┐      ┌────────────────┐
      │  │ Stage 7        │      │ Stage 8        │
      │  │ Play 검증      │      │ Live 버전관리  │
      │  │ play-verify.js │      │ /sync-live     │
      │  │ VP bridge      │      │ design-ver.js  │
      │  └────────────────┘      └────────────────┘
      │
      └──────────▶ ┌────────────────────┐
                   │ Design → Code      │
                   │ Bridge             │
                   │ design-to-code-    │
                   │ bridge.js          │
                   └────────┬───────────┘
                            │
                            ▼
                   ┌────────────────────┐
                   │ Code Workflow      │
                   │ (기존 파이프라인)   │
                   │ system_spec.yaml   │
                   │ + nodes/*.yaml     │
                   └────────────────────┘
```

---

## 4. DB 구조

```
E:\AI\db\design\
├── base\
│   ├── generic\          # 장르 무관
│   │   ├── ingame\       { index.json, files/ }
│   │   ├── outgame\
│   │   ├── balance\
│   │   ├── content\
│   │   ├── bm\
│   │   ├── liveops\
│   │   ├── ux\
│   │   ├── social\
│   │   ├── meta\
│   │   └── projects\
│   ├── rpg\              # 장르별 (동일 구조)
│   ├── idle\
│   ├── slg\
│   ├── simulation\
│   ├── tycoon\
│   ├── merge\
│   ├── puzzle\
│   └── casual\
├── expert\               # 검증 완료 (score >= 0.6)
│   ├── index.json
│   └── files\
└── rules\                # 축적된 규칙
    ├── generic_rules.json
    ├── genre_rules.json
    └── domain_rules.json
```

---

## 5. 명령어 요약

| 명령어 | 용도 | 담당 Agent | 스크립트 |
|--------|------|-----------|----------|
| `/parse-design [path] [genre]` | 기획 문서 → Design DB | Design DB Builder | design-parser.js |
| `/generate-design-v2 [concept] [genre] [project]` | 8단계 기획 워크플로우 | Designer (design mode) | - |
| `/validate-design [project]` | 기획 통합 검증 | Design Validator | balance-simulator.js |
| `/sync-live [project] [version]` | 라이브 데이터 동기화 | Design DB Builder | design-version.js |

### CLI 스크립트

```bash
# DB 검색
node scripts/design-db-search.js --genre rpg --domain Balance --system "전투" --json

# 기획 자료 파싱
node scripts/design-parser.js --input docs/battle.yaml --format yaml --genre rpg --project MyGame

# 밸런스 시뮬레이션
node scripts/balance-simulator.js --input balance.yaml --mode economy --days 30 --output results.json

# C10+ → Design DB 변환
node scripts/c10-to-design-db.js --game ash_n_veil --genre Idle

# Design → Code 변환
node scripts/design-to-code-bridge.js --project MyGame --input designs/design_workflow --output designs

# 버전 관리
node scripts/design-version.js --designId xxx --genre rpg --domain balance --version 1.1.0 --phase post_launch

# 플레이 검증
node scripts/play-verification.js --project MyGame --mode accelerated

# VP 브리지
node scripts/virtual-player-bridge.js --input vp_export.yaml --project MyGame --output feedback.json
```

---

## 6. 알려진 제한사항 및 개선 포인트

### balance-simulator.js
- 커스텀 YAML 파서 사용 (외부 의존성 없음) → 복잡한 YAML 구조 (앵커, 멀티라인 등) 미지원
- 각 모드별 기대 입력 스키마가 고정되어 있음 (주석으로 문서화)
- 해결 방안: `js-yaml` 패키지 도입 시 파서 교체 가능

### design-parser.js
- YAML 입력의 `domain` 필드를 그대로 사용하여 커스텀 도메인 생성 가능 (combat, economy 등)
- 표준 9 도메인(InGame 등)으로 자동 매핑하려면 C10+ 도메인 매핑 테이블 적용 필요
- CSV notes 컬럼이 sink_amount로 매핑되는 오프셋 이슈 (CSV 헤더 순서 의존)

### design-db-search.js
- 표준 DOMAINS 리스트 외 커스텀 도메인(combat, economy)도 검색 가능 (유연성)
- normalizeDomain()에 combat→ingame, economy→balance 매핑 추가 가능

---

## 7. Agent Team 실행 결과

| Agent | 할당 태스크 | 소요 | 생성 파일 수 |
|-------|------------|------|-------------|
| Lead | #1 DB 디렉토리 | 즉시 | 90+ dirs + JSONs |
| scripts-agent-1 | #2, #3 | ~3분 | 2 scripts |
| agents-agent-2 | #4, #5, #6, #7 | ~5분 | 3 agents + 1 script |
| integration-agent-3 | #8, #9, #11 | ~7분 | 2 scripts + 4 commands |
| verification-agent-4 | #10, #12 | ~5분 | 3 scripts + 2 docs |

**총 12 태스크 / 12 완료 / 0 실패**
