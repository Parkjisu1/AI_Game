'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { transform, parseArgs, checkLinks } = require('./virtual-player-bridge');
const templatePath = path.join(__dirname, 'templates', 'flow-contract.example.json');
const script = path.join(__dirname, 'virtual-player-bridge.js');
const criterion = (metric, extra = {}) => ({ id: 'V1', metric, min: 0, max: 0, ...extra });
const run = (data, criteria) => transform({ ...data, virtual_player: { criteria } }, { project: 'VPFixture' });

test('without definitions, short sessions or few actions do not invent violations, hooks, or boredom', () => {
  const result = transform({ sessions: { avg_length: 10 }, actions: { frequency: 1, variety_score: 1 }, failures: { combat: 0 } }, { project: 'VPFixture' });
  assert.equal(result.comparisons[0].status, 'missing_definition');
  assert.equal(result.observations.failure_rates[0].value, 0);
  assert.equal(result.feedback_items.length, 1);
  assert.equal(result.feedback_items[0].severity, 'UNASSESSED');
  assert.ok(!JSON.stringify(result).includes('daily_reward'));
  assert.ok(result.feedback_items.every(item => !Object.hasOwn(item, 'recommendation')));
});

test('zero telemetry, zero bounds and empty expected hook sets retain their explicit meaning', () => {
  const result = run({ sessions: { avg_length: 0, engagement_hooks: [] }, actions: { frequency: 0, variety_score: 0 }, failures: [{ point: 'combat', rate: 0 }], player_count: 0 }, [
    criterion('session_length'), criterion('action_frequency', { id: 'V2' }), criterion('action_variety', { id: 'V3' }),
    { id: 'V4', metric: 'engagement_hooks', expected_hooks: [] }, criterion('failure_rate', { id: 'V5', point: 'combat' }),
  ]);
  assert.ok(result.comparisons.every(item => item.status === 'within_declared_range'));
  assert.equal(result.vp_metadata.player_count, 0);
  assert.equal(result.feedback_items.length, 0);
});

test('provided null and NaN never fall back to alternate or fabricated measurements', () => {
  for (const value of [null, NaN, Infinity, -1, '0']) {
    const result = run({ sessions: { avg_length: value, average_session: 0 } }, [criterion('session_length')]);
    assert.equal(result.comparisons[0].status, 'missing_evidence');
  }
  assert.equal(run({ failures: [{ point: 'combat', rate: null, drop_off_rate: 0 }] }, [criterion('failure_rate', { point: 'combat' })]).comparisons[0].status, 'missing_evidence');
  assert.equal(run({ sessions: { engagement_hooks: { daily_reward: false } } }, [{ id: 'V1', metric: 'engagement_hooks', expected_hooks: ['daily_reward'] }]).comparisons[0].status, 'missing_evidence');
});

test('explicit legacy session target needs explicit tolerance, including zero', () => {
  const transformTarget = sessions => transform({ sessions }, { project: 'VPFixture' });
  assert.equal(transformTarget({ avg_length: 0, target_length: 0 }).comparisons[0].status, 'missing_definition');
  assert.equal(transformTarget({ avg_length: 0, target_length: 0, tolerance_seconds: 0 }).comparisons[0].status, 'within_declared_range');
  assert.equal(transformTarget({ avg_length: 120, target_length: 100, tolerance_ratio: 0.1 }).comparisons[0].status, 'outside_declared_range');
  assert.equal(transformTarget({ avg_length: 0, target_length: null, tolerance_seconds: 0 }).comparisons[0].status, 'missing_definition');
});

test('declared comparisons report boundary differences without causal diagnosis or severity heuristics', () => {
  const result = run({ sessions: { avg_length: 15, engagement_hooks: ['custom_finish'] } }, [
    criterion('session_length', { min: 10, max: 12 }), { id: 'V2', metric: 'engagement_hooks', expected_hooks: ['custom_finish', 'custom_retry'] },
  ]);
  assert.equal(result.comparisons[0].status, 'outside_declared_range');
  assert.deepEqual(result.comparisons[1].missing_hooks, ['custom_retry']);
  assert.ok(result.feedback_items.every(item => item.severity === 'UNASSESSED' && !item.recommendation));
});

test('malformed criteria and ambiguous failures stay unjudged', () => {
  for (const value of [null, {}, criterion('session_length', { min: null }), criterion('session_length', { min: 2, max: 1 }), criterion('failure_rate', { point: 'combat', max: 2 })]) {
    assert.equal(run({}, [value]).comparisons[0].status, 'missing_definition');
  }
  const result = run({ failures: [{ point: 'combat', rate: 0 }, { point: 'combat', rate: 1 }] }, [criterion('failure_rate', { point: 'combat' })]);
  assert.equal(result.comparisons[0].status, 'missing_evidence');
});

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vp-flow-'));
  t.after(() => {
    const target = path.resolve(dir);
    assert.equal(path.dirname(target), path.resolve(os.tmpdir()));
    assert.ok(path.basename(target).startsWith('vp-flow-'));
    fs.rmSync(target, { recursive: true, force: true });
  });
  const contract = JSON.parse(fs.readFileSync(templatePath, 'utf8').replace(/^\uFEFF/, ''));
  contract.virtual_player = { criteria: [criterion('session_length', { requirement_ids: ['R1'], acceptance_ids: ['A1'] })] };
  const input = path.join(dir, 'input.json'), output = path.join(dir, 'report.json'), contractPath = path.join(dir, 'flow-contract.json');
  const guard = path.join(dir, 'no-db.cjs');
  fs.writeFileSync(guard, "const M=require('module'),load=M._load;M._load=function(id,...args){if(/mongodb|db-client|^(?:node:)?(?:http|https|net|tls)$/.test(id))throw Error('DB/network forbidden in VP test: '+id);return load.call(this,id,...args)}");
  fs.writeFileSync(input, JSON.stringify({ project: contract.project, sessions: { avg_length: 0 } }));
  fs.writeFileSync(contractPath, JSON.stringify(contract));
  const cli = () => spawnSync(process.execPath, ['--require', guard, script, '--project', contract.project, '--input', input, '--output', output, '--flow-contract', contractPath], { encoding: 'utf8' });
  return { dir, input, output, contractPath, contract, guard, cli };
}

test('real handoff contract drives CLI comparisons and preserves raw input SHA without DB/network access', t => {
  const f = fixture(t), result = f.cli();
  assert.equal(result.status, 0, result.stderr);
  const report = JSON.parse(fs.readFileSync(f.output, 'utf8'));
  assert.equal(report.criteria_source, 'flow_contract');
  assert.equal(report.comparisons[0].status, 'within_declared_range');
  assert.deepEqual(report.comparisons[0].acceptance_ids, ['A1']);
  assert.equal(report.input_snapshot.raw, fs.readFileSync(f.input, 'utf8'));
  assert.equal(report.input_snapshot.sha256, require('./lib/flow-contract').sha256(fs.readFileSync(f.input)));
  assert.equal(JSON.parse(fs.readFileSync(f.contractPath)).acceptance[0].status, 'not_run');
});

test('contract and telemetry mismatches fail before output, unknown links cannot borrow unrelated acceptance', t => {
  const f = fixture(t);
  fs.writeFileSync(f.input, JSON.stringify({ project: 'Wrong', sessions: { avg_length: 0 } }));
  let result = f.cli(); assert.notEqual(result.status, 0); assert.match(result.stderr, /project mismatch/); assert.equal(fs.existsSync(f.output), false);
  fs.writeFileSync(f.input, JSON.stringify({ sessions: { avg_length: 0 } }));
  fs.writeFileSync(f.contractPath, JSON.stringify({ ...f.contract, project: 'WrongContract' }));
  result = f.cli(); assert.notEqual(result.status, 0); assert.match(result.stderr, /contract project mismatch/); assert.equal(fs.existsSync(f.output), false);
  f.contract.virtual_player.criteria[0].acceptance_ids = ['Missing'];
  fs.writeFileSync(f.contractPath, JSON.stringify(f.contract));
  result = f.cli(); assert.notEqual(result.status, 0); assert.match(result.stderr, /not linked/); assert.equal(fs.existsSync(f.output), false);
  assert.throws(() => checkLinks([{ id: 'V1', requirement_ids: ['R1'], acceptance_ids: ['A2'] }], {
    requirements: [{ id: 'R1', acceptance_ids: ['A1'] }, { id: 'R2', acceptance_ids: ['A2'] }], acceptance: [{ id: 'A1' }, { id: 'A2' }],
  }), /not linked/);
});

test('contract criteria absence does not borrow a competing input target', t => {
  const f = fixture(t); delete f.contract.virtual_player;
  const result = transform({ sessions: { avg_length: 1, target_length: 100, tolerance_seconds: 0 } }, { project: f.contract.project, contract: f.contract });
  assert.equal(result.criteria_source, 'flow_contract');
  assert.equal(result.comparisons[0].status, 'missing_definition');
});

test('import is inert and CLI option typos or missing values cannot downgrade the contract', t => {
  const f = fixture(t);
  const result = spawnSync(process.execPath, ['--require', f.guard, '-e', `require(${JSON.stringify(script)})`], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr); assert.equal(result.stdout, ''); assert.equal(fs.existsSync(f.output), false);
  assert.throws(() => parseArgs(['--flow-contarct', 'file.json']), /Unknown option/);
  assert.throws(() => parseArgs(['--flow-contract']), /requires a value/);
});
