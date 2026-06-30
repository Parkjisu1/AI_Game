"use client";
import { useEffect, useState } from "react";

interface Resp {
  golden: { role: string; count: number }[];
  latest_batches: { batch_id: string; total: number; passed: number; avg_score: number; run_at: string }[];
  by_role: { role: string; runs: number; avg_score: number; pass_rate: number; last_run: string }[];
  recent_failures: {
    _id: string;
    case_id: string;
    role: string;
    score: number;
    diff_summary: string;
    error?: string;
    run_at: string;
    batch_id?: string;
  }[];
}

export default function EvalPage() {
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetch("/api/agents/eval")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">🧪 H4 Eval Harness</h1>
          <p className="mt-1 text-sm text-gray-500">
            Golden test → 회귀 감지. 별점 ≥ 4점 받은 task에서 자동 추출. 패스 임계값: <code>0.7</code>.
          </p>
        </div>
        <div className="flex gap-2">
          <a href="/agents" className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg">← /agents</a>
          <a href="/agents/cost" className="text-xs px-3 py-1.5 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 rounded-lg border border-indigo-200">💰 비용</a>
          <a href="/agents/design-teams" className="text-xs px-3 py-1.5 bg-pink-50 text-pink-700 hover:bg-pink-100 rounded-lg border border-pink-200">🏁 팀 점수</a>
        </div>
      </div>

      {loading && <p className="text-gray-400">로딩 중...</p>}
      {err && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">에러: {err}</div>}

      {data && (
        <>
          {/* Golden cases */}
          <Section title="🥇 Golden cases (역할별)">
            {data.golden.length === 0 ? (
              <p className="text-sm text-gray-400 py-4 text-center">
                아직 golden 없음 — 사용자 별점 후 <code>python harness/eval.py extract --role design_level_designer</code>
              </p>
            ) : (
              <Table cols={["역할", "개수"]} rows={data.golden.map(g => [g.role, g.count])} />
            )}
          </Section>

          {/* Latest batches */}
          <Section title="🔄 최근 회귀 batch (최신순)">
            {data.latest_batches.length === 0 ? (
              <p className="text-sm text-gray-400 py-4 text-center">
                실행 기록 없음 — <code>python harness/eval.py run --all</code>
              </p>
            ) : (
              <Table
                cols={["Batch", "Pass", "Avg Score", "Run at"]}
                rows={data.latest_batches.map(b => [
                  <span key="b" className="font-mono text-xs">{b.batch_id}</span>,
                  <span key="p" className={b.passed === b.total ? "text-emerald-600" : "text-orange-600"}>
                    {b.passed}/{b.total}
                  </span>,
                  <ScoreBar key="s" value={b.avg_score} />,
                  <span key="t" className="text-xs text-gray-500">{b.run_at?.slice(0, 19)}</span>,
                ])}
              />
            )}
          </Section>

          {/* By role */}
          <Section title="📊 역할별 누적 통계">
            <Table
              cols={["역할", "총 runs", "Avg Score", "Pass Rate", "Last Run"]}
              rows={data.by_role.map(r => [
                <span key="r" className="font-mono text-xs">{r.role}</span>,
                r.runs,
                <ScoreBar key="s" value={r.avg_score} />,
                <span key="p" className={r.pass_rate >= 0.8 ? "text-emerald-600" : r.pass_rate >= 0.5 ? "text-orange-600" : "text-red-600"}>
                  {(r.pass_rate * 100).toFixed(0)}%
                </span>,
                <span key="t" className="text-xs text-gray-500">{r.last_run?.slice(0, 19)}</span>,
              ])}
            />
          </Section>

          {/* Recent failures */}
          <Section title="❌ 최근 실패 10건">
            {data.recent_failures.length === 0 ? (
              <p className="text-sm text-emerald-600 py-4 text-center">실패 없음 ✓</p>
            ) : (
              <Table
                cols={["역할", "Case", "Score", "Diff / Error", "When"]}
                rows={data.recent_failures.map(f => [
                  <span key="r" className="font-mono text-xs">{f.role}</span>,
                  <span key="c" className="font-mono text-[11px]">{f.case_id?.slice(-12)}</span>,
                  <span key="s" className="font-mono">{f.score?.toFixed(2)}</span>,
                  <span key="d" className="text-xs text-gray-600">{(f.error || f.diff_summary || "").slice(0, 80)}</span>,
                  <span key="t" className="text-xs text-gray-500">{f.run_at?.slice(11, 19)}</span>,
                ])}
              />
            )}
          </Section>
        </>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6 rounded-xl border border-gray-200 bg-white p-5">
      <h2 className="mb-3 text-base font-bold">{title}</h2>
      {children}
    </div>
  );
}

function ScoreBar({ value }: { value: number }) {
  const pct = Math.max(0, Math.min(1, value)) * 100;
  const color = value >= 0.8 ? "bg-emerald-500" : value >= 0.5 ? "bg-orange-400" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <div className="relative h-2 w-24 overflow-hidden rounded bg-gray-200">
        <div className={`absolute inset-y-0 left-0 ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-xs">{(value ?? 0).toFixed(3)}</span>
    </div>
  );
}

function Table({ cols, rows }: { cols: string[]; rows: React.ReactNode[][] }) {
  if (rows.length === 0) return <p className="text-sm text-gray-400 text-center py-4">데이터 없음</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
            {cols.map((c) => <th key={c} className="px-2 py-2 font-medium">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-gray-100">
              {r.map((cell, j) => <td key={j} className="px-2 py-1.5">{cell}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
