"""learner_main.py — learner 컨테이너 진입점: 채택된 작업을 배우는 루프를 독립 프로세스로 돌린다.
(워처 컨테이너는 NEWPLAY_LEARNING_THREAD=0 으로 두고, 학습은 여기서만.)
"""
from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

import agent_team  # noqa: E402
import learning  # noqa: E402
from hermes_executor import _kb_collection_for, _learning_comment  # noqa: E402

if __name__ == "__main__":
    logging.getLogger("learner").info("학습 루프 시작 (채택된 작업 → 결정 메모 + 증분 재색인)")
    learning.learning_loop(agent_team.invoke, agent_team.set_actor, _learning_comment, _kb_collection_for)
