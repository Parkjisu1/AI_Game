"""토로이드 재정렬 테스트 — field_map을 파싱해 wrap offset을 찾아 roll로 센터링."""
import os
from collections import Counter

from dotenv import load_dotenv
from pymongo import MongoClient
from PIL import Image, ImageDraw

import gimmick_placement as gp

load_dotenv("/home/aimed/.hermes/watcher/.env")
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
col = db.pixelforge_levels
PF = gp.PF_PALETTE


def parse(fmap):
    rows = [r.split() for r in fmap.split("\n") if r.strip()]
    W = max(len(r) for r in rows)
    M = [[(int(t) if t != ".." else 0) for t in (r + [".."] * (W - len(r)))] for r in rows]
    return M, len(M), W


def bg_set(M):
    """배경 = 빈칸(0) + 가장 많은 단색(테두리/배경)."""
    cnt = Counter(v for row in M for v in row)
    bg = {0}
    # 최빈 비-0 색도 배경 후보(꽉 찬 단색 배경)
    nz = [(v, c) for v, c in cnt.items() if v != 0]
    if nz:
        top, tc = max(nz, key=lambda x: x[1])
        if tc > 0.30 * sum(c for _v, c in nz):
            bg.add(top)
    return bg


def longest_empty_run(profile):
    """원형 프로파일에서 가장 긴 '빈(0)' 연속 구간의 (시작, 길이)."""
    n = len(profile)
    # 이중 순회로 원형 처리
    best_start, best_len = 0, 0
    i = 0
    doubled = profile + profile
    while i < n:
        if doubled[i] == 0:
            j = i
            while j < i + n and doubled[j] == 0:
                j += 1
            if j - i > best_len:
                best_len = j - i
                best_start = i % n
            i = j
        else:
            i += 1
    return best_start, best_len


def recenter(M, H, W, bg):
    col_prof = [sum(1 for r in range(H) if M[r][c] not in bg) for c in range(W)]
    row_prof = [sum(1 for c in range(W) if M[r][c] not in bg) for r in range(H)]
    # 가장 긴 빈 구간 끝 = 콘텐츠 시작 → 그 지점을 0으로 roll, 이후 중앙 정렬
    cs, cl = longest_empty_run(col_prof)
    rs, rl = longest_empty_run(row_prof)
    dx = (cs + cl) % W  # 콘텐츠가 시작되는 컬럼
    dy = (rs + rl) % H
    # roll so content starts at 0
    rolledx = [[M[r][(c + dx) % W] for c in range(W)] for r in range(H)]
    rolled = [[rolledx[(r + dy) % H][c] for c in range(W)] for r in range(H)]
    # 콘텐츠 폭/높이 → 중앙 정렬 추가 shift
    cprof = [sum(1 for r in range(H) if rolled[r][c] not in bg) for c in range(W)]
    rprof = [sum(1 for c in range(W) if rolled[r][c] not in bg) for r in range(H)]
    cw = max((c for c in range(W) if cprof[c]), default=0) - min((c for c in range(W) if cprof[c]), default=0) + 1
    rh = max((r for r in range(H) if rprof[r]), default=0) - min((r for r in range(H) if rprof[r]), default=0) + 1
    sx = max(0, (W - cw) // 2)
    sy = max(0, (H - rh) // 2)
    # 센터링도 toroidal roll → 배경 보존(풀블리드 배경에 빈 가장자리 안 생김)
    final = [[rolled[(r - sy) % H][(c - sx) % W] for c in range(W)] for r in range(H)]
    return final, (dx, dy)


def render(M, cell=10):
    H, W = len(M), len(M[0])
    img = Image.new("RGB", (W * cell, H * cell), (235, 235, 235))
    d = ImageDraw.Draw(img)
    for r in range(H):
        for c in range(W):
            v = M[r][c]
            if v == 0:
                continue
            d.rectangle([c * cell, r * cell, c * cell + cell - 1, r * cell + cell - 1], fill=PF.get(v, (128, 128, 128)))
    return img


for lv in [248, 253, 257]:
    doc = col.find_one({"level_number": lv}, {"field_map": 1})
    M, H, W = parse(doc["field_map"])
    bg = bg_set(M)
    final, off = recenter(M, H, W, bg)
    print("lv%d %dx%d bg=%s roll_offset=%s" % (lv, W, H, sorted(bg), off))
    render(final).save("/home/aimed/gimmick_placement/_recenter_lv%d.png" % lv)
print("done")
