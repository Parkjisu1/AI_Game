/**
 * graph-build.js — code_base 문서 배열 → 타입드 그래프 {nodes, edges}
 *
 * 입력은 code_base doc 그대로. 이미 적재된 관계 필드를 엣지로 승격한다:
 *   integration.singleton_access[{target,method}] → CALLS
 *   integration.event_publish[]                  → PUBLISHES  (파일 → 이벤트)
 *   integration.event_subscribe[{event,handler}] → SUBSCRIBES (파일 → 이벤트)
 *   integration.pool_usage[{action,type}]        → POOL_GET / POOL_RETURN
 *   integration.resource_load / addressable_load → LOADS
 *   integration.instantiate_calls                → INSTANTIATES
 *   unity_config.serialized_fields[]             → WIRES
 *   uses[] / requires[]                          → USES (타입 미상 폴백)
 *
 * 해결 안 되는 참조는 버리지 않고 EXTERNAL 노드로 보낸다.
 * 실측상 requires 고유값의 66%가 Unity 내장 타입이라, 버리면 "왜 안 이어지는지"를 못 본다.
 *
 * Usage:
 *   const { buildGraph } = require('./lib/graph-build');
 *   const g = buildGraph(docs, { project: 'BalloonFlow' });
 */
'use strict';

const {
  NODE, EDGE, normalizeSymbol, isNoise, isExternal, isLikelyEvent, nodeId, edgeId,
} = require('./graph-model');

/** doc에서 파일/클래스 식별자를 얻는다. parser.js는 fileId=클래스명으로 넣는다. */
function docKey(doc) {
  return normalizeSymbol(doc.fileId || doc.className || doc.filePath || '');
}

function asArray(v) {
  if (v == null) return [];
  return Array.isArray(v) ? v : [v];
}

/**
 * @param {object[]} docs  code_base 문서 배열
 * @param {object} [opts]
 * @param {string} [opts.project]        프로젝트 필터 (없으면 전부)
 * @param {boolean} [opts.includeExternal=true]  Unity·외부 심볼을 노드로 남길지
 * @returns {{nodes: object[], edges: object[], stats: object}}
 */
function buildGraph(docs, opts = {}) {
  const includeExternal = opts.includeExternal !== false;
  const nodes = new Map();   // id -> node
  const edges = new Map();   // id -> edge
  const dropped = { noise: 0, selfRef: 0, notEvent: 0 };

  const src = opts.project
    ? docs.filter((d) => String(d.project || '').toLowerCase() === String(opts.project).toLowerCase())
    : docs.slice();

  // 1) 파일 노드 — 먼저 전부 등록해야 참조 해결이 가능하다
  const known = new Set();
  for (const d of src) {
    const key = docKey(d);
    if (!key || isNoise(key)) { dropped.noise++; continue; }
    const id = nodeId(NODE.FILE, key);
    known.add(key);
    nodes.set(id, {
      id,
      type: NODE.FILE,
      name: key,
      system: d.system || null,
      layer: d.layer || null,
      role: d.role || null,
      project: d.project || null,
      path: d.filePath || null,
      score: typeof d.score === 'number' ? d.score : null,
      // 파서를 거쳤는지 — 관계 필드가 하나라도 있으면 true.
      // false면 그래프에 점으로만 떠 있는 노드다 (델타 임베딩만 거친 파일).
      parsed: !!(d.integration || d.provides || d.uses || d.filePath),
    });
  }

  const ensure = (type, name) => {
    const nm = normalizeSymbol(name);
    if (!nm || isNoise(nm)) return null;
    const id = nodeId(type, nm);
    if (!nodes.has(id)) nodes.set(id, { id, type, name: nm });
    return id;
  };

  /** 참조 대상을 노드로 해결. 알려진 파일이면 FILE, Unity 심볼이면 EXTERNAL. */
  const resolveTarget = (name) => {
    const nm = normalizeSymbol(name);
    if (!nm || isNoise(nm)) return null;
    if (known.has(nm)) return nodeId(NODE.FILE, nm);
    if (!includeExternal) return null;
    return ensure(isExternal(nm) ? NODE.EXTERNAL : NODE.EXTERNAL, nm);
  };

  const addEdge = (from, to, type, via) => {
    if (!from || !to) return;
    if (from === to) { dropped.selfRef++; return; }
    const id = edgeId(from, to, type);
    const cur = edges.get(id);
    if (cur) {
      cur.weight += 1;
      if (via && cur.via.length < 6 && !cur.via.includes(via)) cur.via.push(via);
    } else {
      edges.set(id, { id, from, to, type, weight: 1, via: via ? [via] : [] });
    }
  };

  // 2) 관계 필드 → 엣지
  for (const d of src) {
    const key = docKey(d);
    if (!key || isNoise(key)) continue;
    const from = nodeId(NODE.FILE, key);
    const ig = d.integration || {};

    // 호출 (타입 있음)
    for (const sa of asArray(ig.singleton_access)) {
      const target = typeof sa === 'string' ? sa : sa && sa.target;
      const method = typeof sa === 'object' && sa ? sa.method : null;
      addEdge(from, resolveTarget(target), EDGE.CALLS, method || null);
    }

    // 이벤트 — 파일과 이벤트 노드를 잇는다. pub/sub 짝 검사는 graph-query에서.
    for (const ev of asArray(ig.event_publish)) {
      const name = typeof ev === 'string' ? ev : ev && (ev.event || ev.name);
      if (!isLikelyEvent(name)) { dropped.notEvent++; continue; }
      addEdge(from, ensure(NODE.EVENT, name), EDGE.PUBLISHES, null);
    }
    for (const ev of asArray(ig.event_subscribe)) {
      const name = typeof ev === 'string' ? ev : ev && (ev.event || ev.name);
      if (!isLikelyEvent(name)) { dropped.notEvent++; continue; }
      const handler = typeof ev === 'object' && ev ? ev.handler : null;
      addEdge(from, ensure(NODE.EVENT, name), EDGE.SUBSCRIBES, handler || null);
    }

    // 오브젝트 풀
    for (const pu of asArray(ig.pool_usage)) {
      const t = typeof pu === 'string' ? pu : pu && (pu.type || pu.key);
      const action = typeof pu === 'object' && pu ? String(pu.action || '').toLowerCase() : '';
      const kind = action.includes('return') ? EDGE.POOL_RETURN : EDGE.POOL_GET;
      addEdge(from, ensure(NODE.POOL_KEY, t), kind, null);
    }

    // 에셋 로드 / 생성
    for (const r of asArray(ig.resource_load).concat(asArray(ig.addressable_load))) {
      const p = typeof r === 'string' ? r : r && (r.path || r.key);
      addEdge(from, ensure(NODE.PREFAB, p), EDGE.LOADS, null);
    }
    for (const r of asArray(ig.instantiate_calls)) {
      const p = typeof r === 'string' ? r : r && (r.type || r.target);
      addEdge(from, resolveTarget(p) || ensure(NODE.PREFAB, p), EDGE.INSTANTIATES, null);
    }

    // 씬 와이어링
    const sf = (d.unity_config && d.unity_config.serialized_fields) || [];
    for (const f of asArray(sf)) {
      const fname = typeof f === 'string' ? f : f && (f.name || f.field);
      addEdge(from, ensure(NODE.FIELD, fname ? `${key}.${fname}` : null), EDGE.WIRES, null);
    }

    // 타입 미상 폴백 — 위에서 이미 타입드 엣지가 난 대상은 weight만 올라간다
    for (const u of asArray(d.uses).concat(asArray(d.requires))) {
      addEdge(from, resolveTarget(u), EDGE.USES, null);
    }
  }

  const nodeArr = [...nodes.values()];
  const edgeArr = [...edges.values()];
  const byType = (arr, k) => arr.reduce((a, x) => (a[x[k]] = (a[x[k]] || 0) + 1, a), {});

  return {
    nodes: nodeArr,
    edges: edgeArr,
    stats: {
      docs: src.length,
      nodes: nodeArr.length,
      edges: edgeArr.length,
      nodesByType: byType(nodeArr, 'type'),
      edgesByType: byType(edgeArr, 'type'),
      // 파서를 안 거친 파일 — 그래프에 떠 있지만 관계가 없는 노드
      unparsedFiles: nodeArr.filter((n) => n.type === NODE.FILE && !n.parsed).length,
      dropped,
    },
  };
}

module.exports = { buildGraph, docKey };
