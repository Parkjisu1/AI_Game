"""Versioned source inventory; never changes game files or legacy databases."""
import collections, hashlib, json, os, pathlib, re, subprocess, sys, time, uuid
from PIL import Image, ImageOps

OUT=pathlib.Path('E:/AI/output/asset-library-v2')
DATA=OUT/'data'; DATA.mkdir(parents=True,exist_ok=True)
THUMBS=OUT/'previews'; THUMBS.mkdir(exist_ok=True)
SOURCES=OUT/'sources'; SOURCES.mkdir(exist_ok=True)
def digest(data): return hashlib.sha256(data).hexdigest()
def ident(*args): return str(uuid.uuid5(uuid.NAMESPACE_URL,'asset-library-v2:'+'|'.join(map(str,args))))
def write_json(name,value):
 p=DATA/name;t=p.with_suffix(p.suffix+'.tmp');t.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8');t.replace(p)
rows=[json.loads(x) for x in (DATA/'mongo-source.jsonl').read_text(encoding='utf-8-sig').splitlines() if x.strip()]
by=collections.defaultdict(list)
for r in rows:by[r['collection']].append(r['doc'])
roots=collections.defaultdict(set)
for d in by['art_assets']:
 p=(d.get('absolute_path') or d.get('path') or '').replace('\\','/')
 if '/Assets/' in p:roots[d['project']].add(p.split('/Assets/')[0])
EXCLUDE={'.git','Library','Temp','obj','bin','Logs','node_modules'}
def walk(root):
 for parent,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=sorted(d for d in dirs if d not in EXCLUDE and not os.path.islink(os.path.join(parent,d)))
  for f in sorted(files):
   p=pathlib.Path(parent)/f
   if not p.is_symlink():yield p
project_files={};project_info={};name_index={}
for project,rs in sorted(roots.items()):
 files=[]
 for root in sorted(rs):files.extend(walk(pathlib.Path(root)/'Assets'))
 files=sorted(set(files));project_files[project]=files
 names=collections.defaultdict(list)
 for p in files:names[p.name.lower()].append(p)
 name_index[project]=names
 commits=[]
 for root in sorted(rs):
  r=subprocess.run(['git','-C',root,'rev-parse','HEAD'],capture_output=True,text=True)
  commits.append({'root':root,'commit':r.stdout.strip() if r.returncode==0 else None})
 project_info[project]={'roots':sorted(rs),'files':len(files),'repositories':commits,'snapshot':'working_tree_content_hash; commit_is_context_not_proof_of_clean_tree'}
 print('source_tree',project,len(files),flush=True)
write_json('projects.json',project_info)

guid_indexes={}
def project_guid_index(project):
 if project not in guid_indexes:
  found=collections.defaultdict(list)
  for meta in project_files.get(project,[]):
   if meta.suffix.lower()!='.meta':continue
   asset=pathlib.Path(str(meta)[:-5])
   if not asset.is_file():continue
   match=re.search(rb'^guid:\s*([a-f0-9]{32})',meta.read_bytes(),re.M)
   if match:found[match[1].decode()].append(asset)
  guid_indexes[project]=found
 return guid_indexes[project]
def resolve(d,code=False):
 project=d.get('project','unknown');original=d.get('absolute_path') or d.get('path') or d.get('filePath') or d.get('file_path') or ''
 p=pathlib.Path(original)
 if original and p.is_file():return p,'original_path',[]
 if d.get('guid'):
  matches=project_guid_index(project).get(d['guid'],[])
  if len(matches)==1:return matches[0],'unity_guid',[]
  if len(matches)>1:return None,'ambiguous_guid',[str(p) for p in matches]
 rel=original.replace('\\','/');name=rel.rsplit('/',1)[-1]
 if code and not name:name=str(d.get('fileId',''))+'.cs'
 candidates=name_index.get(project,{}).get(name.lower(),[])
 suffix_path='Assets/'+rel.split('/Assets/',1)[1] if '/Assets/' in rel else rel
 suffix=[p for p in candidates if p.as_posix().lower().endswith('/'+suffix_path.lower())]
 if len(suffix)==1:return suffix[0],'project_relative_path',[]
 if len(candidates)==1:return candidates[0],'unique_filename_in_project',[]
 return None,'ambiguous' if candidates else 'missing',[str(p) for p in candidates]

code=[];code_gaps=[]
for d in by['code_base']+by['code_expert']:
 p,method,candidates=resolve(d,True);project=d.get('project','unknown')
 base={'legacy_id':str(d['_id']),'project':project,'genre':str(d.get('genre') or 'unclassified').lower(),
       'classification_status':'imported_unreviewed','feature':d.get('system') or 'unclassified',
       'feature_evidence':'legacy_metadata','source_path':str(p) if p else None,'legacy_path':d.get('filePath'),
       'resolution':method,'candidate_paths':candidates,'version':project_info.get(project,{}).get('repositories',[])}
 if not p:
  base['status']='source_missing' if method=='missing' else 'source_ambiguous';code_gaps.append(base);continue
 if p.suffix.lower()!='.cs':base['status']='unsupported_language';code_gaps.append(base);continue
 if p.name.lower().endswith('.local.cs'):
  base['status']='excluded_secret_file';code_gaps.append(base);continue
 raw=p.read_bytes();sha=digest(raw)
 try:text=raw.decode('utf-8-sig')
 except UnicodeDecodeError:base['status']='encoding_unverified';code_gaps.append(base);continue
 if re.search(r'(?i)(?:sk-[a-z0-9_-]{24,}|gh[pousr]_[a-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY)',text):
  base['status']='secret_pattern_quarantined';code_gaps.append(base);continue
 archive=SOURCES/(sha+'.cs');archive.write_bytes(raw)
 base.update(source_hash=sha,archive_path=str(archive),id=ident(project,str(p),sha),status='source_preserved')
 code.append(base)
unique={}
for d in code:unique.setdefault((d['project'],d['source_path']),d)
with (DATA/'code-files.jsonl').open('w',encoding='utf8') as f:
 for d in unique.values():f.write(json.dumps(d,ensure_ascii=False)+'\n')
write_json('code-gaps.json',code_gaps)

# Preserve one inventory row for every registered art asset, including failures.
arts=[];guid_art=collections.defaultdict(list);usage_sources={};counts=collections.Counter()
for i,d in enumerate(by['art_assets']):
 p,method,candidates=resolve(d);project=d.get('project','unknown');oldpath=d.get('absolute_path') or d.get('path') or d.get('file_path') or ''
 a={'id':ident('art',str(d['_id'])),'legacy_id':str(d['_id']),'project':project,'genre':str(d.get('genre') or 'unclassified').lower(),
 'classification_status':'imported_unreviewed','name':d.get('file_name') or d.get('name') or pathlib.Path(oldpath).name,
 'kind':d.get('kind') or 'unclassified','source_path':str(p) if p else None,'legacy_path':oldpath,'resolution':method,
 'candidate_paths':candidates,'registered_guid':d.get('guid'),'source_resolution':method,'registration_status':'legacy_record_found','extension':(p.suffix if p else d.get('ext','')).lower(),'usage_status':'not_scanned',
 'purpose':{'value':None,'status':'unconfirmed'},'variant_of':None,'runtime_verified':False,'uses':[],
 'version':project_info.get(project,{}).get('repositories',[]),'width':None,'height':None,'preview':None}
 if not p:a['status']='source_missing' if method=='missing' else 'source_ambiguous'
 else:
  try:
   raw=p.read_bytes();a.update(source_hash=digest(raw),bytes=len(raw),status='file_present_format_unverified')
   meta=pathlib.Path(str(p)+'.meta')
   if meta.is_file():
    mt=meta.read_text(encoding='utf8',errors='replace');m=re.search(r'^guid:\s*([a-f0-9]{32})',mt,re.M)
    if m:a['guid']=m.group(1);guid_art[(project,m.group(1))].append(a)
    settings={}
    for key in ['textureType','spriteMode','spritePixelsToUnits','spritePivot','spriteBorder','maxTextureSize','alphaIsTransparency','sRGBTexture','wrapU','wrapV','filterMode']:
     found=re.search(r'^\s*'+key+r':\s*(.+)$',mt,re.M)
     if found:settings[key]=found.group(1)
    a['import_settings']=settings;a['meta_hash']=digest(meta.read_bytes())
   if a['extension'] in {'.png','.jpg','.jpeg','.tga','.psd','.webp','.bmp','.gif','.tif','.tiff'}:
    try:
     with Image.open(p) as im:im.verify()
     with Image.open(p) as im:
      im.load();a.update(width=im.width,height=im.height,mode=im.mode,format=im.format,frames=1 if a['extension']=='.psd' else getattr(im,'n_frames',1),has_alpha=('A' in im.getbands() or 'transparency' in im.info),status='image_decoded')
      preview=ImageOps.exif_transpose(im).convert('RGBA');preview.thumbnail((512,512))
      name=a['source_hash']+'.png';target=THUMBS/name
      if not target.exists():preview.save(target)
      a['preview']=name;a['preview_kind']='composite' if a['extension']=='.psd' else 'image'
      if a['extension']=='.psd':a['editable_structure_status']='layers_not_verified'
    except (Image.UnidentifiedImageError,NotImplementedError):a['status']='image_decoder_unsupported'
    except Exception as e:a['status']='image_decode_failed';a['error_type']=type(e).__name__
   elif a['extension'] in {'.mat','.shader','.anim','.controller','.prefab','.asset','.spriteatlas','.spriteatlasv2','.shadergraph'}:
    try:raw.decode('utf-8-sig');a['status']='text_asset_readable'
    except UnicodeDecodeError:a['status']='binary_asset_requires_tool'
  except OSError as e:a['status']='file_read_failed';a['error_type']=type(e).__name__
 counts[a['status']]+=1;arts.append(a)
 if (i+1)%1000==0:
  write_json('inventory-progress.json',{'phase':'art_validation','processed':i+1,'total':len(by['art_assets']),'counts':dict(counts)})
  print('art',i+1,dict(counts),flush=True)

REFERENCE_EXTS={'.unity','.prefab','.mat','.asset','.anim','.controller','.overridecontroller','.spriteatlas','.spriteatlasv2','.shadergraph','.vfx'}
ref_re=re.compile(r'guid:\s*([a-f0-9]{32})')
for project,files in project_files.items():
 n=0
 for p in files:
  if p.suffix.lower() not in REFERENCE_EXTS:continue
  try:
   raw=p.read_bytes()
   if len(raw)>32*1024*1024:continue
   text=raw.decode('utf-8-sig')
  except (OSError,UnicodeDecodeError):continue
  source_hash=digest(raw);object_id=None;object_name=None
  for ln,line in enumerate(text.splitlines(),1):
   obj=re.match(r'--- !u!\d+ &(-?\d+)',line)
   if obj:object_id=obj.group(1);object_name=None
   nm=re.match(r'\s*m_Name:\s*(.*)',line)
   if nm:object_name=nm.group(1)
   for match in ref_re.finditer(line):
    targets=guid_art.get((project,match.group(1)),[])
    for a in targets:
     field=line.strip().split(':',1)[0].lstrip('- ')
     a['uses'].append({'file':str(p),'source_hash':source_hash,'line':ln,'object_id':object_id,'object_name_observed':object_name,
       'field':field,'guid':match.group(1),'relation':'serialized_reference','resolution':'exact_guid' if len(targets)==1 else 'duplicate_guid_ambiguous','runtime_verified':False})
     n+=1
 print('usage',project,n,flush=True)
for a in arts:a['usage_status']='references_found' if a['uses'] else 'no_serialized_reference_found' if a.get('guid') else 'guid_unavailable'
with (DATA/'art-assets.jsonl').open('w',encoding='utf8') as f:
 for a in arts:f.write(json.dumps(a,ensure_ascii=False)+'\n')
write_json('inventory-summary.json',{'source_art_records':len(by['art_assets']),'art_records':len(arts),'art_status':dict(counts),
 'code_registered':len(by['code_base'])+len(by['code_expert']),'code_source_files':len(unique),'code_unresolved':len(code_gaps),
 'code_status':dict(collections.Counter(x['status'] for x in code_gaps)),
 'art_with_references':sum(bool(x['uses']) for x in arts),'art_reference_count':sum(len(x['uses']) for x in arts),
 'integrity':'byte_hash_and_decode_checks; no runtime gameplay verification','at':time.time()})
write_json('inventory-progress.json',{'phase':'complete','processed':len(arts),'total':len(arts)})
print('inventory complete',flush=True)
