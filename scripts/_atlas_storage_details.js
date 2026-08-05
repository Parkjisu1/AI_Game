#!/usr/bin/env node
const fs = require('fs');
const env = fs.readFileSync('E:/AI/.env','utf8').split(/\r?\n/).reduce((a,l)=>{const m=l.match(/^([^=]+)=(.*)$/);if(m)a[m[1].trim()]=m[2].trim();return a;},{});
const { MongoClient } = require('mongodb');
(async () => {
  const c = new MongoClient(env.MONGO_URI);
  await c.connect();
  const db = c.db('aigame');

  for (const n of ['code_base','unity_configs','pixelforge_tasks','pixelforge_grid_levels','design_base']) {
    const stats = await db.command({ collStats: n });
    const data = (stats.size / 1024 / 1024).toFixed(2);
    const storage = (stats.storageSize / 1024 / 1024).toFixed(2);
    const idx = (stats.totalIndexSize / 1024 / 1024).toFixed(2);
    console.log(n.padEnd(25) + ' docs=' + String(stats.count).padStart(6) + '  data=' + String(data).padStart(7) + ' MB  storage=' + String(storage).padStart(7) + ' MB  index=' + String(idx).padStart(6) + ' MB');
  }

  console.log('\n=== unity_configs by project ===');
  const ag = await db.collection('unity_configs').aggregate([{ $group: { _id: '$project', n: { $sum: 1 } } }, { $sort: { n: -1 } }]).toArray();
  for (const r of ag) console.log('  ' + String(r._id || 'null').padEnd(25) + ' ' + r.n);

  console.log('\n=== code_base by project ===');
  const cb = await db.collection('code_base').aggregate([{ $group: { _id: '$project', n: { $sum: 1 } } }, { $sort: { n: -1 } }]).toArray();
  for (const r of cb) console.log('  ' + String(r._id || 'null').padEnd(25) + ' ' + r.n);

  await c.close();
})();
