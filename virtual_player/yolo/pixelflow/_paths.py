"""
프로젝트 경로 자동 탐지

이 파일을 import하면 어느 PC/드라이브에서도 정상 작동.
모든 다른 스크립트가 이 모듈을 import해서 경로 사용.
"""
from pathlib import Path

# 이 파일 = yolo/pixelflow/_paths.py
PIXELFLOW_DIR = Path(__file__).resolve().parent

# 상위 경로 (자동 탐지)
# pixelflow/ → yolo/ → virtual_player/
VIRTUAL_PLAYER_DIR = PIXELFLOW_DIR.parent.parent

# 주요 폴더
LABELING_DIR = PIXELFLOW_DIR / "labeling"
DATASET_DIR = PIXELFLOW_DIR / "dataset_levels"
RUNS_DIR = PIXELFLOW_DIR / "runs"

# Tools / Data (virtual_player 하위)
TOOLS_DIR = VIRTUAL_PLAYER_DIR / "tools"
DATA_DIR = VIRTUAL_PLAYER_DIR / "data" / "pixelflow"
PROFILE_PATH = DATA_DIR / "profile" / "cell_profile.json"
LEVELS_JSON_DIR = DATA_DIR / "levels" / "json"

# Labeling 하위
LABEL_IMAGES_DIR = LABELING_DIR / "images_levels"
LABEL_XML_DIR = LABELING_DIR / "labels_levels"
CLASSES_FILE = LABEL_XML_DIR / "classes.txt"
BOARD_REGIONS_FILE = LABELING_DIR / "board_regions.json"

# 모델 weights (학습 후 생성)
BOARD_DETECTOR_WEIGHTS = RUNS_DIR / "board_detector" / "weights" / "best.pt"
GIMMICK_DETECTOR_WEIGHTS = RUNS_DIR / "auto_v1" / "weights" / "best.pt"
LEVELS_MODEL_WEIGHTS = RUNS_DIR / "levels_v1" / "weights" / "best.pt"
BASE_MODEL = PIXELFLOW_DIR / "yolo26n.pt"


def add_tools_to_path():
    """tools 폴더를 sys.path에 추가."""
    import sys
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))


if __name__ == "__main__":
    print(f"PIXELFLOW_DIR:        {PIXELFLOW_DIR}")
    print(f"VIRTUAL_PLAYER_DIR:   {VIRTUAL_PLAYER_DIR}")
    print(f"LABELING_DIR:         {LABELING_DIR}")
    print(f"TOOLS_DIR:            {TOOLS_DIR}")
    print(f"DATA_DIR:             {DATA_DIR}")
    print(f"PROFILE_PATH:         {PROFILE_PATH}  (exists: {PROFILE_PATH.exists()})")
    print(f"BASE_MODEL:           {BASE_MODEL}  (exists: {BASE_MODEL.exists()})")
