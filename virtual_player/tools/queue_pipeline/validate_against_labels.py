"""
v3 결과를 42 라벨 ground truth로 검증.

각 라벨 XML:
    - 해당 click 이미지의 실제 holder bbox + class 명세
    - filename → level 매핑 (filename prefix "L001__...")

검증 로직:
    - 라벨에서 holder color set 추출 (ground truth initial state)
    - v3 queue의 position 0~N을 비교 → 초기 queue에 이 색이 들어있는지 확인
    - v3 queue 전체 color counter vs 라벨 visible set 대조

Output:
    labels_validation_report.json
        - per-label accuracy
        - summary: avg match rate, worst levels
        - priority list for additional labeling
"""
import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path


def parse_xml(xml_path: Path):
    """Pascal VOC XML → list of objects."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return []
    objs = []
    for obj in tree.getroot().findall("object"):
        name = obj.findtext("name", "").strip().lower()
        objs.append(name)
    return objs


def parse_level_from_filename(filename: str):
    """L001__click_...png → 1"""
    m = re.match(r"L(\d+)__", filename)
    return int(m.group(1)) if m else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--v3-result", required=True, type=Path,
                   default="E:/AI/virtual_player/tools/queue_pipeline/queue_full_per_level_v3_practical.json")
    p.add_argument("--labels-dir", required=True, type=Path,
                   default="E:/AI/virtual_player/yolo/pixelflow/labeling/labels_queue")
    p.add_argument("--images-dir", required=True, type=Path,
                   default="E:/AI/virtual_player/yolo/pixelflow/labeling/images_queue")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    v3 = json.loads(args.v3_result.read_text(encoding="utf-8"))
    levels_data = v3["levels"]

    # Build labeled level -> holder set map
    label_files = sorted(args.labels_dir.glob("*.xml"))
    labeled_levels = {}  # level_id -> {"filename": str, "holders": Counter, "gimmicks": list}
    for lbl in label_files:
        stem = lbl.stem
        level_id = parse_level_from_filename(stem)
        if level_id is None:
            continue
        objs = parse_xml(lbl)
        holders = Counter(o for o in objs if o.startswith("holder_"))
        gimmicks = [o for o in objs if "gimmik" in o or "gimmick" in o]
        labeled_levels[level_id] = {
            "filename": stem,
            "holders": holders,
            "gimmicks": gimmicks,
        }

    print(f"Labeled levels: {len(labeled_levels)}")
    print(f"V3 levels: {len(levels_data)}")

    reports = []
    stats = {
        "exact_match_initial": 0,
        "partial_match_initial": 0,
        "no_match_initial": 0,
        "missing_from_v3": 0,
        "v3_failed": 0,
    }

    for level_id, lbl_info in sorted(labeled_levels.items()):
        v3_info = levels_data.get(str(level_id))
        report = {
            "level": level_id,
            "label_file": lbl_info["filename"],
            "label_holders": dict(lbl_info["holders"]),
            "label_holder_set": sorted(lbl_info["holders"].keys()),
            "label_gimmicks": lbl_info["gimmicks"],
        }
        if v3_info is None:
            report["status"] = "MISSING_FROM_V3"
            stats["missing_from_v3"] += 1
            reports.append(report)
            continue
        if v3_info["queue_length"] == 0:
            report["status"] = "V3_FAILED"
            report["v3_recovery"] = v3_info["recovery_confidence"]
            stats["v3_failed"] += 1
            reports.append(report)
            continue

        label_set = set(lbl_info["holders"].keys())
        # v3 schema: queue = [{color, position, ...}]
        # v4 schema: queue_sequence = [color, color, ...]
        if "queue" in v3_info:
            queue_entries = v3_info["queue"]
            queue_colors = [c["color"] for c in queue_entries]
        elif "queue_sequence" in v3_info:
            queue_colors = v3_info["queue_sequence"]
        else:
            queue_colors = []
        v3_colors = set(queue_colors)

        overlap = label_set & v3_colors
        label_only = label_set - v3_colors
        v3_only = v3_colors - label_set

        if label_set == v3_colors:
            status = "EXACT_MATCH"
            stats["exact_match_initial"] += 1
        elif overlap:
            status = "PARTIAL_MATCH"
            stats["partial_match_initial"] += 1
        else:
            status = "NO_MATCH"
            stats["no_match_initial"] += 1

        # Also check: first N queue entries should come from label_set
        first_n = min(5, len(queue_colors))
        first_colors = queue_colors[:first_n]
        first_in_label = sum(1 for c in first_colors if c in label_set)

        report.update({
            "status": status,
            "v3_queue_length": v3_info["queue_length"],
            "v3_recovery": v3_info["recovery_confidence"],
            "v3_avg_confidence": v3_info.get("avg_position_confidence", v3_info.get("valid_ratio")),
            "v3_valid_sessions": v3_info.get("valid_session_count", v3_info.get("valid_pairs")),
            "v3_color_set": sorted(v3_colors),
            "overlap": sorted(overlap),
            "label_only": sorted(label_only),
            "v3_only": sorted(v3_only),
            "jaccard": round(len(overlap) / len(label_set | v3_colors), 3)
                if (label_set | v3_colors) else 0.0,
            "first5_queue": first_colors,
            "first5_in_label_ratio": round(first_in_label / first_n, 3) if first_n > 0 else 0.0,
        })
        reports.append(report)

    # Priority list for additional labeling = levels with poor match
    priority = sorted(
        [r for r in reports if r.get("status") in ("NO_MATCH", "PARTIAL_MATCH", "V3_FAILED", "MISSING_FROM_V3")],
        key=lambda r: (r.get("jaccard", 0), -(r.get("v3_queue_length", 0)))
    )

    # Summary
    total_labeled = len(labeled_levels)
    avg_jaccard = (
        sum(r.get("jaccard", 0) for r in reports if "jaccard" in r) /
        max(1, sum(1 for r in reports if "jaccard" in r))
    )
    avg_first5 = (
        sum(r.get("first5_in_label_ratio", 0) for r in reports if "first5_in_label_ratio" in r) /
        max(1, sum(1 for r in reports if "first5_in_label_ratio" in r))
    )

    summary = {
        "total_labeled_levels": total_labeled,
        "v3_source": str(args.v3_result),
        "stats": stats,
        "avg_jaccard_color_set": round(avg_jaccard, 3),
        "avg_first5_in_label_ratio": round(avg_first5, 3),
        "priority_labeling_candidates": [r["level"] for r in priority[:30]],
    }

    payload = {"summary": summary, "reports": reports}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== LABEL VALIDATION SUMMARY ===")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    print("\n--- Per-level detail ---")
    for r in reports:
        if r["status"] in ("MISSING_FROM_V3", "V3_FAILED"):
            print(f"  L{r['level']:>3}: {r['status']}  (label: {r['label_holder_set']})")
            continue
        print(f"  L{r['level']:>3}: {r['status']:14s} "
              f"Jaccard={r['jaccard']}  "
              f"first5_match={r['first5_in_label_ratio']}  "
              f"v3_len={r['v3_queue_length']}  "
              f"v3_conf={r['v3_recovery']}")
        if r["status"] in ("NO_MATCH", "PARTIAL_MATCH"):
            print(f"       label: {r['label_holder_set']}")
            print(f"       v3:    {r['v3_color_set']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
