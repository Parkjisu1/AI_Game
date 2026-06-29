"use client";
import { useEffect, useMemo, useState } from "react";

interface CostResponse {
  range: { days: number; since: string };
  totals: {
    calls: number;
    input_tokens: number;
    output_tokens: number;
    cache_read: number;
    cache_create: number;
    cost_usd: number;
    avg_dur: number;
  };
  daily: { date: string; calls: number; in: number; out: number; cost_usd: number }[];
  by_role: { role: string; calls: number; in: number; out: number; cost_usd: number; avg_dur: number }[];
  by_model: { model: string; calls: number; in: number; out: number; cost_usd: number; avg_dur: number }[];
  by_subteam: { team: string; sub_team: string; calls: number; cost_usd: number }[];
  recent: {
    _id: string;
    role: string;
    model: string;
    team?: string;
    sub_team?: string;
    task_id?: string;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    duration_sec: number;
    created_at: string;
  }[];
}

const fmtNum = (n: number) => n.toLocaleString();
const fmtUsd = (n: number) => `$${n.toFixed(4)}`;

export default function CostPage() {
  const [days, setDays] = useState(7);
  const [data, setData] = useState<CostResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    setLoading(true);
    fetch(`/api/agents/cost?days=${days}`)
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((j) => {
        setData(j);
        setErr("");
      })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [days]);

  const dailyMaxCost = useMemo(() => {
    if (!data) return 0;
    return Math.max(0.0001, ...data.daily.map((d) => d.cost_usd));
  }, [data]);

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-zinc-100">💰 비용 대시보드</h1>
          <p className="mt-1 text-sm text-zinc-400">
            Hermes 에이전트 호출의 토큰 사용량과 USD 비용 추세.
          </p>
        </div>
        <div className="flex gap-2">
          {[1, 7, 14, 30].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`rounded-lg px-3 py-1.5 text-sm transition ${
                days === d
                  ? "bg-indigo-500 text-white"
                  : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
              }`}
            >
              {d === 1 ? "오늘" : `${d}일`}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="text-zinc-400">로딩 중...</div>}
      {err && <div className="rounded-lg bg-red-500/10 p-4 text-red-300">에러: {err}</div>}

      {data && (
        <>
          {/* Totals */}
          <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-5">
            <KPI label="호출 수" value={fmtNum(data.totals.calls)} />
            <KPI label="총 비용" value={fmtUsd(data.totals.cost_usd)} accent />
            <KPI label="입력 토큰" value={fmtNum(data.totals.input_tokens)} />
            <KPI label="출력 토큰" value={fmtNum(data.totals.output_tokens)} />
            <KPI label="평균 응답시간" value={`${data.totals.avg_dur.toFixed(1)}s`} />
          </div>

          {/* Daily bar chart */}
          <Section title="📈 일별 비용 추세">
            <div className="space-y-1">
              {data.daily.length === 0 ? (
                <div className="py-8 text-center text-zinc-500">데이터 없음 (해당 기간 호출 0건)</div>
              ) : (
                data.daily.map((d) => (
                  <div key={d.date} className="flex items-center gap-3 text-sm">
                    <div className="w-24 font-mono text-zinc-400">{d.date}</div>
                    <div className="relative h-6 flex-1 overflow-hidden rounded bg-zinc-800">
                      <div
                        className="absolute inset-y-0 left-0 bg-gradient-to-r from-indigo-600 to-purple-500"
                        style={{ width: `${(d.cost_usd / dailyMaxCost) * 100}%` }}
                      />
                      <div className="absolute inset-0 flex items-center justify-end pr-2 text-xs text-white">
                        {d.calls}건 · {fmtUsd(d.cost_usd)}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </Section>

          {/* By model */}
          <Section title="🤖 모델별">
            <Table
              cols={["모델", "호출", "입력", "출력", "비용", "평균 시간"]}
              rows={data.by_model.map((r) => [
                <span key="m" className="font-mono text-xs">{r.model}</span>,
                fmtNum(r.calls),
                fmtNum(r.in),
                fmtNum(r.out),
                fmtUsd(r.cost_usd),
                `${r.avg_dur.toFixed(1)}s`,
              ])}
            />
          </Section>

          {/* By role */}
          <Section title="👤 역할별 (TOP 30)">
            <Table
              cols={["역할", "호출", "입력", "출력", "비용", "평균 시간"]}
              rows={data.by_role.map((r) => [
                <span key="r" className="font-mono text-xs">{r.role}</span>,
                fmtNum(r.calls),
                fmtNum(r.in),
                fmtNum(r.out),
                fmtUsd(r.cost_usd),
                `${r.avg_dur.toFixed(1)}s`,
              ])}
            />
          </Section>

          {/* By sub_team */}
          <Section title="🧭 분과별">
            <Table
              cols={["팀", "분과", "호출", "비용"]}
              rows={data.by_subteam.map((s) => [
                s.team || "—",
                s.sub_team || "general",
                fmtNum(s.calls),
                fmtUsd(s.cost_usd),
              ])}
            />
          </Section>

          {/* Recent calls */}
          <Section title="🕒 최근 호출 30건">
            <Table
              cols={["시각", "역할", "모델", "분과", "입/출", "비용", "Task"]}
              rows={data.recent.map((r) => [
                <span key="t" className="font-mono text-xs text-zinc-400">{r.created_at.slice(11, 19)}</span>,
                <span key="role" className="font-mono text-xs">{r.role}</span>,
                <span key="m" className="font-mono text-xs text-zinc-500">{r.model}</span>,
                `${r.team || "—"}/${r.sub_team || "general"}`,
                `${fmtNum(r.input_tokens)} / ${fmtNum(r.output_tokens)}`,
                fmtUsd(r.cost_usd),
                r.task_id ? (
                  <a key="ti" href={`/tasks?id=${r.task_id}`} className="font-mono text-xs text-indigo-400 hover:underline">
                    {r.task_id.slice(-8)}
                  </a>
                ) : "—",
              ])}
            />
          </Section>
        </>
      )}
    </div>
  );
}

function KPI({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className={`rounded-xl border p-4 ${accent ? "border-indigo-500/40 bg-indigo-500/5" : "border-zinc-800 bg-zinc-900/30"}`}>
      <div className="text-xs uppercase tracking-wide text-zinc-500">{label}</div>
      <div className={`mt-1 text-xl font-bold ${accent ? "text-indigo-300" : "text-zinc-100"}`}>{value}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-6 rounded-xl border border-zinc-800 bg-zinc-900/30 p-5">
      <h2 className="mb-3 text-sm font-semibold text-zinc-300">{title}</h2>
      {children}
    </div>
  );
}

function Table({ cols, rows }: { cols: string[]; rows: React.ReactNode[][] }) {
  if (rows.length === 0) {
    return <div className="py-6 text-center text-sm text-zinc-500">데이터 없음</div>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800 text-left text-xs uppercase tracking-wide text-zinc-500">
            {cols.map((c) => (
              <th key={c} className="px-2 py-2 font-medium">{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-zinc-900 hover:bg-zinc-800/30">
              {r.map((cell, j) => (
                <td key={j} className="px-2 py-2 text-zinc-300">{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
