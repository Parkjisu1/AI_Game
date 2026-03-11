"""
Learning Engine — 데모 데이터 → 학습 DB 변환
===============================================
사람 플레이 3~5판의 demo_log.jsonl을 분석하여
AI가 즉시 사용 가능한 행동 DB를 생성.

핵심: Vision API 없이 동작 (비용 0)
  - 화면 분류: 이미지 해시 유사도 클러스터링
  - 행동 매핑: 화면 클러스터 → 탭 좌표 통계
  - 전략 추출: 상황→행동 조건부 규칙

파이프라인:
  demo_log.jsonl + screenshots
       ↓
  [1] Screen Clustering (pHash)
       ↓
  [2] Action Pattern Extraction
       ↓
  [3] Timing Pattern Extraction
       ↓
  [4] Conditional Rule Extraction
       ↓
  learned_db.json (AI가 바로 사용)
"""

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


# ---------------------------------------------------------------------------
# Image Hashing (Vision API 없이 화면 유사도 비교)
# ---------------------------------------------------------------------------
def phash(img_path: Path, hash_size: int = 16) -> Optional[np.ndarray]:
    """Perceptual Hash — 이미지를 64bit 해시로 변환.

    유사한 화면은 해밍 거리가 가까움.
    """
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    resized = cv2.resize(img, (hash_size + 1, hash_size))
    diff = resized[:, 1:] > resized[:, :-1]
    return diff.flatten()


def hamming_distance(h1: np.ndarray, h2: np.ndarray) -> int:
    """두 해시 간 해밍 거리."""
    return int(np.sum(h1 != h2))


def region_fingerprint(img_path: Path) -> Optional[np.ndarray]:
    """화면 영역별 밝기 fingerprint.

    화면을 6x10 그리드로 나누고 각 셀의 평균 밝기를 벡터로.
    pHash보다 구조적 차이(UI 레이아웃)에 민감.
    """
    img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    resized = cv2.resize(img, (60, 100))
    # 6x10 그리드
    grid = resized.reshape(10, 10, 6, 10).mean(axis=(1, 3))
    return grid.flatten()


def fingerprint_distance(f1: np.ndarray, f2: np.ndarray) -> float:
    """Fingerprint 간 유클리드 거리 (정규화)."""
    return float(np.sqrt(np.sum((f1.astype(float) - f2.astype(float)) ** 2)))


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------
@dataclass
class ScreenCluster:
    """화면 유형 클러스터."""
    cluster_id: int
    label: str                          # 자동 추정 or 사용자 지정
    sample_paths: List[str] = field(default_factory=list)
    center_hash: Optional[np.ndarray] = None
    center_fingerprint: Optional[np.ndarray] = None
    tap_positions: List[Tuple[int, int]] = field(default_factory=list)
    transitions_to: Dict[int, int] = field(default_factory=dict)  # cluster_id → count


@dataclass
class ActionPattern:
    """화면별 행동 패턴."""
    cluster_id: int
    cluster_label: str
    tap_x: int
    tap_y: int
    tap_count: int              # 이 위치가 탭된 횟수
    success_count: int          # 화면 전이가 발생한 횟수
    avg_interval: float         # 평균 탭 간격
    next_cluster: int = -1      # 탭 후 가장 빈번한 다음 화면
    confidence: float = 0.0


@dataclass
class LearnedDB:
    """학습된 행동 DB. AI가 플레이에 사용."""
    game_id: str
    demo_sessions: int = 0
    total_frames: int = 0
    clusters: Dict[int, dict] = field(default_factory=dict)
    action_patterns: List[dict] = field(default_factory=list)
    screen_flow: Dict[str, List[str]] = field(default_factory=dict)
    timing: dict = field(default_factory=dict)
    conditional_rules: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Learning Engine
# ---------------------------------------------------------------------------
class LearningEngine:
    """데모 데이터에서 학습 DB를 생성.

    사용법:
        engine = LearningEngine("carmatch")
        engine.add_demo("path/to/demo_20260306_100000")
        engine.add_demo("path/to/demo_20260306_110000")  # 여러 세션 누적
        db = engine.learn()
        engine.save(db, "path/to/learned_db.json")
    """

    CLUSTER_THRESHOLD_HASH = 40       # 해밍 거리 이하 = 같은 클러스터
    CLUSTER_THRESHOLD_FP = 800        # fingerprint 거리 이하 = 같은 클러스터
    TAP_CLUSTER_RADIUS = 80           # 80px 내 탭은 같은 버튼으로 간주

    # 화면 라벨 자동 추정 힌트 (탭 위치 + 결과로 추정)
    LABEL_HINTS = {
        "lobby": {"tap_y_range": (1300, 1700), "next_is_gameplay": True},
        "win": {"tap_y_range": (900, 1300), "next_is_lobby": True},
        "fail": {"tap_y_range": (600, 900), "has_retry": True},
        "popup": {"has_close_x": True},
    }

    def __init__(self, game_id: str):
        self.game_id = game_id
        self._all_frames: List[dict] = []       # 모든 세션의 프레임
        self._frame_hashes: Dict[str, np.ndarray] = {}
        self._frame_fps: Dict[str, np.ndarray] = {}
        self._clusters: List[ScreenCluster] = []
        self._frame_cluster: Dict[str, int] = {}  # frame_path → cluster_id

    def add_demo(self, demo_dir: Path):
        """데모 세션 추가."""
        demo_dir = Path(demo_dir)
        log_path = demo_dir / "demo_log.jsonl"
        if not log_path.exists():
            print(f"[Learn] Log not found: {log_path}")
            return

        entries = []
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    # 절대 경로로 변환
                    entry["_demo_dir"] = str(demo_dir)
                    entry["_pre_abs"] = str(demo_dir / entry["pre_screenshot"])
                    entry["_post_abs"] = str(demo_dir / entry["post_screenshot"])
                    entries.append(entry)

        self._all_frames.extend(entries)
        print(f"[Learn] Added {len(entries)} frames from {demo_dir.name}")

    def learn(self) -> LearnedDB:
        """전체 학습 파이프라인 실행."""
        if not self._all_frames:
            print("[Learn] No frames to learn from!")
            return LearnedDB(game_id=self.game_id)

        print(f"[Learn] Total frames: {len(self._all_frames)}")

        # Step 1: 이미지 해시 계산
        self._compute_hashes()

        # Step 2: 화면 클러스터링
        self._cluster_screens()

        # Step 3: 클러스터 라벨 추정
        self._estimate_labels()

        # Step 4: 행동 패턴 추출
        patterns = self._extract_patterns()

        # Step 5: 전이 그래프
        flow = self._extract_flow()

        # Step 6: 타이밍 패턴
        timing = self._extract_timing()

        # Step 7: 조건부 규칙
        rules = self._extract_conditional_rules()

        # DB 구성
        db = LearnedDB(
            game_id=self.game_id,
            demo_sessions=len(set(
                e.get("_demo_dir", "") for e in self._all_frames
            )),
            total_frames=len(self._all_frames),
            clusters={
                c.cluster_id: {
                    "label": c.label,
                    "sample_count": len(c.sample_paths),
                    "samples": c.sample_paths[:5],
                }
                for c in self._clusters
            },
            action_patterns=[
                {
                    "cluster": p.cluster_id,
                    "label": p.cluster_label,
                    "x": p.tap_x,
                    "y": p.tap_y,
                    "count": p.tap_count,
                    "success": p.success_count,
                    "confidence": round(p.confidence, 2),
                    "avg_interval": round(p.avg_interval, 2),
                    "next_cluster": p.next_cluster,
                }
                for p in patterns
            ],
            screen_flow=flow,
            timing=timing,
            conditional_rules=rules,
        )

        print(f"[Learn] Clusters: {len(db.clusters)}")
        print(f"[Learn] Action patterns: {len(db.action_patterns)}")
        print(f"[Learn] Flow transitions: {sum(len(v) for v in flow.values())}")
        print(f"[Learn] Conditional rules: {len(rules)}")

        return db

    def _compute_hashes(self):
        """모든 프레임의 이미지 해시 + fingerprint 계산."""
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

    def _cluster_screens(self):
        """이미지 해시 기반 화면 클러스터링."""
        print("[Learn] Clustering screens...")
        paths = list(self._frame_hashes.keys())
        assigned = {}  # path → cluster_id
        clusters = []

        for path in paths:
            h = self._frame_hashes[path]
            fp = self._frame_fps.get(path)

            best_cluster = -1
            best_dist = float("inf")

            for cluster in clusters:
                # 해시 거리
                if cluster.center_hash is not None:
                    dist_h = hamming_distance(h, cluster.center_hash)
                else:
                    dist_h = 999

                # Fingerprint 거리
                if fp is not None and cluster.center_fingerprint is not None:
                    dist_fp = fingerprint_distance(fp, cluster.center_fingerprint)
                else:
                    dist_fp = 999

                # 두 메트릭 모두 임계값 이하
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
                # 새 클러스터
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

    def _estimate_labels(self):
        """클러스터 라벨 자동 추정."""
        print("[Learn] Estimating cluster labels...")

        # 각 클러스터의 탭 패턴 수집
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

        # 전이 패턴 수집
        for i in range(len(self._all_frames) - 1):
            pre_path = self._all_frames[i]["_pre_abs"]
            next_path = self._all_frames[i + 1]["_pre_abs"]
            cid = self._frame_cluster.get(pre_path, -1)
            next_cid = self._frame_cluster.get(next_path, -1)
            if cid >= 0 and next_cid >= 0 and cid != next_cid:
                self._clusters[cid].transitions_to[next_cid] = \
                    self._clusters[cid].transitions_to.get(next_cid, 0) + 1

        # 탭 패턴 기반 라벨 추정
        gameplay_cid = -1
        max_taps = 0
        for cluster in self._clusters:
            # 가장 많이 탭된 클러스터 = gameplay
            if len(cluster.tap_positions) > max_taps:
                max_taps = len(cluster.tap_positions)
                gameplay_cid = cluster.cluster_id

        if gameplay_cid >= 0:
            self._clusters[gameplay_cid].label = "gameplay"

        for cluster in self._clusters:
            if cluster.cluster_id == gameplay_cid:
                continue

            # gameplay으로 전이하는 클러스터 = lobby
            if gameplay_cid in cluster.transitions_to:
                if cluster.transitions_to[gameplay_cid] >= 1:
                    cluster.label = "lobby"
                    continue

            # gameplay에서 오는 클러스터 = win 또는 fail
            for other in self._clusters:
                if other.cluster_id == gameplay_cid:
                    if cluster.cluster_id in other.transitions_to:
                        # 탭 위치 분석으로 win/fail 구분
                        avg_y = (
                            sum(y for _, y in cluster.tap_positions) /
                            len(cluster.tap_positions)
                            if cluster.tap_positions else 960
                        )
                        if avg_y > 1000:
                            cluster.label = "win"
                        else:
                            cluster.label = "fail"

            # 아직 미분류 = popup
            if cluster.label.startswith("screen_"):
                cluster.label = "popup"

        for c in self._clusters:
            print(f"  Cluster {c.cluster_id}: {c.label} ({len(c.sample_paths)} samples)")

    def _extract_patterns(self) -> List[ActionPattern]:
        """화면별 탭 패턴 추출."""
        patterns = []

        for cluster in self._clusters:
            if not cluster.tap_positions:
                continue

            # 탭 좌표 클러스터링
            tap_groups = self._cluster_taps(cluster.tap_positions)

            for (cx, cy), members in tap_groups:
                # 성공률: 이 위치 탭 후 다른 화면으로 전이된 비율
                success = 0
                intervals = []
                next_clusters = Counter()

                for entry in self._all_frames:
                    pre_path = entry["_pre_abs"]
                    cid = self._frame_cluster.get(pre_path, -1)
                    if cid != cluster.cluster_id:
                        continue

                    action = entry.get("action", {})
                    if action.get("type") != "tap":
                        continue

                    ax, ay = action["x"], action["y"]
                    if abs(ax - cx) < self.TAP_CLUSTER_RADIUS and \
                       abs(ay - cy) < self.TAP_CLUSTER_RADIUS:
                        intervals.append(entry.get("interval_sec", 0))

                # 다음 프레임 전이 체크
                for i, entry in enumerate(self._all_frames[:-1]):
                    pre_path = entry["_pre_abs"]
                    cid = self._frame_cluster.get(pre_path, -1)
                    if cid != cluster.cluster_id:
                        continue

                    action = entry.get("action", {})
                    if action.get("type") != "tap":
                        continue

                    ax, ay = action["x"], action["y"]
                    if abs(ax - cx) < self.TAP_CLUSTER_RADIUS and \
                       abs(ay - cy) < self.TAP_CLUSTER_RADIUS:
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

                patterns.append(ActionPattern(
                    cluster_id=cluster.cluster_id,
                    cluster_label=cluster.label,
                    tap_x=cx,
                    tap_y=cy,
                    tap_count=len(members),
                    success_count=success,
                    avg_interval=avg_interval,
                    next_cluster=most_common_next,
                    confidence=success / max(len(members), 1),
                ))

        # 신뢰도 순 정렬
        patterns.sort(key=lambda p: -p.confidence)
        return patterns

    def _cluster_taps(
        self, taps: List[Tuple[int, int]]
    ) -> List[Tuple[Tuple[int, int], List[Tuple[int, int]]]]:
        """탭 좌표를 클러스터로 묶기."""
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
        """화면 전이 그래프 (라벨 기반)."""
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
        """타이밍 패턴 추출."""
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
        """조건부 규칙 추출.

        "이 화면에서 N번 탭했는데 변화 없으면 → 다른 위치 탭"
        "이 화면에서 항상 같은 위치 → 고정 핸들러"
        """
        rules = []

        for cluster in self._clusters:
            if cluster.label == "gameplay":
                continue

            if not cluster.tap_positions:
                continue

            # 탭 위치 분산 분석
            xs = [t[0] for t in cluster.tap_positions]
            ys = [t[1] for t in cluster.tap_positions]
            var_x = np.var(xs) if xs else 0
            var_y = np.var(ys) if ys else 0

            if var_x < 2500 and var_y < 2500 and len(xs) >= 2:
                # 항상 같은 위치 → 고정 핸들러
                rules.append({
                    "type": "fixed_tap",
                    "screen": cluster.label,
                    "x": int(np.mean(xs)),
                    "y": int(np.mean(ys)),
                    "confidence": min(1.0, len(xs) / 5),
                    "source": f"cluster_{cluster.cluster_id}",
                })
            elif len(xs) >= 3:
                # 여러 위치 → 순차 탭
                tap_groups = self._cluster_taps(cluster.tap_positions)
                for (cx, cy), members in tap_groups:
                    rules.append({
                        "type": "tap_option",
                        "screen": cluster.label,
                        "x": cx,
                        "y": cy,
                        "count": len(members),
                        "confidence": len(members) / len(xs),
                        "source": f"cluster_{cluster.cluster_id}",
                    })

        return rules

    # -----------------------------------------------------------------------
    # Save / Load
    # -----------------------------------------------------------------------
    def save(self, db: LearnedDB, output_path: Path):
        """학습 DB를 JSON으로 저장."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "game_id": db.game_id,
            "demo_sessions": db.demo_sessions,
            "total_frames": db.total_frames,
            "clusters": db.clusters,
            "action_patterns": db.action_patterns,
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
        """저장된 학습 DB 로드."""
        data = json.loads(Path(db_path).read_text(encoding="utf-8"))
        return LearnedDB(
            game_id=data["game_id"],
            demo_sessions=data.get("demo_sessions", 0),
            total_frames=data.get("total_frames", 0),
            clusters={int(k): v for k, v in data.get("clusters", {}).items()},
            action_patterns=data.get("action_patterns", []),
            screen_flow=data.get("screen_flow", {}),
            timing=data.get("timing", {}),
            conditional_rules=data.get("conditional_rules", []),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Learning Engine — Learn from demos")
    parser.add_argument("--game", required=True, help="Game ID")
    parser.add_argument("--demos", nargs="+", required=True, help="Demo directories")
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
