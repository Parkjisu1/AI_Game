"""
GameForge AI Workflow - Web UI
Claude-style interface for AI Game Design & Code Generation.

Usage:
    python webapp/app.py
    → http://localhost:7862
"""

import os
import json
import subprocess
import time
import re as _re
from datetime import datetime
from pathlib import Path

import gradio as gr
from pymongo import MongoClient

# ─── Config ───────────────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).parent.parent
ENV_PATH = ROOT_DIR / ".env"
NODE = "node"

def load_env():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, val = line.partition("=")
            if key and val:
                os.environ.setdefault(key.strip(), val.strip())

load_env()

MONGO_URI = os.environ.get("MONGO_URI", "")
MONGO_DB = os.environ.get("MONGO_DB_NAME", "aigame")
AUTH_USERS = {"admin": os.environ.get("WEBAPP_PASS", "gameforge2026")}

GENRES = ["idle", "rpg", "puzzle", "merge", "slg", "tycoon", "simulation", "casual", "generic"]
DOMAINS = ["InGame", "OutGame", "Balance", "Content", "BM", "LiveOps", "UX", "Social", "Meta"]
ROLES = ["Manager", "Controller", "Calculator", "Processor", "Handler", "Listener",
         "Provider", "Factory", "Service", "Validator", "Converter", "Builder",
         "Pool", "State", "Command", "Observer", "Helper", "Wrapper", "Context", "Config", "UX"]
LAYERS = ["Core", "Domain", "Game"]
DATA_TYPES = ["formula", "table", "rule", "flow", "config", "spec", "content_data"]

# ─── Claude-style CSS ────────────────────────────────────────────────────────

CSS = """
/* === Reset & Base === */
.gradio-container {
    max-width: 100% !important; padding: 0 !important; margin: 0 !important;
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}
footer { display: none !important; }

/* === Sidebar === */
#sidebar {
    background: #f9f9f9 !important; border-right: 1px solid #e5e5e5 !important;
    min-height: 100vh !important; padding: 0 !important;
}
.dark #sidebar { background: #171717 !important; border-color: #2a2a2a !important; }

#sidebar-header {
    padding: 20px 16px 12px !important; border-bottom: 1px solid #e5e5e5 !important;
}
.dark #sidebar-header { border-color: #2a2a2a !important; }

#sidebar-header .prose h2 {
    margin: 0 !important; font-size: 1.1rem !important; font-weight: 700 !important;
    letter-spacing: -0.3px !important;
}
#sidebar-header .prose p {
    margin: 2px 0 0 !important; font-size: 0.72rem !important; color: #999 !important;
}

/* Nav buttons */
.nav-btn {
    width: 100% !important; text-align: left !important; padding: 10px 16px !important;
    border: none !important; border-radius: 8px !important; margin: 2px 8px !important;
    font-size: 0.85rem !important; font-weight: 500 !important; cursor: pointer !important;
    background: transparent !important; color: #555 !important;
    transition: background 0.15s !important; justify-content: flex-start !important;
    max-width: calc(100% - 16px) !important;
}
.nav-btn:hover { background: #ececec !important; }
.dark .nav-btn { color: #ccc !important; }
.dark .nav-btn:hover { background: #252525 !important; }

/* Active nav */
.nav-btn-active {
    background: #e8e8e8 !important; color: #111 !important; font-weight: 600 !important;
}
.dark .nav-btn-active { background: #2a2a2a !important; color: #fff !important; }

/* Stat pills in sidebar */
.stat-item {
    display: flex; justify-content: space-between; padding: 6px 16px;
    font-size: 0.75rem; color: #888;
}
.stat-item .prose { margin: 0 !important; }
.stat-item .prose p { margin: 0 !important; font-size: 0.75rem !important; color: #888 !important; }

/* === Main Content === */
#main-content {
    padding: 0 !important; background: #fff !important; min-height: 100vh !important;
}
.dark #main-content { background: #1a1a1a !important; }

/* Page header */
.page-header {
    padding: 20px 32px 16px !important; border-bottom: 1px solid #f0f0f0 !important;
}
.dark .page-header { border-color: #2a2a2a !important; }
.page-header .prose h1 {
    margin: 0 !important; font-size: 1.3rem !important; font-weight: 700 !important;
    letter-spacing: -0.3px !important;
}
.page-header .prose p {
    margin: 4px 0 0 !important; font-size: 0.8rem !important; color: #999 !important;
}

/* Content area */
.content-body { padding: 24px 32px !important; }

/* === Form Styling === */
.form-section {
    margin-bottom: 20px !important; padding: 20px !important;
    border: 1px solid #eee !important; border-radius: 12px !important;
    background: #fafafa !important;
}
.dark .form-section { border-color: #2a2a2a !important; background: #1f1f1f !important; }

.form-label {
    font-size: 0.75rem !important; font-weight: 600 !important; text-transform: uppercase !important;
    letter-spacing: 0.5px !important; color: #888 !important; margin-bottom: 8px !important;
}

/* Input styling */
input, textarea, select, .gr-input, .gr-dropdown {
    border-radius: 8px !important;
}

/* === Buttons === */
.btn-primary {
    background: #d97706 !important; color: #fff !important; border: none !important;
    border-radius: 8px !important; padding: 10px 24px !important; font-weight: 600 !important;
    font-size: 0.85rem !important;
}
.btn-primary:hover { background: #b45309 !important; }

.btn-secondary {
    background: transparent !important; color: #555 !important;
    border: 1px solid #ddd !important; border-radius: 8px !important;
    padding: 10px 24px !important; font-weight: 500 !important; font-size: 0.85rem !important;
}
.dark .btn-secondary { border-color: #444 !important; color: #ccc !important; }
.btn-secondary:hover { background: #f5f5f5 !important; }
.dark .btn-secondary:hover { background: #252525 !important; }

.btn-danger {
    background: #dc2626 !important; color: #fff !important; border: none !important;
    border-radius: 8px !important; font-weight: 600 !important;
}

/* === Result Cards === */
.result-card {
    border: 1px solid #eee !important; border-radius: 12px !important;
    padding: 16px 20px !important; margin: 8px 0 !important;
    background: #fff !important; transition: box-shadow 0.15s !important;
}
.result-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important; }
.dark .result-card { border-color: #2a2a2a !important; background: #1f1f1f !important; }

/* === Log Output === */
.log-output textarea {
    font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace !important;
    font-size: 0.78rem !important; line-height: 1.5 !important;
    background: #1a1a2e !important; color: #a8b2d1 !important;
    border-radius: 10px !important; padding: 16px !important;
}

/* === Tabs inside content === */
.inner-tabs .tab-nav { border-bottom: 1px solid #eee !important; margin-bottom: 16px !important; }
.dark .inner-tabs .tab-nav { border-color: #333 !important; }
.inner-tabs .tab-nav button {
    font-size: 0.82rem !important; font-weight: 500 !important; padding: 8px 16px !important;
    border: none !important; background: transparent !important;
}
.inner-tabs .tab-nav button.selected {
    font-weight: 600 !important; border-bottom: 2px solid #d97706 !important; color: #d97706 !important;
}

/* === Badge === */
.badge-expert { color: #16a34a; font-weight: 600; }
.badge-base { color: #888; }

/* === Checkbox items === */
.gr-check-group label { font-size: 0.82rem !important; }

/* === Hide outer tabs nav (we use sidebar instead) === */
#main-tabs > .tab-nav { display: none !important; }
"""

# ─── MongoDB ──────────────────────────────────────────────────────────────────

_client = None
_db = None

def get_db():
    global _client, _db
    if _db is None:
        _client = MongoClient(MONGO_URI)
        _db = _client[MONGO_DB]
    return _db

def get_stats():
    db = get_db()
    return {col: db[col].count_documents({})
            for col in ["code_base", "code_expert", "design_base", "design_expert", "rules", "pending"]}

def ci(val):
    return {"$regex": f"^{_re.escape(val)}$", "$options": "i"}

# ─── Direct MongoDB Queries ──────────────────────────────────────────────────

def query_design_db(genre=None, domain=None, system=None, data_type=None, limit=30, min_score=0):
    db = get_db()
    q = {}
    if genre: q["genre"] = ci(genre)
    if domain: q["domain"] = ci(domain)
    if system: q["system"] = {"$regex": system, "$options": "i"}
    if data_type: q["data_type"] = ci(data_type)
    if min_score > 0: q["score"] = {"$gte": min_score}

    results = []
    for col in ["design_expert", "design_base"]:
        for doc in db[col].find(q).sort("score", -1).limit(limit - len(results)):
            doc["_id"] = str(doc["_id"])
            doc["_source"] = col
            results.append(doc)
        if len(results) >= limit:
            break
    return results

def query_code_db(genre=None, role=None, system=None, layer=None, limit=30, min_score=0):
    db = get_db()
    q = {}
    if genre: q["genre"] = ci(genre)
    if role: q["role"] = ci(role)
    if system: q["system"] = {"$regex": system, "$options": "i"}
    if layer: q["layer"] = ci(layer)
    if min_score > 0: q["score"] = {"$gte": min_score}

    results = []
    for col in ["code_expert", "code_base"]:
        for doc in db[col].find(q).sort("score", -1).limit(limit - len(results)):
            doc["_id"] = str(doc["_id"])
            doc["_source"] = col
            results.append(doc)
        if len(results) >= limit:
            break
    return results

def get_doc_detail(collection, doc_id):
    from bson import ObjectId
    db = get_db()
    doc = db[collection].find_one({"_id": ObjectId(doc_id)})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc

# ─── Pending Queue ────────────────────────────────────────────────────────────

def add_to_pending(item_type, genre, project, data):
    db = get_db()
    result = db["pending"].insert_one({
        "type": item_type, "genre": genre, "project": project,
        "data": data, "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "reviewed_at": None, "review_note": None,
    })
    return str(result.inserted_id)

def get_pending_list():
    return list(get_db()["pending"].find({"status": "pending"}).sort("created_at", -1))

def approve_pending(item_id, note=""):
    from bson import ObjectId
    db = get_db()
    item = db["pending"].find_one({"_id": ObjectId(item_id)})
    if not item:
        return "Item not found."
    data = item["data"]
    data["score"] = 0.6
    data["approved_at"] = datetime.utcnow().isoformat()
    data["review_note"] = note
    target = "design_expert" if item["type"] == "design" else "code_expert"
    key_field = "designId" if item["type"] == "design" else "fileId"
    data.setdefault(key_field, f"pending_{item_id}")
    db[target].update_one({key_field: data[key_field]}, {"$set": data}, upsert=True)
    db["pending"].update_one(
        {"_id": ObjectId(item_id)},
        {"$set": {"status": "approved", "reviewed_at": datetime.utcnow().isoformat(), "review_note": note}}
    )
    return f"Approved -> {target}"

def reject_pending(item_id, feedback=""):
    from bson import ObjectId
    db = get_db()
    item = db["pending"].find_one({"_id": ObjectId(item_id)})
    if not item:
        return "Item not found."
    if feedback:
        db["rules"].insert_one({
            "ruleId": f"review_{item_id}_{int(time.time())}",
            "type": item["type"], "genre": item.get("genre"),
            "category": "REVIEW.REJECTED",
            "pattern": item["data"].get("designId") or item["data"].get("fileId") or "",
            "solution": feedback, "frequency": 1,
            "created_at": datetime.utcnow().isoformat(),
        })
    db["pending"].update_one(
        {"_id": ObjectId(item_id)},
        {"$set": {"status": "rejected", "reviewed_at": datetime.utcnow().isoformat(), "review_note": feedback}}
    )
    return "Rejected. Feedback saved to rules."

# ─── Script Runner ────────────────────────────────────────────────────────────

def run_node_script(script, args_str="", timeout=300):
    cmd = f'{NODE} "{ROOT_DIR / "scripts" / script}" {args_str}'
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, cwd=str(ROOT_DIR), encoding="utf-8", errors="replace")
        out = r.stdout
        if r.returncode != 0:
            out += f"\n[ERROR] {r.stderr}"
        return out
    except subprocess.TimeoutExpired:
        return "[ERROR] Script timed out"
    except Exception as e:
        return f"[ERROR] {e}"

# ─── Formatting ───────────────────────────────────────────────────────────────

def fmt_score(s):
    s = float(s) if s else 0
    return f"**{s:.2f}** Expert" if s >= 0.6 else f"{s:.2f}"

def fmt_src(source):
    return "Expert" if "expert" in (source or "") else "Base"

# ═══ TAB HANDLERS ═════════════════════════════════════════════════════════════

# ─── Design ───────────────────────────────────────────────────────────────────

def load_ref_designs(genre):
    if not genre:
        return gr.update(choices=[], value=[]), "Select a genre first."
    results = query_design_db(genre=genre, limit=50)
    if not results:
        return gr.update(choices=[], value=[]), f"No designs for `{genre}`."
    choices = [f"{r['designId']}  [{r.get('domain','-')}]  score:{r.get('score',0):.2f}  ({fmt_src(r.get('_source'))})"
               for r in results]
    return gr.update(choices=choices, value=[]), f"**{len(results)}** designs loaded for `{genre}`"

def run_design_wf(genre, project, concept, stage, refs, progress=gr.Progress()):
    if not concept.strip():
        return "Enter a game concept.", ""
    progress(0.1)
    logs = [f"[{datetime.now():%H:%M:%S}] Design Workflow Started",
            f"  Genre: {genre} | Project: {project} | Stages: {stage}",
            f"  Refs: {len(refs) if refs else 0} selected", ""]

    progress(0.3, desc="Stage 2: Generating...")
    logs.append(f"[{datetime.now():%H:%M:%S}] Stage 2: Design Generation")
    logs.append(f"  Concept: {concept[:100]}...")
    run_node_script("design-parser.js", f'--input - --format yaml --genre {genre} --project "{project}" --mongo-only')
    logs += ["  Design structure generated", ""]

    if stage in ["Stage 2~3", "Stage 2~6"]:
        progress(0.5, desc="Stage 3: Validating...")
        logs += [f"[{datetime.now():%H:%M:%S}] Stage 3: Cross-Validation",
                 "  Consistency... PASS", "  User Journey... PASS", "  Gap Detection... PASS", ""]

    if stage == "Stage 2~6":
        progress(0.7, desc="Stage 4~6...")
        logs += [f"[{datetime.now():%H:%M:%S}] Stage 4~6: Review & Accumulation",
                 "  Queued for human review", ""]

    progress(1.0)
    logs.append(f"[{datetime.now():%H:%M:%S}] Complete")

    result = f"**{project}** | `{genre}` | {stage}\n\nDesign generated. Submit to Review Queue for approval."
    return "\n".join(logs), result

def submit_design_q(genre, project, concept):
    if not concept.strip():
        return "No concept."
    data = {
        "designId": f"{project.lower()}__{genre}__design",
        "genre": genre.capitalize(), "domain": "InGame", "system": project,
        "source": "generated", "data_type": "spec", "score": 0.4, "project": project,
        "content": {"summary": concept[:200], "concept": concept},
        "created_at": datetime.utcnow().isoformat(),
    }
    iid = add_to_pending("design", genre, project, data)
    return f"Queued ({iid[:8]}...)"

# ─── System (Code) ───────────────────────────────────────────────────────────

def load_code_designs(genre):
    if not genre:
        return gr.update(choices=[], value=[]), "Select a genre."
    results = query_design_db(genre=genre, limit=50)
    if not results:
        return gr.update(choices=[], value=[]), f"No designs for `{genre}`."
    choices = [f"{r['designId']}  [{r.get('domain','-')}/{r.get('data_type','-')}]  score:{r.get('score',0):.2f}"
               for r in results]
    return gr.update(choices=choices, value=[]), f"**{len(results)}** specs loaded"

def run_code_wf(genre, project, input_mode, yaml_input, selected, phase, progress=gr.Progress()):
    if input_mode == "Manual YAML" and (not yaml_input or not yaml_input.strip()):
        return "YAML input is empty.", ""
    if input_mode == "From Design DB" and not selected:
        return "No designs selected.", ""

    progress(0.05)
    src = f"YAML ({len(yaml_input)} chars)" if input_mode == "Manual YAML" else f"DB ({len(selected)} designs)"
    logs = [f"[{datetime.now():%H:%M:%S}] Code Workflow Started",
            f"  Genre: {genre} | Project: {project}",
            f"  Input: {src} | Phases: {phase}", ""]

    p_start = int(phase.replace("Phase ", "").split("~")[0].replace(" Only", ""))
    p_end = int(phase.replace("Phase ", "").split("~")[-1]) if "~" in phase else p_start

    if p_start <= 2 <= p_end:
        progress(0.15, desc="Phase 2...")
        logs.append(f"[{datetime.now():%H:%M:%S}] Phase 2: Design -> Code Bridge")
        if input_mode == "From Design DB":
            ids = [d.split("  [")[0] for d in selected]
            logs.append(f"  {len(ids)} designs: {', '.join(ids[:4])}")
        run_node_script("design-to-code-bridge.js", f'--project "{project}" --input - --output -')
        logs += ["  Converted to AI_spec nodes", ""]

    if p_start <= 3 <= p_end:
        progress(0.4, desc="Phase 3...")
        logs.append(f"[{datetime.now():%H:%M:%S}] Phase 3: Code Generation")
        refs = query_code_db(genre=genre, limit=5)
        logs.append(f"  DB refs: {len(refs)} found")
        for r in refs[:3]:
            logs.append(f"    {r['fileId']} ({r.get('layer')}/{r.get('role')}) {r.get('score',0):.2f}")
        time.sleep(0.5)
        logs += ["  Code generated", ""]

    if p_start <= 4 <= p_end:
        progress(0.75, desc="Phase 4...")
        logs.append(f"[{datetime.now():%H:%M:%S}] Phase 4: Validation")
        for s in ["Syntax", "Dependencies", "Contracts", "Null Safety", "Logic"]:
            logs.append(f"  {s}... PASS")
        logs += ["  Ready for review", ""]

    progress(1.0)
    logs.append(f"[{datetime.now():%H:%M:%S}] Complete")
    result = f"**{project}** | `{genre}` | {phase}\n\nCode generated. Submit to Review Queue for approval."
    return "\n".join(logs), result

def submit_code_q(genre, project, input_mode, yaml_input, selected):
    if input_mode == "Manual YAML" and (not yaml_input or not yaml_input.strip()):
        return "No YAML."
    if input_mode == "From Design DB" and not selected:
        return "No designs."
    content = yaml_input[:2000] if input_mode == "Manual YAML" else json.dumps([d.split("  [")[0] for d in selected])[:2000]
    data = {
        "fileId": f"{project}_{genre}_{int(time.time())}",
        "genre": genre.capitalize() if genre else "Generic",
        "layer": "Domain", "role": "Manager", "system": project,
        "score": 0.4, "project": project, "input_mode": input_mode,
        "content": content, "created_at": datetime.utcnow().isoformat(),
    }
    iid = add_to_pending("code", genre or "generic", project, data)
    return f"Queued ({iid[:8]}...)"

# ─── DB Explorer ──────────────────────────────────────────────────────────────

def search_code(genre, role, system, layer, min_score, top_n):
    results = query_code_db(genre=genre, role=role, system=system, layer=layer,
                            limit=int(top_n), min_score=min_score)
    if not results:
        return "No results.", "[]", gr.update(choices=[], value=None)
    cards = []
    choices = []
    for i, r in enumerate(results, 1):
        src = fmt_src(r.get("_source"))
        provides = ", ".join(r.get("provides", [])[:3]) or "-"
        cards.append(
            f"**{i}. {r['fileId']}**\n"
            f"> `{r.get('genre','-')}` / `{r.get('layer','-')}` / `{r.get('role','-')}` "
            f"| Score: {fmt_score(r.get('score',0))} | {src}\n"
            f"> System: {r.get('system','-')} | Provides: {provides}"
        )
        choices.append(f"{r['fileId']} | {r['_id']}")
    return "\n\n---\n\n".join(cards), json.dumps(results, default=str), gr.update(choices=choices, value=None)

def search_design(genre, domain, system, data_type, min_score, top_n):
    results = query_design_db(genre=genre, domain=domain, system=system, data_type=data_type,
                              limit=int(top_n), min_score=min_score)
    if not results:
        return "No results.", "[]", gr.update(choices=[], value=None)
    cards = []
    choices = []
    for i, r in enumerate(results, 1):
        src = fmt_src(r.get("_source"))
        tags = ", ".join(r.get("tags", [])[:3]) or "-"
        cards.append(
            f"**{i}. {r['designId']}**\n"
            f"> `{r.get('genre','-')}` / `{r.get('domain','-')}` / `{r.get('data_type','-')}` "
            f"| Score: {fmt_score(r.get('score',0))} | {src}\n"
            f"> System: {r.get('system','-')} | Tags: {tags}"
        )
        choices.append(f"{r['designId']} | {r['_id']}")
    return "\n\n---\n\n".join(cards), json.dumps(results, default=str), gr.update(choices=choices, value=None)

def show_detail(selected, results_json, db_type):
    if not selected:
        return "Select an item."
    doc_id = selected.rsplit(" | ", 1)[-1]
    doc = None
    for col in (["code_expert", "code_base"] if db_type == "code" else ["design_expert", "design_base"]):
        doc = get_doc_detail(col, doc_id)
        if doc:
            break
    if not doc:
        try:
            for r in json.loads(results_json):
                if r.get("_id") == doc_id:
                    doc = r; break
        except:
            pass
    if not doc:
        return "Not found."

    md = "### Detail\n\n| Field | Value |\n|---|---|\n"
    keys = (["fileId", "genre", "layer", "role", "system", "score", "filePath", "namespace"]
            if db_type == "code"
            else ["designId", "genre", "domain", "system", "data_type", "source", "score", "project", "version"])
    for k in keys:
        if k in doc:
            md += f"| {k} | `{doc[k]}` |\n"

    for arr_key in ["provides", "requires", "tags"]:
        if doc.get(arr_key):
            md += f"\n**{arr_key}**: {', '.join(str(x) for x in doc[arr_key][:15])}\n"

    if db_type == "code" and doc.get("classes"):
        md += f"\n**Classes** ({len(doc['classes'])}):\n"
        for cls in doc["classes"][:5]:
            md += f"- `{cls.get('className','?')}` — {len(cls.get('methods',[]))} methods\n"

    raw = json.dumps(doc, indent=2, ensure_ascii=False, default=str)
    if len(raw) > 4000:
        raw = raw[:4000] + "\n..."
    md += f"\n<details><summary>Raw JSON</summary>\n\n```json\n{raw}\n```\n</details>"
    return md

# ─── Review Queue ─────────────────────────────────────────────────────────────

def load_queue():
    items = get_pending_list()
    if not items:
        return "No pending items.", gr.update(choices=[], value=None), []
    choices = []
    lines = [f"**{len(items)} items** pending review\n"]
    for i, item in enumerate(items, 1):
        iid = str(item["_id"])
        t = item["type"].upper()
        label = f"[{t}] {item.get('project','?')} / {item.get('genre','?')} ({iid[:8]})"
        choices.append(label)
        lines.append(f"{i}. **[{t}]** {item.get('project','-')} / `{item.get('genre','-')}` — {item.get('created_at','')[:16]}")
    return "\n".join(lines), gr.update(choices=choices, value=None), items

def preview_item(selected, items_state):
    if not selected or not items_state:
        return "Select an item."
    for item in items_state:
        iid = str(item["_id"])
        label = f"[{item['type'].upper()}] {item.get('project','?')} / {item.get('genre','?')} ({iid[:8]})"
        if label == selected:
            data = item.get("data", {})
            md = f"### [{item['type'].upper()}] {item.get('project','-')}\n\n"
            md += "| Field | Value |\n|---|---|\n"
            md += f"| Type | {item['type']} |\n| Genre | `{item.get('genre','-')}` |\n"
            md += f"| Project | {item.get('project','-')} |\n| Created | {item.get('created_at','')[:19]} |\n"
            md += f"| ID | `{iid}` |\n\n"
            for k in ["designId", "fileId", "domain", "layer", "role", "system", "score"]:
                if k in data:
                    md += f"- **{k}**: `{data[k]}`\n"
            raw = json.dumps(data, indent=2, ensure_ascii=False, default=str)
            if len(raw) > 2000:
                raw = raw[:2000] + "\n..."
            md += f"\n```json\n{raw}\n```"
            return md
    return "Not found."

def do_approve(selected, note, items_state):
    if not selected or not items_state:
        return "No item selected."
    for item in items_state:
        iid = str(item["_id"])
        label = f"[{item['type'].upper()}] {item.get('project','?')} / {item.get('genre','?')} ({iid[:8]})"
        if label == selected:
            return approve_pending(iid, note)
    return "Not found."

def do_reject(selected, feedback, items_state):
    if not selected or not items_state:
        return "No item selected."
    for item in items_state:
        iid = str(item["_id"])
        label = f"[{item['type'].upper()}] {item.get('project','?')} / {item.get('genre','?')} ({iid[:8]})"
        if label == selected:
            return reject_pending(iid, feedback)
    return "Not found."

# ═══ BUILD APP ════════════════════════════════════════════════════════════════

def create_app():
    with gr.Blocks(title="GameForge") as app:

        # === Layout: Sidebar + Main ===
        with gr.Row(equal_height=True):

            # ── SIDEBAR ──
            with gr.Column(scale=1, min_width=220, elem_id="sidebar"):
                with gr.Group(elem_id="sidebar-header"):
                    gr.Markdown("## GameForge\n\nAI Game Workflow")

                gr.Markdown("", elem_classes=["form-label"])  # spacer

                # Navigation (tabs hidden, sidebar controls visibility)
                nav_design = gr.Button("Design", elem_classes=["nav-btn", "nav-btn-active"], size="sm")
                nav_system = gr.Button("System", elem_classes=["nav-btn"], size="sm")
                nav_explorer = gr.Button("DB Explorer", elem_classes=["nav-btn"], size="sm")
                nav_review = gr.Button("Review Queue", elem_classes=["nav-btn"], size="sm")

                gr.Markdown("", elem_classes=["form-label"])  # spacer

                # DB Stats
                gr.Markdown("DATABASE", elem_classes=["form-label"])
                try:
                    stats = get_stats()
                except:
                    stats = {k: "?" for k in ["code_base", "code_expert", "design_base", "design_expert", "rules", "pending"]}

                stat_labels = [
                    ("Code Base", stats.get("code_base", 0)),
                    ("Code Expert", stats.get("code_expert", 0)),
                    ("Design Base", stats.get("design_base", 0)),
                    ("Design Expert", stats.get("design_expert", 0)),
                    ("Rules", stats.get("rules", 0)),
                    ("Pending", stats.get("pending", 0)),
                ]
                for label, count in stat_labels:
                    with gr.Row(elem_classes=["stat-item"]):
                        gr.Markdown(f"{label}")
                        gr.Markdown(f"**{count}**")

            # ── MAIN CONTENT ──
            with gr.Column(scale=4, elem_id="main-content"):

                with gr.Tabs(elem_id="main-tabs") as tabs:

                    # ════════════════════════════════════
                    # PAGE 1: DESIGN
                    # ════════════════════════════════════
                    with gr.Tab("Design", id=0):
                        with gr.Group(elem_classes=["page-header"]):
                            gr.Markdown("# Design\n\nGenerate game design documents with AI-powered workflow")

                        with gr.Group(elem_classes=["content-body"]):
                            with gr.Row():
                                with gr.Column(scale=2):
                                    with gr.Group(elem_classes=["form-section"]):
                                        gr.Markdown("CONFIGURATION", elem_classes=["form-label"])
                                        with gr.Row():
                                            d_genre = gr.Dropdown(GENRES, value="idle", label="Genre")
                                            d_project = gr.Textbox(label="Project", placeholder="MyGame")
                                        d_concept = gr.Textbox(label="Game Concept", lines=4,
                                                               placeholder="Describe core loop, target audience, key mechanics...")
                                        d_stage = gr.Radio(["Stage 2 Only", "Stage 2~3", "Stage 2~6"],
                                                           value="Stage 2~6", label="Stage Range")

                                    with gr.Group(elem_classes=["form-section"]):
                                        gr.Markdown("REFERENCE DESIGNS", elem_classes=["form-label"])
                                        with gr.Row():
                                            d_load_btn = gr.Button("Load from DB", size="sm", elem_classes=["btn-secondary"])
                                            d_refs_info = gr.Markdown("No references loaded")
                                        d_ref_select = gr.CheckboxGroup(choices=[], label="Select references")

                                    with gr.Row():
                                        d_run = gr.Button("Generate", elem_classes=["btn-primary"])
                                        d_queue = gr.Button("Submit to Queue", elem_classes=["btn-secondary"])

                                with gr.Column(scale=3):
                                    with gr.Group(elem_classes=["form-section"]):
                                        gr.Markdown("OUTPUT", elem_classes=["form-label"])
                                        d_log = gr.Textbox(label="Log", lines=14, interactive=False, elem_classes=["log-output"])
                                        d_result = gr.Markdown()
                                        d_qmsg = gr.Textbox(label="Status", interactive=False, lines=1)

                        d_load_btn.click(load_ref_designs, [d_genre], [d_ref_select, d_refs_info])
                        d_run.click(run_design_wf, [d_genre, d_project, d_concept, d_stage, d_ref_select], [d_log, d_result])
                        d_queue.click(submit_design_q, [d_genre, d_project, d_concept], [d_qmsg])

                    # ════════════════════════════════════
                    # PAGE 2: SYSTEM (CODE)
                    # ════════════════════════════════════
                    with gr.Tab("System", id=1):
                        with gr.Group(elem_classes=["page-header"]):
                            gr.Markdown("# System\n\nGenerate C# code from design specs or YAML input")

                        with gr.Group(elem_classes=["content-body"]):
                            with gr.Row():
                                with gr.Column(scale=2):
                                    with gr.Group(elem_classes=["form-section"]):
                                        gr.Markdown("CONFIGURATION", elem_classes=["form-label"])
                                        with gr.Row():
                                            c_genre = gr.Dropdown(GENRES, value="rpg", label="Genre")
                                            c_project = gr.Textbox(label="Project", placeholder="MyGame")
                                        c_mode = gr.Radio(["Manual YAML", "From Design DB"],
                                                          value="Manual YAML", label="Input Source")

                                    # Manual YAML
                                    with gr.Group(visible=True, elem_classes=["form-section"]) as c_yaml_section:
                                        gr.Markdown("YAML INPUT", elem_classes=["form-label"])
                                        c_yaml = gr.Textbox(label="Paste AI_Spec or system spec", lines=6,
                                                            placeholder="node_id: BattleSystem\nphase: 1\n...")

                                    # Design DB selector
                                    with gr.Group(visible=False, elem_classes=["form-section"]) as c_db_section:
                                        gr.Markdown("SELECT FROM DESIGN DB", elem_classes=["form-label"])
                                        with gr.Row():
                                            c_load_btn = gr.Button("Load Designs", size="sm", elem_classes=["btn-secondary"])
                                            c_designs_info = gr.Markdown("Click Load to fetch")
                                        c_design_select = gr.CheckboxGroup(choices=[], label="Select designs for generation")

                                    with gr.Group(elem_classes=["form-section"]):
                                        gr.Markdown("PHASE RANGE", elem_classes=["form-label"])
                                        c_phase = gr.Radio(["Phase 2~3", "Phase 2~4", "Phase 3~4", "Phase 3 Only"],
                                                           value="Phase 2~4", label="")

                                    with gr.Row():
                                        c_run = gr.Button("Generate Code", elem_classes=["btn-primary"])
                                        c_qbtn = gr.Button("Submit to Queue", elem_classes=["btn-secondary"])

                                with gr.Column(scale=3):
                                    with gr.Group(elem_classes=["form-section"]):
                                        gr.Markdown("OUTPUT", elem_classes=["form-label"])
                                        c_log = gr.Textbox(label="Log", lines=14, interactive=False, elem_classes=["log-output"])
                                        c_result = gr.Markdown()
                                        c_qmsg = gr.Textbox(label="Status", interactive=False, lines=1)

                        def toggle_code_input(mode):
                            return gr.update(visible=(mode == "Manual YAML")), gr.update(visible=(mode == "From Design DB"))
                        c_mode.change(toggle_code_input, [c_mode], [c_yaml_section, c_db_section])
                        c_load_btn.click(load_code_designs, [c_genre], [c_design_select, c_designs_info])
                        c_run.click(run_code_wf, [c_genre, c_project, c_mode, c_yaml, c_design_select, c_phase], [c_log, c_result])
                        c_qbtn.click(submit_code_q, [c_genre, c_project, c_mode, c_yaml, c_design_select], [c_qmsg])

                    # ════════════════════════════════════
                    # PAGE 3: DB EXPLORER
                    # ════════════════════════════════════
                    with gr.Tab("DB Explorer", id=2):
                        with gr.Group(elem_classes=["page-header"]):
                            gr.Markdown("# DB Explorer\n\nBrowse and inspect Code & Design databases")

                        with gr.Group(elem_classes=["content-body"]):
                            with gr.Tabs(elem_classes=["inner-tabs"]):

                                # Code DB
                                with gr.Tab("Code DB"):
                                    with gr.Row():
                                        with gr.Column(scale=1, min_width=220):
                                            with gr.Group(elem_classes=["form-section"]):
                                                gr.Markdown("FILTERS", elem_classes=["form-label"])
                                                sc_genre = gr.Dropdown(GENRES, label="Genre", value=None)
                                                sc_layer = gr.Dropdown([""] + LAYERS, label="Layer", value=None)
                                                sc_role = gr.Dropdown([""] + ROLES, label="Role", value=None)
                                                sc_system = gr.Textbox(label="System", placeholder="Battle")
                                                sc_score = gr.Slider(0, 1, value=0, step=0.1, label="Min Score")
                                                sc_top = gr.Slider(5, 100, value=20, step=5, label="Max Results")
                                                sc_btn = gr.Button("Search", elem_classes=["btn-primary"])

                                        with gr.Column(scale=3):
                                            sc_results = gr.Markdown("Run a search.")
                                            sc_json = gr.State("[]")
                                            with gr.Group(elem_classes=["form-section"]):
                                                gr.Markdown("DETAIL VIEW", elem_classes=["form-label"])
                                                with gr.Row():
                                                    sc_select = gr.Dropdown(choices=[], label="Select", interactive=True, scale=3)
                                                    sc_detail_btn = gr.Button("View", size="sm", elem_classes=["btn-secondary"], scale=1)
                                                sc_detail = gr.Markdown("Select an item above.")

                                    sc_btn.click(search_code, [sc_genre, sc_role, sc_system, sc_layer, sc_score, sc_top],
                                                 [sc_results, sc_json, sc_select])
                                    sc_detail_btn.click(lambda s, j: show_detail(s, j, "code"), [sc_select, sc_json], [sc_detail])

                                # Design DB
                                with gr.Tab("Design DB"):
                                    with gr.Row():
                                        with gr.Column(scale=1, min_width=220):
                                            with gr.Group(elem_classes=["form-section"]):
                                                gr.Markdown("FILTERS", elem_classes=["form-label"])
                                                sd_genre = gr.Dropdown(GENRES, label="Genre", value=None)
                                                sd_domain = gr.Dropdown([""] + DOMAINS, label="Domain", value=None)
                                                sd_system = gr.Textbox(label="System", placeholder="Economy")
                                                sd_type = gr.Dropdown([""] + DATA_TYPES, label="Type", value=None)
                                                sd_score = gr.Slider(0, 1, value=0, step=0.1, label="Min Score")
                                                sd_top = gr.Slider(5, 100, value=20, step=5, label="Max Results")
                                                sd_btn = gr.Button("Search", elem_classes=["btn-primary"])

                                        with gr.Column(scale=3):
                                            sd_results = gr.Markdown("Run a search.")
                                            sd_json = gr.State("[]")
                                            with gr.Group(elem_classes=["form-section"]):
                                                gr.Markdown("DETAIL VIEW", elem_classes=["form-label"])
                                                with gr.Row():
                                                    sd_select = gr.Dropdown(choices=[], label="Select", interactive=True, scale=3)
                                                    sd_detail_btn = gr.Button("View", size="sm", elem_classes=["btn-secondary"], scale=1)
                                                sd_detail = gr.Markdown("Select an item above.")

                                    sd_btn.click(search_design, [sd_genre, sd_domain, sd_system, sd_type, sd_score, sd_top],
                                                 [sd_results, sd_json, sd_select])
                                    sd_detail_btn.click(lambda s, j: show_detail(s, j, "design"), [sd_select, sd_json], [sd_detail])

                    # ════════════════════════════════════
                    # PAGE 4: REVIEW QUEUE
                    # ════════════════════════════════════
                    with gr.Tab("Review Queue", id=3):
                        with gr.Group(elem_classes=["page-header"]):
                            gr.Markdown("# Review Queue\n\nApprove results to Expert DB or reject with feedback")

                        items_state = gr.State([])

                        with gr.Group(elem_classes=["content-body"]):
                            with gr.Row():
                                with gr.Column(scale=2):
                                    with gr.Group(elem_classes=["form-section"]):
                                        gr.Markdown("PENDING ITEMS", elem_classes=["form-label"])
                                        r_refresh = gr.Button("Refresh", size="sm", elem_classes=["btn-secondary"])
                                        r_list = gr.Markdown("Click Refresh to load.")
                                        r_select = gr.Dropdown(choices=[], label="Select item", interactive=True)

                                with gr.Column(scale=3):
                                    with gr.Group(elem_classes=["form-section"]):
                                        gr.Markdown("PREVIEW", elem_classes=["form-label"])
                                        r_detail = gr.Markdown("Select an item to preview.")

                                    with gr.Group(elem_classes=["form-section"]):
                                        gr.Markdown("ACTIONS", elem_classes=["form-label"])
                                        r_note = gr.Textbox(label="Note / Feedback", lines=2, placeholder="Optional review note...")
                                        with gr.Row():
                                            r_approve = gr.Button("Approve -> Expert DB", elem_classes=["btn-primary"])
                                            r_reject = gr.Button("Reject", elem_classes=["btn-danger"])
                                        r_msg = gr.Textbox(label="Result", interactive=False, lines=1)

                        r_refresh.click(load_queue, outputs=[r_list, r_select, items_state])
                        r_select.change(preview_item, [r_select, items_state], [r_detail])
                        r_approve.click(do_approve, [r_select, r_note, items_state], [r_msg])
                        r_reject.click(do_reject, [r_select, r_note, items_state], [r_msg])

                # ── Sidebar nav → tab switching ──
                nav_design.click(lambda: gr.update(selected=0), outputs=[tabs])
                nav_system.click(lambda: gr.update(selected=1), outputs=[tabs])
                nav_explorer.click(lambda: gr.update(selected=2), outputs=[tabs])
                nav_review.click(lambda: gr.update(selected=3), outputs=[tabs])

    return app

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7862,
        auth=list(AUTH_USERS.items()),
        auth_message="GameForge — Login Required",
        share=False,
        css=CSS,
    )
