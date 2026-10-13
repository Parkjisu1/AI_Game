"""
기존 레벨 field_map 토로이드 재정렬 백필.
 - field_map(풀해상도 격자)을 직접 recenter → 품질 손실 없음
 - 원본 백업(field_map_prewrap / image_base64_prewrap, 1회만)
 - image_base64 재렌더(PF 팔레트)
사용: python _backfill_recenter.py <lv1,lv2,...|ALL> [--apply]
  --apply 없으면 *_recentered 필드에 비파괴 저장(검토용).
"""
import base64
import io
import os
import sys
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
    cnt = Counter(v for row in M for v in row)
    bg = {0}
    nz = [(v, c) for v, c in cnt.items() if v != 0]
    if nz:
        top, tc = max(nz, key=lambda x: x[1])
        if tc > 0.30 * sum(c for _v, c in nz):
            bg.add(top)
    return bg


def longest_empty_run(profile):
    n = len(profile)
    best_start, best_len, i = 0, 0, 0
    d = profile + profile
    while i < n:
        if d[i] == 0:
            j = i
            while j < i + n and d[j] == 0:
                j += 1
            if j - i > best_len:
                best_len, best_start = j - i, i % n
            i = j
        else:
            i += 1
    return best_start, best_len


def recenter(M, H, W, bg):
    col_prof = [sum(1 for r in range(H) if M[r][c] not in bg) for c in range(W)]
    row_prof = [sum(1 for c in range(W) if M[r][c] not in bg) for r in range(H)]
    cs, cl = longest_empty_run(col_prof)
    rs, rl = longest_empty_run(row_prof)
    dx, dy = (cs + cl) % W, (rs + rl) % H
    rolled = [[M[(r + dy) % H][(c + dx) % W] for c in range(W)] for r in range(H)]
    cprof = [sum(1 for r in range(H) if rolled[r][c] not in bg) for c in range(W)]
    rprof = [sum(1 for c in range(W) if rolled[r][c] not in bg) for r in range(H)]
    xs = [c for c in range(W) if cprof[c]]
    ys = [r for r in range(H) if rprof[r]]
    if not xs or not ys:
        return M
    cw = max(xs) - min(xs) + 1
    rh = max(ys) - min(ys) + 1
    sx, sy = max(0, (W - cw) // 2), max(0, (H - rh) // 2)
    return [[rolled[(r - sy) % H][(c - sx) % W] for c in range(W)] for r in range(H)]


def to_fieldmap(M):
    return "\n".join(" ".join(("%02d" % v if v else "..") for v in row) for row in M)


def render_b64(M, cell=10):
    H, W = len(M), len(M[0])
    img = Image.new("RGB", (W * cell, H * cell), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for r in range(H):
        for c in range(W):
            v = M[r][c]
            if v:
                d.rectangle([c * cell, r * cell, c * cell + cell - 1, r * cell + cell - 1], fill=PF.get(v, (128, 128, 128)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


arg = sys.argv[1] if len(sys.argv) > 1 else "ALL"
apply = "--apply" in sys.argv
if arg == "ALL":
    targets = [d["level_number"] for d in col.find({"field_map": {"$exists": True, "$ne": ""}}, {"level_number": 1})]
else:
    targets = [int(x) for x in arg.split(",")]

print("mode:", "APPLY(원본 덮어쓰기)" if apply else "DRY(_recentered 필드)", "| 대상:", len(targets))
changed = 0
for lv in targets:
    doc = col.find_one({"level_number": lv}, {"field_map": 1, "image_base64": 1})
    if not doc or not doc.get("field_map"):
        continue
    M, H, W = parse(doc["field_map"])
    new = recenter(M, H, W, bg_set(M))
    new_fmap = to_fieldmap(new)
    if new_fmap == doc["field_map"]:
        continue  # 이미 정렬됨 → 변경 없음
    new_img = render_b64(new)
    if apply:
        setf = {"field_map": new_fmap, "image_base64": new_img, "recentered_at": "backfill"}
        # 원본 백업(최초 1회)
        if not doc.get("field_map_prewrap"):
            setf["field_map_prewrap"] = doc["field_map"]
            setf["image_base64_prewrap"] = doc.get("image_base64", "")
        col.update_one({"level_number": lv}, {"$set": setf})
    else:
        col.update_one({"level_number": lv}, {"$set": {"field_map_recentered": new_fmap, "image_base64_recentered": new_img}})
    changed += 1
print("변경:", changed, "/", len(targets))
