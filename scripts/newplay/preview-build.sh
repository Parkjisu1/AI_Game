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
  # --recount: LLM 이 만든 패치는 hunk 헤더의 줄 수(@@ -a,b +c,d @@)를 자주 틀린다.
  # 실측(게임키 목업): @@ -102,6 +102,10 @@ 인데 실제 추가는 3줄 → "corrupt patch".
  # --recount 는 헤더를 무시하고 본문에서 다시 세므로 이 부류가 그대로 통과한다.
  if ! OUT=$($GIT -C "$ROOT" apply --recount --check "$PATCH" 2>&1); then
    fail "패치 적용 불가(--recount --check 실패): $OUT"
  fi
  $GIT -C "$ROOT" apply --recount "$PATCH" || fail "패치 적용 실패"
  APPLIED=$(basename "$PATCH")
fi

# 1-5) 미리보기 전용 보정 — 라우터 basename
#
# 앱은 /preview 하위에서 서빙되는데 <BrowserRouter> 에 basename 이 없다.
# 그러면 /preview/home 이 라우트 /:gameSlug 에 gameSlug="preview" 로 잡혀
# 존재하지 않는 게임의 스토어 화면이 그려진다 — 쿠키 모달만 뜨고 본문이 비던 이유다.
# 사용자 패치를 먼저 적용한 뒤 덧대고, 빌드가 끝나면 아래에서 통째로 되돌린다.
python3 - "$ROOT" <<'PYBASE'
import io, sys
p = sys.argv[1] + "/front-end/src/containers/Router.tsx"
s = io.open(p, encoding="utf-8").read()
if "basename=" in s:
    print("  basename 이미 있음 — 생략")
else:
    old = "<BrowserRouter>"
    n = s.count(old)
    if n == 1:
        s = s.replace(old, "<BrowserRouter basename={import.meta.env.BASE_URL.replace(/[/]$/, '')}>")
        io.open(p, "w", encoding="utf-8").write(s)
        print("  basename 주입 완료")
    else:
        print("  BrowserRouter 앵커 %d개 — 주입 생략(수동 확인 필요)" % n)
PYBASE

# 홈이 끼우는 마케팅 정적 사이트 경로도 BASE_URL 기준으로 바꾼다.
python3 - "$ROOT" <<'PYHOME'
import io, sys
p = sys.argv[1] + "/front-end/src/pages/Home.tsx"
try:
    s = io.open(p, encoding="utf-8").read()
except FileNotFoundError:
    print("  Home.tsx 없음 — 생략")
    raise SystemExit(0)
old = "`/newplay/index.html"
if "BASE_URL}newplay" in s:
    print("  홈 iframe 경로 이미 처리됨")
elif old in s:
    n = s.count(old)
    s = s.replace(old, "`${import.meta.env.BASE_URL}newplay/index.html")
    io.open(p, "w", encoding="utf-8").write(s)
    print("  홈 iframe 경로 %d곳 보정" % n)
else:
    print("  홈 iframe 앵커 없음 — 생략(구조 변경 확인 필요)")
PYHOME

# 1-7) 이번 빌드에 존재하는 라우트를 기록한다(패치로 새로 생긴 것 포함).
ROUTES_JSON=$(python3 - "$ROOT" <<'PYROUTES'
import io, json, re, sys
p = sys.argv[1] + "/front-end/src/containers/Router.tsx"
try:
    s = io.open(p, encoding="utf-8").read()
except Exception:
    print("[]")
    raise SystemExit(0)
seen = []
for m in re.finditer(r"""path=["'`]([^"'`]+)["'`]""", s):
    v = m.group(1)
    if v and v != "*" and v not in seen:
        seen.append(v)
print(json.dumps(seen, ensure_ascii=False))
PYROUTES
)

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

# 4) 소스는 항상 깨끗하게 되돌린다 — 빌드 후 정리
# checkout 은 **추적되던 파일만** 되돌린다. 목업처럼 새 파일을 만드는 패치는
# untracked 로 남아 다음 미리보기에 섞인다(실측: 목업 빌드 후 1건 잔존).
# clean -fd 로 새로 생긴 것까지 지운다.
$GIT -C "$ROOT" checkout -- . 2>/dev/null
$GIT -C "$ROOT" clean -fdq front-end/src front-end/public 2>/dev/null

SHA=$($GIT -C "$ROOT" rev-parse --short HEAD 2>/dev/null)
FILES=$(find "$SERVE" -type f | wc -l)
python3 - "$APPLIED" "$SHA" "$FILES" "$STARTED" "$ROUTES_JSON" <<'PY' > "$META"
import json, sys, datetime
applied, sha, files, started = sys.argv[1:5]
try:
    routes = json.loads(sys.argv[5]) if len(sys.argv) > 5 else []
except Exception:
    routes = []
print(json.dumps({
    "ok": True, "patch": applied, "baseSha": sha, "files": int(files),
    "startedAt": started, "finishedAt": datetime.datetime.now().astimezone().isoformat(),
    "routes": routes,
}, ensure_ascii=False))
PY

echo "미리보기 갱신 완료 — 패치=$APPLIED · 파일 $FILES개 · base=$SHA"
