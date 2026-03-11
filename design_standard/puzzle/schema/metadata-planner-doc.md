# 퍼즐 게임 공용 Metadata 스키마 명세서

> **목적**: Raw Data(level_play_event 등)를 레벨 단위로 집계하여 밸런스 대시보드에서 사용
> **갱신 주기**: 일배치(daily) 권장
> **관계**: Raw Data → GROUP BY level_id, stat_date → Metadata

---

## 1. level_meta — 레벨 설계 정보 (기획자 입력)

유저 행동 데이터가 아니라 **맵 자체의 속성**입니다. 기획자가 직접 관리합니다.

| 필드명 | 타입 | 설명 | 밸런스 활용 |
|---|---|---|---|
| game_id | VARCHAR | 게임 식별자 | |
| level_id | VARCHAR | 맵 고유 ID | A/B 테스트 시 같은 레벨 번호에 다른 맵 구분 |
| level_number | INT | 유저 노출 순서 | 난이도 곡선의 X축 |
| hard_tier | INT | 난이도 등급 (0/1/2) | 의도된 허들 표시 |
| is_tutorial | BOOLEAN | 튜토리얼 여부 | 필터링 |
| optimal_moves | INT | 최소 풀이 무브 수 | moves_used / optimal_moves = 효율 비율 |
| objective_type | VARCHAR | 목표 유형 | 목표 유형별 난이도 패턴 비교 |
| objective_target | INT | 목표 수량 | |
| moves_limit | INT | 무브 제한 (없으면 null) | |
| time_limit_sec | INT | 시간 제한 (없으면 null) | |
| num_colors | INT | 색상/요소 종류 수 | 복잡도 지표 |
| num_containers | INT | 튜브/보드 칸 수 | |
| num_empty_slots | INT | 빈 슬롯 수 (소트 퍼즐) | 여유 공간 → 난이도 결정 요소 |
| special_mechanics | VARCHAR (JSON) | 특수 기믹 목록 | 기믹 조합별 난이도 영향 분석 |
| designer_note | VARCHAR | 기획 의도 메모 | 의도 vs 실제 결과 비교 |

---

## 2. level_balance_daily — 핵심 밸런스 지표 (일간)

대시보드의 메인 테이블. 레벨별로 매일 집계됩니다.

### 퍼널 & 볼륨

| 필드명 | 설명 | 보는 법 |
|---|---|---|
| play_user_count | 플레이한 유저 수 (UV) | 퍼널 어디서 막히는지 |
| play_count | 총 시도 횟수 | play_count / play_user_count = 유저당 평균 시도 |
| clear_count | 클리어 횟수 | |
| fail_count | 실패 횟수 | |
| cancel_count | 취소 횟수 | 높으면 지루함/좌절 신호 |

### 핵심 비율 — 밸런스 판단의 1순위

| 필드명 | 설명 | 보는 법 |
|---|---|---|
| clear_rate | 클리어율 (clear / play) | **가장 중요한 지표.** Normal 목표: 70~85%, Hard: 40~60% (게임마다 다름) |
| first_try_clear_rate | 첫 시도 클리어율 | 너무 높으면 쉬움, 너무 낮으면 첫인상이 벽 |
| cancel_rate | 취소율 | 높은 레벨 = 피로도 지표 |

### 시도 횟수 분포 — 병목 감지

| 필드명 | 설명 | 보는 법 |
|---|---|---|
| avg_attempts_to_clear | 클리어까지 평균 시도 수 | Normal 기대치: 1~3회 |
| median_attempts_to_clear | 클리어까지 중앙값 시도 수 | 평균보다 안정적인 지표 |
| p90_attempts_to_clear | 상위 10% 유저 시도 수 | 이 값이 10+이면 심각한 병목 |

### 실패 유형 분석 — 왜 실패하는지

| 필드명 | 설명 | 보는 법 |
|---|---|---|
| fail_deadlock_count | 데드락 실패 수 | 많으면 맵 구조 결함 (소트 퍼즐 핵심) |
| fail_timeout_count | 시간 초과 실패 수 | 타임 리밋 밸런스 |
| fail_out_of_moves_count | 무브 소진 실패 수 | 무브 제한 밸런스 (매치3) |
| fail_manual_quit_count | 수동 포기 수 | 많으면 "해봐야 안 된다"고 느끼는 것 |

### 무브 지표 — 난이도 체감의 핵심

| 필드명 | 설명 | 보는 법 |
|---|---|---|
| avg_moves_used | 전체 평균 조작 수 | |
| avg_moves_clear | 클리어 시 평균 조작 수 | optimal_moves 대비 비율로 효율 판단 |
| avg_moves_fail | 실패 시 평균 조작 수 | clear보다 훨씬 높으면 헤매다 실패 |
| median_moves_clear | 클리어 조작 수 중앙값 | |
| p90_moves_clear | 상위 10% 조작 수 | 하위 유저가 얼마나 헤매는지 |
| avg_moves_remaining | 클리어 시 남은 무브 (무브 제한 게임) | 항상 높으면 쉬움, 항상 0이면 빠듯함 |
| avg_undo_count | 평균 되돌리기 횟수 (자유 조작 게임) | 높으면 풀이 경로 불명확 |
| avg_deadlock_count | 평균 데드락 횟수 (자유 조작 게임) | 높으면 맵 설계 문제 |
| undo_usage_rate | undo 1회+ 사용 판 비율 | |

### 목표 달성도 — "아깝게 실패" vs "희망 없는 실패"

| 필드명 | 설명 | 보는 법 |
|---|---|---|
| avg_objective_completion_on_fail | 실패 시 평균 목표 달성률 | 60~80%면 적절 (아쉬워서 재도전) |
| near_miss_rate | 목표 80%+ 달성 후 실패 비율 | **높을수록 좋음.** 재도전 욕구 자극 |
| hopeless_fail_rate | 목표 30% 미만 달성 후 실패 비율 | **낮을수록 좋음.** 높으면 이탈 위험 |

### 시간 & 점수

| 필드명 | 설명 | 보는 법 |
|---|---|---|
| avg_play_time_sec | 전체 평균 플레이 시간 | |
| avg_clear_time_sec | 클리어 평균 시간 | 너무 길면 지루, 너무 짧으면 허무 |
| median_clear_time_sec | 클리어 시간 중앙값 | |
| avg_fail_time_sec | 실패 평균 시간 | 매우 짧으면 빠른 포기 (= 희망 없음) |
| avg_score | 평균 점수 | |
| avg_star_count | 평균 별 수 | 1에 몰리면 겨우 통과, 3이 많으면 쉬움 |

---

## 3. level_item_daily — 아이템 사용 집계

레벨별로 어떤 아이템이 얼마나 쓰이는지, 효과가 있는지 봅니다.

| 필드명 | 설명 | 보는 법 |
|---|---|---|
| item_id | 아이템 ID → item_master 참조 | |
| item_category | pre_play_item / in_play_item / continue_item | |
| use_count | 총 사용 횟수 | |
| use_user_count | 사용 유저 수 | |
| use_rate | 사용 판 비율 | 특정 레벨에서 급등하면 그 레벨이 어렵다는 신호 |
| clear_rate_with | 이 아이템 사용 시 클리어율 | |
| clear_rate_without | 미사용 시 클리어율 | **with - without 차이 = 아이템 효과.** 차이 없으면 가치 없는 아이템 |
| total_cost | 소비된 총 재화 | 싱크 기여도 |
| free_use_count | 무료 사용 | |
| paid_use_count | 유료 사용 | 유료 비율 높으면 수익 기여 아이템 |

---

## 4. level_economy_daily — 경제 집계

레벨별 재화 흐름과 수익을 봅니다.

| 필드명 | 설명 | 보는 법 |
|---|---|---|
| total_coin_earned | 총 획득 코인 | |
| total_coin_spent | 총 소비 코인 | |
| net_coin_flow | earned - spent | **양수면 소스 > 싱크 (인플레 위험), 음수면 싱크 > 소스** |
| avg_coin_earned | 판당 평균 획득 | |
| avg_coin_spent | 판당 평균 소비 | |
| continue_use_count | 컨티뉴 총 사용 횟수 | |
| continue_use_rate | 컨티뉴 사용 판 비율 | 높은 레벨 = 아쉬운 실패가 많은 것 (좋은 설계) |
| total_continue_cost | 컨티뉴 총 소비 재화 | |
| purchase_count | 이 레벨에서 발생한 구매 건수 | |
| purchase_user_count | 구매 유저 수 | |
| purchase_revenue_usd | 매출 | **레벨별 매출 = monetization 허들 어디 있는지** |
| top_trigger_point | 가장 많은 구매 트리거 | 'level_fail_popup'이 대부분이면 실패 → 결제 구조 |

---

## 5. level_retention_daily — 이탈/체류 지표

레벨별로 유저가 멈추는 곳, 빠지는 곳을 봅니다.

| 필드명 | 설명 | 보는 법 |
|---|---|---|
| reach_user_count | 이 레벨에 도달한 유저 수 | 퍼널 X축 |
| clear_user_count | 클리어한 유저 수 | |
| pass_through_rate | 레벨 통과율 (clear / reach) | **clear_rate와 다름.** 이건 유저 단위, clear_rate는 판 단위 |
| churn_user_count | 이 레벨이 마지막인 유저 수 | |
| churn_rate | 이탈률 | **갑자기 튀는 레벨 = 밸런스 문제 또는 디자인 문제** |
| avg_attempts_before_churn | 이탈 전 평균 시도 수 | 1~2회면 "해볼 가치 없음", 5+회면 "끈질기게 하다 포기" |
| avg_stay_time_sec | 이 레벨 총 체류 시간 | |
| payer_reach_count | 도달 결제 유저 수 | |
| payer_churn_count | 이탈 결제 유저 수 | **결제 유저 이탈은 매출 직결 → 최우선 대응** |

---

## 6. level_ab_test_daily — A/B 테스트 비교

같은 level_number에 다른 맵(level_id)을 배정했을 때, 그룹 간 비교용 테이블입니다.

| 필드명 | 설명 |
|---|---|
| test_group | 'A' / 'B' / 'control' |
| level_id | 각 그룹에 배정된 맵 ID |
| clear_rate | 클리어율 비교 |
| first_try_clear_rate | 첫 시도 클리어율 비교 |
| avg_attempts_to_clear | 클리어까지 시도 수 비교 |
| avg_moves_clear | 클리어 무브 수 비교 |
| cancel_rate | 취소율 비교 |
| churn_rate | 이탈률 비교 |
| near_miss_rate | 아깝게 실패 비율 비교 |
| item_use_rate | 아이템 사용률 비교 |
| purchase_revenue_usd | 매출 비교 |

---

## 📌 대시보드에서 보는 우선순위

### 1순위 — 매일 봐야 할 것
- level_balance_daily의 **clear_rate, cancel_rate, avg_attempts_to_clear**
- level_retention_daily의 **churn_rate, payer_churn_count**

### 2순위 — 주간 리뷰
- **near_miss_rate vs hopeless_fail_rate** 비율 밸런스
- **아이템 사용률 급등 레벨** 확인 (level_item_daily)
- **net_coin_flow** 추세 (인플레 감지)

### 3순위 — 밸런스 조정 시
- level_meta의 **optimal_moves** vs 실제 avg_moves_clear 비교
- **실패 유형 분포** (데드락 vs 무브 부족 vs 수동 포기)
- A/B 테스트 결과 비교
