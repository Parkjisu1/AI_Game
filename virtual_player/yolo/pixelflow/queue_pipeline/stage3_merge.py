# Stage 3: Merge cells + gimmicks (from batch_all_levels_run) with queue data.
# Produces per-level JSON with all info combined.
#
# Usage:
#   python stage3_merge.py \
#     --cells-dir path/to/batch_all_levels_run/levels \
#     --queue queue_by_level.json \
#     --output final_levels/
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cells-dir", required=True,
                    help="Folder with level_XXX.json from batch_all_levels_run")
    ap.add_argument("--queue", required=True,
                    help="queue_by_level.json from Stage 2d")
    ap.add_argument("--output", required=True,
                    help="Output folder for final per-level JSONs")
    args = ap.parse_args()

    cells_dir = Path(args.cells_dir)
    queue_path = Path(args.queue)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not cells_dir.exists():
        print("ERROR: cells dir not found: " + str(cells_dir))
        sys.exit(1)
    if not queue_path.exists():
        print("ERROR: queue json not found: " + str(queue_path))
        sys.exit(1)

    queue_data = json.loads(queue_path.read_text(encoding="utf-8"))

    merged_count = 0
    no_queue = 0
    missing_cells = []

    # Iterate queue levels, find matching cells file
    for level_str, q in queue_data.items():
        try:
            level_num = int(level_str)
        except ValueError:
            continue

        cells_file = cells_dir / ("level_" + str(level_num).zfill(3) + ".json")
        if not cells_file.exists():
            missing_cells.append(level_num)
            continue

        cells_data = json.loads(cells_file.read_text(encoding="utf-8"))

        # Build merged output
        merged = dict(cells_data)
        merged["queue"] = {
            "holder_count": q.get("holder_count", 0),
            "source_image": q.get("source_image", ""),
            "holders": q.get("holders", []),
        }
        merged["stage3_merged"] = True

        out_file = out_dir / ("level_" + str(level_num).zfill(3) + ".json")
        out_file.write_text(
            json.dumps(merged, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        merged_count += 1

    # Also output cells-only levels (no queue data) so final set is complete
    for cf in cells_dir.glob("level_*.json"):
        level_num = int(cf.stem.split("_")[1])
        if str(level_num) in queue_data:
            continue
        cells_data = json.loads(cf.read_text(encoding="utf-8"))
        cells_data["queue"] = {"holder_count": 0, "holders": []}
        cells_data["stage3_merged"] = False
        out_file = out_dir / cf.name
        out_file.write_text(
            json.dumps(cells_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        no_queue += 1

    # Summary
    summary = {
        "merged_with_queue": merged_count,
        "cells_only": no_queue,
        "missing_cells_for_queue": len(missing_cells),
        "missing_levels": sorted(missing_cells)[:20],
        "total_output_files": merged_count + no_queue,
    }
    (out_dir.parent / "stage3_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("Merged (cells + queue): " + str(merged_count))
    print("Cells only (no queue): " + str(no_queue))
    print("Missing cells for queue: " + str(len(missing_cells)))
    print("Output: " + str(out_dir))


if __name__ == "__main__":
    main()
