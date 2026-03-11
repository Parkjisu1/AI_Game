-- ============================================================
-- 퍼즐 게임 공용 Raw Data Schema
-- 목적: 밸런스 기획을 위한 이벤트 단위 유저 행동 로그
-- 최종 정리: 2025-03
-- ============================================================


-- ============================================================
-- 0. item_master  (게임별 아이템 정의 테이블)
-- ============================================================
CREATE TABLE item_master (
    game_id             VARCHAR     NOT NULL,
    item_id             VARCHAR     NOT NULL,
    item_name           VARCHAR,
    item_category       VARCHAR     NOT NULL,
        -- 'pre_play_item'   : 판 시작 전 사용
        -- 'in_play_item'    : 판 진행 중 사용
        -- 'continue_item'   : 이어하기 관련
        -- 'currency'        : 재화 (코인, 젬 등)
        -- 'consumable'      : 기타 소모품 (라이프, 키 등)
    item_description    VARCHAR,
    PRIMARY KEY (game_id, item_id)
);

-- 예시: 소트 퍼즐
-- ('sort_puzzle', 'SP_001', '빈 튜브',      'pre_play_item',  '시작 시 빈 튜브 1개 추가')
-- ('sort_puzzle', 'SP_002', '되돌리기 3회',  'in_play_item',   '판 중 undo 3회 추가')
-- ('sort_puzzle', 'SP_003', '셔플',          'in_play_item',   '튜브 내용물 재배치')
-- ('sort_puzzle', 'SP_100', '코인',          'currency',       '기본 재화')

-- 예시: 매치3
-- ('match3', 'M3_001', '레인보우 볼', 'pre_play_item',  '시작 시 보드에 배치')
-- ('match3', 'M3_002', '해머',        'in_play_item',   '타일 1개 즉시 제거')
-- ('match3', 'M3_003', '+5 무브',     'continue_item',  '실패 시 무브 5회 추가')


-- ============================================================
-- 1. level_play_event  (핵심: 한 판 = 한 행)
-- ============================================================
CREATE TABLE level_play_event (
    -- ── PK / 식별 ──
    event_id            VARCHAR     NOT NULL,
    session_id          VARCHAR     NOT NULL,
    game_id             VARCHAR     NOT NULL,
    UID                 VARCHAR     NOT NULL,

    -- ── 시간 ──
    event_timestamp     DATETIME    NOT NULL,

    -- ── 버전 & 환경 ──
    app_version         VARCHAR     NOT NULL,
    install_version     VARCHAR,
    country             VARCHAR,
    platform            VARCHAR,
    device_model        VARCHAR,

    -- ── 레벨 정보 ──
    level_number        INT         NOT NULL,
    level_id            VARCHAR     NOT NULL,
    is_tutorial         BOOLEAN     DEFAULT FALSE,
    hard_tier           INT,

    -- ── 시도 컨텍스트 ──
    attempt_number      INT         NOT NULL,
    is_first_play       BOOLEAN,

    -- ── 플레이 결과 ──
    result              VARCHAR     NOT NULL,   -- 'clear' / 'fail' / 'cancel'
    fail_reason         VARCHAR,                -- 'deadlock' / 'timeout' / 'manual_quit' / 'out_of_moves' / null

    -- ── 무브 (공용) ──
    moves_used          INT,                    -- 총 조작 횟수

    -- ── 무브 (무브 제한 게임용: 매치3 등) ──
    moves_given         INT,                    -- 주어진 무브 수 (제한 없으면 null)
    moves_remaining     INT,                    -- 클리어 시 남은 무브 (제한 없으면 null)

    -- ── 무브 (자유 조작 게임용: 소트 퍼즐 등) ──
    undo_count          INT         DEFAULT 0,
    deadlock_count      INT         DEFAULT 0,

    -- ── 목표 달성 ──
    objective_total     INT,
    objective_done      INT,

    -- ── 시간 ──
    play_time_sec       INT,

    -- ── 점수 ──
    score               INT,
    star_count          INT,

    -- ── 아이템: 판 시작 전 ──
    pre_play_item_ids   VARCHAR,                -- JSON: '["SP_001"]'
    pre_play_item_count INT         DEFAULT 0,

    -- ── 아이템: 판 진행 중 ──
    in_play_item_ids    VARCHAR,                -- JSON: '["SP_003","SP_003"]'
    in_play_item_count  INT         DEFAULT 0,

    -- ── 컨티뉴 ──
    continue_count      INT         DEFAULT 0,
    continue_cost_total INT         DEFAULT 0,

    -- ── 경제 ──
    coin_earned         INT         DEFAULT 0,
    coin_spent          INT         DEFAULT 0,

    -- ── 보조 기능 ──
    shuffle_count       INT         DEFAULT 0,
    hint_count          INT         DEFAULT 0
);


-- ============================================================
-- 2. item_use_event  (아이템 개별 사용 상세)
-- ============================================================
CREATE TABLE item_use_event (
    event_id            VARCHAR     NOT NULL,
    play_event_id       VARCHAR     NOT NULL,
    game_id             VARCHAR     NOT NULL,
    UID                 VARCHAR     NOT NULL,
    event_timestamp     DATETIME    NOT NULL,

    level_number        INT         NOT NULL,
    level_id            VARCHAR     NOT NULL,

    item_id             VARCHAR     NOT NULL,
    item_category       VARCHAR     NOT NULL,
    acquisition_type    VARCHAR,                -- 'free' / 'purchased' / 'reward'
    cost_amount         INT         DEFAULT 0,
    cost_currency_id    VARCHAR
);


-- ============================================================
-- 3. purchase_event  (IAP / 인앱 구매)
-- ============================================================
CREATE TABLE purchase_event (
    event_id            VARCHAR     NOT NULL,
    game_id             VARCHAR     NOT NULL,
    UID                 VARCHAR     NOT NULL,
    event_timestamp     DATETIME    NOT NULL,

    app_version         VARCHAR,
    country             VARCHAR,
    platform            VARCHAR,

    product_id          VARCHAR     NOT NULL,
    product_name        VARCHAR,
    product_type        VARCHAR,                -- 'coin_pack' / 'item_pack' / 'lives' / 'subscription' / 'starter_pack'
    price_usd           DECIMAL(10,2),
    price_local         DECIMAL(10,2),
    currency_code       VARCHAR,

    trigger_point       VARCHAR,                -- 'level_fail_popup' / 'shop' / 'out_of_lives' / 'item_slot' / 'special_offer'
    level_number        INT,

    coin_granted        INT         DEFAULT 0,
    items_granted       VARCHAR,                -- JSON
    lives_granted       INT         DEFAULT 0,

    receipt_id          VARCHAR,
    is_verified         BOOLEAN     DEFAULT FALSE
);


-- ============================================================
-- 4. economy_event  (재화 변동 원장)
-- ============================================================
CREATE TABLE economy_event (
    event_id            VARCHAR     NOT NULL,
    game_id             VARCHAR     NOT NULL,
    UID                 VARCHAR     NOT NULL,
    event_timestamp     DATETIME    NOT NULL,

    currency_type       VARCHAR     NOT NULL,   -- item_master의 currency item_id 참조
    change_amount       INT         NOT NULL,   -- 양수: 획득, 음수: 소비
    balance_after       INT,

    source              VARCHAR     NOT NULL,   -- 'level_clear' / 'daily_reward' / 'iap' / 'ad_reward' / 'item_purchase' / 'continue'
    ref_event_id        VARCHAR,
    level_number        INT
);


-- ============================================================
-- 5. session_event  (앱 세션)
-- ============================================================
CREATE TABLE session_event (
    session_id          VARCHAR     NOT NULL,
    game_id             VARCHAR     NOT NULL,
    UID                 VARCHAR     NOT NULL,
    session_start       DATETIME    NOT NULL,
    session_end         DATETIME,
    duration_sec        INT,

    app_version         VARCHAR,
    country             VARCHAR,
    platform            VARCHAR,
    device_model        VARCHAR,

    levels_played       INT         DEFAULT 0,
    levels_cleared      INT         DEFAULT 0
);


-- ============================================================
-- 6. ad_event  (광고 시청)
-- ============================================================
CREATE TABLE ad_event (
    event_id            VARCHAR     NOT NULL,
    game_id             VARCHAR     NOT NULL,
    UID                 VARCHAR     NOT NULL,
    event_timestamp     DATETIME    NOT NULL,

    ad_type             VARCHAR     NOT NULL,   -- 'rewarded' / 'interstitial'
    ad_placement        VARCHAR,
    result              VARCHAR     NOT NULL,   -- 'completed' / 'skipped' / 'error'

    reward_type         VARCHAR,
    reward_amount       INT,

    level_number        INT
);


-- ============================================================
-- 7. user_property  (유저 일별 스냅샷)
-- ============================================================
CREATE TABLE user_property (
    game_id             VARCHAR     NOT NULL,
    UID                 VARCHAR     NOT NULL,
    snapshot_date       DATE        NOT NULL,

    install_date        DATE,
    install_version     VARCHAR,
    country             VARCHAR,
    platform            VARCHAR,
    device_model        VARCHAR,

    current_level       INT,
    total_play_count    INT,
    total_clear_count   INT,
    total_coin_balance  INT,
    total_spend_usd     DECIMAL(10,2),
    is_payer            BOOLEAN,
    days_since_install  INT,
    last_active_date    DATE
);
