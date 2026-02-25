"""
Merge Genre Module for C10+ v2.5 (Template)
=============================================
Covers: Merge-type games (Merge Dragons, Merge Magic, etc.)

Tester Roles (10) — Merge-specific flex roles:
  1. Full Playthrough A    — Quest/order progression, merge chains
  2. Full Playthrough B    — UI/menu mapping, all features explored
  3. Numeric Collection    — Merge chain lengths, XP values, coin rates
  4. Merge Chain Analysis  — Chain efficiency, max merge levels, discovery tree
  5. Visual Measurement    — Board size, tile size, UI layout
  6. Board Management      — Board capacity, bubbling, storage
  7. Economy Tracking      — Coins, gems, energy, chalices
  8. Orders & Events       — Quest rewards, event mechanics, camp quests
  9. Production Chains     — Spawner rates, harvest cycles, cloud keys
 10. Cross-Validation      — Verify merge chain data, economy rates

STATUS: Template — add games and complete capture scripts when needed.
"""

import time
from genres import GenreBase, GameConfig, Mission, CaptureContext, register_genre
from typing import Dict, List, Tuple


class MergeGenre(GenreBase):

    @property
    def genre_name(self) -> str:
        return "Merge"

    @property
    def genre_key(self) -> str:
        return "merge"

    def get_games(self) -> Dict[str, GameConfig]:
        # Add games here when analyzing merge games
        return {}

    def get_missions(self) -> Dict[int, Mission]:
        return {
            1:  Mission(1,  "Full Playthrough A",       "gameplay",     "퀘스트 진행, 머지 체인, 오더 완료 과정"),
            2:  Mission(2,  "Full Playthrough B",       "gameplay",     "UI/메뉴 전수 매핑, 모든 기능 탐색"),
            3:  Mission(3,  "Numeric Collection",       "numeric",      "머지 체인 길이, XP, 코인 획득량 수집", flex=True),
            4:  Mission(4,  "Merge Chain Analysis",     "merge_chain",  "체인 효율, 최대 머지 레벨, 발견 트리", flex=True),
            5:  Mission(5,  "Visual Measurement",       "visual",       "보드 크기, 타일 크기, UI 레이아웃 측정"),
            6:  Mission(6,  "Board Management",         "board",        "보드 용량, 버블링, 저장소, 잠긴 영역", flex=True),
            7:  Mission(7,  "Economy Tracking",         "economy",      "코인/젬/에너지/성배 추적, 상점 가격", flex=True),
            8:  Mission(8,  "Orders & Events",          "quest",        "퀘스트 보상, 이벤트 구조, 캠프 퀘스트", flex=True),
            9:  Mission(9,  "Production Chains",        "production",   "스포너 주기, 수확 사이클, 클라우드 키", flex=True),
            10: Mission(10, "Cross-Validation",         "cross_validation", "머지 체인 데이터, 경제 수치 교차 검증"),
        }

    def get_domain_weights(self) -> Dict[str, List[int]]:
        return {
            "gameplay":     [1, 2],
            "numeric":      [3],
            "merge_chain":  [4],
            "visual":       [5],
            "board":        [6],
            "economy":      [7],
            "quest":        [8],
            "production":   [9],
            "cross_validation": [10],
        }

    def get_aggregation_sections(self) -> List[str]:
        return [
            "게임 정체성", "UI 구성", "머지 메커니즘 (체인/레벨/발견)",
            "수치 데이터 (체인 효율, XP)", "시각 측정 (보드/타일)",
            "보드 관리 (용량, 버블, 잠김)", "재화/경제 (코인/젬/에너지)",
            "퀘스트/이벤트 구조", "생산 체인 (스포너/수확)",
            "난이도 진행", "알고리즘 추론", "교차검증 결과",
        ]

    def get_aggregation_rules(self) -> str:
        return """- Merge 게임 특화: 머지 체인 레벨별 XP/가치 테이블 필수
- 스포너 주기는 전문가 9의 시간 측정 데이터 우선
- 보드 크기/용량은 전문가 5, 6의 교차 검증"""

    def get_vision_prompt(self, session_id: int, game_name: str) -> str:
        # Template prompts — customize per game when adding
        base_prompts = {
            1: f"{game_name} - 전문가 1: 게임 진행 분석. 퀘스트 순서, 머지 체인, 스테이지 클리어 과정을 관찰하세요.",
            2: f"{game_name} - 전문가 2: UI 전수 매핑. 모든 메뉴, 탭, 버튼을 기록하세요.",
            3: f"{game_name} - 전문가 3: 수치 수집. 머지 레벨별 XP, 코인 획득량, 에너지 비용을 테이블로 정리하세요.",
            4: f"{game_name} - 전문가 4: 머지 체인 분석. 각 오브젝트 계열의 최대 머지 레벨, 3머지 vs 5머지 효율을 분석하세요.",
            5: f"{game_name} - 전문가 5: 시각 측정. 보드 크기, 타일 크기, UI 요소를 px 단위로 측정하세요.",
            6: f"{game_name} - 전문가 6: 보드 관리. 총 보드 타일 수, 잠긴 영역, 버블링 메커니즘을 조사하세요.",
            7: f"{game_name} - 전문가 7: 경제 추적. 모든 재화, 획득 경로, 소비처를 정리하세요.",
            8: f"{game_name} - 전문가 8: 퀘스트/이벤트. 모든 퀘스트 보상, 이벤트 구조를 매핑하세요.",
            9: f"{game_name} - 전문가 9: 생산 체인. 스포너 주기, 수확 사이클, 클라우드 키를 분석하세요.",
            10: f"{game_name} - 전문가 10: 교차검증. 핵심 수치를 재확인하세요.",
        }
        return base_prompts[session_id]

    def get_parameters(self, game_key: str) -> str:
        return ""  # Define per game when adding

    def capture_session(self, ctx: CaptureContext, session_id: int):
        # Template capture — override per game
        ctx.dismiss_popups()
        ctx.shot(f"01_session_{session_id}_start")
        ctx.tap("center", wait=3)
        ctx.shot(f"02_session_{session_id}_mid")
        ctx.tap("play", wait=3)
        ctx.shot(f"03_session_{session_id}_end")


# Register
register_genre(MergeGenre())
