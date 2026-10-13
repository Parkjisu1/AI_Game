#!/usr/bin/env bash
# rollback.sh — 플랫폼이 죽었을 때 SSH 로 직접 되돌린다. 마지막 방어선.
#
# 왜 별도 스크립트인가:
#   플랫폼 배포는 자기 자신을 고치는 일이라, 잘못되면 **되돌리기 버튼이 있는 화면이 같이 죽는다.**
#   자동 복구(platform_deploy.py)가 먼저 시도하지만 그것마저 실패할 수 있다.
#   그때 사람이 쓸 수 있는 것이 이 스크립트다. 웹도, 파이썬 모듈도, DB도 필요 없다.
#
# Usage:
#   rollback.sh              # 마지막 커밋 하나 되돌리기 (가장 흔한 경우)
#   rollback.sh <커밋>       # 그 커밋 상태로 되돌리기
#   rollback.sh --status     # 지금 상태만 보기
set -uo pipefail

TREE="${NEWPLAY_PLATFORM_TREE:-$HOME/projecthub-newteam}"
SERVICE="${NEWPLAY_PLATFORM_SERVICE:-projecthub-newteam}"
HEALTH="${NEWPLAY_PLATFORM_HEALTH:-http://127.0.0.1:3000/login}"
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"

cd "$TREE" || { echo "플랫폼 디렉토리가 없습니다: $TREE" >&2; exit 1; }
[ -d .git ] || { echo "git 저장소가 아닙니다 — 되돌릴 기준이 없습니다" >&2; exit 1; }

status() {
  echo "현재 커밋 : $(git log --oneline -1)"
  echo "서비스    : $(systemctl --user is-active "$SERVICE" 2>/dev/null)"
  printf "응답      : "; curl -s -o /dev/null -w "%{http_code}\n" --max-time 10 "$HEALTH" || echo "무응답"
  echo
  echo "최근 이력:"
  git log --oneline -8 | sed "s/^/  /"
}

if [ "${1:-}" = "--status" ]; then status; exit 0; fi

echo "=== 되돌리기 전 ==="; status; echo

TARGET="${1:-HEAD~1}"
echo "→ $TARGET 상태로 되돌립니다."
git reset --hard "$TARGET" || { echo "reset 실패" >&2; exit 1; }

echo "→ 빌드 중…"
if ! npm run build >/tmp/rollback-build.log 2>&1; then
  echo "빌드 실패. 로그: /tmp/rollback-build.log" >&2
  tail -15 /tmp/rollback-build.log >&2
  exit 1
fi

echo "→ 재기동…"
systemctl --user restart "$SERVICE"

# 재기동 직후엔 잠깐 안 뜬다. 최대 60초 기다린다.
for _ in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$HEALTH" || echo 000)
  case "$code" in 2*|3*) echo "복구됨 (HTTP $code)"; echo; status; exit 0;; esac
  sleep 3
done

echo "되돌렸지만 아직 응답이 없습니다. 로그를 확인하세요:" >&2
echo "  tail -50 ~/.newteam/logs/projecthub-newteam.log" >&2
exit 1
