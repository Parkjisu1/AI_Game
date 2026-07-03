import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { getDb } from "@/lib/mongodb";

// 어시스턴트 상태 요약 — 실시간 음성 대화의 get_status 툴 + 대시보드용.
// 읽기 전용. updated_at은 ISO 문자열 저장 규칙(ProjectHub) → 문자열 비교로 24h 필터.

export async function GET() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  try {
    const db = await getDb();
    const tasks = db.collection("pixelforge_tasks");
    const dayAgoIso = new Date(Date.now() - 24 * 3600 * 1000).toISOString();

    const [todo, inProgressCount, review, done24h, inProgress, reviews, workers] = await Promise.all([
      tasks.countDocuments({ status: "todo" }),
      tasks.countDocuments({ status: "in_progress" }),
      tasks.countDocuments({ status: "review" }),
      tasks.countDocuments({ status: "done", updated_at: { $gte: dayAgoIso } }),
      tasks
        .find({ status: "in_progress" }, { projection: { title: 1, hermes_claimed_by: 1, updated_at: 1 } })
        .sort({ updated_at: -1 }).limit(8).toArray(),
      tasks
        .find({ status: "review" }, { projection: { title: 1, updated_at: 1 } })
        .sort({ updated_at: -1 }).limit(8).toArray(),
      db.collection("hermes_workers")
        .find({ ts: { $gte: new Date(Date.now() - 3 * 60 * 1000) } })
        .toArray(),
    ]);

    return NextResponse.json({
      counts: { todo, in_progress: inProgressCount, review, done_24h: done24h },
      in_progress: inProgress.map((t) => ({
        id: String(t._id).slice(-8),
        title: t.title,
        worker: t.hermes_claimed_by || null,
      })),
      reviews: reviews.map((t) => ({ id: String(t._id).slice(-8), title: t.title })),
      workers: workers.map((w) => ({
        worker_id: w.worker_id,
        slots: w.slots,
        active: (w.active || []).length,
      })),
      as_of: new Date().toISOString(),
    });
  } catch (e) {
    return NextResponse.json(
      { error: "status query failed", detail: e instanceof Error ? e.message : String(e) },
      { status: 500 },
    );
  }
}
