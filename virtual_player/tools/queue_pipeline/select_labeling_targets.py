"""
추가 라벨링 대상 자동 선정.

입력:
    - labels_validation_report.json — priority 30 레벨 리스트
    - stage1_out/level_to_images.json — 레벨별 click 이미지 매핑
    - 원본 이미지 폴더 (F:/LevelDesignExtractor/pixelflow/)
    - 기존 라벨 폴더 (labeling/images_queue/) — 중복 방지

선정 전략:
    1. Priority 30 레벨: 각 6장 (초반 2, 중반 2, 후반 2)     = 180장
    2. Multi-session top 레벨(L190, L170, L228, L300): 각 3장 추가 = 12장
    3. 튜토리얼 특별 처리 L1~L10: 이미 queue 부정확했으면 추가 2장씩 = 20장
    (중복 제거 후 약 180~210장)

출력:
    - labeling/images_queue_v2/ 폴더에 이미지 복사
    - selection_report.json (어느 레벨에서 몇 장 뽑았는지)

Usage:
    python select_labeling_targets.py \
        --validation-report .../labels_validation_report.json \
        --level-mapping .../stage1_out/level_to_images.json \
        --source-dir G:/LevelDesignExtractor/pixelflow \
        --existing-labels .../labeling/images_queue \
        --output-dir .../labeling/images_queue_v2 \
        --count-per-level 6
"""
import argparse
import json
import random
import re
import shutil
import sys
from pathlib import Path


SEQ_RE = re.compile(r"click_\d+_\d+_(\d+)_")


def parse_seq(filename: str) -> int:
    m = SEQ_RE.search(filename)
    return int(m.group(1)) if m else -1


def sample_from_level(images, count):
    """
    이미지 리스트에서 초반/중반/후반 고르게 count장 샘플.
    """
    n = len(images)
    if n == 0:
        return []
    if n <= count:
        return images[:]
    # Split into 3 segments
    seg_size = n // 3
    early = images[:seg_size]
    middle = images[seg_size : 2 * seg_size]
    late = images[2 * seg_size :]
    picks = []
    # Count per segment (distribute)
    per_seg = count // 3
    rem = count - per_seg * 3
    for seg, k in [(early, per_seg), (middle, per_seg), (late, per_seg + rem)]:
        if not seg:
            continue
        # Evenly spaced within segment
        if len(seg) <= k:
            picks.extend(seg)
        else:
            step = len(seg) // k
            picks.extend([seg[i * step] for i in range(k)])
    # De-duplicate preserving order
    seen = set()
    unique = []
    for p in picks:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique[:count]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--validation-report", required=True, type=Path)
    p.add_argument("--level-mapping", required=True, type=Path)
    p.add_argument("--source-dir", required=True, type=Path,
                   help="원본 이미지 폴더 (F: or G:)")
    p.add_argument("--existing-labels", required=True, type=Path,
                   help="기존 라벨 폴더 - 여기 있는 파일은 제외")
    p.add_argument("--output-dir", required=True, type=Path,
                   help="선정된 이미지 복사 위치")
    p.add_argument("--count-per-level", type=int, default=6,
                   help="priority 레벨당 선정 수")
    p.add_argument("--top-play-levels", nargs="+", type=int,
                   default=[190, 170, 228, 300, 183, 1150],
                   help="추가로 샘플링할 많이 플레이된 레벨")
    p.add_argument("--top-play-count", type=int, default=3)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    if not args.source_dir.exists():
        print(f"ERROR: source_dir not found: {args.source_dir}", file=sys.stderr)
        return 2

    report = json.loads(args.validation_report.read_text(encoding="utf-8"))
    priority = report["summary"]["priority_labeling_candidates"]
    print(f"Priority levels from validation ({len(priority)}): {priority}")

    mapping = json.loads(args.level_mapping.read_text(encoding="utf-8"))

    # Skip images already labeled
    existing = set()
    if args.existing_labels.exists():
        for p_ in args.existing_labels.glob("*.png"):
            # labeled files might be prefixed "L001__click_..." — extract click part
            name = p_.name
            m = re.search(r"(click_\d+_\d+_\d+_\w+\.png)", name)
            if m:
                existing.add(m.group(1))
            else:
                existing.add(name)
    print(f"Existing labeled images to skip: {len(existing)}")

    selection = {}
    all_selected = []

    # 1. Priority levels
    for lv in priority:
        imgs = mapping.get(str(lv), [])
        imgs = sorted(imgs, key=parse_seq)
        candidates = [im for im in imgs if im not in existing]
        picks = sample_from_level(candidates, args.count_per_level)
        selection[str(lv)] = picks
        all_selected.extend([(lv, im) for im in picks])

    # 2. Top-play levels
    for lv in args.top_play_levels:
        if lv in priority:
            continue  # already covered
        imgs = mapping.get(str(lv), [])
        imgs = sorted(imgs, key=parse_seq)
        candidates = [im for im in imgs if im not in existing]
        picks = sample_from_level(candidates, args.top_play_count)
        if picks:
            selection[str(lv)] = picks
            all_selected.extend([(lv, im) for im in picks])

    # Deduplicate
    seen = set()
    unique = []
    for lv, im in all_selected:
        if im in seen:
            continue
        seen.add(im)
        unique.append((lv, im))
    print(f"\nSelected {len(unique)} unique images across {len(selection)} levels")

    # Check source files exist
    missing = []
    valid = []
    for lv, im in unique:
        src = args.source_dir / im
        if src.exists():
            valid.append((lv, im))
        else:
            missing.append(im)
    if missing:
        print(f"WARNING: {len(missing)} images missing from source, first 5: {missing[:5]}")

    # Copy
    if not args.dry_run:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        copied = 0
        for lv, im in valid:
            src = args.source_dir / im
            # Add L{level} prefix like existing folder convention
            dst_name = f"L{lv:03d}__{im}"
            dst = args.output_dir / dst_name
            if not dst.exists():
                shutil.copy2(src, dst)
                copied += 1
        print(f"\nCopied {copied} images to {args.output_dir}")
    else:
        print("\n(dry-run mode - nothing copied)")

    report_out = args.output_dir / "selection_report.json" if not args.dry_run else None
    payload = {
        "total_priority_levels": len(priority),
        "total_top_play_levels": len(args.top_play_levels),
        "total_unique_selected": len(unique),
        "source_missing": len(missing),
        "valid_to_copy": len(valid),
        "per_level_counts": {lv: len(ims) for lv, ims in selection.items()},
        "selection_detail": {lv: ims for lv, ims in selection.items()},
    }
    if report_out:
        report_out.parent.mkdir(parents=True, exist_ok=True)
        report_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Report: {report_out}")

    print("\n=== SUMMARY ===")
    print(f"  Priority levels covered: {len(priority)}")
    print(f"  Top-play levels added:   {len([l for l in args.top_play_levels if l not in priority])}")
    print(f"  Unique images:           {len(unique)}")
    print(f"  Missing (source):        {len(missing)}")
    print(f"  Valid to label:          {len(valid)}")

    print("\n다음 단계:")
    print(f"  1. label_editor.py 실행 → --dir {args.output_dir}")
    print(f"  2. 각 이미지에 holder bbox + class 라벨링 (약 1-2분/장 × {len(valid)} = ~{len(valid)*1.5/60:.1f}시간)")
    print(f"  3. 완료 후 stage2c_train_holder.py 재학습 (3080 Ti ~45분)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
