#!/usr/bin/env node
const fs = require('fs');
const env = fs.readFileSync('E:/AI/.env','utf8').split(/\r?\n/).reduce((a,l)=>{const m=l.match(/^([^=]+)=(.*)$/);if(m)a[m[1].trim()]=m[2].trim();return a;},{});
const { MongoClient } = require('mongodb');
(async () => {
  const c = new MongoClient(env.MONGO_URI);
  await c.connect();
  const db = c.db('aigame');
  console.log('Collection            | BalloonFlow* | embedded | no-emb');
  console.log('----------------------|--------------|----------|--------');
  const queries = {
    'code_base':           { project: { $in: ['BalloonFlow','BalloonFlow_PixelArtConverter'] } },
    'code_expert':         { project: { $in: ['BalloonFlow','BalloonFlow_PixelArtConverter'] } },
    'design_base':         { project: 'BalloonFlow' },
    'design_expert':       { project: 'BalloonFlow' },
    'unity_configs':       { project: 'BalloonFlow' },
    'art_assets':          { project: 'BalloonFlow' },
    'level_backups':       { project: 'BalloonFlow' },
  };
  for (const [coll, q] of Object.entries(queries)) {
    const total = await db.collection(coll).countDocuments(q);
    const withEmb = await db.collection(coll).countDocuments({ ...q, embedding: { $exists: true } });
    const noEmb = total - withEmb;
    console.log(coll.padEnd(22) + '| ' + String(total).padStart(12) + ' | ' + String(withEmb).padStart(8) + ' | ' + String(noEmb).padStart(6));
  }
  await c.close();
})();
