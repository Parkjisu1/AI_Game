"""세션의 큐레이션 전체 과정 점검: 세션 stage / v43 job curations / pixelforge_levels field_map 갱신 여부."""
import os, json, sys
from pymongo import MongoClient
from bson import ObjectId

c = MongoClient(os.environ["MONGODB_URI"])
db = c[os.environ.get("MONGODB_DB", "aigame")]

sess_id = sys.argv[1] if len(sys.argv) > 1 else "6a168358e63453fc3198f7c4"
sess = db["pixelforge_pipeline_sessions"].find_one({"_id": ObjectId(sess_id)})
if not sess:
    print(f"Session {sess_id} not found"); sys.exit(1)

print(f"=== Pipeline Session {sess_id} ===")
print(f"  label       = {sess.get('label')}")
print(f"  stage       = {sess.get('stage')}")
print(f"  target_lvs  = {sess.get('target_levels')}")
print(f"  preset      = {sess.get('gimmick_preset')}")
print(f"  auto_advance= {sess.get('auto_advance')}")
print(f"  curations   = {sess.get('curations')}")  # 세션의 큐레이션 선택
print(f"  curation_results = {sess.get('curation_results')[:3] if sess.get('curation_results') else None}")
print(f"  art_job     = {sess.get('art_job')}")
print(f"  fc_job      = {sess.get('field_complete_job')}")
print(f"  stage_history = {sess.get('stage_history')}")
print(f"  error       = {sess.get('error')}")

art = sess.get("art_job") or {}
art_id = art.get("job_id")
if art_id:
    v43 = db["pixelforge_v43_jobs"].find_one({"_id": ObjectId(art_id)})
    print(f"\n=== v43 job {art_id} ===")
    print(f"  status       = {v43.get('status')}")
    print(f"  out_dir      = {v43.get('out_dir')}")
    print(f"  curated_at   = {v43.get('curated_at')}")
    print(f"  curated_by   = {v43.get('curated_by')}")
    print(f"  curations    = {v43.get('curations')}")
    cr = v43.get("curation_results") or []
    print(f"  curation_results count = {len(cr)}")
    for r in cr[:8]:
        print(f"    Lv {r.get('level')} label={r.get('label')} ok={r.get('ok')} err={r.get('error','')}")

# pixelforge_levels — target lv 들의 field_map / field_map_source / field_map_curated_at 확인
tl = sess.get("target_levels") or []
print(f"\n=== pixelforge_levels — {len(tl)} target levels — field_map state ===")
rows = list(db["pixelforge_levels"].find(
    {"level_number": {"$in": tl}, "status": {"$exists": True}},
    projection={"level_number": 1, "field_map_source": 1, "field_map_pipeline": 1,
                "field_map_curated_at": 1, "field_map_curated_from": 1, "field_map": 1,
                "updated_at": 1},
))
rows.sort(key=lambda r: r["level_number"])
for r in rows:
    fm_len = len(r.get("field_map") or "")
    print(f"  Lv {r['level_number']:>3} | src={r.get('field_map_source','??'):<30}"
          f" | curated_at={r.get('field_map_curated_at','??')[:19] if r.get('field_map_curated_at') else '—':<19}"
          f" | fm_len={fm_len}")
    if r.get("field_map_curated_from"):
        cf = r["field_map_curated_from"]
        print(f"      from job={cf.get('job_id','??')[-8:]} label={cf.get('label')} png={cf.get('png')}")
