// CLIP 델타 대상 계산 (2026-10-12).
// 사용: node scripts/embedding/manifest_todo.js <full_manifest.jsonl> <delta_manifest.jsonl> <vector_paths.txt> <out_todo.jsonl> [--stale-out=<file>]
//   todo  = delta(신규·바이트 변경) ∪ (full 중 art_vectors 에 path 가 없는 것)
//   stale = art_vectors 에는 있는데 full manifest(디스크)에 없는 path → 목록만 기록, 삭제는 사람이 결정
//   vector_paths.txt 는 임베딩컴 `python3 ~/kb_qdrant.py paths art_vectors <project>` 출력
const fs = require("fs");
const [FULL, DELTA, VPATHS, OUT] = process.argv.slice(2);
if (!OUT) { console.error("usage: node manifest_todo.js <full> <delta> <vector_paths.txt> <out> [--stale-out=f]"); process.exit(2); }
const staleOut = (process.argv.find(a => a.startsWith("--stale-out=")) || "").split("=").slice(1).join("=");
const read = f => fs.readFileSync(f, "utf8").split("\n").filter(l => l.trim()).map(l => JSON.parse(l));
const full = read(FULL), delta = read(DELTA);
const vp = new Set(fs.readFileSync(VPATHS, "utf8").split(/\r?\n/).filter(Boolean));
const todo = new Map();
for (const m of delta) todo.set(m.path, m);
let missingVec = 0;
for (const m of full) if (!vp.has(m.path) && !todo.has(m.path)) { todo.set(m.path, m); missingVec++; }
const disk = new Set(full.map(m => m.path));
const stale = [...vp].filter(p => !disk.has(p));
fs.writeFileSync(OUT, [...todo.values()].map(m => JSON.stringify(m)).join("\n") + (todo.size ? "\n" : ""));
if (staleOut) fs.writeFileSync(staleOut, stale.join("\n") + (stale.length ? "\n" : ""));
console.log(JSON.stringify({ full: full.length, vectors: vp.size, delta: delta.length, missing_vector: missingVec, todo: todo.size, stale_vectors: stale.length, stale_sample: stale.slice(0, 5) }));
