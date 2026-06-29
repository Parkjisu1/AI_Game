"""
pattern_lib — pixel_pattern_cowork 본 파이프라인 vendoring.

cowork 모듈들이 서로 top-level absolute import (`from plan_counts import ...`,
`from blank_engine import ...`, `from pixel_pattern_api import ...`,
`from variant_pipeline import ...`)을 사용하므로, 이 패키지의 디렉토리를 sys.path
앞에 등록해 그대로 동작하게 한다.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
