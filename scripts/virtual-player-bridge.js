#!/usr/bin/env node
/**
 * virtual-player-bridge.js
 * Reads Virtual Player YAML exports and converts them to Design DB feedback format.
 *
 * Mapping logic:
 *   Session patterns    → validate design intent  (session_length, engagement_hooks)
 *   Action distributions → validate core loop      (action_frequency, action_variety)
 *   Failure points      → map to feedback categories (SYSTEM, BALANCE, CONTENT, UX)
 *
 * Usage:
 *   node virtual-player-bridge.js
 *     --input  <virtual-player-export-yaml>
 *     --project <project-name>
 *     --output  <feedback-output-path>   (optional; defaults to projects/{project}/feedback/design/vp_feedback.json)
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// Shared libraries
const { parseYaml } = require('./lib/yaml-utils');
const { writeJsonAtomic, ensureDir } = require('./lib/safe-io');

// ---------------------------------------------------------------------------
// CLI parsing
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const flag = argv[i];
    if (flag.startsWith('--')) {
      const key = flag.slice(2);
      const val  = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
      args[key] = val;
    }
  }
  return args;
}

const args = parseArgs(process.argv);

const INPUT   = args.input;
const PROJECT = args.project;
const OUTPUT  = args.output || `E:/AI/projects/${PROJECT}/feedback/design/vp_feedback.json`;

if (!INPUT || !PROJECT) {
  console.error('[ERROR] --input <yaml-path> and --project <name> are required');
  process.exit(1);
}
if (!fs.existsSync(INPUT)) {
  console.error(`[ERROR] Input file not found: ${INPUT}`);
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Fix: unique ID counter to prevent collision in tight loops
// ---------------------------------------------------------------------------
let idCounter = 0;
function nextId(prefix) {
  return `${prefix}_${Date.now()}_${++idCounter}`;
}

// ---------------------------------------------------------------------------
// Feedback category mapping
// Priority-based: compound patterns first, then single keywords.
// Each entry has an optional `priority` (lower = higher priority).
// ---------------------------------------------------------------------------
const FAILURE_CATEGORY_MAP = [
  // Compound patterns (higher specificity) — checked first
  { pattern: 'combat_tutorial',  priority: 1, category: 'BALANCE', type: 'CURVE_TOO_STEEP'   },
  { pattern: 'ui_confusion',     priority: 1, category: 'UX',      type: 'FLOW_BROKEN'       },
  { pattern: 'content_gap',      priority: 1, category: 'CONTENT', type: 'PACING_ISSUE'      },
  // Single keyword patterns
  { pattern: 'tutorial',         priority: 2, category: 'UX',      type: 'TUTORIAL_GAP'      },
  { pattern: 'onboarding',       priority: 2, category: 'UX',      type: 'TUTORIAL_GAP'      },
  { pattern: 'navigation',       priority: 2, category: 'UX',      type: 'FLOW_BROKEN'       },
  { pattern: 'combat',           priority: 2, category: 'BALANCE', type: 'CURVE_TOO_STEEP'   },
  { pattern: 'difficulty',       priority: 2, category: 'BALANCE', type: 'CURVE_TOO_STEEP'   },
  { pattern: 'economy',          priority: 2, category: 'BALANCE', type: 'ECONOMY_IMBALANCE' },
  { pattern: 'currency',         priority: 2, category: 'BALANCE', type: 'ECONOMY_IMBALANCE' },
  { pattern: 'paywall',          priority: 2, category: 'BM',      type: 'PAY_WALL_TOO_HARD' },
  { pattern: 'iap',              priority: 2, category: 'BM',      type: 'VALUE_MISMATCH'    },
  { pattern: 'stage',            priority: 2, category: 'CONTENT', type: 'PACING_ISSUE'      },
  { pattern: 'crash',            priority: 2, category: 'SYSTEM',  type: 'MISSING_FEATURE'   },
  { pattern: 'bug',              priority: 2, category: 'SYSTEM',  type: 'RULE_CONFLICT'     },
  { pattern: 'feature',          priority: 2, category: 'SYSTEM',  type: 'MISSING_FEATURE'   },
];

function mapFailureToCategory(failurePoint) {
  const fp = (failurePoint || '').toLowerCase();

  // Sort by priority (ascending) so compound/high-priority patterns are checked first
  const sorted = FAILURE_CATEGORY_MAP.slice().sort((a, b) => a.priority - b.priority);

  for (const entry of sorted) {
    if (fp.includes(entry.pattern)) {
      return { category: entry.category, type: entry.type };
    }
  }
  return { category: 'SYSTEM', type: 'OVER_COMPLEXITY' };
}

function severityFromRate(rate) {
  if (rate >= 0.5) return 'CRITICAL';
  if (rate >= 0.25) return 'HIGH';
  if (rate >= 0.1) return 'MEDIUM';
  return 'LOW';
}

// ---------------------------------------------------------------------------
// Transform Virtual Player export → Design feedback
// ---------------------------------------------------------------------------
function transform(vpData) {
  // Fix: validate input structure — warn if all main sections are missing
  const hasSessions = !!(vpData.sessions || vpData.session_data);
  const hasActions  = !!(vpData.actions  || vpData.action_data);
  const hasFailures = !!(vpData.failures || vpData.failure_points || vpData.failure_data);

  if (!hasSessions && !hasActions && !hasFailures) {
    console.warn('[WARN] VP data has no sessions, actions, or failures sections. Output may be empty.');
  }

  const feedbackItems = [];
  const ts = new Date().toISOString();

  // ── 1. Session patterns → design intent validation ──────────────────────
  const sessions = vpData.sessions || vpData.session_data || {};
  const avgSession     = sessions.avg_length   || sessions.average_session || 0;
  const targetSession  = sessions.target_length || 300;
  const engagementHooks = Array.isArray(sessions.engagement_hooks)
    ? sessions.engagement_hooks
    : Object.keys(sessions.engagement_hooks || {});

  if (avgSession && targetSession && Math.abs(avgSession - targetSession) / targetSession > 0.2) {
    feedbackItems.push({
      id               : nextId('vpb_session'),
      timestamp        : ts,
      source           : 'virtual_player_bridge',
      designId         : vpData.design_id || `${PROJECT}_design`,
      feedback_category: 'UX',
      feedback_type    : 'FLOW_BROKEN',
      severity         : severityFromRate(Math.abs(avgSession - targetSession) / targetSession),
      description      : `Session length deviation: actual ${avgSession}s vs target ${targetSession}s (${Math.round((avgSession - targetSession) / targetSession * 100)}%)`,
      recommendation   : avgSession < targetSession
        ? 'Review engagement hooks and mid-session content pacing. Consider adding rewarding checkpoints.'
        : 'Session is longer than intended — check if users are confused or stuck rather than engaged.',
      session_data     : { avg_length: avgSession, target_length: targetSession, hooks_present: engagementHooks },
    });
  }

  // Check engagement hooks completeness
  const expectedHooks = ['tutorial_complete', 'first_win', 'daily_reward', 'level_up'];
  const missingHooks  = expectedHooks.filter(h => !engagementHooks.includes(h));
  if (missingHooks.length > 0) {
    feedbackItems.push({
      id               : nextId('vpb_hooks'),
      timestamp        : ts,
      source           : 'virtual_player_bridge',
      designId         : vpData.design_id || `${PROJECT}_design`,
      feedback_category: 'UX',
      feedback_type    : 'TUTORIAL_GAP',
      severity         : 'MEDIUM',
      description      : `Missing engagement hooks: ${missingHooks.join(', ')}`,
      recommendation   : `Implement missing engagement triggers: ${missingHooks.join(', ')}`,
      session_data     : { missing_hooks: missingHooks, present_hooks: engagementHooks },
    });
  }

  // ── 2. Action distributions → core loop validation ──────────────────────
  const actions = vpData.actions || vpData.action_data || {};
  const actionFreq    = actions.frequency     || actions.actions_per_minute || 0;
  const actionVariety = actions.variety_score || actions.unique_action_types || 0;
  const coreLoopActions = Array.isArray(actions.core_loop)
    ? actions.core_loop
    : Object.keys(actions.core_loop || {});

  if (actionFreq > 0 && actionFreq < 2) {
    feedbackItems.push({
      id               : nextId('vpb_freq'),
      timestamp        : ts,
      source           : 'virtual_player_bridge',
      designId         : vpData.design_id || `${PROJECT}_design`,
      feedback_category: 'CONTENT',
      feedback_type    : 'PACING_ISSUE',
      severity         : severityFromRate(1 - actionFreq / 2),
      description      : `Low action frequency: ${actionFreq} actions/min. Core loop may be too slow.`,
      recommendation   : 'Reduce wait times or add parallel engagement options to increase action density.',
      action_data      : { frequency: actionFreq, core_loop: coreLoopActions },
    });
  }

  if (actionVariety > 0 && actionVariety < 3) {
    feedbackItems.push({
      id               : nextId('vpb_variety'),
      timestamp        : ts,
      source           : 'virtual_player_bridge',
      designId         : vpData.design_id || `${PROJECT}_design`,
      feedback_category: 'CONTENT',
      feedback_type    : 'PACING_ISSUE',
      severity         : 'MEDIUM',
      description      : `Low action variety: ${actionVariety} unique action types. Risk of boredom loop.`,
      recommendation   : 'Diversify core loop with at least 3–5 distinct player action types.',
      action_data      : { variety_score: actionVariety, unique_actions: coreLoopActions },
    });
  }

  // ── 3. Failure points → categorised feedback ────────────────────────────
  const failures = vpData.failures || vpData.failure_points || vpData.failure_data || {};
  const failureList = Array.isArray(failures)
    ? failures
    : Object.entries(failures).map(([point, rate]) => ({ point, rate: typeof rate === 'number' ? rate : 0.1 }));

  for (const failure of failureList) {
    const point = typeof failure === 'string' ? failure : (failure.point || failure.location || '');
    const rate  = typeof failure === 'object'  ? (failure.rate || failure.drop_off_rate || 0.1) : 0.1;
    const { category, type } = mapFailureToCategory(point);

    feedbackItems.push({
      id               : nextId('vpb_fail'),
      timestamp        : ts,
      source           : 'virtual_player_bridge',
      designId         : vpData.design_id || `${PROJECT}_design`,
      feedback_category: category,
      feedback_type    : type,
      severity         : severityFromRate(rate),
      description      : `Failure point detected: "${point}" — drop-off rate ${Math.round(rate * 100)}%`,
      recommendation   : generateRecommendation(category, type, point, rate),
      failure_data     : { point, drop_off_rate: rate },
    });
  }

  return {
    source         : 'virtual_player_bridge',
    project        : PROJECT,
    input_file     : INPUT,
    generated_at   : ts,
    vp_metadata    : {
      design_id    : vpData.design_id,
      export_date  : vpData.export_date || vpData.timestamp,
      player_count : vpData.player_count || vpData.session_count || 'unknown',
    },
    feedback_items : feedbackItems,
    summary        : {
      total          : feedbackItems.length,
      by_category    : countBy(feedbackItems, 'feedback_category'),
      by_severity    : countBy(feedbackItems, 'severity'),
      critical_count : feedbackItems.filter(f => f.severity === 'CRITICAL').length,
    },
  };
}

function generateRecommendation(category, type, point, rate) {
  const rateStr = `${Math.round(rate * 100)}%`;
  switch (type) {
    case 'TUTORIAL_GAP':      return `Tutorial gap at "${point}" (${rateStr} drop). Simplify instructions or add contextual hints.`;
    case 'FLOW_BROKEN':       return `UX flow break at "${point}" (${rateStr} drop). Review navigation and screen transitions.`;
    case 'CURVE_TOO_STEEP':   return `Difficulty spike at "${point}" (${rateStr} drop). Smooth difficulty curve or add fail-state guidance.`;
    case 'ECONOMY_IMBALANCE': return `Economy issue at "${point}" (${rateStr} drop). Rebalance resource generation/consumption.`;
    case 'PAY_WALL_TOO_HARD': return `Hard paywall at "${point}" (${rateStr} drop). Consider soft-gate or freemium alternative.`;
    case 'PACING_ISSUE':      return `Content pacing issue at "${point}" (${rateStr} drop). Add bridging content or adjust progression speed.`;
    case 'RULE_CONFLICT':     return `System rule conflict detected at "${point}". Review overlapping mechanics.`;
    case 'MISSING_FEATURE':   return `Missing feature expected at "${point}" (${rateStr} drop). Implement or surface existing feature.`;
    default:                  return `Issue at "${point}" (${rateStr} drop). Investigate and address root cause.`;
  }
}

function countBy(arr, key) {
  return arr.reduce((acc, item) => {
    const val = item[key] || 'unknown';
    acc[val] = (acc[val] || 0) + 1;
    return acc;
  }, {});
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
const rawYaml = fs.readFileSync(INPUT, 'utf8');
const vpData  = parseYaml(rawYaml);

const feedback = transform(vpData);

// Ensure output directory exists and write atomically
ensureDir(path.dirname(OUTPUT));
writeJsonAtomic(OUTPUT, feedback);

console.log(`[OK] Feedback written to: ${OUTPUT}`);
console.log(`[OK] Total feedback items: ${feedback.summary.total}`);
if (feedback.summary.critical_count > 0) {
  console.warn(`[WARN] ${feedback.summary.critical_count} CRITICAL issues found — review immediately`);
}
