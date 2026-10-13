"""
Deterministic vs Random queue 판별 스크립트.

"PixelFlow는 deterministic인데 v2 알고리즘이 노이즈에 약한 것인지" 또는
"PixelFlow가 진짜로 random인지" 판별.

3가지 독립 테스트:

  Test 1: 초기 상태 일치도 (Initial State Similarity)
    - 각 세션의 첫 frame에서 관찰된 holder multiset
    - 세션 간 Jaccard similarity (교집합 / 합집합)
    - Deterministic: 높음 (>0.8) — 같은 레벨은 같은 초기 queue로 시작
    - Random: 낮음 — 매 세션 다른 시작
    - 노이즈 영향 최소 (FIFO reasoning 전혀 안 씀)

  Test 2: 초기 prefix 일치도 (Initial Prefix Similarity)
    - 각 세션의 confirmed consumption 시퀀스 (v2 추출 결과) 비교
    - 처음 5, 10 consumption이 얼마나 일치하는지 (longest common prefix 비율)
    - Deterministic + low noise: 높음
    - Deterministic + high noise: 중간 (노이즈가 끼어들지만 초반엔 적음)
    - Random: 낮음

  Test 3: 색상 팔레트 일치도 (Color Palette Overlap)
    - 각 세션에서 소비된 색상의 multiset
    - 세션 간 Cosine similarity
    - Deterministic + same queue: 매우 높음 (1.0에 근접)
    - 같은 레벨 같은 색 수급이지만 순서만 random: 높음 (0.9+)
    - 레벨마다 정말 완전 random: 중간~낮음

해석 매트릭스:
  T1 높음 + T2 높음 + T3 높음 → Deterministic (내 알고리즘도 잘 맞음)
  T1 높음 + T2 낮음 + T3 높음 → Deterministic이지만 내 알고리즘 노이즈에 약함
  T1 낮음 + T3 낮음           → Random queue
  T1 중간 + T3 높음 + T2 낮음 → 색 풀은 결정적, 순서는 random

Usage:
    python verify_determinism.py \
        --observations E:/AI/.../queue_all_observations.jsonl \
        --v2-result   E:/AI/.../queue_full_per_level_v2.json \
        --output      E:/AI/.../determinism_report.json \
        --min-sessions 2 \
        --session-gap 50 \
        --min-conf 0.5
"""
import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


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


def holder_counter(frame, min_conf=0.5):
    return Counter(
        h["name"]
        for h in frame["holders"]
        if h.get("conf", 0) >= min_conf and h.get("class", 99) <= 28
    )


def extract_session_events(session, min_conf=0.5):
    events = []
    prev = None
    for frame in session:
        curr = holder_counter(frame, min_conf=min_conf)
        if prev is not None:
            appeared = curr - prev
            disappeared = prev - curr
            if sum(disappeared.values()) == 1 and sum(appeared.values()) <= 1:
                events.append(next(iter(disappeared.keys())))
        prev = curr
    return events


def jaccard(a: Counter, b: Counter):
    if not a and not b:
        return 1.0
    keys = set(a.keys()) | set(b.keys())
    inter = sum(min(a.get(k, 0), b.get(k, 0)) for k in keys)
    union = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return inter / union if union > 0 else 0.0


def cosine(a: Counter, b: Counter):
    if not a or not b:
        return 0.0
    keys = set(a.keys()) | set(b.keys())
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


def longest_common_prefix_ratio(a, b):
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i / n
    return 1.0


def prefix_agreement(sessions_events, prefix_len):
    if len(sessions_events) < 2:
        return None
    prefixes = [s[:prefix_len] for s in sessions_events if len(s) >= prefix_len]
    if len(prefixes) < 2:
        return None
    ratios = []
    for i in range(len(prefixes)):
        for j in range(i + 1, len(prefixes)):
            ratios.append(longest_common_prefix_ratio(prefixes[i], prefixes[j]))
    return sum(ratios) / len(ratios) if ratios else None


def pairwise_avg(fn, items):
    if len(items) < 2:
        return None
    vals = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            vals.append(fn(items[i], items[j]))
    return sum(vals) / len(vals) if vals else None


def analyze_level(level_obs, min_conf=0.5, session_gap=50):
    sessions = detect_sessions(level_obs, gap_threshold=session_gap)
    sess_events = [extract_session_events(s, min_conf=min_conf) for s in sessions]
    valid = [(s, ev) for s, ev in zip(sessions, sess_events) if len(ev) >= 3]
    if len(valid) < 2:
        return None

    initial_counters = []
    for s, _ in valid:
        first_with_holders = next((f for f in s if f["holder_count"] > 0), None)
        if first_with_holders:
            initial_counters.append(holder_counter(first_with_holders, min_conf=min_conf))

    t1_jaccard = pairwise_avg(jaccard, initial_counters) if len(initial_counters) >= 2 else None

    events_list = [ev for _, ev in valid]
    t2_p5 = prefix_agreement(events_list, 5)
    t2_p10 = prefix_agreement(events_list, 10)
    t2_p20 = prefix_agreement(events_list, 20)

    session_color_multisets = [Counter(ev) for ev in events_list]
    t3_cosine = pairwise_avg(cosine, session_color_multisets) if len(session_color_multisets) >= 2 else None

    return {
        "valid_sessions": len(valid),
        "session_event_counts": [len(ev) for ev in events_list],
        "t1_initial_state_jaccard": round(t1_jaccard, 4) if t1_jaccard is not None else None,
        "t2_prefix_5_match": round(t2_p5, 4) if t2_p5 is not None else None,
        "t2_prefix_10_match": round(t2_p10, 4) if t2_p10 is not None else None,
        "t2_prefix_20_match": round(t2_p20, 4) if t2_p20 is not None else None,
        "t3_color_palette_cosine": round(t3_cosine, 4) if t3_cosine is not None else None,
        "sample_events": [ev[:10] for ev in events_list[:3]],
    }


def classify(report):
    t1 = report.get("t1_initial_state_jaccard")
    t2_5 = report.get("t2_prefix_5_match")
    t2_10 = report.get("t2_prefix_10_match")
    t3 = report.get("t3_color_palette_cosine")
    scores = [x for x in [t1, t2_5, t3] if x is not None]
    if not scores:
        return "unknown"
    if t1 is not None and t1 >= 0.85 and t2_5 is not None and t2_5 >= 0.7 and t3 is not None and t3 >= 0.85:
        return "deterministic_clean"
    if t1 is not None and t1 >= 0.85 and (t2_5 is None or t2_5 < 0.5) and t3 is not None and t3 >= 0.7:
        return "deterministic_but_noisy"
    if (t1 is None or t1 < 0.4) and (t3 is None or t3 < 0.5):
        return "random"
    if t3 is not None and t3 >= 0.7 and (t2_5 is None or t2_5 < 0.4):
        return "same_color_pool_random_order"
    return "mixed"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--observations", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--min-sessions", type=int, default=2)
    p.add_argument("--session-gap", type=int, default=50)
    p.add_argument("--min-conf", type=float, default=0.5)
    args = p.parse_args()

    print(f"Loading: {args.observations}")
    by_level = group_by_level(args.observations)

    per_level = {}
    verdicts = Counter()
    score_sums = defaultdict(list)

    for lv, obs in sorted(by_level.items()):
        info = analyze_level(obs, min_conf=args.min_conf, session_gap=args.session_gap)
        if info is None:
            continue
        if info["valid_sessions"] < args.min_sessions:
            continue
        verdict = classify(info)
        info["verdict"] = verdict
        per_level[str(lv)] = info
        verdicts[verdict] += 1
        for k in ("t1_initial_state_jaccard", "t2_prefix_5_match", "t2_prefix_10_match", "t3_color_palette_cosine"):
            if info.get(k) is not None:
                score_sums[k].append(info[k])

    def agg(name):
        vals = score_sums[name]
        if not vals:
            return None
        return {
            "count": len(vals),
            "mean": round(sum(vals) / len(vals), 4),
            "median": round(sorted(vals)[len(vals) // 2], 4),
            "min": round(min(vals), 4),
            "max": round(max(vals), 4),
        }

    summary = {
        "levels_analyzed": len(per_level),
        "verdict_distribution": dict(verdicts),
        "score_aggregates": {
            "t1_initial_state_jaccard": agg("t1_initial_state_jaccard"),
            "t2_prefix_5_match": agg("t2_prefix_5_match"),
            "t2_prefix_10_match": agg("t2_prefix_10_match"),
            "t3_color_palette_cosine": agg("t3_color_palette_cosine"),
        },
    }

    # Overall verdict based on aggregate scores
    t1_mean = (summary["score_aggregates"]["t1_initial_state_jaccard"] or {}).get("mean")
    t3_mean = (summary["score_aggregates"]["t3_color_palette_cosine"] or {}).get("mean")
    t2_mean = (summary["score_aggregates"]["t2_prefix_5_match"] or {}).get("mean")

    if t1_mean is not None and t1_mean >= 0.85 and t2_mean is not None and t2_mean >= 0.7:
        overall = "DETERMINISTIC_CLEAN: 알고리즘도 믿을만함"
    elif t1_mean is not None and t1_mean >= 0.7 and t3_mean is not None and t3_mean >= 0.7 and (t2_mean is None or t2_mean < 0.5):
        overall = "DETERMINISTIC_NOISY: queue는 고정이지만 알고리즘이 노이즈에 약함 (알고리즘 개선 필요)"
    elif t1_mean is not None and t1_mean < 0.5 and t3_mean is not None and t3_mean < 0.6:
        overall = "RANDOM: 게임이 매 플레이마다 queue 랜덤 생성"
    elif t3_mean is not None and t3_mean >= 0.7 and (t2_mean is None or t2_mean < 0.4):
        overall = "PARTIAL_RANDOM: 같은 색 풀이지만 순서는 random"
    else:
        overall = "MIXED / 판단 보류"

    summary["overall_verdict"] = overall

    args.output.parent.mkdir(parents=True, exist_ok=True)
    payload = {"summary": summary, "levels": per_level}
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== DETERMINISM VERIFICATION ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    print("\n--- Representative levels (top 10 by session count) ---")
    top = sorted(per_level.items(), key=lambda x: -x[1]["valid_sessions"])[:10]
    for lv, info in top:
        print(f"\n  L{lv}: verdict={info['verdict']}  sessions={info['valid_sessions']}  events={info['session_event_counts']}")
        print(f"    T1 init-state Jaccard: {info['t1_initial_state_jaccard']}")
        print(f"    T2 prefix-5 match:     {info['t2_prefix_5_match']}")
        print(f"    T2 prefix-10 match:    {info['t2_prefix_10_match']}")
        print(f"    T3 palette cosine:     {info['t3_color_palette_cosine']}")
        if info["sample_events"]:
            for i, ev in enumerate(info["sample_events"][:3]):
                print(f"    session{i+1}[:10]: {ev}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
