import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { auth, isAdminEmail } from "@/auth";
import { ObjectId } from "mongodb";

export const runtime = "nodejs";

interface MetaBody {
  border_px?: number;
  border_top?: number;
  border_bottom?: number;
  border_left?: number;
  border_right?: number;
}

/**
 * PATCH /api/designs/[id]/9slice-meta
 *
 * 정통 9-slice 메타데이터 등록 — 이미지 자체는 변형하지 않고
 * 디자인 도큐먼트에 4면 보더값(top/right/bottom/left)만 추가.
 * Unity import 시 Sprite Editor의 Border 입력값으로 그대로 사용.
 *
 * Body: 단일 보더면 border_px, 4면 다르면 border_top/right/bottom/left
 *
 * DELETE: nine_slice 메타 제거
 */
export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  // 인증
  const authHeader = (req.headers.get("authorization") || "").trim();
  const bearerKey = authHeader.toLowerCase().startsWith("bearer ")
    ? authHeader.slice(7).trim()
    : "";
  const expectedKey = process.env.HERMES_INTERNAL_API_KEY || "";
  let email: string | null | undefined;
  if (bearerKey && expectedKey && bearerKey === expectedKey) {
    email = req.headers.get("x-hermes-on-behalf-of") || "hermes@aimed.local";
  } else {
    const session = await auth();
    email = session?.user?.email;
  }
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  if (!/^[a-f0-9]{24}$/.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }

  const body = (await req.json().catch(() => null)) as MetaBody | null;
  if (!body) return NextResponse.json({ error: "invalid body" }, { status: 400 });

  const db = await getDb();
  const orig = await db.collection("pixelforge_designs").findOne({ _id: new ObjectId(id) });
  if (!orig) return NextResponse.json({ error: "design not found" }, { status: 404 });

  // owner 또는 admin
  const isOwner = (orig.created_by_email || "").toLowerCase() === email.toLowerCase();
  if (!isOwner && !isAdminEmail(email)) {
    return NextResponse.json({ error: "forbidden — owner or admin only" }, { status: 403 });
  }

  // 이미지 dimension (보더 clamp용) — 첫 번째 이미지 기준
  const firstImg = (orig.images || [])[0];
  const W = firstImg?.width || 1024;
  const H = firstImg?.height || 1024;

  const def = Math.max(0, Math.min(512, Math.floor(body.border_px || 96)));
  const t = clamp(body.border_top ?? def, H);
  const b = clamp(body.border_bottom ?? def, H);
  const l = clamp(body.border_left ?? def, W);
  const r = clamp(body.border_right ?? def, W);

  if (t + b >= H || l + r >= W) {
    return NextResponse.json({
      error: `border too large — top+bottom(${t + b}) < height(${H}); left+right(${l + r}) < width(${W})`,
    }, { status: 400 });
  }

  const nineSlice = {
    top: t,
    right: r,
    bottom: b,
    left: l,
    image_width: W,
    image_height: H,
    set_at: new Date().toISOString(),
    set_by: String(email).toLowerCase(),
  };

  await db.collection("pixelforge_designs").updateOne(
    { _id: new ObjectId(id) },
    { $set: { nine_slice: nineSlice } }
  );

  return NextResponse.json({ ok: true, nine_slice: nineSlice });
}

/**
 * DELETE — 9-slice 메타 제거
 */
export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const session = await auth();
  const email = String(session?.user?.email || "").toLowerCase();
  if (!email) return NextResponse.json({ error: "unauthorized" }, { status: 401 });

  const { id } = await params;
  if (!/^[a-f0-9]{24}$/.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
  const db = await getDb();
  const orig = await db.collection("pixelforge_designs").findOne({ _id: new ObjectId(id) });
  if (!orig) return NextResponse.json({ error: "not found" }, { status: 404 });
  const isOwner = (orig.created_by_email || "").toLowerCase() === email;
  if (!isOwner && !isAdminEmail(email)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  await db.collection("pixelforge_designs").updateOne(
    { _id: new ObjectId(id) },
    { $unset: { nine_slice: "" } }
  );
  return NextResponse.json({ ok: true });
}

function clamp(v: number, dim: number): number {
  const n = Math.max(0, Math.floor(v || 0));
  return Math.min(n, Math.floor(dim / 2) - 1);
}
