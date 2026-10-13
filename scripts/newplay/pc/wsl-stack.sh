#!/bin/bash
# wsl-stack.sh — NewPlay 전용 서버 스택 설치 (newplay 사용자, sudo NOPASSWD)
#   node 20(nvm) · MongoDB 8(system, :27018, rs0) · Qdrant(system, :6343) · Claude Code CLI
set -e
export DEBIAN_FRONTEND=noninteractive
cd ~

# ── node 20 via nvm
if [ ! -d ~/.nvm ]; then
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash >/dev/null
fi
. ~/.nvm/nvm.sh
nvm install 20 >/dev/null
nvm alias default 20 >/dev/null
echo "node=$(node --version) npm=$(npm --version)"

# ── MongoDB 8 (apt repo)
if ! command -v mongod >/dev/null; then
  curl -fsSL https://www.mongodb.org/static/pgp/server-8.0.asc | sudo gpg -o /usr/share/keyrings/mongodb-server-8.0.gpg --dearmor --yes
  echo "deb [ arch=amd64 signed-by=/usr/share/keyrings/mongodb-server-8.0.gpg ] https://repo.mongodb.org/apt/ubuntu noble/mongodb-org/8.0 multiverse" \
    | sudo tee /etc/apt/sources.list.d/mongodb-org-8.0.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq mongodb-org >/dev/null
fi
sudo tee /etc/mongod.conf >/dev/null <<'EOC'
storage:
  dbPath: /var/lib/mongodb
systemLog:
  destination: file
  logAppend: true
  path: /var/log/mongodb/mongod.log
net:
  port: 27018
  bindIp: 127.0.0.1
replication:
  replSetName: rs0
EOC
sudo systemctl enable --now mongod
sleep 3
# 단일노드 복제셋 — 워처의 change stream 이 이것을 요구한다
mongosh --quiet --port 27018 --eval 'try { rs.status().ok } catch(e) { rs.initiate({_id:"rs0", members:[{_id:0, host:"127.0.0.1:27018"}]}).ok }' || true
sleep 2
echo "mongod=$(mongod --version | head -1) rs=$(mongosh --quiet --port 27018 --eval 'rs.status().set + "/" + rs.status().members[0].stateStr')"

# ── Qdrant (GitHub 릴리스 바이너리, system 서비스, :6343)
if [ ! -x /opt/qdrant/qdrant ]; then
  QV=$(curl -fsSL https://api.github.com/repos/qdrant/qdrant/releases/latest | jq -r .tag_name)
  curl -fsSL -o /tmp/qdrant.tgz "https://github.com/qdrant/qdrant/releases/download/${QV}/qdrant-x86_64-unknown-linux-gnu.tar.gz"
  sudo mkdir -p /opt/qdrant /var/lib/qdrant
  sudo tar -xzf /tmp/qdrant.tgz -C /opt/qdrant
  sudo chown -R newplay:newplay /var/lib/qdrant
fi
sudo tee /etc/qdrant.yaml >/dev/null <<'EOC'
storage:
  storage_path: /var/lib/qdrant/storage
  snapshots_path: /var/lib/qdrant/snapshots
service:
  host: 127.0.0.1
  http_port: 6343
  grpc_port: 6344
EOC
sudo tee /etc/systemd/system/qdrant.service >/dev/null <<'EOC'
[Unit]
Description=Qdrant vector DB (NewPlay)
After=network.target
[Service]
User=newplay
ExecStart=/opt/qdrant/qdrant --config-path /etc/qdrant.yaml
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOC
sudo systemctl daemon-reload
sudo systemctl enable --now qdrant
sleep 3
echo "qdrant=$(curl -s http://127.0.0.1:6343/ | jq -r .version)"

# ── Claude Code CLI
npm i -g @anthropic-ai/claude-code >/dev/null 2>&1 || true
echo "claude=$(claude --version 2>/dev/null | head -1)"

echo STACK_OK
