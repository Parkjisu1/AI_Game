"""Pin real browser observations and export their complete provenance to a local audit folder."""
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from virtual_player.observers.aggregator import ParameterAggregator
from virtual_player.observers.exporter import DesignDBExporter,DomainGroup
OUT=ROOT/'output/flow-plan-20261006'
raw_path=OUT/'browser/browser-results.json';raw=raw_path.read_bytes();data=json.loads(raw)
assert data['passed']
assert hashlib.sha256((ROOT/'scripts/verify-serares-flow.py').read_bytes()).hexdigest()==data['runner_sha256']
records={'SF_FIRST_MORPH':[],'SF_NEXT_MORPH':[]}
for scenario in data['scenarios']:
 observations={o['step']:o for o in scenario['observations']}
 def level(key):
  return next(int(t['text'][3:]) for t in observations[key]['canvas_text'] if re.fullmatch(r'Lv\.\d+',t['text']))
 for pid,key,before in [('SF_FIRST_MORPH','level-61','initial'),('SF_NEXT_MORPH','level-62','level-61')]:
  capture=observations[key];screen=OUT/'browser'/capture['screenshot']
  assert hashlib.sha256(screen.read_bytes()).hexdigest()==capture['sha256']
  records[pid].append({'observation_id':data['run_id']+':'+scenario['id']+':'+key,
   'observer':scenario['id'],'value':level(key)-level(before),'confidence':0.5,
   'notes':'Uncalibrated selection score only. Same build/harness in different input/viewports, not independent truth authorities.',
   'input':{'mode':scenario['input_mode'],'action':'tap morph menu then transform button'},
   'initial_state':{'visible_level':level(before)},'output':{'visible_level':level(key)},
   'environment':{'viewport':scenario['viewport'],'browser':data['conditions']['browser_version'],'seed':20261006,'build_sha256':data['build_sha256'],'runner_sha256':data['runner_sha256']},
   'evidence_refs':[{'locator':str(screen.relative_to(OUT)),'sha256':capture['sha256']},{'locator':'browser/browser-results.json','sha256':hashlib.sha256(raw).hexdigest()}]})
result=ParameterAggregator(param_names={'SF_FIRST_MORPH':'first_visible_level_delta','SF_NEXT_MORPH':'next_visible_level_delta'},param_domains={p:'ingame' for p in records}).aggregate(records)
provenance=OUT/'observations';provenance.mkdir(exist_ok=True)
(provenance/'raw.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
(provenance/'aggregated.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
exporter=DesignDBExporter('SeraresPlayable','RPG',domain_groups=[DomainGroup('ingame','serares_flow_slice','MorphLoop','core',list(records),[],[])],db_root=provenance/'export')
paths=exporter.export(result)
print(json.dumps({'raw_observations':sum(map(len,records.values())),'selected_parameters':len(result),'output_root':str(provenance),'exported_files':[str(p) for p in paths]},ensure_ascii=True))
