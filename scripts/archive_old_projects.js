#!/usr/bin/env node
/**
 * Archive non-BalloonFlow projects to local NDJSON files, then delete from Atlas.
 *
 * Steps:
 *   1. For each project to archive: dump project-bound collections to E:/AI/db_archive/{project}/{collection}.ndjson
 *   2. Compute count + bytes per dump
 *   3. Write manifest with counts so we can restore later
 *   4. Verify dumps (re-count docs + file size sanity)
 *   5. Delete from Atlas only if verification passes
 *
 * USAGE:
 *   node archive_old_projects.js                # dry-run (default)
 *   node archive_old_projects.js --execute      # actually dump + delete
 *   node archive_old_projects.js --only-dump    # dump only, no delete
 *   node archive_old_projects.js --only-delete  # delete only (skip dump — DANGEROUS, only after verified dump)
 */
const fs = require('fs');
const path = require('path');
const { MongoClient } = require('mongodb');

const env = fs.readFileSync('E:/AI/.env','utf8').split(/\r?\n/).reduce((a,l)=>{const m=l.match(/^([^=]+)=(.*)$/);if(m)a[m[1].trim()]=m[2].trim();return a;},{});

const KEEP_PROJECTS = new Set(['BalloonFlow', 'BalloonFlow_PixelArtConverter']);
const COLLECTIONS = ['code_base', 'code_expert', 'design_base', 'design_expert', 'unity_configs', 'art_assets', 'level_backups'];
const ARCHIVE_ROOT = 'E:/AI/db_archive';
const NOW = new Date().toISOString();

const args = process.argv.slice(2);
const MODE = args.includes('--only-delete') ? 'delete'
           : args.includes('--only-dump')   ? 'dump'
           : args.includes('--execute')      ? 'both'
           : 'dryrun';

async function main() {
  const client = new MongoClient(env.MONGO_URI);
  await client.connect();
  const db = client.db('aigame');

  // 1. Discover all projects across collections, filtering out the kept ones
  const projectSet = new Set();
  for (const coll of COLLECTIONS) {
    const projects = await db.collection(coll).distinct('project');
    for (const p of projects) {
      if (p && !KEEP_PROJECTS.has(p)) projectSet.add(p);
    }
  }
  const projects = Array.from(projectSet).sort();

  console.log(`=== Mode: ${MODE} ===`);
  console.log(`Projects to archive (${projects.length}):`, projects);
  console.log(`Collections per project (${COLLECTIONS.length}):`, COLLECTIONS);
  console.log('');

  if (!fs.existsSync(ARCHIVE_ROOT)) fs.mkdirSync(ARCHIVE_ROOT, { recursive: true });

  const manifest = {
    archived_at: NOW,
    mode: MODE,
    projects: {},
  };

  let grandTotalDocs = 0;
  let grandTotalBytes = 0;

  for (const project of projects) {
    const projDir = path.join(ARCHIVE_ROOT, project);
    if (MODE !== 'delete' && !fs.existsSync(projDir)) fs.mkdirSync(projDir, { recursive: true });

    const summary = { counts: {}, bytes: {}, total_docs: 0, total_bytes: 0 };

    for (const coll of COLLECTIONS) {
      const filter = { project };
      const count = await db.collection(coll).countDocuments(filter);
      if (count === 0) continue;

      const outPath = path.join(projDir, `${coll}.ndjson`);

      if (MODE === 'dump' || MODE === 'both') {
        const cursor = db.collection(coll).find(filter, { batchSize: 200 });
        const stream = fs.createWriteStream(outPath);
        let written = 0;
        for await (const doc of cursor) {
          // Convert _id to string for JSON serialization
          if (doc._id && typeof doc._id === 'object' && doc._id.toString) {
            doc._id = { $oid: doc._id.toString() };
          }
          stream.write(JSON.stringify(doc) + '\n');
          written++;
        }
        await new Promise(r => stream.end(r));
        const size = fs.statSync(outPath).size;
        summary.counts[coll] = count;
        summary.bytes[coll] = size;
        summary.total_docs += count;
        summary.total_bytes += size;
        console.log(`  dump  ${project}/${coll}: ${count} docs → ${(size / 1024 / 1024).toFixed(2)} MB`);

        if (written !== count) {
          console.error(`  ERROR: wrote ${written} but DB has ${count}`);
          process.exit(2);
        }
      } else if (MODE === 'dryrun') {
        summary.counts[coll] = count;
        summary.total_docs += count;
        console.log(`  [dry] ${project}/${coll}: ${count} docs`);
      } else if (MODE === 'delete') {
        // Verify dump exists + count matches before delete
        if (!fs.existsSync(outPath)) {
          console.log(`  SKIP delete ${project}/${coll}: dump missing`);
          continue;
        }
        const lineCount = fs.readFileSync(outPath, 'utf8').split('\n').filter(Boolean).length;
        if (lineCount !== count) {
          console.log(`  SKIP delete ${project}/${coll}: dump has ${lineCount} but DB has ${count}`);
          continue;
        }
        const result = await db.collection(coll).deleteMany(filter);
        console.log(`  delete ${project}/${coll}: ${result.deletedCount} docs removed`);
        summary.counts[coll] = result.deletedCount;
      }
    }

    if (MODE === 'dump' || MODE === 'both') {
      fs.writeFileSync(path.join(projDir, '_manifest.json'), JSON.stringify({
        project, archived_at: NOW, ...summary
      }, null, 2));
      grandTotalDocs += summary.total_docs;
      grandTotalBytes += summary.total_bytes;
    }
    manifest.projects[project] = summary;
  }

  if (MODE === 'dump' || MODE === 'both') {
    fs.writeFileSync(path.join(ARCHIVE_ROOT, '_master_manifest.json'), JSON.stringify(manifest, null, 2));
    console.log(`\nGrand total dumped: ${grandTotalDocs} docs / ${(grandTotalBytes / 1024 / 1024).toFixed(2)} MB`);
  }

  if (MODE === 'both') {
    console.log('\n=== Running delete pass ===');
    for (const project of projects) {
      for (const coll of COLLECTIONS) {
        const filter = { project };
        const count = await db.collection(coll).countDocuments(filter);
        if (count === 0) continue;
        const projDir = path.join(ARCHIVE_ROOT, project);
        const outPath = path.join(projDir, `${coll}.ndjson`);
        if (!fs.existsSync(outPath)) {
          console.log(`  SKIP delete ${project}/${coll}: no dump`);
          continue;
        }
        const lineCount = fs.readFileSync(outPath, 'utf8').split('\n').filter(Boolean).length;
        if (lineCount !== count) {
          console.log(`  SKIP delete ${project}/${coll}: count mismatch dump=${lineCount} db=${count}`);
          continue;
        }
        const result = await db.collection(coll).deleteMany(filter);
        console.log(`  delete ${project}/${coll}: ${result.deletedCount} docs removed`);
      }
    }
  }

  await client.close();
  console.log('\nDone.');
}

main().catch(e => { console.error(e); process.exit(1); });
