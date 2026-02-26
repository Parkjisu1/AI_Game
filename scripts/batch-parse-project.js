#!/usr/bin/env node
/**
 * batch-parse-project.js
 * Unity 프로젝트의 JSON 테이블을 일괄 파싱하여 Design DB에 저장
 *
 * Usage:
 *   node batch-parse-project.js --tables <path> --genre idle --project IdleMoney
 */

'use strict';

const fs = require('fs');
const path = require('path');
const { writeJsonAtomic, upsertIndex, ensureDir, readJsonSafe } = require('./lib/safe-io');
const { normalizeDomain, displayDomain, normalizeGenre, displayGenre } = require('./lib/domain-utils');

// ============================================================
// Table → Domain Mapping
// ============================================================

const TABLE_DOMAIN_MAP = {
  // InGame - core gameplay mechanics
  'Machine':              { domain: 'ingame',  system: 'Machine',           dataType: 'table',   balanceArea: 'core_mechanic' },
  'Slot':                 { domain: 'ingame',  system: 'Slot',              dataType: 'table',   balanceArea: 'core_mechanic' },
  'SupplyMachine':        { domain: 'ingame',  system: 'SupplyMachine',     dataType: 'table',   balanceArea: 'core_mechanic' },

  // OutGame - inventory, managers, products
  'Product':              { domain: 'outgame', system: 'Product',           dataType: 'table',   balanceArea: 'item' },
  'ProductGroup':         { domain: 'outgame', system: 'ProductGroup',      dataType: 'config',  balanceArea: 'item' },
  'Manager':              { domain: 'outgame', system: 'Manager',           dataType: 'table',   balanceArea: 'character' },
  'ManagerGrade':         { domain: 'outgame', system: 'ManagerGrade',      dataType: 'table',   balanceArea: 'character' },
  'Goods':                { domain: 'outgame', system: 'Goods',             dataType: 'config',  balanceArea: 'item' },

  // Balance - progression curves, formulas, tuning
  'SlotLevelUp':          { domain: 'balance', system: 'SlotProgression',       dataType: 'table', balanceArea: 'progression' },
  'SupplyMachineLevelUp': { domain: 'balance', system: 'SupplyProgression',     dataType: 'table', balanceArea: 'progression' },
  'FactoryLevelUp':       { domain: 'balance', system: 'FactoryProgression',    dataType: 'table', balanceArea: 'progression' },
  'FactoryRebirth':       { domain: 'balance', system: 'RebirthSystem',         dataType: 'table', balanceArea: 'prestige' },
  'FactoryRebirthReward': { domain: 'balance', system: 'RebirthReward',         dataType: 'table', balanceArea: 'prestige' },
  'MachineTuningExp':     { domain: 'balance', system: 'MachineTuning',         dataType: 'table', balanceArea: 'upgrade' },
  'MachineTuningMaterial':{ domain: 'balance', system: 'MachineTuningCost',     dataType: 'table', balanceArea: 'upgrade' },
  'LabItemLevelUp':       { domain: 'balance', system: 'LabProgression',        dataType: 'table', balanceArea: 'research' },
  'ADMoneyBonusFactor':   { domain: 'balance', system: 'AdRewardCurve',         dataType: 'formula',balanceArea: 'economy' },
  'ConfigCommon':         { domain: 'balance', system: 'GlobalConfig',           dataType: 'config', balanceArea: 'system' },

  // Content - dungeons, challenges, quests
  'Dungeon':              { domain: 'content', system: 'Dungeon',            dataType: 'content_data', balanceArea: 'stage' },
  'Challenge':            { domain: 'content', system: 'Challenge',          dataType: 'content_data', balanceArea: 'quest' },
  'LabItem':              { domain: 'content', system: 'LabItem',            dataType: 'content_data', balanceArea: 'research' },
  'LabBuff':              { domain: 'content', system: 'LabBuff',            dataType: 'config',       balanceArea: 'research' },
  'Roulette':             { domain: 'content', system: 'Roulette',           dataType: 'content_data', balanceArea: 'reward' },

  // BM - monetization, shop, gacha
  'StoreDiamond':         { domain: 'bm',     system: 'DiamondShop',        dataType: 'config',       balanceArea: 'iap' },
  'StorePackage':         { domain: 'bm',     system: 'PackageShop',        dataType: 'config',       balanceArea: 'iap' },
  'StoreBox':             { domain: 'bm',     system: 'BoxShop',            dataType: 'config',       balanceArea: 'gacha' },
  'StoreEtc':             { domain: 'bm',     system: 'MiscShop',           dataType: 'config',       balanceArea: 'iap' },
  'StoreLoopyCoin':       { domain: 'bm',     system: 'SecondaryCurrencyShop', dataType: 'config',    balanceArea: 'currency' },
  'BoxGeneral':           { domain: 'bm',     system: 'GachaGeneral',       dataType: 'table',        balanceArea: 'gacha' },
  'BoxAdvanced':          { domain: 'bm',     system: 'GachaAdvanced',      dataType: 'table',        balanceArea: 'gacha' },
  'BoxSuper':             { domain: 'bm',     system: 'GachaSuper',         dataType: 'table',        balanceArea: 'gacha' },
  'BoxStoreEvent':        { domain: 'bm',     system: 'GachaStoreEvent',    dataType: 'table',        balanceArea: 'gacha' },
  'BoxLobbyEvent':        { domain: 'bm',     system: 'GachaLobbyEvent',    dataType: 'table',        balanceArea: 'gacha' },
  'LevelGachaBox':        { domain: 'bm',     system: 'LevelGacha',         dataType: 'table',        balanceArea: 'gacha' },

  // LiveOps
  'AttendanceReward':     { domain: 'liveops', system: 'DailyLogin',        dataType: 'content_data', balanceArea: 'reward' },

  // Meta
  'Achievement':          { domain: 'meta',    system: 'Achievement',       dataType: 'content_data', balanceArea: 'progression' },

  // UX - localization (skip actual parsing, just register)
  'Language_English':     { domain: 'ux', system: 'Localization_EN',  dataType: 'config', balanceArea: 'text' },
  'Language_Korean':      { domain: 'ux', system: 'Localization_KO',  dataType: 'config', balanceArea: 'text' },
  'Language_Japanese':    { domain: 'ux', system: 'Localization_JA',  dataType: 'config', balanceArea: 'text' },
  'Language_ChineseTraditional': { domain: 'ux', system: 'Localization_ZH', dataType: 'config', balanceArea: 'text' },

  // Platform
  'BillingMode':          { domain: 'bm', system: 'BillingConfig', dataType: 'config', balanceArea: 'iap' },

  // Additional unmapped tables
  'BoxSameMachineSelect': { domain: 'bm',     system: 'GachaSameMachine',  dataType: 'table',  balanceArea: 'gacha' },
  'Vehicle':              { domain: 'ingame',  system: 'Vehicle',           dataType: 'table',  balanceArea: 'core_mechanic' },
};

// ============================================================
// CLI
// ============================================================

function parseArgs(argv) {
  const args = { tables: null, genre: 'idle', project: null, output: null, dryRun: false };
  for (let i = 0; i < argv.length; i++) {
    switch (argv[i]) {
      case '--tables': args.tables = argv[++i]; break;
      case '--genre': args.genre = argv[++i]; break;
      case '--project': args.project = argv[++i]; break;
      case '--output': args.output = argv[++i]; break;
      case '--dry-run': args.dryRun = true; break;
      case '--help': case '-h':
        console.log(`Usage: node batch-parse-project.js --tables <path> --genre <genre> --project <name> [--output <db-path>] [--dry-run]`);
        process.exit(0);
    }
  }
  return args;
}

// ============================================================
// Table Analysis
// ============================================================

function analyzeTable(data, tableName) {
  const stats = { rowCount: 0, columns: [], sampleRow: null, numericColumns: [], textColumns: [] };

  if (Array.isArray(data)) {
    stats.rowCount = data.length;
    if (data.length > 0) {
      const first = data[0];
      stats.columns = Object.keys(first);
      stats.sampleRow = first;

      for (const col of stats.columns) {
        const sampleVals = data.slice(0, Math.min(10, data.length)).map(r => r[col]);
        const allNumeric = sampleVals.every(v => v === null || v === '' || !isNaN(Number(v)));
        if (allNumeric) stats.numericColumns.push(col);
        else stats.textColumns.push(col);
      }
    }
  } else if (typeof data === 'object') {
    const keys = Object.keys(data);
    stats.rowCount = keys.length;
    stats.columns = keys;
    stats.sampleRow = data[keys[0]];
  }

  return stats;
}

function extractBalancePoints(data, tableName) {
  const points = [];
  if (!Array.isArray(data) || data.length < 2) return points;

  const numCols = [];
  const first = data[0];
  for (const key of Object.keys(first)) {
    const val = first[key];
    if (!isNaN(Number(val)) && val !== '' && val !== null) numCols.push(key);
  }

  for (const col of numCols) {
    const values = data.map(r => Number(r[col] || 0)).filter(v => !isNaN(v));
    if (values.length < 2) continue;

    const min = Math.min(...values);
    const max = Math.max(...values);
    const avg = values.reduce((a, b) => a + b, 0) / values.length;

    if (max > min * 2 && values.length >= 5) {
      // Detect growth pattern
      const growthRatio = max / (min || 1);
      points.push({
        variable: col,
        min_value: min,
        max_value: max,
        avg_value: Math.round(avg * 100) / 100,
        growth_ratio: Math.round(growthRatio * 100) / 100,
        data_points: values.length,
        impact: growthRatio > 100 ? 'critical' : growthRatio > 10 ? 'high' : 'medium',
      });
    }
  }

  return points.slice(0, 20); // Top 20 balance points
}

function buildProvides(tableName, mapping, stats) {
  const provides = [];
  provides.push(`${tableName}_data`);
  if (stats.numericColumns.length > 0) {
    for (const col of stats.numericColumns.slice(0, 5)) {
      provides.push(`${tableName}.${col}`);
    }
  }
  return provides;
}

function buildTags(tableName, mapping) {
  const tags = [mapping.balanceArea];
  if (mapping.dataType === 'table') tags.push('data_table');
  if (mapping.dataType === 'formula') tags.push('formula');
  if (mapping.dataType === 'config') tags.push('config');
  if (mapping.dataType === 'content_data') tags.push('content');

  const name = tableName.toLowerCase();
  if (/level|exp|progression/.test(name)) tags.push('progression');
  if (/cost|price|reward/.test(name)) tags.push('economy');
  if (/gacha|box/.test(name)) tags.push('gacha');
  if (/store|shop|diamond/.test(name)) tags.push('monetization');

  return [...new Set(tags)];
}

// ============================================================
// Main Processing
// ============================================================

function main() {
  const args = parseArgs(process.argv.slice(2));

  if (!args.tables || !args.project) {
    console.error('Error: --tables and --project are required');
    process.exit(1);
  }

  const tablesDir = path.resolve(args.tables);
  const genre = normalizeGenre(args.genre);
  const project = args.project;
  const dbRoot = args.output || 'E:/AI/db/design';

  if (!fs.existsSync(tablesDir)) {
    console.error(`Error: Tables directory not found: ${tablesDir}`);
    process.exit(1);
  }

  console.log('='.repeat(60));
  console.log('Batch Project Parser');
  console.log(`Tables:  ${tablesDir}`);
  console.log(`Genre:   ${genre} | Project: ${project}`);
  console.log(`Output:  ${dbRoot}`);
  console.log(`Mode:    ${args.dryRun ? 'DRY RUN' : 'LIVE'}`);
  console.log('='.repeat(60));

  // Find all JSON files
  const jsonFiles = fs.readdirSync(tablesDir)
    .filter(f => f.endsWith('.json'))
    .sort();

  console.log(`\nFound ${jsonFiles.length} JSON files\n`);

  const results = { total: 0, saved: 0, skipped: 0, errors: 0, byDomain: {} };

  for (const file of jsonFiles) {
    const tableName = path.basename(file, '.json');
    const mapping = TABLE_DOMAIN_MAP[tableName];

    if (!mapping) {
      console.log(`[SKIP] ${tableName} - no domain mapping defined`);
      results.skipped++;
      continue;
    }

    const filePath = path.join(tablesDir, file);
    let rawData;
    try {
      const content = fs.readFileSync(filePath, 'utf-8')
        .replace(/^\uFEFF/, '')           // Strip BOM
        .replace(/\r\n/g, '\n')           // Normalize CRLF
        .replace(/\t/g, '  ')             // Tabs to spaces
        .replace(/,\s*([\]}])/g, '$1');   // Strip trailing commas (Unity JSON)
      rawData = JSON.parse(content);
    } catch (e) {
      console.error(`[ERROR] ${tableName}: ${e.message}`);
      results.errors++;
      continue;
    }

    // Analyze table structure
    const stats = analyzeTable(rawData, tableName);
    const balancePoints = extractBalancePoints(rawData, tableName);

    // Build design entry
    const domain = mapping.domain;
    const designId = `${project.toLowerCase()}__${domain}__${mapping.system.toLowerCase().replace(/[^a-z0-9]/g, '_')}`;

    // Truncate large data for storage (keep first/last rows as samples)
    let storedData;
    if (Array.isArray(rawData)) {
      if (rawData.length > 50) {
        storedData = {
          _note: `Table truncated: ${rawData.length} rows total. First 10 + last 5 shown.`,
          _total_rows: rawData.length,
          _columns: stats.columns,
          sample_first: rawData.slice(0, 10),
          sample_last: rawData.slice(-5),
        };
      } else {
        storedData = rawData;
      }
    } else {
      // ConfigCommon etc - keep full object but truncate if too large
      const jsonStr = JSON.stringify(rawData);
      if (jsonStr.length > 50000) {
        const keys = Object.keys(rawData);
        storedData = {
          _note: `Config truncated: ${keys.length} entries. First 30 shown.`,
          _total_entries: keys.length,
          sample: Object.fromEntries(keys.slice(0, 30).map(k => [k, rawData[k]])),
        };
      } else {
        storedData = rawData;
      }
    }

    const indexEntry = {
      designId,
      domain: displayDomain(domain),
      genre: displayGenre(genre),
      system: mapping.system,
      score: 0.4,
      source: 'internal_original',
      data_type: mapping.dataType,
      balance_area: mapping.balanceArea,
      version: '1.0.0',
      project,
      provides: buildProvides(tableName, mapping, stats),
      requires: [],
      tags: buildTags(tableName, mapping),
    };

    const detailFile = {
      designId,
      project,
      domain: displayDomain(domain),
      genre: displayGenre(genre),
      system: mapping.system,
      source: 'internal_original',
      version: '1.0.0',
      score: 0.4,
      data_type: mapping.dataType,
      balance_area: mapping.balanceArea,
      source_file: file,
      table_stats: {
        row_count: stats.rowCount,
        columns: stats.columns,
        numeric_columns: stats.numericColumns,
        text_columns: stats.textColumns,
      },
      content: {
        summary: `${mapping.system} 데이터 테이블 (${stats.rowCount}행, ${stats.columns.length}열)`,
        parameters: stats.sampleRow || {},
        balance_points: balancePoints,
        edge_cases: [],
        references: [],
      },
      data: storedData,
      versions: [{
        version: '1.0.0',
        phase: 'post_launch',
        data: `Parsed from ${file} (${stats.rowCount} rows)`,
        note: 'Live game data import',
      }],
      feedback_history: [],
      code_mapping: {
        code_domain: '',
        code_roles: [],
        related_code_nodes: [],
      },
      timestamp: new Date().toISOString(),
    };

    // Domain stats
    if (!results.byDomain[domain]) results.byDomain[domain] = { count: 0, rows: 0 };
    results.byDomain[domain].count++;
    results.byDomain[domain].rows += stats.rowCount;

    if (args.dryRun) {
      console.log(`[DRY] ${tableName} → ${genre}/${domain}/${designId} (${stats.rowCount}행)`);
      results.total++;
      continue;
    }

    // Write to DB
    const baseDir = path.join(dbRoot, 'base', genre, domain);
    const filesDir = path.join(baseDir, 'files');
    const indexPath = path.join(baseDir, 'index.json');

    ensureDir(filesDir);
    upsertIndex(indexPath, indexEntry, 'designId');
    writeJsonAtomic(path.join(filesDir, `${designId}.json`), detailFile);

    const bpCount = balancePoints.length;
    console.log(`[OK] ${tableName} → ${genre}/${domain} (${stats.rowCount}행, ${bpCount} balance points)`);
    results.saved++;
    results.total++;
  }

  // Summary
  console.log('\n' + '='.repeat(60));
  console.log('Summary');
  console.log('='.repeat(60));
  console.log(`Total files:   ${results.total}`);
  console.log(`Saved:         ${results.saved}`);
  console.log(`Skipped:       ${results.skipped}`);
  console.log(`Errors:        ${results.errors}`);
  console.log('\nBy Domain:');
  for (const [domain, info] of Object.entries(results.byDomain).sort()) {
    console.log(`  ${displayDomain(domain).padEnd(10)} ${info.count} tables, ${info.rows.toLocaleString()} total rows`);
  }
  console.log(`\nDB: ${dbRoot}/base/${genre}/`);
}

main();
