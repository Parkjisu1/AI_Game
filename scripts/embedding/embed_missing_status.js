// Mongo 문서의 OpenAI `embedding` 필드 누락 현황 (쓰기 없음, 2026-10-12).
// 사용: node scripts/embedding/embed_missing_status.js [collection ...]
//   기본: embed_collection.py 대상 6종. code_base/code_expert 는 project 별로도 보여 준다.
const fs = require("fs"), path = require("path");
for (const l of fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n")) { const m = l.trim().match(/^([A-Z_]+)=(.*)$/); if (m && m[1] === "MONGO_URI" && !process.env.MONGO_URI) process.env.MONGO_URI = m[2]; }
const { MongoClient } = require("mongodb");
const COLLS = process.argv.slice(2).length ? process.argv.slice(2) : ["code_base", "code_expert", "design_base", "design_expert", "hermes_team_scores", "pixelforge_tasks"];
(async () => {
  const c = await MongoClient.connect(process.env.MONGO_URI); const db = c.db("aigame");
  for (const name of COLLS) {
    const col = db.collection(name);
    const total = await col.countDocuments(); const missing = await col.countDocuments({ embedding: { $exists: false } });
    console.log(`${name}: total=${total} missing_embedding=${missing}`);
    if (name.startsWith("code_") && missing) {
      const by = await col.aggregate([{ $match: { embedding: { $exists: false } } }, { $group: { _id: "$project", n: { $sum: 1 } } }, { $sort: { n: -1 } }]).toArray();
      console.log("   by project:", JSON.stringify(by.map(x => [x._id, x.n])));
    }
  }
  await c.close();
})().catch(e => { console.error(e); process.exit(1); });
