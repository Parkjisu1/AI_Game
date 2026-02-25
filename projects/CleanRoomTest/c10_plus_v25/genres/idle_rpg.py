"""
Idle RPG Genre Module for C10+ v2.5
=====================================
Covers: Ash N Veil, and future Idle RPG games

Tester Roles (10) — v2 redesigned for Idle RPG:
  1. Full Playthrough A    — Chapter/stage progression, boss mechanics
  2. Full Playthrough B    — UI/menu full mapping, all tabs explored
  3. Numeric Early (v2)    — Early game stats Lv.1~15, base values
  4. Numeric Late  (v2)    — Late game scaling Lv.30+, growth curve regression
  5. Visual + Multi-Res    — UI measurement + 720p/1080p/1440p comparison
  6. Equipment & Enhance   — Gear slots, grades, enhance costs, set effects
  7. Economy & Idle         — Currencies, idle rewards, attendance, shop
  8. Gacha & Pets          — Summon costs, rates, pity, pet system
  9. Skills & Combat       — Skill cooldowns, damage formula, attack speed
 10. Cross-Validation      — Re-confirm weak parameters across all domains
"""

import time
from genres import GenreBase, GameConfig, Mission, MissionPlan, CaptureContext, register_genre
from typing import Dict, List, Tuple


class IdleRPGGenre(GenreBase):

    @property
    def genre_name(self) -> str:
        return "Idle RPG"

    @property
    def genre_key(self) -> str:
        return "idle_rpg"

    # ------------------------------------------------------------------
    # Games
    # ------------------------------------------------------------------

    def get_games(self) -> Dict[str, GameConfig]:
        return {
            "ash_n_veil": GameConfig(
                key="ash_n_veil",
                name="Ash N Veil: Fast Idle Action",
                package="studio.gameberry.anv",
                prefix="ANV",
                # BlueStacks 800x1280 기준 — 실제 설치 후 좌표 재측정 필요
                coords={
                    # 공통
                    "center": (400, 640),
                    "play": (400, 1000),
                    "back": (60, 60),
                    "settings": (720, 60),
                    "popup_close": (400, 900),
                    "popup_x": (650, 200),
                    "popup": (400, 900),
                    # 하단 메뉴바
                    "menu_char": (80, 1230),
                    "menu_skill": (200, 1230),
                    "menu_field": (400, 1230),
                    "menu_summon": (560, 1230),
                    "menu_shop": (680, 1230),
                    # 전투 화면
                    "joystick_area": (150, 900),
                    "skill_1": (550, 950),
                    "skill_2": (630, 870),
                    "skill_3": (710, 950),
                    "auto_btn": (750, 800),
                    # 장비 화면
                    "gear_slot_1": (200, 400),
                    "gear_slot_2": (200, 500),
                    "gear_slot_3": (200, 600),
                    "gear_enhance": (400, 1100),
                    "gear_tab_weapon": (150, 300),
                    "gear_tab_armor": (300, 300),
                    "gear_tab_acc": (450, 300),
                    # 소환 화면
                    "summon_1x": (250, 900),
                    "summon_10x": (550, 900),
                    "summon_tab_hero": (200, 250),
                    "summon_tab_gear": (400, 250),
                    "summon_tab_pet": (600, 250),
                    # 스크롤
                    "scroll_up": (400, 300),
                    "scroll_down": (400, 900),
                    # 상점
                    "shop_tab_1": (150, 300),
                    "shop_tab_2": (300, 300),
                    "shop_item_1": (200, 500),
                },
                ocr_regions={
                    # (x, y, width, height) for pytesseract crop
                    "player_level": (20, 20, 100, 30),
                    "hp_bar": (50, 60, 200, 20),
                    "gold": (600, 20, 150, 30),
                    "gem": (600, 50, 150, 30),
                    "atk_stat": (100, 400, 120, 25),
                    "hp_stat": (100, 430, 120, 25),
                    "stage_number": (300, 50, 200, 30),
                },
                apk_path=None,  # Set after downloading APK
                wiki_keywords=[
                    "Ash N Veil guide",
                    "Ash N Veil gacha rates",
                    "Ash N Veil tier list",
                    "Ash N Veil idle rewards",
                    "Ash N Veil equipment upgrade",
                ],
            ),
        }

    # ------------------------------------------------------------------
    # Screen Types (for Smart Classifier)
    # ------------------------------------------------------------------

    def get_screen_types(self) -> Dict[str, str]:
        base = super().get_screen_types()
        base.update({
            # Core screens
            "stage_select": "Stage/chapter selection screen",
            # Menu screens
            "menu_character": "Character stats/info screen",
            "menu_skill": "Skill list/upgrade screen",
            "menu_inventory": "Inventory/bag screen",
            "menu_summon": "Gacha/summon main screen",
            "menu_shop": "In-game shop screen",
            # Sub-screens
            "equipment_detail": "Equipment detail/stat view",
            "equipment_enhance": "Equipment enhancement screen",
            "skill_detail": "Individual skill detail popup",
            "summon_rates": "Gacha probability table",
            "summon_result": "Summon result display",
            # System
            "quest_list": "Quest/mission list screen",
            # Additional popups
            "black_screen": "Transition black screen",
        })
        return base

    # ------------------------------------------------------------------
    # Mission Targets (for Smart Navigator)
    # ------------------------------------------------------------------

    def get_screen_equivalences(self) -> Dict[str, str]:
        """Idle RPG screen equivalences.

        In idle RPGs, 'battle' is just the field/lobby with auto-combat active.
        The character fights monsters on the same map screen automatically.
        'loading' is a transient screen that auto-transitions.
        """
        return {
            "battle": "lobby",      # battle is lobby with auto-combat
            "loading": "lobby",     # loading auto-transitions to lobby
        }

    def get_mission_targets(self) -> Dict[int, "MissionPlan"]:
        # MissionRouter auto-filters targets not in the nav_graph.
        # Available graph nodes (typical idle RPG after recording):
        #   lobby, battle, menu_shop, menu_character, menu_inventory,
        #   skill_detail, quest_list, equipment_enhance, equipment_detail, settings
        return {
            1: MissionPlan(
                targets=["lobby", "battle", "menu_character", "menu_inventory"],
                required_screenshots={"lobby": 1, "battle": 2, "menu_character": 1, "menu_inventory": 1},
                max_time_minutes=5.0,
                strategy="sequential",
            ),
            2: MissionPlan(
                targets=["lobby", "menu_character", "menu_inventory",
                         "menu_shop", "skill_detail", "quest_list", "equipment_enhance", "settings"],
                required_screenshots={
                    "lobby": 1, "menu_character": 1, "menu_inventory": 1,
                    "menu_shop": 1, "skill_detail": 1, "quest_list": 1,
                    "equipment_enhance": 1, "settings": 1,
                },
                max_time_minutes=5.0,
                strategy="breadth_first",
            ),
            3: MissionPlan(
                targets=["menu_character", "equipment_detail", "skill_detail", "menu_shop"],
                required_screenshots={
                    "menu_character": 2, "equipment_detail": 1,
                    "skill_detail": 1, "menu_shop": 1,
                },
                max_time_minutes=5.0,
                strategy="data_focused",
            ),
            4: MissionPlan(
                targets=["menu_character", "equipment_enhance", "battle", "equipment_detail"],
                required_screenshots={
                    "menu_character": 2, "equipment_enhance": 1,
                    "battle": 1, "equipment_detail": 1,
                },
                max_time_minutes=5.0,
                strategy="data_focused",
            ),
            5: MissionPlan(
                targets=["lobby", "battle", "menu_character"],
                required_screenshots={"lobby": 2, "battle": 2, "menu_character": 2},
                max_time_minutes=5.0,
                strategy="visual_sweep",
            ),
            6: MissionPlan(
                targets=["equipment_detail", "equipment_enhance"],
                required_screenshots={"equipment_detail": 3, "equipment_enhance": 3},
                max_time_minutes=5.0,
                strategy="depth_first",
            ),
            7: MissionPlan(
                targets=["lobby", "menu_shop", "quest_list", "menu_inventory"],
                required_screenshots={
                    "lobby": 1, "menu_shop": 2,
                    "quest_list": 1, "menu_inventory": 1,
                },
                max_time_minutes=5.0,
                strategy="economy_track",
            ),
            8: MissionPlan(
                targets=["menu_shop", "menu_inventory", "settings"],
                required_screenshots={"menu_shop": 2, "menu_inventory": 1, "settings": 1},
                max_time_minutes=5.0,
                strategy="depth_first",
            ),
            9: MissionPlan(
                targets=["skill_detail", "battle", "menu_character"],
                required_screenshots={"skill_detail": 2, "battle": 4, "menu_character": 1},
                max_time_minutes=5.0,
                strategy="combat_focused",
            ),
            10: MissionPlan(
                targets=["lobby", "menu_character", "menu_inventory",
                         "menu_shop", "equipment_detail", "skill_detail"],
                required_screenshots={
                    "lobby": 1, "menu_character": 1, "menu_inventory": 1,
                    "menu_shop": 1, "equipment_detail": 1, "skill_detail": 1,
                },
                max_time_minutes=5.0,
                strategy="breadth_first",
            ),
        }

    # ------------------------------------------------------------------
    # Missions (10 AI Testers — Idle RPG v2)
    # ------------------------------------------------------------------

    def get_missions(self) -> Dict[int, Mission]:
        return {
            1:  Mission(1,  "Full Playthrough A",       "gameplay",     "챕터/스테이지 진행, 보스 메커니즘, 자동전투 관찰"),
            2:  Mission(2,  "Full Playthrough B",       "gameplay",     "UI/메뉴 전수 매핑, 모든 탭/서브메뉴 탐색"),
            3:  Mission(3,  "Numeric Early (Lv.1~15)",  "numeric",      "초반 스탯 수집: HP/ATK/DEF 기본값, 레벨업 증가량, 초기 비용", flex=True),
            4:  Mission(4,  "Numeric Late (Lv.30+)",    "numeric",      "후반 스케일링: 성장 곡선 변곡점, 비선형 공식 역산", flex=True),
            5:  Mission(5,  "Visual + Multi-Resolution", "visual",      "UI 정밀 측정 + 720p/1080p/1440p 다해상도 비교"),
            6:  Mission(6,  "Equipment & Enhancement",  "equipment",    "장비 슬롯/등급/강화 비용/세트 효과 전수 조사", flex=True),
            7:  Mission(7,  "Economy & Idle Rewards",   "economy",      "재화 종류/방치 보상/출석/일퀘/상점 가격표", flex=True),
            8:  Mission(8,  "Gacha & Pet System",       "gacha",        "소환 비용/등급 확률/천장/펫 시스템 전수 조사", flex=True),
            9:  Mission(9,  "Skills & Combat Algorithm","combat",       "스킬 쿨다운/데미지 공식/공격 속도/속성 상성", flex=True),
            10: Mission(10, "Cross-Validation",         "cross_validation", "전 영역 약점 파라미터 재확인, 수치 교차 검증"),
        }

    # ------------------------------------------------------------------
    # Domain Weights (Idle RPG specific)
    # ------------------------------------------------------------------

    def get_domain_weights(self) -> Dict[str, List[int]]:
        return {
            "gameplay":     [1, 2],
            "numeric":      [3, 4],     # v2: 2명이 수치 담당
            "visual":       [5],
            "equipment":    [6],
            "economy":      [7],
            "gacha":        [8],
            "combat":       [9],
            "cross_validation": [10],
        }

    # ------------------------------------------------------------------
    # Aggregation (Idle RPG specific sections)
    # ------------------------------------------------------------------

    def get_aggregation_sections(self) -> List[str]:
        return [
            "게임 정체성 (장르, 세계관, 아트)",
            "UI 구성 (메뉴 구조, 하단바, 팝업)",
            "전투 메커니즘 (자동/수동, 스킬, 속성)",
            "캐릭터 성장 (레벨업, 스탯, 각성)",
            "장비 시스템 (슬롯, 등급, 강화, 세트)",
            "가챠/소환 시스템 (비용, 확률, 천장)",
            "펫/동료 시스템",
            "경제/재화 (골드, 젬, 방치보상, 출석)",
            "스테이지/콘텐츠 진행 (챕터, 보스, 던전)",
            "스킬 시스템 (쿨다운, 버프, 시너지)",
            "시각 측정 (UI 크기, 해상도, 레이아웃)",
            "초반 수치 vs 후반 수치 (성장 곡선 회귀분석)",
        ]

    def get_aggregation_rules(self) -> str:
        return """- Idle RPG 특화 규칙:
  - 수치 전문가 3(초반)과 4(후반)의 데이터를 병합하여 성장 곡선 회귀분석 실시
  - 가챠 확률은 게임 내 공시 데이터를 최우선 채택
  - 방치 보상은 전문가 7의 시간당 수치를 정밀 확인
  - 데미지 공식은 전문가 9의 전투 관찰에서 역산 (ATK, DEF, 크리, 속성 반영)
  - 장비 강화 비용은 전문가 6의 전수 조사 데이터 채택"""

    # ------------------------------------------------------------------
    # Vision Prompts (Idle RPG 10 sessions)
    # ------------------------------------------------------------------

    def get_vision_prompt(self, session_id: int, game_name: str) -> str:
        prompts = {
            1: f"""{game_name} - 전문가 1: 챕터 진행 플레이스루

당신은 Idle RPG 구조 분석 전문가입니다. 스크린샷은 게임 시작부터 순서대로 진행한 기록입니다.

분석 항목:
1. 스테이지/챕터 구조: 총 몇 챕터, 챕터당 몇 스테이지?
2. 보스전 구조: 몇 스테이지마다 보스? 보스 특수 메커니즘?
3. 자동전투 해금 시점: 어느 레벨/스테이지에서 자동전투 가능?
4. 난이도 모드: 노말/하드/헬 등 난이도 분기?
5. 전투 기본 흐름: 웨이브 수, 몬스터 출현 패턴
6. 클리어/실패 조건, 별점 시스템 유무
7. 튜토리얼 구성: 몇 단계? 어떤 시스템을 가르치나?

규칙: 스테이지 번호, 몬스터 수, 보스 HP 등 모든 숫자를 테이블로 정리.""",

            2: f"""{game_name} - 전문가 2: UI/메뉴 전수 매핑

당신은 모바일 게임 UI 분석 전문가입니다. 모든 메뉴와 화면을 매핑하세요.

필수 매핑:
1. 하단 메뉴바: 각 탭 이름과 기능 (캐릭터/스킬/필드/소환/상점 등)
2. 각 탭의 서브메뉴: 모든 하위 화면 목록
3. 설정 화면: 그래픽/사운드/계정/알림 등 모든 옵션
4. 팝업 목록: 모든 팝업 종류와 출현 조건
5. 알림 아이콘: 빨간 점(dot)이 표시되는 조건
6. 메인 HUD: 상단 표시 정보 (레벨, 닉네임, 재화, 스테이지)
7. 버튼 레이아웃: 각 화면의 주요 버튼 위치와 기능

출력: 화면별 트리 구조로 정리. 스크린샷 번호 참조.""",

            3: f"""{game_name} - 전문가 3: 초반 수치 수집 (Lv.1~15)

당신은 게임 밸런스 수치 분석 전문가입니다. 초반 구간의 정확한 수치를 수집하세요.

필수 수집:
1. 캐릭터 기본 스탯 (Lv.1): HP, ATK, DEF, SPD 각각의 정확한 숫자
2. 레벨업 증가량: Lv.1→2, 2→3, ... 15까지 각 레벨의 스탯 변화
3. 레벨업 비용: 각 레벨업에 필요한 골드/경험치
4. 장비 초기값: 첫 장비의 스탯, 강화 1회 비용
5. 스킬 초기값: 첫 스킬의 데미지/쿨다운
6. 초기 재화량: 시작 시 골드, 젬, 기타 재화

출력 형식:
| Lv | HP | ATK | DEF | EXP필요 | 골드필요 |
|----|-----|-----|-----|---------|---------|
| 1  | ?? | ??  | ??  | ??      | ??      |
| 2  | ?? | ??  | ??  | ??      | ??      |
...
반드시 정확한 숫자만 기록. 모르면 "관찰불가" 표시.""",

            4: f"""{game_name} - 전문가 4: 후반 스케일링 (Lv.30+)

당신은 게임 성장 곡선 분석 전문가입니다. 후반 구간의 스케일링 패턴을 분석하세요.

필수 분석:
1. Lv.30+ 스탯: HP, ATK, DEF의 후반 수치 (5레벨 간격으로)
2. 성장 공식 추론: 선형? 지수? 로그? 구간별 다른 공식?
3. 강화 비용 스케일링: 초반 vs 후반 비용 비율
4. 경험치 곡선: 레벨업에 필요한 EXP가 어떻게 증가하는지
5. 몬스터 스탯 스케일링: 스테이지별 몬스터 HP/ATK 변화
6. 골드 획득 스케일링: 후반 스테이지의 골드 보상량

회귀분석 시도:
- 데이터 포인트 3개 이상이면 공식 역산 시도
- 예: HP = a + b×Lv (선형), HP = a × b^Lv (지수), HP = a × Lv^b (거듭제곱)
- R² 값을 추정하여 모델 적합도 표시

출력: 레벨별 데이터 테이블 + 추정 공식.""",

            5: f"""{game_name} - 전문가 5: 시각 측정 + 다해상도 비교

당신은 UI/UX 정밀 측정 전문가입니다.

기본 측정 (현재 해상도):
1. 화면 해상도: 전체 화면 크기
2. HUD 영역: 상단바 높이, 하단 메뉴바 높이 (px)
3. 전투 영역: 사용 가능한 게임플레이 영역 크기
4. 버튼 크기: 주요 버튼의 가로×세로 (px)
5. 폰트 크기: HP/ATK 등 주요 텍스트 크기 추정
6. 캐릭터 크기: 플레이어/몬스터 스프라이트 크기
7. UI 여백: 요소 간 간격

다해상도 비교 (v2 추가):
- 동일 화면의 720p/1080p/1440p 캡처가 있으면:
  - 각 해상도에서 동일 UI 요소의 px 크기 비교
  - 스케일링 비율 계산 → 기준 해상도(reference resolution) 역산
  - 예: 1080p에서 버튼 120px, 720p에서 80px → 비율 1.5 → 기준 720p

출력: 모든 측정값을 px 단위로. 비율은 소수점 2자리.""",

            6: f"""{game_name} - 전문가 6: 장비/강화 전수 조사

당신은 RPG 장비 시스템 분석 전문가입니다. 장비 관련 모든 것을 조사하세요.

필수 조사:
1. 장비 슬롯: 총 몇 개? 각 슬롯 이름 (무기, 갑옷, 투구, 장갑, 신발, 반지 등)
2. 장비 등급: 등급 체계 (일반/고급/희귀/영웅/전설 등), 각 등급 색상
3. 장비 스탯: 등급별 기본 스탯 범위
4. 강화 시스템:
   - 강화 최대 레벨
   - 각 강화 레벨의 비용 (골드/재료)
   - 강화 성공률 (있다면)
   - 강화 실패 시 패널티
5. 세트 효과: 세트 장비 구성과 세트 보너스
6. 장비 획득 경로: 가챠/드롭/제작/상점 등
7. 분해/매각: 불필요 장비 처리 시 획득 재화

출력: 등급별, 슬롯별 데이터 테이블. 강화 비용 테이블.""",

            7: f"""{game_name} - 전문가 7: 경제/방치 보상 전담

당신은 모바일 게임 경제 분석 전문가입니다.

필수 추적:
1. 재화 종류: 모든 재화 이름, 아이콘, 용도
2. 초기 재화: 게임 시작 시 보유량
3. 주요 수입원:
   - 스테이지 클리어 보상 (골드/EXP/장비)
   - 방치(Idle) 보상: 분당/시간당 획득량, 최대 축적 시간
   - 출석 보상: 7일/30일 패턴
   - 일일 퀘스트: 보상 종류와 양
   - 업적 보상
4. 주요 지출처:
   - 레벨업 비용
   - 장비 강화 비용
   - 스킬 업그레이드 비용
   - 가챠 비용
5. 상점: 모든 상품과 가격표
6. VIP/월정액: 있다면 혜택 상세
7. 광고: 보상형 광고 빈도와 보상량

출력: 수입/지출 테이블. 방치 보상 계산식.""",

            8: f"""{game_name} - 전문가 8: 가챠/펫 시스템 전수 조사

당신은 가챠 시스템 분석 전문가입니다.

필수 조사:
1. 소환 종류: 캐릭터 소환, 장비 소환, 펫 소환 등 각 카테고리
2. 소환 비용: 1회/10연차 비용 (젬/티켓), 각 카테고리별
3. 등급 확률: 게임 내 확률표가 표시되면 정확히 기록
   - SSR/SR/R/N 각 등급의 확률 (%)
4. 천장(Pity) 시스템: 몇 회 소환 시 확정 등급? 표시되는가?
5. 펫 시스템:
   - 펫 등급/종류
   - 펫 스킬/효과
   - 펫 성장 방식
6. 중복 처리: 이미 보유한 캐릭터/펫 중복 소환 시 보상
7. 무료 소환: 일일 무료 소환 횟수, 쿨다운

출력: 가챠 확률표, 비용표, 천장 시스템 정리.""",

            9: f"""{game_name} - 전문가 9: 스킬/전투 알고리즘 분석

당신은 전투 시스템 분석 전문가입니다.

필수 분석:
1. 스킬 목록: 모든 액티브/패시브 스킬, 각 스킬의 효과
2. 쿨다운: 각 스킬의 쿨다운 시간 (초)
3. 데미지 공식 추론:
   - 기본 공격 데미지 = ATK × ? - DEF × ?
   - 크리티컬: 확률, 배율
   - 속성 상성: 유리/불리 배율
4. 공격 속도: 자동공격 주기 (초)
5. 버프/디버프: 종류, 지속시간, 중첩 가능 여부
6. 전투 AI:
   - 자동전투 시 스킬 사용 패턴 (쿨다운 순? 우선순위?)
   - 타겟 선택 로직 (가까운 적? 낮은 HP?)
7. 전투 종료 조건: 시간제한? HP 0? 웨이브 완료?

출력: 스킬 테이블, 데미지 공식 추정, 전투 AI 패턴.""",

            10: f"""{game_name} - 전문가 10: 교차검증 (전 영역)

당신은 데이터 검증 전문가입니다. 다른 9명의 전문가 관찰에서 약점이 될 수 있는 항목을 재확인하세요.

집중 확인:
1. 성장 공식: 전문가 3(초반)과 4(후반)의 데이터가 일관되는지
2. 가챠 확률: 공시된 확률 vs 실제 관찰 (가능한 범위에서)
3. 방치 보상: 표시된 시간당 보상 vs 실제 축적량
4. 장비 강화: 비용 테이블의 규칙성 확인
5. 스킬 쿨다운: 실제 전투에서 측정 가능한 쿨다운
6. UI 수치: 표시된 HP/ATK와 전투에서 관찰되는 수치 일치 여부

규칙: 불일치 발견 시 어떤 값이 맞는지 판단 근거 제시.""",
        }
        return prompts[session_id]

    # ------------------------------------------------------------------
    # Parameters (32, Idle RPG specific)
    # ------------------------------------------------------------------

    def get_parameters(self, game_key: str) -> str:
        params = {
            "ash_n_veil": """ANV01: max_chapter (progression) - 최대 챕터 수
ANV02: stages_per_chapter (progression) - 챕터당 스테이지 수
ANV03: boss_frequency (progression) - 보스 등장 빈도 (몇 스테이지마다)
ANV04: auto_battle_unlock (progression) - 자동전투 해금 조건
ANV05: difficulty_modes (progression) - 난이도 모드 수
ANV06: base_hp_lv1 (growth) - Lv.1 기본 HP
ANV07: base_atk_lv1 (growth) - Lv.1 기본 ATK
ANV08: hp_growth_formula (growth) - HP 성장 공식 (선형/지수/구간)
ANV09: atk_growth_formula (growth) - ATK 성장 공식
ANV10: exp_curve_formula (growth) - EXP 곡선 공식
ANV11: gear_slot_count (equipment) - 장비 슬롯 수
ANV12: gear_grade_count (equipment) - 장비 등급 수
ANV13: enhance_max_level (equipment) - 강화 최대 레벨
ANV14: enhance_cost_formula (equipment) - 강화 비용 공식
ANV15: active_skill_count (combat) - 액티브 스킬 수
ANV16: skill_cooldown_range (combat) - 스킬 쿨다운 범위 (초)
ANV17: auto_attack_speed (combat) - 자동공격 주기 (초)
ANV18: damage_formula (combat) - 데미지 공식 (ATK/DEF 관계)
ANV19: critical_rate (combat) - 크리티컬 확률 (%)
ANV20: critical_multiplier (combat) - 크리티컬 배율
ANV21: gacha_cost_1x (gacha) - 1회 소환 비용
ANV22: gacha_cost_10x (gacha) - 10연차 소환 비용
ANV23: gacha_ssr_rate (gacha) - SSR 확률 (%)
ANV24: gacha_pity_count (gacha) - 천장 횟수
ANV25: currency_types (economy) - 재화 종류 수
ANV26: idle_gold_per_min (economy) - 방치 골드/분
ANV27: idle_max_accumulation (economy) - 방치 최대 축적 시간
ANV28: attendance_days (economy) - 출석 보상 주기 (일)
ANV29: daily_quest_count (economy) - 일일 퀘스트 수
ANV30: pet_system_exists (system) - 펫 시스템 유무
ANV31: ui_reference_resolution (visual) - UI 기준 해상도
ANV32: state_count (architecture) - 게임 상태 수 (메인/전투/로비 등)""",
        }
        return params.get(game_key, "")

    # ------------------------------------------------------------------
    # Capture Scripts (Idle RPG 10 sessions)
    # ------------------------------------------------------------------

    def capture_session(self, ctx: CaptureContext, session_id: int):
        handler = {
            1:  self._cap_chapter_progress,
            2:  self._cap_ui_mapping,
            3:  self._cap_numeric_early,
            4:  self._cap_numeric_late,
            5:  self._cap_visual_multires,
            6:  self._cap_equipment,
            7:  self._cap_economy_idle,
            8:  self._cap_gacha_pet,
            9:  self._cap_combat_skills,
            10: self._cap_cross_validation,
        }
        handler[session_id](ctx)

    def _cap_chapter_progress(self, ctx: CaptureContext):
        """Session 1: Chapter/stage progression."""
        ctx.dismiss_popups()
        ctx.shot("01_main_lobby")
        # Start battle
        ctx.tap("play", wait=5)
        ctx.shot("02_battle_start")
        time.sleep(10)  # Wait for auto-combat
        ctx.shot("03_battle_mid")
        time.sleep(10)
        ctx.shot("04_battle_result")
        ctx.tap("popup_close", wait=3)
        # Next stages
        ctx.tap("play", wait=5)
        time.sleep(15)
        ctx.shot("05_stage_clear")
        ctx.tap("popup_close", wait=3)
        ctx.tap("play", wait=5)
        time.sleep(15)
        ctx.shot("06_later_stage")
        ctx.tap("popup_close", wait=3)
        # Check stage select / chapter list
        ctx.back()
        ctx.shot("07_stage_select")
        ctx.swipe("scroll_down", "scroll_up", dur=500, wait=2)
        ctx.shot("08_chapter_list")

    def _cap_ui_mapping(self, ctx: CaptureContext):
        """Session 2: Full UI/menu mapping."""
        ctx.dismiss_popups()
        ctx.shot("01_main_hud")
        # Bottom menu tabs
        ctx.tap("menu_char", wait=2)
        ctx.shot("02_character_tab")
        ctx.tap("menu_skill", wait=2)
        ctx.shot("03_skill_tab")
        ctx.tap("menu_field", wait=2)
        ctx.shot("04_field_tab")
        ctx.tap("menu_summon", wait=2)
        ctx.shot("05_summon_tab")
        ctx.tap("menu_shop", wait=2)
        ctx.shot("06_shop_tab")
        # Settings
        ctx.tap("settings", wait=2)
        ctx.shot("07_settings")
        ctx.back()
        # Any remaining menus
        ctx.tap("menu_char", wait=2)
        ctx.swipe("scroll_down", "scroll_up", dur=500, wait=2)
        ctx.shot("08_char_scroll")

    def _cap_numeric_early(self, ctx: CaptureContext):
        """Session 3: Early game numeric collection (Lv.1~15)."""
        ctx.dismiss_popups()
        # Character stats screen
        ctx.tap("menu_char", wait=2)
        ctx.shot("01_char_stats_lv1")
        # Level up a few times and record
        ctx.tap("play", wait=5)
        time.sleep(10)
        ctx.tap("popup_close", wait=2)
        ctx.tap("menu_char", wait=2)
        ctx.shot("02_char_stats_after_battle")
        # Gear stats
        ctx.tap("gear_slot_1", wait=2)
        ctx.shot("03_gear_detail")
        ctx.back()
        # Skill details
        ctx.tap("menu_skill", wait=2)
        ctx.shot("04_skill_list")
        ctx.tap("skill_1", wait=2)
        ctx.shot("05_skill_detail")
        ctx.back()
        # Economy snapshot
        ctx.tap("menu_shop", wait=2)
        ctx.shot("06_shop_prices")

    def _cap_numeric_late(self, ctx: CaptureContext):
        """Session 4: Late game scaling (Lv.30+).
        Note: Requires game progressed to Lv.30+.
        """
        ctx.dismiss_popups()
        ctx.tap("menu_char", wait=2)
        ctx.shot("01_char_stats_high_level")
        # Gear at high level
        ctx.tap("gear_slot_1", wait=2)
        ctx.shot("02_gear_high_level")
        ctx.back()
        # Enhancement cost
        ctx.tap("gear_slot_1", wait=2)
        ctx.tap("gear_enhance", wait=2)
        ctx.shot("03_enhance_cost_high")
        ctx.back()
        ctx.back()
        # Battle damage numbers at high level
        ctx.tap("menu_field", wait=2)
        ctx.tap("play", wait=5)
        time.sleep(8)
        ctx.shot("04_battle_damage_high")
        time.sleep(8)
        ctx.shot("05_battle_damage_high_2")
        ctx.tap("popup_close", wait=2)
        # EXP requirement
        ctx.tap("menu_char", wait=2)
        ctx.shot("06_exp_bar_high_level")

    def _cap_visual_multires(self, ctx: CaptureContext):
        """Session 5: Visual measurement + multi-resolution comparison."""
        from core import change_resolution, reset_resolution

        ctx.dismiss_popups()
        # Default resolution capture
        ctx.shot("01_default_res_lobby")
        ctx.tap("play", wait=5)
        time.sleep(5)
        ctx.shot("02_default_res_battle")
        ctx.back()
        ctx.tap("popup_close", wait=2)

        # Multi-resolution captures (720p, 1080p, 1440p)
        resolutions = [
            ("720p", 720, 1280, 240),
            ("1080p", 1080, 1920, 360),
            ("1440p", 1440, 2560, 480),
        ]
        for label, w, h, dpi in resolutions:
            try:
                change_resolution(w, h, dpi)
                time.sleep(3)
                ctx.shot(f"03_lobby_{label}")
            except Exception as e:
                pass  # Resolution change may fail on some emulators

        # Reset to default
        try:
            reset_resolution()
        except Exception:
            pass
        time.sleep(3)

        # UI detail shots
        ctx.tap("menu_char", wait=2)
        ctx.shot("04_char_ui_detail")
        ctx.tap("menu_shop", wait=2)
        ctx.shot("05_shop_ui_detail")

    def _cap_equipment(self, ctx: CaptureContext):
        """Session 6: Equipment & enhancement full survey."""
        ctx.dismiss_popups()
        ctx.tap("menu_char", wait=2)
        # All gear slots
        ctx.shot("01_gear_overview")
        ctx.tap("gear_slot_1", wait=2)
        ctx.shot("02_weapon_detail")
        ctx.back()
        ctx.tap("gear_slot_2", wait=2)
        ctx.shot("03_armor_detail")
        ctx.back()
        ctx.tap("gear_slot_3", wait=2)
        ctx.shot("04_accessory_detail")
        ctx.back()
        # Enhancement
        ctx.tap("gear_slot_1", wait=2)
        ctx.tap("gear_enhance", wait=2)
        ctx.shot("05_enhance_screen")
        # Try multiple enhance levels
        ctx.tap("gear_enhance", wait=1)
        ctx.shot("06_enhance_level2_cost")
        ctx.tap("gear_enhance", wait=1)
        ctx.shot("07_enhance_level3_cost")
        ctx.back()
        # Gear tabs
        ctx.tap("gear_tab_weapon", wait=2)
        ctx.shot("08_gear_list")

    def _cap_economy_idle(self, ctx: CaptureContext):
        """Session 7: Economy, idle rewards, shop."""
        ctx.dismiss_popups()
        ctx.shot("01_initial_currencies")
        # Idle reward popup (if available)
        ctx.tap("center", wait=2)
        ctx.shot("02_idle_reward_popup")
        ctx.tap("popup_close", wait=2)
        # Shop
        ctx.tap("menu_shop", wait=2)
        ctx.shot("03_shop_main")
        ctx.tap("shop_tab_1", wait=2)
        ctx.shot("04_shop_tab1")
        ctx.tap("shop_tab_2", wait=2)
        ctx.shot("05_shop_tab2")
        ctx.back()
        # Daily quest
        ctx.tap("menu_field", wait=2)
        ctx.shot("06_quest_list")
        # Battle reward
        ctx.tap("play", wait=5)
        time.sleep(12)
        ctx.shot("07_battle_reward")
        ctx.tap("popup_close", wait=2)
        ctx.shot("08_currencies_after")

    def _cap_gacha_pet(self, ctx: CaptureContext):
        """Session 8: Gacha system & pet system survey."""
        ctx.dismiss_popups()
        ctx.tap("menu_summon", wait=2)
        ctx.shot("01_summon_main")
        # Hero summon
        ctx.tap("summon_tab_hero", wait=2)
        ctx.shot("02_hero_summon")
        # Check rates (usually a small button)
        ctx.tap((700, 250), wait=2)  # "확률 보기" button area
        ctx.shot("03_summon_rates")
        ctx.back()
        # Gear summon
        ctx.tap("summon_tab_gear", wait=2)
        ctx.shot("04_gear_summon")
        # Pet tab
        ctx.tap("summon_tab_pet", wait=2)
        ctx.shot("05_pet_system")
        # Try 1x summon (if free available)
        ctx.tap("summon_1x", wait=3)
        ctx.shot("06_summon_result")
        ctx.tap("popup_close", wait=2)
        # Pity counter (if visible)
        ctx.shot("07_pity_counter")

    def _cap_combat_skills(self, ctx: CaptureContext):
        """Session 9: Skills & combat algorithm analysis."""
        ctx.dismiss_popups()
        # Skill list
        ctx.tap("menu_skill", wait=2)
        ctx.shot("01_skill_list")
        ctx.tap((200, 450), wait=2)  # First skill detail
        ctx.shot("02_skill_1_detail")
        ctx.back()
        ctx.tap((200, 550), wait=2)  # Second skill
        ctx.shot("03_skill_2_detail")
        ctx.back()
        # Enter battle, watch combat
        ctx.tap("menu_field", wait=2)
        ctx.tap("play", wait=5)
        # Capture combat sequence rapidly
        for i in range(4):
            time.sleep(3)
            ctx.shot(f"0{4+i}_combat_frame_{i+1}")
        ctx.tap("popup_close", wait=2)
        # Auto-battle toggle
        ctx.tap("auto_btn", wait=2)
        ctx.shot("08_auto_battle")

    def _cap_cross_validation(self, ctx: CaptureContext):
        """Session 10: Cross-validate weak parameters."""
        ctx.dismiss_popups()
        # Re-check stats
        ctx.tap("menu_char", wait=2)
        ctx.shot("01_stats_verify")
        # Re-check gacha rates
        ctx.tap("menu_summon", wait=2)
        ctx.tap((700, 250), wait=2)
        ctx.shot("02_rates_verify")
        ctx.back()
        # Re-check idle reward
        ctx.tap("menu_field", wait=2)
        ctx.shot("03_idle_verify")
        # Re-check gear enhancement
        ctx.tap("menu_char", wait=2)
        ctx.tap("gear_slot_1", wait=2)
        ctx.tap("gear_enhance", wait=2)
        ctx.shot("04_enhance_verify")
        ctx.back()
        ctx.back()
        # Battle for damage verification
        ctx.tap("menu_field", wait=2)
        ctx.tap("play", wait=5)
        time.sleep(10)
        ctx.shot("05_damage_verify")


# Register
register_genre(IdleRPGGenre())
