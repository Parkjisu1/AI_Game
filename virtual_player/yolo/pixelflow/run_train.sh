#!/usr/bin/env bash
cd "$(dirname "$0")"
source venv/bin/activate
python labels_levels_to_yolo.py "$@"
python train_levels.py
