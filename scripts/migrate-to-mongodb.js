#!/usr/bin/env node
/**
 * migrate-to-mongodb.js
 * Migrates all local JSON DB files to MongoDB Atlas.
 *
 * Collections:
 *   code_base    ← db/base/{genre}/{layer}/files/*.json (merged with index metadata)
 *   code_expert  ← db/expert/files/*.json (merged with index metadata)
 *   design_base  ← db/design/base/{genre}/{domain}/files/*.json (merged with index metadata)
 *   design_expert← db/design/expert/files/*.json (merged with index metadata)
 *   rules        ← db/rules/*.json + db/design/rules/*.json
 *
 * Usage: node scripts/migrate-to-mongodb.js [--dry-run]
 */

const fs = require('fs');
const path = require('path');
const { MongoClient } = require('mongodb');

// ─── Config ───
const DB_ROOT = path.resolve(__dirname, '../db');

// Load .env
const envPath = path.resolve(__dirname, '../.env');
try {
  fs.readFileSync(envPath, 'utf-8').split('\n').forEach(line => {
    line = line.trim();
    if (!line || line.startsWith('#')) return;
    const [key, ...rest] = line.split('=');
    if (key && rest.length) process.env[key.trim()] = rest.join('=').trim();
  });
} catch (e) {}

const MONGO_URI = process.env.MONGO_URI;
const DB_NAME = process.env.MONGO_DB_NAME || 'aigame';
const DRY_RUN = process.argv.includes('--dry-run');

// ─── Helpers ───

function readJSON(filePath) {
  try {
    let text = fs.readFileSync(filePath, 'utf-8');
    // Handle BOM
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1);
    // Handle trailing commas (common in Unity-exported JSON)
    text = text.replace(/,\s*([\]}])/g, '$1');
    return JSON.parse(text);
  } catch (e) {
    console.warn(`  WARN: Failed to parse ${filePath}: ${e.message}`);
    return null;
  }
}

function getDirs(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter(f =>
    fs.statSync(path.join(dir, f)).isDirectory()
  );
}

function getFiles(dir, ext = '.json') {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter(f => f.endsWith(ext));
}

// ─── Build index lookup from index.json ───

function buildIndexMap(indexPath, idField) {
  const map = new Map();
  const index = readJSON(indexPath);
  if (!index) return map;
  const entries = Array.isArray(index) ? index : (index.entries || index.files || []);
  for (const entry of entries) {
    if (entry[idField]) {
      map.set(entry[idField], entry);
    }
  }
  return map;
}

// ─── Migrate Code Base ───

async function migrateCodeBase(col) {
  const baseDir = path.join(DB_ROOT, 'base');
  const genres = getDirs(baseDir);
  let count = 0;

  for (const genre of genres) {
    const genreDir = path.join(baseDir, genre);
    const layers = getDirs(genreDir);

    for (const layer of layers) {
      const layerDir = path.join(genreDir, layer);
      const indexPath = path.join(layerDir, 'index.json');
      const filesDir = path.join(layerDir, 'files');

      // Build index map for merging metadata
      const indexMap = buildIndexMap(indexPath, 'fileId');

      if (!fs.existsSync(filesDir)) continue;

      const files = getFiles(filesDir);
      for (const file of files) {
        const detail = readJSON(path.join(filesDir, file));
        if (!detail) continue;

        // Merge index metadata into detail
        const fileId = detail.fileId || path.basename(file, '.json');
        const indexEntry = indexMap.get(fileId) || {};

        const doc = {
          ...indexEntry,
          ...detail,
          fileId,
          _sourceGenre: genre,
          _sourceLayer: layer,
          migratedAt: new Date(),
        };
        delete doc._id;

        if (!DRY_RUN) {
          await col.updateOne({ fileId }, { $set: doc }, { upsert: true });
        }
        count++;
      }
    }
  }

  return count;
}

// ─── Migrate Code Expert ───

async function migrateCodeExpert(col) {
  const expertDir = path.join(DB_ROOT, 'expert');
  const indexPath = path.join(expertDir, 'index.json');
  const filesDir = path.join(expertDir, 'files');
  let count = 0;

  if (!fs.existsSync(filesDir)) return count;

  const indexMap = buildIndexMap(indexPath, 'fileId');
  const files = getFiles(filesDir);

  for (const file of files) {
    const detail = readJSON(path.join(filesDir, file));
    if (!detail) continue;

    const fileId = detail.fileId || path.basename(file, '.json');
    const indexEntry = indexMap.get(fileId) || {};

    const doc = {
      ...indexEntry,
      ...detail,
      fileId,
      migratedAt: new Date(),
    };
    delete doc._id;

    if (!DRY_RUN) {
      await col.updateOne({ fileId }, { $set: doc }, { upsert: true });
    }
    count++;
  }

  return count;
}

// ─── Migrate Design Base ───

async function migrateDesignBase(col) {
  const designBaseDir = path.join(DB_ROOT, 'design', 'base');
  const genres = getDirs(designBaseDir);
  let count = 0;

  for (const genre of genres) {
    const genreDir = path.join(designBaseDir, genre);
    const domains = getDirs(genreDir);

    for (const domain of domains) {
      const domainDir = path.join(genreDir, domain);
      const indexPath = path.join(domainDir, 'index.json');
      const filesDir = path.join(domainDir, 'files');

      const indexMap = buildIndexMap(indexPath, 'designId');

      if (!fs.existsSync(filesDir)) continue;

      const files = getFiles(filesDir);
      for (const file of files) {
        const detail = readJSON(path.join(filesDir, file));
        if (!detail) continue;

        const designId = detail.designId || path.basename(file, '.json');
        const indexEntry = indexMap.get(designId) || {};

        const doc = {
          ...indexEntry,
          ...detail,
          designId,
          _sourceGenre: genre,
          _sourceDomain: domain,
          migratedAt: new Date(),
        };
        delete doc._id;

        if (!DRY_RUN) {
          await col.updateOne({ designId }, { $set: doc }, { upsert: true });
        }
        count++;
      }
    }
  }

  return count;
}

// ─── Migrate Design Expert ───

async function migrateDesignExpert(col) {
  const expertDir = path.join(DB_ROOT, 'design', 'expert');
  const indexPath = path.join(expertDir, 'index.json');
  const filesDir = path.join(expertDir, 'files');
  let count = 0;

  if (!fs.existsSync(filesDir)) return count;

  const indexMap = buildIndexMap(indexPath, 'designId');
  const files = getFiles(filesDir);

  for (const file of files) {
    const detail = readJSON(path.join(filesDir, file));
    if (!detail) continue;

    const designId = detail.designId || path.basename(file, '.json');
    const indexEntry = indexMap.get(designId) || {};

    const doc = {
      ...indexEntry,
      ...detail,
      designId,
      migratedAt: new Date(),
    };
    delete doc._id;

    if (!DRY_RUN) {
      await col.updateOne({ designId }, { $set: doc }, { upsert: true });
    }
    count++;
  }

  return count;
}

// ─── Migrate Rules ───

async function migrateRules(col) {
  let count = 0;

  // Code rules
  const codeRulesDir = path.join(DB_ROOT, 'rules');
  // Design rules
  const designRulesDir = path.join(DB_ROOT, 'design', 'rules');

  for (const [dir, source] of [[codeRulesDir, 'code'], [designRulesDir, 'design']]) {
    if (!fs.existsSync(dir)) continue;

    const files = getFiles(dir);
    for (const file of files) {
      const data = readJSON(path.join(dir, file));
      if (!data) continue;

      // Rules files can be arrays or objects with rule arrays
      const rules = Array.isArray(data) ? data : (data.rules || []);

      for (const rule of rules) {
        if (!rule.ruleId && !rule.id) continue;

        const ruleId = rule.ruleId || rule.id;
        const doc = {
          ...rule,
          ruleId,
          _source: source,
          _sourceFile: file,
          migratedAt: new Date(),
        };
        delete doc._id;

        if (!DRY_RUN) {
          await col.updateOne({ ruleId }, { $set: doc }, { upsert: true });
        }
        count++;
      }
    }
  }

  return count;
}

// ─── Main ───

async function main() {
  console.log(`=== MongoDB Migration ${DRY_RUN ? '(DRY RUN)' : ''} ===`);
  console.log(`DB Root: ${DB_ROOT}`);
  console.log(`MongoDB: ${DB_NAME}`);
  console.log('');

  const client = new MongoClient(MONGO_URI);
  await client.connect();
  const db = client.db(DB_NAME);

  // Code Base
  process.stdout.write('Migrating code_base... ');
  const codeBaseCount = await migrateCodeBase(db.collection('code_base'));
  console.log(`${codeBaseCount} documents`);

  // Code Expert
  process.stdout.write('Migrating code_expert... ');
  const codeExpertCount = await migrateCodeExpert(db.collection('code_expert'));
  console.log(`${codeExpertCount} documents`);

  // Design Base
  process.stdout.write('Migrating design_base... ');
  const designBaseCount = await migrateDesignBase(db.collection('design_base'));
  console.log(`${designBaseCount} documents`);

  // Design Expert
  process.stdout.write('Migrating design_expert... ');
  const designExpertCount = await migrateDesignExpert(db.collection('design_expert'));
  console.log(`${designExpertCount} documents`);

  // Rules
  process.stdout.write('Migrating rules... ');
  const rulesCount = await migrateRules(db.collection('rules'));
  console.log(`${rulesCount} documents`);

  console.log('');
  console.log('=== Summary ===');
  console.log(`  Code (System) DB: ${codeBaseCount} base + ${codeExpertCount} expert`);
  console.log(`  Design DB:        ${designBaseCount} base + ${designExpertCount} expert`);
  console.log(`  Rules:            ${rulesCount}`);
  console.log(`  Total:            ${codeBaseCount + codeExpertCount + designBaseCount + designExpertCount + rulesCount}`);

  await client.close();
  console.log('\nDone!');
}

main().catch(e => {
  console.error('FATAL:', e.message);
  process.exit(1);
});
