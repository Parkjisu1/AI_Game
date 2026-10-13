#!/bin/bash
# wsl-init.sh — NewPlay 전용 WSL2 우분투 1회 초기화 (root 로 실행)
set -e
export DEBIAN_FRONTEND=noninteractive

# 1) 사용자
if ! id newplay >/dev/null 2>&1; then
  useradd -m -s /bin/bash -G sudo newplay
  echo 'newplay ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/newplay
  chmod 440 /etc/sudoers.d/newplay
fi

# 2) systemd + 기본 사용자
cat > /etc/wsl.conf <<'EOC'
[boot]
systemd=true
[user]
default=newplay
[network]
generateResolvConf=true
EOC

# 3) 패키지
apt-get update -qq
apt-get install -y -qq git curl wget build-essential python3 python3-venv python3-pip ca-certificates gnupg unzip jq >/dev/null

# 4) 재부팅 후에도 사용자 서비스가 살아 있게
mkdir -p /var/lib/systemd/linger
touch /var/lib/systemd/linger/newplay

echo "INIT_OK user=$(id newplay) ubuntu=$(. /etc/os-release && echo $VERSION_ID)"
