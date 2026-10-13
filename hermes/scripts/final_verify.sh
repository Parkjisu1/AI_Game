#!/usr/bin/env bash
# Mother에서 실행할 최종 검증 스크립트

set +e

echo "=== Mother → Sub SSH 테스트 ==="
ssh -o BatchMode=yes -o StrictHostKeyChecking=no aimed@100.87.87.59 'echo SUB_FROM_MOTHER_OK && hostname && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader'
SUB_RC=$?
echo "  SSH exit code: $SUB_RC"

echo ""
echo "=== Mother → 머신 B SSH 테스트 ==="
ssh -o BatchMode=yes -o StrictHostKeyChecking=no user@100.92.43.9 'echo B_FROM_MOTHER_OK && hostname'
B_RC=$?
echo "  SSH exit code: $B_RC"

echo ""
echo "=== Python 메모리 로더 테스트 ==="
cd ~/.hermes/watcher
source venv/bin/activate
export HERMES_MEMORY_ROOT=/home/aimed/.hermes/memories
export HERMES_USER_REGISTRY=/home/aimed/.hermes/memories/user_registry.yaml
python3 - <<'PYEOF'
import sys
sys.path.insert(0, ".")
from scoped_memory_loader import load_scoped_memory, estimate_total_tokens
from user_name_resolver import _load_registry

registry = _load_registry()
users = registry.get("users", {})
channels = registry.get("channels", {})
print(f"user_registry 로드: users={len(users)}, channels={len(channels)}")

files = load_scoped_memory(
    team="aimed-puzzle",
    genre="puzzle",
    role="designer",
    project="balloonflow",
)
print(f"메모리 파일 로드: {len(files)}개, 약 {estimate_total_tokens(files)} 토큰")
for f in files:
    print(f"  - {f['path']}")
PYEOF
PY_RC=$?

echo ""
echo "=== 결과 요약 ==="
if [ $SUB_RC -eq 0 ]; then echo "✅ Mother → Sub SSH"; else echo "❌ Mother → Sub SSH (BOM 이슈 추정)"; fi
if [ $B_RC -eq 0 ]; then echo "✅ Mother → 머신 B SSH"; else echo "❌ Mother → 머신 B SSH"; fi
if [ $PY_RC -eq 0 ]; then echo "✅ Python 메모리 로더"; else echo "❌ Python 메모리 로더"; fi
