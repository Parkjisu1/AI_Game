"""
Puzzle Genre Module for C10+ v2.5
==================================
Covers: Car Match, Tap Shift, Magic Sort (and future puzzle games)

Tester Roles (10):
  1. Full Playthrough A    — Level progression, difficulty curve
  2. Full Playthrough B    — Independent verification, menu/UI mapping
  3. Numeric Collection    — Star ratings, scores, level data tables
  4. Timing Observation    — Animation speed, transitions, easing
  5. Visual Measurement    — Grid size, spacing, colors (px units)
  6. Edge Case Testing     — Resource depletion, fail states, limits
  7. Economy Tracking      — Coins, rewards, IAP, daily bonuses
  8. Algorithm Behavior    — Pathfinding, level gen, hint logic
  9. State & Flow Mapping  — Screens, popups, state machine
 10. Cross-Validation      — Re-confirm weak/critical parameters
"""

import time
from genres import GenreBase, GameConfig, Mission, CaptureContext, register_genre
from typing import Dict, List, Tuple


class PuzzleGenre(GenreBase):

    @property
    def genre_name(self) -> str:
        return "Puzzle"

    @property
    def genre_key(self) -> str:
        return "puzzle"

    # ------------------------------------------------------------------
    # Games
    # ------------------------------------------------------------------

    def get_games(self) -> Dict[str, GameConfig]:
        return {
            "tapshift": GameConfig(
                key="tapshift", name="Tap Shift",
                package="com.paxiegames.tapshift", prefix="TS",
                coords={
                    "play": (400, 980), "settings": (690, 145),
                    "center": (400, 550), "tl": (200, 350), "tr": (600, 350),
                    "bl": (200, 750), "br": (600, 750),
                    "booster": (400, 1100), "popup": (400, 800),
                    "popup_close": (400, 800), "popup_x": (650, 200),
                },
                wiki_keywords=["tap shift puzzle guide", "tap shift tips levels"],
            ),
            "magicsort": GameConfig(
                key="magicsort", name="Magic Sort",
                package="com.grandgames.magicsort", prefix="MS",
                coords={
                    "play": (400, 900), "settings": (690, 145),
                    "center": (400, 500), "tl": (100, 350), "tr": (700, 350),
                    "bl": (100, 700), "br": (700, 700),
                    "booster": (400, 1050), "popup": (400, 800),
                    "popup_close": (400, 800), "popup_x": (650, 200),
                },
                wiki_keywords=["magic sort puzzle guide", "magic sort levels solution"],
            ),
            "carmatch": GameConfig(
                key="carmatch", name="Car Match",
                package="com.grandgames.carmatch", prefix="CM",
                coords={
                    "play": (400, 900), "settings": (690, 145),
                    "center": (400, 450), "tl": (200, 250), "tr": (600, 250),
                    "bl": (200, 650), "br": (600, 650),
                    "booster": (400, 1050), "popup": (400, 800),
                    "popup_close": (400, 800), "popup_x": (650, 200),
                },
                wiki_keywords=["car match puzzle guide", "car match tips walkthrough"],
            ),
        }

    # ------------------------------------------------------------------
    # Missions (10 AI Testers)
    # ------------------------------------------------------------------

    def get_missions(self) -> Dict[int, Mission]:
        return {
            1:  Mission(1,  "Full Playthrough A",      "gameplay",         "레벨 1부터 10+레벨 진행, 난이도 곡선 관찰"),
            2:  Mission(2,  "Full Playthrough B",      "gameplay",         "독립 플레이스루, 메뉴 탐색 포함 교차검증"),
            3:  Mission(3,  "Numeric Data Collection", "numeric",          "레벨별 수치(오브젝트수, 색상수, 별점) 수집", flex=True),
            4:  Mission(4,  "Timing Observation",      "timing",           "애니메이션 속도, 전환 시간, 이동 타이밍 관찰", flex=True),
            5:  Mission(5,  "Visual Measurement",      "visual",           "격자 크기, 간격, 색상, UI 레이아웃 측정"),
            6:  Mission(6,  "Edge Case Testing",       "edge_case",        "한계값 테스트 - 힌트/되돌리기/생명 소진", flex=True),
            7:  Mission(7,  "Economy Tracking",        "economy",          "초기 재화, 레벨 보상, 상점 가격 추적", flex=True),
            8:  Mission(8,  "Algorithm Behavior",      "algorithm",        "경로탐색, 충돌판정, 레벨생성 방식 추론", flex=True),
            9:  Mission(9,  "State & Flow Mapping",    "state",            "화면 전환, 팝업 목록, 상태 머신 매핑", flex=True),
            10: Mission(10, "Cross-Validation",        "cross_validation", "약점 항목 재확인, 별점 기준 정밀 관찰"),
        }

    # ------------------------------------------------------------------
    # Domain Weights
    # ------------------------------------------------------------------

    def get_domain_weights(self) -> Dict[str, List[int]]:
        return {
            "gameplay":     [1, 2],
            "numeric":      [3],
            "timing":       [4],
            "visual":       [5],
            "edge_case":    [6],
            "economy":      [7],
            "algorithm":    [8],
            "state":        [9],
            "cross_validation": [10],
        }

    # ------------------------------------------------------------------
    # Aggregation Sections (puzzle-specific)
    # ------------------------------------------------------------------

    def get_aggregation_sections(self) -> List[str]:
        return [
            "게임 정체성", "UI 구성", "게임 메커니즘", "수치 데이터 (Numeric Expert)",
            "시각 측정 (Visual Expert)", "재화/경제 (Economy Expert)",
            "난이도/레벨 진행", "부스터/특수기능",
            "타이밍 (Timing Expert)", "알고리즘 추론 (Algorithm Expert)",
            "상태/흐름 (State Expert)", "한계값 (Edge Case Expert)",
        ]

    def get_aggregation_rules(self) -> str:
        return """- 퍼즐 게임 특화: 격자 크기 변화, 색상 수 진행, 별점 기준을 특히 정밀하게
- 수치 전문가(3)의 레벨별 데이터 테이블을 우선 채택
- 타이밍 전문가(4)의 프레임 분석 결과를 채택 (체감 추정 < 정량 측정)"""

    # ------------------------------------------------------------------
    # Vision Prompts
    # ------------------------------------------------------------------

    def get_vision_prompt(self, session_id: int, game_name: str) -> str:
        prompts = {
            1: f"""{game_name} 게임 - 전문가 1: Full Playthrough A

당신은 게임 구조 분석 전문가입니다. 이 스크린샷들은 레벨 1부터 순서대로 진행한 플레이스루입니다.

분석 항목:
1. 총 레벨 수 (레벨 선택 화면에서 확인)
2. 레벨별 보드/격자 크기 변화 (숫자로 기록)
3. 레벨별 오브젝트(화살표/병/자동차) 수 변화
4. 난이도 전환점 (새 메커니즘 등장 레벨)
5. 챕터/구간 구조
6. 클리어 조건, 실패 조건

규칙: 모든 숫자를 정확히 기록. 레벨 번호와 관찰값을 테이블로 정리.""",

            2: f"""{game_name} 게임 - 전문가 2: Full Playthrough B (교차검증)

당신은 게임 구조 분석 전문가입니다. 이 스크린샷들은 독립적인 두 번째 플레이스루입니다.

분석 항목 (전문가 1과 동일하지만 독립 관찰):
1. 총 레벨 수, 챕터 구조
2. 레벨별 보드 크기, 오브젝트 수 변화
3. 난이도 전환점
4. 메뉴 구조, 버튼 배치, UI 요소
5. 게임 정체성 (제목, 장르, 아트 스타일)

규칙: 전문가 1의 결과를 보지 않고 독립 분석. 모든 숫자를 테이블로 정리.""",

            3: f"""{game_name} 게임 - 전문가 3: 수치 역추정 전문가

당신은 게임 밸런스 수치 분석 전문가입니다. 스크린샷에서 정확한 숫자값을 추출하세요.

필수 수집 데이터:
1. 별점 기준: 실수 0회=?성, 1회=?성, 2회=?성, 3+회=?성
2. 점수/코인 보상: 별점별 보상량
3. 레벨별 데이터 (테이블): 레벨#, 격자크기, 오브젝트수, 색상수, 목표이동수
4. 진행 공식 추정: 위 데이터에서 패턴/공식 역산
5. 부스터 수량, 한계값

출력 형식: 반드시 정확한 숫자를 테이블로 정리. 추정값은 (추정) 표시.""",

            4: f"""{game_name} 게임 - 전문가 4: 타이밍 측정 전문가

당신은 게임 애니메이션 타이밍 분석 전문가입니다. 스크린샷의 상태 변화로 타이밍을 추론하세요.

분석 항목:
1. 오브젝트 이동 애니메이션: 시작→종료 상태, 추정 소요 시간
2. 이동 가속/감속 패턴: 등속 vs ease-in vs ease-out
3. 이동 중 변형: 늘어남(stretch), 축소, 회전 여부
4. 매칭/완성 연출: 사라짐, 바운스, 스케일 변화
5. 팝업 애니메이션: 등장/퇴장 방식
6. 페이지 전환: 페이드, 슬라이드, 즉시
7. 피드백 애니메이션: 막힘 흔들림, 힌트 펄스

규칙: 스크린샷 간 변화로 대략적 시간 추정. 초 단위로 기록.""",

            5: f"""{game_name} 게임 - 전문가 5: 시각 측정 전문가

당신은 UI/UX 측정 전문가입니다. 스크린샷에서 다음을 픽셀 단위로 분석하세요.

필수 측정:
1. 격자/보드: 전체 크기, 셀 크기, 셀 간격 (px 단위)
2. 오브젝트: 크기, 격자 대비 비율 (model_scale)
3. 홀더/병 영역: 위치(Y좌표), 슬롯 간격
4. UI 요소: 버튼 크기, 여백, 상단/하단 바 높이
5. 색상: 주요 오브젝트 색상의 HEX 코드 (가능한 정확하게)
6. 화면 비율: 해상도 추정 (16:9, 9:16 등)
7. Y 오프셋: 보드 시작 Y좌표

출력: 모든 측정값을 px 단위 숫자로 기록. 비율은 소수점으로.""",

            6: f"""{game_name} 게임 - 전문가 6: 경계조건 탐색 전문가

당신은 게임 한계값 테스트 전문가입니다. 리소스 고갈과 극단적 상태를 분석하세요.

필수 확인:
1. 되돌리기(Undo): 최대 몇 회 가능? 소진 후 UI 변화?
2. 힌트: 최대 몇 개? 소진 후 UI 변화?
3. 생명(Lives): 최대 몇 개? 소진 과정? 회복 메커니즘?
4. 부스터: 각 종류별 초기 수량? 소진 후 구매 UI?
5. 홀더/병: 최대 용량? 가득 찰 때의 동작?
6. 실패 조건: 정확히 어떤 상태에서 실패 판정?
7. 재시작 흐름: 실패 후 선택지 (재시작, 부스터 구매, 메뉴)

규칙: 정확한 최대/최소 숫자 기록. 소진 전후 상태 비교.""",

            7: f"""{game_name} 게임 - 전문가 7: 경제 시스템 전문가

당신은 게임 경제 분석 전문가입니다. 재화 흐름을 정밀 추적하세요.

필수 추적:
1. 초기 재화: 게임 최초 시작 시 코인/젬 수 (정확한 숫자)
2. 레벨 보상: 레벨별 (별점, 코인 보상) 쌍 기록
3. 부스터 가격: 각 부스터의 코인/젬 가격
4. 일일 보상: 7일 주기 보상 (가능한 범위까지)
5. 여정/마일스톤 보상: 레벨 마일스톤별 보상
6. 광고 빈도: 몇 레벨마다 전면광고 노출?
7. IAP 상품: 상점에 표시된 상품과 가격

출력: 모든 재화값을 정확한 숫자로 기록. 보상 테이블 작성.""",

            8: f"""{game_name} 게임 - 전문가 8: 알고리즘 행동 분석 전문가

당신은 게임 알고리즘 추론 전문가입니다. 외부 행동에서 내부 알고리즘을 추론하세요.

분석 항목:
1. 경로 탐색: 자동차/오브젝트가 장애물을 어떻게 우회하는가?
2. 충돌 판정: 이동 가능/불가능을 어떻게 결정하는가?
3. 레벨 생성: 같은 레벨 재시작 시 배치가 바뀌나? (절차적 vs 고정)
4. 힌트 로직: 힌트가 추천하는 수의 패턴은?
5. 매칭 검사: 연속 동일 타입 감지 방식
6. 교착 판정: 더 이상 진행 불가한 상태를 감지하는가?

규칙: 관찰된 행동 패턴에서 논리적으로 추론. 확실한 것과 추론을 구분.""",

            9: f"""{game_name} 게임 - 전문가 9: 상태/흐름 매핑 전문가

당신은 게임 상태 머신 분석 전문가입니다. 모든 화면과 전환을 매핑하세요.

필수 매핑:
1. 화면 목록: 모든 고유 화면(메인메뉴, 게임, 일시정지, 완료, 실패 등)
2. 전환 다이어그램: 화면 A -> 화면 B (어떤 동작으로)
3. 팝업 목록: 모든 팝업 종류와 출현 조건
4. 설정 옵션: 설정 화면의 모든 항목
5. 저장 동작: 앱 종료 후 재시작 시 보존되는 상태
6. 게임 상태 수: 총 몇 개의 상태가 존재하는가?

출력: 상태 목록과 전환 다이어그램을 텍스트로 작성.""",

            10: f"""{game_name} 게임 - 전문가 10: 교차검증 전문가

당신은 게임 데이터 검증 전문가입니다. 핵심 파라미터를 정밀 재확인하세요.

집중 확인 항목:
1. 별점 기준: 실수 횟수별 별점 변화를 정밀 관찰
2. 레벨 진행: 격자 크기가 정확히 몇 레벨에서 바뀌는지
3. 부스터 상세: 각 부스터의 정확한 효과와 초기 수량
4. 색상 수: 초반/중반/후반 활성 색상 수
5. 난이도 전환: 어느 레벨에서 체감 난이도가 급변하는지

규칙: 최대한 정밀하게 관찰. 불확실하면 여러 번 시도하여 확인.""",
        }
        return prompts[session_id]

    # ------------------------------------------------------------------
    # Parameters (32 per game)
    # ------------------------------------------------------------------

    def get_parameters(self, game_key: str) -> str:
        params = {
            "tapshift": """TS01: total_levels (core_constants) - 총 레벨 수
TS02: max_lives (core_constants) - 최대 생명 수
TS03: max_undo_count (core_constants) - 최대 되돌리기 횟수
TS04: max_hint_count (core_constants) - 최대 힌트 수
TS05: interstitial_frequency (monetization) - 전면광고 빈도
TS06: arrow_move_speed (core_constants) - 화살표 이동 속도
TS07: max_arrow_clamp (core_constants) - 최대 화살표 수 제한
TS08: star_rating_system (scoring) - 별점 시스템 기준
TS09: base_unit (animation) - 기본 단위(픽셀)
TS10: position_snap (animation) - 위치 스냅 값
TS11: duration_clamp (animation) - 애니메이션 지속시간 범위
TS12: stretch_phase (animation) - 스트레칭 단계 비율
TS13: stretch_max (animation) - 최대 스트레칭 배율
TS14: snap_phase (animation) - 스냅 단계 비율
TS15: arrow_colors (visual) - 방향별 화살표 색상
TS16: head_ratio (visual) - 화살표 머리 비율
TS17: shaft_height_ratio (visual) - 화살표 축 높이 비율
TS18: collision_system (algorithm) - 충돌 판정 방식
TS19: performance_complexity (algorithm) - 성능 복잡도
TS20: solver_algorithm (algorithm) - 솔버 알고리즘
TS21: ui_reference_resolution (ui) - UI 기준 해상도
TS22: total_files (architecture) - 총 파일 수
TS23: pattern_count (architecture) - 디자인 패턴 수
TS24: state_count (architecture) - 게임 상태 수
TS25: serialization_format (architecture) - 직렬화 형식
TS26: arrow_directions (gameplay) - 화살표 방향 종류
TS27: arrow_count_progression (difficulty) - 화살표 수 진행
TS28: grid_size_range (gameplay) - 격자 크기 범위
TS29: tap_mechanic (gameplay) - 탭 메커니즘
TS30: goal_condition (gameplay) - 클리어 조건
TS31: level_generation (algorithm) - 레벨 생성 방식
TS32: save_system (architecture) - 저장 시스템""",

            "magicsort": """MS01: bottle_max_height (core_constants) - 병 최대 높이(층)
MS02: colors_total (core_constants) - 전체 색상 수
MS03: colors_playable (core_constants) - 플레이 가능 색상 수
MS04: builtin_levels (level_gen) - 빌트인 레벨 수
MS05: procedural_after_level (level_gen) - 절차적 생성 시작 레벨
MS06: max_gen_attempts (level_gen) - 최대 생성 시도 횟수
MS07: difficulty_tier_count (difficulty) - 난이도 티어 수
MS08: tier_color_counts (difficulty) - 티어별 색상 수
MS09: tier_level_ranges (difficulty) - 티어별 레벨 범위
MS10: par_bonus_values (difficulty) - 파 보너스 값
MS11: par_formula (difficulty) - 파 계산 공식
MS12: max_per_row (visual) - 행당 최대 병 수
MS13: h_spacing (visual) - 수평 간격
MS14: v_spacing (visual) - 수직 간격
MS15: pour_total_duration (animation) - 따르기 총 시간
MS16: lift_height (animation) - 들어올림 높이
MS17: tilt_angle (animation) - 기울기 각도
MS18: starting_coins (economy) - 시작 코인
MS19: starting_gems (economy) - 시작 젬
MS20: booster_type_count (gameplay) - 부스터 종류 수
MS21: booster_initial_counts (gameplay) - 부스터 초기 수량
MS22: undo_max_steps (gameplay) - 되돌리기 최대 단계
MS23: star_rating_3star (scoring) - 3성 기준
MS24: star_rating_2star_threshold (scoring) - 2성 기준
MS25: hint_scoring_system (algorithm) - 힌트 점수화 시스템
MS26: blocker_type_count (gameplay) - 블로커 종류 수
MS27: save_prefix (architecture) - 저장 접두사
MS28: pattern_count (architecture) - 디자인 패턴 수
MS29: state_count (architecture) - 게임 상태 수
MS30: pour_mechanic (gameplay) - 따르기 메커니즘
MS31: win_condition (gameplay) - 승리 조건
MS32: empty_bottles_formula (difficulty) - 빈 병 공식""",

            "carmatch": """CM01: cell_size (core_constants) - 셀 크기
CM02: car_types (core_constants) - 자동차 종류 수
CM03: match_count (core_constants) - 매칭 필요 수
CM04: movement_speed (core_constants) - 이동 속도
CM05: model_scale (visual) - 모델 스케일
CM06: y_offset (visual) - Y 오프셋
CM07: holder_max_slots (gameplay) - 홀더 최대 슬롯
CM08: slot_spacing (visual) - 슬롯 간격
CM09: grid_size_progression (difficulty) - 격자 크기 진행
CM10: scoring_formula (scoring) - 점수 공식
CM11: star_thresholds (scoring) - 별 기준
CM12: max_levels (core_constants) - 최대 레벨 수
CM13: car_sets_formula (difficulty) - 자동차 세트 공식
CM14: booster_types (gameplay) - 부스터 종류
CM15: booster_initial_counts (gameplay) - 부스터 초기 수량
CM16: initial_coins (economy) - 초기 코인
CM17: move_history_max (gameplay) - 이동 히스토리 최대
CM18: tunnel_spawn_count (gameplay) - 터널 스폰 수
CM19: tunnel_placement (gameplay) - 터널 배치
CM20: pathfinding_algorithm (algorithm) - 경로탐색 알고리즘
CM21: storage_count (gameplay) - 임시저장소 수
CM22: daily_reward_progression (economy) - 일일보상 진행
CM23: journey_frequency (gameplay) - 여정 보상 빈도
CM24: camera_angle (visual) - 카메라 각도
CM25: base_height_5x5 (visual) - 5x5 기준 높이
CM26: state_count (architecture) - 게임 상태 수
CM27: namespace (architecture) - 네임스페이스
CM28: tap_mechanic (gameplay) - 탭 메커니즘
CM29: fail_condition (gameplay) - 실패 조건
CM30: win_condition (gameplay) - 승리 조건
CM31: pattern_count (architecture) - 디자인 패턴 수
CM32: serialization (architecture) - 직렬화 방식""",
        }
        return params.get(game_key, "")

    # ------------------------------------------------------------------
    # Capture Scripts
    # ------------------------------------------------------------------

    def capture_session(self, ctx: CaptureContext, session_id: int):
        handler = {
            1:  self._cap_playthrough_a,
            2:  self._cap_playthrough_b,
            3:  self._cap_numeric,
            4:  self._cap_timing,
            5:  self._cap_visual,
            6:  self._cap_edge_case,
            7:  self._cap_economy,
            8:  self._cap_algorithm,
            9:  self._cap_state_flow,
            10: self._cap_cross_validation,
        }
        handler[session_id](ctx)

    def _cap_playthrough_a(self, ctx: CaptureContext):
        ctx.dismiss_popups()
        ctx.shot("01_main_menu")
        ctx.tap("play", wait=3)
        ctx.shot("02_level1_board")
        ctx.play_generic(taps=3)
        ctx.shot("03_level1_result")
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.play_generic(taps=4)
        ctx.shot("04_level3_board")
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.play_generic(taps=5)
        ctx.shot("05_level5_result")
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.play_generic(taps=6)
        ctx.shot("06_higher_level")
        ctx.back()
        ctx.tap("popup", wait=2)
        ctx.shot("07_level_select")
        ctx.swipe((400, 800), (400, 200), dur=500, wait=2)
        ctx.shot("08_level_select_scrolled")

    def _cap_playthrough_b(self, ctx: CaptureContext):
        ctx.dismiss_popups()
        ctx.shot("01_main_menu_b")
        ctx.tap("settings", wait=2)
        ctx.shot("02_settings")
        ctx.back()
        ctx.tap("play", wait=3)
        ctx.shot("03_level1_b")
        ctx.play_generic(taps=3)
        ctx.shot("04_level1_result_b")
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.shot("05_level2_b")
        ctx.play_generic(taps=4)
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.play_generic(taps=5)
        ctx.shot("06_level3_result_b")
        ctx.tap("popup", wait=2)
        ctx.shot("07_progression_b")
        ctx.swipe((400, 400), (400, 800), dur=500, wait=2)
        ctx.shot("08_scroll_b")

    def _cap_numeric(self, ctx: CaptureContext):
        ctx.dismiss_popups()
        ctx.tap("play", wait=3)
        ctx.shot("01_level_start_board")
        ctx.play_generic(taps=3)
        ctx.shot("02_perfect_result")
        # Play with 2 mistakes
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.tap((50, 400), wait=0.5)
        ctx.tap((50, 400), wait=0.5)
        ctx.play_generic(taps=4)
        ctx.shot("03_2mistake_result")
        # Play with 5 mistakes
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        for _ in range(5):
            ctx.tap((50, 400), wait=0.3)
        ctx.play_generic(taps=5)
        ctx.shot("04_5mistake_result")
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.shot("05_higher_level_board")
        ctx.play_generic(taps=6)
        ctx.shot("06_higher_level_result")

    def _cap_timing(self, ctx: CaptureContext):
        ctx.dismiss_popups()
        ctx.tap("play", wait=3)
        ctx.shot("01_before_move")
        ctx.tap("center", wait=0.3)
        ctx.shot("02_during_move")
        time.sleep(1)
        ctx.shot("03_after_move")
        ctx.play_generic(taps=4)
        ctx.shot("04_popup_appearing")
        time.sleep(0.5)
        ctx.shot("05_popup_visible")

    def _cap_visual(self, ctx: CaptureContext):
        ctx.dismiss_popups()
        ctx.tap("play", wait=3)
        ctx.shot("01_small_grid_clean")
        time.sleep(1)
        ctx.shot("02_grid_detail")
        ctx.play_generic(taps=4)
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.shot("03_medium_grid")
        ctx.play_generic(taps=5)
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.shot("04_larger_grid")
        ctx.back()
        ctx.shot("05_ui_overlay")
        ctx.tap("popup", wait=2)
        ctx.tap("settings", wait=2)
        ctx.shot("06_settings_ui")

    def _cap_edge_case(self, ctx: CaptureContext):
        ctx.dismiss_popups()
        ctx.tap("play", wait=3)
        bx, by = ctx.c("booster")
        for i in range(5):
            ctx.tap((bx - 200, by), wait=1)
        ctx.shot("01_hints_used")
        ctx.tap("center", wait=0.8)
        for i in range(12):
            ctx.tap("booster", wait=0.5)
        ctx.shot("02_undos_used")
        ctx.back()
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        for _ in range(8):
            ctx.tap("tl", wait=0.3)
            ctx.tap("br", wait=0.3)
        time.sleep(3)
        ctx.shot("03_near_fail")
        ctx.shot("04_fail_state")
        ctx.tap("booster", wait=2)
        ctx.shot("05_booster_shop")
        ctx.tap("popup", wait=2)
        ctx.shot("06_after_fail")

    def _cap_economy(self, ctx: CaptureContext):
        ctx.dismiss_popups()
        ctx.shot("01_initial_coins")
        ctx.tap("play", wait=3)
        ctx.play_generic(taps=3)
        ctx.shot("02_level1_reward")
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.play_generic(taps=4)
        ctx.shot("03_level2_reward")
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.play_generic(taps=5)
        ctx.shot("04_level3_reward")
        ctx.tap("popup", wait=2)
        ctx.tap((200, 145), wait=2)  # shop area
        ctx.shot("05_shop")
        ctx.back()
        ctx.shot("06_coins_after_levels")

    def _cap_algorithm(self, ctx: CaptureContext):
        ctx.dismiss_popups()
        ctx.tap("play", wait=3)
        ctx.shot("01_initial_layout")
        ctx.tap((50, 400), wait=1)
        ctx.tap((750, 400), wait=1)
        ctx.shot("02_blocked_feedback")
        ctx.tap("center", wait=2)
        ctx.tap("tl", wait=2)
        ctx.shot("03_movement_path")
        ctx.back()
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.shot("04_restart_layout_1")
        ctx.back()
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        ctx.shot("05_restart_layout_2")

    def _cap_state_flow(self, ctx: CaptureContext):
        ctx.dismiss_popups()
        ctx.shot("01_main_menu")
        ctx.tap("play", wait=3)
        ctx.shot("02_gameplay")
        ctx.back()
        ctx.shot("03_pause_popup")
        ctx.tap("popup", wait=2)
        ctx.play_generic(taps=5)
        ctx.shot("04_complete_popup")
        ctx.tap("popup", wait=2)
        ctx.tap("settings", wait=2)
        ctx.shot("05_settings")
        ctx.back()
        ctx.tap("play", wait=3)
        for _ in range(6):
            ctx.tap("tl", wait=0.3)
            ctx.tap("br", wait=0.3)
        time.sleep(3)
        ctx.shot("06_fail_popup")

    def _cap_cross_validation(self, ctx: CaptureContext):
        ctx.dismiss_popups()
        ctx.tap("play", wait=3)
        ctx.play_generic(taps=3)
        ctx.shot("01_3star_attempt")
        ctx.tap("popup", wait=2)
        ctx.tap("play", wait=3)
        for _ in range(6):
            ctx.tap((50, 400), wait=0.3)
        ctx.play_generic(taps=5)
        ctx.shot("02_1star_attempt")
        ctx.tap("popup", wait=2)
        ctx.shot("03_progression")
        ctx.tap("play", wait=3)
        ctx.tap("booster", wait=2)
        ctx.shot("04_booster_detail")
        ctx.back()
        ctx.tap("popup", wait=2)
        ctx.swipe((400, 800), (400, 200), dur=500, wait=2)
        ctx.shot("05_later_levels")


# Register
register_genre(PuzzleGenre())
