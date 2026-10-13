# Stage 2b: Copy representative images to a labeling folder.
# After this, open label_editor.py on that folder for manual labeling.
#
# Usage:
#   python stage2b_prepare_labeling.py \
#     --input path/to/level_to_representative.json \
#     --source path/to/click_image_folder \
#     --output path/to/labeling/images_queue \
#     --sample 50
from __future__ import annotations
import argparse
import json
import shutil
import sys
import random
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True,
                    help="level_to_representative.json")
    ap.add_argument("--source", required=True,
                    help="Folder containing click_*.png images")
    ap.add_argument("--output", required=True,
                    help="Where to copy sampled images for labeling")
    ap.add_argument("--sample", type=int, default=50,
                    help="Number of representatives to sample for labeling")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    src = Path(args.input)
    source_dir = Path(args.source)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        print("ERROR: input not found: " + str(src))
        sys.exit(1)

    data = json.loads(src.read_text(encoding="utf-8"))

    # Collect (level, filename) pairs
    all_pairs = []
    for level, files in data.items():
        if not files:
            continue
        all_pairs.append((level, files[0]))

    # Sort by level number for even distribution across levels
    def level_sort_key(pair):
        try:
            return int(pair[0])
        except Exception:
            return 0

    all_pairs.sort(key=level_sort_key)

    # Even sampling across all levels
    total = len(all_pairs)
    sample_n = min(args.sample, total)
    if sample_n < total:
        # Stride-based sampling to cover early/middle/late levels
        step = total / float(sample_n)
        indices = [int(i * step) for i in range(sample_n)]
        picks = [all_pairs[i] for i in indices]
    else:
        picks = all_pairs

    print("Total levels: " + str(total))
    print("Sampling: " + str(len(picks)))

    copied = 0
    missing = []
    for level, fname in picks:
        src_path = source_dir / fname
        if not src_path.exists():
            missing.append(fname)
            continue
        # Rename with level prefix for easy tracking
        new_name = "L" + str(level).zfill(3) + "__" + fname
        dst = out_dir / new_name
        if not dst.exists():
            shutil.copy2(src_path, dst)
        copied += 1

    print("Copied: " + str(copied))
    print("Missing: " + str(len(missing)))
    if missing:
        print("First missing: " + str(missing[:5]))
    print("Output: " + str(out_dir))
    print()
    print("Next step: label these images with label_editor.py")
    print("  python label_editor.py --dir " + str(out_dir)
          + " --labels " + str(out_dir.parent / "labels_queue"))


if __name__ == "__main__":
    main()
