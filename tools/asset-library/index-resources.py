"""Retain legacy structured game data by JSON subtree / CSV record, not character cuts."""
import csv,hashlib,io,json,pathlib
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data';nodes=[];issues=[]
def sha(s):return hashlib.sha256(s.encode()).hexdigest()
for d in (json.loads(x) for x in (data/'code-resource-files.jsonl').open(encoding='utf8')):
 name=pathlib.Path(d['source_path']).name
 if name.startswith('google-services'):
  issues.append({'source_path':d['source_path'],'status':'excluded_sensitive_service_config'});continue
 text=pathlib.Path(d['archive_path']).read_text(encoding='utf-8-sig');ext=pathlib.Path(name).suffix.lower()
 context=f"Project: {d['project']}\nFile: {d['source_path']}\nResource configuration; not executable code.\n"
 def emit(pointer,content,kind,parent=None,container=False):
  id=sha(d['id']+'|'+pointer);input=context+pointer+'\n'+content
  if container:input=context+'Container '+pointer+'; retrieve structured children and original source.'
  n={**d,'id':id,'parent_id':parent,'symbol':name+pointer,'name':name+pointer,'kind':kind,'source_file_id':d['id'],'source_pointer':pointer,'content':content,'content_hash':sha(content),'embedding_text':input if len(input)<=7000 else None,'status':'parsed' if len(input)<=7000 else 'oversize_structured_atom','representation':'structured_serialization' if ext=='.json' else 'source_document','runtime_verified':False,'binding_scope':'non-executable resource data; no C# semantic binding'};nodes.append(n);return id
 try:
  if ext=='.json':
   value=json.loads(text)
   def walk(v,pointer,parent):
    content=json.dumps(v,ensure_ascii=False,indent=2);split=len(context+content+pointer)>7000 and isinstance(v,(dict,list));id=emit(pointer,content,'JsonContainer' if split else 'JsonValue',parent,split)
    if split:
     for k,child in (v.items() if isinstance(v,dict) else enumerate(v)):walk(child,pointer+'/'+str(k).replace('~','~0').replace('/','~1'),id)
   walk(value,'',None)
  elif ext=='.csv':
   rows=list(csv.reader(io.StringIO(text)));parent=emit('',text,'CsvDocument',container=len(text)>6000)
   if len(text)>6000:
    for i,row in enumerate(rows[1:],2):emit('/record/'+str(i),json.dumps({'header':rows[0],'row':row},ensure_ascii=False),'CsvRecord',parent)
  else:emit('',text,'TextDocument')
 except (ValueError,csv.Error) as e:issues.append({'source_path':d['source_path'],'status':'structured_parse_failed','error_type':type(e).__name__})
for filename in ['code-extra-nodes.jsonl','code-nodes.jsonl']:
 p=data/filename;existing=[json.loads(x) for x in p.open(encoding='utf8')];by={x['id']:x for x in existing};by.update({x['id']:x for x in nodes});tmp=p.with_suffix('.tmp')
 with tmp.open('w',encoding='utf8') as f:
  for n in by.values():f.write(json.dumps(n,ensure_ascii=False)+'\n')
 tmp.replace(p)
s=data/'code-index-summary.json';summary=json.loads(s.read_text());summary['resource_nodes']=len(nodes);summary['resource_files']=len({x['source_file_id'] for x in nodes});summary['nodes']=len(by);s.write_text(json.dumps(summary,indent=2))
(data/'resource-index-report.json').write_text(json.dumps({'nodes':len(nodes),'issues':issues},ensure_ascii=False,indent=2),encoding='utf8');print('Resource nodes',len(nodes),'issues',len(issues))
