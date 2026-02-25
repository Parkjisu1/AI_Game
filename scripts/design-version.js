#!/usr/bin/env node
/**
 * design-version.js
 * Design version management — never overwrites, always appends to versions[].
 *
 * Usage:
 *   node design-version.js
 *     --designId   <id>
 *     --genre      <genre>
 *     --domain     <domain>
 *     --version    <semver>           e.g. 1.2.0
 *     --phase      pre_launch|post_launch
 *     [--note      "description"]
 *     [--trigger   "reason for change"]
 *     [--kpi-before "{}"]             JSON string
 *     [--kpi-after  "{}"]             JSON string
 *     [--snapshot]                    capture full project state
 *     [--project   <name>]            required when using --snapshot
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// Shared libraries
const { readJsonSafe, writeJsonAtomic, ensureDir } = require('./lib/safe-io');
const { updateScore } = require('./lib/score-manager');

// ---------------------------------------------------------------------------
// CLI parsing
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i++) {
    const flag = argv[i];
    if (flag.startsWith('--')) {
      const key = flag.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase()); // kebab → camel
      const val  = argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[++i] : true;
      args[key] = val;
    }
  }
  return args;
}

const args = parseArgs(process.argv);

const DESIGN_ID    = args.designId;
const GENRE        = (args.genre  || '').toLowerCase();
const DOMAIN       = (args.domain || '').toLowerCase();
const VERSION      = args.version;
const PHASE        = args.phase;
const NOTE         = args.note    || '';
const TRIGGER      = args.trigger || '';
const SNAPSHOT_MODE = !!args.snapshot;
const PROJECT      = args.project || '';

let KPI_BEFORE = {};
let KPI_AFTER  = {};
try { if (args.kpiBefore) KPI_BEFORE = JSON.parse(args.kpiBefore); } catch { KPI_BEFORE = {}; }
try { if (args.kpiAfter)  KPI_AFTER  = JSON.parse(args.kpiAfter);  } catch { KPI_AFTER  = {}; }

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------
if (!SNAPSHOT_MODE) {
  if (!DESIGN_ID) { console.error('[ERROR] --designId is required'); process.exit(1); }
  if (!GENRE)     { console.error('[ERROR] --genre is required');    process.exit(1); }
  if (!DOMAIN)    { console.error('[ERROR] --domain is required');   process.exit(1); }
  if (!VERSION)   { console.error('[ERROR] --version is required');  process.exit(1); }
  if (!PHASE || !['pre_launch', 'post_launch'].includes(PHASE)) {
    console.error('[ERROR] --phase must be pre_launch or post_launch');
    process.exit(1);
  }
}
if (SNAPSHOT_MODE && !PROJECT) {
  console.error('[ERROR] --project is required when using --snapshot');
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------
const DESIGN_DB_ROOT = 'E:/AI/db/design/base';

function detailFilePath(genre, domain, designId) {
  return `${DESIGN_DB_ROOT}/${genre}/${domain}/files/${designId}.json`;
}

function indexFilePath(genre, domain) {
  return `${DESIGN_DB_ROOT}/${genre}/${domain}/index.json`;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function semverValid(v) {
  return /^\d+\.\d+\.\d+$/.test(v);
}

function semverGreater(a, b) {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) {
    if (pa[i] > pb[i]) return true;
    if (pa[i] < pb[i]) return false;
  }
  return false;
}

// ---------------------------------------------------------------------------
// Main: append version
// ---------------------------------------------------------------------------
function appendVersion() {
  if (!semverValid(VERSION)) {
    console.error(`[ERROR] Invalid semver: "${VERSION}". Use format X.Y.Z`);
    process.exit(1);
  }

  const detailPath = detailFilePath(GENRE, DOMAIN, DESIGN_ID);
  const detail     = readJsonSafe(detailPath);

  if (!detail) {
    console.error(`[ERROR] Design detail file not found: ${detailPath}`);
    console.error('        Ensure the design exists in the DB before versioning.');
    process.exit(1);
  }

  // Guard: version must be newer than current top-level version
  const currentVersion = detail.version || '0.0.0';
  if (!semverGreater(VERSION, currentVersion)) {
    console.error(`[ERROR] New version ${VERSION} must be greater than current ${currentVersion}`);
    process.exit(1);
  }

  // Guard: no duplicate version in history
  const versions = Array.isArray(detail.versions) ? detail.versions : [];
  if (versions.some(v => v.version === VERSION)) {
    console.error(`[ERROR] Version ${VERSION} already exists in history for ${DESIGN_ID}`);
    process.exit(1);
  }

  // Build version entry
  // Snapshot of current content (exclude the versions array itself to avoid recursion)
  const { versions: _ignored, ...contentSnapshot } = detail;

  const versionEntry = {
    version   : VERSION,
    phase     : PHASE,
    timestamp : new Date().toISOString(),
    note      : NOTE,
    data      : contentSnapshot,
    live_context: {
      trigger   : TRIGGER,
      kpi_before: KPI_BEFORE,
      kpi_after : KPI_AFTER,
    },
  };

  if (PHASE === 'post_launch') {
    versionEntry.post_launch_label = `v${VERSION} (live)`;
  }

  // Append
  versions.push(versionEntry);

  // Update top-level version field (NEVER overwrite content — only append + update version pointer)
  detail.versions = versions;
  detail.version  = VERSION;
  if (PHASE === 'post_launch') {
    detail.post_launch_label = versionEntry.post_launch_label;
  }

  writeJsonAtomic(detailPath, detail);
  console.log(`[OK] Appended version ${VERSION} to ${detailPath}`);

  // If post_launch: update score via score-manager (FEEDBACK_PASS)
  if (PHASE === 'post_launch') {
    const scoreResult = updateScore(GENRE, DOMAIN, DESIGN_ID, 'FEEDBACK_PASS');
    if (scoreResult.error) {
      console.warn(`[WARN] Score update failed: ${scoreResult.error}`);
    } else {
      console.log(`[OK] Score updated → ${scoreResult.newScore}${scoreResult.promoted ? ' (promoted to Expert DB)' : ''}`);
    }
  }

  // Update index entry
  updateIndexVersion(GENRE, DOMAIN, DESIGN_ID, VERSION, PHASE);
}

function updateIndexVersion(genre, domain, designId, version, phase) {
  const idxPath = indexFilePath(genre, domain);
  const rawIndex = readJsonSafe(idxPath);
  if (!rawIndex) {
    console.warn(`[WARN] Index not found at ${idxPath} — skipping index update`);
    return;
  }

  // Simplify: always treat index as array.
  // If it has .entries, extract them first.
  const entries = Array.isArray(rawIndex)
    ? rawIndex
    : (Array.isArray(rawIndex.entries) ? rawIndex.entries : []);

  const entry = entries.find(e => e.designId === designId || e.id === designId);
  if (!entry) {
    console.warn(`[WARN] Design ID "${designId}" not found in index — skipping index update`);
    return;
  }

  entry.version = version;
  if (phase === 'post_launch') {
    entry.live = true;
  }

  // Always write index as plain array
  writeJsonAtomic(idxPath, entries);
  console.log(`[OK] Updated index version for ${designId} → ${version}`);
}

// ---------------------------------------------------------------------------
// Snapshot mode: capture full project state
// ---------------------------------------------------------------------------
function runSnapshot() {
  console.log(`[SNAPSHOT] Capturing full project state for project: ${PROJECT} @ ${VERSION || 'no-version'}`);

  const snapshotVersion = VERSION || new Date().toISOString().slice(0, 10).replace(/-/g, '.');
  const snapshotEntries = [];

  // Walk all genre/domain combinations and collect entries for this project
  if (!fs.existsSync(DESIGN_DB_ROOT)) {
    console.error(`[ERROR] Design DB root not found: ${DESIGN_DB_ROOT}`);
    process.exit(1);
  }

  const genres = fs.readdirSync(DESIGN_DB_ROOT).filter(g => {
    const gPath = `${DESIGN_DB_ROOT}/${g}`;
    return fs.statSync(gPath).isDirectory() && g !== 'projects';
  });

  for (const genre of genres) {
    const genrePath = `${DESIGN_DB_ROOT}/${genre}`;
    const domains   = fs.readdirSync(genrePath).filter(d => {
      const dPath = `${genrePath}/${d}`;
      return fs.statSync(dPath).isDirectory() && d !== 'projects';
    });

    for (const domain of domains) {
      const filesDir = `${genrePath}/${domain}/files`;
      if (!fs.existsSync(filesDir)) continue;

      const files = fs.readdirSync(filesDir).filter(f => f.endsWith('.json'));
      for (const file of files) {
        const detail = readJsonSafe(`${filesDir}/${file}`);
        if (!detail) continue;

        // Include only entries belonging to this project
        const belongsToProject = (detail.project === PROJECT)
          || (detail.tags && detail.tags.includes(PROJECT))
          || (detail.designId && detail.designId.toLowerCase().includes(PROJECT.toLowerCase()));

        if (belongsToProject) {
          snapshotEntries.push({
            designId : detail.designId || file.replace('.json', ''),
            genre,
            domain,
            version  : detail.version || '0.0.0',
            system   : detail.system,
            phase    : detail.phase,
            score    : detail.score,
          });
        }
      }
    }
  }

  const snapshotData = {
    project          : PROJECT,
    snapshot_version : snapshotVersion,
    timestamp        : new Date().toISOString(),
    note             : NOTE,
    total_entries    : snapshotEntries.length,
    entries          : snapshotEntries,
  };

  // Determine genre from entries (majority) or first genre found
  const snapshotGenre = GENRE || (snapshotEntries[0]?.genre) || 'generic';
  const snapshotDir   = `${DESIGN_DB_ROOT}/${snapshotGenre}/projects`;
  const snapshotFile  = `${snapshotDir}/${PROJECT}_snapshot_${snapshotVersion}.json`;

  ensureDir(snapshotDir);
  writeJsonAtomic(snapshotFile, snapshotData);

  console.log(`[OK] Snapshot saved: ${snapshotFile}`);
  console.log(`[OK] Captured ${snapshotEntries.length} design entries for project "${PROJECT}"`);
}

// ---------------------------------------------------------------------------
// Entry
// ---------------------------------------------------------------------------
if (SNAPSHOT_MODE) {
  runSnapshot();
} else {
  appendVersion();
}
