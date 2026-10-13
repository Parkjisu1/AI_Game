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
├── flow-contract.json           # 대표 신규/역설계 작업의 의도·근거·인수 추적 (적용 시)
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

## 대표 신규/역설계 작업의 준비

대표 제작 구간을 새로 만들거나 레퍼런스를 역설계·재가공하는 작업이면, Step 2-1 전에 `designs/flow-contract.json`을 생성하거나 갱신한다. 기존 소규모 수정에 전체 계약을 강제하지 않는다. 이 파일은 기존 기획 YAML과 별도인 JSON sidecar이며, 아래 연결을 보존한다.

구조 예시는 `scripts/templates/flow-contract.example.json`을 참고한다. 계약 작성용 예시이며 실제 게임 산출물이나 검증된 게임 사례가 아니다. 현재 사용자 요청과 근거에 맞게 작성한다.

| 항목 | 기록할 필드 |
|---|---|
| 최상위 | `version: 1`, `project` (프로젝트 이름) |
| `intent` | `user_request`, `goals[{id, statement}]`, `non_goals`, `constraints`, `assumptions` |
| `references[]` | `id`, `source`, `version` |
| `claims[]` | `id`, `reference_id`, `statement`, `basis`, `verification`, `evidence` |
| `decisions[]` | `id`, `mode`, `goal_ids`, `claim_ids`, `rationale`, `expected_difference` |
| `requirements[]` | `id`, `goal_ids`, `decision_ids`, `statement`, `category`, `delivery_scope`, `acceptance_ids` |
| `work_items[]` | `id`, `discipline`, `requirement_ids`, `deliverable`, `node_ids` |
| `acceptance[]` | `id`, `kind`, `scope`, `method`, `expected`, `status`, `evidence`, `input_artifacts`, `basis_hash` |

- 사용자 원문과 목표에서 시작해 레퍼런스 주장 → 의도된 차이 → 요구사항 → 해당 직군의 작업·산출물 → 관측 가능한 인수로 ID를 연결한다. DB 검색은 기존 규칙대로 수행하되, 적중한 패턴이 사용자 의도에 맞지 않으면 제외 사유를 남긴다.
- `basis`는 `observed|inferred|designed|unknown`, `verification`은 `untested|reproduced|contradicted`로 분리한다. `mode`는 `keep|adapt|replace|omit|new`이며, 원본과 다른 행동은 그 이유와 기대 차이를 기록한다. 관찰이 원작의 성공 원인을 증명하지는 않는다.
- 모르는 값은 가정·미확인으로 남기고 기존 승인 범위 안에서 준비 작업을 진행한다. 사용자 승인이나 실제 검증 결과를 발명하지 않고 매 단계 재확인하지 않는다. 중단은 저장소의 세 조건에 해당할 때만 한다.
- `placeholder_functional`과 `production_experience` 범위를 구분한다. 기술·행동·아트·경험·시장 판정을 분리하고, 실행하지 않은 인수를 통과로 기록하지 않는다. `input_artifacts`와 `basis_hash`는 검증에 사용한 버전과 근거를 추적하며, 관련 변경 시 해당 인수만 재검증한다.
- `requirements[].category`와 CLI `--scope`는 `technical|behavior|art|experience|market` 중 하나다. 별도로 `requirements[].delivery_scope`와 연결된 `acceptance[].scope`는 `placeholder_functional|production_experience` 중 같은 값이어야 한다. `acceptance[].kind`는 `parity|delta|runtime|art|experience|market|structure`이며 요구사항의 분야에 맞는 검증을 선택한다.
- `evidence[]`에는 `locator`, `kind`를 기록하고 실제 인수에는 로컬 파일의 `sha256`도 필요하다. `input_artifacts[]`는 `locator`, `sha256`으로 평가한 입력을 고정한다. 상대 `locator`의 기준은 계약 JSON이 있는 폴더이며, 원격 자료는 인수 전에 로컬 증거로 보존한다.
- handoff 결과의 `acceptance_basis[id]`는 현재 인수 기준 해시다. 해당 기준·입력으로 실제 검증한 뒤 결과와 함께 `acceptance[].basis_hash`에 기록한다. 기준 변경 후 해시만 교체해 이전 통과를 재사용하지 않는다. 관련 작업 산출물 변경은 해당 인수를, 공통 의도·제약·가정 변경은 보수적으로 모든 인수를 다시 확인한다. 선택한 인수의 `not_applicable`은 통과가 아니며 범위 제외가 필요하면 요구사항과 그 근거를 먼저 정정한다.

실제 기획/코드 handoff 전 Design Validator가 실행한다:

```text
node scripts/validate-flow-contract.js --input projects/$project/designs/flow-contract.json --stage handoff
```

handoff PASS는 참조·기록 구조 검사이며 실제 동작·재미·시장성 인수가 아니다. 실제 실행 증거를 확보한 뒤 `--stage acceptance --scope technical`로 해당 범위를 검사한다(`behavior`, `art`, `experience`, `market`도 개별 선택 가능). 실패 항목을 고치고 전달하며, 검사를 우회하려고 적용한 계약을 제거하지 않는다.

VP 관측을 비교할 때는 계약에 `virtual_player.criteria: [{id, metric, requirement_ids, acceptance_ids, min?, max?, expected_hooks?, point?}]`를 기록한다. 연결된 acceptance가 해당 requirement에 속하는지도 VP bridge에서 검사한다.
`metric`은 `session_length`(초), `action_frequency`(분당 행동), `action_variety`(입력 score/count), `engagement_hooks`, `failure_rate`(0~1) 중 하나다. 수치는 명시한 `min`/`max` 중 하나 이상으로 비교하며, hooks는 `expected_hooks` 배열, 실패율은 `point`도 필요하다. 0과 빈 hook 요구 배열은 유효하다.
기준 누락은 `missing_definition`, 측정 누락·null·유효하지 않은 값은 `missing_evidence`로 구분한다. 기존 입력의 `target_length`는 `tolerance_seconds` 또는 `tolerance_ratio`가 있어야 범위를 판정한다.

```text
node scripts/virtual-player-bridge.js --input projects/$project/feedback/vp-export.yaml --project $project --flow-contract projects/$project/designs/flow-contract.json --output projects/$project/feedback/design/vp_feedback.json
```

결과의 `within_declared_range`는 명시 지표 범위 안이라는 뜻이며 재미·시장 인수 PASS가 아니다. 원본 입력과 SHA는 출력 JSON에 보존한다. 관련 criteria가 바뀌면 연결된 acceptance 기준 해시가 달라지므로 해당 인수를 재검증하고, 이전 증거에 새 해시만 붙이지 않는다.

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
- 데이터 스키마 로드 (0단계 설계 표준에서 해당 콘텐츠의 데이터 구조 참조)
  - 스키마 미정의 시 디렉터+프로그래머 싱크 요청 (0단계로 되돌림)
- 스테이지 구성 (챕터/단계/보스 주기)
- 퀘스트/미션 체계
- 보상 테이블
- 데이터 스키마에 맞춰 실제 JSON/YAML 데이터 생성 (바로 사용 가능한 형태)
- 생성된 데이터의 스키마 유효성 자동 검증 (enum/필수필드/값 범위)
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

위 대표 신규/역설계 계약을 적용한 경우에는 handoff 검사 후 같은 변환 명령에 `--flow-contract E:/AI/projects/$project/designs/flow-contract.json`을 추가하여 계약을 Bridge까지 전달한다. 계약 미적용 기존 작업은 위 명령을 그대로 사용한다. Bridge의 구조 검사나 템플릿 생성 완료를 실제 플레이 인수로 간주하지 않는다.

### Post-step C: Design DB 저장
- 생성된 기획 데이터를 Design DB에 저장
- 재사용 가능한 패턴 추출 및 인덱싱
- 장르별 표준 수치 업데이트

대표 신규/역설계 Flow를 적용한 경우, 위 저장·표준 업데이트에는 근거 상태를 함께 전달한다. 생성·관찰·추론 데이터는 각각의 상태와 출처를 보존하며, 검증하지 않은 수치를 장르 표준이나 Expert의 확정 사실로 자동 승격하지 않는다. DB의 source 라벨은 자료 출처 분류이고 claim의 `basis`/`verification`은 주장 근거와 검증 상태이므로 서로 대체하지 않는다. 저장 또는 Expert 등록 자체를 관측·재현·시장 검증으로 해석하지 않으며, 표준 수치 채택에는 적용 조건과 실제 검증 근거를 별도로 기록한다.

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
