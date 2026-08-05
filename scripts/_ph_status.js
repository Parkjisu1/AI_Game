const fs = require('fs');
const env = fs.readFileSync('E:/AI/.env','utf8').split(/\r?\n/).reduce((a,l)=>{const m=l.match(/^([^=]+)=(.*)$/);if(m)a[m[1].trim()]=m[2].trim();return a;},{});
const { MongoClient } = require('mongodb');
(async () => {
  const c = new MongoClient(env.MONGO_URI); await c.connect();
  const db = c.db('aigame');
  for (const coll of ['pixelforge_tasks','pixelforge_grid_levels','pixelforge_levels','hermes_team_scores']) {
    const total = await db.collection(coll).countDocuments({});
    const emb = await db.collection(coll).countDocuments({ embedding: { $exists: true } });
    console.log(coll.padEnd(24)+'| total '+String(total).padStart(6)+' | embedded '+String(emb).padStart(6)+' | no-emb '+String(total-emb).padStart(6));
  }
  await c.close();
})().catch(e=>{console.error(e.message);process.exit(1)});
