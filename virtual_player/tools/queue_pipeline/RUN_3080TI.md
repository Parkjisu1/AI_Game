# 3080 Ti에서 실행 가이드 (Queue 전량 추출)

## 준비 (외장하드에 이미 포함됨)

외장하드 F:\에 이미 모든 필요 파일 있음:
- `F:\LevelDesignExtractor\pixelflow\` — 원본 이미지 (50,518장)
- `F:\queue_pipeline_raw\` 또는 `F:\runs\holder_detector\weights\best.pt`
- `E:\AI\virtual_player\tools\queue_pipeline\` (본 PC에 있음, 외장하드로 복사 필요)

## 외장하드 추가 복사 (본 PC → F:\)

```cmd
xcopy /E /I /Y E:\AI\virtual_player\tools\queue_pipeline F:\queue_pipeline_v2
```

## 3080 Ti PC에서 실행

외장하드 F:를 3080 Ti PC에 연결 후 (드라이브 레터 확인 필요, 여기서는 F:라 가정):

### 1. 환경 확인
```cmd
cd /d F:\queue_pipeline_v2
python -c "import ultralytics; print(ultralytics.__version__)"
```

ultralytics 없으면:
```cmd
pip install ultralytics
```

### 2. Stage 2d-all 실행 (holder inference)

```cmd
python stage2d_all.py ^
    --images-dir F:\LevelDesignExtractor\pixelflow ^
    --level-mapping F:\queue_pipeline_v2\stage1_out\level_to_images.json ^
    --weights F:\runs\holder_detector\weights\best.pt ^
    --output F:\queue_pipeline_v2\queue_all_observations.jsonl ^
    --batch 16 ^
    --imgsz 1280 ^
    --conf 0.25 ^
    --resume
```

**예상 시간**: 3080 Ti / batch=16 / imgsz=1280 / 42,850장 → **45분~1시간**

진행 로그는 10 배치마다 출력됩니다:
```
  160/42850 (0.4%)  rate=23.4 img/s  ETA=30.5m  missing=0  err=0
  320/42850 (0.7%)  rate=24.1 img/s  ETA=29.4m  missing=0  err=0
  ...
```

`--resume` 플래그로 중단 시 재개 가능 (이미 처리된 filename은 skip).

### 3. Stage 3 집계 (Queue 시퀀스 복원)

```cmd
python stage3_timeseries.py ^
    --observations F:\queue_pipeline_v2\queue_all_observations.jsonl ^
    --output F:\queue_pipeline_v2\queue_full_per_level.json ^
    --position-tolerance 40 ^
    --min-conf 0.3
```

**예상 시간**: 10~30분 (CPU 집약, GPU 불필요)

## 결과 가져오기

외장하드에서 본 PC로:
```cmd
copy F:\queue_pipeline_v2\queue_all_observations.jsonl E:\AI\virtual_player\tools\queue_pipeline\
copy F:\queue_pipeline_v2\queue_full_per_level.json E:\AI\virtual_player\data\pixelflow\levels\
```

## 결과 검증 포인트

`queue_full_per_level.json`의 summary 확인:
```json
{
  "summary": {
    "total_levels": 296,
    "recovery_distribution": {"A": 280, "B": 10, "C": 5, "F": 1},
    "total_queue_entries": 5000+
  }
}
```

A급 레벨(관찰 100+) 수가 280 근처면 성공.

## 트러블슈팅

- **CUDA out of memory**: `--batch 8` 또는 `--imgsz 960`로 낮춤
- **실행 중 크래시**: `--resume` 추가하여 재실행
- **특정 파일 missing**: 원본 이미지가 external drive에 없음 — `missing` 카운트 확인
- **processing 느림**: `--device cuda:0` 명시적 지정
