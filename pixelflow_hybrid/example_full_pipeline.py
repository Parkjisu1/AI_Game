"""
Example: 통합 파이프라인 데모.

실제 사용 시나리오:
  1. 레벨 N 시작
  2. 화면 캡처
  3. APK 정답으로 매칭
  4. 다음 탭 결정
"""
import sys
from pathlib import Path

# Allow running directly from this folder
sys.path.insert(0, str(Path(__file__).parent.parent))

from pixelflow_hybrid import LevelLoader, RuntimeDetector, StateMatcher


def demo_level(level_num: int, screenshot_path: str, variant: str = None):
    print(f"\n{'='*70}")
    print(f"Demo: Level {level_num}")
    print(f"{'='*70}")

    # 1. APK 정답 로드
    loader = LevelLoader()
    queue = loader.get_queue(level_num, variant)
    if not queue:
        print(f"  Level {level_num} APK 데이터 없음")
        return

    print(f"\n[APK 정답]")
    print(f"  Lines: {queue['line_count']}")
    print(f"  Total shooters: {queue['total_shooters']}")
    print(f"  Total ammo: {queue['total_ammo_sum']}")
    print(f"  처음 5 shooters:")
    flat = loader.get_expanded_queue(level_num, variant)
    for s in flat[:5]:
        print(f"    Line {s['line']} pos {s['position']}: "
              f"{s['material_name']} × {s['ammo']}")

    # 2. YOLO 화면 인식
    if not Path(screenshot_path).exists():
        print(f"\n  스크린샷 없음: {screenshot_path}")
        return

    det = RuntimeDetector()
    state = det.get_visible_state(screenshot_path)

    print(f"\n[YOLO 인식]")
    print(f"  검출된 holder: {state['holder_count']}")
    print(f"  검출된 라인 수: {state['line_count']}")
    print(f"  Line heads:")
    for h in state["line_heads"]:
        print(f"    Line {h['line']}: {h['name']} (conf={h['conf']})")

    # 3. APK ↔ YOLO 매칭
    matcher = StateMatcher(loader)
    matches = matcher.match_lines(level_num, state["line_heads"], variant)

    print(f"\n[Hybrid 매칭]")
    matched_count = sum(1 for m in matches if m["match"])
    print(f"  라인 매칭: {matched_count}/{len(matches)}")
    for m in matches:
        check = "✓" if m["match"] else "✗"
        obs = m["observed_name"]
        exp = m["expected_name"]
        print(f"    Line {m['observed_line']}: {obs} vs {exp} {check}")

    # 4. 진행도 추정
    progress = matcher.estimate_progress(level_num, state, variant)
    print(f"\n[진행도]")
    print(f"  추정: {progress.get('progress_pct')}% "
          f"({progress.get('estimated_consumed')}/{progress.get('estimated_total_shooters')})")

    # 5. 다음 탭 예측
    next_taps = matcher.predict_next_taps(level_num, state, n=3, variant=variant)
    print(f"\n[다음 3개 탭 예측 (APK 정답 기반)]")
    for t in next_taps:
        print(f"    Line {t['line']}: {t['material_name']} (id={t['id']}, ammo={t['ammo']})")


if __name__ == "__main__":
    # Sample images we have
    samples = [
        (1, "G:/LevelDesignExtractor/pixelflow/click_20260325_101717_0001_before.png"),
        (2, "G:/LevelDesignExtractor/pixelflow/click_20260325_101731_0015_before.png"),
    ]
    for lv, img in samples:
        if not Path(img).exists():
            # Try alt path
            alt = f"E:/AI/virtual_player/yolo/pixelflow/labeling/images_queue/L{lv:03d}__click_*.png"
            from glob import glob
            matches = glob(alt)
            if matches:
                img = matches[0]
        demo_level(lv, img)
