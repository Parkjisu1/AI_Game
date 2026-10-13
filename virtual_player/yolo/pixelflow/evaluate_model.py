"""
학습된 YOLO 모델 평가 + 약점 클래스 분석

사용:
  python evaluate_model.py                          # 기본 levels_v1 평가
  python evaluate_model.py --weights runs/X/best.pt
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import RUNS_DIR, DATASET_DIR, LEVELS_MODEL_WEIGHTS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", type=Path, default=LEVELS_MODEL_WEIGHTS)
    ap.add_argument("--data", type=Path, default=DATASET_DIR / "dataset.yaml")
    args = ap.parse_args()

    if not args.weights.exists():
        print(f"[ERROR] 모델 가중치 없음: {args.weights}")
        print("먼저 학습 실행: run_train.bat")
        return

    from ultralytics import YOLO
    model = YOLO(str(args.weights))

    print(f"[model] {args.weights}")
    print(f"[data]  {args.data}")
    print()

    # val 셋 평가
    metrics = model.val(data=str(args.data), verbose=False)

    # 전체 메트릭
    print("=" * 65)
    print(f"  Overall mAP50:    {metrics.box.map50:.3f}")
    print(f"  Overall mAP50-95: {metrics.box.map:.3f}")
    print(f"  Precision:        {metrics.box.mp:.3f}")
    print(f"  Recall:           {metrics.box.mr:.3f}")
    print("=" * 65)
    print()

    # 클래스별
    names = model.names
    maps = metrics.box.maps  # mAP50-95 per class
    p_per_class = metrics.box.p
    r_per_class = metrics.box.r
    map50_per_class = metrics.box.ap50

    print(f"{'Class':<22s} {'P':>6s} {'R':>6s} {'mAP50':>8s} {'mAP50-95':>10s}")
    print("-" * 65)

    weak_classes = []
    for i, name in names.items():
        if i >= len(maps):
            continue
        p = float(p_per_class[i]) if i < len(p_per_class) else 0
        r = float(r_per_class[i]) if i < len(r_per_class) else 0
        m50 = float(map50_per_class[i]) if i < len(map50_per_class) else 0
        m95 = float(maps[i])
        marker = ""
        if m50 < 0.5:
            marker = "  ⚠️"
            weak_classes.append((name, m50))
        print(f"{name:<22s} {p:>6.2f} {r:>6.2f} {m50:>8.3f} {m95:>10.3f}{marker}")

    print()
    if weak_classes:
        print(f"⚠️  취약 클래스 (mAP50 < 0.5): {len(weak_classes)}개")
        for n, m in weak_classes:
            print(f"   - {n}: {m:.3f}  → 라벨 추가 권장")
    else:
        print("✓ 모든 클래스 mAP50 >= 0.5")

    # 결과 파일 안내
    save_dir = Path(metrics.save_dir) if hasattr(metrics, "save_dir") else None
    if save_dir:
        print()
        print(f"상세 결과: {save_dir}")
        print(f"  - confusion_matrix.png  (클래스간 혼동 패턴)")
        print(f"  - results.png           (loss/mAP 그래프)")
        print(f"  - val_batch*_pred.jpg   (예측 시각화)")


if __name__ == "__main__":
    main()
