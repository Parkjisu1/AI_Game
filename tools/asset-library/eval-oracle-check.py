"""Three seeded defects check that the frozen evaluator can actually reject code.

Only disposable benchmark copies are modified, never candidate or game sources.
This is not an exhaustive mutation score or independent human oracle review.
"""
import importlib.util
import json
import pathlib

spec=importlib.util.spec_from_file_location('grade',pathlib.Path(__file__).with_name('eval-grade.py'))
grade=importlib.util.module_from_spec(spec);spec.loader.exec_module(grade)
root=grade.ROOT
base=json.loads((root/'runs/astra-baseline-1/answer.txt').read_text(encoding='utf8'))
changes=[
    ('stop_after_exception','TypedEventBus.cs','exceptions.Add(exception);','exceptions.Add(exception); break;'),
    ('value_equality_pool','ReferencePool.cs','ReferenceEquals(items[i], item)','EqualityComparer<T>.Default.Equals(items[i], item)'),
    ('missing_receipt_commit','RewardLedger.cs','_appliedTransactions.Add(transactionId);','// Seeded defect: receipt not committed.')
]
results=[]
for name,file,before,after in changes:
    candidate=json.loads(json.dumps(base))
    source=next(x for x in candidate['files'] if x['path']==file)
    assert source['content'].count(before)==1
    source['content']=source['content'].replace(before,after)
    folder=root/'oracle-checks'/name;folder.mkdir(parents=True,exist_ok=True)
    (folder/'answer.txt').write_text(json.dumps(candidate),encoding='utf8')
    result=grade.grade(folder)
    assert result['compile_passed'] and result['failed']>0
    results.append({'name':name,'compile_passed':True,'caught':True,'failed_cases':[x['name'] for x in result['cases'] if not x['passed']]})
report={'seeded_defects':len(results),'caught':len(results),'checks':results,'scope':'Three targeted oracle sanity checks; not an exhaustive mutation score. Original candidates unchanged.'}
(root/'oracle-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('Seeded defects detected:',len(results),'/',len(changes))
