"""Enrich OOP relations without changing any node IDs or in-flight vectors."""
import json,pathlib,subprocess
root=pathlib.Path('E:/AI/output/asset-library-v2');data=root/'data';tool=pathlib.Path(__file__).parent
subprocess.run(['dotnet','build',str(tool/'CodeIndexer/CodeIndexer.csproj'),'-c','Release','--nologo','-v','quiet'],check=True)
edges={}
for platform in ['UNITY_EDITOR','UNITY_ANDROID','UNITY_IOS']:
 out=data/('relations-'+platform);out.mkdir(exist_ok=True)
 subprocess.run(['dotnet',str(tool/'CodeIndexer/bin/Release/net10.0/CodeIndexer.dll'),str(data/'code-files.jsonl'),str(out),platform],check=True)
 for line in (out/'code-edges.jsonl').open(encoding='utf8'):
  d=json.loads(line);key=(d['from'],d.get('to'),d['relation'],d['line'],d.get('resolution'),d.get('expression'))
  if key not in edges:d['configurations']=[];edges[key]=d
  edges[key]['configurations'].append(platform)
p=data/'code-edges.jsonl';tmp=p.with_suffix('.tmp')
with tmp.open('w',encoding='utf8') as f:
 for d in edges.values():f.write(json.dumps(d,ensure_ascii=False)+'\n')
tmp.replace(p)
s=data/'code-index-summary.json';summary=json.loads(s.read_text());summary.update(edges=len(edges),unresolved_edges=sum(x['resolution']=='unresolved' for x in edges.values()),member_reference_edges=sum(x['relation']=='references_member' for x in edges.values()),type_reference_edges=sum(x['relation']=='references_type' for x in edges.values()));s.write_text(json.dumps(summary,indent=2))
print('RELATIONS',summary,flush=True)
