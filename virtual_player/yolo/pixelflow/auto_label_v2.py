"""
Auto-Label Generator v2 (Hybrid Extractor 기반)
================================================
Hybrid Extractor (YOLO board + FFT grid + 픽셀 색상)로
이미지에서 셀 bbox를 자동 생성 → PascalVOC XML 저장.

labelImg 또는 자체 label_editor.py 에서 열어서 편집 가능.

사용법:
  python auto_label_v2.py --image path/to/img.png
  python auto_label_v2.py --dir path/to/images/
  python auto_label_v2.py --dir labeling/images --out labeling/labels_auto --skip-existing

출력: {입력이미지 stem}.xml (PascalVOC 포맷)
"""
from __future__ import annotations
import sys
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _paths import TOOLS_DIR, PROFILE_PATH, LABEL_IMAGES_DIR, LABEL_XML_DIR
sys.path.insert(0, str(TOOLS_DIR))

from cell_aware_analyzer import (
    load_profile, build_render_palette, classify_pixel,
)
from board_detector import BoardDetector
from grid_detector import detect_grid_dimensions


# ══════════════════════════════════════════════════════════════
#  팔레트 ID → labelImg 클래스명 매핑
#  (현재 라벨링된 19 cell 클래스에 맞춘 근사 매핑)
# ══════════════════════════════════════════════════════════════
PALETTE_TO_LABEL: dict[int, str | None] = {
    1: "pink cell",
    2: "cyan cell",
    3: "purple cell",
    4: "yellow cell",
    5: "green cell",
    6: "orange cell",
    7: "white cell",
    8: "black cell",
    9: "blue cell",
    10: "dark green cell",
    11: "red cell",
    12: "blue cell",
    13: "dark green cell",
    14: "white blue cell",
    15: "white blue cell",
    16: "brown cell",
    17: "white yellow cell",
    18: "pink cell",
    19: "hot pink cell",
    20: "white green cell",
    21: "black cell",          # DarkPurple (64,69,119) — 게임에서 어두운 셀 = 검정
    22: "brown cell",          # DustyRose (187,135,98) = Brown 계열 (render 기준)
    23: "white cell",
    24: "gray cell",
    25: "hot pink cell",
    26: "orange cell",
    27: "brown red cell",
    28: "cyan cell",
    29: "dark gray cell",
}

MIN_CELL_SIZE_PX = 6

# 이상치 필터링 파라미터
SIZE_TOLERANCE = 0.30       # 크기 median 대비 ±30%
MAX_COLOR_STD = 60.0        # 셀 내부 RGB std 완화 (3D 그라데이션 허용)
MIN_VOTE_RATIO = 0.4
MAX_PALETTE_DISTANCE = 100.0  # 팔레트 거리 완화
ASPECT_MIN = 0.85           # w/h 허용 범위 약간 완화
ASPECT_MAX = 1.18


def classify_cell_region(
    board_rgb: np.ndarray,
    x0: int, y0: int, x1: int, y1: int,
    pal_keys: list, pal_arr: np.ndarray,
    min_saturation: float = 20.0,
    skip_background: bool = True,
) -> int:
    """셀 영역의 대표 색상 (팔레트 ID) 반환.

    개선:
      - 3D 셀 대응: 셀 상단 25~65% (Y) + 중앙 30~70% (X) 샘플링
      - 바닥 타일 필터: 채도 낮으면 -1 반환 (skip)
    """
    cell = board_rgb[y0:y1, x0:x1]
    if cell.size == 0:
        return 21

    h, w = cell.shape[:2]
    votes: Counter = Counter()

    # 적응적 샘플링: 셀 크기가 작으면 margin 작게
    if min(w, h) < 18:
        # 작은 셀: 중앙 1/3 정도 (정사각형)
        ym0 = h // 3; ym1 = max(ym0 + 1, 2 * h // 3)
        xm0 = w // 3; xm1 = max(xm0 + 1, 2 * w // 3)
    else:
        # 큰 셀 (3D 블록): 상단 평평 부분 + 중앙
        ym0 = int(h * 0.25); ym1 = int(h * 0.65)
        xm0 = int(w * 0.30); xm1 = int(w * 0.70)
    if ym1 - ym0 < 2 or xm1 - xm0 < 2:
        center = cell
    else:
        center = cell[ym0:ym1, xm0:xm1]

    # 바닥 타일/배경 필터 1: 채도 낮고 어두움 = 배경
    if skip_background and center.size > 0:
        import cv2 as _cv2
        center_bgr = _cv2.cvtColor(center, _cv2.COLOR_RGB2BGR)
        hsv = _cv2.cvtColor(center_bgr, _cv2.COLOR_BGR2HSV)
        sat_mean = float(hsv[:, :, 1].mean())
        val_mean = float(hsv[:, :, 2].mean())
        # 매우 어두움 AND 채도 낮음 = 배경/바닥
        if sat_mean < min_saturation and val_mean < 70:
            return -1  # 배경 신호

    # 바닥 타일/배경 필터 2: 색상 분산 큰 영역 = 셀 경계/그라데이션
    if skip_background and center.size > 0:
        std_rgb = float(np.std(center.reshape(-1, 3), axis=0).mean())
        if std_rgb > MAX_COLOR_STD:
            return -1

    # 기믹/특이 색 필터: 중앙 중심 픽셀이 팔레트 어느 색에도 멀면 skip
    if skip_background and center.size > 0:
        ch, cw = center.shape[:2]
        mid = center[ch // 2, cw // 2].astype(np.float64)
        dists_to_palette = np.sqrt(np.sum((pal_arr - mid) ** 2, axis=1))
        if dists_to_palette.min() > MAX_PALETTE_DISTANCE:
            return -1  # 팔레트 밖 = 기믹/특이

    # 엣지 밀도 필터: 셀 경계가 중앙보다 어두워야 진짜 셀 (gridline 존재)
    # 바닥 타일은 경계가 중앙과 비슷 → 필터링
    if skip_background and cell.shape[0] >= 6 and cell.shape[1] >= 6:
        ch_c, cw_c = cell.shape[:2]
        # 경계 2px
        top = cell[0:2, :].mean(axis=(0, 1))
        bot = cell[-2:, :].mean(axis=(0, 1))
        lft = cell[:, 0:2].mean(axis=(0, 1))
        rgt = cell[:, -2:].mean(axis=(0, 1))
        edge_brightness = float(np.mean([max(top), max(bot), max(lft), max(rgt)]))

        # 중앙 brightness (이미 center 영역)
        if center.size > 0:
            center_brightness = float(center.reshape(-1, 3).max(axis=1).mean())
        else:
            center_brightness = 0

        # 엣지 밀도 필터 완화: 명확히 차이 없는 경우만 제거
        # (inner_mask가 주 필터 역할, 여기는 보조)
        if center_brightness > 100 and (center_brightness - edge_brightness) < 3:
            return -1  # 확실히 gridline 없음

    if center.size == 0:
        return 21

    ch, cw = center.shape[:2]
    for fy in [0.3, 0.5, 0.7]:
        for fx in [0.3, 0.5, 0.7]:
            sy = min(ch - 1, max(0, int(fy * ch)))
            sx = min(cw - 1, max(0, int(fx * cw)))
            pixel = center[sy, sx].astype(np.float64)
            cid = classify_pixel(pixel, pal_keys, pal_arr)
            weight = 3 if (fy == 0.5 and fx == 0.5) else 1
            votes[cid] += weight

    med = np.median(center.reshape(-1, 3), axis=0).astype(np.float64)
    votes[classify_pixel(med, pal_keys, pal_arr)] += 2
    return votes.most_common(1)[0][0]


def _get_inner_board_mask(board_rgb: np.ndarray) -> np.ndarray:
    """보드 이미지에서 '검은 아웃라인 안쪽' 마스크 생성.

    1) 채도 있거나 밝은 픽셀 = 셀 후보
    2) 강한 dilate → 검은 셀도 포함 (주변 컬러 셀과 연결)
    3) close → 내부 구멍 채움
    4) erode → 외부 과포함 방지
    5) 가장 큰 CC = 보드 내부
    """
    h, w = board_rgb.shape[:2]
    hsv = cv2.cvtColor(board_rgb, cv2.COLOR_RGB2HSV)

    sat = hsv[:, :, 1]
    val = hsv[:, :, 2]
    # 셀 후보: 채도 있거나 충분히 밝음
    cell_mask = ((sat > 30) | (val > 180)).astype(np.uint8) * 255

    # 강한 dilate로 어두운 셀(검은색)도 포함
    k1 = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    dilated = cv2.dilate(cell_mask, k1, iterations=1)

    # 큰 구멍 채우기
    k2 = cv2.getStructuringElement(cv2.MORPH_RECT, (35, 35))
    closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, k2)

    # erode로 외부 과포함 축소
    k3 = cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11))
    eroded = cv2.erode(closed, k3, iterations=1)

    # 가장 큰 CC = 보드 내부
    num, labels, stats, _ = cv2.connectedComponentsWithStats(eroded)
    if num <= 1:
        return eroded

    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = int(np.argmax(areas)) + 1
    return (labels == largest).astype(np.uint8) * 255


def generate_bboxes(img_bgr: np.ndarray, profile: dict,
                    board_rect: tuple[int, int, int, int] | None = None,
                    use_inner_mask: bool = True) -> list[dict]:
    """이미지 → 셀 bbox + 라벨 리스트 (원본 이미지 좌표계).

    Args:
        board_rect: (x, y, w, h) 사용자 지정 보드 영역.
                    None이면 YOLO board_detector 사용.
        use_inner_mask: True면 검은 아웃라인 내부만 유효.
    """
    if board_rect is not None:
        bx, by, bw, bh = board_rect
        H, W = img_bgr.shape[:2]
        bx = max(0, min(W - 1, int(bx)))
        by = max(0, min(H - 1, int(by)))
        bw = max(1, min(W - bx, int(bw)))
        bh = max(1, min(H - by, int(bh)))
        board_bgr = img_bgr[by:by + bh, bx:bx + bw]
    else:
        bd = BoardDetector()
        board_bgr, (bx, by, bw, bh) = bd.detect(img_bgr)
    board_rgb = cv2.cvtColor(board_bgr, cv2.COLOR_BGR2RGB)

    # 보드 내부 마스크 (검은 아웃라인 안쪽만)
    inner_mask = _get_inner_board_mask(board_rgb) if use_inner_mask else None

    grid = detect_grid_dimensions(board_rgb)
    gridlines_h = grid["gridlines_h"]
    gridlines_v = grid["gridlines_v"]

    if len(gridlines_h) < 2 or len(gridlines_v) < 2:
        return []

    pal_keys, pal_arr = build_render_palette(profile)

    bboxes: list[dict] = []
    for r in range(len(gridlines_v) - 1):
        for c in range(len(gridlines_h) - 1):
            cx0 = gridlines_h[c]
            cx1 = gridlines_h[c + 1]
            cy0 = gridlines_v[r]
            cy1 = gridlines_v[r + 1]

            if cx1 - cx0 < MIN_CELL_SIZE_PX or cy1 - cy0 < MIN_CELL_SIZE_PX:
                continue

            # 보드 내부 마스크 체크: 셀 중심이 마스크 내부에 있어야
            if inner_mask is not None:
                ccx = (cx0 + cx1) // 2
                ccy = (cy0 + cy1) // 2
                ih, iw = inner_mask.shape[:2]
                if 0 <= ccy < ih and 0 <= ccx < iw:
                    if inner_mask[ccy, ccx] == 0:
                        continue  # 마스크 밖 = 검은 아웃라인 외부
                else:
                    continue

            pid = classify_cell_region(
                board_rgb, cx0, cy0, cx1, cy1, pal_keys, pal_arr
            )
            # -1 = 바닥/배경 필터됨
            if pid == -1:
                continue
            label = PALETTE_TO_LABEL.get(pid)
            if label is None:
                continue

            bboxes.append({
                "name": label,
                "xmin": int(bx + cx0),
                "ymin": int(by + cy0),
                "xmax": int(bx + cx1),
                "ymax": int(by + cy1),
                "palette_id": pid,
                "row": r,
                "col": c,
            })

    # 최종 필터: 사이즈 median에서 벗어나는 이상치 제거
    bboxes = _filter_outlier_sizes(bboxes, SIZE_TOLERANCE)

    # Aspect ratio 필터: 정사각형에 가깝지 않은 것 제거
    bboxes = _filter_aspect_ratio(bboxes, ASPECT_MIN, ASPECT_MAX)

    # 큰 연결 클러스터 제거 (바닥 타일) - 관대하게 (검은 셀 많을 수 있음)
    bboxes = _filter_large_clusters(bboxes, max_ratio=0.50)

    return bboxes


def _filter_aspect_ratio(bboxes: list[dict], min_ratio: float, max_ratio: float) -> list[dict]:
    """bbox의 가로세로 비율(w/h)이 정사각형 범위를 벗어나면 제거."""
    keep = []
    for b in bboxes:
        w = b["xmax"] - b["xmin"]
        h = b["ymax"] - b["ymin"]
        if h <= 0 or w <= 0:
            continue
        ratio = w / h
        if min_ratio <= ratio <= max_ratio:
            keep.append(b)
    return keep


def _filter_large_clusters(bboxes: list[dict], max_ratio: float = 0.25) -> list[dict]:
    """같은 클래스의 connected component가 너무 크면 배경으로 간주하고 제거.

    바닥 타일은 같은 색이 넓게 이어짐 → 큰 클러스터.
    실제 게임 셀은 다양한 색이 섞여 있음 → 작은~중간 클러스터.
    """
    if len(bboxes) < 10:
        return bboxes

    # 그리드 맵
    grid: dict[tuple[int, int], dict] = {}
    for b in bboxes:
        grid[(b["row"], b["col"])] = b

    visited = set()
    large_components: list[tuple[int, int]] = []
    total = len(bboxes)
    max_size = int(total * max_ratio)

    # 4방향 인접 bfs로 같은 클래스 connected component 탐지
    for start, sb in grid.items():
        if start in visited:
            continue
        class_name = sb["name"]
        comp = []
        stack = [start]
        while stack:
            pos = stack.pop()
            if pos in visited:
                continue
            b = grid.get(pos)
            if b is None or b["name"] != class_name:
                continue
            visited.add(pos)
            comp.append(pos)
            r, c = pos
            stack.extend([(r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)])

        if len(comp) > max_size:
            large_components.extend(comp)

    if not large_components:
        return bboxes

    remove_set = set(large_components)
    return [b for b in bboxes if (b["row"], b["col"]) not in remove_set]


def _filter_outlier_sizes(bboxes: list[dict], tolerance: float = 0.25) -> list[dict]:
    """bbox 너비/높이의 median에서 ±tolerance 범위를 벗어나는 bbox 제거.

    퍼즐 셀은 거의 동일 크기 → median 기준으로 이상치 자동 제거.
    그리드 오차나 경계 셀이 비정상 사이즈면 필터됨.
    """
    if len(bboxes) < 5:
        return bboxes
    widths = np.array([b["xmax"] - b["xmin"] for b in bboxes], dtype=np.float64)
    heights = np.array([b["ymax"] - b["ymin"] for b in bboxes], dtype=np.float64)
    med_w = float(np.median(widths))
    med_h = float(np.median(heights))
    if med_w <= 0 or med_h <= 0:
        return bboxes

    keep = []
    for b, w, h in zip(bboxes, widths, heights):
        if (abs(w - med_w) / med_w <= tolerance
                and abs(h - med_h) / med_h <= tolerance):
            keep.append(b)
    return keep


def _indent(elem, level=0):
    i = "\n" + level * "\t"
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "\t"
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = i
    if not elem.tail or not elem.tail.strip():
        elem.tail = i


def save_pascal_voc_xml(
    img_path: Path,
    img_size: tuple[int, int],
    bboxes: list[dict],
    xml_path: Path,
) -> None:
    """PascalVOC XML 저장 (labelImg 호환)."""
    w, h = img_size
    root = ET.Element("annotation")

    ET.SubElement(root, "folder").text = img_path.parent.name
    ET.SubElement(root, "filename").text = img_path.name
    ET.SubElement(root, "path").text = str(img_path)

    src = ET.SubElement(root, "source")
    ET.SubElement(src, "database").text = "Auto-Generated"

    sz = ET.SubElement(root, "size")
    ET.SubElement(sz, "width").text = str(w)
    ET.SubElement(sz, "height").text = str(h)
    ET.SubElement(sz, "depth").text = "3"

    ET.SubElement(root, "segmented").text = "0"

    for bb in bboxes:
        obj = ET.SubElement(root, "object")
        ET.SubElement(obj, "name").text = bb["name"]
        ET.SubElement(obj, "pose").text = "Unspecified"
        ET.SubElement(obj, "truncated").text = "0"
        ET.SubElement(obj, "difficult").text = "0"
        box = ET.SubElement(obj, "bndbox")
        ET.SubElement(box, "xmin").text = str(bb["xmin"])
        ET.SubElement(box, "ymin").text = str(bb["ymin"])
        ET.SubElement(box, "xmax").text = str(bb["xmax"])
        ET.SubElement(box, "ymax").text = str(bb["ymax"])

    _indent(root)
    tree = ET.ElementTree(root)
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(xml_path, encoding="utf-8", xml_declaration=False)


def process_image(
    img_path: Path, profile: dict, out_dir: Path, skip_existing: bool = False,
) -> dict:
    xml_path = out_dir / f"{img_path.stem}.xml"
    if skip_existing and xml_path.exists():
        return {"status": "skip", "xml": str(xml_path)}

    img = cv2.imread(str(img_path))
    if img is None:
        return {"status": "error", "reason": "cannot read image"}

    h, w = img.shape[:2]
    bboxes = generate_bboxes(img, profile)
    save_pascal_voc_xml(img_path, (w, h), bboxes, xml_path)

    return {
        "status": "ok",
        "xml": str(xml_path),
        "bbox_count": len(bboxes),
        "classes": dict(Counter(b["name"] for b in bboxes)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", type=Path, help="단일 이미지")
    ap.add_argument("--dir", type=Path, help="이미지 폴더")
    ap.add_argument("--out", type=Path, default=LABEL_XML_DIR)
    ap.add_argument("--profile", type=Path, default=PROFILE_PATH)
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    profile = load_profile(str(args.profile))
    args.out.mkdir(parents=True, exist_ok=True)

    if args.image:
        images = [args.image]
    elif args.dir:
        images = sorted(
            p for p in args.dir.iterdir()
            if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
        )
        if args.limit:
            images = images[:args.limit]
    else:
        ap.error("--image or --dir required")

    print(f"[input]  {len(images)} images")
    print(f"[output] {args.out}")

    stats: Counter = Counter()
    total_bbox = 0
    all_classes: Counter = Counter()

    for i, img_path in enumerate(images):
        result = process_image(img_path, profile, args.out, args.skip_existing)
        stats[result["status"]] += 1
        if result["status"] == "ok":
            total_bbox += result.get("bbox_count", 0)
            all_classes.update(result.get("classes", {}))
            if (i + 1) % 20 == 0 or i == len(images) - 1:
                print(f"  [{i+1}/{len(images)}] {img_path.name}: {result['bbox_count']} bboxes")

    print()
    print("=== Summary ===")
    print(f"  OK:    {stats['ok']}")
    print(f"  SKIP:  {stats['skip']}")
    print(f"  ERROR: {stats['error']}")
    print(f"  Total bboxes: {total_bbox:,}")
    if stats["ok"] > 0:
        print(f"  Avg/image: {total_bbox / stats['ok']:.0f}")
    print()
    print("=== Classes ===")
    for cname, cnt in all_classes.most_common():
        print(f"  {cname:<22s} {cnt:,}")


if __name__ == "__main__":
    main()
