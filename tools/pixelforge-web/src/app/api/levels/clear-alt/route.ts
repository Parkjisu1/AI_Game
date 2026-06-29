import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

// alt 필드($unset)만 제거 — 원본은 유지
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const levelNumber = Number(body.level_number);
    if (!levelNumber || levelNumber <= 0) {
      return NextResponse.json({ ok: false, error: "level_number 필수" }, { status: 400 });
    }
    const db = await getDb();
    const result = await db.collection("pixelforge_levels").updateOne(
      { level_number: levelNumber },
      {
        $unset: {
          image_base64_alt: "",
          field_map_alt: "",
          alt_meta: "",
        },
        $set: { updated_at: new Date().toISOString() },
      }
    );
    return NextResponse.json({ ok: true, modified: result.modifiedCount });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
