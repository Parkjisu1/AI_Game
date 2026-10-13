"""
stage3_timeseries.py — 레벨별 queue 시퀀스 복원.

queue_all_observations.jsonl (이미지별 holder 관찰) →
queue_full_per_level.json (레벨별 전체 queue 순서)

알고리즘:
    1. 레벨별 관찰 그룹화 → seq 순 정렬
    2. Slot 식별: 각 프레임의 holder bbox center 클러스터링
       — 같은 위치(±TOL)에서 색이 바뀌면 slot의 holder가 교체된 것
    3. Queue 소모 추적:
       — 프레임 t1에 slot S가 color X → 프레임 t2에 slot S가 color Y
       — X는 소모됨, Y가 새로 들어옴
    4. 전체 queue 복원:
       — 각 slot의 색 변화 이력 = 해당 slot을 통과한 holder 목록
       — 가장 많이 변화한 slot (head slot) = queue 전체 순서
       — 여러 slot이 있는 레벨은 slot별 sequence 결합

Recovery confidence:
    A = 관찰 100+장, slot tracking 안정
    B = 관찰 10~100장
    C = 관찰 <10장 (단일 스냅샷 수준)

Usage:
    python stage3_timeseries.py \
        --observations E:/AI/.../queue_all_observations.jsonl \
        --output E:/AI/.../queue_full_per_level.json \
        --position-tolerance 40 \
        --min-conf 0.3
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def group_by_level(jsonl_path: Path) -> dict:
    """레벨별 관찰 그룹화 + seq 순 정렬."""
    by_level = defaultdict(list)
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            by_level[rec["level"]].append(rec)
    for lv in by_level:
        by_level[lv].sort(key=lambda r: r["seq"])
    return dict(by_level)


def match_slots(prev_holders, curr_holders, tol=40):
    """
    이전 프레임 holder와 현재 프레임 holder 간 위치 매칭.

    Returns: (matches [(p_idx, c_idx)], unmatched_prev [idx...], unmatched_curr [idx...])
    """
    matches = []
    used_curr = set()
    for pi, ph in enumerate(prev_holders):
        best_ci, best_d = -1, float("inf")
        for ci, ch in enumerate(curr_holders):
            if ci in used_curr:
                continue
            d = ((ph["cx"] - ch["cx"]) ** 2 + (ph["cy"] - ch["cy"]) ** 2) ** 0.5
            if d < best_d and d <= tol:
                best_d, best_ci = d, ci
        if best_ci >= 0:
            matches.append((pi, best_ci))
            used_curr.add(best_ci)

    unmatched_prev = [i for i in range(len(prev_holders)) if i not in {m[0] for m in matches}]
    unmatched_curr = [i for i in range(len(curr_holders)) if i not in used_curr]
    return matches, unmatched_prev, unmatched_curr


def cluster_slots(observations, tol=40):
    """
    모든 프레임의 holder 위치를 클러스터링하여 slot 정의.

    Returns: [{"slot_id": int, "cx": float, "cy": float, "count": int}, ...]
    """
    all_positions = []
    for obs in observations:
        for h in obs["holders"]:
            all_positions.append((h["cx"], h["cy"]))
    if not all_positions:
        return []

    clusters = []
    for cx, cy in all_positions:
        assigned = False
        for cl in clusters:
            d = ((cl["cx"] - cx) ** 2 + (cl["cy"] - cy) ** 2) ** 0.5
            if d <= tol:
                n = cl["count"]
                cl["cx"] = (cl["cx"] * n + cx) / (n + 1)
                cl["cy"] = (cl["cy"] * n + cy) / (n + 1)
                cl["count"] += 1
                assigned = True
                break
        if not assigned:
            clusters.append({"cx": cx, "cy": cy, "count": 1})

    clusters.sort(key=lambda c: (c["cy"], c["cx"]))
    for i, c in enumerate(clusters):
        c["slot_id"] = i
    return clusters


def assign_slot(holder, slots, tol):
    best_id, best_d = -1, float("inf")
    for sl in slots:
        d = ((sl["cx"] - holder["cx"]) ** 2 + (sl["cy"] - holder["cy"]) ** 2) ** 0.5
        if d < best_d and d <= tol:
            best_d, best_id = d, sl["slot_id"]
    return best_id


def reconstruct_level(observations, tol=40, min_conf=0.3):
    """단일 레벨의 관찰들 → queue 시퀀스 복원."""
    obs = [o for o in observations if o["holder_count"] > 0]
    if not obs:
        return {
            "total_observations": len(observations),
            "valid_observations": 0,
            "recovery_confidence": "F",
            "full_queue_sequence": [],
            "total_queue_length": 0,
            "colors_used": {},
            "slots": [],
            "notes": "no valid holder observations",
        }

    slots = cluster_slots(obs, tol=tol)
    slot_history = {sl["slot_id"]: [] for sl in slots}

    for o in obs:
        for h in o["holders"]:
            if h["conf"] < min_conf:
                continue
            slot_id = assign_slot(h, slots, tol)
            if slot_id < 0:
                continue
            hist = slot_history[slot_id]
            if not hist or hist[-1]["name"] != h["name"]:
                hist.append({
                    "name": h["name"],
                    "class": h["class"],
                    "first_seen_seq": o["seq"],
                    "first_seen_file": o["filename"],
                    "conf": h["conf"],
                })
            else:
                hist[-1]["conf"] = max(hist[-1]["conf"], h["conf"])

    # head slot = 가장 많은 색 변화를 본 slot
    head_slot_id = max(slot_history.keys(), key=lambda k: len(slot_history[k])) if slot_history else -1
    full_sequence = []
    if head_slot_id >= 0:
        for i, entry in enumerate(slot_history[head_slot_id]):
            full_sequence.append({
                "order": i,
                "color": entry["name"],
                "class_id": entry["class"],
                "first_seen_seq": entry["first_seen_seq"],
                "first_seen_file": entry["first_seen_file"],
            })

    colors_used = defaultdict(int)
    for entry in full_sequence:
        colors_used[entry["color"]] += 1

    n_obs = len(observations)
    if n_obs >= 100:
        conf = "A"
    elif n_obs >= 10:
        conf = "B"
    elif n_obs >= 1:
        conf = "C"
    else:
        conf = "F"

    return {
        "total_observations": n_obs,
        "valid_observations": len(obs),
        "recovery_confidence": conf,
        "slot_count": len(slots),
        "head_slot_id": head_slot_id,
        "full_queue_sequence": full_sequence,
        "total_queue_length": len(full_sequence),
        "colors_used": dict(sorted(colors_used.items(), key=lambda x: -x[1])),
        "slots": [
            {
                "slot_id": sl["slot_id"],
                "center": [round(sl["cx"], 1), round(sl["cy"], 1)],
                "observed_count": sl["count"],
                "color_changes": len(slot_history.get(sl["slot_id"], [])),
            }
            for sl in slots
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--observations", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--position-tolerance", type=int, default=40, help="Slot 클러스터링 허용 범위 (px)")
    p.add_argument("--min-conf", type=float, default=0.3, help="이 이하 confidence는 slot tracking에서 제외")
    args = p.parse_args()

    if not args.observations.exists():
        print(f"ERROR: observations not found: {args.observations}", file=sys.stderr)
        return 2

    print(f"Loading: {args.observations}")
    by_level = group_by_level(args.observations)
    print(f"Levels: {len(by_level)}")

    result = {}
    counts = {"A": 0, "B": 0, "C": 0, "F": 0}
    total_queue_len = 0
    for level, obs in sorted(by_level.items()):
        info = reconstruct_level(obs, tol=args.position_tolerance, min_conf=args.min_conf)
        result[str(level)] = info
        counts[info["recovery_confidence"]] += 1
        total_queue_len += info["total_queue_length"]

    summary = {
        "source": str(args.observations),
        "total_levels": len(result),
        "recovery_distribution": counts,
        "total_queue_entries": total_queue_len,
        "parameters": {
            "position_tolerance": args.position_tolerance,
            "min_conf": args.min_conf,
        },
    }

    payload = {"summary": summary, "levels": result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nOutput: {args.output}")

    top = sorted(result.items(), key=lambda x: -x[1]["total_queue_length"])[:10]
    print("\nTop 10 recovered queues (longest):")
    for lv, info in top:
        cu = ", ".join(f"{k}:{v}" for k, v in list(info["colors_used"].items())[:5])
        print(f"  L{lv}: len={info['total_queue_length']} conf={info['recovery_confidence']} obs={info['total_observations']} slots={info['slot_count']} colors=[{cu}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
