#!/usr/bin/env node
/**
 * enrich-code-graph.js — 기존 코드 그래프 JSON에 "엣지 타입"을 덧붙인다.
 *
 * 배경:
 *   bf_graph_refresh.mjs 가 만드는 그래프는 "파일 본문에 다른 파일의 클래스명이 보이면 엣지"라
 *   엣지에 타입이 없다. 문자열 리터럴 우연일치까지 엣지가 되어
 *   169노드 중 96개(57%)가 순환 판정 — 사실상 신호가 없다.
 *
 *   반면 code_base.integration 에는 타입이 있는 관계가 이미 적재돼 있다
 *   (호출 316 / 구독 27 / 발행 19 / 풀 9 / 로드 55 · 2026-08-03 실측).
 *   두 자산을 클래스명으로 조인해(실측 커버리지 96%) 기존 엣지에 타입을 부여한다.
 *
 * 설계 원칙 — 스키마를 깨지 않는다:
 *   소비자가 3곳(bf_graph_context.py 그라운딩 / balloonflow 화면 / voice 질의 인덱스)이라
 *   기존 필드는 그대로 두고 **필드를 추가만** 한다.
 *     edges[].type      추가  (calls|subscribes|publishes|pool_get|loads|instantiates|wires|uses|unknown)
 *     edges[].typed     추가  (타입이 확정됐는가)
 *     nodes[].qaTyped   추가  (타입드 엣지만으로 다시 계산한 QA — 기존 qa 는 보존)
 *     typedStats        추가  (최상위 요약)
 *
 * Usage:
 *   node scripts/enrich-code-graph.js --graph <path> [--project BalloonFlow] [--dry]
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { buildGraph } = require('./lib/graph-build');
const Q = require('./lib/graph-query');
const { NODE } = require('./lib/graph-model');

function loadEnv() {
  const envUri = process.env.MONGO_URI || process.env.MONGODB_URI;
  if (envUri) return { uri: envUri, db: process.env.MONGO_DB_NAME || process.env.MONGODB_DB || 'aigame' };
  const candidates = [
    path.resolve(__dirname, '../.env'),
    path.resolve(__dirname, '.env'),
    path.join(process.env.HOME || '', '.hermes/watcher/.env'),
  ];
  for (const p of candidates) {
    try {
      if (!p || !fs.existsSync(p)) continue;
      const txt = fs.readFileSync(p, 'utf8');
      const get = (k) => {
        const m = txt.match(new RegExp('^' + k + '=(.*)$', 'm'));
        return m ? m[1].trim().replace(/^["']|["']$/g, '') : null;
      };
      const uri = get('MONGO_URI') || get('MONGODB_URI');
      if (uri) return { uri, db: get('MONGO_DB_NAME') || get('MONGODB_DB') || 'aigame' };
    } catch { /* 다음 후보 */ }
  }
  throw new Error('MONGO_URI 를 찾지 못했습니다');
}

const args = process.argv.slice(2);
const DRY = args.includes('--dry');
const argOf = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : d; };
// 그래프 경로 — 로컬(E:\AI)과 Mother(~/projecthub-web) 양쪽에서 인자 없이 돌아야 한다.
function defaultGraphPath() {
  const candidates = [
    path.resolve(__dirname, '../tools/projecthub-web/public/balloonflow-graph.json'), // 로컬 레포
    path.join(process.env.HOME || '', 'projecthub-web/public/balloonflow-graph.json'), // Mother
  ];
  return candidates.find((p) => p && fs.existsSync(p)) || candidates[0];
}
const GRAPH_PATH = argOf('--graph', defaultGraphPath());
const PROJECT = argOf('--project', 'BalloonFlow');

async function main() {
  if (!fs.existsSync(GRAPH_PATH)) throw new Error('그래프 파일 없음: ' + GRAPH_PATH);
  const graph = JSON.parse(fs.readFileSync(GRAPH_PATH, 'utf8'));
  const nodes = graph.nodes || [];
  const edges = graph.edges || [];

  const { uri, db } = loadEnv();
  const { MongoClient } = require('mongodb');
  const client = new MongoClient(uri, { serverSelectionTimeoutMS: 30000 });
  await client.connect();
  const docs = await client.db(db).collection('code_base')
    .find({ project: PROJECT }).project({ embedding: 0, text: 0, content: 0 }).toArray();
  await client.close();

  // 타입드 그래프 (클래스명 기준)
  const typed = buildGraph(docs, { project: PROJECT });

  // 클래스명 → 그래프 노드 id
  const clsToId = new Map();
  for (const n of nodes) if (n.cls) clsToId.set(String(n.cls).trim(), n.id);

  // (fromId|toId) → 타입 목록
  const typeMap = new Map();
  for (const e of typed.edges) {
    const fromNode = typed.nodes.find((n) => n.id === e.from);
    const toNode = typed.nodes.find((n) => n.id === e.to);
    if (!fromNode || !toNode) continue;
    if (fromNode.type !== NODE.FILE || toNode.type !== NODE.FILE) continue; // 파일-파일 엣지만 기존 그래프와 대응
    const a = clsToId.get(fromNode.name), b = clsToId.get(toNode.name);
    if (!a || !b) continue;
    const key = a + '|' + b;
    if (!typeMap.has(key)) typeMap.set(key, new Set());
    typeMap.get(key).add(e.type);
  }

  // 엣지에 타입 부여 — 우선순위: 구체적인 타입 > uses
  const RANK = ['calls', 'subscribes', 'publishes', 'pool_get', 'pool_return', 'loads', 'instantiates', 'wires', 'uses'];
  let typedCount = 0;
  for (const e of edges) {
    const set = typeMap.get(e.from + '|' + e.to);
    if (!set || !set.size) { e.type = 'unknown'; e.typed = false; continue; }
    const best = RANK.find((t) => set.has(t)) || [...set][0];
    e.type = best;
    e.typed = true;
    typedCount++;
  }

  // 타입드 엣지만으로 QA 재계산 — 기존 qa 는 건드리지 않는다
  const sub = {
    nodes: nodes.map((n) => ({ id: n.id, type: NODE.FILE, name: n.cls || n.id })),
    edges: edges.filter((e) => e.typed).map((e) => ({ id: e.from + '|' + e.type + '|' + e.to, from: e.from, to: e.to, type: e.type, weight: e.n || 1 })),
  };
  const idx = Q.index(sub);
  const cyc = Q.scc(idx);
  const inCycle = new Set(cyc.flat());
  const orphanIds = new Set(Q.orphans(idx).map((n) => n.id));
  const entryIds = new Set(Q.entries(idx).map((n) => n.id));
  for (const n of nodes) {
    n.qaTyped = inCycle.has(n.id) ? 'cycle' : orphanIds.has(n.id) ? 'orphan' : entryIds.has(n.id) ? 'entry' : 'ok';
  }

  const byType = edges.reduce((a, e) => (a[e.type] = (a[e.type] || 0) + 1, a), {});
  const qaOld = nodes.reduce((a, n) => (a[n.qa] = (a[n.qa] || 0) + 1, a), {});
  const qaNew = nodes.reduce((a, n) => (a[n.qaTyped] = (a[n.qaTyped] || 0) + 1, a), {});

  // 계약 섹션 — 이벤트 pub/sub 와 풀 키는 파일-파일 엣지가 아니라서
  // 기존 edges 배열에 안 실린다. ICS(_CONTRACTS.yaml)와 같은 모양으로 따로 담는다.
  // 이게 "발행만 있고 아무도 안 듣는 이벤트" 같은 통합 결함을 잡는 실제 신호다.
  const tIdx = Q.index(typed);
  const nameOf = (id) => (typed.nodes.find((n) => n.id === id) || {}).name || null;
  const events = [];
  for (const n of typed.nodes) {
    if (n.type !== NODE.EVENT) continue;
    const inc = tIdx.inn.get(n.id) || [];
    events.push({
      name: n.name,
      publishers: inc.filter((e) => e.type === 'publishes').map((e) => nameOf(e.from)).filter(Boolean),
      subscribers: inc.filter((e) => e.type === 'subscribes').map((e) => nameOf(e.from)).filter(Boolean),
    });
  }
  const poolKeys = [];
  for (const n of typed.nodes) {
    if (n.type !== NODE.POOL_KEY) continue;
    const inc = tIdx.inn.get(n.id) || [];
    poolKeys.push({
      key: n.name,
      consumers: [...new Set(inc.map((e) => nameOf(e.from)).filter(Boolean))],
    });
  }
  const mm = Q.pubsubMismatch(tIdx);
  graph.contracts = {
    events,
    poolKeys,
    mismatches: {
      publishWithoutSubscribe: mm.orphanPublish,
      subscribeWithoutPublish: mm.orphanSubscribe,
    },
  };

  graph.typedStats = {
    enrichedAt: new Date().toISOString(),
    project: PROJECT,
    codeBaseDocs: docs.length,
    edgesTotal: edges.length,
    edgesTyped: typedCount,
    typedRatio: edges.length ? +(typedCount / edges.length).toFixed(3) : 0,
    edgesByType: byType,
    cycleGroupsTyped: cyc.length,
  };

  console.log(`그래프: ${GRAPH_PATH}`);
  console.log(`code_base ${PROJECT} ${docs.length}건 → 타입드 엣지 ${typed.stats.edges}개`);
  console.log(`기존 엣지 ${edges.length}개 중 타입 부여 ${typedCount}개 (${(typedCount / edges.length * 100).toFixed(0)}%)`);
  console.log('엣지 타입 분포:', JSON.stringify(byType));
  console.log('QA  기존:', JSON.stringify(qaOld));
  console.log('QA 타입드:', JSON.stringify(qaNew), `— 순환 그룹 ${cyc.length}개`);

  if (DRY) { console.log('\n[예행] 파일을 쓰지 않았습니다.'); return; }

  const bak = GRAPH_PATH + '.bak';
  if (!fs.existsSync(bak)) fs.copyFileSync(GRAPH_PATH, bak);
  fs.writeFileSync(GRAPH_PATH, JSON.stringify(graph));
  console.log(`\n반영 완료 (원본 백업: ${path.basename(bak)})`);
}

main().catch((e) => { console.error('ERR ' + e.message); process.exit(1); });
