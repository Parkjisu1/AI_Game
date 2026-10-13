"""Contract and provenance checks; destructive fixtures are temporary only."""
import hashlib
import importlib.util
import json
import pathlib
import sqlite3
import subprocess
import sys
import tempfile

spec=importlib.util.spec_from_file_location('library_mcp',pathlib.Path(__file__).with_name('mcp-readonly.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
checks=[]
def rejected(name,action):
    try:action()
    except ValueError:checks.append(name);return
    raise AssertionError(name)
with tempfile.TemporaryDirectory(prefix='asset-library-mcp-') as temp:
    m.ROOT=pathlib.Path(temp);m.CATALOG=m.ROOT/'catalog.sqlite';(m.ROOT/'sources').mkdir()
    content='public class Example { }';raw=content.encode();sha=hashlib.sha256(raw).hexdigest()
    archive=m.ROOT/'sources'/sha;archive.write_bytes(raw);current=m.ROOT/'Example.cs';current.write_bytes(raw)
    unit={'id':'sample','project':'P','status':'parsed','content':content,'content_hash':sha,'source_hash':sha,'source_path':str(current),'archive_path':str(archive)}
    db=sqlite3.connect(m.CATALOG);db.execute('CREATE TABLE assets(id TEXT,domain TEXT,project TEXT,data TEXT,status TEXT,source_path TEXT)')
    def save():
        db.execute('DELETE FROM assets');db.execute('INSERT INTO assets VALUES(?,?,?,?,?,?)',('sample','code','P',json.dumps(unit),unit['status'],unit['source_path']));db.commit();m.CORPUS.clear()
    save();result=m.verified_unit('sample',['P']);assert result['snapshot_verified'] and result['current_source_matches_snapshot'];checks.append('verified snapshot and current source')
    result=m.dispatch('read_source_file',{'projects':['P'],'source_path':str(current)})
    assert result['snapshot_verified'] and result['numbered_source']=='1: '+content;checks.append('literal source reads verified snapshot')
    rejected('literal path outside project',lambda:m.dispatch('read_source_file',{'projects':['Other'],'source_path':str(current)}))
    rejected('unregistered literal source path',lambda:m.dispatch('read_source_file',{'projects':['P'],'source_path':str(m.ROOT/'secret')}))
    rejected('project boundary',lambda:m.verified_unit('sample',['Other']))
    rejected('unknown source ID',lambda:m.verified_unit('../secret',['P']))
    rejected('explicit project required',lambda:m.dispatch('search_code',{'projects':[],'query':'x'}))
    current.write_text('changed');assert not m.verified_unit('sample',['P'])['current_source_matches_snapshot'];checks.append('changed source explicitly flagged')
    archive.write_text('corrupt');rejected('archive corruption',lambda:m.verified_unit('sample',['P']));archive.write_bytes(raw)
    unit['content']='altered';save();rejected('chunk corruption',lambda:m.verified_unit('sample',['P']));unit['content']=content
    unit['source_scope']='historical';save();rejected('historical material excluded',lambda:m.verified_unit('sample',['P']))
    assert not m.source_corpus(['P']);checks.append('historical literal sources excluded');unit.pop('source_scope')
    unit['archive_path']=str(current);save();rejected('archive outside store',lambda:m.verified_unit('sample',['P']));db.close()
messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'contract-test','version':'1'}}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'get_code_unit','arguments':{'projects':['not-a-project'],'id':'not-a-unit'}}}]
p=subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('mcp-readonly.py'))],input=''.join(json.dumps(x)+'\n' for x in messages),capture_output=True,text=True,encoding='utf8',timeout=20,check=True)
responses=[json.loads(x) for x in p.stdout.splitlines()];assert [r['id'] for r in responses]==[1,2,3];assert len(responses[1]['result']['tools'])==3;assert responses[2]['result']['isError'];checks.append('stdio protocol and safe tool error')
messages[-1]['params']={'name':'search_code','arguments':{'projects':['NextPR'],'query':'EventBus'}}
p=subprocess.run([sys.executable,str(pathlib.Path(__file__).with_name('mcp-readonly.py')),'--mode','source'],input=''.join(json.dumps(x)+'\n' for x in messages),capture_output=True,text=True,encoding='utf8',timeout=20,check=True)
responses=[json.loads(x) for x in p.stdout.splitlines()]
assert {x['name'] for x in responses[1]['result']['tools']}=={'list_projects','list_source_files','search_source_text','read_source_file'}
assert responses[2]['result']['isError'] and 'not enabled' in responses[2]['result']['content'][0]['text'];checks.append('source-only mode rejects semantic tool calls')
report={'passed':True,'checks':checks,'production_catalog_modified':False}
pathlib.Path('E:/AI/output/embedding-eval-20261005/mcp-validation.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('MCP contract/provenance:',len(checks),'checks PASS')
