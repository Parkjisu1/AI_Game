import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { ObjectId } from "mongodb";
import { auth, isAdminEmail } from "@/auth";
import { promises as fs } from "fs";
import path from "path";

export const runtime = "nodejs";

const STORAGE_DIR = process.env.DESIGNS_STORAGE_DIR || "/home/aimed/projecthub-web/data/designs";

interface DesignDoc {
  _id: InstanceType<typeof ObjectId>;
  images: Array<{ filename: string; width: number; height: number }>;
  created_by_email: string;
}

export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = await getDb();
  try {
    const doc = await db.collection("pixelforge_designs").findOne({ _id: new ObjectId(id) });
    if (!doc) return NextResponse.json({ error: "not found" }, { status: 404 });
    return NextResponse.json({
      _id: String(doc._id),
      prompt: doc.prompt,
      tags: doc.tags || [],
      model: doc.model,
      size: doc.size,
      n: doc.n,
      images: doc.images || [],
      created_by_email: doc.created_by_email,
      created_at: doc.created_at,
    });
  } catch {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
}

/**
 * PATCH — 즐겨찾기·별점 등 가벼운 메타데이터 갱신.
 * Body 키: starred (boolean), star_rating (0-5)
 * 누구나 가능 (개인 즐겨찾기/평가)
 */
export async function PATCH(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const session = await auth();
  const email = session?.user?.email;
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => null);
  if (!body || typeof body !== "object") {
    return NextResponse.json({ error: "invalid body" }, { status: 400 });
  }

  const update: Record<string, unknown> = {};
  if (typeof body.starred === "boolean") {
    update[`stars.${email.replace(/[.@]/g, "_")}`] = body.starred;
  }
  if (typeof body.star_rating === "number") {
    const r = Math.max(0, Math.min(5, Math.floor(body.star_rating)));
    update[`star_ratings.${email.replace(/[.@]/g, "_")}`] = r;
  }
  if (Object.keys(update).length === 0) {
    return NextResponse.json({ error: "no valid fields" }, { status: 400 });
  }

  try {
    await db_update(id, update);
    return NextResponse.json({ ok: true });
  } catch {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
}

async function db_update(id: string, set: Record<string, unknown>) {
  const db = await getDb();
  await db.collection("pixelforge_designs").updateOne(
    { _id: new ObjectId(id) },
    { $set: set }
  );
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const session = await auth();
  const email = session?.user?.email;
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const db = await getDb();
  let doc: DesignDoc | null;
  try {
    doc = (await db
      .collection<DesignDoc>("pixelforge_designs")
      .findOne({ _id: new ObjectId(id) })) as DesignDoc | null;
  } catch {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
  if (!doc) return NextResponse.json({ error: "not found" }, { status: 404 });

  // 제작자 본인 또는 관리자만 삭제
  if (doc.created_by_email !== email.toLowerCase() && !isAdminEmail(email)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  // 파일 삭제 (실패해도 DB 레코드는 지움)
  for (const img of doc.images || []) {
    try {
      await fs.unlink(path.join(STORAGE_DIR, img.filename));
    } catch { /* ignore */ }
  }
  await db.collection("pixelforge_designs").deleteOne({ _id: new ObjectId(id) });
  return NextResponse.json({ ok: true });
}
