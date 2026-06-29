import { NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth } from "@/auth";
import { ObjectId } from "mongodb";

export const runtime = "nodejs";

/**
 * FC job 의 모든 ok 레벨에 대해 pixelforge_levels.queue_data 보유 여부 반환.
 * 모달 진입 시 호출 → "다운로드 vs Queue 생성" UI 분기에 사용.
 */
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const session = await auth();
  if (!session?.user?.email) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const { id } = await params;
  let jobObjId: ObjectId;
  try { jobObjId = new ObjectId(id); }
  catch { return NextResponse.json({ error: "invalid id" }, { status: 400 }); }

  const db = await getDb();
  const job = await db.collection("pixelforge_field_complete_jobs").findOne(
    { _id: jobObjId },
    { projection: { "results.level_number": 1, "results.ok": 1, "results.balloons": 1 } },
  );
  if (!job) return NextResponse.json({ error: "job not found" }, { status: 404 });

  const okLevels = ((job.results as Array<{ level_number: number; ok: boolean; balloons?: unknown[] }>) || [])
    .filter((r) => r.ok && Array.isArray(r.balloons) && r.balloons.length > 0)
    .map((r) => r.level_number);

  if (okLevels.length === 0) {
    return NextResponse.json({ total: 0, withQueue: 0, withoutQueue: 0, levels: [] });
  }

  const designerRows = await db.collection("pixelforge_levels")
    .find({ level_number: { $in: okLevels }, status: { $exists: true } }, { projection: { level_number: 1, queue_data: 1, field_map: 1 } })
    .toArray();
  const byLv = new Map(designerRows.map((r) => [Number(r.level_number), r]));

  const levels = okLevels.map((lv) => {
    const row = byLv.get(lv);
    return {
      level_number: lv,
      hasQueue: !!(row && row.queue_data),
      hasFieldMap: !!(row && typeof row.field_map === "string" && row.field_map.trim().length > 0),
      hasDesignerRow: !!row,
    };
  });
  const withQueue = levels.filter((l) => l.hasQueue).length;
  return NextResponse.json({
    total: okLevels.length,
    withQueue,
    withoutQueue: okLevels.length - withQueue,
    levels,
  });
}
