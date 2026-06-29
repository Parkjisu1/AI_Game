import { NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

export const runtime = "nodejs";

/**
 * 팀·분과별 품질 점수 집계 — Reviewer가 매긴 quality_score 평균.
 * Phase 2 보상 체계의 데이터 표시용.
 *
 * Returns:
 *   {
 *     totals: [{ team, sub_team, count, avg, last_30d_avg }, ...],
 *     recent: [...최근 20개 점수 기록],
 *   }
 */
export async function GET() {
  const db = await getDb();
  const coll = db.collection("hermes_team_scores");

  const totals = await coll
    .aggregate([
      {
        $group: {
          _id: { team: "$team", sub_team: "$sub_team" },
          count: { $sum: 1 },
          avg: { $avg: "$score" },
          min: { $min: "$score" },
          max: { $max: "$score" },
          last: { $max: "$created_at" },
        },
      },
      { $sort: { "_id.team": 1, "_id.sub_team": 1 } },
    ])
    .toArray();

  const recent = await coll
    .find({}, { projection: { task_id: 1, team: 1, sub_team: 1, role: 1, score: 1, verdict: 1, created_at: 1 } })
    .sort({ created_at: -1 })
    .limit(20)
    .toArray();

  return NextResponse.json({
    totals: totals.map((t) => ({
      team: (t._id as { team: string }).team,
      sub_team: (t._id as { sub_team: string }).sub_team,
      count: t.count,
      avg: t.avg ? Math.round(t.avg * 10) / 10 : null,
      min: t.min,
      max: t.max,
      last: t.last,
    })),
    recent: recent.map((r) => ({
      _id: String(r._id),
      task_id: r.task_id,
      team: r.team,
      sub_team: r.sub_team,
      role: r.role,
      score: r.score,
      verdict: r.verdict,
      created_at: r.created_at,
    })),
  });
}
