# PixelFlow 작업 새 PC 이전 가이드

## 1. 폴더 복사

원본 PC에서 새 PC로 다음 폴더 복사:

```
E:\AI\virtual_player\
  ├── yolo\pixelflow\
  │   ├── *.py
  │   ├── labeling\
  │   │   ├── images_levels\          ← 250장
  │   │   ├── labels_levels\          ← 검수된 XML
  │   │   └── board_regions.json
  │   ├── dataset_levels\             ← 학습 데이터셋
  │   ├── runs\board_detector\        ← 보드 모델
  │   ├── runs\auto_v1\               ← 셀+기믹 모델
  │   ├── yolo26n.pt                  ← 베이스 모델
  │   └── requirements.txt
  ├── tools\
  │   ├── board_detector.py
  │   ├── grid_detector.py
  │   ├── cell_aware_analyzer.py
  │   └── hybrid_extractor.py
  └── data\pixelflow\
      ├── profile\
      └── levels\json\
```

경로는 새 PC에서도 같게 유지하면 (`E:\AI\virtual_player\...`) 코드 수정 불필요.
다른 경로 사용 시: 각 .py 파일 상단의 경로 상수만 수정.

## 2. Python 환경 설정

```bash
# Python 3.11+ 설치 후
cd E:\AI\virtual_player\yolo\pixelflow
pip install -r requirements.txt
```

## 3. CUDA 확인

```bash
python -c "import torch; print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0))"
```

GPU 인식 안 되면 NVIDIA 드라이버 + CUDA 12.4+ 설치.

## 4. GUI 실행 테스트

```bash
python label_editor.py --dir labeling/images_levels --labels labeling/labels_levels
```

## 5. 학습 실행

새 GPU 메모리에 맞춰 `train_levels.py`의 batch 조정:

```python
batch=2   # 8GB GPU
batch=4   # 12GB GPU
batch=8   # 16GB GPU
batch=16  # 24GB+ GPU (A100, 4090 등)
imgsz=1920  # 권장 (변경 X)
```

```bash
python train_levels.py
```

## 6. 추가 라벨링 진행

GUI에서 검수 계속:
- D/A: 다음/이전 이미지
- Ctrl+L: 자동 탐지
- B: 보드 영역 설정
- R: 영역 클래스 변경
- E: 영역 삭제

추가 라벨 후 재학습:
```bash
python labels_levels_to_yolo.py --max-level 250  # 검수 범위에 맞춰 조정
python train_levels.py
```

## 7. 학습 결과 확인

```
runs/levels_v1/
  ├── weights/best.pt     ← 학습된 모델
  ├── results.png         ← 학습 그래프
  ├── confusion_matrix.png
  └── results.csv
```

## GPU별 권장 배치 / 학습 시간

| GPU | VRAM | batch | 1 epoch | 100 epochs |
|-----|------|-------|---------|------------|
| RTX 3060 Ti | 8GB | 1 | ~2분 | ~3시간 |
| RTX 4070 | 12GB | 4 | ~1분 | ~1.5시간 |
| RTX 4080 | 16GB | 8 | ~30초 | ~50분 |
| RTX 4090 | 24GB | 16 | ~20초 | ~30분 |
| A100 | 40GB | 32 | ~10초 | ~15분 |

## 트러블슈팅

### CUDA OutOfMemory
- batch 줄임 (2 → 1)
- imgsz 줄임 (1920 → 1280)

### PySide6 GUI 안 뜸
- pythonw.exe로 실행 (Windows)
- 또는 Linux/Mac은 그냥 python

### 경로 에러
- 모든 .py 파일 상단의 BASE 경로 확인
- `E:\AI\...` → 새 경로로 변경

## 핵심 파일 체크리스트

- [ ] yolo/pixelflow/*.py (모든 스크립트)
- [ ] yolo/pixelflow/labeling/labels_levels/*.xml (검수 라벨)
- [ ] yolo/pixelflow/labeling/images_levels/*.png (250장)
- [ ] yolo/pixelflow/yolo26n.pt (베이스 모델)
- [ ] yolo/pixelflow/runs/ (학습 모델)
- [ ] tools/*.py (탐지 모듈)
- [ ] data/pixelflow/profile/cell_profile.json (팔레트)
- [ ] data/pixelflow/levels/json/*.json (레벨 메타)
