import { NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

export const runtime = "nodejs";

/**
 * Hermes harness — H4 Eval results.
 *
 * Returns:
 *   {
 *     golden:  [{role, count}],          # role별 golden case 수
 *     latest_batches: [{batch_id, total, passed, avg_score, run_at}],  # 최근 5 batch
 *     by_role: [{role, runs, avg_score, last_run, pass_rate}],
 *     recent_failures: [...],
 *   }
 */
export async function GET() {
  const db = await getDb();
  const golden = db.collection("hermes_eval_golden");
  const runs = db.collection("hermes_eval_runs");

  const goldenAgg = await golden
    .aggregate([{ $group: { _id: "$role", count: { $sum: 1 } } }, { $sort: { count: -1 } }])
    .toArray();

  // 최근 5 batch
  const batchAgg = await runs
    .aggregate([
      {
        $group: {
          _id: "$batch_id",
          total: { $sum: 1 },
          passed: { $sum: { $cond: ["$passed", 1, 0] } },
          avg_score: { $avg: "$score" },
          run_at: { $max: "$run_at" },
        },
      },
      { $sort: { run_at: -1 } },
      { $limit: 5 },
    ])
    .toArray();

  // role별 누적 통계
  const roleAgg = await runs
    .aggregate([
      {
        $group: {
          _id: "$role",
          runs: { $sum: 1 },
          avg_score: { $avg: "$score" },
          pass_count: { $sum: { $cond: ["$passed", 1, 0] } },
          last_run: { $max: "$run_at" },
        },
      },
      { $sort: { _id: 1 } },
    ])
    .toArray();

  // 최근 실패 케이스 10개
  const failures = await runs
    .find({ passed: false }, {
      projection: {
        case_id: 1, role: 1, score: 1, diff_summary: 1,
        error: 1, run_at: 1, batch_id: 1,
      },
    })
    .sort({ run_at: -1 })
    .limit(10)
    .toArray();

  return NextResponse.json({
    golden: goldenAgg.map((g) => ({ role: g._id as string, count: g.count as number })),
    latest_batches: batchAgg.map((b) => ({
      batch_id: b._id as string,
      total: b.total as number,
      passed: b.passed as number,
      avg_score: Math.round((b.avg_score || 0) * 1000) / 1000,
      run_at: b.run_at as string,
    })),
    by_role: roleAgg.map((r) => ({
      role: r._id as string,
      runs: r.runs as number,
      avg_score: Math.round((r.avg_score || 0) * 1000) / 1000,
      pass_rate: r.runs > 0 ? Math.round((r.pass_count / r.runs) * 1000) / 1000 : 0,
      last_run: r.last_run as string,
    })),
    recent_failures: failures.map((f) => ({
      _id: String(f._id),
      case_id: f.case_id,
      role: f.role,
      score: f.score,
      diff_summary: f.diff_summary,
      error: f.error,
      run_at: f.run_at,
      batch_id: f.batch_id,
    })),
  });
}
