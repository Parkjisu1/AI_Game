import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

export async function GET() {
  try {
    const db = await getDb();
    const levels = await db.collection("pixelforge_levels").find().sort({ level_number: 1 }).toArray();
    return NextResponse.json(levels);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error("[GET /api/levels]", msg);
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}

// upsert에 안전하지 않은 필드 제거 + level_number 검증
function sanitize(level: Record<string, unknown>): Record<string, unknown> | null {
  const clean: Record<string, unknown> = { ...level };
  // _id는 MongoDB가 ObjectId로 기대하므로 제거 (string 들어오면 cast 에러)
  delete clean._id;
  // 빈 문자열/undefined 필드 정리
  for (const k of Object.keys(clean)) {
    if (clean[k] === undefined || clean[k] === null) delete clean[k];
  }
  // level_number는 양의 정수여야 함
  const lvNum = Number(clean.level_number);
  if (!Number.isFinite(lvNum) || lvNum <= 0) return null;
  clean.level_number = lvNum;
  return clean;
}

export async function POST(req: NextRequest) {
  try {
    const db = await getDb();
    const body = await req.json();

    if (Array.isArray(body)) {
      // 배치 — 각 항목 sanitize, 무효 항목은 스킵
      const valid: Record<string, unknown>[] = [];
      const skipped: Array<{ index: number; reason: string }> = [];
      body.forEach((row, i) => {
        const cleaned = sanitize(row);
        if (cleaned) valid.push(cleaned);
        else skipped.push({ index: i, reason: "invalid level_number" });
      });

      if (valid.length === 0) {
        return NextResponse.json(
          { ok: false, error: "유효한 행 없음 (level_number가 양수여야 함)", skipped },
          { status: 400 }
        );
      }

      const ops = valid.map((level) => ({
        updateOne: {
          filter: { level_number: level.level_number },
          update: { $set: { ...level, updated_at: new Date().toISOString() } },
          upsert: true,
        },
      }));
      const result = await db.collection("pixelforge_levels").bulkWrite(ops);
      return NextResponse.json({
        ok: true,
        count: result.upsertedCount + result.modifiedCount,
        skipped: skipped.length,
      });
    }

    // 단일 항목
    const cleaned = sanitize(body);
    if (!cleaned) {
      return NextResponse.json(
        { ok: false, error: "level_number가 양수여야 함" },
        { status: 400 }
      );
    }
    cleaned.updated_at = new Date().toISOString();
    cleaned.created_at = cleaned.created_at || new Date().toISOString();
    await db.collection("pixelforge_levels").updateOne(
      { level_number: cleaned.level_number },
      { $set: cleaned },
      { upsert: true }
    );
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    const stack = e instanceof Error ? e.stack?.split("\n").slice(0, 3).join(" | ") : "";
    console.error("[POST /api/levels]", msg, stack);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
