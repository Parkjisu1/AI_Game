#!/usr/bin/env node
/**
 * migrate-design-domains.js
 * Fix corrupted domain directory entries in the Design DB.
 *
 * Problem: Old design-parser versions stored entries under raw domain names
 * (e.g., "combat", "economy") instead of the canonical names ("ingame", "balance").
 * This script detects invalid domain directories and moves their contents to the
 * correct canonical location.
 *
 * Usage:
 *   node migrate-design-domains.js [--dry-run] [--db-root <path>]
 *
 * Options:
 *   --dry-run      Preview changes without writing anything
 *   --db-root      Design DB root path (default: E:/AI/db/design)
 *   --help, -h     Show this help
 *
 * Examples:
 *   node migrate-design-domains.js --dry-run
 *   node migrate-design-domains.js --db-root E:/AI/db/design
 */

'use strict';

const fs   = require('fs');
const path = require('path');
const { normalizeDomain, displayDomain, VALID_DOMAINS } = require('./lib/domain-utils');
const { readJsonSafe, writeJsonAtomic, upsertIndex, ensureDir } = require('./lib/safe-io');

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------
function parseArgs(argv) {
  const args = { dryRun: false, dbRoot: 'E:/AI/db/design', help: false };
  for (let i = 2; i < argv.length; i++) {
    switch (argv[i]) {
      case '--dry-run':  args.dryRun  = true; break;
      case '--db-root':  args.dbRoot  = argv[++i]; break;
      case '--help': case '-h': args.help = true; break;
    }
  }
  return args;
}

function printUsage() {
  console.log(`
migrate-design-domains.js - Fix corrupted domain directory entries in Design DB

Usage:
  node migrate-design-domains.js [--dry-run] [--db-root <path>]

Options:
  --dry-run        Preview changes without writing anything
  --db-root <path> Design DB root (default: E:/AI/db/design)
  --help, -h       Show this help

Examples:
  node migrate-design-domains.js --dry-run
  node migrate-design-domains.js
`);
}

// ---------------------------------------------------------------------------
// Migration logic
// ---------------------------------------------------------------------------

/**
 * Walk all base/{genre}/{domain} directories and return invalid ones.
 * @param {string} baseDir  - Path to db/design/base/
 * @returns {Array<{genreDir, domainDir, fullPath, canonicalDomain}>}
 */
function findInvalidDomainDirs(baseDir) {
  const invalid = [];

  if (!fs.existsSync(baseDir)) return invalid;

  const genres = fs.readdirSync(baseDir).filter(g => {
    return fs.statSync(path.join(baseDir, g)).isDirectory();
  });

  for (const genre of genres) {
    const genrePath = path.join(baseDir, genre);
    const domains = fs.readdirSync(genrePath).filter(d => {
      return fs.statSync(path.join(genrePath, d)).isDirectory();
    });

    for (const domain of domains) {
      if (!VALID_DOMAINS.includes(domain)) {
        const canonical = normalizeDomain(domain);
        invalid.push({
          genreDir: genre,
          domainDir: domain,
          fullPath: path.join(genrePath, domain),
          canonicalDomain: canonical,
        });
      }
    }
  }

  return invalid;
}

/**
 * Migrate one invalid domain directory to the canonical location.
 * - Reads the invalid index.json
 * - Updates domain fields in each entry and detail file
 * - Upserts all entries into the canonical index.json
 * - Copies detail files to canonical files/ directory
 * - Removes the original directory (unless --dry-run)
 */
function migrateDir(entry, baseDir, dryRun, stats) {
  const { genreDir, domainDir, fullPath, canonicalDomain } = entry;
  const displayName = displayDomain(canonicalDomain);

  const srcIndexPath   = path.join(fullPath, 'index.json');
  const srcFilesDir    = path.join(fullPath, 'files');
  const dstDir         = path.join(baseDir, genreDir, canonicalDomain);
  const dstIndexPath   = path.join(dstDir, 'index.json');
  const dstFilesDir    = path.join(dstDir, 'files');

  console.log(`\n[MIGRATE] ${genreDir}/${domainDir} → ${genreDir}/${canonicalDomain}`);

  // Read source index
  const srcIndex = readJsonSafe(srcIndexPath);
  if (!Array.isArray(srcIndex) || srcIndex.length === 0) {
    console.log(`  [SKIP] No valid index.json found or empty index.`);
    stats.skipped++;
    return;
  }

  if (!dryRun) {
    ensureDir(dstFilesDir);
  }

  let movedFiles  = 0;
  let movedIndex  = 0;

  for (const indexEntry of srcIndex) {
    const designId = indexEntry.designId;
    if (!designId) continue;

    // Update domain fields in the index entry
    const updatedEntry = { ...indexEntry, domain: displayName };

    // Handle detail file
    const srcDetailPath = path.join(srcFilesDir, `${designId}.json`);
    const dstDetailPath = path.join(dstFilesDir, `${designId}.json`);

    if (fs.existsSync(srcDetailPath)) {
      const detail = readJsonSafe(srcDetailPath);
      if (detail) {
        const updatedDetail = { ...detail, domain: displayName };

        if (dryRun) {
          console.log(`  [DRY] Would move file: ${srcDetailPath} → ${dstDetailPath}`);
          console.log(`        domain: "${detail.domain}" → "${displayName}"`);
        } else {
          writeJsonAtomic(dstDetailPath, updatedDetail);
          console.log(`  [FILE] ${designId}.json → ${genreDir}/${canonicalDomain}/files/`);
          movedFiles++;
        }
      }
    } else {
      console.log(`  [WARN] Detail file not found: ${srcDetailPath}`);
    }

    // Upsert into canonical index
    if (dryRun) {
      console.log(`  [DRY] Would upsert index entry: ${designId} → ${genreDir}/${canonicalDomain}/index.json`);
    } else {
      upsertIndex(dstIndexPath, updatedEntry, 'designId');
      movedIndex++;
    }
  }

  // Remove source directory after successful migration
  if (!dryRun && (movedFiles > 0 || movedIndex > 0)) {
    try {
      fs.rmSync(fullPath, { recursive: true, force: true });
      console.log(`  [CLEAN] Removed source dir: ${fullPath}`);
    } catch (e) {
      console.warn(`  [WARN] Could not remove source dir: ${e.message}`);
    }
  }

  if (dryRun) {
    console.log(`  [DRY] Would migrate ${srcIndex.length} entries from ${domainDir} → ${canonicalDomain}`);
    stats.wouldMigrate += srcIndex.length;
  } else {
    console.log(`  [OK] Migrated ${movedIndex} index entries, ${movedFiles} files`);
    stats.migrated += movedIndex;
    stats.filesMoved += movedFiles;
  }

  stats.dirs++;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------
function main() {
  const args = parseArgs(process.argv);

  if (args.help) {
    printUsage();
    process.exit(0);
  }

  const baseDir = path.join(args.dbRoot, 'base');
  const dryRun  = args.dryRun;

  console.log('='.repeat(60));
  console.log('Design Domain Migration');
  console.log(`DB Root:  ${args.dbRoot}`);
  console.log(`Mode:     ${dryRun ? 'DRY RUN (no changes will be made)' : 'LIVE'}`);
  console.log('='.repeat(60));

  if (!fs.existsSync(baseDir)) {
    console.error(`Error: DB base directory not found: ${baseDir}`);
    process.exit(1);
  }

  const invalidDirs = findInvalidDomainDirs(baseDir);

  if (invalidDirs.length === 0) {
    console.log('\nNo invalid domain directories found. DB is clean.');
    process.exit(0);
  }

  console.log(`\nFound ${invalidDirs.length} invalid domain director${invalidDirs.length === 1 ? 'y' : 'ies'}:`);
  for (const d of invalidDirs) {
    console.log(`  ${d.genreDir}/${d.domainDir} → ${d.genreDir}/${d.canonicalDomain}`);
  }

  const stats = { dirs: 0, migrated: 0, filesMoved: 0, skipped: 0, wouldMigrate: 0 };

  for (const entry of invalidDirs) {
    migrateDir(entry, baseDir, dryRun, stats);
  }

  console.log('\n' + '='.repeat(60));
  console.log('Migration Summary');
  console.log('='.repeat(60));
  if (dryRun) {
    console.log(`Directories to migrate : ${stats.dirs + invalidDirs.length}`);
    console.log(`Entries to migrate     : ${stats.wouldMigrate}`);
    console.log(`Skipped                : ${stats.skipped}`);
    console.log('\nRun without --dry-run to apply changes.');
  } else {
    console.log(`Directories processed  : ${stats.dirs}`);
    console.log(`Index entries migrated : ${stats.migrated}`);
    console.log(`Detail files moved     : ${stats.filesMoved}`);
    console.log(`Skipped                : ${stats.skipped}`);
  }
  console.log('='.repeat(60));
}

main();
