"""Build evidence-linked project knowledge; source catalog and game projects remain read-only."""
import argparse,collections,datetime,hashlib,json,os,pathlib,re,sqlite3
ROOT=pathlib.Path('E:/AI/output/asset-library-v2')
EXCLUDE={'.git','Library','Temp','obj','bin','Logs','node_modules','.vs'}
HEX=re.compile(r'^[a-f0-9]{64}$')
GUID=re.compile(r'guid:\s*([a-f0-9]{32})')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8',newline='\n')
def read(p,limit=16*1024*1024):
 if not p.is_file():return None,'missing'
 if p.stat().st_size>limit:return None,'size_limit'
 try:return p.read_bytes(),None
 except OSError:return None,'unreadable'
def decode(raw):
 for enc in ('utf-8-sig','utf-16' if raw[:2] in (b'\xff\xfe',b'\xfe\xff') else 'cp949'):
  try:return raw.decode(enc)
  except UnicodeError:pass
 return None
def evidence(p,raw,**more):return {'file':str(p),'sha256':digest(raw),**more}
def source(d):
 h=d.get('source_hash','')
 if not HEX.fullmatch(h):return None,'invalid_hash',None
 paths=[ROOT/'sources'/h,ROOT/'sources'/(h+'.original')]
 name=pathlib.PureWindowsPath(d.get('original_archive_path') or d.get('archive_path','')).name
 if name.startswith(h+'.') and re.fullmatch(r'[a-f0-9]{64}\.[a-zA-Z0-9._-]+',name):paths.append(ROOT/'sources'/name)
 p=next((p for p in paths if p.is_file()),None)
 if p is None:return None,'missing',None
 raw,err=read(p,32*1024*1024)
 if err:return None,err,p
 return (raw,None,p) if digest(raw)==h else (None,'hash_mismatch',p)
def usable(d,domain):return d.get('source_scope')!='historical' and d.get('status') not in ('historical_source_recovered','source_missing','sprite_rect_out_of_bounds') and (domain!='code' or d.get('status')=='parsed')
def walk(root):
 for parent,dirs,files in os.walk(root,followlinks=False):
  dirs[:]=sorted(x for x in dirs if x not in EXCLUDE and not pathlib.Path(parent,x).is_symlink())
  for f in sorted(files):
   p=pathlib.Path(parent,f)
   if not p.is_symlink():yield p

def unity_info(root,arts):
 result={'root':str(root),'runtimeVerified':False,'snapshot':'current_worktree_observation; separate from indexed snapshot','coverage':{'referenceFileLimit':60,'serializedFileMaxBytes':16*1024*1024},'evidence':[]}
 version=root/'ProjectSettings/ProjectVersion.txt';raw,err=read(version)
 if raw:
  text=decode(raw) or '';m=re.search(r'^m_EditorVersion:\s*(.+)$',text,re.M);result['editorVersion']=m.group(1).strip() if m else None;result['evidence'].append(evidence(version,raw))
 packages=root/'Packages/manifest.json';raw,err=read(packages)
 if raw:
  try:
   deps=json.loads(raw).get('dependencies',{});result['packages']={k:v if re.fullmatch(r'[0-9A-Za-z.+_-]+',str(v)) else 'non-registry dependency; location omitted' for k,v in deps.items()};result['evidence'].append(evidence(packages,raw))
  except ValueError:result['packagesError']='invalid_json'
 files=list(walk(root/'Assets'));result['assetFiles']=len(files)
 result['extensions']=dict(collections.Counter(p.suffix.lower() for p in files))
 result['resourceFolders']=dict(collections.Counter(str(p.relative_to(root)).replace('\\','/').split('/Resources/')[0]+'/Resources' for p in files if '/Resources/' in str(p).replace('\\','/') and p.suffix!='.meta'))
 index=collections.defaultdict(list);meta_by={}
 for p in files:
  if p.suffix!='.meta':continue
  try:
   with p.open('rb') as f:head=f.read(4096)
  except OSError:continue
  m=re.search(rb'^guid:\s*([a-f0-9]{32})',head,re.M)
  if m:index[m.group(1).decode()].append(str(p)[:-5]);meta_by[str(p)[:-5]]={'file':str(p),'guid':m.group(1).decode(),'line':head[:m.start()].count(b'\n')+1}
 result['guidCount']=len(index);result['duplicateGuids']=[{'guid':g,'paths':p} for g,p in index.items() if len(p)>1]
 result['assemblyDefinitions']=[];result['contracts']=[]
 for p in files:
  if p.suffix=='.asmdef':
   raw,err=read(p)
   if raw:
    try:
     d=json.loads(raw);result['assemblyDefinitions'].append(evidence(p,raw,name=d.get('name'),references=d.get('references',[]),includePlatforms=d.get('includePlatforms',[])))
    except ValueError:pass
  if p.name in ('_ARCHITECTURE.md','_CONTRACTS.yaml','_ASSET_MANIFEST.yaml'):
   raw,err=read(p)
   if raw:result['contracts'].append(evidence(p,raw,status='present_not_semantically_validated'))
 for name in ('_ARCHITECTURE.md','_CONTRACTS.yaml','_ASSET_MANIFEST.yaml'):
  p=root/name;raw,err=read(p)
  if raw:result['contracts'].append(evidence(p,raw,status='present_not_semantically_validated'))
 build=root/'ProjectSettings/EditorBuildSettings.asset';raw,err=read(build);scenes=[]
 if raw:
  text=decode(raw) or '';result['evidence'].append(evidence(build,raw));enabled=None
  for ln,line in enumerate(text.splitlines(),1):
   m=re.search(r'- enabled:\s*(\d)',line)
   if m:enabled=m.group(1)=='1'
   m=re.search(r'^\s*path:\s*(Assets/.+\.unity)\s*$',line)
   if m:
    path=m.group(1).strip();scene=root/path
    scenes.append({'path':path,'enabled':enabled,'exists':scene.is_file(),'settingsLine':ln,'guid':meta_by.get(str(scene),{}).get('guid')})
 if raw and not (decode(raw) or '').startswith('%YAML'):
  try:
   import UnityPy
   objects=UnityPy.load(raw).objects
   settings=next(o.read_typetree() for o in objects if o.type.name=='EditorBuildSettings')
   scenes=[{'path':x['path'],'enabled':bool(x['enabled']),'exists':(root/x['path']).is_file(),'evidenceFormat':'binary_typetree','settingsObject':'EditorBuildSettings.m_Scenes','guid':meta_by.get(str(root/x['path']),{}).get('guid')} for x in settings.get('m_Scenes',[])]
   result['buildSettingsFormat']='binary_typetree'
  except Exception as e:result['buildSettingsError']='binary_not_decoded:'+type(e).__name__
 elif raw:result['buildSettingsFormat']='unity_text_yaml'
 else:result['buildSettingsError']=err
 result['buildScenes']=scenes
 # Current build profiles can override legacy scene lists; inventory separately.
 result['buildProfiles']=[str(p.relative_to(root)) for p in files if 'BuildProfiles' in str(p) and p.suffix=='.asset']
 candidates=[root/s['path'] for s in scenes]
 if not candidates:candidates=sorted(p for p in files if p.suffix=='.unity')[:10]
 candidates += [pathlib.Path(u['file']) for d in arts for u in d.get('uses',[]) if u.get('file') and pathlib.Path(u['file']).suffix in ('.prefab','.controller','.unity')]
 seen=set();selected=[]
 for p in candidates:
  resolved=p.resolve()
  if not resolved.is_relative_to(root.resolve()) or resolved in seen:continue
  seen.add(resolved);selected.append(p)
 result['coverage']['candidateReferenceFiles']=len(selected);selected=selected[:60]
 result['serializedFiles']=[];result['scriptAttachments']=[];result['resourceReferences']=[]
 for p in selected:
  raw,err=read(p)
  if err:result['serializedFiles'].append({'file':str(p),'status':err});continue
  text=decode(raw)
  if text is None or not text.startswith('%YAML'):result['serializedFiles'].append(evidence(p,raw,status='not_unity_text_yaml'));continue
  result['serializedFiles'].append(evidence(p,raw,status='current_text_read'))
  file_hash=digest(raw);doc='';owner=None;names={};pending=[]
  for ln,line in enumerate(text.splitlines(),1):
   m=re.match(r'--- !u!\d+ &(-?\d+)',line)
   if m:doc=m.group(1);owner=None
   m=re.match(r'  m_Name: (.*)',line)
   if m:names[doc]=m.group(1)
   m=re.match(r'  m_GameObject: \{fileID: (-?\d+)\}',line)
   if m:owner=m.group(1)
   g=GUID.search(line)
   if not g:continue
   guid=g.group(1);paths=index.get(guid,[]);field=line.strip().split(':',1)[0].lstrip('- ')
   item={'file':str(p),'fileHash':file_hash,'line':ln,'objectId':doc,'gameObjectId':owner,'field':field,'guid':guid,'targets':paths,'resolution':'unique_current_guid' if len(paths)==1 else 'duplicate_guid' if paths else 'guid_not_in_assets','runtimeVerified':False}
   if field=='m_Script':pending.append(item)
   elif len(result['resourceReferences'])<100 and len(paths)==1:result['resourceReferences'].append(item)
  for item in pending:item['gameObjectName']=names.get(item['gameObjectId']);result['scriptAttachments'].append(item)
 result['coverage']['referenceFilesSelected']=len(selected)
 result['coverage']['serializedCoverage']='all configured build scenes first, then indexed usage files; bounded to 60; references are static observations, not complete runtime graph'
 return result

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=pathlib.Path,required=True);args=ap.parse_args();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True);(out/'projects').mkdir(exist_ok=True)
 registry=json.loads((ROOT/'data/projects.json').read_text(encoding='utf-8'))
 db=sqlite3.connect((ROOT/'catalog.sqlite').as_uri()+'?mode=ro',uri=True);db.execute('BEGIN')
 projects=[x[0] for x in db.execute('select distinct project from assets order by project')]
 edges=collections.defaultdict(collections.Counter)
 for project,rel,res,n in db.execute("select json_extract(data,'$.project'),relation,resolution,count(*) from edges group by 1,2,3"):edges[project][rel+' / '+res]=n
 cards=[];manifest=[]
 for project in projects:
  print('BUILD',project,flush=True)
  rows=[(domain,json.loads(data)) for domain,data in db.execute('select domain,data from assets where project=?',(project,))]
  code=[d for domain,d in rows if domain=='code' and usable(d,domain)];art=[d for domain,d in rows if domain=='art' and usable(d,domain)]
  card={'project':project,'genreStatus':'imported_unreviewed; mixed code-unit tags do not establish game genre','genreTags':dict(collections.Counter(d.get('genre','unclassified') for _,d in rows)),'catalogCounts':dict(collections.Counter(domain for domain,_ in rows)),'eligibleCounts':{'code':len(code),'art':len(art)},'codeKinds':dict(collections.Counter(d.get('kind') for d in code)),'artKinds':dict(collections.Counter(d.get('kind') for d in art)),'relations':dict(edges[project]),'successStatus':'unknown_no_project_outcome_evidence','runtimeVerified':False,'codeFiles':[],'codeExamples':[],'recordedArtUses':sum(len(d.get('uses',[])) for d in art),'artExamples':[],'unity':[]}
  unique={}
  for d in code:unique.setdefault((d.get('source_path'),d.get('source_hash')),d)
  validhash={};verified_text={}
  for key,d in unique.items():
   raw,err,p=source(d);text=decode(raw) if raw else None
   f={k:d.get(k) for k in ('source_path','source_hash','archive_path','version')};f.update(snapshotVerified=err is None,error=err,readPath=str(p) if p else None)
   card['codeFiles'].append(f)
   if raw and text:verified_text[d['source_path']]=(text, d['source_hash'])
  card['codeContentHashMismatches']=sum(digest(d.get('content','').encode('utf-8'))!=d.get('content_hash') for d in code)
  candidates=[d for d in code if d.get('kind') in ('ClassDeclaration','MethodDeclaration') and re.search(r'Bootstrap|AppInitialize|GameBoard|GameRule|GameManager|ResourceManager|PoolManager|LevelManager|BattleManager|PlayableBootstrap|PixelArt',d.get('symbol',''))]
  # Prefer small members in multiple files; separate selection from full inventory.
  picked=set()
  for d in sorted(candidates,key=lambda d:(0 if d.get('kind')=='MethodDeclaration' and re.search(r'\.((Start|Awake|Init|Load|Run)\w*)\(',d.get('symbol','')) else 1,len(d.get('content','')))):
   if d['source_path'] in picked or d['source_path'] not in verified_text:continue
   picked.add(d['source_path']);body=d.get('content','');card['codeExamples'].append({k:d.get(k) for k in ('id','symbol','kind','source_path','source_hash','content_hash','line_start','line_end')}|{'body':body[:6000],'bodyTruncated':len(body)>6000,'snapshotVerified':True})
   if len(picked)>=10:break
  signals=collections.defaultdict(list)
  patterns={'resource_load':r'Resources\.(Load|LoadAll)|Addressables\.|AssetBundle','scene_transition':r'SceneManager\.LoadScene|Application\.LoadLevel','events':r'EventBus\.(Publish|Subscribe|Unsubscribe)','pooling':r'CreatePool\(|ObjectPool|PoolManager','data_asset':r'ScriptableObject|CreateAssetMenu','lifecycle':r'RuntimeInitializeOnLoadMethod|void\s+(Awake|Start|OnEnable|OnDisable)\(','onboarding':r'FTUE|Tutorial|Onboarding','monetization_measurement':r'LogEvent\(|TrackEvent\(|Rewarded|IAP|Purchase'}
  for path,(text,h) in verified_text.items():
   for ln,line in enumerate(text.splitlines(),1):
    for kind,pattern in patterns.items():
     if len(signals[kind])<35 and re.search(pattern,line):signals[kind].append({'file':path,'sourceHash':h,'line':ln,'text':line.strip()[:350],'interpretation':'literal_source_signal_not_semantic_or_runtime_proof'})
  card['implementationSignals']=dict(signals)
  for d in sorted(art,key=lambda d:(not bool(d.get('uses')),d.get('name','')))[:12]:
   card['artExamples'].append({k:d.get(k) for k in ('id','name','kind','source_path','source_hash','guid','import_settings','status','width','height','purpose','editable_structure_status')}|{'uses':d.get('uses',[])[:4],'totalUses':len(d.get('uses',[])),'evidenceState':'catalog_metadata; current use recheck is separate'})
  for path in registry.get(project,{}).get('roots',[]):
   p=pathlib.Path(path)
   if p.is_dir():card['unity'].append(unity_info(p,art))
   else:card['unity'].append({'root':path,'status':'unavailable'})
  # Recheck DB-recorded use-file hashes against current Unity files, without replacing old evidence.
  checks={}
  for d in art:
   for u in d.get('uses',[]):
    key=(u.get('file'),u.get('source_hash'))
    if key in checks or not key[0]:continue
    p=pathlib.Path(key[0]);roots=[pathlib.Path(x).resolve() for x in registry.get(project,{}).get('roots',[])]
    if not any(p.resolve().is_relative_to(x) for x in roots):checks[key]='outside_registered_project';continue
    raw,err=read(p)
    checks[key]=err or ('match' if digest(raw)==key[1] else 'changed')
  card['recordedUseFileChecks']=dict(collections.Counter(checks.values()))
  card['recordedUseFileFailures']=[{'file':k[0],'indexedHash':k[1],'status':v} for k,v in checks.items() if v!='match']
  card['learningRoute']=['Read this project card and genre uncertainty first.','Follow verified codeExamples and exact source units; explain behavior and dependencies.','Follow current buildScenes -> scriptAttachments -> source file, then resourceReferences/GUID and recorded art uses.','Keep indexed snapshot and current Unity observation separate; stop mixed-version claims on changed hashes.','State reusable mechanism, project-specific assumptions, required assets and counterexamples.','Read separate success-knowledge.json; do not label this project commercially successful without outcome evidence.']
  path=out/'projects'/(project+'.json');save(path,card);cards.append(card)
  manifest.append({'project':project,'path':str(path.relative_to(out)),'sha256':digest(path.read_bytes()),'codeFiles':len(card['codeFiles']),'verifiedCodeFiles':sum(x['snapshotVerified'] for x in card['codeFiles']),'unityRoots':len(card['unity'])})
 planning=db.execute('select status,count(*),sum(length(body)) from planning group by status').fetchall();db.close()
 save(out/'manifest.json',{'schemaVersion':1,'builtAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'catalog':str(ROOT/'catalog.sqlite'),'catalogMode':'read-only SQLite transaction','meaning':'derived retrieval knowledge, not model weight training','projectCount':len(cards),'projects':manifest,'planning':planning,'limits':['Code and art classifications imported unreviewed','Current Unity observations are not the indexed commit','No model, Unity or performance experiment executed','Serialized scan bounded; dynamic loads and imported packages may be unresolved']})
 print('DONE',len(cards),'projects',sum(x['verifiedCodeFiles'] for x in manifest),'verified code file identities',flush=True)
if __name__=='__main__':main()