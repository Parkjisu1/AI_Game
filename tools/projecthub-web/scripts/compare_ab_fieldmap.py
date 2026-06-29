"""A vs B PNG → field_map text 비교. 각 라벨이 같은 nearest-palette 로직으로 디코드되는지 검증."""
import os
from PIL import Image

BL_PALETTE = [
    "#FC6AAF", "#50E8F6", "#8950F8", "#FED555", "#73FE66", "#FDA14C",
    "#FFFFFF", "#414141", "#6EA8FA", "#39AE2E", "#FC5E5E", "#326BF8",
    "#3AA58B", "#E7A7FA", "#B7C7FB", "#6A4A30", "#FEE3A9", "#FDB7C1",
    "#9E3D5E", "#A7DD94", "#592E7E", "#DC7881", "#D9D9E7", "#6F727F",
    "#FC38A5", "#FDB458", "#890A08", "#6FAFB1",
]
def hex_rgb(h):
    h = h.strip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
PAL = [hex_rgb(c) for c in BL_PALETTE]
def nearest(r, g, b, a):
    if a < 128: return 0
    best, bd = 0, 1e18
    for i, (pr, pg, pb) in enumerate(PAL):
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < bd: bd, best = d, i
    return best + 1

def png_to_fieldmap(path):
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    px = img.load()
    rows = []
    for y in range(h):
        cells = []
        for x in range(w):
            r, g, b, a = px[x, y]
            pid = nearest(r, g, b, a)
            cells.append(".." if pid == 0 else f"{pid:02d}")
        rows.append(" ".join(cells))
    return "\n".join(rows), w, h

OUT_DIR = "/home/aimed/.hermes/v43_out/6a167beee63453fc3198f7c3"
# Lv 1, Lv 3, Lv 23 (different motif A/B 비교)
for lv, meta in [(1, "나선"), (3, "헤링본"), (23, "방사_패턴")]:
    pA = f"{OUT_DIR}/level_{lv:03d}_{meta}_A.png"
    pB = f"{OUT_DIR}/level_{lv:03d}_{meta}_B.png"
    if not (os.path.exists(pA) and os.path.exists(pB)):
        print(f"Lv {lv}: missing files")
        continue
    fa, wa, ha = png_to_fieldmap(pA)
    fb, wb, hb = png_to_fieldmap(pB)
    same = fa == fb
    # count palette ids
    from collections import Counter
    def stats(fm):
        cells = fm.replace("\n", " ").split()
        empties = sum(1 for c in cells if c == "..")
        colors = Counter(c for c in cells if c != "..")
        return len(cells), empties, len(colors), colors
    sa, ea, ca, ka = stats(fa)
    sb, eb, cb, kb = stats(fb)
    print(f"Lv {lv} ({meta}):")
    print(f"  A: {wa}x{ha} cells={sa} empty={ea} colors_used={ca} top={ka.most_common(3)}")
    print(f"  B: {wb}x{hb} cells={sb} empty={eb} colors_used={cb} top={kb.most_common(3)}")
    print(f"  identical? {same}")
    if not same:
        # show first different row
        ra = fa.split("\n")
        rb = fb.split("\n")
        for i in range(min(len(ra), len(rb))):
            if ra[i] != rb[i]:
                print(f"  first diff row [{i}]:")
                print(f"    A: {ra[i][:80]}")
                print(f"    B: {rb[i][:80]}")
                break
    print()
