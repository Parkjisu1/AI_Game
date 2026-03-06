"""
tester.personas — Player persona profiles
============================================
플레이어 성향 프로필을 정의.

구조:
  personas/
    __init__.py          ← 이 파일
    base.py              ← PlayerProfile 클래스
    presets.py            ← 기본 프리셋 (casual_f2p, mid_dolphin, hardcore_whale)
"""
from .base import PlayerProfile
from .presets import load_persona, list_personas

__all__ = ["PlayerProfile", "load_persona", "list_personas"]
