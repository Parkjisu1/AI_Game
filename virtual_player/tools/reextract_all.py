"""
전체 레벨 재추출 스크립트
=========================
기존 data/pixelflow/levels/json 의 250 레벨을 하이브리드 추출기로 재추출.
새 파일은 data/pixelflow/levels/json_v2 에 저장.
비교 리포트 출력.
"""
import sys
import json
import time
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent))
from hybrid_extractor import extract_level, GimmickDetector
from cell_aware_analyzer import load_profile


def main():
    base = Path(r"E:\AI\virtual_player\data\pixelflow")
    img_dir = base / "images"
    old_json_dir = base / "levels" / "json"
    new_json_dir = base / "levels" / "json_v2"
    new_json_dir.mkdir(parents=True, exist_ok=True)

    profile = load_profile(str(base / "profile" / "cell_profile.json"))
    detector = GimmickDetector()

    print(f"[env] gimmick detector: {'OK' if detector._model else 'FAIL'}")
    print(f"[env] gimmick classes: {len(detector.gimmick_types)}")

    old_files = sorted(old_json_dir.glob("level_*.json"))
    print(f"[input] {len(old_files)} old levels")

    stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "grid_same": 0,
        "grid_diff": 0,
        "time_ms_sum": 0,
    }

    results = []
    t0 = time.time()

    for i, old_path in enumerate(old_files):
        old_data = json.loads(old_path.read_text(encoding="utf-8"))
        src = old_data.get("pixel_art_source", "")
        if not src:
            continue

        img_path = img_dir / src
        if not img_path.exists():
            stats["failed"] += 1
            continue

        lv = old_data.get("level_number", i + 1)
        t1 = time.time()
        new_data = extract_level(img_path, profile, lv, detector)
        stats["time_ms_sum"] += (time.time() - t1) * 1000

        stats["total"] += 1

        if "error" in new_data:
            stats["failed"] += 1
            continue

        stats["success"] += 1

        # 그리드 변화
        old_grid = (old_data.get("field_columns", 0), old_data.get("field_rows", 0))
        new_grid = (new_data.get("field_columns", 0), new_data.get("field_rows", 0))
        if old_grid == new_grid:
            stats["grid_same"] += 1
        else:
            stats["grid_diff"] += 1

        # JSON 저장
        out = new_json_dir / old_path.name
        out.write_text(
            json.dumps(new_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        results.append({
            "level": lv,
            "old_grid": old_grid,
            "new_grid": new_grid,
            "old_colors": old_data.get("num_colors", 0),
            "new_colors": new_data.get("num_colors", 0),
            "new_gimmicks": len(new_data.get("gimmicks", {})),
            "gimmick_count": sum(new_data.get("gimmicks", {}).values()),
            "grid_conf": new_data.get("grid_confidence", 0),
        })

        if (i + 1) % 25 == 0:
            print(f"  [{i+1}/{len(old_files)}] "
                  f"latest: lv{lv} old={old_grid[0]}x{old_grid[1]} new={new_grid[0]}x{new_grid[1]}")

    elapsed = time.time() - t0
    print(f"\n[done] {elapsed:.1f}s, avg {stats['time_ms_sum']/max(1,stats['total']):.0f}ms/image")

    # 통계 요약
    print(f"\n{'='*70}")
    print(f"  RE-EXTRACTION SUMMARY")
    print(f"{'='*70}")
    print(f"  Total:     {stats['total']}")
    print(f"  Success:   {stats['success']}")
    print(f"  Failed:    {stats['failed']}")
    print(f"  Grid same: {stats['grid_same']} ({stats['grid_same']*100//max(1,stats['success'])}%)")
    print(f"  Grid diff: {stats['grid_diff']} ({stats['grid_diff']*100//max(1,stats['success'])}%)")

    # 그리드 크기 분포
    new_grid_counter = Counter(r["new_grid"] for r in results)
    print(f"\n  New grid distribution (top 15):")
    for grid, cnt in new_grid_counter.most_common(15):
        print(f"    {grid[0]:>3}x{grid[1]:<3}: {cnt} levels")

    # 기믹 탐지 성공률
    with_gimmicks = sum(1 for r in results if r["gimmick_count"] > 0)
    total_gimmicks = sum(r["gimmick_count"] for r in results)
    print(f"\n  Gimmicks detected: {total_gimmicks} total across {with_gimmicks}/{len(results)} levels")

    # Grid confidence 분포
    confs = [r["grid_conf"] for r in results]
    if confs:
        print(f"\n  Grid confidence: min={min(confs):.3f}, max={max(confs):.3f}, "
              f"mean={sum(confs)/len(confs):.3f}")

    # 요약 저장
    summary = {
        "stats": stats,
        "sample_results": results[:20],
        "grid_distribution": {f"{g[0]}x{g[1]}": c for g, c in new_grid_counter.most_common(30)},
    }
    (new_json_dir.parent / "reextract_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n  Summary saved: {new_json_dir.parent / 'reextract_summary.json'}")
    print(f"  New JSONs:     {new_json_dir}")


if __name__ == "__main__":
    main()
