import { NextRequest, NextResponse } from "next/server";
import { getDb } from "@/lib/mongodb";
import { ObjectId } from "mongodb";
import { auth } from "@/auth";
import { recordAudit } from "@/lib/audit";

export async function GET(_req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!id || !/^[a-f0-9]{24}$/i.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
  const db = await getDb();
  const doc = await db.collection("pixelforge_tasks").findOne({ _id: new ObjectId(id) });
  if (!doc) {
    return NextResponse.json({ error: "not found" }, { status: 404 });
  }
  return NextResponse.json(doc);
}

export async function DELETE(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!id || !/^[a-f0-9]{24}$/i.test(id)) {
    return NextResponse.json({ error: "invalid id" }, { status: 400 });
  }
  const db = await getDb();
  const existing = await db
    .collection("pixelforge_tasks")
    .findOne({ _id: new ObjectId(id) });
  // U1 tombstone: 삭제 직전 hermes_stopped 세팅 — 진행 중 rework 루프가 다음 사이클
  // 진입 시 멈추도록(짧은 창). 백엔드 execute 진입부의 '존재 가드'(삭제된 task=find_one None→abort)와
  // 이중 방어로 팬텀루프를 차단한다.
  await db
    .collection("pixelforge_tasks")
    .updateOne({ _id: new ObjectId(id) }, { $set: { hermes_stopped: true } });
  await db.collection("pixelforge_tasks").deleteOne({ _id: new ObjectId(id) });

  try {
    const session = await auth();
    const email = String(session?.user?.email || "").toLowerCase();
    recordAudit({
      task_id: id,
      event: "task.deleted",
      actor: { email, source: email ? "ui" : "system" },
      data: { title: (existing?.title as string) || "" },
    }).catch(() => {});
  } catch { /* ignore */ }

  return NextResponse.json({ ok: true });
}
