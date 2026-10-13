#!/usr/bin/env bash
# PixelFlow 자동 설치 (Linux/Mac)
set -e

cd "$(dirname "$0")"

echo "=== PixelFlow Setup ==="

echo "[1/4] Python 확인..."
if ! command -v python3 >/dev/null; then
    echo "Python 3 미설치. 설치 후 재실행."
    exit 1
fi
python3 --version

echo "[2/4] 가상환경..."
if [ ! -d venv ]; then
    python3 -m venv venv
fi
source venv/bin/activate

echo "[3/4] 의존성 설치..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[4/4] CUDA 확인..."
python -c "import torch; print('CUDA:', torch.cuda.is_available())"

echo "=== Setup 완료 ==="
echo "GUI:    ./run_gui.sh"
echo "Train:  ./run_train.sh"
