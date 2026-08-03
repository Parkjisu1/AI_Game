/**
 * graph-query.js — 그래프 질의. 인접·k-hop·SCC·정합성 검사.
 *
 * 기존 SCC/QA 로직은 추출기(bf_graph_refresh.mjs)에 인라인돼 있어 재사용이 안 됐다.
 * 여기로 빼서 code_base 기반 그래프에도 같은 판정을 쓴다.
 *
 * 설계 계약: 실패해도 예외를 던지지 않고 빈 결과를 준다.
 *   (hermes 쪽 RAG 모듈들이 전부 "실패 시 빈 문자열" 계약을 지키므로 맞춘다)
 *
 * Usage:
 *   const { index, khop, impact, scc, orphans, pubsubMismatch } = require('./lib/graph-query');
 *   const idx = index(graph);
 *   const ctx = impact(idx, 'GameManager');
 */
'use strict';

const { NODE, EDGE, normalizeSymbol, nodeId } = require('./graph-model');

/** 인접 리스트 인덱스. 질의 전에 한 번 만든다. */
function index(graph) {
  const nodes = new Map();
  const out = new Map();   // id -> edge[]
  const inn = new Map();   // id -> edge[]
  for (const n of (graph && graph.nodes) || []) nodes.set(n.id, n);
  for (const e of (graph && graph.edges) || []) {
    if (!out.has(e.from)) out.set(e.from, []);
    if (!inn.has(e.to)) inn.set(e.to, []);
    out.get(e.from).push(e);
    inn.get(e.to).push(e);
  }
  return { nodes, out, inn };
}

/** 이름으로 노드 찾기 (타입 미지정이면 FILE 우선) */
function findNode(idx, name, type) {
  const nm = normalizeSymbol(name);
  if (!nm) return null;
  if (type) return idx.nodes.get(nodeId(type, nm)) || null;
  for (const t of [NODE.FILE, NODE.CLASS, NODE.EVENT, NODE.POOL_KEY, NODE.EXTERNAL]) {
    const hit = idx.nodes.get(nodeId(t, nm));
    if (hit) return hit;
  }
  return null;
}

/** 직접 이웃. dir: 'out' | 'in' | 'both' */
function neighbors(idx, id, dir = 'both', types = null) {
  const pick = (list) => (types ? list.filter((e) => types.includes(e.type)) : list);
  const res = [];
  if (dir === 'out' || dir === 'both') for (const e of pick(idx.out.get(id) || [])) res.push({ edge: e, node: idx.nodes.get(e.to), dir: 'out' });
  if (dir === 'in' || dir === 'both') for (const e of pick(idx.inn.get(id) || [])) res.push({ edge: e, node: idx.nodes.get(e.from), dir: 'in' });
  return res.filter((r) => r.node);
}

/**
 * k-hop 이웃. BFS.
 * @returns {{node, dist, dir}[]} seed 제외
 */
function khop(idx, id, depth = 1, dir = 'both', types = null) {
  if (!idx.nodes.has(id)) return [];
  const seen = new Set([id]);
  let frontier = [id];
  const out = [];
  for (let d = 1; d <= depth; d++) {
    const next = [];
    for (const cur of frontier) {
      for (const nb of neighbors(idx, cur, dir, types)) {
        if (seen.has(nb.node.id)) continue;
        seen.add(nb.node.id);
        out.push({ node: nb.node, dist: d, dir: nb.dir, edge: nb.edge });
        next.push(nb.node.id);
      }
    }
    frontier = next;
    if (!frontier.length) break;
  }
  return out;
}

/**
 * 영향범위 — "이걸 고치면 무엇이 깨지나".
 * 들어오는 엣지(호출자·구독자)를 우선으로 본다. RAG 프롬프트 주입용.
 */
function impact(idx, name, { depth = 1, limit = 12 } = {}) {
  const n = findNode(idx, name);
  if (!n) return { seed: null, callers: [], callees: [] };
  const callers = khop(idx, n.id, depth, 'in').slice(0, limit);
  const callees = khop(idx, n.id, depth, 'out').slice(0, limit);
  return { seed: n, callers, callees };
}

/** Tarjan SCC — 크기 2 이상인 그룹만 반환 (진짜 순환) */
function scc(idx) {
  const ids = [...idx.nodes.keys()];
  const idxMap = new Map(), low = new Map(), onStack = new Set();
  const stack = [];
  let counter = 0;
  const groups = [];

  const strongconnect = (v) => {
    // 재귀 대신 명시적 스택 — 노드가 많아지면 콜스택이 터진다
    const work = [[v, 0]];
    idxMap.set(v, counter); low.set(v, counter); counter++;
    stack.push(v); onStack.add(v);
    while (work.length) {
      const [node, pi] = work[work.length - 1];
      const es = idx.out.get(node) || [];
      if (pi < es.length) {
        work[work.length - 1][1] = pi + 1;
        const w = es[pi].to;
        if (!idxMap.has(w)) {
          idxMap.set(w, counter); low.set(w, counter); counter++;
          stack.push(w); onStack.add(w);
          work.push([w, 0]);
        } else if (onStack.has(w)) {
          low.set(node, Math.min(low.get(node), idxMap.get(w)));
        }
      } else {
        work.pop();
        if (work.length) {
          const parent = work[work.length - 1][0];
          low.set(parent, Math.min(low.get(parent), low.get(node)));
        }
        if (low.get(node) === idxMap.get(node)) {
          const grp = [];
          let w;
          do { w = stack.pop(); onStack.delete(w); grp.push(w); } while (w !== node);
          if (grp.length > 1) groups.push(grp);
        }
      }
    }
  };

  for (const v of ids) if (!idxMap.has(v)) strongconnect(v);
  return groups;
}

/** 고아 — 들어오지도 나가지도 않는 파일 노드 */
function orphans(idx) {
  const res = [];
  for (const n of idx.nodes.values()) {
    if (n.type !== NODE.FILE) continue;
    const o = (idx.out.get(n.id) || []).length;
    const i = (idx.inn.get(n.id) || []).length;
    if (o === 0 && i === 0) res.push(n);
  }
  return res;
}

/** 진입점 — 아무도 참조하지 않지만 나가는 참조는 있는 노드 */
function entries(idx) {
  const res = [];
  for (const n of idx.nodes.values()) {
    if (n.type !== NODE.FILE) continue;
    if ((idx.inn.get(n.id) || []).length === 0 && (idx.out.get(n.id) || []).length > 0) res.push(n);
  }
  return res;
}

/**
 * 이벤트 pub/sub 불일치 — ICS 양방향 검증을 실행 코드로.
 *   발행만 있고 구독 없음 → 아무도 안 듣는 이벤트
 *   구독만 있고 발행 없음 → 영원히 안 오는 이벤트
 */
function pubsubMismatch(idx) {
  const orphanPublish = [], orphanSubscribe = [];
  for (const n of idx.nodes.values()) {
    if (n.type !== NODE.EVENT) continue;
    const inc = idx.inn.get(n.id) || [];
    const pubs = inc.filter((e) => e.type === EDGE.PUBLISHES);
    const subs = inc.filter((e) => e.type === EDGE.SUBSCRIBES);
    if (pubs.length && !subs.length) {
      orphanPublish.push({ event: n.name, publishers: pubs.map((e) => idx.nodes.get(e.from)?.name).filter(Boolean) });
    }
    if (subs.length && !pubs.length) {
      orphanSubscribe.push({ event: n.name, subscribers: subs.map((e) => idx.nodes.get(e.from)?.name).filter(Boolean) });
    }
  }
  return { orphanPublish, orphanSubscribe };
}

/** 파서를 안 거쳐 관계가 비어 있는 파일 노드 — 그래프 신뢰도 지표 */
function unparsed(idx) {
  return [...idx.nodes.values()].filter((n) => n.type === NODE.FILE && n.parsed === false);
}

module.exports = {
  index, findNode, neighbors, khop, impact,
  scc, orphans, entries, pubsubMismatch, unparsed,
};
