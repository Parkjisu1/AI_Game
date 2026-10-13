import os
import re

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/aimed/.hermes/watcher/.env")
db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
col = db.pixelforge_levels

terms = {"벚꽃": r"cherry|blossom|벚꽃|sakura", "노움": r"gnome|노움|dwarf", "파인애플": r"pineapple|파인애플"}
docs = list(col.find({}, {"level_number": 1, "bl_metaphor": 1, "pf_metaphor": 1, "designer_note": 1,
                          "field_rows": 1, "field_columns": 1, "status": 1, "image_base64": 1, "field_map": 1}))
for ko, pat in terms.items():
    rx = re.compile(pat, re.I)
    hits = [d for d in docs if rx.search(" ".join(str(d.get(k, "")) for k in ["bl_metaphor", "pf_metaphor", "designer_note"]))]
    print("=== %s (%s): %d hits ===" % (ko, pat, len(hits)))
    for d in hits[:5]:
        meta = str(d.get("bl_metaphor") or d.get("pf_metaphor") or "")[:45]
        print("  lv%-4s %sx%s status=%-9s img=%dB fmap=%dB | %s" % (
            d.get("level_number"), d.get("field_columns"), d.get("field_rows"), d.get("status"),
            len(d.get("image_base64", "") or ""), len(d.get("field_map", "") or ""), meta))
