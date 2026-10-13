#!/usr/bin/env node
'use strict';

// Compare VP observations with explicit project criteria; never diagnose enjoyment or root cause.
const fs = require('fs');
const path = require('path');
const { randomUUID } = require('crypto');
const { parseYaml } = require('./lib/yaml-utils');
const { writeJsonAtomic } = require('./lib/safe-io');
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
const own = (v, key) => object(v) && Object.prototype.hasOwnProperty.call(v, key);
const finite = v => typeof v === 'number' && Number.isFinite(v);
const text = v => typeof v === 'string' && v.trim().length > 0;
const METRICS = ['session_length', 'action_frequency', 'action_variety', 'engagement_hooks', 'failure_rate'];

/* contract.virtual_player.criteria, or explicit VP input virtual_player.criteria:
 * [{id, metric, requirement_ids, acceptance_ids, min?, max?, expected_hooks?, point?}]
 * Inclusive numeric bounds require min or max. Units: seconds, actions/minute,
 * exported variety score/count, failure ratio [0,1]. Failure ratios also need point.
 * Hooks need expected_hooks (including []). No global numeric or hook defaults.
 * This bridge validates criterion definitions and links in addition to handoff validation.
 */
function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    const flag = argv[i];
    if (flag === '--help' || flag === '-h') { args.help = true; continue; }
    if (!['--input', '--project', '--output', '--flow-contract'].includes(flag)) throw new Error(`Unknown option: ${flag}`);
    const value = argv[++i];
    if (!value || value.startsWith('-')) throw new Error(`${flag} requires a value`);
    args[flag.slice(2)] = value;
  }
  return args;
}

function readFirst(data, keys, prefix = '') {
  for (const key of keys) if (own(data, key)) return { present: true, value: data[key], locator: prefix + key };
  return { present: false, value: null, locator: prefix + keys[0] };
}

function observations(data) {
  const sessions = readFirst(data, ['sessions', 'session_data']);
  const actions = readFirst(data, ['actions', 'action_data']);
  const failures = readFirst(data, ['failures', 'failure_points', 'failure_data']);
  const values = {
    session_length: readFirst(sessions.value, ['avg_length', 'average_session'], sessions.locator + '.'),
    action_frequency: readFirst(actions.value, ['frequency', 'actions_per_minute'], actions.locator + '.'),
    action_variety: readFirst(actions.value, ['variety_score', 'unique_action_types'], actions.locator + '.'),
    engagement_hooks: readFirst(sessions.value, ['engagement_hooks'], sessions.locator + '.'),
  };
  // A hook dictionary may be a definition table or zero counts; keys alone do not prove observed events.
  const list = Array.isArray(failures.value) ? failures.value
    : object(failures.value) ? Object.entries(failures.value).map(([point, v]) => object(v) ? { ...v, point } : { point, rate: v }) : [];
  values.failure_rates = list.map((failure, i) => ({
    point: typeof failure === 'string' ? failure : readFirst(failure, ['point', 'location']).value,
    ...readFirst(failure, ['rate', 'drop_off_rate'], `${failures.locator}[${i}].`),
  }));
  return values;
}

function selectCriteria(data, contract) {
  if (contract) return { source: 'flow_contract', criteria: contract.virtual_player?.criteria };
  if (own(data, 'virtual_player')) return { source: 'explicit_input', criteria: data.virtual_player?.criteria };
  const sessions = readFirst(data, ['sessions', 'session_data']).value;
  if (own(sessions, 'target_length')) {
    const target = sessions.target_length;
    const tolerance = own(sessions, 'tolerance_seconds') ? sessions.tolerance_seconds
      : own(sessions, 'tolerance_ratio') && finite(target) && finite(sessions.tolerance_ratio) ? Math.abs(target) * sessions.tolerance_ratio : null;
    const criterion = { id: 'input_session_target', metric: 'session_length', target, tolerance };
    if (finite(target) && target >= 0 && finite(tolerance) && tolerance >= 0) {
      criterion.min = Math.max(0, target - tolerance); criterion.max = target + tolerance;
    }
    return { source: 'explicit_input_target', criteria: [criterion] };
  }
  return { source: 'undefined', criteria: undefined };
}

function definitionIssues(c) {
  if (!object(c)) return ['Criterion must be an object'];
  const issues = [];
  if (!text(c.id)) issues.push('id is required');
  if (!METRICS.includes(c.metric)) issues.push('Unsupported or missing metric');
  if (c.metric === 'engagement_hooks') {
    if (!Array.isArray(c.expected_hooks) || c.expected_hooks.some(h => !text(h))) issues.push('expected_hooks must be a string array; [] explicitly requires no hooks');
  } else {
    if (!own(c, 'min') && !own(c, 'max')) issues.push('Explicit min/max required; a target without tolerance does not define a pass range');
    for (const key of ['min', 'max']) if (own(c, key) && (!finite(c[key]) || c[key] < 0)) issues.push(`${key} must be a finite nonnegative number`);
    if (finite(c.min) && finite(c.max) && c.min > c.max) issues.push('min must not exceed max');
    if (c.metric === 'failure_rate') {
      if (!text(c.point)) issues.push('failure_rate needs point');
      if (c.min > 1 || c.max > 1) issues.push('failure_rate bounds must be in [0,1]');
    }
  }
  return issues;
}

function checkLinks(criteria, contract) {
  const seen = new Set();
  for (const c of criteria) {
    if (!object(c)) continue;
    if (seen.has(c.id)) throw new Error(`Duplicate VP criterion id: ${c.id}`);
    seen.add(c.id);
    if (!contract) continue;
    for (const key of ['requirement_ids', 'acceptance_ids']) {
      if (!Array.isArray(c[key]) || !c[key].length || c[key].some(id => !text(id))) throw new Error(`${c.id}: ${key} must be a nonempty ID array`);
    }
    const reqs = c.requirement_ids.map(id => {
      const req = contract.requirements.find(item => item.id === id);
      if (!req) throw new Error(`${c.id}: unknown requirement ${id}`);
      return req;
    });
    for (const id of c.acceptance_ids) {
      if (!contract.acceptance.some(item => item.id === id) || !reqs.some(req => req.acceptance_ids.includes(id))) throw new Error(`${c.id}: acceptance ${id} is not linked to its requirements`);
    }
    if (reqs.some(req => !req.acceptance_ids.some(id => c.acceptance_ids.includes(id)))) throw new Error(`${c.id}: requirement has no selected acceptance`);
  }
}

function compare(c, values) {
  const issues = definitionIssues(c);
  const base = { criterion_id: c?.id ?? null, metric: c?.metric ?? null,
    requirement_ids: c?.requirement_ids ?? [], acceptance_ids: c?.acceptance_ids ?? [],
    definition: c ?? null, status: 'missing_definition', issues };
  if (issues.length) return base;
  const matches = c.metric === 'failure_rate' ? values.failure_rates.filter(item => item.point === c.point) : [];
  const observed = c.metric === 'failure_rate' ? matches[0] || { present: false, value: null } : values[c.metric];
  const actual = observed.value, hooks = c.metric === 'engagement_hooks';
  const valid = observed.present && (hooks ? Array.isArray(actual) && actual.every(text)
    : finite(actual) && actual >= 0 && (c.metric !== 'failure_rate' || actual <= 1));
  if (!valid || matches.length > 1) return { ...base, status: 'missing_evidence', actual, locator: observed.locator ?? null,
    issues: [matches.length > 1 ? 'Multiple failure observations need an explicit aggregation' : !observed.present ? 'Observation absent' : actual === null ? 'Observation explicitly null' : 'Observation invalid for this metric'] };
  const within = hooks ? c.expected_hooks.every(hook => actual.includes(hook))
    : (!own(c, 'min') || actual >= c.min) && (!own(c, 'max') || actual <= c.max);
  return { ...base, status: within ? 'within_declared_range' : 'outside_declared_range', actual, locator: observed.locator, issues: [],
    ...(hooks ? { missing_hooks: c.expected_hooks.filter(hook => !actual.includes(hook)) } : {}) };
}

function transform(data, options = {}) {
  if (!object(data)) throw new Error('VP input must be an object');
  const { project, inputFile = null, contract = null, contractTrace = null } = options;
  if (!text(project)) throw new Error('project is required');
  if (contract && contract.project !== project) throw new Error('Flow contract project mismatch');
  if (own(data, 'project') && data.project !== project) throw new Error('VP input project mismatch');
  const values = observations(data), selected = selectCriteria(data, contract), criteria = selected.criteria;
  if (Array.isArray(criteria)) checkLinks(criteria, contract);
  const results = !Array.isArray(criteria) || !criteria.length ? [{ criterion_id: null, metric: null, status: 'missing_definition',
    issues: ['No explicit virtual_player.criteria; no project target judgment can be made'] }] : criteria.map(c => compare(c, values));
  const generated = new Date().toISOString();
  const feedbackItems = results.filter(r => r.status !== 'within_declared_range').map(r => ({
    id: `vpb_${randomUUID()}`, timestamp: generated, source: 'virtual_player_bridge', designId: data.design_id ?? `${project}_design`,
    feedback_category: r.status === 'outside_declared_range' ? 'COMPARISON' : 'EVIDENCE',
    feedback_type: r.status.toUpperCase(), severity: 'UNASSESSED',
    description: r.status === 'outside_declared_range' ? `Observed ${r.metric} is outside explicitly declared bounds; cause and player impact are unverified.` : r.issues.join('; '),
    comparison: r,
  }));
  return {
    source: 'virtual_player_bridge', project, input_file: inputFile, generated_at: generated,
    evaluation_scope: 'declared_metric_comparison_only',
    limitation: 'VP observations and numeric comparisons do not establish player enjoyment, causal diagnosis, engine quality, or market acceptance.',
    criteria_source: selected.source, contract_trace: contractTrace, observations: values, comparisons: results,
    vp_metadata: { design_id: data.design_id ?? null, export_date: data.export_date ?? data.timestamp ?? null,
      player_count: readFirst(data, ['player_count', 'session_count']).value },
    feedback_items: feedbackItems,
    summary: { total: feedbackItems.length, by_status: countBy(results, 'status'), by_category: countBy(feedbackItems, 'feedback_category'),
      by_severity: countBy(feedbackItems, 'severity'), critical_count: 0, severity_assessed: false },
  };
}

function countBy(values, field) {
  return values.reduce((counts, v) => { const key = v[field]; counts[key] = (counts[key] || 0) + 1; return counts; }, {});
}

function main(argv = process.argv.slice(2)) {
  const args = parseArgs(argv);
  if (args.help) { console.log('node virtual-player-bridge.js --input <yaml/json> --project <name> [--output <json>] [--flow-contract <json>]'); return; }
  if (!args.input || !args.project) throw new Error('--input and --project are required');
  const inputPath = path.resolve(args.input), raw = fs.readFileSync(inputPath, 'utf8');
  const data = /\.json$/i.test(inputPath) ? JSON.parse(raw.replace(/^\uFEFF/, '')) : parseYaml(raw);
  const output = args.output || path.join('E:/AI/projects', args.project, 'feedback/design/vp_feedback.json');
  const contractPath = args['flow-contract'] || path.join('E:/AI/projects', args.project, 'designs/flow-contract.json');
  const { sha256 } = require('./lib/flow-contract');
  let contract = null, contractTrace = null;
  if (args['flow-contract'] || fs.existsSync(contractPath)) {
    const content = fs.readFileSync(contractPath, 'utf8');
    contract = JSON.parse(content.replace(/^\uFEFF/, ''));
    const result = require('./lib/flow-contract').validateContract(contract, { stage: 'handoff', baseDir: path.dirname(path.resolve(contractPath)) });
    if (!result.ok) throw new Error(`Flow contract invalid: ${JSON.stringify(result.errors)}`);
    if (contract.project !== args.project) throw new Error('Flow contract project mismatch');
    contractTrace = { path: path.resolve(contractPath), sha256: sha256(content), acceptance_basis: result.acceptance_basis };
  }
  const feedback = transform(data, { project: args.project, inputFile: inputPath, contract, contractTrace });
  // Preserve exact input for review; do not write DB records or promote acceptance statuses.
  feedback.input_snapshot = { sha256: sha256(raw), raw };
  writeJsonAtomic(output, feedback);
  console.log(JSON.stringify({ output, evaluation_scope: feedback.evaluation_scope, summary: feedback.summary }));
  return feedback;
}

module.exports = { parseArgs, observations, selectCriteria, definitionIssues, checkLinks, compare, transform, main };
if (require.main === module) {
  try { main(); } catch (error) { console.error(error.message); process.exitCode = 1; }
}
