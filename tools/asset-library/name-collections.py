"""Publish descriptive Qdrant aliases without removing physical legacy indexes."""
import json,pathlib,time,requests
root=pathlib.Path('E:/AI/output/asset-library-v2')
endpoint='http://127.0.0.1:16334'
names={
 'gf_code_chunks_m3':'code_assets_legacy_bgem3',
 'gf_code_chunks':'code_assets_legacy_nomic',
 'art_vectors':'art_assets_legacy_clip',
 'projecthub_3d_knowledge':'art_reference_documents',
 'hermes_text_memory_m3':'work_history_bgem3',
 'hermes_text_memory':'work_history_legacy_nomic',
 'hermes_code_index':'code_index_legacy',
 'task_commit_m3':'task_commit_links',
 'code_assets_v2_20261002':'code_assets',
 'art_assets_v2_20261002':'art_assets',
}
def get(path):
 r=requests.get(endpoint+path,timeout=30);r.raise_for_status();return r.json()['result']
collections={c['name'] for c in get('/collections')['collections']}
aliases={a['alias_name']:a['collection_name'] for a in get('/aliases')['aliases']}
actions=[]
for physical,public in names.items():
 if physical not in collections:continue
 if public in ['code_assets','art_assets']:
  report=json.loads((root/'data'/'vector-validation.json').read_text())
  if not report['passed']:raise RuntimeError('Cannot publish active aliases before vector validation passes')
 if public in collections or (public in aliases and aliases[public]!=physical):raise RuntimeError('Name conflict: '+public)
 if public not in aliases:actions.append({'create_alias':{'collection_name':physical,'alias_name':public}})
if actions:
 r=requests.post(endpoint+'/collections/aliases',json={'actions':actions},timeout=60);r.raise_for_status()
manifest={'at':time.time(),'strategy':'descriptive_public_aliases; original physical indexes retained for rollback','names':names,'old_data_deleted':False}
(root/'collection-names.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
for a in get('/aliases')['aliases']:
 if a['alias_name'] in names.values():print(a['alias_name'],'OK')
