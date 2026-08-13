#!/usr/bin/env node
/**
 * qa-feature-check.mjs — 기능 QA 판정기.
 *
 * 코드 그래프의 판정 단위는 파일/클래스였다. 그래서 "아이템 사용이 되는가" 를 물어볼
 * 대상이 없었고, QA 패널이 전부 초록이어도 게임이 도는지는 알 수 없었다.
 * 이 스크립트는 **기능**을 대상으로 세우고 3등급으로 판정한다.
 *
 *   ① 구조   graph.json 대조 — 진입점 메서드 실존 + 경로 인접쌍이 실제 참조 엣지인가.
 *            git push 마다 자동 재판정되므로 코드가 사라지면 즉시 빨강이 된다.
 *   ② 컴파일  Unity batchmode 결과(compile.json)의 에러 파일과 기능 파일의 교집합.
 *            결과 파일이 없으면 '미실행' — 통과로 위장하지 않는다.
 *   ③ 실행   실제 수행 관측(qa_feature_runs). 없으면 '미검증'.
 *            관측원: analytics 이벤트 로그 / bf_sim / PlayMode 테스트 등.
 *
 * 설계 원칙: **근거 없는 초록을 만들지 않는다.** 판정마다 evidence 문자열을 남기고,
 * 판정할 수 없으면 unknown 으로 둔다. 세 칸이 모두 초록일 때만 "된다"고 말한다.
 *
 * 사용:
 *   node qa-feature-check.mjs --project balloonflow
 *   node qa-feature-check.mjs --project balloonflow --verify-only   # 카탈로그 자체 점검
 *
 * 출력: <public>/<project>-features.json  (그래프 JSON 과 같은 자리 = 화면이 바로 읽음)
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

/**
 * .env 직접 로드.
 * `set -a; . .env` 로 cron 에서 넘기려 했더니 MONGODB_URI 의 쿼리스트링에 있는 `&` 를
 * sh 가 백그라운드 연산자로 읽어 값이 잘렸다(실측: "MONGODB_URI 필요"로 실패).
 * 셸에 맡기지 않고 key=value 로만 파싱한다.
 */
function loadEnvFile(p) {
  try {
    for (const line of fs.readFileSync(p, "utf8").split("\n")) {
      const s = line.trim();
      if (!s || s.startsWith("#")) continue;
      const i = s.indexOf("=");
      if (i <= 0) continue;
      const k = s.slice(0, i).trim();
      if (process.env[k]) continue; // 이미 있으면 덮지 않는다
      process.env[k] = s.slice(i + 1).trim().replace(/^["']|["']$/g, "");
    }
  } catch { /* 없으면 그냥 진행 */ }
}
loadEnvFile(process.env.HERMES_ENV_FILE || "/home/aimed/.hermes/watcher/.env");

function arg(name, def = null) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith("--") ? process.argv[i + 1] : def;
}
const has = (name) => process.argv.includes(`--${name}`);

const PROJECT = (arg("project", "balloonflow") || "").toLowerCase();
const PUBLIC_DIR = arg("public", process.env.NEWPLAY_GRAPH_PUBLIC || "/home/aimed/projecthub-web/public");
const CATALOG_DIR = arg("catalog", process.env.QA_FEATURE_DIR || path.join(HERE, "..", "qa", "features"));
const COMPILE_DIR = arg("compile", process.env.QA_COMPILE_DIR || "/home/aimed/.hermes/qa");

// ── YAML 로더: js-yaml 이 있으면 쓰고, 없으면 최소 파서로 폴백 ──────────────
// (Mother 에는 projecthub-web/node_modules/js-yaml 이 있다. 로컬 점검용으로 폴백을 둔다.)
async function loadYaml(text) {
  try {
    const mod = await import("js-yaml");
    return (mod.default || mod).load(text);
  } catch {
    return miniYaml(text);
  }
}

/** 이 카탈로그 형태(2단 리스트 + 인라인 map)만 다루는 최소 파서. 폴백 전용. */
function miniYaml(text) {
  const clean = text.split("\n").filter((l) => !/^\s*#/.test(l) && l.trim() !== "");
  const root = {};
  let features = null, cur = null, curKey = null;
  for (const raw of clean) {
    const line = raw.replace(/\s+#.*$/, "");
    const indent = line.match(/^ */)[0].length;
    const t = line.trim();
    if (indent === 0 && t.endsWith(":") && t === "features:") { features = []; root.features = features; cur = null; continue; }
    if (indent === 0 && /^[a-z_]+:/.test(t)) { const [k, ...v] = t.split(":"); root[k] = v.join(":").trim().replace(/^"|"$/g, ""); continue; }
    if (features && t.startsWith("- ")) { cur = {}; features.push(cur); parseKV(cur, t.slice(2)); curKey = null; continue; }
    if (!cur) continue;
    if (/^[a-z_]+:$/.test(t)) { curKey = t.slice(0, -1); cur[curKey] = {}; continue; }
    if (curKey && indent >= 6) { parseKV(cur[curKey], t); continue; }
    parseKV(cur, t);
  }
  return root;
}
function parseKV(obj, s) {
  const i = s.indexOf(":");
  if (i < 0) return;
  const k = s.slice(0, i).trim();
  let v = s.slice(i + 1).trim();
  if (!v) { obj[k] = {}; return; }
  if (v.startsWith("[")) obj[k] = v.slice(1, -1).split(",").map((x) => x.trim().replace(/^"|"$/g, "")).filter(Boolean);
  else if (v.startsWith("{")) {
    const o = {};
    for (const part of v.slice(1, -1).split(",")) { const j = part.indexOf(":"); if (j > 0) o[part.slice(0, j).trim()] = part.slice(j + 1).trim().replace(/^"|"$/g, ""); }
    obj[k] = o;
  } else obj[k] = v.replace(/^"|"$/g, "");
}

// ── 그래프 인덱스 ──────────────────────────────────────────────────────────
function indexGraph(g) {
  const byCls = new Map();
  for (const n of g.nodes || []) if (n.cls && !byCls.has(n.cls)) byCls.set(n.cls, n);
  const edge = new Set();
  for (const e of g.edges || []) edge.add(`${e.from}>${e.to}`);
  const edgeTyped = new Set();
  for (const e of g.edges || []) if (e.typed) edgeTyped.add(`${e.from}>${e.to}`);
  return { byCls, edge, edgeTyped };
}

/** ① 구조 판정 — 진입점 실존 + 경로 연결. 근거를 문장으로 남긴다. */
function checkStructure(f, ix) {
  const problems = [];
  const files = new Set();

  const [ecls, emeth] = String(f.entry || "").split(".");
  const enode = ix.byCls.get(ecls);
  if (!enode) problems.push(`진입점 클래스 ${ecls} 없음`);
  else {
    files.add(enode.id);
    if (emeth && !(enode.methods || []).includes(emeth)) problems.push(`${ecls}.${emeth} 메서드 없음 (클래스는 존재)`);
  }

  const links = [];
  const p = Array.isArray(f.path) ? f.path : [];
  for (const c of p) {
    const n = ix.byCls.get(c);
    if (!n) { problems.push(`경로 클래스 ${c} 없음`); continue; }
    files.add(n.id);
  }
  for (let i = 0; i + 1 < p.length; i++) {
    const a = ix.byCls.get(p[i]), b = ix.byCls.get(p[i + 1]);
    if (!a || !b) continue;
    const k = `${a.id}>${b.id}`;
    const ok = ix.edge.has(k);
    links.push({ from: p[i], to: p[i + 1], ok, typed: ix.edgeTyped.has(k) });
    if (!ok) problems.push(`경로 끊김: ${p[i]} → ${p[i + 1]} 참조 없음`);
  }

  const verdict = problems.length === 0 ? "pass" : "fail";
  const typedN = links.filter((l) => l.typed).length;
  const evidence = verdict === "pass"
    ? `진입점 ${f.entry} 실존 · 경로 ${links.length}구간 전부 연결${links.length ? ` (타입 검증 ${typedN}/${links.length})` : ""}`
    : problems.join(" · ");
  return { verdict, evidence, links, files: [...files], problems };
}

/**
 * ② 컴파일 판정 — batchmode 결과가 있을 때만. 없으면 미실행(unknown).
 *
 * 결과가 **그래프와 같은 커밋**의 것인지 반드시 대조한다. CI 클론이 다른 커밋을 컴파일해
 * 통과를 반환한 적이 있다(그래프 54df2a1b vs 컴파일 09549c1a). 다른 코드의 통과는
 * 이 코드의 통과가 아니므로 unknown 으로 떨어뜨린다.
 */
function checkCompile(structFiles, compile, graphSha) {
  if (!compile) return { verdict: "unknown", evidence: "컴파일 결과 없음 — Unity batchmode 미실행" };
  const cSha = String(compile.sha || "");
  if (graphSha && cSha && !graphSha.startsWith(cSha) && !cSha.startsWith(graphSha)) {
    return { verdict: "unknown", evidence: `컴파일 결과가 다른 커밋 기준 (컴파일 ${cSha} ≠ 그래프 ${graphSha}) — 이 코드에 대한 판정이 아님` };
  }
  const errs = (compile.errors || []).filter((e) => structFiles.some((f) => (e.file || "").replace(/\\/g, "/").endsWith(f)));
  if (errs.length) {
    return { verdict: "fail", evidence: `이 기능이 걸친 파일에 컴파일 에러 ${errs.length}건: ${errs.slice(0, 2).map((e) => `${e.file}:${e.line} ${e.code}`).join(" / ")}`, errors: errs.slice(0, 8) };
  }
  const when = compile.finishedAt ? ` (${String(compile.finishedAt).slice(0, 16)})` : "";
  if (compile.ok === false) return { verdict: "unknown", evidence: `빌드 자체가 실패해 파일별 판정 불가${when}` };
  return { verdict: "pass", evidence: `컴파일 통과 — 이 기능 파일 ${structFiles.length}개에 에러 없음${when}` };
}

/**
 * ③ 실행 판정 — 관측 레코드가 있을 때만. 없으면 미검증(unknown).
 *
 * 관측에는 등급이 있다. 이걸 뭉개면 이 패널을 만든 이유가 사라진다:
 *   direct — 실제 게임 빌드가 그 기능을 수행한 관측(analytics 이벤트 로그, PlayMode 테스트).
 *            이것만 'pass'(= "된다")로 인정한다.
 *   proxy  — 게임 코드가 아닌 대리물의 관측(BalloonFlowSim 은 재구현 시뮬레이터다).
 *            로직이 성립함을 시사할 뿐 Unity 코드가 돈다는 증거가 아니므로 'proxy' 로 따로 둔다.
 */
function checkRuntime(f, runs) {
  const mine = (runs || []).filter((r) => r.featureId === f.id);
  if (!mine.length) {
    const wants = [
      ...((f.signals?.analytics) || []).map((a) => `analytics:${a}`),
      ...(f.signals?.sim ? [`sim:${f.signals.sim.metric}`] : []),
    ];
    return { verdict: "unknown", evidence: wants.length ? `실행 관측 없음 — 기대 신호: ${wants.join(", ")}` : "실행 관측 없음 — 관측 신호 미정의" };
  }
  mine.sort((a, b) => String(b.observedAt || "").localeCompare(String(a.observedAt || "")));
  // 직접 관측이 하나라도 있으면 그것을 쓴다. 대리 관측이 직접 관측을 가려선 안 된다.
  const last = mine.find((r) => r.confidence !== "proxy") || mine[0];
  const proxy = last.confidence === "proxy";
  const verdict = last.ok === true ? (proxy ? "proxy" : "pass") : last.ok === false ? "fail" : "unknown";
  const tag = proxy ? " ⚠대리관측(실기 아님)" : "";
  return {
    verdict,
    evidence: `${last.source || "?"} 관측 ${String(last.observedAt || "").slice(0, 16)} — ${last.detail || (last.ok ? "수행 확인" : "수행 안 됨")}${tag}`,
    source: last.source,
    confidence: last.confidence || "direct",
    observedAt: last.observedAt,
  };
}

/**
 * 기능 최종 판정.
 * 하나라도 fail 이면 fail. 세 칸이 전부 direct pass 여야만 pass(= "된다").
 * 그 외는 unknown — 여기서 관대해지면 패널이 다시 벽지가 된다.
 */
function overall(t) {
  const v = [t.structure.verdict, t.compile.verdict, t.runtime.verdict];
  if (v.includes("fail")) return "fail";
  return v.every((x) => x === "pass") ? "pass" : "unknown";
}

async function main() {
  const catalogPath = path.join(CATALOG_DIR, `${PROJECT}.yaml`);
  if (!fs.existsSync(catalogPath)) {
    console.log(JSON.stringify({ skipped: true, reason: `카탈로그 없음: ${catalogPath}` }));
    return;
  }
  const cat = await loadYaml(fs.readFileSync(catalogPath, "utf8"));
  const feats = cat.features || [];

  const graphPath = path.join(PUBLIC_DIR, `${PROJECT}-graph.json`);
  if (!fs.existsSync(graphPath)) throw new Error(`그래프 없음: ${graphPath}`);
  const graph = JSON.parse(fs.readFileSync(graphPath, "utf8"));
  const ix = indexGraph(graph);

  // 컴파일 결과 (있으면)
  let compile = null;
  const cPath = path.join(COMPILE_DIR, `${PROJECT}-compile.json`);
  if (fs.existsSync(cPath)) { try { compile = JSON.parse(fs.readFileSync(cPath, "utf8")); } catch { /* 손상 시 무시 */ } }

  // 실행 관측 (Mongo qa_feature_runs) — 없으면 빈 배열로 계속 간다(비치명).
  let runs = [];
  if (!has("no-db")) {
    try {
      const { MongoClient } = await import("mongodb");
      const uri = process.env.MONGODB_URI;
      if (uri) {
        const cli = new MongoClient(uri, { serverSelectionTimeoutMS: 10000 });
        await cli.connect();
        runs = await cli.db(process.env.MONGODB_DB || "aigame").collection("qa_feature_runs")
          .find({ project: PROJECT }).sort({ observedAt: -1 }).limit(500).toArray();
        await cli.close();
      }
    } catch (e) { console.error("qa_feature_runs 조회 실패(비치명):", e.message); }
  }

  // generatedFrom 예: "origin/main @54df2a1b (BalloonFlow)" — 컴파일 결과와 대조할 커밋.
  const graphSha = (String(graph.generatedFrom || "").match(/@([0-9a-f]{7,40})/) || [])[1] || "";

  const results = feats.map((f) => {
    const structure = checkStructure(f, ix);
    const compileV = checkCompile(structure.files, compile, graphSha);
    const runtime = checkRuntime(f, runs);
    const t = { structure, compile: compileV, runtime };
    return {
      id: f.id, name: f.name, group: f.group || "기타", severity: f.severity || "major",
      entry: f.entry, path: f.path || [], why: f.why || "", signals: f.signals || {},
      files: structure.files, links: structure.links,
      tiers: t, verdict: overall(t),
    };
  });

  const count = (k, v) => results.filter((r) => r.tiers[k].verdict === v).length;
  const out = {
    project: PROJECT,
    generatedFrom: graph.generatedFrom || "",
    checkedAt: new Date().toISOString(),
    catalogVersion: cat.version || 1,
    summary: {
      total: results.length,
      structure: { pass: count("structure", "pass"), fail: count("structure", "fail"), unknown: count("structure", "unknown") },
      compile: { pass: count("compile", "pass"), fail: count("compile", "fail"), unknown: count("compile", "unknown") },
      runtime: { pass: count("runtime", "pass"), proxy: count("runtime", "proxy"), fail: count("runtime", "fail"), unknown: count("runtime", "unknown") },
      verdict: { pass: results.filter((r) => r.verdict === "pass").length, fail: results.filter((r) => r.verdict === "fail").length, unknown: results.filter((r) => r.verdict === "unknown").length },
      compileSource: compile ? (compile.finishedAt || "있음") : null,
      runsSeen: runs.length,
    },
    features: results,
  };

  if (has("verify-only")) {
    for (const r of results) {
      const s = r.tiers.structure;
      console.log(`${s.verdict === "pass" ? "OK  " : "FAIL"} ${r.id.padEnd(24)} ${s.evidence}`);
    }
    console.log(`\n구조 판정: pass ${out.summary.structure.pass} / fail ${out.summary.structure.fail}`);
    return;
  }

  const outPath = path.join(PUBLIC_DIR, `${PROJECT}-features.json`);
  fs.writeFileSync(outPath, JSON.stringify(out));
  console.log(JSON.stringify({
    wrote: outPath, total: out.summary.total,
    structure: out.summary.structure, compile: out.summary.compile, runtime: out.summary.runtime,
  }));
}

main().catch((e) => { console.error("qa-feature-check 실패:", e.message); process.exit(1); });
