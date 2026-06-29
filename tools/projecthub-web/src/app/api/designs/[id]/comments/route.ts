import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { ObjectId } from "mongodb";
import { auth, isAdminEmail } from "@/auth";

export const runtime = "nodejs";

/**
 * POST — 디자인에 코멘트 추가
 * Body: { text: string }
 */
export async function POST(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!/^[a-f0-9]{24}$/.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
  const session = await auth();
  const email = (session?.user?.email || "").toLowerCase();
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const body = await req.json().catch(() => null);
  const text = String(body?.text || "").trim().slice(0, 2000);
  if (!text) return NextResponse.json({ error: "text required" }, { status: 400 });

  const author = session?.user?.name || email.split("@")[0];
  const newComment = {
    id: new ObjectId().toString(),
    text,
    author,
    author_email: email,
    created_at: new Date().toISOString(),
  };

  const db = await getDb();
  const ops: Record<string, unknown> = {
    $push: { comments: newComment },
    $set: { updated_at: new Date().toISOString() },
  };
  await db.collection("pixelforge_designs").updateOne({ _id: new ObjectId(id) }, ops);

  return NextResponse.json({ ok: true, comment: newComment });
}

/**
 * DELETE — 코멘트 삭제 (본인 또는 관리자)
 * Query: ?cid=<comment_id>
 */
export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const cid = new URL(req.url).searchParams.get("cid") || "";
  const session = await auth();
  const email = (session?.user?.email || "").toLowerCase();
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const db = await getDb();
  const doc = await db.collection("pixelforge_designs").findOne({ _id: new ObjectId(id) });
  if (!doc) return NextResponse.json({ error: "not found" }, { status: 404 });

  const target = (doc.comments || []).find((c: { id?: string }) => c.id === cid);
  if (!target) return NextResponse.json({ error: "comment not found" }, { status: 404 });

  // 본인 코멘트 또는 관리자만 삭제
  if (target.author_email !== email && !isAdminEmail(email)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }

  await db.collection("pixelforge_designs").updateOne(
    { _id: new ObjectId(id) },
    { $pull: { comments: { id: cid } } } as unknown as Record<string, unknown>,
  );
  return NextResponse.json({ ok: true });
}
