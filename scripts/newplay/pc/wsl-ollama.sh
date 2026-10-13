#!/bin/bash
# wsl-ollama.sh — 로컬 임베딩용 Ollama + bge-m3 (WSL, newplay 사용자)
set -e
echo "== GPU in WSL"; (nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "no GPU passthrough (CPU 로 동작)")
sudo apt-get install -y -qq zstd bc >/dev/null 2>&1 || true
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh 2>&1 | tail -3
fi
sudo systemctl enable --now ollama >/dev/null 2>&1 || true
sleep 3
ollama pull bge-m3 >/dev/null 2>&1
echo "ollama=$(ollama --version 2>/dev/null | head -1)"
echo "models: $(curl -s http://127.0.0.1:11434/api/tags | jq -r '.models[].name' | tr '\n' ' ')"
# 임베딩 1회 속도
S=$(date +%s.%N); D=$(curl -s http://127.0.0.1:11434/api/embeddings -d '{"model":"bge-m3","prompt":"결제 승인 orderId 불일치 처리"}' | jq '.embedding | length'); E=$(date +%s.%N)
echo "bge-m3 dim=$D  latency=$(echo "$E - $S" | bc | cut -c1-5)s"
echo OLLAMA_OK
