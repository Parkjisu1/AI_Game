-- ============================================================
-- 퍼즐 게임 공용 Metadata Schema
-- 목적: raw data(level_play_event 등)를 레벨 단위로 집계하여
--       밸런스 대시보드에서 사용하는 지표 테이블
-- 원본: level_play_event + item_use_event + purchase_event + economy_event
-- 갱신 주기: 일배치 (daily) 또는 준실시간
-- ============================================================


-- ============================================================
-- 1. level_meta  (레벨 정의 — 맵 자체의 속성)
--    기획자가 직접 관리하는 레벨 설계 정보
--    raw data가 아닌 기획 입력값
-- ============================================================
CREATE TABLE level_meta (
    game_id             VARCHAR     NOT NULL,
    level_id            VARCHAR     NOT NULL,
    level_number        INT         NOT NULL,

    hard_tier           INT,                    -- 0: Normal / 1: Hard / 2: Super Hard
    is_tutorial         BOOLEAN     DEFAULT FALSE,

    -- ── 맵 설계 속성 ──
    optimal_moves       INT,                    -- 최소 풀이 무브 (시뮬레이션 or 수동 측정)
    objective_type      VARCHAR,                -- 'sort_color' / 'clear_jelly' / 'collect_item' 등
    objective_target    INT,                    -- 목표 수량
    moves_limit         INT,                    -- 무브 제한 (없으면 null)
    time_limit_sec      INT,                    -- 시간 제한 (없으면 null)

    -- ── 맵 구성 요소 ──
    num_colors          INT,                    -- 색상/요소 종류 수
    num_containers      INT,                    -- 튜브/보드 칸 수 등
    num_empty_slots     INT,                    -- 빈 슬롯 수 (소트 퍼즐)
    special_mechanics   VARCHAR,                -- JSON: 특수 기믹 목록 (예: '["ice","lock"]')

    -- ── 관리 ──
    designer_note       VARCHAR,                -- 기획자 의도 메모
    created_at          DATE,
    last_modified_at    DATE,

    PRIMARY KEY (game_id, level_id)
);


-- ============================================================
-- 2. level_balance_daily  (핵심: 레벨별 일간 밸런스 지표)
--    매일 집계. 대시보드의 메인 테이블
-- ============================================================
CREATE TABLE level_balance_daily (
    game_id             VARCHAR     NOT NULL,
    level_id            VARCHAR     NOT NULL,
    level_number        INT         NOT NULL,
    stat_date           DATE        NOT NULL,
    hard_tier           INT,

    -- ── 퍼널 & 볼륨 ──
    play_user_count     INT,                    -- UV (해당 레벨 플레이한 유저 수)
    play_count          INT,                    -- 총 시도 횟수
    clear_count         INT,                    -- 클리어 횟수
    fail_count          INT,                    -- 실패 횟수
    cancel_count        INT,                    -- 취소(나가기) 횟수

    -- ── 핵심 비율 ──
    clear_rate          DECIMAL(5,4),           -- clear_count / play_count
    first_try_clear_rate DECIMAL(5,4),          -- attempt_number=1에서 클리어한 비율
    cancel_rate         DECIMAL(5,4),           -- cancel_count / play_count

    -- ── 시도 횟수 분포 ──
    avg_attempts_to_clear DECIMAL(6,2),         -- 클리어까지 평균 시도 수
    median_attempts_to_clear INT,               -- 클리어까지 중앙값 시도 수
    p90_attempts_to_clear INT,                  -- 상위 10% 유저의 시도 수 (고난이도 병목 감지)

    -- ── 실패 유형 ──
    fail_deadlock_count INT,                    -- 데드락으로 인한 실패
    fail_timeout_count  INT,                    -- 시간 초과 실패
    fail_out_of_moves_count INT,                -- 무브 소진 실패
    fail_manual_quit_count INT,                 -- 수동 포기

    -- ── 무브 (공용) ──
    avg_moves_used      DECIMAL(6,2),           -- 전체 평균 조작 수
    avg_moves_clear     DECIMAL(6,2),           -- 클리어 판 평균 조작 수
    avg_moves_fail      DECIMAL(6,2),           -- 실패 판 평균 조작 수
    median_moves_clear  INT,
    p90_moves_clear     INT,                    -- 상위 10% 무브 (헤매는 유저 감지)

    -- ── 무브 효율 (무브 제한 게임용) ──
    avg_moves_remaining DECIMAL(6,2),           -- 클리어 시 평균 남은 무브 (null if 제한 없음)

    -- ── 무브 효율 (자유 조작 게임용) ──
    avg_undo_count      DECIMAL(6,2),
    avg_deadlock_count  DECIMAL(6,2),
    undo_usage_rate     DECIMAL(5,4),           -- undo를 1회 이상 사용한 판 비율

    -- ── 목표 달성도 (실패 판 한정) ──
    avg_objective_completion_on_fail DECIMAL(5,4),  -- 실패 시 평균 목표 달성률 (done/total)
    near_miss_rate      DECIMAL(5,4),           -- 목표 80%+ 달성 후 실패한 비율 ("아깝게 실패")
    hopeless_fail_rate  DECIMAL(5,4),           -- 목표 30% 미만 달성 후 실패한 비율 ("희망 없는 실패")

    -- ── 시간 ──
    avg_play_time_sec   DECIMAL(8,2),           -- 전체 평균 플레이 시간
    avg_clear_time_sec  DECIMAL(8,2),           -- 클리어 평균 시간
    median_clear_time_sec INT,
    avg_fail_time_sec   DECIMAL(8,2),           -- 실패 평균 시간 (짧으면 빠른 포기)

    -- ── 점수 ──
    avg_score           DECIMAL(10,2),
    avg_star_count      DECIMAL(3,2),

    PRIMARY KEY (game_id, level_id, stat_date)
);


-- ============================================================
-- 3. level_item_daily  (레벨별 아이템 사용 집계)
-- ============================================================
CREATE TABLE level_item_daily (
    game_id             VARCHAR     NOT NULL,
    level_id            VARCHAR     NOT NULL,
    level_number        INT         NOT NULL,
    stat_date           DATE        NOT NULL,

    item_id             VARCHAR     NOT NULL,
    item_category       VARCHAR     NOT NULL,

    -- ── 사용 지표 ──
    use_count           INT,                    -- 총 사용 횟수
    use_user_count      INT,                    -- 사용 유저 수 (UV)
    use_rate            DECIMAL(5,4),           -- 사용한 판 비율 (use_play_count / total_play_count)

    -- ── 효과 분석 ──
    clear_rate_with     DECIMAL(5,4),           -- 이 아이템 사용 시 클리어율
    clear_rate_without  DECIMAL(5,4),           -- 이 아이템 미사용 시 클리어율

    -- ── 경제 ──
    total_cost          INT,                    -- 이 아이템에 소비된 총 재화
    free_use_count      INT,                    -- 무료 사용 횟수
    paid_use_count      INT,                    -- 유료 사용 횟수

    PRIMARY KEY (game_id, level_id, stat_date, item_id)
);


-- ============================================================
-- 4. level_economy_daily  (레벨별 경제 집계)
-- ============================================================
CREATE TABLE level_economy_daily (
    game_id             VARCHAR     NOT NULL,
    level_id            VARCHAR     NOT NULL,
    level_number        INT         NOT NULL,
    stat_date           DATE        NOT NULL,

    -- ── 재화 흐름 ──
    total_coin_earned   INT,                    -- 이 레벨에서 총 획득 코인
    total_coin_spent    INT,                    -- 이 레벨에서 총 소비 코인
    net_coin_flow       INT,                    -- earned - spent (양수: 소스 > 싱크)
    avg_coin_earned     DECIMAL(8,2),
    avg_coin_spent      DECIMAL(8,2),

    -- ── 컨티뉴 ──
    continue_use_count  INT,                    -- 총 컨티뉴 사용 횟수
    continue_use_rate   DECIMAL(5,4),           -- 컨티뉴 사용 판 비율
    total_continue_cost INT,                    -- 컨티뉴에 소비된 총 재화

    -- ── 구매 (이 레벨에서 발생한 IAP) ──
    purchase_count      INT,                    -- 이 레벨에서 발생한 구매 건수
    purchase_user_count INT,                    -- 이 레벨에서 구매한 유저 수
    purchase_revenue_usd DECIMAL(10,2),         -- 이 레벨에서 발생한 매출
    top_trigger_point   VARCHAR,                -- 가장 많이 발생한 구매 트리거

    PRIMARY KEY (game_id, level_id, stat_date)
);


-- ============================================================
-- 5. level_retention_daily  (레벨별 이탈/체류 지표)
-- ============================================================
CREATE TABLE level_retention_daily (
    game_id             VARCHAR     NOT NULL,
    level_id            VARCHAR     NOT NULL,
    level_number        INT         NOT NULL,
    stat_date           DATE        NOT NULL,

    -- ── 퍼널 ──
    reach_user_count    INT,                    -- 이 레벨에 도달한 유저 수
    clear_user_count    INT,                    -- 이 레벨을 클리어한 유저 수
    pass_through_rate   DECIMAL(5,4),           -- clear_user / reach_user (레벨 통과율)

    -- ── 이탈 ──
    churn_user_count    INT,                    -- 이 레벨이 마지막 플레이인 유저 수 (D+1 미접속)
    churn_rate          DECIMAL(5,4),           -- churn_user / reach_user
    avg_attempts_before_churn DECIMAL(6,2),     -- 이탈 유저의 평균 시도 횟수

    -- ── 체류 ──
    avg_stay_time_sec   BIGINT,                 -- 이 레벨에 머문 총 시간 (클리어+실패+이탈 포함)
    payer_reach_count   INT,                    -- 이 레벨에 도달한 결제 유저 수
    payer_churn_count   INT,                    -- 이 레벨에서 이탈한 결제 유저 수

    PRIMARY KEY (game_id, level_id, stat_date)
);


-- ============================================================
-- 6. level_ab_test_daily  (A/B 테스트 비교용)
--    같은 level_number에 다른 level_id가 배정된 경우
-- ============================================================
CREATE TABLE level_ab_test_daily (
    game_id             VARCHAR     NOT NULL,
    level_number        INT         NOT NULL,
    stat_date           DATE        NOT NULL,
    test_group          VARCHAR     NOT NULL,   -- 'A' / 'B' / 'control'
    level_id            VARCHAR     NOT NULL,

    play_user_count     INT,
    clear_rate          DECIMAL(5,4),
    first_try_clear_rate DECIMAL(5,4),
    avg_attempts_to_clear DECIMAL(6,2),
    avg_moves_clear     DECIMAL(6,2),
    cancel_rate         DECIMAL(5,4),
    churn_rate          DECIMAL(5,4),
    avg_play_time_sec   DECIMAL(8,2),
    near_miss_rate      DECIMAL(5,4),
    item_use_rate       DECIMAL(5,4),
    purchase_revenue_usd DECIMAL(10,2),

    PRIMARY KEY (game_id, level_number, stat_date, test_group)
);
