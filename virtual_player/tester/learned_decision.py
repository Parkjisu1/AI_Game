"""
Learned Decision V2 — Zone + Patch 기반 의사결정
==================================================
V1 문제점:
  - 학습된 절대 좌표 그대로 탭 → 레벨 바뀌면 의미 없음
  - 화면 매칭만으로 행동 선택 → 게임 오브젝트 인식 불가

V2 해결:
  1. Zone 패턴: "gameplay에서는 queue_area → board_lower 순서로 탭"
  2. Template Matching: 학습된 패치를 현재 화면에서 찾아 탭 위치 결정
  3. Fallback: Zone 패턴 → Coord 패턴 → 탐색 순서

의사결정 흐름:
  현재 스크린샷
       ↓
  [1] 화면 클러스터 매칭 (pHash)
       ↓
  [2] 조건부 규칙 체크 (fixed_tap 등)
       ↓
  [3] 패치 매칭 시도 (gameplay인 경우)
       ↓
  [4] Zone 패턴 기반 탭 위치 결정
       ↓
  [5] 페르소나 변형 적용
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .playbook import Action
from .perception import BoardState
from .memory import GameMemory
from .personas.base import PlayerProfile
from .demo_recorder import ZONES, tap_to_zone
from .learning_engine import (
    LearnedDB, LearningEngine,
    phash, hamming_distance, region_fingerprint, fingerprint_distance,
)


class LearnedDecision:
    """Zone + Patch 기반 학습 의사결정 엔진."""

    PATCH_MATCH_THRESHOLD = 0.5   # template matching 최소 유사도

    def __init__(
        self,
        learned_db: LearnedDB,
        persona: Optional[PlayerProfile] = None,
        demo_dir: Optional[Path] = None,
    ):
        self.db = learned_db
        self.persona = persona
        self.demo_dir = demo_dir  # 패치 파일 위치
        self._screenshot_path: Optional[Path] = None
        self._current_cluster: int = -1
        self._last_cluster: int = -1
        self._turn_count: int = 0
        self._same_cluster_count: int = 0

        # 클러스터 매칭용 캐시
        self._cluster_hashes: Dict[int, np.ndarray] = {}
        self._cluster_fps: Dict[int, np.ndarray] = {}
        self._load_cluster_references()

        # 패치 템플릿 캐시
        self._patch_templates: List[dict] = []
        self._load_patch_templates()

    def _load_cluster_references(self):
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

    def _load_patch_templates(self):
        """학습된 패치 이미지를 템플릿으로 로드."""
        for pp in self.db.patch_patterns:
            patch_rel = pp.get("representative_patch", "")
            if not patch_rel:
                continue

            # 패치 파일 찾기 (여러 demo_dir에서)
            patch_path = None
            if self.demo_dir:
                candidate = self.demo_dir / patch_rel
                if candidate.exists():
                    patch_path = candidate

            if patch_path is None:
                # 절대 경로 시도
                if Path(patch_rel).exists():
                    patch_path = Path(patch_rel)

            if patch_path and patch_path.exists():
                img = cv2.imread(str(patch_path), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    # 템플릿 크기 정규화
                    img = cv2.resize(img, (60, 60))
                    self._patch_templates.append({
                        "template": img,
                        "info": pp,
                    })

    def set_screenshot(self, path: Path):
        self._screenshot_path = path

    def decide(self, board: BoardState, memory: GameMemory) -> List[Action]:
        """현재 상태 → 행동 리스트."""
        self._turn_count += 1

        # 1. 화면 클러스터 매칭
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
            self._turn_count * 2.0 / 60
        ):
            return [Action("back", wait=1.0,
                           reason="Persona quit: patience exhausted")]

        # 3. 페르소나 탐색
        if self.persona and self.persona.should_explore():
            return self._explore_action()

        # 4. 조건부 규칙 (popup, lobby 등 고정 핸들러)
        rule_action = self._check_rules(cluster_label)
        if rule_action:
            return self._apply_persona(rule_action)

        # 5. Patch 매칭 (gameplay인 경우)
        if cluster_label == "gameplay":
            patch_action = self._patch_match_action(cluster_label)
            if patch_action:
                return self._apply_persona(patch_action)

        # 6. Zone 패턴 기반
        zone_action = self._zone_action(cluster_id, cluster_label, memory)
        if zone_action:
            return self._apply_persona(zone_action)

        # 7. 좌표 패턴 fallback
        coord_action = self._coord_action(cluster_id, cluster_label, memory)
        if coord_action:
            return self._apply_persona(coord_action)

        # 8. 최종 fallback
        return self._apply_persona(self._fallback_action(cluster_label, memory))

    # ===================================================================
    # Screen Matching
    # ===================================================================
    def _match_screen(self) -> Tuple[int, str]:
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

        if best_cid >= 0 and best_dist < 60:
            label = self.db.clusters.get(best_cid, {}).get("label", "unknown")
            self._current_cluster = best_cid
            return (best_cid, label)

        return (-1, "unknown")

    # ===================================================================
    # Rule-based Action (popup, lobby 고정 핸들러)
    # ===================================================================
    def _check_rules(self, cluster_label: str) -> Optional[List[Action]]:
        for rule in self.db.conditional_rules:
            if rule.get("screen") != cluster_label:
                continue
            if rule["type"] == "fixed_tap":
                return [Action(
                    "tap", rule["x"], rule["y"],
                    self._get_wait_time(cluster_label),
                    f"Rule: fixed tap on {cluster_label} "
                    f"zone={rule.get('zone')} (conf={rule['confidence']:.0%})"
                )]
        return None

    # ===================================================================
    # Patch Matching (gameplay용)
    # ===================================================================
    def _patch_match_action(self, cluster_label: str) -> Optional[List[Action]]:
        """현재 화면에서 학습된 패치를 찾아 탭."""
        if not self._patch_templates or not self._screenshot_path:
            return None

        screen = cv2.imread(str(self._screenshot_path), cv2.IMREAD_GRAYSCALE)
        if screen is None:
            return None

        best_match = None
        best_val = self.PATCH_MATCH_THRESHOLD

        for pt in self._patch_templates:
            template = pt["template"]
            th, tw = template.shape[:2]

            # 다양한 스케일로 매칭 시도
            for scale in [0.8, 1.0, 1.2, 1.5]:
                scaled_t = cv2.resize(
                    template,
                    (int(tw * scale), int(th * scale))
                )
                sh, sw = scaled_t.shape[:2]
                if sh > screen.shape[0] or sw > screen.shape[1]:
                    continue

                result = cv2.matchTemplate(
                    screen, scaled_t, cv2.TM_CCOEFF_NORMED
                )
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val > best_val:
                    best_val = max_val
                    # 매칭된 위치의 중심
                    cx = max_loc[0] + sw // 2
                    cy = max_loc[1] + sh // 2
                    best_match = {
                        "x": cx, "y": cy,
                        "confidence": max_val,
                        "info": pt["info"],
                    }

        if best_match:
            return [Action(
                "tap", best_match["x"], best_match["y"],
                self._get_wait_time(cluster_label),
                f"Patch match: conf={best_match['confidence']:.0%} "
                f"zone={tap_to_zone(best_match['x'], best_match['y'])}"
            )]

        return None

    # ===================================================================
    # Zone-based Action
    # ===================================================================
    def _zone_action(
        self, cluster_id: int, cluster_label: str, memory: GameMemory
    ) -> Optional[List[Action]]:
        """Zone 패턴에서 행동 선택."""
        matching = [
            zp for zp in self.db.zone_patterns
            if (zp.get("cluster") == cluster_id or
                zp.get("label") == cluster_label)
            and zp.get("tap_count", 0) >= 2
        ]

        if not matching:
            return None

        # 지능에 따른 선택
        mode = self.persona.get_priority_override() if self.persona else "decent"

        if mode == "optimal":
            # 전이율 높은 zone
            best = max(matching, key=lambda z: z.get("transition_rate", 0))
        elif mode == "decent":
            # 탭 비율 상위 3개 중 랜덤
            top = sorted(matching, key=lambda z: -z.get("tap_ratio", 0))[:3]
            best = random.choice(top)
        elif mode == "random":
            best = random.choice(matching)
        else:  # worst
            best = min(matching, key=lambda z: z.get("transition_rate", 0))

        zone_name = best["zone"]
        # Zone 영역 내 랜덤 좌표
        x, y = self._random_point_in_zone(zone_name)
        wait = self._get_wait_time(cluster_label)

        return [Action(
            "tap", x, y, wait,
            f"Zone: {cluster_label}/{zone_name} "
            f"(ratio={best['tap_ratio']:.0%}, mode={mode})"
        )]

    def _random_point_in_zone(self, zone_name: str) -> Tuple[int, int]:
        """Zone 영역 내 랜덤 좌표."""
        if zone_name not in ZONES:
            return (540, 960)  # 화면 중앙
        x1, y1, x2, y2 = ZONES[zone_name]
        x = random.randint(x1 + 10, x2 - 10)
        y = random.randint(y1 + 10, y2 - 10)
        return (x, y)

    # ===================================================================
    # Coordinate-based Action (V1 fallback)
    # ===================================================================
    def _coord_action(
        self, cluster_id: int, cluster_label: str, memory: GameMemory
    ) -> Optional[List[Action]]:
        matching = [
            p for p in self.db.action_patterns
            if p.get("cluster") == cluster_id or p.get("label") == cluster_label
        ]
        if not matching:
            return None

        mode = self.persona.get_priority_override() if self.persona else "decent"
        if mode == "optimal":
            best = max(matching, key=lambda p: p.get("confidence", 0))
        elif mode == "decent":
            top = sorted(matching, key=lambda p: -p.get("confidence", 0))[:3]
            best = random.choice(top)
        elif mode == "random":
            best = random.choice(matching)
        else:
            best = min(matching, key=lambda p: p.get("confidence", 0))

        return [Action(
            "tap", best["x"], best["y"],
            self._get_wait_time(cluster_label),
            f"Coord: {cluster_label} (conf={best.get('confidence', 0):.0%}, mode={mode})"
        )]

    # ===================================================================
    # Timing
    # ===================================================================
    def _get_wait_time(self, cluster_label: str) -> float:
        timing = self.db.timing.get(cluster_label, {})
        base = timing.get("mean", 2.0)
        if self.persona:
            persona_delay = self.persona.get_reaction_delay()
            return base * 0.4 + persona_delay * 0.6
        return base

    # ===================================================================
    # Persona Modifier
    # ===================================================================
    def _apply_persona(self, actions: List[Action]) -> List[Action]:
        if not self.persona:
            return actions

        modified = []
        for action in actions:
            if action.type != "tap":
                modified.append(action)
                continue

            if self.persona.should_make_mistake():
                bad_x = action.x + random.randint(-200, 200)
                bad_y = action.y + random.randint(-200, 200)
                bad_x = max(10, min(1070, bad_x))
                bad_y = max(10, min(1910, bad_y))
                modified.append(Action(
                    "tap", bad_x, bad_y, action.wait,
                    f"MISTAKE: intended ({action.x},{action.y})"
                ))
            else:
                jx, jy = self.persona.jitter_tap(action.x, action.y)
                jx = max(10, min(1070, jx))
                jy = max(10, min(1910, jy))
                modified.append(Action(
                    "tap", jx, jy, action.wait, action.reason
                ))

        return modified

    # ===================================================================
    # Explore / Fallback
    # ===================================================================
    def _explore_action(self) -> List[Action]:
        explore_targets = [
            (540, 1800, "bottom menu"),
            (540, 100, "top bar"),
            (900, 100, "top right"),
            (100, 100, "top left"),
            (540, 960, "center"),
            (random.randint(100, 980), random.randint(200, 1700), "random"),
        ]
        target = random.choice(explore_targets)
        return [Action(
            "tap", target[0], target[1], 2.0,
            f"Explore: {target[2]}"
        )]

    def _fallback_action(
        self, cluster_label: str, memory: GameMemory
    ) -> List[Action]:
        if self._same_cluster_count >= 10:
            return [Action("back", wait=1.0, reason="Stuck: back")]
        return [Action("tap", 540, 1200, 2.0,
                        f"Fallback: no pattern for {cluster_label}")]

    def reset(self):
        self._turn_count = 0
        self._same_cluster_count = 0
        self._last_cluster = -1

    @property
    def stats(self) -> Dict[str, int]:
        return {
            "turns": self._turn_count,
            "clusters_known": len(self._cluster_hashes),
            "patch_templates": len(self._patch_templates),
        }
