"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
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
  replays?: Record<string, string>;   // 레벨별 온디맨드 리플레이 (level → bf_sim_replays id)
  created_at: string;
  results?: LevelResult[];
}
interface LevelResult {
  levelId: number; purpose: string; numColors: number; balloonCount: number; totalDarts: number;
  runs: number; clearRate: number; targetClearRate?: number; avgClearTime: number; failRailOverflow: number; failNoMoves: number;
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

  // 첫 진입 시 최신 결과 자동 선택 — 빈 화면 대신 바로 대시보드
  useEffect(() => {
    if (!detail && !loadingDetail && list.length > 0) openDetail(list[0]._id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [list]);

  // 리플레이 생성 대기 중 조용한 갱신 (로딩 표시 없이 — 선택 상태 유지)
  const refetchDetail = useCallback(async () => {
    setDetail((cur) => {
      if (cur) {
        fetch(`/api/sim/results/${cur._id}`)
          .then((r) => r.json())
          .then((d) => setDetail((now) => (now && now._id === cur._id ? d : now)))
          .catch(() => { /* noop */ });
      }
      return cur;
    });
  }, []);

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

      {/* 좌: 분석 대시보드 / 우: 요청 폼 + 결과 히스토리 (모바일: 폼 먼저) */}
      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px] gap-4 items-start">
        <div className="space-y-4 min-w-0 order-2 lg:order-1">
          {/* 진행중 */}
          {pending.length > 0 && (
            <section className="glass rounded-2xl p-3">
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

          {loadingDetail && !detail && (
            <div className="glass rounded-2xl p-8 text-center text-[13px]" style={{ color: "var(--text-dim)" }}>불러오는 중…</div>
          )}
          {!detail && !loadingDetail && (
            <div className="glass rounded-2xl p-8 text-center text-[13px]" style={{ color: "var(--text-faint)" }}>
              아직 결과 없음 — 우측에서 시뮬을 요청하면 완료 후 여기 표시됩니다
            </div>
          )}
          {detail && (
            <DetailView key={detail._id} doc={detail} others={list} onRefetch={refetchDetail} />
          )}
        </div>

        <aside className="space-y-4 min-w-0 order-1 lg:order-2 lg:sticky lg:top-4">
          {/* 요청 폼 */}
          <section className="glass rounded-2xl p-4">
            <div className="text-[12px] mono tracking-hud mb-3" style={{ color: "var(--text-dim)" }}>NEW SIMULATION</div>
            <div className="grid grid-cols-2 gap-3">
              <label className="block col-span-2">
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
                <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>시드</span>
                <input type="number" value={seed} onChange={(e) => setSeed(parseInt(e.target.value) || 12345)}
                  className="mt-1 w-full rounded-xl px-3 py-2 text-sm bg-transparent border" style={{ borderColor: "var(--line)" }} />
              </label>
              <label className="block col-span-2">
                <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>정책 (유저 모델)</span>
                <select value={policy} onChange={(e) => setPolicy(e.target.value)}
                  className="mt-1 w-full rounded-xl px-3 py-2 text-sm border bg-[var(--panel-solid)]" style={{ borderColor: "var(--line)" }}>
                  <option value="smart">smart (상급)</option>
                  <option value="greedy">greedy (중급)</option>
                  <option value="random">random (하급)</option>
                </select>
              </label>
              <label className="flex items-center gap-2 text-[12px] col-span-2" style={{ color: "var(--text-dim)" }}>
                <input type="checkbox" checked={withReplay} onChange={(e) => setWithReplay(e.target.checked)} className="accent-cyan-400" />
                최난 레벨 리플레이
              </label>
              <button onClick={submit} disabled={submitting}
                className="col-span-2 rounded-xl px-4 py-2.5 text-sm font-bold transition-all disabled:opacity-50"
                style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018", boxShadow: "0 0 18px -4px rgba(34,211,238,.6)" }}>
                {submitting ? "등록 중…" : "시뮬 요청"}
              </button>
            </div>
            {toast && <div className="mt-3 text-[12px] neon-text-soft">{toast}</div>}
            <div className="mt-2 text-[11px]" style={{ color: "var(--text-faint)" }}>
              Hermes → 머신 B(BalloonFlowSim) 실행. 작업 보드에서도 진행 확인 가능.
            </div>
          </section>

          {/* 결과 히스토리 */}
          <section className="glass rounded-2xl p-4">
            <div className="text-[12px] mono tracking-hud mb-2" style={{ color: "var(--text-dim)" }}>RESULTS</div>
            {list.length === 0 && (
              <div className="text-[12px] py-3 text-center" style={{ color: "var(--text-faint)" }}>아직 결과 없음</div>
            )}
            <div className="space-y-1.5 max-h-[420px] overflow-y-auto pr-1">
              {list.map((r) => {
                const avg = r.summary?.avgClearRate ?? 0;
                const active = detail?._id === r._id;
                return (
                  <button key={r._id} onClick={() => openDetail(r._id)}
                    className="w-full rounded-xl px-3 py-2 text-left border transition-all hover:bg-[rgba(56,189,248,.06)]"
                    style={{
                      borderColor: active ? "var(--line-strong)" : "transparent",
                      background: active ? "rgba(34,211,238,.08)" : undefined,
                    }}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[12px] font-bold truncate">레벨 {r.params.levels}</span>
                      <span className="mono text-[12px] font-bold shrink-0" style={{ color: clearColor(avg) }}>{(avg * 100).toFixed(0)}%</span>
                    </div>
                    <div className="flex items-center justify-between text-[10px] mt-0.5" style={{ color: "var(--text-faint)" }}>
                      <span>×{r.params.runs} · {r.params.policy} · 50%↓ {r.summary?.below50Count ?? 0}</span>
                      <span>{(r.created_at || "").slice(5, 16).replace("T", " ")}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// memo: 부모 리렌더에서 대형 콘텐츠 리렌더 최소화
const DetailView = memo(function DetailView({ doc, others, onRefetch }: { doc: ResultDoc; others: ResultDoc[]; onRefetch: () => void }) {
  const [tab, setTab] = useState<"chart" | "fails" | "table">("chart");
  const [compareId, setCompareId] = useState("");
  const [compareDoc, setCompareDoc] = useState<ResultDoc | null>(null);
  const [selLevel, setSelLevel] = useState<number | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [waitSecs, setWaitSecs] = useState(0);
  const [genErr, setGenErr] = useState("");
  const waitStartRef = useRef(0);
  const waitTaskRef = useRef<string | null>(null);
  const rows = doc.results || [];

  // 해당 레벨의 리플레이 id (온디맨드 맵 → 레거시 최난 레벨 순)
  const replayIdFor = (lvl: number | null) =>
    lvl == null ? null
      : doc.replays?.[String(lvl)] || (doc.replay_level === lvl ? doc.replay_id : null) || null;

  // 생성 대기 폴링 — doc 갱신으로 리플레이가 연결되면 자동 종료.
  // 태스크 상태도 함께 폴링해 실패(⚠️ 코멘트)를 즉시 노출 — 조용히 4분 기다리다 타임아웃 금지.
  useEffect(() => {
    if (!waiting) return;
    if (replayIdFor(selLevel)) { setWaiting(false); return; }
    const t = setInterval(async () => {
      const elapsed = Date.now() - waitStartRef.current;
      setWaitSecs(Math.round(elapsed / 1000));
      if (waitTaskRef.current) {
        try {
          const s = await (await fetch(`/api/sim/replay?task_id=${waitTaskRef.current}`)).json();
          if (s.failed) {
            setWaiting(false);
            setGenErr(s.message || "생성 실패 — 작업 보드에서 태스크를 확인하세요");
            return;
          }
        } catch { /* 상태 조회 실패는 무시하고 계속 대기 */ }
      }
      if (elapsed > 600_000) {
        setWaiting(false);
        setGenErr("생성 시간 초과(10분) — 작업 보드에서 리플레이 태스크 상태를 확인하세요");
      } else onRefetch();
    }, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waiting, doc, selLevel]);

  const requestReplay = async (lvl: number) => {
    setGenErr("");
    try {
      const res = await fetch("/api/sim/replay", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result_id: doc._id, level: lvl }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error || res.statusText);
      if (d.ready) { onRefetch(); return; }
      waitTaskRef.current = d.task_id || null;
      waitStartRef.current = Date.now();
      setWaitSecs(0);
      setWaiting(true);
    } catch (e) {
      setGenErr("요청 실패: " + (e as Error).message);
    }
  };

  const selectLevel = (lvl: number) => {
    setGenErr("");
    setSelLevel((cur) => (cur === lvl ? null : lvl));
  };

  // 비교 대상 결과 로드 (레벨별 delta)
  useEffect(() => {
    if (!compareId) { setCompareDoc(null); return; }
    let alive = true;
    fetch(`/api/sim/results/${compareId}`)
      .then((r) => r.json())
      .then((d) => { if (alive) setCompareDoc(d); })
      .catch(() => { /* noop */ });
    return () => { alive = false; };
  }, [compareId]);

  // KPI 산출
  const worst = rows.length ? rows.reduce((a, b) => (b.clearRate < a.clearRate ? b : a)) : null;
  const belowTarget = rows.filter((r) => (r.targetClearRate ?? 0) > 0 && r.clearRate < r.targetClearRate!).length;
  const hasTargets = rows.some((r) => (r.targetClearRate ?? 0) > 0);
  const cmpAvg = compareDoc?.summary?.avgClearRate;
  const avgDelta = cmpAvg != null ? (doc.summary?.avgClearRate ?? 0) - cmpAvg : null;

  const compareMap = (() => {
    if (!compareDoc?.results) return null;
    const m = new Map<number, LevelResult>();
    for (const r of compareDoc.results) m.set(r.levelId, r);
    return m;
  })();

  return (
    <section className="glass rounded-2xl p-4 sm:p-5">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <div>
          <div className="text-[12px] mono tracking-hud" style={{ color: "var(--text-dim)" }}>DETAIL</div>
          <h2 className="text-base font-bold">레벨 {doc.params.levels} × {doc.params.runs}회 · {doc.params.policy} · 시드 {doc.params.seed}</h2>
        </div>
        <div className="flex items-center gap-2">
          {/* 결과 비교 — 시뮬 로직/레벨데이터 변경 전후 대조 */}
          <select value={compareId} onChange={(e) => setCompareId(e.target.value)}
            className="rounded-xl px-2 py-2 text-[11px] border bg-[var(--panel-solid)] max-w-[220px]"
            style={{ borderColor: "var(--line)", color: "var(--text-dim)" }}>
            <option value="">비교 안 함</option>
            {others.filter((o) => o._id !== doc._id).map((o) => (
              <option key={o._id} value={o._id}>
                vs 레벨 {o.params.levels} ×{o.params.runs} · {(o.created_at || "").slice(5, 16).replace("T", " ")}
              </option>
            ))}
          </select>
          {doc.replay_id && doc.replay_level != null && (
            <button onClick={() => selectLevel(doc.replay_level!)}
              className="rounded-xl px-3 py-2 text-[12px] font-bold shrink-0"
              style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018" }}>
              <Icon name="play" size={12} /> L{doc.replay_level} 리플레이
            </button>
          )}
        </div>
      </div>

      {/* KPI 요약 스트립 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        <div className="rounded-xl border p-3" style={{ borderColor: "var(--line)" }}>
          <div className="text-[10px] mono tracking-hud" style={{ color: "var(--text-faint)" }}>평균 클리어율</div>
          <div className="text-2xl font-bold mono mt-0.5" style={{ color: clearColor(doc.summary?.avgClearRate ?? 0) }}>
            {((doc.summary?.avgClearRate ?? 0) * 100).toFixed(1)}%
          </div>
          {avgDelta != null && (
            <div className="text-[11px] mono" style={{ color: avgDelta >= 0 ? "var(--ok)" : "var(--err)" }}>
              {avgDelta >= 0 ? "▲" : "▼"} {(Math.abs(avgDelta) * 100).toFixed(1)}pt vs 비교
            </div>
          )}
        </div>
        <div className="rounded-xl border p-3" style={{ borderColor: "var(--line)" }}>
          <div className="text-[10px] mono tracking-hud" style={{ color: "var(--text-faint)" }}>클리어율 50% 미만</div>
          <div className="text-2xl font-bold mono mt-0.5" style={{ color: (doc.summary?.below50Count ?? 0) > 0 ? "var(--err)" : "var(--ok)" }}>
            {doc.summary?.below50Count ?? 0}<span className="text-[12px]" style={{ color: "var(--text-dim)" }}> / {doc.summary?.levelCount}레벨</span>
          </div>
        </div>
        <div className="rounded-xl border p-3" style={{ borderColor: "var(--line)" }}>
          <div className="text-[10px] mono tracking-hud" style={{ color: "var(--text-faint)" }}>타깃 미달</div>
          <div className="text-2xl font-bold mono mt-0.5" style={{ color: belowTarget > 0 ? "var(--warn)" : "var(--ok)" }}>
            {hasTargets ? belowTarget : "—"}
            {hasTargets && <span className="text-[12px]" style={{ color: "var(--text-dim)" }}>개</span>}
          </div>
          {!hasTargets && <div className="text-[10px]" style={{ color: "var(--text-faint)" }}>타깃 미저작 데이터</div>}
        </div>
        <div className="rounded-xl border p-3" style={{ borderColor: "var(--line)" }}>
          <div className="text-[10px] mono tracking-hud" style={{ color: "var(--text-faint)" }}>최난 레벨</div>
          <div className="text-2xl font-bold mono mt-0.5">
            {worst ? <>L{worst.levelId} <span className="text-[13px]" style={{ color: clearColor(worst.clearRate) }}>{Math.round(worst.clearRate * 100)}%</span></> : "—"}
          </div>
          {worst && (
            <button onClick={() => selectLevel(worst.levelId)} className="text-[10px] underline" style={{ color: "var(--neon-soft)" }}>
              리플레이 보기
            </button>
          )}
        </div>
      </div>

      {/* 선택 레벨 리플레이 — 있으면 즉시 재생, 없으면 온디맨드 생성 */}
      {selLevel != null && (
        replayIdFor(selLevel) ? (
          <ReplayViewer key={selLevel} resultId={doc._id} level={selLevel} />
        ) : (
          <div className="rounded-2xl border p-4 mb-2 flex flex-wrap items-center gap-3"
            style={{ borderColor: "var(--line)", background: "rgba(6,11,22,.5)" }}>
            <span className="text-[13px] font-bold">L{selLevel}</span>
            {waiting ? (
              <span className="text-[12px] animate-pulse" style={{ color: "var(--neon-soft)" }}>
                <Icon name="zap" size={12} /> 리플레이 생성 중… {waitSecs}s — 머신 B 실행 후 자동 표시
                (다른 헤르메스 작업이 실행 중이면 대기열만큼 늦어질 수 있음)
              </span>
            ) : (
              <>
                <span className="text-[12px]" style={{ color: "var(--text-dim)" }}>이 레벨의 리플레이가 아직 없습니다</span>
                <button onClick={() => requestReplay(selLevel)}
                  className="rounded-xl px-3 py-2 text-[12px] font-bold"
                  style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018" }}>
                  <Icon name="play" size={12} /> 리플레이 생성 (동일 시드·정책)
                </button>
              </>
            )}
            {genErr && <span className="text-[12px]" style={{ color: "var(--err)" }}>{genErr}</span>}
          </div>
        )
      )}

      {/* 탭 — 차트 / 실패 분석 / 테이블 */}
      <div className="flex items-center gap-1 mt-1 mb-2">
        {([["chart", "레벨 차트"], ["fails", "실패 분석"], ["table", "테이블"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className="rounded-lg px-3 py-1.5 text-[12px] font-bold transition-colors"
            style={tab === k
              ? { background: "rgba(34,211,238,.14)", color: "var(--neon-soft)", border: "1px solid var(--line-strong)" }
              : { color: "var(--text-dim)", border: "1px solid transparent" }}>
            {label}
          </button>
        ))}
      </div>

      {tab === "chart" && (
        <>
          <LevelBarChart rows={rows} selLevel={selLevel} onSelect={selectLevel} compareMap={compareMap} />
          {compareMap && <CompareDeltaPanel rows={rows} compareMap={compareMap} onSelect={selectLevel} />}
        </>
      )}

      {tab === "fails" && <FailBreakdown rows={rows} onSelect={selectLevel} />}

      {/* 레벨별 테이블 (모바일: 가로 스크롤) */}
      {tab === "table" && (
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
              const sel = selLevel === r.levelId;
              const hasReplay = !!replayIdFor(r.levelId);
              return (
                <tr key={r.levelId} onClick={() => selectLevel(r.levelId)}
                  className="border-t cursor-pointer transition-colors hover:bg-[rgba(56,189,248,.06)]"
                  style={{
                    borderColor: sel ? "var(--line-strong)" : "var(--line)",
                    background: sel ? "rgba(34,211,238,.10)" : hard ? "rgba(251,90,107,.07)" : undefined,
                  }}>
                  <td className="py-1.5 pr-2 font-bold whitespace-nowrap">
                    L{r.levelId}
                    <span className="ml-1 align-middle" style={{ color: hasReplay ? "var(--neon-soft)" : "var(--text-faint)" }}>
                      <Icon name="play" size={10} />
                    </span>
                  </td>
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
      )}
      <div className="mt-2 text-[11px]" style={{ color: "var(--text-faint)" }}>
        <b style={{ color: "var(--text-dim)" }}>차트 막대/테이블 행 클릭 = 레벨 선택</b> → 리플레이 재생 (없으면 그 자리에서 생성) ·{" "}
        실패 사유 — <span style={{ color: "var(--err)" }}>만석</span>: 못 쏘는 색이 레일 점유(색 밸런스/순서) ·{" "}
        <span style={{ color: "var(--warn)" }}>소진</span>: 다트 총량 부족 ·{" "}
        <span style={{ color: "var(--violet)" }}>교착</span>: 안전한 수 없음(구조 문제)
      </div>
    </section>
  );
});

// ──────────────────────────────────────────────────────────────
// 레벨 차트 — 레벨별 클리어율 막대 (상태색 밴드) + 타깃 틱. 호버 툴팁, 클릭 = 레벨 선택.
function LevelBarChart({ rows, selLevel, onSelect, compareMap }: {
  rows: LevelResult[]; selLevel: number | null; onSelect: (lvl: number) => void;
  compareMap: Map<number, LevelResult> | null;
}) {
  const [hover, setHover] = useState<number | null>(null);   // rows 인덱스
  const wrapRef = useRef<HTMLDivElement>(null);

  const SLOT = 9, BAR = 7, H = 150, AXIS_B = 18, PAD_L = 34, PAD_R = 8, PAD_T = 8;
  const width = PAD_L + rows.length * SLOT + PAD_R;
  const height = PAD_T + H + AXIS_B;
  const y = (rate: number) => PAD_T + H * (1 - Math.max(0, Math.min(1, rate)));

  if (rows.length === 0) return <div className="text-[12px] py-4" style={{ color: "var(--text-faint)" }}>레벨 데이터 없음</div>;

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const idx = Math.floor((e.clientX - rect.left - PAD_L) / SLOT);
    setHover(idx >= 0 && idx < rows.length ? idx : null);
  };
  const hv = hover != null ? rows[hover] : null;
  const hvCmp = hv && compareMap ? compareMap.get(hv.levelId) : null;

  return (
    <div className="relative">
      <div ref={wrapRef} className="overflow-x-auto rounded-xl border" style={{ borderColor: "var(--line)", background: "rgba(6,11,22,.4)" }}>
        <svg width={width} height={height} onPointerMove={onMove} onPointerLeave={() => setHover(null)}
          onClick={() => { if (hover != null) onSelect(rows[hover].levelId); }}
          style={{ display: "block", cursor: "pointer" }}>
          {/* 그리드 + y축 라벨 (0/50/80/100%) */}
          {[0, 0.5, 0.8, 1].map((g) => (
            <g key={g}>
              <line x1={PAD_L} x2={width - PAD_R} y1={y(g)} y2={y(g)} stroke="rgba(219,230,245,.08)" strokeWidth={1} />
              <text x={PAD_L - 5} y={y(g) + 3} textAnchor="end" fontSize={9} fill="var(--text-faint)" fontFamily="ui-monospace, monospace">
                {Math.round(g * 100)}
              </text>
            </g>
          ))}
          {rows.map((r, i) => {
            const x = PAD_L + i * SLOT;
            const barY = y(r.clearRate);
            const barH = Math.max(1.5, PAD_T + H - barY);
            const sel = selLevel === r.levelId;
            const isHover = hover === i;
            return (
              <g key={r.levelId}>
                {isHover && <rect x={x - 1} y={PAD_T} width={SLOT} height={H} fill="rgba(56,189,248,.10)" />}
                {/* 막대: 상단 2px 라운드, 베이스라인 직각 */}
                <path
                  d={`M${x} ${PAD_T + H} L${x} ${barY + 2} Q${x} ${barY} ${x + 2} ${barY} L${x + BAR - 2} ${barY} Q${x + BAR} ${barY} ${x + BAR} ${barY + 2} L${x + BAR} ${PAD_T + H} Z`}
                  fill={clearColor(r.clearRate)}
                  opacity={sel || isHover ? 1 : 0.82}
                  stroke={sel ? "var(--neon)" : "none"} strokeWidth={sel ? 1.5 : 0}
                />
                {/* 타깃 틱 */}
                {(r.targetClearRate ?? 0) > 0 && (
                  <line x1={x - 1} x2={x + BAR + 1} y1={y(r.targetClearRate!)} y2={y(r.targetClearRate!)}
                    stroke="rgba(219,230,245,.75)" strokeWidth={1.2} />
                )}
                {/* x축 라벨 — 10레벨 간격 */}
                {(r.levelId % 10 === 0 || rows.length <= 25) && (
                  <text x={x + BAR / 2} y={PAD_T + H + 12} textAnchor="middle" fontSize={8.5}
                    fill="var(--text-faint)" fontFamily="ui-monospace, monospace">{r.levelId}</text>
                )}
              </g>
            );
          })}
        </svg>
      </div>
      {/* 캡션 — 색은 상태(클리어율 밴드), 흰 틱 = 타깃 */}
      <div className="mt-1.5 flex flex-wrap gap-3 text-[10px]" style={{ color: "var(--text-faint)" }}>
        <span><span className="inline-block w-2.5 h-2.5 rounded-sm align-middle mr-1" style={{ background: "var(--ok)" }} />80%↑</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded-sm align-middle mr-1" style={{ background: "var(--warn)" }} />50–80%</span>
        <span><span className="inline-block w-2.5 h-2.5 rounded-sm align-middle mr-1" style={{ background: "var(--err)" }} />50%↓</span>
        <span><span className="inline-block w-3 align-middle mr-1 border-t" style={{ borderColor: "rgba(219,230,245,.75)" }} />타깃 클리어율</span>
        <span>막대 클릭 = 레벨 선택(리플레이)</span>
      </div>
      {/* 툴팁 */}
      {hv && (
        <div className="absolute top-1 left-1/2 -translate-x-1/2 pointer-events-none rounded-lg border px-3 py-2 text-[11px] z-10"
          style={{ borderColor: "var(--line-strong)", background: "rgba(7,13,24,.95)" }}>
          <b className="text-[13px] mono">L{hv.levelId}</b>{" "}
          <b className="mono" style={{ color: clearColor(hv.clearRate) }}>{Math.round(hv.clearRate * 100)}%</b>
          {(hv.targetClearRate ?? 0) > 0 && <span style={{ color: "var(--text-dim)" }}> / 타깃 {Math.round(hv.targetClearRate! * 100)}%</span>}
          {hvCmp && (
            <b className="mono ml-1" style={{ color: hv.clearRate - hvCmp.clearRate >= 0 ? "var(--ok)" : "var(--err)" }}>
              {hv.clearRate - hvCmp.clearRate >= 0 ? "▲" : "▼"}{Math.abs((hv.clearRate - hvCmp.clearRate) * 100).toFixed(0)}pt
            </b>
          )}
          <div style={{ color: "var(--text-dim)" }}>
            {hv.purpose} · 실패 만석 {hv.failRailOverflow} / 소진 {hv.failNoMoves} / 교착 {hv.failTimeout} · 난이도 {hv.difficultyScore}
          </div>
        </div>
      )}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// 실패 분석 — 사유별 비중 스택바(의미색 + 라벨·수치 병기) + 실패 많은 레벨 목록
function FailBreakdown({ rows, onSelect }: { rows: LevelResult[]; onSelect: (lvl: number) => void }) {
  const CATS = [
    { key: "failRailOverflow" as const, name: "만석", color: "var(--err)", desc: "못 쏘는 색이 레일 점유 (색 밸런스/순서)" },
    { key: "failNoMoves" as const, name: "소진", color: "var(--warn)", desc: "다트 총량 부족" },
    { key: "failTimeout" as const, name: "교착", color: "var(--violet)", desc: "안전한 수 없음 (구조 문제)" },
  ];
  const totals = CATS.map((c) => rows.reduce((s, r) => s + (r[c.key] || 0), 0));
  const grand = totals.reduce((a, b) => a + b, 0);
  const failing = rows
    .map((r) => ({ r, fails: r.failRailOverflow + r.failNoMoves + r.failTimeout }))
    .filter((x) => x.fails > 0)
    .sort((a, b) => b.fails - a.fails)
    .slice(0, 12);

  if (grand === 0) {
    return <div className="rounded-xl border p-6 text-center text-[13px]" style={{ borderColor: "var(--line)", color: "var(--ok)" }}>
      실패 0건 — 모든 시행 클리어
    </div>;
  }
  const maxFails = failing[0]?.fails || 1;

  return (
    <div className="space-y-3">
      {/* 사유별 비중 (전체 실패 시행 대비) */}
      <div className="rounded-xl border p-3" style={{ borderColor: "var(--line)" }}>
        <div className="text-[10px] mono tracking-hud mb-2" style={{ color: "var(--text-faint)" }}>실패 사유 비중 — 총 {grand}회 실패</div>
        <div className="flex h-5 rounded-md overflow-hidden" style={{ background: "rgba(6,11,22,.6)" }}>
          {CATS.map((c, i) => totals[i] > 0 && (
            <div key={c.key} style={{ width: `${(totals[i] / grand) * 100}%`, background: c.color, marginRight: i < 2 ? 2 : 0 }} />
          ))}
        </div>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px]">
          {CATS.map((c, i) => (
            <span key={c.key} style={{ color: "var(--text-dim)" }}>
              <span className="inline-block w-2.5 h-2.5 rounded-sm align-middle mr-1" style={{ background: c.color }} />
              <b style={{ color: "var(--text)" }}>{c.name} {totals[i]}회 ({grand ? Math.round((totals[i] / grand) * 100) : 0}%)</b> — {c.desc}
            </span>
          ))}
        </div>
      </div>

      {/* 실패 많은 레벨 TOP — 클릭 = 리플레이 */}
      <div className="rounded-xl border p-3" style={{ borderColor: "var(--line)" }}>
        <div className="text-[10px] mono tracking-hud mb-2" style={{ color: "var(--text-faint)" }}>실패 많은 레벨 TOP {failing.length} (클릭 = 리플레이)</div>
        <div className="space-y-1">
          {failing.map(({ r, fails }) => (
            <button key={r.levelId} onClick={() => onSelect(r.levelId)}
              className="w-full flex items-center gap-2 rounded-lg px-2 py-1 text-left hover:bg-[rgba(56,189,248,.06)]">
              <span className="mono text-[11px] font-bold w-12 shrink-0">L{r.levelId}</span>
              <div className="flex h-3 rounded-sm overflow-hidden flex-1" style={{ background: "rgba(6,11,22,.6)" }}>
                {CATS.map((c, i) => (r[c.key] || 0) > 0 && (
                  <div key={c.key} style={{ width: `${((r[c.key] || 0) / maxFails) * 100}%`, background: c.color, marginRight: i < 2 ? 2 : 0 }} />
                ))}
              </div>
              <span className="mono text-[11px] w-14 text-right shrink-0" style={{ color: "var(--text-dim)" }}>{fails}회</span>
              <span className="mono text-[11px] w-10 text-right shrink-0" style={{ color: clearColor(r.clearRate) }}>{Math.round(r.clearRate * 100)}%</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// 비교 델타 — 레벨별 클리어율 변화 (개선=ok / 악화=err 다이버징), |Δ| 큰 순
function CompareDeltaPanel({ rows, compareMap, onSelect }: {
  rows: LevelResult[]; compareMap: Map<number, LevelResult>; onSelect: (lvl: number) => void;
}) {
  const deltas = rows
    .map((r) => { const c = compareMap.get(r.levelId); return c ? { r, d: r.clearRate - c.clearRate } : null; })
    .filter((x): x is { r: LevelResult; d: number } => x != null);
  if (deltas.length === 0) {
    return <div className="mt-3 text-[12px]" style={{ color: "var(--text-faint)" }}>비교 대상과 겹치는 레벨이 없습니다</div>;
  }
  const improved = deltas.filter((x) => x.d >= 0.05).length;
  const worse = deltas.filter((x) => x.d <= -0.05).length;
  const top = deltas.filter((x) => Math.abs(x.d) >= 0.02).sort((a, b) => Math.abs(b.d) - Math.abs(a.d)).slice(0, 15);
  const maxAbs = Math.max(0.01, ...top.map((x) => Math.abs(x.d)));

  return (
    <div className="mt-3 rounded-xl border p-3" style={{ borderColor: "var(--line)" }}>
      <div className="text-[10px] mono tracking-hud mb-2" style={{ color: "var(--text-faint)" }}>
        비교 델타 (현재 − 비교) — 공통 {deltas.length}레벨 ·{" "}
        <b style={{ color: "var(--ok)" }}>개선(+5pt↑) {improved}</b> ·{" "}
        <b style={{ color: "var(--err)" }}>악화(−5pt↓) {worse}</b>
      </div>
      {top.length === 0 && <div className="text-[12px]" style={{ color: "var(--text-dim)" }}>±2pt 이상 변화 없음</div>}
      <div className="space-y-1">
        {top.map(({ r, d }) => (
          <button key={r.levelId} onClick={() => onSelect(r.levelId)}
            className="w-full flex items-center gap-2 rounded-lg px-2 py-0.5 text-left hover:bg-[rgba(56,189,248,.06)]">
            <span className="mono text-[11px] font-bold w-12 shrink-0">L{r.levelId}</span>
            {/* 중앙 기준 다이버징 바 */}
            <div className="relative flex-1 h-3">
              <div className="absolute inset-y-0 left-1/2 w-px" style={{ background: "rgba(219,230,245,.25)" }} />
              <div className="absolute inset-y-0 rounded-sm"
                style={d >= 0
                  ? { left: "50%", width: `${(d / maxAbs) * 50}%`, background: "var(--ok)" }
                  : { right: "50%", width: `${(-d / maxAbs) * 50}%`, background: "var(--err)" }} />
            </div>
            <span className="mono text-[11px] w-16 text-right shrink-0" style={{ color: d >= 0 ? "var(--ok)" : "var(--err)" }}>
              {d >= 0 ? "+" : ""}{(d * 100).toFixed(0)}pt
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ──────────────────────────────────────────────────────────────
// 리플레이 캔버스 플레이어 — 보드/레일/비행다트/홀더 큐, 시크/배속 (터치 대응)
// 성능 설계:
//  - 캔버스 draw는 rAF에서만, React 상태 갱신 없음 (기존: 매 프레임 force() 리렌더 → 페이지 전체 버벅임)
//  - HUD/슬라이더 표시는 250ms 스로틀 상태(hudFrame)로만 갱신
//  - 시크는 키프레임 스냅샷(SNAP_EVERY 간격) 복원 — 기존은 드래그 이벤트마다 0프레임부터 전체 재적용 O(n²)
const SNAP_EVERY = 40;

interface BalloonState {
  n: number;
  xs: number[]; zs: number[]; cs: number[];
  idToIdx: Map<number, number>;
  popped: Uint8Array; concealed: Uint8Array; marks: string[];
  baseConcealed: Uint8Array; baseMarks: string[];
  snaps: { popped: Uint8Array; concealed: Uint8Array; marks: string[] }[];  // [k] = 프레임 k*SNAP_EVERY 적용 후
}

function applyFrameTo(st: BalloonState, f: RFrame) {
  for (const id of f.pop) { const i = st.idToIdx.get(id); if (i !== undefined) st.popped[i] = 1; }
  for (const id of f.reveal) { const i = st.idToIdx.get(id); if (i !== undefined) st.concealed[i] = 0; }
  for (const [id, mark] of f.mark) { const i = st.idToIdx.get(id); if (i !== undefined) st.marks[i] = mark; }
}

function restoreTo(st: BalloonState, rep: Replay, idx: number) {
  const k = Math.min(Math.floor(idx / SNAP_EVERY), st.snaps.length - 1);
  const snap = k >= 0 ? st.snaps[k] : null;
  if (snap) {
    st.popped.set(snap.popped);
    st.concealed.set(snap.concealed);
    for (let i = 0; i < st.n; i++) st.marks[i] = snap.marks[i];
    for (let i = k * SNAP_EVERY + 1; i <= idx && i < rep.frames.length; i++) applyFrameTo(st, rep.frames[i]);
  } else {
    st.popped.fill(0);
    st.concealed.set(st.baseConcealed);
    for (let i = 0; i < st.n; i++) st.marks[i] = st.baseMarks[i];
    for (let i = 0; i <= idx && i < rep.frames.length; i++) applyFrameTo(st, rep.frames[i]);
  }
}

function buildBalloonState(rep: Replay): BalloonState {
  const n = rep.balloons.length;
  const st: BalloonState = {
    n, xs: new Array(n), zs: new Array(n), cs: new Array(n), idToIdx: new Map(),
    popped: new Uint8Array(n), concealed: new Uint8Array(n), marks: new Array(n).fill(""),
    baseConcealed: new Uint8Array(n), baseMarks: new Array(n).fill(""), snaps: [],
  };
  rep.balloons.forEach(([id, x, z, c, mark, con], i) => {
    st.xs[i] = x; st.zs[i] = z; st.cs[i] = c; st.idToIdx.set(id, i);
    st.baseMarks[i] = mark; st.baseConcealed[i] = con ? 1 : 0;
  });
  // 시크용 키프레임 스냅샷 — 로드 시 1회 전체 패스
  st.concealed.set(st.baseConcealed);
  st.marks = st.baseMarks.slice();
  for (let i = 0; i < rep.frames.length; i++) {
    applyFrameTo(st, rep.frames[i]);
    if (i % SNAP_EVERY === 0) {
      st.snaps[i / SNAP_EVERY] = { popped: st.popped.slice(), concealed: st.concealed.slice(), marks: st.marks.slice() };
    }
  }
  restoreTo(st, rep, 0);
  return st;
}

function ReplayViewer({ resultId, level }: { resultId: string; level?: number }) {
  const [replay, setReplay] = useState<Replay | null>(null);
  const [err, setErr] = useState("");
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stRef = useRef<BalloonState | null>(null);
  const frameRef = useRef(0);
  const playingRef = useRef(false);
  const speedRef = useRef(1);
  const accumRef = useRef(0);
  const lastTsRef = useRef(0);
  const lastHudRef = useRef(0);
  const sizeRef = useRef({ W: 0, H: 0, bs: 1 });   // 레이아웃 캐시 — 매 프레임 clientWidth 읽기(강제 레이아웃) 방지
  const [hudFrame, setHudFrame] = useState(0);      // HUD·슬라이더 표시용 (재생 중 250ms 스로틀)
  const [, force] = useState(0);                    // 재생/일시정지 아이콘 갱신용

  useEffect(() => {
    fetch(`/api/sim/results/${resultId}?replay=1${level != null ? `&level=${level}` : ""}`)
      .then(async (r) => { if (!r.ok) throw new Error((await r.json()).error || r.statusText); return r.json(); })
      .then((d: Replay) => { setReplay(d); })
      .catch((e) => setErr(String(e.message || e)));
  }, [resultId, level]);

  const measure = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);      // 고DPI 백킹 과대 방지
    const W = canvas.clientWidth, H = Math.round(W * 1.35);
    const bs = dpr * Math.min(1, 1300 / Math.max(1, W * dpr));    // 백킹 폭 상한 ~1300px
    sizeRef.current = { W, H, bs };
    canvas.width = Math.round(W * bs);
    canvas.height = Math.round(H * bs);
    canvas.style.height = `${H}px`;
  }, []);

  const render = useCallback(() => {
    // 캔버스만 그린다 — 여기서 React 상태를 건드리지 않음
    const rep = replay, canvas = canvasRef.current, st = stRef.current;
    if (!rep || !canvas || !st) return;
    const f = rep.frames[frameRef.current];
    const { W, H, bs } = sizeRef.current;
    if (!W) return;
    const ctx = canvas.getContext("2d")!;
    ctx.setTransform(bs, 0, 0, bs, 0, 0);
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
    for (let i = 0; i < st.n; i++) {
      if (st.popped[i]) continue;
      const px = X(st.xs[i]), py = Y(st.zs[i]);
      const concealed = !!st.concealed[i];
      const mark = st.marks[i];
      let fill = concealed ? "#4b5563" : rep.palette[st.cs[i]] || "#f0f";
      if (mark.startsWith("I")) fill = "#96c8eb";
      ctx.fillStyle = fill;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();
      const mk = concealed ? "?" : mark;
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
        const stateIcon = state === "deploy" ? "▶" : state === "wait" ? "◇" : "";
        ctx.fillText(`${stateIcon}c${c}×${mag}${tags}`, x0 + 2, y0 + 8, colW - 9);
        y0 += 18;
      }
      if (hc.more > 0) { ctx.fillStyle = "#5a6f8c"; ctx.fillText(`+${hc.more}`, x0 + 2, y0 + 7); }
    }
  }, [replay]);

  // 시크 — 키프레임 스냅샷 복원 (드래그 중에도 가벼움)
  const seek = useCallback((v: number) => {
    const rep = replay, st = stRef.current;
    if (!rep || !st) return;
    playingRef.current = false;
    frameRef.current = Math.max(0, Math.min(v, rep.frames.length - 1));
    restoreTo(st, rep, frameRef.current);
    render();
    setHudFrame(frameRef.current);
  }, [replay, render]);

  // 초기화 + 재생 루프
  useEffect(() => {
    if (!replay) return;
    stRef.current = buildBalloonState(replay);
    frameRef.current = 0;
    setHudFrame(0);
    measure();
    render();
    let raf = 0;
    const tickFn = (ts: number) => {
      if (playingRef.current) {
        if (!lastTsRef.current) lastTsRef.current = ts;
        accumRef.current += ((ts - lastTsRef.current) / 1000) * speedRef.current;
        lastTsRef.current = ts;
        let changed = false;
        // 프레임 간격은 가변 — 대형 리플레이는 서버에서 다운샘플되므로 t 차이 기준으로 진행
        for (;;) {
          if (frameRef.current >= replay.frames.length - 1) { playingRef.current = false; break; }
          const dt = Math.max(0.05, replay.frames[frameRef.current + 1].t - replay.frames[frameRef.current].t);
          if (accumRef.current < dt) break;
          accumRef.current -= dt;
          frameRef.current++;
          applyFrameTo(stRef.current!, replay.frames[frameRef.current]);
          changed = true;
        }
        if (changed) {
          render();
          // HUD/슬라이더 갱신은 4회/초로 제한 — 매 프레임 React 리렌더 금지
          if (ts - lastHudRef.current > 250 || !playingRef.current) {
            lastHudRef.current = ts;
            setHudFrame(frameRef.current);
          }
        }
      } else lastTsRef.current = ts;
      raf = requestAnimationFrame(tickFn);
    };
    raf = requestAnimationFrame(tickFn);
    const onResize = () => { measure(); render(); };
    window.addEventListener("resize", onResize);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", onResize); };
  }, [replay, measure, render]);

  if (err) return <div className="text-[12px] py-3" style={{ color: "var(--err)" }}>리플레이 로드 실패: {err}</div>;
  if (!replay) return <div className="text-[12px] py-3" style={{ color: "var(--text-dim)" }}>리플레이 로드 중…</div>;

  const f = replay.frames[Math.min(hudFrame, replay.frames.length - 1)];
  const occPct = f.stat.cap > 0 ? Math.round((f.stat.occ / f.stat.cap) * 100) : 0;
  return (
    <div className="rounded-2xl border p-3 mb-2" style={{ borderColor: "var(--line)", background: "rgba(6,11,22,.5)" }}>
      {/* 컨트롤 — 모바일 터치 크기 */}
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <button onClick={() => {
          if (!playingRef.current && frameRef.current >= replay.frames.length - 1) seek(0);   // 끝났으면 처음부터
          playingRef.current = !playingRef.current; lastTsRef.current = 0; force((v) => v + 1);
        }}
          className="w-10 h-10 rounded-xl font-bold" style={{ background: "linear-gradient(135deg, var(--neon-deep), var(--neon))", color: "#041018" }}>
          <Icon name={playingRef.current ? "x" : "play"} size={14} />
        </button>
        <select defaultValue="1" onChange={(e) => { speedRef.current = parseFloat(e.target.value); }}
          className="rounded-xl px-2 py-2 text-[12px] border bg-[var(--panel-solid)]" style={{ borderColor: "var(--line)" }}>
          <option value="0.5">x0.5</option><option value="1">x1</option><option value="2">x2</option>
          <option value="4">x4</option><option value="10">x10</option>
        </select>
        <input type="range" min={0} max={replay.frames.length - 1} value={Math.min(hudFrame, replay.frames.length - 1)}
          onChange={(e) => seek(parseInt(e.target.value))}
          className="flex-1 min-w-[120px] accent-cyan-400" />
        <span className="mono text-[11px] w-24 text-right" style={{ color: "var(--text-dim)" }}>
          {f.t.toFixed(1)}s / {replay.frames[replay.frames.length - 1].t.toFixed(1)}s
        </span>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* contain+translateZ: 캔버스를 자체 컴포지터 레이어로 격리 — 리페인트가 glass(backdrop blur) 재합성을 유발하지 않게 */}
        <canvas ref={canvasRef} className="w-full rounded-xl lg:col-span-2"
          style={{ touchAction: "none", contain: "paint", transform: "translateZ(0)" }} />
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
