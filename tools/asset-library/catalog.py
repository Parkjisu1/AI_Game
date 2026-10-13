"""Build the local inspection catalog from immutable index outputs."""
import json,pathlib,sqlite3,time
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data'
db=sqlite3.connect(root/'catalog.sqlite',timeout=60);db.execute('PRAGMA journal_mode=WAL')
db.executescript('''CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY, domain TEXT, project TEXT, genre TEXT, kind TEXT, name TEXT, feature TEXT, status TEXT, source_path TEXT, parent_id TEXT, data TEXT);
CREATE INDEX IF NOT EXISTS asset_scope ON assets(domain,project,genre,kind);
CREATE INDEX IF NOT EXISTS asset_parent ON assets(parent_id);
CREATE TABLE IF NOT EXISTS edges(id INTEGER PRIMARY KEY, source TEXT,target TEXT,relation TEXT,resolution TEXT,data TEXT);
CREATE INDEX IF NOT EXISTS edge_source ON edges(source);CREATE INDEX IF NOT EXISTS edge_target ON edges(target);
CREATE TABLE IF NOT EXISTS imports(name TEXT PRIMARY KEY,mtime REAL);
CREATE TABLE IF NOT EXISTS planning(id TEXT PRIMARY KEY,title TEXT,project TEXT,genre TEXT,url TEXT,body TEXT,status TEXT,version INTEGER,updated_at TEXT);
''')
def import_file(name,domain):
 p=data/name
 if not p.exists():return
 stamp=p.stat().st_mtime;old=db.execute('SELECT mtime FROM imports WHERE name=?',(name,)).fetchone()
 if old and old[0]==stamp:return
 count=0
 with p.open(encoding='utf8') as f:
  for line in f:
   if not line.strip():continue
   a=json.loads(line);row_domain=domain or a['domain'];db.execute('INSERT OR REPLACE INTO assets VALUES (?,?,?,?,?,?,?,?,?,?,?)',(a['id'],row_domain,a.get('project','unclassified'),a.get('genre','unclassified'),a.get('kind','unknown'),a.get('symbol') or a.get('name') or a['id'],a.get('feature',''),a.get('status','unknown'),a.get('source_path',''),a.get('parent_id'),json.dumps(a,ensure_ascii=False)));count+=1
   if count%1000==0:db.commit()
 db.execute('INSERT OR REPLACE INTO imports VALUES (?,?)',(name,stamp));db.commit();print('catalog',domain,count,flush=True)
import_file('art-assets.jsonl','art');import_file('art-components.jsonl','art');import_file('code-nodes.jsonl','code')
# Recovery overlays are derived separately: do not rewrite the original inventory.
# Reapply after base imports too, so rebuilding the catalog cannot erase provenance.
db.execute('DELETE FROM imports WHERE name=?',('source-recovery.jsonl',));db.commit()
import_file('source-recovery.jsonl',None)
p=data/'code-edges.jsonl';name=p.name
if p.exists():
 stamp=p.stat().st_mtime;old=db.execute('SELECT mtime FROM imports WHERE name=?',(name,)).fetchone()
 if not old or old[0]!=stamp:
  db.execute('DELETE FROM edges') # local derived cache only; never source data
  with p.open(encoding='utf8') as f:
   for i,line in enumerate(f):
    a=json.loads(line);db.execute('INSERT INTO edges(source,target,relation,resolution,data) VALUES (?,?,?,?,?)',(a['from'],a.get('to'),a['relation'],a['resolution'],line.strip()))
    if i%3000==0:db.commit()
  db.execute('INSERT OR REPLACE INTO imports VALUES (?,?)',(name,stamp));db.commit();print('catalog edges imported',flush=True)
db.close()
