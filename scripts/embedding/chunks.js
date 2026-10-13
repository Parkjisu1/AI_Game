// 원문 .cs → chunks JSONL (raw_to_jsonl 규약: 24000자 비중첩). path 는 <base> 기준 상대경로('/').
// 2026-10-09 스크래치 chunks_generic.js 를 승격(2026-10-12). 동작 동일.
// 출력은 임베딩컴 host/qdrant_delta.py 의 입력(scp 후 실행).
// 사용: node scripts/embedding/chunks.js <project> <base> <dir1,dir2,...(base 기준 상대)> <out.jsonl> [--only=<paths.txt>]
//   *.local.cs 와 시크릿 패턴이 든 파일은 건너뛴다(skipped 로 보고).
//   --only: base 기준 상대 path 목록(한 줄 하나)에 든 파일만 출력(조각 누락 보수 등 부분 실행용, 2026-10-13).
//           부분 JSONL 로 qdrant_delta 를 돌리면 나머지 path 는 missing_on_disk 로 "보고만" 된다(--delete-missing 금지).
const fs = require("fs"), path = require("path"), crypto = require("crypto");
const [PROJECT, BASE, DIRS, OUT] = process.argv.slice(2);
if (!PROJECT || !BASE || !DIRS || !OUT || OUT.startsWith("--")) { console.error("usage: node chunks.js <project> <base> <dir1,dir2,...> <out.jsonl> [--only=paths.txt]"); process.exit(2); }
const ONLY_ARG = process.argv.find(a => a.startsWith("--only="));
const ONLY = ONLY_ARG ? new Set(fs.readFileSync(ONLY_ARG.slice(7), "utf8").split(/\r?\n/).map(s => s.trim()).filter(Boolean)) : null;
const CHUNK = 24000;
const SECRET = /(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|xox[abp]-|mongodb\+srv:\/\/|PRIVATE KEY)/;
const EXCL = new Set(["Library", "obj", "Temp", "Logs", ".git"]);
const files = [];
for (const d of DIRS.split(",")) {
  const root = path.join(BASE, d);
  (function walk(dd) { for (const e of fs.readdirSync(dd, { withFileTypes: true })) { const p = path.join(dd, e.name); if (e.isDirectory()) { if (!EXCL.has(e.name)) walk(p); } else if (e.name.endsWith(".cs")) files.push(p); } })(root);
}
files.sort();
const out = fs.createWriteStream(OUT); let n = 0, nf = 0; const skipped = [];
for (const f of files) {
  const rel = path.relative(BASE, f).replace(/\\/g, "/");
  if (ONLY && !ONLY.has(rel)) continue;
  if (/\.local\.cs$/i.test(rel)) { skipped.push(rel); continue; }
  const content = fs.readFileSync(f, "utf8");
  if (SECRET.test(content)) { skipped.push(rel + " (secret pattern)"); continue; }
  nf++;
  const fileSha = crypto.createHash("sha256").update(content, "utf8").digest("hex");
  const nChunks = Math.max(1, Math.ceil(content.length / CHUNK));
  for (let i = 0; i < nChunks; i++) { out.write(JSON.stringify({ project: PROJECT, path: rel, chunkIndex: i, nChunks, fileSha, lang: "csharp", content: content.slice(i * CHUNK, (i + 1) * CHUNK) }) + "\n"); n++; }
}
out.end(() => console.log(JSON.stringify({ project: PROJECT, files: ONLY ? nf : files.length, chunks: n, skipped, ...(ONLY ? { only_listed: ONLY.size, only_found: nf } : {}) })));
