#!/usr/bin/env node
const fs = require('fs');
const env = fs.readFileSync('E:/AI/.env','utf8').split(/\r?\n/).reduce((a,l)=>{const m=l.match(/^([^=]+)=(.*)$/);if(m)a[m[1].trim()]=m[2].trim();return a;},{});
const { MongoClient } = require('mongodb');
(async () => {
  const c = new MongoClient(env.MONGO_URI);
  await c.connect();
  const db = c.db('aigame');
  const sample = await db.collection('design_base').findOne({ project: 'BalloonFlow' });
  console.log('=== sample BalloonFlow design ===');
  console.log(JSON.stringify({
    _id: String(sample._id),
    designId: sample.designId,
    genre: sample.genre, domain: sample.domain, system: sample.system,
    data_type: sample.data_type, score: sample.score,
    source: sample.source, project: sample.project,
    has_embedding: !!sample.embedding,
    embedding_dim: sample.embedding ? sample.embedding.length : 0,
    provides: sample.provides, requires: sample.requires,
    keys: Object.keys(sample),
  }, null, 2));
  console.log('\n=== designId list (BalloonFlow) ===');
  const all = await db.collection('design_base').find({ project: 'BalloonFlow' }, { projection: { designId: 1, system: 1, domain: 1 } }).toArray();
  all.forEach(d => console.log('  ' + d.domain.padEnd(10) + ' / ' + (d.system||'').padEnd(30) + ' / ' + d.designId));
  await c.close();
})();
