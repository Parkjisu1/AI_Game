"""
python -m virtual_player.tester [duration_minutes]

예:
  python -m virtual_player.tester 60     # 60분 실행
  python -m virtual_player.tester 540    # 9시간 (오버나이트)
"""
from .runner import main
main()
