---
description: 게임 기획 워크플로우 실행 (8단계 파이프라인)
arguments:
  - name: concept
    description: 게임 컨셉 설명
    required: true
  - name: genre
    description: "메인 장르 (rpg/idle/merge/slg/tycoon/simulation/puzzle/casual)"
    required: true
  - name: project
    description: 프로젝트 이름
    required: true
---

# Design Workflow v2 — 8단계 파이프라인

$concept 을 기반으로 $genre 장르의 $project 게임 기획을 8단계로 완성합니다.

## 출력 위치
```
E:\AI\projects\$project\designs\
├── game_design.yaml             # Layer 1: 게임 기획서
├── system_spec.yaml             # Layer 2: 시스템 명세서
├── build_order.yaml             # 빌드 순서
├── nodes\                       # Layer 3: AI_기획서 (노드별)
│   ├── BattleManager.yaml
│   └── ...
└── design_workflow\             # 워크플로우 산출물
    ├── systems\                 # 시스템 설계
    ├── balance\                 # 밸런스 설계
    ├── content\                 # 콘텐츠 설계
    └── bm\                      # 비즈니스 모델 설계
```

## 8단계 파이프라인

### Step 1: 컨셉 분석
- 핵심 게임플레이 메카닉 추출
- 장르별 필수 시스템 목록화
- 레퍼런스 게임 패턴 참조 (Design DB 검색)
- 출력: `designs/game_design.yaml` (game_overview, core_experience, core_loop)

### Step 2: 시스템 설계
각 도메인별 핵심 시스템 정의:
```
InGame:   전투/스킬/스테이지/캐릭터
OutGame:  인벤토리/상점/아이템/장비
Balance:  성장 공식/스탯 체계
Content:  퀘스트/스테이지/보상
BM:       결제/가챠/패스
UX:       UI 흐름/이펙트/오디오
```
출력: `design_workflow/systems/*.yaml`

### Step 3: 콘텐츠 설계
- 스테이지 구성 (챕터/단계/보스 주기)
- 퀘스트/미션 체계
- 보상 테이블
- 출력: `design_workflow/content/*.yaml`

### Step 4: 밸런스 설계
수치 공식 정의:
```yaml
growth_formulas:
  hp:   "baseHP × (1 + growthRate)^level"
  atk:  "baseATK + flatBonus × level"
  exp:  "baseEXP × expCurve^(level - 1)"

economy:
  gold_income_per_min: <공식>
  cost_scaling: <공식>
```
출력: `design_workflow/balance/*.yaml`

### Step 5: BM 설계
- 가챠 구조 (확률/천장/비용)
- 패스/시즌패스 설계
- IAP 상품 목록
- 광고 배치
- 출력: `design_workflow/bm/*.yaml`

### Step 6: 통합 정합성 검사
교차 검증:
- 인게임 경제 ↔ 콘텐츠 소비 속도 일치 여부
- 밸런스 곡선 ↔ BM 구매 시점 연계 검증
- 일일 세션 시간 ↔ 콘텐츠 소비량 정합

### Step 7: 코드 파이프라인 변환
```bash
node E:/AI/scripts/design-to-code-bridge.js \
  --project $project \
  --input E:/AI/projects/$project/designs/design_workflow \
  --output E:/AI/projects/$project/designs
```
출력: `system_spec.yaml` + `nodes/*.yaml`

### Step 8: Design DB 저장
- 생성된 기획 데이터를 Design DB에 저장
- 재사용 가능한 패턴 추출 및 인덱싱
- 장르별 표준 수치 업데이트

## 장르별 필수 포함 항목

### Idle RPG
- 방치 수익 공식 (idle_gold_per_min)
- 오프라인 누적 한도 (idle_max_accumulation)
- 자동 전투 해금 조건 (auto_battle_unlock)

### Merge
- 병합 테이블 (N+N → N+1)
- 에너지 시스템
- 생산-병합 루프

### SLG
- 건물 업그레이드 트리
- 병력 생산 공식
- PvP 전투 공식

### Tycoon
- 수익 생성 공식
- 업그레이드 비용 곡선
- 고객 유입 모델

## 출력
- 생성된 파일 목록
- 시스템 개수 (도메인별)
- 밸런스 공식 요약
- 정합성 검사 결과
- 빌드 Phase 요약
