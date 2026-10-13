#!/usr/bin/env bash
# refresh-verify-tree.sh — 기계 검증용 체크아웃을 최신 스냅샷에 맞춘다.
#
# 왜 별도 트리인가:
#   미리보기 빌드는 ~/newplay-preview/webstore 에서 `git checkout` + `git clean -fd` 를 돌린다.
#   검증이 그 트리를 읽으면 빌드 도중에 파일이 바뀌어 **틀린 사실**을 내놓는다.
#   그래서 ~/newplay-verify 를 detached worktree 로 따로 뒀다.
#
# 언제 돌리나:
#   webstore 스냅샷을 갱신했을 때. 이 호스트는 GitHub 자격이 없어 fetch 가 안 되므로
#   (디플로이 키 미등록) 스냅샷 갱신은 밖에서 들어온다.
#
# 왜 중요한가:
#   게이트는 "이 줄에 이게 있다" 를 사실로 내민다. 스냅샷이 낡으면 그 사실이 거짓이 된다.
#   아무것도 안 내미는 것보다 나쁘다. 그래서 게이트는 항상 rev 와 날짜를 함께 출력한다.
set -euo pipefail

SRC="${1:-$HOME/newplay-preview/webstore}"
DST="${2:-$HOME/newplay-verify}"

[ -d "$SRC/.git" ] || { echo "원본 레포가 없습니다: $SRC" >&2; exit 1; }

REV=$(git -C "$SRC" rev-parse HEAD)
CUR=$(git -C "$DST" rev-parse HEAD 2>/dev/null || echo none)

if [ "$REV" = "$CUR" ]; then
  echo "이미 최신: $(git -C "$DST" rev-parse --short HEAD) ($(git -C "$DST" log -1 --format=%ad --date=short))"
  exit 0
fi

if [ ! -d "$DST" ]; then
  git -C "$SRC" worktree add --detach "$DST" "$REV"
else
  git -C "$DST" checkout --detach "$REV"
  # 이전 검증에서 남은 것이 있으면 지운다 — 검증 트리는 항상 깨끗해야 한다
  git -C "$DST" clean -fd >/dev/null
fi

echo "갱신: $CUR → $(git -C "$DST" rev-parse --short HEAD) ($(git -C "$DST" log -1 --format=%ad --date=short))"
echo "워처 재시작 필요 — 파일 인덱스가 프로세스 안에 캐시돼 있습니다:"
echo "  systemctl --user restart hermes-newteam"
