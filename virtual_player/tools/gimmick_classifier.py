"""Gimmick Type Classifier v2 — 1-NN with rich features
========================================================

개선 사항 (v2):
  - 5-point RGB 샘플링 (중심 + 4 내부 코너) — 다색 기믹 대응
  - aspect ratio log — snake 같은 길쭉한 bbox 식별
  - 상대 면적 log — pinata의 다양한 크기 대응
  - 1-NN (centroid 대신) — multi-modal 분포 자연 처리

성능:
  - DB 크기: ~1,261 bbox × 5 points = ~6,305 samples per class aggregated
  - 추론: class당 min distance, 가장 가까운 class 선택
"""
from __future__ import annotations
from pathlib import Path
import xml.etree.ElementTree as ET
import json
from collections import defaultdict
from typing import Optional

import cv2
import numpy as np


DEFAULT_XML_DIR = Path(r"E:\AI\virtual_player\yolo\pixelflow\labeling\labels_levels")
DEFAULT_IMG_DIR = Path(r"E:\AI\virtual_player\yolo\pixelflow\labeling\images_levels")
DEFAULT_SIG_PATH = Path(
    r"E:\AI\virtual_player\yolo\pixelflow\runs\gimmick_detector\gimmick_signatures_v2.npz"
)

GIMMICK_NAMES = {
    'hidden gimik', 'pinata gimik', 'snake gimik', 'ice gimik',
    'block gimik', 'wall gimik', 'key gimik', 'door gimik',
    'egg gimik', 'cannon gimik',
}

# Feature dims: R, G, B, aspect_log, area_log  (5 dim per sample point)
# Per bbox: 5 sample points → 5 separate feature rows
FEATURE_DIM = 5


def _sample_5points(img_bgr: np.ndarray, bbox: tuple[int, int, int, int]) -> list[np.ndarray]:
    """bbox 5개 샘플 지점(중심+내부 4코너) RGB 리턴.

    각 지점: 5×5 패치 평균 (1픽셀 노이즈 방지).
    """
    x1, y1, x2, y2 = bbox
    h_img, w_img = img_bgr.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w_img, x2), min(h_img, y2)
    if x2 <= x1 + 2 or y2 <= y1 + 2:
        return []
    bw, bh = x2 - x1, y2 - y1
    mx, my = max(1, bw // 5), max(1, bh // 5)
    pts = [
        ((x1 + x2) // 2, (y1 + y2) // 2),     # center
        (x1 + mx, y1 + my),                    # top-left
        (x2 - mx - 1, y1 + my),                # top-right
        (x1 + mx, y2 - my - 1),                # bot-left
        (x2 - mx - 1, y2 - my - 1),            # bot-right
    ]
    samples = []
    for cx, cy in pts:
        x0, x1p = max(0, cx - 2), min(w_img, cx + 3)
        y0, y1p = max(0, cy - 2), min(h_img, cy + 3)
        patch = img_bgr[y0:y1p, x0:x1p]
        if patch.size == 0:
            continue
        mean_bgr = patch.reshape(-1, 3).mean(axis=0)
        rgb = np.array([mean_bgr[2], mean_bgr[1], mean_bgr[0]])  # BGR→RGB
        samples.append(rgb)
    return samples


def _extract_features(
    img_bgr: np.ndarray,
    bbox: tuple[int, int, int, int],
    img_area: float,
) -> list[np.ndarray]:
    """bbox → 5개 5-dim 피처 벡터. (R, G, B, aspect_log, area_log)"""
    x1, y1, x2, y2 = bbox
    w, h = max(1, x2 - x1), max(1, y2 - y1)
    aspect = w / h
    area = w * h
    aspect_log = np.log(aspect)
    area_log = np.log(area / img_area * 10000.0 + 1e-6)  # per 10k image px
    rgbs = _sample_5points(img_bgr, bbox)
    feats = []
    for rgb in rgbs:
        feats.append(np.concatenate([rgb, [aspect_log, area_log]]))
    return feats


def build_signatures(
    xml_dir: Path = DEFAULT_XML_DIR,
    img_dir: Path = DEFAULT_IMG_DIR,
    out_path: Path = DEFAULT_SIG_PATH,
) -> None:
    """GT bbox에서 타입별 feature DB 구축 (npz)."""
    class_feats: dict[str, list[np.ndarray]] = defaultdict(list)

    xml_files = sorted(xml_dir.glob("level_*.xml"))
    print(f"Scanning {len(xml_files)} XML files...")

    for xml_path in xml_files:
        img_path = img_dir / f"{xml_path.stem}.png"
        if not img_path.exists():
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        img_area = float(img.shape[0] * img.shape[1])
        root = ET.parse(xml_path).getroot()
        for obj in root.findall("object"):
            name = (obj.find("name").text or "").strip().lower()
            if name not in GIMMICK_NAMES:
                continue
            bb = obj.find("bndbox")
            bbox = (
                int(float(bb.find("xmin").text)),
                int(float(bb.find("ymin").text)),
                int(float(bb.find("xmax").text)),
                int(float(bb.find("ymax").text)),
            )
            feats = _extract_features(img, bbox, img_area)
            class_feats[name].extend(feats)

    # Stack per class → np.ndarray
    db: dict[str, np.ndarray] = {}
    for name, feats in sorted(class_feats.items()):
        arr = np.stack(feats, axis=0).astype(np.float32)
        db[name] = arr
        print(f"  {name:16s} bboxes~{len(feats)//5:3d}  samples={len(feats):5d}  "
              f"RGB_mean=({arr[:,0].mean():5.1f},{arr[:,1].mean():5.1f},{arr[:,2].mean():5.1f})  "
              f"asp_log={arr[:,3].mean():+.2f}  area_log={arr[:,4].mean():+.2f}")

    # Global feature std for normalization
    all_feats = np.concatenate(list(db.values()), axis=0)
    feat_std = all_feats.std(axis=0) + 1e-6

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(out_path,
             feat_std=feat_std,
             class_names=np.array(list(db.keys())),
             **{f"cls_{name.replace(' ', '_')}": arr for name, arr in db.items()})
    print(f"\nSaved: {out_path}")
    print(f"Feature std (R,G,B,asp,area): {feat_std}")


class GimmickClassifier:
    """1-NN gimmick type classifier (5-point RGB + shape features)."""

    def __init__(self, sig_path: Path = DEFAULT_SIG_PATH):
        if not sig_path.exists():
            print(f"[GimmickClassifier] signatures not found: {sig_path}")
            self.signatures = {}
            return
        data = np.load(sig_path, allow_pickle=True)
        self.feat_std = data["feat_std"].astype(np.float32)
        self.class_names = list(data["class_names"])
        self.class_feats: dict[str, np.ndarray] = {}
        for name in self.class_names:
            arr = data[f"cls_{name.replace(' ', '_')}"].astype(np.float32)
            # Pre-normalize
            self.class_feats[name] = arr / self.feat_std
        self.signatures = self.class_feats  # 호환성 flag

    def classify(
        self, img_bgr: np.ndarray, bbox: tuple[int, int, int, int]
    ) -> tuple[str, float]:
        """bbox → (type_name, normalized_distance)."""
        if not self.signatures:
            return "gimmick", 0.0
        img_area = float(img_bgr.shape[0] * img_bgr.shape[1])
        feats = _extract_features(img_bgr, bbox, img_area)
        if not feats:
            return "gimmick", 0.0
        query = np.stack(feats, axis=0).astype(np.float32) / self.feat_std  # (5, 5)

        # class별 query-DB 최소 거리의 평균 (5 샘플 평균)
        best_class = None
        best_score = float("inf")
        for name, db_feats in self.class_feats.items():
            # dist matrix: (5, N)
            dmat = np.linalg.norm(
                query[:, None, :] - db_feats[None, :, :], axis=2
            )
            # 각 query sample의 최근접 거리 평균
            score = dmat.min(axis=1).mean()
            if score < best_score:
                best_score = score
                best_class = name
        return best_class, float(best_score)


if __name__ == "__main__":
    build_signatures()
