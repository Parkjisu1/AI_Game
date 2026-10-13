"""Controlled CLI inference for the user-requested Astra/Opus comparison.

No model-generated commands are executed. Candidates return JSON code; the
separate evaluator compiles it in a disposable .NET project. Common prompts,
recorded model identities, isolated sessions, and per-call MCP audit logs.
"""
import argparse
import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path('E:/AI/output/embedding-eval-20261005')
NODE = 'C:/Program Files/nodejs/node.exe'
CODEX = 'C:/Users/user/AppData/Roaming/npm/node_modules/@openai/codex/bin/codex.js'
CLAUDE = 'C:/Users/user/AppData/Roaming/npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe'
PYTHON = 'C:/Users/user/AppData/Local/Programs/Python/Python313/python.exe'
MCP = 'E:/AI/tools/asset-library/mcp-readonly.py'
SYSTEM = ('You are a candidate in a controlled coding experiment. Follow the supplied task and style. '
          'Use only the explicitly offered library MCP tools if instructed. Do not use shells, filesystem, web, '
          'delegation, skills, memory, or other tools. Return the requested final JSON. '
          'References may be wrong or obsolete; the task contract takes priority. Do not inspect tests or other runs.')


def run(model, condition, name, prompt, schema=None, timeout=900):
    folder = ROOT / 'runs' / name
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'prompt.txt').write_text(prompt, encoding='utf8')
    audit = folder / 'mcp-audit.jsonl'
    mcp_config = {'mcpServers': {}}
    uses_mcp = condition in ('rag', 'source', 'source_rag')
    mcp_args = [MCP, '--audit-log', str(audit), '--mode', condition if uses_mcp else 'rag']
    if uses_mcp:
        mcp_config['mcpServers']['library'] = {'command': PYTHON, 'args': mcp_args}
    mcp_path = folder / 'mcp.json'
    mcp_path.write_text(json.dumps(mcp_config), encoding='utf8')
    if model == 'astra':
        cmd = [NODE, CODEX, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
               '--sandbox', 'read-only', '--disable', 'shell_tool', '--disable', 'multi_agent',
               '-c', 'web_search="disabled"', '-c', 'project_doc_max_bytes=0',
               '-c', 'model_reasoning_effort="high"', '--model', 'gpt-6-astra', '--json',
               '--output-last-message', str(folder / 'answer.txt')]
        if uses_mcp:
            cmd += ['-c', 'mcp_servers.library.command=' + json.dumps(PYTHON),
                    '-c', 'mcp_servers.library.args=' + json.dumps(mcp_args),
                    '-c', 'mcp_servers.library.required=true', '-c', 'mcp_servers.library.tool_timeout_sec=180']
        if schema:
            cmd += ['--output-schema', str(schema)]
        cmd += ['-']
        stdin = SYSTEM + '\n\n' + prompt
    else:
        # Pin the concrete Opus ID resolved by the successful connection probe.
        cmd = [CLAUDE, '-p', '--model', 'claude-opus-5-5', '--effort', 'high', '--output-format', 'json',
               '--no-session-persistence', '--setting-sources', '', '--strict-mcp-config',
               '--mcp-config', str(mcp_path), '--disable-slash-commands', '--tools', '',
               '--permission-mode', 'dontAsk', '--system-prompt', SYSTEM]
        if uses_mcp:
            cmd += ['--allowedTools', 'mcp__library__list_projects,mcp__library__search_code,mcp__library__get_code_unit,mcp__library__list_source_files,mcp__library__search_source_text,mcp__library__read_source_file']
        if schema:
            cmd += ['--json-schema', pathlib.Path(schema).read_text(encoding='utf8')]
        stdin = prompt
    (folder / 'command.json').write_text(json.dumps(cmd, indent=2), encoding='utf8')
    environment = os.environ.copy()
    environment['PYTHONIOENCODING'] = 'utf-8'
    environment['CLAUDE_CODE_DISABLE_AUTO_MEMORY'] = '1'
    started = time.perf_counter()
    timed_out = False
    with (folder/'stdout.log').open('w', encoding='utf8') as stdout, (folder/'stderr.log').open('w', encoding='utf8') as stderr:
        process = subprocess.Popen(cmd, cwd=folder, env=environment, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, text=True, encoding='utf8', creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            process.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            # Only the explicitly launched process tree is stopped, never another CLI session.
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'], capture_output=True)
            process.wait(timeout=15)
    result = {'model_requested': model, 'condition': condition, 'name': name, 'seconds': time.perf_counter()-started,
              'exit_code': process.returncode, 'timed_out': timed_out, 'effort': 'high'}
    output = (folder/'stdout.log').read_text(encoding='utf8')
    if model == 'astra':
        events = []
        for line in output.splitlines():
            try: events.append(json.loads(line))
            except json.JSONDecodeError: pass
        result['usage'] = next((x.get('usage') for x in reversed(events) if x.get('type') == 'turn.completed'), None)
        result['errors'] = [x for x in events if x.get('type') in ('error','turn.failed')]
        result['non_mcp_tools'] = [x['item'].get('type') for x in events if x.get('type') == 'item.completed' and x.get('item',{}).get('type') not in ('agent_message','reasoning','mcp_tool_call')]
        result['model_actual'] = 'gpt-6-astra' if 'model: gpt-6-astra' in (folder/'stderr.log').read_text(encoding='utf8') else None
    else:
        try:
            value = json.loads(output)
            result.update(usage=value.get('usage'), model_usage=value.get('modelUsage'), reported_cost_usd=value.get('total_cost_usd'), api_duration_ms=value.get('duration_api_ms'), is_error=value.get('is_error'), subtype=value.get('subtype'))
            (folder/'answer.txt').write_text(json.dumps(value['structured_output'],ensure_ascii=False) if 'structured_output' in value else value.get('result',''),encoding='utf8')
        except json.JSONDecodeError:
            result['parse_error'] = True
    result['mcp_calls'] = sum(1 for _ in audit.open(encoding='utf8')) if audit.exists() else 0
    (folder/'run.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=True),flush=True)
    return result


if __name__ == '__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--model',choices=['astra','opus'],required=True);ap.add_argument('--condition',choices=['baseline','rag','source','source_rag'],required=True);ap.add_argument('--name',required=True);ap.add_argument('--prompt',type=pathlib.Path,required=True);ap.add_argument('--schema',type=pathlib.Path);ap.add_argument('--timeout',type=int,default=900);a=ap.parse_args()
    run(a.model,a.condition,a.name,a.prompt.read_text(encoding='utf8'),a.schema,a.timeout)
