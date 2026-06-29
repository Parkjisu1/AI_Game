"use client";
import { useEffect, useState } from "react";

interface TeamRow {
  team_id: string;
  label: string;
  icon: string;
  color: string;
  n: number;
  avg: number | null;
  last_score_at: string | null;
  weak: boolean;
}
interface PatternRow {
  team_id: string;
  pattern: string;
  n: number;
  avg: number;
}
interface RecentRow {
  _id: string;
  team_id: string;
  level_id?: string;
  task_id?: string;
  pattern: string;
  score: number;
  scored_by?: string;
  created_at: string;
}
interface Resp {
  teams: TeamRow[];
  by_pattern: PatternRow[];
  recent: RecentRow[];
}

const COLOR_CLASSES: Record<string, { border: string; bg: string; text: string; bar: string }> = {
  indigo:  { border: "border-indigo-400",  bg: "bg-indigo-50",  text: "text-indigo-700",  bar: "bg-indigo-500" },
  emerald: { border: "border-emerald-400", bg: "bg-emerald-50", text: "text-emerald-700", bar: "bg-emerald-500" },
  amber:   { border: "border-amber-400",   bg: "bg-amber-50",   text: "text-amber-700",   bar: "bg-amber-500" },
  pink:    { border: "border-pink-400",    bg: "bg-pink-50",    text: "text-pink-700",    bar: "bg-pink-500" },
  cyan:    { border: "border-cyan-400",    bg: "bg-cyan-50",    text: "text-cyan-700",    bar: "bg-cyan-500" },
  gray:    { border: "border-gray-300",    bg: "bg-gray-50",    text: "text-gray-700",    bar: "bg-gray-400" },
};

function StarBar({ value }: { value: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((n) => (
        <span key={n} className={`text-base ${value >= n ? "text-yellow-400" : "text-gray-300"}`}>★</span>
      ))}
      <span className="ml-1 text-xs text-gray-500 font-mono">{value.toFixed(2)}</span>
    </div>
  );
}

export default function DesignTeamsPage() {
  const [data, setData] = useState<Resp | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    fetch("/api/agents/design-teams")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">🏁 Design Teams Leaderboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            4팀 경쟁 누적 별점 (1~5). 평균 &lt; 3 + 표본 5+ → 약팀 표시 + 다음 task에서 패턴 선택 가중치 자동 조정.
          </p>
        </div>
        <div className="flex gap-2">
          <a href="/agents" className="text-xs px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded-lg">← /agents</a>
          <a href="/agents/cost" className="text-xs px-3 py-1.5 bg-indigo-50 text-indigo-700 hover:bg-indigo-100 rounded-lg border border-indigo-200">💰 비용</a>
        </div>
      </div>

      {loading && <p className="text-gray-400">로딩 중...</p>}
      {err && <div className="rounded-lg bg-red-50 p-3 text-sm text-red-700">에러: {err}</div>}

      {data && (
        <>
          {/* 팀 카드 4개 */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            {data.teams.map((t) => {
              const cc = COLOR_CLASSES[t.color] || COLOR_CLASSES.gray;
              return (
                <div key={t.team_id} className={`rounded-xl border-2 ${cc.border} ${cc.bg} p-4`}>
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className={`font-bold ${cc.text}`}>{t.icon} {t.label}</h3>
                      <p className="text-[11px] text-gray-500 font-mono">{t.team_id}</p>
                    </div>
                    {t.weak && (
                      <span className="px-1.5 py-0.5 bg-red-500 text-white text-[10px] rounded font-bold">
                        WEAK
                      </span>
                    )}
                  </div>
                  <div className="mt-3">
                    {t.avg !== null ? (
                      <StarBar value={t.avg} />
                    ) : (
                      <span className="text-sm text-gray-400">아직 별점 없음</span>
                    )}
                  </div>
                  <div className="mt-2 flex items-center gap-3 text-[11px] text-gray-500">
                    <span>표본 {t.n}건</span>
                    {t.last_score_at && (
                      <span>· 최근 {t.last_score_at.slice(5, 10)}</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* 팀×패턴 leaderboard */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 mb-6">
            <h2 className="text-base font-bold mb-3">📊 팀 × 패턴 별 평균 별점</h2>
            {data.by_pattern.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">데이터 없음 — 별점 누적되면 표시됩니다.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                      <th className="px-2 py-1.5">팀</th>
                      <th className="px-2 py-1.5">패턴</th>
                      <th className="px-2 py-1.5">표본</th>
                      <th className="px-2 py-1.5 text-right">평균</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_pattern.map((r, i) => {
                      const team = data.teams.find((t) => t.team_id === r.team_id);
                      const cc = team ? COLOR_CLASSES[team.color] || COLOR_CLASSES.gray : COLOR_CLASSES.gray;
                      return (
                        <tr key={i} className="border-b border-gray-100">
                          <td className="px-2 py-1.5">
                            <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded ${cc.bg} ${cc.text}`}>
                              {team?.icon} {team?.label || r.team_id}
                            </span>
                          </td>
                          <td className="px-2 py-1.5 font-mono text-xs">{r.pattern}</td>
                          <td className="px-2 py-1.5 text-gray-500">{r.n}</td>
                          <td className="px-2 py-1.5 text-right">
                            <StarBar value={r.avg} />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* 최근 별점 */}
          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <h2 className="text-base font-bold mb-3">🕒 최근 별점 30건</h2>
            {data.recent.length === 0 ? (
              <p className="text-sm text-gray-400 text-center py-6">아직 별점 없음</p>
            ) : (
              <div className="space-y-1">
                {data.recent.map((r) => {
                  const team = data.teams.find((t) => t.team_id === r.team_id);
                  return (
                    <div key={r._id} className="flex items-center gap-3 text-xs py-1 border-b border-gray-50">
                      <span className="font-mono text-gray-400 w-32 shrink-0">{r.created_at.slice(5, 16)}</span>
                      <span className="w-32 shrink-0">{team?.icon} {team?.label || r.team_id}</span>
                      <span className="font-mono text-gray-500 w-32 shrink-0">{r.pattern}</span>
                      <span className="text-yellow-500">{"★".repeat(r.score)}{"☆".repeat(5 - r.score)}</span>
                      <span className="text-gray-400 ml-auto truncate">{r.scored_by || ""}</span>
                      {r.task_id && (
                        <a href={`/tasks?id=${r.task_id}`} className="text-indigo-600 hover:underline shrink-0">
                          task →
                        </a>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
