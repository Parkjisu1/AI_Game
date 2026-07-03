import { NextRequest, NextResponse } from "next/server";
import { ObjectId } from "mongodb";
import { getDb } from "@/lib/mongodb";

export const runtime = "nodejs";

/**
 * 시뮬 결과 상세.
 *   GET /api/sim/results/:id                     → 레벨별 전체 결과
 *   GET /api/sim/results/:id?replay=1            → 기본 리플레이 프레임 JSON (배치 시 최난 레벨)
 *   GET /api/sim/results/:id?replay=1&level=N    → 해당 레벨 리플레이 (replays 맵 → 레거시 replay_id 순)
 */
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!ObjectId.isValid(id)) return NextResponse.json({ error: "invalid id" }, { status: 400 });
  const db = await getDb();
  const url = new URL(req.url);

  if (url.searchParams.get("replay") === "1") {
    const level = url.searchParams.get("level");
    const result = await db.collection("bf_sim_results")
      .findOne({ _id: new ObjectId(id) }, { projection: { replay_id: 1, replay_level: 1, replays: 1 } });
    let repId: string | null = null;
    if (level) {
      repId = result?.replays?.[level]
        || (String(result?.replay_level) === level ? result?.replay_id : null);
    } else {
      repId = result?.replay_id || null;
    }
    if (!repId || !ObjectId.isValid(repId)) {
      return NextResponse.json({ error: "리플레이 없음" }, { status: 404 });
    }
    const rep = await db.collection("bf_sim_replays").findOne({ _id: new ObjectId(repId) });
    if (!rep) return NextResponse.json({ error: "리플레이 없음" }, { status: 404 });
    return NextResponse.json(rep.data);
  }

  const doc = await db.collection("bf_sim_results").findOne({ _id: new ObjectId(id) });
  if (!doc) return NextResponse.json({ error: "not found" }, { status: 404 });
  return NextResponse.json({ ...doc, _id: String(doc._id) });
}
