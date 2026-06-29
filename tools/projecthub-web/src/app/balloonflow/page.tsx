"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Icon from "@/components/Icon";

// ──────────────────────────────────────────────────────────────
// BalloonFlow — 실제 코드 그래프 (거미줄 G2) · 169개 개별 노드 force-directed 뷰
// 사실 기반: Machine B C:/projects/balloonflow @565ba578 Assets/1.Scripts
// 노드=실제 클래스/파일(169), 엣지=실제 참조(1006). public/balloonflow-graph.json.
// ──────────────────────────────────────────────────────────────

interface GNode { id: string; file: string; system: string; cls: string; classes: string[]; methods?: string[]; loc: number; refsOut: number; refsIn: number; qa?: string; }
interface FEdge { from: string; to: string; via: string[]; n: number; }
interface Sys { name: string; count: number; loc: number; }
interface QASummary { total: number; ok: number; orphan: number; cycle: number; entry: number; cycleGroups: string[][]; }
interface Graph { generatedFrom: string; nodes: GNode[]; edges: FEdge[]; systems: Sys[]; qa?: QASummary; }

const SYS_COLOR: Record<string, string> = {
  Core: "#ef4444", Manager: "#f59e0b", InGame: "#22c55e", Popup: "#a855f7",
  UI: "#3b82f6", UX: "#ec4899", Data: "#14b8a6", Controller: "#eab308",
  Analytics: "#64748b", Util: "#94a3b8", Debug: "#94a3b8", UA: "#06b6d4", "(root)": "#94a3b8",
};
const sysColor = (s: string) => SYS_COLOR[s] || "#94a3b8";

const W = 1500, H = 980;

export default function BalloonFlowPage() {
  const [graph, setGraph] = useState<Graph | null>(null);
  const [mode, setMode] = useState<"graph" | "live" | "qa">("graph");
  const [focus, setFocus] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const [view, setView] = useState({ k: 1, x: 0, y: 0 });
  const [showLimit, setShowLimit] = useState(false);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);

  useEffect(() => {
    fetch("/balloonflow-graph.json").then((r) => r.json()).then(setGraph).catch(() => setGraph(null));
  }, []);

  // ── force-directed 레이아웃 (graph 변경 시 1회 계산, 결정론적 init) ──
  const layout = useMemo(() => {
    if (!graph) return null;
    const nodes = graph.nodes;
    const n = nodes.length;
    const idx: Record<string, number> = {};
    nodes.forEach((nd, i) => (idx[nd.id] = i));
    const sysList = [...new Set(nodes.map((nd) => nd.system))];
    const sysAngle: Record<string, number> = {};
    sysList.forEach((s, i) => (sysAngle[s] = (i / sysList.length) * Math.PI * 2));
    const px = new Float64Array(n), py = new Float64Array(n);
    nodes.forEach((nd, i) => {
      const a = sysAngle[nd.system] + ((i % 9) - 4) * 0.04;
      const r = 300 + (i % 17) * 9;
      px[i] = W / 2 + r * Math.cos(a);
      py[i] = H / 2 + r * Math.sin(a);
    });
    const E = graph.edges
      .map((e) => [idx[e.from], idx[e.to]] as [number, number])
      .filter(([a, b]) => a != null && b != null);
    let alpha = 1;
    for (let it = 0; it < 320; it++) {
      const fx = new Float64Array(n), fy = new Float64Array(n);
      for (let i = 0; i < n; i++) {
        for (let j = i + 1; j < n; j++) {
          let dx = px[i] - px[j], dy = py[i] - py[j];
          const d2 = dx * dx + dy * dy + 0.01;
          const dd = Math.sqrt(d2);
          const f = 2700 / d2;
          const ux = dx / dd, uy = dy / dd;
          fx[i] += ux * f; fy[i] += uy * f; fx[j] -= ux * f; fy[j] -= uy * f;
        }
      }
      for (const [a, b] of E) {
        let dx = px[b] - px[a], dy = py[b] - py[a];
        const d = Math.sqrt(dx * dx + dy * dy) + 0.01;
        const f = (d - 64) * 0.018;
        const ux = dx / d, uy = dy / d;
        fx[a] += ux * f; fy[a] += uy * f; fx[b] -= ux * f; fy[b] -= uy * f;
      }
      // 약한 시스템 응집(경계 강화, 색상 보조) + 중심 중력
      const cx: Record<string, number> = {}, cy: Record<string, number> = {}, cc: Record<string, number> = {};
      for (let i = 0; i < n; i++) { const s = nodes[i].system; cx[s] = (cx[s] || 0) + px[i]; cy[s] = (cy[s] || 0) + py[i]; cc[s] = (cc[s] || 0) + 1; }
      for (let i = 0; i < n; i++) {
        const s = nodes[i].system;
        fx[i] += (cx[s] / cc[s] - px[i]) * 0.03 + (W / 2 - px[i]) * 0.0016;
        fy[i] += (cy[s] / cc[s] - py[i]) * 0.03 + (H / 2 - py[i]) * 0.0016;
      }
      for (let i = 0; i < n; i++) {
        px[i] += Math.max(-16, Math.min(16, fx[i] * alpha));
        py[i] += Math.max(-16, Math.min(16, fy[i] * alpha));
      }
      alpha *= 0.985;
    }
    const pos: Record<string, { x: number; y: number }> = {};
    nodes.forEach((nd, i) => {
      pos[nd.id] = { x: Math.max(30, Math.min(W - 30, px[i])), y: Math.max(30, Math.min(H - 30, py[i])) };
    });
    // 시스템 헐(경계 색): centroid + 반지름
    const hulls = graph.systems.map((s) => {
      const ns = nodes.filter((nd) => nd.system === s.name);
      const mx = ns.reduce((a, nd) => a + pos[nd.id].x, 0) / ns.length;
      const my = ns.reduce((a, nd) => a + pos[nd.id].y, 0) / ns.length;
      const rad = Math.max(40, ...ns.map((nd) => Math.hypot(pos[nd.id].x - mx, pos[nd.id].y - my))) + 18;
      return { name: s.name, x: mx, y: my, r: rad };
    });
    return { pos, hulls };
  }, [graph]);

  const jumpToCode = (filePath: string) => {
    const rel = filePath.includes("/1.Scripts/") ? filePath.split("/1.Scripts/")[1] : filePath;
    const n = graph?.nodes.find((nd) => nd.id === rel || nd.id.endsWith(rel) || rel.endsWith(nd.id));
    if (n) setFocus(n.id);
    setMode("graph");
  };
  const focusNode = (id: string) => { setFocus(id); setMode("graph"); };
  const LIMIT_TEXT = mode === "qa"
    ? "QA 범위(정직): 정적 구조 정합성(고아·순환·피참조 전수)으로 유기적 연결을 확인합니다. 컴파일/런타임(실제 에러 없이 도는지)은 Unity 빌드가 필요 = 별도 트랙(MCP/batchmode). 정적 참조라 동적 디스패치 누락·순환 일부 과다검출 가능."
    : "정적 참조 기반 — Unity 동적 디스패치(UnityEvent/SendMessage/리플렉션) 일부 누락. depth-1. 스냅샷(@565ba578, 코드 변경 시 재생성). 현재는 사실 기반 뷰어 + 데이터 — Hermes 편집/QA 실행 연결은 Phase 1 노드엔진 + Phase 2 extract/check 노드.";
  const modeBtn = (m: "graph" | "live" | "qa", icon: string, label: string) => (
    <button onClick={() => setMode(m)}
      className={`text-xs px-3 py-1.5 rounded-md font-medium inline-flex items-center gap-1.5 transition-colors ${mode === m ? "bg-blue-500 text-white" : "text-gray-300 hover:bg-white/10"}`}>
      <Icon name={icon} size={14} /> {label}
    </button>
  );
  const modeBarEl = (
    <div className="inline-flex rounded-lg border border-gray-700 bg-[#0d0f14]/90 backdrop-blur p-1 shadow-lg">
      {modeBtn("graph", "graph", "코드 그래프")}
      {modeBtn("live", "zap", "실행 파이프라인")}
      {modeBtn("qa", "flask", "QA 정합성")}
    </div>
  );
  const helpFloat = (
    <button onClick={() => setShowLimit(true)} aria-label="한계/안내" title="이 뷰의 한계/안내"
      className="w-8 h-8 rounded-full border border-gray-700 bg-[#0d0f14]/90 text-gray-400 hover:text-gray-200 flex items-center justify-center shadow-lg shrink-0">
      <Icon name="help" size={15} />
    </button>
  );
  const limitModal = showLimit ? (
    <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4 fade-in" onClick={() => setShowLimit(false)}>
      <div className="bg-white rounded-xl max-w-md w-full p-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-2">
          <h3 className="font-bold text-sm flex items-center gap-1.5"><Icon name="help" size={16} /> 한계 / 안내</h3>
          <button onClick={() => setShowLimit(false)} className="text-gray-400 hover:text-gray-200"><Icon name="x" size={18} /></button>
        </div>
        <p className="text-sm text-gray-600 leading-relaxed">{LIMIT_TEXT}</p>
      </div>
    </div>
  ) : null;
  if (mode === "live") return (
    <>
    <div className="relative w-full rounded-xl border border-gray-800 overflow-hidden" style={{ height: "calc(100vh - 130px)", minHeight: 500, background: "#141821" }}>
      <div className="absolute inset-0 overflow-auto thin-scroll pt-16 px-3 pb-3"><LivePipeline onJump={jumpToCode} /></div>
      <div className="absolute top-2.5 left-2.5 z-20">{modeBarEl}</div>
      <div className="absolute top-2.5 right-2.5 z-20">{helpFloat}</div>
    </div>
    {limitModal}
    </>
  );
  if (mode === "qa") return (
    <>
    <div className="relative w-full rounded-xl border border-gray-800 overflow-hidden" style={{ height: "calc(100vh - 130px)", minHeight: 500, background: "#141821" }}>
      <div className="absolute inset-0 overflow-auto thin-scroll pt-16 px-3 pb-3">{graph ? <QaReport graph={graph} onJump={focusNode} /> : <div className="text-gray-400 p-8">로딩 중…</div>}</div>
      <div className="absolute top-2.5 left-2.5 z-20">{modeBarEl}</div>
      <div className="absolute top-2.5 right-2.5 z-20">{helpFloat}</div>
    </div>
    {limitModal}
    </>
  );
  if (!graph || !layout) return (<><div className="flex items-center gap-2 mb-3">{modeBarEl}</div><div className="text-sm text-gray-400 p-8">실제 코드 그래프 로딩 중…</div>{limitModal}</>);

  const byId = (id: string) => graph.nodes.find((nd) => nd.id === id);
  const rOf = (nd: GNode) => Math.max(3.5, Math.min(15, 3.5 + Math.sqrt(nd.refsIn) * 1.7));

  // 이웃(1-hop) 집합
  const neigh = new Set<string>();
  if (focus) {
    graph.edges.forEach((e) => { if (e.from === focus) neigh.add(e.to); if (e.to === focus) neigh.add(e.from); });
  }
  const visible = (s: string) => !hidden.has(s);

  const matches = q.trim()
    ? graph.nodes.filter((nd) => (nd.cls + " " + nd.classes.join(" ") + " " + nd.file).toLowerCase().includes(q.toLowerCase())).slice(0, 30)
    : [];

  const fnode = focus ? byId(focus) : null;
  const deps = focus ? graph.edges.filter((e) => e.from === focus) : [];
  const dependents = focus ? graph.edges.filter((e) => e.to === focus) : [];

  // pan/zoom
  const onWheel = (e: React.WheelEvent) => {
    const f = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    setView((v) => ({ ...v, k: Math.max(0.4, Math.min(4, v.k * f)) }));
  };
  const onDown = (e: React.PointerEvent) => { drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }; };
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return; // 로컬 캡처 — setView 업데이터에서 drag.current를 다시 읽지 않음(null 레이스 방지)
    const nx = d.vx + (e.clientX - d.x);
    const ny = d.vy + (e.clientY - d.y);
    setView((v) => ({ ...v, x: nx, y: ny }));
  };
  const onUp = () => { drag.current = null; };

  return (
    <>
    <div className="relative w-full rounded-xl border border-gray-800 overflow-hidden" style={{ height: "calc(100vh - 130px)", minHeight: 500, background: "#141821" }}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" className="absolute inset-0"
        style={{ width: "100%", height: "100%", display: "block", cursor: drag.current ? "grabbing" : "grab" }}
        onWheel={onWheel} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={onUp}>
            <defs>
              <marker id="arrow" markerWidth="9" markerHeight="9" refX="7" refY="3" orient="auto" markerUnits="userSpaceOnUse">
                <path d="M0,0 L7,3 L0,6 Z" fill="context-stroke" />
              </marker>
            </defs>
            <rect width={W} height={H} fill="#141821" onClick={() => setFocus(null)} />
            <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
              {/* 시스템 헐 (경계 색) — 원만 (라벨은 노드 위 별도 패스) */}
              {layout.hulls.map((h) => visible(h.name) && (
                <circle key={h.name} cx={h.x} cy={h.y} r={h.r} fill={sysColor(h.name)} fillOpacity={0.05} stroke={sysColor(h.name)} strokeOpacity={0.2} strokeWidth={1} />
              ))}
              {/* 엣지: 기본 흐리게, 포커스 시 해당 노드 연결만 밝게 */}
              {graph.edges.map((e, i) => {
                const a = layout.pos[e.from], b = layout.pos[e.to];
                const na = byId(e.from), nb = byId(e.to);
                if (!a || !b || !na || !nb || !visible(na.system) || !visible(nb.system)) return null;
                const hot = focus && (e.from === focus || e.to === focus);
                if (focus && !hot) return (
                  <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#2b313d" strokeWidth={0.4} strokeOpacity={0.15} />
                );
                if (hot) {
                  // 방향 화살표: from(의존하는 쪽) → to(의존받는 쪽). 타깃 노드 반경만큼 트림해 화살표가 보이게.
                  const dx = b.x - a.x, dy = b.y - a.y, L = Math.hypot(dx, dy) || 1, r = rOf(nb) + 6;
                  const bx = b.x - (dx / L) * r, by = b.y - (dy / L) * r;
                  return (
                    <line key={i} x1={a.x} y1={a.y} x2={bx} y2={by}
                      stroke={sysColor(na.system)} strokeWidth={1.8} strokeOpacity={0.95} markerEnd="url(#arrow)" />
                  );
                }
                return (
                  <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#4a5263" strokeWidth={0.5} strokeOpacity={0.07} />
                );
              })}
              {/* 노드 */}
              {graph.nodes.map((nd) => {
                const p = layout.pos[nd.id];
                if (!p || !visible(nd.system)) return null;
                const isF = nd.id === focus;
                const isN = neigh.has(nd.id);
                const dim = focus && !isF && !isN;
                const showLabel = isF || isN || nd.refsIn >= 18;
                return (
                  <g key={nd.id} transform={`translate(${p.x},${p.y})`} style={{ cursor: "pointer" }}
                    onClick={(ev) => { ev.stopPropagation(); setFocus(nd.id); }}>
                    {nd.qa === "orphan" && !dim && <circle r={rOf(nd) + 4} fill="none" stroke="#ef4444" strokeWidth={1.2} strokeDasharray="2 2" />}
                    <circle r={rOf(nd) + (isF ? 3 : 0)} fill={sysColor(nd.system)}
                      stroke={isF ? "#fff" : "#0d0f14"} strokeWidth={isF ? 2 : 0.8}
                      fillOpacity={dim ? 0.18 : 1} />
                    {showLabel && !dim && (
                      <>
                        <rect x={rOf(nd) + 3} y={-7} width={nd.cls.length * (isF ? 6.4 : 5.6) + 7} height={14} rx={3} fill="#0d0f14" fillOpacity={0.72} />
                        <text x={rOf(nd) + 6} y={3.5} fontSize={isF ? 12 : 10} fill="#e6e9ef" fontWeight={isF ? 700 : 500}>{nd.cls}</text>
                      </>
                    )}
                  </g>
                );
              })}
              {/* 카테고리(시스템) 라벨 — 노드 위에 렌더해 가림 방지 + 배경 펠릿 */}
              {layout.hulls.map((h) => visible(h.name) && (
                <g key={"lbl-" + h.name} transform={`translate(${h.x},${h.y - h.r + 2})`}>
                  <rect x={-(h.name.length * 4 + 9)} y={-11} width={h.name.length * 8 + 18} height={18} rx={9} fill="#0d0f14" fillOpacity={0.78} stroke={sysColor(h.name)} strokeOpacity={0.6} />
                  <text textAnchor="middle" y={2} fontSize={12} fontWeight={700} fill={sysColor(h.name)}>{h.name}</text>
                </g>
              ))}
            </g>
          </svg>

          {/* 좌상단: 모드 버튼 (Figma 코너 툴바) */}
          <div className="absolute top-2.5 left-2.5 z-20">{modeBarEl}</div>

          {/* 우상단: 검색 + 줌 + ? */}
          <div className="absolute top-2.5 right-2.5 z-20 flex flex-col items-end gap-2 max-w-[62%]">
            <div className="flex items-center gap-1.5">
              <span className="relative inline-flex items-center">
                <span className="absolute left-2.5 text-gray-400 pointer-events-none"><Icon name="search" size={15} /></span>
                <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="클래스/파일 검색"
                  className="text-sm rounded-lg pl-8 pr-3 py-1.5 w-48 bg-[#0d0f14]/90 border border-gray-700 text-gray-100 outline-none" />
              </span>
              <button onClick={() => setView({ k: 1, x: 0, y: 0 })} className="text-xs px-2.5 py-1.5 rounded-lg border border-gray-700 bg-[#0d0f14]/90 text-gray-300 hover:bg-white/10">리셋</button>
              <button onClick={() => setView((v) => ({ ...v, k: Math.max(0.4, v.k / 1.25) }))} aria-label="축소" className="w-8 h-8 rounded-lg border border-gray-700 bg-[#0d0f14]/90 text-gray-300 hover:bg-white/10 flex items-center justify-center text-base leading-none">－</button>
              <button onClick={() => setView((v) => ({ ...v, k: Math.min(4, v.k * 1.25) }))} aria-label="확대" className="w-8 h-8 rounded-lg border border-gray-700 bg-[#0d0f14]/90 text-gray-300 hover:bg-white/10 flex items-center justify-center text-base leading-none">＋</button>
              {helpFloat}
            </div>
            {matches.length > 0 && (
              <div className="flex flex-wrap gap-1 justify-end bg-[#0d0f14]/85 backdrop-blur rounded-lg p-1.5 max-h-40 overflow-y-auto thin-scroll">
                {matches.map((nd) => (
                  <button key={nd.id} onClick={() => setFocus(nd.id)} className="text-xs px-2 py-0.5 rounded-full border hover:bg-white/10"
                    style={{ borderColor: sysColor(nd.system), color: sysColor(nd.system) }}>
                    {nd.cls} <span className="opacity-50">·{nd.system}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* 좌하단: 시스템 칩 */}
          <div className="absolute bottom-2.5 left-2.5 z-20 flex flex-wrap items-center gap-1.5 max-w-[78%] bg-[#0d0f14]/80 backdrop-blur rounded-lg p-1.5">
            <span className="text-xs text-gray-400 mr-0.5">시스템</span>
            {graph.systems.map((s) => {
              const on = visible(s.name);
              return (
                <button key={s.name} onClick={() => setHidden((h) => { const n = new Set(h); n.has(s.name) ? n.delete(s.name) : n.add(s.name); return n; })}
                  className={`text-xs px-2 py-1 rounded-full border inline-flex items-center gap-1.5 transition ${on ? "text-gray-200 hover:bg-white/10" : "opacity-45 line-through text-gray-400"}`}
                  style={{ borderColor: sysColor(s.name) + "66" }}>
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ background: sysColor(s.name) }} />
                  {s.name} <span className="text-gray-500">{s.count}</span>
                </button>
              );
            })}
          </div>

          {/* 우측: 노드 상세 (포커스 시 플로팅) */}
          {fnode && (
            <div className="absolute top-16 right-2.5 z-20 w-72 max-h-[calc(100%-5rem)] overflow-y-auto thin-scroll rounded-xl border border-gray-200 bg-white p-3 text-sm shadow-2xl">
              <button onClick={() => setFocus(null)} className="absolute top-2 right-2 text-gray-400 hover:text-gray-600"><Icon name="x" size={16} /></button>
              <div className="space-y-2">
                <div className="flex items-center gap-2 pr-6">
                  <span className="w-3 h-3 rounded-full" style={{ background: sysColor(fnode.system) }} />
                  <span className="font-bold text-base">{fnode.cls}</span>
                </div>
                <div className="text-xs text-gray-400 break-all">{fnode.id}</div>
                <div className="flex gap-3 text-xs">
                  <span>{fnode.loc}L</span><span className="text-rose-600">⬅ {fnode.refsIn}</span><span className="text-emerald-600">➡ {fnode.refsOut}</span>
                </div>
                <div className="text-xs font-semibold text-emerald-700 mt-1">의존 ({deps.length})</div>
                <div className="space-y-0.5">
                  {deps.slice(0, 40).map((e, i) => { const t = byId(e.to); return (
                    <button key={i} onClick={() => t && setFocus(t.id)} className="block text-left text-xs hover:underline w-full">
                      <span style={{ color: sysColor(t?.system || "") }}>{t?.cls}</span>
                      <span className="text-gray-400"> ·{t?.system} <span className="opacity-60">({e.via.join(", ")})</span></span>
                    </button> ); })}
                  {deps.length === 0 && <div className="text-xs text-gray-300">없음(말단)</div>}
                </div>
                <div className="text-xs font-semibold text-rose-700 mt-1">피의존 ({dependents.length})</div>
                <div className="space-y-0.5">
                  {dependents.slice(0, 40).map((e, i) => { const t = byId(e.from); return (
                    <button key={i} onClick={() => t && setFocus(t.id)} className="block text-left text-xs hover:underline w-full">
                      <span style={{ color: sysColor(t?.system || "") }}>{t?.cls}</span><span className="text-gray-400"> ·{t?.system}</span>
                    </button> ); })}
                  {dependents.length === 0 && <div className="text-xs text-gray-300">없음</div>}
                </div>
              </div>
            </div>
          )}
        </div>
      {limitModal}
      </>
    );
}

// ──────────────────────────────────────────────────────────────
// G1 — 실행 파이프라인 (라이브): 실제 hermes_agent_sessions(에이전트 호출=노드 실행)을
// 노드로 연결. 완료 기록 기반 — 진짜 in-flight 정밀표시는 노드 저널(다음 슬라이스) 필요.
// in_progress 작업은 '마지막 실행 노드'로 현재 위치 추정. 15초 폴링.
// ──────────────────────────────────────────────────────────────
interface Sess { task_id: string; task_title?: string; role: string; model?: string; duration_sec?: number; success?: boolean; error?: string | null; created_at?: string; }
interface TaskLite { _id?: string; title?: string; assignee?: string; status?: string; current_phase?: number; }

const PIPE: { id: string; label: string; color: string }[] = [
  { id: "translator", label: "Translator", color: "#3b82f6" },
  { id: "pm", label: "PM", color: "#0ea5e9" },
  { id: "lead", label: "Lead", color: "#8b5cf6" },
  { id: "coder", label: "Coder", color: "#a855f7" },
  { id: "validator", label: "Validator", color: "#22c55e" },
  { id: "reviewer", label: "Reviewer", color: "#ef4444" },
];
const EXTRA: { id: string; label: string; color: string }[] = [
  { id: "writer", label: "Writer", color: "#14b8a6" },
  { id: "prompter", label: "Art Prompter", color: "#ec4899" },
  { id: "optimizer", label: "Optimizer", color: "#f59e0b" },
];
function roleNode(role: string): string {
  const r = (role || "").toLowerCase();
  if (r.includes("translator")) return "translator";
  if (r === "pm" || r.endsWith("_pm")) return "pm";
  if (r.endsWith("lead")) return "lead";
  if (r.includes("writer")) return "writer";
  if (r.includes("prompter")) return "prompter";
  if (r.includes("optimization_reviewer")) return "reviewer";
  if (r.includes("optimizer")) return "optimizer";
  if (r.includes("coder")) return "coder";
  if (r.includes("validator")) return "validator";
  if (r.includes("reviewer")) return "reviewer";
  return "기타";
}
function isHermes(t: TaskLite) { return /hermes|헤르메스/i.test(t.assignee || ""); }
function ago(iso?: string): string {
  if (!iso) return "";
  const ms = Date.now() - Date.parse(iso);
  if (isNaN(ms)) return "";
  const m = Math.floor(ms / 60000);
  if (m < 1) return "방금";
  if (m < 60) return `${m}분 전`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}시간 전`;
  return `${Math.floor(h / 24)}일 전`;
}

function LivePipeline({ onJump }: { onJump: (f: string) => void }) {
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [tasks, setTasks] = useState<TaskLite[]>([]);
  const [running, setRunning] = useState<{ task_id: string; role: string }[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [selSess, setSelSess] = useState<Sess[]>([]);
  const [selFiles, setSelFiles] = useState<string[]>([]);

  useEffect(() => {
    const load = () => {
      fetch("/api/agents/sessions?limit=200").then((r) => r.json()).then((d) => setSessions(d.sessions || [])).catch(() => {});
      fetch("/api/agents/node-runs").then((r) => r.json()).then((d) => setRunning(d.running || [])).catch(() => {});
      fetch("/api/tasks").then((r) => r.json()).then((d) => {
        const arr: TaskLite[] = Array.isArray(d) ? d : (d.tasks || []);
        setTasks(arr.filter((t) => isHermes(t) && t.status === "in_progress"));
      }).catch(() => {});
    };
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    if (!sel) { setSelSess([]); setSelFiles([]); return; }
    fetch(`/api/agents/sessions?task_id=${sel}&limit=80`).then((r) => r.json()).then((d) => setSelSess(d.sessions || [])).catch(() => {});
    fetch(`/api/agents/node-runs?task_id=${sel}`).then((r) => r.json()).then((d) => setSelFiles(d.files || [])).catch(() => {});
  }, [sel]);

  const runningNodes = new Set(running.map((r) => roleNode(r.role)));
  const runningByTask: Record<string, string> = {};
  running.forEach((r) => { if (!runningByTask[r.task_id]) runningByTask[r.task_id] = roleNode(r.role); });

  // 노드별 집계
  const agg: Record<string, { n: number; ok: number; dur: number; last: number }> = {};
  for (const s of sessions) {
    const k = roleNode(s.role);
    agg[k] = agg[k] || { n: 0, ok: 0, dur: 0, last: 0 };
    agg[k].n++; if (s.success) agg[k].ok++; agg[k].dur += s.duration_sec || 0;
    const ts = s.created_at ? Date.parse(s.created_at) : 0;
    if (ts > agg[k].last) agg[k].last = ts;
  }
  const hot = (k: string) => agg[k] && Date.now() - agg[k].last < 180000; // 3분 내 활동

  // in_progress 작업의 추정 현재 노드 = 그 task의 최신 세션 노드
  const latestNodeFor: Record<string, { node: string; ts: number }> = {};
  for (const s of sessions) {
    const ts = s.created_at ? Date.parse(s.created_at) : 0;
    const cur = latestNodeFor[s.task_id];
    if (!cur || ts > cur.ts) latestNodeFor[s.task_id] = { node: roleNode(s.role), ts };
  }

  const extrasPresent = EXTRA.filter((e) => agg[e.id]);
  const recent = [...sessions].slice(0, 14);
  const pathSess = [...selSess].sort((a, b) => Date.parse(a.created_at || "") - Date.parse(b.created_at || ""));

  const NodeBox = ({ nd }: { nd: { id: string; label: string; color: string } }) => {
    const a = agg[nd.id];
    const okPct = a && a.n ? Math.round((a.ok / a.n) * 100) : 0;
    return (
      <div className="rounded-lg border-2 px-3 py-2 min-w-[120px]" style={{ borderColor: nd.color, background: hot(nd.id) ? nd.color + "22" : "#fff" }}>
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full" style={{ background: nd.color }} />
          <span className="text-sm font-bold">{nd.label}</span>
          {runningNodes.has(nd.id) && <span className="text-[10px] text-white bg-emerald-600 rounded px-1 animate-pulse">▶ 실행중</span>}
          {!runningNodes.has(nd.id) && hot(nd.id) && <span className="text-[10px] text-emerald-600">● 최근</span>}
        </div>
        {a ? (
          <div className="text-[11px] text-gray-500 mt-0.5">
            {a.n}회 · 성공 {okPct}% · 평균 {(a.dur / a.n).toFixed(0)}s
            <div className="text-[10px] text-gray-400">{ago(new Date(a.last).toISOString())}</div>
          </div>
        ) : <div className="text-[11px] text-gray-300 mt-0.5">기록 없음</div>}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* 파이프라인 노드 행 */}
      <div className="flex flex-wrap items-center gap-1">
        {PIPE.map((nd, i) => (
          <div key={nd.id} className="flex items-center gap-1">
            <NodeBox nd={nd} />
            {i < PIPE.length - 1 && <span className="text-gray-300">→</span>}
          </div>
        ))}
      </div>
      {extrasPresent.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-gray-400">기타 분과:</span>
          {extrasPresent.map((nd) => <NodeBox key={nd.id} nd={nd} />)}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 현재 진행 중 작업 */}
        <div className="rounded-lg border border-gray-200 bg-white p-3">
          <div className="font-semibold text-sm mb-2">🔵 현재 진행 중 (in_progress · {tasks.length})</div>
          {tasks.length === 0 && <div className="text-xs text-gray-400">진행 중인 Hermes 작업 없음 (idle)</div>}
          <div className="space-y-1">
            {tasks.map((t) => {
              const runNode = t._id ? runningByTask[t._id] : undefined;
              const curNode = runNode || (t._id ? latestNodeFor[t._id]?.node : undefined);
              const nodeMeta = [...PIPE, ...EXTRA].find((p) => p.id === curNode);
              return (
                <button key={t._id} onClick={() => setSel(t._id || null)} className="flex items-center justify-between w-full text-left text-xs py-1 px-1.5 rounded hover:bg-gray-50">
                  <span className="truncate">{t.title}{t.current_phase ? <span className="text-gray-400"> · phase {t.current_phase}</span> : null}</span>
                  {curNode && <span className={`shrink-0 ml-2 px-1.5 py-0.5 rounded text-white text-[10px] ${runNode ? "animate-pulse" : ""}`} style={{ background: nodeMeta?.color || "#94a3b8" }}>{runNode ? "▶ " : "@"}{nodeMeta?.label || curNode}</span>}
                </button>
              );
            })}
          </div>
        </div>

        {/* 선택 작업의 노드 경로 OR 최근 활동 */}
        <div className="rounded-lg border border-gray-200 bg-white p-3 max-h-[420px] overflow-y-auto">
          {sel ? (
            <div>
              <button onClick={() => setSel(null)} className="text-xs text-blue-600 mb-2">← 최근 활동</button>
              <div className="font-semibold text-sm mb-2">작업 노드 경로 (실제 실행 순서)</div>
              <div className="space-y-1">
                {pathSess.map((s, i) => {
                  const nm = [...PIPE, ...EXTRA].find((p) => p.id === roleNode(s.role));
                  return (
                    <div key={i} className="flex items-center gap-2 text-xs">
                      <span className="px-1.5 py-0.5 rounded text-white text-[10px] shrink-0" style={{ background: nm?.color || "#94a3b8" }}>{nm?.label || roleNode(s.role)}</span>
                      <span className="text-gray-500">{s.role}</span>
                      <span className={s.success ? "text-emerald-600" : "text-rose-600"}>{s.success ? "✓" : "✗"}</span>
                      <span className="text-gray-400">{(s.duration_sec || 0).toFixed(0)}s · {ago(s.created_at)}</span>
                    </div>
                  );
                })}
                {pathSess.length === 0 && <div className="text-xs text-gray-400">세션 기록 없음</div>}
              </div>
              {selFiles.length > 0 && (
                <div className="mt-3">
                  <div className="font-semibold text-sm mb-1 flex items-center gap-1.5"><Icon name="graph" size={15} /> 수정한 코드 ({selFiles.length}) <span className="text-[10px] text-gray-400 font-normal">클릭 → 코드그래프</span></div>
                  <div className="space-y-0.5">
                    {selFiles.map((f, i) => (
                      <button key={i} onClick={() => onJump(f)} className="block text-left text-xs hover:underline w-full text-indigo-600 truncate">
                        {f.includes("/1.Scripts/") ? f.split("/1.Scripts/")[1] : f}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div>
              <div className="font-semibold text-sm mb-2">📜 최근 노드 실행</div>
              <div className="space-y-1">
                {recent.map((s, i) => {
                  const nm = [...PIPE, ...EXTRA].find((p) => p.id === roleNode(s.role));
                  return (
                    <button key={i} onClick={() => setSel(s.task_id)} className="flex items-center gap-2 text-xs w-full text-left hover:bg-gray-50 rounded px-1 py-0.5">
                      <span className="px-1.5 py-0.5 rounded text-white text-[10px] shrink-0" style={{ background: nm?.color || "#94a3b8" }}>{nm?.label || roleNode(s.role)}</span>
                      <span className={s.success ? "text-emerald-600" : "text-rose-600"}>{s.success ? "✓" : "✗"}</span>
                      <span className="truncate flex-1 text-gray-600">{s.task_title || s.task_id}</span>
                      <span className="text-gray-400 shrink-0">{ago(s.created_at)}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-xs text-blue-900/80">
        <b>이게 "노드엔진 연결" 1차</b>: 실제 Hermes 실행(에이전트 호출)이 노드로 표시됨 — 백엔드 무변경(기존 세션 로그 재사용). <b>다음 슬라이스</b>: 노드 저널(node_start/end)로 진짜 in-flight 상태 + A7 stage→노드 래핑(실행 단위를 노드로) + G1↔G2 연결(어느 노드가 어떤 코드 파일을 건드렸는지).
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// QA — 코드 그래프 전수 정합성 검사 (정적): 고아 노드 · 순환 의존(SCC) · 피참조0.
// "유기적으로 연결돼 에러없이 도는가"를 구조 차원에서 점검. (컴파일/런타임은 빌드 필요 — 별도)
// ──────────────────────────────────────────────────────────────
// ──────────────────────────────────────────────────────────────
// QA — Behavior-Tree 스타일 계층 뷰: 루트 → 시스템 → 파일.
// 각 노드 = 박스(아이콘·제목·부제·인덱스 배지) + 상태 테두리(🔴고아/🟠순환/🟡피참조0/정상).
// 시스템 클릭 = 펼침/접힘. 파일 클릭 = G2 코드그래프 점프. 직각 커넥터(top-down).
// ──────────────────────────────────────────────────────────────
// ──────────────────────────────────────────────────────────────
// QA — 세로 들여쓰기 트리(파일탐색기 스타일): 루트 → 시스템 → 파일 → 기능(메서드).
// 화면 꽉 채움(세로 스크롤). 좌측 색바=상태(🔴고아/🟠순환/🟡피참조0/정상). 펼침/접힘.
// ──────────────────────────────────────────────────────────────
// ──────────────────────────────────────────────────────────────
// QA — Behavior-Tree(top-down) 노드박스+커넥터. 루트→시스템→파일→기능.
// 기본 접힘(루트+시스템)=균형. 시스템/파일 클릭=펼침(깊이↑). 휠 줌·드래그 이동. 화면 맞춤.
// ──────────────────────────────────────────────────────────────
// ──────────────────────────────────────────────────────────────
// QA — Behavior-Tree(top-down) + grid-wrap: 자식이 많으면 10개씩 줄바꿈해 층구조로.
// 루트→시스템→파일→기능. 노드 클릭=펼침. 휠 줌·드래그 이동. 화면 맞춤.
// ──────────────────────────────────────────────────────────────
function QaReport({ graph, onJump }: { graph: Graph; onJump: (id: string) => void }) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [qv, setQv] = useState({ k: 1, x: 0, y: 0 });
  const qdrag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);
  const nodes = graph.nodes;
  const qa: QASummary = graph.qa || {
    total: nodes.length,
    ok: nodes.filter((n) => (n.qa || "ok") === "ok").length,
    orphan: nodes.filter((n) => n.qa === "orphan").length,
    cycle: nodes.filter((n) => n.qa === "cycle").length,
    entry: nodes.filter((n) => n.qa === "entry").length,
    cycleGroups: [],
  };
  const issues = qa.orphan + qa.cycle + qa.entry;
  const qaBorder = (q?: string) => (q === "orphan" ? "#ef4444" : q === "cycle" ? "#f59e0b" : q === "entry" ? "#eab308" : "#3a4150");
  const qaIcon = (q?: string) => (q === "orphan" ? "🔴" : q === "cycle" ? "🟠" : q === "entry" ? "🟡" : "◻");
  const toggle = (key: string) => setOpen((o) => { const n = new Set(o); n.has(key) ? n.delete(key) : n.add(key); return n; });

  const NODEW = 150, NODEH = 50, XGAP = 24, YGAP = 60, ROWGAP = 22, COLS = 10;
  type TN = { id: string; depth: number; kind: "root" | "sys" | "file" | "method"; label: string; sub: string; border: string; icon: string; x: number; y: number; w: number; h: number; jump?: string; tgl?: string };
  const tn: TN[] = [];
  const links: [string, string][] = [];
  tn.push({ id: "root", depth: 0, kind: "root", label: "루트 · BalloonFlow", sub: `${qa.total} files · 이슈 ${issues}`, border: "#6b7280", icon: "🎈", x: 0, y: 0, w: NODEW, h: NODEH });
  for (const s of graph.systems) {
    const sfiles = nodes.filter((n) => n.system === s.name);
    const iss = sfiles.filter((n) => n.qa && n.qa !== "ok").length;
    const sOpen = open.has(s.name);
    tn.push({ id: "sys:" + s.name, depth: 1, kind: "sys", label: s.name, sub: `${s.count}개 · 이슈 ${iss}`, border: iss > 0 ? "#ef4444" : sysColor(s.name), icon: sOpen ? "📂" : "📁", x: 0, y: 0, w: NODEW, h: NODEH, tgl: s.name });
    links.push(["root", "sys:" + s.name]);
    if (sOpen) for (const f of sfiles) {
      const ms = f.methods || [];
      const fOpen = open.has(f.id);
      tn.push({ id: f.id, depth: 2, kind: "file", label: f.cls, sub: `${ms.length}기능 · ⬅${f.refsIn} ➡${f.refsOut}`, border: qaBorder(f.qa), icon: ms.length ? (fOpen ? "🔽" : "▶") : qaIcon(f.qa), x: 0, y: 0, w: NODEW, h: NODEH, tgl: ms.length ? f.id : undefined, jump: ms.length ? undefined : f.id });
      links.push(["sys:" + s.name, f.id]);
      if (fOpen) for (const m of ms) {
        tn.push({ id: f.id + "::" + m, depth: 3, kind: "method", label: m, sub: f.cls, border: qaBorder(f.qa), icon: "ƒ", x: 0, y: 0, w: NODEW, h: NODEH, jump: f.id });
        links.push([f.id, f.id + "::" + m]);
      }
    }
  }
  const byIdT: Record<string, TN> = {}; tn.forEach((t) => (byIdT[t.id] = t));
  const childrenOf = (id: string) => links.filter((l) => l[0] === id).map((l) => byIdT[l[1]]);

  // grid-wrap measure: 자식을 COLS개씩 줄바꿈한 블록의 bbox를 t.w/t.h에 기록
  const measure = (t: TN) => {
    const ch = childrenOf(t.id);
    if (ch.length === 0) { t.w = NODEW; t.h = NODEH; return; }
    ch.forEach(measure);
    let blockW = 0, blockH = 0;
    for (let i = 0; i < ch.length; i += COLS) {
      const row = ch.slice(i, i + COLS);
      const rowW = row.reduce((a, c) => a + c.w, 0) + (row.length - 1) * XGAP;
      const rowH = Math.max(...row.map((c) => c.h));
      blockW = Math.max(blockW, rowW);
      blockH += rowH + ROWGAP;
    }
    blockH -= ROWGAP;
    t.w = Math.max(NODEW, blockW);
    t.h = NODEH + YGAP + blockH;
  };
  const place = (t: TN, x: number, y: number) => {
    t.x = x + (t.w - NODEW) / 2;
    t.y = y;
    const ch = childrenOf(t.id);
    if (!ch.length) return;
    let cy = y + NODEH + YGAP;
    for (let i = 0; i < ch.length; i += COLS) {
      const row = ch.slice(i, i + COLS);
      const rowW = row.reduce((a, c) => a + c.w, 0) + (row.length - 1) * XGAP;
      const rowH = Math.max(...row.map((c) => c.h));
      let cx = x + (t.w - rowW) / 2;
      for (const c of row) { place(c, cx, cy); cx += c.w + XGAP; }
      cy += rowH + ROWGAP;
    }
  };
  measure(byIdT["root"]); place(byIdT["root"], 0, 0);
  const totalW = byIdT["root"].w + 60;
  const totalH = byIdT["root"].h + 40;
  const idxOf: Record<string, number> = {}; tn.forEach((t, i) => (idxOf[t.id] = i));

  const onW = (e: React.WheelEvent) => { const f = e.deltaY < 0 ? 1.15 : 1 / 1.15; setQv((v) => ({ ...v, k: Math.max(0.2, Math.min(6, v.k * f)) })); };
  const onD = (e: React.PointerEvent) => { qdrag.current = { x: e.clientX, y: e.clientY, vx: qv.x, vy: qv.y }; };
  const onM = (e: React.PointerEvent) => { const d = qdrag.current; if (!d) return; const nx = d.vx + (e.clientX - d.x), ny = d.vy + (e.clientY - d.y); setQv((v) => ({ ...v, x: nx, y: ny })); };
  const onU = () => { qdrag.current = null; };

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <button onClick={() => setOpen(new Set(graph.systems.map((s) => s.name)))} className="text-xs px-2 py-1 rounded border border-gray-300">시스템 펼치기</button>
        <button onClick={() => setOpen(new Set())} className="text-xs px-2 py-1 rounded border border-gray-300">전체 접기</button>
        <button onClick={() => setOpen(new Set(graph.systems.filter((s) => nodes.some((n) => n.system === s.name && n.qa && n.qa !== "ok")).map((s) => s.name)))} className="text-xs px-2 py-1 rounded border border-rose-300 text-rose-600">이슈 시스템만</button>
        <button onClick={() => setQv({ k: 1, x: 0, y: 0 })} className="text-xs px-2 py-1 rounded border border-gray-300">맞춤(뷰 리셋)</button>
        <button onClick={() => setQv((v) => ({ ...v, k: Math.max(0.2, v.k / 1.3) }))} className="text-xs px-3 py-1 rounded border border-gray-300">－ 축소</button>
        <button onClick={() => setQv((v) => ({ ...v, k: Math.min(6, v.k * 1.3) }))} className="text-xs px-3 py-1 rounded border border-gray-300">＋ 확대</button>
      </div>

      <div className="rounded-xl border border-gray-800" style={{ background: "#141821", height: "calc(100vh - 230px)", overflow: "hidden" }}>
        <svg viewBox={`0 0 ${totalW} ${totalH}`} preserveAspectRatio="xMidYMid meet"
          style={{ width: "100%", height: "100%", display: "block", cursor: qdrag.current ? "grabbing" : "grab" }}
          onWheel={onW} onPointerDown={onD} onPointerMove={onM} onPointerUp={onU} onPointerLeave={onU}>
          <defs>
            <pattern id="qg" width="30" height="30" patternUnits="userSpaceOnUse"><path d="M30 0 L0 0 0 30" fill="none" stroke="#222633" strokeWidth="1" /></pattern>
          </defs>
          <g transform={`translate(${qv.x},${qv.y}) scale(${qv.k})`}>
            <rect x={-3000} y={-3000} width={totalW + 6000} height={totalH + 6000} fill="url(#qg)" />
            {links.map(([p, c], i) => {
              const a = byIdT[p], b = byIdT[c];
              if (!a || !b) return null;
              const sx = a.x + NODEW / 2, sy = a.y + NODEH, tx = b.x + NODEW / 2, ty = b.y;
              const mid = sy + Math.min(YGAP / 2, (ty - sy) / 2);
              return <path key={i} d={`M ${sx} ${sy} V ${mid} H ${tx} V ${ty}`} fill="none" stroke="#4a5263" strokeWidth={1.3} strokeOpacity={0.7} />;
            })}
            {tn.map((t) => (
              <g key={t.id} transform={`translate(${t.x},${t.y})`} style={{ cursor: "pointer" }}
                onClick={() => { if (t.tgl) toggle(t.tgl); else if (t.jump) onJump(t.jump); }}>
                <rect width={NODEW} height={NODEH} rx={8} fill="#1f2430" stroke={t.border} strokeWidth={t.border === "#3a4150" ? 1.4 : 2.8} />
                <text x={10} y={21} fontSize={13} fontWeight={700} fill="#e6e9ef">{t.icon} {t.label.length > 15 ? t.label.slice(0, 14) + "…" : t.label}</text>
                <text x={10} y={39} fontSize={10} fill="#9aa3b2">{t.sub}</text>
                <circle cx={NODEW - 13} cy={13} r={9} fill="#0d0f14" stroke={t.border} strokeWidth={1} />
                <text x={NODEW - 13} y={16.5} textAnchor="middle" fontSize={9} fill="#cfd5e0">{idxOf[t.id]}</text>
              </g>
            ))}
          </g>
        </svg>
      </div>
    </div>
  );
}
