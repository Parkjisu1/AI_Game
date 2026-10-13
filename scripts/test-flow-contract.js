'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const {spawnSync} = require('child_process');
const {validateContract, acceptanceBasis, sha256} = require('./lib/flow-contract');
const example = require('./templates/flow-contract.example.json');
const fixture = () => structuredClone(example);
function check(c, options) { return validateContract(c, options); }
function includes(result, text) { assert.equal(result.ok, false); assert.ok(result.errors.some(e => e.includes(text)), JSON.stringify(result)); }
function evidenceFixture(t) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-flow-test-'));
    t.after(() => {
        const resolved = path.resolve(dir);
        assert.equal(path.dirname(resolved), path.resolve(os.tmpdir()));
        assert.ok(path.basename(resolved).startsWith('ai-flow-test-'));
        fs.rmSync(resolved, {recursive: true, force: true});
    });
    fs.writeFileSync(path.join(dir, 'build.txt'), 'evaluated synthetic input');
    fs.writeFileSync(path.join(dir, 'result.txt'), 'synthetic comparison passed');
    const c = fixture(), ac = c.acceptance[0];
    ac.input_artifacts = [{locator: 'build.txt', sha256: sha256('evaluated synthetic input')}];
    ac.evidence = [{locator: 'result.txt', kind: 'test', sha256: sha256('synthetic comparison passed')}];
    ac.status = 'passed'; ac.basis_hash = acceptanceBasis(c, ac);
    return {dir, c};
}
test('minimal handoff passes but pending acceptance is blocked', () => {
    const c = fixture(); assert.equal(check(c).verdict, 'HANDOFF_STRUCTURE_PASS');
    includes(check(c, {stage: 'acceptance'}), 'not_run');
});
test('malformed top-level and IDs fail without throwing', () => {
    for (const c of [null, [], {}, {...fixture(), claims: [null]}, {...fixture(), version: 2}]) assert.equal(check(c).ok, false);
    const c = fixture(); c.requirements.push(structuredClone(c.requirements[0])); includes(check(c), 'duplicate id');
});
test('broken references and missing work cannot pass handoff', () => {
    const c = fixture(); c.requirements[0].decision_ids = ['missing']; includes(check(c), 'unknown missing');
    const d = fixture(); d.intent.goals.push({id: 'G2', statement: 'Untraced user goal'}); includes(check(d), 'no requirement');
    const e = fixture(); e.work_items[0].requirement_ids = []; includes(check(e), 'nonempty');
});
test('observed needs evidence; inference does not become verified by confidence', () => {
    const c = fixture(); c.references.push({id: 'S1', source: 'source.cs', version: 'hash-or-build-id'});
    c.claims.push({id: 'C1', reference_id: 'S1', statement: 'Candidate rule', basis: 'inferred', verification: 'untested', confidence: 1, evidence: []});
    assert.equal(check(c).ok, true); assert.ok(check(c).warnings.some(w => w.includes('untested')));
    c.claims[0].basis = 'observed'; includes(check(c), 'evidence is required');
});
test('keep requires parity, omit cannot drive implementation', () => {
    const c = fixture(); c.claims.push({id: 'C1', statement: 'Reference behavior is still unknown', basis: 'unknown', verification: 'untested', evidence: []});
    c.decisions[0].claim_ids = ['C1']; c.decisions[0].mode = 'keep'; includes(check(c), 'parity');
    c.acceptance[0].kind = 'parity'; assert.equal(check(c).ok, true);
    c.decisions[0].mode = 'omit'; includes(check(c), 'omitted');
});
test('acceptance requires pinned evaluated inputs, result and matching basis', t => {
    const {c, dir} = evidenceFixture(t); const opts = {stage: 'acceptance', baseDir: dir};
    assert.equal(check(c, opts).verdict, 'EVIDENCE_RECORDS_PASS');
    delete c.acceptance[0].basis_hash; includes(check(c, opts), 'basis_hash');
    c.acceptance[0].basis_hash = acceptanceBasis(c, c.acceptance[0]);
    fs.writeFileSync(path.join(dir, 'build.txt'), 'changed input'); includes(check(c, opts), 'stale file');
});
test('changed goal invalidates prior evidence even if file hashes still match', t => {
    const {c, dir} = evidenceFixture(t); c.intent.goals[0].statement = 'Different desired result';
    includes(check(c, {stage: 'acceptance', baseDir: dir}), 'stale basis_hash');
});
test('unrelated art requirement does not stale technical result; scope stays separate', t => {
    const {c, dir} = evidenceFixture(t); const old = c.acceptance[0].basis_hash;
    c.intent.goals.push({id: 'G2', statement: 'Readable silhouette'});
    c.decisions.push({id: 'D2', mode: 'new', goal_ids: ['G2'], claim_ids: [], rationale: 'Art intent', expected_difference: 'New art'});
    c.requirements.push({id: 'R2', goal_ids: ['G2'], decision_ids: ['D2'], statement: 'Readable in target camera', category: 'art', delivery_scope: 'production_experience', acceptance_ids: ['A2']});
    c.work_items.push({id: 'W2', discipline: 'art', deliverable: 'Camera capture', requirement_ids: ['R2']});
    c.acceptance.push({id: 'A2', kind: 'art', scope: 'production_experience', method: 'Evaluate target camera screenshot', expected: 'Specified silhouette readable', status: 'not_run', evidence: []});
    assert.equal(acceptanceBasis(c, c.acceptance[0]), old);
    assert.equal(check(c, {stage: 'acceptance', scope: 'technical', baseDir: dir}).ok, true);
    includes(check(c, {stage: 'acceptance', baseDir: dir}), 'A2: not_run');
});
test('self-declared pass and nonexistent scopes do not bypass evidence', () => {
    const c = fixture(); c.acceptance[0].status = 'passed'; includes(check(c), 'evidence is required');
    includes(check(fixture(), {stage: 'acceptance', scope: 'typo'}), 'Unknown scope');
    includes(check(fixture(), {stage: 'acceptance', scope: 'market'}), 'No acceptance cases');
});
test('structure cannot accept market and placeholder cannot satisfy production requirement', () => {
    const c = fixture(); c.requirements[0].category = 'market'; includes(check(c), 'cannot accept market');
    const d = fixture(); d.requirements[0].delivery_scope = 'production_experience'; includes(check(d), 'delivery_scope differs');
});
test('changed deliverable invalidates prior result', t => {
    const {c, dir} = evidenceFixture(t); c.work_items[0].deliverable = 'Different build';
    includes(check(c, {stage: 'acceptance', baseDir: dir}), 'stale basis_hash');
});
test('one executed case does not hide a mandatory not-applicable case', t => {
    const {c, dir} = evidenceFixture(t);
    c.acceptance.push({...structuredClone(c.acceptance[0]), id: 'A2', status: 'not_applicable', reason: 'Not ready'});
    c.requirements[0].acceptance_ids.push('A2'); c.acceptance[0].basis_hash = acceptanceBasis(c, c.acceptance[0]);
    includes(check(c, {stage: 'acceptance', baseDir: dir}), 'not_applicable cannot satisfy');
});
test('art parity accepts pinned review evidence without pretending runtime testing', t => {
    const {c, dir} = evidenceFixture(t);
    c.requirements[0].category = 'art'; c.acceptance[0].kind = 'parity'; c.acceptance[0].evidence[0].kind = 'review';
    c.acceptance[0].basis_hash = acceptanceBasis(c, c.acceptance[0]);
    assert.equal(check(c, {stage: 'acceptance', baseDir: dir}).ok, true);
});
test('all not-applicable is not a completed acceptance', () => {
    const c = fixture(); Object.assign(c.acceptance[0], {status: 'not_applicable', reason: 'Demonstration only'});
    includes(check(c, {stage: 'acceptance'}), 'No executed');
});
test('runtime/parity cannot pass with only a review file', t => {
    const {c, dir} = evidenceFixture(t); const ac = c.acceptance[0]; ac.kind = 'runtime'; ac.evidence[0].kind = 'review';
    ac.basis_hash = acceptanceBasis(c, ac); includes(check(c, {stage: 'acceptance', baseDir: dir}), 'test or trace');
});
test('evidence tampering and remote links cannot pass local integrity gate', t => {
    const {c, dir} = evidenceFixture(t); const opts = {stage: 'acceptance', baseDir: dir};
    fs.writeFileSync(path.join(dir, 'result.txt'), 'altered result'); includes(check(c, opts), 'stale file');
    c.acceptance[0].evidence[0].locator = 'https://example.com/result'; includes(check(c, opts), 'captured locally');
});
test('CLI succeeds for example, rejects unknown flags and pending acceptance', () => {
    const cli = path.join(__dirname, 'validate-flow-contract.js');
    const input = path.join(__dirname, 'templates/flow-contract.example.json');
    const run = args => spawnSync(process.execPath, [cli, ...args], {encoding: 'utf8'});
    assert.equal(run(['--input', input]).status, 0);
    assert.equal(run(['--input', input, '--stage', 'acceptance']).status, 1);
    assert.equal(run(['--input', input, '--typo', 'true']).status, 1);
});

test('linked virtual-player criteria change stales acceptance, unrelated criteria do not', t => {
    const {c, dir} = evidenceFixture(t);
    c.virtual_player = {criteria: [{id: 'V1', metric: 'action_frequency', min: 0, requirement_ids: ['R1'], acceptance_ids: ['A1']}]};
    c.acceptance[0].basis_hash = acceptanceBasis(c, c.acceptance[0]);
    const before = c.acceptance[0].basis_hash;
    c.virtual_player.criteria.push({id: 'V2', metric: 'session_length', min: 1, acceptance_ids: ['Other']});
    assert.equal(acceptanceBasis(c, c.acceptance[0]), before);
    c.virtual_player.criteria[0].min = 2;
    includes(check(c, {stage: 'acceptance', baseDir: dir}), 'stale basis_hash');
});
