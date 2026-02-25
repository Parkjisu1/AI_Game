"""
VirtualPlayer - AI Game Player Framework
=========================================
Play → Record → Develop 파이프라인의 Stage 1.
게임을 자동 플레이하고 행동 데이터를 기록합니다.

v2.0: ADB mode + 3-Tier Decision Architecture
  - L0: Reflex Cache (pHash → action, <50ms)
  - L1: Tactical Rules (nav_graph BFS, <200ms)
  - L2: Claude Vision (strategic, 1-3s, auto-cached)
"""

__version__ = "2.0.0"
