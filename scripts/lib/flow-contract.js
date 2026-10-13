'use strict';

// A handoff/evidence integrity check, not an oracle for fun, factual truth or market success.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const CATEGORIES = ['technical', 'behavior', 'art', 'experience', 'market'];
const DELIVERY_SCOPES = ['placeholder_functional', 'production_experience'];
const KINDS_BY_CATEGORY = {
    technical: ['structure', 'runtime', 'parity', 'delta'],
    behavior: ['runtime', 'parity', 'delta'], art: ['art', 'parity', 'delta'],
    experience: ['experience', 'parity', 'delta'], market: ['market'],
};
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const nonempty = value => typeof value === 'string' && value.trim().length > 0;
const sha256 = value => crypto.createHash('sha256').update(value).digest('hex');
function stable(value) {
    if (Array.isArray(value)) return value.map(stable);
    if (!object(value)) return value;
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])]));
}

// Hash related work/requirements; shared intent constraints and assumptions deliberately affect all cases.
function acceptanceBasis(contract, acceptance) {
    const requirements = contract.requirements.filter(r => r.acceptance_ids.includes(acceptance.id));
    const decisionIds = new Set(requirements.flatMap(r => r.decision_ids));
    const decisions = contract.decisions.filter(d => decisionIds.has(d.id));
    const goalIds = new Set([...requirements.flatMap(r => r.goal_ids), ...decisions.flatMap(d => d.goal_ids)]);
    const claimIds = new Set(decisions.flatMap(d => d.claim_ids));
    const claims = contract.claims.filter(c => claimIds.has(c.id));
    const referenceIds = new Set(claims.map(c => c.reference_id));
    const vpCriteria = (Array.isArray(contract.virtual_player?.criteria) ? contract.virtual_player.criteria : []).filter(c =>
        c && Array.isArray(c.acceptance_ids) && c.acceptance_ids.includes(acceptance.id));
    return sha256(JSON.stringify(stable({
        version: contract.version, project: contract.project,
        user_request: contract.intent.user_request,
        non_goals: contract.intent.non_goals, constraints: contract.intent.constraints,
        assumptions: contract.intent.assumptions,
        goals: contract.intent.goals.filter(g => goalIds.has(g.id)),
        requirements, decisions, claims,
        work_items: contract.work_items.filter(w => w.requirement_ids.some(id => requirements.some(r => r.id === id))),
        references: contract.references.filter(r => referenceIds.has(r.id)),
        ...(vpCriteria.length ? {virtual_player_criteria: vpCriteria} : {}),
        acceptance: {
            id: acceptance.id, kind: acceptance.kind, scope: acceptance.scope,
            method: acceptance.method, expected: acceptance.expected,
            input_artifacts: acceptance.input_artifacts || [],
        },
    })));
}

function validateContract(contract, options = {}) {
    const stage = options.stage || 'handoff';
    const baseDir = options.baseDir || process.cwd();
    const errors = [], warnings = [], acceptance_basis = {};
    const error = message => errors.push(message);
    const result = () => ({ok: errors.length === 0, stage, scope: options.scope || 'all',
        verdict: errors.length ? 'BLOCKED' : stage === 'handoff' ? 'HANDOFF_STRUCTURE_PASS' : 'EVIDENCE_RECORDS_PASS',
        limitation: 'Checks trace links and pinned local evidence, not evidence truth, game quality or market success.',
        delivery_scopes: Array.isArray(contract?.requirements) ? [...new Set(contract.requirements.filter(r => object(r) && (!options.scope || r.category === options.scope)).map(r => r.delivery_scope))] : [],
        errors, warnings, acceptance_basis});
    if (!['handoff', 'acceptance'].includes(stage)) error(`Unknown stage: ${stage}`);
    if (options.scope && !CATEGORIES.includes(options.scope)) error(`Unknown scope: ${options.scope}`);
    if (!object(contract)) { error('Contract must be an object'); return result(); }
    if (contract.version !== 1) error('version must be 1');
    if (!nonempty(contract.project)) error('project is required');
    if (!object(contract.intent)) { error('intent is required'); return result(); }
    if (!nonempty(contract.intent.user_request)) error('intent.user_request is required');
    for (const key of ['non_goals', 'constraints', 'assumptions']) {
        if (!Array.isArray(contract.intent[key])) error(`intent.${key} must be an array (empty is allowed)`);
    }
    const maps = {};
    const lists = {goals: contract.intent.goals, references: contract.references, claims: contract.claims,
        decisions: contract.decisions, requirements: contract.requirements,
        work_items: contract.work_items, acceptance: contract.acceptance};
    for (const [name, list] of Object.entries(lists)) {
        maps[name] = new Map();
        if (!Array.isArray(list)) { error(`${name} must be an array`); continue; }
        if (!['references', 'claims'].includes(name) && !list.length) error(`${name} must not be empty`);
        for (const entry of list) {
            if (!object(entry) || !nonempty(entry.id)) { error(`${name}: object with id required`); continue; }
            if (maps[name].has(entry.id)) error(`${name}: duplicate id ${entry.id}`);
            maps[name].set(entry.id, entry);
        }
    }
    if (errors.length) return result();
    function textFields(entry, fields) {
        for (const field of fields) if (!nonempty(entry[field])) error(`${entry.id}.${field} is required`);
    }
    function links(entry, field, target, allowEmpty = false) {
        if (!Array.isArray(entry[field]) || (!allowEmpty && !entry[field].length)) {
            error(`${entry.id}.${field} must be ${allowEmpty ? 'an' : 'a nonempty'} array`); return [];
        }
        for (const id of entry[field]) if (!maps[target].has(id)) error(`${entry.id}.${field}: unknown ${id}`);
        if (new Set(entry[field]).size !== entry[field].length) error(`${entry.id}.${field}: duplicate link`);
        return entry[field];
    }
    function enumField(entry, field, allowed) {
        if (!allowed.includes(entry[field])) error(`${entry.id}.${field}: expected ${allowed.join('|')}`);
    }
    function evidenceShape(entry, required) {
        if (!Array.isArray(entry.evidence)) { error(`${entry.id}.evidence must be an array`); return; }
        if (required && !entry.evidence.length) error(`${entry.id}: evidence is required`);
        for (const ev of entry.evidence) if (!object(ev) || !nonempty(ev.locator) || !nonempty(ev.kind)) {
            error(`${entry.id}: evidence needs locator and kind`);
        }
    }
    for (const goal of lists.goals) textFields(goal, ['statement']);
    for (const ref of lists.references) textFields(ref, ['source', 'version']);
    for (const claim of lists.claims) {
        textFields(claim, ['statement']);
        enumField(claim, 'basis', ['observed', 'inferred', 'designed', 'unknown']);
        enumField(claim, 'verification', ['untested', 'reproduced', 'contradicted']);
        if (claim.reference_id && !maps.references.has(claim.reference_id)) error(`${claim.id}: unknown reference_id`);
        if (['observed', 'inferred'].includes(claim.basis) && !claim.reference_id) error(`${claim.id}: reference_id required`);
        evidenceShape(claim, claim.basis === 'observed' || claim.verification === 'reproduced');
        if (claim.basis === 'inferred' && !nonempty(claim.competing_explanation)) warnings.push(`${claim.id}: competing explanation not recorded`);
        if (claim.verification !== 'reproduced') warnings.push(`${claim.id}: ${claim.verification}; do not treat as confirmed`);
    }
    for (const decision of lists.decisions) {
        enumField(decision, 'mode', ['keep', 'adapt', 'replace', 'omit', 'new']);
        textFields(decision, ['rationale', 'expected_difference']);
        links(decision, 'goal_ids', 'goals');
        links(decision, 'claim_ids', 'claims', decision.mode === 'new');
    }
    for (const req of lists.requirements) {
        textFields(req, ['statement']);
        enumField(req, 'category', CATEGORIES);
        enumField(req, 'delivery_scope', DELIVERY_SCOPES);
        links(req, 'goal_ids', 'goals'); links(req, 'decision_ids', 'decisions');
        links(req, 'acceptance_ids', 'acceptance');
    }
    for (const work of lists.work_items) {
        textFields(work, ['discipline', 'deliverable']);
        links(work, 'requirement_ids', 'requirements');
        if (work.node_ids !== undefined && (!Array.isArray(work.node_ids) || work.node_ids.some(id => !nonempty(id)))) {
            error(`${work.id}.node_ids must be an array of strings`);
        }
    }
    for (const ac of lists.acceptance) {
        textFields(ac, ['method', 'expected']);
        enumField(ac, 'kind', ['parity', 'delta', 'runtime', 'art', 'experience', 'market', 'structure']);
        enumField(ac, 'scope', DELIVERY_SCOPES);
        enumField(ac, 'status', ['not_run', 'passed', 'failed', 'not_applicable', 'stale']);
        evidenceShape(ac, ac.status === 'passed');
        if (ac.status === 'not_applicable' && !nonempty(ac.reason)) error(`${ac.id}: not_applicable needs reason`);
        if (ac.input_artifacts !== undefined && (!Array.isArray(ac.input_artifacts) ||
            ac.input_artifacts.some(a => !object(a) || !nonempty(a.locator) || !/^[a-f0-9]{64}$/i.test(a.sha256 || '')))) {
            error(`${ac.id}.input_artifacts needs locator and sha256`);
        }
    }
    if (errors.length) return result();
    for (const goal of lists.goals) if (!lists.requirements.some(r => r.goal_ids.includes(goal.id))) error(`${goal.id}: no requirement traces this goal`);
    for (const req of lists.requirements) {
        if (!lists.work_items.some(w => w.requirement_ids.includes(req.id))) error(`${req.id}: no work item`);
        for (const id of req.acceptance_ids) {
            const ac = maps.acceptance.get(id);
            if (!KINDS_BY_CATEGORY[req.category].includes(ac.kind)) error(`${req.id}: ${ac.kind} cannot accept ${req.category}`);
            if (req.delivery_scope !== ac.scope) error(`${req.id}: delivery_scope differs from ${id}.scope`);
        }
        for (const id of req.decision_ids) {
            const decision = maps.decisions.get(id);
            if (!req.goal_ids.some(g => decision.goal_ids.includes(g))) error(`${req.id}: decision ${id} belongs to unrelated goals`);
            if (decision.mode === 'omit') error(`${req.id}: omitted decision ${id} cannot drive implementation`);
            if (decision.mode === 'keep' && !req.acceptance_ids.some(a => maps.acceptance.get(a).kind === 'parity')) {
                error(`${req.id}: keep requires a parity acceptance case`);
            }
        }
    }
    for (const decision of lists.decisions) if (decision.mode !== 'omit' && !lists.requirements.some(r => r.decision_ids.includes(decision.id))) {
        error(`${decision.id}: decision has no requirement`);
    }
    for (const ac of lists.acceptance) {
        if (!lists.requirements.some(r => r.acceptance_ids.includes(ac.id))) error(`${ac.id}: acceptance is not traced to a requirement`);
        acceptance_basis[ac.id] = acceptanceBasis(contract, ac);
    }
    function pinnedFile(record, owner) {
        if (!object(record) || !nonempty(record.locator) || !/^[a-f0-9]{64}$/i.test(record.sha256 || '')) {
            error(`${owner}: local file locator and sha256 required`); return;
        }
        if (/^[a-z]+:\/\//i.test(record.locator)) { error(`${owner}: remote evidence must be captured locally before acceptance`); return; }
        try {
            const file = path.resolve(baseDir, record.locator);
            if (!fs.statSync(file).isFile()) throw new Error('not a file');
            if (sha256(fs.readFileSync(file)) !== record.sha256.toLowerCase()) error(`${owner}: stale file ${record.locator}`);
        } catch (err) { error(`${owner}: unreadable file ${record.locator}: ${err.message}`); }
    }
    if (stage === 'acceptance') {
        const selected = lists.acceptance.filter(ac => lists.requirements.some(r =>
            (!options.scope || r.category === options.scope) && r.acceptance_ids.includes(ac.id)));
        if (!selected.length) error('No acceptance cases in selected scope');
        if (selected.length && selected.every(ac => ac.status === 'not_applicable')) error('No executed acceptance case in selected scope');
        for (const ac of selected) {
            if (ac.status === 'not_applicable') { error(`${ac.id}: not_applicable cannot satisfy a selected requirement; revise its scope explicitly`); continue; }
            if (ac.status !== 'passed') { error(`${ac.id}: ${ac.status}`); continue; }
            if (ac.basis_hash !== acceptance_basis[ac.id]) error(`${ac.id}: missing/stale basis_hash; rerun against current requirements`);
            if (!ac.input_artifacts || !ac.input_artifacts.length) error(`${ac.id}: pin evaluated input_artifacts`);
            for (const artifact of ac.input_artifacts || []) pinnedFile(artifact, ac.id);
            for (const evidence of ac.evidence) pinnedFile(evidence, ac.id);
            const executable = lists.requirements.some(r => ['technical', 'behavior'].includes(r.category) && r.acceptance_ids.includes(ac.id));
            if ((ac.kind === 'runtime' || (executable && ['parity', 'delta'].includes(ac.kind))) && !ac.evidence.some(e => ['test', 'trace'].includes(e.kind))) {
                error(`${ac.id}: executable behavior evidence (test or trace) required`);
            }
        }
    }
    return result();
}

module.exports = {validateContract, acceptanceBasis, sha256, CATEGORIES};
