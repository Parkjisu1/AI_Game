#!/usr/bin/env node
const fs = require('fs');
const env = fs.readFileSync('E:/AI/.env','utf8').split(/\r?\n/).reduce((a,l)=>{const m=l.match(/^([^=]+)=(.*)$/);if(m)a[m[1].trim()]=m[2].trim();return a;},{});
const { MongoClient } = require('mongodb');
(async () => {
  const c = new MongoClient(env.MONGO_URI);
  await c.connect();
  const db = c.db('aigame');
  const names = (await db.listCollections().toArray()).map(c => c.name).sort();
  console.log('Collection                       | docs    | storage MB');
  console.log('---------------------------------|---------|----------');
  let total = 0;
  for (const n of names) {
    try {
      const stats = await db.command({ collStats: n });
      const sizeMB = (stats.storageSize / 1024 / 1024).toFixed(2);
      const count = stats.count;
      total += stats.storageSize;
      console.log(n.padEnd(33) + '| ' + String(count).padStart(7) + ' | ' + String(sizeMB).padStart(8));
    } catch (e) { console.log(n + ': err ' + e.message); }
  }
  console.log('---');
  console.log('TOTAL storage MB: ' + (total / 1024 / 1024).toFixed(2));
  await c.close();
})();
