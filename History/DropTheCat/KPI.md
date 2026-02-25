# DropTheCat KPI 보고서

## 프로젝트 기본 정보
| 항목 | 값 |
|------|-----|
| 프로젝트명 | DropTheCat |
| 장르 | Puzzle |
| 보고 일자 | 2026-02-10 |
| 생성 노드 수 | 26 |

---

## 1. 검증 결과 요약

| 노드명 | 검증 결과 | 피드백 수 | 점수 | 주요 카테고리 |
|--------|----------|----------|------|---------------|
| BoosterManager | pass | 0 | 0.6 | - |
| CatController | pass | 1 | 0.6 | READABLE.FORMATTING |
| ColorMatcher | pass | 0 | 0.6 | - |
| CurrencyManager | pass | 0 | 0.6 | - |
| DropProcessor | pass | 0 | 0.6 | - |
| GameManager | pass | 0 | 0.6 | - |
| GamePage | pass | 0 | 0.6 | - |
| GridManager | pass | 0 | 0.6 | - |
| HoleController | pass | 1 | 0.6 | PATTERN.API_MISMATCH |
| LevelClearPopup | pass | 0 | 0.6 | - |
| LevelDataProvider | pass | 0 | 0.6 | - |
| LevelFailPopup | pass | 2 | 0.6 | PATTERN.API_MISMATCH, LOGIC.WRONG_CALC |
| LevelManager | pass | 0 | 0.6 | - |
| MainPage | pass | 2 | 0.6 | PATTERN.API_MISMATCH, READABLE.COMPLEXITY |
| ObstacleManager | pass | 0 | 0.6 | - |
| ScoreCalculator | pass | 1 | 0.6 | PATTERN.API_MISMATCH |
| ShopPopup | pass | 0 | 0.6 | - |
| SlideProcessor | pass | 0 | 0.6 | - |
| TileController | pass | 0 | 0.6 | - |
| TitlePage | pass | 1 | 0.6 | PATTERN.API_MISMATCH |

## 2. 피드백 횟수

**총 피드백 수**: 8

| 카테고리 | 횟수 | 비율 |
|----------|------|------|
| PATTERN.API_MISMATCH | 5 | 62.5% |
| READABLE.FORMATTING | 1 | 12.5% |
| LOGIC.WRONG_CALC | 1 | 12.5% |
| READABLE.COMPLEXITY | 1 | 12.5% |

---

## 3. 베이스 코드 편입 비율

| 항목 | 수치 |
|------|------|
| 전체 생성 노드 수 | 26 |
| DB 참조 사용 노드 수 | 0 |
| Expert DB 참조 | 0 |
| Base DB 참조 | 0 |
| 순수 생성 (참조 없음) | 26 |
| **베이스 코드 편입 비율** | **0.0%** |

---

## 4. 데이터셋 수

### Base Code DB
| 구분 | 수 |
|------|----|
| generic/core | 0 |
| generic/domain | 0 |
| generic/game | 0 |
| idle/core | 14 |
| idle/domain | 182 |
| idle/game | 116 |
| merge/core | 0 |
| merge/domain | 11 |
| merge/game | 6 |
| playable/core | 0 |
| playable/domain | 0 |
| playable/game | 0 |
| puzzle/core | 26 |
| puzzle/domain | 80 |
| puzzle/game | 30 |
| rpg/core | 59 |
| rpg/domain | 473 |
| rpg/game | 302 |
| simulation/core | 12 |
| simulation/domain | 49 |
| simulation/game | 13 |
| slg/core | 4 |
| slg/domain | 33 |
| slg/game | 41 |
| tycoon/core | 9 |
| tycoon/domain | 51 |
| tycoon/game | 30 |
| **합계** | **1541** |

### Expert DB
| 항목 | 수치 |
|------|------|
| Expert 코드 수 | 20 |
| 승격률 | 100.0% |

### Rules DB
| 항목 | 수치 |
|------|------|
| Rules 수 | 8 |

---

## 5. 신뢰도 점수 분포

| 점수 구간 | Base DB | Expert DB |
|-----------|---------|----------|
| 0.0-0.3 | 0 | 0 |
| 0.4-0.5 | 1541 | 0 |
| 0.6-0.7 | 0 | 20 |
| 0.8-1.0 | 0 | 0 |

### Role별 생성 코드 수
| Role | 수 |
|------|----|
| Manager | 9 |
| View | 6 |
| Controller | 3 |
| Component | 3 |
| Processor | 2 |
| Provider | 1 |
| Pool | 1 |
| Calculator | 1 |

---

## 6. UX 연출 항목

UX 노드 없음

---

## 7. 종합 요약

| KPI 지표 | 수치 |
|----------|------|
| 총 피드백 횟수 | 8 |
| 베이스 코드 편입 비율 | 0.0% |
| 데이터셋 총 수 (Base) | 1541 |
| 데이터셋 총 수 (Expert) | 20 |
| Expert 승격률 | 100.0% |
| UX 노드 수 | 0 |

---

## 8. 개선 사항 / 특이 사항

### 반복 발생 이슈
- PATTERN.API_MISMATCH: 5회
- READABLE.FORMATTING: 1회
- LOGIC.WRONG_CALC: 1회

### 다음 프로젝트 적용 사항
- (자동 생성 완료 후 수동 작성)
