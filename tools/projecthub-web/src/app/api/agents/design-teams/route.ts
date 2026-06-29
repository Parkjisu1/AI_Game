import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

export const runtime = "nodejs";

/**
 * 4팀 경쟁 누적 점수 — 별점 1~5의 hermes_design_team_scores 컬렉션 집계.
 *
 * Returns:
 *   {
 *     teams: [{ team_id, label, icon, n, avg, last_score_at, weak }, ...],
 *     by_pattern: [{ team_id, pattern, n, avg }, ...],
 *     recent: [...최근 30개 별점],
 *   }
 */

const TEAM_META: Record<string, { label: string; icon: string; color: string }> = {
  hermes_native: { label: "Hermes Native",   icon: "🌀", color: "indigo" },
  geometric:     { label: "Geometric",       icon: "🔷", color: "emerald" },
  organic:       { label: "Organic",         icon: "🌊", color: "amber" },
  tile:          { label: "Tile / Pixel-Art", icon: "🧱", color: "pink" },
  balloonflow:   { label: "BalloonFlow",     icon: "🎯", color: "cyan" },
};
const TEAM_ORDER = ["hermes_native", "geometric", "organic", "tile", "balloonflow"];

export async function GET(_req: NextRequest) {
  const db = await getDb();
  const coll = db.collection("hermes_design_team_scores");

  const teamAgg = await coll
    .aggregate([
      {
        $group: {
          _id: "$team_id",
          n: { $sum: 1 },
          avg: { $avg: "$score" },
          last: { $max: "$created_at" },
        },
      },
    ])
    .toArray();
  const teamMap = new Map<string, { n: number; avg: number; last: string }>(
    teamAgg.map((r) => [r._id as string, { n: r.n, avg: r.avg, last: r.last as string }])
  );

  const teams = TEAM_ORDER.map((tid) => {
    const meta = TEAM_META[tid];
    const stats = teamMap.get(tid);
    const n = stats?.n ?? 0;
    const avg = stats?.avg ?? null;
    const weak = n >= 5 && (avg ?? 5) < 3.0;
    return {
      team_id: tid,
      label: meta.label,
      icon: meta.icon,
      color: meta.color,
      n,
      avg: avg !== null ? Math.round(avg * 100) / 100 : null,
      last_score_at: stats?.last || null,
      weak,
    };
  });

  // 누락된 (커스텀) 팀 추가
  for (const [tid, stats] of teamMap.entries()) {
    if (!TEAM_ORDER.includes(tid)) {
      teams.push({
        team_id: tid,
        label: tid,
        icon: "❓",
        color: "gray",
        n: stats.n,
        avg: Math.round(stats.avg * 100) / 100,
        last_score_at: stats.last,
        weak: stats.n >= 5 && stats.avg < 3.0,
      });
    }
  }

  // 팀×패턴 평균
  const byPattern = await coll
    .aggregate([
      { $group: { _id: { team: "$team_id", pat: "$pattern_chosen" }, n: { $sum: 1 }, avg: { $avg: "$score" } } },
      { $sort: { "_id.team": 1, avg: -1 } },
    ])
    .toArray();

  // 최근 30건
  const recent = await coll
    .find({}, {
      projection: { team_id: 1, level_id: 1, task_id: 1, score: 1, scored_by: 1,
                    pattern_chosen: 1, created_at: 1 },
    })
    .sort({ created_at: -1 })
    .limit(30)
    .toArray();

  return NextResponse.json({
    teams,
    by_pattern: byPattern.map((r) => ({
      team_id: (r._id as { team: string; pat: string }).team,
      pattern: (r._id as { team: string; pat: string }).pat,
      n: r.n,
      avg: Math.round((r.avg || 0) * 100) / 100,
    })),
    recent: recent.map((r) => ({
      _id: String(r._id),
      team_id: r.team_id,
      level_id: r.level_id,
      task_id: r.task_id,
      pattern: r.pattern_chosen,
      score: r.score,
      scored_by: r.scored_by,
      created_at: r.created_at,
    })),
  });
}
