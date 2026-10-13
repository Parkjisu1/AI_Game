"""conf 튜닝 실험 — cell_only_v2의 min_confidence 변경 후 재추출.

OUT_DIR만 변경해서 batch_all_levels.py 로직 재사용.
"""
from __future__ import annotations
import sys
import argparse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import batch_all_levels as bal
from hybrid_extractor import CellDetector


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--conf", type=float, required=True)
    ap.add_argument("--tag", type=str, required=True, help="예: c35, c40")
    args = ap.parse_args()

    # OUT_DIR 덮어쓰기
    bal.OUT_DIR = HERE / f"batch_all_levels_run_{args.tag}"

    # CellDetector default 변경 (monkey patch)
    orig_init = CellDetector.__init__

    def new_init(self, weights=None, min_confidence=None, max_det=5000,
                 imgsz=1920, use_hires=True):
        effective_conf = args.conf if min_confidence is None else min_confidence
        orig_init(self, weights=weights, min_confidence=effective_conf,
                  max_det=max_det, imgsz=imgsz, use_hires=use_hires)

    CellDetector.__init__ = new_init

    print(f"[conf_sweep] conf={args.conf}  OUT={bal.OUT_DIR}")
    bal.main()


if __name__ == "__main__":
    main()
