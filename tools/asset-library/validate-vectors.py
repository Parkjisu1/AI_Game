"""Compare every stored vector point's identity and provenance with the source ledger."""
import collections,json,pathlib,requests,time
from embed import point_id,COLLECTIONS,DIGEST,QDRANT
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data';errors=[];reports={}
for domain,files in [('code',['code-nodes.jsonl']),('art',['art-assets.jsonl','art-components.jsonl'])]:
 expected={};skipped=[]
 for filename in files:
  for line in (data/filename).open(encoding='utf8'):
   d=json.loads(line)
   valid=bool(d.get('embedding_text')) and len(d['embedding_text'])<=9000 if domain=='code' else bool(d.get('source_hash')) and d['status'] not in ['image_decode_failed','file_read_failed','image_decoder_unsupported','sprite_rect_out_of_bounds','component_decode_failed']
   if not valid:skipped.append(d['id']);continue
   expected[point_id(d['id'])]={'id':d['id'],'project':d['project'],'hash':d['source_hash'],'visual':bool(d.get('preview'))}
 actual={};offset=None
 while True:
  body={'limit':1000,'with_vector':False,'with_payload':{'include':['original_id','project','source_hash','embedding_model_digest','visual_model','visual_preprocessing','visual_input_hash']}}
  if offset is not None:body['offset']=offset
  r=requests.post(QDRANT+'/collections/'+COLLECTIONS[domain]+'/points/scroll',json=body,timeout=60);r.raise_for_status();result=r.json()['result']
  for p in result['points']:actual[p['id']]=p['payload']
  offset=result['next_page_offset']
  if offset is None:break
 missing=set(expected)-set(actual);extra=set(actual)-set(expected)
 if missing:errors.append({'domain':domain,'kind':'missing_points','count':len(missing),'examples':sorted(missing)[:10]})
 if extra:errors.append({'domain':domain,'kind':'unexpected_points','count':len(extra),'examples':sorted(extra)[:10]})
 for id,e in expected.items():
  p=actual.get(id)
  if not p:continue
  if (p.get('original_id'),p.get('project'),p.get('source_hash'),p.get('embedding_model_digest'))!=(e['id'],e['project'],e['hash'],DIGEST):errors.append({'domain':domain,'kind':'provenance_mismatch','id':id})
  if e['visual'] and (not p.get('visual_model') or 'square padded gray' not in p.get('visual_preprocessing','')):errors.append({'domain':domain,'kind':'visual_encoder_mismatch','id':id})
 config=requests.get(QDRANT+'/collections/'+COLLECTIONS[domain],timeout=30).json()['result']
 sample_checks=[]
 for project in sorted({x['project'] for x in expected.values()}):
  id=next(k for k,v in expected.items() if v['project']==project)
  # Query-by-ID excludes that point itself. Use its actual vector for a true
  # self-similarity check, rather than incorrectly testing its nearest neighbor.
  point=requests.post(QDRANT+'/collections/'+COLLECTIONS[domain]+'/points',json={'ids':[id],'with_vector':['text'],'with_payload':False},timeout=60);point.raise_for_status();vector=point.json()['result'][0]['vector']['text']
  q=requests.post(QDRANT+'/collections/'+COLLECTIONS[domain]+'/points/query',json={'query':vector,'using':'text','limit':1,'params':{'exact':True},'filter':{'must':[{'key':'project','match':{'value':project}}]},'with_payload':['project']},timeout=60);q.raise_for_status();points=q.json()['result']['points']
  okay=bool(points) and points[0]['score']>0.999 and points[0]['payload']['project']==project
  sample_checks.append({'project':project,'self_similarity':points[0]['score'] if points else None,'passed':okay})
  if not okay:errors.append({'domain':domain,'kind':'retrieval_identity_failed','project':project})
 reports[domain]={'expected_points':len(expected),'actual_points':len(actual),'excluded_records':len(skipped),'visual_metadata_count':sum(bool(x.get('visual_model')) for x in actual.values()),'vector_configuration':config['config']['params']['vectors'],'identity_queries':sample_checks}
 print(domain,'expected',len(expected),'actual',len(actual),'errors',len(errors),flush=True)
report={'at':time.time(),'reports':reports,'errors':errors,'passed':not errors,'scope':'All point IDs and provenance. Each vector was dimension/finite-checked before writing; identity queries do not establish semantic relevance or game quality.'}
(data/'vector-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print('VECTOR VALIDATION',report['passed'],flush=True)
