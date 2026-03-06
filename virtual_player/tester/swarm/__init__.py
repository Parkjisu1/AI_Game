"""
tester.swarm — AI Agent Swarm for Self-Improving Game Testing
===============================================================
여러 Claude Code 인스턴스가 역할을 분담하여
Play → Analyze → Improve → Validate 루프를 자동으로 돌린다.

참고 논문:
  - Voyager (NVIDIA, 2023): 자기 개선 에이전트, 스킬 라이브러리 축적
  - Reflexion (Shinn et al., 2023): 실패 경험으로부터 언어적 강화학습
  - AppAgent (Tencent, 2024): 시연+탐색 기반 앱 에이전트
  - CRADLE (Tan et al., 2024): 범용 컴퓨터 제어 에이전트
  - SPRING (Wu et al., 2024): 게임 매뉴얼 기반 전략 추론

구조:
  swarm/
    __init__.py            ← 이 파일
    orchestrator.py        ← 전체 사이클 관리 (coordinator)
    roles.py               ← 각 에이전트 역할 정의
    experience_db.py       ← 경험 축적 DB (Voyager의 Skill Library)
    reflector.py           ← 실패 분석 + 개선 제안 (Reflexion)
"""
__version__ = "0.1.0"
