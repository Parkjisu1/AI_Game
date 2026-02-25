# C10+ v2.5 분석 보고서: Ash N Veil: Fast Idle Action

> 생성일: 2026-02-24 11:29:17
> 장르: Idle RPG
> 방법론: C10+ v2.5 (Enhanced Observation + OCR + Wiki + Assets)

---

## 결과 요약

| 항목 | 값 |
|------|-----|
| 대상 게임 | Ash N Veil: Fast Idle Action |
| 패키지 | studio.gameberry.anv |
| 장르 모듈 | idle_rpg |
| 분석 세션 | 10/10 |
| 총 스크린샷 | 16 |
| OCR 전처리 | X |
| 커뮤니티 데이터 | X |
| APK 에셋 추출 | X |
| **정확도** | 검토 대기 중 |

> Ground Truth가 제공되지 않아 정확도를 산출할 수 없습니다.
> `report/ash_n_veil_review_template.md`를 게임 팀에 전달하여 검토를 요청하세요.

## 사용된 향상 기능

| 기능 | 상태 | 효과 |
|------|:----:|------|
| v2 미션 재설계 | O | 장르 특화 10개 미션 (Idle RPG) |
| M2: OCR 전처리 | X | 수치 데이터 정밀도 향상 |
| M3: 커뮤니티 데이터 | X | 공개 데이터 교차검증 |
| M4: APK 에셋 추출 | X | 설정 데이터 직접 확인 |

## 10명 AI 테스터 역할

| # | 역할 | 도메인 | 장르 특화 |
|---|------|--------|:---------:|
| 1 | Full Playthrough A | gameplay | Core |
| 2 | Full Playthrough B | gameplay | Core |
| 3 | Numeric Early (Lv.1~15) | numeric | Flex |
| 4 | Numeric Late (Lv.30+) | numeric | Flex |
| 5 | Visual + Multi-Resolution | visual | Core |
| 6 | Equipment & Enhancement | equipment | Flex |
| 7 | Economy & Idle Rewards | economy | Flex |
| 8 | Gacha & Pet System | gacha | Flex |
| 9 | Skills & Combat Algorithm | combat | Flex |
| 10 | Cross-Validation | cross_validation | Core |

## 파일 구조

```
output/ash_n_veil/
├── sessions/          16 screenshots across 10 sessions
├── ocr_data/          OCR extraction results
├── observations/      10 specialist analysis texts
├── wiki_data/         Community cross-reference data
├── asset_data/        APK extracted configs
├── aggregated/        Domain-weighted consensus
├── specs/             32-parameter estimation
├── scoring/           Ground truth comparison
├── ground_truth/      Team-provided actual values
└── report/            This report + review template
```

## 실험 환경

| 항목 | 내용 |
|------|------|
| AI 모델 | Claude sonnet |
| 장르 모듈 | idle_rpg (Idle RPG) |
| 세션 전략 | 전문 미션 10종 (Core 4 + Flex 6) |
| 분석일 | 2026-02-24 |
