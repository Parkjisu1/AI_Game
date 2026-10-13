"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Icon from "@/components/Icon";

/**
 * 데이터 (BigQuery) — clean 인스턴스 전용.
 * 좌: 데이터셋/테이블 브라우저 + 저장된 쿼리 · 우: SQL 편집기 + 결과(표/막대/선 그래프).
 * 읽기 전용(SELECT/WITH), 행 1,000 · 스캔 2GB 상한. 차트는 의존성 없는 인라인 SVG.
 */

interface QueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
  rowCount: number;
  truncated?: boolean;
  bytesProcessed?: number;
  ms?: number;
}
interface SavedQuery { name: string; sql: string }

const LS_KEY = "newplay_bq_saved";
const ACCENT = "#4b8bfa";
const PALETTE = ["#4b8bfa", "#3fb950", "#f0883e", "#bc8cff", "#4dd0e1", "#e3b341", "#ff7b72", "#ec8cbf"];

function fmtBytes(n?: number) {
  if (!n) return "0 B";
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}
const isNum = (v: unknown) => typeof v === "number" || (typeof v === "string" && v !== "" && !isNaN(Number(v)));

/* ── 인라인 SVG 차트 (막대/선) ── */
function Chart({ result, xCol, yCols, kind }: { result: QueryResult; xCol: string; yCols: string[]; kind: "bar" | "line" }) {
  const W = 860, H = 300, PAD = { l: 56, r: 12, t: 12, b: 56 };
  const rows = result.rows.slice(0, 60);
  const series = yCols.map((c, i) => ({
    col: c, color: PALETTE[i % PALETTE.length],
    vals: rows.map((r) => Number(r[c] ?? 0)),
  }));
  const all = series.flatMap((s) => s.vals);
  const max = Math.max(1, ...all);
  const min = Math.min(0, ...all);
  const span = max - min || 1;
  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
  const xPos = (i: number) => PAD.l + (rows.length <= 1 ? iw / 2 : (i / (rows.length - 1)) * iw);
  const yPos = (v: number) => PAD.t + ih - ((v - min) / span) * ih;
  const bw = Math.max(2, (iw / Math.max(1, rows.length)) * 0.7 / Math.max(1, series.length));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => min + span * t);

  return (
    <div className="overflow-x-auto thin-scroll">
      <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[640px] w-full" role="img">
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.l} x2={W - PAD.r} y1={yPos(t)} y2={yPos(t)} stroke="#2a2c31" strokeWidth="1" />
            <text x={PAD.l - 8} y={yPos(t) + 4} textAnchor="end" fontSize="11" fill="#82868c">
              {Math.abs(t) >= 1000 ? `${(t / 1000).toFixed(1)}k` : t.toFixed(t % 1 === 0 ? 0 : 1)}
            </text>
          </g>
        ))}
        {kind === "bar"
          ? series.map((s, si) =>
              s.vals.map((v, i) => {
                const cx = PAD.l + (i + 0.5) * (iw / rows.length);
                const x = cx - (bw * series.length) / 2 + si * bw;
                const y0 = yPos(Math.max(0, min));
                const y1 = yPos(v);
                return <rect key={`${si}-${i}`} x={x} y={Math.min(y0, y1)} width={bw - 1} height={Math.abs(y0 - y1)} fill={s.color} rx="2" />;
              }))
          : series.map((s, si) => (
              <g key={si}>
                <polyline fill="none" stroke={s.color} strokeWidth="2"
                  points={s.vals.map((v, i) => `${kind === "line" && rows.length > 1 ? xPos(i) : PAD.l + (i + 0.5) * (iw / rows.length)},${yPos(v)}`).join(" ")} />
                {s.vals.map((v, i) => (
                  <circle key={i} cx={rows.length > 1 ? xPos(i) : PAD.l + iw / 2} cy={yPos(v)} r="3" fill={s.color} />
                ))}
              </g>
            ))}
        {rows.map((r, i) => {
          const step = Math.ceil(rows.length / 12);
          if (i % step !== 0) return null;
          const cx = kind === "bar" || rows.length <= 1 ? PAD.l + (i + 0.5) * (iw / rows.length) : xPos(i);
          return (
            <text key={i} x={cx} y={H - PAD.b + 16} textAnchor="end" fontSize="10" fill="#82868c"
              transform={`rotate(-35 ${cx} ${H - PAD.b + 16})`}>
              {String(r[xCol] ?? "").slice(0, 14)}
            </text>
          );
        })}
      </svg>
      <div className="flex flex-wrap gap-3 px-1 pb-1">
        {series.map((s) => (
          <span key={s.col} className="inline-flex items-center gap-1.5 text-[11px] text-gray-500">
            <span className="w-2.5 h-2.5 rounded-sm" style={{ background: s.color }} /> {s.col}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function DataPage() {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [projectId, setProjectId] = useState("");
  const [datasets, setDatasets] = useState<string[]>([]);
  const [openDs, setOpenDs] = useState<string>("");
  const [tables, setTables] = useState<Record<string, { id: string }[]>>({});
  const [sql, setSql] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [err, setErr] = useState("");
  const [view, setView] = useState<"table" | "bar" | "line">("table");
  const [xCol, setXCol] = useState("");
  const [yCols, setYCols] = useState<string[]>([]);
  const [saved, setSaved] = useState<SavedQuery[]>([]);

  useEffect(() => {
    fetch("/api/bq/meta").then((r) => r.json()).then((d) => {
      setConfigured(Boolean(d.configured));
      setProjectId(d.projectId || "");
      setDatasets((d.datasets || []).map((x: { id: string }) => x.id));
    }).catch(() => setConfigured(false));
    try { setSaved(JSON.parse(localStorage.getItem(LS_KEY) || "[]")); } catch { /* ignore */ }
  }, []);

  const toggleDs = async (ds: string) => {
    setOpenDs((cur) => (cur === ds ? "" : ds));
    if (!tables[ds]) {
      const d = await fetch(`/api/bq/meta?dataset=${encodeURIComponent(ds)}`).then((r) => r.json()).catch(() => null);
      if (d?.tables) setTables((m) => ({ ...m, [ds]: d.tables }));
    }
  };

  const run = useCallback(async (q?: string) => {
    const body = (q ?? sql).trim();
    if (!body || running) return;
    setRunning(true); setErr(""); setResult(null);
    try {
      const r = await fetch("/api/bq/query", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sql: body }),
      });
      const d = await r.json();
      if (!r.ok) { setErr(d.error || "실행 실패"); return; }
      setResult(d);
      // 차트 기본 축 추천: x=첫 비숫자 컬럼, y=숫자 컬럼들
      const numeric = d.columns.filter((c: string) => d.rows.length > 0 && isNum(d.rows[0][c]));
      const nonNum = d.columns.filter((c: string) => !numeric.includes(c));
      setXCol(nonNum[0] || d.columns[0] || "");
      setYCols(numeric.slice(0, 3));
      setView("table");
    } finally { setRunning(false); }
  }, [sql, running]);

  const saveCurrent = () => {
    const name = prompt("저장할 이름:");
    if (!name || !sql.trim()) return;
    const next = [...saved.filter((s) => s.name !== name), { name, sql }];
    setSaved(next);
    localStorage.setItem(LS_KEY, JSON.stringify(next));
  };
  const removeSaved = (name: string) => {
    const next = saved.filter((s) => s.name !== name);
    setSaved(next);
    localStorage.setItem(LS_KEY, JSON.stringify(next));
  };

  const numericCols = useMemo(
    () => (result && result.rows.length > 0 ? result.columns.filter((c) => isNum(result.rows[0][c])) : []),
    [result],
  );

  if (configured === false) {
    return (
      <div className="max-w-xl mx-auto mt-16">
        <div className="glass p-8 text-center">
          <span className="mx-auto mb-4 w-12 h-12 rounded-xl bg-gray-100 flex items-center justify-center text-gray-500 inline-flex"><Icon name="graph" size={22} /></span>
          <h1 className="text-lg font-bold text-gray-900 mb-2">BigQuery 연결 대기</h1>
          <p className="text-[13px] text-gray-500 leading-relaxed">
            아직 BigQuery가 연결되지 않았습니다.<br />
            GCP 서비스 계정 키(BigQuery 읽기 권한)를 관리자에게 전달하면<br />
            데이터셋 탐색·쿼리·그래프가 이 화면에서 열립니다.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-4 h-[calc(100vh-120px)]">
      {/* ── 좌: 브라우저 ── */}
      <div className="hidden lg:flex w-60 shrink-0 flex-col glass overflow-hidden">
        <div className="px-3 py-2.5 border-b border-gray-200 text-[13px] font-bold text-gray-900 truncate">
          {projectId || "BigQuery"}
        </div>
        <div className="flex-1 overflow-y-auto thin-scroll p-2">
          <div className="px-1.5 mb-1 text-[11px] font-semibold text-gray-400">데이터셋</div>
          {configured === null ? (
            <div className="text-[12px] text-gray-400 px-1.5 py-2">불러오는 중…</div>
          ) : datasets.length === 0 ? (
            <div className="text-[12px] text-gray-400 px-1.5 py-2">데이터셋 없음</div>
          ) : datasets.map((ds) => (
            <div key={ds}>
              <button onClick={() => toggleDs(ds)}
                className="w-full text-left flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[13px] text-gray-700 hover:bg-gray-50">
                <Icon name={openDs === ds ? "folder" : "folder"} size={13} />
                <span className="truncate">{ds}</span>
              </button>
              {openDs === ds && (
                <div className="ml-4 mb-1">
                  {(tables[ds] || []).map((t) => (
                    <button key={t.id}
                      onClick={() => setSql(`SELECT *\nFROM \`${projectId}.${ds}.${t.id}\`\nLIMIT 100`)}
                      className="w-full text-left flex items-center gap-1.5 rounded-md px-1.5 py-1 text-[12px] text-gray-500 hover:bg-gray-50 hover:text-gray-900">
                      <Icon name="doc" size={11} /> <span className="truncate">{t.id}</span>
                    </button>
                  ))}
                  {!tables[ds] && <div className="text-[11px] text-gray-400 px-1.5 py-1">…</div>}
                </div>
              )}
            </div>
          ))}
          {saved.length > 0 && (
            <>
              <div className="px-1.5 mt-3 mb-1 text-[11px] font-semibold text-gray-400">저장된 쿼리</div>
              {saved.map((s) => (
                <div key={s.name} className="group flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-gray-50">
                  <button onClick={() => setSql(s.sql)} className="flex-1 min-w-0 text-left text-[12px] text-gray-600 truncate flex items-center gap-1.5">
                    <Icon name="star" size={11} /> {s.name}
                  </button>
                  <button onClick={() => removeSaved(s.name)} className="hidden group-hover:block text-gray-400 hover:text-red-500"><Icon name="x" size={11} /></button>
                </div>
              ))}
            </>
          )}
        </div>
      </div>

      {/* ── 우: 편집기 + 결과 ── */}
      <div className="flex-1 min-w-0 flex flex-col gap-3">
        <div className="glass p-3">
          <textarea
            value={sql} onChange={(e) => setSql(e.target.value)}
            onKeyDown={(e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") run(); }}
            placeholder={`SELECT date, SUM(amount) AS total\nFROM \`project.dataset.table\`\nGROUP BY date ORDER BY date  — Ctrl+Enter 실행`}
            rows={5}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-[13px] font-mono resize-y"
            spellCheck={false}
          />
          <div className="mt-2 flex items-center gap-2">
            <button onClick={() => run()} disabled={running || !sql.trim()}
              className="px-4 py-2 rounded-lg text-[13px] font-semibold text-white disabled:opacity-50"
              style={{ background: ACCENT }}>
              {running ? "실행 중…" : "실행"}
            </button>
            <button onClick={saveCurrent} disabled={!sql.trim()}
              className="px-3 py-2 rounded-lg text-[13px] text-gray-600 border border-gray-300 hover:bg-gray-50 disabled:opacity-50">
              저장
            </button>
            {result && (
              <span className="ml-auto text-[12px] text-gray-500">
                {result.rowCount.toLocaleString()}행{result.truncated ? "+" : ""} · 스캔 {fmtBytes(result.bytesProcessed)} · {result.ms}ms
              </span>
            )}
          </div>
          {err && <div className="mt-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-600 whitespace-pre-wrap">{err}</div>}
        </div>

        {result && (
          <div className="glass flex-1 min-h-0 flex flex-col overflow-hidden">
            <div className="flex items-center gap-1.5 px-3 py-2 border-b border-gray-200 shrink-0 flex-wrap">
              {(["table", "bar", "line"] as const).map((v) => (
                <button key={v} onClick={() => setView(v)}
                  className={`px-2.5 py-1 rounded-md text-[12px] font-medium ${view === v ? "bg-gray-100 text-gray-900" : "text-gray-500 hover:bg-gray-50"}`}>
                  {v === "table" ? "표" : v === "bar" ? "막대" : "선"}
                </button>
              ))}
              {view !== "table" && (
                <>
                  <span className="ml-2 text-[11px] text-gray-400">X</span>
                  <select value={xCol} onChange={(e) => setXCol(e.target.value)} className="text-[12px] rounded-md border border-gray-300 px-1.5 py-1">
                    {result.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                  <span className="text-[11px] text-gray-400">Y</span>
                  {numericCols.map((c) => (
                    <button key={c}
                      onClick={() => setYCols((cur) => cur.includes(c) ? cur.filter((x) => x !== c) : [...cur, c])}
                      className={`px-2 py-1 rounded-md text-[11px] border ${yCols.includes(c) ? "border-transparent text-white" : "border-gray-200 text-gray-500"}`}
                      style={yCols.includes(c) ? { background: ACCENT } : undefined}>
                      {c}
                    </button>
                  ))}
                </>
              )}
            </div>
            <div className="flex-1 min-h-0 overflow-auto thin-scroll p-3">
              {view === "table" ? (
                <table className="w-full text-[12px]">
                  <thead>
                    <tr className="text-left text-gray-500">
                      {result.columns.map((c) => <th key={c} className="px-2 py-1.5 border-b border-gray-200 font-semibold whitespace-nowrap">{c}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {result.rows.map((r, i) => (
                      <tr key={i} className="hover:bg-gray-50">
                        {result.columns.map((c) => (
                          <td key={c} className="px-2 py-1.5 border-b border-gray-100 text-gray-700 whitespace-nowrap max-w-[280px] truncate">
                            {r[c] === null || r[c] === undefined ? <span className="text-gray-300">null</span> : String(r[c])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : yCols.length === 0 ? (
                <div className="py-12 text-center text-[13px] text-gray-400">Y축으로 쓸 숫자 컬럼을 선택하세요</div>
              ) : (
                <Chart result={result} xCol={xCol} yCols={yCols} kind={view} />
              )}
            </div>
          </div>
        )}

        {!result && !err && (
          <div className="glass flex-1 flex items-center justify-center text-[13px] text-gray-400">
            좌측에서 테이블을 선택하거나 쿼리를 작성해 실행하세요
          </div>
        )}
      </div>
    </div>
  );
}
