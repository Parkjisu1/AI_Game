import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

// style_image — Pro 엔드포인트용 스타일 레퍼런스 이미지 (1장)
// MongoDB pixelforge_settings 컬렉션에 singleton 저장
const COLLECTION = "pixelforge_settings";
const KEY = "style_image";

export async function GET() {
  try {
    const db = await getDb();
    const doc = await db.collection(COLLECTION).findOne({ key: KEY });
    if (!doc || !doc.base64) {
      return NextResponse.json({ ok: true, hasImage: false });
    }
    return NextResponse.json({
      ok: true,
      hasImage: true,
      width: doc.width || 0,
      height: doc.height || 0,
      preview: doc.base64.substring(0, 100),
      uploadedAt: doc.uploaded_at,
    });
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const { base64, width, height } = await req.json();
    if (!base64 || typeof base64 !== "string") {
      return NextResponse.json({ ok: false, error: "base64 필수" }, { status: 400 });
    }
    const db = await getDb();
    await db.collection(COLLECTION).updateOne(
      { key: KEY },
      {
        $set: {
          key: KEY,
          base64: base64.startsWith("data:") ? base64.split(",")[1] || base64 : base64,
          width: width || 0,
          height: height || 0,
          uploaded_at: new Date().toISOString(),
        },
      },
      { upsert: true }
    );
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 });
  }
}

export async function DELETE() {
  try {
    const db = await getDb();
    await db.collection(COLLECTION).deleteOne({ key: KEY });
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 });
  }
}
