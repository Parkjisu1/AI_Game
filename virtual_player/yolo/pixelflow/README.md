# PixelFlow Label Editor + YOLO Training

## 빠른 시작

### Windows
```
1. setup.bat 더블클릭     ← 한 번만
2. run_gui.bat 더블클릭   ← 라벨 편집
3. run_train.bat 더블클릭  ← 학습
```

### Linux/Mac
```bash
chmod +x setup.sh run_gui.sh run_train.sh
./setup.sh
./run_gui.sh
./run_train.sh
```

## 디렉토리 구조 (자동 인식)

이 폴더 어디에 두든 작동. 필수 구조:

```
{어디든}/
├── yolo/pixelflow/         ← 이 폴더 (모든 .py + setup 스크립트)
├── tools/                  ← board_detector, grid_detector 등
└── data/pixelflow/
    ├── profile/cell_profile.json
    └── levels/json/
```

`yolo/pixelflow/`만 옮기면 `_paths.py`가 자동으로 다른 폴더 찾음.

## Python 설치 (없을 때)

### Windows
1. https://www.python.org/downloads/ 접속
2. Python 3.11+ 다운로드
3. 설치 시 **"Add Python to PATH"** 체크
4. setup.bat 실행

### Linux
```bash
sudo apt install python3 python3-pip python3-venv
```

### Mac
```bash
brew install python@3.11
```

## 작업 흐름

```
[새 PC]
  ↓
setup.bat (자동 설치)
  ↓
run_gui.bat → 검수 작업
  ↓
run_train.bat → YOLO 학습
  ↓
runs/levels_v1/weights/best.pt 생성됨
```

## GPU별 batch 권장값 (train_levels.py 수정)

| GPU | VRAM | batch |
|-----|------|-------|
| RTX 3060 Ti | 8GB | 1 |
| RTX 4070 | 12GB | 4 |
| RTX 4080 | 16GB | 8 |
| RTX 4090 | 24GB | 16 |

## 주요 단축키 (label_editor.py)

| 키 | 동작 |
|----|------|
| D / A | 다음 / 이전 이미지 |
| Ctrl+L | 자동 셀 탐지 |
| B | 보드 영역 모드 |
| R | 영역 클래스 변경 |
| E | 영역 삭제 |
| W | 새 bbox 그리기 |
| Ctrl+Z | Undo |
| Ctrl+S | 저장 |

## 트러블슈팅

### setup.bat 안 됨
- Python PATH 추가 안 됐을 가능성. 다시 설치 시 체크박스 확인.

### CUDA 안 됨
- `python -c "import torch; print(torch.cuda.is_available())"` 가 False면
- NVIDIA 드라이버 + CUDA 12.4+ 설치

### CUDA OutOfMemory
- `train_levels.py`의 `batch=` 값 줄임
- `imgsz=1280` 으로 줄임 (1920 → 1280)
