"""Resume-safe reindexer. Uses local embedding models and new collections only."""
import argparse,collections,hashlib,json,math,pathlib,sqlite3,time,uuid
import requests

ROOT=pathlib.Path('E:/AI/output/asset-library-v2');DATA=ROOT/'data'
QDRANT='http://127.0.0.1:16334';OLLAMA='http://100.87.87.59:11434'
MODEL='bge-m3:latest';DIGEST='7907646426070047a77226ac3e684fbbe8410524f7b4a74d02837e43f2146bab'
COLLECTIONS={'code':'code_assets_v2_20261002','code_extra':'code_assets_v2_20261002','art':'art_assets_v2_20261002','art_components':'art_assets_v2_20261002'}
def request(method,path,body=None):
 r=requests.request(method,QDRANT+path,json=body,timeout=120);r.raise_for_status();return r.json()
def atomic(path,obj):
 t=path.with_suffix('.tmp');t.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8');t.replace(path)
def point_id(value):return str(uuid.uuid5(uuid.NAMESPACE_URL,'asset-library:'+value))
def main():
 ap=argparse.ArgumentParser();ap.add_argument('kind',choices=list(COLLECTIONS));args=ap.parse_args();kind=args.kind;is_code=kind.startswith('code')
 tags=requests.get(OLLAMA+'/api/tags',timeout=20).json()['models']
 if not any(x['name']==MODEL and x['digest']==DIGEST for x in tags):raise RuntimeError('Embedding model version mismatch')
 coll=COLLECTIONS[kind]
 found=requests.get(QDRANT+'/collections/'+coll,timeout=20)
 vectors={'text':{'size':1024,'distance':'Cosine'}}
 if not is_code:vectors['visual']={'size':512,'distance':'Cosine'}
 if found.status_code==404:request('PUT','/collections/'+coll,{'vectors':vectors,'on_disk_payload':True})
 else:
  found.raise_for_status()
  if found.json()['result']['config']['params']['vectors']!=vectors:
   current=found.json()['result']['config']['params']['vectors']
   if any(current.get(k,{}).get('size')!=v['size'] for k,v in vectors.items()):raise RuntimeError('Collection vector configuration mismatch')
 for field in ['project','genre','kind','class_name','feature','status','source_hash','eligible']:
  request('PUT','/collections/'+coll+'/index?wait=true',{'field_name':field,'field_schema':'bool' if field=='eligible' else 'keyword'})
 cache=sqlite3.connect(DATA/'embedding-cache.sqlite',timeout=60);cache.execute('PRAGMA journal_mode=WAL');cache.execute('CREATE TABLE IF NOT EXISTS vectors (hash TEXT PRIMARY KEY, model TEXT NOT NULL, vector TEXT NOT NULL)');cache.commit()
 state_path=DATA/(kind+'-embedding-state.json')
 state=json.loads(state_path.read_text()) if state_path.exists() else {'kind':kind,'collection':coll,'model':MODEL,'model_digest':DIGEST,'processed':0,'embedded':0,'skipped':0,'errors':[],'complete':False}
 state['complete']=False
 source_file={'code':'code-nodes.jsonl','code_extra':'code-extra-nodes.jsonl','art':'art-assets.jsonl','art_components':'art-components.jsonl'}[kind]
 rows=[json.loads(x) for x in (DATA/source_file).read_text(encoding='utf8').splitlines() if x.strip()]
 model=None;processor=None;torch=None
 if not is_code:
  import torch as torch_module
  from transformers import CLIPModel,CLIPProcessor,CLIPConfig
  torch=torch_module;torch.set_num_threads(4)
  model_path=str(ROOT/'models'/'clip-vit-base-patch32')
  model=CLIPModel(CLIPConfig.from_pretrained(model_path,local_files_only=True))
  weights=torch.load(pathlib.Path(model_path)/'pytorch_model.bin',map_location='cpu',weights_only=True)
  # Older CLIP checkpoints persist deterministic position buffers that newer
  # Transformers regenerates. Validate those exact buffers before omitting them.
  for key,expected in [('text_model.embeddings.position_ids',77),('vision_model.embeddings.position_ids',50)]:
   if key in weights:
    if not torch.equal(weights[key],torch.arange(expected).reshape(1,-1)):raise RuntimeError('Unexpected CLIP position buffer')
    del weights[key]
  model.load_state_dict(weights);del weights
  model=model.to('cuda' if torch.cuda.is_available() else 'cpu').eval()
  processor=CLIPProcessor.from_pretrained(model_path,local_files_only=True)
 state['total']=len(rows);atomic(state_path,state)
 for start in range(state['processed'],len(rows),32):
  batch=rows[start:start+32];items=[]
  for d in batch:
   if d.get('source_scope')=='historical' or d.get('embedding_status') in ['excluded_historical','excluded_source_unavailable']:
    state['skipped']+=1;continue
   if is_code:
    text=d.get('embedding_text');eligible=d.get('status')=='parsed';payload={k:v for k,v in d.items() if k not in ['embedding_text']}
    # Full code remains intact in payload and source snapshot.
   else:
    if not d.get('source_hash') or d['status'] in ['image_decode_failed','file_read_failed','image_decoder_unsupported','sprite_rect_out_of_bounds','component_decode_failed']:
     state['skipped']+=1;continue
    purpose=d.get('purpose',{})
    text='\n'.join([f"Project: {d['project']}",f"Genre: {d['genre']} (imported, unreviewed)",f"Resource: {d['name']}",f"Kind: {d['kind']} / {d['extension']}",f"Source: {d['source_path']}",f"Resolution: {d.get('width')} x {d.get('height')}",f"Purpose: {purpose.get('value') or 'unconfirmed'}",'Observed reference files: '+', '.join(sorted({u['file'] for u in d['uses']})[:12]),'Reference evidence is not runtime verification.'])
    payload=dict(d);eligible=d['status'] in ['image_decoded','text_asset_readable']
   if not text or len(text)>9000:
    state['skipped']+=1;continue
   h=hashlib.sha256((DIGEST+'\n'+text).encode()).hexdigest()
   payload.update(eligible=eligible,embedding_model=MODEL,embedding_model_digest=DIGEST,embedding_input_hash=h,
     embedding_schema=2,indexed_at=time.time(),original_id=d['id'])
   items.append({'source':d,'id':point_id(d['id']),'text':text,'hash':h,'payload':payload,'vector':{}})
  pending=[]
  for item in items:
   hit=cache.execute('SELECT vector FROM vectors WHERE hash=?',(item['hash'],)).fetchone()
   if hit:item['vector']['text']=json.loads(hit[0])
   else:pending.append(item)
  if pending:
   result=None
   for attempt in range(4):
    try:
     r=requests.post(OLLAMA+'/api/embed',json={'model':MODEL,'input':[x['text'] for x in pending],'truncate':False,'keep_alive':'15m'},timeout=180)
     r.raise_for_status();result=r.json()['embeddings'];break
    except (requests.RequestException,KeyError):
     if attempt==3:raise
     time.sleep(2**attempt)
   if len(result)!=len(pending):raise RuntimeError('Embedding batch count mismatch')
   for item,vector in zip(pending,result):
    if len(vector)!=1024 or not all(math.isfinite(x) for x in vector):raise RuntimeError('Invalid embedding vector')
    item['vector']['text']=vector
    cache.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?)',(item['hash'],DIGEST,json.dumps(vector)))
   cache.commit()
  if not is_code:
   from PIL import Image
   visual=[x for x in items if x['source'].get('preview')]
   images=[]
   for item in visual:
    with Image.open(ROOT/'previews'/item['source']['preview']) as image:
     rgba=image.convert('RGBA');side=max(rgba.size);canvas=Image.new('RGB',(side,side),(127,127,127));canvas.paste(rgba,((side-rgba.width)//2,(side-rgba.height)//2),mask=rgba.getchannel('A'));images.append(canvas)
   if images:
    inputs=processor(images=images,return_tensors='pt',input_data_format='channels_last').to(model.device)
    with torch.inference_mode():features=model.get_image_features(**inputs);features=features/features.norm(dim=-1,keepdim=True)
    for item,v in zip(visual,features.cpu().tolist()):
     if len(v)!=512 or not all(math.isfinite(x) for x in v):raise RuntimeError('Invalid visual embedding')
     item['vector']['visual']=v;item['payload']['visual_model']='openai/clip-vit-base-patch32@3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268';item['payload']['visual_preprocessing']='decoded composite; preview max512; square padded gray; channels_last; CLIPProcessor';item['payload']['visual_input_hash']=hashlib.sha256(b'square-pad-v1\n'+(ROOT/'previews'/item['source']['preview']).read_bytes()).hexdigest()
  if items:
   request('PUT','/collections/'+coll+'/points?wait=true',{'points':[{k:x[k] for k in ['id','vector','payload']} for x in items]})
  state['processed']=min(start+len(batch),len(rows));state['embedded']+=len(items);state['updated_at']=time.time();atomic(state_path,state)
  print(kind,state['processed'],'/',len(rows),'indexed',state['embedded'],'skipped',state['skipped'],flush=True)
 state['complete']=True;state['qdrant_points']=request('GET','/collections/'+coll)['result']['points_count'];atomic(state_path,state)
 cache.close()
if __name__=='__main__':
 try:main()
 except Exception as error:
  import sys
  if len(sys.argv)>1:
   p=DATA/(sys.argv[1]+'-embedding-state.json')
   if p.exists():
    s=json.loads(p.read_text());s.update(complete=False,status='failed',error_type=type(error).__name__,error_message=str(error)[:400]);atomic(p,s)
  raise
