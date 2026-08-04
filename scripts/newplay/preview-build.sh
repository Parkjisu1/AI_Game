#!/usr/bin/env bash
# preview-build.sh — 수정안(patch)을 적용해 front-end 를 빌드하고 미리보기로 띄운다.
#
# 목적: 라이브(newplay.store)에도 QA 에도 올리지 않고, 제안된 변경이 화면에서 어떻게 보이는지 확인.
#       Hermes 의 dev 역할은 지금 push 권한이 없어 "제안"까지만 하는데, 그 제안을 눈으로 볼 방법이 없었다.
#
# 동작:
#   1. 작업 트리를 원본 상태로 되돌린다 (이전 미리보기 잔재 제거)
#   2. 패치가 있으면 git apply
#   3. yarn build:qa  (약 2초. API 는 qa-api.newplay.store 를 본다)
#   4. dist 를 serve 디렉토리로 원자적 교체
#   5. 작업 트리를 다시 되돌린다 — 미리보기는 산출물만 남기고 소스는 항상 깨끗하게 둔다
#
# Usage:
#   preview-build.sh                 # 원본 그대로 빌드 (기준선)
#   preview-build.sh /path/to.patch  # 수정안 적용 후 빌드
set -uo pipefail

ROOT="$HOME/newplay-preview/webstore"
FE="$ROOT/front-end"
SERVE="$HOME/newplay-preview/serve"
META="$HOME/newplay-preview/state.json"
GIT="git"
export PATH="$HOME/.nvm/versions/node/v20.20.2/bin:$PATH"

PATCH="${1:-}"
STARTED=$(date -Is)

fail() {
  # 실패해도 상태 파일은 남긴다 — 화면이 "왜 안 되는지" 를 보여줄 수 있어야 한다.
  printf '{"ok":false,"error":%s,"patch":%s,"startedAt":"%s","finishedAt":"%s"}\n' \
    "$(printf '%s' "$1" | head -c 2000 | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')" \
    "$(printf '%s' "${PATCH:-}" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))')" \
    "$STARTED" "$(date -Is)" > "$META"
  echo "FAIL: $1" >&2
  exit 1
}

cd "$FE" || fail "front-end 디렉토리 없음: $FE"

# 동시 빌드 차단 — 두 사람이 동시에 미리보기를 누르면 서로의 패치가 섞이고
# serve 디렉토리 교체가 겹쳐 반쪽짜리 화면이 나온다.
LOCK="$HOME/newplay-preview/.build.lock"
exec 9>"$LOCK"
if ! flock -n 9; then
  fail "다른 미리보기 빌드가 진행 중입니다. 잠시 후 다시 시도하세요."
fi

# 1) 원본 복구 — 이전 미리보기의 패치가 남아 있으면 안 된다
$GIT -C "$ROOT" checkout -- . 2>/dev/null
$GIT -C "$ROOT" clean -fd front-end/src >/dev/null 2>&1

APPLIED="none"
if [ -n "$PATCH" ]; then
  [ -f "$PATCH" ] || fail "패치 파일 없음: $PATCH"
  if ! OUT=$($GIT -C "$ROOT" apply --check "$PATCH" 2>&1); then
    fail "패치 적용 불가(--check 실패): $OUT"
  fi
  $GIT -C "$ROOT" apply "$PATCH" || fail "패치 적용 실패"
  APPLIED=$(basename "$PATCH")
fi

# 2) 빌드
# base=/preview/ — Next 앱의 /preview 하위에서 서빙하므로 에셋 절대경로를 그에 맞춘다.
# (기본 빌드는 /assets/... 로 나와서 /preview/ 아래에서는 전부 404 가 된다)
BUILD_LOG=$(timeout 900 node .yarn/releases/yarn-4.17.0.cjs vite build --mode qa --base=/preview/ 2>&1)
BUILD_RC=$?
if [ $BUILD_RC -ne 0 ]; then
  $GIT -C "$ROOT" checkout -- . 2>/dev/null
  fail "빌드 실패(rc=$BUILD_RC): $(printf '%s' "$BUILD_LOG" | tail -c 1500)"
fi
[ -f "$FE/dist/index.html" ] || { $GIT -C "$ROOT" checkout -- . 2>/dev/null; fail "dist/index.html 이 생성되지 않았습니다"; }

# 3) 원자적 교체 — 교체 도중에 화면이 반쪽짜리를 보지 않게
rm -rf "$SERVE.new"
cp -r "$FE/dist" "$SERVE.new" || fail "dist 복사 실패"
rm -rf "$SERVE.old"
[ -d "$SERVE" ] && mv "$SERVE" "$SERVE.old"
mv "$SERVE.new" "$SERVE" || fail "serve 교체 실패"
rm -rf "$SERVE.old"

# 4) 소스는 항상 깨끗하게 되돌린다
$GIT -C "$ROOT" checkout -- . 2>/dev/null

SHA=$($GIT -C "$ROOT" rev-parse --short HEAD 2>/dev/null)
FILES=$(find "$SERVE" -type f | wc -l)
python3 - "$APPLIED" "$SHA" "$FILES" "$STARTED" <<'PY' > "$META"
import json, sys, datetime
applied, sha, files, started = sys.argv[1:5]
print(json.dumps({
    "ok": True, "patch": applied, "baseSha": sha, "files": int(files),
    "startedAt": started, "finishedAt": datetime.datetime.now().astimezone().isoformat(),
}, ensure_ascii=False))
PY

echo "미리보기 갱신 완료 — 패치=$APPLIED · 파일 $FILES개 · base=$SHA"
