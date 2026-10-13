// parser.js 재실행 전후 code_base 내용 비교 → 바뀐/새 문서의 OpenAI embedding 무효화 (2026-10-12).
// parser.js 는 $set 업서트라 내용이 바뀌어도 기존 `embedding` 이 남는다(내용과 안 맞는 낡은 벡터).
// embed_collection.py 는 embedding 이 없는 문서만 채우므로, 바뀐 문서만 골라 embedding 을 지워 둔다.
//
// 사용:
//   node scripts/embedding/code_base_changed.js snapshot <project> <snap.json>     (parser.js 전)
//   node scripts/embedding/code_base_changed.js diff <project> <snap.json> [--unset] (parser.js 후)
//     diff: 내용 해시(_id·updatedAt·embedding*·usedBy 제외)가 달라진 문서 / 새 문서 / 사라진 문서 보고
//     --unset: 바뀐 문서 중 embedding 이 있는 것만 project 조건 + _id 로 embedding·embedding_model·embedded_at 제거
const fs = require("fs"), path = require("path"), crypto = require("crypto");
for (const l of fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n")) { const m = l.trim().match(/^([A-Z_]+)=(.*)$/); if (m && m[1] === "MONGO_URI" && !process.env.MONGO_URI) process.env.MONGO_URI = m[2]; }
const { MongoClient } = require("mongodb");
const [CMD, PROJECT, SNAP] = process.argv.slice(2);
if (!["snapshot", "diff"].includes(CMD) || !PROJECT || !SNAP) { console.error("usage: code_base_changed.js snapshot|diff <project> <snap.json> [--unset]"); process.exit(2); }
// usedBy 는 다른 파일이 바뀌면 같이 바뀌는 역참조라 "내용 변경"으로 치지 않는다(임베딩 텍스트에 안 들어감 — 아래 diff 출력으로 확인)
const SKIP = new Set(["_id", "updatedAt", "embedding", "embedding_model", "embedded_at", "usedBy"]);
const hash = d => crypto.createHash("sha1").update(JSON.stringify(Object.keys(d).filter(k => !SKIP.has(k)).sort().map(k => [k, d[k]]))).digest("hex");
(async () => {
  const c = await MongoClient.connect(process.env.MONGO_URI); const col = c.db("aigame").collection("code_base");
  const docs = await col.find({ project: PROJECT }).toArray();
  if (CMD === "snapshot") {
    fs.writeFileSync(SNAP, JSON.stringify(Object.fromEntries(docs.map(d => [String(d._id), { fileId: d.fileId, h: hash(d) }]))));
    console.log("snapshot", PROJECT, docs.length, "->", SNAP);
  } else {
    const snap = JSON.parse(fs.readFileSync(SNAP, "utf8"));
    const changed = [], added = [];
    for (const d of docs) { const s = snap[String(d._id)]; if (!s) added.push(d); else if (s.h !== hash(d)) changed.push(d); }
    const now = new Set(docs.map(d => String(d._id)));
    const gone = Object.entries(snap).filter(([id]) => !now.has(id)).map(([, v]) => v.fileId);
    console.log(JSON.stringify({ project: PROJECT, docs: docs.length, snapshot: Object.keys(snap).length, changed: changed.length, added: added.length, removed: gone.length }));
    console.log("changed:", changed.map(d => d.fileId).join(", "));
    console.log("added:", added.map(d => d.fileId).join(", "));
    const stale = changed.filter(d => d.embedding);
    console.log("changed with old embedding:", stale.length);
    if (process.argv.includes("--unset") && stale.length) {
      const r = await col.updateMany({ project: PROJECT, _id: { $in: stale.map(d => d._id) } }, { $unset: { embedding: "", embedding_model: "", embedded_at: "" } });
      console.log("unset embedding on", r.modifiedCount);
    }
  }
  await c.close();
})().catch(e => { console.error(e); process.exit(1); });
