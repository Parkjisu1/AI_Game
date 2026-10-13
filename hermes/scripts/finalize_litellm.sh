#!/bin/bash
set -e

# Watcher .env에 LiteLLM URL/키 추가
cd ~/.hermes/watcher
MK=$(grep LITELLM_MASTER_KEY ~/litellm-env/.env | cut -d= -f2)

grep -v '^LITELLM_URL' .env | grep -v '^LITELLM_MASTER_KEY' > .env.tmp
mv .env.tmp .env
echo "LITELLM_URL=http://localhost:4000" >> .env
echo "LITELLM_MASTER_KEY=$MK" >> .env
chmod 600 .env
echo "✓ watcher .env LiteLLM 설정 추가"

# watcher 재시작
pkill -9 -f projecthub_watcher.py 2>/dev/null || true
sleep 2
bash /tmp/start_watcher.sh
