"""
stage3_timeseries_v3.py — Deterministic queue 복원 (v2 대체).

확정 사실 (verify_determinism.py):
    - PixelFlow는 deterministic queue 게임
    - T1 초기 상태 일치도 mean=0.77 (레벨마다 같은 초기 queue로 시작)
    - T3 색 팔레트 일치도 mean=0.71 (같은 색 풀 사용)
    - T2 순서 일치도 mean=0.17 ← v2 알고리즘의 한계

v3 개선:
    [E] Strict FIFO: 소멸 1 + 등장 1 엄격 (v2는 등장 0~1 허용 → noise 많았음)
    [F] N-frame stability: 같은 multiset이 N frame 이상 유지되어야 stable state로 인정
        → 단발성 flicker 제거
    [D] Cross-session consensus: position별 다수결 투표
        → 개별 세션 추출의 오류를 여러 세션 합의로 교정
    [G] 초기 상태 anchor: T1 >= 0.85인 레벨은 초기 visible holders를 gold로 간주
        → 첫 position이 그 집합 안에 있어야 함

Per-position confidence: 투표한 세션 수 대비 동의 비율.

Usage:
    python stage3_timeseries_v3.py \
        --observations .../queue_all_observations.jsonl \
        --output      .../queue_full_per_level_v3.json \
        --min-conf 0.6 \
        --session-gap 50 \
        --stability 3
"""
import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


# ---------- I/O ----------

def group_by_level(jsonl_path: Path):
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
    if not observations:
        return []
    sessions = [[observations[0]]]
    for i in range(1, len(observations)):
        if observations[i]["seq"] - observations[i - 1]["seq"] > gap_threshold:
            sessions.append([observations[i]])
        else:
            sessions[-1].append(observations[i])
    return sessions


def holder_counter(frame, min_conf=0.6):
    return Counter(
        h["name"]
        for h in frame["holders"]
        if h.get("conf", 0) >= min_conf and h.get("class", 99) <= 28
    )


# ---------- [F] N-frame stability ----------

def find_stable_states(session, min_conf, stability_frames):
    """
    연속 N frame 이상 동일 multiset인 구간만 "stable state"로 식별.
    flicker(1~2 frame 변화)는 무시.

    Returns: [(counter, seq_start, seq_end, frame_start_idx, frame_end_idx)]
    """
    if not session:
        return []
    counters = [holder_counter(f, min_conf=min_conf) for f in session]
    segments = []
    cur = counters[0]
    cur_start = 0
    for i in range(1, len(counters)):
        if counters[i] != cur:
            length = i - cur_start
            if length >= stability_frames:
                segments.append((cur, session[cur_start]["seq"], session[i - 1]["seq"], cur_start, i - 1))
            cur = counters[i]
            cur_start = i
    length = len(counters) - cur_start
    if length >= stability_frames:
        segments.append((cur, session[cur_start]["seq"], session[-1]["seq"], cur_start, len(counters) - 1))
    return segments


# ---------- [E] Strict FIFO extraction ----------

def extract_session_events_strict(stable_states):
    """
    stable state 간 transition 추출.
    조건: disappeared 정확히 1개 AND appeared 정확히 1개 (FIFO shift)
    또는 disappeared 1개 AND appeared 0개 (tail 소진)
    2개 이상 동시 변화는 skip (noise or multi-tap)
    """
    events = []
    skipped = 0
    for k in range(1, len(stable_states)):
        prev_cnt = stable_states[k - 1][0]
        curr_cnt = stable_states[k][0]
        appeared = curr_cnt - prev_cnt
        disappeared = prev_cnt - curr_cnt
        na = sum(appeared.values())
        nd = sum(disappeared.values())
        if nd == 1 and na <= 1:
            events.append({
                "consumed": next(iter(disappeared.keys())),
                "replacement": next(iter(appeared.keys())) if appeared else None,
                "seq_at": stable_states[k][1],
                "prev_seq": stable_states[k - 1][2],
                "prev_state": dict(prev_cnt),
                "curr_state": dict(curr_cnt),
            })
        else:
            skipped += 1
    return events, skipped


# ---------- [D] Cross-session consensus ----------

def cross_session_consensus(all_session_events, min_agreement=0.5):
    """
    세션별 소비 시퀀스 → position별 다수결 투표.

    position i에서:
      - 각 세션의 i번째 소비 색상을 수집
      - 가장 많이 나온 색상 선택
      - confidence = winner_count / total_votes
      - confidence < min_agreement 이면 stop (이후 position은 신뢰 불가)

    Returns:
      consensus_queue: [{"position": 0, "color": "c3", "confidence": 0.75, "vote_count": 3, "total_votes": 4}, ...]
      halt_reason: "end_of_sessions" or "low_confidence_at_position_N"
    """
    if not all_session_events:
        return [], "no_sessions"

    sequences = [[e["consumed"] for e in s] for s in all_session_events]
    if not sequences:
        return [], "no_events"

    max_len = max(len(s) for s in sequences)
    consensus = []
    halt = "end_of_sessions"

    for i in range(max_len):
        votes = Counter()
        for s in sequences:
            if i < len(s):
                votes[s[i]] += 1
        if not votes:
            halt = f"no_votes_at_position_{i}"
            break
        winner, winner_count = votes.most_common(1)[0]
        total = sum(votes.values())
        conf = winner_count / total
        if conf < min_agreement:
            halt = f"low_confidence_at_position_{i}"
            break
        consensus.append({
            "position": i,
            "color": winner,
            "confidence": round(conf, 3),
            "vote_count": winner_count,
            "total_votes": total,
            "tied_with": [c for c, n in votes.items() if n == winner_count and c != winner],
        })
    return consensus, halt


# ---------- [G] Initial state anchor ----------

def compute_initial_state_jaccard(sessions, min_conf):
    """세션별 초기 frame multiset들의 평균 Jaccard."""
    init_counters = []
    for s in sessions:
        first = next((f for f in s if f["holder_count"] > 0), None)
        if first is not None:
            init_counters.append(holder_counter(first, min_conf=min_conf))
    if len(init_counters) < 2:
        return None, init_counters
    vals = []
    for i in range(len(init_counters)):
        for j in range(i + 1, len(init_counters)):
            a, b = init_counters[i], init_counters[j]
            keys = set(a.keys()) | set(b.keys())
            inter = sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)
            union = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
            vals.append(inter / union if union > 0 else 0.0)
    return sum(vals) / len(vals) if vals else None, init_counters


def anchor_consensus_to_initial(consensus, init_counters, t1_score):
    """
    T1 >= 0.85이면 초기 상태 교집합을 gold로 간주.
    consensus[0].color가 그 집합에 있어야 함. 없으면 warning.
    """
    warning = None
    if t1_score is None or t1_score < 0.85 or not init_counters or not consensus:
        return consensus, None

    init_union = Counter()
    for c in init_counters:
        for k, v in c.items():
            init_union[k] = max(init_union.get(k, 0), v)

    first_color = consensus[0]["color"]
    if first_color not in init_union:
        warning = (
            f"position 0 color '{first_color}' not in initial state union "
            f"(initial holders: {list(init_union.keys())})"
        )
        consensus[0]["anchor_warning"] = warning
    else:
        consensus[0]["anchor_verified"] = True
    return consensus, warning


# ---------- Level reconstruction ----------

def reconstruct_level(level_obs, *, min_conf, session_gap, stability, min_agreement):
    sessions = detect_sessions(level_obs, gap_threshold=session_gap)
    all_events = []
    session_stats = []
    for s in sessions:
        stable = find_stable_states(s, min_conf=min_conf, stability_frames=stability)
        events, skipped = extract_session_events_strict(stable)
        if len(events) >= 3:
            all_events.append(events)
        session_stats.append({
            "frames": len(s),
            "stable_states": len(stable),
            "events_extracted": len(events),
            "transitions_skipped": skipped,
            "kept": len(events) >= 3,
        })

    t1, init_counters = compute_initial_state_jaccard(sessions, min_conf=min_conf)

    consensus, halt_reason = cross_session_consensus(all_events, min_agreement=min_agreement)
    consensus, anchor_warning = anchor_consensus_to_initial(consensus, init_counters, t1)

    queue_length = len(consensus)
    avg_confidence = (
        sum(c["confidence"] for c in consensus) / queue_length if queue_length > 0 else 0.0
    )

    if queue_length >= 20 and avg_confidence >= 0.85:
        recovery = "A"
    elif queue_length >= 10 and avg_confidence >= 0.7:
        recovery = "B"
    elif queue_length >= 3:
        recovery = "C"
    else:
        recovery = "F"

    return {
        "total_observations": len(level_obs),
        "session_count": len(sessions),
        "valid_session_count": len(all_events),
        "session_event_lengths": [len(ev) for ev in all_events],
        "recovery_confidence": recovery,
        "queue_length": queue_length,
        "avg_position_confidence": round(avg_confidence, 3),
        "halt_reason": halt_reason,
        "t1_initial_state_jaccard": round(t1, 3) if t1 is not None else None,
        "anchor_warning": anchor_warning,
        "queue": consensus,
        "per_session_stats": session_stats,
    }


# ---------- Main ----------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--observations", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--min-conf", type=float, default=0.6)
    p.add_argument("--session-gap", type=int, default=50)
    p.add_argument("--stability", type=int, default=3,
                   help="이 수 이상 연속 동일 state만 인정 (flicker 제거)")
    p.add_argument("--min-agreement", type=float, default=0.5,
                   help="consensus 투표 합의 하한. 이 이하로 떨어지면 position에서 중단")
    args = p.parse_args()

    if not args.observations.exists():
        print(f"ERROR: observations not found: {args.observations}", file=sys.stderr)
        return 2

    print(f"Loading: {args.observations}")
    by_level = group_by_level(args.observations)
    print(f"Levels: {len(by_level)}")
    print(f"Params: min_conf={args.min_conf}, session_gap={args.session_gap}, "
          f"stability={args.stability}, min_agreement={args.min_agreement}")

    result = {}
    counts = {"A": 0, "B": 0, "C": 0, "F": 0}
    total_q_len = 0
    total_confident = 0
    total_anchor_warn = 0
    for level, obs in sorted(by_level.items()):
        info = reconstruct_level(
            obs,
            min_conf=args.min_conf,
            session_gap=args.session_gap,
            stability=args.stability,
            min_agreement=args.min_agreement,
        )
        result[str(level)] = info
        counts[info["recovery_confidence"]] += 1
        total_q_len += info["queue_length"]
        total_confident += sum(1 for c in info["queue"] if c["confidence"] >= 0.8)
        if info.get("anchor_warning"):
            total_anchor_warn += 1

    levels_with_multi = sum(1 for v in result.values() if v["valid_session_count"] >= 2)
    summary = {
        "source": str(args.observations),
        "total_levels": len(result),
        "recovery_distribution": counts,
        "total_queue_entries": total_q_len,
        "total_high_confidence_positions": total_confident,
        "levels_with_multi_sessions": levels_with_multi,
        "anchor_warnings_count": total_anchor_warn,
        "parameters": {
            "min_conf": args.min_conf,
            "session_gap": args.session_gap,
            "stability": args.stability,
            "min_agreement": args.min_agreement,
        },
    }

    payload = {"summary": summary, "levels": result}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nOutput: {args.output}")

    print("\n--- Top 15 queues ---")
    top = sorted(result.items(), key=lambda x: -x[1]["queue_length"])[:15]
    for lv, info in top:
        q_preview = " ".join(f"{c['color'].replace('holder_','')}({c['confidence']:.2f})" for c in info["queue"][:6])
        tail = " …" if info["queue_length"] > 6 else ""
        print(f"  L{lv}: len={info['queue_length']} conf={info['recovery_confidence']} "
              f"avg_conf={info['avg_position_confidence']} "
              f"sessions={info['valid_session_count']}/{info['session_count']} "
              f"T1={info['t1_initial_state_jaccard']}")
        print(f"      [{q_preview}{tail}] halt={info['halt_reason']}")

    print("\n--- 초기 레벨 L1~L10 (튜토리얼 검증) ---")
    for lv in range(1, 11):
        info = result.get(str(lv))
        if not info:
            continue
        q_preview = " ".join(c["color"].replace("holder_", "") for c in info["queue"][:10])
        print(f"  L{lv}: len={info['queue_length']} conf={info['recovery_confidence']} "
              f"avg_conf={info['avg_position_confidence']} queue=[{q_preview}]")

    return 0


if __name__ == "__main__":
    sys.exit(main())
