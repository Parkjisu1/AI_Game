"""
Build Reference DB
===================
CLI tool to pre-build reference screenshot database from recordings.

Usage:
    python -m virtual_player.tools.build_reference_db --game ash_n_veil
    python -m virtual_player.tools.build_reference_db --game ash_n_veil --output data/games/ash_n_veil/reference_db
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from virtual_player.brain.reference_db import ReferenceDB


def main():
    parser = argparse.ArgumentParser(
        description="Build reference screenshot DB from recordings"
    )
    parser.add_argument(
        "--game", required=True,
        help="Game ID (e.g., ash_n_veil)"
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory for reference DB (default: data/games/{game}/reference_db)"
    )
    parser.add_argument(
        "--recordings-dir", default=None,
        help="Recordings directory (default: data/recordings/{game})"
    )

    args = parser.parse_args()

    # Resolve paths
    data_dir = Path(__file__).parent.parent / "data"

    recordings_dir = (
        Path(args.recordings_dir) if args.recordings_dir
        else data_dir / "recordings" / args.game
    )
    annotations_path = recordings_dir / "annotations.json"
    frames_dir = recordings_dir / "frames"

    output_dir = (
        Path(args.output) if args.output
        else data_dir / "games" / args.game / "reference_db"
    )

    # Validate inputs
    if not annotations_path.exists():
        print(f"ERROR: Annotations not found: {annotations_path}")
        sys.exit(1)
    if not frames_dir.exists():
        print(f"ERROR: Frames directory not found: {frames_dir}")
        sys.exit(1)

    print(f"Building reference DB for: {args.game}")
    print(f"  Annotations: {annotations_path}")
    print(f"  Frames: {frames_dir}")
    print(f"  Output: {output_dir}")
    print()

    # Build
    db = ReferenceDB()
    db.build_from_annotations(annotations_path, frames_dir)

    # Save
    db.save(output_dir)

    # Summary
    print(f"\nReference DB built successfully!")
    print(f"  Total entries: {len(db.get_all_entries())}")
    print(f"  Screen types: {len(db.get_screen_types())}")
    for st in sorted(db.get_screen_types()):
        entries = db.get_entries(st)
        elem_count = sum(len(e.element_crops) for e in entries)
        print(f"    {st}: {len(entries)} frames, {elem_count} element crops")


if __name__ == "__main__":
    main()
