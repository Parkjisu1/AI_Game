"""Summarize recorded trials; never converts test cases into independent tasks."""
import hashlib
import json
import pathlib
import re
import statistics

ROOT = pathlib.Path('E:/AI/output/embedding-eval-20261005')


def read(path):
    value = path.read_text(encoding='utf8').strip()
    if value.startswith('```'):
        value = re.sub(r'^```(?:json)?\s*|\s*```$', '', value)
    return json.loads(value)


def main():
    frozen = {}
    for name in ['frozen-inputs.json', 'source-frozen-inputs.json']:
        data = read(ROOT/name)
        for path, expected in data.get('hashes', data).items():
            frozen[path] = hashlib.sha256((ROOT/path).read_bytes()).hexdigest() == expected
    assert all(frozen.values()), frozen
    trials = []
    for folder in sorted((ROOT/'runs').iterdir()):
        if not re.fullmatch(r'(astra|opus)-(baseline|rag)-[12]', folder.name):
            continue
        run, grade = read(folder/'run.json'), read(folder/'grade.json')
        trials.append({**run, 'grade':grade})
    groups = []
    for model in ['astra','opus']:
        for condition in ['baseline','rag']:
            selected = [x for x in trials if x['model_requested']==model and x['condition']==condition]
            assert len(selected)==2
            groups.append({'model':model,'condition':condition,'runs':len(selected),
                'mean_seconds':statistics.mean(x['seconds'] for x in selected),
                'compile_passed':sum(x['grade']['compile_passed'] for x in selected),
                'passed':sum(x['grade']['passed'] for x in selected),
                'total':sum(x['grade']['total'] for x in selected),
                'mean_reported_list_cost_usd':statistics.mean(x['reported_cost_usd'] for x in selected) if model=='opus' else None,
                'mean_input_tokens_including_cache':statistics.mean(x['usage']['input_tokens'] + (x['usage'].get('cache_creation_input_tokens',0)+x['usage'].get('cache_read_input_tokens',0) if model=='opus' else 0) for x in selected),
                'mean_output_tokens':statistics.mean(x['usage']['output_tokens'] for x in selected)})
    expected=read(ROOT/'evaluator/source-expected.json')
    lookups=[]
    excerpts=[]
    for folder in sorted((ROOT/'runs').glob('lookup-*')):
        answer,run=read(folder/'answer.txt'),read(folder/'run.json')
        checks={}
        for key,value in expected.items():
            actual=answer.get(key)
            if key=='receipt_methods':
                # Equivalent qualified/unqualified method names; no behavior relaxation.
                actual=sorted(x.rsplit('.',1)[-1] for x in actual)
                value=sorted(value)
            checks[key]=actual==value
        citations=[]
        for citation in answer.get('citations',[]):
            source=pathlib.Path(citation['source_path'])
            raw=source.read_bytes();lines=raw.decode('utf-8-sig').splitlines()
            start,end=citation['line_start'],citation['line_end']
            valid=1<=start<=end<=len(lines)
            citations.append({**citation,'current_hash_matches':hashlib.sha256(raw).hexdigest()==citation['source_hash'],'valid_line_range':valid})
            excerpts.append({'run':folder.name,**citation,'source_excerpt':'\n'.join(f'{i+1}: {lines[i]}' for i in range(start-1,end)) if valid else ''})
        audit=[json.loads(x) for x in (folder/'mcp-audit.jsonl').read_text(encoding='utf8').splitlines()]
        semantic_calls=sum(x['tool']=='search_code' for x in audit)
        assert semantic_calls==0 if run['condition']=='source' else semantic_calls>=1
        grade={'checks':checks,'passed':sum(checks.values()),'total':len(checks),'citations':citations,
            'all_citation_hashes_and_ranges_valid':all(c['current_hash_matches'] and c['valid_line_range'] for c in citations),
            'questions_cited':sorted({c['question'] for c in citations}),
            'semantic_calls':semantic_calls,'normalization':'receipt_methods accepts class-qualified names; order ignored',
            'citation_semantics':'See source-citation-excerpts.json for human/model review; hash/range checks alone do not prove entailment.'}
        (folder/'source-grade.json').write_text(json.dumps(grade,ensure_ascii=False,indent=2),encoding='utf8')
        lookups.append({**run,'grade':grade})
    summary={'frozen_inputs_unchanged':frozen,'primary_groups':groups,'primary_trials':trials,'source_lookup_trials':lookups,
        'scope':{'independent_component_specs':3,'repetitions_per_model_condition':2,'candidate_requests':8,'component_implementations':24,'test_case_executions':488,'repository_lookup_questions':4,'repository_fact_fields':9,'lookup_repetitions_per_model_condition':1},
        'limitations':['Generic component tests have a ceiling effect; equal scores do not prove equal general capability.',
            'No Unity/Player/device/full-game execution or human review/fix time was measured.',
            'CLI end-to-end wall times include retrieval, queueing, formatting and startup. They are not development time or game FPS.',
            'Candidate batches were serial, but an independent Opus review overlapped parts of first Opus primary trials; service/cache/load are confounders.',
            'RAG was mandatory in the treatment, so this measures forced retrieval, not a model deciding whether retrieval helps.',
            'Astra command requested gpt-6-astra; runtime resolved-model metadata was not exposed. Opus reported claude-opus-5-5.',
            'Opus primary calls requested alias opus (all resolved 5-5); subsequent lookup/review runner pins 5-5. Command logs are authoritative.',
            'Provider token counters differ. Opus costs are list-price estimates on a subscription, not observed invoices.',
            'Project lookup tasks name components and favor direct source search; they are not blind discovery or an integration-change benchmark.',
            'Literal-source historical exclusion was hardened after lookup trials; cited lookup files were current parsed sources in both conditions.',
            'Hidden tests were not offered by MCP. This is practical task isolation, not an OS-level hostile-agent security audit.']}
    (ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    (ROOT/'source-citation-excerpts.json').write_text(json.dumps(excerpts,ensure_ascii=False,indent=2),encoding='utf8')
    print('Frozen inputs: PASS',len(frozen))
    for group in groups:print(group['model'],group['condition'],str(group['passed'])+'/'+str(group['total']),round(group['mean_seconds'],2),'s')
    for lookup in lookups:print(lookup['name'],str(lookup['grade']['passed'])+'/'+str(lookup['grade']['total']),'citation hashes/ranges',lookup['grade']['all_citation_hashes_and_ranges_valid'])


if __name__=='__main__':
    main()
