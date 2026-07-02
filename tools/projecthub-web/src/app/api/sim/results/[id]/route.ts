import { NextRequest, NextResponse } from "next/server";
import { ObjectId } from "mongodb";
import { getDb } from "@/lib/mongodb";

export const runtime = "nodejs";

/**
 * 시뮬 결과 상세.
 *   GET /api/sim/results/:id            → 레벨별 전체 결과
 *   GET /api/sim/results/:id?replay=1   → 연결된 리플레이 프레임 JSON
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!ObjectId.isValid(id)) return NextResponse.json({ error: "invalid id" }, { status: 400 });
  const db = await getDb();
  const url = new URL(req.url);

  if (url.searchParams.get("replay") === "1") {
    const result = await db.collection("bf_sim_results")
      .findOne({ _id: new ObjectId(id) }, { projection: { replay_id: 1 } });
    if (!result?.replay_id || !ObjectId.isValid(result.replay_id)) {
      return NextResponse.json({ error: "리플레이 없음" }, { status: 404 });
    }
    const rep = await db.collection("bf_sim_replays").findOne({ _id: new ObjectId(result.replay_id) });
    if (!rep) return NextResponse.json({ error: "리플레이 없음" }, { status: 404 });
    return NextResponse.json(rep.data);
  }

  const doc = await db.collection("bf_sim_results").findOne({ _id: new ObjectId(id) });
  if (!doc) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json({ ...doc, _id: String(doc._id) });
}
