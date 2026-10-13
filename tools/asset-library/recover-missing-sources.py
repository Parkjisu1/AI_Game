"""Recover inspection copies; never restore deleted files into game repositories.
DB reference search: catalog code generic/unclassified GUIDToAssetPath/ResolvePath/
FindAsset => 0 rows. Reuses inventory.py source-ledger conventions.
Historical files stay excluded from active RAG; a legacy ID is not a content hash.
"""
import collections,hashlib,json,pathlib,re,subprocess,time,uuid
from PIL import Image,ImageOps
ROOT=pathlib.Path('E:/AI/output/asset-library-v2');DATA=ROOT/'data'
OUT=ROOT/'source-recovery-20261005';OUT.mkdir(exist_ok=True)
SOURCES=OUT/'sources';SOURCES.mkdir(exist_ok=True)
def git(repo,*args,required=True):
 r=subprocess.run(['git','-c','core.quotepath=false','-C',str(repo),*args],capture_output=True,timeout=45)
 if required and r.returncode:raise RuntimeError('git '+args[0]+' failed')
 return r.stdout if r.returncode==0 else None
def gs(repo,*args,required=True):
 value=git(repo,*args,required=required);return value.decode('utf8').strip() if value is not None else None
def digest(raw):return hashlib.sha256(raw).hexdigest()
def atomic(path,rows):
 temp=path.with_suffix('.tmp');temp.write_text(rows,encoding='utf8',newline='');temp.replace(path)
def main():
 projects=json.loads((DATA/'projects.json').read_text());legacy={}
 for line in (DATA/'mongo-source.jsonl').open(encoding='utf-8-sig'):
  r=json.loads(line);legacy[str(r['doc'].get('_id'))]=r['doc']
 arts=[json.loads(x) for x in (DATA/'art-assets.jsonl').open(encoding='utf8')]
 targets=[{**x,'domain':'art'} for x in arts if x['status']=='source_missing']
 for x in json.loads((DATA/'code-gaps.json').read_text()):
  if x['status']=='source_missing':targets.append({**x,'domain':'code','id':str(uuid.uuid5(uuid.NAMESPACE_URL,'missing-code-source:'+x['legacy_id'])),'kind':'SourceFileHistory','name':pathlib.PureWindowsPath(x['legacy_path']).name})
 root_info={};guid_index={}
 for project in {x['project'] for x in targets}:
  info=projects[project];project_root=pathlib.Path(info['roots'][0]);repo=pathlib.Path(gs(project_root,'rev-parse','--show-toplevel'))
  anchor=info['repositories'][0]['commit'];prefix=project_root.relative_to(repo).as_posix().strip('.')
  root_info[project]=(project_root,repo,anchor,prefix);guids=collections.defaultdict(list)
  if any(legacy[x['legacy_id']].get('guid') for x in targets if x['project']==project):
   for meta in (project_root/'Assets').rglob('*.meta'):
    asset=pathlib.Path(str(meta)[:-5])
    if not asset.is_file():continue
    m=re.search(rb'^guid:\s*([a-f0-9]{32})',meta.read_bytes(),re.M)
    if m:guids[m[1].decode()].append(asset)
  guid_index[project]=guids
 recovered=[];problems=[]
 for i,a in enumerate(targets):
  d=legacy[a['legacy_id']];project_root,repo,anchor,prefix=root_info[a['project']]
  a.update(registration_status='legacy_record_found',original_status=a['status'],current_source_exists=False,source_resolution='unresolved',source_status='unavailable',eligible=False,embedding_status='excluded_source_unavailable',last_source_check=time.time())
  a['resolution']='unresolved';a['recovery_checks']={'project_root':str(project_root),'git_repository':str(repo),'anchor_commit':anchor,'legacy_guid':d.get('guid')}
  try:
   original=d.get('absolute_path') or d.get('path') or d.get('filePath') or d.get('file_path') or a['legacy_path']
   p=pathlib.Path(original);current=None
   if p.is_absolute() and p.is_file():current=p;a['source_resolution']='original_path'
   elif d.get('guid') and len(guid_index[a['project']].get(d['guid'],[]))==1:current=guid_index[a['project']][d['guid']][0];a['source_resolution']='unity_guid'
   if current:
    raw=current.read_bytes();meta=pathlib.Path(str(current)+'.meta');meta_raw=meta.read_bytes() if meta.exists() else None
    a.update(source_scope='current',source_status='current_verified',current_source_exists=True,current_source_path=str(current),source_path=str(current),status='source_recovered_pending_index',embedding_status='pending_reindex')
   else:
    if p.is_absolute():paths=[p.relative_to(repo).as_posix()]
    else:
     tail=original.replace('\\','/');pattern=':(glob)'+(prefix+'/' if prefix else '')+'**/'+tail.rsplit('/',1)[-1]
     history=gs(repo,'log',anchor,'--format=','--name-only','--',pattern)
     paths=sorted({v for v in history.splitlines() if v and (v==tail or v.endswith('/'+tail))})
    a['recovery_checks']['historical_path_candidates']=paths
    if len(paths)!=1:
     a['recovery_reason']='historical_path_ambiguous' if paths else 'historical_path_not_found';recovered.append(a);continue
    rel=paths[0];commit=gs(repo,'log',anchor,'-1','--format=%H','--diff-filter=AM','--',rel)
    if not commit:a['recovery_reason']='no_source_version_at_or_before_anchor';recovered.append(a);continue
    raw=git(repo,'show',commit+':'+rel);blob=gs(repo,'rev-parse',commit+':'+rel)
    calculated=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
    if calculated!=blob:raise ValueError('Git blob verification failed')
    if raw.startswith(b'version https://git-lfs.github.com/spec/'):
     a['recovery_reason']='git_lfs_pointer_without_original';recovered.append(a);continue
    meta_raw=git(repo,'show',commit+':'+rel+'.meta',required=False)
    a.update(source_scope='historical',source_status='historical_only',source_resolution='git_history',status='historical_source_recovered',embedding_status='excluded_historical',git_source={'repository':str(repo),'commit':commit,'path':rel,'blob':blob,'anchor_commit':anchor,'deleted_at_commit':gs(repo,'log',anchor,'-1','--format=%H','--diff-filter=D','--',rel) or None})
   if a['domain']=='code' and re.search(rb'(sk-[A-Za-z0-9_-]{24,}|gh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY)',raw):
    a.update(status='secret_pattern_quarantined',source_status='unavailable',source_path=None,recovery_reason='secret_pattern_quarantined');recovered.append(a);continue
   sha=digest(raw);extension=pathlib.PureWindowsPath(original).suffix.lower();archive=SOURCES/(sha+extension)
   if archive.exists():
    if digest(archive.read_bytes())!=sha:raise ValueError('Archive hash mismatch')
   else:archive.write_bytes(raw)
   a.update(source_hash=sha,archive_path=str(archive),source_path=str(current) if current else str(archive),bytes=len(raw),extension=extension,resolution=a['source_resolution'],image_dimensions=None)
   if meta_raw:
    a['meta_hash']=digest(meta_raw);(SOURCES/(sha+'.meta')).write_bytes(meta_raw);m=re.search(rb'^guid:\s*([a-f0-9]{32})',meta_raw,re.M)
    if m:a['guid']=m[1].decode()
   a['legacy_identity_check']={'same_guid':a.get('guid')==d.get('guid') if d.get('guid') else None,'same_size':len(raw)==d.get('size_bytes') if d.get('size_bytes') is not None else None,'exact_legacy_content_hash_available':False}
   if a['domain']=='art' and extension in {'.png','.jpg','.jpeg','.psd','.tga','.webp','.bmp','.gif','.tif','.tiff'}:
    with Image.open(archive) as im:im.verify()
    with Image.open(archive) as im:
     im.load();a.update(width=im.width,height=im.height,image_dimensions={'width':im.width,'height':im.height,'unit':'px'},content_verification='image_decoded',preview_kind='historical_image' if not current else 'image')
     preview=ImageOps.exif_transpose(im).convert('RGBA');preview.thumbnail((512,512));name=sha+'.png';preview.save(ROOT/'previews'/name);a['preview']=name
   elif a['domain']=='code':
    enc='utf-8-sig'
    try:content=raw.decode(enc)
    except UnicodeError:enc='cp949';content=raw.decode(enc)
    a.update(content=content,content_hash=digest(content.encode()),encoding=enc,content_verification='text_readable_not_compiled',line_start=1,line_end=len(content.splitlines()))
   else:a['content_verification']='file_bytes_verified_format_unverified'
   a['recovery_reason']='current_file_found' if current else 'file_absent_in_working_tree_historical_copy_preserved'
   recovered.append(a)
  except Exception as e:
   a['recovery_error']=type(e).__name__;a['recovery_reason']='recovery_or_decode_failed';problems.append({'id':a['id'],'type':type(e).__name__});recovered.append(a)
  print(i+1,'/',len(targets),a['project'],a.get('source_status'),flush=True)
 atomic(DATA/'source-recovery.jsonl',''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in recovered))
 summary={'at':time.time(),'targets':len(targets),'domains':{domain:dict(collections.Counter(x['source_status'] for x in recovered if x['domain']==domain)) for domain in ['art','code']},'statuses':dict(collections.Counter(x['status'] for x in recovered)),'problems':problems,'original_game_files_modified':False,'active_vectors_changed':False,'identity_limit':'Git path/blob verified; legacy_id alone cannot establish equality with original ingested bytes.'}
 atomic(DATA/'source-recovery-summary.json',json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
