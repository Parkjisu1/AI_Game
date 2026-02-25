"""
C10+ v2.5 Genre Module System
==============================
Base class for genre modules + registry.

Each genre defines:
- 10 AI tester roles (missions, prompts, capture scripts)
- 32 parameter definitions per game
- Domain weight matrix for aggregation
- OCR regions and wiki keywords (optional)

Genre Structure:
- Testers 1, 2:  Universal playthrough (genre-adapted prompts)
- Tester  5:     Universal visual measurement (genre-adapted)
- Tester 10:     Universal cross-validation (genre-adapted)
- Testers 3, 4, 6, 7, 8, 9:  Genre-specific flex roles
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Callable


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class MissionPlan:
    """Definition for a smart capture mission's navigation targets."""
    targets: List[str]                        # Screen types to visit
    required_screenshots: Dict[str, int]      # screen_type -> min captures
    max_time_minutes: float = 5.0             # Time budget per mission
    strategy: str = "sequential"              # sequential/breadth_first/depth_first/data_focused/...


@dataclass
class GameConfig:
    """Configuration for a specific game within a genre."""
    key: str                                    # e.g. "car_match"
    name: str                                   # e.g. "Car Match"
    package: str                                # e.g. "com.grandgames.carmatch"
    prefix: str                                 # e.g. "CM" (parameter ID prefix)
    coords: Dict[str, Tuple[int, int]]          # Named coordinates for ADB taps
    apk_path: Optional[str] = None              # APK file path (for M4 asset extraction)
    ocr_regions: Dict[str, Tuple[int, int, int, int]] = field(default_factory=dict)
    wiki_keywords: List[str] = field(default_factory=list)


@dataclass
class Mission:
    """Definition for one of the 10 AI tester missions."""
    id: int             # 1-10
    name: str           # e.g. "Full Playthrough A"
    domain: str         # e.g. "gameplay", "numeric", "visual"
    desc: str           # Detailed mission description
    flex: bool = False  # True if this is a genre-specific flex role


# ---------------------------------------------------------------------------
# Capture Context (passed to genre capture scripts)
# ---------------------------------------------------------------------------

class CaptureContext:
    """Provides ADB + screenshot helpers to genre capture scripts.

    Genre capture scripts call methods on this context instead of
    importing ADB functions directly. This allows testing/mocking.
    """

    def __init__(self, game: GameConfig, session_dir: Path,
                 tap_fn, swipe_fn, shot_fn, press_back_fn):
        self.game = game
        self.coords = game.coords
        self.session_dir = session_dir
        self.shots: List[Path] = []
        self._tap = tap_fn
        self._swipe = swipe_fn
        self._shot = shot_fn
        self._press_back = press_back_fn

    def c(self, name: str) -> Tuple[int, int]:
        """Get named coordinate. Returns (0,0) if not found."""
        return self.coords.get(name, (0, 0))

    def tap(self, target, wait: float = 1.5):
        """Tap a named coordinate or (x, y) tuple."""
        if isinstance(target, str):
            x, y = self.c(target)
        else:
            x, y = target
        self._tap(x, y, wait)

    def swipe(self, start, end, dur: int = 300, wait: float = 1.5):
        """Swipe from start to end. Each can be name or (x,y)."""
        if isinstance(start, str):
            x1, y1 = self.c(start)
        else:
            x1, y1 = start
        if isinstance(end, str):
            x2, y2 = self.c(end)
        else:
            x2, y2 = end
        self._swipe(x1, y1, x2, y2, dur, wait)

    def shot(self, name: str) -> bool:
        """Take a screenshot and add to session shots."""
        p = self.session_dir / f"{name}.png"
        if self._shot(p):
            self.shots.append(p)
            return True
        return False

    def back(self, wait: float = 1.5):
        """Press back button."""
        self._press_back(wait)

    def play_generic(self, positions: List[str] = None, taps: int = 5,
                     tap_wait: float = 0.8, wait_after: float = 2.0):
        """Generic play helper: tap multiple positions then wait."""
        if positions is None:
            positions = ["center", "tl", "tr", "bl", "br", "center", "tl", "tr"]
        for i in range(min(taps, len(positions))):
            self.tap(positions[i], wait=tap_wait)
        import time
        time.sleep(wait_after)

    def dismiss_popups(self, attempts: int = 3, wait: float = 2.0):
        """Try to dismiss any popups/dialogs."""
        for coord_name in ["popup_close", "popup_x", "popup"]:
            if coord_name in self.coords:
                for _ in range(attempts):
                    self.tap(coord_name, wait=wait)
                return
        # Fallback: tap center-bottom area
        self.tap((400, 900), wait=wait)


# ---------------------------------------------------------------------------
# Genre Base Class
# ---------------------------------------------------------------------------

class GenreBase(ABC):
    """Abstract base for genre modules.

    Subclasses must implement all abstract methods to define how
    C10+ v2.5 operates for their genre.
    """

    @property
    @abstractmethod
    def genre_name(self) -> str:
        """Human-readable genre name. e.g. 'Puzzle'"""

    @property
    @abstractmethod
    def genre_key(self) -> str:
        """Machine key. e.g. 'puzzle'"""

    @abstractmethod
    def get_games(self) -> Dict[str, GameConfig]:
        """Return all registered games for this genre. key -> GameConfig"""

    @abstractmethod
    def get_missions(self) -> Dict[int, Mission]:
        """Return 10 mission definitions (IDs 1-10)."""

    @abstractmethod
    def get_vision_prompt(self, session_id: int, game_name: str) -> str:
        """Return the Claude Vision analysis prompt for a session.

        Must contain detailed instructions for the AI tester.
        {game_name} is already substituted.
        """

    @abstractmethod
    def get_parameters(self, game_key: str) -> str:
        """Return 32 parameter definitions as formatted text.

        Format: PREFIX##: param_name (category) - description
        """

    @abstractmethod
    def get_domain_weights(self) -> Dict[str, List[int]]:
        """Return domain -> [expert session IDs] mapping.

        Used during aggregation to weight domain-expert opinions higher.
        e.g. {"numeric": [3, 4], "visual": [5], "economy": [7]}
        """

    @abstractmethod
    def capture_session(self, ctx: CaptureContext, session_id: int):
        """Execute the capture script for a specific session.

        Uses ctx.tap(), ctx.shot(), ctx.back() etc.
        Must populate ctx.shots with captured screenshot paths.
        """

    # --- Smart Player support ---

    def get_screen_types(self) -> Dict[str, str]:
        """Return {screen_type: description} for smart classifier.

        Default: 11 common screen types. Override per genre for more.
        """
        return {
            "loading": "Loading/splash screen",
            "lobby": "Main lobby or home screen",
            "battle": "Active gameplay/battle screen",
            "battle_result": "Victory/defeat result screen",
            "settings": "Settings/options menu",
            "popup_reward": "Reward popup overlay",
            "popup_ad": "Advertisement popup",
            "popup_tutorial": "Tutorial highlight overlay",
            "popup_announcement": "Announcement/notice popup",
            "popup_unknown": "Unrecognized popup overlay",
            "unknown": "Cannot determine screen type",
        }

    def get_mission_targets(self) -> Dict[int, MissionPlan]:
        """Return mission ID -> MissionPlan for smart capture.

        Default: empty (genre must override for smart mode).
        """
        return {}

    def get_screen_equivalences(self) -> Dict[str, str]:
        """Return screen equivalences for navigation.

        When a screen is equivalent to another, the navigator treats being at
        one as being at the other. This handles cases like idle RPGs where
        'battle' is just the lobby/field with auto-combat active.

        Returns: {screen_type: equivalent_to} e.g. {"battle": "lobby"}
        Meaning: if we're at 'battle' and need to reach 'lobby', we're already there.
        """
        return {}

    # --- Optional overrides ---

    def get_aggregation_sections(self) -> List[str]:
        """Section titles for the aggregation document. Override per genre."""
        return [
            "게임 정체성", "UI 구성", "게임 메커니즘", "수치 데이터",
            "시각 측정", "재화/경제", "난이도/레벨 진행", "부스터/특수기능",
            "타이밍", "알고리즘 추론", "상태/흐름", "한계값",
        ]

    def get_aggregation_rules(self) -> str:
        """Additional genre-specific aggregation rules. Override per genre."""
        return ""

    def get_ocr_regions(self, game_key: str) -> Dict[str, Tuple[int, int, int, int]]:
        """Return OCR crop regions for a game. Override per genre.

        Returns: Dict of name -> (x, y, width, height)
        """
        game = self.get_games().get(game_key)
        if game:
            return game.ocr_regions
        return {}

    def get_wiki_keywords(self, game_key: str) -> List[str]:
        """Return wiki search keywords for a game. Override per genre."""
        game = self.get_games().get(game_key)
        if game:
            return game.wiki_keywords
        return []


# ---------------------------------------------------------------------------
# Genre Registry
# ---------------------------------------------------------------------------

_GENRE_REGISTRY: Dict[str, GenreBase] = {}


def register_genre(genre: GenreBase):
    _GENRE_REGISTRY[genre.genre_key] = genre


def get_genre(genre_key: str) -> Optional[GenreBase]:
    return _GENRE_REGISTRY.get(genre_key)


def list_genres() -> List[str]:
    return list(_GENRE_REGISTRY.keys())


def find_game(game_key: str) -> Optional[Tuple[GenreBase, GameConfig]]:
    """Find a game across all registered genres."""
    for genre in _GENRE_REGISTRY.values():
        games = genre.get_games()
        if game_key in games:
            return genre, games[game_key]
    return None


def load_all_genres():
    """Import all genre modules to trigger registration."""
    from genres import puzzle, idle_rpg, merge
