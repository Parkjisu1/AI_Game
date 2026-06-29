"""
Level Design Extractor (Batch Mode) v2
=======================================
녹화 프레임에서 각 스테이지의 시작 보드(초기 배치)만 추출합니다.

v2 개선:
  - 분류 스무딩: 짧은 오분류 깜빡임(N프레임 미만) 무시
  - 보드 안정화: 전환 후 보드가 안정된 프레임 선택
  - 전역 중복 제거: 모든 기존 레벨과 해시 비교

동작 방식:
  1. YOLO 분류기로 모든 프레임을 screen type 분류
  2. 분류 스무딩 (깜빡임 제거)
  3. 안정적 전환 감지 (N프레임 연속 비-gameplay 후 gameplay 진입)
  4. 보드 안정화 대기 후 프레임 추출
  5. 전역 중복 제거
  6. index.json에 메타데이터 기록

사용법:
  python level_design_extractor.py --game carmatch
  python level_design_extractor.py --game carmatch --min-gap 5 --settle-frames 3
"""

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

from PIL import Image
import numpy as np


# ── 경로 설정 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent  # virtual_player/
DATA_DIR = BASE_DIR / "data"

YOLO_AVAILABLE = False
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    pass


def get_default_paths(game_id: str):
    """게임별 기본 경로 반환."""
    return {
        "frames_dir": DATA_DIR / "recordings" / game_id / "frames",
        "recording": DATA_DIR / "recordings" / game_id / "recording.json",
        "model": DATA_DIR / "games" / game_id / "yolo_dataset" / "models" / "screen_classifier_v2" / "weights" / "best.pt",
        "output_dir": DATA_DIR / "games" / game_id / "level_designs",
    }


def classify_frames_yolo(model_path: Path, frames: list[Path], conf_threshold: float = 0.5) -> list[dict]:
    """YOLO 분류기로 프레임들을 일괄 분류."""
    if not YOLO_AVAILABLE:
        print("[ERROR] ultralytics 미설치. pip install ultralytics")
        sys.exit(1)

    model = YOLO(str(model_path))
    results = []

    batch_size = 16
    for i in range(0, len(frames), batch_size):
        batch = frames[i:i + batch_size]
        batch_paths = [str(f) for f in batch]
        preds = model.predict(batch_paths, verbose=False, conf=conf_threshold)

        for j, pred in enumerate(preds):
            frame_path = batch[j]
            if pred.probs is not None:
                top_cls = int(pred.probs.top1)
                top_conf = float(pred.probs.top1conf)
                label = model.names[top_cls]
            else:
                label = "unknown"
                top_conf = 0.0

            results.append({
                "frame": frame_path.name,
                "label": label,
                "confidence": round(top_conf, 4),
            })

        done = min(i + batch_size, len(frames))
        print(f"\r  분류 진행: {done}/{len(frames)} frames", end="", flush=True)

    print()
    return results


# ── v2: 분류 스무딩 ──────────────────────────────────────────

def smooth_classifications(classifications: list[dict], min_run: int = 5) -> list[dict]:
    """짧은 오분류 구간을 주변 라벨로 스무딩.

    gameplay 사이에 min_run 미만의 비-gameplay 구간이 있으면
    해당 구간을 gameplay로 덮어씀 (깜빡임 제거).
    반대로, 비-gameplay 사이에 짧은 gameplay 구간도 제거.
    """
    if not classifications:
        return classifications

    smoothed = [dict(c) for c in classifications]  # deep copy
    labels = [c["label"] for c in smoothed]
    n = len(labels)

    # Run-length encoding
    runs = []  # (start_idx, length, label)
    i = 0
    while i < n:
        label = labels[i]
        j = i
        while j < n and labels[j] == label:
            j += 1
        runs.append((i, j - i, label))
        i = j

    # 짧은 구간을 양쪽 라벨로 대체
    for ri in range(1, len(runs) - 1):
        start, length, label = runs[ri]
        prev_label = runs[ri - 1][2]
        next_label = runs[ri + 1][2]

        # 양쪽이 같은 라벨이고, 현재 구간이 짧으면 → 스무딩
        if prev_label == next_label and length < min_run:
            for k in range(start, start + length):
                smoothed[k]["label"] = prev_label
                smoothed[k]["smoothed_from"] = label

    # 스무딩 통계
    changed = sum(1 for c in smoothed if "smoothed_from" in c)
    if changed > 0:
        print(f"  스무딩: {changed}개 프레임 보정")

    return smoothed


# ── v2: 안정적 전환 감지 ─────────────────────────────────────

def detect_stage_starts_v2(classifications: list[dict], min_gap: int = 5) -> list[int]:
    """진짜 스테이지 시작만 감지.

    조건:
    1. gameplay 진입 시점 (이전 라벨이 gameplay가 아님)
    2. 진입 전 비-gameplay 구간이 min_gap 프레임 이상 지속됨
       (짧은 깜빡임은 스무딩에서 이미 제거되었지만 이중 안전장치)
    """
    starts = []
    n = len(classifications)

    i = 0
    while i < n:
        label = classifications[i]["label"]

        if label != "gameplay":
            # 비-gameplay 구간 시작
            gap_start = i
            while i < n and classifications[i]["label"] != "gameplay":
                i += 1
            gap_length = i - gap_start

            # gameplay 진입 발견 + 비-gameplay 구간이 충분히 길었음
            if i < n and gap_length >= min_gap:
                starts.append(i)
            # gap이 너무 짧으면 → 스테이지 전환이 아닌 깜빡임 잔여
        else:
            i += 1

    # 첫 프레임이 gameplay인 경우도 포함
    if classifications and classifications[0]["label"] == "gameplay":
        if not starts or starts[0] != 0:
            starts.insert(0, 0)

    return starts


# ── v2: 보드 안정화 ──────────────────────────────────────────

def compute_image_hash(img_path: Path, hash_size: int = 16) -> str:
    """PIL 기반 평균 해시."""
    img = Image.open(img_path).convert("L").resize((hash_size, hash_size), Image.LANCZOS)
    arr = np.array(img)
    mean = arr.mean()
    bits = (arr > mean).flatten()
    return "".join("1" if b else "0" for b in bits)


def hamming_distance(h1: str, h2: str) -> int:
    return sum(c1 != c2 for c1, c2 in zip(h1, h2))


def compute_frame_delta(path_a: Path, path_b: Path, size: tuple = (270, 480)) -> float:
    """두 프레임 간 변화율 (0.0 ~ 1.0)."""
    img_a = np.array(Image.open(path_a).convert("L").resize(size, Image.LANCZOS), dtype=np.float32)
    img_b = np.array(Image.open(path_b).convert("L").resize(size, Image.LANCZOS), dtype=np.float32)
    diff = np.abs(img_a - img_b)
    return float(np.mean(diff) / 255.0)


def find_settled_frame(frame_files: list[Path], classifications: list[dict],
                       start_idx: int, settle_frames: int = 3,
                       settle_threshold: float = 0.02, max_search: int = 15) -> int:
    """전환 후 보드가 안정된 프레임 인덱스를 찾음.

    start_idx부터 연속 settle_frames개 프레임의 delta가 모두
    settle_threshold 미만이면 해당 첫 프레임을 반환.
    max_search 내에서 못 찾으면 start_idx 반환 (fallback).
    """
    n = len(frame_files)
    search_end = min(start_idx + max_search, n - 1)

    for i in range(start_idx, search_end - settle_frames + 1):
        # i ~ i+settle_frames 구간이 모두 gameplay인지 확인
        all_gameplay = all(
            classifications[i + k]["label"] == "gameplay"
            for k in range(settle_frames)
            if i + k < len(classifications)
        )
        if not all_gameplay:
            continue

        # 연속 프레임 간 delta 확인
        stable = True
        for k in range(settle_frames - 1):
            delta = compute_frame_delta(frame_files[i + k], frame_files[i + k + 1])
            if delta > settle_threshold:
                stable = False
                break

        if stable:
            return i

    return start_idx  # fallback


# ── v2: 전역 중복 제거 ──────────────────────────────────────

def filter_duplicates_global(start_indices: list[int], frames: list[Path],
                             hash_threshold: int = 20) -> tuple[list[int], list[tuple]]:
    """모든 기존 레벨과 비교하여 중복 제거 (직전뿐 아니라 전체)."""
    if not start_indices:
        return [], []

    filtered = []
    skipped = []
    known_hashes = []  # 지금까지 채택된 레벨의 해시들

    for idx in start_indices:
        curr_hash = compute_image_hash(frames[idx])

        # 모든 기존 레벨과 비교
        is_duplicate = False
        for prev_hash in known_hashes:
            dist = hamming_distance(prev_hash, curr_hash)
            if dist <= hash_threshold:
                skipped.append((idx, frames[idx].name, dist))
                is_duplicate = True
                break

        if not is_duplicate:
            filtered.append(idx)
            known_hashes.append(curr_hash)

    return filtered, skipped


def extract_levels(args):
    paths = get_default_paths(args.game)

    frames_dir = Path(args.frames_dir) if args.frames_dir else paths["frames_dir"]
    recording_path = Path(args.recording) if args.recording else paths["recording"]
    model_path = Path(args.model) if args.model else paths["model"]
    output_dir = Path(args.output_dir) if args.output_dir else paths["output_dir"]

    # ── 1. 프레임 목록 로드 ──
    if not frames_dir.exists():
        print(f"[ERROR] 프레임 디렉토리 없음: {frames_dir}")
        sys.exit(1)

    frame_files = sorted(frames_dir.glob("frame_*.png"))
    if not frame_files:
        frame_files = sorted(frames_dir.glob("*.png"))
    if not frame_files:
        print(f"[ERROR] 프레임 파일 없음: {frames_dir}")
        sys.exit(1)

    print(f"[1/5] 프레임 로드: {len(frame_files)}장 ({frames_dir})")

    # ── 2. 프레임 분류 ──
    if not model_path.exists():
        print(f"[ERROR] YOLO 모델 없음: {model_path}")
        sys.exit(1)

    print(f"[2/5] YOLO 분류 시작 ({model_path.name})")
    classifications = classify_frames_yolo(model_path, frame_files, conf_threshold=args.threshold)

    # 분류 통계 (스무딩 전)
    label_counts = {}
    for c in classifications:
        label_counts[c["label"]] = label_counts.get(c["label"], 0) + 1
    print(f"  원본 분류: {label_counts}")

    # ── 3. 분류 스무딩 ──
    print(f"[3/5] 분류 스무딩 (min_run={args.min_run})")
    classifications = smooth_classifications(classifications, min_run=args.min_run)

    # 스무딩 후 통계
    label_counts2 = {}
    for c in classifications:
        label_counts2[c["label"]] = label_counts2.get(c["label"], 0) + 1
    if label_counts != label_counts2:
        print(f"  스무딩 후: {label_counts2}")

    # ── 4. 스테이지 시작점 감지 ──
    print(f"[4/5] 스테이지 시작점 감지 (min_gap={args.min_gap})")
    raw_starts = detect_stage_starts_v2(classifications, min_gap=args.min_gap)
    print(f"  감지된 전환: {len(raw_starts)}개")

    for idx in raw_starts[:20]:  # 처음 20개만 표시
        cls = classifications[idx]
        prev = classifications[idx - 1]["label"] if idx > 0 else "none"
        print(f"    frame {cls['frame']}: {prev} -> gameplay (conf={cls['confidence']})")
    if len(raw_starts) > 20:
        print(f"    ... 외 {len(raw_starts) - 20}개")

    # 보드 안정화
    if args.settle_frames > 0:
        print(f"  보드 안정화 (settle={args.settle_frames}, threshold={args.settle_threshold})")
        settled_starts = []
        for idx in raw_starts:
            settled = find_settled_frame(
                frame_files, classifications, idx,
                settle_frames=args.settle_frames,
                settle_threshold=args.settle_threshold,
                max_search=args.max_settle_search,
            )
            if settled != idx:
                print(f"    {frame_files[idx].name} -> {frame_files[settled].name} (안정화 +{settled - idx})")
            settled_starts.append(settled)
        start_indices = settled_starts
    else:
        start_indices = raw_starts

    # 전역 중복 제거
    if args.skip_duplicates and len(start_indices) > 1:
        start_indices, skipped = filter_duplicates_global(
            start_indices, frame_files, hash_threshold=args.hash_threshold)
        if skipped:
            print(f"  중복 제거: {len(skipped)}개 스킵")
            for idx, name, dist in skipped[:10]:
                print(f"    [SKIP] {name} (hamming={dist})")
            if len(skipped) > 10:
                print(f"    ... 외 {len(skipped) - 10}개")
        print(f"  최종: {len(start_indices)}개")

    # ── 5. 추출 및 저장 ──
    print(f"[5/5] 레벨 디자인 추출 -> {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # recording.json 메타데이터
    recording_meta = {}
    if recording_path.exists():
        with open(recording_path, "r", encoding="utf-8") as f:
            rec = json.load(f)
            recording_meta = {
                "screen_width": rec.get("screen_width", 0),
                "screen_height": rec.get("screen_height", 0),
                "device": rec.get("device", ""),
            }

    levels = []
    for level_num, frame_idx in enumerate(start_indices, start=1):
        src_frame = frame_files[frame_idx]
        dst_name = f"level_{level_num:03d}.png"
        dst_path = output_dir / dst_name

        shutil.copy2(src_frame, dst_path)

        cls = classifications[frame_idx]
        prev_label = classifications[frame_idx - 1]["label"] if frame_idx > 0 else "none"

        level_entry = {
            "level": level_num,
            "image": dst_name,
            "source_frame": cls["frame"],
            "source_frame_index": frame_idx,
            "confidence": cls["confidence"],
            "transition_from": prev_label,
            "screen_size": [
                recording_meta.get("screen_width", 0),
                recording_meta.get("screen_height", 0),
            ],
        }
        levels.append(level_entry)

    # index.json 저장
    index = {
        "game_id": args.game,
        "total_frames": len(frame_files),
        "total_levels": len(levels),
        "model": model_path.name,
        "settings": {
            "threshold": args.threshold,
            "min_run": args.min_run,
            "min_gap": args.min_gap,
            "settle_frames": args.settle_frames,
            "settle_threshold": args.settle_threshold,
            "skip_duplicates": args.skip_duplicates,
            "hash_threshold": args.hash_threshold,
        },
        "levels": levels,
    }

    index_path = output_dir / "index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    # 전체 분류 결과 (디버그용)
    cls_path = output_dir / "frame_classifications.json"
    with open(cls_path, "w", encoding="utf-8") as f:
        json.dump(classifications, f, indent=2, ensure_ascii=False)

    print(f"\n완료: {len(levels)}개 레벨 추출")
    print(f"  레벨 이미지: {output_dir}")
    print(f"  인덱스: {index_path}")
    print(f"  분류 상세: {cls_path}")


def main():
    parser = argparse.ArgumentParser(description="Level Design Extractor v2 (Batch)")
    parser.add_argument("--game", required=True, help="게임 ID (예: carmatch)")
    parser.add_argument("--frames-dir", help="프레임 디렉토리")
    parser.add_argument("--recording", help="recording.json 경로")
    parser.add_argument("--model", help="YOLO 모델 경로")
    parser.add_argument("--output-dir", help="출력 디렉토리")

    # 분류 설정
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="YOLO confidence 임계값 (기본: 0.5)")

    # v2: 스무딩 설정
    parser.add_argument("--min-run", type=int, default=5,
                        help="스무딩 최소 연속 프레임 수 (기본: 5, 이보다 짧은 구간은 노이즈로 처리)")

    # v2: 전환 감지 설정
    parser.add_argument("--min-gap", type=int, default=5,
                        help="최소 비-gameplay 구간 길이 (기본: 5, 이보다 짧은 중단은 무시)")

    # v2: 보드 안정화 설정
    parser.add_argument("--settle-frames", type=int, default=3,
                        help="보드 안정화 확인 프레임 수 (기본: 3, 0이면 비활성화)")
    parser.add_argument("--settle-threshold", type=float, default=0.02,
                        help="안정화 delta 임계값 (기본: 0.02)")
    parser.add_argument("--max-settle-search", type=int, default=15,
                        help="안정화 탐색 최대 프레임 (기본: 15)")

    # 중복 제거 설정
    parser.add_argument("--skip-duplicates", action="store_true", default=True,
                        help="전역 중복 제거 (기본: on)")
    parser.add_argument("--no-skip-duplicates", action="store_true",
                        help="중복 제거 비활성화")
    parser.add_argument("--hash-threshold", type=int, default=20,
                        help="중복 판단 hamming 거리 (기본: 20)")

    args = parser.parse_args()
    if args.no_skip_duplicates:
        args.skip_duplicates = False

    extract_levels(args)


if __name__ == "__main__":
    main()
