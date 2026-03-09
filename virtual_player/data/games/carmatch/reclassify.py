"""
YOLO 학습 데이터 재분류 스크립트
=================================
수동 검수 결과 기반 이미지 이동.
"""
import shutil
from pathlib import Path

BASE = Path(r"E:\AI\virtual_player\data\games\carmatch\yolo_dataset")

# ======================================================
# train/fail → train/popup (ingame_quit_confirm)
# ======================================================
FAIL_TO_POPUP = [
    "Screenshot_2026.03.06_17.23.54.639.png",  # Are you sure? Quit (lose 1 Life)
    "Screenshot_2026.03.06_17.23.56.939.png",  # Are you sure? Quit (lose streak)
    "Screenshot_2026.03.06_17.23.58.356.png",  # Are you sure? Quit (lose streak)
    "Screenshot_2026.03.06_17.24.00.639.png",  # Are you sure? Quit (lose keys)
    "Screenshot_2026.03.06_17.26.54.273.png",  # Are you sure? Quit (lose keys)
]

# ======================================================
# train/fail → train/other (event result)
# ======================================================
FAIL_TO_OTHER = [
    "Screenshot_2026.03.06_16.59.12.739.png",  # Punch Out event result
]

# ======================================================
# train/lobby → train/other (non-lobby screens)
# ======================================================
LOBBY_TO_OTHER = [
    # Leaderboard
    "Screenshot_2026.03.06_16.48.51.639.png",
    "Screenshot_2026.03.06_16.48.59.806.png",
    "Screenshot_2026.03.06_16.49.01.706.png",
    "Screenshot_2026.03.06_16.49.38.123.png",
    "Screenshot_2026.03.06_16.49.45.290.png",
    "Screenshot_2026.03.06_16.49.48.923.png",
    "Screenshot_2026.03.06_16.49.51.773.png",
    "Screenshot_2026.03.06_16.49.57.656.png",
    # Shop
    "Screenshot_2026.03.06_16.49.20.039.png",
    "Screenshot_2026.03.06_16.49.24.073.png",
    "Screenshot_2026.03.06_16.49.26.306.png",
    # Journey
    "Screenshot_2026.03.06_16.50.39.306.png",
    "Screenshot_2026.03.06_16.50.43.206.png",
    "Screenshot_2026.03.06_16.50.55.906.png",
    "Screenshot_2026.03.06_16.51.00.606.png",
    "Screenshot_2026.03.06_16.51.04.340.png",
    "Screenshot_2026.03.06_16.51.07.623.png",
    # Settings
    "Screenshot_2026.03.06_16.51.10.206.png",
]

# ======================================================
# train/lobby → train/popup (event popups)
# ======================================================
LOBBY_TO_POPUP = [
    "Screenshot_2026.03.06_17.04.36.706.png",  # Daily Bonus
    "Screenshot_2026.03.06_17.05.36.823.png",  # Getaway Pack (purchase)
    "Screenshot_2026.03.06_17.08.28.823.png",  # Streak Race
]


def move_files(file_list, src_class, dst_class, split="train"):
    """파일 이동."""
    src_dir = BASE / split / src_class
    dst_dir = BASE / split / dst_class
    dst_dir.mkdir(parents=True, exist_ok=True)

    moved = 0
    for fname in file_list:
        src = src_dir / fname
        dst = dst_dir / fname
        if src.exists():
            shutil.move(str(src), str(dst))
            moved += 1
            print(f"  {src_class} → {dst_class}: {fname}")
        else:
            print(f"  NOT FOUND: {src}")
    return moved


def count_classes(split="train"):
    """클래스별 이미지 수."""
    split_dir = BASE / split
    if not split_dir.exists():
        return {}
    counts = {}
    for d in sorted(split_dir.iterdir()):
        if d.is_dir():
            n = len(list(d.glob("*.png")))
            counts[d.name] = n
    return counts


def main():
    print("=" * 50)
    print("YOLO 학습 데이터 재분류")
    print("=" * 50)

    # 재분류 전 현황
    print("\n[BEFORE]")
    for split in ["train", "val"]:
        counts = count_classes(split)
        total = sum(counts.values())
        print(f"  {split}: {counts} (total: {total})")

    # 이동 실행
    print("\n[MOVING FILES]")

    total_moved = 0
    total_moved += move_files(FAIL_TO_POPUP, "fail", "popup", "train")
    total_moved += move_files(FAIL_TO_OTHER, "fail", "other", "train")
    total_moved += move_files(LOBBY_TO_OTHER, "lobby", "other", "train")
    total_moved += move_files(LOBBY_TO_POPUP, "lobby", "popup", "train")

    print(f"\nTotal moved: {total_moved} files")

    # 재분류 후 현황
    print("\n[AFTER]")
    for split in ["train", "val"]:
        counts = count_classes(split)
        total = sum(counts.values())
        print(f"  {split}: {counts} (total: {total})")

    # 캐시 삭제 (YOLO 재학습 시 필요)
    for cache in BASE.glob("**/*.cache"):
        cache.unlink()
        print(f"  Deleted cache: {cache}")

    print("\n✓ 재분류 완료. YOLO 재학습 준비됨.")


if __name__ == "__main__":
    main()
