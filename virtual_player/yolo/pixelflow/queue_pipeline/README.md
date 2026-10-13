# Queue Extraction Pipeline

Extracts queue/holder info per game level from gameplay click screenshots.
Final output: per-level JSON with cells + gimmicks + queue combined.

## Overview

```
Stage 1 (OCR level detection)
  click_*.png  ->  level_to_images.json
                   (which image belongs to which game level)

Stage 2a (representative selector)
  level_to_images.json  ->  level_to_representative.json
                            (one image per level)

Stage 2b (prepare labeling)
  level_to_representative.json + source click folder
    -> copies ~50 images to labeling/images_queue/

[USER] Manually label holders via label_editor.py

Stage 2c (train holder YOLO)
  labels_queue/*.xml  ->  runs/holder_detector/best.pt

Stage 2d (queue extraction)
  Representatives + holder_detector + EasyOCR
    -> queue_by_level.json (holders with color + count)

Stage 3 (merge)
  batch_all_levels_run/levels/ + queue_by_level.json
    -> final_levels/level_XXX.json  (all data per level)
```

## Prerequisites on 3080 Ti

Python packages:
```
pip install ultralytics easyocr opencv-python numpy
```

Also need:
- `label_editor.py` (PySide6 GUI, already set up in pixelflow_transfer_core)
- GPU with CUDA

## Run Order

### Step 0 (already done on current PC)
- Stage 1: `queue_stage1_ocr_levels.py` produced `level_to_images.json`
  (transfer this to 3080 Ti)

### Step 1: Pick representative images
```
python stage2a_select_representatives.py \
  --input level_to_images.json \
  --output level_to_representative.json
```

### Step 2: Copy sample images for labeling
```
python stage2b_prepare_labeling.py \
  --input level_to_representative.json \
  --source D:\LevelDesignExtractor\pixelflow \
  --output labeling/images_queue \
  --sample 50
```

### Step 3 [USER TASK]: Label holders
Open label editor:
```
python label_editor.py \
  --dir labeling/images_queue \
  --labels labeling/labels_queue
```

For each image, draw bbox around:
- Every holder on the rail
- Current balloon at bottom center (optional, use `current_balloon` class)
- Empty queue slots at bottom are NOT labeled (no content)

Class name: `holder` (single class) OR `holder` + `current_balloon`

### Step 4: Train YOLO
```
python stage2c_train_holder.py \
  --images labeling/images_queue \
  --labels labeling/labels_queue \
  --output-dataset dataset_holder \
  --runs-dir runs \
  --epochs 150 --imgsz 1280 --batch 4 \
  --single-class
```

Output: `runs/holder_detector/weights/best.pt`

### Step 5: Extract queue for all levels
```
python stage2d_extract_queue.py \
  --representatives level_to_representative.json \
  --source D:\LevelDesignExtractor\pixelflow \
  --weights runs/holder_detector/weights/best.pt \
  --palette data/pixelflow/profile/cell_profile.json \
  --output queue_by_level.json
```

### Step 6: Merge with existing cell/gimmick data
```
python stage3_merge.py \
  --cells-dir path/to/batch_all_levels_run/levels \
  --queue queue_by_level.json \
  --output final_levels
```

### Step 7 (optional): Convert to BalloonFlow format
Use existing `pixelflow_to_balloonflow.py` (will need minor update to read
queue from `final_levels/` instead of `export_1_300/`).

## File Transfer Checklist

From current PC to 3080 Ti:
- [ ] This whole `queue_pipeline/` folder
- [ ] `queue_stage1_out/level_to_images.json` (Stage 1 output)
- [ ] `batch_all_levels_run/levels/` (for Stage 3 merge)
- [ ] `data/pixelflow/profile/cell_profile.json` (for color palette)
- [ ] `label_editor.py` (if not already on 3080 Ti)

From 3080 Ti back to current PC (after all done):
- [ ] `runs/holder_detector/weights/best.pt` (trained model)
- [ ] `queue_by_level.json` (extracted queue data)
- [ ] `final_levels/` (merged per-level JSONs)

## Expected Timeline

| Step | Time | Notes |
|------|------|-------|
| 1 (select) | 1 min | auto |
| 2 (prepare) | 2 min | auto |
| 3 (label) | 1-2 h | USER manual |
| 4 (train) | 30 min | 3080 Ti |
| 5 (extract) | 30 min | depends on level count |
| 6 (merge) | 5 min | auto |
| TOTAL | ~3-4 h | |
