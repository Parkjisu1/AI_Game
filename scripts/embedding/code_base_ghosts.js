// code_base 유령 문서 탐지/삭제 (2026-10-12, 2026-10-13 백업 규칙 수정). 업서트(parser.js)와 분리된 별도 도구.
// 사용: node scripts/embedding/code_base_ghosts.js <project> <scripts_root> [--include=fileId,..] [--apply [--dump=<file.ejson>]]
//   - filePath(scripts_root 기준 상대) 가 디스크에 없는 문서를 찾는다.
//   - parser.js 는 fileId=클래스명 upsert(partial class 합쳐짐)라, 파일이 없어도 그 클래스가 다른 .cs 에
//     정의돼 있을 수 있다 → fileId·classes[].className 이 현재 .cs 어디에도 `class|struct|interface|enum|record <이름>` 로
//     정의되지 않은 문서만 "확정 유령"으로 친다.
//   - --include=fileId,..: 파일이 없고 클래스가 다른 파일로 옮겨져 그쪽에 자기 문서가 따로 있는 경우(이름 변경 등) 사람이 확인 후 포함
//   - --apply 없으면 조회만 하고 **아무 파일도 쓰지 않는다**.
//   - --apply: 확정 유령 원문을 EJSON canonical 로 백업(덮어쓰기 금지, 생략 시 deleted/code_base_ghosts_<project>_<시각>.ejson)
//     → 백업 성공 후 그 _id 로만 삭제(project 조건 포함). 복구: restore_mongo_dump.js <dump> code_base --apply
const fs = require("fs"), path = require("path");
for (const l of fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n")) { const m = l.trim().match(/^([A-Z_]+)=(.*)$/); if (m && m[1] === "MONGO_URI" && !process.env.MONGO_URI) process.env.MONGO_URI = m[2]; }
const { MongoClient } = require("mongodb");
const { writeDumpOnce, stampedPath } = require("./lib_dump");
const [PROJECT, ROOT] = process.argv.slice(2);
if (!PROJECT || !ROOT || ROOT.startsWith("--")) { console.error("usage: node code_base_ghosts.js <project> <scripts_root> [--include=..] [--apply [--dump=f.ejson]]"); process.exit(2); }
const DUMP_ARG = (process.argv.find(a => a.startsWith("--dump=")) || "").slice(7);
const APPLY = process.argv.includes("--apply");
const INCLUDE = new Set(((process.argv.find(a => a.startsWith("--include=")) || "").slice(10)).split(",").filter(Boolean));
const all = [];
(function w(d) { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name); if (e.isDirectory()) w(p); else if (e.name.endsWith(".cs")) all.push(p); } })(ROOT);
const src = all.map(f => fs.readFileSync(f, "utf8"));
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
(async () => {
  const c = await MongoClient.connect(process.env.MONGO_URI); const col = c.db("aigame").collection("code_base");
  const docs = await col.find({ project: PROJECT }).toArray();
  const missing = [];
  for (const d of docs) {
    const rel = String(d.filePath || "").replace(/\\/g, "/");
    if (rel && fs.existsSync(path.join(ROOT, rel))) continue;
    const names = [...new Set([d.fileId, ...(d.classes || []).map(k => (k && (k.name || k.className)) || k).filter(x => typeof x === "string")])].filter(Boolean);
    const defined = names.map(n => { const re = new RegExp("\\b(class|struct|interface|enum|record)\\s+" + esc(n) + "\\b"); return { name: n, definedIn: all.filter((f, i) => re.test(src[i])).map(f => path.relative(ROOT, f).replace(/\\/g, "/")) }; });
    missing.push({ doc: d, rel, defined, ghost: defined.every(x => x.definedIn.length === 0) || INCLUDE.has(d.fileId) });
  }
  console.log(JSON.stringify({ project: PROJECT, disk_cs: all.length, docs: docs.length, filePath_missing: missing.length, confirmed_ghost: missing.filter(m => m.ghost).length }));
  for (const m of missing) console.log(`  ${m.ghost ? "GHOST" : "KEEP "} ${m.doc.fileId} | ${m.rel} | ${m.defined.map(x => x.name + "→" + (x.definedIn.join(",") || "없음")).join("; ")}`);
  const ghosts = missing.filter(m => m.ghost).map(m => m.doc);
  if (!APPLY) { console.log("dry-run: 아무것도 쓰지 않음 (삭제하려면 --apply)"); await c.close(); return; }
  if (!ghosts.length) { console.log("삭제할 문서 없음"); await c.close(); return; }
  const dump = writeDumpOnce(DUMP_ARG || stampedPath(path.join(__dirname, "deleted"), `code_base_ghosts_${PROJECT}`), ghosts);
  console.log("backup (EJSON canonical) ->", dump, ghosts.length);
  const r = await col.deleteMany({ project: PROJECT, _id: { $in: ghosts.map(d => d._id) } });
  console.log("deleted", r.deletedCount, "| project count now", await col.countDocuments({ project: PROJECT }));
  await c.close();
})().catch(e => { console.error(e.code === "EEXIST" ? `백업 파일이 이미 있음 — 덮어쓰지 않고 중단: ${e.path}` : e); process.exit(1); });
