// BalloonFlow 코드 그래프 추출 + 직전 스냅샷 대비 회귀(diff) 검출.
// 사용: node bf_graph_refresh.mjs <srcDir(.../1.Scripts)> <prevJson> <outJson> <genfrom>
// stdout에 회귀 요약 JSON 출력: {removedFiles:[], removedMethods:[{file,gone:[]}], counts:{...}}
import fs from "fs";
import path from "path";

const ROOT = process.argv[2];
const PREV = process.argv[3];
const OUT = process.argv[4];
const GENFROM = process.argv[5] || "origin/main";
const D = "|##|";

function walk(dir) {
  const out = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p));
    else if (e.name.endsWith(".cs")) out.push(p);
  }
  return out;
}
function stripComments(s) { return s.replace(/\/\*[\s\S]*?\*\//g, " ").replace(/\/\/[^\n]*/g, " "); }

const files = walk(ROOT);
const recs = [];
for (const f of files) {
  const raw = fs.readFileSync(f, "utf8");
  const rel = f.replace(/\\/g, "/").split("/1.Scripts/")[1];
  const parts = rel.split("/");
  const system = parts.length > 1 ? parts[0] : "(root)";
  const text = stripComments(raw);
  const classes = [];
  const re = /\b(?:public|internal|private|protected|sealed|abstract|static|partial|\s)*\b(class|struct|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)/g;
  let m; while ((m = re.exec(text))) classes.push(m[2]);
  const uniq = [...new Set(classes)];
  const methods = [];
  const mre = /\b(?:public|private|protected|internal)\b[^\n;{}]*?\b([A-Za-z_]\w*)\s*\([^;{)]*\)\s*(?:\{|=>)/g;
  const skip = new Set(["if", "for", "while", "switch", "catch", "foreach", "lock", "using", "return", "get", "set"]);
  let mm; while ((mm = mre.exec(text))) { const nm = mm[1]; if (!skip.has(nm) && !uniq.includes(nm)) methods.push(nm); }
  const base = path.basename(f, ".cs");
  const primary = uniq.includes(base) ? base : (uniq[0] || base);
  recs.push({ rel, system, classes: uniq, methods: [...new Set(methods)], primary, loc: raw.split("\n").length, text });
}

const classToFile = new Map();
for (const r of recs) for (const c of r.classes) if (!classToFile.has(c)) classToFile.set(c, r.rel);
const allClasses = [...classToFile.keys()].filter((c) => c.length >= 3);
const edgeSet = new Set();
for (const r of recs) for (const c of allClasses) {
  if (r.classes.includes(c)) continue;
  const target = classToFile.get(c);
  if (target === r.rel) continue;
  if (new RegExp(`\\b${c}\\b`).test(r.text)) edgeSet.add(`${r.rel}${D}${target}${D}${c}`);
}
const fileEdges = new Map();
for (const e of edgeSet) { const [from, to, c] = e.split(D); const k = `${from}${D}${to}`; if (!fileEdges.has(k)) fileEdges.set(k, new Set()); fileEdges.get(k).add(c); }
const nodes = recs.map((r) => ({ id: r.rel, file: r.rel.split("/").pop(), system: r.system, cls: r.primary, classes: r.classes, methods: r.methods, loc: r.loc }));
const edges = [...fileEdges.entries()].map(([k, set]) => { const [from, to] = k.split(D); return { from, to, via: [...set].slice(0, 6), n: set.size }; });
const outC = {}, inC = {};
for (const e of edges) { outC[e.from] = (outC[e.from] || 0) + 1; inC[e.to] = (inC[e.to] || 0) + 1; }
for (const n of nodes) { n.refsOut = outC[n.id] || 0; n.refsIn = inC[n.id] || 0; }

// SCC (Tarjan) for cycle QA
const idx = {}; nodes.forEach((n, i) => (idx[n.id] = i));
const adj = nodes.map(() => []);
for (const e of edges) if (idx[e.from] != null && idx[e.to] != null) adj[idx[e.from]].push(idx[e.to]);
const N = nodes.length; let counter = 0;
const num = new Array(N).fill(-1), low = new Array(N).fill(-1), onstk = new Array(N).fill(false), stk = [], sccs = [];
function sc(u) { num[u] = low[u] = counter++; stk.push(u); onstk[u] = true; for (const v of adj[u]) { if (num[v] === -1) { sc(v); low[u] = Math.min(low[u], low[v]); } else if (onstk[v]) low[u] = Math.min(low[u], num[v]); } if (low[u] === num[u]) { const comp = []; let w; do { w = stk.pop(); onstk[w] = false; comp.push(w); } while (w !== u); sccs.push(comp); } }
for (let i = 0; i < N; i++) if (num[i] === -1) sc(i);
const cycleGroups = sccs.filter((c) => c.length > 1).map((c) => c.map((i) => nodes[i].id));
const inCycle = new Set(cycleGroups.flat());
for (const n of nodes) { n.qa = (n.refsIn === 0 && n.refsOut === 0) ? "orphan" : inCycle.has(n.id) ? "cycle" : (n.refsIn === 0 ? "entry" : "ok"); }
const sysMap = {}; for (const n of nodes) { sysMap[n.system] = sysMap[n.system] || { name: n.system, count: 0, loc: 0 }; sysMap[n.system].count++; sysMap[n.system].loc += n.loc; }
const fileSys = Object.fromEntries(nodes.map((n) => [n.id, n.system]));
const sysEdge = {}; for (const e of edges) { const a = fileSys[e.from], b = fileSys[e.to]; if (a === b) continue; const k = `${a}${D}${b}`; sysEdge[k] = (sysEdge[k] || 0) + 1; }
const systems = Object.values(sysMap).sort((x, y) => y.count - x.count);
const systemEdges = Object.entries(sysEdge).map(([k, w]) => { const [from, to] = k.split(D); return { from, to, weight: w }; });
const qa = { total: nodes.length, ok: nodes.filter((n) => n.qa === "ok").length, orphan: nodes.filter((n) => n.qa === "orphan").length, cycle: inCycle.size, entry: nodes.filter((n) => n.qa === "entry").length, cycleGroups: cycleGroups.slice(0, 30) };
const graph = { generatedFrom: GENFROM, nodes, edges, systems, systemEdges, qa };
fs.writeFileSync(OUT, JSON.stringify(graph));

// ── 회귀 diff vs 직전 스냅샷 ──
let removedFiles = [], removedMethods = [];
try {
  if (PREV && fs.existsSync(PREV)) {
    const prev = JSON.parse(fs.readFileSync(PREV, "utf8"));
    const newIds = new Set(nodes.map((n) => n.id));
    const newById = Object.fromEntries(nodes.map((n) => [n.id, n]));
    for (const pn of prev.nodes || []) {
      if (!newIds.has(pn.id)) { removedFiles.push(pn.cls + " (" + pn.id + ")"); continue; }
      const pm = new Set(pn.methods || []);
      const nm = new Set(newById[pn.id].methods || []);
      const gone = [...pm].filter((x) => !nm.has(x));
      if (gone.length) removedMethods.push({ file: pn.cls, gone });
    }
  }
} catch (e) { /* prev parse 실패 시 diff 생략 */ }

console.log(JSON.stringify({ removedFiles, removedMethods, counts: { nodes: nodes.length, methods: nodes.reduce((a, n) => a + (n.methods ? n.methods.length : 0), 0) } }));
