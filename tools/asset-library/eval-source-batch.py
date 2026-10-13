"""Exploratory project-specific lookup: literal source tools vs source + RAG."""
import hashlib,json
from pathlib import Path
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('runner',Path(__file__).with_name('eval-runner.py'));r=module_from_spec(spec);spec.loader.exec_module(r)
root=r.ROOT;task=(root/'source-task.txt').read_text(encoding='utf8')
files=['source-task.txt','source-schema.json','evaluator/source-expected.json']
(root/'source-frozen-inputs.json').write_text(json.dumps({name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files},indent=2))
order=[('astra','source'),('opus','source_rag'),('opus','source'),('astra','source_rag')]
for model,condition in order:
 name=f'lookup-{model}-{condition}'
 if (root/'runs'/name/'run.json').exists():continue
 intro='CONDITION: original-source literal search/list/read only. No vector search is enabled.\n' if condition=='source' else 'CONDITION: same original-source tools PLUS semantic embedding search. Make at least one real search_code call; choose the remaining source/semantic calls yourself.\n'
 print('START',name,flush=True)
 result=r.run(model,condition,name,intro+task,root/'source-schema.json',timeout=480)
 if result['exit_code'] or result.get('is_error') or result.get('errors'):raise SystemExit('Lookup failed: '+name)
