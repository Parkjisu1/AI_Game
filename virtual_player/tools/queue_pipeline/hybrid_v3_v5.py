"""
Hybrid v3 + v5 전략.

라벨링한 레벨은 v5 (new detector) 결과 사용,
나머지는 v3 (old detector) 결과 사용.

라벨링 된 레벨 목록은 labels_queue_v2 폴더의 XML 파일명에서 자동 추출.

Output: queue_full_per_level_hybrid.json
"""
import argparse
import json
import re
import sys
from pathlib import Path


LEVEL_PREFIX_RE = re.compile(r"^L(\d+)__")


def levels_in_label_folder(folder: Path) -> set:
    levels = set()
    for f in folder.glob("*.xml"):
        m = LEVEL_PREFIX_RE.match(f.name)
        if m:
            levels.add(int(m.group(1)))
    return levels


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--v3", required=True, type=Path)
    p.add_argument("--v5", required=True, type=Path)
    p.add_argument("--labels-v2", required=True, type=Path,
                   help="labels_queue_v2 폴더 (어느 레벨을 새로 라벨했는지 추론)")
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()

    labeled_v2_levels = levels_in_label_folder(args.labels_v2)
    print(f"Newly labeled levels (v5 사용): {len(labeled_v2_levels)} → {sorted(labeled_v2_levels)}")

    v3 = json.loads(args.v3.read_text(encoding="utf-8"))
    v5 = json.loads(args.v5.read_text(encoding="utf-8"))
    v3_levels = v3["levels"]
    v5_levels = v5["levels"]

    all_lv_keys = set(v3_levels.keys()) | set(v5_levels.keys())
    hybrid = {}
    source_count = {"v3": 0, "v5": 0, "v5_only_fallback": 0, "v3_only_fallback": 0}
    for lv_key in sorted(all_lv_keys, key=lambda x: int(x)):
        lv_int = int(lv_key)
        in_v3 = lv_key in v3_levels
        in_v5 = lv_key in v5_levels
        use_v5 = lv_int in labeled_v2_levels

        if use_v5 and in_v5:
            entry = dict(v5_levels[lv_key])
            entry["_source"] = "v5"
            source_count["v5"] += 1
        elif in_v3:
            entry = dict(v3_levels[lv_key])
            entry["_source"] = "v3"
            source_count["v3"] += 1
        elif in_v5:
            entry = dict(v5_levels[lv_key])
            entry["_source"] = "v5_only_fallback"
            source_count["v5_only_fallback"] += 1
        else:
            continue
        hybrid[lv_key] = entry

    summary = {
        "v3_source": str(args.v3),
        "v5_source": str(args.v5),
        "labeled_v2_levels_count": len(labeled_v2_levels),
        "labeled_v2_levels": sorted(labeled_v2_levels),
        "total_levels": len(hybrid),
        "source_distribution": source_count,
        "total_queue_entries": sum(v.get("queue_length", 0) for v in hybrid.values()),
    }

    payload = {"summary": summary, "levels": hybrid}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
