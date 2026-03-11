"""
Learning Engine V2 — Zone + Patch 기반 학습
=============================================
V1 문제점:
  - 절대 좌표 학습 → 레벨 바뀌면 의미 없음
  - 화면 클러스터만 → 게임 오브젝트 인식 불가

V2 해결:
  1. Zone 기반 행동 패턴: 좌표 → 영역(zone) 변환 후 패턴 추출
  2. 탭 패치 유사도: 120x120 크롭 이미지로 "무엇을 탭했는지" 학습
  3. 차이 영역 분석: pre/post 차이로 "탭 효과" 학습

파이프라인:
  demo_log.jsonl + frames + patches
       ↓
  [1] Screen Clustering (pHash)
       ↓
  [2] Zone Pattern Extraction (zone 빈도 + 전이)
       ↓
  [3] Patch Pattern Extraction (패치 유사도 그룹핑)
       ↓
  [4] Timing + Conditional Rules
       ↓
  learned_db.json
"""

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from .demo_recorder import ZONES, tap_to_zone


# ---------------------------------------------------------------------------
# Image Hashing
# ---------------------------------------------------------------------------
def phash(img_path: Path, hash_size: int = 16) -> Optional[np.ndarray]:
    """Perceptual Hash — 이미지를 해시로 변환."""
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    resized = cv2.resize(img, (hash_size + 1, hash_size))
    diff = resized[:, 1:] > resized[:, :-1]
    return diff.flatten()


def hamming_distance(h1: np.ndarray, h2: np.ndarray) -> int:
    return int(np.sum(h1 != h2))


def region_fingerprint(img_path: Path) -> Optional[np.ndarray]:
    """화면 영역별 밝기 fingerprint (6x10 그리드)."""
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    resized = cv2.resize(img, (60, 100))
    grid = resized.reshape(10, 10, 6, 10).mean(axis=(1, 3))
    return grid.flatten()


def fingerprint_distance(f1: np.ndarray, f2: np.ndarray) -> float:
    return float(np.sqrt(np.sum((f1.astype(float) - f2.astype(float)) ** 2)))


def patch_similarity(patch1_path: Path, patch2_path: Path) -> float:
    """두 패치 이미지의 유사도 (0~1, 높을수록 유사)."""
    img1 = cv2.imread(str(patch1_path), cv2.IMREAD_GRAYSCALE)
    img2 = cv2.imread(str(patch2_path), cv2.IMREAD_GRAYSCALE)
    if img1 is None or img2 is None:
        return 0.0
    # 같은 크기로
    img1 = cv2.resize(img1, (60, 60))
    img2 = cv2.resize(img2, (60, 60))
    # 정규화된 상관계수
    result = cv2.matchTemplate(img1, img2, cv2.TM_CCOEFF_NORMED)
    return float(result[0][0])


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------
@dataclass
class ScreenCluster:
    cluster_id: int
    label: str
    sample_paths: List[str] = field(default_factory=list)
    center_hash: Optional[np.ndarray] = None
    center_fingerprint: Optional[np.ndarray] = None
    tap_positions: List[Tuple[int, int]] = field(default_factory=list)
    tap_zones: List[str] = field(default_factory=list)
    transitions_to: Dict[int, int] = field(default_factory=dict)


@dataclass
class LearnedDB:
    """학습된 행동 DB."""
    game_id: str
    version: str = "v2"
    demo_sessions: int = 0
    total_frames: int = 0
    clusters: Dict[int, dict] = field(default_factory=dict)
    action_patterns: List[dict] = field(default_factory=list)
    zone_patterns: List[dict] = field(default_factory=list)
    patch_patterns: List[dict] = field(default_factory=list)
    screen_flow: Dict[str, List[str]] = field(default_factory=dict)
    timing: dict = field(default_factory=dict)
    conditional_rules: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Learning Engine
# ---------------------------------------------------------------------------
class LearningEngine:
    """데모 데이터에서 학습 DB 생성."""

    CLUSTER_THRESHOLD_HASH = 40
    CLUSTER_THRESHOLD_FP = 800
    TAP_CLUSTER_RADIUS = 80
    PATCH_SIMILARITY_THRESHOLD = 0.6

    LABEL_HINTS = {
        "lobby": {"tap_y_range": (1300, 1700), "next_is_gameplay": True},
        "win": {"tap_y_range": (900, 1300), "next_is_lobby": True},
        "fail": {"tap_y_range": (600, 900), "has_retry": True},
        "popup": {"has_close_x": True},
    }

    def __init__(self, game_id: str):
        self.game_id = game_id
        self._all_frames: List[dict] = []
        self._frame_hashes: Dict[str, np.ndarray] = {}
        self._frame_fps: Dict[str, np.ndarray] = {}
        self._clusters: List[ScreenCluster] = []
        self._frame_cluster: Dict[str, int] = {}

    def add_demo(self, demo_dir: Path):
        """데모 세션 추가. V2 포맷(zone, patch) 및 V1 포맷 모두 지원."""
        demo_dir = Path(demo_dir)
        log_path = demo_dir / "demo_log.jsonl"
        if not log_path.exists():
            print(f"[Learn] Log not found: {log_path}")
            return

        entries = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                entry["_demo_dir"] = str(demo_dir)
                # pre/post 절대 경로
                entry["_pre_abs"] = str(demo_dir / entry["pre_screenshot"])
                entry["_post_abs"] = str(demo_dir / entry["post_screenshot"])
                # 패치 절대 경로 (V2)
                if entry.get("tap_patch"):
                    entry["_patch_abs"] = str(demo_dir / entry["tap_patch"])
                # Zone (V2에서는 이미 있고, V1이면 좌표에서 계산)
                if "zone" not in entry:
                    action = entry.get("action", {})
                    if action.get("type") == "tap":
                        entry["zone"] = tap_to_zone(action["x"], action["y"])
                entries.append(entry)

        self._all_frames.extend(entries)
        print(f"[Learn] Added {len(entries)} frames from {demo_dir.name}")

    def learn(self) -> LearnedDB:
        """전체 학습 파이프라인."""
        if not self._all_frames:
            print("[Learn] No frames to learn from!")
            return LearnedDB(game_id=self.game_id)

        print(f"[Learn] Total frames: {len(self._all_frames)}")

        self._compute_hashes()
        self._cluster_screens()
        self._estimate_labels()

        # V1: 좌표 기반 패턴
        coord_patterns = self._extract_patterns()
        # V2: Zone 기반 패턴
        zone_patterns = self._extract_zone_patterns()
        # V2: Patch 기반 패턴
        patch_patterns = self._extract_patch_patterns()
        flow = self._extract_flow()
        timing = self._extract_timing()
        rules = self._extract_conditional_rules()

        db = LearnedDB(
            game_id=self.game_id,
            version="v2",
            demo_sessions=len(set(
                e.get("_demo_dir", "") for e in self._all_frames
            )),
            total_frames=len(self._all_frames),
            clusters={
                c.cluster_id: {
                    "label": c.label,
                    "sample_count": len(c.sample_paths),
                    "samples": c.sample_paths[:5],
                    "zone_distribution": dict(Counter(c.tap_zones)),
                }
                for c in self._clusters
            },
            action_patterns=[
                {
                    "cluster": p["cluster"], "label": p["label"],
                    "x": p["x"], "y": p["y"],
                    "count": p["count"], "confidence": p["confidence"],
                    "avg_interval": p["avg_interval"],
                    "next_cluster": p["next_cluster"],
                }
                for p in coord_patterns
            ],
            zone_patterns=zone_patterns,
            patch_patterns=patch_patterns,
            screen_flow=flow,
            timing=timing,
            conditional_rules=rules,
        )

        print(f"[Learn] Clusters: {len(db.clusters)}")
        print(f"[Learn] Coord patterns: {len(db.action_patterns)}")
        print(f"[Learn] Zone patterns: {len(db.zone_patterns)}")
        print(f"[Learn] Patch patterns: {len(db.patch_patterns)}")
        print(f"[Learn] Flow transitions: {sum(len(v) for v in flow.values())}")
        print(f"[Learn] Conditional rules: {len(rules)}")

        return db

    # -----------------------------------------------------------------------
    # Step 1: Image Hashing
    # -----------------------------------------------------------------------
    def _compute_hashes(self):
        print("[Learn] Computing image hashes...")
        for entry in self._all_frames:
            pre_path = entry["_pre_abs"]
            if pre_path not in self._frame_hashes:
                h = phash(Path(pre_path))
                if h is not None:
                    self._frame_hashes[pre_path] = h
                fp = region_fingerprint(Path(pre_path))
                if fp is not None:
                    self._frame_fps[pre_path] = fp
        print(f"  Hashed {len(self._frame_hashes)} images")

    # -----------------------------------------------------------------------
    # Step 2: Screen Clustering
    # -----------------------------------------------------------------------
    def _cluster_screens(self):
        print("[Learn] Clustering screens...")
        paths = list(self._frame_hashes.keys())
        assigned = {}
        clusters = []

        for path in paths:
            h = self._frame_hashes[path]
            fp = self._frame_fps.get(path)

            best_cluster = -1
            best_dist = float("inf")

            for cluster in clusters:
                if cluster.center_hash is not None:
                    dist_h = hamming_distance(h, cluster.center_hash)
                else:
                    dist_h = 999
                if fp is not None and cluster.center_fingerprint is not None:
                    dist_fp = fingerprint_distance(fp, cluster.center_fingerprint)
                else:
                    dist_fp = 999
                if (dist_h < self.CLUSTER_THRESHOLD_HASH and
                        dist_fp < self.CLUSTER_THRESHOLD_FP):
                    combined = dist_h + dist_fp * 0.1
                    if combined < best_dist:
                        best_dist = combined
                        best_cluster = cluster.cluster_id

            if best_cluster >= 0:
                assigned[path] = best_cluster
                clusters[best_cluster].sample_paths.append(path)
            else:
                cid = len(clusters)
                new_cluster = ScreenCluster(
                    cluster_id=cid,
                    label=f"screen_{cid}",
                    sample_paths=[path],
                    center_hash=h.copy(),
                    center_fingerprint=fp.copy() if fp is not None else None,
                )
                clusters.append(new_cluster)
                assigned[path] = cid

        self._clusters = clusters
        self._frame_cluster = assigned
        print(f"  Found {len(clusters)} screen clusters")

    # -----------------------------------------------------------------------
    # Step 3: Label Estimation
    # -----------------------------------------------------------------------
    def _estimate_labels(self):
        print("[Learn] Estimating cluster labels...")

        for entry in self._all_frames:
            pre_path = entry["_pre_abs"]
            cid = self._frame_cluster.get(pre_path, -1)
            if cid < 0 or cid >= len(self._clusters):
                continue
            action = entry.get("action", {})
            if action.get("type") == "tap":
                self._clusters[cid].tap_positions.append(
                    (action["x"], action["y"])
                )
                self._clusters[cid].tap_zones.append(
                    entry.get("zone", tap_to_zone(action["x"], action["y"]))
                )

        # 전이 패턴
        for i in range(len(self._all_frames) - 1):
            pre_path = self._all_frames[i]["_pre_abs"]
            next_path = self._all_frames[i + 1]["_pre_abs"]
            cid = self._frame_cluster.get(pre_path, -1)
            next_cid = self._frame_cluster.get(next_path, -1)
            if cid >= 0 and next_cid >= 0 and cid != next_cid:
                self._clusters[cid].transitions_to[next_cid] = \
                    self._clusters[cid].transitions_to.get(next_cid, 0) + 1

        # 가장 많이 탭된 클러스터 = gameplay
        gameplay_cid = -1
        max_taps = 0
        for cluster in self._clusters:
            if len(cluster.tap_positions) > max_taps:
                max_taps = len(cluster.tap_positions)
                gameplay_cid = cluster.cluster_id

        # Zone 기반 라벨 보정
        if gameplay_cid >= 0:
            gp = self._clusters[gameplay_cid]
            zone_counts = Counter(gp.tap_zones)
            # gameplay은 board/queue 영역 탭이 많아야 함
            game_zones = zone_counts.get("board_upper", 0) + \
                         zone_counts.get("board_lower", 0) + \
                         zone_counts.get("queue_area", 0)
            if game_zones > len(gp.tap_zones) * 0.3:
                gp.label = "gameplay"
            else:
                gp.label = "gameplay"  # 어쨌든 가장 많이 탭된 건 gameplay

        for cluster in self._clusters:
            if cluster.cluster_id == gameplay_cid:
                continue

            zone_counts = Counter(cluster.tap_zones)

            # close_x 탭이 많으면 popup
            if zone_counts.get("close_x", 0) >= 1:
                cluster.label = "popup"
                continue

            # bottom_menu 탭이 많으면 lobby
            if zone_counts.get("bottom_menu", 0) >= 2:
                cluster.label = "lobby"
                continue

            # gameplay으로 전이하는 클러스터 = lobby
            if gameplay_cid in cluster.transitions_to:
                if cluster.transitions_to[gameplay_cid] >= 1:
                    cluster.label = "lobby"
                    continue

            # gameplay에서 오는 클러스터
            for other in self._clusters:
                if other.cluster_id == gameplay_cid:
                    if cluster.cluster_id in other.transitions_to:
                        # center 탭이 많으면 win (계속하기)
                        center_taps = zone_counts.get("center", 0)
                        if center_taps > 0:
                            cluster.label = "result"
                        else:
                            cluster.label = "result"
                        break

            if cluster.label.startswith("screen_"):
                cluster.label = "popup"

        for c in self._clusters:
            zone_str = dict(Counter(c.tap_zones).most_common(3))
            print(f"  Cluster {c.cluster_id}: {c.label} "
                  f"({len(c.sample_paths)} samples, zones={zone_str})")

    # -----------------------------------------------------------------------
    # Step 4: Coordinate-based Patterns (V1 호환)
    # -----------------------------------------------------------------------
    def _extract_patterns(self) -> List[dict]:
        patterns = []
        for cluster in self._clusters:
            if not cluster.tap_positions:
                continue
            tap_groups = self._cluster_taps(cluster.tap_positions)
            for (cx, cy), members in tap_groups:
                success = 0
                intervals = []
                next_clusters = Counter()

                for i, entry in enumerate(self._all_frames[:-1]):
                    pre_path = entry["_pre_abs"]
                    cid = self._frame_cluster.get(pre_path, -1)
                    if cid != cluster.cluster_id:
                        continue
                    action = entry.get("action", {})
                    if action.get("type") != "tap":
                        continue
                    ax, ay = action["x"], action["y"]
                    if (abs(ax - cx) < self.TAP_CLUSTER_RADIUS and
                            abs(ay - cy) < self.TAP_CLUSTER_RADIUS):
                        intervals.append(entry.get("interval_sec", 0))
                        next_path = self._all_frames[i + 1]["_pre_abs"]
                        next_cid = self._frame_cluster.get(next_path, -1)
                        if next_cid != cluster.cluster_id:
                            success += 1
                        if next_cid >= 0:
                            next_clusters[next_cid] += 1

                avg_interval = (
                    sum(intervals) / len(intervals) if intervals else 2.0
                )
                most_common_next = (
                    next_clusters.most_common(1)[0][0] if next_clusters else -1
                )
                patterns.append({
                    "cluster": cluster.cluster_id,
                    "label": cluster.label,
                    "x": cx, "y": cy,
                    "count": len(members),
                    "confidence": round(success / max(len(members), 1), 2),
                    "avg_interval": round(avg_interval, 2),
                    "next_cluster": most_common_next,
                })

        patterns.sort(key=lambda p: -p["confidence"])
        return patterns

    # -----------------------------------------------------------------------
    # Step 5: Zone-based Patterns (V2 신규)
    # -----------------------------------------------------------------------
    def _extract_zone_patterns(self) -> List[dict]:
        """클러스터별 Zone 행동 패턴.

        "gameplay 화면에서 queue_area를 68% 탭 → board_lower 변화"
        """
        patterns = []

        for cluster in self._clusters:
            if not cluster.tap_zones:
                continue

            zone_counts = Counter(cluster.tap_zones)
            total = len(cluster.tap_zones)

            for zone_name, count in zone_counts.most_common():
                # 이 zone 탭 후 화면 전이율
                transitions = 0
                zone_to_next = Counter()
                diff_zones_after = Counter()

                for i, entry in enumerate(self._all_frames[:-1]):
                    pre_path = entry["_pre_abs"]
                    cid = self._frame_cluster.get(pre_path, -1)
                    if cid != cluster.cluster_id:
                        continue
                    if entry.get("zone") != zone_name:
                        continue
                    # 전이 체크
                    next_path = self._all_frames[i + 1]["_pre_abs"]
                    next_cid = self._frame_cluster.get(next_path, -1)
                    if next_cid >= 0 and next_cid != cluster.cluster_id:
                        transitions += 1
                        if next_cid < len(self._clusters):
                            zone_to_next[self._clusters[next_cid].label] += 1
                    # diff_zones
                    for dz in entry.get("diff_zones", []):
                        diff_zones_after[dz] += 1

                transition_rate = transitions / max(count, 1)
                patterns.append({
                    "cluster": cluster.cluster_id,
                    "label": cluster.label,
                    "zone": zone_name,
                    "tap_count": count,
                    "tap_ratio": round(count / total, 2),
                    "transition_rate": round(transition_rate, 2),
                    "leads_to": dict(zone_to_next.most_common(3)),
                    "changes_in": dict(diff_zones_after.most_common(3)),
                })

        patterns.sort(key=lambda p: (-p["tap_ratio"],))
        return patterns

    # -----------------------------------------------------------------------
    # Step 6: Patch-based Patterns (V2 신규)
    # -----------------------------------------------------------------------
    def _extract_patch_patterns(self) -> List[dict]:
        """탭 패치 유사도 그룹핑.

        비슷한 패치끼리 묶어서 "이런 모양의 것을 탭하라" 패턴 추출.
        """
        # 패치가 있는 엔트리만
        patch_entries = [
            e for e in self._all_frames
            if e.get("_patch_abs") and Path(e["_patch_abs"]).exists()
        ]

        if not patch_entries:
            print("[Learn] No patches found, skipping patch patterns")
            return []

        print(f"[Learn] Grouping {len(patch_entries)} patches...")

        # 패치 클러스터링 (greedy)
        groups: List[List[dict]] = []
        used = [False] * len(patch_entries)

        for i in range(len(patch_entries)):
            if used[i]:
                continue
            group = [patch_entries[i]]
            used[i] = True
            ref_path = Path(patch_entries[i]["_patch_abs"])

            for j in range(i + 1, len(patch_entries)):
                if used[j]:
                    continue
                cmp_path = Path(patch_entries[j]["_patch_abs"])
                sim = patch_similarity(ref_path, cmp_path)
                if sim >= self.PATCH_SIMILARITY_THRESHOLD:
                    group.append(patch_entries[j])
                    used[j] = True

            groups.append(group)

        # 의미 있는 그룹 (2개 이상)만
        patterns = []
        for gid, group in enumerate(groups):
            if len(group) < 2:
                continue

            zones = Counter(e.get("zone", "unknown") for e in group)
            cluster_labels = Counter()
            for e in group:
                pre_path = e["_pre_abs"]
                cid = self._frame_cluster.get(pre_path, -1)
                if cid >= 0 and cid < len(self._clusters):
                    cluster_labels[self._clusters[cid].label] += 1

            # 대표 패치 (첫 번째)
            representative = group[0].get("tap_patch", "")

            patterns.append({
                "patch_group": gid,
                "count": len(group),
                "representative_patch": representative,
                "zones": dict(zones.most_common(3)),
                "screen_labels": dict(cluster_labels.most_common(3)),
                "avg_x": int(sum(
                    e["action"]["x"] for e in group
                ) / len(group)),
                "avg_y": int(sum(
                    e["action"]["y"] for e in group
                ) / len(group)),
            })

        print(f"  Found {len(patterns)} patch groups")
        return patterns

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------
    def _cluster_taps(
        self, taps: List[Tuple[int, int]]
    ) -> List[Tuple[Tuple[int, int], List[Tuple[int, int]]]]:
        clusters = []
        used = [False] * len(taps)
        for i in range(len(taps)):
            if used[i]:
                continue
            group = [taps[i]]
            used[i] = True
            for j in range(i + 1, len(taps)):
                if used[j]:
                    continue
                if (abs(taps[i][0] - taps[j][0]) < self.TAP_CLUSTER_RADIUS and
                        abs(taps[i][1] - taps[j][1]) < self.TAP_CLUSTER_RADIUS):
                    group.append(taps[j])
                    used[j] = True
            cx = sum(t[0] for t in group) // len(group)
            cy = sum(t[1] for t in group) // len(group)
            clusters.append(((cx, cy), group))
        return clusters

    def _extract_flow(self) -> Dict[str, List[str]]:
        flow = defaultdict(Counter)
        for cluster in self._clusters:
            for next_cid, count in cluster.transitions_to.items():
                if next_cid < len(self._clusters):
                    src_label = cluster.label
                    dst_label = self._clusters[next_cid].label
                    flow[src_label][dst_label] += count
        return {
            src: [dst for dst, _ in counter.most_common()]
            for src, counter in flow.items()
        }

    def _extract_timing(self) -> dict:
        cluster_intervals = defaultdict(list)
        for entry in self._all_frames:
            pre_path = entry["_pre_abs"]
            cid = self._frame_cluster.get(pre_path, -1)
            if cid < 0 or cid >= len(self._clusters):
                continue
            label = self._clusters[cid].label
            interval = entry.get("interval_sec", 0)
            if interval > 0:
                cluster_intervals[label].append(interval)

        timing = {}
        for label, intervals in cluster_intervals.items():
            if intervals:
                timing[label] = {
                    "mean": round(sum(intervals) / len(intervals), 2),
                    "min": round(min(intervals), 2),
                    "max": round(max(intervals), 2),
                    "count": len(intervals),
                }
        return timing

    def _extract_conditional_rules(self) -> List[dict]:
        rules = []
        for cluster in self._clusters:
            if cluster.label == "gameplay":
                continue
            if not cluster.tap_positions:
                continue

            xs = [t[0] for t in cluster.tap_positions]
            ys = [t[1] for t in cluster.tap_positions]
            var_x = np.var(xs) if xs else 0
            var_y = np.var(ys) if ys else 0

            # Zone 기반 규칙 추가
            zone_counts = Counter(cluster.tap_zones)
            dominant_zone = zone_counts.most_common(1)[0] if zone_counts else None

            if var_x < 2500 and var_y < 2500 and len(xs) >= 2:
                rules.append({
                    "type": "fixed_tap",
                    "screen": cluster.label,
                    "x": int(np.mean(xs)),
                    "y": int(np.mean(ys)),
                    "zone": dominant_zone[0] if dominant_zone else "unknown",
                    "confidence": min(1.0, len(xs) / 5),
                    "source": f"cluster_{cluster.cluster_id}",
                })
            elif len(xs) >= 3:
                tap_groups = self._cluster_taps(cluster.tap_positions)
                for (cx, cy), members in tap_groups:
                    rules.append({
                        "type": "tap_option",
                        "screen": cluster.label,
                        "x": cx, "y": cy,
                        "zone": tap_to_zone(cx, cy),
                        "count": len(members),
                        "confidence": len(members) / len(xs),
                        "source": f"cluster_{cluster.cluster_id}",
                    })

        return rules

    # -----------------------------------------------------------------------
    # Save / Load
    # -----------------------------------------------------------------------
    def save(self, db: LearnedDB, output_path: Path):
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "game_id": db.game_id,
            "version": db.version,
            "demo_sessions": db.demo_sessions,
            "total_frames": db.total_frames,
            "clusters": db.clusters,
            "action_patterns": db.action_patterns,
            "zone_patterns": db.zone_patterns,
            "patch_patterns": db.patch_patterns,
            "screen_flow": db.screen_flow,
            "timing": db.timing,
            "conditional_rules": db.conditional_rules,
        }

        output_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[Learn] DB saved: {output_path}")

    @staticmethod
    def load(db_path: Path) -> LearnedDB:
        data = json.loads(Path(db_path).read_text(encoding="utf-8"))
        return LearnedDB(
            game_id=data["game_id"],
            version=data.get("version", "v1"),
            demo_sessions=data.get("demo_sessions", 0),
            total_frames=data.get("total_frames", 0),
            clusters={int(k): v for k, v in data.get("clusters", {}).items()},
            action_patterns=data.get("action_patterns", []),
            zone_patterns=data.get("zone_patterns", []),
            patch_patterns=data.get("patch_patterns", []),
            screen_flow=data.get("screen_flow", {}),
            timing=data.get("timing", {}),
            conditional_rules=data.get("conditional_rules", []),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Learning Engine V2 — Zone + Patch based"
    )
    parser.add_argument("--game", required=True, help="Game ID")
    parser.add_argument("--demos", nargs="+", required=True,
                        help="Demo directories")
    parser.add_argument("--output", default=None, help="Output DB path")
    args = parser.parse_args()

    engine = LearningEngine(args.game)
    for demo in args.demos:
        engine.add_demo(Path(demo))

    db = engine.learn()

    output = Path(args.output) if args.output else Path(
        f"E:/AI/virtual_player/data/games/{args.game}/learned_db.json"
    )
    engine.save(db, output)


if __name__ == "__main__":
    main()
