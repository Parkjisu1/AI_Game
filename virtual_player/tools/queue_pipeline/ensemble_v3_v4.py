"""
v3 (single-stream) + v4 (pair-based) 결과 앙상블.

두 알고리즘이 서로 다른 방식으로 noise를 다루므로,
"두 알고리즘이 모두 인정한 색"만 채택하면 false positive 크게 감소 기대.

전략 2가지:
  1. STRICT_INTERSECTION: v3 색 집합 ∩ v4 색 집합 (교집합만 유지)
  2. CONFIDENCE_WEIGHTED: v3 position 순서 유지하되 v4에 없는 색은 제거

Output: queue_full_per_level_ensemble.json (v3 스키마와 호환)
"""
import argparse
import json
import sys
from pathlib import Path


def queue_colors(level_info):
    """v3 schema (queue 필드) or v4 schema (queue_sequence 필드) 지원."""
    if "queue" in level_info and isinstance(level_info["queue"], list):
        return [c["color"] for c in level_info["queue"]]
    elif "queue_sequence" in level_info:
        return list(level_info["queue_sequence"])
    return []


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--v3", required=True, type=Path)
    p.add_argument("--v4", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--mode", choices=["intersection", "confidence_weighted"],
                   default="confidence_weighted")
    args = p.parse_args()

    v3 = json.loads(args.v3.read_text(encoding="utf-8"))
    v4 = json.loads(args.v4.read_text(encoding="utf-8"))

    v3_levels = v3["levels"]
    v4_levels = v4["levels"]

    result = {}
    stats = {"both": 0, "v3_only": 0, "v4_only": 0, "neither": 0}
    for lv_key in sorted(set(v3_levels.keys()) | set(v4_levels.keys()), key=lambda x: int(x)):
        v3_info = v3_levels.get(lv_key, {})
        v4_info = v4_levels.get(lv_key, {})
        v3_colors_list = queue_colors(v3_info)
        v4_colors_list = queue_colors(v4_info)
        v3_set = set(v3_colors_list)
        v4_set = set(v4_colors_list)

        if v3_set and v4_set:
            stats["both"] += 1
        elif v3_set:
            stats["v3_only"] += 1
        elif v4_set:
            stats["v4_only"] += 1
        else:
            stats["neither"] += 1

        if args.mode == "intersection":
            ensemble_colors = v3_set & v4_set
            # Queue: v3 position 순서대로 ensemble_colors만 남김
            ensemble_queue = [c for c in v3_colors_list if c in ensemble_colors]
        else:  # confidence_weighted
            # v3 순서 유지 + v4 색 집합에 있는 색만 필터
            # v4 색 집합에 없지만 v3만 단독 식별한 색도 포함 (confidence 1개라도 있으면)
            if v4_set:
                ensemble_queue = [c for c in v3_colors_list if c in v4_set]
            else:
                ensemble_queue = v3_colors_list[:]  # v4 데이터 없으면 v3 그대로

        qlen = len(ensemble_queue)
        result[lv_key] = {
            "queue_length": qlen,
            "queue_sequence": ensemble_queue,
            "colors_used": {c: ensemble_queue.count(c) for c in set(ensemble_queue)},
            "v3_len": len(v3_colors_list),
            "v4_len": len(v4_colors_list),
            "v3_color_set": sorted(v3_set),
            "v4_color_set": sorted(v4_set),
            "intersection_set": sorted(v3_set & v4_set),
            "recovery_confidence": ("A" if qlen >= 20 else "B" if qlen >= 10 else "C" if qlen >= 3 else "F"),
        }

    summary = {
        "v3_source": str(args.v3),
        "v4_source": str(args.v4),
        "mode": args.mode,
        "total_levels": len(result),
        "stats": stats,
        "total_queue_entries": sum(v["queue_length"] for v in result.values()),
        "recovery_distribution": {
            g: sum(1 for v in result.values() if v["recovery_confidence"] == g)
            for g in "ABCF"
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"summary": summary, "levels": result}, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
