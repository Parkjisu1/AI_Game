#!/usr/bin/env node
/**
 * track-tokens.js — Simple token usage logger for AI Workflow
 *
 * Logs API token usage per project/agent to JSONL file.
 * Internal tool — no billing, no alerts, just visibility.
 *
 * Usage:
 *   node scripts/track-tokens.js log --project BalloonFlow --agent designer --model sonnet --input 15000 --output 3200
 *   node scripts/track-tokens.js summary --project BalloonFlow
 *   node scripts/track-tokens.js summary --since 2026-04-01
 *   node scripts/track-tokens.js summary  (all-time, all projects)
 */

const fs = require('fs');
const path = require('path');

const LOG_DIR = path.resolve(__dirname, '../logs');
const LOG_FILE = path.join(LOG_DIR, 'token-usage.jsonl');

const PRICING = {
  'opus':   { input: 15.00, output: 75.00 },
  'sonnet': {  input:  3.00, output: 15.00 },
  'haiku':  { input:  0.80, output:  4.00 },
};

function ensureLogDir() {
  if (!fs.existsSync(LOG_DIR)) fs.mkdirSync(LOG_DIR, { recursive: true });
}

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      const key = argv[i].slice(2);
      const val = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : true;
      args[key] = val;
      if (val !== true) i++;
    }
  }
  return args;
}

function estimateCost(model, inputTokens, outputTokens) {
  const m = model.toLowerCase();
  const key = Object.keys(PRICING).find(k => m.includes(k));
  if (!key) return null;
  const rate = PRICING[key];
  return {
    input_usd:  (inputTokens  / 1_000_000) * rate.input,
    output_usd: (outputTokens / 1_000_000) * rate.output,
    total_usd: ((inputTokens  / 1_000_000) * rate.input) +
               ((outputTokens / 1_000_000) * rate.output),
  };
}

function logUsage(args) {
  ensureLogDir();
  const input  = parseInt(args.input  || 0, 10);
  const output = parseInt(args.output || 0, 10);
  const entry = {
    timestamp: new Date().toISOString(),
    project: args.project || 'unknown',
    agent:   args.agent   || 'unknown',
    model:   args.model   || 'unknown',
    input_tokens:  input,
    output_tokens: output,
    cost: estimateCost(args.model || '', input, output),
    note: args.note || null,
  };
  fs.appendFileSync(LOG_FILE, JSON.stringify(entry) + '\n');
  console.log(`Logged: ${entry.project} / ${entry.agent} / ${entry.model} — $${entry.cost ? entry.cost.total_usd.toFixed(4) : 'n/a'}`);
}

function summary(args) {
  if (!fs.existsSync(LOG_FILE)) {
    console.log('No usage log yet.');
    return;
  }
  const lines = fs.readFileSync(LOG_FILE, 'utf-8').split('\n').filter(Boolean);
  const since = args.since ? new Date(args.since) : null;
  const project = args.project || null;

  const byProject = {};
  const byAgent = {};
  const byModel = {};
  let totalCost = 0;
  let totalInput = 0;
  let totalOutput = 0;
  let count = 0;

  for (const line of lines) {
    let e;
    try { e = JSON.parse(line); } catch { continue; }
    if (since && new Date(e.timestamp) < since) continue;
    if (project && e.project !== project) continue;
    count++;
    totalInput  += e.input_tokens  || 0;
    totalOutput += e.output_tokens || 0;
    const cost = e.cost ? e.cost.total_usd : 0;
    totalCost += cost;
    byProject[e.project] = (byProject[e.project] || 0) + cost;
    byAgent[e.agent]     = (byAgent[e.agent]     || 0) + cost;
    byModel[e.model]     = (byModel[e.model]     || 0) + cost;
  }

  console.log('\n=== Token Usage Summary ===');
  console.log(`Entries: ${count}`);
  if (since)   console.log(`Since:   ${since.toISOString()}`);
  if (project) console.log(`Project: ${project}`);
  console.log(`\nTotal input:  ${totalInput.toLocaleString()} tokens`);
  console.log(`Total output: ${totalOutput.toLocaleString()} tokens`);
  console.log(`Total cost:   $${totalCost.toFixed(2)}`);

  const rows = (obj) => Object.entries(obj).sort((a, b) => b[1] - a[1]);
  console.log('\nBy Project:');
  for (const [k, v] of rows(byProject)) console.log(`  ${k.padEnd(24)} $${v.toFixed(2)}`);
  console.log('\nBy Agent:');
  for (const [k, v] of rows(byAgent))   console.log(`  ${k.padEnd(24)} $${v.toFixed(2)}`);
  console.log('\nBy Model:');
  for (const [k, v] of rows(byModel))   console.log(`  ${k.padEnd(24)} $${v.toFixed(2)}`);
}

function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  const args = parseArgs(rest);

  switch (cmd) {
    case 'log':     return logUsage(args);
    case 'summary': return summary(args);
    default:
      console.log('Usage:');
      console.log('  track-tokens.js log --project X --agent Y --model sonnet --input N --output M [--note "..."]');
      console.log('  track-tokens.js summary [--project X] [--since YYYY-MM-DD]');
  }
}

if (require.main === module) main();

module.exports = { logUsage, summary, estimateCost };
