import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

export const runtime = "nodejs";

// PixelForge Queue Confirm endpoint
//
// 디자이너가 [💾 큐 확정] 클릭 → 현재 큐 데이터를 pixelforge_levels[level_number].queue_data로 저장.
// 휘발성 generate와 분리 — 명시적 confirm만 영구 저장.
//
// POST body:
//   {
//     level_number: number,
//     queue: QueueResult,                  // /api/queue/generate 응답의 queue 필드 그대로
//     designer_email?: string,
//   }

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as Record<string, unknown>;
    const lvNum = Number(body.level_number);
    if (!Number.isFinite(lvNum) || lvNum <= 0) {
      return NextResponse.json({ ok: false, error: "invalid level_number" }, { status: 400 });
    }
    const queue = body.queue as Record<string, unknown> | undefined;
    if (!queue || typeof queue !== "object") {
      return NextResponse.json({ ok: false, error: "missing queue" }, { status: 400 });
    }

    const db = await getDb();
    const now = new Date().toISOString();
    const designerEmail = typeof body.designer_email === "string" ? body.designer_email : null;

    const result = await db.collection("pixelforge_levels").updateOne(
      { level_number: lvNum },
      {
        $set: {
          queue_data: queue,
          queue_confirmed_at: now,
          queue_confirmed_by: designerEmail,
          updated_at: now,
        },
      },
      { upsert: false },
    );

    if (result.matchedCount === 0) {
      return NextResponse.json(
        { ok: false, error: `level ${lvNum} not found in pixelforge_levels` },
        { status: 404 },
      );
    }
    return NextResponse.json({ ok: true, modified: result.modifiedCount });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[POST /api/queue/confirm]", msg);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
