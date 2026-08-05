#!/usr/bin/env node
const fs = require('fs');
const env = fs.readFileSync('E:/AI/.env','utf8').split(/\r?\n/).reduce((a,l)=>{const m=l.match(/^([^=]+)=(.*)$/);if(m)a[m[1].trim()]=m[2].trim();return a;},{});
const { MongoClient } = require('mongodb');
(async () => {
  const c = new MongoClient(env.MONGO_URI);
  await c.connect();
  const db = c.db('aigame');

  for (const n of ['code_base','code_expert','design_base','design_expert','unity_configs','art_assets','level_backups','hermes_team_scores','pixelforge_tasks']) {
    const sample = await db.collection(n).findOne({});
    if (!sample) continue;
    const hasProject = 'project' in sample;
    const projects = await db.collection(n).distinct('project');
    console.log(n.padEnd(22) + ' project_field=' + hasProject + '  distinct_projects=' + projects.length);
  }

  await c.close();
})();
