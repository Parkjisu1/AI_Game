// art_assets 메타데이터 인덱서 (범용). 스키마는 2026-09-07 인라인 인덱서와 동일:
// {project, assetId=sha1("<project>|<path>")[:16], bytes, ext, kind, name, path(forward slash, 드라이브 포함), updatedAt}
// 2026-10-09 스크래치 art_index_generic.js 를 승격(2026-10-12). 동작 동일 + 델타/잔존 보고 추가.
//
// 사용: node scripts/embedding/art_index.js <project> <root1,root2,...> [옵션]
//   --exclude=Dir1,Dir2        폴더 이름(경로 아님) 제외. 기본 제외: Library .utmp obj Temp Logs .git
//   --manifest=out.jsonl       CLIP 매니페스트(이미지 전부) 출력
//   --delta-manifest=out.jsonl CLIP 매니페스트 중 이번에 신규/바이트 변경된 이미지만 출력
//   --missing-out=out.txt      Mongo 에는 있는데 디스크에 없는 문서 path 목록(삭제하지 않음)
//   --dry-run                  Mongo 에 쓰지 않음
// 주의: root 문자열은 기존 문서 path 접두와 대소문자까지 같아야 한다(assetId 가 path 해시).
//   예) Buddyflow 는 E:/Buddyflow/Buddyflow/Assets (소문자 f)
const fs = require("fs"), path = require("path"), crypto = require("crypto");
for (const l of fs.readFileSync(path.resolve(__dirname, "../../.env"), "utf8").split("\n")) { const m = l.trim().match(/^([A-Z_]+)=(.*)$/); if (m && !process.env[m[1]]) process.env[m[1]] = m[2]; }
const { MongoClient } = require("mongodb");
const [PROJECT, ROOTS] = process.argv.slice(2);
if (!PROJECT || !ROOTS || ROOTS.startsWith("--")) { console.error("usage: node art_index.js <project> <root1,root2,...> [--exclude=..] [--manifest=..] [--delta-manifest=..] [--missing-out=..] [--dry-run]"); process.exit(2); }
const opt = Object.fromEntries(process.argv.slice(4).filter(a => a.startsWith("--")).map(a => { const i = a.indexOf("="); return i < 0 ? [a.slice(2), true] : [a.slice(2, i), a.slice(i + 1)]; }));
const EXCLUDE = new Set(["Library", ".utmp", "obj", "Temp", "Logs", ".git", ...(opt.exclude ? opt.exclude.split(",") : [])]);
const KIND = { ".png": "sprite", ".jpg": "sprite", ".jpeg": "sprite", ".mat": "material", ".anim": "animation", ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
  ".shader": "shader", ".controller": "animator", ".overridecontroller": "animator", ".ttf": "font", ".otf": "font", ".spriteatlas": "atlas", ".spriteatlasv2": "atlas", ".tga": "texture", ".psd": "source_art" };
const IMAGE_KINDS = ["sprite", "texture", "source_art"];
const files = [];
for (const root of ROOTS.split(",")) {
  const R = root.replace(/\\/g, "/").replace(/\/$/, "");
  (function walk(d) { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = d + "/" + e.name; if (e.isDirectory()) { if (!EXCLUDE.has(e.name)) walk(p); } else { const ext = path.extname(e.name).toLowerCase(); if (KIND[ext]) files.push({ p, ext }); } } })(R);
}
(async () => {
  const c = await MongoClient.connect(process.env.MONGO_URI);
  const col = c.db("aigame").collection("art_assets");
  const existing = new Map((await col.find({ project: PROJECT }, { projection: { assetId: 1, bytes: 1, path: 1 } }).toArray()).map(d => [d.assetId, d]));
  let ins = 0, upd = 0, same = 0; const ops = []; const manifest = []; const delta = []; const seen = new Set();
  for (const { p, ext } of files) {
    const assetId = crypto.createHash("sha1").update(PROJECT + "|" + p).digest("hex").slice(0, 16);
    seen.add(assetId);
    const bytes = fs.statSync(p).size; const kind = KIND[ext]; const name = path.basename(p);
    const m = { project: PROJECT, path: p, name, kind };
    if (IMAGE_KINDS.includes(kind)) manifest.push(m);
    const ex = existing.get(assetId);
    if (ex && ex.bytes === bytes) { same++; continue; }
    if (ex) upd++; else ins++;
    if (IMAGE_KINDS.includes(kind)) delta.push(m);
    ops.push({ updateOne: { filter: { project: PROJECT, assetId }, update: { $set: { project: PROJECT, assetId, bytes, ext, kind, name, path: p, updatedAt: new Date() } }, upsert: true } });
  }
  // 이 root 들 밑에 있던 문서 중 디스크에 없는 것만 잔존으로 센다(다른 root 로 넣은 문서는 제외)
  const roots = ROOTS.split(",").map(r => r.replace(/\\/g, "/").replace(/\/$/, "") + "/");
  const gone = [...existing.values()].filter(d => !seen.has(d.assetId) && roots.some(r => (d.path || "").startsWith(r)));
  const kinds = {}; for (const f of files) kinds[KIND[f.ext]] = (kinds[KIND[f.ext]] || 0) + 1;
  console.log(JSON.stringify({ project: PROJECT, disk: files.length, kinds, existing: existing.size, same, update: upd, insert: ins, images_for_clip: manifest.length, images_delta: delta.length, missing_on_disk: gone.length, missing_sample: gone.slice(0, 5).map(d => d.path) }));
  const dump = (f, rows) => fs.writeFileSync(f, rows.map(m => JSON.stringify(m)).join("\n") + (rows.length ? "\n" : ""));
  if (opt.manifest) { dump(opt.manifest, manifest); console.log("manifest ->", opt.manifest); }
  if (opt["delta-manifest"]) { dump(opt["delta-manifest"], delta); console.log("delta manifest ->", opt["delta-manifest"], delta.length); }
  if (opt["missing-out"]) { fs.writeFileSync(opt["missing-out"], gone.map(d => d.path).join("\n") + (gone.length ? "\n" : "")); console.log("missing list ->", opt["missing-out"], gone.length); }
  if (!opt["dry-run"] && ops.length) { for (let i = 0; i < ops.length; i += 2000) await col.bulkWrite(ops.slice(i, i + 2000), { ordered: false }); }
  console.log("art_assets", PROJECT, "count now:", await col.countDocuments({ project: PROJECT }), opt["dry-run"] ? "(dry-run)" : "");
  await c.close();
})().catch(e => { console.error(e); process.exit(1); });
