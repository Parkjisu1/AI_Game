"""Gimmick 모델 동작 검증 — 샘플 이미지 3장 추론 + GT 비교"""
from pathlib import Path
import xml.etree.ElementTree as ET
from ultralytics import YOLO
import cv2

HERE = Path(__file__).resolve().parent
MODEL = HERE / "runs" / "gimmick_detector" / "weights" / "best.pt"
IMG_DIR = HERE / "labeling" / "images_levels"
XML_DIR = HERE / "labeling" / "labels_levels"
OUT_DIR = HERE / "test_gimmick_output"

GIMMICK_NAMES = {
    'hidden gimik', 'pinata gimik', 'snake gimik', 'ice gimik',
    'block gimik', 'wall gimik', 'key gimik', 'door gimik',
    'egg gimik', 'cannon gimik',
}

SAMPLES = ["level_219", "level_267", "level_086"]


def count_gt_gimmicks(xml_path: Path) -> tuple[int, dict]:
    if not xml_path.exists():
        return 0, {}
    root = ET.parse(xml_path).getroot()
    types = {}
    total = 0
    for obj in root.findall("object"):
        name = (obj.find("name").text or "").strip().lower()
        if name in GIMMICK_NAMES:
            types[name] = types.get(name, 0) + 1
            total += 1
    return total, types


def main():
    OUT_DIR.mkdir(exist_ok=True)
    model = YOLO(str(MODEL))
    print(f"Model loaded: {MODEL.name}")
    print(f"Classes: {model.names}\n")

    for name in SAMPLES:
        img_path = IMG_DIR / f"{name}.png"
        xml_path = XML_DIR / f"{name}.xml"
        if not img_path.exists():
            print(f"[SKIP] {name}.png not found")
            continue

        gt_count, gt_types = count_gt_gimmicks(xml_path)

        for conf in [0.25, 0.4, 0.5]:
            results = model.predict(
                source=str(img_path),
                conf=conf,
                save=False,
                verbose=False,
                max_det=1000,
            )
            r = results[0]
            pred_count = len(r.boxes)

            if conf == 0.25:
                annotated = r.plot()
                out_path = OUT_DIR / f"{name}_pred_conf{conf}.png"
                cv2.imwrite(str(out_path), annotated)

            print(f"  {name} @conf={conf}: predicted={pred_count} / GT={gt_count}")

        print(f"    GT types: {gt_types}\n")

    print(f"Visualization saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
