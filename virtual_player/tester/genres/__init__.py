"""
tester.genres — Genre-level configurations
============================================
장르별 공통 규칙을 정의.

구조:
  genres/
    __init__.py          ← 이 파일 (로더)
    base.py              ← GenreProfile 기본 클래스
    puzzle_match.py      ← 퍼즐 매치 장르 (CarMatch, Candy Crush 등)
    idle_rpg.py          ← 방치형 RPG (Ash & Veil 등)
    merge.py             ← 머지 장르 (추후)
    ...

사용법:
    from tester.genres import load_genre
    genre = load_genre("puzzle_match")
"""
from .base import GenreProfile
from .loader import load_genre, list_genres

__all__ = ["GenreProfile", "load_genre", "list_genres"]
