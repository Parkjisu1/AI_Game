"""
stage3_timeseries_v2.py — FIFO 소비 이벤트 기반 queue 복원 (v1 대체판).

v1 문제점:
    - Slot 클러스터링 tol=40으로 slot 70~89개 과잉 생성
    - Head slot 색 변화 횟수 = queue 길이로 가정했으나 detection noise로 인플레이션
    - L228 queue=1438 같은 비현실 수치 발생

v2 알고리즘:
    1. 레벨별 관찰 → seq 순 정렬
    2. 세션 분리: seq 간격 > GAP_THRESHOLD 이면 새 플레이 세션
    3. 세션 내 연속 frame 간 holder multiset 비교:
       - Counter(curr) - Counter(prev) = 새로 등장한 색
       - Counter(prev) - Counter(curr) = 소멸한 색
       - 정확히 "1 소멸 + 0~1 등장"일 때만 FIFO 소비 이벤트로 확정
       - 2개 이상 동시 변화는 detection noise로 간주, skip
    4. confirmed 소비 시퀀스 = 해당 세션의 queue 관찰
    5. 세션 간 합의: 가장 긴 세션을 채택, 다수 세션의 공통 prefix 검증

Usage:
    python stage3_timeseries_v2.py \
        --observations E:/AI/.../queue_all_observations.jsonl \
        --output E:/AI/.../queue_full_per_level_v2.json \
        --min-conf 0.5 \
        --session-gap 50
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


def group_by_level(jsonl_path: Path) -> dict:
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


def detect_sessions(observations, gap_threshold=50):
    """seq 간격 > threshold 이면 새 세션."""
    if not observations:
        return []
    sessions = []
    current = [observations[0]]
    for i in range(1, len(observations)):
        gap = observations[i]["seq"] - observations[i - 1]["seq"]
        if gap > gap_threshold:
            sessions.append(current)
            current = [observations[i]]
        else:
            current.append(observations[i])
    sessions.append(current)
    return sessions


def holder_counter(frame, min_conf=0.5):
    """신뢰할 수 있는 holder만 Counter로. class 29~39는 제외 (기믹/current_balloon)."""
    return Counter(
        h["name"]
        for h in frame["holders"]
        if h.get("conf", 0) >= min_conf and h.get("class", 99) <= 28
    )


def extract_session_events(session, min_conf=0.5):
    """
    세션 내 FIFO 소비 이벤트 추출.

    각 연속 frame (prev, curr) 비교:
      appeared = Counter(curr) - Counter(prev)
      disappeared = Counter(prev) - Counter(curr)

    유효 소비 이벤트 조건:
      sum(disappeared) == 1 AND sum(appeared) <= 1
    → 정확히 한 색이 소비되고, 최대 한 색이 새로 들어옴 (FIFO shift 또는 tail-empty)

    2개 이상 변화는 skip (noise).
    """
    events = []
    prev = None
    prev_seq = None
    skipped_noise = 0
    same_state = 0
    for frame in session:
        curr = holder_counter(frame, min_conf=min_conf)
        if prev is not None:
            appeared = curr - prev
            disappeared = prev - curr
            na = sum(appeared.values())
            nd = sum(disappeared.values())
            if nd == 0 and na == 0:
                same_state += 1
            elif nd == 1 and na <= 1:
                consumed = next(iter(disappeared.keys()))
                new_from_tail = next(iter(appeared.keys())) if appeared else None
                events.append({
                    "consumed": consumed,
                    "tail_new": new_from_tail,
                    "seq_at": frame["seq"],
                    "prev_seq": prev_seq,
                    "prev_visible": dict(prev),
                    "curr_visible": dict(curr),
                })
            else:
                skipped_noise += 1
        prev = curr
        prev_seq = frame["seq"]
    return events, {"same_state": same_state, "skipped_noise": skipped_noise, "total_frames": len(session)}


def consolidate_sessions(session_results, min_session_len=3):
    """
    세션별 소비 이벤트 → 레벨 전체 queue 추정.

    전략:
      - 가장 긴 확정 이벤트 시퀀스(= longest_session)를 우선 채택
      - 다른 세션이 longest와 같은 prefix를 보이면 cross-session 합의 점수 +1
      - 최종 queue = longest_session의 consumed 색 순서
      - colors_set = 모든 세션에서 관찰된 색의 union
    """
    valid_sessions = [(i, ev) for i, (ev, _) in enumerate(session_results) if len(ev) >= min_session_len]
    if not valid_sessions:
        return None

    valid_sessions.sort(key=lambda x: -len(x[1]))
    longest_idx, longest_events = valid_sessions[0]
    longest_sequence = [e["consumed"] for e in longest_events]

    agreements = 0
    partial_agreements = 0
    for idx, ev in valid_sessions[1:]:
        other_seq = [e["consumed"] for e in ev]
        n = min(len(other_seq), len(longest_sequence))
        matched = sum(1 for i in range(n) if other_seq[i] == longest_sequence[i])
        if n > 0 and matched / n >= 0.9:
            agreements += 1
        elif n > 0 and matched / n >= 0.5:
            partial_agreements += 1

    all_colors = Counter()
    for _, ev in valid_sessions:
        for e in ev:
            all_colors[e["consumed"]] += 1

    return {
        "longest_session_index": longest_idx,
        "queue_sequence": longest_sequence,
        "sequence_len": len(longest_sequence),
        "sessions_full_agreement": agreements,
        "sessions_partial_agreement": partial_agreements,
        "sessions_total_valid": len(valid_sessions),
        "colors_observed": dict(all_colors.most_common()),
    }


def reconstruct_level(level_obs, min_conf=0.5, session_gap=50, min_session_len=3):
    sessions = detect_sessions(level_obs, gap_threshold=session_gap)
    session_results = [extract_session_events(s, min_conf=min_conf) for s in sessions]

    consolidated = consolidate_sessions(session_results, min_session_len=min_session_len)

    total_events = sum(len(ev) for ev, _ in session_results)
    total_noise = sum(stats["skipped_noise"] for _, stats in session_results)
    total_same = sum(stats["same_state"] for _, stats in session_results)
    total_frames = sum(stats["total_frames"] for _, stats in session_results)

    if consolidated is None:
        recovery = "F"
        queue = []
    else:
        ln = consolidated["sequence_len"]
        agree = consolidated["sessions_full_agreement"]
        if ln >= 20 and agree >= 1:
            recovery = "A"
        elif ln >= 10:
            recovery = "B"
        elif ln >= 1:
            recovery = "C"
        else:
            recovery = "F"
        queue = consolidated["queue_sequence"]

    return {
        "total_observations": len(level_obs),
        "total_frames_all_sessions": total_frames,
        "session_count": len(sessions),
        "valid_session_count": consolidated["sessions_total_valid"] if consolidated else 0,
        "recovery_confidence": recovery,
        "queue_sequence": queue,
        "queue_length": len(queue),
        "sessions_full_agreement": consolidated["sessions_full_agreement"] if consolidated else 0,
        "sessions_partial_agreement": consolidated["sessions_partial_agreement"] if consolidated else 0,
        "colors_observed": consolidated["colors_observed"] if consolidated else {},
        "diagnostics": {
            "total_consumption_events": total_events,
            "skipped_noise_transitions": total_noise,
            "same_state_transitions": total_same,
        },
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--observations", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--min-conf", type=float, default=0.5,
                   help="이 이하 confidence holder는 제외 (detection noise)")
    p.add_argument("--session-gap", type=int, default=50,
                   help="seq 간격 이 값 초과 시 새 세션")
    p.add_argument("--min-session-len", type=int, default=3,
                   help="이 수 미만 이벤트 세션은 무시")
    args = p.parse_args()

    if not args.observations.exists():
        print(f"ERROR: observations not found: {args.observations}", file=sys.stderr)
        return 2

    print(f"Loading: {args.observations}")
    by_level = group_by_level(args.observations)
    print(f"Levels: {len(by_level)}")
    print(f"Parameters: min_conf={args.min_conf}, session_gap={args.session_gap}, min_session_len={args.min_session_len}")

    result = {}
    counts = {"A": 0, "B": 0, "C": 0, "F": 0}
    total_queue_len = 0
    total_noise = 0
    total_events = 0
    for level, obs in sorted(by_level.items()):
        info = reconstruct_level(
            obs,
            min_conf=args.min_conf,
            session_gap=args.session_gap,
            min_session_len=args.min_session_len,
        )
        result[str(level)] = info
        counts[info["recovery_confidence"]] += 1
        total_queue_len += info["queue_length"]
        total_noise += info["diagnostics"]["skipped_noise_transitions"]
        total_events += info["diagnostics"]["total_consumption_events"]

    summary = {
        "source": str(args.observations),
        "total_levels": len(result),
        "recovery_distribution": counts,
        "total_queue_entries": total_queue_len,
        "total_consumption_events_all_levels": total_events,
        "total_noise_skipped": total_noise,
        "parameters": {
            "min_conf": args.min_conf,
            "session_gap": args.session_gap,
            "min_session_len": args.min_session_len,
        },
    }

    payload = {"summary": summary, "levels": result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nOutput: {args.output}")

    top = sorted(result.items(), key=lambda x: -x[1]["queue_length"])[:15]
    print("\nTop 15 recovered queues (longest):")
    for lv, info in top:
        cu = ", ".join(f"{k}:{v}" for k, v in list(info["colors_observed"].items())[:5])
        seq_preview = " → ".join(info["queue_sequence"][:8])
        tail = " …" if len(info["queue_sequence"]) > 8 else ""
        print(f"  L{lv}: len={info['queue_length']} conf={info['recovery_confidence']} "
              f"sessions={info['valid_session_count']}/{info['session_count']} "
              f"agree={info['sessions_full_agreement']}")
        print(f"      colors=[{cu}]")
        print(f"      queue: [{seq_preview}{tail}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
