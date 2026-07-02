"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "@/components/Icon";

// ──────────────────────────────────────────────────────────────
// BalloonFlow 시뮬레이터 — 클리어율 배치 분석 + 리플레이 뷰어
// 요청 → hermes 태스크(sim_params) → Mother watcher → 머신 B BalloonFlowSim 실행
// → bf_sim_results/bf_sim_replays → 이 페이지가 시각화. 모바일 대응.
// ──────────────────────────────────────────────────────────────

interface PendingTask { _id: string; title: string; status: string; created_at: string }
interface ResultDoc {
  _id: string;
  task_id: string;
  params: { levels: string; runs: number; policy: string; seed: number };
  summary: { levelCount: number; avgClearRate: number; below50Count: number; worstLevels: { levelId: number; clearRate: number }[] };
  replay_id?: string | null;
  replay_level?: number | null;
  created_at: string;
  results?: LevelResult[];
}
interface LevelResult {
  levelId: number; purpose: string; numColors: number; balloonCount: number; totalDarts: number;
  runs: number; clearRate: number; avgClearTime: number; failRailOverflow: number; failNoMoves: number;
  failTimeout: number; avgPeakOccupancy: number; avgDartsFired: number; avgDartsWasted: number; difficultyScore: number;
}
interface Replay {
  level: { id: number; policy: string; seed: number };
  world: { cx: number; cz: number; halfW: number; halfH: number; cell: number };
  palette: string[];
  railPath: [number, number][];
  closedLoop: boolean;
  balloons: [number, number, number, number, string, number][];
  frames: RFrame[];
  result: { cleared: boolean; failReason: string; simTime: number; popped: number; total: number };
}
interface RFrame {
  t: number; pop: number[]; reveal: number[]; mark: [number, string][];
  darts: [number, number, number, number][]; proj: [number, number, number][];
  holders: { col: number; more: number; entries: [number, number, number, string, string][] }[];
  colors: [number, number, number][];
  stat: { occ: number; cap: number; remain: number; fired: number; wasted: number; mag: number; deadlock: number; almost: number };
  log: string[];
}

const clearColor = (r: number) => (r >= 0.8 ? "var(--ok)" : r >= 0.5 ? "var(--warn)" : "var(--err)");

export default function SimulatorPage() {
  // ── 요청 폼 ──
  const [levels, setLevels] = useState("1-20");
  const [runs, setRuns] = useState(50);
  const [policy, setPolicy] = useState("smart");
  const [seed, setSeed] = useState(12345);
  const [withReplay, setWithReplay] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [toast, setToast] = useState("");

  // ── 목록/상세 ──
  const [pending, setPending] = useState<PendingTask[]>([]);
  const [list, setList] = useState<ResultDoc[]>([]);
  const [detail, setDetail] = useState<ResultDoc | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const d = await (await fetch("/api/sim")).json();
      setPending(d.pending || []);
      setList(d.results || []);
    } catch { /* 네트워크 오류 무시 */ }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 10_000);   // 진행중 태스크 폴링
    return () => clearInterval(t);
  }, [refresh]);

  const submit = async () => {
    setSubmitting(true);
    try {
      const res = await fetch("/api/sim", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ levels, runs, policy, seed, replay: withReplay }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error || res.statusText);
      setToast("요청 등록됨 — Hermes가 머신 B에서 실행 후 결과가 아래에 나타납니다");
      refresh();
    } catch (e) {
      setToast("요청 실패: " + (e as Error).message);
    }
    setSubmitting(false);
    setTimeout(() => setToast(""), 6000);
  };

  const openDetail = async (id: string) => {
    setLoadingDetail(true);
    try {
      const d = await (await fetch(`/api/sim/results/${id}`)).json();
      setDetail(d);
    } catch { /* noop */ }
    setLoadingDetail(false);
  };

  return (
    <div className="space-y-5">
      {/* 헤더 */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-2">
        <div>
          <div className="text-[11px] mono tracking-hud neon-text-soft">BALLOONFLOW · CLEAR-RATE SIMULATOR</div>
          <h1 className="text-xl font-bold mt-0.5">시뮬레이터</h1>
          <p className="text-[12px] mt-1" style={{ color: "var(--text-dim)" }}>
            Git 레벨 데이터 기준 n회 몬테카를로 — 클리어율·실패 사유·난이도를 산출하고 리플레이로 판을 직접 확인
          </p>
        </div>
        <button onClick={refresh} className="glass glass-hover rounded-xl px-3 py-2 text-[12px] self-start sm:self-auto" style={{ color: "var(--text-dim)" }}>
          <Icon name="search" size={13} /> <span className="ml-1">새로고침</span>
        </button>
      </div>

      {/* 요청 폼 */}
      <section className="glass rounded-2xl p-4 sm:p-5">
        <div className="text-[12px] mono tracking-hud mb-3" style={{ color: "var(--text-dim)" }}>NEW SIMULATION</div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 items-end">
          <label className="block col-span-2 sm:col-span-1">
            <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>레벨 범위</span>
            <input value={levels} onChange={(e) => setLevels(e.target.value)} placeholder="1-20, 45"
              className="mt-1 w-full rounded-xl px-3 py-2 text-sm bg-transparent border" style={{ borderColor: "var(--line)" }} />
          </label>
          <label className="block">
            <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>시행 횟수 (n)</span>
            <input type="number" value={runs} min={1} max={200} onChange={(e) => setRuns(parseInt(e.target.value) || 50)}
              className="mt-1 w-full rounded-xl px-3 py-2 text-sm bg-transparent border" style={{ borderColor: "var(--line)" }} />
          </label>
          <label className="block">
            <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>정책 (유저 모델)</span>
            <select value={policy} onChange={(e) => setPolicy(e.target.value)}
              className="mt-1 w-full rounded-xl px-3 py-2 text-sm border bg-[var(--panel-solid)]" style={{ borderColor: "var(--line)" }}>
              <option value="smart">smart (상급)</option>
              <option value="greedy">greedy (중급)</option>
              <option value="random">random (하급)</option>
            </select>
          </label>
          <label className="block">
            <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>시드</span>
            <input type="number" value={seed} onChange={(e) => setSeed(parseInt(e.target.value) || 12345)}
              className="mt-1 w-full rounded-xl px-3 py-2 text-sm bg-transparent border" style={{ borderColor: "var(--line)" }} />
          </label>
          <label className="flex items-center gap-2 pb-2.5 text-[12px]" style={{ color: "var(--text-dim)" }}>
            <input type="checkbox" checked={withReplay} onChange={(e) => setWithReplay(e.target.checked)} className="accent-cyan-400" />
            최난 레벨 리플레이
          </label>
          <button onClick={submit} disabled={submitting}
            className="rounded-xl px-4 py-2.5 text-sm font-bold transition-all disabled:opacity-50"
            style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018", boxShadow: "0 0 18px -4px rgba(34,211,238,.6)" }}>
            {submitting ? "등록 중…" : "시뮬 요청"}
          </button>
        </div>
        {toast && <div className="mt-3 text-[12px] neon-text-soft">{toast}</div>}
        <div className="mt-2 text-[11px]" style={{ color: "var(--text-faint)" }}>
          요청은 Hermes 태스크로 등록되어 Mother → 머신 B(BalloonFlowSim)에서 실행됩니다. 작업 보드에서도 진행 상황 확인 가능.
        </div>
      </section>

      {/* 진행중 */}
      {pending.length > 0 && (
        <section className="glass rounded-2xl p-4">
          <div className="text-[12px] mono tracking-hud mb-2" style={{ color: "var(--text-dim)" }}>RUNNING</div>
          <div className="flex flex-wrap gap-2">
            {pending.map((t) => (
              <span key={t._id} className="rounded-full px-3 py-1.5 text-[12px] border animate-pulse"
                style={{ borderColor: "var(--line-strong)", color: "var(--neon-soft)" }}>
                <Icon name="zap" size={12} /> {t.title.replace("🎯 ", "")} · {t.status}
              </span>
            ))}
          </div>
        </section>
      )}

      {/* 결과 목록 */}
      <section>
        <div className="text-[12px] mono tracking-hud mb-2" style={{ color: "var(--text-dim)" }}>RESULTS</div>
        {list.length === 0 && (
          <div className="glass rounded-2xl p-6 text-center text-[13px]" style={{ color: "var(--text-faint)" }}>
            아직 결과 없음 — 위에서 시뮬을 요청하면 완료 후 여기 표시됩니다
          </div>
        )}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {list.map((r) => {
            const avg = r.summary?.avgClearRate ?? 0;
            return (
              <button key={r._id} onClick={() => openDetail(r._id)}
                className="glass glass-hover rounded-2xl p-4 text-left transition-all"
                style={detail?._id === r._id ? { borderColor: "var(--line-strong)", boxShadow: "0 0 20px -8px rgba(34,211,238,.5)" } : undefined}>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-bold">레벨 {r.params.levels} <span className="mono text-[11px]" style={{ color: "var(--text-dim)" }}>×{r.params.runs} · {r.params.policy}</span></span>
                  <span className="text-lg font-bold mono" style={{ color: clearColor(avg) }}>{(avg * 100).toFixed(0)}%</span>
                </div>
                <div className="mt-2 h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(56,189,248,.1)" }}>
                  <div className="h-full rounded-full" style={{ width: `${avg * 100}%`, background: clearColor(avg) }} />
                </div>
                <div className="mt-2 flex items-center justify-between text-[11px]" style={{ color: "var(--text-dim)" }}>
                  <span>{r.summary?.levelCount}레벨 · 50%↓ <b style={{ color: r.summary?.below50Count ? "var(--err)" : "var(--ok)" }}>{r.summary?.below50Count}개</b></span>
                  <span>{(r.created_at || "").slice(5, 16).replace("T", " ")}</span>
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {/* 상세 */}
      {loadingDetail && <div className="text-center text-[13px] py-4" style={{ color: "var(--text-dim)" }}>불러오는 중…</div>}
      {detail && !loadingDetail && <DetailView doc={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
function DetailView({ doc, onClose }: { doc: ResultDoc; onClose: () => void }) {
  const [showReplay, setShowReplay] = useState(false);
  const rows = doc.results || [];
  return (
    <section className="glass rounded-2xl p-4 sm:p-5">
      <div className="flex items-center justify-between mb-3">
        <div>
          <div className="text-[12px] mono tracking-hud" style={{ color: "var(--text-dim)" }}>DETAIL</div>
          <h2 className="text-base font-bold">레벨 {doc.params.levels} × {doc.params.runs}회 · {doc.params.policy} · 시드 {doc.params.seed}</h2>
        </div>
        <div className="flex gap-2">
          {doc.replay_id && (
            <button onClick={() => setShowReplay((v) => !v)}
              className="rounded-xl px-3 py-2 text-[12px] font-bold"
              style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018" }}>
              <Icon name="play" size={12} /> L{doc.replay_level} 리플레이
            </button>
          )}
          <button onClick={onClose} className="glass glass-hover rounded-xl px-3 py-2 text-[12px]" style={{ color: "var(--text-dim)" }}>
            <Icon name="x" size={12} />
          </button>
        </div>
      </div>

      {showReplay && doc.replay_id && <ReplayViewer resultId={doc._id} />}

      {/* 레벨별 테이블 (모바일: 가로 스크롤) */}
      <div className="overflow-x-auto mt-3">
        <table className="w-full text-[12px] min-w-[760px]">
          <thead>
            <tr className="text-left mono text-[10px] tracking-hud" style={{ color: "var(--text-faint)" }}>
              <th className="py-2 pr-2">LV</th><th className="pr-2">의도</th><th className="pr-2">색</th>
              <th className="pr-2">풍선</th><th className="pr-2">다트</th>
              <th className="pr-2 w-48">클리어율</th>
              <th className="pr-2">실패 만석/소진/교착</th>
              <th className="pr-2">시간</th><th className="pr-2">점유</th><th className="pr-2">난이도</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const hard = r.difficultyScore >= 70;
              return (
                <tr key={r.levelId} className="border-t" style={{ borderColor: "var(--line)", background: hard ? "rgba(251,90,107,.07)" : undefined }}>
                  <td className="py-1.5 pr-2 font-bold">L{r.levelId}</td>
                  <td className="pr-2" style={{ color: "var(--text-dim)" }}>{r.purpose}</td>
                  <td className="pr-2">{r.numColors}</td>
                  <td className="pr-2">{r.balloonCount}</td>
                  <td className="pr-2">{r.totalDarts}</td>
                  <td className="pr-2">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-2 rounded-full overflow-hidden min-w-[70px]" style={{ background: "rgba(56,189,248,.1)" }}>
                        <div className="h-full rounded-full" style={{ width: `${r.clearRate * 100}%`, background: clearColor(r.clearRate) }} />
                      </div>
                      <span className="mono w-10 text-right" style={{ color: clearColor(r.clearRate) }}>{Math.round(r.clearRate * 100)}%</span>
                    </div>
                  </td>
                  <td className="pr-2 mono">
                    <span style={{ color: "var(--err)" }}>{r.failRailOverflow}</span>/
                    <span style={{ color: "var(--warn)" }}>{r.failNoMoves}</span>/
                    <span style={{ color: "var(--violet)" }}>{r.failTimeout}</span>
                  </td>
                  <td className="pr-2">{r.avgClearTime ? `${r.avgClearTime}s` : "—"}</td>
                  <td className="pr-2">{Math.round(r.avgPeakOccupancy * 100)}%</td>
                  <td className="pr-2 font-bold" style={{ color: hard ? "var(--err)" : undefined }}>{r.difficultyScore}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="mt-2 text-[11px]" style={{ color: "var(--text-faint)" }}>
        실패 사유 — <span style={{ color: "var(--err)" }}>만석</span>: 못 쏘는 색이 레일 점유(색 밸런스/순서) ·{" "}
        <span style={{ color: "var(--warn)" }}>소진</span>: 다트 총량 부족 ·{" "}
        <span style={{ color: "var(--violet)" }}>교착</span>: 안전한 수 없음(구조 문제) · 난이도 70↑ 행 강조 = 점검 후보
      </div>
    </section>
  );
}

// ──────────────────────────────────────────────────────────────
// 리플레이 캔버스 플레이어 — 보드/레일/비행다트/홀더 큐, 시크/배속 (터치 대응)
function ReplayViewer({ resultId }: { resultId: string }) {
  const [replay, setReplay] = useState<Replay | null>(null);
  const [err, setErr] = useState("");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef<Map<number, { x: number; z: number; c: number; mark: string; concealed: boolean; popped: boolean }>>(new Map());
  const frameRef = useRef(0);
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  const accumRef = useRef(0);
  const lastTsRef = useRef(0);
  const [, force] = useState(0);

  useEffect(() => {
    fetch(`/api/sim/results/${resultId}?replay=1`)
      .then(async (r) => { if (!r.ok) throw new Error((await r.json()).error || r.statusText); return r.json(); })
      .then((d: Replay) => { setReplay(d); })
      .catch((e) => setErr(String(e.message || e)));
  }, [resultId]);

  const resetState = useCallback((rep: Replay) => {
    const m = new Map();
    for (const [id, x, z, c, mark, con] of rep.balloons) m.set(id, { x, z, c, mark, concealed: !!con, popped: false });
    stateRef.current = m;
  }, []);

  const applyFrame = useCallback((f: RFrame) => {
    const m = stateRef.current;
    for (const id of f.pop) { const b = m.get(id); if (b) b.popped = true; }
    for (const id of f.reveal) { const b = m.get(id); if (b) b.concealed = false; }
    for (const [id, mark] of f.mark) { const b = m.get(id); if (b) b.mark = mark; }
  }, []);

  const rebuildTo = useCallback((rep: Replay, idx: number) => {
    resetState(rep);
    for (let i = 0; i <= idx && i < rep.frames.length; i++) applyFrame(rep.frames[i]);
    frameRef.current = Math.min(idx, rep.frames.length - 1);
  }, [resetState, applyFrame]);

  const render = useCallback(() => {
    const rep = replay, canvas = canvasRef.current;
    if (!rep || !canvas) return;
    const f = rep.frames[frameRef.current];
    const dpr = window.devicePixelRatio || 1;
    const W = canvas.clientWidth, H = Math.round(W * 1.35);
    if (canvas.width !== W * dpr) { canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.height = `${H}px`; }
    const ctx = canvas.getContext("2d")!;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#070d18";
    ctx.fillRect(0, 0, W, H);

    const boardH = H * 0.74, holderY = H * 0.75;
    const w = rep.world;
    const scale = Math.min((W - 14) / (w.halfW * 2), (boardH - 14) / (w.halfH * 2));
    const X = (x: number) => W / 2 + (x - w.cx) * scale;
    const Y = (z: number) => boardH / 2 - (z - w.cz) * scale;

    // 레일
    ctx.strokeStyle = "rgba(56,189,248,.25)";
    ctx.lineWidth = Math.max(3, scale * 0.5);
    ctx.lineJoin = "round";
    ctx.beginPath();
    rep.railPath.forEach(([x, z], i) => (i ? ctx.lineTo(X(x), Y(z)) : ctx.moveTo(X(x), Y(z))));
    if (rep.closedLoop) ctx.closePath();
    ctx.stroke();

    // 풍선
    const r = Math.max(1.2, w.cell * scale * 0.48);
    const showMark = r >= 6;
    ctx.font = `bold ${Math.max(7, r * 0.85)}px ui-monospace, monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const b of stateRef.current.values()) {
      if (b.popped) continue;
      const px = X(b.x), py = Y(b.z);
      let fill = b.concealed ? "#4b5563" : rep.palette[b.c] || "#f0f";
      if (b.mark.startsWith("I")) fill = "#96c8eb";
      ctx.fillStyle = fill;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();
      const mk = b.concealed ? "?" : b.mark;
      if (mk && showMark) { ctx.fillStyle = "#000"; ctx.fillText(mk, px, py); }
    }
    // 다트/발사체
    for (const [c, x, z, head] of f.darts) {
      ctx.fillStyle = rep.palette[c] || "#f0f";
      ctx.beginPath(); ctx.arc(X(x), Y(z), 3.5, 0, Math.PI * 2); ctx.fill();
      if (head) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 1; ctx.stroke(); }
    }
    for (const [c, x, z] of f.proj) {
      ctx.fillStyle = rep.palette[c] || "#f0f";
      ctx.beginPath(); ctx.arc(X(x), Y(z), 4, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = "#fde047"; ctx.lineWidth = 1.3; ctx.stroke();
    }
    // 홀더 스트립
    ctx.fillStyle = "rgba(12,20,36,.85)";
    ctx.fillRect(0, holderY, W, H - holderY);
    ctx.font = "9px ui-monospace, monospace";
    ctx.textAlign = "left";
    const colW = (W - 10) / Math.max(1, f.holders.length);
    for (const hc of f.holders) {
      const x0 = 5 + hc.col * colW;
      let y0 = holderY + 5;
      for (const [, c, mag, state, tags] of hc.entries) {
        const fill = tags.includes("?") ? "#4b5563" : rep.palette[c] || "#888";
        ctx.fillStyle = fill;
        ctx.fillRect(x0, y0, colW - 5, 15);
        const bright = parseInt(fill.slice(1, 3), 16) * 0.45 + parseInt(fill.slice(3, 5), 16) * 0.5;
        ctx.fillStyle = bright > 105 ? "#000" : "#fff";
        const st = state === "deploy" ? "▶" : state === "wait" ? "◇" : "";
        ctx.fillText(`${st}c${c}×${mag}${tags}`, x0 + 2, y0 + 8, colW - 9);
        y0 += 18;
      }
      if (hc.more > 0) { ctx.fillStyle = "#5a6f8c"; ctx.fillText(`+${hc.more}`, x0 + 2, y0 + 7); }
    }
    force((v) => v + 1);   // HUD 텍스트 리렌더
  }, [replay]);

  // 초기화 + 재생 루프
  useEffect(() => {
    if (!replay) return;
    rebuildTo(replay, 0);
    render();
    let raf = 0;
    const tickFn = (ts: number) => {
      if (playingRef.current) {
        if (!lastTsRef.current) lastTsRef.current = ts;
        accumRef.current += ((ts - lastTsRef.current) / 1000) * speedRef.current;
        lastTsRef.current = ts;
        let changed = false;
        while (accumRef.current >= 0.1) {
          accumRef.current -= 0.1;
          if (frameRef.current >= replay.frames.length - 1) { playingRef.current = false; break; }
          frameRef.current++;
          applyFrame(replay.frames[frameRef.current]);
          changed = true;
        }
        if (changed) render();
      } else lastTsRef.current = ts;
      raf = requestAnimationFrame(tickFn);
    };
    raf = requestAnimationFrame(tickFn);
    const onResize = () => render();
    window.addEventListener("resize", onResize);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); };
  }, [replay, rebuildTo, render, applyFrame]);

  if (err) return <div className="text-[12px] py-3" style={{ color: "var(--err)" }}>리플레이 로드 실패: {err}</div>;
  if (!replay) return <div className="text-[12px] py-3" style={{ color: "var(--text-dim)" }}>리플레이 로드 중…</div>;

  const f = replay.frames[frameRef.current];
  const occPct = f.stat.cap > 0 ? Math.round((f.stat.occ / f.stat.cap) * 100) : 0;
  return (
    <div className="rounded-2xl border p-3 mb-2" style={{ borderColor: "var(--line)", background: "rgba(6,11,22,.5)" }}>
      {/* 컨트롤 — 모바일 터치 크기 */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <button onClick={() => { playingRef.current = !playingRef.current; lastTsRef.current = 0; force((v) => v + 1); }}
          className="w-10 h-10 rounded-xl font-bold" style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018" }}>
          <Icon name={playingRef.current ? "x" : "play"} size={14} />
        </button>
        <select defaultValue="1" onChange={(e) => { speedRef.current = parseFloat(e.target.value); }}
          className="rounded-xl px-2 py-2 text-[12px] border bg-[var(--panel-solid)]" style={{ borderColor: "var(--line)" }}>
          <option value="0.5">x0.5</option><option value="1">x1</option><option value="2">x2</option>
          <option value="4">x4</option><option value="10">x10</option>
        </select>
        <input type="range" min={0} max={replay.frames.length - 1} value={frameRef.current}
          onChange={(e) => { playingRef.current = false; rebuildTo(replay, parseInt(e.target.value)); render(); }}
          className="flex-1 min-w-[120px] accent-cyan-400" />
        <span className="mono text-[11px] w-24 text-right" style={{ color: "var(--text-dim)" }}>
          {f.t.toFixed(1)}s / {replay.frames[replay.frames.length - 1].t.toFixed(1)}s
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <canvas ref={canvasRef} className="w-full rounded-xl lg:col-span-2" style={{ touchAction: "none" }} />
        <div className="space-y-2 text-[12px]">
          <div className="rounded-xl border p-3" style={{ borderColor: "var(--line)" }}>
            <div className="font-bold mb-1">L{replay.level.id} · {replay.level.policy} · 시드 {replay.level.seed}</div>
            <div style={{ color: "var(--text-dim)" }}>잔여 풍선 <b style={{ color: "var(--text)" }}>{f.stat.remain}</b> · 발사 {f.stat.fired} · 매거진 {f.stat.mag}</div>
            <div className="mt-1" style={{ color: "var(--text-dim)" }}>레일 점유 <b style={{ color: occPct > 90 ? "var(--err)" : occPct > 75 ? "var(--warn)" : "var(--ok)" }}>{f.stat.occ}/{f.stat.cap} ({occPct}%)</b></div>
            <div className="mt-1 h-1.5 rounded-full overflow-hidden" style={{ background: "rgba(56,189,248,.1)" }}>
              <div className="h-full" style={{ width: `${Math.min(100, occPct)}%`, background: occPct > 90 ? "var(--err)" : occPct > 75 ? "var(--warn)" : "var(--ok)" }} />
            </div>
            {f.stat.deadlock >= 0 && <div className="mt-1 font-bold" style={{ color: "var(--warn)" }}>⚠ 데드락 모드</div>}
            {f.stat.almost === 1 && <div className="mt-1 font-bold" style={{ color: "var(--ok)" }}>★ Almost There (1.8×)</div>}
          </div>
          <div className="rounded-xl border p-3" style={{ borderColor: "var(--line)" }}>
            <div className="mono text-[10px] tracking-hud mb-1.5" style={{ color: "var(--text-faint)" }}>색별 노출 / 레일 재고</div>
            {f.colors.map(([c, exp, sup]) => {
              const dead = sup > 0 && exp === 0;
              return (
                <div key={c} className="flex items-center gap-2 py-0.5" style={{ color: dead ? "var(--err)" : "var(--text-dim)" }}>
                  <span className="w-3 h-3 rounded-sm border border-black/40 shrink-0" style={{ background: replay.palette[c] }} />
                  <span className="mono">c{c} 노출{exp} 레일{sup}{dead ? " ← 죽은 다트" : ""}</span>
                </div>
              );
            })}
          </div>
          <div className="rounded-xl border p-3" style={{ borderColor: "var(--line)" }}>
            <div className="mono text-[10px] tracking-hud mb-1" style={{ color: "var(--text-faint)" }}>결과</div>
            <div style={{ color: replay.result.cleared ? "var(--ok)" : "var(--err)" }}>
              {replay.result.cleared ? "클리어" : `실패 (${replay.result.failReason})`} · {replay.result.simTime}s · 팝 {replay.result.popped}/{replay.result.total}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
