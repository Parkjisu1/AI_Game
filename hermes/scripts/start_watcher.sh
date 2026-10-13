#!/usr/bin/env bash
# Watcher 시작 (Mother에서 실행)

set -e

cd ~/.hermes/watcher
source venv/bin/activate

mkdir -p ~/.hermes/logs

# 기존 프로세스 종료
pkill -f projecthub_watcher.py 2>/dev/null || true
sleep 1

# 완전 detached 실행
(nohup python3 projecthub_watcher.py > ~/.hermes/logs/watcher.log 2>&1 </dev/null &)

# PID 파일 기록
sleep 2
pgrep -f projecthub_watcher.py > ~/.hermes/logs/watcher.pid 2>/dev/null || echo "PID 추적 실패"

echo "=== 시작 후 3초 ==="
sleep 1
if [ -f ~/.hermes/logs/watcher.log ]; then
  echo "--- 로그 (첫 20줄) ---"
  head -20 ~/.hermes/logs/watcher.log
fi
echo "--- 프로세스 ---"
ps aux | grep -v grep | grep projecthub_watcher.py || echo "프로세스 없음"
echo "--- PID 파일 ---"
cat ~/.hermes/logs/watcher.pid 2>/dev/null || echo "PID 없음"
