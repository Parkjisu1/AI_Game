#!/usr/bin/env node
/**
 * Ingest BalloonFlow art assets metadata into `art_assets` collection.
 * - Indexes file path, size, type, folder categorization, GUID (from .meta), tags
 * - Does NOT embed image binaries — only metadata
 * - Sweeps multiple roots: Assets/2.Sprite, 3.Material, 4.Atlas, 5.Fonts, 6.Sound,
 *   Resources_backup (history), and Animation/Animator/Modeling backups.
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { MongoClient } = require('mongodb');

const ENV = fs.readFileSync('E:/AI/.env', 'utf8').split(/\r?\n/).reduce((a, l) => {
  const m = l.match(/^([^=]+)=(.*)$/);
  if (m) a[m[1].trim()] = m[2].trim();
  return a;
}, {});

const PROJECT = 'BalloonFlow';
const GENRE = 'Puzzle';
const NOW = new Date().toISOString();

const ROOTS = [
  { path: 'E:/Balloonflow/BallonFlow_Git/BalloonFlow/Assets/2.Sprite', kind: 'sprite', source: 'current' },
  { path: 'E:/Balloonflow/BallonFlow_Git/BalloonFlow/Assets/3.Material', kind: 'material', source: 'current' },
  { path: 'E:/Balloonflow/BallonFlow_Git/BalloonFlow/Assets/4.Atlas', kind: 'atlas', source: 'current' },
  { path: 'E:/Balloonflow/BallonFlow_Git/BalloonFlow/Assets/5.Fonts', kind: 'font', source: 'current' },
  { path: 'E:/Balloonflow/BallonFlow_Git/BalloonFlow/Assets/6.Sound', kind: 'audio', source: 'current' },
  { path: 'E:/Balloonflow/BalloonFlow_History/Resources_backup_20260407_105645/Animation', kind: 'animation', source: 'backup_20260407' },
  { path: 'E:/Balloonflow/BalloonFlow_History/Resources_backup_20260407_105645/Animator', kind: 'animator', source: 'backup_20260407' },
  { path: 'E:/Balloonflow/BalloonFlow_History/Resources_backup_20260407_105645/Atlas', kind: 'atlas', source: 'backup_20260407' },
  { path: 'E:/Balloonflow/BalloonFlow_History/Resources_backup_20260407_105645/Modeling', kind: 'modeling', source: 'backup_20260407' },
  { path: 'E:/Balloonflow/BalloonFlow_History/Resources_backup_20260407_105645/Popup', kind: 'popup_backup', source: 'backup_20260407' },
  { path: 'E:/Balloonflow/BalloonFlow_History/Resources_backup_20260407_105645/Prefabs', kind: 'prefab_backup', source: 'backup_20260407' },
  { path: 'E:/Balloonflow/BalloonFlow_History/Resources_backup_20260407_105645/Shaders', kind: 'shader', source: 'backup_20260407' },
];

const EXT_KIND = {
  '.png': 'image', '.jpg': 'image', '.jpeg': 'image', '.psd': 'image_psd', '.tga': 'image_tga',
  '.mat': 'material', '.shader': 'shader', '.cginc': 'shader_include',
  '.spriteatlas': 'spriteatlas', '.spriteatlasv2': 'spriteatlas',
  '.ttf': 'font', '.otf': 'font',
  '.wav': 'audio_wav', '.mp3': 'audio_mp3', '.ogg': 'audio_ogg',
  '.anim': 'animation', '.controller': 'animator', '.overrideController': 'animator_override',
  '.fbx': 'model_fbx', '.obj': 'model_obj',
  '.prefab': 'prefab',
};

function* walk(dir) {
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
  catch { return; }
  for (const e of entries) {
    const full = path.join(dir, e.name);
    if (e.isDirectory()) yield* walk(full);
    else if (e.isFile()) yield full;
  }
}

function readGuid(metaPath) {
  try {
    const text = fs.readFileSync(metaPath, 'utf8');
    const m = text.match(/^guid:\s*([0-9a-f]+)/m);
    return m ? m[1] : null;
  } catch { return null; }
}

function hash12(s) { return crypto.createHash('sha1').update(s).digest('hex').slice(0, 12); }

function tagFromPath(p, kind) {
  const tags = [kind];
  const lower = p.toLowerCase().replace(/\\/g, '/');
  if (lower.includes('/ui/')) tags.push('ui');
  if (lower.includes('/ts/')) tags.push('ts');
  if (lower.includes('popup')) tags.push('popup');
  if (lower.includes('balloon')) tags.push('balloon');
  if (lower.includes('dart')) tags.push('dart');
  if (lower.includes('rail')) tags.push('rail');
  if (lower.includes('booster')) tags.push('booster');
  if (lower.includes('hud')) tags.push('hud');
  if (lower.includes('icon')) tags.push('icon');
  if (lower.includes('button') || lower.includes('btn')) tags.push('button');
  if (lower.includes('bg_') || lower.includes('background')) tags.push('background');
  if (lower.includes('bgm/')) tags.push('bgm');
  if (lower.includes('effect/')) tags.push('sfx');
  return Array.from(new Set(tags));
}

async function main() {
  const client = new MongoClient(ENV.MONGO_URI);
  await client.connect();
  const db = client.db('aigame');
  const coll = db.collection('art_assets');

  // Ensure index
  try { await coll.createIndex({ assetId: 1, project: 1 }, { unique: true }); } catch {}
  try { await coll.createIndex({ project: 1, kind: 1 }); } catch {}
  try { await coll.createIndex({ project: 1, source: 1 }); } catch {}

  let total = 0, added = 0, updated = 0;
  const kindStats = {};

  for (const root of ROOTS) {
    if (!fs.existsSync(root.path)) { console.log(`SKIP missing: ${root.path}`); continue; }
    console.log(`\n-- ${root.path} (kind=${root.kind})`);
    let inRoot = 0;
    for (const fpath of walk(root.path)) {
      if (fpath.endsWith('.meta')) continue;  // .meta is sidecar
      const ext = path.extname(fpath).toLowerCase();
      const kind = EXT_KIND[ext] || root.kind;
      if (kind === 'prefab' && root.source === 'current') continue;  // already in unity_configs

      const stat = fs.statSync(fpath);
      if (stat.size === 0) continue;

      const rel = path.relative('E:/Balloonflow', fpath).replace(/\\/g, '/');
      const guid = readGuid(fpath + '.meta');
      const assetId = guid ? `guid_${guid}` : hash12(rel);
      const folder = path.dirname(rel);
      const fileName = path.basename(fpath);

      const doc = {
        assetId,
        project: PROJECT,
        genre: GENRE,
        kind,
        source: root.source,
        source_root: root.kind,
        file_path: rel,
        absolute_path: fpath.replace(/\\/g, '/'),
        file_name: fileName,
        folder,
        size_bytes: stat.size,
        ext,
        guid: guid || null,
        tags: tagFromPath(rel, kind),
        mtime: stat.mtime.toISOString(),
        ingested_at: NOW,
      };

      const result = await coll.updateOne(
        { assetId, project: PROJECT },
        { $set: doc },
        { upsert: true }
      );
      if (result.upsertedCount) added++;
      else if (result.modifiedCount) updated++;
      total++; inRoot++;
      kindStats[kind] = (kindStats[kind] || 0) + 1;
    }
    console.log(`   indexed ${inRoot}`);
  }

  console.log(`\n=== SUMMARY ===`);
  console.log(`Total scanned: ${total}, added=${added}, updated=${updated}`);
  console.log(`By kind:`, JSON.stringify(kindStats, null, 2));
  await client.close();
}

main().catch(e => { console.error(e); process.exit(1); });
