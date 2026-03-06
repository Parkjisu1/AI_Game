"""
AI Game Tester v2 — Constrained Layer Architecture
====================================================
5-Layer 제약 기반 게임 테스터.

Layer 1: Perception  (눈)   — 정해진 JSON 포맷으로만 화면 인식
Layer 2: Memory      (기억) — 고정 필드만 업데이트, 최근 N개만 유지
Layer 3: Decision    (판단) — 고정 분기 트리, AI 자율판단 금지
Layer 4: Execution   (손)   — Layer 3 결과만 실행, 자체 판단 금지
Layer 5: Verification(확인) — 홀더 변화만 체크, 실패 시 에스컬레이션

설계 원칙:
  - AI 자유도 = 최소 (Layer 1의 이미지 인식만 AI 의존)
  - 나머지 = 전부 규칙 기반 코드
  - TO DO / TO DON'T로 경계 고정 → 오버플로우 방지
"""

__version__ = "2.0.0"
