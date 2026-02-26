#!/usr/bin/env node
/**
 * batch-parse-yaml-designs.js
 * Batch parse structured YAML design documents into Design DB
 *
 * Usage:
 *   node batch-parse-yaml-designs.js --dir <yaml-dir> --genre idle --project IdleMoney
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { parseYaml } = require('./lib/yaml-utils');
const { writeJsonAtomic, upsertIndex, ensureDir } = require('./lib/safe-io');
const { normalizeDomain, displayDomain, normalizeGenre, displayGenre } = require('./lib/domain-utils');

// ============================================================
// CLI
// ============================================================

function parseArgs(argv) {
  const args = { dir: null, genre: null, project: null, output: 'E:/AI/db/design', dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '--dir': args.dir = argv[++i]; break;
      case '--genre': args.genre = argv[++i]; break;
      case '--project': args.project = argv[++i]; break;
      case '--output': args.output = argv[++i]; break;
      case '--dry-run': args.dryRun = true; break;
    }
  }
  return args;
}

// ============================================================
// System Entry Builder
// ============================================================

function buildIndexEntry(sys, genre, project) {
  const domain = normalizeDomain(sys.domain || sys._parentDomain);
  return {
    designId: sys.designId,
    domain: displayDomain(domain),
    genre: displayGenre(genre),
    system: sys.system,
    score: 0.4,
    source: sys.content && sys.content.summary ? 'internal_original' : 'internal_produced',
    data_type: sys.data_type || 'spec',
    balance_area: sys.balance_area || null,
    version: '1.0.0',
    project,
    provides: sys.provides || [],
    requires: sys.requires || [],
    tags: sys.tags || [],
  };
}

function buildDetailFile(sys, genre, project, sourceFile) {
  const domain = normalizeDomain(sys.domain || sys._parentDomain);
  return {
    designId: sys.designId,
    project,
    domain: displayDomain(domain),
    genre: displayGenre(genre),
    system: sys.system,
    source: sys.content && sys.content.summary ? 'internal_original' : 'internal_produced',
    version: '1.0.0',
    score: 0.4,
    data_type: sys.data_type || 'spec',
    balance_area: sys.balance_area || null,
    source_file: sourceFile,
    content: {
      summary: (sys.content && sys.content.summary) || '',
      flow: (sys.content && sys.content.flow) || [],
      parameters: (sys.content && sys.content.parameters) || {},
      edge_cases: (sys.content && sys.content.edge_cases) || [],
      references: (sys.content && sys.content.references) || [],
    },
    versions: [{
      version: '1.0.0',
      phase: 'post_launch',
      data: `Parsed from C# analysis: ${sys.system}`,
      note: 'Live game code analysis import',
    }],
    feedback_history: [],
    code_mapping: {
      code_domain: '',
      code_roles: [],
      related_code_nodes: [],
    },
    timestamp: new Date().toISOString(),
  };
}

// ============================================================
// YAML File Processor
// ============================================================

function processYamlFile(filePath, genre, project, dbRoot, dryRun) {
  const content = fs.readFileSync(filePath, 'utf-8');
  let parsed;
  try {
    parsed = parseYaml(content);
  } catch (e) {
    console.error(`[ERROR] Failed to parse ${path.basename(filePath)}: ${e.message}`);
    return { saved: 0, errors: 1 };
  }

  // Handle multi-document YAML (our parseYaml returns first document)
  // Extract systems from various section keys
  const systemSections = [];
  const sectionKeys = ['systems', 'outgame_systems', 'content_systems', 'meta_systems',
    'liveops_systems', 'ux_systems', 'social_systems'];

  for (const key of sectionKeys) {
    if (parsed[key] && Array.isArray(parsed[key])) {
      // Determine parent domain from section key
      let parentDomain = null;
      if (key === 'outgame_systems') parentDomain = 'outgame';
      else if (key === 'content_systems') parentDomain = 'content';
      else if (key === 'meta_systems') parentDomain = 'meta';
      else if (key === 'liveops_systems') parentDomain = 'liveops';
      else if (key === 'ux_systems') parentDomain = 'ux';
      else if (key === 'social_systems') parentDomain = 'social';

      for (const sys of parsed[key]) {
        if (parentDomain && !sys.domain) sys._parentDomain = parentDomain;
        systemSections.push(sys);
      }
    }
  }

  // Also check top-level domain from YAML front matter
  const topDomain = parsed.domain;
  if (topDomain) {
    for (const sys of systemSections) {
      if (!sys.domain && !sys._parentDomain) sys._parentDomain = topDomain;
    }
  }

  let saved = 0;
  let errors = 0;

  for (const sys of systemSections) {
    if (!sys.designId) {
      console.error(`  [SKIP] System without designId in ${path.basename(filePath)}`);
      errors++;
      continue;
    }

    const domain = normalizeDomain(sys.domain || sys._parentDomain || topDomain || 'ingame');
    const indexEntry = buildIndexEntry(sys, genre, project);
    const detailFile = buildDetailFile(sys, genre, project, path.basename(filePath));

    if (dryRun) {
      console.log(`  [DRY] ${sys.designId} → ${genre}/${domain}`);
      saved++;
      continue;
    }

    const baseDir = path.join(dbRoot, 'base', genre, domain);
    const filesDir = path.join(baseDir, 'files');
    const indexPath = path.join(baseDir, 'index.json');

    ensureDir(filesDir);
    upsertIndex(indexPath, indexEntry, 'designId');
    writeJsonAtomic(path.join(filesDir, `${sys.designId}.json`), detailFile);

    console.log(`  [OK] ${sys.designId} → ${genre}/${domain}`);
    saved++;
  }

  return { saved, errors };
}

// ============================================================
// Main
// ============================================================

function main() {
  const args = parseArgs(process.argv.slice(2));

  if (!args.dir || !args.genre || !args.project) {
    console.error('Usage: node batch-parse-yaml-designs.js --dir <yaml-dir> --genre <genre> --project <name>');
    process.exit(1);
  }

  const dir = path.resolve(args.dir);
  const genre = normalizeGenre(args.genre);
  const project = args.project;
  const dbRoot = args.output;

  console.log('='.repeat(60));
  console.log('Batch YAML Design Parser');
  console.log(`Dir:     ${dir}`);
  console.log(`Genre:   ${genre} | Project: ${project}`);
  console.log(`Output:  ${dbRoot}`);
  console.log(`Mode:    ${args.dryRun ? 'DRY RUN' : 'LIVE'}`);
  console.log('='.repeat(60));

  const yamlFiles = fs.readdirSync(dir)
    .filter(f => f.endsWith('.yaml') || f.endsWith('.yml'))
    .sort();

  console.log(`\nFound ${yamlFiles.length} YAML files\n`);

  let totalSaved = 0;
  let totalErrors = 0;

  for (const file of yamlFiles) {
    console.log(`\nProcessing: ${file}`);
    const filePath = path.join(dir, file);
    const result = processYamlFile(filePath, genre, project, dbRoot, args.dryRun);
    totalSaved += result.saved;
    totalErrors += result.errors;
  }

  console.log('\n' + '='.repeat(60));
  console.log('Summary');
  console.log('='.repeat(60));
  console.log(`YAML files:    ${yamlFiles.length}`);
  console.log(`Systems saved: ${totalSaved}`);
  console.log(`Errors:        ${totalErrors}`);
  console.log(`DB: ${dbRoot}/base/${genre}/`);
}

main();
