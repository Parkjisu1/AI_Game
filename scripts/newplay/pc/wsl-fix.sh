#!/bin/bash
# wsl-fix.sh — ① env 값 병합(비밀 미출력) ② Qdrant 를 원본과 같은 1.12.0 으로 맞추고 스냅샷 복원
set -e

# ── ① env 병합
python3 - <<'EOP'
part = {}
for l in open("/mnt/c/newplay/env.part"):
    l = l.rstrip("\n")
    if "=" in l:
        k, v = l.split("=", 1); part[k] = v
p = "/home/newplay/projecthub-newteam/.env.production"
out = []
for l in open(p).read().splitlines():
    k = l.split("=", 1)[0]
    out.append(f"{k}={part[k]}" if k in part else l)
open(p, "w").write("\n".join(out) + "\n")
print("env merged:", sorted(part))
EOP
rm -f /mnt/c/newplay/env.part

# ── ② Qdrant 1.12.0 (스냅샷 세그먼트 포맷 호환)
if [ "$(curl -s http://127.0.0.1:6343/ | jq -r .version)" != "1.12.0" ]; then
  sudo systemctl stop qdrant
  curl -fsSL -o /tmp/qdrant-1.12.0.tgz "https://github.com/qdrant/qdrant/releases/download/v1.12.0/qdrant-x86_64-unknown-linux-gnu.tar.gz"
  sudo rm -rf /opt/qdrant /var/lib/qdrant/storage
  sudo mkdir -p /opt/qdrant /var/lib/qdrant/storage /var/lib/qdrant/snapshots
  sudo tar -xzf /tmp/qdrant-1.12.0.tgz -C /opt/qdrant
  sudo chown -R newplay:newplay /var/lib/qdrant
  sudo systemctl start qdrant
  sleep 4
fi
echo "qdrant=$(curl -s http://127.0.0.1:6343/ | jq -r .version)"
curl -s -X POST "http://127.0.0.1:6343/collections/newplay_code/snapshots/upload?priority=snapshot" \
  -H "Content-Type: multipart/form-data" -F "snapshot=@/mnt/c/newplay/export/newplay_code.snapshot" | jq -c '.status, .result'
echo "qdrant points=$(curl -s http://127.0.0.1:6343/collections/newplay_code | jq .result.points_count)"
echo FIX_OK
