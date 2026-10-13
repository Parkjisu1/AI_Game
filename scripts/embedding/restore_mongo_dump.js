// 삭제 백업 덤프 → Mongo 복원 (2026-10-13). 기본은 dry-run(쓰기 없음).
// 사용: node scripts/embedding/restore_mongo_dump.js <dump> <collection> [--target=<collection>] [--apply] [--date-fields=updatedAt,...]
//   - EJSON canonical 덤프(.ejson, lib_dump.js 출력): ObjectId·Date·숫자 타입이 그대로 되살아난다.
//   - 2026-10-12 이전의 평범한 JSON 덤프(_id·날짜가 문자열): 자동 감지해 변환한다.
//       _id 가 24자리 hex 문자열이면 ObjectId, --date-fields(기본 updatedAt,createdAt) 의 ISO 문자열은 Date.
//       (embedded_at 처럼 원래 문자열로 저장되던 필드는 바꾸지 않는다 — 원본 컬렉션의 같은 필드 타입과 비교해 고를 것)
//   - 대상 컬렉션(--target, 기본 <collection>)에 같은 _id 가 이미 있으면 그 문서는 건너뛴다(덮어쓰지 않음).
//   - <collection> 은 타입 비교 기준(같은 project 의 살아 있는 문서와 필드 타입 대조)에만 쓴다.
const fs = require("fs"), path = require("path");
for (const l of fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n")) { const m = l.trim().match(/^([A-Z_]+)=(.*)$/); if (m && m[1] === "MONGO_URI" && !process.env.MONGO_URI) process.env.MONGO_URI = m[2]; }
const { MongoClient, ObjectId, BSON } = require("mongodb");
const [DUMP, COLL] = process.argv.slice(2);
if (!DUMP || !COLL || COLL.startsWith("--")) { console.error("usage: node restore_mongo_dump.js <dump> <collection> [--target=c] [--apply] [--date-fields=a,b]"); process.exit(2); }
const opt = Object.fromEntries(process.argv.slice(4).filter(a => a.startsWith("--")).map(a => { const i = a.indexOf("="); return i < 0 ? [a.slice(2), true] : [a.slice(2, i), a.slice(i + 1)]; }));
const TARGET = opt.target || COLL;
const DATE_FIELDS = (opt["date-fields"] || "updatedAt,createdAt").split(",").filter(Boolean);
const raw = fs.readFileSync(DUMP, "utf8");
const isEjson = /"\$oid"\s*:/.test(raw) || /"\$date"\s*:/.test(raw);
let docs;
if (isEjson) docs = BSON.EJSON.parse(raw, { relaxed: false });
else {
  docs = JSON.parse(raw);
  for (const d of docs) {
    if (typeof d._id === "string" && /^[0-9a-f]{24}$/i.test(d._id)) d._id = new ObjectId(d._id);
    for (const f of DATE_FIELDS) if (typeof d[f] === "string" && !isNaN(Date.parse(d[f]))) d[f] = new Date(d[f]);
  }
}
if (!Array.isArray(docs)) { console.error("덤프는 문서 배열이어야 한다"); process.exit(2); }
const typeOf = v => v === null ? "null" : v instanceof ObjectId ? "objectId" : v instanceof Date ? "date" : Array.isArray(v) ? "array" : typeof v === "object" && v._bsontype ? ({ Double: "number", Int32: "number" }[v._bsontype] || v._bsontype) : typeof v;
(async () => {
  const c = await MongoClient.connect(process.env.MONGO_URI); const db = c.db("aigame");
  const ids = docs.map(d => d._id);
  const exists = new Set((await db.collection(TARGET).find({ _id: { $in: ids } }, { projection: { _id: 1 } }).toArray()).map(d => String(d._id)));
  const todo = docs.filter(d => !exists.has(String(d._id)));
  // 타입 대조: 덤프 첫 문서와 같은 project 의 살아 있는 문서
  const ref = docs[0] && await db.collection(COLL).findOne(docs[0].project ? { project: docs[0].project } : {});
  const mism = [];
  if (ref && docs[0]) for (const k of Object.keys(docs[0])) if (k in ref && typeOf(docs[0][k]) !== typeOf(ref[k])) mism.push(`${k}: dump=${typeOf(docs[0][k])} live=${typeOf(ref[k])}`);
  console.log(JSON.stringify({ dump: DUMP, format: isEjson ? "ejson" : "plain-json(converted)", docs: docs.length, target: TARGET, already_in_target: exists.size, to_insert: todo.length, type_mismatch_vs_live: mism }));
  if (!opt.apply) { console.log("dry-run: 쓰지 않음 (복원하려면 --apply)"); await c.close(); return; }
  if (todo.length) { const r = await db.collection(TARGET).insertMany(todo, { ordered: false }); console.log("inserted", r.insertedCount, "into", TARGET); }
  await c.close();
})().catch(e => { console.error(e); process.exit(1); });
