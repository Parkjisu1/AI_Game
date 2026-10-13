#!/bin/bash
# Qdrant 파일 디스크립터 상한 (RocksDB "Too many open files") + 손상된 m3 컬렉션 재생성 + 재임베딩 재시작
set -e
sudo mkdir -p /etc/systemd/system/qdrant.service.d
printf '[Service]\nLimitNOFILE=65536\n' | sudo tee /etc/systemd/system/qdrant.service.d/nofile.conf >/dev/null
sudo systemctl daemon-reload && sudo systemctl restart qdrant
sleep 4
echo "qdrant nofile: $(cat /proc/$(systemctl show qdrant -p MainPID --value)/limits | grep 'open files' | awk '{print $4}')"
curl -s -X DELETE http://127.0.0.1:6343/collections/newplay_code_m3 | jq -c .status
pkill -f "reembed_kb.py --from" 2>/dev/null || true
cd ~/.hermes-newteam/watcher
nohup venv/bin/python reembed_kb.py --from-collection newplay_code --to newplay_code_m3 --batch 8 > ~/.hermes-newteam/logs/reembed.log 2>&1 &
echo "reembed pid=$!"
sleep 60
grep -E "개|완료|실패" ~/.hermes-newteam/logs/reembed.log | tail -2
