import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

// style 레퍼런스 이미지 — PixelLab generate-image-v2 스타일 참조.
// 유형별 4종을 pixelforge_settings 에 저장:
//   - ?type=character|background|structure → key=style_image_<type>
//   - type 없음/default → key=style_image (공통 fallback)
const COLLECTION = "pixelforge_settings";

function keyFromReq(req: NextRequest): string {
  const t = new URL(req.url).searchParams.get("type");
  if (t === "character" || t === "background" || t === "structure") return `style_image_${t}`;
  return "style_image";
}

export async function GET(req: NextRequest) {
  try {
    const full = new URL(req.url).searchParams.get("full") === "1";
    const key = keyFromReq(req);
    const db = await getDb();
    const doc = await db.collection(COLLECTION).findOne({ key });
    if (!doc || !doc.base64) {
      return NextResponse.json({ ok: true, hasImage: false, key });
    }
    return NextResponse.json({
      ok: true,
      hasImage: true,
      key,
      width: doc.width || 0,
      height: doc.height || 0,
      ...(full ? { base64: doc.base64 } : { preview: doc.base64.substring(0, 100) }),
      uploadedAt: doc.uploaded_at,
    });
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const key = keyFromReq(req);
    const { base64, width, height } = await req.json();
    if (!base64 || typeof base64 !== "string") {
      return NextResponse.json({ ok: false, error: "base64 필수" }, { status: 400 });
    }
    const db = await getDb();
    await db.collection(COLLECTION).updateOne(
      { key },
      {
        $set: {
          key,
          base64: base64.startsWith("data:") ? base64.split(",")[1] || base64 : base64,
          width: width || 0,
          height: height || 0,
          uploaded_at: new Date().toISOString(),
        },
      },
      { upsert: true }
    );
    return NextResponse.json({ ok: true, key });
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const key = keyFromReq(req);
    const db = await getDb();
    await db.collection(COLLECTION).deleteOne({ key });
    return NextResponse.json({ ok: true, key });
  } catch (e: unknown) {
    return NextResponse.json({ ok: false, error: String(e) }, { status: 500 });
  }
}
