# 퍼즐 게임 공용 Raw Data 스키마 명세서

> **목적**: 밸런스 기획을 위한 이벤트 단위 유저 행동 로그 정의
> **원칙**: 유저 플레이 1판 = 1행. 레벨별 집계(Metadata)는 이 raw data에서 파생

---

## 0. item_master — 게임별 아이템 정의

게임마다 아이템 이름이 다르므로, ID로만 기록하고 이 테이블에서 "그게 뭔지" 매핑합니다.

| 필드명 | 타입 | 설명 |
|---|---|---|
| game_id | VARCHAR | 게임 식별자 (예: sort_puzzle, match3) |
| item_id | VARCHAR | 아이템 고유 ID (예: SP_001) |
| item_name | VARCHAR | 사람이 읽을 이름 (예: 빈 튜브) |
| item_category | VARCHAR | 공용 카테고리 (아래 참고) |
| item_description | VARCHAR | 설명 |

**item_category 공용 분류:**
| 카테고리 | 의미 | 예시 (소트 퍼즐) | 예시 (매치3) |
|---|---|---|---|
| pre_play_item | 판 시작 전 장착/사용 | 빈 튜브 | 레인보우 볼 |
| in_play_item | 판 진행 중 사용 | 셔플, 되돌리기 | 해머, 폭탄 |
| continue_item | 이어하기 관련 | - | +5 무브 |
| currency | 재화 | 코인 | 코인 |
| consumable | 기타 소모품 | 라이프 | 라이프 |

---

## 1. level_play_event — 핵심 테이블 (한 판 = 한 행)

유저가 레벨을 시작해서 끝날 때마다 1건 기록됩니다.

### 식별 & 환경

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| event_id | VARCHAR | 이벤트 고유 ID (UUID) | PK |
| session_id | VARCHAR | 앱 세션 ID | 같은 세션 내 여러 판 묶기 |
| game_id | VARCHAR | 게임 식별자 | 멀티 게임 구분 |
| UID | VARCHAR | 유저 고유 ID | 유저 추적 |
| event_timestamp | DATETIME | 이벤트 발생 시각 (UTC) | 시계열 분석 |
| app_version | VARCHAR | 앱 버전 | 버전별 비교 |
| install_version | VARCHAR | 최초 설치 버전 | 신규/기존 유저 구분 |
| country | VARCHAR | 국가 코드 | 지역별 분석 |
| platform | VARCHAR | iOS / AOS | 기기별 분석 |
| device_model | VARCHAR | 기기 모델 | 성능 이슈 추적 |

### 레벨 정보

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| level_number | INT | 유저에게 노출되는 순서 | 난이도 곡선 추적 |
| level_id | VARCHAR | 시스템 고유 맵 ID | A/B 테스트 시 같은 level_number에 다른 맵 구분 |
| is_tutorial | BOOLEAN | 튜토리얼 여부 | 튜토리얼 스킵 유저 필터링 |
| hard_tier | INT | 난이도 등급 (0:일반 / 1:어려움 / 2:매우 어려움) | 의도된 허들 구분 |

### 시도 컨텍스트

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| attempt_number | INT | 이 레벨에서 몇 번째 시도 (1부터) | 3회차 클리어 집중이면 적절, 10회 이상이면 병목 |
| is_first_play | BOOLEAN | 해당 레벨 최초 플레이 여부 | 퍼널 분석 시 첫 시도만 필터 |

### 플레이 결과

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| result | VARCHAR | 'clear' / 'fail' / 'cancel' | 성공률 계산 |
| fail_reason | VARCHAR | 'deadlock' / 'timeout' / 'manual_quit' / 'out_of_moves' / null | 실패 유형별 레벨 문제 진단 |

### 무브 — 공용

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| moves_used | INT | 유저가 실제로 한 총 조작 횟수 | 모든 퍼즐 게임의 난이도 핵심 지표 |

### 무브 — 무브 제한 게임용 (매치3 등)

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| moves_given | INT | 주어진 총 무브 수 (제한 없으면 null) | 밸런스 기준선 |
| moves_remaining | INT | 클리어 시 남은 무브 (제한 없으면 null) | 항상 높으면 너무 쉬움, 0 실패 집중이면 빠듯함 |

### 무브 — 자유 조작 게임용 (소트 퍼즐 등)

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| undo_count | INT | 되돌리기 횟수 | 높으면 풀이 경로가 직관적이지 않다는 신호 |
| deadlock_count | INT | 막힘(유효 수 없음) 발생 횟수 | 맵 설계 결함 감지 |

### 목표 달성

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| objective_total | INT | 목표 수량 (예: 젤리 10개) | 기준선 |
| objective_done | INT | 실제 달성 수량 | 8/10 = 아쉬운 실패(재도전 유도), 3/10 = 희망 없는 실패(이탈 위험) |

### 시간 & 점수

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| play_time_sec | INT | 이번 판 소요 시간 (초) | 체류 시간, 너무 짧으면 포기 / 너무 길면 지루 |
| score | INT | 획득 점수 | 점수 분포 분석 |
| star_count | INT | 획득 별 수 (0~3) | 클리어 품질 지표 |

### 아이템 사용

| 필드명 | 타입 | 설명 | 예시 |
|---|---|---|---|
| pre_play_item_ids | VARCHAR (JSON) | 시작 전 사용 아이템 ID 목록 | '["SP_001"]' |
| pre_play_item_count | INT | 시작 전 사용 아이템 수 | 1 |
| in_play_item_ids | VARCHAR (JSON) | 판 중 사용 아이템 ID 목록 | '["SP_003","SP_003"]' |
| in_play_item_count | INT | 판 중 사용 아이템 수 | 2 |

### 컨티뉴 & 경제

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| continue_count | INT | 이어하기 사용 횟수 | 재도전 욕구 지표 |
| continue_cost_total | INT | 이어하기에 소비한 재화 | 재화 싱크 추적 |
| coin_earned | INT | 이번 판 획득 코인 | 인플레이션 모니터링 |
| coin_spent | INT | 이번 판 소비 코인 | 싱크 밸런스 |

### 보조 기능

| 필드명 | 타입 | 설명 | 활용 |
|---|---|---|---|
| shuffle_count | INT | 셔플 사용 횟수 | 막힘 빈도 간접 지표 |
| hint_count | INT | 힌트 사용 횟수 | 난이도 체감 간접 지표 |

---

## 2. item_use_event — 아이템 개별 사용 상세

level_play_event의 JSON 필드를 개별 행으로 풀어서 아이템별 세부 분석에 사용합니다.

| 필드명 | 타입 | 설명 |
|---|---|---|
| event_id | VARCHAR | 이벤트 고유 ID |
| play_event_id | VARCHAR | FK → level_play_event |
| game_id | VARCHAR | 게임 식별자 |
| UID | VARCHAR | 유저 ID |
| event_timestamp | DATETIME | 사용 시각 |
| level_number | INT | 레벨 번호 |
| level_id | VARCHAR | 맵 ID |
| item_id | VARCHAR | 사용한 아이템 ID → item_master 참조 |
| item_category | VARCHAR | pre_play_item / in_play_item / continue_item |
| acquisition_type | VARCHAR | 'free' / 'purchased' / 'reward' |
| cost_amount | INT | 소비된 재화 양 (0이면 무료) |
| cost_currency_id | VARCHAR | 어떤 재화로 구매했는지 |

---

## 3. purchase_event — 인앱 구매

| 필드명 | 타입 | 설명 |
|---|---|---|
| event_id | VARCHAR | 이벤트 고유 ID |
| game_id | VARCHAR | 게임 식별자 |
| UID | VARCHAR | 유저 ID |
| event_timestamp | DATETIME | 구매 시각 |
| app_version | VARCHAR | 앱 버전 |
| country | VARCHAR | 국가 |
| platform | VARCHAR | OS |
| product_id | VARCHAR | 스토어 상품 ID |
| product_name | VARCHAR | 상품명 |
| product_type | VARCHAR | 'coin_pack' / 'item_pack' / 'lives' / 'subscription' / 'starter_pack' |
| price_usd | DECIMAL | USD 환산 금액 |
| price_local | DECIMAL | 현지 통화 금액 |
| currency_code | VARCHAR | 통화 코드 (KRW, USD 등) |
| trigger_point | VARCHAR | 구매 트리거 위치 (어디서 결제가 터졌는지) |
| level_number | INT | 구매 시점 레벨 |
| coin_granted | INT | 지급된 코인 |
| items_granted | VARCHAR (JSON) | 지급된 아이템 목록 |
| lives_granted | INT | 지급된 라이프 |
| receipt_id | VARCHAR | 영수증 ID |
| is_verified | BOOLEAN | 서버 영수증 검증 여부 |

---

## 4. economy_event — 재화 변동 원장

모든 재화 획득/소비를 기록하는 원장. 소스-싱크 밸런스 분석의 원본입니다.

| 필드명 | 타입 | 설명 |
|---|---|---|
| event_id | VARCHAR | 이벤트 고유 ID |
| game_id | VARCHAR | 게임 식별자 |
| UID | VARCHAR | 유저 ID |
| event_timestamp | DATETIME | 변동 시각 |
| currency_type | VARCHAR | 재화 종류 (item_master의 currency 참조) |
| change_amount | INT | 양수: 획득, 음수: 소비 |
| balance_after | INT | 변동 후 잔액 |
| source | VARCHAR | 변동 원인 (level_clear / daily_reward / iap / ad_reward 등) |
| ref_event_id | VARCHAR | 관련 이벤트 ID (조인용) |
| level_number | INT | 레벨 관련 변동일 경우 |

---

## 5. session_event — 앱 세션

| 필드명 | 타입 | 설명 |
|---|---|---|
| session_id | VARCHAR | 세션 고유 ID |
| game_id | VARCHAR | 게임 식별자 |
| UID | VARCHAR | 유저 ID |
| session_start | DATETIME | 세션 시작 |
| session_end | DATETIME | 세션 종료 |
| duration_sec | INT | 세션 길이 (초) |
| app_version | VARCHAR | 앱 버전 |
| country | VARCHAR | 국가 |
| platform | VARCHAR | OS |
| device_model | VARCHAR | 기기 모델 |
| levels_played | INT | 이 세션에서 플레이한 판 수 |
| levels_cleared | INT | 이 세션에서 클리어한 판 수 |

---

## 6. ad_event — 광고 시청

| 필드명 | 타입 | 설명 |
|---|---|---|
| event_id | VARCHAR | 이벤트 고유 ID |
| game_id | VARCHAR | 게임 식별자 |
| UID | VARCHAR | 유저 ID |
| event_timestamp | DATETIME | 시청 시각 |
| ad_type | VARCHAR | 'rewarded' / 'interstitial' |
| ad_placement | VARCHAR | 광고 노출 위치 |
| result | VARCHAR | 'completed' / 'skipped' / 'error' |
| reward_type | VARCHAR | 보상 종류 |
| reward_amount | INT | 보상 수량 |
| level_number | INT | 시청 시점 레벨 |

---

## 7. user_property — 유저 일별 스냅샷

| 필드명 | 타입 | 설명 |
|---|---|---|
| game_id | VARCHAR | 게임 식별자 |
| UID | VARCHAR | 유저 ID |
| snapshot_date | DATE | 스냅샷 날짜 |
| install_date | DATE | 설치일 |
| install_version | VARCHAR | 최초 설치 버전 |
| country | VARCHAR | 국가 |
| platform | VARCHAR | OS |
| device_model | VARCHAR | 기기 모델 |
| current_level | INT | 현재 도달 레벨 |
| total_play_count | INT | 누적 플레이 수 |
| total_clear_count | INT | 누적 클리어 수 |
| total_coin_balance | INT | 현재 코인 잔액 |
| total_spend_usd | DECIMAL | 누적 결제 금액 |
| is_payer | BOOLEAN | 결제 유저 여부 |
| days_since_install | INT | 설치 후 경과일 |
| last_active_date | DATE | 마지막 활동일 |
