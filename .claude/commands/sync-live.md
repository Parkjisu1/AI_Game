---
description: 라이브 서비스 데이터 동기화 및 버전 관리
arguments:
  - name: project
    description: 프로젝트 이름
    required: true
  - name: version
    description: "버전 번호 (semver, e.g. 1.2.0)"
    required: true
---

# Live Data Sync & Version Management

$project 의 라이브 데이터를 $version 으로 버전 관리하고 Design DB와 동기화합니다.

## 동작 개요

라이브 서비스에서 측정/수집된 실제 데이터를 기획서와 비교하여
Design DB의 수치를 현실 데이터로 보정합니다.

## 실행 단계

### Step 1: 라이브 데이터 읽기
```
입력 경로:
  E:\AI\projects\$project\live_data\
  ├── metrics\        # KPI 측정값 (retention, ARPU, session_length)
  ├── balance\        # 실측 밸런스 데이터 (레벨별 클리어율, 전투 결과)
  └── economy\        # 경제 데이터 (재화 유통량, 구매 패턴)
```

읽기 대상:
- `metrics/*.csv` 또는 `metrics/*.json`
- `balance/stage_clear_rates.csv`
- `economy/currency_flow.json`

### Step 2: 버전 엔트리 생성
```yaml
# E:\AI\projects\$project\designs\versions\$version.yaml

version: "$version"
project: "$project"
created_at: "<ISO8601 타임스탬프>"
source: "live_sync"

live_metrics:
  dau: <측정값 또는 null>
  retention_d1: <측정값>
  retention_d7: <측정값>
  arpu: <측정값>
  avg_session_min: <측정값>

balance_adjustments:
  - parameter: "damage_formula"
    design_value: <기획값>
    live_value: <실측값>
    delta_pct: <변동률>
    action: "update | monitor | alert"

economy_health:
  gold_sink_ratio: <지출/획득 비율>
  premium_currency_velocity: <회전율>
  top_spender_ratio: <상위 5% ARPU 비중>

status: "healthy | warning | critical"
notes: ""
```

### Step 3: Design DB 업데이트
실측 데이터 기반 수치 보정:

```
업데이트 규칙:
  live_value 존재 AND delta_pct < 20%  → accuracy_estimate 유지
  live_value 존재 AND delta_pct 20~50% → accuracy_estimate 재계산
  live_value 존재 AND delta_pct > 50%  → 해당 파라미터 신뢰도 하향 + 경고

신뢰도 점수 업데이트:
  실측 확인된 파라미터: score += 0.1 (최대 1.0)
  실측값과 큰 괴리:     score -= 0.15
```

업데이트 대상:
```
E:\AI\db\design\base\{genre}\{domain}\files\{designId}.json
  → live_value, live_verified_at, accuracy_estimate 필드 업데이트
```

### Step 4: 스냅샷 저장
현재 기획서 상태를 버전 스냅샷으로 보존:

```
E:\AI\projects\$project\designs\snapshots\$version\
├── game_design.yaml     # 기획서 스냅샷
├── system_spec.yaml     # 시스템 명세 스냅샷
└── balance_summary.yaml # 밸런스 요약
```

스냅샷 형식:
```yaml
snapshot_meta:
  version: "$version"
  project: "$project"
  snapshot_at: "<ISO8601>"
  base_design_hash: "<파일 해시>"

changes_from_prev:
  - type: "balance_adjust | system_add | system_remove | bm_change"
    item: ""
    detail: ""

next_version_targets: []
```

## 경보 기준

| 항목 | Warning | Critical |
|------|---------|----------|
| D1 Retention | < 35% | < 25% |
| D7 Retention | < 15% | < 10% |
| Gold sink ratio | < 0.7 | < 0.5 |
| Stage clear rate (목표 스테이지) | < 40% or > 80% | < 25% or > 90% |

Critical 항목 발생 시:
→ 해당 파라미터에 `alert: true` 플래그 설정
→ 재밸런싱 권고 메시지 출력

## 출력
```
E:\AI\projects\$project\designs\versions\$version.yaml
E:\AI\projects\$project\designs\snapshots\$version\
```

- 동기화된 파라미터 수
- 경고/위험 항목 목록
- 권장 조치 사항
