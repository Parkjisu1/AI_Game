"""
NR(No-Reference) 품질 점수 — PixelLab 생성물의 잘림/wrap/치우침 자동 탐지.
키 0회. 기존 pixelforge_levels.image_base64(=raw) 코퍼스에 적용 → 재생성 권장 레벨 플래그.
(워크플로우 합성 R2 + critique '대안 S' 채택: 복원 아닌 탐지에 집중)
"""
import base64
import io
import os
from collections import Counter

from dotenv import load_dotenv
from pymongo import MongoClient
from PIL import Image

load_dotenv("/home/aimed/.hermes/watcher/.env")
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
col = db.pixelforge_levels


def nr_score(ib):
    im = Image.open(io.BytesIO(base64.b64decode(ib))).convert("RGBA")
    W, H = im.size
    px = im.load()
    corners = [px[0, 0], px[W - 1, 0], px[0, H - 1], px[W - 1, H - 1]]
    has_alpha = any(px[x, y][3] < 128 for x in range(W) for y in range(0, H, max(1, H // 8)))
    bgc = Counter(corners).most_common(1)[0][0]

    def isbg(p):
        return (p[3] < 128) if has_alpha else (abs(p[0] - bgc[0]) + abs(p[1] - bgc[1]) + abs(p[2] - bgc[2]) < 30)

    xs, ys = [], []
    top = bot = left = right = 0
    for y in range(H):
        for x in range(W):
            if not isbg(px[x, y]):
                xs.append(x); ys.append(y)
                if y == 0: top += 1
                if y == H - 1: bot += 1
                if x == 0: left += 1
                if x == W - 1: right += 1
    if not xs:
        return None
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    centering = (abs(cx - W / 2) / W + abs(cy - H / 2) / H) / 2
    fill = len(xs) / (W * H)
    v_bleed = (top >= W * 0.5) and (bot >= W * 0.5)
    h_bleed = (left >= H * 0.5) and (right >= H * 0.5)
    return dict(W=W, H=H, centering=centering, fill=fill, v_bleed=v_bleed, h_bleed=h_bleed, has_alpha=has_alpha)


def style_type(cat):
    c = (cat or "").strip().lower()
    if c in ("nature", "seasonal", "holiday", "art"):
        return "background"
    if c in ("geometric", "symbol", "abstract"):
        return "structure"
    return "character"  # animal/character/food/object


def flag(s, st):
    """유형 인식 플래그. 패턴(structure)·씬(background)은 가득참/가장자리 정상."""
    reasons = []
    sev = 0.0
    if st == "character":
        # 단일 피사체여야 함 → 씬화/잘림/치우침 모두 결함
        if s["v_bleed"] or s["h_bleed"]:
            reasons.append("잘림/wrap(%s)" % ("상하" if s["v_bleed"] else "좌우")); sev += 2.0
        if s["fill"] > 0.78:
            reasons.append("씬화(fill %.2f)" % s["fill"]); sev += 1.5
        if s["centering"] > 0.12:
            reasons.append("치우침(%.0f%%)" % (s["centering"] * 100)); sev += s["centering"] * 2
        if s["fill"] < 0.10:
            reasons.append("피사체 과소(fill %.2f)" % s["fill"]); sev += 1.0
    else:
        # background/structure = 가득참 정상. 심한 치우침만(드물게 실제 wrap)
        if s["centering"] > 0.18:
            reasons.append("치우침(%.0f%%)" % (s["centering"] * 100)); sev += s["centering"] * 2
    return reasons, round(sev, 3)


rows = []
for d in col.find({"image_base64": {"$exists": True, "$ne": ""}}, {"image_base64": 1, "level_number": 1, "bl_metaphor": 1, "bl_category": 1}):
    try:
        s = nr_score(d["image_base64"])
    except Exception:
        continue
    if not s:
        continue
    st = style_type(d.get("bl_category"))
    reasons, sev = flag(s, st)
    rows.append(dict(lv=d.get("level_number"), meta=str(d.get("bl_metaphor") or "")[:18],
                     st=st, fill=round(s["fill"], 2), centering=round(s["centering"], 2),
                     reasons=reasons, sev=sev))

from collections import Counter as C
by_type = C(r["st"] for r in rows)
flagged = [r for r in rows if r["reasons"]]
flagged.sort(key=lambda r: -r["sev"])
print("분석:", len(rows), "유형:", dict(by_type))
print("플래그(재생성 권장):", len(flagged), f"({100*len(flagged)//max(1,len(rows))}%)  — 유형:", dict(C(r['st'] for r in flagged)))
print("\n=== 재생성 우선순위 (캐릭터형 결함 위주) ===")
for r in flagged[:25]:
    print(f"  lv{r['lv']:<4} sev {r['sev']:<5} [{r['st'][:4]}] {r['meta']:<18} {' / '.join(r['reasons'])}")
cat = C()
for r in flagged:
    for x in r["reasons"]:
        cat[x.split("(")[0]] += 1
print("\n사유별:", dict(cat))
