import base64
import io
import os

from dotenv import load_dotenv
from pymongo import MongoClient
from PIL import Image

import gimmick_placement as gp

load_dotenv("/home/aimed/.hermes/watcher/.env")
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
col = db.pixelforge_levels

PF = gp.PF_PALETTE  # 1-28

def render_fieldmap(fmap, cell=10):
    rows = [r for r in fmap.split("\n") if r.strip()]
    H = len(rows)
    grid = []
    W = 0
    for r in rows:
        toks = r.split()
        W = max(W, len(toks))
        grid.append(toks)
    img = Image.new("RGB", (W * cell, H * cell), (235, 235, 235))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    for ry, toks in enumerate(grid):
        for cx, t in enumerate(toks):
            if t == "..":
                continue
            try:
                ci = int(t)
            except ValueError:
                continue
            rgb = PF.get(ci, (128, 128, 128))
            d.rectangle([cx * cell, ry * cell, cx * cell + cell - 1, ry * cell + cell - 1], fill=rgb)
    return img

for lv in [248, 253, 257]:
    doc = col.find_one({"level_number": lv}, {"field_map": 1, "image_base64": 1, "field_rows": 1, "field_columns": 1, "bl_metaphor": 1})
    fmap = doc.get("field_map", "")
    rows = [r for r in fmap.split("\n") if r.strip()]
    widths = set(len(r.split()) for r in rows)
    print("lv%d %s rows=%d widths=%s declared=%sx%s meta=%s" % (
        lv, "", len(rows), sorted(widths), doc.get("field_columns"), doc.get("field_rows"), doc.get("bl_metaphor")))
    img = render_fieldmap(fmap)
    img.save("/home/aimed/gimmick_placement/_fmap_lv%d.png" % lv)
    # also save the stored image_base64 thumbnail
    ib = doc.get("image_base64")
    if ib:
        try:
            raw = base64.b64decode(ib)
            with open("/home/aimed/gimmick_placement/_img_lv%d.png" % lv, "wb") as f:
                f.write(raw)
        except Exception as e:
            print("  img decode fail:", e)
print("saved.")
