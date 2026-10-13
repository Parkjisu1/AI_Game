"""
RuntimeDetector — YOLO holder_detector + v7 알고리즘으로 실시간 화면 인식.

입력: 스크린샷 이미지 (numpy array 또는 파일 경로)
출력: 현재 visible holders (라인별 + 색 + 위치)
"""
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import Counter


DEFAULT_WEIGHTS = Path("E:/AI/virtual_player/yolo/pixelflow/runs/holder_detector/weights/best.pt")

CLASS_NAMES = (
    [f"holder_c{i}" for i in range(1, 30)]                       # 0~28
    + ["gimmick_snake", "gimmick_pinata", "gimmick_ice",          # 29~31
       "gimmick_block", "gimmick_wall", "gimmick_key",            # 32~34
       "gimmick_door", "gimmick_egg", "gimmick_hidden",           # 35~37
       "gimmick_cannon"]                                          # 38
    + ["current_balloon"]                                         # 39
)


class RuntimeDetector:
    """YOLO 기반 화면 holder 검출기."""

    def __init__(self, weights_path: Path = DEFAULT_WEIGHTS,
                 conf_threshold: float = 0.4, imgsz: int = 1280):
        self.weights_path = Path(weights_path)
        if not self.weights_path.exists():
            raise FileNotFoundError(f"Weights not found: {self.weights_path}")
        self.conf_threshold = conf_threshold
        self.imgsz = imgsz
        self._model = None

    def _load_model(self):
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(str(self.weights_path))
        return self._model

    def detect(self, image, conf: Optional[float] = None) -> List[dict]:
        """
        Args:
            image: 파일 경로 또는 numpy array (BGR)
            conf: confidence threshold (default: self.conf_threshold)

        Returns:
            List of detected holders:
              [{class, name, material, conf, bbox, cx, cy, kind}]
            kind: 'holder' (1-29) | 'gimmick' (30+) | 'current_balloon' (40)
        """
        model = self._load_model()
        c = conf if conf is not None else self.conf_threshold

        results = model.predict(
            source=image, conf=c, iou=0.7, imgsz=self.imgsz,
            verbose=False, save=False
        )
        if not results:
            return []
        r = results[0]
        if r.boxes is None or len(r.boxes) == 0:
            return []

        out = []
        for box, cls, conf_val in zip(
            r.boxes.xyxy.cpu().numpy(),
            r.boxes.cls.cpu().numpy(),
            r.boxes.conf.cpu().numpy(),
        ):
            cls_id = int(cls)
            x1, y1, x2, y2 = (float(box[0]), float(box[1]),
                              float(box[2]), float(box[3]))

            # Map class to material code (APK convention)
            if 0 <= cls_id <= 28:
                material = cls_id + 1  # holder_c1 → material 1
                kind = "holder"
            elif 29 <= cls_id <= 38:
                material = cls_id + 1  # gimmick_snake → material 30
                kind = "gimmick"
            elif cls_id == 39:
                material = 40  # current_balloon
                kind = "current_balloon"
            else:
                continue

            name = CLASS_NAMES[cls_id] if cls_id < len(CLASS_NAMES) else f"cls{cls_id}"
            out.append({
                "class": cls_id,
                "name": name,
                "material": material,
                "kind": kind,
                "conf": round(float(conf_val), 3),
                "bbox": [x1, y1, x2, y2],
                "cx": (x1 + x2) / 2,
                "cy": (y1 + y2) / 2,
            })
        return out

    def cluster_by_lines(self, holders: List[dict],
                        gap_x: float = 80) -> List[List[dict]]:
        """
        화면에 검출된 holder들을 X 좌표로 라인별 그룹핑.

        Returns: List of clusters, each cluster is a vertical line of holders.
        """
        if not holders:
            return []
        holders_only = [h for h in holders if h["kind"] == "holder"]
        if not holders_only:
            return []
        sorted_h = sorted(holders_only, key=lambda h: h["cx"])
        clusters = [[sorted_h[0]]]
        for h in sorted_h[1:]:
            prev_cx_avg = sum(x["cx"] for x in clusters[-1]) / len(clusters[-1])
            if abs(h["cx"] - prev_cx_avg) < gap_x:
                clusters[-1].append(h)
            else:
                clusters.append([h])
        # Sort each cluster by cy (head usually at bottom = larger cy)
        for c in clusters:
            c.sort(key=lambda h: -h["cy"])  # head first
        return clusters

    def get_visible_state(self, image) -> dict:
        """
        High-level: 화면에서 현재 visible state 요약.

        Returns:
          {
            "holders": [...],
            "lines": [[holders in line 0], [...]],
            "line_heads": [{material, name, position, conf}, ...],
            "gimmicks": [...],
            "current_balloon": {...} or None,
            "color_distribution": Counter,
          }
        """
        all_dets = self.detect(image)
        holders = [h for h in all_dets if h["kind"] == "holder"]
        gimmicks = [h for h in all_dets if h["kind"] == "gimmick"]
        cur_balloons = [h for h in all_dets if h["kind"] == "current_balloon"]

        clusters = self.cluster_by_lines(holders)
        line_heads = []
        for i, cluster in enumerate(clusters):
            if cluster:
                head = cluster[0]
                line_heads.append({
                    "line": i,
                    "material": head["material"],
                    "name": head["name"],
                    "conf": head["conf"],
                    "cx": head["cx"], "cy": head["cy"],
                })

        color_dist = Counter(h["material"] for h in holders)

        return {
            "holders": holders,
            "holder_count": len(holders),
            "lines": clusters,
            "line_count": len(clusters),
            "line_heads": line_heads,
            "gimmicks": gimmicks,
            "current_balloon": cur_balloons[0] if cur_balloons else None,
            "color_distribution": dict(color_dist),
        }


if __name__ == "__main__":
    # Quick test on a sample image
    sample_img = "G:/LevelDesignExtractor/pixelflow/click_20260325_101717_0001_before.png"
    if not Path(sample_img).exists():
        sample_img = "E:/AI/virtual_player/yolo/pixelflow/labeling/images_queue/L001__click_20260325_101717_0001_before.png"
    if Path(sample_img).exists():
        det = RuntimeDetector()
        state = det.get_visible_state(sample_img)
        print(f"Image: {sample_img}")
        print(f"Holders: {state['holder_count']}")
        print(f"Lines: {state['line_count']}")
        print(f"Line heads:")
        for h in state["line_heads"]:
            print(f"  Line {h['line']}: {h['name']} (conf={h['conf']})")
        print(f"Gimmicks: {len(state['gimmicks'])}")
        print(f"Color distribution: {state['color_distribution']}")
    else:
        print("No sample image found")
