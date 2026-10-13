"""Independent deterministic compiler/runtime checks for frozen task contracts."""
import hashlib,json,pathlib,subprocess,time,re
ROOT=pathlib.Path('E:/AI/output/embedding-eval-20261005')
DOTNET='C:/Program Files/dotnet/dotnet.exe'
PROGRAM=ROOT/'evaluator/Program.cs'
PROJECT='<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>9.0</LangVersion><ImplicitUsings>disable</ImplicitUsings><Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers></PropertyGroup></Project>'
EXPECTED={'TypedEventBus.cs','ReferencePool.cs','RewardLedger.cs'}

def grade(folder):
 text=(folder/'answer.txt').read_text(encoding='utf8').strip()
 if text.startswith('```'): text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
 try:
  answer=json.loads(text);files=answer['files']
  assert len(files)==3 and {x['path'] for x in files}==EXPECTED
 except Exception as error:
  result={'compile_passed':False,'output_error':str(error)}
  (folder/'grade.json').write_text(json.dumps(result,indent=2));return result
 build=folder/'compiled';build.mkdir(exist_ok=True)
 for file in files: (build/file['path']).write_text(file['content'],encoding='utf8')
 (build/'Program.cs').write_bytes(PROGRAM.read_bytes());(build/'Candidate.csproj').write_text(PROJECT,encoding='utf8')
 started=time.perf_counter()
 process=subprocess.run([DOTNET,'run','--project',str(build/'Candidate.csproj'),'-c','Release','--nologo'],cwd=build,capture_output=True,text=True,encoding='utf8',errors='replace',timeout=120)
 (folder/'compile-test.log').write_text(process.stdout+'\n'+process.stderr,encoding='utf8')
 result={'evaluator_sha256':hashlib.sha256(PROGRAM.read_bytes()).hexdigest(),'evaluation_seconds':time.perf_counter()-started,'exit_code':process.returncode,'compile_passed':False,'source_lines':sum(len(f['content'].splitlines()) for f in files)}
 for line in process.stdout.splitlines():
  if line.startswith('{"total":'):result.update(json.loads(line));result['compile_passed']=True
 # Explicit style metrics only, not an invented maintainability score.
 fields=[]
 for f in files:
  for line in f['content'].splitlines():
   match=re.match(r'\s*private\s+(?:(?:static|readonly|const)\s+)*(?:[\w<>,\[\].?]+\s+)+([A-Za-z_]\w*)\s*(?:=|;)',line)
   if match and ' const ' not in line:fields.append({'file':f['path'],'name':match[1],'underscore_prefix':match[1].startswith('_')})
 result['style_private_fields']=fields
 result['style_all_private_fields_underscore']=all(x['underscore_prefix'] for x in fields)
 result['style_forbidden_imports']=[f['path'] for f in files if re.search(r'using\s+(?:UnityEngine|System\.(?:IO|Net|Reflection))',f['content'])]
 (folder/'grade.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
 return result

if __name__=='__main__':
 for folder in sorted((ROOT/'runs').iterdir()):
  if not re.match(r'^(astra|opus)-(baseline|rag)-[12]$',folder.name) or not (folder/'run.json').exists() or not (folder/'answer.txt').exists():continue
  if (folder/'grade.json').exists():continue
  result=grade(folder);print(folder.name,'compile',result.get('compile_passed'),'passed',result.get('passed'),'/',result.get('total'),flush=True)
