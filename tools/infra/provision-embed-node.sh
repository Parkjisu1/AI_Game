#!/usr/bin/env bash
# provision-embed-node.sh — 신규 임베딩 노드 기본 프로비저닝 (새 팀 전용)
#
# 대상: Ubuntu 24.04 LTS (Mother `aimed` / Sub `aimed-sub`와 동일 베이스라인)
# 실행: 새 장비에 SSH가 열린 직후, 워크스테이션에서
#         scp provision-embed-node.sh <user>@<ip>:~/ && ssh <user>@<ip> 'bash ~/provision-embed-node.sh'
#
# 멱등(idempotent) — 여러 번 실행해도 안전하다. 이미 된 단계는 건너뛴다.
#
# 이 스크립트가 하는 것 = "팀 무관 공통 기반"까지만.
#   · Node 20 / Python venv / Qdrant / systemd --user / 방화벽
# 팀별 임베딩 워커·ProjectHub 인스턴스는 그분들 스택·리포를 안 뒤 별도 배치한다.

set -euo pipefail

log() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*"; }

# ──────────────────────────────────────────────────────────
# 0. 전제 확인
# ──────────────────────────────────────────────────────────
log "전제 확인"
. /etc/os-release
[ "${ID:-}" = "ubuntu" ] || { echo "Ubuntu 전용 스크립트다 (감지: ${ID:-unknown})"; exit 1; }
case "${VERSION_ID:-}" in
  24.04) : ;;
  *) warn "Ubuntu ${VERSION_ID} — 기준(24.04)과 다르다. 계속하되 차이를 유의할 것." ;;
esac
[ "$(id -u)" -ne 0 ] || { echo "root 말고 일반 사용자로 실행할 것 (systemd --user 를 쓴다)"; exit 1; }
sudo -n true 2>/dev/null || echo "(sudo 비밀번호를 한 번 물을 수 있다)"

echo "user=$(whoami) host=$(hostname) kernel=$(uname -r)"
echo "cpu=$(nproc)core mem=$(free -g | awk '/^Mem:/{print $2}')GB"
lsblk -d -o NAME,SIZE | tail -n +2 | sed 's/^/disk: /'
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | sed 's/^/gpu: /'
else
  warn "GPU 드라이버 없음 — 로컬 임베딩 모델을 쓰려면 nvidia-driver 설치 필요"
fi

# ──────────────────────────────────────────────────────────
# 1. systemd --user 지속화
#    이게 없으면 SSH 로그아웃 시 user 서비스가 전부 죽는다.
#    Mother/Sub의 서비스가 84일 연속 살아있는 이유가 이것.
# ──────────────────────────────────────────────────────────
log "systemd --user linger 활성화"
sudo loginctl enable-linger "$(whoami)"
loginctl show-user "$(whoami)" -p Linger

# ──────────────────────────────────────────────────────────
# 2. 기본 패키지
# ──────────────────────────────────────────────────────────
log "apt 패키지"
sudo apt-get update -qq
sudo apt-get install -y -qq \
  build-essential git curl wget unzip jq \
  python3-venv python3-pip python3-dev \
  ufw ca-certificates

# ──────────────────────────────────────────────────────────
# 3. Node 20 (nvm) — Mother와 동일 버전
#    ⚠️ 배포 함정: 비로그인 SSH 셸의 기본 node는 apt판(구버전)이라
#       Next.js 빌드가 ">=20.9.0 required"로 죽는다. 원격 빌드 시
#       반드시 PATH를 선지정할 것 (아래 안내 참조).
# ──────────────────────────────────────────────────────────
NODE_VER="v20.20.2"
log "Node ${NODE_VER} (nvm)"
if [ ! -d "$HOME/.nvm" ]; then
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
fi
export NVM_DIR="$HOME/.nvm"
# shellcheck disable=SC1091
. "$NVM_DIR/nvm.sh"
nvm install "$NODE_VER" >/dev/null
nvm alias default "$NODE_VER" >/dev/null
echo "node=$(node -v) npm=$(npm -v)"
echo "원격 빌드 시 PATH: export PATH=$HOME/.nvm/versions/node/${NODE_VER}/bin:\$PATH"

# ──────────────────────────────────────────────────────────
# 4. Python venv (임베딩 워커용)
# ──────────────────────────────────────────────────────────
log "Python venv"
mkdir -p "$HOME/.embedworker"
if [ ! -d "$HOME/.embedworker/venv" ]; then
  python3 -m venv "$HOME/.embedworker/venv"
fi
"$HOME/.embedworker/venv/bin/pip" install -q --upgrade pip
"$HOME/.embedworker/venv/bin/pip" install -q \
  qdrant-client openai python-dotenv pymongo requests
echo "venv=$($HOME/.embedworker/venv/bin/python --version)"

# ──────────────────────────────────────────────────────────
# 5. Qdrant (새 팀 전용 벡터DB)
#    Sub(aimed-sub)의 검증된 구성을 따르되 두 가지를 고친다:
#      (a) LimitNOFILE=65535 — Sub는 기본 1024가 소진돼 accept()/RocksDB flush가
#          전면 실패한 이력이 있다 (2026-07-20). 처음부터 넣는다.
#      (b) 127.0.0.1 바인딩 — Sub는 0.0.0.0 + API키 없음이라 사내망(172.31.x)
#          누구나 읽고 쓸 수 있다. 여기는 루프백만 열고 SSH 터널로 접근한다.
# ──────────────────────────────────────────────────────────
QDRANT_VER="v1.12.0"
log "Qdrant ${QDRANT_VER}"
mkdir -p "$HOME/qdrant" "$HOME/.qdrant/storage" "$HOME/.qdrant/snapshots"
if [ ! -x "$HOME/qdrant/qdrant" ]; then
  tmp=$(mktemp -d)
  wget -qO "$tmp/q.tar.gz" \
    "https://github.com/qdrant/qdrant/releases/download/${QDRANT_VER}/qdrant-x86_64-unknown-linux-gnu.tar.gz"
  tar -xzf "$tmp/q.tar.gz" -C "$HOME/qdrant"
  rm -rf "$tmp"
fi
chmod +x "$HOME/qdrant/qdrant"

mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/qdrant.service" <<EOF
[Unit]
Description=Qdrant Vector DB (new-team embedding store)
After=network.target

[Service]
Type=simple
WorkingDirectory=${HOME}/qdrant
Environment=QDRANT__STORAGE__STORAGE_PATH=${HOME}/.qdrant/storage
Environment=QDRANT__STORAGE__SNAPSHOTS_PATH=${HOME}/.qdrant/snapshots
# 루프백만 — 외부 접근은 SSH 터널 경유. (Sub의 0.0.0.0 + 무인증 노출을 되풀이하지 않는다)
Environment=QDRANT__SERVICE__HOST=127.0.0.1
ExecStart=${HOME}/qdrant/qdrant
# FD 고갈로 accept()/RocksDB flush가 전면 실패했던 이력 (Sub, 2026-07-20). 기본 soft 1024는 부족하다.
LimitNOFILE=65535
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now qdrant.service
sleep 2
systemctl --user is-active qdrant.service
curl -s localhost:6333/ | head -c 200; echo

# ──────────────────────────────────────────────────────────
# 6. 방화벽 — 사내망(172.31.x)에 열지 않는다. 접근은 Tailscale/SSH 터널만.
# ──────────────────────────────────────────────────────────
log "ufw"
sudo ufw --force reset >/dev/null
sudo ufw default deny incoming >/dev/null
sudo ufw default allow outgoing >/dev/null
sudo ufw allow in on tailscale0 >/dev/null 2>&1 || warn "tailscale0 인터페이스 없음 — Tailscale 가입 후 'sudo ufw allow in on tailscale0' 재실행"
sudo ufw allow 22/tcp >/dev/null   # LAN SSH — Tailscale 안정화 후 제거 권장
sudo ufw --force enable >/dev/null
sudo ufw status verbose | head -12

# ──────────────────────────────────────────────────────────
# 7. 마무리 안내
# ──────────────────────────────────────────────────────────
log "완료"
cat <<'DONE'
기반 구성 끝. 남은 단계:

  1) Tailscale 가입 (아직이면)
       curl -fsSL https://tailscale.com/install.sh | sh
       sudo tailscale up --hostname=<정한이름> --ssh
     → 출력되는 URL을 브라우저에서 열어 기존 계정으로 승인
     → 가입 후: sudo ufw allow in on tailscale0

  2) Mother에서 이 노드로 오는 키 등록 (Mother가 워커를 조율할 경우)
       ~/.ssh/authorized_keys 에 Mother 공개키 추가

  3) 팀별 구성 — 그분들 스택/리포를 안 뒤 진행
       · 임베딩 워커 (delta_embed 패턴 일반화)
       · 새 팀 전용 ProjectHub 인스턴스
       · Qdrant 컬렉션 설계 (게임 코퍼스와 물리 분리)

점검 명령:
  systemctl --user status qdrant.service
  curl -s localhost:6333/collections | jq
  loginctl show-user $(whoami) -p Linger    # Linger=yes 여야 함
DONE
