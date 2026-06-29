import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { ObjectId } from "mongodb";

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const db = await getDb();

  // _id 또는 level_number로 삭제
  if (ObjectId.isValid(id)) {
    await db.collection("pixelforge_levels").deleteOne({ _id: new ObjectId(id) });
  } else {
    await db.collection("pixelforge_levels").deleteOne({ level_number: parseInt(id) });
  }
  return NextResponse.json({ ok: true });
}
