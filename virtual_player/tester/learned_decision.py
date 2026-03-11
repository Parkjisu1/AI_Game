"""
Learned Decision Engine — 학습된 패턴 + 페르소나로 플레이
==========================================================
학습 DB (learned_db.json)를 기반으로 의사결정.
페르소나 파라미터가 행동을 변형.

작동 방식:
  1. 현재 스크린샷 → 학습된 클러스터 매칭 (어떤 화면인지)
  2. 해당 화면의 학습된 행동 패턴 조회
  3. 페르소나에 따라 행동 변형:
     - 멍청한 플레이어: 잘못된 위치 탭, 규칙 무시
     - 똑똑한 플레이어: 최적 패턴 선택
     - 초보: 느린 반응, 탐색 행동 추가
     - 숙련자: 빠른 반응, 불필요 화면 스킵
"""

import json
import random
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .playbook import Action
from .perception import BoardState
from .memory import GameMemory
from .personas.base import PlayerProfile
from .learning_engine import (
    LearnedDB, LearningEngine,
    phash, hamming_distance, region_fingerprint, fingerprint_distance,
)


class LearnedDecision:
    """학습 기반 + 페르소나 적용 의사결정 엔진.

    사용법:
        db = LearningEngine.load("learned_db.json")
        persona = load_persona("dumb_newbie")
        decision = LearnedDecision(db, persona)
        decision.set_screenshot(img_path)
        actions = decision.decide(board, memory)
    """

    def __init__(
        self,
        learned_db: LearnedDB,
        persona: Optional[PlayerProfile] = None,
    ):
        self.db = learned_db
        self.persona = persona
        self._screenshot_path: Optional[Path] = None
        self._current_cluster: int = -1
        self._last_cluster: int = -1
        self._turn_count: int = 0
        self._same_cluster_count: int = 0

        # 클러스터 매칭용 해시 캐시
        self._cluster_hashes: Dict[int, np.ndarray] = {}
        self._cluster_fps: Dict[int, np.ndarray] = {}
        self._load_cluster_references()

    def _load_cluster_references(self):
        """학습된 클러스터의 대표 이미지 해시 로드."""
        for cid_str, info in self.db.clusters.items():
            cid = int(cid_str)
            samples = info.get("samples", [])
            if samples:
                first_sample = Path(samples[0])
                if first_sample.exists():
                    h = phash(first_sample)
                    if h is not None:
                        self._cluster_hashes[cid] = h
                    fp = region_fingerprint(first_sample)
                    if fp is not None:
                        self._cluster_fps[cid] = fp

    def set_screenshot(self, path: Path):
        """현재 스크린샷 설정."""
        self._screenshot_path = path

    def decide(self, board: BoardState, memory: GameMemory) -> List[Action]:
        """현재 상태 → 행동 리스트."""
        self._turn_count += 1

        # 1. 현재 화면 클러스터 매칭
        cluster_id, cluster_label = self._match_screen()

        # Stuck detection
        if cluster_id == self._last_cluster:
            self._same_cluster_count += 1
        else:
            self._same_cluster_count = 0
        self._last_cluster = cluster_id

        # 2. 페르소나 이탈 체크
        if self.persona and self.persona.should_quit(
            memory.consecutive_fails,
            self._turn_count * 2.0 / 60  # 대략적 분 환산
        ):
            return [Action("back", wait=1.0, reason="Persona quit: patience exhausted")]

        # 3. 페르소나 탐색 행동
        if self.persona and self.persona.should_explore():
            return self._explore_action()

        # 4. 학습된 패턴 기반 행동
        actions = self._get_learned_action(cluster_id, cluster_label, memory)

        # 5. 페르소나 변형 적용
        actions = self._apply_persona(actions)

        return actions

    def _match_screen(self) -> Tuple[int, str]:
        """현재 스크린샷을 학습된 클러스터에 매칭."""
        if not self._screenshot_path or not self._screenshot_path.exists():
            return (-1, "unknown")

        h = phash(self._screenshot_path)
        fp = region_fingerprint(self._screenshot_path)

        best_cid = -1
        best_dist = float("inf")

        for cid, ref_h in self._cluster_hashes.items():
            dist = hamming_distance(h, ref_h) if h is not None else 999

            if cid in self._cluster_fps and fp is not None:
                fp_dist = fingerprint_distance(fp, self._cluster_fps[cid])
                combined = dist + fp_dist * 0.1
            else:
                combined = dist

            if combined < best_dist:
                best_dist = combined
                best_cid = cid

        if best_cid >= 0 and best_dist < 60:  # 매칭 임계값
            label = self.db.clusters.get(best_cid, {}).get("label", "unknown")
            self._current_cluster = best_cid
            return (best_cid, label)

        return (-1, "unknown")

    def _get_learned_action(
        self, cluster_id: int, cluster_label: str, memory: GameMemory
    ) -> List[Action]:
        """학습된 패턴에서 행동 선택."""

        # 조건부 규칙 먼저 체크
        for rule in self.db.conditional_rules:
            if rule.get("screen") == cluster_label:
                if rule["type"] == "fixed_tap":
                    return [Action(
                        "tap", rule["x"], rule["y"],
                        self._get_wait_time(cluster_label),
                        f"Learned: fixed tap on {cluster_label} (conf={rule['confidence']:.0%})"
                    )]

        # 행동 패턴에서 선택
        matching = [
            p for p in self.db.action_patterns
            if p.get("cluster") == cluster_id or p.get("label") == cluster_label
        ]

        if not matching:
            # 학습 데이터 없는 화면 → fallback
            return self._fallback_action(cluster_label, memory)

        # 지능에 따른 선택
        if self.persona:
            mode = self.persona.get_priority_override()
        else:
            mode = "decent"

        if mode == "optimal":
            # 가장 높은 신뢰도 패턴
            best = max(matching, key=lambda p: p.get("confidence", 0))
        elif mode == "decent":
            # 신뢰도 상위 3개 중 랜덤
            top = sorted(matching, key=lambda p: -p.get("confidence", 0))[:3]
            best = random.choice(top)
        elif mode == "random":
            # 완전 랜덤
            best = random.choice(matching)
        else:  # worst
            # 가장 낮은 신뢰도 (의도적으로 나쁜 선택)
            best = min(matching, key=lambda p: p.get("confidence", 0))

        x, y = best["x"], best["y"]
        wait = self._get_wait_time(cluster_label)
        conf = best.get("confidence", 0)

        return [Action(
            "tap", x, y, wait,
            f"Learned: {cluster_label} ({conf:.0%}) mode={mode}"
        )]

    def _get_wait_time(self, cluster_label: str) -> float:
        """학습된 타이밍 + 페르소나 반응 속도."""
        # 학습된 기본 타이밍
        timing = self.db.timing.get(cluster_label, {})
        base = timing.get("mean", 2.0)

        # 페르소나 반응 속도 적용
        if self.persona:
            persona_delay = self.persona.get_reaction_delay()
            # 학습 타이밍과 페르소나 타이밍의 가중 평균
            return base * 0.4 + persona_delay * 0.6

        return base

    def _apply_persona(self, actions: List[Action]) -> List[Action]:
        """페르소나에 따른 행동 변형."""
        if not self.persona:
            return actions

        modified = []
        for action in actions:
            if action.type != "tap":
                modified.append(action)
                continue

            # 실수 체크
            if self.persona.should_make_mistake():
                # 잘못된 위치 탭 (원래 위치에서 크게 벗어남)
                bad_x = action.x + random.randint(-200, 200)
                bad_y = action.y + random.randint(-200, 200)
                bad_x = max(10, min(1070, bad_x))
                bad_y = max(10, min(1910, bad_y))
                modified.append(Action(
                    "tap", bad_x, bad_y, action.wait,
                    f"MISTAKE: intended ({action.x},{action.y})"
                ))
            else:
                # 정상 탭 + 사람같은 지터
                jx, jy = self.persona.jitter_tap(action.x, action.y)
                jx = max(10, min(1070, jx))
                jy = max(10, min(1910, jy))
                modified.append(Action(
                    "tap", jx, jy, action.wait,
                    action.reason
                ))

        return modified

    def _explore_action(self) -> List[Action]:
        """탐색 행동 (호기심/초보 페르소나)."""
        # 화면의 랜덤 위치 탭 (버튼이 있을 법한 영역)
        explore_targets = [
            (540, 1800, "bottom menu"),      # 하단 메뉴
            (540, 100, "top bar"),            # 상단 바
            (900, 100, "top right"),          # 우상단
            (100, 100, "top left"),           # 좌상단
            (540, 960, "center"),             # 중앙
            (random.randint(100, 980), random.randint(200, 1700), "random"),
        ]
        target = random.choice(explore_targets)
        return [Action(
            "tap", target[0], target[1], 2.0,
            f"Explore: {target[2]}"
        )]

    def _fallback_action(self, cluster_label: str, memory: GameMemory) -> List[Action]:
        """학습 데이터 없는 화면 fallback."""
        if self._same_cluster_count >= 10:
            return [Action("back", wait=1.0, reason="Stuck: back")]

        # 화면 중앙 하단 (대부분 게임의 메인 버튼 위치)
        return [Action("tap", 540, 1200, 2.0,
                        f"Fallback: no learned pattern for {cluster_label}")]

    def reset(self):
        """새 게임 시작."""
        self._turn_count = 0
        self._same_cluster_count = 0
        self._last_cluster = -1

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "turns": self._turn_count,
            "clusters_known": len(self._cluster_hashes),
        }
