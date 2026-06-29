"""DB의 design 역할 페르소나 길이/desc 빠른 점검."""
import os
from pymongo import MongoClient

db = MongoClient(os.environ["MONGODB_URI"])[os.environ.get("MONGODB_DB", "aigame")]
roles = ["design_pm", "design_level_designer", "design_level_reviewer", "design_level_lead"]
for role in roles:
    r = db.hermes_agent_roles.find_one({"role": role})
    if not r:
        print(f"  {role:30} (missing)")
        continue
    persona = r.get("persona") or ""
    desc = r.get("description", "")[:60]
    print(f"  {role:30} persona={len(persona):4} chars   desc={desc}")
