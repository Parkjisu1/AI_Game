---
description: 게임 기획서 및 시스템 명세서 생성
arguments:
  - name: input
    description: "게임 URL, 컨셉 설명, 또는 레퍼런스"
    required: true
  - name: genre
    description: "메인 장르 (rpg/idle/merge/slg/tycoon/puzzle)"
    required: true
  - name: project
    description: "프로젝트 이름"
    required: true
---

# Design Document Generation

$input을 분석하여 $genre 장르의 기획서를 생성합니다.

## 출력 위치
```
E:\AI\projects\$project\designs\
├── game_design.yaml        # Layer 1: 게임 기획서
├── system_spec.yaml        # Layer 2: 시스템 명세서
├── build_order.yaml        # 빌드 순서
└── nodes\                  # Layer 3: AI_기획서
    ├── BattleManager.yaml
    ├── CharacterSystem.yaml
    └── ...
```

## Layer 1: 게임 기획서

### 공통 섹션 (필수)
```yaml
game_overview:
  title: "게임 제목"
  genre: "$genre"
  sub_genre: []
  platform: "mobile"
  target_user: "midcore"
  session_length: "5min"
  one_liner: "한 줄 설명"
  references: []

core_experience:
  main_fun: "핵심 재미"
  emotion_goal: "감정 목표"
  core_verbs: []

core_loop:
  main_loop: { description: "", flow: [], duration: "" }
  daily_loop: { description: "", flow: [] }
  long_term_loop: { description: "", flow: [] }

session_structure:
  start_condition: ""
  progress_type: "auto|manual|turn|realtime"
  end_conditions: []
  result_handling: ""

monetization:
  main_bm: "f2p"
  revenue_sources: []
```

### 장르별 섹션
$genre에 따라 해당 섹션 추가

## Layer 2: 시스템 명세서

```yaml
system_list:
  Core: []
  Domain: []
  Game: []

systems:
  - nodeId: "시스템명"
    layer: "Domain"
    genre: "$genre"
    role: "Manager"
    purpose: "목적"
    responsibilities: []
    states: []
    behaviors:
      - trigger: ""
        action: ""
        result: ""
    relations:
      uses: []
      usedBy: []
      publishes: []
      subscribes: []
```

## Layer 3: AI_기획서 (노드별)

```yaml
metadata:
  nodeId: "시스템명"
  version: "1.0.0"
  phase: 1
  role: "Manager"

dependencies:
  internal: []
  external: []

contract:
  provides: []
  requires: []

tags:
  layer: "Domain"
  genre: "$genre"
  role: "Manager"
  system: ""
  majorFunctions: []
  minorFunctions: []

logicFlow:
  - step: 1
    tag: ""
    action: ""
    next: 2

referencePatterns:
  - source: ""
    pattern: ""

codeHints:
  patterns: []
  avoidPatterns: []
```

## 빌드 오더 결정

의존성 기반 Phase 할당:
- Phase 0: Core (의존성 없음)
- Phase 1: 기반 Domain (Core만 의존)
- Phase 2: 상위 Domain (Domain 의존)
- Phase 3: Game Layer

## 출력
- 생성된 파일 목록
- 시스템 개수
- 빌드 Phase 요약
