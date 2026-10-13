// Mongo 지식베이스 현황 (쓰기 없음, 2026-10-12).
// 사용: node scripts/embedding/kb_status.js <project> [<project> ...]
//   code_base / unity_configs / art_assets 의 project 별 문서 수와 최근 updatedAt.
//   Qdrant 쪽은 임베딩컴에서 python3 ~/kb_qdrant.py counts <project...>
const fs = require("fs"), path = require("path");
for (const l of fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n")) { const m = l.trim().match(/^([A-Z_]+)=(.*)$/); if (m && !process.env[m[1]]) process.env[m[1]] = m[2]; }
const { MongoClient } = require("mongodb");
const projects = process.argv.slice(2);
if (!projects.length) { console.error("usage: node kb_status.js <project> [...]"); process.exit(2); }
(async () => {
  const c = await MongoClient.connect(process.env.MONGO_URI); const db = c.db("aigame");
  const rows = [];
  for (const p of projects) {
    const r = { project: p };
    for (const col of ["code_base", "unity_configs", "art_assets"]) {
      r[col] = await db.collection(col).countDocuments({ project: p });
      const last = await db.collection(col).find({ project: p }, { projection: { updatedAt: 1, updated_at: 1 } }).sort({ updatedAt: -1 }).limit(1).toArray();
      r[col + "_last"] = last[0] ? String(last[0].updatedAt || last[0].updated_at || "").slice(0, 24) : "";
    }
    rows.push(r);
  }
  console.table(rows);
  await c.close();
})().catch(e => { console.error(e); process.exit(1); });
