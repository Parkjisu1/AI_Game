import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { getDb } from "@/lib/mongodb";

// P0 검증 게이트 관측 — hermes_gate_events 집계 + merge_state 분포 + 차단 task(락업 탐지).
export async function GET() {
  const session = await auth();
  if (!session?.user?.email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  try {
    const db = await getDb();
    const since = new Date(Date.now() - 14 * 86400000).toISOString();
    const ev = await db.collection("hermes_gate_events").aggregate([
      { $match: { created_at: { $gte: since } } },
      { $group: { _id: { gate: "$gate", result: "$result" }, n: { $sum: 1 } } },
    ]).toArray();
    const ms = await db.collection("pixelforge_tasks").aggregate([
      { $match: { hermes_merge_state: { $exists: true } } },
      { $group: { _id: "$hermes_merge_state", n: { $sum: 1 } } },
    ]).toArray();
    const blocked = await db.collection("pixelforge_tasks").find(
      { hermes_merge_state: "blocked" },
      { projection: { title: 1, hermes_merge_reason: 1, hermes_merge_updated_at: 1 } }
    ).sort({ hermes_merge_updated_at: -1 }).limit(20).toArray();

    return NextResponse.json({
      gates: ev.map((e) => ({ gate: e._id.gate, result: e._id.result, n: e.n })),
      mergeStates: ms.map((m) => ({ state: m._id, n: m.n })),
      blocked: blocked.map((b) => ({ id: String(b._id), title: b.title || "", reason: b.hermes_merge_reason || "", at: b.hermes_merge_updated_at || "" })),
    });
  } catch (e) {
    return NextResponse.json({ gates: [], mergeStates: [], blocked: [], error: String(e) }, { status: 500 });
  }
}
