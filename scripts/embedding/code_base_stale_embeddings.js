// code_base 의 낡은 OpenAI embedding 탐지/무효화 (2026-10-13).
// 결함: parser.js 는 $set 업서트라 내용을 바꿔도 기존 embedding 을 남긴다 → embedded_at < updatedAt 인 문서는
//       지금 내용과 안 맞는 벡터일 수 있다. embed_collection.py 는 embedding 이 "없는" 문서만 채우므로 먼저 비워야 한다.
// 규칙: embedding 이 있고 embedded_at 이 updatedAt 보다 이르면 낡은 것으로 본다(내용이 같아도 parser 가 updatedAt 을
//       갱신하므로 넓게 잡힌다 — 다시 임베딩해도 비용은 몇 초라 안전한 쪽을 택함).
// 사용: node scripts/embedding/code_base_stale_embeddings.js [--project=P] [--unset [--log=<file.ejson>]]
//   기본은 조회만(프로젝트별 개수), 파일을 쓰지 않는다. --unset 은 대상 문서의 _id·옛 embedding 3필드를 EJSON canonical 로
//   백업(덮어쓰기 금지, --log 생략 시 deleted/code_base_stale_embeddings_<시각>.ejson)한 뒤 그 _id 들에서만 3필드 제거.
//   (2026-10-13 수정: 예전엔 --log 를 조회 때도 써서 같은 경로로 다시 돌리면 기록이 덮어써졌다)
//   그다음: python scripts/embed_collection.py code_base
const fs = require("fs"), path = require("path");
for (const l of fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n")) { const m = l.trim().match(/^([A-Z_]+)=(.*)$/); if (m && m[1] === "MONGO_URI" && !process.env.MONGO_URI) process.env.MONGO_URI = m[2]; }
const { MongoClient } = require("mongodb");
const { writeDumpOnce, stampedPath } = require("./lib_dump");
const opt = Object.fromEntries(process.argv.slice(2).filter(a => a.startsWith("--")).map(a => { const i = a.indexOf("="); return i < 0 ? [a.slice(2), true] : [a.slice(2, i), a.slice(i + 1)]; }));
(async () => {
  const c = await MongoClient.connect(process.env.MONGO_URI); const col = c.db("aigame").collection("code_base");
  const match = { embedding: { $exists: true }, ...(opt.project ? { project: opt.project } : {}) };
  const stale = await col.aggregate([
    { $match: match },
    { $match: { $expr: { $lt: [{ $toDate: "$embedded_at" }, { $toDate: "$updatedAt" }] } } },
    { $project: { project: 1, fileId: 1, embedded_at: 1, updatedAt: 1, embedding_model: 1, embedding: 1 } },
  ]).toArray();
  const noTime = await col.countDocuments({ ...match, $or: [{ embedded_at: { $exists: false } }, { updatedAt: { $exists: false } }] });
  const by = {}; for (const d of stale) by[d.project] = (by[d.project] || 0) + 1;
  const tot = {}; for (const r of await col.aggregate([{ $match: match }, { $group: { _id: "$project", n: { $sum: 1 } } }]).toArray()) tot[r._id] = r.n;
  console.log(JSON.stringify({ stale_total: stale.length, missing_timestamps: noTime, by_project: Object.fromEntries(Object.entries(tot).map(([p, n]) => [p, `${by[p] || 0}/${n}`])) }));
  if (!opt.unset) { if (opt.log) console.log("--log 는 --unset 과 함께일 때만 쓴다(조회는 파일을 쓰지 않음)"); await c.close(); return; }
  if (!stale.length) { console.log("비울 문서 없음"); await c.close(); return; }
  const log = writeDumpOnce(opt.log || stampedPath(path.join(__dirname, "deleted"), "code_base_stale_embeddings"), stale);
  console.log("backup (EJSON canonical, 옛 embedding 포함) ->", log, stale.length);
  const r = await col.updateMany({ _id: { $in: stale.map(d => d._id) }, embedding: { $exists: true } }, { $unset: { embedding: "", embedding_model: "", embedded_at: "" } });
  console.log("unset embedding on", r.modifiedCount);
  await c.close();
})().catch(e => { console.error(e.code === "EEXIST" ? `백업 파일이 이미 있음 — 덮어쓰지 않고 중단: ${e.path}` : e); process.exit(1); });
