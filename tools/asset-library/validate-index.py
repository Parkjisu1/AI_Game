"""Exhaustive identity, source-span and graph integrity checks; no production-quality inference."""
import collections,functools,hashlib,json,pathlib,time
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data';errors=[];counts=collections.Counter();nodes={}
@functools.lru_cache(maxsize=64)
def source_utf16(path):return pathlib.Path(path).read_bytes().decode('utf-8-sig').encode('utf-16-le')
for line in (data/'code-nodes.jsonl').open(encoding='utf8'):
 d=json.loads(line);id=d['id']
 if id in nodes:errors.append({'kind':'duplicate_code_id','id':id})
 nodes[id]={'project':d['project'],'parent':d.get('parent_id'),'source_hash':d['source_hash']}
 if hashlib.sha256(d['content'].encode()).hexdigest()!=d['content_hash']:errors.append({'kind':'content_hash_mismatch','id':id})
 if 'start' in d:
  raw=source_utf16(d['archive_path']);span=raw[2*d['start']:2*(d['start']+d['length'])].decode('utf-16-le')
  if span!=d['content']:errors.append({'kind':'source_span_mismatch','id':id})
  counts['exact_code_spans_verified']+=1
 else:counts['structured_resource_units']+=1
 if pathlib.Path(d['source_path']).name.lower().endswith('.local.cs'):errors.append({'kind':'secret_config_in_index','id':id})
 counts['code_nodes']+=1
for id,d in nodes.items():
 if d['parent'] and d['parent'] not in nodes:errors.append({'kind':'missing_code_parent','id':id})
for line in (data/'code-edges.jsonl').open(encoding='utf8'):
 e=json.loads(line);counts['edges']+=1
 if e['from'] not in nodes:errors.append({'kind':'missing_edge_source','id':e['from']})
 if e.get('to'):
  if e['to'] not in nodes:errors.append({'kind':'missing_edge_target','id':e['to']})
  elif nodes[e['from']]['project']!=nodes[e['to']]['project']:errors.append({'kind':'cross_project_edge','id':e['from']})
 if e['resolution']=='unresolved':counts['explicitly_unresolved_edges']+=1
parents={json.loads(x)['id'] for x in (data/'art-assets.jsonl').open(encoding='utf8')}
for line in (data/'art-components.jsonl').open(encoding='utf8'):
 d=json.loads(line);counts['art_components']+=1
 if d['parent_id'] not in parents:errors.append({'kind':'missing_art_parent','id':d['id']})
 if d['status']=='sprite_rect_out_of_bounds':counts['quarantined_art_rectangles']+=1
 for u in d['uses']:
  if u.get('file_id')!=d.get('internal_file_id') or u['guid']!=d['guid']:errors.append({'kind':'subasset_reference_mismatch','id':d['id']})
report={'at':time.time(),'counts':dict(counts),'errors':errors,'passed':not errors,'limitations':['Source + .NET binding only; Unity and external assembly symbols can remain unresolved.','Custom platform defines and runtime reflection are not exhaustively resolved.','Imported genre and feature taxonomy has not been human-reviewed.','These checks do not establish game build or production quality.']}
(data/'index-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=True),flush=True)
