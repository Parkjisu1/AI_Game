"""Content-addressed raw source snapshots for reproducible retrieval."""
import hashlib,io,json,pathlib,tarfile,time
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data';files={};manifest=[]
for name in ['code-all-files.jsonl','code-resource-files.jsonl','art-assets.jsonl']:
 for line in (data/name).open(encoding='utf8'):
  d=json.loads(line)
  if not d.get('source_hash'):continue
  path=d.get('original_archive_path') or d.get('archive_path') or d.get('source_path')
  if pathlib.Path(d.get('source_path','')).name.startswith('google-services'):continue
  key='sources/'+d['source_hash'];files.setdefault(key,(path,d['source_hash']))
  manifest.append({'id':d['id'],'project':d['project'],'source_path':d['source_path'],'source_hash':d['source_hash'],'artifact_key':key,'encoding':d.get('encoding'),'kind':d.get('kind'),'preview':d.get('preview')})
for p in (root/'previews').glob('*.png'):files['previews/'+p.name]=(str(p),None)
archive=root/'source-artifacts.tar';tmp=archive.with_suffix('.partial');total=0
with tarfile.open(tmp,'w') as tar:
 for i,(key,(path,expected)) in enumerate(files.items()):
  raw=pathlib.Path(path).read_bytes()
  if expected and hashlib.sha256(raw).hexdigest()!=expected:raise RuntimeError('Source changed while archiving: '+path)
  item=tarfile.TarInfo(key);item.size=len(raw);item.mode=0o600;tar.addfile(item,io.BytesIO(raw));total+=len(raw)
  if (i+1)%5000==0:print('archived',i+1,'files',round(total/1e9,2),'GB',flush=True)
 body=''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in manifest).encode();item=tarfile.TarInfo('manifest.jsonl');item.size=len(body);item.mode=0o600;tar.addfile(item,io.BytesIO(body))
tmp.replace(archive)
h=hashlib.sha256()
with archive.open('rb') as f:
 for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
report={'archive':str(archive),'sha256':h.hexdigest(),'files':len(files),'source_records':len(manifest),'payload_bytes':total,'archive_bytes':archive.stat().st_size,'at':time.time()}
(data/'source-archive.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
