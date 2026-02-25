---
description: 기획서 통합 검증 (교차 검증, 갭 탐지, 밸런스 시뮬레이션)
arguments:
  - name: project
    description: 프로젝트 이름
    required: true
---

# Design Validation

E:\AI\projects\$project\designs\ 의 기획서를 통합 검증합니다.

## 검증 대상 파일
```
E:\AI\projects\$project\designs\
├── game_design.yaml
├── system_spec.yaml
└── design_workflow\
    ├── systems\*.yaml
    ├── balance\*.yaml
    ├── content\*.yaml
    └── bm\*.yaml
```

## 5단계 검증

### Step 1: 교차 일관성 검사 (Cross-Consistency)
시스템 간 계약 정합성:

```
검사 항목:
- system_spec.yaml의 relations.uses 목록이 실제 존재하는 노드인지 확인
- PublishEvent ↔ SubscribeEvent 페어 매칭
- Contract provides/requires 교차 검증
  (A.requires ⊆ B.provides 이어야 함)
```

**통과 기준**: 미해결 의존성 0개

### Step 2: 유저 여정 검증 (User Journey Check)
핵심 게임 루프의 완전성:

```
신규 유저 여정:
  □ 튜토리얼 → 첫 전투 → 첫 보상 → 첫 업그레이드 경로 존재

일일 루프:
  □ 일일 콘텐츠 → 재화 획득 → 소비 채널 완결성
  □ 세션 길이 = (일일 콘텐츠 소비 시간) 일치 여부

장기 루프:
  □ 주요 성장 마일스톤 (Lv10, Lv30, Lv50 등) 정의 여부
  □ 콘텐츠 소비 → BM 전환 포인트 명시 여부
```

**통과 기준**: 각 루프 단계가 최소 1개 시스템에 매핑됨

### Step 3: 갭 탐지 (Gap Detection)
누락된 시스템/수치 감지:

```
장르 필수 항목 체크리스트 ($genre 기준):
  □ 전투 시스템 (InGame)
  □ 경제 루프 (Economy cycle: 획득 → 소비)
  □ 성장 공식 (Balance formulas)
  □ 핵심 BM 채널 최소 1개

미정의 수치 감지:
  □ value: null 항목 중 balance_area = "combat" 인 것
  □ 핵심 공식(exp_curve_formula, damage_formula 등) null 여부
  □ 가챠가 있는데 확률 정의 누락
```

**출력**: 갭 목록 + 우선순위 (High/Medium/Low)

### Step 4: 자가 검증 (Self-Verification)
AI 생성 기획서의 내부 모순 탐지:

```
수치 일관성:
  □ 일일 골드 획득 vs 주요 아이템 비용 비율 (권장: 7~14일치)
  □ 레벨 성장 속도 vs 콘텐츠 해금 속도 동기화
  □ 가챠 기대값 vs 무과금 재화 획득량 (천장 이내 달성 가능한지)

밸런스 시뮬레이션 (10레벨 단위):
  □ 레벨 1, 10, 30, 50, MAX 스탯 값 계산 및 로그 출력
  □ 전투력 곡선이 단조증가인지 확인 (역전 구간 탐지)
```

**통과 기준**: 심각한 수치 오류 0개 (경고는 허용)

### Step 5: 점수 업데이트 (Score Update)
검증 결과에 따라 Design DB 신뢰도 점수 업데이트:

```
검증 완전 통과:    score += 0.2
갭 탐지 항목 있음: score 유지
자가 검증 실패:    score -= 0.1
```

## 검증 결과 출력 형식

```yaml
validation_result:
  project: "$project"
  timestamp: "ISO8601"

  step1_cross_consistency:
    status: PASS | FAIL
    issues: []

  step2_user_journey:
    status: PASS | WARN | FAIL
    missing_loops: []

  step3_gap_detection:
    status: PASS | WARN
    gaps:
      - id: "GAP-001"
        priority: High | Medium | Low
        description: ""

  step4_self_verification:
    status: PASS | WARN | FAIL
    balance_simulation:
      - level: 1
        hp: 0
        atk: 0
    issues: []

  step5_score_update:
    before: 0.4
    after: 0.6

  overall: PASS | WARN | FAIL
  recommended_actions: []
```

## 출력 위치
```
E:\AI\projects\$project\designs\validation_report.yaml
```
