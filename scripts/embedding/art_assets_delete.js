// art_assets 문서 삭제 (사람이 승인한 목록만, 2026-10-12, 2026-10-13 백업 규칙 수정). 업서트(art_index.js)와 분리된 별도 도구.
// 사용: node scripts/embedding/art_assets_delete.js <project> <paths_file> [--apply [--dump=<file.ejson>]]
//   - paths_file: 한 줄에 path 하나 (art_index.js --missing-out 출력)
//   - 디스크에 지금 파일이 **있는** path 는 대상에서 빼고 보고한다.
//   - --apply 없으면 조회만 하고 **아무 파일도 쓰지 않는다**.
//   - --apply: 대상 문서 전체를 EJSON canonical 로 백업(기존 파일 덮어쓰기 금지, --dump 생략 시
//     scripts/embedding/deleted/art_assets_<project>_<시각>.ejson) → 백업 성공 후 그 _id 로만 삭제.
//   - 복구: node scripts/embedding/restore_mongo_dump.js <dump> art_assets --apply
const fs = require("fs"), path = require("path");
for (const l of fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n")) { const m = l.trim().match(/^([A-Z_]+)=(.*)$/); if (m && m[1] === "MONGO_URI" && !process.env.MONGO_URI) process.env.MONGO_URI = m[2]; }
const { MongoClient } = require("mongodb");
const { writeDumpOnce, stampedPath } = require("./lib_dump");
const [PROJECT, PATHS] = process.argv.slice(2);
const APPLY = process.argv.includes("--apply");
const DUMP_ARG = (process.argv.find(a => a.startsWith("--dump=")) || "").slice(7);
if (!PROJECT || !PATHS || PATHS.startsWith("--")) { console.error("usage: node art_assets_delete.js <project> <paths_file> [--apply [--dump=f.ejson]]"); process.exit(2); }
const listed = fs.readFileSync(PATHS, "utf8").split(/\r?\n/).filter(Boolean);
const stillOnDisk = listed.filter(p => fs.existsSync(p));
const targets = listed.filter(p => !fs.existsSync(p));
(async () => {
  const c = await MongoClient.connect(process.env.MONGO_URI); const col = c.db("aigame").collection("art_assets");
  const docs = await col.find({ project: PROJECT, path: { $in: targets } }).toArray();
  const before = await col.countDocuments({ project: PROJECT });
  console.log(JSON.stringify({ project: PROJECT, listed: listed.length, still_on_disk: stillOnDisk.length, still_on_disk_sample: stillOnDisk.slice(0, 5), targets: targets.length, docs_found: docs.length, project_count_before: before }));
  if (!APPLY) { console.log("dry-run: 아무것도 쓰지 않음 (삭제하려면 --apply)"); await c.close(); return; }
  if (!docs.length) { console.log("삭제할 문서 없음"); await c.close(); return; }
  const dump = writeDumpOnce(DUMP_ARG || stampedPath(path.join(__dirname, "deleted"), `art_assets_${PROJECT}`), docs);
  console.log("backup (EJSON canonical) ->", dump, docs.length);
  const r = await col.deleteMany({ _id: { $in: docs.map(d => d._id) }, project: PROJECT });
  console.log("deleted", r.deletedCount, "| project count after:", await col.countDocuments({ project: PROJECT }));
  await c.close();
})().catch(e => { console.error(e.code === "EEXIST" ? `백업 파일이 이미 있음 — 덮어쓰지 않고 중단: ${e.path}` : e); process.exit(1); });
