#!/usr/bin/env bash
#
# deploy-to-mother.sh
#
# 자리 PC 또는 Git Bash에서 실행.
# E:\AI\hermes\의 watcher/skills/config/systemd를 Mother로 배포 + 의존성 설치.
#
# 사용:
#   bash deploy-to-mother.sh
#
# 전제:
#   - Mother(100.77.190.68)에 SSH 키 인증 설정됨
#   - Mother의 ~/.hermes/memories/는 별도 rsync로 동기화 중
#   - Python 3.12 + pip 설치됨 (Mother 셋업 시 설치함)

set -euo pipefail

MOTHER_HOST="${MOTHER_HOST:-aimed@100.77.190.68}"
LOCAL_ROOT="${LOCAL_ROOT:-/e/AI/hermes}"

echo "==> Deploying from $LOCAL_ROOT to $MOTHER_HOST"

# 1. watcher 코드
echo "==> Syncing watcher/..."
ssh "$MOTHER_HOST" "mkdir -p ~/.hermes/watcher"
rsync -avz --exclude 'venv' --exclude '__pycache__' --exclude '.env' \
  "$LOCAL_ROOT/watcher/" "$MOTHER_HOST:~/.hermes/watcher/"

# 2. skills (있다면)
if [ -d "$LOCAL_ROOT/skills" ]; then
  echo "==> Syncing skills/..."
  ssh "$MOTHER_HOST" "mkdir -p ~/.hermes/skills"
  rsync -avz "$LOCAL_ROOT/skills/" "$MOTHER_HOST:~/.hermes/skills/"
fi

# 3. config
echo "==> Syncing config/..."
ssh "$MOTHER_HOST" "mkdir -p ~/hermes-config"
rsync -avz "$LOCAL_ROOT/config/" "$MOTHER_HOST:~/hermes-config/"

# 4. systemd unit files (수동 sudo cp 가이드만)
echo "==> systemd unit files (manual deploy):"
echo "   SCP하고 sudo로 옮기세요:"
echo "   scp $LOCAL_ROOT/systemd/*.service $MOTHER_HOST:/tmp/"
echo "   ssh $MOTHER_HOST 'sudo cp /tmp/*.service /etc/systemd/system/ && sudo systemctl daemon-reload'"

# 5. 의존성 설치 (watcher)
echo "==> Installing watcher dependencies on Mother..."
ssh "$MOTHER_HOST" bash <<'EOF'
cd ~/.hermes/watcher
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "Dependencies installed."

# .env 없으면 .env.example 복사 (사용자가 실값 기입)
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo ""
  echo "⚠️  ~/.hermes/watcher/.env 파일이 생성됐습니다."
  echo "   MONGODB_URI 등 실제 값을 기입하세요."
fi
EOF

echo ""
echo "✅ 배포 완료"
echo ""
echo "다음 단계:"
echo "  1. Mother SSH: ssh $MOTHER_HOST"
echo "  2. .env 편집:   nano ~/.hermes/watcher/.env"
echo "  3. 테스트 실행: cd ~/.hermes/watcher && source venv/bin/activate && python projecthub_watcher.py"
echo "  4. systemd 등록: sudo cp /tmp/*.service /etc/systemd/system/ && sudo systemctl enable --now projecthub-watcher"
