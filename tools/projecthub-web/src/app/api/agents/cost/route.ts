import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

export const runtime = "nodejs";

/**
 * Hermes 토큰/비용 사용량 집계.
 *
 * Query:
 *   days = 7 | 14 | 30 (default 7)
 *   group = "day" | "role" | "model" | "sub_team"  (default "day")
 *
 * Returns:
 *   {
 *     totals: { calls, input_tokens, output_tokens, cache_read, cache_create, cost_usd },
 *     daily: [{ date, calls, in, out, cost_usd }, ...],
 *     by_role: [{ role, calls, in, out, cost_usd, avg_dur }, ...],
 *     by_model: [{ model, calls, in, out, cost_usd, avg_dur }, ...],
 *     by_subteam: [{ team, sub_team, calls, cost_usd }, ...],
 *     recent: [...최근 30개 호출],
 *   }
 */
export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const days = Math.min(90, Math.max(1, parseInt(url.searchParams.get("days") || "7", 10)));
  const since = new Date(Date.now() - days * 86400_000).toISOString();

  const db = await getDb();
  const coll = db.collection("hermes_token_usage");
  const filter = { created_at: { $gte: since } };

  // 1. 전체 합계
  const totalsAgg = await coll
    .aggregate([
      { $match: filter },
      {
        $group: {
          _id: null,
          calls: { $sum: 1 },
          input_tokens: { $sum: "$input_tokens" },
          output_tokens: { $sum: "$output_tokens" },
          cache_read: { $sum: "$cache_read" },
          cache_create: { $sum: "$cache_create" },
          cost_usd: { $sum: "$cost_usd" },
          avg_dur: { $avg: "$duration_sec" },
        },
      },
    ])
    .toArray();
  const totalsRow = totalsAgg[0] || { calls: 0, input_tokens: 0, output_tokens: 0, cache_read: 0, cache_create: 0, cost_usd: 0, avg_dur: 0 };

  // 2. 일별 (UTC 날짜 기준)
  const daily = await coll
    .aggregate([
      { $match: filter },
      {
        $group: {
          _id: { $substr: ["$created_at", 0, 10] },
          calls: { $sum: 1 },
          in: { $sum: "$input_tokens" },
          out: { $sum: "$output_tokens" },
          cost_usd: { $sum: "$cost_usd" },
        },
      },
      { $sort: { _id: 1 } },
    ])
    .toArray();

  // 3. 역할별
  const byRole = await coll
    .aggregate([
      { $match: filter },
      {
        $group: {
          _id: "$role",
          calls: { $sum: 1 },
          in: { $sum: "$input_tokens" },
          out: { $sum: "$output_tokens" },
          cost_usd: { $sum: "$cost_usd" },
          avg_dur: { $avg: "$duration_sec" },
        },
      },
      { $sort: { cost_usd: -1 } },
      { $limit: 30 },
    ])
    .toArray();

  // 4. 모델별
  const byModel = await coll
    .aggregate([
      { $match: filter },
      {
        $group: {
          _id: "$model",
          calls: { $sum: 1 },
          in: { $sum: "$input_tokens" },
          out: { $sum: "$output_tokens" },
          cost_usd: { $sum: "$cost_usd" },
          avg_dur: { $avg: "$duration_sec" },
        },
      },
      { $sort: { cost_usd: -1 } },
    ])
    .toArray();

  // 5. sub_team별
  const bySubteam = await coll
    .aggregate([
      { $match: filter },
      {
        $group: {
          _id: { team: "$team", sub_team: "$sub_team" },
          calls: { $sum: 1 },
          cost_usd: { $sum: "$cost_usd" },
        },
      },
      { $sort: { cost_usd: -1 } },
    ])
    .toArray();

  // 6. 최근 호출 30건
  const recent = await coll
    .find(filter, {
      projection: {
        role: 1, model: 1, team: 1, sub_team: 1, task_id: 1,
        input_tokens: 1, output_tokens: 1, cost_usd: 1,
        duration_sec: 1, created_at: 1,
      },
    })
    .sort({ created_at: -1 })
    .limit(30)
    .toArray();

  return NextResponse.json({
    range: { days, since },
    totals: {
      calls: totalsRow.calls,
      input_tokens: totalsRow.input_tokens,
      output_tokens: totalsRow.output_tokens,
      cache_read: totalsRow.cache_read,
      cache_create: totalsRow.cache_create,
      cost_usd: Math.round((totalsRow.cost_usd || 0) * 10000) / 10000,
      avg_dur: Math.round((totalsRow.avg_dur || 0) * 10) / 10,
    },
    daily: daily.map((d) => ({
      date: d._id as string,
      calls: d.calls,
      in: d.in,
      out: d.out,
      cost_usd: Math.round((d.cost_usd || 0) * 10000) / 10000,
    })),
    by_role: byRole.map((r) => ({
      role: r._id as string,
      calls: r.calls,
      in: r.in,
      out: r.out,
      cost_usd: Math.round((r.cost_usd || 0) * 10000) / 10000,
      avg_dur: Math.round((r.avg_dur || 0) * 10) / 10,
    })),
    by_model: byModel.map((r) => ({
      model: r._id as string,
      calls: r.calls,
      in: r.in,
      out: r.out,
      cost_usd: Math.round((r.cost_usd || 0) * 10000) / 10000,
      avg_dur: Math.round((r.avg_dur || 0) * 10) / 10,
    })),
    by_subteam: bySubteam.map((s) => ({
      team: (s._id as { team: string }).team,
      sub_team: (s._id as { sub_team: string }).sub_team,
      calls: s.calls,
      cost_usd: Math.round((s.cost_usd || 0) * 10000) / 10000,
    })),
    recent: recent.map((r) => ({
      _id: String(r._id),
      role: r.role,
      model: r.model,
      team: r.team,
      sub_team: r.sub_team,
      task_id: r.task_id,
      input_tokens: r.input_tokens,
      output_tokens: r.output_tokens,
      cost_usd: r.cost_usd,
      duration_sec: r.duration_sec,
      created_at: r.created_at,
    })),
  });
}
