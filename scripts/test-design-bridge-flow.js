'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { serializeYaml, parseYaml } = require('./lib/yaml-utils');
const bridge = require('./design-to-code-bridge');

const design = () => ({
    nodeId: 'ChainController', domain: 'ingame',
    contract: { provides: ['int Resolve(int seed)'], requires: [], invariant: 'No reward before a chain ends' },
    behaviors: [{ trigger: 'tap', action: 'resolve chain', result: 'one reward' }],
    logicFlow: [{ step: 1, action: 'Reject occupied tile', next: null, failNext: 'feedback' }],
});
const elements = systems => ({ systems: [{ file: 'systems.yaml', data: { systems } }], balance: [], content: [], bm: [] });
function temp(t) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'design-bridge-flow-'));
    t.after(() => {
        const target = path.resolve(dir);
        assert.equal(path.dirname(target), path.resolve(os.tmpdir()));
        assert.ok(path.basename(target).startsWith('design-bridge-flow-'));
        fs.rmSync(target, { recursive: true, force: true });
    });
    return dir;
}

test('explicit API, behavior, and error flow survive conversion without invented architecture', () => {
    const source = design();
    const [node] = bridge.processDesignElements(elements([source]), 'Fixture', 'Puzzle', { strict: true });
    assert.deepEqual(node.contract, source.contract);
    assert.deepEqual(node.behaviors, source.behaviors);
    assert.deepEqual(node.logicFlow, source.logicFlow);
    assert.deepEqual(node.referencePatterns, []);
    assert.deepEqual(node.codeHints, {});
    const system = bridge.buildSystemSpec([node], 'Fixture', 'Puzzle').systems[0];
    assert.deepEqual(system.contract, source.contract);
    assert.deepEqual(system.logicFlow, source.logicFlow);
});

test('contracts alias retains API metadata and conflicting aliases fail', () => {
    const source = design(); source.contracts = source.contract; delete source.contract;
    const [node] = bridge.processDesignElements(elements([source]), 'Fixture', 'Puzzle', { strict: true });
    assert.deepEqual(node.contract, source.contracts);
    source.contract = { provides: ['void Other()'], requires: [] };
    assert.throws(() => bridge.processDesignElements(elements([source]), 'Fixture', 'Puzzle', { strict: true }), /conflicting/);
});

test('strict handoff rejects missing API/behavior/flow, nonobjects and duplicate sanitized IDs', () => {
    for (const key of ['contract', 'logicFlow', 'behaviors']) {
        const source = design(); delete source[key];
        assert.throws(() => bridge.processDesignElements(elements([source]), 'Fixture', 'Puzzle', { strict: true }), /explicit/);
    }
    const source = design(); delete source.contract.requires;
    assert.throws(() => bridge.processDesignElements(elements([source]), 'Fixture', 'Puzzle', { strict: true }), /provides\/requires/);
    for (const field of ['behaviors', 'logicFlow']) {
        for (const value of [null, 'auto', {}, { trigger: 'tap' }, { action: ' ' }]) {
            const malformed = design(); malformed[field] = [value];
            assert.throws(() => bridge.processDesignElements(elements([malformed]), 'Fixture', 'Puzzle', { strict: true }), /nonempty action/);
        }
    }
    for (const field of ['provides', 'requires']) {
        for (const value of [null, '', ' ', {}, 1]) {
            const malformed = design(); malformed.contract[field] = [value];
            assert.throws(() => bridge.processDesignElements(elements([malformed]), 'Fixture', 'Puzzle', { strict: true }), /nonempty strings or objects/);
        }
    }
    for (const bad of ['ChainController', null, []]) {
        assert.throws(() => bridge.processDesignElements(elements([bad]), 'Fixture', 'Puzzle', { strict: true }), /object/);
    }
    const a = design(); delete a.nodeId; a.name = 'chain-controller';
    const b = design(); delete b.nodeId; b.name = 'ChainController';
    assert.throws(() => bridge.processDesignElements(elements([a, b]), 'Fixture', 'Puzzle', { strict: true }), /Duplicate/);
    const differentCase = design(); differentCase.nodeId = 'chaincontroller';
    assert.throws(() => bridge.processDesignElements(elements([design(), differentCase]), 'Fixture', 'Puzzle', { strict: true }), /Duplicate/);
    assert.throws(() => bridge.processDesignElements(elements([]), 'Fixture', 'Puzzle', { strict: true }), /No explicit/);
});

test('legacy fallback remains available and assumptions are untested', () => {
    const [node] = bridge.processDesignElements(elements([{ name: 'ChainController' }]), 'Fixture', 'Puzzle');
    assert.ok(node.contract.provides.length);
    for (const field of ['contract', 'behaviors', 'logicFlow', 'referencePatterns', 'codeHints']) {
        assert.ok(node.generation_assumptions.some(item => item.field === field && item.basis === 'proposed' && item.verification === 'untested'));
    }
});

test('trace connects every node and rejects dangling work items or requirements', () => {
    const nodes = bridge.processDesignElements(elements([design()]), 'Fixture', 'Puzzle', { strict: true });
    const context = { contractPath: '/fixture/flow-contract.json', hash: 'digest', contract: {
        requirements: [{ id: 'r1', goal_ids: ['g1'], claim_ids: ['c1'], decision_ids: ['d1'], acceptance_ids: ['a1'] }],
        work_items: [{ id: 'w1', node_ids: ['ChainController'], requirement_ids: ['r1'] }],
    } };
    bridge.attachFlowTrace(nodes, context);
    assert.deepEqual(nodes[0].flow_trace.acceptance_ids, ['a1']);
    assert.equal(bridge.buildSystemSpec(nodes, 'Fixture', 'Puzzle').systems[0].flow_trace.contract_sha256, 'digest');
    context.contract.work_items[0].node_ids = ['Missing'];
    assert.throws(() => bridge.attachFlowTrace(nodes, context), /unknown node/);
    context.contract.work_items[0].node_ids = [];
    assert.throws(() => bridge.attachFlowTrace(nodes, context), /no work item/);
    context.contract.work_items[0].node_ids = ['ChainController'];
    context.contract.work_items[0].requirement_ids = ['Missing'];
    assert.throws(() => bridge.attachFlowTrace(nodes, context), /unknown requirement/);
});

test('CLI persists L3 behavior and complete API contract in isolated output', t => {
    const dir = temp(t); const input = path.join(dir, 'input'); const output = path.join(dir, 'output');
    fs.mkdirSync(path.join(input, 'systems'), { recursive: true });
    const source = design();
    fs.writeFileSync(path.join(input, 'systems', 'chain.yaml'), serializeYaml(source));
    const result = spawnSync(process.execPath, [path.join(__dirname, 'design-to-code-bridge.js'), '--project', 'Fixture', '--input', input, '--output', output], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    const node = parseYaml(fs.readFileSync(path.join(output, 'nodes', 'ChainController.yaml'), 'utf8'));
    assert.deepEqual(node.behaviors, source.behaviors);
    assert.deepEqual(node.contract, source.contract);
    assert.deepEqual(node.logicFlow, source.logicFlow);
});

test('import has no CLI side effects', () => {
    const result = spawnSync(process.execPath, ['-e', `require(${JSON.stringify(path.join(__dirname, 'design-to-code-bridge.js'))})`], { encoding: 'utf8' });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(result.stdout, '');
});

test('an explicit strict flag without a path cannot silently select legacy mode', () => {
    for (const option of ['--project', '--input', '--output', '--flow-contract']) {
        assert.throws(() => bridge.parseArgs([option]), /requires a value/);
        assert.throws(() => bridge.parseArgs([option, '--help']), /requires a value/);
    }
    assert.throws(() => bridge.parseArgs(['--flow-contarct', 'fixture.json']), /Unknown option/);
});

function strictFixture(t) {
    const dir = temp(t), input = path.join(dir, 'input'), output = path.join(dir, 'output');
    fs.mkdirSync(path.join(input, 'systems'), { recursive: true });
    const source = design(); source.nodeId = 'IntentProbe';
    fs.writeFileSync(path.join(input, 'systems', 'probe.yaml'), serializeYaml(source));
    const contract = JSON.parse(fs.readFileSync(path.join(__dirname, 'templates', 'flow-contract.example.json'), 'utf8'));
    const contractPath = path.join(dir, 'flow-contract.json');
    fs.writeFileSync(contractPath, JSON.stringify(contract, null, 2));
    const argv = ['--project', contract.project, '--input', input, '--output', output, '--flow-contract', contractPath];
    const run = () => spawnSync(process.execPath, [path.join(__dirname, 'design-to-code-bridge.js'), ...argv], { encoding: 'utf8' });
    return { dir, input, output, source, contract, contractPath, argv, run };
}

test('strict CLI validates the real contract and pins full context in L2/L3 plus snapshot', t => {
    const f = strictFixture(t);
    const result = f.run(); assert.equal(result.status, 0, result.stderr);
    const l3 = parseYaml(fs.readFileSync(path.join(f.output, 'nodes', 'IntentProbe.yaml'), 'utf8'));
    const l2 = parseYaml(fs.readFileSync(path.join(f.output, 'system_spec.yaml'), 'utf8'));
    assert.deepEqual(l3.flow_trace, l2.systems[0].flow_trace);
    assert.deepEqual(l3.flow_trace.requirement_ids, ['R1']);
    assert.deepEqual(l3.flow_trace.decision_ids, ['D1']);
    assert.deepEqual(l3.flow_trace.acceptance_ids, ['A1']);
    const original = fs.readFileSync(f.contractPath);
    assert.deepEqual(fs.readFileSync(path.join(f.output, 'flow-contract.snapshot.json')), original);
    assert.equal(l3.flow_trace.contract_sha256, require('./lib/flow-contract').sha256(original));
    assert.deepEqual(l3.behaviors, f.source.behaviors);
    assert.deepEqual(l3.codeHints, {});
});

test('strict failures leave output absent, and invalid auto-discovered contracts cannot fall back', t => {
    const f = strictFixture(t);
    f.contract.project = 'OtherProject';
    fs.writeFileSync(f.contractPath, JSON.stringify(f.contract));
    let result = f.run(); assert.notEqual(result.status, 0); assert.match(result.stderr, /project/);
    assert.equal(fs.existsSync(f.output), false);
    f.contract.project = 'FlowTraceDemo'; f.contract.requirements[0].acceptance_ids = ['Missing'];
    fs.writeFileSync(f.contractPath, JSON.stringify(f.contract));
    result = f.run(); assert.notEqual(result.status, 0); assert.match(result.stderr, /validation failed/);
    assert.equal(fs.existsSync(f.output), false);
    fs.mkdirSync(f.output);
    fs.writeFileSync(path.join(f.output, 'flow-contract.json'), JSON.stringify(f.contract));
    f.argv.splice(-2);
    result = f.run(); assert.notEqual(result.status, 0);
    assert.deepEqual(fs.readdirSync(f.output), ['flow-contract.json']);
});

test('strict malformed design and missing work-node links fail before writes', t => {
    const f = strictFixture(t);
    fs.writeFileSync(path.join(f.input, 'systems', 'probe.yaml'), 'systems:\n  - IntentProbe\n');
    let result = f.run(); assert.notEqual(result.status, 0); assert.match(result.stderr, /object/);
    assert.equal(fs.existsSync(f.output), false);
    fs.writeFileSync(path.join(f.input, 'systems', 'probe.yaml'), serializeYaml(f.source));
    f.contract.work_items[0].node_ids = [];
    fs.writeFileSync(f.contractPath, JSON.stringify(f.contract));
    result = f.run(); assert.notEqual(result.status, 0); assert.match(result.stderr, /no work item/);
    assert.equal(fs.existsSync(f.output), false);
});

test('strict accepts BOM JSON while preserving exact snapshot bytes and hash', t => {
    const f = strictFixture(t);
    fs.writeFileSync(f.contractPath, '\uFEFF' + JSON.stringify(f.contract));
    const result = f.run(); assert.equal(result.status, 0, result.stderr);
    assert.deepEqual(fs.readFileSync(path.join(f.output, 'flow-contract.snapshot.json')), fs.readFileSync(f.contractPath));
    const node = parseYaml(fs.readFileSync(path.join(f.output, 'nodes', 'IntentProbe.yaml'), 'utf8'));
    assert.equal(node.flow_trace.contract_sha256, require('./lib/flow-contract').sha256(fs.readFileSync(f.contractPath)));
});

test('strict refuses stale node YAML without deleting it or overwriting other outputs', t => {
    const f = strictFixture(t);
    fs.mkdirSync(path.join(f.output, 'nodes'), { recursive: true });
    const stale = path.join(f.output, 'nodes', 'OldNode.yml');
    fs.writeFileSync(stale, 'old node bytes');
    fs.writeFileSync(path.join(f.output, 'system_spec.yaml'), 'previous output bytes');
    const result = f.run(); assert.notEqual(result.status, 0); assert.match(result.stderr, /explicit cleanup\/archive needed/);
    assert.equal(fs.readFileSync(stale, 'utf8'), 'old node bytes');
    assert.equal(fs.readFileSync(path.join(f.output, 'system_spec.yaml'), 'utf8'), 'previous output bytes');
    assert.equal(fs.existsSync(path.join(f.output, 'flow-contract.snapshot.json')), false);
});
