# VeilBreaker KPI 보고서

## 프로젝트 기본 정보
| 항목 | 값 |
|------|-----|
| 프로젝트명 | VeilBreaker |
| 장르 | Idle |
| 보고 일자 | 2026-02-24 |
| 생성 노드 수 | 41 |

---

## 1. 검증 결과 요약

| 노드명 | 검증 결과 | 피드백 수 | 점수 | 주요 카테고리 |
|--------|----------|----------|------|---------------|
| CharacterManager | pass | 1 | 0.6 | PATTERN.STRUCTURE |
| DataManager | pass | 1 | 0.6 | PATTERN.STRUCTURE |
| SceneBuilder | pass | 1 | 0.6 | PATTERN.STRUCTURE |
| AdMobManager | pass | 1 | 0.6 | PATTERN.STRUCTURE |
| FirebaseManager | pass | 1 | 0.6 | PATTERN.STRUCTURE |
| IAPManager | pass | 0 | 0.6 | - |

## 2. 피드백 횟수

**총 피드백 수**: 5

| 카테고리 | 횟수 | 비율 |
|----------|------|------|
| PATTERN.STRUCTURE | 5 | 100.0% |

---

## 3. 베이스 코드 편입 비율

| 항목 | 수치 |
|------|------|
| 전체 생성 노드 수 | 41 |
| DB 참조 사용 노드 수 | 0 |
| Expert DB 참조 | 0 |
| Base DB 참조 | 0 |
| 순수 생성 (참조 없음) | 41 |
| **베이스 코드 편입 비율** | **0.0%** |

---

## 4. 데이터셋 수

### Base Code DB
| 구분 | 수 |
|------|----|
| generic/core | 50 |
| generic/domain | 0 |
| generic/game | 0 |
| idle/core | 1 |
| idle/domain | 173 |
| idle/game | 108 |
| merge/core | 0 |
| merge/domain | 6 |
| merge/game | 1 |
| playable/core | 0 |
| playable/domain | 79 |
| playable/game | 4 |
| puzzle/core | 9 |
| puzzle/domain | 90 |
| puzzle/game | 21 |
| rpg/core | 6 |
| rpg/domain | 154 |
| rpg/game | 29 |
| simulation/core | 7 |
| simulation/domain | 62 |
| simulation/game | 4 |
| slg/core | 1 |
| slg/domain | 34 |
| slg/game | 27 |
| tycoon/core | 8 |
| tycoon/domain | 56 |
| tycoon/game | 28 |
| **합계** | **958** |

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
| 0.4-0.5 | 958 | 0 |
| 0.6-0.7 | 0 | 20 |
| 0.8-1.0 | 0 | 0 |

### Role별 생성 코드 수
| Role | 수 |
|------|----|
| Component | 20 |
| Manager | 17 |
| Calculator | 1 |
| Pool | 1 |
| Config | 1 |
| Helper | 1 |

---

## 6. UX 연출 항목

UX 노드 없음

---

## 7. 종합 요약

| KPI 지표 | 수치 |
|----------|------|
| 총 피드백 횟수 | 5 |
| 베이스 코드 편입 비율 | 0.0% |
| 데이터셋 총 수 (Base) | 958 |
| 데이터셋 총 수 (Expert) | 20 |
| Expert 승격률 | 100.0% |
| UX 노드 수 | 0 |

---

## 8. 개선 사항 / 특이 사항

### 반복 발생 이슈
- PATTERN.STRUCTURE: 5회

### 다음 프로젝트 적용 사항
- (자동 생성 완료 후 수동 작성)
