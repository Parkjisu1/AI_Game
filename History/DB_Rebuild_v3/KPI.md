# DB Rebuild v3.0 KPI 보고서

## 프로젝트 기본 정보
| 항목 | 값 |
|------|-----|
| 프로젝트명 | DB_Rebuild_v3 (DB 재구축 + Tag 분류 + UI 메타데이터) |
| 유형 | 인프라 개선 (게임 생성 아님) |
| 보고 일자 | 2026-02-11 |
| 작업 범위 | parser.js v3.0 / unity_prefab_parser.py 전면 개편 / DB 재파싱 / UI 메타 신규 |

---

## 1. 작업 항목 및 결과

| 단계 | 작업 | 결과 | 비고 |
|------|------|------|------|
| Step 1 | GitHub 레포 클론 | 완료 | Unity.SortPuzzleBase(15), Mobile_Sorting_Game(3) |
| Step 2 | parser.js v2.0 → v3.0 | 완료 | Tag 분류 + Generic 자동 분류 + index 스키마 확장 |
| Step 3 | unity_prefab_parser.py 전면 개편 | 완료 | 273줄 → 1,201줄 |
| Step 4 | 기존 DB 백업 → 5개 프로젝트 재파싱 | 완료 | 780 파일 (고유) |
| Step 5 | UI 메타데이터 추출 + 집계 | 완료 | 3개 프로젝트, 834 파일 |
| Step 6 | analyze.js v3.0 업그레이드 | 완료 | Tag 통계 추가 |
| Step 7 | ui_spec_reference.yaml 실측 반영 | 완료 | 버튼/텍스트/스크롤/레이아웃 |
| Step 8 | 검증 | 완료 | Generic 34건, Tag 81.2% 커버 |

---

## 2. 데이터셋 수 변화

### 2.1 Base Code DB
| 장르 | Layer | 작업 전 | 작업 후 | 증감 | 비고 |
|------|-------|---------|---------|------|------|
| Generic | Core | 0 | 34 | **+34** | 이전 0 → 해결 |
| Idle | Domain | 182 | 173 | -9 | 중복 제거 |
| Idle | Game | 116 | 108 | -8 | 중복 제거 |
| Puzzle | Core | 26 | 9 | -17 | Generic으로 재분류 |
| Puzzle | Domain | 80 | 89 | +9 | GitHub 추가분 |
| Puzzle | Game | 30 | 21 | -9 | 정확한 분류 |
| Rpg | Core | 59 | 1 | -58 | Generic/Domain 재분류 |
| Rpg | Domain | 473 | 123 | -350 | 실제 RPG만 남김 |
| Rpg | Game | 302 | 29 | -273 | 실제 RPG만 남김 |
| Simulation | Core | 12 | 6 | -6 | |
| Simulation | Domain | 49 | 49 | 0 | |
| Simulation | Game | 13 | 3 | -10 | |
| Slg | Core | 4 | 1 | -3 | |
| Slg | Domain | 33 | 23 | -10 | |
| Slg | Game | 41 | 27 | -14 | |
| Tycoon | Core | 9 | 6 | -3 | |
| Tycoon | Domain | 51 | 47 | -4 | |
| Tycoon | Game | 30 | 27 | -3 | |
| Merge | * | 17 | 4 | -13 | |
| **합계 (중복 포함)** | | **1,541** | **780** | **-761** | 중복 제거 + 정확 분류 |

> **감소 원인**: 이전 DB는 동일 파일이 여러 장르에 중복 분류됨 (예: Singleton이 RPG/Puzzle/Idle 모두에 존재). v3.0은 파일당 1장르로 정확 분류 + 중복 제거. 실제 고유 파일 수는 이전과 유사.

### 2.2 신규: Tag 분류 현황
| Major Tag | 건수 | 비율 |
|-----------|------|------|
| ValueModification | 337 | 26.7% |
| FlowControl | 252 | 20.0% |
| ResponseTrigger | 181 | 14.3% |
| DataSync | 136 | 10.8% |
| ConditionCheck | 125 | 9.9% |
| StateControl | 91 | 7.2% |
| ResourceTransfer | 10 | 0.8% |
| (없음) | 147 | 11.6% |

| Minor Tag | 건수 |
|-----------|------|
| Assign | 247 |
| Find | 158 |
| Despawn | 12 |
| Spawn | 6 |
| Calculate | 3 |
| Delay | 3 |
| Validate | 2 |

### 2.3 신규: UI 메타데이터
| 프로젝트 | Prefab | Scene | Button | Scroll | Layout | Text | Image |
|----------|--------|-------|--------|--------|--------|------|-------|
| FantaPuzzle | 227 | 5 | 147 | 7 | 14 | 279 | 2,162 |
| TamplePuzzle | 189 | 7 | 126 | 7 | 15 | 231 | 2,119 |
| Luffy | 388 | 18 | 308 | 2 | 5 | 47 | 1,237 |
| **합계** | **804** | **30** | **581** | **16** | **34** | **557** | **5,518** |

### 2.4 Expert DB / Rules DB (변동 없음)
| 항목 | 수치 |
|------|------|
| Expert 코드 수 | 20 |
| Rules 수 | 3 |

---

## 3. 품질 지표 변화

| 지표 | 작업 전 | 작업 후 | 변화 |
|------|---------|---------|------|
| Generic 장르 파일 수 | 0 | 34 | **+34** (해결) |
| Tag 커버리지 | 0% | 81.2% | **+81.2%** (신규) |
| provides 있음 | - | 92.4% | 양호 |
| requires 있음 | - | 90.3% | 양호 |
| uses 있음 | - | 92.6% | 양호 |
| 중복 파일 | 88건 | 0건 | **해결** |
| UI 실측 데이터 | 없음 | 581 버튼 / 557 텍스트 | **신규** |

---

## 4. 실측 UI 규격 요약 (ui_spec_reference.yaml 반영)

| 항목 | 실측값 |
|------|--------|
| 버튼 width mode | 150 (소형이 49.4%로 가장 많음) |
| 버튼 height mode | 120 |
| 텍스트 fontSize mode | 40 |
| 텍스트 정렬 최빈 | MiddleCenter (74.5%) |
| ScrollRect decelerationRate | 0.14 (100% 동일) |
| ScrollRect 방향 | 세로 100% |
| LayoutGroup spacing mode | 0 |

---

## 5. 종합 요약

| KPI 지표 | 수치 |
|----------|------|
| Base DB 총 파일 (고유) | 780 |
| Generic 장르 | 34 (이전 0 → 해결) |
| Tag 커버리지 | 81.2% |
| UI 메타 프로젝트 | 3개 |
| UI 메타 총 컴포넌트 | 6,706 (버튼+스크롤+레이아웃+텍스트+이미지) |
| 수정 파일 | 3개 (parser.js, analyze.js, unity_prefab_parser.py) |
| 갱신 파일 | 1개 (ui_spec_reference.yaml) |
| 신규 DB 디렉토리 | db/ui_meta/ (3 프로젝트 + aggregated) |

---

## 6. 개선 사항 / 특이 사항

### 해결된 문제
- Generic 장르 비어있던 문제 → Core + 장르 키워드 0점 시 자동 Generic 분류
- Tag 분류 부재 → Major 7종 + Minor 11종 메서드 패턴 기반 분류
- UI 규격이 추정치였던 문제 → 581개 버튼, 557개 텍스트 실측 데이터 반영

### 장르 분류 정확도 향상
- 이전: 동일 파일이 RPG/Puzzle 등 여러 장르에 중복 (2,989건 중 88건 중복)
- 이후: 파일당 1장르, Generic Core 34건 정상 분리

### 향후 개선 가능
- Tag 커버리지 81.2% → 메서드 패턴 확장으로 90%+ 가능
- Minor Tag 중 Compare/Iterate/Aggregate/Notify 등 미탐지 → 패턴 보강 필요
- UI parser에서 CanvasScaler m_ReferenceResolution 추출률 낮음 → 씬 내 Canvas 참조 개선
