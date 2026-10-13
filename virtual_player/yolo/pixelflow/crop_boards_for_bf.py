"""BalloonFlow용 PNG 크롭.

전체 게임 화면(1080x1920)에서 **보드 영역만 잘라서** 저장.
BF 임포터가 pixel_art_source를 읽을 때 UI/큐 영역이 풍선으로 오인되는 것 방지.

입력: balloonflow_autogen/json/level_XXX.png (원본 전체 화면)
출력: 같은 경로에 덮어쓰기 (크롭된 버전)
     + balloonflow_autogen/json/_crop_log.csv (크롭 결과 로그)
"""
from __future__ import annotations
import sys
from pathlib import Path
import csv

import cv2
from ultralytics import YOLO

HERE = Path(__file__).resolve().parent
JSON_DIR = HERE / "balloonflow_autogen" / "json"
BACKUP_DIR = HERE / "balloonflow_autogen" / "json_original_full"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

BOARD_WEIGHTS = HERE / "runs" / "board_detector" / "weights" / "best.pt"

def main():
    if not BOARD_WEIGHTS.exists():
        print(f"ERROR: {BOARD_WEIGHTS} 없음")
        sys.exit(1)

    print(f"Loading board_detector: {BOARD_WEIGHTS}")
    model = YOLO(str(BOARD_WEIGHTS))

    pngs = sorted(JSON_DIR.glob("level_*.png"))
    print(f"Processing {len(pngs)} images...")

    log_rows = []
    success, fail = 0, 0

    for i, png in enumerate(pngs, 1):
        try:
            img = cv2.imread(str(png))
            if img is None:
                fail += 1
                log_rows.append([png.name, "ERROR", "imread failed", "", ""])
                continue
            h, w = img.shape[:2]

            # 원본 백업 (최초 1회만)
            backup = BACKUP_DIR / png.name
            if not backup.exists():
                cv2.imwrite(str(backup), img)

            # 보드 탐지
            results = model(img, verbose=False, conf=0.25, imgsz=1920)
            boxes = results[0].boxes
            if len(boxes) == 0:
                fail += 1
                log_rows.append([png.name, "SKIP", "no board detected", f"{w}x{h}", ""])
                # 원본 유지 (크롭 안 함)
                continue

            # 가장 큰 bbox (보드가 가장 큰 영역)
            best_box = None
            best_area = 0
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()
                area = (x2 - x1) * (y2 - y1)
                if area > best_area:
                    best_area = area
                    best_box = (int(x1), int(y1), int(x2), int(y2))

            if best_box is None:
                fail += 1
                log_rows.append([png.name, "SKIP", "no valid box", f"{w}x{h}", ""])
                continue

            x1, y1, x2, y2 = best_box
            # 약간의 여백 추가 (bbox 경계가 셀 일부 자를 수 있음)
            pad = 5
            x1 = max(0, x1 - pad)
            y1 = max(0, y1 - pad)
            x2 = min(w, x2 + pad)
            y2 = min(h, y2 + pad)

            cropped = img[y1:y2, x1:x2]
            cv2.imwrite(str(png), cropped)
            success += 1
            log_rows.append([
                png.name, "OK",
                f"{x2-x1}x{y2-y1}",
                f"{w}x{h}",
                f"({x1},{y1})-({x2},{y2})",
            ])

            if i % 30 == 0:
                print(f"  [{i}/{len(pngs)}] {png.name} -> {x2-x1}x{y2-y1}")

        except Exception as ex:
            fail += 1
            log_rows.append([png.name, "ERROR", str(ex)[:50], "", ""])

    # 로그 저장
    log_path = JSON_DIR / "_crop_log.csv"
    with log_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["filename", "status", "cropped_size", "original_size", "bbox"])
        w.writerows(log_rows)

    print(f"\n=== 완료 ===")
    print(f"성공: {success} / 실패: {fail}")
    print(f"백업: {BACKUP_DIR}")
    print(f"로그: {log_path}")


if __name__ == "__main__":
    main()
