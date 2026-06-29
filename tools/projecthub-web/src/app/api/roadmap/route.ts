import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";

// 단일 문서 컬렉션 — 가장 최근 업로드된 로드맵 1개만 유지
const COLLECTION = "pixelforge_roadmap";
const SINGLETON_KEY = "current";

export async function GET() {
  try {
    const db = await getDb();
    const doc = await db.collection(COLLECTION).findOne({ key: SINGLETON_KEY });
    if (!doc) return NextResponse.json({ ok: true, data: null });
    return NextResponse.json({ ok: true, data: doc.data });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    if (!body?.data) {
      return NextResponse.json({ ok: false, error: "data 필드 누락" }, { status: 400 });
    }
    const db = await getDb();
    await db.collection(COLLECTION).updateOne(
      { key: SINGLETON_KEY },
      { $set: { key: SINGLETON_KEY, data: body.data, updated_at: new Date().toISOString() } },
      { upsert: true }
    );
    return NextResponse.json({ ok: true });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json({ ok: false, error: msg }, { status: 500 });
  }
}
