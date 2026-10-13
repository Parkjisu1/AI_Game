"""Verify every registered source hash and every generated preview without altering originals."""
import collections,hashlib,json,pathlib,time
from PIL import Image
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data';errors=[];counts=collections.Counter();checked={}
def digest(path):
 p=pathlib.Path(path)
 if str(p) not in checked:
  h=hashlib.sha256()
  with p.open('rb') as f:
   for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
  checked[str(p)]=h.hexdigest()
 return checked[str(p)]
for filename in ['code-all-files.jsonl','code-resource-files.jsonl']:
 for line in (data/filename).open(encoding='utf8'):
  d=json.loads(line);path=d.get('original_archive_path') or d['archive_path']
  if digest(path)!=d['source_hash']:errors.append({'kind':'code_archive_hash_mismatch','path':path})
  else:counts['code_archives_verified']+=1
  if d.get('encoding') not in [None,'utf-8-sig']:
   a=pathlib.Path(path).read_bytes().decode(d['encoding']);b=pathlib.Path(d['archive_path']).read_bytes().decode('utf-8-sig')
   if a!=b:errors.append({'kind':'encoding_conversion_changed_text','path':path})
for filename in ['art-assets.jsonl','art-components.jsonl']:
 for i,line in enumerate((data/filename).open(encoding='utf8')):
  d=json.loads(line)
  if d.get('source_hash'):
   try:
    if digest(d['source_path'])!=d['source_hash']:errors.append({'kind':'art_source_changed','id':d['id'],'path':d['source_path']})
    else:counts['art_source_records_verified']+=1
   except OSError:errors.append({'kind':'art_source_unavailable','id':d['id']})
  if d.get('preview'):
   try:
    with Image.open(root/'previews'/d['preview']) as image:image.verify()
    counts['previews_verified']+=1
   except Exception as e:errors.append({'kind':'preview_decode_failed','id':d['id'],'type':type(e).__name__})
  if (i+1)%5000==0:print(filename,i+1,flush=True)
report={'at':time.time(),'counts':dict(counts),'distinct_files_hashed':len(checked),'errors':errors,'passed':not errors}
(data/'source-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=True),flush=True)
