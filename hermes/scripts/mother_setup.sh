#!/usr/bin/env bash
# Mother 자동 설정 — AIMED에서 scp로 올려 실행
# 포함: Python 의존성 검증 + Mother SSH 키 확인 + .env 준비

set -e

echo "=== Python 의존성 확인 ==="
cd ~/.hermes/watcher
source venv/bin/activate
python3 -c 'import pymongo; import yaml; import bson; print(f"pymongo={pymongo.__version__}, yaml=OK, bson=OK")'

echo ""
echo "=== .env 상태 확인 ==="
if [ -f .env ]; then
  echo ".env 존재 (권한 $(stat -c %a .env))"
  if grep -q "USER:PASS" .env; then
    echo "⚠️  MONGODB_URI가 아직 플레이스홀더 상태 - 나중에 실제 값으로 교체 필요"
  fi
else
  echo "❌ .env 없음"
fi

echo ""
echo "=== Mother SSH 키 (for Mother → Sub/B) ==="
if [ ! -f ~/.ssh/id_ed25519 ]; then
  ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -q -P '' -C mother-to-workers
  echo "키 새로 생성됨"
else
  echo "키 이미 존재"
fi
echo ""
echo "--- 공개키 (Sub와 B에 등록할 값) ---"
cat ~/.ssh/id_ed25519.pub

echo ""
echo "=== 디렉토리 구조 확인 ==="
ls -la ~/.hermes/
echo ""
ls -la ~/.hermes/watcher/ | head -15
echo ""
ls -la ~/.hermes/memories/ | head -5
echo ""
ls -la ~/hermes-config/

echo ""
echo "=== 완료 ==="
