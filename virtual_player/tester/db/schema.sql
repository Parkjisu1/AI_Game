-- ══════════════════════════════════════════════════════════════
--  AI Game Tester — Human Play Database v1.0
--  Black-box APK 기반: 이미지 + 터치 JSON에서 학습
-- ══════════════════════════════════════════════════════════════

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── 디바이스 관리 ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS device (
    device_id       TEXT PRIMARY KEY,           -- UUID or ADB serial
    name            TEXT,                       -- 사람이 읽을 수 있는 이름
    platform        TEXT DEFAULT 'android',     -- android | ios | web
    screen_width    INTEGER DEFAULT 1080,
    screen_height   INTEGER DEFAULT 1920,
    emulator        TEXT,                       -- BlueStacks | LDPlayer | Nox
    registered_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_sync_at    DATETIME,
    total_sessions  INTEGER DEFAULT 0
);

-- ── 게임 프로필 ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS game_profile (
    game_id         TEXT PRIMARY KEY,           -- 패키지명 또는 식별자
    game_name       TEXT,
    genre           TEXT,                       -- puzzle | idle | rpg | merge | slg
    screen_types    TEXT,                       -- JSON: 인식된 화면 유형 목록
    yolo_model_path TEXT,                       -- 화면 분류기 경로
    playbook_id     TEXT,                       -- Playbook 규칙 참조
    registered_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- ── 플레이 세션 (1레벨 1시도 = 1세션) ───────────────────────
CREATE TABLE IF NOT EXISTS session (
    session_id      TEXT PRIMARY KEY,
    device_id       TEXT REFERENCES device(device_id),
    game_id         TEXT REFERENCES game_profile(game_id),
    player_type     TEXT DEFAULT 'human',       -- human | ai | ai_v2 | ai_v3
    level_id        INTEGER,                    -- 레벨 번호 (OCR 추출)
    started_at      DATETIME NOT NULL,
    ended_at        DATETIME,
    outcome         TEXT,                       -- clear | fail | abandon | crash
    fail_reason     TEXT,
    total_turns     INTEGER DEFAULT 0,
    total_taps      INTEGER DEFAULT 0,
    score           INTEGER DEFAULT 0,
    star_count      INTEGER DEFAULT 0,
    duration_sec    REAL DEFAULT 0,

    -- 초기 상태 요약 (빠른 검색용)
    screen_type_at_start TEXT,                  -- gameplay | lobby | ...
    state_hash_start     TEXT,                  -- 초기 상태 해시

    -- 스크린샷 참조 (파일 경로 또는 NULL)
    screenshot_start TEXT,
    screenshot_end   TEXT,

    -- 원본 데이터 소스
    source_file     TEXT,                       -- session_log.jsonl 경로
    source_device   TEXT                        -- 원본 디바이스 ID
);

-- ── 턴 (1턴 = 1회 의사결정 + 실행 + 결과) ──────────────────
CREATE TABLE IF NOT EXISTS turn (
    turn_id         TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES session(session_id) ON DELETE CASCADE,
    turn_number     INTEGER NOT NULL,
    timestamp       DATETIME NOT NULL,

    -- 상태 스냅샷
    screenshot_before TEXT,                     -- 행동 전 스크린샷 경로
    screenshot_after  TEXT,                     -- 행동 후 스크린샷 경로
    state_hash      TEXT,                       -- 행동 전 상태 해시 (패턴 매칭 키)
    screen_type     TEXT,                       -- YOLO 분류 결과

    -- 의사결정
    decision_source TEXT,                       -- human | rule | pattern | lookahead
    decision_reason TEXT,
    confidence      REAL DEFAULT 1.0,           -- 인간=1.0, AI=0~1

    -- 결과
    result          TEXT,                       -- match | move | no_change | screen_change
    delta_score     REAL DEFAULT 0,             -- 이미지 변화량 (0~1)

    -- 타이밍
    think_time_ms   INTEGER,
    exec_time_ms    INTEGER
);

-- ── 개별 터치 액션 ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS action (
    action_id       TEXT PRIMARY KEY,
    turn_id         TEXT NOT NULL REFERENCES turn(turn_id) ON DELETE CASCADE,
    action_index    INTEGER NOT NULL,           -- 턴 내 순서

    type            TEXT NOT NULL,              -- tap | swipe | long_press | booster
    x               REAL NOT NULL,              -- 정규화 좌표 [0-1]
    y               REAL NOT NULL,
    end_x           REAL,                       -- swipe 끝점
    end_y           REAL,
    duration_ms     INTEGER,                    -- 터치 지속 시간
    timestamp       DATETIME NOT NULL,

    -- 메타 (선택적, YOLO/OCR로 추출 시)
    target_region   TEXT,                       -- board | holder | booster | ui | unknown
    target_label    TEXT                        -- 색상명 또는 UI 요소명
);

-- ── 레벨 스냅샷 (스테이지 초기 상태) ────────────────────────
CREATE TABLE IF NOT EXISTS level_snapshot (
    snapshot_id     TEXT PRIMARY KEY,
    game_id         TEXT REFERENCES game_profile(game_id),
    level_id        INTEGER,
    captured_at     DATETIME DEFAULT CURRENT_TIMESTAMP,

    -- 이미지
    screenshot_path TEXT,                       -- 전체 스크린샷
    board_crop_path TEXT,                       -- 보드 크롭 이미지
    board_hash      TEXT,                       -- 이미지 해시 (중복 방지)

    -- 추출 정보 (가능한 경우)
    grid_rows       INTEGER,
    grid_cols       INTEGER,
    num_colors      INTEGER,
    fieldmap        TEXT,                       -- FieldMap 문자열 (색상 배치)

    -- 통계 (누적)
    human_clear_rate    REAL DEFAULT 0,
    human_avg_turns     REAL DEFAULT 0,
    ai_clear_rate       REAL DEFAULT 0,
    total_attempts      INTEGER DEFAULT 0,

    UNIQUE(game_id, level_id, board_hash)
);

-- ── 행동 패턴 (학습된 "상황→행동" 매핑) ────────────────────
CREATE TABLE IF NOT EXISTS pattern (
    pattern_id      TEXT PRIMARY KEY,
    game_id         TEXT REFERENCES game_profile(game_id),
    level_id        INTEGER,                    -- NULL = 범용 패턴

    -- 상태 조건 (매칭 키)
    state_hash      TEXT NOT NULL,              -- 보드+UI 상태의 해시
    screen_type     TEXT,                       -- gameplay | lobby | popup | ...
    state_features  TEXT,                       -- JSON: 추가 특성 (위험도, 매칭가능 등)

    -- 행동
    action_type     TEXT NOT NULL,              -- tap | swipe | booster | ui_tap
    action_x        REAL,                       -- 정규화 좌표
    action_y        REAL,
    action_detail   TEXT,                       -- JSON: 추가 정보

    -- 성과 통계
    times_seen      INTEGER DEFAULT 1,
    times_success   INTEGER DEFAULT 0,
    avg_delta_score REAL DEFAULT 0,
    confidence      REAL DEFAULT 0.5,           -- 0~1, 높을수록 신뢰

    -- 출처
    source          TEXT DEFAULT 'human',       -- human | ai_learned | rule
    first_seen_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_seen_at    DATETIME DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(game_id, state_hash, action_type, action_x, action_y)
);

-- ── 분석 캐시 (역분석 결과) ──────────────────────────────────
CREATE TABLE IF NOT EXISTS analytics_cache (
    cache_id        TEXT PRIMARY KEY,
    game_id         TEXT REFERENCES game_profile(game_id),
    analysis_type   TEXT NOT NULL,              -- bm | difficulty_curve | screen_flow | economy
    data_json       TEXT NOT NULL,              -- 분석 결과 JSON
    computed_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    session_count   INTEGER DEFAULT 0,          -- 분석에 사용된 세션 수
    is_stale        BOOLEAN DEFAULT FALSE       -- 새 데이터 추가 시 stale 마킹
);

-- ── 디바이스 동기화 추적 ─────────────────────────────────────
CREATE TABLE IF NOT EXISTS sync_log (
    sync_id         TEXT PRIMARY KEY,
    device_id       TEXT REFERENCES device(device_id),
    synced_at       DATETIME DEFAULT CURRENT_TIMESTAMP,
    sessions_synced INTEGER DEFAULT 0,
    turns_synced    INTEGER DEFAULT 0,
    patterns_synced INTEGER DEFAULT 0,
    bytes_transferred INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'success'      -- success | partial | failed
);

-- ══════════════════════════════════════════════════════════════
--  인덱스
-- ══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_session_game ON session(game_id);
CREATE INDEX IF NOT EXISTS idx_session_level ON session(level_id);
CREATE INDEX IF NOT EXISTS idx_session_outcome ON session(outcome);
CREATE INDEX IF NOT EXISTS idx_session_player ON session(player_type);
CREATE INDEX IF NOT EXISTS idx_session_device ON session(device_id);

CREATE INDEX IF NOT EXISTS idx_turn_session ON turn(session_id);
CREATE INDEX IF NOT EXISTS idx_turn_state ON turn(state_hash);
CREATE INDEX IF NOT EXISTS idx_turn_screen ON turn(screen_type);

CREATE INDEX IF NOT EXISTS idx_action_turn ON action(turn_id);

CREATE INDEX IF NOT EXISTS idx_pattern_state ON pattern(state_hash);
CREATE INDEX IF NOT EXISTS idx_pattern_game ON pattern(game_id);
CREATE INDEX IF NOT EXISTS idx_pattern_confidence ON pattern(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_pattern_level ON pattern(level_id);

CREATE INDEX IF NOT EXISTS idx_snapshot_game_level ON level_snapshot(game_id, level_id);

-- ══════════════════════════════════════════════════════════════
--  뷰 (자주 쓰는 쿼리)
-- ══════════════════════════════════════════════════════════════

-- 레벨별 클리어율
CREATE VIEW IF NOT EXISTS v_level_stats AS
SELECT
    game_id,
    level_id,
    player_type,
    COUNT(*) as attempts,
    SUM(CASE WHEN outcome = 'clear' THEN 1 ELSE 0 END) as clears,
    ROUND(100.0 * SUM(CASE WHEN outcome = 'clear' THEN 1 ELSE 0 END) / COUNT(*), 1) as clear_rate,
    ROUND(AVG(total_turns), 1) as avg_turns,
    ROUND(AVG(duration_sec), 1) as avg_duration
FROM session
WHERE outcome IN ('clear', 'fail')
GROUP BY game_id, level_id, player_type;

-- 상위 패턴 (신뢰도 순)
CREATE VIEW IF NOT EXISTS v_top_patterns AS
SELECT
    p.*,
    (CASE WHEN times_seen >= 5 THEN ROUND(100.0 * times_success / times_seen, 1) ELSE NULL END) as success_rate
FROM pattern p
WHERE confidence >= 0.3
ORDER BY confidence DESC, times_success DESC;

-- 디바이스별 동기화 현황
CREATE VIEW IF NOT EXISTS v_device_status AS
SELECT
    d.device_id,
    d.name,
    d.total_sessions,
    d.last_sync_at,
    (SELECT COUNT(*) FROM session s WHERE s.device_id = d.device_id) as synced_sessions,
    ROUND(julianday('now') - julianday(d.last_sync_at), 1) as days_since_sync
FROM device d;
