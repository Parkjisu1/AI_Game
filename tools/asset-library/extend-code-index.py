"""Include legacy editor sources in the same full-source semantic compilation."""
import collections,hashlib,json,pathlib,subprocess
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data';tool=pathlib.Path(__file__).parent
before={x['id']:x for x in (json.loads(line) for line in (data/'code-nodes.jsonl').open(encoding='utf8'))}
nodes={};edges={};issues=[];summaries=[]
for platform in ['UNITY_EDITOR','UNITY_ANDROID','UNITY_IOS']:
 out=data/('all-'+platform);out.mkdir(exist_ok=True)
 subprocess.run(['dotnet',str(tool/'CodeIndexer/bin/Release/net10.0/CodeIndexer.dll'),str(data/'code-all-files.jsonl'),str(out),platform],check=True)
 for line in (out/'code-nodes.jsonl').open(encoding='utf8'):
  d=json.loads(line)
  if d['id'] not in nodes:d['configurations']=[];nodes[d['id']]=d
  nodes[d['id']]['configurations'].append(platform)
 for line in (out/'code-edges.jsonl').open(encoding='utf8'):
  d=json.loads(line);key=(d['from'],d.get('to'),d['relation'],d['line'],d.get('resolution'),d.get('expression'))
  if key not in edges:d['configurations']=[];edges[key]=d
  edges[key]['configurations'].append(platform)
 for line in (out/'code-parse-issues.jsonl').open(encoding='utf8'):
  d=json.loads(line);d['configuration']=platform;issues.append(d)
 summaries.append(json.loads((out/'code-index-summary.json').read_text()))
missing=set(before)-set(nodes)
if missing:raise RuntimeError('Previously indexed nodes disappeared: '+str(len(missing)))
extra=[d for id,d in nodes.items() if id not in before or d['content_hash']!=before[id]['content_hash'] or d.get('embedding_text')!=before[id].get('embedding_text') or d.get('configurations')!=before[id].get('configurations')]
for name,rows in [('code-extra-nodes.jsonl',extra),('code-nodes.jsonl',nodes.values()),('code-edges.jsonl',edges.values()),('code-parse-issues.jsonl',issues)]:
 p=data/name;tmp=p.with_suffix('.tmp')
 with tmp.open('w',encoding='utf8') as f:
  for d in rows:f.write(json.dumps(d,ensure_ascii=False)+'\n')
 tmp.replace(p)
s={'source_files':summaries[0]['source_files'],'nodes':len(nodes),'edges':len(edges),'unresolved_edges':sum(x['resolution']=='unresolved' for x in edges.values()),'member_reference_edges':sum(x['relation']=='references_member' for x in edges.values()),'type_reference_edges':sum(x['relation']=='references_type' for x in edges.values()),'syntax_errors':sum(x['syntax_errors'] for x in summaries),'supplementary_upserts':len(extra),'configurations':['UNITY_EDITOR','UNITY_ANDROID','UNITY_IOS'],'parser':'Roslyn SDK 10','semantics':'source + .NET references; Unity/external assemblies and custom defines unverified'}
(data/'code-index-summary.json').write_text(json.dumps(s,indent=2));print('EXTENDED',s,flush=True)
