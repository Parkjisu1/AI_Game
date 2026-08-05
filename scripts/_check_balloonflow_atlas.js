#!/usr/bin/env node
const fs = require('fs');
const env = fs.readFileSync('E:/AI/.env','utf8').split(/\r?\n/).reduce((a,l)=>{const m=l.match(/^([^=]+)=(.*)$/);if(m)a[m[1].trim()]=m[2].trim();return a;},{});
const { MongoClient } = require('mongodb');
(async () => {
  const c = new MongoClient(env.MONGO_URI);
  await c.connect();
  const db = c.db('aigame');
  for (const coll of ['code_base','code_expert','design_base','design_expert','unity_configs']) {
    const total = await db.collection(coll).countDocuments({ project: 'BalloonFlow' });
    const withEmb = await db.collection(coll).countDocuments({ project: 'BalloonFlow', embedding: { $exists: true } });
    console.log('  ' + coll.padEnd(20) + ' BalloonFlow=' + String(total).padStart(5) + '  embedded=' + String(withEmb).padStart(5));
  }
  await c.close();
})();
