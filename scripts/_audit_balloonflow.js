#!/usr/bin/env node
// 검수 — 임베딩이 실제로 존재하고 1536차원인지, source 분포가 맞는지 검증
const fs = require('fs');
const env = fs.readFileSync('E:/AI/.env','utf8').split(/\r?\n/).reduce((a,l)=>{const m=l.match(/^([^=]+)=(.*)$/);if(m)a[m[1].trim()]=m[2].trim();return a;},{});
const { MongoClient } = require('mongodb');

(async () => {
  const c = new MongoClient(env.MONGO_URI);
  await c.connect();
  const db = c.db('aigame');

  console.log('=== 1) 임베딩 dimension 샘플 검증 ===');
  for (const coll of ['code_base','design_base','unity_configs','art_assets','level_backups']) {
    const q = coll === 'code_base'
      ? { project: { $in: ['BalloonFlow','BalloonFlow_PixelArtConverter'] }, embedding: { $exists: true } }
      : { project: 'BalloonFlow', embedding: { $exists: true } };
    const sample = await db.collection(coll).findOne(q, { projection: { embedding: 1, embedding_model: 1, embedded_at: 1 } });
    if (!sample) { console.log(`  ${coll}: NO SAMPLE`); continue; }
    const dim = Array.isArray(sample.embedding) ? sample.embedding.length : 'NOT_ARRAY';
    const first = Array.isArray(sample.embedding) ? sample.embedding[0]?.toFixed(4) : 'n/a';
    console.log(`  ${coll.padEnd(15)} dim=${dim}  model=${sample.embedding_model}  date=${(sample.embedded_at||'').slice(0,19)}  first_val=${first}`);
  }

  console.log('\n=== 2) BalloonFlow design_base source 분포 ===');
  const sources = await db.collection('design_base').aggregate([
    { $match: { project: 'BalloonFlow' } },
    { $group: { _id: { source: '$source', data_type: '$data_type' }, n: { $sum: 1 } } },
    { $sort: { n: -1 } }
  ]).toArray();
  for (const r of sources) console.log(`  source=${r._id.source}  type=${r._id.data_type}  n=${r.n}`);

  console.log('\n=== 3) BalloonFlow code_base 분포 ===');
  const cb = await db.collection('code_base').aggregate([
    { $match: { project: { $in: ['BalloonFlow','BalloonFlow_PixelArtConverter'] } } },
    { $group: { _id: '$project', n: { $sum: 1 } } }
  ]).toArray();
  for (const r of cb) console.log(`  ${r._id}: ${r.n}`);

  console.log('\n=== 4) art_assets 분포 ===');
  const aa = await db.collection('art_assets').aggregate([
    { $match: { project: 'BalloonFlow' } },
    { $group: { _id: '$source', n: { $sum: 1 } } },
    { $sort: { n: -1 } }
  ]).toArray();
  for (const r of aa) console.log(`  source=${r._id}: ${r.n}`);

  console.log('\n=== 5) 다른 프로젝트 잔존물 확인 (예상=0) ===');
  for (const coll of ['code_base','design_base','design_expert','unity_configs','art_assets']) {
    const list = await db.collection(coll).distinct('project');
    const nonBalloon = list.filter(p => p && !['BalloonFlow','BalloonFlow_PixelArtConverter'].includes(p));
    console.log(`  ${coll}: leftover projects = ${nonBalloon.length === 0 ? '(none)' : nonBalloon.join(', ')}`);
  }

  console.log('\n=== 6) Vector index 상태 ===');
  for (const coll of ['code_base','pixelforge_tasks','hermes_team_scores','design_base','art_assets']) {
    const idxs = await db.collection(coll).listSearchIndexes().toArray();
    console.log(`  ${coll}: ${idxs.length} index(es)  ${idxs.map(i => `${i.name}=${i.status||i.queryable}`).join(', ')}`);
  }

  console.log('\n=== 7) Atlas 용량 ===');
  let total = 0;
  for (const n of (await db.listCollections().toArray()).map(c => c.name).sort()) {
    const s = await db.command({ collStats: n });
    total += s.size;
  }
  console.log(`  Total dataSize: ${(total / 1024 / 1024).toFixed(2)} MB  (M0 limit = 512 MB)`);

  await c.close();
})();
