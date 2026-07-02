import { NextRequest, NextResponse } from "next/server";
import { ObjectId } from "mongodb";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";

export const runtime = "nodejs";

/**
 * BalloonFlow 클리어율 시뮬레이터 연동.
 *
 * POST — 시뮬 요청: assignee=hermes 태스크 생성 (sim_params 구조체 포함)
 *        → Mother watcher(_handle_simulation)가 머신 B에서 BalloonFlowSim 실행
 *        → bf_sim_results / bf_sim_replays 저장.
 * GET  — 최근 시뮬 태스크(진행중) + 결과 목록.
 */
export async function POST(req: NextRequest) {
  const db = await getDb();
  const body = await req.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }

  const levels = String(body.levels || "1-20").trim();
  if (!/^[\d,\-\s~]+$/.test(levels)) {
    return NextResponse.json({ error: "레벨 범위 형식 오류 (예: 1-20, 45)" }, { status: 400 });
  }
  const runs = Math.min(200, Math.max(1, parseInt(body.runs) || 50));
  const policy = ["smart", "greedy", "random"].includes(body.policy) ? body.policy : "smart";
  const seed = parseInt(body.seed) || 12345;
  const replay = body.replay !== false;
  const replayLevel = parseInt(body.replay_level) || 0;

  let email = "";
  try {
    const session = await auth();
    email = (session?.user?.email || "").toLowerCase();
  } catch { /* 인증 우회 모드 */ }

  const now = new Date().toISOString();
  const task = {
    title: `🎯 시뮬레이션: 레벨 ${levels} × ${runs}회 (${policy})`,
    description:
      `BalloonFlow 클리어율 시뮬레이션 요청 (시뮬레이터 탭에서 생성).\n` +
      `레벨 ${levels} · ${runs}회 · 정책 ${policy} · 시드 ${seed}` +
      (replay ? ` · 리플레이 ${replayLevel ? `L${replayLevel}` : "자동(최난)"}` : ""),
    assignee: "hermes",
    status: "todo",
    priority: "medium",
    tags: ["시뮬", "balloonflow"],
    sim_params: { levels, runs, policy, seed, replay, replay_level: replayLevel },
    created_by_email: email,
    created_at: now,
    updated_at: now,
  };
  const ins = await db.collection("pixelforge_tasks").insertOne(task);
  return NextResponse.json({ ok: true, task_id: String(ins.insertedId) });
}

export async function GET(req: NextRequest) {
  const db = await getDb();
  const url = new URL(req.url);
  const limit = Math.min(30, Math.max(1, parseInt(url.searchParams.get("limit") || "12", 10)));

  const [tasks, results] = await Promise.all([
    db.collection("pixelforge_tasks")
      .find({ tags: "시뮬", status: { $in: ["todo", "in_progress"] } })
      .sort({ created_at: -1 }).limit(10)
      .project({ title: 1, status: 1, created_at: 1, sim_params: 1 })
      .toArray(),
    db.collection("bf_sim_results")
      .find({})
      .sort({ created_at: -1 }).limit(limit)
      .project({ results: 0 })   // 목록은 요약만 (상세는 /api/sim/results/[id])
      .toArray(),
  ]);

  return NextResponse.json({
    pending: tasks.map((t) => ({ ...t, _id: String(t._id) })),
    results: results.map((r) => ({ ...r, _id: String(r._id) })),
  });
}

export async function DELETE(req: NextRequest) {
  // 결과 삭제 (정리용)
  const db = await getDb();
  const url = new URL(req.url);
  const id = url.searchParams.get("id") || "";
  if (!ObjectId.isValid(id)) return NextResponse.json({ error: "invalid id" }, { status: 400 });
  const doc = await db.collection("bf_sim_results").findOneAndDelete({ _id: new ObjectId(id) });
  if (doc?.replay_id && ObjectId.isValid(doc.replay_id)) {
    await db.collection("bf_sim_replays").deleteOne({ _id: new ObjectId(doc.replay_id) });
  }
  return NextResponse.json({ ok: true });
}
