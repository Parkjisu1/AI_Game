import collections,json,pathlib,subprocess,sys
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data';tool=pathlib.Path(__file__).parent
subprocess.run([sys.executable,str(tool/'recover-encoding.py')],check=True)
subprocess.run(['dotnet','build',str(tool/'CodeIndexer/CodeIndexer.csproj'),'-c','Release','--nologo','-v','quiet'],check=True)
nodes={};edges={};issues={};summaries=[]
for platform in ['UNITY_EDITOR','UNITY_ANDROID','UNITY_IOS']:
 out=data/platform;out.mkdir(exist_ok=True)
 subprocess.run(['dotnet',str(tool/'CodeIndexer/bin/Release/net10.0/CodeIndexer.dll'),str(data/'code-files.jsonl'),str(out),platform],check=True)
 for line in (out/'code-nodes.jsonl').read_text(encoding='utf8').splitlines():
  d=json.loads(line)
  if d['id'] not in nodes:d['configurations']=[];nodes[d['id']]=d
  nodes[d['id']]['configurations'].append(platform)
 for line in (out/'code-edges.jsonl').read_text(encoding='utf8').splitlines():
  d=json.loads(line);key=(d['from'],d.get('to'),d['relation'],d['line'],d.get('resolution'),d.get('expression'))
  if key not in edges:d['configurations']=[];edges[key]=d
  edges[key]['configurations'].append(platform)
 for line in (out/'code-parse-issues.jsonl').read_text(encoding='utf8').splitlines():
  d=json.loads(line);d['configuration']=platform;issues[json.dumps(d,sort_keys=True)]=d
 summaries.append(json.loads((out/'code-index-summary.json').read_text()))
for filename,values in [('code-nodes.jsonl',nodes.values()),('code-edges.jsonl',edges.values()),('code-parse-issues.jsonl',issues.values())]:
 with (data/filename).open('w',encoding='utf8') as f:
  for d in values:f.write(json.dumps(d,ensure_ascii=False)+'\n')
summary={'source_files':summaries[0]['source_files'],'nodes':len(nodes),'edges':len(edges),'unresolved_edges':sum(x.get('resolution')=='unresolved' for x in edges.values()),'syntax_errors':sum(x['syntax_errors'] for x in summaries),'configurations':['UNITY_EDITOR','UNITY_ANDROID','UNITY_IOS'],'parser':'Roslyn SDK 10','semantics':'source + .NET references; external Unity binding and custom defines unverified'}
(data/'code-index-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
print('MERGED',json.dumps(summary),flush=True)
subprocess.run([sys.executable,'-u',str(tool/'embed.py'),'code'],check=True)
