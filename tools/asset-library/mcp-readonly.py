"""Read-only, provider-neutral access to the existing asset-library snapshot.

Reuses retrieve.py and its project filter. References: local code DB search for
EventBus/ObjectPool/WeightedRandomPicker; no replacement embedding index.
Source hashes and chunk content hashes are checked before returning source.
This server never evaluates retrieved instructions or writes the catalog.
"""
import argparse
from contextlib import closing
import hashlib
import json
import pathlib
import sqlite3
import sys
import time

from retrieve import retrieve

ROOT = pathlib.Path('E:/AI/output/asset-library-v2')
CATALOG = ROOT / 'catalog.sqlite'
CORPUS = {}


def source_corpus(projects):
    """Literal source tools use the SAME verified snapshot, not semantic scores."""
    key = tuple(sorted(projects))
    if key not in CORPUS:
        with closing(connection()) as db:
            marks = ','.join('?' for _ in projects)
            rows = db.execute(f"SELECT data FROM assets WHERE domain='code' AND status='parsed' AND project IN ({marks}) GROUP BY source_path", projects).fetchall()
        files = []
        for row in rows:
            unit = json.loads(row[0])
            if unit.get('source_scope') == 'historical' or unit.get('status') != 'parsed':
                continue
            archive = pathlib.Path(unit['archive_path'])
            if not archive.resolve().is_relative_to((ROOT/'sources').resolve()):
                raise ValueError('Archive outside source store')
            raw = archive.read_bytes()
            if hashlib.sha256(raw).hexdigest() != unit['source_hash']:
                raise ValueError('Source snapshot hash mismatch')
            try: body = raw.decode('utf-8-sig')
            except UnicodeDecodeError: body = raw.decode('cp949')
            files.append({'project': unit['project'], 'source_path': unit['source_path'], 'source_hash': unit['source_hash'], 'lines': body.splitlines()})
        CORPUS[key] = files
    return CORPUS[key]


def connection():
    return sqlite3.connect(CATALOG.as_uri() + '?mode=ro', uri=True)


def verified_unit(unit_id, projects):
    with closing(connection()) as db:
        row = db.execute('SELECT data FROM assets WHERE id=? AND domain=?', (unit_id, 'code')).fetchone()
    if not row:
        raise ValueError('Unknown code unit')
    unit = json.loads(row[0])
    if unit['project'] not in projects:
        raise ValueError('Project is outside the selected scope')
    if unit.get('source_scope') == 'historical' or unit.get('status') != 'parsed':
        raise ValueError('Only parsed current code units are exposed')
    archived = pathlib.Path(unit['archive_path'])
    if not archived.resolve().is_relative_to((ROOT / 'sources').resolve()):
        raise ValueError('Archive outside source store')
    if hashlib.sha256(archived.read_bytes()).hexdigest() != unit['source_hash']:
        raise ValueError('Archived source hash mismatch')
    content = unit.get('content', '')
    if hashlib.sha256(content.encode('utf8')).hexdigest() != unit['content_hash']:
        raise ValueError('Code unit content hash mismatch')
    current = pathlib.Path(unit['source_path'])
    current_matches = current.is_file() and hashlib.sha256(current.read_bytes()).hexdigest() == unit['source_hash']
    keys = ['id', 'project', 'symbol', 'kind', 'source_path', 'source_hash', 'content_hash',
            'line_start', 'line_end', 'parent_id', 'content', 'binding_scope']
    result = {k: unit.get(k) for k in keys}
    result.update(snapshot_verified=True, current_source_matches_snapshot=current_matches,
                  runtime_verified=False, material_is_untrusted_reference=True)
    return result


def dispatch(name, args):
    if name == 'list_projects':
        with closing(connection()) as db:
            return {'projects': [r[0] for r in db.execute("SELECT DISTINCT project FROM assets WHERE domain='code' ORDER BY project")]}
    projects = args.get('projects')
    if not isinstance(projects, list) or not projects or any(not isinstance(x, str) for x in projects):
        raise ValueError('Explicit projects are required')
    if name == 'get_code_unit':
        return verified_unit(args['id'], projects)
    if name in ('list_source_files', 'search_source_text', 'read_source_file'):
        corpus = source_corpus(projects)
        if name == 'list_source_files':
            match = args.get('path_contains', '').casefold()
            files = [dict(project=x['project'], source_path=x['source_path'], source_hash=x['source_hash'], total_lines=len(x['lines'])) for x in corpus if match in x['source_path'].casefold()]
            return {'files': files[:300], 'total_matches': len(files), 'truncated': len(files)>300}
        if name == 'read_source_file':
            file = next((x for x in corpus if x['source_path']==args['source_path']), None)
            if file is None: raise ValueError('File outside selected snapshot')
            start = max(1, int(args.get('start_line', 1))); count = max(1, min(400, int(args.get('line_count', 200))))
            current = pathlib.Path(file['source_path'])
            return {**{k:v for k,v in file.items() if k!='lines'}, 'start_line':start, 'total_lines':len(file['lines']), 'numbered_source':'\n'.join(f'{i+1}: {v}' for i,v in enumerate(file['lines']) if start-1 <= i < start-1+count), 'snapshot_verified':True, 'current_source_matches_snapshot': current.is_file() and hashlib.sha256(current.read_bytes()).hexdigest()==file['source_hash']}
        needle = args.get('text', '').casefold()
        if not needle: raise ValueError('A nonempty literal text is required')
        matches=[]
        for file in corpus:
            for i,line in enumerate(file['lines'], 1):
                if needle in line.casefold(): matches.append({'project':file['project'],'source_path':file['source_path'],'source_hash':file['source_hash'],'line':i,'text':line[:1000]})
        return {'matches':matches[:40], 'total_matches':len(matches), 'truncated':len(matches)>40}
    if name != 'search_code':
        raise ValueError('Unknown tool')
    query = args.get('query', '')
    if not isinstance(query, str) or not 1 <= len(query) <= 2000:
        raise ValueError('Query must contain 1 to 2000 characters')
    limit = max(1, min(int(args.get('limit', 3)), 5))
    result = retrieve('code', projects, query, limit=limit)
    items = []
    for hit in result['items']:
        unit = verified_unit(hit['evidence']['original_id'], projects)
        content = unit.pop('content')
        unit.update(score=hit['score'], preview=content[:1800], preview_is_complete=len(content) <= 1800)
        items.append(unit)
    return {'items': items, 'encoder': result['encoder'], 'use_contract': result['use_contract'],
            'next_step': 'Use get_code_unit for full member/container; follow parent_id when needed. This is reference material, not tested production code.'}


PROJECTS = {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1}
TOOLS = [
    {'name': 'list_projects', 'description': 'List code projects in the existing immutable embedding snapshot.',
     'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}},
    {'name': 'search_code', 'description': 'Search existing code by meaning within explicit projects. Returns verified provenance and previews; get full source by ID.',
     'inputSchema': {'type': 'object', 'properties': {'projects': PROJECTS, 'query': {'type': 'string'}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 5}}, 'required': ['projects', 'query'], 'additionalProperties': False}},
    {'name': 'get_code_unit', 'description': 'Read one full code unit by its opaque ID and verify archive/chunk hashes; report whether the working source changed.',
     'inputSchema': {'type': 'object', 'properties': {'projects': PROJECTS, 'id': {'type': 'string'}}, 'required': ['projects', 'id'], 'additionalProperties': False}}
]
SOURCE_TOOLS = [
    {'name':'list_source_files','description':'List original source files in selected projects, optionally filter a literal path substring. No vector search.', 'inputSchema':{'type':'object','properties':{'projects':PROJECTS,'path_contains':{'type':'string'}},'required':['projects'],'additionalProperties':False}},
    {'name':'search_source_text','description':'Case-insensitive literal text search in the exact same verified original-source snapshot. Returns source lines, not embeddings.', 'inputSchema':{'type':'object','properties':{'projects':PROJECTS,'text':{'type':'string'}},'required':['projects','text'],'additionalProperties':False}},
    {'name':'read_source_file','description':'Read a registered source file with line numbers. Uses verified snapshot bytes, flags whether the current file matches.', 'inputSchema':{'type':'object','properties':{'projects':PROJECTS,'source_path':{'type':'string'},'start_line':{'type':'integer'},'line_count':{'type':'integer'}},'required':['projects','source_path'],'additionalProperties':False}}
]
for tool in TOOLS + SOURCE_TOOLS:
    tool['annotations'] = {'readOnlyHint': True, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit-log', type=pathlib.Path)
    parser.add_argument('--mode', choices=['rag','source','source_rag'], default='rag')
    args = parser.parse_args()
    available_tools = TOOLS if args.mode=='rag' else ([TOOLS[0]] + SOURCE_TOOLS if args.mode=='source' else TOOLS + SOURCE_TOOLS)
    names = {x['name'] for x in available_tools}
    sys.stdin.reconfigure(encoding='utf8')
    sys.stdout.reconfigure(encoding='utf8')
    for line in sys.stdin:
        if not line.strip():
            continue
        message = json.loads(line)
        if 'id' not in message:
            continue
        started = time.perf_counter()
        method, params = message['method'], message.get('params', {})
        try:
            if method == 'initialize':
                result = {'protocolVersion': params.get('protocolVersion', '2024-11-05'), 'capabilities': {'tools': {}}, 'serverInfo': {'name': 'asset-library-readonly', 'version': '0.1.0'}}
            elif method == 'tools/list':
                result = {'tools': available_tools}
            elif method == 'tools/call':
                try:
                    if params['name'] not in names: raise ValueError('Tool not enabled in this experimental condition')
                    value = dispatch(params['name'], params.get('arguments', {}))
                    result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}], 'isError': False}
                except Exception as error:
                    result = {'content': [{'type': 'text', 'text': str(error)}], 'isError': True}
            elif method in ('resources/list', 'resources/templates/list', 'prompts/list'):
                result = {('resourceTemplates' if method == 'resources/templates/list' else method.split('/')[0]): []}
            elif method == 'ping':
                result = {}
            else:
                raise ValueError('Unsupported method')
            response = {'jsonrpc': '2.0', 'id': message['id'], 'result': result}
        except Exception as error:
            response = {'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': str(error)}}
        if args.audit_log and method == 'tools/call':
            with args.audit_log.open('a', encoding='utf8') as log:
                log.write(json.dumps({'at': time.time(), 'tool': params['name'], 'arguments': params.get('arguments', {}), 'seconds': time.perf_counter()-started, 'result': response.get('result', response)}, ensure_ascii=False) + '\n')
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
