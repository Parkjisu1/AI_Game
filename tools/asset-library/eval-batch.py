"""Two counterbalanced repetitions; fixed task/style and isolated candidate runs."""
import hashlib
import json
from pathlib import Path
from importlib.util import spec_from_file_location, module_from_spec

spec=spec_from_file_location('runner',Path(__file__).with_name('eval-runner.py')); runner=module_from_spec(spec);spec.loader.exec_module(runner)
root=runner.ROOT
task=(root/'task.txt').read_text(encoding='utf8')
baseline='CONDITION: STYLE ONLY. Implement all functionality yourself from the contract and supplied style. No existing-source search or reference tools are available. Do not claim to have searched.\n\n'+task
rag='CONDITION: STYLE + EXISTING EMBEDDING LIBRARY. Before implementing, use search_code to search for each of the three components in projects BalloonFlow, NextPR, ARRRM, AshAndVeil. Read at least one full relevant code unit for EACH component when search finds one, preferably its containing class via parent_id. Up to 12 tool calls total. References may lack required edge-case behavior; adapt or reject them. Honor the contract over old implementation. Cite actual returned IDs. No other tools.\n\n'+task
(root/'baseline-prompt.txt').write_text(baseline,encoding='utf8');(root/'rag-prompt.txt').write_text(rag,encoding='utf8')
manifest={'task_sha256':hashlib.sha256(task.encode()).hexdigest(),'repetitions':2,'tasks':3,'generation':'first pass; no hidden tests or feedback; serial runs; high effort each','baseline':'code style + requirements, no original implementation','rag':'same style + requirements + real library MCP','scope':'pure C# gameplay foundations, not complete games or full repository inspection','assumption':'User did not resolve the optional clarification; interpreted full AI work as implementing all functionality from scratch.','rule_exception':'The explicit user-requested no-retrieval comparison overrides db-search.md for baseline candidates only. Benchmark designer searched local DB before preparing tasks.'}
(root/'experiment.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
order=[('astra','baseline',1),('astra','rag',1),('opus','rag',1),('opus','baseline',1),('astra','rag',2),('astra','baseline',2),('opus','baseline',2),('opus','rag',2)]
for model,condition,repeat in order:
 name=f'{model}-{condition}-{repeat}'
 if (root/'runs'/name/'run.json').exists():
  print('EXISTS',name,flush=True);continue
 print('START',name,flush=True)
 result=runner.run(model,condition,name,baseline if condition=='baseline' else rag,root/'output-schema.json')
 if result['exit_code'] or result.get('is_error') or result.get('parse_error') or result.get('errors'):
  raise SystemExit('Candidate run failed; review logs before retrying: '+name)
