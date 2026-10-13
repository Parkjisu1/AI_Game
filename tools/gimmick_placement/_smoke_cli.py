"""서버 스모크: 실제 완성보드(Lv34) → cli.py variants/commit."""
import json
import os
import subprocess

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/home/aimed/.hermes/watcher/.env")
PY = "/home/aimed/.hermes/watcher/venv/bin/python"
HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "cli.py")

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ.get("MONGODB_DB", "aigame")]

best = None
for j in db.pixelforge_field_complete_jobs.find({"status": "done"}, {"results": 1, "finished_at": 1}):
    for r in j.get("results", []):
        if r.get("level_number") == 34 and r.get("ok") and r.get("balloons"):
            if best is None or j.get("finished_at", "") > best[0]:
                best = (j.get("finished_at", ""), r)
_fin, r = best
fa = r.get("field_analysis", {})
board = {"field_rows": fa.get("field_rows"), "field_columns": fa.get("field_columns"),
         "balloons": r["balloons"], "gimmicks": []}
cmin = min(b["color"] for b in board["balloons"])
cmax = max(b["color"] for b in board["balloons"])
print("Lv34 board:", board["field_columns"], "x", board["field_rows"],
      "balloons", len(board["balloons"]), "color_range", cmin, "-", cmax)


def run(payload):
    p = subprocess.run([PY, CLI], input=json.dumps(payload), capture_output=True, text=True)
    if p.returncode != 0:
        print("  STDERR:", p.stderr[-400:])
    return json.loads(p.stdout)


res = run({"cmd": "variants", "board": board, "gimmick_type": "Wooden"})
print("\n[variants] ok=", res["ok"], "indexing=", res.get("indexing"))
for v in res["variants"]:
    print("  {:<12} viol={} auto_fix_clean={} designer={} preview={}B".format(
        v["name"], len(v["validation"]["violations"]), v["auto_fix_clean"],
        len(v["designer_needed"]), len(v["preview_b64"])))

res2 = run({"cmd": "commit", "board": board, "gimmick_type": "Wooden", "variant_index": 1})
print("\n[commit idx=1] ok=", res2["ok"], "chosen=", res2.get("chosen"), "clean=", res2.get("clean"))
mv = res2["merged"]["validation"]
print("  merged balloons:", len(res2["merged"]["balloons"]), "gimmicks:", len(res2["merged"]["gimmicks"]),
      "adjustments:", len(res2["adjustments"]), "designer:", len(res2["designer_needed"]))
print("  merged.validation total:", mv["total"], "viol:", mv["violations"])
print("\nSMOKE OK" if res["ok"] and res2["ok"] else "\nSMOKE FAIL")
