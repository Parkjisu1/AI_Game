---
description: 게임 기획 워크플로우 실행 (Stage 0~8 파이프라인)
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

# Stage 2: 기획 생성 — Design Workflow Stage 0~8 중 Stage 2

$concept 을 기반으로 $genre 장르의 $project 게임 기획을 생성합니다.

> **파이프라인 위치**: 이 커맨드는 Design Workflow Stage 0~8 중 **Stage 2 (기획 생성)** 를 실행합니다.
> 전체 흐름: Stage 0(설계 표준) → Stage 1(DB 가공) → **Stage 2(기획 생성)** → Stage 3(통합 검증) → Stage 4(디렉터 검수)
> → Stage 5(재생성 평가) → Stage 6(DB 축적) → Stage 7(플레이 검증) → Stage 8(라이브 동기화)

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
    ├── bm\                      # 비즈니스 모델 설계
    └── liveops\                 # 라이브 운영 설계
```

## Stage 2 기획 생성 (Sub-steps 2-1 ~ 2-5 + 후처리)

### Step 2-1: 컨셉 정의
- 핵심 게임플레이 메카닉 추출
- 장르별 필수 시스템 목록화
- 레퍼런스 게임 패턴 참조 (Design DB 검색)
- 디자인 필러(3~5개), 핵심 루프, 타겟 유저 프로파일
- 출력: `designs/game_design.yaml` (game_overview, core_experience, core_loop)

### Step 2-2: 시스템 기획
각 도메인별 핵심 시스템 정의:
```
InGame:   전투/스킬/스테이지/캐릭터
OutGame:  인벤토리/상점/아이템/장비
Balance:  성장 공식/스탯 체계
Content:  퀘스트/스테이지/보상
BM:       결제/가챠/패스
LiveOps:  이벤트/시즌/업데이트 주기
UX:       UI 흐름/이펙트/오디오
```
출력: `design_workflow/systems/*.yaml`

### Step 2-3: 밸런스 기획
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

> **병렬 가능**: Step 2-3과 2-4는 Step 2-2 완료 후 동시 진행 가능

### Step 2-4: 콘텐츠 기획
- 스테이지 구성 (챕터/단계/보스 주기)
- 퀘스트/미션 체계
- 보상 테이블
- 출력: `design_workflow/content/*.yaml`

### Step 2-5: BM/LiveOps 기획
- 가챠 구조 (확률/천장/비용)
- 패스/시즌패스 설계
- IAP 상품 목록
- 광고 배치
- 이벤트 캘린더, 시즌 구조, 업데이트 주기
- 출력: `design_workflow/bm/*.yaml`, `design_workflow/liveops/*.yaml`

> **의존성**: Step 2-5는 Step 2-3(밸런스) 완료 후 시작 (경제 수치 참조 필요)

---

### Post-step A: 통합 정합성 검사
교차 검증:
- 인게임 경제 ↔ 콘텐츠 소비 속도 일치 여부
- 밸런스 곡선 ↔ BM 구매 시점 연계 검증
- 일일 세션 시간 ↔ 콘텐츠 소비량 정합

### Post-step B: 코드 파이프라인 변환
```bash
node E:/AI/scripts/design-to-code-bridge.js \
  --project $project \
  --input E:/AI/projects/$project/designs/design_workflow \
  --output E:/AI/projects/$project/designs
```
출력: `system_spec.yaml` + `nodes/*.yaml`

### Post-step C: Design DB 저장
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
