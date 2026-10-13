# Stage 2a: Select representative image per level.
# For each level in level_to_images.json, pick the earliest _before.png.
# Output: level_to_representative.json (level -> single filename)
#
# Usage:
#   python stage2a_select_representatives.py \
#     --input path/to/level_to_images.json \
#     --output path/to/level_to_representative.json
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def pick_representative(filenames):
    # Prefer _before.png. Sort by filename (timestamps are embedded).
    befores = sorted([f for f in filenames if f.endswith("_before.png")])
    if befores:
        return befores[0]
    # Fallback: first _after.png or any png
    all_sorted = sorted(filenames)
    return all_sorted[0] if all_sorted else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True,
                    help="level_to_images.json from Stage 1")
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-per-level", type=int, default=1,
                    help="How many candidates per level (default 1)")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        print("ERROR: input not found: " + str(src))
        sys.exit(1)

    data = json.loads(src.read_text(encoding="utf-8"))
    result = {}
    stats_levels = 0
    stats_total_candidates = 0
    for level, files in data.items():
        if not files:
            continue
        stats_levels += 1
        # Sort by timestamp (embedded in filename)
        all_sorted = sorted(files)
        befores = [f for f in all_sorted if f.endswith("_before.png")]
        picks = befores[: args.max_per_level] if befores else all_sorted[: args.max_per_level]
        result[level] = picks
        stats_total_candidates += len(picks)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Levels: " + str(stats_levels))
    print("Candidates: " + str(stats_total_candidates))
    print("Output: " + str(out))


if __name__ == "__main__":
    main()
