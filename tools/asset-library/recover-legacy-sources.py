"""Reconcile ALL previously indexed sources, including editor code absent in Mongo."""
import collections,hashlib,json,os,pathlib,re,uuid
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data'
current=[json.loads(x) for x in (data/'code-files.jsonl').open(encoding='utf8')];known={(x['project'],x['source_path'].lower()) for x in current}
projects=json.loads((data/'projects.json').read_text());old={};outcomes=[];extra=[];documents=[]
for name in ['legacy-gf_code_chunks_m3-inventory.jsonl','legacy-gf_code_chunks-inventory.jsonl']:
 for line in (data/name).open(encoding='utf8'):
  x=json.loads(line);old[(x['project'],x['path'])]=x
names={}
for project,info in projects.items():
 index=collections.defaultdict(list)
 for base in info['roots']:
  for parent,dirs,files in os.walk(pathlib.Path(base)/'Assets',followlinks=False):
   dirs[:]=[x for x in dirs if x not in {'.git','Library','Temp','obj','bin','node_modules'} and not os.path.islink(os.path.join(parent,x))]
   for f in files:
    if pathlib.Path(f).suffix.lower() in {'.cs','.json','.txt','.csv','.xml'}:index[f.lower()].append(pathlib.Path(parent)/f)
 names[project]=index
for (project,path),legacy in old.items():
 candidates=names.get(project,{}).get(path.replace('\\','/').rsplit('/',1)[-1].lower(),[])
 suffix=[p for p in candidates if p.as_posix().lower().endswith('/'+path.replace('\\','/').lower())]
 matches=suffix if len(suffix)==1 else candidates
 rec={'project':project,'legacy_path':path,'status':'source_missing','candidates':[str(x) for x in matches]}
 if len(matches)!=1:rec['status']='source_ambiguous' if matches else 'source_missing';outcomes.append(rec);continue
 p=matches[0];rec['source_path']=str(p)
 if (project,str(p).lower()) in known:rec['status']='already_indexed';outcomes.append(rec);continue
 if p.name.lower().endswith('.local.cs'):rec['status']='excluded_secret_file';outcomes.append(rec);continue
 raw=p.read_bytes();encoding='utf-8-sig'
 try:text=raw.decode(encoding)
 except UnicodeError:
  encoding='utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'cp949'
  try:
   text=raw.decode(encoding)
   if text.encode(encoding)!=raw:raise ValueError('Nonreversible encoding')
  except (UnicodeError,ValueError):rec['status']='encoding_unverified';outcomes.append(rec);continue
 if re.search(r'(?i)(?:sk-[a-z0-9_-]{24,}|gh[pousr]_[a-z0-9]{30,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY)',text):rec['status']='secret_pattern_quarantined';outcomes.append(rec);continue
 sha=hashlib.sha256(raw).hexdigest();original=root/'sources'/(sha+p.suffix);original.write_bytes(raw);archive=original
 if encoding!='utf-8-sig':archive=root/'sources'/(sha+'.utf8'+p.suffix);archive.write_text(text,encoding='utf8',newline='')
 d={'id':str(uuid.uuid5(uuid.NAMESPACE_URL,'legacy-source:'+project+':'+str(p)+':'+sha)),'project':project,'genre':'unclassified','feature':'unclassified','classification_status':'unreviewed','source_path':str(p),'source_hash':sha,'archive_path':str(archive),'original_archive_path':str(original),'encoding':encoding,'resolution':'exact_suffix' if suffix else 'unique_filename_in_project','legacy_path':path,'provenance':'previous_vector_index_source_inventory','status':'source_preserved'}
 (extra if p.suffix.lower()=='.cs' else documents).append(d);known.add((project,str(p).lower()));rec['status']='recovered_source';outcomes.append(rec)
for filename,rows in [('code-extra-files.jsonl',extra),('code-all-files.jsonl',current+extra),('code-resource-files.jsonl',documents)]:
 with (data/filename).open('w',encoding='utf8') as f:
  for d in rows:f.write(json.dumps(d,ensure_ascii=False)+'\n')
report={'unique_legacy_sources':len(old),'outcome_counts':dict(collections.Counter(x['status'] for x in outcomes)),'additional_code_files':len(extra),'additional_resource_files':len(documents),'outcomes':outcomes}
(data/'legacy-source-reconciliation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print({k:v for k,v in report.items() if k!='outcomes'},flush=True)
