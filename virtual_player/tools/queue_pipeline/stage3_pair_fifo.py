"""
stage3_pair_fifo.py — Before/After 페어 기반 확정 소비 추출 (v4).

v3의 한계:
    - Before frames만 사용 → 연속 frame 간 비교
    - Noise로 인한 hallucinated 소비 이벤트 다수 (Jaccard 0.44)
    - Detection noise가 장시간 세션에서 누적

v4 개선 (페어 기반):
    - 동일 seq의 before.png + after.png 페어 조회
    - 단일 tap 이벤트 전/후 비교 = 최소 noise 관찰
    - Before multiset - After multiset = 확정 소비 색상
    - After multiset - Before multiset = 확정 공급 색상
    - 1 tap = 1 소비 + ≤1 공급 (FIFO) 충족 시에만 이벤트로 기록
    - 세션 개념 불필요 (페어 자체가 atomic event)

이득:
    - 각 페어는 독립적 → detection noise가 이벤트 간 전파 안 됨
    - 세션 내 drift 없음
    - Before/After 둘 다 틀려야 잘못된 이벤트 발생 (확률 매우 낮음)

Output:
    queue_full_per_level_v4.json
        - 레벨별 확정 소비 시퀀스 (seq 순 정렬)
        - 각 이벤트마다 before/after state 기록 (검증용)

Usage:
    python stage3_pair_fifo.py \
        --before .../queue_all_observations.jsonl \
        --after  .../queue_all_observations_after.jsonl \
        --output .../queue_full_per_level_v4.json \
        --min-conf 0.5
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_jsonl_by_key(jsonl_path: Path):
    """JSONL → {(level, seq): record}"""
    by_key = {}
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            by_key[(rec["level"], rec["seq"])] = rec
    return by_key


def holder_counter(rec, min_conf=0.5):
    return Counter(
        h["name"]
        for h in rec.get("holders", [])
        if h.get("conf", 0) >= min_conf and h.get("class", 99) <= 28
    )


def analyze_pair(before_rec, after_rec, min_conf=0.5, strict=False):
    """
    단일 (before, after) 페어 분석.

    strict=False (default): fifo_shift + tail_empty 모두 valid
    strict=True: fifo_shift (nc==1 AND nn==1)만 valid — noise 최소화
    """
    b = holder_counter(before_rec, min_conf=min_conf)
    a = holder_counter(after_rec, min_conf=min_conf)
    consumed_set = b - a
    new_set = a - b
    nc = sum(consumed_set.values())
    nn = sum(new_set.values())
    reason = ""
    valid = False
    consumed = None
    new_holder = None
    if nc == 0 and nn == 0:
        reason = "no_change"
    elif nc == 1 and nn == 1:
        valid = True
        consumed = next(iter(consumed_set.keys()))
        new_holder = next(iter(new_set.keys()))
        reason = "fifo_shift"
    elif nc == 1 and nn == 0:
        if not strict:
            valid = True
            consumed = next(iter(consumed_set.keys()))
        reason = "tail_empty"
    elif nc > 1 or nn > 1:
        reason = f"multi_change_nc{nc}_na{nn}"
    elif nc == 0 and nn >= 1:
        reason = "appeared_only"
    return {
        "valid": valid,
        "consumed": consumed,
        "new": new_holder,
        "reason": reason,
        "before_state": dict(b),
        "after_state": dict(a),
    }


def reconstruct_level(events):
    """레벨의 확정 이벤트들(순서 이미 seq 정렬) → queue 시퀀스."""
    consumed_seq = [e["consumed"] for e in events if e["valid"]]
    colors_used = Counter(consumed_seq)
    reason_dist = Counter(e["reason"] for e in events)
    return {
        "queue_sequence": consumed_seq,
        "queue_length": len(consumed_seq),
        "colors_used": dict(colors_used.most_common()),
        "total_pairs": len(events),
        "valid_pairs": sum(1 for e in events if e["valid"]),
        "reason_distribution": dict(reason_dist),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--before", required=True, type=Path)
    p.add_argument("--after", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--min-conf", type=float, default=0.5)
    p.add_argument("--strict", action="store_true",
                   help="fifo_shift(1 소비+1 공급)만 valid. tail_empty 제외.")
    p.add_argument("--dump-events", action="store_true",
                   help="각 이벤트의 before/after state 전체를 출력 (파일 커짐)")
    args = p.parse_args()

    if not args.before.exists():
        print(f"ERROR: before JSONL not found: {args.before}", file=sys.stderr)
        return 2
    if not args.after.exists():
        print(f"ERROR: after JSONL not found: {args.after}", file=sys.stderr)
        return 2

    print(f"Loading before: {args.before}")
    before_map = load_jsonl_by_key(args.before)
    print(f"  {len(before_map)} records")
    print(f"Loading after:  {args.after}")
    after_map = load_jsonl_by_key(args.after)
    print(f"  {len(after_map)} records")

    # Pair up by (level, seq)
    common_keys = set(before_map.keys()) & set(after_map.keys())
    only_before = set(before_map.keys()) - set(after_map.keys())
    only_after = set(after_map.keys()) - set(before_map.keys())
    print(f"\nPair stats:")
    print(f"  paired:      {len(common_keys)}")
    print(f"  only_before: {len(only_before)}")
    print(f"  only_after:  {len(only_after)}")

    # Group by level, sort by seq
    by_level = defaultdict(list)
    for (lv, seq) in common_keys:
        by_level[lv].append(seq)
    for lv in by_level:
        by_level[lv].sort()

    # Analyze
    result = {}
    overall_reason_dist = Counter()
    for lv, seqs in sorted(by_level.items()):
        events = []
        for seq in seqs:
            b = before_map[(lv, seq)]
            a = after_map[(lv, seq)]
            evt = analyze_pair(b, a, min_conf=args.min_conf, strict=args.strict)
            evt["seq"] = seq
            overall_reason_dist[evt["reason"]] += 1
            if not args.dump_events:
                evt.pop("before_state", None)
                evt.pop("after_state", None)
            events.append(evt)
        info = reconstruct_level(events)
        info["level"] = lv

        # Recovery grade
        qlen = info["queue_length"]
        valid_ratio = info["valid_pairs"] / info["total_pairs"] if info["total_pairs"] > 0 else 0
        if qlen >= 20 and valid_ratio >= 0.3:
            grade = "A"
        elif qlen >= 10:
            grade = "B"
        elif qlen >= 3:
            grade = "C"
        else:
            grade = "F"
        info["recovery_confidence"] = grade
        info["valid_ratio"] = round(valid_ratio, 3)

        # Keep events only if dump requested, else strip for size
        if args.dump_events:
            info["events"] = events
        result[str(lv)] = info

    counts = Counter(v["recovery_confidence"] for v in result.values())
    total_q = sum(v["queue_length"] for v in result.values())

    summary = {
        "before_jsonl": str(args.before),
        "after_jsonl": str(args.after),
        "total_levels": len(result),
        "total_pairs": sum(len(v) for v in by_level.values()),
        "recovery_distribution": dict(counts),
        "total_queue_entries": total_q,
        "pair_reason_distribution": dict(overall_reason_dist.most_common()),
        "parameters": {"min_conf": args.min_conf},
    }

    payload = {"summary": summary, "levels": result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nOutput: {args.output}")

    top = sorted(result.items(), key=lambda x: -x[1]["queue_length"])[:15]
    print("\n--- Top 15 longest queues ---")
    for lv, info in top:
        q_preview = " ".join(
            c.replace("holder_", "") for c in info["queue_sequence"][:10]
        )
        tail = " …" if info["queue_length"] > 10 else ""
        print(f"  L{lv}: len={info['queue_length']} conf={info['recovery_confidence']} "
              f"valid={info['valid_pairs']}/{info['total_pairs']} "
              f"({info['valid_ratio']:.2f})")
        print(f"       [{q_preview}{tail}]")

    print("\n--- L1~L10 (튜토리얼) ---")
    for lv in range(1, 11):
        info = result.get(str(lv))
        if not info:
            print(f"  L{lv}: no data")
            continue
        q = " ".join(c.replace("holder_", "") for c in info["queue_sequence"][:10])
        print(f"  L{lv}: len={info['queue_length']} conf={info['recovery_confidence']} "
              f"valid_ratio={info['valid_ratio']} queue=[{q}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
