"""
Genre Loader — 장르 프로필 로더
================================
장르 ID로 GenreProfile을 로드.
"""

from typing import Dict, List

from .base import GenreProfile

# 장르 레지스트리: genre_id → factory function
_REGISTRY: Dict[str, callable] = {}


def _register_builtins():
    """내장 장르 등록."""
    from .puzzle_match import create_puzzle_match_profile
    from .idle_rpg import create_idle_rpg_profile
    from .runner_platformer import create_runner_platformer_profile
    from .tower_defense import create_tower_defense_profile
    from .card_battle import create_card_battle_profile
    from .simulation import create_simulation_profile

    _REGISTRY["puzzle_match"] = create_puzzle_match_profile
    _REGISTRY["idle_rpg"] = create_idle_rpg_profile
    _REGISTRY["runner_platformer"] = create_runner_platformer_profile
    _REGISTRY["tower_defense"] = create_tower_defense_profile
    _REGISTRY["card_battle"] = create_card_battle_profile
    _REGISTRY["simulation"] = create_simulation_profile


def load_genre(genre_id: str) -> GenreProfile:
    """장르 ID로 GenreProfile 로드."""
    if not _REGISTRY:
        _register_builtins()

    factory = _REGISTRY.get(genre_id)
    if factory is None:
        raise ValueError(
            f"Unknown genre: {genre_id}. "
            f"Available: {list(_REGISTRY.keys())}"
        )
    return factory()


def list_genres() -> List[str]:
    """등록된 장르 목록."""
    if not _REGISTRY:
        _register_builtins()
    return list(_REGISTRY.keys())


def register_genre(genre_id: str, factory: callable):
    """외부 장르 등록 (확장용)."""
    _REGISTRY[genre_id] = factory
